"""Tarifa de la pasarela configurable en la torre + margen real por cobro
(pregunta del director, 26-sep-2026: "si pagué 15, ¿por qué al dueño le tocan
13? ¿cuánto me descuenta Culqi y cuál es mi comisión?")."""
from fastapi.testclient import TestClient

import config
from db.store import stores
from main import app
from pagos import tarifas_pasarela as tp
from pagos.router import _liquidacion_dict, comision_centimos

H = {"X-Admin-Token": "t"}


def _cli(monkeypatch):
    monkeypatch.setattr(config, "ADMIN_PANEL_TOKEN", "t")
    return TestClient(app)


def test_costo_de_culqi_y_margen_sobre_una_reserva_de_15(monkeypatch):
    for k in list(stores.config):
        if k.startswith("tarifa_"):
            del stores.config[k]
    # Referencia publicada de Culqi: 3.44 % + S/ 0.30 + IGV 18 % → sobre S/ 15 ≈ S/ 0.96.
    assert tp.costo_centimos(1500, "PEN", "tarjeta", "liquidacion_online") == 96
    com = comision_centimos(15.0, "PEN")
    assert com == 200  # 5 % = 0.75 < mínimo S/ 2
    d = tp.desglose(1500, com, "PEN", "tarjeta", "liquidacion_online")
    assert d["neto_centimos"] == 1300 and d["margen_centimos"] == 104 and d["pasarela"] == "culqi"
    # Pagado con SALDO (bodega, torneo): la pasarela ya se pagó al recargar → 0.
    assert tp.costo_centimos(1500, "PEN", None, "venta_bodega") == 0
    assert tp.costo_centimos(1500, "PEN", None, "inscripcion_torneo_ingreso") == 0
    # Otras pasarelas sin configurar → 0 (no se inventa un costo).
    assert tp.costo_centimos(1000, "USD", "tarjeta", "liquidacion_online") == 0
    assert tp.pasarela_de("BOB") == "libelula" and tp.pasarela_de("USD") == "payphone"
    # La fila de la torre lleva pasarela y margen.
    p = stores.registrar_pago(tipo="liquidacion_online", monto_centimos=1500, moneda="PEN", estado="aprobado",
                              dueno_id="dueno@x.com", culqi_charge_id="res_tp_1", concepto="Club · Cancha 1 · Ana · hoy 19:00", medio="yape")
    x = _liquidacion_dict(p)
    assert x["bruto_soles"] == 15 and x["comision_soles"] == 2 and x["neto_soles"] == 13
    assert x["pasarela_soles"] == 0.96 and x["margen_soles"] == 1.04 and x["medio"] == "yape"


def test_torre_configura_tarifas_y_simula(monkeypatch):
    cli = _cli(monkeypatch)
    assert cli.get("/pagos/tarifas-pasarela").status_code in (401, 403, 503)
    j = cli.get("/pagos/tarifas-pasarela?monto=15&moneda=PEN&medio=tarjeta", headers=H).json()
    assert j["tarifas"]["culqi"]["medios"]["tarjeta"] == {"pct": 3.44, "fijo": 0.3} and j["tarifas"]["culqi"]["configurada"]
    assert j["tarifas"]["payphone"]["configurada"] is False
    s = j["simulacion"]
    assert s == {"moneda": "PEN", "simbolo": "S/", "medio": "tarjeta", "pasarela": "culqi", "bruto_soles": 15.0, "pasarela_soles": 0.96,
                 "comision_soles": 2.0, "margen_soles": 1.04, "neto_soles": 13.0, "comision_pct": config.COMISION_PORC, "comision_min": 2.0}
    # Guardar: Yape más barato y PayPhone configurado; validación de rangos.
    r = cli.post("/pagos/tarifas-pasarela", headers=H, json={"culqi": {"medios": {"yape": {"pct": 2.5, "fijo": 0}}, "impuesto_pct": 18},
                                                             "payphone": {"medios": {"tarjeta": {"pct": 4.5, "fijo": 0}}, "impuesto_pct": 15}}).json()
    assert r["ok"] and r["tarifas"]["culqi"]["medios"]["yape"] == {"pct": 2.5, "fijo": 0.0} and r["tarifas"]["payphone"]["configurada"]
    assert stores.config["tarifa_culqi_yape_pct"] == "2.5" and stores.config["tarifa_payphone_tarjeta_pct"] == "4.5"
    # Yape a 2.5 % + IGV sobre S/ 100: 2.95 → margen 5 − 2.95.
    s = cli.get("/pagos/tarifas-pasarela?monto=100&medio=yape", headers=H).json()["simulacion"]
    assert s["pasarela_soles"] == 2.95 and s["comision_soles"] == 5.0 and s["margen_soles"] == 2.05
    # Ecuador: $ 10 con PayPhone 4.5 % + IVA 15 % = 0.52; comisión mínimo $ 0.50 → margen negativo (la torre lo pinta en rojo).
    s = cli.get("/pagos/tarifas-pasarela?monto=10&moneda=USD", headers=H).json()["simulacion"]
    assert s["simbolo"] == "$" and s["pasarela"] == "payphone" and s["pasarela_soles"] == 0.52 and s["comision_soles"] == 0.5 and s["margen_soles"] == -0.02
    assert cli.post("/pagos/tarifas-pasarela", headers=H, json={"culqi": {"medios": {"tarjeta": {"pct": 45, "fijo": 0}}}}).status_code == 400
    assert cli.post("/pagos/tarifas-pasarela", headers=H, json={}).status_code == 400
    # Liquidaciones pendientes: totales de pasarela y margen.
    stores.registrar_pago(tipo="liquidacion_online", monto_centimos=10000, moneda="PEN", estado="aprobado",
                          dueno_id="dueno@x.com", culqi_charge_id="res_tp_2", concepto="Club · Cancha 1 · Ana · hoy 20:00", medio="yape")
    j = cli.get("/pagos/liquidaciones/pendientes", headers=H).json()
    fila = next(x for x in j["pendientes"] if x["reserva_id"] == "res_tp_2")
    assert fila["pasarela_soles"] == 2.95 and fila["margen_soles"] == 2.05 and "total_pasarela_soles" in j and "total_margen_soles" in j and "tarifas" in j
    # La torre tiene el pane y las funciones.
    html = cli.get("/admin").text
    for t in ("Tarifas de pasarela", "id=\"tarifasPanel\"", "cargarTarifas", "guardarTarifas", "simularTarifa", "Margen Pichangol"):
        assert t in html, t
    for k in list(stores.config):
        if k.startswith("tarifa_"):
            del stores.config[k]
