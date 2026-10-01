"""MENSAJES en la web = la mensajería del APK (pedido del director,
29-sep-2026: "en la web implementa las mismas funcionalidades que existen
actualmente en el app").

Espejo de estas pantallas, con las MISMAS tablas de Supabase (Postgres
directo) y la MISMA forma de fila que escribe el app:

- `GET /mensajes` = `mensajes_screen.dart` (bandeja): hilos de
  `pichangol_mensajes` donde el correo de la sesión participa —academia
  (dueño por `academia_id` o alumno/jugador por `cuenta_email`), cancha
  (`ref_id` = dueño o `cuenta_email` = jugador), grupo (miembro en
  `pichangol_grupo_miembros`) y directo (`autor_email`/`cuenta_email`)—.
  **Una persona = un chat** (`_fusionarPorPersona`): los hilos 1:1 con la
  misma contraparte se funden en UNA fila (principal = el más reciente, no
  leídos sumados, título = local/academia si soy el cliente, si no el nombre
  de perfil). No leídos contra `pichangol_lecturas.leido_hasta` (los checks
  del app). Fijar / archivar / silenciar / eliminar en
  `pichangol_chat_prefs` con la semántica de `AppState`: eliminar = oculto
  desde ahora y **reaparece si llega algo más nuevo** (y la nube se limpia,
  como `chatOculto`); archivar también desfija; las acciones de una fila
  fundida aplican a todos sus hilos. Filtros Todos / No leídos / Academias /
  Canchas / Grupos / Fijados + Archivados.
- `GET /mensajes/{clave}` = `chat_screen.dart`: historial de TODOS los hilos
  de la fila (`MensajesRepo.streamHilos`, ventana de 50 + "Cargar mensajes
  anteriores"), "mío" por correo, citas (`resp_texto/resp_autor/resp_media`),
  reenviados, fotos, audios, GIF, documentos, ubicación, llamadas; enviar
  texto (con responder citando) y foto (bucket `chat`, ruta
  `<hilo saneado>/<µs>.jpg`, texto "📷 Foto", igual que
  `MensajesRepo.subirFoto`); lo nuevo va SIEMPRE al hilo principal; marca
  leído (`LecturasRepo.marcarLeido`) y la bandeja marca entregado; checks ✓ /
  ✓✓ / ✓✓ azul en 1:1. Tiempo real = sondeo ligero cada 4,5 s SOLO con la
  pestaña visible, pidiendo solo lo posterior al último mensaje; la página
  llega pintada del servidor y la bandeja se guarda en `localStorage`
  (se pinta al instante al volver, nada de spinner de pantalla completa).
- Grupos = `crear_grupo_screen.dart` / `grupo_info_screen.dart`:
  `pichangol_grupos` (`grp_<µs>`) + `pichangol_grupo_miembros`, foto en el
  bucket `grupos/<id>.jpg`, renombrar, añadir integrante (contactos de la
  agenda o buscador), salir.
- Nuevo chat = `buscar_usuario_screen.dart` / `selector_chat_screen.dart`:
  buscador de perfiles (nombre o correo, ≥2 letras) → chat directo
  `directo_a|b` con los correos ordenados (`Mensaje.hiloDirecto`); si ya hay
  conversación con esa persona se reusa la fila. Desde la ficha:
  `/mensajes/nuevo?cancha=<id>` → hilo `cancha_<dueño>|<jugador>` en
  minúsculas (`_chatearConDueno`) y `/mensajes/nuevo?academia=<id>` → hilo
  `<academia>|<jugador>` (`_abrirChatProfe`).

Seguridad: la participación se decide SIEMPRE en el servidor a partir del
hilo y del correo de la sesión (misma regla del app por tipo de hilo); el
navegador solo ve una `clave` cifrada (Fernet con el secreto del backend) y
nunca los correos de las contrapartes (los perfiles viajan como `ref`
opaco, como en la Liga). Los contactos bloqueados en la agenda
(`pichangol_agenda.bloqueados`) no reciben mensajes míos.

Push: el aviso lo dispara el trigger `trg_push_mensaje` /
Database Webhook `push-mensaje` al INSERTAR en `pichangol_mensajes`
(docs/piloto/reparar_push.sql): la web NO manda otro aviso (sería doble).
Llamadas de voz y video: solo en la app (se indica en el chat).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import time
from datetime import datetime, timezone
from urllib.parse import quote

from fastapi import APIRouter, Body, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from db import pg
from web import almacen, datos, sesion, ui
from web.jugador_liga import (_ocultar_correo, email_de_ref, perfiles, ref_de,
                              sin_sesion)
from web.ui import e

router = APIRouter()

PLAY_URL = ui.PLAY_URL
LIMITE = 50                      # ventana de mensajes (`streamHilo(limite: 50)`)
TEXTO_MAX = 4000
FOTO_MAX = 6 * 1024 * 1024       # ya comprimida a 1600 px en el navegador
MAX_MIEMBROS = 256


# ═══════════════════════════ Utilidades ═══════════════════════════════════════

def _low(s) -> str:
    return (str(s or "")).strip().lower()


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
    """ISO UTC SIEMPRE con microsegundos: el navegador compara estas cadenas
    (cursor del sondeo y checks) y deben tener el mismo largo."""
    d = _dt(v)
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ") if d else ""


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _llaves() -> tuple[bytes, bytes]:
    base = sesion._secreto()
    return (hashlib.sha256(base + b"|pcg-chat-hilos-enc").digest(), hashlib.sha256(base + b"|pcg-chat-hilos-mac").digest())


def clave_de(hilos: list[str]) -> str:
    """Clave OPACA y ESTABLE de una fila de la bandeja (lista de hilos,
    principal primero). Los hilos llevan correos → nunca viajan en claro.
    Cifrado determinista autenticado (AES-GCM con nonce = HMAC del contenido):
    la misma fila da siempre la misma clave (sirve para marcar la activa)."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    hs = [h for h in dict.fromkeys(hilos) if h]
    datos_ = json.dumps(hs, separators=(",", ":")).encode()
    k_enc, k_mac = _llaves()
    nonce = hmac.new(k_mac, datos_, hashlib.sha256).digest()[:12]
    return base64.urlsafe_b64encode(nonce + AESGCM(k_enc).encrypt(nonce, datos_, None)).decode().rstrip("=")


def hilos_de_clave(k: str) -> list[str]:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    try:
        raw = base64.urlsafe_b64decode((k or "") + "=" * (-len(k or "") % 4))
        k_enc, _ = _llaves()
        v = json.loads(AESGCM(k_enc).decrypt(raw[:12], raw[12:], None).decode())
    except Exception:  # noqa: BLE001
        return []
    return [str(h) for h in v if isinstance(h, str) and h][:12] if isinstance(v, list) else []


def uid_de(email: str) -> str:
    """Id corto y estable de una persona para el navegador (deduplicar chips)."""
    return hmac.new(_llaves()[1], _low(email).encode(), hashlib.sha256).hexdigest()[:14]


def hilo_directo(a: str, b: str) -> str:
    """`Mensaje.hiloDirecto`: simétrico, correos en minúsculas y ordenados."""
    x, y = sorted([_low(a), _low(b)])
    return f"directo_{x}|{y}"


def hilo_cancha(dueno: str, jugador: str) -> str:
    """`Mensaje.hiloCancha` (el 1.er parámetro es el correo del DUEÑO)."""
    return f"cancha_{_low(dueno)}|{_low(jugador)}"


def hilo_academia(academia_id: str, cuenta: str) -> str:
    """`Mensaje.hiloDe`."""
    return f"{academia_id}|{_low(cuenta)}"


def hilo_grupo(grupo_id: str) -> str:
    return f"grupo_{grupo_id}"


def partir_hilo(hilo: str) -> dict | None:
    """Tipo y partes de un hilo según su forma (la del app)."""
    h = hilo or ""
    if h.startswith("directo_"):
        a, sep, b = h[len("directo_"):].partition("|")
        return {"tipo": "directo", "a": a, "b": b} if sep and a and b else None
    if h.startswith("cancha_"):
        d, sep, j = h[len("cancha_"):].partition("|")
        return {"tipo": "cancha", "dueno": d, "jugador": j} if sep and d and j else None
    if h.startswith("grupo_"):
        g = h[len("grupo_"):]
        return {"tipo": "grupo", "grupo": g} if g else None
    ac, sep, c = h.rpartition("|")
    return {"tipo": "academia", "academia": ac, "cuenta": c} if sep and ac and c else None


def _carpeta_hilo(hilo: str) -> str:
    """`MensajesRepo.subirFoto`: `hilo.replaceAll(RegExp(r'[^a-zA-Z0-9_-]'), '_')`."""
    return re.sub(r"[^a-zA-Z0-9_-]", "_", hilo)


_EXT_IMG = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif", ".bmp"}


def clase_media(url: str) -> str:
    """Espejo de los getters de `Mensaje`: audio · gif · foto · doc · geo · geolive · ''."""
    u = (url or "").strip()
    if not u:
        return ""
    if u.startswith("geolive:"):
        return "geolive"
    if u.startswith("geo:"):
        return "geo"
    lu = u.lower()
    if any(x in lu for x in (".m4a", ".aac", ".mp3", ".wav", ".ogg")):
        return "audio"
    web = lu.startswith("http://") or lu.startswith("https://")
    if ".gif" in lu or "giphy.com" in lu:
        return "gif"
    base = lu.split("?", 1)[0]
    ext = base[base.rfind("."):] if base.rfind(".") > base.rfind("/") else ""
    if web and ext in _EXT_IMG:
        return "foto"
    return "doc" if web else ""


def preview(texto: str, media: str) -> str:
    """`_previewMsg` del inbox."""
    c = clase_media(media)
    if c == "audio":
        return "🎤 Nota de voz"
    if c == "gif":
        return "🎞️ GIF"
    if c == "foto":
        return texto or "📷 Foto"
    return texto or ""


def snippet(texto: str, media: str) -> str:
    """`_snippet` (texto de la cita al responder)."""
    c = clase_media(media)
    if c == "audio":
        return "🎤 Nota de voz"
    if c == "gif":
        return "🎞️ GIF"
    if c == "geolive":
        return "📍 Ubicación en tiempo real"
    if c == "geo":
        return "📍 Ubicación"
    if c == "doc":
        t = (texto or "").strip()
        if t.startswith("📄"):
            return t
        base = (media or "").split("?", 1)[0]
        return "📄 " + (base[base.rfind("/") + 1:] if "/" in base else "archivo")
    if c == "foto":
        return texto or "📷 Foto"
    return texto or ""


def _ses_o_401(request: Request):
    ses = sesion.de_request(request)
    if not ses or not ses.get("email"):
        return None, JSONResponse({"ok": False, "error": "sesion_requerida", "mensaje": "Inicia sesión para continuar."},
                                  status_code=401)
    return ses, None


def _mi_nombre(email: str, ses: dict) -> str:
    p = perfiles([email]).get(email) or {}
    return (p.get("nombre") or ses.get("nombre") or email.split("@")[0]).strip()


# ═══════════════════════════ Datos (Postgres directo, fail-safe) ═══════════════

_COLS_MSG = ["id", "hilo", "tipo", "ref_id", "academia_id", "cuenta_email", "autor_email", "autor_nombre",
             "es_profe", "texto", "media_url", "resp_texto", "resp_autor", "resp_media", "reenviado", "creado"]
_col_resp: dict[str, bool] = {}


def _cols_msg() -> list[str]:
    """Las columnas de respuesta/reenvío salen de `supabase_mensajes_reply.sql`;
    si una base aún no lo corrió, se lee sin ellas (y no se escriben)."""
    if "ok" not in _col_resp:
        ok = True
        if pg.habilitado:
            try:
                with pg.conexion() as conn, conn.cursor() as cur:
                    cur.execute("SELECT count(*) FROM information_schema.columns WHERE table_name = 'pichangol_mensajes' "
                                "AND column_name IN ('resp_texto','resp_autor','resp_media','reenviado')")
                    ok = int(cur.fetchone()[0] or 0) >= 4
            except Exception:  # noqa: BLE001
                ok = True
        _col_resp["ok"] = ok
    return _COLS_MSG if _col_resp["ok"] else [c for c in _COLS_MSG if not c.startswith("resp_") and c != "reenviado"]


def _fila_msg(cols: list[str], f) -> dict:
    d = dict(zip(cols, f))
    for c in _COLS_MSG:
        d.setdefault(c, "" if c not in ("es_profe", "reenviado") else False)
    return d


def academias_de_dueno(email: str) -> list[str]:
    """Ids de las academias de las que es dueño (profe) → ve TODOS sus hilos."""
    em = _low(email)
    if not pg.habilitado or not em:
        return []
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id FROM pichangol_academias WHERE lower(dueno) = %s", (em,))
            return [str(f[0]) for f in cur.fetchall()]
    except Exception:  # noqa: BLE001
        return []


def academias_info(ids) -> dict[str, dict]:
    """{id: {nombre, dueno, logo}} (también eliminadas: el hilo sigue existiendo)."""
    ids = sorted({str(i) for i in ids if i})
    if not pg.habilitado or not ids:
        return {}
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id, dueno, data FROM pichangol_academias WHERE id = ANY(%s::text[])", (ids,))
            out = {}
            for f in cur.fetchall():
                d = f[2] if isinstance(f[2], dict) else (json.loads(f[2]) if f[2] else {})
                out[str(f[0])] = {"nombre": str(d.get("nombre") or "Academia"), "dueno": _low(f[1] or d.get("dueno")),
                                  "logo": str(d.get("logoUrl") or "")}
            return out
    except Exception:  # noqa: BLE001
        return {}


def nombres_alumnos(pares) -> dict[tuple, str]:
    """(academia_id, correo) → nombre del alumno como lo muestra `_nombreAlumno`
    (apoderado si es menor, si no el nombre)."""
    pares = {(str(a), _low(c)) for a, c in pares if a and c}
    if not pg.habilitado or not pares:
        return {}
    acs = sorted({a for a, _ in pares})
    es = sorted({c for _, c in pares})
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT academia_id, lower(email), data FROM pichangol_matriculas WHERE academia_id = ANY(%s::text[]) "
                        "AND lower(email) = ANY(%s::text[]) AND coalesce(eliminada,false) = false", (acs, es))
            out: dict[tuple, str] = {}
            for f in cur.fetchall():
                d = f[2] if isinstance(f[2], dict) else (json.loads(f[2]) if f[2] else {})
                n = str(d.get("apoderadoNombre") or "").strip() or str(d.get("nombre") or "").strip()
                if n and (str(f[0]), str(f[1])) in pares:
                    out.setdefault((str(f[0]), str(f[1])), n)
            return out
    except Exception:  # noqa: BLE001
        return {}


def locales_de(duenos) -> dict[str, dict]:
    """`_nombreLocalDe`: nombre del local (club o nombre) y su 1.ª foto, por dueño."""
    es = sorted({_low(x) for x in duenos if x})
    if not pg.habilitado or not es:
        return {}
    for con_fotos in (True, False):
        try:
            with pg.conexion() as conn, conn.cursor() as cur:
                cur.execute("SELECT lower(dueno), club, nombre" + (", fotos" if con_fotos else "") +
                            " FROM pichangol_canchas WHERE lower(dueno) = ANY(%s::text[]) AND coalesce(eliminada,false) = false "
                            "ORDER BY verificada DESC, nombre", (es,))
                out: dict[str, dict] = {}
                for f in cur.fetchall():
                    if f[0] in out:
                        continue
                    fotos = f[3] if con_fotos and len(f) > 3 else []
                    if isinstance(fotos, str):
                        try:
                            fotos = json.loads(fotos)
                        except Exception:  # noqa: BLE001
                            fotos = []
                    out[str(f[0])] = {"nombre": str(f[1] or "").strip() or str(f[2] or "").strip() or "Dueño de cancha",
                                      "foto": str((fotos or [""])[0] or "") if isinstance(fotos, list) else ""}
                return out
        except Exception:  # noqa: BLE001
            continue
    return {}


def grupos_de(email: str) -> list[dict]:
    """`GruposRepo.gruposDe`: grupos donde soy miembro, con sus miembros."""
    em = _low(email)
    if not pg.habilitado or not em:
        return []
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT grupo_id FROM pichangol_grupo_miembros WHERE email = %s", (em,))
            ids = sorted({str(f[0]) for f in cur.fetchall() if f[0]})
            if not ids:
                return []
            try:
                cur.execute("SELECT id, nombre, creador_email, coalesce(foto_url,''), creado FROM pichangol_grupos WHERE id = ANY(%s::text[])", (ids,))
                gs = cur.fetchall()
            except Exception:  # noqa: BLE001  (base sin `foto_url`)
                conn.rollback()
                cur.execute("SELECT id, nombre, creador_email, '', creado FROM pichangol_grupos WHERE id = ANY(%s::text[])", (ids,))
                gs = cur.fetchall()
            cur.execute("SELECT grupo_id, email FROM pichangol_grupo_miembros WHERE grupo_id = ANY(%s::text[])", (ids,))
            mm: dict[str, list[str]] = {}
            for gid, em2 in cur.fetchall():
                mm.setdefault(str(gid), []).append(_low(em2))
            return [{"id": str(g[0]), "nombre": str(g[1] or ""), "creador": _low(g[2]), "foto": str(g[3] or ""),
                     "creado": g[4], "miembros": mm.get(str(g[0]), [])} for g in gs]
    except Exception:  # noqa: BLE001
        return []


def grupo(grupo_id: str) -> dict | None:
    """`GruposRepo.obtener`."""
    if not pg.habilitado or not grupo_id:
        return None
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            try:
                cur.execute("SELECT id, nombre, creador_email, coalesce(foto_url,''), creado FROM pichangol_grupos WHERE id = %s", (grupo_id,))
                g = cur.fetchone()
            except Exception:  # noqa: BLE001
                conn.rollback()
                cur.execute("SELECT id, nombre, creador_email, '', creado FROM pichangol_grupos WHERE id = %s", (grupo_id,))
                g = cur.fetchone()
            if not g:
                return None
            cur.execute("SELECT email FROM pichangol_grupo_miembros WHERE grupo_id = %s", (grupo_id,))
            return {"id": str(g[0]), "nombre": str(g[1] or ""), "creador": _low(g[2]), "foto": str(g[3] or ""),
                    "creado": g[4], "miembros": [_low(f[0]) for f in cur.fetchall()]}
    except Exception:  # noqa: BLE001
        return None


def es_miembro(grupo_id: str, email: str) -> bool:
    if not pg.habilitado or not grupo_id or not email:
        return False
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pichangol_grupo_miembros WHERE grupo_id = %s AND email = %s", (grupo_id, _low(email)))
            return cur.fetchone() is not None
    except Exception:  # noqa: BLE001
        return False


def crear_grupo(gid: str, nombre: str, creador: str, miembros: list[tuple[str, str]]) -> bool:
    """`GruposRepo.crear`: fila del grupo + miembros (el creador incluido)."""
    if not pg.habilitado:
        return False
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO pichangol_grupos (id, nombre, creador_email) VALUES (%s, %s, %s)", (gid, nombre, _low(creador)))
            for em, nom in miembros:
                cur.execute("INSERT INTO pichangol_grupo_miembros (grupo_id, email, nombre) VALUES (%s, %s, %s) "
                            "ON CONFLICT (grupo_id, email) DO UPDATE SET nombre = EXCLUDED.nombre", (gid, _low(em), nom))
            conn.commit()
            return True
    except Exception:  # noqa: BLE001
        return False


def agregar_miembro(gid: str, email: str, nombre: str) -> bool:
    if not pg.habilitado:
        return False
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO pichangol_grupo_miembros (grupo_id, email, nombre) VALUES (%s, %s, %s) "
                        "ON CONFLICT (grupo_id, email) DO UPDATE SET nombre = EXCLUDED.nombre", (gid, _low(email), nombre))
            conn.commit()
            return True
    except Exception:  # noqa: BLE001
        return False


def salir_grupo(gid: str, email: str) -> bool:
    if not pg.habilitado:
        return False
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM pichangol_grupo_miembros WHERE grupo_id = %s AND email = %s", (gid, _low(email)))
            conn.commit()
            return True
    except Exception:  # noqa: BLE001
        return False


def actualizar_grupo(gid: str, nombre: str | None = None, foto: str | None = None) -> bool:
    """`GruposRepo.actualizar`."""
    cambios, vals = [], []
    if nombre:
        cambios.append("nombre = %s"); vals.append(nombre)
    if foto is not None:
        cambios.append("foto_url = %s"); vals.append(foto)
    if not cambios:
        return True
    if not pg.habilitado:
        return False
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute(f"UPDATE pichangol_grupos SET {', '.join(cambios)} WHERE id = %s", (*vals, gid))
            conn.commit()
            return True
    except Exception:  # noqa: BLE001
        return False


_SQL_BANDEJA = """
WITH mis AS (
  SELECT hilo, tipo, ref_id, academia_id, cuenta_email, autor_email, autor_nombre, texto, media_url, creado
  FROM pichangol_mensajes m
  WHERE (m.tipo = 'academia' AND (m.academia_id = ANY(%(acs)s::text[]) OR m.cuenta_email = %(e)s))
     OR (m.tipo = 'cancha' AND (m.ref_id = %(e)s OR m.cuenta_email = %(e)s))
     OR (m.tipo = 'grupo' AND m.ref_id = ANY(%(gs)s::text[]))
     OR (m.tipo = 'directo' AND (m.autor_email = %(e)s OR m.cuenta_email = %(e)s))
), ult AS (
  SELECT DISTINCT ON (hilo) * FROM mis ORDER BY hilo, creado DESC
), lec AS (
  SELECT hilo, leido_hasta FROM pichangol_lecturas WHERE email = %(e)s
), cnt AS (
  SELECT mis.hilo, count(*) FILTER (WHERE lower(mis.autor_email) <> %(e)s
                                      AND (lec.leido_hasta IS NULL OR mis.creado > lec.leido_hasta)) AS n
  FROM mis LEFT JOIN lec ON lec.hilo = mis.hilo GROUP BY mis.hilo
), nom AS (
  SELECT DISTINCT ON (hilo) hilo, autor_nombre FROM mis
  WHERE lower(autor_email) <> %(e)s AND autor_nombre <> '' ORDER BY hilo, creado DESC
)
SELECT ult.hilo, ult.tipo, ult.ref_id, ult.academia_id, ult.cuenta_email, ult.autor_email, ult.autor_nombre,
       ult.texto, ult.media_url, ult.creado, cnt.n, nom.autor_nombre
FROM ult JOIN cnt ON cnt.hilo = ult.hilo LEFT JOIN nom ON nom.hilo = ult.hilo
"""


def resumen_hilos(email: str, acs: list[str], gids: list[str]) -> list[dict]:
    """Por hilo donde participo: último mensaje, no leídos (contra MI
    `leido_hasta`) y el último nombre de la contraparte. UNA consulta."""
    em = _low(email)
    if not pg.habilitado or not em:
        return []
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute(_SQL_BANDEJA, {"e": em, "acs": list(acs), "gs": list(gids)})
            out = []
            for f in cur.fetchall():
                out.append({"hilo": str(f[0]), "tipo": str(f[1] or "academia"), "ref_id": str(f[2] or ""),
                            "academia_id": str(f[3] or ""), "cuenta_email": _low(f[4]), "autor_email": _low(f[5]),
                            "autor_nombre": str(f[6] or ""), "texto": str(f[7] or ""), "media_url": str(f[8] or ""),
                            "creado": f[9], "no_leidos": int(f[10] or 0), "otro_nombre": str(f[11] or "")})
            return out
    except Exception:  # noqa: BLE001
        return []


def prefs_de(email: str) -> dict[str, dict]:
    """`ChatPrefsRepo.leer`."""
    em = _low(email)
    if not pg.habilitado or not em:
        return {}
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT hilo, oculto_en, fijado, archivado, silenciado FROM pichangol_chat_prefs WHERE email = %s", (em,))
            return {str(f[0]): {"oculto_en": f[1], "fijado": bool(f[2]), "archivado": bool(f[3]), "silenciado": bool(f[4])}
                    for f in cur.fetchall()}
    except Exception:  # noqa: BLE001
        return {}


def guardar_prefs(email: str, filas: dict[str, dict]) -> bool:
    """`ChatPrefsRepo.guardarVarios` (upsert por (email, hilo), estado COMPLETO)."""
    em = _low(email)
    if not pg.habilitado or not em or not filas:
        return False
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            for hilo, p in filas.items():
                cur.execute("INSERT INTO pichangol_chat_prefs (email, hilo, oculto_en, fijado, archivado, silenciado, actualizado) "
                            "VALUES (%s, %s, %s, %s, %s, %s, now()) ON CONFLICT (email, hilo) DO UPDATE SET "
                            "oculto_en = EXCLUDED.oculto_en, fijado = EXCLUDED.fijado, archivado = EXCLUDED.archivado, "
                            "silenciado = EXCLUDED.silenciado, actualizado = now()",
                            (em, hilo, p.get("oculto_en"), bool(p.get("fijado")), bool(p.get("archivado")), bool(p.get("silenciado"))))
            conn.commit()
            return True
    except Exception:  # noqa: BLE001
        return False


def agenda_de(email: str) -> dict:
    """`AgendaRepo.cargar`: apodos, contactos y bloqueados del usuario."""
    em = _low(email)
    vacio = {"apodos": {}, "contactos": [], "bloqueados": []}
    if not pg.habilitado or not em:
        return vacio
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT apodos, contactos, bloqueados FROM pichangol_agenda WHERE email = %s LIMIT 1", (em,))
            f = cur.fetchone()
    except Exception:  # noqa: BLE001
        return vacio
    if not f:
        return vacio

    def _j(v, d):
        if isinstance(v, str):
            try:
                v = json.loads(v)
            except Exception:  # noqa: BLE001
                return d
        return v if isinstance(v, type(d)) else d
    return {"apodos": {_low(k): str(v) for k, v in _j(f[0], {}).items() if str(v or "").strip()},
            "contactos": [_low(x) for x in _j(f[1], []) if x],
            "bloqueados": [_low(x) for x in _j(f[2], []) if x]}


def mensajes_de(hilos: list[str], antes=None, desde=None, limite: int = LIMITE) -> list[dict]:
    """`MensajesRepo.streamHilos`: ventana de los N más recientes (o anteriores
    a `antes`, o posteriores a `desde`), en orden cronológico."""
    if not pg.habilitado or not hilos:
        return []
    cols = _cols_msg()
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            if desde is not None:
                cur.execute(f"SELECT {', '.join(cols)} FROM pichangol_mensajes WHERE hilo = ANY(%s::text[]) AND creado >= %s "
                            "ORDER BY creado ASC LIMIT 200", (hilos, desde))
                return [_fila_msg(cols, f) for f in cur.fetchall()]
            if antes is not None:
                cur.execute(f"SELECT {', '.join(cols)} FROM pichangol_mensajes WHERE hilo = ANY(%s::text[]) AND creado < %s "
                            "ORDER BY creado DESC LIMIT %s", (hilos, antes, limite))
            else:
                cur.execute(f"SELECT {', '.join(cols)} FROM pichangol_mensajes WHERE hilo = ANY(%s::text[]) "
                            "ORDER BY creado DESC LIMIT %s", (hilos, limite))
            return list(reversed([_fila_msg(cols, f) for f in cur.fetchall()]))
    except Exception:  # noqa: BLE001
        return []


def mensaje(msg_id: str) -> dict | None:
    if not pg.habilitado or not msg_id:
        return None
    cols = _cols_msg()
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT {', '.join(cols)} FROM pichangol_mensajes WHERE id = %s", (msg_id,))
            f = cur.fetchone()
            return _fila_msg(cols, f) if f else None
    except Exception:  # noqa: BLE001
        return None


def insertar_mensaje(fila: dict) -> dict | None:
    """`MensajesRepo.enviar` (`Mensaje.toInsert`): `creado` lo pone el servidor
    (now()). Devuelve la fila guardada. El push lo dispara el trigger."""
    if not pg.habilitado:
        return None
    cols = ["id", "hilo", "tipo", "ref_id", "cuenta_email", "autor_email", "autor_nombre", "es_profe", "texto"]
    vals = [fila[c] for c in cols]
    if fila.get("tipo") == "academia":
        cols.append("academia_id"); vals.append(fila.get("academia_id") or "")
    if fila.get("media_url"):
        cols.append("media_url"); vals.append(fila["media_url"])
    if _col_resp.get("ok", True):
        for c in ("resp_texto", "resp_autor", "resp_media"):
            if fila.get(c):
                cols.append(c); vals.append(fila[c])
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute(f"INSERT INTO pichangol_mensajes ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))}) RETURNING creado",
                        vals)
            creado = cur.fetchone()[0]
            conn.commit()
    except Exception:  # noqa: BLE001
        return None
    out = {c: "" for c in _COLS_MSG}
    out.update(fila)
    out["creado"] = creado
    return out


def marcar_leido(hilos: list[str], email: str) -> None:
    """`LecturasRepo.marcarLeido` (entregado y leído hasta ahora)."""
    em = _low(email)
    if not pg.habilitado or not em or not hilos:
        return
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            for h in dict.fromkeys(hilos):
                cur.execute("INSERT INTO pichangol_lecturas (hilo, email, entregado_hasta, leido_hasta) VALUES (%s, %s, now(), now()) "
                            "ON CONFLICT (hilo, email) DO UPDATE SET entregado_hasta = now(), leido_hasta = now()", (h, em))
            conn.commit()
    except Exception:  # noqa: BLE001
        pass


def marcar_entregados(hilos: list[str], email: str) -> None:
    """`LecturasRepo.marcarEntregados` (no pisa `leido_hasta`)."""
    em = _low(email)
    if not pg.habilitado or not em or not hilos:
        return
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            for h in dict.fromkeys(hilos):
                cur.execute("INSERT INTO pichangol_lecturas (hilo, email, entregado_hasta) VALUES (%s, %s, now()) "
                            "ON CONFLICT (hilo, email) DO UPDATE SET entregado_hasta = now()", (h, em))
            conn.commit()
    except Exception:  # noqa: BLE001
        pass


def lecturas_ajenas(hilos: list[str], email: str) -> dict[str, dict]:
    """Marcas de la OTRA persona por hilo (checks del remitente)."""
    em = _low(email)
    if not pg.habilitado or not hilos:
        return {}
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT hilo, entregado_hasta, leido_hasta FROM pichangol_lecturas WHERE hilo = ANY(%s::text[]) AND email <> %s",
                        (hilos, em))
            out: dict[str, dict] = {}
            for h, en, le in cur.fetchall():
                o = out.setdefault(str(h), {"e": "", "l": ""})
                if en and (not o["e"] or _iso(en) > o["e"]):
                    o["e"] = _iso(en)
                if le and (not o["l"] or _iso(le) > o["l"]):
                    o["l"] = _iso(le)
            return out
    except Exception:  # noqa: BLE001
        return {}


def buscar_perfiles(q: str, yo: str) -> list[dict]:
    """`PerfilesRepo.buscar` (nombre o correo, ≥2 letras, hasta 25)."""
    q = (q or "").strip()
    if len(q) < 2 or not pg.habilitado:
        return []
    patron = "%" + q.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT email, nombre, foto_url FROM pichangol_perfiles WHERE lower(nombre) LIKE %s OR lower(email) LIKE %s "
                        "ORDER BY nombre LIMIT 25", (patron, patron))
            filas = cur.fetchall()
    except Exception:  # noqa: BLE001
        return []
    return [{"email": _low(f[0]), "nombre": str(f[1] or ""), "foto": str(f[2] or "")}
            for f in filas if _low(f[0]) not in ("", _low(yo))]


# ═══════════════════════════ Participación (regla del app por tipo) ══════════

def descriptor(hilo: str, yo: str, cache: dict | None = None) -> dict | None:
    """Cómo participo en [hilo] (o None si no soy parte). Da la fila base para
    enviar: tipo, ref_id, academia_id, cuenta_email, es_profe y la persona."""
    yo = _low(yo)
    p = partir_hilo(hilo)
    if not p or not yo:
        return None
    cache = cache if cache is not None else {}
    t = p["tipo"]
    if t == "directo":
        a, b = p["a"], p["b"]
        if yo not in (a, b) or a == b:
            return None
        otro = b if yo == a else a
        return {"hilo": hilo, "tipo": "directo", "ref_id": "", "academia_id": "", "cuenta_email": otro,
                "es_profe": False, "persona": otro, "negocio": False}
    if t == "cancha":
        d, j = p["dueno"], p["jugador"]
        if yo == d:
            return {"hilo": hilo, "tipo": "cancha", "ref_id": d, "academia_id": "", "cuenta_email": j,
                    "es_profe": True, "persona": j, "negocio": False}
        if yo == j:
            return {"hilo": hilo, "tipo": "cancha", "ref_id": d, "academia_id": "", "cuenta_email": j,
                    "es_profe": False, "persona": d, "negocio": True}
        return None
    if t == "grupo":
        g = p["grupo"]
        k = "g:" + g
        if k not in cache:
            cache[k] = es_miembro(g, yo)
        if not cache[k]:
            return None
        return {"hilo": hilo, "tipo": "grupo", "ref_id": g, "academia_id": "", "cuenta_email": "",
                "es_profe": False, "persona": "", "negocio": False}
    ac, cuenta = p["academia"], p["cuenta"]
    k = "a:" + ac
    if k not in cache:
        cache[k] = academias_info([ac]).get(ac)
    info = cache[k]
    dueno = (info or {}).get("dueno", "")
    if dueno and yo == dueno:
        return {"hilo": hilo, "tipo": "academia", "ref_id": ac, "academia_id": ac, "cuenta_email": cuenta,
                "es_profe": True, "persona": cuenta, "negocio": False}
    if yo == cuenta:
        return {"hilo": hilo, "tipo": "academia", "ref_id": ac, "academia_id": ac, "cuenta_email": cuenta,
                "es_profe": False, "persona": dueno, "negocio": True}
    return None


# ═══════════════════════════ Bandeja (mensajes_screen._cargar) ═══════════════

def bandeja(email: str, marcar: bool = True) -> dict:
    """Arma la bandeja como `_cargar`: conversaciones por tipo, filtra las
    eliminadas por hilo (reaparecen si hay algo más nuevo), funde por persona y
    ordena. Devuelve {filas, archivadas}."""
    yo = _low(email)
    acs = academias_de_dueno(yo)
    gs = grupos_de(yo)
    gids = [g["id"] for g in gs]
    res = resumen_hilos(yo, acs, gids)
    ag = agenda_de(yo)
    owned = set(acs)

    convs: list[dict] = []
    ac_ids, duenos_cancha, emails, pares_alumno = set(), set(), set(), set()
    for r in res:
        p = partir_hilo(r["hilo"])
        if not p:
            continue
        t = p["tipo"]
        c = {"hilo": r["hilo"], "tipo": t, "cuando": _dt(r["creado"]) or _ahora(), "no_leidos": r["no_leidos"],
             "texto": r["texto"], "media": r["media_url"], "otro_nombre": r["otro_nombre"],
             "autor_nombre": r["autor_nombre"], "autor_email": r["autor_email"]}
        if t == "academia":
            ac, cuenta = p["academia"], p["cuenta"]
            if ac in owned:
                c.update(soy_profe=True, academia=ac, cuenta=cuenta, persona=cuenta)
                pares_alumno.add((ac, cuenta)); emails.add(cuenta)
            elif cuenta == yo:
                c.update(soy_profe=False, academia=ac, cuenta=cuenta, persona="")
            else:
                continue  # hilo ajeno (nunca los de otros alumnos)
            ac_ids.add(ac)
        elif t == "cancha":
            d, j = p["dueno"], p["jugador"]
            if yo == d:
                c.update(soy_profe=True, dueno=d, cuenta=j, persona=j); emails.add(j)
            elif yo == j:
                c.update(soy_profe=False, dueno=d, cuenta=j, persona=d); duenos_cancha.add(d)
            else:
                continue
        elif t == "directo":
            a, b = p["a"], p["b"]
            if yo not in (a, b) or a == b:
                continue
            otro = b if yo == a else a
            c.update(soy_profe=False, persona=otro); emails.add(otro)
        else:  # grupo
            if p["grupo"] not in gids:
                continue
            c.update(soy_profe=False, grupo=p["grupo"], persona="")
        convs.append(c)

    # Grupos sin mensajes también salen ("N miembros · toca para escribir").
    vistos = {c["hilo"] for c in convs}
    for g in gs:
        h = hilo_grupo(g["id"])
        if h not in vistos:
            convs.append({"hilo": h, "tipo": "grupo", "grupo": g["id"], "persona": "", "soy_profe": False,
                          "cuando": _dt(g.get("creado")) or _ahora(), "no_leidos": 0, "texto": "", "media": "",
                          "otro_nombre": "", "autor_nombre": "", "autor_email": "", "vacio": True})

    info_ac = academias_info(ac_ids)
    for c in convs:
        if c["tipo"] == "academia" and not c["soy_profe"]:
            c["persona"] = (info_ac.get(c["academia"]) or {}).get("dueno", "")
    locales = locales_de(duenos_cancha)
    emails |= {c["persona"] for c in convs if c.get("persona")}
    perf = perfiles(emails)
    alumnos = nombres_alumnos(pares_alumno)
    grupos_idx = {g["id"]: g for g in gs}

    def mostrable(em: str) -> str | None:
        """`nombreMostrableDe`: MI apodo > nombre de su perfil."""
        return ag["apodos"].get(em) or ((perf.get(em) or {}).get("nombre") or "").strip() or None

    for c in convs:
        t = c["tipo"]
        per = c.get("persona", "")
        foto = (perf.get(per) or {}).get("foto_url", "") if per else ""
        if t == "academia":
            if c["soy_profe"]:
                titulo = mostrable(per) or alumnos.get((c["academia"], per)) or c["otro_nombre"] or per.split("@")[0]
            else:
                ia = info_ac.get(c["academia"]) or {}
                titulo, foto = ia.get("nombre") or "Academia", ia.get("logo") or ""
        elif t == "cancha":
            if c["soy_profe"]:
                titulo = mostrable(per) or c["otro_nombre"] or per.split("@")[0]
            else:
                lo = locales.get(c["dueno"]) or {}
                titulo, foto = lo.get("nombre") or "Dueño de cancha", lo.get("foto") or ""
        elif t == "directo":
            titulo = mostrable(per) or c["otro_nombre"] or per.split("@")[0]
        else:
            g = grupos_idx.get(c["grupo"]) or {}
            titulo, foto = g.get("nombre") or "Grupo", g.get("foto") or ""
        c["titulo"], c["foto"] = titulo, foto
        if t == "grupo":
            if c.get("vacio"):
                c["preview"] = f"{len(g.get('miembros') or [])} miembros · toca para escribir"
            else:
                pv = preview(c["texto"], c["media"])
                c["preview"] = (("Tú" if c["autor_email"] == yo else c["autor_nombre"]) + ": " + pv) if c["autor_nombre"] or c["autor_email"] == yo else pv
        else:
            c["preview"] = preview(c["texto"], c["media"])

    # Eliminados: por hilo, ANTES de fundir (como el app). Reaparece si llegó
    # un mensaje más nuevo que el momento en que se ocultó → la nube se limpia.
    prefs = prefs_de(yo)
    reaparecen: dict[str, dict] = {}
    vivos = []
    for c in convs:
        p = prefs.get(c["hilo"])
        oc = _dt((p or {}).get("oculto_en"))
        if oc:
            if c.get("vacio") or c["cuando"] <= oc:
                continue
            reaparecen[c["hilo"]] = dict(p, oculto_en=None)
        vivos.append(c)
    if reaparecen:
        guardar_prefs(yo, reaparecen)
        for h, p in reaparecen.items():
            prefs[h] = p

    # Una persona = un chat.
    por_persona: dict[str, list[dict]] = {}
    filas: list[dict] = []
    for c in vivos:
        if c.get("persona") and c["tipo"] != "grupo":
            por_persona.setdefault(c["persona"], []).append(c)
        else:
            filas.append(dict(c, hilos=[c["hilo"]]))
    for per, lista in por_persona.items():
        lista.sort(key=lambda x: x["cuando"], reverse=True)
        pr = lista[0]
        if len(lista) == 1:
            filas.append(dict(pr, hilos=[pr["hilo"]]))
            continue
        negocio = next((x for x in lista if not x["soy_profe"] and x["tipo"] != "directo"), None)
        titulo = negocio["titulo"] if negocio else (mostrable(per) or pr["titulo"])
        foto = negocio["foto"] if negocio else pr["foto"]
        filas.append(dict(pr, hilos=[x["hilo"] for x in lista], no_leidos=sum(x["no_leidos"] for x in lista),
                          titulo=titulo, foto=foto, fundida=True))

    out, arch = [], []
    for f in filas:
        ps = [prefs.get(h) or {} for h in f["hilos"]]
        f["fijado"] = any(p.get("fijado") for p in ps)
        f["archivado"] = any(p.get("archivado") for p in ps)
        f["silenciado"] = any(p.get("silenciado") for p in ps)
        f["bloqueado"] = bool(f.get("persona")) and f["persona"] in ag["bloqueados"]
        (arch if f["archivado"] else out).append(f)
    orden = lambda x: (not x["fijado"], -x["cuando"].timestamp())  # noqa: E731
    out.sort(key=orden)
    arch.sort(key=lambda x: -x["cuando"].timestamp())
    if marcar:
        marcar_entregados([c["hilo"] for c in vivos if not c.get("vacio")], yo)
    return {"filas": out, "archivadas": arch}


def fila_json(f: dict) -> dict:
    """Lo que ve el navegador de una fila (sin correos)."""
    return {"k": clave_de(f["hilos"]), "tipo": f["tipo"], "titulo": f["titulo"], "foto": f.get("foto") or "",
            "preview": f.get("preview") or "", "t": _iso(f["cuando"]), "n": int(f.get("no_leidos") or 0),
            "fijado": bool(f.get("fijado")), "archivado": bool(f.get("archivado")), "silenciado": bool(f.get("silenciado")),
            "negocio": f["tipo"] in ("cancha", "academia") and not f.get("soy_profe"), "grupo": f.get("grupo") or ""}


def no_leidos_total(email: str) -> int:
    """Badge: chats (filas) con algo sin leer, fuera de los archivados."""
    b = bandeja(email, marcar=False)
    return sum(1 for f in b["filas"] if f.get("no_leidos"))


# ═══════════════════════════ Mensajes → JSON para el navegador ═══════════════

def msg_json(m: dict, yo: str) -> dict:
    media = str(m.get("media_url") or "")
    c = clase_media(media)
    texto = str(m.get("texto") or "")
    llamada = texto in ("📞 Llamada de voz", "📹 Videollamada")
    return {"id": str(m.get("id") or ""), "h": str(m.get("hilo") or ""), "mio": _low(m.get("autor_email")) == _low(yo),
            "autor": str(m.get("autor_nombre") or ""), "texto": texto, "media": media if c in ("foto", "gif", "audio", "doc") else "",
            "c": "llamada" if llamada else c, "geo": media[4:] if c == "geo" else "",
            "t": _iso(m.get("creado")), "rt": str(m.get("resp_texto") or ""), "ra": str(m.get("resp_autor") or ""),
            "rm": str(m.get("resp_media") or ""), "fw": bool(m.get("reenviado"))}


def _hilos_json(hilos: list[str]) -> dict[str, str]:
    """Los hilos viajan al navegador como índices opacos (h0, h1…)."""
    return {h: f"h{i}" for i, h in enumerate(hilos)}


def _msgs_para(mm: list[dict], hilos: list[str], yo: str) -> list[dict]:
    idx = _hilos_json(hilos)
    out = []
    for m in mm:
        j = msg_json(m, yo)
        j["h"] = idx.get(j["h"], "h0")
        out.append(j)
    return out


def _lecturas_para(hilos: list[str], yo: str, tipo: str) -> dict[str, dict]:
    if tipo == "grupo":
        return {}
    idx = _hilos_json(hilos)
    return {idx[h]: v for h, v in lecturas_ajenas(hilos, yo).items() if h in idx}


def conversacion(clave: str, yo: str) -> dict | None:
    """Valida la clave: TODOS sus hilos deben ser míos (si alguno dejó de
    serlo, p. ej. salí del grupo, se descarta; si no queda ninguno → None)."""
    hilos = hilos_de_clave(clave)
    cache: dict = {}
    descs = [d for d in (descriptor(h, yo, cache) for h in hilos) if d]
    if not descs:
        return None
    return {"hilos": [d["hilo"] for d in descs], "principal": descs[0], "descs": descs, "cache": cache}


def _titulo_conv(conv: dict, yo: str) -> dict:
    """Título, foto y subtítulo del encabezado del chat."""
    d = conv["principal"]
    t = d["tipo"]
    ag = agenda_de(yo)
    negocio = next((x for x in conv["descs"] if x.get("negocio")), None)
    per = d.get("persona") or ""
    perf = perfiles([per]).get(per, {}) if per else {}
    if t == "grupo":
        g = grupo(d["ref_id"]) or {}
        return {"titulo": g.get("nombre") or "Grupo", "foto": g.get("foto") or "", "sub": f"{len(g.get('miembros') or [])} miembros",
                "grupo": d["ref_id"], "bloqueado": False}
    if negocio and negocio["tipo"] == "cancha":
        lo = locales_de([negocio["ref_id"]]).get(negocio["ref_id"]) or {}
        tit, foto, sub = lo.get("nombre") or "Dueño de cancha", lo.get("foto") or "", "Local · te responde el dueño"
    elif negocio and negocio["tipo"] == "academia":
        ia = academias_info([negocio["academia_id"]]).get(negocio["academia_id"]) or {}
        tit, foto, sub = ia.get("nombre") or "Academia", ia.get("logo") or "", "Academia · te responde el profe"
    else:
        tit = ag["apodos"].get(per) or (perf.get("nombre") or "").strip()
        if not tit and d["tipo"] == "academia" and d["es_profe"]:
            tit = nombres_alumnos([(d["academia_id"], per)]).get((d["academia_id"], per), "")
        tit = tit or per.split("@")[0]
        foto = perf.get("foto_url") or ""
        sub = {"cancha": "Cliente de tu local", "academia": "Alumno de tu academia"}.get(d["tipo"], "Chat directo") if d["es_profe"] or d["tipo"] == "directo" else ""
    return {"titulo": tit, "foto": foto, "sub": sub, "grupo": "", "bloqueado": bool(per) and per in ag["bloqueados"]}


# ═══════════════════════════ CSS + JS ════════════════════════════════════════

_CSS = """
<style>
.mj{display:grid;grid-template-columns:minmax(0,1fr);gap:0;max-width:1180px;margin:0 auto}
@media(min-width:900px){.mj.dos{grid-template-columns:minmax(300px,380px) minmax(0,1fr);border:1px solid var(--trazo);border-radius:var(--r-lg);overflow:hidden;background:#fff;height:calc(100dvh - var(--cab-h,81px) - 36px);min-height:460px;margin-top:16px}
  .mj.dos .mj-lista{border-right:1px solid var(--trazo);overflow:auto}.mj.dos .mj-chat{height:100%}}
@media(max-width:899px){.mj.dos .mj-lista{display:none}}
.mj-top{display:flex;align-items:center;justify-content:space-between;gap:10px;margin:8px 0 14px;flex-wrap:wrap}
.mj-top h1{font-size:28px;margin:0}
.mj-top .acc{display:flex;gap:8px;flex-wrap:wrap}.mj-top .acc .btn{padding:10px 14px;font-size:14px}
.mj-chips{display:flex;gap:8px;overflow-x:auto;padding:2px 2px 12px;scrollbar-width:none}.mj-chips::-webkit-scrollbar{display:none}
.mj-chip{flex:none;border:1px solid #E4E4E4;background:#fff;border-radius:999px;padding:8px 14px;font:inherit;font-size:14px;font-weight:600;color:var(--noche);cursor:pointer;box-shadow:0 1px 2px rgba(0,0,0,.06)}
.mj-chip.sel{background:#EBEBEB;border-color:#EBEBEB}.mj-chip small{color:var(--tenue);font-weight:700;margin-left:4px}
.mj-busca{margin:0 0 12px}.mj-busca input{border-radius:999px;padding:11px 16px;border:1px solid var(--trazo);font:inherit;font-size:15px;width:100%;background:#F7F7F7}
.mj-filas{display:flex;flex-direction:column}
.mj-fila{display:flex;align-items:center;gap:12px;padding:12px 10px;border-radius:14px;text-decoration:none;color:inherit;position:relative;min-width:0}
.mj-fila:hover{background:#F7F7F7}.mj-fila.act{background:#EBEBEB}
.mj-av{width:52px;height:52px;border-radius:50%;object-fit:cover;flex:none;background:var(--tinte);display:inline-flex;align-items:center;justify-content:center;font-weight:800;color:var(--teal);font-size:20px}
.mj-av.sm{width:40px;height:40px;font-size:16px}
.mj-fila .cuerpo{flex:1;min-width:0}
.mj-fila .l1{display:flex;align-items:baseline;gap:8px;min-width:0}.mj-fila .l1 b{font-size:15.5px;flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.mj-fila .l1 time{font-size:12.5px;color:var(--tenue);flex:none}.mj-fila.nl .l1 time{color:var(--esmeralda);font-weight:700}
.mj-fila .l2{display:flex;align-items:center;gap:6px;margin-top:3px;min-width:0}
.mj-fila .l2 span.pv{flex:1;min-width:0;color:var(--tenue);font-size:14px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.mj-fila.nl .l2 span.pv{color:var(--noche);font-weight:600}
.mj-n{background:var(--esmeralda);color:#fff;border-radius:999px;font-size:12px;font-weight:800;min-width:20px;height:20px;padding:0 6px;display:inline-flex;align-items:center;justify-content:center}
.mj-ic{font-size:13px;opacity:.7}
.mj-mas{border:0;background:transparent;font-size:20px;line-height:1;padding:6px 8px;border-radius:50%;cursor:pointer;color:var(--tenue);flex:none}.mj-mas:hover{background:#EBEBEB}
.mj-menu{position:fixed;z-index:60;background:#fff;border-radius:14px;box-shadow:0 10px 30px rgba(0,0,0,.16);padding:6px;min-width:200px;display:none}
.mj-menu.open{display:block}.mj-menu button{display:flex;gap:10px;align-items:center;width:100%;border:0;background:transparent;padding:11px 12px;border-radius:10px;font:inherit;font-size:15px;cursor:pointer;text-align:left;color:var(--noche)}
.mj-menu button:hover{background:#F2F2F2}.mj-menu button.mal{color:var(--rojo)}
.mj-vacio{text-align:center;padding:40px 16px;color:var(--tenue)}.mj-vacio .em{font-size:44px}
.mj-vacio h2{color:var(--noche);font-size:20px;margin:8px 0 6px}
.mj-arch{display:flex;align-items:center;gap:10px;padding:12px 10px;border-radius:14px;cursor:pointer;font-weight:700;border:0;background:transparent;font:inherit;width:100%;text-align:left;color:var(--noche)}
.mj-arch:hover{background:#F7F7F7}
/* ── chat ── */
.mj-chat{display:flex;flex-direction:column;background:#fff;min-width:0;min-height:0}
/* MÓVIL = pantalla completa tipo WhatsApp (shell pantalla="chat" quita cabecera y pie del sitio): cabecera del
   contacto arriba, mensajes con scroll propio al medio, compositor abajo. La altura sigue al visualViewport
   (--mj-vh, lo pone el JS) para que el teclado no tape el compositor. */
@media(max-width:899px){
  .mj-chat{position:fixed;left:0;right:0;top:var(--mj-top,0px);height:var(--mj-vh,100dvh);z-index:30}
  .mj-cab{padding-top:calc(8px + env(safe-area-inset-top));background:#fff}
}
.mj-cab{display:flex;align-items:center;gap:10px;padding:10px 14px;border-bottom:1px solid var(--trazo);min-width:0;flex:none}
.mj-cab .vol{text-decoration:none;font-size:22px;color:var(--noche);padding:4px 8px;border-radius:50%}.mj-cab .vol:hover{background:#F2F2F2}
@media(min-width:900px){.mj.dos .mj-cab .vol{display:none}}
.mj-cab .who{flex:1;min-width:0;text-decoration:none;color:inherit;display:flex;align-items:center;gap:10px}
.mj-cab .who b{display:block;font-size:16px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.mj-cab .who small{display:block;color:var(--tenue);font-size:12.5px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.mj-cab .ib{border:0;background:transparent;font-size:19px;padding:8px;border-radius:50%;cursor:pointer}.mj-cab .ib:hover{background:#F2F2F2}
.mj-msgs{flex:1;min-height:0;overflow-y:auto;padding:14px 14px 8px;background:#F7F7F7;display:flex;flex-direction:column;gap:3px;overscroll-behavior:contain}
.mj-msgs>:first-child{margin-top:auto}
.mj-dia{align-self:center;background:#fff;border-radius:999px;padding:4px 12px;font-size:12px;font-weight:700;color:var(--tenue);margin:10px 0 6px;box-shadow:0 1px 2px rgba(0,0,0,.06)}
.mj-b{max-width:min(78%,560px);padding:8px 11px 6px;border-radius:16px;background:#fff;box-shadow:0 1px 1.5px rgba(0,0,0,.08);align-self:flex-start;position:relative;overflow-wrap:anywhere;font-size:15px;line-height:1.38}
.mj-b.mio{align-self:flex-end;background:var(--tinte)}
.mj-b .au{font-size:12.5px;font-weight:800;color:var(--teal);margin-bottom:2px}
.mj-b .tx{white-space:pre-wrap}.mj-b .tx a{color:var(--teal);word-break:break-all}
.mj-b .pie{display:flex;justify-content:flex-end;align-items:center;gap:4px;font-size:11.5px;color:var(--tenue);margin-top:2px}
.mj-b .ck{font-size:12px;letter-spacing:-3px;color:#8A9AA5}.mj-b .ck.azul{color:#34B7F1}
.mj-b img.ft{display:block;max-width:100%;width:280px;max-height:340px;object-fit:cover;border-radius:12px;margin:2px 0 4px;cursor:zoom-in;background:#eee}
.mj-b img.gif{max-width:200px;border-radius:10px;background:transparent}
.mj-b audio{width:240px;max-width:100%}
.mj-b .cita{border-left:3px solid var(--esmeralda);background:rgba(0,0,0,.04);border-radius:8px;padding:5px 8px;margin-bottom:5px;font-size:13px;display:flex;gap:8px;align-items:center}
.mj-b .cita b{display:block;color:var(--teal);font-size:12.5px}.mj-b .cita img{width:38px;height:38px;border-radius:6px;object-fit:cover}
.mj-b .fw{font-size:12px;color:var(--tenue);font-style:italic;margin-bottom:2px}
.mj-b .doc,.mj-b .geo{display:flex;align-items:center;gap:8px;text-decoration:none;color:var(--noche);background:rgba(0,0,0,.04);border-radius:10px;padding:8px 10px;font-weight:600}
.mj-b .resp{position:absolute;top:4px;right:-34px;border:0;background:#fff;border-radius:50%;width:28px;height:28px;box-shadow:0 1px 3px rgba(0,0,0,.15);cursor:pointer;opacity:0;transition:opacity .15s;font-size:14px}
.mj-b.mio .resp{right:auto;left:-34px}.mj-b:hover .resp,.mj-b:focus-within .resp{opacity:1}
@media(hover:none){.mj-b .resp{opacity:.85;right:-30px}.mj-b.mio .resp{left:-30px}}
.mj-b.pend{opacity:.7}
.mj-mas-ant{align-self:center;border:1px solid var(--trazo);background:#fff;border-radius:999px;padding:7px 14px;font:inherit;font-size:13px;font-weight:700;cursor:pointer;margin:4px 0 8px}
.mj-comp{border-top:1px solid var(--trazo);padding:8px 10px calc(8px + env(safe-area-inset-bottom));background:#fff;flex:none}
.mj-cit{display:none;align-items:center;gap:8px;background:#F2F2F2;border-left:3px solid var(--esmeralda);border-radius:10px;padding:6px 10px;margin-bottom:6px;font-size:13px}
.mj-cit.on{display:flex}.mj-cit div{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.mj-cit button{border:0;background:transparent;font-size:18px;cursor:pointer}
.mj-fila2{display:flex;align-items:flex-end;gap:8px}
.mj-fila2 textarea{flex:1;min-width:0;resize:none;border:1px solid var(--trazo);border-radius:22px;padding:11px 16px;font:inherit;font-size:15px;max-height:140px;line-height:1.35;background:#F7F7F7}
.mj-fila2 .ib{flex:none;width:44px;height:44px;border-radius:50%;border:0;background:#F2F2F2;font-size:19px;cursor:pointer}
.mj-fila2 .env{background:var(--esmeralda);color:#fff;font-size:18px}.mj-fila2 .env:disabled{opacity:.45}
.mj-bloq{padding:14px;text-align:center;color:var(--tenue);font-size:14px}
.mj-foto-grande{position:fixed;inset:0;background:rgba(0,0,0,.88);z-index:80;display:none;align-items:center;justify-content:center;padding:16px}
.mj-foto-grande.open{display:flex}.mj-foto-grande img{max-width:100%;max-height:100%;border-radius:8px}
/* ── nuevo / grupos ── */
.mj-panel{max-width:640px;margin:0 auto}
.mj-res{display:flex;flex-direction:column;gap:2px;margin-top:10px}
.mj-per{display:flex;align-items:center;gap:12px;padding:10px;border-radius:14px;border:0;background:transparent;font:inherit;text-align:left;cursor:pointer;width:100%;color:inherit;text-decoration:none;min-width:0}
.mj-per:hover{background:#F7F7F7}.mj-per .cuerpo{flex:1;min-width:0}.mj-per b{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.mj-per small{color:var(--tenue)}
.mj-per .sel{font-size:20px}
.mj-elegidos{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0}.mj-elegidos .mj-chip{display:inline-flex;gap:6px;align-items:center}
.mj-sec{font-size:13px;font-weight:800;color:var(--tenue);text-transform:uppercase;letter-spacing:.04em;margin:18px 0 4px}
.mj-gfoto{display:flex;flex-direction:column;align-items:center;gap:8px;margin:6px 0 14px}
.mj-gfoto .mj-av{width:110px;height:110px;font-size:40px}
</style>
"""

_JS_COMUN = r"""
<script>
(function(){
var MESES = ['ene','feb','mar','abr','may','jun','jul','ago','set','oct','nov','dic'];
function pad(n){ return (n < 10 ? '0' : '') + n; }
window.mjHora = function(iso){ var d = new Date(iso); return isNaN(d) ? '' : pad(d.getHours()) + ':' + pad(d.getMinutes()); };
window.mjCuando = function(iso){ var d = new Date(iso); if(isNaN(d)) return ''; var h = new Date(), a = new Date(); a.setDate(h.getDate() - 1);
  if(d.toDateString() === h.toDateString()) return mjHora(iso); if(d.toDateString() === a.toDateString()) return 'Ayer';
  if((h - d) < 6 * 864e5) return ['dom','lun','mar','mié','jue','vie','sáb'][d.getDay()]; return d.getDate() + ' ' + MESES[d.getMonth()] + (d.getFullYear() !== h.getFullYear() ? ' ' + d.getFullYear() : ''); };
window.mjDia = function(iso){ var d = new Date(iso), h = new Date(), a = new Date(); a.setDate(h.getDate() - 1);
  if(d.toDateString() === h.toDateString()) return 'Hoy'; if(d.toDateString() === a.toDateString()) return 'Ayer';
  return ['Domingo','Lunes','Martes','Miércoles','Jueves','Viernes','Sábado'][d.getDay()] + ' ' + d.getDate() + ' ' + MESES[d.getMonth()] + (d.getFullYear() !== h.getFullYear() ? ' ' + d.getFullYear() : ''); };
window.mjEsc = function(s){ return String(s == null ? '' : s).replace(/[&<>"']/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]; }); };
window.mjAv = function(nombre, foto, cls){ cls = cls || 'mj-av'; if(foto) return "<img class='" + cls + "' src='" + mjEsc(foto) + "' alt='' loading='lazy' referrerpolicy='no-referrer'>";
  return "<span class='" + cls + "'>" + mjEsc((String(nombre || '?').trim() || '?').charAt(0).toUpperCase()) + "</span>"; };
window.mjLlamadas = function(){ pcgConfirmar({titulo: 'Llamadas en la app', icono: '📞', mensaje: 'Las llamadas de voz y las videollamadas se hacen desde la app Pichangol. Aquí puedes seguir escribiendo.', confirmar: 'Abrir la app', cancelar: 'Seguir aquí'})
  .then(function(ok){ if(ok) location.href = '""" + PLAY_URL + r"""'; }); };
// Foto rota (URL vencida o borrada) → inicial de color, como el app.
document.addEventListener('error', function(ev){ var im = ev.target; if(!im || im.tagName !== 'IMG' || !im.classList.contains('mj-av')) return;
  var c = im.closest('.mj-fila,.mj-per,.mj-cab,.mj-gfoto'), b = c && c.querySelector('b'), sp = document.createElement('span');
  sp.className = im.className; if(im.id) sp.id = im.id; sp.textContent = ((b && b.textContent.trim()) || '?').charAt(0).toUpperCase(); im.replaceWith(sp); }, true);
document.addEventListener('DOMContentLoaded', function(){ document.querySelectorAll('time[data-t]').forEach(function(t){ t.textContent = mjCuando(t.dataset.t); }); });
})();
</script>
"""


# ═══════════════════════════ Páginas ═════════════════════════════════════════

def _fila_html(f: dict, activa: set | None = None) -> str:
    j = fila_json(f)
    iconos = ("<span class='mj-ic' title='Fijado'>📌</span>" if j["fijado"] else "") + \
             ("<span class='mj-ic' title='Silenciado'>🔕</span>" if j["silenciado"] else "")
    nl = j["n"] > 0
    av = ui.e(j["titulo"])
    foto = (f"<img class='mj-av' src='{e(j['foto'])}' alt='' loading='lazy' referrerpolicy='no-referrer'>" if j["foto"]
            else f"<span class='mj-av'>{'👥' if j['tipo'] == 'grupo' else e((j['titulo'].strip() or '?')[:1].upper())}</span>")
    act = " act" if activa and set(f["hilos"]) & activa else ""
    return (f"<a class='mj-fila{' nl' if nl else ''}{act}' href='/mensajes/{quote(j['k'], safe='')}' data-k='{e(j['k'])}' "
            f"data-tipo='{e(j['tipo'])}' data-n='{j['n']}' data-fijado='{1 if j['fijado'] else 0}' data-arch='{1 if j['archivado'] else 0}' "
            f"data-sil='{1 if j['silenciado'] else 0}' data-tit='{av.lower()}'>{foto}"
            f"<div class='cuerpo'><div class='l1'><b>{av}</b><time data-t='{e(j['t'])}'></time></div>"
            f"<div class='l2'><span class='pv'>{e(j['preview'])}</span>{iconos}"
            + (f"<span class='mj-n'>{j['n']}</span>" if nl else "") +
            "</div></div><button type='button' class='mj-mas' aria-label='Opciones' data-menu='1'>⋯</button></a>")


def _lista_html(b: dict, activa: set | None = None) -> str:
    filas = b["filas"]
    n_nl = sum(1 for f in filas if f.get("no_leidos"))
    n_gr = sum(1 for f in filas if f["tipo"] == "grupo")
    chips = [("todos", "Todos", 0), ("nl", "No leídos", n_nl), ("academia", "Academias", 0), ("cancha", "Canchas", 0),
             ("grupo", "Grupos", n_gr), ("fijado", "Fijados", 0)]
    h = ["<div class='mj-busca'><input id='mjBusca' type='search' placeholder='Buscar un chat' autocomplete='off' aria-label='Buscar un chat'></div>",
         "<div class='mj-chips' id='mjChips'>"]
    for k, t, n in chips:
        h.append(f"<button type='button' class='mj-chip{' sel' if k == 'todos' else ''}' data-f='{k}'>{t}"
                 + (f"<small>{n}</small>" if n else "") + "</button>")
    h.append("</div>")
    if b["archivadas"]:
        h.append(f"<button type='button' class='mj-arch' id='mjVerArch'>🗄️ Archivados <small class='sub' style='margin:0'>{len(b['archivadas'])}</small></button>")
    h.append("<div class='mj-filas' id='mjFilas'>")
    h.extend(_fila_html(f, activa) for f in filas)
    h.append("</div><div class='mj-filas' id='mjFilasArch' hidden>")
    h.extend(_fila_html(f, activa) for f in b["archivadas"])
    h.append("</div>")
    vacio = ("<div class='mj-vacio' id='mjVacio'" + ("" if not filas and not b["archivadas"] else " hidden") + ">"
             "<div class='em'>💬</div><h2>Aún no tienes mensajes</h2>"
             "<p>Escríbele a una cancha o academia desde su ficha, o empieza un chat con otro jugador.</p>"
             "<a class='btn' href='/mensajes/nuevo'>Nuevo chat</a></div>")
    h.append(vacio)
    h.append("<div class='mj-vacio' id='mjNada' hidden><p>No hay chats con ese filtro.</p></div>")
    return "".join(h)


_JS_BANDEJA = r"""
<div class='mj-menu' id='mjMenu' role='menu'></div>
<script>
(function(){
var C = window.MJ || {}, filtro = 'todos', verArch = false, $ = function(i){ return document.getElementById(i); };
function aplicar(){ var q = ($('mjBusca') ? $('mjBusca').value : '').trim().toLowerCase(), vis = 0;
  var cont = verArch ? $('mjFilasArch') : $('mjFilas');
  if($('mjFilas')) $('mjFilas').hidden = verArch; if($('mjFilasArch')) $('mjFilasArch').hidden = !verArch;
  if(!cont) return;
  cont.querySelectorAll('.mj-fila').forEach(function(a){ var ok = true, d = a.dataset;
    if(q && d.tit.indexOf(q) < 0) ok = false;
    if(!verArch){ if(filtro === 'nl' && d.n === '0') ok = false; if((filtro === 'academia' || filtro === 'cancha' || filtro === 'grupo') && d.tipo !== filtro) ok = false; if(filtro === 'fijado' && d.fijado !== '1') ok = false; }
    a.style.display = ok ? '' : 'none'; if(ok) vis++; });
  var tot = cont.querySelectorAll('.mj-fila').length;
  if($('mjNada')) $('mjNada').hidden = !(tot && !vis);
  if($('mjVerArch')) $('mjVerArch').innerHTML = verArch ? '‹ Volver a tus chats' : ('🗄️ Archivados <small class="sub" style="margin:0">' + $('mjFilasArch').querySelectorAll('.mj-fila').length + '</small>');
}
if($('mjChips')) $('mjChips').addEventListener('click', function(ev){ var b = ev.target.closest('[data-f]'); if(!b) return; filtro = b.dataset.f; verArch = false;
  this.querySelectorAll('.mj-chip').forEach(function(x){ x.classList.toggle('sel', x === b); }); aplicar(); });
if($('mjBusca')) $('mjBusca').addEventListener('input', aplicar);
document.addEventListener('click', function(ev){ if(ev.target.closest('#mjVerArch')){ verArch = !verArch; aplicar(); } });
// ── menú ⋯ de cada fila (fijar / archivar / silenciar / eliminar), como la hoja del app ──
var menu = $('mjMenu'), filaMenu = null;
function cerrar(){ menu.classList.remove('open'); filaMenu = null; }
document.addEventListener('click', function(ev){ var b = ev.target.closest('.mj-mas');
  if(b){ ev.preventDefault(); ev.stopPropagation(); var a = b.closest('.mj-fila'); filaMenu = a; var d = a.dataset;
    menu.innerHTML = (d.arch === '1' ? '' : "<button data-a='" + (d.fijado === '1' ? 'desfijar' : 'fijar') + "'>📌 " + (d.fijado === '1' ? 'Desfijar' : 'Fijar chat') + "</button>")
      + "<button data-a='" + (d.arch === '1' ? 'desarchivar' : 'archivar') + "'>🗄️ " + (d.arch === '1' ? 'Desarchivar' : 'Archivar chat') + "</button>"
      + "<button data-a='" + (d.sil === '1' ? 'activar' : 'silenciar') + "'>" + (d.sil === '1' ? '🔔 Activar avisos' : '🔕 Silenciar') + "</button>"
      + "<button class='mal' data-a='eliminar'>🗑 Eliminar chat</button>";
    var r = b.getBoundingClientRect(); menu.classList.add('open'); var w = menu.offsetWidth, hgt = menu.offsetHeight;
    menu.style.left = Math.max(8, Math.min(window.innerWidth - w - 8, r.right - w)) + 'px';
    menu.style.top = (r.bottom + hgt + 8 > window.innerHeight ? Math.max(8, r.top - hgt - 4) : r.bottom + 4) + 'px'; return; }
  if(!ev.target.closest('#mjMenu')) cerrar(); });
document.addEventListener('keydown', function(ev){ if(ev.key === 'Escape') cerrar(); });
menu.addEventListener('click', function(ev){ var b = ev.target.closest('[data-a]'); if(!b || !filaMenu) return; var a = filaMenu, acc = b.dataset.a; cerrar();
  var go = acc === 'eliminar' ? pcgConfirmar({titulo: '¿Eliminar este chat?', mensaje: 'Se quita de tu bandeja (no se borra para la otra persona). Si te vuelven a escribir, reaparece.', confirmar: 'Eliminar', destructivo: true}) : Promise.resolve(true);
  go.then(function(ok){ if(!ok) return; window.mjAccion(a.dataset.k, acc).then(function(j){ if(!j) return;
    if(acc === 'eliminar'){ if(window.MJ_ABIERTA === a.dataset.k){ pcgIr('/mensajes', 'Un momento…'); return; } a.remove(); pcgToast('Chat eliminado.'); }
    else { pcgRecargar(); } }); }); });
window.mjAccion = function(k, acc){ return fetch('/web/mensajes/accion', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({k: k, accion: acc})})
  .then(function(r){ return r.json(); }).then(function(j){ if(!j.ok){ pcgAvisar({titulo: 'No se pudo', icono: '⚠️', mensaje: j.mensaje || 'Reintenta.'}); return null; } return j; })
  .catch(function(){ pcgAvisar({titulo: 'Sin conexión', icono: '⚠️', mensaje: 'Revisa tu conexión y reintenta.'}); return null; }); };
aplicar();
// ── Refresco en silencio (solo con la pestaña visible) + caché local para pintar al instante ──
function pintar(filas, arch){ var act = window.MJ_ABIERTA || '';
  function fila(f){ var nl = f.n > 0, ini = f.tipo === 'grupo' ? '👥' : mjEsc((String(f.titulo).trim() || '?').charAt(0).toUpperCase());
    return "<a class='mj-fila" + (nl ? ' nl' : '') + (f.k === act ? ' act' : '') + "' href='/mensajes/" + encodeURIComponent(f.k) + "' data-k='" + mjEsc(f.k) + "' data-tipo='" + f.tipo + "' data-n='" + f.n + "' data-fijado='" + (f.fijado ? 1 : 0) + "' data-arch='" + (f.archivado ? 1 : 0) + "' data-sil='" + (f.silenciado ? 1 : 0) + "' data-tit='" + mjEsc(String(f.titulo).toLowerCase()) + "'>"
      + (f.foto ? "<img class='mj-av' src='" + mjEsc(f.foto) + "' alt='' loading='lazy' referrerpolicy='no-referrer'>" : "<span class='mj-av'>" + ini + "</span>")
      + "<div class='cuerpo'><div class='l1'><b>" + mjEsc(f.titulo) + "</b><time>" + mjCuando(f.t) + "</time></div><div class='l2'><span class='pv'>" + mjEsc(f.preview) + "</span>"
      + (f.fijado ? "<span class='mj-ic'>📌</span>" : '') + (f.silenciado ? "<span class='mj-ic'>🔕</span>" : '') + (nl ? "<span class='mj-n'>" + f.n + "</span>" : '')
      + "</div></div><button type='button' class='mj-mas' aria-label='Opciones' data-menu='1'>⋯</button></a>"; }
  if($('mjFilas')) $('mjFilas').innerHTML = filas.map(fila).join(''); if($('mjFilasArch')) $('mjFilasArch').innerHTML = arch.map(fila).join('');
  if($('mjVacio')) $('mjVacio').hidden = !!(filas.length || arch.length);
  if($('mjVerArch')) $('mjVerArch').style.display = arch.length ? '' : 'none';
  aplicar(); }
var KEY = C.cache ? 'pcg_bandeja_' + C.cache : '';
try { if(KEY && !C.fresca){ var c = JSON.parse(localStorage.getItem(KEY) || 'null'); if(c && c.filas) pintar(c.filas, c.archivadas || []); } } catch(e){}
try { if(KEY && C.inicial) localStorage.setItem(KEY, JSON.stringify(C.inicial)); } catch(e){}
function refrescar(){ if(document.visibilityState !== 'visible' || menu.classList.contains('open')) return;
  fetch('/web/mensajes/bandeja', {headers: {'Accept': 'application/json'}}).then(function(r){ return r.json(); }).then(function(j){ if(!j.ok) return;
    try { if(KEY) localStorage.setItem(KEY, JSON.stringify(j)); } catch(e){}
    pintar(j.filas, j.archivadas); }).catch(function(){}); }
setInterval(refrescar, C.cada || 12000);
document.addEventListener('visibilitychange', function(){ if(document.visibilityState === 'visible') refrescar(); });
})();
</script>
"""


def _clave_cache(email: str) -> str:
    """Clave de `localStorage` por cuenta (hash: no deja el correo en el navegador)."""
    return hashlib.sha256((sesion._secreto()[:8] + _low(email).encode())).hexdigest()[:16]


def _cabecera_bandeja() -> str:
    return ("<div class='mj-top'><h1>Mensajes</h1><div class='acc'>"
            "<a class='btn sec' href='/mensajes/grupo/nuevo'>👥 Nuevo grupo</a>"
            "<a class='btn' href='/mensajes/nuevo'>✏️ Nuevo chat</a></div></div>")


@router.get("/mensajes", response_class=HTMLResponse)
def pagina_mensajes(request: Request) -> HTMLResponse:
    """Bandeja = `mensajes_screen.dart`."""
    ses = sesion.de_request(request)
    if not ses or not ses.get("email"):
        return sin_sesion(request, "/mensajes", "Mensajes", "Tu bandeja de mensajes")
    yo = _low(ses["email"])
    b = bandeja(yo)
    inicial = {"ok": True, "filas": [fila_json(f) for f in b["filas"]], "archivadas": [fila_json(f) for f in b["archivadas"]]}
    cfg = {"cache": _clave_cache(yo), "inicial": inicial, "fresca": True, "cada": 12000}
    cuerpo = (_CSS + "<div class='mj-panel' style='max-width:760px'>" + _cabecera_bandeja() + _lista_html(b) + "</div>"
              + f"<script>window.MJ = {json.dumps(cfg, ensure_ascii=False)};</script>" + _JS_COMUN + _JS_BANDEJA)
    return ui.shell("Mensajes", cuerpo, sesion=ses, titulo_tab="Mensajes · Pichangol", pantalla="mensajes")


_JS_CHAT = r"""
<div class='mj-foto-grande' id='mjFotoG'><img alt=''></div>
<script>
(function(){
var C = window.MJC, $ = function(i){ return document.getElementById(i); }, caja = $('mjMsgs');
var vistos = {}, msgs = [], lect = C.lecturas || {}, resp = null, enviando = false, ultimoLeer = 0;
function linkify(t){ return mjEsc(t).replace(/(https?:\/\/[^\s<]+)/g, function(u){ return "<a href='" + u + "' target='_blank' rel='noopener nofollow'>" + u + "</a>"; }); }
function checks(m){ if(!m.mio || C.grupo) return ''; if(m.pend) return "<span class='ck'>🕓</span>"; var l = lect[m.h] || {};
  if(l.l && l.l >= m.t) return "<span class='ck azul'>✓✓</span>"; if(l.e && l.e >= m.t) return "<span class='ck'>✓✓</span>"; return "<span class='ck'>✓</span>"; }
function burbuja(m){ var h = "<div class='mj-b" + (m.mio ? ' mio' : '') + (m.pend ? ' pend' : '') + "' data-id='" + mjEsc(m.id) + "'>";
  if(C.grupo && !m.mio && m.autor) h += "<div class='au'>" + mjEsc(m.autor) + "</div>";
  if(m.fw) h += "<div class='fw'>↪ Reenviado</div>";
  if(m.rt || m.ra) h += "<div class='cita'>" + (m.rm ? "<img src='" + mjEsc(m.rm) + "' alt=''>" : '') + "<div><b>" + mjEsc(m.ra || '') + "</b>" + mjEsc(m.rt || '') + "</div></div>";
  if(m.c === 'foto') h += "<img class='ft' src='" + mjEsc(m.media) + "' alt='Foto' loading='lazy'>" + (m.texto && m.texto !== '📷 Foto' ? "<div class='tx'>" + linkify(m.texto) + "</div>" : '');
  else if(m.c === 'gif') h += "<img class='gif' src='" + mjEsc(m.media) + "' alt='GIF' loading='lazy'>";
  else if(m.c === 'audio') h += "<audio controls preload='none' src='" + mjEsc(m.media) + "'></audio>";
  else if(m.c === 'doc') h += "<a class='doc' href='" + mjEsc(m.media) + "' target='_blank' rel='noopener'>📄 " + mjEsc((m.texto || '').replace(/^📄\s*/, '') || 'Documento') + "</a>";
  else if(m.c === 'geo') h += "<a class='geo' href='https://www.google.com/maps?q=" + encodeURIComponent(m.geo) + "' target='_blank' rel='noopener'>📍 Ubicación · ver en el mapa</a>";
  else if(m.c === 'geolive') h += "<div class='geo'>📍 Ubicación en tiempo real · se ve en la app</div>";
  else if(m.c === 'llamada') h += "<div class='geo'>" + mjEsc(m.texto) + " · desde la app</div>";
  else h += "<div class='tx'>" + linkify(m.texto) + "</div>";
  h += "<div class='pie'>" + mjHora(m.t) + checks(m) + "</div>";
  if(!m.pend && C.puedeEscribir) h += "<button type='button' class='resp' title='Responder' aria-label='Responder' data-r='" + mjEsc(m.id) + "'>↩</button>";
  return h + "</div>"; }
function pintar(abajo){ var cerca = caja.scrollHeight - caja.scrollTop - caja.clientHeight < 120, top = caja.scrollTop, alto = caja.scrollHeight;
  msgs.sort(function(a, b){ return a.t < b.t ? -1 : (a.t > b.t ? 1 : 0); });
  var h = C.hayMas ? "<button type='button' class='mj-mas-ant' id='mjAnt'>Cargar mensajes anteriores</button>" : '', dia = '';
  if(!msgs.length) h += "<div class='mj-vacio'><div class='em'>👋</div><p>" + mjEsc(C.vacio) + "</p></div>";
  msgs.forEach(function(m){ var d = mjDia(m.t); if(d !== dia){ dia = d; h += "<div class='mj-dia'>" + d + "</div>"; } h += burbuja(m); });
  caja.innerHTML = h;
  if(abajo === 'mantener') caja.scrollTop = top + (caja.scrollHeight - alto); else if(abajo || cerca) caja.scrollTop = caja.scrollHeight; }
function sumar(lista){ var nuevos = 0; (lista || []).forEach(function(m){ if(vistos[m.id]) return;
  msgs = msgs.filter(function(x){ return !(x.pend && x.mio && m.mio && x.texto === m.texto && x.c === m.c); }); vistos[m.id] = 1; msgs.push(m); nuevos++; }); return nuevos; }
// Alto real de la pantalla: en escritorio la caja del chat descuenta la cabecera del sitio (--cab-h); en móvil la
// conversación sigue al visualViewport (--mj-vh/--mj-top) para que el teclado no tape el compositor. Si estaba
// abajo, se queda abajo (último mensaje siempre visible), como WhatsApp.
function medir(){ var R = document.documentElement.style, cab = document.querySelector('header.nav'), vv = window.visualViewport;
  var abajo = caja.scrollHeight - caja.scrollTop - caja.clientHeight < 120;
  R.setProperty('--cab-h', ((cab && cab.offsetHeight) || 0) + 'px');
  if(vv && window.innerWidth < 900){ R.setProperty('--mj-vh', Math.round(vv.height) + 'px'); R.setProperty('--mj-top', Math.round(vv.offsetTop) + 'px'); }
  else { R.removeProperty('--mj-vh'); R.removeProperty('--mj-top'); }
  if(abajo) caja.scrollTop = caja.scrollHeight; }
medir(); window.addEventListener('resize', medir);
if(window.visualViewport){ visualViewport.addEventListener('resize', medir); visualViewport.addEventListener('scroll', medir); }
sumar(C.mensajes); pintar(true);
// Las fotos cargan después: si el usuario estaba abajo, seguir abajo cuando crecen.
caja.addEventListener('load', function(ev){ if(ev.target.tagName === 'IMG' && caja.scrollHeight - caja.scrollTop - caja.clientHeight < 400) caja.scrollTop = caja.scrollHeight; }, true);
caja.addEventListener('click', function(ev){ var r = ev.target.closest('[data-r]');
  if(r){ var m = msgs.filter(function(x){ return x.id === r.dataset.r; })[0]; if(!m) return; resp = m;
    $('mjCitT').innerHTML = '<b>' + mjEsc(m.mio ? 'Tú' : (m.autor || C.titulo)) + '</b> · ' + mjEsc(m.c === 'foto' ? (m.texto || '📷 Foto') : (m.c === 'audio' ? '🎤 Nota de voz' : (m.c === 'gif' ? '🎞️ GIF' : m.texto)));
    $('mjCit').classList.add('on'); $('mjTexto').focus(); return; }
  var im = ev.target.closest('img.ft'); if(im){ var g = $('mjFotoG'); g.querySelector('img').src = im.src; g.classList.add('open'); return; }
  if(ev.target.id === 'mjAnt') anteriores(); });
$('mjFotoG').onclick = function(){ this.classList.remove('open'); };
if($('mjCitX')) $('mjCitX').onclick = function(){ resp = null; $('mjCit').classList.remove('on'); };
function anteriores(){ if(!msgs.length) return; var b = $('mjAnt'); if(b){ b.disabled = true; b.textContent = 'Cargando…'; }
  fetch('/web/mensajes/hilo?k=' + encodeURIComponent(C.k) + '&antes=' + encodeURIComponent(msgs[0].t)).then(function(r){ return r.json(); }).then(function(j){
    if(!j.ok) return; C.hayMas = j.mensajes.length >= C.limite; sumar(j.mensajes); pintar('mantener'); }).catch(function(){ if(b){ b.disabled = false; b.textContent = 'Cargar mensajes anteriores'; } }); }
function ultimoT(){ var t = ''; msgs.forEach(function(m){ if(!m.pend && m.t > t) t = m.t; }); return t; }
var sondeando = false;
function sondear(){ if(sondeando || document.visibilityState !== 'visible') return; sondeando = true;
  var leer = document.hasFocus() ? 1 : 0;
  fetch('/web/mensajes/hilo?k=' + encodeURIComponent(C.k) + '&desde=' + encodeURIComponent(ultimoT()) + '&leer=' + leer).then(function(r){ return r.json(); }).then(function(j){
    sondeando = false; if(!j.ok){ if(j.error === 'sin_acceso'){ pcgAvisar({titulo: 'Ya no estás en este chat', icono: '👥', mensaje: j.mensaje}).then(function(){ pcgIr('/mensajes'); }); clearInterval(tm); } return; }
    var antes = JSON.stringify(lect); lect = j.lecturas || lect; var n = sumar(j.mensajes); if(n || JSON.stringify(lect) !== antes) pintar(false); })
    .catch(function(){ sondeando = false; }); }
var tm = setInterval(sondear, 4500);
document.addEventListener('visibilitychange', function(){ if(document.visibilityState === 'visible') sondear(); });
window.addEventListener('focus', sondear);
// ── Enviar texto (Enter envía, Shift+Enter salta de línea) ──
var ta = $('mjTexto');
function ajustar(){ if(!ta) return; ta.style.height = 'auto'; ta.style.height = Math.min(140, ta.scrollHeight) + 'px'; $('mjEnv').disabled = !ta.value.trim(); }
if(ta){ ta.addEventListener('input', ajustar); ta.addEventListener('keydown', function(ev){ if(ev.key === 'Enter' && !ev.shiftKey && !ev.isComposing && window.matchMedia('(hover:hover)').matches){ ev.preventDefault(); enviar(); } }); ajustar(); }
function enviar(){ var t = (ta.value || '').trim(); if(!t || enviando) return; if(t.length > C.max){ pcgAvisar({titulo: 'Mensaje muy largo', icono: '✍️', mensaje: 'Máximo ' + C.max + ' caracteres.'}); return; }
  enviando = true; var tmp = {id: 'tmp' + Date.now(), mio: true, pend: true, texto: t, c: '', t: new Date().toISOString(), h: 'h0', rt: resp ? 'x' : '', ra: ''};
  if(resp){ tmp.ra = resp.mio ? 'Tú' : (resp.autor || C.titulo); tmp.rt = resp.texto || ''; }
  msgs.push(tmp); pintar(true); var rid = resp ? resp.id : ''; ta.value = ''; ajustar(); resp = null; $('mjCit').classList.remove('on');
  fetch('/web/mensajes/enviar', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({k: C.k, texto: t, resp: rid})})
    .then(function(r){ return r.json(); }).then(function(j){ enviando = false; msgs = msgs.filter(function(x){ return x.id !== tmp.id; });
      if(!j.ok){ pintar(false); ta.value = t; ajustar(); pcgAvisar({titulo: 'No se envió', icono: '⚠️', mensaje: j.mensaje || 'Revisa tu conexión y reintenta.'}); return; }
      sumar([j.mensaje]); pintar(true); })
    .catch(function(){ enviando = false; msgs = msgs.filter(function(x){ return x.id !== tmp.id; }); pintar(false); ta.value = t; ajustar(); pcgAvisar({titulo: 'Sin conexión', icono: '⚠️', mensaje: 'No se pudo enviar. Revisa tu conexión.'}); }); }
if($('mjEnv')) $('mjEnv').onclick = enviar;
// ── Foto: se comprime a 1600 px (como `pickImage(maxWidth: 1600, imageQuality: 80)`) ──
function comprimir(file){ return new Promise(function(res, rej){ var img = new Image(), u = URL.createObjectURL(file);
  img.onload = function(){ var k = Math.min(1, 1600 / Math.max(img.width, img.height)), cv = document.createElement('canvas'); cv.width = Math.round(img.width * k); cv.height = Math.round(img.height * k);
    cv.getContext('2d').drawImage(img, 0, 0, cv.width, cv.height); URL.revokeObjectURL(u); cv.toBlob(function(b){ b ? res(b) : rej(); }, 'image/jpeg', 0.8); };
  img.onerror = function(){ URL.revokeObjectURL(u); rej(); }; img.src = u; }); }
if($('mjClip')) $('mjClip').onclick = function(){ if(!C.subida){ pcgAvisar({titulo: 'Fotos no disponibles', icono: '📷', mensaje: 'El envío de fotos no está disponible en este momento. Puedes enviarlas desde la app.'}); return; } $('mjArchivo').click(); };
if($('mjArchivo')) $('mjArchivo').onchange = function(){ var f = this.files && this.files[0]; this.value = ''; if(!f) return;
  if(!/^image\//.test(f.type)){ pcgAvisar({titulo: 'Solo fotos', icono: '📷', mensaje: 'Desde la web puedes enviar fotos. Audios y documentos, desde la app.'}); return; }
  pcgCargando('Enviando foto…');
  comprimir(f).then(function(b){ return fetch('/web/mensajes/foto?k=' + encodeURIComponent(C.k), {method: 'POST', headers: {'Content-Type': 'image/jpeg'}, body: b}); })
    .then(function(r){ return r.json(); }).then(function(j){ pcgCargando(false); if(!j.ok) return pcgAvisar({titulo: 'No se envió', icono: '⚠️', mensaje: j.mensaje || 'Reintenta.'}); sumar([j.mensaje]); pintar(true); })
    .catch(function(){ pcgCargando(false); pcgAvisar({titulo: 'No se envió', icono: '⚠️', mensaje: 'No se pudo enviar la foto. Reintenta.'}); }); };
// ── Menú del encabezado ──
if($('mjOpc')) $('mjOpc').addEventListener('click', function(ev){ ev.preventDefault(); ev.stopPropagation();
  var menu = $('mjMenu'), d = C.estado; window.MJ_MENU_K = C.k;
  menu.innerHTML = (C.grupo ? "<button data-x='info'>ℹ️ Info del grupo</button>" : '')
    + (d.archivado ? '' : "<button data-a='" + (d.fijado ? 'desfijar' : 'fijar') + "'>📌 " + (d.fijado ? 'Desfijar' : 'Fijar chat') + "</button>")
    + "<button data-a='" + (d.archivado ? 'desarchivar' : 'archivar') + "'>🗄️ " + (d.archivado ? 'Desarchivar' : 'Archivar chat') + "</button>"
    + "<button data-a='" + (d.silenciado ? 'activar' : 'silenciar') + "'>" + (d.silenciado ? '🔔 Activar avisos' : '🔕 Silenciar') + "</button>"
    + "<button class='mal' data-a='eliminar'>🗑 Eliminar chat</button>";
  var r = this.getBoundingClientRect(); menu.classList.add('open'); menu.style.left = Math.max(8, r.right - menu.offsetWidth) + 'px'; menu.style.top = (r.bottom + 4) + 'px'; });
document.addEventListener('click', function(ev){ var menu = $('mjMenu'); if(!menu || !window.MJ_MENU_K) return; var b = ev.target.closest('#mjMenu [data-a], #mjMenu [data-x]');
  if(!b){ if(!ev.target.closest('#mjMenu')){ menu.classList.remove('open'); window.MJ_MENU_K = null; } return; }
  ev.stopImmediatePropagation(); menu.classList.remove('open'); window.MJ_MENU_K = null;
  if(b.dataset.x === 'info'){ pcgIr('/mensajes/grupo/' + encodeURIComponent(C.grupo)); return; }
  var acc = b.dataset.a, go = acc === 'eliminar' ? pcgConfirmar({titulo: '¿Eliminar este chat?', mensaje: 'Se quita de tu bandeja (no se borra para la otra persona). Si te vuelven a escribir, reaparece.', confirmar: 'Eliminar', destructivo: true}) : Promise.resolve(true);
  go.then(function(ok){ if(!ok) return; mjAccion(C.k, acc).then(function(j){ if(!j) return; if(acc === 'eliminar') pcgIr('/mensajes', 'Un momento…'); else pcgRecargar(); }); }); }, true);
})();
</script>
"""


def _cabecera_chat(conv: dict, tit: dict) -> str:
    foto = (f"<img class='mj-av sm' src='{e(tit['foto'])}' alt='' referrerpolicy='no-referrer'>" if tit["foto"]
            else f"<span class='mj-av sm'>{'👥' if tit['grupo'] else e((tit['titulo'].strip() or '?')[:1].upper())}</span>")
    who_href = f"/mensajes/grupo/{quote(tit['grupo'], safe='')}" if tit["grupo"] else "#"
    return ("<div class='mj-cab'><a class='vol' href='/mensajes' aria-label='Volver'>‹</a>"
            f"<a class='who' href='{who_href}'" + ("" if tit["grupo"] else " onclick='return false'") + f">{foto}"
            f"<span style='min-width:0'><b>{e(tit['titulo'])}</b><small>{e(tit['sub'])}</small></span></a>"
            "<button type='button' class='ib' onclick='mjLlamadas()' title='Llamar' aria-label='Llamar'>📞</button>"
            "<button type='button' class='ib' id='mjOpc' title='Opciones' aria-label='Opciones'>⋯</button></div>")


@router.get("/mensajes/nuevo", response_class=HTMLResponse)
def pagina_nuevo(request: Request, cancha: str = "", academia: str = "", persona: str = ""):
    """Nuevo chat = `buscar_usuario_screen.dart`; con `cancha`/`academia`/`persona`
    abre (o reusa) la conversación y redirige al chat."""
    ses = sesion.de_request(request)
    ruta = str(request.url.path) + (("?" + request.url.query) if request.url.query else "")
    if not ses or not ses.get("email"):
        return sin_sesion(request, ruta, "Mensajes", "Escribir mensajes")
    yo = _low(ses["email"])
    if cancha or academia or persona:
        return _abrir_con(ses, yo, cancha=cancha, academia=academia, persona=persona)
    ag = agenda_de(yo)
    contactos = [c for c in ag["contactos"] if c != yo][:60]
    perf = perfiles(contactos)
    filas = []
    for c in contactos:
        p = perf.get(c) or {}
        nom = ag["apodos"].get(c) or p.get("nombre") or c.split("@")[0]
        filas.append((nom.lower(), f"<a class='mj-per' href='/mensajes/nuevo?persona={quote(ref_de(c), safe='')}'>"
                                   + _av_html(nom, p.get("foto_url") or "") +
                                   f"<span class='cuerpo'><b>{e(nom)}</b><small>{e(_ocultar_correo(c))}</small></span></a>"))
    filas.sort()
    cuerpo = (_CSS + "<div class='mj-panel'><div class='mj-top'><h1>Nuevo chat</h1><div class='acc'>"
              "<a class='btn sec' href='/mensajes'>‹ Mensajes</a></div></div>"
              "<a class='mj-per' href='/mensajes/grupo/nuevo'><span class='mj-av'>👥</span><span class='cuerpo'><b>Nuevo grupo</b>"
              "<small>Chatea con varios jugadores a la vez</small></span></a>"
              "<div class='mj-busca' style='margin-top:12px'><input id='mjQ' type='search' placeholder='Busca por nombre o correo' autocomplete='off' aria-label='Buscar jugadores'></div>"
              "<div class='mj-res' id='mjRes'></div>"
              + ("<div class='mj-sec'>Mis contactos</div><div class='mj-res'>" + "".join(f for _, f in filas) + "</div>" if filas else "")
              + "</div>" + _JS_COMUN + _JS_BUSCAR.replace("__MODO__", "chat"))
    return ui.shell("Nuevo chat", cuerpo, sesion=ses, titulo_tab="Nuevo chat · Pichangol", pantalla="mensajes")


def _av_html(nombre: str, foto: str, cls: str = "mj-av") -> str:
    if foto:
        return f"<img class='{cls}' src='{e(foto)}' alt='' loading='lazy' referrerpolicy='no-referrer'>"
    return f"<span class='{cls}'>{e((nombre.strip() or '?')[:1].upper())}</span>"


_JS_BUSCAR = r"""
<script>
(function(){
var q = document.getElementById('mjQ'), caja = document.getElementById('mjRes'), t = null, modo = '__MODO__';
if(!q) return;
q.addEventListener('input', function(){ clearTimeout(t); var v = q.value.trim();
  if(v.length < 2){ caja.innerHTML = v ? "<p class='sub' style='font-size:13px'>Escribe al menos 2 letras.</p>" : ''; return; }
  t = setTimeout(function(){ fetch('/web/mensajes/buscar?q=' + encodeURIComponent(v)).then(function(r){ return r.json(); }).then(function(j){
    if(!j.ok) return; if(!j.jugadores.length){ caja.innerHTML = "<p class='sub' style='font-size:14px'>No encontramos jugadores con «" + mjEsc(v) + "».</p>"; return; }
    caja.innerHTML = j.jugadores.map(function(p){ var inner = mjAv(p.nombre, p.foto) + "<span class='cuerpo'><b>" + mjEsc(p.nombre) + "</b><small>" + mjEsc(p.sub) + "</small></span>";
      return modo === 'chat' ? "<a class='mj-per' href='/mensajes/nuevo?persona=" + encodeURIComponent(p.ref) + "'>" + inner + "</a>"
        : "<button type='button' class='mj-per' data-ref='" + mjEsc(p.ref) + "' data-u='" + mjEsc(p.u) + "' data-nombre='" + mjEsc(p.nombre) + "' data-foto='" + mjEsc(p.foto) + "'>" + inner + "<span class='sel'>＋</span></button>"; }).join(''); })
    .catch(function(){}); }, 350); });
})();
</script>
"""


def _abrir_con(ses: dict, yo: str, cancha: str = "", academia: str = "", persona: str = ""):
    """Abre el chat: cancha → `cancha_<dueño>|<yo>`; academia → `<id>|<yo>`;
    persona → reusa la fila existente con esa persona o `directo_a|b`."""
    def aviso(titulo: str, msg: str, btn: str = "", href: str = "") -> HTMLResponse:
        cuerpo = (f"<div class='panel' style='max-width:520px;margin:40px auto;text-align:center'><h1 style='font-size:22px'>{e(titulo)}</h1>"
                  f"<p class='sub'>{e(msg)}</p><div class='acciones' style='justify-content:center'>"
                  f"<a class='btn' href='{e(href or '/mensajes')}'>{e(btn or 'Ir a Mensajes')}</a></div></div>")
        return ui.shell(titulo, cuerpo, sesion=ses, pantalla="mensajes")

    principal = ""
    persona_em = ""
    if cancha:
        c = datos.cancha(cancha) or {}
        dueno = _low(c.get("dueno"))
        if not c:
            return aviso("Cancha no encontrada", "Esta cancha ya no está disponible.")
        if not dueno:
            return aviso("Aún sin dueño", "Esta cancha todavía no tiene un dueño en Pichangol, así que no hay a quién escribirle.",
                         "Ver la cancha", f"/reservar/{quote(cancha, safe='')}")
        if dueno == yo:
            return aviso("Es tu cancha", "Los mensajes de tus clientes te llegan a tu bandeja de Mensajes.")
        principal, persona_em = hilo_cancha(dueno, yo), dueno
    elif academia:
        a = datos.academia(academia) or {}
        if not a:
            return aviso("Academia no encontrada", "Esta academia ya no está disponible.")
        dueno = _low(a.get("dueno"))
        if dueno == yo:
            return aviso("Es tu academia", "Los mensajes de tus alumnos te llegan a tu bandeja de Mensajes.")
        principal, persona_em = hilo_academia(academia, yo), dueno
    else:
        otro = email_de_ref(persona)
        if not otro or otro == yo:
            return aviso("Enlace vencido", "Vuelve a buscar a la persona para escribirle.", "Nuevo chat", "/mensajes/nuevo")
        principal, persona_em = hilo_directo(yo, otro), otro
    # Una persona = un chat: si ya conversamos (por la cancha, la academia o
    # directo), el historial completo viene con la conversación.
    hilos = [principal]
    if persona_em:
        for f in _todas(yo):
            if f.get("persona") == persona_em:
                if persona:  # desde el buscador: se reusa la fila tal cual (`onAbrirChat`)
                    hilos = list(f["hilos"])
                else:
                    hilos = [principal] + [h for h in f["hilos"] if h != principal]
                break
    return RedirectResponse(f"/mensajes/{quote(clave_de(hilos), safe='')}", status_code=303)


def _todas(yo: str) -> list[dict]:
    b = bandeja(yo, marcar=False)
    return b["filas"] + b["archivadas"]


@router.get("/mensajes/grupo/nuevo", response_class=HTMLResponse)
def pagina_nuevo_grupo(request: Request):
    """`crear_grupo_screen.dart`: nombre + miembros (buscador y contactos)."""
    ses = sesion.de_request(request)
    if not ses or not ses.get("email"):
        return sin_sesion(request, "/mensajes/grupo/nuevo", "Nuevo grupo", "Crear grupos")
    yo = _low(ses["email"])
    ag = agenda_de(yo)
    contactos = [c for c in ag["contactos"] if c != yo][:60]
    perf = perfiles(contactos)
    sugeridos = sorted(((ag["apodos"].get(c) or (perf.get(c) or {}).get("nombre") or c.split("@")[0]), c) for c in contactos)
    sug = "".join(f"<button type='button' class='mj-per' data-ref='{e(ref_de(c))}' data-u='{uid_de(c)}' data-nombre='{e(n)}'>"
                  + _av_html(n, (perf.get(c) or {}).get("foto_url") or "") +
                  f"<span class='cuerpo'><b>{e(n)}</b><small>{e(_ocultar_correo(c))}</small></span><span class='sel'>＋</span></button>"
                  for n, c in sugeridos)
    cuerpo = (_CSS + "<div class='mj-panel'><div class='mj-top'><h1>Nuevo grupo</h1><div class='acc'><a class='btn sec' href='/mensajes'>‹ Mensajes</a></div></div>"
              "<div class='panel'><label style='font-weight:700;font-size:14px'>Nombre del grupo</label>"
              "<input id='mjGNom' maxlength='60' placeholder='Ej.: Pichanga de los jueves' style='margin-top:6px'>"
              "<div class='mj-sec'>Miembros <span id='mjGCnt'></span></div><div class='mj-elegidos' id='mjGEl'></div>"
              "<div class='mj-busca'><input id='mjQ' type='search' placeholder='Busca por nombre o correo para agregar' autocomplete='off' aria-label='Buscar miembros'></div>"
              "<div class='mj-res' id='mjRes'></div>"
              + (f"<div class='mj-sec'>Mis contactos</div><div class='mj-res' id='mjSug'>{sug}</div>" if sug else "")
              + "<div class='acciones' style='margin-top:16px'><button class='btn lg' id='mjGCrear' type='button'>Crear grupo</button></div></div></div>"
              + _JS_COMUN + _JS_BUSCAR.replace("__MODO__", "grupo") + _JS_GRUPO_NUEVO)
    return ui.shell("Nuevo grupo", cuerpo, sesion=ses, titulo_tab="Nuevo grupo · Pichangol", pantalla="mensajes")


_JS_GRUPO_NUEVO = r"""
<script>
(function(){
var el = {}, $ = function(i){ return document.getElementById(i); };
function pintar(){ var ks = Object.keys(el); $('mjGEl').innerHTML = ks.map(function(r){ return "<span class='mj-chip sel'>" + mjEsc(el[r].nombre) + " <button type='button' data-quitar='" + mjEsc(r) + "' style='border:0;background:transparent;cursor:pointer;font-size:15px' aria-label='Quitar'>✕</button></span>"; }).join('');
  $('mjGCnt').textContent = ks.length ? '· ' + ks.length : ''; $('mjGCrear').textContent = ks.length ? 'Crear grupo (' + ks.length + ')' : 'Crear grupo'; }
document.addEventListener('click', function(ev){ var b = ev.target.closest('[data-ref]'); if(b && b.tagName === 'BUTTON'){ var r = b.dataset.ref, u = b.dataset.u;
    var ya = Object.keys(el).some(function(k){ return el[k].u === u; });
    if(ya){ pcgToast('Ya está en el grupo.'); return; } el[r] = {nombre: b.dataset.nombre, u: u}; pintar(); pcgToast(b.dataset.nombre + ' agregado.'); return; }
  var q = ev.target.closest('[data-quitar]'); if(q){ delete el[q.dataset.quitar]; pintar(); } });
$('mjGCrear').onclick = function(){ var nom = $('mjGNom').value.trim();
  if(!nom){ pcgAvisar({titulo: 'Falta el nombre', icono: '✍️', mensaje: 'Ponle un nombre al grupo.'}); return; }
  if(!Object.keys(el).length){ pcgAvisar({titulo: 'Faltan miembros', icono: '👥', mensaje: 'Agrega al menos un miembro.'}); return; }
  pcgCargando('Creando grupo…');
  fetch('/web/mensajes/grupos', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({nombre: nom, miembros: Object.keys(el)})})
    .then(function(r){ return r.json(); }).then(function(j){ if(!j.ok){ pcgCargando(false); pcgAvisar({titulo: 'No se pudo', icono: '⚠️', mensaje: j.mensaje || 'Reintenta.'}); return; } pcgIr(j.url, 'Abriendo el grupo…'); })
    .catch(function(){ pcgCargando(false); pcgAvisar({titulo: 'Sin conexión', icono: '⚠️', mensaje: 'No se pudo crear el grupo. Revisa tu conexión.'}); }); };
pintar();
})();
</script>
"""


@router.get("/mensajes/grupo/{grupo_id}", response_class=HTMLResponse)
def pagina_info_grupo(request: Request, grupo_id: str):
    """`grupo_info_screen.dart`: foto, nombre, integrantes, añadir y salir."""
    ses = sesion.de_request(request)
    if not ses or not ses.get("email"):
        return sin_sesion(request, f"/mensajes/grupo/{grupo_id}", "Info del grupo", "Los grupos")
    yo = _low(ses["email"])
    g = grupo(grupo_id)
    if not g or yo not in g["miembros"]:
        cuerpo = ("<div class='panel' style='max-width:520px;margin:40px auto;text-align:center'><h1 style='font-size:22px'>Grupo no disponible</h1>"
                  "<p class='sub'>No existe o ya no eres parte de este grupo.</p><div class='acciones' style='justify-content:center'>"
                  "<a class='btn' href='/mensajes'>Ir a Mensajes</a></div></div>")
        return ui.shell("Info del grupo", cuerpo, sesion=ses, titulo_tab="Grupo · Pichangol", pantalla="mensajes")
    ag = agenda_de(yo)
    perf = perfiles(g["miembros"])
    miembros = []
    for em in g["miembros"]:
        p = perf.get(em) or {}
        nom = "Tú" if em == yo else (ag["apodos"].get(em) or p.get("nombre") or em.split("@")[0])
        miembros.append((em != yo, nom.lower(), f"<div class='mj-per'>{_av_html(nom, p.get('foto_url') or '')}<span class='cuerpo'><b>{e(nom)}</b>"
                         + ("<small>Creador del grupo</small>" if em == g["creador"] else "") + "</span></div>"))
    miembros.sort()
    candidatos = [c for c in ag["contactos"] if c not in g["miembros"]]
    perf_c = perfiles(candidatos)
    cand = "".join(f"<button type='button' class='mj-per' data-ref='{e(ref_de(c))}' data-nombre='{e(ag['apodos'].get(c) or (perf_c.get(c) or {}).get('nombre') or c.split('@')[0])}' data-foto=''>"
                   + _av_html(ag["apodos"].get(c) or (perf_c.get(c) or {}).get("nombre") or c, (perf_c.get(c) or {}).get("foto_url") or "")
                   + f"<span class='cuerpo'><b>{e(ag['apodos'].get(c) or (perf_c.get(c) or {}).get('nombre') or c.split('@')[0])}</b></span><span class='sel'>＋</span></button>"
                   for c in candidatos[:60])
    k = clave_de([hilo_grupo(g["id"])])
    cfg = {"g": g["id"], "subida": almacen.disponible(), "k": k}
    cuerpo = (_CSS + "<div class='mj-panel'><div class='mj-top'><h1>Info del grupo</h1><div class='acc'>"
              f"<a class='btn sec' href='/mensajes/{quote(k, safe='')}'>‹ Volver al chat</a></div></div>"
              "<div class='panel'><div class='mj-gfoto'>" + _av_html(g["nombre"], g["foto"]).replace("class='mj-av'", "class='mj-av' id='mjGFoto'")
              + "<button type='button' class='btn sec' id='mjGCam' style='padding:8px 14px;font-size:14px'>📷 Cambiar foto</button>"
              "<input type='file' id='mjGArch' accept='image/*' hidden></div>"
              f"<label style='font-weight:700;font-size:14px'>Nombre del grupo</label><div style='display:flex;gap:8px;margin-top:6px'>"
              f"<input id='mjGNom' maxlength='60' value='{e(g['nombre'])}'><button type='button' class='btn' id='mjGGuardar'>Guardar</button></div>"
              f"<div class='mj-sec'>{len(g['miembros'])} integrantes</div><div class='mj-res'>" + "".join(x for _, _, x in miembros) + "</div>"
              "<div class='mj-sec'>Añadir integrante</div>"
              "<div class='mj-busca'><input id='mjQ' type='search' placeholder='Busca por nombre o correo' autocomplete='off' aria-label='Buscar integrante'></div>"
              "<div class='mj-res' id='mjRes'></div>" + (f"<div class='mj-res'>{cand}</div>" if cand else "")
              + "<div class='acciones' style='margin-top:18px'><button type='button' class='btn sec' id='mjGLlamar' onclick='mjLlamadas()'>📹 Llamada grupal (en la app)</button>"
              "<button type='button' class='btn sec' id='mjGSalir' style='color:var(--rojo)'>🚪 Salir del grupo</button></div></div></div>"
              f"<script>window.MJG = {json.dumps(cfg)};</script>" + _JS_COMUN + _JS_BUSCAR.replace("__MODO__", "grupo") + _JS_GRUPO_INFO)
    return ui.shell("Info del grupo", cuerpo, sesion=ses, titulo_tab=f"{g['nombre'] or 'Grupo'} · Pichangol", pantalla="mensajes")


_JS_GRUPO_INFO = r"""
<script>
(function(){
var C = window.MJG, $ = function(i){ return document.getElementById(i); }, base = '/web/mensajes/grupos/' + encodeURIComponent(C.g);
function post(url, body, msg){ pcgCargando(msg || 'Guardando…', {demora: 250}); return fetch(url, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body || {})})
  .then(function(r){ return r.json(); }).then(function(j){ pcgCargando(false); if(!j.ok){ pcgAvisar({titulo: 'No se pudo', icono: '⚠️', mensaje: j.mensaje || 'Reintenta.'}); return null; } return j; })
  .catch(function(){ pcgCargando(false); pcgAvisar({titulo: 'Sin conexión', icono: '⚠️', mensaje: 'Revisa tu conexión y reintenta.'}); return null; }); }
$('mjGGuardar').onclick = function(){ var n = $('mjGNom').value.trim(); if(!n){ pcgAvisar({titulo: 'Falta el nombre', icono: '✍️', mensaje: 'Ponle un nombre al grupo.'}); return; }
  post(base + '/nombre', {nombre: n}).then(function(j){ if(j) pcgToast('Nombre actualizado.'); }); };
document.addEventListener('click', function(ev){ var b = ev.target.closest('button[data-ref]'); if(!b) return;
  pcgConfirmar({titulo: '¿Añadir a ' + b.dataset.nombre + '?', icono: '👥', mensaje: 'Podrá ver y escribir en el grupo.', confirmar: 'Añadir'}).then(function(ok){ if(!ok) return;
    post(base + '/miembros', {ref: b.dataset.ref}, 'Añadiendo…').then(function(j){ if(j) pcgRecargar('Actualizando…'); }); }); });
$('mjGSalir').onclick = function(){ pcgConfirmar({titulo: '¿Salir del grupo?', mensaje: 'Dejarás de recibir los mensajes de "' + $('mjGNom').value + '".', confirmar: 'Salir', destructivo: true, icono: '🚪'})
  .then(function(ok){ if(!ok) return; post(base + '/salir', {}, 'Saliendo…').then(function(j){ if(j) pcgIr('/mensajes'); }); }); };
function comprimir(file){ return new Promise(function(res, rej){ var img = new Image(), u = URL.createObjectURL(file);
  img.onload = function(){ var k = Math.min(1, 800 / Math.max(img.width, img.height)), cv = document.createElement('canvas'); cv.width = Math.round(img.width * k); cv.height = Math.round(img.height * k);
    cv.getContext('2d').drawImage(img, 0, 0, cv.width, cv.height); URL.revokeObjectURL(u); cv.toBlob(function(b){ b ? res(b) : rej(); }, 'image/jpeg', 0.82); };
  img.onerror = function(){ URL.revokeObjectURL(u); rej(); }; img.src = u; }); }
$('mjGCam').onclick = function(){ if(!C.subida){ pcgAvisar({titulo: 'Foto no disponible', icono: '📷', mensaje: 'La subida de fotos no está disponible en este momento. Cámbiala desde la app.'}); return; } $('mjGArch').click(); };
$('mjGArch').onchange = function(){ var f = this.files && this.files[0]; this.value = ''; if(!f) return; pcgCargando('Subiendo la foto…');
  comprimir(f).then(function(b){ return fetch(base + '/foto', {method: 'POST', headers: {'Content-Type': 'image/jpeg'}, body: b}); }).then(function(r){ return r.json(); })
    .then(function(j){ pcgCargando(false); if(!j.ok) return pcgAvisar({titulo: 'No se pudo', icono: '⚠️', mensaje: j.mensaje || 'Reintenta.'});
      var el = $('mjGFoto'), im = document.createElement('img'); im.id = 'mjGFoto'; im.className = 'mj-av'; im.alt = ''; im.src = j.foto; el.replaceWith(im); pcgToast('Foto actualizada.'); })
    .catch(function(){ pcgCargando(false); pcgAvisar({titulo: 'No se pudo', icono: '⚠️', mensaje: 'No se pudo subir la foto. Reintenta.'}); }); };
})();
</script>
"""


@router.get("/mensajes/{clave}", response_class=HTMLResponse)
def pagina_chat(request: Request, clave: str):
    """Chat = `chat_screen.dart` (en escritorio, con la bandeja a la izquierda)."""
    ses = sesion.de_request(request)
    if not ses or not ses.get("email"):
        return sin_sesion(request, f"/mensajes/{quote(clave, safe='')}", "Mensajes", "Tus conversaciones")
    yo = _low(ses["email"])
    conv = conversacion(clave, yo)
    if not conv:
        cuerpo = ("<div class='panel' style='max-width:520px;margin:40px auto;text-align:center'><h1 style='font-size:22px'>Chat no disponible</h1>"
                  "<p class='sub'>Este chat no existe o no eres parte de él.</p><div class='acciones' style='justify-content:center'>"
                  "<a class='btn' href='/mensajes'>Ir a Mensajes</a></div></div>")
        return ui.shell("Mensajes", cuerpo, sesion=ses, titulo_tab="Mensajes · Pichangol", pantalla="mensajes")
    hilos = conv["hilos"]
    k = clave_de(hilos)
    tit = _titulo_conv(conv, yo)
    mm = mensajes_de(hilos)
    marcar_leido(hilos, yo)
    b = bandeja(yo)
    fila = next((f for f in b["filas"] + b["archivadas"] if set(f["hilos"]) & set(hilos)), None)
    estado = {"fijado": bool(fila and fila.get("fijado")), "archivado": bool(fila and fila.get("archivado")),
              "silenciado": bool(fila and fila.get("silenciado"))}
    puede = not tit["bloqueado"]
    vacio = ("Escríbele tus dudas de horarios, precios o disponibilidad." if conv["principal"].get("negocio")
             else ("Saluda al grupo 👋" if tit["grupo"] else "Aún no hay mensajes. ¡Saluda!"))
    cfg = {"k": k, "titulo": tit["titulo"], "grupo": tit["grupo"], "mensajes": _msgs_para(mm, hilos, yo),
           "lecturas": _lecturas_para(hilos, yo, conv["principal"]["tipo"]), "hayMas": len(mm) >= LIMITE, "limite": LIMITE,
           "subida": almacen.disponible(), "max": TEXTO_MAX, "estado": estado, "puedeEscribir": puede, "vacio": vacio}
    comp = ("<div class='mj-comp'><div class='mj-cit' id='mjCit'><div id='mjCitT'></div><button type='button' id='mjCitX' aria-label='Quitar cita'>✕</button></div>"
            "<div class='mj-fila2'><button type='button' class='ib' id='mjClip' title='Enviar foto' aria-label='Enviar foto'>📷</button>"
            "<input type='file' id='mjArchivo' accept='image/*' hidden>"
            f"<textarea id='mjTexto' rows='1' maxlength='{TEXTO_MAX}' placeholder='Escribe un mensaje' aria-label='Mensaje'></textarea>"
            "<button type='button' class='ib env' id='mjEnv' aria-label='Enviar' disabled>➤</button></div></div>") if puede else (
            "<div class='mj-bloq'>Bloqueaste a este contacto. Para volver a escribirle, desbloquéalo desde la app.</div>")
    chat = ("<section class='mj-chat'>" + _cabecera_chat(conv, tit) + "<div class='mj-msgs' id='mjMsgs'></div>" + comp + "</section>")
    lista = ("<aside class='mj-lista' style='padding:12px'>" + _lista_html(b, activa=set(hilos)) + "</aside>")
    cfg_b = {"cache": _clave_cache(yo), "inicial": {"ok": True, "filas": [fila_json(f) for f in b["filas"]],
                                                     "archivadas": [fila_json(f) for f in b["archivadas"]]}, "fresca": True, "cada": 15000}
    cuerpo = (_CSS + "<div class='mj dos'>" + lista + chat + "</div>"
              + f"<script>window.MJ = {json.dumps(cfg_b, ensure_ascii=False)}; window.MJC = {json.dumps(cfg, ensure_ascii=False)}; "
              + f"window.MJ_ABIERTA = {json.dumps(fila_json(fila)['k'] if fila else '')};</script>"
              + _JS_COMUN + _JS_BANDEJA + _JS_CHAT)
    return ui.shell(tit["titulo"], cuerpo, sesion=ses, titulo_tab=f"{tit['titulo']} · Mensajes · Pichangol",
                    pantalla="chat")


# ═══════════════════════════ Endpoints JSON ══════════════════════════════════

@router.get("/web/mensajes/bandeja")
def api_bandeja(request: Request) -> JSONResponse:
    ses, err = _ses_o_401(request)
    if err:
        return err
    b = bandeja(ses["email"])
    return JSONResponse({"ok": True, "filas": [fila_json(f) for f in b["filas"]], "archivadas": [fila_json(f) for f in b["archivadas"]]},
                        headers={"Cache-Control": "no-store"})


@router.get("/web/mensajes/no-leidos")
def api_no_leidos(request: Request) -> JSONResponse:
    """Para el badge de "💬 Mensajes" (cabecera / Perfil)."""
    ses = sesion.de_request(request)
    if not ses or not ses.get("email"):
        return JSONResponse({"ok": True, "n": 0})
    return JSONResponse({"ok": True, "n": no_leidos_total(ses["email"])}, headers={"Cache-Control": "no-store"})


@router.get("/web/mensajes/hilo")
def api_hilo(request: Request, k: str = "", desde: str = "", antes: str = "", leer: int = 0) -> JSONResponse:
    """Sondeo del chat: solo lo posterior a `desde` (o la página anterior a
    `antes`) + las marcas de lectura de la otra persona."""
    ses, err = _ses_o_401(request)
    if err:
        return err
    yo = _low(ses["email"])
    conv = conversacion(k, yo)
    if not conv:
        return JSONResponse({"ok": False, "error": "sin_acceso", "mensaje": "Ya no eres parte de este chat."}, status_code=403)
    hilos = conv["hilos"]
    d_desde, d_antes = _dt(desde), _dt(antes)
    if d_antes:
        mm = mensajes_de(hilos, antes=d_antes)
    elif d_desde:
        mm = mensajes_de(hilos, desde=d_desde)
    else:
        mm = mensajes_de(hilos)
    if leer and not d_antes and any(_low(m.get("autor_email")) != yo and (not d_desde or (_dt(m.get("creado")) or d_desde) > d_desde)
                                    for m in mm):
        marcar_leido(hilos, yo)
    return JSONResponse({"ok": True, "mensajes": _msgs_para(mm, hilos, yo),
                         "lecturas": _lecturas_para(hilos, yo, conv["principal"]["tipo"])}, headers={"Cache-Control": "no-store"})


def _fila_nueva(conv: dict, yo: str, nombre: str, texto: str, media: str = "", resp: dict | None = None) -> dict:
    d = conv["principal"]
    fila = {"id": f"msg_{time.time_ns() // 1000}", "hilo": d["hilo"], "tipo": d["tipo"], "ref_id": d["ref_id"],
            "academia_id": d["academia_id"], "cuenta_email": d["cuenta_email"], "autor_email": yo, "autor_nombre": nombre,
            "es_profe": bool(d["es_profe"]), "texto": texto, "media_url": media}
    if resp:
        fila["resp_texto"] = snippet(resp.get("texto") or "", resp.get("media_url") or "")[:300]
        # Nombre real del autor citado (si es mío, el mío: la otra persona no debe leer "Tú").
        fila["resp_autor"] = nombre if _low(resp.get("autor_email")) == yo else (resp.get("autor_nombre") or "")
        fila["resp_media"] = resp.get("media_url") if clase_media(resp.get("media_url") or "") == "foto" else ""
    return fila


def _puede_escribir(conv: dict, yo: str) -> str:
    """'' si puede; si no, el motivo (contacto bloqueado en MI agenda)."""
    per = conv["principal"].get("persona") or ""
    if per and per in agenda_de(yo)["bloqueados"]:
        return "Bloqueaste a este contacto. Desbloquéalo desde la app para escribirle."
    return ""


@router.post("/web/mensajes/enviar")
def api_enviar(request: Request, body: dict = Body(default_factory=dict)) -> JSONResponse:
    """`_enviar` del chat: texto (+ cita) al hilo principal de la fila."""
    ses, err = _ses_o_401(request)
    if err:
        return err
    yo = _low(ses["email"])
    conv = conversacion(str(body.get("k") or ""), yo)
    if not conv:
        return JSONResponse({"ok": False, "error": "sin_acceso", "mensaje": "Ya no eres parte de este chat."}, status_code=403)
    texto = str(body.get("texto") or "").strip()
    if not texto:
        return JSONResponse({"ok": False, "mensaje": "Escribe un mensaje."}, status_code=400)
    if len(texto) > TEXTO_MAX:
        return JSONResponse({"ok": False, "mensaje": f"Máximo {TEXTO_MAX} caracteres."}, status_code=400)
    motivo = _puede_escribir(conv, yo)
    if motivo:
        return JSONResponse({"ok": False, "error": "bloqueado", "mensaje": motivo}, status_code=403)
    resp = None
    rid = str(body.get("resp") or "")
    if rid:
        r = mensaje(rid)
        if r and r.get("hilo") in conv["hilos"]:  # solo se cita lo de ESTA conversación
            resp = r
    fila = _fila_nueva(conv, yo, _mi_nombre(yo, ses), texto, resp=resp)
    guardado = insertar_mensaje(fila)
    if not guardado:
        return JSONResponse({"ok": False, "mensaje": "No se pudo enviar. Revisa tu conexión."}, status_code=503)
    marcar_leido(conv["hilos"], yo)
    return JSONResponse({"ok": True, "mensaje": _msgs_para([guardado], conv["hilos"], yo)[0]})


def _enviar_foto(ses: dict, k: str, datos_img: bytes) -> JSONResponse:
    yo = _low(ses["email"])
    conv = conversacion(k, yo)
    if not conv:
        return JSONResponse({"ok": False, "error": "sin_acceso", "mensaje": "Ya no eres parte de este chat."}, status_code=403)
    motivo = _puede_escribir(conv, yo)
    if motivo:
        return JSONResponse({"ok": False, "error": "bloqueado", "mensaje": motivo}, status_code=403)
    if not almacen.disponible():
        return JSONResponse({"ok": False, "mensaje": "El envío de fotos no está disponible en este momento."}, status_code=503)
    es_jpg, es_png = datos_img[:3] == b"\xff\xd8\xff", datos_img[:8] == b"\x89PNG\r\n\x1a\n"
    if not datos_img or len(datos_img) > FOTO_MAX or not (es_jpg or es_png):
        return JSONResponse({"ok": False, "mensaje": "Envía una foto JPG o PNG de hasta 6 MB."}, status_code=400)
    hilo = conv["principal"]["hilo"]
    ruta = f"{_carpeta_hilo(hilo)}/{time.time_ns() // 1000}.{'jpg' if es_jpg else 'png'}"
    url = almacen.subir("chat", ruta, datos_img, "image/jpeg" if es_jpg else "image/png", max_bytes=FOTO_MAX)
    if not url:
        return JSONResponse({"ok": False, "mensaje": "No se pudo subir la foto. Reintenta."}, status_code=502)
    fila = _fila_nueva(conv, yo, _mi_nombre(yo, ses), "📷 Foto", media=url.split("?", 1)[0])
    guardado = insertar_mensaje(fila)
    if not guardado:
        return JSONResponse({"ok": False, "mensaje": "No se pudo enviar. Revisa tu conexión."}, status_code=503)
    marcar_leido(conv["hilos"], yo)
    return JSONResponse({"ok": True, "mensaje": _msgs_para([guardado], conv["hilos"], yo)[0]})


@router.post("/web/mensajes/foto")
async def api_foto(request: Request, k: str = "") -> JSONResponse:
    """`_enviarBytes`: cuerpo crudo (el navegador la comprime a 1600 px)."""
    ses, err = _ses_o_401(request)
    if err:
        return err
    datos_img = await request.body()
    return await run_in_threadpool(_enviar_foto, ses, k, datos_img)


_ACCIONES = {"fijar", "desfijar", "archivar", "desarchivar", "silenciar", "activar", "eliminar"}


@router.post("/web/mensajes/accion")
def api_accion(request: Request, body: dict = Body(default_factory=dict)) -> JSONResponse:
    """Fijar / archivar / silenciar / eliminar sobre TODOS los hilos de la fila,
    con el estado COMPLETO por hilo en `pichangol_chat_prefs` (como
    `_subirPrefChat`). Archivar también desfija; eliminar = oculto desde ahora."""
    ses, err = _ses_o_401(request)
    if err:
        return err
    yo = _low(ses["email"])
    acc = str(body.get("accion") or "")
    if acc not in _ACCIONES:
        return JSONResponse({"ok": False, "mensaje": "Acción no válida."}, status_code=400)
    conv = conversacion(str(body.get("k") or ""), yo)
    if not conv:
        return JSONResponse({"ok": False, "error": "sin_acceso", "mensaje": "Ya no eres parte de este chat."}, status_code=403)
    actuales = prefs_de(yo)
    ahora = _ahora()
    filas = {}
    for h in conv["hilos"]:
        p = dict(actuales.get(h) or {"oculto_en": None, "fijado": False, "archivado": False, "silenciado": False})
        if acc == "fijar":
            p["fijado"] = True
        elif acc == "desfijar":
            p["fijado"] = False
        elif acc == "archivar":
            p["archivado"], p["fijado"] = True, False
        elif acc == "desarchivar":
            p["archivado"] = False
        elif acc == "silenciar":
            p["silenciado"] = True
        elif acc == "activar":
            p["silenciado"] = False
        else:
            p["oculto_en"] = ahora
        filas[h] = p
    if not guardar_prefs(yo, filas):
        return JSONResponse({"ok": False, "mensaje": "No se pudo guardar. Reintenta."}, status_code=503)
    return JSONResponse({"ok": True})


@router.get("/web/mensajes/buscar")
def api_buscar(request: Request, q: str = "") -> JSONResponse:
    """`PerfilesRepo.buscar`: refs opacos (nunca el correo en claro)."""
    ses, err = _ses_o_401(request)
    if err:
        return err
    yo = _low(ses["email"])
    ag = agenda_de(yo)
    out = [{"ref": ref_de(p["email"]), "u": uid_de(p["email"]), "nombre": ag["apodos"].get(p["email"]) or p["nombre"] or p["email"].split("@")[0],
            "foto": p["foto"], "sub": _ocultar_correo(p["email"])} for p in buscar_perfiles(q, yo)]
    return JSONResponse({"ok": True, "jugadores": out})


def _nombre_de(email: str) -> str:
    p = perfiles([email]).get(email) or {}
    return (p.get("nombre") or email.split("@")[0]).strip()


@router.post("/web/mensajes/grupos")
def api_crear_grupo(request: Request, body: dict = Body(default_factory=dict)) -> JSONResponse:
    """`CrearGrupoScreen._crear`: `grp_<µs>`, creador + miembros."""
    ses, err = _ses_o_401(request)
    if err:
        return err
    yo = _low(ses["email"])
    nombre = str(body.get("nombre") or "").strip()[:60]
    if not nombre:
        return JSONResponse({"ok": False, "mensaje": "Ponle un nombre al grupo."}, status_code=400)
    ems = []
    for r in (body.get("miembros") or [])[:MAX_MIEMBROS]:
        em = email_de_ref(str(r))
        if em and em != yo and em not in ems:
            ems.append(em)
    if not ems:
        return JSONResponse({"ok": False, "mensaje": "Agrega al menos un miembro."}, status_code=400)
    gid = f"grp_{time.time_ns() // 1000}"
    perf = perfiles(ems + [yo])
    miembros = [(yo, (perf.get(yo) or {}).get("nombre") or _mi_nombre(yo, ses))] + \
               [(em, (perf.get(em) or {}).get("nombre") or "") for em in ems]
    if not crear_grupo(gid, nombre, yo, miembros):
        return JSONResponse({"ok": False, "mensaje": "No se pudo crear el grupo. Revisa tu conexión."}, status_code=503)
    return JSONResponse({"ok": True, "url": f"/mensajes/{quote(clave_de([hilo_grupo(gid)]), safe='')}"})


def _grupo_mio(request: Request, gid: str):
    ses, err = _ses_o_401(request)
    if err:
        return None, None, err
    yo = _low(ses["email"])
    g = grupo(gid)
    if not g or yo not in g["miembros"]:
        return None, None, JSONResponse({"ok": False, "mensaje": "No eres parte de este grupo."}, status_code=404)
    return ses, g, None


@router.post("/web/mensajes/grupos/{gid}/nombre")
def api_grupo_nombre(request: Request, gid: str, body: dict = Body(default_factory=dict)) -> JSONResponse:
    ses, g, err = _grupo_mio(request, gid)
    if err:
        return err
    nombre = str(body.get("nombre") or "").strip()[:60]
    if not nombre:
        return JSONResponse({"ok": False, "mensaje": "Ponle un nombre al grupo."}, status_code=400)
    if not actualizar_grupo(gid, nombre=nombre):
        return JSONResponse({"ok": False, "mensaje": "No se pudo guardar. Reintenta."}, status_code=503)
    return JSONResponse({"ok": True})


@router.post("/web/mensajes/grupos/{gid}/miembros")
def api_grupo_miembro(request: Request, gid: str, body: dict = Body(default_factory=dict)) -> JSONResponse:
    """`_anadirIntegrante` (`GruposRepo.agregarMiembro`)."""
    ses, g, err = _grupo_mio(request, gid)
    if err:
        return err
    em = email_de_ref(str(body.get("ref") or ""))
    if not em:
        return JSONResponse({"ok": False, "mensaje": "Vuelve a buscar a la persona."}, status_code=400)
    if em in g["miembros"]:
        return JSONResponse({"ok": True, "ya": True})
    if len(g["miembros"]) >= MAX_MIEMBROS:
        return JSONResponse({"ok": False, "mensaje": "El grupo está lleno."}, status_code=400)
    if not agregar_miembro(gid, em, _nombre_de(em)):
        return JSONResponse({"ok": False, "mensaje": "No se pudo añadir al integrante."}, status_code=503)
    return JSONResponse({"ok": True})


@router.post("/web/mensajes/grupos/{gid}/salir")
def api_grupo_salir(request: Request, gid: str) -> JSONResponse:
    ses, g, err = _grupo_mio(request, gid)
    if err:
        return err
    if not salir_grupo(gid, ses["email"]):
        return JSONResponse({"ok": False, "mensaje": "No se pudo salir del grupo."}, status_code=503)
    return JSONResponse({"ok": True})


def _foto_grupo(request: Request, gid: str, datos_img: bytes) -> JSONResponse:
    ses, g, err = _grupo_mio(request, gid)
    if err:
        return err
    if not almacen.disponible():
        return JSONResponse({"ok": False, "mensaje": "La subida de fotos no está disponible en este momento."}, status_code=503)
    if not datos_img or len(datos_img) > FOTO_MAX or datos_img[:3] != b"\xff\xd8\xff":
        return JSONResponse({"ok": False, "mensaje": "Sube una foto JPG de hasta 6 MB."}, status_code=400)
    url = almacen.subir("grupos", f"{gid}.jpg", datos_img, "image/jpeg", max_bytes=FOTO_MAX)
    if not url:
        return JSONResponse({"ok": False, "mensaje": "No se pudo subir la foto. Reintenta."}, status_code=502)
    url = f"{url.split('?', 1)[0]}?v={int(time.time() * 1000)}"  # `GruposRepo.subirFoto` (rompe la caché)
    if not actualizar_grupo(gid, foto=url):
        return JSONResponse({"ok": False, "mensaje": "No se pudo guardar la foto."}, status_code=503)
    return JSONResponse({"ok": True, "foto": url})


@router.post("/web/mensajes/grupos/{gid}/foto")
async def api_grupo_foto(request: Request, gid: str) -> JSONResponse:
    datos_img = await request.body()
    return await run_in_threadpool(_foto_grupo, request, gid, datos_img)


# Para el coordinador: badge de no leídos en la cabecera / Perfil. Pinta al
# instante con el último valor (localStorage) y lo refresca en segundo plano.
JS_BADGE_MENSAJES = r"""
<script>
(function(){ var els = document.querySelectorAll('[data-badge-mensajes]'); if(!els.length) return;
  function pon(n){ els.forEach(function(el){ el.textContent = n > 99 ? '99+' : String(n); el.hidden = !n; }); }
  try { pon(parseInt(localStorage.getItem('pcg_msj_nl') || '0', 10) || 0); } catch(e){}
  fetch('/web/mensajes/no-leidos').then(function(r){ return r.json(); }).then(function(j){ if(!j.ok) return; pon(j.n); try { localStorage.setItem('pcg_msj_nl', String(j.n)); } catch(e){} }).catch(function(){});
})();
</script>
"""

