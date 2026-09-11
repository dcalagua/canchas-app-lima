"""Supabase Storage desde el backend (fotos de canchas subidas desde la web).

Habla con el MISMO bucket público `canchas` que usa el APK (`CanchasRepo.
subirFoto`: ruta `<canchaId>/<sufijo>.jpg`, upsert) vía la API REST de
Storage con la llave anon (`SUPABASE_URL` + `SUPABASE_ANON_KEY`, las mismas
policies que el app). Sin esas envs → None y la web avisa (fail-safe).
"""

from __future__ import annotations

import time
import urllib.error
import urllib.parse
import urllib.request

import config

BUCKET = "canchas"
MAX_BYTES = 6 * 1024 * 1024  # una foto ya comprimida en el navegador pesa <1 MB


def disponible() -> bool:
    return bool(config.SUPABASE_URL and config.SUPABASE_ANON_KEY)


def url_publica(ruta: str) -> str:
    base = (config.SUPABASE_URL or "").rstrip("/")
    return f"{base}/storage/v1/object/public/{BUCKET}/{ruta}"


def prefijo_cancha(cancha_id: str) -> str:
    """URL pública bajo la que viven las fotos de ESTA cancha (para validar que
    una URL que manda el navegador es de verdad una foto subida aquí)."""
    return url_publica(f"{urllib.parse.quote(cancha_id, safe='')}/")


def subir_foto(cancha_id: str, datos: bytes, content_type: str = "image/jpeg") -> str | None:
    """Sube la foto a `canchas/<id>/web_<epoch_ms>.jpg` y devuelve su URL
    pública (con `?v=` para saltar cachés, como el app). None si falló."""
    if not disponible() or not datos or len(datos) > MAX_BYTES:
        return None
    sufijo = f"web_{int(time.time() * 1000)}"
    ruta = f"{urllib.parse.quote(cancha_id, safe='')}/{sufijo}.jpg"
    req = urllib.request.Request(
        f"{config.SUPABASE_URL.rstrip('/')}/storage/v1/object/{BUCKET}/{ruta}",
        data=datos, method="POST",
        headers={"apikey": config.SUPABASE_ANON_KEY,
                 "Authorization": f"Bearer {config.SUPABASE_ANON_KEY}",
                 "Content-Type": content_type or "image/jpeg",
                 "x-upsert": "true"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310
            r.read()
    except urllib.error.HTTPError as e:
        print(f"[foto-web] subida rechazada {e.code} cancha={cancha_id}", flush=True)
        return None
    except Exception as e:  # noqa: BLE001
        print(f"[foto-web] subida falló: {e}", flush=True)
        return None
    return f"{url_publica(ruta)}?v={int(time.time() * 1000)}"


def borrar_foto(url: str) -> bool:
    """Borra del bucket la foto de una URL pública NUESTRA (el dueño la quitó
    de la galería). URLs ajenas (Google, otro bucket) se ignoran."""
    if not disponible():
        return False
    base = url_publica("")
    if not url.startswith(base):
        return False
    ruta = url[len(base):].split("?", 1)[0]
    if not ruta or ".." in ruta:
        return False
    req = urllib.request.Request(
        f"{config.SUPABASE_URL.rstrip('/')}/storage/v1/object/{BUCKET}/{ruta}",
        method="DELETE",
        headers={"apikey": config.SUPABASE_ANON_KEY,
                 "Authorization": f"Bearer {config.SUPABASE_ANON_KEY}"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:  # noqa: S310
            r.read()
        return True
    except urllib.error.HTTPError as e:
        return e.code == 404
    except Exception:  # noqa: BLE001
        return False
