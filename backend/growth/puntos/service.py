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


def _saldo_disponible(usuario_id: str) -> int:
    liberados = sum(m.puntos for m in stores.movimientos
                    if m.usuario_id == usuario_id and m.estado == "liberado")
    usados = sum(cj.puntos_usados for cj in stores.canjes
                 if cj.usuario_id == usuario_id and cj.estado != "anulado")
    return liberados - usados


def saldo(usuario_id: str) -> dict:
    pendientes = sum(m.puntos for m in stores.movimientos
                     if m.usuario_id == usuario_id and m.estado == "pendiente")
    return {
        "usuario_id": usuario_id,
        "disponible": _saldo_disponible(usuario_id),
        "pendiente": pendientes,
    }


def movimientos(usuario_id: str) -> list[dict]:
    return [como_dict(m) for m in stores.movimientos
            if m.usuario_id == usuario_id]


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
