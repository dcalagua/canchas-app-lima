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

Cierres de caja, reservas fijas, notas de clientes y "ya recordado" (cobro
de academia y reservas) viven en el snapshot del backend
(`stores.negocio_web[correo]`), FUENTE ÚNICA para la web y el APK: el app los
lee y escribe por `/negocio/*` (`negocio_app.py`), que llama a las MISMAS
funciones de abajo (`cerrar_caja_de`, `autocerrar_de`, `crear_fija`,
`generar_fijas`, `guardar_nota_de`, `marcar_recordado_de`…).
"""

from __future__ import annotations

import csv
import io
import json
import re
import threading
import time
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote

from fastapi import APIRouter, Body, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

from db import pg
from db.store import stores
from reservas import reglas as _reglas
from web import datos, horarios, sesion, ui
from web import vista_anfitrion as va
from web.estilos_anfitrion import RAMPA
from web.anfitrion import (JS_PAGAR, _cabecera, _contexto, _en_segundo_plano, _motivo_cierre, _pais_de, _sesion_o_entrar)
from web.router import PLAY_URL, _moneda_de, e
from config import MARCA  # noqa: E402 — nombre y dominio de marca (un solo lugar)

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
                        (ui.json_js(data), alumno_id))
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
    """Datos del negocio del dueño que NO viven en una tabla (cierres de caja,
    reservas fijas, notas de clientes, recordatorios). FUENTE ÚNICA para la web
    y el APK (`negocio_app.py`, `/negocio/*`): ambos leen y escriben aquí."""
    email = email.strip().lower()
    d = stores.negocio_web.get(email)
    if d is None:
        d = {"fijas": [], "cierres": [], "notas": {}, "recordados": {}}
        stores.negocio_web[email] = d
    # `fijas_quitadas`: ids borrados (lápida) para que la copia vieja de otro
    # teléfono no los resucite al migrar; `migraciones`: equipos que ya
    # subieron lo que tenían guardado solo en el teléfono.
    for k, v in (("fijas", []), ("cierres", []), ("notas", {}), ("recordados", {}), ("fijas_quitadas", []),
                 ("migraciones", [])):
        d.setdefault(k, v)
    return d


# ── Operaciones compartidas web + APK ───────────────────────────────────────
# La web (handlers de abajo) y el APK (`negocio_app.py`) pasan por ESTAS
# funciones: mismas validaciones, mismo formato y mismo resultado.

_LOCK = threading.RLock()


class ErrNegocio(Exception):
    """Error de validación con su código HTTP (la web y el APK lo responden)."""

    def __init__(self, msg: str, status: int = 400):
        super().__init__(msg)
        self.msg = msg
        self.status = status


def _ordenar_cierres(neg: dict) -> None:
    neg["cierres"] = sorted(neg["cierres"], key=lambda x: x.get("fecha", ""), reverse=True)[:400]


def cerrar_caja_de(email: str, fecha: str, m: str = "", canchas: list[dict] | None = None) -> dict:
    """Cierre (arqueo CONFIRMADO) de la caja de un día en una moneda: foto de
    cobrado / por cobrar / reservas / medios calculada con las reservas de la
    nube (`caja_dia`). Reemplaza un cierre previo (manual o automático)."""
    canchas = datos.canchas_de_dueno(email) if canchas is None else canchas
    if not canchas:
        raise ErrNegocio("No tienes canchas a tu nombre.", 404)
    canchas, iso_mon, sim, _ = _por_moneda(canchas, str(m or ""))
    try:
        dia = date.fromisoformat(str(fecha or ""))
    except ValueError:
        raise ErrNegocio("Fecha inválida.") from None
    filas = reservas_dueno([c["id"] for c in canchas], dia.isoformat(), dia.isoformat())
    c = caja_dia(filas, dia.isoformat(), canchas)
    cierre = {"fecha": dia.isoformat(), "moneda": iso_mon, "cobrado": c["cobrado"], "porCobrar": c["por_cobrar"],
              "reservas": c["reservas"], "cerradaEn": datetime.now(timezone.utc).isoformat(), "automatico": False,
              "medios": c["medios"]}
    with _LOCK:
        neg = _negocio(email)
        neg["cierres"] = [x for x in neg["cierres"] if not (x.get("fecha") == dia.isoformat() and x.get("moneda", "PEN") == iso_mon)]
        neg["cierres"].insert(0, cierre)
        _ordenar_cierres(neg)
    return {"cierre": cierre, "cobrado": c["cobrado"], "simbolo": sim}


def reabrir_caja_de(email: str, fecha: str, m: str = "") -> bool:
    """Borra el cierre de ese día y moneda (para revisarlo y volver a cerrar)."""
    iso_mon = str(m or "PEN").upper()
    with _LOCK:
        neg = _negocio(email)
        antes = len(neg["cierres"])
        neg["cierres"] = [x for x in neg["cierres"] if not (x.get("fecha") == str(fecha or "") and x.get("moneda", "PEN") == iso_mon)]
        return len(neg["cierres"]) != antes


def autocerrar_de(email: str, canchas: list[dict] | None = None) -> bool:
    """Cierre automático de respaldo en TODAS las monedas del dueño (lo que la
    web hace al abrir la caja de una moneda). True si agregó algún cierre."""
    canchas = datos.canchas_de_dueno(email) if canchas is None else canchas
    if not canchas:
        return False
    cambio = False
    for iso_mon, _sim in _monedas(canchas):
        sub = [c for c in canchas if _moneda_de(c)[1] == iso_mon]
        if not sub:
            continue
        ahora = _hoy_de(sub)
        hoy = ahora.date()
        filas = reservas_dueno([c["id"] for c in sub], (hoy - timedelta(days=45)).isoformat(), hoy.isoformat())
        with _LOCK:
            neg = _negocio(email)
            antes = len(neg["cierres"])
            _autocerrar(neg, filas, sub, iso_mon, ahora)
            cambio = cambio or len(neg["cierres"]) != antes
    return cambio


def crear_fija(email: str, canchas: list[dict], body: dict, fid: str = "") -> dict:
    """Nuevo cliente fijo (validaciones de la web) y genera su serie. Con [fid]
    (el APK manda el suyo para reintentar sin duplicar) es idempotente."""
    c = next((x for x in canchas if x["id"] == str(body.get("cancha_id") or "")), None)
    if c is None:
        raise ErrNegocio("Esta cancha no está a tu nombre.", 404)
    try:
        dia = int(body.get("dia") or 0)
    except (TypeError, ValueError):
        dia = 0
    if not 1 <= dia <= 7:
        raise ErrNegocio("Elige el día de la semana.")
    hora = str(body.get("hora") or "")
    if hora not in _slots_dia_semana(c, dia):
        raise ErrNegocio("Elige la hora." if hora not in _slots(c) else "Ese día la cancha no atiende a esa hora (reglas del club).")
    nombre = re.sub(r"\s+", " ", str(body.get("nombre") or "")).strip()[:80]
    if not nombre:
        raise ErrNegocio("Escribe el nombre del cliente.")
    tel = re.sub(r"[^\d+ ]", "", str(body.get("telefono") or "")).strip()[:20]
    correo = str(body.get("email") or "").strip().lower()[:120]
    if correo and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", correo):
        raise ErrNegocio("El correo del cliente no es válido.")
    fid = re.sub(r"[^\w\-]", "", str(fid or ""))[:60]
    with _LOCK:
        neg = _negocio(email)
        if fid and any(f.get("id") == fid for f in neg["fijas"]):
            return {"id": fid, "creadas": 0, "omitidas": [], "existia": True}
        if fid and fid in neg["fijas_quitadas"]:
            raise ErrNegocio("Ese cliente fijo ya fue quitado.", 410)
        if any(f.get("canchaId") == c["id"] and int(f.get("diaSemana") or 0) == dia and f.get("hora") == hora and f.get("activo", True)
               for f in neg["fijas"]):
            raise ErrNegocio("Ya tienes un cliente fijo en ese día y hora.", 409)
        fid = fid or f"fija_{time.time_ns() // 1000}"
        neg["fijas"].append({"id": fid, "canchaId": c["id"], "diaSemana": dia, "hora": hora, "clienteNombre": nombre,
                             "clienteEmail": correo, "clienteTelefono": tel, "activo": True, "hechas": []})
    res = generar_fijas(email, canchas, solo=fid)
    return {"id": fid, **res}


def activar_fija_de(email: str, fid: str, activo: bool, canchas: list[dict] | None = None) -> dict:
    """Pausa / reactiva un cliente fijo; al reactivar completa su serie."""
    with _LOCK:
        f = next((x for x in _negocio(email)["fijas"] if x.get("id") == fid), None)
        if f is None:
            raise ErrNegocio("No encontramos ese cliente fijo.", 404)
        f["activo"] = bool(activo)
    if not f["activo"]:
        return {"creadas": 0, "omitidas": []}
    return generar_fijas(email, datos.canchas_de_dueno(email) if canchas is None else canchas, solo=fid)


def quitar_fija_de(email: str, fid: str) -> bool:
    """Deja de generar (las reservas ya creadas siguen en la agenda)."""
    with _LOCK:
        neg = _negocio(email)
        antes = len(neg["fijas"])
        neg["fijas"] = [x for x in neg["fijas"] if x.get("id") != fid]
        if len(neg["fijas"]) == antes:
            return False
        if fid not in neg["fijas_quitadas"]:
            neg["fijas_quitadas"] = (neg["fijas_quitadas"] + [fid])[-300:]
        return True


def guardar_nota_de(email: str, clave: str, texto: str) -> None:
    """Nota privada del dueño sobre un cliente (vacía = se borra)."""
    clave = str(clave or "").strip().lower()[:160]
    texto = re.sub(r"[ \t]+", " ", str(texto or "")).strip()[:600]
    if not clave:
        raise ErrNegocio("Cliente inválido.")
    with _LOCK:
        notas = _negocio(email)["notas"]
        if texto:
            notas[clave] = texto
        else:
            notas.pop(clave, None)


def marcar_recordado_de(email: str, clave: str, cuando: str = "") -> str:
    """Anota que se le recordó algo a alguien: el pago a un alumno (clave =
    id de su matrícula) o una reserva (clave `res:<id>`). Las marcas de reservas
    de más de 10 días se limpian solas."""
    clave = str(clave or "").strip()[:120]
    if not clave:
        raise ErrNegocio("Falta a quién se le recordó.")
    ahora = datetime.now(timezone.utc)
    try:
        t = datetime.fromisoformat(str(cuando).replace("Z", "+00:00")) if cuando else ahora
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        t = min(t, ahora)
    except ValueError:
        t = ahora
    iso = t.isoformat()
    with _LOCK:
        m = _negocio(email)["recordados"]
        if str(m.get(clave) or "") < iso:
            m[clave] = iso
        corte = (ahora - timedelta(days=10)).isoformat()
        for k in [k for k, v in m.items() if k.startswith("res:") and str(v) < corte]:
            m.pop(k, None)
        return str(m.get(clave) or iso)


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
    if len(ms) > 1:  # selector de moneda (va en las acciones de la cabecera)
        chips = ("<nav class='va-seg vn-mon' aria-label='Moneda'>" + "".join(
            f"<a class='{'sel' if i == iso else ''}' href='?m={i}'" + (" aria-current='page'" if i == iso else "")
            + f">{e(s)} · {e(i)}</a>" for i, s in ms) + "</nav>")
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
    # Los estilos de "Tu negocio" viajan en el CSS versionado del sitio
    # (`web/estilos_anfitrion.py`); `.anf-ng` acota los que tocan clases genéricas.
    html = ("<div class='anf-pag anf-ng'><a class='anf-back' href='/anfitrion/mis-canchas'>‹ Mis canchas</a>" + _nav(activo) + cuerpo
            + f"</div><script>{JS_TIP}</script>")
    return ui.shell(titulo, html, nav=_cabecera(tab, ses), sesion=ses, ancho=True, titulo_tab=f"{titulo} · Modo anfitrión")


# ── Rediseño del diseñador (16-nov-2026): vistas con el kit ─────────────────
# `_pagina` queda para quien lo importa desde otro módulo (Recordar reservas,
# `web/jugador_pro.py`); las páginas de este módulo usan `_render`: la barra
# superior del modo anfitrión va sola (`ui.shell`) y la vista lleva el kit
# (`web/vista_anfitrion.py`) + la hoja `web/estilos_v_negocio.py` (`.vn-*`).

# Íconos de línea que `web/iconos.py` no trae (mismo trazo 24×24, currentColor).
_SVG = {
    "fuego": "<path d='M12 21c-3.9 0-6.5-2.6-6.5-6.2 0-3.4 2.4-5.6 3.9-7.7.4 1.6 1.2 2.7 2.3 3.3.2-3 1.4-5.6 3.6-7.4.3 3 1.7 4.6 2.9 6.4"
             ".9 1.4 1.3 2.9 1.3 4.6C19.5 18.4 16 21 12 21z'/>",
    "xcirc": "<circle cx='12' cy='12' r='9'/><path d='M9 9l6 6M15 9l-6 6'/>",
    "check": "<circle cx='12' cy='12' r='9'/><path d='M8 12.3l2.7 2.7L16.2 9.5'/>",
    "alerta": "<path d='M12 3.5l9.5 16.5h-19z'/><path d='M12 10v4.5M12 17.4v.01' stroke-width='2.6'/>",
    "sol": "<circle cx='12' cy='12' r='4'/><path d='M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.3 5.3l1.4 1.4M17.3 17.3l1.4 1.4M5.3 18.7l1.4-1.4M17.3 6.7l1.4-1.4'/>",
    "luna": "<path d='M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z'/>",
    "candado": "<rect x='4.5' y='10.5' width='15' height='10' rx='2'/><path d='M8 10.5V7.5a4 4 0 0 1 8 0v3'/>",
    "enviar": "<path d='M21 3L10.5 13.5M21 3l-6.5 18-4-7.5-7.5-4z'/>",
    "lapiz": "<path d='M4 20h4L19 9a2.8 2.8 0 0 0-4-4L4 16z'/><path d='M13.5 6.5l4 4'/>",
    "pausa": "<path d='M9 5.5v13M15 5.5v13'/>",
    "play": "<path d='M7.5 5l11 7-11 7z'/>",
    "basura": "<path d='M4 7h16M9.5 7V4.5h5V7M6.5 7l1 13h9l1-13'/>",
    "mas": "<path d='M12 5v14M5 12h14'/>",
    "usuario": "<circle cx='12' cy='8' r='4'/><path d='M4.5 20.5c.8-4 3.8-6 7.5-6s6.7 2 7.5 6'/>",
    "repetir": "<path d='M4 11V9a3 3 0 0 1 3-3h12l-3-3M20 13v2a3 3 0 0 1-3 3H5l3 3'/>",
    "pastel": "<path d='M12 3a9 9 0 1 0 9 9h-9z'/><path d='M15 2.6A9 9 0 0 1 21.4 9H15z'/>",
    "celular": "<rect x='6.5' y='2.5' width='11' height='19' rx='2.2'/><path d='M11 18.2h2'/>",
    "info": "<circle cx='12' cy='12' r='9'/><path d='M12 11v5.5M12 7.6v.01' stroke-width='2.6'/>",
    "descargar": "<path d='M12 4v11M7 10.5l5 5 5-5M5 20h14'/>",
}


def _svg(clave: str, tam: int = 18, grueso: float = 2.2) -> str:
    from web import iconos
    if iconos.existe(clave):
        return iconos.svg(clave, tam, grueso=grueso)
    cuerpo = _SVG.get(clave, "")
    if not cuerpo:
        return ""
    return (f"<svg class='ic-l' viewBox='0 0 24 24' width='{tam}' height='{tam}' fill='none' stroke='currentColor' "
            f"stroke-width='{grueso}' stroke-linecap='round' stroke-linejoin='round' aria-hidden='true'>{cuerpo}</svg>")


def _ic(clave: str, color: str = "azul", tam: int = 18) -> str:
    """Ícono blanco en cuadrado de color (`va-ic` del kit; color por clase)."""
    if color == "suave":
        return f"<span class='va-ic suave'>{_svg(clave, tam)}</span>"
    return f"<span class='va-ic vn-c-{e(color)}'>{_svg(clave, tam)}</span>"


def _cifra(ico: str, titulo: str, valor: str, *, color: str = "azul", sub: str = "", tono: str = "") -> str:
    """Tarjeta de cifra del kit (`va-kpi`) con los íconos de este módulo.
    [valor] es HTML ya escapado; [tono] "warn" (dorado) · "bad" · "ok"."""
    v = f"<b class='{e(tono)}'>{valor}</b>" if tono else f"<b>{valor}</b>"
    return (f"<div class='va-kpi'><div class='va-kpi-c'>{_ic(ico, color)}<span>{e(titulo)}</span></div>"
            f"<div class='va-kpi-v'>{v}" + (f"<small>{sub}</small>" if sub else "") + "</div></div>")


def _render(titulo: str, contenido: str, ses: dict, *, js: str = "", tab: str = "", clase: str = "") -> HTMLResponse:
    """Página del módulo con el kit: barra del anfitrión (sola, `ui.shell`) +
    vista de 1120 px. [js] = scripts propios (van después de los comunes)."""
    html = va.vista(contenido, f"vn {clase}".strip()) + f"<script>{JS_TIP}{JS_VN}{js}</script>"
    return ui.shell(titulo, html, sesion=ses, ancho=True, titulo_tab=f"{tab or titulo} · Modo anfitrión")


TABS_ICO = {"resumen": "barras", "ocupacion": "fuego", "cobros": "billete", "cancelaciones": "xcirc"}


def _tabs_rep(activo: str) -> str:
    """Pestañas subrayadas con ícono de Reportes (Resumen · Ocupación · Cobros ·
    Cancelaciones), como el diseño."""
    return ("<nav class='vn-tabs' aria-label='Reportes'>" + "".join(
        f"<a href='{href}' class='{'sel' if k == activo else ''}'" + (" aria-current='page'" if k == activo else "")
        + f">{_svg(TABS_ICO[k], 17)}{e(n)}</a>" for k, n, href in TABS_REPORTES) + "</nav>")


def _grafico(valores: list[float], etiquetas: list[str], sim: str, titulo: str, *, hoy_idx: int = -1, cada: int = 1,
             col: str = "Día") -> str:
    """Barras verticales de UNA serie con líneas guía: rótulo con el monto en la
    barra más alta y en la de hoy (la de hoy en azul claro, como el diseño),
    tooltip por barra y "Ver como tabla ›" (tabla accesible desplegable).
    [cada] = cada cuántas barras se escribe la etiqueta del eje (30 días)."""
    mx = max(valores) if valores else 0
    paso = 1
    for p in (1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000, 50000, 100000):
        paso = p
        if p * 4 >= mx:
            break
    techo = max(paso * 4, 1)
    guias = "".join(f"<i style='bottom:{k * 25}%'></i>" for k in range(5))
    i_max = valores.index(mx) if mx > 0 else -1
    barras = ""
    for i, (v, t) in enumerate(zip(valores, etiquetas)):
        rot = v > 0 and (i == i_max or i == hoy_idx)
        etq = t if (i == hoy_idx or i % cada == 0) else ""
        barras += (f"<div class='vn-bar{' hoy' if i == hoy_idx else ''}' data-tip='{e(t)} · {e(_m(v, sim))}' tabindex='0'>"
                   f"<div class='vn-bar-c'>" + (f"<small>{e(_m(v, sim, 0))}</small>" if rot else "")
                   + f"<i style='height:{0 if techo <= 0 else round(v * 100 / techo, 2)}%'></i></div>"
                   f"<span>{e(etq)}</span></div>")
    tabla = "".join(f"<tr><th scope='row'>{e(t)}</th><td>{e(_m(v, sim))}</td></tr>" for v, t in zip(valores, etiquetas))
    return (f"<div class='vn-graf'><div class='vn-guias' aria-hidden='true'>{guias}</div>"
            f"<div class='vn-barras' role='img' aria-label='{e(titulo)}'>{barras}</div></div>"
            f"<details class='vn-tabla'><summary>Ver como tabla ›</summary><table class='va-tabla'><thead><tr><th scope='col'>{e(col)}</th>"
            f"<th scope='col'>Cobrado</th></tr></thead><tbody>{tabla}</tbody></table></details>")


def _hbarras_v(filas: list[tuple[str, float, str]], sim: str) -> str:
    """Barras horizontales (ingreso por cancha / por medio), normalizadas al máximo."""
    mx = max((v for _, v, _ in filas), default=0)
    return "".join(
        f"<div class='vn-hb' data-tip='{e(n)} · {e(_m(v, sim))}'><div class='vn-hb-t'><b>{e(n)}</b>"
        + (f"<small>{e(sub)}</small>" if sub else "") + f"<span>{e(_m(v, sim))}</span></div>"
        f"<div class='vn-hb-p'><i style='width:{0 if mx <= 0 else max(2, round(v / mx * 100))}%'></i></div></div>"
        for n, v, sub in filas)


def _fecha_picker(dia: date, hoy: date, campos: dict, etiqueta: str) -> str:
    """Botón "📅 Hoy · mié 11 nov" que abre el calendario del navegador (el
    `<input type=date>` va encima, transparente) y envía el formulario."""
    ocultos = "".join(f"<input type='hidden' name='{e(k)}' value='{e(v)}'>" for k, v in campos.items())
    return (f"<form method='get' class='vn-fecha'>{ocultos}<span class='vn-fecha-t'>{_svg('calendario', 16)}{e(etiqueta)}</span>"
            f"<input type='date' name='fecha' value='{dia.isoformat()}' aria-label='Elegir día' data-vn-fecha></form>")


def _hoy_de(canchas: list[dict]) -> datetime:
    return horarios.ahora_local(_pais_de(canchas[0]) if canchas else "PE")


def _slots(c: dict) -> list[str]:
    return horarios.slots(c.get("hora_apertura") or "07:00", c.get("hora_cierre") or "23:00", int(c.get("duracion_slot_min") or 60))


def _slots_dia_semana(c: dict, dia: int) -> list[str]:
    """Turnos del día de la semana `dia` (1 = lunes) con el horario por día
    de las REGLAS del club (`null` = cerrado ese día); sin regla, el general."""
    hs = (_reglas.de_cancha(c).get("horario_semana") or {})
    clave = _reglas.DIAS_SEMANA[(dia - 1) % 7]
    if clave not in hs:
        return _slots(c)
    if hs[clave] is None:
        return []
    return horarios.slots(hs[clave]["apertura"], hs[clave]["cierre"], int(c.get("duracion_slot_min") or 60))


def _n_res(n: int) -> str:
    return f"{n} reserva{'' if n == 1 else 's'}"


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


def _json_ok(**kw) -> JSONResponse:
    return JSONResponse({"ok": True, **kw})


def _err(msg: str, status: int = 400, **kw) -> JSONResponse:
    return JSONResponse({"ok": False, "error": msg, **kw}, status_code=status)


# ── Reportes · Resumen (reportes_screen.dart) ───────────────────────────────

@router.get("/anfitrion/reportes", response_class=HTMLResponse)
def pagina_resumen(request: Request, m: str = "", d: str = "7") -> HTMLResponse:
    ses, canchas, resp = _contexto(request, "/anfitrion/reportes")
    if resp is not None:
        return resp
    canchas, iso, sim, chips = _por_moneda(canchas, m)
    ahora = _hoy_de(canchas)
    hoy = ahora.date()
    clave = hoy.isoformat()[:7]
    ndias = 30 if d == "30" else 7
    ids = [c["id"] for c in canchas]
    desde = min((hoy - timedelta(days=40)).replace(day=1), hoy - timedelta(days=ndias - 1))
    filas = reservas_dueno(ids, desde.isoformat(), (hoy + timedelta(days=62)).isoformat())
    del_mes = [r for r in filas if r["fecha"].startswith(clave) and not es_noshow(r)]
    ingreso = sum(r["precio"] for r in del_mes if r["pagado"])
    por_cobrar = sum(r["precio"] for r in del_mes if not r["pagado"])
    serie, etq = [], []
    for i in range(ndias - 1, -1, -1):
        dd = hoy - timedelta(days=i)
        serie.append(float(sum(r["precio"] for r in filas if r["fecha"] == dd.isoformat() and r["pagado"])))
        etq.append("Hoy" if i == 0 else (f"{horarios.DIAS[dd.weekday()]} {dd.day}" if ndias == 7 else f"{dd.day} {MESES_CORTO[dd.month - 1]}"))
    res_hoy = sum(1 for r in filas if r["fecha"] == hoy.isoformat() and not es_noshow(r))
    slots_hoy = sum(len(_slots(c)) for c in canchas)
    pct = (res_hoy * 100) // slots_hoy if slots_hoy else 0
    seg = va.segmentado([(f"?d=7&m={iso}", "7 días", ndias == 7), (f"?d=30&m={iso}", "30 días", ndias == 30)], etiqueta="Período del gráfico")
    grafico = _grafico(serie, etq, sim, f"Cobrado por día, últimos {ndias} días", hoy_idx=len(serie) - 1, cada=1 if ndias == 7 else 5)
    ingresos = ("<section class='va-panel vn-ing' aria-labelledby='vnIngT'><div class='vn-ing-cab'>"
                f"<div class='vn-ing-t'>{_ic('billete')}<h2 id='vnIngT'>Ingresos del mes (cobrado)</h2></div>{seg}</div>"
                f"<b class='vn-ing-v'>{e(_m(ingreso, sim, 0))}</b>"
                + (grafico if filas else va.vacio("barras", "Aún no hay reservas en tus canchas",
                                                   "Cuando lleguen, aquí verás tus números reales."))
                + "</section>")
    lado = ("<div class='vn-col'>"
            + _cifra("calendario", "Reservas del mes", str(len(del_mes)))
            + _cifra("recibo", "Por cobrar del mes", e(_m(por_cobrar, sim, 0)), tono="warn" if por_cobrar else "")
            + _cifra("pastel", "Ocupación de hoy", f"{pct}%", sub=f"{res_hoy} de {slots_hoy} turnos") + "</div>")
    mas = "".join(
        f"<a class='vn-mas' href='{h}'>{_ic(ico, 'suave')}<span><b>{e(t)}</b><small>{e(s)}</small></span><i aria-hidden='true'>›</i></a>"
        for t, s, h, ico in (("Ocupación", "Mapa de calor y horas pico", "/anfitrion/ocupacion", "fuego"),
                             ("Cobros", "Por período, local y cancha", "/anfitrion/reportes/cobros", "billete"),
                             ("Billetera", "Saldo y por recibir", "/anfitrion/ingresos", "tarjeta")))
    cuerpo = (va.cabecera(f"Reportes · {MESES_LARGO[hoy.month - 1]}", "Tu cuaderno, en tiempo real: lo que cobras en tus canchas.",
                          acciones=chips)
              + _tabs_rep("resumen")
              + f"<div class='vn-dos'>{ingresos}{lado}</div>"
              + f"<h2 class='vn-sec'>Más reportes</h2><div class='vn-mas-g'>{mas}</div>")
    return _render("Reportes", cuerpo, ses)


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
    tit = f"Cuánto vas a recibir de {MARCA}"
    if total <= 0:
        return va.panel("<p class='vn-tenue'>Nada pendiente por ahora. Cuando un jugador pague en línea, el neto aparece aquí y en tu billetera.</p>",
                        tit)

    def bloque(t, s, v):
        return f"<div class='vn-rc'><div><b>{e(t)}</b><small>{s}</small></div><span>{e(_m(v, sim))}</span></div>"
    return va.panel(
        (bloque(f"Reservas online ({n_on})", f"La comisión ({e(_m(com_on, sim))}) se descontó del pago · recibes el neto", rec_on) if n_on else "")
        + (bloque(f"Reservas pagadas con tu saldo ({n_sal})", f"Recibes el 100% · la comisión ({e(_m(com_sal, sim))}) salió de tu billetera", rec_sal) if n_sal else "")
        + f"<div class='vn-rc tot'><b>Total por recibir</b><span>{e(_m(total, sim))}</span></div>"
        f"<p class='vn-nota'>Este total es EXACTO el \"Por recibir\" de tu <a href='/anfitrion/ingresos'>billetera</a>. "
        f"Comisión total: {e(_m(com_on + com_sal, sim))} ({e(_m(com_on, sim))} del pago + {e(_m(com_sal, sim))} de tu saldo).</p>", tit)


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
        f"<div class='vn-local'><div class='vn-local-h'><b>{e(loc)}</b><span>{e(_m(sum(v for _, v, _ in lst), sim))}</span></div>{_hbarras_v(lst, sim)}</div>"
        for loc, lst in sorted(locales.items(), key=lambda kv: -sum(v for _, v, _ in kv[1])))
    seg = va.segmentado([(f"?r={k}&m={iso}", t, k == rango) for k, t in RANGOS], etiqueta="Período")
    txt_rango = f"{a.day} {MESES_CORTO[a.month - 1]} {a.year} – {b.day} {MESES_CORTO[b.month - 1]} {b.year}" if rango != "todo" else "Todo el historial"
    filas = [[f"<b>{e(x['jugador'] or 'Jugador')}</b><small>{e((por_id.get(x['cancha_id']) or {}).get('nombre') or 'Cancha')}</small>",
              f"{e(_fecha_bonita(x['fecha'], hoy))}<small>{e(x['hora_inicio'])}</small>",
              _pill_estado(x), f"<b>{e(_m(total_con_extras(x), sim))}</b>"] for x in del_rango[:120]]
    csv_url = f"/anfitrion/reportes/cobros.csv?r={rango}&desde={a.isoformat()}&hasta={b.isoformat()}&m={iso}"
    cuerpo = (
        va.cabecera("Reporte de cobros", "Facturación de tus canchas por período, local y cancha.",
                    acciones=chips + f"<a class='btn sec' href='{e(csv_url)}'>{_svg('descargar', 17)} Descargar CSV</a>")
        + _tabs_rep("cobros")
        + f"<div class='vn-filtros'>{seg}"
        f"<form class='vn-rango' method='get'><input type='hidden' name='r' value='custom'><input type='hidden' name='m' value='{iso}'>"
        f"<label>Desde<input type='date' name='desde' value='{a.isoformat() if rango != 'todo' else ''}' required></label>"
        f"<label>Hasta<input type='date' name='hasta' value='{b.isoformat() if rango != 'todo' else ''}' required></label>"
        "<button class='btn sec' type='submit'>Ver período</button></form></div>"
        f"<p class='vn-tenue vn-rango-t'>{e(txt_rango)}</p>"
        + "<div class='vn-k5'>" + va.kpis([_cifra("check", "Cobrado", e(_m(facturado, sim, 0))),
                   _cifra("recibo", "Por cobrar", e(_m(por_cobrar, sim, 0)), tono="warn" if por_cobrar else ""),
                   _cifra("calendario", "Reservas", str(n)), _cifra("etiqueta", "Ticket promedio por reserva", e(_m(ticket, sim))),
                   _cifra("billete", f"Comisión {MARCA} estimada", e(_m(comision, sim)), sub="5 % de las reservas que trajo la app")]) + "</div>"
        + _resumen_comision(ses["email"], iso, sim)
        + va.panel(_grafico(tot6, [f"{MESES_CORTO[mm - 1]} {str(yy)[2:]}" for yy, mm in meses], sim, "Cobrado por mes, últimos 6 meses",
                            hoy_idx=5, col="Mes"), "Ingresos cobrados (últimos 6 meses)")
        + (va.panel(bloque_locales, "Por local y cancha") if bloque_locales else "")
        + va.panel(va.tabla(["Jugador", "Cuándo", "Estado", "Monto"], filas, vacia=va.vacio("calendario", "Sin reservas en este rango"))
                   + (f"<p class='vn-tenue'>Se muestran las 120 más recientes. El CSV trae todas.</p>" if len(del_rango) > 120 else ""),
                   f"Reservas ({n})", f"{sum(1 for x in del_rango if x['pagado'])} pagadas"))
    return _render("Reporte de cobros", cuerpo, ses)


def _estado_txt(x: dict) -> str:
    if es_noshow(x):
        return "No-show"
    if es_bono(x):
        return "Bono"
    return "Pagada" if x["pagado"] else "Por cobrar"


def _pill_estado(x: dict) -> str:
    est = _estado_txt(x)
    return va.pill(est, {"Pagada": "ok", "Por cobrar": "warn", "No-show": "bad", "Bono": "info"}.get(est, "gris"))


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
    nombre = f"{MARCA.lower()}-cobros-{a.isoformat()}-{b.isoformat()}.csv" if rango != "todo" else f"{MARCA.lower()}-cobros.csv"
    return Response("﻿" + buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f"attachment; filename={nombre}"})


# ── Reportes · Ocupación (analitica_ocupacion_screen.dart) ──────────────────

PERIODOS = [("d30", "30 días"), ("d90", "90 días"), ("mes", "Este mes"), ("todo", "Todo")]
# RAMPA (escala del mapa de calor) vive en `web/estilos_anfitrion.py`: cada celda lleva `n<nivel>`.


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


DIAS_PLURAL = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábados", "domingos"]
# Umbrales de las sugerencias automáticas de Ocupación (reglas, sin IA).
SUG_MIN_DIAS = 14        # período mínimo para sacar conclusiones
SUG_MIN_RESERVAS = 20    # reservas mínimas en el período
SUG_LLENA = 0.6          # una hora "se llena" si se ocupa ≥ 60 % de las veces que se ofrece
SUG_CASI_TODOS = 0.75    # … "casi todos los días" desde el 75 %
SUG_MANANA_VACIA = 0.10  # las mañanas de un día "casi no se usan" si se ocupan ≤ 10 %
SUG_MIN_CAP = 8          # turnos ofrecidos mínimos para juzgar una hora o una mañana


def sugerencias_ocupacion(activas: list[dict], canchas: list[dict], desde: date, hoy: date) -> list[dict]:
    """Dos sugerencias automáticas sobre el mapa de calor (diseño, Frame 22):
    (1) la hora que se llena casi siempre → subir el precio de punta (Reglas);
    (2) el día cuyas mañanas casi no se usan → promo de hora valle (Llenar
    cancha). Tasa = reservas / turnos ofrecidos en el período (por día de la
    semana, con el horario de las reglas del club). Sin datos suficientes
    (menos de `SUG_MIN_DIAS` días o `SUG_MIN_RESERVAS` reservas) no sugiere nada."""
    dias = (hoy - desde).days + 1
    if dias < SUG_MIN_DIAS or len(activas) < SUG_MIN_RESERVAS or not canchas:
        return []
    n_wd = [0] * 7
    for i in range(dias):
        n_wd[(desde + timedelta(days=i)).weekday()] += 1
    ofrece: dict[tuple[str, int, str], bool] = {}
    cap: dict[tuple[int, str], int] = {}
    for c in canchas:
        for wd in range(7):
            for h in _slots_dia_semana(c, wd + 1):
                ofrece[(c["id"], wd, h)] = True
                cap[(wd, h)] = cap.get((wd, h), 0) + n_wd[wd]
    uso: dict[tuple[int, str], int] = {}
    por_cancha_hora: dict[tuple[str, str], int] = {}
    for r in activas:
        try:
            wd = date.fromisoformat(r["fecha"]).weekday()
        except ValueError:
            continue
        h = r["hora_inicio"]
        if not ofrece.get((r["cancha_id"], wd, h)):
            continue
        uso[(wd, h)] = uso.get((wd, h), 0) + 1
        por_cancha_hora[(r["cancha_id"], h)] = por_cancha_hora.get((r["cancha_id"], h), 0) + 1
    out: list[dict] = []
    # (1) hora que se llena
    horas = sorted({h for (_wd, h) in cap})
    mejor, tasa_mejor = "", 0.0
    for h in horas:
        c_h = sum(cap.get((wd, h), 0) for wd in range(7))
        if c_h < SUG_MIN_CAP:
            continue
        t = sum(uso.get((wd, h), 0) for wd in range(7)) / c_h
        if t > tasa_mejor:
            mejor, tasa_mejor = h, t
    if mejor and tasa_mejor >= SUG_LLENA:
        cid = max((c["id"] for c in canchas), key=lambda x: por_cancha_hora.get((x, mejor), 0))
        out.append({"tipo": "punta", "titulo": f"{mejor} se llena {'casi todos los días' if tasa_mejor >= SUG_CASI_TODOS else 'la mayoría de los días'}",
                    "texto": "Es tu mejor hora: puedes subir el precio de punta.", "cta": "Reglas de reserva",
                    "href": f"/anfitrion/reglas/{quote(cid)}", "tasa": round(tasa_mejor, 2)})
    # (2) mañanas vacías (turnos que empiezan antes de las 12:00)
    peor, tasa_peor = -1, 2.0
    for wd in range(7):
        c_m = sum(v for (d, h), v in cap.items() if d == wd and (horarios.hora_en_minutos(h) or 0) < 12 * 60)
        if c_m < SUG_MIN_CAP:
            continue
        t = sum(v for (d, h), v in uso.items() if d == wd and (horarios.hora_en_minutos(h) or 0) < 12 * 60) / c_m
        if t < tasa_peor:
            peor, tasa_peor = wd, t
    if peor >= 0 and tasa_peor <= SUG_MANANA_VACIA:
        out.append({"tipo": "valle", "titulo": f"Las mañanas de los {DIAS_PLURAL[peor]} casi no se usan",
                    "texto": "Lánzalas con una promo de hora valle.", "cta": "Llenar cancha", "href": "/anfitrion/llenar",
                    "tasa": round(tasa_peor, 2)})
    return out


@router.get("/anfitrion/ocupacion", response_class=HTMLResponse)
def pagina_ocupacion(request: Request, p: str = "d90", m: str = "", cancha: str = "") -> HTMLResponse:
    ses, canchas, resp = _contexto(request, "/anfitrion/ocupacion")
    if resp is not None:
        return resp
    canchas, iso, sim, chips = _por_moneda(canchas, m)
    todas_c = canchas
    if cancha and any(c["id"] == cancha for c in canchas):
        canchas = [c for c in canchas if c["id"] == cancha]
    else:
        cancha = ""
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
    # Mapa de calor como el diseño: filas = días (L..D), columnas = horas.
    n_h = len(horas_l)
    hm = "<div></div>" + "".join(f"<div class='vn-hm-h'>{e(h[:2] if h.endswith(':00') else h[2:])}</div>" for h in horas_l)
    for ds in range(7):
        hm += f"<div class='vn-hm-d'>{horarios.DIAS[ds]}</div>"
        for h in horas_l:
            v = celda.get((ds, h), 0)
            nivel = 0 if v == 0 or mx == 0 else min(5, 1 + int((v / mx) * 4.999))
            hm += (f"<div class='hm-c vn-hm-c n{nivel}' tabindex='0' "
                   f"data-tip='{DIAS_TIT[ds]} {e(h)} · {v} reserva{'s' if v != 1 else ''}'></div>")
    leyenda = ("<div class='vn-hm-ley' aria-hidden='true'><span>Menos</span><i class='hm-c n0'></i>"
               + "".join(f"<i class='hm-c n{i}'></i>" for i in range(1, len(RAMPA))) + "<span>Más reservas</span></div>")
    tabla_hm = "".join(f"<tr><th scope='row'>{DIAS_TIT[d]}</th>" + "".join(f"<td>{celda.get((d, h), 0)}</td>" for h in horas_l) + "</tr>"
                       for d in range(7))
    media = any(not h.endswith(":00") for h in horas_l)
    mapa = ((f"<div class='vn-hm-w'><div class='vn-hm' style='grid-template-columns:44px repeat({n_h},minmax(26px,1fr))' role='img' "
             f"aria-label='Reservas por día de la semana y hora'>{hm}</div></div>"
             + (f"<p class='vn-nota'>“:30” = turnos que empiezan a la media hora, por los turnos de más de una hora.</p>" if media else "")
             + "<details class='vn-tabla'><summary>Ver como tabla ›</summary><div class='va-tabla-w'><table class='va-tabla'><thead><tr><th scope='col'>Día</th>"
             + "".join(f"<th scope='col'>{e(h)}</th>" for h in horas_l) + f"</tr></thead><tbody>{tabla_hm}</tbody></table></div></details>")
            if horas_l else "<p class='vn-tenue'>Configura el horario de tus canchas para ver el mapa.</p>")
    sugs = sugerencias_ocupacion(activas, canchas, desde, hoy)
    sug_html = "".join(
        f"<div class='vn-sug {x['tipo']}'>{_ic('fuego' if x['tipo'] == 'punta' else 'etiqueta', 'suave')}"
        f"<div class='vn-sug-t'><b>{e(x['titulo'])}</b><small>{e(x['texto'])}</small></div>"
        f"<a href='{e(x['href'])}'>{e(x['cta'])} ›</a></div>" for x in sugs)
    ing_filas = [((por_id.get(cid) or {}).get("nombre") or "Cancha", float(v), (por_id.get(cid) or {}).get("club") or "")
                 for cid, v in sorted(ing.items(), key=lambda kv: -kv[1])]
    # Reputación real (⭐ de pichangol_resenas).
    res = _resenas(ids)
    estrellas = [int(x.get("estrellas") or 0) for x in res if int(x.get("estrellas") or 0) > 0]
    prom = sum(estrellas) / len(estrellas) if estrellas else 0
    ult = [x for x in res if str(x.get("comentario") or "").strip()][:3]
    rep = va.panel(
        (f"<div class='vn-rep'><b>{prom:.1f}</b><span aria-label='{prom:.1f} de 5'>{'★' * round(prom)}{'☆' * (5 - round(prom))}</span>"
         f"<small>{len(estrellas)} reseña{'s' if len(estrellas) != 1 else ''}</small></div>"
         + "".join(f"<div class='vn-resena'><b>{'★' * int(x.get('estrellas') or 0)}</b> {e(x.get('comentario'))}<small>{e(x.get('autor_nombre') or '')}</small></div>" for x in ult)
         if estrellas else "<p class='vn-tenue'>Aún no tienes reseñas. Llegan cuando los jugadores califican su reserva.</p>"), "Tu reputación")
    seg = va.segmentado([(f"?p={k}&m={iso}" + (f"&cancha={quote(cancha)}" if cancha else ""), t, k == p) for k, t in PERIODOS], etiqueta="Período")
    opts = "<option value=''>Todas las canchas</option>" + "".join(
        f"<option value='{e(c['id'])}'{' selected' if c['id'] == cancha else ''}>{e(c.get('nombre') or 'Cancha')}"
        + (f" · {e(c.get('club'))}" if c.get("club") and len({x.get('club') for x in todas_c}) > 1 else "") + "</option>" for c in todas_c)
    sel = (f"<form method='get' class='vn-sel'><input type='hidden' name='p' value='{p}'><input type='hidden' name='m' value='{iso}'>"
           f"<label class='vh' for='vnCancha'>Cancha</label>{_svg('cancha', 17)}<select id='vnCancha' name='cancha' data-vn-auto>{opts}</select>"
           "<noscript><button class='btn sec' type='submit'>Ver</button></noscript></form>") if len(todas_c) > 1 else ""
    cuerpo = (
        va.cabecera("Ocupación", "Cuándo se llenan tus canchas: decide precios, promos de hora valle y en qué cancha invertir.", acciones=chips)
        + _tabs_rep("ocupacion")
        + f"<div class='vn-filtros'>{seg}{sel}</div>"
        + va.kpis([_cifra("pastel", "Ocupación promedio", f"{ocup}%", sub=f"{_n_res(len(activas))} en {dias} día{'s' if dias != 1 else ''}"),
                   _cifra("reloj", "Hora pico", e(hora_pico or "Sin datos"), sub=_n_res(por_hora.get(hora_pico, 0)) if hora_pico else ""),
                   _cifra("calendario", "Día pico", e(DIAS_TIT[dia_pico] if dia_pico >= 0 else "Sin datos"),
                          sub=_n_res(por_dia[dia_pico]) if dia_pico >= 0 else ""),
                   _cifra("alerta", "No-show", f"{ns_pct}%", sub=f"{noshows} de {len(en)}", tono="bad" if ns_pct >= 10 else "")])
        + ("" if activas else va.aviso("Sin reservas en este período. Cuando lleguen, aquí verás cuándo se llena tu local.", "info", ico="info"))
        + va.panel(mapa, "Mapa de calor · día × hora", acciones=leyenda if horas_l else "", clase="vn-hm-p")
        + (f"<div class='vn-sugs'>{sug_html}</div>" if sug_html else "")
        + (va.panel(_hbarras_v(ing_filas, sim), "Ingreso cobrado por cancha") if ing_filas else "")
        + "<h2 class='vn-sec'>Mes vs mes</h2>"
        + va.kpis([_cifra("billete", f"{MESES_LARGO[hoy.month - 1].capitalize()} (cobrado)", e(_m(ing_mes, sim, 0)), sub=e(var)),
                   _cifra("billete", f"{MESES_LARGO[int(pasado[5:7]) - 1].capitalize()} (cobrado)", e(_m(ing_pas, sim, 0)), color="claro")])
        + rep)
    return _render("Ocupación", cuerpo, ses)


# ── Reportes · Cancelaciones (cancelaciones_screen.dart) ────────────────────

_REEMBOLSO = {"reembolsado": "Devuelto al jugador por la pasarela", "reembolsado_manual": "Devuelto al jugador (a mano)",
              "devuelto_saldo": "Devuelto al saldo del jugador", "manual": f"Devolución pendiente del equipo {MARCA}",
              "fallo": f"Devolución pendiente del equipo {MARCA}", "sin_reembolso": "Canceló tarde · sin devolución",
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
    filas = [[f"<b>{e(x['jugador'] or 'Jugador')}</b><small>Cancelada {e(cuando(x['cuando']))}</small>",
              f"{e(x['lugar'])}<small>{e(horarios.fecha_larga(x['fecha']))} · {e(x['hora'])}{(' · ' + e(x['quien'])) if x['quien'] else ''}</small>",
              f"<b>{e(x['monto'])}</b>", va.pill(x["estado"], "ok" if x["favor"] else "gris")] for x in items]
    n_favor = sum(1 for x in items if x["favor"])
    cuerpo = (va.cabecera("Cancelaciones", "Reservas que se cancelaron en tus canchas y qué pasó con la plata.")
              + _tabs_rep("cancelaciones")
              + (va.kpis([_cifra("xcirc", "Cancelaciones", str(len(items))),
                          _cifra("check", "Con plata de por medio", str(n_favor), sub="revisa la devolución o la seña a tu favor")]) if items else "")
              + va.panel(va.tabla(["Jugador", "Dónde y cuándo", "Monto", "Qué pasó con la plata"], filas, clase="vn-canc",
                                  vacia=va.vacio("calendario", "Sin cancelaciones", "Cuando alguien cancele, aquí verás qué pasó con la plata.")),
                         "Historial" if items else ""))
    return _render("Cancelaciones", cuerpo, ses)


# ── Caja del día (caja_dia_screen.dart) ─────────────────────────────────────

def _medio_etq(k: str, pais: str) -> str:
    """Nombre del medio por país: Yape/Plin solo en Perú (fuera, QR o transferencia)."""
    return {"yape": "Yape / Plin" if pais == "PE" else "QR / transferencia", "tarjeta": "Tarjeta", "efectivo": "Efectivo",
            "manual": "Manual", "sena": "Señas (online)"}.get(k, "Online")


_MEDIO_ICO = {"yape": "celular", "tarjeta": "tarjeta", "efectivo": "billete", "manual": "lapiz", "sena": "candado"}


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
def pagina_caja(request: Request, fecha: str = "", m: str = "", ver: str = "") -> HTMLResponse:
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
    antes = ui.json_js(neg["cierres"], sort_keys=True)
    _autocerrar(neg, filas, canchas, iso_mon, ahora)
    if ui.json_js(neg["cierres"], sort_keys=True) != antes:
        _persistir()
    c = caja_dia(filas, dia.isoformat(), canchas)
    pais = _pais_de(canchas[0]) if canchas else "PE"
    cierre = next((x for x in neg["cierres"] if x.get("fecha") == dia.isoformat() and x.get("moneda", "PEN") == iso_mon), None)
    # Por dónde entró la plata: barras por medio sobre el total cobrado.
    medios = "".join(
        f"<div class='vn-medio'>{_ic(_MEDIO_ICO.get(k, 'tarjeta'), 'suave', 16)}<div class='vn-medio-t'><div><b>{e(_medio_etq(k, pais))}</b>"
        f"<span>{e(_m(v, sim, 0))}</span></div><div class='vn-hb-p'><i style='width:{max(2, round(v * 100 / c['cobrado'])) if c['cobrado'] else 0}%'>"
        "</i></div></div></div>" for k, v in sorted(c["medios"].items(), key=lambda kv: -kv[1]))
    medios_panel = va.panel(
        (medios + f"<div class='vn-medio-tot'><span>Total cobrado</span><b>{e(_m(c['cobrado'], sim, 0))}</b></div>") if medios
        else "<p class='vn-tenue'>Todavía no entró plata este día.</p>", "Por dónde entró la plata")
    pend = [r for r in c["lista"] if not r["pagado"] and not es_bono(r)]
    ver = ver if ver in ("pendientes", "todas") else ("pendientes" if pend else "todas")
    lista = pend if ver == "pendientes" else c["lista"]
    filas_html = ""
    for r in lista:
        cn = por_id.get(r["cancha_id"]) or {}
        t = total_con_extras(r)
        if es_bono(r):
            acc = va.pill("Bono", "info")
        elif r["pagado"]:
            medio = r["medio_pago"]
            acc = (va.pill(f"Pagada en línea · {medio}", "ok") if medio in ("yape", "tarjeta")
                   else f"<button type='button' class='btn sec vn-mini' data-pagar='{e(r['id'])}' data-v='0'>Marcar por cobrar</button>")
        else:
            acc = f"<button type='button' class='btn vn-mini' data-pagar='{e(r['id'])}' data-v='1'>{_svg('check', 16)} Marcar pagado</button>"
        sena = (f"<small class='vn-sena'>Seña {e(sim)} {r['sena']} pagada · cobra {e(_m(t - r['sena'], sim))}</small>"
                if r["sena"] > 0 and not r["pagado"] else "")
        filas_html += (f"<div class='vn-fila'>{_ic('reloj', 'suave', 16)}<div class='vn-fila-t'><b>{e(r['hora_inicio'])}–{e(r['hora_fin'])} · "
                       f"{e(r['jugador'] or 'Jugador')}</b><small>{e(cn.get('nombre') or 'Cancha')}{'' if r['traida_por_app'] else ' · reserva propia'}</small>"
                       f"{sena}</div><b class='vn-monto'>{e(_m(t, sim))}</b><div class='vn-fila-a'>{acc}</div></div>")
    q = f"fecha={dia.isoformat()}&m={iso_mon}"
    seg = va.segmentado([(f"?{q}&ver=pendientes", "Por cobrar", ver == "pendientes"), (f"?{q}&ver=todas", f"Todas ({len(c['lista'])})", ver == "todas")],
                        etiqueta="Reservas que se muestran")
    if filas_html:
        lista_html = f"<div class='vn-lista'>{filas_html}</div>"
        if ver == "pendientes" and len(c["lista"]) > len(pend):
            lista_html += f"<a class='vn-ver-todas' href='?{e(q)}&ver=todas'>Ver las {len(c['lista'])} reservas del día ›</a>"
    else:
        lista_html = va.vacio("calendario", "No hay reservas este día" if not c["lista"] else "Nada por cobrar",
                              "" if not c["lista"] else "Todas las reservas de este día ya están cobradas.")
    reservas_panel = va.panel(lista_html, "Reservas del día", acciones=seg if c["lista"] else "")
    # Cierre de caja (arqueo).
    if cierre:
        auto = bool(cierre.get("automatico"))
        cierre_html = (f"<div class='vn-arqueo'>{_ic('candado', 'naranja' if auto else 'verde', 17)}<div><b>"
                       f"{'Cierre automático (sin confirmar)' if auto else 'Caja cerrada'}</b>"
                       f"<small>Cobrado {e(_m(cierre.get('cobrado', 0), sim, 0))} · por cobrar {e(_m(cierre.get('porCobrar', 0), sim, 0))} · "
                       f"{_n_res(cierre.get('reservas', 0))}</small></div></div><div class='vn-arqueo-a'>"
                       + ("<button type='button' class='btn' data-caja='cerrar'>Confirmar arqueo</button>" if auto else "")
                       + "<button type='button' class='btn sec' data-caja='reabrir'>Reabrir</button></div>")
    else:
        cierre_html = (f"<div class='vn-arqueo'>{_ic('candado', 'naranja', 17)}<div><b>Cierre de caja (arqueo)</b>"
                       "<small>Cuenta el efectivo y cierra el día.</small></div></div>"
                       "<div class='vn-arqueo-a'><button type='button' class='btn' data-caja='cerrar'>Cerrar caja del día</button></div>")
    prev = [y for y in neg["cierres"] if y.get("moneda", "PEN") == iso_mon][:20]
    historial = "".join(
        f"<a class='vn-fila vn-hist' href='/anfitrion/caja?fecha={e(x['fecha'])}&m={iso_mon}'><div class='vn-fila-t'><b>{e(horarios.fecha_larga(x['fecha']))}</b>"
        f"<small>{_n_res(x.get('reservas', 0))} · por cobrar {e(_m(x.get('porCobrar', 0), sim, 0))}</small></div>"
        + va.pill("Automático" if x.get("automatico") else "Confirmado", "gris" if x.get("automatico") else "ok")
        + f"<b class='vn-monto'>{e(_m(x.get('cobrado', 0), sim, 0))}</b></a>" for x in prev)
    cierre_html += (f"<details class='vn-cierres'><summary>Cierres anteriores ({len(prev)})</summary><div class='vn-lista'>{historial}</div></details>"
                    if historial else "")
    cfg = {"fecha": dia.isoformat(), "m": iso_mon, "resumen": f"Cobrado: {sim} {c['cobrado']}" + "".join(
        f"\n{_medio_etq(k, pais)}: {sim} {v}" for k, v in c["medios"].items()) + f"\nPor cobrar: {sim} {c['por_cobrar']}\nReservas: {c['reservas']}"}
    etq = _fecha_bonita(dia.isoformat(), hoy)
    etq = f"Hoy · {horarios.DIAS[hoy.weekday()].lower()} {hoy.day} {MESES_CORTO[hoy.month - 1]}" if dia == hoy else (
        f"{etq} · {horarios.DIAS[dia.weekday()].lower()} {dia.day} {MESES_CORTO[dia.month - 1]}" if etq in ("Ayer", "Mañana") else etq)
    nav_dia = (f"<div class='vn-dia'><a class='vn-flecha' href='?fecha={(dia - timedelta(days=1)).isoformat()}&m={iso_mon}' aria-label='Día anterior'>‹</a>"
               + _fecha_picker(dia, hoy, {"m": iso_mon}, etq)
               + f"<a class='vn-flecha' href='?fecha={(dia + timedelta(days=1)).isoformat()}&m={iso_mon}' aria-label='Día siguiente'>›</a>"
               + (f"<a class='btn suave vn-hoy' href='?m={iso_mon}'>Hoy</a>" if dia != hoy else "") + "</div>")
    cuerpo = (
        va.cabecera("Caja del día", "La plata del día de un vistazo, el cobro en efectivo y el cierre de caja (arqueo).", acciones=chips + nav_dia)
        + va.kpis([_cifra("check", "Cobrado", e(_m(c["cobrado"], sim, 0))),
                   _cifra("recibo", "Por cobrar", e(_m(c["por_cobrar"], sim, 0)), tono="warn" if c["por_cobrar"] else ""),
                   _cifra("calendario", "Reservas", str(c["reservas"])), _cifra("pastel", "Ocupación", f"{c['ocupacion']}%")])
        + f"<div class='va-dos'><div>{reservas_panel}</div><div>{medios_panel}"
        + va.panel(cierre_html, clase="vn-cierre") + "</div></div>")
    return _render("Caja del día", cuerpo, ses, js=f"window.__caja={ui.json_js(cfg, ensure_ascii=False)};{JS_PAGAR}{JS_CAJA}")


@router.post("/anfitrion/caja/cerrar")
def cerrar_caja(request: Request, body: dict = Body(default_factory=dict)) -> JSONResponse:
    ses = sesion.de_request(request)
    if not ses:
        return _err("sesion_requerida", 401)
    try:
        r = cerrar_caja_de(ses["email"], str(body.get("fecha") or ""), str(body.get("m") or ""))
    except ErrNegocio as ex:
        return _err(ex.msg, ex.status)
    return _json_ok(cobrado=r["cobrado"], simbolo=r["simbolo"])


@router.post("/anfitrion/caja/reabrir")
def reabrir_caja(request: Request, body: dict = Body(default_factory=dict)) -> JSONResponse:
    ses = sesion.de_request(request)
    if not ses:
        return _err("sesion_requerida", 401)
    reabrir_caja_de(ses["email"], str(body.get("fecha") or ""), str(body.get("m") or "PEN"))
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
    from web import permisos  # dueño o su recepción (encargado del local)
    operables = permisos.canchas_para(ses["email"], permisos.NOSHOW)
    ids = [c["id"] for c in operables]
    if not ids:
        return _err("Esta reserva no es de tus canchas.", 404)
    fila = next((r for r in reservas_dueno(ids, "2020-01-01", "2100-01-01") if r["id"] == res_id), None)
    if fila is None:
        return _err("Esta reserva no es de tus canchas.", 404)
    if fila["pagado"] and fila["medio_pago"] in ("yape", "tarjeta"):
        return _err("Esta reserva se pagó en línea: no se marca como no-show.", 409)
    if not marcar_noshow(res_id, ids):
        return _err("No pudimos guardar en este momento.", 503)
    permisos.auditar(ses["email"], next((c for c in operables if c["id"] == fila.get("cancha_id")), None), "noshow", res_id)
    print(f"[noshow-web] {ses['email']} marcó no-show {res_id}", flush=True)
    return _json_ok()


# ── Clientes (clientes_screen.dart) ─────────────────────────────────────────

SEGMENTOS = [("todos", "Todos"), ("vip", "VIP"), ("recurrente", "Recurrentes"), ("nuevo", "Nuevos"),
             ("riesgo", "En riesgo"), ("moroso", "Deudores")]
# Color de cada insignia de segmento: `.ng-badge.s-<segmento>` en `web/estilos_anfitrion.py`.
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
def pagina_clientes(request: Request, seg: str = "todos", orden: str = "gasto", m: str = "") -> HTMLResponse:
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
    orden = orden if orden in ("frecuentes", "gasto", "recientes") else "gasto"
    lista = [c for c in todos if seg == "todos" or seg in c["segmentos"]]
    if orden == "gasto":
        lista.sort(key=lambda c: (-c["gastado"], -c["reservas"]))
    elif orden == "recientes":
        lista.sort(key=lambda c: c["ultima"], reverse=True)
    else:
        lista.sort(key=lambda c: (-c["reservas"], -c["gastado"]))
    recurrentes = sum(1 for c in todos if "recurrente" in c["segmentos"])
    nuevos = sum(1 for c in todos if "nuevo" in c["segmentos"])
    deudores = [c for c in todos if c["por_cobrar"] > 0]
    te_deben = sum(c["por_cobrar"] for c in deudores)
    chips_seg = "".join(
        f"<a class='vn-chip{' sel' if k == seg else ''}' href='?seg={k}&orden={orden}&m={iso_mon}'" + (" aria-current='page'" if k == seg else "")
        + f">{e(t)} · {len(todos) if k == 'todos' else sum(1 for c in todos if k in c['segmentos'])}</a>" for k, t in SEGMENTOS)

    def th(k: str, t: str) -> str:
        sel = k == orden
        return (f"<th scope='col'{' aria-sort=' + chr(39) + 'descending' + chr(39) if sel else ''}><a class='vn-orden{' sel' if sel else ''}' "
                f"href='?seg={seg}&orden={k}&m={iso_mon}'>{e(t)}{' ↓' if sel else ''}</a></th>")
    filas_html, fichas = "", {}
    for i, c in enumerate(lista):
        p = fotos.get(c["email"]) or {}
        nom = c["visible"]
        contacto = c["email"] or c["telefono"] or "Cliente de mostrador"
        badge = va.pill({"vip": "VIP", "nuevo": "Nuevo", "riesgo": "En riesgo"}.get(c["badge"], ""), {"moroso": "warn", "riesgo": "bad", "vip": "azul", "nuevo": "ok"}.get(c["badge"], "gris"),
                        "estrella" if c["badge"] == "vip" else "") if c["badge"] and c["badge"] != "moroso" else ""
        ult = _fecha_bonita(c["ultima"], hoy) if c["ultima"] else "Sin fecha"
        wa = _wa(c["telefono"])
        if c["por_cobrar"] > 0:
            deuda = va.pill(f"Debe {_m(c['por_cobrar'], sim)}", "warn")
            msg = f"Hola {nom}, te recordamos tu saldo pendiente de {_m(c['por_cobrar'], sim)} por tu reserva. ¡Gracias!"
            acc = ((f"<a class='vn-acc' target='_blank' rel='noopener' href='{e(ui.enlace_whatsapp(msg, wa))}'>{_svg('chat', 16)}Recordar pago</a>" if wa else "")
                   + f"<button type='button' class='vn-acc' data-cli='{i}'>Ver</button>")
        else:
            deuda = "<span class='vn-al-dia'>Al día</span>"
            acc = f"<button type='button' class='vn-acc' data-cli='{i}'>Ver</button>"
        filas_html += (f"<tr data-q='{e((nom + ' ' + c['email'] + ' ' + c['telefono']).lower())}'>"
                       f"<td data-et='Cliente'><div class='vn-cli'>{avatar(nom, p.get('foto_url') or '', 'vn-av')}<div><b>{e(nom)}</b>{badge}"
                       f"<small>{e(contacto)}{(' · ' + e(c['nivel'])) if c['nivel'] else ''}</small></div></div></td>"
                       f"<td data-et='Reservas'><b>{c['reservas']}</b></td><td data-et='Gastado'><b>{e(_m(c['gastado'], sim, 0))}</b></td>"
                       f"<td data-et='Última vez'>{e(ult)}</td><td data-et='Deuda'>{deuda}</td>"
                       f"<td data-et='Acciones' class='vn-td-acc'>{acc}</td></tr>")
        suyas = sorted(c["filas"], key=lambda r: r["fecha"], reverse=True)
        pagadas = [r for r in suyas if r["pagado"]]
        ticket = sum(total_con_extras(r) for r in pagadas) / len(pagadas) if pagadas else 0
        fichas[i] = {
            "nombre": nom, "contacto": contacto, "foto": p.get("foto_url") or "", "clave": c["clave"], "nota": notas.get(c["clave"], ""),
            "wa": wa, "debe": round(c["por_cobrar"], 2), "moneda": sim,
            "datos": [["Ticket promedio", _m(ticket, sim)], ["Cancha favorita", _moda((por_id.get(r["cancha_id"]) or {}).get("nombre", "") for r in suyas) or "Sin datos"],
                      ["Horario favorito", _moda(r["hora_inicio"] for r in suyas) or "Sin datos"],
                      ["Paga con", MEDIOS_LABEL.get(_moda(r["medio_pago"] for r in suyas), "Sin datos")],
                      ["No-show", f"{round(c['noshows'] * 100 / c['reservas']) if c['reservas'] else 0}%"], ["Reservas", str(c["reservas"])]],
            "historial": [[_fecha_bonita(r["fecha"], hoy), r["hora_inicio"], (por_id.get(r["cancha_id"]) or {}).get("nombre", ""),
                           _estado_txt(r), _m(total_con_extras(r), sim)] for r in suyas[:30]]}
    if lista:
        tabla = ("<div class='va-tabla-w'><table class='va-tabla vn-clientes'><thead><tr><th scope='col'>Cliente</th>"
                 + th("frecuentes", "Reservas") + th("gasto", "Gastado") + th("recientes", "Última vez")
                 + "<th scope='col'>Deuda</th><th scope='col' class='vn-th-acc'>Acciones</th></tr></thead>"
                 f"<tbody id='listaCli'>{filas_html}</tbody></table></div>"
                 "<div id='cliVacio' hidden>" + va.vacio("lupa", "Ningún cliente coincide con tu búsqueda") + "</div>")
    else:
        tabla = va.vacio("comparar", "Aún no tienes clientes" if not todos else "Nadie en este segmento por ahora",
                         "Aparecen cuando alguien reserva en tus canchas." if not todos else "")
    cuerpo = (
        va.cabecera("Base de clientes", "Quién reserva en tus canchas, cuánto gastó, cuándo volvió y quién te debe. Sale de tus reservas reales.",
                    acciones=chips_m)
        + va.kpis([_cifra("comparar", "Clientes", str(len(todos))), _cifra("repetir", "Recurrentes", str(recurrentes)),
                   _cifra("usuario", "Nuevos este mes", str(nuevos)),
                   _cifra("alerta", "Te deben", e(_m(te_deben, sim, 0)), sub=f"{len(deudores)} deudor{'es' if len(deudores) != 1 else ''}",
                          tono="warn" if te_deben else "")])
        + "<div class='vn-filtros'><label class='vn-buscar'><span class='vh'>Buscar cliente</span>" + _svg("lupa", 18)
        + "<input type='search' id='qCli' placeholder='Buscar por nombre o correo…' aria-label='Buscar cliente'></label>"
        f"<nav class='vn-chips' aria-label='Segmentos'>{chips_seg}</nav></div>"
        + va.panel(tabla, clase="vn-cli-p"))
    return _render("Clientes", cuerpo, ses, js=f"window.__cli={ui.json_js(fichas, ensure_ascii=False)};{JS_CLIENTES}")


@router.post("/anfitrion/clientes/nota")
def guardar_nota(request: Request, body: dict = Body(default_factory=dict)) -> JSONResponse:
    """Notas privadas del dueño sobre un cliente (solo él las ve)."""
    ses = sesion.de_request(request)
    if not ses:
        return _err("sesion_requerida", 401)
    try:
        guardar_nota_de(ses["email"], str(body.get("clave") or ""), str(body.get("texto") or ""))
    except ErrNegocio as ex:
        return _err(ex.msg, ex.status)
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
    email = ses["email"].lower()
    locs = _locales(canchas)
    ofertas = ofertas_de_dueno(email)
    if not local and len(locs) > 1:   # sin elegir: el primer local que ya tiene bonos
        con_bonos = {b["club"] for b in ofertas}
        local = next((c for c, _s in locs if c in con_bonos), "")
    club, sim = next(((c, s) for c, s in locs if c == local), locs[0] if locs else ("", "S/"))
    bonos = [b for b in ofertas if b["club"] == club]
    vend = [v for v in vendidos_de_dueno(email) if v["club"] == club]
    if len(locs) > 1:
        opts = "".join(f"<option value='{e(c)}'{' selected' if c == club else ''}>{e(c)}</option>" for c, _ in locs)
        sel_local = (f"<form method='get' class='vn-sel vn-sel-local'><label for='vnLocal'>Local:</label>"
                     f"<select id='vnLocal' name='local' data-vn-auto>{opts}</select>"
                     "<noscript><button class='btn sec' type='submit'>Ver</button></noscript></form>")
    else:
        sel_local = f"<span class='vn-sel vn-sel-local'><span>Local:</span><b>{e(club)}</b></span>"
    tarj = ""
    for b in bonos:
        por_hora = b["precio"] / b["horas"] if b["horas"] else b["precio"]
        datos_b = ui.json_js({"id": b["id"], "nombre": b["nombre"], "horas": b["horas"], "precio": b["precio"]})
        nombre_b = b["nombre"] or f"Pack {b['horas']} horas"
        tarj += (f"<article class='vn-bono{'' if b['activo'] else ' pausa'}' data-bono='{e(datos_b)}'>"
                 f"<div class='vn-bono-h'><span class='vn-bono-n' aria-hidden='true'>{b['horas']}h</span><div><h3>{e(nombre_b)}</h3>"
                 + va.pill("A la venta" if b["activo"] else "Pausado", "ok" if b["activo"] else "gris", "check" if b["activo"] else "")
                 + f"</div></div><b class='vn-bono-p'>{e(_m(b['precio'], sim))}</b><small class='vn-bono-ph'>{e(_m(por_hora, sim))} por hora</small>"
                 "<div class='vn-bono-a'>"
                 f"<button type='button' class='vn-bbtn' data-acc='editar'>{_svg('lapiz', 15)}Editar</button>"
                 f"<button type='button' class='vn-bbtn' data-acc='activo' data-v='{0 if b['activo'] else 1}'>{_svg('pausa' if b['activo'] else 'play', 15)}"
                 f"{'Pausar' if b['activo'] else 'Reanudar'}</button>"
                 f"<button type='button' class='vn-bbtn rojo' data-acc='eliminar'>{_svg('basura', 15)}Retirar</button></div></article>")
    tarj += (f"<button type='button' class='vn-bono-nuevo' id='nuevoBono'><span>{_svg('mas', 24, 2.6)}</span><b>Nuevo bono</b>"
             "<small>Ej.: pack de 10 horas</small></button>")
    total = sum(v["precio"] for v in vend)
    hv, hu = sum(v["horas_total"] for v in vend), sum(v["horas_usadas"] for v in vend)
    vendidos = [[f"<b>{e(v['comprador_nombre'] or v['comprador'].split('@')[0] or 'Jugador')}</b>",
                 e(_m(v["precio"], sim)), f"le quedan {v['saldo']} de {v['horas_total']} h",
                 va.pill(f"{v['saldo']} h", "ok" if v["saldo"] else "gris")] for v in vend]
    cuerpo = (
        va.cabecera("Bonos", "Vende packs de horas con descuento. El jugador paga por adelantado y descuenta 1 hora al reservar en tu local.",
                    acciones=sel_local)
        + va.pasos([("etiqueta", "1. Creas el pack", "Horas y precio total"),
                    ("billete", "2. El jugador paga adelantado", "En línea, desde la app o la web"),
                    ("bono", "3. Descuenta 1 h por reserva", "Solo en este local")])
        + f"<h2 class='vh'>Bonos · {e(club)}</h2><div class='vn-bonos'>{tarj}</div>"
        + (va.panel(va.kpis([_cifra("billete", "Vendido", e(_m(total, sim))), _cifra("reloj", "Horas usadas", f"{hu} / {hv}")])
                    + va.tabla(["Jugador", "Pagó", "Saldo", "Horas"], vendidos), "Bonos vendidos",
                    "Esta plata ya entró a tu billetera (\"por recibir\") al venderse. Cuando el jugador reserva con su bono, NO vuelve a "
                    "pagarte: descuenta de estas horas.") if vend else ""))
    return _render("Bonos", cuerpo, ses, js=f"window.__bonos={ui.json_js({'club': club, 'moneda': sim}, ensure_ascii=False)};{JS_BONOS}")


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

def _ocurrencias_fija(c: dict, dia_semana: int, hora: str, semanas: int, ahora: datetime) -> list[dict]:
    """Las próximas [semanas] fechas de un cliente fijo con lo que pasaría con
    cada una (MISMA regla que `generar_fijas` y que la vista previa del
    modal): `base` (día de la semana), `fecha` real del turno y `estado`
    cerrado (reglas del club) · fuera (la hora no existe ese día) · pasado ·
    ok (se intenta crear; lo ocupado/bloqueado se decide contra la base)."""
    hoy = ahora.date()
    delta = (int(dia_semana or 1) - 1 - hoy.weekday()) % 7
    out = []
    for w in range(semanas):
        base = (hoy + timedelta(days=delta + 7 * w)).isoformat()
        cd = _reglas.cancha_del_dia(c, base)
        if cd.get("_cerrado"):
            out.append({"w": w, "base": base, "fecha": base, "estado": "cerrado", "cd": cd})
            continue
        if hora not in horarios.slots_de(cd):
            out.append({"w": w, "base": base, "fecha": base, "estado": "fuera", "cd": cd})
            continue
        fr = horarios.fecha_real(base, cd["hora_apertura"], cd["hora_cierre"], hora)
        mins = horarios.hora_en_minutos(hora) or 0
        pasado = fr < hoy.isoformat() or (fr == hoy.isoformat() and mins < ahora.hour * 60 + ahora.minute)
        out.append({"w": w, "base": base, "fecha": fr, "estado": "pasado" if pasado else "ok", "cd": cd})
    return out


def vista_previa_fija(c: dict, dia_semana: int, hora: str, semanas: int = 4, ahora: datetime | None = None) -> dict:
    """Lo que creará "Guardar y generar reservas" ANTES de guardar (modal
    "Nuevo cliente fijo"): fechas que se crean y las que se saltan (ocupado o
    bloqueado, día cerrado, hora fuera del horario). Una sola consulta de
    ocupados para todas las fechas."""
    ahora = ahora or horarios.ahora_local(_pais_de(c))
    occ = _ocurrencias_fija(c, dia_semana, hora, semanas, ahora)
    vivas = [o["fecha"] for o in occ if o["estado"] == "ok"]
    tomados = datos.ocupados(c["id"], vivas) if vivas else set()
    crea, salta = [], []
    for o in occ:
        if o["estado"] == "ok" and (o["fecha"], hora) in tomados:
            salta.append({"fecha": o["fecha"], "motivo": "ocupado o bloqueado"})
        elif o["estado"] == "ok":
            crea.append(o["fecha"])
        elif o["estado"] == "cerrado":
            salta.append({"fecha": o["fecha"], "motivo": "el club cierra ese día"})
        elif o["estado"] == "fuera":
            salta.append({"fecha": o["fecha"], "motivo": "esa hora no se atiende ese día"})
    return {"crea": crea, "salta": salta, "texto": _texto_fechas(crea, hora)}


def _texto_fechas(fechas: list[str], hora: str) -> str:
    """"Mié 18, 25 nov y 2 dic · 21:00" (agrupa por mes, como el diseño)."""
    if not fechas:
        return ""
    ds = [date.fromisoformat(f) for f in fechas]
    grupos: list[tuple[int, list[int]]] = []
    for d in ds:
        if grupos and grupos[-1][0] == d.month:
            grupos[-1][1].append(d.day)
        else:
            grupos.append((d.month, [d.day]))
    if len(grupos) == 1:   # "11, 18 y 25 nov"
        mth, dias = grupos[0]
        txt = (str(dias[0]) if len(dias) == 1 else ", ".join(str(x) for x in dias[:-1]) + f" y {dias[-1]}") + f" {MESES_CORTO[mth - 1]}"
    else:                  # "18, 25 nov y 2 dic"
        partes = [", ".join(str(x) for x in dias) + f" {MESES_CORTO[mth - 1]}" for mth, dias in grupos]
        txt = ", ".join(partes[:-1]) + " y " + partes[-1]
    return f"{horarios.DIAS[ds[0].weekday()]} {txt} · {hora}"


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
        ahora = horarios.ahora_local(_pais_de(c))
        hoy = ahora.date()
        hechas = set(f.get("hechas") or [])
        nuevas_para_push = []
        for o in _ocurrencias_fija(c, int(f.get("diaSemana") or 1), hora, semanas, ahora):
            w, base, fr, cd = o["w"], o["base"], o["fecha"], o["cd"]
            if base in hechas:
                continue
            # Cancha EFECTIVA del día (reglas del club): un día cerrado o sin
            # ese turno no genera reserva (se reintenta si el club lo abre).
            if o["estado"] == "cerrado":
                omitidas.append(f"{horarios.fecha_larga(base)} cerrado")
                continue
            if o["estado"] == "fuera":
                omitidas.append("hora fuera del horario")
                continue
            if o["estado"] == "pasado":
                continue
            if (fr, hora) in datos.ocupados(c["id"], [fr]):
                omitidas.append(f"{horarios.fecha_larga(fr)} ocupado o bloqueado")
                hechas.add(base)
                continue
            paso = int(c.get("duracion_slot_min") or 60)
            precio = horarios.precio_turno_de(cd, hora, datos.descuentos(c["id"], [fr]).get((fr, hora), 0))
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
def pagina_fijas(request: Request, cancha: str = "") -> HTMLResponse:
    ses, canchas, resp = _contexto(request, "/anfitrion/fijas")
    if resp is not None:
        return resp
    res = generar_fijas(ses["email"], canchas)  # como el app: al abrir el panel, se completan las próximas semanas
    _persistir()
    neg = _negocio(ses["email"])
    por_id = {c["id"]: c for c in canchas}
    hoy = _hoy_de(canchas).date()

    def nom(cid):
        c = por_id.get(cid) or {}
        return f"{c['club']} · {c['nombre']}" if c.get("club") and c.get("club") != c.get("nombre") else (c.get("nombre") or "Cancha")
    cancha = cancha if cancha in por_id else ""
    fijas = [f for f in neg["fijas"] if f.get("canchaId") in por_id and (not cancha or f.get("canchaId") == cancha)]
    # Próximas reservas de cada fija: UNA consulta de las próximas 5 semanas.
    prox = reservas_dueno(list(por_id), hoy.isoformat(), (hoy + timedelta(days=35)).isoformat()) if fijas else []
    filas = []
    for f in fijas:
        dia = int(f.get("diaSemana") or 1)
        suyas = sorted(r["fecha"] for r in prox if r["cancha_id"] == f.get("canchaId") and r["hora_inicio"] == f.get("hora")
                       and r["jugador"] == (f.get("clienteNombre") or "Cliente") and not es_noshow(r)
                       and date.fromisoformat(r["fecha"]).weekday() == dia - 1)
        activo = f.get("activo", True)
        prox_txt = (", ".join(f"{date.fromisoformat(x).day} {MESES_CORTO[date.fromisoformat(x).month - 1]}" for x in suyas[:4])
                    if suyas else ("Pausado" if not activo else "Sin fechas libres"))
        tel = f.get("clienteTelefono") or ""
        filas.append([
            f"<div class='vn-cli'>{_ic('repetir', 'suave', 16)}<div><b>{e(f.get('clienteNombre') or 'Cliente')}</b>"
            f"<small>{e(tel or f.get('clienteEmail') or 'Sin contacto')}</small></div></div>",
            e(nom(f.get("canchaId"))), f"<b>{DIAS_TIT[dia - 1]}</b><small>{e(f.get('hora'))}</small>",
            (va.pill(f"{len(suyas)} próximas", "ok") + f"<small>{e(prox_txt)}</small>") if suyas else f"<small>{e(prox_txt)}</small>",
            f"<div class='vn-fija-a' data-fija='{e(f['id'])}'>"
            f"<label class='vn-sw' title='{'Activa' if activo else 'Pausada'}'><input type='checkbox' data-acc='activo' {'checked' if activo else ''} "
            f"aria-label='{'Pausar' if activo else 'Reactivar'} a {e(f.get('clienteNombre') or 'Cliente')}'><i></i></label>"
            f"<button type='button' class='vn-bbtn rojo' data-acc='quitar'>{_svg('basura', 15)}Quitar</button></div>"])
    cfg = {"canchas": [{"id": c["id"], "nombre": nom(c["id"]), "paso": int(c.get("duracion_slot_min") or 60),
                        "slots": {str(d): _slots_dia_semana(c, d) for d in range(1, 8)}} for c in canchas],
           "hoy": hoy.weekday() + 1, "sel": cancha}
    opts = "<option value=''>Todas las canchas</option>" + "".join(
        f"<option value='{e(c['id'])}'{' selected' if c['id'] == cancha else ''}>{e(nom(c['id']))}</option>" for c in canchas)
    sel = (f"<form method='get' class='vn-sel'><label class='vh' for='vnFC'>Cancha</label><select id='vnFC' name='cancha' data-vn-auto>{opts}</select>"
           "<noscript><button class='btn sec' type='submit'>Ver</button></noscript></form>") if len(canchas) > 1 else ""
    vacio = va.vacio("intercambio", "Aún no tienes clientes fijos" if not cancha else "Sin clientes fijos en esta cancha",
                     "Agrega al equipo que juega cada semana y olvídate de anotarlo a mano.",
                     "<button type='button' class='btn suave' data-nueva-fija>+ Agregar cliente fijo</button>")
    aviso = (va.aviso(f"Se crearon {res['creadas']} reserva{'s' if res['creadas'] != 1 else ''} de tus clientes fijos para las próximas semanas.",
                      "ok", ico="check") if res["creadas"] else "")
    cuerpo = (
        va.cabecera("Reservas fijas", "Tus pensionados: el equipo que juega siempre el mismo día y hora. Sus reservas de las próximas "
                    "4 semanas se crean solas.", acciones="<button type='button' class='btn' id='nuevaFija' data-nueva-fija>+ Cliente fijo</button>")
        + aviso
        + va.pasos([("calendario", "1. Elige cancha, día y hora", "Ej.: todos los miércoles 21:00"),
                    ("intercambio", "2. Se crean 4 semanas", "Respetando lo ocupado y tus bloqueos"),
                    ("chat", "3. Avisas al cliente", "Por WhatsApp o ve sus reservas en la app")])
        + va.panel(va.tabla(["Cliente", "Cancha", "Día y hora", "Próximas reservas", "Acciones"], filas, clase="vn-fijas", vacia=vacio),
                   "Clientes fijos", acciones=sel))
    return _render("Reservas fijas", cuerpo, ses, js=f"window.__fijas={ui.json_js(cfg, ensure_ascii=False)};{JS_FIJAS}")


@router.get("/anfitrion/fijas/vista-previa")
def fija_vista_previa(request: Request, cancha_id: str = "", dia: int = 0, hora: str = "") -> JSONResponse:
    """Vista previa del modal "Nuevo cliente fijo": qué fechas se crearán y
    cuáles se saltan (misma regla que `generar_fijas`)."""
    ses = sesion.de_request(request)
    if not ses:
        return _err("sesion_requerida", 401)
    c = next((x for x in datos.canchas_de_dueno(ses["email"]) if x["id"] == cancha_id), None)
    if c is None:
        return _err("Esta cancha no está a tu nombre.", 404)
    if not 1 <= int(dia or 0) <= 7 or hora not in _slots_dia_semana(c, int(dia)):
        return _err("Elige el día y la hora.")
    return _json_ok(**vista_previa_fija(c, int(dia), hora))


@router.post("/anfitrion/fijas/nueva")
def nueva_fija(request: Request, body: dict = Body(default_factory=dict)) -> JSONResponse:
    ses = sesion.de_request(request)
    if not ses:
        return _err("sesion_requerida", 401)
    try:
        res = crear_fija(ses["email"], datos.canchas_de_dueno(ses["email"]), body)
    except ErrNegocio as ex:
        return _err(ex.msg, ex.status)
    return _json_ok(id=res["id"], creadas=res["creadas"], omitidas=res["omitidas"])


@router.post("/anfitrion/fijas/{fid}/activo")
def activar_fija(request: Request, fid: str, body: dict = Body(default_factory=dict)) -> JSONResponse:
    ses = sesion.de_request(request)
    if not ses:
        return _err("sesion_requerida", 401)
    try:
        res = activar_fija_de(ses["email"], fid, bool(body.get("activo")))
    except ErrNegocio as ex:
        return _err(ex.msg, ex.status)
    return _json_ok(**res)


@router.post("/anfitrion/fijas/{fid}/quitar")
def quitar_fija(request: Request, fid: str) -> JSONResponse:
    """Deja de generar (las reservas ya creadas siguen en la agenda)."""
    ses = sesion.de_request(request)
    if not ses:
        return _err("sesion_requerida", 401)
    if not quitar_fija_de(ses["email"], fid):
        return _err("No encontramos ese cliente fijo.", 404)
    return _json_ok()


# ── Disponibilidad (disponibilidad_screen.dart, hecha real) ─────────────────

def _es_valle(c: dict, h: str) -> bool:
    """Hora valle de la cancha: la franja con descuento si el dueño la
    configuró; si no, las mañanas (antes de las 12:00)."""
    if int(c.get("descuento_valle") or 0) > 0:
        return horarios.es_valle(h, c.get("valle_desde") or "", c.get("valle_hasta") or "")
    return (horarios.hora_en_minutos(h) or 0) < 12 * 60


def _turnos_del_dia(c: dict, base: str, ahora: datetime) -> tuple[dict, list[dict]]:
    """Turnos de la cancha en el día `base` con su estado: (cancha del día,
    [{hora, fecha real, pasado, valle, reserva, bloqueado}]). Dos consultas
    (reservas y bloqueos de las fechas reales del día)."""
    hoy = ahora.date()
    cd = _reglas.cancha_del_dia(c, base)
    sl = horarios.slots_de(cd)
    fechas = sorted({horarios.fecha_real(base, cd["hora_apertura"], cd["hora_cierre"], h) for h in sl} | {base})
    reservas = {(r["fecha"], r["hora_inicio"]): r for r in reservas_dueno([c["id"]], fechas[0], fechas[-1]) if not es_noshow(r)}
    bloq = {(f, h) for (_cid, f, h) in datos.bloqueos_de([c["id"]], fechas)}
    out = []
    for h in sl:
        fr = horarios.fecha_real(base, cd["hora_apertura"], cd["hora_cierre"], h)
        out.append({"hora": h, "fecha": fr, "valle": _es_valle(c, h), "reserva": reservas.get((fr, h)), "bloqueado": (fr, h) in bloq,
                    "pasado": fr < hoy.isoformat() or (fr == hoy.isoformat() and (horarios.hora_en_minutos(h) or 0) < ahora.hour * 60 + ahora.minute)})
    return cd, out


def turnos_para_lote(turnos: list[dict], accion: str, ocupados: set | None = None) -> list[dict]:
    """Turnos que toca una acción en lote de Disponibilidad. Nunca toca los
    que ya pasaron ni los reservados (tampoco los apartados web en espera de
    pago: [ocupados] = `datos.ocupados`, que los incluye).
    cerrar_dia → los abiertos; abrir_valle → los de hora valle que están cerrados."""
    ocupados = ocupados or set()
    out = []
    for t in turnos:
        if t["pasado"] or t["reserva"]:
            continue
        if accion == "cerrar_dia" and not t["bloqueado"] and (t["fecha"], t["hora"]) not in ocupados:
            out.append(t)
        elif accion == "abrir_valle" and t["valle"] and t["bloqueado"]:
            out.append(t)
    return out


def _bloquear_lote(cancha_id: str, pares: list[tuple[str, str]], bloquear: bool) -> bool:
    """Bloquea / desbloquea VARIOS turnos en UNA sentencia (misma tabla y clave
    que `datos.bloquear`: PK (cancha_id, fecha, hora))."""
    if not pg.habilitado or not cancha_id or not pares:
        return False
    fechas, horas = [f for f, _h in pares], [h for _f, h in pares]
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            if bloquear:
                cur.execute("INSERT INTO pichangol_bloqueos (cancha_id, fecha, hora) SELECT %s, f, h FROM unnest(%s::text[], %s::text[]) AS t(f, h) "
                            "ON CONFLICT DO NOTHING", (cancha_id, fechas, horas))
            else:
                cur.execute("DELETE FROM pichangol_bloqueos b USING unnest(%s::text[], %s::text[]) AS t(f, h) "
                            "WHERE b.cancha_id = %s AND b.fecha = t.f AND b.hora = t.h", (fechas, horas, cancha_id))
            conn.commit()
            return True
    except Exception as ex:  # noqa: BLE001
        print(f"[bloqueo-web] lote falló {cancha_id} ({len(pares)}): {ex}", flush=True)
        return False


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
    # Cancha EFECTIVA del día con las reglas del club (horario del día,
    # cierres especiales): un día cerrado no tiene turnos que abrir.
    cd, turnos = _turnos_del_dia(c, base, ahora)
    abiertas = sum(1 for t in turnos if not t["reserva"] and not t["bloqueado"] and not t["pasado"])
    reservadas = sum(1 for t in turnos if t["reserva"])
    vivos = [t for t in turnos if not t["pasado"] and not t["reserva"] and not t["bloqueado"]]
    # (los apartados web en espera de pago tampoco se cierran: misma cuenta que el endpoint)
    ocup = datos.ocupados(c["id"], sorted({t["fecha"] for t in vivos})) if vivos else set()
    n_cerrar = len(turnos_para_lote(turnos, "cerrar_dia", ocup))
    n_valle = len(turnos_para_lote(turnos, "abrir_valle"))
    tarjetas = ""
    for t in turnos:
        h, fr, r = t["hora"], t["fecha"], t["reserva"]
        abierta = not r and not t["bloqueado"]
        franja = (f"<span class='vn-franja'>{_svg('sol' if t['valle'] else 'luna', 15)}{'Hora valle' if t['valle'] else 'Hora punta'}"
                  f"{' · madrugada' if fr != base else ''}</span>")
        if r:
            quien = (r["jugador"] or "Reserva").split(" ")[0]
            ctrl = f"<span class='vn-lock' title='Reservada' aria-label='Reservada'>{_svg('candado', 15)}</span>"
            pie = f"<small class='vn-res'>{e(quien)} · {'pagada' if r['pagado'] else 'por cobrar'}</small>"
            clase = " reservada"
        else:
            ctrl = (f"<label class='vn-sw'><input type='checkbox' data-f='{fr}' data-h='{e(h)}' {'checked' if abierta else ''} {'disabled' if t['pasado'] else ''}"
                    f" aria-label='{e(h)} abierta'><i></i></label>")
            if t["pasado"]:
                pie, clase = "<small>Ya pasó</small>", " pasada"
            elif t["valle"]:
                pie, clase = ("<small class='vn-prio'>Prioriza abrirla</small>", "" if abierta else " cerrada")
            else:
                pie, clase = (f"<small>{'Abierta' if abierta else 'Cerrada'}</small>", "" if abierta else " cerrada")
        tarjetas += f"<div class='vn-turno{clase}'><div class='vn-turno-h'><b>{e(h)}</b>{ctrl}</div>{franja}{pie}</div>"
    # Semana del día elegido (lunes a domingo) + flechas de semana.
    lunes = dia - timedelta(days=dia.weekday())
    q = f"cancha={quote(c['id'])}"
    tira = "".join(
        f"<a class='vn-dsem{' sel' if d == dia else ''}{' hoy' if d == hoy else ''}' href='?{q}&fecha={d.isoformat()}'"
        + (" aria-current='date'" if d == dia else "") + f"><small>{horarios.DIAS[d.weekday()]}</small><b>{d.day}</b></a>"
        for d in (lunes + timedelta(days=i) for i in range(7)))
    etq_f = f"{'Hoy · ' if dia == hoy else ''}{dia.day:02d}/{dia.month:02d}/{dia.year}"
    semana = (f"<div class='va-panel vn-semana'><a class='vn-flecha' href='?{q}&fecha={(dia - timedelta(days=7)).isoformat()}' aria-label='Semana anterior'>‹</a>"
              f"<nav class='vn-dsems' aria-label='Días de la semana'>{tira}</nav>"
              f"<a class='vn-flecha' href='?{q}&fecha={(dia + timedelta(days=7)).isoformat()}' aria-label='Semana siguiente'>›</a>"
              + _fecha_picker(dia, hoy, {"cancha": c["id"]}, etq_f)
              + (f"<a class='btn suave vn-hoy' href='?{q}'>Hoy</a>" if lunes != hoy - timedelta(days=hoy.weekday()) else "") + "</div>")
    resumen = (f"<div class='vn-resumen'>{va.pill(f'{abiertas} turno' + ('s' if abiertas != 1 else '') + ' abierto' + ('s' if abiertas != 1 else ''), 'ok', 'check')}"
               f"{va.pill(f'{reservadas} reservada' + ('s' if reservadas != 1 else ''), 'warn')}"
               f"{va.pill(horarios.duracion_texto(int(c.get('duracion_slot_min') or 60)) + ' por turno', 'gris', 'reloj')}</div>"
               "<div class='vn-lote'>"
               f"<button type='button' class='btn sec' data-lote='cerrar_dia' data-n='{n_cerrar}'{' disabled' if not n_cerrar else ''}>Cerrar todo el día</button>"
               f"<button type='button' class='btn' data-lote='abrir_valle' data-n='{n_valle}'{' disabled' if not n_valle else ''}"
               f" title='{'' if n_valle else 'No hay horas valle cerradas'}'>Abrir horas valle</button></div>")
    if tarjetas:
        cuerpo_dia = (f"<div class='vn-dia-cab'>{resumen}</div><div class='vn-turnos'>{tarjetas}</div>"
                      f"<p class='vn-nota'>{_svg('info', 16)} Las mañanas (horas valle) son las que más conviene llenar. "
                      "Los turnos reservados no se pueden cerrar.</p>")
    elif cd.get("_cerrado"):
        cuerpo_dia = va.vacio("calendario", f"{_motivo_cierre(cd['_cerrado'])}: ese día no hay turnos",
                              cta=f"<a class='btn suave' href='/anfitrion/reglas/{quote(c['id'])}'>Ver reglas de reserva</a>")
    else:
        cuerpo_dia = va.vacio("reloj", "Configura el horario de esta cancha",
                              cta=f"<a class='btn suave' href='/anfitrion/reglas/{quote(c['id'])}'>Reglas de reserva</a>")
    opts = "".join(f"<option value='{e(x['id'])}'{' selected' if x['id'] == c['id'] else ''}>{e(x.get('nombre') or 'Cancha')}"
                   + (f" · {e(x.get('club'))}" if x.get("club") else "") + "</option>" for x in canchas)
    sel_mov = (f"<form method='get' class='vn-sel vn-sel-mov'><input type='hidden' name='fecha' value='{base}'>"
               f"<label class='vh' for='vnDC'>Cancha</label>{_svg('cancha', 17)}<select id='vnDC' name='cancha' data-vn-auto>{opts}</select></form>")
    lateral = va.lista_lateral(canchas, c["id"], lambda x: f"?cancha={quote(x['id'])}&fecha={base}", contar=f"{len(canchas)}")
    cuerpo = (
        va.cabecera("Disponibilidad", "Abre las horas que quieres publicar en la app y en la web; las cerradas no se pueden reservar.")
        + f"<div class='va-lado vn-dispo'>{lateral}<div class='vn-dispo-d'>{sel_mov}{semana}{cuerpo_dia}</div></div>")
    return _render("Disponibilidad", cuerpo, ses,
                   js=f"window.__dispo={ui.json_js({'cancha': c['id'], 'base': base})};{JS_DISPO}")


@router.post("/anfitrion/disponibilidad/lote")
def disponibilidad_lote(request: Request, body: dict = Body(default_factory=dict)) -> JSONResponse:
    """Acciones en lote de Disponibilidad (diseño, Frame 18): "Cerrar todo el
    día" (bloquea los turnos abiertos que no pasaron ni están reservados) y
    "Abrir horas valle" (desbloquea los de hora valle). Mismos candados que
    el bloqueo de un turno (`/anfitrion/bloqueo`): dueño o su recepción con
    permiso de bloquear y el Pro del DUEÑO si se exige."""
    from web import permisos
    from web.anfitrion import _RESP_PRO, _canchas_sesion, _pro_ok
    ses, canchas = _canchas_sesion(request, permisos.BLOQUEAR)
    if not ses:
        return _err("sesion_requerida", 401)
    c = next((x for x in canchas if x["id"] == str(body.get("cancha_id") or "")), None)
    if c is None:
        return _err("Esta cancha no está a tu nombre.", 404)
    accion = str(body.get("accion") or "")
    if accion not in ("cerrar_dia", "abrir_valle"):
        return _err("Acción inválida.")
    if not _pro_ok(c.get("dueno") or ses["email"]):
        return JSONResponse(_RESP_PRO, status_code=402)
    try:
        base = date.fromisoformat(str(body.get("base") or "")).isoformat()
    except ValueError:
        return _err("Fecha inválida.")
    cd, turnos = _turnos_del_dia(c, base, horarios.ahora_local(_pais_de(c)))
    if cd.get("_cerrado"):
        return _err(f"Ese día el club está cerrado ({_motivo_cierre(cd['_cerrado'])}): no hay turnos.")
    fechas = sorted({t["fecha"] for t in turnos})
    ocup = datos.ocupados(c["id"], fechas) if accion == "cerrar_dia" and fechas else set()
    objetivo = turnos_para_lote(turnos, accion, ocup)
    if not objetivo:
        return _json_ok(n=0)
    if not _bloquear_lote(c["id"], [(t["fecha"], t["hora"]) for t in objetivo], accion == "cerrar_dia"):
        return _err("No pudimos guardar en este momento.", 503)
    permisos.auditar(ses["email"], c, "bloquear" if accion == "cerrar_dia" else "desbloquear",
                     f"{base} lote {accion} ({len(objetivo)})")
    print(f"[bloqueo-web] {ses['email']} {accion} {c['id']} {base}: {len(objetivo)} turnos", flush=True)
    return _json_ok(n=len(objetivo))


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


def _morosos(mats: list[dict], hoy: str) -> tuple[float, float, float, list]:
    """(por cobrar, vencido, cobrado este mes, [(matrícula, deuda, vencida, pendientes)]):
    vencidos primero y, dentro, la deuda más grande primero."""
    mes = hoy[:7]
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
    return por_cobrar, vencido, cobrado, morosos


def _dias_recordado(recordados: dict, mid: str) -> int | None:
    try:
        t = datetime.fromisoformat(str(recordados[mid]).replace("Z", "+00:00"))
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - t).days
    except (KeyError, ValueError, TypeError):
        return None


RECORDAR_CADA_DIAS = 7  # a un alumno no se le recuerda dos veces en la misma semana


def _por_recordar(morosos: list, recordados: dict) -> list:
    """Los que deben y no recibieron un recordatorio en la última semana."""
    out = []
    for t in morosos:
        d = _dias_recordado(recordados, t[0]["id"])
        if d is None or d >= RECORDAR_CADA_DIAS:
            out.append(t)
    return out


def _tel_alumno(m: dict) -> str:
    return str(m.get("apoderadoWhatsapp") if m.get("apoderadoNombre") and m.get("apoderadoWhatsapp") else m.get("whatsapp") or "")


def _selector_academia(acads: list[dict], a: dict) -> str:
    if len(acads) < 2:
        return ""
    opts = "".join(f"<option value='{e(x['id'])}'{' selected' if x['id'] == a['id'] else ''}>{e(x.get('nombre') or 'Academia')}</option>" for x in acads)
    return (f"<form method='get' class='vn-sel'><label class='vh' for='vnAc'>Academia</label>{_svg('academias', 17)}"
            f"<select id='vnAc' name='academia' data-vn-auto>{opts}</select>"
            "<noscript><button class='btn sec' type='submit'>Ver</button></noscript></form>")


@router.get("/anfitrion/cobros", response_class=HTMLResponse)
def pagina_cobros(request: Request, academia: str = "") -> HTMLResponse:
    from web.anfitrion_academia import _mias, _moneda
    from web.jugador_liga import avatar
    ses, resp = _sesion_o_entrar(request, "/anfitrion/cobros")
    if resp is not None:
        return resp
    acads = _mias(ses["email"])
    if not acads:
        cuerpo = (va.cabecera("Cobros de academia", "Quién debe, recordatorios por la app o WhatsApp y el cobro en efectivo por cuota.")
                  + va.panel(va.vacio("academias", "Aún no tienes una academia", "Créala y cobra las mensualidades de tus alumnos desde aquí.",
                                      "<a class='btn' href='/anfitrion/academia'>Crear mi academia</a>")))
        return _render("Cobros de academia", cuerpo, ses)
    a = next((x for x in acads if x["id"] == academia), acads[0])
    for x in acads:
        x.setdefault("dueno", ses["email"])
    from web import academia_plan_web as apw
    # PLAN ACADEMIA: los yapeos que reportaron los alumnos SIEMPRE se confirman aquí,
    # aunque el plan esté vencido (es plata de los alumnos, no del plan).
    por_confirmar = apw.seccion_por_confirmar(acads)
    sel = _selector_academia(acads, a)
    titulo = f"Cobros · {a.get('nombre') or 'Mi academia'}"
    sub = "Quién debe, recordatorios por la app o WhatsApp y el cobro en efectivo por cuota."
    if not apw.beneficios(a):
        cuerpo = (va.cabecera(titulo, "Confirma aquí los pagos que te reportaron tus alumnos; el resto de la gestión de cobros es parte "
                              "del Plan Academia.", acciones=sel) + por_confirmar + apw.paywall(a))
        return _render("Cobros de academia", cuerpo, ses)
    sim = _moneda(a)
    hoy = date.today().isoformat()
    mats = datos.matriculas_de_academias([a["id"]])
    recordados = _negocio(ses["email"])["recordados"]
    por_cobrar, vencido, cobrado, morosos = _morosos(mats, hoy)
    por_recordar = _por_recordar(morosos, recordados)
    n_venc = sum(1 for t in morosos if t[2])
    fichas, filas = {}, ""
    for m, deuda, venc, pend in morosos:
        tel = _tel_alumno(m)
        app = bool((m.get("email") or "").strip())
        d = _dias_recordado(recordados, m["id"])
        fichas[m["id"]] = {"nombre": m.get("nombre") or "Alumno", "app": app, "wa": ui.enlace_whatsapp(_msj_cobro(m, deuda, sim, False), _wa(tel)) if _wa(tel) else "",
                           "cuotas": [{"id": c.get("id"), "concepto": c.get("concepto") or "Cuota", "monto": float(c.get("monto") or 0),
                                       "vence": str(c.get("vencimiento") or "")[:10], "auto": bool(c.get("autoDebito"))} for c in pend]}
        canal = (va.pill("Tiene la app", "azul", "celular") if app else (va.pill("WhatsApp", "ok", "whatsapp") if _wa(tel) else va.pill("Sin contacto", "gris")))
        rec = f"<small>Recordado hace {d} día{'s' if d != 1 else ''}</small>" if d is not None else ""
        filas += (f"<tr data-al='{e(m['id'])}'><td data-et='Alumno'><div class='vn-cli'>{avatar(m.get('nombre') or '?', m.get('fotoUrl') or '', 'vn-av')}"
                  f"<div><b>{e(m.get('nombre') or 'Alumno')}</b>"
                  + (f"<small>con {e(m['apoderadoNombre'])}</small>" if m.get("apoderadoNombre") else "") + f"{rec}</div></div></td>"
                  f"<td data-et='Deuda'><b class='vn-rojo'>{e(_m(deuda, sim))}</b></td>"
                  f"<td data-et='Cuotas'>{len(pend)} cuota{'s' if len(pend) != 1 else ''}</td>"
                  f"<td data-et='Estado'>{va.pill('Vencido', 'bad', 'reloj') if venc else va.pill('Por vencer', 'warn', 'reloj')}</td>"
                  f"<td data-et='Canal'>{canal}</td>"
                  f"<td data-et='Acciones' class='vn-td-acc'><button type='button' class='btn sec vn-mini' data-acc='cobrar'>{_svg('billete', 16)}Cobrar</button>"
                  f"<button type='button' class='btn vn-mini' data-acc='recordar'>{_svg('enviar', 16)}Recordar</button></td></tr>")
    if filas:
        tabla = ("<div class='va-tabla-w'><table class='va-tabla vn-deben'><thead><tr><th scope='col'>Alumno</th><th scope='col'>Deuda</th>"
                 "<th scope='col'>Cuotas</th><th scope='col'>Estado</th><th scope='col'>Canal</th><th scope='col' class='vn-th-acc'>Acciones</th>"
                 f"</tr></thead><tbody id='morosos'>{filas}</tbody></table></div>")
    else:
        tabla = va.vacio("billete", "Todos al día", "Ningún alumno debe cuotas en esta academia.")
    banner = ""
    if por_recordar:
        n = len(por_recordar)
        banner = (f"<div class='va-panel vn-banner'>{_ic('campana', 'naranja', 18)}<div class='vn-banner-t'><b>Tienes {n} alumno{'s' if n != 1 else ''} por recordar</b>"
                  "<small>Deben y no se les recordó en la última semana.</small></div>"
                  f"<button type='button' class='btn' id='recTodos'>{_svg('enviar', 17)} Recordar a todos</button></div>")
    acciones = (sel + f"<a class='btn sec' href='/anfitrion/academia/alumnos?academia={e(a['id'])}'>Ver todos los alumnos</a>"
                f"<a class='btn' href='/anfitrion/cobros/agregar?academia={e(a['id'])}'>+ Agregar cuota</a>")
    cuerpo = (
        va.cabecera(titulo, sub, acciones=acciones) + por_confirmar
        + va.kpis([_cifra("recibo", "Por cobrar", e(_m(por_cobrar, sim))),
                   _cifra("alerta", "Vencido", e(_m(vencido, sim)), color="rojo" if vencido > 0 else "azul",
                          sub=f"{n_venc} alumno{'s' if n_venc != 1 else ''}" if n_venc else "", tono="bad" if vencido > 0 else ""),
                   _cifra("check", "Cobrado este mes", e(_m(cobrado, sim)))])
        + banner
        + va.panel(tabla, "Quién debe", clase="vn-deben-p"))
    cfg = {"academia": a["id"], "moneda": sim, "fichas": fichas, "porRecordar": [t[0]["id"] for t in por_recordar]}
    return _render("Cobros de academia", cuerpo, ses, js=f"window.__cob={ui.json_js(cfg, ensure_ascii=False)};{JS_COBROS}")


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
    marcar_recordado_de(ses["email"], m["id"])
    return _json_ok(canal=canal)


def _mensajes_academia_lote(academia_id: str, autor: str, autor_nombre: str, envios: list[tuple[str, str]]) -> bool:
    """Varios mensajes del PROFE en los hilos de la academia en UNA sentencia
    (= `mensaje_academia` por cada uno); el trigger dispara cada push."""
    if not pg.habilitado or not envios:
        return False
    base = time.time_ns() // 1000
    ids = [f"msg_{base + i}_w" for i in range(len(envios))]
    ems = [em.strip().lower() for em, _t in envios]
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO pichangol_mensajes (id, hilo, tipo, ref_id, academia_id, cuenta_email, autor_email, autor_nombre, es_profe, texto) "
                        "SELECT t.id, %s || '|' || t.em, 'academia', %s, %s, t.em, %s, %s, true, t.tx "
                        "FROM unnest(%s::text[], %s::text[], %s::text[]) AS t(id, em, tx)",
                        (academia_id, academia_id, academia_id, autor.lower(), autor_nombre, ids, ems, [tx for _em, tx in envios]))
            conn.commit()
            return True
    except Exception as ex:  # noqa: BLE001
        print(f"[cobros-web] recordatorio en lote falló ({len(envios)}): {ex}", flush=True)
        return False


@router.post("/anfitrion/cobros/recordar-todos")
def recordar_todos(request: Request, body: dict = Body(default_factory=dict)) -> JSONResponse:
    """"Recordar a todos" (diseño, Frame 31): a cada alumno que debe y NO se le
    recordó en la última semana. Los que tienen la app reciben el mensaje por
    el chat de la academia (con push) en UNA escritura; los demás vuelven como
    enlaces de WhatsApp (se anotan al abrirlos, como el individual). Nunca
    repite un aviso de esta semana. Es parte del Plan Academia."""
    from web import academia_plan_web as apw
    from web.anfitrion_academia import _mia, _moneda
    from web.jugador_liga import mi_nombre
    ses = sesion.de_request(request)
    if not ses:
        return _err("sesion_requerida", 401)
    a = _mia(ses["email"], str(body.get("academia_id") or ""))
    if a is None:
        return _err("Esa academia no es tuya.", 404)
    a.setdefault("dueno", ses["email"])
    if not apw.beneficios(a):
        return _err("Los recordatorios son parte del Plan Academia.", 402, codigo="plan_academia")
    sim = _moneda(a)
    with _LOCK:
        recordados = dict(_negocio(ses["email"])["recordados"])
    _p, _v, _c, morosos = _morosos(datos.matriculas_de_academias([a["id"]]), date.today().isoformat())
    pend = _por_recordar(morosos, recordados)
    por_app = [(m, deuda) for m, deuda, _venc, _pd in pend if (m.get("email") or "").strip()]
    wa, sin = [], []
    for m, deuda, _venc, _pd in pend:
        if (m.get("email") or "").strip():
            continue
        tel = _wa(_tel_alumno(m))
        if tel:
            wa.append({"id": m["id"], "nombre": m.get("nombre") or "Alumno", "wa": ui.enlace_whatsapp(_msj_cobro(m, deuda, sim, False), tel)})
        else:
            sin.append(m.get("nombre") or "Alumno")
    n_app = 0
    if por_app:
        envios = [(m["email"], _msj_cobro(m, deuda, sim, True)) for m, deuda in por_app]
        if not _mensajes_academia_lote(a["id"], ses["email"], mi_nombre(ses), envios):
            return _err("No se pudo enviar por la app. Reintenta.", 503)
        for m, _d in por_app:
            marcar_recordado_de(ses["email"], m["id"])
        n_app = len(por_app)
    print(f"[cobros-web] {ses['email']} recordó a todos en {a['id']}: app={n_app} wa={len(wa)} sin={len(sin)}", flush=True)
    return _json_ok(app=n_app, whatsapp=wa, sin_contacto=sin)


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


# ── Agregar cuota (mi_academia_screen._inscribir / _claseSuelta) ────────────

def _precio_final(a: dict, plan: dict, al: dict) -> tuple[float, float]:
    """= `Academia.precioFinal(plan, socio: esSocioSede, ordenHermano, prepago)`:
    (monto de cada cuota, % de descuento aplicado)."""
    from web.academia import dto_familiar_pct
    base = float(plan["precioMes"]) + (0.0 if al.get("esSocioSede", True) is not False else float(a.get("recargoInvitado") or 0))
    try:
        orden = int(al.get("ordenHermano") or 1)
    except (TypeError, ValueError):
        orden = 1
    dto = dto_familiar_pct(a, orden) + (float(a.get("descuentoPrepago") or 0) if plan["tipo"] == "prepago" else 0.0)
    dto = min(dto, 100.0)
    return max(0.0, round(base * (1 - dto / 100.0), 2)), dto


def _mes_anio(d: datetime) -> str:
    """`AppState._mesNombre`: "Setiembre 2026"."""
    return f"{MESES_LARGO[d.month - 1].capitalize()} {d.year}"


def cuotas_nuevas(a: dict, al: dict, tipo: str, plan: dict | None, meses: int, monto: float, ahora: datetime) -> list[dict]:
    """Cuotas POR COBRAR con el formato de `Cuota.toJson` del app:
    plan mensual/prepago = `AppState.inscribir` (N cuotas, vencen el mismo día
    de cada mes a medianoche, concepto "Plan · Setiembre 2026 (−10%)");
    plan por clase o clase suelta = `agregarClaseSuelta` (una cuota hoy)."""
    from web.academia import _sumar_meses
    us = time.time_ns() // 1000
    base = {"academiaId": a["id"], "alumnoId": al["id"], "pagada": False}
    if tipo == "suelta":
        return [dict(base, id=f"cu_{us}", concepto=f"Clase suelta {ahora.day}/{ahora.month}", monto=round(monto, 2),
                     vencimiento=ahora.isoformat())]
    if plan["tipo"] == "porClase":
        return [dict(base, id=f"cu_{us}", concepto=plan["nombre"], monto=round(plan["precioMes"], 2), vencimiento=ahora.isoformat())]
    precio, dto = _precio_final(a, plan, al)
    suf = f" (−{dto:.0f}%)" if dto > 0 else ""
    dia = datetime(ahora.year, ahora.month, ahora.day)
    out = []
    for i in range(meses):
        v = _sumar_meses(dia, i)
        out.append(dict(base, id=f"cu_{us}_{i}", concepto=f"{plan['nombre']} · {_mes_anio(v)}{suf}", monto=precio,
                        vencimiento=v.isoformat()))
    return out


def agregar_cuotas_db(email: str, academia_id: str, alumno_id: str, armar) -> list[dict] | None:
    """Agrega cuotas a la matrícula bajo `FOR UPDATE`, SOLO si la academia es
    del correo (`pichangol_academias.dueno`). [armar](data) → cuotas nuevas.
    None si no existe / no es suya / falló."""
    if not pg.habilitado:
        return None
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT m.data FROM pichangol_matriculas m JOIN pichangol_academias a ON a.id = m.academia_id "
                        "WHERE m.id = %s AND m.academia_id = %s AND lower(a.dueno) = %s "
                        "AND coalesce(m.eliminada,false) = false AND coalesce(a.eliminada,false) = false FOR UPDATE OF m",
                        (alumno_id, academia_id, email.lower()))
            row = cur.fetchone()
            if not row:
                conn.rollback()
                return None
            data = row[0] if isinstance(row[0], dict) else json.loads(row[0] or "{}")
            data.setdefault("id", alumno_id)
            nuevas = armar(data)
            if not nuevas:
                conn.rollback()
                return None
            data["cuotas"] = [c for c in (data.get("cuotas") or []) if isinstance(c, dict)] + nuevas
            cur.execute("UPDATE pichangol_matriculas SET data = %s::jsonb, updated_at = now() WHERE id = %s",
                        (ui.json_js(data), alumno_id))
            conn.commit()
            return nuevas
    except Exception as ex:  # noqa: BLE001
        print(f"[cobros-web] no se pudo agregar cuota a {alumno_id}: {ex}", flush=True)
        return None


@router.get("/anfitrion/cobros/agregar", response_class=HTMLResponse)
def pagina_agregar_cuota(request: Request, academia: str = "", alumno: str = "") -> HTMLResponse:
    from web.academia import _planes
    from web.anfitrion_academia import _mias, _moneda
    ses, resp = _sesion_o_entrar(request, "/anfitrion/cobros/agregar")
    if resp is not None:
        return resp
    acads = _mias(ses["email"])
    if not acads:
        return _render("Agregar cuota", va.cabecera("Agregar cuota", volver="/anfitrion/cobros") + va.panel(va.vacio(
            "academias", "Aún no tienes una academia", "Créala y luego agrega cuotas a tus alumnos.",
            "<a class='btn' href='/anfitrion/academia'>Crear mi academia</a>")), ses)
    a = next((x for x in acads if x["id"] == academia), acads[0])
    sim = _moneda(a)
    mats = sorted(datos.matriculas_de_academias([a["id"]]), key=lambda m: str(m.get("nombre") or "").lower())
    planes = _planes(a)
    sel = _selector_academia(acads, a)
    volver = f"/anfitrion/cobros?academia={quote(a['id'])}"
    titulo_v = f"Agregar cuota · {a.get('nombre') or 'Mi academia'}"
    if not mats:
        cuerpo = (va.cabecera(titulo_v, volver=volver, acciones=sel)
                  + va.panel(va.vacio("comparar", "Aún no tienes alumnos en esta academia",
                                      "Cuando se matriculen (desde la app o la web) podrás agregarles cuotas aquí.")))
        return _render("Agregar cuota", cuerpo, ses)
    opts = "".join(f"<option value='{e(m['id'])}'{' selected' if m['id'] == alumno else ''}>{e(m.get('nombre') or 'Alumno')}"
                   f"{' · ' + e(m['apoderadoNombre']) if m.get('apoderadoNombre') else ''}</option>" for m in mats)
    grupos: dict[str, list[dict]] = {}
    for p in planes:
        grupos.setdefault(p["programa"], []).append(p)
    tarjetas = ""
    for prog, lst in grupos.items():
        tarjetas += f"<div class='ag-prog'>{e(prog)}</div>" if prog else ""
        for p in sorted(lst, key=lambda x: x["frecuenciaSemana"]):
            tit = (f"{p['frecuenciaSemana']}x por semana" if prog and p["frecuenciaSemana"] else p["nombre"])
            sub = (f"Por clase · {sim} {p['precioMes']:.2f}" if p["tipo"] == "porClase" else
                   (f"Mensual · {sim} {p['precioMes']:.2f}/mes" if p["tipo"] == "mensual" else
                    f"Prepago {p['meses']} meses · {sim} {p['precioMes']:.2f}/mes"))
            tarjetas += (f"<label class='ag-op'><input type='radio' name='agPlan' value='{e(p['id'])}'>"
                         f"<span><b>{e(tit)}</b><small>{e(sub)}</small></span></label>")
    tarjetas += ("<label class='ag-op'><input type='radio' name='agPlan' value='__suelta'>"
                 "<span><b>🎾 Clase suelta</b><small>Una cuota de hoy por el monto que indiques</small></span></label>")
    cfg = {"academia": a["id"], "moneda": sim,
           "planes": {p["id"]: {"tipo": p["tipo"], "precio": p["precioMes"], "meses": p["meses"], "nombre": p["nombre"]} for p in planes},
           "alumnos": {m["id"]: {"socio": m.get("esSocioSede", True) is not False, "orden": int(m.get("ordenHermano") or 1)} for m in mats},
           "recargo": float(a.get("recargoInvitado") or 0), "h2": float(a.get("descuentoHermano2") or 0),
           "h3": float(a.get("descuentoHermano3") or 0), "prepago": float(a.get("descuentoPrepago") or 0)}
    meses = "".join(f"<option value='{n}'>{n} {'mes' if n == 1 else 'meses'}</option>" for n in range(1, 13))
    cuerpo = (
        va.cabecera(titulo_v, "Inscribe a un alumno en un plan (genera sus cuotas mensuales por cobrar) o regístrale una clase suelta. "
                    "Aparece al instante en su app, en “Mis clases y pagos”.", volver=volver, acciones=sel)
        + "<section class='va-panel ag-card'><label class='ag-l' for='agAl'>Alumno</label>"
        f"<select id='agAl'>{opts}</select>"
        "<div class='ag-l'>¿Qué le cobras?</div>"
        + (tarjetas if planes else "<p class='vn-tenue'>Tu academia aún no tiene planes con precio. <a href='/anfitrion/academia'>Agrégalos</a> o registra una clase suelta.</p>" + tarjetas)
        + f"<div id='agMesesBox' hidden><label class='ag-l' for='agMeses'>¿Por cuántos meses?</label><select id='agMeses'>{meses}</select></div>"
        f"<div id='agMontoBox' hidden><label class='ag-l' for='agMonto'>Monto</label><div class='inp-moneda ag-monto'><span>{e(sim)}</span>"
        "<input id='agMonto' inputmode='decimal' maxlength='9' placeholder='0.00'></div></div>"
        "<div class='ag-prev' id='agPrev' hidden></div>"
        "<button type='button' class='btn ag-ok' id='agOk' disabled>Agregar</button></section>")
    return _render("Agregar cuota", cuerpo, ses, js=f"window.__ag={ui.json_js(cfg, ensure_ascii=False)};{JS_AGREGAR_CUOTA}")


@router.post("/anfitrion/cobros/agregar")
def agregar_cuota(request: Request, body: dict = Body(default_factory=dict)) -> JSONResponse:
    """Inscribir en plan / clase suelta desde la web (el total lo recalcula el
    servidor con los datos de la academia y del alumno)."""
    from web.academia import _planes
    from web.anfitrion_academia import _mia, _moneda
    ses = sesion.de_request(request)
    if not ses:
        return _err("sesion_requerida", 401)
    email = ses["email"].lower()
    a = _mia(email, str(body.get("academia_id") or ""))
    if a is None:
        return _err("Esa academia no es tuya.", 404)
    tipo = "suelta" if body.get("plan_id") == "__suelta" else "plan"
    plan = None
    meses = 1
    monto = 0.0
    if tipo == "plan":
        plan = next((p for p in _planes(a) if p["id"] == str(body.get("plan_id") or "")), None)
        if plan is None:
            return _err("Elige un plan de tu academia.")
        try:
            meses = int(body.get("meses") or 1)
        except (TypeError, ValueError):
            meses = 0
        if plan["tipo"] != "porClase" and not 1 <= meses <= 12:
            return _err("Elige entre 1 y 12 meses.")
    else:
        try:
            monto = round(float(str(body.get("monto") or "").replace(",", ".")), 2)
        except ValueError:
            monto = 0.0
        if not 0 < monto <= 100000:
            return _err("Escribe un monto válido.")
    ahora = datetime.now()
    nuevas = agregar_cuotas_db(email, a["id"], str(body.get("alumno_id") or ""),
                               lambda data: cuotas_nuevas(a, data, tipo, plan, meses, monto, ahora))
    if nuevas is None:
        return _err("No se pudo agregar. Ese alumno no es de tu academia o hubo un problema; reintenta.", 409)
    sim = _moneda(a)
    total = sum(float(c["monto"]) for c in nuevas)
    print(f"[cobros-web] {email} agregó {len(nuevas)} cuota(s) {sim} {total:.2f} a {body.get('alumno_id')}", flush=True)
    return _json_ok(cuotas=len(nuevas), total=round(total, 2), moneda=sim)


JS_AGREGAR_CUOTA = r"""
(function(){
  var C = window.__ag || {}, $ = function(id){ return document.getElementById(id); };
  function plan(){ var r = document.querySelector("input[name='agPlan']:checked"); return r ? r.value : ''; }
  function fmt(n){ return C.moneda + ' ' + Number(n || 0).toFixed(2); }
  function calc(){
    var pid = plan(), al = C.alumnos[$('agAl').value] || {socio: true, orden: 1}, prev = $('agPrev'), ok = $('agOk');
    $('agMesesBox').hidden = !(pid && pid !== '__suelta' && C.planes[pid].tipo !== 'porClase');
    $('agMontoBox').hidden = pid !== '__suelta';
    if(!pid){ prev.hidden = true; ok.disabled = true; return; }
    if(pid === '__suelta'){ var m = Number(($('agMonto').value || '').replace(',', '.')); ok.disabled = !(m > 0); prev.hidden = !(m > 0);
      prev.textContent = 'Se agrega 1 cuota por cobrar de ' + fmt(m) + ' (clase suelta de hoy).'; ok.textContent = 'Agregar clase suelta'; return; }
    var p = C.planes[pid];
    if(p.tipo === 'porClase'){ prev.hidden = false; ok.disabled = false; prev.textContent = 'Se agrega 1 cuota por cobrar de ' + fmt(p.precio) + ' (' + p.nombre + ').'; ok.textContent = 'Agregar cuota'; return; }
    var base = p.precio + (al.socio ? 0 : C.recargo), dto = (al.orden >= 3 ? C.h3 : (al.orden === 2 ? C.h2 : 0)) + (p.tipo === 'prepago' ? C.prepago : 0);
    dto = Math.min(dto, 100); var cu = Math.max(0, Math.round(base * (1 - dto / 100) * 100) / 100), n = Number($('agMeses').value || 1);
    prev.hidden = false; ok.disabled = false;
    prev.innerHTML = 'Se generan <b>' + n + ' cuota' + (n === 1 ? '' : 's') + '</b> mensual' + (n === 1 ? '' : 'es') + ' de <b>' + fmt(cu) + '</b>' + (dto > 0 ? ' (−' + dto.toFixed(0) + '%)' : '') + (al.socio ? '' : ' · tarifa invitado') + '. Total por cobrar: <b>' + fmt(cu * n) + '</b>.';
    ok.textContent = 'Inscribir y generar ' + n + ' cuota' + (n === 1 ? '' : 's');
  }
  document.querySelectorAll("input[name='agPlan']").forEach(function(r){ r.addEventListener('change', calc); });
  ['agAl', 'agMeses'].forEach(function(id){ $(id).addEventListener('change', calc); });
  $('agMonto').addEventListener('input', calc);
  $('agOk').addEventListener('click', function(){
    var al = $('agAl'), nom = al.options[al.selectedIndex].text;
    pcgConfirmar({titulo: 'Agregar a ' + nom, icono: '🧾', mensaje: $('agPrev').textContent, confirmar: 'Agregar', cancelar: 'Volver'}).then(function(ok){
      if(!ok) return;
      pcgCargando('Guardando…');
      fetch('/anfitrion/cobros/agregar', {method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({academia_id: C.academia, alumno_id: al.value, plan_id: plan(), meses: Number($('agMeses').value || 1), monto: $('agMonto').value})})
        .then(function(r){ return r.json(); }).then(function(j){
          pcgCargando(false);
          if(j.ok) pcgAvisar({titulo: 'Listo ✅', icono: '🧾', confirmar: 'Ver cobros', mensaje: 'Se agregó ' + j.cuotas + ' cuota' + (j.cuotas === 1 ? '' : 's') + ' por ' + j.moneda + ' ' + Number(j.total).toFixed(2) + ' a ' + nom + '.'})
            .then(function(){ pcgIr('/anfitrion/cobros?academia=' + encodeURIComponent(C.academia), 'Abriendo cobros…'); });
          else pcgAvisar({titulo: 'No se pudo', icono: '⚠️', mensaje: j.mensaje || 'Reintenta.'});
        }).catch(function(){ pcgCargando(false); pcgAvisar({titulo: 'Sin conexión', icono: '⚠️', mensaje: 'Reintenta.'}); });
    });
  });
  calc();
})();
"""


# ── estilos y scripts ───────────────────────────────────────────────────────

# CSS de estas páginas: `web/estilos_anfitrion.py` (va en el CSS versionado del sitio).

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
(function(){var q=document.getElementById('qCli');if(q)q.addEventListener('input',function(){var v=q.value.trim().toLowerCase(),n=0;document.querySelectorAll('#listaCli tr').forEach(function(c){var ok=!v||c.dataset.q.indexOf(v)>=0;c.hidden=!ok;if(ok)n++;});var z=document.getElementById('cliVacio');if(z)z.hidden=!!n;});
document.addEventListener('click',function(ev){var b=ev.target.closest('[data-cli]');if(!b)return;var c=window.__cli[b.dataset.cli];if(!c)return;
  var av=c.foto?'<img class="ng-av" src="'+ngEsc(c.foto)+'" alt="" referrerpolicy="no-referrer">':'<span class="ng-av">'+ngEsc((c.nombre||'?').charAt(0).toUpperCase())+'</span>';
  var h='<div class="ng-ficha"><div class="fh">'+av+'<div><b>'+ngEsc(c.nombre)+'</b><small>'+ngEsc(c.contacto)+'</small></div></div><div class="dts">';
  c.datos.forEach(function(d){h+='<div><small>'+ngEsc(d[0])+'</small><b>'+ngEsc(d[1])+'</b></div>';});h+='</div><div class="acc">';
  if(c.wa){h+='<a class="btn sec mini-b" target="_blank" rel="noopener" href="https://wa.me/'+c.wa+'">💬 WhatsApp</a>';
    if(c.debe>0){var msg='Hola '+c.nombre+' 👋 Te recordamos tu saldo pendiente de '+c.moneda+c.debe.toFixed(2)+' por tu reserva. ¡Gracias!';h+='<a class="btn mini-b" target="_blank" rel="noopener" href="https://wa.me/'+c.wa+'?text='+encodeURIComponent(msg)+'">Recordar cobro</a>';}}
  h+='<a class="btn sec mini-b" href="/anfitrion/calendario">📝 Reservar</a></div>';
  if(c.debe>0)h+='<div class="ng-debe">Te debe '+ngEsc(c.moneda)+' '+c.debe.toFixed(2)+'</div>';
  h+='<label class="nota-l" for="ngNota">Notas privadas</label><textarea id="ngNota" maxlength="600" placeholder="Solo tú las ves. Ej: prefiere Cancha 2, juega martes, paga efectivo.">'+ngEsc(c.nota)+'</textarea>';
  h+='<div class="hist"><b>Historial de reservas</b>';c.historial.forEach(function(r){h+='<div><span>'+ngEsc(r[0])+' · '+ngEsc(r[1])+' · '+ngEsc(r[2])+'</span><span>'+ngEsc(r[3])+' · '+ngEsc(r[4])+'</span></div>';});
  if(!c.historial.length)h+='<div>Sin reservas registradas.</div>';h+='</div></div>';
  pcgConfirmar({titulo:'Ficha del cliente',html:h,confirmar:'Guardar nota',cancelar:'Cerrar',icono:'👤'}).then(async function(ok){if(!ok)return;var t=(document.getElementById('ngNota')||{}).value||'';
    var j=await ngPost('/anfitrion/clientes/nota',{clave:c.clave,texto:t});if(j&&j.ok){c.nota=t.trim();pcgToast('Nota guardada');}else if(j){pcgAvisar({titulo:'No se pudo',mensaje:j.error||'Reintenta.'});}});});})();
"""

JS_BONOS = r"""
(function(){var B=window.__bonos;
function form(b){b=b||{};var hs=[2,4,5,8,10,12,20];var h='<div class="ng-form"><label id="bHl">¿Cuántas horas trae el pack?</label><div class="chips" id="bH" role="group" aria-labelledby="bHl">';
  hs.forEach(function(x){h+='<button type="button" class="chip'+(b.horas==x?' sel':'')+'" data-h="'+x+'">'+x+' h</button>';});
  h+='</div><input type="number" id="bHo" min="1" max="200" inputmode="numeric" placeholder="Otra cantidad de horas" aria-label="Otra cantidad de horas" value="'+(b.horas&&hs.indexOf(b.horas)<0?b.horas:'')+'" style="margin-top:8px">';
  h+='<label for="bP">Precio del pack ('+ngEsc(B.moneda)+')</label><input type="number" id="bP" min="0.5" step="0.5" inputmode="decimal" value="'+(b.precio||'')+'">';
  h+='<label for="bN">Nombre (opcional)</label><input type="text" id="bN" maxlength="60" placeholder="Ej: Pack mensual" value="'+ngEsc(b.nombre||'')+'"><div class="err" id="bE"></div></div>';return h;}
async function editar(b){var nuevo=!b;var p=pcgConfirmar({titulo:nuevo?'Nuevo bono':'Editar bono',html:form(b),confirmar:'Guardar bono',icono:'🎟️'});
  setTimeout(function(){var g=document.getElementById('bH');if(g)g.addEventListener('click',function(ev){var c=ev.target.closest('[data-h]');if(!c)return;g.querySelectorAll('.chip').forEach(function(x){x.classList.toggle('sel',x===c);});document.getElementById('bHo').value='';});},60);
  var ok=await p;if(!ok)return;var sel=document.querySelector('#bH .chip.sel');var horas=parseInt(document.getElementById('bHo').value||(sel?sel.dataset.h:'0'),10);
  var precio=document.getElementById('bP').value,nombre=document.getElementById('bN').value;
  var j=await ngPost('/anfitrion/bonos/guardar',{id:b?b.id:'',club:B.club,horas:horas,precio:precio,nombre:nombre});
  if(j&&j.ok){pcgRecargar('Bono guardado ✅');}else if(j){await pcgAvisar({titulo:'No se pudo guardar',mensaje:j.error||'Reintenta.'});editar(b?Object.assign({},b,{horas:horas,precio:precio,nombre:nombre}):{horas:horas,precio:precio,nombre:nombre});}}
var n=document.getElementById('nuevoBono');if(n)n.addEventListener('click',function(){editar(null);});
document.addEventListener('click',async function(ev){var a=ev.target.closest('.vn-bono [data-acc]');if(!a)return;var b=JSON.parse(a.closest('.vn-bono').dataset.bono);
  if(a.dataset.acc==='editar'){editar(b);return;}
  if(a.dataset.acc==='activo'){var j=await ngPost('/anfitrion/bonos/'+encodeURIComponent(b.id)+'/activo',{activo:a.dataset.v==='1'});if(j&&j.ok)pcgRecargar();else if(j)pcgAvisar({titulo:'No se pudo',mensaje:j.error});return;}
  var ok=await pcgConfirmar({titulo:'Retirar bono',mensaje:'¿Quitar "'+(b.nombre||b.horas+' horas')+'" de tu local? Los jugadores que ya lo compraron conservan sus horas.',confirmar:'Retirar',destructivo:true});
  if(!ok)return;var k=await ngPost('/anfitrion/bonos/'+encodeURIComponent(b.id)+'/eliminar',{},'Retirando…');if(k&&k.ok)pcgRecargar('Bono retirado');else if(k)pcgAvisar({titulo:'No se pudo',mensaje:k.error});});})();
"""

JS_FIJAS = r"""
(function(){var F=window.__fijas,D=['Lun','Mar','Mié','Jue','Vie','Sáb','Dom'],tPrev=null;
function cancha(){var id=(document.getElementById('fC')||{}).value;return F.canchas.find(function(x){return x.id===id;})||F.canchas[0];}
function diaSel(){var d=document.querySelector('#fD .vn-chip.sel');return d?parseInt(d.dataset.d,10):0;}
function fin(h,paso){var p=h.split(':'),m=(+p[0])*60+(+p[1])+paso;m=m%1440;return ('0'+Math.floor(m/60)).slice(-2)+':'+('0'+(m%60)).slice(-2);}
function form(v){v=v||{};var h='<div class="vn-form"><label for="fC">Cancha</label><select id="fC">';
  F.canchas.forEach(function(c){h+='<option value="'+ngEsc(c.id)+'"'+((v.c||F.sel)===c.id?' selected':'')+'>'+ngEsc(c.nombre)+'</option>';});
  h+='</select><label id="fDl">Día de la semana</label><div class="vn-chips vn-dias" id="fD" role="group" aria-labelledby="fDl">';
  D.forEach(function(d,i){var s=(v.d||F.hoy)===i+1;h+='<button type="button" class="vn-chip'+(s?' sel':'')+'" aria-pressed="'+s+'" data-d="'+(i+1)+'">'+d+'</button>';});
  h+='</div><label for="fH">Hora</label><select id="fH"></select>';
  h+='<label for="fN">Cliente</label><input type="text" id="fN" maxlength="80" autocomplete="off" placeholder="Nombre del cliente o equipo" value="'+ngEsc(v.n||'')+'">';
  h+='<div class="vn-form-2"><div><label for="fT">WhatsApp (opcional)</label><input type="tel" id="fT" maxlength="20" inputmode="tel" value="'+ngEsc(v.t||'')+'"></div>';
  h+='<div><label for="fE">Correo (opcional)</label><input type="email" id="fE" maxlength="120" placeholder="Para ver sus reservas" value="'+ngEsc(v.e||'')+'"></div></div>';
  h+='<div class="vn-prev" id="fPrev" aria-live="polite"></div><div class="err" id="fErr" role="alert">'+ngEsc(v.err||'')+'</div></div>';return h;}
function horas(sel){var c=cancha(),d=diaSel(),s=document.getElementById('fH'),lst=(c.slots[String(d)]||[]);
  s.innerHTML=lst.length?'<option value="">Elige la hora</option>'+lst.map(function(h){return '<option value="'+h+'"'+(h===sel?' selected':'')+'>'+h+' – '+fin(h,c.paso)+'</option>';}).join(''):'<option value="">Ese día el club no atiende</option>';
  previa();}
function previa(){clearTimeout(tPrev);var box=document.getElementById('fPrev');if(!box)return;var c=cancha(),d=diaSel(),h=(document.getElementById('fH')||{}).value;
  if(!h){box.innerHTML='<b>Elige el día y la hora</b><small>Te mostramos qué reservas se crearán antes de guardar.</small>';return;}
  box.innerHTML='<b>Calculando…</b>';
  tPrev=setTimeout(async function(){try{var r=await fetch('/anfitrion/fijas/vista-previa?cancha_id='+encodeURIComponent(c.id)+'&dia='+d+'&hora='+encodeURIComponent(h));var j=await r.json();
    if(!j.ok){box.innerHTML='<b>'+ngEsc(j.error||'No se pudo calcular')+'</b>';return;}
    var n=j.crea.length,t='<b>'+(n?'Se crearán '+n+' reserva'+(n===1?'':'s'):'No se creará ninguna reserva por ahora')+'</b>';
    if(j.texto)t+='<span>'+ngEsc(j.texto)+'</span>';
    if(j.salta.length)t+='<small>Se salta'+(j.salta.length===1?'':'n')+': '+j.salta.map(function(x){var p=x.fecha.split('-');return +p[2]+'/'+(+p[1])+' ('+ngEsc(x.motivo)+')';}).join(', ')+'.</small>';
    t+='<small>Si un turno está ocupado o bloqueado, se salta.</small>';box.innerHTML=t;}catch(e){box.innerHTML='<b>Sin conexión para calcular</b>';}},250);}
async function nueva(v){var p=pcgConfirmar({titulo:'Nuevo cliente fijo',html:form(v),confirmar:'Guardar y generar reservas',cancelar:'Cancelar',icono:'🔁'});
  setTimeout(function(){horas(v&&v.h);document.getElementById('fC').addEventListener('change',function(){horas();});document.getElementById('fH').addEventListener('change',previa);
    var g=document.getElementById('fD');g.addEventListener('click',function(ev){var c=ev.target.closest('[data-d]');if(!c)return;g.querySelectorAll('.vn-chip').forEach(function(x){x.classList.toggle('sel',x===c);x.setAttribute('aria-pressed',x===c);});horas();});},60);
  var ok=await p;if(!ok)return;v={c:document.getElementById('fC').value,d:diaSel(),h:document.getElementById('fH').value,n:document.getElementById('fN').value.trim(),t:document.getElementById('fT').value,e:document.getElementById('fE').value.trim()};
  if(!v.h){v.err='Elige la hora.';return nueva(v);}if(!v.n){v.err='Escribe el nombre del cliente.';return nueva(v);}
  var j=await ngPost('/anfitrion/fijas/nueva',{cancha_id:v.c,dia:v.d,hora:v.h,nombre:v.n,telefono:v.t,email:v.e},'Generando reservas…');
  if(j&&j.ok){await pcgAvisar({titulo:'Cliente fijo guardado ✅',mensaje:'Se crearon '+j.creadas+' reserva(s) de las próximas semanas.'+(j.omitidas&&j.omitidas.length?' Omitidas: '+j.omitidas.join('; ')+'.':''),icono:'🔁'});pcgRecargar();}
  else if(j){v.err=j.error||'No se pudo guardar.';nueva(v);}}
document.addEventListener('click',function(ev){if(ev.target.closest('[data-nueva-fija]'))nueva();});
document.addEventListener('change',async function(ev){var i=ev.target.closest('[data-fija] [data-acc="activo"]');if(!i)return;var id=i.closest('[data-fija]').dataset.fija;
  var j=await ngPost('/anfitrion/fijas/'+encodeURIComponent(id)+'/activo',{activo:i.checked});if(j&&j.ok){pcgToast(i.checked?'Reactivada: se completan sus próximas semanas':'Pausada: ya no se generan sus reservas');i.closest('tr').classList.toggle('vn-pausa',!i.checked);}else{i.checked=!i.checked;if(j)pcgAvisar({titulo:'No se pudo',mensaje:j.error});}});
document.addEventListener('click',async function(ev){var b=ev.target.closest('[data-fija] [data-acc="quitar"]');if(!b)return;var id=b.closest('[data-fija]').dataset.fija;
  var ok=await pcgConfirmar({titulo:'Quitar cliente fijo',mensaje:'Se deja de generar sus reservas. Las que ya están creadas siguen en tu agenda.',confirmar:'Quitar',destructivo:true});if(!ok)return;
  var j=await ngPost('/anfitrion/fijas/'+encodeURIComponent(id)+'/quitar',{},'Quitando…');if(j&&j.ok)pcgRecargar();else if(j)pcgAvisar({titulo:'No se pudo',mensaje:j.error});});})();
"""

JS_DISPO = (r"""
document.addEventListener('change',async function(ev){var i=ev.target.closest('.vn-turnos input[type=checkbox]');if(!i)return;var abrir=i.checked;
  var j=await ngPost('/anfitrion/bloqueo',{cancha_id:window.__dispo.cancha,fecha:i.dataset.f,base:window.__dispo.base,hora:i.dataset.h,bloquear:!abrir},abrir?'Abriendo…':'Cerrando…');
  if(j&&j.ok){pcgToast(abrir?'Turno abierto ✅':'Turno cerrado');var t=i.closest('.vn-turno');if(t){t.classList.toggle('cerrada',!abrir);var s=t.querySelector('small');if(s&&!s.classList.contains('vn-prio'))s.textContent=abrir?'Abierta':'Cerrada';}}
  else{i.checked=!abrir;if(j)pcgAvisar({titulo:j.error==='requiere_pro'?'Es ⟦MARCA⟧ Pro':'No se pudo',mensaje:j.mensaje||j.error||'Reintenta.'});}});
document.addEventListener('click',async function(ev){var b=ev.target.closest('[data-lote]');if(!b||b.disabled)return;var D=window.__dispo,n=+b.dataset.n||0,cerrar=b.dataset.lote==='cerrar_dia';
  var ok=await pcgConfirmar(cerrar?{titulo:'Cerrar todo el día',mensaje:'Se cierran '+n+' turno'+(n===1?'':'s')+' abiertos de este día. Los reservados y los que ya pasaron no cambian.',confirmar:'Cerrar el día',destructivo:true,icono:'🔒'}
    :{titulo:'Abrir horas valle',mensaje:'Se abren '+n+' turno'+(n===1?'':'s')+' de hora valle que estaban cerrados, para que los puedan reservar.',confirmar:'Abrir horas valle',icono:'☀️'});
  if(!ok)return;var j=await ngPost('/anfitrion/disponibilidad/lote',{cancha_id:D.cancha,base:D.base,accion:b.dataset.lote},cerrar?'Cerrando turnos…':'Abriendo turnos…');
  if(j&&j.ok){pcgRecargar(j.n?(cerrar?'Día cerrado':'Horas valle abiertas'):'No había turnos que cambiar');}
  else if(j){pcgAvisar({titulo:j.error==='requiere_pro'?'Es ⟦MARCA⟧ Pro':'No se pudo',mensaje:j.mensaje||j.error||'Reintenta.'});}});
""").replace('⟦MARCA⟧', MARCA)

# Comunes a las vistas: selects que se envían solos y botón de fecha que abre el calendario.
JS_VN = r"""
document.addEventListener('change',function(ev){var s=ev.target.closest('[data-vn-auto],[data-vn-fecha]');if(s&&s.form){if(window.pcgBarra)window.pcgBarra(true);s.form.submit();}});
document.addEventListener('click',function(ev){var f=ev.target.closest('.vn-fecha');if(!f)return;var i=f.querySelector('input[type=date]');if(i&&i.showPicker&&ev.target!==i){try{i.showPicker();}catch(e){}}});
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
var t=document.getElementById('recTodos');if(t)t.addEventListener('click',async function(){
  var j=await ngPost('/anfitrion/cobros/recordar-todos',{academia_id:C.academia},'Enviando recordatorios…');if(!j)return;
  if(!j.ok){pcgAvisar({titulo:'No se pudo',mensaje:j.error||'Reintenta.'});return;}
  var n=j.app||0,wa=j.whatsapp||[],sin=j.sin_contacto||[];
  if(wa.length||sin.length){var h='<p class="vn-dlg-p">'+(n?'Recordé a '+n+' por la app 📲. ':'')+(wa.length?'Estos no tienen la app: avísales por WhatsApp.':'')+'</p>';
    wa.forEach(function(f){h+='<div class="ng-cuota"><b>'+ngEsc(f.nombre)+'</b><a class="btn mini-b" target="_blank" rel="noopener" href="'+ngEsc(f.wa)+'" data-marca="'+ngEsc(f.id)+'">💬 Enviar</a></div>';});
    sin.forEach(function(x){h+='<div class="ng-cuota"><b>'+ngEsc(x)+'</b><small>Sin WhatsApp ni app</small></div>';});
    await pcgAvisar({titulo:'Avisar por WhatsApp',html:h,confirmar:'Listo',icono:'💬'});pcgRecargar();}
  else{await pcgAvisar({titulo:n?'Recordatorios enviados':'Nadie por recordar',mensaje:n?'Recordé a '+n+' por la app 📲':'Ya les recordaste a todos esta semana.'});pcgRecargar();}});
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
