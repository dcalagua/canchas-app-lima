"""Lógica de horarios y precios de una cancha, ESPEJO de `Cancha` en el APK
(`lib/models/models.dart`): mismos slots, misma regla de cierre que cruza
medianoche, misma fecha real de los turnos de madrugada, misma hora feliz y
mismo precio por slot. Sin dependencias: se prueba solo.
"""

from __future__ import annotations

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


def precio_slot(precio_hora: float, paso: int, descuento_slot: int = 0) -> int:
    """Precio de UN slot (redondeado como en el APK), con el descuento
    puntual que el dueño pudo poner a ese slot (`pichangol_descuentos_slot`)."""
    paso = paso if paso and paso > 0 else 60
    p = precio_hora * paso / 60
    if descuento_slot and descuento_slot > 0:
        p = p * (100 - min(max(descuento_slot, 0), 90)) / 100
    return int(round(p))


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
