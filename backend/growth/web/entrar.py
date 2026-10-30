"""SESIÓN CON GOOGLE en la web (mismo flujo que el APK): `POST /web/sesion`,
el acceso de revisión con usuario y contraseña `POST /web/sesion/prueba`,
`POST /web/salir`, `GET /web/sesion` y la página `GET /entrar?volver=`.

Movido tal cual desde `web/router.py`, que lo re-exporta.
"""

from __future__ import annotations

import time

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel

from web import datos, sesion, ui
from web.ui import e
from config import MARCA  # noqa: E402 — nombre y dominio de marca (un solo lugar)

router = APIRouter()


# ── sesión con Google (mismo flujo que el APK) ────────────────────────────────

class SesionReq(BaseModel):
    credential: str


@router.post("/web/sesion")
def abrir_sesion(req: SesionReq, response: Response) -> dict:
    """Recibe el ID token del botón de Google, lo verifica y deja la cookie
    firmada de sesión (30 días). Sin `GOOGLE_WEB_CLIENT_ID` → no disponible."""
    if not sesion.activo():
        return {"ok": False, "error": "no_configurado"}
    u = sesion.verificar_id_token(req.credential)
    if not u:
        return {"ok": False, "error": "token_invalido"}
    sesion.poner_cookie(response, sesion.emitir(u))
    # Celular del perfil (el mismo del app) para prellenar "Tus datos".
    return {"ok": True, **u, "celular": datos.celular_de_perfil(u.get("email", ""))}


class SesionPruebaReq(BaseModel):
    usuario: str
    clave: str


_revision_intentos: dict[str, tuple[int, float]] = {}   # ip -> (fallos, bloqueado_hasta)


@router.post("/web/sesion/prueba")
def abrir_sesion_prueba(req: SesionPruebaReq, request: Request, response: Response) -> dict:
    """Acceso de REVISIÓN (Culqi/INDECOPI): usuario + contraseña de
    `WEB_USUARIOS_PRUEBA` → la misma cookie firmada que el login con Google, así
    el revisor reserva, paga y ve el comprobante como un cliente. Anti fuerza
    bruta por IP real (5 fallos → 5 min)."""
    if not sesion.revision_activa():
        return {"ok": False, "error": "no_configurado"}
    xff = request.headers.get("x-forwarded-for", "")
    ip = (xff.split(",")[0].strip() if xff else (request.client.host if request.client else "?"))[:64]
    fallos, hasta = _revision_intentos.get(ip, (0, 0.0))
    if time.time() < hasta:
        return {"ok": False, "error": "demasiados_intentos"}
    if not sesion.credenciales_prueba_validas(req.usuario, req.clave):
        fallos += 1
        _revision_intentos[ip] = (0, time.time() + 300) if fallos >= 5 else (fallos, 0.0)
        print(f"[web] acceso de revisión fallido usuario={req.usuario!r} ip={ip}", flush=True)
        return {"ok": False, "error": "credenciales_invalidas"}
    _revision_intentos.pop(ip, None)
    u = {"email": req.usuario.strip().lower(), "nombre": "Cuenta de revisión", "foto": ""}
    sesion.poner_cookie(response, sesion.emitir(u))
    print(f"[web] acceso de revisión OK usuario={u['email']} ip={ip}", flush=True)
    return {"ok": True, **u}


@router.post("/web/salir")
def cerrar_sesion(response: Response) -> dict:
    sesion.borrar_cookie(response)
    return {"ok": True}


@router.get("/web/sesion")
def ver_sesion(request: Request) -> dict:
    u = sesion.de_request(request)
    return {"ok": True, "activo": sesion.activo(), "sesion": u}


# Título de /entrar según a dónde vuelve (antes siempre decía "para reservar").
_MOTIVOS_ENTRAR = [
    ("/anfitrion", "Inicia sesión para entrar al modo anfitrión",
     "Usa la cuenta de Google con la que registraste tu cancha o academia."),
    ("/mis-reservas", "Inicia sesión para ver tus reservas", ""),
    ("/partidos", "Inicia sesión para jugar", "Busca partido, organiza el tuyo o encuentra partner cerca."),
    ("/pichangas", "Inicia sesión para jugar", "Únete a las pichangas de tu club."),
    ("/liga", "Inicia sesión para entrar a la liga", "Ranking por nivel, retos y temporadas."),
    ("/mensajes", "Inicia sesión para ver tus mensajes", ""),
    ("/mi-billetera", "Inicia sesión para ver tu billetera", ""),
    ("/perfil", "Inicia sesión", ""),
    ("/torneo", "Inicia sesión para inscribirte", ""),
    ("/academia", "Inicia sesión para matricularte", ""),
]


def _motivo_entrar(volver: str) -> tuple[str, str]:
    base = ("Usa tu cuenta de Google, la misma del app: tus reservas quedan en "
            "\"Mis reservas\" y el comprobante llega a tu correo.")
    for pref, titulo, sub in _MOTIVOS_ENTRAR:
        if volver == pref or volver.startswith(pref + "/") or volver.startswith(pref + "?"):
            if "Google" in sub:
                return titulo, sub
            return titulo, (sub + " " if sub else "") + "Usa tu cuenta de Google, la misma del app."
    return "Inicia sesión para reservar", base


def _volver_seguro(volver: str) -> str:
    v = (volver or "").strip()
    return v if v.startswith("/") and not v.startswith("//") else "/"


@router.get("/entrar", response_class=HTMLResponse)
def pagina_entrar(request: Request, volver: str = "/") -> HTMLResponse:
    """Inicio de sesión con Google (como en el app). Al entrar vuelve a la
    página desde la que se pidió (`volver`)."""
    v = _volver_seguro(volver)
    ses = sesion.de_request(request)
    if ses or not sesion.activo():
        return HTMLResponse("", status_code=302, headers={"Location": v})
    titulo, sub = _motivo_entrar(v)
    cuerpo = ("<div class='panel' style='max-width:460px;margin:40px auto;text-align:center'>"
              f"<div style='margin-bottom:8px'>{ui.wordmark(26, '/')}</div>"
              f"<h1 style='font-size:22px'>{e(titulo)}</h1>"
              f"<p class='sub'>{e(sub)}</p>"
              f"<div style='display:flex;justify-content:center;margin:22px 0 10px'>{sesion.boton_google()}</div>"
              "<div class='estado bad' id='sesionErr'></div>"
              "<p class='sub' style='font-size:12.5px'>Al continuar aceptas los <a href='/legal/terminos'>términos</a> y la "
              "<a href='/legal/privacidad'>política de privacidad</a>.</p>"
              + (("<div id='revision' style='margin-top:18px;padding-top:16px;border-top:1px solid #eee;text-align:left'>"
                  "<b style='font-size:14px'>Acceso de revisión</b>"
                  f"<div class='sub' style='font-size:12.5px;margin:2px 0 10px'>Para revisores (Culqi, INDECOPI): usa el usuario y la contraseña que te entregó {MARCA}.</div>"
                  "<label for='revUsr' style='font-size:12.5px;font-weight:700'>Usuario</label>"
                  "<input id='revUsr' autocomplete='username' maxlength='120' style='width:100%;margin:4px 0 10px'>"
                  "<label for='revPwd' style='font-size:12.5px;font-weight:700'>Contraseña</label>"
                  "<input id='revPwd' type='password' autocomplete='current-password' maxlength='120' style='width:100%;margin:4px 0 12px'>"
                  "<button type='button' class='btn' style='width:100%' onclick='entrarRevision()'>Entrar como revisor</button>"
                  "<div class='estado bad' id='revErr'></div></div>") if sesion.revision_activa() else "")
              + "</div>"
              f"<script>window.alIniciarSesion=function(){{location.href={ui.json_js(v)};}};{sesion.JS_SESION}"
              "window.entrarRevision=function(){var u=document.getElementById('revUsr').value.trim(),c=document.getElementById('revPwd').value,er=document.getElementById('revErr');er.textContent='';"
              "fetch('/web/sesion/prueba',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({usuario:u,clave:c})}).then(function(r){return r.json();})"
              ".then(function(j){if(j&&j.ok){window.alIniciarSesion(j);}else{er.textContent=j&&j.error==='demasiados_intentos'?'Demasiados intentos. Espera 5 minutos.':'Usuario o contraseña incorrectos.';er.style.display='block';}})"
              ".catch(function(){er.textContent='Sin conexión. Inténtalo de nuevo.';er.style.display='block';});};"
              "var rp=document.getElementById('revPwd');if(rp)rp.addEventListener('keydown',function(e){if(e.key==='Enter')entrarRevision();});</script>")
    return ui.shell("Iniciar sesión", cuerpo, extra_head=sesion.GIS_SCRIPT, sesion=None)
