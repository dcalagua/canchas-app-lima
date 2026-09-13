"""SESIÓN WEB con Google (mismo flujo que el APK: "inicia sesión con tu Gmail
para reservar", decisión del director sep-2026).

- El navegador obtiene un ID token con Google Identity Services (botón
  "Iniciar sesión con Google", `GOOGLE_WEB_CLIENT_ID`).
- `POST /web/sesion` lo verifica contra Google (tokeninfo, sin dependencias
  de crypto) exigiendo que la audiencia sea NUESTRO client id, y deja una
  cookie httpOnly FIRMADA (HMAC con el secreto del backend) con correo,
  nombre y foto por 30 días. Nada del token de Google se guarda.
- Reservar (`/web/asegurar`, `/web/pagar`) exige la cookie: la reserva queda a
  nombre del CORREO de Google, así el jugador la ve en "Mis reservas" del app
  con la misma cuenta, y el dueño ve al mismo usuario.

Sin `GOOGLE_WEB_CLIENT_ID` configurado, `activo()` es False y la web sigue con
el formulario de invitado (nombre + correo) para no romper el flujo antes de
crear el client id.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import urllib.parse
import urllib.request

from fastapi import Request, Response

import config

COOKIE = "pcg_sesion"
DIAS = 30


def activo() -> bool:
    return bool(config.GOOGLE_WEB_CLIENT_ID)


def _secreto() -> bytes:
    return (config.ADMIN_PANEL_TOKEN or config.APP_API_KEY or "pichangol-web").encode()


def _firmar(cuerpo: bytes) -> str:
    return hmac.new(_secreto(), cuerpo, hashlib.sha256).hexdigest()[:40]


def emitir(datos: dict) -> str:
    """Valor de cookie: base64url(json) + '.' + HMAC. Incluye `exp`."""
    d = {"email": (datos.get("email") or "").strip().lower()[:120],
         "nombre": (datos.get("nombre") or "").strip()[:80],
         "foto": (datos.get("foto") or "").strip()[:300],
         "exp": int(time.time()) + DIAS * 24 * 3600}
    cuerpo = base64.urlsafe_b64encode(json.dumps(d, separators=(",", ":")).encode()).decode().rstrip("=")
    return f"{cuerpo}.{_firmar(cuerpo.encode())}"


def leer(valor: str | None) -> dict | None:
    """Sesión válida (dict con email/nombre/foto) o None."""
    if not valor or "." not in valor:
        return None
    cuerpo, firma = valor.rsplit(".", 1)
    if not hmac.compare_digest(_firmar(cuerpo.encode()), firma):
        return None
    try:
        pad = "=" * (-len(cuerpo) % 4)
        d = json.loads(base64.urlsafe_b64decode(cuerpo + pad).decode())
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(d, dict) or int(d.get("exp", 0)) < time.time() or "@" not in str(d.get("email", "")):
        return None
    return {"email": d["email"], "nombre": d.get("nombre") or "", "foto": d.get("foto") or ""}


def de_request(request: Request | None) -> dict | None:
    if request is None:
        return None
    try:
        return leer(request.cookies.get(COOKIE))
    except Exception:  # noqa: BLE001
        return None


def poner_cookie(response: Response, valor: str) -> None:
    response.set_cookie(COOKIE, valor, max_age=DIAS * 24 * 3600, httponly=True, secure=True,
                        samesite="lax", path="/")


def borrar_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE, path="/")


def _tokeninfo(token: str) -> dict:
    q = urllib.parse.urlencode({"id_token": token})
    with urllib.request.urlopen(f"https://oauth2.googleapis.com/tokeninfo?{q}", timeout=8) as r:  # noqa: S310
        return json.loads(r.read().decode("utf-8"))


def verificar_id_token(token: str) -> dict | None:
    """Verifica el ID token de Google del navegador. Devuelve
    {email, nombre, foto} o None. Exige correo verificado y audiencia =
    `GOOGLE_WEB_CLIENT_ID` (o uno de `GOOGLE_OAUTH_CLIENT_IDS`)."""
    token = (token or "").strip()
    if not token or not activo():
        return None
    try:
        info = _tokeninfo(token)
    except Exception:  # noqa: BLE001
        return None
    email = (info.get("email") or "").strip().lower()
    if not email or str(info.get("email_verified")).lower() not in ("true", "1"):
        return None
    permitidos = {config.GOOGLE_WEB_CLIENT_ID} | {
        a.strip() for a in (config.GOOGLE_OAUTH_CLIENT_IDS or "").split(",") if a.strip()}
    if info.get("aud") not in permitidos:
        return None
    try:
        if int(info.get("exp", 0)) < time.time():
            return None
    except (TypeError, ValueError):
        return None
    return {"email": email, "nombre": (info.get("name") or "").strip(),
            "foto": (info.get("picture") or "").strip()}


def boton_google(callback: str = "onGoogleCred") -> str:
    """HTML del botón oficial de Google (Google Identity Services)."""
    if not activo():
        return ""
    return (f"<div id='g_id_onload' data-client_id='{config.GOOGLE_WEB_CLIENT_ID}' data-callback='{callback}' "
            "data-auto_prompt='false' data-ux_mode='popup' data-context='signin'></div>"
            "<div class='g_id_signin' data-type='standard' data-shape='pill' data-theme='outline' "
            "data-text='signin_with' data-size='large' data-locale='es' data-logo_alignment='left'></div>")


GIS_SCRIPT = "<script src='https://accounts.google.com/gsi/client' async defer></script>"

# JS común: recibe la credencial del botón y abre la sesión en el backend.
JS_SESION = r"""
window.onGoogleCred = function(resp){
  fetch('/web/sesion', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({credential: resp.credential})})
    .then(function(r){ return r.json(); })
    .then(function(j){ if(j && j.ok){ if(window.alIniciarSesion) window.alIniciarSesion(j); else location.reload(); }
      else { var el = document.getElementById('sesionErr'); if(el){ el.textContent = 'No pudimos iniciar tu sesión. Inténtalo de nuevo.'; el.style.display = 'block'; } } })
    .catch(function(){ var el = document.getElementById('sesionErr'); if(el){ el.textContent = 'Sin conexión. Inténtalo de nuevo.'; el.style.display = 'block'; } });
};
window.cerrarSesion = function(){ fetch('/web/salir', {method:'POST'}).then(function(){ location.reload(); }); };
"""
