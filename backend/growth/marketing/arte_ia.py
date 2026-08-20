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
import hashlib
import io
import json
import threading
import urllib.request

from PIL import Image

import config

_TIMEOUT = 90  # la generación de imagen puede tardar

# Caché en memoria (clave deporte:variante → PIL.Image RGB) + copia DURABLE
# en Supabase Storage (bucket canchas/afiches): así el arte NO se re-genera
# (ni se re-paga) en cada redeploy de Railway. Locks POR CLAVE: varias
# variantes pueden generarse en paralelo (la galería pide 5 a la vez).
_cache: dict[str, Image.Image] = {}
_lock = threading.Lock()
_locks: dict[str, threading.Lock] = {}


def _lock_de(clave: str) -> threading.Lock:
    with _lock:
        return _locks.setdefault(clave, threading.Lock())


def _storage_base() -> str | None:
    base = (config.SUPABASE_URL or "").strip().strip('"').strip("'").rstrip("/")
    if not base or not config.SUPABASE_ANON_KEY:
        return None
    if not base.startswith("http"):
        base = f"https://{base}"
    return base


def _storage_ruta(clave: str) -> str:
    return f"afiches/fondo_{clave.replace(':', '_')}.jpg"


def _storage_leer(clave: str) -> Image.Image | None:
    """¿Ya está el arte en Storage (de un deploy anterior)? Best-effort."""
    base = _storage_base()
    if base is None:
        return None
    url = f"{base}/storage/v1/object/public/canchas/{_storage_ruta(clave)}"
    try:
        with urllib.request.urlopen(url, timeout=10) as r:  # noqa: S310
            return Image.open(io.BytesIO(r.read())).convert("RGB")
    except Exception:  # noqa: BLE001
        return None


def _storage_guardar(clave: str, img: Image.Image) -> None:
    """Persiste el arte generado (JPEG) para no re-pagarlo tras un redeploy."""
    base = _storage_base()
    if base is None:
        return
    try:
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=90)
        req = urllib.request.Request(
            f"{base}/storage/v1/object/canchas/{_storage_ruta(clave)}",
            data=buf.getvalue(),
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

_ESCENA = {
    "tenis": "a tennis player mid-swing hitting a forehand on a tennis court",
    "futbol": "a soccer player striking the ball on a turf field",
    "padel": "a padel player smashing the ball on a padel court with glass walls",
    "pickleball": "a pickleball player at the net hitting a volley",
    "voley": "a volleyball player spiking the ball over the net",
    "basquet": "a basketball player driving to the hoop",
    "natacion": "a swimmer doing freestyle stroke in a competition pool",
}


# Escena SIN personas (temática "solo la cancha").
_CANCHA = {
    "tenis": "a beautiful empty tennis court",
    "futbol": "a beautiful empty soccer field with goal posts",
    "padel": "a beautiful empty padel court with glass walls",
    "pickleball": "a beautiful empty pickleball court",
    "voley": "a beautiful empty volleyball court with net",
    "basquet": "a beautiful empty basketball court with hoop",
    "natacion": "a beautiful empty olympic swimming pool with lane lines",
}

# TEMÁTICAS curadas (chips en el APK). "" = la nocturna de marca de siempre.
# Cualquier otro texto = descripción LIBRE del organizador ("Mi idea").
_TEMAS = {
    "": ("shot at night with cinematic rim lighting, deep navy blue and "
         "emerald green color grading, dark moody atmosphere"),
    "claro": ("bright daylight scene, clean white and light background, "
              "airy fresh minimal atmosphere, soft natural sunlight"),
    "cancha": ("wide establishing shot of the venue, vibrant colors, "
               "late afternoon light, no people"),
    "amanecer": ("golden hour sunrise light, warm orange and teal color "
                 "grading, hopeful atmosphere"),
    "celebracion": ("the athlete celebrating a victory with arms raised, "
                    "confetti in the air, festive stadium atmosphere"),
}


# Variantes de encuadre/estilo: "generar otro arte" avanza a la siguiente
# (cache por deporte+variante, así el organizador puede cambiar el fondo).
_VARIACIONES = [
    "",
    "low angle action shot, ",
    "wide angle dramatic perspective, ",
    "close-up on the decisive moment, ",
    "backlit silhouette against stadium lights, ",
]


def _prompt(deporte: str, variante: int = 0, tema: str = "") -> str:
    tema = (tema or "").strip()[:140]
    # Deporte desconocido → escena GENÉRICA (nunca un tenista por defecto).
    if tema == "cancha":
        escena = _CANCHA.get(deporte, "a beautiful empty sports venue")
    else:
        escena = _ESCENA.get(
            deporte, "dynamic athletes in action, energetic sports scene")
    extra = _VARIACIONES[variante % len(_VARIACIONES)]
    # Temática curada, o la DESCRIPCIÓN LIBRE del organizador ("Mi idea").
    estilo = _TEMAS.get(tema, tema)
    return (
        f"Professional sports photography poster background: "
        f"{extra}{escena}, {estilo}, "
        "subject in the lower two thirds of the frame, generous empty space "
        "at the top and bottom for typography, vertical 4:5 composition, "
        "photorealistic, no text, no letters, no watermark, no logos"
    )


def _openai(deporte: str, variante: int = 0,
            tema: str = "") -> bytes | None:
    """OpenAI Images: gpt-image-1 y, si no está habilitado, dall-e-3."""
    for modelo, size in (("gpt-image-1", "1024x1536"),
                         ("dall-e-3", "1024x1792")):
        try:
            cuerpo = {"model": modelo,
                      "prompt": _prompt(deporte, variante, tema),
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


def _replicate(deporte: str, variante: int = 0,
               tema: str = "") -> bytes | None:
    """Replicate Flux (schnell): rápido y ~$0.003 por imagen."""
    try:
        cuerpo = {"input": {"prompt": _prompt(deporte, variante, tema),
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


def num_variantes() -> int:
    return len(_VARIACIONES)


def disponible() -> bool:
    return bool(config.OPENAI_API_KEY or config.REPLICATE_API_TOKEN)


_generando: set[str] = set()


def _clave(deporte: str, variante: int, tema: str = "") -> str:
    d = deporte if deporte in _ESCENA else "generico"
    base = f"{d}:{variante % len(_VARIACIONES)}"
    tema = (tema or "").strip()[:140]
    if not tema:
        return base  # clave histórica: el arte de marca ya persistido sirve
    h = hashlib.md5(tema.encode("utf-8")).hexdigest()[:8]
    return f"{base}:{h}"


def fondo_cacheado(deporte: str, variante: int = 0,
                   tema: str = "") -> Image.Image | None:
    """Solo el fondo YA cacheado (nunca bloquea). Para respuestas que deben
    ser inmediatas, p. ej. el og:image que baja el robot de WhatsApp."""
    return _cache.get(_clave(deporte, variante, tema))


def precalentar(deporte: str, variante: int = 0, tema: str = "") -> None:
    """Dispara la generación del fondo IA en un hilo (si falta) y retorna al
    instante: la siguiente petición ya lo encuentra en caché."""
    if not disponible():
        return
    k = _clave(deporte, variante, tema)
    if k in _cache or k in _generando:
        return
    _generando.add(k)

    def _correr():
        try:
            fondo_para(deporte, variante, tema)
        finally:
            _generando.discard(k)

    threading.Thread(target=_correr, daemon=True).start()


def fondo_para(deporte: str, variante: int = 0,
               tema: str = "") -> Image.Image | None:
    """Fondo IA para [deporte], [variante] y [tema] (cacheado + persistido).
    None = sin proveedor / falló → el afiche usa el gradiente de marca."""
    if not disponible():
        return None
    d = deporte if deporte in _ESCENA else "generico"
    v = variante % len(_VARIACIONES)
    k = _clave(deporte, v, tema)
    con = _cache.get(k)
    if con is not None:
        return con
    with _lock_de(k):
        con = _cache.get(k)  # ¿otro hilo la generó mientras esperaba?
        if con is not None:
            return con
        # 1) ¿Persistida en Storage de un deploy anterior? (gratis)
        durable = _storage_leer(k)
        if durable is not None:
            _cache[k] = durable
            return durable
        # 2) Generar con el proveedor y persistir para la próxima.
        crudo = (_openai(d, v, tema) if config.OPENAI_API_KEY
                 else _replicate(d, v, tema))
        if not crudo:
            return None
        try:
            img = Image.open(io.BytesIO(crudo)).convert("RGB")
        except Exception:
            return None
        _cache[k] = img
        _storage_guardar(k, img)
        return img
