"""FOTOS PROPIAS OBLIGATORIAS AL RECLAMAR (decisión del director, 2-oct-2026:
"cuando se reclama una cancha, subir fotos propias debe ser una OBLIGACIÓN").

Los términos de Google no permiten guardar sus fotos: las del dueño son las
que quedan y prueban que el local existe. Mínimo configurable en la torre
(`reclamo_fotos_min`, default 2; 0 = apagado), validado en la web al
registrar/reclamar/agregar y, como candado REAL (los APK viejos no validan),
al aprobar/activar el reclamo."""

import os
import re
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config  # noqa: E402
from db.store import stores  # noqa: E402
from main import app  # noqa: E402
from propiedad import fotos_reclamo, reclamos  # noqa: E402
from web import datos  # noqa: E402
from test_web_reservas import _entrar_como, db  # noqa: E402,F401

SB = "https://sb.test/storage/v1/object/public/canchas"


@pytest.fixture(autouse=True)
def _base(monkeypatch):
    monkeypatch.setattr(config, "SUPABASE_URL", "https://sb.test")
    monkeypatch.setattr(config, "SUPABASE_ANON_KEY", "anon")
    monkeypatch.setattr(config, "GOOGLE_WEB_CLIENT_ID", "cid-web")
    monkeypatch.setattr(config, "ADMIN_PANEL_TOKEN", "adm")
    monkeypatch.setattr(reclamos, "_notificar_admin", lambda *a, **k: None)
    monkeypatch.setattr(reclamos, "_notificar_reclamante_aprobado", lambda *a, **k: None)
    monkeypatch.setattr(reclamos, "_bienvenida_al_activar", lambda *a, **k: None)
    stores.config.pop("reclamo_fotos_min", None)
    stores.reclamos.clear()
    yield
    stores.config.pop("reclamo_fotos_min", None)
    stores.reclamos.clear()


def test_que_cuenta_como_foto_propia():
    assert fotos_reclamo.minimo() == 2  # default
    assert fotos_reclamo.es_foto_propia(f"{SB}/u1700000000000/web_1.jpg?v=3", "u1700000000000")
    assert fotos_reclamo.es_foto_propia(f"{SB}/u1700000000000.jpg?v=1", "u1700000000000")  # portada del APK
    assert fotos_reclamo.es_foto_propia(f"{SB}/u1700000000000/app_1.jpg", "u1700000000000_tenis")  # hermana
    assert fotos_reclamo.es_foto_propia(f"{SB}/c_pend/a.jpg", "c_pend")
    for mala in ("https://lh3.googleusercontent.com/p/AF1Qip=w800",
                 "https://maps.googleapis.com/maps/api/place/photo?photo_reference=x",
                 f"{SB}/evu1700000000000/ev.jpg",            # foto de EVIDENCIA
                 f"{SB}/otra/a.jpg",                          # carpeta de otra cancha
                 "https://otro.supabase.co/storage/v1/object/public/canchas/u1700000000000/a.jpg",  # otro proyecto
                 "https://sb.test/storage/v1/object/public/productos/u1700000000000/a.jpg",         # otro bucket
                 f"{SB}/u1700000000000/../x/a.jpg", "", "ftp://sb.test/x"):
        assert not fotos_reclamo.es_foto_propia(mala, "u1700000000000"), mala
    assert fotos_reclamo.propias([f"{SB}/c1/a.jpg", f"{SB}/c1/a.jpg", "https://lh3.googleusercontent.com/x", f"{SB}/c1/b.jpg"], "c1") == \
        [f"{SB}/c1/a.jpg", f"{SB}/c1/b.jpg"]
    assert fotos_reclamo.set_minimo(9)["ok"] is False and fotos_reclamo.set_minimo(-1)["ok"] is False
    assert fotos_reclamo.set_minimo(3)["minimo"] == 3 and fotos_reclamo.minimo() == 3


def _registro(cli, monkeypatch, email="dueno.nuevo@gmail.com", **extra):
    _entrar_como(cli, monkeypatch, email, "Dueño Nuevo")
    html = cli.get("/anfitrion/nueva").text
    nid = re.search(r'"id": "(u\d+)"', html).group(1)
    body = {"id": nid, "nombre_local": "Complejo Luna", "direccion": "Av. Luna 1", "lat": -12.2, "lng": -77.01, "zona": "Surco",
            "deportes": ["futbol"], "modo": "unica", "superficie": "Grass sintético", "precio_hora": 70, "hora_apertura": "07:00",
            "hora_cierre": "23:00", "duracion_slot_min": 60, "whatsapp": "987654321", "relacion": "dueno", "fotos": [], **extra}
    return html, nid, body


def test_registro_web_exige_fotos_propias_y_la_aprobacion_tambien(db, monkeypatch):
    cli = TestClient(app, base_url="https://testserver")
    html, nid, body = _registro(cli, monkeypatch)
    # Formulario: obligatorio, contador y el porqué.
    assert "Obligatorio: al menos 2 fotos tuyas del local" in html and "id='fotosCont'" in html and '"minFotos": 2' in html
    assert "Las fotos de Google no se pueden guardar" in html and "actualizarEnvio" in html
    # Sin fotos → rechazado en el servidor, sección fotos.
    r = cli.post("/anfitrion/nueva", json=body)
    assert r.status_code == 400 and r.json()["campo"] == "fotos" and "llevas 0" in r.json()["error"]
    # URLs de Google / evidencia / carpeta ajena no cuentan.
    r = cli.post("/anfitrion/nueva", json={**body, "fotos": ["https://lh3.googleusercontent.com/p/x", f"{SB}/ev{nid}/e.jpg",
                                                             f"{SB}/u1/a.jpg", f"{SB}/{nid}/web_1.jpg"]})
    assert r.status_code == 400 and r.json()["campo"] == "fotos" and "llevas 1" in r.json()["error"]
    assert not any(c for c in db.canchas if c.startswith(nid))
    # Con 2 fotos propias → se registra y solo se guardan las propias.
    mias = [f"{SB}/{nid}/web_1.jpg", f"{SB}/{nid}/web_2.jpg"]
    r = cli.post("/anfitrion/nueva", json={**body, "fotos": mias + ["https://lh3.googleusercontent.com/p/x"]})
    assert r.status_code == 200 and r.json()["ok"], r.text
    assert db.canchas[nid]["fotos"] == mias and db.canchas[nid]["foto_url"] == mias[0]
    rec = next(x for x in stores.reclamos if x.cancha_id == nid)
    # La torre ve las fotos propias (y miniaturas) en la tarjeta del reclamo.
    lst = cli.get("/admin/api/reclamos", headers={"X-Admin-Token": "adm"}).json()
    d = next(x for x in lst if x["id"] == rec.id)
    assert d["fotos_propias"] == 2 and d["fotos_faltan"] == 0 and d["fotos_urls"] == mias and d["fotos_minimo"] == 2
    # Candado real (APK viejo / fotos quitadas después): si en la nube quedan menos del mínimo, NO se activa.
    db.canchas[nid]["fotos"] = [mias[0], "https://lh3.googleusercontent.com/p/x"]
    db.canchas[nid]["foto_url"] = mias[0]
    d = next(x for x in cli.get("/admin/api/reclamos", headers={"X-Admin-Token": "adm"}).json() if x["id"] == rec.id)
    assert d["fotos_propias"] == 1 and d["fotos_faltan"] == 1
    res = cli.post(f"/admin/api/reclamo/{rec.id}/decidir", headers={"X-Admin-Token": "adm"}, json={"aprobado": True}).json()
    assert res["ok"] is False and res["error"] == "faltan_fotos_propias" and res["faltan"] == 1 and "fotos propias" in res["mensaje"]
    assert rec.estado == "pendiente_triage" and db.canchas[nid]["verificada"] is False
    assert reclamos.activar_admin(rec.id)["error"] == "faltan_fotos_propias"
    assert reclamos.aprobar_por_codigo(rec.codigo)["error"] == "faltan_fotos_propias"
    # El dueño ve el aviso con acceso directo a subirlas (verificación y Mis canchas).
    ver = cli.get(f"/anfitrion/verificacion/{nid}").text
    assert "Sube 1 foto de tu local para que podamos aprobarlo" in ver and f"/anfitrion/cancha/{nid}/editar#sec-fotos" in ver
    mc = cli.get("/anfitrion/canchas").text
    assert "Sube 1 foto de tu local" in mc and "Subir fotos ›" in mc
    # Sube la que falta → la torre aprueba y activa.
    db.canchas[nid]["fotos"] = mias
    res = reclamos.aprobar_directo(rec.id, "admin")
    assert res["ok"] and res["estado"] == "activada" and db.canchas[nid]["verificada"] is True
    assert "para que podamos aprobarlo" not in cli.get("/anfitrion/canchas").text


def test_validacion_en_sitio_tampoco_activa_sin_fotos(db, monkeypatch):
    monkeypatch.setattr(config, "VALIDADOR_ACTIVA_AUTOMATICO", True)
    db.canchas["c_pend"]["dueno"] = "dueno.pend@gmail.com"
    db.canchas["c_pend"]["fotos"] = []
    r = reclamos.crear_reclamo("c_pend", "dueno.pend@gmail.com", "Club Raqueta", "51987654321", lat=-12.09, lng=-77.0)
    assert r["ok"]
    rec = next(x for x in stores.reclamos if x.cancha_id == "c_pend")
    rec.estado = "pendiente_validacion"
    res = reclamos.validar_en_sitio(rec.codigo, -12.09, -77.0, "moto@x.com")
    assert res["ok"] is False and res["error"] == "faltan_fotos_propias" and rec.estado == "pendiente_validacion"
    db.canchas["c_pend"]["fotos"] = [f"{SB}/c_pend/a.jpg", f"{SB}/c_pend/b.jpg"]
    res = reclamos.validar_en_sitio(rec.codigo, -12.09, -77.0, "moto@x.com")
    assert res["ok"] and res["estado"] == "activada"


def test_base_caida_no_activa_a_ciegas(db, monkeypatch):
    r = reclamos.crear_reclamo("c_pend", "x@gmail.com", "Club Raqueta", "51987654321", lat=-12.09, lng=-77.0)
    rec = next(x for x in stores.reclamos if x.id == r["reclamo_id"])

    def _cae(ids):
        raise RuntimeError("timeout")
    monkeypatch.setattr(datos, "fotos_de_canchas", _cae)
    res = reclamos.aprobar_directo(rec.id, "admin")
    assert res["ok"] is False and res["error"] == "fotos_no_verificables" and rec.estado == "pendiente_triage"
    # La lista de la torre no se rompe (sin dato de fotos).
    assert all("fotos_propias" not in d for d in reclamos.listar())


def test_minimo_cero_desactiva_todo_y_se_configura_en_la_torre(db, monkeypatch):
    cli = TestClient(app, base_url="https://testserver")
    h = {"X-Admin-Token": "adm"}
    assert cli.get("/admin/api/reclamo-fotos", headers=h).json() == {"minimo": 2, "max": 8}
    assert cli.get("/admin/api/reclamo-fotos").status_code in (401, 403)
    assert cli.get("/config/canal").json()["reclamo_fotos_min"] == 2  # el APK lo lee de aquí
    assert cli.post("/admin/api/reclamo-fotos", headers=h, json={"minimo": 12}).json()["ok"] is False
    assert cli.post("/admin/api/reclamo-fotos", headers=h, json={"minimo": 0}).json() == {"ok": True, "minimo": 0, "max": 8}
    assert cli.get("/config/canal").json()["reclamo_fotos_min"] == 0
    assert "reclamo-fotos" in cli.get("/admin").text and "Fotos propias al reclamar" in cli.get("/admin").text
    html, nid, body = _registro(cli, monkeypatch, "sinfotos@gmail.com")
    assert "id='fotosCont'" not in html and '"minFotos": 0' in html
    r = cli.post("/anfitrion/nueva", json=body)
    assert r.status_code == 200 and r.json()["ok"], r.text
    rec = next(x for x in stores.reclamos if x.cancha_id == nid)
    assert "fotos_propias" not in next(x for x in reclamos.listar() if x["id"] == rec.id)
    assert "para que podamos aprobarlo" not in cli.get(f"/anfitrion/verificacion/{nid}").text
    assert reclamos.aprobar_directo(rec.id, "admin")["estado"] == "activada"
