"""POLÍTICA DE DEVOLUCIONES con cargo por servicio (fase 4 del diseño,
decisión del director del 27-sep-2026, `docs/diseno-cargo-por-servicio.md` § 7).

Culqi NO devuelve su comisión al reembolsar, así que devolver el 100 % a la
tarjeta cuesta plata real. La política publicada en `/legal/devoluciones` y
mostrada ANTES de confirmar la cancelación:

- **A saldo Pichangol: 100 %, incluido el cargo por servicio.** No hay
  reembolso a Culqi, la plata se queda en el sistema. Es la opción que se
  ofrece PRIMERO.
- **Al medio original (tarjeta / Yape vía Culqi):** se devuelve el PRECIO de
  la cancha o academia; el cargo por servicio NO se devuelve (cubre lo que
  Culqi ya cobró), como la tarifa de servicio de Airbnb.
- **Cancela el anfitrión (dueño / academia):** el cliente recupera el 100 %
  incluido el cargo por el medio que elija; el costo de pasarela de esa
  devolución se descuenta al anfitrión en su siguiente liquidación.
- **Arrepentimiento:** dentro de `ARREPENTIMIENTO_HORAS` (1 h) del pago y con
  más de `ARREPENTIMIENTO_MIN_HORAS_TURNO` (24 h) para el turno: 100 %
  incluido el cargo, por cualquier medio.
- **Tarde** (< `WEB_CANCELACION_HORAS`, o el turno ya empezó): sin devolución.

Este módulo es SOLO la regla (pura, sin efectos): quién llama decide cómo
mover la plata (`culqi.reembolsar`, `stores.acreditar`).
"""
from __future__ import annotations

import os

import config

ARREPENTIMIENTO_HORAS = float(os.getenv("ARREPENTIMIENTO_HORAS", "1"))
ARREPENTIMIENTO_MIN_HORAS_TURNO = float(os.getenv("ARREPENTIMIENTO_MIN_HORAS_TURNO", "24"))

MEDIOS = ("saldo", "original")


def horas_minimas() -> float:
    return float(getattr(config, "WEB_CANCELACION_HORAS", 6) or 6)


def motivo(*, pagado: bool, horas_para_inicio: float, horas_desde_pago: float | None = None,
           cancela_anfitrion: bool = False) -> str:
    """Clasifica la cancelación: no_pagado · anfitrion · arrepentimiento ·
    plazo · tarde."""
    if not pagado:
        return "no_pagado"
    if cancela_anfitrion:
        return "anfitrion"
    if (horas_desde_pago is not None and 0 <= horas_desde_pago <= ARREPENTIMIENTO_HORAS
            and horas_para_inicio > ARREPENTIMIENTO_MIN_HORAS_TURNO):
        return "arrepentimiento"
    if horas_para_inicio >= horas_minimas():
        return "plazo"
    return "tarde"


def monto_devolucion(mot: str, medio: str, precio_centimos: int, cargo_centimos: int) -> tuple[int, bool]:
    """(céntimos a devolver, incluye_cargo) para ese motivo y medio."""
    precio = max(int(precio_centimos or 0), 0)
    cargo = max(int(cargo_centimos or 0), 0)
    if mot in ("no_pagado", "tarde"):
        return 0, False
    if mot in ("anfitrion", "arrepentimiento"):
        return precio + cargo, True
    # plazo: a saldo todo; al medio original solo el precio.
    if medio == "saldo":
        return precio + cargo, True
    return precio, False


def opciones(mot: str, precio_centimos: int, cargo_centimos: int, simbolo: str = "S/") -> list[dict]:
    """Opciones que se muestran ANTES de confirmar (la primera es la
    recomendada). Vacío = sin devolución."""
    if mot in ("no_pagado", "tarde"):
        return []
    out = []
    for medio in MEDIOS:
        monto, incluye = monto_devolucion(mot, medio, precio_centimos, cargo_centimos)
        if medio == "saldo":
            etiqueta = "A tu saldo Pichangol (al instante)"
            nota = "100 %, incluido el cargo por servicio. Lo usas en tu próxima reserva."
        else:
            etiqueta = "Al mismo medio de pago (tarjeta / Yape)"
            nota = ("100 %, incluido el cargo por servicio. Llega en 3 a 7 días hábiles."
                    if incluye else
                    "Se devuelve el precio de la reserva; el cargo por servicio no se devuelve "
                    "(cubre lo que la pasarela ya cobró). Llega en 3 a 7 días hábiles.")
        out.append({"medio": medio, "monto_centimos": monto, "monto": monto / 100.0, "incluye_cargo": incluye,
                    "etiqueta": etiqueta, "nota": nota, "simbolo": simbolo})
    return out


def resumen(*, pagado: bool, horas_para_inicio: float, horas_desde_pago: float | None, precio_centimos: int,
            cargo_centimos: int, simbolo: str = "S/", cancela_anfitrion: bool = False) -> dict:
    """Todo lo que la pantalla de cancelar necesita explicar."""
    mot = motivo(pagado=pagado, horas_para_inicio=horas_para_inicio, horas_desde_pago=horas_desde_pago,
                 cancela_anfitrion=cancela_anfitrion)
    return {
        "motivo": mot,
        "precio_centimos": int(precio_centimos or 0),
        "cargo_centimos": int(cargo_centimos or 0),
        "opciones": opciones(mot, precio_centimos, cargo_centimos, simbolo),
        "horas_minimas": horas_minimas(),
        "arrepentimiento_horas": ARREPENTIMIENTO_HORAS,
        "arrepentimiento_min_horas_turno": ARREPENTIMIENTO_MIN_HORAS_TURNO,
        "costo_anfitrion": mot == "anfitrion",
    }


def medio_valido(m: str | None) -> str:
    m = (m or "").strip().lower()
    return m if m in MEDIOS else "original"
