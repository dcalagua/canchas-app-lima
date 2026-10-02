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

MÍNIMO POR RESERVA (decisión del director, 2-oct-2026, opción B): la
comisión al jugador es max(% × base jugador, mínimo por moneda) — S/ 1 ·
$ 0.30 · Bs 2 por defecto —, así en una cancha barata el % efectivo sube
solo (S/ 30 → S/ 1.00 = 3.2 %) y nunca cobra menos a una cancha más cara.
`cliente_tope_pct` (0 = sin tope) limita ese mínimo en canchas muy baratas.
El dueño tiene su propio mínimo (`dueno_min`, 0 = apagado), que también
aplica en efectivo. Ninguna comisión supera la base de quien la paga.

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
# TARIFA POR MEDIO (2-oct-2026, calculadora de Culqi que mostró el director):
# Yape en línea = 3.44 % + $ 0.20 (≈ S/ 0.77) por cobro, "comisiones
# inafectas a IGV"; la tarjeta = banco 2.5 % + Culqi 5.5 % (lo observado en el
# cobro real de S/ 15: 0.38 + 0.83, abono sin IGV encima). La pasarela se
# calcula sobre lo COBRADO (es lo que Culqi descuenta de verdad); `sobre` =
# "precio" reproduce la hoja original. `igv_aplica` = "1" suma el IGV.
_BASE = {"cliente_pct": "1.2", "dueno_pct": "0", "banco_pct": "2.5", "pasarela_pct": "5.5",
         "reparto_cliente_pct": "50", "sobre": "cobrado", "dueno_min": "0", "cliente_tope_pct": "0",
         "igv_aplica": "0", "tarjeta_fijo": "0", "yape_pct": "3.44", "yape_fijo": "0.77"}
PARAMS_DEFAULT: dict[str, dict[str, str]] = {
    "PEN": {**_BASE, "igv_pct": "18", "cliente_min": "1"},
    "USD": {**_BASE, "igv_pct": "15", "cliente_min": "0.3"},
    "BOB": {**_BASE, "igv_pct": "13", "cliente_min": "2"},
}
CLAVES_DEFAULT: dict[str, str] = {
    "modelo_reservas": "1",
    **{f"m2_{m}_{k}": v for m, d in PARAMS_DEFAULT.items() for k, v in d.items()},
}
# Claves que no son números (se validan aparte).
_TEXTO = {"sobre": ("precio", "cobrado"), "igv_aplica": ("0", "1")}
# Topes de validación (en % o en la moneda).
_TOPES = {"cliente_pct": 30.0, "dueno_pct": 30.0, "banco_pct": 15.0, "pasarela_pct": 15.0,
          "igv_pct": 30.0, "reparto_cliente_pct": 100.0,
          "cliente_min": 100.0, "dueno_min": 100.0, "cliente_tope_pct": 50.0,
          "tarjeta_fijo": 20.0, "yape_pct": 15.0, "yape_fijo": 20.0}
ETIQUETAS = {
    "cliente_pct": "Comisión Pichangol al jugador",
    "dueno_pct": "Comisión Pichangol al dueño",
    "banco_pct": "Comisión del banco (tarjeta)",
    "pasarela_pct": "Comisión Culqi (tarjeta)",
    "tarjeta_fijo": "Fijo por cobro con tarjeta",
    "yape_pct": "Comisión Culqi con Yape",
    "yape_fijo": "Fijo por cobro con Yape",
    "igv_pct": "IGV / IVA sobre las comisiones",
    "igv_aplica": "La pasarela cobra IGV",
    "reparto_cliente_pct": "Parte de la pasarela que paga el jugador",
    "cliente_min": "Mínimo de la comisión al jugador (monto por reserva)",
    "dueno_min": "Mínimo de la comisión al dueño (monto por reserva, 0 = sin mínimo)",
    "cliente_tope_pct": "Tope de la comisión al jugador (% de su base, 0 = sin tope)",
}
# Medios con tarifa propia por moneda: Yape solo existe en soles; en $ y Bs
# hay una sola pasarela hospedada (PayPhone / Libélula) = tarifa "tarjeta".
MEDIOS = {"PEN": ("yape", "tarjeta"), "USD": ("tarjeta",), "BOB": ("tarjeta",)}
NOMBRE_MEDIO = {"yape": "Yape", "tarjeta": "Tarjeta"}


def moneda_iso(m: str | None) -> str:
    return _ISO.get((m or "").strip().upper(), "PEN")


def medio_de(medio: str | None, moneda: str) -> str:
    """Normaliza el medio a una tarifa conocida de esa moneda. Desconocido
    (seña, vacío, APK viejo) = "tarjeta": es la tarifa con la que esos
    clientes cotizaron, así lo cobrado y lo liquidado calzan."""
    m = (medio or "").strip().lower()
    return m if m in MEDIOS.get(moneda_iso(moneda), ("tarjeta",)) else "tarjeta"


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
    out: dict = {k: _num(f"m2_{iso}_{k}", v) for k, v in d.items() if k not in _TEXTO}
    for k, validos in _TEXTO.items():
        v = str(stores.config.get(f"m2_{iso}_{k}", d[k]) or d[k])
        out[k] = v if v in validos else d[k]
    out["moneda"] = iso
    out["simbolo"] = _SIMBOLO[iso]
    out["medios"] = list(MEDIOS[iso])
    return out


def _r(x: float) -> int:
    """Céntimos, redondeo comercial (0.5 hacia arriba)."""
    return int(math.floor(x + 0.5 + 1e-9))


def _comision(base: float, pct: float, minimo_centimos: float, tope_pct: float = 0.0) -> float:
    """Comisión en céntimos = max(% × base, mínimo), con tope opcional en % de
    la base y nunca más que la base. Sin % ni mínimo → 0."""
    if base <= 0 or (pct <= 0 and minimo_centimos <= 0):
        return 0.0
    c = max(base * pct, minimo_centimos)
    if tope_pct > 0:
        c = min(c, base * tope_pct)
    return min(c, base)


def tarifa(p: dict, medio: str) -> dict:
    """Tasa (fracción) y fijo (céntimos) de la pasarela para un medio, con el
    IGV si aplica. `pcts` = las partes del % para el desglose."""
    igv = p["igv_pct"] / 100.0 if str(p.get("igv_aplica", "0")) == "1" else 0.0
    if medio == "yape":
        pcts = [("Comisión Culqi · Yape", p["yape_pct"] / 100.0)]
        fijo = p["yape_fijo"] * 100.0
    else:
        pcts = [("Comisión del banco", p["banco_pct"] / 100.0), ("Comisión Culqi", p["pasarela_pct"] / 100.0)]
        fijo = p["tarjeta_fijo"] * 100.0
    sin_igv = sum(x for _, x in pcts)
    return {"pcts": pcts, "igv": igv, "tasa": sin_igv * (1 + igv), "tasa_sin_igv": sin_igv,
            "fijo": fijo * (1 + igv), "fijo_sin_igv": fijo}


def calcular(precio_centimos: int, moneda: str, p: dict | None = None, medio: str | None = None) -> dict:
    """Todo el desglose del modelo 2 para un precio (en céntimos) pagado con
    `medio` (yape | tarjeta). `p` permite simular con parámetros que aún no
    se guardaron (torre)."""
    p = p or params(moneda)
    iso = p.get("moneda") or moneda_iso(moneda)
    md = medio_de(medio, iso)
    P = max(int(precio_centimos or 0), 0)
    t = tarifa(p, md)
    s = p["reparto_cliente_pct"] / 100.0
    cc = p["cliente_pct"] / 100.0
    cd = p["dueno_pct"] / 100.0
    cmin = float(p.get("cliente_min", 0) or 0) * 100.0
    dmin = float(p.get("dueno_min", 0) or 0) * 100.0
    ctope = float(p.get("cliente_tope_pct", 0) or 0) / 100.0
    if P <= 0:
        pasarela = 0.0
    elif p.get("sobre") == "cobrado":
        # La pasarela cobra sobre lo que paga el jugador: punto fijo
        # pasarela = tasa × (base jugador + comisión jugador) + fijo.
        pasarela = t["tasa"] * P + t["fijo"]
        for _ in range(60):
            bc = P + s * pasarela
            nuevo = t["tasa"] * (bc + _comision(bc, cc, cmin, ctope)) + t["fijo"]
            if abs(nuevo - pasarela) < 1e-7:
                break
            pasarela = nuevo
    else:
        pasarela = t["tasa"] * P + t["fijo"]
    # Desglose de la pasarela (para mostrar): cada % y el fijo, con su IGV.
    sin_igv = pasarela / (1 + t["igv"]) if pasarela else 0.0
    fijo_sin = t["fijo_sin_igv"] if P > 0 else 0.0
    var_sin = max(sin_igv - fijo_sin, 0.0)
    partes = []
    for nombre, x in t["pcts"]:
        monto = var_sin * x / (t["tasa_sin_igv"] or 1.0)
        partes.append({"nombre": nombre, "pct": round(x * 100, 4), "centimos": _r(monto)})
    pas_cliente = pasarela * s
    pas_dueno = pasarela - pas_cliente
    base_dueno = P - pas_dueno
    base_cliente = P + pas_cliente
    pcg_dueno = _comision(base_dueno, cd, dmin)
    pcg_cliente = _comision(base_cliente, cc, cmin, ctope)
    dueno_recibe = _r(base_dueno - pcg_dueno)
    cliente_paga = _r(base_cliente + pcg_cliente)
    cargo = max(cliente_paga - P, 0)              # lo que el jugador paga ADEMÁS del precio
    descuento = max(P - dueno_recibe, 0)          # lo que se le descuenta al dueño
    ingreso_pcg = _r(pcg_dueno) + _r(pcg_cliente)
    # Lo que la pasarela cobra DE VERDAD (sobre el total cobrado) con estas
    # tarifas, y lo que le queda a Pichangol tras pagarla.
    real = _r(t["tasa"] * cliente_paga + t["fijo"]) if P > 0 else 0
    margen = cargo + descuento - real
    banco = partes[0]["centimos"] if md == "tarjeta" else 0
    culqi = partes[-1]["centimos"]
    return {
        "moneda": iso, "simbolo": p.get("simbolo") or _SIMBOLO[iso], "sobre": p.get("sobre", "cobrado"),
        "medio": md, "medio_nombre": NOMBRE_MEDIO.get(md, md), "igv_aplica": t["igv"] > 0,
        "reparto_pct": round(p["reparto_cliente_pct"], 2),
        "precio_centimos": P, "partes_pasarela": partes,
        "banco_centimos": banco, "igv_banco_centimos": _r(banco * t["igv"]),
        "pasarela_centimos": culqi, "igv_pasarela_centimos": _r((sin_igv - banco) * t["igv"]),
        "fijo_centimos": _r(fijo_sin), "igv_centimos": _r(sin_igv * t["igv"]),
        "pasarela_total_centimos": _r(pasarela),
        "pasarela_cliente_centimos": _r(pas_cliente), "pasarela_dueno_centimos": _r(pas_dueno),
        "base_dueno_centimos": _r(base_dueno), "base_cliente_centimos": _r(base_cliente),
        "pcg_dueno_centimos": _r(pcg_dueno), "pcg_cliente_centimos": _r(pcg_cliente),
        "dueno_recibe_centimos": dueno_recibe, "cliente_paga_centimos": cliente_paga,
        "cargo_cliente_centimos": cargo, "descuento_dueno_centimos": descuento,
        "ingreso_pcg_centimos": ingreso_pcg,
        "pasarela_real_centimos": real, "margen_real_centimos": margen,
        "cliente_pct_efectivo": round(pcg_cliente / base_cliente * 100, 2) if base_cliente > 0 else 0.0,
        "dueno_pct_efectivo": round(pcg_dueno / base_dueno * 100, 2) if base_dueno > 0 else 0.0,
        "cliente_min_aplicado": bool(pcg_cliente > 0 and base_cliente * cc < cmin),
    }


def descuento_dueno_centimos(precio_centimos: int, moneda: str, medio: str | None = None) -> int:
    """Lo que se le descuenta al dueño por una reserva PAGADA EN LÍNEA con ese medio."""
    return calcular(precio_centimos, moneda, medio=medio)["descuento_dueno_centimos"]


def comision_efectivo_centimos(precio_centimos: int, moneda: str) -> int:
    """Reserva traída por la app y pagada EN EFECTIVO: no hay pasarela ni cargo
    al jugador; solo la comisión Pichangol al dueño (puede ser 0)."""
    p = params(moneda)
    return _r(_comision(max(int(precio_centimos or 0), 0), p["dueno_pct"] / 100.0, p.get("dueno_min", 0) * 100.0))


def desglose_cliente(c: dict) -> list[dict]:
    """Líneas que ve el jugador en la ⓘ del cargo (checkout y comprobante)."""
    out = []
    medio = "con Yape" if c.get("medio") == "yape" else ("con tarjeta" if c.get("moneda") == "PEN" else "")
    if c["pasarela_cliente_centimos"] > 0:
        out.append({"clave": "pago_en_linea", "nombre": "Costo del pago en línea" + (f" ({medio})" if medio else ""),
                    "pct": 0.0, "monto_centimos": c["pasarela_cliente_centimos"],
                    "detalle": "Tu parte de lo que cobra la pasarela por procesar tu pago "
                               "(el dueño de la cancha paga la otra parte)."
                               + (" Con Yape es más barato." if c.get("medio") == "tarjeta" and c.get("moneda") == "PEN" else "")})
    if c["pcg_cliente_centimos"] > 0:
        out.append({"clave": "servicio_pichangol", "nombre": "Servicio Pichangol",
                    "pct": 0.0, "monto_centimos": c["cargo_cliente_centimos"] - c["pasarela_cliente_centimos"],
                    "detalle": "Reserva garantizada al instante, comprobante, reembolso según la política y soporte."})
    # Ajuste por redondeo: la suma de las líneas = el cargo exacto.
    if out:
        dif = c["cargo_cliente_centimos"] - sum(x["monto_centimos"] for x in out)
        out[-1]["monto_centimos"] += dif
    return out


def regla_texto(moneda: str, medio: str | None = None) -> str:
    p = params(moneda)
    md = medio_de(medio, moneda)
    quien = f"{p['reparto_cliente_pct']:g} % lo paga el jugador"
    pago = f"Costo del pago en línea{' con Yape' if md == 'yape' else (' con tarjeta' if len(p['medios']) > 1 else '')}"
    return (f"{pago} compartido ({quien}) + {p['cliente_pct']:g} % de servicio Pichangol"
            + (f" (mínimo {p['simbolo']} {p['cliente_min']:.2f})" if p.get("cliente_min", 0) > 0 else ""))


def publico() -> dict:
    """Lo que el APK y la web pueden saber del modelo vigente."""
    return {"modelo_reservas": modelo_reservas(),
            "monedas": {m: {k: v for k, v in params(m).items()} for m in MONEDAS}}


def leer() -> dict:
    return {"modelo_reservas": modelo_reservas(), "monedas": {m: params(m) for m in MONEDAS},
            "etiquetas": ETIQUETAS, "topes": _TOPES}


def guardar(body: dict) -> tuple[bool, str]:
    """Torre: {modelo_reservas: "1"|"2", monedas: {PEN: {cliente_pct, …, sobre, igv_aplica}}}."""
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
            if k in _TEXTO:
                v = str(v)
                if v in ("true", "True"):
                    v = "1"
                elif v in ("false", "False"):
                    v = "0"
                if v not in _TEXTO[k]:
                    return False, f"{k}_invalido"
                nuevos[f"m2_{iso}_{k}"] = v
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
