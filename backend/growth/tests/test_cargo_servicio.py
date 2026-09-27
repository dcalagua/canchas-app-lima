"""CARGO POR SERVICIO al cliente (fase 1, 27-sep-2026; diseño en
`docs/diseno-cargo-por-servicio.md`): regla 5 % hasta S/ 500 + 2 % del
excedente con mínimo, red de seguridad con la tarifa de la pasarela, desglose
por línea y deporte, cotización para app/web, contabilidad con el cargo,
liquidaciones con margen real, pane de la torre. Todo apagado por flag."""
from fastapi.testclient import TestClient

import config
from db.store import CONFIG_DEFAULT, stores
from main import app
from pagos import cargo_servicio as cs
from pagos.router import _liquidacion_dict

H = {"X-Admin-Token": "t"}


def _cli(monkeypatch):
    monkeypatch.setattr(config, "ADMIN_PANEL_TOKEN", "t")
    monkeypatch.setattr(config, "APP_API_KEY", "")
    for k in list(stores.config):
        if k.startswith(("cargo_", "tarifa_")):
            del stores.config[k]
    stores.cargo_servicio_textos = {}
    return TestClient(app)


def test_regla_del_cargo_tramos_minimo_y_defaults_consistentes(monkeypatch):
    _cli(monkeypatch)
    # CONFIG_DEFAULT (snapshots reales) debe decir lo mismo que el módulo.
    for k, v in cs.CLAVES_DEFAULT.items():
        assert CONFIG_DEFAULT.get(k) == v, k
    # Casos del Excel `modelo_academias_cargo_tramos.xlsx`.
    assert cs.cargo_centimos(1500, "PEN") == 200      # S/ 15 → mínimo S/ 2
    assert cs.cargo_centimos(6000, "PEN") == 300      # S/ 60 → 5 %
    assert cs.cargo_centimos(30000, "PEN") == 1500    # S/ 300 → 15
    assert cs.cargo_centimos(50000, "PEN") == 2500    # S/ 500 → 25 (fin del tramo)
    assert cs.cargo_centimos(85000, "PEN") == 3200    # 25 + 2 % de 350
    assert cs.cargo_centimos(115000, "PEN") == 3800   # familia de 4 → 38
    assert cs.cargo_centimos(150000, "PEN") == 4500
    assert cs.cargo_centimos(0, "PEN") == 0
    # Redondeo a 0.10 hacia arriba: S/ 33.33 × 5 % = 1.6665 → mínimo 2; S/ 61 → 3.05 → 3.10.
    assert cs.cargo_centimos(6100, "PEN") == 310
    # Otras monedas: $ 10 → mínimo $ 0.50; $ 200 → 5 % de 140 + 2 % de 60 = 8.20; Bs 50 → mínimo Bs 3.
    assert cs.cargo_centimos(1000, "USD") == 50 and cs.cargo_centimos(20000, "$") == 820 and cs.cargo_centimos(5000, "Bs") == 300
    assert "5 % sobre los primeros S/ 500" in cs.regla_texto("PEN") and "$ 140" in cs.regla_texto("USD")


def test_red_de_seguridad_sube_el_cargo_si_la_pasarela_se_come_el_margen(monkeypatch):
    _cli(monkeypatch)
    # S/ 1500 por tarjeta (6.05 % + 0.30 + IGV): comisión 75 + cargo 45 = 120 ≥ 110.65 + 2 → no cambia.
    assert cs.red_de_seguridad(150000, 4500, 7500, "PEN", "tarjeta", "matricula_online") == 4500
    # Con una pasarela carísima (20 %) el cargo sube al múltiplo de 0.50 que cubre costo + margen mínimo.
    stores.config["tarifa_culqi_tarjeta_pct"] = "20"
    c = cs.red_de_seguridad(30000, 1500, 1500, "PEN", "tarjeta", "matricula_online")
    from pagos import tarifas_pasarela as tp
    assert c > 1500 and c % 50 == 0 and 1500 + c >= tp.costo_centimos(30000 + c, "PEN", "tarjeta", "matricula_online") + 200
    # Pasarela sin configurar (PayPhone en 0) → no actúa.
    assert cs.red_de_seguridad(10000, 500, 500, "USD", "tarjeta", "liquidacion_online") == 500
    del stores.config["tarifa_culqi_tarjeta_pct"]


def test_cotizar_desglose_por_deporte_ahorro_familiar_y_flags(monkeypatch):
    cli = _cli(monkeypatch)
    # Apagado por defecto: cotización sin cargo y el público lo dice.
    pub = cli.get("/config/cargo-servicio").json()
    assert pub["activo"] == {"reservas": False, "academias": False, "marketplace": False, "torneos": False}
    assert pub["monedas"]["PEN"]["tramo"] == 500 and "reservas" in pub["textos"] and "comision" in pub
    r = cli.post("/pagos/cotizar", json={"linea": "reservas", "moneda": "S/", "base_centimos": 1500, "medio": "yape"}).json()
    assert r["ok"] and r["activo"] is False and r["cargo_centimos"] == 0 and r["total_centimos"] == 1500
    # Encendido en reservas: S/ 15 → cargo 2, total 17, desglose de fútbol con el texto del deporte.
    stores.config["cargo_activo_reservas"] = "1"
    r = cli.post("/pagos/cotizar", json={"linea": "reservas", "moneda": "PEN", "base_centimos": 1500, "medio": "tarjeta", "deporte": "futbol"}).json()
    assert r["activo"] and r["cargo_centimos"] == 200 and r["total_centimos"] == 1700 and r["titulo"] == "Cargo por servicio Pichangol"
    assert [d["nombre"] for d in r["desglose"]] == ["Pago protegido", "Reserva garantizada", "Tu equipo y tu partido"]
    assert sum(d["monto_centimos"] for d in r["desglose"]) == 200 and "Yape o tarjeta" in r["desglose"][0]["detalle"]
    # Tenis cambia el tercer componente; Ecuador no nombra Yape.
    r = cli.post("/pagos/cotizar", json={"linea": "reservas", "moneda": "USD", "base_centimos": 1000, "deporte": "tenis"}).json()
    assert r["desglose"][2]["nombre"] == "Comunidad y ranking" and "Yape" not in r["desglose"][0]["detalle"] and r["cargo_centimos"] == 50
    # Academias apagadas aún → sin cargo aunque reservas esté encendido.
    r = cli.post("/pagos/cotizar", json={"linea": "academias", "moneda": "PEN", "base_centimos": 30000}).json()
    assert r["activo"] is False and r["cargo_centimos"] == 0
    # Familia de 4 (300+300+300+250) con academias encendidas: cargo 38, ahorro 19.50 vs por separado.
    stores.config["cargo_activo_academias"] = "1"
    r = cli.post("/pagos/cotizar", json={"linea": "academias", "moneda": "PEN", "base_centimos": 115000, "medio": "tarjeta",
                                        "deporte": "natacion", "partes": [30000, 30000, 30000, 25000]}).json()
    assert r["cargo_centimos"] == 3800 and r["total_centimos"] == 118800 and r["ahorro_centimos"] == 1950
    assert r["desglose"][2]["nombre"] == "Portal del alumno y marcas" and r["ajuste_seguridad_centimos"] == 0
    for k in ("cargo_activo_reservas", "cargo_activo_academias"):
        del stores.config[k]


def test_contabilidad_guarda_el_cargo_y_liquidaciones_muestran_margen_real(monkeypatch):
    cli = _cli(monkeypatch)
    stores.pagos = [p for p in stores.pagos if p.culqi_charge_id not in ("res_cs_1", "mat_cs_1")]
    # Reserva de S/ 15 por tarjeta con cargo 2 (lo manda el APK/web tras cotizar).
    r = cli.post("/pagos/liquidacion-online", json={
        "dueno_id": "dueno_cs@x.com", "monto_soles": 15.0, "reserva_id": "res_cs_1", "medio": "tarjeta", "moneda": "PEN",
        "charge_id": "chr_cs_1", "cargo_servicio_centimos": 200,
        "cargo_desglose": [{"clave": "pago_protegido", "nombre": "Pago protegido", "pct": 2.0, "detalle": "x", "monto_centimos": 80},
                           {"clave": "reserva_garantizada", "nombre": "Reserva garantizada", "pct": 1.5, "detalle": "x", "monto_centimos": 60},
                           {"clave": "beneficios", "nombre": "Promociones y beneficios", "pct": 1.5, "detalle": "x", "monto_centimos": 60}]}).json()
    assert r["ok"] and r["comision_centimos"] == 200 and r["neto_centimos"] == 1300  # el dueño recibe lo mismo que hoy
    p = stores.pago_por_charge("res_cs_1")
    assert p.cargo_servicio_centimos == 200 and len(p.cargo_desglose) == 3 and p.cargo_ajuste_centimos == 0
    d = _liquidacion_dict(p)
    # Culqi cobró sobre 17 (precio + cargo): (17 × 6.05 % + 0.30) × 1.18 = 1.57; margen = 2 + 2 − 1.57 = 2.43.
    assert d["cargo_servicio_soles"] == 2.0 and d["ingreso_pcg_soles"] == 4.0 and d["pasarela_soles"] == 1.57 and d["margen_soles"] == 2.43
    # Matrícula de S/ 300 con cargo 15: margen 15 + 15 − 22.84 = 7.16 (antes −6.77).
    r = cli.post("/pagos/matricula", json={"academia_id": "aca_cs", "monto_soles": 300.0, "matricula_id": "mat_cs_1", "pais": "pe",
                                          "charge_id": "chr_cs_2", "cargo_servicio_centimos": 1500}).json()
    assert r["ok"] and r["neto_centimos"] == 28500
    m = stores.pago_por_charge("mat_cs_1")
    m.medio = "tarjeta"
    d = _liquidacion_dict(m)
    assert d["cargo_servicio_soles"] == 15.0 and d["pasarela_soles"] == 22.84 and d["margen_soles"] == 7.16
    # Sin cargo (APK viejo): todo como antes y el KPI lo cuenta cuando la línea está encendida.
    cli.post("/pagos/liquidacion-online", json={"dueno_id": "dueno_cs@x.com", "monto_soles": 15.0, "reserva_id": "res_cs_2", "medio": "yape"})
    v = stores.pago_por_charge("res_cs_2")
    assert v.cargo_servicio_centimos == 0 and v.cargo_desglose is None and _liquidacion_dict(v)["margen_soles"] == 1.04
    stores.config["cargo_activo_reservas"] = "1"
    kpi = cs.sin_cargo_recientes()
    assert kpi["reservas"] >= 1 and kpi["con_cargo"] >= 2
    del stores.config["cargo_activo_reservas"]
    # Snapshot: los campos viajan y vuelven.
    st = stores.to_state()
    fila = next(x for x in st["pagos"] if x["culqi_charge_id"] == "res_cs_1")
    assert fila["cargo_servicio_centimos"] == 200 and len(fila["cargo_desglose"]) == 3
    from db.store import _pago_from
    assert _pago_from(fila).cargo_desglose[0]["nombre"] == "Pago protegido"
    # Liquidaciones pendientes: totales con el cargo.
    j = cli.get("/pagos/liquidaciones/pendientes", headers=H).json()
    assert "total_cargo_soles" in j and j["total_cargo_soles"] >= 2.0
    stores.pagos = [p for p in stores.pagos if p.culqi_charge_id not in ("res_cs_1", "res_cs_2", "mat_cs_1")]


def test_torre_configura_regla_flags_y_textos_y_simula(monkeypatch):
    cli = _cli(monkeypatch)
    assert cli.get("/pagos/cargo-servicio/config").status_code in (401, 403, 503)
    j = cli.get("/pagos/cargo-servicio/config?monto=850&moneda=PEN&medio=tarjeta&linea=academias", headers=H).json()
    s = j["simulacion"]
    assert s["cargo_soles"] == 32.0 and s["total_soles"] == 882.0 and s["recibe_soles"] == 807.5 and s["comision_soles"] == 42.5
    assert s["pasarela_soles"] == 63.32 and s["margen_soles"] == 11.18 and s["ingreso_pcg_soles"] == 74.5
    assert j["config"]["activo"]["academias"] is False and "sin_cargo" in j
    # Guardar: encender academias, cambiar el tramo de PEN y el texto de un componente + deporte.
    r = cli.post("/pagos/cargo-servicio/config", headers=H, json={
        "activo": {"academias": True}, "monedas": {"PEN": {"tramo": 400, "pct_exc": 1.5}},
        "textos": {"academias": {"componentes": [
            {"clave": "pago_protegido", "nombre": "Pago protegido", "pct": 2, "detalle": "Cobro seguro con {medios}."},
            {"clave": "gestion_matricula", "nombre": "Gestión de tu matrícula", "pct": 2, "detalle": "Cuotas y débito automático."},
            {"clave": "portal_alumno", "nombre": "Portal del alumno", "pct": 1, "detalle": "Clases y pagos en la app."}],
            "por_deporte": {"natacion": {"nombre": "Portal del alumno y marcas", "detalle": "Pruebas y tiempos."}}}}}).json()
    assert r["ok"] and r["config"]["activo"]["academias"] is True and r["config"]["monedas"]["PEN"]["tramo"] == 400
    assert stores.config["cargo_activo_academias"] == "1" and stores.config["cargo_PEN_pct_exc"] == "1.5"
    assert stores.cargo_servicio_textos["academias"]["componentes"][2]["nombre"] == "Portal del alumno"
    # S/ 850 ahora: 5 % de 400 + 1.5 % de 450 = 26.75 → 26.80 (redondeo a 0.10).
    assert cs.cargo_centimos(85000, "PEN") == 2680
    c = cli.post("/pagos/cotizar", json={"linea": "academias", "moneda": "PEN", "base_centimos": 30000, "deporte": "natacion"}).json()
    assert c["desglose"][2]["nombre"] == "Portal del alumno y marcas" and c["desglose"][2]["detalle"] == "Pruebas y tiempos."
    # Validaciones.
    assert cli.post("/pagos/cargo-servicio/config", headers=H, json={"monedas": {"PEN": {"pct": 45}}}).status_code == 400
    assert cli.post("/pagos/cargo-servicio/config", headers=H, json={}).status_code == 400
    assert cli.post("/pagos/cargo-servicio/config", headers=H, json={"textos": {"reservas": {"componentes": []}}}).status_code == 400
    # Snapshot conserva los textos; la torre tiene el pane.
    assert stores.to_state()["cargo_servicio_textos"]["version"] >= 2
    html = cli.get("/admin").text
    for t in ("Cargo por servicio", 'id="cargoPanel"', "cargarCargoServicio", "guardarCargoServicio", "simularCargo", "Cargo por servicio ${S(gCargo)}"):
        assert t in html, t
    for k in list(stores.config):
        if k.startswith("cargo_"):
            del stores.config[k]
    stores.cargo_servicio_textos = {}


def test_mes_a_mes_agrupado_por_familia(monkeypatch):
    """Fase 4: las mensualidades vencidas de la MISMA cuenta y tarjeta se cobran
    en UN solo cargo de Culqi con UNA cotización del cargo por servicio
    (partes por persona → menos por cabeza), el cargo se reparte en la fila de
    cada matrícula y, si Culqi rechaza, el grupo entero queda pendiente."""
    from datetime import datetime, timedelta, timezone
    import pagos.router as pr
    from pagos import culqi
    stores.config["cargo_activo_academias"] = "1"
    stores.suscripciones_alumno.clear()
    vencido = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    def sub(aid, email, card, monto, aca="ac_1", rest=None):
        stores.suscripciones_alumno[aid] = {"alumno_id": aid, "academia_id": aca, "email": email, "card_id": card,
                                            "monto_centimos": monto, "pais": "pe", "estado": "activa", "concepto": f"Plan {aid}",
                                            "proximo_cobro": vencido, "cobros_hechos": 0, "cobros_restantes": rest}
    sub("al_yo", "dennis@gmail.com", "crd_1", 30000, rest=2)
    sub("al_esposa", "dennis@gmail.com", "crd_1", 30000, aca="ac_2")
    sub("al_otro", "otra@gmail.com", "crd_9", 10000)
    cargos = []
    monkeypatch.setattr(culqi, "disponible", lambda: True)
    monkeypatch.setattr(culqi, "crear_cargo", lambda **kw: (cargos.append(kw) or {"ok": kw["token"] != "crd_9", "charge_id": f"chr_m{len(cargos)}", "error": "rechazada"}))
    try:
        r = pr.procesar_renovaciones_alumnos()
        assert r["cobradas"] == 2 and r["pendientes"] == 1
        # UN cargo para la familia: 600 + (5 % de 500 + 2 % de 100 = 27) = 627; el otro correo va aparte y falla.
        fam = next(k for k in cargos if k["token"] == "crd_1")
        assert fam["monto_centimos"] == 62700 and fam["metadata"]["alumnos"] == 2 and fam["metadata"]["cargo_servicio_centimos"] == 2700
        assert "pago familiar" in fam["descripcion"] and "cargo por servicio" in fam["descripcion"]
        filas = [p for p in stores.pagos if p.tipo == "matricula_online" and (p.cargo_id or "").startswith("chr_m")]
        assert len(filas) == 2 and sorted(p.dueno_id for p in filas) == ["ac_1", "ac_2"]
        assert sum(p.cargo_servicio_centimos for p in filas) == 2700 and {p.monto_centimos for p in filas} == {30000}
        assert filas[0].culqi_charge_id.startswith("chr_m") and "#" in filas[1].culqi_charge_id and filas[0].cargo_desglose
        assert all("pago familiar" in p.concepto and "cargo por servicio" in p.concepto for p in filas)
        assert stores.suscripciones_alumno["al_yo"]["cobros_restantes"] == 1 and stores.suscripciones_alumno["al_yo"]["estado"] == "activa"
        assert stores.suscripciones_alumno["al_esposa"]["cobros_hechos"] == 1
        assert stores.suscripciones_alumno["al_otro"]["estado"] == "pendiente_pago"
        # Rechazo de la tarjeta → el grupo entero queda pendiente, sin filas.
        monkeypatch.setattr(culqi, "crear_cargo", lambda **kw: {"ok": False, "error": "fondos"})
        for s in stores.suscripciones_alumno.values():
            s["proximo_cobro"] = vencido; s["estado"] = "activa"
        n = len(stores.pagos)
        r = pr.procesar_renovaciones_alumnos()
        assert r["cobradas"] == 0 and r["pendientes"] == 3 and len(stores.pagos) == n
        assert all(s["estado"] == "pendiente_pago" for s in stores.suscripciones_alumno.values())
        # Apagado: un solo alumno se cobra como siempre (sin cargo, mismo monto).
        stores.config["cargo_activo_academias"] = "0"
        monkeypatch.setattr(culqi, "crear_cargo", lambda **kw: (cargos.append(kw) or {"ok": True, "charge_id": f"chr_s{len(cargos)}"}))
        stores.suscripciones_alumno.clear()
        sub("al_solo", "solo@gmail.com", "crd_5", 25000)
        pr.procesar_renovaciones_alumnos()
        assert cargos[-1]["monto_centimos"] == 25000 and stores.pagos[-1].cargo_servicio_centimos == 0
        assert stores.pagos[-1].monto_centimos == 25000 and "pago familiar" not in stores.pagos[-1].concepto
    finally:
        stores.config["cargo_activo_academias"] = "0"
        stores.suscripciones_alumno.clear()
