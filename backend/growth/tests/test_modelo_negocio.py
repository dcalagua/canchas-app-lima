"""MODELO DE NEGOCIO de las reservas elegible en la torre (2-oct-2026, hoja
«Cálculo PCG» del director): el modelo 1 (el de siempre) sigue intacto y el
modelo 2 reparte el costo de la pasarela entre jugador y dueño y suma las
comisiones Pichangol que pone el operador."""
from fastapi.testclient import TestClient

import config
from db.store import CONFIG_DEFAULT, Stores, stores
from main import app
from pagos import modelo_negocio as mn
from pagos.router import _liquidacion_dict

H = {"X-Admin-Token": "t"}


def _cli(monkeypatch):
    monkeypatch.setattr(config, "ADMIN_PANEL_TOKEN", "t")
    monkeypatch.setattr(config, "APP_API_KEY", "")
    for k in list(stores.config):
        if k.startswith(("m2_", "cargo_", "tarifa_")) or k == "modelo_reservas":
            del stores.config[k]
    stores.config.update({k: v for k, v in CONFIG_DEFAULT.items()
                          if k.startswith(("m2_", "cargo_", "tarifa_")) or k == "modelo_reservas"})
    return TestClient(app)


def test_formula_igual_a_la_hoja_del_director(monkeypatch):
    _cli(monkeypatch)
    for k, v in mn.CLAVES_DEFAULT.items():  # CONFIG_DEFAULT espejo del módulo
        assert CONFIG_DEFAULT.get(k) == v, k
    c = mn.calcular(9000, "PEN")
    assert c["pasarela_total_centimos"] == 850          # 8.496
    assert c["pasarela_cliente_centimos"] == 425 and c["pasarela_dueno_centimos"] == 425
    assert c["dueno_recibe_centimos"] == 8575            # 85.752
    assert c["cliente_paga_centimos"] == 9538            # 95.378976
    assert c["ingreso_pcg_centimos"] == 113              # 1.130976
    assert c["cargo_cliente_centimos"] == 538 and c["descuento_dueno_centimos"] == 425
    # "Sobre lo cobrado": la pasarela se calcula sobre lo que paga el jugador.
    p = {**mn.params("PEN"), "sobre": "cobrado"}
    c2 = mn.calcular(9000, "PEN", p)
    assert c2["pasarela_total_centimos"] > 850 and abs(c2["pasarela_real_centimos"] - c2["pasarela_total_centimos"]) <= 1


def test_modelo_1_sigue_igual_y_el_2_se_activa_desde_la_torre(monkeypatch):
    cli = _cli(monkeypatch)
    # Modelo 1 por defecto: cargo de reservas apagado → el jugador paga el precio.
    assert mn.modelo_reservas() == "1"
    r = cli.post("/pagos/cotizar", json={"linea": "reservas", "moneda": "PEN", "base_centimos": 9000}).json()
    assert r["cargo_centimos"] == 0 and r["total_centimos"] == 9000
    r = cli.post("/pagos/liquidacion-online", json={"dueno_id": "m1@x.com", "monto_soles": 90, "reserva_id": "m1_res"}).json()
    assert r["comision_centimos"] == 450  # 5 %
    # La torre: lectura, validación y cambio de modelo con comisiones propias.
    g = cli.get("/pagos/modelo-negocio?monto=90", headers=H).json()
    assert g["modelo_reservas"] == "1" and g["simulacion"]["modelo_2"]["cliente_paga_centimos"] == 9538
    assert cli.get("/pagos/modelo-negocio").status_code in (401, 403)
    assert cli.post("/pagos/modelo-negocio", headers=H, json={"modelo_reservas": "3"}).status_code == 400
    assert cli.post("/pagos/modelo-negocio", headers=H, json={"monedas": {"PEN": {"cliente_pct": 99}}}).status_code == 400
    sim = cli.post("/pagos/modelo-negocio/simular", headers=H,
                   json={"monto": 90, "moneda": "PEN", "params": {"cliente_pct": 2, "dueno_pct": 1}}).json()
    assert sim["modelo_2"]["pcg_dueno_centimos"] == 86 and mn.modelo_reservas() == "1"  # simular no guarda
    ok = cli.post("/pagos/modelo-negocio", headers=H,
                  json={"modelo_reservas": "2", "monedas": {"PEN": {"cliente_pct": 1.2, "dueno_pct": 0}}}).json()
    assert ok["ok"] and ok["modelo_reservas"] == "2"
    # Checkout (APK y web): el cargo es la parte de la pasarela + 1.2 %.
    assert cli.get("/config/cargo-servicio").json()["activo"]["reservas"] is True
    r = cli.post("/pagos/cotizar", json={"linea": "reservas", "moneda": "PEN", "base_centimos": 9000}).json()
    assert r["cargo_centimos"] == 538 and r["total_centimos"] == 9538
    assert [d["clave"] for d in r["desglose"]] == ["pago_en_linea", "servicio_pichangol"]
    assert sum(d["monto_centimos"] for d in r["desglose"]) == 538
    # Academias no cambian con el modelo de reservas.
    a = cli.post("/pagos/cotizar", json={"linea": "academias", "moneda": "PEN", "base_centimos": 9000}).json()
    assert a["cargo_centimos"] == 0
    # Liquidación al dueño: recibe 85.75 y queda CONGELADO aunque cambien los %.
    r = cli.post("/pagos/liquidacion-online", json={"dueno_id": "m2@x.com", "monto_soles": 90, "reserva_id": "m2_res",
                                                    "cargo_servicio_centimos": 538, "medio": "yape"}).json()
    assert r["modelo"] == "2" and r["comision_centimos"] == 425 and r["neto_centimos"] == 8575
    p = stores.pago_por_charge("m2_res")
    assert p.modelo_cobro == "m2" and p.comision_centimos == 425
    cli.post("/pagos/modelo-negocio", headers=H, json={"monedas": {"PEN": {"dueno_pct": 5}}})
    d = _liquidacion_dict(p)
    assert d["comision_soles"] == 4.25 and d["neto_soles"] == 85.75
    # Reserva en EFECTIVO con modelo 2: solo el % del dueño (aquí 5 % de 90).
    r = cli.post("/pagos/comision-reserva", json={"dueno_id": "m2@x.com", "monto_soles": 90, "reserva_id": "m2_ef"}).json()
    assert r["comision_centimos"] == 450
    cli.post("/pagos/modelo-negocio", headers=H, json={"monedas": {"PEN": {"dueno_pct": 0}}})
    r = cli.post("/pagos/comision-reserva", json={"dueno_id": "m2@x.com", "monto_soles": 90, "reserva_id": "m2_ef2"}).json()
    assert r["comision_centimos"] == 0 and stores.pago_por_charge("m2_ef2") is None
    # Volver al modelo 1 no toca lo ya cobrado.
    cli.post("/pagos/modelo-negocio", headers=H, json={"modelo_reservas": "1"})
    assert _liquidacion_dict(stores.pago_por_charge("m2_res"))["neto_soles"] == 85.75
    assert "Modelo de negocio" in cli.get("/admin").text and "cargarModeloNegocio" in cli.get("/admin").text


def test_modelo_del_pago_sobrevive_al_snapshot():
    s = Stores()
    s.registrar_pago(tipo="liquidacion_online", monto_centimos=9000, moneda="PEN", estado="aprobado",
                     dueno_id="d@x.com", culqi_charge_id="r1", comision_centimos=425, modelo_cobro="m2")
    s2 = Stores()
    s2.load_state(s.to_state())
    assert s2.pago_por_charge("r1").modelo_cobro == "m2"
