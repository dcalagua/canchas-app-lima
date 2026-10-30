"""LOGO DE LA MARCA configurable desde la torre (pedido del director,
20-oct-2026: "¿y si quiero cambiar de logo? quiero que sea configurable").

Un solo lugar para el isotipo (cuadrado) que ven usuarios y dueños:
- web: cabecera (`ui.wordmark`), favicon, diálogos, banner "Abrir en la app",
  vista previa de enlaces (og:image) → todo apunta a `GET /marca/logo.png`;
- correos de pago → `<base>/marca/logo.png`;
- piezas de redes, videos y afiches compuestos con Pillow → `abrir()`;
- APK → `GET /config/canal` publica `marca_logo_url` y el app lo cachea.

El operador sube un PNG/JPG en la torre → Comunicación → "🎨 Logo de la
marca"; se normaliza a 512×512 PNG (fondo transparente si el original lo
tiene, centrado y con margen), se guarda en Storage `canchas/marca/logo_<ms>.png`
y la URL queda en `stores.config[marca_logo_url]` (+ `marca_logo_v` para
saltar cachés). Sin logo propio, todo sigue con `static/brand/logo_pin.png`.
El ícono del APK en el celular y su pantalla de arranque NO cambian así:
van compilados en el APK (hay que generar uno nuevo)."""
from __future__ import annotations

import base64
import io
import os
import threading
import time
import urllib.request

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from db.store import stores

_DIR = os.path.dirname(os.path.abspath(__file__))
_STATIC = os.path.join(_DIR, "static", "brand")
LOGO_DEFECTO = os.path.join(_STATIC, "logo_pin.png")
LOGO_OG_DEFECTO = os.path.join(_STATIC, "logo_pichangol.png")

LADO = 512           # lado del PNG normalizado
LADO_MIN = 128       # menos que esto se ve pixelado en la cabecera
MAX_BYTES = 5 * 1024 * 1024

_cache: dict[str, bytes] = {}
_lock = threading.Lock()

router = APIRouter()


# ── estado ────────────────────────────────────────────────────────────────────
def url_propia() -> str:
    return str(stores.config.get("marca_logo_url") or "").strip()


def version() -> str:
    return str(stores.config.get("marca_logo_v") or "0")


def personalizado() -> bool:
    return bool(url_propia() or stores.config.get("marca_logo_b64"))


def url_publica(base: str = "") -> str:
    """URL ESTABLE para HTML y correos (el contenido cambia, la ruta no)."""
    return f"{base.rstrip('/')}/marca/logo.png?v={version()}"


def _leer(ruta: str) -> bytes:
    with open(ruta, "rb") as f:
        return f.read()


def logo_bytes() -> bytes:
    """PNG vigente: el propio (Storage, con caché en memoria) o el de siempre."""
    url = url_propia()
    if url:
        with _lock:
            if url in _cache:
                return _cache[url]
        try:
            with urllib.request.urlopen(url, timeout=8) as r:  # noqa: S310 — URL de nuestro Storage
                datos = r.read(MAX_BYTES + 1)
            if datos and len(datos) <= MAX_BYTES:
                with _lock:
                    _cache.clear()
                    _cache[url] = datos
                return datos
        except Exception as e:  # noqa: BLE001
            print(f"[marca] no se pudo leer el logo propio: {str(e)[:120]}", flush=True)
    b64 = str(stores.config.get("marca_logo_b64") or "")
    if b64:
        try:
            return base64.b64decode(b64)
        except Exception:  # noqa: BLE001
            pass
    return _leer(LOGO_DEFECTO)


def abrir():
    """El logo vigente como imagen Pillow RGBA (para piezas compuestas)."""
    from PIL import Image
    try:
        return Image.open(io.BytesIO(logo_bytes())).convert("RGBA")
    except Exception:  # noqa: BLE001
        return Image.open(LOGO_DEFECTO).convert("RGBA")


# ── normalización ─────────────────────────────────────────────────────────────
def normalizar(datos: bytes) -> bytes:
    """PNG cuadrado LADO×LADO: centra el logo con un margen del 6 %, conserva la
    transparencia y rechaza lo que no es imagen o es demasiado chico."""
    from PIL import Image, ImageOps
    if not datos:
        raise ValueError("Sube una imagen.")
    if len(datos) > MAX_BYTES:
        raise ValueError("La imagen pesa más de 5 MB.")
    try:
        im = Image.open(io.BytesIO(datos))
        im.load()
    except Exception as exc:  # noqa: BLE001
        raise ValueError("El archivo no es una imagen válida (usa PNG o JPG).") from exc
    im = ImageOps.exif_transpose(im).convert("RGBA")
    if min(im.size) < LADO_MIN:
        raise ValueError(f"La imagen es muy chica ({im.size[0]}×{im.size[1]}): usa al menos {LADO_MIN}×{LADO_MIN} px.")
    caja = im.getbbox()  # recorta el borde totalmente transparente
    if caja:
        im = im.crop(caja)
    util = int(LADO * 0.88)
    im.thumbnail((util, util), Image.LANCZOS)
    lienzo = Image.new("RGBA", (LADO, LADO), (255, 255, 255, 0))
    lienzo.paste(im, ((LADO - im.size[0]) // 2, (LADO - im.size[1]) // 2), im)
    out = io.BytesIO()
    lienzo.save(out, "PNG", optimize=True)
    return out.getvalue()


def _desde_data_url(s: str) -> bytes:
    s = (s or "").strip()
    if s.startswith("data:"):
        s = s.split(",", 1)[1] if "," in s else ""
    try:
        return base64.b64decode(s, validate=False)
    except Exception as exc:  # noqa: BLE001
        raise ValueError("No se pudo leer la imagen.") from exc


def guardar(datos: bytes) -> dict:
    """Normaliza, sube a Storage y deja la URL en la config (QAS y PRD tienen
    cada uno el suyo). Sin Storage (desarrollo), el PNG queda en la config."""
    from web import almacen
    png = normalizar(datos)
    ahora = int(time.time() * 1000)
    url = almacen.subir(almacen.BUCKET, f"marca/logo_{ahora}.png", png, "image/png") if almacen.disponible() else None
    anterior = url_propia()
    if url:
        stores.config["marca_logo_url"] = url
        stores.config.pop("marca_logo_b64", None)
    elif almacen.disponible():
        raise ValueError("No se pudo subir el logo a Storage. Reintenta en un momento.")
    else:
        stores.config["marca_logo_url"] = ""
        stores.config["marca_logo_b64"] = base64.b64encode(png).decode()
    stores.config["marca_logo_v"] = str(ahora)
    with _lock:
        _cache.clear()
        if url:
            _cache[url] = png
    if anterior and anterior != url:
        try:
            almacen.borrar_foto(anterior.split("?", 1)[0])
        except Exception:  # noqa: BLE001
            pass
    _persistir()
    return estado()


def quitar() -> dict:
    """Vuelve al logo original de siempre."""
    from web import almacen
    anterior = url_propia()
    stores.config["marca_logo_url"] = ""
    stores.config.pop("marca_logo_b64", None)
    stores.config["marca_logo_v"] = str(int(time.time() * 1000))
    with _lock:
        _cache.clear()
    if anterior:
        try:
            almacen.borrar_foto(anterior.split("?", 1)[0])
        except Exception:  # noqa: BLE001
            pass
    _persistir()
    return estado()


def _persistir() -> None:
    try:
        from db import pg
        pg.persistir_en_segundo_plano(stores)
    except Exception:  # noqa: BLE001
        pass


def estado() -> dict:
    return {"personalizado": personalizado(), "url": url_publica(), "version": version(),
            "storage": url_propia()}


def publico(base: str = "") -> dict:
    """Lo que lee el APK en `/config/canal`: URL absoluta del logo propio
    (vacía = usa el que trae el APK) y su versión para la caché."""
    return {"marca_logo_url": url_publica(base) if personalizado() else "", "marca_logo_v": version()}


# ── rutas ─────────────────────────────────────────────────────────────────────
_CACHE = {"Cache-Control": "public, max-age=300"}


@router.get("/marca/logo.png", include_in_schema=False)
def ruta_logo() -> Response:
    return Response(logo_bytes(), media_type="image/png", headers=_CACHE)


@router.get("/marca/logo-og.png", include_in_schema=False)
def ruta_logo_og() -> Response:
    """Vista previa de enlaces (WhatsApp/Facebook): el logo propio o, sin él,
    la pieza de marca de siempre."""
    datos = logo_bytes() if personalizado() else _leer(LOGO_OG_DEFECTO)
    return Response(datos, media_type="image/png", headers=_CACHE)


class LogoRequest(BaseModel):
    imagen: str = ""


def _check(token: str | None) -> None:
    from propiedad import panel
    panel._check(token)


@router.get("/admin/api/marca/logo")
def get_logo_admin(x_admin_token: str | None = Header(default=None)) -> dict:
    _check(x_admin_token)
    import config
    return {**estado(), "nombre": config.MARCA}


@router.post("/admin/api/marca/logo")
def set_logo_admin(req: LogoRequest, x_admin_token: str | None = Header(default=None)) -> dict:
    _check(x_admin_token)
    try:
        return {"ok": True, **guardar(_desde_data_url(req.imagen))}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/admin/api/marca/logo/quitar")
def quitar_logo_admin(x_admin_token: str | None = Header(default=None)) -> dict:
    _check(x_admin_token)
    return {"ok": True, **quitar()}
