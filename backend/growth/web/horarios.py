"""Lógica de horarios y precios de una cancha, ESPEJO de `Cancha` en el APK
(`lib/models/models.dart`): mismos slots, misma regla de cierre que cruza
medianoche, misma fecha real de los turnos de madrugada, misma hora feliz y
mismo precio por slot. Sin dependencias: se prueba solo.
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone

DIAS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct",
         "nov", "dic"]

# Zona horaria por país (para saber qué turnos de HOY ya pasaron).
_UTC_OFFSET = {"PE": -5, "EC": -5, "BO": -4}


def hora_en_minutos(hhmm: str) -> int | None:
    try:
        h, m = str(hhmm).strip().split(":")
        h, m = int(h), int(m)
    except (ValueError, AttributeError):
        return None
    if not (0 <= h <= 24 and 0 <= m < 60):
        return None
    return h * 60 + m


def minutos_en_hora(m: int) -> str:
    m = m % (24 * 60)
    return f"{m // 60:02d}:{m % 60:02d}"


def slots(apertura: str, cierre: str, paso: int, desde_minutos: int | None = None) -> list[str]:
    """Horas de INICIO reservables (paso = duración del slot). Cierre <=
    apertura → cruza medianoche (07:00→00:00, 18:00→02:00, 00:00→00:00).
    REGLA (director, sep-2026, espejo de `Cancha.horariosSlots`): la hora de
    cierre es la hora en que EMPIEZA el último turno (cierra 23:00 → último
    turno 23:00–00:00; cierra 00:00 → 00:00–01:00 de la madrugada). 24 h =
    24 turnos sin repetir el de medianoche."""
    ini = hora_en_minutos(apertura)
    fin = hora_en_minutos(cierre)
    paso = paso if paso and paso > 0 else 60
    if ini is None or fin is None:
        return []
    if fin <= ini:
        fin += 24 * 60
    tope = fin - 1 if fin - ini >= 24 * 60 else fin
    out = []
    m = ini
    while m <= tope:
        if desde_minutos is None or m >= desde_minutos:
            out.append(minutos_en_hora(m))
        m += paso
    return out


def hora_fin(inicio: str, paso: int) -> str:
    m = hora_en_minutos(inicio)
    if m is None:
        return inicio
    return minutos_en_hora(m + (paso if paso and paso > 0 else 60))


def slot_es_madrugada(apertura: str, cierre: str, hora: str) -> bool:
    """Con cierre que cruza medianoche, los turnos con hora < apertura son del
    día SIGUIENTE (cancha 18:00→02:00: 00:00 y 01:00 son madrugada)."""
    ini, fin, h = hora_en_minutos(apertura), hora_en_minutos(cierre), hora_en_minutos(hora)
    if ini is None or fin is None or h is None:
        return False
    return fin <= ini and h < ini


def fecha_real(base_iso: str, apertura: str, cierre: str, hora: str) -> str:
    if not slot_es_madrugada(apertura, cierre, hora):
        return base_iso
    try:
        d = date.fromisoformat(base_iso) + timedelta(days=1)
        return d.isoformat()
    except ValueError:
        return base_iso


def es_valle(hora: str, desde: str, hasta: str) -> bool:
    d = (desde or "").strip() or "00:00"
    h = (hasta or "").strip() or "12:00"
    if d == h:
        return False
    if d < h:
        return d <= hora < h
    return hora >= d or hora < h  # cruza medianoche


def precio_hora_en(precio_hora: float, hora: str, descuento_valle: int,
                   valle_desde: str, valle_hasta: str) -> float:
    if descuento_valle and descuento_valle > 0 and es_valle(hora, valle_desde, valle_hasta):
        return precio_hora * (100 - min(max(descuento_valle, 0), 90)) / 100
    return precio_hora


def redondear_precio(x: float) -> int:
    """Redondeo del precio de un turno: .50 va hacia ARRIBA (22.5 → 23),
    igual que `double.round()` de Dart. OJO: `round()` de Python redondea al
    par (22.5 → 22) y descuadraba la web con el APP en S/ 1 por turno."""
    return int(math.floor(float(x) + 0.5 + 1e-9))


def precio_base_turno(precio_hora: float, paso: int, precio_turno: float = 0.0) -> float:
    """Lo que cuesta UN turno sin descuentos. El dueño cobra POR TURNO
    (`precio_turno` > 0: "S/ 15 el turno de 1 h 30") o POR HORA (precio por
    hora × duración). Espejo de `Cancha.precioBaseTurno` del APK."""
    paso = paso if paso and paso > 0 else 60
    if precio_turno and precio_turno > 0:
        return float(precio_turno)
    return float(precio_hora or 0) * paso / 60


def precio_slot(precio_hora: float, paso: int, descuento_slot: int = 0, *,
                precio_turno: float = 0.0, descuento_valle: int = 0,
                en_valle: bool = False) -> int:
    """Precio de UN turno: base (por turno o por hora × duración) con UN
    descuento: el puntual del turno (`pichangol_descuentos_slot`) si lo hay,
    si no la hora feliz de ese horario. No se acumulan (así lo cobra el APK:
    `AppState.precioSlotEfectivo`)."""
    base = precio_base_turno(precio_hora, paso, precio_turno)
    pct = descuento_slot if descuento_slot and descuento_slot > 0 else (
        descuento_valle if en_valle and descuento_valle and descuento_valle > 0 else 0)
    if pct > 0:
        base = base * (100 - min(max(int(pct), 0), 90)) / 100
    return redondear_precio(base)


def precio_turno_de(c: dict, hora: str, descuento_slot: int = 0) -> int:
    """Precio del turno `hora` de la cancha `c` (dict de `datos`). Fuente
    ÚNICA de la web para mostrar, reservar y sugerir precio."""
    valle = int(c.get("descuento_valle") or 0)
    return precio_slot(
        float(c.get("precio_hora") or 0), int(c.get("duracion_slot_min") or 60),
        descuento_slot, precio_turno=float(c.get("precio_turno") or 0),
        descuento_valle=valle,
        en_valle=valle > 0 and es_valle(hora, c.get("valle_desde") or "", c.get("valle_hasta") or ""))


def precio_hora_equivalente(precio_turno: float, paso: int) -> float:
    """Precio por hora que se guarda junto a un precio POR TURNO, para que los
    APKs viejos (que calculan hora × duración) cobren lo mismo."""
    paso = paso if paso and paso > 0 else 60
    return round(float(precio_turno) * 60 / paso, 4)


def precio_publico(c: dict) -> tuple[float, str]:
    """(monto, unidad) que se MUESTRA de una cancha: "15.00", "por turno de
    1 h 30" si el dueño cobra por turno; si no, precio por hora y "por hora"."""
    turno = float(c.get("precio_turno") or 0)
    if turno > 0:
        return turno, f"por turno de {duracion_texto(int(c.get('duracion_slot_min') or 60))}"
    return float(c.get("precio_hora") or 0), "por hora"


def duracion_texto(paso: int) -> str:
    """90 → "1 h 30", 60 → "1 h", 120 → "2 h"."""
    paso = paso if paso and paso > 0 else 60
    h, m = divmod(paso, 60)
    if not h:
        return f"{m} min"
    return f"{h} h" + (f" {m:02d}" if m else "")


def etiqueta_dia(iso: str, hoy: date | None = None) -> str:
    """"Hoy" / "Mañana" / "Lun 22" (misma etiqueta visible que usa el APK)."""
    try:
        d = date.fromisoformat(iso)
    except ValueError:
        return iso
    hoy = hoy or date.today()
    if d == hoy:
        return "Hoy"
    if d == hoy + timedelta(days=1):
        return "Mañana"
    return f"{DIAS[d.weekday()]} {d.day}"


def fecha_larga(iso: str) -> str:
    try:
        d = date.fromisoformat(iso)
    except ValueError:
        return iso
    return f"{DIAS[d.weekday()]} {d.day} {MESES[d.month - 1]} {d.year}"


def ahora_local(pais: str) -> datetime:
    return datetime.now(timezone(timedelta(hours=_UTC_OFFSET.get(pais, -5))))
