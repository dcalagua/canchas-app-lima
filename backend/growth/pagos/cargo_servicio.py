"""CARGO POR SERVICIO al cliente (jugador / alumno) + desglose transparente.

Modelo aprobado por el director (27-sep-2026, `docs/diseno-cargo-por-servicio.md`):
dos lados como Airbnb. Quien RECIBE (dueño de cancha, academia) paga la
comisión de siempre (5 % con mínimo por moneda); quien PAGA ve una línea
aparte "Cargo por servicio Pichangol" = **% base sobre los primeros
`tramo` de la moneda + % reducido sobre el excedente, con mínimo**
(PEN: 5 % hasta S/ 500 + 2 % del resto, mín S/ 2). Pichangol absorbe la
pasarela: `margen = comisión + cargo − pasarela`.

Fuente de verdad del cálculo: este módulo. El APK y la web PIDEN la
cotización (`POST /pagos/cotizar`) para pintar el checkout y el backend la
RECALCULA al registrar la contabilidad; nunca se confía en el total que
manda el cliente.

Red de seguridad: si `comisión + cargo` no cubre el costo estimado de la
pasarela (`tarifas_pasarela.costo_centimos`, la tarifa configurada u
observada) más un margen mínimo, el cargo SUBE al múltiplo de 0.50
necesario. Así una subida de Culqi nunca deja una operación en pérdida.

Todo arranca APAGADO (`cargo_activo_<linea>` = 0): con el flag en 0 la
cotización devuelve cargo 0 y `activo: False`, y el checkout no muestra la
línea. Los parámetros y los textos del desglose viven en la torre.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

import config
from db.store import stores

LINEAS = ("reservas", "academias", "marketplace", "torneos")
MONEDAS = ("PEN", "USD", "BOB")
_SIMBOLO = {"PEN": "S/", "USD": "$", "BOB": "Bs"}
_MONEDA_ISO = {"S/": "PEN", "PEN": "PEN", "$": "USD", "USD": "USD", "BS": "BOB", "BOB": "BOB"}

# Parámetros por moneda (unidad mayor). Espejo de la tabla del diseño § 2.
PARAMS_DEFAULT: dict[str, dict[str, str]] = {
    "PEN": {"pct": "5", "min": "2", "tramo": "500", "pct_exc": "2", "margen_min": "2"},
    "USD": {"pct": "5", "min": "0.5", "tramo": "140", "pct_exc": "2", "margen_min": "0.5"},
    "BOB": {"pct": "5", "min": "3", "tramo": "1000", "pct_exc": "2", "margen_min": "3"},
}
# Claves de `stores.config` (CONFIG_DEFAULT las siembra también).
CLAVES_DEFAULT: dict[str, str] = {
    **{f"cargo_{m}_{k}": v for m, d in PARAMS_DEFAULT.items() for k, v in d.items()},
    **{f"cargo_activo_{l}": "0" for l in LINEAS},
}

# Desglose del cargo (§ 4 del diseño). Describe SOLO lo que Pichangol entrega:
# nunca "mantenimiento de cancha" ni nada del dueño (eso son servicios extra).
# Los pesos son referenciales del % base; el cliente paga el total.
TEXTOS_DEFAULT: dict = {
    "version": 1,
    "reservas": {
        "titulo": "Cargo por servicio Pichangol",
        "componentes": [
            {"clave": "pago_protegido", "nombre": "Pago protegido", "pct": 2.0,
             "detalle": "Cobro seguro con {medios}, antifraude, comprobante y reembolso si la cancha cancela."},
            {"clave": "reserva_garantizada", "nombre": "Reserva garantizada", "pct": 1.5,
             "detalle": "Turno bloqueado al instante, sin doble reserva, aviso al dueño, cancelación según política y soporte."},
            {"clave": "beneficios", "nombre": "Promociones y beneficios", "pct": 1.5,
             "detalle": "Puntos Pichangol, bonos de recarga, cupones, recordatorios e historial."},
        ],
        # Texto del tercer componente por deporte (clave = deporte del app).
        "por_deporte": {
            "futbol": {"nombre": "Tu equipo y tu partido", "detalle": "Vaquita entre jugadores, invitación por enlace, campeonatos con fixture, petos y árbitro reservables, puntos Pichangol."},
            "futsal": {"nombre": "Tu equipo y tu partido", "detalle": "Vaquita entre jugadores, invitación por enlace, campeonatos con fixture, petos y árbitro reservables, puntos Pichangol."},
            "basquet": {"nombre": "Tu equipo y tu partido", "detalle": "Vaquita entre jugadores, invitación por enlace, campeonatos, puntos Pichangol."},
            "voley": {"nombre": "Tu equipo y tu partido", "detalle": "Vaquita entre jugadores, invitación por enlace, campeonatos, puntos Pichangol."},
            "tenis": {"nombre": "Comunidad y ranking", "detalle": "Jugadores disponibles, retos, ranking, campeonatos, puntos Pichangol."},
            "padel": {"nombre": "Comunidad y ranking", "detalle": "Jugadores disponibles, retos, ranking, campeonatos, puntos Pichangol."},
            "pickleball": {"nombre": "Comunidad y ranking", "detalle": "Jugadores disponibles, retos, ranking, campeonatos, puntos Pichangol."},
        },
    },
    "academias": {
        "titulo": "Cargo por servicio Pichangol",
        "componentes": [
            {"clave": "pago_protegido", "nombre": "Pago protegido", "pct": 2.0,
             "detalle": "Cobro seguro con {medios}, comprobante y reembolso según la política de la academia."},
            {"clave": "gestion_matricula", "nombre": "Gestión de tu matrícula", "pct": 2.0,
             "detalle": "Cuotas, débito automático sin volver a poner tu tarjeta, recordatorios antes del vencimiento, carrito y descuento familiar aplicado solo."},
            {"clave": "portal_alumno", "nombre": "Portal del alumno y promociones", "pct": 1.0,
             "detalle": "Clases y pagos en la app para el alumno o el apoderado, chat con la academia, un solo pago para toda la familia, puntos."},
        ],
        "por_deporte": {
            "tenis": {"nombre": "Portal del alumno y competencia", "detalle": "Clases y pagos en la app, chat con la academia, ranking interno, retos y campeonatos de la academia."},
            "padel": {"nombre": "Portal del alumno y competencia", "detalle": "Clases y pagos en la app, chat con la academia, ranking interno, retos y campeonatos de la academia."},
            "natacion": {"nombre": "Portal del alumno y marcas", "detalle": "Clases y pagos en la app, chat con la academia, pruebas, tiempos y ranking por prueba."},
            "futbol": {"nombre": "Portal del alumno y equipos", "detalle": "Clases y pagos en la app, chat con la academia, plantel, fixture y campeonatos."},
        },
    },
    "marketplace": {
        "titulo": "Cargo por servicio Pichangol",
        "componentes": [
            {"clave": "pago_protegido", "nombre": "Pago protegido", "pct": 3.0, "detalle": "Cobro seguro con {medios}, comprobante y devolución si el producto no llega."},
            {"clave": "coordinacion", "nombre": "Coordinación de la entrega", "pct": 2.0, "detalle": "Chat con el vendedor, vendedores verificados, soporte."},
        ],
        "por_deporte": {},
    },
    "torneos": {
        "titulo": "Cargo por servicio Pichangol",
        "componentes": [
            {"clave": "pago_protegido", "nombre": "Pago protegido", "pct": 2.5, "detalle": "Cobro seguro con {medios}, comprobante y devolución si el equipo queda fuera antes de empezar."},
            {"clave": "torneo", "nombre": "Tu torneo en la app", "pct": 2.5, "detalle": "Vaquita del equipo, fixture, resultados y ranking en vivo."},
        ],
        "por_deporte": {},
    },
    # Lo que incluye la COMISIÓN de quien recibe (se muestra al dueño/academia).
    "comision": {
        "reservas": [
            {"clave": "marketing", "nombre": "Visibilidad y marketing", "pct": 2.0, "detalle": "Explorador de la app y la web, ficha pública con fotos y reseñas, Google, redes de Pichangol, campañas por deporte y zona."},
            {"clave": "operacion", "nombre": "Agenda y reservas", "pct": 1.5, "detalle": "Calendario en línea, reserva manual y bloqueos, sin doble reserva, recordatorios de cobro, WhatsApp del jugador."},
            {"clave": "cobros", "nombre": "Cobros y liquidación", "pct": 1.5, "detalle": "Cobro en línea, billetera, liquidación a tu cuenta, reportes de ingresos."},
        ],
        "academias": [
            {"clave": "marketing", "nombre": "Visibilidad y marketing", "pct": 2.0, "detalle": "Pestaña Academias del explorador, ficha web con tarifario y matrícula en línea, landing pública, redes de Pichangol."},
            {"clave": "operacion", "nombre": "Alumnos y cuotas", "pct": 2.0, "detalle": "Matrículas, cuotas, débito automático, recordatorios de vencimiento, familia y descuentos, morosos."},
            {"clave": "cobros", "nombre": "Cobros y liquidación", "pct": 1.0, "detalle": "Cobro en línea, comprobante al alumno, liquidación a tu cuenta."},
        ],
    },
}

_MEDIOS_POR_MONEDA = {"PEN": "Yape o tarjeta", "USD": "tarjeta", "BOB": "QR o tarjeta"}


def moneda_iso(m: str | None) -> str:
    return _MONEDA_ISO.get((m or "").strip().upper(), "PEN")


def _f(clave: str, defecto: str = "0") -> float:
    try:
        return float(stores.config.get(clave, CLAVES_DEFAULT.get(clave, defecto)))
    except (TypeError, ValueError):
        return float(defecto)


def params(moneda: str) -> dict:
    """Parámetros vigentes de la moneda (torre → defaults)."""
    iso = moneda_iso(moneda)
    d = PARAMS_DEFAULT.get(iso, PARAMS_DEFAULT["PEN"])
    return {k: _f(f"cargo_{iso}_{k}", v) for k, v in d.items()} | {"moneda": iso, "simbolo": _SIMBOLO.get(iso, "S/")}


def activo(linea: str) -> bool:
    return _f(f"cargo_activo_{linea}") >= 1


def textos() -> dict:
    """Catálogo de textos del desglose (torre → defaults)."""
    t = stores.cargo_servicio_textos if isinstance(getattr(stores, "cargo_servicio_textos", None), dict) else {}
    return t if t.get("componentes_ok") else _con_defaults(t)


def _con_defaults(t: dict) -> dict:
    out = {k: (v if not isinstance(v, dict) else dict(v)) for k, v in TEXTOS_DEFAULT.items()}
    for k, v in (t or {}).items():
        if k == "comision" and isinstance(v, dict):
            out["comision"] = {**out["comision"], **v}
        elif isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = {**out[k], **v}
        else:
            out[k] = v
    return out


def _redondear_arriba(centimos: int, paso: int = 10) -> int:
    """Al múltiplo de `paso` céntimos hacia arriba (0.10 por defecto)."""
    return int(math.ceil(centimos / paso) * paso)


def cargo_centimos(base_centimos: int, moneda: str) -> int:
    """Regla visible: % base hasta el tramo + % excedente, mínimo; redondeo a
    0.10 hacia arriba. Base ≤ 0 → 0."""
    if base_centimos <= 0:
        return 0
    p = params(moneda)
    tramo = int(round(p["tramo"] * 100))
    base_tramo = min(base_centimos, tramo)
    exceso = max(base_centimos - tramo, 0)
    bruto = base_tramo * p["pct"] / 100.0 + exceso * p["pct_exc"] / 100.0
    con_min = max(bruto, p["min"] * 100.0)
    return _redondear_arriba(int(math.ceil(con_min - 1e-9)))


def regla_texto(moneda: str) -> str:
    p = params(moneda)
    s = p["simbolo"]
    return (f"{p['pct']:g} % sobre los primeros {s} {p['tramo']:g} del pago + {p['pct_exc']:g} % sobre el excedente, "
            f"mínimo {s} {p['min']:.2f}")


@dataclass
class Cotizacion:
    linea: str
    moneda: str
    simbolo: str
    activo: bool
    base_centimos: int
    cargo_centimos: int
    total_centimos: int
    ajuste_seguridad_centimos: int = 0
    regla: str = ""
    titulo: str = ""
    desglose: list[dict] = field(default_factory=list)
    ahorro_centimos: int = 0  # por pagar junto (carrito), 0 si una sola parte

    def dict(self) -> dict:
        d = asdict(self)
        d.update({"base_soles": self.base_centimos / 100.0, "cargo_soles": self.cargo_centimos / 100.0,
                  "total_soles": self.total_centimos / 100.0, "ahorro_soles": self.ahorro_centimos / 100.0})
        return d


def desglose(linea: str, moneda: str, cargo: int, deporte: str = "") -> list[dict]:
    """Componentes del cargo con su monto proporcional (para la ⓘ y el
    comprobante). Se CONGELA en el pago."""
    t = textos().get(linea) or textos().get("reservas") or {}
    comps = [dict(c) for c in (t.get("componentes") or [])]
    esp = (t.get("por_deporte") or {}).get((deporte or "").strip().lower())
    if esp and comps:
        comps[-1] = {**comps[-1], **{k: v for k, v in esp.items() if k in ("nombre", "detalle")}}
    medios = _MEDIOS_POR_MONEDA.get(moneda_iso(moneda), "tarjeta")
    total_pct = sum(float(c.get("pct") or 0) for c in comps) or 1.0
    out, acumulado = [], 0
    for i, c in enumerate(comps):
        if i == len(comps) - 1:
            monto = cargo - acumulado
        else:
            monto = int(round(cargo * float(c.get("pct") or 0) / total_pct))
            acumulado += monto
        out.append({"clave": c.get("clave"), "nombre": c.get("nombre"), "pct": float(c.get("pct") or 0),
                    "detalle": str(c.get("detalle") or "").replace("{medios}", medios), "monto_centimos": max(monto, 0)})
    return out


def red_de_seguridad(base_centimos: int, cargo: int, comision_centimos: int, moneda: str, medio: str | None,
                     tipo: str = "liquidacion_online") -> int:
    """Devuelve el cargo (≥ el recibido) que garantiza `comisión + cargo ≥
    costo_pasarela(base + cargo) + margen_min`, en múltiplos de 0.50. Si la
    pasarela no está configurada (costo 0) no cambia nada."""
    from pagos import tarifas_pasarela as _tp
    iso = moneda_iso(moneda)
    margen_min = int(round(params(iso)["margen_min"] * 100))
    c = cargo
    for _ in range(40):  # converge en 1-2 vueltas; el tope evita bucles
        costo = _tp.costo_centimos(base_centimos + c, iso, medio, tipo)
        if costo <= 0 or comision_centimos + c >= costo + margen_min:
            return c
        falta = costo + margen_min - comision_centimos - c
        c = _redondear_arriba(c + falta, 50)
    return c


def cotizar(*, linea: str, moneda: str, base_centimos: int, medio: str | None = None, deporte: str = "",
            comision_centimos: int | None = None, partes: list[int] | None = None,
            forzar_activo: bool | None = None) -> Cotizacion:
    """Cotización completa para el checkout / la contabilidad."""
    iso = moneda_iso(moneda)
    linea = linea if linea in LINEAS else "reservas"
    esta_activo = activo(linea) if forzar_activo is None else forzar_activo
    base = max(int(base_centimos or 0), 0)
    if not esta_activo or base <= 0:
        return Cotizacion(linea=linea, moneda=iso, simbolo=_SIMBOLO.get(iso, "S/"), activo=esta_activo, base_centimos=base,
                          cargo_centimos=0, total_centimos=base, regla=regla_texto(iso), titulo=(textos().get(linea) or {}).get("titulo", ""))
    cargo = cargo_centimos(base, iso)
    ajuste = 0
    if comision_centimos is not None:
        seguro = red_de_seguridad(base, cargo, comision_centimos, iso, medio, _tipo_de(linea))
        ajuste = seguro - cargo
        cargo = seguro
    ahorro = 0
    if partes and len(partes) > 1:
        ahorro = max(sum(cargo_centimos(int(p), iso) for p in partes) - cargo, 0)
    return Cotizacion(linea=linea, moneda=iso, simbolo=_SIMBOLO.get(iso, "S/"), activo=True, base_centimos=base,
                      cargo_centimos=cargo, total_centimos=base + cargo, ajuste_seguridad_centimos=ajuste,
                      regla=regla_texto(iso), titulo=(textos().get(linea) or {}).get("titulo", "Cargo por servicio Pichangol"),
                      desglose=desglose(linea, iso, cargo, deporte), ahorro_centimos=ahorro)


def _tipo_de(linea: str) -> str:
    return {"reservas": "liquidacion_online", "academias": "matricula_online", "marketplace": "venta_producto",
            "torneos": "liquidacion_online"}.get(linea, "liquidacion_online")


def publico() -> dict:
    """Respuesta de `GET /config/cargo-servicio` (APK + web, cache-first)."""
    t = textos()
    return {
        "version": int(t.get("version") or 1),
        "activo": {l: activo(l) for l in LINEAS},
        "monedas": {m: params(m) for m in MONEDAS},
        "regla": {m: regla_texto(m) for m in MONEDAS},
        "textos": {k: t[k] for k in LINEAS if k in t},
        "comision": t.get("comision") or {},
    }


def validar_y_guardar(body: dict) -> tuple[bool, str]:
    """Torre: guarda parámetros por moneda, flags por línea y textos."""
    nuevos: dict[str, str] = {}
    for m, vals in (body.get("monedas") or {}).items():
        iso = moneda_iso(m)
        if iso not in PARAMS_DEFAULT or not isinstance(vals, dict):
            continue
        for k in ("pct", "min", "tramo", "pct_exc", "margen_min"):
            if k not in vals:
                continue
            try:
                v = float(vals[k])
            except (TypeError, ValueError):
                return False, f"{iso} · {k}: número inválido."
            if k in ("pct", "pct_exc") and not (0 <= v <= 30):
                return False, f"{iso} · {k}: el porcentaje va de 0 a 30."
            if k in ("min", "tramo", "margen_min") and not (0 <= v <= 100000):
                return False, f"{iso} · {k}: fuera de rango."
            nuevos[f"cargo_{iso}_{k}"] = f"{v:g}"
    for l, v in (body.get("activo") or {}).items():
        if l in LINEAS:
            nuevos[f"cargo_activo_{l}"] = "1" if v in (True, 1, "1", "true") else "0"
    textos_nuevos = body.get("textos")
    if isinstance(textos_nuevos, dict):
        t = _con_defaults(stores.cargo_servicio_textos if isinstance(stores.cargo_servicio_textos, dict) else {})
        for k, v in textos_nuevos.items():
            if k in LINEAS and isinstance(v, dict):
                comps = v.get("componentes")
                if comps is not None:
                    if not isinstance(comps, list) or not comps or len(comps) > 6:
                        return False, f"{k}: entre 1 y 6 componentes."
                    limpios = []
                    for c in comps:
                        nombre = str(c.get("nombre") or "").strip()[:60]
                        if not nombre:
                            return False, f"{k}: cada componente necesita nombre."
                        try:
                            pct = float(c.get("pct") or 0)
                        except (TypeError, ValueError):
                            return False, f"{k}: peso inválido."
                        limpios.append({"clave": str(c.get("clave") or nombre.lower().replace(" ", "_"))[:40], "nombre": nombre,
                                        "pct": pct, "detalle": str(c.get("detalle") or "").strip()[:300]})
                    t.setdefault(k, {})["componentes"] = limpios
                if isinstance(v.get("por_deporte"), dict):
                    t.setdefault(k, {})["por_deporte"] = {
                        str(d)[:20]: {"nombre": str(x.get("nombre") or "")[:60], "detalle": str(x.get("detalle") or "")[:300]}
                        for d, x in v["por_deporte"].items() if isinstance(x, dict)}
                if v.get("titulo"):
                    t.setdefault(k, {})["titulo"] = str(v["titulo"])[:60]
            elif k == "comision" and isinstance(v, dict):
                t["comision"] = {**(t.get("comision") or {}), **{l2: c2 for l2, c2 in v.items() if l2 in LINEAS and isinstance(c2, list)}}
        t["version"] = int(t.get("version") or 1) + 1
        t["componentes_ok"] = True
        stores.cargo_servicio_textos = t
    if not nuevos and not isinstance(textos_nuevos, dict):
        return False, "Nada que guardar."
    stores.config.update(nuevos)
    return True, ""


def repartir(cargo_centimos: int, subtotales: list[int]) -> list[int]:
    """Reparte un cargo proporcionalmente a [subtotales] (resto al primero):
    un pago que cubre varias matrículas/academias deja su parte del cargo en
    cada fila. Espejo de `CargoServicio.repartir` del APK."""
    total = sum(int(x) for x in subtotales)
    if not subtotales or total <= 0 or cargo_centimos <= 0:
        return [0] * len(subtotales)
    out = [int(cargo_centimos * int(s) // total) for s in subtotales]
    out[0] += int(cargo_centimos) - sum(out)
    return out


def sin_cargo_recientes(dias: int = 30) -> dict:
    """KPI de la torre: operaciones cobradas en línea SIN cargo (APK viejo)
    desde que la línea está activa, en los últimos `dias`."""
    from datetime import datetime, timedelta, timezone
    corte = datetime.now(timezone.utc) - timedelta(days=dias)
    out = {"reservas": 0, "academias": 0, "con_cargo": 0}
    for p in stores.pagos:
        if p.creado_en < corte or p.estado != "aprobado":
            continue
        if p.tipo in ("liquidacion_online", "liquidacion_full"):
            linea = "reservas"
        elif p.tipo == "matricula_online":
            linea = "academias"
        else:
            continue
        if int(getattr(p, "cargo_servicio_centimos", 0) or 0) > 0:
            out["con_cargo"] += 1
        elif activo(linea):
            out[linea] += 1
    return out
