"""FOTOS PROPIAS OBLIGATORIAS AL RECLAMAR (decisión del director, 2-oct-2026:
"cuando se reclama una cancha, subir fotos propias debe ser una OBLIGACIÓN").

Por qué: los términos de Google no permiten guardar sus fotos; las fotos que
sube el dueño son las que quedan para siempre en la ficha y, además, prueban
que el local existe. Regla única para web, APK y torre:

- `minimo()` = `stores.config["reclamo_fotos_min"]` (default 3; 0 = apagado) y
  `maximo()` = `reclamo_fotos_max` (default 5, tope del formulario),
  editable en la torre (`/admin` → Reglas → "📷 Fotos propias al reclamar") y
  público en `GET /config/canal` (`reclamo_fotos_min`) para que el APK no lo
  tenga fijo.
- Una foto es PROPIA solo si es una URL pública de NUESTRO Supabase Storage,
  bucket `canchas`, en la carpeta de ESA cancha: `canchas/<id>/…` (galería,
  web y app) o `canchas/<id>.jpg` (portada del APK). Las hermanas de un mismo
  registro (`u<ts>_<deporte>`) comparten la carpeta `u<ts>`. Nunca cuentan
  Google / googleusercontent, otro bucket, la foto de EVIDENCIA
  (`canchas/ev<id>/`) ni carpetas de otra cosa (verif, validacion, bodega…).
- El candado REAL está en `reclamos.aprobar_directo / activar_admin /
  validar_en_sitio` (`gate`): los APK viejos no validan nada al enviar.
"""

from __future__ import annotations

import re
import urllib.parse

import config
from db.store import stores

CLAVE = "reclamo_fotos_min"
CLAVE_MAX = "reclamo_fotos_max"
DEFAULT = 3
DEFAULT_MAX = 5
MAXIMO = 8  # = catalogos.MAX_FOTOS (tope de la galería)

_RE_BASE = re.compile(r"^(u\d+)_")
_HOSTS_GOOGLE = ("google", "googleusercontent", "gstatic", "ggpht")
_PREFIJO_RUTA = "/storage/v1/object/public/canchas/"


def minimo() -> int:
    """Mínimo de fotos propias exigido para APROBAR un reclamo (0 = apagado)."""
    try:
        n = int(float(stores.cfg(CLAVE)))
    except (TypeError, ValueError):
        n = DEFAULT
    return max(0, min(MAXIMO, n))


def maximo() -> int:
    """Tope de fotos del FORMULARIO de reclamo (decisión del director,
    2-oct-2026: "3 a 5 fotos máximo"). Nunca menor que el mínimo ni mayor que
    la galería (8). Editar cancha fuera del reclamo sigue con su tope de 8."""
    try:
        n = int(float(stores.cfg(CLAVE_MAX)))
    except (TypeError, ValueError):
        n = DEFAULT_MAX
    return max(minimo(), 1, min(MAXIMO, n))


def set_minimo(n, maximo_nuevo=None) -> dict:
    try:
        v = int(n)
        mx = int(maximo_nuevo) if maximo_nuevo is not None else None
    except (TypeError, ValueError):
        return {"ok": False, "error": "minimo_invalido"}
    if v < 0 or v > MAXIMO:
        return {"ok": False, "error": "minimo_invalido", "max": MAXIMO}
    if mx is not None and (mx < max(1, v) or mx > MAXIMO):
        return {"ok": False, "error": "maximo_invalido", "max": MAXIMO}
    stores.config[CLAVE] = str(v)
    if mx is not None:
        stores.config[CLAVE_MAX] = str(mx)
    return {"ok": True, "minimo": minimo(), "maximo": maximo(), "max": MAXIMO}


def carpetas_de(cancha_id: str) -> set[str]:
    """Carpetas del bucket donde viven las fotos de ESTA cancha: su id y, para
    las hermanas de un mismo registro (`u<ts>_<deporte>`), la carpeta `u<ts>`."""
    cid = (cancha_id or "").strip()
    if not cid:
        return set()
    out = {cid}
    m = _RE_BASE.match(cid)
    if m:
        out.add(m.group(1))
    return out


def _carpeta_de_url(url: str) -> str | None:
    """Carpeta (o nombre de portada) de una URL pública del bucket `canchas`
    de NUESTRO Supabase; None si la URL no es de ahí."""
    u = str(url or "").strip()
    if not u:
        return None
    try:
        p = urllib.parse.urlsplit(u)
    except ValueError:
        return None
    if p.scheme not in ("https", "http") or not p.netloc:
        return None
    host = p.netloc.lower()
    if any(g in host for g in _HOSTS_GOOGLE):
        return None
    base = (config.SUPABASE_URL or "").strip()
    if base:
        if urllib.parse.urlsplit(base).netloc.lower() != host:
            return None
    elif not host.endswith(".supabase.co"):
        return None
    if not p.path.startswith(_PREFIJO_RUTA):
        return None
    resto = urllib.parse.unquote(p.path[len(_PREFIJO_RUTA):])
    if not resto or ".." in resto:
        return None
    partes = resto.split("/")
    if len(partes) == 1:  # portada del APK: canchas/<id>.jpg
        nombre = partes[0]
        return nombre.rsplit(".", 1)[0] if "." in nombre else None
    return partes[0] if partes[0] and partes[-1] else None


def es_foto_propia(url: str, cancha_id: str) -> bool:
    """¿La URL es una foto subida por el dueño a la carpeta de ESTA cancha?"""
    carpeta = _carpeta_de_url(url)
    return bool(carpeta) and carpeta in carpetas_de(cancha_id)


def propias(urls, cancha_id: str) -> list[str]:
    """Fotos propias (sin repetir, en orden) de una lista de URLs."""
    out: list[str] = []
    for u in urls or []:
        u = str(u or "").strip()
        if u and u not in out and es_foto_propia(u, cancha_id):
            out.append(u)
    return out


def de_cancha(c: dict | None) -> list[str]:
    """Fotos propias de una fila de `pichangol_canchas` (portada + galería)."""
    if not c:
        return []
    urls = [c.get("foto_url")] + list(c.get("fotos") or [])
    return propias(urls, str(c.get("id") or ""))


def faltan(c: dict | None) -> int:
    """Cuántas fotos propias le faltan a la cancha para el mínimo."""
    return max(0, minimo() - len(de_cancha(c)))


def estado(cancha_id: str) -> dict:
    """Fotos propias de la cancha reclamada según la NUBE. `conocido=False`
    cuando no hay base configurada (dev/tests): no se puede afirmar nada."""
    m = minimo()
    if m <= 0:
        return {"minimo": 0, "conocido": True, "n": 0, "faltan": 0, "fotos": [], "ok": True}
    from web import datos as _datos
    fotos = _datos.fotos_de_cancha(cancha_id)  # None = sin base; lanza si la base falló
    if fotos is None:
        return {"minimo": m, "conocido": False, "n": 0, "faltan": 0, "fotos": [], "ok": True}
    p = propias(fotos, cancha_id)
    return {"minimo": m, "conocido": True, "n": len(p), "faltan": max(0, m - len(p)),
            "fotos": p[:MAXIMO], "ok": len(p) >= m}


def estado_varios(cancha_ids: list[str]) -> dict[str, dict]:
    """`estado` de varias canchas con UNA consulta (lista de reclamos de la
    torre). Fail-safe: si la base falla devuelve {} y la tarjeta no pinta nada
    (el candado de `gate` igual bloquea al aprobar)."""
    m = minimo()
    ids = [i for i in dict.fromkeys(cancha_ids or []) if i]
    if m <= 0 or not ids:
        return {}
    from web import datos as _datos
    try:
        mapa = _datos.fotos_de_canchas(ids)
    except Exception as ex:  # noqa: BLE001
        print(f"[reclamo] no se pudieron leer fotos para la torre: {ex}", flush=True)
        return {}
    if mapa is None:
        return {}
    out = {}
    for cid in ids:
        p = propias(mapa.get(cid) or [], cid)
        out[cid] = {"minimo": m, "conocido": True, "n": len(p), "faltan": max(0, m - len(p)),
                    "fotos": p[:MAXIMO], "ok": len(p) >= m}
    return out


def gate(cancha_id: str) -> dict | None:
    """Candado de ACTIVACIÓN: error si la cancha no tiene el mínimo de fotos
    propias; None si pasa (o si no hay base configurada, como en dev/tests).
    Si la base FALLA se bloquea (no se activa a ciegas) y se puede reintentar."""
    if minimo() <= 0:
        return None
    try:
        e = estado(cancha_id)
    except Exception as ex:  # noqa: BLE001
        print(f"[reclamo] no se pudieron revisar las fotos de {cancha_id}: {ex}", flush=True)
        return {"ok": False, "error": "fotos_no_verificables",
                "mensaje": "No pudimos revisar las fotos del local en este momento. Inténtalo de nuevo."}
    if not e["conocido"]:
        print(f"[reclamo] fotos de {cancha_id}: sin base configurada, no se exige", flush=True)
        return None
    if e["ok"]:
        return None
    return {"ok": False, "error": "faltan_fotos_propias", "fotos_propias": e["n"],
            "minimo": e["minimo"], "faltan": e["faltan"],
            "mensaje": (f"Faltan fotos propias del local: tiene {e['n']} y se exigen {e['minimo']}. "
                        "Pídele al dueño que las suba desde Editar cancha (web o app).")}


def texto_faltan(n: int) -> str:
    return f"Sube {n} foto{'s' if n != 1 else ''} de tu local para que podamos aprobarlo"
