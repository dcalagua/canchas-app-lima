"""Centro de NOTIFICACIONES de la web (plan de mejoras ronda 2, P2-5).

Todos los avisos push que el backend y el APK mandan pasan por la tabla
`pichangol_avisos` (email, titulo, cuerpo, tipo, data, creado; un Database
Webhook los convierte en push). La web los lee de ahí: `/notificaciones`
lista los últimos 50 y el menú ☰ muestra cuántos son nuevos. "Leído" se
guarda en el navegador (`localStorage pcg_avisos_visto` = id del último visto),
sin columnas nuevas en la tabla.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from config import MARCA
from db import pg
from web import horarios, ui
from web.jugador_billetera import _email, _gate
from web.ui import e

router = APIRouter()

# tipo → (ícono, a dónde lleva tocarlo)
_DESTINO = {
    "reserva": ("📅", "/mis-reservas"), "reserva_manual": ("📅", "/mis-reservas"), "reserva_cancelada": ("📅", "/mis-reservas"),
    "espera": ("🔔", "/mis-reservas"), "puntos": ("⭐", "/mis-puntos"), "bono": ("🎟️", "/mis-bonos"),
    "reto": ("🎾", "/liga?tab=retos"), "partido": ("⚽", "/partidos"), "boleador": ("🥎", "/anfitrion/boleador"),
    "fotos_local": ("📷", "/anfitrion/mis-canchas"), "mensaje": ("💬", "/mensajes"), "pago": ("💳", "/mis-pagos"),
    "recarga": ("👛", "/mi-billetera"), "matricula": ("🎓", "/mis-clases"), "cuota": ("🎓", "/mis-clases"),
    "entrenador": ("🤖", ""), "bodega": ("🧃", "/mis-pedidos-bodega"), "venta": ("🛍️", "/mis-ordenes"),
}


def avisos_de(email: str, limite: int = 50) -> list[dict]:
    if not pg.habilitado or not email:
        return []
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id, titulo, cuerpo, coalesce(tipo,''), creado FROM pichangol_avisos "
                        "WHERE lower(email) = %s ORDER BY id DESC LIMIT %s", (email.strip().lower(), int(limite)))
            return [{"id": int(r[0]), "titulo": r[1] or "", "cuerpo": r[2] or "", "tipo": r[3], "creado": r[4]}
                    for r in cur.fetchall()]
    except Exception:  # noqa: BLE001
        return []


def nuevos(email: str, desde: int) -> int:
    if not pg.habilitado or not email:
        return 0
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM (SELECT 1 FROM pichangol_avisos WHERE lower(email) = %s AND id > %s LIMIT 99) x",
                        (email.strip().lower(), int(desde)))
            return int(cur.fetchone()[0])
    except Exception:  # noqa: BLE001
        return 0


def _hace(d) -> str:
    if not isinstance(d, datetime):
        return ""
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    s = (datetime.now(timezone.utc) - d).total_seconds()
    if s < 3600:
        return f"hace {max(1, int(s // 60))} min"
    if s < 86400:
        return f"hace {int(s // 3600)} h"
    if s < 7 * 86400:
        n = int(s // 86400)
        return f"hace {n} día{'s' if n != 1 else ''}"
    return horarios.fecha_larga(d.astimezone(horarios.ahora_local("PE").tzinfo).date().isoformat())


@router.get("/web/avisos/nuevos")
def ver_nuevos(request: Request, desde: int = 0):
    from web import sesion
    ses = sesion.de_request(request)
    if not ses or not ses.get("email"):
        return {"ok": False, "n": 0}
    return {"ok": True, "n": nuevos(_email(ses), desde)}


@router.get("/notificaciones", response_class=HTMLResponse)
def pagina_avisos(request: Request) -> HTMLResponse:
    ses, resp = _gate(request, "/notificaciones", "Notificaciones", "Tus avisos llegan al app.")
    if resp:
        return resp
    lst = avisos_de(_email(ses))
    if lst:
        items = ""
        for a in lst:
            ico, href = _DESTINO.get(a["tipo"], ("🔔", ""))
            cuerpo = (f"<span class='av-ic'>{ico}</span><span class='av-tx'><b>{e(a['titulo'])}</b>"
                      f"<span>{e(a['cuerpo'])}</span><small>{e(_hace(a['creado']))}</small></span>")
            items += (f"<a class='av-it' data-id='{a['id']}' href='{href}'>{cuerpo}<span class='av-chev'>›</span></a>" if href
                      else f"<div class='av-it' data-id='{a['id']}'>{cuerpo}</div>")
        lista = f"<div class='av-lista'>{items}</div>"
    else:
        lista = ("<div class='vacio' style='margin-top:24px'><div style='font-size:46px'>🔔</div><h3>Aún no tienes notificaciones</h3>"
                 "<p class='sub'>Aquí verás tus reservas confirmadas, turnos que se liberan, retos, pagos y más.</p></div>")
    ultimo = lst[0]["id"] if lst else 0
    cuerpo = (
        "<style>.av-lista{display:grid;gap:8px;margin-top:14px}"
        ".av-it{display:flex;gap:12px;align-items:flex-start;padding:14px;border:1px solid var(--trazo);border-radius:var(--r-sm);"
        "background:#fff;color:inherit;text-decoration:none}.av-it.nuevo{border-color:var(--esmeralda);background:var(--tinte)}"
        ".av-ic{font-size:22px;line-height:1.2}.av-tx{display:grid;gap:2px;min-width:0;flex:1}.av-tx span{color:var(--tenue);font-size:14px}"
        ".av-tx small{color:var(--tenue);font-size:12.5px}.av-chev{color:var(--tenue);font-size:20px;align-self:center}</style>"
        "<div style='max-width:720px;margin:0 auto;padding-top:18px'><h1 class='anf-hola' style='margin-top:6px'>Notificaciones</h1>"
        f"<p class='sub'>Los avisos de tu cuenta de {e(MARCA)}: los mismos que llegan a tu celular.</p>{lista}</div>"
        "<script>(function(){var v=0;try{v=parseInt(localStorage.getItem('pcg_avisos_visto')||'0',10)||0;}catch(e){}"
        "document.querySelectorAll('.av-it').forEach(function(a){if(+a.dataset.id>v)a.classList.add('nuevo');});"
        f"try{{localStorage.setItem('pcg_avisos_visto','{ultimo}');}}catch(e){{}}"
        "document.querySelectorAll('[data-badge-avisos]').forEach(function(b){b.hidden=true;});})();</script>")
    return ui.shell("Notificaciones", cuerpo, sesion=ses, titulo_tab=f"Notificaciones · {MARCA}")
