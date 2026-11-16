"""Canchas de OpenStreetMap: COMPLEMENTO permanente de Google Places (oct-2026).

Pedido del director: "siembra OSM solo con nombre … bajar costo lo máximo que se
pueda SIN QUE AFECTE LO ACTUAL". Google sigue siendo la fuente principal (a OSM
le faltan 27-41 % de los locales comerciales); OSM suma, gratis y para siempre
(licencia ODbL, con atribución "© colaboradores de OpenStreetMap"), las canchas
CON NOMBRE que Google no trajo.

Reglas:
  * Solo filas con nombre útil (se descartan "Cancha", "Losa deportiva 2"…) y
    un deporte que Pichangol soporte (tag `sport` de OSM o, si viene vacío, la
    MISMA heurística de nombres que `descubrir.deporte_de`).
  * Varias filas OSM del mismo nombre a ≤150 m = un solo local.
  * Google y las registradas GANAN siempre: una OSM a ≤150 m (o con el mismo
    nombre) de una de ellas no se muestra. Se agregan DESPUÉS de lo de Google,
    con su propio tope, así nunca desplazan un resultado de Google.
  * Una OSM nunca dispara llamadas a Google (ni fotos, ni Place Details).

Fuente: `web/osm_canchas.json.gz` (gzip de [lat, lng, sport, nombre, ciudad,
osm_id, leisure], generado por `tool/medicion_osm.py` en Actions). La web lo
lee en memoria; el backend lo siembra en `pichangol_canchas_osm` (para la Edge
`places-cerca`, que lo sirve al APK con `osm=1`) solo si la tabla está vacía o
el archivo cambió (`stores.config["osm_semilla_version"]`).
"""

from __future__ import annotations

import gzip
import hashlib
import json
import math
import os
import re
import threading
import unicodedata

ARCHIVO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "osm_canchas.json.gz")
ATRIBUCION = "© colaboradores de OpenStreetMap"
ATRIBUCION_URL = "https://www.openstreetmap.org/copyright"
AGRUPAR_M = 150.0      # mismo nombre a ≤150 m = un solo local
DEDUP_M = 150.0        # Google / registrada a ≤150 m gana
MAX_OSM = 40           # tope de OSM por respuesta (aparte del de Google)
LOTE = 500

# Tag `sport` de OSM → clave de deporte de Pichangol. "multi" no existe como
# deporte en el app: se infiere del nombre y, si no, fútbol (losa multiuso).
SPORT = {
    "soccer": "futbol", "futsal": "futbol", "football_5": "futbol", "5-a-side": "futbol",
    "7-a-side": "futbol", "five-a-side": "futbol", "six-a-side": "futbol", "seven-a-side": "futbol",
    "eight-a-side": "futbol", "fulbito": "futbol", "futbol": "futbol", "fútbol": "futbol",
    "football": "futbol",  # en LatAm casi siempre es fútbol mal etiquetado
    "tennis": "tenis", "padel": "padel", "paddle_tennis": "padel",
    "basketball": "basquet", "volleyball": "voley", "voleyball": "voley", "beachvolleyball": "voley",
    "ecuavoley": "voley",
    "pickleball": "pickleball",
}
MULTI = {"multi", "multisport", "de_todo"}

# Palabras que, solas, no identifican a ningún local ("Cancha 2", "Losa
# deportiva", "Campo de fútbol"). Un nombre hecho SOLO de estas (más números,
# letras sueltas o romanos) se descarta.
GENERICAS = {
    "cancha", "canchas", "canchita", "losa", "loza", "losas", "lozas", "deportiva", "deportivo",
    "deportivas", "deportivos", "multideportiva", "multideportivo", "multiuso", "multiusos",
    "recreativa", "recreativo", "campo", "campos", "futbol", "fulbito", "futsal", "football", "soccer",
    "tenis", "tennis", "padel", "voley", "voleibol", "volley", "volleyball", "basquet", "basket",
    "basketball", "basquetbol", "baloncesto", "pickleball", "court", "courts", "pitch", "field",
    "sintetica", "sintetico", "grass", "gras", "minifutbol", "mini", "estadio", "coliseo",
    "polideportivo", "complejo", "club", "centro", "plataforma", "playa", "parque", "municipal",
    "publica", "publico", "comunal", "vecinal", "de", "del", "la", "el", "los", "las", "y", "e",
    "en", "n", "no", "nro", "num", "numero", "sin", "nombre", "area", "zona", "espacio",
    "uso", "usos", "multiple", "multiples", "polifuncional", "deporte", "deportes", "basloncesto",
    "s", "sn",
}
_ROMANOS = re.compile(r"^(i{1,3}|iv|v|vi{0,3}|ix|x)$")

# Además de los descartes de `descubrir.deporte_de`, los del APK que importan
# en OSM (muchas canchas mapeadas son de colegios o lozas municipales).
EXCLUIDAS_EXTRA = [
    "loza deportiva", "losa deportiva", "loza multideportiva", "losa multideportiva",
    "loza recreativa", "losa recreativa", "loza multiuso", "losa multiuso",
    "institucion educativa", "i.e.", "i. e.", "iep ", "i.e.p", "colegio",
    "fitness", "wellness", "funcional", "baile", "danza", "yoga", "pilates", "karate",
    "taekwondo", "judo", "boxeo", "dojo", "ecuestre", "equitacion", "hipic", "golf",
    "skate", "bmx", "atletismo", "bike", "ciclismo", "piscina", "natacion",
    "frontón", "fronton", "bochas", "petanca", "beisbol", "béisbol", "baseball", "softbol",
    "cementerio", "iglesia", "parroquia", "cuartel", "comisaria", "comisaría",
    "toros", "paintball", "ajedrez", "escalada", "velodromo", "velódromo", "motocross", "karting",
]


def _sin_tildes(s: str) -> str:
    s = unicodedata.normalize("NFKD", (s or "").lower())
    return "".join(ch for ch in s if not unicodedata.combining(ch))


def clave(nombre: str) -> str:
    """Nombre normalizado para comparar (sin tildes, solo a-z0-9)."""
    return re.sub(r"[^a-z0-9]", "", _sin_tildes(nombre))


def nombre_util(nombre: str) -> bool:
    """¿El nombre identifica a un local? False para los genéricos sin valor."""
    n = re.sub(r"\s+", " ", (nombre or "")).strip()
    if len(clave(n)) < 3:
        return False
    tokens = [t for t in re.split(r"[^a-z0-9]+", _sin_tildes(n)) if t]
    utiles = [t for t in tokens
              if t not in GENERICAS and not t.isdigit() and len(t) > 1 and not _ROMANOS.match(t)]
    return bool(utiles)


def _excluido(nombre: str) -> bool:
    from web import descubrir
    n = (nombre or "").lower()
    s = _sin_tildes(nombre)
    if any(p in n or p in s for p in descubrir.PALABRAS_EXCLUIDAS):
        return True
    return any(p in n or p in s for p in EXCLUIDAS_EXTRA)


def deporte_osm(sport: str, nombre: str) -> str | None:
    """Clave de deporte de Pichangol para una fila OSM, o None si no se sabe /
    no es un deporte que Pichangol reserve (entonces se descarta la fila)."""
    from web import descubrir
    if _excluido(nombre):
        return None
    s = (sport or "").split(";")[0].strip().lower()
    if s in SPORT:
        return SPORT[s]
    if s in MULTI:
        return descubrir.deporte_de(nombre, []) or "futbol"
    if s:
        return None  # deporte que Pichangol no reserva (béisbol, frontón, ajedrez…)
    return descubrir.deporte_de(nombre, [])


def _m(a_lat, a_lng, b_lat, b_lng) -> float:
    dlat = (a_lat - b_lat) * 111000.0
    dlng = (a_lng - b_lng) * 111000.0 * math.cos(math.radians(a_lat))
    return math.hypot(dlat, dlng)


def procesar(filas: list) -> list[dict]:
    """Filas crudas del archivo → locales limpios, agrupados y con país."""
    from paises import pais_de_coordenadas
    candidatas = []
    for f in filas or []:
        try:
            lat, lng, sport, nombre = float(f[0]), float(f[1]), str(f[2] or ""), str(f[3] or "")
            ciudad = str(f[4] or "") if len(f) > 4 else ""
            osm_id = str(f[5] or "") if len(f) > 5 else ""
            leisure = str(f[6] or "") if len(f) > 6 else ""
        except (TypeError, ValueError, IndexError):
            continue
        nombre = re.sub(r"\s+", " ", nombre).strip()[:80]
        if not osm_id or not re.fullmatch(r"[nwr]\d+", osm_id) or not nombre_util(nombre):
            continue
        dep = deporte_osm(sport, nombre)
        if not dep:
            continue
        candidatas.append({"id": f"osm_{osm_id}", "nombre": nombre, "deporte": dep, "lat": round(lat, 6),
                           "lng": round(lng, 6), "ciudad": ciudad, "leisure": leisure})
    # Agrupar: mismo nombre a ≤150 m = un local. Representante: el complejo
    # (sports_centre) si lo hay; deporte = el más frecuente del grupo.
    grupos: dict[str, list[list[dict]]] = {}
    for c in candidatas:
        lst = grupos.setdefault(clave(c["nombre"]), [])
        for g in lst:
            if any(_m(c["lat"], c["lng"], x["lat"], x["lng"]) <= AGRUPAR_M for x in g):
                g.append(c)
                break
        else:
            lst.append([c])
    out = []
    for lst in grupos.values():
        for g in lst:
            rep = next((x for x in g if x["leisure"] == "sports_centre"), g[0])
            conteo: dict[str, int] = {}
            for x in g:
                conteo[x["deporte"]] = conteo.get(x["deporte"], 0) + 1
            dep = max(conteo, key=lambda k: (conteo[k], k == rep["deporte"]))
            out.append({**rep, "deporte": dep, "pais": pais_de_coordenadas(rep["lat"], rep["lng"])})
    out.sort(key=lambda c: c["id"])
    return out


# ── Carga en memoria (perezosa, una vez por proceso) ─────────────────────────
_lock = threading.Lock()
_datos: tuple[str, list[dict]] | None = None


def version_archivo(ruta: str | None = None) -> str:
    try:
        with open(ruta or ARCHIVO, "rb") as fh:
            return hashlib.sha256(fh.read()).hexdigest()[:16]
    except OSError:
        return ""


def cargar(ruta: str | None = None) -> tuple[str, list[dict]]:
    """(versión, locales). Sin archivo → ('', []): la web sigue igual que antes."""
    global _datos
    if ruta is None and _datos is not None:
        return _datos
    with _lock:
        if ruta is None and _datos is not None:
            return _datos
        try:
            with open(ruta or ARCHIVO, "rb") as fh:
                crudo = fh.read()
            filas = json.loads(gzip.decompress(crudo).decode("utf-8"))
            res = (hashlib.sha256(crudo).hexdigest()[:16], procesar(filas))
        except (OSError, ValueError) as ex:
            if not isinstance(ex, FileNotFoundError):
                print(f"[osm] no se pudo leer el archivo: {ex}", flush=True)
            res = ("", [])
        if ruta is None:
            _datos = res
        return res


def limpiar_cache() -> None:
    global _datos
    with _lock:
        _datos = None


def cerca(lat: float, lng: float, radio_m: float) -> list[dict]:
    """Locales OSM a ≤ `radio_m`, ordenados por distancia (con `km`)."""
    _, lista = cargar()
    if not lista:
        return []
    d = radio_m / 111000.0
    out = []
    for c in lista:
        if abs(c["lat"] - lat) > d or abs(c["lng"] - lng) > d * 2:
            continue
        m = _m(lat, lng, c["lat"], c["lng"])
        if m <= radio_m:
            out.append({**c, "km": round(m / 1000.0, 2)})
    out.sort(key=lambda c: c["km"])
    return out


def sin_duplicar(osm: list[dict], otros: list[dict], tope: int = MAX_OSM) -> list[dict]:
    """Quita las OSM que ya están en `otros` (Google, cosecha o registradas):
    a ≤150 m, o con el mismo nombre normalizado (con o sin sufijo de sede)."""
    ref = []
    for o in otros or []:
        try:
            la, ln = float(o.get("lat")), float(o.get("lng"))
        except (TypeError, ValueError):
            continue
        claves = set()
        for n in (o.get("nombre"), o.get("club")):
            if n:
                claves |= {clave(n), clave(re.split(r"[–-]", str(n))[0])}
        ref.append((claves - {""}, la, ln))
    out = []
    for c in osm:
        k = clave(c["nombre"])
        if any(_m(c["lat"], c["lng"], la, ln) <= DEDUP_M or k in ks for ks, la, ln in ref):
            continue
        out.append(c)
        if len(out) >= tope:
            break
    return out


def a_tarjeta(c: dict) -> dict:
    """Formato de una descubierta para el explorador web (sin fotos)."""
    return {"id": c["id"], "nombre": c["nombre"], "direccion": "", "lat": c["lat"], "lng": c["lng"],
            "deporte": c["deporte"], "fotos": [], "fuente": "osm", "km": c.get("km")}


# ── Siembra en Supabase (para la Edge `places-cerca`) ────────────────────────

def _stores():
    from db.store import stores
    return stores


def sembrar(ruta: str | None = None, forzar: bool = False) -> dict:
    """UPSERT del archivo en `pichangol_canchas_osm` si la tabla está vacía o
    la versión cambió. Idempotente, en lotes. Sin DATABASE_URL no hace nada."""
    from db import pg
    if not pg.habilitado:
        return {"ok": False, "motivo": "sin_base"}
    version, lista = cargar(ruta)
    if not version or not lista:
        return {"ok": False, "motivo": "sin_archivo"}
    st = _stores()
    previa = str((getattr(st, "config", {}) or {}).get("osm_semilla_version") or "")
    try:
        with pg._conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM pichangol_canchas_osm")
            n = int((cur.fetchone() or [0])[0] or 0)
            if n > 0 and previa == version and not forzar:
                return {"ok": True, "motivo": "al_dia", "filas": n}
            for i in range(0, len(lista), LOTE):
                cur.executemany(
                    "INSERT INTO pichangol_canchas_osm (id, nombre, deporte, lat, lng, ciudad, pais, leisure, "
                    "actualizado_en) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, now()) ON CONFLICT (id) DO UPDATE SET "
                    "nombre = excluded.nombre, deporte = excluded.deporte, lat = excluded.lat, lng = excluded.lng, "
                    "ciudad = excluded.ciudad, pais = excluded.pais, leisure = excluded.leisure, "
                    "actualizado_en = now()",
                    [(c["id"], c["nombre"], c["deporte"], c["lat"], c["lng"], c["ciudad"], c["pais"], c["leisure"])
                     for c in lista[i:i + LOTE]])
            # Lo que ya no está en el archivo (renombrado sin nombre útil, borrado en OSM) sale.
            cur.execute("DELETE FROM pichangol_canchas_osm WHERE NOT (id = ANY(%s))", ([c["id"] for c in lista],))
            borradas = cur.rowcount or 0
            conn.commit()
    except Exception as ex:  # noqa: BLE001
        print(f"[osm] siembra falló: {ex}", flush=True)
        return {"ok": False, "motivo": "error", "error": str(ex)[:200]}
    st.config["osm_semilla_version"] = version
    try:
        pg.persistir_en_segundo_plano(st)
    except Exception:  # noqa: BLE001
        pass
    print(f"[osm] sembradas {len(lista)} canchas (versión {version}, quitadas {borradas})", flush=True)
    return {"ok": True, "motivo": "sembrado", "filas": len(lista), "borradas": borradas, "version": version}


def iniciar_siembra_en_fondo() -> None:
    """Al arrancar: siembra en un hilo (nunca bloquea el arranque ni la web)."""
    def _correr():
        try:
            sembrar()
        except Exception as ex:  # noqa: BLE001
            print(f"[osm] siembra falló: {ex}", flush=True)
    threading.Thread(target=_correr, name="pcg-osm", daemon=True).start()
