"""GUARDRAILS: validación automática de cada pieza ANTES de que un humano (o el
modo automático) la apruebe. Principios 1-5 y 9 del agente:

* No se inventan precios, porcentajes, cifras, horarios, zonas, locales,
  promociones ni disponibilidad: TODO lo que el copy afirme tiene que estar en
  `hechos` (lo que el estratega sacó de la base).
* Un local solo se nombra si es `destacada` (dueño Pro + "destacar Pro").
* Arte IA = conceptual: nunca acompaña a una cancha concreta.
* Multi-país: moneda del país y nada de jerga peruana fuera de Perú.
* Sin datos personales (teléfonos, correos) ni enlaces que no sean el propio.
* Sin repetir lo reciente.

Se valida el texto COMPLETO (incluidos hashtags escritos a mano); solo se
apartan el enlace y los hashtags que agrega el código.

Devuelve `{"ok", "errores": [...], "avisos": [...]}`. Un solo error = REJECTED
(el operador puede editar la pieza y volver a validarla).
"""
from __future__ import annotations

import re

from marketing.agente_ia import zonas

_NUM = r"\d{1,3}(?:[.,]\d{3})+(?![\d])|\d+(?:[.,]\d{1,2})?"
_RE_DINERO = re.compile(
    rf"(?P<sim>S/\.?|Bs\.?|US\$|USD|PEN|BOB|\$)\s?(?P<v>{_NUM})"
    rf"|(?P<v2>{_NUM})\s?(?P<pal>soles?|bolivianos?|d[oó]lares|lucas|mangos|pesos|PEN|BOB|USD)\b", re.I)
_MONEDA = {"s/": "S/", "s/.": "S/", "pen": "S/", "sol": "S/", "soles": "S/", "lucas": "S/",
           "bs": "Bs", "bs.": "Bs", "bob": "Bs", "boliviano": "Bs", "bolivianos": "Bs",
           "$": "$", "us$": "$", "usd": "$", "dólares": "$", "dolares": "$"}
_RE_PCT = re.compile(rf"(?P<v>{_NUM})\s?(?:%|por\s?ciento|off\b)", re.I)
_RE_HORA = re.compile(r"\b([01]?\d|2[0-3])[:h]([0-5]\d)\b")
_RE_HORA_SUELTA = re.compile(r"\b([01]?\d|2[0-3])\s?(am|pm|a\.\s?m\.?|p\.\s?m\.?|hrs?\b|h\b|horas\b)", re.I)
_RE_NUM = re.compile(rf"(?<![\d.,])({_NUM})(?![\d%])")
_RE_URL = re.compile(r"https?://\S+|www\.\S+|\b[\w-]+(?:\.[\w-]+)*\.(?:com|pe|app|net|org|bo|ec|ly|me|link|co|io|info|biz)\b(?:/\S*)?", re.I)
_RE_PROMO = re.compile(r"\b(promo\w*|descuent\w*|dsc?to\w*|ofert\w*|rebaj\w*|liquidaci\w*|cup[oó]n\w*|hora feliz|happy hour|"
                       r"\d+\s?x\s?\d+|precio especial|mitad de precio|black friday|cyber\w*|off)\b", re.I)
_RE_GRATIS = re.compile(r"\b(gratis|gratuit\w*|sin costo|free|de regalo|regal(?:o|amos|an)\w*|cortes[ií]a|sin pagar)\b", re.I)
_RE_DISPONIBLE = re.compile(
    r"\b(hay|quedan|tenemos|todav[ií]a hay|a[uú]n hay)\b[^.\n]{0,60}\b(libres?|disponibles?|turnos?|horarios?|cupos?)\b"
    r"|\b(turnos?|canchas?|horarios?|cupos?|espacios?|lugares)\s+(libres?|disponibles?)\b"
    r"|\b[uú]ltimos?\s+(turnos?|cupos?|horarios?|lugares|espacios?)\b"
    r"|\b(libres?|disponibles?)\s+(hoy|ma[ñn]ana|esta noche|ahora|ya)\b", re.I)
_RE_LETRAS = re.compile(r"\b(un|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|once|doce|quince|veinte|treinta|cuarenta|"
                        r"cincuenta|sesenta|setenta|ochenta|noventa|cien|ciento|mil)\s+(soles?|lucas|bolivianos?|d[oó]lares|"
                        r"por\s?ciento|horas gratis)\b", re.I)
_RE_FONO = re.compile(r"(?<!\d)(?:\+?51\s?)?9\d{2}[\s-]?\d{3}[\s-]?\d{3}(?!\d)|(?<!\d)(?:\+?59[13]\s?)?[67]\d{7}(?!\d)|wa\.me", re.I)
_RE_MAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
# Medios con IA a partir de fotos reales del local (locales Pro): la pieza DEBE
# decirlo (transparencia con el público; también lo piden las reglas de Meta).
ORIGENES_IA_MEDIA = ("ia_ambientada", "video_ia")
AVISO_IA = "✨ Contenido creado con IA a partir de fotos reales del local."
_RE_FOTO_REAL = re.compile(r"\b(as[ií] luce|foto real|as[ií] es la cancha|mira c[oó]mo es)\b", re.I)
_SOLO_PE = re.compile(r"\b(yape|plin|soles?|lucas|PEN)\b|S/", re.I)
_PROPIO = re.compile(r"^(https?://)?(www\.)?pichangol\.app/?$", re.I)
_NOMBRES_GENERICOS = {"cancha", "club", "complejo", "complejo deportivo", "cancha sintetica", "la cancha", "canchas"}
MAX_SIMILITUD = 0.6


def _valor(x: str) -> str:
    """'80' '80.50' '1,200' '1.200' → forma canónica para comparar."""
    if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", x):
        return str(int(re.sub(r"[.,]", "", x)))
    f = float(x.replace(",", "."))
    return f"{f:.2f}".rstrip("0").rstrip(".")


def _nums_en(v) -> set[str]:
    """Todos los números que aparecen en los hechos (valores y textos)."""
    out: set[str] = set()
    if isinstance(v, bool) or v is None:
        return out
    if isinstance(v, (int, float)):
        return {_valor(f"{float(v):.2f}")}
    if isinstance(v, str):
        return {_valor(m) for m in re.findall(_NUM, v)}
    if isinstance(v, dict):
        for k, x in v.items():
            if k != "id":
                out |= _nums_en(x)
    if isinstance(v, (list, tuple, set)):
        for x in v:
            out |= _nums_en(x)
    return out


def _horas_en(v) -> set[str]:
    return {f"{int(h):02d}:{m}" for h, m in re.findall(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", str(v))}


def _precios(h: dict) -> set[str]:
    out = set()
    for c in [h.get("cancha")] + list(h.get("canchas") or []):
        if c and c.get("precio_hora"):
            out.add(_valor(f"{float(c['precio_hora']):.2f}"))
    p = h.get("promo") or {}
    if p.get("precio"):
        out.add(_valor(f"{float(p['precio']):.2f}"))
    return out


def _pcts(h: dict) -> set[str]:
    out = set()
    if (h.get("promo") or {}).get("pct"):
        out.add(_valor(str(h["promo"]["pct"])))
    if h.get("pct_max"):
        out.add(_valor(str(h["pct_max"])))
    return out


def _destacados(h: dict) -> set[str]:
    return {zonas.norm(c["nombre"]) for c in [h.get("cancha")] + list(h.get("canchas") or []) if c and c.get("nombre")}


def _palabras(t: str) -> set[str]:
    return {w for w in zonas.norm(re.sub(r"https?://\S+|#\w+", " ", t)).split() if len(w) > 3}


def _primera(t: str) -> str:
    return zonas.norm(next((l for l in str(t or "").splitlines() if l.strip()), ""))[:120]


def similitud(a: str, b: str) -> float:
    pa, pb = _palabras(a), _palabras(b)
    if not pa or not pb:
        return 0.0
    return len(pa & pb) / len(pa | pb)


def _zona_ok(clave: str, hechos: dict, pais: str) -> bool:
    permitida = zonas.norm(hechos.get("zona"))
    if not permitida:
        return False
    variantes = {permitida, zonas._ALIAS.get(permitida, permitida)}
    variantes |= {k for k, v in zonas._ALIAS.items() if v in variantes}
    variantes |= {zonas.norm(zonas.mostrar(v, pais)) for v in list(variantes)}
    return clave in variantes or zonas._ALIAS.get(clave, clave) in variantes


def validar(pieza: dict, hechos: dict, *, oportunidad: dict, media_origen: str | None = None,
            recientes: list[str] | None = None, locales_pais: list[str] | None = None, link: str | None = None) -> dict:
    """`pieza`: title, subtitle, etiqueta, body, call_to_action, hashtags.
    `locales_pais`: nombres de TODOS los locales registrados del país (para
    detectar un local mencionado que no está autorizado). `link`: el enlace
    propio de la pieza (el único permitido)."""
    errores: list[str] = []
    avisos: list[str] = []
    cuerpo = str(pieza.get("body") or "")
    texto = "\n".join([str(pieza.get(k) or "") for k in ("title", "subtitle", "etiqueta")] + [cuerpo, str(pieza.get("call_to_action") or "")])
    pais = str(hechos.get("pais") or "PE")
    moneda = hechos.get("moneda") or {"PE": "S/", "BO": "Bs", "EC": "$"}.get(pais, "S/")

    # Se apartan SOLO el enlace propio y los hashtags que puso el código; un
    # hashtag escrito a mano (#2x1, #Miraflores) se valida como texto.
    limpio = texto.replace(AVISO_IA, " ")
    if link:
        limpio = limpio.replace(link, " ")
    for tag in pieza.get("hashtags") or []:
        limpio = re.sub(rf"(?<!\w){re.escape(tag)}(?!\w)", " ", limpio)
    limpio = limpio.replace("#", " ")
    for m in _RE_URL.finditer(limpio):
        if not _PROPIO.match(m.group(0).rstrip(".,;:!?)")):
            errores.append(f"Contiene un enlace que no es el de la pieza: {m.group(0)[:60]}.")
    limpio = _RE_URL.sub(" ", limpio)

    if not oportunidad.get("objetivo") or not oportunidad.get("kpi"):
        errores.append("La pieza no tiene objetivo medible (regla fundamental).")
    if len(cuerpo.strip()) < 80:
        errores.append("El texto es demasiado corto.")
    if len(cuerpo) > 2200:
        errores.append("El texto supera 2.200 caracteres.")

    # Datos personales.
    if _RE_FONO.search(limpio) or _RE_MAIL.search(limpio) or _RE_MAIL.search(texto.replace(link or "\x00", " ")):
        errores.append("Contiene un teléfono o correo (datos personales).")

    # Dinero (monto Y moneda).
    precios = _precios(hechos)
    for m in _RE_DINERO.finditer(limpio):
        sim = (m.group("sim") or m.group("pal") or "").lower()
        if _MONEDA.get(sim) != moneda:
            errores.append(f"Moneda que no corresponde al país o al local: {m.group(0).strip()}.")
        elif _valor(m.group("v") or m.group("v2")) not in precios:
            errores.append(f"Monto no respaldado por los datos: {m.group(0).strip()}.")
    if _RE_LETRAS.search(limpio):
        errores.append(f"Cifra en letras no respaldada por los datos: {_RE_LETRAS.search(limpio).group(0)}.")
    # Porcentajes.
    pcts = _pcts(hechos)
    for m in _RE_PCT.finditer(limpio):
        if _valor(m.group("v")) not in pcts:
            errores.append(f"Porcentaje no respaldado por los datos: {m.group(0).strip()}.")
    # Horas (12:30, 20h00, 8pm, 10 am, 20h).
    horas_ok = _horas_en(hechos)
    for m in _RE_HORA.finditer(limpio):
        if f"{int(m.group(1)):02d}:{m.group(2)}" not in horas_ok:
            errores.append(f"Horario no respaldado por los datos: {m.group(0)}.")
    sin_horas = _RE_HORA.sub(" ", limpio)
    horas_enteras = {int(h[:2]) for h in horas_ok}
    for m in _RE_HORA_SUELTA.finditer(sin_horas):
        h, suf = int(m.group(1)), m.group(2).lower()
        if suf.startswith("horas") and m.group(1) and _valor(m.group(1)) in _nums_en(hechos):
            continue
        h24 = h + 12 if suf.startswith("p") and h < 12 else h
        if h24 not in horas_enteras:
            errores.append(f"Horario no respaldado por los datos: {m.group(0).strip()}.")
    # Otras cifras.
    resto = _RE_HORA_SUELTA.sub(" ", _RE_PCT.sub(" ", _RE_DINERO.sub(" ", sin_horas)))
    permitidos = _nums_en(hechos)
    for m in _RE_NUM.finditer(resto):
        if _valor(m.group(1)) not in permitidos:
            errores.append(f"Cifra no respaldada por los datos: {m.group(1)}.")
    # Zonas (de los tres países).
    for iso, clave, prep in zonas.mencionadas(limpio):
        nombre = zonas.mostrar(clave, iso)
        if not prep and (clave in zonas.AMBIGUAS or (clave not in zonas.metro(iso) and clave not in zonas.CIUDADES.get(iso, set())
                                                     and clave not in zonas._ALIAS.values())):
            continue
        if iso != pais:
            if clave in zonas._catalogo(pais) or clave in zonas.CIUDADES.get(pais, set()):
                continue                       # el mismo nombre existe en el país de la pieza
            errores.append(f"Menciona una zona de otro país: {nombre}.")
        elif clave in zonas.CIUDADES.get(pais, set()):
            # "Lima" como ciudad es genérico; otra ciudad solo si ES la zona de la pieza.
            if clave != "lima" and not _zona_ok(clave, hechos, pais):
                errores.append(f"Menciona una ciudad que no corresponde a los datos: {nombre}.")
        elif not _zona_ok(clave, hechos, pais):
            errores.append(f"Menciona una zona que no corresponde a los datos: {nombre}.")
    # Locales.
    autorizados = _destacados(hechos)
    n_limpio = zonas.norm(limpio)
    for nombre in locales_pais or []:
        nn = zonas.norm(nombre)
        if len(nn) < 5 or nn in _NOMBRES_GENERICOS or nn in autorizados:
            continue
        if re.search(rf"(?<![a-z0-9]){re.escape(nn)}(?![a-z0-9])", n_limpio):
            errores.append(f"Menciona un local no autorizado para publicidad: {nombre}.")
    # Promos y "gratis".
    if _RE_PROMO.search(limpio) and not hechos.get("promo"):
        errores.append("Habla de una promoción y no hay ninguna promoción vigente en los datos.")
    if _RE_GRATIS.search(limpio) and not hechos.get("registro_gratis"):
        errores.append("Dice 'gratis' (o similar) y eso solo está respaldado para el registro de dueños.")
    # Disponibilidad.
    if _RE_DISPONIBLE.search(limpio) and not hechos.get("dia"):
        errores.append("Afirma disponibilidad sin datos de turnos libres.")
    # Imagen IA.
    if media_origen == "ia_conceptual":
        if oportunidad.get("destacadas"):
            errores.append("Una imagen generada por IA no puede acompañar a una cancha concreta.")
        if _RE_FOTO_REAL.search(limpio):
            errores.append("El texto presenta como real una imagen conceptual.")
    if media_origen in ORIGENES_IA_MEDIA:
        if AVISO_IA not in cuerpo:
            errores.append("El contenido se creó con IA y el texto no lo dice (falta el aviso de IA).")
        if _RE_FOTO_REAL.search(limpio):
            errores.append("El texto presenta como foto sin retoque una imagen ambientada con IA.")
    # País.
    if pais != "PE" and _SOLO_PE.search(limpio):
        errores.append("Usa jerga o moneda de Perú en una pieza de otro país.")
    # Repetición.
    primera = _primera(cuerpo)
    for r in recientes or []:
        if primera and primera == _primera(r):
            errores.append("Empieza igual que una publicación reciente.")
            break
        if similitud(cuerpo, r) > MAX_SIMILITUD:
            errores.append("Es demasiado parecida a una publicación reciente.")
            break
    # Avisos (no bloquean).
    if len(pieza.get("hashtags") or []) > 8:
        avisos.append("Más de 8 hashtags.")
    if sum(1 for ch in texto if ord(ch) > 0x2500) > 5:
        avisos.append("Muchos emojis.")
    return {"ok": not errores, "errores": list(dict.fromkeys(errores)), "avisos": avisos}
