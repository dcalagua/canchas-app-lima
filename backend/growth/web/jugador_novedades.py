"""NOVEDADES y CANALES en la web = los del APK (pedido del director,
29-sep-2026: "en la web implementa las mismas funcionalidades que existen
actualmente en el app").

Espejo de estas pantallas, con las MISMAS tablas y buckets de Supabase
(Postgres directo + Storage REST vía `web/almacen.py`):

- `GET /novedades` = `novedades_screen.dart`: "Mi estado" (mis historias
  vigentes + "Visto por N"), "Canales" (los que sigo + los míos, ordenados
  por su última publicación, con no leídos contra la última vista guardada en
  el navegador como `appState.canalUltimaVista`) y "Actualizaciones
  recientes" = autores con historia vigente que están en MIS contactos
  (`pichangol_agenda.contactos`, regla de privacidad de `_conocidos()`:
  nunca bloqueados ni ocultos), primero los que tienen algo no visto y dentro
  el más reciente arriba. Aro lima = no visto / gris = visto; lo visto sale
  de `pichangol_estados_vistas` (la misma fila que `EstadosRepo.marcarVisto`).
- Visor (capa dentro de /novedades) = `estado_viewer_screen.dart`: barras de
  avance, 5 s por foto/texto, 15 s si lleva música, el video dura lo que dura
  (tope 30 s), tocar izquierda/derecha, mantener = pausa, música desde
  `musica_inicio_ms` con enlace a Apple Music (o búsqueda en Spotify), marcar
  visto, responder = mensaje DIRECTO citando la historia (`enviarMensajeDirecto`
  con `resp_texto/resp_autor/resp_media`), Mensaje → chat web, Ocultar sus
  historias y Reportar; en las mías: "Visto por N" con foto real y Eliminar
  (fila + `estados/<id>.jpg|mp4`).
- `GET /novedades/estado/nuevo?tipo=texto|foto|video` =
  `estado_composer_screen.dart`: texto ≤280 sobre los 8 fondos del catálogo
  del app (`_fondos`, se guarda el ARGB como el app), foto (comprimida a
  1600 px) o video (≤30 s como `pickVideo(maxDuration: 30 s)`) con pie
  ≤200, y música opcional (búsqueda de iTunes y "destacadas" del país, igual
  que `MusicaService`, recorte con deslizador como `selector_musica_screen`).
  Sube al bucket `estados/<id>.jpg|.mp4` con id `st_<µs>` y la fila de
  `Estado.toRow`. Vigencia 24 h (servidor y navegador); al abrir Novedades se
  barren MIS historias vencidas (`limpiarVencidosDe`).
- `GET /canales` = `canales_screen.dart` (buscar, Mis canales / Siguiendo /
  Descubrir, Seguir), `GET /canales/nuevo` = `crear_canal_screen.dart`,
  `GET /canales/{id}` = `canal_detalle_screen.dart` (cabecera con seguidores,
  Seguir/Siguiendo o "Eres el administrador", publicaciones con foto/video y
  enlaces, reacciones de `pichangol_reacciones` con hilo `canal_<id>`
  —alternar como `ReaccionesRepo.alternar`—, el dueño publica texto, foto o
  video ≤60 s con descripción y borra posts; media en
  `canales/<canal>/<post>.jpg|mp4`), `GET /canales/{id}/editar` =
  `editar_canal_screen.dart` (portada `canales/<id>/portada.jpg`).
  "Generar con IA" NO aparece: en el app está oculto por
  `kServiciosPichangolActivo = false`.

Privacidad: el navegador nunca recibe correos ajenos. Los autores viajan
como `ref` opaco (el mismo cifrado de la Liga/Mensajes) y los canales solo
dicen si son míos; toda escritura valida en el servidor con el correo de la
sesión (ver solo historias de mis contactos, borrar solo lo mío, publicar solo
en mi canal). Device-first: cada página llega pintada con sus datos, los
guarda en `localStorage` y se repinta desde ahí al volver (bfcache/atrás),
refrescando en segundo plano solo con la pestaña visible.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import struct
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from fastapi import APIRouter, Body, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, JSONResponse

from db import pg
from web import almacen, sesion, ui
from web.jugador_liga import email_de_ref, perfiles, ref_de, sin_sesion
from web.jugador_mensajes import agenda_de, hilo_directo, insertar_mensaje
from web.ui import e

router = APIRouter()

VIGENCIA = timedelta(hours=24)            # `Estado.vigente`
TEXTO_MAX = 280                           # composer de texto (`maxLength: 280`)
PIE_MAX = 200                             # pie de foto/video (`maxLength: 200`)
VIDEO_ESTADO_SEG = 30                     # `pickVideo(maxDuration: 30 s)`
VIDEO_CANAL_SEG = 60                      # canal: `pickVideo(maxDuration: 60 s)`
FOTO_MAX = 6 * 1024 * 1024                # ya comprimida a 1600 px en el navegador
VIDEO_MAX = 50 * 1024 * 1024              # tope del bucket (el app avisa "graba uno más corto")
CANAL_NOMBRE_MAX = 50
CANAL_DESC_MAX = 160
POST_TEXTO_MAX = 4000
REACCIONES = ["👍", "❤️", "😂", "😮", "😢", "🙏", "🔥", "⚽"]   # canal_detalle `_elegirReaccion`

# Catálogo de fondos del estado de texto = `_fondos` de estado_composer_screen.dart.
FONDOS = [0xFF128C7E, 0xFF008489, 0xFF14463A, 0xFF7B61FF, 0xFFE07A3E, 0xFFC13515, 0xFF2AA9E0, 0xFF222222]
BG_DEFECTO = 0xFF128C7E

_RE_ID_ESTADO = re.compile(r"^st_\d{10,20}$")
_RE_ID_CANAL = re.compile(r"^ch_\d{10,20}$")
_RE_ID_POST = re.compile(r"^cp_\d{10,20}$")


# ═══════════════════════════ Utilidades ═══════════════════════════════════════

def _low(s) -> str:
    return str(s or "").strip().lower()


def _dt(v) -> datetime | None:
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    if not v:
        return None
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:  # noqa: BLE001
        return None


def _iso(v) -> str:
    d = _dt(v)
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ") if d else ""


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _us() -> int:
    return time.time_ns() // 1000


def color_css(argb) -> str:
    """ARGB del app (`bg`) → `#RRGGBB` del navegador."""
    try:
        v = int(argb) & 0xFFFFFF
    except Exception:  # noqa: BLE001
        v = BG_DEFECTO & 0xFFFFFF
    return f"#{v:06X}"


def _ses_o_401(request: Request):
    ses = sesion.de_request(request)
    if not ses or not ses.get("email"):
        return None, JSONResponse({"ok": False, "error": "sesion_requerida", "mensaje": "Inicia sesión para continuar."},
                                  status_code=401)
    return ses, None


def _mal(msg: str, code: int = 400, error: str = "invalido") -> JSONResponse:
    return JSONResponse({"ok": False, "error": error, "mensaje": msg}, status_code=code)


def _mi_nombre(email: str, ses: dict) -> str:
    p = perfiles([email]).get(email) or {}
    return (p.get("nombre") or ses.get("nombre") or email.split("@")[0]).strip()


def _firma(*partes: str) -> str:
    """Prueba de que una media la subió ESTA cuenta (entre la subida y la publicación)."""
    k = hashlib.sha256(sesion._secreto() + b"|pcg-novedades-media").digest()
    return hmac.new(k, "|".join(partes).encode(), hashlib.sha256).hexdigest()[:32]


def _clave_cache(email: str, que: str) -> str:
    """Clave de `localStorage` por cuenta (hash: no deja el correo en el navegador)."""
    return "pcg_" + que + "_" + hashlib.sha256(sesion._secreto()[:8] + _low(email).encode()).hexdigest()[:14]


def duracion_mp4(datos_: bytes) -> float | None:
    """Duración (s) de un MP4/MOV leyendo `moov/mvhd` (sin decodificar). None si
    no es un ISO-BMFF válido. Así el servidor hace cumplir el tope del app."""
    def cajas(buf: bytes, ini: int, fin: int):
        i = ini
        while i + 8 <= fin:
            tam, tipo = struct.unpack(">I4s", buf[i:i + 8])
            cab = 8
            if tam == 1:
                if i + 16 > fin:
                    return
                tam = struct.unpack(">Q", buf[i + 8:i + 16])[0]
                cab = 16
            elif tam == 0:
                tam = fin - i
            if tam < cab or i + tam > fin:
                return
            yield tipo, i + cab, i + tam
            i += tam
    try:
        if datos_[4:8] != b"ftyp":
            return None
        for tipo, a, b in cajas(datos_, 0, len(datos_)):
            if tipo != b"moov":
                continue
            for t2, a2, _b2 in cajas(datos_, a, b):
                if t2 != b"mvhd":
                    continue
                ver = datos_[a2]
                if ver == 1:
                    escala = struct.unpack(">I", datos_[a2 + 20:a2 + 24])[0]
                    dur = struct.unpack(">Q", datos_[a2 + 24:a2 + 32])[0]
                else:
                    escala = struct.unpack(">I", datos_[a2 + 12:a2 + 16])[0]
                    dur = struct.unpack(">I", datos_[a2 + 16:a2 + 20])[0]
                return (dur / escala) if escala else None
    except Exception:  # noqa: BLE001
        return None
    return None


def _es_jpeg(b: bytes) -> bool:
    return b[:3] == b"\xff\xd8\xff"


def _borrar_media(bucket: str, rutas: list[str]) -> None:
    """Borrado físico best-effort (misma policy que el app, `StorageLimpieza.borrar`)."""
    try:
        from storage_limpieza import _borrar_objeto
    except Exception:  # noqa: BLE001
        return
    for r in rutas:
        try:
            _borrar_objeto(bucket, r)
        except Exception:  # noqa: BLE001
            pass


def _es_media_de(url: str, bucket: str, ruta: str) -> bool:
    return bool(url) and url.split("?", 1)[0] == almacen.url_publica(ruta, bucket)


# ═══════════════════════════ Datos: estados (fail-safe) ═══════════════════════

_COLS_BASE = ["id", "autor_email", "autor_nombre", "tipo", "texto", "foto_url", "bg", "creado_en"]
_COLS_MUSICA = ["musica_titulo", "musica_artista", "musica_preview", "musica_art", "musica_inicio_ms", "musica_track_url"]
_cols_estado: dict[str, list[str]] = {}


def _cols_estados() -> list[str]:
    """Columnas de `pichangol_estados` (la música llegó en una migración aparte)."""
    if "v" in _cols_estado:
        return _cols_estado["v"]
    cols = list(_COLS_BASE)
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'pichangol_estados'")
            hay = {str(f[0]) for f in cur.fetchall()}
        if hay:
            cols += [c for c in _COLS_MUSICA if c in hay]
            _cols_estado["v"] = cols
    except Exception:  # noqa: BLE001
        pass
    return cols


def estados_vigentes(autores: list[str]) -> list[dict]:
    """`EstadosRepo.fetchVigentes` limitado a los autores que puedo ver (más
    antiguos primero, como el app)."""
    es = sorted({_low(a) for a in autores if _low(a)})
    if not pg.habilitado or not es:
        return []
    cols = _cols_estados()
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT {', '.join(cols)} FROM pichangol_estados WHERE lower(autor_email) = ANY(%s) "
                        "AND creado_en >= %s ORDER BY creado_en ASC", (es, _ahora() - VIGENCIA))
            filas = [dict(zip(cols, f)) for f in cur.fetchall()]
    except Exception:  # noqa: BLE001
        return []
    for f in filas:
        f["autor_email"] = _low(f.get("autor_email"))
    return filas


def estado(estado_id: str) -> dict | None:
    if not pg.habilitado or not estado_id:
        return None
    cols = _cols_estados()
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT {', '.join(cols)} FROM pichangol_estados WHERE id = %s", (estado_id,))
            f = cur.fetchone()
    except Exception:  # noqa: BLE001
        return None
    if not f:
        return None
    d = dict(zip(cols, f))
    d["autor_email"] = _low(d.get("autor_email"))
    return d


def vistos_por(email: str, ids: list[str]) -> set[str]:
    """Estados que YO ya vi (`pichangol_estados_vistas`)."""
    if not pg.habilitado or not ids:
        return set()
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT estado_id FROM pichangol_estados_vistas WHERE lower(email) = %s AND estado_id = ANY(%s)",
                        (_low(email), list(ids)))
            return {str(f[0]) for f in cur.fetchall()}
    except Exception:  # noqa: BLE001
        return set()


def vistas_de(ids: list[str]) -> dict[str, list[tuple[str, datetime | None]]]:
    """`EstadosRepo.vistas`: quién vio cada estado (solo para MIS estados)."""
    if not pg.habilitado or not ids:
        return {}
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT estado_id, email, visto_en FROM pichangol_estados_vistas WHERE estado_id = ANY(%s) "
                        "ORDER BY visto_en DESC", (list(ids),))
            out: dict[str, list] = {}
            for f in cur.fetchall():
                out.setdefault(str(f[0]), []).append((_low(f[1]), _dt(f[2])))
            return out
    except Exception:  # noqa: BLE001
        return {}


def marcar_visto(estado_id: str, email: str) -> bool:
    if not pg.habilitado:
        return False
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO pichangol_estados_vistas (estado_id, email, visto_en) VALUES (%s, %s, now()) "
                        "ON CONFLICT (estado_id, email) DO UPDATE SET visto_en = EXCLUDED.visto_en",
                        (estado_id, _low(email)))
            conn.commit()
            return True
    except Exception:  # noqa: BLE001
        return False


def insertar_estado(fila: dict) -> bool:
    """`EstadosRepo.publicar` (`Estado.toRow`, las columnas de música solo si traen algo)."""
    if not pg.habilitado:
        return False
    cols_ok = set(_cols_estados())
    cols = [c for c in _COLS_BASE if c != "creado_en"]
    vals = [fila.get(c, "") for c in cols]
    for c in _COLS_MUSICA:
        v = fila.get(c)
        if v and c in cols_ok:
            cols.append(c); vals.append(v)
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute(f"INSERT INTO pichangol_estados ({', '.join(cols)}, creado_en) "
                        f"VALUES ({', '.join(['%s'] * len(cols))}, now())", vals)
            conn.commit()
            return True
    except Exception:  # noqa: BLE001
        return False


def borrar_estado(estado_id: str, autor: str) -> bool:
    """`EstadosRepo.eliminar`: SOLO si es del autor; luego su media."""
    if not pg.habilitado:
        return False
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM pichangol_estados WHERE id = %s AND lower(autor_email) = %s", (estado_id, _low(autor)))
            n = cur.rowcount
            conn.commit()
    except Exception:  # noqa: BLE001
        return False
    if n:
        _borrar_media("estados", [f"{estado_id}.jpg", f"{estado_id}.mp4"])
    return bool(n)


def limpiar_vencidos_de(email: str) -> None:
    """`EstadosRepo.limpiarVencidosDe`: cada uno barre SU vereda (media, vistas y filas)."""
    em = _low(email)
    if not pg.habilitado or not em:
        return
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id FROM pichangol_estados WHERE lower(autor_email) = %s AND creado_en < %s",
                        (em, _ahora() - VIGENCIA))
            ids = [str(f[0]) for f in cur.fetchall() if f[0]]
            if not ids:
                return
            cur.execute("DELETE FROM pichangol_estados_vistas WHERE estado_id = ANY(%s)", (ids,))
            cur.execute("DELETE FROM pichangol_estados WHERE id = ANY(%s)", (ids,))
            conn.commit()
    except Exception:  # noqa: BLE001
        return
    _borrar_media("estados", [r for i in ids for r in (f"{i}.jpg", f"{i}.mp4")])


def _limpiar_en_segundo_plano(email: str) -> None:
    threading.Thread(target=limpiar_vencidos_de, args=(email,), daemon=True, name="pcg-estados-barrido").start()


# ═══════════════════════════ Datos: canales (fail-safe) ═══════════════════════

def _canal_dict(f) -> dict:
    return {"id": str(f[0]), "nombre": str(f[1] or ""), "descripcion": str(f[2] or ""), "foto_url": str(f[3] or ""),
            "owner_email": _low(f[4]), "creado": _dt(f[5])}


def canales_todos(limite: int = 500) -> list[dict]:
    """`CanalesRepo.todos` (más nuevos primero) con el conteo de seguidores."""
    if not pg.habilitado:
        return []
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT c.id, c.nombre, c.descripcion, c.foto_url, c.owner_email, c.creado, "
                        "(SELECT count(*) FROM pichangol_canal_seguidores s WHERE s.canal_id = c.id) "
                        "FROM pichangol_canales c ORDER BY c.creado DESC LIMIT %s", (limite,))
            out = []
            for f in cur.fetchall():
                d = _canal_dict(f)
                d["seguidores"] = int(f[6] or 0)
                out.append(d)
            return out
    except Exception:  # noqa: BLE001
        return []


def canal(canal_id: str) -> dict | None:
    if not pg.habilitado or not canal_id:
        return None
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT c.id, c.nombre, c.descripcion, c.foto_url, c.owner_email, c.creado, "
                        "(SELECT count(*) FROM pichangol_canal_seguidores s WHERE s.canal_id = c.id) "
                        "FROM pichangol_canales c WHERE c.id = %s", (canal_id,))
            f = cur.fetchone()
    except Exception:  # noqa: BLE001
        return None
    if not f:
        return None
    d = _canal_dict(f)
    d["seguidores"] = int(f[6] or 0)
    return d


def seguidos_de(email: str) -> set[str]:
    if not pg.habilitado:
        return set()
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT canal_id FROM pichangol_canal_seguidores WHERE lower(email) = %s", (_low(email),))
            return {str(f[0]) for f in cur.fetchall()}
    except Exception:  # noqa: BLE001
        return set()


def seguir(canal_id: str, email: str, si: bool) -> bool:
    """`CanalesRepo.seguir` / `dejar`."""
    if not pg.habilitado:
        return False
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            if si:
                cur.execute("INSERT INTO pichangol_canal_seguidores (canal_id, email, desde) VALUES (%s, %s, now()) "
                            "ON CONFLICT (canal_id, email) DO NOTHING", (canal_id, _low(email)))
            else:
                cur.execute("DELETE FROM pichangol_canal_seguidores WHERE canal_id = %s AND lower(email) = %s",
                            (canal_id, _low(email)))
            conn.commit()
            return True
    except Exception:  # noqa: BLE001
        return False


def crear_canal(fila: dict) -> bool:
    if not pg.habilitado:
        return False
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO pichangol_canales (id, nombre, descripcion, foto_url, owner_email, creado) "
                        "VALUES (%s, %s, %s, %s, %s, now())",
                        (fila["id"], fila["nombre"], fila.get("descripcion", ""), fila.get("foto_url", ""), _low(fila["owner_email"])))
            conn.commit()
            return True
    except Exception:  # noqa: BLE001
        return False


def actualizar_canal(canal_id: str, owner: str, cambios: dict) -> bool:
    """`CanalesRepo.actualizar`, con el dueño en el WHERE (canal ajeno → False)."""
    cols = [c for c in ("nombre", "descripcion", "foto_url") if c in cambios]
    if not pg.habilitado or not cols:
        return False
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute(f"UPDATE pichangol_canales SET {', '.join(c + ' = %s' for c in cols)} "
                        "WHERE id = %s AND lower(owner_email) = %s", [cambios[c] for c in cols] + [canal_id, _low(owner)])
            n = cur.rowcount
            conn.commit()
            return bool(n)
    except Exception:  # noqa: BLE001
        return False


def _post_dict(f) -> dict:
    return {"id": str(f[0]), "canal_id": str(f[1]), "autor_email": _low(f[2]), "autor_nombre": str(f[3] or ""),
            "tipo": str(f[4] or "texto"), "texto": str(f[5] or ""), "media_url": str(f[6] or ""), "creado": _dt(f[7])}


_SEL_POST = "SELECT id, canal_id, autor_email, autor_nombre, tipo, texto, media_url, creado FROM pichangol_canal_posts "


def posts_de(canal_id: str, limite: int = 50) -> list[dict]:
    """`CanalesRepo.posts` (más nuevos primero)."""
    if not pg.habilitado:
        return []
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute(_SEL_POST + "WHERE canal_id = %s ORDER BY creado DESC LIMIT %s", (canal_id, limite))
            return [_post_dict(f) for f in cur.fetchall()]
    except Exception:  # noqa: BLE001
        return []


def posts_agrupados(ids: list[str], limite: int = 400) -> dict[str, list[dict]]:
    """`CanalesRepo.postsAgrupados`: última publicación y no leídos por canal."""
    if not pg.habilitado or not ids:
        return {}
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute(_SEL_POST + "WHERE canal_id = ANY(%s) ORDER BY creado DESC LIMIT %s", (list(ids), limite))
            out: dict[str, list] = {}
            for f in cur.fetchall():
                p = _post_dict(f)
                out.setdefault(p["canal_id"], []).append(p)
            return out
    except Exception:  # noqa: BLE001
        return {}


def ultimas_de(ids: list[str]) -> dict[str, dict]:
    """`CanalesRepo.ultimasDe`: la publicación más nueva de cada canal."""
    if not pg.habilitado or not ids:
        return {}
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT DISTINCT ON (canal_id) id, canal_id, autor_email, autor_nombre, tipo, texto, media_url, creado "
                        "FROM pichangol_canal_posts WHERE canal_id = ANY(%s) ORDER BY canal_id, creado DESC", (list(ids),))
            return {str(f[1]): _post_dict(f) for f in cur.fetchall()}
    except Exception:  # noqa: BLE001
        return {}


def insertar_post(fila: dict) -> bool:
    if not pg.habilitado:
        return False
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO pichangol_canal_posts (id, canal_id, autor_email, autor_nombre, tipo, texto, media_url, creado) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, now())",
                        (fila["id"], fila["canal_id"], _low(fila["autor_email"]), fila["autor_nombre"], fila["tipo"],
                         fila.get("texto", ""), fila.get("media_url", "")))
            conn.commit()
            return True
    except Exception:  # noqa: BLE001
        return False


def borrar_post(post_id: str, canal_id: str) -> dict | None:
    """Borra el post del canal (el llamador ya validó que el canal es mío) y
    devuelve la fila borrada (para limpiar su media, `_borrarMediaDePost`)."""
    if not pg.habilitado:
        return None
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM pichangol_canal_posts WHERE id = %s AND canal_id = %s RETURNING media_url",
                        (post_id, canal_id))
            f = cur.fetchone()
            cur.execute("DELETE FROM pichangol_reacciones WHERE mensaje_id = %s AND hilo = %s", (post_id, f"canal_{canal_id}"))
            conn.commit()
    except Exception:  # noqa: BLE001
        return None
    return {"media_url": str(f[0] or "")} if f else None


def post_existe(canal_id: str, post_id: str) -> bool:
    if not pg.habilitado:
        return False
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pichangol_canal_posts WHERE id = %s AND canal_id = %s", (post_id, canal_id))
            return cur.fetchone() is not None
    except Exception:  # noqa: BLE001
        return False


def reacciones_de(canal_id: str) -> dict[str, dict[str, str]]:
    """`ReaccionesRepo.stream('canal_<id>')` → {post: {correo: emoji}}."""
    if not pg.habilitado:
        return {}
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT mensaje_id, email, emoji FROM pichangol_reacciones WHERE hilo = %s ORDER BY creado ASC",
                        (f"canal_{canal_id}",))
            out: dict[str, dict] = {}
            for f in cur.fetchall():
                if f[0] and f[1] and f[2]:
                    out.setdefault(str(f[0]), {})[_low(f[1])] = str(f[2])
            return out
    except Exception:  # noqa: BLE001
        return {}


def alternar_reaccion(canal_id: str, post_id: str, email: str, emoji: str) -> bool:
    """`ReaccionesRepo.alternar`: el mismo emoji la QUITA; otro la cambia."""
    if not pg.habilitado:
        return False
    hilo, em = f"canal_{canal_id}", _low(email)
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT emoji FROM pichangol_reacciones WHERE mensaje_id = %s AND lower(email) = %s", (post_id, em))
            f = cur.fetchone()
            if f and str(f[0]) == emoji:
                cur.execute("DELETE FROM pichangol_reacciones WHERE mensaje_id = %s AND lower(email) = %s", (post_id, em))
            else:
                cur.execute("INSERT INTO pichangol_reacciones (mensaje_id, email, emoji, hilo, creado) VALUES (%s, %s, %s, %s, now()) "
                            "ON CONFLICT (mensaje_id, email) DO UPDATE SET emoji = EXCLUDED.emoji, hilo = EXCLUDED.hilo",
                            (post_id, em, emoji, hilo))
            conn.commit()
            return True
    except Exception:  # noqa: BLE001
        return False


# ═══════════════════════════ Armado de datos para el navegador ════════════════

def _nombre_de(email: str, agenda: dict, pf: dict, respaldo: str = "") -> str:
    """`nombreMostrableDe`: mi apodo > nombre de su perfil > el del estado."""
    return ((agenda.get("apodos") or {}).get(email) or (pf.get(email) or {}).get("nombre") or respaldo
            or email.split("@")[0]).strip()


def _item_estado(f: dict, vistos: set[str], vistas: dict | None = None) -> dict:
    it = {"id": f["id"], "tipo": f.get("tipo") or "texto", "texto": f.get("texto") or "", "media": f.get("foto_url") or "",
          "bg": color_css(f.get("bg") if f.get("bg") is not None else BG_DEFECTO), "creado": _iso(f.get("creado_en")),
          "visto": f["id"] in vistos}
    if f.get("musica_preview"):
        it["musica"] = {"titulo": f.get("musica_titulo") or "", "artista": f.get("musica_artista") or "",
                        "preview": f.get("musica_preview") or "", "art": f.get("musica_art") or "",
                        "inicio": int(f.get("musica_inicio_ms") or 0), "track": f.get("musica_track_url") or ""}
    if vistas is not None:
        it["vistas"] = len(vistas.get(f["id"]) or [])
    return it


def datos_novedades(yo: str, ses: dict | None = None) -> dict:
    """Todo lo que pinta /novedades (sin correos ajenos)."""
    agenda = agenda_de(yo)
    bloq = set(agenda.get("bloqueados") or [])
    conocidos = [c for c in agenda.get("contactos") or [] if c and c != yo and c not in bloq]
    filas = estados_vigentes([yo] + conocidos)
    ahora = _ahora()
    filas = [f for f in filas if (_dt(f.get("creado_en")) or ahora) > ahora - VIGENCIA]
    ids_ajenos = [f["id"] for f in filas if f["autor_email"] != yo]
    vistos = vistos_por(yo, ids_ajenos)
    mios = [f for f in filas if f["autor_email"] == yo]
    vistas = vistas_de([f["id"] for f in mios]) if mios else {}
    pf = perfiles({yo, *(f["autor_email"] for f in filas)})
    por_autor: dict[str, list] = {}
    for f in filas:
        if f["autor_email"] != yo:
            por_autor.setdefault(f["autor_email"], []).append(f)
    autores = []
    for em, ls in por_autor.items():
        items = [_item_estado(f, vistos) for f in ls]
        autores.append({"ref": ref_de(em), "k": hashlib.sha256(sesion._secreto()[:8] + em.encode()).hexdigest()[:12],
                        "nombre": _nombre_de(em, agenda, pf, ls[-1].get("autor_nombre") or ""),
                        "foto": (pf.get(em) or {}).get("foto_url") or "", "items": items})
    # Orden del app: con algo no visto primero; dentro, el más reciente arriba.
    autores.sort(key=lambda a: (all(i["visto"] for i in a["items"]), -(_dt(a["items"][-1]["creado"]) or ahora).timestamp()))
    mi = {"nombre": _nombre_de(yo, {}, pf, (ses or {}).get("nombre") or ""),
          "foto": (pf.get(yo) or {}).get("foto_url") or (ses or {}).get("foto") or "",
          "items": [_item_estado(f, set(), vistas) for f in mios]}
    return {"ok": True, "mi": mi, "autores": autores, "canales": canales_novedades(yo),
            "sin_contactos": not conocidos}


def _preview_post(p: dict | None) -> str:
    if not p:
        return ""
    if p["tipo"] == "foto":
        return "📷 Foto" + (f" · {p['texto']}" if p.get("texto") else "")
    if p["tipo"] == "video":
        return "🎥 Video" + (f" · {p['texto']}" if p.get("texto") else "")
    t = p.get("texto") or ""
    return ("🔗 " + t) if re.search(r"(https?://|www\.)", t, re.I) else t


def _canal_json(c: dict, yo: str, sigo: bool, ultima: dict | None = None) -> dict:
    return {"id": c["id"], "nombre": c["nombre"], "descripcion": c.get("descripcion") or "", "foto": c.get("foto_url") or "",
            "mio": c["owner_email"] == yo, "sigo": sigo, "seguidores": int(c.get("seguidores") or 0),
            "creado": _iso(c.get("creado")), "ultima": _preview_post(ultima), "ultima_en": _iso((ultima or {}).get("creado"))}


def canales_novedades(yo: str) -> list[dict]:
    """Canales de Novedades: los que sigo + los míos, por su última publicación.
    `nuevos` = fechas de lo publicado por OTROS (el navegador cuenta los no leídos)."""
    todos = canales_todos()
    seg = seguidos_de(yo)
    vis = [c for c in todos if c["id"] in seg or c["owner_email"] == yo]
    posts = posts_agrupados([c["id"] for c in vis])
    out = []
    for c in vis:
        ps = posts.get(c["id"]) or []
        d = _canal_json(c, yo, c["id"] in seg, ps[0] if ps else None)
        d["nuevos"] = [_iso(p["creado"]) for p in ps if p["autor_email"] != yo][:999]
        out.append(d)
    out.sort(key=lambda d: d["ultima_en"] or d["creado"], reverse=True)
    return out


def datos_canales(yo: str) -> dict:
    todos = canales_todos()
    seg = seguidos_de(yo)
    ult = ultimas_de([c["id"] for c in todos])
    return {"ok": True, "canales": [_canal_json(c, yo, c["id"] in seg, ult.get(c["id"])) for c in todos]}


def _post_json(p: dict, reacc: dict, yo: str) -> dict:
    r = reacc.get(p["id"]) or {}
    emojis = list(dict.fromkeys(r.values()))
    return {"id": p["id"], "tipo": p["tipo"], "texto": p.get("texto") or "", "media": p.get("media_url") or "",
            "creado": _iso(p.get("creado")), "mio": p["autor_email"] == yo,
            "reacc": {"emojis": emojis[:3], "total": len(r), "mia": r.get(yo, "")}}


def datos_canal(c: dict, yo: str) -> dict:
    ps = posts_de(c["id"])
    reacc = reacciones_de(c["id"])
    pf = perfiles([c["owner_email"]])
    sigo = c["id"] in seguidos_de(yo)
    d = _canal_json(c, yo, sigo, ps[0] if ps else None)
    d["admin"] = {"nombre": (pf.get(c["owner_email"]) or {}).get("nombre") or "", "foto": (pf.get(c["owner_email"]) or {}).get("foto_url") or ""}
    return {"ok": True, "canal": d, "posts": [_post_json(p, reacc, yo) for p in ps]}


# ═══════════════════════════ CSS / JS comunes ═════════════════════════════════

_CSS = """<style>
.nv-wrap{max-width:720px;margin:6px auto 70px;min-width:0}
.nv-top{display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap;margin:6px 0 10px}
.nv-top h1{font-size:28px;margin:0;letter-spacing:-.3px}
.nv-card{background:#fff;border-radius:18px;box-shadow:0 6px 20px rgba(0,0,0,.07);padding:6px 4px;margin:0 0 14px;min-width:0}
.nv-sec{display:flex;align-items:center;justify-content:space-between;gap:8px;font-weight:800;font-size:17px;margin:20px 4px 8px}
.nv-sec a{font-size:14px;color:var(--esmeralda);text-decoration:none;font-weight:700}
.nv-fila{display:flex;align-items:center;gap:12px;padding:10px 12px;border-radius:14px;cursor:pointer;text-decoration:none;color:inherit;min-width:0;background:none;border:0;width:100%;font:inherit;text-align:left}
.nv-fila:hover{background:#F7F7F7}
.nv-fila .tx{flex:1;min-width:0}
.nv-fila .tx b{display:block;font-size:15.5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.nv-fila .tx small{display:block;color:#6a6a6a;font-size:13.5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.nv-fila .der{display:flex;flex-direction:column;align-items:flex-end;gap:4px;flex:none;color:#6a6a6a;font-size:12.5px}
.nv-badge{background:var(--esmeralda);color:#fff;border-radius:999px;font-size:11.5px;font-weight:800;padding:2px 7px;min-width:20px;text-align:center}
.nv-aro{position:relative;width:58px;height:58px;border-radius:50%;flex:none;padding:3px;background:#C7CDD4}
.nv-aro.nuevo{background:conic-gradient(#7CB518,#0B8A3E,#7CB518)}
.nv-aro.mio{background:none;padding:0}
.nv-aro .in{width:100%;height:100%;border-radius:50%;border:2.5px solid #fff;overflow:hidden;background:#0E8F67;display:flex;align-items:center;justify-content:center;color:#fff;font-weight:800;font-size:20px}
.nv-aro .in img,.nv-aro .in video{width:100%;height:100%;object-fit:cover}
.nv-aro .in .txt{font-size:9px;padding:4px;text-align:center;line-height:1.1;overflow:hidden}
.nv-aro .mas{position:absolute;right:-2px;bottom:-2px;width:22px;height:22px;border-radius:50%;background:var(--esmeralda);color:#fff;border:2px solid #fff;font-size:15px;font-weight:800;display:flex;align-items:center;justify-content:center;line-height:1}
.nv-av{width:52px;height:52px;border-radius:50%;object-fit:cover;flex:none;display:inline-flex;align-items:center;justify-content:center;background:#EAF7EF;font-size:24px;overflow:hidden}
.nv-av img{width:100%;height:100%;object-fit:cover}
.nv-vacio{text-align:center;color:#6a6a6a;padding:26px 16px;font-size:14.5px}
.nv-vacio .em{font-size:48px;display:block;margin-bottom:6px}
.nv-fab{position:fixed;right:max(18px,env(safe-area-inset-right));bottom:max(22px,env(safe-area-inset-bottom));z-index:40;border:0;border-radius:18px;background:var(--esmeralda);color:#fff;font:inherit;font-weight:800;font-size:15px;padding:15px 18px;box-shadow:0 8px 22px rgba(11,138,62,.35);cursor:pointer}
.nv-opc{display:flex;align-items:center;gap:12px;width:100%;border:1px solid #E4E4E4;background:#fff;border-radius:14px;padding:12px;margin:0 0 8px;font:inherit;cursor:pointer;text-align:left;text-decoration:none;color:inherit}
.nv-opc .em{font-size:24px;flex:none}.nv-opc b{display:block}.nv-opc small{color:#6a6a6a}
.nv-buscar{width:100%;border:1px solid #E4E4E4;border-radius:999px;padding:11px 16px;font:inherit;font-size:15px;background:#F7F7F7;margin:4px 0 6px}
.nv-seguir{border:0;border-radius:999px;background:var(--tinte,#EAF7EF);color:var(--esmeralda);font:inherit;font-weight:800;font-size:13.5px;padding:8px 14px;cursor:pointer;flex:none}
.nv-seguir.on{background:#F0F0F0;color:#6a6a6a}
/* Visor de historias (estado_viewer_screen) */
.nv-visor{position:fixed;inset:0;z-index:90;background:#000;display:none;color:#fff;user-select:none;-webkit-user-select:none}
.nv-visor.open{display:flex;align-items:center;justify-content:center}
.nv-marco{position:relative;width:min(100vw,calc(100dvh * 9 / 16));height:100dvh;max-height:100dvh;overflow:hidden;background:#111}
.nv-barras{position:absolute;top:max(8px,env(safe-area-inset-top));left:8px;right:8px;display:flex;gap:4px;z-index:3}
.nv-barras i{flex:1;height:3px;border-radius:3px;background:rgba(255,255,255,.35);overflow:hidden}
.nv-barras i b{display:block;height:100%;width:0;background:#fff}
.nv-cab{position:absolute;top:calc(max(8px,env(safe-area-inset-top)) + 12px);left:10px;right:10px;display:flex;align-items:center;gap:10px;z-index:3;min-width:0}
.nv-cab .av{width:38px;height:38px;border-radius:50%;object-fit:cover;background:#0E8F67;display:flex;align-items:center;justify-content:center;font-weight:800;flex:none;overflow:hidden}
.nv-cab .av img{width:100%;height:100%;object-fit:cover}
.nv-cab .q{flex:1;min-width:0}.nv-cab .q b{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;text-shadow:0 1px 3px rgba(0,0,0,.5)}
.nv-cab .q small{opacity:.85;font-size:12.5px;text-shadow:0 1px 3px rgba(0,0,0,.5)}
.nv-cab button{background:rgba(0,0,0,.25);border:0;color:#fff;width:38px;height:38px;border-radius:50%;font-size:20px;cursor:pointer;flex:none}
.nv-lienzo{position:absolute;inset:0;display:flex;align-items:center;justify-content:center}
.nv-lienzo img,.nv-lienzo video{max-width:100%;max-height:100%;width:100%;height:100%;object-fit:contain}
.nv-lienzo .texto{padding:28px;font-size:clamp(22px,5.5vw,30px);font-weight:700;text-align:center;line-height:1.3;overflow-wrap:anywhere;white-space:pre-wrap}
.nv-pie{position:absolute;left:0;right:0;bottom:92px;padding:10px 18px;text-align:center;background:linear-gradient(transparent,rgba(0,0,0,.55));overflow-wrap:anywhere;white-space:pre-wrap;z-index:2}
.nv-zona{position:absolute;top:80px;bottom:90px;z-index:1;width:35%;background:none;border:0;cursor:pointer}
.nv-zona.izq{left:0}.nv-zona.der{right:0;width:65%}
.nv-musica{position:absolute;left:12px;top:calc(max(8px,env(safe-area-inset-top)) + 62px);display:flex;align-items:center;gap:8px;background:rgba(0,0,0,.45);border-radius:999px;padding:5px 12px 5px 5px;max-width:calc(100% - 24px);z-index:3;font-size:13px;color:#fff;text-decoration:none}
.nv-musica img{width:26px;height:26px;border-radius:50%;object-fit:cover}
.nv-musica span{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;min-width:0}
.nv-pieBar{position:absolute;left:0;right:0;bottom:0;padding:10px 12px max(12px,env(safe-area-inset-bottom));display:flex;gap:8px;align-items:center;z-index:3;background:linear-gradient(transparent,rgba(0,0,0,.6))}
.nv-pieBar input{flex:1;min-width:0;border:1px solid rgba(255,255,255,.55);background:rgba(0,0,0,.25);color:#fff;border-radius:999px;padding:12px 16px;font:inherit;font-size:15px}
.nv-pieBar input::placeholder{color:rgba(255,255,255,.8)}
.nv-pieBar button{border:0;border-radius:999px;background:var(--esmeralda);color:#fff;font:inherit;font-weight:800;padding:12px 16px;cursor:pointer;flex:none}
.nv-pieBar .vistas{flex:1;background:none;text-align:center;font-weight:700}
.nv-menu{position:absolute;right:10px;top:calc(max(8px,env(safe-area-inset-top)) + 56px);background:#fff;color:#222;border-radius:14px;box-shadow:0 10px 30px rgba(0,0,0,.35);padding:6px;z-index:5;display:none;min-width:210px}
.nv-menu.open{display:block}
.nv-menu button,.nv-menu a{display:block;width:100%;text-align:left;border:0;background:none;padding:11px 12px;font:inherit;font-size:15px;border-radius:10px;cursor:pointer;color:inherit;text-decoration:none}
.nv-menu button:hover,.nv-menu a:hover{background:#F2F2F2}
.nv-lista-vistas{display:flex;flex-direction:column;gap:8px;text-align:left;max-height:50vh;overflow:auto}
.nv-lista-vistas div{display:flex;align-items:center;gap:10px}
.nv-lista-vistas .av{width:36px;height:36px;border-radius:50%;object-fit:cover;background:#0E8F67;color:#fff;display:inline-flex;align-items:center;justify-content:center;font-weight:800;flex:none;overflow:hidden}
.nv-lista-vistas .av img{width:100%;height:100%;object-fit:cover}
.nv-lista-vistas small{color:#6a6a6a;margin-left:auto}
/* Composer */
.nv-comp{border-radius:22px;min-height:min(62vh,560px);display:flex;flex-direction:column;align-items:center;justify-content:center;padding:26px 18px;color:#fff;position:relative;transition:background .2s}
.nv-comp textarea{width:100%;background:none;border:0;color:#fff;font:inherit;font-size:clamp(22px,5.5vw,30px);font-weight:700;text-align:center;resize:none;outline:none;min-height:160px}
.nv-comp textarea::placeholder{color:rgba(255,255,255,.75)}
.nv-cont{font-size:12.5px;opacity:.85;align-self:flex-end}
.nv-fondos{display:flex;flex-wrap:wrap;gap:10px;margin:14px 0}
.nv-fondos button{width:36px;height:36px;border-radius:50%;border:3px solid #fff;box-shadow:0 0 0 1px #E4E4E4;cursor:pointer}
.nv-fondos button.sel{box-shadow:0 0 0 2.5px #222}
.nv-prev{background:#111;border-radius:22px;min-height:260px;display:flex;align-items:center;justify-content:center;overflow:hidden;position:relative}
.nv-prev img,.nv-prev video{max-width:100%;max-height:70vh;display:block}
.nv-campo{width:100%;border:1px solid #E4E4E4;border-radius:14px;padding:12px 14px;font:inherit;font-size:15px;margin:10px 0 4px;background:#fff}
textarea.nv-campo{min-height:88px;resize:vertical}
.nv-lbl{font-weight:800;font-size:14px;margin:14px 0 2px;display:block}
.nv-ayuda{color:#6a6a6a;font-size:13px;margin:4px 0}
.nv-acc{display:flex;gap:10px;flex-wrap:wrap;margin-top:14px}
.nv-acc .btn{flex:1;min-width:min(180px,100%)}
.nv-mus{display:flex;align-items:center;gap:10px;border:1px solid #E4E4E4;border-radius:14px;padding:8px 10px;background:#fff;margin:10px 0;min-width:0}
.nv-mus img{width:44px;height:44px;border-radius:8px;object-fit:cover;flex:none}
.nv-mus .tx{flex:1;min-width:0}.nv-mus .tx b,.nv-mus .tx small{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.nv-mus .tx small{color:#6a6a6a}
.nv-mus button{border:0;background:#F2F2F2;border-radius:999px;padding:8px 12px;font:inherit;font-weight:700;cursor:pointer;flex:none}
.nv-mlista{max-height:46vh;overflow:auto;text-align:left;margin-top:8px}
.nv-mlista .nv-mus{cursor:pointer;margin:6px 0}
.nv-rango{width:100%;margin:10px 0 2px}
/* Canal */
.nv-canal-cab{text-align:center;padding:18px 14px 16px}
.nv-canal-cab .nv-av{width:96px;height:96px;font-size:44px;margin:0 auto 8px;display:flex}
.nv-canal-cab h1{font-size:24px;margin:4px 0;overflow-wrap:anywhere}
.nv-canal-cab p{color:#6a6a6a;margin:6px 0;overflow-wrap:anywhere;white-space:pre-wrap}
.nv-admin{display:inline-block;background:var(--tinte,#EAF7EF);color:var(--esmeralda);font-weight:800;border-radius:999px;padding:6px 12px;font-size:13px;margin-top:6px}
.nv-post{background:#fff;border-radius:16px;box-shadow:0 2px 8px rgba(0,0,0,.05);padding:12px;margin:10px 0;min-width:0}
.nv-post img,.nv-post video{width:100%;border-radius:12px;display:block;max-height:560px;object-fit:cover;background:#111}
.nv-post .t{white-space:pre-wrap;overflow-wrap:anywhere;margin:8px 2px 4px;font-size:15px;line-height:1.45}
.nv-post .t a{color:var(--esmeralda);font-weight:700;overflow-wrap:anywhere}
.nv-post .pie{display:flex;align-items:center;gap:8px;flex-wrap:wrap;color:#6a6a6a;font-size:12.5px;margin-top:6px}
.nv-post .pie .sp{flex:1}
.nv-reac{border:1px solid #E4E4E4;background:#fff;border-radius:999px;padding:5px 10px;font:inherit;font-size:13px;cursor:pointer}
.nv-reac.mia{background:var(--tinte,#EAF7EF);border-color:var(--esmeralda)}
.nv-borrar{border:0;background:none;color:#C13515;font:inherit;font-weight:700;cursor:pointer;padding:5px 6px}
.nv-emojis{display:flex;flex-wrap:wrap;gap:8px;justify-content:center}
.nv-emojis button{font-size:28px;border:0;background:#F4F4F4;border-radius:14px;width:52px;height:52px;cursor:pointer}
.nv-emojis button.sel{background:var(--tinte,#EAF7EF);box-shadow:inset 0 0 0 2px var(--esmeralda)}
.nv-escribir{position:sticky;bottom:0;background:#fff;border-top:1px solid #EEE;padding:10px 0 max(10px,env(safe-area-inset-bottom));display:flex;gap:8px;align-items:flex-end;z-index:5}
.nv-escribir textarea{flex:1;min-width:0;border:1px solid #E4E4E4;border-radius:18px;padding:11px 14px;font:inherit;font-size:15px;resize:none;max-height:140px;min-height:46px}
.nv-escribir .ico{border:0;background:#F2F2F2;border-radius:50%;width:44px;height:44px;font-size:20px;cursor:pointer;flex:none}
.nv-escribir .env{border:0;background:var(--esmeralda);color:#fff;border-radius:999px;height:44px;padding:0 16px;font:inherit;font-weight:800;cursor:pointer;flex:none}
.nv-foto-edit{display:flex;align-items:center;gap:14px;margin:6px 0 4px}
.nv-foto-edit .nv-av{width:84px;height:84px;font-size:38px;cursor:pointer}
@media (max-width:600px){.nv-top h1{font-size:24px}.nv-fab{padding:14px 16px}.nv-escribir .env{padding:0 12px}}
</style>"""

# Utilidades JS compartidas (hora relativa como el app, compresión 1600 px,
# cache device-first y pintado seguro).
_JS_COMUN = r"""<script>
(function(){
  var NV = window.NVU = {};
  NV.esc = function(s){ return String(s == null ? '' : s).replace(/[&<>"']/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]; }); };
  NV.hace = function(iso){ var d = (Date.now() - new Date(iso).getTime()) / 60000; if(!(d >= 0)) d = 0;
    if(d < 1) return 'ahora'; if(d < 60) return 'hace ' + Math.floor(d) + ' min'; if(d < 1440) return 'hace ' + Math.floor(d / 60) + ' h'; return 'hace ' + Math.floor(d / 1440) + ' d'; };
  NV.hora = function(iso){ var t = new Date(iso), h = new Date(); if(isNaN(t)) return '';
    var dias = Math.floor((new Date(h.getFullYear(), h.getMonth(), h.getDate()) - new Date(t.getFullYear(), t.getMonth(), t.getDate())) / 864e5);
    if(dias <= 0){ var hh = t.getHours() % 12 || 12; return hh + ':' + String(t.getMinutes()).padStart(2, '0') + (t.getHours() < 12 ? ' a. m.' : ' p. m.'); }
    if(dias === 1) return 'Ayer'; if(dias < 7) return ['dom','lun','mar','mié','jue','vie','sáb'][t.getDay()];
    return t.getDate() + '/' + (t.getMonth() + 1) + '/' + t.getFullYear(); };
  NV.av = function(nombre, foto, cls){ if(foto) return "<span class='" + (cls || 'av') + "'><img src='" + NV.esc(foto) + "' alt='' loading='lazy' referrerpolicy='no-referrer'></span>";
    return "<span class='" + (cls || 'av') + "'>" + NV.esc((String(nombre || '?').trim()[0] || '?').toUpperCase()) + "</span>"; };
  NV.ls = function(k, v){ try{ if(v === undefined){ var x = localStorage.getItem(k); return x ? JSON.parse(x) : null; } localStorage.setItem(k, JSON.stringify(v)); }catch(e){ return null; } };
  NV.post = function(url, body){ return fetch(url, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body || {})})
    .then(function(r){ return r.json().catch(function(){ return {ok: false}; }); }).catch(function(){ return {ok: false, mensaje: 'Revisa tu conexión.'}; }); };
  NV.subir = function(url, blob, tipo){ return fetch(url, {method: 'POST', headers: {'Content-Type': tipo || 'application/octet-stream'}, body: blob})
    .then(function(r){ return r.json().catch(function(){ return {ok: false, mensaje: r.status === 413 ? 'El archivo es muy pesado.' : 'No se pudo subir.'}; }); })
    .catch(function(){ return {ok: false, mensaje: 'No se pudo subir. Revisa tu conexión.'}; }); };
  NV.comprimir = function(file){ return new Promise(function(res, rej){ var img = new Image(), u = URL.createObjectURL(file);
    img.onload = function(){ var k = Math.min(1, 1600 / Math.max(img.width, img.height)), cv = document.createElement('canvas'); cv.width = Math.round(img.width * k); cv.height = Math.round(img.height * k);
      cv.getContext('2d').drawImage(img, 0, 0, cv.width, cv.height); URL.revokeObjectURL(u); cv.toBlob(function(b){ b ? res(b) : rej(new Error('img')); }, 'image/jpeg', 0.85); };
    img.onerror = function(){ URL.revokeObjectURL(u); rej(new Error('img')); }; img.src = u; }); };
  NV.duracion = function(file){ return new Promise(function(res){ var v = document.createElement('video'), u = URL.createObjectURL(file); v.preload = 'metadata';
    v.onloadedmetadata = function(){ var d = v.duration; URL.revokeObjectURL(u); res(isFinite(d) ? d : 0); }; v.onerror = function(){ URL.revokeObjectURL(u); res(-1); }; v.src = u; }); };
  NV.enlaces = function(t){ return NV.esc(t).replace(/((https?:\/\/|www\.)[^\s<]+)/gi, function(m){ var h = /^https?:/i.test(m) ? m : 'https://' + m; return "<a href='" + h + "' target='_blank' rel='noopener nofollow'>" + m + "</a>"; }); };
})();
</script>"""


def _js(obj) -> str:
    """JSON seguro dentro de <script> (sin cerrar la etiqueta)."""
    return json.dumps(obj, ensure_ascii=False).replace("</", "<\\/")


def _sin_login(request: Request, ruta: str, titulo: str, que: str) -> HTMLResponse:
    return sin_sesion(request, ruta, titulo, que)


# ═══════════════════════════ /novedades ═══════════════════════════════════════

_JS_NOVEDADES = r"""<script>
(function(){
  var U = window.NVU, C = window.NV_CFG, D = C.inicial, esc = U.esc;
  var OCULTOS = C.cache + '_ocultos', VISTO_CANAL = C.cache + '_canalvisto';
  function ocultos(){ return U.ls(OCULTOS) || []; }
  function vigente(it){ return Date.now() - new Date(it.creado).getTime() < 864e5; }
  function limpiar(d){ d.mi.items = d.mi.items.filter(vigente);
    d.autores = d.autores.filter(function(a){ a.items = a.items.filter(vigente); return a.items.length && ocultos().indexOf(a.k) < 0; }); return d; }
  function noVisto(a){ return a.items.some(function(i){ return !i.visto; }); }
  function miniatura(it){ if(!it) return '';
    if(it.tipo === 'foto' && it.media) return "<img src='" + esc(it.media) + "' alt='' loading='lazy'>";
    if(it.tipo === 'video' && it.media) return "<video src='" + esc(it.media) + "#t=0.1' muted playsinline preload='metadata'></video>";
    return "<span class='txt' style='background:" + esc(it.bg) + ";width:100%;height:100%;display:flex;align-items:center;justify-content:center'>" + esc((it.texto || '').slice(0, 30)) + "</span>"; }
  function aro(nombre, foto, it, cls){ var dentro = it ? miniatura(it) : (foto ? "<img src='" + esc(foto) + "' alt='' referrerpolicy='no-referrer'>" : esc((String(nombre || '?').trim()[0] || '?').toUpperCase()));
    return "<span class='nv-aro " + cls + "'><span class='in'>" + dentro + "</span>" + (cls.indexOf('mio') >= 0 && !it ? "<span class='mas'>+</span>" : '') + "</span>"; }
  function noLeidos(c){ var v = (U.ls(VISTO_CANAL) || {})[c.id]; return (c.nuevos || []).filter(function(t){ return !v || t > v; }).length; }
  function pintar(d){
    d = limpiar(JSON.parse(JSON.stringify(d)));
    window.NV_DATOS = d;
    var mi = d.mi, h = '';
    var ult = mi.items[mi.items.length - 1];
    var vistas = mi.items.reduce(function(s, i){ return s + (i.vistas || 0); }, 0);
    h += "<div class='nv-card'><button type='button' class='nv-fila' id='nvMiEstado'>" + aro(mi.nombre, mi.foto, ult, 'mio' + (ult ? ' nuevo' : ''))
      + "<span class='tx'><b>Mi estado</b><small>" + (ult ? esc(U.hace(ult.creado)) + (vistas ? ' · 👁 Visto por ' + vistas : '') : 'Toca para añadir una novedad') + "</small></span>"
      + (ult ? "<span class='der'><span class='nv-seguir' data-anadir='1'>＋ Añadir</span></span>" : '') + "</button></div>";
    h += "<div class='nv-sec'><span>Canales</span><a href='/canales'>Explorar</a></div><div class='nv-card'>";
    if(!d.canales.length){
      h += "<a class='nv-fila' href='/canales'><span class='nv-av'>📢</span><span class='tx'><b>Sigue canales</b><small>Mantente al día o crea el tuyo para difundir</small></span></a>";
    } else d.canales.forEach(function(c){ var n = noLeidos(c);
      h += "<a class='nv-fila' href='/canales/" + encodeURIComponent(c.id) + "'>" + (c.foto ? "<span class='nv-av'><img src='" + esc(c.foto) + "' alt='' loading='lazy'></span>" : "<span class='nv-av'>📢</span>")
        + "<span class='tx'><b>" + esc(c.nombre) + (c.mio ? " <span style='color:var(--esmeralda)'>✓</span>" : '') + "</b><small>" + esc(c.ultima || ('Se creó el canal "' + c.nombre + '"')) + "</small></span>"
        + "<span class='der'><span>" + esc(U.hora(c.ultima_en || c.creado)) + "</span>" + (n ? "<span class='nv-badge'>" + (n > 999 ? '+999' : n) + "</span>" : '') + "</span></a>"; });
    h += "</div><div class='nv-sec'><span>Actualizaciones recientes</span></div><div class='nv-card'>";
    if(!d.autores.length){
      h += "<div class='nv-vacio'><span class='em'>🌅</span>" + (d.sin_contactos ? 'Aún no tienes contactos. Guarda contactos en la app (o chatea desde <a href="/mensajes">Mensajes</a>) y verás aquí sus historias.' : 'Aún no hay novedades de tus contactos. Cuando alguien que conoces publique una historia, aparecerá aquí.') + "</div>";
    } else d.autores.forEach(function(a, i){ var u = a.items[a.items.length - 1];
      h += "<button type='button' class='nv-fila' data-autor='" + i + "'>" + aro(a.nombre, a.foto, u, noVisto(a) ? 'nuevo' : '') + "<span class='tx'><b>" + esc(a.nombre) + "</b><small>" + esc(U.hace(u.creado)) + "</small></span></button>"; });
    h += "</div>";
    document.getElementById('nvLista').innerHTML = h;
  }
  document.addEventListener('click', function(ev){
    var t = ev.target.closest('[data-anadir]'); if(t){ ev.preventDefault(); ev.stopPropagation(); menuAnadir(); return; }
    if(ev.target.closest('#nvMiEstado')){ var d = window.NV_DATOS; if(d.mi.items.length) NVVisor.abrir({mio: true, nombre: 'Mi estado', foto: d.mi.foto, items: d.mi.items}); else menuAnadir(); return; }
    var a = ev.target.closest('[data-autor]'); if(a){ NVVisor.abrir(window.NV_DATOS.autores[+a.dataset.autor]); }
  });
  function menuAnadir(){
    pcgAvisar({titulo: 'Añadir a mi estado', icono: '✨', confirmar: 'Cerrar', html:
      "<a class='nv-opc' href='/novedades/estado/nuevo?tipo=texto'><span class='em'>✍️</span><span><b>Escribir</b><small>Texto sobre un fondo de color</small></span></a>"
      + "<a class='nv-opc' href='/novedades/estado/nuevo?tipo=foto'><span class='em'>📷</span><span><b>Foto</b><small>De tu galería o la cámara</small></span></a>"
      + "<a class='nv-opc' href='/novedades/estado/nuevo?tipo=video'><span class='em'>🎥</span><span><b>Video</b><small>Hasta 30 segundos</small></span></a>"});
  }
  window.NVMenuAnadir = menuAnadir;
  var fab = document.getElementById('nvFab'); if(fab) fab.onclick = menuAnadir;
  window.NVRefrescar = function(){ return fetch('/web/novedades/datos', {headers: {'Accept': 'application/json'}}).then(function(r){ return r.json(); }).then(function(j){ if(j && j.ok){ U.ls(C.cache, j); pintar(j); } }).catch(function(){}); };
  window.NVOcultar = function(k){ var o = ocultos(); if(o.indexOf(k) < 0) o.push(k); U.ls(OCULTOS, o); pintar(U.ls(C.cache) || D); };
  // Device-first: pinta YA (datos de la página o lo guardado) y refresca en segundo plano.
  U.ls(C.cache, D); pintar(D);
  window.addEventListener('pageshow', function(ev){ if(ev.persisted){ var c = U.ls(C.cache); if(c) pintar(c); NVRefrescar(); } });
  setInterval(function(){ if(!document.hidden && !document.querySelector('.nv-visor.open')) NVRefrescar(); }, 60000);
  document.addEventListener('visibilitychange', function(){ if(!document.hidden) NVRefrescar(); });
})();
</script>"""

_JS_VISOR = r"""<script>
(function(){
  var U = window.NVU, esc = U.esc, V = document.getElementById('nvVisor');
  var st = {a: null, i: 0, t0: 0, dur: 5000, pausa: false, trans: 0, raf: 0};
  var audio = new Audio(); audio.preload = 'none';
  function $(id){ return document.getElementById(id); }
  function item(){ return st.a.items[st.i]; }
  function barras(){ var h = ''; st.a.items.forEach(function(_, k){ h += "<i><b style='width:" + (k < st.i ? 100 : 0) + "%'></b></i>"; }); $('nvBarras').innerHTML = h; }
  function marcar(it){ if(st.a.mio || it.visto) return; it.visto = true; U.post('/web/novedades/visto', {id: it.id}); }
  function mostrar(){
    cancelAnimationFrame(st.raf); audio.pause(); var it = item(); if(!it){ cerrar(); return; }
    barras(); var L = $('nvLienzo'), dur = 5000; L.style.background = '#111';
    if(it.tipo === 'foto'){ L.innerHTML = "<img src='" + esc(it.media) + "' alt=''>"; }
    else if(it.tipo === 'video'){ L.innerHTML = "<video id='nvVid' src='" + esc(it.media) + "' playsinline autoplay" + (it.musica ? ' muted' : '') + "></video>"; dur = 0; }
    else { L.style.background = it.bg; L.innerHTML = "<div class='texto'>" + esc(it.texto) + "</div>"; }
    if(it.musica) dur = 15000;
    $('nvPie').style.display = (it.tipo !== 'texto' && it.texto) ? '' : 'none'; $('nvPie').textContent = it.tipo !== 'texto' ? it.texto : '';
    $('nvHace').textContent = U.hace(it.creado);
    var m = $('nvMusica');
    if(it.musica){ var mu = it.musica, url = mu.track || ('https://open.spotify.com/search/' + encodeURIComponent(mu.titulo + ' ' + mu.artista));
      m.href = url; m.style.display = ''; m.innerHTML = (mu.art ? "<img src='" + esc(mu.art) + "' alt=''>" : '🎵') + "<span>🎵 " + esc(mu.titulo) + ' · ' + esc(mu.artista) + " · " + (mu.track ? 'Apple Music' : 'Spotify') + "</span>";
      audio.src = mu.preview; audio.currentTime = 0; audio.addEventListener('loadedmetadata', function f(){ audio.removeEventListener('loadedmetadata', f); try{ audio.currentTime = (mu.inicio || 0) / 1000; }catch(e){} }); audio.play().catch(function(){});
    } else { m.style.display = 'none'; audio.removeAttribute('src'); }
    if(st.a.mio){ $('nvVistas').textContent = '👁 Visto por ' + (it.vistas || 0); }
    st.dur = dur; st.trans = 0; st.t0 = performance.now(); st.pausa = false; marcar(it);
    var vid = $('nvVid');
    if(vid){ vid.onloadedmetadata = function(){ st.dur = Math.min(30000, Math.max(1000, (vid.duration || 5) * 1000)); st.t0 = performance.now() - vid.currentTime * 1000; };
      vid.onended = function(){ sig(); }; vid.onerror = function(){ st.dur = 5000; st.t0 = performance.now(); }; st.dur = 30000; }
    tick();
  }
  function tick(){ st.raf = requestAnimationFrame(function(){ if(!st.a) return;
    if(!st.pausa){ var el = st.trans + (performance.now() - st.t0), p = Math.min(1, el / st.dur), b = document.querySelectorAll('#nvBarras i b')[st.i];
      var vid = $('nvVid'); if(vid && vid.duration && isFinite(vid.duration)) p = Math.min(1, vid.currentTime * 1000 / st.dur);
      if(b) b.style.width = (p * 100) + '%'; if(p >= 1){ sig(); return; } }
    tick(); }); }
  function pausar(){ if(st.pausa || !st.a) return; st.pausa = true; st.trans += performance.now() - st.t0; var v = $('nvVid'); if(v) v.pause(); audio.pause(); }
  function reanudar(){ if(!st.pausa || !st.a) return; st.pausa = false; st.t0 = performance.now(); var v = $('nvVid'); if(v) v.play().catch(function(){}); if(item() && item().musica) audio.play().catch(function(){}); }
  function sig(){ if(st.i < st.a.items.length - 1){ st.i++; mostrar(); } else cerrar(); }
  function ant(){ if(st.i > 0){ st.i--; mostrar(); } else { st.trans = 0; st.t0 = performance.now(); } }
  function cerrar(){ cancelAnimationFrame(st.raf); audio.pause(); V.classList.remove('open'); $('nvLienzo').innerHTML = ''; $('nvMenu').classList.remove('open'); document.body.style.overflow = ''; st.a = null; if(window.NVRefrescar) NVRefrescar(); }
  window.NVVisor = {abrir: function(a){ if(!a || !a.items.length) return; st.a = a; st.i = a.mio ? 0 : Math.max(0, a.items.findIndex(function(x){ return !x.visto; })); if(st.i < 0) st.i = 0;
    $('nvAv').innerHTML = a.foto ? "<img src='" + esc(a.foto) + "' alt='' referrerpolicy='no-referrer'>" : esc((String(a.nombre || '?')[0] || '?').toUpperCase());
    $('nvNom').textContent = a.mio ? 'Mi estado' : a.nombre; $('nvResp').style.display = a.mio ? 'none' : 'flex'; $('nvVistas').style.display = a.mio ? '' : 'none';
    var mh = a.mio ? "<button type='button' data-m='vistas'>👁 Ver quién lo vio</button><button type='button' data-m='eliminar'>🗑 Eliminar</button>"
      : "<a href='/mensajes/nuevo?persona=" + encodeURIComponent(a.ref) + "'>💬 Mensaje</a><button type='button' data-m='ocultar'>🙈 Ocultar sus historias</button><button type='button' data-m='reportar'>🚩 Reportar</button>";
    $('nvMenu').innerHTML = mh; V.classList.add('open'); document.body.style.overflow = 'hidden'; mostrar(); }};
  $('nvIzq').onclick = function(){ ant(); }; $('nvDer').onclick = function(){ sig(); };
  ['nvIzq', 'nvDer'].forEach(function(id){ var z = $(id), tm = 0;
    z.addEventListener('pointerdown', function(){ tm = setTimeout(pausar, 180); });
    z.addEventListener('pointerup', function(ev){ clearTimeout(tm); if(st.pausa){ ev.preventDefault(); reanudar(); z.dataset.skip = '1'; } });
    z.addEventListener('click', function(ev){ if(z.dataset.skip){ delete z.dataset.skip; ev.stopImmediatePropagation(); } }, true); });
  $('nvCerrar').onclick = cerrar;
  $('nvMas').onclick = function(ev){ ev.stopPropagation(); var m = $('nvMenu'); m.classList.toggle('open'); if(m.classList.contains('open')) pausar(); else reanudar(); };
  $('nvMenu').addEventListener('click', async function(ev){ var b = ev.target.closest('[data-m]'); if(!b) return; $('nvMenu').classList.remove('open'); var it = item(), a = st.a;
    if(b.dataset.m === 'vistas') return verVistas(it);
    if(b.dataset.m === 'eliminar'){ var ok = await pcgConfirmar({titulo: 'Eliminar historia', mensaje: '¿Quieres eliminar esta historia? Nadie más podrá verla.', confirmar: 'Eliminar', destructivo: true});
      if(!ok) return reanudar(); pcgCargando('Eliminando…'); var j = await U.post('/web/novedades/estado/' + encodeURIComponent(it.id) + '/eliminar'); pcgCargando(false);
      if(!j.ok){ pcgAvisar({titulo: 'No se pudo eliminar', mensaje: j.mensaje || 'Inténtalo de nuevo.'}); return reanudar(); }
      a.items.splice(st.i, 1); pcgToast('Historia eliminada'); if(!a.items.length) return cerrar(); if(st.i >= a.items.length) st.i = a.items.length - 1; return mostrar(); }
    if(b.dataset.m === 'ocultar'){ var ok2 = await pcgConfirmar({titulo: 'Ocultar sus historias', mensaje: 'Dejarás de ver las historias de ' + a.nombre + ' en este navegador. No se le avisa.', confirmar: 'Ocultar', icono: '🙈'});
      if(!ok2) return reanudar(); cerrar(); return window.NVOcultar && NVOcultar(a.k); }
    if(b.dataset.m === 'reportar'){ await pcgAvisar({titulo: 'Gracias', icono: '🚩', mensaje: 'Recibimos tu reporte de esta historia. Nuestro equipo la revisará.'}); return reanudar(); } });
  $('nvVistas').onclick = function(){ verVistas(item()); };
  async function verVistas(it){ pausar(); var j = await fetch('/web/novedades/estado/' + encodeURIComponent(it.id) + '/vistas').then(function(r){ return r.json(); }).catch(function(){ return {ok: false}; });
    var h = '';
    if(!j.ok) h = '<p>No se pudo cargar. Revisa tu conexión.</p>';
    else if(!j.vistas.length) h = '<p>Todavía nadie ha visto esta historia.</p>';
    else { h = "<div class='nv-lista-vistas'>"; j.vistas.forEach(function(v){ h += '<div>' + U.av(v.nombre, v.foto, 'av') + '<b>' + esc(v.nombre) + '</b><small>' + esc(U.hace(v.en)) + '</small></div>'; }); h += '</div>'; }
    await pcgAvisar({titulo: 'Visto por ' + (j.ok ? j.vistas.length : 0), icono: '👁', html: h}); reanudar(); }
  var inp = $('nvRespTxt');
  inp.addEventListener('focus', pausar);
  $('nvRespForm').onsubmit = async function(ev){ ev.preventDefault(); var t = inp.value.trim(); if(!t) return; var it = item(); inp.value = ''; inp.blur();
    var j = await U.post('/web/novedades/responder', {id: it.id, texto: t}); pcgToast(j.ok ? 'Respuesta enviada' : (j.mensaje || 'No se pudo enviar')); reanudar(); };
  document.addEventListener('keydown', function(ev){ if(!st.a || document.activeElement === inp || document.querySelector('.pcg-dlg.open')) return;
    if(ev.key === 'Escape') cerrar(); else if(ev.key === 'ArrowRight') sig(); else if(ev.key === 'ArrowLeft') ant(); else if(ev.key === ' '){ ev.preventDefault(); st.pausa ? reanudar() : pausar(); } });
  document.addEventListener('visibilitychange', function(){ if(document.hidden) pausar(); });
})();
</script>"""

_VISOR_HTML = ("<div class='nv-visor' id='nvVisor' aria-modal='true' role='dialog'><div class='nv-marco'>"
               "<div class='nv-barras' id='nvBarras'></div>"
               "<div class='nv-cab'><span class='av' id='nvAv'></span><span class='q'><b id='nvNom'></b><small id='nvHace'></small></span>"
               "<button type='button' id='nvMas' aria-label='Más opciones'>⋮</button><button type='button' id='nvCerrar' aria-label='Cerrar'>✕</button></div>"
               "<a class='nv-musica' id='nvMusica' target='_blank' rel='noopener' style='display:none'></a>"
               "<div class='nv-menu' id='nvMenu'></div>"
               "<div class='nv-lienzo' id='nvLienzo'></div>"
               "<button type='button' class='nv-zona izq' id='nvIzq' aria-label='Anterior'></button>"
               "<button type='button' class='nv-zona der' id='nvDer' aria-label='Siguiente'></button>"
               "<div class='nv-pie' id='nvPie' style='display:none'></div>"
               "<form class='nv-pieBar' id='nvRespForm'><span id='nvResp' style='display:flex;gap:8px;flex:1;min-width:0'>"
               "<input id='nvRespTxt' maxlength='1000' placeholder='Responder…' autocomplete='off'><button type='submit'>Enviar</button></span>"
               "<button type='button' class='vistas' id='nvVistas' style='display:none'></button></form>"
               "</div></div>")


@router.get("/novedades", response_class=HTMLResponse)
def pagina_novedades(request: Request) -> HTMLResponse:
    """`novedades_screen.dart` + visor (`estado_viewer_screen.dart`)."""
    ses = sesion.de_request(request)
    if not ses or not ses.get("email"):
        return _sin_login(request, "/novedades", "Novedades", "Ver y publicar novedades")
    yo = _low(ses["email"])
    _limpiar_en_segundo_plano(yo)
    d = datos_novedades(yo, ses)
    cfg = {"cache": _clave_cache(yo, "nov"), "inicial": d}
    cuerpo = (_CSS + "<div class='nv-wrap'><div class='nv-top'><h1>Novedades</h1>"
              "<a class='btn sec' href='/canales'>📢 Canales</a></div><div id='nvLista'></div></div>"
              "<button type='button' class='nv-fab' id='nvFab' aria-label='Añadir a mi estado'>📷 Mi estado</button>"
              + _VISOR_HTML
              + f"<script>window.NV_CFG = {_js(cfg)};</script>"
              + _JS_COMUN + _JS_NOVEDADES + _JS_VISOR)
    return ui.shell("Novedades", cuerpo, sesion=ses, titulo_tab="Novedades · Pichangol")


@router.get("/web/novedades/datos")
def api_novedades(request: Request) -> JSONResponse:
    ses, err = _ses_o_401(request)
    if err:
        return err
    return JSONResponse(datos_novedades(_low(ses["email"]), ses), headers={"Cache-Control": "no-store"})


def _puedo_ver(est: dict | None, yo: str) -> bool:
    """Regla del app: mis historias o las de MIS contactos (no bloqueados), vigentes."""
    if not est:
        return False
    if (_dt(est.get("creado_en")) or _ahora()) <= _ahora() - VIGENCIA:
        return False
    if est["autor_email"] == yo:
        return True
    ag = agenda_de(yo)
    return est["autor_email"] in (ag.get("contactos") or []) and est["autor_email"] not in (ag.get("bloqueados") or [])


@router.post("/web/novedades/visto")
def api_visto(request: Request, body: dict = Body(default_factory=dict)) -> JSONResponse:
    """`appState.marcarEstadoVisto` → `EstadosRepo.marcarVisto`."""
    ses, err = _ses_o_401(request)
    if err:
        return err
    yo = _low(ses["email"])
    est = estado(str(body.get("id") or ""))
    if not _puedo_ver(est, yo):
        return _mal("Esta historia ya no está disponible.", 404, "no_encontrado")
    if est["autor_email"] == yo:
        return JSONResponse({"ok": True})
    return JSONResponse({"ok": marcar_visto(est["id"], yo)})


@router.post("/web/novedades/responder")
def api_responder(request: Request, body: dict = Body(default_factory=dict)) -> JSONResponse:
    """`_enviarResp`: mensaje DIRECTO al autor citando la historia."""
    ses, err = _ses_o_401(request)
    if err:
        return err
    yo = _low(ses["email"])
    texto = str(body.get("texto") or "").strip()[:1000]
    if not texto:
        return _mal("Escribe tu respuesta.")
    est = estado(str(body.get("id") or ""))
    if not _puedo_ver(est, yo) or est["autor_email"] == yo:
        return _mal("Esta historia ya no está disponible.", 404, "no_encontrado")
    otro = est["autor_email"]
    ag = agenda_de(yo)
    if otro in (ag.get("bloqueados") or []):
        return _mal("Bloqueaste a este contacto.", 403, "bloqueado")
    tipo = est.get("tipo") or "texto"
    resp_texto = (est.get("texto") or ("📷 Foto" if tipo == "foto" else "🎥 Video")) if tipo in ("foto", "video") else (est.get("texto") or "")
    pf = perfiles([otro])
    fila = {"id": f"msg_{_us()}", "hilo": hilo_directo(yo, otro), "tipo": "directo", "ref_id": "", "academia_id": "",
            "cuenta_email": otro, "autor_email": yo, "autor_nombre": _mi_nombre(yo, ses), "es_profe": False, "texto": texto,
            "media_url": "", "resp_texto": resp_texto[:300], "resp_autor": _nombre_de(otro, ag, pf, est.get("autor_nombre") or ""),
            "resp_media": (est.get("foto_url") or "") if tipo == "foto" else ""}
    ok = insertar_mensaje(fila) is not None
    return JSONResponse({"ok": ok, **({} if ok else {"mensaje": "No se pudo enviar. Revisa tu conexión."})},
                        status_code=200 if ok else 503)


@router.get("/web/novedades/estado/{estado_id}/vistas")
def api_vistas(request: Request, estado_id: str) -> JSONResponse:
    """"Ver quién lo vio" (solo el autor)."""
    ses, err = _ses_o_401(request)
    if err:
        return err
    yo = _low(ses["email"])
    est = estado(estado_id)
    if not est or est["autor_email"] != yo:
        return _mal("No encontramos esta historia.", 404, "no_encontrado")
    vs = vistas_de([estado_id]).get(estado_id) or []
    ag = agenda_de(yo)
    pf = perfiles([v[0] for v in vs])
    return JSONResponse({"ok": True, "vistas": [{"nombre": _nombre_de(em, ag, pf), "foto": (pf.get(em) or {}).get("foto_url") or "",
                                                 "en": _iso(en)} for em, en in vs]})


@router.post("/web/novedades/estado/{estado_id}/eliminar")
def api_eliminar_estado(request: Request, estado_id: str) -> JSONResponse:
    ses, err = _ses_o_401(request)
    if err:
        return err
    if not borrar_estado(estado_id, _low(ses["email"])):
        return _mal("No encontramos esta historia.", 404, "no_encontrado")
    return JSONResponse({"ok": True})


# ── Publicar (composer) ──────────────────────────────────────────────────────

def _validar_media(datos_: bytes, tipo: str, tope_seg: int) -> str:
    """'' si vale; si no, el motivo (mismos topes del app)."""
    if not datos_:
        return "No llegó el archivo."
    if tipo == "foto":
        if not _es_jpeg(datos_) or len(datos_) > FOTO_MAX:
            return "Sube una foto JPG de hasta 6 MB."
        return ""
    if len(datos_) > VIDEO_MAX:
        return "El video es muy pesado. Graba uno más corto."
    dur = duracion_mp4(datos_)
    if dur is None:
        return "Ese video no se puede usar. Sube un MP4 grabado con tu celular."
    if dur > tope_seg + 1.5:
        return f"El video dura más de {tope_seg} segundos. Recórtalo o graba uno más corto."
    return ""


def _subir_estado(ses: dict, tipo: str, datos_: bytes) -> JSONResponse:
    if tipo not in ("foto", "video"):
        return _mal("Tipo inválido.")
    motivo = _validar_media(datos_, tipo, VIDEO_ESTADO_SEG)
    if motivo:
        return _mal(motivo)
    if not almacen.disponible():
        return _mal("La subida de fotos y videos no está disponible en este momento.", 503, "sin_storage")
    eid = f"st_{_us()}"
    ext, ct = ("jpg", "image/jpeg") if tipo == "foto" else ("mp4", "video/mp4")
    url = almacen.subir("estados", f"{eid}.{ext}", datos_, ct, max_bytes=VIDEO_MAX)
    if not url:
        return _mal("No se pudo subir. Inténtalo de nuevo.", 502, "subida")
    return JSONResponse({"ok": True, "id": eid, "url": url, "tk": _firma(_low(ses["email"]), eid, url)})


@router.post("/web/novedades/estado/subir")
async def api_subir_estado(request: Request, tipo: str = "foto") -> JSONResponse:
    """Paso 1 de publicar foto/video: `EstadosRepo.subirFoto` / `subirVideo`."""
    ses, err = _ses_o_401(request)
    if err:
        return err
    datos_ = await request.body()
    return await run_in_threadpool(_subir_estado, ses, tipo, datos_)


def _musica_de(m) -> dict:
    """Pista elegida (de iTunes, como `MusicaService`): solo URLs https de Apple."""
    if not isinstance(m, dict):
        return {}
    prev = str(m.get("preview") or "")
    if not prev.startswith("https://") or "apple.com" not in urllib.parse.urlparse(prev).netloc:
        return {}
    art = str(m.get("art") or "")
    track = str(m.get("track") or "")
    try:
        ini = max(0, min(25000, int(m.get("inicio") or 0)))
    except Exception:  # noqa: BLE001
        ini = 0
    return {"musica_titulo": str(m.get("titulo") or "")[:120], "musica_artista": str(m.get("artista") or "")[:120],
            "musica_preview": prev[:500], "musica_art": art[:500] if art.startswith("https://") else "",
            "musica_inicio_ms": ini, "musica_track_url": track[:500] if track.startswith("https://") else ""}


@router.post("/web/novedades/estado")
def api_publicar_estado(request: Request, body: dict = Body(default_factory=dict)) -> JSONResponse:
    """`publicarEstadoTexto/Foto/Video`: la fila de `Estado.toRow`."""
    ses, err = _ses_o_401(request)
    if err:
        return err
    yo = _low(ses["email"])
    tipo = str(body.get("tipo") or "texto")
    musica = _musica_de(body.get("musica"))
    fila = {"autor_email": yo, "autor_nombre": _mi_nombre(yo, ses), "tipo": tipo, **musica}
    if tipo == "texto":
        texto = str(body.get("texto") or "").strip()
        if not texto:
            return _mal("Escribe algo para tu estado.")
        if len(texto) > TEXTO_MAX:
            return _mal(f"Máximo {TEXTO_MAX} caracteres.")
        try:
            bg = int(body.get("bg") or BG_DEFECTO)
        except Exception:  # noqa: BLE001
            bg = BG_DEFECTO
        fila.update({"id": f"st_{_us()}", "texto": texto, "foto_url": "", "bg": bg if bg in FONDOS else BG_DEFECTO})
    elif tipo in ("foto", "video"):
        eid, url, tk = str(body.get("id") or ""), str(body.get("url") or ""), str(body.get("tk") or "")
        ext = "jpg" if tipo == "foto" else "mp4"
        if (not _RE_ID_ESTADO.match(eid) or not _es_media_de(url, "estados", f"{eid}.{ext}")
                or not hmac.compare_digest(tk, _firma(yo, eid, url))):
            return _mal("Vuelve a subir la foto o el video.", 400, "media_invalida")
        pie = str(body.get("texto") or "").strip()
        if len(pie) > PIE_MAX:
            return _mal(f"El pie admite hasta {PIE_MAX} caracteres.")
        fila.update({"id": eid, "texto": pie, "foto_url": url, "bg": BG_DEFECTO})
    else:
        return _mal("Tipo inválido.")
    if not insertar_estado(fila):
        return _mal("No se pudo publicar. Revisa tu conexión.", 503, "guardar")
    return JSONResponse({"ok": True, "id": fila["id"]})


_MUSICA_CACHE: dict[str, tuple[float, list]] = {}


def _itunes(url: str) -> dict | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Pichangol/1.0"})
        with urllib.request.urlopen(req, timeout=8) as r:  # noqa: S310
            return json.loads(r.read().decode("utf-8"))
    except Exception:  # noqa: BLE001
        return None


def buscar_musica(q: str, pais: str = "pe") -> list[dict]:
    """`MusicaService.buscar` (vacío → `destacadas` del país). Caché 10 min."""
    q = (q or "").strip()[:80]
    clave = f"{pais}|{q.lower()}"
    hit = _MUSICA_CACHE.get(clave)
    if hit and time.time() - hit[0] < 600:
        return hit[1]
    out: list[dict] = []
    if q:
        d = _itunes("https://itunes.apple.com/search?media=music&entity=song&limit=25&term=" + urllib.parse.quote_plus(q)) or {}
        for m in d.get("results") or []:
            if not m.get("previewUrl"):
                continue
            out.append({"titulo": str(m.get("trackName") or ""), "artista": str(m.get("artistName") or ""),
                        "preview": str(m["previewUrl"]), "art": str(m.get("artworkUrl100") or "").replace("100x100bb", "300x300bb"),
                        "track": str(m.get("trackViewUrl") or "")})
    else:
        d = _itunes(f"https://itunes.apple.com/{pais}/rss/topsongs/limit=30/json") or {}
        for m in ((d.get("feed") or {}).get("entry") or []):
            try:
                prev = next((l["attributes"]["href"] for l in m.get("link") or [] if (l.get("attributes") or {}).get("rel") == "enclosure"), "")
                if not prev:
                    continue
                imgs = m.get("im:image") or []
                out.append({"titulo": str((m.get("im:name") or {}).get("label") or ""), "artista": str((m.get("im:artist") or {}).get("label") or ""),
                            "preview": prev, "art": str(imgs[-1].get("label") or "") if imgs else "",
                            "track": str((m.get("id") or {}).get("label") or "")})
            except Exception:  # noqa: BLE001
                continue
    if out:
        _MUSICA_CACHE[clave] = (time.time(), out)
    return out


@router.get("/web/novedades/musica")
def api_musica(request: Request, q: str = "") -> JSONResponse:
    ses, err = _ses_o_401(request)
    if err:
        return err
    pais = "pe"
    try:
        from web.jugador_billetera import pais_billetera
        pais = (pais_billetera(_low(ses["email"]))[0] or "PE").lower()
    except Exception:  # noqa: BLE001
        pass
    return JSONResponse({"ok": True, "pistas": buscar_musica(q, pais)})


_JS_COMPOSER = r"""<script>
(function(){
  var U = window.NVU, C = window.NV_COMP, esc = U.esc, $ = function(id){ return document.getElementById(id); };
  var st = {bg: C.fondos[0], musica: null, blob: null, tipoBlob: '', listo: false};
  function pintarMusica(){ var b = $('nvMusBox'); if(!st.musica){ b.innerHTML = "<button type='button' class='btn sec' id='nvMusBtn'>🎵 Añadir música</button>"; return; }
    var m = st.musica; b.innerHTML = "<div class='nv-mus'>" + (m.art ? "<img src='" + esc(m.art) + "' alt=''>" : '') + "<span class='tx'><b>🎵 " + esc(m.titulo) + "</b><small>" + esc(m.artista) + " · desde el segundo " + Math.round((m.inicio || 0) / 1000) + "</small></span><button type='button' id='nvMusQuitar'>Quitar</button></div>"; }
  var audio = new Audio();
  async function elegirMusica(){
    var h = "<input class='nv-buscar' id='nvMusQ' placeholder='Busca una canción o artista' autocomplete='off'><div class='nv-mlista' id='nvMusLista'><p class='nv-ayuda'>Cargando destacadas…</p></div>";
    var p = pcgAvisar({titulo: 'Música para tu estado', icono: '🎵', confirmar: 'Cerrar', html: h});
    var lista = [], tm = 0, elegida = null;
    function pintar(ls){ lista = ls; var el = $('nvMusLista'); if(!el) return; if(!ls.length){ el.innerHTML = "<p class='nv-ayuda'>No encontramos canciones.</p>"; return; }
      el.innerHTML = ls.map(function(m, i){ return "<div class='nv-mus' data-i='" + i + "'>" + (m.art ? "<img src='" + esc(m.art) + "' alt='' loading='lazy'>" : '') + "<span class='tx'><b>" + esc(m.titulo) + "</b><small>" + esc(m.artista) + "</small></span><button type='button' data-oir='" + i + "'>▶</button></div>"; }).join(''); }
    function cargar(q){ fetch('/web/novedades/musica?q=' + encodeURIComponent(q || '')).then(function(r){ return r.json(); }).then(function(j){ pintar((j && j.pistas) || []); }).catch(function(){ pintar([]); }); }
    cargar('');
    $('nvMusQ').addEventListener('input', function(){ clearTimeout(tm); var v = this.value; tm = setTimeout(function(){ cargar(v); }, 400); });
    $('nvMusLista').addEventListener('click', function(ev){ var o = ev.target.closest('[data-oir]'); if(o){ ev.stopPropagation(); var m = lista[+o.dataset.oir]; if(audio.src === m.preview && !audio.paused){ audio.pause(); } else { audio.src = m.preview; audio.play().catch(function(){}); } return; }
      var f = ev.target.closest('[data-i]'); if(!f) return; elegida = lista[+f.dataset.i]; var ok = document.getElementById('pcgDlgOk'); if(ok) ok.click(); });
    await p; audio.pause(); if(elegida) recortar(elegida); }
  async function recortar(m){
    var h = "<div class='nv-mus'>" + (m.art ? "<img src='" + esc(m.art) + "' alt=''>" : '') + "<span class='tx'><b>" + esc(m.titulo) + "</b><small>" + esc(m.artista) + "</small></span></div>"
      + "<label class='nv-lbl' for='nvRango'>¿Desde qué segundo suena? <span id='nvRangoV'>0 s</span></label><input type='range' class='nv-rango' id='nvRango' min='0' max='15' step='1' value='0'><p class='nv-ayuda'>Se escuchan 15 segundos desde ahí.</p>";
    var p = pcgConfirmar({titulo: 'Elige el fragmento', icono: '✂️', confirmar: 'Usar esta canción', cancelar: 'Cancelar', html: h});
    var r = $('nvRango'); audio.src = m.preview; audio.play().catch(function(){});
    r.addEventListener('input', function(){ $('nvRangoV').textContent = r.value + ' s'; try{ audio.currentTime = +r.value; audio.play().catch(function(){}); }catch(e){} });
    var seg = 0; r.addEventListener('change', function(){ seg = +r.value; }); r.addEventListener('input', function(){ seg = +r.value; });
    var ok = await p; audio.pause(); if(!ok) return; st.musica = Object.assign({}, m, {inicio: seg * 1000}); pintarMusica(); }
  document.addEventListener('click', function(ev){ if(ev.target.id === 'nvMusBtn') elegirMusica(); if(ev.target.id === 'nvMusQuitar'){ st.musica = null; pintarMusica(); } });
  pintarMusica();
  // Texto
  if(C.tipo === 'texto'){
    var comp = $('nvComp'), ta = $('nvTexto');
    function fondo(v){ st.bg = v; comp.style.background = '#' + (v & 0xFFFFFF).toString(16).padStart(6, '0'); document.querySelectorAll('.nv-fondos button').forEach(function(b){ b.classList.toggle('sel', +b.dataset.bg === v); }); }
    document.querySelectorAll('.nv-fondos button').forEach(function(b){ b.onclick = function(){ fondo(+b.dataset.bg); }; }); fondo(st.bg);
    ta.addEventListener('input', function(){ $('nvCont').textContent = ta.value.length + '/' + C.textoMax; });
    ta.focus();
  } else {
    var inp = $('nvArchivo'), prev = $('nvPrev');
    inp.addEventListener('change', async function(){ var f = inp.files && inp.files[0]; if(!f) return; st.listo = false;
      if(C.tipo === 'foto'){ try{ st.blob = await U.comprimir(f); st.tipoBlob = 'image/jpeg'; prev.innerHTML = "<img src='" + URL.createObjectURL(st.blob) + "' alt=''>"; st.listo = true; }catch(e){ pcgAvisar({titulo: 'Foto no válida', mensaje: 'Elige una imagen JPG o PNG.'}); } }
      else { var d = await U.duracion(f);
        if(d < 0){ return pcgAvisar({titulo: 'Video no válido', mensaje: 'Tu navegador no puede leer este video. Sube un MP4 grabado con tu celular.'}); }
        if(d > C.videoSeg + 1.5){ inp.value = ''; return pcgAvisar({titulo: 'Video muy largo', icono: '⏱️', mensaje: 'Tu estado puede durar hasta ' + C.videoSeg + ' segundos. Recórtalo o graba uno más corto.'}); }
        if(f.size > C.videoMax){ inp.value = ''; return pcgAvisar({titulo: 'Video muy pesado', mensaje: 'El video pasa de ' + Math.round(C.videoMax / 1048576) + ' MB. Graba uno más corto.'}); }
        st.blob = f; st.tipoBlob = f.type || 'video/mp4'; prev.innerHTML = "<video src='" + URL.createObjectURL(f) + "' controls playsinline autoplay muted loop></video>"; st.listo = true; }
      $('nvPieBox').style.display = st.listo ? '' : 'none'; });
    $('nvElegir').onclick = function(){ inp.click(); };
    prev.onclick = function(ev){ if(!st.listo) inp.click(); };
  }
  $('nvPublicar').onclick = async function(){
    var body = {tipo: C.tipo, musica: st.musica};
    if(C.tipo === 'texto'){ body.texto = $('nvTexto').value.trim(); body.bg = st.bg; if(!body.texto) return pcgAvisar({titulo: 'Tu estado está vacío', mensaje: 'Escribe algo para publicar.'}); }
    else { if(!st.listo) return pcgAvisar({titulo: C.tipo === 'foto' ? 'Elige una foto' : 'Elige un video', mensaje: 'Primero selecciona lo que quieres publicar.'});
      pcgCargando(C.tipo === 'foto' ? 'Subiendo tu foto…' : 'Subiendo tu video…');
      var s = await U.subir('/web/novedades/estado/subir?tipo=' + C.tipo, st.blob, st.tipoBlob);
      if(!s.ok){ pcgCargando(false); return pcgAvisar({titulo: 'No se pudo subir', mensaje: s.mensaje || 'Inténtalo de nuevo.'}); }
      body.id = s.id; body.url = s.url; body.tk = s.tk; body.texto = $('nvPieTxt').value.trim(); }
    pcgCargando('Publicando…');
    var j = await U.post('/web/novedades/estado', body);
    if(!j.ok){ pcgCargando(false); return pcgAvisar({titulo: 'No se pudo publicar', mensaje: j.mensaje || 'Inténtalo de nuevo.'}); }
    pcgIr('/novedades', 'Publicado ✓'); };
})();
</script>"""


@router.get("/novedades/estado/nuevo", response_class=HTMLResponse)
def pagina_nuevo_estado(request: Request, tipo: str = "texto") -> HTMLResponse:
    """`estado_composer_screen.dart` (texto) y los composers de foto/video."""
    ses = sesion.de_request(request)
    if not ses or not ses.get("email"):
        return _sin_login(request, f"/novedades/estado/nuevo?tipo={quote(tipo)}", "Nuevo estado", "Publicar novedades")
    tipo = tipo if tipo in ("texto", "foto", "video") else "texto"
    cfg = {"tipo": tipo, "fondos": FONDOS, "textoMax": TEXTO_MAX, "videoSeg": VIDEO_ESTADO_SEG, "videoMax": VIDEO_MAX}
    tabs = "".join(f"<a class='chip{' sel' if t == tipo else ''}' href='/novedades/estado/nuevo?tipo={t}'>{et}</a>"
                   for t, et in (("texto", "✍️ Texto"), ("foto", "📷 Foto"), ("video", "🎥 Video")))
    if tipo == "texto":
        fondos = "".join(f"<button type='button' aria-label='Fondo {i + 1}' data-bg='{v}' style='background:{color_css(v)}'></button>"
                         for i, v in enumerate(FONDOS))
        medio = (f"<div class='nv-comp' id='nvComp'><textarea id='nvTexto' maxlength='{TEXTO_MAX}' placeholder='Escribe un estado'></textarea>"
                 f"<span class='nv-cont' id='nvCont'>0/{TEXTO_MAX}</span></div>"
                 f"<span class='nv-lbl'>Fondo</span><div class='nv-fondos'>{fondos}</div>")
    else:
        acepta = "image/*" if tipo == "foto" else "video/mp4,video/quicktime,video/*"
        medio = (f"<input type='file' id='nvArchivo' accept='{acepta}' hidden>"
                 f"<div class='nv-prev' id='nvPrev' style='cursor:pointer'><div class='nv-vacio' style='color:#ddd'><span class='em'>{'📷' if tipo == 'foto' else '🎥'}</span>"
                 f"{'Elige una foto de tu galería o tómala con la cámara' if tipo == 'foto' else f'Elige un video de hasta {VIDEO_ESTADO_SEG} segundos'}</div></div>"
                 f"<div class='nv-acc'><button type='button' class='btn sec' id='nvElegir'>{'📷 Elegir foto' if tipo == 'foto' else '🎥 Elegir video'}</button></div>"
                 f"<div id='nvPieBox' style='display:none'><label class='nv-lbl' for='nvPieTxt'>Añade un pie (opcional)</label>"
                 f"<input class='nv-campo' id='nvPieTxt' maxlength='{PIE_MAX}' placeholder='Escribe un pie…'></div>")
    cuerpo = (_CSS + "<div class='nv-wrap'><div class='nv-top'><h1>Nuevo estado</h1><a class='btn sec' href='/novedades'>Cancelar</a></div>"
              f"<div class='chips' style='margin:0 0 14px'>{tabs}</div>{medio}"
              "<div id='nvMusBox'></div>"
              "<p class='nv-ayuda'>Tu estado dura 24 horas y lo ven tus contactos.</p>"
              "<div class='nv-acc'><button type='button' class='btn lg' id='nvPublicar'>Publicar estado</button></div></div>"
              + f"<script>window.NV_COMP = {json.dumps(cfg)};</script>" + _JS_COMUN + _JS_COMPOSER)
    return ui.shell("Nuevo estado", cuerpo, sesion=ses, titulo_tab="Nuevo estado · Pichangol")


# ═══════════════════════════ /canales ═════════════════════════════════════════

_JS_CANALES = r"""<script>
(function(){
  var U = window.NVU, C = window.NV_CAN, esc = U.esc, q = '';
  function fila(c){ var sub = c.ultima || (c.seguidores + ' seguidores');
    return "<a class='nv-fila' href='/canales/" + encodeURIComponent(c.id) + "'>" + (c.foto ? "<span class='nv-av'><img src='" + esc(c.foto) + "' alt='' loading='lazy'></span>" : "<span class='nv-av'>📢</span>")
      + "<span class='tx'><b>" + esc(c.nombre) + (c.mio ? " <span style='color:var(--esmeralda)'>✓</span>" : '') + "</b><small>" + esc(sub) + "</small></span>"
      + (c.mio ? '' : c.sigo ? "<span class='nv-seguir on'>Siguiendo</span>" : "<button type='button' class='nv-seguir' data-seguir='" + esc(c.id) + "'>Seguir</button>") + "</a>"; }
  function pintar(d){ window.NV_CAN_D = d; var ok = function(c){ return !q || (c.nombre + ' ' + c.descripcion).toLowerCase().indexOf(q) >= 0; };
    var mis = d.canales.filter(function(c){ return c.mio && ok(c); }), sigo = d.canales.filter(function(c){ return c.sigo && !c.mio && ok(c); }), desc = d.canales.filter(function(c){ return !c.sigo && !c.mio && ok(c); });
    var h = '';
    if(!d.canales.length) h = "<div class='nv-card'><div class='nv-vacio'><span class='em'>📢</span>Aún no hay canales. Crea el primero para difundir novedades a tus seguidores.</div></div>";
    else if(!mis.length && !sigo.length && !desc.length) h = "<div class='nv-card'><div class='nv-vacio'>No hay canales que coincidan con «" + esc(q) + "».</div></div>";
    [['Mis canales', mis], ['Siguiendo', sigo], ['Descubrir canales', desc]].forEach(function(s){ if(!s[1].length) return; h += "<div class='nv-sec'><span>" + s[0] + "</span></div><div class='nv-card'>" + s[1].map(fila).join('') + "</div>"; });
    document.getElementById('nvCanales').innerHTML = h; }
  document.getElementById('nvBuscar').addEventListener('input', function(){ q = this.value.trim().toLowerCase(); pintar(window.NV_CAN_D); });
  document.addEventListener('click', async function(ev){ var b = ev.target.closest('[data-seguir]'); if(!b) return; ev.preventDefault(); ev.stopPropagation(); b.disabled = true;
    var j = await U.post('/web/canales/' + encodeURIComponent(b.dataset.seguir) + '/seguir', {seguir: true});
    if(!j.ok){ b.disabled = false; return pcgAvisar({titulo: 'No se pudo seguir', mensaje: j.mensaje || 'Inténtalo de nuevo.'}); }
    var d = window.NV_CAN_D; d.canales.forEach(function(c){ if(c.id === b.dataset.seguir){ c.sigo = true; c.seguidores++; } }); U.ls(C.cache, d); pintar(d); pcgToast('Ahora sigues este canal'); });
  var c0 = C.inicial; U.ls(C.cache, c0); pintar(c0);
  window.addEventListener('pageshow', function(ev){ if(ev.persisted){ var c = U.ls(C.cache); if(c) pintar(c); fetch('/web/canales/datos').then(function(r){ return r.json(); }).then(function(j){ if(j.ok){ U.ls(C.cache, j); pintar(j); } }).catch(function(){}); } });
})();
</script>"""


@router.get("/canales", response_class=HTMLResponse)
def pagina_canales(request: Request) -> HTMLResponse:
    """`canales_screen.dart`."""
    ses = sesion.de_request(request)
    if not ses or not ses.get("email"):
        return _sin_login(request, "/canales", "Canales", "Seguir y crear canales")
    yo = _low(ses["email"])
    cfg = {"cache": _clave_cache(yo, "canales"), "inicial": datos_canales(yo)}
    cuerpo = (_CSS + "<div class='nv-wrap'><div class='nv-top'><h1>Canales</h1><a class='btn' href='/canales/nuevo'>＋ Crear canal</a></div>"
              "<input class='nv-buscar' id='nvBuscar' type='search' placeholder='Buscar' autocomplete='off'>"
              "<div id='nvCanales'></div><p style='margin-top:18px'><a href='/novedades'>‹ Volver a Novedades</a></p></div>"
              + f"<script>window.NV_CAN = {_js(cfg)};</script>" + _JS_COMUN + _JS_CANALES)
    return ui.shell("Canales", cuerpo, sesion=ses, titulo_tab="Canales · Pichangol")


@router.get("/web/canales/datos")
def api_canales(request: Request) -> JSONResponse:
    ses, err = _ses_o_401(request)
    if err:
        return err
    return JSONResponse(datos_canales(_low(ses["email"])), headers={"Cache-Control": "no-store"})


_JS_FORM_CANAL = r"""<script>
(function(){
  var U = window.NVU, C = window.NV_FC, $ = function(id){ return document.getElementById(id); }, blob = null;
  $('nvFotoIn').addEventListener('change', async function(){ var f = this.files && this.files[0]; if(!f) return;
    try{ blob = await U.comprimir(f); $('nvFotoAv').innerHTML = "<img src='" + URL.createObjectURL(blob) + "' alt=''>"; }catch(e){ pcgAvisar({titulo: 'Foto no válida', mensaje: 'Elige una imagen JPG o PNG.'}); } });
  $('nvFotoAv').onclick = $('nvFotoBtn').onclick = function(){ $('nvFotoIn').click(); };
  ['nvNombre', 'nvDesc'].forEach(function(id){ var el = $(id), c = $(id + 'C'); el.addEventListener('input', function(){ c.textContent = el.value.length + '/' + el.maxLength; }); c.textContent = el.value.length + '/' + el.maxLength; });
  $('nvGuardar').onclick = async function(){ var nombre = $('nvNombre').value.trim(); if(!nombre){ $('nvNombre').focus(); return pcgAvisar({titulo: 'Falta el nombre', mensaje: 'Ponle un nombre a tu canal.'}); }
    pcgCargando(C.id ? 'Guardando canal…' : 'Creando canal…');
    var j = await U.post(C.id ? '/web/canales/' + encodeURIComponent(C.id) + '/editar' : '/web/canales/crear', {nombre: nombre, descripcion: $('nvDesc').value.trim()});
    if(!j.ok){ pcgCargando(false); return pcgAvisar({titulo: 'No se pudo guardar', mensaje: j.mensaje || 'Inténtalo de nuevo.'}); }
    if(blob){ var s = await U.subir('/web/canales/' + encodeURIComponent(j.id) + '/portada', blob, 'image/jpeg'); if(!s.ok) pcgToast(s.mensaje || 'No se pudo subir la foto'); }
    pcgIr('/canales/' + encodeURIComponent(j.id), 'Listo ✓'); };
})();
</script>"""


def _form_canal(ses: dict, c: dict | None) -> HTMLResponse:
    """`crear_canal_screen.dart` / `editar_canal_screen.dart`."""
    foto = (c or {}).get("foto_url") or ""
    av = f"<img src='{e(foto)}' alt=''>" if foto else "📢"
    titulo = "Editar canal" if c else "Crear canal"
    cuerpo = (_CSS + f"<div class='nv-wrap' style='max-width:600px'><div class='nv-top'><h1>{titulo}</h1>"
              f"<a class='btn sec' href='{'/canales/' + quote(c['id']) if c else '/canales'}'>Cancelar</a></div><div class='panel'>"
              "<input type='file' id='nvFotoIn' accept='image/*' hidden>"
              f"<div class='nv-foto-edit'><span class='nv-av' id='nvFotoAv' role='button' aria-label='Foto del canal'>{av}</span>"
              "<button type='button' class='btn sec' id='nvFotoBtn'>📷 Foto del canal</button></div>"
              "<label class='nv-lbl' for='nvNombre'>Nombre del canal</label>"
              f"<input class='nv-campo' id='nvNombre' maxlength='{CANAL_NOMBRE_MAX}' placeholder='Ej. Pichangol San Borja' value='{e((c or {}).get('nombre') or '')}'>"
              "<small class='nv-ayuda' id='nvNombreC' style='display:block;text-align:right'></small>"
              f"<label class='nv-lbl' for='nvDesc'>Descripción{'' if c else ' (opcional)'}</label>"
              f"<textarea class='nv-campo' id='nvDesc' maxlength='{CANAL_DESC_MAX}' placeholder='¿De qué trata tu canal?'>{e((c or {}).get('descripcion') or '')}</textarea>"
              "<small class='nv-ayuda' id='nvDescC' style='display:block;text-align:right'></small>"
              + ("" if c else "<p class='nv-ayuda'>Tú serás el administrador. Solo tú publicas; los seguidores ven tus novedades y pueden reaccionar.</p>")
              + f"<div class='nv-acc'><button type='button' class='btn lg' id='nvGuardar'>{'Guardar cambios' if c else '📢 Crear canal'}</button></div></div></div>"
              + f"<script>window.NV_FC = {json.dumps({'id': (c or {}).get('id') or ''})};</script>" + _JS_COMUN + _JS_FORM_CANAL)
    return ui.shell(titulo, cuerpo, sesion=ses, titulo_tab=f"{titulo} · Pichangol")


@router.get("/canales/nuevo", response_class=HTMLResponse)
def pagina_crear_canal(request: Request) -> HTMLResponse:
    ses = sesion.de_request(request)
    if not ses or not ses.get("email"):
        return _sin_login(request, "/canales/nuevo", "Crear canal", "Crear un canal")
    return _form_canal(ses, None)


def _validar_canal(body: dict) -> tuple[dict, str]:
    nombre = str(body.get("nombre") or "").strip()
    desc = str(body.get("descripcion") or "").strip()
    if not nombre:
        return {}, "Ponle un nombre a tu canal."
    if len(nombre) > CANAL_NOMBRE_MAX:
        return {}, f"El nombre admite hasta {CANAL_NOMBRE_MAX} caracteres."
    if len(desc) > CANAL_DESC_MAX:
        return {}, f"La descripción admite hasta {CANAL_DESC_MAX} caracteres."
    return {"nombre": nombre, "descripcion": desc}, ""


@router.post("/web/canales/crear")
def api_crear_canal(request: Request, body: dict = Body(default_factory=dict)) -> JSONResponse:
    """`CrearCanalScreen._crear`: id `ch_<µs>`, dueño = correo de la sesión."""
    ses, err = _ses_o_401(request)
    if err:
        return err
    campos, motivo = _validar_canal(body)
    if motivo:
        return _mal(motivo)
    cid = f"ch_{_us()}"
    if not crear_canal({"id": cid, "owner_email": _low(ses["email"]), "foto_url": "", **campos}):
        return _mal("No se pudo crear el canal. Revisa tu conexión.", 503, "guardar")
    return JSONResponse({"ok": True, "id": cid})


def _canal_mio(request: Request, canal_id: str):
    ses, err = _ses_o_401(request)
    if err:
        return None, None, err
    c = canal(canal_id)
    if not c or c["owner_email"] != _low(ses["email"]):
        return None, None, _mal("Este canal no es tuyo.", 404, "no_encontrado")
    return ses, c, None


@router.post("/web/canales/{canal_id}/editar")
def api_editar_canal(request: Request, canal_id: str, body: dict = Body(default_factory=dict)) -> JSONResponse:
    ses, c, err = _canal_mio(request, canal_id)
    if err:
        return err
    campos, motivo = _validar_canal(body)
    if motivo:
        return _mal(motivo)
    if not actualizar_canal(canal_id, ses["email"], campos):
        return _mal("No se pudo guardar. Revisa tu conexión.", 503, "guardar")
    return JSONResponse({"ok": True, "id": canal_id})


def _subir_portada(request: Request, canal_id: str, datos_: bytes) -> JSONResponse:
    ses, c, err = _canal_mio(request, canal_id)
    if err:
        return err
    motivo = _validar_media(datos_, "foto", 0)
    if motivo:
        return _mal(motivo)
    if not almacen.disponible():
        return _mal("La subida de fotos no está disponible en este momento.", 503, "sin_storage")
    url = almacen.subir("canales", f"{canal_id}/portada.jpg", datos_, "image/jpeg")
    if not url or not actualizar_canal(canal_id, ses["email"], {"foto_url": url}):
        return _mal("No se pudo subir la foto.", 502, "subida")
    return JSONResponse({"ok": True, "url": url})


@router.post("/web/canales/{canal_id}/portada")
async def api_portada(request: Request, canal_id: str) -> JSONResponse:
    datos_ = await request.body()
    return await run_in_threadpool(_subir_portada, request, canal_id, datos_)


@router.post("/web/canales/{canal_id}/seguir")
def api_seguir(request: Request, canal_id: str, body: dict = Body(default_factory=dict)) -> JSONResponse:
    ses, err = _ses_o_401(request)
    if err:
        return err
    c = canal(canal_id)
    if not c:
        return _mal("Este canal ya no existe.", 404, "no_encontrado")
    if c["owner_email"] == _low(ses["email"]):
        return _mal("Eres el administrador de este canal.")
    if not seguir(canal_id, ses["email"], bool(body.get("seguir", True))):
        return _mal("No se pudo actualizar. Revisa tu conexión.", 503, "guardar")
    return JSONResponse({"ok": True})


_JS_CANAL = r"""<script>
(function(){
  var U = window.NVU, C = window.NV_CD, esc = U.esc, $ = function(id){ return document.getElementById(id); };
  var VISTO = C.cacheVisto, EMOJIS = C.emojis, D = null;
  function cab(c){ var h = "<div class='nv-card nv-canal-cab'>" + (c.foto ? "<span class='nv-av'><img src='" + esc(c.foto) + "' alt=''></span>" : "<span class='nv-av'>📢</span>")
      + "<h1>" + esc(c.nombre) + "</h1><div class='nv-ayuda'>Canal · " + c.seguidores + " seguidor" + (c.seguidores === 1 ? '' : 'es') + "</div>" + (c.descripcion ? "<p>" + esc(c.descripcion) + "</p>" : '');
    if(c.mio) h += "<span class='nv-admin'>Eres el administrador</span><div class='nv-acc' style='justify-content:center'><a class='btn sec' href='/canales/" + encodeURIComponent(c.id) + "/editar'>✏️ Editar canal</a></div>";
    else h += "<div class='nv-acc' style='justify-content:center'><button type='button' class='btn" + (c.sigo ? ' sec' : '') + "' id='nvSeguir'>" + (c.sigo ? '✓ Siguiendo' : '＋ Seguir') + "</button></div>";
    return h + "</div>"; }
  function post(p){ var r = p.reacc, h = "<div class='nv-post' data-post='" + esc(p.id) + "'>";
    if(p.tipo === 'foto' && p.media) h += "<img src='" + esc(p.media) + "' alt='' loading='lazy'>";
    if(p.tipo === 'video' && p.media) h += "<video src='" + esc(p.media) + "#t=0.1' controls playsinline preload='metadata'></video>";
    if(p.texto) h += "<div class='t'>" + U.enlaces(p.texto) + "</div>";
    h += "<div class='pie'>" + (r.total ? "<span class='nv-reac" + (r.mia ? ' mia' : '') + "'>" + esc(r.emojis.join('')) + ' ' + r.total + "</span>" : '')
      + "<button type='button' class='nv-reac" + (r.mia ? ' mia' : '') + "' data-reac='" + esc(p.id) + "' aria-label='Reaccionar'>" + (r.mia ? esc(r.mia) : '🙂 Reaccionar') + "</button><span class='sp'></span><span>" + esc(U.hora(p.creado)) + "</span>"
      + (D.canal.mio ? "<button type='button' class='nv-borrar' data-borrar='" + esc(p.id) + "'>Eliminar</button>" : '') + "</div></div>";
    return h; }
  function pintar(d){ D = d; var h = cab(d.canal);
    if(!d.posts.length) h += "<div class='nv-vacio'>" + (d.canal.mio ? 'Aún no publicas nada. Escribe abajo tu primera novedad.' : 'Este canal todavía no tiene publicaciones.') + "</div>";
    h += d.posts.map(post).join(''); $('nvCanal').innerHTML = h;
    var v = U.ls(VISTO) || {}; v[d.canal.id] = d.posts.length ? d.posts[0].creado : new Date().toISOString(); U.ls(VISTO, v);
    U.ls(C.cache, d); }
  function refrescar(){ return fetch('/web/canales/' + encodeURIComponent(C.id) + '/datos').then(function(r){ return r.json(); }).then(function(j){ if(j.ok) pintar(j); }).catch(function(){}); }
  document.addEventListener('click', async function(ev){
    if(ev.target.id === 'nvSeguir'){ var s = !D.canal.sigo; ev.target.disabled = true; var j = await U.post('/web/canales/' + encodeURIComponent(C.id) + '/seguir', {seguir: s}); ev.target.disabled = false;
      if(!j.ok) return pcgAvisar({titulo: 'No se pudo actualizar', mensaje: j.mensaje || 'Inténtalo de nuevo.'}); D.canal.sigo = s; D.canal.seguidores = Math.max(0, D.canal.seguidores + (s ? 1 : -1)); pintar(D); return; }
    var r = ev.target.closest('[data-reac]');
    if(r){ var p = D.posts.find(function(x){ return x.id === r.dataset.reac; }), h = "<div class='nv-emojis'>" + EMOJIS.map(function(e){ return "<button type='button' data-e='" + e + "' class='" + (p.reacc.mia === e ? 'sel' : '') + "'>" + e + "</button>"; }).join('') + "</div>";
      var pr = pcgAvisar({titulo: 'Reacciona', icono: '🙂', confirmar: 'Cerrar', html: h}), elegido = '';
      document.querySelector('.nv-emojis').addEventListener('click', function(e2){ var b = e2.target.closest('[data-e]'); if(!b) return; elegido = b.dataset.e; var ok = document.getElementById('pcgDlgOk'); if(ok) ok.click(); });
      await pr; if(!elegido) return; var j2 = await U.post('/web/canales/' + encodeURIComponent(C.id) + '/post/' + encodeURIComponent(p.id) + '/reaccion', {emoji: elegido});
      if(!j2.ok) return pcgToast(j2.mensaje || 'No se pudo reaccionar'); p.reacc = j2.reacc; pintar(D); return; }
    var b = ev.target.closest('[data-borrar]');
    if(b){ var ok = await pcgConfirmar({titulo: 'Eliminar publicación', mensaje: '¿Quieres eliminar esta publicación del canal?', confirmar: 'Eliminar', destructivo: true}); if(!ok) return;
      pcgCargando('Eliminando…'); var j3 = await U.post('/web/canales/' + encodeURIComponent(C.id) + '/post/' + encodeURIComponent(b.dataset.borrar) + '/eliminar'); pcgCargando(false);
      if(!j3.ok) return pcgAvisar({titulo: 'No se pudo eliminar', mensaje: j3.mensaje || 'Inténtalo de nuevo.'}); D.posts = D.posts.filter(function(x){ return x.id !== b.dataset.borrar; }); pintar(D); }
  });
  if($('nvPubTxt')){
    var ta = $('nvPubTxt');
    ta.addEventListener('input', function(){ ta.style.height = 'auto'; ta.style.height = Math.min(140, ta.scrollHeight) + 'px'; });
    $('nvPubEnv').onclick = async function(){ var t = ta.value.trim(); if(!t) return; pcgCargando('Publicando…'); var j = await U.post('/web/canales/' + encodeURIComponent(C.id) + '/publicar', {tipo: 'texto', texto: t}); pcgCargando(false);
      if(!j.ok) return pcgAvisar({titulo: 'No se pudo publicar', mensaje: j.mensaje || 'Inténtalo de nuevo.'}); ta.value = ''; ta.style.height = ''; D.posts.unshift(j.post); pintar(D); };
    async function media(video){ var inp = $(video ? 'nvPubVid' : 'nvPubFoto'), f = inp.files && inp.files[0]; inp.value = ''; if(!f) return; var blob, tipoB, url;
      if(video){ var d = await U.duracion(f); if(d < 0) return pcgAvisar({titulo: 'Video no válido', mensaje: 'Tu navegador no puede leer este video. Sube un MP4.'});
        if(d > C.videoSeg + 1.5) return pcgAvisar({titulo: 'Video muy largo', icono: '⏱️', mensaje: 'En el canal puedes publicar videos de hasta ' + C.videoSeg + ' segundos.'});
        if(f.size > C.videoMax) return pcgAvisar({titulo: 'Video muy pesado', mensaje: 'Graba uno más corto.'}); blob = f; tipoB = f.type || 'video/mp4'; }
      else { try{ blob = await U.comprimir(f); tipoB = 'image/jpeg'; }catch(e){ return pcgAvisar({titulo: 'Foto no válida', mensaje: 'Elige una imagen JPG o PNG.'}); } }
      url = URL.createObjectURL(blob);
      var h = (video ? "<video src='" + url + "' controls playsinline style='width:100%;max-height:50vh;border-radius:12px;background:#111'></video>" : "<img src='" + url + "' alt='' style='width:100%;max-height:50vh;object-fit:contain;border-radius:12px;background:#111'>")
        + "<input class='nv-campo' id='nvCap' maxlength='1000' placeholder='Añade una descripción…'>";
      var cap = '', pr = pcgConfirmar({titulo: video ? 'Publicar video' : 'Publicar foto', icono: video ? '🎥' : '📷', confirmar: 'Publicar', cancelar: 'Cancelar', html: h});
      var ci = $('nvCap'); ci.addEventListener('input', function(){ cap = ci.value; });
      if(!(await pr)) return; pcgCargando(video ? 'Subiendo tu video…' : 'Subiendo tu foto…');
      var s = await U.subir('/web/canales/' + encodeURIComponent(C.id) + '/media?tipo=' + (video ? 'video' : 'foto'), blob, tipoB);
      if(!s.ok){ pcgCargando(false); return pcgAvisar({titulo: 'No se pudo subir', mensaje: s.mensaje || 'Inténtalo de nuevo.'}); }
      pcgCargando('Publicando…'); var j = await U.post('/web/canales/' + encodeURIComponent(C.id) + '/publicar', {tipo: video ? 'video' : 'foto', texto: cap.trim(), id: s.id, url: s.url, tk: s.tk}); pcgCargando(false);
      if(!j.ok) return pcgAvisar({titulo: 'No se pudo publicar', mensaje: j.mensaje || 'Inténtalo de nuevo.'}); D.posts.unshift(j.post); pintar(D); }
    $('nvPubFoto').addEventListener('change', function(){ media(false); }); $('nvPubVid').addEventListener('change', function(){ media(true); });
    $('nvBtnFoto').onclick = function(){ $('nvPubFoto').click(); }; $('nvBtnVid').onclick = function(){ $('nvPubVid').click(); };
  }
  pintar(C.inicial);
  window.addEventListener('pageshow', function(ev){ if(ev.persisted){ var c = U.ls(C.cache); if(c) pintar(c); refrescar(); } });
  setInterval(function(){ if(!document.hidden && !document.querySelector('.pcg-dlg.open')) refrescar(); }, 20000);
})();
</script>"""


@router.get("/canales/{canal_id}", response_class=HTMLResponse)
def pagina_canal(request: Request, canal_id: str) -> HTMLResponse:
    """`canal_detalle_screen.dart`."""
    ses = sesion.de_request(request)
    if not ses or not ses.get("email"):
        return _sin_login(request, f"/canales/{quote(canal_id, safe='')}", "Canal", "Los canales")
    yo = _low(ses["email"])
    c = canal(canal_id)
    if not c:
        cuerpo = ("<div class='panel' style='max-width:520px;margin:40px auto;text-align:center'><h1 style='font-size:22px'>Canal no encontrado</h1>"
                  "<p class='sub'>Este canal ya no existe o fue eliminado.</p><div class='acciones' style='justify-content:center'>"
                  "<a class='btn' href='/canales'>Ver canales</a></div></div>")
        r = ui.shell("Canal no encontrado", cuerpo, sesion=ses)
        r.status_code = 404
        return r
    d = datos_canal(c, yo)
    cfg = {"id": c["id"], "cache": _clave_cache(yo, "canal_" + c["id"]), "cacheVisto": _clave_cache(yo, "nov") + "_canalvisto",
           "inicial": d, "emojis": REACCIONES, "videoSeg": VIDEO_CANAL_SEG, "videoMax": VIDEO_MAX}
    escribir = ""
    if c["owner_email"] == yo:
        escribir = ("<div class='nv-escribir'><input type='file' id='nvPubFoto' accept='image/*' hidden><input type='file' id='nvPubVid' accept='video/mp4,video/quicktime,video/*' hidden>"
                    "<button type='button' class='ico' id='nvBtnFoto' aria-label='Publicar foto'>📷</button>"
                    "<button type='button' class='ico' id='nvBtnVid' aria-label='Publicar video'>🎥</button>"
                    f"<textarea id='nvPubTxt' rows='1' maxlength='{POST_TEXTO_MAX}' placeholder='Escribe…'></textarea>"
                    "<button type='button' class='env' id='nvPubEnv'>Publicar</button></div>")
    cuerpo = (_CSS + "<div class='nv-wrap'><p style='margin:0 0 8px'><a href='/canales'>‹ Canales</a></p><div id='nvCanal'></div>" + escribir + "</div>"
              + f"<script>window.NV_CD = {_js(cfg)};</script>" + _JS_COMUN + _JS_CANAL)
    return ui.shell(c["nombre"], cuerpo, sesion=ses, titulo_tab=f"{c['nombre']} · Canal · Pichangol")


@router.get("/canales/{canal_id}/editar", response_class=HTMLResponse)
def pagina_editar_canal(request: Request, canal_id: str) -> HTMLResponse:
    ses = sesion.de_request(request)
    if not ses or not ses.get("email"):
        return _sin_login(request, f"/canales/{quote(canal_id, safe='')}/editar", "Editar canal", "Editar tu canal")
    c = canal(canal_id)
    if not c or c["owner_email"] != _low(ses["email"]):
        return HTMLResponse("", status_code=303, headers={"Location": f"/canales/{quote(canal_id, safe='')}"})
    return _form_canal(ses, c)


@router.get("/web/canales/{canal_id}/datos")
def api_canal(request: Request, canal_id: str) -> JSONResponse:
    ses, err = _ses_o_401(request)
    if err:
        return err
    c = canal(canal_id)
    if not c:
        return _mal("Este canal ya no existe.", 404, "no_encontrado")
    return JSONResponse(datos_canal(c, _low(ses["email"])), headers={"Cache-Control": "no-store"})


def _subir_media_canal(request: Request, canal_id: str, tipo: str, datos_: bytes) -> JSONResponse:
    ses, c, err = _canal_mio(request, canal_id)
    if err:
        return err
    if tipo not in ("foto", "video"):
        return _mal("Tipo inválido.")
    motivo = _validar_media(datos_, tipo, VIDEO_CANAL_SEG)
    if motivo:
        return _mal(motivo)
    if not almacen.disponible():
        return _mal("La subida de fotos y videos no está disponible en este momento.", 503, "sin_storage")
    pid = f"cp_{_us()}"
    ext, ct = ("jpg", "image/jpeg") if tipo == "foto" else ("mp4", "video/mp4")
    url = almacen.subir("canales", f"{canal_id}/{pid}.{ext}", datos_, ct, max_bytes=VIDEO_MAX)
    if not url:
        return _mal("No se pudo subir. Revisa el bucket \"canales\".", 502, "subida")
    return JSONResponse({"ok": True, "id": pid, "url": url, "tk": _firma(_low(ses["email"]), canal_id, pid, url)})


@router.post("/web/canales/{canal_id}/media")
async def api_media_canal(request: Request, canal_id: str, tipo: str = "foto") -> JSONResponse:
    datos_ = await request.body()
    return await run_in_threadpool(_subir_media_canal, request, canal_id, tipo, datos_)


@router.post("/web/canales/{canal_id}/publicar")
def api_publicar_post(request: Request, canal_id: str, body: dict = Body(default_factory=dict)) -> JSONResponse:
    """`_publicarTexto` / `_subirYPublicar`: solo el dueño del canal."""
    ses, c, err = _canal_mio(request, canal_id)
    if err:
        return err
    yo = _low(ses["email"])
    tipo = str(body.get("tipo") or "texto")
    texto = str(body.get("texto") or "").strip()
    if len(texto) > POST_TEXTO_MAX:
        return _mal(f"Máximo {POST_TEXTO_MAX} caracteres.")
    fila = {"canal_id": canal_id, "autor_email": yo, "autor_nombre": _mi_nombre(yo, ses), "tipo": tipo, "texto": texto, "media_url": ""}
    if tipo == "texto":
        if not texto:
            return _mal("Escribe tu novedad.")
        fila["id"] = f"cp_{_us()}"
    elif tipo in ("foto", "video"):
        pid, url, tk = str(body.get("id") or ""), str(body.get("url") or ""), str(body.get("tk") or "")
        ext = "jpg" if tipo == "foto" else "mp4"
        if (not _RE_ID_POST.match(pid) or not _es_media_de(url, "canales", f"{canal_id}/{pid}.{ext}")
                or not hmac.compare_digest(tk, _firma(yo, canal_id, pid, url))):
            return _mal("Vuelve a subir la foto o el video.", 400, "media_invalida")
        fila.update({"id": pid, "media_url": url})
    else:
        return _mal("Tipo inválido.")
    if not insertar_post(fila):
        return _mal("No se pudo publicar. Revisa tu conexión.", 503, "guardar")
    fila["creado"] = _ahora()
    return JSONResponse({"ok": True, "post": _post_json(fila, {}, yo)})


@router.post("/web/canales/{canal_id}/post/{post_id}/eliminar")
def api_borrar_post(request: Request, canal_id: str, post_id: str) -> JSONResponse:
    ses, c, err = _canal_mio(request, canal_id)
    if err:
        return err
    f = borrar_post(post_id, canal_id)
    if f is None:
        return _mal("No encontramos esta publicación.", 404, "no_encontrado")
    limpia = f["media_url"].split("?", 1)[0]
    exts = [x for x in ("jpg", "mp4") if limpia.endswith("." + x)] or (["jpg", "mp4"] if limpia else [])
    _borrar_media("canales", [f"{canal_id}/{post_id}.{x}" for x in exts])
    return JSONResponse({"ok": True})


@router.post("/web/canales/{canal_id}/post/{post_id}/reaccion")
def api_reaccion(request: Request, canal_id: str, post_id: str, body: dict = Body(default_factory=dict)) -> JSONResponse:
    ses, err = _ses_o_401(request)
    if err:
        return err
    yo = _low(ses["email"])
    emoji = str(body.get("emoji") or "")
    if emoji not in REACCIONES:
        return _mal("Reacción inválida.")
    if not post_existe(canal_id, post_id):
        return _mal("Esta publicación ya no existe.", 404, "no_encontrado")
    if not alternar_reaccion(canal_id, post_id, yo, emoji):
        return _mal("No se pudo reaccionar.", 503, "guardar")
    r = reacciones_de(canal_id).get(post_id) or {}
    return JSONResponse({"ok": True, "reacc": {"emojis": list(dict.fromkeys(r.values()))[:3], "total": len(r), "mia": r.get(yo, "")}})
