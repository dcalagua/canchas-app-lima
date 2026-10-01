"""PARTIDOS, PICHANGAS, REFERIDOS, CARNET y LLENAR CANCHA en la web: espejo
de las pantallas del app (fase 2-3 del lado jugador, pedido del director:
"en la web implementa las mismas funcionalidades que existen en el app").

· `/partidos` = `partidos_screen.dart` ("Match"): partidos abiertos que
  publica cualquier jugador en `pichangol_partidos`; el ROSTER y el chat son
  el GRUPO homónimo (`pichangol_grupos` + `pichangol_grupo_miembros`, mismo
  id), igual que `PartidosRepo`. Filtro por país (como el app: los que no
  tienen ubicación salen siempre), Me apunto con el cupo validado en el
  servidor (con candado de fila: dos a la vez no pasan del cupo), Salir,
  +1 cupo y Eliminar solo del creador, Coordinar = chat del grupo en
  `/mensajes`. Crear = `_CrearPartidoSheet` (deporte, sede con los locales
  conocidos, fecha, hora, total de jugadores con los atajos por deporte,
  título y nota opcionales). Arriba, el top-3 del Circuito (→ `/liga`) y el
  acceso a las pichangas de club.
· `/pichangas` = `convocatorias_screen.dart` + `convocatoria_detalle_screen`
  + `crear_convocatoria_screen` + `ranking_socios_screen`: llama como
  funciones a `convocatorias/service.py` (cupos, lista de espera y los 3
  modos de asignación: orden de llegada, sorteo y equidad) con el correo de
  la SESIÓN. OJO: `/convocatorias` es la API JSON del APK (router con
  prefijo), por eso la web vive en `/pichangas` (el nombre que muestra el
  app). En el APK el "panel del dueño" depende de un login de club heredado
  que ya no existe (`sesionIniciada` nunca se enciende); aquí el admin de una
  pichanga es quien la creó o el dueño de un local con ese club (slug =
  `ConvocatoriasService.slugClub`), y solo un dueño con canchas crea.
· `/referidos` = `referidos_screen.dart`: código `PCGxxxxxx` (misma fórmula
  que `AppState.codigoReferido`), invitar por WhatsApp y cuántos usaron tu
  código (`pichangol_referidos`). El CANJE y el cobro del bono quedan en la
  app: el bono del app se acredita en el saldo LOCAL del teléfono (no en la
  billetera del backend), así que la web no puede darlo sin inventar plata.
· `/jugador/{ref}` = `perfil_global_screen.dart` (carnet): stats
  consolidadas de academias + retos (`AppState.perfilGlobalDe`), puesto en
  el ranking global del deporte, PRO, bio, desglose por academia, últimos
  partidos, Retar (misma acción que `/liga`) e imprimir el carnet. `ref` =
  correo cifrado de `jugador_liga.ref_de` (el navegador nunca ve correos).
· `/anfitrion/llenar` = `llenar_cancha_screen.dart` (dueño): horas LIBRES de
  hoy/mañana de una cancha, descuento REAL por slot
  (`pichangol_descuentos_slot`, el mismo que cobra la reserva), aviso por el
  chat de la cancha a los clientes con cuenta y WhatsApp a los demás.
"""

from __future__ import annotations

import json
import re
import time
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote

from fastapi import APIRouter, Body, Request
from fastapi.responses import HTMLResponse, JSONResponse

import config
import paises
from convocatorias import service as conv
from db import pg
from db.store import MODOS_ASIGNACION, stores
from web import catalogos, datos, horarios, sesion, ui
from web.jugador_liga import (DEPORTES, DEPORTES_ACTIVOS, DEPORTES_CIRCUITO, PUNTOS_DERROTA,
                              PUNTOS_VICTORIA, _fernet, aviso_push, avatar, datos_ranking,
                              deportes_con_ranking, mi_nombre, perfiles, ranking_global, ref_de,
                              sin_sesion)
from web.ui import PLAY_URL, e

router = APIRouter(tags=["web-jugador-partidos"])

_ID_PARTIDO = re.compile(r"^p_[0-9]{6,20}$")
_ID_CANCHA = re.compile(r"^[A-Za-z0-9_.\-]{1,120}$")
_HORA = re.compile(r"^([01][0-9]|2[0-3]):[0-5][0-9]$")
_MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "set", "oct", "nov", "dic"]
_DIAS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]


def _ses_o_401(request: Request):
    ses = sesion.de_request(request)
    if not ses:
        return None, JSONResponse({"ok": False, "error": "sesion_requerida", "mensaje": "Inicia sesión para continuar."}, status_code=401)
    return ses, None


def _low(s) -> str:
    return str(s or "").strip().lower()


def _etq(dep: str) -> str:
    return DEPORTES.get(dep, (dep.capitalize() if dep else "", ""))[0]


def _emo(dep: str) -> str:
    return DEPORTES.get(dep, ("", "🏅"))[1]


def _js(obj) -> str:
    return json.dumps(obj, ensure_ascii=False).replace("</", "<\\/")


def fecha_legible(fecha: str, hora: str = "") -> str:
    """`_fechaLegible` del app: "vie 18 jul · 20:00"."""
    try:
        d = date.fromisoformat(fecha)
        base = f"{_DIAS[d.weekday()]} {d.day} {_MESES[d.month - 1]}"
    except ValueError:
        base = fecha
    return f"{base} · {hora}" if hora else base


# JS común: POST con preloader, avisos con modales (nunca confirm/alert).
_JS_BASE = r"""
function jpPost(url, body, msg){
  pcgCargando(msg || 'Guardando…', {demora: 250});
  return fetch(url, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body || {})})
    .then(function(r){ return r.json().catch(function(){ return {ok: false}; }); })
    .then(function(j){ pcgCargando(false); return j || {ok: false}; })
    .catch(function(){ pcgCargando(false); return {ok: false, mensaje: 'Sin conexión. Revisa tu internet y reintenta.'}; });
}
function jpFallo(j, t){ pcgAvisar({titulo: t || 'No se pudo', mensaje: (j && j.mensaje) || 'Reintenta en un momento.', icono: '⚠️'}); }
function jpEsc(s){ return String(s == null ? '' : s).replace(/[&<>"']/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]; }); }
"""

_CSS = """
.jp-wrap{max-width:760px;margin:10px auto 70px;min-width:0}
.jp-wrap h1{font-size:28px;margin:4px 0 6px;letter-spacing:-.3px}
.jp-volver{color:#6a6a6a;text-decoration:none;font-size:14px}
.jp-hero{background:linear-gradient(135deg,#0B8A3E,#067A38);color:#fff;border-radius:22px;padding:20px;margin:8px 0 14px}
.jp-hero h1{color:#fff;margin:0 0 2px}
.jp-hero p{margin:0 0 12px;opacity:.92}
.jp-hero .jp-link{display:inline-flex;align-items:center;gap:8px;background:rgba(255,255,255,.18);color:#fff;text-decoration:none;font-weight:700;font-size:13.5px;border-radius:10px;padding:8px 12px;margin:0 8px 6px 0}
.jp-card{background:#fff;border:1px solid #EBEBEB;border-radius:18px;box-shadow:0 5px 14px rgba(0,0,0,.06);padding:16px;margin:0 0 14px;min-width:0}
.jp-top{display:flex;align-items:center;gap:12px;min-width:0}
.jp-dep{width:44px;height:44px;border-radius:50%;background:#EAF7EF;display:inline-flex;align-items:center;justify-content:center;font-size:22px;flex:none}
.jp-top .t{flex:1;min-width:0}
.jp-top .t b{display:block;font-size:16.5px;overflow-wrap:anywhere}
.jp-top .t small{color:#6a6a6a}
.jp-pill{display:inline-block;border-radius:999px;padding:5px 10px;font-weight:800;font-size:12px;white-space:nowrap}
.jp-pill.ok{background:#EAF7EF;color:#067A38}.jp-pill.gris{background:#EBEBEB;color:#6a6a6a}
.jp-pill.warn{background:#FFF6E0;color:#B7791F}.jp-pill.info{background:#EAF2FB;color:#1F5FA8}.jp-pill.bad{background:#FBEAEA;color:#C0392B}
.jp-lin{display:flex;gap:8px;color:#555;font-size:13.5px;margin:6px 0 0;min-width:0}
.jp-lin span:last-child{min-width:0;overflow-wrap:anywhere}
.jp-acc{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}
.jp-acc .btn{flex:1 1 auto}
.jp-vacio{text-align:center;color:#6a6a6a;padding:34px 12px}
.jp-vacio .em{font-size:54px;display:block;margin-bottom:8px}
.jp-vacio b{display:block;color:#0A1B3D;font-size:18px;margin-bottom:4px}
.jp-chips{display:flex;flex-wrap:wrap;gap:8px;margin:8px 0 12px}
.jp-chips .chip{max-width:100%;white-space:normal}
.jp-wrap.con-fab{padding-bottom:70px}
.pcg-dlg .caja .jp-fila .q{text-align:left}
.jp-fab{position:fixed;right:18px;bottom:calc(18px + env(safe-area-inset-bottom));z-index:30;box-shadow:0 8px 22px rgba(0,0,0,.18);border-radius:999px}
.jp-sec{font-weight:800;font-size:16px;margin:18px 0 8px}
.jp-barra{height:8px;border-radius:999px;background:#EBEBEB;overflow:hidden;margin:12px 0 8px}
.jp-barra i{display:block;height:100%;background:#0B8A3E;border-radius:999px}
.jp-barra.llena i{background:#F2C94C}
.jp-cupos{display:flex;flex-wrap:wrap;gap:6px 14px;align-items:center;font-size:13.5px}
.jp-cupos .der{margin-left:auto;font-weight:800}
.jp-banner{display:flex;gap:12px;align-items:flex-start;border-radius:14px;padding:14px;margin:12px 0}
.jp-banner .em{font-size:22px}
.jp-banner b{display:block}
.jp-banner small{display:block;opacity:.9}
.jp-fila{display:flex;align-items:center;gap:10px;padding:10px 0;border-top:1px solid #F0F0F0;min-width:0}
.jp-fila:first-child{border-top:0}
.jp-fila .q{flex:1;min-width:0}
.jp-fila .q b{display:block;overflow-wrap:anywhere}
.jp-fila .q small{color:#6a6a6a}
.jp-n{width:30px;height:30px;border-radius:50%;background:#EAF7EF;color:#067A38;font-weight:800;display:inline-flex;align-items:center;justify-content:center;flex:none}
.jp-av{width:36px;height:36px;border-radius:50%;object-fit:cover;flex:none;display:inline-flex;align-items:center;justify-content:center;background:#0E8F67;color:#fff;font-weight:800}
.jp-form label.l{display:block;font-weight:800;margin:16px 0 6px}
.jp-form .ayuda{color:#6a6a6a;font-size:12.5px;margin:-2px 0 6px}
.jp-form input[type=text],.jp-form select,.jp-form input[type=date]{width:100%;padding:12px;border:1px solid #E4E4E4;border-radius:12px;font:inherit;background:#fff}
.jp-step{display:flex;align-items:center;gap:12px;margin-top:8px}
.jp-step button{width:44px;height:44px;border-radius:50%;border:1px solid #E4E4E4;background:#fff;font-size:22px;cursor:pointer}
.jp-step b{flex:1;text-align:center;font-size:26px}
.jp-modo{display:flex;gap:12px;align-items:flex-start;border:1px solid #E4E4E4;border-radius:14px;padding:12px;margin:0 0 8px;cursor:pointer;background:#fff;width:100%;text-align:left;font:inherit}
.jp-modo.sel{border:1.5px solid #0B8A3E;background:#EAF7EF}
.jp-modo .em{font-size:22px}
.jp-modo b{display:block}
.jp-modo small{color:#555}
.jp-grid2{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}
.jp-stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin:12px 0}
.jp-stats div{background:#fff;border:1px solid #EBEBEB;border-radius:14px;padding:10px 6px;text-align:center;min-width:0}
.jp-stats b{display:block;font-size:20px}
.jp-stats small{color:#6a6a6a;font-size:11.5px}
.jp-carnet{background:linear-gradient(135deg,#067A38,#0A1B3D);color:#fff;border-radius:20px;padding:18px;display:flex;gap:14px;align-items:center;min-width:0}
.jp-carnet .jp-av{width:60px;height:60px;font-size:24px;background:#7CB518}
.jp-carnet b{font-size:19px;display:block;overflow-wrap:anywhere}
.jp-carnet small{opacity:.85;display:block}
.jp-pro{display:inline-block;background:#7CB518;color:#fff;font-weight:900;font-size:10px;border-radius:6px;padding:2px 7px;margin-left:6px;vertical-align:middle}
.jp-cod{font-size:30px;font-weight:900;letter-spacing:3px;margin:4px 0 12px}
.jp-slots{display:flex;flex-wrap:wrap;gap:8px}
.jp-slot{border:1px solid #E4E4E4;background:#fff;border-radius:12px;padding:8px 12px;cursor:pointer;font:inherit;text-align:center;min-width:84px}
.jp-slot b{display:block}
.jp-slot small{color:#6a6a6a}
.jp-slot.sel{background:#0B8A3E;border-color:#0B8A3E;color:#fff}
.jp-slot.sel small{color:#EAF7EF}
.jp-mini{display:flex;align-items:center;gap:8px;padding:4px 0;font-size:13.5px}
.jp-mini .nm{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-weight:600}
.jp-mini .pt{font-weight:900;color:#067A38}
.jp-bio{display:flex;gap:10px;padding:6px 0;font-size:14px}
.jp-bio small{display:block;color:#6a6a6a}
.pcg-dlg .caja .jp-chk{display:flex;align-items:center;gap:10px;padding:8px 0;border-top:1px solid #F0F0F0;cursor:pointer}
.pcg-dlg .caja .jp-chk input{width:auto;flex:none}
@media (max-width:600px){.jp-stats{grid-template-columns:repeat(2,minmax(0,1fr))}.jp-wrap h1{font-size:24px}}
@media print{.cab,header,footer,.jp-noprint,.pcg-app-banner,#abrirApp{display:none!important}.jp-wrap{margin:0}}
"""


# ════════════════════════════ PARTIDOS ABIERTOS ═══════════════════════════════

def _fila_partido(cols, f) -> dict:
    d = dict(zip(cols, f))
    return {"id": str(d.get("id") or ""), "creador_email": _low(d.get("creador_email")),
            "creador_nombre": str(d.get("creador_nombre") or ""), "deporte": str(d.get("deporte") or "futbol"),
            "titulo": str(d.get("titulo") or ""), "fecha": str(d.get("fecha") or ""), "hora": str(d.get("hora") or ""),
            "sede": str(d.get("sede_nombre") or ""),
            "lat": float(d["lat"]) if d.get("lat") is not None else None,
            "lng": float(d["lng"]) if d.get("lng") is not None else None,
            "cupos": int(d.get("cupos") or 10), "nota": str(d.get("nota") or ""),
            "jugadores": [], "nombres": []}


_COLS_P = ["id", "creador_email", "creador_nombre", "deporte", "titulo", "fecha", "hora", "sede_nombre",
           "lat", "lng", "cupos", "nota"]


def _roster(cur, ids: list[str]) -> dict[str, list[tuple[str, str]]]:
    """Miembros por partido, en orden de llegada si la tabla tiene `creado`."""
    out: dict[str, list[tuple[str, str]]] = {}
    if not ids:
        return out
    try:
        cur.execute("SELECT grupo_id, email, nombre FROM pichangol_grupo_miembros WHERE grupo_id = ANY(%s) ORDER BY creado", (ids,))
    except Exception:  # noqa: BLE001  (base sin columna `creado`)
        cur.connection.rollback()
        cur.execute("SELECT grupo_id, email, nombre FROM pichangol_grupo_miembros WHERE grupo_id = ANY(%s)", (ids,))
    for gid, em, nom in cur.fetchall():
        if gid and em:
            out.setdefault(str(gid), []).append((_low(em), str(nom or "")))
    return out


def partidos_desde(hoy_iso: str) -> list[dict]:
    """`PartidosRepo.abiertos`: fecha de hoy en adelante, con su roster."""
    if not pg.habilitado:
        return []
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT {', '.join(_COLS_P)} FROM pichangol_partidos WHERE fecha >= %s ORDER BY fecha, hora", (hoy_iso,))
            ps = [_fila_partido(_COLS_P, f) for f in cur.fetchall()]
            ros = _roster(cur, [p["id"] for p in ps])
    except Exception:  # noqa: BLE001
        return []
    for p in ps:
        r = ros.get(p["id"], [])
        p["jugadores"] = [x[0] for x in r]
        p["nombres"] = [x[1] for x in r]
    return ps


def partido(pid: str) -> dict | None:
    if not pg.habilitado or not _ID_PARTIDO.match(pid or ""):
        return None
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT {', '.join(_COLS_P)} FROM pichangol_partidos WHERE id = %s", (pid,))
            f = cur.fetchone()
            if not f:
                return None
            p = _fila_partido(_COLS_P, f)
            r = _roster(cur, [pid]).get(pid, [])
    except Exception:  # noqa: BLE001
        return None
    p["jugadores"] = [x[0] for x in r]
    p["nombres"] = [x[1] for x in r]
    return p


def crear_partido(p: dict) -> bool:
    """`PartidosRepo.crear`: fila + grupo de chat homónimo (best-effort) + el
    creador como primer jugador."""
    if not pg.habilitado:
        return False
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO pichangol_partidos (id, creador_email, creador_nombre, deporte, titulo, fecha, hora, "
                        "sede_nombre, lat, lng, cupos, nota) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (p["id"], p["creador_email"], p["creador_nombre"], p["deporte"], p["titulo"], p["fecha"], p["hora"],
                         p["sede"], p.get("lat"), p.get("lng"), p["cupos"], p["nota"]))
            cur.execute("SAVEPOINT g")
            try:
                cur.execute("INSERT INTO pichangol_grupos (id, nombre, creador_email) VALUES (%s, %s, %s)",
                            (p["id"], p["titulo"], p["creador_email"]))
            except Exception:  # noqa: BLE001
                cur.execute("ROLLBACK TO SAVEPOINT g")
            cur.execute("INSERT INTO pichangol_grupo_miembros (grupo_id, email, nombre) VALUES (%s, %s, %s) "
                        "ON CONFLICT (grupo_id, email) DO UPDATE SET nombre = EXCLUDED.nombre",
                        (p["id"], p["creador_email"], p["creador_nombre"]))
            conn.commit()
            return True
    except Exception:  # noqa: BLE001
        return False


def apuntarse(pid: str, email: str, nombre: str) -> str:
    """`PartidosRepo.apuntarse` con el cupo validado EN el servidor: la fila del
    partido se bloquea (FOR UPDATE), así dos que entran a la vez al último cupo
    no lo desbordan. 'ok' | 'lleno' | 'no_existe' | 'error'."""
    if not pg.habilitado:
        return "error"
    em = _low(email)
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT cupos FROM pichangol_partidos WHERE id = %s FOR UPDATE", (pid,))
            f = cur.fetchone()
            if not f:
                conn.rollback()
                return "no_existe"
            cupos = int(f[0] or 0)
            cur.execute("SELECT email FROM pichangol_grupo_miembros WHERE grupo_id = %s", (pid,))
            emails = [_low(x[0]) for x in cur.fetchall()]
            if em in emails:
                conn.rollback()
                return "ok"
            if cupos > 0 and len(emails) >= cupos:
                conn.rollback()
                return "lleno"
            cur.execute("INSERT INTO pichangol_grupo_miembros (grupo_id, email, nombre) VALUES (%s, %s, %s) "
                        "ON CONFLICT (grupo_id, email) DO UPDATE SET nombre = EXCLUDED.nombre", (pid, em, nombre))
            conn.commit()
            return "ok"
    except Exception:  # noqa: BLE001
        return "error"


def bajarse(pid: str, email: str) -> bool:
    if not pg.habilitado:
        return False
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM pichangol_grupo_miembros WHERE grupo_id = %s AND email = %s", (pid, _low(email)))
            conn.commit()
            return True
    except Exception:  # noqa: BLE001
        return False


def cambiar_cupos(pid: str, creador: str, cupos: int) -> bool:
    """Solo el CREADOR (el WHERE lo exige)."""
    if not pg.habilitado:
        return False
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE pichangol_partidos SET cupos = %s WHERE id = %s AND lower(creador_email) = %s",
                        (max(2, min(40, int(cupos))), pid, _low(creador)))
            n = cur.rowcount
            conn.commit()
            return n > 0
    except Exception:  # noqa: BLE001
        return False


def eliminar_partido(pid: str, creador: str) -> bool:
    """`PartidosRepo.eliminar` (solo el creador): partido + roster + grupo."""
    if not pg.habilitado:
        return False
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM pichangol_partidos WHERE id = %s AND lower(creador_email) = %s", (pid, _low(creador)))
            if cur.rowcount <= 0:
                conn.rollback()
                return False
            cur.execute("DELETE FROM pichangol_grupo_miembros WHERE grupo_id = %s", (pid,))
            cur.execute("DELETE FROM pichangol_grupos WHERE id = %s", (pid,))
            conn.commit()
            return True
    except Exception:  # noqa: BLE001
        return False


def locales_conocidos() -> dict[str, tuple[float, float]]:
    """Sedes para "¿Dónde se juega?" (= `Club.agrupar(todasLasCanchas)`): nombre
    del local → ubicación."""
    out: dict[str, tuple[float, float]] = {}
    for c in datos.canchas_publicas():
        n = (c.get("club") or c.get("nombre") or "").strip()
        if n and c.get("lat") is not None and c.get("lng") is not None and n not in out:
            out[n] = (float(c["lat"]), float(c["lng"]))
    return out


# Atajos "jugadores en total" por deporte (`_presetsDe`); incluye al creador.
PRESETS = {
    "tenis": [("Singles", 2), ("Dobles", 4)], "padel": [("Singles", 2), ("Dobles", 4)],
    "pickleball": [("Singles", 2), ("Dobles", 4)],
    "futbol": [("Fut 5", 10), ("Fut 6", 12), ("Fut 7", 14), ("Fut 8", 16), ("Fut 11", 22)],
    "voley": [("4 vs 4", 8), ("6 vs 6", 12)], "basquet": [("3 vs 3", 6), ("5 vs 5", 10)], "natacion": [],
}
_PAISES = [("PE", "Perú"), ("BO", "Bolivia"), ("EC", "Ecuador")]


def _pais_usuario(email: str) -> str:
    try:
        from web.jugador_billetera import pais_billetera
        return pais_billetera(email)[0]
    except Exception:  # noqa: BLE001
        return "PE"


def _preview_circuito() -> str:
    """`_CircuitoPreview`: top-3 del primer deporte de raqueta con ranking."""
    try:
        d = datos_ranking()
        deps = [x for x in deportes_con_ranking(d) if x in DEPORTES_CIRCUITO]
    except Exception:  # noqa: BLE001
        return ""
    if not deps:
        return ""
    top = ranking_global(d, deps[0])[:3]
    filas = "".join(
        f"<div class='jp-mini'><span>{['🥇', '🥈', '🥉'][i]}</span><span class='nm'>{e(f['nombre'] or 'Jugador')}"
        + ("<span class='jp-pro'>PRO</span>" if f["email"] and stores.pro_activo(f["email"]) else "")
        + f"</span><small>{f['pj']} PJ</small><span class='pt'>{f['puntos']} pts</span></div>" for i, f in enumerate(top))
    return (f"<a class='jp-card' href='/liga?deporte={deps[0]}' style='display:block;text-decoration:none;color:inherit'>"
            "<div class='jp-top'><span class='jp-dep'>🏆</span><div class='t'><b>Circuito Pichangol</b>"
            "<small>Ranking de tu ciudad · rétalos y sube</small></div><span style='font-size:22px;color:#6a6a6a'>›</span></div>"
            + (f"<div style='margin-top:8px'>{filas}</div>" if filas else "") + "</a>")


def _tarjeta_partido(p: dict, yo: str) -> str:
    from web.jugador_mensajes import clave_de, hilo_grupo
    apuntado = yo in p["jugadores"]
    creador = p["creador_email"] == yo
    n = len(p["jugadores"])
    lleno = n >= p["cupos"]
    faltan = max(0, p["cupos"] - n)
    chip = ("<span class='jp-pill gris'>Completo</span>" if lleno else f"<span class='jp-pill ok'>Faltan {faltan}</span>")
    lin = ""
    if p["sede"]:
        lin += f"<div class='jp-lin'><span>📍</span><span>{e(p['sede'])}</span></div>"
    lin += f"<div class='jp-lin'><span>👥</span><span>{n} de {p['cupos']} jugadores · {e(_etq(p['deporte']))}</span></div>"
    if p["nota"]:
        lin += f"<div class='jp-lin'><span>🗒️</span><span>{e(p['nota'])}</span></div>"
    if p["nombres"]:
        nombres = ", ".join(x.split(" ")[0] for x in p["nombres"][:12] if x) or ""
        if nombres:
            lin += f"<div class='jp-lin'><span>🙋</span><span>{e(nombres)}{'…' if len(p['nombres']) > 12 else ''}</span></div>"
    pid = e(p["id"])
    if apuntado:
        acc = f"<a class='btn' href='/mensajes/{quote(clave_de([hilo_grupo(p['id'])]), safe='')}'>💬 Coordinar</a>"
        if creador:
            acc += (f"<button type='button' class='btn sec' data-cupo='{pid}' data-n='{p['cupos'] + 1}'>+1 cupo</button>"
                    f"<button type='button' class='btn sec' style='color:#C0392B' data-eliminar='{pid}'>Eliminar</button>")
        else:
            acc += f"<button type='button' class='btn sec' data-salir='{pid}'>Salir</button>"
    else:
        acc = (f"<button type='button' class='btn' disabled style='background:#BDBDBD'>Completo</button>" if lleno
               else f"<button type='button' class='btn' data-apuntar='{pid}'>＋ Me apunto</button>")
    return (f"<div class='jp-card'><div class='jp-top'><span class='jp-dep'>{_emo(p['deporte'])}</span>"
            f"<div class='t'><b>{e(p['titulo'])}</b><small>{e(fecha_legible(p['fecha'], p['hora']))}</small></div>{chip}</div>"
            f"{lin}<div class='jp-acc'>{acc}</div></div>")


@router.get("/partidos", response_class=HTMLResponse)
def pagina_partidos(request: Request, pais: str = "") -> HTMLResponse:
    ses = sesion.de_request(request)
    if not ses:
        return sin_sesion(request, "/partidos", "Partidos", "Publicar y unirte a partidos")
    yo = _low(ses["email"])
    iso = pais if pais in dict(_PAISES) else _pais_usuario(yo)
    hoy = horarios.ahora_local(iso).date()
    lista = [p for p in partidos_desde(hoy.isoformat())
             if p["lat"] is None or p["lng"] is None or paises.pais_de_coordenadas(p["lat"], p["lng"]) == iso]
    chips = "".join(f"<a class='chip{' sel' if k == iso else ''}' href='/partidos?pais={k}'>{ui.bandera(k)} {n}</a>" for k, n in _PAISES)
    tarjetas = "".join(_tarjeta_partido(p, yo) for p in lista) or (
        "<div class='jp-vacio'><span class='em'>⚽</span><b>Todavía no hay partidos abiertos</b>"
        "¿Te falta gente para jugar? Publica tu partido con el botón “Crear partido” y deja que otros se apunten.</div>")
    locales = locales_conocidos()
    cfg = {"presets": PRESETS, "deportes": [[d, _etq(d), _emo(d)] for d in DEPORTES_ACTIVOS],
           "hoy": hoy.isoformat(), "max": (hoy + timedelta(days=90)).isoformat(),
           "dias": [[(hoy + timedelta(days=i)).isoformat(), "Hoy" if i == 0 else "Mañana" if i == 1 else fecha_legible((hoy + timedelta(days=i)).isoformat())] for i in range(7)]}
    opciones = "".join(f"<option value='{e(n)}'>" for n in sorted(locales)[:600])
    cuerpo = (f"<style>{_CSS}</style><div class='jp-wrap con-fab'><a class='jp-volver' href='/perfil'>‹ Perfil</a>"
              "<div class='jp-hero'><h1>Partidos</h1><p>Publica un partido y encuentra con quién jugar.</p>"
              "<a class='jp-link' href='/pichangas'>📅 Pichangas de mi club ›</a>"
              "<a class='jp-link' href='/liga'>🏆 Liga y retos ›</a></div>"
              + _preview_circuito()
              + f"<div class='jp-chips'>{chips}</div>{tarjetas}</div>"
              "<button type='button' class='btn jp-fab' onclick='jpCrear()'>＋ Crear partido</button>"
              f"<datalist id='jpSedes'>{opciones}</datalist>"
              f"<script>window.JP={_js(cfg)};</script><script>{_JS_BASE}{_JS_PARTIDOS}</script>")
    return ui.shell("Partidos", cuerpo, sesion=ses, titulo_tab="Partidos · Pichangol")


_JS_PARTIDOS = r"""
function jpHoras(){ var h = ''; for(var i = 6; i <= 23; i++){ ['00','30'].forEach(function(m){ var v = (i < 10 ? '0' : '') + i + ':' + m; h += "<option" + (v === '20:00' ? ' selected' : '') + ">" + v + "</option>"; }); } return h; }
var F = {dep: 'futbol', cupos: 10}, V = null;
function pintarPresets(){
  var ps = JP.presets[F.dep] || [], h = '';
  ps.forEach(function(p){ h += "<button type='button' class='chip" + (F.cupos === p[1] ? ' sel' : '') + "' data-pre='" + p[1] + "'>" + jpEsc(p[0]) + " (" + p[1] + ")</button>"; });
  var box = document.getElementById('jpPre'); if(box) box.innerHTML = h;
  var n = document.getElementById('jpN'); if(n) n.textContent = F.cupos;
  var f = document.getElementById('jpFaltan'); if(f) f.textContent = 'Tú ya cuentas como 1 · te faltan ' + (F.cupos - 1);
}
window.jpCrear = function(reusar){
  if(!reusar){ F = {dep: 'futbol', cupos: 10}; V = null; }
  var deps = JP.deportes.map(function(d){ return "<button type='button' class='chip" + (d[0] === F.dep ? ' sel' : '') + "' data-dep='" + d[0] + "'>" + d[2] + ' ' + jpEsc(d[1]) + "</button>"; }).join('');
  var dias = JP.dias.map(function(d){ return "<button type='button' class='chip' data-dia='" + d[0] + "'>" + jpEsc(d[1]) + "</button>"; }).join('');
  var html = "<div class='jp-form' style='text-align:left'>"
    + "<label class='l'>Deporte</label><div class='jp-chips' id='jpDeps'>" + deps + "</div>"
    + "<label class='l'>¿Dónde se juega?</label><input type='text' id='jpSede' list='jpSedes' maxlength='80' placeholder='Cancha o lugar (ej.: La Molina)'>"
    + "<label class='l'>Fecha</label><div class='jp-chips' id='jpDias'>" + dias + "</div>"
    + "<input type='date' id='jpFecha' min='" + JP.hoy + "' max='" + JP.max + "'>"
    + "<label class='l'>Hora</label><select id='jpHora'>" + jpHoras() + "</select>"
    + "<label class='l'>Jugadores en total</label><div class='ayuda' id='jpFaltan'></div><div class='jp-chips' id='jpPre'></div>"
    + "<div class='jp-step'><button type='button' data-paso='-1' aria-label='Menos'>−</button><b id='jpN'></b><button type='button' data-paso='1' aria-label='Más'>+</button></div>"
    + "<label class='l'>Título (opcional)</label><input type='text' id='jpTit' maxlength='60' placeholder='Ej.: Fulbito de los viernes'>"
    + "<label class='l'>Nota (opcional)</label><input type='text' id='jpNota' maxlength='160' placeholder='Nivel, si traer pechera, cómo se paga la cancha…'>"
    + "</div>";
  pcgConfirmar({titulo: 'Nuevo partido', icono: '⚽', html: html, confirmar: 'Publicar partido', cancelar: 'Cancelar'}).then(function(ok){
    if(!ok) return;
    V = {sede: document.getElementById('jpSede').value, fecha: document.getElementById('jpFecha').value, hora: document.getElementById('jpHora').value,
      tit: document.getElementById('jpTit').value, nota: document.getElementById('jpNota').value};
    var body = {deporte: F.dep, sede: V.sede, fecha: V.fecha, hora: V.hora, cupos: F.cupos, titulo: V.tit, nota: V.nota};
    jpPost('/web/partidos/crear', body, 'Publicando…').then(function(j){
      if(j.ok){ pcgToast('¡Partido publicado! Ya pueden apuntarse.'); pcgRecargar('Actualizando…'); return; }
      if(j.error === 'sesion_requerida'){ jpFallo(j); return; }
      pcgAvisar({titulo: 'Falta un dato', icono: '⚠️', mensaje: j.mensaje || 'Reintenta en un momento.', confirmar: 'Corregir'}).then(function(){ jpCrear(true); });
    });
  });
  setTimeout(function(){
    pintarPresets();
    document.querySelectorAll('#jpDeps .chip').forEach(function(c){ c.classList.toggle('sel', c.dataset.dep === F.dep); });
    if(V){ document.getElementById('jpSede').value = V.sede; document.getElementById('jpFecha').value = V.fecha; document.getElementById('jpHora').value = V.hora;
      document.getElementById('jpTit').value = V.tit; document.getElementById('jpNota').value = V.nota; }
    document.querySelectorAll('#jpDias .chip').forEach(function(c){ c.classList.toggle('sel', !!V && c.dataset.dia === V.fecha); });
  }, 0);
};
document.addEventListener('click', function(ev){
  var t;
  if((t = ev.target.closest('[data-dep]'))){ F.dep = t.dataset.dep; var ps = JP.presets[F.dep] || []; if(ps.length) F.cupos = ps[0][1];
    document.querySelectorAll('#jpDeps .chip').forEach(function(c){ c.classList.toggle('sel', c === t); }); pintarPresets(); return; }
  if((t = ev.target.closest('[data-pre]'))){ F.cupos = +t.dataset.pre; pintarPresets(); return; }
  if((t = ev.target.closest('[data-paso]'))){ F.cupos = Math.max(2, Math.min(40, F.cupos + (+t.dataset.paso))); pintarPresets(); return; }
  if((t = ev.target.closest('[data-dia]'))){ document.getElementById('jpFecha').value = t.dataset.dia;
    document.querySelectorAll('#jpDias .chip').forEach(function(c){ c.classList.toggle('sel', c === t); }); return; }
  if((t = ev.target.closest('[data-apuntar]'))){
    jpPost('/web/partidos/' + t.dataset.apuntar + '/apuntarse', {}, 'Apuntándote…').then(function(j){
      if(j.ok){ pcgToast('¡Te apuntaste! Coordinen por el chat del partido.'); pcgRecargar('Actualizando…'); }
      else if(j.error === 'lleno') pcgAvisar({titulo: 'El partido ya se llenó', icono: '⛔', mensaje: j.mensaje}).then(function(){ pcgRecargar(); });
      else jpFallo(j);
    }); return; }
  if((t = ev.target.closest('[data-salir]'))){ var id = t.dataset.salir;
    pcgConfirmar({titulo: '¿Salir del partido?', icono: '🚪', mensaje: 'Dejas tu cupo libre para otro jugador.', confirmar: 'Salir', cancelar: 'Me quedo', destructivo: true}).then(function(ok){
      if(!ok) return; jpPost('/web/partidos/' + id + '/salir', {}, 'Saliendo…').then(function(j){ if(j.ok){ pcgToast('Te bajaste del partido.'); pcgRecargar(); } else jpFallo(j); });
    }); return; }
  if((t = ev.target.closest('[data-cupo]'))){ var n = +t.dataset.n;
    jpPost('/web/partidos/' + t.dataset.cupo + '/cupo', {cupos: n}, 'Ampliando…').then(function(j){ if(j.ok){ pcgToast('Cupo ampliado a ' + j.cupos + ' jugadores.'); pcgRecargar(); } else jpFallo(j); }); return; }
  if((t = ev.target.closest('[data-eliminar]'))){ var pid = t.dataset.eliminar;
    pcgConfirmar({titulo: '¿Eliminar el partido?', icono: '🗑️', mensaje: 'Se borra el partido y su chat de coordinación para todos.', confirmar: 'Eliminar', cancelar: 'Cancelar', destructivo: true}).then(function(ok){
      if(!ok) return; jpPost('/web/partidos/' + pid + '/eliminar', {}, 'Eliminando…').then(function(j){ if(j.ok){ pcgToast('Partido eliminado.'); pcgRecargar(); } else jpFallo(j); });
    }); return; }
});
"""


def validar_partido(b: dict, hoy: date) -> tuple[dict | None, str]:
    """Reglas de `_CrearPartidoSheet._publicar`."""
    dep = str(b.get("deporte") or "")
    if dep not in DEPORTES_ACTIVOS:
        return None, "Elige el deporte."
    fecha, hora = str(b.get("fecha") or ""), str(b.get("hora") or "")
    try:
        f = date.fromisoformat(fecha)
    except ValueError:
        return None, "Elige la fecha y la hora del partido."
    if not _HORA.match(hora):
        return None, "Elige la fecha y la hora del partido."
    if f < hoy or f > hoy + timedelta(days=90):
        return None, "La fecha debe ser desde hoy y hasta 90 días."
    sede = re.sub(r"\s+", " ", str(b.get("sede") or "")).strip()[:80]
    if not sede:
        return None, "¿Dónde se juega? Pon la cancha o el lugar."
    try:
        cupos = int(b.get("cupos") or 0)
    except (TypeError, ValueError):
        cupos = 0
    if not 2 <= cupos <= 40:
        return None, "El partido es de 2 a 40 jugadores."
    titulo = re.sub(r"\s+", " ", str(b.get("titulo") or "")).strip()[:60] or f"{_etq(dep)} · {sede}"
    nota = re.sub(r"\s+", " ", str(b.get("nota") or "")).strip()[:160]
    return {"deporte": dep, "fecha": fecha, "hora": hora, "sede": sede, "cupos": cupos, "titulo": titulo, "nota": nota}, ""


@router.post("/web/partidos/crear")
def crear(request: Request, body: dict = Body(default_factory=dict)) -> JSONResponse:
    ses, err = _ses_o_401(request)
    if err:
        return err
    yo = _low(ses["email"])
    hoy = horarios.ahora_local(_pais_usuario(yo)).date() - timedelta(days=1)  # tolerancia de zona horaria
    v, msg = validar_partido(body, hoy)
    if v is None:
        return JSONResponse({"ok": False, "mensaje": msg}, status_code=400)
    ubic = locales_conocidos().get(v["sede"])
    p = {**v, "id": f"p_{time.time_ns() // 1000}", "creador_email": yo, "creador_nombre": mi_nombre(ses),
         "lat": ubic[0] if ubic else None, "lng": ubic[1] if ubic else None}
    if not crear_partido(p):
        return JSONResponse({"ok": False, "mensaje": "No se pudo publicar. Reintenta."}, status_code=500)
    return JSONResponse({"ok": True, "id": p["id"]})


@router.post("/web/partidos/{pid}/apuntarse")
def web_apuntarse(request: Request, pid: str) -> JSONResponse:
    ses, err = _ses_o_401(request)
    if err:
        return err
    if not _ID_PARTIDO.match(pid):
        return JSONResponse({"ok": False, "mensaje": "Partido no encontrado."}, status_code=404)
    r = apuntarse(pid, ses["email"], mi_nombre(ses))
    if r == "ok":
        return JSONResponse({"ok": True})
    if r == "lleno":
        return JSONResponse({"ok": False, "error": "lleno", "mensaje": "Otro jugador tomó el último cupo. Pídele al creador que amplíe los cupos o busca otro partido."}, status_code=409)
    if r == "no_existe":
        return JSONResponse({"ok": False, "mensaje": "Este partido ya no existe."}, status_code=404)
    return JSONResponse({"ok": False, "mensaje": "No se pudo apuntar. Reintenta."}, status_code=500)


@router.post("/web/partidos/{pid}/salir")
def web_salir(request: Request, pid: str) -> JSONResponse:
    ses, err = _ses_o_401(request)
    if err:
        return err
    p = partido(pid)
    if p is None:
        return JSONResponse({"ok": False, "mensaje": "Partido no encontrado."}, status_code=404)
    if p["creador_email"] == _low(ses["email"]):
        return JSONResponse({"ok": False, "mensaje": "Eres quien organiza: amplía el cupo o elimina el partido."}, status_code=400)
    return JSONResponse({"ok": bajarse(pid, ses["email"])})


@router.post("/web/partidos/{pid}/cupo")
def web_cupo(request: Request, pid: str, body: dict = Body(default_factory=dict)) -> JSONResponse:
    ses, err = _ses_o_401(request)
    if err:
        return err
    p = partido(pid)
    if p is None or p["creador_email"] != _low(ses["email"]):
        return JSONResponse({"ok": False, "mensaje": "Solo quien organiza puede cambiar los cupos."}, status_code=404)
    try:
        n = max(2, min(40, int(body.get("cupos") or 0)))
    except (TypeError, ValueError):
        n = p["cupos"]
    if not cambiar_cupos(pid, ses["email"], n):
        return JSONResponse({"ok": False, "mensaje": "No se pudo ampliar el cupo."}, status_code=500)
    return JSONResponse({"ok": True, "cupos": n})


@router.post("/web/partidos/{pid}/eliminar")
def web_eliminar(request: Request, pid: str) -> JSONResponse:
    ses, err = _ses_o_401(request)
    if err:
        return err
    if not _ID_PARTIDO.match(pid) or not eliminar_partido(pid, ses["email"]):
        return JSONResponse({"ok": False, "mensaje": "Solo quien organiza puede eliminar el partido."}, status_code=404)
    return JSONResponse({"ok": True})


# ═══════════════════════════ PICHANGAS DE CLUB ════════════════════════════════

def slug_club(nombre: str) -> str:
    """`ConvocatoriasService.slugClub`."""
    n = (nombre or "").lower()
    for pat, rep in (("[áàä]", "a"), ("[éèë]", "e"), ("[íìï]", "i"), ("[óòö]", "o"), ("[úùü]", "u"), ("ñ", "n")):
        n = re.sub(pat, rep, n)
    s = re.sub(r"^_+|_+$", "", re.sub(r"[^a-z0-9]+", "_", n))
    return s or "club"


def mis_clubs(email: str) -> dict[str, dict]:
    """Locales del dueño: slug → {nombre, deportes}."""
    out: dict[str, dict] = {}
    for c in datos.canchas_de_dueno(email):
        nom = (c.get("club") or c.get("nombre") or "").strip()
        if not nom:
            continue
        g = out.setdefault(slug_club(nom), {"nombre": nom, "deportes": []})
        for d in ([c.get("deporte")] + list(c.get("deportes") or [])):
            if d and d not in g["deportes"]:
                g["deportes"].append(str(d))
    return out


def nombres_clubs() -> dict[str, str]:
    out: dict[str, str] = {}
    for c in datos.canchas_publicas():
        nom = (c.get("club") or c.get("nombre") or "").strip()
        if nom:
            out.setdefault(slug_club(nom), nom)
    return out


def _nombre_club(slug: str, nombres: dict[str, str]) -> str:
    return nombres.get(slug) or slug.replace("_", " ").strip().title() or "Club"


def es_admin(c: dict, email: str, clubs: dict[str, dict]) -> bool:
    """Admin de una pichanga = quien la creó o dueño de un local de ese club."""
    return _low(c.get("creado_por")) == _low(email) or str(c.get("club_id") or "") in clubs


def _conv(cid: int) -> dict | None:
    d = conv.detalle(cid)
    return d if d.get("ok") else None


_MODOS = {"orden_llegada": ("⏱️", "Orden de llegada", "El que se anota primero entra. Confirma al instante."),
          "sorteo": ("🎲", "Sorteo", "Ventana de inscripción; al cerrar se sortea de forma justa."),
          "equidad": ("⚖️", "Equidad", "Al cerrar prioriza a quien más quedó fuera y mejor asiste.")}
_CATEGORIAS = ["master", "menor", "libre"]


def _chip_modo(m: str) -> str:
    ico, nom, _ = _MODOS.get(m, _MODOS["orden_llegada"])
    return f"<span class='jp-pill ok'>{ico} {nom}</span>"


def _barra(total_conf: int, cupos: int, espera: int, libres: int, cerrada: bool) -> str:
    ratio = min(1.0, total_conf / (cupos or 1))
    lleno = libres == 0
    der = "" if cerrada else (f"<span class='der' style='color:{'#B7791F' if lleno else '#067A38'}'>{'Lista llena' if lleno else f'{libres} libres'}</span>")
    return (f"<div class='jp-barra{' llena' if lleno else ''}'><i style='width:{ratio * 100:.0f}%'></i></div>"
            f"<div class='jp-cupos'><span>👥 <b>{total_conf}/{cupos}</b> confirmados</span>"
            + (f"<span style='color:#6a6a6a'>⏳ {espera} en espera</span>" if espera else "") + der + "</div>")


def _mi_estado_chip(cid: int, yo: str) -> str:
    est = conv.estado_socio(cid, yo).get("estado_efectivo")
    return {"confirmado": "<span class='jp-pill ok'>✅ Estás dentro</span>",
            "lista_espera": "<span class='jp-pill warn'>⏳ En espera</span>",
            "en_bolsa": "<span class='jp-pill info'>🎲 En la bolsa</span>"}.get(est, "")


@router.get("/pichangas", response_class=HTMLResponse)
def pagina_pichangas(request: Request, club: str = "") -> HTMLResponse:
    """`ConvocatoriasScreen`: pichangas de los clubes; el jugador se anota, el
    dueño crea nuevas y ve el ranking de socios."""
    ses = sesion.de_request(request)
    if not ses:
        return sin_sesion(request, "/pichangas" + (f"?club={quote(club)}" if club else ""), "Pichangas", "Anotarte a las pichangas de tu club")
    yo = _low(ses["email"])
    clubs = mis_clubs(yo)
    nombres = nombres_clubs()
    for k, v in clubs.items():
        nombres.setdefault(k, v["nombre"])
    todas = conv.listar(club or None)
    slugs = sorted({c["club_id"] for c in conv.listar()}, key=lambda s: _nombre_club(s, nombres).lower())
    chips = ""
    if len(slugs) > 1 or club:
        chips = ("<div class='jp-chips'>" + f"<a class='chip{'' if club else ' sel'}' href='/pichangas'>Todos los clubes</a>"
                 + "".join(f"<a class='chip{' sel' if s == club else ''}' href='/pichangas?club={quote(s)}'>{e(_nombre_club(s, nombres))}</a>" for s in slugs)
                 + "</div>")
    tarj = ""
    for c in todas:
        cerrada = c.get("estado") == "cerrada"
        sub = [f"<span class='jp-pill {'gris' if cerrada else 'ok'}'>{'Cerrada' if cerrada else 'Abierta'}</span>"]
        if c.get("categoria"):
            sub.append(f"<span class='jp-pill info'>{e(str(c['categoria']).capitalize())}</span>")
        sub.append(_chip_modo(c.get("modo_efectivo") or ""))
        if c.get("fecha_partido"):
            sub.append(f"<span class='jp-pill gris'>📅 {e(c['fecha_partido'])}</span>")
        mio = _mi_estado_chip(int(c["id"]), yo)
        tarj += (f"<a class='jp-card' href='/pichangas/{int(c['id'])}' style='display:block;text-decoration:none;color:inherit'>"
                 f"<div class='jp-top'><span class='jp-dep'>{_emo(c.get('deporte') or 'futbol')}</span><div class='t'><b>{e(c.get('titulo') or 'Pichanga')}</b>"
                 f"<small>{e(_nombre_club(c.get('club_id') or '', nombres))}</small></div>{mio}</div>"
                 f"<div class='jp-chips' style='margin:10px 0 0'>{''.join(sub)}</div>"
                 + _barra(int(c.get("confirmados_n") or 0), int(c.get("cupos") or 0), int(c.get("espera_n") or 0),
                          int(c.get("cupos_libres") or 0), cerrada) + "</a>")
    if not tarj:
        tarj = ("<div class='jp-vacio'><span class='em'>⚽</span><b>Aún no hay pichangas</b>"
                + ("Crea la primera convocatoria de tu club." if clubs else "Cuando el club abra una convocatoria, aparecerá acá.") + "</div>")
    acciones = ""
    if clubs:
        acciones = "<div class='jp-acc jp-noprint'><a class='btn' href='/pichangas/nueva" + (f"?club={quote(club)}" if club in clubs else "") + "'>＋ Nueva pichanga</a>"
        rk = club if club in clubs else next(iter(clubs))
        acciones += f"<a class='btn sec' href='/pichangas/ranking?club={quote(rk)}'>📊 Ranking de socios</a></div>"
    titulo_club = f"<p class='sub' style='margin:0'>{e(_nombre_club(club, nombres))}</p>" if club else ""
    cuerpo = (f"<style>{_CSS}</style><div class='jp-wrap'><a class='jp-volver' href='/partidos'>‹ Partidos</a>"
              f"<h1>Pichangas</h1>{titulo_club}<p class='sub'>Convocatorias de club con cupos y lista de espera: te anotas y sabes al toque si entras.</p>"
              f"{acciones}{chips}{tarj}</div>")
    return ui.shell("Pichangas", cuerpo, sesion=ses, titulo_tab="Pichangas · Pichangol")


@router.get("/pichangas/nueva", response_class=HTMLResponse)
def pagina_nueva_pichanga(request: Request, club: str = "") -> HTMLResponse:
    """`CrearConvocatoriaScreen`: todo por selección (local, deporte, categoría,
    cupos, fecha, modo); solo el título se escribe."""
    ses = sesion.de_request(request)
    if not ses:
        return sin_sesion(request, "/pichangas/nueva", "Nueva pichanga", "Crear convocatorias")
    clubs = mis_clubs(ses["email"])
    if not clubs:
        cuerpo = (f"<style>{_CSS}</style><div class='jp-wrap'><a class='jp-volver' href='/pichangas'>‹ Pichangas</a>"
                  "<div class='jp-vacio'><span class='em'>🏟️</span><b>Las pichangas las organiza el club</b>"
                  "Para convocar necesitas un local registrado a tu nombre.<div class='jp-acc' style='justify-content:center'>"
                  "<a class='btn' href='/anfitrion/nueva'>Registrar mi cancha</a></div></div></div>")
        return ui.shell("Nueva pichanga", cuerpo, sesion=ses)
    sel = club if club in clubs else next(iter(clubs))
    hoy = horarios.ahora_local("PE").date()
    cfg = {"clubs": {k: v for k, v in clubs.items()}, "club": sel,
           "dias": [[(hoy + timedelta(days=i)).isoformat(), "Hoy" if i == 0 else "Mañana" if i == 1 else fecha_legible((hoy + timedelta(days=i)).isoformat())] for i in range(21)],
           "min": (hoy - timedelta(days=1)).isoformat(), "max": (hoy + timedelta(days=120)).isoformat(),
           "etq": {d: [_etq(d), _emo(d)] for d in DEPORTES}}
    locales = "".join(f"<button type='button' class='chip{' sel' if k == sel else ''}' data-club='{e(k)}'>{e(v['nombre'])}</button>" for k, v in clubs.items())
    cats = "".join(f"<button type='button' class='chip{' sel' if c == 'master' else ''}' data-cat='{c}'>{c.capitalize()}</button>" for c in _CATEGORIAS)
    cupos = "".join(f"<button type='button' class='chip{' sel' if n == 14 else ''}' data-cupos='{n}'>{n}</button>" for n in (10, 12, 14, 16, 18, 22))
    modos = "".join(f"<button type='button' class='jp-modo{' sel' if k == 'orden_llegada' else ''}' data-modo='{k}'><span class='em'>{ico}</span>"
                    f"<span><b>{nom}</b><small>{d}</small></span></button>" for k, (ico, nom, d) in _MODOS.items())
    cuerpo = (f"<style>{_CSS}</style><div class='jp-wrap jp-form'><a class='jp-volver' href='/pichangas'>‹ Pichangas</a><h1>Nueva pichanga</h1>"
              f"<label class='l'>Local</label><div class='jp-chips' id='npClubs'>{locales}</div>"
              "<label class='l'>Título</label><input type='text' id='npTit' maxlength='60' value='Fulbito' placeholder='Ej. Fulbito Máster'>"
              "<label class='l'>Deporte</label><div class='jp-chips' id='npDeps'></div>"
              f"<label class='l'>Categoría</label><div class='jp-chips' id='npCats'>{cats}</div>"
              f"<label class='l'>Cupos</label><div class='jp-chips' id='npCupos'>{cupos}</div>"
              "<div class='jp-step'><button type='button' data-np='-1' aria-label='Menos'>−</button><b id='npN'>14</b><button type='button' data-np='1' aria-label='Más'>+</button></div>"
              "<label class='l'>Fecha del partido (opcional)</label><div class='jp-chips' id='npDias'></div>"
              "<label class='l'>¿Cómo se reparten los cupos?</label><p class='ayuda'>Elige el modo para esta pichanga. Puedes usar uno distinto en cada una.</p>"
              f"<div id='npModos'>{modos}</div>"
              "<div class='jp-acc'><button type='button' class='btn' id='npGo'>✓ Crear convocatoria</button></div></div>"
              f"<script>window.NP={_js(cfg)};</script><script>{_JS_BASE}{_JS_NUEVA}</script>")
    return ui.shell("Nueva pichanga", cuerpo, sesion=ses, titulo_tab="Nueva pichanga · Pichangol")


_JS_NUEVA = r"""
var S = {club: NP.club, dep: '', cat: 'master', cupos: 14, fecha: '', modo: 'orden_llegada'};
function deps(){
  var ds = (NP.clubs[S.club] || {}).deportes || []; if(!ds.length) ds = ['futbol'];
  if(ds.indexOf(S.dep) < 0) S.dep = ds.indexOf('futbol') >= 0 ? 'futbol' : ds[0];
  document.getElementById('npDeps').innerHTML = ds.map(function(d){ var t = NP.etq[d] || [d, '🏅']; return "<button type='button' class='chip" + (d === S.dep ? ' sel' : '') + "' data-dep='" + jpEsc(d) + "'>" + t[1] + ' ' + jpEsc(t[0]) + "</button>"; }).join('');
}
function dias(){
  document.getElementById('npDias').innerHTML = "<button type='button' class='chip" + (S.fecha ? '' : ' sel') + "' data-dia=''>Sin fecha</button>"
    + NP.dias.map(function(d){ return "<button type='button' class='chip" + (d[0] === S.fecha ? ' sel' : '') + "' data-dia='" + d[0] + "'>" + jpEsc(d[1]) + "</button>"; }).join('');
}
function marcar(box, attr, val){ document.querySelectorAll('#' + box + ' [data-' + attr + ']').forEach(function(b){ b.classList.toggle('sel', b.dataset[attr] === String(val)); }); }
deps(); dias();
document.addEventListener('click', function(ev){
  var t;
  if((t = ev.target.closest('[data-club]'))){ S.club = t.dataset.club; marcar('npClubs', 'club', S.club); deps(); return; }
  if((t = ev.target.closest('#npDeps [data-dep]'))){ S.dep = t.dataset.dep; marcar('npDeps', 'dep', S.dep); return; }
  if((t = ev.target.closest('[data-cat]'))){ S.cat = t.dataset.cat; marcar('npCats', 'cat', S.cat); return; }
  if((t = ev.target.closest('[data-cupos]'))){ S.cupos = +t.dataset.cupos; document.getElementById('npN').textContent = S.cupos; marcar('npCupos', 'cupos', S.cupos); return; }
  if((t = ev.target.closest('[data-np]'))){ S.cupos = Math.max(2, Math.min(60, S.cupos + (+t.dataset.np))); document.getElementById('npN').textContent = S.cupos; marcar('npCupos', 'cupos', S.cupos); return; }
  if((t = ev.target.closest('#npDias [data-dia]'))){ S.fecha = t.dataset.dia; dias(); return; }
  if((t = ev.target.closest('[data-modo]'))){ S.modo = t.dataset.modo; document.querySelectorAll('.jp-modo').forEach(function(b){ b.classList.toggle('sel', b === t); }); return; }
});
document.getElementById('npGo').addEventListener('click', function(){
  var body = {club: S.club, titulo: document.getElementById('npTit').value, deporte: S.dep, categoria: S.cat, cupos: S.cupos, fecha: S.fecha, modo: S.modo};
  jpPost('/web/pichangas/crear', body, 'Creando convocatoria…').then(function(j){
    if(j.ok) pcgIr('/pichangas/' + j.id, 'Abriendo…'); else jpFallo(j, 'No se pudo crear');
  });
});
"""


def fecha_partido_texto(iso: str) -> str | None:
    """`_fechaTexto` del app: "Jue 18 sep"."""
    try:
        f = date.fromisoformat(iso)
    except ValueError:
        return None
    dias = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
    meses = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
    return f"{dias[f.weekday()]} {f.day} {meses[f.month - 1]}"


@router.post("/web/pichangas/crear")
def crear_pichanga(request: Request, body: dict = Body(default_factory=dict)) -> JSONResponse:
    ses, err = _ses_o_401(request)
    if err:
        return err
    yo = _low(ses["email"])
    clubs = mis_clubs(yo)
    club = str(body.get("club") or "")
    if club not in clubs:
        return JSONResponse({"ok": False, "mensaje": "Solo el dueño de un local puede convocar en su club."}, status_code=403)
    titulo = re.sub(r"\s+", " ", str(body.get("titulo") or "")).strip()[:60]
    if not titulo:
        return JSONResponse({"ok": False, "mensaje": "Ponle un título."}, status_code=400)
    dep = str(body.get("deporte") or "futbol")
    if dep not in DEPORTES:
        dep = "futbol"
    cat = str(body.get("categoria") or "master")
    if cat not in _CATEGORIAS:
        return JSONResponse({"ok": False, "mensaje": "Elige la categoría."}, status_code=400)
    try:
        cupos = int(body.get("cupos") or 0)
    except (TypeError, ValueError):
        cupos = 0
    if not 1 <= cupos <= 60:
        return JSONResponse({"ok": False, "mensaje": "Elige el número de cupos."}, status_code=400)
    modo = str(body.get("modo") or "orden_llegada")
    if modo not in MODOS_ASIGNACION:
        return JSONResponse({"ok": False, "mensaje": "Elige cómo se reparten los cupos."}, status_code=400)
    fecha = str(body.get("fecha") or "")
    d = conv.crear(club, titulo, dep, cupos, categoria=cat, fecha_partido=fecha_partido_texto(fecha) if fecha else None,
                   modo_asignacion=modo, creado_por=yo)
    if not d.get("ok"):
        return JSONResponse({"ok": False, "mensaje": "No se pudo crear la convocatoria."}, status_code=500)
    return JSONResponse({"ok": True, "id": d["convocatoria"]["id"]})


@router.get("/pichangas/ranking", response_class=HTMLResponse)
def pagina_ranking_socios(request: Request, club: str = "") -> HTMLResponse:
    """`RankingSociosScreen`: recurrencia por socio (solo el admin del club)."""
    ses = sesion.de_request(request)
    if not ses:
        return sin_sesion(request, "/pichangas/ranking?club=" + quote(club), "Ranking de socios", "El ranking de socios")
    clubs = mis_clubs(ses["email"])
    mias = {str(c.get("club_id")) for c in conv.listar() if _low(c.get("creado_por")) == _low(ses["email"])}
    if club not in clubs and club not in mias:
        return HTMLResponse("", status_code=302, headers={"Location": "/pichangas"})
    nombres = nombres_clubs()
    nombres.update({k: v["nombre"] for k, v in clubs.items()})
    filas = conv.ranking_socios(club)
    medallas = {1: "#F2C94C", 2: "#B8C0C2", 3: "#CD9A6A"}
    html = ""
    for i, f in enumerate(filas, start=1):
        chips = (f"<span class='jp-pill ok'>⚽ {f['jugo']} jugó</span><span class='jp-pill info'>✍️ {f['inscripciones']} inscrito</span>"
                 + (f"<span class='jp-pill warn'>⏳ {f['lista_espera']} en espera</span>" if f["lista_espera"] else "")
                 + (f"<span class='jp-pill bad'>🚫 {f['no_show']} no-show</span>" if f["no_show"] else ""))
        html += (f"<div class='jp-fila'><span class='jp-n' style='background:{medallas.get(i, '#EAF7EF')}'>{i}</span>"
                 f"<div class='q'><b>{e(f['socio_nombre'] or 'Socio')}</b><div class='jp-chips' style='margin:6px 0 0'>{chips}</div></div></div>")
    if not html:
        html = ("<div class='jp-vacio'><span class='em'>📊</span><b>Todavía sin datos</b>"
                "El ranking se llena a medida que hay convocatorias y asistencia.</div>")
    else:
        html = f"<div class='jp-card'>{html}</div>"
    cuerpo = (f"<style>{_CSS}</style><div class='jp-wrap'><a class='jp-volver' href='/pichangas?club={quote(club)}'>‹ Pichangas</a>"
              f"<h1>Ranking de socios</h1><p class='sub'>{e(_nombre_club(club, nombres))} · Ordenado por partidos jugados</p>{html}</div>")
    return ui.shell("Ranking de socios", cuerpo, sesion=ses)


def _lista_inscritos(ins: list[dict], yo: str, posicion: bool, cerrada: bool) -> str:
    if not ins:
        return "<p class='sub'>Nadie todavía.</p>"
    h = ""
    for i, x in enumerate(ins, start=1):
        yo_ = _low(x.get("socio_id")) == yo
        extra = ""
        if cerrada and x.get("asistio") is True:
            extra = "<span class='jp-pill ok'>Asistió</span>"
        elif cerrada and x.get("asistio") is False:
            extra = "<span class='jp-pill bad'>No vino</span>"
        h += (f"<div class='jp-fila'><span class='jp-n'>{i if posicion else '✓'}</span><div class='q'><b>{e(x.get('socio_nombre') or 'Socio')}"
              f"{' (tú)' if yo_ else ''}</b></div>{extra}</div>")
    return h


@router.get("/pichangas/{cid}", response_class=HTMLResponse)
def pagina_pichanga(request: Request, cid: int) -> HTMLResponse:
    """`ConvocatoriaDetalleScreen`."""
    ses = sesion.de_request(request)
    if not ses:
        return sin_sesion(request, f"/pichangas/{cid}", "Pichanga", "Anotarte a la pichanga")
    yo = _low(ses["email"])
    d = _conv(cid)
    if d is None:
        cuerpo = (f"<style>{_CSS}</style><div class='jp-wrap'><div class='jp-vacio'><span class='em'>🔎</span><b>Esta pichanga no existe</b>"
                  "<div class='jp-acc' style='justify-content:center'><a class='btn' href='/pichangas'>Ver pichangas</a></div></div></div>")
        return ui.shell("Pichanga", cuerpo, sesion=ses)
    c = d["convocatoria"]
    cerrada = c.get("estado") == "cerrada"
    nombres = nombres_clubs()
    clubs = mis_clubs(yo)
    admin = es_admin(c, yo, clubs)
    mi = conv.estado_socio(cid, yo)
    est = mi.get("estado_efectivo")
    banner = {
        "confirmado": ("✅", "¡Estás dentro!", "Tu cupo está confirmado.", "#EAF7EF", "#067A38"),
        "lista_espera": ("⏳", "En lista de espera", f"Puesto {mi.get('posicion') or '-'}. Si alguien cancela, subes.", "#FFF6E0", "#B7791F"),
        "en_bolsa": ("🎲", "Anotado — en la bolsa", "Los cupos se definen al cerrar la inscripción.", "#EAF2FB", "#1F5FA8"),
    }.get(est, ("ℹ️", "No estás anotado", "La inscripción está cerrada." if cerrada else "Anótate mientras haya cupo.", "#F2F2F2", "#555"))
    anotado = est != "sin_inscripcion"
    if anotado:
        acc = ("<button type='button' class='btn sec' style='width:100%' disabled>🔒 Inscripción cerrada</button>" if cerrada
               else "<button type='button' class='btn sec' style='color:#C0392B;width:100%' data-pc='cancelar'>✕ Cancelar mi inscripción</button>")
    elif not cerrada:
        acc = "<button type='button' class='btn' style='width:100%' data-pc='inscribir'>✍️ Anotarme</button>"
    else:
        acc = ""
    panel = ""
    if admin:
        if not cerrada:
            panel = "<button type='button' class='btn' style='width:100%' data-pc='cerrar'>🔒 Cerrar inscripción y asignar cupos</button>"
        else:
            panel = ("<button type='button' class='btn' style='width:100%' data-pc='asistencia'>📋 Marcar asistencia</button>"
                     "<button type='button' class='btn sec' style='width:100%;margin-top:8px' data-pc='reabrir'>🔓 Reabrir inscripción</button>")
        panel = (f"<div class='jp-card' style='background:#FAFAF7'><b>🛡️ Panel del organizador</b>"
                 f"<p class='sub' style='margin:4px 0 10px'>Solo tú (y el dueño del local) ven este panel.</p>{panel}"
                 f"<a class='btn sec' style='width:100%;margin-top:8px' href='/pichangas/ranking?club={quote(str(c.get('club_id') or ''))}'>📊 Ranking de socios</a></div>")
    chips = [f"<span class='jp-pill {'gris' if cerrada else 'ok'}'>{'Cerrada' if cerrada else 'Abierta'}</span>"]
    if c.get("categoria"):
        chips.append(f"<span class='jp-pill info'>{e(str(c['categoria']).capitalize())}</span>")
    chips.append(_chip_modo(d.get("modo_efectivo") or ""))
    if c.get("fecha_partido"):
        chips.append(f"<span class='jp-pill gris'>📅 {e(c['fecha_partido'])}</span>")
    conf, esp = d["confirmados"], d["lista_espera"]
    modo = d.get("modo_efectivo") or "orden_llegada"
    t_conf = "Anotados (en la bolsa)" if (not cerrada and modo != "orden_llegada") else "Confirmados"
    asis = [{"id": i, "nombre": x.get("socio_nombre") or "Socio",
             "asistio": x.get("asistio") is not False} for i, x in enumerate(conf)] if admin and cerrada else []
    cfg = {"id": cid, "asis": asis}
    cuerpo = (f"<style>{_CSS}</style><div class='jp-wrap'><a class='jp-volver' href='/pichangas?club={quote(str(c.get('club_id') or ''))}'>‹ Pichangas</a>"
              f"<h1>{e(c.get('titulo') or 'Pichanga')}</h1><p class='sub' style='margin:0 0 8px'>{_emo(c.get('deporte') or 'futbol')} {e(_nombre_club(str(c.get('club_id') or ''), nombres))}</p>"
              f"<div class='jp-chips'>{''.join(chips)}</div><p class='sub'>{e(_MODOS.get(modo, _MODOS['orden_llegada'])[2])}</p>"
              + _barra(len(conf) if (cerrada or modo == 'orden_llegada') else 0, int(d.get("cupos") or 0), len(esp), int(d.get("cupos_libres") or 0), cerrada)
              + f"<div class='jp-banner' style='background:{banner[3]};color:{banner[4]}'><span class='em'>{banner[0]}</span><div><b>{banner[1]}</b><small>{e(banner[2])}</small></div></div>"
              f"{acc}<div style='height:12px'></div>{panel}"
              f"<div class='jp-sec'>✅ {t_conf} · {len(conf) if conf else 0}</div><div class='jp-card'>{_lista_inscritos(conf, yo, False, cerrada)}</div>"
              + (f"<div class='jp-sec'>⏳ {'Lista de espera' if (cerrada or modo == 'orden_llegada') else 'Anotados'} · {len(esp)}</div><div class='jp-card'>{_lista_inscritos(esp, yo, True, cerrada)}</div>" if esp else "")
              + f"</div><script>window.PC={_js(cfg)};</script><script>{_JS_BASE}{_JS_PICHANGA}</script>")
    return ui.shell(str(c.get("titulo") or "Pichanga"), cuerpo, sesion=ses, titulo_tab=f"{c.get('titulo') or 'Pichanga'} · Pichangol")


_JS_PICHANGA = r"""
var TXT = {
  cancelar: ['¿Cancelar tu inscripción?', 'Si te cancelas, tu cupo pasa al primero de la lista de espera.', 'Sí, cancelar', true, '✋'],
  cerrar: ['¿Cerrar la inscripción?', 'Se resolverá la asignación final según el modo y no se podrán anotar más socios.', 'Cerrar y asignar', false, '🔒'],
  reabrir: ['¿Reabrir la convocatoria?', 'Vuelve a estado abierto para recibir inscripciones.', 'Reabrir', false, '🔓']
};
function hacer(acc, body){
  jpPost('/web/pichangas/' + PC.id + '/' + acc, body || {}, acc === 'inscribir' ? 'Anotándote…' : 'Guardando…').then(function(j){
    if(j.ok){ pcgToast(j.mensaje || 'Listo.'); pcgRecargar('Actualizando…'); } else jpFallo(j);
  });
}
document.addEventListener('click', function(ev){
  var t = ev.target.closest('[data-pc]'); if(!t) return;
  var acc = t.dataset.pc;
  if(acc === 'inscribir'){ hacer('inscribir'); return; }
  if(acc === 'asistencia'){
    var h = "<div style='text-align:left'>" + PC.asis.map(function(a){ return "<label class='jp-chk'><input type='checkbox' data-as='" + a.id + "'" + (a.asistio ? ' checked' : '') + "> " + jpEsc(a.nombre) + "</label>"; }).join('') + "</div>";
    if(!PC.asis.length){ pcgAvisar({titulo: 'Sin confirmados', icono: 'ℹ️', mensaje: 'No hay socios confirmados para marcar.'}); return; }
    pcgConfirmar({titulo: '¿Quién vino?', icono: '📋', html: "<p>Marca a los que jugaron. Los que no, cuentan como no-show.</p>" + h, confirmar: 'Guardar asistencia', cancelar: 'Cancelar'}).then(function(ok){
      if(!ok) return;
      var marcas = PC.asis.map(function(a){ var c = document.querySelector("[data-as='" + a.id + "']"); return {i: a.id, asistio: c ? c.checked : a.asistio}; });
      hacer('asistencia', {marcas: marcas});
    });
    return;
  }
  var x = TXT[acc]; if(!x) return;
  pcgConfirmar({titulo: x[0], mensaje: x[1], confirmar: x[2], cancelar: 'No', destructivo: x[3], icono: x[4]}).then(function(ok){ if(ok) hacer(acc); });
});
"""


_ERRORES_CONV = {"convocatoria_cerrada": "La inscripción ya está cerrada.", "inscripcion_cerrada": "La inscripción ya cerró.",
                 "aun_no_abre": "La inscripción aún no abre.", "convocatoria_no_encontrada": "Esta pichanga ya no existe.",
                 "no_inscrito": "No estabas anotado."}


@router.post("/web/pichangas/{cid}/{accion}")
def accion_pichanga(request: Request, cid: int, accion: str, body: dict = Body(default_factory=dict)) -> JSONResponse:
    ses, err = _ses_o_401(request)
    if err:
        return err
    yo = _low(ses["email"])
    d = _conv(cid)
    if d is None:
        return JSONResponse({"ok": False, "mensaje": "Esta pichanga ya no existe."}, status_code=404)
    c = d["convocatoria"]
    if accion == "inscribir":
        r = conv.inscribir(cid, yo, mi_nombre(ses))
        if not r.get("ok"):
            return JSONResponse({"ok": False, "mensaje": _ERRORES_CONV.get(r.get("error"), "No se pudo anotar. Intenta de nuevo.")}, status_code=400)
        msg = {"confirmado": "¡Estás dentro! Cupo confirmado.",
               "lista_espera": f"Entraste a la lista de espera (puesto {r.get('posicion')}).",
               "en_bolsa": "Anotado. Los cupos se definen al cerrar la inscripción."}.get(r.get("estado_efectivo"), "Anotado.")
        return JSONResponse({"ok": True, "mensaje": msg, "estado": r.get("estado_efectivo")})
    if accion == "cancelar":
        r = conv.cancelar(cid, yo)
        if not r.get("ok"):
            return JSONResponse({"ok": False, "mensaje": _ERRORES_CONV.get(r.get("error"), "No se pudo cancelar.")}, status_code=400)
        _avisar_promovidos(d, conv.detalle(cid))
        return JSONResponse({"ok": True, "mensaje": "Inscripción cancelada."})
    if not es_admin(c, yo, mis_clubs(yo)):
        return JSONResponse({"ok": False, "mensaje": "Solo quien organiza la pichanga puede hacer esto."}, status_code=403)
    if accion == "cerrar":
        r = conv.cerrar(cid)
        if not r.get("ok"):
            return JSONResponse({"ok": False, "mensaje": "No se pudo cerrar."}, status_code=400)
        for x in r.get("confirmados") or []:
            aviso_push(x.get("socio_id") or "", "¡Estás dentro! ⚽", f"Tienes cupo en {c.get('titulo') or 'la pichanga'}.", "aviso")
        for i, x in enumerate(r.get("lista_espera") or [], start=1):
            aviso_push(x.get("socio_id") or "", "Quedaste en lista de espera ⏳",
                       f"{c.get('titulo') or 'Pichanga'}: puesto {i}. Si alguien cancela, subes.", "aviso")
        return JSONResponse({"ok": True, "mensaje": "Convocatoria cerrada. Cupos asignados."})
    if accion == "reabrir":
        r = conv.reabrir(cid)
        return JSONResponse({"ok": bool(r.get("ok")), "mensaje": "Convocatoria reabierta."})
    if accion == "asistencia":
        if c.get("estado") != "cerrada":
            return JSONResponse({"ok": False, "mensaje": "Primero cierra la inscripción."}, status_code=400)
        conf = d["confirmados"]
        marcas = []
        for m in body.get("marcas") or []:
            try:
                i = int(m.get("i"))
            except (TypeError, ValueError, AttributeError):
                continue
            if 0 <= i < len(conf):
                marcas.append({"socio_id": conf[i]["socio_id"], "asistio": bool(m.get("asistio"))})
        r = conv.marcar_asistencia(cid, marcas)
        return JSONResponse({"ok": bool(r.get("ok")), "mensaje": f"Asistencia guardada ({r.get('marcadas', 0)} socios)."})
    return JSONResponse({"ok": False, "mensaje": "Acción no válida."}, status_code=404)


def _avisar_promovidos(antes: dict, despues: dict) -> None:
    """Tras una cancelación en una pichanga CERRADA, el primero de la espera
    sube: se le avisa (push best-effort)."""
    if not despues.get("ok") or antes["convocatoria"].get("estado") != "cerrada":
        return
    previos = {x.get("socio_id") for x in antes.get("confirmados") or []}
    for x in despues.get("confirmados") or []:
        if x.get("socio_id") not in previos:
            aviso_push(x.get("socio_id") or "", "¡Te liberaron un cupo! ⚽",
                       f"Subiste de la lista de espera: juegas {antes['convocatoria'].get('titulo') or 'la pichanga'}.", "aviso")


# ════════════════════════════════ REFERIDOS ═══════════════════════════════════

BONO_REFERIDO = 10  # `AppState.bonoReferido` (en la moneda local)


def codigo_referido(email: str) -> str:
    """`AppState.codigoReferido`: hash de las unidades UTF-16 del correo."""
    em = _low(email)
    if not em:
        return ""
    h = 7
    u = em.encode("utf-16-le")
    for i in range(0, len(u), 2):
        h = (h * 31 + (u[i] | (u[i + 1] << 8))) & 0x7FFFFFFF
    dig = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    s = ""
    n = h
    while True:
        n, r = divmod(n, 36)
        s = dig[r] + s
        if n == 0:
            break
    s = s.rjust(6, "0")
    return "PCG" + s[-6:]


def invitados(codigo: str) -> tuple[int, int]:
    """(cuántos usaron el código, cuántos aún sin bono cobrado por el referidor)."""
    if not pg.habilitado or not codigo:
        return 0, 0
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT count(*), count(*) FILTER (WHERE NOT coalesce(referidor_dado,false)) "
                        "FROM pichangol_referidos WHERE referido_codigo = %s", (codigo.upper(),))
            n, p = cur.fetchone()
            return int(n or 0), int(p or 0)
    except Exception:  # noqa: BLE001
        return 0, 0


def mi_canje(email: str) -> str:
    """Código que canjeé yo (o '')."""
    if not pg.habilitado:
        return ""
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT referido_codigo FROM pichangol_referidos WHERE invitado_email = %s", (_low(email),))
            f = cur.fetchone()
            return str(f[0]) if f else ""
    except Exception:  # noqa: BLE001
        return ""


@router.get("/referidos", response_class=HTMLResponse)
def pagina_referidos(request: Request) -> HTMLResponse:
    """`ReferidosScreen` ("Invita y gana")."""
    ses = sesion.de_request(request)
    if not ses:
        return sin_sesion(request, "/referidos", "Invita y gana", "Tu código de referido")
    yo = _low(ses["email"])
    cod = codigo_referido(yo)
    n, pend = invitados(cod)
    canje = mi_canje(yo)
    iso = _pais_usuario(yo)
    sim = paises.simbolo_de_moneda(paises.moneda_de_pais(iso))
    msg = ("¡Juega conmigo en Pichangol! 🎾⚽\n\nReserva canchas de fútbol, tenis y más cerca de ti.\n"
           f"Usa mi código *{cod}* al registrarte y ambos ganamos un bono. 🎁\n\nDescárgala: {config.APP_DOWNLOAD_URL}")
    estado = (f"{n} {'persona ya usó' if n == 1 else 'personas ya usaron'} tu código." if n else "Aún nadie usó tu código. ¡Comparte y gana!")
    pend_html = (f"<div class='jp-banner' style='background:#FFF6E0;color:#8a5a00'><span class='em'>🎁</span><div><b>{pend} bono{'s' if pend != 1 else ''} por cobrar</b>"
                 "<small>Tus bonos por invitar se cobran al abrir “Invita y gana” en la app Pichangol.</small></div></div>") if pend else ""
    canje_html = (f"<div class='jp-banner' style='background:#EAF7EF;color:#067A38'><span class='em'>✅</span><div><b>Ya canjeaste el código {e(canje)}</b>"
                  "<small>Solo se puede canjear un código por cuenta.</small></div></div>") if canje else (
        "<div class='jp-card'><b>¿Tienes el código de un amigo?</b><p class='sub' style='margin:4px 0 10px'>El bono de bienvenida se acredita en el "
        "saldo de tu app, por eso el canje se hace desde la app Pichangol (Ajustes → Invita y gana). Solo puedes canjear un código una vez, y no el tuyo.</p>"
        "<button type='button' class='btn sec' onclick='rfApp()'>Canjear en la app <span class='pill gris'>En la app</span></button></div>")
    cuerpo = (f"<style>{_CSS}</style><div class='jp-wrap' style='max-width:600px'><a class='jp-volver' href='/perfil'>‹ Perfil</a>"
              "<h1>Invita y gana</h1>"
              "<div class='jp-hero' style='text-align:center;background:linear-gradient(135deg,#7CB518,#0B8A3E)'>"
              "<div style='font-size:40px'>🎁</div><p style='margin:6px 0 0'>Tu código</p>"
              f"<div class='jp-cod' id='rfCod'>{e(cod)}</div>"
              + ui.boton_whatsapp(msg, etiqueta="💬 Invitar por WhatsApp", clase="btn", extra="style='background:#fff;color:#0B8A3E;width:100%'")
              + "<button type='button' class='btn sec' style='margin-top:8px;width:100%;background:transparent;color:#fff;border-color:rgba(255,255,255,.6)' onclick='rfCopiar()'>⧉ Copiar código</button></div>"
              f"<p class='sub'>Comparte tu código. Cuando un amigo lo canjea al registrarse, {BONO_REFERIDO} {e(sim)} para cada uno. 🎁</p>"
              f"<div class='jp-banner' style='background:#EAF7EF;color:#14463A'><span class='em'>👥</span><div><b>{e(estado)}</b></div></div>"
              f"{pend_html}{canje_html}</div>"
              f"<script>window.RF={_js({'cod': cod, 'play': PLAY_URL})};</script><script>{_JS_BASE}"
              "window.rfCopiar=function(){ try{ navigator.clipboard.writeText(RF.cod).then(function(){ pcgToast('Código copiado'); }); }catch(_){ pcgToast(RF.cod); } };"
              "window.rfApp=function(){ pcgConfirmar({titulo: 'Canjea en la app', icono: '🎁', mensaje: 'Abre Pichangol → Ajustes → Invita y gana y escribe el código de tu amigo. El bono cae a tu saldo al instante.', confirmar: 'Abrir la app', cancelar: 'Ahora no'}).then(function(ok){ if(ok) window.open(RF.play, '_blank', 'noopener'); }); };"
              "</script>")
    return ui.shell("Invita y gana", cuerpo, sesion=ses, titulo_tab="Invita y gana · Pichangol")


# ═══════════════════════════ CARNET DEL JUGADOR ═══════════════════════════════

_PROMPTS_BIO = [("dedico", "💼", "Me dedico a"), ("juego_desde", "⏳", "Juego desde hace"),
                ("logro", "🏆", "Mi mayor logro deportivo"), ("estilo", "⚽", "Mi estilo de juego"),
                ("tiempo", "🕒", "Dedico demasiado tiempo a"), ("musica", "🎵", "Mi música para entrar en calor"),
                ("horario", "🌅", "Mi horario de juego"), ("idiomas", "🗣️", "Idiomas que hablo")]


def email_de_carnet(ref: str) -> str:
    """El carnet se comparte: el `ref` cifrado vale sin vencimiento (solo lectura;
    las ACCIONES usan refs frescos con TTL)."""
    try:
        v = _fernet().decrypt((ref or "").encode()).decode()
    except Exception:  # noqa: BLE001
        return ""
    return v if "@" in v else ""


def bio_de(email: str) -> dict[str, str]:
    if not pg.habilitado:
        return {}
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT bio FROM pichangol_perfiles WHERE lower(email) = %s", (_low(email),))
            f = cur.fetchone()
    except Exception:  # noqa: BLE001
        return {}
    b = f[0] if f else None
    if isinstance(b, str):
        try:
            b = json.loads(b)
        except ValueError:
            b = None
    return {str(k): str(v).strip() for k, v in (b or {}).items() if v is not None and str(v).strip()} if isinstance(b, dict) else {}


def _dt(v) -> datetime:
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return datetime.now(timezone.utc)


def perfil_global(email: str, d: dict) -> dict | None:
    """`AppState.perfilGlobalDe('e:correo')`: partidos de ranking de TODAS las
    academias + retos jugados; por academia, puntos 3/1 y últimos partidos."""
    em = _low(email)
    nombre = categoria = ""
    pj = pg_ = pp = 0
    por: dict[str, list[int]] = {}
    partidos: list[dict] = []
    for a in d.get("academias") or []:
        cats = a.get("categorias") or {}
        an = str(a.get("nombre") or "")
        for p in a.get("partidos") or []:
            for jid in (p.get("jugadorAId") or "", p.get("jugadorBId") or ""):
                if not jid:
                    continue
                pe = str((p.get("jugadorAEmail") if jid == p.get("jugadorAId") else p.get("jugadorBEmail")) or "")
                if _low(pe) != em:
                    continue
                gano = p.get("ganadorId") == jid
                pj += 1
                pg_ += gano
                pp += not gano
                r = por.setdefault(an, [0, 0, 0])
                r[0] += 1
                r[1 if gano else 2] += 1
                nom = str((p.get("jugadorANombre") if jid == p.get("jugadorAId") else p.get("jugadorBNombre")) or "")
                if nom:
                    nombre = nom
                if cats.get(jid):
                    categoria = str(cats[jid])
                rival = p.get("jugadorBId") if jid == p.get("jugadorAId") else p.get("jugadorAId")
                rn = str((p.get("jugadorANombre") if rival == p.get("jugadorAId") else p.get("jugadorBNombre")) or "")
                partidos.append({"fecha": _dt(p.get("fecha")), "academia": an, "gano": gano, "rival": rn,
                                 "marcador": str(p.get("marcador") or "")})
    for r in d.get("retos") or []:
        for side in ("retador", "retado"):
            if _low(r.get(f"{side}_email")) != em:
                continue
            otro = "retado" if side == "retador" else "retador"
            gano = _low(r.get("ganador_email")) == em
            pj += 1
            pg_ += gano
            pp += not gano
            rec = por.setdefault("Retos", [0, 0, 0])
            rec[0] += 1
            rec[1 if gano else 2] += 1
            if r.get(f"{side}_nombre"):
                nombre = str(r[f"{side}_nombre"])
            partidos.append({"fecha": _dt(r.get("creado_en")), "academia": "Reto", "gano": gano,
                             "rival": str(r.get(f"{otro}_nombre") or ""), "marcador": str(r.get("marcador") or "")})
    if pj == 0:
        return None
    partidos.sort(key=lambda x: x["fecha"], reverse=True)
    por_ac = sorted(({"academia": k, "pj": v[0], "pg": v[1], "pp": v[2], "puntos": v[1] * PUNTOS_VICTORIA + v[2] * PUNTOS_DERROTA}
                     for k, v in por.items()), key=lambda x: -x["puntos"])
    return {"nombre": nombre, "categoria": categoria, "email": em, "pj": pj, "pg": pg_, "pp": pp,
            "puntos": pg_ * PUNTOS_VICTORIA + pp * PUNTOS_DERROTA, "pct": (pg_ / pj * 100) if pj else 0.0,
            "por_academia": por_ac, "partidos": partidos}


@router.get("/jugador/{ref}", response_class=HTMLResponse)
def pagina_carnet(request: Request, ref: str, deporte: str = "") -> HTMLResponse:
    """`PerfilGlobalScreen`: carnet del jugador."""
    ses = sesion.de_request(request)
    if not ses:
        return sin_sesion(request, f"/jugador/{ref}" + (f"?deporte={quote(deporte)}" if deporte else ""), "Carnet del jugador", "El carnet del jugador")
    yo = _low(ses["email"])
    email = email_de_carnet(ref)
    d = datos_ranking() if email else {"academias": [], "retos": [], "campeonatos": []}
    p = perfil_global(email, d) if email else None
    if p is None:
        cuerpo = (f"<style>{_CSS}</style><div class='jp-wrap'><a class='jp-volver' href='/liga'>‹ Ranking</a>"
                  "<div class='jp-vacio'><span class='em'>🪪</span><b>Jugador no encontrado</b>Aún no tiene partidos en el ranking.</div></div>")
        return ui.shell("Carnet del jugador", cuerpo, sesion=ses)
    deps = deportes_con_ranking(d)
    pos = None
    dep = deporte if deporte in DEPORTES else ""
    for x in ([dep] if dep else deps):
        tabla = ranking_global(d, x)
        i = next((k for k, f in enumerate(tabla) if f["email"] == email), None)
        if i is not None:
            dep, pos = x, i + 1
            break
    dep = dep or (deps[0] if deps else "tenis")
    per = perfiles([email]).get(email) or {}
    nombre = p["nombre"] or per.get("nombre") or "Jugador"
    pro = stores.pro_activo(email)
    bio = bio_de(email)
    primer = nombre.split(" ")[0]
    stats = (f"<div class='jp-stats'><div><b style='color:#0A1B3D'>{p['puntos']}</b><small>Puntos</small></div>"
             f"<div><b>{p['pj']}</b><small>Jugados</small></div><div><b style='color:#0B8A3E'>{p['pg']}</b><small>Ganados</small></div>"
             f"<div><b style='color:#067A38'>{p['pct']:.0f}%</b><small>Efectividad</small></div></div>")
    acciones = ""
    if email != yo:
        acciones += (f"<button type='button' class='btn' style='width:100%' data-retar='{e(ref_de(email))}' data-nombre='{e(nombre)}' data-dep='{e(dep)}'>"
                     f"⚔️ Retar a {e(primer)}</button>")
    acciones += "<button type='button' class='btn sec' style='width:100%;margin-top:8px' onclick='window.print()'>🖨️ Guardar carnet (PDF)</button>"
    acciones += "<button type='button' class='btn sec' style='width:100%;margin-top:8px' onclick='jcCopiar()'>🔗 Copiar enlace del carnet</button>"
    acad = "".join(f"<div class='jp-fila'><span>{'⚔️' if r['academia'] == 'Retos' else '🎓'}</span><div class='q'><b>{e(r['academia'])}</b></div>"
                   f"<small style='color:#6a6a6a'>{r['pg']}G-{r['pp']}P</small><b style='color:#0B8A3E;margin-left:8px'>{r['puntos']} pts</b></div>"
                   for r in p["por_academia"])
    t_ac = f"Juega en {len(p['por_academia'])} academias" if len(p["por_academia"]) > 1 else "Academia"
    bio_h = "".join(f"<div class='jp-bio'><span>{ico}</span><div><small>{e(et)}</small>{e(bio[k])}</div></div>"
                    for k, ico, et in _PROMPTS_BIO if bio.get(k))
    ult = "".join(f"<div class='jp-fila'><span class='jp-pill {'ok' if x['gano'] else 'bad'}'>{'Ganó' if x['gano'] else 'Perdió'}</span>"
                  f"<div class='q'><b>vs {e(x['rival'] or 'Rival')}</b><small>{e(x['academia'])} · {x['fecha']:%d/%m/%Y}</small></div>"
                  + (f"<small style='color:#6a6a6a'>{e(x['marcador'])}</small>" if x["marcador"] else "") + "</div>"
                  for x in p["partidos"][:12])
    sub = f"Puesto #{pos} · {_etq(dep)}" if pos else _etq(dep)
    cuerpo = (f"<style>{_CSS}</style><div class='jp-wrap' style='max-width:640px'><a class='jp-volver jp-noprint' href='/liga?deporte={e(dep)}'>‹ Ranking</a>"
              "<h1>Carnet del jugador</h1>"
              f"<div class='jp-carnet'>{avatar(nombre, per.get('foto_url', ''), 'jp-av')}<div style='min-width:0'><b>{e(nombre)}</b>"
              f"<small>{e(sub)}{'<span class=jp-pro>PRO</span>' if pro else ''}</small>"
              + (f"<small>{e(p['categoria'])}</small>" if p["categoria"] else "") + "</div></div>"
              f"{stats}<div class='jp-noprint'>{acciones}</div>"
              f"<div class='jp-sec'>{e(t_ac)}</div><div class='jp-card'>{acad}</div>"
              + (f"<div class='jp-sec'>Acerca de {e(primer)}</div><div class='jp-card'>{bio_h}</div>" if bio_h else "")
              + f"<div class='jp-sec'>Últimos partidos</div><div class='jp-card'>{ult}</div>"
              "<p class='sub' style='text-align:center'>Ranking Global Pichangol</p></div>"
              f"<script>{_JS_BASE}{_JS_CARNET}</script>")
    return ui.shell(f"Carnet de {nombre}", cuerpo, sesion=ses, titulo_tab=f"{nombre} · Carnet Pichangol")


_JS_CARNET = r"""
window.jcCopiar = function(){ try{ navigator.clipboard.writeText(location.href).then(function(){ pcgToast('Enlace copiado'); }); }catch(_){ pcgToast('Copia el enlace de la barra del navegador'); } };
var enVuelo = false;
document.addEventListener('click', function(ev){
  var b = ev.target.closest('[data-retar]'); if(!b || enVuelo) return;
  pcgConfirmar({titulo: '¿Retar a ' + b.dataset.nombre + '?', icono: '⚔️', mensaje: 'Le llega el reto y un mensaje para coordinar cancha y horario. El resultado suma al ranking.', confirmar: 'Enviar reto', cancelar: 'Cancelar'}).then(function(ok){
    if(!ok) return; enVuelo = true;
    jpPost('/web/liga/retar', {ref: b.dataset.retar, nombre: b.dataset.nombre, deporte: b.dataset.dep, zona: ''}, 'Enviando reto…').then(function(j){
      enVuelo = false;
      if(j.ok) pcgAvisar({titulo: '¡Reto enviado!', icono: '⚔️', mensaje: j.mensaje}); else jpFallo(j, 'No se pudo retar');
    });
  });
});
"""


# ═══════════════════════════ LLENAR CANCHA (dueño) ════════════════════════════

def clientes_de(canchas: list[dict], hoy: date) -> list[dict]:
    """`AppState.clientesParaAvisar`: clientes de las reservas de MIS canchas
    (con correo → app; con teléfono → WhatsApp), deduplicados."""
    ids = [c["id"] for c in canchas]
    filas = datos.reservas_de_canchas(ids, (hoy - timedelta(days=365)).isoformat(), (hoy + timedelta(days=120)).isoformat())
    out: dict[str, dict] = {}
    for r in filas:
        em = _low(r.get("usuario"))
        tel = re.sub(r"\D", "", str(r.get("telefono") or ""))
        if not em and not tel:
            continue
        if str(r.get("medio_pago") or "") == "manual" and not em and not tel:
            continue
        k = em or f"t:{tel}"
        out.setdefault(k, {"nombre": (str(r.get("jugador") or "").strip() or "Cliente"), "email": em, "telefono": tel})
    return list(out.values())


def horas_libres(c: dict, base: date, ahora: datetime) -> list[str]:
    """`AppState.horasLibresDe`: slots de la sesión (hoy: los que aún no
    empiezan) sin reserva ni bloqueo, con la FECHA REAL de la madrugada."""
    desde = ahora.hour * 60 + ahora.minute if base == ahora.date() else None
    slots = horarios.slots(c.get("hora_apertura") or "07:00", c.get("hora_cierre") or "23:00", int(c.get("duracion_slot_min") or 60), desde)
    sig = (base + timedelta(days=1)).isoformat()
    ocup = datos.ocupados(c["id"], [base.isoformat(), sig])  # reservas vigentes + bloqueos
    libres = []
    for h in slots:
        fr = horarios.fecha_real(base.isoformat(), c.get("hora_apertura") or "", c.get("hora_cierre") or "", h)
        if (fr, h) in ocup:
            continue
        libres.append(h)
    return libres


def aplicar_descuento_slot(cancha_id: str, fecha: str, hora: str, pct: int) -> bool:
    """`DescuentosRepo.aplicar/quitar` (0 = quitar)."""
    if not pg.habilitado:
        return False
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            if pct <= 0:
                cur.execute("DELETE FROM pichangol_descuentos_slot WHERE cancha_id = %s AND fecha = %s AND hora = %s", (cancha_id, fecha, hora))
            else:
                cur.execute("INSERT INTO pichangol_descuentos_slot (cancha_id, fecha, hora, pct) VALUES (%s, %s, %s, %s) "
                            "ON CONFLICT (cancha_id, fecha, hora) DO UPDATE SET pct = EXCLUDED.pct",
                            (cancha_id, fecha, hora, max(1, min(90, int(pct)))))
            conn.commit()
            return True
    except Exception:  # noqa: BLE001
        return False


def texto_aviso(c: dict, nombre: str, horas: list[str], precios: list[int], dia: str, descuento: int, promo: str, sim: str) -> str:
    """`_texto` del app."""
    donde = f"{c['club']} · {c['nombre']}" if c.get("club") else c.get("nombre") or "mi cancha"
    off = f" 🔥 {descuento}% OFF" if descuento > 0 else ""
    desde = min(precios) if precios else 0
    extra = f"\n{promo}" if promo else ""
    return (f"¡Hola {nombre}! 🎾 Tengo libre {donde} {dia}: {', '.join(sorted(horas))} "
            f"(desde {sim} {desde}{off}). ¿La quieres? Resérvala en Pichangol o respóndeme por aquí.{extra}")


@router.get("/anfitrion/llenar", response_class=HTMLResponse)
def pagina_llenar(request: Request, cancha: str = "", dia: int = 0) -> HTMLResponse:
    from web.anfitrion import _cabecera, _contexto
    from web.router import _moneda_de, _pais_de
    ses, canchas, resp = _contexto(request, "/anfitrion/llenar")
    if resp is not None:
        return resp
    c = next((x for x in canchas if x["id"] == cancha), canchas[0])
    dia = 1 if dia == 1 else 0
    ahora = horarios.ahora_local(_pais_de(c))
    base = ahora.date() + timedelta(days=dia)
    sim = _moneda_de(c)[0]
    libres = horas_libres(c, base, ahora)
    desc = datos.descuentos(c["id"], [base.isoformat(), (base + timedelta(days=1)).isoformat()])
    slots = []
    for h in libres:
        fr = horarios.fecha_real(base.isoformat(), c.get("hora_apertura") or "", c.get("hora_cierre") or "", h)
        slots.append({"h": h, "p0": horarios.precio_turno_de(c, h, 0), "pa": horarios.precio_turno_de(c, h, desc.get((fr, h), 0)),
                      "d": desc.get((fr, h), 0),
                      "px": {str(p): horarios.precio_turno_de(c, h, p) for p in (10, 15, 20, 30)}})
    n_cli = len(clientes_de(canchas, ahora.date()))
    opts = "".join(f"<a class='chip{' sel' if x['id'] == c['id'] else ''}' href='/anfitrion/llenar?cancha={quote(x['id'])}&dia={dia}'>"
                   f"{e((x['club'] + ' · ' + x['nombre']) if x.get('club') else x['nombre'])}</a>" for x in canchas)
    dias = "".join(f"<a class='chip{' sel' if i == dia else ''}' href='/anfitrion/llenar?cancha={quote(c['id'])}&dia={i}'>{t}</a>" for i, t in ((0, "Hoy"), (1, "Mañana")))
    cfg = {"cancha": c["id"], "dia": dia, "sim": sim, "slots": slots, "n": n_cli}
    lista = ("<div class='jp-slots' id='llSlots'></div><button type='button' class='btn sec' style='margin-top:10px' id='llTodas'>Seleccionar todas</button>"
             if slots else f"<p class='sub'>{'No quedan horas libres hoy. 🎉' if dia == 0 else 'No hay horas libres mañana. 🎉'}</p>")
    descs = "".join(f"<button type='button' class='chip{' sel' if p == 0 else ''}' data-desc='{p}'>{'Sin desc.' if p == 0 else f'{p}%'}</button>" for p in (0, 10, 15, 20, 30))
    cuerpo = (f"<style>{_CSS}</style><div class='jp-wrap jp-form'><a class='jp-volver' href='/anfitrion/hoy'>‹ Hoy</a>"
              "<h1>Llenar cancha</h1><p class='sub'>Elige las horas vacías y avísalas a tus clientes: no dejes la cancha sin jugar.</p>"
              f"<label class='l'>Cancha</label><div class='jp-chips'>{opts}</div>"
              f"<div class='jp-chips'>{dias}</div><label class='l'>Horas libres</label>{lista}"
              f"<div id='llDescBox' style='display:none'><label class='l'>Descuento para llenar (opcional)</label><div class='jp-chips' id='llDesc'>{descs}</div>"
              "<p class='ayuda' id='llDescAyuda'>Sin descuento: precio normal.</p></div>"
              "<label class='l'>Mensaje o promo (opcional)</label><input type='text' id='llPromo' maxlength='160' placeholder='Ej.: 20% off hoy'>"
              f"<div class='jp-acc'><button type='button' class='btn' id='llGo' disabled>Elige horas para avisar</button></div></div>"
              f"<script>window.LL={_js(cfg)};</script><script>{_JS_BASE}{_JS_LLENAR}</script>")
    return ui.shell("Llenar cancha", cuerpo, nav=_cabecera("hoy", ses), sesion=ses, ancho=True, titulo_tab="Llenar cancha · Pichangol")


_JS_LLENAR = r"""
var sel = {}, desc = 0;
function precio(s){ return (sel[s.h] && desc > 0) ? s.px[String(desc)] : (sel[s.h] ? s.p0 : s.pa); }
function pintar(){
  var box = document.getElementById('llSlots');
  if(box) box.innerHTML = LL.slots.map(function(s){ return "<button type='button' class='jp-slot" + (sel[s.h] ? ' sel' : '') + "' data-h='" + s.h + "'><b>" + s.h + "</b><small>" + jpEsc(LL.sim) + ' ' + precio(s) + (s.d && !sel[s.h] ? ' · −' + s.d + '%' : '') + "</small></button>"; }).join('');
  var n = Object.keys(sel).length, go = document.getElementById('llGo');
  go.disabled = !n; go.textContent = n ? 'Avisar a mis clientes (' + LL.n + ')' : 'Elige horas para avisar';
  document.getElementById('llDescBox').style.display = n ? '' : 'none';
  var t = document.getElementById('llTodas'); if(t) t.textContent = n === LL.slots.length ? 'Quitar todas' : 'Seleccionar todas';
  document.getElementById('llDescAyuda').textContent = desc > 0 ? 'Se cobra ' + desc + '% menos en esas horas: es el precio REAL al reservar (no solo el aviso).' : 'Sin descuento: precio normal.';
  document.querySelectorAll('#llDesc [data-desc]').forEach(function(b){ b.classList.toggle('sel', +b.dataset.desc === desc); });
}
document.addEventListener('click', function(ev){
  var t;
  if((t = ev.target.closest('[data-h]'))){ if(sel[t.dataset.h]) delete sel[t.dataset.h]; else sel[t.dataset.h] = 1; pintar(); return; }
  if((t = ev.target.closest('#llTodas'))){ if(Object.keys(sel).length === LL.slots.length) sel = {}; else LL.slots.forEach(function(s){ sel[s.h] = 1; }); pintar(); return; }
  if((t = ev.target.closest('[data-desc]'))){ desc = +t.dataset.desc; pintar(); return; }
});
document.getElementById('llGo').addEventListener('click', function(){
  var horas = Object.keys(sel); if(!horas.length) return;
  if(!LL.n){ pcgAvisar({titulo: 'Aún sin clientes', icono: 'ℹ️', mensaje: 'Aún no tienes clientes registrados para avisar.'}); return; }
  pcgConfirmar({titulo: 'Avisar a tus clientes', icono: '📣', mensaje: 'Se aplicará el precio elegido a ' + horas.length + ' hora(s) y se avisará a tus ' + LL.n + ' cliente(s): por el chat de Pichangol a los que tienen la app y por WhatsApp a los demás.', confirmar: 'Avisar', cancelar: 'Cancelar'}).then(function(ok){
    if(!ok) return;
    jpPost('/anfitrion/llenar/avisar', {cancha_id: LL.cancha, dia: LL.dia, horas: horas, descuento: desc, promo: document.getElementById('llPromo').value}, 'Avisando…').then(function(j){
      if(!j.ok){ jpFallo(j); return; }
      var msg = j.enviados > 0 ? '✅ Avisé a ' + j.enviados + ' cliente(s) por la app 📲' : (j.whatsapp.length ? 'Ningún cliente tiene la app aún.' : 'Listo.');
      if(!j.whatsapp.length){ pcgAvisar({titulo: 'Aviso enviado', icono: '📣', mensaje: msg}).then(function(){ pcgRecargar(); }); return; }
      var h = "<p>" + jpEsc(msg) + "</p><p><b>Avisar por WhatsApp</b><br><small>Clientes sin la app. Toca para abrir el chat con el mensaje listo.</small></p>"
        + j.whatsapp.map(function(c){ return "<div class='jp-fila'><span class='jp-av'>" + jpEsc((c.nombre || '?').charAt(0).toUpperCase()) + "</span><div class='q'><b>" + jpEsc(c.nombre) + "</b></div><a class='btn chico' style='width:auto;flex:none;margin:0;padding:8px 14px' target='_blank' rel='noopener' href='" + jpEsc(c.url) + "' data-wa-movil='" + jpEsc(c.movil) + "'>WhatsApp</a></div>"; }).join('');
      pcgAvisar({titulo: 'Aviso enviado', icono: '📣', html: h, confirmar: 'Listo'}).then(function(){ pcgRecargar(); });
    });
  });
});
pintar();
"""


@router.post("/anfitrion/llenar/avisar")
def avisar_libres(request: Request, body: dict = Body(default_factory=dict)) -> JSONResponse:
    """`_avisar`: aplica el descuento REAL a cada hora elegida y avisa por el
    chat de la cancha (hilo `cancha_<dueño>|<cliente>`, push por el trigger) a
    los clientes con cuenta; devuelve los enlaces de WhatsApp de los demás."""
    ses, err = _ses_o_401(request)
    if err:
        return err
    from web.jugador_mensajes import hilo_cancha, insertar_mensaje
    from web.router import _moneda_de, _pais_de
    yo = _low(ses["email"])
    canchas = datos.canchas_de_dueno(yo)
    c = next((x for x in canchas if x["id"] == str(body.get("cancha_id") or "")), None)
    if c is None:
        return JSONResponse({"ok": False, "mensaje": "Cancha no encontrada."}, status_code=404)
    try:
        dia = 1 if int(body.get("dia") or 0) == 1 else 0
        pct = int(body.get("descuento") or 0)
    except (TypeError, ValueError):
        return JSONResponse({"ok": False, "mensaje": "Datos inválidos."}, status_code=400)
    if pct not in (0, 10, 15, 20, 30):
        return JSONResponse({"ok": False, "mensaje": "Descuento inválido."}, status_code=400)
    ahora = horarios.ahora_local(_pais_de(c))
    base = ahora.date() + timedelta(days=dia)
    libres = set(horas_libres(c, base, ahora))
    horas = sorted({str(h) for h in (body.get("horas") or []) if str(h) in libres})
    if not horas:
        return JSONResponse({"ok": False, "mensaje": "Elige al menos una hora libre (las elegidas ya no están libres)."}, status_code=400)
    clientes = clientes_de(canchas, ahora.date())
    if not clientes:
        return JSONResponse({"ok": False, "mensaje": "Aún no tienes clientes registrados para avisar."}, status_code=400)
    promo = re.sub(r"\s+", " ", str(body.get("promo") or "")).strip()[:160]
    precios = []
    for h in horas:
        fr = horarios.fecha_real(base.isoformat(), c.get("hora_apertura") or "", c.get("hora_cierre") or "", h)
        aplicar_descuento_slot(c["id"], fr, h, pct)
        precios.append(horarios.precio_turno_de(c, h, pct))
    sim = _moneda_de(c)[0]
    dia_txt = "hoy" if dia == 0 else "mañana"
    minom = mi_nombre(ses)
    enviados = 0
    wa = []
    iso = _pais_de(c)
    for i, cli in enumerate(clientes):
        txt = texto_aviso(c, cli["nombre"], horas, precios, dia_txt, pct, promo, sim)
        if cli["email"]:
            if cli["email"] == yo:
                continue
            fila = {"id": f"msg_{time.time_ns() // 1000}_{i}", "hilo": hilo_cancha(yo, cli["email"]), "tipo": "cancha",
                    "ref_id": yo, "cuenta_email": cli["email"], "autor_email": yo, "autor_nombre": minom,
                    "es_profe": True, "texto": txt}
            if insertar_mensaje(fila):
                enviados += 1
        elif cli["telefono"]:
            tel = cli["telefono"]
            pref = catalogos.TEL_PREFIJO.get(iso, "51")
            if len(tel) <= catalogos.TEL_LONGITUD.get(iso, 9):
                tel = pref + tel
            wa.append({"nombre": cli["nombre"], "url": ui.enlace_whatsapp(txt, tel, pc=True), "movil": ui.enlace_whatsapp(txt, tel)})
    return JSONResponse({"ok": True, "enviados": enviados, "whatsapp": wa, "horas": horas})
