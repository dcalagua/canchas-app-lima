"""ILUSTRACIONES de marca para el APK (darle vida a la app, pedido del
director): imágenes IA de ESTILO CONSISTENTE (flat, paleta lima/bosque de
Pichangol) para los ESTADOS VACÍOS y momentos del app — donde una ilustración
cálida gana; los íconos chicos de navegación siguen siendo del sistema (con
color), que es lo legible.

Mismo patrón que los packshots: cada clave se genera UNA sola vez (centavos),
se cachea en memoria y se persiste en Supabase Storage
(`canchas/ilustraciones/il_*.jpg`). Fail-safe: sin proveedor → 404 y el APK
muestra el emoji de siempre.
"""

from __future__ import annotations

import io
import threading
import urllib.request

from PIL import Image

import config

from . import arte_ia

# Descripciones por CLAVE (en inglés, los modelos rinden mejor). El estilo va
# en _prompt para que TODAS salgan de la misma familia visual.
_CLAVES = {
    "billetera_vacia": ("a friendly open wallet with a small tennis ball "
                        "and a soccer ball peeking out"),
    "puntos_vacio": ("a shiny star trophy surrounded by small floating "
                     "stars and a tennis ball"),
    "bodega_vacia": ("a small cooler box with soda bottles and a snack "
                     "bag next to a sports bench"),
    "pedidos_vacio": ("a serving tray with a sports drink running on "
                      "little legs towards a tennis court"),
    "cuentas_vacio": ("a small friendly notebook with a pencil and a "
                      "beer mug next to it"),
    "mensajes_vacio": ("two friendly chat bubbles with a tennis ball and "
                       "a soccer ball inside them"),
    "reservas_vacias": ("a calendar page with a tennis racket and a "
                        "whistle resting on it"),
    "clases_vacias": ("a sports whistle, a training cone and a small "
                      "notebook for a sports academy"),
    "explorar_vacio": ("a map with a location pin shaped like a tennis "
                       "ball over a small sports field"),
    "celebracion": ("confetti and a golden trophy over a small sports "
                    "court, celebration moment"),
}


def _prompt(clave: str) -> str:
    desc = _CLAVES.get(clave, "")
    return (
        f"Flat vector style spot illustration for a sports booking app: "
        f"{desc}. Friendly, minimal and warm, rounded shapes, "
        "brand palette: soft lime green #AEEA94, deep forest green #14463A, "
        "warm yellow #F2C94C accents, clean white background, "
        "square composition, no people, no text, no letters, no watermark"
    )


_cache: dict[str, bytes] = {}
_lock = threading.Lock()
_locks: dict[str, threading.Lock] = {}


def _lock_de(clave: str) -> threading.Lock:
    with _lock:
        return _locks.setdefault(clave, threading.Lock())


def _storage_ruta(clave: str) -> str:
    return f"ilustraciones/il_{clave}.jpg"


def _storage_leer(clave: str) -> bytes | None:
    base = arte_ia._storage_base()
    if base is None:
        return None
    url = f"{base}/storage/v1/object/public/canchas/{_storage_ruta(clave)}"
    try:
        with urllib.request.urlopen(url, timeout=10) as r:  # noqa: S310
            datos = r.read()
        return datos if datos else None
    except Exception:  # noqa: BLE001
        return None


def _storage_guardar(clave: str, datos: bytes) -> None:
    base = arte_ia._storage_base()
    if base is None:
        return
    try:
        req = urllib.request.Request(
            f"{base}/storage/v1/object/canchas/{_storage_ruta(clave)}",
            data=datos,
            method="POST",
            headers={
                "Authorization": f"Bearer {config.SUPABASE_ANON_KEY}",
                "apikey": config.SUPABASE_ANON_KEY,
                "Content-Type": "image/jpeg",
                "x-upsert": "true",
            })
        with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310
            r.read()
    except Exception:  # noqa: BLE001
        pass


def claves() -> list[str]:
    return list(_CLAVES)


def disponible() -> bool:
    return arte_ia.disponible()


def imagen(clave: str) -> bytes | None:
    """Ilustración JPEG de la [clave] (cacheada + persistida). None = clave
    desconocida, sin proveedor o falló (el APK cae al emoji)."""
    clave = (clave or "").strip().lower()
    if clave not in _CLAVES:
        return None
    con = _cache.get(clave)
    if con is not None:
        return con
    with _lock_de(clave):
        con = _cache.get(clave)
        if con is not None:
            return con
        durable = _storage_leer(clave)
        if durable is not None:
            _cache[clave] = durable
            return durable
        if not disponible():
            return None
        crudo = arte_ia.generar(_prompt(clave))
        if not crudo:
            return None
        try:
            img = Image.open(io.BytesIO(crudo)).convert("RGB")
            lado = min(img.size)
            img = img.crop((
                (img.width - lado) // 2, (img.height - lado) // 2,
                (img.width + lado) // 2, (img.height + lado) // 2,
            ))
            if lado > 720:
                img = img.resize((720, 720), Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=90)
            datos = buf.getvalue()
        except Exception:  # noqa: BLE001
            return None
        _cache[clave] = datos
        _storage_guardar(clave, datos)
        return datos
