"""DISPONIBILIDAD: fechas reservables por país, turnos del día de una cancha
con precio y estado (`_slots_del_dia`), `GET /web/disponibilidad/{id}` y
`GET /web/libres` (qué canchas tienen un turno libre a una hora).

Movido tal cual desde `web/router.py`, que lo re-exporta (otros módulos usan
`wr._fechas_validas`, `wr._slots_del_dia`, `wr._es_iso`).
"""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Request

from web import datos, horarios, sesion
from reservas import reglas as _reglas
from web.comun import DIAS_ADELANTE, _moneda_de, _pais_de

router = APIRouter()


# ── disponibilidad ────────────────────────────────────────────────────────────

def _fechas_validas(pais: str) -> tuple[str, str]:
    hoy = horarios.ahora_local(pais).date()
    return hoy.isoformat(), (hoy + timedelta(days=DIAS_ADELANTE)).isoformat()


def _slots_del_dia(c: dict, fecha: str) -> list[dict]:
    """Slots del día con precio y estado. Hoy: se omiten los que ya pasaron.
    Con REGLAS DE RESERVA del dueño (`reservas.reglas`): horario de ese día de
    la semana, cierres especiales, franjas de precio, recargo de luz y
    ventana de anticipación."""
    pais = _pais_de(c)
    ahora = horarios.ahora_local(pais)
    c = _reglas.cancha_del_dia(c, fecha)
    desde = None
    if fecha == ahora.date().isoformat():
        desde = ahora.hour * 60 + ahora.minute + 1
    paso = c["duracion_slot_min"]
    horas = horarios.slots_de(c, desde)
    if c.get("_reglas"):
        horas = [h for h in horas if not _reglas.validar_inicio(
            c, horarios.fecha_real(fecha, c["hora_apertura"], c["hora_cierre"], h), h, ahora)]
    fechas = sorted({horarios.fecha_real(fecha, c["hora_apertura"], c["hora_cierre"], h) for h in horas} | {fecha})
    datos.precargar_dia(c["id"], fechas)  # reservas + bloqueos + descuentos: un viaje
    ocup = datos.ocupados(c["id"], fechas)
    desc = datos.descuentos(c["id"], fechas)
    out = []
    for h in horas:
        fr = horarios.fecha_real(fecha, c["hora_apertura"], c["hora_cierre"], h)
        out.append({
            "hora": h, "fin": horarios.hora_fin(h, paso), "fecha": fr,
            "precio": horarios.precio_turno_de(c, h, desc.get((fr, h), 0)),
            "ocupado": (fr, h) in ocup,
            "valle": c["descuento_valle"] > 0 and horarios.es_valle(h, c["valle_desde"], c["valle_hasta"]),
            "promo": desc.get((fr, h), 0),
            **_reglas.etiqueta_turno(c, h),
        })
    return out


@router.get("/web/disponibilidad/{cancha_id}")
def disponibilidad(cancha_id: str, fecha: str = "", request: Request = None) -> dict:
    c = datos.cancha(cancha_id)
    if not c:
        return {"ok": False, "error": "no_encontrada"}
    d_min, d_max = _fechas_validas(_pais_de(c))
    if not fecha or not _es_iso(fecha):
        return {"ok": False, "error": "fecha_invalida"}
    if not (d_min <= fecha <= d_max):
        return {"ok": False, "error": "fecha_fuera_de_rango", "min": d_min, "max": d_max}
    sim, iso = _moneda_de(c)
    cd = _reglas.cancha_del_dia(c, fecha)
    slots = _slots_del_dia(c, fecha)
    # Turnos ocupados en los que ESTE jugador está en lista de espera.
    # y los que son SUS reservas (no tiene sentido esperar el turno propio).
    espera: list[str] = []
    propias: list[str] = []
    ses = sesion.de_request(request) if request is not None else None
    if ses and ses.get("email") and any(s.get("ocupado") for s in slots):
        from web import jugador_espera as _je
        mis = {(x["fecha"], x["hora"]) for x in _je.mias(ses["email"], c["id"])}
        espera = [s["hora"] for s in slots if (s.get("fecha") or fecha, s["hora"]) in mis]
        mias_r = {(str(r.get("fecha")), str(r.get("hora_inicio"))) for r in datos.reservas_de_usuario(ses["email"])
                  if r.get("cancha_id") == c["id"]}
        propias = [s["hora"] for s in slots if s.get("ocupado") and (s.get("fecha") or fecha, s["hora"]) in mias_r]
    return {"ok": True, "fecha": fecha, "moneda": sim, "moneda_iso": iso,
            "slots": slots, "cerrado": cd.get("_cerrado", ""), "espera": espera, "propias": propias,
            "politica": _reglas.resumen_publico(c)}


def _hora_libre(c: dict, fecha: str, hora: str, ocup: set[tuple[str, str]]) -> bool:
    """¿Hay un turno LIBRE que cubra [hora] ese día? (inicio <= hora < fin,
    misma lógica de slots, madrugada y turnos ya pasados que la ficha)."""
    h = horarios.hora_en_minutos(hora)
    if h is None:
        return False
    c = _reglas.cancha_del_dia(c, fecha)
    ap, ci = c["hora_apertura"], c["hora_cierre"]
    ini = horarios.hora_en_minutos(ap)
    if ini is not None and h < ini and horarios.slot_es_madrugada(ap, ci, hora):
        h += 24 * 60  # 00:30 en una cancha 18:00→02:00 es la madrugada del día siguiente
    ahora = horarios.ahora_local(_pais_de(c))
    desde = ahora.hour * 60 + ahora.minute + 1 if fecha == ahora.date().isoformat() else None
    paso = c["duracion_slot_min"]
    for s_ in horarios.slots_de(c, desde):
        m = horarios.hora_en_minutos(s_)
        if m is None:
            continue
        if m < (ini or 0):
            m += 24 * 60
        if m <= h < m + paso:
            return (horarios.fecha_real(fecha, ap, ci, s_), s_) not in ocup
    return False


@router.get("/web/libres")
def libres(fecha: str = "", hora: str = "") -> dict:
    """Buscador de la portada: qué canchas reservables tienen un turno libre
    que cubra [hora] el día [fecha] (una sola consulta de ocupados para todas)."""
    if not fecha or not _es_iso(fecha) or horarios.hora_en_minutos(hora) is None:
        return {"ok": False, "error": "parametros_invalidos"}
    hoy = horarios.ahora_local("PE").date()
    try:
        d = date.fromisoformat(fecha)
    except ValueError:
        return {"ok": False, "error": "parametros_invalidos"}
    if not (hoy - timedelta(days=1) <= d <= hoy + timedelta(days=DIAS_ADELANTE + 1)):
        return {"ok": False, "error": "fecha_fuera_de_rango"}
    canchas = [c for c in datos.canchas_publicas() if datos.reservable(c)]
    fechas = [fecha, (d + timedelta(days=1)).isoformat()]
    ocup = datos.ocupados_varias([c["id"] for c in canchas], fechas)
    out = {c["id"]: _hora_libre(c, fecha, hora, ocup.get(c["id"], set())) for c in canchas}
    # Diagnóstico en los logs de Railway (como las líneas [foto]): horario real de cada cancha y el veredicto.
    print(f"[libres] {fecha} {hora}: " + " | ".join(
        f"{c['nombre']} {c['hora_apertura']}-{c['hora_cierre']}/{c['duracion_slot_min']}m "
        f"{'libre' if out[c['id']] else ('ocupada' if any(h == hora for _f, h in ocup.get(c['id'], set())) else 'sin turno')}"
        for c in canchas[:20]), flush=True)
    return {"ok": True, "fecha": fecha, "hora": hora, "libres": out}


def _es_iso(s: str) -> bool:
    try:
        date.fromisoformat(s)
        return True
    except (TypeError, ValueError):
        return False
