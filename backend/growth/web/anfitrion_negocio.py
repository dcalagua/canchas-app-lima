"""PANEL DEL NEGOCIO del dueño en la web (modo anfitrión): lo que el app tiene
en "Mis canchas" más allá de Hoy/Calendario/Reservas/Ingresos/Canchas
(`web/anfitrion.py`). Cada página es ESPEJO de su pantalla Dart, sobre las
MISMAS tablas y la MISMA lógica:

  · Reportes (`reportes_hub_screen.dart`): Resumen (`reportes_screen`),
    Ocupación (`analitica_ocupacion_screen`: mapa de calor hora × día, pico,
    ocupación, no-show, ingreso por cancha, mes vs mes, reputación), Cobros
    (`reporte_canchas_screen`: rango, cobrado/por cobrar, ticket, "Cuánto vas
    a recibir de Pichangol" = `_ResumenComision`, 6 meses, por local/cancha,
    CSV) y Cancelaciones (`cancelaciones_screen`, tabla
    `pichangol_reservas_canceladas` + las canceladas desde la web).
  · Caja del día (`caja_dia_screen` + `AppState.cajaDia/cajaDiaPorMedio/
    cerrarCaja/autocerrarCajasPendientes`).
  · Clientes (`clientes_screen`: CRM derivado de las reservas, segmentos VIP /
    recurrentes / nuevos / en riesgo / deudores, ficha con perfil de consumo,
    notas privadas y WhatsApp).
  · Bonos (`bonos_dueno_screen`: packs `pichangol_bonos` y vendidos
    `pichangol_bonos_comprados`).
  · Reservas fijas (`reservas_fijas_screen` + `generarReservasFijas`): la
    serie de las próximas 4 semanas con la misma fila que la reserva manual,
    respetando ocupados, bloqueos y turnos pasados.
  · Disponibilidad (`disponibilidad_screen`, hecha REAL: abrir/cerrar turnos =
    `pichangol_bloqueos`, la misma tabla del app).
  · Cobros de academia (`cobros_screen`: por cobrar, vencido, cobrado del mes,
    quién debe, recordatorios por chat de la app o WhatsApp y cobro en
    efectivo por cuota = `marcarCuotaPagada`).
  · No-show de una reserva (`marcarNoShow`), que usa la lista de Reservas.

Lo que en el app vive solo en el teléfono (cierres de caja, reservas fijas,
notas de clientes, último recordatorio de cobro) aquí se guarda en el snapshot
del backend (`stores.negocio_web[correo]`), así el dueño lo ve igual desde
cualquier navegador.
"""

from __future__ import annotations

import csv
import io
import json
import re
import time
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote

from fastapi import APIRouter, Body, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

from db import pg
from db.store import stores
from web import datos, horarios, sesion, ui
from web.anfitrion import (JS_PAGAR, _cabecera, _contexto, _en_segundo_plano, _pais_de, _sesion_o_entrar)
from web.router import PLAY_URL, _moneda_de, e

router = APIRouter(tags=["web-anfitrion-negocio"])

DIAS_LARGO = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
DIAS_TIT = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
DIAS_CORTO = ["L", "M", "X", "J", "V", "S", "D"]
MESES_CORTO = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "set", "oct", "nov", "dic"]
MESES_LARGO = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "setiembre",
               "octubre", "noviembre", "diciembre"]

# Navegación del panel del negocio (debajo de la cabecera del modo anfitrión).
NAV = [("reportes", "📊", "Reportes", "/anfitrion/reportes"), ("caja", "🧾", "Caja del día", "/anfitrion/caja"),
       ("clientes", "👥", "Clientes", "/anfitrion/clientes"), ("bonos", "🎟️", "Bonos", "/anfitrion/bonos"),
       ("fijas", "🔁", "Reservas fijas", "/anfitrion/fijas"), ("disponibilidad", "🟢", "Disponibilidad", "/anfitrion/disponibilidad"),
       ("cobros", "💳", "Cobros de academia", "/anfitrion/cobros")]
TABS_REPORTES = [("resumen", "Resumen", "/anfitrion/reportes"), ("ocupacion", "Ocupación", "/anfitrion/ocupacion"),
                 ("cobros", "Cobros", "/anfitrion/reportes/cobros"), ("cancelaciones", "Cancelaciones", "/anfitrion/cancelaciones")]


# ── datos ────────────────────────────────────────────────────────────────────

_COLS = ["id", "cancha_id", "jugador", "nivel", "fecha", "hora_inicio", "hora_fin", "estado", "precio", "sena", "pagado",
         "usuario", "moneda", "extras", "telefono", "grupo_reserva_id", "medio_pago", "traida_por_app"]
_COLS_MIN = ["id", "cancha_id", "jugador", "fecha", "hora_inicio", "hora_fin", "estado", "precio", "sena", "pagado",
             "usuario", "moneda", "extras", "telefono", "grupo_reserva_id", "medio_pago"]


def _lista(v) -> list:
    if isinstance(v, list):
        return v
    if isinstance(v, str) and v.strip():
        try:
            x = json.loads(v)
            return x if isinstance(x, list) else []
        except ValueError:
            return []
    return []


def reservas_dueno(ids: list[str], desde: str, hasta: str) -> list[dict]:
    """Reservas de las canchas del dueño entre dos fechas (inclusive), como
    `appState.reservas` del dueño: con no-shows (estado `noShow`), sin las
    canceladas ni las retenciones web sin pagar. Trae `traida_por_app` y
    `nivel` (el CRM y la comisión los usan). Fail-safe: [] sin base."""
    if not pg.habilitado or not ids:
        return []
    filtro = ("WHERE cancha_id = ANY(%s) AND fecha BETWEEN %s AND %s "
              "AND NOT (coalesce(estado,'') = 'nueva' AND NOT coalesce(pagado,false)) "
              "AND coalesce(estado,'') <> 'cancelada' ORDER BY fecha, hora_inicio")
    for cols in (_COLS, _COLS_MIN):
        try:
            with pg.conexion() as conn, conn.cursor() as cur:
                cur.execute(f"SELECT {', '.join(cols)} FROM pichangol_reservas {filtro}", (ids, desde, hasta))
                return [_norm_res(pg._fila_a_dict(cols, f)) for f in cur.fetchall()]
        except Exception:  # noqa: BLE001
            continue
    return []


def _norm_res(d: dict) -> dict:
    d["extras"] = _lista(d.get("extras"))
    d["precio"] = int(round(float(d.get("precio") or 0)))
    d["sena"] = int(round(float(d.get("sena") or 0)))
    d["pagado"] = bool(d.get("pagado"))
    d["fecha"] = str(d.get("fecha") or "")[:10]
    d["traida_por_app"] = True if d.get("traida_por_app") is None else bool(d.get("traida_por_app"))
    for k in ("jugador", "nivel", "usuario", "telefono", "medio_pago", "estado", "hora_inicio", "hora_fin", "moneda"):
        d[k] = str(d.get(k) or "")
    return d


def total_con_extras(r: dict) -> float:
    """= `Reserva.totalConExtras` (precio + extras)."""
    ex = 0.0
    for x in r.get("extras") or []:
        if isinstance(x, dict):
            try:
                ex += float(x.get("precio") or 0)
            except (TypeError, ValueError):
                pass
    return float(r.get("precio") or 0) + ex


def es_noshow(r: dict) -> bool:
    return str(r.get("estado") or "") in ("noShow", "no_show")


def es_bono(r: dict) -> bool:
    return str(r.get("medio_pago") or "") == "bono"


def grupo_medio(r: dict) -> str:
    """= `ReservasDuenoScreen._grupoMedio`: online | efectivo | manual."""
    m = str(r.get("medio_pago") or "")
    if m in ("yape", "tarjeta", "bono"):
        return "online"
    if m in ("sena", "efectivo"):
        return "efectivo"
    if m == "manual":
        return "manual"
    if not r.get("traida_por_app", True):
        return "manual"
    return "online" if r.get("pagado") else "efectivo"


def marcar_noshow(res_id: str, cancha_ids: list[str]) -> bool:
    """= `AppState.marcarNoShow` (`estado = 'noShow'` en la misma fila)."""
    if not pg.habilitado or not res_id or not cancha_ids:
        return False
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE pichangol_reservas SET estado = 'noShow' WHERE id = %s AND cancha_id = ANY(%s)",
                        (res_id, cancha_ids))
            n = cur.rowcount
            conn.commit()
            return n == 1
    except Exception:  # noqa: BLE001
        return False


def cancelaciones_de(email: str) -> list[dict]:
    """= `CancelacionesRepo.deDueno` (más recientes primero, 200)."""
    email = (email or "").strip().lower()
    if not pg.habilitado or not email:
        return []
    cols = ["reserva_id", "cancha_id", "cancha_nombre", "local", "jugador", "usuario", "fecha", "hora_inicio", "hora_fin",
            "precio", "moneda", "pagado", "sena", "medio_pago", "cancelado_por", "cancelada_en"]
    for cs in (cols, [c for c in cols if c != "sena"]):
        try:
            with pg.conexion() as conn, conn.cursor() as cur:
                cur.execute(f"SELECT {', '.join(cs)} FROM pichangol_reservas_canceladas WHERE lower(dueno) = %s "
                            "ORDER BY cancelada_en DESC LIMIT 200", (email,))
                out = []
                for f in cur.fetchall():
                    d = pg._fila_a_dict(cs, f)
                    d["cancelada_en"] = d["cancelada_en"].isoformat() if hasattr(d.get("cancelada_en"), "isoformat") else str(d.get("cancelada_en") or "")
                    d["fecha"] = str(d.get("fecha") or "")[:10]
                    out.append(d)
                return out
        except Exception:  # noqa: BLE001
            continue
    return []


_COLS_OF = ["id", "dueno", "club", "nombre", "horas", "precio", "activo", "creado"]
_COLS_BC = ["id", "bono_id", "dueno", "club", "comprador", "comprador_nombre", "horas_total", "horas_usadas", "precio", "venta_id", "creado"]


def ofertas_de_dueno(email: str) -> list[dict]:
    """= `BonosRepo.ofertasDeDueno` (todas, activas y pausadas)."""
    if not pg.habilitado or not email:
        return []
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT {', '.join(_COLS_OF)} FROM pichangol_bonos WHERE lower(dueno) = %s ORDER BY creado DESC",
                        (email.lower(),))
            out = []
            for f in cur.fetchall():
                d = pg._fila_a_dict(_COLS_OF, f)
                d.update(horas=int(d.get("horas") or 0), precio=float(d.get("precio") or 0), activo=d.get("activo") is not False)
                out.append(d)
            return out
    except Exception:  # noqa: BLE001
        return []


def vendidos_de_dueno(email: str) -> list[dict]:
    """= `BonosRepo.comprasDeDueno`."""
    if not pg.habilitado or not email:
        return []
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT {', '.join(_COLS_BC)} FROM pichangol_bonos_comprados WHERE lower(dueno) = %s ORDER BY creado DESC",
                        (email.lower(),))
            out = []
            for f in cur.fetchall():
                d = pg._fila_a_dict(_COLS_BC, f)
                d.update(horas_total=int(d.get("horas_total") or 0), horas_usadas=int(d.get("horas_usadas") or 0),
                         precio=float(d.get("precio") or 0))
                d["saldo"] = max(0, d["horas_total"] - d["horas_usadas"])
                out.append(d)
            return out
    except Exception:  # noqa: BLE001
        return []


def guardar_oferta(fila: dict, email: str) -> bool:
    """= `BonosRepo.guardarOferta` (upsert por id); un id que ya existe a
    nombre de OTRO dueño no se pisa."""
    if not pg.habilitado:
        return False
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO pichangol_bonos (id, dueno, club, nombre, horas, precio, activo) VALUES (%s,%s,%s,%s,%s,%s,%s) "
                        "ON CONFLICT (id) DO UPDATE SET nombre = EXCLUDED.nombre, horas = EXCLUDED.horas, precio = EXCLUDED.precio, "
                        "activo = EXCLUDED.activo WHERE lower(pichangol_bonos.dueno) = %s",
                        (fila["id"], email, fila["club"], fila["nombre"], fila["horas"], fila["precio"], fila["activo"], email))
            n = cur.rowcount
            conn.commit()
            return n == 1
    except Exception:  # noqa: BLE001
        return False


def activar_oferta(oferta_id: str, email: str, activo: bool) -> bool:
    if not pg.habilitado:
        return False
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE pichangol_bonos SET activo = %s WHERE id = %s AND lower(dueno) = %s", (activo, oferta_id, email))
            n = cur.rowcount
            conn.commit()
            return n == 1
    except Exception:  # noqa: BLE001
        return False


def eliminar_oferta(oferta_id: str, email: str) -> bool:
    """= `BonosRepo.eliminarOferta` (los créditos comprados se conservan)."""
    if not pg.habilitado:
        return False
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM pichangol_bonos WHERE id = %s AND lower(dueno) = %s", (oferta_id, email))
            n = cur.rowcount
            conn.commit()
            return n == 1
    except Exception:  # noqa: BLE001
        return False


def marcar_cuota_cobrada(academia_id: str, alumno_id: str, cuota_id: str) -> dict | None:
    """`AppState.marcarCuotaPagada` hecho por el PROFE (cobro en efectivo):
    bloquea la matrícula, marca la cuota (si sigue impaga) y devuelve la cuota
    marcada. None si no se pudo (no existe, ya pagada o sin base)."""
    if not pg.habilitado:
        return None
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT data FROM pichangol_matriculas WHERE id = %s AND academia_id = %s "
                        "AND coalesce(eliminada,false) = false FOR UPDATE", (alumno_id, academia_id))
            row = cur.fetchone()
            if not row:
                conn.rollback()
                return None
            data = row[0] if isinstance(row[0], dict) else json.loads(row[0] or "{}")
            hecha = None
            for c in data.get("cuotas") or []:
                if isinstance(c, dict) and str(c.get("id") or "") == cuota_id and not c.get("pagada"):
                    c["pagada"] = True
                    c["fechaPago"] = datetime.now().isoformat()
                    hecha = dict(c)
            if hecha is None:
                conn.rollback()
                return None
            cur.execute("UPDATE pichangol_matriculas SET data = %s::jsonb, updated_at = now() WHERE id = %s",
                        (json.dumps(data), alumno_id))
            conn.commit()
            return hecha
    except Exception as ex:  # noqa: BLE001
        print(f"[cobros-web] no se pudo marcar {cuota_id} de {alumno_id}: {ex}", flush=True)
        return None


def mensaje_academia(academia_id: str, alumno_email: str, autor: str, autor_nombre: str, texto: str) -> bool:
    """`MensajesRepo.enviar` de un mensaje del PROFE en el hilo de la academia
    (`<academiaId>|<correo>`); el trigger de la base dispara el push."""
    if not pg.habilitado or not alumno_email:
        return False
    em = alumno_email.strip().lower()
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO pichangol_mensajes (id, hilo, tipo, ref_id, academia_id, cuenta_email, autor_email, autor_nombre, es_profe, texto) "
                        "VALUES (%s, %s, 'academia', %s, %s, %s, %s, %s, true, %s)",
                        (f"msg_{time.time_ns() // 1000}_w", f"{academia_id}|{em}", academia_id, academia_id, em,
                         autor.lower(), autor_nombre, texto))
            conn.commit()
            return True
    except Exception:  # noqa: BLE001
        return False


def _persistir() -> None:
    """Los GET que cambian el snapshot (auto-cierre de caja, generación de
    fijas) lo guardan fuera de la request (el middleware solo guarda tras
    POST/PUT/DELETE)."""
    try:
        pg.persistir_en_segundo_plano(stores)
    except Exception:  # noqa: BLE001
        pass


def _negocio(email: str) -> dict:
    """Lo del panel que el app guarda en el teléfono, aquí en el snapshot."""
    email = email.lower()
    d = stores.negocio_web.get(email)
    if d is None:
        d = {"fijas": [], "cierres": [], "notas": {}, "recordados": {}}
        stores.negocio_web[email] = d
    for k, v in (("fijas", []), ("cierres", []), ("notas", {}), ("recordados", {})):
        d.setdefault(k, v)
    return d


# ── utilidades de presentación ──────────────────────────────────────────────

def _monedas(canchas: list[dict]) -> list[tuple[str, str]]:
    """Monedas (ISO, símbolo) de las canchas del dueño, en orden de aparición."""
    out: list[tuple[str, str]] = []
    for c in canchas:
        sim, iso = _moneda_de(c)
        if iso not in [x[0] for x in out]:
            out.append((iso, sim))
    return out or [("PEN", "S/")]


def _por_moneda(canchas: list[dict], m: str) -> tuple[list[dict], str, str, str]:
    """Canchas de la moneda elegida (el dueño con locales en dos países ve
    cada moneda por separado: nunca se suman soles con dólares) + selector."""
    ms = _monedas(canchas)
    iso, sim = next(((i, s) for i, s in ms if i == (m or "").upper()), ms[0])
    sub = [c for c in canchas if _moneda_de(c)[1] == iso]
    chips = ""
    if len(ms) > 1:
        chips = ("<div class='chips ng-mon'>" + "".join(
            f"<a class='chip{' sel' if i == iso else ''}' href='?m={i}'>{e(s)} · {e(i)}</a>" for i, s in ms) + "</div>")
    return sub, iso, sim, chips


def _m(v: float, sim: str, dec: int = 2) -> str:
    return f"{sim} {v:,.{dec}f}".replace(",", " ")


def _nav(activo: str) -> str:
    return ("<nav class='ng-nav' aria-label='Tu negocio'>" + "".join(
        f"<a class='chip{' sel' if k == activo else ''}' href='{href}'><span>{ico}</span>{e(n)}</a>" for k, ico, n, href in NAV)
        + "</nav>")


def _tabs_rep(activo: str) -> str:
    return ("<div class='ng-tabs' role='tablist'>" + "".join(
        f"<a role='tab' class='{'sel' if k == activo else ''}' href='{href}'>{n}</a>" for k, n, href in TABS_REPORTES) + "</div>")


def _pagina(titulo: str, cuerpo: str, ses: dict, activo: str, tab: str = "") -> HTMLResponse:
    html = ("<a class='anf-back' href='/anfitrion/mis-canchas'>‹ Mis canchas</a>" + _nav(activo) + cuerpo
            + f"<style>{CSS}</style><script>{JS_TIP}</script>")
    return ui.shell(titulo, html, nav=_cabecera(tab, ses), sesion=ses, ancho=True, titulo_tab=f"{titulo} · Modo anfitrión")


def _hoy_de(canchas: list[dict]) -> datetime:
    return horarios.ahora_local(_pais_de(canchas[0]) if canchas else "PE")


def _slots(c: dict) -> list[str]:
    return horarios.slots(c.get("hora_apertura") or "07:00", c.get("hora_cierre") or "23:00", int(c.get("duracion_slot_min") or 60))


def _fecha_bonita(iso: str, hoy: date) -> str:
    try:
        d = date.fromisoformat(iso)
    except ValueError:
        return iso
    dif = (d - hoy).days
    if dif == 0:
        return "Hoy"
    if dif == 1:
        return "Mañana"
    if dif == -1:
        return "Ayer"
    return f"{horarios.DIAS[d.weekday()].lower()} {d.day} {MESES_CORTO[d.month - 1]}"


def _barras(valores: list[float], etiquetas: list[str], sim: str, titulo: str, alto: int = 150) -> str:
    """Barras verticales de UNA serie (un solo tono, esquinas redondeadas en el
    extremo del dato, anclado a la base), valor directo solo en el máximo y en
    el último, tooltip por barra y la tabla con los mismos números."""
    mx = max(valores) if valores else 0
    barras = []
    for i, (v, t) in enumerate(zip(valores, etiquetas)):
        h = 0 if mx <= 0 else max(3, round(v / mx * (alto - 22)))
        rot = v > 0 and (v == mx or i == len(valores) - 1)
        barras.append(f"<div class='ng-bar' data-tip='{e(t)} · {e(_m(v, sim))}' tabindex='0'>"
                      + (f"<small>{e(_m(v, sim, 0))}</small>" if rot else "<small></small>")
                      + f"<i style='height:{h}px'></i><span>{e(t)}</span></div>")
    tabla = "".join(f"<tr><td>{e(t)}</td><td>{e(_m(v, sim))}</td></tr>" for v, t in zip(valores, etiquetas))
    return (f"<div class='ng-barras' role='img' aria-label='{e(titulo)}' style='height:{alto + 26}px'>{''.join(barras)}</div>"
            f"<details class='ng-tabla'><summary>Ver como tabla</summary><table><tbody>{tabla}</tbody></table></details>")


def _hbarras(filas: list[tuple[str, float, str]], sim: str) -> str:
    """Barras horizontales (ingreso por cancha), normalizadas al máximo."""
    mx = max((v for _, v, _ in filas), default=0)
    return "".join(
        f"<div class='ng-hb' data-tip='{e(n)} · {e(_m(v, sim))}'><div class='ng-hb-t'><b>{e(n)}</b>{f'<small>{e(sub)}</small>' if sub else ''}"
        f"<span>{e(_m(v, sim))}</span></div><div class='ng-hb-p'><i style='width:{0 if mx <= 0 else max(2, round(v / mx * 100))}%'></i></div></div>"
        for n, v, sub in filas)


def _kpi(titulo: str, valor: str, sub: str = "", clase: str = "") -> str:
    return f"<div class='kpi {clase}'><small>{e(titulo)}</small><b>{valor}</b>{f'<small>{sub}</small>' if sub else ''}</div>"


def _json_ok(**kw) -> JSONResponse:
    return JSONResponse({"ok": True, **kw})


def _err(msg: str, status: int = 400, **kw) -> JSONResponse:
    return JSONResponse({"ok": False, "error": msg, **kw}, status_code=status)


# ── Reportes · Resumen (reportes_screen.dart) ───────────────────────────────

@router.get("/anfitrion/reportes", response_class=HTMLResponse)
def pagina_resumen(request: Request, m: str = "") -> HTMLResponse:
    ses, canchas, resp = _contexto(request, "/anfitrion/reportes")
    if resp is not None:
        return resp
    canchas, iso, sim, chips = _por_moneda(canchas, m)
    ahora = _hoy_de(canchas)
    hoy = ahora.date()
    clave = hoy.isoformat()[:7]
    ids = [c["id"] for c in canchas]
    filas = reservas_dueno(ids, (hoy - timedelta(days=40)).replace(day=1).isoformat(), (hoy + timedelta(days=62)).isoformat())
    del_mes = [r for r in filas if r["fecha"].startswith(clave) and not es_noshow(r)]
    ingreso = sum(r["precio"] for r in del_mes if r["pagado"])
    por_cobrar = sum(r["precio"] for r in del_mes if not r["pagado"])
    serie, etq = [], []
    for i in range(6, -1, -1):
        d = hoy - timedelta(days=i)
        serie.append(float(sum(r["precio"] for r in filas if r["fecha"] == d.isoformat() and r["pagado"])))
        etq.append("Hoy" if i == 0 else f"{horarios.DIAS[d.weekday()][:3]} {d.day}")
    res_hoy = sum(1 for r in filas if r["fecha"] == hoy.isoformat() and not es_noshow(r))
    slots_hoy = sum(len(_slots(c)) for c in canchas)
    pct = (res_hoy * 100) // slots_hoy if slots_hoy else 0
    cuerpo = (
        _tabs_rep("resumen") + chips
        + f"<h1 class='anf-hola'>Reportes · {MESES_LARGO[hoy.month - 1]}</h1>"
        "<p class='sub'>Tu cuaderno, en tiempo real: lo que cobras en tus canchas.</p>"
        "<div class='ng-hero'><small>Ingresos del mes (cobrado)</small>"
        f"<b>{e(_m(ingreso, sim, 0))}</b><small>Últimos 7 días</small>"
        + _barras(serie, etq, sim, "Cobrado por día, últimos 7 días") + "</div>"
        "<div class='kpis'>"
        + _kpi("Reservas del mes", str(len(del_mes)))
        + _kpi("Por cobrar del mes", e(_m(por_cobrar, sim, 0)))
        + _kpi("Ocupación de hoy", f"{pct}%", f"{res_hoy} de {slots_hoy} turnos")
        + "</div>"
        + ("" if filas else "<div class='anf-vacio' style='margin-top:16px'>Aún no hay reservas en tus canchas. "
           "Cuando lleguen, aquí verás tus números reales.</div>")
        + "<div class='kpis ng-atajos'>"
        "<a class='kpi' href='/anfitrion/ocupacion'><small>Ocupación</small><b>Mapa de calor y horas pico</b></a>"
        "<a class='kpi' href='/anfitrion/reportes/cobros'><small>Cobros</small><b>Por período, local y cancha</b></a>"
        "<a class='kpi' href='/anfitrion/ingresos'><small>Billetera</small><b>Saldo y por recibir</b></a></div>")
    return _pagina("Reportes", cuerpo, ses, "reportes")


# ── Reportes · Cobros (reporte_canchas_screen.dart) ─────────────────────────

RANGOS = [("mes", "Este mes"), ("pasado", "Mes pasado"), ("3m", "3 meses"), ("todo", "Todo")]


def _rango(r: str, hoy: date, desde: str = "", hasta: str = "") -> tuple[date, date, str]:
    def fin_mes(y, mth):
        return (date(y + (mth // 12), mth % 12 + 1, 1) - timedelta(days=1))
    if r == "custom":
        try:
            a, b = date.fromisoformat(desde), date.fromisoformat(hasta)
            if a <= b:
                return a, b, "custom"
        except ValueError:
            pass
        r = "mes"
    if r == "pasado":
        ini = (hoy.replace(day=1) - timedelta(days=1)).replace(day=1)
        return ini, fin_mes(ini.year, ini.month), r
    if r == "3m":
        y, mth = hoy.year, hoy.month - 2
        while mth <= 0:
            mth += 12
            y -= 1
        return date(y, mth, 1), fin_mes(hoy.year, hoy.month), r
    if r == "todo":
        return date(2020, 1, 1), date(hoy.year + 5, 12, 31), r
    return hoy.replace(day=1), fin_mes(hoy.year, hoy.month), "mes"


def _datos_cobros(canchas: list[dict], rango: str, desde: str, hasta: str):
    hoy = _hoy_de(canchas).date()
    a, b, rango = _rango(rango, hoy, desde, hasta)
    ids = [c["id"] for c in canchas]
    seis = date(hoy.year, hoy.month, 1)
    for _ in range(5):
        seis = (seis - timedelta(days=1)).replace(day=1)
    todas = reservas_dueno(ids, min(a, seis).isoformat(), max(b, hoy).isoformat())
    del_rango = [r for r in todas if a.isoformat() <= r["fecha"] <= b.isoformat()]
    del_rango.sort(key=lambda r: (r["fecha"], r["hora_inicio"]), reverse=True)
    return hoy, a, b, rango, todas, del_rango


def _resumen_comision(email: str, iso: str, sim: str) -> str:
    """`_ResumenComision` del app: "Cuánto vas a recibir de Pichangol", de los
    MISMOS movimientos del backend que suma la billetera en "Por recibir"
    (`pagos.router.movimientos_de`), separado por la fuente de la comisión."""
    from pagos.router import movimientos_de
    tipos = ("liquidacion_online", "liquidacion_full", "venta_producto", "inscripcion_torneo_ingreso", "liquidacion_boleador")
    rec_on = rec_sal = com_on = com_sal = 0.0
    n_on = n_sal = 0
    for mv in movimientos_de(email):
        if mv.get("tipo") not in tipos or mv.get("liquidado") or (mv.get("moneda") or "PEN") != iso:
            continue
        monto = abs(float(mv.get("monto_soles") or 0))
        com = float(mv.get("comision_soles") or 0)
        if mv["tipo"] == "liquidacion_full":
            rec_sal += monto
            com_sal += com
            n_sal += 1
        else:
            rec_on += monto
            com_on += com
            n_on += 1
    total = rec_on + rec_sal
    if total <= 0:
        return ("<div class='ng-card'><h3>Cuánto vas a recibir de Pichangol</h3><p class='sub' style='margin:0'>Nada pendiente por ahora. "
                "Cuando un jugador pague en línea, el neto aparece aquí y en tu billetera.</p></div>")
    def bloque(t, s, v):
        return f"<div class='ng-rc'><div><b>{e(t)}</b><small>{s}</small></div><span>{e(_m(v, sim))}</span></div>"
    return ("<div class='ng-card'><h3>Cuánto vas a recibir de Pichangol</h3>"
            + (bloque(f"Reservas online ({n_on})", f"La comisión ({e(_m(com_on, sim))}) se descontó del pago · recibes el neto", rec_on) if n_on else "")
            + (bloque(f"Reservas pagadas con tu saldo ({n_sal})", f"Recibes el 100% · la comisión ({e(_m(com_sal, sim))}) salió de tu billetera", rec_sal) if n_sal else "")
            + f"<div class='ng-rc tot'><b>Total por recibir</b><span>{e(_m(total, sim))}</span></div>"
            f"<p class='ng-nota'>✓ Este total es EXACTO el \"Por recibir\" de tu <a href='/anfitrion/ingresos'>billetera</a>. "
            f"Comisión total: {e(_m(com_on + com_sal, sim))} ({e(_m(com_on, sim))} del pago + {e(_m(com_sal, sim))} de tu saldo).</p></div>")


@router.get("/anfitrion/reportes/cobros", response_class=HTMLResponse)
def pagina_cobros_reporte(request: Request, r: str = "mes", desde: str = "", hasta: str = "", m: str = "") -> HTMLResponse:
    from pagos.router import comision_centimos
    ses, canchas, resp = _contexto(request, "/anfitrion/reportes/cobros")
    if resp is not None:
        return resp
    canchas, iso, sim, chips = _por_moneda(canchas, m)
    hoy, a, b, rango, todas, del_rango = _datos_cobros(canchas, r, desde, hasta)
    por_id = {c["id"]: c for c in canchas}
    facturado = por_cobrar = comision = 0.0
    n = 0
    por_cancha: dict[str, float] = {}
    for x in del_rango:
        if es_noshow(x):
            continue
        n += 1
        if es_bono(x):  # su plata ya se contó al vender el bono
            continue
        t = total_con_extras(x)
        if x["pagado"]:
            facturado += t
        else:
            por_cobrar += t
        if x.get("traida_por_app"):  # 5 % con mínimo por moneda, igual que el backend
            comision += comision_centimos(float(x["precio"]), iso) / 100.0
        por_cancha[x["cancha_id"]] = por_cancha.get(x["cancha_id"], 0) + t
    ticket = (facturado + por_cobrar) / n if n else 0
    # 6 meses cobrados (pagadas, sin no-show), como `_GraficoMeses`.
    meses, y, mth = [], hoy.year, hoy.month
    for _ in range(6):
        meses.insert(0, (y, mth))
        mth -= 1
        if mth == 0:
            mth, y = 12, y - 1
    tot6 = [sum(total_con_extras(x) for x in todas if x["pagado"] and not es_noshow(x) and x["fecha"].startswith(f"{yy:04d}-{mm:02d}"))
            for yy, mm in meses]
    # Por local → cancha.
    locales: dict[str, list] = {}
    for cid, v in sorted(por_cancha.items(), key=lambda kv: -kv[1]):
        c = por_id.get(cid) or {}
        locales.setdefault((c.get("club") or "").strip() or "Mi local", []).append((c.get("nombre") or "Cancha", v, ""))
    bloque_locales = "".join(
        f"<div class='ng-local'><div class='ng-local-h'><b>{e(loc)}</b><span>{e(_m(sum(v for _, v, _ in lst), sim))}</span></div>{_hbarras(lst, sim)}</div>"
        for loc, lst in sorted(locales.items(), key=lambda kv: -sum(v for _, v, _ in kv[1])))
    chips_r = "".join(f"<a class='chip{' sel' if k == rango else ''}' href='?r={k}&m={iso}'>{t}</a>" for k, t in RANGOS)
    txt_rango = f"{a.day} {MESES_CORTO[a.month - 1]} {a.year} – {b.day} {MESES_CORTO[b.month - 1]} {b.year}" if rango != "todo" else "Todo el historial"
    lista = "".join(_fila_reserva(x, por_id.get(x["cancha_id"]), hoy, sim) for x in del_rango[:120])
    cuerpo = (
        _tabs_rep("cobros") + chips
        + "<h1 class='anf-hola'>Reporte de cobros</h1><p class='sub'>Facturación de tus canchas por período, local y cancha.</p>"
        f"<div class='chips' style='margin-top:12px'>{chips_r}</div>"
        f"<form class='ng-custom' method='get'><input type='hidden' name='r' value='custom'><input type='hidden' name='m' value='{iso}'>"
        f"<label>Desde<input type='date' name='desde' value='{a.isoformat() if rango != 'todo' else ''}' required></label>"
        f"<label>Hasta<input type='date' name='hasta' value='{b.isoformat() if rango != 'todo' else ''}' required></label>"
        f"<button class='btn sec' type='submit'>Ver período</button></form>"
        f"<p class='sub' style='margin-top:6px'>{e(txt_rango)}</p>"
        "<div class='kpis'>" + _kpi("Cobrado", e(_m(facturado, sim, 0))) + _kpi("Por cobrar", e(_m(por_cobrar, sim, 0)))
        + _kpi("Reservas", str(n)) + _kpi("Ticket promedio por reserva", e(_m(ticket, sim)))
        + _kpi("Comisión Pichangol estimada", e(_m(comision, sim)), "5 % de las reservas que trajo la app") + "</div>"
        + _resumen_comision(ses["email"], iso, sim)
        + "<h2 class='ng-h2'>Ingresos cobrados (últimos 6 meses)</h2><div class='ng-card'>"
        + _barras(tot6, [f"{MESES_CORTO[mm - 1]} {str(yy)[2:]}" for yy, mm in meses], sim, "Cobrado por mes, últimos 6 meses") + "</div>"
        + (f"<h2 class='ng-h2'>Por local y cancha</h2>{bloque_locales}" if bloque_locales else "")
        + f"<h2 class='ng-h2'>Reservas ({n}) <small>· {sum(1 for x in del_rango if x['pagado'])} pagadas</small></h2>"
        + (f"<div class='ng-lista'>{lista}</div>" if lista else "<div class='anf-vacio'>Sin reservas en este rango.</div>")
        + (f"<p class='sub'>Se muestran las 120 más recientes. El CSV trae todas.</p>" if len(del_rango) > 120 else "")
        + f"<p style='margin-top:16px'><a class='btn' href='/anfitrion/reportes/cobros.csv?r={rango}&desde={a.isoformat()}&hasta={b.isoformat()}&m={iso}'>⬇ Descargar reporte (CSV)</a></p>")
    return _pagina("Reporte de cobros", cuerpo, ses, "reportes")


def _estado_txt(x: dict) -> str:
    if es_noshow(x):
        return "No-show"
    if es_bono(x):
        return "Bono"
    return "Pagada" if x["pagado"] else "Por cobrar"


def _fila_reserva(x: dict, c: dict | None, hoy: date, sim: str) -> str:
    est = _estado_txt(x)
    clase = {"Pagada": "ok", "Por cobrar": "warn", "No-show": "bad", "Bono": ""}.get(est, "")
    return (f"<div class='ng-fila'><div class='ng-fila-t'><b>{e(x['jugador'] or 'Jugador')}</b>"
            f"<small>{e((c or {}).get('nombre') or 'Cancha')} · {e(x['hora_inicio'])} · {e(_fecha_bonita(x['fecha'], hoy))}</small></div>"
            f"<span class='pill {clase}'>{e(est)}</span><b class='ng-monto'>{e(_m(total_con_extras(x), sim))}</b></div>")


@router.get("/anfitrion/reportes/cobros.csv")
def descargar_csv(request: Request, r: str = "mes", desde: str = "", hasta: str = "", m: str = ""):
    ses, canchas, resp = _contexto(request, "/anfitrion/reportes/cobros")
    if resp is not None:
        return resp
    canchas, iso, sim, _ = _por_moneda(canchas, m)
    hoy, a, b, rango, _t, del_rango = _datos_cobros(canchas, r, desde, hasta)
    por_id = {c["id"]: c for c in canchas}
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Fecha", "Hora", "Local", "Cancha", "Jugador", "Correo", "Medio", "Estado", f"Precio ({iso})", f"Total con extras ({iso})"])
    for x in sorted(del_rango, key=lambda z: (z["fecha"], z["hora_inicio"])):
        c = por_id.get(x["cancha_id"]) or {}
        w.writerow([x["fecha"], f"{x['hora_inicio']}-{x['hora_fin']}", c.get("club") or "", c.get("nombre") or "", x["jugador"],
                    x["usuario"], x["medio_pago"], _estado_txt(x), f"{x['precio']:.2f}", f"{total_con_extras(x):.2f}"])
    nombre = f"pichangol-cobros-{a.isoformat()}-{b.isoformat()}.csv" if rango != "todo" else "pichangol-cobros.csv"
    return Response("﻿" + buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f"attachment; filename={nombre}"})


# ── Reportes · Ocupación (analitica_ocupacion_screen.dart) ──────────────────

PERIODOS = [("d30", "30 días"), ("d90", "90 días"), ("mes", "Este mes"), ("todo", "Todo")]
RAMPA = ["#E6F4EA", "#BFE3CB", "#8DCBA3", "#52AC77", "#1E8F4E", "#0B6E3A"]  # un solo tono, claro → oscuro


def _resenas(ids: list[str]) -> list[dict]:
    if not pg.habilitado or not ids:
        return []
    for cols in (["cancha_id", "estrellas", "comentario", "autor_nombre", "creado"], ["cancha_id", "estrellas"]):
        try:
            with pg.conexion() as conn, conn.cursor() as cur:
                cur.execute(f"SELECT {', '.join(cols)} FROM pichangol_resenas WHERE cancha_id = ANY(%s) ORDER BY {cols[-1]} DESC LIMIT 300", (ids,))
                return [pg._fila_a_dict(cols, f) for f in cur.fetchall()]
        except Exception:  # noqa: BLE001
            continue
    return []


@router.get("/anfitrion/ocupacion", response_class=HTMLResponse)
def pagina_ocupacion(request: Request, p: str = "d90", m: str = "") -> HTMLResponse:
    ses, canchas, resp = _contexto(request, "/anfitrion/ocupacion")
    if resp is not None:
        return resp
    canchas, iso, sim, chips = _por_moneda(canchas, m)
    hoy = _hoy_de(canchas).date()
    ids = [c["id"] for c in canchas]
    por_id = {c["id"]: c for c in canchas}
    mias = reservas_dueno(ids, "2020-01-01", hoy.isoformat())
    p = p if p in dict(PERIODOS) else "d90"
    primera = min((r["fecha"] for r in mias if r["fecha"]), default=hoy.isoformat())
    desde = {"d30": hoy - timedelta(days=29), "d90": hoy - timedelta(days=89), "mes": hoy.replace(day=1)}.get(p) or date.fromisoformat(primera)
    dias = (hoy - desde).days + 1
    en = [r for r in mias if desde.isoformat() <= r["fecha"] <= hoy.isoformat()]
    activas = [r for r in en if not es_noshow(r)]
    noshows = len(en) - len(activas)
    horas = set()
    for c in canchas:
        horas.update(_slots(c))
    horas.update(r["hora_inicio"] for r in activas if r["hora_inicio"])
    horas_l = sorted(horas)
    celda: dict[tuple[int, str], int] = {}
    por_hora: dict[str, int] = {}
    por_dia = [0] * 7
    for r in activas:
        try:
            ds = date.fromisoformat(r["fecha"]).weekday()
        except ValueError:
            continue
        celda[(ds, r["hora_inicio"])] = celda.get((ds, r["hora_inicio"]), 0) + 1
        por_hora[r["hora_inicio"]] = por_hora.get(r["hora_inicio"], 0) + 1
        por_dia[ds] += 1
    mx = max(celda.values(), default=0)
    hora_pico = max(por_hora.items(), key=lambda kv: kv[1])[0] if por_hora else ""
    dia_pico = max(range(7), key=lambda i: por_dia[i]) if any(por_dia) else -1
    cap = sum(len(_slots(c)) for c in canchas) * dias
    ocup = round(len(activas) * 100 / cap) if cap else 0
    ns_pct = round(noshows * 100 / len(en)) if en else 0
    ing: dict[str, int] = {}
    for r in activas:
        if r["pagado"]:
            ing[r["cancha_id"]] = ing.get(r["cancha_id"], 0) + r["precio"]
    mes, pasado = hoy.isoformat()[:7], (hoy.replace(day=1) - timedelta(days=1)).isoformat()[:7]
    # Mes vs mes (independiente del período): se consultan sus fechas aunque "todo" no alcance.
    ing_mes = sum(r["precio"] for r in mias if r["fecha"].startswith(mes) and r["pagado"] and not es_noshow(r))
    ing_pas = sum(r["precio"] for r in mias if r["fecha"].startswith(pasado) and r["pagado"] and not es_noshow(r))
    var = "" if ing_pas <= 0 else f"{'▲' if ing_mes >= ing_pas else '▼'} {abs(round((ing_mes - ing_pas) * 100 / ing_pas))} % vs mes pasado"
    # Mapa de calor: filas = horas, columnas = L..D.
    cab = "<div></div>" + "".join(f"<div class='hm-d'>{d}</div>" for d in DIAS_CORTO)
    cuerpo_hm = ""
    for h in horas_l:
        cuerpo_hm += f"<div class='hm-h'>{e(h)}</div>"
        for ds in range(7):
            v = celda.get((ds, h), 0)
            nivel = 0 if v == 0 or mx == 0 else min(5, 1 + int((v / mx) * 4.999))
            fondo = "var(--gris)" if v == 0 else RAMPA[nivel]
            cuerpo_hm += (f"<div class='hm-c' style='background:{fondo}' tabindex='0' "
                          f"data-tip='{DIAS_TIT[ds]} {e(h)} · {v} reserva{'s' if v != 1 else ''}'></div>")
    leyenda = ("<div class='hm-ley'><span>Menos</span><i style='background:var(--gris)'></i>"
               + "".join(f"<i style='background:{c}'></i>" for c in RAMPA[1:]) + "<span>Más</span></div>")
    tabla_hm = "".join(f"<tr><td>{e(h)}</td>" + "".join(f"<td>{celda.get((d, h), 0)}</td>" for d in range(7)) + "</tr>" for h in horas_l)
    ing_filas = [((por_id.get(cid) or {}).get("nombre") or "Cancha", float(v), (por_id.get(cid) or {}).get("club") or "")
                 for cid, v in sorted(ing.items(), key=lambda kv: -kv[1])]
    # Reputación real (⭐ de pichangol_resenas).
    res = _resenas(ids)
    estrellas = [int(x.get("estrellas") or 0) for x in res if int(x.get("estrellas") or 0) > 0]
    prom = sum(estrellas) / len(estrellas) if estrellas else 0
    ult = [x for x in res if str(x.get("comentario") or "").strip()][:3]
    rep = ("<div class='ng-card'><h3>Tu reputación</h3>"
           + (f"<div class='ng-rep'><b>{prom:.1f}</b><span>{'★' * round(prom)}{'☆' * (5 - round(prom))}</span><small>{len(estrellas)} reseña{'s' if len(estrellas) != 1 else ''}</small></div>"
              + "".join(f"<div class='ng-resena'><b>{'★' * int(x.get('estrellas') or 0)}</b> {e(x.get('comentario'))}<small>{e(x.get('autor_nombre') or '')}</small></div>" for x in ult)
              if estrellas else "<p class='sub' style='margin:0'>Aún no tienes reseñas. Llegan cuando los jugadores califican su reserva.</p>")
           + "</div>")
    chips_p = "".join(f"<a class='chip{' sel' if k == p else ''}' href='?p={k}&m={iso}'>{t}</a>" for k, t in PERIODOS)
    cuerpo = (
        _tabs_rep("ocupacion") + chips
        + "<h1 class='anf-hola'>Ocupación</h1><p class='sub'>Cuándo se llenan tus canchas: decide precios, promos de hora valle y en qué cancha invertir.</p>"
        f"<div class='chips' style='margin-top:12px'>{chips_p}</div>"
        "<div class='kpis'>" + _kpi("Ocupación promedio", f"{ocup}%", f"{len(activas)} reservas en {dias} día{'s' if dias != 1 else ''}")
        + _kpi("Hora pico", e(hora_pico or "—"), f"{por_hora.get(hora_pico, 0)} reservas" if hora_pico else "")
        + _kpi("Día pico", e(DIAS_TIT[dia_pico] if dia_pico >= 0 else "—"), f"{por_dia[dia_pico]} reservas" if dia_pico >= 0 else "")
        + _kpi("No-show", f"{ns_pct}%", f"{noshows} de {len(en)}", "bad" if ns_pct >= 10 else "") + "</div>"
        + ("<div class='anf-vacio' style='margin-top:16px'>Sin reservas en este período. Cuando lleguen, aquí verás cuándo se llena tu local.</div>"
           if not activas else "")
        + "<h2 class='ng-h2'>Mapa de calor · hora × día</h2><div class='ng-card'>"
        + (f"<div class='hm' role='img' aria-label='Reservas por hora y día de la semana'>{cab}{cuerpo_hm}</div>{leyenda}"
           f"<details class='ng-tabla'><summary>Ver como tabla</summary><div class='tabla'><table><thead><tr><th>Hora</th>"
           + "".join(f"<th>{d}</th>" for d in DIAS_CORTO) + f"</tr></thead><tbody>{tabla_hm}</tbody></table></div></details>"
           if horas_l else "<p class='sub'>Configura el horario de tus canchas para ver el mapa.</p>")
        + "</div>"
        + (f"<h2 class='ng-h2'>Ingreso cobrado por cancha</h2><div class='ng-card'>{_hbarras(ing_filas, sim)}</div>" if ing_filas else "")
        + "<h2 class='ng-h2'>Mes vs mes</h2><div class='kpis' style='margin-top:0'>"
        + _kpi(f"{MESES_LARGO[hoy.month - 1].capitalize()} (cobrado)", e(_m(ing_mes, sim, 0)), e(var))
        + _kpi(f"{MESES_LARGO[int(pasado[5:7]) - 1].capitalize()} (cobrado)", e(_m(ing_pas, sim, 0))) + "</div>"
        + rep)
    return _pagina("Ocupación", cuerpo, ses, "reportes")


# ── Reportes · Cancelaciones (cancelaciones_screen.dart) ────────────────────

_REEMBOLSO = {"reembolsado": "Devuelto al jugador por la pasarela", "reembolsado_manual": "Devuelto al jugador (a mano)",
              "devuelto_saldo": "Devuelto al saldo del jugador", "manual": "Devolución pendiente del equipo Pichangol",
              "fallo": "Devolución pendiente del equipo Pichangol", "sin_reembolso": "Canceló tarde · sin devolución",
              "no_aplica": "Pagaba en la cancha · nadie debe nada"}


@router.get("/anfitrion/cancelaciones", response_class=HTMLResponse)
def pagina_cancelaciones(request: Request) -> HTMLResponse:
    ses, canchas, resp = _contexto(request, "/anfitrion/cancelaciones")
    if resp is not None:
        return resp
    email = ses["email"].lower()
    hoy = _hoy_de(canchas).date()
    items = []
    for c in cancelaciones_de(email):
        local, cn = str(c.get("local") or "").strip(), str(c.get("cancha_nombre") or "").strip()
        mon = str(c.get("moneda") or "S/")
        sena = float(c.get("sena") or 0)
        if c.get("pagado"):
            est, favor = "Estaba PAGADA (revisar reembolso)", True
        elif sena > 0:
            est, favor = f"Seña {mon} {sena:.0f} a tu favor · resto ya no se debe", True
        else:
            est, favor = "Sin pago de por medio · nadie debe nada", False
        items.append({"cuando": c.get("cancelada_en") or "", "jugador": c.get("jugador") or "",
                      "lugar": f"{local} · {cn}" if local and local != cn else (cn or local),
                      "fecha": c.get("fecha") or "", "hora": f"{c.get('hora_inicio') or ''}–{c.get('hora_fin') or ''}",
                      "monto": f"{mon} {float(c.get('precio') or 0):.0f}", "estado": est, "favor": favor, "quien": ""})
    ids = {c["id"] for c in canchas}
    for w in stores.cancelaciones_web:
        if (w.get("dueno") or "").lower() != email and w.get("cancha_id") not in ids:
            continue
        local, cn = str(w.get("club") or "").strip(), str(w.get("cancha") or "").strip()
        items.append({"cuando": w.get("creado_en") or "", "jugador": w.get("usuario") or "", "fecha": w.get("fecha") or "",
                      "lugar": f"{local} · {cn}" if local and local != cn else (cn or local),
                      "hora": f"{w.get('hora_inicio') or ''}–{w.get('hora_fin') or ''}",
                      "monto": f"{w.get('moneda') or 'S/'} {float(w.get('monto') or 0) / 100.0:.2f}",
                      "estado": _REEMBOLSO.get(str(w.get("reembolso") or ""), "Cancelada") + (" · tienes un ajuste pendiente" if w.get("deuda_dueno_centimos") else ""),
                      "favor": bool(w.get("pagado")), "quien": "Cancelaste tú" if w.get("cancela_anfitrion") else "Canceló el jugador"})
    items.sort(key=lambda x: str(x["cuando"]), reverse=True)

    def cuando(iso: str) -> str:
        try:
            d = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        except ValueError:
            return ""
        if d.tzinfo:
            d = d.astimezone(timezone(timedelta(hours=-5)))
        return f"{_fecha_bonita(d.date().isoformat(), hoy)} · {d.strftime('%H:%M')}"
    tarjetas = "".join(
        f"<div class='anf-res'><div class='ng-fila-t' style='display:flex;justify-content:space-between;gap:8px'><b>🚫 {e(x['jugador'] or 'Jugador')}</b>"
        f"<small>{e(cuando(x['cuando']))}</small></div>"
        f"<div class='sub' style='margin:4px 0 8px'>{e(x['lugar'])} · {e(horarios.fecha_larga(x['fecha']))} · {e(x['hora'])}"
        f"{(' · ' + e(x['quien'])) if x['quien'] else ''}</div>"
        f"<div style='display:flex;gap:8px;align-items:center;flex-wrap:wrap'><b>{e(x['monto'])}</b>"
        f"<span class='pill {'ok' if x['favor'] else 'gris'}' style='white-space:normal'>{e(x['estado'])}</span></div></div>" for x in items)
    cuerpo = (_tabs_rep("cancelaciones")
              + "<h1 class='anf-hola'>Cancelaciones</h1><p class='sub'>Reservas que se cancelaron en tus canchas y qué pasó con la plata.</p>"
              + (f"<div class='anf-grid' style='margin-top:16px'>{tarjetas}</div>" if items
                 else "<div class='anf-vacio' style='margin-top:16px'>Sin cancelaciones. 🎉</div>"))
    return _pagina("Cancelaciones", cuerpo, ses, "reportes")


# ── Caja del día (caja_dia_screen.dart) ─────────────────────────────────────

def _medio_etq(k: str, pais: str) -> str:
    return {"yape": "📱 Yape/Plin" if pais == "PE" else "📱 QR/transf.", "tarjeta": "💳 Tarjeta", "efectivo": "💵 Efectivo",
            "manual": "✍️ Manual", "sena": "🔒 Señas (online)"}.get(k, "🌐 Online")


def caja_dia(filas: list[dict], iso: str, canchas: list[dict]) -> dict:
    """= `AppState.cajaDia` + `cajaDiaPorMedio` (mismas reglas: no-show fuera,
    bono no suma plata, la seña ya es cobrada)."""
    lst = sorted([r for r in filas if r["fecha"] == iso and not es_noshow(r)], key=lambda r: r["hora_inicio"])
    cobrado = por_cobrar = 0
    medios: dict[str, int] = {}
    for r in lst:
        if es_bono(r):
            continue
        t = round(total_con_extras(r))
        if r["pagado"]:
            cobrado += t
            k = r["medio_pago"] if r["medio_pago"] in ("yape", "tarjeta", "efectivo", "manual", "sena") else ("online" if r["traida_por_app"] else "manual")
            medios[k] = medios.get(k, 0) + t
        else:
            s = max(0, min(r["sena"], t))
            cobrado += s
            por_cobrar += t - s
            if s > 0:
                medios["sena"] = medios.get("sena", 0) + s
    slots = sum(len(_slots(c)) for c in canchas)
    return {"cobrado": cobrado, "por_cobrar": por_cobrar, "reservas": len(lst), "ocupacion": (len(lst) * 100) // slots if slots else 0,
            "lista": lst, "medios": medios}


def _autocerrar(neg: dict, filas: list[dict], canchas: list[dict], iso_mon: str, ahora: datetime) -> None:
    """= `autocerrarCajasPendientes`: días ANTERIORES al corte (hoy, o ayer
    antes de las 3 a.m.) con actividad y sin cierre → foto automática."""
    corte = ahora.date() - (timedelta(days=1) if ahora.hour < 3 else timedelta(0))
    hechos = {(x.get("fecha"), x.get("moneda", "PEN")) for x in neg["cierres"]}
    for f in sorted({r["fecha"] for r in filas if not es_noshow(r)}):
        try:
            if date.fromisoformat(f) >= corte:
                continue
        except ValueError:
            continue
        if (f, iso_mon) in hechos:
            continue
        c = caja_dia(filas, f, canchas)
        neg["cierres"].insert(0, {"fecha": f, "moneda": iso_mon, "cobrado": c["cobrado"], "porCobrar": c["por_cobrar"],
                                  "reservas": c["reservas"], "cerradaEn": ahora.isoformat(), "automatico": True, "medios": c["medios"]})
    neg["cierres"] = sorted(neg["cierres"], key=lambda x: x.get("fecha", ""), reverse=True)[:400]


@router.get("/anfitrion/caja", response_class=HTMLResponse)
def pagina_caja(request: Request, fecha: str = "", m: str = "") -> HTMLResponse:
    ses, canchas, resp = _contexto(request, "/anfitrion/caja")
    if resp is not None:
        return resp
    canchas, iso_mon, sim, chips = _por_moneda(canchas, m)
    ahora = _hoy_de(canchas)
    hoy = ahora.date()
    try:
        dia = date.fromisoformat(fecha)
    except ValueError:
        dia = hoy
    ids = [c["id"] for c in canchas]
    por_id = {c["id"]: c for c in canchas}
    filas = reservas_dueno(ids, min(dia, hoy - timedelta(days=45)).isoformat(), max(dia, hoy).isoformat())
    neg = _negocio(ses["email"])
    antes = json.dumps(neg["cierres"], sort_keys=True)
    _autocerrar(neg, filas, canchas, iso_mon, ahora)
    if json.dumps(neg["cierres"], sort_keys=True) != antes:
        _persistir()
    c = caja_dia(filas, dia.isoformat(), canchas)
    pais = _pais_de(canchas[0]) if canchas else "PE"
    cierre = next((x for x in neg["cierres"] if x.get("fecha") == dia.isoformat() and x.get("moneda", "PEN") == iso_mon), None)
    medios = "".join(f"<div class='ng-rc'><div><b>{e(_medio_etq(k, pais))}</b></div><span>{e(_m(v, sim, 0))}</span></div>"
                     for k, v in sorted(c["medios"].items(), key=lambda kv: -kv[1]))
    lista = ""
    for r in c["lista"]:
        cn = por_id.get(r["cancha_id"]) or {}
        t = total_con_extras(r)
        if es_bono(r):
            acc = "<span class='pill'>Bono</span>"
        elif r["pagado"]:
            medio = r["medio_pago"]
            acc = (f"<span class='pill ok'>Pagada en línea · {e(medio)}</span>" if medio in ("yape", "tarjeta")
                   else f"<button type='button' class='btn sec mini-b' data-pagar='{e(r['id'])}' data-v='0'>↩ Marcar por cobrar</button>")
        else:
            acc = f"<button type='button' class='btn mini-b' data-pagar='{e(r['id'])}' data-v='1'>✅ Marcar pagado</button>"
        sena = (f"<small class='ng-sena'>Seña {e(sim)} {r['sena']} pagada · cobra {e(_m(t - r['sena'], sim))}</small>"
                if r["sena"] > 0 and not r["pagado"] else "")
        lista += (f"<div class='ng-fila'><div class='ng-fila-t'><b>{e(r['hora_inicio'])}–{e(r['hora_fin'])} · {e(r['jugador'] or 'Jugador')}</b>"
                  f"<small>{e(cn.get('nombre') or 'Cancha')}{'' if r['traida_por_app'] else ' · propio'}</small>{sena}</div>"
                  f"<b class='ng-monto'>{e(_m(t, sim))}</b>{acc}</div>")
    etq = _fecha_bonita(dia.isoformat(), hoy)
    if cierre:
        estado = (f"<div class='ng-cierre{' auto' if cierre.get('automatico') else ''}'><div><b>{'🤖 Cierre automático (sin confirmar)' if cierre.get('automatico') else '🔒 Caja cerrada'}</b>"
                  f"<small>Cobrado {e(_m(cierre.get('cobrado', 0), sim, 0))} · por cobrar {e(_m(cierre.get('porCobrar', 0), sim, 0))} · {cierre.get('reservas', 0)} reservas</small></div>"
                  + ("<button type='button' class='btn' data-caja='cerrar'>Confirmar arqueo</button>" if cierre.get("automatico") else "")
                  + "<button type='button' class='btn sec' data-caja='reabrir'>Reabrir</button></div>")
    else:
        estado = "<button type='button' class='btn' data-caja='cerrar'>🔒 Cerrar caja del día</button>"
    historial = "".join(
        f"<a class='ng-fila' href='/anfitrion/caja?fecha={e(x['fecha'])}&m={iso_mon}'><div class='ng-fila-t'><b>{e(horarios.fecha_larga(x['fecha']))}</b>"
        f"<small>{x.get('reservas', 0)} reservas · por cobrar {e(_m(x.get('porCobrar', 0), sim, 0))}</small></div>"
        f"<span class='pill {'gris' if x.get('automatico') else 'ok'}'>{'Automático' if x.get('automatico') else 'Confirmado'}</span>"
        f"<b class='ng-monto'>{e(_m(x.get('cobrado', 0), sim, 0))}</b></a>"
        for x in [y for y in neg["cierres"] if y.get("moneda", "PEN") == iso_mon][:20])
    cfg = {"fecha": dia.isoformat(), "m": iso_mon, "resumen": f"Cobrado: {sim} {c['cobrado']}" + "".join(
        f"\n{_medio_etq(k, pais)}: {sim} {v}" for k, v in c["medios"].items()) + f"\nPor cobrar: {sim} {c['por_cobrar']}\nReservas: {c['reservas']}"}
    cuerpo = (
        chips + "<h1 class='anf-hola'>Caja del día</h1><p class='sub'>La plata del día de un vistazo, el cobro en efectivo y el cierre de caja (arqueo).</p>"
        "<div class='ng-dia'>"
        f"<a class='ng-flecha' href='?fecha={(dia - timedelta(days=1)).isoformat()}&m={iso_mon}' aria-label='Día anterior'>‹</a>"
        f"<form method='get'><input type='hidden' name='m' value='{iso_mon}'><input type='date' name='fecha' value='{dia.isoformat()}' onchange='this.form.submit()' aria-label='Elegir día'></form>"
        f"<b>{e(etq)}</b>"
        f"<a class='ng-flecha' href='?fecha={(dia + timedelta(days=1)).isoformat()}&m={iso_mon}' aria-label='Día siguiente'>›</a>"
        + (f"<a class='chip' href='?m={iso_mon}'>Hoy</a>" if dia != hoy else "") + "</div>"
        "<div class='kpis'>" + _kpi("Cobrado", e(_m(c["cobrado"], sim, 0)), "", "ok") + _kpi("Por cobrar", e(_m(c["por_cobrar"], sim, 0)))
        + _kpi("Reservas", str(c["reservas"])) + _kpi("Ocupación", f"{c['ocupacion']}%") + "</div>"
        + (f"<div class='ng-card'><h3>Por dónde entró la plata</h3>{medios}</div>" if medios else "")
        + f"<div class='ng-cierre-box'>{estado}</div>"
        "<h2 class='ng-h2'>Reservas del día</h2>"
        + (f"<div class='ng-lista'>{lista}</div>" if lista else "<div class='anf-vacio'>No hay reservas este día.</div>")
        + (f"<h2 class='ng-h2'>Cierres anteriores</h2><div class='ng-lista'>{historial}</div>" if historial else "")
        + f"<script>window.__caja={json.dumps(cfg, ensure_ascii=False)};{JS_PAGAR}{JS_CAJA}</script>")
    return _pagina("Caja del día", cuerpo, ses, "caja")


@router.post("/anfitrion/caja/cerrar")
def cerrar_caja(request: Request, body: dict = Body(default_factory=dict)) -> JSONResponse:
    ses = sesion.de_request(request)
    if not ses:
        return _err("sesion_requerida", 401)
    canchas = datos.canchas_de_dueno(ses["email"])
    if not canchas:
        return _err("No tienes canchas a tu nombre.", 404)
    canchas, iso_mon, sim, _ = _por_moneda(canchas, str(body.get("m") or ""))
    try:
        dia = date.fromisoformat(str(body.get("fecha") or ""))
    except ValueError:
        return _err("Fecha inválida.")
    filas = reservas_dueno([c["id"] for c in canchas], dia.isoformat(), dia.isoformat())
    c = caja_dia(filas, dia.isoformat(), canchas)
    neg = _negocio(ses["email"])
    neg["cierres"] = [x for x in neg["cierres"] if not (x.get("fecha") == dia.isoformat() and x.get("moneda", "PEN") == iso_mon)]
    neg["cierres"].insert(0, {"fecha": dia.isoformat(), "moneda": iso_mon, "cobrado": c["cobrado"], "porCobrar": c["por_cobrar"],
                              "reservas": c["reservas"], "cerradaEn": datetime.now(timezone.utc).isoformat(), "automatico": False,
                              "medios": c["medios"]})
    neg["cierres"] = sorted(neg["cierres"], key=lambda x: x.get("fecha", ""), reverse=True)[:400]
    return _json_ok(cobrado=c["cobrado"], simbolo=sim)


@router.post("/anfitrion/caja/reabrir")
def reabrir_caja(request: Request, body: dict = Body(default_factory=dict)) -> JSONResponse:
    ses = sesion.de_request(request)
    if not ses:
        return _err("sesion_requerida", 401)
    iso_mon = str(body.get("m") or "PEN").upper()
    f = str(body.get("fecha") or "")
    neg = _negocio(ses["email"])
    neg["cierres"] = [x for x in neg["cierres"] if not (x.get("fecha") == f and x.get("moneda", "PEN") == iso_mon)]
    return _json_ok()


# ── No-show (reservas_dueno_screen.dart) ────────────────────────────────────

@router.post("/anfitrion/reserva/{res_id}/noshow")
def reserva_noshow(request: Request, res_id: str) -> JSONResponse:
    """El jugador no vino: `marcarNoShow` (no ocupa, no suma plata; si pagó seña
    queda a favor del dueño). Solo en reservas de SUS canchas que no se pagaron
    en línea (lo pagado en línea se resuelve con la política de cancelación)."""
    ses = sesion.de_request(request)
    if not ses:
        return _err("sesion_requerida", 401)
    ids = [c["id"] for c in datos.canchas_de_dueno(ses["email"])]
    if not ids:
        return _err("Esta reserva no es de tus canchas.", 404)
    fila = next((r for r in reservas_dueno(ids, "2020-01-01", "2100-01-01") if r["id"] == res_id), None)
    if fila is None:
        return _err("Esta reserva no es de tus canchas.", 404)
    if fila["pagado"] and fila["medio_pago"] in ("yape", "tarjeta"):
        return _err("Esta reserva se pagó en línea: no se marca como no-show.", 409)
    if not marcar_noshow(res_id, ids):
        return _err("No pudimos guardar en este momento.", 503)
    print(f"[noshow-web] {ses['email']} marcó no-show {res_id}", flush=True)
    return _json_ok()


# ── Clientes (clientes_screen.dart) ─────────────────────────────────────────

SEGMENTOS = [("todos", "Todos"), ("vip", "VIP"), ("recurrente", "Recurrentes"), ("nuevo", "Nuevos"),
             ("riesgo", "En riesgo"), ("moroso", "Deudores")]
SEG_COLOR = {"vip": "#B8860B", "recurrente": "#0B8A3E", "nuevo": "#2F6FDE", "riesgo": "#C0392B", "moroso": "#946200"}
DIAS_RIESGO = 30
MEDIOS_LABEL = {"yape": "Yape", "tarjeta": "Tarjeta", "efectivo": "Efectivo", "sena": "Seña + saldo", "manual": "Manual", "online": "Online", "bono": "Bono"}


def clientes_de(filas: list[dict], hoy: date) -> list[dict]:
    """= `_ClientesScreenState._clientes`: una ficha por correo (o por nombre si
    es cliente de mostrador) con reservas, gastado, por cobrar, no-shows,
    primera y última visita, y sus segmentos."""
    mapa: dict[str, dict] = {}
    for r in filas:
        email = r["usuario"].strip().lower()
        nombre = r["jugador"].strip()
        if not email and not nombre:
            continue
        clave = email or f"n:{nombre.lower()}"
        cl = mapa.setdefault(clave, {"clave": clave, "email": email, "nombre": "", "telefono": "", "nivel": "", "moneda": "",
                                     "reservas": 0, "gastado": 0.0, "por_cobrar": 0.0, "noshows": 0, "ultima": "", "primera": "", "filas": []})
        if not cl["nombre"] and nombre:
            cl["nombre"] = nombre
        if not cl["telefono"] and r["telefono"]:
            cl["telefono"] = r["telefono"]
        if r.get("nivel"):
            cl["nivel"] = r["nivel"]
        cl["reservas"] += 1
        if es_noshow(r):
            cl["noshows"] += 1
        elif r["pagado"]:
            cl["gastado"] += total_con_extras(r)
        else:
            cl["por_cobrar"] += total_con_extras(r)
        if r["fecha"]:
            cl["ultima"] = max(cl["ultima"], r["fecha"]) if cl["ultima"] else r["fecha"]
            cl["primera"] = min(cl["primera"], r["fecha"]) if cl["primera"] else r["fecha"]
        cl["filas"].append(r)
    lista = list(mapa.values())
    mx = max((c["gastado"] for c in lista), default=0)
    mes = hoy.isoformat()[:7]
    for c in lista:
        c["visible"] = c["nombre"] or (c["email"].split("@")[0] if c["email"] else "Cliente")
        try:
            dias = (hoy - date.fromisoformat(c["ultima"])).days if c["ultima"] else 1 << 30
        except ValueError:
            dias = 1 << 30
        c["dias"] = dias
        s = set()
        if c["reservas"] >= 2:
            s.add("recurrente")
        if c["primera"].startswith(mes):
            s.add("nuevo")
        if c["reservas"] >= 3 and mx > 0 and c["gastado"] >= 0.6 * mx:
            s.add("vip")
        if c["por_cobrar"] > 0:
            s.add("moroso")
        if c["reservas"] >= 2 and dias >= DIAS_RIESGO:
            s.add("riesgo")
        c["segmentos"] = s
        c["badge"] = next((k for k in ("moroso", "riesgo", "vip", "nuevo") if k in s), "")
    return lista


def _moda(vals) -> str:
    cnt: dict[str, int] = {}
    for v in vals:
        if str(v).strip():
            cnt[v] = cnt.get(v, 0) + 1
    return max(cnt.items(), key=lambda kv: kv[1])[0] if cnt else ""


def _wa(tel: str) -> str:
    return "".join(ch for ch in tel if ch.isdigit())


@router.get("/anfitrion/clientes", response_class=HTMLResponse)
def pagina_clientes(request: Request, seg: str = "todos", orden: str = "frecuentes", m: str = "") -> HTMLResponse:
    from web.jugador_liga import avatar, perfiles
    ses, canchas, resp = _contexto(request, "/anfitrion/clientes")
    if resp is not None:
        return resp
    canchas, iso_mon, sim, chips_m = _por_moneda(canchas, m)
    hoy = _hoy_de(canchas).date()
    por_id = {c["id"]: c for c in canchas}
    filas = reservas_dueno(list(por_id), "2020-01-01", (hoy + timedelta(days=180)).isoformat())
    todos = clientes_de(filas, hoy)
    fotos = perfiles([c["email"] for c in todos if c["email"]])
    notas = _negocio(ses["email"])["notas"]
    seg = seg if seg in dict(SEGMENTOS) else "todos"
    orden = orden if orden in ("frecuentes", "gasto", "recientes") else "frecuentes"
    lista = [c for c in todos if seg == "todos" or seg in c["segmentos"]]
    if orden == "gasto":
        lista.sort(key=lambda c: -c["gastado"])
    elif orden == "recientes":
        lista.sort(key=lambda c: c["ultima"], reverse=True)
    else:
        lista.sort(key=lambda c: (-c["reservas"], -c["gastado"]))
    recurrentes = sum(1 for c in todos if "recurrente" in c["segmentos"])
    nuevos = sum(1 for c in todos if "nuevo" in c["segmentos"])
    chips_seg = "".join(
        f"<a class='chip{' sel' if k == seg else ''}' href='?seg={k}&orden={orden}&m={iso_mon}'>{e(t)} · "
        f"{len(todos) if k == 'todos' else sum(1 for c in todos if k in c['segmentos'])}</a>" for k, t in SEGMENTOS)
    chips_ord = "".join(f"<a class='chip{' sel' if k == orden else ''}' href='?seg={seg}&orden={k}&m={iso_mon}'>{t}</a>"
                        for k, t in (("frecuentes", "Frecuentes"), ("gasto", "Mayor gasto"), ("recientes", "Recientes")))
    tarjetas, fichas = "", {}
    for i, c in enumerate(lista):
        p = fotos.get(c["email"]) or {}
        nom = c["visible"]
        contacto = c["email"] or c["telefono"] or "Cliente de mostrador"
        badge = (f"<span class='ng-badge' style='background:{SEG_COLOR[c['badge']]}'>{e(dict(SEGMENTOS)[c['badge']])}</span>" if c["badge"] else "")
        ult = _fecha_bonita(c["ultima"], hoy) if c["ultima"] else "—"
        tarjetas += (f"<button type='button' class='ng-cli' data-cli='{i}' data-q='{e((nom + ' ' + c['email']).lower())}'>{badge}"
                     f"<div class='ng-cli-h'>{avatar(nom, p.get('foto_url') or '', 'ng-av')}<div style='min-width:0'><b>{e(nom)}</b>"
                     f"<small>{e(contacto)}{(' · ' + e(c['nivel'])) if c['nivel'] else ''}</small></div></div>"
                     f"<div class='ng-cli-d'><span><b>{c['reservas']}</b>reservas</span><span><b>{e(_m(c['gastado'], sim, 0))}</b>gastado</span>"
                     f"<span><b>{e(ult)}</b>última vez</span></div>"
                     + (f"<div class='ng-debe'>Debe {e(_m(c['por_cobrar'], sim))}</div>" if c["por_cobrar"] > 0 else "")
                     + "</button>")
        suyas = sorted(c["filas"], key=lambda r: r["fecha"], reverse=True)
        pagadas = [r for r in suyas if r["pagado"]]
        ticket = sum(total_con_extras(r) for r in pagadas) / len(pagadas) if pagadas else 0
        fichas[i] = {
            "nombre": nom, "contacto": contacto, "foto": p.get("foto_url") or "", "clave": c["clave"], "nota": notas.get(c["clave"], ""),
            "wa": _wa(c["telefono"]), "debe": round(c["por_cobrar"], 2), "moneda": sim,
            "datos": [["Ticket promedio", _m(ticket, sim)], ["Cancha favorita", _moda((por_id.get(r["cancha_id"]) or {}).get("nombre", "") for r in suyas) or "—"],
                      ["Horario favorito", _moda(r["hora_inicio"] for r in suyas) or "—"],
                      ["Paga con", MEDIOS_LABEL.get(_moda(r["medio_pago"] for r in suyas), "—")],
                      ["No-show", f"{round(c['noshows'] * 100 / c['reservas']) if c['reservas'] else 0}%"], ["Reservas", str(c["reservas"])]],
            "historial": [[_fecha_bonita(r["fecha"], hoy), r["hora_inicio"], (por_id.get(r["cancha_id"]) or {}).get("nombre", ""),
                           _estado_txt(r), _m(total_con_extras(r), sim)] for r in suyas[:30]]}
    cuerpo = (
        chips_m + "<h1 class='anf-hola'>Base de clientes</h1><p class='sub'>Quién reserva en tus canchas, cuánto gastó, cuándo volvió y quién te debe. "
        "Sale de tus reservas reales.</p>"
        "<div class='kpis'>" + _kpi("Clientes", str(len(todos))) + _kpi("Recurrentes", str(recurrentes)) + _kpi("Nuevos este mes", str(nuevos)) + "</div>"
        f"<div class='chips' style='margin-top:16px'>{chips_seg}</div>"
        "<div class='ng-busca'><input type='search' id='qCli' placeholder='Buscar cliente por nombre o correo…' aria-label='Buscar cliente'>"
        f"<div class='chips'>{chips_ord}</div></div>"
        + (f"<div class='ng-clis' id='listaCli'>{tarjetas}</div><div class='anf-vacio' id='cliVacio' style='display:none'>Ningún cliente coincide con tu búsqueda.</div>"
           if lista else "<div class='anf-vacio' style='margin-top:14px'>" + ("Aún no tienes clientes: aparecen cuando alguien reserva en tus canchas."
                                                                               if not todos else "Nadie en este segmento por ahora.") + "</div>")
        + f"<script>window.__cli={json.dumps(fichas, ensure_ascii=False)};{JS_CLIENTES}</script>")
    return _pagina("Clientes", cuerpo, ses, "clientes")


@router.post("/anfitrion/clientes/nota")
def guardar_nota(request: Request, body: dict = Body(default_factory=dict)) -> JSONResponse:
    """Notas privadas del dueño sobre un cliente (solo él las ve)."""
    ses = sesion.de_request(request)
    if not ses:
        return _err("sesion_requerida", 401)
    clave = str(body.get("clave") or "").strip().lower()[:160]
    texto = re.sub(r"[ \t]+", " ", str(body.get("texto") or "")).strip()[:600]
    if not clave:
        return _err("Cliente inválido.")
    notas = _negocio(ses["email"])["notas"]
    if texto:
        notas[clave] = texto
    else:
        notas.pop(clave, None)
    return _json_ok()


# ── Bonos (bonos_dueno_screen.dart) ─────────────────────────────────────────

def _locales(canchas: list[dict]) -> list[tuple[str, str]]:
    """(club, símbolo de moneda) de los locales del dueño."""
    out: list[tuple[str, str]] = []
    for c in canchas:
        club = (c.get("club") or "").strip() or (c.get("nombre") or "").strip()
        if club and club not in [x[0] for x in out]:
            out.append((club, _moneda_de(c)[0]))
    return out


@router.get("/anfitrion/bonos", response_class=HTMLResponse)
def pagina_bonos(request: Request, local: str = "") -> HTMLResponse:
    ses, canchas, resp = _contexto(request, "/anfitrion/bonos")
    if resp is not None:
        return resp
    locs = _locales(canchas)
    club, sim = next(((c, s) for c, s in locs if c == local), locs[0] if locs else ("", "S/"))
    email = ses["email"].lower()
    bonos = [b for b in ofertas_de_dueno(email) if b["club"] == club]
    vend = [v for v in vendidos_de_dueno(email) if v["club"] == club]
    chips = ("<div class='chips' style='margin-top:12px'>" + "".join(
        f"<a class='chip{' sel' if c == club else ''}' href='?local={quote(c)}'>{e(c)}</a>" for c, _ in locs) + "</div>") if len(locs) > 1 else ""
    tarj = "".join(
        f"<div class='ng-bono{'' if b['activo'] else ' pausa'}' data-bono='{e(json.dumps({'id': b['id'], 'nombre': b['nombre'], 'horas': b['horas'], 'precio': b['precio']}))}'>"
        f"<div class='ng-bono-h'>{b['horas']}h</div><div style='min-width:0;flex:1'><b>{e(b['nombre'] or str(b['horas']) + ' horas')}</b>"
        f"<small>{e(_m(b['precio'], sim))} · {e(_m(b['precio'] / b['horas'] if b['horas'] else b['precio'], sim))}/hora</small>"
        f"<span class='pill {'ok' if b['activo'] else 'gris'}'>{'A la venta' if b['activo'] else 'Pausado'}</span></div>"
        "<div class='ng-bono-a'><button type='button' class='btn sec mini-b' data-acc='editar'>Editar</button>"
        f"<button type='button' class='btn sec mini-b' data-acc='activo' data-v='{0 if b['activo'] else 1}'>{'Pausar' if b['activo'] else 'Reanudar'}</button>"
        "<button type='button' class='btn sec mini-b' data-acc='eliminar'>Retirar</button></div></div>" for b in bonos)
    total = sum(v["precio"] for v in vend)
    hv, hu = sum(v["horas_total"] for v in vend), sum(v["horas_usadas"] for v in vend)
    vendidos = "".join(
        f"<div class='ng-fila'><div class='ng-fila-t'><b>{e(v['comprador_nombre'] or v['comprador'].split('@')[0] or 'Jugador')}</b>"
        f"<small>{e(_m(v['precio'], sim))} · le quedan {v['saldo']} de {v['horas_total']} h</small></div><b class='ng-monto'>{v['saldo']} h</b></div>"
        for v in vend)
    cuerpo = (
        f"<h1 class='anf-hola'>Bonos · {e(club)}</h1><p class='sub'>Vende packs de horas con descuento. El jugador paga por adelantado y descuenta "
        "1 hora al reservar en tu local.</p>" + chips
        + "<p style='margin-top:14px'><button type='button' class='btn' id='nuevoBono'>＋ Nuevo bono</button></p>"
        + (f"<div class='ng-bonos'>{tarj}</div>" if tarj else
           "<div class='anf-vacio' style='margin-top:14px'>🎟️ Aún no tienes bonos. Crea packs de horas con descuento para fidelizar y cobrar por adelantado.</div>")
        + ("<h2 class='ng-h2'>Bonos vendidos</h2><p class='sub'>Esta plata ya entró a tu billetera (\"por recibir\") al venderse. Cuando el jugador reserva con su "
           "bono, NO vuelve a pagarte: descuenta de estas horas.</p>"
           f"<div class='kpis'>{_kpi('Vendido', e(_m(total, sim)))}{_kpi('Horas usadas', f'{hu} / {hv}')}</div><div class='ng-lista' style='margin-top:12px'>{vendidos}</div>"
           if vend else "")
        + f"<script>window.__bonos={json.dumps({'club': club, 'moneda': sim}, ensure_ascii=False)};{JS_BONOS}</script>")
    return _pagina("Bonos", cuerpo, ses, "bonos")


@router.post("/anfitrion/bonos/guardar")
def guardar_bono(request: Request, body: dict = Body(default_factory=dict)) -> JSONResponse:
    ses = sesion.de_request(request)
    if not ses:
        return _err("sesion_requerida", 401)
    email = ses["email"].lower()
    club = str(body.get("club") or "").strip()
    if club not in [c for c, _ in _locales(datos.canchas_de_dueno(email))]:
        return _err("Ese local no está a tu nombre.", 404)
    try:
        horas = int(body.get("horas") or 0)
        precio = round(float(str(body.get("precio") or "0").replace(",", ".")), 2)
    except (TypeError, ValueError):
        return _err("Pon una cantidad de horas y un precio válidos.")
    if horas <= 0 or horas > 200 or precio <= 0 or precio > 100000:
        return _err("Pon una cantidad de horas y un precio válidos.")
    nombre = re.sub(r"\s+", " ", str(body.get("nombre") or "")).strip()[:60]
    bid = str(body.get("id") or "").strip()
    existentes = {b["id"]: b for b in ofertas_de_dueno(email)}
    if bid and bid not in existentes:
        return _err("Ese bono no es tuyo.", 404)
    fila = {"id": bid or f"bof_{int(time.time() * 1000)}", "club": club, "nombre": nombre, "horas": horas, "precio": precio,
            "activo": existentes[bid]["activo"] if bid else True}
    if not guardar_oferta(fila, email):
        return _err("No se pudo guardar. Reintenta.", 503)
    return _json_ok(id=fila["id"])


@router.post("/anfitrion/bonos/{bono_id}/activo")
def activar_bono(request: Request, bono_id: str, body: dict = Body(default_factory=dict)) -> JSONResponse:
    ses = sesion.de_request(request)
    if not ses:
        return _err("sesion_requerida", 401)
    if not activar_oferta(bono_id, ses["email"].lower(), bool(body.get("activo"))):
        return _err("Ese bono no es tuyo.", 404)
    return _json_ok()


@router.post("/anfitrion/bonos/{bono_id}/eliminar")
def eliminar_bono(request: Request, bono_id: str) -> JSONResponse:
    ses = sesion.de_request(request)
    if not ses:
        return _err("sesion_requerida", 401)
    if not eliminar_oferta(bono_id, ses["email"].lower()):
        return _err("Ese bono no es tuyo.", 404)
    return _json_ok()


# ── Reservas fijas (reservas_fijas_screen.dart) ─────────────────────────────

def generar_fijas(email: str, canchas: list[dict], semanas: int = 4, solo: str = "") -> dict:
    """= `AppState.generarReservasFijas`: para cada fija ACTIVA, las próximas
    [semanas] ocurrencias como RESERVA MANUAL (misma fila que
    `agregarReservaManual`). Mejoras de producción sobre el app: respeta los
    BLOQUEOS del dueño y los turnos que ya pasaron, y recuerda las fechas que
    ya generó (si el dueño quita una a mano, no reaparece). Devuelve el conteo."""
    neg = _negocio(email)
    por_id = {c["id"]: c for c in canchas}
    creadas, omitidas = 0, []
    for f in neg["fijas"]:
        if not f.get("activo", True) or (solo and f.get("id") != solo):
            continue
        c = por_id.get(f.get("canchaId"))
        if c is None:
            continue
        hora = str(f.get("hora") or "")
        if hora not in _slots(c):
            omitidas.append("hora fuera del horario")
            continue
        ahora = horarios.ahora_local(_pais_de(c))
        hoy = ahora.date()
        delta = (int(f.get("diaSemana") or 1) - 1 - hoy.weekday()) % 7
        hechas = set(f.get("hechas") or [])
        nuevas_para_push = []
        for w in range(semanas):
            base = (hoy + timedelta(days=delta + 7 * w)).isoformat()
            if base in hechas:
                continue
            fr = horarios.fecha_real(base, c["hora_apertura"], c["hora_cierre"], hora)
            mins = horarios.hora_en_minutos(hora) or 0
            if fr < hoy.isoformat() or (fr == hoy.isoformat() and mins < ahora.hour * 60 + ahora.minute):
                continue
            if (fr, hora) in datos.ocupados(c["id"], [fr]):
                omitidas.append(f"{horarios.fecha_larga(fr)} ocupado o bloqueado")
                hechas.add(base)
                continue
            paso = int(c.get("duracion_slot_min") or 60)
            precio = horarios.precio_turno_de(c, hora, datos.descuentos(c["id"], [fr]).get((fr, hora), 0))
            fila = {"id": f"man_{int(time.time() * 1000)}_f{w}", "cancha_id": c["id"], "jugador": f.get("clienteNombre") or "Cliente",
                    "nivel": "", "fecha": fr, "dia": horarios.etiqueta_dia(fr, hoy), "hora_inicio": hora,
                    "hora_fin": horarios.hora_fin(hora, paso), "estado": "confirmada", "traida_por_app": False, "precio": precio,
                    "sena": 0, "pagado": False, "usuario": f.get("clienteEmail") or "", "deporte": c.get("deporte") or "",
                    "moneda": _moneda_de(c)[0], "extras": [], "telefono": f.get("clienteTelefono") or "",
                    "grupo_reserva_id": "", "medio_pago": "manual"}
            r = datos.insertar_reservas([fila])
            if r == "ocupado":
                omitidas.append(f"{horarios.fecha_larga(fr)} ocupado")
                hechas.add(base)
                continue
            if r:
                continue  # error de base: se reintenta la próxima vez
            hechas.add(base)
            creadas += 1
            nuevas_para_push.append(fr)
        f["hechas"] = sorted(hechas)[-40:]
        if nuevas_para_push and f.get("clienteEmail"):
            from pagos import router as pr
            lugar = (c.get("club") or "").strip() or c.get("nombre") or "Tu cancha"
            _en_segundo_plano(pr._aviso_push_usuario, f["clienteEmail"], "Turno fijo reservado 🔁",
                              f"{lugar} te reservó {len(nuevas_para_push)} fecha{'s' if len(nuevas_para_push) != 1 else ''}: "
                              f"{DIAS_LARGO[int(f.get('diaSemana') or 1) - 1]} {hora}. ¡Te esperamos!", "reserva_manual")
    return {"creadas": creadas, "omitidas": omitidas}


@router.get("/anfitrion/fijas", response_class=HTMLResponse)
def pagina_fijas(request: Request) -> HTMLResponse:
    ses, canchas, resp = _contexto(request, "/anfitrion/fijas")
    if resp is not None:
        return resp
    res = generar_fijas(ses["email"], canchas)  # como el app: al abrir el panel, se completan las próximas semanas
    _persistir()
    neg = _negocio(ses["email"])
    por_id = {c["id"]: c for c in canchas}

    def nom(cid):
        c = por_id.get(cid) or {}
        return f"{c['club']} · {c['nombre']}" if c.get("club") and c.get("club") != c.get("nombre") else (c.get("nombre") or "Cancha")
    filas = "".join(
        f"<div class='ng-fila{'' if f.get('activo', True) else ' pausa'}' data-fija='{e(f['id'])}'><span class='ng-ico'>🔁</span>"
        f"<div class='ng-fila-t'><b>{e(f.get('clienteNombre') or 'Cliente')}</b>"
        f"<small>{DIAS_TIT[int(f.get('diaSemana') or 1) - 1]} · {e(f.get('hora'))} · {e(nom(f.get('canchaId')))}"
        f"{(' · ' + e(f['clienteTelefono'])) if f.get('clienteTelefono') else ''}</small></div>"
        f"<label class='ng-sw' title='{'Activa' if f.get('activo', True) else 'Pausada'}'><input type='checkbox' data-acc='activo' {'checked' if f.get('activo', True) else ''}><i></i></label>"
        "<button type='button' class='btn sec mini-b' data-acc='quitar' aria-label='Quitar'>Quitar</button></div>"
        for f in neg["fijas"] if f.get("canchaId") in por_id)
    cfg = {"canchas": [{"id": c["id"], "nombre": nom(c["id"]), "slots": _slots(c)} for c in canchas],
           "hoy": _hoy_de(canchas).date().weekday() + 1}
    aviso = (f"<div class='ng-ok'>✅ Se crearon {res['creadas']} reserva{'s' if res['creadas'] != 1 else ''} de tus clientes fijos para las próximas semanas.</div>"
             if res["creadas"] else "")
    cuerpo = (
        "<h1 class='anf-hola'>Reservas fijas</h1><p class='sub'>Tus pensionados: el equipo que juega siempre el mismo día y hora. "
        "Se crean solas sus reservas de las próximas 4 semanas (respetando lo ocupado y tus bloqueos).</p>" + aviso
        + "<p style='margin-top:14px'><button type='button' class='btn' id='nuevaFija'>＋ Cliente fijo</button></p>"
        + (f"<div class='ng-lista'>{filas}</div>" if filas else "<div class='anf-vacio' style='margin-top:14px'>🔁 Aún no tienes clientes fijos.</div>")
        + f"<script>window.__fijas={json.dumps(cfg, ensure_ascii=False)};{JS_FIJAS}</script>")
    return _pagina("Reservas fijas", cuerpo, ses, "fijas")


@router.post("/anfitrion/fijas/nueva")
def nueva_fija(request: Request, body: dict = Body(default_factory=dict)) -> JSONResponse:
    ses = sesion.de_request(request)
    if not ses:
        return _err("sesion_requerida", 401)
    canchas = datos.canchas_de_dueno(ses["email"])
    c = next((x for x in canchas if x["id"] == str(body.get("cancha_id") or "")), None)
    if c is None:
        return _err("Esta cancha no está a tu nombre.", 404)
    try:
        dia = int(body.get("dia") or 0)
    except (TypeError, ValueError):
        dia = 0
    if not 1 <= dia <= 7:
        return _err("Elige el día de la semana.")
    hora = str(body.get("hora") or "")
    if hora not in _slots(c):
        return _err("Elige la hora.")
    nombre = re.sub(r"\s+", " ", str(body.get("nombre") or "")).strip()[:80]
    if not nombre:
        return _err("Escribe el nombre del cliente.")
    tel = re.sub(r"[^\d+ ]", "", str(body.get("telefono") or "")).strip()[:20]
    correo = str(body.get("email") or "").strip().lower()[:120]
    if correo and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", correo):
        return _err("El correo del cliente no es válido.")
    neg = _negocio(ses["email"])
    if any(f.get("canchaId") == c["id"] and int(f.get("diaSemana") or 0) == dia and f.get("hora") == hora and f.get("activo", True)
           for f in neg["fijas"]):
        return _err("Ya tienes un cliente fijo en ese día y hora.", 409)
    fid = f"fija_{time.time_ns() // 1000}"
    neg["fijas"].append({"id": fid, "canchaId": c["id"], "diaSemana": dia, "hora": hora, "clienteNombre": nombre,
                         "clienteEmail": correo, "clienteTelefono": tel, "activo": True, "hechas": []})
    res = generar_fijas(ses["email"], canchas, solo=fid)
    return _json_ok(id=fid, **res)


@router.post("/anfitrion/fijas/{fid}/activo")
def activar_fija(request: Request, fid: str, body: dict = Body(default_factory=dict)) -> JSONResponse:
    ses = sesion.de_request(request)
    if not ses:
        return _err("sesion_requerida", 401)
    f = next((x for x in _negocio(ses["email"])["fijas"] if x.get("id") == fid), None)
    if f is None:
        return _err("No encontramos ese cliente fijo.", 404)
    f["activo"] = bool(body.get("activo"))
    res = generar_fijas(ses["email"], datos.canchas_de_dueno(ses["email"]), solo=fid) if f["activo"] else {"creadas": 0, "omitidas": []}
    return _json_ok(**res)


@router.post("/anfitrion/fijas/{fid}/quitar")
def quitar_fija(request: Request, fid: str) -> JSONResponse:
    """Deja de generar (las reservas ya creadas siguen en la agenda)."""
    ses = sesion.de_request(request)
    if not ses:
        return _err("sesion_requerida", 401)
    neg = _negocio(ses["email"])
    antes = len(neg["fijas"])
    neg["fijas"] = [x for x in neg["fijas"] if x.get("id") != fid]
    if len(neg["fijas"]) == antes:
        return _err("No encontramos ese cliente fijo.", 404)
    return _json_ok()


# ── Disponibilidad (disponibilidad_screen.dart, hecha real) ─────────────────

@router.get("/anfitrion/disponibilidad", response_class=HTMLResponse)
def pagina_disponibilidad(request: Request, cancha: str = "", fecha: str = "") -> HTMLResponse:
    ses, canchas, resp = _contexto(request, "/anfitrion/disponibilidad")
    if resp is not None:
        return resp
    c = next((x for x in canchas if x["id"] == cancha), canchas[0])
    ahora = horarios.ahora_local(_pais_de(c))
    hoy = ahora.date()
    try:
        dia = date.fromisoformat(fecha)
    except ValueError:
        dia = hoy
    base = dia.isoformat()
    sl = _slots(c)
    fechas = sorted({horarios.fecha_real(base, c["hora_apertura"], c["hora_cierre"], h) for h in sl} | {base})
    reservadas = {(r["fecha"], r["hora_inicio"]) for r in reservas_dueno([c["id"]], fechas[0], fechas[-1]) if not es_noshow(r)}
    bloq = {(f, h) for (_cid, f, h) in datos.bloqueos_de([c["id"]], fechas)}
    valle_cfg = int(c.get("descuento_valle") or 0) > 0
    filas = ""
    abiertas = 0
    for h in sl:
        fr = horarios.fecha_real(base, c["hora_apertura"], c["hora_cierre"], h)
        pasado = fr < hoy.isoformat() or (fr == hoy.isoformat() and (horarios.hora_en_minutos(h) or 0) < ahora.hour * 60 + ahora.minute)
        valle = horarios.es_valle(h, c.get("valle_desde") or "", c.get("valle_hasta") or "") if valle_cfg else (horarios.hora_en_minutos(h) or 0) < 12 * 60
        ocupada = (fr, h) in reservadas
        abierta = not ocupada and (fr, h) not in bloq
        abiertas += 1 if abierta and not pasado else 0
        estado = "Reservada" if ocupada else ("Hora valle" if valle else "Horario regular")
        extra = ("<small class='ng-valle'>Prioriza abrirla</small>" if valle and not ocupada and not pasado else "")
        madr = " · madrugada" if fr != base else ""
        ctrl = ("<span class='ng-lock' title='Reservada'>🔒</span>" if ocupada else
                f"<label class='ng-sw'><input type='checkbox' data-f='{fr}' data-h='{e(h)}' {'checked' if abierta else ''} {'disabled' if pasado else ''}"
                f" aria-label='{e(h)} abierta'><i></i></label>")
        filas += (f"<div class='ng-fila{' pasada' if pasado else ''}'><b class='ng-hora'>{e(h)}</b><div class='ng-fila-t'><b>{estado}{madr}</b>{extra}"
                  f"{'<small>Ya pasó</small>' if pasado and not ocupada else ''}</div>{ctrl}</div>")
    chips = "".join(f"<a class='chip{' sel' if x['id'] == c['id'] else ''}' href='?cancha={e(x['id'])}&fecha={base}'>{e(x['nombre'])}</a>" for x in canchas)
    cuerpo = (
        "<h1 class='anf-hola'>Disponibilidad</h1><p class='sub'>Abre las horas que quieres publicar en la app y en la web; las cerradas no se pueden "
        "reservar. Las mañanas (horas valle) son las que más conviene llenar.</p>"
        f"<div class='chips' style='margin-top:12px'>{chips}</div>"
        "<div class='ng-dia'>"
        f"<a class='ng-flecha' href='?cancha={e(c['id'])}&fecha={(dia - timedelta(days=1)).isoformat()}' aria-label='Día anterior'>‹</a>"
        f"<form method='get'><input type='hidden' name='cancha' value='{e(c['id'])}'><input type='date' name='fecha' value='{base}' onchange='this.form.submit()' aria-label='Elegir día'></form>"
        f"<b>{e(_fecha_bonita(base, hoy))}</b>"
        f"<a class='ng-flecha' href='?cancha={e(c['id'])}&fecha={(dia + timedelta(days=1)).isoformat()}' aria-label='Día siguiente'>›</a></div>"
        f"<p class='sub'>{abiertas} turno{'s' if abiertas != 1 else ''} abierto{'s' if abiertas != 1 else ''} · "
        f"{e(horarios.duracion_texto(int(c.get('duracion_slot_min') or 60)))} por turno</p>"
        + (f"<div class='ng-card ng-dispo'>{filas}</div>" if filas else "<div class='anf-vacio'>Configura el horario de esta cancha.</div>")
        + f"<script>window.__dispo={json.dumps({'cancha': c['id']})};{JS_DISPO}</script>")
    return _pagina("Disponibilidad", cuerpo, ses, "disponibilidad")


# ── Cobros de academia (cobros_screen.dart) ─────────────────────────────────

def _deuda(m: dict, hoy: str) -> tuple[float, bool, list[dict]]:
    pend = [c for c in (m.get("cuotas") or []) if isinstance(c, dict) and not c.get("pagada")]
    return (sum(float(c.get("monto") or 0) for c in pend),
            any(str(c.get("vencimiento") or "")[:10] < hoy for c in pend if c.get("vencimiento")), pend)


def _saludo(m: dict) -> str:
    return (m.get("apoderadoNombre") or m.get("nombre") or "").strip()


def _msj_cobro(m: dict, deuda: float, sim: str, app: bool) -> str:
    de = f" de {m.get('nombre')}" if m.get("apoderadoNombre") else ""
    if app:
        return (f"Hola {_saludo(m)}, tienes una cuota pendiente{de} por {sim} {deuda:.2f}. Puedes pagarla ahora mismo desde la app "
                "en “Mis clases y pagos”. ¡Gracias! 🙌")
    return f"Hola {_saludo(m)}, te recuerdo el pago pendiente{de} por {sim} {deuda:.2f}. ¡Gracias! 🙌"


@router.get("/anfitrion/cobros", response_class=HTMLResponse)
def pagina_cobros(request: Request, academia: str = "") -> HTMLResponse:
    from web.anfitrion_academia import _mias, _moneda
    from web.jugador_liga import avatar
    ses, resp = _sesion_o_entrar(request, "/anfitrion/cobros")
    if resp is not None:
        return resp
    acads = _mias(ses["email"])
    if not acads:
        cuerpo = ("<h1 class='anf-hola'>Cobros de academia</h1><div class='anf-vacio' style='margin-top:16px'>Aún no tienes una academia. "
                  "<a href='/anfitrion/academia'>Créala aquí</a> y cobra las mensualidades de tus alumnos.</div>")
        return _pagina("Cobros de academia", cuerpo, ses, "cobros")
    a = next((x for x in acads if x["id"] == academia), acads[0])
    sim = _moneda(a)
    hoy = date.today().isoformat()
    mes = hoy[:7]
    mats = datos.matriculas_de_academias([a["id"]])
    recordados = _negocio(ses["email"])["recordados"]
    por_cobrar = vencido = cobrado = 0.0
    morosos = []
    for m in mats:
        deuda, venc, pend = _deuda(m, hoy)
        por_cobrar += deuda
        vencido += sum(float(c.get("monto") or 0) for c in pend if str(c.get("vencimiento") or "")[:10] < hoy)
        cobrado += sum(float(c.get("monto") or 0) for c in (m.get("cuotas") or [])
                       if isinstance(c, dict) and c.get("pagada") and str(c.get("fechaPago") or "").startswith(mes))
        if deuda > 0:
            morosos.append((m, deuda, venc, pend))
    morosos.sort(key=lambda t: (not t[2], -t[1]))

    def dias_rec(mid):
        try:
            return (datetime.now(timezone.utc) - datetime.fromisoformat(recordados[mid])).days
        except (KeyError, ValueError, TypeError):
            return None
    por_recordar = [t for t in morosos if dias_rec(t[0]["id"]) is None or dias_rec(t[0]["id"]) >= 7]
    fichas, filas = {}, ""
    for m, deuda, venc, pend in morosos:
        tel = str(m.get("apoderadoWhatsapp") if m.get("apoderadoNombre") and m.get("apoderadoWhatsapp") else m.get("whatsapp") or "")
        app = bool((m.get("email") or "").strip())
        d = dias_rec(m["id"])
        fichas[m["id"]] = {"nombre": m.get("nombre") or "Alumno", "app": app, "wa": ui.enlace_whatsapp(_msj_cobro(m, deuda, sim, False), _wa(tel)) if _wa(tel) else "",
                           "cuotas": [{"id": c.get("id"), "concepto": c.get("concepto") or "Cuota", "monto": float(c.get("monto") or 0),
                                       "vence": str(c.get("vencimiento") or "")[:10], "auto": bool(c.get("autoDebito"))} for c in pend]}
        filas += (f"<div class='ng-fila' data-al='{e(m['id'])}'>{avatar(m.get('nombre') or '?', m.get('fotoUrl') or '', 'ng-av')}"
                  f"<div class='ng-fila-t'><b>{e(m.get('nombre') or 'Alumno')}{' · ' + e(m['apoderadoNombre']) if m.get('apoderadoNombre') else ''}</b>"
                  f"<small>Debe {e(_m(deuda, sim))} · {len(pend)} cuota{'s' if len(pend) != 1 else ''}"
                  f"{' · recordado hace ' + str(d) + ' día' + ('s' if d != 1 else '') if d is not None else ''}{' · 📲 tiene la app' if app else ''}</small></div>"
                  + ("<span class='pill bad'>Vencido</span>" if venc else "")
                  + "<button type='button' class='btn sec mini-b' data-acc='cobrar'>Cobrar</button>"
                  "<button type='button' class='btn mini-b' data-acc='recordar'>Recordar</button></div>")
    chips = ("<div class='chips' style='margin-top:12px'>" + "".join(
        f"<a class='chip{' sel' if x['id'] == a['id'] else ''}' href='?academia={e(x['id'])}'>{e(x.get('nombre') or 'Academia')}</a>" for x in acads)
        + "</div>") if len(acads) > 1 else ""
    cuerpo = (
        f"<h1 class='anf-hola'>Cobros · {e(a.get('nombre') or 'Mi academia')}</h1><p class='sub'>Lo que abres a diario para cobrar: quién debe, "
        "recordatorios por la app o WhatsApp y el cobro en efectivo por cuota.</p>" + chips
        + "<div class='kpis'>" + _kpi("Por cobrar", e(_m(por_cobrar, sim))) + _kpi("Vencido", e(_m(vencido, sim)), "", "bad" if vencido > 0 else "")
        + _kpi("Cobrado este mes", e(_m(cobrado, sim)), "", "ok") + "</div>"
        + (f"<div class='ng-rec'><b>🔔 Tienes {len(por_recordar)} alumno{'s' if len(por_recordar) != 1 else ''} por recordar</b>"
           "<small>Deben y no se les recordó en la última semana.</small><button type='button' class='btn' id='recTodos'>Recordar a todos</button></div>"
           if por_recordar else "")
        + "<h2 class='ng-h2'>Quién debe</h2>"
        + (f"<div class='ng-lista' id='morosos'>{filas}</div>" if filas else "<div class='anf-vacio'>Todos al día 🎉</div>")
        + f"<p style='margin-top:16px'><a class='btn sec' href='/anfitrion/academia/alumnos?academia={e(a['id'])}'>Ver todos los alumnos</a></p>"
        + f"<script>window.__cob={json.dumps({'academia': a['id'], 'moneda': sim, 'fichas': fichas, 'porRecordar': [t[0]['id'] for t in por_recordar]}, ensure_ascii=False)};{JS_COBROS}</script>")
    return _pagina("Cobros de academia", cuerpo, ses, "cobros")


def _mat_de(email: str, academia_id: str, alumno_id: str):
    from web.anfitrion_academia import _mia, _moneda
    a = _mia(email, academia_id)
    if a is None:
        return None, None, ""
    m = next((x for x in datos.matriculas_de_academias([academia_id]) if x.get("id") == alumno_id), None)
    return a, m, _moneda(a)


@router.post("/anfitrion/cobros/recordar")
def recordar_cobro(request: Request, body: dict = Body(default_factory=dict)) -> JSONResponse:
    """Recuerda el pago: por el CHAT de la academia (con push) si el alumno
    tiene la app; si no, el navegador abre WhatsApp y aquí solo se anota."""
    from web.jugador_liga import mi_nombre
    ses = sesion.de_request(request)
    if not ses:
        return _err("sesion_requerida", 401)
    a, m, sim = _mat_de(ses["email"], str(body.get("academia_id") or ""), str(body.get("alumno_id") or ""))
    if a is None or m is None:
        return _err("Ese alumno no es de tu academia.", 404)
    deuda, _v, _p = _deuda(m, date.today().isoformat())
    if deuda <= 0:
        return _err("Este alumno ya está al día.", 409)
    canal = "whatsapp"
    if (m.get("email") or "").strip() and not body.get("solo_marcar"):
        if not mensaje_academia(a["id"], m["email"], ses["email"], mi_nombre(ses), _msj_cobro(m, deuda, sim, True)):
            return _err("No se pudo enviar por la app.", 503)
        canal = "app"
    _negocio(ses["email"])["recordados"][m["id"]] = datetime.now(timezone.utc).isoformat()
    return _json_ok(canal=canal)


@router.post("/anfitrion/cobros/cuota")
def cobrar_cuota(request: Request, body: dict = Body(default_factory=dict)) -> JSONResponse:
    """El profe cobró una cuota en efectivo (= `marcarCuotaPagada` del app) y
    se avisa al alumno "Pago registrado ✓"."""
    from web.jugador_liga import aviso_push
    ses = sesion.de_request(request)
    if not ses:
        return _err("sesion_requerida", 401)
    a, m, sim = _mat_de(ses["email"], str(body.get("academia_id") or ""), str(body.get("alumno_id") or ""))
    if a is None or m is None:
        return _err("Ese alumno no es de tu academia.", 404)
    c = marcar_cuota_cobrada(a["id"], m["id"], str(body.get("cuota_id") or ""))
    if c is None:
        return _err("Esa cuota ya estaba pagada o no existe.", 409)
    if (m.get("email") or "").strip():
        _en_segundo_plano(aviso_push, m["email"], "Pago registrado ✓",
                          f"{a.get('nombre') or 'Tu academia'} registró tu pago: {c.get('concepto') or 'Cuota'} · {sim} {float(c.get('monto') or 0):.2f}.",
                          "academia")
    print(f"[cobros-web] {ses['email']} cobró {c.get('id')} de {m['id']}", flush=True)
    return _json_ok()


# ── estilos y scripts ───────────────────────────────────────────────────────

CSS = r"""
.kpis{grid-template-columns:repeat(auto-fill,minmax(min(150px,100%),1fr))}.kpi{min-width:0}.kpi b{overflow-wrap:anywhere}
.ng-nav{display:flex;gap:8px;overflow-x:auto;padding:4px 0 10px;margin:8px 0 6px;scrollbar-width:none}.ng-nav::-webkit-scrollbar{display:none}
.ng-nav .chip{flex:none;font-size:13.5px;padding:8px 13px}.ng-nav .chip span{font-size:15px}
.ng-tabs{display:flex;gap:22px;border-bottom:1px solid var(--trazo);margin:6px 0 16px;overflow-x:auto;scrollbar-width:none}
.ng-tabs a{padding:10px 0;font-weight:700;color:var(--tenue);text-decoration:none;border-bottom:3px solid transparent;white-space:nowrap}
.ng-tabs a.sel{color:var(--noche);border-bottom-color:var(--esmeralda)}
.ng-mon{margin:0 0 10px}
.ng-h2{margin-top:28px;font-size:19px}.ng-h2 small{color:var(--tenue);font-size:14px;font-weight:600}
.ng-hero,.ng-card{background:var(--blanco);border:1px solid var(--trazo);border-radius:20px;padding:18px 20px;box-shadow:var(--sombra);margin-top:16px;min-width:0}
.ng-card h3{margin:0 0 8px;font-size:16px}
.ng-hero>small{display:block;color:var(--tenue);font-weight:600}.ng-hero>b{display:block;font-size:34px;color:var(--esmeralda);margin:4px 0}
.ng-barras{display:flex;align-items:flex-end;gap:8px;margin-top:10px;min-width:0}
.ng-bar{flex:1;min-width:0;display:flex;flex-direction:column;align-items:center;justify-content:flex-end;height:100%;cursor:default;outline:none}
.ng-bar i{display:block;width:100%;max-width:44px;background:var(--esmeralda);border-radius:4px 4px 0 0;transition:opacity .15s}
.ng-bar:hover i,.ng-bar:focus i{opacity:.8}
.ng-bar small{font-size:11px;font-weight:700;color:var(--noche);min-height:15px;white-space:nowrap}
.ng-bar span{font-size:11px;color:var(--tenue);margin-top:5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:100%}
.ng-tabla{margin-top:10px;font-size:13px;color:var(--tenue)}.ng-tabla summary{cursor:pointer;font-weight:700}
.ng-tabla table{border-collapse:collapse;margin-top:6px}.ng-tabla td,.ng-tabla th{padding:4px 10px;border-bottom:1px solid var(--trazo);text-align:left}
.ng-hb{margin:10px 0}.ng-hb-t{display:flex;gap:8px;align-items:baseline;min-width:0}.ng-hb-t b{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.ng-hb-t small{color:var(--tenue);font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;min-width:0}.ng-hb-t span{margin-left:auto;font-weight:800;white-space:nowrap}
.ng-hb-p{height:10px;background:var(--gris);border-radius:6px;margin-top:5px;overflow:hidden}.ng-hb-p i{display:block;height:100%;background:var(--esmeralda);border-radius:6px}
.ng-local{background:var(--blanco);border:1px solid var(--trazo);border-radius:16px;padding:12px 16px;margin-top:12px}
.ng-local-h{display:flex;justify-content:space-between;gap:8px}.ng-local-h span{font-weight:800}
.ng-rc{display:flex;justify-content:space-between;gap:10px;padding:8px 0;border-top:1px solid var(--trazo)}.ng-rc:first-of-type{border-top:0}
.ng-rc div{min-width:0}.ng-rc small{display:block;color:var(--tenue);font-size:12px}.ng-rc span{font-weight:800;color:var(--esmeralda);white-space:nowrap}
.ng-rc.tot b{font-size:15px}.ng-rc.tot span{font-size:17px}
.ng-nota{font-size:12.5px;color:var(--tenue);margin:8px 0 0}
.ng-custom{display:flex;flex-wrap:wrap;gap:10px;align-items:flex-end;margin-top:10px}.ng-custom label{display:flex;flex-direction:column;font-size:12.5px;font-weight:700;color:var(--tenue);gap:4px}
.ng-custom input{width:auto}
.ng-lista{display:flex;flex-direction:column;gap:8px;margin-top:10px}
.ng-fila{display:flex;align-items:center;gap:10px;background:var(--blanco);border:1px solid var(--trazo);border-radius:14px;padding:11px 14px;min-width:0;text-decoration:none;color:inherit;flex-wrap:wrap}
.ng-fila.pausa,.ng-fila.pasada{opacity:.6}
.ng-fila-t{flex:1;min-width:150px}.ng-fila-t b{display:block;overflow:hidden;text-overflow:ellipsis}.ng-fila-t small{display:block;color:var(--tenue);font-size:12.5px}
.ng-monto{white-space:nowrap}
.ng-sena{color:var(--teal)!important;font-weight:700}
.mini-b{padding:8px 12px!important;font-size:13px!important}
.pill.gris{background:var(--gris);color:var(--tenue)}.pill.bad{background:var(--bad-bg);color:var(--bad-fg)}.pill.warn{background:var(--warn-bg);color:var(--warn-fg)}.pill.ok{background:var(--ok-bg);color:var(--ok-fg)}
.kpi.bad b{color:var(--bad-fg)}.kpi.ok b{color:var(--esmeralda)}
.ng-atajos a{text-decoration:none;color:inherit}.ng-atajos b{font-size:15px}
.ng-dia{display:flex;align-items:center;gap:10px;margin-top:14px;flex-wrap:wrap}.ng-dia input{width:auto}.ng-dia>b{font-size:17px}
.ng-flecha{width:38px;height:38px;border-radius:50%;border:1px solid var(--trazo);display:inline-flex;align-items:center;justify-content:center;text-decoration:none;color:var(--noche);font-size:22px;background:var(--blanco);box-shadow:0 1px 3px rgba(0,0,0,.06)}
.ng-cierre-box{margin-top:16px}.ng-cierre{display:flex;gap:10px;align-items:center;flex-wrap:wrap;background:var(--ok-bg);border-radius:16px;padding:12px 16px}
.ng-cierre.auto{background:var(--warn-bg)}.ng-cierre>div{flex:1;min-width:180px}.ng-cierre small{display:block;color:var(--tenue)}
.ng-av{width:42px;height:42px;border-radius:50%;object-fit:cover;flex:none;display:inline-flex;align-items:center;justify-content:center;background:#0E8F67;color:#fff;font-weight:800;font-size:17px}
.ng-busca{display:flex;flex-direction:column;gap:10px;margin:14px 0 4px}
.ng-clis{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(280px,100%),1fr));gap:12px;margin-top:12px}
.ng-cli{position:relative;text-align:left;background:var(--blanco);border:1px solid var(--trazo);border-radius:18px;padding:14px 16px;box-shadow:var(--sombra);cursor:pointer;font:inherit;color:inherit;min-width:0}
.ng-cli:hover{box-shadow:var(--sombra2)}
.ng-cli-h{display:flex;gap:12px;align-items:center;min-width:0;padding-right:70px}.ng-cli-h b{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.ng-cli-h small{display:block;color:var(--tenue);font-size:12.5px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.ng-cli-d{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:6px;margin-top:12px;font-size:12px;color:var(--tenue)}
.ng-cli-d b{display:block;color:var(--noche);font-size:14px}
.ng-debe{margin-top:8px;font-size:12.5px;font-weight:800;color:var(--warn-fg);background:var(--warn-bg);border-radius:999px;padding:4px 10px;display:inline-block}
.ng-badge{position:absolute;top:12px;right:12px;color:#fff;font-size:11px;font-weight:800;padding:4px 9px;border-radius:999px}
.ng-ficha{text-align:left}.ng-ficha .fh{display:flex;gap:12px;align-items:center;margin-bottom:12px}.ng-ficha .fh small{display:block;color:var(--tenue)}
.ng-ficha .dts{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.ng-ficha .dts div{background:var(--gris);border-radius:12px;padding:8px 10px}
.ng-ficha .dts small{display:block;color:var(--tenue);font-size:11.5px}.ng-ficha .acc{display:flex;gap:8px;flex-wrap:wrap;margin:12px 0}
.ng-ficha textarea{width:100%;min-height:70px;border:1px solid var(--trazo);border-radius:12px;padding:10px;font:inherit;box-sizing:border-box}
.ng-ficha .hist{font-size:13px;margin-top:10px}.ng-ficha .hist div{display:flex;justify-content:space-between;gap:8px;padding:6px 0;border-top:1px solid var(--trazo)}
.ng-bonos{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(320px,100%),1fr));gap:12px;margin-top:14px}
.ng-bono{display:flex;flex-wrap:wrap;gap:12px;align-items:center;background:var(--blanco);border:1px solid var(--trazo);border-radius:18px;padding:14px;box-shadow:var(--sombra)}
.ng-bono.pausa{opacity:.7}.ng-bono b{display:block}.ng-bono small{display:block;color:var(--tenue);margin:2px 0 6px}
.ng-bono-h{width:54px;height:54px;border-radius:16px;background:var(--tinte);color:var(--teal);font-weight:800;font-size:18px;display:flex;align-items:center;justify-content:center;flex:none}
.ng-bono-a{display:flex;gap:6px;flex-wrap:wrap;width:100%}
.ng-ico{font-size:20px}
.ng-sw{position:relative;display:inline-block;width:46px;height:28px;flex:none;cursor:pointer}.ng-sw input{position:absolute;opacity:0;width:100%;height:100%;margin:0;cursor:pointer}
.ng-sw i{position:absolute;inset:0;background:#CFD8D3;border-radius:999px;transition:.2s}.ng-sw i:after{content:'';position:absolute;top:3px;left:3px;width:22px;height:22px;border-radius:50%;background:#fff;box-shadow:0 1px 3px rgba(0,0,0,.2);transition:.2s}
.ng-sw input:checked+i{background:var(--esmeralda)}.ng-sw input:checked+i:after{left:21px}.ng-sw input:disabled+i{opacity:.45}
.ng-sw input:focus-visible+i{outline:2px solid var(--noche);outline-offset:2px}
.ng-dispo{padding:6px 12px}.ng-dispo .ng-fila{border:0;border-bottom:1px solid var(--trazo);border-radius:0;box-shadow:none}.ng-dispo .ng-fila:last-child{border-bottom:0}
.ng-hora{width:56px;font-size:16px;flex:none}.ng-valle{color:var(--warn-fg)!important;font-weight:700}.ng-lock{font-size:18px}
.ng-ok{background:var(--ok-bg);color:var(--ok-fg);border-radius:14px;padding:12px 14px;font-weight:700;margin-top:12px}
.ng-rec{display:flex;flex-wrap:wrap;gap:6px 12px;align-items:center;background:var(--warn-bg);border-radius:16px;padding:14px 16px;margin-top:16px}
.ng-rec b{flex:1 1 240px}.ng-rec small{flex:1 1 100%;order:3;color:var(--warn-fg)}
.ng-form label{display:block;font-weight:700;font-size:13px;margin:12px 0 6px;text-align:left}.ng-form select,.ng-form input{width:100%;box-sizing:border-box}
.ng-form .chips{gap:6px}.ng-form .chip{padding:7px 11px;font-size:13px}.ng-form .err{color:var(--bad-fg);font-size:13px;margin-top:8px;text-align:left;min-height:1em}
.ng-cuota{display:flex;gap:8px;align-items:center;justify-content:space-between;padding:8px 0;border-top:1px solid var(--trazo);text-align:left}
.ng-cuota small{display:block;color:var(--tenue)}
.hm{display:grid;grid-template-columns:48px repeat(7,minmax(0,1fr));gap:3px;min-width:0}
.hm-d{text-align:center;font-size:12px;font-weight:800;color:var(--tenue)}.hm-h{font-size:11.5px;color:var(--tenue);display:flex;align-items:center}
.hm-c{height:20px;border-radius:4px;outline:none}.hm-c:hover,.hm-c:focus{box-shadow:0 0 0 2px var(--noche)}
.hm-ley{display:flex;align-items:center;gap:3px;justify-content:flex-end;margin-top:10px;font-size:11.5px;color:var(--tenue)}.hm-ley i{width:16px;height:12px;border-radius:3px;display:inline-block}.hm-ley span{margin:0 4px}
.ng-rep{display:flex;align-items:baseline;gap:10px}.ng-rep b{font-size:32px}.ng-rep span{color:#E0A100;font-size:18px}.ng-rep small{color:var(--tenue)}
.ng-resena{padding:8px 0;border-top:1px solid var(--trazo);font-size:14px}.ng-resena b{color:#E0A100}.ng-resena small{display:block;color:var(--tenue)}
.ng-tip{position:fixed;z-index:9999;pointer-events:none;background:var(--noche);color:#fff;font-size:12.5px;font-weight:700;padding:6px 10px;border-radius:8px;box-shadow:0 4px 14px rgba(0,0,0,.2);max-width:240px;display:none}
"""

# Tooltip para las barras y el mapa de calor (hover y foco/toque).
JS_TIP = r"""
(function(){var t=null;function tip(){if(!t){t=document.createElement('div');t.className='ng-tip';document.body.appendChild(t);}return t;}
function mostrar(el,x,y){var d=tip();d.textContent=el.dataset.tip;d.style.display='block';var w=d.offsetWidth;d.style.left=Math.max(8,Math.min(window.innerWidth-w-8,x-w/2))+'px';d.style.top=Math.max(8,y-d.offsetHeight-12)+'px';}
function ocultar(){if(t)t.style.display='none';}
document.addEventListener('mouseover',function(ev){var el=ev.target.closest('[data-tip]');if(!el){ocultar();return;}var r=el.getBoundingClientRect();mostrar(el,r.left+r.width/2,r.top);});
document.addEventListener('focusin',function(ev){var el=ev.target.closest('[data-tip]');if(!el)return;var r=el.getBoundingClientRect();mostrar(el,r.left+r.width/2,r.top);});
document.addEventListener('focusout',ocultar);window.addEventListener('scroll',ocultar,{passive:true});})();
async function ngPost(url,body,msg){pcgCargando(msg||'Guardando…',{demora:250});try{var r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body||{})});var j={};try{j=await r.json();}catch(e){}pcgCargando(false);if(r.status===401){pcgIr('/entrar?volver='+encodeURIComponent(location.pathname+location.search));return null;}return j;}catch(e){pcgCargando(false);return {ok:false,error:'No se pudo guardar. Revisa tu conexión.'};}}
function ngEsc(s){return String(s==null?'':s).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});}
"""

JS_CAJA = r"""
window.alPagar=function(){pcgRecargar('Actualizando la caja…');};
document.addEventListener('click',async function(ev){var b=ev.target.closest('[data-caja]');if(!b)return;var C=window.__caja;
  if(b.dataset.caja==='cerrar'){var ok=await pcgConfirmar({titulo:'Cerrar caja del día',html:'<div style="white-space:pre-line;text-align:left">'+ngEsc(C.resumen)+'\n\nSe guarda el arqueo de este día.</div>',confirmar:'Cerrar caja',icono:'🧾'});if(!ok)return;
    var j=await ngPost('/anfitrion/caja/cerrar',{fecha:C.fecha,m:C.m},'Cerrando caja…');if(j&&j.ok){pcgRecargar('Caja cerrada ✅');}else if(j){pcgAvisar({titulo:'No se pudo',mensaje:j.error||'Reintenta.'});}}
  else{var ok2=await pcgConfirmar({titulo:'Reabrir la caja',mensaje:'Se borra el cierre de este día para que lo revises y lo vuelvas a cerrar.',confirmar:'Reabrir'});if(!ok2)return;
    var k=await ngPost('/anfitrion/caja/reabrir',{fecha:C.fecha,m:C.m});if(k&&k.ok)pcgRecargar();}});
"""

JS_CLIENTES = r"""
(function(){var q=document.getElementById('qCli');if(q)q.addEventListener('input',function(){var v=q.value.trim().toLowerCase(),n=0;document.querySelectorAll('.ng-cli').forEach(function(c){var ok=!v||c.dataset.q.indexOf(v)>=0;c.style.display=ok?'':'none';if(ok)n++;});var z=document.getElementById('cliVacio');if(z)z.style.display=n?'none':'';});
document.addEventListener('click',function(ev){var b=ev.target.closest('[data-cli]');if(!b)return;var c=window.__cli[b.dataset.cli];if(!c)return;
  var av=c.foto?'<img class="ng-av" src="'+ngEsc(c.foto)+'" alt="" referrerpolicy="no-referrer">':'<span class="ng-av">'+ngEsc((c.nombre||'?').charAt(0).toUpperCase())+'</span>';
  var h='<div class="ng-ficha"><div class="fh">'+av+'<div><b>'+ngEsc(c.nombre)+'</b><small>'+ngEsc(c.contacto)+'</small></div></div><div class="dts">';
  c.datos.forEach(function(d){h+='<div><small>'+ngEsc(d[0])+'</small><b>'+ngEsc(d[1])+'</b></div>';});h+='</div><div class="acc">';
  if(c.wa){h+='<a class="btn sec mini-b" target="_blank" rel="noopener" href="https://wa.me/'+c.wa+'">💬 WhatsApp</a>';
    if(c.debe>0){var msg='Hola '+c.nombre+' 👋 Te recordamos tu saldo pendiente de '+c.moneda+c.debe.toFixed(2)+' por tu reserva. ¡Gracias!';h+='<a class="btn mini-b" target="_blank" rel="noopener" href="https://wa.me/'+c.wa+'?text='+encodeURIComponent(msg)+'">Recordar cobro</a>';}}
  h+='<a class="btn sec mini-b" href="/anfitrion/calendario">📝 Reservar</a></div>';
  if(c.debe>0)h+='<div class="ng-debe">Te debe '+ngEsc(c.moneda)+' '+c.debe.toFixed(2)+'</div>';
  h+='<label style="display:block;font-weight:800;margin:14px 0 6px;text-align:left">Notas privadas</label><textarea id="ngNota" maxlength="600" placeholder="Solo tú las ves. Ej: prefiere Cancha 2, juega martes, paga efectivo.">'+ngEsc(c.nota)+'</textarea>';
  h+='<div class="hist"><b>Historial de reservas</b>';c.historial.forEach(function(r){h+='<div><span>'+ngEsc(r[0])+' · '+ngEsc(r[1])+' · '+ngEsc(r[2])+'</span><span>'+ngEsc(r[3])+' · '+ngEsc(r[4])+'</span></div>';});
  if(!c.historial.length)h+='<div>Sin reservas registradas.</div>';h+='</div></div>';
  pcgConfirmar({titulo:'Ficha del cliente',html:h,confirmar:'Guardar nota',cancelar:'Cerrar',icono:'👤'}).then(async function(ok){if(!ok)return;var t=(document.getElementById('ngNota')||{}).value||'';
    var j=await ngPost('/anfitrion/clientes/nota',{clave:c.clave,texto:t});if(j&&j.ok){c.nota=t.trim();pcgToast('Nota guardada');}else if(j){pcgAvisar({titulo:'No se pudo',mensaje:j.error||'Reintenta.'});}});});})();
"""

JS_BONOS = r"""
(function(){var B=window.__bonos;
function form(b){b=b||{};var hs=[2,4,5,8,10,12,20];var h='<div class="ng-form"><label>¿Cuántas horas trae el pack?</label><div class="chips" id="bH">';
  hs.forEach(function(x){h+='<button type="button" class="chip'+(b.horas==x?' sel':'')+'" data-h="'+x+'">'+x+' h</button>';});
  h+='</div><input type="number" id="bHo" min="1" max="200" inputmode="numeric" placeholder="Otra cantidad de horas" value="'+(b.horas&&hs.indexOf(b.horas)<0?b.horas:'')+'" style="margin-top:8px">';
  h+='<label>Precio del pack ('+ngEsc(B.moneda)+')</label><input type="number" id="bP" min="0.5" step="0.5" inputmode="decimal" value="'+(b.precio||'')+'">';
  h+='<label>Nombre (opcional)</label><input type="text" id="bN" maxlength="60" placeholder="Ej: Pack mensual" value="'+ngEsc(b.nombre||'')+'"><div class="err" id="bE"></div></div>';return h;}
async function editar(b){var nuevo=!b;var p=pcgConfirmar({titulo:nuevo?'Nuevo bono':'Editar bono',html:form(b),confirmar:'Guardar bono',icono:'🎟️'});
  setTimeout(function(){var g=document.getElementById('bH');if(g)g.addEventListener('click',function(ev){var c=ev.target.closest('[data-h]');if(!c)return;g.querySelectorAll('.chip').forEach(function(x){x.classList.toggle('sel',x===c);});document.getElementById('bHo').value='';});},60);
  var ok=await p;if(!ok)return;var sel=document.querySelector('#bH .chip.sel');var horas=parseInt(document.getElementById('bHo').value||(sel?sel.dataset.h:'0'),10);
  var precio=document.getElementById('bP').value,nombre=document.getElementById('bN').value;
  var j=await ngPost('/anfitrion/bonos/guardar',{id:b?b.id:'',club:B.club,horas:horas,precio:precio,nombre:nombre});
  if(j&&j.ok){pcgRecargar('Bono guardado ✅');}else if(j){await pcgAvisar({titulo:'No se pudo guardar',mensaje:j.error||'Reintenta.'});editar(b?Object.assign({},b,{horas:horas,precio:precio,nombre:nombre}):{horas:horas,precio:precio,nombre:nombre});}}
var n=document.getElementById('nuevoBono');if(n)n.addEventListener('click',function(){editar(null);});
document.addEventListener('click',async function(ev){var a=ev.target.closest('.ng-bono [data-acc]');if(!a)return;var b=JSON.parse(a.closest('.ng-bono').dataset.bono);
  if(a.dataset.acc==='editar'){editar(b);return;}
  if(a.dataset.acc==='activo'){var j=await ngPost('/anfitrion/bonos/'+encodeURIComponent(b.id)+'/activo',{activo:a.dataset.v==='1'});if(j&&j.ok)pcgRecargar();else if(j)pcgAvisar({titulo:'No se pudo',mensaje:j.error});return;}
  var ok=await pcgConfirmar({titulo:'Retirar bono',mensaje:'¿Quitar "'+(b.nombre||b.horas+' horas')+'" de tu local? Los jugadores que ya lo compraron conservan sus horas.',confirmar:'Retirar',destructivo:true});
  if(!ok)return;var k=await ngPost('/anfitrion/bonos/'+encodeURIComponent(b.id)+'/eliminar',{},'Retirando…');if(k&&k.ok)pcgRecargar('Bono retirado');else if(k)pcgAvisar({titulo:'No se pudo',mensaje:k.error});});})();
"""

JS_FIJAS = r"""
(function(){var F=window.__fijas,D=['Lunes','Martes','Miércoles','Jueves','Viernes','Sábado','Domingo'];
function form(v){v=v||{};var h='<div class="ng-form"><label>Cancha</label><select id="fC">';F.canchas.forEach(function(c){h+='<option value="'+ngEsc(c.id)+'"'+(v.c===c.id?' selected':'')+'>'+ngEsc(c.nombre)+'</option>';});
  h+='</select><label>Día de la semana</label><div class="chips" id="fD">';D.forEach(function(d,i){h+='<button type="button" class="chip'+((v.d||F.hoy)===i+1?' sel':'')+'" data-d="'+(i+1)+'">'+d.slice(0,3)+'</button>';});
  h+='</div><label>Hora</label><select id="fH"></select><label>Cliente</label><input type="text" id="fN" maxlength="80" placeholder="Nombre del cliente o equipo" value="'+ngEsc(v.n||'')+'">';
  h+='<label>WhatsApp (opcional)</label><input type="tel" id="fT" maxlength="20" inputmode="tel" value="'+ngEsc(v.t||'')+'"><label>Correo (opcional: así ve sus reservas en la app)</label><input type="email" id="fE" maxlength="120" value="'+ngEsc(v.e||'')+'"><div class="err" id="fErr">'+ngEsc(v.err||'')+'</div></div>';return h;}
function horas(sel){var id=document.getElementById('fC').value,c=F.canchas.find(function(x){return x.id===id;})||F.canchas[0],s=document.getElementById('fH');s.innerHTML='<option value="">Elige la hora</option>'+c.slots.map(function(h){return '<option'+(h===sel?' selected':'')+'>'+h+'</option>';}).join('');}
async function nueva(v){var p=pcgConfirmar({titulo:'Nuevo cliente fijo',html:form(v),confirmar:'Guardar y generar reservas',icono:'🔁'});
  setTimeout(function(){horas(v&&v.h);document.getElementById('fC').addEventListener('change',function(){horas();});var g=document.getElementById('fD');g.addEventListener('click',function(ev){var c=ev.target.closest('[data-d]');if(!c)return;g.querySelectorAll('.chip').forEach(function(x){x.classList.toggle('sel',x===c);});});},60);
  var ok=await p;if(!ok)return;var d=document.querySelector('#fD .chip.sel');v={c:document.getElementById('fC').value,d:d?parseInt(d.dataset.d,10):0,h:document.getElementById('fH').value,n:document.getElementById('fN').value.trim(),t:document.getElementById('fT').value,e:document.getElementById('fE').value.trim()};
  if(!v.h){v.err='Elige la hora.';return nueva(v);}if(!v.n){v.err='Escribe el nombre del cliente.';return nueva(v);}
  var j=await ngPost('/anfitrion/fijas/nueva',{cancha_id:v.c,dia:v.d,hora:v.h,nombre:v.n,telefono:v.t,email:v.e},'Generando reservas…');
  if(j&&j.ok){await pcgAvisar({titulo:'Cliente fijo guardado ✅',mensaje:'Se crearon '+j.creadas+' reserva(s) de las próximas semanas.'+(j.omitidas&&j.omitidas.length?' Omitidas: '+j.omitidas.join('; ')+'.':''),icono:'🔁'});pcgRecargar();}
  else if(j){v.err=j.error||'No se pudo guardar.';nueva(v);}}
var n=document.getElementById('nuevaFija');if(n)n.addEventListener('click',function(){nueva();});
document.addEventListener('change',async function(ev){var i=ev.target.closest('.ng-fila [data-acc="activo"]');if(!i)return;var id=i.closest('[data-fija]').dataset.fija;
  var j=await ngPost('/anfitrion/fijas/'+encodeURIComponent(id)+'/activo',{activo:i.checked});if(j&&j.ok){pcgToast(i.checked?'Reactivada: se completan sus próximas semanas':'Pausada: ya no se generan sus reservas');i.closest('.ng-fila').classList.toggle('pausa',!i.checked);}else{i.checked=!i.checked;if(j)pcgAvisar({titulo:'No se pudo',mensaje:j.error});}});
document.addEventListener('click',async function(ev){var b=ev.target.closest('.ng-fila [data-acc="quitar"]');if(!b)return;var id=b.closest('[data-fija]').dataset.fija;
  var ok=await pcgConfirmar({titulo:'Quitar cliente fijo',mensaje:'Se deja de generar sus reservas. Las que ya están creadas siguen en tu agenda.',confirmar:'Quitar',destructivo:true});if(!ok)return;
  var j=await ngPost('/anfitrion/fijas/'+encodeURIComponent(id)+'/quitar',{},'Quitando…');if(j&&j.ok)pcgRecargar();else if(j)pcgAvisar({titulo:'No se pudo',mensaje:j.error});});})();
"""

JS_DISPO = r"""
document.addEventListener('change',async function(ev){var i=ev.target.closest('.ng-dispo input[type=checkbox]');if(!i)return;var abrir=i.checked;
  var j=await ngPost('/anfitrion/bloqueo',{cancha_id:window.__dispo.cancha,fecha:i.dataset.f,hora:i.dataset.h,bloquear:!abrir},abrir?'Abriendo…':'Cerrando…');
  if(j&&j.ok){pcgToast(abrir?'Turno abierto ✅':'Turno cerrado');}else{i.checked=!abrir;if(j)pcgAvisar({titulo:j.error==='requiere_pro'?'Es Pichangol Pro':'No se pudo',mensaje:j.mensaje||j.error||'Reintenta.'});}});
"""

JS_COBROS = r"""
(function(){var C=window.__cob;
async function recordar(id,silencioso){var f=C.fichas[id];if(!f)return false;
  if(f.app){var j=await ngPost('/anfitrion/cobros/recordar',{academia_id:C.academia,alumno_id:id},'Enviando…');if(j&&j.ok){if(!silencioso)pcgToast('Le recordé a '+f.nombre+' por la app 📲');return true;}if(j&&!silencioso)pcgAvisar({titulo:'No se pudo',mensaje:j.error});return false;}
  if(!f.wa){if(!silencioso)pcgAvisar({titulo:'Sin contacto',mensaje:f.nombre+' no tiene WhatsApp ni cuenta en la app.'});return false;}
  window.open(f.wa,'_blank','noopener');ngPost('/anfitrion/cobros/recordar',{academia_id:C.academia,alumno_id:id,solo_marcar:true});return true;}
document.addEventListener('click',async function(ev){var b=ev.target.closest('#morosos [data-acc]');if(!b)return;var id=b.closest('[data-al]').dataset.al,f=C.fichas[id];
  if(b.dataset.acc==='recordar'){recordar(id);return;}
  var h='<div>';f.cuotas.forEach(function(c){h+='<div class="ng-cuota"><div><b>'+ngEsc(c.concepto)+'</b><small>'+ngEsc(C.moneda)+' '+c.monto.toFixed(2)+(c.vence?' · vence '+ngEsc(c.vence):'')+(c.auto?' · débito automático':'')+'</small></div><button type="button" class="btn mini-b" data-cuota="'+ngEsc(c.id)+'">💵 Cobrada</button></div>';});h+='</div>';
  pcgAvisar({titulo:'Cobrar a '+f.nombre,html:h,confirmar:'Cerrar',icono:'💳'});});
document.addEventListener('click',async function(ev){var b=ev.target.closest('[data-cuota]');if(!b)return;var dlg=document.getElementById('pcgDlg');var id=null;
  Object.keys(C.fichas).forEach(function(k){if(C.fichas[k].cuotas.some(function(c){return c.id===b.dataset.cuota;}))id=k;});if(!id)return;b.disabled=true;b.textContent='Guardando…';
  var j=await ngPost('/anfitrion/cobros/cuota',{academia_id:C.academia,alumno_id:id,cuota_id:b.dataset.cuota},'Registrando el cobro…');
  if(j&&j.ok){b.textContent='✅ Cobrada';C._cambio=true;pcgToast('Pago registrado ✓');}else{b.disabled=false;b.textContent='💵 Cobrada';if(j)pcgToast(j.error||'No se pudo');}
  if(dlg&&!dlg.dataset.ngw){dlg.dataset.ngw='1';var ok=document.getElementById('pcgDlgOk');ok.addEventListener('click',function(){if(C._cambio)pcgRecargar('Actualizando…');});}});
var t=document.getElementById('recTodos');if(t)t.addEventListener('click',async function(){var app=C.porRecordar.filter(function(i){return C.fichas[i]&&C.fichas[i].app;}),sin=C.porRecordar.filter(function(i){return C.fichas[i]&&!C.fichas[i].app;});
  var n=0;for(var k=0;k<app.length;k++){if(await recordar(app[k],true))n++;}
  if(sin.length){var h='<p style="text-align:left">'+(n?'Recordé a '+n+' por la app 📲. ':'')+'Estos no tienen la app: avísales por WhatsApp.</p>';
    sin.forEach(function(i){var f=C.fichas[i];h+='<div class="ng-cuota"><b>'+ngEsc(f.nombre)+'</b>'+(f.wa?'<a class="btn mini-b" target="_blank" rel="noopener" href="'+ngEsc(f.wa)+'" data-marca="'+ngEsc(i)+'">💬 Enviar</a>':'<small>Sin WhatsApp</small>')+'</div>';});
    await pcgAvisar({titulo:'Avisar por WhatsApp',html:h,confirmar:'Listo',icono:'💬'});pcgRecargar();}
  else{await pcgAvisar({titulo:n?'Recordatorios enviados':'Nadie por recordar',mensaje:n?'Recordé a '+n+' por la app 📲':'¡Nadie debe! 🎉'});pcgRecargar();}});
document.addEventListener('click',function(ev){var a=ev.target.closest('[data-marca]');if(!a)return;ngPost('/anfitrion/cobros/recordar',{academia_id:C.academia,alumno_id:a.dataset.marca,solo_marcar:true});});})();
"""

# Filtro por ORIGEN del cobro en la lista de Reservas del anfitrión
# (`_FiltroMedio` de reservas_dueno_screen): Todos / Online / Efectivo / Manual.
JS_FILTRO_RESERVAS = r"""
(function(){var f=document.getElementById('filMedio');if(!f)return;
f.querySelectorAll('[data-medio]').forEach(function(b){var k=b.dataset.medio,n=document.querySelectorAll('.anf-res'+(k==='todos'?'':'[data-medio="'+k+'"]')).length;b.textContent+=' ('+n+')';});
f.addEventListener('click',function(ev){var b=ev.target.closest('[data-medio]');if(!b)return;var k=b.dataset.medio;f.querySelectorAll('.chip').forEach(function(x){x.classList.toggle('sel',x===b);});
  document.querySelectorAll('.anf-res').forEach(function(c){c.style.display=(k==='todos'||c.dataset.medio===k)?'':'none';});
  document.querySelectorAll('.anf-grid').forEach(function(g){var h=g.previousElementSibling,vis=[].some.call(g.children,function(c){return c.style.display!=='none';});g.style.display=vis?'':'none';if(h&&h.tagName==='H3')h.style.display=vis?'':'none';});});})();
"""
