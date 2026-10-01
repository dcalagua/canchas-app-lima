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
    # En un snapshot REAL `stores.config` nace de CONFIG_DEFAULT (store.py) y pisa a
    # tarifas_pasarela.DEFAULTS: ambos deben decir lo mismo o la observada no aplica.
    from db.store import CONFIG_DEFAULT
    for k, v in tp.DEFAULTS.items():
        assert CONFIG_DEFAULT.get(k) == v, f"CONFIG_DEFAULT[{k}]={CONFIG_DEFAULT.get(k)!r} ≠ DEFAULTS {v!r}"
    for k in list(stores.config):
        if k.startswith("tarifa_"):
            del stores.config[k]
    # Tarifa OBSERVADA en el primer cobro live (panel de Culqi): 6.05 % + S/ 0.30 + IGV 18 % → sobre S/ 15 ≈ S/ 1.42.
    assert tp.costo_centimos(1500, "PEN", "tarjeta", "liquidacion_online") == 142
    com = comision_centimos(15.0, "PEN")
    assert com == 200  # 5 % = 0.75 < mínimo S/ 2
    d = tp.desglose(1500, com, "PEN", "tarjeta", "liquidacion_online")
    assert d["neto_centimos"] == 1300 and d["margen_centimos"] == 58 and d["pasarela"] == "culqi"
    # Pagado con SALDO (bodega, torneo): la pasarela ya se pagó al recargar → 0.
    assert tp.costo_centimos(1500, "PEN", None, "venta_bodega") == 0
    assert tp.costo_centimos(1500, "PEN", None, "inscripcion_torneo_ingreso") == 0
    # Otras pasarelas sin configurar → 0 (no se inventa un costo).
    assert tp.costo_centimos(1000, "USD", "tarjeta", "liquidacion_online") == 0
    assert tp.pasarela_de("BOB") == "libelula" and tp.pasarela_de("USD") == "nuvei"
    # La fila de la torre lleva pasarela y margen.
    p = stores.registrar_pago(tipo="liquidacion_online", monto_centimos=1500, moneda="PEN", estado="aprobado",
                              dueno_id="dueno@x.com", culqi_charge_id="res_tp_1", concepto="Club · Cancha 1 · Ana · hoy 19:00", medio="yape")
    x = _liquidacion_dict(p)
    assert x["bruto_soles"] == 15 and x["comision_soles"] == 2 and x["neto_soles"] == 13
    # Esta fila fue con YAPE: su tarifa de referencia sigue en 3.44 % + 0.30 (aún sin observación real).
    assert x["pasarela_soles"] == 0.96 and x["margen_soles"] == 1.04 and x["medio"] == "yape" and x["pasarela_fuente"] == "estimado"


def test_torre_configura_tarifas_y_simula(monkeypatch):
    cli = _cli(monkeypatch)
    assert cli.get("/pagos/tarifas-pasarela").status_code in (401, 403, 503)
    j = cli.get("/pagos/tarifas-pasarela?monto=15&moneda=PEN&medio=tarjeta", headers=H).json()
    assert j["tarifas"]["culqi"]["medios"]["tarjeta"] == {"pct": 6.05, "fijo": 0.3} and j["tarifas"]["culqi"]["configurada"] and "observado" in j
    assert j["tarifas"]["payphone"]["configurada"] is False
    s = j["simulacion"]
    assert s == {"moneda": "PEN", "simbolo": "S/", "medio": "tarjeta", "pasarela": "culqi", "bruto_soles": 15.0, "pasarela_soles": 1.42,
                 "comision_soles": 2.0, "margen_soles": 0.58, "neto_soles": 13.0, "comision_pct": config.COMISION_PORC, "comision_min": 2.0}
    # Guardar: Yape más barato y PayPhone configurado; validación de rangos.
    r = cli.post("/pagos/tarifas-pasarela", headers=H, json={"culqi": {"medios": {"yape": {"pct": 2.5, "fijo": 0}}, "impuesto_pct": 18},
                                                             "nuvei": {"medios": {"tarjeta": {"pct": 4.5, "fijo": 0}}, "impuesto_pct": 15}}).json()
    assert r["ok"] and r["tarifas"]["culqi"]["medios"]["yape"] == {"pct": 2.5, "fijo": 0.0} and r["tarifas"]["nuvei"]["configurada"]
    assert stores.config["tarifa_culqi_yape_pct"] == "2.5" and stores.config["tarifa_nuvei_tarjeta_pct"] == "4.5"
    # Yape a 2.5 % + IGV sobre S/ 100: 2.95 → margen 5 − 2.95.
    s = cli.get("/pagos/tarifas-pasarela?monto=100&medio=yape", headers=H).json()["simulacion"]
    assert s["pasarela_soles"] == 2.95 and s["comision_soles"] == 5.0 and s["margen_soles"] == 2.05
    # Ecuador: $ 10 con PayPhone 4.5 % + IVA 15 % = 0.52; comisión mínimo $ 0.50 → margen negativo (la torre lo pinta en rojo).
    s = cli.get("/pagos/tarifas-pasarela?monto=10&moneda=USD", headers=H).json()["simulacion"]
    assert s["simbolo"] == "$" and s["pasarela"] == "nuvei" and s["pasarela_soles"] == 0.52 and s["comision_soles"] == 0.5 and s["margen_soles"] == -0.02
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


def test_sincera_la_comision_real_de_culqi_y_la_liga_a_la_liquidacion(monkeypatch):
    """Pedido del director (27-sep-2026, con el panel de Culqi del cobro de
    S/ 15 a la vista: emisor 0.38 + Culqi 0.83 + IGV): "sincerar los montos
    y comisiones que ganará PCG". La torre lee de Culqi la comisión REAL de
    cada cargo (`net_amount`/`total_fee`), la liga a su liquidación (por
    `charge_id` explícito o infiriendo el cargo del mismo monto y hora) y la
    muestra como "real" en vez de "estimado"."""
    import pagos.router as pr
    from pagos import culqi
    for k in list(stores.config):
        if k.startswith("tarifa_"):
            del stores.config[k]
    tp._ultimo_intento.clear()
    cli = _cli(monkeypatch)
    cargos = {"chr_real_1": {"id": "chr_real_1", "amount": 1500, "net_amount": 1357, "total_fee": 121, "fee_details": {"variable_fee": {"total": 91}, "fixed_fee": {"total": 30}}},
              "chr_pend_1": {"id": "chr_pend_1", "amount": 8000, "net_amount": 0, "total_fee": 0},
              "chr_solo_fee": {"id": "chr_solo_fee", "amount": 5000, "total_fee": 350}}
    monkeypatch.setattr(culqi, "disponible", lambda: True)
    monkeypatch.setattr(culqi, "_request", lambda metodo, path, body=None: {"ok": True, "data": cargos[path.rsplit("/", 1)[1]]})
    # comision_real: prefiere monto − net_amount (incluye IGV); si solo hay total_fee, ese; nada → pendiente.
    assert culqi.comision_real("chr_real_1") == {"ok": True, "conocida": True, "monto_centimos": 1500, "pasarela_centimos": 143, "neto_centimos": 1357,
                                                 "detalle": {"variable_fee": {"total": 91}, "fixed_fee": {"total": 30}}}
    assert culqi.comision_real("chr_pend_1")["conocida"] is False
    assert culqi.comision_real("chr_solo_fee")["pasarela_centimos"] == 350
    # El APK viejo cobra con /cobrar (fila `reserva` con el chr_) y registra la liquidación SIN charge_id.
    c1 = stores.registrar_pago(tipo="reserva", monto_centimos=1500, moneda="PEN", estado="aprobado", email="ana@x.com",
                               culqi_charge_id="chr_real_1", concepto="Reserva · Club", medio="tarjeta")
    liq = stores.registrar_pago(tipo="liquidacion_online", monto_centimos=1500, moneda="PEN", estado="aprobado", dueno_id="dueno@x.com",
                                culqi_charge_id="res_sinc_1", concepto="Club · Cancha 1 · Ana · sáb 19:00", medio="tarjeta")
    assert tp.cargo_de(liq) is c1 and liq.cargo_id == "chr_real_1"  # inferido y guardado
    assert tp.costo_para(liq) == (142, "estimado")  # aún no sincerado: tarifa
    # Sincerar: lee Culqi, guarda en la fila del cargo y la liquidación pasa a "real".
    r = tp.sincerar(max_consultas=10, reintento_horas=0)
    assert r["actualizados"] >= 1 and c1.pasarela_centimos == 143 and c1.pasarela_en is not None
    assert tp.costo_para(liq) == (143, "real")
    x = pr._liquidacion_dict(liq)
    assert x["pasarela_soles"] == 1.43 and x["pasarela_fuente"] == "real" and x["margen_soles"] == 0.57 and x["neto_soles"] == 13
    # Pendiente en Culqi → se reintenta después, sin inventar.
    c2 = stores.registrar_pago(tipo="cobro_web", monto_centimos=8000, moneda="PEN", estado="aprobado", email="luis@x.com",
                               culqi_charge_id="chr_pend_1", concepto="web:web_1", medio="yape")
    r = tp.sincerar(max_consultas=10, reintento_horas=0)
    assert r["pendientes"] >= 1 and c2.pasarela_centimos is None
    # Enlace EXPLÍCITO desde la web/APK nuevo: charge_id en la liquidación.
    stores.saldos.pop("dueno2@x.com", None)
    out = pr.post_liquidacion_online(pr.LiquidacionOnlineReq(dueno_id="dueno2@x.com", monto_soles=80.0, reserva_id="res_sinc_2",
                                                              concepto="Club · Cancha 2 · Luis", medio="yape", moneda="PEN", charge_id="chr_pend_1"))
    liq2 = next(p for p in stores.pagos if p.culqi_charge_id == "res_sinc_2")
    assert liq2.cargo_id == "chr_pend_1" and tp.costo_para(liq2)[1] == "estimado"
    cargos["chr_pend_1"]["net_amount"] = 7620  # Culqi ya calculó: 3.80
    tp.sincerar(max_consultas=10, reintento_horas=0)
    assert tp.costo_para(liq2) == (380, "real")
    # Observado por medio + % sugerido para la tarifa (dado fijo 0.30 e IGV 18 %).
    ob = tp.observado()["medios"]
    assert ob["tarjeta"]["n"] == 1 and ob["tarjeta"]["pasarela_soles"] == 1.43 and ob["tarjeta"]["efectivo_pct"] == 9.53 and 6.0 < ob["tarjeta"]["pct_sugerido"] < 6.2
    assert ob["yape"]["n"] == 1 and ob["yape"]["pasarela_soles"] == 3.8
    # Torre: botón "Sincerar con Culqi" y la fila de liquidaciones dice que es real.
    j = cli.post("/pagos/tarifas-pasarela/sincerar", headers=H).json()
    assert j["ok"] and "resultado" in j and j["observado"]["medios"]["tarjeta"]["n"] == 1
    fila = next(x for x in cli.get("/pagos/liquidaciones/pendientes", headers=H).json()["pendientes"] if x["reserva_id"] == "res_sinc_1")
    assert fila["pasarela_fuente"] == "real" and fila["pasarela_soles"] == 1.43
    html = cli.get("/admin").text
    for t in ("sincerarTarifas", "Sincerar con Culqi", "usarObservada", "Lo que Culqi cobró de verdad"):
        assert t in html, t
    # Persistencia: los campos nuevos viajan en el snapshot.
    st = stores.to_state()
    d = next(p for p in st["pagos"] if p["culqi_charge_id"] == "chr_real_1")
    assert d["pasarela_centimos"] == 143 and d["pasarela_en"]
    for k in list(stores.config):
        if k.startswith("tarifa_"):
            del stores.config[k]
