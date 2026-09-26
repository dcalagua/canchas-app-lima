"""POZO DEL EQUIPO ("la vaquita"): la cuota de inscripción de un torneo por
equipos (fútbol) se reparte entre los jugadores del plantel.

Decisión del director (26-sep-2026): la cuota es POR EQUIPO (p. ej. S/ 100);
el organizador define el cupo (mínimo de titulares + suplentes, p. ej. 10);
cada jugador pone su parte AL UNIRSE (100 / 10 = S/ 10, redondeado hacia
arriba a 0.50); el dinero queda RETENIDO en Pichangol en el pozo del equipo;
el equipo queda INSCRITO cuando el pozo cubre la cuota (el último paga solo lo
que falta; quien quiera puede "completar lo que falta"); recién ahí se cobra
la comisión UNA sola vez sobre la cuota del equipo y el neto queda POR
RECIBIR para el organizador (misma cola de liquidaciones que las reservas
online: la torre le transfiere y lo marca pagado). Si el equipo queda fuera
antes de completarse (o antes de que se le pague), cada jugador recupera su
parte en su saldo.

Fuente de verdad del dinero: `stores.pozos_equipo` (snapshot). El JSON del
campeonato (app/web) solo espeja los aportes para mostrarlos.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone

from db.store import stores

PASO_CENTIMOS = 50  # la cuota por jugador se redondea hacia arriba a S/ 0.50


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat()


def clave(campeonato_id: str, equipo_id: str) -> str:
    return f"{campeonato_id}|{equipo_id}"


def cuota_jugador_centimos(cuota_equipo_centimos: int, cupo: int) -> int:
    """Parte de cada jugador: cuota del equipo ÷ cupo, hacia arriba a 0.50.
    Sin cupo (0) → la cuota completa (el capitán la paga entera)."""
    if cuota_equipo_centimos <= 0:
        return 0
    cupo = max(1, int(cupo or 0))
    bruto = cuota_equipo_centimos / cupo
    return int(math.ceil(bruto / PASO_CENTIMOS) * PASO_CENTIMOS)


def _pozo(campeonato_id: str, equipo_id: str) -> dict | None:
    return stores.pozos_equipo.get(clave(campeonato_id, equipo_id))


def _pozo_centimos(p: dict) -> int:
    if p.get("devuelto"):
        return 0
    return sum(int(a.get("centimos") or 0) for a in (p.get("aportes") or {}).values())


def estado(p: dict | None, cuota_equipo_centimos: int = 0, cupo: int = 0) -> dict:
    """Foto del pozo para app/web. Sin registro aún → pozo en cero con la
    cuota que manda el cliente (así la app sabe cuánto pone cada uno)."""
    if p is None:
        cuota = int(cuota_equipo_centimos or 0)
        return {"pozo_centimos": 0, "cuota_equipo_centimos": cuota,
                "cuota_jugador_centimos": cuota_jugador_centimos(cuota, cupo),
                "faltante_centimos": cuota, "completo": cuota <= 0,
                "liquidado": False, "devuelto": False, "aportes": [], "cupo": int(cupo or 0)}
    cuota = int(p.get("cuota_equipo_centimos") or 0)
    pozo = _pozo_centimos(p)
    return {
        "campeonato_id": p.get("campeonato_id"), "equipo_id": p.get("equipo_id"),
        "moneda": p.get("moneda") or "PEN", "cupo": int(p.get("cupo") or 0),
        "pozo_centimos": pozo, "cuota_equipo_centimos": cuota,
        "cuota_jugador_centimos": cuota_jugador_centimos(cuota, int(p.get("cupo") or 0)),
        "faltante_centimos": max(0, cuota - pozo),
        "completo": bool(p.get("liquidado")) or pozo >= cuota > 0,
        "liquidado": bool(p.get("liquidado")), "devuelto": bool(p.get("devuelto")),
        "comision_centimos": int(p.get("comision_centimos") or 0),
        "neto_centimos": int(p.get("neto_centimos") or 0),
        "aportes": [{"email": k, "centimos": int(v.get("centimos") or 0), "en": v.get("en")}
                    for k, v in (p.get("aportes") or {}).items()],
    }


def _liquidar(p: dict, comision_fn) -> None:
    """El pozo cubrió la cuota: comisión UNA vez sobre la cuota del equipo y el
    NETO queda POR RECIBIR para el organizador — la MISMA cola de
    liquidaciones que una reserva online (torre → Liquidaciones, billetera
    "Por recibir", web Ingresos), NO su saldo (decisión del director,
    26-sep-2026: "PCG le debe transferir como a los dueños de cancha").
    `culqi_charge_id` = `pozo:<camp>|<equipo>` es la clave con la que el
    operador la marca pagada. Idempotente."""
    if p.get("liquidado"):
        return
    cuota = int(p["cuota_equipo_centimos"])
    moneda = p.get("moneda") or "PEN"
    comision = min(cuota, int(comision_fn(cuota / 100.0, moneda)))
    neto = max(0, cuota - comision)
    org = (p.get("organizador") or "").strip().lower()
    pago_id = None
    if org:
        pago = stores.registrar_pago(
            tipo="inscripcion_torneo_ingreso", monto_centimos=cuota, moneda=moneda,
            estado="aprobado", dueno_id=org, comision_centimos=comision,
            culqi_charge_id=f"pozo:{clave(p['campeonato_id'], p['equipo_id'])}",
            # "Torneo · Equipo · detalle · fecha": la torre agrupa por el 1.º y
            # el 2.º campo (como Local · Cancha en las reservas).
            concepto=f"🏆 {p.get('campeonato_nombre') or 'Torneo'} · {p.get('equipo_nombre') or 'Equipo'} · inscripción del equipo (pozo completo) · {_ahora()[:10]}")
        pago_id = pago.id
    p.update({"liquidado": True, "liquidado_en": _ahora(),
              "comision_centimos": comision, "neto_centimos": neto,
              "liquidacion_pago_id": pago_id})
    print(f"[pozo] liquidado {p.get('campeonato_id')}/{p.get('equipo_id')}: cuota {cuota} comisión {comision} neto {neto} por recibir → {org}", flush=True)


def _pago_liquidacion(p: dict):
    pid = p.get("liquidacion_pago_id")
    if pid is None:
        return None
    for pg in stores.pagos:
        if pg.id == pid:
            return pg
    return None


def liquidacion_pagada(p: dict) -> bool:
    """¿Pichangol YA le transfirió al organizador el neto de este pozo?"""
    pg = _pago_liquidacion(p)
    return bool(pg and pg.liquidado)


def aportar(*, email: str, campeonato_id: str, equipo_id: str, cuota_equipo_soles: float,
            cupo: int, moneda: str, organizador: str, campeonato_nombre: str,
            equipo_nombre: str, monto_soles: float | None, comision_fn) -> dict:
    """Aporte de un jugador. `monto_soles=None` → su cuota (o lo que falte si es
    menos); con monto → "completar" (tope: lo que falta). Idempotente por
    jugador para la cuota (un segundo toque no cobra de nuevo)."""
    email = (email or "").strip().lower()
    if not email or not campeonato_id or not equipo_id:
        return {"ok": False, "error": "datos_incompletos"}
    cuota_eq = int(round(float(cuota_equipo_soles or 0) * 100))
    if cuota_eq <= 0:
        return {"ok": True, "aporte_centimos": 0, "pozo": estado(None, 0, cupo), "gratis": True}
    k = clave(campeonato_id, equipo_id)
    p = stores.pozos_equipo.get(k)
    if p is None:
        p = {"campeonato_id": campeonato_id, "equipo_id": equipo_id,
             "organizador": (organizador or "").strip().lower(), "moneda": (moneda or "PEN").upper(),
             "cuota_equipo_centimos": cuota_eq, "cupo": int(cupo or 0), "aportes": {},
             "liquidado": False, "devuelto": False, "creado_en": _ahora(),
             "campeonato_nombre": campeonato_nombre or "", "equipo_nombre": equipo_nombre or ""}
        stores.pozos_equipo[k] = p
    else:
        # La cuota/cupo los manda el cliente desde el campeonato vigente: si el
        # organizador la cambió antes de completarse, se respeta la nueva.
        if not p.get("liquidado"):
            p["cuota_equipo_centimos"] = cuota_eq
            p["cupo"] = int(cupo or 0)
        if organizador and not p.get("organizador"):
            p["organizador"] = organizador.strip().lower()
        if p.get("devuelto"):
            # El equipo volvió a la vida (p. ej. lo reinscribieron): pozo nuevo.
            p.update({"aportes": {}, "devuelto": False, "devuelto_en": None})
    st = estado(p)
    if st["completo"]:
        return {"ok": True, "aporte_centimos": 0, "pozo": st, "ya_completo": True}
    ya = p["aportes"].get(email)
    if ya and monto_soles is None:
        return {"ok": True, "aporte_centimos": 0, "pozo": st, "ya_aporto": True}
    faltante = st["faltante_centimos"]
    if monto_soles is None:
        aporte = min(st["cuota_jugador_centimos"], faltante)
    else:
        aporte = min(int(round(float(monto_soles) * 100)), faltante)
    if aporte <= 0:
        return {"ok": False, "error": "monto_invalido", "pozo": st}
    saldo = stores.saldo_centimos(email)
    if saldo < aporte:
        return {"ok": False, "falta_saldo": True, "requerido_centimos": aporte,
                "requerido_soles": aporte / 100.0, "saldo_centimos": saldo, "pozo": st}
    stores.debitar(email, aporte)
    pago = stores.registrar_pago(
        tipo="aporte_equipo", monto_centimos=aporte, moneda=p["moneda"], estado="aprobado",
        dueno_id=email, email=email,
        concepto=f"Mi parte en {p.get('equipo_nombre') or 'el equipo'} · {p.get('campeonato_nombre') or 'torneo'}")
    prev = int((ya or {}).get("centimos") or 0)
    p["aportes"][email] = {"centimos": prev + aporte, "pago_id": pago.id, "en": _ahora()}
    st = estado(p)
    if st["completo"]:
        _liquidar(p, comision_fn)
        st = estado(p)
    return {"ok": True, "aporte_centimos": aporte, "pozo": st,
            "saldo_centimos": stores.saldo_centimos(email),
            "saldo_soles": stores.saldo_centimos(email) / 100.0}


def devolver(*, campeonato_id: str, equipo_id: str, solicitante: str) -> dict:
    """El equipo queda fuera antes de completarse: cada jugador recupera su
    parte en su saldo. Solo el organizador del pozo (o quien lo creó sin
    organizador). Con el neto "por recibir" aún NO pagado se anula la
    liquidación y se devuelve igual; si Pichangol ya se lo transfirió, no hay
    devolución automática (`ya_liquidado`): la resuelve el organizador."""
    p = _pozo(campeonato_id, equipo_id)
    if p is None:
        return {"ok": True, "devueltos": 0, "pozo": estado(None)}
    sol = (solicitante or "").strip().lower()
    org = (p.get("organizador") or "").strip().lower()
    if org and sol != org:
        return {"ok": False, "error": "solo_organizador"}
    if p.get("devuelto"):
        return {"ok": True, "devueltos": 0, "pozo": estado(p)}
    if p.get("liquidado"):
        # Ya está "por recibir": si Pichangol AÚN NO se lo transfirió al
        # organizador, se ANULA esa liquidación y los jugadores recuperan su
        # parte; si ya se pagó, la devolución queda de lado del organizador.
        if liquidacion_pagada(p):
            return {"ok": False, "error": "ya_liquidado", "pozo": estado(p)}
        pg = _pago_liquidacion(p)
        if pg is not None:
            pg.estado = "anulado"
        p.update({"liquidado": False, "anulado_en": _ahora()})
    n = 0
    for email, a in list((p.get("aportes") or {}).items()):
        c = int(a.get("centimos") or 0)
        if c <= 0:
            continue
        stores.acreditar(email, c)
        stores.registrar_pago(
            tipo="aporte_equipo_devolucion", monto_centimos=c, moneda=p.get("moneda") or "PEN",
            estado="aprobado", dueno_id=email, email=email,
            concepto=f"Devolución de mi parte · {p.get('equipo_nombre') or 'equipo'} · {p.get('campeonato_nombre') or 'torneo'}")
        n += 1
    p.update({"devuelto": True, "devuelto_en": _ahora()})
    print(f"[pozo] devuelto {campeonato_id}/{equipo_id}: {n} jugadores", flush=True)
    return {"ok": True, "devueltos": n, "pozo": estado(p)}


def de_campeonato(campeonato_id: str) -> list[dict]:
    return [estado(p) for k, p in stores.pozos_equipo.items() if k.startswith(f"{campeonato_id}|")]


def de_equipo(campeonato_id: str, equipo_id: str, cuota_equipo_soles: float = 0, cupo: int = 0) -> dict:
    return estado(_pozo(campeonato_id, equipo_id), int(round(float(cuota_equipo_soles or 0) * 100)), cupo)
