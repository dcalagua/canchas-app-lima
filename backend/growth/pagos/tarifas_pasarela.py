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
    "nuvei": {"nombre": "Nuvei", "pais": "EC", "moneda": "USD", "simbolo": "$", "medios": ["tarjeta"],
              "impuesto": "IVA", "nota": "Nuvei Ecuador (ex-Paymentez) cobra un porcentaje + fijo + IVA según el contrato; ponlo tal cual figura en el tuyo."},
    "payphone": {"nombre": "PayPhone", "pais": "EC", "moneda": "USD", "simbolo": "$", "medios": ["tarjeta"],
                 "impuesto": "IVA", "nota": "PayPhone Ecuador cobra un porcentaje + IVA según el plan contratado; ponlo tal cual figura en tu contrato."},
    "libelula": {"nombre": "Libélula", "pais": "BO", "moneda": "BOB", "simbolo": "Bs", "medios": ["tarjeta"],
                 "impuesto": "IVA", "nota": "Libélula Bolivia: porcentaje + monto fijo según contrato."},
}
MEDIO_NOMBRE = {"tarjeta": "Tarjeta", "yape": "Yape"}
# USD lo cobran Nuvei o PayPhone según `PASARELA_EC` (ver pagos/pasarela_ec);
# el resto de monedas tiene una sola pasarela.
_POR_MONEDA = {v["moneda"]: k for k, v in PASARELAS.items() if k not in ("nuvei", "payphone")}

# Defaults (strings, como todo `stores.config`). Culqi = tarifa publicada de
# referencia; las otras en 0 hasta que el director las configure.
# Tarjeta: lo OBSERVADO en el primer cobro live (panel de Culqi, 26-sep-2026,
# S/ 15 → comisión emisor 0.38 + comisión Culqi 0.83 = 1.21 antes de IGV ≈
# 6.05 % + S/ 0.30). Culqi desglosa en "emisor" (varía por tarjeta) + "Culqi";
# aquí se modela como un solo % + fijo. La cifra exacta por cobro la trae
# `sincerar()` de la API; esta tarifa es solo para lo que aún no se leyó.
DEFAULTS: dict[str, str] = {
    "tarifa_culqi_tarjeta_pct": "6.05", "tarifa_culqi_tarjeta_fijo": "0.30",
    "tarifa_culqi_yape_pct": "3.44", "tarifa_culqi_yape_fijo": "0.30",
    "tarifa_culqi_impuesto_pct": "18",
    "tarifa_nuvei_tarjeta_pct": "0", "tarifa_nuvei_tarjeta_fijo": "0", "tarifa_nuvei_impuesto_pct": "0",
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
    m = (moneda_iso or "PEN").upper()
    if m == "USD":
        import os
        return "payphone" if (os.getenv("PASARELA_EC") or "nuvei").strip().lower() == "payphone" else "nuvei"
    return _POR_MONEDA.get(m, "culqi")


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


# ── COMISIÓN REAL (sincerada con Culqi) ──────────────────────────────────────
# El objeto del cargo trae `total_fee` / `net_amount` cuando Culqi termina de
# calcular su comisión (~12 h después del pago, según su panel). Se guarda en
# la fila del CARGO (`culqi_charge_id` = `chr_…`) y las filas contables que
# nacen de ese pago (liquidación, matrícula, venta) la leen por `cargo_id`.

TIPOS_CARGO = {"reserva", "academia", "cobro", "cobro_web", "recarga", "venta_producto", "matricula_online", "suscripcion", "fee_reserva"}
_ultimo_intento: dict[str, float] = {}


def es_cargo(p) -> bool:
    return str(p.culqi_charge_id or "").startswith("chr_")


def cargo_de(p):
    """Fila del CARGO de Culqi de la que salió esta liquidación/matrícula/venta
    (o la misma fila si ya es el cargo). Sin enlace explícito (`cargo_id`,
    APKs viejos) se infiere: un único cargo `chr_` del mismo monto, misma
    moneda y creado ±20 min alrededor, aún no ligado a otra fila; si calza,
    se guarda el enlace para no volver a buscar."""
    if es_cargo(p):
        return p
    if p.cargo_id:
        c = stores.pago_por_charge(p.cargo_id)
        if c is not None:
            return c
    if p.tipo not in ("liquidacion_online", "liquidacion_full", "matricula_online", "venta_producto"):
        return None
    usados = {q.cargo_id for q in stores.pagos if q.cargo_id}
    cands = []
    for q in stores.pagos:
        if q is p or not es_cargo(q) or q.tipo not in TIPOS_CARGO or q.moneda != p.moneda:
            continue
        if q.monto_centimos != p.monto_centimos or q.culqi_charge_id in usados:
            continue
        try:
            if abs((q.creado_en - p.creado_en).total_seconds()) > 20 * 60:
                continue
        except TypeError:
            continue
        cands.append(q)
    if len(cands) == 1:
        p.cargo_id = cands[0].culqi_charge_id
        return cands[0]
    return None


def costo_para(p) -> tuple[int, str]:
    """(céntimos, fuente) del costo de la pasarela para una fila contable:
    'real' (leído de Culqi), 'estimado' (tarifa configurada), 'saldo' (0: se
    pagó con saldo, la pasarela ya se pagó al recargar)."""
    if p.tipo and p.tipo not in TIPOS_CON_PASARELA:
        return 0, "saldo"
    c = cargo_de(p)
    if c is not None and c.pasarela_centimos is not None:
        return int(c.pasarela_centimos), "real"
    from pagos.router import moneda_iso  # import tardío: router importa este módulo
    return costo_centimos(p.monto_centimos, moneda_iso(p.moneda), p.medio, p.tipo), "estimado"


def sincerar(max_consultas: int = 40, dias: int = 15, reintento_horas: float = 4.0) -> dict:
    """Lee de Culqi la comisión REAL de los cargos recientes que aún no la
    tienen (`pasarela_centimos` None) y la guarda. Lo corre el cron cada hora
    y el botón "Sincerar con Culqi" de la torre. Fail-safe: si Culqi no está
    configurado o falla, no toca nada. Devuelve un resumen."""
    from datetime import datetime, timedelta, timezone
    import time as _t
    from pagos import culqi
    res = {"consultados": 0, "actualizados": 0, "pendientes": 0, "errores": 0, "disponible": culqi.disponible()}
    if not res["disponible"]:
        return res
    ahora = datetime.now(timezone.utc)
    corte = ahora - timedelta(days=dias)
    vistos: set[str] = set()
    for p in sorted(stores.pagos, key=lambda x: x.creado_en, reverse=True):
        if res["consultados"] >= max_consultas:
            break
        if not es_cargo(p) or p.pasarela_centimos is not None or p.moneda not in ("PEN", "S/"):
            continue
        cid = str(p.culqi_charge_id)
        if cid in vistos:
            continue
        try:
            if p.creado_en.replace(tzinfo=p.creado_en.tzinfo or timezone.utc) < corte:
                continue
        except Exception:  # noqa: BLE001
            pass
        if _t.time() - _ultimo_intento.get(cid, 0) < reintento_horas * 3600:
            continue
        vistos.add(cid)
        _ultimo_intento[cid] = _t.time()
        res["consultados"] += 1
        r = culqi.comision_real(cid)
        if not r.get("ok"):
            res["errores"] += 1
            continue
        if not r.get("conocida"):
            res["pendientes"] += 1
            continue
        # Todas las filas con ese cargo (p. ej. cobro_web + matricula_online del mismo chr_).
        for q in stores.pagos:
            if q.culqi_charge_id == cid:
                q.pasarela_centimos = int(r["pasarela_centimos"])
                q.pasarela_en = ahora
        res["actualizados"] += 1
        print(f"[tarifa] {cid}: Culqi cobró {r['pasarela_centimos']/100:.2f} de {r['monto_centimos']/100:.2f} "
              f"(neto {r['neto_centimos']/100:.2f}) detalle={r.get('detalle')}", flush=True)
    stores.config["tarifa_sincerado_en"] = ahora.isoformat()
    if res["actualizados"]:
        try:
            from db import pg
            pg.persistir_en_segundo_plano(stores)
        except Exception:  # noqa: BLE001
            pass
    return res


def observado() -> dict:
    """Lo que Culqi cobró DE VERDAD en los cargos ya sincerados, por medio
    (tarjeta / yape): n, bruto, pasarela, % efectivo y el % que habría que
    poner en la tarifa (dado el fijo y el impuesto configurados) para que la
    estimación calce con la realidad. Para el botón "Usar la tarifa observada"."""
    t = leer()["culqi"]
    imp = 1 + t["impuesto_pct"] / 100.0
    acc: dict[str, dict] = {}
    for p in stores.pagos:
        if not es_cargo(p) or p.pasarela_centimos is None or p.moneda not in ("PEN", "S/") or p.monto_centimos <= 0:
            continue
        m = "yape" if (p.medio or "").lower() == "yape" else "tarjeta"
        a = acc.setdefault(m, {"n": 0, "bruto": 0, "pasarela": 0, "pcts": [], "ids": set()})
        if p.culqi_charge_id in a["ids"]:
            continue
        a["ids"].add(p.culqi_charge_id)
        a["n"] += 1
        a["bruto"] += p.monto_centimos
        a["pasarela"] += p.pasarela_centimos
        fijo = t["medios"].get(m, {}).get("fijo", 0.0) * 100
        a["pcts"].append(max(0.0, (p.pasarela_centimos / imp - fijo) / p.monto_centimos * 100))
    out = {}
    for m, a in acc.items():
        out[m] = {"n": a["n"], "bruto_soles": a["bruto"] / 100.0, "pasarela_soles": a["pasarela"] / 100.0,
                  "efectivo_pct": round(a["pasarela"] / a["bruto"] * 100, 2) if a["bruto"] else 0.0,
                  "pct_sugerido": round(sum(a["pcts"]) / len(a["pcts"]), 2) if a["pcts"] else 0.0}
    return {"medios": out, "sincerado_en": stores.config.get("tarifa_sincerado_en", "")}
