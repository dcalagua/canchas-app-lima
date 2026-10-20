"""ORQUESTADOR del AI Marketing Agent: el ciclo diario y los controles humanos.

DATOS → ANÁLISIS → ESTRATEGIA → CONTENIDO → (validación) → APROBACIÓN →
PUBLICACIÓN → MÉTRICAS → APRENDIZAJE → nueva estrategia.

`tick()` lo llama un cron del backend cada 60 s (una réplica en Railway):

* a la `hora_plan` de cada país, una vez al día: snapshot + estrategia + piezas;
* cada minuto: publica lo APPROVED cuya hora llegó;
* cada hora: mide las ventanas de métricas vencidas;
* los lunes: recalcula los aprendizajes.

Modos (`ai_mkt_modo`):
* `aprobar` (por defecto): toda pieza válida queda PENDING_APPROVAL y la
  aprueba el operador en la torre.
* `auto_validado` (fase 6): la pieza que pasa TODOS los guardrails se aprueba
  sola, con tope diario (`ai_mkt_auto_max_dia`). `ai_mkt_pausa=1` es el freno
  de emergencia: no se publica nada.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from datetime import date, datetime, timedelta, timezone

import config
from db.store import stores
from marketing.agente_ia import aprendizaje, analitica, creador, creativo, datos, estratega, guardrails, publicador
from marketing.agente_ia.repo import ESTADOS, ahora, nuevo_codigo, nuevo_id, repo

ZONAS_PAIS = {"PE": "America/Lima", "BO": "America/La_Paz", "EC": "America/Guayaquil"}
_OFFSET = {"America/Lima": -5, "America/La_Paz": -4, "America/Guayaquil": -5}
CFG = {
    "activo": ("ai_mkt_activo", "0"), "modo": ("ai_mkt_modo", "aprobar"), "hora_plan": ("ai_mkt_hora_plan", "06:30"),
    "paises": ("ai_mkt_paises", "PE"), "posts_dia": ("ai_mkt_posts_dia", "1"), "umbral": ("ai_mkt_umbral", "15"),
    "mix_baja": ("ai_mkt_mix_baja", "0.7"), "mix_alta": ("ai_mkt_mix_alta", "0.3"), "arte_ia": ("ai_mkt_arte_ia", "0"),
    "destacar_pro": ("ai_mkt_destacar_pro", "0"), "tono": ("ai_mkt_tono", "cercano"), "plataformas": ("ai_mkt_plataformas", "facebook"),
    "auto_max_dia": ("ai_mkt_auto_max_dia", "2"), "pausa": ("ai_mkt_pausa", "0"), "ultimo_plan": ("ai_mkt_ultimo_plan", "{}"),
    "ultimo_aprendizaje": ("ai_mkt_ultimo_aprendizaje", ""), "ultima_medicion": ("ai_mkt_ultima_medicion", "0"),
    "reintento_plan": ("ai_mkt_reintento_plan", "{}"),
}
REINTENTO_PLAN_S = 30 * 60
EDITABLES = ("PENDING_APPROVAL", "REJECTED", "FAILED", "DRAFT", "APPROVED")
CANCELABLES = ("DRAFT", "PENDING_APPROVAL", "APPROVED", "FAILED", "REJECTED")
_lock = threading.Lock()
_plan_lock = threading.Lock()


# ── configuración ─────────────────────────────────────────────────────────────
def _cfg(k: str) -> str:
    clave, defecto = CFG[k]
    v = stores.config.get(clave)
    return defecto if v is None or str(v) == "" else str(v)


def _f(k: str, lo: float, hi: float) -> float:
    try:
        return max(lo, min(hi, float(_cfg(k))))
    except ValueError:
        return float(CFG[k][1])


def configuracion() -> dict:
    return {"activo": _cfg("activo") == "1", "modo": _cfg("modo") if _cfg("modo") in ("aprobar", "auto_validado") else "aprobar",
            "hora_plan": _cfg("hora_plan"), "paises": [p for p in _cfg("paises").split(",") if p in ZONAS_PAIS] or ["PE"],
            "posts_dia": int(_f("posts_dia", 1, 3)), "umbral": int(_f("umbral", 1, 200)), "mix_baja": _f("mix_baja", 0, 1),
            "mix_alta": _f("mix_alta", 0, 1), "arte_ia": _cfg("arte_ia") == "1", "destacar_pro": _cfg("destacar_pro") == "1",
            "tono": _cfg("tono") if _cfg("tono") in creador.TONOS else "cercano",
            "plataformas": [p for p in _cfg("plataformas").split(",") if p in ("facebook", "instagram")] or ["facebook"],
            "auto_max_dia": int(_f("auto_max_dia", 0, 5)), "pausa": _cfg("pausa") == "1"}


def guardar_configuracion(d: dict) -> dict:
    def _put(k, v):
        stores.config[CFG[k][0]] = v
    for k in ("activo", "arte_ia", "destacar_pro", "pausa"):
        if k in d:
            _put(k, "1" if d[k] else "0")
    if "modo" in d:
        if d["modo"] not in ("aprobar", "auto_validado"):
            raise ValueError("Modo inválido (aprobar | auto_validado).")
        _put("modo", d["modo"])
    if "hora_plan" in d:
        h = estratega._hora_ok(d["hora_plan"])
        if not h:
            raise ValueError("Hora inválida; usa HH:MM.")
        _put("hora_plan", h)
    if "paises" in d:
        ps = [p for p in (d["paises"] or []) if p in ZONAS_PAIS]
        if not ps:
            raise ValueError("Elige al menos un país (PE, BO, EC).")
        _put("paises", ",".join(ps))
    if "plataformas" in d:
        ps = [p for p in (d["plataformas"] or []) if p in ("facebook", "instagram")]
        if not ps:
            raise ValueError("Elige al menos una red (facebook, instagram).")
        _put("plataformas", ",".join(ps))
    for k, lo, hi in (("posts_dia", 1, 3), ("umbral", 1, 200), ("mix_baja", 0, 1), ("mix_alta", 0, 1), ("auto_max_dia", 0, 5)):
        if k in d:
            try:
                v = float(d[k])
            except (TypeError, ValueError):
                raise ValueError(f"Valor inválido para {k}.")
            if not lo <= v <= hi:
                raise ValueError(f"{k} debe estar entre {lo} y {hi}.")
            _put(k, str(int(v)) if k in ("posts_dia", "umbral", "auto_max_dia") else str(v))
    if "tono" in d:
        _put("tono", d["tono"] if d["tono"] in creador.TONOS else "cercano")
    if d.get("activo"):
        # Un solo agente publica en la página: el nuevo reemplaza al calendario fijo.
        stores.config["agente_fb_activo"] = "0"
    _persistir()
    return configuracion()


def _persistir() -> None:
    try:
        from pagos.router import _persistir_ahora
        _persistir_ahora()
    except Exception:  # noqa: BLE001
        pass


# ── reloj ────────────────────────────────────────────────────────────────────
def _tz(pais: str):
    nombre = ZONAS_PAIS.get(pais, "America/Lima")
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(nombre)
    except Exception:  # noqa: BLE001
        return timezone(timedelta(hours=_OFFSET[nombre]))


def ahora_local(pais: str) -> datetime:
    return ahora().astimezone(_tz(pais))


def _programar(fecha_local: date, hora: str, pais: str) -> datetime:
    hh, mm = (int(x) for x in hora.split(":"))
    dt = datetime(fecha_local.year, fecha_local.month, fecha_local.day, hh, mm, tzinfo=_tz(pais)).astimezone(timezone.utc)
    return max(dt, ahora() + timedelta(minutes=10))


# ── ciclo diario ─────────────────────────────────────────────────────────────
def snapshot(pais: str) -> dict:
    loc = ahora_local(pais)
    return datos.recolectar(pais=pais, hoy=loc.date(), ahora_min=loc.hour * 60 + loc.minute, destacar_pro=configuracion()["destacar_pro"])


def _recientes(dias: int = 14) -> list[dict]:
    out = []
    for c in repo().listar_contenidos(desde=ahora() - timedelta(days=dias), limite=60):
        if c["status"] in ("CANCELLED", "REJECTED"):
            continue
        op = c.get("oportunidad") or {}
        out.append({"id": c["id"], "strategy_id": c.get("strategy_id"), "op_id": op.get("id"), "tipo": op.get("tipo"),
                    "audiencia": c.get("audiencia"), "zona": op.get("zona"),
                    "fecha": str((c.get("scheduled_at") or c["created_at"]).date()), "body": c.get("body") or ""})
    return out


def _huella(texto: str) -> str:
    return hashlib.sha1(" ".join(texto.lower().split()).encode()).hexdigest()[:16]


def _aprobados_auto_hoy(pais: str) -> int:
    loc = ahora_local(pais)
    ini = datetime(loc.year, loc.month, loc.day, tzinfo=_tz(pais)).astimezone(timezone.utc)
    return sum(1 for c in repo().listar_contenidos(desde=ini, limite=100) if c.get("revisado_por") == "auto" and c.get("pais") == pais)


def crear_pieza(op: dict, s: dict, *, estrategia_id: str | None, campana_id: str | None, plataforma: str, fecha: date,
                recientes: list[dict], usar_ia: bool = True) -> dict:
    """Contenido + creativo + validación para UNA oportunidad. Guarda la pieza."""
    cfg = configuracion()
    pais = s["pais"]
    cid, codigo = nuevo_id("cnt"), nuevo_codigo()
    base = (config.PUBLIC_BASE_URL or "https://www.pichangol.app").rstrip("/")
    link = f"{base}/go/{codigo}"
    receta = creativo.elegir(op, s, permitir_ia=cfg["arte_ia"])
    locales = [c["club"] for c in s["canchas_lista"] if c.get("club")]
    p = creador.redactar(op, link=link, tono=cfg["tono"], plataforma=plataforma, recientes=[r["body"] for r in recientes],
                         locales_pais=locales, media_origen=receta["origen"], usar_ia=usar_ia, semilla=fecha.toordinal())
    v = p["validacion"]
    imagen = creativo.componer(receta, titulo=p["title"], subtitulo=p["subtitle"], etiqueta=p["etiqueta"])
    media_url = creativo.guardar(cid, imagen)
    estado = "PENDING_APPROVAL" if v["ok"] else "REJECTED"
    revisado = {}
    if v["ok"] and cfg["modo"] == "auto_validado" and _aprobados_auto_hoy(pais) < cfg["auto_max_dia"] and \
            (publicador.facebook_listo() if plataforma == "facebook" else publicador.instagram_listo()):
        estado, revisado = "APPROVED", {"revisado_por": "auto", "revisado_en": ahora()}
    destino = f"{base}/canchas" if op["audiencia"] == "jugadores" else f"{base}/anfitrion"
    oportunidad = {k: op.get(k) for k in ("id", "tipo", "objetivo", "kpi", "audiencia", "zona", "razon", "por_que", "content_type",
                                          "cancha_ids", "destacadas", "dia_objetivo", "franja", "enfoque", "puntaje",
                                          "fecha_objetivo", "vigente_hasta", "promo_tipo")}
    oportunidad["media"] = {k: v_ for k, v_ in receta.items() if not k.startswith("_")}
    hora = aprendizaje.hora_sugerida(op["audiencia"], repo().insights_vigentes(), op.get("hora") or estratega.HORA_DEFECTO[op["audiencia"]])
    c = {"id": cid, "codigo": codigo, "campaign_id": campana_id, "strategy_id": estrategia_id, "oportunidad": oportunidad,
         "content_type": op.get("content_type") if op.get("content_type") in estratega.TIPOS_CONTENIDO else "post",
         "platform": plataforma, "audiencia": op["audiencia"], "objetivo": op["objetivo"], "kpi": op["kpi"], "pais": pais,
         "zona": (op.get("hechos") or {}).get("zona"), "title": p["title"], "subtitle": p["subtitle"], "etiqueta": p["etiqueta"],
         "body": p["body"], "call_to_action": p["call_to_action"], "hashtags": p["hashtags"], "link_url": link, "destino_url": destino,
         "media_url": media_url, "media_origen": receta["origen"], "hechos": op.get("hechos") or {}, "validacion": v,
         "fuente": p["fuente"], "status": estado, "scheduled_at": _programar(fecha, hora, pais),
         "motivo_rechazo": "; ".join(v["errores"]) if not v["ok"] else None, "huella": _huella(p["body"]), "intentos": 0, **revisado}
    targets = [{"cancha_id": x, "rol": "destacada" if x in (op.get("destacadas") or []) else "evidencia"}
               for x in dict.fromkeys(list(op.get("destacadas") or []) + list(op.get("cancha_ids") or []))]
    guardado = repo().crear_contenido(c, targets)
    repo().log("creator", "pieza", content_id=cid, strategy_id=estrategia_id, estado=estado, fuente=p["fuente"],
               tipo=op.get("tipo"), errores=v["errores"])
    return guardado


def planificar(pais: str, *, forzar: bool = False, usar_ia: bool = True) -> dict:
    """Corrida del día para un país. Idempotente por (fecha, país) salvo `forzar`
    ("Correr ahora"), que reemplaza las piezas aún no aprobadas de ese día.
    Serializada con `_plan_lock` (el cron y la torre no corren a la vez)."""
    if not _plan_lock.acquire(timeout=120):
        return {"ok": False, "motivo": "en_curso"}
    try:
        return _planificar(pais, forzar=forzar, usar_ia=usar_ia)
    finally:
        _plan_lock.release()


def _planificar(pais: str, *, forzar: bool, usar_ia: bool) -> dict:
    cfg = configuracion()
    loc = ahora_local(pais)
    hoy = loc.date()
    previa = repo().estrategia_de(hoy, pais)
    if previa and not forzar:
        return {"ok": False, "motivo": "ya_planificado", "estrategia": previa}
    if previa:
        for viejo in repo().listar_contenidos(estados=("DRAFT", "PENDING_APPROVAL", "REJECTED"), limite=200):
            if viejo.get("strategy_id") == previa["id"]:
                repo().cambiar_estado(viejo["id"], ("DRAFT", "PENDING_APPROVAL", "REJECTED"), "CANCELLED",
                                      motivo_rechazo="Reemplazada por una nueva corrida del día.")
    t0 = time.time()
    s = snapshot(pais)
    insights = repo().insights_vigentes()
    recientes = _recientes()
    dec = estratega.decidir(s, insights=insights, recientes=recientes, n=cfg["posts_dia"], umbral=cfg["umbral"],
                            mix_duenos_baja=cfg["mix_baja"], mix_duenos_alta=cfg["mix_alta"], dia_rotacion=hoy.toordinal(),
                            usar_ia=usar_ia)
    snap_guardar = {k: v for k, v in s.items() if k not in ("canchas_lista", "libres_por_cancha")}
    snap_guardar["canchas_lista"] = [{k: c[k] for k in ("id", "club", "zona_nombre", "reservable", "destacable")} for c in s["canchas_lista"]]
    e = repo().guardar_estrategia({"id": (previa or {}).get("id"), "fecha": hoy, "pais": pais, "snapshot": snap_guardar,
                                   "candidatas": [{k: c.get(k) for k in ("id", "tipo", "objetivo", "kpi", "audiencia", "razon", "puntaje", "hechos")}
                                                  for c in dec["candidatas"]],
                                   "oportunidades": [{k: o.get(k) for k in ("id", "tipo", "objetivo", "kpi", "audiencia", "razon", "por_que", "hora", "content_type")}
                                                     for o in dec["elegidas"]],
                                   "insights_usados": [i["id"] for i in insights[:10]], "fuente": dec["fuente"]})
    repo().log("strategist", "estrategia", strategy_id=e["id"], pais=pais, fuente=dec["fuente"], candidatas=len(dec["candidatas"]),
               elegidas=[o["tipo"] for o in dec["elegidas"]], baja_densidad=dec["baja_densidad"])
    piezas = []
    for op in dec["elegidas"]:
        semana = hoy - timedelta(days=hoy.weekday())
        campana = repo().campana_asegurar(nombre=f"{op['objetivo'].replace('_', ' ').capitalize()} · {op['audiencia']}"
                                          f"{(' · ' + op['hechos']['zona']) if op['hechos'].get('zona') else ''} · semana {semana.isoformat()}",
                                          objetivo=op["objetivo"], audiencia=op["audiencia"], pais=pais, zona=op.get("zona"), kpi=op["kpi"],
                                          inicio=semana, fin=semana + timedelta(days=6))
        for plataforma in cfg["plataformas"]:
            if plataforma == "instagram" and not publicador.instagram_listo():
                continue
            try:
                piezas.append(crear_pieza(op, s, estrategia_id=e["id"], campana_id=campana, plataforma=plataforma, fecha=hoy,
                                          recientes=recientes, usar_ia=usar_ia))
            except Exception as ex:  # noqa: BLE001
                repo().log("creator", "error", strategy_id=e["id"], nivel="error", tipo=op.get("tipo"), error=str(ex)[:300])
    ult = _ultimo_plan()
    ult[pais] = hoy.isoformat()
    stores.config[CFG["ultimo_plan"][0]] = json.dumps(ult)
    _persistir()
    print(f"[agente_ia] plan {pais} {hoy}: {len(piezas)} pieza(s) en {time.time() - t0:.1f}s ({dec['fuente']})", flush=True)
    return {"ok": True, "estrategia": e, "piezas": piezas, "fuente": dec["fuente"]}


def _reintentos_plan() -> dict:
    try:
        return json.loads(_cfg("reintento_plan")) or {}
    except ValueError:
        return {}


def _ultimo_plan() -> dict:
    try:
        return json.loads(_cfg("ultimo_plan")) or {}
    except ValueError:
        return {}


def tick() -> bool:
    """Cada 60 s. True si hizo algo."""
    cfg = configuracion()
    if not cfg["activo"]:
        return False
    if not _lock.acquire(blocking=False):
        return False
    hizo = False
    try:
        hh, mm = (int(x) for x in cfg["hora_plan"].split(":"))
        ult = _ultimo_plan()
        reintento = _reintentos_plan()
        for pais in cfg["paises"]:
            loc = ahora_local(pais)
            if ult.get(pais) == loc.date().isoformat() or (loc.hour, loc.minute) < (hh, mm):
                continue
            if time.time() < float(reintento.get(pais) or 0):
                continue
            try:
                r = planificar(pais)
                if r.get("motivo") == "ya_planificado":      # p. ej. se cayó tras guardar la estrategia
                    ult[pais] = loc.date().isoformat()
                    stores.config[CFG["ultimo_plan"][0]] = json.dumps(ult)
                hizo = True
            except Exception as e:  # noqa: BLE001 — un país roto no frena a los demás ni la publicación
                reintento[pais] = time.time() + REINTENTO_PLAN_S
                stores.config[CFG["reintento_plan"][0]] = json.dumps(reintento)
                print(f"[agente_ia] plan {pais} falló: {str(e)[:200]}", flush=True)
                try:
                    repo().log("strategist", "error_plan", nivel="error", pais=pais, error=str(e)[:300])
                except Exception:  # noqa: BLE001
                    pass
        try:
            if not cfg["pausa"] and publicador.tick(snapshot_de=snapshot):
                hizo = True
        except Exception as e:  # noqa: BLE001
            print(f"[agente_ia] publicador: {str(e)[:200]}", flush=True)
        if time.time() - float(_cfg("ultima_medicion") or 0) >= 3600:
            stores.config[CFG["ultima_medicion"][0]] = str(time.time())
            try:
                hizo = bool(analitica.tick()) or hizo
            except Exception as e:  # noqa: BLE001
                print(f"[agente_ia] analytics: {str(e)[:200]}", flush=True)
        loc = ahora_local(cfg["paises"][0])
        if loc.weekday() == 0 and _cfg("ultimo_aprendizaje") != loc.date().isoformat() and loc.hour >= 5:
            aprendizaje.actualizar(_tz)
            stores.config[CFG["ultimo_aprendizaje"][0]] = loc.date().isoformat()
            hizo = True
    finally:
        _lock.release()
    if hizo:
        _persistir()
    return hizo


# ── controles humanos ────────────────────────────────────────────────────────
class Rechazo(ValueError):
    pass


def _get(cid: str) -> dict:
    c = repo().contenido(cid)
    if not c:
        raise Rechazo("La pieza no existe.")
    return c


def aprobar(cid: str, usuario: str, scheduled_at: datetime | None = None) -> dict:
    c = _get(cid)
    if not (c.get("validacion") or {}).get("ok"):
        raise Rechazo("La pieza no pasó la validación; edítala primero.")
    cuando = scheduled_at or c.get("scheduled_at") or ahora()
    cuando = max(cuando, ahora())
    r = repo().cambiar_estado(cid, ("PENDING_APPROVAL",), "APPROVED", revisado_por=usuario, revisado_en=ahora(), scheduled_at=cuando)
    if not r:
        raise Rechazo(f"No se puede aprobar una pieza en estado {c['status']}.")
    repo().log("admin", "aprobar", content_id=cid, usuario=usuario)
    return r


def rechazar(cid: str, usuario: str, motivo: str) -> dict:
    c = _get(cid)
    r = repo().cambiar_estado(cid, ("DRAFT", "PENDING_APPROVAL", "APPROVED", "FAILED"), "REJECTED", revisado_por=usuario,
                              revisado_en=ahora(), motivo_rechazo=(motivo or "Rechazada por el operador")[:500])
    if not r:
        raise Rechazo(f"No se puede rechazar una pieza en estado {c['status']}.")
    repo().log("admin", "rechazar", content_id=cid, usuario=usuario, motivo=motivo[:200])
    return r


def cancelar(cid: str, usuario: str) -> dict:
    c = _get(cid)
    r = repo().cambiar_estado(cid, CANCELABLES, "CANCELLED", revisado_por=usuario, revisado_en=ahora())
    if not r:
        raise Rechazo(f"No se puede cancelar una pieza en estado {c['status']}.")
    repo().log("admin", "cancelar", content_id=cid, usuario=usuario)
    return r


def reprogramar(cid: str, usuario: str, cuando: datetime) -> dict:
    c = _get(cid)
    if cuando < ahora() - timedelta(minutes=1):
        raise Rechazo("La nueva fecha ya pasó.")
    if c["status"] == "FAILED":
        if not (c.get("validacion") or {}).get("ok"):
            raise Rechazo("La pieza no pasó la validación; edítala primero.")
        r = repo().cambiar_estado(cid, ("FAILED",), "APPROVED", scheduled_at=cuando, intentos=0, error=None, revisado_por=usuario,
                                  revisado_en=ahora())
    else:
        r = repo().cambiar_estado(cid, ("PENDING_APPROVAL", "APPROVED"), c["status"], scheduled_at=cuando)
    if not r:
        raise Rechazo(f"No se puede reprogramar una pieza en estado {c['status']}.")
    repo().log("admin", "reprogramar", content_id=cid, usuario=usuario, cuando=cuando.isoformat())
    return r


def solo_texto(c: dict) -> str:
    """El cuerpo SIN el bloque del enlace ni los hashtags (lo que el operador edita)."""
    partes = (c.get("body") or "").split("\n\n")
    link = c.get("link_url") or "\x00"
    corte = next((i for i, p in enumerate(partes) if link in p), len(partes))
    return "\n\n".join(partes[:corte]).strip()


def editar(cid: str, usuario: str, campos: dict) -> dict:
    """El operador corrige el copy: se recompone la imagen y se VUELVE A VALIDAR.
    Lo editado vuelve a PENDING_APPROVAL (o REJECTED si sigue sin pasar)."""
    c = _get(cid)
    if c["status"] not in EDITABLES:
        raise Rechazo(f"No se puede editar una pieza en estado {c['status']}.")
    texto = campos.get("texto")
    if texto is None:
        texto = solo_texto(c)
    nuevo = {"title": creador._limpiar(campos.get("title", c.get("title")), 36),
             "subtitle": creador._limpiar(campos.get("subtitle", c.get("subtitle")), 80),
             "etiqueta": creador._limpiar(campos.get("etiqueta", c.get("etiqueta")), 14),
             "call_to_action": creador._limpiar(campos.get("call_to_action", c.get("call_to_action")), 90) or creador.CTA[c["audiencia"]]}
    nuevo["body"] = creador.componer_cuerpo(str(texto), nuevo["call_to_action"], c.get("link_url") or "", c.get("hashtags") or [])
    nuevo["hashtags"] = c.get("hashtags") or []
    # Fuera de la comparación: la propia pieza y su gemela de la otra red (misma oportunidad del mismo día).
    otros = [r["body"] for r in _recientes()
             if r["id"] != cid and not (r["strategy_id"] == c.get("strategy_id") and r["op_id"] == (c.get("oportunidad") or {}).get("id"))]
    s = None
    try:
        s = snapshot(c.get("pais") or "PE")
    except Exception:  # noqa: BLE001
        pass
    locales = [x["club"] for x in (s or {}).get("canchas_lista", []) if x.get("club")]
    v = guardrails.validar(nuevo, c.get("hechos") or {}, oportunidad=c.get("oportunidad") or {}, media_origen=c.get("media_origen"),
                           recientes=otros, locales_pais=locales, link=c.get("link_url"))
    receta = (c.get("oportunidad") or {}).get("media") or {}
    media_url = creativo.guardar(cid, creativo.componer(receta, titulo=nuevo["title"], subtitulo=nuevo["subtitle"], etiqueta=nuevo["etiqueta"]))
    estado = "PENDING_APPROVAL" if v["ok"] else "REJECTED"
    r = repo().cambiar_estado(cid, EDITABLES, estado, **nuevo, validacion={**v, "editado_por": usuario}, media_url=media_url,
                              motivo_rechazo=None if v["ok"] else "; ".join(v["errores"]), huella=_huella(nuevo["body"]),
                              revisado_por=None, revisado_en=None, fuente=f"{c.get('fuente') or ''}+editado".lstrip("+"))
    repo().log("admin", "editar", content_id=cid, usuario=usuario, ok=v["ok"], errores=v["errores"])
    return r


def regenerar(cid: str, usuario: str, *, usar_ia: bool = True) -> dict:
    """Otra versión de la misma oportunidad (la anterior se cancela)."""
    c = _get(cid)
    if c["status"] in ("PUBLISHED",):
        raise Rechazo("Una pieza publicada no se regenera.")
    s = snapshot(c.get("pais") or "PE")
    op = dict(c.get("oportunidad") or {})
    op["hechos"] = c.get("hechos") or {}
    op.setdefault("content_type", c["content_type"])
    recientes = _recientes() + [{"body": c.get("body") or ""}]
    nueva = crear_pieza(op, s, estrategia_id=c.get("strategy_id"), campana_id=c.get("campaign_id"), plataforma=c["platform"],
                        fecha=ahora_local(c.get("pais") or "PE").date(), recientes=recientes, usar_ia=usar_ia)
    if c["status"] in CANCELABLES:
        repo().cambiar_estado(cid, CANCELABLES, "CANCELLED", revisado_por=usuario, revisado_en=ahora(),
                              motivo_rechazo=f"Reemplazada por {nueva['id']}")
    repo().log("admin", "regenerar", content_id=cid, usuario=usuario, nueva=nueva["id"])
    return nueva


def publicar_ahora(cid: str, usuario: str) -> dict:
    c = _get(cid)
    if c["status"] == "PENDING_APPROVAL":
        c = aprobar(cid, usuario, ahora())
    if c["status"] != "APPROVED":
        raise Rechazo(f"No se puede publicar una pieza en estado {c['status']}.")
    try:
        s = snapshot(c.get("pais") or "PE")
    except Exception:  # noqa: BLE001
        s = None                         # sin datos frescos el publicador no publica (revalidación)
    r = publicador.publicar_una(cid, s)
    if r and r.get("status") == "APPROVED" and r.get("error"):
        raise Rechazo(f"No se publicó todavía: {r['error']}")
    return r


# ── lectura para la torre ─────────────────────────────────────────────────────
def _publica(c: dict) -> dict:
    perf = repo().performance(c["id"])
    m = analitica.mejor_ventana(perf) or (perf.get("1h") if perf else None)
    return {**c, "targets": repo().targets_de(c["id"]), "metricas": m, "ventanas": sorted(perf)}


def resumen() -> dict:
    cfg = configuracion()
    t = ahora()
    piezas = repo().listar_contenidos(desde=t - timedelta(days=30), limite=200)
    conteo = {e: 0 for e in ESTADOS}
    for c in piezas:
        conteo[c["status"]] += 1
    import config as _c
    from marketing.agente_ia import esquema
    return {"config": cfg, "conteo": conteo, "facebook_listo": publicador.facebook_listo(), "instagram_listo": publicador.instagram_listo(),
            "ia": bool(_c.ANTHROPIC_API_KEY), "atribucion": sorted(esquema.columnas_atribucion()),
            "ultimo_plan": _ultimo_plan(), "hora_local": {p: ahora_local(p).strftime("%Y-%m-%d %H:%M") for p in cfg["paises"]},
            "insights": repo().insights_vigentes()[:10], "estrategias": [
                {k: e.get(k) for k in ("id", "fecha", "pais", "fuente", "oportunidades", "created_at")} for e in repo().estrategias_lista(7)],
            "campanas": repo().campanas_lista(10), "agente_viejo_activo": str(stores.config.get("agente_fb_activo", "0")) == "1"}


def piezas(*, estado: str | None = None, desde: datetime | None = None, hasta: datetime | None = None) -> list[dict]:
    estados = (estado,) if estado in ESTADOS else None
    return [_publica(c) for c in repo().listar_contenidos(estados=estados, desde=desde, hasta=hasta, limite=200)]


def pieza(cid: str) -> dict:
    return _publica(_get(cid))
