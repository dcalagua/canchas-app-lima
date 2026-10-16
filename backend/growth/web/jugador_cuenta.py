"""CONFIGURACIÓN DE LA CUENTA + VERIFICAR IDENTIDAD en la web (pedido del
director, 29-sep-2026: "en la web implementa las mismas funcionalidades que
existen actualmente en el app").

- `GET /cuenta/configuracion` = `editar_perfil_screen.dart` + la parte de
  cuenta de `ajustes_screen.dart`: foto (bucket `chat`, carpeta
  `perfiles/<correo_saneado>/<µs>.jpg` como `PerfilesRepo.subirFoto`, borrando
  la anterior), nombre visible y celular con prefijo y largo por país (se
  guarda en formato internacional como el app), la BIO por SELECCIÓN (mismos 8
  prompts y opciones que `_kPromptsBio`, jsonb `bio`) y "Mis deportes" (niveles
  → `/mi-nivel`). Todo en `pichangol_perfiles` (UPSERT por email). Al guardar
  se re-emite la cookie de sesión con el nombre/foto nuevos (cabecera al día).
- `GET /cuenta/identidad` = `verificar_identidad_screen.dart`: Perú (DNI,
  RENIEC vía Factiliza) y Ecuador (cédula, CipherByte) por número, llamando
  como función a `propiedad.router.post_verificar_dni` (regla anti-fraude
  "1 documento = 1 cuenta" incluida) y escribiendo `pichangol_verificaciones`
  (email, nombre, estado 'verificado') como `VerificacionRepo.
  registrarVerificado`. El número NUNCA se guarda ni se devuelve (Ley 29733);
  la edad se muestra una vez y no se persiste (el app la guarda solo en el
  teléfono). Bolivia (CI) se verifica en la app: su camino es OCR EN EL
  TELÉFONO (ML Kit) + selfie, que la web no puede replicar sin bajar la
  barrera anti-fraude.
"""

from __future__ import annotations

import json
import re
import threading
import time
import urllib.parse
import urllib.request
from datetime import date, datetime

from fastapi import APIRouter, Body, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, JSONResponse

import config
from db import pg
from web import almacen, catalogos, datos, sesion, ui
from web.jugador_liga import (PLAY_URL, _CSS_BASE, _CSS_NIVEL, chip_nivel,
                              niveles_completos, sin_sesion)
from web.ui import e

router = APIRouter()

# `_kPromptsBio` de editar_perfil_screen.dart: (clave, emoji, etiqueta, opciones, multi).
PROMPTS_BIO = [
    ("dedico", "💼", "Me dedico a", ["Estudiante", "Ingeniería", "Salud", "Docencia", "Comercio", "Emprendimiento",
                                   "Administración", "Tecnología", "Derecho", "Construcción", "Transporte", "Deporte",
                                   "Hogar", "Jubilado/a"], False),
    ("juego_desde", "🕰️", "Juego desde hace", ["Menos de 1 año", "1–3 años", "3–5 años", "5–10 años", "Más de 10 años",
                                               "Toda la vida"], False),
    ("logro", "🏆", "Mi mayor logro deportivo", ["Campeón de barrio", "Campeón distrital", "Campeón de academia",
                                                 "Campeón interescolar", "Jugué federado", "Medalla escolar",
                                                 "Aún lo estoy buscando", "Jugar por diversión"], False),
    ("estilo", "⚽", "Mi estilo de juego", ["Ofensivo", "Defensivo", "Estratega", "Velocidad pura", "Garra y corazón",
                                          "Fair play primero", "El del gol agónico", "Zurdo/a de oro"], False),
    ("tiempo", "⏰", "Dedico demasiado tiempo a", ["Entrenar", "Ver deporte", "La familia", "El trabajo", "Videojuegos",
                                                  "Series", "Música", "Salir con amigos"], False),
    ("musica", "🎵", "Mi música para entrar en calor", ["Salsa", "Reggaetón", "Rock", "Cumbia", "Electrónica", "Huayno",
                                                       "Pop", "Trap", "Criolla"], False),
    ("horario", "🌅", "Mi horario de juego", ["Mañanero", "Al mediodía", "Por la tarde", "Nocturno", "Fines de semana",
                                             "Cuando se pueda"], False),
    ("idiomas", "🗣️", "Idiomas que hablo", ["Español", "Inglés", "Portugués", "Quechua", "Aimara", "Otro"], True),
]
PAISES = [("PE", "Perú"), ("BO", "Bolivia"), ("EC", "Ecuador")]
DOC = {"PE": ("DNI", 8, "RENIEC"), "EC": ("Cédula", 10, "el Registro Civil"), "BO": ("CI", None, "")}
_FOTO_MAX = 4 * 1024 * 1024


def _carpeta(email: str) -> str:
    """`PerfilesRepo`: 'perfiles/' + correo con todo lo no alfanumérico → '_'."""
    return "perfiles/" + re.sub(r"[^a-zA-Z0-9_-]", "_", email.strip().lower())


# ── Datos (pichangol_perfiles / pichangol_verificaciones) ─────────────────────

def perfil_completo(email: str) -> dict:
    em = (email or "").strip().lower()
    if not pg.habilitado or not em:
        return {}
    for cols in ("nombre, foto_url, celular, bio", "nombre, foto_url, celular"):
        try:
            with pg.conexion() as conn, conn.cursor() as cur:
                cur.execute(f"SELECT {cols} FROM pichangol_perfiles WHERE lower(email) = %s LIMIT 1", (em,))
                f = cur.fetchone()
                if not f:
                    return {}
                bio = f[3] if len(f) > 3 else {}
                if isinstance(bio, str):
                    try:
                        bio = json.loads(bio)
                    except ValueError:
                        bio = {}
                return {"nombre": str(f[0] or ""), "foto_url": str(f[1] or ""), "celular": str(f[2] or ""),
                        "bio": {str(k): str(v) for k, v in (bio or {}).items()} if isinstance(bio, dict) else {}}
        except Exception:  # noqa: BLE001
            continue
    return {}


def guardar_perfil(email: str, nombre: str, celular: str, bio: dict) -> bool:
    """`PerfilesRepo.guardar(email, nombre, celular, bio)`: UPSERT que NO toca
    la foto. Si la columna `bio` aún no existe, guarda el perfil base."""
    em = (email or "").strip().lower()
    if not pg.habilitado or not em:
        return False
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO pichangol_perfiles (email, nombre, celular, bio, actualizado) VALUES (%s, %s, %s, %s::jsonb, now()) "
                        "ON CONFLICT (email) DO UPDATE SET nombre = EXCLUDED.nombre, celular = EXCLUDED.celular, "
                        "bio = EXCLUDED.bio, actualizado = now()", (em, nombre, celular, json.dumps(bio, ensure_ascii=False)))
            conn.commit()
            return True
    except Exception:  # noqa: BLE001
        pass
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO pichangol_perfiles (email, nombre, celular, actualizado) VALUES (%s, %s, %s, now()) "
                        "ON CONFLICT (email) DO UPDATE SET nombre = EXCLUDED.nombre, celular = EXCLUDED.celular, actualizado = now()",
                        (em, nombre, celular))
            conn.commit()
            return True
    except Exception:  # noqa: BLE001
        return False


def guardar_foto(email: str, nombre: str, url: str) -> bool:
    em = (email or "").strip().lower()
    if not pg.habilitado or not em:
        return False
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO pichangol_perfiles (email, nombre, foto_url, actualizado) VALUES (%s, %s, %s, now()) "
                        "ON CONFLICT (email) DO UPDATE SET foto_url = EXCLUDED.foto_url, actualizado = now()",
                        (em, nombre, url))
            conn.commit()
            return True
    except Exception:  # noqa: BLE001
        return False


def registrar_verificado(email: str, nombre: str) -> bool:
    """`VerificacionRepo.registrarVerificado`: fila (email, nombre, 'verificado'), sin imágenes."""
    em = (email or "").strip().lower()
    if not pg.habilitado or not em:
        return False
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO pichangol_verificaciones (email, nombre, estado) VALUES (%s, %s, 'verificado') "
                        "ON CONFLICT (email) DO UPDATE SET nombre = EXCLUDED.nombre, estado = 'verificado'", (em, nombre))
            conn.commit()
            return True
    except Exception:  # noqa: BLE001
        return False


def _borrar_foto_vieja(email: str, url: str) -> None:
    """Borra el avatar anterior SOLO si vive en la carpeta de este usuario (como
    `StorageLimpieza.borrarCarpeta('chat', carpeta, excepto: path)`)."""
    if not url or not almacen.disponible():
        return
    raiz = f"{config.SUPABASE_URL.rstrip('/')}/storage/v1/object/public/chat/"
    ruta = urllib.parse.unquote(url.split("?", 1)[0][len(raiz):]) if url.startswith(raiz) else ""
    if not ruta.startswith(_carpeta(email) + "/") or ".." in ruta:
        return
    q = "/".join(urllib.parse.quote(p, safe="") for p in ruta.split("/"))
    req = urllib.request.Request(f"{config.SUPABASE_URL.rstrip('/')}/storage/v1/object/chat/{q}", method="DELETE",
                                 headers={"apikey": config.SUPABASE_ANON_KEY, "Authorization": f"Bearer {config.SUPABASE_ANON_KEY}"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:  # noqa: S310
            r.read()
    except Exception:  # noqa: BLE001
        pass


# ── Celular por país (como la web de reserva / `PaisConfig`) ──────────────────

def partir_celular(cel: str) -> tuple[str, str]:
    """"51987654321" → ("PE", "987654321"). Sin prefijo reconocible → PE + dígitos."""
    d = re.sub(r"\D", "", cel or "")
    for iso, _ in PAISES:
        cc = catalogos.TEL_PREFIJO[iso]
        if d.startswith(cc) and len(d) > catalogos.TEL_LONGITUD[iso]:
            return iso, d[len(cc):]
    return "PE", d


def _validar_celular(pais: str, local: str) -> tuple[str, str]:
    """→ (celular internacional o '', error)."""
    d = re.sub(r"\D", "", local or "")
    if not d:
        return "", ""
    if pais not in catalogos.TEL_PREFIJO:
        return "", "Elige el país de tu celular."
    largo = catalogos.TEL_LONGITUD[pais]
    if len(d) != largo:
        return "", f"El celular de {dict(PAISES)[pais]} tiene {largo} dígitos."
    if pais == "PE" and not d.startswith("9"):
        return "", "El celular peruano empieza con 9."
    if pais == "BO" and d[0] not in "67":
        return "", "El celular boliviano empieza con 6 o 7."
    return catalogos.TEL_PREFIJO[pais] + d, ""


def _validar_bio(bio) -> dict:
    """Solo claves y opciones del catálogo (nada de texto libre), en el orden del catálogo."""
    out: dict[str, str] = {}
    if not isinstance(bio, dict):
        return out
    for clave, _, _, opciones, multi in PROMPTS_BIO:
        v = bio.get(clave)
        elegidas = [x.strip() for x in (v if isinstance(v, list) else str(v or "").split(" · ")) if str(x).strip()]
        validas = [o for o in opciones if o in elegidas]
        if not multi:
            validas = validas[:1]
        if validas:
            out[clave] = " · ".join(validas)
    return out


def _cookie_actualizada(resp: JSONResponse, ses: dict, nombre: str | None = None, foto: str | None = None) -> None:
    sesion.poner_cookie(resp, sesion.emitir({"email": ses["email"], "nombre": nombre if nombre is not None else ses.get("nombre"),
                                             "foto": foto if foto is not None else ses.get("foto")}))


# ═════════════════════════════ Configuración ═════════════════════════════════

_CSS_CUENTA = """
.cf-av{position:relative;width:152px;height:152px;margin:8px auto 30px}
.cf-av img,.cf-av .ini{width:152px;height:152px;border-radius:50%;object-fit:cover;display:flex;align-items:center;justify-content:center;background:#EAF7EF;color:#067A38;font-size:60px;font-weight:800}
.cf-av .ed{position:absolute;left:50%;transform:translateX(-50%);bottom:-14px;background:#fff;border:0;border-radius:99px;box-shadow:0 3px 10px rgba(0,0,0,.18);padding:9px 16px;font:inherit;font-weight:800;cursor:pointer;white-space:nowrap}
.cf-lbl{display:block;font-size:12.5px;font-weight:700;color:#6a6a6a;margin:14px 0 6px}
.cf-cel{display:flex;gap:8px;align-items:center}
.cf-cel .pre{flex:none;font-weight:700;background:#F4F7FA;border-radius:12px;padding:12px 12px}
.cf-cel input{flex:1;min-width:0}
.cf-err{color:#C0392B;font-size:13px;font-weight:600;margin-top:6px;min-height:0}
.cf-bio{display:flex;flex-direction:column}
.cf-bio button{display:flex;align-items:center;gap:14px;padding:15px 2px;border:0;border-bottom:1px solid #EBEBEB;background:none;font:inherit;text-align:left;cursor:pointer;width:100%;color:inherit}
.cf-bio button .em{font-size:22px;width:28px;text-align:center;flex:none}
.cf-bio button .tx{flex:1;min-width:0;overflow-wrap:anywhere}
.cf-bio button .tx.nada{color:#6a6a6a}
.cf-bio button .chev{color:#b0b0b0;font-size:20px}
.cf-niv{display:flex;flex-wrap:wrap;gap:8px;margin:8px 0}
.cf-barra{position:sticky;bottom:0;background:#fff;border-top:1px solid #EBEBEB;padding:12px 0 calc(12px + env(safe-area-inset-bottom));margin-top:18px;display:flex;justify-content:flex-end;z-index:5}
.cf-barra .btn{margin:0;background:#222;min-width:140px}
.cf-it{display:flex;align-items:center;gap:14px;padding:15px 2px;border-bottom:1px solid #EBEBEB;color:inherit;text-decoration:none;background:none;border-left:0;border-right:0;border-top:0;font:inherit;width:100%;text-align:left;cursor:pointer}
.cf-it .em{font-size:22px;width:28px;text-align:center;flex:none}
.cf-it .tx{flex:1;min-width:0}
.cf-it small{display:block;color:#6a6a6a;font-size:13px;margin-top:2px}
.cf-it .app{font-size:11.5px;font-weight:700;color:#067A38;background:#E9F6EE;border-radius:99px;padding:3px 9px;white-space:nowrap}
.cf-it .chev{color:#b0b0b0;font-size:20px}
.cf-it.rojo{color:#C0392B}
.pcg-dlg .caja .cf-op{display:flex;flex-wrap:wrap;gap:8px;text-align:left}
.pcg-dlg .caja .cf-op .chip{white-space:normal}
.id-caja{background:#fff;border:1px solid #EBEBEB;border-radius:16px;padding:16px;margin:14px 0}
.id-caja input{font-size:18px;letter-spacing:1px}
.id-ok{text-align:center;padding:24px 10px}
.id-ok .em{font-size:56px;display:block}
.id-nota{display:flex;gap:10px;background:#F4F7FA;border-radius:14px;padding:12px 14px;font-size:13px;color:#444;line-height:1.4;margin-top:12px}
"""


@router.get("/cuenta/configuracion", response_class=HTMLResponse)
def pagina_configuracion(request: Request) -> HTMLResponse:
    ses = sesion.de_request(request)
    if not ses:
        return sin_sesion(request, "/cuenta/configuracion", "Configuración de la cuenta", "La configuración de tu cuenta")
    email = ses["email"].lower()
    p = perfil_completo(email)
    nombre = p.get("nombre") or ses.get("nombre") or ""
    foto = p.get("foto_url") or ses.get("foto") or ""
    pais, local = partir_celular(p.get("celular") or "")
    bio = p.get("bio") or {}
    niveles = niveles_completos(email)
    verificado = datos.esta_verificado(email)

    av = (f"<img id='cfFoto' src='{e(foto)}' alt='' referrerpolicy='no-referrer'>" if foto
          else f"<span class='ini' id='cfFoto'>{e((nombre or email)[:1].upper())}</span>")
    paises = "".join(f"<button type='button' class='chip{' sel' if iso == pais else ''}' data-pais='{iso}'>{ui.bandera(iso)} {e(n)}</button>"
                     for iso, n in PAISES)
    filas_bio = "".join(
        f"<button type='button' data-clave='{c}'><span class='em'>{em}</span>"
        f"<span class='tx{'' if bio.get(c) else ' nada'}'>{e(et + ': ' + bio[c]) if bio.get(c) else e(et)}</span><span class='chev'>›</span></button>"
        for c, em, et, _, _ in PROMPTS_BIO)
    nivs = ("<div class='cf-niv'>" + "".join(chip_nivel(n["deporte"], n["nivel"]) for n in niveles) + "</div>" if niveles
            else "<p class='sub' style='margin:4px 0 8px'>Aún no te autoevaluaste. Así te emparejamos con rivales de tu nivel.</p>")
    cuenta = (
        f"<a class='cf-it' href='/cuenta/identidad'><span class='em'>{'✅' if verificado else '🪪'}</span><span class='tx'>"
        f"{'Identidad verificada ✓' if verificado else 'Verifica tu identidad'}<small>"
        f"{'Tu perfil muestra la insignia de jugador verificado' if verificado else 'Da confianza a los dueños y reserva sin fricción'}</small></span><span class='chev'>›</span></a>"
        "<button type='button' class='cf-it' data-app='La última vez, en línea y las confirmaciones de lectura del chat se configuran en tu teléfono, desde la app.' data-titulo='Privacidad' data-em='🔒'>"
        "<span class='em'>🔒</span><span class='tx'>Privacidad<small>Última vez, en línea y confirmaciones de lectura</small></span><span class='app'>En la app</span><span class='chev'>›</span></button>"
        "<button type='button' class='cf-it' data-app='Tu código de invitado y los bonos por referir amigos están en la app.' data-titulo='Invita y gana' data-em='🎁'>"
        "<span class='em'>🎁</span><span class='tx'>Invita y gana<small>Comparte tu código; tú y tu amigo ganan un bono</small></span><span class='app'>En la app</span><span class='chev'>›</span></button>"
        "<button type='button' class='cf-it' onclick='window.pcgSalir&&pcgSalir()'><span class='em'>🚪</span><span class='tx'>Cierra la sesión</span><span class='chev'>›</span></button>"
        "<a class='cf-it rojo' href='/legal/eliminar-cuenta'><span class='em'>🗑️</span><span class='tx'>Eliminar mi cuenta</span><span class='chev'>›</span></a>")
    cfg = {"bio": bio, "prompts": [[c, em, et, ops, mu] for c, em, et, ops, mu in PROMPTS_BIO],
           "pref": catalogos.TEL_PREFIJO, "largo": catalogos.TEL_LONGITUD, "pais": pais,
           "subida": almacen.disponible(), "play": PLAY_URL}
    cuerpo = (
        f"<style>{_CSS_BASE}{_CSS_NIVEL}{_CSS_CUENTA}</style><div class='lg-wrap' style='max-width:560px'>"
        "<a class='sub' href='/perfil' style='text-decoration:none'>‹ Perfil</a>"
        "<h1>Edita el perfil</h1>"
        f"<div class='cf-av'>{av}<button type='button' class='ed' id='cfEd'>📷 Editar</button>"
        "<input type='file' id='cfArchivo' accept='image/*' hidden></div>"
        "<div style='font-size:26px;font-weight:800;letter-spacing:-.4px'>Mi perfil</div>"
        "<p class='sub' style='margin:6px 0 4px'>Los jugadores y dueños pueden ver tu perfil en el chat, los retos y el ranking. Completarlo genera confianza en la comunidad.</p>"
        "<label class='cf-lbl' for='cfNombre'>Tu nombre</label>"
        f"<input id='cfNombre' maxlength='80' autocomplete='name' value='{e(nombre)}'>"
        "<label class='cf-lbl'>Celular (opcional)</label>"
        f"<div class='lg-chips' id='cfPais'>{paises}</div>"
        f"<div class='cf-cel'><span class='pre' id='cfPre'>+{catalogos.TEL_PREFIJO[pais]}</span>"
        f"<input id='cfCel' inputmode='numeric' autocomplete='tel-national' maxlength='{catalogos.TEL_LONGITUD[pais]}' value='{e(local)}' "
        f"placeholder='{catalogos.TEL_LONGITUD[pais]} dígitos' aria-label='Celular'></div><div class='cf-err' id='cfErr'></div>"
        f"<div class='cf-bio' style='margin-top:10px'>{filas_bio}</div>"
        "<div class='lg-sec' style='margin-top:24px'>Mis deportes</div>" + nivs +
        "<a class='btn sec' href='/mi-nivel' style='margin:0'>✏️ Edita tus deportes</a>"
        "<div class='cf-barra'><button type='button' class='btn' id='cfListo'>Listo</button></div>"
        "<div class='lg-sec' style='margin-top:30px'>Tu cuenta</div>" + cuenta + "</div>"
        "<script>window.CF=" + json.dumps(cfg, ensure_ascii=False).replace("</", "<\\/") + ";</script><script>" + _JS_CONFIG + "</script>")
    return ui.shell("Configuración de la cuenta", cuerpo, sesion=ses, titulo_tab="Configuración · Pichangol")


@router.post("/web/cuenta/perfil")
def guardar_mi_perfil(request: Request, body: dict = Body(default_factory=dict)) -> JSONResponse:
    """`actualizarMiNombre(nombre, celular)` + `PerfilesRepo.guardar(bio:)`."""
    ses = sesion.de_request(request)
    if not ses:
        return JSONResponse({"ok": False, "mensaje": "Inicia sesión."}, status_code=401)
    nombre = re.sub(r"\s+", " ", str(body.get("nombre") or "")).strip()
    if not nombre:
        return JSONResponse({"ok": False, "campo": "nombre", "mensaje": "Escribe tu nombre."}, status_code=400)
    if len(nombre) > 80 or re.search(r"[<>{}\\]", nombre):
        return JSONResponse({"ok": False, "campo": "nombre", "mensaje": "Ese nombre no es válido."}, status_code=400)
    celular, err = _validar_celular(str(body.get("pais") or "PE"), str(body.get("celular") or ""))
    if err:
        return JSONResponse({"ok": False, "campo": "celular", "mensaje": err}, status_code=400)
    bio = _validar_bio(body.get("bio"))
    if not guardar_perfil(ses["email"], nombre, celular, bio):
        return JSONResponse({"ok": False, "mensaje": "No se pudo guardar. Reintenta."}, status_code=503)
    resp = JSONResponse({"ok": True, "mensaje": "Listo. Así te verán en el chat y el ranking."})
    _cookie_actualizada(resp, ses, nombre=nombre)
    return resp


def _subir_foto(ses: dict, datos_img: bytes) -> JSONResponse:
    if not almacen.disponible():
        return JSONResponse({"ok": False, "mensaje": "La subida de fotos no está disponible en este momento."}, status_code=503)
    if not datos_img or len(datos_img) > _FOTO_MAX or not (datos_img[:3] == b"\xff\xd8\xff" or datos_img[:8] == b"\x89PNG\r\n\x1a\n"):
        return JSONResponse({"ok": False, "mensaje": "Sube una foto JPG o PNG de hasta 4 MB."}, status_code=400)
    email = ses["email"].lower()
    ruta = f"{_carpeta(email)}/{time.time_ns() // 1000}.jpg"
    url = almacen.subir("chat", ruta, datos_img, "image/jpeg" if datos_img[:3] == b"\xff\xd8\xff" else "image/png")
    if not url:
        return JSONResponse({"ok": False, "mensaje": "No se pudo subir la foto. Reintenta."}, status_code=502)
    url = url.split("?", 1)[0]  # la URL pública limpia, como `getPublicUrl` del app
    antes = perfil_completo(email)
    previa = antes.get("foto_url") or ""
    nombre = antes.get("nombre") or ses.get("nombre") or email.split("@")[0]
    if not guardar_foto(email, nombre, url):
        return JSONResponse({"ok": False, "mensaje": "No se pudo guardar la foto. Reintenta."}, status_code=503)
    if previa and previa != url:
        _borrar_foto_vieja(email, previa)
    resp = JSONResponse({"ok": True, "foto": url})
    _cookie_actualizada(resp, ses, foto=url)
    return resp


@router.post("/web/cuenta/foto")
async def subir_mi_foto(request: Request) -> JSONResponse:
    """`actualizarMiFoto`: cuerpo crudo (el navegador la comprime a 800 px)."""
    ses = sesion.de_request(request)
    if not ses:
        return JSONResponse({"ok": False, "mensaje": "Inicia sesión."}, status_code=401)
    datos_img = await request.body()
    return await run_in_threadpool(_subir_foto, ses, datos_img)


# ═══════════════════════════ Verificar identidad ═════════════════════════════

_INTENTOS: dict[str, list[float]] = {}
_INTENTOS_LOCK = threading.Lock()
_MAX_INTENTOS, _VENTANA_S = 5, 15 * 60


def _puede_intentar(email: str) -> bool:
    """Tope anti abuso: 5 consultas al registro por cuenta cada 15 min (cada
    consulta a Factiliza cuesta y probar números al azar es fraude)."""
    ahora = time.time()
    with _INTENTOS_LOCK:
        l = [t for t in _INTENTOS.get(email, []) if ahora - t < _VENTANA_S]
        if len(l) >= _MAX_INTENTOS:
            _INTENTOS[email] = l
            return False
        l.append(ahora)
        _INTENTOS[email] = l
        return True


def edad_desde(raw: str | None) -> int | None:
    """`_parseNacimiento` + `edadDesdeFecha` del app (dd/mm/aaaa o aaaa-mm-dd)."""
    s = (raw or "").strip()
    f = None
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", s)
    try:
        if m:
            f = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        else:
            m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", s)
            if m:
                f = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None
    if not f:
        return None
    hoy = datetime.now().date()
    edad = hoy.year - f.year - ((hoy.month, hoy.day) < (f.month, f.day))
    return edad if 0 <= edad < 130 else None


@router.get("/cuenta/identidad", response_class=HTMLResponse)
def pagina_identidad(request: Request, pais: str = "") -> HTMLResponse:
    ses = sesion.de_request(request)
    if not ses:
        return sin_sesion(request, "/cuenta/identidad", "Verificar identidad", "La verificación de identidad")
    email = ses["email"].lower()
    head = f"<style>{_CSS_BASE}{_CSS_CUENTA}</style><div class='lg-wrap' style='max-width:560px'><a class='sub' href='/cuenta/configuracion' style='text-decoration:none'>‹ Configuración</a><h1>Verificar identidad</h1>"
    if datos.esta_verificado(email):
        cuerpo = head + ("<div class='lg-card id-ok'><span class='em'>✅</span><div style='font-size:19px;font-weight:800;margin-top:8px'>Identidad verificada</div>"
                         "<p class='sub'>Tu perfil muestra la insignia de jugador verificado. Los dueños de cancha confían más en jugadores verificados.</p>"
                         "<a class='btn' href='/perfil'>Volver a mi perfil</a></div></div>")
        return ui.shell("Verificar identidad", cuerpo, sesion=ses, titulo_tab="Verificar identidad · Pichangol")
    iso = pais.upper() if pais.upper() in DOC else partir_celular(perfil_completo(email).get("celular") or "")[0]
    chips = "".join(f"<a class='chip{' sel' if i == iso else ''}' href='/cuenta/identidad?pais={i}'>{e(n)}</a>" for i, n in PAISES)
    doc, largo, registro = DOC[iso]
    if iso == "BO":
        panel = ("<div class='lg-card'><div style='font-weight:800;font-size:18px'>Jugador verificado</div>"
                 f"<p class='sub'>En Bolivia validamos tu {doc} en tu propio teléfono: la app lee el documento con la cámara (no se envía a ningún lado para leerlo) y suma una selfie. "
                 "Ese paso no se puede hacer desde el navegador sin bajar la seguridad, así que se hace en la app.</p>"
                 "<button type='button' class='btn lg' id='idApp'>📱 Verificar en la app</button></div>")
    else:
        panel = ("<div class='lg-card'><div style='font-weight:800;font-size:18px'>Jugador verificado</div>"
                 f"<p class='sub'>Validamos tu {doc} contra {registro}. Es rápido y da confianza a los dueños de cancha para reservar sin fricción.</p>"
                 f"<div class='id-caja'><label class='cf-lbl' for='idNum' style='margin-top:0'>🪪 Número de {doc}</label>"
                 f"<input id='idNum' inputmode='numeric' autocomplete='off' maxlength='{largo}' placeholder='{largo} dígitos'>"
                 "<div class='cf-err' id='idErr'></div></div>"
                 f"<button type='button' class='btn lg' id='idVer'>🛡️ Verificar {doc}</button>"
                 f"<div class='id-nota'><span>🔒</span><span>Solo usamos tu {doc} para confirmar tu identidad y tu edad. No guardamos foto de tu documento ni lo mostramos a nadie.</span></div></div>")
    cfg = {"pais": iso, "largo": largo, "doc": doc, "play": PLAY_URL}
    cuerpo = (head + f"<div class='lg-chips'>{chips}</div>" + panel + "</div>"
              "<script>window.ID=" + json.dumps(cfg) + ";</script><script>" + _JS_IDENTIDAD + "</script>")
    return ui.shell("Verificar identidad", cuerpo, sesion=ses, titulo_tab="Verificar identidad · Pichangol")


@router.post("/web/cuenta/identidad")
def verificar_identidad(request: Request, body: dict = Body(default_factory=dict)) -> JSONResponse:
    """`AppState.verificarConDni` para el correo de la SESIÓN."""
    ses = sesion.de_request(request)
    if not ses:
        return JSONResponse({"ok": False, "mensaje": "Inicia sesión primero."}, status_code=401)
    email = ses["email"].lower()
    pais = str(body.get("pais") or "PE").upper()
    if pais not in ("PE", "EC"):
        return JSONResponse({"ok": False, "mensaje": "En tu país la verificación se hace desde la app."}, status_code=400)
    doc, largo, _ = DOC[pais]
    numero = re.sub(r"\D", "", str(body.get("numero") or ""))
    if not numero:
        return JSONResponse({"ok": False, "mensaje": f"Escribe tu número de {doc}."}, status_code=400)
    if len(numero) != largo:
        return JSONResponse({"ok": False, "mensaje": f"El {doc} tiene {largo} dígitos."}, status_code=400)
    if datos.esta_verificado(email):
        return JSONResponse({"ok": True, "ya": True})
    if not _puede_intentar(email):
        return JSONResponse({"ok": False, "mensaje": "Hiciste varios intentos seguidos. Espera unos minutos y vuelve a probar."}, status_code=429)
    from propiedad.router import VerificarDniReq, post_verificar_dni
    try:
        data = post_verificar_dni(VerificarDniReq(dni=numero, email=email, pais=pais))
    except Exception:  # noqa: BLE001
        data = None
    if not data:
        return JSONResponse({"ok": False, "mensaje": "No pudimos conectar. Revisa tu conexión."}, status_code=502)
    if not data.get("ok"):
        err = data.get("error")
        if err == "dni_en_uso":
            msg = f"Ese {doc} ya está verificado en otra cuenta. Cada persona verifica una sola cuenta."
        elif err == "no_configurado":
            msg = "Servicio de verificación no disponible."
        else:
            msg = "Ese número no figura en el registro. Revísalo."
        return JSONResponse({"ok": False, "mensaje": msg}, status_code=400)
    from web.jugador_liga import mi_nombre
    if not registrar_verificado(email, mi_nombre(ses)):
        return JSONResponse({"ok": False, "mensaje": "Validamos tu documento pero no pudimos guardar la verificación. Reintenta."}, status_code=503)
    return JSONResponse({"ok": True, "edad": edad_desde(data.get("fecha_nacimiento"))})


_JS_CONFIG = r"""
(function(){
var C = window.CF || {}, $ = function(i){ return document.getElementById(i); };
var bio = Object.assign({}, C.bio || {}), pais = C.pais || 'PE', sucio = false;
function esc(s){ return String(s == null ? '' : s).replace(/[&<>"']/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]; }); }
document.querySelectorAll('[data-app]').forEach(function(b){ b.addEventListener('click', function(ev){ ev.preventDefault();
  pcgConfirmar({titulo: b.dataset.titulo, mensaje: b.dataset.app, icono: b.dataset.em || '📱', confirmar: 'Abrir la app', cancelar: 'Ahora no'})
    .then(function(ok){ if(ok) window.open(C.play, '_blank', 'noopener'); }); }); });
$('cfPais').addEventListener('click', function(ev){ var b = ev.target.closest('[data-pais]'); if(!b) return; pais = b.dataset.pais; sucio = true;
  this.querySelectorAll('.chip').forEach(function(x){ x.classList.toggle('sel', x === b); });
  $('cfPre').textContent = '+' + C.pref[pais]; $('cfCel').maxLength = C.largo[pais]; $('cfCel').placeholder = C.largo[pais] + ' dígitos'; $('cfErr').textContent = ''; });
$('cfCel').addEventListener('input', function(){ this.value = this.value.replace(/\D/g, ''); $('cfErr').textContent = ''; sucio = true; });
$('cfNombre').addEventListener('input', function(){ sucio = true; });
function pintaFila(clave){ var p = C.prompts.find(function(x){ return x[0] === clave; }), b = document.querySelector("[data-clave='" + clave + "'] .tx");
  b.textContent = bio[clave] ? p[2] + ': ' + bio[clave] : p[2]; b.classList.toggle('nada', !bio[clave]); }
document.querySelectorAll('[data-clave]').forEach(function(btn){ btn.addEventListener('click', function(){
  var p = C.prompts.find(function(x){ return x[0] === btn.dataset.clave; }), multi = p[4];
  var sel = (bio[p[0]] || '').split(' · ').filter(Boolean);
  var h = "<div class='cf-op' id='cfOp'>" + p[3].map(function(o){ return "<button type='button' class='chip" + (sel.indexOf(o) >= 0 ? ' sel' : '') + "' data-o='" + esc(o) + "'>" + esc(o) + "</button>"; }).join('') + "</div>" +
          (multi ? "<p class='sub' style='font-size:12.5px;text-align:left'>Puedes elegir varios.</p>" : '');
  var pr = pcgConfirmar({titulo: p[2], icono: p[1], html: h, confirmar: multi ? 'Listo' : 'Guardar', cancelar: sel.length ? 'Quitar' : 'Cancelar'});
  var quitar = !!sel.length;
  $('cfOp').addEventListener('click', function(ev){ var b = ev.target.closest('[data-o]'); if(!b) return; var o = b.dataset.o;
    if(multi){ var i = sel.indexOf(o); if(i >= 0) sel.splice(i, 1); else sel.push(o); b.classList.toggle('sel'); }
    else { sel = [o]; this.querySelectorAll('.chip').forEach(function(x){ x.classList.toggle('sel', x === b); }); var ok = document.getElementById('pcgDlgOk'); if(ok) ok.click(); } });
  pr.then(function(ok){
    if(ok){ var orden = p[3].filter(function(o){ return sel.indexOf(o) >= 0; }); if(orden.length) bio[p[0]] = orden.join(' · '); else delete bio[p[0]]; sucio = true; pintaFila(p[0]); }
    else if(quitar){ delete bio[p[0]]; sucio = true; pintaFila(p[0]); }
  });
}); });
// Foto: se comprime a 800 px (como el app) y sube al instante.
function comprimir(file){ return new Promise(function(res, rej){ var img = new Image(), u = URL.createObjectURL(file);
  img.onload = function(){ var k = Math.min(1, 800 / Math.max(img.width, img.height)), cv = document.createElement('canvas'); cv.width = Math.round(img.width * k); cv.height = Math.round(img.height * k);
    cv.getContext('2d').drawImage(img, 0, 0, cv.width, cv.height); URL.revokeObjectURL(u); cv.toBlob(function(b){ b ? res(b) : rej(); }, 'image/jpeg', 0.82); };
  img.onerror = function(){ URL.revokeObjectURL(u); rej(); }; img.src = u; }); }
$('cfEd').onclick = function(){ if(!C.subida){ pcgAvisar({titulo: 'Foto no disponible', icono: '📷', mensaje: 'La subida de fotos no está disponible en este momento. Puedes cambiarla desde la app.'}); return; } $('cfArchivo').click(); };
$('cfArchivo').onchange = function(){ var f = this.files && this.files[0]; this.value = ''; if(!f) return;
  pcgCargando('Subiendo tu foto…');
  comprimir(f).then(function(b){ return fetch('/web/cuenta/foto', {method: 'POST', headers: {'Content-Type': 'image/jpeg'}, body: b}); })
    .then(function(r){ return r.json(); }).then(function(j){ pcgCargando(false);
      if(!j.ok) return pcgAvisar({titulo: 'No se pudo', icono: '⚠️', mensaje: j.mensaje || 'Reintenta.'});
      var el = $('cfFoto'), im = document.createElement('img'); im.id = 'cfFoto'; im.alt = ''; im.src = j.foto; el.replaceWith(im); pcgToast('Foto actualizada.'); })
    .catch(function(){ pcgCargando(false); pcgAvisar({titulo: 'No se pudo', icono: '⚠️', mensaje: 'No se pudo subir la foto. Reintenta.'}); }); };
$('cfListo').onclick = function(){ var btn = this; if(btn.disabled) return;
  var nombre = $('cfNombre').value.trim(); if(!nombre){ pcgAvisar({titulo: 'Falta tu nombre', icono: '✍️', mensaje: 'Escribe tu nombre.'}); return; }
  var cel = $('cfCel').value.trim(); if(cel && cel.length !== C.largo[pais]){ $('cfErr').textContent = 'El celular tiene ' + C.largo[pais] + ' dígitos.'; $('cfCel').focus(); return; }
  btn.disabled = true; pcgCargando('Guardando…');
  fetch('/web/cuenta/perfil', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({nombre: nombre, pais: pais, celular: cel, bio: bio})})
    .then(function(r){ return r.json(); }).then(function(j){ btn.disabled = false; pcgCargando(false);
      if(!j.ok){ if(j.campo === 'celular'){ $('cfErr').textContent = j.mensaje; return; } return pcgAvisar({titulo: 'No se pudo guardar', icono: '⚠️', mensaje: j.mensaje || 'Reintenta.'}); }
      sucio = false; pcgAvisar({titulo: 'Perfil guardado', icono: '✅', mensaje: j.mensaje}).then(function(){ pcgIr('/perfil', 'Volviendo a tu perfil…'); }); })
    .catch(function(){ btn.disabled = false; pcgCargando(false); pcgAvisar({titulo: 'Sin conexión', icono: '📶', mensaje: 'Revisa tu internet y reintenta.'}); }); };
})();
"""

_JS_IDENTIDAD = r"""
(function(){
var C = window.ID || {}, $ = function(i){ return document.getElementById(i); };
if($('idApp')) $('idApp').onclick = function(){ window.open(C.play, '_blank', 'noopener'); };
var inp = $('idNum'); if(!inp) return;
inp.addEventListener('input', function(){ this.value = this.value.replace(/\D/g, ''); $('idErr').textContent = ''; });
$('idVer').onclick = function(){ var btn = this, n = inp.value.trim(); if(btn.disabled) return;
  if(!n){ $('idErr').textContent = 'Escribe tu número de ' + C.doc + '.'; return; }
  if(C.largo && n.length !== C.largo){ $('idErr').textContent = 'El ' + C.doc + ' tiene ' + C.largo + ' dígitos.'; return; }
  btn.disabled = true; pcgCargando('Validando tu ' + C.doc + '…');
  fetch('/web/cuenta/identidad', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({pais: C.pais, numero: n})})
    .then(function(r){ return r.json(); }).then(function(j){ btn.disabled = false; pcgCargando(false);
      if(!j.ok){ $('idErr').textContent = j.mensaje || 'No se pudo. Reintenta.'; return; }
      inp.value = '';
      pcgAvisar({titulo: '¡Identidad verificada! ✓', icono: '✅', mensaje: 'Tu perfil ahora muestra la insignia de jugador verificado. Los dueños de cancha confían más en jugadores verificados.' +
        (j.edad != null ? ' Edad según el registro: ' + j.edad + ' años.' : ''), confirmar: 'Listo'})
        .then(function(){ pcgIr('/perfil', 'Volviendo a tu perfil…'); }); })
    .catch(function(){ btn.disabled = false; pcgCargando(false); $('idErr').textContent = 'No pudimos conectar. Revisa tu conexión.'; }); };
})();
"""
