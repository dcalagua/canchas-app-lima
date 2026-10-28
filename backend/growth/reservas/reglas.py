"""REGLAS DE RESERVA configurables por cancha (plan nocturno A2, oct-2026).

Antes una cancha tenía UN horario para todos los días, UN precio con UNA hora
feliz y la política de cancelación era global (`WEB_CANCELACION_HORAS`). Ahora
el dueño puede configurar, por cancha (columna `pichangol_canchas.reglas_reserva`
jsonb, migración `0002`):

- **Horario por día de la semana** (`horario_semana`): `{"lun": {"apertura":
  "07:00", "cierre": "23:00"}, "dom": null}` — `null` = cerrado ese día; un día
  ausente usa el horario general de la cancha. Misma convención de siempre: el
  cierre es la hora en que EMPIEZA el último turno y puede cruzar medianoche.
- **Cierres especiales** (`cierres`): feriados, mantenimiento, eventos.
- **Franjas de precio** (`franjas`): por días y rango horario (punta, fin de
  semana…), con precio por hora o por turno. Una franja manda sobre la hora
  feliz; el descuento puntual de un turno se sigue aplicando encima.
- **Recargo de iluminación** (`recargo_luz`): monto fijo por turno desde una hora.
- **Ventana de reserva**: anticipación mínima (horas) y máxima (días).
- **Turnos por reserva**: mínimo y máximo de turnos seguidos.
- **Cancelación del club** (`cancelacion_horas`): reemplaza al global.
- **Límite por jugador** (`max_reservas_dia_jugador`).

Diseño: las reglas producen una **cancha efectiva del día** (`cancha_del_dia`):
copia del dict de `datos` con la apertura/cierre de ese día y las franjas
aplicables, así TODO el código existente de slots y precios (`horarios.slots`,
`horarios.precio_turno_de`) sigue siendo la única fuente y una cancha SIN
reglas se comporta exactamente igual que antes. Puro, sin efectos: se prueba
solo y su espejo en el APK es `lib/models/reglas_reserva.dart` (mismos casos en
`tests/fixtures/reglas_casos.json`).
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta

from web import horarios

DIAS_SEMANA = ("lun", "mar", "mie", "jue", "vie", "sab", "dom")

# Topes de cordura (lo que venga del cliente se recorta a esto).
MAX_FRANJAS = 24
MAX_CIERRES = 120
MAX_ANTICIPACION_DIAS = 180
MAX_TURNOS = 12


def _hora_ok(h) -> str | None:
    h = str(h or "").strip()
    return h if horarios.hora_en_minutos(h) is not None and len(h) == 5 else None


def _num(v, minimo: float = 0.0, maximo: float = 1e7) -> float:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return 0.0
    if x != x:  # NaN
        return 0.0
    return min(max(x, minimo), maximo)


def _entero(v, minimo: int = 0, maximo: int = 10_000) -> int:
    return int(_num(v, minimo, maximo))


def _dias(v) -> list[str]:
    if not isinstance(v, (list, tuple)):
        return list(DIAS_SEMANA)
    out = [d for d in DIAS_SEMANA if d in {str(x).strip().lower()[:3] for x in v}]
    return out or list(DIAS_SEMANA)


def normalizar(raw) -> dict:
    """Valida y recorta lo que manda el dueño. Nunca lanza: lo inválido se
    descarta. Devuelve SOLO las claves con valor (vacío = sin reglas)."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw or "{}")
        except ValueError:
            raw = {}
    if not isinstance(raw, dict):
        return {}
    out: dict = {}

    hs = raw.get("horario_semana")
    if isinstance(hs, dict):
        semana = {}
        for d in DIAS_SEMANA:
            if d not in hs:
                continue
            v = hs[d]
            if v is None or (isinstance(v, dict) and v.get("cerrado")):
                semana[d] = None
                continue
            if isinstance(v, dict):
                ap, ci = _hora_ok(v.get("apertura")), _hora_ok(v.get("cierre"))
                if ap and ci:
                    semana[d] = {"apertura": ap, "cierre": ci}
        if semana:
            out["horario_semana"] = semana

    cierres = []
    for c in (raw.get("cierres") or [])[:MAX_CIERRES]:
        if not isinstance(c, dict):
            continue
        try:
            f = date.fromisoformat(str(c.get("fecha") or "")).isoformat()
        except ValueError:
            continue
        cierres.append({"fecha": f, "motivo": str(c.get("motivo") or "")[:80]})
    if cierres:
        out["cierres"] = sorted({c["fecha"]: c for c in cierres}.values(), key=lambda c: c["fecha"])

    franjas = []
    for fr in (raw.get("franjas") or [])[:MAX_FRANJAS]:
        if not isinstance(fr, dict):
            continue
        desde, hasta = _hora_ok(fr.get("desde")), _hora_ok(fr.get("hasta"))
        ph, pt = _num(fr.get("precio_hora")), _num(fr.get("precio_turno"))
        if not desde or not hasta or desde == hasta or (ph <= 0 and pt <= 0):
            continue
        franjas.append({
            "nombre": str(fr.get("nombre") or "")[:40],
            "dias": _dias(fr.get("dias")),
            "desde": desde, "hasta": hasta,
            "precio_hora": round(ph, 2), "precio_turno": round(pt, 2),
        })
    if franjas:
        out["franjas"] = franjas

    rl = raw.get("recargo_luz")
    if isinstance(rl, dict) and _hora_ok(rl.get("desde")) and _num(rl.get("monto")) > 0:
        out["recargo_luz"] = {"desde": _hora_ok(rl.get("desde")), "monto": round(_num(rl.get("monto")), 2)}

    for clave, tope in (("anticipacion_min_horas", 72), ("anticipacion_max_dias", MAX_ANTICIPACION_DIAS),
                        ("cancelacion_horas", 168)):
        if raw.get(clave) not in (None, ""):
            out[clave] = round(_num(raw.get(clave), 0, tope), 2)
    for clave in ("min_turnos", "max_turnos"):
        if raw.get(clave) not in (None, "", 0, "0"):
            out[clave] = _entero(raw.get(clave), 1, MAX_TURNOS)
    if "min_turnos" in out and "max_turnos" in out and out["max_turnos"] < out["min_turnos"]:
        out["max_turnos"] = out["min_turnos"]
    if raw.get("max_reservas_dia_jugador") not in (None, "", 0, "0"):
        out["max_reservas_dia_jugador"] = _entero(raw.get("max_reservas_dia_jugador"), 1, 50)
    return out


def de_cancha(c: dict) -> dict:
    """Reglas normalizadas guardadas en la cancha (vacío si no tiene)."""
    return normalizar((c or {}).get("reglas_reserva") or {})


def dia_clave(fecha_iso: str) -> str:
    try:
        return DIAS_SEMANA[date.fromisoformat(fecha_iso).weekday()]
    except ValueError:
        return ""


def cerrado(c: dict, fecha_iso: str, reglas: dict | None = None) -> str:
    """Motivo si la cancha NO atiende ese día ("" si atiende)."""
    r = de_cancha(c) if reglas is None else reglas
    for ci in r.get("cierres") or []:
        if ci["fecha"] == fecha_iso:
            return ci.get("motivo") or "cerrado"
    d = dia_clave(fecha_iso)
    hs = r.get("horario_semana") or {}
    if d in hs and hs[d] is None:
        return "cerrado"
    return ""


def _franja_aplica(fr: dict, dia: str, hora: str) -> bool:
    return dia in fr["dias"] and horarios.es_valle(hora, fr["desde"], fr["hasta"])


def franja_de(reglas: dict, fecha_iso: str, hora: str) -> dict | None:
    """Primera franja que cubre ese turno (el orden lo decide el dueño)."""
    d = dia_clave(fecha_iso)
    for fr in reglas.get("franjas") or []:
        if _franja_aplica(fr, d, hora):
            return fr
    return None


def cancha_del_dia(c: dict, fecha_iso: str) -> dict:
    """Copia de la cancha con el horario y precios EFECTIVOS de ese día.

    - Sin reglas: devuelve `c` tal cual (comportamiento de siempre).
    - Día cerrado: `_cerrado` con el motivo y `_sin_turnos=True`.
    - `_reglas` y `_fecha` viajan para que `horarios.precio_turno_de` aplique
      franjas y recargo de luz sin cambiar su firma.
    """
    r = de_cancha(c)
    if not r:
        return c
    out = dict(c)
    out["_reglas"] = r
    out["_fecha"] = fecha_iso
    mot = cerrado(c, fecha_iso, r)
    if mot:
        out["_cerrado"] = mot
        out["_sin_turnos"] = True
        return out
    hs = (r.get("horario_semana") or {}).get(dia_clave(fecha_iso))
    if hs:
        out["hora_apertura"], out["hora_cierre"] = hs["apertura"], hs["cierre"]
    return out


def precio_turno(c: dict, hora: str, descuento_slot: int = 0) -> int | None:
    """Precio con reglas (franja + recargo) o None si no hay reglas que
    apliquen a este turno (el llamador usa el precio de siempre)."""
    r = c.get("_reglas")
    if not r:
        return None
    fecha = c.get("_fecha") or ""
    paso = int(c.get("duracion_slot_min") or 60)
    ap, ci = c.get("hora_apertura") or "07:00", c.get("hora_cierre") or "23:00"
    # Un turno de madrugada (cancha 18:00→02:00, 00:30) es del día siguiente.
    fr = franja_de(r, horarios.fecha_real(fecha, ap, ci, hora), hora) if fecha else None
    rl = r.get("recargo_luz")
    luz = bool(rl) and (horarios.slot_es_madrugada(ap, ci, hora) or
                        (horarios.hora_en_minutos(hora) or 0) >= (horarios.hora_en_minutos(rl["desde"]) or 0))
    if not fr and not luz:
        return None
    if fr:
        # La franja manda sobre la hora feliz; el descuento puntual sí se aplica.
        base = horarios.precio_slot(fr["precio_hora"], paso, descuento_slot, precio_turno=fr["precio_turno"])
    else:
        base = horarios.precio_turno_de({k: v for k, v in c.items() if k != "_reglas"}, hora, descuento_slot)
    return base + (horarios.redondear_precio(rl["monto"]) if luz else 0)


def validar_inicio(c: dict, fecha_iso: str, hora: str, ahora: datetime) -> str:
    """Error ('' si vale) de la ventana de reserva para un turno que empieza
    en `fecha_iso hora` (hora local del país; `ahora` también local, naive)."""
    r = de_cancha(c)
    if not r:
        return ""
    if cerrado(c, fecha_iso, r):
        return "cerrado"
    m = horarios.hora_en_minutos(hora)
    try:
        inicio = datetime.fromisoformat(fecha_iso) + timedelta(minutes=m or 0)
    except ValueError:
        return "fecha_invalida"
    ahora = ahora.replace(tzinfo=None)
    falta_h = (inicio - ahora).total_seconds() / 3600
    if r.get("anticipacion_min_horas") and falta_h < r["anticipacion_min_horas"]:
        return "anticipacion_minima"
    if r.get("anticipacion_max_dias") and falta_h > r["anticipacion_max_dias"] * 24:
        return "anticipacion_maxima"
    return ""


def validar_bloque(c: dict, n_turnos: int) -> str:
    """Error de cantidad de turnos seguidos de una reserva ('' si vale)."""
    r = de_cancha(c)
    if r.get("min_turnos") and n_turnos < r["min_turnos"]:
        return "min_turnos"
    if r.get("max_turnos") and n_turnos > r["max_turnos"]:
        return "max_turnos"
    return ""


def cancelacion_horas(c: dict, por_defecto: float) -> float:
    r = de_cancha(c)
    v = r.get("cancelacion_horas")
    return float(v) if v is not None else float(por_defecto)


def resumen_publico(c: dict) -> dict:
    """Lo que el jugador debe ver ANTES de pagar (política del club)."""
    r = de_cancha(c)
    return {
        "cancelacion_horas": r.get("cancelacion_horas"),
        "anticipacion_min_horas": r.get("anticipacion_min_horas"),
        "anticipacion_max_dias": r.get("anticipacion_max_dias"),
        "min_turnos": r.get("min_turnos"), "max_turnos": r.get("max_turnos"),
        "max_reservas_dia_jugador": r.get("max_reservas_dia_jugador"),
        "recargo_luz": r.get("recargo_luz"),
        "franjas": [{k: fr[k] for k in ("nombre", "dias", "desde", "hasta", "precio_hora", "precio_turno")}
                    for fr in r.get("franjas") or []],
        "horario_semana": r.get("horario_semana") or {},
        "cierres": [ci for ci in r.get("cierres") or [] if ci["fecha"] >= date.today().isoformat()][:30],
    }
