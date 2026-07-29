"""Previsualización de enlaces (Open Graph) para los posts de los Canales.

Baja la página del enlace en el servidor (maneja redirecciones tipo acortar.link),
lee los metadatos Open Graph (`og:title`, `og:description`, `og:image`) con caída a
`<title>` / `<meta name=description>`, y devuelve una tarjeta lista para pintar en
la app (título + descripción + imagen + dominio). Cachea en memoria para no volver a
bajar el mismo enlace en cada render.

Fail-safe: cualquier error (timeout, sin OG, no es HTML) devuelve una tarjeta vacía
(`ok=False`) y la app simplemente no muestra el preview.
"""

from __future__ import annotations

import html as html_mod
import re
import urllib.request
from urllib.parse import urljoin, urlparse

# Caché en memoria: url -> dict. Se limita el tamaño para no crecer sin freno.
_CACHE: dict[str, dict] = {}
_CACHE_MAX = 500

_TIMEOUT = 8  # segundos
_MAX_BYTES = 300_000  # solo leemos el <head> (los OG viven arriba)
_UA = ("Mozilla/5.0 (compatible; PichangolBot/1.0; +https://www.pichangol.app)")


def _meta(html: str, clave: str) -> str:
    """Extrae el content de un <meta property/name="clave">, en cualquier orden."""
    c = re.escape(clave)
    patrones = [
        r'<meta[^>]+(?:property|name)=["\']%s["\'][^>]*content=["\']([^"\']*)["\']' % c,
        r'<meta[^>]+content=["\']([^"\']*)["\'][^>]*(?:property|name)=["\']%s["\']' % c,
    ]
    for p in patrones:
        m = re.search(p, html, re.IGNORECASE)
        if m:
            return html_mod.unescape(m.group(1)).strip()
    return ""


def _titulo_tag(html: str) -> str:
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    return html_mod.unescape(m.group(1)).strip() if m else ""


def _dominio(url: str) -> str:
    try:
        net = urlparse(url).netloc.lower()
        return net[4:] if net.startswith("www.") else net
    except Exception:  # noqa: BLE001
        return ""


def _bajar(url: str) -> tuple[str, str]:
    """Devuelve (html, url_final) siguiendo redirecciones. Solo si es HTML."""
    req = urllib.request.Request(url, headers={"User-Agent": _UA,
                                               "Accept": "text/html,*/*"})
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:  # nosec B310
        ctype = (resp.headers.get("Content-Type") or "").lower()
        if "html" not in ctype and ctype:
            return "", resp.geturl()
        raw = resp.read(_MAX_BYTES)
        final = resp.geturl()
    # Detecta charset básico; si falla, utf-8 con reemplazo.
    try:
        return raw.decode("utf-8", "replace"), final
    except Exception:  # noqa: BLE001
        return raw.decode("latin-1", "replace"), final


def obtener(url: str) -> dict:
    """Tarjeta de preview del enlace. Nunca lanza."""
    url = (url or "").strip()
    if not url:
        return {"ok": False}
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    if url in _CACHE:
        return _CACHE[url]

    data = {"ok": False, "url": url, "domain": _dominio(url)}
    try:
        html, final = _bajar(url)
        if html:
            titulo = _meta(html, "og:title") or _titulo_tag(html)
            desc = _meta(html, "og:description") or _meta(html, "description")
            img = _meta(html, "og:image") or _meta(html, "og:image:url")
            if img:
                img = urljoin(final, img)  # resuelve rutas relativas
            dominio = _dominio(final) or _dominio(url)
            if titulo or img:
                data = {
                    "ok": True,
                    "url": final,
                    "title": titulo[:200],
                    "description": desc[:300],
                    "image": img,
                    "domain": dominio,
                }
    except Exception:  # noqa: BLE001 — fail-safe: tarjeta vacía
        pass

    # Cachea (con tope): así el mismo enlace no se vuelve a bajar en cada render.
    if len(_CACHE) >= _CACHE_MAX:
        _CACHE.clear()
    _CACHE[url] = data
    return data
