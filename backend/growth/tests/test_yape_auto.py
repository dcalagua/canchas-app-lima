"""FASE 2 del Plan Academia (10-oct-2026): el celular de la academia lee la
notificación de Yape y Pichangol confirma SOLO el pago reportado cuyo código
de seguridad y monto coinciden (`yape_auto.py`)."""
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

import academia_plan as ap
import yape_auto
from db.store import stores
from tests.test_academia_plan import ALUMNO, DUENO, entorno  # noqa: F401 — fixture compartida


def _txt(monto="300", cod="427", nombre="Juan Pérez"):
    return f"¡Yape! {nombre} te envió un pago por S/ {monto}. El cód. de seguridad es: {cod}"


@pytest.fixture
def ya(entorno, monkeypatch):  # noqa: F811
    stores.yape_dispositivos.clear()
    stores.yape_notificaciones.clear()
    for k in yape_auto.DEFAULTS:
        stores.config[k] = yape_auto.DEFAULTS[k]
    monkeypatch.setattr(yape_auto, "_SINCRONO", True)
    return entorno


def _cuota(fm, cid):
    return next(c for c in fm.filas["al_1"]["cuotas"] if c["id"] == cid)


def test_lee_el_texto_de_la_notificacion_con_expresiones_editables():
    assert yape_auto.leer("Yape", _txt("1,250.50", "083")) == {"monto": 1250.5, "codigo": "083", "nombre": "Juan Pérez"}
    assert yape_auto.leer("", "Recibiste S/ 20.00 de Carlos")["codigo"] is None
    # Si Yape cambia su texto, la torre ajusta la expresión sin publicar un APK.
    yape_auto.set_config({"regex_codigo": r"clave\s+(\d{3})"})
    try:
        assert yape_auto.leer("", "Recibiste S/ 20.00 · clave 555")["codigo"] == "555"
        with pytest.raises(ValueError):
            yape_auto.set_config({"regex_codigo": "sin grupo"})
        with pytest.raises(ValueError):
            yape_auto.set_config({"paquetes": "no es paquete"})
    finally:
        stores.config["yape_regex_codigo"] = yape_auto.DEFAULTS["yape_regex_codigo"]


def test_notificacion_despues_del_reporte_confirma_sola(ya):
    fm, hoy = ya["fm"], ya["hoy"]
    yape_auto.vincular(DUENO)
    assert ap.reportar_pago("al_1", ALUMNO, ["cu_1"], "427", "", ahora=hoy)["ok"]
    assert not _cuota(fm, "cu_1").get("pagada")
    # Otro monto o código: no confirma.
    r = yape_auto.registrar(DUENO, "com.bcp.innovacxion.yapeapp", "Yape", _txt("299", "427"), ahora=hoy + timedelta(minutes=5))
    assert r["confirmados"] == []
    r = yape_auto.registrar(DUENO, "com.bcp.innovacxion.yapeapp", "Yape", _txt("300", "428"), ahora=hoy + timedelta(minutes=6))
    assert r["confirmados"] == []
    # Paquete ajeno se ignora.
    assert yape_auto.registrar(DUENO, "com.whatsapp", "x", _txt(), ahora=hoy)["ignorada"] == "paquete"
    r = yape_auto.registrar(DUENO, "com.bcp.innovacxion.yapeapp", "Yape", _txt("300", "427"), ahora=hoy + timedelta(minutes=7))
    assert len(r["confirmados"]) == 1
    c = _cuota(fm, "cu_1")
    assert c["pagada"] and c["medioPago"] == "yape_directo" and c["reporte"]["auto"] == "yape_notificacion"
    assert any(p[0] == DUENO and "solo" in p[1] for p in ya["pushes"])
    assert any(p[0] == ALUMNO and "confirmado" in p[1].lower() for p in ya["pushes"])
    # Android re-publica la misma notificación: no se duplica ni se reusa.
    r = yape_auto.registrar(DUENO, "com.bcp.innovacxion.yapeapp", "Yape", _txt("300", "427"), ahora=hoy + timedelta(minutes=8))
    assert r.get("duplicada")
    assert sum(1 for n in stores.yape_notificaciones if n.get("usada")) == 1


def test_reporte_despues_de_la_notificacion_confirma_al_reportar(ya):
    fm, hoy = ya["fm"], ya["hoy"]
    yape_auto.vincular(DUENO)
    yape_auto.registrar(DUENO, "com.bcp.innovacxion.yapeapp", "Yape", _txt("600", "915"), ahora=hoy)
    # El alumno reporta las DOS cuotas juntas (S/ 600) con el mismo código.
    assert ap.reportar_pago("al_1", ALUMNO, ["cu_1", "cu_2"], "915", "", ahora=hoy + timedelta(minutes=3))["ok"]
    assert _cuota(fm, "cu_1")["pagada"] and _cuota(fm, "cu_2")["pagada"]


def test_fuera_de_ventana_o_ambiguo_queda_para_la_academia(ya):
    fm, hoy = ya["fm"], ya["hoy"]
    yape_auto.vincular(DUENO)
    yape_auto.registrar(DUENO, "com.bcp.innovacxion.yapeapp", "Yape", _txt("300", "111"), ahora=hoy - timedelta(hours=60))
    assert ap.reportar_pago("al_1", ALUMNO, ["cu_1"], "111", "", ahora=hoy)["ok"]
    assert not _cuota(fm, "cu_1").get("pagada")  # 60 h > ventana de 48 h
    # Dos alumnos reportan el mismo monto con el mismo código: una notificación
    # no sabe de quién es → ambigua, no se confirma ninguno.
    fm.filas["al_2"] = {"id": "al_2", "academiaId": "ac_1", "email": "otra@correo.pe", "nombre": "Pepita",
                        "cuotas": [{"id": "cu_9", "concepto": "Octubre", "monto": 300.0,
                                    "vencimiento": "2026-10-13T10:00:00", "pagada": False}]}
    assert ap.reportar_pago("al_2", "otra@correo.pe", ["cu_9"], "111", "", ahora=hoy)["ok"]
    yape_auto.registrar(DUENO, "com.bcp.innovacxion.yapeapp", "Yape", _txt("300", "111", "Ana"), ahora=hoy)
    assert not _cuota(fm, "cu_1").get("pagada")
    assert not fm.filas["al_2"]["cuotas"][0].get("pagada")
    assert any(n.get("nota") == "ambigua" for n in stores.yape_notificaciones)
    # La academia sigue pudiendo confirmar a mano.
    assert ap.resolver_pago("ac_1", "al_1", ["cu_1"], DUENO, True, ahora=hoy)["ok"]


def test_sin_plan_vigente_no_confirma_solo(ya, monkeypatch):
    fm, hoy = ya["fm"], ya["hoy"]
    yape_auto.vincular(DUENO)
    monkeypatch.setattr(ap, "beneficios", lambda a: False)
    assert ap.reportar_pago("al_1", ALUMNO, ["cu_1"], "427", "", ahora=hoy)["ok"]
    yape_auto.registrar(DUENO, "com.bcp.innovacxion.yapeapp", "Yape", _txt(), ahora=hoy)
    assert not _cuota(fm, "cu_1").get("pagada")


def test_endpoints_token_de_dispositivo_y_torre(ya, monkeypatch):
    import config
    monkeypatch.setattr(config, "ADMIN_PANEL_TOKEN", "tk")
    from main import app
    cli = TestClient(app)
    r = cli.post("/academias/yape/vincular", json={"email": DUENO, "modelo": "Moto G"})
    assert r.status_code == 200 and r.json()["ok"]
    token = r.json()["token"]
    assert "com.bcp.innovacxion.yapeapp" in r.json()["paquetes"]
    assert stores.yape_dispositivos[DUENO]["token_sha"] != token  # solo se guarda el hash
    cuerpo = {"email": DUENO, "paquete": "com.bcp.innovacxion.yapeapp", "titulo": "Yape", "texto": _txt()}
    assert cli.post("/academias/yape/notificacion", json=cuerpo).status_code == 401
    assert cli.post("/academias/yape/notificacion", json=cuerpo, headers={"X-Yape-Token": "malo"}).status_code == 401
    r = cli.post("/academias/yape/notificacion", json=cuerpo, headers={"X-Yape-Token": token})
    assert r.status_code == 200 and r.json()["leido"]["codigo"] == "427"
    est = cli.get("/academias/yape/estado", params={"email": DUENO}).json()
    assert est["vinculado"] and est["recibidas"] == 1
    h = {"X-Admin-Token": "tk"}
    t = cli.get("/admin/api/yape-auto", headers=h).json()
    assert t["kpis"]["recibidas"] == 1 and t["notificaciones"][0]["codigo"] == "427"
    assert cli.post("/admin/api/yape-auto/probar", headers=h, json={"texto": _txt("12.50", "007")}).json()["monto"] == 12.5
    assert cli.post("/admin/api/yape-auto/config", headers=h, json={"regex_monto": "("}).status_code == 400
    assert cli.post("/admin/api/yape-auto/config", headers=h, json={"activo": False}).json()["activo"] is False
    r = cli.post("/academias/yape/notificacion", json=cuerpo, headers={"X-Yape-Token": token})
    assert r.json().get("ignorada") == "apagado"
    stores.config["yape_auto_activo"] = "1"
    cli.post("/academias/yape/desvincular", json={"email": DUENO})
    assert cli.post("/academias/yape/notificacion", json=cuerpo, headers={"X-Yape-Token": token}).status_code == 401


def test_snapshot_conserva_dispositivos_y_notificaciones(ya):
    yape_auto.vincular(DUENO)
    yape_auto.registrar(DUENO, "com.bcp.innovacxion.yapeapp", "Yape", _txt(), ahora=ya["hoy"])
    estado = stores.to_state()
    assert estado["yape_dispositivos"][DUENO]["token_sha"]
    assert estado["yape_notificaciones"][0]["codigo"] == "427"
