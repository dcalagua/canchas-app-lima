"""Rendimiento y seguridad de la WEB pública (plan nocturno web, fase W3).

- **Estáticos versionados**: el CSS del sistema de diseño (`ui.CSS`, ~70 KB)
  y el JS de navegación (`ui.JS_NAV`) se sirven como archivos con su huella
  en el nombre y caché inmutable de un año, en vez de repetirse dentro de cada
  página. Cambiar el CSS cambia la huella: nunca se sirve uno viejo.
- **Compresión** gzip de todo lo que pase de 1 KB.
- **Cabeceras**: `X-Frame-Options: SAMEORIGIN` en las páginas HTML (antes las
  de pago se podían meter en un iframe ajeno → clickjacking) y una CSP en modo
  SOLO REPORTE con los dominios reales (Culqi, Google, unpkg, Supabase…): no
  bloquea nada; lo que la violaría se anota en los logs (`[csp]`) para poder
  pasarla a modo bloqueo con datos.
- **CSRF**: un POST/PUT/DELETE que trae la cookie de sesión web desde OTRO
  sitio (`Sec-Fetch-Site: cross-site` u `Origin` ajeno) se rechaza con 403.
  Los webhooks y callbacks de pasarelas no traen esa cookie: no se tocan.
- **Límite por IP real** (último valor de `X-Forwarded-For`, el que pone el
  proxy de Railway) en los endpoints que gastan cuota de Google o reciben
  archivos/apartados.
"""

from __future__ import annotations

import hashlib
import threading
import time
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

import config

# ── estáticos versionados ────────────────────────────────────────────────────

_cache: dict[str, tuple[str, str]] = {}


def _asset(nombre: str) -> tuple[str, str]:
    """(huella, contenido) del asset, calculado una vez por proceso."""
    if nombre not in _cache:
        from web import ui
        texto = ui.CSS if nombre == "estilo" else ui.JS_NAV
        _cache[nombre] = (hashlib.sha1(texto.encode()).hexdigest()[:12], texto)
    return _cache[nombre]


def url_css() -> str:
    return f"/web/a/estilo.{_asset('estilo')[0]}.css"


def url_nav() -> str:
    return f"/web/a/nav.{_asset('nav')[0]}.js"


# ── límites por IP ───────────────────────────────────────────────────────────

# ruta (prefijo) → (peticiones, ventana en segundos)
LIMITES: dict[str, tuple[int, int]] = {
    "/web/lugares": (30, 60),
    "/web/descubrir": (30, 60),
    "/web/foto": (120, 60),
    "/web/voucher": (10, 60),
    "/web/asegurar": (20, 60),
    "/web/sesion/prueba": (10, 60),
    "/web/csp-reporte": (30, 60),
}
_golpes: dict[tuple[str, str], list[float]] = {}
_lock = threading.Lock()


def ip_real(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[-1].strip()[:64] or "?"
    return (request.client.host if request.client else "?")[:64]


def _limite_de(ruta: str) -> tuple[str, tuple[int, int]] | None:
    for pref, lim in LIMITES.items():
        if ruta == pref or ruta.startswith(pref + "/") or ruta.startswith(pref + "?"):
            return pref, lim
    return None


ACTIVO = True   # la suite de tests lo apaga (todas sus peticiones salen de la misma IP)


def excede(ruta: str, ip: str) -> bool:
    if not ACTIVO:
        return False
    hit = _limite_de(ruta)
    if not hit:
        return False
    pref, (n, ventana) = hit
    ahora = time.time()
    with _lock:
        if len(_golpes) > 20000:   # memoria acotada
            _golpes.clear()
        lista = [t for t in _golpes.get((pref, ip), []) if ahora - t < ventana]
        if len(lista) >= n:
            _golpes[(pref, ip)] = lista
            return True
        lista.append(ahora)
        _golpes[(pref, ip)] = lista
    return False


# ── CSRF ─────────────────────────────────────────────────────────────────────

def _hosts_propios(request: Request) -> set[str]:
    hosts = {(request.headers.get("host") or "").split(":")[0].lower()}
    for u in (getattr(config, "PUBLIC_BASE_URL", ""), getattr(config, "MARCA_URL", ""),
              getattr(config, "LANDING_BASE_URL", "")):
        h = (urlparse(u).hostname or "").lower() if u else ""
        if h:
            hosts.add(h)
    return {h for h in hosts if h}


def es_csrf(request: Request) -> bool:
    """¿Una escritura con la cookie de sesión web que viene de otro sitio?"""
    if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
        return False
    from web import sesion
    if sesion.COOKIE not in request.cookies:
        return False
    if (request.headers.get("sec-fetch-site") or "").lower() == "cross-site":
        return True
    origen = request.headers.get("origin") or ""
    if origen and origen != "null":
        return (urlparse(origen).hostname or "").lower() not in _hosts_propios(request)
    return False


# ── CSP (solo reporte) ───────────────────────────────────────────────────────

CSP = ("default-src 'self'; "
       "script-src 'self' 'unsafe-inline' https://checkout.culqi.com https://js.culqi.com https://*.culqi.com "
       "https://unpkg.com https://accounts.google.com https://apis.google.com https://www.gstatic.com; "
       "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://unpkg.com https://accounts.google.com; "
       "font-src 'self' data: https://fonts.gstatic.com; "
       "img-src 'self' data: blob: https:; media-src 'self' blob: https:; "
       "connect-src 'self' https:; "
       "frame-src 'self' https://*.culqi.com https://accounts.google.com https://www.youtube.com https://www.google.com; "
       "frame-ancestors 'self'; form-action 'self' https:; base-uri 'self'; "
       "report-uri /web/csp-reporte")

_csp_vistos: dict[str, float] = {}


def instalar(app: FastAPI) -> None:
    from starlette.middleware.gzip import GZipMiddleware

    @app.get("/web/a/{archivo}", include_in_schema=False)
    def asset(archivo: str) -> Response:
        nombre, _, resto = archivo.partition(".")
        if nombre not in ("estilo", "nav"):
            return Response("No encontrado", status_code=404)
        huella, texto = _asset(nombre)
        tipo = "text/css" if nombre == "estilo" else "application/javascript"
        # Una huella vieja (página en caché del navegador) recibe el contenido
        # actual sin caché larga: nunca se queda sin estilos.
        cache = "public, max-age=31536000, immutable" if resto.startswith(huella + ".") else "no-cache"
        return Response(texto, media_type=f"{tipo}; charset=utf-8", headers={"Cache-Control": cache})

    @app.post("/web/csp-reporte", include_in_schema=False)
    async def csp_reporte(request: Request) -> Response:
        try:
            cuerpo = (await request.body())[:2000].decode("utf-8", "replace")
        except Exception:  # noqa: BLE001
            cuerpo = ""
        clave = cuerpo[:300]
        ahora = time.time()
        if ahora - _csp_vistos.get(clave, 0) > 3600:   # una vez por hora por violación
            _csp_vistos[clave] = ahora
            if len(_csp_vistos) > 500:
                _csp_vistos.clear()
            print(f"[csp] {cuerpo[:600]}", flush=True)
        return Response(status_code=204)

    @app.middleware("http")
    async def _seguridad(request: Request, call_next):
        ruta = request.url.path
        if es_csrf(request):
            print(f"[csrf] bloqueado {request.method} {ruta} origen={request.headers.get('origin')!r}", flush=True)
            return JSONResponse({"ok": False, "error": "origen_no_permitido"}, status_code=403)
        if excede(ruta, ip_real(request)):
            return JSONResponse({"ok": False, "error": "demasiadas_solicitudes",
                                 "mensaje": "Vas muy rápido. Espera un momento e inténtalo de nuevo."},
                                status_code=429, headers={"Retry-After": "30"})
        response = await call_next(request)
        if (response.headers.get("content-type") or "").startswith("text/html") and not ruta.startswith("/admin"):
            response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
            response.headers.setdefault("Content-Security-Policy-Report-Only", CSP)
        return response

    app.add_middleware(GZipMiddleware, minimum_size=1024)
