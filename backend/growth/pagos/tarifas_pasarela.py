"""Tarifa de la PASARELA de pagos (lo que Culqi / PayPhone / Libélula le
cobran a Pichangol por cada cobro), configurable desde la torre.

Pedido del director (26-sep-2026, tras el primer cobro live de S/ 15:
"¿cuánto me descuenta Culqi y cuál es mi comisión?"): la torre solo conocía
la comisión de Pichangol y el neto del dueño; ahora también estima el costo
de la pasarela y muestra el MARGEN real (comisión − pasarela) por cobro.

- Es una ESTIMACIÓN contable con la tarifa contratada (porcentaje + monto
  fijo + IGV/IVA sobre la tarifa). La pasarela liquida a su ritmo y con sus
  redondeos; el número exacto está en su panel. No mueve plata.
- Una tarifa por pasarela (= por país/moneda: PEN → Culqi, USD → PayPhone,
  BOB → Libélula) y, en Culqi, distinta para tarjeta y Yape.
- Solo aplica a cobros que PASARON por la pasarela (reserva online, venta del
  marketplace, matrícula web…). Lo pagado con SALDO (bodega, torneo) ya pagó
  la pasarela al recargar → costo 0 en esa fila.
- Valores por defecto = la tarifa publicada de Culqi en Perú (3.44 % +
  S/ 0.30 + IGV 18 %) como referencia; PayPhone y Libélula arrancan en 0
  (= "sin configurar": no se descuenta nada hasta que el director ponga la
  suya). Se guardan en `stores.config` (claves `tarifa_<pasarela>_*`).
"""
from __future__ import annotations

from db.store import stores

# pasarela → moneda en la que cobra y medios con tarifa propia.
PASARELAS: dict[str, dict] = {
    "culqi": {"nombre": "Culqi", "pais": "PE", "moneda": "PEN", "simbolo": "S/", "medios": ["tarjeta", "yape"],
              "impuesto": "IGV", "nota": "Tarifa publicada de Culqi Perú: 3.44 % + S/ 0.30 + IGV por cobro (revisa la tuya en el panel de Culqi → Comisiones)."},
    "payphone": {"nombre": "PayPhone", "pais": "EC", "moneda": "USD", "simbolo": "$", "medios": ["tarjeta"],
                 "impuesto": "IVA", "nota": "PayPhone Ecuador cobra un porcentaje + IVA según el plan contratado; ponlo tal cual figura en tu contrato."},
    "libelula": {"nombre": "Libélula", "pais": "BO", "moneda": "BOB", "simbolo": "Bs", "medios": ["tarjeta"],
                 "impuesto": "IVA", "nota": "Libélula Bolivia: porcentaje + monto fijo según contrato."},
}
MEDIO_NOMBRE = {"tarjeta": "Tarjeta", "yape": "Yape"}
_POR_MONEDA = {v["moneda"]: k for k, v in PASARELAS.items()}

# Defaults (strings, como todo `stores.config`). Culqi = tarifa publicada de
# referencia; las otras en 0 hasta que el director las configure.
DEFAULTS: dict[str, str] = {
    "tarifa_culqi_tarjeta_pct": "3.44", "tarifa_culqi_tarjeta_fijo": "0.30",
    "tarifa_culqi_yape_pct": "3.44", "tarifa_culqi_yape_fijo": "0.30",
    "tarifa_culqi_impuesto_pct": "18",
    "tarifa_payphone_tarjeta_pct": "0", "tarifa_payphone_tarjeta_fijo": "0", "tarifa_payphone_impuesto_pct": "0",
    "tarifa_libelula_tarjeta_pct": "0", "tarifa_libelula_tarjeta_fijo": "0", "tarifa_libelula_impuesto_pct": "0",
}

# Tipos de pago que pasaron por la pasarela (el jugador pagó con tarjeta/Yape
# en ese momento). Los demás (bodega, torneo) se pagaron con saldo.
TIPOS_CON_PASARELA = {"liquidacion_online", "liquidacion_full", "venta_producto", "matricula_online", "cobro_web", "recarga", "fee_reserva"}


def _f(clave: str) -> float:
    try:
        return max(0.0, float(stores.config.get(clave, DEFAULTS.get(clave, "0")) or 0))
    except (TypeError, ValueError):
        return 0.0


def leer() -> dict:
    """Tarifas vigentes por pasarela y medio (para la torre y el cálculo)."""
    out = {}
    for k, meta in PASARELAS.items():
        medios = {m: {"pct": _f(f"tarifa_{k}_{m}_pct"), "fijo": _f(f"tarifa_{k}_{m}_fijo")} for m in meta["medios"]}
        out[k] = dict(meta, medios=medios, impuesto_pct=_f(f"tarifa_{k}_impuesto_pct"),
                      configurada=any(v["pct"] > 0 or v["fijo"] > 0 for v in medios.values()))
    return out


def guardar(valores: dict) -> tuple[bool, str]:
    """TORRE: guarda {pasarela: {medios: {medio: {pct, fijo}}, impuesto_pct}}.
    Valida rangos (0-20 % de tarifa, 0-10 de fijo, 0-30 % de impuesto)."""
    nuevos: dict[str, str] = {}
    for k, meta in PASARELAS.items():
        v = valores.get(k) if isinstance(valores, dict) else None
        if not isinstance(v, dict):
            continue
        for m in meta["medios"]:
            mv = (v.get("medios") or {}).get(m) if isinstance(v.get("medios"), dict) else v.get(m)
            if not isinstance(mv, dict):
                continue
            try:
                pct, fijo = float(mv.get("pct", 0) or 0), float(mv.get("fijo", 0) or 0)
            except (TypeError, ValueError):
                return False, f"{meta['nombre']} · {MEDIO_NAME(m)}: valores inválidos."
            if not (0 <= pct <= 20) or not (0 <= fijo <= 10):
                return False, f"{meta['nombre']} · {MEDIO_NAME(m)}: el porcentaje va de 0 a 20 y el fijo de 0 a 10."
            nuevos[f"tarifa_{k}_{m}_pct"] = f"{pct:g}"
            nuevos[f"tarifa_{k}_{m}_fijo"] = f"{fijo:g}"
        if "impuesto_pct" in v:
            try:
                imp = float(v.get("impuesto_pct") or 0)
            except (TypeError, ValueError):
                return False, f"{meta['nombre']}: impuesto inválido."
            if not (0 <= imp <= 30):
                return False, f"{meta['nombre']}: el impuesto va de 0 a 30 %."
            nuevos[f"tarifa_{k}_impuesto_pct"] = f"{imp:g}"
    if not nuevos:
        return False, "Nada que guardar."
    stores.config.update(nuevos)
    return True, ""


def MEDIO_NAME(m: str) -> str:
    return MEDIO_NOMBRE.get(m, m)


def pasarela_de(moneda_iso: str) -> str:
    return _POR_MONEDA.get((moneda_iso or "PEN").upper(), "culqi")


def costo_centimos(monto_centimos: int, moneda_iso: str = "PEN", medio: str | None = None, tipo: str | None = None) -> int:
    """Costo estimado de la pasarela por UN cobro: (monto × % + fijo) × (1 +
    impuesto). 0 si el tipo no pasó por la pasarela (pagado con saldo) o si la
    pasarela no está configurada. `medio` 'yape' usa su tarifa; cualquier
    otro (tarjeta, seña, vacío) la de tarjeta."""
    if monto_centimos <= 0:
        return 0
    if tipo and tipo not in TIPOS_CON_PASARELA:
        return 0
    k = pasarela_de(moneda_iso)
    t = leer()[k]
    m = "yape" if (medio or "").strip().lower() == "yape" and "yape" in t["medios"] else "tarjeta"
    tar = t["medios"].get(m) or {"pct": 0.0, "fijo": 0.0}
    if tar["pct"] <= 0 and tar["fijo"] <= 0:
        return 0
    base = monto_centimos * tar["pct"] / 100.0 + tar["fijo"] * 100.0
    return int(round(base * (1 + t["impuesto_pct"] / 100.0)))


def desglose(monto_centimos: int, comision_centimos: int, moneda_iso: str = "PEN", medio: str | None = None, tipo: str | None = None) -> dict:
    """Bruto → pasarela → comisión Pichangol → margen (comisión − pasarela)
    → neto del dueño. Para las filas de la torre y el simulador."""
    pas = costo_centimos(monto_centimos, moneda_iso, medio, tipo)
    return {"bruto_centimos": monto_centimos, "pasarela_centimos": pas, "comision_centimos": comision_centimos,
            "margen_centimos": comision_centimos - pas, "neto_centimos": monto_centimos - comision_centimos,
            "pasarela": pasarela_de(moneda_iso), "medio": "yape" if (medio or "").lower() == "yape" else "tarjeta"}
