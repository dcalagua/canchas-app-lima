"""MODELO DE NEGOCIO de las RESERVAS de cancha, elegible en la torre.

Decisión del director (2-oct-2026, hoja «Cálculo PCG»): convivir con DOS
modelos y que el operador elija con cuál trabaja, sin borrar el actual.

- **Modelo 1 (el de siempre):** el dueño paga la comisión de Pichangol (5 %
  con mínimo por moneda, `pagos.router.comision_centimos`) y, si está
  encendido, el jugador paga el "Cargo por servicio" (`cargo_servicio.py`).
  Pichangol absorbe la pasarela.
- **Modelo 2 (reparto de la pasarela):** el costo de cobrar en línea (banco +
  pasarela, cada uno con su IGV/IVA) se REPARTE entre jugador y dueño (50/50
  por defecto) y encima Pichangol cobra un % al jugador y un % al dueño que
  pone el operador. Todo lo demás es calculado:

      pasarela   = P × (banco % + pasarela %) × (1 + IGV %)
      base dueño   = P − pasarela × (1 − reparto)
      base jugador = P + pasarela × reparto
      dueño recibe = base dueño × (1 − comisión dueño %)
      jugador paga = base jugador × (1 + comisión jugador %)
      ingreso PCG  = base dueño × comisión dueño % + base jugador × comisión jugador %

  Con P = S/ 90, banco 2.5 %, pasarela 5.5 %, IGV 18 %, reparto 50 %, dueño
  0 % y jugador 1.2 % (la hoja del director): pasarela S/ 8.50, dueño recibe
  S/ 85.75, jugador paga S/ 95.38, ingreso PCG S/ 1.13.

  `sobre` = "precio" (como la hoja: la pasarela se calcula sobre el precio) o
  "cobrado" (sobre lo que de verdad cobra la pasarela: el total del jugador).
  Con "precio" la pasarela real cobra un poco más de lo repartido y la
  diferencia sale del ingreso de Pichangol (el simulador lo muestra).

Solo aplica a RESERVAS. Academias, marketplace y torneos siguen como están.
El modelo se lee en cada cobro: la cotización del checkout (APK y web vía
`pagos.router.cotizacion_para`), la liquidación al dueño
(`post_liquidacion_online`, que CONGELA lo calculado en el pago con
`modelo_cobro = "m2"`) y la comisión de las reservas en efectivo.
"""
from __future__ import annotations

import math

from db.store import stores

MODELOS = ("1", "2")
MONEDAS = ("PEN", "USD", "BOB")
_SIMBOLO = {"PEN": "S/", "USD": "$", "BOB": "Bs"}
_ISO = {"S/": "PEN", "PEN": "PEN", "$": "USD", "USD": "USD", "BS": "BOB", "BOB": "BOB"}

# Defaults = la hoja del director para soles. Ecuador (IVA 15 %) y Bolivia
# (IVA 13 %) arrancan con las mismas tasas de banco/pasarela: hay que
# ponerles las tarifas reales de PayPhone y Libélula en la torre.
PARAMS_DEFAULT: dict[str, dict[str, str]] = {
    "PEN": {"cliente_pct": "1.2", "dueno_pct": "0", "banco_pct": "2.5", "pasarela_pct": "5.5",
            "igv_pct": "18", "reparto_cliente_pct": "50", "sobre": "precio"},
    "USD": {"cliente_pct": "1.2", "dueno_pct": "0", "banco_pct": "2.5", "pasarela_pct": "5.5",
            "igv_pct": "15", "reparto_cliente_pct": "50", "sobre": "precio"},
    "BOB": {"cliente_pct": "1.2", "dueno_pct": "0", "banco_pct": "2.5", "pasarela_pct": "5.5",
            "igv_pct": "13", "reparto_cliente_pct": "50", "sobre": "precio"},
}
CLAVES_DEFAULT: dict[str, str] = {
    "modelo_reservas": "1",
    **{f"m2_{m}_{k}": v for m, d in PARAMS_DEFAULT.items() for k, v in d.items()},
}
# Topes de validación (en %).
_TOPES = {"cliente_pct": 30.0, "dueno_pct": 30.0, "banco_pct": 15.0, "pasarela_pct": 15.0,
          "igv_pct": 30.0, "reparto_cliente_pct": 100.0}
ETIQUETAS = {
    "cliente_pct": "Comisión Pichangol al jugador",
    "dueno_pct": "Comisión Pichangol al dueño",
    "banco_pct": "Comisión del banco",
    "pasarela_pct": "Comisión de la pasarela",
    "igv_pct": "IGV / IVA sobre las comisiones",
    "reparto_cliente_pct": "Parte de la pasarela que paga el jugador",
}


def moneda_iso(m: str | None) -> str:
    return _ISO.get((m or "").strip().upper(), "PEN")


def modelo_reservas() -> str:
    v = str(stores.config.get("modelo_reservas") or "1").strip()
    return v if v in MODELOS else "1"


def es_modelo_2() -> bool:
    return modelo_reservas() == "2"


def _num(clave: str, defecto: str) -> float:
    try:
        return float(stores.config.get(clave, defecto))
    except (TypeError, ValueError):
        return float(defecto)


def params(moneda: str) -> dict:
    iso = moneda_iso(moneda)
    d = PARAMS_DEFAULT[iso]
    out: dict = {k: _num(f"m2_{iso}_{k}", v) for k, v in d.items() if k != "sobre"}
    sobre = str(stores.config.get(f"m2_{iso}_sobre", d["sobre"]) or "precio")
    out["sobre"] = sobre if sobre in ("precio", "cobrado") else "precio"
    out["moneda"] = iso
    out["simbolo"] = _SIMBOLO[iso]
    return out


def _r(x: float) -> int:
    """Céntimos, redondeo comercial (0.5 hacia arriba)."""
    return int(math.floor(x + 0.5 + 1e-9))


def calcular(precio_centimos: int, moneda: str, p: dict | None = None) -> dict:
    """Todo el desglose del modelo 2 para un precio (en céntimos). `p` permite
    simular con parámetros que aún no se guardaron (torre)."""
    p = p or params(moneda)
    P = max(int(precio_centimos or 0), 0)
    tasa_banco = p["banco_pct"] / 100.0
    tasa_pas = p["pasarela_pct"] / 100.0
    igv = p["igv_pct"] / 100.0
    s = p["reparto_cliente_pct"] / 100.0
    cc = p["cliente_pct"] / 100.0
    cd = p["dueno_pct"] / 100.0
    tasa_total = (tasa_banco + tasa_pas) * (1 + igv)
    if p.get("sobre") == "cobrado":
        # La pasarela cobra sobre lo que paga el jugador: se resuelve el punto
        # fijo pasarela = tasa × (P + s × pasarela) × (1 + cc).
        den = 1 - tasa_total * s * (1 + cc)
        pasarela = tasa_total * (1 + cc) * P / den if den > 0 else 0.0
    else:
        pasarela = tasa_total * P
    # Desglose de la pasarela en proporción a sus tasas (para mostrar).
    peso = (tasa_banco + tasa_pas) or 1.0
    banco = pasarela / (1 + igv) * tasa_banco / peso
    pas = pasarela / (1 + igv) * tasa_pas / peso
    pas_cliente = pasarela * s
    pas_dueno = pasarela - pas_cliente
    base_dueno = P - pas_dueno
    base_cliente = P + pas_cliente
    pcg_dueno = base_dueno * cd
    pcg_cliente = base_cliente * cc
    dueno_recibe = _r(base_dueno - pcg_dueno)
    cliente_paga = _r(base_cliente + pcg_cliente)
    cargo = max(cliente_paga - P, 0)              # lo que el jugador paga ADEMÁS del precio
    descuento = max(P - dueno_recibe, 0)          # lo que se le descuenta al dueño
    ingreso_pcg = _r(pcg_dueno) + _r(pcg_cliente)
    # Lo que la pasarela cobraría DE VERDAD (sobre el total cobrado) con estas
    # mismas tasas, y el margen que le queda a Pichangol tras pagarla.
    real = _r(tasa_total * cliente_paga)
    margen = cargo + descuento - real
    return {
        "moneda": p["moneda"], "simbolo": p["simbolo"], "sobre": p.get("sobre", "precio"),
        "precio_centimos": P,
        "banco_centimos": _r(banco), "igv_banco_centimos": _r(banco * igv),
        "pasarela_centimos": _r(pas), "igv_pasarela_centimos": _r(pas * igv),
        "pasarela_total_centimos": _r(pasarela),
        "pasarela_cliente_centimos": _r(pas_cliente), "pasarela_dueno_centimos": _r(pas_dueno),
        "base_dueno_centimos": _r(base_dueno), "base_cliente_centimos": _r(base_cliente),
        "pcg_dueno_centimos": _r(pcg_dueno), "pcg_cliente_centimos": _r(pcg_cliente),
        "dueno_recibe_centimos": dueno_recibe, "cliente_paga_centimos": cliente_paga,
        "cargo_cliente_centimos": cargo, "descuento_dueno_centimos": descuento,
        "ingreso_pcg_centimos": ingreso_pcg,
        "pasarela_real_centimos": real, "margen_real_centimos": margen,
    }


def descuento_dueno_centimos(precio_centimos: int, moneda: str) -> int:
    """Lo que se le descuenta al dueño por una reserva PAGADA EN LÍNEA."""
    return calcular(precio_centimos, moneda)["descuento_dueno_centimos"]


def comision_efectivo_centimos(precio_centimos: int, moneda: str) -> int:
    """Reserva traída por la app y pagada EN EFECTIVO: no hay pasarela ni cargo
    al jugador; solo la comisión Pichangol al dueño (puede ser 0)."""
    return _r(max(int(precio_centimos or 0), 0) * params(moneda)["dueno_pct"] / 100.0)


def desglose_cliente(c: dict) -> list[dict]:
    """Líneas que ve el jugador en la ⓘ del cargo (checkout y comprobante)."""
    out = []
    if c["pasarela_cliente_centimos"] > 0:
        out.append({"clave": "pago_en_linea", "nombre": "Costo del pago en línea",
                    "pct": 0.0, "monto_centimos": c["pasarela_cliente_centimos"],
                    "detalle": "Tu parte de lo que cobran el banco y la pasarela por procesar tu pago "
                               "(el dueño de la cancha paga la otra parte)."})
    if c["pcg_cliente_centimos"] > 0:
        out.append({"clave": "servicio_pichangol", "nombre": "Servicio Pichangol",
                    "pct": 0.0, "monto_centimos": c["cargo_cliente_centimos"] - c["pasarela_cliente_centimos"],
                    "detalle": "Reserva garantizada al instante, comprobante, reembolso según la política y soporte."})
    # Ajuste por redondeo: la suma de las líneas = el cargo exacto.
    if out:
        dif = c["cargo_cliente_centimos"] - sum(x["monto_centimos"] for x in out)
        out[-1]["monto_centimos"] += dif
    return out


def regla_texto(moneda: str) -> str:
    p = params(moneda)
    return (f"Costo del pago en línea compartido ({p['reparto_cliente_pct']:g} % lo paga el jugador) "
            f"+ {p['cliente_pct']:g} % de servicio Pichangol")


def publico() -> dict:
    """Lo que el APK y la web pueden saber del modelo vigente."""
    return {"modelo_reservas": modelo_reservas(),
            "monedas": {m: {k: v for k, v in params(m).items()} for m in MONEDAS}}


def leer() -> dict:
    return {"modelo_reservas": modelo_reservas(), "monedas": {m: params(m) for m in MONEDAS},
            "etiquetas": ETIQUETAS, "topes": _TOPES}


def guardar(body: dict) -> tuple[bool, str]:
    """Torre: {modelo_reservas: "1"|"2", monedas: {PEN: {cliente_pct, …, sobre}}}."""
    if not isinstance(body, dict):
        return False, "datos_invalidos"
    nuevos: dict[str, str] = {}
    if "modelo_reservas" in body:
        m = str(body.get("modelo_reservas") or "").strip()
        if m not in MODELOS:
            return False, "modelo_invalido"
        nuevos["modelo_reservas"] = m
    for iso, vals in (body.get("monedas") or {}).items():
        iso = moneda_iso(iso)
        if not isinstance(vals, dict):
            return False, "datos_invalidos"
        for k, v in vals.items():
            if k == "sobre":
                if v not in ("precio", "cobrado"):
                    return False, "sobre_invalido"
                nuevos[f"m2_{iso}_sobre"] = v
                continue
            if k not in _TOPES:
                continue
            try:
                x = float(v)
            except (TypeError, ValueError):
                return False, f"{k}_invalido"
            if x < 0 or x > _TOPES[k]:
                return False, f"{k}_fuera_de_rango"
            nuevos[f"m2_{iso}_{k}"] = f"{round(x, 4):g}"
    stores.config.update(nuevos)
    return True, ""
