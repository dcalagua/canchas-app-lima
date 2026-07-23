"""PANEL WEB de administración (piloto).

El admin de Pichangol entra desde el navegador, ve los reclamos de canchas y los
aprueba/rechaza. La aprobación es DIRECTA: al aprobar, la cancha queda activa
(sin validación en sitio todavía).

Seguridad: protegido por ADMIN_PANEL_TOKEN. El token NO viaja en la URL; la
página lo guarda en el navegador (localStorage) y lo manda en la cabecera
X-Admin-Token. Si el token no está configurado, el panel responde 503.
"""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

import config
from convocatorias import service as convocatorias_service
from db.store import stores
from propiedad import reclamos

router = APIRouter(tags=["panel"])


def _check(token: str | None) -> None:
    if not config.ADMIN_PANEL_TOKEN:
        raise HTTPException(status_code=503, detail="panel_no_configurado")
    if token != config.ADMIN_PANEL_TOKEN:
        raise HTTPException(status_code=401, detail="token_invalido")


class DecidirRequest(BaseModel):
    aprobado: bool
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
    mat_bruto = sum(p.monto_centimos for p in mat)
    comision_mat = sum(p.comision_centimos for p in mat)
    comision_res = sum(p.monto_centimos for p in res)  # la comisión ES el monto
    rec_bruto = sum(p.monto_centimos for p in rec)
    bruto_procesado = mat_bruto + rec_bruto            # todo lo cobrado a tarjeta
    ingresos = comision_mat + comision_res             # ingreso bruto de PCG
    banco_pct = _banco_pct()
    costo_banco = int(round(bruto_procesado * banco_pct / 100.0))
    margen = ingresos - costo_banco
    return {
        "cobros_matricula": len(mat),
        "cobros_reserva": len(res),
        "comision_matricula_soles": comision_mat / 100.0,
        "comision_reserva_soles": comision_res / 100.0,
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
<title>Pichangol · Panel de canchas</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;700;800;900&display=swap" rel="stylesheet">
<style>
  /* Paleta del APP (verde WhatsApp) — co-marca Pichangol + EBIM, solo web admin.
     El primario ('bosque'/'lima') se remapea al verde de la app para congruencia:
     superficies primarias en verde #128C7E con texto blanco. */
  :root{
    --bg:#f4f7f6; --card:#fff; --border:#e6eae8; --text:#1e2422; --muted:#6b7671;
    --green:#128C7E; --green-deep:#0d6f63; --sage:#5AA97F; --verde:#128C7E;
    --bosque:#128C7E; --lima:#ffffff; --teal:#008489; --amarillo:#F2C94C;
    --limaSuave:#e3f2ef; --rojo:#D11F2E;
  }
  *{box-sizing:border-box}
  body{margin:0;font-family:'DM Sans',system-ui,sans-serif;background:var(--bg);color:var(--text)}
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
  .sec{font-size:13px;font-weight:800;text-transform:uppercase;letter-spacing:.08em;
    color:var(--muted);margin:26px 2px 4px}
  .cfg-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));
    gap:16px;align-items:stretch}
  .cfg-grid > div{display:flex}
  .cfg-grid .card{flex:1;display:flex;flex-direction:column;margin:0}
  #liquidaciones{margin-top:16px}
  #liquidaciones:empty{display:none}
  #lista{display:grid;grid-template-columns:repeat(auto-fill,minmax(380px,1fr));
    gap:16px;margin-top:12px}
  /* --- Layout con BARRA LATERAL izquierda (dashboard) --- */
  .shell{display:flex;min-height:100vh}
  .side{width:238px;flex-shrink:0;position:sticky;top:0;height:100vh;
    background:linear-gradient(180deg,var(--green),var(--green-deep));color:#fff;
    display:flex;flex-direction:column;padding:18px 14px;
    box-shadow:2px 0 16px rgba(18,140,126,.18)}
  .side-brand{display:flex;align-items:center;gap:11px;padding:6px 8px 4px}
  .side-brand .pin{width:36px;height:36px;border-radius:11px;overflow:hidden;flex-shrink:0}
  .side-brand .wm{font-size:19px;color:#fff}
  .side-sub{font-size:11px;font-weight:700;color:rgba(255,255,255,.75);margin-top:1px}
  .side-sub .ebim{color:#fff;font-size:11px}
  .nav{display:flex;flex-direction:column;gap:4px;margin-top:22px;flex:1}
  .nav-i{display:flex;align-items:center;gap:11px;background:transparent;border:0;
    color:rgba(255,255,255,.86);text-align:left;padding:12px;border-radius:12px;
    font-family:inherit;font-weight:700;font-size:14.5px;cursor:pointer;transition:.12s}
  .nav-i .ico{font-size:16px;width:20px;text-align:center}
  .nav-i:hover{background:rgba(255,255,255,.10);color:#fff}
  .nav-i.on{background:rgba(255,255,255,.18);color:#fff}
  .side-foot{display:flex;flex-direction:column;gap:8px}
  .side-btn{background:rgba(255,255,255,.14);color:#fff;border:0;border-radius:11px;
    padding:10px;font-family:inherit;font-weight:700;font-size:13px;cursor:pointer;
    display:flex;align-items:center;justify-content:center;gap:8px}
  .side-btn:hover{background:rgba(255,255,255,.24)}
  .side-cred{text-align:center;font-size:11px;color:rgba(255,255,255,.7);
    font-weight:600;padding-top:6px}
  .side-cred .ebim{color:#fff;font-size:11px}
  /* Botón para colapsar/expandir la barra lateral */
  .side-toggle{align-self:flex-end;background:rgba(255,255,255,.14);color:#fff;border:0;
    border-radius:10px;width:30px;height:30px;font-size:17px;line-height:1;cursor:pointer;
    flex-shrink:0;margin-bottom:4px;transition:.12s}
  .side-toggle:hover{background:rgba(255,255,255,.26)}
  .side{transition:width .16s ease}
  .side.collapsed{width:70px;padding:18px 10px;align-items:center}
  .side.collapsed .sb-txt,
  .side.collapsed .side-cred,
  .side.collapsed .side-btn .lbl{display:none}
  .side.collapsed .side-toggle{align-self:center}
  .side.collapsed .side-brand{justify-content:center;padding:6px 0 4px}
  .side.collapsed .nav-i{justify-content:center;gap:0;padding:12px 0;font-size:0}
  .side.collapsed .nav-i .ico{font-size:19px;width:auto}
  .side.collapsed .side-btn{justify-content:center;gap:0}
  .main{flex:1;min-width:0;padding:26px 30px 44px;max-width:1360px}
  .page-h{font-size:22px;font-weight:900;letter-spacing:-.01em;margin:0 0 18px}
  @media(max-width:820px){
    .shell{flex-direction:column}
    .side{width:auto;height:auto;position:static;flex-direction:row;flex-wrap:wrap;
      align-items:center;padding:12px 14px;gap:8px}
    .nav{flex-direction:row;margin-top:0;flex:1 1 100%;overflow:auto;gap:6px;order:3}
    .nav-i{padding:9px 12px;font-size:13.5px;white-space:nowrap}
    .side-foot{flex-direction:row;order:2;margin-left:auto}
    .side-cred{display:none}
    .main{padding:18px 16px 40px}
    /* En móvil la barra es horizontal: el colapsable no aplica. */
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
  .card h3{margin:0;font-size:16px;font-weight:800;flex:1}
  .cod{background:#EAF6C2;color:var(--bosque);font-weight:900;font-size:12px;
    border-radius:999px;padding:5px 10px;white-space:nowrap}
  .row{font-size:13px;color:var(--muted);margin-top:5px}
  .row b{color:var(--text);font-weight:700}
  .chip{display:inline-block;border-radius:999px;padding:3px 10px;font-size:11px;
    font-weight:800;margin-top:8px}
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
  .btn-rc{background:#fff;color:var(--rojo);border-color:#F3C9CE}
  .btn-ap:disabled,.btn-rc:disabled{opacity:.5;cursor:default}
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
  /* login */
  .gate{position:fixed;inset:0;background:var(--bg);display:flex;align-items:center;
    justify-content:center;padding:24px;z-index:30}
  .gate .box{background:#fff;border:1px solid var(--border);border-radius:18px;
    padding:28px 24px;max-width:380px;width:100%;text-align:center}
  .gate .pin{width:58px;height:58px;border-radius:16px;overflow:hidden;margin:0 auto 14px}
  .gate h2{margin:0 0 4px;font-weight:900}
  .gate p{margin:0 0 18px;color:var(--muted);font-size:14px}
  .gate input{width:100%;padding:12px 14px;border:1px solid var(--border);border-radius:10px;
    font-family:inherit;font-size:15px;margin-bottom:12px}
  .gate button{width:100%;background:var(--bosque);color:var(--lima);border:0;
    border-radius:12px;padding:13px;font-family:inherit;font-weight:800;font-size:15px;cursor:pointer}
  .gate .err{color:var(--rojo);font-size:13px;font-weight:700;min-height:18px;margin-bottom:8px}
</style>
</head>
<body>
<div class="gate" id="gate">
  <div class="box">
    <div class="pin"><svg viewBox="0 0 48 48"><rect x="1.5" y="1.5" width="45" height="45" rx="12" fill="#128C7E"/><path d="M24 11.5c-4.3 0-7.8 3.5-7.8 7.8 0 5.9 7.8 14.2 7.8 14.2s7.8-8.3 7.8-14.2c0-4.3-3.5-7.8-7.8-7.8zm0 10.7a2.9 2.9 0 110-5.8 2.9 2.9 0 010 5.8z" fill="#fff"/></svg></div>
    <h2><span class="wm" style="font-size:24px">Pichang<svg class="ball" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><polygon points="12,8.2 14.9,10.3 13.8,13.8 10.2,13.8 9.1,10.3"/><path d="M12 8.2V4.3M14.9 10.3l3.6-1.7M13.8 13.8l2.5 3.2M10.2 13.8l-2.5 3.2M9.1 10.3L5.5 8.6"/></svg>l</span></h2>
    <p>Panel de administración de canchas</p>
    <div class="err" id="gateErr"></div>
    <input id="tok" type="password" placeholder="Token de administrador" autocomplete="off">
    <button onclick="entrar()">Entrar</button>
    <div style="margin-top:16px;color:var(--muted);font-size:12px;font-weight:600">
      Una solución de <span class="ebim">EBIM</span>
    </div>
  </div>
</div>

<div class="shell" id="app" style="display:none">
  <aside class="side" id="side">
    <button class="side-toggle" onclick="toggleSide()" title="Colapsar / expandir menú">‹</button>
    <div class="side-brand">
      <div class="pin"><svg viewBox="0 0 48 48"><rect x="1.5" y="1.5" width="45" height="45" rx="12" fill="#fff"/><path d="M24 11.5c-4.3 0-7.8 3.5-7.8 7.8 0 5.9 7.8 14.2 7.8 14.2s7.8-8.3 7.8-14.2c0-4.3-3.5-7.8-7.8-7.8zm0 10.7a2.9 2.9 0 110-5.8 2.9 2.9 0 010 5.8z" fill="#128C7E"/></svg></div>
      <div class="sb-txt">
        <span class="wm">Pichang<svg class="ball" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><polygon points="12,8.2 14.9,10.3 13.8,13.8 10.2,13.8 9.1,10.3"/><path d="M12 8.2V4.3M14.9 10.3l3.6-1.7M13.8 13.8l2.5 3.2M10.2 13.8l-2.5 3.2M9.1 10.3L5.5 8.6"/></svg>l</span>
        <div class="side-sub"><span class="ebim">EBIM</span> · admin</div>
      </div>
    </div>
    <nav class="nav">
      <button class="nav-i on" data-sec="reclamos" onclick="mostrarSeccion('reclamos')" title="Reclamos">
        <span class="ico">📋</span> Reclamos</button>
      <button class="nav-i" data-sec="liquidaciones" onclick="mostrarSeccion('liquidaciones')" title="Liquidaciones">
        <span class="ico">💸</span> Liquidaciones</button>
      <button class="nav-i" data-sec="config" onclick="mostrarSeccion('config')" title="Configuración">
        <span class="ico">⚙️</span> Configuración</button>
    </nav>
    <div class="side-foot">
      <button class="side-btn" onclick="cargar();cargarLiquidaciones()" title="Actualizar"><span class="ico">↻</span><span class="lbl">Actualizar</span></button>
      <button class="side-btn" onclick="salir()" title="Salir"><span class="ico">⎋</span><span class="lbl">Salir</span></button>
      <div class="side-cred">una solución de <span class="ebim">EBIM</span></div>
    </div>
  </aside>
  <main class="main">
    <section id="page-reclamos" class="page">
      <h1 class="page-h">Reclamos de propiedad</h1>
      <div class="tabs" id="tabs"></div>
      <div id="lista"></div>
    </section>
    <section id="page-liquidaciones" class="page" style="display:none">
      <h1 class="page-h">Liquidaciones a dueños</h1>
      <div id="liquidaciones"></div>
    </section>
    <section id="page-config" class="page" style="display:none">
      <h1 class="page-h">Configuración</h1>
      <div class="cfg-grid">
        <div id="modo"></div>
        <div id="canal"></div>
        <div id="pichangaModo"></div>
        <div id="ubic"></div>
        <div id="contacto"></div>
        <div id="marketing"></div>
        <div id="comision"></div>
        <div id="margenes"></div>
        <div id="mantenimiento"></div>
      </div>
    </section>
  </main>
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

async function entrar(){
  const t = document.getElementById('tok').value.trim();
  const err = document.getElementById('gateErr');
  err.textContent='';
  if(!t){ err.textContent='Ingresa el token.'; return; }
  const r = await fetch('/admin/api/sesion',{headers:{'X-Admin-Token':t}});
  if(r.ok){
    localStorage.setItem('pichangol_admin_tok',t);
    mostrarApp();
  } else if(r.status===503){
    err.textContent='El panel no está configurado en el servidor (ADMIN_PANEL_TOKEN).';
  } else {
    err.textContent='Token inválido.';
  }
}
function salir(){ localStorage.removeItem('pichangol_admin_tok'); location.reload(); }
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
  document.getElementById('app').style.display='flex';
  restaurarSide();
  renderTabs();
  cargarModo();
  cargarCanal();
  cargarPichangaModo();
  cargarUbicacion();
  cargarContacto();
  cargarMarketing();
  cargarComision();
  cargarMargenes();
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
      </div>
      <div id="mant_res" class="row" style="margin-top:10px;color:var(--muted)"></div>
    </div>`;
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
  const campo = (id,lbl,val,suf)=>`
    <div style="display:flex;align-items:center;gap:8px;margin-top:8px">
      <span style="flex:1;font-weight:600;font-size:13px">${lbl}</span>
      <input id="${id}" value="${val}" inputmode="numeric" style="width:96px;padding:9px 10px;
        border:1px solid var(--border);border-radius:10px;font-family:inherit;font-size:14px;text-align:right">
      <span style="color:var(--muted);font-size:13px;min-width:44px">${suf}</span>
    </div>`;
  document.getElementById('marketing').innerHTML =
    `<div class="card"><div class="top"><h3>Servicios de marketing</h3></div>
      <div class="row">Precios MENSUALES de cada servicio (se debitan del saldo del
        dueño) y tope de generaciones de posts con IA por academia/mes (control de
        costo; la landing no cuenta).</div>
      ${campo('mkt_landing','Landing web', mkt.landing_soles, 'S/ /mes')}
      ${campo('mkt_redes','Manejo de redes (contenido IA + publicación)', mkt.redes_soles, 'S/ /mes')}
      ${campo('mkt_presencia','Presencia digital', mkt.presencia_soles, 'S/ /mes')}
      ${campo('mkt_limite','Tope de posts IA', mkt.posts_limite_mes, '/mes')}
      <div class="row" style="margin-top:14px;font-weight:600">Tarifa propia para clubes / canchas
        <span style="font-weight:400;color:var(--muted)"> — dejar en 0 usa la tarifa base de arriba. El
        negocio unificado (academia + canchas) usa la base.</span></div>
      ${campo('mkt_landing_club','Landing web (club)', mkt.landing_soles_club||0, 'S/ /mes')}
      ${campo('mkt_redes_club','Manejo de redes (club)', mkt.redes_soles_club||0, 'S/ /mes')}
      ${campo('mkt_presencia_club','Presencia digital (club)', mkt.presencia_soles_club||0, 'S/ /mes')}
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
      <div class="row">Tus INGRESOS por comisiones (matrículas + reservas) menos el
        COSTO real del banco/pasarela (Culqi) sobre todo lo que pasa por tarjeta
        (matrículas de alumnos + recargas de saldo de dueños). Ajusta la tasa del
        banco con tu tarifa real.</div>
      ${fila('Comisión de matrículas · '+m.cobros_matricula, '<b>'+s(m.comision_matricula_soles)+'</b>')}
      ${fila('Comisión de reservas · '+m.cobros_reserva, '<b>'+s(m.comision_reserva_soles)+'</b>')}
      ${fila('= Ingresos Pichangol (comisiones)', '<b>'+s(m.ingresos_pcg_soles)+'</b>', 'color:#14463A')}
      <hr style="border:none;border-top:1px solid var(--border);margin:8px 0">
      ${fila('Bruto procesado por tarjeta (matrículas + recargas)', s(m.bruto_procesado_soles), 'color:var(--muted)')}
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
    </div>`;
}
async function guardarBanco(){
  const pct = parseFloat((document.getElementById('banco_pct').value||'0').replace(',','.'))||0;
  const r = await fetch('/admin/api/margenes/banco',{method:'POST',headers:headers(),
    body:JSON.stringify({pct})});
  if(r.status===401){ salir(); return; }
  if(r.ok){ renderMargenes(await r.json()); toast('Tasa del banco actualizada'); }
  else toast('No se pudo guardar');
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
function mostrarSeccion(sec){
  document.querySelectorAll('.page').forEach(p=>{ p.style.display='none'; });
  const el = document.getElementById('page-'+sec);
  if(el) el.style.display='block';
  document.querySelectorAll('.nav-i').forEach(b=>{
    b.classList.toggle('on', b.dataset.sec===sec);
  });
}

// --- Liquidaciones: pagos pendientes de Pichangol al dueño (reservas online) ---
async function cargarLiquidaciones(){
  const box = document.getElementById('liquidaciones');
  try{
    const r = await fetch('/pagos/liquidaciones/pendientes',{headers:headers()});
    if(!r.ok){ box.innerHTML=''; return; }
    const j = await r.json();
    const pend = j.pendientes||[];
    const filas = pend.length ? pend.map(p=>`
      <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;padding:12px 0;border-top:1px solid var(--border)">
        <div>
          <b>${esc(p.dueno_id)||'—'}</b>
          <div style="color:var(--muted);font-size:13px">${esc(p.concepto)} · ${fmtFecha(p.creado_en)}</div>
          <div style="color:var(--muted);font-size:12px">Bruto S/${p.bruto_soles} · comisión S/${p.comision_soles}</div>
        </div>
        <div style="text-align:right;white-space:nowrap">
          <div style="font-weight:800;font-size:17px">S/${p.neto_soles}</div>
          <button onclick="pagarLiquidacion('${esc(p.reserva_id)}')" style="margin-top:6px;background:var(--bosque);color:var(--lima);border:0;border-radius:12px;padding:9px 12px;font-family:inherit;font-weight:700;cursor:pointer">Marcar pagado</button>
        </div>
      </div>`).join('')
      : '<div style="color:var(--muted);padding:8px 0">No hay liquidaciones pendientes. 🎉</div>';
    box.innerHTML = `<div class="card"><div class="top">
      <h3 style="flex:1">Liquidaciones por pagar a dueños</h3>
      <span style="font-weight:800;color:var(--bosque)">Total S/${j.total_neto_soles||0}</span></div>
      <p style="color:var(--muted);font-size:13px;margin:6px 0 4px">Reservas online: el jugador pagó a Pichangol. Transfiere el NETO al dueño (Yape/banco) y marca pagado.</p>
      ${filas}</div>`;
  }catch(e){ box.innerHTML=''; }
}
async function pagarLiquidacion(rid){
  const metodo = prompt('¿Cómo le pagaste al dueño? (yape / transferencia / efectivo)','yape');
  if(metodo===null) return;
  const ref = prompt('Referencia / nº de operación (opcional):','') || '';
  const r = await fetch('/pagos/liquidaciones/'+encodeURIComponent(rid)+'/pagar',{
    method:'POST', headers:headers(),
    body:JSON.stringify({metodo:metodo.trim(), referencia:ref.trim()})});
  if(r.ok){ cargarLiquidaciones(); }
  else { alert('No se pudo marcar como pagado. Revisa tu conexión/token.'); }
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

function render(){
  const items = filtro==='' ? cache : cache.filter(r=>r.estado===filtro);
  const cont = document.getElementById('lista');
  if(!items.length){ cont.innerHTML='<div class="empty">No hay reclamos en este estado.</div>'; return; }
  cont.innerHTML = items.map(r=>{
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
    </div>`;
  }).join('');
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

// auto-login si ya hay token guardado
if(tok()){
  fetch('/admin/api/sesion',{headers:headers()}).then(r=>{ if(r.ok) mostrarApp(); });
}
document.getElementById('tok').addEventListener('keydown',e=>{ if(e.key==='Enter') entrar(); });
</script>
</body>
</html>"""
