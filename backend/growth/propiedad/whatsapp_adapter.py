"""Adapter de WhatsApp Cloud API para enviar el código OTP de PROPIEDAD.

Diseño fail-safe: si no hay `WHATSAPP_TOKEN` configurado (secret en Railway), el
adapter corre en modo STUB y NO intenta llamar a Meta. Así el backend funciona en
desarrollo/tests sin credenciales, y en producción basta con cargar los secrets
siguiendo docs/whatsapp-cloud-api-setup.md.

No se retiene el teléfono ni el código más allá de lo necesario para validar el
OTP (Ley 29733): el envío es transitorio y el código vive con TTL en memoria.
"""

from __future__ import annotations

import json
import urllib.request

import config


def disponible() -> bool:
    return bool(config.WHATSAPP_TOKEN and config.WHATSAPP_PHONE_NUMBER_ID)


def enviar_otp(telefono_e164: str, codigo: str) -> dict:
    """Envía el código por una plantilla de AUTENTICACIÓN de WhatsApp.

    `telefono_e164` debe ir en formato internacional sin '+' (ej. 51987654321).
    Devuelve {ok, via, error?}. Nunca lanza: ante cualquier fallo devuelve ok=False
    para que el servicio decida (reintento / aprobación manual).
    """
    if not disponible():
        # STUB: no hay credenciales. El servicio puede exponer el código sólo si
        # OTP_DEBUG_DEVOLVER_CODIGO=1 (entorno de prueba), nunca en producción.
        return {"ok": True, "via": "stub"}

    url = (
        f"https://graph.facebook.com/{config.WHATSAPP_API_VERSION}/"
        f"{config.WHATSAPP_PHONE_NUMBER_ID}/messages"
    )
    # Plantilla de autenticación: el código va como parámetro del body y del botón
    # "copiar código" (one-time passcode), según el formato de Meta.
    payload = {
        "messaging_product": "whatsapp",
        "to": telefono_e164,
        "type": "template",
        "template": {
            "name": config.WHATSAPP_OTP_TEMPLATE,
            "language": {"code": config.WHATSAPP_OTP_LANG},
            "components": [
                {
                    "type": "body",
                    "parameters": [{"type": "text", "text": codigo}],
                },
                {
                    "type": "button",
                    "sub_type": "url",
                    "index": "0",
                    "parameters": [{"type": "text", "text": codigo}],
                },
            ],
        },
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {config.WHATSAPP_TOKEN}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            cuerpo = json.loads(resp.read().decode("utf-8"))
            return {"ok": True, "via": "whatsapp", "respuesta": cuerpo}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "via": "whatsapp", "error": str(e)[:200]}
