"""Canchas DESCUBIERTAS en Google cerca del usuario, para la web (espejo de
`lib/services/places_service.dart`).

La web enseña el mismo mapa que el APK: además de las canchas registradas en
Pichangol, las que Google conoce alrededor (canchas, complejos, clubes) salen
con "Reservar en la app" y "¿Es tuya? Reclámala". Se consulta la MISMA Edge
Function de Supabase `places-cerca` que usa el app (la API key de Places vive
como secret de Supabase, no en Railway), y se aplica la MISMA heurística de
deporte/descartes (`docs/heuristica-deteccion-canchas.md`).

Caché en memoria por celda de ~2 km y país (6 h): una zona popular no dispara
12 consultas de Places por cada visitante. Fail-safe: sin Supabase, sin key o
con error de red → lista vacía (la web sigue mostrando las registradas).
"""

from __future__ import annotations

import json
import math
import re
import threading
import time
import unicodedata
import urllib.error
import urllib.request

import config

RADIO_M = 8000.0
TTL_SEG = 6 * 3600
MAX_RESULTADOS = 60

TIPOS_EXCLUIDOS = {
    "gym", "store", "shopping_mall", "clothing_store", "shoe_store", "sporting_goods_store",
    "school", "university", "lodging", "gas_station", "supermarket", "restaurant", "bar",
    "doctor", "hospital", "pharmacy", "bank",
}
PALABRAS_EXCLUIDAS = [
    "gimnasio", "gym", "tienda", "store", "colegio", "universidad", "federación", "federacion",
    "crossfit", "spinning", "natación", "natacion", "piscina", "billar", "bowling",
    "zapatilla", "zapato", "calzado", "sneaker", "sport wear", "sportwear", "deportes americano",
    "ropa deportiva", "boutique", "outlet", "sport center", "sports center", "sport centre",
    "sports centre", "sportcenter", "sport shop", "sports shop", "deportes en general",
    "skate", "patinaje", "patineta", "bmx", "atletismo", "loza deportiva municipal",
]
NOMBRE_FUERTE = ["complejo deportivo", "polideportivo", "centro deportivo", "club deportivo",
                 "campo deportivo", "villa deportiva", "estadio", "cancha", "canchita",
                 "grass sintétic", "grass sintetic"]
TIPOS_DEPORTIVOS = {"stadium", "arena", "sports_complex", "sports_club", "sports_activity_location",
                    "recreation_center", "athletic_field", "country_club"}
TIPOS_CAMPO = {"stadium", "arena", "sports_complex", "athletic_field", "country_club"}
TIPOS_GENERICOS = {"sports_activity_location", "recreation_center", "sports_club"}
FUTBOL = ["fútbol", "futbol", "pichang", "golazo", "fulbito", "futsal", "cancha", "canchita",
          "sintétic", "sintetic", "grass", "complejo deportivo", "club deportivo", "centro deportivo",
          "polideportivo", "country club", "club de campo", "club campestre", "regatas", "villa club",
          "golf club", "club de golf", "polo club", "lawn tennis", "sporting", "estadio"]


def deporte_de(nombre: str, tipos: list[str]) -> str | None:
    """Heurística de deporte por nombre/tipos (null = no es cancha de alquiler)."""
    n = (nombre or "").lower()
    tipos = [str(t) for t in (tipos or [])]
    fuerte = any(p in n for p in NOMBRE_FUERTE)
    excl = TIPOS_EXCLUIDOS - {"gym", "school", "university"} if fuerte else TIPOS_EXCLUIDOS
    if any(t in excl for t in tipos):
        return None
    if any(p in n for p in PALABRAS_EXCLUIDAS):
        return None
    tipos_dep = any(t in TIPOS_DEPORTIVOS for t in tipos)
    senal = fuerte or any(k in n for k in ("club", "academia", "court", "lawn", "sede", "country"))
    if "pickleball" in n or "pickle" in n:
        return "pickleball"
    if "pádel" in n or "padel" in n:
        return "padel"
    if any(k in n for k in ("vóley", "voley", "voleibol", "vóleibol", "volley")):
        return "voley"
    if any(k in n for k in ("básquet", "basquet", "básket", "basket")):
        return "basquet"
    if "raqueta" in n or "racquet" in n:
        return "tenis"
    if ("tenis" in n or "tennis" in n) and (senal or tipos_dep):
        return "tenis"
    if any(k in n for k in FUTBOL):
        return "futbol"
    if fuerte:
        return "futbol"
    if any(t in TIPOS_CAMPO for t in tipos):
        return "futbol"
    if any(t in TIPOS_GENERICOS for t in tipos) and senal:
        return "futbol"
    return None


def _clave(nombre: str) -> str:
    s = unicodedata.normalize("NFKD", (nombre or "").lower())
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]", "", s)


def _km(a_lat, a_lng, b_lat, b_lng) -> float:
    dlat = (a_lat - b_lat) * 111.0
    dlng = (a_lng - b_lng) * 111.0 * math.cos(math.radians(a_lat))
    return math.hypot(dlat, dlng)


def a_cancha(p: dict) -> dict | None:
    """Mapea un `place` de Google a la ficha mínima que muestra la web."""
    pid = p.get("id")
    nombre = ((p.get("displayName") or {}).get("text")) if isinstance(p.get("displayName"), dict) else p.get("displayName")
    loc = p.get("location") or {}
    try:
        lat, lng = float(loc.get("latitude")), float(loc.get("longitude"))
    except (TypeError, ValueError):
        return None
    if not pid or not nombre:
        return None
    dep = deporte_de(str(nombre), p.get("types") or [])
    if not dep:
        return None
    fotos = [str(u) for u in (p.get("fotos") or []) if str(u).startswith("http")]
    return {"id": f"gp_{pid}", "nombre": str(nombre), "direccion": p.get("formattedAddress") or "",
            "lat": lat, "lng": lng, "deporte": dep, "fotos": fotos[:3]}


def _llamar_edge(lat: float, lng: float, radio: float, region: str, fotos: bool) -> list[dict]:
    """POST a la Edge Function `places-cerca` (misma que el APK). Lanza en error."""
    base = (config.SUPABASE_URL or "").strip()
    if not base or not config.SUPABASE_ANON_KEY:
        return []
    if not base.startswith("http"):
        base = f"https://{base}"
    req = urllib.request.Request(
        f"{base}/functions/v1/places-cerca",
        data=json.dumps({"lat": lat, "lng": lng, "radius": radio, "fotos": fotos,
                         "region": region}).encode(),
        headers={"Content-Type": "application/json", "apikey": config.SUPABASE_ANON_KEY,
                 "Authorization": f"Bearer {config.SUPABASE_ANON_KEY}"},
        method="POST")
    with urllib.request.urlopen(req, timeout=25) as r:  # noqa: S310
        data = json.loads(r.read().decode("utf-8"))
    global ultimo_diag
    ultimo_diag = (data.get("diag") or data.get("error") or "") if isinstance(data, dict) else ""
    return list(data.get("places") or []) if isinstance(data, dict) else []


# Último `diag` que devolvió la Edge (estados/primer error de Google): se
# imprime en los logs de Railway para diagnosticar sin adivinar.
ultimo_diag: object = ""


def _http_json(url: str, headers: dict, body: dict | None = None, timeout: int = 12) -> dict:
    """GET/POST JSON a Google Places (New). Lanza en error HTTP/red."""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", **headers},
                                 method="POST" if data is not None else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310
        return json.loads(r.read().decode("utf-8"))


def _media_publica(nombre_foto: str, key: str) -> tuple[str, str]:
    """(URL pública sin key, error). `photoUri` con skipHttpRedirect."""
    try:
        j = _http_json(f"https://places.googleapis.com/v1/{nombre_foto}/media?maxWidthPx=800&skipHttpRedirect=true&key={key}", {})
        u = str(j.get("photoUri") or "")
        return (u, "") if u.startswith("http") else ("", f"sin photoUri: {str(j)[:120]}")
    except urllib.error.HTTPError as ex:
        try:
            cuerpo = ex.read().decode("utf-8", "ignore")[:160]
        except Exception:  # noqa: BLE001
            cuerpo = ""
        return "", f"HTTP {ex.code} {cuerpo}"
    except Exception as ex:  # noqa: BLE001
        return "", str(ex)[:160]


def _fotos_directo(place_id: str, nombre: str, club: str, lat: float, lng: float,
                   region: str) -> tuple[list[str], bool]:
    """Camino PRINCIPAL con `PLACES_API_KEY`: el backend habla con Google
    Places (New) con UNA llamada por lugar. Con `place_id` → Place Details
    (fotos); sin él → Text Search por nombre/club sesgado a 300 m y el más
    cercano (≤250 m), como `fotosDeLugar` del APK. Máximo 3 fotos, URLs
    públicas. Devuelve (fotos, ok): ok=False = error de red/cuota (no cachear)."""
    key = config.PLACES_API_KEY
    if not key:
        return [], False
    try:
        fotos_meta: list = []
        if place_id:
            j = _http_json(f"https://places.googleapis.com/v1/places/{place_id}",
                           {"X-Goog-Api-Key": key, "X-Goog-FieldMask": "photos"})
            fotos_meta = list(j.get("photos") or [])
        else:
            consulta = re.split(r"[–-]", club or nombre or "")[0].strip() or nombre
            j = _http_json("https://places.googleapis.com/v1/places:searchText",
                           {"X-Goog-Api-Key": key,
                            "X-Goog-FieldMask": "places.id,places.displayName,places.location,places.photos"},
                           {"textQuery": consulta, "languageCode": "es", "regionCode": region or "PE",
                            "maxResultCount": 10, "rankPreference": "DISTANCE",
                            "locationBias": {"circle": {"center": {"latitude": lat, "longitude": lng}, "radius": 300}}})
            mejor, mejor_d = None, 1e9
            for p in j.get("places") or []:
                loc = p.get("location") or {}
                try:
                    d = _km(lat, lng, float(loc.get("latitude")), float(loc.get("longitude")))
                except (TypeError, ValueError):
                    continue
                if (p.get("photos")) and d < mejor_d:
                    mejor, mejor_d = p, d
            if mejor is None or mejor_d > RADIO_FOTO_M / 1000.0 + 0.05:
                return [], True
            fotos_meta = list(mejor.get("photos") or [])
        out = []
        err_media = ""
        for ph in fotos_meta[:3]:
            nombre_foto = str((ph or {}).get("name") or "")
            if not nombre_foto:
                continue
            u, err = _media_publica(nombre_foto, key)
            if u:
                out.append(u)
            elif not err_media:
                err_media = err
        # Diagnóstico honesto: "0 fotos" puede ser que Google NO tiene fotos
        # del lugar (meta=0) o que el media falló (meta>0 + error).
        print(f"[foto] detalle {nombre!r}: meta={len(fotos_meta)} resueltas={len(out)}"
              f"{' media_error=' + err_media if err_media else ''}", flush=True)
        if fotos_meta and not out:
            return [], False  # había fotos y no se pudieron resolver: no cachear
        return out, True
    except urllib.error.HTTPError as ex:
        if ex.code == 429:
            _pausar_por_cuota()
        print(f"[foto] directo fallo {nombre!r}: HTTP {ex.code}", flush=True)
        return [], False
    except Exception as ex:  # noqa: BLE001
        print(f"[foto] directo fallo {nombre!r}: {ex}", flush=True)
        return [], False


_cache: dict[tuple, tuple[float, list[dict]]] = {}
_lock = threading.Lock()


def _celda(lat: float, lng: float) -> tuple[int, int]:
    return (math.floor(lat / 0.02), math.floor(lng / 0.02))


def descubrir_cerca(lat: float, lng: float, region: str = "PE", fotos: bool = False,
                    registradas: list[dict] | None = None) -> list[dict]:
    """Canchas de Google alrededor de (lat, lng), ya filtradas por la heurística,
    sin duplicar las REGISTRADAS en Pichangol (mismo nombre a <120 m), ordenadas
    por distancia. Con caché por celda/país/fotos."""
    try:
        lat, lng = float(lat), float(lng)
    except (TypeError, ValueError):
        return []
    key = (_celda(lat, lng), (region or "PE").upper(), bool(fotos))
    ahora = time.time()
    with _lock:
        hit = _cache.get(key)
    if hit and ahora - hit[0] < TTL_SEG:
        lista = hit[1]
    else:
        try:
            crudos = _llamar_edge(lat, lng, RADIO_M, (region or "PE").upper(), fotos)
        except Exception:  # noqa: BLE001
            crudos = []
        vistos: dict[str, dict] = {}
        for p in crudos:
            c = a_cancha(p) if isinstance(p, dict) else None
            if c:
                vistos[c["id"]] = c
        lista = list(vistos.values())
        with _lock:
            _cache[key] = (ahora, lista)
    # Quitar las que ya están registradas en Pichangol (por nombre + cercanía).
    reg = []
    for r in (registradas or []):
        claves = {_clave(r.get("nombre")), _clave(r.get("club"))} - {""}
        # Nombre del club sin el sufijo de sede ("Sabor Golazo - Futbol 7").
        claves |= {_clave(re.split(r"[–-]", str(r.get("club") or ""))[0])} - {""}
        reg.append((claves, float(r.get("lat") or 0), float(r.get("lng") or 0)))
    out = []
    for c in lista:
        k = _clave(c["nombre"])
        k0 = _clave(re.split(r"[–-]", c["nombre"])[0])
        if any((k in rk or k0 in rk) and _km(c["lat"], c["lng"], rl, rg) < 0.12 for rk, rl, rg in reg):
            continue
        c = dict(c)
        c["km"] = round(_km(lat, lng, c["lat"], c["lng"]), 2)
        out.append(c)
    out.sort(key=lambda c: c["km"])
    return out[:MAX_RESULTADOS]


# ── Primera foto de un lugar (como `enriquecerSembradas` del APK) ─────────────
#
# Las canchas SEMBRADAS desde el app (registradas a partir de un lugar de
# Google) no guardan las fotos de Google en la base (caducan y son de Google);
# el APK las resuelve en vivo por nombre + cercanía. La web hace lo mismo con
# la MISMA Edge Function: pide los lugares con foto en un radio corto alrededor
# de la cancha y se queda con el que mejor coincide por nombre (o el más
# cercano). Caché por lugar (las URLs `photoUri` duran horas).

RADIO_FOTO_M = 250.0
TTL_FOTO_SEG = 12 * 3600
_cache_fotos: dict[tuple, tuple[float, list[str]]] = {}
# CANDADOS DE CUOTA (trampa real, sep-2026): pedir la foto de cada tarjeta
# vía la Edge disparaba 12 Text Search por tarjeta → Google respondió 429
# "SearchTextRequest per minute" y nada tenía foto. Ahora: (1) por tarjeta,
# UNA llamada a Google (Place Details por id o un Text Search) y no la Edge;
# (2) máximo 3 resoluciones en paralelo en el servidor; (3) ante un 429 se
# PAUSAN las resoluciones 60 s y no se cachea el vacío (se reintenta luego).
_semaforo = threading.BoundedSemaphore(3)
_pausa_hasta = 0.0


def _en_pausa() -> bool:
    return time.time() < _pausa_hasta


def _pausar_por_cuota(seg: float = 60.0) -> None:
    global _pausa_hasta
    _pausa_hasta = max(_pausa_hasta, time.time() + seg)


def _tokens(s: str) -> set[str]:
    base = unicodedata.normalize("NFKD", (s or "").lower())
    base = "".join(ch for ch in base if not unicodedata.combining(ch))
    return {t for t in re.split(r"[^a-z0-9]+", base) if len(t) >= 3}


def _elegir_lugar(crudos: list[dict], nombre: str, club: str, lat: float, lng: float) -> list[str]:
    """Entre los `places` de Google alrededor, elige las fotos del que mejor
    coincide con la cancha: mayor coincidencia de palabras con el nombre/club
    (quitando el sufijo de sede tras '-'), y a igual puntaje el más cercano.
    Sin coincidencia de nombre, el lugar CON FOTOS más cercano (≤ 250 m)."""
    quiero = set()
    for n in (nombre, club):
        quiero |= _tokens(re.split(r"[–-]", n or "")[0])
    mejor: tuple[float, float] | None = None
    fotos_mejor: list[str] = []
    for p in crudos:
        if not isinstance(p, dict):
            continue
        fotos = [str(u) for u in (p.get("fotos") or []) if str(u).startswith("http")]
        if not fotos:
            continue
        dn = p.get("displayName")
        pn = dn.get("text") if isinstance(dn, dict) else dn
        loc = p.get("location") or {}
        try:
            d = _km(lat, lng, float(loc.get("latitude")), float(loc.get("longitude")))
        except (TypeError, ValueError):
            continue
        if d > RADIO_FOTO_M / 1000.0 + 0.05:
            continue
        coinc = len(quiero & _tokens(str(pn or ""))) if quiero else 0
        puntaje = (coinc, -d)
        if mejor is None or puntaje > mejor:
            mejor = puntaje
            fotos_mejor = fotos[:3]
    return fotos_mejor


def fotos_de_lugar(nombre: str, club: str, lat: float, lng: float, region: str = "PE",
                   place_id: str = "", cancha_id: str = "", forzar: bool = False) -> list[str]:
    """Fotos públicas de Google del lugar donde está la cancha (o [] si no
    hay). Primero la Edge Function (misma que el APK); si no trae fotos y hay
    `PLACES_API_KEY`, el backend las resuelve directo. Fail-safe y con caché."""
    try:
        lat, lng = float(lat), float(lng)
    except (TypeError, ValueError):
        return []
    if not lat and not lng:
        return []
    key = (round(lat, 4), round(lng, 4), _clave(nombre), _clave(club), place_id)
    ahora = time.time()
    with _lock:
        hit = None if forzar else _cache_fotos.get(key)
    if hit and ahora - hit[0] < TTL_FOTO_SEG:
        return list(hit[1])
    # COSECHA en Supabase (`pichangol_lugares_fotos`): se paga UNA vez por
    # lugar; pasados 30 días se refresca (y mientras tanto se usa lo guardado).
    from web import datos  # import perezoso (datos importa pg)
    clave_db = place_id or (f"cancha:{cancha_id}" if cancha_id else "")
    guardado = datos.leer_fotos_lugar(clave_db) if clave_db else None
    if guardado is not None and not forzar:
        fotos_db, vigente = guardado
        if vigente and (fotos_db or ahora - _sin_foto_visto.get(clave_db, 0) < 6 * 3600):
            with _lock:
                _cache_fotos[key] = (ahora, fotos_db)
            return list(fotos_db)
    if place_id and not forzar:
        with _lock:
            de_edge = _fotos_edge.get(place_id)
        if de_edge:
            with _lock:
                _cache_fotos[key] = (ahora, de_edge)
            return list(de_edge)
    if _en_pausa():
        return list(guardado[0]) if guardado else []  # cuota agotada hace poco: no insistir
    with _semaforo:
        if config.PLACES_API_KEY:
            fotos, ok = _fotos_directo(place_id, nombre, club, lat, lng, region)
            detalle = "directo"
        else:
            # Sin llave propia: UNA llamada a la Edge (12 Text Search) por lugar.
            try:
                crudos = _llamar_edge(lat, lng, RADIO_FOTO_M, (region or "PE").upper(), True)
                ok = True
            except Exception:  # noqa: BLE001
                crudos, ok = [], False
            fotos = _elegir_lugar(crudos, nombre, club, lat, lng)
            detalle = f"edge:lugares={len(crudos)} diag={str(ultimo_diag)[:160]!r}"
    print(f"[foto] {nombre!r} club={club!r} id={place_id or '-'} {detalle} "
          f"-> {'ok' if ok else 'ERROR'} ({len(fotos)} fotos)", flush=True)
    if ok:
        with _lock:
            # Sin fotos se cachea poco (10 min): el lugar puede no tener aún.
            _cache_fotos[key] = (ahora if fotos else ahora - TTL_FOTO_SEG + 600, fotos)
        if clave_db:
            datos.guardar_fotos_lugar(clave_db, nombre, lat, lng, fotos)
            if not fotos:
                _sin_foto_visto[clave_db] = ahora
    elif guardado:
        return list(guardado[0])  # error de red/cuota: lo guardado vale aunque esté viejo
    return fotos


# Fotos que la Edge ya trajo para un lugar (pagadas en el descubrimiento de la
# zona): se recuerdan en memoria y se cosechan en Supabase para que /web/foto
# no vuelva a preguntarle a Google por ese place_id.
_fotos_edge: dict[str, list[str]] = {}
_edge_cosechadas: set[str] = set()


def recordar_fotos_edge(c: dict) -> None:
    pid = str(c.get("id") or "")
    fotos = [str(u) for u in (c.get("fotos") or []) if str(u).startswith("http")]
    if not pid.startswith("gp_") or not fotos:
        return
    place_id = pid[3:]
    with _lock:
        _fotos_edge[place_id] = fotos[:3]
        nueva = place_id not in _edge_cosechadas
        _edge_cosechadas.add(place_id)
    if nueva:
        from web import datos
        datos.guardar_fotos_lugar(place_id, str(c.get("nombre") or ""), c.get("lat"), c.get("lng"), fotos[:3])


# Lugares que Google confirmó SIN fotos (para no volver a preguntar cada visita
# aunque la fila cosechada esté vacía): se reintenta cada 6 h.
_sin_foto_visto: dict[str, float] = {}


def limpiar_cache() -> None:
    with _lock:
        _cache.clear()
        _cache_fotos.clear()
        _sin_foto_visto.clear()
        _fotos_edge.clear()
        _edge_cosechadas.clear()
