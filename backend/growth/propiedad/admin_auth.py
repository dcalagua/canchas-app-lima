"""Autenticación de la TORRE DE CONTROL (/admin) por usuario + contraseña.

Los operadores se configuran en la env `ADMIN_PANEL_USUARIOS` con el formato
"correo:clave" separados por coma, p. ej.:

    ADMIN_PANEL_USUARIOS="dcalagua@ebim.pe:MiClaveSegura, soporte@ebim.pe:Otra"

El login (`POST /admin/api/login`) valida las credenciales y emite una SESIÓN
FIRMADA con expiración (HMAC-SHA256 con `ADMIN_PANEL_TOKEN` como llave de
firma). Esa sesión viaja en la cabecera `X-Admin-Token` igual que antes, así
todos los endpoints admin existentes siguen funcionando sin cambios.

Compatibilidad: el token clásico `ADMIN_PANEL_TOKEN` sigue siendo aceptado
(scripts/ops y respaldo si aún no se configuran usuarios). Fail-closed: sin
`ADMIN_PANEL_TOKEN` no hay firma posible y todo el panel responde 503.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time

import config

# Duración de la sesión del panel. Vencida, el panel devuelve 401 y la página
# vuelve sola al login (mismo manejo de 401 que ya existía).
SESION_HORAS = 12

_PREFIJO = "s1"  # versión del formato de sesión: s1.<usuario_b64>.<exp>.<firma>


def usuarios_configurados() -> dict[str, str]:
    """Mapa correo→clave desde ADMIN_PANEL_USUARIOS. Vacío si no está seteada."""
    out: dict[str, str] = {}
    for par in (config.ADMIN_PANEL_USUARIOS or "").split(","):
        par = par.strip()
        if not par or ":" not in par:
            continue
        correo, clave = par.split(":", 1)
        correo, clave = correo.strip().lower(), clave.strip()
        if correo and clave:
            out[correo] = clave
    return out


def credenciales_validas(usuario: str | None, clave: str | None) -> bool:
    esperada = usuarios_configurados().get((usuario or "").strip().lower())
    if esperada is None:
        # Comparar igual para no delatar por tiempo si el correo existe.
        hmac.compare_digest(clave or "", "x")
        return False
    return hmac.compare_digest(clave or "", esperada)


def _firma(usuario_b64: str, exp: int) -> str:
    return hmac.new(
        config.ADMIN_PANEL_TOKEN.encode(),
        f"{_PREFIJO}.{usuario_b64}.{exp}".encode(),
        hashlib.sha256,
    ).hexdigest()


def crear_sesion(usuario: str) -> str:
    """Token de sesión firmado, con expiración, para X-Admin-Token."""
    exp = int(time.time()) + SESION_HORAS * 3600
    ub = base64.urlsafe_b64encode(usuario.encode()).decode().rstrip("=")
    return f"{_PREFIJO}.{ub}.{exp}.{_firma(ub, exp)}"


def _sesion_valida(token: str) -> bool:
    partes = token.split(".")
    if len(partes) != 4 or partes[0] != _PREFIJO:
        return False
    _, ub, exp_txt, firma = partes
    try:
        exp = int(exp_txt)
    except ValueError:
        return False
    if exp < time.time():
        return False  # sesión vencida
    return hmac.compare_digest(firma, _firma(ub, exp))


def token_admin_valido(token: str | None) -> bool:
    """¿La cabecera X-Admin-Token trae el token clásico O una sesión vigente?"""
    if not config.ADMIN_PANEL_TOKEN or not token:
        return False
    if hmac.compare_digest(token, config.ADMIN_PANEL_TOKEN):
        return True
    return _sesion_valida(token)
