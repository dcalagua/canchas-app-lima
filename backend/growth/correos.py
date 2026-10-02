"""CORREOS TRANSACCIONALES DE PAGO (pedido del director, 1-oct-2026:
"cuando el usuario reserva una cancha o se matricula o algo que tenga que ver
con un pago, obligatoriamente PCG debe enviarle un correo… y de igual manera
le llega un correo al dueño de cancha, dueño de academia o boleador").

Cómo funciona:

1. **Un solo enganche**: `stores.registrar_pago` llama a `al_pago(p)` con cada
   movimiento del libro. Según el `tipo` se encola un EVENTO (reserva,
   matrícula, venta, recarga, Pro, servicio, bodega, torneo, aporte, boleo).
   Así cubre app y web por igual: los dos pasan por la misma contabilidad.
2. **Rebote**: reservas y matrículas esperan ~40 s antes de armarse (el APK
   registra una liquidación por turno y la web escribe la orden DESPUÉS del
   pago) → UN correo por reserva/pago con todos sus turnos o alumnos.
3. **Armado**: cada evento lee los datos REALES (filas de `pichangol_reservas`,
   `pichangol_matriculas`, academia, cancha, orden del marketplace) y genera
   el RECIBO para quien pagó y el AVISO para quien recibe (dueño de la cancha,
   de la academia, vendedor, organizador, boleador) con lo que le toca.
4. **Bandeja de salida persistente** (`stores.correos`, en el snapshot): clave
   única por destinatario (`reserva:<grupo>:cliente`…) → nunca se manda dos
   veces; reintentos con espera creciente (1 min → 6 h) y `fallo` al 6.º.
5. **Proveedor**: Resend (`RESEND_API_KEY`) o SMTP (`SMTP_HOST`, `SMTP_PORT`,
   `SMTP_USUARIO`, `SMTP_CLAVE`); remitente `CORREO_REMITENTE`. Sin proveedor
   los correos quedan `sin_proveedor` (visibles en la torre) y nada se rompe.

Torre: `/admin` → Comunicación → "✉️ Correos de pago" (estado, últimos
envíos, correo de prueba, reintentar). Hilo `pcg-correos` arrancado en
`main.py`.
"""

from __future__ import annotations

import json
import os
import smtplib
import ssl
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import formataddr, make_msgid, parseaddr
from html import escape

import config
from db.store import stores

# ── Configuración ─────────────────────────────────────────────────────────────

REBOTE_S = {"reserva": 40, "matricula": 40, "venta": 8}
REBOTE_DEFECTO = 4
REINTENTOS_S = (60, 300, 1800, 7200, 21600)   # luego → fallo
MAX_ARMADO = 8          # intentos de armar un evento cuyos datos aún no llegan
VENCE_H = 48            # un correo que no salió en 48 h ya no sirve (vencido)
MAX_BANDEJA = 600

_LOCK = threading.RLock()
_HILO: threading.Thread | None = None
_MONEDA = {"PEN": "S/", "USD": "$", "BOB": "Bs"}


def _env(nombre: str) -> str:
    return (os.getenv(nombre) or "").strip()


def remitente() -> str:
    return _env("CORREO_REMITENTE") or "Pichangol <no-reply@pichangol.app>"


def proveedor() -> str:
    """resend | smtp | '' (sin proveedor: no se envía nada)."""
    if _env("RESEND_API_KEY"):
        return "resend"
    if _env("SMTP_HOST"):
        return "smtp"
    return ""


def activo() -> bool:
    try:
        return (stores.cfg("correos_activo") or "1") != "0"
    except Exception:  # noqa: BLE001
        return True


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _iso(d: datetime) -> str:
    return d.isoformat()


def _de_iso(s: str | None) -> datetime:
    try:
        return datetime.fromisoformat(str(s))
    except (TypeError, ValueError):
        return _ahora()


def base_url() -> str:
    return config.url_limpia(config.LANDING_BASE_URL) or config.url_limpia(config.PUBLIC_BASE_URL) \
        or "https://www.pichangol.app"


def _correo_valido(c: str | None) -> bool:
    c = (c or "").strip()
    return "@" in c and "." in c.split("@")[-1] and " " not in c and len(c) <= 200


def _sim(moneda: str | None) -> str:
    m = (moneda or "PEN").strip().upper()
    return _MONEDA.get(m, m if m in ("S/", "$", "BS") else "S/")


def _monto(centimos: int | float, moneda: str | None) -> str:
    return f"{_sim(moneda)} {float(centimos) / 100.0:,.2f}"


def _soles(valor: float, moneda: str | None) -> str:
    return f"{_sim(moneda)} {float(valor):,.2f}"


def _medio_txt(medio: str | None) -> str:
    m = (medio or "").strip().lower()
    return {"yape": "Yape", "tarjeta": "Tarjeta", "saldo": "Saldo Pichangol", "sena": "Seña en línea",
            "yape_qr": "Yape (QR)", "fidelidad": "Premio de fidelidad", "efectivo": "Efectivo",
            "payphone": "PayPhone", "libelula": "Libélula"}.get(m, m.capitalize() if m else "")


# ── Estado persistente (vive en stores → snapshot) ────────────────────────────

def _bandeja() -> list[dict]:
    if not isinstance(getattr(stores, "correos", None), list):
        stores.correos = []
    return stores.correos


def _eventos() -> list[dict]:
    if not isinstance(getattr(stores, "correos_eventos", None), list):
        stores.correos_eventos = []
    return stores.correos_eventos


# ── Enganche con el libro de pagos ────────────────────────────────────────────

# tipo de pago → evento
_EVENTO_DE_TIPO = {
    "liquidacion_online": "reserva", "liquidacion_full": "reserva",
    "matricula_online": "matricula",
    "venta_producto": "venta",
    "recarga": "recarga",
    "suscripcion_pro": "pro",
    "suscripcion": "servicio",
    "venta_bodega": "bodega",
    "inscripcion_torneo": "torneo",
    "inscripcion_torneo_ingreso": "torneo_ingreso",
    "aporte_equipo": "aporte",
    "liquidacion_boleador": "boleo",
}


def al_pago(p) -> None:
    """Lo llama `stores.registrar_pago`. Barato: solo encola. Nunca lanza."""
    try:
        ev = _EVENTO_DE_TIPO.get(getattr(p, "tipo", "") or "")
        if not ev or (getattr(p, "estado", "") or "") != "aprobado":
            return
        if int(getattr(p, "monto_centimos", 0) or 0) <= 0:
            return
        encolar(ev, pago_id=int(p.id))
    except Exception as ex:  # noqa: BLE001 — un correo jamás rompe un cobro
        print(f"[correos] no se pudo encolar: {ex}", flush=True)


def encolar(tipo: str, *, pago_id: int | None = None, datos: dict | None = None) -> dict:
    ahora = _ahora()
    ev = {"id": f"ev_{int(time.time() * 1_000_000)}_{len(_eventos())}", "tipo": tipo,
          "pago_id": pago_id, "datos": datos or {}, "creado": _iso(ahora),
          "listo_en": _iso(ahora + timedelta(seconds=REBOTE_S.get(tipo, REBOTE_DEFECTO))), "intentos": 0}
    with _LOCK:
        _eventos().append(ev)
    return ev


class _NoListo(Exception):
    """Los datos del evento aún no están (p. ej. la fila de la reserva no llegó)."""


# ── Utilidades de datos ───────────────────────────────────────────────────────

def _pago(pid) -> object | None:
    for q in reversed(stores.pagos):
        if q.id == pid:
            return q
    return None


def _cobro_de(charge: str | None):
    """La fila del CARGO (`cobro_web`, o `reserva|academia|cobro` de
    `/pagos/cobrar`) con ese N.º de operación: trae el correo de quien pagó,
    el monto total cobrado y el medio."""
    if not charge:
        return None
    for q in reversed(stores.pagos):
        if q.culqi_charge_id == charge and q.tipo in ("cobro_web", "reserva", "academia", "cobro"):
            return q
    return None


def _datos():
    from web import datos
    return datos


def _fecha_txt(iso: str) -> str:
    try:
        from web import horarios
        return horarios.fecha_larga(str(iso))
    except Exception:  # noqa: BLE001
        return str(iso)


def _nombre_de(email: str) -> str:
    try:
        return (stores.clientes_pago.get((email or "").lower()) or {}).get("nombre") or ""
    except Exception:  # noqa: BLE001
        return ""


def _hola(nombre: str) -> str:
    n = (nombre or "").strip().split(" ")[0]
    return f"Hola {n}," if n else "Hola,"


def _liq(p) -> dict:
    try:
        from pagos.router import _liquidacion_dict
        return _liquidacion_dict(p)
    except Exception:  # noqa: BLE001
        com = int(getattr(p, "comision_centimos", 0) or 0)
        return {"bruto_soles": p.monto_centimos / 100.0, "comision_soles": com / 100.0,
                "neto_soles": (p.monto_centimos - com) / 100.0}


# ── Plantilla HTML (estilo Airbnb, paleta del logo) ───────────────────────────

_VERDE = "#0B8A3E"
_TINTA = "#0A1B3D"
_TENUE = "#6A7282"
_BORDE = "#E7EAEE"


def _fila_dato(et: str, val: str) -> str:
    return (f"<tr><td style='padding:6px 0;color:{_TENUE};font-size:13px;width:38%;vertical-align:top'>{escape(et)}</td>"
            f"<td style='padding:6px 0;color:{_TINTA};font-size:14px;font-weight:600;text-align:right'>{escape(val)}</td></tr>")


def _fila_monto(et: str, val: str, *, fuerte: bool = False, tenue: bool = False) -> str:
    peso = "800" if fuerte else "500"
    color = _TENUE if tenue else _TINTA
    tam = "16px" if fuerte else "14px"
    borde = f"border-top:1px solid {_BORDE};" if fuerte else ""
    return (f"<tr><td style='{borde}padding:{'12px' if fuerte else '6px'} 0 6px;color:{color};font-size:{tam};font-weight:{peso}'>{escape(et)}</td>"
            f"<td style='{borde}padding:{'12px' if fuerte else '6px'} 0 6px;color:{color};font-size:{tam};font-weight:{peso};text-align:right;white-space:nowrap'>{escape(val)}</td></tr>")


def plantilla(*, titulo: str, saludo: str, intro: str, datos: list[tuple[str, str]] | None = None,
              lineas: list[tuple[str, str]] | None = None, total: tuple[str, str] | None = None,
              extra_montos: list[tuple[str, str]] | None = None, boton: tuple[str, str] | None = None,
              notas: list[str] | None = None, etiqueta: str = "Constancia de pago") -> tuple[str, str]:
    """(html, texto). Tablas con estilos en línea: Gmail/Outlook ignoran <style>."""
    try:
        import empresa
        e = empresa.datos()
    except Exception:  # noqa: BLE001
        e = {}
    base = base_url()
    logo = f"{base}/static/brand/logo_pin.png"
    bloque_datos = ""
    if datos:
        bloque_datos = ("<table role='presentation' width='100%' cellpadding='0' cellspacing='0' "
                        f"style='margin:6px 0 4px'>{''.join(_fila_dato(a, b) for a, b in datos if b)}</table>")
    bloque_montos = ""
    if lineas or total:
        filas = "".join(_fila_monto(a, b) for a, b in (lineas or []))
        if total:
            filas += _fila_monto(total[0], total[1], fuerte=True)
        filas += "".join(_fila_monto(a, b, tenue=True) for a, b in (extra_montos or []))
        bloque_montos = (f"<div style='margin:18px 0 6px;padding:16px 18px;border:1px solid {_BORDE};border-radius:16px'>"
                         f"<div style='font-size:12px;font-weight:700;letter-spacing:.04em;text-transform:uppercase;color:{_TENUE};margin-bottom:6px'>Detalle</div>"
                         f"<table role='presentation' width='100%' cellpadding='0' cellspacing='0'>{filas}</table></div>")
    bloque_boton = ""
    if boton:
        bloque_boton = (f"<div style='margin:22px 0 6px'><a href='{escape(boton[1])}' style='display:inline-block;background:{_VERDE};"
                        f"color:#ffffff;text-decoration:none;font-weight:700;font-size:15px;padding:13px 22px;border-radius:12px'>{escape(boton[0])}</a></div>")
    bloque_notas = "".join(f"<p style='margin:10px 0 0;color:{_TENUE};font-size:13px;line-height:1.5'>{escape(n)}</p>" for n in (notas or []) if n)
    pie_emp = " · ".join(x for x in (e.get("razon_social", ""), (f"{e.get('doc_etiqueta', 'RUC')} {e.get('ruc', '')}" if e.get("ruc") else ""),
                                     e.get("ciudad", "")) if x)
    contacto = e.get("correo", "")
    html = f"""<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(titulo)}</title></head>
<body style="margin:0;padding:0;background:#F4F6F8;font-family:'DM Sans',Helvetica,Arial,sans-serif;color:{_TINTA}">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#F4F6F8"><tr><td align="center" style="padding:24px 12px">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;background:#ffffff;border-radius:20px;overflow:hidden">
<tr><td style="padding:22px 26px 6px">
  <table role="presentation" cellpadding="0" cellspacing="0"><tr>
    <td style="vertical-align:middle"><img src="{logo}" width="34" height="34" alt="" style="display:block;border:0"></td>
    <td style="vertical-align:middle;padding-left:8px;font-size:20px;font-weight:800;color:{_TINTA}">Pichangol</td>
  </tr></table>
</td></tr>
<tr><td style="padding:10px 26px 26px">
  <div style="display:inline-block;background:#E8F5EC;color:{_VERDE};font-size:12px;font-weight:700;padding:5px 10px;border-radius:999px">{escape(etiqueta)}</div>
  <h1 style="margin:14px 0 6px;font-size:22px;line-height:1.3;color:{_TINTA}">{escape(titulo)}</h1>
  <p style="margin:0 0 4px;font-size:15px;color:{_TINTA}">{escape(saludo)}</p>
  <p style="margin:0 0 8px;font-size:15px;line-height:1.55;color:{_TINTA}">{escape(intro)}</p>
  {bloque_datos}{bloque_montos}{bloque_boton}{bloque_notas}
</td></tr>
<tr><td style="padding:16px 26px 22px;background:#FAFBFC;border-top:1px solid {_BORDE};font-size:12px;line-height:1.55;color:{_TENUE}">
  Este correo es una constancia de tu operación en Pichangol; no es un comprobante de pago electrónico.
  {('¿Dudas? Escríbenos a <a href="mailto:' + contacto + '" style="color:' + _VERDE + '">' + contacto + '</a>.') if contacto else ''}<br>
  {pie_emp}{(' · ' if pie_emp else '')}<a href="{base}" style="color:{_TENUE}">{escape(base.replace('https://', ''))}</a>
</td></tr>
</table></td></tr></table></body></html>"""
    # Versión texto (clientes sin HTML y filtros de spam).
    t = [titulo, "", saludo, intro, ""]
    t += [f"{a}: {b}" for a, b in (datos or []) if b]
    if lineas or total:
        t.append("")
        t += [f"{a}: {b}" for a, b in (lineas or [])]
        if total:
            t.append(f"{total[0]}: {total[1]}")
        t += [f"{a}: {b}" for a, b in (extra_montos or [])]
    if boton:
        t += ["", f"{boton[0]}: {boton[1]}"]
    t += [""] + [n for n in (notas or []) if n]
    t += ["", "Pichangol · " + base]
    return html, "\n".join(t)


def _msg(clave: str, para: str, asunto: str, html_txt: tuple[str, str], rol: str, tipo: str) -> dict:
    return {"clave": clave, "para": (para or "").strip().lower(), "asunto": asunto, "html": html_txt[0],
            "texto": html_txt[1], "rol": rol, "tipo": tipo}


# ── Armado por tipo de evento ─────────────────────────────────────────────────

def _armar_reserva(ev: dict) -> list[dict]:
    p = _pago(ev.get("pago_id"))
    if p is None:
        return []
    datos = _datos()
    filas = datos.reservas_de([str(p.culqi_charge_id)]) if p.culqi_charge_id else []
    if not filas:
        raise _NoListo("reserva")
    grupo = (filas[0].get("grupo_reserva_id") or "").strip()
    if grupo:
        filas = datos.reservas_por_grupo(grupo) or filas
    ref = grupo or str(filas[0]["id"])
    ids = {str(f["id"]) for f in filas}
    liqs = [q for q in stores.pagos if q.tipo in ("liquidacion_online", "liquidacion_full")
            and str(q.culqi_charge_id) in ids and q.estado == "aprobado"]
    moneda = p.moneda or filas[0].get("moneda") or "PEN"
    c = datos.cancha(str(filas[0]["cancha_id"])) or {}
    local = str(c.get("club") or c.get("nombre") or "la cancha")
    cancha_nom = str(c.get("nombre") or "")
    charge = next((q.cargo_id for q in liqs if q.cargo_id), None) or p.cargo_id
    cobro = _cobro_de(charge)
    pagador = (str(filas[0].get("usuario") or "").strip().lower()) or (cobro.email if cobro else "") or ""
    jugador = str(filas[0].get("jugador") or "") or _nombre_de(pagador)
    # Líneas: turnos + extras (incluye boleador) + cargo por servicio.
    lineas: list[tuple[str, str]] = []
    subtotal = 0.0
    for f in filas:
        lineas.append((f"Turno {f.get('hora_inicio', '')}–{f.get('hora_fin', '')}", _soles(f.get("precio") or 0, moneda)))
        subtotal += float(f.get("precio") or 0)
    bol = None
    for f in filas:
        for x in f.get("extras") or []:
            if not isinstance(x, dict):
                continue
            pr = float(x.get("precio") or 0)
            nombre = str(x.get("nombre") or x.get("clave") or "Extra")
            cant = int(x.get("cantidad") or 0)
            et = f"{nombre} × {cant}" if cant > 1 else nombre
            if x.get("clave") == "boleador":
                bol = x
                et += " (por confirmar)" if (x.get("estado") or "pendiente") == "pendiente" else ""
            lineas.append((et, _soles(pr, moneda)))
            subtotal += pr
    cargo_c = sum(int(q.cargo_servicio_centimos or 0) for q in liqs)
    if not cargo_c:
        cargo_c = int(round(float(filas[0].get("cargo_servicio") or 0) * 100))
    if cargo_c:
        lineas.append(("Cargo por servicio Pichangol", _monto(cargo_c, moneda)))
    total_c = int(round(subtotal * 100)) + cargo_c
    if cobro and cobro.monto_centimos:
        pagado_c = int(cobro.monto_centimos)
    else:
        pagado_c = sum(int(q.monto_centimos) for q in liqs) + cargo_c + (int(round(float(bol.get("precio") or 0) * 100)) if bol else 0)
    pagado_c = min(pagado_c, total_c) if total_c else pagado_c
    resto_c = max(0, total_c - pagado_c)
    medio = (cobro.medio if cobro and cobro.medio else "") or p.medio or filas[0].get("medio_pago") or ""
    fecha = _fecha_txt(str(filas[0].get("fecha") or ""))
    horario = f"{filas[0].get('hora_inicio', '')}–{filas[-1].get('hora_fin', '')}"
    turnos = len(filas)
    dir_ = str(c.get("direccion") or "")
    url_ref = f"{base_url()}/reserva/{ref}"
    mapa = f"https://www.google.com/maps/dir/?api=1&destination={c.get('lat')},{c.get('lng')}" if c.get("lat") and c.get("lng") else ""
    out: list[dict] = []
    if _correo_valido(pagador):
        extra = []
        if resto_c:
            extra.append(("Por pagar en la cancha", _monto(resto_c, moneda)))
        notas = []
        if bol:
            notas.append("Tu boleador recibe la solicitud y la confirma; si no puede, te devolvemos su parte automáticamente.")
        if mapa:
            notas.append(f"Cómo llegar: {mapa}")
        notas.append("Puedes ver o cancelar tu reserva desde “Mis reservas” (app o web), según la política de cancelación.")
        out.append(_msg(f"reserva:{ref}:cliente", pagador, f"✅ Pago confirmado · Tu reserva en {local} · {fecha} {horario}",
                        plantilla(titulo="¡Tu reserva está confirmada!", saludo=_hola(jugador),
                                  intro=f"Recibimos tu pago. Te esperamos en {local}.",
                                  datos=[("Local", local), ("Cancha", cancha_nom if cancha_nom != local else ""),
                                         ("Dirección", dir_), ("Fecha", fecha), ("Horario", f"{horario} · {turnos} turno{'s' if turnos > 1 else ''}"),
                                         ("A nombre de", jugador), ("Medio de pago", _medio_txt(medio)),
                                         ("N.º de operación", str(charge or "")), ("Código de reserva", ref)],
                                  lineas=lineas, total=("Pagaste hoy", _monto(pagado_c, moneda)), extra_montos=extra,
                                  boton=("Ver mi comprobante", url_ref), notas=notas),
                        "cliente", "reserva"))
    dueno = str(c.get("dueno") or p.dueno_id or "").strip().lower()
    if _correo_valido(dueno):
        bruto = sum(float(_liq(q).get("bruto_soles") or 0) for q in liqs)
        com = sum(float(_liq(q).get("comision_soles") or 0) for q in liqs)
        neto = sum(float(_liq(q).get("neto_soles") or 0) for q in liqs)
        montos = [("Precio pagado en línea", _soles(bruto, moneda)), ("Comisión Pichangol", "− " + _soles(com, moneda))]
        extra = [("Por cobrar en la cancha", _monto(resto_c, moneda))] if resto_c else []
        notas = ["El neto queda “por recibir” en tu billetera y te lo transferimos a tu cuenta de cobro registrada."]
        if bol:
            notas.append("El boleador lo paga Pichangol aparte: no se descuenta de tu liquidación.")
        out.append(_msg(f"reserva:{ref}:dueno", dueno, f"📅 Nueva reserva pagada · {local} · {fecha} {horario}",
                        plantilla(titulo="Tienes una nueva reserva pagada", saludo=_hola(_nombre_de(dueno)),
                                  intro=f"{jugador or 'Un jugador'} reservó y pagó en línea en {local}.",
                                  datos=[("Cancha", cancha_nom or local), ("Fecha", fecha),
                                         ("Horario", f"{horario} · {turnos} turno{'s' if turnos > 1 else ''}"),
                                         ("Cliente", jugador), ("Celular", str(filas[0].get("telefono") or "")),
                                         ("Medio de pago", _medio_txt(medio)), ("Código de reserva", ref)],
                                  lineas=montos, total=("Recibes", _soles(neto, moneda)), extra_montos=extra,
                                  boton=("Ver mi calendario", f"{base_url()}/anfitrion/calendario"), notas=notas,
                                  etiqueta="Aviso de pago recibido"),
                        "dueno", "reserva"))
    return out


def _armar_matricula(ev: dict) -> list[dict]:
    p = _pago(ev.get("pago_id"))
    if p is None:
        return []
    datos = _datos()
    aid = str(p.dueno_id or "")
    charge = str(p.cargo_id or p.culqi_charge_id or "")
    base_op = charge.split("#")[0]
    # Todos los cobros de matrícula de ESTA academia con el mismo cargo (renovación
    # agrupada por familia: `chr_…`, `chr_…#1`…) = un solo correo.
    pagos = [q for q in stores.pagos if q.tipo == "matricula_online" and str(q.dueno_id or "") == aid and q.estado == "aprobado"
             and str(q.cargo_id or q.culqi_charge_id or "").split("#")[0] == base_op] or [p]
    a = datos.academia(aid) or {}
    alumnos = datos.matriculas_por_operacion(aid, base_op) if (base_op and hasattr(datos, "matriculas_por_operacion")) else []
    cobro = _cobro_de(base_op)
    if not alumnos and not cobro and int(ev.get("intentos") or 0) < 3:
        raise _NoListo("matricula")
    nombre_aca = str(a.get("nombre") or "tu academia")
    moneda = (cobro.moneda if cobro else "") or str(a.get("moneda") or "") or p.moneda or "PEN"
    if moneda in ("S/", "$", "Bs"):
        moneda = {"S/": "PEN", "$": "USD", "Bs": "BOB"}[moneda]
    pagador = (cobro.email if cobro and cobro.email else "") or (str(alumnos[0].get("email") or "") if alumnos else "")
    pagador = pagador.strip().lower()
    lineas: list[tuple[str, str]] = []
    suma_c = 0
    nombres = []
    for al in alumnos:
        cuotas = [cu for cu in (al.get("cuotas") or []) if isinstance(cu, dict) and str(cu.get("operacionId") or "").split("#")[0] == base_op]
        if not cuotas:
            continue
        nombres.append(str(al.get("nombre") or "Alumno"))
        m = sum(int(round(float(cu.get("monto") or 0) * 100)) for cu in cuotas)
        con = cuotas[0].get("concepto") or "Matrícula"
        con = f"{con}{f' (+{len(cuotas) - 1} más)' if len(cuotas) > 1 else ''}"
        lineas.append((f"{al.get('nombre') or 'Alumno'} · {con}", _monto(m, moneda)))
        suma_c += m
    precio_c = sum(int(q.monto_centimos) for q in pagos)
    cargo_c = sum(int(q.cargo_servicio_centimos or 0) for q in pagos)
    if not lineas:
        lineas.append((p.concepto or "Matrícula", _monto(precio_c, moneda)))
    elif suma_c != precio_c and abs(suma_c - precio_c) > 1:
        dif = precio_c - suma_c
        lineas.append(("Descuentos (familiar / prepago)" if dif < 0 else "Ajuste", ("− " if dif < 0 else "") + _monto(abs(dif), moneda)))
    if cargo_c:
        lineas.append(("Cargo por servicio Pichangol", _monto(cargo_c, moneda)))
    total_c = precio_c + cargo_c
    medio = (cobro.medio if cobro and cobro.medio else "") or p.medio or ""
    renovacion = "renov" in (p.concepto or "").lower() or "#" in charge
    quien = ", ".join(nombres) if nombres else ""
    out: list[dict] = []
    if _correo_valido(pagador):
        out.append(_msg(f"matricula:{base_op or p.id}:{aid}:cliente", pagador,
                        f"✅ Pago confirmado · {nombre_aca}" + (f" · {quien}" if quien else ""),
                        plantilla(titulo="Tu pago de clases está confirmado" if not renovacion else "Se cobró tu mensualidad",
                                  saludo=_hola(_nombre_de(pagador)),
                                  intro=(f"Recibimos tu pago a {nombre_aca}." if not renovacion
                                         else f"Cobramos automáticamente la mensualidad de {nombre_aca} con tu tarjeta registrada."),
                                  datos=[("Academia", nombre_aca), ("Alumno(s)", quien), ("Medio de pago", _medio_txt(medio)),
                                         ("N.º de operación", base_op)],
                                  lineas=lineas, total=("Pagaste", _monto(total_c, moneda)),
                                  boton=("Ver mis clases y pagos", f"{base_url()}/mis-clases"),
                                  notas=["Puedes ver tus cuotas, próximos vencimientos y el débito automático en “Mis clases y pagos”."]),
                        "cliente", "matricula"))
    dueno = str(a.get("dueno") or "").strip().lower()
    if _correo_valido(dueno):
        com = sum(float(_liq(q).get("comision_soles") or 0) for q in pagos)
        neto = sum(float(_liq(q).get("neto_soles") or 0) for q in pagos)
        out.append(_msg(f"matricula:{base_op or p.id}:{aid}:dueno", dueno,
                        f"🎓 Pago recibido · {nombre_aca}" + (f" · {quien}" if quien else ""),
                        plantilla(titulo="Recibiste un pago de matrícula" if not renovacion else "Se cobró una mensualidad",
                                  saludo=_hola(_nombre_de(dueno)),
                                  intro=f"{quien or 'Un alumno'} pagó en línea en {nombre_aca}.",
                                  datos=[("Alumno(s)", quien), ("Pagó", pagador), ("Medio de pago", _medio_txt(medio)),
                                         ("N.º de operación", base_op)],
                                  lineas=[("Cobrado (sin cargo por servicio)", _monto(precio_c, moneda)),
                                          ("Comisión Pichangol", "− " + _soles(com, moneda))],
                                  total=("Recibes", _soles(neto, moneda)),
                                  boton=("Ver mis alumnos", f"{base_url()}/anfitrion/academia/alumnos?academia={aid}"),
                                  notas=["El neto queda “por recibir” y te lo transferimos a tu cuenta de cobro registrada."],
                                  etiqueta="Aviso de pago recibido"),
                        "dueno", "matricula"))
    return out


def _armar_venta(ev: dict) -> list[dict]:
    p = _pago(ev.get("pago_id"))
    if p is None:
        return []
    vend = str(p.dueno_id or "").strip().lower()
    orden = None
    for v in reversed(stores.ventas):
        if (v.vendedor_email or "").lower() == vend and abs(float(v.monto_soles) * 100 - p.monto_centimos) <= 1 \
                and abs((v.creado_en - p.creado_en).total_seconds()) < 120:
            orden = v
            break
    if orden is None and int(ev.get("intentos") or 0) < 2:
        raise _NoListo("venta")
    moneda = p.moneda or "PEN"
    producto = (orden.producto_nombre if orden else "") or p.concepto or "Producto"
    comprador = (orden.comprador_email if orden else "") or (_cobro_de(p.cargo_id or p.culqi_charge_id).email
                                                              if _cobro_de(p.cargo_id or p.culqi_charge_id) else "")
    comprador = (comprador or "").strip().lower()
    es_bono = "bono" in (p.concepto or "").lower() or str(p.culqi_charge_id or "").startswith("bono")
    ref = str(p.culqi_charge_id or p.id)
    out = []
    if _correo_valido(comprador):
        out.append(_msg(f"venta:{ref}:cliente", comprador, f"✅ Compra confirmada · {producto}",
                        plantilla(titulo="¡Tu compra está confirmada!", saludo=_hola(orden.comprador_nombre if orden else ""),
                                  intro=("Tu bono ya está en “Mis bonos” y lo usas al reservar." if es_bono else
                                         f"Pagaste {producto}. Coordina la entrega con {orden.vendedor_nombre if orden and orden.vendedor_nombre else 'el vendedor'} por el chat."),
                                  datos=[("Producto", producto), ("Vendedor", orden.vendedor_nombre if orden else ""),
                                         ("N.º de operación", str(p.cargo_id or p.culqi_charge_id or ""))],
                                  lineas=[(producto, _monto(p.monto_centimos, moneda))], total=("Pagaste", _monto(p.monto_centimos, moneda)),
                                  boton=("Ver mis bonos" if es_bono else "Ver mis órdenes", f"{base_url()}/{'mis-bonos' if es_bono else 'mis-ordenes'}"),
                                  notas=[] if es_bono else ["Tu dinero queda protegido: se libera al vendedor cuando confirmas que lo recibiste."]),
                        "cliente", "venta"))
    if _correo_valido(vend):
        lq = _liq(p)
        out.append(_msg(f"venta:{ref}:dueno", vend, f"🛍️ ¡Te compraron! · {producto}",
                        plantilla(titulo="¡Vendiste " + ("un bono" if es_bono else "un producto") + "!", saludo=_hola(orden.vendedor_nombre if orden else ""),
                                  intro=(f"{orden.comprador_nombre or 'Un cliente'} pagó {producto}." if orden else f"Se pagó {producto}.")
                                  + ("" if es_bono else " Coordina la entrega por el chat."),
                                  datos=[("Producto", producto), ("Comprador", orden.comprador_nombre if orden else "")],
                                  lineas=[("Precio", _monto(p.monto_centimos, moneda)), ("Comisión Pichangol", "− " + _soles(lq.get("comision_soles") or 0, moneda))],
                                  total=("Recibes", _soles(lq.get("neto_soles") or 0, moneda)),
                                  boton=("Ver mis ventas", f"{base_url()}/anfitrion/tienda"),
                                  notas=[] if es_bono else ["El neto se libera cuando el comprador confirma que recibió el producto."],
                                  etiqueta="Aviso de pago recibido"),
                        "dueno", "venta"))
    return out


def _armar_simple(ev: dict) -> list[dict]:
    """Recarga, Pro, servicios, inscripción y aporte a torneo: solo a quien pagó."""
    p = _pago(ev.get("pago_id"))
    if p is None:
        return []
    tipo = ev["tipo"]
    email = str(p.email or p.dueno_id or "").strip().lower()
    if not _correo_valido(email):
        return []
    moneda = p.moneda or "PEN"
    if tipo in ("pro", "servicio", "torneo"):
        try:
            from pagos.router import moneda_billetera
            moneda = moneda_billetera(email) or moneda
        except Exception:  # noqa: BLE001
            pass
    concepto = p.concepto or ""
    saldo = ""
    try:
        saldo = _monto(stores.saldo_centimos(email), moneda)
    except Exception:  # noqa: BLE001
        pass
    cfg = {
        "recarga": ("✅ Recarga confirmada", "Tu recarga está confirmada", "Ya puedes usar tu saldo para reservar, pagar clases o comprar en Pichangol.",
                    ("Ver mi billetera", "/mi-billetera"), [("Saldo actual", saldo)]),
        "pro": ("👑 Pichangol Pro activo", "Tu Pichangol Pro está activo", "Pagaste tu suscripción Pro con tu saldo.",
                ("Ver Pichangol Pro", "/pro"), [("Saldo restante", saldo)]),
        "servicio": ("✅ Suscripción pagada", "Tu suscripción está pagada", "Pagaste tu servicio Pichangol.",
                     ("Ver mi billetera", "/mi-billetera"), [("Saldo restante", saldo)]),
        "torneo": ("🏆 Inscripción confirmada", "Tu inscripción al torneo está pagada", "Pagaste tu inscripción con tu saldo.",
                   ("Ver campeonatos", "/anfitrion/campeonatos"), [("Saldo restante", saldo)]),
        "aporte": ("🏆 Tu parte del equipo está pagada", "Pusiste tu parte del equipo", "Pagaste tu parte de la inscripción del equipo con tu saldo.",
                   ("Ver campeonatos", "/anfitrion/campeonatos"), [("Saldo restante", saldo)]),
    }[tipo]
    asunto, titulo, intro, (bt, ruta), extra = cfg
    return [_msg(f"{tipo}:{p.id}:cliente", email, f"{asunto} · {_monto(p.monto_centimos, moneda)}",
                 plantilla(titulo=titulo, saludo=_hola(_nombre_de(email)), intro=intro,
                           datos=[("Concepto", concepto), ("Medio de pago", _medio_txt(p.medio) or ("Saldo Pichangol" if tipo != "recarga" else "")),
                                  ("N.º de operación", str(p.culqi_charge_id or f"PCG-{p.id}"))],
                           lineas=[(concepto or titulo, _monto(p.monto_centimos, moneda))], total=("Total", _monto(p.monto_centimos, moneda)),
                           extra_montos=[x for x in extra if x[1]], boton=(bt, base_url() + ruta)),
                 "cliente", tipo)]


def _armar_torneo_ingreso(ev: dict) -> list[dict]:
    p = _pago(ev.get("pago_id"))
    if p is None:
        return []
    org = str(p.dueno_id or "").strip().lower()
    if not _correo_valido(org):
        return []
    moneda = p.moneda or "PEN"
    lq = _liq(p)
    return [_msg(f"torneo_ingreso:{p.id}:dueno", org, "🏆 Recibiste una inscripción · " + (p.concepto or "torneo")[:60],
                 plantilla(titulo="Recibiste el pago de una inscripción", saludo=_hola(_nombre_de(org)),
                           intro="Se completó un pago de inscripción a tu campeonato.", datos=[("Concepto", p.concepto or "")],
                           lineas=[("Inscripción", _monto(p.monto_centimos, moneda)), ("Comisión Pichangol", "− " + _soles(lq.get("comision_soles") or 0, moneda))],
                           total=("Recibes", _soles(lq.get("neto_soles") or 0, moneda)),
                           boton=("Ver mis campeonatos", f"{base_url()}/anfitrion/campeonatos"),
                           notas=["El neto queda “por recibir” y te lo transferimos a tu cuenta de cobro registrada."],
                           etiqueta="Aviso de pago recibido"),
                 "dueno", "torneo")]


def _armar_bodega(ev: dict) -> list[dict]:
    p = _pago(ev.get("pago_id"))
    if p is None:
        return []
    moneda = p.moneda or "PEN"
    ref = str(p.culqi_charge_id or p.id)
    deb = stores.pago_por_charge(f"{ref}_deb")
    cliente = str((deb.dueno_id if deb else "") or "").strip().lower()
    dueno = str(p.dueno_id or "").strip().lower()
    concepto = p.concepto or "Pedido de bodega"
    out = []
    if _correo_valido(cliente):
        out.append(_msg(f"bodega:{ref}:cliente", cliente, f"✅ Pedido pagado · {_monto(p.monto_centimos, moneda)}",
                        plantilla(titulo="Tu pedido de bodega está pagado", saludo=_hola(_nombre_de(cliente)),
                                  intro="Pagaste tu pedido con tu saldo Pichangol. El local te lo lleva a tu cancha.",
                                  datos=[("Pedido", concepto), ("Medio de pago", "Saldo Pichangol"), ("N.º de pedido", ref)],
                                  lineas=[(concepto, _monto(p.monto_centimos, moneda))], total=("Pagaste", _monto(p.monto_centimos, moneda)),
                                  boton=("Ver mis pedidos", f"{base_url()}/mis-pedidos-bodega"),
                                  notas=["Si el local no puede atenderlo, te devolvemos el saldo automáticamente."]),
                        "cliente", "bodega"))
    if _correo_valido(dueno):
        out.append(_msg(f"bodega:{ref}:dueno", dueno, f"🧃 Pedido pagado con saldo · {_monto(p.monto_centimos, moneda)}",
                        plantilla(titulo="Te pagaron un pedido de bodega", saludo=_hola(_nombre_de(dueno)),
                                  intro="Un cliente pagó su pedido con saldo Pichangol: entrégalo sin cobrar.",
                                  datos=[("Pedido", concepto), ("N.º de pedido", ref)],
                                  lineas=[("Pedido", _monto(p.monto_centimos, moneda)), ("Comisión Pichangol", _monto(0, moneda))],
                                  total=("Recibes", _monto(p.monto_centimos, moneda)),
                                  boton=("Ver pedidos", f"{base_url()}/anfitrion/bodega?tab=pedidos"),
                                  etiqueta="Aviso de pago recibido"),
                        "dueno", "bodega"))
    return out


def _armar_boleo(ev: dict) -> list[dict]:
    """Boleo ACEPTADO: al boleador, cuánto recibe."""
    p = _pago(ev.get("pago_id"))
    if p is None:
        return []
    bol = str(p.dueno_id or "").strip().lower()
    if not _correo_valido(bol):
        return []
    moneda = p.moneda or "PEN"
    com = int(p.comision_centimos or 0)
    return [_msg(f"boleo:{p.culqi_charge_id or p.id}:dueno", bol, "🎾 Boleo confirmado · " + (p.concepto or "")[:70],
                 plantilla(titulo="Confirmaste un boleo pagado", saludo=_hola(_nombre_de(bol)),
                           intro="El cliente ya pagó. Te transferimos tu parte cuando termine el turno.",
                           datos=[("Detalle", p.concepto or "")],
                           lineas=[("Tarifa", _monto(p.monto_centimos, moneda)), ("Comisión Pichangol", "− " + _monto(com, moneda))],
                           total=("Recibes", _monto(p.monto_centimos - com, moneda)),
                           boton=("Ver mis boleos", f"{base_url()}/anfitrion/boleador"),
                           etiqueta="Aviso de pago recibido"),
                 "dueno", "boleo")]


def _armar_boleo_solicitud(ev: dict) -> list[dict]:
    """Solicitud PAGADA al boleador (debe aceptar en el plazo)."""
    s = ev.get("datos") or {}
    bol = str(s.get("boleador_email") or "").strip().lower()
    if not _correo_valido(bol):
        return []
    moneda = s.get("moneda") or "PEN"
    monto, com = int(s.get("monto_centimos") or 0), int(s.get("comision_centimos") or 0)
    fecha = _fecha_txt(str(s.get("fecha") or ""))
    return [_msg(f"boleo_sol:{s.get('id')}:dueno", bol, f"🎾 Te contrataron · {s.get('club') or 'cancha'} · {fecha} {s.get('hora_inicio', '')}",
                 plantilla(titulo="¡Te contrataron para bolear!", saludo=_hola((s.get("data") or {}).get("boleador_nombre") or ""),
                           intro=f"{s.get('cliente_nombre') or 'Un jugador'} ya pagó tu boleo. Acéptalo desde la app o la web antes de que venza el plazo.",
                           datos=[("Local", str(s.get("club") or "")), ("Fecha", fecha),
                                  ("Horario", f"{s.get('hora_inicio', '')}–{s.get('hora_fin', '')} · {s.get('turnos') or 1} turno(s)"),
                                  ("Cliente", str(s.get("cliente_nombre") or ""))],
                           lineas=[("Tarifa", _monto(monto, moneda)), ("Comisión Pichangol", "− " + _monto(com, moneda))],
                           total=("Ganas", _monto(monto - com, moneda)),
                           boton=("Aceptar o rechazar", f"{base_url()}/anfitrion/boleador"),
                           notas=["Si no respondes a tiempo, la solicitud vence y le devolvemos su parte al cliente."],
                           etiqueta="Aviso de pago recibido"),
                 "dueno", "boleo")]


def _armar_fotos_local(ev: dict) -> list[dict]:
    """FOTOS PROPIAS DE LOS LOCALES (`propiedad/fotos_locales.py`): aviso al
    dueño para que suba las fotos de su local antes del plazo. No es un pago."""
    s = ev.get("datos") or {}
    para = str(s.get("para") or "").strip().lower()
    if not _correo_valido(para):
        return []
    from urllib.parse import quote as _q
    principal = str(s.get("principal") or "")
    enlace = f"{base_url()}/anfitrion/cancha/{_q(principal, safe='')}/editar#sec-fotos" if principal else f"{base_url()}/anfitrion/canchas"
    datos_ = [("Local", str(s.get("local") or "")),
              ("Fotos propias", f"{int(s.get('minimo') or 0) - int(s.get('faltan') or 0)} de {int(s.get('minimo') or 0)}")]
    if s.get("vence") and s.get("estado") != "vencido":
        datos_.append(("Plazo", _fecha_txt(str(s.get("vence")))))
    return [_msg(str(s.get("clave") or f"fotos_local:{para}:{ev.get('id')}"), para, str(s.get("titulo") or "Sube las fotos de tu local"),
                 plantilla(titulo=str(s.get("titulo") or "Sube las fotos de tu local"), saludo="Hola,",
                           intro=str(s.get("cuerpo") or ""), datos=datos_,
                           boton=("Subir fotos de mi local", enlace),
                           notas=["Las fotos de Google no se pueden guardar (sus términos no lo permiten): las tuyas quedan "
                                  "para siempre en tu ficha. Puedes subirlas desde la web (Modo anfitrión → Mis canchas) o "
                                  "desde la app (Mis canchas → Editar cancha)."],
                           etiqueta="Aviso de Pichangol"),
                 "dueno", "fotos_local")]


_ARMADORES = {
    "reserva": _armar_reserva, "matricula": _armar_matricula, "venta": _armar_venta,
    "recarga": _armar_simple, "pro": _armar_simple, "servicio": _armar_simple, "torneo": _armar_simple,
    "aporte": _armar_simple, "torneo_ingreso": _armar_torneo_ingreso, "bodega": _armar_bodega,
    "boleo": _armar_boleo, "boleo_solicitud": _armar_boleo_solicitud,
    "fotos_local": _armar_fotos_local,
}


# ── Envío ─────────────────────────────────────────────────────────────────────

def _enviar_resend(m: dict) -> str:
    cuerpo = {"from": remitente(), "to": [m["para"]], "subject": m["asunto"], "html": m["html"], "text": m["texto"]}
    resp = _responder_a()
    if resp:
        cuerpo["reply_to"] = resp
    req = urllib.request.Request("https://api.resend.com/emails", data=json.dumps(cuerpo).encode(), method="POST",
                                 headers={"Authorization": f"Bearer {_env('RESEND_API_KEY')}", "Content-Type": "application/json",
                                          "Idempotency-Key": m["clave"][:250],
                                          # Cloudflare (delante de la API de Resend) responde 403 «error code:
                                          # 1010» al User-Agent por defecto de urllib: hay que identificarse.
                                          "User-Agent": "Pichangol-Backend/1.0 (+https://www.pichangol.app)",
                                          "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            j = json.loads(r.read().decode() or "{}")
            return str(j.get("id") or "ok")
    except urllib.error.HTTPError as ex:
        raise RuntimeError(f"Resend {ex.code}: {ex.read().decode(errors='ignore')[:200]}") from ex


def _enviar_smtp(m: dict) -> str:
    msg = EmailMessage()
    msg["From"] = remitente()
    msg["To"] = m["para"]
    msg["Subject"] = m["asunto"]
    msg["Message-ID"] = make_msgid(domain=(parseaddr(remitente())[1].split("@")[-1] or "pichangol.app"))
    resp = _responder_a()
    if resp:
        msg["Reply-To"] = resp
    msg.set_content(m["texto"])
    msg.add_alternative(m["html"], subtype="html")
    host, puerto = _env("SMTP_HOST"), int(_env("SMTP_PORT") or "587")
    usuario, clave = _env("SMTP_USUARIO"), _env("SMTP_CLAVE")
    ctx = ssl.create_default_context()
    if puerto == 465:
        srv = smtplib.SMTP_SSL(host, puerto, context=ctx, timeout=20)
    else:
        srv = smtplib.SMTP(host, puerto, timeout=20)
        srv.starttls(context=ctx)
    try:
        if usuario:
            srv.login(usuario, clave)
        srv.send_message(msg)
    finally:
        try:
            srv.quit()
        except Exception:  # noqa: BLE001
            pass
    return str(msg["Message-ID"])


def _responder_a() -> str:
    r = _env("CORREO_RESPONDER_A")
    if r:
        return r
    try:
        import empresa
        return empresa.valores().get("empresa_correo") or ""
    except Exception:  # noqa: BLE001
        return ""


def enviar(m: dict) -> str:
    """Envía YA (sin cola). Lanza si falla. Devuelve el id del proveedor."""
    prov = proveedor()
    if prov == "resend":
        return _enviar_resend(m)
    if prov == "smtp":
        return _enviar_smtp(m)
    raise RuntimeError("sin_proveedor")


# ── Bucle ─────────────────────────────────────────────────────────────────────

def _registrar(m: dict, ahora: datetime) -> bool:
    """Agrega a la bandeja si su clave no existe. True si es nuevo."""
    band = _bandeja()
    if any(x.get("clave") == m["clave"] for x in band):
        return False
    m = dict(m, id=f"co_{int(time.time() * 1_000_000)}_{len(band)}", estado="pendiente", intentos=0,
             creado=_iso(ahora), proximo=_iso(ahora), error="", enviado_en=None, proveedor_id="")
    band.append(m)
    return True


def _recortar() -> None:
    band = _bandeja()
    if len(band) > MAX_BANDEJA:
        viejos = [x for x in band if x.get("estado") != "pendiente"]
        sobran = len(band) - MAX_BANDEJA
        quitar = {id(x) for x in viejos[:sobran]}
        stores.correos = [x for x in band if id(x) not in quitar]


def procesar(ahora: datetime | None = None, enviar_fn=None) -> dict:
    """Arma los eventos listos y envía lo pendiente. Lo llama el hilo cada ~5 s
    (y los tests a mano). Devuelve un resumen."""
    ahora = ahora or _ahora()
    enviar_fn = enviar_fn or enviar
    res = {"armados": 0, "enviados": 0, "fallidos": 0, "sin_proveedor": 0}
    with _LOCK:
        listos = [e for e in _eventos() if _de_iso(e.get("listo_en")) <= ahora]
    for ev in listos:
        fn = _ARMADORES.get(ev.get("tipo"))
        try:
            msgs = fn(ev) if fn else []
        except _NoListo:
            with _LOCK:
                ev["intentos"] = int(ev.get("intentos") or 0) + 1
                if ev["intentos"] >= MAX_ARMADO:
                    print(f"[correos] evento {ev['tipo']} {ev.get('pago_id')} sin datos tras {ev['intentos']} intentos: se descarta", flush=True)
                    _eventos().remove(ev)
                else:
                    ev["listo_en"] = _iso(ahora + timedelta(seconds=60 * ev["intentos"]))
            continue
        except Exception as ex:  # noqa: BLE001
            print(f"[correos] no se pudo armar {ev.get('tipo')} {ev.get('pago_id')}: {ex}", flush=True)
            msgs = []
        with _LOCK:
            for m in msgs:
                if _registrar(m, ahora):
                    res["armados"] += 1
            if ev in _eventos():
                _eventos().remove(ev)
    if not activo():
        return res
    with _LOCK:
        pendientes = [m for m in _bandeja() if m.get("estado") == "pendiente" and _de_iso(m.get("proximo")) <= ahora]
    prov = proveedor()
    for m in pendientes:
        if _de_iso(m.get("creado")) < ahora - timedelta(hours=VENCE_H):
            with _LOCK:
                m.update(estado="vencido", html="", texto="")
            continue
        if not prov and enviar_fn is enviar:
            with _LOCK:
                m.update(estado="sin_proveedor", error="Sin RESEND_API_KEY ni SMTP_HOST")
            res["sin_proveedor"] += 1
            print(f"[correos] sin proveedor: {m['tipo']} → {m['para']} «{m['asunto']}»", flush=True)
            continue
        try:
            pid = enviar_fn(m)
            with _LOCK:
                m.update(estado="enviado", enviado_en=_iso(_ahora()), proveedor_id=str(pid or ""), error="", html="", texto="")
            res["enviados"] += 1
            print(f"[correos] enviado {m['tipo']}/{m['rol']} → {m['para']}", flush=True)
        except Exception as ex:  # noqa: BLE001
            with _LOCK:
                m["intentos"] = int(m.get("intentos") or 0) + 1
                m["error"] = str(ex)[:300]
                if m["intentos"] > len(REINTENTOS_S):
                    m["estado"] = "fallo"
                else:
                    m["proximo"] = _iso(ahora + timedelta(seconds=REINTENTOS_S[m["intentos"] - 1]))
            res["fallidos"] += 1
            print(f"[correos] falló {m['tipo']} → {m['para']}: {ex}", flush=True)
    with _LOCK:
        _recortar()
    return res


def _bucle() -> None:
    while True:
        try:
            r = procesar()
            if any(r.values()):
                try:
                    from db import pg
                    pg.persistir_en_segundo_plano(stores)
                except Exception:  # noqa: BLE001
                    pass
        except Exception as ex:  # noqa: BLE001
            print(f"[correos] bucle: {ex}", flush=True)
        time.sleep(5)


def iniciar_hilo() -> None:
    global _HILO
    if _HILO is not None and _HILO.is_alive():
        return
    _HILO = threading.Thread(target=_bucle, name="pcg-correos", daemon=True)
    _HILO.start()


# ── Torre ─────────────────────────────────────────────────────────────────────

def resumen(limite: int = 60) -> dict:
    with _LOCK:
        band = list(_bandeja())
        n_ev = len(_eventos())
    cuenta: dict[str, int] = {}
    for m in band:
        cuenta[m.get("estado", "")] = cuenta.get(m.get("estado", ""), 0) + 1
    ult = [{k: m.get(k) for k in ("id", "clave", "para", "asunto", "rol", "tipo", "estado", "intentos", "error", "creado", "enviado_en")}
           for m in reversed(band[-limite:])]
    return {"proveedor": proveedor(), "remitente": remitente(), "responder_a": _responder_a(), "activo": activo(),
            "en_espera": n_ev, "cuenta": cuenta, "ultimos": ult}


def reintentar(correo_id: str) -> bool:
    """Vuelve a poner en cola un correo fallido/sin proveedor (si aún tiene cuerpo)."""
    with _LOCK:
        for m in _bandeja():
            if m.get("id") == correo_id and m.get("estado") in ("fallo", "sin_proveedor", "vencido"):
                if not m.get("html"):
                    return False
                m.update(estado="pendiente", intentos=0, proximo=_iso(_ahora()), error="", creado=_iso(_ahora()))
                return True
    return False


def correo_prueba(para: str) -> dict:
    if not _correo_valido(para):
        raise ValueError("Correo inválido")
    html, texto = plantilla(titulo="Correo de prueba de Pichangol", saludo="Hola,",
                            intro="Si lees esto, los correos de pago de este ambiente están funcionando.",
                            datos=[("Proveedor", proveedor() or "ninguno"), ("Remitente", remitente())],
                            lineas=[("Turno 19:00–20:00", "S/ 60.00"), ("Cargo por servicio Pichangol", "S/ 3.00")],
                            total=("Pagaste hoy", "S/ 63.00"), boton=("Ir a Pichangol", base_url()), etiqueta="Prueba")
    m = {"clave": f"prueba:{time.time()}", "para": para.strip().lower(), "asunto": "Prueba · correos de Pichangol",
         "html": html, "texto": texto, "rol": "prueba", "tipo": "prueba"}
    pid = enviar(m)
    return {"ok": True, "proveedor": proveedor(), "id": pid}
