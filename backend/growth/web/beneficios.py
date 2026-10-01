"""BONO DE HORAS y PUNTOS PICHANGOL en la reserva web (pedido del director,
1-oct-2026: "en la web el jugador debe poder usar los mismos beneficios que
en el app"). Espejo de `club_detalle._reservar` del APK:

**Bono** (`metodo == 'bono'` en el app): horas prepagadas de ESE local
(`pichangol_bonos_comprados`, club + dueño). Cubre TODOS los turnos del
bloque (1 hora de bono = 1 turno, sea de 60 o 90 min) y solo si alcanza
(`miSaldoBono >= nSlots`). La fila guarda el precio de lista del turno, nace
`pagado` con `medio_pago = 'bono'` y NO genera contabilidad: el dueño ya
cobró al vender el pack (`_accionContable` devuelve null para 'bono'). No se
combina con seña, premio de fidelidad, puntos ni boleador (en el app son
caminos distintos). Diferencia con el app: los servicios extra que elija el
jugador se COBRAN en línea (en el app quedan en la fila sin cobrarse) y al
dueño se le liquidan solo esos extras.

**Puntos** (`_usarPuntos` en el app): 100 puntos = S/ 3 de descuento, solo
pagando TODO en línea en soles, con total > S/ 3, sin seña, sin premio de
fidelidad y un canje por reserva. El descuento lo absorbe Pichangol: la
liquidación al dueño va con el precio COMPLETO (la comisión se calcula sobre
eso). El canje se escribe en `pichangol_puntos_canjes` (la tabla del APK)
recién con el pago aprobado.

Ambos se APARTAN con el hold de `/web/asegurar` en `pichangol_canjes_web`
(SQL `docs/piloto/supabase_canjes_web.sql`) y se confirman en `/web/pagar`;
vuelven al jugador si el hold vence, se libera, el pago se rechaza o (ya
usados) si la cancelación tiene devolución según la política publicada.
"""
from __future__ import annotations

import re
import time

from web import datos, horarios

PUNTOS_CANJE = 100          # = 100 pts por canje (economía aprobada)
DESCUENTO_PUNTOS = 3        # = S/ 3 de descuento
MONEDA_PUNTOS = "PEN"       # el canje solo aplica en soles (como el app)
# Un apartado vive lo que el hold de la reserva (+ margen para el barrido).
BARRIDO_SEGUNDOS = datos.HOLD_SEGUNDOS + 120

_seq = {"n": 0}


def _id(prefijo: str) -> str:
    _seq["n"] = (_seq["n"] + 1) % 1000
    return f"{prefijo}_{int(time.time() * 1_000_000)}{_seq['n']:03d}"


def disponible() -> bool:
    return datos.canjes_web_disponible()


def local_de(c: dict) -> tuple[str, str]:
    """(club, dueño) = la llave del bono (los packs se venden por local)."""
    return str(c.get("club") or "").strip(), str(c.get("dueno") or "").strip().lower()


def horas_bono(email: str, c: dict) -> int:
    club, dueno = local_de(c)
    if not email or not club or not disponible():
        return 0
    return datos.saldo_bono(email, club, dueno)


def puntos_disponibles(email: str) -> tuple[int, int]:
    """(ganados, disponibles para canjear): `datos.puntos_de` menos lo que la
    web tenga apartado en holds vivos."""
    if not email:
        return 0, 0
    p = datos.puntos_de(email)
    return int(p.get("ganados") or 0), max(0, int(p.get("disponibles") or 0) - datos.puntos_apartados(email))


def puede_canjear_puntos(*, iso: str, total: float, desc_fidelidad: float, con_sena: bool, con_bono: bool,
                         disponibles: int) -> bool:
    """Regla del app (`club_detalle._puedeCanjear` + `canjea`)."""
    return (iso == MONEDA_PUNTOS and not con_sena and not con_bono and desc_fidelidad <= 0
            and total > DESCUENTO_PUNTOS and disponibles >= PUNTOS_CANJE)


def estado(email: str, c: dict, iso: str) -> dict:
    """Lo que el checkout web necesita pintar para el jugador con sesión."""
    if not disponible():
        return {"activo": False}
    club, _d = local_de(c)
    _g, pts = puntos_disponibles(email)
    return {"activo": True, "local": club, "bono": {"horas": horas_bono(email, c)},
            "puntos": {"disponibles": pts, "canje": PUNTOS_CANJE, "descuento": DESCUENTO_PUNTOS,
                       "aplica": iso == MONEDA_PUNTOS}}


def apartar_bono(email: str, c: dict, *, ref: str, ids: list[str], horas: int, cubre: float, iso: str) -> str:
    club, dueno = local_de(c)
    return datos.bono_apartar({"id": _id("cwb"), "tipo": "bono", "email": email, "cancha_id": c["id"], "club": club,
                               "dueno": dueno, "reserva_ref": ref, "reserva_ids": list(ids), "horas": int(horas),
                               "descuento": round(float(cubre), 2), "moneda": iso})


def apartar_puntos(email: str, c: dict, *, ref: str, ids: list[str]) -> str:
    club, dueno = local_de(c)
    ganados, _disp = puntos_disponibles(email)
    return datos.puntos_apartar({"id": _id("cwp"), "tipo": "puntos", "email": email, "cancha_id": c["id"], "club": club,
                                 "dueno": dueno, "reserva_ref": ref, "reserva_ids": list(ids), "puntos": PUNTOS_CANJE,
                                 "descuento": DESCUENTO_PUNTOS, "moneda": MONEDA_PUNTOS}, ganados, PUNTOS_CANJE)


def de_ref(ref: str) -> dict:
    """{'bono': canje|None, 'puntos': canje|None} vivos de esa reserva."""
    out = {"bono": None, "puntos": None}
    for cj in datos.canjes_web_de_ref(ref) if ref else []:
        out[cj["tipo"]] = cj
    return out


def referencia_puntos(filas: list[dict]) -> str:
    """Mismo formato que el APK: `<cancha>_<fecha>_<hora>` del primer turno."""
    f = filas[0]
    return f"{f.get('cancha_id')}_{f.get('fecha')}_{f.get('hora_inicio')}"


def confirmar(ref: str, filas: list[dict]) -> None:
    """Pago aprobado (o reserva gratis con el bono): lo apartado queda usado y
    los puntos se escriben en `pichangol_puntos_canjes`."""
    for cj in datos.canjes_web_de_ref(ref):
        if cj["estado"] == "reservado":
            datos.canje_web_usar(cj["id"], referencia_puntos(filas))


def soltar(ref: str = "", ids: list[str] | None = None) -> int:
    """Hold liberado / vencido / pago rechazado: lo APARTADO vuelve al jugador
    (solo lo que sigue 'reservado'; lo usado se devuelve con la cancelación)."""
    canjes = datos.canjes_web_de_ref(ref) if ref else []
    if not canjes and ids:
        canjes = datos.canjes_web_por_ids(ids)
    n = 0
    for cj in canjes:
        if cj["estado"] == "reservado" and datos.canje_web_devolver(cj["id"]):
            n += 1
            print(f"[canje-web] devuelto {cj['tipo']} {cj['id']} ref={cj['reserva_ref']}", flush=True)
    return n


def _refs_puntos_app(filas: list[dict], c: dict | None) -> list[str]:
    """Referencias con las que el APK pudo escribir el canje de puntos de esta
    reserva: `<cancha>_<fecha>_<hora>` de cada turno con su fecha REAL (como la
    web y el APK desde oct-2026) y, en turnos de madrugada, también con el día
    BASE (APKs anteriores usaban la fecha de la sesión, no la real)."""
    out: list[str] = []
    for f in filas:
        cid, fecha, hora = str(f.get("cancha_id") or ""), str(f.get("fecha") or ""), str(f.get("hora_inicio") or "")
        if not cid or not fecha or not hora:
            continue
        out.append(f"{cid}_{fecha}_{hora}")
        if c and horarios.slot_es_madrugada(str(c.get("hora_apertura") or ""), str(c.get("hora_cierre") or ""), hora):
            try:
                from datetime import date, timedelta
                out.append(f"{cid}_{(date.fromisoformat(fecha) - timedelta(days=1)).isoformat()}_{hora}")
            except ValueError:
                pass
    return list(dict.fromkeys(out))


# Margen hacia atrás desde que se creó la reserva: el canje del APK se escribe
# DESPUÉS de confirmar, pero el reloj del teléfono puede ir adelantado.
_MARGEN_CANJE_S = 2 * 3600
# Medios en los que el APK nunca canjea puntos (solo pago total en línea).
_SIN_PUNTOS = {"bono", "sena", "efectivo", "manual", "fidelidad", ""}


def _creada_en(filas: list[dict]) -> float | None:
    """Epoch (s) en que se creó la reserva, leído de su id (`jug_<ms>_n`,
    `web_<ms>_n`, `grp_<ms>`). None si no se puede leer."""
    for v in [filas[0].get("grupo_reserva_id"), *[f.get("id") for f in filas]]:
        m = re.search(r"(\d{12,14})", str(v or ""))
        if m:
            return int(m.group(1)) / 1000.0
    return None


def _puntos_app(filas: list[dict], c: dict | None) -> tuple[int, float, list[str], float | None]:
    """Puntos que el APK canjeó en esta reserva (sin libro web): (puntos,
    soles, referencias, desde). 0 si no hubo canje o ya se devolvió."""
    if not filas or str(filas[0].get("medio_pago") or "") in _SIN_PUNTOS or not all(f.get("pagado") for f in filas):
        return 0, 0.0, [], None
    email = str(filas[0].get("usuario") or "").strip().lower()
    refs = _refs_puntos_app(filas, c)
    creada = _creada_en(filas)
    desde = (creada - _MARGEN_CANJE_S) if creada else None
    pts, soles = datos.puntos_canje_neto(email, refs, desde)
    return pts, soles, refs, desde


def devolver_por_cancelacion(ref: str, filas: list[dict], c: dict | None, email: str) -> dict:
    """Cancelación CON devolución: horas de bono a los mismos créditos y
    puntos de vuelta (fila negativa en `pichangol_puntos_canjes`). Vale para
    reservas de la web (libro `pichangol_canjes_web`) y del APK: una reserva
    con bono del app (sin libro) devuelve sus horas a los créditos del local
    y un canje de puntos del app (escrito directo en la tabla de canjes) se
    devuelve con la misma fila negativa. Devuelve {'horas': n, 'puntos': n}."""
    out = {"horas": 0, "puntos": 0}
    canjes = datos.canjes_web_de_ref(ref)
    for cj in canjes:
        prev = datos.canje_web_devolver(cj["id"], "devolucion:" + referencia_puntos(filas))
        if prev:
            if prev["tipo"] == "bono":
                out["horas"] += int(prev["horas"])
            elif prev["estado"] == "usado":
                out["puntos"] += int(prev["puntos"])
    if not any(cj["tipo"] == "bono" for cj in canjes) and c and str(filas[0].get("medio_pago") or "") == "bono":
        club, dueno = local_de(c)
        out["horas"] += datos.bono_devolver_horas(email, club, dueno, len(filas))
    if not any(cj["tipo"] == "puntos" for cj in canjes):
        pts, _s, refs, desde = _puntos_app(filas, c)
        if pts > 0:
            owner = str(filas[0].get("usuario") or email).strip().lower()
            out["puntos"] += datos.puntos_devolver_neto(owner, refs, referencia_puntos(filas), desde)
    return out


def ajustes(filas: list[dict], c: dict | None = None) -> dict:
    """Cómo leer el dinero de una reserva con beneficios: `bono_cubre` = precio
    de los turnos que pagó el bono (la fila guarda el precio de lista, como el
    app), `puntos_desc` = soles descontados por puntos (canje de la web o del
    APK). `pagado_centimos` lo calcula quien llama: total − bono_cubre −
    puntos_desc. [c] (la cancha) afina las referencias de madrugada del APK."""
    if not filas:
        return {"bono_horas": 0, "bono_cubre": 0, "puntos": 0, "puntos_desc": 0}
    ref = (filas[0].get("grupo_reserva_id") or "").strip() or str(filas[0]["id"])
    cj = de_ref(ref)
    es_bono = cj["bono"] is not None or str(filas[0].get("medio_pago") or "") == "bono"
    out = {"bono_horas": 0, "bono_cubre": 0, "puntos": 0, "puntos_desc": 0}
    if es_bono:
        out["bono_horas"] = int(cj["bono"]["horas"]) if cj["bono"] else len(filas)
        out["bono_cubre"] = sum(int(f.get("precio") or 0) for f in filas)
    if cj["puntos"] is not None:
        out["puntos"] = int(cj["puntos"]["puntos"])
        out["puntos_desc"] = int(round(cj["puntos"]["descuento"]))
    else:
        pts, soles, _r, _d = _puntos_app(filas, c)
        if pts > 0:
            out["puntos"] = pts
            out["puntos_desc"] = int(round(soles)) if soles > 0 else DESCUENTO_PUNTOS
    return out


def barrer_vencidos() -> int:
    """Cron: apartados que siguen 'reservado' pasado el hold. Si su reserva
    se confirmó (el pago entró pero algo cortó antes de marcarlo), quedan
    usados; si no, vuelven al jugador. Cubre los holds que se borran sin
    pasar por `/web/liberar` (vencidos en `liberar_holds_vencidos`)."""
    n = 0
    for cj in datos.canjes_web_reservados_viejos(BARRIDO_SEGUNDOS):
        filas = datos.reservas_de(cj.get("reserva_ids") or [])
        if filas and all(str(f.get("estado") or "") == "confirmada" for f in filas):
            datos.canje_web_usar(cj["id"], referencia_puntos(filas))
        elif datos.canje_web_devolver(cj["id"]):
            n += 1
    if n:
        print(f"[canje-web] barrido: {n} apartados devueltos", flush=True)
    return n
