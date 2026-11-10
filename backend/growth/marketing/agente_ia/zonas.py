"""Zona (distrito / barrio) REAL de una cancha, sin inventarla.

`pichangol_canchas.distrito` suele venir vacío y `barrio` es texto libre, así
que la zona se deriva así, en orden:

1. `distrito` o `barrio`, si coinciden con un distrito del país (catálogo
   `web/geo/{pe,bo,ec}_geo.json`, el mismo de la web).
2. La dirección: se busca el distrito que aparece MÁS AL FINAL del texto (las
   direcciones terminan en "…, Distrito, Ciudad"; así "Av. La Molina 123, Ate"
   da Ate y no La Molina).
3. Si nada coincide → `None`. El agente NO menciona zona en ese caso.

Los nombres del catálogo vienen sin tildes en Perú; `_BONITO` los muestra bien
y `_CORTO` usa el nombre con que la gente los llama ("Surco").
"""
from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

_GEO = Path(__file__).resolve().parents[2] / "web" / "geo"

_BONITO = {
    "jesus maria": "Jesús María", "brena": "Breña", "rimac": "Rímac", "lurin": "Lurín", "ancon": "Ancón",
    "pachacamac": "Pachacámac", "san martin de porres": "San Martín de Porres",
    "villa maria del triunfo": "Villa María del Triunfo", "santa maria del mar": "Santa María del Mar",
    "mi peru": "Mi Perú", "santa maria de huachipa": "Santa María de Huachipa", "villa el salvador": "Villa El Salvador",
}
_CORTO = {"santiago de surco": "Surco", "magdalena del mar": "Magdalena", "carmen de la legua reynoso": "Carmen de la Legua"}
# Alias que la gente escribe → nombre del catálogo.
_ALIAS = {"surco": "santiago de surco", "smp": "san martin de porres", "sjl": "san juan de lurigancho",
          "sjm": "san juan de miraflores", "vmt": "villa maria del triunfo", "ves": "villa el salvador",
          "magdalena": "magdalena del mar", "cercado de lima": "lima"}
# Nombres que también son ciudad/provincia: solo valen si no hay otro distrito en el texto.
_GENERICOS = {"lima", "callao", "arequipa", "quito", "guayaquil", "la paz", "cochabamba", "santa cruz", "cuenca"}


def norm(t: str | None) -> str:
    t = unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", t)).strip()


@lru_cache(maxsize=4)
def _catalogo(iso: str) -> dict[str, str]:
    """norm(nombre) → nombre del catálogo, para el país."""
    f = _GEO / f"{iso.lower()}_geo.json"
    out: dict[str, str] = {}
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return out
    for provincias in data.values():
        for distritos in provincias.values():
            for d in distritos:
                n = norm(d)
                if len(n) >= 3:
                    out.setdefault(n, d)
    return out


def mostrar(clave_norm: str, iso: str = "PE") -> str:
    """Nombre para el copy (con tildes y forma corta)."""
    if clave_norm in _CORTO:
        return _CORTO[clave_norm]
    if clave_norm in _BONITO:
        return _BONITO[clave_norm]
    return _catalogo(iso).get(clave_norm, clave_norm.title())


def _directo(texto: str | None, iso: str) -> str | None:
    n = norm(texto)
    if not n:
        return None
    n = _ALIAS.get(n, n)
    return n if n in _catalogo(iso) else None


def _en_direccion(direccion: str | None, iso: str) -> str | None:
    n = norm(direccion)
    if not n:
        return None
    cat = _catalogo(iso)
    mejor: tuple[int, int, str] | None = None     # (posición final, largo, clave)
    for clave in list(cat) + list(_ALIAS):
        for m in re.finditer(rf"(?<![a-z0-9]){re.escape(clave)}(?![a-z0-9])", n):
            real = _ALIAS.get(clave, clave)
            cand = (m.end(), len(clave), real)
            if real in _GENERICOS:
                cand = (-1, len(clave), real)       # solo si no hay nada más específico
            if mejor is None or cand[:2] > mejor[:2]:
                mejor = cand
    return mejor[2] if mejor else None


def zona_de(c: dict, iso: str = "PE") -> str | None:
    """Clave normalizada de la zona real de la cancha, o None si no se sabe."""
    return (_directo(c.get("distrito"), iso) or _directo(c.get("barrio"), iso)
            or _en_direccion(c.get("direccion"), iso))


def todas(iso: str = "PE") -> list[str]:
    """Todos los nombres de zona del país (normalizados + alias), para que los
    guardrails detecten una zona mencionada en un copy."""
    return list(_catalogo(iso)) + [a for a in _ALIAS if len(a) > 3]


# ── zonas MENCIONADAS en un texto (para los guardrails) ───────────────────────
# Se buscan con MAYÚSCULA inicial (nombre propio) y sin tildes, en los
# catálogos de los TRES países: "en Miraflores" en una pieza de Bolivia o
# "Quito" en una de Perú también se detectan.
CIUDADES = {"PE": {"lima", "callao", "arequipa", "trujillo", "chiclayo", "piura", "cusco"},
            "BO": {"la paz", "el alto", "cochabamba", "santa cruz", "sucre"},
            "EC": {"quito", "guayaquil", "cuenca"}}
# Palabras comunes que también son distritos: solo cuentan tras "en/de/desde/por…".
AMBIGUAS = {"independencia", "la victoria", "victoria", "libertad", "esperanza", "progreso", "union", "la union", "florida",
            "bellavista", "alto", "paz", "santa rosa", "san luis", "primavera", "paraiso", "centro", "belen", "rosario", "carmen",
            "pampa", "sol", "mercedes", "fatima", "ascension", "la esperanza", "el progreso", "la libertad", "nueva esperanza",
            "porvenir", "el porvenir", "providencia", "la paz", "san jose", "santa ana", "san pedro", "san juan", "san pablo",
            "santiago", "san antonio", "san miguel", "san martin", "la merced", "merced", "cristo rey", "el carmen", "jesus",
            "san francisco", "san isidro", "santa maria", "el salvador", "magdalena", "huaca", "sucre", "bolivar", "chica"}
_ALIAS_TXT = {"Surco": "santiago de surco", "SJL": "san juan de lurigancho", "SMP": "san martin de porres",
              "SJM": "san juan de miraflores", "VMT": "villa maria del triunfo", "VES": "villa el salvador",
              "Magdalena": "magdalena del mar", "Cercado de Lima": "lima"}


def _sin_tildes(t: str) -> str:
    return unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode()


@lru_cache(maxsize=4)
def _patron(iso: str):
    nombres = {_sin_tildes(n): k for k, n in _catalogo(iso).items()}
    if iso == "PE":
        nombres.update(_ALIAS_TXT)
    for c in CIUDADES.get(iso, ()):
        nombres.setdefault(_sin_tildes(c).title().replace(" De ", " de ").replace(" La ", " la "), c)
    orden = sorted(nombres, key=len, reverse=True)
    rx = re.compile(r"(?<![\w])(" + "|".join(re.escape(n) for n in orden if len(n) >= 3) + r")(?![\w])")
    return rx, nombres


# Provincias metropolitanas donde opera Pichangol. Sin preposición ("Miraflores
# te espera") solo cuentan sus distritos: en el resto del país hay distritos que
# son palabras comunes con mayúscula inicial ("Arma el partido").
_METRO = {"PE": [("lima", "lima"), ("callao", "callao"), ("arequipa", "arequipa"), ("la libertad", "trujillo"),
                 ("lambayeque", "chiclayo"), ("piura", "piura"), ("cusco", "cusco")],
          "BO": [("la paz", "murillo"), ("cochabamba", "cercado"), ("santa cruz", "andres")],
          "EC": [("pichincha", "quito"), ("guayas", "guayaquil"), ("azuay", "cuenca")]}


@lru_cache(maxsize=4)
def metro(iso: str) -> frozenset[str]:
    try:
        data = json.loads((_GEO / f"{iso.lower()}_geo.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return frozenset()
    out = set()
    for dep, provincias in data.items():
        for prov, distritos in provincias.items():
            if any(norm(dep) == d and norm(prov).startswith(pr) for d, pr in _METRO.get(iso, [])):
                out |= {norm(x) for x in distritos}
    return frozenset(out)


def mencionadas(texto: str) -> list[tuple[str, str, bool]]:
    """[(iso, clave_norm, con_preposicion)] de cada zona nombrada en el texto."""
    t = _sin_tildes(texto)
    out = []
    for iso in ("PE", "BO", "EC"):
        rx, nombres = _patron(iso)
        for m in rx.finditer(t):
            antes = t[max(0, m.start() - 12):m.start()].lower()
            prep = bool(re.search(r"(?:\ben|\bde|\bdel|\bdesde|\bpor|\bpara|\bcerca de|\bcerca a|\bzona|\bdistrito de)\s+$", antes))
            out.append((iso, norm(nombres[m.group(1)]) if m.group(1) not in _ALIAS_TXT else _ALIAS_TXT[m.group(1)], prep))
    return out
