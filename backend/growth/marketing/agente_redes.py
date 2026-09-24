"""AGENTE DE MARKETING 24×7 de la página de Facebook de Pichangol.

Pedido del director (24-sep-2026): "agentes de marketing que vivan 24×7: un
creativo y un community manager que actúen como estratega comercial y de
marketing para impulsar Facebook, publicando todos los días a las 7:00 am:
primero promocionando Pichangol (que descarguen la app o reserven en la web) y
también incitando a los dueños de canchas a administrarlas con la solución".

Tres roles en un solo módulo, sin intervención manual:

* **Estratega** (`planificar`): calendario editorial SEMANAL configurable desde
  la torre (por día: audiencia jugadores/dueños + enfoque), rotación de locales
  destacados, memoria de lo publicado (enfoques y ganchos recientes) y un
  objetivo comercial explícito por audiencia (descargar la app / reservar en la
  web; registrar y administrar la cancha en Modo anfitrión).
* **Creativo** (`crear_pieza`): elige fotos reales del local del día (o la
  portada de marca si aún no hay locales con foto), pide el copy al redactor
  IA (`post_redes.redactar`, tono y enfoque del plan, sin repetir) y compone
  la pieza (`post_redes.componer`, 1080×1080).
* **Community manager** (`ejecutar` / `tick`): publica en la página a la HORA
  configurada (zona horaria del país, por defecto America/Lima 07:00) o deja
  un BORRADOR para que el operador lo apruebe (modo "aprobar"); una sola
  publicación por día (`agente_fb_ultimo_dia`), con bitácora de corridas.

El reloj lo mueve un cron del backend (`main.py`, cada 60 s → `tick()`); una
sola réplica en Railway. Todo es fail-safe: si falla la IA cae al banco de
variantes; si falla Facebook queda registrado en la bitácora y se reintenta
al día siguiente (o el operador aprueba a mano).
"""
from __future__ import annotations

import base64
import json
import os
import time
import uuid
from datetime import datetime, timedelta, timezone

import config
from db.store import stores

_DIR = os.path.dirname(os.path.abspath(__file__))
_STATIC = os.path.join(os.path.dirname(_DIR), "static", "brand")

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
AUDIENCIAS = {
    "jugadores": {
        "nombre": "Jugadores",
        "objetivo": ("Objetivo comercial: que quien lee DESCARGUE la app Pichangol (Android, Play Store: "
                     "https://play.google.com/store/apps/details?id=pe.ebim.pichangol) o RESERVE su cancha en la web "
                     "www.pichangol.app. Menciona una de las dos opciones de forma natural, no las dos como lista."),
    },
    "duenos": {
        "nombre": "Dueños de canchas",
        "objetivo": ("Objetivo comercial: que los DUEÑOS y administradores de canchas o academias registren su local y lo "
                     "administren GRATIS con Pichangol: agenda de reservas, cobros en línea, clientes nuevos. Se hace en "
                     "Modo anfitrión en www.pichangol.app o desde la app. Habla de igual a igual, como socio."),
    },
}
# Calendario editorial por defecto (índice = weekday(): 0 = lunes). 5 días a jugadores, 2 a dueños.
PLAN_DEFAULT = {
    "0": {"audiencia": "jugadores", "enfoque": "beneficio"},
    "1": {"audiencia": "duenos", "enfoque": "duenos"},
    "2": {"audiencia": "jugadores", "enfoque": "local"},
    "3": {"audiencia": "jugadores", "enfoque": "tip"},
    "4": {"audiencia": "jugadores", "enfoque": "finde"},
    "5": {"audiencia": "jugadores", "enfoque": "comunidad"},
    "6": {"audiencia": "duenos", "enfoque": "duenos"},
}
ENFOQUES_JUGADORES = ["beneficio", "local", "comunidad", "tip", "finde", "promo", "humor", "historia", "academia"]
ENFOQUES_DUENOS = ["duenos"]
CFG = {"activo": "agente_fb_activo", "hora": "agente_fb_hora", "zona": "agente_fb_zona", "modo": "agente_fb_modo",
       "tono": "agente_fb_tono", "plan": "agente_fb_plan", "ultimo_dia": "agente_fb_ultimo_dia", "ultimo_local": "agente_fb_ultimo_local"}
DEFAULTS = {"activo": "0", "hora": "07:00", "zona": "America/Lima", "modo": "auto", "tono": "cercano", "plan": "", "ultimo_dia": "", "ultimo_local": ""}
ZONAS = {"America/Lima": -5, "America/La_Paz": -4, "America/Guayaquil": -5}
MAX_BORRADORES = 14
MAX_CORRIDAS = 60


# ── configuración ─────────────────────────────────────────────────────────────
def _cfg(k: str) -> str:
    return str(stores.config.get(CFG[k], DEFAULTS[k]) or DEFAULTS[k])


def configuracion() -> dict:
    return {"activo": _cfg("activo") == "1", "hora": _cfg("hora"), "zona": _cfg("zona"), "modo": _cfg("modo") if _cfg("modo") in ("auto", "aprobar") else "auto",
            "tono": _cfg("tono"), "plan": plan(), "ultimo_dia": _cfg("ultimo_dia")}


def plan() -> dict:
    try:
        p = json.loads(_cfg("plan") or "{}") or {}
    except ValueError:
        p = {}
    out = {}
    for i in range(7):
        d = p.get(str(i)) or {}
        aud = d.get("audiencia") if d.get("audiencia") in AUDIENCIAS else PLAN_DEFAULT[str(i)]["audiencia"]
        enf = d.get("enfoque") or PLAN_DEFAULT[str(i)]["enfoque"]
        if aud == "duenos":
            enf = "duenos"
        elif enf not in ENFOQUES_JUGADORES + ["auto"]:
            enf = PLAN_DEFAULT[str(i)]["enfoque"]
        out[str(i)] = {"audiencia": aud, "enfoque": enf}
    return out


def guardar_configuracion(datos: dict) -> dict:
    """Valida y guarda lo que el operador cambió en la torre. Devuelve la config vigente."""
    if "activo" in datos:
        stores.config[CFG["activo"]] = "1" if datos.get("activo") else "0"
    if "hora" in datos:
        h = str(datos.get("hora") or "07:00")
        try:
            hh, mm = h.split(":")
            if not (0 <= int(hh) <= 23 and 0 <= int(mm) <= 59):
                raise ValueError
            stores.config[CFG["hora"]] = f"{int(hh):02d}:{int(mm):02d}"
        except ValueError:
            raise ValueError("Hora inválida; usa HH:MM (p. ej. 07:00).")
    if "zona" in datos:
        z = str(datos.get("zona") or "America/Lima")
        if z not in ZONAS:
            raise ValueError("Zona horaria no admitida (Lima, La Paz o Guayaquil).")
        stores.config[CFG["zona"]] = z
    if "modo" in datos:
        m = str(datos.get("modo") or "auto")
        if m not in ("auto", "aprobar"):
            raise ValueError("Modo inválido.")
        stores.config[CFG["modo"]] = m
    if "tono" in datos:
        from marketing import post_redes as _pr
        t = str(datos.get("tono") or "cercano")
        stores.config[CFG["tono"]] = t if t in _pr.TONOS else "cercano"
    if "plan" in datos and isinstance(datos.get("plan"), dict):
        actual = plan()
        nuevo = {}
        for i in range(7):
            d = datos["plan"].get(str(i)) or datos["plan"].get(i) or actual[str(i)]   # día no enviado = se conserva
            aud = d.get("audiencia") if d.get("audiencia") in AUDIENCIAS else actual[str(i)]["audiencia"]
            enf = str(d.get("enfoque") or actual[str(i)]["enfoque"] or "auto")
            nuevo[str(i)] = {"audiencia": aud, "enfoque": "duenos" if aud == "duenos" else (enf if enf in ENFOQUES_JUGADORES + ["auto"] else "auto")}
        stores.config[CFG["plan"]] = json.dumps(nuevo)
    return configuracion()


# ── reloj ────────────────────────────────────────────────────────────────────
def _tz(nombre: str):
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(nombre)
    except Exception:  # noqa: BLE001 — sin tzdata en la imagen: desplazamiento fijo (sin horario de verano en los 3 países)
        return timezone(timedelta(hours=ZONAS.get(nombre, -5)))


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def ahora_local() -> datetime:
    return _ahora().astimezone(_tz(_cfg("zona")))


def proxima_corrida() -> dict:
    """Cuándo toca la próxima publicación y qué dice el plan para ese día."""
    loc = ahora_local()
    hh, mm = [int(x) for x in _cfg("hora").split(":")]
    objetivo = loc.replace(hour=hh, minute=mm, second=0, microsecond=0)
    hoy_publicado = _cfg("ultimo_dia") == loc.strftime("%Y-%m-%d")
    pendiente_hoy = loc >= objetivo and not hoy_publicado      # el cron la hace en su próximo minuto (o el backend estuvo caído)
    if hoy_publicado:
        objetivo = objetivo + timedelta(days=1)
    p = plan()[str(objetivo.weekday())]
    meses = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
    return {"cuando": (loc if pendiente_hoy else objetivo).isoformat(), "dia": DIAS[objetivo.weekday()], "audiencia": p["audiencia"],
            "enfoque": p["enfoque"], "hoy_publicado": hoy_publicado, "pendiente_hoy": pendiente_hoy,
            "local": f"{DIAS[objetivo.weekday()]} {objetivo.day:02d}-{meses[objetivo.month - 1]} {objetivo.strftime('%H:%M')} ({_cfg('zona').replace('America/', '')})"}


# ── estratega ────────────────────────────────────────────────────────────────
def _locales() -> list[dict]:
    """Locales verificados con fotos reales (los que la torre ya lista), para destacar por rotación."""
    try:
        from propiedad.panel import _redes_canchas
        return [l for l in _redes_canchas() if l.get("fotos")]
    except Exception:  # noqa: BLE001
        return []


def _foto_marca() -> str:
    """Portada de marca como data URL (cuando aún no hay locales con foto)."""
    for nombre in ("portada_facebook.png", "logo_pichangol.png"):
        ruta = os.path.join(_STATIC, nombre)
        if os.path.exists(ruta):
            with open(ruta, "rb") as f:
                return "data:image/png;base64," + base64.b64encode(f.read()).decode()
    return ""


def planificar(fecha_local: datetime | None = None, *, audiencia: str | None = None, enfoque: str | None = None) -> dict:
    """El estratega decide el brief del día: audiencia, enfoque, local destacado, tono y objetivo."""
    loc = fecha_local or ahora_local()
    p = plan()[str(loc.weekday())]
    aud = audiencia if audiencia in AUDIENCIAS else p["audiencia"]
    enf = enfoque or p["enfoque"]
    if aud == "duenos":
        enf = "duenos"
    locales = _locales()
    local = None
    if locales:
        ultimo = _cfg("ultimo_local")
        ids = [l["canchas"][0]["id"] for l in locales]
        idx = (ids.index(ultimo) + 1) % len(ids) if ultimo in ids else 0
        local = locales[idx]
    verificados = len(locales)
    tema = AUDIENCIAS[aud]["objetivo"]
    if aud == "jugadores" and local:
        tema += f" Si encaja, menciona que {local['local']} ({local.get('zona') or 'la zona'}) ya se reserva ahí."
    if aud == "duenos" and verificados:
        tema += f" Dato real que puedes usar: ya hay {verificados} local{'es' if verificados != 1 else ''} con fotos publicando sus horarios."
    return {"fecha": loc.strftime("%Y-%m-%d"), "dia": DIAS[loc.weekday()], "audiencia": aud, "enfoque": enf, "tono": _cfg("tono"),
            "local": local, "tema": tema, "formato": "cuadrado"}


# ── creativo ─────────────────────────────────────────────────────────────────
def crear_pieza(brief: dict, *, evitar: list[str] | None = None) -> dict:
    """Copy con IA + composición de la imagen. Devuelve la receta (sin bytes) + `png`."""
    from marketing import post_redes as _pr
    local = brief.get("local") or {}
    cancha = local.get("muestra") if local else None
    fotos = list((local.get("fotos") or [])[:3]) if local else []
    if not fotos:
        marca = _foto_marca()
        fotos = [marca] if marca else []
    copy = _pr.redactar(cancha, brief.get("tono") or "cercano", brief.get("enfoque") or "auto", brief.get("tema") or "", evitar or [])
    etiqueta = copy.get("etiqueta") or ("Para dueños" if brief.get("audiencia") == "duenos" else "")
    png = _pr.componer(fotos, copy["titulo"] or "Pichangol", copy.get("subtitulo") or "", "www.pichangol.app", brief.get("formato") or "cuadrado", etiqueta)
    return {"fotos": fotos, "titulo": copy["titulo"], "subtitulo": copy.get("subtitulo", ""), "etiqueta": etiqueta, "texto": copy["texto"],
            "enfoque": copy.get("enfoque") or brief.get("enfoque"), "fuente": copy.get("fuente"), "tono": copy.get("tono"),
            "audiencia": brief.get("audiencia"), "local": local.get("local", "") if local else "", "local_id": (local["canchas"][0]["id"] if local else ""),
            "formato": brief.get("formato") or "cuadrado", "png": png}


def _receta(pieza: dict) -> dict:
    # las fotos data: (portada de marca) no se guardan en el snapshot: se marcan y se regeneran
    fotos = ["brand:portada" if u.startswith("data:") else u for u in pieza.get("fotos") or []]
    return {k: pieza[k] for k in ("titulo", "subtitulo", "etiqueta", "texto", "enfoque", "fuente", "tono", "audiencia", "local", "local_id", "formato") if k in pieza} | {"fotos": fotos}


def componer_receta(receta: dict) -> bytes:
    from marketing import post_redes as _pr
    fotos = [(_foto_marca() if u == "brand:portada" else u) for u in receta.get("fotos") or []]
    fotos = [u for u in fotos if u]
    return _pr.componer(fotos, receta.get("titulo") or "Pichangol", receta.get("subtitulo") or "", "www.pichangol.app", receta.get("formato") or "cuadrado", receta.get("etiqueta") or "")


# ── community manager ────────────────────────────────────────────────────────
def _estado() -> dict:
    a = stores.agente_fb
    a.setdefault("borradores", [])
    a.setdefault("corridas", [])
    return a


def _bitacora(**campos) -> None:
    a = _estado()
    a["corridas"].insert(0, {"en": time.time(), **campos})
    del a["corridas"][MAX_CORRIDAS:]


def _persistir() -> None:
    try:
        from pagos.router import _persistir_ahora
        _persistir_ahora()
    except Exception:  # noqa: BLE001
        pass


def _publicar_pieza(pieza: dict, receta: dict, *, origen: str) -> dict:
    from marketing import post_redes as _pr
    r = _pr.publicar_facebook(pieza["texto"].strip(), pieza["png"])
    _pr.registrar({"red": "facebook", "tipo": "foto", "plantilla": "agente", "enfoque": receta.get("enfoque", ""), "fuente": "agente",
                   "audiencia": receta.get("audiencia", ""), "local": receta.get("local", ""), "titulo": receta.get("titulo", ""),
                   "texto": pieza["texto"].strip()[:600], "fotos": len(receta.get("fotos") or []), "formato": receta.get("formato", "cuadrado"),
                   "ok": bool(r.get("ok")), "post_id": r.get("post_id", ""), "url": r.get("url", ""), "error": r.get("error", ""), "origen": origen})
    return r


def ejecutar(*, forzar: bool = False, publicar: bool | None = None, audiencia: str | None = None, enfoque: str | None = None) -> dict:
    """Corrida del día. `forzar` ignora hora/ya-publicado (botones de la torre);
    `publicar` fuerza publicar (True) o dejar borrador (False); None = según el modo."""
    from marketing import post_redes as _pr
    cfg = configuracion()
    loc = ahora_local()
    hoy = loc.strftime("%Y-%m-%d")
    if not forzar and cfg["ultimo_dia"] == hoy:
        return {"ok": False, "motivo": "ya_publicado_hoy"}
    debe_publicar = publicar if publicar is not None else (cfg["modo"] == "auto")
    if debe_publicar and not _pr.configurado():
        _bitacora(resultado="sin_credenciales", fecha=hoy)
        return {"ok": False, "motivo": "sin_credenciales"}
    brief = planificar(loc, audiencia=audiencia, enfoque=enfoque)
    evitar = [b.get("texto", "") for b in _estado()["borradores"]]
    try:
        pieza = crear_pieza(brief, evitar=evitar)
    except Exception as e:  # noqa: BLE001
        _bitacora(resultado="error_creativo", fecha=hoy, detalle=str(e)[:200], audiencia=brief["audiencia"], enfoque=brief["enfoque"])
        _persistir()
        return {"ok": False, "motivo": "error_creativo", "detalle": str(e)[:200]}
    receta = _receta(pieza)
    if brief.get("local"):
        stores.config[CFG["ultimo_local"]] = brief["local"]["canchas"][0]["id"]
    if debe_publicar:
        r = _publicar_pieza(pieza, receta, origen="agente_auto" if publicar is None else "torre")
        if r.get("ok"):
            stores.config[CFG["ultimo_dia"]] = hoy
            _bitacora(resultado="publicado", fecha=hoy, audiencia=receta["audiencia"], enfoque=receta["enfoque"], local=receta["local"],
                      titulo=receta["titulo"], url=r.get("url", ""), fuente=receta.get("fuente", ""))
            print(f"[agente] publicado {hoy} · {receta['audiencia']} · {receta['enfoque']} · {receta['titulo']!r}", flush=True)
            _persistir()
            return {"ok": True, "publicado": True, "url": r.get("url", ""), "receta": receta}
        _bitacora(resultado="error_facebook", fecha=hoy, detalle=str(r.get("error", ""))[:200], audiencia=receta["audiencia"], enfoque=receta["enfoque"])
        # Facebook rechazó: queda como borrador para que el operador lo apruebe cuando arregle el token.
        b = _guardar_borrador(receta, hoy, motivo=f"Facebook rechazó la publicación automática: {str(r.get('error', ''))[:160]}")
        _persistir()
        return {"ok": False, "motivo": "error_facebook", "detalle": r.get("error", ""), "borrador": b["id"]}
    b = _guardar_borrador(receta, hoy)
    stores.config[CFG["ultimo_dia"]] = hoy
    _bitacora(resultado="borrador", fecha=hoy, audiencia=receta["audiencia"], enfoque=receta["enfoque"], local=receta["local"], titulo=receta["titulo"], borrador=b["id"])
    print(f"[agente] borrador {hoy} · {receta['audiencia']} · {receta['enfoque']} · {receta['titulo']!r}", flush=True)
    _persistir()
    return {"ok": True, "publicado": False, "borrador": b, "receta": receta}


def _guardar_borrador(receta: dict, fecha: str, motivo: str = "") -> dict:
    a = _estado()
    b = {"id": "bor_" + uuid.uuid4().hex[:10], "creado_en": time.time(), "fecha": fecha, "motivo": motivo, **receta}
    a["borradores"].insert(0, b)
    del a["borradores"][MAX_BORRADORES:]
    return b


def borradores() -> list[dict]:
    return [dict(b) for b in _estado()["borradores"]]


def borrador(bid: str) -> dict | None:
    return next((dict(b) for b in _estado()["borradores"] if b.get("id") == bid), None)


def descartar_borrador(bid: str) -> bool:
    a = _estado()
    n = len(a["borradores"])
    a["borradores"] = [b for b in a["borradores"] if b.get("id") != bid]
    return len(a["borradores"]) < n


def editar_borrador(bid: str, **campos) -> dict | None:
    for b in _estado()["borradores"]:
        if b.get("id") == bid:
            for k in ("titulo", "subtitulo", "etiqueta", "texto"):
                if campos.get(k) is not None:
                    b[k] = str(campos[k])
            return dict(b)
    return None


def aprobar_borrador(bid: str) -> dict:
    """El operador aprueba: se compone la pieza de la receta y se publica."""
    b = borrador(bid)
    if not b:
        return {"ok": False, "error": "El borrador ya no existe."}
    png = componer_receta(b)
    r = _publicar_pieza({"texto": b.get("texto", ""), "png": png}, b, origen="aprobado")
    if r.get("ok"):
        descartar_borrador(bid)
        stores.config[CFG["ultimo_dia"]] = max(_cfg("ultimo_dia"), str(b.get("fecha") or ""))
        _bitacora(resultado="publicado", fecha=b.get("fecha", ""), audiencia=b.get("audiencia", ""), enfoque=b.get("enfoque", ""),
                  local=b.get("local", ""), titulo=b.get("titulo", ""), url=r.get("url", ""), origen="aprobado")
        return {"ok": True, "url": r.get("url", "")}
    return {"ok": False, "error": r.get("error", "Facebook rechazó la publicación")}


def regenerar_borrador(bid: str) -> dict | None:
    """Otra versión del mismo brief (misma audiencia), sin repetir la anterior."""
    b = borrador(bid)
    if not b:
        return None
    loc = ahora_local()
    brief = planificar(loc, audiencia=b.get("audiencia"), enfoque=None if b.get("audiencia") == "duenos" else "auto")
    if b.get("local_id"):
        brief["local"] = next((l for l in _locales() if l["canchas"][0]["id"] == b["local_id"]), brief.get("local"))
    pieza = crear_pieza(brief, evitar=[b.get("texto", "")] + [x.get("texto", "") for x in _estado()["borradores"]])
    receta = _receta(pieza)
    for i, x in enumerate(_estado()["borradores"]):
        if x.get("id") == bid:
            _estado()["borradores"][i] = {**x, **receta, "regenerado_en": time.time()}
            return dict(_estado()["borradores"][i])
    return None


def tick() -> bool:
    """Lo llama el cron cada 60 s. True si hizo algo que haya que persistir."""
    cfg = configuracion()
    if not cfg["activo"]:
        return False
    loc = ahora_local()
    hoy = loc.strftime("%Y-%m-%d")
    if cfg["ultimo_dia"] == hoy:
        return False
    hh, mm = [int(x) for x in cfg["hora"].split(":")]
    if (loc.hour, loc.minute) < (hh, mm):
        return False
    r = ejecutar()
    return bool(r.get("ok") or r.get("motivo") not in ("ya_publicado_hoy",))


def resumen() -> dict:
    """Todo lo que la torre muestra del agente."""
    from marketing import post_redes as _pr
    return {"config": configuracion(), "proxima": proxima_corrida(), "borradores": borradores(), "corridas": [dict(c) for c in _estado()["corridas"][:12]],
            "credenciales": _pr.configurado(), "ia": bool(config.ANTHROPIC_API_KEY), "locales": len(_locales()), "zonas": list(ZONAS),
            "audiencias": {k: v["nombre"] for k, v in AUDIENCIAS.items()}, "enfoques_jugadores": ["auto"] + ENFOQUES_JUGADORES, "dias": DIAS,
            "hora_local": ahora_local().strftime("%Y-%m-%d %H:%M")}
