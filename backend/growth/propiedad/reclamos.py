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
from db.store import (
    CANALES_COMUNICACION,
    MODOS_APROBACION,
    ReclamoPropiedad,
    ahora,
    como_dict,
    stores,
)
from propiedad import identidad, twilio_adapter, whatsapp_adapter


def config_modo() -> dict:
    """Configuración del modo de aprobación: global + overrides por cancha."""
    return {
        "global": stores.cfg("modo_aprobacion"),
        "overrides": dict(stores.modo_aprobacion_overrides),
        "modos": list(MODOS_APROBACION),
    }


def set_modo_global(modo: str) -> dict:
    if modo not in MODOS_APROBACION:
        return {"ok": False, "error": "modo_invalido",
                "modos": list(MODOS_APROBACION)}
    stores.config["modo_aprobacion"] = modo
    return {"ok": True, "global": modo}


def canal_comunicacion() -> str:
    """Canal que el APK muestra para contactar al profe: 'pcg_primero' |
    'solo_pcg' | 'whatsapp_libre'. Editable desde la torre de control."""
    valor = stores.cfg("canal_comunicacion")
    return valor if valor in CANALES_COMUNICACION else "pcg_primero"


def config_canal() -> dict:
    """Config del canal de comunicación (global + valores válidos)."""
    return {"canal": canal_comunicacion(), "canales": list(CANALES_COMUNICACION)}


def set_canal_comunicacion(canal: str) -> dict:
    if canal not in CANALES_COMUNICACION:
        return {"ok": False, "error": "canal_invalido",
                "canales": list(CANALES_COMUNICACION)}
    stores.config["canal_comunicacion"] = canal
    return {"ok": True, "canal": canal}


def exigir_ubicacion() -> bool:
    """¿El admin exige que el reclamante esté en la cancha (GPS coincidente)
    para poder aprobar?"""
    return stores.cfg("exigir_ubicacion_reclamo") == "1"


def set_exigir_ubicacion(activo: bool) -> dict:
    """Activa/desactiva la exigencia de ubicación coincidente para aprobar."""
    stores.config["exigir_ubicacion_reclamo"] = "1" if activo else "0"
    return {"ok": True, "exigir_ubicacion_reclamo": exigir_ubicacion(),
            "max_m": config.RECLAMO_UBICACION_MAX_M}


# Código telefónico internacional por país (para armar el número completo).
COD_PAIS_CONTACTO = {"pe": "51", "ec": "593", "bo": "591"}


def _solo_digitos(v: str) -> str:
    return "".join(ch for ch in (v or "") if ch.isdigit())


def contacto_local(pais: str) -> str:
    """Número LOCAL guardado para un país (pe|ec|bo), sin el código de país."""
    p = (pais or "").lower()
    return stores.cfg("contacto_whatsapp_" + p) if p in COD_PAIS_CONTACTO else ""


def contactos_whatsapp() -> dict:
    """Números LOCALES por país (para la torre de control)."""
    return {p: contacto_local(p) for p in COD_PAIS_CONTACTO}


def contacto_whatsapp(pais: str | None = None) -> str:
    """WhatsApp COMPLETO (código + local) del país indicado. Si ese país no
    tiene número, cae al primero configurado (orden ec, pe, bo). Editable desde
    la torre de control."""
    p = (pais or "").lower()
    local = contacto_local(p)
    if local:
        return COD_PAIS_CONTACTO[p] + local
    for q in ("ec", "pe", "bo"):
        lq = contacto_local(q)
        if lq:
            return COD_PAIS_CONTACTO[q] + lq
    return stores.cfg("contacto_whatsapp")  # respaldo legado (global)


def set_contactos_whatsapp(contactos: dict) -> dict:
    """Fija los números LOCALES por país. Ignora países desconocidos."""
    for p, v in (contactos or {}).items():
        pk = str(p).lower()
        if pk in COD_PAIS_CONTACTO:
            stores.config["contacto_whatsapp_" + pk] = _solo_digitos(str(v))
    return {"ok": True, "contactos": contactos_whatsapp()}


def set_modo_cancha(cancha_id: str, modo: str | None) -> dict:
    """Fija (o limpia, si modo es None/'') el override de una cancha."""
    if not modo:
        stores.modo_aprobacion_overrides.pop(cancha_id, None)
        return {"ok": True, "cancha_id": cancha_id, "modo": None}
    if modo not in MODOS_APROBACION:
        return {"ok": False, "error": "modo_invalido",
                "modos": list(MODOS_APROBACION)}
    stores.modo_aprobacion_overrides[cancha_id] = modo
    return {"ok": True, "cancha_id": cancha_id, "modo": modo}


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


def _notificar_reclamante_aprobado(r: "ReclamoPropiedad") -> None:
    """Push "¡Tu cancha fue aprobada!" al reclamante, vía la Edge Function de
    Supabase (push-aprobacion). El backend growth NO hace FCM; delega en Supabase.
    Fail-safe: nunca lanza (si no hay URL configurada o falla la red, se ignora)."""
    url = config.PUSH_APROBACION_URL
    email = (r.solicitante_id or "").strip()
    if not url or not email:
        return
    try:
        import json as _json
        import urllib.request as _url
        cuerpo = _json.dumps({
            "email": email,
            "cancha_nombre": r.nombre_local or "tu cancha",
            "cancha_id": r.cancha_id or "",
        }).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if config.PUSH_APROBACION_SECRET:
            headers["X-Push-Secret"] = config.PUSH_APROBACION_SECRET
        req = _url.Request(url, data=cuerpo, headers=headers, method="POST")
        with _url.urlopen(req, timeout=10):
            pass
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


_ESTADOS_TERMINALES = ("activada", "rechazada")

# Estados en los que un reclamo "ocupa" la cancha e impide un segundo reclamo de
# OTRO usuario. (Un reclamo 'rechazada' NO bloquea: vuelve a ser reclamable.)
_ESTADOS_BLOQUEANTES = (
    "pendiente_triage", "aprobado_triage", "pendiente_validacion",
    "validada_pendiente_admin", "activada",
)
# Radio (m) para considerar que dos reclamos son del MISMO lugar aunque tengan
# distinto cancha_id (p. ej. dos personas reclamando la misma cancha de Google).
_MISMO_LUGAR_M = 80.0


def _reclamo_activo_del_lugar(cancha_id: str, lat: float | None,
                              lng: float | None) -> ReclamoPropiedad | None:
    """Devuelve el reclamo ACTIVO que ya ocupa esta cancha: por mismo cancha_id,
    o por ubicación muy cercana (mismo lugar físico). None si está libre."""
    for r in stores.reclamos:
        if r.estado not in _ESTADOS_BLOQUEANTES:
            continue
        if r.cancha_id == cancha_id:
            return r
        if (lat is not None and lng is not None
                and r.lat is not None and r.lng is not None
                and _distancia_m(r.lat, r.lng, lat, lng) <= _MISMO_LUGAR_M):
            return r
    return None


def lugar_reclamado(lat: float | None, lng: float | None, cancha_id: str = "",
                    solicitante: str | None = None) -> dict:
    """¿Este lugar ya tiene un reclamo ACTIVO? La app lo consulta para bloquear el
    botón "Reclamar" ANTES de intentarlo (si ya lo reclamó otro usuario)."""
    activo = _reclamo_activo_del_lugar(cancha_id, lat, lng)
    if activo is None:
        return {"reclamada": False}
    return {
        "reclamada": True,
        "estado": activo.estado,
        "por_mi": bool(solicitante) and activo.solicitante_id == solicitante,
    }


def crear_reclamo(cancha_id: str, solicitante_id: str, nombre_local: str,
                  telefono_contacto: str | None = None,
                  dni: str | None = None, ruc: str | None = None,
                  relacion: str | None = None,
                  lat: float | None = None, lng: float | None = None,
                  solicitante_lat: float | None = None,
                  solicitante_lng: float | None = None,
                  solicitante_nombre: str = "",
                  foto_evidencia_url: str = "",
                  nota_reclamante: str = "") -> dict:
    # Anti doble-reclamo. Si esta cancha (por id) o el MISMO lugar (ubicación
    # cercana) ya tiene un reclamo ACTIVO:
    #  - de OTRO usuario → se rechaza ("ya_reclamada").
    #  - del MISMO solicitante → idempotente: actualiza datos y devuelve el
    #    existente (cubre "reenviar solicitud" y reintentos de red).
    activo = _reclamo_activo_del_lugar(cancha_id, lat, lng)
    if activo is not None:
        if activo.solicitante_id != solicitante_id:
            return {"ok": False, "error": "ya_reclamada", "estado": activo.estado,
                    "cancha_id": activo.cancha_id}
        activo.telefono_contacto = telefono_contacto or activo.telefono_contacto
        activo.dni = dni or activo.dni
        activo.ruc = ruc or activo.ruc
        activo.relacion = relacion or activo.relacion
        activo.lat = lat if lat is not None else activo.lat
        activo.lng = lng if lng is not None else activo.lng
        activo.solicitante_lat = (
            solicitante_lat if solicitante_lat is not None else activo.solicitante_lat)
        activo.solicitante_lng = (
            solicitante_lng if solicitante_lng is not None else activo.solicitante_lng)
        activo.foto_evidencia_url = foto_evidencia_url or activo.foto_evidencia_url
        activo.nota_reclamante = nota_reclamante or activo.nota_reclamante
        if activo.estado == "pendiente_triage":
            _notificar_admin(
                f"🔁 Recordatorio de reclamo pendiente\n"
                f"Local: {activo.nombre_local}\n"
                f"Código: {activo.codigo}\n"
                f"(el reclamante reenvió la solicitud, sigue esperando tu revisión)")
        return {"ok": True, "reclamo_id": activo.id, "codigo": activo.codigo,
                "estado": activo.estado, "reenviado": True, "ya_existia": True}

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
        solicitante_nombre=solicitante_nombre or "",
        foto_evidencia_url=foto_evidencia_url or "",
        nota_reclamante=nota_reclamante or "",
        telefono_contacto=telefono_contacto,
        dni=dni,
        nombre_titular=nombre_titular,
        ruc=ruc,
        razon_social=razon_social,
        relacion=relacion,
        lat=lat,
        lng=lng,
        solicitante_lat=solicitante_lat,
        solicitante_lng=solicitante_lng,
    )
    stores.reclamos.append(r)
    _notificar_admin(
        f"🟢 Nuevo reclamo de cancha en Pichangol\n"
        f"Local: {nombre_local}\n"
        f"Relación: {relacion or 's/d'}\n"
        f"Titular (DNI {dni or 's/n'}): {nombre_titular or 's/d'}\n"
        + (f"RUC {ruc}: {razon_social or 's/d'}\n" if ruc else "")
        + f"Cuenta: {solicitante_id}"
        + (f" ({solicitante_nombre})" if solicitante_nombre else "") + "\n"
        f"WhatsApp del dueño: {telefono_contacto or '⚠️ no dejó número'}\n"
        + (f"Nota: {nota_reclamante}\n" if nota_reclamante else "")
        + (f"Foto de evidencia: {foto_evidencia_url}\n" if foto_evidencia_url else "")
        + f"Código: {codigo}\n"
        f"Verifícalo y, para activarla, responde aquí: APROBAR {codigo}  "
        f"(o RECHAZAR {codigo}). También puedes usar el panel de Reclamos.")
    return {"ok": True, "reclamo_id": r.id, "codigo": codigo, "estado": r.estado}


def _coincidencia_ubicacion(r: ReclamoPropiedad) -> dict:
    """Contrasta el GPS del dispositivo del reclamante contra la ubicación de la
    cancha. Devuelve la distancia y si "coincide" (dentro del radio permitido)."""
    if (r.solicitante_lat is None or r.solicitante_lng is None
            or r.lat is None or r.lng is None):
        return {"tiene_ubicacion": False, "distancia_m": None, "coincide": False}
    dist = _distancia_m(r.lat, r.lng, r.solicitante_lat, r.solicitante_lng)
    return {"tiene_ubicacion": True, "distancia_m": round(dist),
            "coincide": dist <= config.RECLAMO_UBICACION_MAX_M}


def _enriquecer(r: ReclamoPropiedad) -> dict:
    """Serializa el reclamo + datos derivados para el panel (fecha/hora ya va en
    creado_en; sumamos la coincidencia de ubicación)."""
    d = como_dict(r)
    d.update(_coincidencia_ubicacion(r))
    return d


def _revocar_cancha_al_rechazar(r: ReclamoPropiedad) -> None:
    """Al RECHAZAR un reclamo, la cancha deja de estar verificada/activa (si ese
    reclamo era el que la sostenía). Así el rechazo se refleja en la app: se quita
    "Verificada" y se deshabilitan las reservas. No revoca si aún queda OTRO
    reclamo activo (bloqueante) para la misma cancha."""
    otro_activo = any(
        o.id != r.id and o.cancha_id == r.cancha_id
        and o.estado in _ESTADOS_BLOQUEANTES
        for o in stores.reclamos
    )
    if otro_activo:
        return
    c = stores.canchas.get(r.cancha_id)
    if c is not None:
        c.verificada = False
        c.verificada_en_persona = False
        c.metodo_verificacion = None


def _cerrar_duplicados(r: ReclamoPropiedad) -> None:
    """Al avanzar un reclamo hacia su activación, rechaza otros reclamos NO
    terminales de la misma cancha (duplicados por reintentos previos a la
    idempotencia de crear_reclamo)."""
    for otro in stores.reclamos:
        if otro.id != r.id and otro.cancha_id == r.cancha_id \
                and otro.estado not in _ESTADOS_TERMINALES:
            otro.estado = "rechazada"
            otro.decidido_en = ahora()
            otro.nota = f"Duplicado: la cancha ya fue activada por el reclamo #{r.id}."


def _rechazar_hermanos_lugar(r: ReclamoPropiedad, nota: str) -> int:
    """Al RECHAZAR/LIBERAR un lugar, rechaza también los OTROS reclamos NO
    terminales del MISMO lugar (mismo cancha_id o ≤ _MISMO_LUGAR_M metros). Así un
    rechazo deja el lugar REALMENTE libre para reclamar de nuevo, sin stragglers
    que quedaron pendientes por reintentos o por carreras al reiniciar el backend.
    Devuelve cuántos reclamos hermanos cerró."""
    n = 0
    for otro in _reclamos_del_lugar(r.cancha_id):
        if otro.id != r.id and otro.estado not in _ESTADOS_TERMINALES:
            otro.estado = "rechazada"
            otro.decidido_en = ahora()
            otro.nota = nota
            n += 1
    return n


def liberar_lugar(reclamo_id: int, revisor: str | None = None) -> dict:
    """Admin: LIBERA un lugar. Rechaza el reclamo dado y TODOS los reclamos NO
    terminales del mismo lugar, y revoca la cancha si estaba sostenida por él. Deja
    la ficha reclamable de nuevo de un toque (para resolver lugares que quedaron
    'atascados' en revisión)."""
    r = _por_id(reclamo_id)
    if r is None:
        return {"ok": False, "error": "reclamo_no_existe"}
    nota = f"Lugar liberado por {revisor or 'admin'}."
    r.estado = "rechazada"
    r.decidido_en = ahora()
    r.nota = nota
    hermanos = _rechazar_hermanos_lugar(r, nota)
    _revocar_cancha_al_rechazar(r)
    return {"ok": True, "estado": "rechazada", "liberados": hermanos + 1}


def _por_id(reclamo_id: int) -> ReclamoPropiedad | None:
    return next((r for r in stores.reclamos if r.id == reclamo_id), None)


def _por_codigo(codigo: str) -> ReclamoPropiedad | None:
    """Reclamo más reciente con ese código (los códigos son de 6 dígitos)."""
    rs = [r for r in stores.reclamos if r.codigo == codigo]
    return rs[-1] if rs else None


def aprobar_por_codigo(codigo: str, revisor: str | None = None) -> dict:
    """Aprueba (activa) un reclamo a partir de su CÓDIGO. Usado por el webhook de
    WhatsApp: el admin responde 'APROBAR <código>'. Idempotente si ya estaba activa."""
    r = _por_codigo(codigo)
    if r is None:
        return {"ok": False, "error": "codigo_invalido"}
    if r.estado == "activada":
        return {"ok": True, "ya": True, "estado": "activada",
                "nombre_local": r.nombre_local}
    res = aprobar_directo(r.id, revisor)
    res["nombre_local"] = r.nombre_local
    return res


def rechazar_por_codigo(codigo: str, revisor: str | None = None) -> dict:
    """Rechaza un reclamo a partir de su CÓDIGO (webhook de WhatsApp)."""
    r = _por_codigo(codigo)
    if r is None:
        return {"ok": False, "error": "codigo_invalido"}
    r.estado = "rechazada"
    r.decidido_en = ahora()
    r.nota = f"Rechazado por WhatsApp ({revisor or 'admin'}).".strip()
    _rechazar_hermanos_lugar(r, r.nota)
    _revocar_cancha_al_rechazar(r)
    return {"ok": True, "estado": "rechazada", "nombre_local": r.nombre_local}


def _reclamos_del_lugar(cancha_id: str) -> list[ReclamoPropiedad]:
    """Reclamos que corresponden a ESTA cancha: por mismo cancha_id, o por
    ubicación muy cercana (mismo lugar físico con distinto id, p. ej. tras
    re-descubrir/duplicar la misma cancha de Google). Evita que un reclamo VIEJO
    con distinto id 'secuestre' la ficha cuando ya hay uno nuevo del mismo lugar."""
    directos = [r for r in stores.reclamos if r.cancha_id == cancha_id]
    # Coordenadas de referencia del lugar: las de la cancha registrada y las de
    # sus propios reclamos directos.
    refs: list[tuple[float, float]] = []
    c = stores.canchas.get(cancha_id)
    if c is not None and c.lat_declarada is not None and c.lng_declarada is not None:
        refs.append((c.lat_declarada, c.lng_declarada))
    for r in directos:
        if r.lat is not None and r.lng is not None:
            refs.append((r.lat, r.lng))
    if not refs:
        return directos
    vistos = {id(r) for r in directos}
    pool = list(directos)
    for r in stores.reclamos:
        if id(r) in vistos or r.lat is None or r.lng is None:
            continue
        if any(_distancia_m(la, lo, r.lat, r.lng) <= _MISMO_LUGAR_M for la, lo in refs):
            pool.append(r)
    return pool


def estado(cancha_id: str, solicitante: str | None = None) -> dict:
    pool = _reclamos_del_lugar(cancha_id)
    if not pool:
        return {"existe": False}
    # Elegimos el reclamo REPRESENTATIVO del lugar (los ids crecen monótonos, así
    # que id mayor = más reciente):
    #  1. el reclamo VIGENTE (activo/bloqueante) más reciente — un reclamo vivo
    #     nunca debe quedar oculto tras un rechazo viejo del mismo lugar;
    #  2. si ninguno está vigente y quien pregunta tiene reclamo, el suyo más
    #     reciente (para que vea SU estado, no el de un tercero);
    #  3. en última instancia, el más reciente.
    activos = [r for r in pool if r.estado in _ESTADOS_BLOQUEANTES]
    if activos:
        r = max(activos, key=lambda x: x.id)
    elif solicitante and any(x.solicitante_id == solicitante for x in pool):
        r = max((x for x in pool if x.solicitante_id == solicitante),
                key=lambda x: x.id)
    else:
        r = max(pool, key=lambda x: x.id)
    c = stores.canchas.get(r.cancha_id)
    # 'verificada' para la APP = HABILITAR RESERVAS = PROPIEDAD aprobada, es decir
    # el reclamo llegó a "activada". NO se deriva de la bandera CanchaEstado.
    # verificada cruda, porque el subsistema de VERIFICACIÓN DE EXISTENCIA (IA)
    # también la escribe cuando el lugar existe — y existir ≠ ser dueño. Si se
    # leyera esa bandera, un reclamo recién creado (pendiente) aparecería como
    # verificado solo porque la cancha existe en Google. La propiedad se confiere
    # únicamente al aprobar/validar el reclamo (que deja estado="activada").
    verificada = (r.estado == "activada")
    return {
        "existe": True,
        "reclamo_id": r.id,
        "estado": r.estado,
        "panel_desbloqueado": r.estado in (
            "aprobado_triage", "pendiente_validacion", "activada"),
        "verificada": verificada,
        "verificada_en_persona": bool(c and c.verificada_en_persona),
        # ¿el reclamo es del que pregunta? (para que la app asigne dueño sin que
        # un tercero se apropie de una cancha de "legado" al sincronizar).
        "es_mio": bool(solicitante) and r.solicitante_id == solicitante,
    }


def triage(reclamo_id: int, aprobado: bool, revisor: str | None = None,
           nota: str | None = None) -> dict:
    r = _por_id(reclamo_id)
    if r is None:
        return {"ok": False, "error": "reclamo_no_existe"}
    # Guarda de estado: no se puede APROBAR un reclamo ya terminal (rechazado o
    # activado); habría que re-reclamar. Rechazar sí se permite desde cualquier
    # estado no-rechazado (permite REVOCAR una cancha ya activada).
    if aprobado and r.estado in _ESTADOS_TERMINALES:
        return {"ok": False, "error": "estado_invalido", "estado": r.estado}
    if not aprobado and r.estado == "rechazada":
        return {"ok": True, "estado": "rechazada", "ya": True}
    r.estado = "aprobado_triage" if aprobado else "rechazada"
    r.decidido_en = ahora()
    r.nota = f"Triage por {revisor or 'admin'}. {nota or ''}".strip()
    if not aprobado:
        # Un rechazo libera el lugar: cierra también los hermanos NO terminales del
        # mismo lugar (evita que quede uno pendiente "secuestrando" la ficha).
        _rechazar_hermanos_lugar(r, r.nota)
        _revocar_cancha_al_rechazar(r)
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
    _cerrar_duplicados(r)

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
        _notificar_reclamante_aprobado(r)  # push "¡tu cancha fue aprobada!"
        return {"ok": True, "estado": "activada", "verificada": True,
                "distancia_m": round(dist) if dist is not None else None}

    # Modo manual: queda validada pero la activa el admin.
    r.estado = "validada_pendiente_admin"
    _notificar_admin(
        f"🟡 Cancha validada en sitio, falta tu activación\n"
        f"Local: {r.nombre_local}\nCódigo: {r.codigo}")
    return {"ok": True, "estado": "validada_pendiente_admin", "verificada": False,
            "distancia_m": round(dist) if dist is not None else None}


def _gate_ubicacion(r: ReclamoPropiedad) -> dict | None:
    """Si el admin exige ubicación coincidente, valida el GPS del reclamante
    contra la cancha. Devuelve el dict de error si NO pasa, o None si pasa/no se
    exige. Se aplica en TODA activación (aprobar_directo y activar_admin)."""
    if not exigir_ubicacion():
        return None
    co = _coincidencia_ubicacion(r)
    if not co["tiene_ubicacion"]:
        return {"ok": False, "error": "sin_ubicacion_solicitante"}
    if not co["coincide"]:
        return {"ok": False, "error": "ubicacion_no_coincide",
                "distancia_m": co["distancia_m"],
                "max_m": config.RECLAMO_UBICACION_MAX_M}
    return None


def aprobar_directo(reclamo_id: int, revisor: str | None = None) -> dict:
    """Aprobación del admin. Su efecto depende del MODO de la cancha:

    - "marcha_blanca" (piloto): aprueba y ACTIVA al instante (verificada=True),
      sin validación en sitio. Método 'panel_admin'.
    - "nuevo_flujo": aprueba el triage pero NO activa; deja la cancha pendiente
      de VALIDACIÓN EN SITIO (código + GPS) antes de habilitar reservas.
    """
    r = _por_id(reclamo_id)
    if r is None:
        return {"ok": False, "error": "reclamo_no_existe"}
    # Guarda de estado: no se aprueba un reclamo ya terminal (rechazado/activado).
    # Reactivar un rechazado saltándose el flujo era un bug de seguridad.
    if r.estado in _ESTADOS_TERMINALES:
        return {"ok": False, "error": "estado_invalido", "estado": r.estado}

    err = _gate_ubicacion(r)
    if err is not None:
        return err

    _cerrar_duplicados(r)
    modo = stores.modo_aprobacion(r.cancha_id)
    if modo == "nuevo_flujo":
        r.estado = "pendiente_validacion"
        r.decidido_en = ahora()
        r.nota = (f"Aprobado en triage (nuevo flujo) por {revisor or 'admin'}: "
                  f"requiere validación en sitio.").strip()
        _notificar_admin(
            f'🟡 "{r.nombre_local}" aprobada en triage (nuevo flujo).\n'
            f"Falta VALIDACIÓN EN SITIO. Código: {r.codigo}")
        return {"ok": True, "estado": "pendiente_validacion", "verificada": False,
                "requiere_validacion_sitio": True, "modo": modo}

    # marcha_blanca: activa al instante (comportamiento del piloto).
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
    _notificar_reclamante_aprobado(r)  # push "¡tu cancha fue aprobada!"
    return {"ok": True, "estado": "activada", "verificada": True, "modo": modo}


def activar_admin(reclamo_id: int) -> dict:
    """Activación manual por el admin (cuando VALIDADOR_ACTIVA_AUTOMATICO=0)."""
    r = _por_id(reclamo_id)
    if r is None:
        return {"ok": False, "error": "reclamo_no_existe"}
    if r.estado in _ESTADOS_TERMINALES:
        return {"ok": False, "error": "estado_invalido", "estado": r.estado}
    err = _gate_ubicacion(r)  # mismo anti-fraude que aprobar_directo
    if err is not None:
        return err
    _cerrar_duplicados(r)
    r.estado = "activada"
    c = stores.cancha(r.cancha_id)
    c.verificada = True
    c.verificada_en_persona = True
    c.metodo_verificacion = "en_sitio"
    _notificar_reclamante_aprobado(r)  # push "¡tu cancha fue aprobada!"
    return {"ok": True, "estado": "activada", "verificada": True}


def listar(estado_filtro: str | None = None) -> list[dict]:
    rs = stores.reclamos
    if estado_filtro:
        rs = [r for r in rs if r.estado == estado_filtro]
    return [_enriquecer(r) for r in rs]
