"""Endpoints de VERIFICACIÓN DE PROPIEDAD (OTP por WhatsApp + aprobación manual)."""

from __future__ import annotations

import hashlib
import re
import time
import urllib.parse
from collections import defaultdict, deque
from xml.sax.saxutils import escape as _xml_esc

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel

import config
from db.store import stores
from models import (
    AprobarManualRequest,
    OtpConfirmarRequest,
    OtpSolicitarRequest,
    ReclamoRequest,
    TriageRequest,
    ValidarReclamoRequest,
)
from propiedad import identidad, reclamos, service, twilio_adapter, whatsapp_adapter

router = APIRouter(prefix="/propiedad", tags=["propiedad"])


def _require_admin(x_admin_token: str | None = Header(default=None)) -> None:
    """Auth de operador (torre de control). Protege los endpoints ADMINISTRATIVOS
    de propiedad para que sólo el equipo (con ADMIN_PANEL_TOKEN) apruebe/rechace/
    configure y vea datos personales. Sin token configurado, fail-closed (503).
    La app del dueño NO usa estos endpoints; usa /reclamo, /estado, /otp, etc."""
    if not config.ADMIN_PANEL_TOKEN:
        raise HTTPException(status_code=503, detail="admin_no_configurado")
    if x_admin_token != config.ADMIN_PANEL_TOKEN:
        raise HTTPException(status_code=401, detail="token_invalido")


_ADMIN = [Depends(_require_admin)]


def _require_app_key(x_app_key: str | None = Header(default=None)) -> None:
    """Gatea los endpoints PÚBLICOS de la app: solo el APK oficial (que envía
    X-App-Key) puede llamarlos. Evita que un cliente externo (curl) cree reclamos
    o consulte identidad contra el backend público. Si APP_API_KEY no está
    configurada, no se exige (despliegue gradual)."""
    if not config.APP_API_KEY:
        return
    if x_app_key != config.APP_API_KEY:
        raise HTTPException(status_code=401, detail="app_key_invalida")


_APP = [Depends(_require_app_key)]


# Rate-limit en memoria por IP (anti-spam). Ventana deslizante simple; suficiente
# para el piloto (una sola instancia). Se resetea si el proceso reinicia.
_rate_hits: dict[str, "deque[float]"] = defaultdict(deque)


def _client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "?"


def _rate_limit(request: Request) -> None:
    """Limita las solicitudes por IP a los endpoints con efecto externo."""
    limite = config.RECLAMO_RATE_LIMIT
    if limite <= 0:
        return
    ventana = config.RECLAMO_RATE_WINDOW_S
    ip = _client_ip(request)
    ahora = time.monotonic()
    dq = _rate_hits[ip]
    while dq and (ahora - dq[0]) > ventana:
        dq.popleft()
    if len(dq) >= limite:
        raise HTTPException(status_code=429, detail="demasiadas_solicitudes")
    dq.append(ahora)


# App key + rate-limit (para POST con efecto externo: reclamo, OTP).
_APP_RL = [Depends(_require_app_key), Depends(_rate_limit)]


# --- Consulta de identidad (DNI persona / RUC negocio) vía Factiliza ---
@router.get("/dni/{dni}", dependencies=_APP)
def get_dni(dni: str) -> dict:
    return identidad.consultar_dni(dni)


@router.get("/cedula/{cedula}", dependencies=_APP)
def get_cedula(cedula: str) -> dict:
    """Consulta la cédula ecuatoriana (CipherByte). Espejo de /dni para EC."""
    return identidad.consultar_cedula(cedula)


# Pimienta fija para el hash del DNI: no guardamos el número (Ley 29733), solo su
# hash, y así podemos comprobar unicidad sin exponer el dato.
_DNI_PEPPER = "pichangol-dni-v1"


def _dni_hash(dni: str) -> str:
    return hashlib.sha256((dni.strip() + "|" + _DNI_PEPPER).encode()).hexdigest()


class VerificarDniReq(BaseModel):
    dni: str
    email: str
    pais: str = "PE"  # 'PE' → DNI (Factiliza); 'EC' → cédula (CipherByte)


@router.post("/verificar-dni", dependencies=_APP)
def post_verificar_dni(req: VerificarDniReq) -> dict:
    """Verifica identidad por documento con la regla ANTI-FRAUDE
    **1 documento = 1 cuenta**. Valida contra el registro oficial del país
    (Perú: DNI/RENIEC vía Factiliza; Ecuador: cédula vía CipherByte) y liga el
    documento (solo su HASH) al correo. Si ese documento ya está verificado en
    OTRA cuenta, rechaza (`dni_en_uso`)."""
    email = req.email.strip().lower()
    if not email:
        return {"ok": False, "error": "correo_requerido"}
    pais = (req.pais or "PE").strip().upper()
    # Registro oficial según el país. Default Perú (compat. con clientes viejos).
    if pais == "EC":
        data = identidad.consultar_cedula(req.dni)
    else:
        data = identidad.consultar_dni(req.dni)
    if not data.get("ok"):
        return data  # {ok: False, error: ...} (documento inválido / no encontrado)
    # Hash del NÚMERO (no guardamos el dato): DNI (8) y cédula (10) no colisionan;
    # la regla "1 documento = 1 cuenta" vale entre países.
    h = _dni_hash(req.dni)
    dueno = stores.dni_verificados.get(h)
    if dueno and dueno != email:
        return {"ok": False, "error": "dni_en_uso"}
    stores.dni_verificados[h] = email  # liga (o confirma) el documento a la cuenta
    return data  # ok + nombre_completo + fecha_nacimiento


@router.get("/ruc/{ruc}", dependencies=_APP)
def get_ruc(ruc: str) -> dict:
    return identidad.consultar_ruc(ruc)


# --- Reclamo con intervención humana + validación en sitio ---
@router.post("/reclamo", dependencies=_APP_RL)
def post_reclamo(req: ReclamoRequest) -> dict:
    """El dueño presiona 'Reclamar': avisa al admin por WhatsApp con un código."""
    return reclamos.crear_reclamo(
        req.cancha_id, req.solicitante_id, req.nombre_local,
        req.telefono_contacto, req.dni, req.ruc, req.relacion,
        req.lat, req.lng, req.solicitante_lat, req.solicitante_lng,
        solicitante_nombre=req.solicitante_nombre,
        foto_evidencia_url=req.foto_evidencia_url,
        nota_reclamante=req.nota_reclamante)


@router.get("/reclamo/{cancha_id}", dependencies=_APP)
def get_reclamo(cancha_id: str, solicitante: str = "") -> dict:
    return reclamos.estado(cancha_id, solicitante or None)


class BorrarMisReclamosRequest(BaseModel):
    solicitante: str


@router.post("/reclamos/borrar-mios", dependencies=_APP)
def post_borrar_mis_reclamos(req: BorrarMisReclamosRequest) -> dict:
    """El DUEÑO borra SUS propios reclamos (los que él inició) desde la app, al
    'dejar en virgen'. Así sus canchas reclamadas también desaparecen de la torre
    de control y puede volver a reclamarlas de cero. Solo toca los del correo que
    manda; NO borra reclamos de otros usuarios (por eso no necesita token admin).
    El middleware persiste el snapshot tras el POST."""
    n = stores.borrar_reclamos_de(req.solicitante)
    return {"ok": True, "borrados": n}


@router.get("/lugar-reclamado", dependencies=_APP)
def get_lugar_reclamado(lat: float, lng: float, cancha_id: str = "",
                        solicitante: str = "") -> dict:
    """¿El lugar (lat/lng, o cancha_id) ya tiene un reclamo activo? Para que la
    ficha de una cancha descubierta bloquee el botón "Reclamar" si ya la
    reclamaron."""
    return reclamos.lugar_reclamado(lat, lng, cancha_id, solicitante or None)


@router.post("/reclamo/{reclamo_id}/triage", dependencies=_ADMIN)
def post_triage(reclamo_id: int, req: TriageRequest) -> dict:
    """El admin vetea al reclamante y aprueba/rechaza (desbloquea el panel)."""
    return reclamos.triage(reclamo_id, req.aprobado, req.revisor, req.nota)


@router.post("/reclamo/{reclamo_id}/aprobar", dependencies=_ADMIN)
def post_aprobar_directo(reclamo_id: int, req: TriageRequest) -> dict:
    """Aprobación DIRECTA (piloto): el admin aprueba y la cancha queda ACTIVA al
    instante (verificada=True), sin validación en sitio. Mismo efecto que el
    botón 'Aprobar y activar' del panel web."""
    return reclamos.aprobar_directo(reclamo_id, req.revisor)


@router.post("/reclamo/{reclamo_id}/listo-para-validar", dependencies=_APP)
def post_listo(reclamo_id: int) -> dict:
    """El dueño guardó su info: pasa a pendiente de validación en sitio."""
    return reclamos.listo_para_validar(reclamo_id)


@router.post("/reclamo/validar", dependencies=_APP)
def post_validar(req: ValidarReclamoRequest) -> dict:
    """El motorizado ingresa el código en el sitio; su GPS debe coincidir."""
    return reclamos.validar_en_sitio(
        req.codigo, req.lat, req.lng, req.validador, req.fotos_urls)


@router.post("/reclamo/{reclamo_id}/activar", dependencies=_ADMIN)
def post_activar(reclamo_id: int) -> dict:
    """Activación manual por el admin (si VALIDADOR_ACTIVA_AUTOMATICO=0)."""
    return reclamos.activar_admin(reclamo_id)


@router.post("/reclamo/{reclamo_id}/liberar", dependencies=_ADMIN)
def post_liberar_lugar(reclamo_id: int, req: TriageRequest) -> dict:
    """LIBERA el lugar: rechaza este reclamo y todos los NO terminales del mismo
    lugar, y revoca la cancha. Deja la ficha reclamable de nuevo (resuelve lugares
    atascados en 'revisión')."""
    return reclamos.liberar_lugar(reclamo_id, req.revisor)


@router.get("/reclamos", dependencies=_ADMIN)
def get_reclamos(estado: str | None = None) -> list[dict]:
    """ADMIN: lista completa (incluye datos personales del reclamante). Protegido
    por token para no exponer DNI/teléfono/GPS (Ley 29733)."""
    return reclamos.listar(estado)


# --- Configuración del MODO de aprobación (marcha_blanca | nuevo_flujo) ---
@router.get("/config/modo", dependencies=_ADMIN)
def get_modo() -> dict:
    """Modo de aprobación: global + overrides por cancha + modos válidos."""
    return reclamos.config_modo()


@router.put("/config/modo", dependencies=_ADMIN)
def put_modo_global(req: dict) -> dict:
    """Cambia el modo GLOBAL (aplica a todas las canchas sin override)."""
    return reclamos.set_modo_global(str(req.get("modo", "")))


@router.put("/config/modo/cancha", dependencies=_ADMIN)
def put_modo_cancha(req: dict) -> dict:
    """Fija o limpia el override de una cancha. modo=null/'' limpia el override."""
    return reclamos.set_modo_cancha(str(req.get("cancha_id", "")), req.get("modo"))


@router.get("/estado/{cancha_id}", dependencies=_APP)
def get_estado(cancha_id: str) -> dict:
    return service.estado(cancha_id)


@router.post("/otp/solicitar", dependencies=_APP_RL)
def post_solicitar(req: OtpSolicitarRequest) -> dict:
    """Envía un código al teléfono del local. Si WhatsApp no está configurado,
    corre en modo stub (no envía nada real)."""
    return service.solicitar(req.cancha_id, req.telefono)


@router.post("/otp/confirmar", dependencies=_APP)
def post_confirmar(req: OtpConfirmarRequest) -> dict:
    """Valida el código. Si coincide (y el número prueba propiedad), marca la
    cancha como verificada por su dueño."""
    return service.confirmar(
        req.cancha_id, req.codigo, req.solicitante_id, req.telefono_publico)


@router.post("/aprobar-manual", dependencies=_ADMIN)
def post_aprobar_manual(req: AprobarManualRequest) -> dict:
    """Aprobación/rechazo manual de propiedad (uso interno del equipo)."""
    return service.aprobar_manual(
        req.cancha_id, req.solicitante_id, req.aprobado, req.revisor, req.nota)


# --- Webhook ENTRANTE de WhatsApp (Twilio): aprobar/rechazar respondiendo ---
_PAT_CODIGO = re.compile(r"\d{6}")


def _norm_tel(t: str) -> str:
    return "".join(ch for ch in t if ch.isdigit())


@router.post("/webhook/whatsapp")
async def webhook_whatsapp(request: Request) -> Response:
    """El admin APRUEBA/RECHAZA un reclamo respondiendo el WhatsApp del aviso.

    Responde 'APROBAR <código>' o 'RECHAZAR <código>'. Triple barrera de
    seguridad: (1) firma X-Twilio-Signature válida, (2) remitente ==
    PICHANGOL_ADMIN_WHATSAPP, (3) código existente. Contesta por el mismo chat
    con TwiML.
    """
    # Twilio envía application/x-www-form-urlencoded. Parseamos el cuerpo crudo
    # (sin depender de python-multipart).
    raw = (await request.body()).decode("utf-8", "ignore")
    parsed = urllib.parse.parse_qs(raw, keep_blank_values=True)
    params = {k: v[0] for k, v in parsed.items()}

    # 1) Firma de Twilio (varias URLs candidatas por el proxy de Railway).
    firma = request.headers.get("X-Twilio-Signature", "")
    su = str(request.url)
    urls = [config.TWILIO_WEBHOOK_URL, su]
    if su.startswith("http://"):
        urls.append("https://" + su[len("http://"):])
    if not twilio_adapter.validar_firma_multi(urls, params, firma):
        return Response(status_code=403)

    # 2) El remitente debe ser el admin configurado.
    de = _norm_tel(params.get("From", "").replace("whatsapp:", ""))
    admin = _norm_tel(config.PICHANGOL_ADMIN_WHATSAPP or "")
    if not admin or de != admin:
        return Response(status_code=403)

    def _twiml(msg: str) -> Response:
        xml = ('<?xml version="1.0" encoding="UTF-8"?>'
               f"<Response><Message>{msg}</Message></Response>")
        return Response(content=xml, media_type="application/xml")

    # 3) Parseo del comando.
    texto = (params.get("Body") or "").strip()
    up = texto.upper()
    m = _PAT_CODIGO.search(texto)
    if m is None:
        return _twiml("Responde: APROBAR <código> o RECHAZAR <código> "
                      "(el código de 6 dígitos del aviso).")
    codigo = m.group(0)

    if "RECHAZ" in up:
        r = reclamos.rechazar_por_codigo(codigo, revisor="admin_whatsapp")
        if not r.get("ok"):
            return _twiml(f"No encontré un reclamo con el código {codigo}.")
        return _twiml(f'❌ Reclamo de "{_xml_esc(r.get("nombre_local", ""))}" '
                      f"RECHAZADO.")

    if any(k in up for k in ("APROB", "APRUEB", "OK", "SI", "SÍ", "ACTIVA")):
        r = reclamos.aprobar_por_codigo(codigo, revisor="admin_whatsapp")
        if not r.get("ok"):
            err = r.get("error", "")
            if err == "codigo_invalido":
                return _twiml(f"No encontré un reclamo con el código {codigo}.")
            if err == "estado_invalido":
                return _twiml(
                    f"No se pudo aprobar: el reclamo {codigo} ya está "
                    f'"{r.get("estado", "")}". Si quieres, pide un nuevo reclamo.')
            if err == "sin_ubicacion_solicitante":
                return _twiml("No se pudo aprobar: no hay ubicación del "
                              "reclamante para validar que estaba en la cancha.")
            if err == "ubicacion_no_coincide":
                return _twiml(
                    f"No se pudo aprobar: el reclamante estuvo a "
                    f'{r.get("distancia_m", "?")} m de la cancha (máx '
                    f'{r.get("max_m", "?")} m).')
            return _twiml(f"No se pudo aprobar el reclamo {codigo}.")
        nombre = _xml_esc(r.get("nombre_local", ""))
        if r.get("ya"):
            return _twiml(f'"{nombre}" ya estaba activa. ✅')
        return _twiml(f'✅ "{nombre}" ACTIVADA. Ya acepta reservas.')

    return _twiml("No entendí. Responde: APROBAR <código> o RECHAZAR <código>.")


@router.get("/canal")
def get_canal() -> dict:
    """Informativo: qué canales de OTP están activos en esta build. El canal
    'activo' respeta OTP_CANAL_PREFERIDO y cae al siguiente disponible."""
    import config

    wa = whatsapp_adapter.disponible()
    twa = twilio_adapter.disponible_whatsapp()
    sms = twilio_adapter.disponible()
    disp = {"whatsapp": wa, "twilio_whatsapp": twa, "sms": sms}
    orden = sorted(disp, key=lambda k: 0 if k == config.OTP_CANAL_PREFERIDO else 1)
    activo = next((k for k in orden if disp[k]), "stub")
    return {"whatsapp": wa, "twilio_whatsapp": twa, "sms": sms, "activo": activo}
