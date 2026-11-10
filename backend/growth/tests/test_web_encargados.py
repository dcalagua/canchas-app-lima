"""ENCARGADOS DEL LOCAL (rol único "Recepción") en el modo anfitrión web.

El dueño invita por correo → la persona acepta en /anfitrion → opera la
agenda, las reservas manuales, los bloqueos, los pagos marcados y los
comprobantes SOLO de ese local; todo lo demás (plata, edición, cobros del club,
cancelar con devolución, invitar) le responde 403/404. Quitar el acceso corta
al instante. Sin la migración 0005 la función queda oculta y nada se rompe.
"""

import pytest
from fastapi.testclient import TestClient

import config
from db.store import stores
from main import app
from web import datos, encargados, permisos, sesion
from tests.test_cobro_directo import JUGADOR, _asegurar, directo  # noqa: F401
from tests.test_web_reservas import _manana, db  # noqa: F401
from tests.test_web_anfitrion_cobros_club import _png_de

DUENO = "dueno@x.com"
RECEP = "recep@x.com"


def _cli(email):
    c = TestClient(app, base_url="https://testserver")
    c.cookies.set(sesion.COOKIE, sesion.emitir({"email": email, "nombre": email.split("@")[0].title(), "foto": ""}))
    return c


@pytest.fixture
def enc(db, monkeypatch):
    """Repositorio en memoria + push síncrono capturado."""
    from pagos import router as pr
    from web import anfitrion as anf
    repo = encargados.RepoMemoria()
    encargados.usar_repo(repo)
    monkeypatch.setattr(encargados, "CACHE_TTL", 0)
    monkeypatch.setattr(config, "GOOGLE_WEB_CLIENT_ID", "cid-web")
    pushes = []
    monkeypatch.setattr(pr, "_aviso_push_usuario", lambda email, titulo, cuerpo, tipo="aviso": pushes.append((email, titulo, cuerpo, tipo)))
    monkeypatch.setattr(anf, "_en_segundo_plano", lambda fn, *a: fn(*a))
    monkeypatch.setattr(stores, "correos_eventos", [], raising=False)
    yield {"repo": repo, "pushes": pushes, "db": db}
    encargados.usar_repo(encargados.RepoPG())


def _invitar_y_aceptar(dueno_cli=None, cancha="c_lima", email=RECEP):
    dueno_cli = dueno_cli or _cli(DUENO)
    r = dueno_cli.post("/anfitrion/encargados/invitar", json={"cancha_id": cancha, "email": email}).json()
    assert r["ok"], r
    a = _cli(email).post(f"/anfitrion/encargos/{r['id']}/aceptar", json={}).json()
    assert a["ok"], a
    return r["id"]


# ── invitar / aceptar / rechazar ─────────────────────────────────────────────

def test_dueno_invita_y_la_persona_acepta(enc):
    dueno, recep = _cli(DUENO), _cli(RECEP)
    pag = dueno.get("/anfitrion/encargados?local=c_lima").text
    assert "Equipo de Club Raqueta" in pag and "Correo de Google de la persona" in pag and "Recepción puede" in pag
    assert "Club Sur" in pag  # chips por local
    # Validaciones (el correo es el único texto libre).
    assert dueno.post("/anfitrion/encargados/invitar", json={"cancha_id": "c_lima", "email": "no-es-correo"}).json()["error"] == "correo_invalido"
    assert dueno.post("/anfitrion/encargados/invitar", json={"cancha_id": "c_lima", "email": DUENO}).json()["error"] == "eres_tu"
    assert dueno.post("/anfitrion/encargados/invitar", content="x", headers={"Content-Type": "text/plain"}).status_code == 415
    assert dueno.post("/anfitrion/encargados/invitar", json={"cancha_id": "c_lima", "email": RECEP},
                      headers={"Origin": "https://malo.com"}).status_code == 403
    assert TestClient(app).post("/anfitrion/encargados/invitar", json={}).status_code == 401
    assert _cli("otro@x.com").post("/anfitrion/encargados/invitar", json={"cancha_id": "c_lima", "email": RECEP}).status_code == 404
    r = dueno.post("/anfitrion/encargados/invitar", json={"cancha_id": "c_lima", "email": " Recep@X.com "}).json()
    assert r["ok"] and not r["ya_invitado"]
    fila = enc["repo"].filas[r["id"]]
    assert fila["email"] == RECEP and fila["local_key"] == "dueno@x.com|club raqueta" and set(fila["cancha_ids"]) == {"c_lima", "c_noche"}
    assert fila["estado"] == "invitado" and fila["rol"] == "recepcion"
    # Idempotente: invitar de nuevo devuelve la misma.
    assert dueno.post("/anfitrion/encargados/invitar", json={"cancha_id": "c_noche", "email": RECEP}).json() == {"ok": True, "ya_invitado": True, "id": r["id"]}
    # Push + correo a la persona invitada.
    assert any(p[0] == RECEP and "invitaron" in p[1] for p in enc["pushes"])
    ev = [x for x in stores.correos_eventos if x["tipo"] == "aviso" and x["datos"].get("para") == RECEP]
    assert ev and "Club Raqueta" in ev[0]["datos"]["titulo"]
    assert "Invitación enviada" in dueno.get("/anfitrion/encargados?local=c_lima").text
    # Antes de aceptar: sin acceso a nada del local.
    assert "Cancha Central" not in recep.get("/anfitrion/calendario").text
    assert recep.post("/anfitrion/bloqueo", json={"cancha_id": "c_lima", "fecha": _manana(), "hora": "10:00"}).status_code == 404
    menu = recep.get("/anfitrion").text
    assert "Te invitaron a ayudar en Club Raqueta" in menu and "data-acc='aceptar'" in menu
    # Otra persona no puede aceptar una invitación ajena.
    assert _cli("otro@x.com").post(f"/anfitrion/encargos/{r['id']}/aceptar", json={}).status_code == 404
    a = recep.post(f"/anfitrion/encargos/{r['id']}/aceptar", json={}).json()
    assert a == {"ok": True, "ir": "/anfitrion/mis-canchas"}
    assert enc["repo"].filas[r["id"]]["estado"] == "activo" and enc["repo"].filas[r["id"]]["aceptado_en"]
    assert any(p[0] == DUENO and "aceptó" in p[1] for p in enc["pushes"])
    assert recep.post(f"/anfitrion/encargos/{r['id']}/aceptar", json={}).status_code == 404  # ya respondida
    # Menú recortado: locales donde ayuda, sin la plata ni la configuración del club.
    menu = recep.get("/anfitrion").text
    assert "Locales donde ayudas" in menu and "Te invitaron" not in menu
    assert "/anfitrion/pagos-por-confirmar" in menu
    for oculto in ("/anfitrion/cobros-club'", "/anfitrion/reportes'", "/anfitrion/caja'", "/anfitrion/encargados'", "/anfitrion/reglas'"):
        assert oculto not in menu, oculto
    assert "Activo" in dueno.get("/anfitrion/encargados?local=c_lima").text
    # Editar local del dueño trae la sección Encargados.
    loc = dueno.get("/anfitrion/local/c_lima/editar").text
    assert "id='sec-encargados'" in loc and RECEP in loc and "#sec-encargados" in loc


def test_rechazar_la_invitacion(enc):
    r = _cli(DUENO).post("/anfitrion/encargados/invitar", json={"cancha_id": "c_lima", "email": RECEP}).json()
    assert _cli(RECEP).post(f"/anfitrion/encargos/{r['id']}/rechazar", json={}).json()["ok"]
    assert enc["repo"].filas[r["id"]]["estado"] == "rechazado"
    assert "Cancha Central" not in _cli(RECEP).get("/anfitrion/calendario").text
    assert "Rechazó la invitación" in _cli(DUENO).get("/anfitrion/encargados?local=c_lima").text
    # Reinvitar crea una invitación NUEVA.
    r2 = _cli(DUENO).post("/anfitrion/encargados/invitar", json={"cancha_id": "c_lima", "email": RECEP}).json()
    assert r2["ok"] and r2["id"] != r["id"] and not r2["ya_invitado"]


# ── la recepción opera el local ──────────────────────────────────────────────

def test_recepcion_opera_agenda_reservas_bloqueos_y_pagos_del_local(enc):
    _invitar_y_aceptar()
    recep, dueno = _cli(RECEP), _cli(DUENO)
    f = _manana()
    hoy = recep.get("/anfitrion/mis-canchas")
    assert hoy.status_code == 200 and "2 canchas" in hoy.text and "Comprobantes por confirmar" in hoy.text
    # Pestañas: solo Hoy, Calendario y Reservas.
    assert "/anfitrion/calendario'" in hoy.text and "/anfitrion/ingresos'" not in hoy.text and "/anfitrion/canchas'" not in hoy.text
    cal = recep.get(f"/anfitrion/calendario?cancha=c_lima&desde={f}").text
    assert "Cancha Central" in cal and "Nocturna" in cal and "Cancha Guayaquil" not in cal  # solo el local asignado
    assert "Reserva manual" in cal and "/anfitrion/reglas/" not in cal and '"puedeCancelar": false' in cal
    # Pedir otra cancha del dueño por URL no la abre (cae a la primera del local).
    assert "Cancha Guayaquil" not in recep.get(f"/anfitrion/calendario?cancha=c_gye&desde={f}").text
    # Reserva manual en el local → sí; en otro local del mismo dueño → 404.
    r = recep.post("/anfitrion/reserva-manual", json={"cancha_id": "c_lima", "fecha": f, "hora": "10:00", "nombre": "Luis",
                                                      "telefono": "999111222"}).json()
    assert r["ok"], r
    rid = r["id"]
    assert enc["db"].reservas[rid]["medio_pago"] == "manual" and enc["db"].reservas[rid]["cancha_id"] == "c_lima"
    assert recep.post("/anfitrion/reserva-manual", json={"cancha_id": "c_gye", "fecha": f, "hora": "10:00", "nombre": "X"}).status_code == 404
    # Bloquear / desbloquear.
    assert recep.post("/anfitrion/bloqueo", json={"cancha_id": "c_lima", "fecha": f, "hora": "11:00"}).json()["ok"]
    assert ("c_lima", f, "11:00") in enc["db"].bloqueos
    assert recep.post("/anfitrion/bloqueo", json={"cancha_id": "c_lima", "fecha": f, "hora": "11:00", "bloquear": False}).json()["ok"]
    assert recep.post("/anfitrion/bloqueo", json={"cancha_id": "c_gye", "fecha": f, "hora": "11:00"}).status_code == 404
    # Marcar pagada / por cobrar.
    assert recep.post(f"/anfitrion/reserva/{rid}/pagado", json={"pagado": True}).json()["ok"]
    assert enc["db"].reservas[rid]["pagado"] is True
    assert recep.post(f"/anfitrion/reserva/{rid}/pagado", json={"pagado": False}).json()["ok"]
    # Reserva de OTRO local del dueño: no la toca.
    enc["db"].reservas["man_gye"] = {**enc["db"].reservas[rid], "id": "man_gye", "cancha_id": "c_gye"}
    assert recep.post("/anfitrion/reserva/man_gye/pagado", json={"pagado": True}).status_code == 404
    assert recep.post("/anfitrion/reserva/man_gye/quitar").status_code == 404
    # La reserva aparece en Hoy/Reservas de la recepción y del dueño.
    assert "Luis" in recep.get("/anfitrion/reservas").text
    assert "Luis" in dueno.get("/anfitrion/reservas").text and f"data-rid='{rid}'" in dueno.get(f"/anfitrion/calendario?cancha=c_lima&desde={f}").text
    # Bitácora del dueño: quién hizo qué.
    acc = [(a["actor"], a["accion"]) for a in enc["repo"].acciones]
    assert (RECEP, "reserva_manual") in acc and (RECEP, "bloquear") in acc and (RECEP, "desbloquear") in acc
    assert (RECEP, "marcar_pagada") in acc and (RECEP, "marcar_por_cobrar") in acc
    assert all(a["dueno"] == DUENO for a in enc["repo"].acciones)
    pag = dueno.get("/anfitrion/encargados?local=c_lima").text
    assert "registró una reserva manual" in pag and "Luis" in pag
    # Quitar la reserva manual (deshacer, sin plata).
    assert recep.post(f"/anfitrion/reserva/{rid}/quitar").json()["ok"]
    assert rid not in enc["db"].reservas and (RECEP, "quitar_manual") in [(a["actor"], a["accion"]) for a in enc["repo"].acciones]
    # Las acciones del dueño no van a la bitácora de encargados.
    n = len(enc["repo"].acciones)
    assert dueno.post("/anfitrion/bloqueo", json={"cancha_id": "c_lima", "fecha": f, "hora": "12:00"}).json()["ok"]
    assert len(enc["repo"].acciones) == n


def test_el_candado_pro_es_del_dueno(enc, monkeypatch):
    _invitar_y_aceptar()
    monkeypatch.setattr(config, "WEB_MANUAL_REQUIERE_PRO", True)
    pro = {DUENO}
    monkeypatch.setattr(stores, "pro_activo", lambda email: email in pro)
    f = _manana()
    recep = _cli(RECEP)
    assert recep.post("/anfitrion/bloqueo", json={"cancha_id": "c_lima", "fecha": f, "hora": "10:00"}).json()["ok"]
    assert "parte de <b>Pichangol Pro</b>" not in recep.get(f"/anfitrion/calendario?cancha=c_lima&desde={f}").text
    pro.clear()
    assert recep.post("/anfitrion/bloqueo", json={"cancha_id": "c_lima", "fecha": f, "hora": "11:00"}).status_code == 402


def test_recepcion_no_ve_plata_ni_configuracion(enc, monkeypatch):
    _invitar_y_aceptar()
    monkeypatch.setitem(stores.saldos, DUENO, 987654)
    recep = _cli(RECEP)
    f = _manana()
    # Secciones del dueño → 403 "Tu rol no incluye esta sección".
    for ruta in ("/anfitrion/ingresos", "/anfitrion/canchas", "/anfitrion/reportes", "/anfitrion/caja", "/anfitrion/clientes",
                 "/anfitrion/bonos", "/anfitrion/fijas", "/anfitrion/disponibilidad", "/anfitrion/cobros-club", "/anfitrion/reglas",
                 "/anfitrion/encargados", "/anfitrion/llenar", "/anfitrion/recordatorios", "/anfitrion/cancelaciones"):
        r = recep.get(ruta)
        assert r.status_code == 403, ruta
        assert "Tu rol no incluye esta sección" in r.text and "9876" not in r.text, ruta
    # Editar canchas/local, reglas de una cancha → 404 (no es dueño).
    for ruta in ("/anfitrion/cancha/c_lima/editar", "/anfitrion/local/c_lima/editar", "/anfitrion/reglas/c_lima",
                 "/anfitrion/cancha/c_lima/agregar"):
        assert recep.get(ruta).status_code == 404, ruta
    assert recep.post("/anfitrion/cancha/c_lima/editar", json={"nombre": "Hackeada"}).status_code == 404
    assert recep.post("/anfitrion/local/c_lima/editar", json={"local": "Hackeado"}).status_code == 404
    assert enc["db"].canchas["c_lima"]["nombre"] == "Cancha Central"
    # Cobros del club (Culqi y medios de pago).
    assert recep.post("/anfitrion/cobros-club/culqi", json={"public_key": "pk_test_x", "secret_key": "sk_test_y"}).status_code == 403
    assert recep.post("/anfitrion/cobros-club/medios", json={"medios": []}).status_code == 403
    # Cancelar con devolución: solo el dueño.
    r = recep.post("/anfitrion/reserva-manual", json={"cancha_id": "c_lima", "fecha": f, "hora": "10:00", "nombre": "Luis"}).json()
    enc["db"].reservas[r["id"]].update(medio_pago="tarjeta", pagado=True, usuario="ana@x.com")
    assert recep.post(f"/anfitrion/reserva/{r['id']}/cancelar").status_code == 404
    assert r["id"] in enc["db"].reservas
    # Ni invitar a otros ni quitar a otros encargados.
    assert recep.post("/anfitrion/encargados/invitar", json={"cancha_id": "c_lima", "email": "amigo@x.com"}).status_code == 404
    otro = _cli(DUENO).post("/anfitrion/encargados/invitar", json={"cancha_id": "c_lima", "email": "segundo@x.com"}).json()
    assert recep.post(f"/anfitrion/encargados/{otro['id']}/revocar", json={}).status_code == 404
    assert enc["repo"].filas[otro["id"]]["estado"] == "invitado"
    # Cancelar en línea no aparece en su calendario; el del dueño sí lo trae.
    assert '"puedeCancelar": true' in _cli(DUENO).get(f"/anfitrion/calendario?cancha=c_lima&desde={f}").text


def test_quitar_acceso_corta_al_instante(enc):
    eid = _invitar_y_aceptar()
    recep, dueno = _cli(RECEP), _cli(DUENO)
    f = _manana()
    assert recep.post("/anfitrion/bloqueo", json={"cancha_id": "c_lima", "fecha": f, "hora": "10:00"}).json()["ok"]
    assert _cli("otro@x.com").post(f"/anfitrion/encargados/{eid}/revocar", json={}).status_code == 404
    assert dueno.post(f"/anfitrion/encargados/{eid}/revocar", json={}).json()["ok"]
    assert enc["repo"].filas[eid]["estado"] == "revocado" and enc["repo"].filas[eid]["revocado_en"]
    assert any(p[0] == RECEP and "Ya no tienes acceso" in p[1] for p in enc["pushes"])
    assert recep.post("/anfitrion/bloqueo", json={"cancha_id": "c_lima", "fecha": f, "hora": "11:00"}).status_code == 404
    assert recep.post("/anfitrion/reserva-manual", json={"cancha_id": "c_lima", "fecha": f, "hora": "11:00", "nombre": "X"}).status_code == 404
    assert "Cancha Central" not in recep.get("/anfitrion/calendario").text
    assert "Locales donde ayudas" not in recep.get("/anfitrion").text
    assert "Acceso quitado" in dueno.get("/anfitrion/encargados?local=c_lima").text
    assert dueno.post(f"/anfitrion/encargados/{eid}/revocar", json={}).status_code == 404  # ya quitado


# ── comprobantes (Pagos por confirmar) ───────────────────────────────────────

def _voucher(hora):
    a = _asegurar(hora)
    v = TestClient(app).post("/web/voucher", headers=JUGADOR, json={
        "ids": a["ids"], "firma": a["firma"], "medio": "yape", "operacion": "OP" + hora.replace(":", ""), "imagen": _png_de(int(hora[:2]))}).json()
    assert v["ok"], v
    return a, v["pago_id"]


def test_recepcion_aprueba_y_rechaza_comprobantes_del_local(enc, directo, monkeypatch):  # noqa: F811
    monkeypatch.setattr(datos, "canchas_de_dueno", lambda e: [c for c in enc["db"].canchas.values() if c["dueno"] == e])
    directo["repo"].reemplazar_medios(DUENO, [{"tipo": "yape", "titular": "Club", "numero": "987654321", "banco": "",
                                               "cuenta": "", "cci": "", "qr_url": "", "nota": ""}])
    _invitar_y_aceptar()
    a, pid = _voucher("10:00")
    _b, pid2 = _voucher("15:00")
    _c, pid3 = _voucher("17:00")
    directo["repo"].pagos[pid3]["cancha_id"] = "c_gye"   # comprobante de OTRO local del mismo dueño
    recep = _cli(RECEP)
    pag = recep.get("/anfitrion/pagos-por-confirmar").text
    assert f"data-aprobar='{pid}'" in pag and f"data-aprobar='{pid2}'" in pag and pid3 not in pag
    assert "Por revisar <small>(2)</small>" in pag and "‹ Modo anfitrión" in pag and "Cobros de tu club" not in pag
    assert "aria-label='2 por revisar'" in recep.get("/anfitrion").text
    assert recep.get(f"/anfitrion/pagos-por-confirmar/{pid}/imagen").status_code == 200
    assert recep.get(f"/anfitrion/pagos-por-confirmar/{pid3}/imagen").status_code == 404
    assert recep.post(f"/anfitrion/pagos-por-confirmar/{pid3}/aprobar", json={}).status_code == 404
    r = recep.post(f"/anfitrion/pagos-por-confirmar/{pid}/aprobar", json={}).json()
    assert r["ok"], r
    assert directo["repo"].pagos[pid]["estado"] == "aprobado" and directo["repo"].pagos[pid]["resuelto_por"] == RECEP
    assert enc["db"].reservas[a["ids"][0]]["estado"] == "confirmada"
    # La comisión la paga el DUEÑO (no la recepción).
    assert r["comision"]["deuda_centimos"] == 200
    assert recep.post(f"/anfitrion/pagos-por-confirmar/{pid2}/rechazar", json={"motivo": "monto"}).json()["ok"]
    assert directo["repo"].pagos[pid2]["resuelto_por"] == RECEP
    acc = [(x["actor"], x["accion"], x["ref"]) for x in enc["repo"].acciones]
    assert (RECEP, "voucher_aprobado", pid) in acc and (RECEP, "voucher_rechazado", pid2) in acc
    # El dueño lo ve en Resueltos con quién lo resolvió, y su propio comprobante del otro local sigue ahí.
    hist = _cli(DUENO).get("/anfitrion/pagos-por-confirmar?estado=historial").text
    assert "Aprobado" in hist and f"Por {RECEP} (recepción)" in hist
    assert f"data-aprobar='{pid3}'" in _cli(DUENO).get("/anfitrion/pagos-por-confirmar").text
    assert "aprobó un comprobante" in _cli(DUENO).get("/anfitrion/encargados?local=c_lima").text


# ── reglas de permisos ───────────────────────────────────────────────────────

def test_matriz_de_permisos_y_alcance_por_local(enc):
    eid = _invitar_y_aceptar()
    assert permisos.canchas_operables(RECEP) == {"c_lima": "recepcion", "c_noche": "recepcion"}
    assert set(permisos.canchas_operables(DUENO)) >= {"c_lima", "c_gye", "c_noche"}
    for acc in (permisos.VER_AGENDA, permisos.RESERVA_MANUAL, permisos.BLOQUEAR, permisos.MARCAR_PAGO, permisos.NOSHOW,
                permisos.VOUCHERS, permisos.QUITAR_MANUAL):
        assert permisos.puede(RECEP, "c_lima", acc) and not permisos.puede(RECEP, "c_gye", acc)
    for acc in ("ingresos", "editar", "cobros_club", "cancelar_devolucion", "encargados"):
        assert not permisos.puede(RECEP, "c_lima", acc) and permisos.puede(DUENO, "c_lima", acc)
    assert not permisos.puede("otro@x.com", "c_lima", permisos.VER_AGENDA)
    assert permisos.es_solo_encargado(RECEP) and not permisos.es_solo_encargado(DUENO)
    assert permisos.alcance_delegado(RECEP, permisos.VOUCHERS) == {DUENO: {"c_lima", "c_noche"}}
    # El dueño renombra el local: el encargo lo sigue (canchas ancla).
    for cid in ("c_lima", "c_noche"):
        enc["db"].canchas[cid]["club"] = "Club Raqueta Norte"
    assert set(permisos.canchas_operables(RECEP)) == {"c_lima", "c_noche"}
    # Una cancha que deja de ser del dueño sale sola del alcance.
    enc["db"].canchas["c_noche"]["dueno"] = "nuevo@x.com"
    assert set(permisos.canchas_operables(RECEP)) == {"c_lima"}
    # Revocado → nada.
    encargados.revocar(DUENO, eid)
    assert permisos.canchas_operables(RECEP) == {} and not permisos.es_solo_encargado(RECEP)


def test_quien_tiene_canchas_propias_y_ayuda_en_otro_local(enc):
    """Un dueño que además es recepción de otro: ve las suyas Y las del local
    donde ayuda en la agenda; sus secciones de plata siguen siendo SOLO suyas."""
    enc["db"].canchas["c_mia"] = {**enc["db"].canchas["c_lima"], "id": "c_mia", "nombre": "La Mía", "club": "Mi Club", "dueno": RECEP}
    _invitar_y_aceptar()
    recep = _cli(RECEP)
    assert not permisos.es_solo_encargado(RECEP)
    cal = recep.get("/anfitrion/calendario?cancha=c_mia").text
    assert "La Mía" in cal and "Cancha Central" in cal and '"puedeCancelar": true' in cal
    assert '"puedeCancelar": false' in recep.get("/anfitrion/calendario?cancha=c_lima").text
    ing = recep.get("/anfitrion/ingresos")
    assert ing.status_code == 200 and "/anfitrion/ingresos'" in ing.text
    can = recep.get("/anfitrion/canchas").text
    assert "La Mía" in can and "Cancha Central" not in can
    assert recep.get("/anfitrion/cancha/c_lima/editar").status_code == 404


# ── sin la migración: oculto y sin romper ────────────────────────────────────

def test_sin_migracion_la_funcion_queda_oculta(db, monkeypatch):  # noqa: F811
    monkeypatch.setattr(config, "GOOGLE_WEB_CLIENT_ID", "cid-web")
    encargados.usar_repo(encargados.RepoPG())   # sin DATABASE_URL en la suite → no disponible
    assert not encargados.disponible()
    dueno = _cli(DUENO)
    menu = dueno.get("/anfitrion").text
    assert "/anfitrion/encargados'" not in menu
    assert "id='sec-encargados'" not in dueno.get("/anfitrion/local/c_lima/editar").text
    pag = dueno.get("/anfitrion/encargados?local=c_lima")
    assert pag.status_code == 200 and "aún no están disponibles" in pag.text
    r = dueno.post("/anfitrion/encargados/invitar", json={"cancha_id": "c_lima", "email": RECEP})
    assert r.status_code == 503 and r.json()["error"] == "no_disponible"
    assert permisos.canchas_operables(RECEP) == {}
    # El dueño opera como siempre.
    assert dueno.post("/anfitrion/bloqueo", json={"cancha_id": "c_lima", "fecha": _manana(), "hora": "10:00"}).json()["ok"]
    assert dueno.get("/anfitrion/ingresos").status_code == 200


def test_tope_de_encargados_por_local(enc, monkeypatch):
    monkeypatch.setattr(encargados, "MAX_POR_LOCAL", 2)
    d = _cli(DUENO)
    assert d.post("/anfitrion/encargados/invitar", json={"cancha_id": "c_lima", "email": "a@x.com"}).json()["ok"]
    assert d.post("/anfitrion/encargados/invitar", json={"cancha_id": "c_lima", "email": "b@x.com"}).json()["ok"]
    r = d.post("/anfitrion/encargados/invitar", json={"cancha_id": "c_lima", "email": "c@x.com"})
    assert r.status_code == 400 and r.json()["error"] == "tope"
    # Otro local del mismo dueño tiene su propio cupo.
    assert d.post("/anfitrion/encargados/invitar", json={"cancha_id": "c_gye", "email": "c@x.com"}).json()["ok"]


# ── integración con Postgres local (TEST_DATABASE_URL) ───────────────────────

from tests.conftest_pg import pg_local  # noqa: E402,F401


def test_repo_pg_encargados(pg_local):  # noqa: F811
    pg = pg_local

    def limpiar():
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("delete from cl_encargados where dueno like 'it_%%'")
            cur.execute("delete from cl_encargados_acciones where dueno like 'it_%%'")
            conn.commit()
    r = encargados.RepoPG()
    r._tabla.update(ok=None, t=0.0)
    assert r.disponible()
    limpiar()
    fila = {"id": "enc_it_1", "dueno": "it_d@x.com", "local_key": "it_d@x.com|club", "local_nombre": "Club",
            "cancha_ids": ["c1", "c2"], "email": "it_r@x.com", "rol": "recepcion", "estado": "invitado", "invitado_por": "it_d@x.com"}
    assert r.crear(fila) == ""
    assert r.crear({**fila, "id": "enc_it_2"}) == "ya_existe"           # una viva por persona y local
    assert r.por_id("enc_it_1")["cancha_ids"] == ["c1", "c2"]
    assert [f["id"] for f in r.de_email("it_r@x.com", ("invitado",))] == ["enc_it_1"]
    assert r.cambiar_estado("enc_it_1", "activo", ("invitado",), "aceptado_en")
    assert not r.cambiar_estado("enc_it_1", "activo", ("invitado",), "aceptado_en")   # ya no está invitado
    f = r.por_id("enc_it_1")
    assert f["estado"] == "activo" and f["aceptado_en"]
    assert r.cambiar_estado("enc_it_1", "revocado", ("invitado", "activo"), "revocado_en")
    assert r.crear({**fila, "id": "enc_it_3"}) == ""                     # revocado libera el cupo
    # Solo existe el rol Recepción y los 4 estados (CHECK en la base).
    for col, val in (("estado", "jefe"), ("rol", "admin")):
        with pytest.raises(Exception):
            with pg.conexion() as conn, conn.cursor() as cur:
                cur.execute(f"insert into cl_encargados (id, dueno, local_key, email, {col}) values ('enc_it_x', 'it_d@x.com', 'k', 'z@x.com', %s)", (val,))
                conn.commit()
    # Bitácora.
    assert r.registrar_accion({"encargado_id": "enc_it_3", "dueno": "it_d@x.com", "actor": "it_r@x.com", "accion": "bloquear",
                               "cancha_id": "c1", "ref": "2026-11-01 10:00", "detalle": {"hora": "10:00"}})
    acts = r.acciones_de("it_d@x.com")
    assert acts[0]["accion"] == "bloquear" and acts[0]["detalle"] == {"hora": "10:00"} and acts[0]["creado_en"]
    # RLS activo y sin políticas (la anon key no ve nada).
    with pg.conexion() as conn, conn.cursor() as cur:
        cur.execute("select relname, relrowsecurity from pg_class where relname in ('cl_encargados', 'cl_encargados_acciones')")
        assert all(x[1] for x in cur.fetchall())
        cur.execute("select count(*) from pg_policies where tablename in ('cl_encargados', 'cl_encargados_acciones')")
        assert cur.fetchone()[0] == 0
    limpiar()
