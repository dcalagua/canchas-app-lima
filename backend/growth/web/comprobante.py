"""COMPROBANTE de una reserva: `GET /reserva/{ref}` (por id o por grupo) y
`GET /reserva/{ref}.ics` (evento para el calendario), con el aviso de pago
en revisión del cobro directo, cambiar y calificar.

Movido tal cual desde `web/router.py`, que lo re-exporta.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response

import config
import empresa
from paises import simbolo_de_moneda
from pagos import cargo_servicio as _cs
from pagos import devoluciones as _dev
from web import beneficios, datos, horarios, pago_hospedado, sesion, ui
from pagos import cobro_directo as _cd
from web.ui import e
from config import MARCA  # noqa: E402 — nombre y dominio de marca (un solo lugar)
from web.comun import EXTRAS_NOMBRE, PLAY_URL, _maps, _moneda_de, _no_encontrada, _pais_de, _zona
from web.ficha import _num_txt, _titulo_local
from web.cancelacion import (JS_CANCELAR, _MODAL_CANCELAR, _boton_cancelar, _cobro_web, _es_cargo_culqi, _ref_de,
                             _total_de)
from web.mis_reservas import MOTIVO_RECHAZO

router = APIRouter()


def _filas_comprobante(ref: str, con_revision: bool = False) -> list[dict]:
    """Filas con comprobante: pagadas o confirmadas y, con [con_revision], las
    que esperan que el club revise el comprobante (cobro directo)."""
    filas = datos.reservas_por_grupo(ref) if ref.startswith("grp_") else datos.reservas_de([ref])
    return [f for f in filas if f.get("pagado") or f.get("estado") == "confirmada"
            or (con_revision and f.get("estado") == "nueva" and str(f.get("medio_pago") or "") == datos.MEDIO_HOLD_VOUCHER)]


def _cabecera_revision(ref: str, v: dict | None) -> str:
    vence = ""
    if v and v.get("vence_en"):
        try:
            vv = v["vence_en"] if isinstance(v["vence_en"], datetime) else datetime.fromisoformat(str(v["vence_en"]))
            vence = f" antes de las {vv.astimezone(horarios.ahora_local('PE').tzinfo).strftime('%H:%M')}" if vv.tzinfo else ""
        except (TypeError, ValueError):
            vence = ""
    op = f" (operación {e(v.get('operacion'))})" if v and v.get("operacion") else ""
    return ("<div style='font-size:44px' aria-hidden='true'>⏳</div><h1>Pago en revisión del club</h1>"
            f"<p class='sub'>Subiste tu comprobante{op}. El club lo confirmará{vence} y te avisaremos. "
            f"Tu horario sigue apartado.</p><p class='sub'>Reserva <b>{e(ref)}</b></p>")


def _pagina_pago_caido(ref: str, v: dict, ses: dict | None) -> HTMLResponse:
    """El club rechazó el comprobante o no lo revisó a tiempo: la reserva ya
    se soltó, pero el jugador debe saber qué pasó (y que el dinero lo tiene el club)."""
    c = datos.cancha(str(v.get("cancha_id") or "")) or {}
    rech = v.get("estado") == "rechazado"
    motivo = MOTIVO_RECHAZO.get(v.get("motivo_rechazo") or "", v.get("motivo_rechazo") or "") if rech else "El club no lo revisó a tiempo."
    cuerpo = ("<div style='max-width:560px;margin:26px auto 0'><div class='panel' style='text-align:center'>"
              "<div style='font-size:44px' aria-hidden='true'>🧾</div>"
              f"<h1>{'El club no confirmó tu pago' if rech else 'Tu pago no se revisó a tiempo'}</h1>"
              f"<p class='sub'>{e(c.get('nombre') or 'Cancha')}{(' · ' + e(c.get('club'))) if c.get('club') else ''}</p>"
              f"<div class='cl-aviso bad' style='text-align:left;margin-top:14px'><b>{e(motivo)}</b>"
              "<span>El horario se liberó. Si ya pagaste, escribe al local con tu comprobante: el dinero lo recibió el club, "
              "no la plataforma.</span></div>"
              f"<p class='sub' style='margin-top:12px'>Operación reportada: <b>{e(v.get('operacion') or '—')}</b> · "
              f"{e(simbolo_de_moneda(v.get('moneda') or 'PEN'))} {int(v.get('monto_centimos') or 0) / 100:.2f}</p>"
              "<div class='acciones' style='justify-content:center'>"
              + (f"<a class='btn' href='/reservar/{e(c['id'])}'>Volver a reservar</a>" if c.get("id") else "")
              + "<a class='btn sec' href='/mis-reservas'>Mis reservas</a></div></div></div>")
    return ui.shell("Pago no confirmado", cuerpo, sesion=ses)


@router.get("/reserva/{ref}.ics")
def comprobante_ics(ref: str) -> Response:
    """Evento(s) para el calendario del cliente (Google/Apple/Outlook)."""
    filas = _filas_comprobante(ref)
    if not filas:
        return Response("No encontrada", status_code=404)
    c = datos.cancha(filas[0]["cancha_id"]) or {}
    pais = _pais_de(c) if c else "PE"
    tz = horarios.ahora_local(pais).tzinfo
    lugar = ", ".join(x for x in (c.get("nombre"), c.get("direccion"), _zona(c)) if x)
    ahora = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    ev = []
    for f in filas:
        try:
            d = date.fromisoformat(f["fecha"])
            hi = horarios.hora_en_minutos(f["hora_inicio"]) or 0
            hf = horarios.hora_en_minutos(f["hora_fin"]) or hi + 60
            if hf <= hi:
                hf += 24 * 60
            ini = datetime(d.year, d.month, d.day, tzinfo=tz) + timedelta(minutes=hi)
            fin = datetime(d.year, d.month, d.day, tzinfo=tz) + timedelta(minutes=hf)
        except (ValueError, TypeError):
            continue
        ev.append("BEGIN:VEVENT\r\n"
                  f"UID:{f['id']}@{config.MARCA_DOMINIO}\r\nDTSTAMP:{ahora}\r\n"
                  f"DTSTART:{ini.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}\r\n"
                  f"DTEND:{fin.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}\r\n"
                  f"SUMMARY:{MARCA} · {_ics(c.get('nombre') or 'Reserva')}\r\n"
                  f"LOCATION:{_ics(lugar)}\r\n"
                  f"DESCRIPTION:Reserva {_ics(ref)}. Comprobante: {_ics((config.PUBLIC_BASE_URL or '').rstrip('/'))}/reserva/{_ics(ref)}\r\n"
                  "END:VEVENT\r\n")
    body = (f"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//{_ics(MARCA)}//Reserva web//ES\r\nCALSCALE:GREGORIAN\r\nMETHOD:PUBLISH\r\n"
            + "".join(ev) + "END:VCALENDAR\r\n")
    return Response(body, media_type="text/calendar; charset=utf-8",
                    headers={"Content-Disposition": f"attachment; filename={MARCA.lower()}-{ref}.ics"})


def _ics(s) -> str:
    return str(s or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _boton_cambiar(ref: str, filas: list[dict], c: dict | None, ses: dict | None) -> str:
    """"🔁 Cambiar horario" si la reserva se puede reprogramar (`jugador_reprogramar.puede`)."""
    if not (ses and ses.get("email")):
        return ""
    from web import jugador_reprogramar as _rp
    return "" if _rp.puede(filas, c, ses["email"].strip().lower()) else _rp.boton(ref)


def _calificar_comprobante(filas: list[dict], c: dict | None, ses: dict | None, es_titular: bool) -> str:
    """En el comprobante de una reserva YA jugada: "⭐ Califica tu partido"."""
    if not (c and ses and es_titular and sesion.activo()):
        return ""
    hoy = horarios.ahora_local(_pais_de(c)).date().isoformat()
    if str(filas[0].get("fecha") or "") >= hoy or str(filas[0].get("estado") or "") in ("noShow", "cancelada", "nueva"):
        return ""
    from web import jugador_resenas as _jr
    est = datos.mis_resenas(ses["email"], [c["id"]]).get(c["id"], 0)
    btn = _jr.boton(c["id"], _titulo_local(c), est).replace("class='lnk calificar'", "class='btn sec calificar'")
    return (f"<div class='acciones'>{btn}</div>"
            f"<style>{_jr.CSS}</style><script>{_jr.js()}</script>")


@router.get("/reserva/{ref}", response_class=HTMLResponse)
def pagina_comprobante(ref: str, request: Request = None, enviado: str = "", cambiada: str = "") -> HTMLResponse:
    ses = sesion.de_request(request)
    filas = _filas_comprobante(ref, con_revision=True)
    voucher = _cd.estado_pago_de_ref((ses or {}).get("email", ""), ref) if ses else None
    if not filas:
        if voucher and voucher.get("estado") in ("rechazado", "vencido"):
            return _pagina_pago_caido(ref, voucher, ses)
        return _no_encontrada("Reserva no encontrada")
    en_revision = all(f.get("estado") == "nueva" and not f.get("pagado") for f in filas)
    # El comprobante se abre con su enlace: sin la sesión del titular no se
    # muestran sus datos personales (el id de la reserva es adivinable).
    # (Sin login con Google activo —modo invitado— el enlace es la única llave.)
    es_titular = (not sesion.activo()) or (bool(ses) and ses["email"] == str(filas[0].get("usuario") or "").strip().lower())
    c = datos.cancha(filas[0]["cancha_id"]) or {}
    sim = filas[0].get("moneda") or "S/"
    total = _total_de(filas)
    # Cargo por servicio cobrado (congelado en el libro con su desglose).
    cobro = _cobro_web(_ref_de(filas))
    cargo_c = int(getattr(cobro, "cargo_servicio_centimos", 0) or 0) if cobro else 0
    desglose_guardado = list(getattr(cobro, "cargo_desglose", None) or []) if cobro else []
    if cargo_c <= 0:
        # Reserva pagada desde el APP: el cargo viene en la fila (columnas
        # `cargo_servicio`/`cargo_desglose`, SQL supabase_reservas_cargo.sql).
        try:
            cargo_c = int(round(float(filas[0].get("cargo_servicio") or 0) * 100))
        except (TypeError, ValueError):
            cargo_c = 0
        raw = filas[0].get("cargo_desglose")
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except ValueError:
                raw = []
        desglose_guardado = list(raw or []) if isinstance(raw, list) else []
    # BONO / PUNTOS: los turnos que cubrió el bono y los S/ 3 de puntos no se
    # pagaron en plata (la fila guarda el precio de lista, como el app).
    aj = beneficios.ajustes(filas, c)
    pagado = max(0, total - aj["bono_cubre"] - aj["puntos_desc"]) + cargo_c / 100.0
    # SEÑA: se pagó solo la seña (+ su cargo); el resto se paga en la cancha.
    sena_c = sum(int(f.get("sena") or 0) for f in filas) if str(filas[0].get("medio_pago") or "") == "sena" else 0
    resto_cancha = 0.0
    if sena_c > 0:
        resto_cancha = max(0.0, total - sena_c)
        pagado = sena_c + cargo_c / 100.0
    extras = [x for f in filas for x in (f.get("extras") or [])]
    # Estado del BOLEADOR (si lo contrató): Esperando confirmación / Confirmado / devuelto.
    estado_bol = ""
    if any(isinstance(x, dict) and x.get("clave") == "boleador" for x in extras):
        try:
            import boleadores as _bol
            estado_bol = _bol.estado_visible(datos.solicitud_por_reserva(ref))
        except Exception:  # noqa: BLE001
            estado_bol = ""
    lineas = "".join(
        f"<div class='linea'><span>{e(horarios.fecha_larga(f['fecha']))} · {e(f['hora_inicio'])}–{e(f['hora_fin'])}</span>"
        f"<b>{e(sim)} {int(f['precio']):.2f}</b></div>" for f in filas)
    lineas += "".join(
        f"<div class='linea'><span>{e(x.get('nombre') or EXTRAS_NOMBRE.get(str(x.get('clave')), str(x.get('clave')).capitalize()))}"
        f"{(' × ' + str(int(x.get('cantidad')))) if int(x.get('cantidad') or 1) > 1 else ''}"
        f"{(' <small class=' + chr(39) + 'sub' + chr(39) + ' style=' + chr(39) + 'font-size:12px' + chr(39) + '>· ' + e(estado_bol) + '</small>') if (x.get('clave') == 'boleador' and estado_bol) else ''}</span>"
        f"<b>{e(sim)} {float(x.get('precio') or 0):.2f}</b></div>" for x in extras)
    # Premio de FIDELIDAD usado en esta reserva (el precio de arriba ya va descontado).
    canje_fid = datos.canje_por_ref(ref)
    if canje_fid and canje_fid.get("estado") == "usado":
        import fidelidad as _fid
        lineas += (f"<div class='linea' style='color:var(--verde)'><span>🎁 Premio de fidelidad · "
                   f"{'hora gratis' if canje_fid.get('tipo') == 'hora_gratis' else 'descuento'}</span>"
                   f"<b>ya descontado {e(sim)} {float(canje_fid.get('descuento') or 0):.2f}</b></div>")
    if aj["bono_cubre"] > 0:
        lineas += (f"<div class='linea' style='color:var(--verde)'><span>🎟️ Pagado con tu bono · {aj['bono_horas']} "
                   f"{'hora' if aj['bono_horas'] == 1 else 'horas'}</span><b>−{e(sim)} {aj['bono_cubre']:.2f}</b></div>")
    if aj["puntos_desc"] > 0:
        lineas += (f"<div class='linea' style='color:var(--verde)'><span>⭐ Canje de {aj['puntos']} puntos {MARCA}</span>"
                   f"<b>−{e(sim)} {aj['puntos_desc']:.2f}</b></div>")
    if cargo_c > 0:
        lineas += (f"<div class='linea'><span>Cargo por servicio {MARCA}</span><b>{e(sim)} {cargo_c / 100.0:.2f}</b></div>")
    detalle_cargo = ""
    if cargo_c > 0:
        _s, _iso_c = _moneda_de(c) if c else (sim, _cs.moneda_iso(sim))
        detalle_cargo = ("<details style='margin-top:8px;text-align:left'><summary class='sub' style='cursor:pointer;font-size:13px'>Qué incluye el cargo por servicio</summary>"
                         f"{ui.desglose_cargo_html(desglose_guardado, sim, _cs.regla_texto(_iso_c))}</details>")
    lugar = ui.unir_lugar(ui.direccion_legible(c.get("direccion") or ""), _zona(c))
    base = (config.PUBLIC_BASE_URL or "").rstrip("/")
    boton_wa = ui.boton_whatsapp(
        f"Reservé en {c.get('nombre', 'una cancha')} por {MARCA}: "
        f"{horarios.fecha_larga(filas[0]['fecha'])} {filas[0]['hora_inicio']}–{filas[-1]['hora_fin']}. "
        f"Comprobante: {base}/reserva/{ref}", etiqueta="💬 Compartir", clase="btn sec")
    medio = {"yape": "Yape", "tarjeta": "tarjeta", "fidelidad": "tu premio de fidelidad 🎁", "sena": "seña en línea",
             "bono": "tu bono de horas 🎟️", "plin": "Plin", "transferencia": "transferencia bancaria",
             "qr": "QR", "billetera": "billetera digital"}.get(str(filas[0].get("medio_pago") or ""), "en línea")
    if voucher and voucher.get("estado") == "aprobado":
        medio += " · confirmado por el club"
    if cobro is not None and not _es_cargo_culqi(cobro) and ":" in str(cobro.culqi_charge_id or ""):
        # Cobro por pasarela hospedada ($ / Bs): se nombra la pasarela.
        medio += f" · {pago_hospedado.nombre_pasarela(str(cobro.culqi_charge_id).split(':', 1)[0])}"
    cuerpo = (
        "<div style='max-width:640px;margin:26px auto 0'>"
        + ("<div class='cl-aviso' role='status' style='margin-bottom:14px'><b>✅ Recibimos tu comprobante</b>"
           "<span>Te avisamos apenas el club lo confirme.</span></div>" if (enviado and en_revision) else "")
        + f"<div class='panel' style='text-align:center'>"
        + (_cabecera_revision(ref, voucher) if en_revision else
           ("<div class='estado ok' role='status' style='text-align:left'>🔁 Listo: cambiaste el horario de tu reserva. El local ya lo ve en su agenda.</div>" if cambiada else "")
           + f"{ui.check_svg()}<h1>¡Reserva confirmada!</h1><p class='sub'>Comprobante <b title='{e(ref)}'>{e(ui.codigo_corto(ref))}</b> · pagado con {e(medio)}</p>")
        +
        f"<h3 style='margin-top:16px'>{e(c.get('nombre') or 'Cancha')}</h3>"
        f"<div class='sub'>{e(c.get('club'))}{(' · ' + e(lugar)) if lugar else ''}</div>"
        f"<div style='text-align:left;margin-top:16px'>{lineas}"
        + (f"<div class='linea'><span>Total de la reserva</span><b>{e(sim)} {total:.2f}</b></div>" if sena_c else "")
        + f"<div class='total'><span>{'Pagaste hoy (seña)' if sena_c else ('Pagado al club · en revisión' if en_revision else 'Total pagado')}</span><span>{e(sim)} {pagado:.2f}</span></div>"
        + (f"<div class='linea' style='font-weight:700'><span>Por pagar en la cancha</span><b>{e(sim)} {resto_cancha:.2f}</b></div>"
           "<div class='sub' style='font-size:12.5px'>La seña no es reembolsable: si no llegas, queda a favor de la cancha.</div>" if sena_c else "")
        + f"{detalle_cargo}</div>"
        + (f"<div class='sub' style='margin-top:12px'>A nombre de <b>{e(filas[0].get('jugador'))}</b> · {e(filas[0].get('usuario'))}. "
           "Guarda este enlace: es tu comprobante.</div>" if es_titular else
           "<div class='sub' style='margin-top:12px'>Inicia sesión con la cuenta de la reserva para ver sus datos.</div>")
        +
        "<div class='acciones'>"
        f"<a class='btn sec' href='/reserva/{e(ref)}.ics'>📅 Agregar al calendario</a>"
        + (f"<a class='btn sec' href='{_maps(c)}' target='_blank' rel='noopener'>📍 Cómo llegar</a>" if c else "")
        + boton_wa
        + "</div>"
        + (f"<div class='acciones'>{_boton_cambiar(ref, filas, c, ses)}{_boton_cancelar(filas, c, ses, 'btn sec')}</div>" if (not en_revision and _boton_cancelar(filas, c, ses)) else "")
        + _calificar_comprobante(filas, c, ses, es_titular)
        + f"<div class='estado ok' style='text-align:left'>Política del club: cancelación con más de {_num_txt(_dev.horas_minimas(c))} h de anticipación, devolución del 100 % al mismo medio de pago. "
        f"Puedes cancelar desde aquí o desde <a href='/mis-reservas'>Mis reservas</a>. Dudas: <a href='mailto:{empresa.datos()['correo']}'>{empresa.datos()['correo']}</a>.</div>"
        "</div>"
        "<div class='panel' style='margin-top:16px;display:flex;gap:14px;align-items:center;flex-wrap:wrap'>"
        "<img src='/marca/logo.png' alt='' style='width:56px;height:56px;border-radius:14px;border:1px solid var(--trazo)'>"
        "<div style='flex:1;min-width:200px'><b>Lleva tus reservas contigo</b>"
        "<div class='sub' style='font-size:13px'>Con la app ves tu agenda, acumulas puntos y reservas en dos toques.</div></div>"
        f"<a class='btn' href='{PLAY_URL}'>Descargar la app</a></div>"
        "<div style='text-align:center;margin-top:16px'><a href='/canchas'>Reservar otra cancha</a></div>"
        f"</div>{_MODAL_CANCELAR}<script>{JS_CANCELAR}</script>")
    return ui.shell("Pago en revisión" if en_revision else "Reserva confirmada", cuerpo, sesion=ses)
