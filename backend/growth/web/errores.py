"""Páginas de error con la marca para quien navega (revisión de QAS,
29-oct-2026: una URL inexistente mostraba `{"detail":"Not Found"}`).

Solo cambia la respuesta cuando la pide un NAVEGADOR (GET que acepta
text/html) y la ruta no es de API: el APK, los webhooks y los `fetch` de la
web siguen recibiendo el JSON de siempre."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from starlette.exceptions import HTTPException as StarletteHTTPException

from config import MARCA

# Prefijos que son API (JSON) aunque se abran en el navegador.
_API = ("/web/", "/pagos/", "/admin", "/propiedad/", "/config/", "/negocio/", "/boleadores/", "/fidelidad/",
        "/juego/", "/referidos/", "/academias/", "/reservas/", "/club/", "/puntos/", "/static/", "/.well-known/")


def es_navegador(request: Request) -> bool:
    return (request.method in ("GET", "HEAD") and "text/html" in (request.headers.get("accept") or "")
            and not request.url.path.startswith(_API))


def pagina(titulo: str, texto: str, codigo: int):
    from web import ui
    cuerpo = ("<div class='panel' style='max-width:560px;margin:40px auto;text-align:center'>"
              f"<div style='font-size:56px;line-height:1'>{'🥅' if codigo == 404 else '🛠️'}</div>"
              f"<h1 style='margin-top:10px'>{ui.e(titulo)}</h1><p class='sub'>{ui.e(texto)}</p>"
              "<div class='acciones' style='justify-content:center;margin-top:16px'>"
              "<a class='btn' href='/'>Ver canchas</a><a class='btn sec' href='/mis-reservas'>Mis reservas</a></div></div>")
    try:
        r = ui.shell(titulo, cuerpo, titulo_tab=f"{titulo} · {MARCA}")
    except Exception:  # noqa: BLE001 — si hasta el shell falla, texto plano
        from fastapi.responses import HTMLResponse
        r = HTMLResponse(f"<h1>{titulo}</h1><p>{texto}</p><a href='/'>Volver al inicio</a>")
    r.status_code = codigo
    return r


def instalar(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException):
        if exc.status_code == 404 and es_navegador(request):
            return pagina("No encontramos esta página", "El enlace puede estar mal escrito o la página ya no existe. "
                          "Sigue buscando tu cancha desde el inicio.", 404)
        return await http_exception_handler(request, exc)

    @app.exception_handler(Exception)
    async def _error(request: Request, exc: Exception):
        print(f"[error] {request.method} {request.url.path}: {type(exc).__name__}: {str(exc)[:200]}", flush=True)
        if es_navegador(request):
            return pagina("Algo salió mal", "Tuvimos un problema al cargar esta página. Inténtalo de nuevo en un momento.", 500)
        from fastapi.responses import JSONResponse
        return JSONResponse({"ok": False, "error": "error_interno"}, status_code=500)
