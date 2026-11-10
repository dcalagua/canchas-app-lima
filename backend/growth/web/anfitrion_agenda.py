"""AGENDA DEL ANFITRIÓN EN SU CALENDARIO (plan de mejoras ronda 2, P2-10).

Un enlace iCal PRIVADO por dueño (`/anfitrion/agenda/<token>.ics`) que Google
Calendar, Apple o Outlook leen solos ("Agregar calendario → Desde URL") y
refrescan cada pocas horas: las reservas de todas sus canchas de los últimos 7
días a los próximos 60, con jugador, celular, monto y si está pagada.

El token = correo en base64url + firma HMAC con el secreto estable del backend
(`sesion._secreto`): sin la firma no se puede adivinar el de otro dueño. No
hace falta sesión (los calendarios no tienen cookies) y `robots.txt` ya excluye
`/anfitrion`.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter
from fastapi.responses import Response

import config
from config import MARCA
from web import datos, horarios, sesion

router = APIRouter()


def _firma(email: str) -> str:
    return hmac.new(sesion._secreto(), f"agenda:{email}".encode(), hashlib.sha256).hexdigest()[:24]


def token(email: str) -> str:
    email = (email or "").strip().lower()
    return base64.urlsafe_b64encode(email.encode()).decode().rstrip("=") + "." + _firma(email)


def email_de(tok: str) -> str:
    try:
        cuerpo, firma = tok.rsplit(".", 1)
        email = base64.urlsafe_b64decode(cuerpo + "=" * (-len(cuerpo) % 4)).decode()
    except Exception:  # noqa: BLE001
        return ""
    return email if "@" in email and hmac.compare_digest(_firma(email), firma) else ""


def url(email: str) -> str:
    base = (config.PUBLIC_BASE_URL or "").rstrip("/")
    return f"{base}/anfitrion/agenda/{token(email)}.ics"


def _ics(t: str) -> str:
    return str(t or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", " ")


@router.get("/anfitrion/agenda/{tok}.ics", include_in_schema=False)
def agenda(tok: str) -> Response:
    email = email_de(tok)
    if not email:
        return Response("No encontrada", status_code=404)
    canchas = datos.canchas_de_dueno(email)
    por_id = {c["id"]: c for c in canchas}
    hoy = date.today()
    filas = datos.reservas_de_canchas(list(por_id), (hoy - timedelta(days=7)).isoformat(),
                                      (hoy + timedelta(days=60)).isoformat()) if por_id else []
    ahora = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    ev = []
    for f in filas:
        c = por_id.get(f.get("cancha_id")) or {}
        try:
            from web.router import _pais_de
            tz = horarios.ahora_local(_pais_de(c) if c else "PE").tzinfo
            d = date.fromisoformat(str(f["fecha"]))
            hi = horarios.hora_en_minutos(f["hora_inicio"]) or 0
            hf = horarios.hora_en_minutos(f["hora_fin"]) or hi + 60
            if hf <= hi:
                hf += 24 * 60
            ini = datetime(d.year, d.month, d.day, tzinfo=tz) + timedelta(minutes=hi)
            fin = datetime(d.year, d.month, d.day, tzinfo=tz) + timedelta(minutes=hf)
        except (ValueError, TypeError, KeyError):
            continue
        pagado = "Pagada" if f.get("pagado") else "Cobrar en la cancha"
        jugador = f.get("jugador") or f.get("usuario") or "Jugador"
        desc = f"{jugador} · {f.get('telefono') or ''} · {f.get('moneda') or ''} {f.get('precio') or 0} · {pagado}"
        ev.append("BEGIN:VEVENT\r\n"
                  f"UID:{_ics(f.get('id'))}@{config.MARCA_DOMINIO}\r\nDTSTAMP:{ahora}\r\n"
                  f"DTSTART:{ini.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}\r\n"
                  f"DTEND:{fin.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}\r\n"
                  f"SUMMARY:{_ics(c.get('nombre') or 'Cancha')} · {_ics(jugador)}\r\n"
                  f"LOCATION:{_ics((c.get('club') or '').strip())}\r\n"
                  f"DESCRIPTION:{_ics(desc)}\r\nEND:VEVENT\r\n")
    body = (f"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//{_ics(MARCA)}//Agenda del local//ES\r\n"
            f"X-WR-CALNAME:{_ics(MARCA)} · Mis reservas\r\nX-PUBLISHED-TTL:PT1H\r\nCALSCALE:GREGORIAN\r\nMETHOD:PUBLISH\r\n"
            + "".join(ev) + "END:VCALENDAR\r\n")
    return Response(body, media_type="text/calendar; charset=utf-8", headers={"Cache-Control": "private, max-age=600"})


def tarjeta(email: str) -> str:
    """Caja para el Calendario web: el enlace privado + cómo agregarlo."""
    from web.ui import e
    u = url(email)
    return ("<details class='panel' style='margin-top:16px'><summary style='cursor:pointer;font-weight:700'>📆 Ver tus reservas en Google Calendar</summary>"
            "<p class='sub' style='margin-top:8px'>Copia este enlace privado y agrégalo en Google Calendar → «Otros calendarios» → «Desde URL» "
            "(o en Apple / Outlook como calendario suscrito). Se actualiza solo. No lo compartas: muestra tus reservas.</p>"
            f"<div style='display:flex;gap:8px;flex-wrap:wrap'><input id='agUrl' readonly value='{e(u)}' aria-label='Enlace de tu agenda' style='flex:1;min-width:0'>"
            "<button type='button' class='btn sec' onclick=\"navigator.clipboard&&navigator.clipboard.writeText(document.getElementById('agUrl').value)"
            ".then(function(){window.pcgToast&&pcgToast('Enlace copiado');})\">Copiar</button></div></details>")
