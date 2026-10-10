"""JUEGA YA (fases 1 y 2, pedido del director, 10-oct-2026: "¿cómo hace una
persona que está sola y quiere jugar fútbol o tenis para buscar u organizar un
partido, o buscar un partner?").

Fuente ÚNICA de las reglas que comparten la web (`web/jugador_partidos.py`) y
el APK (`partidos_screen.dart` vía `/juego/*`):

· CATÁLOGOS (todo por selección, sin texto libre): tipo de publicación
  (`partido` = completar equipo · `partner` = busco compañero/rival en
  tenis/pickleball), modalidad de partner (Singles · Dobles · Pelotear),
  nivel (bandas sobre el nivel 1.0–7.0 de `pichangol_niveles`), etiquetas
  ("Cancha ya reservada", "Se divide la cancha", "Llevar pechera"…), franjas
  del día, días y radios de búsqueda.
· PREFERENCIAS DE JUEGO por correo (`stores.juego_prefs`, snapshot): deportes,
  radio (5/10/20/30 km), franjas, días, "Avísame partidos cerca" (push) y
  "Aparecer como disponible" (para que otros me encuentren como partner). La
  ubicación se guarda APROXIMADA (3 decimales ≈ 100 m) y NUNCA viaja a otros:
  solo la distancia redondeada.
· JUGADORES DISPONIBLES CERCA (`disponibles`): quienes se marcaron disponibles
  en ese deporte, dentro del radio de quien busca y del suyo.
· AVISOS DE PARTIDOS CERCA (`avisar_nuevos`, cron de 1 min en `main.py`): por
  cada partido NUEVO (creado en la app o en la web, también por APKs viejos,
  porque se lee de `pichangol_partidos`) se avisa por push a quienes lo
  pidieron y les calza: deporte, distancia ≤ su radio, franja, día y nivel; ni
  al creador ni a quien ya está en el partido; solo si faltan jugadores y
  empieza en más de 30 min. Idempotente por partido (`stores.juego_avisos`) y
  con TOPE DIARIO por persona (`juego_avisos_tope_dia`, 3) para que no sea spam.
"""

from __future__ import annotations

import math
import re
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Body, Header, HTTPException
from fastapi.responses import JSONResponse

import paises
from db import pg
from db.store import stores

# ── Catálogos ────────────────────────────────────────────────────────────────

DEPORTES_JUEGO = ["futbol", "tenis", "pickleball", "voley", "basquet"]   # = deportesActivos
DEPORTES_PARTNER = ["tenis", "pickleball"]                               # raqueta activos
RADIOS = [5, 10, 20, 30]
RADIO_DEFAULT = 10
TIPOS = ["partido", "partner"]

# Partner: (clave, etiqueta, jugadores en total incluyéndome).
MODALIDADES_PARTNER = [("singles", "Singles", 2), ("dobles", "Dobles", 4), ("pelotear", "Pelotear", 2)]

# Bandas de nivel sobre 1.0–7.0 (`Nivel.nivel`; sin fila = 3.0 → intermedio).
NIVELES = [
    ("inicial", "🌱 Principiante", 0.0, 2.5),
    ("intermedio", "⚡ Intermedio", 2.5, 4.0),
    ("avanzado", "🔥 Avanzado", 4.0, 5.5),
    ("competitivo", "🏆 Competitivo", 5.5, 99.0),
]
NIVEL_SIN_DATO = 3.0

# Etiquetas: clave → (emoji, texto, deportes donde aplica; None = todos).
ETIQUETAS: dict[str, tuple[str, str, list[str] | None]] = {
    "cancha_reservada": ("✅", "Cancha ya reservada", None),
    "se_divide": ("💵", "Se divide la cancha", None),
    "amistoso": ("🤝", "Amistoso, sin presión", None),
    "traer_pechera": ("🦺", "Llevar pechera", ["futbol"]),
    "falta_arquero": ("🧤", "Falta arquero", ["futbol"]),
    "llevo_pelotas": ("🎾", "Llevo pelotas", DEPORTES_PARTNER),
    "mixto": ("👫", "Mixto", None),
    "solo_mujeres": ("👩", "Solo mujeres", None),
    "mayores_35": ("🧓", "Mayores de 35", None),
}
MAX_ETIQUETAS = 4

# Franjas por la HORA de inicio (madrugada cuenta como noche).
FRANJAS = [("manana", "🌅 Mañana"), ("tarde", "☀️ Tarde"), ("noche", "🌙 Noche")]
DIAS = [("todos", "Cualquier día"), ("semana", "Lunes a viernes"), ("finde", "Fin de semana")]

PREFS_VIGENCIA_DIAS = 60      # un "disponible" que no abre la app en 60 días deja de salir
AVISO_MIN_ANTES_MIN = 30      # no se avisa un partido que empieza en menos de 30 min
VENTANA_NUEVOS_H = 6          # partidos creados en las últimas 6 h entran al barrido
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _low(s) -> str:
    return str(s or "").strip().lower()


def nivel_banda(n: float | None) -> str:
    v = NIVEL_SIN_DATO if n is None else float(n)
    for k, _, lo, hi in NIVELES:
        if lo <= v < hi:
            return k
    return NIVELES[-1][0]


def etiqueta_nivel(clave: str) -> str:
    return next((t for k, t, _, _ in NIVELES if k == clave), "Todos los niveles")


def franja_de(hora: str) -> str:
    try:
        h = int(str(hora)[:2])
    except ValueError:
        return "noche"
    if h < 6:
        return "noche"
    return "manana" if h < 12 else "tarde" if h < 18 else "noche"


def etiquetas_para(deporte: str) -> list[str]:
    return [k for k, (_, _, deps) in ETIQUETAS.items() if deps is None or deporte in deps]


def modalidad_partner(clave: str) -> tuple[str, str, int] | None:
    return next((m for m in MODALIDADES_PARTNER if m[0] == clave), None)


def km(a_lat, a_lng, b_lat, b_lng) -> float | None:
    try:
        la1, lo1, la2, lo2 = map(math.radians, (float(a_lat), float(a_lng), float(b_lat), float(b_lng)))
    except (TypeError, ValueError):
        return None
    d = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371.0 * 2 * math.asin(min(1.0, math.sqrt(d)))


def km_publico(d: float | None) -> float | None:
    """Distancia que ve otro usuario: redondeada a 0.5 km (nunca la ubicación)."""
    if d is None:
        return None
    return max(0.5, round(d * 2) / 2)


def config_publica() -> dict:
    """Catálogos para el APK y la web (`GET /juego/config`)."""
    return {
        "ok": True,
        "deportes": DEPORTES_JUEGO,
        "deportes_partner": DEPORTES_PARTNER,
        "radios": RADIOS,
        "radio_default": RADIO_DEFAULT,
        "modalidades_partner": [{"clave": k, "etiqueta": t, "cupos": n} for k, t, n in MODALIDADES_PARTNER],
        "niveles": [{"clave": k, "etiqueta": t, "min": lo, "max": hi} for k, t, lo, hi in NIVELES],
        "etiquetas": [{"clave": k, "emoji": em, "texto": tx, "deportes": deps or []}
                      for k, (em, tx, deps) in ETIQUETAS.items()],
        "max_etiquetas": MAX_ETIQUETAS,
        "franjas": [{"clave": k, "etiqueta": t} for k, t in FRANJAS],
        "dias": [{"clave": k, "etiqueta": t} for k, t in DIAS],
    }


# ── Validación de una publicación (web; el APK aplica las mismas reglas) ─────

def validar_extras(tipo: str, deporte: str, modalidad: str, nivel: str, etiquetas) -> tuple[dict | None, str]:
    """Tipo, modalidad, nivel y etiquetas de un partido nuevo."""
    tipo = tipo if tipo in TIPOS else "partido"
    if tipo == "partner":
        if deporte not in DEPORTES_PARTNER:
            return None, "Busco partner es para tenis y pickleball."
        if not modalidad_partner(modalidad):
            return None, "Elige si es singles, dobles o pelotear."
    else:
        modalidad = ""
    if nivel and nivel not in {k for k, *_ in NIVELES}:
        return None, "Nivel no válido."
    permitidas = set(etiquetas_para(deporte))
    ets: list[str] = []
    for x in etiquetas if isinstance(etiquetas, list) else []:
        x = str(x)
        if x in permitidas and x not in ets:
            ets.append(x)
    if len(ets) > MAX_ETIQUETAS:
        return None, f"Elige hasta {MAX_ETIQUETAS} detalles."
    if "solo_mujeres" in ets and "mixto" in ets:
        return None, "Elige “Mixto” o “Solo mujeres”, no ambos."
    return {"tipo": tipo, "modalidad": modalidad, "nivel": nivel, "etiquetas": ets}, ""


def texto_etiquetas(ets) -> str:
    return " · ".join(f"{ETIQUETAS[k][0]} {ETIQUETAS[k][1]}" for k in (ets or []) if k in ETIQUETAS)


# ── Preferencias de juego ────────────────────────────────────────────────────

def prefs_vacias() -> dict:
    return {"deportes": [], "radio_km": RADIO_DEFAULT, "franjas": [], "dias": "todos",
            "avisos": False, "disponible": False, "lat": None, "lng": None, "pais": "",
            "actualizado": ""}


def prefs_de(email: str) -> dict:
    p = stores.juego_prefs.get(_low(email))
    base = prefs_vacias()
    if p:
        base.update({k: p.get(k, base[k]) for k in base})
    base["tiene_ubicacion"] = base.get("lat") is not None and base.get("lng") is not None
    return base


def publicas(p: dict) -> dict:
    """Lo que vuelve al propio dueño de las preferencias (sin coordenadas)."""
    return {k: v for k, v in p.items() if k not in ("lat", "lng")}


def guardar_prefs(email: str, body: dict, nombre: str = "") -> dict:
    """Valida y guarda. ValueError con el mensaje para el usuario."""
    em = _low(email)
    if not _EMAIL_RE.match(em):
        raise ValueError("Correo inválido.")
    actual = prefs_de(em)
    deps = [d for d in (body.get("deportes") or []) if d in DEPORTES_JUEGO]
    deps = list(dict.fromkeys(deps))
    try:
        radio = int(body.get("radio_km") or RADIO_DEFAULT)
    except (TypeError, ValueError):
        radio = RADIO_DEFAULT
    if radio not in RADIOS:
        raise ValueError("Elige un radio de 5, 10, 20 o 30 km.")
    franjas = list(dict.fromkeys(f for f in (body.get("franjas") or []) if f in dict(FRANJAS)))
    dias = str(body.get("dias") or "todos")
    if dias not in dict(DIAS):
        raise ValueError("Elige los días.")
    avisos = bool(body.get("avisos"))
    disponible = bool(body.get("disponible"))
    lat, lng = body.get("lat"), body.get("lng")
    try:
        lat = None if lat in (None, "") else round(float(lat), 3)
        lng = None if lng in (None, "") else round(float(lng), 3)
    except (TypeError, ValueError):
        lat = lng = None
    if lat is not None and not (-90 <= lat <= 90 and -180 <= lng <= 180):
        lat = lng = None
    if lat is None:                       # sin ubicación nueva, conserva la guardada
        lat, lng = actual.get("lat"), actual.get("lng")
    if (avisos or disponible) and not deps:
        raise ValueError("Elige al menos un deporte.")
    if (avisos or disponible) and lat is None:
        raise ValueError("Necesitamos tu ubicación aproximada para buscar partidos y jugadores cerca de ti.")
    p = {"deportes": deps, "radio_km": radio, "franjas": franjas, "dias": dias,
         "avisos": avisos, "disponible": disponible, "lat": lat, "lng": lng,
         "pais": paises.pais_de_coordenadas(lat, lng) if lat is not None else "",
         "actualizado": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    if nombre:
        p["nombre"] = nombre[:60]
    stores.juego_prefs[em] = p
    return prefs_de(em)


def tocar(email: str, lat=None, lng=None) -> None:
    """El usuario abrió "Juega ya": renueva la vigencia (y la ubicación aprox.)."""
    em = _low(email)
    p = stores.juego_prefs.get(em)
    if not p:
        return
    try:
        if lat not in (None, "") and lng not in (None, ""):
            p["lat"], p["lng"] = round(float(lat), 3), round(float(lng), 3)
            p["pais"] = paises.pais_de_coordenadas(p["lat"], p["lng"])
    except (TypeError, ValueError):
        pass
    p["actualizado"] = datetime.now(timezone.utc).isoformat(timespec="seconds")


def _vigente(p: dict, ahora: datetime) -> bool:
    try:
        t = datetime.fromisoformat(str(p.get("actualizado") or ""))
    except ValueError:
        return False
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return ahora - t <= timedelta(days=PREFS_VIGENCIA_DIAS)


def niveles_de_varios(emails: list[str]) -> dict[tuple[str, str], float]:
    """{(correo, deporte): nivel} de `pichangol_niveles`. Fail-safe."""
    es = sorted({_low(x) for x in emails if x})
    if not pg.habilitado or not es:
        return {}
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT lower(email), deporte, nivel FROM pichangol_niveles WHERE lower(email) = ANY(%s)", (es,))
            return {(str(f[0]), str(f[1] or "")): float(f[2] or NIVEL_SIN_DATO) for f in cur.fetchall()}
    except Exception:  # noqa: BLE001
        return {}


def disponibles(email: str, deporte: str, lat, lng, radio_km: int | None = None,
                ahora: datetime | None = None) -> list[dict]:
    """Jugadores que se marcaron disponibles en `deporte`, a ≤ radio de quien
    busca y dentro del radio que ellos mismos eligieron. Devuelve correos (el
    llamador web los cambia por refs opacos) con nombre, foto, nivel y la
    distancia redondeada; nunca coordenadas."""
    yo = _low(email)
    ahora = ahora or datetime.now(timezone.utc)
    if deporte not in DEPORTES_JUEGO or lat in (None, "") or lng in (None, ""):
        return []
    radio = radio_km if radio_km in RADIOS else RADIO_DEFAULT
    cand: list[tuple[str, dict, float]] = []
    for em, p in stores.juego_prefs.items():
        if em == yo or not p.get("disponible") or deporte not in (p.get("deportes") or []):
            continue
        if not _vigente(p, ahora):
            continue
        d = km(lat, lng, p.get("lat"), p.get("lng"))
        if d is None or d > radio or d > float(p.get("radio_km") or RADIO_DEFAULT):
            continue
        cand.append((em, p, d))
    cand.sort(key=lambda x: x[2])
    cand = cand[:60]
    if not cand:
        return []
    from web.jugador_liga import perfiles
    pf = perfiles([c[0] for c in cand])
    nv = niveles_de_varios([c[0] for c in cand])
    out = []
    for em, p, d in cand:
        per = pf.get(em) or {}
        n = nv.get((em, deporte))
        out.append({"email": em, "nombre": (per.get("nombre") or p.get("nombre") or em.split("@")[0]).strip(),
                    "foto": per.get("foto_url") or "", "nivel": round(n, 1) if n is not None else None,
                    "banda": nivel_banda(n), "km": km_publico(d),
                    "franjas": list(p.get("franjas") or []), "dias": p.get("dias") or "todos"})
    return out


# ── Avisos de partidos cerca (fase 2) ────────────────────────────────────────

def _inicio_partido(p: dict) -> datetime | None:
    """Inicio del partido en UTC (hora local del país de su ubicación)."""
    try:
        f = date.fromisoformat(p["fecha"])
        hh, mm = int(p["hora"][:2]), int(p["hora"][3:5])
    except (KeyError, ValueError, TypeError):
        return None
    from web.horarios import _UTC_OFFSET
    iso = paises.pais_de_coordenadas(p.get("lat"), p.get("lng"))
    tz = timezone(timedelta(hours=_UTC_OFFSET.get(iso, -5)))
    return datetime(f.year, f.month, f.day, hh, mm, tzinfo=tz).astimezone(timezone.utc)


def _dia_ok(dias: str, fecha: str) -> bool:
    if dias not in ("semana", "finde"):
        return True
    try:
        wd = date.fromisoformat(fecha).weekday()
    except ValueError:
        return True
    return wd >= 5 if dias == "finde" else wd < 5


def candidatos(p: dict, ahora: datetime, niveles: dict | None = None) -> list[tuple[str, float]]:
    """A quién avisar de un partido: [(correo, km)] ordenado por distancia."""
    if p.get("lat") is None or p.get("lng") is None:
        return []
    if len(p.get("jugadores") or []) >= int(p.get("cupos") or 0):
        return []
    ini = _inicio_partido(p)
    if ini is None or ini - ahora < timedelta(minutes=AVISO_MIN_ANTES_MIN):
        return []
    roster = {_low(x) for x in (p.get("jugadores") or [])}
    creador = _low(p.get("creador_email"))
    franja = franja_de(p.get("hora") or "")
    nivel = p.get("nivel") or ""
    niveles = niveles or {}
    out = []
    for em, pr in stores.juego_prefs.items():
        if not pr.get("avisos") or em == creador or em in roster:
            continue
        if p.get("deporte") not in (pr.get("deportes") or []) or not _vigente(pr, ahora):
            continue
        fr = pr.get("franjas") or []
        if fr and franja not in fr:
            continue
        if not _dia_ok(pr.get("dias") or "todos", p.get("fecha") or ""):
            continue
        if nivel and nivel_banda(niveles.get((em, p.get("deporte")))) != nivel:
            continue
        d = km(p["lat"], p["lng"], pr.get("lat"), pr.get("lng"))
        if d is None or d > float(pr.get("radio_km") or RADIO_DEFAULT):
            continue
        out.append((em, d))
    out.sort(key=lambda x: x[1])
    return out


def _tope_dia() -> int:
    try:
        return max(0, int(stores.config.get("juego_avisos_tope_dia") or 3))
    except (TypeError, ValueError):
        return 3


def _cupo_aviso(email: str, hoy: str) -> bool:
    r = stores.juego_avisos_dia.get(email) or {}
    n = int(r.get("n") or 0) if r.get("dia") == hoy else 0
    return n < _tope_dia()


def _contar_aviso(email: str, hoy: str) -> None:
    r = stores.juego_avisos_dia.get(email) or {}
    n = int(r.get("n") or 0) if r.get("dia") == hoy else 0
    stores.juego_avisos_dia[email] = {"dia": hoy, "n": n + 1}


def texto_aviso(p: dict, d: float) -> tuple[str, str]:
    from web.jugador_partidos import fecha_legible
    faltan = max(0, int(p.get("cupos") or 0) - len(p.get("jugadores") or []))
    if p.get("tipo") == "partner":
        mod = modalidad_partner(p.get("modalidad") or "")
        dep = {"tenis": "tenis", "pickleball": "pickleball"}.get(p.get("deporte"), p.get("deporte"))
        titulo = f"🎾 Buscan partner de {dep} cerca"
        cuerpo = f"{(mod[1] if mod else 'Partido')} · {p.get('sede') or ''} · {fecha_legible(p['fecha'], p['hora'])}"
    else:
        titulo = f"⚽ Partido cerca: falta{'n' if faltan != 1 else ''} {faltan}"
        cuerpo = f"{p.get('titulo') or ''} · {fecha_legible(p['fecha'], p['hora'])}"
    if p.get("nivel"):
        cuerpo += f" · {etiqueta_nivel(p['nivel'])}"
    cuerpo += f" · a {km_publico(d):g} km"
    return titulo, cuerpo


def avisar_partido(p: dict, ahora: datetime | None = None, niveles: dict | None = None) -> int:
    """Avisa UNA vez un partido. Devuelve cuántos push se encolaron."""
    ahora = ahora or datetime.now(timezone.utc)
    pid = str(p.get("id") or "")
    if not pid or pid in stores.juego_avisos:
        return 0
    if str(stores.config.get("juego_avisos_activo", "1")) != "1":
        stores.juego_avisos[pid] = {"t": ahora.isoformat(timespec="seconds"), "n": 0, "nota": "apagado"}
        return 0
    cand = candidatos(p, ahora, niveles)
    from web.horarios import ahora_local
    from web.jugador_liga import aviso_push
    hoy = ahora_local("PE").date().isoformat()
    n = 0
    for em, d in cand:
        if not _cupo_aviso(em, hoy):
            continue
        t, c = texto_aviso(p, d)
        aviso_push(em, t, c, tipo="partido", data={"partido_id": pid, "tipo_partido": p.get("tipo") or "partido",
                                                   "deporte": p.get("deporte") or ""})
        _contar_aviso(em, hoy)
        n += 1
    stores.juego_avisos[pid] = {"t": ahora.isoformat(timespec="seconds"), "n": n}
    if n:
        print(f"[juego] partido {pid} avisado a {n} jugadores cerca", flush=True)
    return n


def _podar(ahora: datetime) -> None:
    lim = ahora - timedelta(days=7)
    for pid in [k for k, v in stores.juego_avisos.items()
                if (lambda t: t is None or t < lim)(_parse(v.get("t")))]:
        stores.juego_avisos.pop(pid, None)


def _parse(s) -> datetime | None:
    try:
        t = datetime.fromisoformat(str(s or ""))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def partidos_nuevos(ahora: datetime) -> list[dict]:
    """Partidos creados en las últimas `VENTANA_NUEVOS_H` horas y aún por jugar."""
    if not pg.habilitado:
        return []
    from web import jugador_partidos as JP
    return JP.partidos_creados_desde(ahora - timedelta(hours=VENTANA_NUEVOS_H),
                                     (ahora - timedelta(days=1)).date().isoformat())


def avisar_nuevos(ahora: datetime | None = None) -> int:
    """Barrido del cron: avisa los partidos nuevos que aún no se avisaron."""
    ahora = ahora or datetime.now(timezone.utc)
    if not stores.juego_prefs:
        return 0
    ps = [p for p in partidos_nuevos(ahora) if p.get("id") not in stores.juego_avisos]
    if not ps:
        _podar(ahora)
        return 0
    avisables = {em for em, pr in stores.juego_prefs.items() if pr.get("avisos")}
    niveles = niveles_de_varios(sorted(avisables)) if any(p.get("nivel") for p in ps) else {}
    n = sum(avisar_partido(p, ahora, niveles) for p in ps)
    _podar(ahora)
    return n


# ── API del APK (X-App-Key + identidad del usuario) ──────────────────────────

def _deps():
    from pagos.router import _APP
    return _APP


router = APIRouter(prefix="/juego", tags=["juega-ya"], dependencies=_deps())


def _auth(email: str, token: str | None) -> str:
    from pagos.router import _require_usuario
    em = _low(email)
    if not _EMAIL_RE.match(em):
        raise HTTPException(status_code=400, detail="Correo inválido.")
    _require_usuario(em, token)
    return em


@router.get("/config")
def get_config():
    return config_publica()


@router.get("/prefs")
def get_prefs(email: str, lat: float | None = None, lng: float | None = None,
              x_user_token: str | None = Header(default=None)):
    em = _auth(email, x_user_token)
    if em in stores.juego_prefs:
        tocar(em, lat, lng)        # renueva la vigencia de "disponible" (GET: persiste aparte)
        pg.persistir_en_segundo_plano(stores)
    return {"ok": True, "prefs": publicas(prefs_de(em))}


@router.post("/prefs")
def post_prefs(body: dict = Body(default_factory=dict), x_user_token: str | None = Header(default=None)):
    em = _auth(body.get("email"), x_user_token)
    try:
        p = guardar_prefs(em, body, str(body.get("nombre") or ""))
    except ValueError as ex:
        return JSONResponse({"ok": False, "mensaje": str(ex)}, status_code=400)
    return {"ok": True, "prefs": publicas(p)}


@router.get("/disponibles")
def get_disponibles(email: str, deporte: str, lat: float, lng: float, radio_km: int = RADIO_DEFAULT,
                    x_user_token: str | None = Header(default=None)):
    em = _auth(email, x_user_token)
    return {"ok": True, "jugadores": disponibles(em, deporte, lat, lng, radio_km)}
