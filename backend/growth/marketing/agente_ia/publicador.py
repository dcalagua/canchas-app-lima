"""SOCIAL MEDIA PUBLISHER: publica las piezas APPROVED cuya hora llegó.

Garantías:

* **Una sola publicación por pieza.** Antes de hablar con la red social la pieza
  se RECLAMA de forma atómica (APPROVED → PUBLISHING). Solo quien gana el
  reclamo publica; mientras tanto nadie puede cancelarla, editarla ni volver a
  publicarla. Si después de publicar falla la escritura en la base, la pieza
  queda en PUBLISHING (nunca vuelve a APPROVED) y `recuperar_colgadas` la pasa
  a FAILED con aviso de revisar la página: preferimos un aviso a un post doble.
* **Revalidación con datos frescos.** Justo antes de publicar se compara cada
  hecho que la pieza afirma contra la base de ese momento (promo vencida o
  cambiada, turnos ya llenos, fecha pasada, local que dejó de ser Pro, conteos
  que bajaron). Sin datos frescos no se publica (se reintenta más tarde).
* Reintentos ante errores de la red social: 15 y 30 min, máximo `MAX_INTENTOS`.
"""
from __future__ import annotations

import os
import threading
from datetime import timedelta

from marketing.agente_ia import creativo
from marketing.agente_ia.repo import ahora, repo

MAX_INTENTOS = 3
COLGADA_MIN = 30
_lock = threading.Lock()


# ── revalidación de hechos ────────────────────────────────────────────────────
def sigue_vigente(c: dict, snapshot: dict | None) -> tuple[str | None, bool]:
    """(motivo, transitorio). motivo None = la pieza sigue siendo verdad.
    transitorio = vale la pena reintentar más tarde (p. ej. sin datos)."""
    op = c.get("oportunidad") or {}
    h = c.get("hechos") or {}
    tipo = op.get("tipo")
    if snapshot is None:
        return "No se pudieron leer los datos actuales para revalidar la pieza.", True
    hoy = snapshot.get("hoy") or ""
    fecha = op.get("fecha_objetivo")
    if fecha and str(fecha) < hoy:
        return "La fecha que anuncia la pieza ya pasó.", False
    if op.get("vigente_hasta") and str(op["vigente_hasta"]) < hoy:
        return "La promoción ya venció.", False
    lista = {x["id"]: x for x in snapshot.get("canchas_lista") or []}
    if op.get("destacadas") and not all((lista.get(cid) or {}).get("destacable") for cid in op["destacadas"]):
        return "El local destacado ya no está habilitado para publicidad (Pro / destacar).", False
    promos = snapshot.get("promos") or []
    if tipo == "promo_real":
        p = h.get("promo") or {}
        ok = False
        for x in promos:
            if x.get("cancha_id") not in (op.get("destacadas") or []) or x.get("tipo") != p.get("tipo") or x.get("pct") != p.get("pct"):
                continue
            if x["tipo"] == "hora_feliz":
                ok = (x.get("desde"), x.get("hasta")) == (p.get("desde"), p.get("hasta"))
            else:
                horas = list(x.get("horas") or [])
                ok = x.get("fecha") == fecha and horas == list(p.get("horas") or [])
                if ok and x.get("fecha") == hoy:      # hoy: alguna hora con descuento aún por delante
                    ok = any(int(hh[:2]) * 60 + int(hh[3:5]) > int(snapshot.get("ahora_min") or 0) for hh in horas)
            if ok:
                break
        if not ok:
            return "La promoción cambió o ya no está vigente en los datos de la cancha.", False
    if tipo == "promo_zona":
        actuales = [x for x in promos if x.get("tipo") == "hora_feliz" and x.get("zona") == op.get("zona")
                    and not (lista.get(x.get("cancha_id")) or {}).get("destacable")]
        if len(actuales) != h.get("canchas_con_promo") or max((x["pct"] for x in actuales), default=None) != h.get("pct_max"):
            return "Las horas felices de la zona cambiaron desde que se creó la pieza.", False
    if h.get("dia") and fecha and tipo in ("huecos_zona", "cancha_destacada"):
        clave = f"{fecha}|{h.get('franja')}"
        por_cancha = snapshot.get("libres_por_cancha") or {}
        con_turnos = [cid for cid in op.get("cancha_ids") or [] if por_cancha.get(cid, {}).get(clave, 0) > 0]
        if not con_turnos:
            return "Ya no quedan turnos libres en la franja anunciada.", False
        if h.get("canchas_con_turnos") and len(con_turnos) < int(h["canchas_con_turnos"]):
            return "Bajó el número de canchas con turnos libres que dice la pieza.", False
    if tipo == "captar_duenos_zona":
        actual = ((snapshot.get("leads_duenos") or {}).get(op.get("zona")) or {}).get("total", 0)
        if actual < int(h.get("canchas_sin_dueno") or 0):
            return "Bajó el número de canchas sin dueño que dice la pieza.", False
    if tipo == "comunidad":
        com = snapshot.get("comunidad") or {}
        if int(com.get("partidos_abiertos") or 0) < int(h.get("partidos_abiertos") or 0):
            return "Bajó el número de partidos abiertos que dice la pieza.", False
    return None, False


# ── redes ────────────────────────────────────────────────────────────────────
def facebook_listo() -> bool:
    from marketing import post_redes
    return post_redes.configurado()


def instagram_listo() -> bool:
    import config
    return bool(config.IG_USER_ID) and facebook_listo()


def _video_ia_listo(receta: dict) -> str | None:
    v = receta.get("video_ia") or {}
    return v.get("url") if v.get("estado") == "listo" and v.get("url") else None


def _publicar_facebook(c: dict, imagen: bytes) -> dict:
    from marketing import post_redes
    receta = (c.get("oportunidad") or {}).get("media") or {}
    url_video = _video_ia_listo(receta)
    if url_video:
        mp4 = creativo.leer_video(url_video)
        if not mp4:
            return {"ok": False, "error": "No se pudo leer el video IA guardado."}
        import tempfile
        fd, ruta = tempfile.mkstemp(suffix=".mp4")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(mp4)
            return post_redes.publicar_video_facebook(c["body"], c.get("title") or "", ruta)
        finally:
            try:
                os.remove(ruta)
            except OSError:
                pass
    if receta.get("video_id"):
        from marketing import agente_redes
        try:
            ruta = agente_redes.render_video({**receta, "titulo": c.get("title") or "", "audiencia": c.get("audiencia")})
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": f"No se pudo preparar el video: {str(e)[:160]}"}
        try:
            return post_redes.publicar_video_facebook(c["body"], c.get("title") or "", ruta)
        finally:
            try:
                os.remove(ruta)
            except OSError:
                pass
    return post_redes.publicar_facebook(c["body"], imagen)


def _publicar_instagram(c: dict) -> dict:
    """Graph: contenedor con `image_url` pública → `media_publish`."""
    import config
    from marketing import post_redes, redes
    url = c.get("media_url") or ""
    if not url.startswith("https://"):
        return {"ok": False, "error": "Instagram exige la imagen en una URL pública (Storage)."}
    t = post_redes._resolver_token()
    if t.get("error") or not t.get("token"):
        return {"ok": False, "error": t.get("error") or "Sin token de página."}
    r = redes._graph(f"{config.IG_USER_ID}/media", {"image_url": url, "caption": c["body"], "access_token": t["token"]}, post=True)
    if not r.get("ok"):
        return {"ok": False, "error": r.get("error", "error")}
    r2 = redes._graph(f"{config.IG_USER_ID}/media_publish", {"creation_id": r["data"].get("id"), "access_token": t["token"]}, post=True)
    if not r2.get("ok"):
        return {"ok": False, "error": r2.get("error", "error")}
    mid = str((r2.get("data") or {}).get("id") or "")
    link = ""
    r3 = redes._graph(mid, {"fields": "permalink", "access_token": t["token"]}) if mid else {}
    if r3.get("ok"):
        link = str((r3.get("data") or {}).get("permalink") or "")
    return {"ok": True, "post_id": mid, "url": link}


def _registrar_historial(c: dict, r: dict) -> None:
    """Mismo historial que ve la torre en "Publicar en Facebook"."""
    try:
        from marketing import post_redes
        m = (c.get("oportunidad") or {}).get("media") or {}
        es_video = bool(m.get("video_id")) or (bool(_video_ia_listo(m)) and c["platform"] == "facebook")
        post_redes.registrar({"red": c["platform"], "tipo": "video" if es_video else "foto",
                              "plantilla": "agente_ia", "enfoque": (c.get("oportunidad") or {}).get("tipo", ""), "fuente": c.get("fuente", ""),
                              "audiencia": c.get("audiencia", ""), "local": "", "titulo": c.get("title", ""), "texto": (c.get("body") or "")[:600],
                              "ok": bool(r.get("ok")), "post_id": r.get("post_id", ""), "url": r.get("url", ""), "error": r.get("error", ""),
                              "origen": "agente_ia"})
    except Exception:  # noqa: BLE001
        pass


def _marcar_uso(c: dict) -> None:
    receta = (c.get("oportunidad") or {}).get("media") or {}
    try:
        from marketing import biblioteca
        if receta.get("biblioteca_ids"):
            biblioteca.marcar_uso(list(receta["biblioteca_ids"]))
    except Exception:  # noqa: BLE001
        pass


def _cerrar(cid: str, hacia: str, **campos) -> dict | None:
    """PUBLISHING → estado final. Reintenta la escritura: tras un post exitoso,
    perder este UPDATE no debe dejar la pieza publicable de nuevo."""
    ultimo = None
    for _ in range(3):
        try:
            return repo().cambiar_estado(cid, ("PUBLISHING",), hacia, **campos)
        except Exception as e:  # noqa: BLE001
            ultimo = e
    print(f"[agente_ia] no se pudo cerrar {cid} → {hacia}: {str(ultimo)[:160]}", flush=True)
    return None


def publicar(c: dict, *, snapshot: dict | None = None) -> dict:
    """Publica UNA pieza APPROVED (si gana el reclamo). Devuelve la pieza actualizada."""
    r_ = repo()
    reclamada = r_.cambiar_estado(c["id"], ("APPROVED",), "PUBLISHING")
    if not reclamada:
        return r_.contenido(c["id"]) or c          # otra corrida la tomó, o la cancelaron
    c = reclamada
    if (((c.get("oportunidad") or {}).get("media") or {}).get("video_ia") or {}).get("estado") == "generando":
        # El video de Sora aún no llega: se espera sin gastar intentos (si falla, sale con la foto ambientada).
        return _cerrar(c["id"], "APPROVED", error="Esperando el video con IA.",
                       scheduled_at=ahora() + timedelta(minutes=10)) or c
    intentos = int(c.get("intentos") or 0) + 1
    motivo, transitorio = sigue_vigente(c, snapshot)
    if motivo:
        if transitorio and intentos < MAX_INTENTOS:
            r_.log("publisher", "revalidacion_pendiente", content_id=c["id"], nivel="warn", motivo=motivo, intentos=intentos)
            return _cerrar(c["id"], "APPROVED", error=motivo, intentos=intentos,
                           scheduled_at=ahora() + timedelta(minutes=15 * intentos)) or c
        r_.log("publisher", "no_vigente", content_id=c["id"], nivel="warn", motivo=motivo)
        return _cerrar(c["id"], "FAILED", error=motivo, intentos=intentos) or c
    try:
        imagen = creativo.leer(c["id"], c.get("media_url"))
        if imagen is None:
            receta = (c.get("oportunidad") or {}).get("media") or {}
            imagen = creativo.componer(receta, titulo=c.get("title") or "", subtitulo=c.get("subtitle") or "", etiqueta=c.get("etiqueta") or "")
        if c["platform"] == "facebook":
            res = _publicar_facebook(c, imagen) if facebook_listo() else {"ok": False, "error": "sin_credenciales: falta FB_PAGE_ID / token de página"}
        elif c["platform"] == "instagram":
            res = _publicar_instagram(c) if instagram_listo() else {"ok": False, "error": "Instagram no está conectado (IG_USER_ID)."}
        else:
            res = {"ok": False, "error": f"Plataforma no soportada aún: {c['platform']}"}
    except Exception as e:  # noqa: BLE001 — nada salió hacia la red: se puede reintentar
        res = {"ok": False, "error": f"Error interno antes de publicar: {str(e)[:200]}"}
    _registrar_historial(c, res)
    if res.get("ok"):
        _marcar_uso(c)
        print(f"[agente_ia] publicado {c['platform']} · {c.get('audiencia')} · {c.get('title')!r}", flush=True)
        out = _cerrar(c["id"], "PUBLISHED", published_at=ahora(), external_post_id=res.get("post_id", ""),
                      permalink=res.get("url", ""), error=None, intentos=intentos)
        try:
            r_.log("publisher", "publicado", content_id=c["id"], plataforma=c["platform"], url=res.get("url", ""), post_id=res.get("post_id", ""))
        except Exception:  # noqa: BLE001
            pass
        return out or {**c, "status": "PUBLISHING", "external_post_id": res.get("post_id", "")}
    err = str(res.get("error") or "error")[:500]
    permanente = err.startswith("sin_credenciales") or "no está conectado" in err or "no soportada" in err
    if intentos >= MAX_INTENTOS or permanente:
        r_.log("publisher", "fallo_definitivo", content_id=c["id"], nivel="error", error=err, intentos=intentos)
        return _cerrar(c["id"], "FAILED", error=err, intentos=intentos) or c
    r_.log("publisher", "reintento", content_id=c["id"], nivel="warn", error=err, intentos=intentos)
    return _cerrar(c["id"], "APPROVED", error=err, intentos=intentos, scheduled_at=ahora() + timedelta(minutes=15 * intentos)) or c


def recuperar_colgadas() -> int:
    """Piezas que quedaron en PUBLISHING (proceso caído o base inaccesible justo
    después de publicar): NO se republican; pasan a FAILED para que el operador
    revise la página y, si no salió, la reprograme."""
    n = 0
    limite = ahora() - timedelta(minutes=COLGADA_MIN)
    for c in repo().listar_contenidos(estados=("PUBLISHING",), limite=50):
        if c["updated_at"] <= limite:
            if repo().cambiar_estado(c["id"], ("PUBLISHING",), "FAILED",
                                     error="Estado incierto: se cortó mientras se publicaba. Revisa la página antes de reprogramarla."):
                repo().log("publisher", "colgada", content_id=c["id"], nivel="error")
                n += 1
    return n


def tick(snapshot_de=None) -> int:
    """Publica lo que toca. `snapshot_de(pais)` → snapshot fresco para revalidar."""
    from db.store import stores
    if str(stores.config.get("ai_mkt_pausa", "0")) == "1":
        return 0
    if not _lock.acquire(blocking=False):
        return 0
    n = 0
    try:
        try:
            recuperar_colgadas()
        except Exception as e:  # noqa: BLE001
            print(f"[agente_ia] recuperar_colgadas: {str(e)[:160]}", flush=True)
        cache: dict[str, dict | None] = {}
        for c in repo().por_publicar(ahora()):
            pais = c.get("pais") or "PE"
            if pais not in cache:
                try:
                    cache[pais] = snapshot_de(pais) if snapshot_de else None
                except Exception:  # noqa: BLE001
                    cache[pais] = None
            try:
                publicar(c, snapshot=cache[pais])
                n += 1
            except Exception as e:  # noqa: BLE001 — una pieza rota no frena la cola
                print(f"[agente_ia] publicar {c['id']} falló: {str(e)[:160]}", flush=True)
    finally:
        _lock.release()
    return n


def publicar_una(cid: str, snapshot: dict | None) -> dict | None:
    """"Publicar ya" desde la torre: mismo camino (y mismo candado) que el cron."""
    with _lock:
        c = repo().contenido(cid)
        if not c or c["status"] != "APPROVED":
            return c
        return publicar(c, snapshot=snapshot)
