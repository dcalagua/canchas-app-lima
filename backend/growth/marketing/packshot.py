"""PACKSHOTS IA para la bodega: imagen de producto GENÉRICA por TIPO (una
botella dorada de cerveza, una bolsa de papitas…), SIN marcas ni logos.

Decisión del director (ago-2026): NO se precargan logos oficiales (Pilsen,
Paceña, etc. son marcas registradas — usarlas sin licencia es riesgo legal y
además habría que curar cientos por país). En su lugar: packshot IA genérico
por tipo — funciona IGUAL en Perú, Bolivia y Ecuador porque muestra QUÉ es el
producto, no la marca — y la FOTO REAL del dueño siempre manda si existe.

Se genera UNA sola vez por tipo (≈16 imágenes en total, centavos), se cachea
en memoria y se persiste en Supabase Storage (`canchas/bodega/packshot_*.jpg`)
para no re-pagar tras un redeploy. Fail-safe: sin proveedor / error → None y
el APK muestra el emoji de siempre.
"""

from __future__ import annotations

import io
import threading
import urllib.request

from PIL import Image

import config

from . import arte_ia

# Descripciones en inglés, SIN marca (los modelos de imagen rinden mejor en
# inglés). El mapeo nombre/categoría → tipo vive en el APK
# (packshotTipoDe en lib/models/bodega.dart) y en bodega_web (carta pública).
_TIPOS = {
    "cerveza": "an ice-cold golden beer bottle with water droplets, no label",
    "agua": "a clear plastic bottle of still water with a blue cap, no label",
    "gaseosa": "a soda bottle with dark cola and red cap, no label",
    "jugo": "a small juice box drink with a straw, fruit colors, no label",
    "rehidratante": ("a sports drink bottle with bright blue isotonic "
                     "liquid, no label"),
    "papitas": ("a small open bag of potato chips with some chips spilling "
                "out, plain foil bag, no label"),
    "galletas": "a stack of round cookies next to a plain wrapper, no label",
    "chocolate": ("a chocolate bar with a few squares broken off, plain "
                  "wrapper, no label"),
    "mani": "a small bowl of roasted salted peanuts",
    "sandwich": "a fresh ham and cheese sandwich cut in half",
    "hielo": "a clear bag of ice cubes, frosty, no label",
    "pelotas": "a bright yellow tennis ball, new with vivid felt",
    "paleta": "a modern padel racket standing upright",
    "gorra": "a plain sports baseball cap, solid color, no logos",
    "toalla": "a folded fresh sports towel",
    "generico": "a small neutral shopping basket with assorted groceries",
}


def _prompt(tipo: str) -> str:
    desc = _TIPOS.get(tipo, _TIPOS["generico"])
    return (
        f"Clean professional product photography: {desc}, centered on a "
        "soft light gray studio background, soft shadows, photorealistic, "
        "square composition, no text, no letters, no logos, no watermark"
    )


_cache: dict[str, bytes] = {}
_lock = threading.Lock()
_locks: dict[str, threading.Lock] = {}


def _lock_de(tipo: str) -> threading.Lock:
    with _lock:
        return _locks.setdefault(tipo, threading.Lock())


def _storage_ruta(tipo: str) -> str:
    return f"bodega/packshot_{tipo}.jpg"


def _storage_leer(tipo: str) -> bytes | None:
    """¿Ya está el packshot en Storage (de un deploy anterior)? Best-effort."""
    base = arte_ia._storage_base()
    if base is None:
        return None
    url = f"{base}/storage/v1/object/public/canchas/{_storage_ruta(tipo)}"
    try:
        with urllib.request.urlopen(url, timeout=10) as r:  # noqa: S310
            datos = r.read()
        return datos if datos else None
    except Exception:  # noqa: BLE001
        return None


def _storage_guardar(tipo: str, datos: bytes) -> None:
    """Persiste el packshot (JPEG) para no re-pagarlo tras un redeploy."""
    base = arte_ia._storage_base()
    if base is None:
        return
    try:
        req = urllib.request.Request(
            f"{base}/storage/v1/object/canchas/{_storage_ruta(tipo)}",
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


def tipos() -> list[str]:
    return list(_TIPOS)


def disponible() -> bool:
    return arte_ia.disponible()


def imagen(tipo: str) -> bytes | None:
    """Packshot JPEG del [tipo] (cacheado + persistido). None = tipo
    desconocido, sin proveedor o falló la generación (el APK/carta caen al
    emoji de siempre)."""
    tipo = (tipo or "").strip().lower()
    if tipo not in _TIPOS:
        return None
    con = _cache.get(tipo)
    if con is not None:
        return con
    with _lock_de(tipo):
        con = _cache.get(tipo)  # ¿otro hilo lo generó mientras esperaba?
        if con is not None:
            return con
        # 1. ¿Persistido en Storage de un deploy anterior? (gratis)
        durable = _storage_leer(tipo)
        if durable is not None:
            _cache[tipo] = durable
            return durable
        if not disponible():
            return None
        # 2. Generar con el proveedor, normalizar a JPEG y persistir.
        crudo = arte_ia.generar(_prompt(tipo))
        if not crudo:
            return None
        try:
            img = Image.open(io.BytesIO(crudo)).convert("RGB")
            lado = min(img.size)
            img = img.crop((
                (img.width - lado) // 2, (img.height - lado) // 2,
                (img.width + lado) // 2, (img.height + lado) // 2,
            ))
            if lado > 640:
                img = img.resize((640, 640), Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=88)
            datos = buf.getvalue()
        except Exception:  # noqa: BLE001
            return None
        _cache[tipo] = datos
        _storage_guardar(tipo, datos)
        return datos
