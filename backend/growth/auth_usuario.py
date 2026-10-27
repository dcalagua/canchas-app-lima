"""IDENTIDAD VERIFICADA del usuario en el servidor (plan nocturno C1).

Hasta ahora casi todos los endpoints del APK confiaban en el correo que manda
el cliente (`email`, `dueno`, `solicitante`): con la `X-App-Key` (que viaja en
el APK) cualquiera podía actuar en nombre de otro. Este módulo es la ÚNICA
forma de saber quién es el usuario:

1. **APK:** cabecera `X-User-Token` = ID token de Google (el APK ya lo manda,
   `PagosService._headers`). Se verifica contra Google (audiencia de NUESTRA
   app, correo verificado, vigencia) con caché en memoria (`pagos.router.
   _email_de_token`, un solo caché para todo el backend).
2. **Web:** la cookie de sesión firmada `pcg_sesion` (`web/sesion.py`).

Todo endpoint NUEVO que actúe sobre datos de un usuario usa
`Depends(requiere_usuario)` y compara contra el dueño REAL del recurso; nunca
recibe el correo en el cuerpo. `comparar_constante` también para la app key.
"""

from __future__ import annotations

import hmac

from fastapi import Depends, Header, HTTPException, Request

import config


def comparar_constante(a: str | None, b: str | None) -> bool:
    return hmac.compare_digest((a or "").encode(), (b or "").encode())


def requiere_app_key(x_app_key: str | None = Header(default=None)) -> None:
    """La clave del APK oficial (si está configurada). NO es identidad: viaja
    dentro del APK; solo filtra tráfico que no viene de nuestra app/web."""
    if not config.APP_API_KEY:
        return
    if not comparar_constante(x_app_key, config.APP_API_KEY):
        raise HTTPException(status_code=401, detail="app_key_invalida")


def usuario_de(request: Request | None, x_user_token: str | None = None) -> str | None:
    """Correo VERIFICADO del que llama, o None."""
    tok = (x_user_token or "").strip()
    if tok:
        from pagos.router import _email_de_token
        email = _email_de_token(tok)
        if email:
            return email.strip().lower()
    if request is not None:
        from web import sesion
        ses = sesion.de_request(request) if sesion.activo() else None
        if ses and ses.get("email"):
            return str(ses["email"]).strip().lower()
    return None


def requiere_usuario(request: Request, x_user_token: str | None = Header(default=None)) -> str:
    """Dependencia FastAPI: devuelve el correo verificado o 401."""
    email = usuario_de(request, x_user_token)
    if not email:
        raise HTTPException(status_code=401, detail="sesion_requerida")
    return email


APP = [Depends(requiere_app_key)]
