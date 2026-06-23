"""Adapter de Twilio para enviar el código OTP por **SMS**.

Alternativa/respaldo a WhatsApp Cloud API que NO depende de Meta (útil mientras la
cuenta de Meta esté en revisión). Usa la API de Mensajes de Twilio enviando el
mismo código que genera nuestro servicio (mantiene el hash + TTL + no-retención).

Fail-safe: sin `TWILIO_ACCOUNT_SID`/`TWILIO_AUTH_TOKEN` el adapter queda inactivo.
"""

from __future__ import annotations

import base64
import urllib.parse
import urllib.request

import config


def disponible() -> bool:
    return bool(
        config.TWILIO_ACCOUNT_SID
        and config.TWILIO_AUTH_TOKEN
        and (config.TWILIO_FROM or config.TWILIO_MESSAGING_SERVICE_SID)
    )


def enviar_sms(telefono_e164: str, codigo: str) -> dict:
    """Envía el código por SMS. `telefono_e164` sin '+'; Twilio lo requiere con '+'.
    Devuelve {ok, via, error?}. Nunca lanza."""
    if not disponible():
        return {"ok": True, "via": "stub"}

    to = telefono_e164 if telefono_e164.startswith("+") else f"+{telefono_e164}"
    cuerpo = (
        f"Tu codigo de verificacion Pichangol es {codigo}. "
        f"Vence en 5 minutos. No lo compartas."
    )
    datos = {"To": to, "Body": cuerpo}
    if config.TWILIO_MESSAGING_SERVICE_SID:
        datos["MessagingServiceSid"] = config.TWILIO_MESSAGING_SERVICE_SID
    else:
        datos["From"] = config.TWILIO_FROM

    url = (
        "https://api.twilio.com/2010-04-01/Accounts/"
        f"{config.TWILIO_ACCOUNT_SID}/Messages.json"
    )
    auth = base64.b64encode(
        f"{config.TWILIO_ACCOUNT_SID}:{config.TWILIO_AUTH_TOKEN}".encode("utf-8")
    ).decode("ascii")
    req = urllib.request.Request(
        url,
        data=urllib.parse.urlencode(datos).encode("utf-8"),
        headers={
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            return {"ok": resp.status < 300, "via": "sms"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "via": "sms", "error": str(e)[:200]}
