"""SEO (plan de mejoras ronda 2, P2-7): `/sitemap.xml` con las páginas
públicas que valen la pena indexar — portada, ayuda, legales, cada ficha de
cancha aprobada, cada academia visible y las páginas por deporte y zona
(`/canchas/{deporte}/{zona}`). `robots.txt` (main.py) lo anuncia."""

from __future__ import annotations

from xml.sax.saxutils import escape

from fastapi import APIRouter, Request
from fastapi.responses import Response

import config
from web import datos

router = APIRouter()

_FIJAS = ["/", "/tenis", "/ayuda", "/buscar", "/marketplace", "/libro-de-reclamaciones",
          "/legal/terminos", "/legal/privacidad", "/legal/devoluciones"]


def base_url(request: Request | None = None) -> str:
    b = (getattr(config, "PUBLIC_BASE_URL", "") or "").rstrip("/")
    if b:
        return b
    return str(request.base_url).rstrip("/") if request is not None else ""


def rutas() -> list[str]:
    from web import router as wr
    out = list(_FIJAS)
    out += [f"/reservar/{c['id']}" for c in datos.canchas_publicas() if datos.reservable(c)]
    try:
        import academia_plan as _ap
        out += [f"/academia/{a['id']}" for a in datos.academias_publicas() if _ap.habilitada(a)]
    except Exception:  # noqa: BLE001
        pass
    out += wr.paginas_zona()
    return list(dict.fromkeys(out))


@router.get("/sitemap.xml", include_in_schema=False)
def sitemap(request: Request) -> Response:
    b = base_url(request)
    urls = "".join(f"<url><loc>{escape(b + r)}</loc></url>" for r in rutas())
    xml = f"<?xml version='1.0' encoding='UTF-8'?><urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>{urls}</urlset>"
    return Response(xml, media_type="application/xml", headers={"Cache-Control": "public, max-age=3600"})


@router.get("/manifest.webmanifest", include_in_schema=False)
def manifest(request: Request) -> Response:
    """Manifiesto de la web instalable (PWA): nombre, colores y el logo de la
    torre (`/marca/logo.png`, 512 px). Sin service worker: la web necesita
    conexión, igual que reservar."""
    import json
    from config import MARCA
    from web import ui
    logo = ui._logo_url()
    m = {"name": MARCA, "short_name": MARCA, "start_url": "/?origen=app", "scope": "/", "display": "standalone",
         "background_color": "#FFFFFF", "theme_color": "#0F1B2D", "lang": "es",
         "description": "Reserva canchas, juega y paga en línea.",
         "icons": [{"src": logo, "sizes": "512x512", "type": "image/png", "purpose": "any"},
                   {"src": logo, "sizes": "192x192", "type": "image/png", "purpose": "any"}]}
    return Response(json.dumps(m, ensure_ascii=False), media_type="application/manifest+json",
                    headers={"Cache-Control": "public, max-age=86400"})
