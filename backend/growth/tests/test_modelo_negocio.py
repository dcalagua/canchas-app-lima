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
    # La HOJA del director (pasarela sobre el precio, con IGV, tarifa de tarjeta).
    hoja = {**mn.params("PEN"), "sobre": "precio", "igv_aplica": "1"}
    c = mn.calcular(9000, "PEN", hoja, medio="tarjeta")
    assert c["pasarela_total_centimos"] == 850          # 8.496
    assert c["pasarela_cliente_centimos"] == 425 and c["pasarela_dueno_centimos"] == 425
    assert c["dueno_recibe_centimos"] == 8575            # 85.752
    assert c["cliente_paga_centimos"] == 9538            # 95.378976
    assert c["ingreso_pcg_centimos"] == 113              # 1.130976
    assert c["cargo_cliente_centimos"] == 538 and c["descuento_dueno_centimos"] == 425


def test_tarifa_por_medio_sobre_lo_cobrado_y_sin_igv(monkeypatch):
    """2-oct-2026 (calculadora de Culqi del director): Yape = 3.44 % + $ 0.20
    sin IGV, tarjeta = 2.5 % + 5.5 %; Culqi cobra sobre lo COBRADO. Así lo que
    Pichangol gana de verdad = lo que pone el operador, con cualquier medio."""
    cli = _cli(monkeypatch)
    y = mn.calcular(10000, "PEN", medio="yape")
    t = mn.calcular(10000, "PEN", medio="tarjeta")
    assert (y["cliente_paga_centimos"], y["dueno_recibe_centimos"]) == (10339, 9784)
    assert (t["cliente_paga_centimos"], t["dueno_recibe_centimos"]) == (10547, 9578)
    for c in (y, t):  # lo que la pasarela cobra de verdad = lo repartido
        assert abs(c["pasarela_real_centimos"] - c["pasarela_total_centimos"]) <= 1
        assert abs(c["margen_real_centimos"] - c["ingreso_pcg_centimos"]) <= 1
    assert y["fijo_centimos"] == 77 and not y["igv_aplica"] and y["banco_centimos"] == 0
    # Medio desconocido (seña, APK viejo) = tarjeta; en $ / Bs solo hay "tarjeta".
    assert mn.medio_de("sena", "PEN") == "tarjeta" and mn.medio_de("yape", "USD") == "tarjeta"
    assert mn.calcular(10000, "USD", medio="yape")["medio"] == "tarjeta"
    # La web cotiza con el medio elegido en la página (Yape ⇄ Tarjeta cambia el total).
    assert cli.post("/pagos/modelo-negocio", headers=H, json={"modelo_reservas": "2"}).json()["ok"]
    wy = cli.get("/web/cotizar?linea=reservas&moneda=PEN&base=10000&medio=yape").json()
    wt = cli.get("/web/cotizar?linea=reservas&moneda=PEN&base=10000&medio=tarjeta").json()
    assert (wy["total_centimos"], wt["total_centimos"]) == (10339, 10547)
    assert cli.get("/web/cotizar?linea=reservas&moneda=PEN&base=10000").json()["total_centimos"] == 10547
    assert "medio" in cli.get("/admin").text and "mnToggle" in cli.get("/admin").text
    # Migración: un snapshot viejo (pasarela sobre el precio) pasa a "lo cobrado" sin IGV, una vez.
    s = Stores()
    estado = s.to_state()
    estado["config"] = {k: v for k, v in estado["config"].items() if k != "m2_tarifas_v2"}
    estado["config"]["m2_PEN_sobre"] = "precio"
    s2 = Stores()
    s2.load_state(estado)
    assert s2.config["m2_PEN_sobre"] == "cobrado" and s2.config["m2_PEN_igv_aplica"] == "0"


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
    assert g["modelo_reservas"] == "1" and g["simulacion"]["modelo_2"]["cliente_paga_centimos"] == 9309  # Yape
    assert g["simulacion"]["modelo_2_medios"]["tarjeta"]["cliente_paga_centimos"] == 9492
    assert cli.get("/pagos/modelo-negocio").status_code in (401, 403)
    assert cli.post("/pagos/modelo-negocio", headers=H, json={"modelo_reservas": "3"}).status_code == 400
    assert cli.post("/pagos/modelo-negocio", headers=H, json={"monedas": {"PEN": {"cliente_pct": 99}}}).status_code == 400
    sim = cli.post("/pagos/modelo-negocio/simular", headers=H,
                   json={"monto": 90, "moneda": "PEN", "params": {"cliente_pct": 2, "dueno_pct": 1}}).json()
    assert sim["modelo_2"]["pcg_dueno_centimos"] == 88 and mn.modelo_reservas() == "1"  # simular no guarda
    ok = cli.post("/pagos/modelo-negocio", headers=H,
                  json={"modelo_reservas": "2", "monedas": {"PEN": {"cliente_pct": 1.2, "dueno_pct": 0}}}).json()
    assert ok["ok"] and ok["modelo_reservas"] == "2"
    # Checkout (APK y web): el cargo es la parte de la pasarela + 1.2 %.
    assert cli.get("/config/cargo-servicio").json()["activo"]["reservas"] is True
    # Sin medio = tarjeta (APK viejo); con Yape el jugador paga menos.
    r = cli.post("/pagos/cotizar", json={"linea": "reservas", "moneda": "PEN", "base_centimos": 9000}).json()
    assert r["cargo_centimos"] == 492 and r["total_centimos"] == 9492 and r["medio"] == "tarjeta"
    assert [d["clave"] for d in r["desglose"]] == ["pago_en_linea", "servicio_pichangol"]
    assert sum(d["monto_centimos"] for d in r["desglose"]) == 492
    r = cli.post("/pagos/cotizar", json={"linea": "reservas", "moneda": "PEN", "base_centimos": 9000, "medio": "yape"}).json()
    assert r["cargo_centimos"] == 309 and r["medio"] == "yape" and "Yape" in r["desglose"][0]["nombre"]
    # Academias no cambian con el modelo de reservas.
    a = cli.post("/pagos/cotizar", json={"linea": "academias", "moneda": "PEN", "base_centimos": 9000}).json()
    assert a["cargo_centimos"] == 0
    # Liquidación al dueño: recibe 85.75 y queda CONGELADO aunque cambien los %.
    r = cli.post("/pagos/liquidacion-online", json={"dueno_id": "m2@x.com", "monto_soles": 90, "reserva_id": "m2_res",
                                                    "cargo_servicio_centimos": 309, "medio": "yape"}).json()
    assert r["modelo"] == "2" and r["comision_centimos"] == 199 and r["neto_centimos"] == 8801
    p = stores.pago_por_charge("m2_res")
    assert p.modelo_cobro == "m2" and p.comision_centimos == 199
    # Seña pagada con tarjeta: el dueño paga la pasarela de la TARJETA.
    r = cli.post("/pagos/liquidacion-online", json={"dueno_id": "m2@x.com", "monto_soles": 90, "reserva_id": "m2_sena",
                                                    "medio": "sena", "medio_pago": "tarjeta"}).json()
    assert r["comision_centimos"] == 380
    cli.post("/pagos/modelo-negocio", headers=H, json={"monedas": {"PEN": {"dueno_pct": 5}}})
    d = _liquidacion_dict(p)
    assert d["comision_soles"] == 1.99 and d["neto_soles"] == 88.01
    # Reserva en EFECTIVO con modelo 2: solo el % del dueño (aquí 5 % de 90).
    r = cli.post("/pagos/comision-reserva", json={"dueno_id": "m2@x.com", "monto_soles": 90, "reserva_id": "m2_ef"}).json()
    assert r["comision_centimos"] == 450
    cli.post("/pagos/modelo-negocio", headers=H, json={"monedas": {"PEN": {"dueno_pct": 0}}})
    r = cli.post("/pagos/comision-reserva", json={"dueno_id": "m2@x.com", "monto_soles": 90, "reserva_id": "m2_ef2"}).json()
    assert r["comision_centimos"] == 0 and stores.pago_por_charge("m2_ef2") is None
    # Volver al modelo 1 no toca lo ya cobrado.
    cli.post("/pagos/modelo-negocio", headers=H, json={"modelo_reservas": "1"})
    assert _liquidacion_dict(stores.pago_por_charge("m2_res"))["neto_soles"] == 88.01
    assert "Modelo de negocio" in cli.get("/admin").text and "cargarModeloNegocio" in cli.get("/admin").text


def test_modelo_del_pago_sobrevive_al_snapshot():
    s = Stores()
    s.registrar_pago(tipo="liquidacion_online", monto_centimos=9000, moneda="PEN", estado="aprobado",
                     dueno_id="d@x.com", culqi_charge_id="r1", comision_centimos=425, modelo_cobro="m2")
    s2 = Stores()
    s2.load_state(s.to_state())
    assert s2.pago_por_charge("r1").modelo_cobro == "m2"


def test_minimo_por_reserva_sube_el_pct_en_canchas_baratas(monkeypatch):
    """Opción B del director (2-oct-2026): comisión al jugador = max(1.2 % de
    su base, S/ 1). En canchas baratas el % efectivo sube; desde ~S/ 80 manda
    el %. Nunca cobra menos a una cancha más cara."""
    cli = _cli(monkeypatch)
    assert mn.params("PEN")["cliente_min"] == 1 and mn.params("USD")["cliente_min"] == 0.3
    assert mn.params("BOB")["cliente_min"] == 2 and mn.params("PEN")["dueno_min"] == 0
    c30 = mn.calcular(3000, "PEN")
    assert c30["pcg_cliente_centimos"] == 100 and c30["cliente_min_aplicado"]
    assert c30["cliente_pct_efectivo"] == 3.2 and c30["cliente_paga_centimos"] == 3229
    c90 = mn.calcular(9000, "PEN")      # la hoja del director no cambia
    assert c90["pcg_cliente_centimos"] == 113 and not c90["cliente_min_aplicado"]
    prev = -1
    for precio in range(500, 30001, 500):
        c = mn.calcular(precio, "PEN")
        assert c["pcg_cliente_centimos"] >= prev
        prev = c["pcg_cliente_centimos"]
    # Tope opcional: con 2 % de tope, la cancha de S/ 30 cobra 2 % y no S/ 1.
    c = mn.calcular(3000, "PEN", {**mn.params("PEN"), "cliente_tope_pct": 2})
    assert c["pcg_cliente_centimos"] == 63
    # Mínimo del dueño: aplica en línea y en efectivo; nunca más que su base.
    p = {**mn.params("PEN"), "dueno_min": 1.5}
    assert mn.calcular(3000, "PEN", p)["pcg_dueno_centimos"] == 150
    assert mn.calcular(100, "PEN", {**p, "dueno_min": 50})["dueno_recibe_centimos"] == 0
    cli.post("/pagos/modelo-negocio", headers=H, json={"modelo_reservas": "2", "monedas": {"PEN": {"dueno_min": 1.5}}})
    assert mn.comision_efectivo_centimos(3000, "PEN") == 150
    r = cli.post("/pagos/comision-reserva", json={"dueno_id": "m2min@x.com", "monto_soles": 30, "reserva_id": "m2min"}).json()
    assert r["comision_centimos"] == 150
    # La cotización del checkout usa el mínimo; el simulador trae la curva.
    q = cli.post("/pagos/cotizar", json={"linea": "reservas", "moneda": "PEN", "base_centimos": 3000}).json()
    assert q["cargo_centimos"] == 229
    sim = cli.post("/pagos/modelo-negocio/simular", headers=H,
                   json={"monto": 30, "moneda": "PEN", "params": {"cliente_min": 2}}).json()
    assert sim["modelo_2"]["pcg_cliente_centimos"] == 200
    assert [x["precio"] for x in sim["curva"]] == [20, 30, 50, 90, 150]
    assert cli.post("/pagos/modelo-negocio", headers=H,
                    json={"monedas": {"PEN": {"cliente_min": 500}}}).status_code == 400
