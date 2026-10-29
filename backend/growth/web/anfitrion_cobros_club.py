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
from urllib.parse import urlparse

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from starlette.concurrency import run_in_threadpool

import config
from config import MARCA
from pagos import cobro_directo as cd
from reservas import reglas as _reglas
from web import almacen, datos, horarios, sesion, ui
from web import cobro_directo_web as cdw
from web.anfitrion import _cabecera, _motivo_cierre, _sesion_o_entrar
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
    html = f"<a class='anf-back' href='{e(volver)}'>‹ {e(volver_txt)}</a>{cuerpo}<style>{CSS}</style>"
    return ui.shell(titulo, html, nav=_cabecera("", ses), sesion=ses, ancho=True, titulo_tab=f"{titulo} · Modo anfitrión · {MARCA}")


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


@router.get("/anfitrion/cobros-club", response_class=HTMLResponse)
def pagina_cobros_club(request: Request) -> HTMLResponse:
    ses, resp = _sesion_o_entrar(request, "/anfitrion/cobros-club")
    if resp is not None:
        return resp
    email = ses["email"]
    if not datos.canchas_de_dueno(email):
        cuerpo = ("<h1 class='anf-hola'>Cobros de tu club</h1><div class='anf-vacio' style='margin-top:16px'>"
                  "Primero registra tu cancha: aquí conectarás tu Culqi y tus medios de pago.</div>"
                  "<p style='margin-top:14px'><a class='btn' href='/anfitrion/nueva'>Registrar mi cancha</a></p>")
        return _pagina("Cobros de tu club", cuerpo, ses)
    est = cdw.estado_club(email, _base_webhook(request))
    iso, pais = est["moneda"], est["pais"]
    pend = int(est.get("pendientes") or 0)
    if not est["disponible"]:
        bloque = "<div class='aviso warn' style='margin-top:16px'>El cobro directo aún no está disponible en este ambiente.</div>"
    else:
        bloque = (
            (f"<a class='cc-pend' href='/anfitrion/pagos-por-confirmar'><span aria-hidden='true'>🧾</span><span><b>Pagos por confirmar</b>"
             f"<small>{pend} por revisar</small></span><span class='cl-insignia'>{pend}</span><span class='chev' aria-hidden='true'>›</span></a>"
             if pend else "")
            + _bloque_culqi(est)
            + "<section class='panel' aria-labelledby='tMedios'><h2 id='tMedios'>Pagos manuales</h2>"
              "<p class='sub'>El jugador te paga y sube su comprobante; tú lo confirmas en Pagos por confirmar.</p>"
              "<div id='ccMedios'></div>"
              "<div class='acciones' style='margin-top:12px'><button type='button' class='btn sec' id='ccAgregar'>＋ Agregar medio de pago</button></div>"
              "<form id='ccMedioForm' hidden novalidate style='margin-top:14px'></form></section>")
    cfg = {"pais": pais, "moneda": iso, "permitidos": est["medios_permitidos"], "medios": est["medios"],
           "bancos": _bancos_de(pais), "billeteras": _billeteras_de(pais), "qr": almacen.disponible(),
           "etiquetas": cd.ETIQUETA_MEDIO, "errores": ERRORES}
    cuerpo = ("<h1 class='anf-hola'>Cobros de tu club</h1>"
              f"<p class='sub'>El pago de cada reserva llega directo a tu cuenta. {e(MARCA)} cobra solo su comisión por reserva.</p>"
              + bloque + tarjeta_comision(est, email, iso)
              + "<section class='panel' aria-labelledby='tReglas'><h2 id='tReglas'>Reglas de reserva</h2>"
                "<p class='sub'>Horarios por día, precios por franja y tu política de cancelación.</p>"
                "<a class='btn sec' href='/anfitrion/reglas'>Configurar reglas</a></section>"
              + f"<script>window.__club={_js(cfg)};</script><script>{JS_CLUB}</script>")
    return _pagina("Cobros de tu club", cuerpo, ses)


def _bloque_culqi(est: dict) -> str:
    cq = est.get("culqi") or {}
    if cq.get("no_aplica"):
        return ("<section class='panel' aria-labelledby='tCulqi'><h2 id='tCulqi'>Pagos con tarjeta</h2>"
                "<p class='sub'>En tu país los jugadores te pagan con QR, transferencia o billetera: agrégalos abajo y "
                "confirma cada comprobante.</p></section>")
    if cq.get("configurada"):
        modo = "Producción" if cq.get("modo") == "live" else "Pruebas"
        return ("<section class='panel' aria-labelledby='tCulqi'><h2 id='tCulqi'>Tarjeta y Yape con tu Culqi</h2>"
                f"<div class='cc-ok'><span aria-hidden='true'>✅</span><div><b>Culqi conectado</b>"
                f"<small><span class='pill {'ok' if modo == 'Producción' else 'warn'}'>{modo}</span></small></div></div>"
                "<dl class='cc-dl'>"
                f"<dt>Llave pública</dt><dd><code>{e(cq.get('public_key'))}</code></dd>"
                f"<dt>Llave secreta</dt><dd><code>{e(cq.get('secret_key'))}</code></dd></dl>"
                + ("" if cq.get("verificada") else "<p class='aviso warn'>No pudimos comprobar la llave con Culqi; se reintentará al cobrar.</p>")
                + "<label for='ccWebhook'>Webhook (pégalo en tu panel de Culqi → Eventos)</label>"
                f"<div class='cc-copiar'><input id='ccWebhook' readonly value='{e(cq.get('webhook_url'))}'>"
                "<button type='button' class='btn sec' data-copiar='ccWebhook'>Copiar</button></div>"
                "<div class='acciones' style='margin-top:14px'><button type='button' class='btn sec cc-rojo' id='ccDesconectar'>Desconectar Culqi</button></div>"
                "</section>")
    sin_cifrado = not est.get("cifrado")
    return ("<section class='panel' aria-labelledby='tCulqi'><h2 id='tCulqi'>Tarjeta y Yape con tu Culqi</h2>"
            "<p class='sub'>Cobra en línea con tu propia cuenta Culqi: la plata cae en tu cuenta. Encuentra tus llaves en "
            "tu panel de Culqi → Desarrollo → API Keys.</p>"
            + ("<div class='aviso warn'>" + e(ERRORES["cifrado_no_configurado"]) + "</div>" if sin_cifrado else "")
            + "<form id='ccCulqi' novalidate>"
            "<label for='ccPk'>Llave pública</label><input id='ccPk' autocomplete='off' spellcheck='false' maxlength='120' placeholder='pk_live_…'>"
            "<label for='ccSk'>Llave secreta</label><input id='ccSk' type='password' autocomplete='off' spellcheck='false' maxlength='120' placeholder='sk_live_…'>"
            "<p class='sub' style='font-size:13px'>La llave secreta se guarda cifrada y nunca se vuelve a mostrar.</p>"
            "<div class='aviso err' id='ccCulqiErr' role='alert' hidden></div>"
            f"<div class='acciones'><button type='submit' class='btn' id='ccConectar'{' disabled' if sin_cifrado else ''}>Conectar Culqi</button></div>"
            "</form></section>")


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

def _turno_txt(p: dict) -> tuple[str, str]:
    filas = datos.reservas_de(list(p.get("reserva_ids") or []))
    if not filas:
        return "", ""
    f0, f1 = filas[0], filas[-1]
    return (horarios.fecha_larga(str(f0.get("fecha") or "")),
            f"{f0.get('hora_inicio')}–{f1.get('hora_fin')}" + (f" · {len(filas)} turnos" if len(filas) > 1 else ""))


def _tarjeta_voucher(p: dict, canchas: dict, historial: bool) -> str:
    c = canchas.get(p.get("cancha_id")) or {}
    lugar = (c.get("club") or "").strip()
    nombre_c = c.get("nombre") or "Cancha"
    dia, rango = _turno_txt(p)
    pid = str(p["id"])
    monto = _plata(int(p.get("monto_centimos") or 0), str(p.get("moneda") or "PEN"))
    medio = cd.ETIQUETA_MEDIO.get(str(p.get("medio") or ""), str(p.get("medio") or ""))
    jugador = (p.get("jugador_nombre") or "").strip() or p.get("jugador_email") or "Jugador"
    estado = str(p.get("estado") or "")
    if historial:
        pill = {"aprobado": "<span class='pill ok'>Aprobado</span>", "rechazado": "<span class='pill bad'>Rechazado</span>",
                "vencido": "<span class='pill gris'>Venció sin revisar</span>"}.get(estado, f"<span class='pill gris'>{e(estado)}</span>")
        motivo = str(p.get("motivo_rechazo") or "")
        motivo = "" if motivo in ("sin_revision", "apartado_perdido") else cdw.MOTIVOS_RECHAZO.get(motivo, motivo)
        acciones = f"<div class='acc'>{pill}" + (f"<small class='sub'>Motivo: {e(motivo)}</small>" if motivo else "") + "</div>"
    else:
        acciones = (f"<div class='acc'><span class='vv-vence' data-vence='{e(p.get('vence_en'))}'>Vence pronto</span>"
                    f"<button type='button' class='btn' data-aprobar='{e(pid)}' data-monto='{e(monto)}'>✅ Aprobar</button>"
                    f"<button type='button' class='btn sec cc-rojo' data-rechazar='{e(pid)}'>Rechazar</button></div>")
    return (f"<article class='vv' data-pid='{e(pid)}' aria-label='Pago de {e(jugador)}'>"
            f"<button type='button' class='vv-img' data-zoom='{e(pid)}' aria-label='Ver el comprobante en grande'>"
            f"<img src='/anfitrion/pagos-por-confirmar/{e(pid)}/imagen' alt='Comprobante de {e(jugador)}' loading='lazy'></button>"
            f"<div class='vv-cuerpo'><div class='vv-monto'>{e(monto)}</div>"
            f"<div class='sub' style='margin:0'><b>{e(medio)}</b> · N.º de operación <b>{e(p.get('operacion') or '—')}</b></div>"
            f"<div style='margin-top:6px'><b>{e(jugador)}</b><small class='sub' style='display:block;margin:0'>{e(p.get('jugador_email') or '')}</small></div>"
            f"<div class='sub' style='margin:6px 0 0'>{e(nombre_c)}{(' · ' + e(lugar)) if lugar and lugar != nombre_c else ''}"
            f"{(' · ' + e(dia) + ' ' + e(rango)) if dia else ''}</div>{acciones}</div></article>")


@router.get("/anfitrion/pagos-por-confirmar", response_class=HTMLResponse)
def pagina_pagos_por_confirmar(request: Request, estado: str = "") -> HTMLResponse:
    ses, resp = _sesion_o_entrar(request, "/anfitrion/pagos-por-confirmar")
    if resp is not None:
        return resp
    email = ses["email"]
    historial = estado == "historial"
    canchas = {c["id"]: c for c in datos.canchas_de_dueno(email)}
    pagos = cdw.bandeja_de(email, "historial" if historial else "en_revision") if cd.disponible() else []
    pend = len(pagos) if not historial else cdw.pendientes_de(email)
    tabs = ("<div class='anf-tabs' role='tablist'>"
            f"<a class='chip{'' if historial else ' sel'}' role='tab' aria-selected='{'false' if historial else 'true'}' href='/anfitrion/pagos-por-confirmar'>Por revisar <small>({pend})</small></a>"
            f"<a class='chip{' sel' if historial else ''}' role='tab' aria-selected='{'true' if historial else 'false'}' href='/anfitrion/pagos-por-confirmar?estado=historial'>Resueltos</a></div>")
    if pagos:
        lista = "<div class='vv-lista'>" + "".join(_tarjeta_voucher(p, canchas, historial) for p in pagos) + "</div>"
    elif not cd.disponible():
        lista = "<div class='anf-vacio'>El cobro directo aún no está disponible en este ambiente.</div>"
    else:
        lista = ("<div class='anf-vacio'>" + ("Aún no resolviste pagos." if historial else
                 "No tienes vouchers pendientes. Cuando un jugador te pague por Yape, Plin o transferencia, su comprobante aparece aquí.")
                 + "</div>")
    cfg = {"motivos": [{"k": k, "n": n} for k, n in MOTIVOS_RECHAZO]}
    cuerpo = ("<h1 class='anf-hola'>Pagos por confirmar</h1>"
              "<p class='sub'>Compara cada comprobante con el movimiento en tu Yape, Plin o banco. Si no lo revisas a tiempo, "
              "la reserva se libera sola.</p>" + tabs + lista
              + f"<script>window.__vv={_js(cfg)};</script><script>{JS_VOUCHERS}</script>")
    return _pagina("Pagos por confirmar", cuerpo, ses, "/anfitrion/cobros-club", "Cobros de tu club")


@router.get("/anfitrion/pagos-por-confirmar/{pid}/imagen")
def imagen_voucher(request: Request, pid: str) -> Response:
    ses = sesion.de_request(request)
    if not ses:
        return Response(status_code=401)
    if cdw.pago_del_dueno(pid, ses["email"]) is None:
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
    p = cdw.pago_del_dueno(pid, email)
    if p is None:
        return _err("no_encontrado", 404)
    r = cdw.aprobar_voucher(p, email)
    if not r.get("ok"):
        return _err(r.get("error") or "error", 409)
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
    p = cdw.pago_del_dueno(pid, email)
    if p is None:
        return _err("no_encontrado", 404)
    r = cdw.rechazar_voucher(p, email, motivo)
    if not r.get("ok"):
        return _err(r.get("error") or "error", 409)
    print(f"[vouchers-web] {email} rechazó {pid} ({motivo})", flush=True)
    return JSONResponse({"ok": True})


# ── Reglas de reserva (reglas_reserva_screen.dart) ───────────────────────────

def _cancha_propia(email: str, cancha_id: str) -> tuple[dict | None, list[dict]]:
    canchas = datos.canchas_de_dueno(email)
    return next((c for c in canchas if c["id"] == cancha_id), None), canchas


@router.get("/anfitrion/reglas", response_class=HTMLResponse)
def pagina_reglas_elegir(request: Request):
    ses, resp = _sesion_o_entrar(request, "/anfitrion/reglas")
    if resp is not None:
        return resp
    canchas = datos.canchas_de_dueno(ses["email"])
    if len(canchas) == 1:
        return RedirectResponse(f"/anfitrion/reglas/{canchas[0]['id']}", status_code=303)
    if not canchas:
        cuerpo = ("<h1 class='anf-hola'>Reglas de reserva</h1><div class='anf-vacio'>Registra tu cancha para configurar sus reglas.</div>"
                  "<p style='margin-top:14px'><a class='btn' href='/anfitrion/nueva'>Registrar mi cancha</a></p>")
        return _pagina("Reglas de reserva", cuerpo, ses)
    filas = "".join(
        f"<a class='anf-item' href='/anfitrion/reglas/{e(c['id'])}'><span class='txt'><b>{e(c['nombre'])}</b>"
        f"<small>{e(c.get('club') or '')}{' · con reglas' if _reglas.de_cancha(c) else ' · horario general'}</small></span>"
        "<span class='chev' aria-hidden='true'>›</span></a>" for c in canchas)
    cuerpo = ("<h1 class='anf-hola'>Reglas de reserva</h1><p class='sub'>Elige la cancha. Luego puedes aplicar las mismas reglas "
              f"a las demás canchas de tu local.</p><div class='anf-menu' style='margin-left:0'>{filas}</div>")
    return _pagina("Reglas de reserva", cuerpo, ses)


def _opciones_hora() -> list[str]:
    return [f"{h:02d}:{m:02d}" for h in range(24) for m in (0, 30)]


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
    sim, _iso = _moneda_de(c)
    club = (c.get("club") or "").strip().lower()
    otras = [x for x in canchas if x["id"] != c["id"]]
    otras.sort(key=lambda x: ((x.get("club") or "").strip().lower() != club, x.get("nombre") or ""))
    hoy = horarios.ahora_local(_pais_de_c(c)).date()
    cfg = {"cancha": c["id"], "moneda": sim, "reglas": _reglas.de_cancha(c),
           "base": {"apertura": c.get("hora_apertura") or "07:00", "cierre": c.get("hora_cierre") or "23:00",
                    "paso": int(c.get("duracion_slot_min") or 60)},
           "horas": _opciones_hora(), "motivos": MOTIVOS_CIERRE, "nombres": NOMBRES_FRANJA,
           "dias": [{"k": k, "n": n} for k, n in zip(_reglas.DIAS_SEMANA, ("Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"))],
           "global_cancelacion": float(devoluciones.horas_minimas({k: v for k, v in c.items() if k != "reglas_reserva"})),
           "hoy": hoy.isoformat(), "disponible": datos.col_reglas_disponible()}
    hermanas = "".join(
        f"<label class='chk rg-her'><input type='checkbox' value='{e(x['id'])}'{' checked' if (x.get('club') or '').strip().lower() == club and club else ''}>"
        f" {e(x['nombre'])}<small> · {e(x.get('club') or 'otro local')}</small></label>" for x in otras)
    cuerpo = (
        f"<h1 class='anf-hola'>Reglas de {e(c['nombre'])}</h1>"
        f"<p class='sub'>Horario general {e(cfg['base']['apertura'])}–{e(cfg['base']['cierre'])} · turnos de {cfg['base']['paso']} min. "
        "Lo que no configures aquí sigue igual que siempre.</p>"
        + ("" if cfg["disponible"] else "<div class='aviso warn'>Las reglas de reserva aún no están activas en este ambiente: puedes verlas pero no guardarlas.</div>")
        + "<form id='rgForm' novalidate>"
          "<section class='panel'><h2>Horario por día</h2><p class='sub'>El cierre es la hora en que empieza el último turno.</p><div id='rgSemana'></div></section>"
          "<section class='panel'><h2>Días cerrados</h2><p class='sub'>Feriados, mantenimiento o eventos: ese día no se reserva.</p>"
          "<div id='rgCierres'></div><div class='rg-fila'><div><label for='rgCierreF'>Fecha</label>"
          f"<input type='date' id='rgCierreF' min='{hoy.isoformat()}'></div></div>"
          "<label>Motivo</label><div class='chips' id='rgCierreM' role='group' aria-label='Motivo del cierre'></div>"
          "<div class='acciones'><button type='button' class='btn sec' id='rgCierreAdd'>＋ Agregar día cerrado</button></div></section>"
          "<section class='panel'><h2>Precios por franja</h2><p class='sub'>Un precio distinto en ciertos días y horas (manda sobre la hora feliz). "
          "Si dos franjas cubren el mismo turno, manda la primera.</p><div id='rgFranjas'></div>"
          "<div class='acciones'><button type='button' class='btn sec' id='rgFranjaNueva'>＋ Agregar franja</button></div>"
          "<div id='rgFranjaForm' hidden></div></section>"
          "<section class='panel'><h2>Recargo de luz</h2><p class='sub'>Un monto fijo por turno desde que se prenden las luces.</p><div id='rgLuz'></div></section>"
          "<section class='panel'><h2>Ventana de reserva</h2><label>Anticipación mínima</label><div class='chips' id='rgAntMin' role='group'></div>"
          "<label>Hasta cuántos días antes se puede reservar</label><div class='chips' id='rgAntMax' role='group'></div></section>"
          "<section class='panel'><h2>Turnos por reserva</h2><label>Mínimo de turnos seguidos</label><div class='chips' id='rgMin' role='group'></div>"
          "<label>Máximo de turnos seguidos</label><div class='chips' id='rgMax' role='group'></div>"
          "<label>Reservas por jugador al día</label><div class='chips' id='rgTope' role='group'></div></section>"
          "<section class='panel'><h2>Cancelación</h2><p class='sub'>Hasta cuántas horas antes el jugador cancela con devolución.</p>"
          "<div class='chips' id='rgCanc' role='group'></div></section>"
          "<section class='panel'><h2>Vista previa</h2><p class='sub'>Así verá el jugador ese día (con lo que tienes en pantalla, aunque no lo hayas guardado).</p>"
          f"<div class='rg-fila'><div><label for='rgVistaF'>Día</label><input type='date' id='rgVistaF' value='{hoy.isoformat()}' min='{hoy.isoformat()}'></div>"
          "<div style='align-self:end'><button type='button' class='btn sec' id='rgVistaBtn'>Ver ese día</button></div></div>"
          "<div id='rgVista' aria-live='polite' style='margin-top:12px'></div></section>"
        + (f"<section class='panel'><h2>Aplicar también a</h2><p class='sub'>Las mismas reglas en otras canchas tuyas (se reemplazan las que tengan).</p>{hermanas}</section>" if otras else "")
        + "<div class='aviso err' id='rgErr' role='alert' hidden></div>"
          f"<div class='rg-barra'><a class='btn sec' href='/anfitrion/calendario?cancha={e(c['id'])}'>Ver calendario</a>"
          f"<button type='submit' class='btn' id='rgGuardar'{'' if cfg['disponible'] else ' disabled'}>Guardar reglas</button></div></form>"
        + f"<script>window.__rg={_js(cfg)};</script><script>{JS_REGLAS}</script>")
    return _pagina(f"Reglas de {c['nombre']}", cuerpo, ses, "/anfitrion/canchas", "Mis canchas")


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
function pintar(){var el=$('ccMedios');if(!el)return;
  if(!medios.length){el.innerHTML="<div class='anf-vacio'>Aún no agregas medios manuales."+(C.pais==='PE'?' Agrega tu Yape, Plin o cuenta bancaria.':' Agrega tu QR, transferencia o billetera.')+"</div>";return}
  el.innerHTML=medios.map(function(m,i){return "<div class='cc-medio'>"+(m.qr_url?"<img src='"+esc(m.qr_url)+"' alt='QR de "+esc(m.titular)+"'>":"")+"<div><b>"+esc(C.etiquetas[m.tipo]||m.tipo)+"</b><small>"+esc(m.titular)+"</small><small>"+esc(detalle(m))+"</small></div>"
    +"<button type='button' class='btn sec' data-editar='"+i+"'>Editar</button><button type='button' class='btn sec cc-rojo' data-quitar='"+i+"'>Quitar</button></div>"}).join('')}
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
  h+="<div class='aviso err' id='mErr' role='alert' hidden></div><div class='acciones'><button type='submit' class='btn'>Guardar medio</button><button type='button' class='btn sec' id='mCancelar'>Cancelar</button></div>";
  f.innerHTML=h;f.hidden=false;var q=$('mQr');if(q)q.addEventListener('change',subirQr)}
function leer(){['titular:mTit','numero:mNum','cuenta:mCta','cci:mCci'].forEach(function(p){var a=p.split(':'),i=$(a[1]);if(i)st[a[0]]=i.value})}
async function subirQr(){var i=$('mQr'),f=i.files&&i.files[0];if(!f)return;leer();pcgCargando('Subiendo el QR…');
  try{var r=await fetch('/anfitrion/cobros-club/qr',{method:'POST',headers:{'Content-Type':f.type||'image/jpeg'},body:f});var j=await r.json();pcgCargando(false);
    if(j.ok){st.qr_url=j.url;form();pcgToast('QR cargado ✓')}else pcgAvisar({titulo:'No se pudo subir',mensaje:j.mensaje||j.error})}catch(e){pcgCargando(false);pcgAvisar({titulo:'No se pudo subir',mensaje:'Revisa tu conexión.'})}}
async function guardar(lista,txt){pcgCargando(txt||'Guardando…');try{var j=await post('/anfitrion/cobros-club/medios',{medios:lista});pcgCargando(false);
  if(j.ok){medios=j.medios||lista;pintar();$('ccMedioForm').hidden=true;pcgToast('Guardado ✓');return true}
  var er=$('mErr');if(er&&!$('ccMedioForm').hidden){er.textContent=msg(j);er.hidden=false}else pcgAvisar({titulo:'No se pudo',mensaje:msg(j)})}catch(e){pcgCargando(false);pcgAvisar({titulo:'No se pudo',mensaje:'Revisa tu conexión.'})}return false}
var ag=$('ccAgregar');if(ag)ag.addEventListener('click',function(){edit=-1;st={tipo:C.permitidos[0]};form()});
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
  el.classList.toggle('tarde',m<=10);el.textContent=m>0?('Vence en '+(m>=60?(Math.floor(m/60)+' h '+(m%60)+' min'):(m+' min'))+' · si no lo revisas, la reserva se libera'):'Venció: la reserva se liberará'})}
vence();setInterval(vence,30000);
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
var G=window.__rg,R=JSON.parse(JSON.stringify(G.reglas||{})),$=function(i){return document.getElementById(i)},cierreM=G.motivos[0],fr=null;
function esc(s){return String(s==null?'':s).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]})}
function chips(ops,sel,attr){return ops.map(function(o){var on=String(o.v)===String(sel);return "<button type='button' class='chip"+(on?' sel':'')+"' "+attr+"='"+esc(o.v)+"' aria-pressed='"+on+"'>"+esc(o.n)+"</button>"}).join('')}
function sel(id,val,opts){return "<select id='"+id+"' aria-label='"+id+"'>"+(opts||G.horas).map(function(h){return "<option"+(h===val?' selected':'')+">"+h+"</option>"}).join('')+"</select>"}
var NDIA={};G.dias.forEach(function(d){NDIA[d.k]=d.n});
function semana(){var hs=R.horario_semana||{},h='';G.dias.forEach(function(d){var v=hs.hasOwnProperty(d.k)?(hs[d.k]===null?'cerrado':'otro'):'general';
  h+="<div class='rg-dia'><b>"+d.n+"</b><div class='chips' role='group' aria-label='"+d.n+"'>"+chips([{v:'general',n:'Horario general'},{v:'cerrado',n:'Cerrado'},{v:'otro',n:'Otro horario'}],v,"data-sem='"+d.k+"' data-v")+"</div>";
  if(v==='otro')h+="<div class='rg-horas'><label class='vh' for='ap_"+d.k+"'>Abre</label>"+sel('ap_'+d.k,hs[d.k].apertura)+"<span style='align-self:center'>a</span><label class='vh' for='ci_"+d.k+"'>Último turno</label>"+sel('ci_'+d.k,hs[d.k].cierre)+"</div>";
  h+="</div>"});$('rgSemana').innerHTML=h}
function cierres(){var l=R.cierres||[];$('rgCierres').innerHTML=l.length?l.map(function(c,i){return "<div class='rg-item'><div><b>"+esc(c.fecha)+"</b><small>"+esc(c.motivo||'Cerrado')+"</small></div><button type='button' class='btn sec' data-qcierre='"+i+"'>Quitar</button></div>"}).join(''):"<p class='sub'>Sin días cerrados.</p>";
  $('rgCierreM').innerHTML=chips(G.motivos.map(function(m){return {v:m,n:m}}),cierreM,'data-cm')}
function diasTxt(ds){if(ds.length===7)return 'Todos los días';if(ds.join()==='lun,mar,mie,jue,vie')return 'Lunes a viernes';if(ds.join()==='sab,dom')return 'Fin de semana';return ds.map(function(d){return NDIA[d].slice(0,3)}).join(', ')}
function precioTxt(f){return f.precio_turno>0?(G.moneda+' '+Number(f.precio_turno).toFixed(2)+' por turno'):(G.moneda+' '+Number(f.precio_hora).toFixed(2)+' por hora')}
function franjas(){var l=R.franjas||[];$('rgFranjas').innerHTML=l.length?l.map(function(f,i){return "<div class='rg-item'><div><b>"+esc(f.nombre||'Franja')+" · "+esc(precioTxt(f))+"</b><small>"+esc(diasTxt(f.dias))+" · "+esc(f.desde)+"–"+esc(f.hasta)+"</small></div><button type='button' class='btn sec' data-qfranja='"+i+"'>Quitar</button></div>"}).join(''):"<p class='sub'>Sin franjas: se cobra el precio general (con su hora feliz).</p>"}
function franjaForm(){var f=fr,h="<div class='panel' style='margin-top:12px;background:var(--gris)'><label>Nombre</label><div class='chips' role='group'>"+chips(G.nombres.map(function(n){return {v:n,n:n}}),f.nombre,'data-fn')+"</div>";
  h+="<label>Días</label><div class='chips' role='group'>"+chips([{v:'lv',n:'Lunes a viernes'},{v:'fs',n:'Fin de semana'},{v:'td',n:'Todos'}],'','data-fatajo')+"</div><div class='chips' role='group' aria-label='Días de la franja'>"+
    G.dias.map(function(d){var on=f.dias.indexOf(d.k)>=0;return "<button type='button' class='chip"+(on?' sel':'')+"' data-fd='"+d.k+"' aria-pressed='"+on+"'>"+d.n.slice(0,3)+"</button>"}).join('')+"</div>";
  h+="<div class='rg-fila'><div><label for='fDesde'>Desde</label>"+sel('fDesde',f.desde)+"</div><div><label for='fHasta'>Hasta</label>"+sel('fHasta',f.hasta)+"</div></div>";
  h+="<label>¿Cómo cobras en esta franja?</label><div class='chips' role='group'>"+chips([{v:'hora',n:'Por hora'},{v:'turno',n:'Por turno'}],f.modo,'data-fmodo')+"</div>";
  h+="<label for='fPrecio'>Precio ("+esc(G.moneda)+")</label><input id='fPrecio' type='number' min='0' step='0.5' inputmode='decimal' value='"+esc(f.precio||'')+"'>";
  h+="<div class='aviso err' id='fErr' role='alert' hidden></div><div class='acciones'><button type='button' class='btn' id='fOk'>Agregar franja</button><button type='button' class='btn sec' id='fNo'>Cancelar</button></div></div>";
  $('rgFranjaForm').innerHTML=h;$('rgFranjaForm').hidden=false}
function leerFranja(){if(!fr)return;var d=$('fDesde'),hh=$('fHasta'),p=$('fPrecio');if(d)fr.desde=d.value;if(hh)fr.hasta=hh.value;if(p)fr.precio=p.value}
function luz(){var l=R.recargo_luz,h="<div class='chips' role='group'>"+chips([{v:'no',n:'Sin recargo'},{v:'si',n:'Con recargo de luz'}],l?'si':'no','data-luz')+"</div>";
  if(l)h+="<div class='rg-fila'><div><label for='lDesde'>Desde</label>"+sel('lDesde',l.desde)+"</div><div><label for='lMonto'>Monto por turno ("+esc(G.moneda)+")</label><input id='lMonto' type='number' min='0' step='0.5' inputmode='decimal' value='"+esc(l.monto)+"'></div></div>";
  $('rgLuz').innerHTML=h}
function chipsNum(id,clave,ops){$(id).innerHTML=chips(ops,R[clave]==null?'':R[clave],"data-num='"+clave+"' data-v")}
function nums(){chipsNum('rgAntMin','anticipacion_min_horas',[{v:'',n:'Sin mínimo'},{v:1,n:'1 h antes'},{v:2,n:'2 h'},{v:3,n:'3 h'},{v:6,n:'6 h'},{v:12,n:'12 h'},{v:24,n:'1 día'}]);
  chipsNum('rgAntMax','anticipacion_max_dias',[{v:'',n:'Sin límite'},{v:7,n:'7 días'},{v:14,n:'14 días'},{v:30,n:'30 días'},{v:60,n:'60 días'},{v:90,n:'90 días'},{v:180,n:'180 días'}]);
  chipsNum('rgMin','min_turnos',[{v:'',n:'Sin mínimo'},{v:2,n:'2 turnos'},{v:3,n:'3 turnos'}]);
  chipsNum('rgMax','max_turnos',[{v:'',n:'Sin máximo'},{v:1,n:'1 turno'},{v:2,n:'2'},{v:3,n:'3'},{v:4,n:'4'},{v:6,n:'6'}]);
  chipsNum('rgTope','max_reservas_dia_jugador',[{v:'',n:'Sin tope'},{v:1,n:'1 reserva'},{v:2,n:'2'},{v:3,n:'3'}]);
  chipsNum('rgCanc','cancelacion_horas',[{v:'',n:'La general ('+G.global_cancelacion+' h)'},{v:2,n:'2 h'},{v:6,n:'6 h'},{v:12,n:'12 h'},{v:24,n:'24 h'},{v:48,n:'48 h'}])}
function leerSemana(){var hs=R.horario_semana||{};G.dias.forEach(function(d){var a=$('ap_'+d.k),c=$('ci_'+d.k);if(a&&c&&hs[d.k])hs[d.k]={apertura:a.value,cierre:c.value}});
  var l=R.recargo_luz;if(l){var ld=$('lDesde'),lm=$('lMonto');if(ld)l.desde=ld.value;if(lm)l.monto=parseFloat(lm.value)||0}}
function todo(){semana();cierres();franjas();luz();nums()}
$('rgForm').addEventListener('click',function(ev){var b=ev.target.closest('button');if(!b)return;leerSemana();leerFranja();var d=b.dataset;
  if(d.sem){R.horario_semana=R.horario_semana||{};if(d.v==='general')delete R.horario_semana[d.sem];else if(d.v==='cerrado')R.horario_semana[d.sem]=null;else R.horario_semana[d.sem]={apertura:G.base.apertura,cierre:G.base.cierre};semana();return}
  if(d.cm){cierreM=d.cm;cierres();return}
  if(b.id==='rgCierreAdd'){var f=$('rgCierreF').value;if(!f){pcgAvisar({titulo:'Falta la fecha',mensaje:'Elige el día que cierras.'});return}R.cierres=(R.cierres||[]).filter(function(c){return c.fecha!==f});R.cierres.push({fecha:f,motivo:cierreM});R.cierres.sort(function(a,b){return a.fecha<b.fecha?-1:1});cierres();return}
  if(d.qcierre!=null){R.cierres.splice(+d.qcierre,1);cierres();return}
  if(d.qfranja!=null){R.franjas.splice(+d.qfranja,1);franjas();return}
  if(b.id==='rgFranjaNueva'){fr={nombre:G.nombres[0],dias:['lun','mar','mie','jue','vie'],desde:'18:00',hasta:'23:00',modo:'hora',precio:''};franjaForm();return}
  if(d.fn){fr.nombre=d.fn;franjaForm();return}
  if(d.fatajo){fr.dias=d.fatajo==='lv'?['lun','mar','mie','jue','vie']:(d.fatajo==='fs'?['sab','dom']:G.dias.map(function(x){return x.k}));franjaForm();return}
  if(d.fd){var i=fr.dias.indexOf(d.fd);if(i>=0)fr.dias.splice(i,1);else fr.dias.push(d.fd);fr.dias=G.dias.map(function(x){return x.k}).filter(function(k){return fr.dias.indexOf(k)>=0});franjaForm();return}
  if(d.fmodo){fr.modo=d.fmodo;franjaForm();return}
  if(b.id==='fNo'){fr=null;$('rgFranjaForm').hidden=true;return}
  if(b.id==='fOk'){var p=parseFloat(fr.precio),e=$('fErr');if(!(p>0)){e.textContent='Escribe el precio de la franja.';e.hidden=false;return}if(!fr.dias.length){e.textContent='Elige al menos un día.';e.hidden=false;return}if(fr.desde===fr.hasta){e.textContent='La franja debe durar algo: cambia la hora de inicio o de fin.';e.hidden=false;return}
    R.franjas=R.franjas||[];R.franjas.push({nombre:fr.nombre,dias:fr.dias,desde:fr.desde,hasta:fr.hasta,precio_hora:fr.modo==='hora'?p:0,precio_turno:fr.modo==='turno'?p:0});fr=null;$('rgFranjaForm').hidden=true;franjas();return}
  if(d.luz){if(d.luz==='si')R.recargo_luz=R.recargo_luz||{desde:'18:00',monto:5};else delete R.recargo_luz;luz();return}
  if(d.num){if(d.v==='')delete R[d.num];else R[d.num]=Number(d.v);nums();return}
  if(b.id==='rgVistaBtn'){vista();return}
});
function limpio(){leerSemana();var r=JSON.parse(JSON.stringify(R));if(r.horario_semana&&!Object.keys(r.horario_semana).length)delete r.horario_semana;if(r.recargo_luz&&!(r.recargo_luz.monto>0))delete r.recargo_luz;return r}
async function post(url,body){var r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});var j={};try{j=await r.json()}catch(e){}return j}
async function vista(){var f=$('rgVistaF').value,box=$('rgVista');if(!f)return;box.innerHTML="<p class='sub'>Cargando…</p>";
  var j;try{j=await post('/anfitrion/reglas/'+encodeURIComponent(G.cancha)+'/vista',{fecha:f,reglas:limpio()})}catch(e){box.innerHTML="<p class='sub'>No pudimos cargar la vista previa. Revisa tu conexión.</p>";return}
  if(!j.ok){box.innerHTML="<p class='aviso err'>"+esc(j.mensaje||j.error||'No se pudo')+"</p>";return}
  if(j.cerrado){box.innerHTML="<div class='aviso warn'>🚫 "+esc(j.cerrado)+": ese día no se reserva.</div>";return}
  if(!j.turnos.length){box.innerHTML="<p class='sub'>Ese día no hay turnos.</p>";return}
  box.innerHTML="<p class='sub'>Horario "+esc(j.horario)+"</p><div class='rg-turnos'>"+j.turnos.map(function(t){return "<div class='rg-t'><b>"+esc(t.hora)+"–"+esc(t.fin)+"</b><small>"+esc(j.moneda)+" "+Number(t.precio).toFixed(2)+"</small>"+(t.franja?"<small>"+esc(t.franja)+"</small>":"")+(t.luz?"<small>💡 incluye luz</small>":"")+"</div>"}).join('')+"</div>"}
$('rgForm').addEventListener('submit',async function(ev){ev.preventDefault();var er=$('rgErr');er.hidden=true;leerFranja();
  var ids=[G.cancha];document.querySelectorAll('.rg-her input:checked').forEach(function(i){ids.push(i.value)});
  if(ids.length>1&&!await pcgConfirmar({titulo:'Aplicar a '+ids.length+' canchas',mensaje:'Las mismas reglas reemplazan las que tengan las otras canchas elegidas.',confirmar:'Guardar en todas'}))return;
  var b=$('rgGuardar');b.disabled=true;pcgCargando('Guardando…');try{var j=await post('/anfitrion/reglas/guardar',{cancha_ids:ids,reglas:limpio()});pcgCargando(false);b.disabled=false;
  if(j.ok){R=j.reglas;todo();pcgToast(j.canchas>1?('Reglas guardadas en '+j.canchas+' canchas ✓'):'Reglas guardadas ✓');return}er.textContent=j.mensaje||j.error;er.hidden=false}catch(e){pcgCargando(false);b.disabled=false;er.textContent='No se pudo guardar. Revisa tu conexión.';er.hidden=false}});
todo();vista();
})();
"""
