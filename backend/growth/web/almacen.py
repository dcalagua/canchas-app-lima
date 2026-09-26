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


def url_publica(ruta: str, bucket: str = BUCKET) -> str:
    base = (config.SUPABASE_URL or "").rstrip("/")
    return f"{base}/storage/v1/object/public/{bucket}/{ruta}"


def prefijo_cancha(cancha_id: str) -> str:
    """URL pública bajo la que viven las fotos de ESTA cancha (para validar que
    una URL que manda el navegador es de verdad una foto subida aquí)."""
    return url_publica(f"{urllib.parse.quote(cancha_id, safe='')}/")


def prefijo_carpeta(carpeta: str, bucket: str = BUCKET) -> str:
    return url_publica(f"{urllib.parse.quote(carpeta, safe='')}/", bucket)


def subir(bucket: str, ruta: str, datos: bytes, content_type: str = "image/jpeg", *, max_bytes: int | None = None) -> str | None:
    """Sube (upsert) `datos` a `bucket/ruta` por la REST de Storage y devuelve
    la URL pública con `?v=` para saltar cachés (como el app). None si falló.
    `max_bytes` permite subir archivos grandes (videos de la biblioteca de marca)."""
    if not disponible() or not datos or len(datos) > (max_bytes or MAX_BYTES):
        return None
    ruta_q = "/".join(urllib.parse.quote(p, safe="") for p in ruta.split("/"))
    req = urllib.request.Request(
        f"{config.SUPABASE_URL.rstrip('/')}/storage/v1/object/{bucket}/{ruta_q}",
        data=datos, method="POST",
        headers={"apikey": config.SUPABASE_ANON_KEY,
                 "Authorization": f"Bearer {config.SUPABASE_ANON_KEY}",
                 "Content-Type": content_type or "image/jpeg",
                 "x-upsert": "true"})
    try:
        with urllib.request.urlopen(req, timeout=max(30, len(datos) // 200_000)) as r:  # noqa: S310
            r.read()
    except urllib.error.HTTPError as e:
        print(f"[foto-web] subida rechazada {e.code} {bucket}/{ruta}", flush=True)
        return None
    except Exception as e:  # noqa: BLE001
        print(f"[foto-web] subida falló {bucket}/{ruta}: {e}", flush=True)
        return None
    return f"{url_publica(ruta_q, bucket)}?v={int(time.time() * 1000)}"


def subir_foto(cancha_id: str, datos: bytes, content_type: str = "image/jpeg") -> str | None:
    """Foto de cancha: `canchas/<id>/web_<epoch_ms>.jpg` (misma carpeta que el app)."""
    return subir(BUCKET, f"{cancha_id}/web_{int(time.time() * 1000)}.jpg", datos, content_type) if cancha_id else None


def borrar_foto(url: str) -> bool:
    """Borra del bucket la foto de una URL pública NUESTRA (el dueño la quitó
    de la galería). URLs ajenas (Google, otro bucket) se ignoran."""
    if not disponible():
        return False
    raiz = f"{config.SUPABASE_URL.rstrip('/')}/storage/v1/object/public/"
    if not url.startswith(raiz):
        return False
    resto = url[len(raiz):].split("?", 1)[0]
    bucket, _, ruta = resto.partition("/")
    if bucket not in ("canchas", "productos") or not ruta or ".." in ruta:
        return False
    req = urllib.request.Request(
        f"{config.SUPABASE_URL.rstrip('/')}/storage/v1/object/{bucket}/{ruta}",
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
