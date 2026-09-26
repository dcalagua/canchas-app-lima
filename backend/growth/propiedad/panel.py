"""PANEL WEB de administración (piloto).

El admin de Pichangol entra desde el navegador, ve los reclamos de canchas y los
aprueba/rechaza. La aprobación es DIRECTA: al aprobar, la cancha queda activa
(sin validación en sitio todavía).

Seguridad: login por USUARIO + CONTRASEÑA (env `ADMIN_PANEL_USUARIOS`) que
emite una sesión firmada con expiración (ver `propiedad/admin_auth.py`); el
token clásico `ADMIN_PANEL_TOKEN` sigue aceptado como respaldo. Nada viaja en
la URL: la página guarda la sesión en el navegador (localStorage) y la manda
en la cabecera X-Admin-Token. Sin `ADMIN_PANEL_TOKEN`, el panel responde 503.
"""

from __future__ import annotations

import os
import base64
import time

from datetime import datetime, timezone

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

import config
import empresa
from convocatorias import service as convocatorias_service
from db import pg
from db.store import stores
import storage_limpieza
from propiedad import admin_auth, reclamos

router = APIRouter(tags=["panel"])


def _check(token: str | None) -> None:
    if not config.ADMIN_PANEL_TOKEN:
        raise HTTPException(status_code=503, detail="panel_no_configurado")
    if not admin_auth.token_admin_valido(token):
        raise HTTPException(status_code=401, detail="token_invalido")


# ── Login usuario+contraseña (+ segundo paso) ───────────────────────────────
# Anti fuerza bruta por IP REAL (X-Forwarded-For: Railway termina TLS en su
# proxy y `request.client.host` es siempre el proxy) y también POR USUARIO
# (rotar IPs no ayuda). Tras MAX_INTENTOS fallos seguidos bloquea BLOQUEO_S y
# el bloqueo se DUPLICA en cada racha (hasta BLOQUEO_MAX_S). En memoria (una
# instancia en Railway; se reinicia con el proceso, suficiente para frenar un
# ataque en línea).
_intentos: dict[str, tuple[int, float, float]] = {}  # clave -> (fallos, bloqueado_hasta, bloqueo_actual)
MAX_INTENTOS = 5
BLOQUEO_S = 60.0
BLOQUEO_MAX_S = 15 * 60.0
ACCESOS_MAX = 200


def _ip_de(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[0].strip()[:64] or "?"
    return (request.client.host if request.client else "?")[:64]


def _bloqueado(*claves: str) -> bool:
    ahora = time.time()
    return any(ahora < _intentos.get(k, (0, 0.0, 0.0))[1] for k in claves if k)


def _fallo(*claves: str) -> None:
    ahora = time.time()
    for k in claves:
        if not k:
            continue
        fallos, _hasta, bloqueo = _intentos.get(k, (0, 0.0, 0.0))
        fallos += 1
        if fallos >= MAX_INTENTOS:
            bloqueo = min(BLOQUEO_MAX_S, (bloqueo * 2) if bloqueo else BLOQUEO_S)
            _intentos[k] = (0, ahora + bloqueo, bloqueo)
        else:
            _intentos[k] = (fallos, 0.0, bloqueo)


def _exito(*claves: str) -> None:
    for k in claves:
        _intentos.pop(k, None)


def _acceso(evento: str, usuario: str, ip: str, detalle: str = "") -> None:
    """Bitácora de accesos (la ve el operador en Mantenimiento → Seguridad)."""
    stores.admin_accesos.append({"ts": int(time.time()), "evento": evento, "usuario": (usuario or "")[:120],
                                 "ip": ip, "detalle": detalle[:160]})
    del stores.admin_accesos[:-ACCESOS_MAX]
    print(f"[admin] {evento} usuario={usuario or '-'} ip={ip} {detalle}", flush=True)


def _qr_data_url(texto: str) -> str:
    """QR del otpauth:// como data URL PNG (lib qrcode ya empaquetada)."""
    try:
        import io
        import qrcode
        img = qrcode.make(texto, box_size=6, border=2)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:  # noqa: BLE001
        return ""


class LoginRequest(BaseModel):
    usuario: str
    clave: str
    dispositivo: str | None = None   # token "confío en este dispositivo" (d1.) si lo hay


class Login2faRequest(BaseModel):
    pre: str
    codigo: str
    recordar: bool = False


@router.get("/admin/api/gate")
def gate_info() -> dict:
    """Lo que la pantalla de login necesita saber (público, sin datos sensibles):
    si hay usuarios (entonces NO se ofrece "Entrar con token") y si hay 2.º paso."""
    return {"configurado": bool(config.ADMIN_PANEL_TOKEN), "usuarios": bool(admin_auth.usuarios_configurados()),
            "dos_pasos": admin_auth.dos_pasos_activo()}


def _respuesta_sesion(usuario: str, recordar: bool = False) -> dict:
    out = {"ok": True, "paso": "ok", "token": admin_auth.crear_sesion(usuario), "usuario": usuario}
    if recordar:
        out["dispositivo"] = admin_auth.crear_dispositivo(usuario)
    return out


@router.post("/admin/api/login")
def login(body: LoginRequest, request: Request) -> dict:
    """Paso 1: usuario+contraseña. Con 2FA activo devuelve un PRE-token y el
    paso que sigue (`codigo` si ya enroló su app, `enrolar` con el QR si no);
    si el navegador trae un dispositivo de confianza vigente, entra directo.
    503 si el panel/usuarios no están configurados; 429 si la IP o el usuario
    están bloqueados por intentos fallidos."""
    if not config.ADMIN_PANEL_TOKEN:
        raise HTTPException(status_code=503, detail="panel_no_configurado")
    if not admin_auth.usuarios_configurados():
        raise HTTPException(status_code=503, detail="usuarios_no_configurados")
    ip = _ip_de(request)
    usuario = (body.usuario or "").strip().lower()
    k_ip, k_usr = f"ip:{ip}", f"usr:{usuario}"
    if _bloqueado(k_ip, k_usr):
        _acceso("bloqueado", usuario, ip)
        raise HTTPException(status_code=429, detail="demasiados_intentos")
    if not admin_auth.credenciales_validas(body.usuario, body.clave):
        _fallo(k_ip, k_usr)
        _acceso("clave_mala", usuario, ip)
        raise HTTPException(status_code=401, detail="credenciales_invalidas")
    _exito(k_ip, k_usr)
    if not admin_auth.dos_pasos_activo():
        _acceso("login_ok", usuario, ip, "sin 2FA (ADMIN_2FA=0)")
        return _respuesta_sesion(usuario)
    if admin_auth.enrolado(usuario):
        if body.dispositivo and admin_auth.dispositivo_valido(body.dispositivo, usuario):
            _acceso("login_ok", usuario, ip, "dispositivo de confianza")
            return _respuesta_sesion(usuario)
        _acceso("clave_ok", usuario, ip, "espera código")
        return {"ok": True, "paso": "codigo", "pre": admin_auth.crear_pre_sesion(usuario), "usuario": usuario}
    sec = admin_auth.iniciar_enrolamiento(usuario)
    uri = admin_auth.otpauth_uri(usuario, sec)
    _acceso("clave_ok", usuario, ip, "debe enrolar 2FA")
    return {"ok": True, "paso": "enrolar", "pre": admin_auth.crear_pre_sesion(usuario), "usuario": usuario,
            "secreto": sec, "otpauth": uri, "qr": _qr_data_url(uri)}


@router.post("/admin/api/login/2fa")
def login_2fa(body: Login2faRequest, request: Request) -> dict:
    """Paso 2: código de la app (o código de recuperación XXXX-XXXX). Si el
    operador estaba enrolando, guarda su secreto y devuelve los códigos de
    recuperación UNA sola vez. `recordar` = dispositivo de confianza 30 días."""
    ip = _ip_de(request)
    usuario = admin_auth.usuario_de_pre_sesion(body.pre)
    if not usuario:
        raise HTTPException(status_code=401, detail="pre_invalido")
    k_ip, k_usr = f"ip:{ip}", f"2fa:{usuario}"
    if _bloqueado(k_ip, k_usr):
        _acceso("bloqueado", usuario, ip, "2FA")
        raise HTTPException(status_code=429, detail="demasiados_intentos")
    codigo = (body.codigo or "").strip()
    if admin_auth.enrolado(usuario):
        if admin_auth.totp_valido(usuario, admin_auth.secreto_de(usuario), codigo):
            _exito(k_ip, k_usr)
            _acceso("login_ok", usuario, ip, "2FA app")
            return _respuesta_sesion(usuario, body.recordar)
        if "-" in codigo and admin_auth.usar_recuperacion(usuario, codigo):
            _exito(k_ip, k_usr)
            _acceso("login_ok", usuario, ip, f"código de recuperación (quedan {admin_auth.recuperacion_restantes(usuario)})")
            return {**_respuesta_sesion(usuario, body.recordar), "recuperacion_usada": True,
                    "recuperacion_restantes": admin_auth.recuperacion_restantes(usuario)}
        _fallo(k_ip, k_usr)
        _acceso("2fa_mal", usuario, ip)
        raise HTTPException(status_code=401, detail="codigo_invalido")
    rec = admin_auth.confirmar_enrolamiento(usuario, codigo)
    if rec is None:
        _fallo(k_ip, k_usr)
        _acceso("2fa_mal", usuario, ip, "enrolando")
        raise HTTPException(status_code=401, detail="codigo_invalido")
    _exito(k_ip, k_usr)
    _acceso("enrolado", usuario, ip)
    return {**_respuesta_sesion(usuario, body.recordar), "recuperacion": rec}


# ── Seguridad (Mantenimiento → Seguridad) ────────────────────────────────────
class CorreoRequest(BaseModel):
    correo: str


class CodigoRequest(BaseModel):
    codigo: str


def _operador(x_admin_token: str | None) -> str:
    _check(x_admin_token)
    return admin_auth.usuario_de_sesion(x_admin_token)


@router.get("/admin/api/seguridad")
def get_seguridad(x_admin_token: str | None = Header(default=None)) -> dict:
    yo = _operador(x_admin_token)
    usuarios = []
    for correo in admin_auth.usuarios_configurados():
        usuarios.append({"correo": correo, "enrolado": admin_auth.enrolado(correo),
                         "desde": admin_auth.enrolado_desde(correo),
                         "recuperacion_restantes": admin_auth.recuperacion_restantes(correo)})
    return {"dos_pasos": admin_auth.dos_pasos_activo(), "yo": yo, "token_clasico": yo == "token",
            "usuarios": usuarios, "accesos": list(reversed(stores.admin_accesos[-60:])),
            "sesion_horas": admin_auth.SESION_HORAS, "dispositivo_dias": admin_auth.DISPOSITIVO_DIAS}


@router.post("/admin/api/seguridad/2fa/restablecer")
def post_seguridad_restablecer(body: CorreoRequest, request: Request,
                               x_admin_token: str | None = Header(default=None)) -> dict:
    """Quita el 2.º paso de un operador (perdió el teléfono): vuelve a enrolar
    en su próximo login. Lo hace otro operador con sesión, o el token clásico
    de ADMIN_PANEL_TOKEN (último recurso, desde Railway)."""
    yo = _operador(x_admin_token)
    correo = (body.correo or "").strip().lower()
    if correo not in admin_auth.usuarios_configurados():
        raise HTTPException(status_code=404, detail="usuario_desconocido")
    admin_auth.restablecer(correo)
    _acceso("2fa_restablecido", correo, _ip_de(request), f"por {yo}")
    return {"ok": True}


@router.post("/admin/api/seguridad/2fa/recuperacion")
def post_seguridad_recuperacion(body: CodigoRequest, request: Request,
                                x_admin_token: str | None = Header(default=None)) -> dict:
    """Códigos de recuperación nuevos para MÍ (invalida los anteriores). Exige
    un código vigente de la app para confirmar que soy yo."""
    yo = _operador(x_admin_token)
    if yo in ("", "token") or not admin_auth.enrolado(yo):
        raise HTTPException(status_code=400, detail="sin_2fa")
    if not admin_auth.totp_valido(yo, admin_auth.secreto_de(yo), body.codigo):
        raise HTTPException(status_code=401, detail="codigo_invalido")
    rec = admin_auth.generar_recuperacion(yo)
    _acceso("recuperacion_nueva", yo, _ip_de(request))
    return {"ok": True, "recuperacion": rec}


@router.post("/admin/api/seguridad/dispositivos/olvidar")
def post_seguridad_olvidar(request: Request, x_admin_token: str | None = Header(default=None)) -> dict:
    """Invalida todos mis "dispositivos de confianza": el próximo login vuelve a pedir el código."""
    yo = _operador(x_admin_token)
    if yo in ("", "token"):
        raise HTTPException(status_code=400, detail="sin_usuario")
    admin_auth.olvidar_dispositivos(yo)
    _acceso("dispositivos_olvidados", yo, _ip_de(request))
    return {"ok": True}


class DecidirRequest(BaseModel):
    aprobado: bool
    revisor: str | None = None


class LiberarRequest(BaseModel):
    revisor: str | None = None


class ModoRequest(BaseModel):
    modo: str


class ModoCanchaRequest(BaseModel):
    cancha_id: str
    modo: str | None = None


class ExigirUbicacionRequest(BaseModel):
    exigir: bool


class ContactoRequest(BaseModel):
    contactos: dict[str, str]


class CanalRequest(BaseModel):
    canal: str


class EmpresaRequest(BaseModel):
    datos: dict[str, str]


class BancoRequest(BaseModel):
    pct: float


class ComisionSaldoRequest(BaseModel):
    # Tarifa de la comisión de reserva cuando se cobra del SALDO (billetera).
    # pct=None (o reset) → volver a la estándar (COMISION_PORC/COMISION_MIN).
    pct: float | None = None
    min_soles: float | None = None
    reset: bool = False


class MarketingConfigRequest(BaseModel):
    landing_soles: float | None = None
    redes_soles: float | None = None
    presencia_soles: float | None = None
    posts_limite_mes: int | None = None
    # Fase 3: tarifa propia para CLUBES/canchas. 0 (o vacío) = usar la base.
    landing_soles_club: float | None = None
    redes_soles_club: float | None = None
    presencia_soles_club: float | None = None


class ComisionRequest(BaseModel):
    # % por cobro digital de matrícula, por país (efectivo = 0%).
    pe: float | None = None
    ec: float | None = None
    bo: float | None = None


@router.get("/admin/api/sesion")
def sesion(x_admin_token: str | None = Header(default=None)) -> dict:
    """Valida el token (lo usa la pantalla de login del panel)."""
    _check(x_admin_token)
    return {"ok": True}


@router.get("/admin/api/reclamos")
def listar(estado: str | None = None,
           x_admin_token: str | None = Header(default=None)) -> list[dict]:
    _check(x_admin_token)
    return reclamos.listar(estado)


@router.post("/admin/api/reclamo/{reclamo_id}/decidir")
def decidir(reclamo_id: int, req: DecidirRequest,
            x_admin_token: str | None = Header(default=None)) -> dict:
    """Aprobar = aprobación directa (cancha activa). Rechazar = triage rechazado."""
    _check(x_admin_token)
    if req.aprobado:
        return reclamos.aprobar_directo(reclamo_id, req.revisor)
    return reclamos.triage(reclamo_id, False, req.revisor)


@router.post("/admin/api/reclamo/{reclamo_id}/liberar")
def liberar_lugar_panel(reclamo_id: int, req: LiberarRequest,
                        x_admin_token: str | None = Header(default=None)) -> dict:
    """LIBERA el lugar: rechaza este reclamo y todos los del mismo lugar, y revoca
    la cancha. La ficha vuelve a ser reclamable (resuelve lugares atascados)."""
    _check(x_admin_token)
    return reclamos.liberar_lugar(reclamo_id, req.revisor or "panel")


@router.get("/admin/api/modo")
def get_modo_admin(x_admin_token: str | None = Header(default=None)) -> dict:
    """Modo de aprobación de canchas (torre de control)."""
    _check(x_admin_token)
    return reclamos.config_modo()


@router.post("/admin/api/modo")
def set_modo_admin(req: ModoRequest,
                   x_admin_token: str | None = Header(default=None)) -> dict:
    """Cambia el modo GLOBAL de aprobación (marcha_blanca | nuevo_flujo)."""
    _check(x_admin_token)
    return reclamos.set_modo_global(req.modo)


@router.post("/admin/api/modo/cancha")
def set_modo_cancha_admin(req: ModoCanchaRequest,
                          x_admin_token: str | None = Header(default=None)) -> dict:
    """Fija/limpia el override de UNA cancha (modo=null vuelve al global)."""
    _check(x_admin_token)
    return reclamos.set_modo_cancha(req.cancha_id, req.modo)


@router.get("/admin/api/ubicacion")
def get_ubicacion_admin(x_admin_token: str | None = Header(default=None)) -> dict:
    """¿Se exige que el reclamante esté en la cancha (GPS) para aprobar?"""
    _check(x_admin_token)
    return {"exigir": reclamos.exigir_ubicacion(),
            "max_m": config.RECLAMO_UBICACION_MAX_M}


@router.post("/admin/api/ubicacion")
def set_ubicacion_admin(req: ExigirUbicacionRequest,
                        x_admin_token: str | None = Header(default=None)) -> dict:
    """Activa/desactiva la exigencia de ubicación coincidente para aprobar."""
    _check(x_admin_token)
    return reclamos.set_exigir_ubicacion(req.exigir)


@router.get("/admin/api/pichangas/modo")
def get_pichangas_modo(x_admin_token: str | None = Header(default=None)) -> dict:
    """Modo GLOBAL de asignación de cupos de las pichangas (convocatorias)."""
    _check(x_admin_token)
    return convocatorias_service.config_modo()


@router.post("/admin/api/pichangas/modo")
def set_pichangas_modo(req: ModoRequest,
                       x_admin_token: str | None = Header(default=None)) -> dict:
    """Cambia el modo GLOBAL de asignación (orden_llegada | sorteo | equidad)."""
    _check(x_admin_token)
    return convocatorias_service.set_modo_global(req.modo)


@router.get("/admin/api/contacto")
def get_contacto_admin(x_admin_token: str | None = Header(default=None)) -> dict:
    """Números LOCALES de contacto por país (para la torre de control)."""
    _check(x_admin_token)
    return {"contactos": reclamos.contactos_whatsapp(),
            "codigos": reclamos.COD_PAIS_CONTACTO}


@router.post("/admin/api/contacto")
def set_contacto_admin(req: ContactoRequest,
                       x_admin_token: str | None = Header(default=None)) -> dict:
    """Cambia los WhatsApp de contacto por país (torre de control)."""
    _check(x_admin_token)
    return reclamos.set_contactos_whatsapp(req.contactos)


@router.get("/admin/api/canal")
def get_canal_admin(x_admin_token: str | None = Header(default=None)) -> dict:
    """Canal de comunicación que muestra el APK (torre de control)."""
    _check(x_admin_token)
    return reclamos.config_canal()


@router.post("/admin/api/canal")
def set_canal_admin(req: CanalRequest,
                    x_admin_token: str | None = Header(default=None)) -> dict:
    """Cambia el canal GLOBAL (pcg_primero | solo_pcg | whatsapp_libre)."""
    _check(x_admin_token)
    return reclamos.set_canal_comunicacion(req.canal)


def _meta_wa(clave: str) -> dict:
    """Prefijo (+51…) y bandera para los campos de WhatsApp por país."""
    for iso, _nom, cod, bandera in empresa.PAISES:
        if clave == f"contacto_whatsapp_{iso}":
            return {"prefijo": cod, "bandera": bandera}
    return {}


@router.get("/admin/api/empresa")
def get_empresa_admin(x_admin_token: str | None = Header(default=None)) -> dict:
    """Datos de la EMPRESA (razón social, RUC, dirección, WhatsApp, correo,
    horario) que salen en la web, las páginas legales y el Libro de
    Reclamaciones. `datos` = valores crudos para el formulario; `vista` =
    cómo se pintan (WhatsApp bonito, wa.me, correo de privacidad efectivo)."""
    _check(x_admin_token)
    return {"datos": empresa.valores(), "vista": empresa.datos(),
            "campos": [{"clave": k, "etiqueta": et, "ayuda": ay, **_meta_wa(k)} for k, (et, ay) in empresa.CAMPOS.items()]}


@router.post("/admin/api/empresa")
def set_empresa_admin(req: EmpresaRequest,
                      x_admin_token: str | None = Header(default=None)) -> dict:
    """Guarda los datos de la empresa (torre de control). Valida correo,
    WhatsApp y obligatorios; el snapshot los persiste por ambiente."""
    _check(x_admin_token)
    try:
        empresa.guardar(req.datos)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, **get_empresa_admin(x_admin_token)}


class ServicioExtraRequest(BaseModel):
    clave: str = ""
    nombre: str = ""
    emoji: str = ""
    tipo: str = "reserva"
    ambito: str = "cancha"
    deportes: list[str] = []
    activo: bool = True
    nuevo: bool = False


class ActivoRequest(BaseModel):
    activo: bool


class EstadoSugerenciaRequest(BaseModel):
    estado: str = "atendida"


@router.get("/admin/api/servicios-extra")
def get_servicios_extra_admin(x_admin_token: str | None = Header(default=None)) -> dict:
    """Catálogo GLOBAL de servicios extra (torre → Comunicación → Servicios
    extra) + sugerencias de dueños pendientes."""
    _check(x_admin_token)
    import servicios_extra as _se
    return {"servicios": _se.catalogo(solo_activos=False), "tipos": _se.TIPOS, "ambitos": _se.AMBITOS,
            "sugerencias": _se.sugerencias(), "version": stores.servicios_extra_version}


@router.post("/admin/api/servicios-extra")
def set_servicio_extra_admin(req: ServicioExtraRequest,
                             x_admin_token: str | None = Header(default=None)) -> dict:
    """Alta (`nuevo=true`) o edición de un servicio del catálogo."""
    _check(x_admin_token)
    import servicios_extra as _se
    try:
        fila = _se.guardar(req.model_dump(exclude={"nuevo"}), nuevo=req.nuevo)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "servicio": fila, **get_servicios_extra_admin(x_admin_token)}


@router.post("/admin/api/servicios-extra/{clave}/activo")
def set_servicio_extra_activo(clave: str, req: ActivoRequest,
                              x_admin_token: str | None = Header(default=None)) -> dict:
    _check(x_admin_token)
    import servicios_extra as _se
    if _se.activar(clave, req.activo) is None:
        raise HTTPException(status_code=404, detail="servicio_no_existe")
    return {"ok": True, **get_servicios_extra_admin(x_admin_token)}


@router.post("/admin/api/servicios-extra/sugerencias/{sug_id}")
def set_sugerencia_servicio(sug_id: str, req: EstadoSugerenciaRequest,
                            x_admin_token: str | None = Header(default=None)) -> dict:
    _check(x_admin_token)
    import servicios_extra as _se
    if _se.atender_sugerencia(sug_id, req.estado) is None:
        raise HTTPException(status_code=404, detail="sugerencia_no_existe")
    return {"ok": True, **get_servicios_extra_admin(x_admin_token)}


class PostRedesRequest(BaseModel):
    fotos: list[str] = []          # URLs https del bucket o data:image (adjuntas)
    titulo: str = ""
    subtitulo: str = ""
    pie: str = "www.pichangol.app"
    etiqueta: str = ""
    formato: str = "cuadrado"
    texto: str = ""                # texto del post (solo al publicar)
    plantilla: str = ""
    cancha_id: str = ""
    video_id: str = ""             # video subido antes a /admin/api/redes/pichangol/video (publica video en vez de foto)
    imagen: str = ""               # data URL de la VISTA PREVIA que el operador vio: se publica tal cual (sin recomponer)
    enfoque: str = ""              # ángulo elegido/usado por el redactor IA (se guarda en el historial para no repetir)
    fuente: str = ""               # 'ia' | 'banco' | 'plantilla' | 'manual'
    usar_pulido: bool = True       # video: publicar la versión pulida si existe (False = el original tal cual)


class PulirVideoRequest(BaseModel):
    formato: str = "vertical"      # vertical 9:16 · cuadrado 1:1 · original
    logo: bool = True
    intro: bool = True
    cierre: bool = True
    rotulo: bool = True
    titulo: str = ""
    subtitulos: bool = True
    segmentos: list[dict] | None = None   # subtítulos corregidos por el operador (None = transcribir / usar la transcripción guardada)
    resaltar: bool = True
    musica: bool | None = None            # compat: True = auto, False = sin música
    musica_modo: str = ""                 # auto | fondo | protagonista | no
    mood: str = ""                        # chill | energetico | epico
    musica_pista: str = ""                # id de "Mi música" (Google Drive); vacío = música original sintetizada
    musica_desde: float | None = None     # segundo desde el que arranca la pista (None = el inicio sugerido, donde empieza a sonar)


class RedactarRedesRequest(BaseModel):
    cancha_id: str = ""
    tono: str = "cercano"
    enfoque: str = "auto"
    tema: str = ""
    evitar: list[str] = []         # textos ya generados en esta sesión (para "otra versión")


def _redes_canchas() -> list[dict]:
    """Locales con fotos reales para el compositor (agrupados por local)."""
    from web import datos as _wd
    out: dict[str, dict] = {}
    for c in _wd.canchas_publicas():
        fotos = [u for u in ([c.get("foto_url")] + list(c.get("fotos") or [])) if isinstance(u, str) and u.startswith("https://")]
        fotos = list(dict.fromkeys(fotos))
        if not fotos:
            continue
        local = (c.get("club") or c.get("nombre") or "").strip()
        k = local.lower()
        if k not in out:
            out[k] = {"local": local, "zona": c.get("barrio") or c.get("distrito") or "", "canchas": [], "fotos": [],
                      "verificada": bool(c.get("verificada")), "muestra": {"id": c["id"], "club": c.get("club"), "nombre": c.get("nombre"),
                      "barrio": c.get("barrio"), "distrito": c.get("distrito"), "deporte": c.get("deporte"), "deportes": c.get("deportes"),
                      "precio_hora": c.get("precio_hora"), "moneda": c.get("moneda"), "lat": c.get("lat"), "lng": c.get("lng"),
                      "hora_apertura": c.get("hora_apertura"), "hora_cierre": c.get("hora_cierre"), "verificada": bool(c.get("verificada")),
                      "dueno": (c.get("dueno") or "").strip().lower()}}
        out[k]["canchas"].append({"id": c["id"], "nombre": c.get("nombre"), "deporte": c.get("deporte")})
        for u in fotos:
            if u not in out[k]["fotos"]:
                out[k]["fotos"].append(u)
    return sorted(out.values(), key=lambda x: (not x["verificada"], x["local"]))


@router.get("/admin/api/redes/pichangol")
def get_redes_pichangol(x_admin_token: str | None = Header(default=None)) -> dict:
    """Publicar en la PÁGINA de Facebook de Pichangol: estado de credenciales,
    plantillas, locales con fotos reales e historial."""
    _check(x_admin_token)
    from marketing import post_redes as _pr
    from marketing import video_pulido as _vp
    return {"facebook": _pr.estado_pagina(), "plantillas": {k: {"nombre": v["nombre"]} for k, v in _pr.PLANTILLAS.items()},
            "formatos": list(_pr.FORMATOS), "locales": _redes_canchas(), "historial": _pr.historial(), "max_fotos": _pr.MAX_FOTOS,
            "video_max_mb": _pr.VIDEO_MAX_MB, "video_extensiones": sorted(_pr.VIDEO_EXTENSIONES),
            "ia": {"disponible": bool(config.ANTHROPIC_API_KEY), "enfoques": {k: v.split(":")[0].split(".")[0][:60] for k, v in _pr.ENFOQUES.items()},
                   "tonos": list(_pr.TONOS)},
            "pulido": {"disponible": _vp.disponible(), "subtitulos": _vp.subtitulos_disponibles(), "formatos": list(_vp.FORMATOS)}}


class TokenRedesRequest(BaseModel):
    token: str = ""


@router.get("/admin/api/redes/biblioteca")
def get_redes_biblioteca(x_admin_token: str | None = Header(default=None)) -> dict:
    """Biblioteca de marca (fotos/videos importados de Google Fotos) + estado de la conexión."""
    _check(x_admin_token)
    from marketing import biblioteca as _bib
    return {"ok": True, **_bib.estado(), "items": _bib.items(), "video_max_mb": _bib.VIDEO_MAX_BYTES // (1024 * 1024)}


@router.get("/admin/api/redes/biblioteca/google/autorizar")
def get_redes_biblioteca_autorizar(x_admin_token: str | None = Header(default=None)) -> dict:
    _check(x_admin_token)
    from marketing import biblioteca as _bib
    if not _bib.credenciales():
        raise HTTPException(status_code=409, detail="Faltan GOOGLE_WEB_CLIENT_ID y GOOGLE_WEB_CLIENT_SECRET en Railway (cliente OAuth 'Aplicación web').")
    if not _bib.redirect_uri():
        raise HTTPException(status_code=409, detail="Falta PUBLIC_BASE_URL en Railway para armar la URI de redirección.")
    return {"ok": True, "url": _bib.url_autorizacion(), "redirect_uri": _bib.redirect_uri()}


@router.get("/admin/api/redes/biblioteca/google/callback", response_class=HTMLResponse)
def get_redes_biblioteca_callback(code: str = "", state: str = "", error: str = "") -> HTMLResponse:
    """Vuelta de Google (sin cabecera de admin): el `state` firmado por la torre es la prueba."""
    from marketing import biblioteca as _bib
    def _pagina(titulo: str, cuerpo: str, ok: bool) -> HTMLResponse:
        return HTMLResponse(f"<!doctype html><html lang='es'><head><meta charset='utf-8'><title>{titulo}</title>"
                            "<style>body{font-family:system-ui,sans-serif;background:#F4F7FA;margin:0;display:flex;align-items:center;justify-content:center;height:100vh}"
                            ".c{background:#fff;border-radius:18px;padding:28px 32px;max-width:460px;box-shadow:0 8px 30px rgba(0,0,0,.08);text-align:center}"
                            f"h1{{font-size:20px;color:{'#0B8A3E' if ok else '#B42318'}}}p{{color:#444;line-height:1.5}}</style></head>"
                            f"<body><div class='c'><h1>{titulo}</h1><p>{cuerpo}</p><p><b>Ya puedes cerrar esta pestaña y volver a la torre.</b></p></div></body></html>",
                            status_code=200 if ok else 400)
    if error:
        return _pagina("Google canceló la conexión", f"Motivo: {error}", False)
    if not _bib.estado_valido(state):
        return _pagina("Enlace vencido", "La autorización no salió de la torre o pasaron más de 10 minutos. Vuelve a la torre y pulsa Conectar de nuevo.", False)
    try:
        r = _bib.canjear_codigo(code)
    except Exception as exc:  # noqa: BLE001
        return _pagina("No se pudo conectar", str(exc)[:300], False)
    print(f"[biblioteca] Google Fotos conectado ({r.get('cuenta') or 'sin correo'})", flush=True)
    return _pagina("Google Fotos conectado ✓", f"Cuenta: {r.get('cuenta') or 'conectada'}. Desde la torre podrás elegir fotos y videos.", True)


@router.post("/admin/api/redes/biblioteca/google/desconectar")
def post_redes_biblioteca_desconectar(x_admin_token: str | None = Header(default=None)) -> dict:
    _check(x_admin_token)
    from marketing import biblioteca as _bib
    _bib.desconectar()
    return {"ok": True, **_bib.estado()}


@router.post("/admin/api/redes/biblioteca/google/sesion")
def post_redes_biblioteca_sesion(x_admin_token: str | None = Header(default=None)) -> dict:
    """Abre una sesión del selector de Google Fotos: la torre abre `pickerUri` en otra pestaña."""
    _check(x_admin_token)
    from marketing import biblioteca as _bib
    if not _bib.conectado():
        raise HTTPException(status_code=409, detail="Conecta Google Fotos primero.")
    try:
        return {"ok": True, **_bib.crear_sesion()}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)[:300])


@router.get("/admin/api/redes/biblioteca/google/sesion/{sesion_id}")
def get_redes_biblioteca_sesion(sesion_id: str, x_admin_token: str | None = Header(default=None)) -> dict:
    """Sondeo: cuando el director terminó de elegir, importa a la biblioteca y devuelve el resultado."""
    _check(x_admin_token)
    from marketing import biblioteca as _bib
    try:
        e = _bib.estado_sesion(sesion_id)
        if not e["listo"]:
            return {"ok": True, "listo": False}
        r = _bib.importar_sesion(sesion_id)
        return {"ok": True, "listo": True, **r, "items": _bib.items(), **{k: v for k, v in _bib.estado().items() if k in ("fotos", "videos")}}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)[:300])


@router.post("/admin/api/redes/biblioteca/{item_id}/quitar")
def post_redes_biblioteca_quitar(item_id: str, x_admin_token: str | None = Header(default=None)) -> dict:
    _check(x_admin_token)
    from marketing import biblioteca as _bib
    if not _bib.quitar(item_id):
        raise HTTPException(status_code=404, detail="Ya no está en la biblioteca.")
    return {"ok": True, "items": _bib.items()}


@router.get("/admin/api/redes/musica")
def get_redes_musica(x_admin_token: str | None = Header(default=None)) -> dict:
    """Mi música: pistas propias sincronizadas desde una carpeta de Google Drive + estado de la conexión."""
    _check(x_admin_token)
    from marketing import musica_drive as _md
    return {"ok": True, **_md.estado(), "items": _md.items(), "carpetas": _md.carpetas()}


@router.get("/admin/api/redes/musica/google/autorizar")
def get_redes_musica_autorizar(x_admin_token: str | None = Header(default=None)) -> dict:
    _check(x_admin_token)
    from marketing import biblioteca as _bib
    from marketing import musica_drive as _md
    if not _bib.credenciales():
        raise HTTPException(status_code=409, detail="Faltan GOOGLE_WEB_CLIENT_ID y GOOGLE_WEB_CLIENT_SECRET en Railway (cliente OAuth 'Aplicación web').")
    if not _bib.redirect_uri():
        raise HTTPException(status_code=409, detail="Falta PUBLIC_BASE_URL en Railway para armar la URI de redirección.")
    return {"ok": True, "url": _md.url_autorizacion()}


class MusicaCarpetaRequest(BaseModel):
    enlace: str = ""


@router.get("/admin/api/redes/musica/carpetas")
def get_redes_musica_carpetas(q: str = "", x_admin_token: str | None = Header(default=None)) -> dict:
    _check(x_admin_token)
    from marketing import musica_drive as _md
    if not _md.conectado():
        raise HTTPException(status_code=409, detail="Conecta Google Drive primero.")
    try:
        return {"ok": True, "carpetas": _md.buscar_carpetas(q)}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)[:300])


@router.post("/admin/api/redes/musica/carpeta")
def post_redes_musica_carpeta(req: MusicaCarpetaRequest, x_admin_token: str | None = Header(default=None)) -> dict:
    _check(x_admin_token)
    from marketing import musica_drive as _md
    if not _md.conectado():
        raise HTTPException(status_code=409, detail="Conecta Google Drive primero.")
    try:
        c = _md.elegir_carpeta(req.enlace)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)[:300])
    return {"ok": True, "carpeta": c, **{k: v for k, v in _md.estado().items() if k != "carpeta"}}


@router.post("/admin/api/redes/musica/sincronizar")
def post_redes_musica_sincronizar(x_admin_token: str | None = Header(default=None)) -> dict:
    _check(x_admin_token)
    from marketing import musica_drive as _md
    try:
        r = _md.sincronizar()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=409 if "primero" in str(exc) else 502, detail=str(exc)[:300])
    return {"ok": True, **r, "items": _md.items(), "carpetas": _md.carpetas(), **_md.estado()}


@router.post("/admin/api/redes/musica/{item_id}/quitar")
def post_redes_musica_quitar(item_id: str, x_admin_token: str | None = Header(default=None)) -> dict:
    _check(x_admin_token)
    from marketing import musica_drive as _md
    if not _md.quitar(item_id):
        raise HTTPException(status_code=404, detail="Esa pista ya no está en Mi música.")
    return {"ok": True, "items": _md.items()}


class VideoDesdeFotosRequest(BaseModel):
    fotos: list[str] = []
    formato: str = "vertical"
    segundos: float = 2.8


@router.post("/admin/api/redes/pichangol/video/desde-fotos")
def post_redes_video_desde_fotos(req: VideoDesdeFotosRequest, x_admin_token: str | None = Header(default=None)) -> dict:
    """Fotos elegidas → clip con movimiento (Ken Burns + fundidos), que entra al flujo de pulido con música."""
    _check(x_admin_token)
    from marketing import foto_video as _fv
    from marketing import post_redes as _pr
    if not req.fotos:
        raise HTTPException(status_code=400, detail="Elige al menos una foto.")
    if req.formato not in _fv.FORMATOS:
        raise HTTPException(status_code=400, detail="Formato no válido.")
    try:
        datos = [_pr._abrir_url(u) for u in req.fotos[:_fv.MAX_FOTOS]]
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"No se pudo leer una foto: {str(exc)[:160]}")
    v = _pr.iniciar_video("fotos-con-movimiento.mp4")
    try:
        info = _fv.generar(datos, v["ruta"], formato=req.formato, segundos=req.segundos)
    except Exception as exc:  # noqa: BLE001
        _pr.descartar_video(v["id"])
        raise HTTPException(status_code=502, detail=f"No se pudo armar el video: {str(exc)[:200]}")
    v = _pr.confirmar_video(v["id"], os.path.getsize(v["ruta"]))
    _pr.anotar_video(v["id"], desde_fotos=len(datos))
    print(f"[fotos-video] {v['id']} · {len(datos)} fotos · {info['duracion']} s · {req.formato}", flush=True)
    return {"ok": True, "video_id": v["id"], "nombre": v["nombre"], "bytes": v["bytes"], "duracion": info["duracion"], "ancho": info["ancho"], "alto": info["alto"]}


@router.post("/admin/api/redes/pichangol/video/desde-biblioteca/{item_id}")
def post_redes_video_desde_biblioteca(item_id: str, x_admin_token: str | None = Header(default=None)) -> dict:
    """Trae un video de la biblioteca al flujo de publicación (queda como video temporal, listo para pulir con música)."""
    _check(x_admin_token)
    from marketing import biblioteca as _bib
    from marketing import post_redes as _pr
    x = _bib.item(item_id)
    if not x or x.get("tipo") != "video":
        raise HTTPException(status_code=404, detail="Ese video ya no está en la biblioteca.")
    try:
        origen = _bib.descargar_a_temporal(item_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"No se pudo traer el video: {str(exc)[:200]}")
    v = _pr.iniciar_video(x.get("nombre") or f"{item_id}.mp4")
    import shutil
    shutil.copyfile(origen, v["ruta"])
    v = _pr.confirmar_video(v["id"], os.path.getsize(v["ruta"]))
    _pr.anotar_video(v["id"], biblioteca_id=item_id)
    return {"ok": True, "video_id": v["id"], "nombre": v["nombre"], "bytes": v["bytes"], "url": x.get("url", "")}


class AgenteConfigRequest(BaseModel):
    activo: bool | None = None
    hora: str | None = None
    zona: str | None = None
    modo: str | None = None
    tono: str | None = None
    plan: dict | None = None
    destacar_pro: bool | None = None
    videos: str | None = None      # 'auto' | 'nunca'


class AgenteCorrerRequest(BaseModel):
    publicar: bool = False         # False = deja borrador; True = publica ya
    audiencia: str | None = None
    enfoque: str | None = None


class BorradorEditarRequest(BaseModel):
    titulo: str | None = None
    subtitulo: str | None = None
    etiqueta: str | None = None
    texto: str | None = None


@router.get("/admin/api/redes/agente")
def get_redes_agente(x_admin_token: str | None = Header(default=None)) -> dict:
    """Agente de marketing 24×7: configuración, próxima corrida, borradores y bitácora."""
    _check(x_admin_token)
    from marketing import agente_redes as _ag
    return {"ok": True, **_ag.resumen()}


@router.post("/admin/api/redes/agente")
def post_redes_agente(req: AgenteConfigRequest, x_admin_token: str | None = Header(default=None)) -> dict:
    _check(x_admin_token)
    from marketing import agente_redes as _ag
    datos = {k: v for k, v in req.model_dump().items() if v is not None}
    try:
        cfg = _ag.guardar_configuracion(datos)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    print(f"[agente] configuración: activo={cfg['activo']} hora={cfg['hora']} {cfg['zona']} modo={cfg['modo']}", flush=True)
    return {"ok": True, **_ag.resumen()}


@router.post("/admin/api/redes/agente/correr")
def post_redes_agente_correr(req: AgenteCorrerRequest, x_admin_token: str | None = Header(default=None)) -> dict:
    """Corre el agente AHORA (prueba u oportunidad): publica o deja borrador según `publicar`."""
    _check(x_admin_token)
    from marketing import agente_redes as _ag
    r = _ag.ejecutar(forzar=True, publicar=req.publicar, audiencia=req.audiencia, enfoque=req.enfoque)
    if not r.get("ok"):
        raise HTTPException(status_code=502 if r.get("motivo") == "error_facebook" else 409, detail={"sin_credenciales": "Configura el token de Facebook primero.",
                            "error_creativo": f"No se pudo crear la pieza: {r.get('detalle', '')}"}.get(r.get("motivo"), f"{r.get('motivo')}: {r.get('detalle', '')}"))
    return {"ok": True, "publicado": bool(r.get("publicado")), "url": r.get("url", ""), **_ag.resumen()}


@router.get("/admin/api/redes/agente/borrador/{bid}/imagen")
def get_redes_agente_imagen(bid: str, x_admin_token: str | None = Header(default=None)) -> dict:
    _check(x_admin_token)
    from marketing import agente_redes as _ag
    from marketing import post_redes as _pr
    b = _ag.borrador(bid)
    if not b:
        raise HTTPException(status_code=404, detail="El borrador ya no existe.")
    import base64 as _b64
    png = _ag.componer_receta(b)
    return {"ok": True, "imagen": f"data:{_pr.MIME};base64," + _b64.b64encode(png).decode()}


@router.post("/admin/api/redes/agente/borrador/{bid}/editar")
def post_redes_agente_editar(bid: str, req: BorradorEditarRequest, x_admin_token: str | None = Header(default=None)) -> dict:
    _check(x_admin_token)
    from marketing import agente_redes as _ag
    b = _ag.editar_borrador(bid, **req.model_dump())
    if not b:
        raise HTTPException(status_code=404, detail="El borrador ya no existe.")
    return {"ok": True, "borrador": b}


@router.post("/admin/api/redes/agente/borrador/{bid}/{accion}")
def post_redes_agente_borrador(bid: str, accion: str, x_admin_token: str | None = Header(default=None)) -> dict:
    _check(x_admin_token)
    from marketing import agente_redes as _ag
    if accion == "aprobar":
        r = _ag.aprobar_borrador(bid)
        if not r.get("ok"):
            raise HTTPException(status_code=502, detail=r.get("error", "No se pudo publicar"))
        return {"ok": True, "url": r.get("url", ""), **_ag.resumen()}
    if accion == "descartar":
        _ag.descartar_borrador(bid)
        return {"ok": True, **_ag.resumen()}
    if accion == "regenerar":
        b = _ag.regenerar_borrador(bid)
        if not b:
            raise HTTPException(status_code=404, detail="El borrador ya no existe.")
        return {"ok": True, "borrador": b, **_ag.resumen()}
    raise HTTPException(status_code=404, detail="Acción desconocida.")


@router.post("/admin/api/redes/pichangol/token")
def post_redes_token(req: TokenRedesRequest, x_admin_token: str | None = Header(default=None)) -> dict:
    """El operador pega un token nuevo (del Explorador de la API Graph); la torre lo
    convierte en token de PÁGINA permanente y lo guarda cifrado. No pasa por Railway."""
    _check(x_admin_token)
    from marketing import post_redes as _pr
    r = _pr.guardar_token_operador(req.token)
    if not r.get("ok"):
        raise HTTPException(status_code=400, detail=r.get("error", "Token inválido"))
    print(f"[redes] token de Facebook actualizado desde la torre · tipo={r.get('tipo')} · derivado={r.get('derivado')}", flush=True)
    return {**r, "facebook": _pr.estado_pagina()}


@router.post("/admin/api/redes/pichangol/token/olvidar")
def post_redes_token_olvidar(x_admin_token: str | None = Header(default=None)) -> dict:
    _check(x_admin_token)
    from marketing import post_redes as _pr
    _pr.olvidar_token_guardado()
    return {"ok": True, "facebook": _pr.estado_pagina()}


@router.post("/admin/api/redes/pichangol/redactar")
def post_redes_redactar(req: RedactarRedesRequest, x_admin_token: str | None = Header(default=None)) -> dict:
    """Redacta con IA título, subtítulo, etiqueta y texto para el local elegido, con un
    enfoque distinto a los recientes y sin repetir ganchos ya publicados."""
    _check(x_admin_token)
    from marketing import post_redes as _pr
    c = next((l["muestra"] for l in _redes_canchas() if any(x["id"] == req.cancha_id for x in l["canchas"])), None) if req.cancha_id else None
    r = _pr.redactar(c, req.tono, req.enfoque, req.tema, req.evitar[-8:])
    return {"ok": True, **r}


@router.post("/admin/api/redes/pichangol/video")
async def post_redes_video(request: Request, nombre: str = "", x_admin_token: str | None = Header(default=None)) -> dict:
    """Recibe un VIDEO (cuerpo crudo, streaming a disco) para publicarlo luego en la
    página. Devuelve `video_id` temporal (vence en 2 h); el tope es `FB_VIDEO_MAX_MB`."""
    _check(x_admin_token)
    from marketing import post_redes as _pr
    tope = _pr.VIDEO_MAX_MB * 1024 * 1024
    try:
        declarado = int(request.headers.get("content-length") or 0)
    except ValueError:
        declarado = 0
    if declarado > tope:
        raise HTTPException(status_code=413, detail=f"El video pesa {declarado // (1024 * 1024)} MB; el máximo es {_pr.VIDEO_MAX_MB} MB.")
    try:
        v = _pr.iniciar_video(nombre)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    total = 0
    try:
        with open(v["ruta"], "wb") as f:
            async for trozo in request.stream():
                total += len(trozo)
                if total > tope:
                    raise HTTPException(status_code=413, detail=f"El video supera el máximo de {_pr.VIDEO_MAX_MB} MB.")
                f.write(trozo)
    except HTTPException:
        _pr.descartar_video(v["id"])
        raise
    except Exception as exc:  # noqa: BLE001
        _pr.descartar_video(v["id"])
        raise HTTPException(status_code=400, detail=f"No se pudo guardar el video: {str(exc)[:120]}")
    if total == 0:
        _pr.descartar_video(v["id"])
        raise HTTPException(status_code=400, detail="El video llegó vacío.")
    v = _pr.confirmar_video(v["id"], total)
    print(f"[redes] video recibido {v['id']} · {v['nombre']!r} · {total // 1024} KB", flush=True)
    return {"ok": True, "video_id": v["id"], "nombre": v["nombre"], "bytes": total, "expira_en_s": _pr.VIDEO_TTL}


@router.post("/admin/api/redes/pichangol/video/{video_id}/descartar")
def post_redes_video_descartar(video_id: str, x_admin_token: str | None = Header(default=None)) -> dict:
    _check(x_admin_token)
    from marketing import post_redes as _pr
    from marketing import video_pulido as _vp
    _pr.descartar_video(video_id)
    _vp.olvidar(video_id)
    return {"ok": True}


@router.post("/admin/api/redes/pichangol/video/{video_id}/pulir")
def post_redes_video_pulir(video_id: str, req: PulirVideoRequest, x_admin_token: str | None = Header(default=None)) -> dict:
    """Arranca en segundo plano el PULIDO con estilo Pichangol (intro, marca de agua,
    rótulo, subtítulos Whisper, cierre, música si no hay audio). Se sondea con /estado."""
    _check(x_admin_token)
    from marketing import post_redes as _pr
    from marketing import video_pulido as _vp
    v = _pr.video(video_id)
    if not v:
        raise HTTPException(status_code=404, detail="El video ya no está en la torre (vence a las 2 h). Súbelo de nuevo.")
    if not _vp.disponible():
        raise HTTPException(status_code=503, detail="FFmpeg no está disponible en este servidor.")
    if req.formato not in _vp.FORMATOS:
        raise HTTPException(status_code=400, detail="Formato no válido.")
    if req.subtitulos and req.segmentos is None and not v.get("transcripcion") and not _vp.subtitulos_disponibles():
        raise HTTPException(status_code=409, detail="Los subtítulos automáticos necesitan OPENAI_API_KEY en este ambiente. Desmarca Subtítulos o configura la llave.")
    opciones = {"formato": req.formato, "logo": req.logo, "intro": req.intro, "cierre": req.cierre, "rotulo": req.rotulo,
                "titulo": (req.titulo or "").strip()[:80], "subtitulos": req.subtitulos, "segmentos": req.segmentos if req.subtitulos else [],
                "resaltar": req.resaltar}
    if req.musica is not None:
        opciones["musica"] = req.musica
    if req.musica_modo:
        if req.musica_modo not in _vp.MODOS_MUSICA:
            raise HTTPException(status_code=400, detail="Modo de música no válido.")
        opciones["musica_modo"] = req.musica_modo
    if req.mood:
        if req.mood not in _vp.MOODS_MUSICA:
            raise HTTPException(status_code=400, detail="Estilo de música no válido.")
        opciones["mood"] = req.mood
    if req.musica_pista:
        from marketing import musica_drive as _md
        pista = _md.resolver_pista(req.musica_pista)        # id, "carpeta:<género>" o "cualquiera"
        if not pista:
            raise HTTPException(status_code=404, detail="Esa pista ya no está en Mi música. Sincroniza la carpeta de Drive.")
        try:
            opciones["musica_ruta"] = _md.descargar_a_temporal(pista["id"])
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=f"No se pudo traer la pista: {str(exc)[:200]}")
        opciones["musica_pista"] = pista["id"]
        opciones["musica_nombre"] = pista.get("nombre", "")
        desde = float(req.musica_desde) if req.musica_desde is not None else float(pista.get("inicio_sugerido") or 0)
        if desde < 0 or desde > 600:
            raise HTTPException(status_code=400, detail="El segundo de inicio de la pista debe estar entre 0 y 600.")
        opciones["musica_desde"] = desde
    salida = os.path.splitext(v["ruta"])[0] + "_pulido.mp4"

    def _al_terminar(vid, res, transcripcion):
        _pr.anotar_video(vid, pulido=res["ruta"], pulido_info={k: res[k] for k in ("ancho", "alto", "duracion", "bytes", "segmentos")},
                         transcripcion=transcripcion or v.get("transcripcion"))
    ok = _vp.iniciar_trabajo(video_id, v["ruta"], salida, opciones, transcripcion_previa=v.get("transcripcion") if req.segmentos is None else None,
                             al_terminar=_al_terminar)
    if not ok:
        raise HTTPException(status_code=409, detail="Ya hay un pulido en curso para este video.")
    print(f"[pulido] {video_id} iniciado · {req.formato} · subs={req.subtitulos}", flush=True)
    return {"ok": True, "estado": _vp.estado(video_id)}


@router.get("/admin/api/redes/pichangol/video/{video_id}/estado")
def get_redes_video_estado(video_id: str, x_admin_token: str | None = Header(default=None)) -> dict:
    _check(x_admin_token)
    from marketing import post_redes as _pr
    from marketing import video_pulido as _vp
    v = _pr.video(video_id)
    if not v:
        raise HTTPException(status_code=404, detail="El video ya no está en la torre.")
    e = _vp.estado(video_id)
    return {"ok": True, "estado": e.get("estado"), "progreso": e.get("progreso", 0), "mensaje": e.get("mensaje", ""), "error": e.get("error", ""),
            "pulido": bool(v.get("pulido") and os.path.exists(v["pulido"])), "pulido_info": v.get("pulido_info") or {},
            "transcripcion": v.get("transcripcion") or (e.get("transcripcion") or None)}


@router.get("/admin/api/redes/pichangol/video/{video_id}/archivo")
def get_redes_video_archivo(video_id: str, cual: str = "pulido", x_admin_token: str | None = Header(default=None)):
    """El MP4 (original o pulido) para la vista previa de la torre (se pide con fetch + cabecera)."""
    _check(x_admin_token)
    from marketing import post_redes as _pr
    v = _pr.video(video_id)
    if not v:
        raise HTTPException(status_code=404, detail="El video ya no está en la torre.")
    ruta = v.get("pulido") if cual == "pulido" else v["ruta"]
    if not ruta or not os.path.exists(ruta):
        raise HTTPException(status_code=404, detail="Todavía no hay versión pulida.")
    return FileResponse(ruta, media_type="video/mp4", filename=os.path.basename(ruta))


@router.post("/admin/api/redes/pichangol/plantilla")
def post_redes_plantilla(req: PostRedesRequest, x_admin_token: str | None = Header(default=None)) -> dict:
    """Rellena título/subtítulo/texto de una plantilla con los datos del local elegido."""
    _check(x_admin_token)
    from marketing import post_redes as _pr
    c = next((l["muestra"] for l in _redes_canchas() if any(x["id"] == req.cancha_id for x in l["canchas"])), None) if req.cancha_id else None
    return {"ok": True, "titulo": _pr.rellenar(req.plantilla, c, "titulo"), "subtitulo": _pr.rellenar(req.plantilla, c, "subtitulo"),
            "texto": _pr.rellenar(req.plantilla, c, "texto")}


@router.post("/admin/api/redes/pichangol/previsualizar")
def post_redes_previsualizar(req: PostRedesRequest, x_admin_token: str | None = Header(default=None)) -> dict:
    _check(x_admin_token)
    from marketing import post_redes as _pr
    try:
        png = _pr.componer(req.fotos, req.titulo, req.subtitulo, req.pie, req.formato, req.etiqueta)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"No se pudo componer la imagen: {str(exc)[:160]}")
    import base64 as _b64
    return {"ok": True, "imagen": f"data:{_pr.MIME};base64," + _b64.b64encode(png).decode(), "bytes": len(png), "extension": _pr.EXTENSION}


@router.post("/admin/api/redes/pichangol/publicar")
def post_redes_publicar(req: PostRedesRequest, x_admin_token: str | None = Header(default=None)) -> dict:
    """Compone y PUBLICA en la página de Facebook (foto + texto). Sin
    credenciales responde 409 `sin_credenciales` con la guía."""
    _check(x_admin_token)
    from marketing import post_redes as _pr
    if not _pr.configurado():
        raise HTTPException(status_code=409, detail="sin_credenciales")
    if not (req.texto or "").strip():
        raise HTTPException(status_code=400, detail="Escribe el texto de la publicación.")
    if req.video_id:
        # VIDEO: el archivo ya está en la torre; se sube a la página por trozos.
        v = _pr.video(req.video_id)
        if not v:
            raise HTTPException(status_code=404, detail="El video ya no está en la torre (vence a las 2 h). Súbelo de nuevo.")
        ruta_pub = v["pulido"] if (req.usar_pulido and v.get("pulido") and os.path.exists(v["pulido"])) else v["ruta"]
        pulido = ruta_pub != v["ruta"]
        r = _pr.publicar_video_facebook(req.texto.strip(), req.titulo, ruta_pub)
        fila = _pr.registrar({"red": "facebook", "tipo": "video", "plantilla": req.plantilla, "enfoque": req.enfoque, "fuente": req.fuente, "titulo": req.titulo, "texto": req.texto.strip()[:600],
                              "fotos": 0, "formato": "video", "video_nombre": v["nombre"], "video_bytes": os.path.getsize(ruta_pub) if os.path.exists(ruta_pub) else v["bytes"],
                              "pulido": pulido, "subtitulos": int((v.get("pulido_info") or {}).get("segmentos") or 0) if pulido else 0, "ok": bool(r.get("ok")),
                              "post_id": r.get("post_id", ""), "url": r.get("url", ""), "error": r.get("error", "")})
        if not r.get("ok"):
            raise HTTPException(status_code=502, detail=f"Facebook rechazó el video: {r.get('error')}")
        _pr.descartar_video(req.video_id)
        print(f"[redes] video publicado en Facebook {r.get('post_id')} · {v['nombre']!r} · {r.get('trozos')} trozo(s)", flush=True)
        return {"ok": True, "publicacion": fila, "url": r.get("url", ""), "video": True}
    # Se publica LO QUE EL OPERADOR VIO: la vista previa. Solo si no llegó se recompone
    # desde las fotos (clientes viejos). Antes, al cambiar de local se vaciaban las fotos
    # pero la vista previa seguía en pantalla y publicar fallaba con "Elige al menos una foto".
    try:
        if (req.imagen or "").startswith("data:image/"):
            png = _pr.pieza_desde_vista_previa(req.imagen)
        elif req.fotos:
            png = _pr.componer(req.fotos, req.titulo, req.subtitulo, req.pie, req.formato, req.etiqueta)
        else:
            raise ValueError("Elige o sube al menos una foto y espera la vista previa antes de publicar.")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    r = _pr.publicar_facebook(req.texto.strip(), png)
    fila = _pr.registrar({"red": "facebook", "tipo": "foto", "plantilla": req.plantilla, "enfoque": req.enfoque, "fuente": req.fuente, "titulo": req.titulo, "texto": req.texto.strip()[:600],
                          "fotos": len(req.fotos), "formato": req.formato, "ok": bool(r.get("ok")),
                          "post_id": r.get("post_id", ""), "url": r.get("url", ""), "error": r.get("error", "")})
    if not r.get("ok"):
        raise HTTPException(status_code=502, detail=f"Facebook rechazó la publicación: {r.get('error')}")
    print(f"[redes] publicado en Facebook {r.get('post_id')} · {req.titulo!r}", flush=True)
    return {"ok": True, "publicacion": fila, "url": r.get("url", "")}


@router.get("/admin/api/marketing")
def get_marketing_admin(x_admin_token: str | None = Header(default=None)) -> dict:
    """Precios de los servicios de marketing + tope mensual de posts IA."""
    _check(x_admin_token)
    return {
        "landing_soles": stores.cfg_int("servicio_landing_soles"),
        "redes_soles": stores.cfg_int("servicio_redes_soles"),
        "presencia_soles": stores.cfg_int("servicio_presencia_soles"),
        "posts_limite_mes": stores.cfg_int("marketing_posts_limite_mes"),
        # 0 = sin tarifa propia de club (se usa la base de academia).
        "landing_soles_club": stores.cfg_int("servicio_landing_soles_club"),
        "redes_soles_club": stores.cfg_int("servicio_redes_soles_club"),
        "presencia_soles_club": stores.cfg_int("servicio_presencia_soles_club"),
    }


@router.post("/admin/api/marketing")
def set_marketing_admin(req: MarketingConfigRequest,
                        x_admin_token: str | None = Header(default=None)) -> dict:
    """Cambia precios de servicios y el tope de posts (torre de control)."""
    _check(x_admin_token)
    if req.landing_soles is not None:
        stores.config["servicio_landing_soles"] = str(int(req.landing_soles))
    if req.redes_soles is not None:
        stores.config["servicio_redes_soles"] = str(int(req.redes_soles))
    if req.presencia_soles is not None:
        stores.config["servicio_presencia_soles"] = str(int(req.presencia_soles))
    if req.posts_limite_mes is not None:
        stores.config["marketing_posts_limite_mes"] = str(max(0, int(req.posts_limite_mes)))
    # Overrides de club: 0 o menos = borrar (usar la tarifa base de academia).
    for campo, clave in (
        (req.landing_soles_club, "servicio_landing_soles_club"),
        (req.redes_soles_club, "servicio_redes_soles_club"),
        (req.presencia_soles_club, "servicio_presencia_soles_club"),
    ):
        if campo is not None:
            stores.config[clave] = "" if int(campo) <= 0 else str(int(campo))
    return get_marketing_admin(x_admin_token)


@router.post("/admin/api/borrar-suscripciones-alumno")
def borrar_suscripciones_alumno_admin(
        x_admin_token: str | None = Header(default=None)) -> dict:
    """PRUEBAS: borra todas las suscripciones mensuales de alumnos (mes a mes),
    para que al limpiar academias/alumnos no queden débitos automáticos huérfanos
    cobrando tarjetas. No toca saldos ni reportes."""
    _check(x_admin_token)
    n = len(stores.suscripciones_alumno)
    stores.suscripciones_alumno.clear()
    return {"ok": True, "borradas": n}


@router.post("/admin/api/borrar-cobros-matricula")
def borrar_cobros_matricula_admin(
        x_admin_token: str | None = Header(default=None)) -> dict:
    """PRUEBAS: borra los cobros digitales de matrícula del libro de pagos, para
    que el 'Reporte de pagos' del profe no arrastre montos de pruebas viejas tras
    'Empezar de cero'. No toca liquidaciones, saldos ni suscripciones."""
    _check(x_admin_token)
    n = stores.borrar_cobros_matricula()
    return {"ok": True, "borrados": n}


@router.post("/admin/api/reiniciar-pagos")
def reiniciar_pagos_admin(
        x_admin_token: str | None = Header(default=None)) -> dict:
    """PRUEBAS: vacía TODO el libro de pagos (matrículas, reservas, recargas,
    servicios, liquidaciones) para dejar el reporte de márgenes en cero y probar
    desde limpio. No toca saldos."""
    _check(x_admin_token)
    n = stores.reiniciar_libro_pagos()
    return {"ok": True, "borrados": n}


@router.get("/admin/api/storage/huerfanos")
def storage_huerfanos_admin(
        x_admin_token: str | None = Header(default=None)) -> dict:
    """DRY-RUN del barrido de Storage: cuántos archivos quedaron sin dueño
    (canchas borradas, historias vencidas, avatares viejos…) y ejemplos. No
    borra nada — es lo que la torre muestra antes de que el operador confirme."""
    _check(x_admin_token)
    return storage_limpieza.analizar()


@router.post("/admin/api/storage/limpiar")
def storage_limpiar_admin(
        x_admin_token: str | None = Header(default=None)) -> dict:
    """Borra los huérfanos detectados (borrado FÍSICO vía Storage API). Las
    constancias de recargas y el arte compartido quedan protegidos siempre."""
    _check(x_admin_token)
    return storage_limpieza.limpiar()


@router.post("/admin/api/reset-virgen")
def reset_virgen_admin(
        x_admin_token: str | None = Header(default=None)) -> dict:
    """DEJAR EN VIRGEN: borra TODO lo transaccional del servidor (pagos, saldos,
    suscripciones de servicios y de alumnos, tarjetas guardadas, customers y
    vistas) CONSERVANDO los reclamos de propiedad (las canchas siguen reclamadas)
    y la config del operador. El lado del cliente (alumnos y reservas en Supabase)
    se limpia desde la app."""
    _check(x_admin_token)
    conteo = stores.reset_virgen()
    return {"ok": True, "borrado": conteo}


@router.post("/admin/api/reset-total")
def reset_total_admin(
        x_admin_token: str | None = Header(default=None)) -> dict:
    """VIRGEN TOTAL: borra ABSOLUTAMENTE TODO el estado del servidor, INCLUIDOS los
    reclamos de propiedad (las canchas dejan de estar reclamadas/verificadas) y la
    config del operador. Deja el backend como recién instalado. Combínalo con el
    SQL dejar_virgen_total.sql (Supabase) y con limpiar los datos de la app en cada
    dispositivo. El snapshot vacío se persiste por el middleware tras este POST."""
    _check(x_admin_token)
    antes = {
        "reclamos": len(stores.reclamos),
        "canchas": len(stores.canchas),
        "pagos": len(stores.pagos),
        "saldos": len(stores.saldos),
    }
    stores.reset()
    # Vacía TAMBIÉN las tablas normalizadas (growth_reclamos, etc.): si no, un
    # reinicio recarga los reclamos desde growth_reclamos y "reaparecen".
    pg.limpiar_todo()
    return {"ok": True, "virgen_total": True, "borrado": antes}


# ─────────────────────── DISPUTAS DEL MARKETPLACE ─────────────────────────────

class ResolverDisputaRequest(BaseModel):
    accion: str  # 'liberar' (dar razón al vendedor) | 'reembolsar' (al comprador)


@router.get("/admin/api/ventas/disputas")
def listar_disputas(x_admin_token: str | None = Header(default=None)) -> dict:
    """Órdenes del marketplace EN DISPUTA, para que el operador resuelva."""
    _check(x_admin_token)
    from pagos.router import comision_centimos

    out = []
    for v in stores.ventas:
        if v.estado != "disputado":
            continue
        neto = round(v.monto_soles - comision_centimos(v.monto_soles) / 100.0, 2)
        out.append({
            "id": v.id,
            "producto_nombre": v.producto_nombre,
            "comprador_email": v.comprador_email,
            "comprador_nombre": v.comprador_nombre,
            "vendedor_email": v.vendedor_email,
            "vendedor_nombre": v.vendedor_nombre,
            "monto_soles": v.monto_soles,
            "neto_soles": neto,
            "creado_en": v.creado_en.isoformat(),
        })
    out.sort(key=lambda d: d["creado_en"], reverse=True)
    return {"disputas": out}


@router.post("/admin/api/venta/{venta_id}/resolver")
def resolver_disputa(venta_id: int, req: ResolverDisputaRequest,
                     x_admin_token: str | None = Header(default=None)) -> dict:
    """Resuelve una disputa: 'liberar' libera el pago al vendedor (estado
    recibido); 'reembolsar' da razón al comprador (estado reembolsado; el neto NO
    se libera y el operador devuelve al comprador fuera de la app)."""
    _check(x_admin_token)
    from db.store import ahora

    v = next((x for x in stores.ventas if x.id == venta_id), None)
    if v is None:
        raise HTTPException(status_code=404, detail="venta_no_encontrada")
    if req.accion == "liberar":
        v.estado = "recibido"
        v.recibido_en = ahora()
    elif req.accion == "reembolsar":
        v.estado = "reembolsado"
    else:
        return {"ok": False, "error": "accion_invalida"}
    return {"ok": True, "estado": v.estado}


# ─────────────────── VERIFICACIONES DE IDENTIDAD (DNI) ────────────────────────
# Registro anti-fraude "1 DNI = 1 cuenta": `stores.dni_verificados` liga el HASH
# del DNI (nunca el número, Ley 29733) a un correo. El operador puede REVOCAR ese
# vínculo para liberar un DNI (p. ej. si alguien lo tomó y el dueño legítimo quedó
# bloqueado, o para limpiar un duplicado). Revocar aquí libera el DNI para que se
# pueda volver a verificar; el flag "verificado" del lado app (Supabase
# pichangol_verificaciones) se limpia aparte desde la app.

class RevocarDniRequest(BaseModel):
    email: str


@router.get("/admin/api/dni/verificaciones")
def listar_dni_verificaciones(
        x_admin_token: str | None = Header(default=None)) -> dict:
    """Lista los DNI verificados agrupados por correo (sin exponer el número:
    solo un prefijo del hash para poder distinguirlos)."""
    _check(x_admin_token)
    por_correo: dict[str, list[str]] = {}
    for h, email in stores.dni_verificados.items():
        por_correo.setdefault(email, []).append(h[:10])
    out = [{"email": e, "dnis": len(hs), "hashes": sorted(hs)}
           for e, hs in por_correo.items()]
    out.sort(key=lambda d: d["email"])
    return {"total": len(stores.dni_verificados), "cuentas": out}


@router.post("/admin/api/dni/revocar")
def revocar_dni(req: RevocarDniRequest,
                x_admin_token: str | None = Header(default=None)) -> dict:
    """Revoca (libera) TODAS las verificaciones de DNI ligadas a un correo, para
    que ese DNI se pueda volver a verificar en la cuenta correcta."""
    _check(x_admin_token)
    email = req.email.strip().lower()
    if not email:
        return {"ok": False, "error": "correo_requerido"}
    quitar = [h for h, e in stores.dni_verificados.items() if e == email]
    for h in quitar:
        stores.dni_verificados.pop(h, None)
    return {"ok": True, "revocados": len(quitar)}


# ─────────────────────── PICHANGOL PRO (torre de control) ─────────────────────
def _pro_precio_pais(iso: str) -> float:
    """Precio Pro efectivo de un país (override EC/BO o base PE)."""
    val = ""
    if iso == "ec":
        val = stores.cfg("pro_precio_soles_ec")
    elif iso == "bo":
        val = stores.cfg("pro_precio_soles_bo")
    if not val:
        val = stores.cfg("pro_precio_soles")
    try:
        return max(0.0, float(val))
    except (TypeError, ValueError):
        return 12.0


@router.get("/admin/api/pro")
def get_pro_admin(x_admin_token: str | None = Header(default=None)) -> dict:
    """Panel Pichangol Pro: precios por país, miembros y MRR (ingreso mensual
    recurrente estimado = suma del precio del país de cada miembro activo)."""
    _check(x_admin_token)
    ahora = datetime.now(timezone.utc)
    miembros = []
    activos = 0
    # MRR POR PAÍS (cada uno en SU moneda: no se pueden sumar S/, $ y Bs).
    mrr_pais = {"pe": 0.0, "ec": 0.0, "bo": 0.0}
    activos_pais = {"pe": 0, "ec": 0, "bo": 0}
    for email, m in stores.membresias_pro.items():
        try:
            dt = datetime.fromisoformat(m.get("hasta")) if m.get("hasta") else None
        except (TypeError, ValueError):
            dt = None
        activa = dt is not None and dt > ahora
        pais = (m.get("pais") or "PE").lower()
        cortesia = bool(m.get("cortesia"))
        if activa:
            activos += 1
            # Las CORTESÍAS (marcha blanca) no pagan → fuera del MRR (que el
            # ingreso estimado sea honesto).
            if pais in mrr_pais and not cortesia:
                mrr_pais[pais] += _pro_precio_pais(pais)
                activos_pais[pais] += 1
        miembros.append({"email": email, "hasta": m.get("hasta"),
                         "activa": activa, "pais": pais.upper(),
                         "cortesia": cortesia,
                         "ultimo_cobro": m.get("ultimo_cobro")})
    miembros.sort(key=lambda x: (not x["activa"], x["email"]))
    return {"precio_soles": _pro_precio_pais("pe"),
            "precios": {"pe": _pro_precio_pais("pe"),
                        "ec": _pro_precio_pais("ec"),
                        "bo": _pro_precio_pais("bo")},
            "activos": activos, "total": len(miembros),
            # MRR de Perú por compatibilidad + desglose por país (en su moneda).
            "mrr_soles": round(mrr_pais["pe"], 2),
            "mrr_por_pais": {k: round(v, 2) for k, v in mrr_pais.items()},
            "activos_por_pais": activos_pais,
            "bienvenida": {
                "pro_dias": stores.cfg("bienvenida_pro_dias") or "0",
                "saldo_soles": stores.cfg("bienvenida_saldo_soles") or "0",
                "saldo_usd": stores.cfg("bienvenida_saldo_usd") or "0",
                "saldo_bob": stores.cfg("bienvenida_saldo_bob") or "0",
            },
            "miembros": miembros}


class BienvenidaReq(BaseModel):
    pro_dias: int = 0
    saldo_soles: float = 0.0   # Perú (S/)
    saldo_usd: float = 0.0     # Ecuador ($)
    saldo_bob: float = 0.0     # Bolivia (Bs)


@router.post("/admin/api/pro/bienvenida")
def set_bienvenida_admin(
        req: BienvenidaReq,
        x_admin_token: str | None = Header(default=None)) -> dict:
    """MARCHA BLANCA automática: qué recibe cada dueño NUEVO al activarse su
    primera cancha — días de Pro de cortesía y/o saldo de REGALO (solo cubre
    comisiones). 0 y 0 = apagada."""
    _check(x_admin_token)
    dias = max(0, min(int(req.pro_dias), 365))

    def _lim(v: float, tope: float) -> float:
        v = max(0.0, min(float(v), tope))
        return v if v % 1 else int(v)

    # Montos POR PAÍS en su moneda (S/ · $ · Bs); topes por moneda.
    saldo = _lim(req.saldo_soles, 1000.0)
    usd = _lim(req.saldo_usd, 300.0)
    bob = _lim(req.saldo_bob, 2000.0)
    stores.config["bienvenida_pro_dias"] = str(dias)
    stores.config["bienvenida_saldo_soles"] = str(saldo)
    stores.config["bienvenida_saldo_usd"] = str(usd)
    stores.config["bienvenida_saldo_bob"] = str(bob)
    return {"ok": True, "pro_dias": dias, "saldo_soles": saldo,
            "saldo_usd": usd, "saldo_bob": bob}


@router.get("/admin/api/reclamaciones")
def get_reclamaciones_admin(
        x_admin_token: str | None = Header(default=None)) -> dict:
    """Libro de Reclamaciones: todas las hojas, las pendientes primero."""
    _check(x_admin_token)
    hojas = sorted(stores.reclamaciones,
                   key=lambda h: (h.get("estado") != "pendiente", -int(h.get("id", 0))))
    pend = sum(1 for h in stores.reclamaciones if h.get("estado") == "pendiente")
    return {"reclamaciones": hojas, "pendientes": pend, "total": len(stores.reclamaciones)}


class ReclamacionRespuestaReq(BaseModel):
    respuesta: str = ""


@router.post("/admin/api/reclamaciones/{rid}/atender")
def atender_reclamacion_admin(
        rid: int, req: ReclamacionRespuestaReq,
        x_admin_token: str | None = Header(default=None)) -> dict:
    """Marca la hoja como atendida y guarda la respuesta dada al consumidor
    (la respuesta formal se le envía por correo; aquí queda el registro)."""
    _check(x_admin_token)
    for h in stores.reclamaciones:
        if int(h.get("id", 0)) == rid:
            h["estado"] = "atendida"
            h["respuesta"] = (req.respuesta or "").strip()[:2000]
            h["respondida_en"] = datetime.now(timezone.utc).isoformat()
            return {"ok": True, "numero": h.get("numero")}
    return {"ok": False, "error": "no_encontrada"}


class ProPrecioReq(BaseModel):
    precio_soles: float
    pais: str = "pe"


@router.post("/admin/api/pro/precio")
def set_pro_precio_admin(
        req: ProPrecioReq,
        x_admin_token: str | None = Header(default=None)) -> dict:
    """Fija el precio mensual de Pichangol Pro de un país (pe = base; ec/bo =
    override)."""
    _check(x_admin_token)
    precio = max(0.0, float(req.precio_soles))
    txt = str(precio if precio % 1 else int(precio))
    iso = (req.pais or "pe").lower()
    clave = "pro_precio_soles" if iso == "pe" else f"pro_precio_soles_{iso}"
    stores.config[clave] = txt
    return {"ok": True, "pais": iso.upper(),
            "precios": {"pe": _pro_precio_pais("pe"),
                        "ec": _pro_precio_pais("ec"),
                        "bo": _pro_precio_pais("bo")}}


@router.get("/admin/api/circuito")
def get_circuito_admin(x_admin_token: str | None = Header(default=None)) -> dict:
    """Ingresos del CIRCUITO para Pichangol: membresías Pro (todo el monto es
    ingreso) + comisión de inscripciones a torneos. Da visibilidad del ingreso
    que genera la capa de comunidad."""
    _check(x_admin_token)
    pro_n = pro_total = 0
    torneo_n = torneo_bruto = torneo_comision = 0
    for p in stores.pagos:
        if p.estado != "aprobado":
            continue
        if p.tipo == "suscripcion_pro":
            pro_n += 1
            pro_total += p.monto_centimos
        elif p.tipo == "inscripcion_torneo_ingreso":
            torneo_n += 1
            torneo_bruto += p.monto_centimos
            torneo_comision += p.comision_centimos
    ingreso = pro_total + torneo_comision

    # Salud del circuito (datos que vive el growth): directorio de jugadores
    # disponibles + actividad de retos + líderes por retos ganados.
    por_deporte: dict[str, int] = {}
    for d in stores.jugadores_circuito.values():
        dep = (d.get("deporte") or "—")
        por_deporte[dep] = por_deporte.get(dep, 0) + 1

    retos_pend = retos_acep = retos_jug = 0
    wins: dict[str, int] = {}
    plays: dict[str, int] = {}
    names: dict[str, str] = {}
    for r in stores.retos:
        if r.estado == "pendiente":
            retos_pend += 1
        elif r.estado == "aceptado":
            retos_acep += 1
        elif r.estado == "jugado":
            retos_jug += 1
        if r.estado == "jugado" and r.ganador_email:
            for email, name in ((r.retador_email, r.retador_nombre),
                                (r.retado_email, r.retado_nombre)):
                if not email:
                    continue
                plays[email] = plays.get(email, 0) + 1
                if name:
                    names[email] = name
            wins[r.ganador_email] = wins.get(r.ganador_email, 0) + 1
    lideres = sorted(
        ({"email": e, "nombre": names.get(e, e),
          "ganados": wins.get(e, 0), "jugados": plays.get(e, 0)}
         for e in plays),
        key=lambda x: (-x["ganados"], -x["jugados"]))[:5]

    try:
        from retos.router import _limite_free
        _lim = _limite_free()
    except Exception:
        _lim = 3

    return {
        "pro": {"cobros": pro_n, "total_soles": pro_total / 100.0},
        "torneos": {"inscripciones": torneo_n,
                    "bruto_soles": torneo_bruto / 100.0,
                    "comision_soles": torneo_comision / 100.0},
        "ingreso_circuito_soles": round(ingreso / 100.0, 2),
        "directorio": {"total": len(stores.jugadores_circuito),
                       "por_deporte": por_deporte},
        "retos": {"total": len(stores.retos), "pendientes": retos_pend,
                  "aceptados": retos_acep, "jugados": retos_jug},
        "lideres_retos": lideres,
        "limite_retos_free": _lim,
    }


class LimiteRetosReq(BaseModel):
    limite: int


@router.post("/admin/api/circuito/limite-retos")
def set_limite_retos_admin(
        req: LimiteRetosReq,
        x_admin_token: str | None = Header(default=None)) -> dict:
    """Fija cuántos retos por semana puede enviar un jugador SIN Pichangol Pro
    (Pro = ilimitado). Mínimo 1."""
    _check(x_admin_token)
    limite = max(1, int(req.limite))
    stores.config["retos_free_limite_semana"] = str(limite)
    return {"ok": True, "limite": limite}


@router.get("/admin/api/ranking")
def get_ranking_admin(x_admin_token: str | None = Header(default=None)) -> dict:
    """Snapshot del ranking global cruzado que empuja el APK (las academias viven
    en Supabase, no en el growth). La torre solo lo muestra."""
    _check(x_admin_token)
    return stores.ranking_snapshot or {"deportes": [], "actualizado": None}


@router.get("/admin/api/comision")
def get_comision_admin(x_admin_token: str | None = Header(default=None)) -> dict:
    """Comisión por cobro digital de matrícula, por país (torre de control)."""
    _check(x_admin_token)

    def _pct(iso: str) -> float:
        try:
            return max(0.0, float(stores.cfg(f"comision_matricula_pct_{iso}")))
        except (TypeError, ValueError):
            return 0.0

    return {"pe": _pct("pe"), "ec": _pct("ec"), "bo": _pct("bo")}


@router.post("/admin/api/comision")
def set_comision_admin(req: ComisionRequest,
                       x_admin_token: str | None = Header(default=None)) -> dict:
    """Cambia la comisión por cobro digital por país (torre de control)."""
    _check(x_admin_token)
    for iso in ("pe", "ec", "bo"):
        val = getattr(req, iso)
        if val is not None:
            stores.config[f"comision_matricula_pct_{iso}"] = str(max(0.0, float(val)))
    return get_comision_admin(x_admin_token)


def _banco_pct() -> float:
    """Tasa efectiva de la pasarela/banco (Culqi) sobre el bruto (config)."""
    try:
        return max(0.0, float(stores.cfg("comision_banco_pct")))
    except (TypeError, ValueError):
        return 0.0


@router.get("/admin/api/margenes")
def get_margenes_admin(x_admin_token: str | None = Header(default=None)) -> dict:
    """DESGLOSE del margen de Pichangol: sus INGRESOS por comisiones (matrículas +
    reservas) menos el COSTO real de la pasarela/banco (Culqi) sobre TODO lo que
    pasa por tarjeta (matrículas de alumnos + recargas de saldo de dueños). Las
    comisiones de reserva se debitan del saldo (que el dueño recargó por tarjeta),
    por eso las recargas entran en la base de costo del banco."""
    _check(x_admin_token)
    mat = [p for p in stores.pagos if p.tipo == "matricula_online"]
    res = [p for p in stores.pagos if p.tipo == "comision_reserva"]
    rec = [p for p in stores.pagos if p.tipo == "recarga"]
    srv = [p for p in stores.pagos if p.tipo == "suscripcion"]
    mat_bruto = sum(p.monto_centimos for p in mat)
    comision_mat = sum(p.comision_centimos for p in mat)
    comision_res = sum(p.monto_centimos for p in res)  # la comisión ES el monto
    rec_bruto = sum(p.monto_centimos for p in rec)
    # Servicios (landing/redes/marketing): la academia le paga a PCG por tarjeta;
    # el monto COMPLETO es ingreso de Pichangol (no hay neto que devolver).
    ingresos_srv = sum(p.monto_centimos for p in srv)
    bruto_procesado = mat_bruto + rec_bruto + ingresos_srv  # todo lo cobrado a tarjeta
    ingresos = comision_mat + comision_res + ingresos_srv    # ingreso bruto de PCG
    banco_pct = _banco_pct()
    costo_banco = int(round(bruto_procesado * banco_pct / 100.0))
    margen = ingresos - costo_banco

    # Tarifa de comisión cuando sale del SALDO (billetera): configurable; vacía
    # = usa la estándar. `stores.config` directo (cfg() devuelve "0" si falta,
    # y ausente ≠ 0%): None = sin configurar.
    def _cfg_float(clave: str) -> float | None:
        try:
            return float(stores.config.get(clave))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None

    saldo_pct = _cfg_float("comision_saldo_pct")
    saldo_min = _cfg_float("comision_saldo_min_soles")
    return {
        "comision_std_pct": config.COMISION_PORC,
        "comision_std_min_soles": config.COMISION_MIN_SOLES,
        "comision_saldo_pct": saldo_pct,
        "comision_saldo_min_soles": saldo_min,
        "cobros_matricula": len(mat),
        "cobros_reserva": len(res),
        "cobros_servicios": len(srv),
        "comision_matricula_soles": comision_mat / 100.0,
        "comision_reserva_soles": comision_res / 100.0,
        "ingresos_servicios_soles": ingresos_srv / 100.0,
        "ingresos_pcg_soles": ingresos / 100.0,
        "banco_pct": banco_pct,
        "bruto_procesado_soles": bruto_procesado / 100.0,
        "costo_banco_soles": costo_banco / 100.0,
        "margen_pcg_soles": margen / 100.0,
    }


@router.post("/admin/api/margenes/banco")
def set_banco_admin(req: BancoRequest,
                    x_admin_token: str | None = Header(default=None)) -> dict:
    """Fija la tasa de la pasarela/banco (Culqi) y devuelve el desglose recalculado."""
    _check(x_admin_token)
    stores.config["comision_banco_pct"] = str(max(0.0, float(req.pct)))
    return get_margenes_admin(x_admin_token)


@router.post("/admin/api/margenes/comision-saldo")
def set_comision_saldo_admin(
        req: ComisionSaldoRequest,
        x_admin_token: str | None = Header(default=None)) -> dict:
    """Configura la comisión de reserva cuando se cobra del SALDO (billetera):
    % y mínimo en soles. Con `reset` (o pct vacío) vuelve a la estándar."""
    _check(x_admin_token)
    if req.reset or req.pct is None:
        stores.config.pop("comision_saldo_pct", None)
        stores.config.pop("comision_saldo_min_soles", None)
    else:
        stores.config["comision_saldo_pct"] = str(max(0.0, float(req.pct)))
        stores.config["comision_saldo_min_soles"] = str(
            max(0.0, float(req.min_soles or 0.0)))
    return get_margenes_admin(x_admin_token)


@router.get("/config/contacto")
def get_contacto_publico(pais: str | None = None) -> dict:
    """PÚBLICO: el APK lee el WhatsApp de contacto COMPLETO del país detectado
    (?pais=PE|EC|BO). Sin país, devuelve el primero configurado."""
    return {"whatsapp": reclamos.contacto_whatsapp(pais)}


@router.get("/config/servicios-extra")
def get_servicios_extra_publico() -> dict:
    """PÚBLICO: catálogo GLOBAL de servicios extra que el APK y la web usan en
    el editor del dueño y en el checkout (nombre, emoji, tipo de cobro,
    ámbito). El APK lo cachea por `version`; sin red usa su lista empaquetada."""
    import servicios_extra as _se
    return _se.publico()


@router.get("/config/canal")
def get_canal_publico() -> dict:
    """PÚBLICO: el APK lee el canal de comunicación para decidir si muestra el
    botón de WhatsApp (pcg_primero | solo_pcg | whatsapp_libre), y si el PAGO
    ONLINE está disponible."""
    return {
        "canal": reclamos.canal_comunicacion(),
        "pago_online": pago_online_disponible(),
    }


def pago_online_disponible() -> bool:
    """¿Se puede cobrar de verdad con tarjeta/Yape en este ambiente?

    Mientras no haya llaves LIVE de Culqi, un jugador que toque "Pagar ahora"
    se topa con un cobro que no puede completarse. Antes que mostrarle una
    pantalla de pago rota —o peor, simular que pagó— el APK esconde esa opción
    y deja sólo "Pagar en la cancha". Cuando lleguen las llaves reales, esto se
    vuelve true solo y el botón reaparece SIN publicar un APK nuevo.

    `PAGO_ONLINE_ACTIVO` permite forzarlo a mano ("1"/"0") para probar en QAS
    con llaves de prueba; sin esa env se decide por la llave: sólo `sk_live`
    habilita el cobro."""
    forzado = (os.getenv("PAGO_ONLINE_ACTIVO", "") or "").strip()
    if forzado:
        return forzado == "1"
    return (config.CULQI_SECRET_KEY or "").startswith("sk_live")


@router.get("/admin", response_class=HTMLResponse)
def panel() -> HTMLResponse:
    """La torre de QAS y la de PRD son idénticas: se distinguen sólo por la URL,
    y confundirlas hace tomar decisiones sobre el ambiente equivocado (o creer
    que producción está sucia cuando lo sucio es dev). Por eso la página lleva
    SIEMPRE, a la vista, el ambiente y el proyecto Supabase con el que habla."""
    # `no-store`: el JS de la torre viaja DENTRO de este HTML, así que una
    # página cacheada significa lógica vieja corriendo contra un backend nuevo
    # — y el operador viendo resultados que ya no corresponden al código.
    return HTMLResponse(
        content=_HTML.replace("__AMBIENTE__", _etiqueta_ambiente()),
        headers={"Cache-Control": "no-store, must-revalidate",
                 "Pragma": "no-cache"})


def _etiqueta_ambiente() -> str:
    """`PICHANGOL_ENTORNO` manda si está seteado (QAS / PRD); si no, se muestra
    el ref del proyecto Supabase, que ya identifica el ambiente sin ambigüedad."""
    entorno = (os.getenv("PICHANGOL_ENTORNO", "") or "").strip().upper()
    ref = storage_limpieza._ref_de_url(config.SUPABASE_URL)
    if entorno and ref:
        return f"{entorno} · {ref}"
    return entorno or ref or "ambiente sin identificar"


_HTML = r"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Pichangol · Torre de control</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
<style>
  /* Paleta del APP (verde WhatsApp) — co-marca Pichangol + EBIM, solo web admin.
     El primario ('bosque'/'lima') se remapea al verde de la app para congruencia:
     superficies primarias en verde #128C7E con texto blanco. */
  :root{
    --bg:#f4f7f6; --card:#fff; --border:#e6eae8; --text:#1e2422; --muted:#6b7671;
    --green:#128C7E; --green-deep:#0d6f63; --sage:#5AA97F; --verde:#128C7E;
    --bosque:#128C7E; --lima:#ffffff; --teal:#008489; --amarillo:#F2C94C;
    --limaSuave:#e3f2ef; --rojo:#D11F2E;
    /* Tipografías (referencia handoff eSupplier): titulares en serif elegante,
       cuerpo/UI en DM Sans, códigos/ids en monoespaciado. */
    /* Tipografía de marca (LookFeel EBIM 2026): DM Sans para TODO — Regular en
       cuerpo, Semibold/Bold para títulos y énfasis. Sin serifas (se retiró
       Lora). La var conserva el nombre para no tocar cada uso. */
    --serif:'DM Sans',system-ui,sans-serif;
    --mono:ui-monospace,'SF Mono',Menlo,Consolas,'Liberation Mono',monospace;
    --ink:#14201c;
  }
  *{box-sizing:border-box}
  body{margin:0;font-family:'DM Sans',system-ui,sans-serif;background:var(--bg);
    color:var(--text);-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}
  /* Wordmark "Pichang[o]l" — la "o" es una PELOTA (igual que el app). */
  .wm{font-weight:800;letter-spacing:-.02em;display:inline-flex;align-items:center}
  .wm .ball{width:.86em;height:.86em;display:inline-block;vertical-align:-.1em;margin:0 .02em}
  /* El icono es el LOGO del app (cuadro + pin), como SVG. */
  .pin svg{width:100%;height:100%;display:block}
  /* Lockup EBIM (respaldo, marca endosante) */
  .ebim{font-weight:900;letter-spacing:.06em;color:var(--teal);text-transform:uppercase}
  header{position:sticky;top:0;z-index:5;
    background:linear-gradient(120deg,var(--green),var(--green-deep));color:#fff;
    padding:15px 26px;display:flex;align-items:center;gap:12px;
    box-shadow:0 2px 14px rgba(18,140,126,.22)}
  header .pin{width:32px;height:32px;border-radius:50%;background:#fff;
    display:flex;align-items:center;justify-content:center;font-size:16px;
    box-shadow:0 1px 4px rgba(0,0,0,.15)}
  header .brand{display:flex;align-items:center;gap:10px}
  header .wm{font-size:18px;color:#fff}
  header .div{width:1px;height:20px;background:rgba(255,255,255,.25)}
  header .ebim{font-size:13px;color:var(--lima)}
  header .sub{font-size:11px;color:rgba(255,255,255,.6);font-weight:600;margin-left:2px}
  header .sp{flex:1}
  header button{background:rgba(255,255,255,.14);color:#fff;border:0;border-radius:12px;
    padding:8px 12px;font-family:inherit;font-weight:700;cursor:pointer;font-size:13px}
  header button:hover{background:rgba(255,255,255,.24)}
  .wrap{max-width:1440px;margin:0 auto;padding:24px 28px 40px}
  footer{max-width:1440px;margin:0 auto;padding:8px 28px 50px;text-align:center;
    color:var(--muted);font-size:12px;font-weight:600}
  footer .ebim{font-size:12px}
  /* Dashboard: config en fila (grid), listas a ancho completo. */
  .sec{font-size:12px;font-weight:800;text-transform:uppercase;letter-spacing:.11em;
    color:var(--green-deep);margin:30px 0 14px;padding-bottom:9px;
    border-bottom:1px solid var(--limaSuave)}
  .sec:first-of-type{margin-top:6px}
  .cfg-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));
    gap:16px;align-items:stretch}
  .cfg-grid > div{display:flex}
  .cfg-grid .card{flex:1;display:flex;flex-direction:column;margin:0}
  /* --- Maestro–detalle (estilo signNow): lista de rubros + detalle --- */
  .md{display:flex;gap:18px;align-items:flex-start}
  .md-list{width:272px;flex-shrink:0;display:flex;flex-direction:column;gap:8px;
    position:sticky;top:76px}
  .md-item{display:flex;align-items:center;gap:11px;background:#fff;
    border:1px solid var(--border);border-radius:12px;padding:11px 12px;width:100%;
    text-align:left;cursor:pointer;font-family:inherit;transition:.12s}
  .md-item:hover{background:#F7FAF8}
  .md-item.on{border-color:var(--green);background:#F2F8F3;
    box-shadow:inset 3px 0 0 var(--green)}
  .md-ico{width:36px;height:36px;border-radius:9px;background:#EEF4EF;flex-shrink:0;
    display:flex;align-items:center;justify-content:center;font-size:17px}
  .md-txt{min-width:0}
  .md-txt b{display:block;font-size:13.5px;color:var(--ink)}
  .md-txt small{color:var(--muted);font-size:11.5px;font-weight:600}
  .md-detail{flex:1;min-width:0}
  .md-detail .card{margin:0}
  @media(max-width:900px){
    .md{flex-direction:column}
    .md-list{width:100%;position:static;flex-direction:row;overflow-x:auto;
      padding-bottom:4px;-webkit-overflow-scrolling:touch}
    .md-item{width:auto;white-space:nowrap;flex-shrink:0}
    .md-txt small{display:none}
  }
  /* Dashboard (Resumen): tarjetas KPI clicables */
  .kpi-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:14px}
  .kpi{background:#fff;border:1px solid var(--border);border-radius:16px;padding:18px;
    cursor:pointer;transition:.12s;box-shadow:0 3px 10px rgba(0,0,0,.05);text-align:left;
    font-family:inherit}
  .kpi:hover{transform:translateY(-2px);box-shadow:0 8px 18px rgba(0,0,0,.09)}
  .kpi .ki{width:40px;height:40px;border-radius:11px;display:flex;align-items:center;
    justify-content:center;font-size:19px;margin-bottom:12px}
  .kpi .kv{font-size:30px;font-weight:800;color:var(--ink);line-height:1;
    letter-spacing:-.02em}
  .kpi .kl{margin-top:6px;font-size:13px;font-weight:700;color:var(--muted)}
  /* Liquidaciones: encabezado con total grande + filas limpias */
  .liq-head{display:flex;align-items:flex-end;justify-content:space-between;margin:2px 0 14px}
  .liq-total{font-size:34px;font-weight:800;color:var(--ink);letter-spacing:-.02em}
  .liq-sub{color:var(--muted);font-size:13px;font-weight:600;margin-top:2px}
  .liq-row{display:flex;justify-content:space-between;align-items:center;gap:14px;
    padding:14px 0;border-bottom:1px solid var(--border)}
  .liq-row:last-child{border-bottom:0}
  .liq-dueno{font-weight:800;font-size:15px}
  .liq-det{color:var(--muted);font-size:13px;margin-top:2px;overflow:hidden;
    text-overflow:ellipsis;white-space:nowrap}
  .liq-der{text-align:right;white-space:nowrap;display:flex;align-items:center;gap:14px}
  .liq-monto{font-weight:800;font-size:18px}
  .liq-btn{background:var(--verde);color:#fff;border:0;border-radius:999px;
    padding:9px 16px;font-family:inherit;font-weight:700;font-size:13px;cursor:pointer}
  .liq-btn:hover{filter:brightness(1.06)}
  #liquidaciones{margin-top:16px}
  #liquidaciones:empty{display:none}
  /* Liquidaciones agrupadas por LOCAL: encabezado del grupo + chips */
  .liq-resumen{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}
  .liq-grupo-top{display:flex;justify-content:space-between;align-items:flex-start;
    gap:14px;flex-wrap:wrap;border-bottom:1px solid var(--border);padding-bottom:10px}
  .liq-grupo-local{font-weight:800;font-size:17px;letter-spacing:-.01em}
  .liq-grupo-dueno{color:var(--muted);font-size:13px;font-weight:600;margin-top:2px}
  .liq-grupo-tot{display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end}
  .liq-mini{background:#F3F4F6;color:var(--ink);border-radius:999px;padding:5px 11px;
    font-size:12px;font-weight:800;white-space:nowrap}
  .liq-mini-pcg{background:#FFF3D6;color:#8A6100}
  .liq-mini-neto{background:#DDF3E1;color:#166534}
  .liq-canchas{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}
  .liq-cuenta{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-top:6px;font-size:12.5px;font-weight:600;color:var(--ink)}
  .liq-cuenta.sin{color:#8A6100;background:#FFF3D6;border-radius:10px;padding:6px 10px}
  .liq-copy{background:#fff;border:1px solid var(--border);border-radius:999px;padding:4px 10px;font-family:inherit;font-weight:700;font-size:12px;cursor:pointer}
  .liq-copy:disabled{opacity:.5;cursor:default}
  .liq-tag{background:#F3F4F6;color:var(--muted);border-radius:999px;padding:3px 9px;font-size:11px;font-weight:800}
  .liq-tag.ok{background:#DDF3E1;color:#166534}
  .liq-lote{display:flex;justify-content:space-between;align-items:center;gap:10px;padding:8px 0;border-top:1px solid var(--border);font-size:13px}
  .lt-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:14px}
  .lt-lbl{font-weight:700;font-size:12.5px;margin-bottom:6px}
  .lt-chips{display:flex;gap:6px;flex-wrap:wrap}
  @media(max-width:700px){.lt-grid{grid-template-columns:1fr}}
  .liq-cancha{background:#F3F4F6;color:var(--muted);border-radius:999px;
    padding:4px 10px;font-size:11.5px;font-weight:700}
  /* Chips de estado compactos de la lista de reclamos (maestro–detalle). */
  .chip-est{margin-left:auto;flex-shrink:0;border-radius:999px;padding:3px 9px;
    font-size:10.5px;font-weight:800;white-space:nowrap}
  .chip-est.e-pend{background:#FFF3D6;color:#8A6100}
  .chip-est.e-act{background:#DDF3E1;color:#166534}
  .chip-est.e-rech{background:#FBE2E2;color:#9A1722}
  .chip-est.e-otro{background:#EEF0EE;color:#51565D}
  /* --- Layout SaaS (estilo signNow): sidebar CLARO fijo + topbar limpia --- */
  .shell{display:flex;min-height:100vh;background:#fff}
  .side{width:254px;flex-shrink:0;position:sticky;top:0;height:100vh;overflow-y:auto;
    background:#FBFCFB;border-right:1px solid var(--border);
    display:flex;flex-direction:column;padding:16px 12px}
  .side-brand{display:flex;align-items:center;gap:10px;padding:4px 10px 14px;
    border-bottom:1px solid var(--border);margin-bottom:10px}
  .side-brand .pin{width:34px;height:34px;border-radius:10px;overflow:hidden;flex-shrink:0}
  .side-brand .wm{font-size:18px;color:var(--ink)}
  .side-sub{font-size:10.5px;font-weight:700;color:var(--muted);margin-top:1px}
    .side-amb{font-size:11px;font-weight:800;letter-spacing:.4px;margin-top:4px;padding:2px 8px;border-radius:999px;display:inline-block;background:#EBEBEB;color:#555}
    .side-amb.prd{background:#9A1722;color:#fff}
  .side-sub .ebim{color:var(--green-deep);font-size:10.5px}
  .nav{display:flex;flex-direction:column;gap:2px;flex:1}
  .side-cred{text-align:center;font-size:11px;color:var(--muted);font-weight:600;
    padding:12px 0 4px;border-top:1px solid var(--border)}
  .side-cred .ebim{color:var(--green-deep);font-size:11px}
  .colmain{flex:1;min-width:0;display:flex;flex-direction:column}
  .main{flex:1;min-width:0}
  .page-h{font-family:var(--serif);font-size:29px;font-weight:700;letter-spacing:-.01em;
    color:var(--ink);margin:0 0 18px;line-height:1.15}
  /* Encabezado de página: eyebrow (tema) + título serif + subtítulo de contexto. */
  .page-head{margin:0 0 22px;padding-bottom:16px;border-bottom:1px solid var(--border)}
  .page-head .page-eyebrow{font-size:11px;font-weight:800;text-transform:uppercase;
    letter-spacing:.12em;color:var(--green-deep);margin:0 0 7px}
  .page-head .page-h{margin:0 0 7px}
  .page-head .page-sub{margin:0;font-size:14px;color:var(--muted);line-height:1.55;
    max-width:74ch}
  /* Encabezados de tabla estilo handoff: versalitas gris, espaciado de letra. */
  .main th{text-transform:uppercase;letter-spacing:.06em;font-size:10.5px;
    color:var(--muted);font-weight:800}
  /* Menú lateral agrupado por temas (rótulo de grupo). */
  .nav-group{font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:.13em;
    color:rgba(255,255,255,.42);padding:15px 12px 6px;user-select:none}
  .nav-group:first-child{padding-top:4px}
  .side.collapsed .nav-group{display:none}
  /* ===== Ítems del menú lateral (estilo signNow: pill gris al activo) =====
     Conservan la clase histórica .topnav-tab para no tocar el JS. */
  .topnav-tab{display:flex;align-items:center;gap:11px;background:transparent;border:0;
    color:#51565D;text-align:left;padding:10px 12px;border-radius:9px;width:100%;
    font-family:inherit;font-weight:600;font-size:14px;cursor:pointer;transition:.12s}
  .topnav-tab .ico{font-size:16px;width:20px;text-align:center}
  .topnav-tab:hover{background:#F1F4F2;color:var(--ink)}
  .topnav-tab.on{background:#E8F1EA;color:var(--green-deep);font-weight:800}
  .topnav-tab .badge{background:var(--rojo);color:#fff;border-radius:999px;
    font-size:10.5px;font-weight:800;min-width:17px;height:17px;padding:0 5px;
    display:inline-flex;align-items:center;justify-content:center;line-height:1;
    margin-left:auto}
  /* ===== Barra superior limpia: título de la página + acciones + avatar ===== */
  .topbar{position:sticky;top:0;z-index:6;display:flex;align-items:center;gap:10px;
    background:#fff;color:var(--ink);padding:11px 26px;
    border-bottom:1px solid var(--border)}
  .topbar .tb-title{font-weight:800;font-size:16.5px;letter-spacing:-.01em}
  .topbar .sp{flex:1}
  .topbar .tb-btn{background:#fff;color:var(--text);border:1px solid var(--border);
    border-radius:10px;padding:8px 14px;font-family:inherit;font-weight:700;
    font-size:13px;cursor:pointer;display:inline-flex;align-items:center;gap:7px}
  .topbar .tb-btn:hover{background:#F4F6F5}
  .topbar .avatar{width:34px;height:34px;border-radius:50%;background:var(--green-deep);
    color:#fff;font-weight:800;font-size:14px;display:flex;align-items:center;
    justify-content:center;user-select:none;flex-shrink:0}
  .content{max-width:1200px;margin:0;padding:24px 28px 60px}
  .content:has(#redesPanel[style*="block"]){max-width:none}
  #redesPanel .rd-grid{display:grid;grid-template-columns:minmax(380px,520px) minmax(0,1fr);gap:22px;margin-top:10px}
  @media(max-width:1100px){#redesPanel .rd-grid{grid-template-columns:1fr}}
  /* Preloader del pane de Facebook (pedido del director: "agrega un preload siempre"). */
  @keyframes rdgira{to{transform:rotate(360deg)}}
  .rd-spin{display:inline-block;width:18px;height:18px;border:3px solid rgba(0,0,0,.12);border-top-color:var(--green);border-radius:50%;animation:rdgira .8s linear infinite;vertical-align:-4px}
  .rd-spin.chico{width:14px;height:14px;border-width:2px;vertical-align:-3px}
  .rd-spin.blanco{border-color:rgba(255,255,255,.35);border-top-color:#fff}
  #rd_prev{position:relative}
  #rd_prev .rd-velo{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:12px;background:rgba(255,255,255,.82);color:var(--text);font-weight:700;font-size:14px;z-index:2;border-radius:14px;backdrop-filter:blur(1.5px)}
  #rd_prev .rd-velo .rd-spin{width:40px;height:40px;border-width:4px}
  #rd_prev .rd-velo small{font-weight:400;color:var(--muted)}
  #rd_prev img.opaca,#rd_prev video.opaca{opacity:.35;filter:grayscale(.3)}
  #redesPanel button[disabled]{opacity:.6;cursor:progress}
  #redesPanel .rd-tabs{display:flex;gap:6px;flex-wrap:wrap;margin:6px 0 14px;border-bottom:1px solid var(--border);padding-bottom:10px}
  #redesPanel .rd-tabs button{border:1px solid var(--border);background:#fff;border-radius:999px;padding:8px 14px;font-family:inherit;font-weight:700;font-size:13px;cursor:pointer;color:var(--text)}
  #redesPanel .rd-tabs button.on{background:var(--green-deep);color:#fff;border-color:transparent}
  #redesPanel .rd-paso{border:1px solid var(--border);border-radius:14px;background:#fff;margin-bottom:10px;overflow:hidden}
  #redesPanel .rd-paso.abierta{border-color:var(--green);box-shadow:0 2px 12px rgba(0,0,0,.05)}
  #redesPanel .rd-paso>.rd-h{display:flex;align-items:center;gap:12px;padding:12px 14px;cursor:pointer;background:#FAFBFC;user-select:none}
  #redesPanel .rd-paso.abierta>.rd-h{background:#F2F8F3}
  #redesPanel .rd-paso>.rd-h>div{flex:1;min-width:0}
  #redesPanel .rd-paso>.rd-h b{display:block;font-size:14px}
  #redesPanel .rd-paso>.rd-h small{color:var(--muted);display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  #redesPanel .rd-num{width:28px;height:28px;border-radius:50%;background:#E9EDF0;color:var(--text);font-weight:800;display:flex;align-items:center;justify-content:center;font-size:13px;flex-shrink:0}
  #redesPanel .rd-paso.abierta .rd-num{background:var(--green);color:#fff}
  #redesPanel .rd-paso.lista .rd-num{background:#DDF3E4;color:#0B6B33}
  #redesPanel .rd-edit{font-size:12.5px;color:var(--green);font-weight:700;flex-shrink:0}
  #redesPanel .rd-cuerpo{padding:12px 14px 14px}
  #redesPanel .rd-tiles{display:grid;grid-template-columns:1fr 1fr;gap:10px}
  #redesPanel .rd-tile{border:2px solid var(--border);border-radius:14px;padding:12px 14px;cursor:pointer;background:#fff;text-align:left;font-family:inherit;color:var(--text)}
  #redesPanel .rd-tile.on{border-color:var(--green);background:#F2F8F3}
  #redesPanel .rd-tile b{display:block;font-size:15px;margin-bottom:2px}
  #redesPanel .rd-tile small{color:var(--muted);line-height:1.35;display:block}
  #redesPanel .rd-subs{display:flex;gap:6px;flex-wrap:wrap;margin:12px 0 8px}
  #redesPanel .rd-sub{border:1px solid var(--border);background:#fff;border-radius:999px;padding:6px 12px;font-family:inherit;font-size:12.5px;font-weight:700;cursor:pointer;color:var(--text)}
  #redesPanel .rd-sub.on{background:#EBEBEB;border-color:transparent}
  #redesPanel .rd-next{display:flex;gap:8px;align-items:center;margin-top:14px;padding-top:10px;border-top:1px solid var(--border)}
  #redesPanel .rd-next .btn-ap:only-child{margin-left:auto}
  #redesPanel .rd-pill{display:inline-flex;align-items:center;gap:6px;border-radius:999px;padding:5px 11px;font-size:12.5px;font-weight:700;cursor:pointer;border:1px solid transparent}
  #redesPanel .rd-pill.ok{background:#DDF3E4;color:#0B6B33}
  #redesPanel .rd-pill.warn{background:#FFF6E5;color:#8a5a00}
  #redesPanel .rd-pill.bad{background:#FDECEC;color:var(--rojo)}
  #redesPanel .rd-pill.off{background:#EEF0F2;color:var(--muted)}
  .rd-cargando{display:flex;align-items:center;gap:10px;color:var(--muted);padding:14px 4px}
  @media(max-width:640px){
    .topbar{padding:10px 14px}
    .content{padding:18px 14px 50px}
    .topbar .tb-btn .lbl{display:none}
  }
  @media(max-width:820px){
    .shell{flex-direction:column}
    .side{width:auto;height:auto;position:static;padding:10px 10px 4px;overflow:visible}
    .side-brand{border-bottom:0;margin-bottom:2px;padding-bottom:4px}
    .nav{flex-direction:row;overflow-x:auto;gap:4px;padding-bottom:6px;
      -webkit-overflow-scrolling:touch;scrollbar-width:thin}
    .topnav-tab{white-space:nowrap;width:auto;padding:9px 12px;font-size:13.5px}
    .topnav-tab .badge{margin-left:2px}
    .side-cred{display:none}
    .side-toggle{display:none}
    .side.collapsed{width:auto;padding:12px 14px;align-items:center}
    .side.collapsed .sb-txt,.side.collapsed .side-btn .lbl{display:inline}
    .side.collapsed .nav-i{font-size:13.5px;padding:9px 12px;gap:11px}
    .side.collapsed .nav-i .ico{font-size:16px}
  }
  .tabs{display:flex;gap:8px;overflow:auto;padding:4px 0 14px}
  .tab{white-space:nowrap;border:1px solid var(--border);background:#fff;color:var(--text);
    border-radius:999px;padding:8px 14px;font-weight:700;font-size:13px;cursor:pointer}
  .tab.on{background:var(--bosque);color:var(--lima);border-color:var(--bosque)}
  .tab .n{display:inline-block;margin-left:6px;background:var(--limaSuave);color:var(--bosque);
    border-radius:999px;padding:0 7px;font-size:11px;font-weight:900}
  .tab.on .n{background:rgba(255,255,255,.2);color:#fff}
  .card{background:var(--card);border:1px solid var(--border);border-radius:18px;
    padding:18px;margin:0;box-shadow:0 1px 2px rgba(18,140,126,.04),
    0 10px 26px -18px rgba(18,140,126,.28)}
  .card .top{display:flex;align-items:flex-start;gap:10px}
  .card h3{margin:0;font-family:var(--serif);font-size:18px;font-weight:700;
    letter-spacing:-.01em;color:var(--ink);flex:1;line-height:1.25}
  .cod{font-family:var(--mono);background:#eef3f0;color:var(--green-deep);font-weight:600;
    font-size:11.5px;letter-spacing:.01em;border:1px solid #dfe8e3;
    border-radius:8px;padding:4px 9px;white-space:nowrap}
  .row{font-size:13px;color:var(--muted);margin-top:5px}
  .row b{color:var(--text);font-weight:700}
  .chip{display:inline-block;border-radius:999px;padding:4px 11px;font-size:11px;
    font-weight:700;letter-spacing:.02em;margin-top:8px}
  .est-pendiente_triage{background:#FBEAD2;color:#9A5B12}
  .est-aprobado_triage{background:#DDEBFF;color:#1E4FA3}
  .est-pendiente_validacion{background:#FFF3C4;color:#8A6D00}
  .est-activada{background:#D7F5E3;color:#1F8F4E}
  .est-rechazada{background:#FAD7DB;color:#9A1722}
  .wa{display:inline-flex;align-items:center;gap:7px;margin-top:10px;text-decoration:none;
    background:#E7F8EE;border:1px solid #BBE8CF;border-radius:10px;padding:8px 12px;
    color:#1F8F4E;font-weight:800;font-size:13px}
  .actions{display:flex;gap:10px;margin-top:14px}
  .actions button{flex:1;border-radius:16px;padding:11px;font-family:inherit;
    font-weight:800;font-size:14px;cursor:pointer;border:1px solid var(--border)}
  .btn-ap{background:var(--bosque);color:var(--lima);border-color:var(--bosque)}
  .btn-sec{background:#fff;color:var(--bosque);border-color:var(--border)}
  .btn-rc{background:#fff;color:var(--rojo);border-color:#F3C9CE}
  .btn-ap:disabled,.btn-rc:disabled{opacity:.5;cursor:default}
  .btn-lib{width:100%;border-radius:14px;padding:9px;font-family:inherit;
    font-weight:700;font-size:13px;cursor:pointer;background:#fff;color:#8a5a00;
    border:1px solid #E9D8A6}
  .btn-lib:disabled{opacity:.5;cursor:default}
  .actions .seg{background:#fff;color:var(--text)}
  .actions .seg.on{background:var(--bosque);color:var(--lima);border-color:var(--bosque)}
  .modosel{font-family:inherit;font-size:12px;padding:5px 8px;border:1px solid var(--border);
    border-radius:8px;margin-left:6px;background:#fff;color:var(--text)}
  .fecha{font-size:12px;color:var(--muted);font-weight:700;margin-top:6px;
    display:flex;align-items:center;gap:6px}
  .mapbox{margin-top:12px;border:1px solid var(--border);border-radius:14px;
    overflow:hidden;background:#EEF1EC}
  .mapbox iframe{display:block;width:100%;height:180px;border:0}
  .maphead{display:flex;align-items:center;gap:8px;flex-wrap:wrap;
    padding:9px 12px;font-size:12px;font-weight:700;color:var(--text);
    border-bottom:1px solid var(--border);background:#F7F9F5}
  .maphead .lnk{margin-left:auto;color:var(--teal);text-decoration:none;font-weight:800}
  .badge-ubi{border-radius:999px;padding:2px 9px;font-size:11px;font-weight:800}
  .ubi-ok{background:#D7F5E3;color:#1F8F4E}
  .ubi-no{background:#FAD7DB;color:#9A1722}
  .ubi-sd{background:#F0ECE2;color:#7C6F5C}
  .nomap{padding:12px;font-size:12px;color:var(--muted);font-weight:700}
  /* switch */
  .sw{display:inline-flex;align-items:center;gap:10px;cursor:pointer;margin-top:12px}
  .sw input{display:none}
  .sw .track{width:46px;height:26px;border-radius:999px;background:#CDD5CB;
    position:relative;transition:.15s}
  .sw .knob{position:absolute;top:3px;left:3px;width:20px;height:20px;border-radius:50%;
    background:#fff;transition:.15s;box-shadow:0 1px 3px rgba(0,0,0,.25)}
  .sw input:checked + .track{background:var(--verde)}
  .sw input:checked + .track .knob{left:23px}
  .empty{text-align:center;color:var(--muted);padding:50px 10px;grid-column:1/-1}
  .toast{position:fixed;left:50%;bottom:24px;transform:translateX(-50%);
    background:var(--bosque);color:#fff;padding:12px 18px;border-radius:12px;
    font-weight:700;font-size:14px;z-index:20;box-shadow:0 6px 20px rgba(0,0,0,.2)}
  /* login (split estilo eChange: lado de marca verde + formulario blanco) */
  .gate{position:fixed;inset:0;background:#E9EDE8;display:flex;align-items:center;
    justify-content:center;padding:24px;z-index:30}
  .gate .split{display:flex;width:100%;max-width:1000px;min-height:580px;background:#fff;
    border-radius:24px;overflow:hidden;box-shadow:0 28px 80px rgba(0,0,0,.20)}
  .gate .lado{flex:1.08;background:linear-gradient(155deg,#14463A 0%,#0E332B 70%,#0A2822 100%);
    color:#fff;padding:46px 42px;display:none;flex-direction:column}
  .gate .lado .marca{display:flex;align-items:center;gap:10px;margin-bottom:42px}
  .gate .lado .pin{width:34px;height:34px;border-radius:10px;overflow:hidden}
  .gate .lado h1{margin:0 0 6px;font-family:var(--serif);font-weight:700;font-size:34px;
    letter-spacing:-.01em}
  .gate .lado .eyebrow{font-size:12px;font-weight:800;letter-spacing:.14em;color:#AEEA94;
    text-transform:uppercase;margin-bottom:18px}
  .gate .lado .pitch{color:#D7E5DC;font-size:14.5px;line-height:1.55;margin:0 0 30px;max-width:400px}
  .gate .feat{display:flex;gap:14px;margin-bottom:22px;align-items:flex-start}
  .gate .feat .fi{flex:0 0 auto;width:38px;height:38px;border-radius:50%;background:rgba(174,234,148,.16);
    display:flex;align-items:center;justify-content:center;font-size:17px}
  .gate .feat b{display:block;font-size:14.5px;margin-bottom:3px}
  .gate .feat span{color:#BFD3C7;font-size:13px;line-height:1.5}
  .gate .lado .foot{margin-top:auto;color:#9DB8AA;font-size:12px}
  .gate .form{flex:1;padding:46px 42px;display:flex;flex-direction:column;justify-content:center;
    max-width:520px;margin:0 auto;width:100%}
  .gate .form h2,.gate .form>div>h2{margin:0 0 4px;font-family:var(--serif);font-weight:700;font-size:26px;
    letter-spacing:-.01em;color:var(--ink)}
  .gate .form .sub{margin:0 0 24px;color:var(--muted);font-size:14px}
  .gate .campo{position:relative;margin-bottom:14px}
  .gate .campo label{position:absolute;top:-7px;left:12px;background:#fff;padding:0 5px;
    font-size:11.5px;font-weight:700;color:var(--muted)}
  .gate .campo input{width:100%;padding:14px 44px 14px 40px;border:1px solid var(--border);
    border-radius:12px;font-family:inherit;font-size:15px;background:#F6F9F5}
  .gate .campo input:focus{outline:2px solid #128C7E33;border-color:#128C7E}
  .gate .campo .ic{position:absolute;left:12px;top:50%;transform:translateY(-50%);
    color:var(--muted);font-size:16px}
  .gate .campo .ojo{position:absolute;right:10px;top:50%;transform:translateY(-50%);
    background:none;border:0;cursor:pointer;color:var(--muted);font-size:17px;padding:4px;width:auto}
  .gate .form button.cta{width:100%;background:var(--bosque);color:#fff;border:0;
    border-radius:12px;padding:14px;font-family:inherit;font-weight:800;font-size:15px;
    cursor:pointer;margin-top:6px}
  .gate .form button.cta:hover{filter:brightness(1.08)}
  .gate .err{color:var(--rojo);font-size:13px;font-weight:700;min-height:18px;margin-bottom:8px}
  .gate .alt{margin-top:18px;text-align:center;font-size:12.5px;color:var(--muted)}
  .gate .alt a{color:#128C7E;font-weight:700;cursor:pointer;text-decoration:none}
  .gate .form .foot{margin-top:26px;text-align:center;color:var(--muted);font-size:12px;font-weight:600}
  @media(min-width:820px){ .gate .lado{display:flex} .gate .form{margin:0} }
</style>
</head>
<body>
<div class="gate" id="gate">
  <div class="split">
    <div class="lado">
      <div class="marca">
        <div class="pin"><svg viewBox="0 0 48 48"><rect x="1.5" y="1.5" width="45" height="45" rx="12" fill="#AEEA94"/><path d="M24 11.5c-4.3 0-7.8 3.5-7.8 7.8 0 5.9 7.8 14.2 7.8 14.2s7.8-8.3 7.8-14.2c0-4.3-3.5-7.8-7.8-7.8zm0 10.7a2.9 2.9 0 110-5.8 2.9 2.9 0 010 5.8z" fill="#14463A"/></svg></div>
        <span class="wm" style="font-size:20px;color:#fff">Pichang<svg class="ball" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><polygon points="12,8.2 14.9,10.3 13.8,13.8 10.2,13.8 9.1,10.3"/><path d="M12 8.2V4.3M14.9 10.3l3.6-1.7M13.8 13.8l2.5 3.2M10.2 13.8l-2.5 3.2M9.1 10.3L5.5 8.6"/></svg>l</span>
      </div>
      <h1>Torre de control</h1>
      <div class="eyebrow">Operación del marketplace</div>
      <p class="pitch">Desde aquí el equipo opera Pichangol: reclamos de
        propiedad, cobros y liquidaciones, disputas y comunicación con dueños
        y jugadores.</p>
      <div class="feat"><div class="fi">📋</div><div><b>Reclamos con evidencia</b>
        <span>Cada solicitud llega con fecha, identidad validada y el mapa de
        dónde se envió, para aprobar con confianza.</span></div></div>
      <div class="feat"><div class="fi">💸</div><div><b>La plata, clara</b>
        <span>Cobros online, comisiones y "por recibir" de cada dueño, cuadrados
        con la billetera de la app.</span></div></div>
      <div class="feat"><div class="fi">🛡️</div><div><b>Sesión protegida</b>
        <span>Usuario, contraseña y código de tu app autenticadora (verificación en dos pasos); la sesión expira sola.</span></div></div>
      <div class="foot">Conexión cifrada · Pichangol · una solución de <span class="ebim" style="color:#AEEA94">EBIM</span></div>
    </div>
    <div class="form">
      <div id="paso1">
      <h2>Entrar</h2>
      <p class="sub">Con tu cuenta de operador de la torre de control.</p>
      <div class="err" id="gateErr"></div>
      <div class="campo" id="campoUsr">
        <label>Correo</label>
        <span class="ic">✉️</span>
        <input id="usr" type="email" placeholder="tucorreo@ebim.pe" autocomplete="username">
      </div>
      <div class="campo">
        <label id="lblPwd">Contraseña</label>
        <span class="ic">🔒</span>
        <input id="pwd" type="password" placeholder="••••••••" autocomplete="current-password">
        <button type="button" class="ojo" onclick="verPwd()" title="Mostrar/ocultar">👁</button>
      </div>
      <button class="cta" onclick="entrar()">Iniciar sesión</button>
      <div class="alt" id="altModo" style="display:none">¿Sin usuario? <a onclick="modoToken(true)">Entrar con token de administrador</a></div>
      </div>
      <div id="paso2" style="display:none">
        <h2>Verificación en dos pasos</h2>
        <p class="sub" id="p2sub">Escribe el código de 6 dígitos de tu app autenticadora.</p>
        <div class="err" id="gateErr2"></div>
        <div class="campo">
          <label id="lblCod">Código</label>
          <span class="ic">🔐</span>
          <input id="cod" type="text" inputmode="numeric" autocomplete="one-time-code" placeholder="123 456" maxlength="12">
        </div>
        <label class="chk" style="display:flex;gap:8px;align-items:center;font-size:13px;margin:-4px 0 12px"><input type="checkbox" id="recordar"> Confiar en este dispositivo por 30 días</label>
        <button class="cta" onclick="verificar2fa()">Verificar y entrar</button>
        <div class="alt"><a onclick="usarRecuperacion()" id="altRec">¿Sin tu teléfono? Usa un código de recuperación</a> · <a onclick="volverPaso1()">Volver</a></div>
      </div>
      <div id="pasoEnrolar" style="display:none">
        <h2>Activa la verificación en dos pasos</h2>
        <p class="sub">Es tu primer ingreso con el nuevo esquema. Escanea este QR con <b>Google Authenticator</b>, <b>Microsoft Authenticator</b> o <b>Authy</b> y escribe el código que te muestra.</p>
        <div class="err" id="gateErr3"></div>
        <div style="display:flex;gap:14px;align-items:center;margin-bottom:12px;flex-wrap:wrap">
          <img id="qr2fa" alt="QR para la app autenticadora" style="width:168px;height:168px;border:1px solid var(--border);border-radius:12px;background:#fff">
          <div style="font-size:12.5px;color:var(--muted);flex:1;min-width:180px">Si no puedes escanear, agrega la cuenta a mano con esta clave:<br><code id="sec2fa" style="font-size:12px;word-break:break-all;user-select:all"></code></div>
        </div>
        <div class="campo">
          <label>Código de la app</label>
          <span class="ic">🔐</span>
          <input id="codEnrolar" type="text" inputmode="numeric" autocomplete="one-time-code" placeholder="123 456" maxlength="8">
        </div>
        <label class="chk" style="display:flex;gap:8px;align-items:center;font-size:13px;margin:-4px 0 12px"><input type="checkbox" id="recordarEnrolar"> Confiar en este dispositivo por 30 días</label>
        <button class="cta" onclick="verificar2fa(true)">Activar y entrar</button>
        <div class="alt"><a onclick="volverPaso1()">Volver</a></div>
      </div>
      <div id="pasoRec" style="display:none">
        <h2>Guarda tus códigos de recuperación</h2>
        <p class="sub">Si pierdes el teléfono, cada uno de estos códigos te deja entrar UNA vez. Guárdalos en un lugar seguro: no se vuelven a mostrar.</p>
        <div id="recLista" style="display:grid;grid-template-columns:1fr 1fr;gap:6px;font-family:ui-monospace,Menlo,monospace;font-size:14px;font-weight:700;background:#F4F7FA;border:1px solid var(--border);border-radius:12px;padding:12px 14px;margin-bottom:12px"></div>
        <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px">
          <button type="button" class="btn-sec" onclick="copiarRec()">📋 Copiar</button>
          <button type="button" class="btn-sec" onclick="descargarRec()">⬇️ Descargar .txt</button>
        </div>
        <button class="cta" onclick="mostrarApp()">Ya los guardé, entrar</button>
      </div>
      <div class="foot">Pichang<span style="letter-spacing:0">o</span>l · una solución de <span class="ebim">EBIM</span></div>
    </div>
  </div>
</div>

<div id="app" style="display:none">
 <div class="shell">
  <aside class="side" id="side">
    <div class="side-brand">
      <div class="pin"><svg viewBox="0 0 48 48"><rect x="1.5" y="1.5" width="45" height="45" rx="12" fill="#128C7E"/><path d="M24 11.5c-4.3 0-7.8 3.5-7.8 7.8 0 5.9 7.8 14.2 7.8 14.2s7.8-8.3 7.8-14.2c0-4.3-3.5-7.8-7.8-7.8zm0 10.7a2.9 2.9 0 110-5.8 2.9 2.9 0 010 5.8z" fill="#fff"/></svg></div>
      <div>
        <span class="wm">Pichang<svg class="ball" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><polygon points="12,8.2 14.9,10.3 13.8,13.8 10.2,13.8 9.1,10.3"/><path d="M12 8.2V4.3M14.9 10.3l3.6-1.7M13.8 13.8l2.5 3.2M10.2 13.8l-2.5 3.2M9.1 10.3L5.5 8.6"/></svg>l</span>
        <div class="side-sub">Torre de control · <span class="ebim">EBIM</span></div>
        <div class="side-amb" id="side_amb" title="Proyecto Supabase al que habla esta torre"></div>
      </div>
    </div>
    <nav class="nav" id="topnav">
      <button class="topnav-tab on" data-sec="resumen" onclick="mostrarSeccion('resumen')"><span class="ico">📊</span> Resumen</button>
      <button class="topnav-tab" data-sec="reclamos" onclick="mostrarSeccion('reclamos')"><span class="ico">📋</span> Reclamos</button>
      <button class="topnav-tab" data-sec="operacion" onclick="mostrarSeccion('operacion')"><span class="ico">✅</span> Operación</button>
      <button class="topnav-tab" data-sec="cobros" onclick="mostrarSeccion('cobros')"><span class="ico">💳</span> Cobros</button>
      <button class="topnav-tab" data-sec="liquidaciones" onclick="mostrarSeccion('liquidaciones')"><span class="ico">💸</span> Liquidaciones</button>
      <button class="topnav-tab" data-sec="disputas" onclick="mostrarSeccion('disputas')"><span class="ico">⚖️</span> Disputas</button>
      <button class="topnav-tab" data-sec="identidad" onclick="mostrarSeccion('identidad')"><span class="ico">🪪</span> Identidad</button>
      <button class="topnav-tab" data-sec="comunicacion" onclick="mostrarSeccion('comunicacion')"><span class="ico">💬</span> Comunicación</button>
      <button class="topnav-tab" data-sec="pruebas" onclick="mostrarSeccion('pruebas')"><span class="ico">🧪</span> Pruebas</button>
    </nav>
    <div class="side-cred">Una solución de <span class="ebim">EBIM</span></div>
  </aside>
  <div class="colmain">
  <header class="topbar">
    <div class="tb-title" id="tbTitle">Resumen</div>
    <div class="sp"></div>
    <button class="tb-btn" onclick="cargar();cargarLiquidaciones()" title="Actualizar">↻ <span class="lbl">Actualizar</span></button>
    <button class="tb-btn" onclick="salir()" title="Cerrar sesión">⎋ <span class="lbl">Salir</span></button>
    <div class="avatar" id="avatarOp" title="Operador">P</div>
  </header>
  <main class="main content">
    <section id="page-resumen" class="page">
      <div class="page-head">
        <div class="page-eyebrow">Hoy</div>
        <h1 class="page-h">Resumen de la operación</h1>
        <p class="page-sub">El pulso del marketplace de un vistazo. Toca una
          tarjeta para ir directo a esa sección.</p>
      </div>
      <div class="kpi-grid" id="kpis"></div>
    </section>
    <section id="page-reclamos" class="page" style="display:none">
      <div class="page-head">
        <div class="page-eyebrow">Propiedad</div>
        <h1 class="page-h">Reclamos de propiedad</h1>
        <p class="page-sub">Aprueba, rechaza o libera los reclamos de canchas. Cada
          tarjeta muestra desde dónde se envió la solicitud y su estado.</p>
      </div>
      <div class="tabs" id="tabs"></div>
      <!-- Maestro–detalle: solicitudes a la izquierda, expediente a la derecha. -->
      <div class="md">
        <aside class="md-list" id="lista"></aside>
        <div class="md-detail" id="reclamoDetalle"></div>
      </div>
    </section>
    <section id="page-liquidaciones" class="page" style="display:none">
      <div class="page-head">
        <div class="page-eyebrow">Finanzas</div>
        <h1 class="page-h">Liquidaciones a dueños</h1>
        <p class="page-sub">Reservas online pagadas por el jugador: transfiere el
          neto al dueño (Yape/banco) y márcalo como pagado.</p>
      </div>
      <div id="liquidaciones"></div>
    </section>
    <section id="page-cobros" class="page" style="display:none">
      <div class="page-head">
        <div class="page-eyebrow">Finanzas</div>
        <h1 class="page-h">Cobros, comisiones y márgenes</h1>
        <p class="page-sub">Comisión de la plataforma, márgenes por banco, marketing,
          circuito, ranking y suscripción Pro.</p>
      </div>
      <!-- Maestro–detalle (estilo signNow): lista de rubros a la izquierda,
           detalle del rubro seleccionado a la derecha. -->
      <div class="md">
        <aside class="md-list">
          <button class="md-item on" data-pane="comision" onclick="mostrarPane(this,'comision')">
            <span class="md-ico">💼</span>
            <span class="md-txt"><b>Comisión</b><small>De la plataforma, por cobro</small></span>
          </button>
          <button class="md-item" data-pane="margenes" onclick="mostrarPane(this,'margenes')">
            <span class="md-ico">🏦</span>
            <span class="md-txt"><b>Márgenes</b><small>Por banco / pasarela</small></span>
          </button>
          <button class="md-item" data-pane="marketing" onclick="mostrarPane(this,'marketing')">
            <span class="md-ico">📣</span>
            <span class="md-txt"><b>Marketing</b><small>Servicios y precios</small></span>
          </button>
          <button class="md-item" data-pane="circuitoPanel" onclick="mostrarPane(this,'circuitoPanel')">
            <span class="md-ico">🎾</span>
            <span class="md-txt"><b>Circuito</b><small>Retos y torneos</small></span>
          </button>
          <button class="md-item" data-pane="rankingPanel" onclick="mostrarPane(this,'rankingPanel')">
            <span class="md-ico">🏆</span>
            <span class="md-txt"><b>Ranking</b><small>Incentivos a jugadores</small></span>
          </button>
          <button class="md-item" data-pane="proPanel" onclick="mostrarPane(this,'proPanel')">
            <span class="md-ico">⭐</span>
            <span class="md-txt"><b>Pichangol Pro</b><small>Suscripción mensual</small></span>
          </button>
          <button class="md-item" data-pane="recargasQr" onclick="mostrarPane(this,'recargasQr');cargarRecargasQr()">
            <span class="md-ico">📲</span>
            <span class="md-txt"><b>Recargas QR</b><small>Yape directo · aprobar/rechazar</small></span>
          </button>
          <button class="md-item" data-pane="promosPanel" onclick="mostrarPane(this,'promosPanel');cargarPromos()">
            <span class="md-ico">🎁</span>
            <span class="md-txt"><b>Promociones</b><small>Bono de recarga · cupones</small></span>
          </button>
          <button class="md-item" data-pane="reclamacionesPanel" onclick="mostrarPane(this,'reclamacionesPanel');cargarReclamaciones()">
            <span class="md-ico">📕</span>
            <span class="md-txt"><b>Libro de Reclamaciones</b><small>INDECOPI · responder en 15 días hábiles</small></span>
          </button>
          <button class="md-item" data-pane="cancelacionesPanel" onclick="mostrarPane(this,'cancelacionesPanel');cargarCancelacionesWeb()">
            <span class="md-ico">↩️</span>
            <span class="md-txt"><b>Cancelaciones web</b><small>Reembolsos Culqi · devoluciones a mano · deudas de dueños</small></span>
          </button>
        </aside>
        <div class="md-detail">
          <div class="md-pane" id="comision"></div>
          <div class="md-pane" id="margenes" style="display:none"></div>
          <div class="md-pane" id="marketing" style="display:none"></div>
          <div class="md-pane" id="circuitoPanel" style="display:none"></div>
          <div class="md-pane" id="rankingPanel" style="display:none"></div>
          <div class="md-pane" id="proPanel" style="display:none"></div>
          <div class="md-pane" id="recargasQr" style="display:none"></div>
          <div class="md-pane" id="promosPanel" style="display:none"></div>
          <div class="md-pane" id="reclamacionesPanel" style="display:none"></div>
          <div class="md-pane" id="cancelacionesPanel" style="display:none"></div>
        </div>
      </div>
    </section>
    <section id="page-disputas" class="page" style="display:none">
      <div class="page-head">
        <div class="page-eyebrow">Finanzas</div>
        <h1 class="page-h">Disputas del marketplace</h1>
        <p class="page-sub">Resuelve reclamos de compras: dar la razón al vendedor
          (liberar) o reembolsar al comprador.</p>
      </div>
      <div id="disputas"></div>
    </section>
    <section id="page-identidad" class="page" style="display:none">
      <div class="page-head">
        <div class="page-eyebrow">Confianza</div>
        <h1 class="page-h">Verificaciones de identidad</h1>
        <p class="page-sub">1 documento = 1 cuenta. Revoca una verificación de DNI
          si hubo un error o fraude.</p>
      </div>
      <div id="dniPanel"></div>
    </section>
    <section id="page-operacion" class="page" style="display:none">
      <div class="page-head">
        <div class="page-eyebrow">Propiedad</div>
        <h1 class="page-h">Aprobación y operación</h1>
        <p class="page-sub">Modo de aprobación de canchas (marcha blanca / nuevo
          flujo), exigir ubicación al reclamar y modo de pichangas.</p>
      </div>
      <div class="md">
        <aside class="md-list">
          <button class="md-item on" onclick="mostrarPane(this,'modo')">
            <span class="md-ico">🛡️</span>
            <span class="md-txt"><b>Modo de aprobación</b><small>Marcha blanca / nuevo flujo</small></span>
          </button>
          <button class="md-item" onclick="mostrarPane(this,'ubic')">
            <span class="md-ico">📍</span>
            <span class="md-txt"><b>Ubicación al reclamar</b><small>Anti-fraude por GPS</small></span>
          </button>
          <button class="md-item" onclick="mostrarPane(this,'pichangaModo')">
            <span class="md-ico">⚽</span>
            <span class="md-txt"><b>Pichangas</b><small>Partidos abiertos</small></span>
          </button>
        </aside>
        <div class="md-detail">
          <div class="md-pane" id="modo"></div>
          <div class="md-pane" id="ubic" style="display:none"></div>
          <div class="md-pane" id="pichangaModo" style="display:none"></div>
        </div>
      </div>
    </section>
    <section id="page-comunicacion" class="page" style="display:none">
      <div class="page-head">
        <div class="page-eyebrow">Sistema</div>
        <h1 class="page-h">Comunicación con la app</h1>
        <p class="page-sub">Canal de avisos que ve el APK y los datos de la empresa
          (WhatsApp por país, correo, razón social…) que usan el app, la web y
          las páginas legales.</p>
      </div>
      <div class="md">
        <aside class="md-list">
          <button class="md-item on" onclick="mostrarPane(this,'canal')">
            <span class="md-ico">📢</span>
            <span class="md-txt"><b>Canal de avisos</b><small>Mensajes que ve el APK</small></span>
          </button>
          <button class="md-item" onclick="mostrarPane(this,'empresaPanel');cargarEmpresa()">
            <span class="md-ico">🏢</span>
            <span class="md-txt"><b>Datos de la empresa</b><small>Razón social · RUC · dirección · WhatsApp por país · correo · horario</small></span>
          </button>
          <button class="md-item" onclick="mostrarPane(this,'serviciosPanel');cargarServicios()">
            <span class="md-ico">🧩</span>
            <span class="md-txt"><b>Servicios extra</b><small>Catálogo global de add-ons (piscina, árbitro, entrada general…) · sugerencias de dueños</small></span>
          </button>
          <button class="md-item" onclick="mostrarPane(this,'redesPanel');cargarRedes()">
            <span class="md-ico">📣</span>
            <span class="md-txt"><b>Publicar en Facebook</b><small>Piezas con fotos reales de las canchas · publicación directa en la página de Pichangol</small></span>
          </button>
        </aside>
        <div class="md-detail">
          <div class="md-pane" id="canal"></div>
          <div class="md-pane" id="empresaPanel" style="display:none"></div>
          <div class="md-pane" id="serviciosPanel" style="display:none"></div>
          <div class="md-pane" id="redesPanel" style="display:none"></div>
        </div>
      </div>
    </section>
    <section id="page-pruebas" class="page" style="display:none">
      <div class="page-head">
        <div class="page-eyebrow">Sistema</div>
        <h1 class="page-h">Pruebas y mantenimiento</h1>
        <p class="page-sub">Reiniciar libros de prueba y dejar el servidor en virgen.
          Acciones sensibles — úsalas con cuidado.</p>
      </div>
      <div class="cfg-grid">
        <div id="seguridad"></div>
        <div id="mantenimiento"></div>
      </div>
    </section>
  </main>
  </div>
 </div>
</div>

<script>
const FILTROS = [
  ['pendiente_triage','Por aprobar'],
  ['activada','Activadas'],
  ['rechazada','Rechazadas'],
  ['','Todas'],
];
let filtro = 'pendiente_triage';
let cache = [];
let modoGlobal = 'marcha_blanca';
let overrides = {};
let exigirUbic = false;   // ¿se exige GPS coincidente para aprobar?
let ubicMaxM = 150;

function tok(){ return localStorage.getItem('pichangol_admin_tok') || ''; }
function headers(){ return {'Content-Type':'application/json','X-Admin-Token':tok()}; }

let conToken = false; // modo respaldo: entrar con el token clásico

function modoToken(on){
  conToken = on;
  document.getElementById('campoUsr').style.display = on ? 'none' : '';
  document.getElementById('lblPwd').textContent = on ? 'Token de administrador' : 'Contraseña';
  document.getElementById('pwd').placeholder = on ? 'Token' : '••••••••';
  document.getElementById('altModo').innerHTML = on
    ? '<a onclick="modoToken(false)">← Volver al ingreso con usuario y contraseña</a>'
    : '¿Sin usuario? <a onclick="modoToken(true)">Entrar con token de administrador</a>';
  document.getElementById('gateErr').textContent='';
}

function verPwd(){
  const p = document.getElementById('pwd');
  p.type = p.type === 'password' ? 'text' : 'password';
}

let pre2fa = '', recCodigos = [];
function mostrarPaso(id){
  ['paso1','paso2','pasoEnrolar','pasoRec'].forEach(x=>{ const el=document.getElementById(x); if(el) el.style.display = (x===id)?'':'none'; });
  const foco = {paso2:'cod', pasoEnrolar:'codEnrolar', paso1:'usr'}[id];
  if(foco){ const f=document.getElementById(foco); if(f) setTimeout(()=>f.focus(),50); }
}
function volverPaso1(){ pre2fa=''; document.getElementById('cod').value=''; document.getElementById('codEnrolar').value=''; mostrarPaso('paso1'); }
function usarRecuperacion(){
  document.getElementById('lblCod').textContent='Código de recuperación';
  document.getElementById('cod').placeholder='XXXX-XXXX'; document.getElementById('cod').inputMode='text';
  document.getElementById('p2sub').textContent='Escribe uno de los códigos de recuperación que guardaste al activar la verificación. Cada uno vale una sola vez.';
  document.getElementById('altRec').style.display='none';
  document.getElementById('cod').focus();
}
function guardarSesion(j){
  localStorage.setItem('pichangol_admin_tok', j.token);
  localStorage.setItem('pichangol_admin_usr', j.usuario || '');
  if(j.dispositivo) localStorage.setItem('pichangol_admin_dev', j.dispositivo);
}
async function entrar(){
  const err = document.getElementById('gateErr');
  err.textContent='';
  const clave = document.getElementById('pwd').value.trim();
  if(conToken){
    if(!clave){ err.textContent='Ingresa el token.'; return; }
    const r = await fetch('/admin/api/sesion',{headers:{'X-Admin-Token':clave}});
    if(r.ok){ localStorage.setItem('pichangol_admin_tok',clave); mostrarApp(); }
    else if(r.status===503) err.textContent='El panel no está configurado en el servidor (ADMIN_PANEL_TOKEN).';
    else err.textContent='Token inválido.';
    return;
  }
  const usuario = document.getElementById('usr').value.trim();
  if(!usuario || !clave){ err.textContent='Ingresa tu correo y contraseña.'; return; }
  const dispositivo = localStorage.getItem('pichangol_admin_dev') || '';
  const r = await fetch('/admin/api/login',{method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({usuario, clave, dispositivo})});
  if(r.ok){
    const j = await r.json();
    if(j.paso==='codigo'){ pre2fa=j.pre; mostrarPaso('paso2'); return; }
    if(j.paso==='enrolar'){
      pre2fa=j.pre;
      document.getElementById('qr2fa').src = j.qr || '';
      document.getElementById('sec2fa').textContent = j.secreto || '';
      mostrarPaso('pasoEnrolar'); return;
    }
    guardarSesion(j);
    mostrarApp();
  } else if(r.status===429){
    err.textContent='Demasiados intentos. Espera unos minutos y vuelve a probar.';
  } else if(r.status===503){
    const j = await r.json().catch(()=>({}));
    err.textContent = (j.detail==='usuarios_no_configurados')
      ? 'Aún no hay usuarios configurados (ADMIN_PANEL_USUARIOS). Usa "Entrar con token".'
      : 'El panel no está configurado en el servidor (ADMIN_PANEL_TOKEN).';
    if(j.detail==='usuarios_no_configurados') document.getElementById('altModo').style.display='';
  } else {
    err.textContent='Correo o contraseña incorrectos.';
  }
}
async function verificar2fa(enrolando){
  const err = document.getElementById(enrolando?'gateErr3':'gateErr2');
  err.textContent='';
  const codigo = document.getElementById(enrolando?'codEnrolar':'cod').value.trim();
  const recordar = !!document.getElementById(enrolando?'recordarEnrolar':'recordar').checked;
  if(!codigo){ err.textContent='Escribe el código.'; return; }
  const r = await fetch('/admin/api/login/2fa',{method:'POST',headers:{'Content-Type':'application/json'},
    body: JSON.stringify({pre:pre2fa, codigo, recordar})});
  if(r.ok){
    const j = await r.json();
    guardarSesion(j);
    if(j.recuperacion && j.recuperacion.length){
      recCodigos = j.recuperacion;
      document.getElementById('recLista').innerHTML = recCodigos.map(c=>`<span>${esc(c)}</span>`).join('');
      mostrarPaso('pasoRec'); return;
    }
    if(j.recuperacion_usada) toast('Entraste con un código de recuperación · te quedan '+j.recuperacion_restantes+'. Genera nuevos en Mantenimiento → Seguridad.');
    mostrarApp();
  } else if(r.status===429){ err.textContent='Demasiados intentos. Espera unos minutos.'; }
  else if(r.status===401){
    const j = await r.json().catch(()=>({}));
    if(j.detail==='pre_invalido'){ err.textContent='Se venció el tiempo. Vuelve a ingresar tu contraseña.'; setTimeout(volverPaso1, 1500); }
    else err.textContent = enrolando ? 'Ese código no coincide. Revisa la hora del teléfono y vuelve a intentar.' : 'Código incorrecto.';
  } else err.textContent='No se pudo verificar. Intenta de nuevo.';
}
function copiarRec(){ navigator.clipboard && navigator.clipboard.writeText(recCodigos.join('\n')).then(()=>toast('Códigos copiados')); }
function descargarRec(){
  const usr = localStorage.getItem('pichangol_admin_usr')||'';
  const blob = new Blob([`Pichangol · Torre de control · códigos de recuperación de ${usr}\nCada código vale UNA vez. Guárdalos en un lugar seguro.\n\n`+recCodigos.join('\n')+'\n'],{type:'text/plain'});
  const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = 'pichangol-torre-recuperacion.txt'; a.click();
}
['cod','codEnrolar'].forEach(id=>{ document.addEventListener('DOMContentLoaded',()=>{ const el=document.getElementById(id); if(el) el.addEventListener('keydown',e=>{ if(e.key==='Enter') verificar2fa(id==='codEnrolar'); }); }); });
fetch('/admin/api/gate').then(r=>r.ok?r.json():null).then(g=>{ if(g && !g.usuarios){ const a=document.getElementById('altModo'); if(a) a.style.display=''; } }).catch(()=>{});
function salir(){
  localStorage.removeItem('pichangol_admin_tok');
  localStorage.removeItem('pichangol_admin_usr');
  location.reload();
}
// Colapsa / expande la barra lateral y recuerda la preferencia.
function toggleSide(){
  const s = document.getElementById('side');
  s.classList.toggle('collapsed');
  try{ localStorage.setItem('pg_side_collapsed', s.classList.contains('collapsed')?'1':'0'); }catch(e){}
}
function restaurarSide(){
  try{ if(localStorage.getItem('pg_side_collapsed')==='1')
    document.getElementById('side').classList.add('collapsed'); }catch(e){}
}
function mostrarApp(){
  document.getElementById('gate').style.display='none';
  document.getElementById('app').style.display='block';
  // Avatar del operador: inicial del correo con el que se logueó.
  const usr = localStorage.getItem('pichangol_admin_usr') || '';
  const av = document.getElementById('avatarOp');
  if(av){ av.textContent = (usr[0]||'P').toUpperCase(); av.title = usr || 'Operador'; }
  renderTabs();
  renderResumen();
  cargarDisputas();
  cargarModo();
  cargarCanal();
  cargarPichangaModo();
  cargarUbicacion();
  cargarMarketing();
  cargarComision();
  cargarMargenes();
  cargarCircuito();
  cargarRanking();
  cargarPro();
  renderMantenimiento();
  cargarLiquidaciones();
  cargar();
}

// --- Mantenimiento / pruebas: disparar cobros automáticos manualmente ---------
function renderMantenimiento(){
  document.getElementById('mantenimiento').innerHTML =
    `<div class="card"><div class="top"><h3>Mantenimiento (pruebas)</h3></div>
      <div class="row">Dispara AHORA los cobros automáticos que normalmente corren
        cada 12 h. Útil para probar el flujo sin esperar. Cobra a las tarjetas
        guardadas de Culqi.</div>
      <div class="actions" style="flex-wrap:wrap;gap:8px">
        <button class="btn-ap" onclick="cobrarMensualidades()">Cobrar mensualidades vencidas (alumnos)</button>
        <button class="btn-ap" onclick="cobrarServicios()">Cobrar suscripciones de marketing vencidas</button>
      </div>
      <div class="row" style="margin-top:12px;color:var(--muted)">Al limpiar academias/alumnos
        (SQL en Supabase), borra también los débitos automáticos para que no queden cobrando huérfanos:</div>
      <div class="actions" style="flex-wrap:wrap;gap:8px">
        <button class="btn-rc" onclick="borrarSuscripcionesAlumno()">Borrar suscripciones de alumnos (pruebas)</button>
        <button class="btn-rc" onclick="borrarCobrosMatricula()">Borrar cobros de matrícula del reporte (pruebas)</button>
        <button class="btn-rc" onclick="reiniciarPagos()">Reiniciar TODO el libro de pagos (pruebas)</button>
      </div>
      <div class="row" style="margin-top:16px;padding-top:14px;border-top:1px solid var(--border)">
        <b>🧼 Dejar en virgen (servidor)</b><br/>
        Borra TODO lo transaccional del servidor: pagos, saldos de billetera,
        suscripciones (servicios + alumnos), tarjetas guardadas y métricas de
        vistas. <b>CONSERVA las canchas reclamadas</b> (reclamos de propiedad) y la
        config. Los alumnos y reservas viven en Supabase: límpialos desde la app
        (Ajustes → “Dejar en virgen”).
      </div>
      <div class="actions" style="flex-wrap:wrap;gap:8px">
        <button class="btn-rc" style="font-weight:800" onclick="resetVirgen()">🧼 Dejar el servidor en virgen</button>
      </div>
      <div class="row" style="margin-top:16px;padding-top:14px;border-top:1px solid var(--border)">
        <b>🧨 VIRGEN TOTAL (servidor)</b><br/>
        Borra <b>ABSOLUTAMENTE TODO</b> del servidor, <b>incluidos los reclamos de
        propiedad</b> (las canchas dejan de estar reclamadas/verificadas) y la
        config. Úsalo junto con el SQL <code>dejar_virgen_total.sql</code> en
        Supabase y con limpiar los datos de la app en cada teléfono.
      </div>
      <div class="actions" style="flex-wrap:wrap;gap:8px">
        <button class="btn-rc" style="font-weight:800;background:#9A1722;color:#fff;border-color:#9A1722" onclick="resetTotal()">🧨 Borrar TODO (virgen total)</button>
      </div>
      <div class="row" style="margin-top:16px;padding-top:14px;border-top:1px solid var(--border)">
        <b>🧹 Limpiar almacenamiento (archivos huérfanos)</b><br/>
        Borra del Storage los archivos cuyo dueño ya no existe: fotos de canchas
        eliminadas, historias vencidas, fotos de productos borrados, afiches de
        campeonatos, avatares viejos y documentos de identidad sin referencia.
        <b>Nunca toca</b> las constancias de recargas ni el arte compartido.
        Primero revisa qué encontró; recién ahí borra.
      </div>
      <div class="actions" style="flex-wrap:wrap;gap:8px">
        <button class="btn-ap" onclick="revisarStorage()">\U0001F50D Revisar archivos huérfanos</button>
        <button class="btn-rc" onclick="limpiarStorage()">🧹 Borrar huérfanos</button>
      </div>
      <div id="stg_res" class="row" style="margin-top:8px;color:var(--muted)"></div>
      <div id="mant_res" class="row" style="margin-top:10px;color:var(--muted)"></div>
    </div>`;
}
function modalConfirmar(titulo, mensaje, textoOk){
  return new Promise(res=>{
    const ov = document.createElement('div');
    ov.style.cssText = 'position:fixed;inset:0;background:rgba(10,20,15,.45);'+
      'display:flex;align-items:center;justify-content:center;z-index:9999';
    ov.innerHTML = `
      <div style="background:#fff;border-radius:18px;max-width:420px;width:92%;padding:20px 22px;box-shadow:0 18px 50px rgba(0,0,0,.25)">
        <div style="font-weight:800;font-size:16px">${titulo}</div>
        <div style="color:var(--muted);font-size:13px;margin-top:6px;line-height:1.45">${mensaje}</div>
        <div style="display:flex;justify-content:flex-end;gap:8px;margin-top:18px">
          <button id="mc_no" style="padding:9px 16px;border-radius:999px;border:none;background:transparent;font-weight:700;cursor:pointer">Cancelar</button>
          <button id="mc_si" class="btn-rc" style="padding:9px 18px;border-radius:999px;cursor:pointer;font-weight:800">${textoOk}</button>
        </div>
      </div>`;
    ov.querySelector('#mc_no').onclick=()=>{ ov.remove(); res(false); };
    ov.onclick=e=>{ if(e.target===ov){ ov.remove(); res(false); } };
    ov.querySelector('#mc_si').onclick=()=>{ ov.remove(); res(true); };
    document.body.appendChild(ov);
  });
}
function pintarStorage(j){
  const el = document.getElementById('stg_res');
  if(!j || !j.ok){ el.textContent = 'No se pudo revisar: ' + ((j&&j.error)||'error'); return; }
  const rx = j.radiografia||{};
  // Los diagnósticos se muestran SIEMPRE con su valor: si sólo se avisara
  // cuando fallan, un dato que no se pudo leer se vería igual que "todo bien".
  const bd = rx.proyecto_bd || '(no reconocido)';
  const stg = rx.proyecto_storage || '(no reconocido)';
  const mismo = rx.proyecto_bd && rx.proyecto_storage && rx.proyecto_bd === rx.proyecto_storage;
  const veTodo = rx.ve_todo === true ? 'sí' : (rx.ve_todo === false ? 'NO' : '(no se pudo leer)');
  let cabecera = `<div style="margin-bottom:6px">Base de datos: <code>${bd}</code> · ` +
    `Storage: <code>${stg}</code> ` +
    (mismo ? '✓ mismo proyecto'
           : '<b style="color:#9A1722">⚠️ NO es el mismo proyecto: se comparan archivos de uno contra filas de otro</b>') +
    `<br/>Usuario BD: <code>${rx.usuario_bd||'?'}</code> · ve todas las filas: ` +
    (rx.ve_todo === true ? '<b>sí</b>'
      : `<b style="color:#9A1722">${veTodo}</b> (si no las ve todas, un 0 no significa "limpio")`) +
    `<br/>Barrido automático: ` +
    (rx.barrido_auto
      ? `<b style="color:#1F6E49">activado</b> (cada ${rx.barrido_horas||24} h)`
      : `<b>apagado</b> — sólo se limpia cuando pulsas el botón`) +
    `</div>`;
  // OJO: aquí va `+=`, no `=`. Con asignación estas ramas BORRABAN el
  // diagnóstico de arriba, que es justamente el dato que hacía falta para
  // interpretar el conteo (y por eso nunca llegó a verse en pantalla).
  if(rx.objetos_vistos === -1){
    cabecera += `<b style="color:#9A1722">⚠️ No se puede leer storage.objects</b>` +
      `<br/>${rx.error_storage||''}<br/>Sin esto el barrido no ve nada (0 no significa "limpio").<br/>`;
  } else if(rx.objetos_vistos === 0){
    // Cero archivos NO siempre es un problema: en un ambiente recién montado
    // el Storage está legítimamente vacío. Sólo se alarma cuando además hay
    // algo mal cableado; si el proyecto coincide y el usuario ve todas las
    // filas, el dato es simplemente "todavía no hay nada". Una alarma roja en
    // un caso normal enseña al operador a ignorar las alarmas.
    cabecera += (mismo && rx.ve_todo === true)
      ? `El Storage está vacío: no hay ningún archivo todavía.<br/>`
      : `<b style="color:#9A1722">⚠️ El barrido no ve ningún archivo</b>` +
        `<br/>Revisa que DATABASE_URL apunte al mismo proyecto que el Storage.<br/>`;
  } else if(rx.objetos_vistos !== undefined){
    const porB = rx.objetos_por_bucket||{};
    const det = Object.keys(porB).map(b=>`${b}: ${porB[b]}`).join(' · ');
    cabecera += `Archivos vistos: <b>${rx.objetos_vistos}</b> (${det})<br/>`;
  }
  const fam = j.familias||{};
  const lineas = Object.keys(fam).map(k=>{
    const f = fam[k];
    if(f.error) return `• ${k}: no se pudo leer (${f.error})`;
    if(f.omitida) return `• ${k}: <span style="color:#946200">omitida</span> — ${f.omitida}`;
    return `• ${k}: ${f.n}` + (f.n && f.ejemplos&&f.ejemplos.length ? ` (ej. ${f.ejemplos[0]})` : '');
  });
  let desc = '';
  if((rx.desconocidos||[]).length){
    desc = `<br/><br/><b>No reconocidos (NO se borran):</b> ${rx.desconocidos.length}` +
      `<br/>${rx.desconocidos.slice(0,5).map(x=>'· '+x).join('<br/>')}` +
      `<br/><i>Archivos que no corresponden a ninguna cancha ni a una carpeta conocida del sistema. Se listan para que los revises a mano.</i>`;
  }
  el.innerHTML = cabecera + `<b>Huérfanos detectados: ${j.total||0}</b><br/>` + lineas.join('<br/>') + desc;
}
async function revisarStorage(){
  const el = document.getElementById('stg_res');
  el.textContent = 'Revisando…';
  try{
    const r = await fetch('/admin/api/storage/huerfanos',{headers:headers(),cache:'no-store'});
    if(r.status===401){ salir(); return; }
    pintarStorage(await r.json());
  }catch(e){ el.textContent='No se pudo revisar.'; }
}
async function limpiarStorage(){
  const ok = await modalConfirmar('¿Borrar los archivos huérfanos?',
    'Se eliminan del Storage los archivos cuyo dueño ya no existe. Las constancias de recargas y el arte compartido quedan intactos. Esto no se puede deshacer.',
    'Sí, borrar');
  if(!ok) return;
  const el = document.getElementById('stg_res');
  el.textContent = 'Borrando… (puede tomar un minuto)';
  try{
    const r = await fetch('/admin/api/storage/limpiar',{method:'POST',headers:headers()});
    if(r.status===401){ salir(); return; }
    const j = await r.json();
    if(!j.ok){ el.textContent = 'No se pudo: ' + (j.error||'error'); return; }
    el.innerHTML = `<b>Listo:</b> ${j.borrados||0} archivos borrados` +
      (j.fallidos ? `, ${j.fallidos} fallaron (¿falta la policy de DELETE del bucket?)` : '') +
      (j.pendientes ? `, ${j.pendientes} quedaron para la próxima corrida` : '') + '.';
    toast('Almacenamiento limpio');
  }catch(e){ el.textContent='No se pudo borrar.'; }
}
async function resetTotal(){
  if(!confirm('⚠️ VIRGEN TOTAL\\n\\nBorra ABSOLUTAMENTE TODO del servidor, INCLUIDOS los reclamos de propiedad (las canchas dejan de estar reclamadas) y la config. Esto NO se puede deshacer.')) return;
  if(!confirm('Última confirmación: se borrará TODO el estado del servidor. ¿Continuar?')) return;
  try{
    const r = await fetch('/admin/api/reset-total',{method:'POST',headers:headers()});
    if(r.status===401){ salir(); return; }
    const j = await r.json();
    const b = j.borrado||{};
    document.getElementById('mant_res').textContent =
      `Servidor VIRGEN TOTAL. Borrado: ${b.reclamos||0} reclamos, ${b.canchas||0} canchas, `+
      `${b.pagos||0} pagos, ${b.saldos||0} saldos. Ahora corre el SQL en Supabase y limpia la app.`;
    toast('Servidor en virgen TOTAL');
    cargar();
  }catch(e){ document.getElementById('mant_res').textContent='No se pudo.'; }
}
async function resetVirgen(){
  if(!confirm('¿DEJAR EL SERVIDOR EN VIRGEN?\\n\\nBorra pagos, saldos, suscripciones, tarjetas guardadas y vistas. CONSERVA las canchas reclamadas y la config. Esto NO se puede deshacer.')) return;
  if(!confirm('Confirma otra vez: se pondrán TODOS los saldos en 0 y se borrará todo el historial de transacciones.')) return;
  try{
    const r = await fetch('/admin/api/reset-virgen',{method:'POST',headers:headers()});
    if(r.status===401){ salir(); return; }
    const j = await r.json();
    const b = j.borrado||{};
    document.getElementById('mant_res').textContent =
      `Servidor en virgen. Borrado: ${b.pagos||0} pagos, ${b.saldos||0} saldos, `+
      `${(b.suscripciones||0)+(b.suscripciones_alumno||0)} suscripciones, `+
      `${b.metodos_pago||0} tarjetas, ${b.vistas||0} vistas. Reclamos conservados.`;
    toast('Servidor en virgen');
    cargarMargenes();
  }catch(e){ document.getElementById('mant_res').textContent='No se pudo.'; }
}
async function borrarCobrosMatricula(){
  if(!confirm('¿Borrar los cobros de matrícula del reporte? (pruebas). No toca saldos ni liquidaciones.')) return;
  try{
    const r = await fetch('/admin/api/borrar-cobros-matricula',{method:'POST',headers:headers()});
    if(r.status===401){ salir(); return; }
    const j = await r.json();
    document.getElementById('mant_res').textContent = `Cobros de matrícula borrados: ${j.borrados||0}.`;
    toast('Cobros de matrícula borrados');
  }catch(e){ document.getElementById('mant_res').textContent='No se pudo.'; }
}
async function reiniciarPagos(){
  if(!confirm('¿Reiniciar TODO el libro de pagos? (pruebas). Borra matrículas, reservas, recargas, servicios y liquidaciones del reporte. No toca saldos.')) return;
  try{
    const r = await fetch('/admin/api/reiniciar-pagos',{method:'POST',headers:headers()});
    if(r.status===401){ salir(); return; }
    const j = await r.json();
    document.getElementById('mant_res').textContent = `Libro de pagos reiniciado: ${j.borrados||0} registros.`;
    toast('Libro de pagos reiniciado');
    cargarMargenes();
  }catch(e){ document.getElementById('mant_res').textContent='No se pudo.'; }
}
async function borrarSuscripcionesAlumno(){
  if(!confirm('¿Borrar TODAS las suscripciones mes a mes de alumnos? (pruebas)')) return;
  try{
    const r = await fetch('/admin/api/borrar-suscripciones-alumno',{method:'POST',headers:headers()});
    if(r.status===401){ salir(); return; }
    const j = await r.json();
    document.getElementById('mant_res').textContent = `Suscripciones de alumnos borradas: ${j.borradas||0}.`;
    toast('Suscripciones de alumnos borradas');
  }catch(e){ document.getElementById('mant_res').textContent='No se pudo.'; }
}
async function cobrarMensualidades(){
  document.getElementById('mant_res').textContent='Cobrando mensualidades…';
  try{
    const r = await fetch('/pagos/matricula/cobrar-vencidas',{method:'POST',headers:headers()});
    if(r.status===401){ salir(); return; }
    const j = await r.json();
    document.getElementById('mant_res').textContent =
      `Mensualidades: ${j.cobradas||0} cobradas, ${j.pendientes||0} pendientes.`;
    toast('Mensualidades procesadas');
  }catch(e){ document.getElementById('mant_res').textContent='No se pudo (revisa Culqi/red).'; }
}
async function cobrarServicios(){
  document.getElementById('mant_res').textContent='Cobrando suscripciones de marketing…';
  try{
    const r = await fetch('/pagos/servicios/cobrar-vencidas',{method:'POST',headers:headers()});
    if(r.status===401){ salir(); return; }
    const j = await r.json();
    document.getElementById('mant_res').textContent =
      `Marketing: ${j.cobradas||0} del saldo, ${j.por_tarjeta||0} por tarjeta, ${j.pendientes||0} pendientes.`;
    toast('Suscripciones procesadas');
  }catch(e){ document.getElementById('mant_res').textContent='No se pudo (revisa Culqi/red).'; }
}

// --- Servicios de marketing: precios + tope de posts IA --------------------
let mkt = {landing_soles:0, redes_soles:0, presencia_soles:0, posts_limite_mes:0};
async function cargarMarketing(){
  try{
    const r = await fetch('/admin/api/marketing',{headers:headers()});
    if(!r.ok) return;
    mkt = await r.json();
    renderMarketing();
  }catch(e){}
}
function renderMarketing(){
  const campo = (id,lbl,val,suf,desc)=>`
    <div style="margin-top:12px">
      <div style="display:flex;align-items:center;gap:8px">
        <span style="flex:1;font-weight:700;font-size:13.5px">${lbl}</span>
        <input id="${id}" value="${val}" inputmode="numeric" style="width:96px;padding:9px 10px;
          border:1px solid var(--border);border-radius:10px;font-family:inherit;font-size:14px;text-align:right">
        <span style="color:var(--muted);font-size:13px;min-width:44px">${suf}</span>
      </div>
      ${desc?`<div style="color:var(--muted);font-size:12px;margin-top:2px">${desc}</div>`:''}
    </div>`;
  const sub = t=>`<div style="font-weight:800;font-size:11.5px;text-transform:uppercase;
    letter-spacing:.06em;color:var(--green-deep);margin:18px 0 2px">${t}</div>`;
  document.getElementById('marketing').innerHTML =
    `<div class="card"><div class="top"><h3>Servicios de marketing</h3></div>
      <div class="row">Precios MENSUALES; se cobran del saldo del dueño. La academia
        contrata UNO de estos servicios.</div>
      ${sub('Precios para academias')}
      ${campo('mkt_landing','Landing web', mkt.landing_soles, 'S/ /mes',
        'Página web propia de la academia.')}
      ${campo('mkt_redes','Manejo de redes', mkt.redes_soles, 'S/ /mes',
        'Contenido con IA + publicación en sus redes.')}
      ${campo('mkt_presencia','Presencia digital', mkt.presencia_soles, 'S/ /mes',
        '📦 PAQUETE: incluye Landing web + Manejo de redes (todo junto, no se paga por separado).')}
      ${sub('Límite de uso')}
      ${campo('mkt_limite','Tope de posts con IA', mkt.posts_limite_mes, '/mes',
        'Máx. de posts que la IA genera por academia al mes (control de costo). La landing no cuenta.')}
      ${sub('Precios para clubes / canchas (opcional)')}
      <div class="row" style="color:var(--muted);font-size:12px;margin-top:2px">Déjalos en 0
        para cobrar lo MISMO que a las academias. El negocio unificado (academia + canchas)
        siempre usa el precio de academia.</div>
      ${campo('mkt_landing_club','Landing web', mkt.landing_soles_club||0, 'S/ /mes')}
      ${campo('mkt_redes_club','Manejo de redes', mkt.redes_soles_club||0, 'S/ /mes')}
      ${campo('mkt_presencia_club','Presencia digital', mkt.presencia_soles_club||0, 'S/ /mes')}
      <div class="actions"><button class="btn-ap" onclick="guardarMarketing()">Guardar</button></div>
    </div>`;
}
async function guardarMarketing(){
  const n = id => parseInt((document.getElementById(id).value||'0').replace(/[^0-9]/g,''))||0;
  const r = await fetch('/admin/api/marketing',{method:'POST',headers:headers(),
    body:JSON.stringify({landing_soles:n('mkt_landing'),redes_soles:n('mkt_redes'),
      presencia_soles:n('mkt_presencia'),posts_limite_mes:n('mkt_limite'),
      landing_soles_club:n('mkt_landing_club'),redes_soles_club:n('mkt_redes_club'),
      presencia_soles_club:n('mkt_presencia_club')})});
  if(r.status===401){ salir(); return; }
  if(r.ok){ mkt = await r.json(); renderMarketing(); toast('Servicios de marketing actualizados'); }
  else toast('No se pudo guardar');
}

// --- Comisión por cobro digital de matrícula (por país) --------------------
let com = {pe:0, ec:0, bo:0};
async function cargarComision(){
  try{
    const r = await fetch('/admin/api/comision',{headers:headers()});
    if(!r.ok) return;
    com = await r.json();
    renderComision();
  }catch(e){}
}
function renderComision(){
  const campo = (id,bandera,lbl,val)=>`
    <div style="display:flex;align-items:center;gap:8px;margin-top:8px">
      <span style="flex:1;font-weight:600;font-size:13px">${bandera} ${lbl}</span>
      <input id="${id}" value="${val}" inputmode="decimal" style="width:80px;padding:9px 10px;
        border:1px solid var(--border);border-radius:10px;font-family:inherit;font-size:14px;text-align:right">
      <span style="color:var(--muted);font-size:13px;min-width:16px">%</span>
    </div>`;
  document.getElementById('comision').innerHTML =
    `<div class="card"><div class="top"><h3>Comisión por cobro digital</h3></div>
      <div class="row">Tarifa "tipo POS" que la academia absorbe cuando el alumno
        paga la matrícula por la app (el alumno paga el precio limpio). El pago en
        efectivo es 0%. Ajusta el % por país.</div>
      ${campo('com_pe','🇵🇪','Perú', com.pe)}
      ${campo('com_ec','🇪🇨','Ecuador', com.ec)}
      ${campo('com_bo','🇧🇴','Bolivia', com.bo)}
      <div class="actions"><button class="btn-ap" onclick="guardarComision()">Guardar</button></div>
    </div>`;
}
async function guardarComision(){
  const f = id => parseFloat((document.getElementById(id).value||'0').replace(',','.'))||0;
  const r = await fetch('/admin/api/comision',{method:'POST',headers:headers(),
    body:JSON.stringify({pe:f('com_pe'),ec:f('com_ec'),bo:f('com_bo')})});
  if(r.status===401){ salir(); return; }
  if(r.ok){ com = await r.json(); renderComision(); toast('Comisión actualizada'); }
  else toast('No se pudo guardar');
}

// --- Márgenes Pichangol: desglose de la comisión (banco vs PCG) -------------
async function cargarMargenes(){
  const r = await fetch('/admin/api/margenes',{headers:headers()});
  if(!r.ok) return;
  renderMargenes(await r.json());
}
function renderMargenes(m){
  const s = v => 'S/ ' + (Number(v)||0).toFixed(2);
  const fila = (t,v,extra='') => `<div class="row" style="display:flex;justify-content:space-between;${extra}"><span>${t}</span><span>${v}</span></div>`;
  document.getElementById('margenes').innerHTML =
    `<div class="card"><div class="top"><h3>Márgenes Pichangol (comisiones)</h3></div>
      <div class="row">Tus INGRESOS (comisiones de matrículas y reservas + servicios)
        menos el COSTO real del banco/pasarela (Culqi) sobre todo lo cobrado por
        tarjeta (matrículas + recargas de saldo + servicios). Ajusta la tasa del
        banco con tu tarifa real.</div>
      ${fila('Comisión de matrículas · '+m.cobros_matricula, '<b>'+s(m.comision_matricula_soles)+'</b>')}
      ${fila('Comisión de reservas · '+m.cobros_reserva, '<b>'+s(m.comision_reserva_soles)+'</b>')}
      ${fila('Ingresos por servicios · '+(m.cobros_servicios||0), '<b>'+s(m.ingresos_servicios_soles)+'</b>')}
      ${fila('= Ingresos Pichangol (total)', '<b>'+s(m.ingresos_pcg_soles)+'</b>', 'color:#14463A')}
      <hr style="border:none;border-top:1px solid var(--border);margin:8px 0">
      ${fila('Bruto procesado por tarjeta (matrículas + recargas + servicios)', s(m.bruto_procesado_soles), 'color:var(--muted)')}
      <div style="display:flex;align-items:center;gap:8px;margin:8px 0">
        <span style="flex:1;font-weight:600;font-size:13px">− Costo pasarela/banco (Culqi)</span>
        <input id="banco_pct" value="${m.banco_pct}" inputmode="decimal" style="width:80px;padding:9px 10px;
          border:1px solid var(--border);border-radius:10px;font-family:inherit;font-size:14px;text-align:right">
        <span style="color:var(--muted);font-size:13px;min-width:16px">%</span>
      </div>
      ${fila('Costo banco estimado', '− '+s(m.costo_banco_soles), 'color:var(--muted)')}
      <hr style="border:none;border-top:1px solid var(--border);margin:8px 0">
      ${fila('Margen neto Pichangol', s(m.margen_pcg_soles), 'font-weight:800;color:#14463A')}
      <div class="actions"><button class="btn-ap" onclick="guardarBanco()">Guardar tasa banco</button></div>
    </div>
    <div class="card"><div class="top"><h3>Comisión cobrada del saldo (billetera)</h3></div>
      <div class="row">Cuando el dueño tiene saldo, la comisión de la reserva se
        descuenta de su billetera y él recibe el pago completo. Aquí defines la
        tarifa de ESE camino — puede ser menor que la estándar
        (${Number(m.comision_std_pct)}% mín S/ ${Number(m.comision_std_min_soles).toFixed(2)})
        como premio por mantener saldo. Vacío = usa la estándar.</div>
      <div style="display:flex;align-items:center;gap:8px;margin:10px 0;flex-wrap:wrap">
        <span style="font-weight:600;font-size:13px">Comisión</span>
        <input id="saldo_pct" value="${m.comision_saldo_pct ?? ''}" placeholder="${m.comision_std_pct}"
          inputmode="decimal" style="width:74px;padding:9px 10px;border:1px solid var(--border);
          border-radius:10px;font-family:inherit;font-size:14px;text-align:right">
        <span style="color:var(--muted);font-size:13px">%</span>
        <span style="font-weight:600;font-size:13px;margin-left:10px">mínimo S/</span>
        <input id="saldo_min" value="${m.comision_saldo_min_soles ?? ''}" placeholder="${m.comision_std_min_soles}"
          inputmode="decimal" style="width:74px;padding:9px 10px;border:1px solid var(--border);
          border-radius:10px;font-family:inherit;font-size:14px;text-align:right">
      </div>
      <div class="row" style="color:var(--muted)">Vigente:
        <b>${m.comision_saldo_pct==null
          ? 'estándar ('+Number(m.comision_std_pct)+'% mín S/ '+Number(m.comision_std_min_soles).toFixed(2)+')'
          : Number(m.comision_saldo_pct)+'% mín S/ '+Number(m.comision_saldo_min_soles||0).toFixed(2)}</b>
        · aplica a comisiones que salen del saldo (reserva online con saldo y
        reserva en efectivo). Sin saldo, sigue la estándar sobre la transacción.</div>
      <div class="actions">
        <button class="btn-ap" onclick="guardarComisionSaldo(false)">Guardar</button>
        <button class="btn-sec" onclick="guardarComisionSaldo(true)">Usar estándar</button>
      </div>
    </div>`;
}
async function guardarComisionSaldo(reset){
  const pctRaw = (document.getElementById('saldo_pct').value||'').replace(',','.').trim();
  const minRaw = (document.getElementById('saldo_min').value||'').replace(',','.').trim();
  const body = reset || pctRaw===''
    ? {reset:true}
    : {pct: parseFloat(pctRaw)||0, min_soles: parseFloat(minRaw)||0};
  const r = await fetch('/admin/api/margenes/comision-saldo',{method:'POST',
    headers:headers(), body:JSON.stringify(body)});
  if(r.status===401){ salir(); return; }
  if(r.ok){ renderMargenes(await r.json());
    toast(reset||pctRaw==='' ? 'Comisión de saldo: estándar' : 'Comisión de saldo actualizada'); }
  else toast('No se pudo guardar');
}
async function guardarBanco(){
  const pct = parseFloat((document.getElementById('banco_pct').value||'0').replace(',','.'))||0;
  const r = await fetch('/admin/api/margenes/banco',{method:'POST',headers:headers(),
    body:JSON.stringify({pct})});
  if(r.status===401){ salir(); return; }
  if(r.ok){ renderMargenes(await r.json()); toast('Tasa del banco actualizada'); }
  else toast('No se pudo guardar');
}

// --- Ingresos del CIRCUITO (Pro + torneos) ----------------------------------
async function cargarCircuito(){
  try{
    const r = await fetch('/admin/api/circuito',{headers:headers()});
    if(r.status===401){ salir(); return; }
    const j = await r.json();
    const s = v => 'S/ ' + (Number(v)||0).toFixed(2);
    const fila = (t,v,extra='') => `<div class="row" style="display:flex;justify-content:space-between;${extra}"><span>${t}</span><span>${v}</span></div>`;
    const dir = j.directorio || {total:0, por_deporte:{}};
    const ret = j.retos || {total:0, pendientes:0, aceptados:0, jugados:0};
    const porDep = Object.entries(dir.por_deporte||{})
      .map(([d,n])=>`${esc(d)} ${n}`).join(' · ') || '—';
    const lideres = (j.lideres_retos||[]).map((l,i)=>{
      const m = ['🥇','🥈','🥉'][i] || (i+1);
      return `<tr><td style="padding:4px 6px">${m}</td>`+
             `<td style="padding:4px 6px">${esc(l.nombre||l.email)}</td>`+
             `<td style="padding:4px 6px;text-align:right">${l.ganados}G / ${l.jugados}J</td></tr>`;
    }).join('') || '<tr><td colspan="3" style="color:var(--muted);padding:6px">Aún sin retos jugados.</td></tr>';
    const mini = (n,t) => `<div><div style="font-size:20px;font-weight:800;color:#14463A">${n}</div><div class="row">${t}</div></div>`;
    document.getElementById('circuitoPanel').innerHTML =
      `<div class="card"><div class="top"><h3>🏆 Ingresos del circuito</h3></div>
        <div class="row">Lo que genera la capa de comunidad: membresías Pro (todo el
          monto es ingreso Pichangol) + comisión de inscripciones a torneos.</div>
        ${fila('Membresías Pro · '+(j.pro.cobros||0), '<b>'+s(j.pro.total_soles)+'</b>')}
        ${fila('Comisión de torneos · '+(j.torneos.inscripciones||0), '<b>'+s(j.torneos.comision_soles)+'</b>', 'color:var(--muted)')}
        ${fila('(volumen bruto de torneos)', s(j.torneos.bruto_soles), 'color:var(--muted);font-size:12px')}
        <hr style="border:none;border-top:1px solid var(--border);margin:8px 0">
        ${fila('= Ingreso del circuito', '<b>'+s(j.ingreso_circuito_soles)+'</b>', 'font-weight:800;color:#14463A')}
      </div>
      <div class="card"><div class="top"><h3>⚡ Salud del circuito</h3></div>
        <div class="row">Actividad de la comunidad (retos + jugadores disponibles).
          Pro es ilimitado; el tope gratis es editable:</div>
        <div class="actions" style="align-items:center;gap:8px;margin-top:6px">
          <span style="font-size:12px;font-weight:600">Retos gratis / semana</span>
          <input id="limiteRetos" value="${j.limite_retos_free||3}" inputmode="numeric"
            style="width:60px;padding:8px;border:1px solid var(--border);border-radius:8px;text-align:right">
          <button class="btn-ap" onclick="guardarLimiteRetos()">✓</button>
        </div>
        <div style="display:flex;gap:20px;margin:12px 0 4px;flex-wrap:wrap">
          ${mini(dir.total, 'Disponibles')}
          ${mini(ret.total, 'Retos')}
          ${mini(ret.pendientes, 'Pendientes')}
          ${mini(ret.aceptados, 'Aceptados')}
          ${mini(ret.jugados, 'Jugados')}
        </div>
        ${fila('Jugadores por deporte', porDep, 'color:var(--muted);font-size:12px')}
        <div class="row" style="margin-top:10px;font-weight:700">Líderes por retos</div>
        <table style="width:100%;border-collapse:collapse;font-size:13px">
          <tbody>${lideres}</tbody>
        </table>
      </div>`;
  }catch(e){ document.getElementById('circuitoPanel').innerHTML =
      '<div class="card">No se pudo cargar el circuito.</div>'; }
}
async function guardarLimiteRetos(){
  const v = parseInt(document.getElementById('limiteRetos').value||'3',10);
  if(!(v>=1)){ toast('Mínimo 1'); return; }
  const r = await fetch('/admin/api/circuito/limite-retos',{method:'POST',headers:headers(),
    body:JSON.stringify({limite:v})});
  if(r.status===401){ salir(); return; }
  if(r.ok){ await cargarCircuito(); toast('Límite de retos actualizado'); }
  else toast('No se pudo guardar');
}

// --- Ranking global cruzado (snapshot que empuja el APK) --------------------
async function cargarRanking(){
  try{
    const r = await fetch('/admin/api/ranking',{headers:headers()});
    if(r.status===401){ salir(); return; }
    const j = await r.json();
    const deportes = j.deportes || [];
    let fresco = '—';
    try{ if(j.actualizado) fresco = new Date(j.actualizado).toLocaleString(); }catch(e){}
    let cuerpo;
    if(!deportes.length){
      cuerpo = `<div class="row" style="color:var(--muted)">Aún no llega el ranking.
        Se llena cuando alguien abre el Ranking Global en el app.</div>`;
    } else {
      cuerpo = deportes.map(d=>{
        const camp = d.campeon
          ? `<div class="row" style="color:#14463A">👑 Campeón ${esc(d.temporada||'')}: <b>${esc(d.campeon.nombre)}</b> · ${d.campeon.puntos} pts</div>`
          : '';
        const filas = (d.top||[]).map((p,i)=>{
          const m = ['🥇','🥈','🥉'][i] || (i+1);
          const pro = p.pro ? ' <span style="background:#14463A;color:#fff;border-radius:4px;padding:0 4px;font-size:9px;font-weight:800">PRO</span>' : '';
          return `<tr><td style="padding:3px 6px">${m}</td>`+
                 `<td style="padding:3px 6px">${esc(p.nombre)}${pro}</td>`+
                 `<td style="padding:3px 6px;color:var(--muted);font-size:12px">${esc(p.academia||'')}</td>`+
                 `<td style="padding:3px 6px;text-align:right"><b>${p.puntos}</b> · ${p.pg||0}G-${p.pp||0}P</td></tr>`;
        }).join('');
        return `<div style="margin-top:12px">
          <div style="font-weight:800;color:#14463A">${esc((d.deporte||'').toUpperCase())}</div>
          ${camp}
          <table style="width:100%;border-collapse:collapse;font-size:13px"><tbody>${filas}</tbody></table>
        </div>`;
      }).join('');
    }
    document.getElementById('rankingPanel').innerHTML =
      `<div class="card"><div class="top"><h3>📊 Ranking global (vista del app)</h3></div>
        <div class="row">El ranking cruzado se calcula en el app (las academias viven
          en Supabase). Esta es la última foto que envió un dispositivo.</div>
        ${cuerpo}
        <div class="row" style="margin-top:10px;color:var(--muted);font-size:12px">Actualizado: ${fresco}</div>
      </div>`;
  }catch(e){ document.getElementById('rankingPanel').innerHTML =
      '<div class="card">No se pudo cargar el ranking.</div>'; }
}

// --- Pichangol Pro (membresía del jugador): precios por país + miembros + MRR -
async function cargarPro(){
  try{
    const r = await fetch('/admin/api/pro',{headers:headers()});
    if(r.status===401){ salir(); return; }
    const j = await r.json();
    const pr = j.precios || {pe:j.precio_soles, ec:0, bo:0};
    // Cada país cobra en SU moneda (no todo es soles).
    const SYM = {pe:'S/', ec:'$', bo:'Bs'};
    const mrrP = j.mrr_por_pais || {pe:j.mrr_soles||0, ec:0, bo:0};
    const actP = j.activos_por_pais || {pe:0, ec:0, bo:0};
    const filas = (j.miembros||[]).map(m=>{
      const est = m.activa
        ? '<span style="color:#176B3A;font-weight:800">Activa</span>'
        : '<span style="color:#B23A3A">Vencida</span>';
      const tipo = m.cortesia
        ? '<span style="background:#FFF3D6;color:#8A6100;font-weight:800;font-size:11px;padding:2px 8px;border-radius:999px">🎁 cortesía</span>'
        : '<span style="color:var(--muted);font-size:12px">pagada</span>';
      let hasta = '—';
      try{ if(m.hasta) hasta = new Date(m.hasta).toLocaleDateString(); }catch(e){}
      const acc = m.cortesia && m.activa
        ? `<button class="btn-rc" style="padding:3px 10px;font-size:11.5px" onclick="revocarCortesia('${esc(m.email)}')">Revocar</button>`
        : '';
      return `<tr><td style="padding:4px 6px">${esc(m.email)}</td>`+
             `<td style="padding:4px 6px">${esc(m.pais||'PE')}</td>`+
             `<td style="padding:4px 6px">${tipo}</td>`+
             `<td style="padding:4px 6px">${est}</td>`+
             `<td style="padding:4px 6px">${hasta}</td>`+
             `<td style="padding:4px 6px">${acc}</td></tr>`;
    }).join('') || '<tr><td colspan="6" style="color:var(--muted);padding:6px">Sin miembros aún.</td></tr>';
    const precioInput = (iso,label) =>
      `<div style="display:flex;align-items:center;gap:6px">
         <span style="font-size:12px;font-weight:600">${label} ${SYM[iso]||''}</span>
         <input id="proPrecio_${iso}" value="${pr[iso]}" inputmode="decimal"
           style="width:66px;padding:8px;border:1px solid var(--border);border-radius:8px;text-align:right">
         <button class="btn-ap" onclick="guardarProPrecio('${iso}')">✓</button>
       </div>`;
    document.getElementById('proPanel').innerHTML =
      `<div class="card"><div class="top"><h3>⭐ Pichangol Pro (jugadores)</h3></div>
        <div class="row">Membresía mensual del jugador. Se cobra de su billetera única
          (saldo) y se renueva sola cada 12 h. Precio por país:</div>
        <div class="actions" style="align-items:center;gap:12px;flex-wrap:wrap;margin-top:8px">
          ${precioInput('pe','🇵🇪 Perú')}
          ${precioInput('ec','🇪🇨 Ecuador')}
          ${precioInput('bo','🇧🇴 Bolivia')}
          <button class="btn-ap" onclick="renovarPro()">Renovar vencidas</button>
        </div>
        <div style="display:flex;gap:22px;margin:14px 0 6px">
          <div><div style="font-size:22px;font-weight:800;color:#14463A">${j.activos}</div><div class="row">Activos</div></div>
          <div><div style="font-size:22px;font-weight:800;color:#14463A">${j.total}</div><div class="row">Total</div></div>
        </div>
        <div class="row" style="font-weight:700;margin-top:4px">MRR estimado (cada país en su moneda)</div>
        <div style="display:flex;gap:18px;margin:4px 0 6px;flex-wrap:wrap">
          <div><div style="font-size:18px;font-weight:800;color:#14463A">S/ ${(Number(mrrP.pe)||0).toFixed(2)}</div><div class="row">🇵🇪 Perú · ${actP.pe||0}</div></div>
          <div><div style="font-size:18px;font-weight:800;color:#14463A">$ ${(Number(mrrP.ec)||0).toFixed(2)}</div><div class="row">🇪🇨 Ecuador · ${actP.ec||0}</div></div>
          <div><div style="font-size:18px;font-weight:800;color:#14463A">Bs ${(Number(mrrP.bo)||0).toFixed(2)}</div><div class="row">🇧🇴 Bolivia · ${actP.bo||0}</div></div>
        </div>
        <div style="border:1px dashed var(--border);border-radius:12px;padding:12px;margin:12px 0">
          <div style="font-weight:800;margin-bottom:2px">🎁 Regalos manuales (marcha blanca)</div>
          <div class="row">Regala Pro y/o SALDO a las canchas aliadas del lanzamiento, sin cobrarles.
            La cortesía NUNCA se renueva sola del saldo del dueño (al vencer, expira) y el
            saldo de regalo SOLO cubre comisiones (no se liquida ni transfiere).</div>
          <div class="actions" style="align-items:center;gap:8px;flex-wrap:wrap;margin-top:8px">
            <input id="cortesiaEmail" placeholder="correo del dueño"
              style="flex:1;min-width:210px;padding:8px;border:1px solid var(--border);border-radius:8px">
            <select id="cortesiaDias" style="padding:8px;border:1px solid var(--border);border-radius:8px">
              <option value="30">30 días</option>
              <option value="60">60 días</option>
              <option value="90" selected>90 días</option>
              <option value="180">180 días</option>
            </select>
            <button class="btn-ap" onclick="darCortesia()">Dar Pro de cortesía</button>
          </div>
          <div class="actions" style="align-items:center;gap:8px;flex-wrap:wrap;margin-top:8px">
            <span style="font-size:12.5px;font-weight:600">Saldo de regalo S/</span>
            <input id="regaloSaldo" inputmode="decimal" placeholder="200"
              style="width:80px;padding:8px;border:1px solid var(--border);border-radius:8px;text-align:right">
            <button class="btn-ap" onclick="darRegaloSaldo()">Regalar saldo 🎁</button>
            <span class="row" style="margin:0">al mismo correo de arriba</span>
          </div>
        </div>
        <div style="border:1px dashed var(--border);border-radius:12px;padding:12px;margin:12px 0">
          <div style="font-weight:800;margin-bottom:2px">🚀 Bienvenida AUTOMÁTICA de nuevos dueños</div>
          <div class="row">Cada dueño nuevo, al ACTIVARSE su primera cancha, recibe esto solo
            (un regalo por correo). El saldo de regalo SOLO cubre comisiones (no se liquida
            ni se gasta en otra cosa) y va en la MONEDA del país de la cancha. Pon todo en 0
            para apagarla.</div>
          <div class="actions" style="align-items:center;gap:10px;flex-wrap:wrap;margin-top:8px">
            <span style="font-size:12.5px;font-weight:600">Pro de cortesía</span>
            <select id="bvDias" style="padding:8px;border:1px solid var(--border);border-radius:8px">
              <option value="0">sin Pro</option>
              <option value="30">30 días</option>
              <option value="60">60 días</option>
              <option value="90">90 días</option>
              <option value="180">180 días</option>
            </select>
            <span style="font-size:12.5px;font-weight:600">Regalo 🇵🇪 S/</span>
            <input id="bvSaldo" inputmode="decimal"
              style="width:64px;padding:8px;border:1px solid var(--border);border-radius:8px;text-align:right">
            <span style="font-size:12.5px;font-weight:600">🇪🇨 $</span>
            <input id="bvSaldoUsd" inputmode="decimal"
              style="width:64px;padding:8px;border:1px solid var(--border);border-radius:8px;text-align:right">
            <span style="font-size:12.5px;font-weight:600">🇧🇴 Bs</span>
            <input id="bvSaldoBob" inputmode="decimal"
              style="width:64px;padding:8px;border:1px solid var(--border);border-radius:8px;text-align:right">
            <button class="btn-ap" onclick="guardarBienvenida()">Guardar</button>
          </div>
        </div>
        <table style="width:100%;border-collapse:collapse;font-size:13px">
          <thead><tr style="border-bottom:1px solid var(--border)">
            <th style="text-align:left;padding:4px 6px">Jugador</th>
            <th style="text-align:left;padding:4px 6px">País</th>
            <th style="text-align:left;padding:4px 6px">Tipo</th>
            <th style="text-align:left;padding:4px 6px">Estado</th>
            <th style="text-align:left;padding:4px 6px">Vigente hasta</th>
            <th style="text-align:left;padding:4px 6px"></th></tr></thead>
          <tbody>${filas}</tbody>
        </table>
        <div id="pro_res" class="row" style="margin-top:8px;color:var(--muted)"></div>
      </div>`;
    const bv = j.bienvenida || {};
    const sel = document.getElementById('bvDias');
    if(sel){
      const d = String(parseInt(bv.pro_dias)||0);
      if([...sel.options].some(o=>o.value===d)) sel.value = d;
      document.getElementById('bvSaldo').value = bv.saldo_soles || '0';
      document.getElementById('bvSaldoUsd').value = bv.saldo_usd || '0';
      document.getElementById('bvSaldoBob').value = bv.saldo_bob || '0';
    }
  }catch(e){ document.getElementById('proPanel').innerHTML =
      '<div class="card">No se pudo cargar Pichangol Pro.</div>'; }
}
async function guardarProPrecio(iso){
  const v = parseFloat((document.getElementById('proPrecio_'+iso).value||'0').replace(',','.'))||0;
  const r = await fetch('/admin/api/pro/precio',{method:'POST',headers:headers(),
    body:JSON.stringify({precio_soles:v, pais:iso})});
  if(r.status===401){ salir(); return; }
  if(r.ok){ await cargarPro(); toast('Precio Pro actualizado'); }
  else toast('No se pudo guardar');
}
async function renovarPro(){
  if(!confirm('¿Renovar ahora las membresías Pro vencidas? Cobra de la billetera de cada jugador.')) return;
  const r = await fetch('/pagos/pro/renovar-vencidas',{method:'POST',headers:headers()});
  if(r.status===401){ salir(); return; }
  const j = await r.json();
  document.getElementById('pro_res').textContent =
    `Renovadas: ${j.renovadas||0} · sin saldo: ${j.sin_saldo||0}.`;
  await cargarPro();
}
async function guardarBienvenida(){
  const dias = parseInt(document.getElementById('bvDias').value)||0;
  const num = id => parseFloat((document.getElementById(id).value||'0').replace(',','.'))||0;
  const saldo = num('bvSaldo'), usd = num('bvSaldoUsd'), bob = num('bvSaldoBob');
  const r = await fetch('/admin/api/pro/bienvenida',{method:'POST',headers:headers(),
    body:JSON.stringify({pro_dias:dias, saldo_soles:saldo, saldo_usd:usd, saldo_bob:bob})});
  if(r.status===401){ salir(); return; }
  if(r.ok) toast((dias||saldo||usd||bob) ? `Bienvenida activa: ${dias} días de Pro + S/ ${saldo} · $ ${usd} · Bs ${bob}` : 'Bienvenida apagada');
  else toast('No se pudo guardar');
}
async function darCortesia(){
  const email = (document.getElementById('cortesiaEmail').value||'').trim().toLowerCase();
  const dias = parseInt(document.getElementById('cortesiaDias').value)||90;
  if(!email || !email.includes('@')){ toast('Pon el correo del dueño'); return; }
  const r = await fetch('/pagos/pro/cortesia',{method:'POST',headers:headers(),
    body:JSON.stringify({email, dias})});
  if(r.status===401){ salir(); return; }
  const j = await r.json().catch(()=>({}));
  if(j.ok){ toast(`Pro de cortesía activado (${dias} días)`); await cargarPro(); }
  else toast('No se pudo activar: '+(j.error||'error'));
}
async function darRegaloSaldo(){
  const email = (document.getElementById('cortesiaEmail').value||'').trim().toLowerCase();
  const soles = parseFloat((document.getElementById('regaloSaldo').value||'0').replace(',','.'))||0;
  if(!email || !email.includes('@')){ toast('Pon el correo del dueño'); return; }
  if(soles<=0){ toast('Pon el monto del regalo'); return; }
  const r = await fetch('/pagos/regalo-saldo',{method:'POST',headers:headers(),
    body:JSON.stringify({email, soles})});
  if(r.status===401){ salir(); return; }
  const j = await r.json().catch(()=>({}));
  if(j.ok) toast(`Saldo de regalo acreditado: S/ ${soles} (total S/ ${j.saldo_promo_soles})`);
  else toast('No se pudo regalar: '+(j.error||'error'));
}
async function revocarCortesia(email){
  if(!confirm(`¿Revocar el Pro de cortesía de ${email}? Pierde el acceso Pro al instante.`)) return;
  const r = await fetch('/pagos/pro/cortesia',{method:'POST',headers:headers(),
    body:JSON.stringify({email, dias:0})});
  if(r.status===401){ salir(); return; }
  const j = await r.json().catch(()=>({}));
  if(j.ok){ toast('Cortesía revocada'); await cargarPro(); }
  else toast('No se pudo revocar');
}

// --- Datos de la EMPRESA (web, legales, Libro de Reclamaciones) ----------------
// Razón social, RUC, dirección, WhatsApp POR PAÍS (las mismas claves que usa
// el APK), correo y horario que pinta TODO lo público (portada, pie, /legal/*,
// comprobantes). Se guardan en el snapshot de ESTE ambiente: QAS y PRD tienen
// cada uno los suyos.
let empresaCampos = [];
async function cargarEmpresa(){
  const box = document.getElementById('empresaPanel');
  if(!box) return;
  box.innerHTML = '<div class="card">Cargando…</div>';
  try{
    const r = await fetch('/admin/api/empresa',{headers:headers()});
    if(r.status===401){ salir(); return; }
    if(!r.ok){ box.innerHTML='<div class="card">No se pudo cargar.</div>'; return; }
    const j = await r.json();
    empresaCampos = j.campos||[];
    renderEmpresa(j.datos||{}, j.vista||{});
  }catch(e){ box.innerHTML='<div class="card">Error de red.</div>'; }
}
function renderEmpresa(d, v){
  const inp = 'style="display:block;width:100%;margin-top:4px;padding:10px 12px;border:1px solid var(--border);border-radius:10px;font-family:inherit;font-size:14px;font-weight:400"';
  const filas = empresaCampos.map(c=>`
    <label style="display:block;margin-top:12px;font-size:12.5px;font-weight:700">${c.bandera?c.bandera+' ':''}${esc(c.etiqueta)}
      ${c.prefijo ? `<span style="display:flex;gap:8px;align-items:center;margin-top:4px">
          <span style="color:var(--muted);font-weight:700;font-size:14px;white-space:nowrap">+${esc(c.prefijo)}</span>
          <input id="emp_${c.clave}" value="${esc(d[c.clave]||'')}" inputmode="numeric" placeholder="número local" ${inp.replace('margin-top:4px;','')}></span>`
        : `<input id="emp_${c.clave}" value="${esc(d[c.clave]||'')}" ${c.clave.includes('correo')?'type="email"':''} ${inp}>`}
      <small style="display:block;color:var(--muted);font-weight:400;margin-top:3px">${esc(c.ayuda)}</small>
    </label>`).join('');
  document.getElementById('empresaPanel').innerHTML =
    `<div class="card"><div class="top"><h3>Datos de la empresa</h3></div>
      <div class="row">Salen en la portada (Contacto, Términos, Privacidad), en el pie de
        TODAS las páginas web, en <code>/legal/*</code> y en el Libro de Reclamaciones.
        Culqi, INDECOPI y Play revisan que sean los reales. Los cambios se ven al instante,
        sin publicar código, y son de <b>este ambiente</b>. <b>WhatsApp por país:</b> el app
        propone al usuario el número de su país y la web lista todos los configurados
        (un país sin número no se muestra).</div>
      ${filas}
      <div class="actions">
        <button class="btn-ap" onclick="guardarEmpresa()">Guardar datos</button>
        <a class="btn-sec" href="/#contacto" target="_blank" rel="noopener" style="text-decoration:none">Ver en la web ↗</a>
      </div>
      <div class="row" style="margin-top:14px;padding-top:12px;border-top:1px solid var(--border)">
        <b>Así se ve hoy:</b><br>
        ${v.razon_social||''} · ${v.doc_etiqueta||'RUC'} ${v.ruc||''}<br>
        ${v.direccion||''}<br>
        WhatsApp: ${(v.whatsapps||[]).length ? v.whatsapps.map(w=>`${w.bandera} <a href="${w.url}" target="_blank" rel="noopener">${w.bonito}</a> ${w.pais}`).join(' · ') : '<span style="color:var(--rojo)">ninguno configurado</span>'}<br>
        <a href="mailto:${v.correo||''}">${v.correo||'—'}</a> · ${v.horario||''}<br>
        <span style="color:var(--muted)">Privacidad / eliminar cuenta: ${v.correo_privacidad||v.correo||'—'}</span>
      </div></div>`;
}
async function guardarEmpresa(){
  const datos = {};
  for(const c of empresaCampos){ datos[c.clave] = document.getElementById('emp_'+c.clave).value||''; }
  const r = await fetch('/admin/api/empresa',{method:'POST',headers:headers(),body:JSON.stringify({datos})});
  if(r.status===401){ salir(); return; }
  const j = await r.json().catch(()=>({}));
  if(r.ok && j.ok){ renderEmpresa(j.datos||{}, j.vista||{}); toast('Datos de la empresa guardados'); }
  else alert(j.detail || 'No se pudo guardar');
}
// ── Servicios extra: catálogo global + sugerencias de dueños ──
let servCat = {servicios:[], tipos:{}, ambitos:{}, sugerencias:[]};
async function cargarServicios(){
  const box = document.getElementById('serviciosPanel'); if(!box) return;
  box.innerHTML = '<div class="card">Cargando…</div>';
  try{
    const r = await fetch('/admin/api/servicios-extra',{headers:headers()});
    if(r.status===401){ salir(); return; }
    if(!r.ok){ box.innerHTML='<div class="card">No se pudo cargar.</div>'; return; }
    servCat = await r.json(); renderServicios();
  }catch(e){ box.innerHTML='<div class="card">Error de red.</div>'; }
}
function renderServicios(){
  const inp = 'style="padding:8px 10px;border:1px solid var(--border);border-radius:10px;font-family:inherit;font-size:13.5px"';
  const selTipo = (v,id)=>`<select id="${id}" ${inp}>${Object.entries(servCat.tipos).map(([k,n])=>`<option value="${k}"${k===v?' selected':''}>${esc(n)}</option>`).join('')}</select>`;
  const selAmb = (v,id)=>`<select id="${id}" ${inp}>${Object.entries(servCat.ambitos).map(([k,n])=>`<option value="${k}"${k===v?' selected':''}>${esc(n)}</option>`).join('')}</select>`;
  const filas = (servCat.servicios||[]).map(s=>`
    <tr style="${s.activo?'':'opacity:.55'}">
      <td style="font-size:20px">${esc(s.emoji||'')}</td>
      <td><b>${esc(s.nombre)}</b><br><code style="font-size:11px;color:var(--muted)">${esc(s.clave)}</code></td>
      <td>${selTipo(s.tipo,'st_'+s.clave)}</td>
      <td>${selAmb(s.ambito,'sa_'+s.clave)}</td>
      <td><input id="sn_${s.clave}" value="${esc(s.nombre)}" style="width:100%;min-width:160px;padding:8px 10px;border:1px solid var(--border);border-radius:10px;font-family:inherit;font-size:13.5px"></td>
      <td style="white-space:nowrap">
        <button class="btn-sec" title="Guardar cambios" onclick="guardarServicio('${esc(s.clave)}')">💾</button>
        <button class="btn-sec" title="${s.activo?'Ocultar a dueños nuevos':'Volver a ofrecer'}" onclick="activarServicio('${esc(s.clave)}',${s.activo?'false':'true'})">${s.activo?'⏸':'▶'}</button>
      </td>
    </tr>`).join('');
  const pend = (servCat.sugerencias||[]).filter(x=>x.estado==='pendiente');
  const sug = pend.length ? pend.map(x=>`
    <div class="row" style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;border:1px solid #F2C94C;background:#FFFBEA;border-radius:12px;padding:10px 12px;margin-top:8px">
      <div style="flex:1;min-width:220px"><b>${esc(x.texto)}</b><br><small style="color:var(--muted)">${esc(x.email)}${x.local?' · '+esc(x.local):''} · ${new Date((x.creado_en||0)*1000).toLocaleString('es-PE')}</small></div>
      <button class="btn-ap" onclick="usarSugerencia('${esc(x.id)}','${esc(x.texto).replace(/'/g,'&#39;')}')">➕ Agregar al catálogo</button>
      <button class="btn-sec" onclick="atenderSugerencia('${esc(x.id)}','descartada')">Descartar</button>
    </div>`).join('') : '<div class="row" style="color:var(--muted)">Sin sugerencias pendientes.</div>';
  document.getElementById('serviciosPanel').innerHTML =
    `<div class="card"><div class="top"><h3>Servicios extra (catálogo global)</h3></div>
      <div class="row">Add-ons de pago que el jugador suma a su reserva. El catálogo es ÚNICO para los 3 países
        y lo ve el app y la web al instante (sin publicar código). El dueño solo elige de esta lista y pone su precio:
        <b>Del local</b> (piscina, sauna, entrada general…) se aplica a todas las canchas del local;
        <b>De la cancha</b> (árbitro, petos…) solo a esa cancha. <b>Cobro:</b> por reserva, por persona (el jugador
        elige cuántas) o por turno (× turnos reservados). Desactivar oculta el servicio a dueños nuevos; lo ya
        configurado sigue vigente.</div>
      <div style="overflow:auto;margin-top:10px"><table style="width:100%;border-collapse:collapse;font-size:13.5px">
        <thead><tr style="text-align:left;color:var(--muted);font-size:12px"><th></th><th>Servicio</th><th>Cobro</th><th>Ámbito</th><th>Nombre visible</th><th></th></tr></thead>
        <tbody>${filas}</tbody></table></div>
      <div class="row" style="margin-top:16px;padding-top:12px;border-top:1px solid var(--border)"><b>➕ Nuevo servicio</b>
        <div style="display:grid;grid-template-columns:70px 1fr 1fr 1fr 1fr auto;gap:8px;margin-top:8px;align-items:center">
          <input id="ns_emoji" placeholder="🏊" maxlength="4" ${inp}>
          <input id="ns_nombre" placeholder="Nombre visible (ej. Piscina)" ${inp}>
          <input id="ns_clave" placeholder="clave (ej. piscina)" ${inp}>
          ${selTipo('reserva','ns_tipo')}${selAmb('local','ns_ambito')}
          <button class="btn-ap" onclick="nuevoServicio()">Agregar</button>
        </div></div>
      <div class="row" style="margin-top:16px;padding-top:12px;border-top:1px solid var(--border)"><b>💡 Sugerencias de dueños</b> <small style="color:var(--muted)">("mi local ofrece X y no está en la lista", desde Editar cancha en la web)</small>${sug}</div>
    </div>`;
}
async function postServicio(body){
  const r = await fetch('/admin/api/servicios-extra',{method:'POST',headers:headers(),body:JSON.stringify(body)});
  if(r.status===401){ salir(); return false; }
  const j = await r.json().catch(()=>({}));
  if(r.ok && j.ok){ servCat = j; renderServicios(); toast('Catálogo guardado'); return true; }
  alert(j.detail || 'No se pudo guardar'); return false;
}
function guardarServicio(clave){
  const s = (servCat.servicios||[]).find(x=>x.clave===clave); if(!s) return;
  postServicio({...s, nombre: document.getElementById('sn_'+clave).value, tipo: document.getElementById('st_'+clave).value, ambito: document.getElementById('sa_'+clave).value, nuevo:false});
}
function nuevoServicio(){
  const nombre = document.getElementById('ns_nombre').value.trim();
  let clave = document.getElementById('ns_clave').value.trim().toLowerCase();
  if(!clave) clave = nombre.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g,'').replace(/[^a-z0-9]+/g,'_').replace(/^_+|_+$/g,'').slice(0,40);
  postServicio({clave, nombre, emoji: document.getElementById('ns_emoji').value.trim(), tipo: document.getElementById('ns_tipo').value, ambito: document.getElementById('ns_ambito').value, activo:true, nuevo:true});
}
async function activarServicio(clave, activo){
  const r = await fetch('/admin/api/servicios-extra/'+encodeURIComponent(clave)+'/activo',{method:'POST',headers:headers(),body:JSON.stringify({activo})});
  if(r.status===401){ salir(); return; }
  const j = await r.json().catch(()=>({})); if(r.ok && j.ok){ servCat = j; renderServicios(); } else alert(j.detail||'No se pudo');
}
async function atenderSugerencia(id, estado){
  const r = await fetch('/admin/api/servicios-extra/sugerencias/'+encodeURIComponent(id),{method:'POST',headers:headers(),body:JSON.stringify({estado})});
  if(r.status===401){ salir(); return; }
  const j = await r.json().catch(()=>({})); if(r.ok && j.ok){ servCat = j; renderServicios(); } else alert(j.detail||'No se pudo');
}
function usarSugerencia(id, texto){
  document.getElementById('ns_nombre').value = texto; document.getElementById('ns_clave').value = '';
  document.getElementById('ns_nombre').scrollIntoView({behavior:'smooth', block:'center'}); document.getElementById('ns_nombre').focus();
  atenderSugerencia(id, 'atendida');
}
// ── Publicar en Facebook (página de Pichangol): fotos reales + plantilla + vista previa ──
let redes = {facebook:{}, locales:[], plantillas:{}, historial:[], ia:{}}, redesSel = {fotos:[], cancha:'', plantilla:'ia', formato:'cuadrado', img:'', tono:'cercano', enfoque:'auto', ia:null, evitar:[], redactando:false};
const ENFOQUE_NOMBRE = {auto:'Que varíe solo', beneficio:'Beneficio de reservar', local:'El local protagonista', comunidad:'Comunidad / armar partido', tip:'Tip deportivo', finde:'Plan de fin de semana', promo:'Precio / promo', duenos:'Para dueños de cancha', academia:'Para padres (academias)', humor:'Humor ligero', historia:'La historia de Pichangol'};
async function cargarRedes(){
  const box = document.getElementById('redesPanel'); if(!box) return;
  box.innerHTML = '<div class="card"><div class="rd-cargando"><span class="rd-spin"></span> Cargando locales, fotos y estado de la página…</div></div>';
  try{
    const r = await fetch('/admin/api/redes/pichangol',{headers:headers()});
    if(r.status===401){ salir(); return; }
    if(!r.ok){ box.innerHTML='<div class="card">No se pudo cargar.</div>'; return; }
    redes = await r.json(); renderRedes();
    if(!redesSel.cancha && redes.locales.length) redesSel.cancha = redes.locales[0].canchas[0].id;
    aplicarPlantilla(); cargarAgente(); cargarBiblioteca(); cargarMusica();
  }catch(e){ box.innerHTML='<div class="card">Error de red.</div>'; }
}
// ── Estado de la interfaz del pane (pestaña, paso del asistente, tipo y fuente del contenido). Se recuerda en el navegador.
let redesUI = {tab:'publicar', paso:1, tipo:'foto', fuente:'biblioteca', fuenteVideo:'biblioteca'};
try{ Object.assign(redesUI, JSON.parse(localStorage.getItem('pichangol_redes_ui')||'{}'), {paso:1}); }catch(e){}
function rdUI(k, v){ redesUI[k]=v; try{ localStorage.setItem('pichangol_redes_ui', JSON.stringify({tab:redesUI.tab, tipo:redesUI.tipo, fuente:redesUI.fuente, fuenteVideo:redesUI.fuenteVideo})); }catch(e){} renderRedes(); }
function rdPaso(n){ redesUI.paso = n; renderRedes(); const el=document.querySelector('.rd-paso[data-paso="'+n+'"]'); if(el && el.getBoundingClientRect().top < 0) el.scrollIntoView({block:'start', behavior:'smooth'}); }
function rdTipo(t){
  if(t==='foto' && redesSel.video){ if(!confirm('¿Cambiar a fotos? Se descarta el video elegido.')) return; quitarVideoRedes(); }
  rdUI('tipo', t);
}
function bibMsg(h){ document.querySelectorAll('.rd-bib-msg').forEach(m=>{ m.innerHTML = h; }); }
function renderRedes(){
  const fb = redes.facebook || {};
  const g = id => (document.getElementById(id)||{}).value; const prev = {t:g('rd_titulo'), s:g('rd_sub'), x:g('rd_texto'), e:g('rd_etq'), p:g('rd_pie'), f:g('rd_formato'), tema:g('rd_tema')};
  const inp = 'style="display:block;width:100%;margin-top:4px;padding:10px 12px;border:1px solid var(--border);border-radius:10px;font-family:inherit;font-size:14px"';
  const esVideo = !!redesSel.video, vd = redesSel.video || {};
  if(esVideo) redesUI.tipo = 'video';
  const tipo = redesUI.tipo === 'video' ? 'video' : 'foto';
  const listoPub = esVideo ? (vd.estado==='listo' && !!vd.id) : !!redesSel.img;
  const mb = b => b < 1048576 ? Math.max(1, Math.round(b/1024))+' KB' : (b/1048576).toFixed(b>=104857600?0:1)+' MB';
  // ── Facebook: tipo de token (de PÁGINA = lo correcto; de USUARIO la torre saca sola el de página) y permisos.
  const faltaPublicar = (fb.faltan||[]).includes('pages_manage_posts');
  const tokenInfo = !fb.configurado || !fb.nombre ? '' :
    (fb.advertencia && (faltaPublicar || !fb.token_tipo || (fb.advertencia.indexOf('no entregó')>=0))
      ? `<div style="margin-top:6px;padding:8px 10px;border-radius:10px;background:#FDECEC;color:var(--rojo);font-weight:600">⚠️ ${esc(fb.advertencia)} <small>(ver "Cómo conectar la página", paso 2)</small></div>`
      : fb.advertencia ? `<div style="margin-top:6px;padding:8px 10px;border-radius:10px;background:#FFF6E5;color:#8a5a00">ℹ️ ${esc(fb.advertencia)}</div>`
      : fb.token_tipo==='pagina' ? `<small style="color:var(--muted);margin-left:8px">token de página ✓${(fb.faltan||[]).length?' · sin '+esc(fb.faltan.join(', ')):''}</small>` : '');
  const vence = fb.vence ? `vence el ${new Date(fb.vence*1000).toLocaleDateString('es-PE',{day:'2-digit',month:'short',year:'numeric'})}` : (fb.nombre ? 'no vence' : '');
  const origen = fb.origen==='torre' ? 'token guardado en la torre' : fb.origen==='railway' ? 'token de Railway' : '';
  const tokenCaja = `<details style="margin-top:8px" ${fb.configurado && !fb.nombre ? 'open' : ''}><summary style="cursor:pointer;font-weight:700;font-size:12.5px">🔑 Token de Facebook ${fb.nombre?`<small style="color:var(--muted);font-weight:400">· ${esc(origen)}${vence?' · '+vence:''}</small>`:''}</summary>
      <div style="margin-top:6px;padding:10px 12px;border:1px solid var(--border);border-radius:10px;background:#FAFBFC">
        <small style="color:var(--muted)">Pega aquí un token nuevo del <b>Explorador de la API Graph</b> (de página o de usuario, con <code>pages_manage_posts</code>, <code>pages_read_engagement</code> y <code>pages_show_list</code>). La torre lo extiende, obtiene el token de la PÁGINA (que no vence) y lo guarda cifrado; ya no hace falta tocar Railway. El token nunca se muestra de vuelta.</small>
        <div style="display:flex;gap:8px;margin-top:8px;flex-wrap:wrap"><input id="rd_token" type="password" placeholder="EAAB…" autocomplete="off" style="flex:1;min-width:260px;padding:9px 12px;border:1px solid var(--border);border-radius:10px;font-family:inherit;font-size:13px">
          <button type="button" class="btn-ap" id="rd_token_btn" onclick="guardarTokenRedes()">Guardar y verificar</button>
          ${fb.guardado?'<button type="button" class="btn-sec" onclick="olvidarTokenRedes()">Olvidar el guardado</button>':''}</div>
        <div id="rd_token_msg" style="margin-top:6px;font-size:12.5px"></div>
      </div></details>`;
  const estadoFb = fb.configurado
    ? (fb.nombre ? `<span style="color:var(--green);font-weight:700">● Conectado a la página <b>${esc(fb.nombre)}</b></span> ${fb.link?`<a href="${esc(fb.link)}" target="_blank" rel="noopener">abrir ↗</a>`:''}${tokenInfo}`
                 : `<span style="color:var(--rojo);font-weight:700">● Credenciales configuradas pero Facebook respondió: ${esc(fb.error||'error')}</span>${/expired|190|venci/i.test(fb.error||'')?'<div style="margin-top:4px;color:var(--rojo)">El token venció (los de usuario sin extender duran 1-2 h). Pega uno nuevo abajo: la torre lo convierte en uno de página que no vence.</div>':''}`)
    : `<span style="color:var(--muted);font-weight:700">○ Sin credenciales de Facebook</span>: la torre compone y descarga la pieza; para publicar directo, pon <code>FB_PAGE_ID</code> en Railway y pega el token abajo (o <code>FB_PAGE_TOKEN</code> en Railway).`;
  const fbPill = !fb.configurado ? `<span class="rd-pill off" onclick="rdUI('tab','conexiones')" title="Ir a Conexiones">○ Facebook sin conectar</span>`
    : !fb.nombre ? `<span class="rd-pill bad" onclick="rdUI('tab','conexiones')" title="Ir a Conexiones">⚠️ Facebook: ${esc((fb.error||'error').slice(0,60))}</span>`
    : (faltaPublicar || !fb.token_tipo) ? `<span class="rd-pill warn" onclick="rdUI('tab','conexiones')" title="Ir a Conexiones">⚠️ Página ${esc(fb.nombre)} · revisar permisos</span>`
    : `<span class="rd-pill ok" onclick="rdUI('tab','conexiones')" title="Ir a Conexiones">● Página ${esc(fb.nombre)}</span>`;
  const bibPill = !bib ? '' : bib.conectado ? `<span class="rd-pill ok" onclick="rdUI('tab','conexiones')" title="Ir a Conexiones">● Google Fotos · ${bib.fotos||0} fotos · ${bib.videos||0} videos</span>` : `<span class="rd-pill off" onclick="rdUI('tab','conexiones')" title="Ir a Conexiones">○ Google Fotos sin conectar</span>`;
  const musPill = !mus ? '' : mus.conectado ? `<span class="rd-pill ok" onclick="rdUI('tab','conexiones')" title="Ir a Conexiones">● Mi música · ${mus.pistas||0} pistas</span>` : `<span class="rd-pill off" onclick="rdUI('tab','conexiones')" title="Ir a Conexiones">○ Mi música sin conectar</span>`;

  // ── PASO 1 · Contenido ───────────────────────────────────────────────────
  const locales = (redes.locales||[]).map(l=>`<option value="${esc(l.canchas[0].id)}"${redesSel.cancha===l.canchas[0].id?' selected':''}>${esc(l.local)}${l.zona?' · '+esc(l.zona):''} (${l.fotos.length} fotos)</option>`).join('');
  const loc = (redes.locales||[]).find(l=>l.canchas.some(c=>c.id===redesSel.cancha));
  const fotosLocal = loc ? loc.fotos.map(u=>`<label style="position:relative;cursor:pointer"><img src="${esc(u)}" style="width:118px;height:118px;object-fit:cover;border-radius:12px;border:3px solid ${redesSel.fotos.includes(u)?'var(--green)':'transparent'};display:block"><input type="checkbox" ${redesSel.fotos.includes(u)?'checked':''} onchange="toggleFotoRedes('${esc(u)}',this.checked)" style="position:absolute;top:8px;left:8px;width:18px;height:18px"></label>`).join('') : '<small style="color:var(--muted)">Elige un local arriba. Si este ambiente no tiene locales con fotos, usa Google Fotos o tu computadora.</small>';
  const fuenteBtn = (k, txt) => `<button type="button" class="rd-sub${redesUI.fuente===k?' on':''}" onclick="rdUI('fuente','${k}')">${txt}</button>`;
  const fuenteFoto = redesUI.fuente==='local'
    ? `<select id="rd_local" ${inp} onchange="cambiarLocalRedes(this.value)"><option value="">— elige un local —</option>${locales}</select>
       <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:10px" id="rd_fotos">${fotosLocal}</div>
       <small style="display:block;margin-top:6px;color:var(--muted)">Fotos reales que subió el dueño de cada local (bucket de canchas).</small>`
    : redesUI.fuente==='pc'
    ? `<label class="btn-sec" for="rd_subir" style="cursor:pointer">📷 Elegir fotos de mi computadora</label><input type="file" id="rd_subir" accept="image/*" multiple hidden onchange="subirFotosRedes(this)">
       <small style="display:block;margin-top:6px;color:var(--muted)">Se comprimen en tu navegador (1600 px) y entran directo al collage. No se guardan en la biblioteca.</small>`
    : `<div id="rd_biblioteca"></div>`;
  const elegidas = redesSel.fotos.length ? `<div style="margin-top:12px;padding:10px 12px;border-radius:12px;background:#F2F8F3"><small style="font-weight:700">Elegidas para esta publicación · ${redesSel.fotos.length}/${redes.max_fotos||4}</small>
      <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:6px">${redesSel.fotos.map(u=>`<span style="position:relative;display:inline-block"><img src="${esc(u)}" style="width:72px;height:72px;object-fit:cover;border-radius:10px;display:block"><button type="button" title="Quitar" onclick="toggleFotoRedes('${esc(u)}',false)" style="position:absolute;top:-6px;right:-6px;width:22px;height:22px;border-radius:50%;border:0;background:#0A1B3D;color:#fff;font-weight:700;cursor:pointer;line-height:1">✕</button></span>`).join('')}</div>
      <small style="color:var(--muted)">1 foto = imagen completa · 2 a 4 = collage. La primera es la principal.</small>
      <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-top:8px;padding-top:8px;border-top:1px solid #DDE8E0"><button type="button" class="btn-sec" onclick="fotosAVideo()" ${fvOcupado?'disabled':''}>${fvOcupado?'<span class="rd-spin chico"></span> Armando el video…':'🎬 Convertir estas fotos en un video con movimiento'}</button>
        <select id="rd_fv_formato" style="padding:6px 10px;border:1px solid var(--border);border-radius:10px;font-family:inherit;font-size:12.5px"><option value="vertical">Vertical 9:16 · Reels</option><option value="cuadrado">Cuadrado 1:1</option></select>
        <select id="rd_fv_seg" style="padding:6px 10px;border:1px solid var(--border);border-radius:10px;font-family:inherit;font-size:12.5px"><option value="2">2 s por foto</option><option value="2.8" selected>3 s por foto</option><option value="4">4 s por foto</option></select>
        <small style="color:var(--muted)">Zoom y paneo lentos con fundidos (estilo CapCut); luego le pones intro, rótulo, cierre y música en el paso 2.</small></div></div>` : '';
  const fuenteVBtn = (k, txt) => `<button type="button" class="rd-sub${redesUI.fuenteVideo===k?' on':''}" onclick="rdUI('fuenteVideo','${k}')">${txt}</button>`;
  const videoEstado = !esVideo ? '' : `<div style="margin-top:10px;padding:10px 12px;border-radius:12px;background:#F2F8F3;display:flex;gap:10px;align-items:center;flex-wrap:wrap"><b>🎞️ ${esc(vd.nombre||'video')}</b><small style="color:var(--muted)">${mb(vd.bytes||0)}${vd.dur?' · '+Math.round(vd.dur)+' s':''}</small>
        <span id="rd_video_estado" style="flex:1;min-width:160px">${vd.estado==='subiendo'?'<span class="rd-spin chico"></span> Subiendo a la torre… <b id="rd_video_pct">'+(vd.pct||0)+'%</b>':vd.estado==='listo'?'<span style="color:var(--green);font-weight:700">✓ Video listo</span>':'<span style="color:var(--rojo)">'+esc(vd.error||'No se pudo subir')+'</span>'}</span>
        <button type="button" class="btn-sec" onclick="quitarVideoRedes()">✕ Quitar video</button>
        <div style="flex-basis:100%;height:6px;border-radius:3px;background:#E9EDF0;overflow:hidden;${vd.estado==='subiendo'?'':'display:none'}"><div id="rd_video_prog" style="height:100%;width:${vd.pct||0}%;background:var(--green);transition:width .2s"></div></div></div>`;
  const fuenteVideo = esVideo ? videoEstado
    : redesUI.fuenteVideo==='pc'
    ? `<label class="btn-sec" for="rd_video" style="cursor:pointer">🎬 Elegir un video de mi computadora</label><input type="file" id="rd_video" accept="video/mp4,video/quicktime,video/x-m4v,video/webm,video/*" hidden onchange="subirVideoRedes(this)"><small style="display:block;margin-top:6px;color:var(--muted)">MP4 o MOV · hasta ${redes.video_max_mb||300} MB. Sube a la torre con barra de progreso.</small>`
    : `<div id="rd_biblioteca_videos"></div>`;
  const paso1 = `<div class="rd-tiles">
      <button type="button" class="rd-tile${tipo==='foto'?' on':''}" onclick="rdTipo('foto')"><b>📷 Fotos</b><small>Una imagen o collage de hasta ${redes.max_fotos||4} fotos con el logo, un título y el pie www.pichangol.app.</small></button>
      <button type="button" class="rd-tile${tipo==='video'?' on':''}" onclick="rdTipo('video')"><b>🎬 Video</b><small>Un clip pulido con intro, marca de agua, cierre, subtítulos y música original.</small></button></div>
    ${tipo==='foto' ? `<div class="rd-subs"><small style="align-self:center;color:var(--muted);font-weight:700;margin-right:4px">De dónde</small>${fuenteBtn('biblioteca','📷 Google Fotos'+(bib?' ('+(bib.fotos||0)+')':''))}${fuenteBtn('local','🏟️ Fotos de un local')}${fuenteBtn('pc','💻 Mi computadora')}</div>${fuenteFoto}${elegidas}`
                    : (esVideo ? videoEstado : `<div class="rd-subs"><small style="align-self:center;color:var(--muted);font-weight:700;margin-right:4px">De dónde</small>${fuenteVBtn('biblioteca','📷 Google Fotos'+(bib?' ('+(bib.videos||0)+')':''))}${fuenteVBtn('pc','💻 Mi computadora')}</div>${fuenteVideo}`)}
    <div class="rd-next"><button type="button" class="btn-ap" onclick="rdPaso(2)" ${(tipo==='foto'?redesSel.fotos.length:(esVideo&&vd.estado==='listo'))?'':'disabled'}>Siguiente: Estilo →</button></div>`;
  const res1 = tipo==='foto' ? (redesSel.fotos.length ? `${redesSel.fotos.length} foto(s) elegida(s)` : 'Elige fotos o un video') : (esVideo ? `Video: ${esc(vd.nombre||'')} · ${mb(vd.bytes||0)}${vd.estado==='subiendo'?' · subiendo '+(vd.pct||0)+'%':''}` : 'Elige un video');
  const ok1 = tipo==='foto' ? !!redesSel.fotos.length : (esVideo && vd.estado==='listo');

  // ── PASO 2 · Estilo ──────────────────────────────────────────────────────
  const estiloFoto = `<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px">
        <label style="font-size:12.5px;font-weight:700">Formato<select id="rd_formato" ${inp} onchange="redesSel.formato=this.value"><option value="cuadrado">Cuadrado 1080×1080 (feed)</option><option value="horizontal">Horizontal 1200×630</option><option value="historia">Historia 1080×1920</option></select></label>
        <label style="font-size:12.5px;font-weight:700">Etiqueta<input id="rd_etq" ${inp} maxlength="16" placeholder="Nuevo"></label>
        <label style="font-size:12.5px;font-weight:700">Pie<input id="rd_pie" ${inp} value="www.pichangol.app" maxlength="40"></label></div>
      <small style="display:block;margin-top:8px;color:var(--muted)">La etiqueta es la pastilla naranja arriba a la derecha (Tip, Nuevo, Promo…); el pie es la pastilla blanca de abajo. El título y el subtítulo que van sobre la imagen se escriben en el paso 3.</small>`;
  const estiloVideo = !esVideo ? '<small style="color:var(--muted)">Primero elige un video en el paso 1.</small>'
    : vd.estado!=='listo' ? '<small style="color:var(--muted)"><span class="rd-spin chico"></span> Espera a que el video termine de subir.</small>'
    : `<small style="display:block;color:var(--muted);margin-bottom:4px">Opcional: si no generas la versión pulida, se publica el video tal cual.</small>${pulidoHtml(vd)}`;
  const paso2 = `<div style="${tipo==='foto'?'':'display:none'}">${estiloFoto}</div><div style="${tipo==='video'?'':'display:none'}">${estiloVideo}</div>
    <div class="rd-next"><button type="button" class="btn-sec" onclick="rdPaso(1)">← Contenido</button><span style="flex:1"></span><button type="button" class="btn-ap" onclick="rdPaso(3)">Siguiente: Texto →</button></div>`;
  const pl = vd.pulido || {}, po = pl.opciones || {};
  const MUS = {auto:'música automática', fondo:'música de fondo', protagonista:'música protagonista', no:'sin música'};
  const res2 = tipo==='foto' ? `${{cuadrado:'Cuadrado 1080×1080',horizontal:'Horizontal 1200×630',historia:'Historia 1080×1920'}[prev.f||redesSel.formato]||'Cuadrado'}${prev.e?' · etiqueta "'+esc(prev.e)+'"':''}`
    : !esVideo ? '—' : (pl.estado==='listo' && pl.url ? `${pl.usar?'Versión pulida':'Original'} · ${po.formato||'vertical'} · ${MUS[po.musica_modo||'auto']}${po.musica_pista&&mus?' · 🎵 '+esc(po.musica_pista==='cualquiera'?'cualquiera':po.musica_pista.startsWith('carpeta:')?po.musica_pista.slice(8):(((mus.items||[]).find(t=>t.id===po.musica_pista)||{}).nombre||''))+(po.musica_desde!==''&&po.musica_desde!=null&&Number(po.musica_desde)>0?' desde '+po.musica_desde+' s':''):''}` : (pl.estado==='transcribiendo'||pl.estado==='renderizando') ? 'Puliendo… '+(pl.progreso||0)+'%' : 'Sin pulir (se publica el original)');
  const ok2 = redesUI.paso > 2;

  // ── PASO 3 · Texto ───────────────────────────────────────────────────────
  const ia = redes.ia || {};
  const plantillas = [`<button class="btn-sec" style="${redesSel.plantilla==='ia'?'border-color:var(--green);background:#F2F8F3;font-weight:700':''}" onclick="redesSel.plantilla='ia';aplicarPlantilla()">✨ Redactar con IA</button>`]
    .concat(Object.entries(redes.plantillas||{}).map(([k,v])=>`<button class="btn-sec" style="${redesSel.plantilla===k?'border-color:var(--green);background:#F2F8F3':''}" onclick="redesSel.plantilla='${k}';aplicarPlantilla()">${esc(v.nombre)}</button>`)).join(' ');
  const tonos = (ia.tonos||['cercano','divertido','informativo','motivador']).map(t=>`<button type="button" class="btn-sec" style="padding:5px 10px;font-size:12.5px;${redesSel.tono===t?'border-color:var(--green);background:#F2F8F3;font-weight:700':''}" onclick="redesSel.tono='${t}';redactarRedes()">${t.charAt(0).toUpperCase()+t.slice(1)}</button>`).join(' ');
  const enfoques = Object.keys(ia.enfoques||ENFOQUE_NOMBRE).map(k=>`<option value="${k}"${redesSel.enfoque===k?' selected':''}>${esc(ENFOQUE_NOMBRE[k]||k)}</option>`).join('');
  const iaEstado = redesSel.redactando ? '<span class="rd-spin chico"></span> Redactando…'
    : redesSel.ia ? `<span style="color:var(--green);font-weight:700">✨ ${redesSel.ia.fuente==='ia'?'Redactado con IA':'Variante del banco (sin IA)'}</span> · enfoque: <b>${esc(ENFOQUE_NAME(redesSel.ia.enfoque))}</b>` : '';
  const iaHtml = redesSel.plantilla!=='ia' ? '' : `
          <div style="margin-top:10px;padding:12px 14px;border:1px solid var(--border);border-radius:12px;background:#FAFBFC">
            <div style="display:flex;gap:14px;flex-wrap:wrap;align-items:center">
              <div><small style="font-weight:700;color:var(--muted)">Tono</small><div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:4px">${tonos}</div></div>
              <label style="font-size:12.5px;font-weight:700;min-width:220px;flex:1">Enfoque<select id="rd_enfoque" ${inp} onchange="redesSel.enfoque=this.value;redactarRedes()">${enfoques}</select></label>
            </div>
            <label style="display:block;margin-top:8px;font-size:12.5px;font-weight:700">Algo que quieras que mencione (opcional)<input id="rd_tema" ${inp} maxlength="200" placeholder="p. ej. este sábado hay torneo relámpago · nueva iluminación LED · feriado largo"></label>
            <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-top:10px">
              <button type="button" class="btn-sec" id="rd_otra" onclick="redactarRedes(true)" ${redesSel.redactando?'disabled':''}>🔁 Otra versión</button>
              <span id="rd_ia_estado" style="font-size:12.5px;color:var(--muted)">${iaEstado}</span>
              ${ia.disponible===false?'<small style="color:#8a5a00">Sin ANTHROPIC_API_KEY en este ambiente: se usa el banco de variantes.</small>':''}
            </div>
            <small style="display:block;margin-top:6px;color:var(--muted)">La IA cambia el ángulo en cada pieza y evita repetir los ganchos de lo ya publicado. Edita lo que quieras antes de publicar.</small>
          </div>`;
  const paso3 = `<small style="font-weight:700;color:var(--muted)">¿Quién escribe?</small><div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:4px">${plantillas}</div>${iaHtml}
    <label style="display:block;margin-top:12px;font-size:12.5px;font-weight:700">${esVideo?'Título del video (va en el rótulo y el cierre; opcional)':'Título sobre la imagen'}<input id="rd_titulo" ${inp} maxlength="60" ${redesSel.redactando?'disabled placeholder="Redactando con IA…"':''}></label>
    <label style="display:${esVideo?'none':'block'};margin-top:8px;font-size:12.5px;font-weight:700">Subtítulo sobre la imagen<input id="rd_sub" ${inp} maxlength="90"></label>
    <label style="display:block;margin-top:12px;font-size:12.5px;font-weight:700">Texto de la publicación (lo que se lee en Facebook)<textarea id="rd_texto" rows="7" ${inp} ${redesSel.redactando?'disabled placeholder="Redactando con IA…"':''}></textarea></label>
    <div class="rd-next"><button type="button" class="btn-sec" onclick="rdPaso(2)">← Estilo</button><span style="flex:1"></span><button type="button" class="btn-ap" onclick="rdPaso(4)">Siguiente: Revisar y publicar →</button></div>`;
  const res3 = redesSel.redactando ? 'Redactando con IA…' : [prev.t ? `"${esc(prev.t)}"` : '', redesSel.plantilla==='ia' ? (redesSel.ia ? `✨ IA · ${esc(ENFOQUE_NAME(redesSel.ia.enfoque))}` : '✨ IA') : 'plantilla ' + esc(((redes.plantillas||{})[redesSel.plantilla]||{}).nombre||redesSel.plantilla)].filter(Boolean).join(' · ');
  const ok3 = !!prev.t || !!prev.x;

  // ── PASO 4 · Revisar y publicar ──────────────────────────────────────────
  const paso4 = `<div style="font-size:13px;color:var(--muted);margin-bottom:8px">${esVideo ? 'Revisa el video en la vista previa (la versión pulida si la generaste) y el texto del paso 3.' : 'La vista previa de la derecha es exactamente lo que se publica. Si cambias algo en los pasos anteriores, se rearma sola.'}</div>
    <div class="actions" style="margin-top:4px">
      <button class="btn-sec" id="rd_prev_btn" onclick="previsualizarRedes()" ${esVideo?'style="display:none"':''}>👁️ Rearmar vista previa</button>
      <button class="btn-sec" id="rd_descargar" onclick="descargarRedes()" ${redesSel.img&&!esVideo?'':'disabled'} ${esVideo?'style="display:none"':''}>⬇️ Descargar imagen</button>
      <button class="btn-ap" id="rd_publicar" onclick="publicarRedes()" ${fb.configurado?(listoPub?'':'disabled title="'+(esVideo?'Espera a que termine de subir el video':'Primero arma la vista previa')+'"'):'disabled data-bloqueado="1" title="Conecta la página de Facebook en la pestaña Conexiones"'}>📣 Publicar ${esVideo?'video ':''}en Facebook</button>
    </div>
    ${!fb.configurado?'<small style="display:block;margin-top:8px;color:#8a5a00">Facebook no está conectado: puedes descargar la imagen y publicarla a mano, o conectar la página en <a href="#" onclick="rdUI(\'tab\',\'conexiones\');return false">Conexiones</a>.</small>':''}
    <div id="rd_msg" class="row" style="margin-top:8px"></div>
    <div class="rd-next"><button type="button" class="btn-sec" onclick="rdPaso(3)">← Texto</button></div>`;
  const paso = (n, titulo, resumen, body, ok) => `<section class="rd-paso${redesUI.paso===n?' abierta':''}${ok&&redesUI.paso!==n?' lista':''}" data-paso="${n}">
      <div class="rd-h" onclick="rdPaso(${n})"><span class="rd-num">${ok&&redesUI.paso!==n?'✓':n}</span><div><b>${titulo}</b><small>${resumen||''}</small></div><span class="rd-edit">${redesUI.paso===n?'':'Editar'}</span></div>
      <div class="rd-cuerpo" style="${redesUI.paso===n?'':'display:none'}">${body}</div></section>`;

  // ── Historial ────────────────────────────────────────────────────────────
  const histN = (redes.historial||[]).length;
  const hist = (redes.historial||[]).map(h=>`<div class="row" style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;border-bottom:1px solid var(--border);padding:8px 0"><span>${h.ok?'✅':'⚠️'}</span><div style="flex:1;min-width:200px">${h.tipo==='video'?'🎬 ':'🖼️ '}<b>${esc(h.titulo||h.video_nombre||'(sin título)')}</b> <small style="color:var(--muted)">· ${h.fuente==='agente'?'🤖 agente'+(h.audiencia?' · '+esc(h.audiencia):''):esc(h.plantilla||'')} · ${h.tipo==='video'?('video '+esc(h.video_nombre||'')+' · '+Math.round((h.video_bytes||0)/1048576)+' MB'+(h.pulido?' · ✨ pulido'+(h.musica?' · 🎵':'')+(h.subtitulos?' · '+h.subtitulos+' subtítulos':''):'')):(h.fotos+' foto(s)')} · ${new Date((h.creado_en||0)*1000).toLocaleString('es-PE')}</small>${h.error?`<br><small style="color:var(--rojo)">${esc(h.error)}</small>`:''}</div>${h.url?`<a class="btn-sec" href="${esc(h.url)}" target="_blank" rel="noopener">Ver en Facebook ↗</a>`:''}</div>`).join('') || '<div class="row" style="color:var(--muted)">Todavía no hay publicaciones.</div>';

  // ── Pestañas ─────────────────────────────────────────────────────────────
  const tabBtn = (k, txt) => `<button type="button" class="${redesUI.tab===k?'on':''}" onclick="rdUI('tab','${k}')">${txt}</button>`;
  const tab = (k, html) => `<div class="rd-tab" data-tab="${k}" style="${redesUI.tab===k?'':'display:none'}">${html}</div>`;
  const agActivo = agente && agente.config && agente.config.activo;
  document.getElementById('redesPanel').innerHTML = `
    <div class="card">
      <div class="top" style="flex-wrap:wrap;gap:8px"><h3>📣 Redes de Pichangol</h3><span style="flex:1"></span>${fbPill} ${bibPill} ${musPill}</div>
      <div class="rd-tabs">${tabBtn('publicar','✍️ Publicar ahora')}${tabBtn('agente','🤖 Agente 24×7'+(agente?(agActivo?' · activo':' · pausado'):''))}${tabBtn('historial','🕘 Historial'+(histN?' ('+histN+')':''))}${tabBtn('conexiones','🔌 Conexiones')}</div>
      ${tab('publicar', `<div class="rd-grid">
        <div>
          ${paso(1,'Contenido',res1,paso1,ok1)}
          ${paso(2,'Estilo',res2,paso2,ok2)}
          ${paso(3,'Texto',res3,paso3,ok3)}
          ${paso(4,'Revisar y publicar','',paso4,false)}
        </div>
        <div style="position:sticky;top:12px;align-self:start"><label style="font-size:12.5px;font-weight:700">Vista previa <small id="rd_prev_estado" style="color:var(--muted);font-weight:400"></small></label>
          <div id="rd_prev" style="margin-top:4px;border:1px dashed var(--border);border-radius:14px;min-height:360px;display:flex;align-items:center;justify-content:center;color:var(--muted);background:#fafafa;overflow:hidden">${esVideo?`<video src="${(vd.pulido&&vd.pulido.usar&&vd.pulido.url)||vd.url}" controls playsinline style="max-width:100%;max-height:78vh;display:block;background:#000"></video>`:(redesSel.img?`<img src="${redesSel.img}" style="max-width:100%;max-height:78vh;display:block">`:'Elige fotos o un video en el paso 1: la vista previa se arma sola.')}</div>
          ${esVideo?`<small style="display:block;margin-top:6px;color:var(--muted)">${(vd.pulido&&vd.pulido.usar&&vd.pulido.url)?'Vista previa de la VERSIÓN PULIDA. ':''}Así se verá el video en la página; Facebook lo procesa unos minutos después de publicar. El texto de la publicación va debajo del video.</small>`:''}
        </div>
      </div>`)}
      ${tab('agente', `<div id="rd_agente"></div>`)}
      ${tab('historial', `<div class="row"><b>Publicaciones hechas desde la torre y por el agente</b>${hist}</div>`)}
      ${tab('conexiones', `<div class="row" style="padding:12px 14px;border:1px solid var(--border);border-radius:14px"><b>📘 Página de Facebook</b><div style="margin-top:6px">${estadoFb}</div>${tokenCaja}
          <details class="row" style="margin-top:10px"><summary style="cursor:pointer;font-weight:700">Cómo conectar la página (una sola vez)</summary>
            <ol style="margin:8px 0 0 18px;line-height:1.6">
              <li>Entra a <b>developers.facebook.com</b> con la cuenta que administra la página Pichangol → <b>Mis apps → Crear app</b> (tipo Empresa). Puede quedarse en <b>modo desarrollo</b>: los administradores de la app pueden publicar en sus propias páginas sin revisión de Meta.</li>
              <li>En la app: <b>Herramientas → Explorador de la API Graph</b>. Elige la app, en "Usuario o página" selecciona <b>Obtener token de acceso a la página</b> → marca la página Pichangol y los permisos <code>pages_manage_posts</code>, <code>pages_read_engagement</code>, <code>pages_show_list</code> → Generar. <b>Tiene que ser el token de la PÁGINA</b> (en el desplegable debe quedar elegida "Pichangol", no tu nombre): con un token de usuario Facebook responde <i>"(#200) publish_actions… deprecated"</i>. Si pegas uno de usuario, la torre intenta obtener el de página sola, pero igual necesita que hayas marcado <code>pages_manage_posts</code>.</li>
              <li>Convierte ese token en uno de LARGA duración: <b>Herramientas → Depurador de tokens de acceso</b> → pega el token → "Extender token de acceso". Un token de PÁGINA obtenido desde un token de usuario extendido no caduca.</li>
              <li>Copia el <b>ID de la página</b> (Configuración de la página → Información de la página) y ponlo en Railway como <code>FB_PAGE_ID</code>. El token pégalo arriba en <b>🔑 Token de Facebook</b> (la torre lo extiende y guarda el de la página, que no vence) o, si prefieres, en Railway como <code>FB_PAGE_TOKEN</code>. <b>No lo pegues en el chat ni en el repo.</b></li>
            </ol></details></div>
        <div class="row" style="margin-top:12px;padding:12px 14px;border:1px solid var(--border);border-radius:14px"><b>📷 Google Fotos · biblioteca de marca</b><div id="rd_biblioteca_con" style="margin-top:6px"></div></div>
        <div class="row" style="margin-top:12px;padding:12px 14px;border:1px solid var(--border);border-radius:14px"><b>🎵 Mi música · carpeta de Google Drive</b><div id="rd_musica_con" style="margin-top:6px"></div></div>
        <div class="row" style="margin-top:12px;font-size:12.5px;color:var(--muted)">Motores de este ambiente: redactor IA ${ia.disponible===false?'<b style="color:#8a5a00">apagado (sin ANTHROPIC_API_KEY)</b>':'<b style="color:var(--green)">activo</b>'} · pulido de video ${(redes.pulido||{}).disponible===false?'<b style="color:#8a5a00">sin FFmpeg</b>':'<b style="color:var(--green)">activo</b>'} · subtítulos Whisper ${(redes.pulido||{}).subtitulos===false?'<b style="color:#8a5a00">apagados (sin OPENAI_API_KEY)</b>':'<b style="color:var(--green)">activos</b>'}.</div>`)}
    </div>`;
  const set=(id,v)=>{ const el=document.getElementById(id); if(el && v!==undefined && v!==null && v!=='') el.value=v; };
  set('rd_titulo',prev.t); set('rd_sub',prev.s); set('rd_texto',prev.x); set('rd_etq',prev.e); set('rd_pie',prev.p); set('rd_formato', prev.f || redesSel.formato); set('rd_tema', prev.tema);
  ['rd_titulo','rd_sub','rd_etq','rd_pie'].forEach(id=>{ const el=document.getElementById(id); if(el) el.addEventListener('input', autoPrevRedes); });
  const fm=document.getElementById('rd_formato'); if(fm) fm.addEventListener('change', ()=>{ redesSel.formato=fm.value; autoPrevRedes(); });
  renderAgente(); renderBiblioteca(); renderMusica();
}
function cambiarLocalRedes(id){
  // Cambiar de local suelta las fotos del bucket del local anterior, pero CONSERVA las subidas
  // desde la computadora; si no queda ninguna, la vista previa se limpia (antes quedaba una
  // imagen vieja en pantalla y publicar fallaba con "Elige al menos una foto").
  redesSel.cancha = id || '';
  redesSel.fotos = redesSel.fotos.filter(u=>u.startsWith('data:'));
  if(!redesSel.fotos.length){ redesSel.img = ''; redesSel.ext = ''; }
  renderRedes(); aplicarPlantilla();
}
function toggleFotoRedes(u, on){
  const i = redesSel.fotos.indexOf(u);
  if(on && i<0){ if(redesSel.fotos.length >= (redes.max_fotos||4)){ alert('Máximo '+(redes.max_fotos||4)+' fotos.'); renderRedes(); return; } redesSel.fotos.push(u); }
  if(!on && i>=0) redesSel.fotos.splice(i,1);
  if(!redesSel.fotos.length){ redesSel.img = ''; redesSel.ext = ''; }
  const g = id => (document.getElementById(id)||{}).value || '';
  const t=g('rd_titulo'), s=g('rd_sub'), x=g('rd_texto'), e=g('rd_etq'), pie=g('rd_pie'); redesSel.formato = g('rd_formato') || redesSel.formato;
  renderRedes();
  const p = (id,v)=>{ const el=document.getElementById(id); if(el && v) el.value=v; };
  p('rd_titulo',t); p('rd_sub',s); p('rd_texto',x); p('rd_etq',e); p('rd_pie',pie);
  autoPrevRedes();
}
function quitarSubidaRedes(i){
  const subidas = redesSel.fotos.filter(u=>u.startsWith('data:')); const u = subidas[i]; if(!u) return;
  toggleFotoRedes(u, false);
}
function subirFotosRedes(inp){
  const files = Array.from(inp.files||[]); inp.value='';
  const max = redes.max_fotos||4, libres = max - redesSel.fotos.length;
  if(libres <= 0){ alert('Ya tienes '+max+' fotos elegidas. Quita alguna para subir otra.'); return; }
  if(files.length > libres) alert('Solo entran '+libres+' foto(s) más (máximo '+max+' por publicación). Se toman las primeras.');
  const msgUp = document.getElementById('rd_msg'); if(msgUp) msgUp.innerHTML = '<span class="rd-spin chico"></span> Preparando '+Math.min(files.length, libres)+' foto(s)…';
  files.slice(0, libres).forEach(f=>{ const img = new Image(), url = URL.createObjectURL(f); img.onload = ()=>{ const M=1600,k=Math.min(1,M/Math.max(img.width,img.height)); const cv=document.createElement('canvas'); cv.width=Math.round(img.width*k); cv.height=Math.round(img.height*k); cv.getContext('2d').drawImage(img,0,0,cv.width,cv.height); URL.revokeObjectURL(url); toggleFotoRedes(cv.toDataURL('image/jpeg',0.86), true); }; img.onerror = ()=>{ URL.revokeObjectURL(url); alert('No se pudo leer "'+f.name+'".'); }; img.src=url; });
}
async function guardarTokenRedes(){
  const inp = document.getElementById('rd_token'), msg = document.getElementById('rd_token_msg'), btn = document.getElementById('rd_token_btn');
  const tok = (inp.value||'').trim(); if(!tok){ msg.innerHTML='<span style="color:var(--rojo)">Pega el token primero.</span>'; return; }
  btn.disabled = true; msg.innerHTML = '<span class="rd-spin chico"></span> Verificando con Facebook y obteniendo el token de la página…';
  try{
    const r = await fetch('/admin/api/redes/pichangol/token',{method:'POST',headers:headers(),body:JSON.stringify({token:tok})});
    const j = await r.json().catch(()=>({}));
    if(r.status===401){ salir(); return; }
    if(r.ok && j.ok){ inp.value=''; toast('Token guardado'); redes.facebook = j.facebook || redes.facebook; renderRedes(); const m2=document.getElementById('rd_token_msg'); if(m2) m2.innerHTML = `<span style="color:var(--green);font-weight:700">✓ Listo.</span> Era un token de ${j.tipo==='pagina'?'página':'usuario'}${j.derivado?' → se obtuvo el de la página':''}${j.extendido?' (extendido a 60 días antes)':''}; ${j.vence?'vence el '+new Date(j.vence*1000).toLocaleDateString('es-PE'):'no vence'}.`; }
    else msg.innerHTML = `<span style="color:var(--rojo)">${esc(j.detail||'No se pudo guardar')}</span>`;
  }catch(e){ msg.innerHTML = '<span style="color:var(--rojo)">Error de red.</span>'; }
  btn.disabled = false;
}
async function olvidarTokenRedes(){
  if(!confirm('¿Olvidar el token guardado en la torre? Volverá a usarse solo el de Railway.')) return;
  const r = await fetch('/admin/api/redes/pichangol/token/olvidar',{method:'POST',headers:headers()});
  const j = await r.json().catch(()=>({})); if(j.facebook) redes.facebook = j.facebook; renderRedes();
}
function ENFOQUE_NAME(k){ return ENFOQUE_NOMBRE[k] || k || ''; }
async function redactarRedes(otra){
  // Redacta con IA (o banco de variantes) título, subtítulo, etiqueta y texto; "otra versión" manda lo ya generado para no repetirlo.
  if(redesSel.redactando) return;
  redesSel.redactando = true; redesSel.plantilla = 'ia';
  const tema = (document.getElementById('rd_tema')||{}).value || '';
  renderRedes(); botonesRedes('componiendo');
  try{
    const r = await fetch('/admin/api/redes/pichangol/redactar',{method:'POST',headers:headers(),body:JSON.stringify({cancha_id:redesSel.cancha, tono:redesSel.tono, enfoque:redesSel.enfoque, tema:tema, evitar:redesSel.evitar.slice(-8)})});
    if(r.status===401){ salir(); return; }
    const j = await r.json().catch(()=>({}));
    redesSel.redactando = false;
    if(r.ok && j.ok){
      redesSel.ia = {enfoque:j.enfoque, fuente:j.fuente}; redesSel.evitar.push(j.texto);
      renderRedes();
      const p=(id,v)=>{ const el=document.getElementById(id); if(el) el.value = v||''; };
      p('rd_titulo', j.titulo); p('rd_sub', j.subtitulo); p('rd_etq', j.etiqueta); p('rd_texto', j.texto); p('rd_tema', tema);
      if(otra) toast('Nueva versión lista');
    } else { renderRedes(); const e=document.getElementById('rd_ia_estado'); if(e) e.innerHTML = `<span style="color:var(--rojo)">${esc(j.detail||'No se pudo redactar')}</span>`; }
  }catch(e){ redesSel.redactando = false; renderRedes(); const el=document.getElementById('rd_ia_estado'); if(el) el.innerHTML = '<span style="color:var(--rojo)">No se pudo redactar (red).</span>'; }
  autoPrevRedes();
}
async function aplicarPlantilla(){
  if(redesSel.plantilla==='ia'){ redesSel.ia = null; await redactarRedes(false); return; }
  redesSel.ia = null;
  const estP = document.getElementById('rd_prev_estado'); if(estP) estP.innerHTML = '<span class="rd-spin chico"></span> aplicando plantilla…';
  const r = await fetch('/admin/api/redes/pichangol/plantilla',{method:'POST',headers:headers(),body:JSON.stringify({plantilla:redesSel.plantilla,cancha_id:redesSel.cancha})});
  const j = await r.json().catch(()=>({}));
  if(j.ok){ const t=document.getElementById('rd_titulo'); if(t){ t.value=j.titulo; document.getElementById('rd_sub').value=j.subtitulo; document.getElementById('rd_texto').value=j.texto; } }
  renderRedes(); autoPrevRedes();
}
let rdTimer = null;
function veloPrev(on, texto){
  const prev = document.getElementById('rd_prev'); if(!prev) return;
  prev.querySelectorAll('.rd-velo').forEach(v=>v.remove());
  prev.querySelectorAll('img,video').forEach(i=>i.classList.toggle('opaca', !!on));
  if(on){ const v=document.createElement('div'); v.className='rd-velo'; v.innerHTML='<span class="rd-spin"></span><div>'+esc(texto||'Componiendo la pieza…')+'</div><small>Fotos reales + logo + texto · unos segundos</small>'; prev.appendChild(v); if(!prev.querySelector('img')) prev.style.minHeight='360px'; }
}
function botonesRedes(ocupado){
  const b = id => document.getElementById(id);
  const pub = b('rd_publicar'), des = b('rd_descargar'), pre = b('rd_prev_btn');
  const puliendo = !!(redesSel.video && redesSel.video.pulido && (redesSel.video.pulido.estado==='transcribiendo' || redesSel.video.pulido.estado==='renderizando'));
  const listo = redesSel.video ? (redesSel.video.estado==='listo' && !!redesSel.video.id && !puliendo) : !!redesSel.img;
  if(pub){ if(ocupado) pub.dataset.txt = pub.dataset.txt || pub.innerHTML; if(!pub.dataset.bloqueado){ pub.disabled = !!ocupado || !listo; pub.title = pub.disabled ? (ocupado ? 'Espera a que termine…' : (redesSel.video ? 'Espera a que termine de subir el video' : 'Primero arma la vista previa')) : ''; } pub.innerHTML = ocupado==='publicando' ? '<span class="rd-spin blanco"></span> Publicando…' : (pub.dataset.txt || pub.innerHTML); }
  if(des) des.disabled = !!ocupado || !redesSel.img || !!redesSel.video;
  const otra = b('rd_otra'); if(otra) otra.disabled = ocupado==='publicando' || redesSel.redactando;
  if(pre) pre.disabled = !!ocupado;
}
function autoPrevRedes(){ clearTimeout(rdTimer); if(redesSel.video){ botonesRedes(false); return; } if(!redesSel.fotos.length) return; veloPrev(true, 'Preparando la vista previa…'); botonesRedes('componiendo'); rdTimer = setTimeout(()=>previsualizarRedes(true), 700); }
function cuerpoRedes(conImagen){ const g=id=>(document.getElementById(id)||{}).value||''; const c = {fotos:redesSel.fotos, titulo:g('rd_titulo'), subtitulo:g('rd_sub'), pie:g('rd_pie'), etiqueta:g('rd_etq'), formato:g('rd_formato')||redesSel.formato, texto:g('rd_texto'), plantilla:redesSel.plantilla, cancha_id:redesSel.cancha, video_id:(redesSel.video&&redesSel.video.id)||'', enfoque:(redesSel.ia&&redesSel.ia.enfoque)||'', fuente:(redesSel.ia&&redesSel.ia.fuente)||(redesSel.plantilla==='libre'?'manual':'plantilla'), usar_pulido: !!(redesSel.video&&redesSel.video.pulido&&redesSel.video.pulido.usar&&redesSel.video.pulido.url)}; if(conImagen && !c.video_id && redesSel.img) c.imagen = redesSel.img; return c; }
// ── Biblioteca de marca + Google Fotos (Picker API) ──
let bib = null, bibOcupado = '', bibSesion = null, bibTimer = null, bibAbierta = false;
let mus = null, musOcupado = '', musCarpetas = null;
async function cargarBiblioteca(){
  try{ const r = await fetch('/admin/api/redes/biblioteca',{headers:headers()}); if(r.ok) bib = await r.json(); }catch(e){}
  renderBiblioteca();
}
function renderBiblioteca(){
  // Tres lugares: fotos (paso 1 · Fotos), videos (paso 1 · Video) y la conexión/gestión (pestaña Conexiones).
  const bF = document.getElementById('rd_biblioteca'), bV = document.getElementById('rd_biblioteca_videos'), bC = document.getElementById('rd_biblioteca_con');
  if(!bF && !bV && !bC) return;
  const cargando = '<div class="rd-cargando" style="padding:8px 4px"><span class="rd-spin chico"></span> Cargando biblioteca…</div>';
  if(!bib){ [bF,bV,bC].forEach(b=>{ if(b) b.innerHTML = cargando; }); return; }
  const items = bib.items || [], fotos = items.filter(x=>x.tipo!=='video'), videos = items.filter(x=>x.tipo==='video');
  const enUso = new Set(redesSel.fotos);
  const quitar = it => `<button type="button" title="Quitar de la biblioteca" onclick="bibQuitar('${it.id}')" style="position:absolute;top:6px;right:6px;width:22px;height:22px;border-radius:50%;border:0;background:rgba(0,0,0,.65);color:#fff;font-weight:700;cursor:pointer;line-height:1">✕</button>`;
  const tFoto = (it, conQuitar) => `<div style="position:relative;width:118px"><label style="cursor:pointer;display:block"><img src="${esc(it.url)}" loading="lazy" style="width:118px;height:118px;object-fit:cover;border-radius:12px;border:3px solid ${enUso.has(it.url)?'var(--green)':'transparent'};display:block"><input type="checkbox" ${enUso.has(it.url)?'checked':''} onchange="toggleFotoRedes('${esc(it.url)}',this.checked)" style="position:absolute;top:8px;left:8px;width:18px;height:18px"></label><small style="display:block;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${it.usos?it.usos+' uso(s)':'sin usar'}</small>${conQuitar?quitar(it):''}</div>`;
  const tVideo = (it, conQuitar) => `<div style="position:relative;width:118px"><div style="width:118px;height:118px;border-radius:12px;background:#0A1B3D;display:flex;align-items:center;justify-content:center;color:#fff;font-size:28px">▶</div><small style="display:block;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis" title="${esc(it.nombre||'video')}">${esc(it.nombre||'video')}${it.usos?' · '+it.usos+' uso(s)':''}</small>
        ${conQuitar?quitar(it):`<button type="button" class="btn-ap" style="width:100%;margin-top:3px;padding:6px;font-size:12px" onclick="bibUsarVideo('${it.id}')" ${bibOcupado?'disabled':''}>${bibOcupado==='video:'+it.id?'<span class="rd-spin blanco"></span>':'Usar este video'}</button>`}</div>`;
  const elegir = `<button type="button" class="btn-sec" onclick="bibElegir()" ${bibOcupado?'disabled':''}>${bibOcupado==='elegir'?'<span class="rd-spin blanco"></span> Esperando tu selección en Google Fotos…':'📷 Elegir en Google Fotos'}</button>${bibOcupado==='elegir'?' <button type="button" class="btn-sec" onclick="bibCancelarEspera()">Cancelar</button>':''}`;
  const sinConexion = !bib.credenciales
    ? `<small style="color:#8a5a00">Para conectar Google Fotos faltan <code>GOOGLE_WEB_CLIENT_SECRET</code> (secreto del mismo cliente OAuth "Aplicación web" del login) en Railway y, en Google Cloud, habilitar la <b>Google Photos Picker API</b> y registrar la URI de redirección <code>${esc(bib.redirect_uri||'(PUBLIC_BASE_URL)/admin/api/redes/biblioteca/google/callback')}</code>.</small>`
    : `<button type="button" class="btn-ap" onclick="bibConectar()">🔗 Conectar Google Fotos</button> <small style="color:var(--muted)">Se abre Google para autorizar; solo se leen las fotos y videos que TÚ elijas en el selector.</small>`;
  const msg = '<div class="rd-bib-msg" style="margin-top:6px;font-size:12.5px"></div>';
  if(bF) bF.innerHTML = !bib.conectado ? `<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">${sinConexion}</div>${msg}`
    : `<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap"><small style="color:var(--muted)">Marca las fotos que entran a esta publicación.</small><span style="flex:1"></span>${elegir}</div>${msg}
       ${fotos.length?`<div style="display:flex;gap:10px;flex-wrap:wrap;margin-top:8px">${fotos.map(it=>tFoto(it,false)).join('')}</div>`:'<small style="display:block;margin-top:8px;color:var(--muted)">Aún no hay fotos en la biblioteca: pulsa "Elegir en Google Fotos".</small>'}`;
  if(bV) bV.innerHTML = !bib.conectado ? `<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">${sinConexion}</div>${msg}`
    : `<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap"><small style="color:var(--muted)">Elige un video: pasa al paso 2 para pulirlo con música.</small><span style="flex:1"></span>${elegir}</div>${msg}
       ${videos.length?`<div style="display:flex;gap:10px;flex-wrap:wrap;margin-top:8px">${videos.map(it=>tVideo(it,false)).join('')}</div>`:'<small style="display:block;margin-top:8px;color:var(--muted)">Aún no hay videos en la biblioteca: pulsa "Elegir en Google Fotos" y marca uno.</small>'}`;
  if(bC) bC.innerHTML = `<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">${!bib.conectado ? sinConexion : `<span style="color:var(--green);font-weight:700">● Google Fotos conectado</span> <small style="color:var(--muted)">${esc(bib.cuenta||'')}</small> ${elegir} <button type="button" class="btn-sec" onclick="bibDesconectar()" ${bibOcupado?'disabled':''}>Desconectar</button>`}</div>
      ${!bib.storage?'<small style="color:var(--rojo)">Sin SUPABASE_URL/ANON_KEY en Railway no se pueden guardar los archivos importados.</small>':''}${msg}
      <small style="display:block;margin-top:8px;color:var(--muted)">Lo que eliges en Google Fotos se copia a la biblioteca de Pichangol (${bib.fotos||0} fotos · ${bib.videos||0} videos). El agente 24×7 publica con estas fotos y, jueves a sábado, con un video que no haya usado en 14 días. Con ✕ se quita de la biblioteca y de Storage.</small>
      ${items.length?`<div style="display:flex;gap:10px;flex-wrap:wrap;margin-top:8px">${items.map(it=>it.tipo==='video'?tVideo(it,true):tFoto(it,true)).join('')}</div>`:''}`;
}
async function bibConectar(){
  try{ const r = await fetch('/admin/api/redes/biblioteca/google/autorizar',{headers:headers()}); const j = await r.json().catch(()=>({}));
    if(r.ok && j.ok){ window.open(j.url, '_blank', 'noopener'); const m=({set innerHTML(h){ bibMsg(h); }}); if(m) m.innerHTML='<span class="rd-spin chico"></span> Autoriza en la pestaña de Google y vuelve aquí; la biblioteca se actualiza sola.'; let n=0; const t=setInterval(async()=>{ await cargarBiblioteca(); n++; if((bib&&bib.conectado)||n>60) clearInterval(t); }, 3000); }
    else alert(j.detail||'No se pudo iniciar la conexión'); }catch(e){ alert('Error de red'); }
}
async function bibDesconectar(){
  if(!confirm('¿Desconectar Google Fotos? Lo ya importado se queda en la biblioteca.')) return;
  await fetch('/admin/api/redes/biblioteca/google/desconectar',{method:'POST',headers:headers()}); cargarBiblioteca();
}
async function bibElegir(){
  bibOcupado='elegir'; renderBiblioteca();
  try{ const r = await fetch('/admin/api/redes/biblioteca/google/sesion',{method:'POST',headers:headers()}); const j = await r.json().catch(()=>({}));
    if(!(r.ok && j.ok)){ alert(j.detail||'No se pudo abrir el selector'); bibOcupado=''; renderBiblioteca(); return; }
    bibSesion = j.id; window.open(j.pickerUri, '_blank', 'noopener');
    const m=({set innerHTML(h){ bibMsg(h); }}); if(m) m.innerHTML='<span class="rd-spin chico"></span> Elige las fotos y videos en la pestaña de Google Fotos y pulsa "Listo" allá. Cuando termines, se importan solos.';
    bibTimer = setTimeout(bibSondear, Math.max(2000, j.poll_ms||3000));
  }catch(e){ alert('Error de red'); bibOcupado=''; renderBiblioteca(); }
}
async function bibSondear(){
  if(!bibSesion) return;
  try{ const r = await fetch('/admin/api/redes/biblioteca/google/sesion/'+encodeURIComponent(bibSesion),{headers:headers()}); const j = await r.json().catch(()=>({}));
    if(!r.ok){ const m=({set innerHTML(h){ bibMsg(h); }}); if(m) m.innerHTML=`<span style="color:var(--rojo)">${esc(j.detail||'Error')}</span>`; bibOcupado=''; bibSesion=null; renderBiblioteca(); return; }
    if(!j.listo){ bibTimer = setTimeout(bibSondear, 3000); return; }
    bibSesion=null; bibOcupado=''; await cargarBiblioteca();
    const m=({set innerHTML(h){ bibMsg(h); }}); if(m) m.innerHTML = `<span style="color:var(--green);font-weight:700">✓ Importados ${j.importados}</span>${j.omitidos?` · omitidos ${j.omitidos}`:''}${(j.detalle||[]).length?'<br><small style="color:var(--muted)">'+j.detalle.map(esc).join('<br>')+'</small>':''}`;
    toast('Biblioteca actualizada');
  }catch(e){ bibTimer = setTimeout(bibSondear, 4000); }
}
function bibCancelarEspera(){ clearTimeout(bibTimer); bibSesion=null; bibOcupado=''; renderBiblioteca(); }
async function bibQuitar(id){
  if(!confirm('¿Quitar este archivo de la biblioteca? Se borra también de Storage.')) return;
  const r = await fetch('/admin/api/redes/biblioteca/'+id+'/quitar',{method:'POST',headers:headers()}); if(r.ok){ const it=(bib.items||[]).find(x=>x.id===id); if(it && it.url){ const i=redesSel.fotos.indexOf(it.url); if(i>=0) redesSel.fotos.splice(i,1); } await cargarBiblioteca(); renderRedes(); }
}
async function bibUsarVideo(id){
  bibOcupado='video:'+id; renderBiblioteca();
  try{ const r = await fetch('/admin/api/redes/pichangol/video/desde-biblioteca/'+id,{method:'POST',headers:headers()}); const j = await r.json().catch(()=>({}));
    if(r.ok && j.ok){
      if(redesSel.video && redesSel.video.url && redesSel.video.url.startsWith('blob:')) URL.revokeObjectURL(redesSel.video.url);
      redesSel.video = {nombre:j.nombre, bytes:j.bytes, url:j.url, estado:'listo', pct:100, id:j.video_id, dur:0, pulido:null};
      redesUI.tipo='video'; redesUI.paso=2; toast('Video listo: elige la música y púlelo'); renderRedes(); botonesRedes(false);
    } else alert(j.detail||'No se pudo traer el video'); }catch(e){ alert('Error de red'); }
  bibOcupado=''; renderBiblioteca();
}
// ── Mi música: pistas propias desde una carpeta de Google Drive (Spotify no da audio y Facebook silencia música comercial) ──
async function cargarMusica(){
  const primera = !mus;
  try{ const r = await fetch('/admin/api/redes/musica',{headers:headers()}); if(r.ok) mus = await r.json(); }catch(e){}
  if(primera && mus && document.getElementById('redesPanel')) renderRedes(); else renderMusica();   // la 1.ª carga pinta la píldora y el selector de pista
}
function musMsg(h){ const m=document.getElementById('rd_mus_msg'); if(m) m.innerHTML=h; }
function musInicioSugerido(id){ const t = (mus&&mus.items||[]).find(x=>x.id===id); return t ? (Number(t.inicio_sugerido)||0) : 0; }
function pulDesdeReproductor(){
  const a = document.querySelector('.rd-paso[data-paso="2"] audio'); const pl = redesSel.video && redesSel.video.pulido; if(!pl) return;
  if(!a){ alert('Elige una pista concreta (no "cualquiera") para usar el reproductor.'); return; }
  pl.opciones.musica_desde = Math.round((a.currentTime||0)*2)/2; renderRedes(); toast('La pista arrancará en el segundo '+pl.opciones.musica_desde);
}
let fvOcupado = false;
async function fotosAVideo(){
  if(!redesSel.fotos.length){ alert('Elige al menos una foto.'); return; }
  const formato = (document.getElementById('rd_fv_formato')||{}).value||'vertical', segundos = Number((document.getElementById('rd_fv_seg')||{}).value||2.8);
  fvOcupado = true; renderRedes();
  try{
    const r = await fetch('/admin/api/redes/pichangol/video/desde-fotos',{method:'POST',headers:headers(),body:JSON.stringify({fotos:redesSel.fotos, formato, segundos})});
    const j = await r.json().catch(()=>({}));
    if(r.status===401){ salir(); return; }
    if(!(r.ok && j.ok)){ fvOcupado=false; renderRedes(); alert(j.detail||'No se pudo armar el video'); return; }
    const ra = await fetch('/admin/api/redes/pichangol/video/'+encodeURIComponent(j.video_id)+'/archivo?cual=original',{headers:headers()});
    const url = ra.ok ? URL.createObjectURL(await ra.blob()) : '';
    if(redesSel.video && redesSel.video.url && redesSel.video.url.startsWith('blob:')) URL.revokeObjectURL(redesSel.video.url);
    redesSel.video = {nombre:j.nombre, bytes:j.bytes, url, estado:'listo', pct:100, id:j.video_id, dur:j.duracion, pulido:null};
    redesUI.tipo='video'; redesUI.paso=2; fvOcupado=false; toast('Video armado: '+j.duracion+' s · elige la música y púlelo'); renderRedes(); botonesRedes(false);
  }catch(e){ fvOcupado=false; renderRedes(); alert('Error de red'); }
}
function musOpciones(sel){
  // Pistas agrupadas por subcarpeta de Drive (= género) + "cualquiera de ese género" (la torre rota la menos usada).
  const items = (mus&&mus.items)||[]; if(!items.length) return '';
  const grupos = {}; items.forEach(t=>{ const c=t.carpeta||''; (grupos[c]=grupos[c]||[]).push(t); });
  const opt = (v,txt)=>`<option value="${esc(v)}"${sel===v?' selected':''}>${txt}</option>`;
  let h = Object.keys(grupos).length>1 ? opt('cualquiera','🎲 Cualquiera de mis pistas (rota la menos usada)') : '';
  Object.keys(grupos).sort((a,b)=>a.localeCompare(b)).forEach(c=>{ const lista = grupos[c].map(t=>opt(t.id,'🎵 '+esc(t.nombre))).join('');
    h += c ? `<optgroup label="📁 ${esc(c)}">${opt('carpeta:'+c,'🎲 Cualquiera de '+esc(c))}${lista}</optgroup>` : `<optgroup label="📁 (raíz de la carpeta)">${lista}</optgroup>`; });
  return h;
}
function renderMusica(){
  const box = document.getElementById('rd_musica_con'); if(!box) return;
  if(!mus){ box.innerHTML = '<div class="rd-cargando" style="padding:8px 4px"><span class="rd-spin chico"></span> Cargando Mi música…</div>'; return; }
  const items = mus.items || [], c = mus.carpeta || {};
  const mb = b => b < 1048576 ? Math.max(1, Math.round(b/1024))+' KB' : (b/1048576).toFixed(1)+' MB';
  let cab;
  if(!mus.credenciales) cab = `<small style="color:#8a5a00">Faltan las credenciales de Google en Railway (las mismas de Google Fotos).</small>`;
  else if(!mus.conectado) cab = `<button type="button" class="btn-ap" onclick="musConectar()">🔗 Conectar Google Drive</button> <small style="color:var(--muted)">${mus.google?'Google Fotos ya está conectado; falta autorizar la lectura de Drive (solo lectura). ':''}Se abre Google para autorizar; la torre solo LEE la carpeta que elijas.</small>`;
  else cab = `<span style="color:var(--green);font-weight:700">● Google Drive conectado</span> <small style="color:var(--muted)">${esc(mus.cuenta||'')}</small>`;
  const carpeta = !mus.conectado ? '' : `<div style="margin-top:10px;padding:10px 12px;border-radius:12px;background:#FAFBFC;border:1px solid var(--border)">
      <div style="font-size:12.5px;font-weight:700">Carpeta de música ${c.id?`<span style="color:var(--green)">· 📁 ${esc(c.nombre||c.id)}</span>`:'<span style="color:#8a5a00">· sin elegir</span>'}</div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:6px;align-items:center">
        <input id="rd_mus_enlace" placeholder="Pega el enlace de la carpeta de Drive (…/drive/folders/…)" style="flex:1;min-width:260px;padding:8px 10px;border:1px solid var(--border);border-radius:10px;font-family:inherit;font-size:13px">
        <button type="button" class="btn-sec" onclick="musCarpeta()" ${musOcupado?'disabled':''}>Usar esta carpeta</button>
        <span style="color:var(--muted);font-size:12.5px">o</span>
        <input id="rd_mus_q" placeholder="buscar carpeta por nombre" style="min-width:180px;padding:8px 10px;border:1px solid var(--border);border-radius:10px;font-family:inherit;font-size:13px" onkeydown="if(event.key==='Enter') musBuscar()">
        <button type="button" class="btn-sec" onclick="musBuscar()" ${musOcupado?'disabled':''}>🔎 Buscar</button></div>
      ${musCarpetas?`<div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:8px">${musCarpetas.length?musCarpetas.map(f=>`<button type="button" class="rd-sub${c.id===f.id?' on':''}" onclick="musCarpeta('${f.id}')">📁 ${esc(f.nombre)}</button>`).join(''):'<small style="color:var(--muted)">No se encontraron carpetas con ese nombre.</small>'}</div>`:''}
      <small style="display:block;margin-top:6px;color:var(--muted)">Sube ahí MP3, M4A, WAV, OGG, AAC o FLAC con derechos de uso (hasta ${mus.max_mb||30} MB cada uno) y pulsa Sincronizar. Se leen también las SUBCARPETAS (Cumbia, Rock…) y quedan como género para elegir. La torre copia las pistas a Storage; lo que borres de la carpeta desaparece al sincronizar.</small></div>`;
  const sync = !(mus.conectado && c.id) ? '' : `<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-top:10px"><button type="button" class="btn-ap" onclick="musSincronizar()" ${musOcupado?'disabled':''}>${musOcupado==='sync'?'<span class="rd-spin blanco"></span> Sincronizando…':'🔄 Sincronizar con Drive'}</button><small style="color:var(--muted)">${mus.sync_en?'última sincronización '+new Date(mus.sync_en*1000).toLocaleString('es-PE'):'aún no se ha sincronizado'} · ${items.length} pista(s)</small></div>`;
  const fila = t => `<div style="display:flex;gap:10px;align-items:center;padding:8px 10px;border-bottom:1px solid #F0F2F4"><audio controls preload="none" src="${esc(t.url)}" style="height:30px;width:230px"></audio><div style="flex:1;min-width:160px"><b style="font-size:13px">${esc(t.nombre)}</b><br><small style="color:var(--muted)">${mb(t.bytes||0)} · ${t.usos?t.usos+' uso(s)':'sin usar'}</small></div><button type="button" class="btn-sec" title="Quitar de Mi música (no toca tu Drive)" onclick="musQuitar('${t.id}')">✕</button></div>`;
  const grupos = {}; items.forEach(t=>{ const k=t.carpeta||''; (grupos[k]=grupos[k]||[]).push(t); });
  const lista = items.length ? `<div style="margin-top:8px;border:1px solid var(--border);border-radius:12px;overflow:hidden">${Object.keys(grupos).sort((a,b)=>a.localeCompare(b)).map(k=>`<div style="padding:6px 10px;background:#FAFBFC;font-size:12.5px;font-weight:700;border-bottom:1px solid #F0F2F4">📁 ${k?esc(k):'(raíz de la carpeta)'} <small style="color:var(--muted);font-weight:400">· ${grupos[k].length} pista(s)</small></div>${grupos[k].map(fila).join('')}`).join('')}</div>` : (mus.conectado && c.id ? '<small style="display:block;margin-top:8px;color:var(--muted)">Todavía no hay pistas: sube audios a la carpeta (o a sus subcarpetas) y sincroniza.</small>' : '');
  box.innerHTML = `<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">${cab}</div><div id="rd_mus_msg" style="margin-top:6px;font-size:12.5px"></div>${carpeta}${sync}${lista}
    <small style="display:block;margin-top:8px;color:var(--muted)">Las pistas aparecen en el paso Estilo de cada video ("Pista") y el agente 24×7 rota la menos usada. Spotify no sirve: su API no entrega el audio y Facebook silencia la música comercial.</small>`;
}
async function musConectar(){
  try{ const r = await fetch('/admin/api/redes/musica/google/autorizar',{headers:headers()}); const j = await r.json().catch(()=>({}));
    if(r.ok && j.ok){ window.open(j.url, '_blank', 'noopener'); musMsg('<span class="rd-spin chico"></span> Autoriza Google Drive en la pestaña de Google y vuelve aquí.'); let n=0; const t=setInterval(async()=>{ await cargarMusica(); await cargarBiblioteca(); n++; if((mus&&mus.conectado)||n>60) clearInterval(t); }, 3000); }
    else alert(j.detail||'No se pudo iniciar la conexión'); }catch(e){ alert('Error de red'); }
}
async function musBuscar(){
  const q = (document.getElementById('rd_mus_q')||{}).value||''; musOcupado='buscar'; renderMusica();
  try{ const r = await fetch('/admin/api/redes/musica/carpetas?q='+encodeURIComponent(q),{headers:headers()}); const j = await r.json().catch(()=>({}));
    musOcupado=''; if(r.ok && j.ok){ musCarpetas = j.carpetas||[]; renderMusica(); const el=document.getElementById('rd_mus_q'); if(el) el.value=q; } else { renderMusica(); musMsg(`<span style="color:var(--rojo)">${esc(j.detail||'No se pudo buscar')}</span>`); }
  }catch(e){ musOcupado=''; renderMusica(); musMsg('<span style="color:var(--rojo)">Error de red.</span>'); }
}
async function musCarpeta(id){
  const enlace = id || (document.getElementById('rd_mus_enlace')||{}).value||''; if(!enlace.trim()){ musMsg('<span style="color:var(--rojo)">Pega el enlace de la carpeta o elige una de la lista.</span>'); return; }
  musOcupado='carpeta'; renderMusica();
  try{ const r = await fetch('/admin/api/redes/musica/carpeta',{method:'POST',headers:headers(),body:JSON.stringify({enlace})}); const j = await r.json().catch(()=>({}));
    musOcupado=''; if(r.ok && j.ok){ mus = {...mus, ...j, items: mus.items}; musCarpetas=null; renderMusica(); toast('Carpeta guardada: '+(j.carpeta.nombre||'')); musSincronizar(); }
    else { renderMusica(); musMsg(`<span style="color:var(--rojo)">${esc(j.detail||'No se pudo usar esa carpeta')}</span>`); }
  }catch(e){ musOcupado=''; renderMusica(); musMsg('<span style="color:var(--rojo)">Error de red.</span>'); }
}
async function musSincronizar(){
  musOcupado='sync'; renderMusica();
  try{ const r = await fetch('/admin/api/redes/musica/sincronizar',{method:'POST',headers:headers()}); const j = await r.json().catch(()=>({}));
    musOcupado=''; if(r.ok && j.ok){ mus = {...mus, ...j}; renderMusica(); renderRedes(); musMsg(`<span style="color:var(--green);font-weight:700">✓ ${j.nuevos} nueva(s) · ${j.actualizados} actualizada(s) · ${j.quitados} quitada(s)</span>${j.omitidos?` · ${j.omitidos} omitida(s)`:''}${(j.detalle||[]).length?'<br><small style="color:var(--muted)">'+j.detalle.map(esc).join('<br>')+'</small>':''}`); toast('Mi música sincronizada'); }
    else { renderMusica(); musMsg(`<span style="color:var(--rojo)">${esc(j.detail||'No se pudo sincronizar')}</span>`); }
  }catch(e){ musOcupado=''; renderMusica(); musMsg('<span style="color:var(--rojo)">Error de red.</span>'); }
}
async function musQuitar(id){
  if(!confirm('¿Quitar esta pista de Mi música? Tu archivo en Drive no se toca (si sigue en la carpeta, volverá al sincronizar).')) return;
  const r = await fetch('/admin/api/redes/musica/'+id+'/quitar',{method:'POST',headers:headers()}); const j = await r.json().catch(()=>({}));
  if(r.ok && j.ok){ mus.items = j.items; mus.pistas = j.items.length; if(redesSel.video&&redesSel.video.pulido&&redesSel.video.pulido.opciones.musica_pista===id) redesSel.video.pulido.opciones.musica_pista=''; renderRedes(); }
}
// ── Agente de marketing 24×7 (estratega + creativo + community manager de la página) ──
let agente = null, agOcupado = '', agImg = {}, agAbierto = null;
async function cargarAgente(){
  try{ const r = await fetch('/admin/api/redes/agente',{headers:headers()}); if(r.ok){ agente = await r.json(); } }catch(e){}
  renderAgente();
}
function renderAgente(){
  const box = document.getElementById('rd_agente'); if(!box) return;
  if(!agente){ box.innerHTML = '<div class="rd-cargando"><span class="rd-spin"></span> Cargando el agente de marketing…</div>'; return; }
  const c = agente.config, px = agente.proxima || {}, plan = c.plan || {};
  const inp = 'style="padding:8px 10px;border:1px solid var(--border);border-radius:10px;font-family:inherit;font-size:13px;background:#fff"';
  const horas = []; for(let h=5; h<=21; h++){ ['00','30'].forEach(m=>{ const v=(h<10?'0':'')+h+':'+m; horas.push(`<option value="${v}"${c.hora===v?' selected':''}>${v}</option>`); }); }
  if(!horas.some(o=>o.includes('selected'))) horas.unshift(`<option value="${esc(c.hora)}" selected>${esc(c.hora)}</option>`);
  const zonas = (agente.zonas||[]).map(z=>`<option value="${z}"${c.zona===z?' selected':''}>${z.replace('America/','')}</option>`).join('');
  const tonos = ['cercano','divertido','informativo','motivador'].map(t=>`<option value="${t}"${c.tono===t?' selected':''}>${t.charAt(0).toUpperCase()+t.slice(1)}</option>`).join('');
  const cuando = px.pendiente_hoy ? '<b style="color:#8a5a00">hoy, en el próximo minuto</b> (ya pasó la hora y aún no publicó)' : (px.local ? `<b>${esc(px.local)}</b>` : '—');
  const filas = (agente.dias||[]).map((d,i)=>{ const f = plan[String(i)]||{}; const esD = f.audiencia==='duenos';
    return `<tr><td style="padding:4px 6px;font-weight:700;text-transform:capitalize">${d}</td>
      <td style="padding:4px 6px"><select data-plan-aud="${i}" ${inp} onchange="renderAgentePlan()">${Object.entries(agente.audiencias||{}).map(([k,v])=>`<option value="${k}"${f.audiencia===k?' selected':''}>${esc(v)}</option>`).join('')}</select></td>
      <td style="padding:4px 6px"><select data-plan-enf="${i}" ${inp} ${esD?'disabled':''}>${esD?'<option value="duenos" selected>Para dueños de cancha</option>':(agente.enfoques_jugadores||[]).map(k=>`<option value="${k}"${f.enfoque===k?' selected':''}>${esc(ENFOQUE_NOMBRE[k]||k)}</option>`).join('')}</select></td></tr>`; }).join('');
  const bor = (agente.borradores||[]).map(b=>{ const ab = agAbierto===b.id; return `<div style="border:1px solid var(--border);border-radius:12px;padding:10px 12px;margin-top:8px;background:#fff">
      <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap"><b>${b.video_id?'🎬 ':''}${esc(b.titulo||'(sin título)')}</b><small style="color:var(--muted)">${esc(b.fecha||'')} · ${esc((agente.audiencias||{})[b.audiencia]||b.audiencia||'')} · ${esc(ENFOQUE_NOMBRE[b.enfoque]||b.enfoque||'')}${b.local?' · '+esc(b.local):''}${b.video_id?' · video con música ('+esc(b.video_nombre||'')+')':''}${b.fuente==='ia'?' · ✨ IA':''}</small>${b.motivo?`<small style="color:var(--rojo)">${esc(b.motivo)}</small>`:''}<span style="flex:1"></span><button type="button" class="btn-sec" onclick="agAbierto=${ab?'null':`'${b.id}'`};renderAgente();${ab?'':`agVerImagen('${b.id}')`}">${ab?'Cerrar':'👁️ Ver pieza'}</button></div>
      ${ab?`<div class="rd-grid" style="margin-top:8px"><div>
          <label style="font-size:12.5px;font-weight:700">Título en la imagen<input id="ag_t_${b.id}" value="${esc(b.titulo||'')}" ${inp} style="display:block;width:100%;margin-top:4px;padding:8px 10px;border:1px solid var(--border);border-radius:10px;font-family:inherit"></label>
          <label style="display:block;margin-top:6px;font-size:12.5px;font-weight:700">Subtítulo<input id="ag_s_${b.id}" value="${esc(b.subtitulo||'')}" style="display:block;width:100%;margin-top:4px;padding:8px 10px;border:1px solid var(--border);border-radius:10px;font-family:inherit"></label>
          <label style="display:block;margin-top:6px;font-size:12.5px;font-weight:700">Texto de la publicación<textarea id="ag_x_${b.id}" rows="7" style="display:block;width:100%;margin-top:4px;padding:8px 10px;border:1px solid var(--border);border-radius:10px;font-family:inherit;font-size:13px">${esc(b.texto||'')}</textarea></label>
          <div class="actions" style="margin-top:8px;flex-wrap:wrap">
            <button type="button" class="btn-sec" onclick="agEditar('${b.id}')" ${agOcupado?'disabled':''}>💾 Guardar cambios</button>
            <button type="button" class="btn-sec" onclick="agAccion('${b.id}','regenerar')" ${agOcupado?'disabled':''}>🔁 Otra versión</button>
            <button type="button" class="btn-sec" onclick="agAccion('${b.id}','descartar')" ${agOcupado?'disabled':''}>🗑 Descartar</button>
            <button type="button" class="btn-ap" onclick="agAccion('${b.id}','aprobar')" ${agOcupado||!agente.credenciales?'disabled':''}>${agOcupado==='aprobar:'+b.id?'<span class="rd-spin blanco"></span> Publicando…':'✅ Aprobar y publicar'}</button>
          </div></div>
          <div id="ag_img_${b.id}" style="border:1px dashed var(--border);border-radius:12px;min-height:240px;display:flex;align-items:center;justify-content:center;background:#fafafa;overflow:hidden">${agImg[b.id]?`<img src="${agImg[b.id]}" style="max-width:100%;max-height:60vh;display:block">`:'<span class="rd-spin"></span>'}</div></div>`:''}
    </div>`; }).join('') || '<small style="color:var(--muted)">No hay borradores pendientes.</small>';
  const log = (agente.corridas||[]).map(k=>`<div style="display:flex;gap:8px;align-items:center;padding:4px 0;border-bottom:1px solid #F0F2F4;font-size:12.5px"><span>${k.resultado==='publicado'?'✅':k.resultado==='borrador'?'📝':'⚠️'}</span><span style="color:var(--muted);min-width:120px">${new Date((k.en||0)*1000).toLocaleString('es-PE',{day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit'})}</span><span style="flex:1">${esc(k.resultado)}${k.audiencia?' · '+esc((agente.audiencias||{})[k.audiencia]||k.audiencia):''}${k.titulo?' · '+esc(k.titulo):''}${k.detalle?' · <span style="color:var(--rojo)">'+esc(k.detalle)+'</span>':''}</span>${k.url?`<a href="${esc(k.url)}" target="_blank" rel="noopener">ver ↗</a>`:''}</div>`).join('') || '<small style="color:var(--muted)">Todavía no corrió.</small>';
  box.innerHTML = `<div class="top"><h3>🤖 Agente de marketing 24×7</h3>${c.activo?`<span style="color:var(--green);font-weight:700">● Activo · publica a las ${esc(c.hora)} (${esc(c.zona.replace('America/',''))})</span>`:'<span style="color:var(--muted);font-weight:700">○ Pausado</span>'}</div>
    <div class="row" style="color:var(--muted);font-size:13px">Estratega + creativo + community manager de la página: cada día arma una pieza de <b>la MARCA Pichangol</b> (fotos y videos de tu biblioteca de Google Fotos si los hay, si no arte de marca por deporte; copy con IA que no se repite y un objetivo comercial: jugadores → descargar la app o reservar en la web; dueños → administrar su cancha con Pichangol) y la publica solo a la hora fijada, o te la deja para aprobar. Ningún local sale en la publicidad salvo que sea <b>Pro</b> y actives "Destacar locales Pro". Próxima: ${cuando} → ${esc((agente.audiencias||{})[px.audiencia]||'')} · ${esc(ENFOQUE_NOMBRE[px.enfoque]||px.enfoque||'')}. Hora local del agente: ${esc(agente.hora_local||'')}.${!agente.credenciales?' <b style="color:var(--rojo)">Falta el token de Facebook: el agente no puede publicar.</b>':''}${agente.ia===false?' <span style="color:#8a5a00">Sin ANTHROPIC_API_KEY: usa el banco de variantes.</span>':''}${agente.arte_ia===false?' <span style="color:#8a5a00">Sin proveedor de imágenes IA (OPENAI_API_KEY): usa la portada de marca.</span>':''}</div>
    <div class="row" style="display:flex;gap:14px;flex-wrap:wrap;align-items:end">
      <label style="display:flex;align-items:center;gap:8px;font-weight:700"><input type="checkbox" id="ag_activo" ${c.activo?'checked':''} style="width:18px;height:18px"> Activo</label>
      <label style="display:flex;align-items:center;gap:8px;font-size:12.5px" title="Solo locales verificados cuyo dueño tiene Pichangol Pro vigente entran en la rotación (enfoque 'El local protagonista')"><input type="checkbox" id="ag_pro" ${c.destacar_pro?'checked':''} style="width:16px;height:16px"> Destacar locales Pro <small style="color:var(--muted)">(${agente.locales_pro||0} disponibles)</small></label>
      <label style="display:flex;align-items:center;gap:8px;font-size:12.5px" title="Jueves, viernes y sábado: si hay un video de la biblioteca sin usar hace 14 días, ese día publica video pulido con música"><input type="checkbox" id="ag_videos" ${c.videos!=='nunca'?'checked':''} style="width:16px;height:16px"> Videos con música <small style="color:var(--muted)">(biblioteca: ${(agente.biblioteca||{}).fotos||0} fotos · ${(agente.biblioteca||{}).videos||0} videos · ${(agente.biblioteca||{}).pistas||0} pistas propias${(agente.biblioteca||{}).pistas?', rota la menos usada':', usa la música original'})</small></label>
      <label style="font-size:12.5px;font-weight:700">Hora<br><select id="ag_hora" ${inp}>${horas.join('')}</select></label>
      <label style="font-size:12.5px;font-weight:700">Zona<br><select id="ag_zona" ${inp}>${zonas}</select></label>
      <div style="font-size:12.5px;font-weight:700">Modo<br><label style="font-weight:400;margin-right:8px"><input type="radio" name="ag_modo" value="auto" ${c.modo==='auto'?'checked':''}> Publicar solo</label><label style="font-weight:400"><input type="radio" name="ag_modo" value="aprobar" ${c.modo==='aprobar'?'checked':''}> Dejarme aprobar</label></div>
      <label style="font-size:12.5px;font-weight:700">Tono<br><select id="ag_tono" ${inp}>${tonos}</select></label>
      <button type="button" class="btn-ap" id="ag_guardar" onclick="agGuardar()" ${agOcupado?'disabled':''}>${agOcupado==='guardar'?'<span class="rd-spin blanco"></span> Guardando…':'Guardar'}</button>
    </div>
    <details class="row" ${agente._planAbierto?'open':''} ontoggle="agente._planAbierto=this.open"><summary style="cursor:pointer;font-weight:700">📅 Plan semanal (audiencia y enfoque por día)</summary>
      <table style="margin-top:6px;border-collapse:collapse"><thead><tr><th style="text-align:left;padding:4px 6px;font-size:12px;color:var(--muted)">Día</th><th style="text-align:left;padding:4px 6px;font-size:12px;color:var(--muted)">Audiencia</th><th style="text-align:left;padding:4px 6px;font-size:12px;color:var(--muted)">Enfoque</th></tr></thead><tbody>${filas}</tbody></table>
      <small style="color:var(--muted)">"Que varíe solo" deja que la IA elija el ángulo evitando los últimos publicados. Los días de dueños siempre invitan a registrar y administrar la cancha. "El local protagonista" solo aplica con "Destacar locales Pro" activo; si no, cae a "Beneficio de reservar". Se guarda con el botón Guardar.</small></details>
    <div class="row actions" style="flex-wrap:wrap">
      <button type="button" class="btn-sec" onclick="agCorrer(false)" ${agOcupado?'disabled':''}>${agOcupado==='correr'?'<span class="rd-spin chico"></span> Creando…':'📝 Generar borrador ahora'}</button>
      <button type="button" class="btn-ap" onclick="agCorrer(true)" ${agOcupado||!agente.credenciales?'disabled':''}>${agOcupado==='publicar'?'<span class="rd-spin blanco"></span> Publicando…':'📣 Publicar ahora'}</button>
      <small style="color:var(--muted)">Prueba la pieza del día sin esperar a la hora. "Publicar ahora" cuenta como la publicación de hoy.</small>
    </div>
    <div class="row"><b>Borradores por aprobar (${(agente.borradores||[]).length})</b>${bor}</div>
    <div class="row" style="padding-top:10px;border-top:1px solid var(--border)"><b>Bitácora</b>${log}</div>`;
}
function renderAgentePlan(){ const plan = {}; (agente.dias||[]).forEach((d,i)=>{ const a=document.querySelector(`[data-plan-aud="${i}"]`), e=document.querySelector(`[data-plan-enf="${i}"]`); plan[String(i)] = {audiencia: a?a.value:'jugadores', enfoque: e?e.value:'auto'}; }); agente.config.plan = plan; renderAgente(); }
function agLeerForm(){
  const plan = {}; (agente.dias||[]).forEach((d,i)=>{ const a=document.querySelector(`[data-plan-aud="${i}"]`), e=document.querySelector(`[data-plan-enf="${i}"]`); plan[String(i)] = {audiencia: a?a.value:'jugadores', enfoque: e?e.value:'auto'}; });
  const modo = (document.querySelector('input[name="ag_modo"]:checked')||{}).value || 'auto';
  return {activo: document.getElementById('ag_activo').checked, destacar_pro: document.getElementById('ag_pro').checked, videos: document.getElementById('ag_videos').checked ? 'auto' : 'nunca', hora: document.getElementById('ag_hora').value, zona: document.getElementById('ag_zona').value, modo: modo, tono: document.getElementById('ag_tono').value, plan: plan};
}
async function agGuardar(){
  const cuerpo = agLeerForm(); agOcupado='guardar'; renderAgente();
  try{ const r = await fetch('/admin/api/redes/agente',{method:'POST',headers:headers(),body:JSON.stringify(cuerpo)}); const j = await r.json().catch(()=>({})); if(r.status===401){ salir(); return; }
    if(r.ok && j.ok){ agente = j; toast(cuerpo.activo ? 'Agente activo: publica a las '+cuerpo.hora : 'Agente en pausa'); } else alert(j.detail||'No se pudo guardar'); }
  catch(e){ alert('Error de red'); }
  agOcupado=''; renderAgente();
}
async function agCorrer(publicar){
  if(publicar && !confirm('¿Publicar AHORA la pieza del día en la página de Facebook? Contará como la publicación de hoy.')) return;
  agOcupado = publicar ? 'publicar' : 'correr'; renderAgente();
  try{ const r = await fetch('/admin/api/redes/agente/correr',{method:'POST',headers:headers(),body:JSON.stringify({publicar:!!publicar})}); const j = await r.json().catch(()=>({})); if(r.status===401){ salir(); return; }
    if(r.ok && j.ok){ agente = j; toast(j.publicado ? 'Publicado en Facebook' : 'Borrador listo'); if(!j.publicado && (j.borradores||[]).length){ agAbierto = j.borradores[0].id; agVerImagen(agAbierto); } cargarRedes(); }
    else alert(j.detail||'No se pudo'); }
  catch(e){ alert('Error de red'); }
  agOcupado=''; renderAgente();
}
async function agVerImagen(bid){
  if(agImg[bid]) return;
  try{ const r = await fetch('/admin/api/redes/agente/borrador/'+bid+'/imagen',{headers:headers()}); const j = await r.json().catch(()=>({})); if(j.ok){ agImg[bid]=j.imagen; const d=document.getElementById('ag_img_'+bid); if(d) d.innerHTML=`<img src="${j.imagen}" style="max-width:100%;max-height:60vh;display:block">`; } }catch(e){}
}
async function agEditar(bid){
  const g = id => (document.getElementById(id)||{}).value;
  agOcupado='editar'; renderAgente();
  try{ const r = await fetch('/admin/api/redes/agente/borrador/'+bid+'/editar',{method:'POST',headers:headers(),body:JSON.stringify({titulo:g('ag_t_'+bid), subtitulo:g('ag_s_'+bid), texto:g('ag_x_'+bid)})}); const j = await r.json().catch(()=>({}));
    if(r.ok && j.ok){ delete agImg[bid]; toast('Borrador guardado'); await cargarAgente(); agVerImagen(bid); return; } else alert(j.detail||'No se pudo guardar'); }catch(e){ alert('Error de red'); }
  agOcupado=''; renderAgente();
}
async function agAccion(bid, accion){
  if(accion==='descartar' && !confirm('¿Descartar este borrador?')) return;
  if(accion==='aprobar' && !confirm('¿Publicar este borrador en la página de Facebook?')) return;
  agOcupado = accion+':'+bid; renderAgente();
  try{ const r = await fetch('/admin/api/redes/agente/borrador/'+bid+'/'+accion,{method:'POST',headers:headers()}); const j = await r.json().catch(()=>({})); if(r.status===401){ salir(); return; }
    if(r.ok && j.ok){ agente = j; delete agImg[bid]; if(accion==='aprobar'){ toast('Publicado en Facebook'); agAbierto=null; cargarRedes(); } if(accion==='descartar') agAbierto=null; if(accion==='regenerar'){ toast('Nueva versión'); agAbierto=bid; agVerImagen(bid); } }
    else alert(j.detail||'No se pudo'); }
  catch(e){ alert('Error de red'); }
  agOcupado=''; renderAgente();
}
// ── Pulido con estilo Pichangol (FFmpeg en el backend) + subtítulos Whisper ──
const PUL_DEF = {formato:'vertical', logo:true, intro:true, rotulo:true, cierre:true, subtitulos:true, musica:true, musica_modo:'auto', mood:'chill', musica_pista:'', musica_desde:''};
function pulidoHtml(vd){
  const cap = redes.pulido || {};
  if(cap.disponible===false) return '<small style="display:block;margin-top:8px;color:var(--muted)">Este servidor no tiene FFmpeg: el video se publica tal cual.</small>';
  const pl = vd.pulido || (vd.pulido = {estado:'ninguno', progreso:0, mensaje:'', url:'', info:null, transcripcion:null, usar:true, opciones:{...PUL_DEF, subtitulos: cap.subtitulos!==false}});
  const o = pl.opciones;
  const ocupado = pl.estado==='transcribiendo' || pl.estado==='renderizando';
  const chip = (k,v,txt)=>`<button type="button" class="btn-sec" style="padding:5px 10px;font-size:12.5px;${o[k]===v?'border-color:var(--green);background:#F2F8F3;font-weight:700':''}" onclick="pulOpt('${k}','${v}')" ${ocupado?'disabled':''}>${txt}</button>`;
  const chk = (k,txt,extra)=>`<label style="display:inline-flex;align-items:center;gap:6px;font-size:12.5px;margin-right:12px;${extra&&extra.off?'opacity:.55':''}"><input type="checkbox" ${o[k]?'checked':''} onchange="pulOpt('${k}',this.checked)" ${ocupado||(extra&&extra.off)?'disabled':''}>${txt}</label>`;
  const subsOff = cap.subtitulos===false && !(pl.transcripcion && pl.transcripcion.segmentos && pl.transcripcion.segmentos.length);
  const estado = ocupado ? `<div style="margin-top:10px"><span class="rd-spin chico"></span> <b>${esc(pl.mensaje||'Procesando…')}</b> <span id="rd_pul_pct">${pl.progreso||0}%</span>
        <div style="height:8px;border-radius:4px;background:#E9EDF0;margin-top:6px;overflow:hidden"><div id="rd_pul_prog" style="height:100%;width:${pl.progreso||0}%;background:var(--green);transition:width .3s"></div></div>
        <small style="color:var(--muted)">Intro, marca de agua, ${o.subtitulos?'subtítulos, ':''}cierre y volumen normalizado. Según el peso del video puede tomar de 20 s a unos minutos.</small></div>`
    : pl.estado==='error' ? `<div style="margin-top:8px;color:var(--rojo)">⚠️ ${esc(pl.error||'No se pudo pulir el video')}</div>` : '';
  const listo = pl.estado==='listo' && pl.url;
  const info = pl.info || {};
  const usar = listo ? `<div style="margin-top:10px;padding:8px 10px;border-radius:10px;background:#F2F8F3;display:flex;gap:14px;flex-wrap:wrap;align-items:center">
        <span style="font-weight:700;color:var(--green)">✓ Versión pulida lista</span><small style="color:var(--muted)">${info.ancho||''}×${info.alto||''} · ${Math.round(info.duracion||0)} s · ${Math.round((info.bytes||0)/1048576*10)/10} MB${info.segmentos?' · '+info.segmentos+' subtítulos':''}</small>
        <span style="flex:1"></span>
        <label style="font-size:12.5px"><input type="radio" name="rd_usar" ${pl.usar?'checked':''} onchange="pulUsar(true)"> Publicar la pulida</label>
        <label style="font-size:12.5px"><input type="radio" name="rd_usar" ${!pl.usar?'checked':''} onchange="pulUsar(false)"> Publicar el original</label></div>` : '';
  const segs = (pl.transcripcion && pl.transcripcion.segmentos) || [];
  const editor = (segs.length && !ocupado) ? `<details style="margin-top:10px" ${pl.editorAbierto?'open':''} ontoggle="if(redesSel.video&&redesSel.video.pulido) redesSel.video.pulido.editorAbierto=this.open">
        <summary style="cursor:pointer;font-weight:700;font-size:12.5px">✏️ Corregir subtítulos (${segs.length})</summary>
        <div style="max-height:260px;overflow:auto;margin-top:6px;border:1px solid var(--border);border-radius:10px;padding:6px 8px;background:#fff">
          ${segs.map((sg,i)=>`<div style="display:flex;gap:8px;align-items:center;padding:4px 0;border-bottom:1px solid #F0F2F4"><small style="color:var(--muted);min-width:78px">${fmtT(sg.inicio)}–${fmtT(sg.fin)}</small><input data-seg="${i}" value="${esc(sg.texto)}" style="flex:1;padding:6px 8px;border:1px solid var(--border);border-radius:8px;font-family:inherit;font-size:13px"></div>`).join('')}
        </div>
        <div style="margin-top:8px;display:flex;gap:8px;flex-wrap:wrap;align-items:center"><button type="button" class="btn-sec" onclick="pulRegenerar()">🔁 Regenerar con mis correcciones</button><small style="color:var(--muted)">Si cambias el texto de una línea, esa línea pierde el resaltado palabra por palabra (no hay tiempos para las palabras nuevas).</small></div>
      </details>` : (pl.transcripcion && pl.transcripcion.sin_audio ? '<small style="display:block;margin-top:6px;color:var(--muted)">El video no trae audio: sin subtítulos; se le puso música de fondo.</small>' : '');
  return `<div style="margin-top:12px;padding:10px 12px;border-radius:12px;border:1px dashed var(--border);background:#fff">
      <div style="font-size:12.5px;font-weight:700">✨ Pulir con estilo Pichangol</div>
      <div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:6px;align-items:center"><small style="color:var(--muted);font-weight:700;margin-right:4px">Formato</small>${chip('formato','vertical','Vertical 9:16 · Reels')} ${chip('formato','cuadrado','Cuadrado 1:1')} ${chip('formato','original','Original')}</div>
      <div style="margin-top:8px">${chk('logo','Logo')}${chk('intro','Intro')}${chk('rotulo','Rótulo con el título')}${chk('cierre','Cierre con título y web')}${chk('subtitulos','Subtítulos automáticos', {off: subsOff})}</div>
      <div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:8px;align-items:center"><small style="color:var(--muted);font-weight:700;margin-right:4px">🎵 Música</small>${chip('musica_modo','auto','Automática')} ${chip('musica_modo','fondo','De fondo')} ${chip('musica_modo','protagonista','Protagonista')} ${chip('musica_modo','no','Sin música')}
        <small style="color:var(--muted);margin-left:4px">${o.musica_modo==='fondo'?'Suave bajo la voz del video (sola si el video es mudo).':o.musica_modo==='protagonista'?'La música manda; el audio original queda de ambiente, bajito.':o.musica_modo==='no'?'Se conserva solo el audio original.':'De fondo si el video trae voz; protagonista si es mudo.'}</small></div>
      ${o.musica_modo!=='no'?`<div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:6px;align-items:center"><small style="color:var(--muted);font-weight:700;margin-right:4px">Pista</small>
          <select id="rd_pista" style="padding:6px 10px;border:1px solid var(--border);border-radius:10px;font-family:inherit;font-size:12.5px;max-width:320px" onchange="pulOpt('musica_pista',this.value)" ${ocupado?'disabled':''}><option value="">🎼 Original de Pichangol (sintetizada)</option>${musOpciones(o.musica_pista)}</select>
          ${(mus&&mus.items&&mus.items.length)?'':`<small style="color:var(--muted)">Sin pistas propias: conéctalas en <a href="#" onclick="rdUI('tab','conexiones');return false">Conexiones → Mi música</a>.</small>`}
          ${o.musica_pista&&mus&&(mus.items||[]).some(t=>t.id===o.musica_pista)?`<audio controls preload="none" src="${esc((mus.items.find(t=>t.id===o.musica_pista)||{}).url||'')}" style="height:30px;max-width:260px"></audio>`:(o.musica_pista?'<small style="color:var(--muted)">la torre elige la menos usada de ese género</small>':'')}</div>
        ${o.musica_pista?`<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-top:6px"><small style="color:var(--muted);font-weight:700;margin-right:4px">Empieza en el segundo</small><input id="rd_pista_desde" type="number" min="0" max="600" step="0.5" value="${esc(o.musica_desde===''||o.musica_desde==null?musInicioSugerido(o.musica_pista):o.musica_desde)}" onchange="pulOpt('musica_desde',this.value)" style="width:80px;padding:6px 8px;border:1px solid var(--border);border-radius:10px;font-family:inherit;font-size:12.5px" ${ocupado?'disabled':''}><button type="button" class="btn-sec" style="padding:5px 10px;font-size:12px" onclick="pulDesdeReproductor()" title="Pausa el reproductor donde quieras que arranque y pulsa aquí">📍 Usar donde está el reproductor</button><small style="color:var(--muted)">${musInicioSugerido(o.musica_pista)>0?'La torre detectó que empieza a sonar a los '+musInicioSugerido(o.musica_pista)+' s.':'Empieza a sonar desde el inicio.'}</small></div><small style="display:block;margin-top:4px;color:var(--muted)">La pista se pone en bucle si es más corta que el video y se corta al terminar, con fundido.</small>`:`<div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:6px;align-items:center"><small style="color:var(--muted);font-weight:700;margin-right:4px">Estilo</small>${chip('mood','chill','Chill')} ${chip('mood','energetico','Enérgica')} ${chip('mood','epico','Épica')}</div>`}`:''}
      ${subsOff?'<small style="color:#8a5a00">Subtítulos automáticos apagados: falta OPENAI_API_KEY en este ambiente.</small>':''}
      <div style="margin-top:8px;display:flex;gap:8px;flex-wrap:wrap;align-items:center">
        <button type="button" class="btn-ap" id="rd_pulir" onclick="pulirVideo()" ${ocupado?'disabled':''}>${ocupado?'<span class="rd-spin blanco"></span> Procesando…':(listo?'🎬 Volver a generar':'🎬 Generar versión pulida')}</button>
        <small style="color:var(--muted)">Usa el título de arriba para el rótulo y el cierre. ${o.musica_pista?'Vas a usar tu propia pista: asegúrate de tener licencia para publicarla en Facebook (una canción comercial puede silenciarse o bloquear el post).':'La música es original de Pichangol (libre de regalías), sin problemas de derechos en Facebook.'}</small>
      </div>
      ${estado}${usar}${editor}
    </div>`;
}
function fmtT(s){ s=Math.max(0,Number(s)||0); const m=Math.floor(s/60), r=s-m*60; return m+':'+(r<10?'0':'')+r.toFixed(1); }
function pulOpt(k, v){ const pl = redesSel.video && redesSel.video.pulido; if(!pl) return; if(k==='musica_pista'){ pl.opciones.musica_pista=v; pl.opciones.musica_desde=''; } else if(k==='formato'||k==='musica_modo'||k==='mood'||k==='musica_desde') pl.opciones[k]=v; else pl.opciones[k]=!!v; renderRedes(); }
function pulUsar(u){ const pl = redesSel.video && redesSel.video.pulido; if(!pl) return; pl.usar=!!u; renderRedes(); mostrarVideoPreview(); }
function mostrarVideoPreview(){
  const v = document.querySelector('#rd_prev video'); const vd = redesSel.video; if(!v || !vd) return;
  const src = (vd.pulido && vd.pulido.usar && vd.pulido.url) ? vd.pulido.url : vd.url;
  if(v.getAttribute('src')!==src){ v.setAttribute('src', src); v.load(); }
}
let pulTimer = null;
async function pulirVideo(segmentos){
  const vd = redesSel.video; if(!vd || !vd.id) return;
  const pl = vd.pulido; const o = pl.opciones;
  const titulo = (document.getElementById('rd_titulo')||{}).value || '';
  pl.estado = (o.subtitulos && !segmentos && !(pl.transcripcion && pl.transcripcion.segmentos)) ? 'transcribiendo' : 'renderizando'; pl.progreso = 0; pl.mensaje = 'Preparando…'; pl.error='';
  renderRedes(); botonesRedes('componiendo');
  const cuerpo = {formato:o.formato, logo:!!o.logo, intro:!!o.intro, cierre:!!o.cierre, rotulo:!!o.rotulo, titulo:titulo, subtitulos:!!o.subtitulos, segmentos: segmentos||null, musica:o.musica_modo!=='no', musica_modo:o.musica_modo||'auto', mood:o.mood||'chill', musica_pista:o.musica_modo!=='no'?(o.musica_pista||''):'', musica_desde:(o.musica_pista&&o.musica_desde!==''&&o.musica_desde!=null)?Number(o.musica_desde):null};
  try{
    const r = await fetch('/admin/api/redes/pichangol/video/'+encodeURIComponent(vd.id)+'/pulir',{method:'POST',headers:headers(),body:JSON.stringify(cuerpo)});
    const j = await r.json().catch(()=>({}));
    if(r.status===401){ salir(); return; }
    if(!r.ok || !j.ok){ pl.estado='error'; pl.error=j.detail||('HTTP '+r.status); renderRedes(); botonesRedes(false); return; }
  }catch(e){ pl.estado='error'; pl.error='No se pudo iniciar (red).'; renderRedes(); botonesRedes(false); return; }
  clearTimeout(pulTimer); sondearPulido();
}
async function sondearPulido(){
  const vd = redesSel.video; if(!vd || !vd.id || !vd.pulido) return;
  const pl = vd.pulido;
  try{
    const r = await fetch('/admin/api/redes/pichangol/video/'+encodeURIComponent(vd.id)+'/estado',{headers:headers()});
    const j = await r.json().catch(()=>({}));
    if(!r.ok){ pl.estado='error'; pl.error=j.detail||('HTTP '+r.status); renderRedes(); botonesRedes(false); return; }
    if(j.transcripcion) pl.transcripcion = j.transcripcion;
    if(j.estado==='transcribiendo' || j.estado==='renderizando'){
      pl.estado=j.estado; pl.progreso=j.progreso||0; pl.mensaje=j.mensaje||'';
      const b=document.getElementById('rd_pul_prog'), t=document.getElementById('rd_pul_pct'); if(b&&t){ b.style.width=pl.progreso+'%'; t.textContent=pl.progreso+'%'; } else renderRedes();
      pulTimer = setTimeout(sondearPulido, 1500); return;
    }
    if(j.estado==='listo' && j.pulido){
      pl.estado='listo'; pl.progreso=100; pl.info=j.pulido_info||{}; pl.usar=true;
      const rv = await fetch('/admin/api/redes/pichangol/video/'+encodeURIComponent(vd.id)+'/archivo?cual=pulido',{headers:headers()});
      if(rv.ok){ const blob = await rv.blob(); if(pl.url) URL.revokeObjectURL(pl.url); pl.url = URL.createObjectURL(blob); }
      renderRedes(); mostrarVideoPreview(); botonesRedes(false); toast('Versión pulida lista'); return;
    }
    if(j.estado==='error'){ pl.estado='error'; pl.error=j.error||'No se pudo pulir'; renderRedes(); botonesRedes(false); return; }
    pulTimer = setTimeout(sondearPulido, 1500);
  }catch(e){ pulTimer = setTimeout(sondearPulido, 2500); }
}
function pulRegenerar(){
  const pl = redesSel.video && redesSel.video.pulido; if(!pl || !pl.transcripcion) return;
  const segs = (pl.transcripcion.segmentos||[]).map((sg,i)=>{ const inp=document.querySelector('input[data-seg="'+i+'"]'); const texto = inp ? inp.value.trim() : sg.texto; const cambiado = texto !== (sg.texto||'').trim(); return {inicio:sg.inicio, fin:sg.fin, texto:texto, palabras: cambiado ? [] : (sg.palabras||[])}; }).filter(x=>x.texto);
  pl.transcripcion = {...pl.transcripcion, segmentos: segs};
  pl.opciones.subtitulos = true;
  pulirVideo(segs);
}
// ── Video: se sube a la torre con barra de progreso; al publicar, la torre lo manda a la página por trozos.
function subirVideoRedes(inp){
  const f = (inp.files||[])[0]; inp.value=''; if(!f) return;
  const ext = (f.name.split('.').pop()||'').toLowerCase(), permitidas = redes.video_extensiones || ['mp4','mov','m4v','webm','avi','mkv','3gp'];
  if(!permitidas.includes(ext)){ alert('Formato no admitido ('+ext+'). Sube un video MP4 o MOV.'); return; }
  const maxMb = redes.video_max_mb || 300;
  if(f.size > maxMb*1048576){ alert('El video pesa '+(f.size/1048576).toFixed(0)+' MB; el máximo es '+maxMb+' MB. Comprímelo o recórtalo.'); return; }
  if(redesSel.video && redesSel.video.url) URL.revokeObjectURL(redesSel.video.url);
  redesSel.video = {nombre:f.name, bytes:f.size, url:URL.createObjectURL(f), estado:'subiendo', pct:0, id:'', dur:0};
  renderRedes();
  // Duración con un <video> aparte (el de la vista previa se re-crea en cada renderRedes).
  const sonda = document.createElement('video'); sonda.preload = 'metadata';
  sonda.onloadedmetadata = ()=>{ if(redesSel.video && redesSel.video.url === sonda.src){ redesSel.video.dur = sonda.duration; renderRedes(); } sonda.removeAttribute('src'); };
  sonda.src = redesSel.video.url;
  const xhr = new XMLHttpRequest();
  xhr.open('POST', '/admin/api/redes/pichangol/video?nombre='+encodeURIComponent(f.name));
  xhr.setRequestHeader('X-Admin-Token', tok()); xhr.setRequestHeader('Content-Type', f.type || 'application/octet-stream');
  xhr.upload.onprogress = e => { if(!e.lengthComputable || !redesSel.video) return; redesSel.video.pct = Math.round(e.loaded*100/e.total); const b=document.getElementById('rd_video_prog'), t=document.getElementById('rd_video_pct'); if(b) b.style.width = redesSel.video.pct+'%'; if(t) t.textContent = redesSel.video.pct+'%'; };
  xhr.onload = () => { if(!redesSel.video) return; let j={}; try{ j=JSON.parse(xhr.responseText||'{}'); }catch(e){} if(xhr.status===401){ salir(); return; } if(xhr.status>=200 && xhr.status<300 && j.ok){ redesSel.video.id=j.video_id; redesSel.video.estado='listo'; redesSel.video.pct=100; redesUI.paso=2; toast('Video listo: elige la música y púlelo'); } else { redesSel.video.estado='error'; redesSel.video.error = j.detail || ('No se pudo subir (HTTP '+xhr.status+')'); } renderRedes(); botonesRedes(false); };
  xhr.onerror = () => { if(!redesSel.video) return; redesSel.video.estado='error'; redesSel.video.error='Se cortó la subida (red). Inténtalo de nuevo.'; renderRedes(); };
  xhr.send(f);
}
function quitarVideoRedes(){
  const v = redesSel.video; if(!v) return;
  if(v.id) fetch('/admin/api/redes/pichangol/video/'+encodeURIComponent(v.id)+'/descartar',{method:'POST',headers:headers()}).catch(()=>{});
  if(v.url) URL.revokeObjectURL(v.url);
  if(v.pulido && v.pulido.url) URL.revokeObjectURL(v.pulido.url);
  clearTimeout(pulTimer);
  redesSel.video = null; redesUI.paso = 1; renderRedes(); autoPrevRedes();
}
let rdSeq = 0;
async function previsualizarRedes(auto){
  const msg = document.getElementById('rd_msg'), est = document.getElementById('rd_prev_estado');
  if(!redesSel.fotos.length){ if(!auto) msg.innerHTML = '<span style="color:var(--rojo)">Elige o sube al menos una foto.</span>'; return; }
  const seq = ++rdSeq; const t0 = Date.now();
  veloPrev(true, 'Componiendo la pieza…'); botonesRedes('componiendo');
  if(est) est.innerHTML = '<span class="rd-spin chico"></span> componiendo…'; if(!auto) msg.innerHTML = '<span class="rd-spin chico"></span> Componiendo…';
  try{
    const r = await fetch('/admin/api/redes/pichangol/previsualizar',{method:'POST',headers:headers(),body:JSON.stringify(cuerpoRedes())});
    const j = await r.json().catch(()=>({}));
    if(seq !== rdSeq) return; // llegó otra más nueva: esa pintará y quitará el velo
    veloPrev(false); botonesRedes(false);
    if(r.ok && j.ok){ redesSel.img = j.imagen; redesSel.ext = j.extension||'jpg'; document.getElementById('rd_prev').innerHTML = `<img src="${j.imagen}" style="max-width:100%;max-height:78vh;display:block">`; botonesRedes(false); if(est) est.textContent = '· '+Math.round(j.bytes/1024)+' KB · '+((Date.now()-t0)/1000).toFixed(1)+' s'; if(!auto) msg.textContent = 'Lista. Revisa y publica o descarga.'; }
    else { if(est) est.textContent = ''; msg.innerHTML = `<span style="color:var(--rojo)">${esc(j.detail||'No se pudo componer')}</span>`; }
  }catch(e){ if(seq !== rdSeq) return; veloPrev(false); botonesRedes(false); if(est) est.textContent = ''; msg.innerHTML = '<span style="color:var(--rojo)">No se pudo componer (red). Inténtalo de nuevo.</span>'; }
}
function descargarRedes(){ if(!redesSel.img) return; const a=document.createElement('a'); a.href=redesSel.img; a.download='pichangol-post-'+Date.now()+'.'+(redesSel.ext||'jpg'); a.click(); }
async function publicarRedes(){
  const esVideo = !!(redesSel.video && redesSel.video.id);
  if(!confirm(esVideo ? '¿Publicar este VIDEO ahora en la página de Facebook de Pichangol?' : '¿Publicar ahora en la página de Facebook de Pichangol?')) return;
  const msg = document.getElementById('rd_msg'); msg.innerHTML = '<span class="rd-spin chico"></span> ' + (esVideo ? 'Subiendo el video a Facebook por partes… puede tardar según su peso.' : 'Publicando en la página… (componiendo la pieza final y subiéndola a Facebook)');
  botonesRedes('publicando'); veloPrev(true, esVideo ? 'Subiendo el video a Facebook…' : 'Publicando en Facebook…');
  try{
    const r = await fetch('/admin/api/redes/pichangol/publicar',{method:'POST',headers:headers(),body:JSON.stringify(cuerpoRedes(true))});
    const j = await r.json().catch(()=>({}));
    if(r.ok && j.ok){ toast(esVideo ? 'Video enviado a Facebook' : 'Publicado en Facebook'); if(esVideo){ if(redesSel.video.url) URL.revokeObjectURL(redesSel.video.url); if(redesSel.video.pulido&&redesSel.video.pulido.url) URL.revokeObjectURL(redesSel.video.pulido.url); redesSel.video=null; } await cargarRedes(); const m2=document.getElementById('rd_msg'); if(m2) m2.innerHTML = esVideo ? `✅ Video enviado. Facebook lo procesa unos minutos y luego aparece en la página. ${j.url?`<a href="${esc(j.url)}" target="_blank" rel="noopener">Ver el video ↗</a>`:''}` : `✅ Publicado. ${j.url?`<a href="${esc(j.url)}" target="_blank" rel="noopener">Ver la publicación ↗</a>`:''}`; return; }
    msg.innerHTML = `<span style="color:var(--rojo)">${esc(j.detail||'No se pudo publicar')}</span>`;
  }catch(e){ msg.innerHTML = '<span style="color:var(--rojo)">No se pudo publicar (red). Revisa el historial antes de reintentar.</span>'; }
  veloPrev(false); botonesRedes(false);
}
// Navegación de la barra lateral: muestra una sección y marca su ítem activo.
// Maestro–detalle genérico (Cobros, Operación, Comunicación…): muestra el
// rubro elegido dentro del MISMO bloque .md y marca el ítem activo.
function mostrarPane(btn, pane){
  const md = btn.closest('.md');
  md.querySelectorAll('.md-pane').forEach(p=>{
    p.style.display = (p.id===pane) ? 'block' : 'none';
  });
  md.querySelectorAll('.md-item').forEach(b=>{ b.classList.toggle('on', b===btn); });
}

// ── Dashboard (Resumen): KPIs que se llenan conforme cargan las secciones ──
const kpi = {reclamosPend:null, activas:null, liqTotal:null, liqN:null, liqAtras:0, liqDias:0, disputas:null};

function renderResumen(){
  const box = document.getElementById('kpis');
  if(!box) return;
  const v = x => (x===null || x===undefined) ? '…' : x;
  box.innerHTML = `
    <button class="kpi" onclick="mostrarSeccion('reclamos')">
      <div class="ki" style="background:#FFF3D6">📋</div>
      <div class="kv">${v(kpi.reclamosPend)}</div>
      <div class="kl">Reclamos por aprobar</div>
    </button>
    <button class="kpi" onclick="mostrarSeccion('reclamos')">
      <div class="ki" style="background:#DDF3E1">✅</div>
      <div class="kv">${v(kpi.activas)}</div>
      <div class="kl">Canchas activadas</div>
    </button>
    <button class="kpi" onclick="mostrarSeccion('liquidaciones')">
      <div class="ki" style="background:#E3F2EF">💸</div>
      <div class="kv">${kpi.liqTotal===null?'…':'S/ '+kpi.liqTotal}</div>
      <div class="kl">${kpi.liqN===null?'Por liquidar a dueños':(kpi.liqN===1?'1 pago pendiente':kpi.liqN+' pagos pendientes')}${kpi.liqAtras?` · <b style="color:#B42318">${kpi.liqAtras} atrasado${kpi.liqAtras===1?'':'s'}</b>`:''}</div>
    </button>
    <button class="kpi" onclick="mostrarSeccion('disputas')">
      <div class="ki" style="background:#FBE2E2">⚖️</div>
      <div class="kv">${v(kpi.disputas)}</div>
      <div class="kl">Disputas abiertas</div>
    </button>`;
}

const TITULOS_SEC = {resumen:'Resumen', reclamos:'Reclamos', operacion:'Operación', cobros:'Cobros',
  liquidaciones:'Liquidaciones', disputas:'Disputas', identidad:'Identidad',
  comunicacion:'Comunicación', pruebas:'Pruebas'};

function mostrarSeccion(sec){
  document.querySelectorAll('.page').forEach(p=>{ p.style.display='none'; });
  const el = document.getElementById('page-'+sec);
  if(el) el.style.display='block';
  const tt = document.getElementById('tbTitle');
  if(tt) tt.textContent = TITULOS_SEC[sec] || '';
  document.querySelectorAll('.topnav-tab').forEach(b=>{
    const on = b.dataset.sec===sec;
    b.classList.toggle('on', on);
    if(on) b.scrollIntoView({block:'nearest',inline:'center',behavior:'smooth'});
  });
  window.scrollTo({top:0,behavior:'smooth'});
  if(sec==='disputas') cargarDisputas();
  if(sec==='identidad') cargarDni();
  if(sec==='pruebas') cargarSeguridad();
}

// ── Seguridad de la torre (2.º paso, dispositivos, bitácora de accesos) ────
async function cargarSeguridad(){
  const box = document.getElementById('seguridad'); if(!box) return;
  const r = await fetch('/admin/api/seguridad',{headers:headers()});
  if(r.status===401){ salir(); return; }
  if(!r.ok){ box.innerHTML=''; return; }
  const g = await r.json();
  const yo = g.usuarios.find(u=>u.correo===g.yo);
  const fecha = ts => ts ? new Date(ts*1000).toLocaleString('es-PE',{dateStyle:'short',timeStyle:'short'}) : '—';
  const EV = {login_ok:'✅ Ingreso', clave_ok:'🔑 Contraseña OK', clave_mala:'❌ Contraseña incorrecta', '2fa_mal':'❌ Código incorrecto',
    bloqueado:'⛔ Bloqueado por intentos', enrolado:'📲 Activó 2 pasos', '2fa_restablecido':'♻️ 2 pasos restablecido',
    recuperacion_nueva:'🧾 Códigos nuevos', dispositivos_olvidados:'📵 Dispositivos olvidados'};
  const estado = !g.dos_pasos
    ? `<div class="row" style="color:#8a5a00"><b>⚠️ Verificación en dos pasos APAGADA</b> (ADMIN_2FA=0 en Railway). Solo se pide contraseña.</div>`
    : g.token_clasico
      ? `<div class="row" style="color:#8a5a00">Entraste con el <b>token de administrador</b> (sin 2.º paso). Úsalo solo para emergencias; para operar, entra con tu usuario.</div>`
      : yo && yo.enrolado
        ? `<div class="row">✅ Tu cuenta <b>${esc(g.yo)}</b> tiene la verificación en dos pasos activa desde ${fecha(yo.desde)} · códigos de recuperación disponibles: <b>${yo.recuperacion_restantes}</b>.</div>
           <div class="actions" style="flex-wrap:wrap;gap:8px">
             <button class="btn-sec" onclick="segRecuperacion()">🧾 Generar códigos de recuperación nuevos</button>
             <button class="btn-sec" onclick="segOlvidar()">📵 Olvidar mis dispositivos de confianza</button>
           </div>`
        : `<div class="row">Tu cuenta <b>${esc(g.yo)}</b> aún no activó el 2.º paso: se te pedirá en tu próximo ingreso.</div>`;
  const filas = g.usuarios.map(u=>`<tr><td style="padding:6px 8px;border-top:1px solid var(--border)">${esc(u.correo)}</td>
      <td style="padding:6px 8px;border-top:1px solid var(--border)">${u.enrolado?'✅ activo desde '+fecha(u.desde):'⏳ pendiente'}</td>
      <td style="padding:6px 8px;border-top:1px solid var(--border);text-align:right">${u.enrolado?`<button class="btn-rc" style="padding:4px 10px;font-size:12px" onclick="segRestablecer('${esc(u.correo)}')">Restablecer 2 pasos</button>`:''}</td></tr>`).join('');
  const accesos = (g.accesos||[]).slice(0,25).map(a=>`<tr><td style="padding:4px 8px;border-top:1px solid var(--border);white-space:nowrap">${fecha(a.ts)}</td>
      <td style="padding:4px 8px;border-top:1px solid var(--border)">${EV[a.evento]||esc(a.evento)}</td>
      <td style="padding:4px 8px;border-top:1px solid var(--border)">${esc(a.usuario||'—')}</td>
      <td style="padding:4px 8px;border-top:1px solid var(--border);color:var(--muted)">${esc(a.ip)} ${esc(a.detalle||'')}</td></tr>`).join('');
  box.innerHTML = `<div class="card"><div class="top"><h3>🔐 Seguridad de la torre</h3></div>
    <div class="row" style="color:var(--muted)">Ingreso con usuario + contraseña + código de app autenticadora (Google/Microsoft Authenticator, Authy). Sesión de ${g.sesion_horas} h; "confiar en este dispositivo" evita el código por ${g.dispositivo_dias} días. Los usuarios se administran en Railway (<code>ADMIN_PANEL_USUARIOS</code>).</div>
    ${estado}
    <div class="row" style="margin-top:12px"><b>Operadores</b></div>
    <table style="width:100%;border-collapse:collapse;font-size:13px"><tbody>${filas||'<tr><td style="padding:6px 8px;color:var(--muted)">Sin usuarios configurados.</td></tr>'}</tbody></table>
    <div class="row" style="margin-top:12px"><b>Últimos accesos</b> <small style="color:var(--muted)">(los 25 más recientes)</small></div>
    <div style="max-height:280px;overflow:auto"><table style="width:100%;border-collapse:collapse;font-size:12.5px"><tbody>${accesos||'<tr><td style="padding:6px 8px;color:var(--muted)">Aún no hay accesos registrados.</td></tr>'}</tbody></table></div>
  </div>`;
}
async function segRestablecer(correo){
  if(!confirm('¿Restablecer la verificación en dos pasos de '+correo+'? En su próximo ingreso tendrá que volver a escanear el QR; sus códigos de recuperación y dispositivos de confianza dejan de valer.')) return;
  const r = await fetch('/admin/api/seguridad/2fa/restablecer',{method:'POST',headers:headers(),body:JSON.stringify({correo})});
  toast(r.ok ? 'Listo: '+correo+' volverá a enrolar su app.' : 'No se pudo restablecer.');
  cargarSeguridad();
}
async function segRecuperacion(){
  const codigo = prompt('Para generar códigos nuevos, escribe el código actual de tu app autenticadora:');
  if(!codigo) return;
  const r = await fetch('/admin/api/seguridad/2fa/recuperacion',{method:'POST',headers:headers(),body:JSON.stringify({codigo})});
  const j = await r.json().catch(()=>({}));
  if(!r.ok){ toast(r.status===401?'Código incorrecto.':'No se pudo generar.'); return; }
  recCodigos = j.recuperacion||[];
  alert('Tus códigos de recuperación NUEVOS (los anteriores ya no valen). Guárdalos ahora, no se vuelven a mostrar:\n\n'+recCodigos.join('\n'));
  descargarRec();
  cargarSeguridad();
}
async function segOlvidar(){
  if(!confirm('¿Olvidar todos tus dispositivos de confianza? La próxima vez, en cada navegador, se pedirá el código otra vez.')) return;
  const r = await fetch('/admin/api/seguridad/dispositivos/olvidar',{method:'POST',headers:headers()});
  if(r.ok) localStorage.removeItem('pichangol_admin_dev');
  toast(r.ok?'Dispositivos olvidados.':'No se pudo.');
  cargarSeguridad();
}

// --- Recargas por QR (Yape directo): el operador verifica y aprueba -------------
async function cargarReclamaciones(){
  const box = document.getElementById('reclamacionesPanel');
  if(!box) return;
  box.innerHTML = '<div class="card">Cargando…</div>';
  try{
    const r = await fetch('/admin/api/reclamaciones',{headers:headers()});
    if(r.status===401){ salir(); return; }
    if(!r.ok){ box.innerHTML='<div class="card">No se pudo cargar.</div>'; return; }
    const j = await r.json();
    const hs = j.reclamaciones||[];
    const esc = s => String(s==null?'':s).replace(/[&<>"]/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
    if(!hs.length){
      box.innerHTML = '<div class="card">Sin hojas de reclamación. Se registran desde el Libro de '
        + 'Reclamaciones de la home pública (<code>/#reclamaciones</code>).</div>';
      return;
    }
    box.innerHTML = `<div class="row" style="margin-bottom:10px;color:var(--muted)">
        ${j.pendientes||0} pendiente(s) de ${j.total||hs.length}. Plazo legal: 15 días hábiles desde la fecha.</div>` +
      hs.map(h=>`
      <div class="card" style="margin-bottom:12px;${h.estado==='pendiente'?'border-left:4px solid #e0a800':''}">
        <div style="display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap">
          <div style="font-weight:800;font-size:15px">${esc(h.numero)} · ${esc(h.detalle&&h.detalle.tipo)}</div>
          <div style="color:#667;font-size:12.5px">${fmtFecha(h.fecha)} · <b>${esc(h.estado)}</b></div>
        </div>
        <div style="font-size:13px;margin-top:6px">
          <b>Consumidor:</b> ${esc(h.consumidor.nombre)} · DNI/CE ${esc(h.consumidor.doc)} ·
          <a href="mailto:${esc(h.consumidor.email)}">${esc(h.consumidor.email)}</a>
          ${h.consumidor.tel?(' · '+esc(h.consumidor.tel)):''}${h.consumidor.menor==='Sí'?' · <b>menor de edad</b>':''}</div>
        <div style="font-size:13px;margin-top:4px"><b>Bien:</b> ${esc(h.bien.tipo)}${h.bien.monto?(' · S/ '+esc(h.bien.monto)):''}${h.bien.desc?(' · '+esc(h.bien.desc)):''}</div>
        <div style="font-size:13px;margin-top:6px;white-space:pre-wrap"><b>Detalle:</b> ${esc(h.detalle.detalle)}</div>
        <div style="font-size:13px;margin-top:4px;white-space:pre-wrap"><b>Pedido:</b> ${esc(h.detalle.pedido)}</div>
        ${h.estado==='pendiente' ? `
        <div style="margin-top:10px;display:flex;gap:8px;flex-wrap:wrap;align-items:center">
          <input id="resp${h.id}" placeholder="Respuesta dada al consumidor (resumen)"
            style="flex:1;min-width:240px;padding:8px;border:1px solid var(--border);border-radius:8px">
          <button class="btn-ap" onclick="atenderReclamacion(${h.id})">✅ Marcar atendida</button>
        </div>` : `<div style="font-size:12.5px;color:#667;margin-top:6px">Atendida ${fmtFecha(h.respondida_en)}${h.respuesta?(' · '+esc(h.respuesta)):''}</div>`}
      </div>`).join('');
  }catch(e){ box.innerHTML='<div class="card">No se pudo cargar.</div>'; }
}
async function atenderReclamacion(id){
  const respuesta = (document.getElementById('resp'+id)||{}).value||'';
  if(!confirm('¿Marcar la hoja como atendida? Recuerda enviar la respuesta formal al correo del consumidor.')) return;
  const r = await fetch('/admin/api/reclamaciones/'+id+'/atender',{method:'POST',headers:headers(),
    body:JSON.stringify({respuesta})});
  if(r.status===401){ salir(); return; }
  if(r.ok){ toast('Hoja atendida'); await cargarReclamaciones(); }
  else toast('No se pudo guardar');
}
async function cargarCancelacionesWeb(){
  const box = document.getElementById('cancelacionesPanel');
  if(!box) return;
  box.innerHTML = '<div class="card">Cargando…</div>';
  try{
    const r = await fetch('/pagos/cancelaciones-web',{headers:headers()});
    if(r.status===401){ salir(); return; }
    if(!r.ok){ box.innerHTML='<div class="card">No se pudo cargar.</div>'; return; }
    const j = await r.json();
    const cs = j.cancelaciones||[];
    const esc = s => String(s==null?'':s).replace(/[&<>"]/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
    const ETQ = {reembolsado:['Reembolso Culqi hecho','#1F6E49'], reembolsado_manual:['Devuelto a mano','#1F6E49'], manual:['Devolver a mano (pagó en el app)','#946200'],
                 fallo:['Culqi rechazó el reembolso: devolver a mano','#C0392B'], sin_reembolso:['Sin devolución (< 6 h)','#667'], no_aplica:['Pagaba en la cancha · sin costo','#667']};
    const mon = c => (c.moneda||'S/')+' '+Number(c.monto||0).toFixed(2);
    if(!cs.length){ box.innerHTML = '<div class="card">Sin cancelaciones desde la web todavía. Se registran cuando un jugador cancela en <code>/mis-reservas</code> o en su comprobante.</div>'; return; }
    box.innerHTML = `<div class="row" style="margin-bottom:10px;color:var(--muted)">
        ${j.pendientes||0} por atender de ${j.total||cs.length}. Regla: con 6 h o más y pagada, devolución del 100 %; el cargo web se reembolsa solo en Culqi; lo pagado en el app o lo que Culqi rechazó se devuelve a mano.</div>` +
      cs.map(c=>{
        const pendRe = c.reembolso==='manual'||c.reembolso==='fallo';
        const pendDe = (c.deuda_dueno_centimos||0)>0 && !c.deuda_resuelta;
        const et = ETQ[c.reembolso]||[c.reembolso,'#667'];
        return `<div class="card" style="margin-bottom:12px;${(pendRe||pendDe)?'border-left:4px solid #e0a800':''}">
        <div style="display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap">
          <div style="font-weight:800;font-size:15px">${esc(c.cancha||'Cancha')}${c.club?(' · '+esc(c.club)):''} · ${esc(c.fecha)} ${esc(c.hora_inicio)}–${esc(c.hora_fin)}${c.turnos>1?(' · '+c.turnos+' turnos'):''}</div>
          <div style="color:#667;font-size:12.5px">${fmtFecha(c.creado_en)} · canceló ${Number(c.horas_antes||0).toFixed(1)} h antes</div>
        </div>
        <div style="font-size:13px;margin-top:6px"><b>Jugador:</b> <a href="mailto:${esc(c.usuario)}">${esc(c.usuario)}</a> · <b>Monto:</b> ${mon(c)}${c.pagado?'':' (no pagado)'}
          · <b>Dueño:</b> ${esc(c.dueno||'—')} · <b>Ref:</b> <code>${esc(c.ref)}</code>${c.refund_id?(' · Culqi <code>'+esc(c.refund_id)+'</code>'):''}</div>
        <div style="font-size:13px;margin-top:6px"><span style="font-weight:800;color:${et[1]}">● ${esc(et[0])}</span>${c.detalle?(' · <span style="color:#C0392B">'+esc(c.detalle)+'</span>'):''}
          ${c.resuelto_en?(' · devuelto '+fmtFecha(c.resuelto_en)+(c.referencia?(' · '+esc(c.referencia)):'')):''}</div>
        ${(c.deuda_dueno_centimos||0)>0 ? `<div style="font-size:13px;margin-top:6px;color:${c.deuda_resuelta?'#1F6E49':'#C0392B'}"><b>Deuda del dueño:</b> ${esc(c.moneda||'S/')} ${(c.deuda_dueno_centimos/100).toFixed(2)} — ya se le había liquidado esta reserva${c.deuda_resuelta?(' · descontada '+fmtFecha(c.deuda_resuelta_en)+(c.deuda_referencia?(' · '+esc(c.deuda_referencia)):'')):': descontar en su siguiente liquidación'}</div>`:''}
        ${(pendRe||pendDe) ? `<div style="margin-top:10px;display:flex;gap:8px;flex-wrap:wrap;align-items:center">
          <input id="refc${c.id}" placeholder="Nº de operación / nota" style="flex:1;min-width:220px;padding:8px;border:1px solid var(--border);border-radius:8px">
          ${pendRe?`<button class="btn-ap" onclick="resolverCancelacion(${c.id},'devuelto')">✅ Marcar devuelto (${mon(c)})</button>`:''}
          ${pendDe?`<button class="btn-ap" onclick="resolverCancelacion(${c.id},'descontado')">➖ Marcar deuda descontada</button>`:''}
        </div>`:''}
      </div>`;}).join('');
  }catch(e){ box.innerHTML='<div class="card">No se pudo cargar.</div>'; }
}
async function resolverCancelacion(id, accion){
  const referencia = (document.getElementById('refc'+id)||{}).value||'';
  const txt = accion==='devuelto' ? '¿Confirmas que YA devolviste el dinero al jugador (Yape/transferencia)?' : '¿Confirmas que ya descontaste la deuda en la liquidación del dueño?';
  if(!confirm(txt)) return;
  const r = await fetch('/pagos/cancelaciones-web/'+id+'/resolver',{method:'POST',headers:headers(),body:JSON.stringify({accion, referencia})});
  if(r.status===401){ salir(); return; }
  const j = r.ok ? await r.json() : {ok:false};
  if(j.ok){ toast('Guardado'); await cargarCancelacionesWeb(); } else toast('No se pudo guardar');
}
async function cargarRecargasQr(){
  const box = document.getElementById('recargasQr');
  if(!box) return;
  box.innerHTML = '<div class="card">Cargando…</div>';
  try{
    const r = await fetch('/pagos/recargas-qr',{headers:headers()});
    if(!r.ok){ box.innerHTML='<div class="card">No se pudo cargar.</div>'; return; }
    const j = await r.json();
    const sols = j.solicitudes||[];
    if(!sols.length){
      box.innerHTML = '<div class="card">Sin solicitudes de recarga por QR. '
        + 'Aparecerán aquí cuando un usuario yapee al QR y suba su constancia.</div>';
      return;
    }
    box.innerHTML = sols.map(s=>`
      <div class="card" style="margin-bottom:12px">
        <div style="display:flex;gap:14px;align-items:flex-start;flex-wrap:wrap">
          ${s.foto_url
            ? `<a href="${s.foto_url}" target="_blank" title="Ver constancia completa">
                 <img src="${s.foto_url}" style="width:110px;height:140px;object-fit:cover;border-radius:10px;border:1px solid var(--border)"></a>`
            : `<div style="width:110px;height:140px;border-radius:10px;background:#f2f2f2;display:flex;align-items:center;justify-content:center;color:#889;font-size:12px">sin<br>constancia</div>`}
          <div style="flex:1;min-width:220px">
            <div style="font-weight:800;font-size:16px">S/ ${Number(s.monto_soles||0).toFixed(2)} · ${s.email}</div>
            <div style="color:#667;font-size:12.5px;margin-top:2px">
              ${fmtFecha(s.creado_en)} · <b>${s.estado}</b>${s.motivo?(' · '+s.motivo):''}</div>
            ${s.estado==='pendiente' ? `
            <div style="margin-top:10px;display:flex;gap:8px;flex-wrap:wrap;align-items:center">
              <button class="btn-ap" onclick="resolverRecargaQr(${s.id},'aprobar')">✅ Aprobar (verifiqué el Yape)</button>
              <select id="motivoRq${s.id}" style="padding:8px;border-radius:10px;border:1px solid var(--border)">
                <option value="no_llego">No llegó el Yape</option>
                <option value="monto_no_coincide">Monto no coincide</option>
                <option value="constancia_ilegible">Constancia ilegible</option>
              </select>
              <button class="btn-rc" onclick="resolverRecargaQr(${s.id},'rechazar')">Rechazar</button>
            </div>` : ''}
          </div>
        </div>
      </div>`).join('');
  }catch(e){ box.innerHTML='<div class="card">Error de red.</div>'; }
}
async function resolverRecargaQr(id, accion){
  let body = '{}';
  if(accion==='rechazar'){
    const sel = document.getElementById('motivoRq'+id);
    body = JSON.stringify({motivo: sel ? sel.value : 'no_llego'});
  } else if(!confirm('¿Verificaste el Yape en la app y el monto coincide?')){
    return;
  }
  const r = await fetch('/pagos/recarga-qr/'+id+'/'+accion,
    {method:'POST',headers:headers(),body:body});
  if(r.ok){ cargarRecargasQr(); } else { alert('No se pudo ('+r.status+').'); }
}

// --- Promociones: bono de recarga (config) + cupones de saldo -------------------
async function cargarPromos(){
  const box = document.getElementById('promosPanel');
  if(!box) return;
  box.innerHTML = '<div class="card">Cargando…</div>';
  try{
    const [rb, rc] = await Promise.all([
      fetch('/pagos/promos/admin',{headers:headers()}),
      fetch('/pagos/cupones',{headers:headers()}),
    ]);
    if(!rb.ok || !rc.ok){ box.innerHTML='<div class="card">No se pudo cargar.</div>'; return; }
    const b = await rb.json();
    const cupones = (await rc.json()).cupones||[];
    box.innerHTML = `
      <div class="card" style="margin-bottom:12px">
        <div style="font-weight:800;font-size:15px;margin-bottom:4px">🎁 Bono de recarga</div>
        <div style="color:#667;font-size:12.5px;margin-bottom:10px">
          "Recarga S/ ${b.min} o más y te regalamos ${b.pct}% extra (máx S/ ${b.tope})".
          Lo paga Pichangol. <b>0% = promo apagada.</b></div>
        <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:end">
          <label style="font-size:12px">% extra<br>
            <input id="promoPct" type="number" min="0" max="100" step="1" value="${b.pct}"
              style="width:90px;padding:8px;border-radius:10px;border:1px solid var(--border)"></label>
          <label style="font-size:12px">Recarga mínima (S/)<br>
            <input id="promoMin" type="number" min="0" step="1" value="${b.min}"
              style="width:110px;padding:8px;border-radius:10px;border:1px solid var(--border)"></label>
          <label style="font-size:12px">Tope del bono (S/)<br>
            <input id="promoTope" type="number" min="0" step="1" value="${b.tope}"
              style="width:110px;padding:8px;border-radius:10px;border:1px solid var(--border)"></label>
          <button class="btn-ap" onclick="guardarPromoBono()">Guardar</button>
        </div>
      </div>
      <div class="card">
        <div style="font-weight:800;font-size:15px;margin-bottom:4px">🎟️ Cupones de saldo</div>
        <div style="color:#667;font-size:12.5px;margin-bottom:10px">Para campañas con
          academias, sorteos o disculpas. Un canje por usuario por cupón.</div>
        <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:end;margin-bottom:12px">
          <label style="font-size:12px">Código (vacío = automático)<br>
            <input id="cupCod" placeholder="BIENVENIDA"
              style="width:150px;padding:8px;border-radius:10px;border:1px solid var(--border)"></label>
          <label style="font-size:12px">Valor (S/)<br>
            <input id="cupVal" type="number" min="1" max="500" value="10"
              style="width:90px;padding:8px;border-radius:10px;border:1px solid var(--border)"></label>
          <label style="font-size:12px">Usos máx.<br>
            <input id="cupUsos" type="number" min="1" max="10000" value="100"
              style="width:90px;padding:8px;border-radius:10px;border:1px solid var(--border)"></label>
          <button class="btn-ap" onclick="crearCupon()">Crear cupón</button>
        </div>
        ${cupones.length ? cupones.map(c=>`
          <div style="display:flex;gap:10px;align-items:center;padding:8px 0;border-top:1px solid var(--border);flex-wrap:wrap">
            <b style="font-family:monospace">${c.codigo}</b>
            <span>S/ ${Number(c.valor_soles).toFixed(2)}</span>
            <span style="color:#667;font-size:12.5px">${c.usados}/${c.usos_max} usados</span>
            <span style="font-size:12px;font-weight:700;color:${c.activo?'var(--bosque)':'#999'}">${c.activo?'activo':'desactivado'}</span>
            ${c.activo?`<button class="btn-rc" onclick="desactivarCupon('${c.codigo}')">Desactivar</button>`:''}
          </div>`).join('') : '<div style="color:#889">Aún no hay cupones.</div>'}
      </div>`;
  }catch(e){ box.innerHTML='<div class="card">Error de red.</div>'; }
}
async function guardarPromoBono(){
  const body = JSON.stringify({
    pct: Number(document.getElementById('promoPct').value||0),
    minimo: Number(document.getElementById('promoMin').value||0),
    tope: Number(document.getElementById('promoTope').value||0)});
  const r = await fetch('/pagos/promos/admin',{method:'POST',headers:headers(),body});
  if(r.ok){ cargarPromos(); } else { alert('Valores inválidos.'); }
}
async function crearCupon(){
  const body = JSON.stringify({
    codigo: document.getElementById('cupCod').value||'',
    valor_soles: Number(document.getElementById('cupVal').value||0),
    usos_max: Number(document.getElementById('cupUsos').value||0)});
  const r = await fetch('/pagos/cupones',{method:'POST',headers:headers(),body});
  if(r.ok){ cargarPromos(); }
  else if(r.status===409){ alert('Ese código ya existe.'); }
  else { alert('Datos inválidos (valor 1–500, usos 1–10000).'); }
}
async function desactivarCupon(codigo){
  if(!confirm('¿Desactivar el cupón '+codigo+'? Ya no se podrá canjear.')) return;
  const r = await fetch('/pagos/cupones/'+encodeURIComponent(codigo)+'/desactivar',
    {method:'POST',headers:headers()});
  if(r.ok) cargarPromos();
}

// --- Identidad (DNI): revocar la verificación 1 DNI = 1 cuenta ------------------
async function cargarDni(){
  const box = document.getElementById('dniPanel');
  if(!box) return;
  try{
    const r = await fetch('/admin/api/dni/verificaciones',{headers:headers()});
    if(!r.ok){ box.innerHTML='<div class="card">No se pudo cargar.</div>'; return; }
    const j = await r.json();
    const cuentas = j.cuentas||[];
    const filas = cuentas.length ? cuentas.map(c=>`
      <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;padding:12px 0;border-top:1px solid var(--border)">
        <div style="min-width:0">
          <b style="word-break:break-all">${esc(c.email)}</b>
          <div style="color:var(--muted);font-size:12px">
            ${c.dnis} DNI · hash ${c.hashes.map(esc).join(', ')}…</div>
        </div>
        <button onclick="revocarDni('${esc(c.email)}')"
          style="background:#fff;color:#C13515;border:1px solid #C13515;border-radius:12px;padding:9px 12px;font-family:inherit;font-weight:700;cursor:pointer;white-space:nowrap">
          Revocar</button>
      </div>`).join('')
      : '<div style="color:var(--muted);padding:8px 0">Aún no hay DNI verificados.</div>';
    box.innerHTML = `<div class="card"><div class="top">
      <h3 style="flex:1">DNI verificados</h3>
      <span style="font-weight:800;color:var(--bosque)">${j.total||0}</span></div>
      <p style="color:var(--muted);font-size:13px;margin:6px 0 4px">
        Cada DNI (guardado solo como hash, nunca el número) queda ligado a una
        cuenta. <b>Revocar</b> libera ese DNI para que se pueda volver a verificar
        en la cuenta correcta. Ojo: el estado "verificado" del lado app (Supabase)
        se limpia aparte desde la app del usuario.</p>
      ${filas}</div>`;
  }catch(e){ box.innerHTML='<div class="card">Error al cargar.</div>'; }
}

async function revocarDni(email){
  if(!confirm('¿Revocar la verificación de DNI de '+email+'? Ese DNI quedará libre para volver a verificarse.')) return;
  const r = await fetch('/admin/api/dni/revocar',
    {method:'POST',headers:headers(),body:JSON.stringify({email})});
  if(r.ok){ cargarDni(); } else { alert('No se pudo revocar.'); }
}

// --- Disputas del marketplace: el operador libera al vendedor o reembolsa ------
async function cargarDisputas(){
  const box = document.getElementById('disputas');
  if(!box) return;
  try{
    const r = await fetch('/admin/api/ventas/disputas',{headers:headers()});
    if(!r.ok){ box.innerHTML='<div class="card">No se pudo cargar.</div>'; return; }
    const j = await r.json();
    const d = j.disputas||[];
    kpi.disputas = d.length; renderResumen();
    const filas = d.length ? d.map(v=>`
      <div style="padding:14px 0;border-top:1px solid var(--border)">
        <div style="display:flex;justify-content:space-between;gap:10px">
          <div>
            <b>${esc(v.producto_nombre)||'Producto'}</b>
            <div style="color:var(--muted);font-size:13px">
              Comprador: ${esc(v.comprador_nombre)||esc(v.comprador_email)} ·
              Vendedor: ${esc(v.vendedor_nombre)||esc(v.vendedor_email)}</div>
            <div style="color:var(--muted);font-size:12px">${fmtFecha(v.creado_en)}</div>
          </div>
          <div style="text-align:right;white-space:nowrap">
            <div style="font-weight:800;font-size:17px">S/${v.monto_soles}</div>
            <div style="color:var(--muted);font-size:12px">neto S/${v.neto_soles}</div>
          </div>
        </div>
        <div style="display:flex;gap:8px;margin-top:10px">
          <button onclick="resolverDisputa(${v.id},'liberar')"
            style="background:var(--bosque);color:var(--lima);border:0;border-radius:12px;padding:9px 12px;font-family:inherit;font-weight:700;cursor:pointer">
            Liberar al vendedor</button>
          <button onclick="resolverDisputa(${v.id},'reembolsar')"
            style="background:#fff;color:#C13515;border:1px solid #C13515;border-radius:12px;padding:9px 12px;font-family:inherit;font-weight:700;cursor:pointer">
            Reembolsar al comprador</button>
        </div>
      </div>`).join('')
      : '<div style="color:var(--muted);padding:8px 0">No hay disputas abiertas. 🎉</div>';
    box.innerHTML = `<div class="card"><div class="top">
      <h3 style="flex:1">Órdenes en disputa</h3>
      <span style="font-weight:800;color:var(--bosque)">${d.length}</span></div>
      <p style="color:var(--muted);font-size:13px;margin:6px 0 4px">
        El comprador reportó un problema. Revisa (chat/pruebas) y decide: liberar
        el pago al vendedor, o reembolsar al comprador (devuelves fuera de la app).</p>
      ${filas}</div>`;
  }catch(e){ box.innerHTML='<div class="card">Error al cargar disputas.</div>'; }
}

async function resolverDisputa(id, accion){
  const txt = accion==='liberar'
    ? '¿Liberar el pago al VENDEDOR?'
    : '¿Reembolsar al COMPRADOR? (el neto NO se libera; devuélvelo fuera de la app)';
  if(!confirm(txt)) return;
  const r = await fetch('/admin/api/venta/'+id+'/resolver',
    {method:'POST',headers:headers(),body:JSON.stringify({accion})});
  if(r.ok){ cargarDisputas(); } else { alert('No se pudo resolver.'); }
}

// --- Liquidaciones: pagos pendientes de Pichangol al dueño (reservas online) ---
async function cargarLiquidaciones(){
  const box = document.getElementById('liquidaciones');
  try{
    // no-store: sin esto el navegador puede CACHEAR el GET y, tras marcar un
    // pago, la lista se re-pintaba con la respuesta VIEJA (bug reportado por
    // el director: "tengo que refrescar para ver el cambio").
    const r = await fetch('/pagos/liquidaciones/pendientes',
        {headers:headers(), cache:'no-store'});
    if(!r.ok){ box.innerHTML=''; return; }
    const j = await r.json();
    const pend = j.pendientes||[];
    const cuentas = j.cuentas||{}; liqBcp = j.bcp||{cuenta:'',tipo:'C'}; liqLotes = j.lotes||[];
    kpi.liqTotal = j.total_neto_soles||0; kpi.liqN = pend.length; kpi.liqAtras = j.atrasadas||0; kpi.liqDias = j.mas_antigua_dias||0; renderResumen();
    const AVISO = j.aviso_dias||3;
    if(!pend.length){
      box.innerHTML = `<div class="card" style="text-align:center;padding:44px 20px">
        <div style="font-size:36px">🎉</div>
        <div style="font-weight:800;font-size:17px;margin-top:8px">Todo liquidado</div>
        <div style="color:var(--muted);font-size:13.5px;margin-top:4px">No tienes pagos pendientes a dueños.</div>
      </div>` + lotesHtml();
      return;
    }
    // Desarma el concepto "Local · Cancha · Jugador · Día hora" para agrupar
    // por LOCAL y sub-agrupar por CANCHA (pedido del director: cuánto se lleva
    // cada local, cada cancha y cuánto le toca a Pichangol).
    const partes = c => (c||'').split(' · ');
    const localDe = p => partes(p.concepto)[0] || (p.dueno_id||'—');
    const canchaDe = p => { const s = partes(p.concepto);
      return s.length >= 4 ? s[1] : s[0] || '—'; };
    const restoDe = p => { const s = partes(p.concepto);
      return s.slice(s.length >= 4 ? 2 : 1).join(' · '); };
    const S = n => 'S/ ' + (Math.round(n*100)/100).toFixed(2);

    // Totales GLOBALES (lo que realmente le toca a Pichangol = la comisión).
    let gBruto=0, gCom=0, gNeto=0;
    const grupos = new Map(); // "local||dueño" → {local, dueno, items}
    for(const p of pend){
      gBruto += p.bruto_soles||0; gCom += p.comision_soles||0; gNeto += p.neto_soles||0;
      const k = localDe(p) + '||' + (p.dueno_id||'');
      if(!grupos.has(k)) grupos.set(k, {local: localDe(p), dueno: p.dueno_id||'—', items: []});
      grupos.get(k).items.push(p);
    }

    const bloques = [...grupos.values()].map(g=>{
      const bruto = g.items.reduce((a,p)=>a+(p.bruto_soles||0),0);
      const com   = g.items.reduce((a,p)=>a+(p.comision_soles||0),0);
      const neto  = g.items.reduce((a,p)=>a+(p.neto_soles||0),0);
      // Subtotales por CANCHA dentro del local.
      const porCancha = new Map();
      for(const p of g.items){
        const c = canchaDe(p);
        if(!porCancha.has(c)) porCancha.set(c, {n:0, bruto:0, neto:0});
        const x = porCancha.get(c); x.n++; x.bruto += p.bruto_soles||0; x.neto += p.neto_soles||0;
      }
      const chipsCancha = [...porCancha.entries()].map(([c,x])=>
        `<span class="liq-cancha">${esc(c)} · ${x.n} ${x.n===1?'reserva':'reservas'} · neto ${S(x.neto)}</span>`).join('');
      const filas = g.items.map(p=>`
        <div class="liq-row"${(p.dias||0)>=AVISO?' style="border-left:3px solid #F04438;padding-left:10px"':''}>
          <div style="min-width:0">
            <div class="liq-dueno">${esc(canchaDe(p))}${(p.dias||0)>=AVISO?` <span style="color:#B42318;font-size:12px;font-weight:800">· hace ${p.dias} días</span>`:''}</div>
            <div class="liq-det">${esc(restoDe(p))} · ${fmtFecha(p.creado_en)}</div>
          </div>
          <div class="liq-der">
            <div class="liq-monto" title="Bruto ${S(p.bruto_soles||0)} − comisión Pichangol ${S(p.comision_soles||0)}">${S(p.neto_soles||0)}</div>
            <button class="liq-btn" onclick="pagarLiquidacion('${esc(p.reserva_id)}','${S(p.neto_soles||0)}')">Marcar pagado</button>
          </div>
        </div>`).join('');
      const cta = cuentas[g.dueno] || {tiene:false};
      const ctaHtml = cta.tiene
        ? `<div class="liq-cuenta">${cta.canal==='archivo'?'🏦':'📱'} <span>${esc(cta.etiqueta)}</span>
             <button class="liq-copy" onclick="copiarTexto('${esc(cta.cuenta_pago||cta.numero||'')}')" title="Copiar ${cta.cci?'CCI':'número'}">⧉ Copiar</button>
             ${cta.canal==='archivo'?'<span class="liq-tag ok">entra al lote BCP</span>':'<span class="liq-tag">pago a mano</span>'}</div>`
        : `<div class="liq-cuenta sin">⚠️ Sin cuenta de cobro: el dueño aún no registró dónde recibir (Billetera → Cuenta de cobro, en la app o en Ingresos de la web).</div>`;
      return `
      <div class="card" style="padding:16px 18px;margin-bottom:14px">
        <div class="liq-grupo-top">
          <div style="min-width:0">
            <div class="liq-grupo-local">${esc(g.local)}</div>
            <div class="liq-grupo-dueno">${esc(g.dueno)} · ${g.items.length} ${g.items.length===1?'pago pendiente':'pagos pendientes'}</div>
            ${ctaHtml}
          </div>
          <div class="liq-grupo-tot">
            <span class="liq-mini">Bruto ${S(bruto)}</span>
            <span class="liq-mini liq-mini-pcg">Pichangol ${S(com)}</span>
            <span class="liq-mini liq-mini-neto">Al dueño ${S(neto)}</span>
          </div>
        </div>
        ${porCancha.size > 1 ? `<div class="liq-canchas">${chipsCancha}</div>` : ''}
        <div style="margin-top:4px">${filas}</div>
      </div>`;
    }).join('');

    const atras = pend.filter(p=>(p.dias||0)>=AVISO);
    const banner = atras.length ? `<div class="card" style="border-left:4px solid #F04438;background:#FFF4F2;padding:12px 16px;margin-bottom:12px">
        <b style="color:#B42318">⏰ ${atras.length} ${atras.length===1?'liquidación lleva':'liquidaciones llevan'} ${AVISO}+ días sin pagar</b>
        <span style="color:var(--muted);font-size:13px"> · ${S(atras.reduce((a,p)=>a+(p.neto_soles||0),0))} · la más antigua hace ${j.mas_antigua_dias||0} días. Pichangol le debe esta plata a dueños y organizadores: transfiere y marca pagado. El recordatorio diario por WhatsApp sigue hasta que quede en cero.</span>
      </div>` : '';
    box.innerHTML = `${banner}
      <div class="liq-head">
        <div>
          <div class="liq-total">${S(gNeto)}</div>
          <div class="liq-sub">${pend.length===1?'1 pago pendiente':pend.length+' pagos pendientes'} · reservas online, ventas y torneos (🏆) · transfiere el neto (Yape/banco) y márcalo</div>
          <div class="liq-resumen">
            <span class="liq-mini">Bruto cobrado ${S(gBruto)}</span>
            <span class="liq-mini liq-mini-pcg">Comisión Pichangol ${S(gCom)}</span>
            <span class="liq-mini liq-mini-neto">Neto a dueños ${S(gNeto)}</span>
          </div>
        </div>
        <div><button class="liq-btn" style="padding:11px 18px;font-size:14px" onclick="abrirLote()">📦 Liquidar por lote (BCP)</button></div>
      </div>
      ${bloques}${lotesHtml()}`;
  }catch(e){ box.innerHTML=''; }
}
// ── Liquidación POR LOTE: agrupa por dueño, archivo Telecrédito BCP, marca todo pagado ──
let liqBcp = {cuenta:'', tipo:'C'}, liqLotes = [], loteActual = null;
function copiarTexto(t){ if(!t) return; navigator.clipboard.writeText(t).then(()=>toast('Copiado ✓')).catch(()=>toast(t)); }
function lotesHtml(){
  if(!liqLotes.length) return '';
  const S = n => 'S/ ' + (Math.round(n*100)/100).toFixed(2);
  return `<div class="card" style="padding:14px 18px;margin-top:6px">
    <div style="font-weight:800;font-size:14px;margin-bottom:6px">Lotes de liquidación</div>
    ${liqLotes.map(l=>`<div class="liq-lote">
      <span>${fmtFecha(l.creado_en)} · <b>${esc(l.id)}</b> · ${l.n_archivo} al BCP por ${S(l.total_archivo_soles)}${l.total_manual_soles?` · a mano ${S(l.total_manual_soles)}`:''}${l.referencia?` · ref ${esc(l.referencia)}`:''}</span>
      <span>${l.estado==='pagado'?'<span class="liq-tag ok">pagado</span>':'<span class="liq-tag">preparado</span>'}
        <button class="liq-copy" onclick="descargarLote('${esc(l.id)}','csv')">CSV</button>
        ${l.n_archivo?`<button class="liq-copy" onclick="descargarLote('${esc(l.id)}','txt')">TXT BCP</button>`:''}</span>
    </div>`).join('')}
  </div>`;
}
async function descargarLote(id, tipo){
  const url = '/pagos/liquidaciones/lote/'+encodeURIComponent(id)+(tipo==='txt'?'/telecredito.txt':'/detalle.csv');
  const r = await fetch(url,{headers:headers(), cache:'no-store'});
  if(!r.ok){ let m='No se pudo generar el archivo.'; try{ m = (await r.json()).detail || m; }catch(e){} toast(m); return; }
  const blob = await r.blob(); const a = document.createElement('a');
  a.href = URL.createObjectURL(blob); a.download = 'pichangol_'+id+(tipo==='txt'?'_bcp.txt':'.csv'); document.body.appendChild(a); a.click();
  setTimeout(()=>{ URL.revokeObjectURL(a.href); a.remove(); }, 800);
}
async function abrirLote(){
  const ov = document.createElement('div');
  ov.style.cssText = 'position:fixed;inset:0;background:rgba(10,20,15,.45);display:flex;align-items:center;justify-content:center;z-index:9999;padding:16px';
  ov.innerHTML = `<div style="background:#fff;border-radius:18px;max-width:760px;width:100%;max-height:92vh;overflow:auto;padding:20px 22px;box-shadow:0 18px 50px rgba(0,0,0,.25)">
      <div style="display:flex;justify-content:space-between;align-items:center;gap:10px">
        <div><div style="font-weight:800;font-size:17px">Liquidar por lote · Telecrédito BCP</div>
        <div style="color:var(--muted);font-size:13px;margin-top:2px">Una transferencia por dueño. Descarga la planilla, cárgala en Telecrédito Web (Pagos → Pago a proveedores), fírmala y luego marca el lote como pagado.</div></div>
        <button id="lt_x" style="border:0;background:transparent;font-size:22px;cursor:pointer">✕</button>
      </div>
      <div class="lt-grid">
        <div><div class="lt-lbl">Cuenta BCP de cargo (EBIM)</div>
          <div style="display:flex;gap:6px"><input id="lt_cta" value="${esc(liqBcp.cuenta||'')}" placeholder="13 o 14 dígitos" style="flex:1;padding:9px 10px;border:1px solid var(--border);border-radius:10px">
          <select id="lt_tipo" style="padding:9px;border:1px solid var(--border);border-radius:10px"><option value="C"${liqBcp.tipo==='C'?' selected':''}>Corriente</option><option value="A"${liqBcp.tipo==='A'?' selected':''}>Ahorros</option><option value="M"${liqBcp.tipo==='M'?' selected':''}>Maestra</option></select>
          <button class="liq-copy" id="lt_guardar_cta">Guardar</button></div></div>
        <div><div class="lt-lbl">Mínimo por dueño (se posterga lo menor)</div>
          <div id="lt_umbral" class="lt-chips"><button data-u="0" class="mp-chip">Sin mínimo</button><button data-u="20" class="mp-chip">S/ 20</button><button data-u="50" class="mp-chip">S/ 50</button><button data-u="100" class="mp-chip">S/ 100</button></div></div>
      </div>
      <div id="lt_body" style="margin-top:14px;color:var(--muted);font-size:13px">Preparando…</div>
      <div id="lt_acc" style="display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end;margin-top:16px"></div>
    </div>`;
  document.body.appendChild(ov);
  let umbral = 50;
  const chips = ov.querySelectorAll('#lt_umbral .mp-chip');
  const pintarChips = ()=>chips.forEach(b=>{ const on = +b.dataset.u===umbral;
    b.style.cssText='padding:7px 12px;border-radius:999px;font-weight:700;cursor:pointer;border:1px solid var(--border);background:'+(on?'#EBEBEB':'#fff'); });
  pintarChips();
  const cerrar = ()=>ov.remove();
  ov.querySelector('#lt_x').onclick = cerrar;
  ov.onclick = e=>{ if(e.target===ov) cerrar(); };
  ov.querySelector('#lt_guardar_cta').onclick = async ()=>{
    const r = await fetch('/pagos/liquidaciones/config-bcp',{method:'POST',headers:headers(),body:JSON.stringify({cuenta:ov.querySelector('#lt_cta').value, tipo:ov.querySelector('#lt_tipo').value})});
    if(r.ok){ liqBcp = await r.json(); toast('Cuenta de cargo guardada ✓'); } else { let m='No se pudo guardar.'; try{ m=(await r.json()).detail||m; }catch(e){} toast(m); }
  };
  const S = n => 'S/ ' + (Math.round(n)/100).toFixed(2);
  async function preparar(){
    ov.querySelector('#lt_body').innerHTML = 'Preparando…';
    const r = await fetch('/pagos/liquidaciones/lote/preparar',{method:'POST',headers:headers(),body:JSON.stringify({moneda:'PEN', umbral_soles:umbral})});
    if(!r.ok){ ov.querySelector('#lt_body').innerHTML = 'No se pudo preparar el lote.'; return; }
    const j = await r.json(); loteActual = j.lote; liqBcp = j.bcp||liqBcp;
    const L = loteActual;
    const fila = f => `<div class="liq-lote"><span><b>${esc(f.dueno)}</b> · ${f.n} ${f.n===1?'pago':'pagos'}<br><small style="color:var(--muted)">${esc((f.cuenta||{}).etiqueta||'Sin cuenta de cobro')}</small></span><b>${S(f.neto_centimos)}</b></div>`;
    const grupo = (titulo, canal, nota) => { const fs = L.filas.filter(f=>f.canal===canal); if(!fs.length) return '';
      return `<div style="margin-top:12px"><div style="font-weight:800;font-size:13.5px">${titulo} <span style="color:var(--muted);font-weight:600">· ${fs.length} · ${S(fs.reduce((a,f)=>a+f.neto_centimos,0))}</span></div><div style="color:var(--muted);font-size:12px">${nota}</div>${fs.map(fila).join('')}</div>`; };
    ov.querySelector('#lt_body').innerHTML =
      (L.filas.length ? '' : '<div class="anf-vacio">No hay liquidaciones pendientes en soles.</div>') +
      grupo('🏦 Entran al archivo BCP', 'archivo', 'Cuentas bancarias peruanas: una transferencia por dueño en la planilla.') +
      grupo('📱 Pagar a mano', 'manual', 'Yape / Plin u otro país: Telecrédito no los cubre. Págalos desde tu app y marca la casilla al confirmar.') +
      grupo('⏳ Bajo el mínimo', 'bajo_umbral', 'Se acumulan para el próximo lote.') +
      grupo('⚠️ Sin cuenta de cobro', 'sin_cuenta', 'Pídele al dueño que la registre en su billetera (app o web). Mientras tanto no se puede pagar.');
    ov.querySelector('#lt_acc').innerHTML =
      `<button class="liq-copy" id="lt_csv">⬇ CSV del lote</button>
       <button class="liq-copy" id="lt_txt" ${L.n_archivo?'':'disabled'}>⬇ Planilla Telecrédito (.txt)</button>
       <label style="font-size:12.5px;display:flex;align-items:center;gap:6px"><input type="checkbox" id="lt_man"> Ya pagué también los de Yape/otro país</label>
       <input id="lt_ref" placeholder="N.º de planilla / referencia" style="padding:9px 10px;border:1px solid var(--border);border-radius:10px;min-width:200px">
       <button class="liq-btn" id="lt_ok" ${(L.n_archivo||L.filas.some(f=>f.canal==='manual'))?'':'disabled'}>✅ Marcar lote pagado</button>`;
    ov.querySelector('#lt_csv').onclick = ()=>descargarLote(L.id,'csv');
    ov.querySelector('#lt_txt').onclick = ()=>{ if(!(liqBcp.cuenta||'').length){ toast('Guarda primero la cuenta BCP de cargo.'); return; } descargarLote(L.id,'txt'); };
    ov.querySelector('#lt_ok').onclick = async ()=>{
      const inc = ov.querySelector('#lt_man').checked, ref = ov.querySelector('#lt_ref').value.trim();
      const n = L.filas.filter(f=>f.canal==='archivo'||(inc&&f.canal==='manual')).length;
      if(!n){ toast('No hay nada que marcar en este lote.'); return; }
      if(!(await confirmarModal('Marcar '+n+' dueño(s) como pagados', 'Solo hazlo si la planilla ya está firmada en Telecrédito'+(inc?' y pagaste a mano los de Yape/otro país':'')+'. Las liquidaciones quedarán como pagadas con la referencia '+(ref||L.id)+'.'))) return;
      const r = await fetch('/pagos/liquidaciones/lote/'+encodeURIComponent(L.id)+'/pagado',{method:'POST',headers:headers(),body:JSON.stringify({referencia:ref, incluir_manuales:inc})});
      if(r.ok){ const j = await r.json(); toast(j.marcadas+' liquidaciones marcadas como pagadas ✓'); cerrar(); await cargarLiquidaciones(); }
      else toast('No se pudo marcar el lote.');
    };
  }
  chips.forEach(b=>b.onclick=()=>{ umbral=+b.dataset.u; pintarChips(); preparar(); });
  preparar();
}
function confirmarModal(titulo, mensaje){
  return new Promise(res=>{
    const ov = document.createElement('div');
    ov.style.cssText = 'position:fixed;inset:0;background:rgba(10,20,15,.45);display:flex;align-items:center;justify-content:center;z-index:10000';
    ov.innerHTML = `<div style="background:#fff;border-radius:18px;max-width:420px;width:92%;padding:20px 22px;box-shadow:0 18px 50px rgba(0,0,0,.25)">
      <div style="font-weight:800;font-size:16px">${esc(titulo)}</div><div style="color:var(--muted);font-size:13px;margin-top:6px">${esc(mensaje)}</div>
      <div style="display:flex;justify-content:flex-end;gap:8px;margin-top:16px"><button id="cm_no" style="padding:9px 16px;border-radius:999px;border:none;background:transparent;font-weight:700;cursor:pointer">Cancelar</button><button id="cm_si" class="btn-ap" style="padding:9px 18px;border-radius:999px;cursor:pointer">Confirmar ✓</button></div></div>`;
    ov.querySelector('#cm_no').onclick=()=>{ ov.remove(); res(false); };
    ov.querySelector('#cm_si').onclick=()=>{ ov.remove(); res(true); };
    ov.onclick=e=>{ if(e.target===ov){ ov.remove(); res(false); } };
    document.body.appendChild(ov);
  });
}
// MODAL de marca de pago (regla de la casa: nunca popup del navegador,
// siempre modal propio). Devuelve {medio, ref} o null si canceló.
function modalPagoLiquidacion(resumen){
  return new Promise(res=>{
    const ov = document.createElement('div');
    ov.style.cssText = 'position:fixed;inset:0;background:rgba(10,20,15,.45);'+
      'display:flex;align-items:center;justify-content:center;z-index:9999';
    ov.innerHTML = `
      <div style="background:#fff;border-radius:18px;max-width:400px;width:92%;padding:20px 22px;box-shadow:0 18px 50px rgba(0,0,0,.25)">
        <div style="font-weight:800;font-size:16px">Marcar liquidación pagada</div>
        <div style="color:var(--muted);font-size:13px;margin-top:2px">${resumen}</div>
        <div style="font-weight:700;font-size:13px;margin-top:14px">¿Cómo le pagaste al dueño?</div>
        <div style="display:flex;gap:8px;margin-top:8px;flex-wrap:wrap">
          <button data-m="yape" class="mp-chip">📱 Yape</button>
          <button data-m="transferencia" class="mp-chip">🏦 Transferencia</button>
          <button data-m="efectivo" class="mp-chip">💵 Efectivo</button>
        </div>
        <input id="mp_ref" placeholder="Referencia / n.º de operación (opcional)"
          style="width:100%;margin-top:12px;padding:10px;border:1px solid var(--border);border-radius:10px;box-sizing:border-box">
        <div style="display:flex;justify-content:flex-end;gap:8px;margin-top:16px">
          <button id="mp_cancel" style="padding:9px 16px;border-radius:999px;border:none;background:transparent;font-weight:700;cursor:pointer">Cancelar</button>
          <button id="mp_ok" class="btn-ap" style="padding:9px 18px;border-radius:999px;cursor:pointer">Confirmar pago ✓</button>
        </div>
      </div>`;
    let medio = 'yape';
    const chips = ov.querySelectorAll('.mp-chip');
    const pintar = ()=>chips.forEach(b=>{
      const on = b.dataset.m===medio;
      b.style.cssText = 'padding:8px 14px;border-radius:999px;font-weight:700;'+
        'cursor:pointer;border:1px solid var(--border);background:'+
        (on ? '#EBEBEB' : '#fff');
    });
    pintar();
    chips.forEach(b=>b.onclick=()=>{ medio=b.dataset.m; pintar(); });
    ov.querySelector('#mp_cancel').onclick=()=>{ ov.remove(); res(null); };
    ov.onclick=e=>{ if(e.target===ov){ ov.remove(); res(null); } };
    ov.querySelector('#mp_ok').onclick=()=>{
      const ref = ov.querySelector('#mp_ref').value.trim();
      ov.remove(); res({medio, ref});
    };
    document.body.appendChild(ov);
  });
}
async function pagarLiquidacion(rid, neto){
  const sel = await modalPagoLiquidacion(neto ? `Neto al dueño: ${neto}` : '');
  if(!sel) return;
  const r = await fetch('/pagos/liquidaciones/'+encodeURIComponent(rid)+'/pagar',{
    method:'POST', headers:headers(),
    body:JSON.stringify({metodo:sel.medio, referencia:sel.ref})});
  if(r.ok){ toast('Liquidación marcada como pagada ✓'); await cargarLiquidaciones(); }
  else toast('No se pudo marcar como pagado. Revisa tu conexión/token.');
}

async function cargarUbicacion(){
  const r = await fetch('/admin/api/ubicacion',{headers:headers()});
  if(!r.ok) return;
  const j = await r.json();
  exigirUbic = !!j.exigir;
  ubicMaxM = j.max_m || 150;
  renderUbicacion();
  render();
}
function renderUbicacion(){
  document.getElementById('ubic').innerHTML =
    `<div class="card"><div class="top"><h3>Verificación de ubicación al reclamar</h3></div>
      <div class="row">Muestra en el mapa desde dónde se envió cada solicitud. Si lo
        activas, sólo podrás <b>Aprobar</b> cuando el reclamante estuvo dentro de
        ${ubicMaxM} m de la cancha (evita reclamos a distancia).</div>
      <label class="sw">
        <input type="checkbox" ${exigirUbic?'checked':''} onchange="setExigir(this.checked)">
        <span class="track"><span class="knob"></span></span>
        <span style="font-weight:800;font-size:14px">${exigirUbic?'Exigir ubicación coincidente':'No exigir (piloto)'}</span>
      </label></div>`;
}
async function setExigir(v){
  const r = await fetch('/admin/api/ubicacion',{method:'POST',headers:headers(),
    body:JSON.stringify({exigir:v})});
  if(r.status===401){ salir(); return; }
  const j = await r.json();
  if(j.ok){
    exigirUbic = !!j.exigir_ubicacion_reclamo;
    toast(exigirUbic?'Ahora se exige ubicación coincidente':'Ya no se exige ubicación');
    renderUbicacion(); render();
  } else toast('No se pudo cambiar la configuración');
}

const MODO_DESC = {
  marcha_blanca:'Aprobar ACTIVA la cancha al instante (modo de pruebas / piloto).',
  nuevo_flujo:'Tras aprobar, la cancha exige validación EN SITIO (código + GPS) antes de habilitar reservas.'
};
async function cargarModo(){
  const r = await fetch('/admin/api/modo',{headers:headers()});
  if(!r.ok) return;
  const j = await r.json();
  modoGlobal = j.global || 'marcha_blanca';
  overrides = j.overrides || {};
  renderModo(modoGlobal);
  render();
}
async function setModoCancha(canchaId, modo){
  const r = await fetch('/admin/api/modo/cancha',{method:'POST',headers:headers(),
    body:JSON.stringify({cancha_id:canchaId, modo:modo||null})});
  if(r.status===401){ salir(); return; }
  const j = await r.json();
  if(j.ok){
    if(modo) overrides[canchaId]=modo; else delete overrides[canchaId];
    toast('Modo de la cancha actualizado');
  } else toast('No se pudo cambiar el modo de la cancha');
}
function modoNombre(m){ return m==='nuevo_flujo'?'Nuevo flujo':'Marcha blanca'; }
function renderModo(g){
  document.getElementById('modo').innerHTML =
    `<div class="card"><div class="top"><h3>Modo de aprobación de canchas</h3></div>
      <div class="row" id="modoDesc">${esc(MODO_DESC[g]||'')}</div>
      <div class="actions">
        <button class="seg ${g==='marcha_blanca'?'on':''}" onclick="setModo('marcha_blanca')">Marcha blanca</button>
        <button class="seg ${g==='nuevo_flujo'?'on':''}" onclick="setModo('nuevo_flujo')">Nuevo flujo</button>
      </div></div>`;
}
async function setModo(m){
  const r = await fetch('/admin/api/modo',{method:'POST',headers:headers(),body:JSON.stringify({modo:m})});
  if(r.status===401){ salir(); return; }
  const j = await r.json();
  if(j.ok){ toast('Modo: '+(m==='marcha_blanca'?'Marcha blanca':'Nuevo flujo')); renderModo(m); }
  else toast('No se pudo cambiar el modo');
}
// --- Canal de comunicación (qué muestra el APK para contactar al profe) -----
const CANAL_DESC = {
  pcg_primero:'Chat Pichangol como botón principal + WhatsApp visible como respaldo. Recomendado en el piloto.',
  solo_pcg:'Se OCULTA WhatsApp: todos escriben por el chat del app (máxima retención). Úsalo cuando el chat notifique bien al profe.',
  whatsapp_libre:'Chat y WhatsApp visibles por igual. Para nichos que exigen WhatsApp.'
};
const CANAL_NOMBRE = {pcg_primero:'PCG primero', solo_pcg:'Solo PCG', whatsapp_libre:'WhatsApp libre'};
async function cargarCanal(){
  const r = await fetch('/admin/api/canal',{headers:headers()});
  if(!r.ok) return;
  const j = await r.json();
  renderCanal(j.canal || 'pcg_primero');
}
function renderCanal(g){
  document.getElementById('canal').innerHTML =
    `<div class="card"><div class="top"><h3>Canal de comunicación (app)</h3></div>
      <div class="row" id="canalDesc">${esc(CANAL_DESC[g]||'')}</div>
      <div class="actions">
        <button class="seg ${g==='pcg_primero'?'on':''}" onclick="setCanal('pcg_primero')">PCG primero</button>
        <button class="seg ${g==='solo_pcg'?'on':''}" onclick="setCanal('solo_pcg')">Solo PCG</button>
        <button class="seg ${g==='whatsapp_libre'?'on':''}" onclick="setCanal('whatsapp_libre')">WhatsApp libre</button>
      </div></div>`;
}
async function setCanal(c){
  const r = await fetch('/admin/api/canal',{method:'POST',headers:headers(),body:JSON.stringify({canal:c})});
  if(r.status===401){ salir(); return; }
  const j = await r.json();
  if(j.ok){ toast('Canal: '+(CANAL_NOMBRE[c]||c)); renderCanal(c); }
  else toast('No se pudo cambiar el canal');
}
// --- Pichangas: modo global de asignación de cupos (convocatorias) ---------
let pichangaModo = 'orden_llegada';
const PICHANGA_MODO_DESC = {
  orden_llegada:'El que se anota primero entra; confirma al instante (como el chat de WhatsApp, pero ordenado).',
  sorteo:'Ventana de inscripción; al cerrar se sortea de forma justa y reproducible.',
  equidad:'Al cerrar prioriza a quien más veces quedó fuera y mejor asiste; penaliza al no-show.'
};
const PICHANGA_MODO_NOMBRE = {
  orden_llegada:'Orden de llegada', sorteo:'Sorteo', equidad:'Equidad'
};
async function cargarPichangaModo(){
  const r = await fetch('/admin/api/pichangas/modo',{headers:headers()});
  if(!r.ok) return;
  const j = await r.json();
  pichangaModo = j.global || 'orden_llegada';
  renderPichangaModo(pichangaModo);
}
function renderPichangaModo(g){
  const modos = ['orden_llegada','sorteo','equidad'];
  document.getElementById('pichangaModo').innerHTML =
    `<div class="card"><div class="top"><h3>Modo de asignación de pichangas</h3></div>
      <div class="row">Cómo se reparten los cupos de las convocatorias cuando una no
        fija su propio modo. El dueño puede elegir uno distinto en cada pichanga.</div>
      <div class="row" id="pichangaModoDesc" style="font-weight:600">${esc(PICHANGA_MODO_DESC[g]||'')}</div>
      <div class="actions">
        ${modos.map(m=>`<button class="seg ${g===m?'on':''}" onclick="setPichangaModo('${m}')">${PICHANGA_MODO_NOMBRE[m]}</button>`).join('')}
      </div></div>`;
}
async function setPichangaModo(m){
  const r = await fetch('/admin/api/pichangas/modo',{method:'POST',headers:headers(),body:JSON.stringify({modo:m})});
  if(r.status===401){ salir(); return; }
  const j = await r.json();
  if(j.ok){ pichangaModo=m; toast('Pichangas: '+PICHANGA_MODO_NOMBRE[m]); renderPichangaModo(m); }
  else toast('No se pudo cambiar el modo de pichangas');
}

function toast(msg){
  const d=document.createElement('div'); d.className='toast'; d.textContent=msg;
  document.body.appendChild(d); setTimeout(()=>d.remove(),2600);
}
(function pintarAmbiente(){
  const el = document.getElementById('side_amb');
  if(!el) return;
  const txt = "__AMBIENTE__";
  el.textContent = txt;
  if(/PRD|PROD/i.test(txt)) el.classList.add('prd');
})();
function esc(s){ return (s==null?'':String(s)).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c])); }

function renderTabs(){
  const counts = {};
  cache.forEach(r=>{counts[r.estado]=(counts[r.estado]||0)+1;});
  document.getElementById('tabs').innerHTML = FILTROS.map(([k,lbl])=>{
    const n = k==='' ? cache.length : (counts[k]||0);
    return `<div class="tab ${filtro===k?'on':''}" onclick="setFiltro('${k}')">${lbl}<span class="n">${n}</span></div>`;
  }).join('');
}
function setFiltro(k){ filtro=k; renderTabs(); render(); }

async function cargar(){
  const r = await fetch('/admin/api/reclamos',{headers:headers()});
  if(r.status===401){ salir(); return; }
  cache = await r.json();
  cache.reverse(); // más recientes primero
  kpi.reclamosPend = cache.filter(x=>x.estado==='pendiente_triage').length;
  kpi.activas = cache.filter(x=>x.estado==='activada').length;
  renderResumen();
  renderTabs(); render();
}

function waLink(tel,nombre,cod){
  let d=(tel||'').replace(/[^0-9]/g,'');
  if(d.length===9 && d[0]==='9') d='51'+d;
  const msg=encodeURIComponent('Hola, te escribo de Pichangol por el reclamo de "'+(nombre||'')+'". Tu código es '+(cod||'')+'. ¿Validamos que eres el dueño?');
  return 'https://wa.me/'+d+'?text='+msg;
}

function fmtFecha(iso){
  if(!iso) return '—';
  try{
    const d = new Date(iso);
    return d.toLocaleString('es-PE',{day:'2-digit',month:'short',year:'numeric',
      hour:'2-digit',minute:'2-digit',hour12:true});
  }catch(e){ return iso; }
}
function mapaUbic(r){
  if(r.solicitante_lat==null || r.solicitante_lng==null){
    return `<div class="mapbox"><div class="nomap">📍 El reclamante no compartió su
      ubicación al enviar la solicitud (app antigua o permiso denegado).</div></div>`;
  }
  const la=r.solicitante_lat, ln=r.solicitante_lng;
  let badge;
  if(!r.tiene_ubicacion) badge='<span class="badge-ubi ubi-sd">sin ubicación de la cancha</span>';
  else if(r.coincide) badge=`<span class="badge-ubi ubi-ok">✔ coincide · ${r.distancia_m} m</span>`;
  else badge=`<span class="badge-ubi ubi-no">✘ lejos · ${r.distancia_m} m</span>`;
  const q = la.toFixed(6)+','+ln.toFixed(6);
  return `<div class="mapbox">
    <div class="maphead">📍 Solicitó desde aquí ${badge}
      <a class="lnk" href="https://www.google.com/maps?q=${q}" target="_blank" rel="noopener">Abrir en Maps ↗</a>
    </div>
    <iframe loading="lazy" referrerpolicy="no-referrer-when-downgrade"
      src="https://maps.google.com/maps?q=${q}&z=17&output=embed"></iframe>
  </div>`;
}

let reclamoSel = null; // id del reclamo abierto en el panel de detalle

function chipEstadoMini(e){
  const m = {pendiente_triage:['Por aprobar','e-pend'],
    activada:['Activada','e-act'], rechazada:['Rechazada','e-rech']};
  const par = m[e] || [String(e||'').replaceAll('_',' '), 'e-otro'];
  return `<span class="chip-est ${par[1]}">${par[0]}</span>`;
}

function render(){
  const items = filtro==='' ? cache : cache.filter(r=>r.estado===filtro);
  const cont = document.getElementById('lista');
  const det = document.getElementById('reclamoDetalle');
  if(!items.length){
    cont.innerHTML='';
    det.innerHTML='<div class="empty">No hay reclamos en este estado.</div>';
    reclamoSel=null; return;
  }
  // Mantén la selección si sigue visible en este filtro; si no, la primera.
  if(!items.some(r=>r.id===reclamoSel)) reclamoSel = items[0].id;
  cont.innerHTML = items.map(r=>`
    <button class="md-item ${r.id===reclamoSel?'on':''}" onclick="verReclamo(${r.id})">
      <span class="md-ico">🏟️</span>
      <span class="md-txt"><b>${esc(r.nombre_local||'Local')}</b>
        <small>${esc(r.nombre_titular||r.solicitante_id||'—')}</small></span>
      ${chipEstadoMini(r.estado)}
    </button>`).join('');
  const s = items.find(r=>r.id===reclamoSel);
  det.innerHTML = s ? cardReclamo(s) : '';
}
function verReclamo(id){ reclamoSel = id; render(); }

// Expediente completo del reclamo (tarjeta del panel derecho).
function cardReclamo(r){
    const pend = r.estado==='pendiente_triage';
    const titular = r.nombre_titular ? `<div class="row">👤 <b>${esc(r.nombre_titular)}</b> · DNI ${esc(r.dni||'—')}</div>`
      : (r.dni ? `<div class="row">DNI ${esc(r.dni)} <i>(sin datos)</i></div>` : '');
    const razon = r.razon_social ? `<div class="row">🏢 ${esc(r.razon_social)} · RUC ${esc(r.ruc||'')}</div>` : '';
    const rel = r.relacion ? `<div class="row">Relación: <b>${esc(r.relacion)}</b></div>` : '';
    const wa = r.telefono_contacto ? `<a class="wa" href="${waLink(r.telefono_contacto,r.nombre_local,r.codigo)}" target="_blank" rel="noopener">💬 ${esc(r.telefono_contacto)} · Escribir</a>` : '';
    const bloqueaUbic = exigirUbic && !r.coincide;
    const apDis = bloqueaUbic
      ? 'disabled title="El reclamante no estuvo en la cancha; no se puede aprobar con esta configuración."'
      : '';
    const aviso = (pend && bloqueaUbic)
      ? `<div class="row" style="color:#9A1722;font-weight:700;margin-top:8px">🔒 No se puede aprobar: ${r.solicitante_lat==null?'sin ubicación del reclamante':'la ubicación no coincide con la cancha'}.</div>`
      : '';
    const acc = pend ? `${aviso}<div class="actions">
        <button class="btn-rc" onclick="decidir(${r.id},false,this)">Rechazar</button>
        <button class="btn-ap" onclick="decidir(${r.id},true,this)" ${apDis}>Aprobar y activar</button>
      </div>` : '';
    // "Liberar lugar": aparece cuando el reclamo AÚN ocupa el lugar (cualquier
    // estado bloqueante, incl. activada). Rechaza este y sus hermanos del mismo
    // lugar y revoca la cancha → la ficha vuelve a ser reclamable.
    const blk = ['pendiente_triage','aprobado_triage','pendiente_validacion',
      'validada_pendiente_admin','activada'].includes(r.estado);
    const lib = blk ? `<div class="row" style="margin-top:8px">
        <button class="btn-lib" onclick="liberar(${r.id},this)">🔓 Liberar lugar (volver a reclamable)</button>
      </div>` : '';
    const ov = overrides[r.cancha_id];
    const sel = `<div class="row" style="margin-top:10px">Modo de esta cancha:
      <select class="modosel" onchange="setModoCancha('${esc(r.cancha_id)}', this.value)">
        <option value="" ${ov?'':'selected'}>Usar global (${esc(modoNombre(modoGlobal))})</option>
        <option value="marcha_blanca" ${ov==='marcha_blanca'?'selected':''}>Marcha blanca</option>
        <option value="nuevo_flujo" ${ov==='nuevo_flujo'?'selected':''}>Nuevo flujo</option>
      </select></div>`;
    return `<div class="card">
      <div class="top">
        <h3>${esc(r.nombre_local||'Local')}</h3>
        <span class="cod">cód. ${esc(r.codigo||'------')}</span>
      </div>
      <div class="fecha">🕒 ${fmtFecha(r.creado_en)}</div>
      ${titular}${razon}${rel}
      <div class="row">Solicitante: ${esc(r.solicitante_id||'—')}</div>
      ${wa}
      ${mapaUbic(r)}
      <div style="margin-top:8px"><span class="chip est-${esc(r.estado)}">${esc(r.estado)}</span></div>
      ${sel}
      ${acc}
      ${lib}
    </div>`;
}

async function decidir(id, aprobado, btn){
  const card = btn.closest('.card');
  card.querySelectorAll('button').forEach(b=>b.disabled=true);
  const r = await fetch('/admin/api/reclamo/'+id+'/decidir',{
    method:'POST', headers:headers(),
    body: JSON.stringify({aprobado:aprobado, revisor:'panel'})
  });
  if(r.status===401){ salir(); return; }
  const j = await r.json();
  if(j.ok){
    toast(aprobado?'✅ Cancha aprobada y activada':'❌ Reclamo rechazado');
    cargar();
  } else {
    let msg;
    if(j.error==='ubicacion_no_coincide')
      msg='🔒 No se aprobó: el reclamante estuvo a '+(j.distancia_m||'?')+' m (máx '+(j.max_m||ubicMaxM)+' m).';
    else if(j.error==='sin_ubicacion_solicitante')
      msg='🔒 No se aprobó: no hay ubicación del reclamante para validar.';
    else msg='No se pudo: '+(j.error||'error');
    toast(msg);
    card.querySelectorAll('button').forEach(b=>b.disabled=false);
  }
}

async function liberar(id, btn){
  if(!confirm('¿Liberar este lugar? Se rechazará este reclamo y todos los del mismo lugar, y la cancha volverá a ser reclamable por cualquiera.')) return;
  const card = btn.closest('.card');
  card.querySelectorAll('button').forEach(b=>b.disabled=true);
  const r = await fetch('/admin/api/reclamo/'+id+'/liberar',{
    method:'POST', headers:headers(),
    body: JSON.stringify({revisor:'panel'})
  });
  if(r.status===401){ salir(); return; }
  const j = await r.json();
  if(j.ok){
    toast('🔓 Lugar liberado ('+(j.liberados||1)+' reclamo(s) cerrado(s))');
    cargar();
  } else {
    toast('No se pudo liberar: '+(j.error||'error'));
    card.querySelectorAll('button').forEach(b=>b.disabled=false);
  }
}

// auto-login si ya hay token guardado
if(tok()){
  fetch('/admin/api/sesion',{headers:headers()}).then(r=>{ if(r.ok) mostrarApp(); });
}
document.getElementById('pwd').addEventListener('keydown',e=>{ if(e.key==='Enter') entrar(); });
document.getElementById('usr').addEventListener('keydown',e=>{ if(e.key==='Enter') entrar(); });
</script>
</body>
</html>"""
