"""Persistencia del AI Marketing Agent.

Dos implementaciones con la MISMA interfaz:

* `_PgRepo`: tablas `ai_*` en Supabase (ver `esquema.py`). Es la de verdad.
* `_MemRepo`: en memoria, para la suite y para correr sin `DATABASE_URL`
  (igual que el resto del growth, que es fail-safe sin base).

A diferencia del agente viejo (`agente_redes`), NADA de esto vive en el
snapshot `growth_state`: contenidos, métricas y aprendizajes son filas
consultables en SQL y sobreviven a cualquier redeploy.
"""
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone

ESTADOS = ("DRAFT", "PENDING_APPROVAL", "APPROVED", "PUBLISHING", "PUBLISHED", "REJECTED", "FAILED", "CANCELLED")
VENTANAS = ("1h", "24h", "72h", "7d", "28d")

_JSON_CONTENIDO = ("oportunidad", "hashtags", "hechos", "validacion")
COLS_CONTENIDO = [
    "id", "codigo", "campaign_id", "strategy_id", "oportunidad", "content_type", "platform", "audiencia",
    "objetivo", "kpi", "pais", "zona", "title", "subtitle", "etiqueta", "body", "call_to_action", "hashtags",
    "link_url", "destino_url", "media_url", "media_origen", "hechos", "validacion", "fuente", "status",
    "scheduled_at", "published_at", "external_post_id", "permalink", "error", "intentos", "revisado_por",
    "revisado_en", "motivo_rechazo", "huella", "created_at", "updated_at",
]
COLS_PERF = ["alcance", "impresiones", "interacciones", "reacciones", "comentarios", "compartidos", "clics",
             "reproducciones", "clics_link", "reservas_atribuidas", "ingresos_atribuidos", "engagement_rate"]


def ahora() -> datetime:
    return datetime.now(timezone.utc)


def nuevo_id(prefijo: str) -> str:
    return f"{prefijo}_{uuid.uuid4().hex[:20]}"


def nuevo_codigo() -> str:
    return uuid.uuid4().hex[:10]


class _MemRepo:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.reiniciar()

    def reiniciar(self) -> None:
        self.campanas: dict[str, dict] = {}
        self.estrategias: dict[str, dict] = {}
        self.contenidos: dict[str, dict] = {}
        self.targets: dict[str, list[dict]] = {}
        self.clics: list[dict] = []
        self.perf: dict[tuple[str, str], dict] = {}
        self.insights: dict[str, dict] = {}
        self.logs: list[dict] = []

    # campañas
    def campana_asegurar(self, *, nombre: str, objetivo: str, audiencia: str, pais: str, zona: str | None,
                         kpi: str, inicio, fin) -> str:
        with self._lock:
            for c in self.campanas.values():
                if (c["objetivo"], c["audiencia"], c["pais"], c.get("zona"), c["inicio"]) == (objetivo, audiencia, pais, zona, inicio):
                    return c["id"]
            cid = nuevo_id("cmp")
            self.campanas[cid] = {"id": cid, "nombre": nombre, "objetivo": objetivo, "audiencia": audiencia, "pais": pais,
                                  "zona": zona, "kpi": kpi, "inicio": inicio, "fin": fin, "estado": "activa", "created_at": ahora()}
            return cid

    def campanas_lista(self, limite: int = 50) -> list[dict]:
        return sorted((dict(c) for c in self.campanas.values()), key=lambda c: c["created_at"], reverse=True)[:limite]

    # estrategia
    def estrategia_de(self, fecha, pais: str) -> dict | None:
        return next((dict(e) for e in self.estrategias.values() if e["fecha"] == fecha and e["pais"] == pais), None)

    def guardar_estrategia(self, e: dict) -> dict:
        with self._lock:
            previa = self.estrategia_de(e["fecha"], e["pais"])
            if previa:
                e = {**e, "id": previa["id"]}
            e.setdefault("id", nuevo_id("est"))
            e.setdefault("created_at", ahora())
            self.estrategias[e["id"]] = dict(e)
            return dict(e)

    def estrategias_lista(self, limite: int = 14) -> list[dict]:
        return sorted((dict(e) for e in self.estrategias.values()), key=lambda e: str(e["fecha"]), reverse=True)[:limite]

    # contenidos
    def crear_contenido(self, c: dict, targets: list[dict]) -> dict:
        with self._lock:
            c = {k: c.get(k) for k in COLS_CONTENIDO} | {"created_at": ahora(), "updated_at": ahora()}
            c["intentos"] = c.get("intentos") or 0
            self.contenidos[c["id"]] = c
            self.targets[c["id"]] = [dict(t) for t in targets]
            return dict(c)

    def contenido(self, cid: str) -> dict | None:
        c = self.contenidos.get(cid)
        return dict(c) if c else None

    def contenido_por_codigo(self, codigo: str) -> dict | None:
        return next((dict(c) for c in self.contenidos.values() if c["codigo"] == codigo), None)

    def targets_de(self, cid: str) -> list[dict]:
        return [dict(t) for t in self.targets.get(cid, [])]

    def actualizar_contenido(self, cid: str, **campos) -> dict | None:
        with self._lock:
            c = self.contenidos.get(cid)
            if not c:
                return None
            c.update({k: v for k, v in campos.items() if k in COLS_CONTENIDO})
            c["updated_at"] = ahora()
            return dict(c)

    def cambiar_estado(self, cid: str, desde: tuple[str, ...], hacia: str, **campos) -> dict | None:
        """Transición ATÓMICA: solo si el estado actual está en `desde` (evita
        publicar dos veces o aprobar algo ya cancelado)."""
        with self._lock:
            c = self.contenidos.get(cid)
            if not c or c["status"] not in desde:
                return None
            return self.actualizar_contenido(cid, status=hacia, **campos)

    def listar_contenidos(self, *, estados: tuple[str, ...] | None = None, desde=None, hasta=None, limite: int = 200) -> list[dict]:
        out = []
        for c in self.contenidos.values():
            if estados and c["status"] not in estados:
                continue
            ref = c.get("scheduled_at") or c["created_at"]
            if desde and ref < desde:
                continue
            if hasta and ref >= hasta:
                continue
            out.append(dict(c))
        return sorted(out, key=lambda c: c["created_at"], reverse=True)[:limite]

    def por_publicar(self, hasta: datetime) -> list[dict]:
        return sorted((dict(c) for c in self.contenidos.values()
                       if c["status"] == "APPROVED" and c.get("scheduled_at") and c["scheduled_at"] <= hasta),
                      key=lambda c: c["scheduled_at"])

    def publicados_desde(self, desde: datetime) -> list[dict]:
        return [dict(c) for c in self.contenidos.values()
                if c["status"] == "PUBLISHED" and c.get("published_at") and c["published_at"] >= desde]

    # clics
    def registrar_clic(self, cid: str, visitante: str) -> None:
        with self._lock:
            self.clics.append({"content_id": cid, "visitante": visitante, "creado": ahora()})

    def contar_clics(self, cid: str, hasta: datetime | None = None) -> int:
        return len({c["visitante"] or str(i) for i, c in enumerate(self.clics)
                    if c["content_id"] == cid and (hasta is None or c["creado"] <= hasta)})

    # performance
    def guardar_performance(self, cid: str, ventana: str, m: dict, raw: dict) -> None:
        with self._lock:
            self.perf[(cid, ventana)] = {k: m.get(k) for k in COLS_PERF} | {"raw": raw, "medido_en": ahora(), "ventana": ventana}

    def performance(self, cid: str) -> dict[str, dict]:
        return {v: dict(p) for (c, v), p in self.perf.items() if c == cid}

    # insights
    def reemplazar_insights(self, nuevos: list[dict]) -> None:
        with self._lock:
            for i in self.insights.values():
                i["vigente"] = False
            for n in nuevos:
                n = {**n, "id": n.get("id") or nuevo_id("ins"), "vigente": True, "created_at": ahora()}
                self.insights[n["id"]] = n

    def insights_vigentes(self) -> list[dict]:
        return sorted((dict(i) for i in self.insights.values() if i["vigente"]),
                      key=lambda i: (-float(i["confianza"]), -abs(float(i["efecto"]))))

    # logs
    def log(self, agente: str, accion: str, *, content_id: str | None = None, strategy_id: str | None = None,
            nivel: str = "info", **detalle) -> None:
        with self._lock:
            self.logs.insert(0, {"agente": agente, "accion": accion, "content_id": content_id, "strategy_id": strategy_id,
                                 "nivel": nivel, "detalle": detalle, "created_at": ahora()})
            del self.logs[2000:]

    def logs_recientes(self, limite: int = 100) -> list[dict]:
        return [dict(x) for x in self.logs[:limite]]


def _j(v):
    return json.dumps(v, ensure_ascii=False, default=str) if v is not None else None


class _PgRepo:
    """Misma interfaz que `_MemRepo`, sobre las tablas `ai_*`."""

    def _q(self, sql: str, params=(), *, uno: bool = False, todos: bool = False):
        from db import pg
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            if uno:
                f = cur.fetchone()
                return (f, [d.name for d in cur.description]) if f else (None, None)
            if todos:
                return cur.fetchall(), [d.name for d in cur.description] if cur.description else []
            return cur.rowcount

    @staticmethod
    def _dict(fila, cols) -> dict:
        return dict(zip(cols, fila))

    def _contenido(self, fila, cols) -> dict | None:
        if fila is None:
            return None
        c = self._dict(fila, cols)
        for k in _JSON_CONTENIDO:
            if isinstance(c.get(k), str):
                c[k] = json.loads(c[k])
        return c

    # campañas
    def campana_asegurar(self, *, nombre, objetivo, audiencia, pais, zona, kpi, inicio, fin) -> str:
        f, _ = self._q("SELECT id FROM ai_marketing_campaigns WHERE objetivo=%s AND audiencia=%s AND pais=%s "
                       "AND zona IS NOT DISTINCT FROM %s AND inicio=%s LIMIT 1", (objetivo, audiencia, pais, zona, inicio), uno=True)
        if f:
            return f[0]
        cid = nuevo_id("cmp")
        self._q("INSERT INTO ai_marketing_campaigns (id, nombre, objetivo, audiencia, pais, zona, kpi, inicio, fin) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)", (cid, nombre, objetivo, audiencia, pais, zona, kpi, inicio, fin))
        return cid

    def campanas_lista(self, limite: int = 50) -> list[dict]:
        filas, cols = self._q("SELECT * FROM ai_marketing_campaigns ORDER BY created_at DESC LIMIT %s", (limite,), todos=True)
        return [self._dict(f, cols) for f in filas]

    # estrategia
    def _estrategia(self, f, cols) -> dict | None:
        if f is None:
            return None
        e = self._dict(f, cols)
        for k in ("snapshot", "candidatas", "oportunidades", "insights_usados"):
            if isinstance(e.get(k), str):
                e[k] = json.loads(e[k])
        return e

    def estrategia_de(self, fecha, pais: str) -> dict | None:
        f, cols = self._q("SELECT * FROM ai_marketing_strategy WHERE fecha=%s AND pais=%s", (fecha, pais), uno=True)
        return self._estrategia(f, cols)

    def guardar_estrategia(self, e: dict) -> dict:
        eid = e.get("id") or nuevo_id("est")
        f, cols = self._q(
            "INSERT INTO ai_marketing_strategy (id, fecha, pais, snapshot, candidatas, oportunidades, insights_usados, fuente) "
            "VALUES (%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,%s) "
            "ON CONFLICT (fecha, pais) DO UPDATE SET snapshot=EXCLUDED.snapshot, candidatas=EXCLUDED.candidatas, "
            "oportunidades=EXCLUDED.oportunidades, insights_usados=EXCLUDED.insights_usados, fuente=EXCLUDED.fuente "
            "RETURNING *",
            (eid, e["fecha"], e["pais"], _j(e.get("snapshot") or {}), _j(e.get("candidatas") or []),
             _j(e.get("oportunidades") or []), _j(e.get("insights_usados") or []), e.get("fuente") or "reglas"), uno=True)
        return self._estrategia(f, cols)

    def estrategias_lista(self, limite: int = 14) -> list[dict]:
        filas, cols = self._q("SELECT * FROM ai_marketing_strategy ORDER BY fecha DESC LIMIT %s", (limite,), todos=True)
        return [self._estrategia(f, cols) for f in filas]

    # contenidos
    def crear_contenido(self, c: dict, targets: list[dict]) -> dict:
        from db import pg
        cols = [k for k in COLS_CONTENIDO if k not in ("created_at", "updated_at")]
        vals = [(_j(c.get(k)) if k in _JSON_CONTENIDO else c.get(k)) for k in cols]
        vals[cols.index("intentos")] = c.get("intentos") or 0
        marcas = [("%s::jsonb" if k in _JSON_CONTENIDO else "%s") for k in cols]
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute(f"INSERT INTO ai_content ({', '.join(cols)}) VALUES ({', '.join(marcas)}) RETURNING *", vals)
            fila, nombres = cur.fetchone(), [d.name for d in cur.description]
            for t in targets:
                cur.execute("INSERT INTO ai_content_targets (content_id, cancha_id, rol) VALUES (%s,%s,%s) "
                            "ON CONFLICT DO NOTHING", (c["id"], t["cancha_id"], t.get("rol") or "evidencia"))
            conn.commit()
        return self._contenido(fila, nombres)

    def contenido(self, cid: str) -> dict | None:
        return self._contenido(*self._q("SELECT * FROM ai_content WHERE id=%s", (cid,), uno=True))

    def contenido_por_codigo(self, codigo: str) -> dict | None:
        return self._contenido(*self._q("SELECT * FROM ai_content WHERE codigo=%s", (codigo,), uno=True))

    def targets_de(self, cid: str) -> list[dict]:
        filas, cols = self._q("SELECT cancha_id, rol FROM ai_content_targets WHERE content_id=%s", (cid,), todos=True)
        return [self._dict(f, cols) for f in filas]

    def _set(self, campos: dict) -> tuple[str, list]:
        partes, vals = [], []
        for k, v in campos.items():
            if k not in COLS_CONTENIDO or k in ("id", "created_at", "updated_at"):
                continue
            partes.append(f"{k} = %s::jsonb" if k in _JSON_CONTENIDO else f"{k} = %s")
            vals.append(_j(v) if k in _JSON_CONTENIDO else v)
        partes.append("updated_at = now()")
        return ", ".join(partes), vals

    def actualizar_contenido(self, cid: str, **campos) -> dict | None:
        sets, vals = self._set(campos)
        return self._contenido(*self._q(f"UPDATE ai_content SET {sets} WHERE id=%s RETURNING *", (*vals, cid), uno=True))

    def cambiar_estado(self, cid: str, desde: tuple[str, ...], hacia: str, **campos) -> dict | None:
        sets, vals = self._set({"status": hacia, **campos})
        return self._contenido(*self._q(f"UPDATE ai_content SET {sets} WHERE id=%s AND status = ANY(%s) RETURNING *",
                                        (*vals, cid, list(desde)), uno=True))

    def listar_contenidos(self, *, estados=None, desde=None, hasta=None, limite: int = 200) -> list[dict]:
        cond, params = ["TRUE"], []
        if estados:
            cond.append("status = ANY(%s)")
            params.append(list(estados))
        if desde:
            cond.append("coalesce(scheduled_at, created_at) >= %s")
            params.append(desde)
        if hasta:
            cond.append("coalesce(scheduled_at, created_at) < %s")
            params.append(hasta)
        filas, cols = self._q(f"SELECT * FROM ai_content WHERE {' AND '.join(cond)} ORDER BY created_at DESC LIMIT %s",
                              (*params, limite), todos=True)
        return [self._contenido(f, cols) for f in filas]

    def por_publicar(self, hasta: datetime) -> list[dict]:
        filas, cols = self._q("SELECT * FROM ai_content WHERE status='APPROVED' AND scheduled_at <= %s ORDER BY scheduled_at",
                              (hasta,), todos=True)
        return [self._contenido(f, cols) for f in filas]

    def publicados_desde(self, desde: datetime) -> list[dict]:
        filas, cols = self._q("SELECT * FROM ai_content WHERE status='PUBLISHED' AND published_at >= %s", (desde,), todos=True)
        return [self._contenido(f, cols) for f in filas]

    # clics
    def registrar_clic(self, cid: str, visitante: str) -> None:
        self._q("INSERT INTO ai_content_clicks (content_id, visitante) VALUES (%s,%s)", (cid, visitante))

    def contar_clics(self, cid: str, hasta: datetime | None = None) -> int:
        f, _ = self._q("SELECT count(DISTINCT coalesce(visitante, id::text)) FROM ai_content_clicks "
                       "WHERE content_id=%s AND (%s::timestamptz IS NULL OR creado <= %s::timestamptz)", (cid, hasta, hasta), uno=True)
        return int(f[0] or 0) if f else 0

    # performance
    def guardar_performance(self, cid: str, ventana: str, m: dict, raw: dict) -> None:
        cols = ["content_id", "ventana", *COLS_PERF, "raw"]
        vals = [cid, ventana, *[m.get(k) for k in COLS_PERF], _j(raw or {})]
        upd = ", ".join(f"{k}=EXCLUDED.{k}" for k in [*COLS_PERF, "raw"]) + ", medido_en=now()"
        self._q(f"INSERT INTO ai_content_performance ({', '.join(cols)}) VALUES ({', '.join(['%s'] * (len(cols) - 1))}, %s::jsonb) "
                f"ON CONFLICT (content_id, ventana) DO UPDATE SET {upd}", vals)

    def performance(self, cid: str) -> dict[str, dict]:
        filas, cols = self._q("SELECT * FROM ai_content_performance WHERE content_id=%s", (cid,), todos=True)
        return {r["ventana"]: r for r in (self._dict(f, cols) for f in filas)}

    # insights
    def reemplazar_insights(self, nuevos: list[dict]) -> None:
        from db import pg
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE ai_insights SET vigente = false WHERE vigente")
            for n in nuevos:
                cur.execute("INSERT INTO ai_insights (id, enunciado, dimension, valor, metrica, efecto, muestras, confianza, evidencia) "
                            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)",
                            (n.get("id") or nuevo_id("ins"), n["enunciado"], n["dimension"], n["valor"], n["metrica"],
                             n["efecto"], n["muestras"], n["confianza"], _j(n.get("evidencia") or [])))
            conn.commit()

    def insights_vigentes(self) -> list[dict]:
        filas, cols = self._q("SELECT * FROM ai_insights WHERE vigente ORDER BY confianza DESC, abs(efecto) DESC", todos=True)
        out = []
        for f in filas:
            d = self._dict(f, cols)
            d["efecto"], d["confianza"] = float(d["efecto"]), float(d["confianza"])
            out.append(d)
        return out

    # logs
    def log(self, agente: str, accion: str, *, content_id=None, strategy_id=None, nivel: str = "info", **detalle) -> None:
        try:
            self._q("INSERT INTO ai_agent_logs (agente, accion, content_id, strategy_id, nivel, detalle) VALUES (%s,%s,%s,%s,%s,%s::jsonb)",
                    (agente, accion, content_id, strategy_id, nivel, _j(detalle)))
        except Exception as e:  # noqa: BLE001 — la bitácora nunca rompe una corrida
            print(f"[agente_ia] log falló: {str(e)[:120]}", flush=True)

    def logs_recientes(self, limite: int = 100) -> list[dict]:
        filas, cols = self._q("SELECT * FROM ai_agent_logs ORDER BY created_at DESC LIMIT %s", (limite,), todos=True)
        return [self._dict(f, cols) for f in filas]


_mem = _MemRepo()
_pg = _PgRepo()
_forzado: object | None = None


def repo():
    """La base si hay `DATABASE_URL` (y el esquema está creado); si no, memoria."""
    if _forzado is not None:
        return _forzado
    from db import pg
    from marketing.agente_ia import esquema
    if pg.habilitado and esquema.asegurar():
        return _pg
    return _mem


def usar(r) -> None:
    """Solo tests: fija el repositorio (None = automático)."""
    global _forzado
    _forzado = r
