"""FOTOS PROPIAS DE LOS LOCALES YA VERIFICADOS (pedido del director, 2-oct-2026:
"los que ya registraron sus canchas usan fotos de Google Place; deben poder
subir sus propias fotos con un plazo y la torre debe llevar el control… así
vamos bajando costos").

Campaña por LOCAL (dueño + club): mínimo `fotos_local_min` (3), plazo
`fotos_local_plazo_dias` (30) desde el lanzamiento o desde que se aprobó el
local, prórroga por local. `ok` y `vencido` dejan de pedir fotos a Google."""

import os
import sys
from datetime import date, datetime, timezone

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config  # noqa: E402
import correos  # noqa: E402
from db.store import ReclamoPropiedad, stores  # noqa: E402
from main import app  # noqa: E402
from pagos import router as pagos_router  # noqa: E402
from propiedad import fotos_locales as fl  # noqa: E402
from web import descubrir  # noqa: E402
from test_web_reservas import _entrar_como, db  # noqa: E402,F401

SB = "https://sb.test/storage/v1/object/public/canchas"
GOOGLE = "https://lh3.googleusercontent.com/p/AF1Qip-google=w800"
ADM = {"X-Admin-Token": "adm"}
# Locales del FakeDB (dueno@x.com): "Club Raqueta" = c_lima + c_noche; "Club Sur" = c_gye.
K_RAQ = "dueno@x.com|club raqueta"
K_SUR = "dueno@x.com|club sur"


@pytest.fixture(autouse=True)
def _base(monkeypatch):
    monkeypatch.setattr(config, "SUPABASE_URL", "https://sb.test")
    monkeypatch.setattr(config, "SUPABASE_ANON_KEY", "anon")
    monkeypatch.setattr(config, "GOOGLE_WEB_CLIENT_ID", "cid-web")
    monkeypatch.setattr(config, "ADMIN_PANEL_TOKEN", "adm")
    hoy = {"d": date(2026, 10, 1)}
    monkeypatch.setattr(fl, "_hoy", lambda: hoy["d"])
    push, mails, google = [], [], []
    monkeypatch.setattr(pagos_router, "_aviso_push_usuario", lambda email, t, c, tipo="aviso": push.append((email, t, c, tipo)))
    monkeypatch.setattr(correos, "encolar", lambda tipo, **k: mails.append((tipo, k.get("datos") or {})))

    def _google(*a, **k):
        google.append(a)
        return [GOOGLE]
    monkeypatch.setattr(descubrir, "fotos_de_lugar", _google)
    for k in (fl.CLAVE_MIN, fl.CLAVE_PLAZO, fl.CLAVE_INICIO):
        stores.config.pop(k, None)
    stores.fotos_locales.clear()
    stores.reclamos.clear()
    fl.invalidar()
    yield {"hoy": hoy, "push": push, "mails": mails, "google": google}
    for k in (fl.CLAVE_MIN, fl.CLAVE_PLAZO, fl.CLAVE_INICIO):
        stores.config.pop(k, None)
    stores.fotos_locales.clear()
    stores.reclamos.clear()
    fl.invalidar()


def _fotos(db, cid, n, google=False):
    urls = [f"{SB}/{cid}/web_{i}.jpg" for i in range(n)] + ([GOOGLE] if google else [])
    db.canchas[cid]["fotos"] = urls
    db.canchas[cid]["foto_url"] = urls[0] if urls else ""
    fl.invalidar()


def _est(key):
    return next(x for x in fl.locales() if x["key"] == key)


def test_estado_ok_pendiente_vencido_prorroga_y_plazo_desde_la_verificacion(db, _base):
    assert fl.minimo() == 3 and fl.plazo_dias() == 30 and fl.inicio() is None and not fl.lanzada()
    # Sin lanzar: sin el mínimo = inactiva (todo como hoy).
    assert _est(K_SUR)["estado"] == "inactiva" and fl.estado_de_cancha(db.canchas["c_gye"])["sin_google"] is False
    # Fotos del local = unión de sus canchas: 2 en c_lima + 1 en c_noche = 3 → ok (aunque no se haya lanzado).
    _fotos(db, "c_lima", 2, google=True)
    _fotos(db, "c_noche", 1)
    e = _est(K_RAQ)
    assert e["estado"] == "ok" and e["n"] == 3 and e["sin_google"] and GOOGLE not in e["fotos"]
    assert set(e["canchas"]) == {"c_lima", "c_noche"} and e["principal"] == "c_lima"
    # La cancha en verificación (PEND) no entra a la campaña.
    assert all("c_pend" not in x["canchas"] for x in fl.locales())
    # Lanzar: plazo de 30 días desde hoy.
    r = fl.lanzar(avisar=False)
    assert r["ok"] and r["inicio"] == "2026-10-01" and fl.lanzada()
    e = _est(K_SUR)
    assert e["estado"] == "pendiente" and e["vence"] == "2026-10-31" and e["dias_restantes"] == 30 and e["faltan"] == 3
    _base["hoy"]["d"] = date(2026, 10, 31)
    assert _est(K_SUR)["estado"] == "pendiente" and _est(K_SUR)["dias_restantes"] == 0  # último día
    _base["hoy"]["d"] = date(2026, 11, 1)
    assert _est(K_SUR)["estado"] == "vencido"
    # Prórroga del operador: +15 días a ESE local.
    assert fl.prorrogar(K_SUR)["prorroga_dias"] == 15
    e = _est(K_SUR)
    assert e["estado"] == "pendiente" and e["vence"] == "2026-11-15" and e["prorroga_dias"] == 15
    assert fl.prorrogar("x", 15)["ok"] is False and fl.prorrogar(K_SUR, 0)["ok"] is False
    # Un local aprobado DESPUÉS del lanzamiento no nace vencido: su plazo corre desde la aprobación.
    stores.fotos_locales.clear()
    stores.reclamos.append(ReclamoPropiedad(
        id=1, cancha_id="c_gye", solicitante_id="dueno@x.com", nombre_local="Club Sur", codigo="ABC123",
        estado="activada", creado_en=datetime(2026, 10, 10, 15, tzinfo=timezone.utc),
        decidido_en=datetime(2026, 10, 20, 15, tzinfo=timezone.utc)))
    e = _est(K_SUR)
    assert e["desde"] == "2026-10-20" and e["vence"] == "2026-11-19" and e["estado"] == "pendiente"
    # Con las fotos subidas pasa a ok.
    _fotos(db, "c_gye", 3)
    assert _est(K_SUR)["estado"] == "ok"
    # Configuración y pausa.
    assert fl.set_config(9, None)["ok"] is False and fl.set_config(None, 0)["ok"] is False
    assert fl.set_config(4, 45)["minimo"] == 4 and fl.plazo_dias() == 45
    assert _est(K_SUR)["estado"] == "pendiente" and _est(K_SUR)["faltan"] == 1
    assert fl.pausar()["minimo"] == 0
    assert all(x["estado"] == "inactiva" for x in fl.locales())
    assert fl.estado_de_cancha(db.canchas["c_gye"]) is None and fl.sin_google_ids() == []
    assert fl.lanzar()["error"] == "minimo_cero"


def test_web_foto_no_llama_a_google_para_local_ok_ni_vencido(db, _base):
    cli = TestClient(app, base_url="https://testserver")
    db.canchas["c_gye"]["fotos"] = [GOOGLE]  # foto de Google GUARDADA en la fila (legado del APK)
    db.canchas["c_gye"]["foto_url"] = GOOGLE
    # Pendiente / campaña sin lanzar: como siempre (las de la fila, y Google si no hay nada).
    assert cli.get("/web/foto", params={"id": "c_gye"}).json()["fotos"] == [GOOGLE]
    r = cli.get("/web/foto", params={"id": "c_lima"}).json()
    assert r["origen"] == "google" and len(_base["google"]) == 1
    # Local OK (Club Raqueta): solo sus fotos propias, nunca Google.
    _fotos(db, "c_lima", 3, google=True)
    _base["google"].clear()
    r = cli.get("/web/foto", params={"id": "c_lima"}).json()
    assert r["origen"] == "propias" and GOOGLE not in r["fotos"] and len(r["fotos"]) == 3
    r = cli.get("/web/foto", params={"id": "c_noche"}).json()  # hermana sin fotos: muestra las del local
    assert r["origen"] == "propias" and r["fotos"][0].startswith(f"{SB}/c_lima/") and not _base["google"]
    html = cli.get("/").text
    assert f"{SB}/c_lima/web_0.jpg" in html
    # Local VENCIDO (Club Sur): ni la guardada ni la de Google; placeholder sin pedir nada.
    fl.lanzar(avisar=False)
    _base["hoy"]["d"] = date(2026, 11, 5)
    fl.invalidar()
    r = cli.get("/web/foto", params={"id": "c_gye"}).json()
    assert r == {"ok": True, "fotos": [], "origen": "sin_google"} and not _base["google"]
    ficha = cli.get("/reservar/c_gye").text
    assert GOOGLE not in ficha and "/web/foto?id=c_gye" not in ficha
    assert GOOGLE not in cli.get("/").text
    # El APK sabe qué canchas ya no usan Google.
    pub = cli.get("/config/fotos-locales").json()
    assert pub["lanzada"] and pub["minimo"] == 3 and set(pub["sin_google"]) == {"c_lima", "c_noche", "c_gye"}
    assert cli.get("/config/canal").json()["fotos_local_min"] == 3


def test_torre_controla_la_campana(db, _base):
    cli = TestClient(app, base_url="https://testserver")
    assert cli.get("/admin/api/fotos-locales").status_code == 401
    _fotos(db, "c_lima", 3)
    j = cli.get("/admin/api/fotos-locales", headers=ADM).json()
    assert j["config"]["lanzada"] is False and j["kpis"]["ok"] == 1 and j["kpis"]["total"] == 2 and j["kpis"]["pct"] == 50
    assert {x["key"] for x in j["locales"]} == {K_RAQ, K_SUR}
    # Config: mínimo 4, plazo 45.
    j = cli.post("/admin/api/fotos-locales/config", headers=ADM, json={"minimo": 4, "plazo_dias": 45}).json()
    assert j["ok"] and j["minimo"] == 4 and j["plazo_dias"] == 45
    assert cli.post("/admin/api/fotos-locales/config", headers=ADM, json={"minimo": 12}).json()["ok"] is False
    # Lanzar: avisa (push + correo) a los dos locales que no llegan a 4.
    j = cli.post("/admin/api/fotos-locales/lanzar", headers=ADM).json()
    assert j["ok"] and j["avisos"] == 2 and j["inicio"] == "2026-10-01"
    assert len(_base["push"]) == 2 and all(p[0] == "dueno@x.com" and p[3] == "fotos_local" for p in _base["push"])
    assert any("Club Sur" in p[2] and "15 nov" in p[2] for p in _base["push"])
    assert [m[0] for m in _base["mails"]] == ["fotos_local", "fotos_local"]
    j = cli.get("/admin/api/fotos-locales", headers=ADM).json()
    sur = next(x for x in j["locales"] if x["key"] == K_SUR)
    assert sur["estado"] == "pendiente" and sur["dias_restantes"] == 45 and sur["ultimo_aviso"]
    # Recordar ahora (siempre envía) y prórroga.
    assert cli.post("/admin/api/fotos-locales/recordar", headers=ADM, json={"key": K_SUR}).json()["ok"]
    assert len(_base["push"]) == 3
    j = cli.post("/admin/api/fotos-locales/prorroga", headers=ADM, json={"key": K_SUR}).json()
    assert j["ok"] and j["prorroga_dias"] == 15
    assert cli.post("/admin/api/fotos-locales/recordar", headers=ADM, json={"key": "nadie|nada"}).json()["ok"] is False
    # Pausar.
    j = cli.post("/admin/api/fotos-locales/pausar", headers=ADM).json()
    assert j["ok"] and j["minimo"] == 0 and cli.get("/config/canal").json()["fotos_local_min"] == 0
    # La torre tiene el pane.
    html = cli.get("/admin").text
    assert "Fotos de los locales" in html and "cargarFotosLocales" in html and "flLanzar" in html


def test_recordatorios_idempotentes_a_7_y_1_dia_y_al_vencer(db, _base):
    _fotos(db, "c_lima", 3)  # Club Raqueta ya cumple: nunca recibe avisos
    assert fl.recordatorios()["enviados"] == 0  # sin lanzar no se avisa nada
    assert fl.lanzar()["avisos"] == 1
    assert fl.recordatorios()["enviados"] == 0  # idempotente
    _base["hoy"]["d"] = date(2026, 10, 20)  # 11 días: nada nuevo
    assert fl.recordatorios()["enviados"] == 0
    _base["hoy"]["d"] = date(2026, 10, 24)  # 7 días
    assert fl.recordatorios()["enviados"] == 1 and "semana" in _base["push"][-1][1]
    assert fl.recordatorios()["enviados"] == 0
    _base["hoy"]["d"] = date(2026, 10, 30)  # 1 día
    assert fl.recordatorios()["enviados"] == 1 and "Mañana" in _base["push"][-1][1]
    _base["hoy"]["d"] = date(2026, 11, 2)  # venció
    assert fl.recordatorios()["enviados"] == 1 and "ya no muestra fotos" in _base["push"][-1][1]
    assert fl.recordatorios()["enviados"] == 0
    assert all(p[0] == "dueno@x.com" and "Club Sur" in p[2] for p in _base["push"])
    assert len(_base["push"]) == 4 and len({m[1]["clave"] for m in _base["mails"]}) == 4
    # Prórroga: el nuevo vencimiento vuelve a tener su aviso de 1 día (no el de lanzamiento).
    fl.prorrogar(K_SUR, 15)  # vence 15 nov
    _base["hoy"]["d"] = date(2026, 11, 14)
    assert fl.recordatorios()["enviados"] == 1 and "Mañana" in _base["push"][-1][1]
    # Un local recién aprobado a 3 días del cierre recibe UN aviso (no "lanzamiento" + "7 días").
    stores.fotos_locales.clear()
    stores.config[fl.CLAVE_INICIO] = "2026-09-01"
    stores.reclamos.append(ReclamoPropiedad(
        id=2, cancha_id="c_gye", solicitante_id="dueno@x.com", nombre_local="Club Sur", codigo="XYZ789",
        estado="activada", creado_en=datetime(2026, 10, 1, 15, tzinfo=timezone.utc),
        decidido_en=datetime(2026, 10, 3, 15, tzinfo=timezone.utc)))  # vence 2 nov
    _base["hoy"]["d"] = date(2026, 10, 30)  # le quedan 3 días
    n = len(_base["push"])
    assert fl.recordatorios()["enviados"] == 1 and "semana" in _base["push"][-1][1] and "te quedan 3 días" in _base["push"][-1][2]
    assert fl.recordatorios()["enviados"] == 0 and len(_base["push"]) == n + 1
    # Correo: se arma con el botón directo a subir fotos.
    datos_mail = _base["mails"][-1][1]
    msgs = correos._armar_fotos_local({"id": "ev1", "datos": datos_mail})
    assert msgs and msgs[0]["para"] == "dueno@x.com" and "/anfitrion/cancha/c_gye/editar#sec-fotos" in msgs[0]["html"]
    assert correos._armar_fotos_local({"id": "ev2", "datos": {"para": "no-es-correo"}}) == []


def test_dueno_ve_el_aviso_en_la_web_y_en_el_app(db, _base, monkeypatch):
    cli = TestClient(app, base_url="https://testserver")
    _entrar_como(cli, monkeypatch, "dueno@x.com", "Dueño")
    assert "Sube 3 fotos" not in cli.get("/anfitrion/canchas").text  # sin lanzar no se pide nada
    fl.lanzar(avisar=False)
    _fotos(db, "c_lima", 1)
    mc = cli.get("/anfitrion/canchas").text
    assert "Sube 3 fotos de Club Sur antes del 31 oct" in mc and "/anfitrion/cancha/c_gye/editar#sec-fotos" in mc
    assert "Sube 2 fotos de Club Raqueta" in mc and "/anfitrion/cancha/c_lima/editar#sec-fotos" in mc
    assert "Sube 3 fotos de Club Sur" in cli.get("/anfitrion/mis-canchas").text
    ed = cli.get("/anfitrion/cancha/c_gye/editar").text
    assert "Tu local lleva <b>0 de 3</b> fotos propias" in ed
    _base["hoy"]["d"] = date(2026, 11, 3)
    fl.invalidar()
    mc = cli.get("/anfitrion/canchas").text
    assert "Club Sur ya no muestra fotos" in mc and "class='aviso err'" in mc
    # APK: estado de los locales del dueño.
    j = cli.get("/fotos-locales/mios", params={"email": "dueno@x.com"}).json()
    sur = next(x for x in j["locales"] if x["key"] == K_SUR)
    assert sur["estado"] == "vencido" and sur["principal"] == "c_gye" and "ya no muestra fotos" in sur["texto"]
    assert cli.get("/fotos-locales/mios", params={"email": "x"}).status_code == 400
    # Sube las que faltan → desaparece el aviso.
    _fotos(db, "c_gye", 3)
    assert "Club Sur ya no muestra fotos" not in cli.get("/anfitrion/canchas").text


def test_snapshot_conserva_la_campana():
    stores.fotos_locales["a|b"] = {"prorroga_dias": 15, "avisos": {"lanzamiento:2026-10-01": "x"}}
    st = stores.to_state()
    stores.fotos_locales.clear()
    stores.load_state(st)
    assert stores.fotos_locales["a|b"]["prorroga_dias"] == 15
