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

import time

from datetime import datetime, timezone

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

import config
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


# ── Login usuario+contraseña ──────────────────────────────────────────────────
# Anti fuerza bruta simple por IP: tras MAX_INTENTOS fallos seguidos, bloquea
# BLOQUEO_S segundos. En memoria (una instancia en Railway; se reinicia con el
# proceso, suficiente para frenar un ataque en línea).
_intentos: dict[str, tuple[int, float]] = {}  # ip -> (fallos, bloqueado_hasta)
MAX_INTENTOS = 5
BLOQUEO_S = 60.0


class LoginRequest(BaseModel):
    usuario: str
    clave: str


@router.post("/admin/api/login")
def login(body: LoginRequest, request: Request) -> dict:
    """Valida usuario+contraseña y devuelve una sesión firmada (12 h) que la
    página manda en X-Admin-Token. 503 si el panel/usuarios no están
    configurados; 429 si la IP está bloqueada por intentos fallidos."""
    if not config.ADMIN_PANEL_TOKEN:
        raise HTTPException(status_code=503, detail="panel_no_configurado")
    if not admin_auth.usuarios_configurados():
        raise HTTPException(status_code=503, detail="usuarios_no_configurados")
    ip = request.client.host if request.client else "?"
    fallos, bloqueado_hasta = _intentos.get(ip, (0, 0.0))
    ahora = time.time()
    if ahora < bloqueado_hasta:
        raise HTTPException(status_code=429, detail="demasiados_intentos")
    if admin_auth.credenciales_validas(body.usuario, body.clave):
        _intentos.pop(ip, None)
        usuario = body.usuario.strip().lower()
        return {"ok": True, "token": admin_auth.crear_sesion(usuario),
                "usuario": usuario}
    fallos += 1
    _intentos[ip] = (
        fallos, ahora + BLOQUEO_S if fallos >= MAX_INTENTOS else 0.0)
    raise HTTPException(status_code=401, detail="credenciales_invalidas")


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
            },
            "miembros": miembros}


class BienvenidaReq(BaseModel):
    pro_dias: int = 0
    saldo_soles: float = 0.0


@router.post("/admin/api/pro/bienvenida")
def set_bienvenida_admin(
        req: BienvenidaReq,
        x_admin_token: str | None = Header(default=None)) -> dict:
    """MARCHA BLANCA automática: qué recibe cada dueño NUEVO al activarse su
    primera cancha — días de Pro de cortesía y/o saldo de REGALO (solo cubre
    comisiones). 0 y 0 = apagada."""
    _check(x_admin_token)
    dias = max(0, min(int(req.pro_dias), 365))
    saldo = max(0.0, min(float(req.saldo_soles), 1000.0))
    stores.config["bienvenida_pro_dias"] = str(dias)
    stores.config["bienvenida_saldo_soles"] = (
        str(saldo if saldo % 1 else int(saldo)))
    return {"ok": True, "pro_dias": dias, "saldo_soles": saldo}


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


@router.get("/config/canal")
def get_canal_publico() -> dict:
    """PÚBLICO: el APK lee el canal de comunicación para decidir si muestra el
    botón de WhatsApp (pcg_primero | solo_pcg | whatsapp_libre)."""
    return {"canal": reclamos.canal_comunicacion()}


@router.get("/admin", response_class=HTMLResponse)
def panel() -> str:
    return _HTML


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
  .gate .form h2{margin:0 0 4px;font-family:var(--serif);font-weight:700;font-size:26px;
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
  .gate .form>button.cta{width:100%;background:var(--bosque);color:#fff;border:0;
    border-radius:12px;padding:14px;font-family:inherit;font-weight:800;font-size:15px;
    cursor:pointer;margin-top:6px}
  .gate .form>button.cta:hover{filter:brightness(1.08)}
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
        <span>Acceso por usuario y contraseña con sesión que expira sola.</span></div></div>
      <div class="foot">Conexión cifrada · Pichangol · una solución de <span class="ebim" style="color:#AEEA94">EBIM</span></div>
    </div>
    <div class="form">
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
      <div class="alt" id="altModo">¿Sin usuario? <a onclick="modoToken(true)">Entrar con token de administrador</a></div>
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
        <p class="page-sub">Canal de avisos que ve el APK y números de contacto del
          operador para WhatsApp.</p>
      </div>
      <div class="md">
        <aside class="md-list">
          <button class="md-item on" onclick="mostrarPane(this,'canal')">
            <span class="md-ico">📢</span>
            <span class="md-txt"><b>Canal de avisos</b><small>Mensajes que ve el APK</small></span>
          </button>
          <button class="md-item" onclick="mostrarPane(this,'contacto')">
            <span class="md-ico">💬</span>
            <span class="md-txt"><b>Contacto WhatsApp</b><small>Números del operador</small></span>
          </button>
        </aside>
        <div class="md-detail">
          <div class="md-pane" id="canal"></div>
          <div class="md-pane" id="contacto" style="display:none"></div>
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
  const r = await fetch('/admin/api/login',{method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({usuario, clave})});
  if(r.ok){
    const j = await r.json();
    localStorage.setItem('pichangol_admin_tok', j.token);
    localStorage.setItem('pichangol_admin_usr', j.usuario || usuario);
    mostrarApp();
  } else if(r.status===429){
    err.textContent='Demasiados intentos. Espera un minuto y vuelve a probar.';
  } else if(r.status===503){
    const j = await r.json().catch(()=>({}));
    err.textContent = (j.detail==='usuarios_no_configurados')
      ? 'Aún no hay usuarios configurados (ADMIN_PANEL_USUARIOS). Usa "Entrar con token".'
      : 'El panel no está configurado en el servidor (ADMIN_PANEL_TOKEN).';
  } else {
    err.textContent='Correo o contraseña incorrectos.';
  }
}
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
  cargarContacto();
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
        <b>\U0001F9F9 Limpiar almacenamiento (archivos huérfanos)</b><br/>
        Borra del Storage los archivos cuyo dueño ya no existe: fotos de canchas
        eliminadas, historias vencidas, fotos de productos borrados, afiches de
        campeonatos, avatares viejos y documentos de identidad sin referencia.
        <b>Nunca toca</b> las constancias de recargas ni el arte compartido.
        Primero revisa qué encontró; recién ahí borra.
      </div>
      <div class="actions" style="flex-wrap:wrap;gap:8px">
        <button class="btn-ap" onclick="revisarStorage()">\U0001F50D Revisar archivos huérfanos</button>
        <button class="btn-rc" onclick="limpiarStorage()">\U0001F9F9 Borrar huérfanos</button>
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
  const fam = j.familias||{};
  const lineas = Object.keys(fam).map(k=>{
    const f = fam[k];
    if(f.error) return `• ${k}: no se pudo leer (${f.error})`;
    return `• ${k}: ${f.n}` + (f.n && f.ejemplos&&f.ejemplos.length ? ` (ej. ${f.ejemplos[0]})` : '');
  });
  el.innerHTML = `<b>Huérfanos detectados: ${j.total||0}</b><br/>` + lineas.join('<br/>');
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
            ni se gasta en otra cosa). Pon 0 y 0 para apagarla.</div>
          <div class="actions" style="align-items:center;gap:10px;flex-wrap:wrap;margin-top:8px">
            <span style="font-size:12.5px;font-weight:600">Pro de cortesía</span>
            <select id="bvDias" style="padding:8px;border:1px solid var(--border);border-radius:8px">
              <option value="0">sin Pro</option>
              <option value="30">30 días</option>
              <option value="60">60 días</option>
              <option value="90">90 días</option>
              <option value="180">180 días</option>
            </select>
            <span style="font-size:12.5px;font-weight:600">Saldo de regalo S/</span>
            <input id="bvSaldo" inputmode="decimal"
              style="width:74px;padding:8px;border:1px solid var(--border);border-radius:8px;text-align:right">
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
  const saldo = parseFloat((document.getElementById('bvSaldo').value||'0').replace(',','.'))||0;
  const r = await fetch('/admin/api/pro/bienvenida',{method:'POST',headers:headers(),
    body:JSON.stringify({pro_dias:dias, saldo_soles:saldo})});
  if(r.status===401){ salir(); return; }
  if(r.ok) toast((dias||saldo) ? `Bienvenida activa: ${dias} días de Pro + S/ ${saldo}` : 'Bienvenida apagada');
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

// --- WhatsApp de contacto por PAÍS (servicios: landing, redes) -------------
const PAISES_CONTACTO = [
  ['pe','🇵🇪','Perú','51'],
  ['ec','🇪🇨','Ecuador','593'],
  ['bo','🇧🇴','Bolivia','591'],
];
let contactos = {pe:'',ec:'',bo:''};
async function cargarContacto(){
  try{
    const r = await fetch('/admin/api/contacto',{headers:headers()});
    if(!r.ok) return;
    const j = await r.json();
    contactos = j.contactos || contactos;
    renderContacto();
  }catch(e){}
}
function renderContacto(){
  const filas = PAISES_CONTACTO.map(([k,fl,nom,cod])=>`
    <div style="display:flex;align-items:center;gap:8px;margin-top:10px">
      <span style="font-size:20px">${fl}</span>
      <span style="min-width:66px;font-weight:700;font-size:13px">${nom}</span>
      <span style="color:var(--muted);font-weight:700;font-size:13px">+${cod}</span>
      <input id="wa_${k}" value="${esc(contactos[k]||'')}" placeholder="número local"
        inputmode="numeric" style="flex:1;padding:10px 12px;border:1px solid var(--border);
        border-radius:10px;font-family:inherit;font-size:14px">
    </div>`).join('');
  document.getElementById('contacto').innerHTML =
    `<div class="card"><div class="top"><h3>WhatsApp de contacto por país</h3></div>
      <div class="row">La app detecta el país del usuario y le propone el número
        local (más confianza). Escribe solo el número, sin el código de país.</div>
      ${filas}
      <div class="actions">
        <button class="btn-ap" onclick="guardarContacto()">Guardar números</button>
      </div></div>`;
}
async function guardarContacto(){
  const nuevos = {};
  for(const [k] of PAISES_CONTACTO){
    nuevos[k] = (document.getElementById('wa_'+k).value||'').replace(/[^0-9]/g,'');
  }
  const r = await fetch('/admin/api/contacto',{method:'POST',headers:headers(),
    body:JSON.stringify({contactos:nuevos})});
  if(r.status===401){ salir(); return; }
  const j = await r.json();
  if(j.ok){ contactos = j.contactos; renderContacto(); toast('Números de contacto guardados'); }
  else toast('No se pudo guardar');
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
const kpi = {reclamosPend:null, activas:null, liqTotal:null, liqN:null, disputas:null};

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
      <div class="kl">${kpi.liqN===null?'Por liquidar a dueños':(kpi.liqN===1?'1 pago pendiente':kpi.liqN+' pagos pendientes')}</div>
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
}

// --- Recargas por QR (Yape directo): el operador verifica y aprueba -------------
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
    kpi.liqTotal = j.total_neto_soles||0; kpi.liqN = pend.length; renderResumen();
    if(!pend.length){
      box.innerHTML = `<div class="card" style="text-align:center;padding:44px 20px">
        <div style="font-size:36px">🎉</div>
        <div style="font-weight:800;font-size:17px;margin-top:8px">Todo liquidado</div>
        <div style="color:var(--muted);font-size:13.5px;margin-top:4px">No tienes pagos pendientes a dueños.</div>
      </div>`;
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
        <div class="liq-row">
          <div style="min-width:0">
            <div class="liq-dueno">${esc(canchaDe(p))}</div>
            <div class="liq-det">${esc(restoDe(p))} · ${fmtFecha(p.creado_en)}</div>
          </div>
          <div class="liq-der">
            <div class="liq-monto" title="Bruto ${S(p.bruto_soles||0)} − comisión Pichangol ${S(p.comision_soles||0)}">${S(p.neto_soles||0)}</div>
            <button class="liq-btn" onclick="pagarLiquidacion('${esc(p.reserva_id)}','${S(p.neto_soles||0)}')">Marcar pagado</button>
          </div>
        </div>`).join('');
      return `
      <div class="card" style="padding:16px 18px;margin-bottom:14px">
        <div class="liq-grupo-top">
          <div style="min-width:0">
            <div class="liq-grupo-local">${esc(g.local)}</div>
            <div class="liq-grupo-dueno">${esc(g.dueno)} · ${g.items.length} ${g.items.length===1?'pago pendiente':'pagos pendientes'}</div>
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

    box.innerHTML = `
      <div class="liq-head">
        <div>
          <div class="liq-total">${S(gNeto)}</div>
          <div class="liq-sub">${pend.length===1?'1 pago pendiente':pend.length+' pagos pendientes'} · transfiere el neto (Yape/banco) y márcalo</div>
          <div class="liq-resumen">
            <span class="liq-mini">Bruto cobrado ${S(gBruto)}</span>
            <span class="liq-mini liq-mini-pcg">Comisión Pichangol ${S(gCom)}</span>
            <span class="liq-mini liq-mini-neto">Neto a dueños ${S(gNeto)}</span>
          </div>
        </div>
      </div>
      ${bloques}`;
  }catch(e){ box.innerHTML=''; }
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
