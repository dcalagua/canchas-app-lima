"""VERIFICACIÓN DE PROPIEDAD (no de existencia).

Confirma que quien reclama una cancha controla el local, no sólo que el local
exista. Caminos soportados:

  1. OTP por WhatsApp Cloud API  -> el código llega al teléfono del local.
  2. Aprobación manual           -> el equipo de Pichangol confirma a mano.
  3. (en_sitio)                  -> ya lo cubre VERIFICACION FISICA (verificador).

Política anti-fraude del OTP: poder leer un código en un teléfono prueba que
controlas ESE teléfono, no que seas el dueño. Por eso, si el número al que se
envía coincide con el teléfono público del local (Places/redes), el OTP basta y
queda `confirmada`. Si no hay un teléfono público con el cual contrastar, el OTP
exitoso deja la solicitud en `pendiente_revision` para aprobación manual.

Privacidad (Ley 29733): el código se guarda sólo como hash con TTL y se borra al
usarse o vencer; el teléfono completo nunca se persiste (sólo enmascarado en el
registro de auditoría).
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

import config
from db.store import ConfirmacionPropiedad, OtpPropiedad, ahora, stores
from datetime import timedelta

from propiedad import twilio_adapter, whatsapp_adapter


def _enviar_codigo(telefono: str, codigo: str) -> dict:
    """Elige canal y envía el código. Preferencia configurable (whatsapp|sms);
    si el preferido no está disponible, cae al otro; si ninguno, modo stub."""
    pref = config.OTP_CANAL_PREFERIDO
    orden = (
        [twilio_adapter, whatsapp_adapter]
        if pref == "sms"
        else [whatsapp_adapter, twilio_adapter]
    )
    for adapter in orden:
        if adapter is whatsapp_adapter and whatsapp_adapter.disponible():
            return whatsapp_adapter.enviar_otp(telefono, codigo)
        if adapter is twilio_adapter and twilio_adapter.disponible():
            return twilio_adapter.enviar_sms(telefono, codigo)
    return {"ok": True, "via": "stub"}


def _norm_tel(telefono: str) -> str:
    """Normaliza a E.164 sin '+' ni separadores. Asume Perú (51) si faltan."""
    d = "".join(ch for ch in telefono if ch.isdigit())
    if d.startswith("00"):
        d = d[2:]
    if len(d) == 9 and d.startswith("9"):  # celular peruano sin prefijo país
        d = "51" + d
    return d


def _mask(telefono: str) -> str:
    d = _norm_tel(telefono)
    return ("•" * max(0, len(d) - 4)) + d[-4:] if d else ""


def _hash(codigo: str, cancha_id: str) -> str:
    # HMAC con el token como clave si existe; si no, sal local del proceso.
    clave = (config.WHATSAPP_TOKEN or "pichangol-otp-salt").encode("utf-8")
    return hmac.new(clave, f"{cancha_id}:{codigo}".encode("utf-8"),
                    hashlib.sha256).hexdigest()


def solicitar(cancha_id: str, telefono: str) -> dict:
    """Genera y envía un OTP al teléfono indicado. Rate-limit por reenvío."""
    tel = _norm_tel(telefono)
    if len(tel) < 8:
        return {"ok": False, "error": "telefono_invalido"}

    prev = stores.otps.get(cancha_id)
    if prev is not None:
        desde = (ahora() - prev.creado_en).total_seconds()
        if desde < config.OTP_REENVIO_MIN_SEG:
            espera = int(config.OTP_REENVIO_MIN_SEG - desde)
            return {"ok": False, "error": "reenvio_muy_pronto", "espera_seg": espera}

    codigo = f"{secrets.randbelow(1_000_000):06d}"
    otp = OtpPropiedad(
        cancha_id=cancha_id,
        telefono=tel,
        codigo_hash=_hash(codigo, cancha_id),
        expira_en=ahora() + timedelta(seconds=config.OTP_TTL_SEG),
        creado_en=ahora(),
    )

    envio = _enviar_codigo(tel, codigo)
    otp.enviado_via = envio.get("via", "stub")
    if not envio.get("ok"):
        return {"ok": False, "error": "envio_fallo", "detalle": envio.get("error")}

    stores.otps[cancha_id] = otp
    out = {
        "ok": True,
        "via": otp.enviado_via,
        "telefono_enmascarado": _mask(tel),
        "expira_seg": config.OTP_TTL_SEG,
    }
    # Sólo en entornos de prueba (sin credenciales reales) y si está habilitado.
    if config.OTP_DEBUG_DEVOLVER_CODIGO and otp.enviado_via == "stub":
        out["codigo_debug"] = codigo
    return out


def confirmar(cancha_id: str, codigo: str, solicitante_id: str,
              telefono_publico: str | None = None) -> dict:
    """Valida el OTP. Si coincide, decide el estado de propiedad y registra la
    confirmación (auditable). Borra el OTP tras un intento exitoso o al agotar
    intentos (no-retención)."""
    otp = stores.otps.get(cancha_id)
    if otp is None:
        return {"ok": False, "error": "sin_otp"}
    if ahora() > otp.expira_en:
        stores.otps.pop(cancha_id, None)
        return {"ok": False, "error": "otp_vencido"}
    if otp.intentos >= config.OTP_MAX_INTENTOS:
        stores.otps.pop(cancha_id, None)
        return {"ok": False, "error": "max_intentos"}

    otp.intentos += 1
    if not hmac.compare_digest(otp.codigo_hash, _hash(codigo, cancha_id)):
        restantes = config.OTP_MAX_INTENTOS - otp.intentos
        if restantes <= 0:
            stores.otps.pop(cancha_id, None)
        return {"ok": False, "error": "codigo_incorrecto", "intentos_restantes": max(0, restantes)}

    # Código correcto. ¿El teléfono prueba propiedad?
    tel_pub = _norm_tel(telefono_publico) if telefono_publico else ""
    coincide_publico = bool(tel_pub) and tel_pub == otp.telefono
    estado = "confirmada" if (coincide_publico or not tel_pub) else "pendiente_revision"
    # Si hay teléfono público y NO coincide, el OTP no debió ser válido para ese
    # número; lo dejamos en revisión por seguridad.
    if tel_pub and not coincide_publico:
        estado = "pendiente_revision"

    conf = ConfirmacionPropiedad(
        id=stores.next_id("conf_propiedad"),
        cancha_id=cancha_id,
        solicitante_id=solicitante_id,
        metodo="otp_whatsapp",
        estado=estado,
        telefono_enmascarado=_mask(otp.telefono),
        creado_en=ahora(),
        decidido_en=ahora() if estado == "confirmada" else None,
        nota="OTP verificado" + (" (coincide con teléfono público)"
                                 if coincide_publico else ""),
    )
    stores.confirmaciones_propiedad.append(conf)
    stores.otps.pop(cancha_id, None)  # no-retención: se borra al usarse

    if estado == "confirmada":
        c = stores.cancha(cancha_id)
        c.verificada = True
        c.metodo_verificacion = "documental"  # OTP = vía no presencial

    return {
        "ok": True,
        "estado": estado,
        "verificada": estado == "confirmada",
        "confirmacion_id": conf.id,
    }


def aprobar_manual(cancha_id: str, solicitante_id: str, aprobado: bool,
                   revisor: str | None = None, nota: str | None = None) -> dict:
    """El equipo de Pichangol aprueba/rechaza la propiedad a mano (uso interno)."""
    estado = "confirmada" if aprobado else "rechazada"
    conf = ConfirmacionPropiedad(
        id=stores.next_id("conf_propiedad"),
        cancha_id=cancha_id,
        solicitante_id=solicitante_id,
        metodo="manual",
        estado=estado,
        telefono_enmascarado=None,
        creado_en=ahora(),
        decidido_en=ahora(),
        nota=f"Revisor: {revisor or 'equipo'}. {nota or ''}".strip(),
    )
    stores.confirmaciones_propiedad.append(conf)
    if aprobado:
        c = stores.cancha(cancha_id)
        c.verificada = True
        c.metodo_verificacion = "documental"
    return {"ok": True, "estado": estado, "verificada": aprobado,
            "confirmacion_id": conf.id}


def estado(cancha_id: str) -> dict:
    """Estado de propiedad de una cancha (la última decisión registrada)."""
    confs = [c for c in stores.confirmaciones_propiedad if c.cancha_id == cancha_id]
    c = stores.canchas.get(cancha_id)
    ultima = confs[-1] if confs else None
    return {
        "cancha_id": cancha_id,
        "verificada": bool(c and c.verificada),
        "ultima": {
            "metodo": ultima.metodo,
            "estado": ultima.estado,
            "nota": ultima.nota,
        } if ultima else None,
        "tiene_otp_activo": cancha_id in stores.otps,
    }
