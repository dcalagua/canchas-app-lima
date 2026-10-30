"""Miniaturas de las fotos de la web (ronda 3, oct-2026).

La portada pesaba ~1,7 MB en escritorio porque cada tarjeta bajaba la foto
ORIGINAL (las del APK llegan a 600 KB y 4000 px) y el plan actual de Supabase
Storage no redimensiona. Este módulo decide, para cada URL de foto, una versión
chica según su origen:

* **Nuestro Storage** (`<SUPABASE_URL>/storage/v1/object/public/{canchas|
  productos}/…`): se sirve por `GET /web/mini?u=&w=`, que baja la original UNA
  vez, la achica con Pillow a los anchos fijos `ANCHOS` (WebP) y la guarda en el
  MISMO bucket bajo `canchas/mini/<bucket>/<ruta original>/<clave>_<ancho>.webp`
  (clave = huella del ETag de la original: si el dueño reemplaza la foto en la
  misma ruta, cambia la clave; variar `?v=` no crea miniaturas nuevas). Responde
  con un redirect cacheable a la miniatura; ante cualquier falla, redirect a la
  original (la foto nunca deja de verse). La carpeta lleva la ruta de la
  original para que el barrido de Storage sepa de quién es cada miniatura
  (`storage_limpieza.py`, consulta "miniaturas").
* **Google** (`lh3.googleusercontent.com`, las `photoUri` cosechadas): NO se
  copian ni se guardan (términos de Google); solo se baja el parámetro de ancho
  de la URL (`=s4800-w800` → `=s4800-w480`), nunca por encima del original.
* **Unsplash** (datos demo): parámetro `w=` de la URL.
* Cualquier otra URL: tal cual.

Sin `SUPABASE_URL` + `SUPABASE_ANON_KEY` (tests/dev) nuestras URLs quedan como
están. `WEB_MINIATURAS=0` apaga todo (corte de emergencia, sin publicar código).
"""

from __future__ import annotations

import hashlib
import html
import io
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import OrderedDict

from fastapi import APIRouter
from fastapi.responses import JSONResponse, RedirectResponse

import config

router = APIRouter()

ANCHOS = (480, 720, 960)  # 1x escritorio · 2x celular / retina · 3x celular
BUCKETS = ("canchas", "productos")       # buckets públicos con fotos de la web
CARPETA = "mini"                          # canchas/mini/<bucket>/<ruta>/<clave>_<w>.webp
MAX_BYTES = 15 * 1024 * 1024              # original más grande que se acepta bajar
MAX_PIXELES = 40_000_000                  # 40 MP: más que eso no es una foto de cancha
TIMEOUT = 15
CALIDAD_WEBP = 72
CACHE_MINI = 7 * 24 * 3600                # redirect a la miniatura (inmutable por clave)
CACHE_FALLA = 60                          # redirect a la original: reintentar pronto
REINTENTO_FALLA_S = 600

# Atributos `sizes` por contexto (ancho que ocupa la foto en pantalla).
SIZES_TARJETA = "(max-width: 600px) 92vw, (max-width: 1100px) 46vw, 300px"
SIZES_PRINCIPAL = "(max-width: 900px) 100vw, 640px"
SIZES_CHICA = "(max-width: 900px) 100vw, 320px"
SIZES_MINI = "120px"

PRECALENTAR = True  # generar al subir (los tests lo apagan en conftest)

_hechas: OrderedDict[tuple[str, int], str] = OrderedDict()  # (url original, ancho) → URL de la miniatura
_MAX_HECHAS = 20_000
_fallas: dict[str, float] = {}
_lock = threading.Lock()
_por_url: dict[str, threading.Lock] = {}
_sem = threading.BoundedSemaphore(3)       # descargas + Pillow en paralelo
_RUTA_OK = re.compile(r"^[\w.\- ]+(?:/[\w.\- ]+)*$", re.UNICODE)


def activo() -> bool:
    return os.environ.get("WEB_MINIATURAS", "1").strip() != "0"


def _storage_ok() -> bool:
    return bool(config.SUPABASE_URL and config.SUPABASE_ANON_KEY)


def _host_supabase() -> str:
    return urllib.parse.urlsplit(config.SUPABASE_URL or "").netloc.lower()


def _ancho(w) -> int:
    """Ancho pedido → el permitido más cercano por arriba (o el mayor)."""
    try:
        w = int(w)
    except (TypeError, ValueError):
        return ANCHOS[0]
    for a in ANCHOS:
        if w <= a:
            return a
    return ANCHOS[-1]


# ── reconocer URLs ───────────────────────────────────────────────────────────

def objeto_nuestro(u: str) -> tuple[str, str] | None:
    """(bucket, ruta SIN escapar) si `u` es una foto pública de NUESTRO Storage
    en un bucket permitido; None en cualquier otro caso (anti-SSRF: es la única
    forma de que `/web/mini` baje algo)."""
    if not u or not _storage_ok():
        return None
    try:
        p = urllib.parse.urlsplit(u)
    except ValueError:
        return None
    if p.scheme != "https" or p.netloc.lower() != _host_supabase() or p.username or p.password:
        return None
    pref = "/storage/v1/object/public/"
    if not p.path.startswith(pref):
        return None
    bucket, _, ruta = p.path[len(pref):].partition("/")
    ruta = urllib.parse.unquote(ruta)
    if bucket not in BUCKETS or not ruta or len(ruta) > 400 or ".." in ruta:
        return None
    if ruta.startswith(CARPETA + "/") or not _RUTA_OK.match(ruta):
        return None
    if not ruta.lower().rsplit(".", 1)[-1] in ("jpg", "jpeg", "png", "webp"):
        return None
    return bucket, ruta


def _q(ruta: str) -> str:
    return "/".join(urllib.parse.quote(x, safe="") for x in ruta.split("/"))


def _url_publica(ruta: str) -> str:
    return f"{config.SUPABASE_URL.rstrip('/')}/storage/v1/object/public/canchas/{_q(ruta)}"


def _ruta_mini(bucket: str, ruta: str, clave: str, w: int, ext: str = "webp") -> str:
    return f"{CARPETA}/{bucket}/{ruta}/{clave}_{w}.{ext}"


_GOOGLE_OPC = re.compile(r"=([a-z0-9-]+)$")


def _google(u: str, w: int) -> str | None:
    """`photoUri` de Google con el ancho bajado (sin copiar ni guardar nada)."""
    p = urllib.parse.urlsplit(u)
    if not p.netloc.endswith("googleusercontent.com") or p.query:
        return None
    m = _GOOGLE_OPC.search(p.path)
    if not m:
        return None
    toks = m.group(1).split("-")
    wt = [t for t in toks if re.fullmatch(r"w\d+", t)]
    if wt:
        w = min(w, int(wt[0][1:]))
        nuevos = [f"w{w}" if re.fullmatch(r"w\d+", t) else t for t in toks if not re.fullmatch(r"h\d+", t)]
    elif any(re.fullmatch(r"s\d+", t) for t in toks):
        nuevos = [f"s{min(w, int(t[1:]))}" if re.fullmatch(r"s\d+", t) else t for t in toks]
    else:
        return None
    return u[:len(u) - len(m.group(0))] + "=" + "-".join(nuevos)


def _unsplash(u: str, w: int) -> str | None:
    p = urllib.parse.urlsplit(u)
    if p.netloc != "images.unsplash.com":
        return None
    qs = urllib.parse.parse_qsl(p.query, keep_blank_values=True)
    orig = next((v for k, v in qs if k == "w"), "")
    if orig.isdigit():
        w = min(w, int(orig))
    qs = [(k, v) for k, v in qs if k not in ("w", "auto")] + [("w", str(w)), ("auto", "format")]
    return urllib.parse.urlunsplit((p.scheme, p.netloc, p.path, urllib.parse.urlencode(qs), ""))


def url(u: str, w: int = ANCHOS[0]) -> str:
    """URL de la versión de ~`w` px de ancho de la foto `u` (o `u` tal cual)."""
    u = str(u or "").strip()
    if not u.startswith("https://") or not activo():
        return u
    w = _ancho(w)
    if objeto_nuestro(u):
        hecha = _hechas.get((u, w))
        if hecha:
            return hecha
        return f"/web/mini?u={urllib.parse.quote(u, safe='')}&w={w}"
    return _google(u, w) or _unsplash(u, w) or u


def redimensionable(u: str) -> bool:
    return url(u, ANCHOS[0]) != str(u or "").strip()


def srcset(u: str) -> str:
    if not redimensionable(u):
        return ""
    vistos: list[str] = []
    partes = []
    for w in ANCHOS:
        x = url(u, w)
        if x not in vistos:
            vistos.append(x)
            partes.append(f"{x} {w}w")
    return ", ".join(partes) if len(partes) > 1 else ""


def img(u: str, alt: str = "", *, w: int = ANCHOS[0], sizes: str = SIZES_TARJETA, clase: str = "",
        prioridad: bool = False, dims: bool = True, extra: str = "") -> str:
    """`<img>` con la miniatura, `srcset` 1x/2x, carga diferida (o prioridad
    alta para la primera foto visible) y medidas para no mover la página
    (`dims=False` donde el CSS no fija alto y ancho)."""
    e = html.escape
    ss = srcset(u)
    attrs = [f"src='{e(url(u, w))}'"]
    if ss:
        attrs.append(f"srcset='{e(ss)}' sizes='{e(sizes)}'")
    if clase:
        attrs.append(f"class='{e(clase)}'")
    attrs.append(f"alt='{e(alt or '')}'")
    attrs.append("fetchpriority='high'" if prioridad else "loading='lazy'")
    attrs.append("decoding='async'")
    if dims:
        attrs.append(f"width='{w}' height='{round(w * 0.95)}'")
    if extra:
        attrs.append(extra)
    return "<img " + " ".join(attrs) + ">"


def para_js(fotos: list[str], w: int = ANCHOS[0]) -> list[dict]:
    """Lo mismo para el JS que pinta fotos después (`data-buscar`, galería):
    `[{s: src, ss: srcset}]` alineado con `fotos`."""
    return [{"s": url(f, w), "ss": srcset(f)} for f in (fotos or [])]


# ── generar ──────────────────────────────────────────────────────────────────

def _recordar(u: str, w: int, mini: str) -> None:
    with _lock:
        _hechas[(u, w)] = mini
        _hechas.move_to_end((u, w))
        while len(_hechas) > _MAX_HECHAS:
            _hechas.popitem(last=False)


def _abrir(req: urllib.request.Request):
    return urllib.request.urlopen(req, timeout=TIMEOUT)  # noqa: S310 (solo nuestro Storage)


def _cabeza(u: str) -> dict | None:
    """HEAD de una URL de nuestro Storage → cabeceras (minúsculas) o None."""
    try:
        with _abrir(urllib.request.Request(u, method="HEAD")) as r:
            if getattr(r, "status", 200) != 200:
                return None
            return {k.lower(): v for k, v in r.headers.items()}
    except Exception:  # noqa: BLE001
        return None


def _clave(cab: dict) -> str | None:
    base = cab.get("etag") or ""
    if not base and cab.get("last-modified"):
        base = f"{cab.get('last-modified')}|{cab.get('content-length', '')}"
    base = re.sub(r"[^0-9A-Za-z|:, -]", "", base)
    return hashlib.sha1(base.encode()).hexdigest()[:16] if base else None


def _bajar(u: str) -> bytes | None:
    try:
        with _abrir(urllib.request.Request(u)) as r:
            tipo = (r.headers.get("Content-Type") or "").lower()
            if not tipo.startswith("image/") or "svg" in tipo:
                return None
            datos = r.read(MAX_BYTES + 1)
            return datos if 0 < len(datos) <= MAX_BYTES else None
    except Exception:  # noqa: BLE001
        return None


def _formato() -> tuple[str, str, str]:
    from PIL import features
    return ("WEBP", "webp", "image/webp") if features.check("webp") else ("JPEG", "jpg", "image/jpeg")


def achicar(datos: bytes, w: int) -> bytes | None:
    """Foto → miniatura de ancho ≤ `w` (nunca agranda), orientación EXIF
    aplicada, WebP (JPEG si el Pillow no trae WebP)."""
    from PIL import Image, ImageOps
    try:
        im = Image.open(io.BytesIO(datos))
        if im.width * im.height > MAX_PIXELES:
            return None
        im = ImageOps.exif_transpose(im)
        alfa = im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info)
        fmt, _ext, _ct = _formato()
        im = im.convert("RGBA" if alfa and fmt == "WEBP" else "RGB")
        im.thumbnail((w, w * 2), Image.LANCZOS)
        out = io.BytesIO()
        if fmt == "WEBP":
            im.save(out, "WEBP", quality=CALIDAD_WEBP, method=4)
        else:
            im.save(out, "JPEG", quality=78, optimize=True, progressive=True)
        return out.getvalue()
    except Exception:  # noqa: BLE001 (imagen rota, bomba, formato raro)
        return None


def _generar(u: str, bucket: str, ruta: str, clave: str, datos: bytes) -> bool:
    from web import almacen
    _fmt, ext, ct = _formato()
    ok = True
    for w in ANCHOS:
        chica = achicar(datos, w)
        dest = _ruta_mini(bucket, ruta, clave, w, ext)
        if not chica or not almacen.subir("canchas", dest, chica, ct, cache_control=f"max-age={365 * 24 * 3600}"):
            ok = False
            continue
        _recordar(u, w, _url_publica(dest))
    return ok


def _lock_de(u: str) -> threading.Lock:
    with _lock:
        lk = _por_url.get(u)
        if lk is None:
            if len(_por_url) > 2000:
                _por_url.clear()
            lk = _por_url[u] = threading.Lock()
        return lk


def resolver(u: str, w: int) -> str | None:
    """URL pública de la miniatura de `u` a ancho `w`; la genera si no existe.
    None = no se pudo (el endpoint manda a la original)."""
    w = _ancho(w)
    obj = objeto_nuestro(u)
    if not obj or not activo():
        return None
    hecha = _hechas.get((u, w))
    if hecha:
        return hecha
    if time.time() - _fallas.get(u, 0) < REINTENTO_FALLA_S:
        return None
    bucket, ruta = obj
    lk = _lock_de(u)
    if not lk.acquire(timeout=TIMEOUT):
        return None
    try:
        hecha = _hechas.get((u, w))  # la hizo otro hilo mientras esperábamos
        if hecha:
            return hecha
        if not _sem.acquire(timeout=8):
            return None
        try:
            ext = _formato()[1]
            clave = _clave(_cabeza(u) or {})
            if clave:
                dest = _url_publica(_ruta_mini(bucket, ruta, clave, w, ext))
                if _cabeza(dest) is not None:  # ya existía (otro proceso / antes de reiniciar)
                    _recordar(u, w, dest)
                    return dest
            datos = _bajar(u)
            if datos and not clave:  # sin ETag ni fecha: huella del contenido
                clave = hashlib.sha1(datos).hexdigest()[:16]
            if not datos or not _generar(u, bucket, ruta, clave, datos):
                _fallas[u] = time.time()
            return _hechas.get((u, w))
        finally:
            _sem.release()
    finally:
        lk.release()


def precalentar(u: str, datos: bytes) -> None:
    """Al subir una foto desde la web: miniaturas YA (con los bytes en mano),
    así el primer visitante no paga la espera. En segundo plano, best-effort."""
    if not PRECALENTAR or not activo() or not objeto_nuestro(u) or not datos:
        return

    def _trabajo():
        obj = objeto_nuestro(u)
        if not obj:
            return
        with _sem:
            clave = _clave(_cabeza(u) or {}) or hashlib.sha1(datos).hexdigest()[:16]
            _generar(u, obj[0], obj[1], clave, datos)

    threading.Thread(target=_trabajo, name="pcg-mini", daemon=True).start()


@router.get("/web/mini")
def miniatura(u: str = "", w: int = ANCHOS[0]):
    """Redirect a la miniatura de una foto de NUESTRO Storage (la genera la
    primera vez). URL ajena → 404 (no es un redirector abierto); falla al
    generar → redirect a la original con caché corta."""
    if not objeto_nuestro(u):
        return JSONResponse({"ok": False, "error": "url_no_permitida"}, status_code=404)
    mini = resolver(u, w)
    if mini:
        return RedirectResponse(mini, status_code=302,
                                headers={"Cache-Control": f"public, max-age={CACHE_MINI}"})
    return RedirectResponse(u, status_code=302, headers={"Cache-Control": f"public, max-age={CACHE_FALLA}"})
