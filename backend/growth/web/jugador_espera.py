"""LISTA DE ESPERA en la web (plan de mejoras ronda 2, P2-2). Misma tabla y
mismo formato que el APK (`pichangol_espera`, `lib/models/espera.dart`): un
jugador ↔ un turno ocupado; si ese turno se libera, le llega un push
"¡Se liberó tu hora! ⏰" y el primero que reserva se lo queda.

- `POST /web/espera {cancha_id, fecha, hora}` → me anoto (solo turnos ocupados
  y en fechas reservables); `POST /web/espera/salir` → me salgo.
- `avisar_liberados(slots)` lo llaman la cancelación web (jugador o
  anfitrión) y "Quitar reserva" del anfitrión, igual que
  `AppState._avisarEsperaLiberada` del APK.
- `mias(email)` alimenta la sección "Lista de espera" de Mis reservas.
"""

from __future__ import annotations

import threading

from fastapi import APIRouter, Body, Request
from fastapi.responses import JSONResponse

from db import pg
from web import datos, horarios, sesion

router = APIRouter()


def clave_id(usuario: str, cancha_id: str, fecha: str, hora: str) -> str:
    """Id determinista (upsert idempotente). El APK usa el hashCode de Dart; aquí
    basta con que sea estable para la web: el UNIQUE lógico es el id."""
    import zlib
    u = usuario.strip().lower()
    return f"esp_w{zlib.crc32(u.encode()) & 0xFFFFF:x}_{cancha_id}_{fecha}_{hora}"


def _db_unirse(e: dict) -> bool:
    if not pg.habilitado:
        return False
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            # Una entrada por (cancha, fecha, hora, usuario) aunque venga del APK con otro id.
            cur.execute("DELETE FROM pichangol_espera WHERE cancha_id = %s AND fecha = %s AND hora = %s AND lower(usuario) = %s",
                        (e["cancha_id"], e["fecha"], e["hora"], e["usuario"]))
            cur.execute("INSERT INTO pichangol_espera (id, cancha_id, fecha, hora, usuario, nombre, telefono) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                        (e["id"], e["cancha_id"], e["fecha"], e["hora"], e["usuario"], e["nombre"], e["telefono"]))
        return True
    except Exception as ex:  # noqa: BLE001
        print(f"[espera] no se pudo anotar: {ex}", flush=True)
        return False


def _db_salir(usuario: str, cancha_id: str, fecha: str, hora: str) -> bool:
    if not pg.habilitado:
        return False
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM pichangol_espera WHERE cancha_id = %s AND fecha = %s AND hora = %s AND lower(usuario) = %s",
                        (cancha_id, fecha, hora, usuario))
        return True
    except Exception:  # noqa: BLE001
        return False


def esperan(cancha_id: str, fecha: str, hora: str) -> list[str]:
    """Correos que esperan ese turno (el más antiguo primero)."""
    if not pg.habilitado:
        return []
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT lower(usuario) FROM pichangol_espera WHERE cancha_id = %s AND fecha = %s AND hora = %s "
                        "ORDER BY creado", (cancha_id, fecha, hora))
            return [r[0] for r in cur.fetchall()]
    except Exception:  # noqa: BLE001
        return []


def mias(email: str, cancha_id: str = "", fecha: str = "") -> list[dict]:
    """Mis turnos en espera desde hoy (opcional: de una cancha y fecha)."""
    if not pg.habilitado or not email:
        return []
    hoy = horarios.ahora_local("PE").date().isoformat()
    sql = "SELECT cancha_id, fecha, hora FROM pichangol_espera WHERE lower(usuario) = %s AND fecha >= %s"
    args: list = [email.strip().lower(), hoy]
    if cancha_id:
        sql += " AND cancha_id = %s"
        args.append(cancha_id)
    if fecha:
        sql += " AND fecha = %s"
        args.append(fecha)
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute(sql + " ORDER BY fecha, hora LIMIT 50", tuple(args))
            return [{"cancha_id": r[0], "fecha": r[1], "hora": r[2]} for r in cur.fetchall()]
    except Exception:  # noqa: BLE001
        return []


def avisar_liberados(slots: list[tuple[str, str, str]], salvo: str = "") -> None:
    """Push "¡Se liberó tu hora!" a quien espera cada (cancha, fecha, hora)
    liberado. En segundo plano: nunca demora la cancelación."""
    slots = [s for s in slots if all(s)]
    if not slots:
        return

    def _correr():
        from pagos import router as pr
        for cancha_id, fecha, hora in slots:
            c = datos.cancha(cancha_id) or {}
            lugar = (c.get("club") or "").strip() or c.get("nombre") or "la cancha"
            for email in esperan(cancha_id, fecha, hora):
                if email == (salvo or "").strip().lower():
                    continue
                try:
                    pr._aviso_push_usuario(email, "¡Se liberó tu hora! ⏰",
                                           f"Las {hora} del {horarios.fecha_larga(fecha)} en {lugar} quedaron libres. "
                                           "Entra y resérvalas antes de que las tomen.", "espera")
                except Exception:  # noqa: BLE001
                    pass
    threading.Thread(target=_correr, name="pcg-espera", daemon=True).start()


def _ses(request: Request) -> dict | None:
    s = sesion.de_request(request)
    return s if s and s.get("email") else None


@router.post("/web/espera")
def unirse(request: Request, body: dict = Body(None)):
    ses = _ses(request)
    if not ses:
        return JSONResponse({"ok": False, "error": "sesion_requerida"}, status_code=401)
    b = body or {}
    cid, fecha, hora = str(b.get("cancha_id") or ""), str(b.get("fecha") or ""), str(b.get("hora") or "")
    c = datos.cancha(cid) if cid else None
    if not c or not datos.reservable(c):
        return JSONResponse({"ok": False, "error": "cancha"}, status_code=404)
    from web import router as wr
    d_min, d_max = wr._fechas_validas(wr._pais_de(c))
    if not (wr._es_iso(fecha) and d_min <= fecha <= d_max):
        return JSONResponse({"ok": False, "error": "fecha", "mensaje": "Esa fecha ya no se puede reservar."}, status_code=400)
    slot = next((s for s in wr._slots_del_dia(c, fecha) if s.get("hora") == hora), None)
    if not slot:
        return JSONResponse({"ok": False, "error": "hora", "mensaje": "Ese turno no existe."}, status_code=400)
    if not slot.get("ocupado"):
        return JSONResponse({"ok": False, "error": "libre", "mensaje": "Ese turno está libre: resérvalo ahora."}, status_code=409)
    email = ses["email"].strip().lower()
    fecha_real = slot.get("fecha") or fecha   # madrugada: la fecha real del turno
    if any(r.get("cancha_id") == cid and str(r.get("fecha")) == fecha_real and str(r.get("hora_inicio")) == hora
           for r in datos.reservas_de_usuario(email)):
        return JSONResponse({"ok": False, "error": "es_tuya", "mensaje": "Ese turno ya es tuyo: míralo en Mis reservas."}, status_code=409)
    e = {"id": clave_id(email, cid, fecha_real, hora), "cancha_id": cid, "fecha": fecha_real, "hora": hora,
         "usuario": email, "nombre": (ses.get("nombre") or "")[:80], "telefono": datos.celular_de_perfil(email) or ""}
    if not _db_unirse(e):
        return JSONResponse({"ok": False, "error": "no_guardado", "mensaje": "No pudimos anotarte. Inténtalo de nuevo."}, status_code=503)
    return {"ok": True}


@router.post("/web/espera/salir")
def salir(request: Request, body: dict = Body(None)):
    ses = _ses(request)
    if not ses:
        return JSONResponse({"ok": False, "error": "sesion_requerida"}, status_code=401)
    b = body or {}
    ok = _db_salir(ses["email"].strip().lower(), str(b.get("cancha_id") or ""), str(b.get("fecha") or ""), str(b.get("hora") or ""))
    return {"ok": ok}
