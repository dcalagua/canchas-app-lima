"""COBROS DEL CLUB en la web del anfitrión (plan nocturno web, W1.5–W1.7).

Espejo de tres pantallas del APK, sobre las MISMAS funciones del backend:

- **Cobros de tu club** `/anfitrion/cobros-club` (= `club_pagos_screen.dart`):
  conectar la cuenta Culqi PROPIA del club (llave pública + secreta,
  verificada con Culqi y guardada cifrada), los medios manuales por país
  (Yape/Plin/transferencia en Perú; QR/transferencia/billetera en Ecuador y
  Bolivia) y el estado de la comisión (saldo, deuda, tope, suspendido).
- **Pagos por confirmar** `/anfitrion/pagos-por-confirmar` (=
  `pagos_por_confirmar_screen.dart`): la bandeja de vouchers con la imagen,
  aprobar o rechazar con motivo POR SELECCIÓN.
- **Reglas de reserva** `/anfitrion/reglas/{cancha_id}` (=
  `reglas_reserva_screen.dart`): horario por día, días cerrados, franjas con
  precio, recargo de luz, ventana de reserva, turnos por reserva, tope por
  jugador y cancelación; "aplicar a otras canchas" y vista previa del día.

Los endpoints `/club/pagos*` y `/reservas/reglas` del APK exigen la X-App-Key
(NO puede viajar al navegador). Estos son sus ENVOLTORIOS WEB: la identidad es
la cookie de sesión (`sesion.de_request`), se re-verifica que cada cancha y
cada voucher sean del correo de la sesión (404 si no), y las llamadas JSON
exigen `Content-Type: application/json` (415) y mismo origen (403) cuando el
navegador manda `Origin` / `Sec-Fetch-Site`.
"""

from __future__ import annotations

import hashlib
import io
import json
import time
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote, urlparse

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from starlette.concurrency import run_in_threadpool

import config
from config import MARCA
from pagos import cobro_directo as cd
from reservas import reglas as _reglas
from web import almacen, datos, horarios, permisos, sesion, ui
from web import cobro_directo_web as cdw
from web import vista_anfitrion as va
from web import dividir_pago as _dividir_web
from web.anfitrion import _motivo_cierre, _sesion_o_entrar
from web.router import PLAY_URL, _moneda_de, e

router = APIRouter(tags=["web-anfitrion-cobros-club"])

SIMBOLO = {"PEN": "S/", "USD": "$", "BOB": "Bs"}

# Motivos de rechazo de un voucher (SELECCIÓN, nunca texto libre). El texto
# viaja tal cual en el aviso al jugador; "otro" no agrega motivo.
MOTIVOS_RECHAZO = list(cdw.MOTIVOS_RECHAZO.items())

# Motivos de un día cerrado (reglas). Se guarda el nombre visible.
MOTIVOS_CIERRE = ["Feriado", "Mantenimiento", "Evento privado", "Cerrado"]
NOMBRES_FRANJA = ["Hora punta", "Noche", "Mañana", "Tarde", "Fin de semana", "Temporada alta"]

ERRORES = {
    "llaves_invalidas": "Revisa las llaves: la pública empieza con pk_ y la secreta con sk_ (cópialas de tu panel de Culqi).",
    "llaves_de_distinto_modo": "Las dos llaves deben ser del mismo modo: las dos de pruebas o las dos de producción.",
    "llave_rechazada_por_culqi": "Culqi rechazó la llave secreta. Cópiala de nuevo desde tu panel de Culqi → Desarrollo → API Keys.",
    "cifrado_no_configurado": "Ahora mismo no podemos guardar llaves de Culqi de forma segura. Avísanos y lo activamos.",
    "base_no_disponible": "El cobro directo aún no está disponible en este ambiente.",
    "culqi_solo_peru": "Culqi cobra solo en soles: está disponible para clubes en Perú.",
    "sin_canchas": "Primero registra tu cancha: los cobros directos son para clubes con canchas.",
    "titular_requerido": "Escribe el nombre del titular (como aparece en el comprobante).",
    "celular_invalido": "El celular debe tener 9 dígitos y empezar con 9.",
    "cuenta_requerida": "Elige el banco y escribe el número de cuenta o el CCI.",
    "cci_invalido": "El CCI tiene 20 dígitos.",
    "qr_o_numero_requerido": "Sube la imagen de tu QR o escribe el número.",
    "hold_vencido": "Esta reserva ya se liberó (venció el plazo o el jugador la soltó).",
    "ya_resuelto": "Este pago ya se resolvió.",
}


def _msg(err: str) -> str:
    if err.startswith("medio_no_permitido"):
        return "Ese medio de pago no está disponible en tu país."
    return ERRORES.get(err, "No se pudo guardar. Inténtalo de nuevo.")


def _js(obj) -> str:
    """JSON seguro dentro de <script> (un nombre con </script> no rompe la página)."""
    return (ui.json_js(obj, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e")
            .replace("&", "\\u0026").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))


def _plata(centimos: int, iso: str) -> str:
    return f"{SIMBOLO.get(iso, iso)} {int(centimos or 0) / 100.0:.2f}"


def _base_webhook(request: Request) -> str:
    return "" if config.PUBLIC_BASE_URL else str(request.base_url).rstrip("/")


# ── guardias de las llamadas JSON ────────────────────────────────────────────

def _err(error: str, status: int = 400, **kw) -> JSONResponse:
    return JSONResponse({"ok": False, "error": error, "mensaje": _msg(error) if error in ERRORES or error.startswith("medio_") else error, **kw},
                        status_code=status)


def _mismo_origen(request: Request) -> bool:
    sfs = (request.headers.get("sec-fetch-site") or "").strip().lower()
    if sfs and sfs not in ("same-origin", "none"):
        return False
    origen = (request.headers.get("origin") or "").strip()
    if origen:
        if origen == "null":
            return False
        host = (request.headers.get("host") or request.url.netloc or "").lower()
        if urlparse(origen).netloc.lower() != host:
            return False
    return True


def _guardia(request: Request, tipo: str = "application/json") -> JSONResponse | None:
    ct = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    if tipo == "image/*":
        if not ct.startswith("image/"):
            return _err("tipo_no_soportado", 415)
    elif ct != tipo:
        return _err("tipo_no_soportado", 415)
    if not _mismo_origen(request):
        return _err("origen_no_permitido", 403)
    return None


async def _cuerpo(request: Request):
    """(sesión, cuerpo JSON, respuesta de error)."""
    malo = _guardia(request)
    if malo is not None:
        return None, None, malo
    ses = sesion.de_request(request)
    if not ses:
        return None, None, _err("sesion_requerida", 401)
    try:
        b = await request.json()
    except Exception:  # noqa: BLE001
        return ses, None, _err("datos_invalidos", 400)
    if not isinstance(b, dict):
        return ses, None, _err("datos_invalidos", 400)
    return ses, b, None


def _pagina(titulo: str, cuerpo: str, ses: dict, volver: str = "/anfitrion", volver_txt: str = "Modo anfitrión") -> HTMLResponse:
    """Página con el formato ANTERIOR (la usa Devoluciones de `web/dividir_pago.py`).
    La barra del modo anfitrión la pone `ui.shell` sola."""
    html = f"<a class='anf-back' href='{e(volver)}'>‹ {e(volver_txt)}</a>{cuerpo}<style>{CSS}</style>"
    return ui.shell(titulo, html, sesion=ses, ancho=True, titulo_tab=f"{titulo} · Modo anfitrión · {MARCA}")


def pagina_vista(titulo: str, cuerpo: str, ses: dict, clase: str = "") -> HTMLResponse:
    """Vista del rediseño (kit `web/vista_anfitrion.py` + `web/estilos_v_club.py`)."""
    return ui.shell(titulo, va.vista(cuerpo, f"vcl {clase}".strip()), sesion=ses, ancho=True,
                    titulo_tab=f"{titulo} · Modo anfitrión · {MARCA}")


# Íconos de los medios de pago (línea blanca sobre cuadrado azul). Celular y QR
# no están en `web/iconos.py`: van aquí (mismo trazo 24×24).
_SVG_EXTRA = {
    "celular": "<rect x='7' y='2.5' width='10' height='19' rx='2.2'/><path d='M11 18h2'/>",
    "qr": "<rect x='3.5' y='3.5' width='6.5' height='6.5' rx='1'/><rect x='14' y='3.5' width='6.5' height='6.5' rx='1'/>"
          "<rect x='3.5' y='14' width='6.5' height='6.5' rx='1'/><path d='M14 14h2.5v2.5H14zM20.5 14v.01M14 20.5h.01M17 20.5h3.5V17'/>",
    "candado": "<rect x='5' y='11' width='14' height='9.5' rx='2'/><path d='M8 11V8a4 4 0 0 1 8 0v3'/>",
    "personas": "<circle cx='9' cy='8' r='3.2'/><path d='M3.5 19.5a5.5 5.5 0 0 1 11 0'/><circle cx='17' cy='9' r='2.6'/><path d='M15.8 14.2a4.6 4.6 0 0 1 4.7 5.3'/>",
    "check": "<path d='M5 12.5l4.2 4.2L19 7'/>",
    "x": "<path d='M6 6l12 12M18 6L6 18'/>",
    "copiar": "<rect x='8.5' y='8.5' width='11' height='11' rx='2'/><path d='M15.5 8.5V6a1.5 1.5 0 0 0-1.5-1.5H6A1.5 1.5 0 0 0 4.5 6v8A1.5 1.5 0 0 0 6 15.5h2.5'/>",
}
ICONO_MEDIO = {"yape": "celular", "plin": "celular", "transferencia": "edificio", "billetera": "billete", "qr": "qr"}


def svg(nombre: str, tam: int = 18) -> str:
    """Ícono de línea: los de `web/iconos.py` o los extra de este módulo."""
    from web import iconos
    cuerpo = _SVG_EXTRA.get(nombre)
    if cuerpo is None:
        return iconos.svg(nombre, tam, grueso=2.2)
    return (f"<svg class='ic-l' viewBox='0 0 24 24' width='{tam}' height='{tam}' fill='none' stroke='currentColor' "
            f"stroke-width='2.2' stroke-linecap='round' stroke-linejoin='round' aria-hidden='true'>{cuerpo}</svg>")


def ico(nombre: str, tono: str = "azul", tam: int = 18) -> str:
    """Ícono blanco en cuadrado de color (como `va.icono`, sin estilos en línea)."""
    return f"<span class='va-ic vcl-ic {e(tono)}'>{svg(nombre, tam)}</span>"


def _panel(titulo: str, sub: str, contenido: str, *, icono: str = "", acciones: str = "", clase: str = "", id_: str = "") -> str:
    """Panel con ícono a la izquierda del título (Culqi, Comisión…)."""
    tid = f"t_{id_ or hashlib.md5(titulo.encode()).hexdigest()[:6]}"
    return (f"<section class='va-panel {e(clase)}'" + (f" id='{e(id_)}'" if id_ else "") + f" aria-labelledby='{tid}'>"
            f"<div class='vcl-pcab'>{ico(icono) if icono else ''}<div class='vcl-pcab-t'><h2 id='{tid}'>{e(titulo)}</h2>"
            + (f"<p>{e(sub)}</p>" if sub else "") + "</div>"
            + (f"<div class='vcl-pcab-acc'>{acciones}</div>" if acciones else "") + f"</div>{contenido}</section>")


# ── Cobros de tu club (club_pagos_screen.dart) ───────────────────────────────

def _bancos_de(pais: str) -> list[str]:
    from pagos import cuentas_cobro as _cc
    return [n for _c, n in _cc.BANCOS.get(pais, [])]


def _billeteras_de(pais: str) -> list[str]:
    try:
        import academia_plan
        return [n for _c, n in academia_plan.QR_APPS.get(pais, [])]
    except Exception:  # noqa: BLE001
        return []


def tarjeta_comision(est: dict, email: str, iso: str) -> str:
    """Saldo, deuda de comisión, tope y "suspendido" con qué hacer. La usan
    Cobros del club e Ingresos (misma fuente: `cdw.estado_club`)."""
    from db.store import stores
    com = est.get("comision") or {}
    deuda, tope = int(com.get("deuda_centimos") or 0), int(com.get("tope_centimos") or 0)
    saldo = stores.saldo_centimos(email) + stores.saldo_promo_centimos(email)
    aviso = ""
    if com.get("suspendido"):
        aviso = ("<div class='aviso err' role='alert' style='margin-top:12px'><b>Cobros en línea pausados.</b> "
                 f"Tienes {_plata(deuda, iso)} de comisiones por pagar (el tope es {_plata(tope, iso)}). "
                 "Recarga tu saldo y la deuda se paga sola; mientras tanto el pago en la cancha sigue funcionando.</div>")
    elif deuda:
        aviso = ("<div class='aviso warn' style='margin-top:12px'>"
                 f"Tienes {_plata(deuda, iso)} de comisiones por pagar. Si pasa de {_plata(tope, iso)} se pausan tus "
                 "cobros en línea. Recarga tu saldo y se paga sola.</div>")
    return ("<section class='panel cc-com' aria-labelledby='tComision'><h2 id='tComision'>Comisión " + e(MARCA) + "</h2>"
            "<p class='sub'>El pago de cada reserva llega directo a tu cuenta. " + e(MARCA)
            + " cobra solo su comisión por reserva, de tu saldo prepago.</p>"
            "<div class='kpis'>"
            f"<div class='kpi'><small>Saldo disponible</small><b>{_plata(saldo, iso)}</b><small>de aquí sale la comisión</small></div>"
            f"<div class='kpi'><small>Comisiones por pagar</small><b>{_plata(deuda, iso)}</b><small>se paga sola al recargar</small></div>"
            f"<div class='kpi'><small>Tope antes de pausar cobros</small><b>{_plata(tope, iso)}</b></div></div>"
            + aviso
            + "<div class='acciones' style='margin-top:14px'><a class='btn' href='/mi-billetera#recargar'>Recargar saldo</a>"
            f"<a class='btn sec' href='{PLAY_URL}' rel='noopener'>O desde la app</a></div></section>")


SUB_COBROS = f"El pago de cada reserva llega directo a tu cuenta. {MARCA} cobra solo su comisión por reserva."


def _saldo_de(email: str) -> int:
    from db.store import stores
    return stores.saldo_centimos(email) + stores.saldo_promo_centimos(email)


def _estado_tarjetas(est: dict, email: str) -> str:
    """Las 3 tarjetas de estado de arriba: cobro en línea, pagos manuales y
    saldo para comisiones (datos reales de `cdw.estado_club`)."""
    iso = est["moneda"]
    cq = est.get("culqi") or {}
    if cq.get("no_aplica"):
        c1 = ("Cobro en línea", "Por ahora tu país cobra con pagos manuales", va.pill("No disponible", "gris"))
    elif cq.get("configurada"):
        c1 = ("Cobro en línea (Culqi)", "Tarjeta y Yape automático",
              va.pill("Conectado", "ok") if cq.get("modo") == "live" else va.pill("Conectado · pruebas", "warn"))
    else:
        c1 = ("Cobro en línea (Culqi)", "Tarjeta y Yape automático", va.pill("No conectado", "warn"))
    n = len(est.get("medios") or [])
    nombres = " · ".join(cd.ETIQUETA_MEDIO.get(k, k).replace(" bancaria", "").replace(" digital", "") for k in est["medios_permitidos"])
    c2 = ("Pagos manuales", nombres, va.pill(f"{n} activo{'s' if n != 1 else ''}", "ok") if n else va.pill("Sin medios", "gris"))
    com = est.get("comision") or {}
    saldo, deuda = _saldo_de(email), int(com.get("deuda_centimos") or 0)
    tono = "bad" if com.get("suspendido") or (saldo <= 0 and deuda > 0) else ("warn" if saldo <= 0 else "ok")
    c3 = ("Saldo para comisiones", "Recarga para no pausar cobros", va.pill(_plata(saldo, iso), tono))
    icos = ("tarjeta", "celular" if est["pais"] == "PE" else "qr", "billete")
    return "<div class='vcl-est'>" + "".join(
        f"<div class='vcl-est-it'>{ico(i)}<div class='tx'><b>{e(t)}</b><small>{e(s)}</small></div>{p}</div>"
        for i, (t, s, p) in zip(icos, (c1, c2, c3))) + "</div>"


@router.get("/anfitrion/cobros-club", response_class=HTMLResponse)
def pagina_cobros_club(request: Request) -> HTMLResponse:
    ses, resp = _sesion_o_entrar(request, "/anfitrion/cobros-club")
    if resp is not None:
        return resp
    email = ses["email"]
    if permisos.es_solo_encargado(email):
        from web import anfitrion_encargados as _enc
        return _enc.sin_permiso(ses, "")
    cab = va.cabecera("Cobros de tu club", SUB_COBROS)
    if not datos.canchas_de_dueno(email):
        cuerpo = cab + va.panel(va.vacio("tarjeta", "Primero registra tu cancha",
                                         "Aquí conectarás tu Culqi y tus medios de pago para cobrar cada reserva.",
                                         "<a class='btn' href='/anfitrion/nueva'>Registrar mi cancha</a>"))
        return pagina_vista("Cobros de tu club", cuerpo, ses)
    est = cdw.estado_club(email, _base_webhook(request))
    iso, pais = est["moneda"], est["pais"]
    pend = int(est.get("pendientes") or 0)
    aviso_pend = va.aviso(f"<b>Tienes {pend} {'pago' if pend == 1 else 'pagos'} por confirmar.</b> Revísalo{'' if pend == 1 else 's'} "
                          "antes de que venza el plazo y la reserva se libere sola.", "warn",
                          "<a href='/anfitrion/pagos-por-confirmar'>Revisar ›</a>", "recibo") if pend else ""
    comision = panel_comision(est, email, iso)
    if not est["disponible"]:
        cuerpo = (cab + va.aviso("El cobro directo aún no está disponible en este ambiente.", "warn", ico="reloj")
                  + f"<div class='va-dos'><div></div><div>{comision}</div></div>")
        return pagina_vista("Cobros de tu club", cuerpo, ses)
    sub_medios = ("El jugador paga y sube su comprobante; tú lo confirmas en Pagos por confirmar." if pais == "PE" else
                  "En tu país los jugadores te pagan con QR, transferencia o billetera: agrégalos aquí y confirma cada "
                  "comprobante en Pagos por confirmar.")
    medios = _panel("Pagos manuales", sub_medios,
                    "<div id='ccMedios' aria-live='polite'></div><form id='ccMedioForm' class='vcl-form' hidden novalidate></form>",
                    acciones="<button type='button' class='btn suave' id='ccAgregar'>＋ Agregar medio</button>", id_="ccMediosP")
    izq = _bloque_culqi(est) + medios
    cfg = {"pais": pais, "moneda": iso, "permitidos": est["medios_permitidos"], "medios": est["medios"],
           "bancos": _bancos_de(pais), "billeteras": _billeteras_de(pais), "qr": almacen.disponible(),
           "etiquetas": cd.ETIQUETA_MEDIO, "errores": ERRORES,
           "iconos": {k: ico(v) for k, v in ICONO_MEDIO.items()}}
    cuerpo = (cab + _estado_tarjetas(est, email) + aviso_pend
              + f"<div class='va-dos vcl-cobros'><div class='vcl-col'>{izq}</div><div class='vcl-col'>{comision}</div></div>"
              + f"<script>window.__club={_js(cfg)};</script><script>{JS_CLUB}</script>")
    return pagina_vista("Cobros de tu club", cuerpo, ses)


def panel_comision(est: dict, email: str, iso: str) -> str:
    """Panel "Comisión <marca>" del rediseño: saldo disponible, comisiones por
    pagar, tope antes de pausar y la barra deuda vs. tope (misma fuente que
    `tarjeta_comision`: `cdw.estado_club`)."""
    com = est.get("comision") or {}
    deuda, tope = int(com.get("deuda_centimos") or 0), int(com.get("tope_centimos") or 0)
    saldo = _saldo_de(email)
    pct = 0 if tope <= 0 else min(100, round(deuda * 100 / tope))
    aviso = ""
    if com.get("suspendido"):
        aviso = va.aviso(f"<b>Cobros en línea pausados.</b> Tienes {_plata(deuda, iso)} de comisiones por pagar (el tope es "
                         f"{_plata(tope, iso)}). Recarga tu saldo y la deuda se paga sola; mientras tanto el pago en la cancha "
                         "sigue funcionando.", "bad")
    elif deuda:
        aviso = va.aviso(f"Tienes {_plata(deuda, iso)} de comisiones por pagar. Si pasa de {_plata(tope, iso)} se pausan tus "
                         "cobros en línea. Recarga tu saldo y se paga sola.", "warn")
    tono = "bad" if pct >= 80 else ("warn" if pct >= 50 else "ok")
    cont = (f"<div class='vcl-saldo'><small>Saldo disponible</small><b>{_plata(saldo, iso)}</b>"
            "<p>De aquí sale la comisión de cada reserva.</p></div>"
            "<div class='vcl-mini'>"
            f"<div><small>Comisiones por pagar</small><b>{_plata(deuda, iso)}</b><p>Se paga sola al recargar</p></div>"
            f"<div><small>Tope antes de pausar</small><b>{_plata(tope, iso)}</b><p>Deuda máxima</p></div></div>"
            f"<div class='vcl-barra-t'><b>Deuda vs. tope</b><span>{_plata(deuda, iso)} de {_plata(tope, iso)}</span></div>"
            f"<div class='vcl-barra {tono}' role='progressbar' aria-label='Deuda de comisiones frente al tope' aria-valuemin='0' "
            f"aria-valuemax='100' aria-valuenow='{pct}'><i class='p{pct // 5 * 5}'></i></div>"
            "<p class='vcl-nota'>Al llegar al tope se pausan los cobros en línea.</p>" + aviso
            + f"<a class='btn vcl-ancho' href='/mi-billetera#recargar'>{svg('billete', 18)} Recargar saldo</a>"
            f"<a class='vcl-link-c' href='{e(PLAY_URL)}' rel='noopener'>También puedes recargar desde la app</a>")
    return _panel(f"Comisión {MARCA}", "Sale de tu saldo prepago.", cont, icono="billete", clase="vcl-com", id_="tComision")


def _bloque_culqi(est: dict) -> str:
    cq = est.get("culqi") or {}
    if cq.get("no_aplica"):
        return ""
    titulo, sub = "Tarjeta y Yape con tu Culqi", "La plata cae en tu cuenta. Llaves en Culqi → Desarrollo → API Keys."
    if cq.get("configurada"):
        modo = "Producción" if cq.get("modo") == "live" else "Pruebas"
        cont = ("<div class='vcl-ok'>" + svg("check", 18) + "<b>Culqi conectado</b>"
                + va.pill(modo, "ok" if modo == "Producción" else "warn") + "</div>"
                "<dl class='vcl-dl'>"
                f"<dt>Llave pública</dt><dd><code>{e(cq.get('public_key'))}</code></dd>"
                f"<dt>Llave secreta</dt><dd><code>{e(cq.get('secret_key'))}</code></dd></dl>"
                + ("" if cq.get("verificada") else va.aviso("No pudimos comprobar la llave con Culqi; se reintentará al cobrar.", "warn"))
                + "<label for='ccWebhook'>Webhook (pégalo en tu panel de Culqi → Eventos)</label>"
                f"<div class='vcl-copiar'><input id='ccWebhook' readonly value='{e(cq.get('webhook_url'))}'>"
                f"<button type='button' class='btn sec' data-copiar='ccWebhook'>{svg('copiar', 16)} Copiar</button></div>"
                "<div class='vcl-pie'><span></span><button type='button' class='btn peligro' id='ccDesconectar'>Desconectar Culqi</button></div>")
        return _panel(titulo, sub, cont, icono="tarjeta", id_="tCulqi")
    sin_cifrado = not est.get("cifrado")
    cont = ((va.aviso(e(ERRORES["cifrado_no_configurado"]), "warn") if sin_cifrado else "")
            + "<form id='ccCulqi' novalidate><div class='vcl-llaves'>"
            "<div><label for='ccPk'>Llave pública</label><input id='ccPk' autocomplete='off' spellcheck='false' maxlength='120' placeholder='pk_live_…'></div>"
            "<div><label for='ccSk'>Llave secreta</label><input id='ccSk' type='password' autocomplete='off' spellcheck='false' maxlength='120' placeholder='sk_live_…'></div></div>"
            "<div class='aviso err' id='ccCulqiErr' role='alert' hidden></div>"
            f"<div class='vcl-pie'><small class='vcl-candado'>{svg('candado', 14)} La llave secreta se guarda cifrada y nunca se vuelve a mostrar.</small>"
            f"<button type='submit' class='btn' id='ccConectar'{' disabled' if sin_cifrado else ''}>Conectar Culqi</button></div>"
            "</form>")
    return _panel(titulo, sub, cont, icono="tarjeta", id_="tCulqi")


@router.post("/anfitrion/cobros-club/culqi")
async def conectar_culqi(request: Request) -> JSONResponse:
    ses, b, malo = await _cuerpo(request)
    if malo is not None:
        return malo
    status, r = await run_in_threadpool(cdw.conectar_culqi, ses["email"], str(b.get("public_key") or ""),
                                        str(b.get("secret_key") or ""))
    if status != 200:
        return _err(r.get("error") or "error", status)
    print(f"[cobros-club-web] {ses['email']} conectó su Culqi ({r.get('modo')})", flush=True)
    return JSONResponse({k: v for k, v in r.items() if k != "secret_key"} | {"secret_key": r.get("secret_key")})


@router.post("/anfitrion/cobros-club/culqi/desconectar")
async def desconectar_culqi(request: Request) -> JSONResponse:
    ses, _b, malo = await _cuerpo(request)
    if malo is not None:
        return malo
    ok = await run_in_threadpool(cd.borrar_culqi, ses["email"])
    print(f"[cobros-club-web] {ses['email']} desconectó su Culqi ok={ok}", flush=True)
    return JSONResponse({"ok": bool(ok)})


@router.post("/anfitrion/cobros-club/medios")
async def guardar_medios(request: Request) -> JSONResponse:
    ses, b, malo = await _cuerpo(request)
    if malo is not None:
        return malo
    medios = b.get("medios")
    if not isinstance(medios, list) or len(medios) > cd.MAX_MEDIOS:
        return _err("datos_invalidos", 400)
    status, r = await run_in_threadpool(cdw.guardar_medios_club, ses["email"], medios)
    if status != 200:
        return _err(r.get("error") or "error", status)
    return JSONResponse(r)


@router.post("/anfitrion/cobros-club/qr")
async def subir_qr(request: Request) -> JSONResponse:
    """Imagen del QR de cobro del club (Ecuador / Bolivia) → Storage público
    (es lo que el jugador escanea). Se normaliza a JPEG ≤ 1200 px."""
    malo = _guardia(request, "image/*")
    if malo is not None:
        return malo
    ses = sesion.de_request(request)
    if not ses:
        return _err("sesion_requerida", 401)
    crudo = await request.body()
    return await run_in_threadpool(_subir_qr, ses["email"], crudo)


def _subir_qr(email: str, crudo: bytes) -> JSONResponse:
    if not datos.canchas_de_dueno(email):
        return _err("sin_canchas", 403)
    if not almacen.disponible():
        return _err("La subida de imágenes no está disponible en este momento.", 503)
    if not crudo or len(crudo) > cd.VOUCHER_MAX_BYTES:
        return _err("La imagen es muy grande (máximo 6 MB).", 413)
    try:
        from PIL import Image, ImageOps
        img = ImageOps.exif_transpose(Image.open(io.BytesIO(crudo))).convert("RGB")
        img.thumbnail((1200, 1200))
        out = io.BytesIO()
        img.save(out, "JPEG", quality=88)
    except Exception:  # noqa: BLE001
        return _err("Ese archivo no es una imagen.", 400)
    carpeta = hashlib.sha256(email.encode()).hexdigest()[:16]
    url = almacen.subir(almacen.BUCKET, f"club_qr/{carpeta}_{int(time.time() * 1000)}.jpg", out.getvalue())
    if not url:
        return _err("No pudimos subir la imagen. Inténtalo de nuevo.", 503)
    return JSONResponse({"ok": True, "url": url})


# ── Pagos por confirmar (pagos_por_confirmar_screen.dart) ───────────────────

def _turnos_de(pagos: list[dict]) -> dict[str, tuple[str, str]]:
    """{pago_id: (día, rango)} con UNA sola consulta para toda la bandeja."""
    ids = [str(i) for p in pagos for i in (p.get("reserva_ids") or [])]
    filas = {str(f.get("id")): f for f in datos.reservas_de(list(dict.fromkeys(ids)))} if ids else {}
    out: dict[str, tuple[str, str]] = {}
    for p in pagos:
        fs = sorted((filas[str(i)] for i in (p.get("reserva_ids") or []) if str(i) in filas),
                    key=lambda f: (str(f.get("fecha") or ""), str(f.get("hora_inicio") or "")))
        if not fs:
            out[str(p["id"])] = ("", "")
            continue
        f0, f1 = fs[0], fs[-1]
        out[str(p["id"])] = (horarios.fecha_larga(str(f0.get("fecha") or "")),
                             f"{f0.get('hora_inicio')}–{f1.get('hora_fin')}" + (f" · {len(fs)} turnos" if len(fs) > 1 else ""))
    return out


ESTADO_VOUCHER = {"aprobado": ("Aprobado", "ok", "check"), "rechazado": ("Rechazado", "bad", "x"),
                  "vencido": ("Venció sin revisar", "gris", "reloj")}


def _fila_voucher(p: dict, canchas: dict, historial: bool, turno: tuple[str, str]) -> list[str]:
    """Celdas de la tabla de Pagos por confirmar (la fila lleva `data-pid`)."""
    c = canchas.get(p.get("cancha_id")) or {}
    lugar = (c.get("club") or "").strip()
    nombre_c = c.get("nombre") or "Cancha"
    dia, rango = turno
    pid = str(p["id"])
    monto = _plata(int(p.get("monto_centimos") or 0), str(p.get("moneda") or "PEN"))
    medio_k = str(p.get("medio") or "")
    medio = cd.ETIQUETA_MEDIO.get(medio_k, medio_k).replace(" bancaria", "")
    jugador = (p.get("jugador_nombre") or "").strip() or p.get("jugador_email") or "Jugador"
    estado = str(p.get("estado") or "")
    comp = (f"<button type='button' class='vcl-mini-img' data-zoom='{e(pid)}' aria-label='Ver el comprobante de {e(jugador)} en grande'>"
            f"{svg('recibo', 22)}<img src='/anfitrion/pagos-por-confirmar/{e(pid)}/imagen' alt='Comprobante de {e(jugador)}' loading='lazy'></button>")
    op = p.get("operacion") or ""
    monto_td = (f"<b class='vcl-monto'>{e(monto)}</b><small class='vcl-medio'>{svg(ICONO_MEDIO.get(medio_k, 'tarjeta'), 13)}"
                f"{e(medio)}" + (f" · N.º {e(op)}" if op else " · sin N.º de operación") + "</small>")
    jug_td = f"<b>{e(jugador)}</b>" + (f"<small>{e(p.get('jugador_email'))}</small>" if p.get("jugador_email") and p.get("jugador_email") != jugador else "")
    cancha_td = (f"<b>{e(nombre_c)}</b>" + (f"<small>{e(lugar)}</small>" if lugar and lugar != nombre_c else "")
                 + (f"<small>{e(dia)} · {e(rango)}</small>" if dia else ""))
    if historial:
        txt, tono, ic = ESTADO_VOUCHER.get(estado, (estado or "Resuelto", "gris", ""))
        motivo = str(p.get("motivo_rechazo") or "")
        motivo = "" if motivo in ("sin_revision", "apartado_perdido") else cdw.MOTIVOS_RECHAZO.get(motivo, motivo)
        por = str(p.get("resuelto_por") or "").strip().lower()
        det = ""
        if motivo:
            det = f"<small>Motivo: {e(motivo)}</small>"
        if estado == "vencido":
            det += "<small>Por el sistema: nadie lo revisó a tiempo</small>"
        elif por and por != str(p.get("dueno") or "").lower():
            det += f"<small>Por {e(por)} (recepción)</small>"
        est_td = va.pill(txt, tono, ic) + det
        acc = f"<button type='button' class='vcl-ver' data-zoom='{e(pid)}'>Ver</button>"
    else:
        est_td = (va.pill("Por revisar", "warn", "reloj")
                  + f"<small class='vv-vence' data-vence='{e(p.get('vence_en'))}'>Vence pronto</small>")
        acc = (f"<div class='vcl-acc'><button type='button' class='btn' data-aprobar='{e(pid)}' data-monto='{e(monto)}'>Aprobar</button>"
               f"<button type='button' class='btn peligro' data-rechazar='{e(pid)}'>Rechazar</button></div>")
    return [comp, monto_td, jug_td, cancha_td, est_td, acc]


def tabla_filas(cabeceras: list[str], filas: list[list[str]], *, clase: str = "", attrs: list[str] | None = None) -> str:
    """= `va.tabla` (mismo marcado: en el celular cada fila es una tarjeta) con
    atributos por fila (`data-pid` que usa el JS para quitarla)."""
    attrs = attrs or [""] * len(filas)
    cab = "".join(f"<th scope='col'>{e(c)}</th>" for c in cabeceras)
    cuerpo = "".join(f"<tr {a}>" + "".join(f"<td data-et='{e(cabeceras[i] if i < len(cabeceras) else '')}'><div class='vcl-c'>{v}</div></td>"
                                           for i, v in enumerate(f)) + "</tr>" for f, a in zip(filas, attrs))
    return f"<div class='va-tabla-w'><table class='va-tabla {e(clase)}'><thead><tr>{cab}</tr></thead><tbody>{cuerpo}</tbody></table></div>"


def _locales_operables(canchas: list[dict]) -> list[tuple[str, str, set]]:
    """[(local_key, nombre, {cancha_id})] de las canchas que se operan."""
    import fidelidad
    g: dict[str, list] = {}
    for c in canchas:
        k = fidelidad.local_key(c)
        g.setdefault(k, [(c.get("club") or "").strip() or c.get("nombre") or "Local", set()])[1].add(c["id"])
    return [(k, n, ids) for k, (n, ids) in g.items()]


@router.get("/anfitrion/pagos-por-confirmar", response_class=HTMLResponse)
def pagina_pagos_por_confirmar(request: Request, estado: str = "", local: str = "", ver: str = "") -> HTMLResponse:
    ses, resp = _sesion_o_entrar(request, "/anfitrion/pagos-por-confirmar")
    if resp is not None:
        return resp
    email = ses["email"]
    historial = estado == "historial"
    lista_c = permisos.canchas_para(email, permisos.VOUCHERS)
    canchas = {c["id"]: c for c in lista_c}
    locales = _locales_operables(lista_c)
    loc = next((x for x in locales if x[0] == local), None)
    disp = cd.disponible()
    en_rev = cdw.bandeja_operable(email, "en_revision") if disp else []
    resueltos = cdw.bandeja_operable(email, "historial") if disp else []
    if loc is not None:
        en_rev = [p for p in en_rev if p.get("cancha_id") in loc[2]]
        resueltos = [p for p in resueltos if p.get("cancha_id") in loc[2]]
    cuenta = {k: sum(1 for p in resueltos if p.get("estado") == k) for k in ESTADO_VOUCHER}
    ver = ver if historial and ver in ESTADO_VOUCHER else ""
    pagos = ([p for p in resueltos if not ver or p.get("estado") == ver] if historial else en_rev)

    def url(**kw) -> str:
        q = {"estado": "historial" if historial else "", "local": loc[0] if loc else "", "ver": ver} | kw
        qs = "&".join(f"{k}={quote(str(v))}" for k, v in q.items() if v)
        return "/anfitrion/pagos-por-confirmar" + (f"?{qs}" if qs else "")

    seg = va.segmentado([(url(estado="", ver=""), "Por revisar", not historial), (url(estado="historial", ver=""), "Resueltos", historial)],
                        etiqueta="Pagos", contar={"Por revisar": len(en_rev), "Resueltos": len(resueltos)})
    sel_local = ""
    if len(locales) > 1:
        sel_local = ("<label class='vcl-sel'><span class='vh'>Local</span><select data-ir aria-label='Filtrar por local'>"
                     f"<option value='{e(url(local=''))}'>Todos los locales</option>"
                     + "".join(f"<option value='{e(url(local=k))}'{' selected' if loc and loc[0] == k else ''}>{e(n)}</option>"
                               for k, n, _ in locales) + "</select></label>")
    chips = ""
    if historial:
        chips = "<div class='vcl-chips' role='group' aria-label='Filtrar resueltos'>" + "".join(
            f"<a class='vcl-chip {tono}{' sel' if ver == k else ''}' href='{e(url(ver='' if ver == k else k))}'"
            + (" aria-current='true'" if ver == k else "") + f">{svg(ic, 14)}{e(txt.replace('Venció sin revisar', 'Vencidos').replace('Aprobado', 'Aprobados').replace('Rechazado', 'Rechazados'))}: {cuenta[k]}</a>"
            for k, (txt, tono, ic) in ESTADO_VOUCHER.items()) + "</div>"
    barra = f"<div class='vcl-barra-f'>{seg}<div class='vcl-filtros'>{sel_local}{chips}</div></div>"
    if pagos:
        turnos = _turnos_de(pagos)
        filas = [_fila_voucher(p, canchas, historial, turnos.get(str(p["id"]), ("", ""))) for p in pagos]
        tabla = tabla_filas(["Comprobante", "Monto y operación", "Jugador", "Cancha", "Estado", ""], filas, clase="vcl-vv",
                            attrs=[f"class='vv' data-pid='{e(str(p['id']))}'" for p in pagos])
        lista = va.panel(tabla, clase="vcl-tabla-p")
    elif not disp:
        lista = va.panel(va.vacio("recibo", "Aún no disponible", "El cobro directo aún no está disponible en este ambiente."))
    elif historial:
        lista = va.panel(va.vacio("recibo", "Nada por aquí" if ver else "Aún no resolviste pagos",
                                  "Prueba con otro filtro." if ver else "Los comprobantes que apruebes, rechaces o que venzan aparecen aquí."))
    else:
        lista = va.panel(va.vacio("recibo", "No tienes comprobantes por revisar",
                                  "Cuando un jugador te pague por " + ("Yape, Plin o transferencia" if any(_pais_de_c(c) == "PE" for c in lista_c) or not lista_c
                                                                       else "QR, transferencia o billetera")
                                  + ", su comprobante aparece aquí para que lo confirmes."))
    cfg = {"motivos": [{"k": k, "n": n} for k, n in MOTIVOS_RECHAZO]}
    medios_txt = "tu Yape, Plin o banco" if any(_pais_de_c(c) == "PE" for c in lista_c) else "tu banco o billetera"
    cuerpo = (va.cabecera("Pagos por confirmar", f"Compara cada comprobante con el movimiento en {medios_txt}. "
                          "Si no lo revisas a tiempo, la reserva se libera sola.")
              + _dividir_web.aviso_devoluciones(email) + barra + lista
              + f"<script>window.__vv={_js(cfg)};</script><script>{JS_VOUCHERS}</script>")
    return pagina_vista("Pagos por confirmar", cuerpo, ses)


@router.get("/anfitrion/pagos-por-confirmar/{pid}/imagen")
def imagen_voucher(request: Request, pid: str) -> Response:
    ses = sesion.de_request(request)
    if not ses:
        return Response(status_code=401)
    if cdw.pago_operable(pid, ses["email"]) is None:
        return Response(status_code=404)
    datos_img, mime = cd.repo().imagen_voucher(pid)
    if not datos_img:
        return Response(status_code=404)
    return Response(content=datos_img, media_type=mime or "image/jpeg", headers={"Cache-Control": "private, no-store"})


@router.post("/anfitrion/pagos-por-confirmar/{pid}/aprobar")
async def aprobar_voucher(request: Request, pid: str) -> JSONResponse:
    ses, _b, malo = await _cuerpo(request)
    if malo is not None:
        return malo
    return await run_in_threadpool(_aprobar, ses["email"], pid)


def _aprobar(email: str, pid: str) -> JSONResponse:
    p = cdw.pago_operable(pid, email)
    if p is None:
        return _err("no_encontrado", 404)
    r = cdw.aprobar_voucher(p, email)  # `resuelto_por` = quien aprobó (dueño o su recepción)
    if not r.get("ok"):
        return _err(r.get("error") or "error", 409)
    permisos.auditar(email, datos.cancha(str(p.get("cancha_id") or "")), "voucher_aprobado", pid,
                     {"monto_centimos": int(p.get("monto_centimos") or 0), "moneda": str(p.get("moneda") or ""), "cliente": p.get("jugador_nombre") or p.get("jugador_email") or ""})
    print(f"[vouchers-web] {email} aprobó {pid}", flush=True)
    return JSONResponse({"ok": True, "comision": r.get("comision")})


@router.post("/anfitrion/pagos-por-confirmar/{pid}/rechazar")
async def rechazar_voucher(request: Request, pid: str) -> JSONResponse:
    ses, b, malo = await _cuerpo(request)
    if malo is not None:
        return malo
    clave = str(b.get("motivo") or "")
    if clave not in cdw.MOTIVOS_RECHAZO:
        return _err("Elige el motivo del rechazo.", 400)
    return await run_in_threadpool(_rechazar, ses["email"], pid, clave)


def _rechazar(email: str, pid: str, motivo: str) -> JSONResponse:
    p = cdw.pago_operable(pid, email)
    if p is None:
        return _err("no_encontrado", 404)
    r = cdw.rechazar_voucher(p, email, motivo)
    if not r.get("ok"):
        return _err(r.get("error") or "error", 409)
    permisos.auditar(email, datos.cancha(str(p.get("cancha_id") or "")), "voucher_rechazado", pid, {"motivo": motivo, "cliente": p.get("jugador_nombre") or p.get("jugador_email") or ""})
    print(f"[vouchers-web] {email} rechazó {pid} ({motivo})", flush=True)
    return JSONResponse({"ok": True})


# ── Reglas de reserva (reglas_reserva_screen.dart) ───────────────────────────

def _cancha_propia(email: str, cancha_id: str) -> tuple[dict | None, list[dict]]:
    canchas = datos.canchas_de_dueno(email)
    return next((c for c in canchas if c["id"] == cancha_id), None), canchas


@router.get("/anfitrion/reglas", response_class=HTMLResponse)
def pagina_reglas_elegir(request: Request):
    """Sin cancha elegida: abre la primera (la columna izquierda deja cambiar)."""
    ses, resp = _sesion_o_entrar(request, "/anfitrion/reglas")
    if resp is not None:
        return resp
    canchas = datos.canchas_de_dueno(ses["email"])
    if not canchas and permisos.es_solo_encargado(ses["email"]):
        from web import anfitrion_encargados as _enc
        return _enc.sin_permiso(ses, "")
    if canchas:
        return RedirectResponse(f"/anfitrion/reglas/{quote(_ordenar_por_local(canchas)[0]['id'])}", status_code=303)
    cuerpo = (va.cabecera("Reglas de reserva", SUB_REGLAS)
              + va.panel(va.vacio("horario", "Registra tu cancha para configurar sus reglas",
                                  "Horario por día, días cerrados, precios por franja y tu política de cancelación.",
                                  "<a class='btn' href='/anfitrion/nueva'>Registrar mi cancha</a>")))
    return pagina_vista("Reglas de reserva", cuerpo, ses)


SUB_REGLAS = "Elige una cancha y ajusta sus reglas. Puedes copiarlas a las demás canchas de tu local."


def _opciones_hora() -> list[str]:
    return [f"{h:02d}:{m:02d}" for h in range(24) for m in (0, 30)]


def _ordenar_por_local(canchas: list[dict]) -> list[dict]:
    return sorted(canchas, key=lambda x: ((x.get("club") or x.get("nombre") or "").strip().lower(), x.get("nombre") or ""))


@router.get("/anfitrion/reglas/{cancha_id}", response_class=HTMLResponse)
def pagina_reglas(request: Request, cancha_id: str) -> HTMLResponse:
    ses, resp = _sesion_o_entrar(request, f"/anfitrion/reglas/{cancha_id}")
    if resp is not None:
        return resp
    c, canchas = _cancha_propia(ses["email"], cancha_id)
    if c is None:
        from web.router import _no_encontrada
        r = _no_encontrada("Cancha no encontrada")
        r.status_code = 404
        return r
    from pagos import devoluciones
    sim, iso = _moneda_de(c)
    club = (c.get("club") or "").strip().lower()
    canchas = _ordenar_por_local(canchas)
    otras = [x for x in canchas if x["id"] != c["id"]]
    otras.sort(key=lambda x: ((x.get("club") or "").strip().lower() != club, x.get("nombre") or ""))
    hoy = horarios.ahora_local(_pais_de_c(c)).date()
    precio, unidad = horarios.precio_publico(c)
    cfg = {"cancha": c["id"], "moneda": sim, "reglas": _reglas.de_cancha(c),
           "base": {"apertura": c.get("hora_apertura") or "07:00", "cierre": c.get("hora_cierre") or "23:00",
                    "paso": int(c.get("duracion_slot_min") or 60), "precio": round(float(precio or 0), 2),
                    "unidad": "turno" if unidad != "por hora" else "hora"},
           "horas": _opciones_hora(), "motivos": MOTIVOS_CIERRE, "nombres": NOMBRES_FRANJA,
           "dias": [{"k": k, "n": n} for k, n in zip(_reglas.DIAS_SEMANA, ("Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"))],
           "meses": horarios.MESES, "diasCortos": horarios.DIAS,
           "global_cancelacion": float(devoluciones.horas_minimas({k: v for k, v in c.items() if k != "reglas_reserva"})),
           "hoy": hoy.isoformat(), "disponible": datos.col_reglas_disponible(),
           "otras": [{"id": x["id"], "nombre": x.get("nombre") or "Cancha", "club": (x.get("club") or "").strip() or "Otro local",
                      "mismo": (x.get("club") or "").strip().lower() == club and bool(club),
                      "otra_moneda": _moneda_de(x)[1] != iso, "moneda": _moneda_de(x)[0]} for x in otras]}
    con_reglas = [x for x in canchas if _reglas.de_cancha(x)]
    lat = va.lista_lateral(canchas, c["id"], lambda x: f"/anfitrion/reglas/{x['id']}", contar=f"{len(con_reglas)} con reglas",
                           sub=lambda x: f"{x.get('hora_apertura') or '07:00'}–{x.get('hora_cierre') or '23:00'} · turnos de {int(x.get('duracion_slot_min') or 60)} min",
                           insignia=lambda x: va.pill("Con reglas", "ok") if _reglas.de_cancha(x) else "",
                           filtro=len(canchas) > 6)
    mismas = [x for x in otras if (x.get("club") or "").strip().lower() == club and club]
    copiar_txt = f"Copiar a {mismas[0]['nombre']}" if len(mismas) == 1 and len(otras) == 1 else "Copiar a otras canchas"
    copiar = (f"<button type='button' class='btn sec' id='rgCopiar'{'' if cfg['disponible'] else ' disabled'}>{svg('copiar', 16)} {e(copiar_txt)}</button>"
              if otras else "")
    sub_top = " · ".join(x for x in ((c.get("club") or "").strip(), f"{sim} {precio:.2f} {unidad}") if x)
    top = (f"<section class='va-panel vcl-rg-top'><div class='vcl-rg-tit'><h2>{e(c['nombre'])}</h2><p>{e(sub_top)}</p></div>"
           f"<div class='vcl-rg-acc'>{copiar}<button type='submit' class='btn rg-guardar'{'' if cfg['disponible'] else ' disabled'}>Guardar cambios</button></div></section>")
    editar = f"/anfitrion/cancha/{quote(c['id'])}/editar"
    horario = va.panel(
        "<div id='rgSemana'></div><div class='vcl-rg-pie'><button type='button' class='vcl-link' id='rgPorDia'></button></div>"
        f"<p class='vcl-nota'>El cierre es la hora en que empieza el último turno. Turnos de {int(cfg['base']['paso'])} min "
        f"(se cambia en <a href='{e(editar)}'>Editar cancha</a>).</p>",
        "Horario de atención", "Por día de la semana", clase="vcl-rg-p")
    franjas = va.panel(
        "<div id='rgFranjas'></div><div class='vcl-rg-pie'><button type='button' class='vcl-link' id='rgFranjaNueva'>＋ Agregar franja</button></div>"
        "<div id='rgFranjaForm' class='vcl-form' hidden></div>"
        "<h3 class='vcl-h3'>Recargo de luz</h3><p class='vcl-nota vcl-nota-a'>Un monto fijo por turno desde que se prenden las luces.</p><div id='rgLuz'></div>",
        "Franjas y precios", "Precio distinto según el día y la hora (manda sobre la hora feliz)", clase="vcl-rg-p")
    cierres = va.panel(
        "<div id='rgCierres'></div>"
        "<button type='button' class='vcl-agregar' id='rgCierreAbrir'>＋ Agregar día cerrado</button>"
        "<div id='rgCierreBox' class='vcl-form' hidden><label for='rgCierreF'>Fecha</label>"
        f"<input type='date' id='rgCierreF' min='{hoy.isoformat()}'>"
        "<label>Motivo</label><div class='chips' id='rgCierreM' role='group' aria-label='Motivo del cierre'></div>"
        "<div class='vcl-form-acc'><button type='button' class='btn' id='rgCierreAdd'>Agregar día cerrado</button>"
        "<button type='button' class='btn sec' id='rgCierreNo'>Cancelar</button></div></div>"
        "<p class='vcl-nota'>Se muestran rayados en el calendario y nadie puede reservar esos días.</p>",
        "Días cerrados", "Feriados, mantenimiento o eventos", clase="vcl-rg-p")
    politica = va.panel("<div id='rgPolitica' class='vcl-pol'></div>", "Cancelación y reserva", "Lo que ve el jugador al reservar",
                        clase="vcl-rg-p")
    vista = va.panel(
        f"<div class='vcl-rg-vista'><div><label for='rgVistaF'>Día</label><input type='date' id='rgVistaF' value='{hoy.isoformat()}' min='{hoy.isoformat()}'></div>"
        "<button type='button' class='btn sec' id='rgVistaBtn'>Ver ese día</button></div>"
        "<div id='rgVista' aria-live='polite'></div>",
        "Vista previa", "Así verá el jugador ese día con lo que tienes en pantalla, aunque no lo hayas guardado.", clase="vcl-rg-p")
    aviso = "" if cfg["disponible"] else va.aviso("Las reglas de reserva aún no están activas en este ambiente: puedes verlas pero no guardarlas.", "warn")
    form = ("<form id='rgForm' class='vcl-rg-main' novalidate>" + top + aviso
            + f"<div class='vcl-rg-grid'><div class='vcl-col'>{horario}{franjas}</div><div class='vcl-col'>{cierres}{politica}</div></div>"
            + vista + "<div class='aviso err' id='rgErr' role='alert' hidden></div>"
            f"<div class='vcl-rg-barra'><a class='btn sec' href='/anfitrion/calendario?cancha={e(quote(c['id']))}'>Ver calendario</a>"
            f"<button type='submit' class='btn rg-guardar'{'' if cfg['disponible'] else ' disabled'}>Guardar cambios</button></div></form>")
    cuerpo = (va.cabecera("Reglas de reserva", SUB_REGLAS) + f"<div class='va-lado vcl-rg'>{lat}{form}</div>"
              + f"<script>window.__rg={_js(cfg)};</script><script>{JS_REGLAS}</script>")
    return pagina_vista(f"Reglas de {c['nombre']}", cuerpo, ses)


def _pais_de_c(c: dict) -> str:
    from web.router import _pais_de
    return _pais_de(c)


def vista_del_dia(c: dict, reglas: dict, fecha: str) -> dict:
    """Turnos y precios de un día con las reglas `reglas` (aún sin guardar):
    la MISMA cancha efectiva (`cancha_del_dia`) y el MISMO precio
    (`precio_turno_de`) que usa la ficha pública."""
    c2 = dict(c, reglas_reserva=_reglas.normalizar(reglas))
    cdia = _reglas.cancha_del_dia(c2, fecha)
    sim, _iso = _moneda_de(c)
    if cdia.get("_cerrado"):
        return {"ok": True, "fecha": fecha, "cerrado": _motivo_cierre(cdia["_cerrado"]), "turnos": [], "moneda": sim}
    paso = int(cdia.get("duracion_slot_min") or 60)
    horas = horarios.slots_de(cdia)
    fechas = sorted({horarios.fecha_real(fecha, cdia["hora_apertura"], cdia["hora_cierre"], h) for h in horas} | {fecha})
    desc = datos.descuentos(c["id"], fechas)
    etq = getattr(_reglas, "etiqueta_turno", None)
    out = []
    for h in horas:
        fr = horarios.fecha_real(fecha, cdia["hora_apertura"], cdia["hora_cierre"], h)
        t = {"hora": h, "fin": horarios.hora_fin(h, paso), "precio": horarios.precio_turno_de(cdia, h, desc.get((fr, h), 0))}
        if etq is not None:
            t.update(etq(cdia, h) or {})
        out.append(t)
    return {"ok": True, "fecha": fecha, "cerrado": "", "turnos": out, "moneda": sim,
            "horario": f"{cdia['hora_apertura']}–{cdia['hora_cierre']}"}


@router.post("/anfitrion/reglas/{cancha_id}/vista")
async def vista_reglas(request: Request, cancha_id: str) -> JSONResponse:
    ses, b, malo = await _cuerpo(request)
    if malo is not None:
        return malo
    return await run_in_threadpool(_vista, ses["email"], cancha_id, b)


def _vista(email: str, cancha_id: str, b: dict) -> JSONResponse:
    c, _ = _cancha_propia(email, cancha_id)
    if c is None:
        return _err("no_encontrada", 404)
    fecha = str(b.get("fecha") or "")
    try:
        date.fromisoformat(fecha)
    except ValueError:
        return _err("Elige un día válido.", 400)
    return JSONResponse(vista_del_dia(c, b.get("reglas") if isinstance(b.get("reglas"), dict) else {}, fecha))


@router.post("/anfitrion/reglas/guardar")
async def guardar_reglas(request: Request) -> JSONResponse:
    ses, b, malo = await _cuerpo(request)
    if malo is not None:
        return malo
    return await run_in_threadpool(_guardar_reglas, ses["email"], b)


def guardar_reglas_de(email: str, cancha_ids: list, reglas: dict) -> tuple[int, dict]:
    """Misma validación que `PUT /reservas/reglas` del APK: canchas del
    correo (si una no lo es, no se guarda ninguna), reglas normalizadas, y
    todas las filas escritas o error."""
    ids = list(dict.fromkeys(str(i).strip() for i in (cancha_ids or []) if str(i or "").strip()))[:50]
    if not ids:
        return 400, {"ok": False, "error": "sin_canchas"}
    propias = {c["id"] for c in datos.canchas_de_dueno(email)}
    if any(i not in propias for i in ids):
        return 404, {"ok": False, "error": "no_es_tu_cancha"}
    if not datos.col_reglas_disponible():
        return 503, {"ok": False, "error": "reglas_no_disponibles"}
    norm = _reglas.normalizar(reglas if isinstance(reglas, dict) else {})
    n = datos.guardar_reglas(ids, email, norm)
    if n != len(ids):
        return 409, {"ok": False, "error": "no_se_guardo"}
    return 200, {"ok": True, "canchas": n, "reglas": norm}


def _guardar_reglas(email: str, b: dict) -> JSONResponse:
    status, r = guardar_reglas_de(email, b.get("cancha_ids") if isinstance(b.get("cancha_ids"), list) else [], b.get("reglas"))
    if status != 200:
        msg = {"sin_canchas": "Elige al menos una cancha.", "no_es_tu_cancha": "Una de esas canchas no está a tu nombre.",
               "reglas_no_disponibles": "Las reglas de reserva aún no están activas en este ambiente.",
               "no_se_guardo": "No pudimos guardar en todas las canchas. Inténtalo de nuevo."}.get(r["error"], r["error"])
        return JSONResponse({"ok": False, "error": r["error"], "mensaje": msg}, status_code=status)
    print(f"[reglas-web] {email} guardó reglas en {r['canchas']} cancha(s)", flush=True)
    return JSONResponse(r)


# Lo de las reglas que lleva PLATA (precio de franja, recargo de luz): solo
# viaja a canchas que cobran en la MISMA moneda.
CLAVES_CON_PRECIO = ("franjas", "recargo_luz")


def copiar_reglas_de(email: str, origen_id: str, destinos: list) -> tuple[int, dict]:
    """Copia las reglas GUARDADAS de `origen_id` (normalizadas) a otras canchas
    del MISMO dueño. A una cancha que cobra en otra moneda NO se le copian las
    franjas con precio ni el recargo de luz: conserva los suyos y se avisa
    (`sin_precios`). Si una cancha no es suya, no se toca ninguna."""
    canchas = {c["id"]: c for c in datos.canchas_de_dueno(email)}
    origen = canchas.get(str(origen_id or ""))
    if origen is None:
        return 404, {"ok": False, "error": "no_es_tu_cancha"}
    ids = [i for i in dict.fromkeys(str(x).strip() for x in (destinos or []) if str(x or "").strip()) if i != origen["id"]][:50]
    if not ids:
        return 400, {"ok": False, "error": "sin_destinos"}
    if any(i not in canchas for i in ids):
        return 404, {"ok": False, "error": "no_es_tu_cancha"}
    if not datos.col_reglas_disponible():
        return 503, {"ok": False, "error": "reglas_no_disponibles"}
    norm = _reglas.de_cancha(origen)
    iso_o = _moneda_de(origen)[1]
    con_precio = any(k in norm for k in CLAVES_CON_PRECIO)
    # Agrupa por las reglas que le tocan a cada destino: una escritura por
    # grupo (casi siempre 1 o 2), nunca una consulta por cancha.
    grupos: dict[str, tuple[dict, list[str]]] = {}
    sin_precios: list[dict] = []
    for i in ids:
        d = canchas[i]
        r = norm
        if _moneda_de(d)[1] != iso_o and con_precio:
            propias = _reglas.de_cancha(d)
            r = {k: v for k, v in norm.items() if k not in CLAVES_CON_PRECIO} | {k: propias[k] for k in CLAVES_CON_PRECIO if k in propias}
            sin_precios.append({"id": i, "nombre": d.get("nombre") or "Cancha", "moneda": _moneda_de(d)[0]})
        r = _reglas.normalizar(r)
        grupos.setdefault(json.dumps(r, sort_keys=True), (r, []))[1].append(i)
    n = sum(datos.guardar_reglas(lista, email, r) for r, lista in grupos.values())
    if n != len(ids):
        return 409, {"ok": False, "error": "no_se_guardo"}
    return 200, {"ok": True, "copiadas": n, "sin_precios": sin_precios, "reglas": norm}


MSG_COPIAR = {"sin_destinos": "Elige al menos una cancha.", "no_es_tu_cancha": "Una de esas canchas no está a tu nombre.",
              "reglas_no_disponibles": "Las reglas de reserva aún no están activas en este ambiente.",
              "no_se_guardo": "No pudimos copiar a todas las canchas. Inténtalo de nuevo."}


@router.post("/anfitrion/reglas/{cancha_id}/copiar")
async def copiar_reglas(request: Request, cancha_id: str) -> JSONResponse:
    """"Copiar a otras canchas": solo el DUEÑO y solo a canchas suyas."""
    ses, b, malo = await _cuerpo(request)
    if malo is not None:
        return malo
    return await run_in_threadpool(_copiar_reglas, ses["email"], cancha_id, b)


def _copiar_reglas(email: str, cancha_id: str, b: dict) -> JSONResponse:
    destinos = b.get("destinos") if isinstance(b.get("destinos"), list) else []
    status, r = copiar_reglas_de(email, cancha_id, destinos)
    if status != 200:
        return JSONResponse({"ok": False, "error": r["error"], "mensaje": MSG_COPIAR.get(r["error"], r["error"])}, status_code=status)
    print(f"[reglas-web] {email} copió las reglas de {cancha_id} a {r['copiadas']} cancha(s)", flush=True)
    return JSONResponse(r)


# ── estilos y scripts ────────────────────────────────────────────────────────

CSS = """
.panel h2{margin-top:0}
.cl-insignia{display:inline-flex;align-items:center;justify-content:center;min-width:24px;height:24px;padding:0 7px;border-radius:12px;background:var(--bad-fg);color:var(--blanco);font-weight:800;font-size:13px}
.cc-pend{display:flex;align-items:center;gap:12px;margin-top:16px;padding:14px 16px;border-radius:var(--r);background:var(--warn-bg);color:var(--warn-fg);text-decoration:none;min-height:44px}
.cc-pend span:nth-child(2){flex:1}.cc-pend small{display:block;font-weight:600}.cc-pend .chev{font-size:24px}
.cc-ok{display:flex;gap:10px;align-items:center;background:var(--ok-bg);color:var(--ok-fg);border-radius:var(--r);padding:12px 14px}
.cc-ok small{display:block;margin-top:2px}
.cc-dl{display:grid;grid-template-columns:auto minmax(0,1fr);gap:6px 12px;margin:14px 0}
.cc-dl dt{color:var(--tenue);font-weight:700}.cc-dl dd{margin:0;overflow-wrap:anywhere}
.cc-copiar{display:flex;gap:8px}.cc-copiar input{flex:1;min-width:0}
.cc-rojo,.btn.sec.cc-rojo{color:var(--rojo)}
.cc-medio{display:flex;gap:12px;align-items:center;border:1px solid var(--trazo);border-radius:var(--r);padding:12px 14px;margin-top:10px;flex-wrap:wrap}
.cc-medio>div{flex:1;min-width:180px}.cc-medio small{display:block;color:var(--tenue);font-weight:600;overflow-wrap:anywhere}
.cc-medio img{width:56px;height:56px;object-fit:cover;border-radius:10px}
.btn,.chip{min-height:44px}
.btn:focus-visible,.chip:focus-visible,a:focus-visible,input:focus-visible,button:focus-visible{outline:3px solid var(--esmeralda);outline-offset:2px}
.vv-lista{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(340px,100%),1fr));gap:14px;margin-top:8px}
.vv{display:flex;gap:14px;background:var(--blanco);border:1px solid var(--trazo);border-radius:var(--r);padding:14px;box-shadow:var(--sombra);min-width:0}
.vv-img{flex:none;width:96px;height:128px;padding:0;border:0;border-radius:12px;overflow:hidden;background:var(--gris);cursor:zoom-in}
.vv-img img{width:100%;height:100%;object-fit:cover;display:block}
.vv-cuerpo{flex:1;min-width:0}.vv-monto{font-size:22px;font-weight:800}
.vv .acc{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-top:10px}
.vv-vence{font-size:13px;font-weight:700;color:var(--warn-fg);width:100%}
.vv-vence.tarde{color:var(--bad-fg)}
.vv-zoom{max-width:100%;max-height:70vh;border-radius:12px;display:block;margin:0 auto}
.rg-dia{display:grid;grid-template-columns:110px minmax(0,1fr);gap:8px 12px;align-items:center;padding:10px 0;border-top:1px solid var(--trazo)}
.rg-dia:first-child{border-top:0}.rg-dia .chips{margin:0}
.rg-horas{display:flex;gap:8px;flex-wrap:wrap;grid-column:2}.rg-horas select{width:auto;min-height:44px}
.rg-fila{display:flex;gap:12px;flex-wrap:wrap}.rg-fila>div{flex:1;min-width:160px}
.rg-item{display:flex;gap:10px;align-items:center;justify-content:space-between;border:1px solid var(--trazo);border-radius:12px;padding:10px 12px;margin-top:8px}
.rg-item small{display:block;color:var(--tenue);font-weight:600}
.rg-her{display:flex;align-items:center;gap:8px;min-height:44px}.rg-her input{width:auto;flex:none}
.rg-her small{color:var(--tenue)}
.rg-turnos{display:flex;flex-wrap:wrap;gap:8px}
.rg-t{border:1px solid var(--trazo);border-radius:12px;padding:8px 10px;min-width:104px}
.rg-t b{display:block}.rg-t small{display:block;color:var(--tenue);font-weight:600;font-size:12px}
.rg-barra{position:sticky;bottom:0;display:flex;gap:10px;justify-content:flex-end;background:var(--blanco);border-top:1px solid var(--trazo);padding:12px 0;margin-top:18px;z-index:5}
@media(max-width:600px){.rg-dia{grid-template-columns:minmax(0,1fr)}.rg-horas{grid-column:1}.vv{flex-direction:column}.vv-img{width:100%;height:200px}}
"""

JS_CLUB = r"""
(function(){
var C=window.__club||{},$=function(i){return document.getElementById(i)};
function esc(s){return String(s==null?'':s).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]})}
async function post(url,body){var r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body||{})});var j={};try{j=await r.json()}catch(e){}j._status=r.status;return j}
function msg(j){return j.mensaje||(C.errores&&C.errores[j.error])||'No se pudo guardar. Inténtalo de nuevo.'}
document.addEventListener('click',function(ev){var b=ev.target.closest('[data-copiar]');if(!b)return;var i=$(b.dataset.copiar);
  var ok=function(){pcgToast('Copiado ✓')};if(navigator.clipboard){navigator.clipboard.writeText(i.value).then(ok,function(){i.select();})}else{i.select();document.execCommand('copy');ok()}});
var fq=$('ccCulqi');if(fq)fq.addEventListener('submit',async function(ev){ev.preventDefault();var er=$('ccCulqiErr');er.hidden=true;var b=$('ccConectar');b.disabled=true;
  pcgCargando('Comprobando con Culqi…');try{var j=await post('/anfitrion/cobros-club/culqi',{public_key:$('ccPk').value.trim(),secret_key:$('ccSk').value.trim()});
  if(j.ok){pcgRecargar('Culqi conectado ✓');return}pcgCargando(false);er.textContent=msg(j);er.hidden=false}catch(e){pcgCargando(false);er.textContent='No se pudo conectar. Revisa tu conexión.';er.hidden=false}b.disabled=false});
var dq=$('ccDesconectar');if(dq)dq.addEventListener('click',async function(){if(!await pcgConfirmar({titulo:'¿Desconectar tu Culqi?',mensaje:'Los jugadores ya no podrán pagarte con tarjeta o Yape en línea. Tus pagos manuales siguen.',confirmar:'Desconectar',destructivo:true,icono:'🔌'}))return;
  pcgCargando('Desconectando…');try{var j=await post('/anfitrion/cobros-club/culqi/desconectar',{});if(j.ok){pcgRecargar('Culqi desconectado');return}pcgCargando(false);pcgAvisar({titulo:'No se pudo',mensaje:msg(j)})}catch(e){pcgCargando(false);pcgAvisar({titulo:'No se pudo',mensaje:'Revisa tu conexión.'})}});
// ── medios manuales ──
var medios=(C.medios||[]).slice(),edit=-1,st={};
function detalle(m){if(m.tipo==='transferencia')return [m.banco,m.cuenta?('Cuenta '+m.cuenta):'',m.cci?('CCI '+m.cci):''].filter(Boolean).join(' · ');
  if(m.tipo==='qr'||m.tipo==='billetera')return [m.banco,m.numero].filter(Boolean).join(' · ')||(m.qr_url?'Con QR':'');return m.numero||''}
function cuenta(m){if(m.tipo==='transferencia')return "<b>"+esc([m.banco,m.cuenta].filter(Boolean).join(' · '))+"</b>"+(m.cci?"<small>CCI "+esc(m.cci)+"</small>":"");
  if(m.tipo==='qr'||m.tipo==='billetera')return (m.qr_url?"<img class='vcl-qr' src='"+esc(m.qr_url)+"' alt='QR de "+esc(m.titular)+"'>":"")+"<b>"+esc([m.banco,m.numero].filter(Boolean).join(' · ')||(m.qr_url?'Con QR':''))+"</b>";
  return "<b>"+esc(m.numero||'')+"</b>"}
function pintar(){var el=$('ccMedios');if(!el)return;
  if(!medios.length){el.innerHTML="<div class='va-vacio vcl-vacio-c'><b>Aún no agregas medios manuales</b><p>"+(C.pais==='PE'?'Agrega tu Yape, Plin o cuenta bancaria.':'Agrega tu QR, transferencia o billetera.')+"</p></div>";return}
  var cab=['Medio','Titular','Número / cuenta',''];
  el.innerHTML="<div class='va-tabla-w'><table class='va-tabla vcl-medios'><thead><tr>"+cab.map(function(c){return "<th scope='col'>"+c+"</th>"}).join('')+"</tr></thead><tbody>"+
    medios.map(function(m,i){return "<tr><td data-et='Medio'><span class='vcl-med'>"+(C.iconos[m.tipo]||'')+"<b>"+esc(C.etiquetas[m.tipo]||m.tipo)+"</b></span></td><td data-et='Titular'><div class='vcl-c'>"+esc(m.titular)+"</div></td><td data-et='Número / cuenta' class='vcl-cta'><div class='vcl-c'>"+cuenta(m)+"</div></td>"
    +"<td data-et=''><div class='vcl-acc-t'><button type='button' class='vcl-link' data-editar='"+i+"' aria-label='Editar "+esc(C.etiquetas[m.tipo]||m.tipo)+"'>Editar</button><button type='button' class='vcl-link rojo' data-quitar='"+i+"' aria-label='Quitar "+esc(C.etiquetas[m.tipo]||m.tipo)+"'>Quitar</button></div></td></tr>"}).join('')+"</tbody></table></div>"}
function chips(ops,sel,attr){return ops.map(function(o){var v=typeof o==='string'?o:o.v,n=typeof o==='string'?o:o.n;return "<button type='button' class='chip"+(v===sel?' sel':'')+"' "+attr+"='"+esc(v)+"' aria-pressed='"+(v===sel)+"'>"+esc(n)+"</button>"}).join('')}
function form(){var f=$('ccMedioForm'),t=st.tipo,h='';
  h+="<label>Medio</label><div class='chips' role='group' aria-label='Medio'>"+chips(C.permitidos.map(function(k){return {v:k,n:C.etiquetas[k]||k}}),t,'data-tipo')+"</div>";
  h+="<label for='mTit'>Titular <span class='req'>como aparece en el comprobante</span></label><input id='mTit' maxlength='80' autocomplete='name' value='"+esc(st.titular||'')+"'>";
  if(t==='yape'||t==='plin')h+="<label for='mNum'>Celular de "+esc(C.etiquetas[t])+"</label><input id='mNum' inputmode='numeric' maxlength='11' value='"+esc(st.numero||'')+"'>";
  if(t==='transferencia'){h+="<label>Banco</label><div class='chips' role='group' aria-label='Banco'>"+chips(C.bancos,st.banco,'data-banco')+"</div>";
    h+="<label for='mCta'>Número de cuenta</label><input id='mCta' inputmode='numeric' maxlength='30' value='"+esc(st.cuenta||'')+"'>";
    if(C.pais==='PE')h+="<label for='mCci'>CCI <span class='req'>opcional · 20 dígitos</span></label><input id='mCci' inputmode='numeric' maxlength='24' value='"+esc(st.cci||'')+"'>"}
  if(t==='qr'||t==='billetera'){if(C.billeteras.length)h+="<label>"+(t==='qr'?'Banco o app del QR':'Billetera')+"</label><div class='chips' role='group'>"+chips(C.billeteras,st.banco,'data-banco')+"</div>";
    h+="<label for='mNum'>Número <span class='req'>celular o cuenta"+(t==='qr'?' · opcional si subes el QR':'')+"</span></label><input id='mNum' inputmode='numeric' maxlength='15' value='"+esc(st.numero||'')+"'>";
    if(C.qr)h+="<label for='mQr'>Imagen del QR</label><input type='file' id='mQr' accept='image/*'>"+(st.qr_url?"<p class='sub'>QR cargado ✓ <img src='"+esc(st.qr_url)+"' alt='' style='width:56px;height:56px;vertical-align:middle;border-radius:8px'></p>":"")}
  h+="<div class='aviso err' id='mErr' role='alert' hidden></div><div class='vcl-form-acc'><button type='submit' class='btn'>Guardar medio</button><button type='button' class='btn sec' id='mCancelar'>Cancelar</button></div>";
  f.innerHTML=h;f.hidden=false;var q=$('mQr');if(q)q.addEventListener('change',subirQr)}
function leer(){['titular:mTit','numero:mNum','cuenta:mCta','cci:mCci'].forEach(function(p){var a=p.split(':'),i=$(a[1]);if(i)st[a[0]]=i.value})}
async function subirQr(){var i=$('mQr'),f=i.files&&i.files[0];if(!f)return;leer();pcgCargando('Subiendo el QR…');
  try{var r=await fetch('/anfitrion/cobros-club/qr',{method:'POST',headers:{'Content-Type':f.type||'image/jpeg'},body:f});var j=await r.json();pcgCargando(false);
    if(j.ok){st.qr_url=j.url;form();pcgToast('QR cargado ✓')}else pcgAvisar({titulo:'No se pudo subir',mensaje:j.mensaje||j.error})}catch(e){pcgCargando(false);pcgAvisar({titulo:'No se pudo subir',mensaje:'Revisa tu conexión.'})}}
async function guardar(lista,txt){pcgCargando(txt||'Guardando…');try{var j=await post('/anfitrion/cobros-club/medios',{medios:lista});pcgCargando(false);
  if(j.ok){medios=j.medios||lista;pintar();$('ccMedioForm').hidden=true;pcgToast('Guardado ✓');return true}
  var er=$('mErr');if(er&&!$('ccMedioForm').hidden){er.textContent=msg(j);er.hidden=false}else pcgAvisar({titulo:'No se pudo',mensaje:msg(j)})}catch(e){pcgCargando(false);pcgAvisar({titulo:'No se pudo',mensaje:'Revisa tu conexión.'})}return false}
var ag=$('ccAgregar');if(ag)ag.addEventListener('click',function(){edit=-1;st={tipo:C.permitidos[0]};form();$('ccMedioForm').scrollIntoView({behavior:'smooth',block:'nearest'})});
var fm=$('ccMedioForm');if(fm){fm.addEventListener('click',function(ev){var b=ev.target.closest('[data-tipo],[data-banco],#mCancelar');if(!b)return;
  if(b.id==='mCancelar'){fm.hidden=true;return}leer();if(b.dataset.tipo){st.tipo=b.dataset.tipo;st.banco=''}else st.banco=b.dataset.banco;form()});
  fm.addEventListener('submit',function(ev){ev.preventDefault();leer();var m={tipo:st.tipo,titular:st.titular||'',numero:st.numero||'',banco:st.banco||'',cuenta:st.cuenta||'',cci:st.cci||'',qr_url:st.qr_url||''};
    var lista=medios.slice();if(edit>=0)lista[edit]=m;else lista.push(m);guardar(lista)})}
var cm=$('ccMedios');if(cm)cm.addEventListener('click',async function(ev){var b=ev.target.closest('[data-editar],[data-quitar]');if(!b)return;
  if(b.dataset.editar!=null){edit=+b.dataset.editar;st=Object.assign({},medios[edit]);form();$('ccMedioForm').scrollIntoView({behavior:'smooth',block:'center'});return}
  var i=+b.dataset.quitar;if(!await pcgConfirmar({titulo:'¿Quitar este medio?',mensaje:'Los jugadores ya no lo verán al pagar.',confirmar:'Quitar',destructivo:true}))return;
  var lista=medios.slice();lista.splice(i,1);guardar(lista,'Quitando…')});
pintar();
})();
"""

JS_VOUCHERS = r"""
(function(){
var V=window.__vv||{},motivo='';
async function post(url,body){var r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body||{})});var j={};try{j=await r.json()}catch(e){}return j}
function quitar(pid){var a=document.querySelector(".vv[data-pid='"+pid+"']");if(a)a.remove();if(!document.querySelector('.vv'))pcgRecargar()}
function vence(){document.querySelectorAll('[data-vence]').forEach(function(el){var t=Date.parse(el.dataset.vence);if(isNaN(t))return;var m=Math.round((t-Date.now())/60000);
  el.classList.toggle('tarde',m<=10);el.textContent=m>0?('Vence en '+(m>=1440?(Math.floor(m/1440)+' día'+(m>=2880?'s':'')+(Math.floor(m%1440/60)?' '+Math.floor(m%1440/60)+' h':'')):m>=60?(Math.floor(m/60)+' h '+(m%60)+' min'):(m+' min'))):'Venció: la reserva se liberará'})}
vence();setInterval(vence,30000);
document.addEventListener('error',function(ev){var t=ev.target;if(t&&t.tagName==='IMG'&&t.closest('.vcl-mini-img'))t.hidden=true},true);
document.addEventListener('change',function(ev){var s=ev.target.closest&&ev.target.closest('select[data-ir]');if(s&&s.value)pcgIr(s.value,'Cargando…')});
document.addEventListener('click',async function(ev){
  var z=ev.target.closest('[data-zoom]');if(z){pcgAvisar({titulo:'Comprobante',html:"<img class='vv-zoom' src='/anfitrion/pagos-por-confirmar/"+encodeURIComponent(z.dataset.zoom)+"/imagen' alt='Comprobante en grande'>",confirmar:'Cerrar'});return}
  var mo=ev.target.closest('[data-motivo]');if(mo){motivo=mo.dataset.motivo;document.querySelectorAll('[data-motivo]').forEach(function(x){var on=x===mo;x.classList.toggle('sel',on);x.setAttribute('aria-pressed',on)});return}
  var a=ev.target.closest('[data-aprobar]');if(a){if(!await pcgConfirmar({titulo:'¿Te llegó el pago?',mensaje:'Confirma solo si ves '+a.dataset.monto+' en tu cuenta. La reserva queda confirmada y se cobra la comisión de tu saldo.',confirmar:'Sí, aprobar',icono:'✅'}))return;
    a.disabled=true;pcgCargando('Confirmando…');var j=await post('/anfitrion/pagos-por-confirmar/'+encodeURIComponent(a.dataset.aprobar)+'/aprobar',{});pcgCargando(false);
    if(j.ok){pcgToast('Reserva confirmada ✅');quitar(a.dataset.aprobar);return}a.disabled=false;pcgAvisar({titulo:'No se pudo',mensaje:j.mensaje||j.error});if(j.error==='hold_vencido'||j.error==='ya_resuelto')quitar(a.dataset.aprobar);return}
  var r=ev.target.closest('[data-rechazar]');if(r){motivo='';var h="<p style='text-align:left;margin:0 0 10px'>Elige el motivo. El horario quedará libre y le avisamos al jugador.</p><div class='chips' role='group' aria-label='Motivo'>"+
      V.motivos.map(function(m){return "<button type='button' class='chip' data-motivo='"+m.k+"' aria-pressed='false'>"+m.n+"</button>"}).join('')+"</div>";
    if(!await pcgConfirmar({titulo:'Rechazar el pago',html:h,confirmar:'Rechazar',destructivo:true,icono:'🧾'}))return;
    if(!motivo){pcgAvisar({titulo:'Falta el motivo',mensaje:'Elige por qué rechazas el pago.'});return}
    r.disabled=true;pcgCargando('Rechazando…');var j2=await post('/anfitrion/pagos-por-confirmar/'+encodeURIComponent(r.dataset.rechazar)+'/rechazar',{motivo:motivo});pcgCargando(false);
    if(j2.ok){pcgToast('Pago rechazado');quitar(r.dataset.rechazar);return}r.disabled=false;pcgAvisar({titulo:'No se pudo',mensaje:j2.mensaje||j2.error})}
});
})();
"""

JS_REGLAS = r"""
(function(){
var G=window.__rg,R=JSON.parse(JSON.stringify(G.reglas||{})),$=function(i){return document.getElementById(i)},cierreM=G.motivos[0],fr=null,sucio=false,copiaSel={};
var LV=['lun','mar','mie','jue','vie'];
function esc(s){return String(s==null?'':s).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]})}
function chips(ops,sel,attr){return ops.map(function(o){var on=String(o.v)===String(sel);return "<button type='button' class='chip"+(on?' sel':'')+"' "+attr+"='"+esc(o.v)+"' aria-pressed='"+on+"'>"+esc(o.n)+"</button>"}).join('')}
function sel(id,val,opts,et,attrs){return "<select id='"+id+"' aria-label='"+esc(et||id)+"' "+(attrs||'')+">"+(opts||G.horas).map(function(h){var v=typeof h==='object'?h.v:h,n=typeof h==='object'?h.n:h;return "<option value='"+esc(v)+"'"+(String(v)===String(val)?' selected':'')+">"+esc(n)+"</option>"}).join('')+"</select>"}
var NDIA={};G.dias.forEach(function(d){NDIA[d.k]=d.n});
function valDia(k){var hs=R.horario_semana||{};return hs.hasOwnProperty(k)?(hs[k]===null?'cerrado':'otro'):'general'}
function igualesLV(){var hs=R.horario_semana||{},f=function(k){return JSON.stringify(hs.hasOwnProperty(k)?hs[k]:'g')},a=f('lun');return LV.every(function(k){return f(k)===a})}
var agrupado=igualesLV();
function filas(){return agrupado?[{n:'Lun – Vie',ks:LV},{n:'Sábado',ks:['sab']},{n:'Domingo',ks:['dom']}]:G.dias.map(function(d){return {n:d.n,ks:[d.k]}})}
var GEN='General · '+G.base.apertura+'–'+G.base.cierre;
function semana(){var hs=R.horario_semana||{},h='';filas().forEach(function(f){var k=f.ks[0],v=valDia(k),id=f.ks.join('_');
  h+="<div class='rg-dia'><b>"+esc(f.n)+"</b><div class='rg-dia-c'>"+sel('sm_'+id,v,[{v:'general',n:GEN},{v:'cerrado',n:'Cerrado'},{v:'otro',n:'Otro horario'}],'Horario de '+f.n,"data-sem='"+f.ks.join(',')+"'");
  if(v==='otro')h+="<div class='rg-horas'><label><span>Abre</span>"+sel('ap_'+id,hs[k].apertura,null,'Abre '+f.n)+"</label><label><span>Último turno</span>"+sel('ci_'+id,hs[k].cierre,null,'Último turno '+f.n)+"</label></div>";
  h+="</div></div>"});$('rgSemana').innerHTML=h;
  var b=$('rgPorDia');b.hidden=!agrupado&&!igualesLV();b.textContent=agrupado?'＋ Horario distinto por día':'Agrupar lunes a viernes'}
function leerSemana(){var hs=R.horario_semana||{};filas().forEach(function(f){var id=f.ks.join('_'),a=$('ap_'+id),c=$('ci_'+id);if(a&&c&&valDia(f.ks[0])==='otro')f.ks.forEach(function(k){hs[k]={apertura:a.value,cierre:c.value}})});
  var l=R.recargo_luz;if(l){var ld=$('lDesde'),lm=$('lMonto');if(ld)l.desde=ld.value;if(lm)l.monto=parseFloat(lm.value)||0}}
function fechaTxt(f){var d=new Date(f+'T12:00:00');if(isNaN(d))return f;return G.diasCortos[(d.getDay()+6)%7]+' '+d.getDate()+' '+G.meses[d.getMonth()]+(f.slice(0,4)!==G.hoy.slice(0,4)?' '+f.slice(0,4):'')}
function cierres(){var l=R.cierres||[];$('rgCierres').innerHTML=l.length?"<ul class='vcl-cierres'>"+l.map(function(c,i){return "<li><div><b>"+esc(fechaTxt(c.fecha))+"</b><small>"+esc(c.motivo||'Cerrado')+" · todo el día</small></div><button type='button' class='vcl-link rojo' data-qcierre='"+i+"' aria-label='Quitar el "+esc(fechaTxt(c.fecha))+"'>Quitar</button></li>"}).join('')+"</ul>":"<p class='vcl-nada'>Sin días cerrados.</p>";
  $('rgCierreM').innerHTML=chips(G.motivos.map(function(m){return {v:m,n:m}}),cierreM,'data-cm')}
function diasTxt(ds){if(ds.length===7)return 'Todos los días';if(ds.join()==='lun,mar,mie,jue,vie')return 'Lunes a viernes';if(ds.join()==='sab,dom')return 'Fin de semana';return ds.map(function(d){return NDIA[d].slice(0,3)}).join(', ')}
function precioTxt(f){return f.precio_turno>0?(G.moneda+' '+Number(f.precio_turno).toFixed(2)+' /turno'):(G.moneda+' '+Number(f.precio_hora).toFixed(2)+' /h')}
function franjas(){var l=R.franjas||[],cab=['Franja','Tipo','Precio',''];
  var base="<tr class='vcl-base'><td data-et='Franja'><div class='vcl-c'><b>Resto del horario</b><small>Fuera de las franjas</small></div></td><td data-et='Tipo'>Normal</td><td data-et='Precio' class='vcl-num'><b>"+esc(G.moneda+' '+Number(G.base.precio).toFixed(2)+(G.base.unidad==='hora'?' /h':' /turno'))+"</b></td><td data-et=''></td></tr>";
  $('rgFranjas').innerHTML="<div class='va-tabla-w'><table class='va-tabla vcl-franjas'><thead><tr>"+cab.map(function(c){return "<th scope='col'>"+c+"</th>"}).join('')+"</tr></thead><tbody>"+base+l.map(function(f,i){return "<tr><td data-et='Franja'><div class='vcl-c'><b>"+esc(f.desde)+" – "+esc(f.hasta)+"</b><small>"+esc(diasTxt(f.dias))+"</small></div></td><td data-et='Tipo'>"+esc(f.nombre||'Franja')+"</td><td data-et='Precio' class='vcl-num'><b>"+esc(precioTxt(f))+"</b></td><td data-et=''><button type='button' class='vcl-link rojo' data-qfranja='"+i+"' aria-label='Quitar la franja "+esc(f.nombre||'')+"'>Quitar</button></td></tr>"}).join('')+"</tbody></table></div>"
    +(l.length>1?"<p class='vcl-nota'>Si dos franjas cubren el mismo turno, manda la primera.</p>":"")}
function franjaForm(){var f=fr,h="<label>Tipo</label><div class='chips' role='group' aria-label='Tipo de franja'>"+chips(G.nombres.map(function(n){return {v:n,n:n}}),f.nombre,'data-fn')+"</div>";
  h+="<label>Días</label><div class='chips' role='group' aria-label='Atajos de días'>"+chips([{v:'lv',n:'Lunes a viernes'},{v:'fs',n:'Fin de semana'},{v:'td',n:'Todos'}],'','data-fatajo')+"</div><div class='chips' role='group' aria-label='Días de la franja'>"+
    G.dias.map(function(d){var on=f.dias.indexOf(d.k)>=0;return "<button type='button' class='chip"+(on?' sel':'')+"' data-fd='"+d.k+"' aria-pressed='"+on+"'>"+d.n.slice(0,3)+"</button>"}).join('')+"</div>";
  h+="<div class='vcl-fila2'><label><span>Desde</span>"+sel('fDesde',f.desde,null,'Desde')+"</label><label><span>Hasta</span>"+sel('fHasta',f.hasta,null,'Hasta')+"</label></div>";
  h+="<label>¿Cómo cobras en esta franja?</label><div class='chips' role='group' aria-label='Cómo cobras'>"+chips([{v:'hora',n:'Por hora'},{v:'turno',n:'Por turno'}],f.modo,'data-fmodo')+"</div>";
  h+="<label for='fPrecio'>Precio ("+esc(G.moneda)+")</label><input id='fPrecio' type='number' min='0' step='0.5' inputmode='decimal' value='"+esc(f.precio||'')+"'>";
  h+="<div class='aviso err' id='fErr' role='alert' hidden></div><div class='vcl-form-acc'><button type='button' class='btn' id='fOk'>Agregar franja</button><button type='button' class='btn sec' id='fNo'>Cancelar</button></div>";
  $('rgFranjaForm').innerHTML=h;$('rgFranjaForm').hidden=false}
function leerFranja(){if(!fr)return;var d=$('fDesde'),hh=$('fHasta'),p=$('fPrecio');if(d)fr.desde=d.value;if(hh)fr.hasta=hh.value;if(p)fr.precio=p.value}
function luz(){var l=R.recargo_luz,h="<div class='vcl-luz'><label><span>Recargo</span>"+sel('luzSel',l?'si':'no',[{v:'no',n:'Sin recargo'},{v:'si',n:'Con recargo de luz'}],'Recargo de luz')+"</label>";
  if(l)h+="<label><span>Desde</span>"+sel('lDesde',l.desde,null,'Recargo desde')+"</label><label><span>Monto por turno ("+esc(G.moneda)+")</span><input id='lMonto' type='number' min='0' step='0.5' inputmode='decimal' value='"+esc(l.monto)+"'></label>";
  $('rgLuz').innerHTML=h+"</div>"}
var POL=[['cancelacion_horas','Puede cancelar hasta',[{v:'',n:'La general ('+G.global_cancelacion+' h antes)'},{v:2,n:'2 h antes'},{v:6,n:'6 h antes'},{v:12,n:'12 h antes'},{v:24,n:'24 h antes'},{v:48,n:'48 h antes'}],' h antes'],
  ['anticipacion_max_dias','Reservar con anticipación de',[{v:'',n:'Sin límite'},{v:7,n:'hasta 7 días'},{v:14,n:'hasta 14 días'},{v:30,n:'hasta 30 días'},{v:60,n:'hasta 60 días'},{v:90,n:'hasta 90 días'},{v:180,n:'hasta 180 días'}],' días'],
  ['anticipacion_min_horas','Anticipación mínima',[{v:'',n:'Sin mínimo'},{v:1,n:'1 h antes'},{v:2,n:'2 h antes'},{v:3,n:'3 h antes'},{v:6,n:'6 h antes'},{v:12,n:'12 h antes'},{v:24,n:'1 día antes'}],' h antes'],
  ['min_turnos','Mínimo de turnos seguidos',[{v:'',n:'Sin mínimo'},{v:2,n:'2 turnos'},{v:3,n:'3 turnos'}],' turnos'],
  ['max_turnos','Máximo de turnos seguidos',[{v:'',n:'Sin máximo'},{v:1,n:'1 turno'},{v:2,n:'2 turnos'},{v:3,n:'3 turnos'},{v:4,n:'4 turnos'},{v:6,n:'6 turnos'}],' turnos'],
  ['max_reservas_dia_jugador','Reservas por jugador al día',[{v:'',n:'Sin tope'},{v:1,n:'1 reserva'},{v:2,n:'2 reservas'},{v:3,n:'3 reservas'}],' reservas']];
function politica(){$('rgPolitica').innerHTML=POL.map(function(p){var v=R[p[0]]==null?'':R[p[0]],ops=p[2].slice();
  if(v!==''&&!ops.some(function(o){return String(o.v)===String(v)}))ops.push({v:v,n:v+p[3]});
  return "<label class='vcl-pol-f'><span>"+esc(p[1])+"</span>"+sel('pol_'+p[0],v,ops,p[1],"data-num='"+p[0]+"'")+"</label>"}).join('')}
function todo(){semana();cierres();franjas();luz();politica()}
var F=$('rgForm');
F.addEventListener('change',function(ev){var t=ev.target;sucio=true;
  if(t.dataset.sem){leerSemana();R.horario_semana=R.horario_semana||{};t.dataset.sem.split(',').forEach(function(k){if(t.value==='general')delete R.horario_semana[k];else if(t.value==='cerrado')R.horario_semana[k]=null;else R.horario_semana[k]={apertura:G.base.apertura,cierre:G.base.cierre}});semana();return}
  if(t.dataset.num){if(t.value==='')delete R[t.dataset.num];else R[t.dataset.num]=Number(t.value);return}
  if(t.id==='luzSel'){leerSemana();if(t.value==='si')R.recargo_luz=R.recargo_luz||{desde:'18:00',monto:5};else delete R.recargo_luz;luz();return}
});
F.addEventListener('input',function(){sucio=true});
F.addEventListener('click',function(ev){var b=ev.target.closest('button');if(!b)return;var d=b.dataset;
  if(b.type==='submit'||b.id==='rgCopiar')return;leerSemana();leerFranja();
  if(b.id==='rgPorDia'){if(agrupado){agrupado=false}else if(igualesLV()){agrupado=true}semana();return}
  if(d.cm){cierreM=d.cm;cierres();return}
  if(b.id==='rgCierreAbrir'){$('rgCierreBox').hidden=false;b.hidden=true;$('rgCierreF').focus();return}
  if(b.id==='rgCierreNo'){$('rgCierreBox').hidden=true;$('rgCierreAbrir').hidden=false;return}
  if(b.id==='rgCierreAdd'){var f=$('rgCierreF').value;if(!f){pcgAvisar({titulo:'Falta la fecha',mensaje:'Elige el día que cierras.'});return}R.cierres=(R.cierres||[]).filter(function(c){return c.fecha!==f});R.cierres.push({fecha:f,motivo:cierreM});R.cierres.sort(function(a,b){return a.fecha<b.fecha?-1:1});sucio=true;cierres();$('rgCierreF').value='';$('rgCierreBox').hidden=true;$('rgCierreAbrir').hidden=false;return}
  if(d.qcierre!=null){R.cierres.splice(+d.qcierre,1);sucio=true;cierres();return}
  if(d.qfranja!=null){R.franjas.splice(+d.qfranja,1);sucio=true;franjas();return}
  if(b.id==='rgFranjaNueva'){fr={nombre:G.nombres[0],dias:['lun','mar','mie','jue','vie'],desde:'18:00',hasta:'23:00',modo:'hora',precio:''};franjaForm();return}
  if(d.fn){fr.nombre=d.fn;franjaForm();return}
  if(d.fatajo){fr.dias=d.fatajo==='lv'?['lun','mar','mie','jue','vie']:(d.fatajo==='fs'?['sab','dom']:G.dias.map(function(x){return x.k}));franjaForm();return}
  if(d.fd){var i=fr.dias.indexOf(d.fd);if(i>=0)fr.dias.splice(i,1);else fr.dias.push(d.fd);fr.dias=G.dias.map(function(x){return x.k}).filter(function(k){return fr.dias.indexOf(k)>=0});franjaForm();return}
  if(d.fmodo){fr.modo=d.fmodo;franjaForm();return}
  if(b.id==='fNo'){fr=null;$('rgFranjaForm').hidden=true;return}
  if(b.id==='fOk'){var p=parseFloat(fr.precio),e=$('fErr');if(!(p>0)){e.textContent='Escribe el precio de la franja.';e.hidden=false;return}if(!fr.dias.length){e.textContent='Elige al menos un día.';e.hidden=false;return}if(fr.desde===fr.hasta){e.textContent='La franja debe durar algo: cambia la hora de inicio o de fin.';e.hidden=false;return}
    R.franjas=R.franjas||[];R.franjas.push({nombre:fr.nombre,dias:fr.dias,desde:fr.desde,hasta:fr.hasta,precio_hora:fr.modo==='hora'?p:0,precio_turno:fr.modo==='turno'?p:0});fr=null;sucio=true;$('rgFranjaForm').hidden=true;franjas();return}
  if(b.id==='rgVistaBtn'){vista();return}
});
function limpio(){leerSemana();var r=JSON.parse(JSON.stringify(R));if(r.horario_semana&&!Object.keys(r.horario_semana).length)delete r.horario_semana;if(r.recargo_luz&&!(r.recargo_luz.monto>0))delete r.recargo_luz;return r}
async function post(url,body){var r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});var j={};try{j=await r.json()}catch(e){}return j}
async function vista(){var f=$('rgVistaF').value,box=$('rgVista');if(!f)return;box.innerHTML="<p class='vcl-nada'>Cargando…</p>";
  var j;try{j=await post('/anfitrion/reglas/'+encodeURIComponent(G.cancha)+'/vista',{fecha:f,reglas:limpio()})}catch(e){box.innerHTML="<p class='vcl-nada'>No pudimos cargar la vista previa. Revisa tu conexión.</p>";return}
  if(!j.ok){box.innerHTML="<p class='aviso err'>"+esc(j.mensaje||j.error||'No se pudo')+"</p>";return}
  if(j.cerrado){box.innerHTML="<div class='va-aviso warn'>"+esc(j.cerrado)+": ese día no se reserva.</div>";return}
  if(!j.turnos.length){box.innerHTML="<p class='vcl-nada'>Ese día no hay turnos.</p>";return}
  box.innerHTML="<p class='vcl-nota'>Horario "+esc(j.horario)+"</p><div class='rg-turnos'>"+j.turnos.map(function(t){return "<div class='rg-t'><b>"+esc(t.hora)+"–"+esc(t.fin)+"</b><small>"+esc(j.moneda)+" "+Number(t.precio).toFixed(2)+"</small>"+(t.franja?"<small>"+esc(t.franja)+"</small>":"")+(t.luz?"<small>Incluye luz</small>":"")+"</div>"}).join('')+"</div>"}
function botones(on){document.querySelectorAll('.rg-guardar').forEach(function(b){b.disabled=!on})}
async function guardar(paraCopiar){var er=$('rgErr');er.hidden=true;leerFranja();botones(false);pcgCargando('Guardando…');
  try{var j=await post('/anfitrion/reglas/guardar',{cancha_ids:[G.cancha],reglas:limpio()});botones(true);
    if(j.ok){R=j.reglas;sucio=false;if(!paraCopiar){pcgCargando(false);todo();pcgToast('Reglas guardadas ✓')}return true}
    pcgCargando(false);er.textContent=j.mensaje||j.error;er.hidden=false;er.scrollIntoView({behavior:'smooth',block:'center'})}
  catch(e){pcgCargando(false);botones(true);er.textContent='No se pudo guardar. Revisa tu conexión.';er.hidden=false}return false}
F.addEventListener('submit',function(ev){ev.preventDefault();guardar(false)});
document.addEventListener('click',function(ev){var b=ev.target.closest('[data-copia]');if(!b)return;var id=b.dataset.copia;copiaSel[id]=!copiaSel[id];b.classList.toggle('sel',!!copiaSel[id]);b.setAttribute('aria-pressed',copiaSel[id]?'true':'false')});
async function copiar(){copiaSel={};var mismas=G.otras.filter(function(o){return o.mismo});if(mismas.length===1)copiaSel[mismas[0].id]=true;
  var por={},orden=[];G.otras.forEach(function(o){if(!por[o.club]){por[o.club]=[];orden.push(o.club)}por[o.club].push(o)});
  var h="<p class='vcl-dlg-p'>Elige las canchas que tendrán las mismas reglas guardadas. Se reemplazan las reglas que ya tengan.</p>";
  orden.forEach(function(club){h+="<div class='vcl-dlg-g'><small>"+esc(club)+"</small><div class='chips' role='group' aria-label='"+esc(club)+"'>"+por[club].map(function(o){var on=!!copiaSel[o.id];return "<button type='button' class='chip"+(on?' sel':'')+"' data-copia='"+esc(o.id)+"' aria-pressed='"+on+"'>"+esc(o.nombre)+(o.otra_moneda?" · cobra en "+esc(o.moneda):"")+"</button>"}).join('')+"</div></div>"});
  if(G.otras.some(function(o){return o.otra_moneda})&&((R.franjas||[]).length||R.recargo_luz))h+="<p class='vcl-dlg-p vcl-nota'>A una cancha que cobra en otra moneda no se le copian las franjas con precio ni el recargo de luz: conserva los suyos.</p>";
  if(sucio)h+="<p class='vcl-dlg-p vcl-nota'>Antes guardamos los cambios que tienes en pantalla.</p>";
  if(!await pcgConfirmar({titulo:'Copiar reglas a otras canchas',html:h,confirmar:'Copiar reglas',icono:'📋'}))return;
  var ids=Object.keys(copiaSel).filter(function(k){return copiaSel[k]});
  if(!ids.length){pcgAvisar({titulo:'Elige una cancha',mensaje:'Marca al menos una cancha para copiar las reglas.'});return}
  if(sucio&&!await guardar(true))return;
  pcgCargando('Copiando reglas…');var j;try{j=await post('/anfitrion/reglas/'+encodeURIComponent(G.cancha)+'/copiar',{destinos:ids})}catch(e){pcgCargando(false);pcgAvisar({titulo:'No se pudo copiar',mensaje:'Revisa tu conexión.'});return}
  if(!j.ok){pcgCargando(false);pcgAvisar({titulo:'No se pudo copiar',mensaje:j.mensaje||j.error});return}
  var msg='Reglas copiadas a '+j.copiadas+' cancha'+(j.copiadas===1?'':'s')+' ✓';
  if(j.sin_precios&&j.sin_precios.length){pcgCargando(false);await pcgAvisar({titulo:'Reglas copiadas',icono:'📋',mensaje:'Se copiaron a '+j.copiadas+' cancha'+(j.copiadas===1?'':'s')+'. A '+j.sin_precios.map(function(x){return x.nombre+' (cobra en '+x.moneda+')'}).join(', ')+' no le copiamos las franjas con precio ni el recargo de luz: ajústalos en sus reglas.'})}
  pcgRecargar(msg)}
var bc=$('rgCopiar');if(bc)bc.addEventListener('click',copiar);
todo();vista();
})();
"""
