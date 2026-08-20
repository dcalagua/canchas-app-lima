"""ARTE IA para los afiches (híbrido aprobado por el director): la IA genera
solo el FONDO fotográfico (jugador en acción, sin texto) y Pillow superpone
los textos exactos encima — así el precio/fechas jamás salen mal escritos.

Proveedor AUTO-DETECTADO por la env presente en Railway:
  - `OPENAI_API_KEY`      → gpt-image-1 (fallback dall-e-3 si la org no está
                            verificada para gpt-image-1)
  - `REPLICATE_API_TOKEN` → black-forest-labs/flux-schnell (~$0.003/imagen)

CACHÉ por DEPORTE (en memoria): el fondo no depende del campeonato, así que
se genera UNA vez por deporte y se reusa en todos los afiches → centavos en
total, y solo la primera petición espera la generación. Fail-safe: cualquier
error → None y el afiche usa el gradiente de marca de siempre.
"""

from __future__ import annotations

import base64
import io
import json
import threading
import urllib.request

from PIL import Image

import config

_TIMEOUT = 90  # la generación de imagen puede tardar

# Caché en memoria: deporte → PIL.Image (RGB). Se pierde al redeploy (se
# regenera; cuesta centavos). El lock evita generar 2 veces en paralelo.
_cache: dict[str, Image.Image] = {}
_lock = threading.Lock()

_ESCENA = {
    "tenis": "a tennis player mid-swing hitting a forehand on a tennis court",
    "futbol": "a soccer player striking the ball on a turf field",
    "padel": "a padel player smashing the ball on a padel court with glass walls",
    "pickleball": "a pickleball player at the net hitting a volley",
    "voley": "a volleyball player spiking the ball over the net",
    "basquet": "a basketball player driving to the hoop",
    "natacion": "a swimmer doing freestyle stroke in a competition pool",
}


def _prompt(deporte: str) -> str:
    escena = _ESCENA.get(deporte, _ESCENA["tenis"])
    return (
        f"Dramatic professional sports photography poster background: {escena}, "
        "shot at night with cinematic rim lighting, deep navy blue and emerald "
        "green color grading, dark moody atmosphere, subject in the lower two "
        "thirds of the frame, generous dark empty space at the top and bottom "
        "for typography, vertical 4:5 composition, photorealistic, "
        "no text, no letters, no watermark, no logos"
    )


def _openai(deporte: str) -> bytes | None:
    """OpenAI Images: gpt-image-1 y, si no está habilitado, dall-e-3."""
    for modelo, size in (("gpt-image-1", "1024x1536"),
                         ("dall-e-3", "1024x1792")):
        try:
            cuerpo = {"model": modelo, "prompt": _prompt(deporte),
                      "size": size, "n": 1}
            if modelo == "gpt-image-1":
                cuerpo["quality"] = "medium"
            else:
                cuerpo["response_format"] = "b64_json"
            req = urllib.request.Request(
                "https://api.openai.com/v1/images/generations",
                data=json.dumps(cuerpo).encode(),
                headers={
                    "Authorization": f"Bearer {config.OPENAI_API_KEY}",
                    "Content-Type": "application/json",
                })
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
                j = json.loads(resp.read().decode())
            dato = (j.get("data") or [{}])[0]
            if dato.get("b64_json"):
                return base64.b64decode(dato["b64_json"])
            if dato.get("url"):
                with urllib.request.urlopen(dato["url"],
                                            timeout=_TIMEOUT) as r2:
                    return r2.read()
        except Exception:
            continue  # prueba el siguiente modelo
    return None


def _replicate(deporte: str) -> bytes | None:
    """Replicate Flux (schnell): rápido y ~$0.003 por imagen."""
    try:
        cuerpo = {"input": {"prompt": _prompt(deporte),
                            "aspect_ratio": "4:5",
                            "output_format": "png"}}
        req = urllib.request.Request(
            "https://api.replicate.com/v1/models/"
            "black-forest-labs/flux-schnell/predictions",
            data=json.dumps(cuerpo).encode(),
            headers={
                "Authorization": f"Bearer {config.REPLICATE_API_TOKEN}",
                "Content-Type": "application/json",
                "Prefer": "wait",  # respuesta síncrona (hasta ~60 s)
            })
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            j = json.loads(resp.read().decode())
        salida = j.get("output")
        url = salida[0] if isinstance(salida, list) and salida else salida
        if not isinstance(url, str) or not url.startswith("http"):
            return None
        with urllib.request.urlopen(url, timeout=_TIMEOUT) as r2:
            return r2.read()
    except Exception:
        return None


def disponible() -> bool:
    return bool(config.OPENAI_API_KEY or config.REPLICATE_API_TOKEN)


_generando: set[str] = set()


def fondo_cacheado(deporte: str) -> Image.Image | None:
    """Solo el fondo YA cacheado (nunca bloquea). Para respuestas que deben
    ser inmediatas, p. ej. el og:image que baja el robot de WhatsApp."""
    d = deporte if deporte in _ESCENA else "tenis"
    return _cache.get(d)


def precalentar(deporte: str) -> None:
    """Dispara la generación del fondo IA en un hilo (si falta) y retorna al
    instante: la siguiente petición ya lo encuentra en caché."""
    if not disponible():
        return
    d = deporte if deporte in _ESCENA else "tenis"
    if d in _cache or d in _generando:
        return
    _generando.add(d)

    def _correr():
        try:
            fondo_para(d)
        finally:
            _generando.discard(d)

    threading.Thread(target=_correr, daemon=True).start()


def fondo_para(deporte: str) -> Image.Image | None:
    """Fondo IA para [deporte] (cacheado). None = sin proveedor / falló →
    el afiche usa el gradiente de marca."""
    if not disponible():
        return None
    d = deporte if deporte in _ESCENA else "tenis"
    con = _cache.get(d)
    if con is not None:
        return con
    with _lock:
        con = _cache.get(d)  # ¿otro hilo la generó mientras esperaba?
        if con is not None:
            return con
        crudo = _openai(d) if config.OPENAI_API_KEY else _replicate(d)
        if not crudo:
            return None
        try:
            img = Image.open(io.BytesIO(crudo)).convert("RGB")
        except Exception:
            return None
        _cache[d] = img
        return img
