"""Lógica de puntos y premios.

Anti-fraude: 'traer_cancha' e 'invitar_jugador' (y 'pedir_cancha') nacen en
estado PENDIENTE. Solo se LIBERAN cuando se cumple la condición real:
  - traer_cancha  -> la cancha está VERIFICADA **y** tiene su PRIMERA RESERVA.
  - pedir_cancha  -> la solicitud se convirtió en cancha registrada y verificada.
  - invitar_jugador -> el jugador invitado hizo su primera reserva.

Los puntos PENDIENTES no son canjeables; solo cuentan los LIBERADOS.
Reglas/valores: SIEMPRE desde config_incentivos (nada hardcodeado).
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from db.store import (PremioCanje, PuntosMovimiento, ahora, como_dict, mes_de,
                      stores)

# Mapea cada acción a la clave de config con sus puntos.
_PUNTOS_POR_ACCION = {
    "traer_cancha": "puntos_traer_cancha",
    "invitar_jugador": "puntos_invitar_jugador",
    "pedir_cancha": "puntos_pedir_cancha",
}


def _puntos_de(accion: str) -> int:
    clave = _PUNTOS_POR_ACCION.get(accion)
    return stores.cfg_int(clave) if clave else 0


def acreditar(usuario_id: str, accion: str, ref_tipo: str | None = None,
              ref_id: str | None = None, idem_key: str | None = None) -> dict:
    """Crea un movimiento PENDIENTE de puntos según la config. Idempotente."""
    cacheado = stores.idem_get("acreditar", idem_key)
    if cacheado is not None:
        return cacheado

    puntos = _puntos_de(accion)
    mov = PuntosMovimiento(
        id=stores.next_id("movimiento"), usuario_id=usuario_id, accion=accion,
        puntos=puntos, estado="pendiente", ref_tipo=ref_tipo, ref_id=ref_id,
        creado_en=ahora())
    stores.movimientos.append(mov)
    return stores.idem_set("acreditar", idem_key, como_dict(mov))


def _liberar(mov: PuntosMovimiento) -> bool:
    if mov.estado == "pendiente":
        mov.estado = "liberado"
        mov.liberado_en = ahora()
        return True
    return False


def liberar_por_ref(ref_tipo: str, ref_id: str,
                    accion: str | None = None) -> int:
    """Libera los movimientos PENDIENTES que apuntan a (ref_tipo, ref_id).
    Idempotente: si ya estaban liberados, no hace nada. Devuelve cuántos liberó."""
    n = 0
    for mov in stores.movimientos:
        if (mov.ref_tipo == ref_tipo and str(mov.ref_id) == str(ref_id)
                and (accion is None or mov.accion == accion)):
            if _liberar(mov):
                n += 1
    return n


def intentar_liberar_traer_cancha(cancha_id: str) -> int:
    """Libera 'traer_cancha' SOLO si la cancha está verificada Y tuvo su primera
    reserva real. Esta es la barrera anti-fraude central."""
    c = stores.cancha(cancha_id)
    if not (c.verificada and c.primera_reserva):
        return 0
    return liberar_por_ref("cancha", cancha_id, accion="traer_cancha")


def _caducidad_dias() -> int:
    return stores.cfg_int("fidelidad_caducidad_dias")


def _fecha_lote(m: PuntosMovimiento):
    return m.liberado_en or m.creado_en


def _vencido(m: PuntosMovimiento) -> bool:
    dias = _caducidad_dias()
    if dias <= 0:
        return False
    return (ahora() - _fecha_lote(m)).days >= dias


def _lotes_restantes(usuario_id: str) -> list[tuple[PuntosMovimiento, int]]:
    """Lotes LIBERADOS con su restante tras consumir los canjes en FIFO (los
    canjes gastan primero los puntos más viejos — así la caducidad castiga
    solo lo que de verdad quedó sin usar)."""
    lotes = sorted(
        [m for m in stores.movimientos
         if m.usuario_id == usuario_id and m.estado == "liberado"],
        key=_fecha_lote)
    usados = sum(cj.puntos_usados for cj in stores.canjes
                 if cj.usuario_id == usuario_id and cj.estado != "anulado")
    out: list[tuple[PuntosMovimiento, int]] = []
    for m in lotes:
        consumo = min(m.puntos, usados)
        usados -= consumo
        restante = m.puntos - consumo
        if restante > 0:
            out.append((m, restante))
    return out


def _saldo_disponible(usuario_id: str) -> int:
    """Puntos canjeables: liberados, no consumidos y NO vencidos."""
    return sum(r for m, r in _lotes_restantes(usuario_id) if not _vencido(m))


def saldo(usuario_id: str) -> dict:
    pendientes = sum(m.puntos for m in stores.movimientos
                     if m.usuario_id == usuario_id and m.estado == "pendiente")
    vivos = [(m, r) for m, r in _lotes_restantes(usuario_id)
             if not _vencido(m)]
    dias = _caducidad_dias()
    por_vencer = 0
    vence_proximo = None
    if dias > 0:
        for m, r in vivos:
            vence = _fecha_lote(m) + timedelta(days=dias)
            if vence_proximo is None or vence < vence_proximo:
                vence_proximo = vence
            if (vence - ahora()).days <= 30:
                por_vencer += r
    try:
        valor_100 = float(stores.cfg("fidelidad_valor_100_puntos"))
    except (TypeError, ValueError):
        valor_100 = 3.0
    return {
        "usuario_id": usuario_id,
        "disponible": sum(r for _, r in vivos),
        "pendiente": pendientes,
        "por_vencer_30d": por_vencer,
        "vence_proximo":
            vence_proximo.isoformat() if vence_proximo else None,
        "valor_100_puntos": valor_100,
    }


def movimientos(usuario_id: str) -> list[dict]:
    return [como_dict(m) for m in stores.movimientos
            if m.usuario_id == usuario_id]


# --- FIDELIDAD del jugador: puntos por reservas PAGADAS ----------------------
def acreditar_reserva(usuario_id: str, monto: float, moneda: str = "S/",
                      reserva_id: str = "") -> dict:
    """Acredita puntos por una reserva efectivamente PAGADA (online al pagar;
    efectivo cuando el dueño la marca pagada). LIBERADOS al instante (el pago
    ya está verificado). Idempotente por reserva: una reserva = un lote.
    Regla (torre): 1 punto por S/ 1 o Bs 1; $1 (Ecuador) = 3 puntos."""
    usuario_id = (usuario_id or "").strip().lower()
    ref = str(reserva_id or "").strip()
    if not usuario_id or not ref or monto <= 0:
        return {"ok": False, "error": "datos_invalidos"}
    for m in stores.movimientos:
        if (m.accion == "reserva_pagada" and m.ref_tipo == "reserva"
                and str(m.ref_id) == ref):
            return {"ok": True, "duplicada": True, "puntos": m.puntos,
                    "saldo_disponible": _saldo_disponible(usuario_id)}
    es_usd = str(moneda or "").strip().upper() in ("$", "USD", "US$")
    factor = stores.cfg_int(
        "fidelidad_puntos_por_usd" if es_usd else "fidelidad_puntos_por_unidad")
    puntos = int(round(monto * max(0, factor)))
    if puntos <= 0:
        return {"ok": False, "error": "monto_muy_chico"}
    mov = PuntosMovimiento(
        id=stores.next_id("movimiento"), usuario_id=usuario_id,
        accion="reserva_pagada", puntos=puntos, estado="liberado",
        ref_tipo="reserva", ref_id=ref, creado_en=ahora(),
        liberado_en=ahora())
    stores.movimientos.append(mov)
    return {"ok": True, "duplicada": False, "puntos": puntos,
            "saldo_disponible": _saldo_disponible(usuario_id)}


def _financiado_pichangol_mes(mes: str) -> float:
    return sum(cj.valor_soles for cj in stores.canjes
               if cj.fuente_financiamiento == "pichangol"
               and cj.estado != "anulado" and mes_de(cj.creado_en) == mes)


def canjear(usuario_id: str, puntos_usados: int, tipo_premio: str,
            fuente_financiamiento: str = "pichangol",
            idem_key: str | None = None) -> dict:
    """Canjea puntos por un VALE aplicable a una reserva. Idempotente.

    Si Pichangol llegó al tope mensual, se bloquean los canjes financiados por
    Pichangol; los cofinanciados por el dueño ('dueno') siguen permitidos.
    """
    cacheado = stores.idem_get("canjear", idem_key)
    if cacheado is not None:
        return cacheado

    if puntos_usados <= 0:
        return {"ok": False, "error": "puntos_usados debe ser > 0"}
    if fuente_financiamiento not in ("pichangol", "dueno"):
        return {"ok": False, "error": "fuente_financiamiento inválida"}
    if _saldo_disponible(usuario_id) < puntos_usados:
        return {"ok": False, "error": "saldo insuficiente"}

    # Regla vigente (fidelidad, ago-2026): 100 puntos = 3 unidades de moneda
    # local (editable en torre). Fallback a la equivalencia histórica.
    try:
        valor_100 = float(stores.cfg("fidelidad_valor_100_puntos"))
    except (TypeError, ValueError):
        valor_100 = 0.0
    if valor_100 > 0:
        valor_soles = round(puntos_usados * valor_100 / 100, 2)
    else:
        equivalencia = max(1, stores.cfg_int("equivalencia_puntos_por_sol"))
        valor_soles = round(puntos_usados / equivalencia, 2)

    if fuente_financiamiento == "pichangol":
        tope = stores.cfg_int("tope_mensual_premios_pichangol_soles")
        usado = _financiado_pichangol_mes(mes_de(ahora()))
        if usado + valor_soles > tope:
            return {
                "ok": False, "bloqueado": True,
                "error": "tope_mensual_pichangol_alcanzado",
                "sugerencia": "usar fuente_financiamiento='dueno' (cofinanciado)",
                "tope": tope, "usado_mes": usado,
            }

    canje = PremioCanje(
        id=stores.next_id("canje"), usuario_id=usuario_id,
        puntos_usados=puntos_usados, tipo_premio=tipo_premio,
        vale_id=f"VALE-{uuid.uuid4().hex[:10].upper()}",
        fuente_financiamiento=fuente_financiamiento, estado="emitido",
        valor_soles=valor_soles, creado_en=ahora())
    stores.canjes.append(canje)
    resp = {"ok": True, **como_dict(canje),
            "saldo_disponible": _saldo_disponible(usuario_id)}
    return stores.idem_set("canjear", idem_key, resp)


# --- ganchos de eventos reales (disparan liberaciones) -----------------------
def evento_primera_reserva(cancha_id: str) -> dict:
    """La cancha tuvo su primera reserva real → intenta liberar 'traer_cancha'."""
    c = stores.cancha(cancha_id)
    c.primera_reserva = True
    liberados = intentar_liberar_traer_cancha(cancha_id)
    return {"cancha_id": cancha_id, "primera_reserva": True,
            "traer_cancha_liberados": liberados}


def cuenta_solicitudes_mes(usuario_id: str, mes: str) -> int:
    return sum(1 for m in stores.movimientos
               if m.usuario_id == usuario_id and m.accion == "pedir_cancha"
               and mes_de(m.creado_en) == mes)
