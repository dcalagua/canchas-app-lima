"""Adapter de Twilio para enviar el código OTP por **SMS** o por **WhatsApp**
(sandbox o número aprobado de Twilio).

Alternativa/respaldo a WhatsApp Cloud API de Meta que NO depende de la aprobación
de Meta (útil mientras la cuenta de WhatsApp Business está en revisión). Usa la API
de Mensajes de Twilio enviando el mismo código que genera nuestro servicio
(mantiene el hash + TTL + no-retención).

Fail-safe: sin `TWILIO_ACCOUNT_SID`/`TWILIO_AUTH_TOKEN` el adapter queda inactivo.
"""

from __future__ import annotations

import base64
import urllib.parse
import urllib.request

import config


def _creds_ok() -> bool:
    return bool(config.TWILIO_ACCOUNT_SID and config.TWILIO_AUTH_TOKEN)


def disponible() -> bool:
    """¿Se puede enviar por SMS? (número o messaging service configurado)."""
    return bool(
        _creds_ok()
        and (config.TWILIO_FROM or config.TWILIO_MESSAGING_SERVICE_SID)
    )


def disponible_whatsapp() -> bool:
    """¿Se puede enviar por WhatsApp vía Twilio? (remitente WhatsApp configurado)."""
    return bool(_creds_ok() and config.TWILIO_WHATSAPP_FROM)


def _cuerpo(codigo: str) -> str:
    return (
        f"Tu codigo de verificacion Pichangol es {codigo}. "
        f"Vence en 5 minutos. No lo compartas."
    )


def _con_mas(telefono_e164: str) -> str:
    return telefono_e164 if telefono_e164.startswith("+") else f"+{telefono_e164}"


def _post(datos: dict, via: str) -> dict:
    """POST a la API de Mensajes de Twilio. Nunca lanza."""
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
            return {"ok": resp.status < 300, "via": via}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "via": via, "error": str(e)[:200]}


def enviar_sms(telefono_e164: str, codigo: str) -> dict:
    """Envía el código por SMS. Devuelve {ok, via, error?}."""
    if not disponible():
        return {"ok": True, "via": "stub"}
    datos = {"To": _con_mas(telefono_e164), "Body": _cuerpo(codigo)}
    if config.TWILIO_MESSAGING_SERVICE_SID:
        datos["MessagingServiceSid"] = config.TWILIO_MESSAGING_SERVICE_SID
    else:
        datos["From"] = config.TWILIO_FROM
    return _post(datos, via="sms")


def enviar_whatsapp(telefono_e164: str, codigo: str) -> dict:
    """Envía el código por WhatsApp vía Twilio (prefijo `whatsapp:`). El número
    de destino debe haberse unido al sandbox (en pruebas). Devuelve {ok, via}."""
    return enviar_whatsapp_texto(telefono_e164, _cuerpo(codigo))


def enviar_whatsapp_texto(telefono_e164: str, texto: str) -> dict:
    """Envía un texto libre por WhatsApp vía Twilio. Para avisos al admin."""
    if not disponible_whatsapp():
        return {"ok": True, "via": "stub"}
    desde = _con_mas(config.TWILIO_WHATSAPP_FROM)
    datos = {
        "From": f"whatsapp:{desde}",
        "To": f"whatsapp:{_con_mas(telefono_e164)}",
        "Body": texto,
    }
    return _post(datos, via="twilio_whatsapp")
