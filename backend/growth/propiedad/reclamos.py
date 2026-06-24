"""RECLAMO de propiedad con intervención humana primero (modelo concierge) y
validación EN SITIO por un motorizado.

Flujo:
  1. crear_reclamo  -> el dueño presiona "Reclamar". Se genera un CÓDIGO y le
     llega un WhatsApp al ADMIN (Pichangol) con los datos + código. Estado:
     pendiente_triage. Nada se activa todavía.
  2. triage         -> el admin lo llama/escribe, se cerciora y aprueba/rechaza.
     Al aprobar (aprobado_triage) la app desbloquea el panel (precio, WhatsApp…).
  3. listo_para_validar -> el dueño guardó su info. Queda pendiente_validacion y
     se avisa para enviar un validador. La cancha NO es reservable aún.
  4. validar_en_sitio -> el motorizado va al local, ingresa el CÓDIGO y su GPS
     debe coincidir con la cancha. Si coincide, se activa (verificada +
     verificada_en_persona) y se avisa al admin. La activación depende de la
     validación, NO de un temporizador.

No retiene datos personales más allá de lo necesario; el teléfono de contacto del
reclamante se usa para que el admin lo ubique y no se publica.
"""

from __future__ import annotations

import math
import secrets

import config
from db.store import ReclamoPropiedad, ahora, como_dict, stores
from propiedad import identidad, twilio_adapter, whatsapp_adapter


def _notificar_admin(texto: str) -> None:
    """Avisa al admin por WhatsApp (Twilio o Meta). Fail-safe: nunca lanza."""
    destino = config.PICHANGOL_ADMIN_WHATSAPP
    if not destino:
        return
    try:
        if twilio_adapter.disponible_whatsapp():
            twilio_adapter.enviar_whatsapp_texto(destino, texto)
        elif whatsapp_adapter.disponible():
            # Meta requiere plantilla para iniciar; reusa el envío de OTP como
            # mejor esfuerzo (el texto va como parámetro). Si falla, se ignora.
            whatsapp_adapter.enviar_otp(destino, texto[:32])
    except Exception:  # noqa: BLE001
        pass


def _distancia_m(lat1, lng1, lat2, lng2) -> float:
    """Haversine en metros."""
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def crear_reclamo(cancha_id: str, solicitante_id: str, nombre_local: str,
                  telefono_contacto: str | None = None,
                  dni: str | None = None, ruc: str | None = None,
                  relacion: str | None = None,
                  lat: float | None = None, lng: float | None = None) -> dict:
    codigo = f"{secrets.randbelow(1_000_000):06d}"
    # Consultas autoritativas server-side (fail-safe): DNI=persona, RUC=negocio.
    nombre_titular = None
    if dni:
        info = identidad.consultar_dni(dni)
        if info.get("ok"):
            nombre_titular = info.get("nombre_completo")
    razon_social = None
    if ruc:
        info = identidad.consultar_ruc(ruc)
        if info.get("ok"):
            razon_social = info.get("razon_social")
    r = ReclamoPropiedad(
        id=stores.next_id("reclamo"),
        cancha_id=cancha_id,
        solicitante_id=solicitante_id,
        nombre_local=nombre_local,
        codigo=codigo,
        estado="pendiente_triage",
        creado_en=ahora(),
        telefono_contacto=telefono_contacto,
        dni=dni,
        nombre_titular=nombre_titular,
        ruc=ruc,
        razon_social=razon_social,
        relacion=relacion,
        lat=lat,
        lng=lng,
    )
    stores.reclamos.append(r)
    _notificar_admin(
        f"🟢 Nuevo reclamo de cancha en Pichangol\n"
        f"Local: {nombre_local}\n"
        f"Relación: {relacion or 's/d'}\n"
        f"Titular (DNI {dni or 's/n'}): {nombre_titular or 's/d'}\n"
        + (f"RUC {ruc}: {razon_social or 's/d'}\n" if ruc else "")
        + f"Cuenta: {solicitante_id}\n"
        f"WhatsApp del dueño: {telefono_contacto or '⚠️ no dejó número'}\n"
        f"Código: {codigo}\n"
        f"Escríbele/llámalo por WhatsApp y, si lo verificas, apruébalo en el "
        f"panel de Reclamos.")
    return {"ok": True, "reclamo_id": r.id, "codigo": codigo, "estado": r.estado}


def _por_id(reclamo_id: int) -> ReclamoPropiedad | None:
    return next((r for r in stores.reclamos if r.id == reclamo_id), None)


def estado(cancha_id: str) -> dict:
    rs = [r for r in stores.reclamos if r.cancha_id == cancha_id]
    if not rs:
        return {"existe": False}
    r = rs[-1]
    c = stores.canchas.get(cancha_id)
    return {
        "existe": True,
        "reclamo_id": r.id,
        "estado": r.estado,
        "panel_desbloqueado": r.estado in (
            "aprobado_triage", "pendiente_validacion", "activada"),
        "verificada": bool(c and c.verificada),
        "verificada_en_persona": bool(c and c.verificada_en_persona),
    }


def triage(reclamo_id: int, aprobado: bool, revisor: str | None = None,
           nota: str | None = None) -> dict:
    r = _por_id(reclamo_id)
    if r is None:
        return {"ok": False, "error": "reclamo_no_existe"}
    r.estado = "aprobado_triage" if aprobado else "rechazada"
    r.decidido_en = ahora()
    r.nota = f"Triage por {revisor or 'admin'}. {nota or ''}".strip()
    return {"ok": True, "estado": r.estado}


def listo_para_validar(reclamo_id: int) -> dict:
    """El dueño guardó su info: pasa a pendiente_validacion y se pide validador."""
    r = _por_id(reclamo_id)
    if r is None:
        return {"ok": False, "error": "reclamo_no_existe"}
    if r.estado not in ("aprobado_triage", "pendiente_validacion"):
        return {"ok": False, "error": "estado_invalido", "estado": r.estado}
    r.estado = "pendiente_validacion"
    _notificar_admin(
        f"📍 Reclamo listo para validar en sitio\n"
        f"Local: {r.nombre_local}\nCódigo: {r.codigo}\n"
        f"Asigna un motorizado para confirmar en el lugar.")
    return {"ok": True, "estado": r.estado, "codigo": r.codigo}


def validar_en_sitio(codigo: str, lat: float, lng: float,
                     validador: str | None = None,
                     fotos_urls: list[str] | None = None) -> dict:
    """El motorizado ingresa el código en el sitio. Su GPS debe coincidir con la
    ubicación de la cancha. Si coincide, activa (o deja lista para que el admin
    active, según VALIDADOR_ACTIVA_AUTOMATICO)."""
    r = next((x for x in stores.reclamos if x.codigo == codigo
              and x.estado in ("aprobado_triage", "pendiente_validacion")), None)
    if r is None:
        return {"ok": False, "error": "codigo_invalido"}

    if r.lat is not None and r.lng is not None:
        dist = _distancia_m(r.lat, r.lng, lat, lng)
        if dist > config.RECLAMO_VALIDACION_GPS_MAX_M:
            return {"ok": False, "error": "ubicacion_no_coincide",
                    "distancia_m": round(dist)}
    else:
        dist = None  # sin ubicación declarada no se puede contrastar

    r.validado_en = ahora()
    r.validador = validador

    if config.VALIDADOR_ACTIVA_AUTOMATICO:
        r.estado = "activada"
        c = stores.cancha(r.cancha_id)
        c.verificada = True
        c.verificada_en_persona = True
        c.metodo_verificacion = "en_sitio"
        _notificar_admin(
            f"✅ Cancha validada en sitio y ACTIVADA\n"
            f"Local: {r.nombre_local}\nValidador: {validador or 's/n'}\n"
            f"Distancia GPS: {round(dist) if dist is not None else 's/d'} m")
        return {"ok": True, "estado": "activada", "verificada": True,
                "distancia_m": round(dist) if dist is not None else None}

    # Modo manual: queda validada pero la activa el admin.
    r.estado = "validada_pendiente_admin"
    _notificar_admin(
        f"🟡 Cancha validada en sitio, falta tu activación\n"
        f"Local: {r.nombre_local}\nCódigo: {r.codigo}")
    return {"ok": True, "estado": "validada_pendiente_admin", "verificada": False,
            "distancia_m": round(dist) if dist is not None else None}


def aprobar_directo(reclamo_id: int, revisor: str | None = None) -> dict:
    """Piloto (panel web): el admin aprueba y la cancha queda ACTIVA al instante.
    Equivale a triage(aprobado) + activación, SIN validación en sitio todavía.
    Marca verificada=True con método 'panel_admin' (no es verificación en persona,
    así que verificada_en_persona queda en False)."""
    r = _por_id(reclamo_id)
    if r is None:
        return {"ok": False, "error": "reclamo_no_existe"}
    r.estado = "activada"
    r.decidido_en = ahora()
    r.validado_en = ahora()
    r.validador = revisor
    r.nota = f"Aprobación directa (panel) por {revisor or 'admin'}.".strip()
    c = stores.cancha(r.cancha_id)
    c.verificada = True
    c.metodo_verificacion = "panel_admin"
    _notificar_admin(
        f"✅ Cancha ACTIVADA por aprobación directa (panel)\n"
        f"Local: {r.nombre_local}\nAdmin: {revisor or 's/n'}")
    return {"ok": True, "estado": "activada", "verificada": True}


def activar_admin(reclamo_id: int) -> dict:
    """Activación manual por el admin (cuando VALIDADOR_ACTIVA_AUTOMATICO=0)."""
    r = _por_id(reclamo_id)
    if r is None:
        return {"ok": False, "error": "reclamo_no_existe"}
    r.estado = "activada"
    c = stores.cancha(r.cancha_id)
    c.verificada = True
    c.verificada_en_persona = True
    c.metodo_verificacion = "en_sitio"
    return {"ok": True, "estado": "activada", "verificada": True}


def listar(estado_filtro: str | None = None) -> list[dict]:
    rs = stores.reclamos
    if estado_filtro:
        rs = [r for r in rs if r.estado == estado_filtro]
    return [como_dict(r) for r in rs]
