"""Cuenta de COBRO del dueño + liquidación POR LOTE (archivo Telecrédito BCP).

Pedido del director (26-sep-2026), tras el primer cobro live: "¿hay forma de
transferirle al dueño de manera automática o desde la torre?". Culqi cobra pero
no dispersa (no tiene payouts en Perú) y Yape no ofrece API a empresas, así
que la liquidación se hace desde la cuenta empresa de EBIM en el BCP. Este
módulo cubre las dos piezas que sí dependen de nosotros:

1. **Cuenta de cobro** (`stores.cuentas_cobro[email]`): dónde quiere recibir
   su plata cada dueño/organizador/academia. Se registra en la billetera del
   app o en Ingresos de la web. Por país:
   - PE: Yape / Plin (celular de 9 dígitos) o cuenta bancaria (banco del
     catálogo + n.º de cuenta + CCI de 20 dígitos + titular + DNI/CE/RUC).
   - BO: cuenta bancaria (banco + n.º de cuenta + titular + CI).
   - EC: cuenta bancaria (banco + tipo + n.º de cuenta + titular + cédula/RUC).
   Todo por SELECCIÓN salvo números y nombre del titular (regla del app).

2. **Lote de liquidación** (`stores.lotes_liquidacion`): la torre agrupa las
   liquidaciones pendientes POR DUEÑO (un dueño con 8 reservas = una sola
   transferencia), aplica un umbral mínimo (no vale la pena una interbancaria
   por S/ 13) y genera el archivo de **pagos masivos de Telecrédito BCP**
   (`archivo_telecredito`) con las cuentas bancarias peruanas; Yape/Plin y
   otros países quedan listados para pagarlos a mano. Al confirmar el lote,
   todas sus liquidaciones se marcan pagadas con la misma referencia.

**OJO con el TXT:** la estructura de ancho fijo de abajo (`_CABECERA`,
`_DETALLE`) es la del formato clásico "Pago a proveedores" de Telecrédito
Web. No pudimos descargar el instructivo oficial desde el entorno de
desarrollo, así que la PRIMERA carga en Telecrédito debe hacerse como
validación: el banco rechaza el archivo con el campo exacto si algo no calza y
no mueve un sol hasta que el operador firma la planilla. Cualquier ajuste es
tocar una fila de la tabla. El CSV (`archivo_csv`) es el respaldo universal.
"""

from __future__ import annotations

import re
import time
from datetime import datetime, timezone

# ── Catálogos por país (SELECCIÓN, nunca texto libre) ────────────────────────

# (código, nombre). El código es estable: es lo que se guarda.
BANCOS: dict[str, list[tuple[str, str]]] = {
    "PE": [
        ("BCP", "BCP"), ("INTERBANK", "Interbank"), ("BBVA", "BBVA"),
        ("SCOTIABANK", "Scotiabank"), ("BN", "Banco de la Nación"),
        ("BANBIF", "BanBif"), ("PICHINCHA", "Banco Pichincha"),
        ("MIBANCO", "Mibanco"), ("COMERCIO", "Banco de Comercio"),
        ("CAJA_AREQUIPA", "Caja Arequipa"), ("CAJA_HUANCAYO", "Caja Huancayo"),
        ("CAJA_PIURA", "Caja Piura"), ("CAJA_CUSCO", "Caja Cusco"),
        ("CAJA_TRUJILLO", "Caja Trujillo"), ("OTRO", "Otro banco / caja"),
    ],
    "BO": [
        ("UNION", "Banco Unión"), ("BNB", "Banco Nacional de Bolivia"),
        ("MERCANTIL", "Banco Mercantil Santa Cruz"), ("BCP_BO", "BCP Bolivia"),
        ("BISA", "Banco BISA"), ("GANADERO", "Banco Ganadero"),
        ("SOL", "Banco Sol"), ("ECONOMICO", "Banco Económico"),
        ("FIE", "Banco FIE"), ("FORTALEZA", "Banco Fortaleza"),
        ("OTRO", "Otro banco"),
    ],
    "EC": [
        ("PICHINCHA_EC", "Banco Pichincha"), ("GUAYAQUIL", "Banco de Guayaquil"),
        ("PACIFICO", "Banco del Pacífico"), ("PRODUBANCO", "Produbanco"),
        ("BOLIVARIANO", "Banco Bolivariano"), ("INTERNACIONAL", "Banco Internacional"),
        ("AUSTRO", "Banco del Austro"), ("SOLIDARIO", "Banco Solidario"),
        ("MACHALA", "Banco de Machala"), ("BANECUADOR", "BanEcuador"),
        ("JEP", "Cooperativa JEP"), ("OTRO", "Otro banco / cooperativa"),
    ],
}

# Tipos de cuenta de cobro por país. 'yape'/'plin' solo Perú.
TIPOS: dict[str, list[tuple[str, str]]] = {
    "PE": [("yape", "Yape"), ("plin", "Plin"), ("banco", "Cuenta bancaria")],
    "BO": [("banco", "Cuenta bancaria")],
    "EC": [("banco", "Cuenta bancaria")],
}

TIPOS_CUENTA = [("ahorros", "Ahorros"), ("corriente", "Corriente")]

# Documento del titular por país (código, etiqueta, largos aceptados).
DOCS: dict[str, list[tuple[str, str, tuple[int, ...]]]] = {
    "PE": [("DNI", "DNI", (8,)), ("CE", "Carné de extranjería", (9, 10, 11, 12)),
           ("RUC", "RUC", (11,)), ("PASAPORTE", "Pasaporte", tuple(range(6, 13)))],
    "BO": [("CI", "Cédula de identidad", tuple(range(5, 13))), ("NIT", "NIT", tuple(range(7, 15)))],
    "EC": [("CEDULA", "Cédula", (10,)), ("RUC", "RUC", (13,)), ("PASAPORTE", "Pasaporte", tuple(range(6, 13)))],
}

# Largo del celular (Yape/Plin) por país — espejo de `PaisConfig.telLongitud`.
TEL_LONGITUD = {"PE": 9, "BO": 8, "EC": 9}
MONEDA_POR_PAIS = {"PE": "PEN", "BO": "BOB", "EC": "USD"}
SIMBOLO = {"PEN": "S/", "BOB": "Bs", "USD": "$"}


def catalogo() -> dict:
    """Lo que el app y la web necesitan para pintar el formulario por país."""
    return {
        iso: {
            "tipos": [{"codigo": c, "nombre": n} for c, n in TIPOS[iso]],
            "bancos": [{"codigo": c, "nombre": n} for c, n in BANCOS[iso]],
            "tipos_cuenta": [{"codigo": c, "nombre": n} for c, n in TIPOS_CUENTA],
            "documentos": [{"codigo": c, "nombre": n, "largos": list(l)} for c, n, l in DOCS[iso]],
            "tel_longitud": TEL_LONGITUD[iso],
            "moneda": MONEDA_POR_PAIS[iso],
            "cci": iso == "PE",
        }
        for iso in ("PE", "BO", "EC")
    }


def nombre_banco(pais: str, codigo: str) -> str:
    for c, n in BANCOS.get(pais, []):
        if c == codigo:
            return n
    return codigo or ""


# ── Validación (misma regla en app, web y backend: el backend manda) ────────

def _digitos(s: str | None) -> str:
    return re.sub(r"\D", "", str(s or ""))


def validar(b: dict) -> tuple[dict | None, str, str]:
    """Normaliza y valida el cuerpo de una cuenta de cobro. Devuelve
    (cuenta, error, campo). Nunca guarda texto libre salvo titular/números."""
    if not isinstance(b, dict):
        return None, "Datos inválidos.", ""
    pais = str(b.get("pais") or "PE").upper()
    if pais not in BANCOS:
        return None, "País no soportado.", "pais"
    tipo = str(b.get("tipo") or "").strip().lower()
    if tipo not in {c for c, _ in TIPOS[pais]}:
        return None, "Elige cómo quieres recibir tu plata.", "tipo"
    titular = re.sub(r"\s+", " ", str(b.get("titular") or "")).strip()[:80]
    if len(titular) < 3:
        return None, "Escribe el nombre del titular tal como figura en la cuenta.", "titular"
    doc_tipo = str(b.get("doc_tipo") or "").upper()
    docs = {c: l for c, _, l in DOCS[pais]}
    doc_numero = re.sub(r"[^0-9A-Za-z]", "", str(b.get("doc_numero") or "")).upper()[:15]
    if doc_tipo not in docs:
        return None, "Elige el tipo de documento del titular.", "doc_tipo"
    if len(doc_numero) not in docs[doc_tipo]:
        return None, "El número de documento no tiene el largo correcto.", "doc_numero"
    cuenta = {
        "pais": pais, "tipo": tipo, "titular": titular,
        "doc_tipo": doc_tipo, "doc_numero": doc_numero,
        "moneda": MONEDA_POR_PAIS[pais],
        "banco": "", "banco_nombre": "", "tipo_cuenta": "", "numero": "", "cci": "",
    }
    if tipo in ("yape", "plin"):
        cel = _digitos(b.get("numero"))
        if len(cel) != TEL_LONGITUD[pais] or not cel.startswith("9"):
            return None, f"El celular de {tipo.capitalize()} debe tener {TEL_LONGITUD[pais]} dígitos.", "numero"
        cuenta["numero"] = cel
        return cuenta, "", ""
    banco = str(b.get("banco") or "").upper()
    if banco not in {c for c, _ in BANCOS[pais]}:
        return None, "Elige el banco.", "banco"
    tipo_cuenta = str(b.get("tipo_cuenta") or "ahorros").lower()
    if tipo_cuenta not in {c for c, _ in TIPOS_CUENTA}:
        return None, "Elige el tipo de cuenta.", "tipo_cuenta"
    numero = _digitos(b.get("numero"))
    if not (8 <= len(numero) <= 20):
        return None, "El número de cuenta debe tener entre 8 y 20 dígitos.", "numero"
    cci = _digitos(b.get("cci"))
    if pais == "PE":
        # El CCI es lo que permite pagar desde OTRO banco (BCP → Interbank…).
        # Para cuentas del propio BCP no hace falta, pero si lo mandan se guarda.
        if banco != "BCP" and len(cci) != 20:
            return None, "El CCI (código interbancario) tiene 20 dígitos. Lo ves en tu app del banco.", "cci"
        if cci and len(cci) != 20:
            return None, "El CCI tiene 20 dígitos.", "cci"
        if banco == "BCP" and not (13 <= len(numero) <= 14):
            return None, "Una cuenta BCP tiene 13 o 14 dígitos.", "numero"
    cuenta.update({"banco": banco, "banco_nombre": nombre_banco(pais, banco),
                   "tipo_cuenta": tipo_cuenta, "numero": numero, "cci": cci})
    return cuenta, "", ""


def _ult(s: str, n: int = 4) -> str:
    return s[-n:] if len(s) > n else s


def resumen(c: dict | None) -> dict:
    """Vista corta para listas: etiqueta, si sirve para el archivo BCP, etc."""
    if not c:
        return {"tiene": False, "etiqueta": "Sin cuenta de cobro", "canal": "sin_cuenta"}
    tipo = c.get("tipo")
    if tipo in ("yape", "plin"):
        et = f"{tipo.capitalize()} {c.get('numero', '')} · {c.get('titular', '')}"
        return {"tiene": True, "etiqueta": et, "canal": "manual", "tipo": tipo,
                "numero": c.get("numero", ""), "titular": c.get("titular", ""), "pais": c.get("pais")}
    banco = c.get("banco_nombre") or c.get("banco") or ""
    if c.get("pais") == "PE":
        cta = c.get("cci") or c.get("numero") or ""
        et = f"{banco} {c.get('tipo_cuenta', '')} ****{_ult(c.get('numero', ''))}"
        if c.get("cci"):
            et += f" · CCI {c['cci']}"
        return {"tiene": True, "etiqueta": et + f" · {c.get('titular', '')}", "canal": "archivo",
                "tipo": "banco", "banco": c.get("banco"), "numero": c.get("numero", ""),
                "cci": c.get("cci", ""), "cuenta_pago": cta, "titular": c.get("titular", ""), "pais": "PE"}
    et = f"{banco} {c.get('tipo_cuenta', '')} {c.get('numero', '')} · {c.get('titular', '')}"
    return {"tiene": True, "etiqueta": et, "canal": "manual", "tipo": "banco", "banco": c.get("banco"),
            "numero": c.get("numero", ""), "titular": c.get("titular", ""), "pais": c.get("pais")}


# ── Lote de liquidación ──────────────────────────────────────────────────────

def armar_lote(pendientes: list[dict], cuentas: dict[str, dict], moneda: str = "PEN",
               umbral_centimos: int = 0) -> dict:
    """Agrupa las liquidaciones pendientes (dicts de `_liquidacion_dict` +
    `moneda`) por dueño en la MONEDA pedida. Cada fila lleva su canal:
    - `archivo`: cuenta bancaria peruana completa → entra al TXT de BCP.
    - `manual`: Yape/Plin u otro país → el operador la paga a mano.
    - `sin_cuenta`: el dueño aún no registró dónde cobrar.
    - `bajo_umbral`: neto acumulado menor al mínimo elegido (se posterga).
    """
    moneda = (moneda or "PEN").upper()
    por_dueno: dict[str, dict] = {}
    for p in pendientes:
        if (p.get("moneda") or "PEN").upper() != moneda:
            continue
        d = por_dueno.setdefault(p["dueno_id"], {"dueno": p["dueno_id"], "neto_centimos": 0, "n": 0,
                                                 "reserva_ids": [], "conceptos": []})
        d["neto_centimos"] += int(round(float(p["neto_soles"]) * 100))
        d["n"] += 1
        d["reserva_ids"].append(p["reserva_id"])
        if len(d["conceptos"]) < 3:
            d["conceptos"].append(p.get("concepto") or "")
    filas = []
    for dueno, d in sorted(por_dueno.items(), key=lambda kv: -kv[1]["neto_centimos"]):
        r = resumen(cuentas.get(dueno))
        canal = r["canal"]
        if d["neto_centimos"] < umbral_centimos:
            canal = "bajo_umbral"
        filas.append({**d, "cuenta": r, "cuenta_full": dict(cuentas.get(dueno) or {}), "canal": canal})
    tot = lambda canal: sum(f["neto_centimos"] for f in filas if f["canal"] == canal)  # noqa: E731
    return {
        "id": f"lote_{int(time.time() * 1000)}",
        "creado_en": datetime.now(timezone.utc).isoformat(),
        "moneda": moneda, "umbral_centimos": umbral_centimos,
        "estado": "preparado", "referencia": "",
        "filas": filas,
        "total_archivo_centimos": tot("archivo"),
        "total_manual_centimos": tot("manual"),
        "total_sin_cuenta_centimos": tot("sin_cuenta"),
        "total_bajo_umbral_centimos": tot("bajo_umbral"),
        "n_archivo": sum(1 for f in filas if f["canal"] == "archivo"),
    }


# ── Archivo Telecrédito BCP (pago a proveedores, ancho fijo) ────────────────

# Cada campo: (nombre, largo, alineación 'I'zquierda/'D'erecha, relleno).
# Numéricos a la derecha con ceros; alfanuméricos a la izquierda con espacios.
_CABECERA = [
    ("tipo_registro", 1, "I", " "),       # "1"
    ("cantidad_abonos", 6, "D", "0"),
    ("fecha_proceso", 8, "I", " "),       # AAAAMMDD
    ("tipo_cuenta_cargo", 1, "I", " "),   # C corriente · A ahorros · M maestra
    ("moneda_cargo", 4, "I", " "),        # 0001 soles · 1001 dólares
    ("cuenta_cargo", 20, "I", " "),
    ("importe_total", 17, "D", "0"),      # 15 enteros + 2 decimales, sin punto
    ("referencia", 40, "I", " "),
    ("checksum", 15, "D", "0"),           # suma de las cuentas de abono + cargo (15 últimos dígitos)
]
_DETALLE = [
    ("tipo_registro", 1, "I", " "),       # "2"
    ("tipo_cuenta_abono", 1, "I", " "),   # C/A cuenta BCP · B interbancaria (CCI)
    ("moneda_abono", 4, "I", " "),
    ("cuenta_abono", 20, "I", " "),
    ("tipo_doc", 1, "I", " "),            # 1 DNI · 4 CE · 6 RUC · 7 pasaporte
    ("numero_doc", 12, "I", " "),
    ("nombre", 75, "I", " "),
    ("referencia_abono", 40, "I", " "),
    ("referencia_beneficiario", 20, "I", " "),
    ("moneda_importe", 4, "I", " "),
    ("importe", 17, "D", "0"),
    ("validar_doc", 1, "I", " "),         # S/N: que el banco valide el documento del titular
    ("tipo_doc_pago", 1, "I", " "),       # D = otros
    ("numero_doc_pago", 20, "I", " "),
    ("fecha_doc_pago", 8, "I", " "),
]
_MONEDA_BCP = {"PEN": "0001", "USD": "1001"}
_DOC_BCP = {"DNI": "1", "CE": "4", "RUC": "6", "PASAPORTE": "7"}
_ASCII = str.maketrans("áéíóúÁÉÍÓÚñÑüÜ", "aeiouAEIOUnNuU")


def _campo(valor: str, largo: int, ali: str, relleno: str) -> str:
    v = str(valor or "").translate(_ASCII)
    v = re.sub(r"[^A-Za-z0-9 .,\-]", "", v)[:largo]
    return v.rjust(largo, relleno) if ali == "D" else v.ljust(largo, relleno)


def _linea(layout, valores: dict) -> str:
    return "".join(_campo(valores.get(n, ""), l, a, r) for n, l, a, r in layout)


def archivo_telecredito(lote: dict, cuenta_cargo: str, tipo_cargo: str = "C",
                        fecha: datetime | None = None, referencia: str = "") -> str:
    """TXT de Telecrédito (una línea por dueño con canal `archivo`). Solo PEN:
    la cuenta de cargo de EBIM está en soles; dólares se liquidan a mano."""
    filas = [f for f in lote.get("filas", []) if f.get("canal") == "archivo"]
    fecha = fecha or datetime.now(timezone.utc)
    ref = (referencia or f"PICHANGOL {fecha.strftime('%d/%m/%Y')}")[:40]
    moneda = _MONEDA_BCP.get((lote.get("moneda") or "PEN").upper(), "0001")
    cargo = _digitos(cuenta_cargo)
    lineas = []
    suma_cuentas = int(cargo or 0)
    total = 0
    for f in filas:
        c = f.get("cuenta_full") or {}
        es_bcp = c.get("banco") == "BCP"
        # Cuenta propia del BCP → su número (13/14 dígitos); otro banco → CCI.
        cuenta = c.get("numero") if es_bcp else c.get("cci")
        tipo_cta = ("A" if c.get("tipo_cuenta") == "ahorros" else "C") if es_bcp else "B"
        doc_tipo = _DOC_BCP.get(str(c.get("doc_tipo") or "DNI"), "1")
        suma_cuentas += int(_digitos(cuenta) or 0)
        total += f["neto_centimos"]
        lineas.append(_linea(_DETALLE, {
            "tipo_registro": "2", "tipo_cuenta_abono": tipo_cta, "moneda_abono": moneda,
            "cuenta_abono": cuenta, "tipo_doc": doc_tipo, "numero_doc": c.get("doc_numero", ""),
            "nombre": c.get("titular", ""), "referencia_abono": f"Liquidacion Pichangol {f['n']} pago(s)",
            "referencia_beneficiario": f["dueno"][:20], "moneda_importe": moneda,
            "importe": str(f["neto_centimos"]), "validar_doc": "S" if c.get("doc_numero") else "N",
            "tipo_doc_pago": "D", "numero_doc_pago": lote.get("id", "")[:20],
            "fecha_doc_pago": fecha.strftime("%Y%m%d"),
        }))
    cab = _linea(_CABECERA, {
        "tipo_registro": "1", "cantidad_abonos": str(len(filas)), "fecha_proceso": fecha.strftime("%Y%m%d"),
        "tipo_cuenta_cargo": (tipo_cargo or "C")[:1].upper(), "moneda_cargo": moneda,
        "cuenta_cargo": cargo, "importe_total": str(total), "referencia": ref,
        "checksum": str(suma_cuentas)[-15:],
    })
    return "\r\n".join([cab, *lineas]) + "\r\n"


def archivo_csv(lote: dict) -> str:
    """Respaldo universal: una fila por dueño con todo lo necesario para pagar
    a mano o importar en cualquier banca empresa."""
    sim = SIMBOLO.get(lote.get("moneda", "PEN"), "S/")
    out = ["dueno;canal;titular;documento;banco;tipo_cuenta;numero;cci;monto;pagos;conceptos"]
    for f in lote.get("filas", []):
        c = f.get("cuenta") or {}
        full = f.get("cuenta_full") or {}
        out.append(";".join(str(x).replace(";", ",") for x in (
            f["dueno"], f["canal"], c.get("titular", ""),
            f"{full.get('doc_tipo', '')} {full.get('doc_numero', '')}".strip(),
            c.get("banco") or c.get("tipo") or "", full.get("tipo_cuenta", ""),
            c.get("numero", ""), c.get("cci", ""), f"{sim} {f['neto_centimos'] / 100:.2f}",
            f["n"], " | ".join(f.get("conceptos") or []))))
    return "\n".join(out) + "\n"
