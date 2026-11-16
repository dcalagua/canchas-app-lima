"""ANALYTICS AGENT: métricas de cada pieza publicada, por ventana de tiempo.

Fuentes:
* Facebook Graph (insights del post + reacciones/comentarios/compartidos).
  Meta cambia y retira métricas seguido: se piden de a una y la que no exista
  queda en NULL (nunca se inventa); la respuesta cruda va a `raw`.
* Short-link propio `/go/{codigo}`: clics únicos.
* Reservas atribuidas: `pichangol_reservas.utm->>'content' = codigo` creadas
  hasta el fin de la ventana (requiere el SQL de atribución).

Ventanas: 1h, 24h, 72h, 7d y 28d desde la publicación; cada una se mide una
vez, cuando vence.
"""
from __future__ import annotations

from datetime import timedelta

from marketing.agente_ia.repo import VENTANAS, ahora, repo

OFFSET = {"1h": timedelta(hours=1), "24h": timedelta(hours=24), "72h": timedelta(hours=72),
          "7d": timedelta(days=7), "28d": timedelta(days=28)}
METRICAS_POST = {"post_impressions_unique": "alcance", "post_impressions": "impresiones", "post_clicks": "clics",
                 "post_video_views": "reproducciones"}


def _fb(post_id: str) -> tuple[dict, dict]:
    from marketing import post_redes
    from marketing import redes
    m: dict = {}
    raw: dict = {}
    t = post_redes._resolver_token()
    tok = t.get("token")
    if not tok or not post_id:
        return m, {"error": t.get("error") or "sin_token"}
    r = redes._graph(post_id, {"fields": "shares,comments.summary(true).limit(0),reactions.summary(true).limit(0)", "access_token": tok})
    if r.get("ok"):
        d = r.get("data") or {}
        raw["campos"] = d
        m["compartidos"] = int((d.get("shares") or {}).get("count") or 0)
        m["comentarios"] = int(((d.get("comments") or {}).get("summary") or {}).get("total_count") or 0)
        m["reacciones"] = int(((d.get("reactions") or {}).get("summary") or {}).get("total_count") or 0)
    else:
        raw["campos_error"] = r.get("error")
    for metrica, campo in METRICAS_POST.items():
        r = redes._graph(f"{post_id}/insights", {"metric": metrica, "access_token": tok})
        if not r.get("ok"):
            raw.setdefault("insights_error", {})[metrica] = r.get("error")
            continue
        datos = (r.get("data") or {}).get("data") or []
        try:
            valor = datos[0]["values"][-1]["value"]
            if isinstance(valor, (int, float)):
                m[campo] = int(valor)
        except (IndexError, KeyError, TypeError):
            pass
        raw.setdefault("insights", {})[metrica] = datos
    return m, raw


def reservas_atribuidas(codigo: str, hasta) -> tuple[int | None, float | None]:
    from db import pg
    from marketing.agente_ia import esquema
    if not pg.habilitado or not {"utm", "created_at"} <= esquema.columnas_atribucion():
        return None, None
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT count(*), coalesce(sum(precio),0) FROM pichangol_reservas "
                        "WHERE utm->>'content' = %s AND created_at <= %s AND coalesce(estado,'') <> 'cancelada'", (codigo, hasta))
            n, total = cur.fetchone()
            return int(n), float(total)
    except Exception:  # noqa: BLE001
        return None, None


def medir(c: dict, ventana: str, *, fb=_fb, reservas=reservas_atribuidas) -> dict:
    fin = c["published_at"] + OFFSET[ventana]
    m, raw = fb(c.get("external_post_id") or "") if c["platform"] == "facebook" else ({}, {})
    m["clics_link"] = repo().contar_clics(c["id"], hasta=fin)
    n, total = reservas(c["codigo"], fin)
    m["reservas_atribuidas"], m["ingresos_atribuidos"] = n, total
    if any(m.get(k) is not None for k in ("reacciones", "comentarios", "compartidos")):
        m["interacciones"] = sum(int(m.get(k) or 0) for k in ("reacciones", "comentarios", "compartidos"))
    if m.get("alcance") and m.get("interacciones") is not None:
        m["engagement_rate"] = round(m["interacciones"] / m["alcance"], 4)
    repo().guardar_performance(c["id"], ventana, m, raw)
    return m


def tick(*, fb=_fb, reservas=reservas_atribuidas) -> int:
    """Mide las ventanas vencidas y no medidas de lo publicado en los últimos 29 días."""
    n = 0
    t = ahora()
    for c in repo().publicados_desde(t - timedelta(days=29)):
        hechas = repo().performance(c["id"])
        for v in VENTANAS:
            if v in hechas or t < c["published_at"] + OFFSET[v]:
                continue
            try:
                medir(c, v, fb=fb, reservas=reservas)
                n += 1
            except Exception as e:  # noqa: BLE001
                repo().log("analytics", "error_medicion", content_id=c["id"], nivel="error", ventana=v, error=str(e)[:200])
    if n:
        repo().log("analytics", "medicion", ventanas=n)
    return n


def mejor_ventana(perf: dict[str, dict]) -> dict | None:
    """La métrica más madura disponible (para el aprendizaje y la torre)."""
    for v in ("7d", "72h", "24h"):
        if v in perf:
            return perf[v]
    return None
