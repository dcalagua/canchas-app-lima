"""ENCARGADOS DEL LOCAL (rol único "Recepción"): datos y reglas.

El dueño invita a una persona por su correo de Google para que le ayude a
operar UN local (`local_key` = "dueño|club", el de la tarjeta de fidelidad).
La persona acepta en el modo anfitrión y desde ahí opera las canchas de ese
local con el rol Recepción (qué puede hacer: `web/permisos.py`).

Tablas de la migración `0005_encargados.sql` (`cl_encargados` y la bitácora
`cl_encargados_acciones`). FAIL-SAFE: sin base o sin la migración aplicada
`disponible()` es False, nadie es encargado y la sección no se muestra.
Los tests inyectan `RepoMemoria` (`usar_repo`).
"""

from __future__ import annotations

import json
import re
import threading
import time
from datetime import datetime, timezone

ROL_RECEPCION = "recepcion"
ROLES = {ROL_RECEPCION: "Recepción"}
ESTADOS = {"invitado": "Invitación enviada", "activo": "Activo", "rechazado": "Rechazó la invitación", "revocado": "Acceso quitado"}
VIVOS = ("invitado", "activo")
MAX_POR_LOCAL = 10
# Caché de "¿de qué locales es encargado este correo?" (cada página del modo
# anfitrión lo pregunta). Se borra en este proceso al invitar, aceptar,
# rechazar o revocar.
CACHE_TTL = 15.0
_CORREO = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _iso(v) -> str:
    return v.isoformat() if isinstance(v, datetime) else str(v or "")


def normalizar_correo(v) -> str:
    return str(v or "").strip().lower()[:120]


def correo_valido(v: str) -> bool:
    return bool(_CORREO.match(v or ""))


# ── repositorios ─────────────────────────────────────────────────────────────

class RepoMemoria:
    """Mismo contrato que `RepoPG`, en memoria (tests)."""

    def __init__(self):
        self.filas: dict[str, dict] = {}
        self.acciones: list[dict] = []
        self._lock = threading.Lock()

    def disponible(self) -> bool:
        return True

    def crear(self, fila: dict) -> str:
        with self._lock:
            if any(f["local_key"] == fila["local_key"] and f["email"] == fila["email"] and f["estado"] in VIVOS
                   for f in self.filas.values()):
                return "ya_existe"
            self.filas[fila["id"]] = dict(fila)
        return ""

    def por_id(self, eid: str) -> dict | None:
        f = self.filas.get(eid)
        return dict(f) if f else None

    def de_dueno(self, dueno: str) -> list[dict]:
        return sorted([dict(f) for f in self.filas.values() if f["dueno"] == dueno], key=lambda f: f["creado"], reverse=True)

    def de_email(self, email: str, estados) -> list[dict]:
        return sorted([dict(f) for f in self.filas.values() if f["email"] == email and f["estado"] in estados],
                      key=lambda f: f["creado"])

    def cambiar_estado(self, eid: str, nuevo: str, desde, campo_ts: str = "") -> bool:
        with self._lock:
            f = self.filas.get(eid)
            if not f or f["estado"] not in desde:
                return False
            f["estado"] = nuevo
            f["actualizado_en"] = _iso(_ahora())
            if campo_ts:
                f[campo_ts] = _iso(_ahora())
            return True

    def registrar_accion(self, fila: dict) -> bool:
        self.acciones.append(dict(fila, id=len(self.acciones) + 1, creado_en=_iso(_ahora())))
        return True

    def acciones_de(self, dueno: str, limite: int = 50) -> list[dict]:
        return [dict(a) for a in reversed(self.acciones) if a["dueno"] == dueno][:limite]


class RepoPG:
    """Tablas de la migración 0005 (rol del backend; la anon key no las ve)."""

    _COLS = ["id", "dueno", "local_key", "local_nombre", "cancha_ids", "email", "rol", "estado", "invitado_por",
             "creado", "aceptado_en", "revocado_en", "actualizado_en"]
    _COLS_ACC = ["id", "encargado_id", "dueno", "actor", "accion", "cancha_id", "ref", "detalle", "creado_en"]
    _tabla = {"ok": None, "t": 0.0}

    def disponible(self) -> bool:
        """¿Hay base y la migración 0005 ya corrió? (cacheado: un "sí" 10 min,
        un "no" 1 min, por si se aplica la migración con el backend vivo)."""
        from db import pg
        if not pg.habilitado:
            return False
        ok, t = self._tabla["ok"], self._tabla["t"]
        if ok is not None and time.monotonic() - t < (600 if ok else 60):
            return ok
        try:
            with pg.conexion() as conn, conn.cursor() as cur:
                cur.execute("select to_regclass('public.cl_encargados') is not null "
                            "and to_regclass('public.cl_encargados_acciones') is not null")
                ok = bool(cur.fetchone()[0])
        except Exception:  # noqa: BLE001
            ok = False
        self._tabla.update(ok=ok, t=time.monotonic())
        return ok

    def _fila(self, f) -> dict:
        d = dict(zip(self._COLS, f))
        if isinstance(d.get("cancha_ids"), str):
            d["cancha_ids"] = json.loads(d["cancha_ids"] or "[]")
        for k in ("creado", "aceptado_en", "revocado_en", "actualizado_en"):
            d[k] = _iso(d.get(k)) if d.get(k) else ""
        d["cancha_ids"] = [str(x) for x in (d.get("cancha_ids") or [])]
        return d

    def _varios(self, where: str, args) -> list[dict]:
        from db import pg
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute(f"select {', '.join(self._COLS)} from cl_encargados where {where}", args)
            return [self._fila(f) for f in cur.fetchall()]

    def crear(self, fila: dict) -> str:
        from db import pg
        cols = ["id", "dueno", "local_key", "local_nombre", "cancha_ids", "email", "rol", "estado", "invitado_por"]
        vals = [json.dumps(fila["cancha_ids"]) if c == "cancha_ids" else fila[c] for c in cols]
        try:
            with pg.conexion() as conn, conn.cursor() as cur:
                cur.execute(f"insert into cl_encargados ({', '.join(cols)}) values ({', '.join(['%s'] * len(cols))})", vals)
                conn.commit()
            return ""
        except Exception as ex:  # noqa: BLE001
            if "uq_cl_enc_vivo" in str(ex):
                return "ya_existe"
            print(f"[encargados] no se pudo crear: {str(ex)[:200]}", flush=True)
            return "error"

    def por_id(self, eid: str) -> dict | None:
        f = self._varios("id = %s", (eid,))
        return f[0] if f else None

    def de_dueno(self, dueno: str) -> list[dict]:
        return self._varios("dueno = %s order by creado desc limit 200", (dueno,))

    def de_email(self, email: str, estados) -> list[dict]:
        return self._varios("email = %s and estado = any(%s) order by creado", (email, list(estados)))

    def cambiar_estado(self, eid: str, nuevo: str, desde, campo_ts: str = "") -> bool:
        from db import pg
        extra = f", {campo_ts} = now()" if campo_ts in ("aceptado_en", "revocado_en") else ""
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute(f"update cl_encargados set estado = %s, actualizado_en = now(){extra} "
                        "where id = %s and estado = any(%s)", (nuevo, eid, list(desde)))
            n = cur.rowcount
            conn.commit()
            return n == 1

    def registrar_accion(self, fila: dict) -> bool:
        from db import pg
        cols = ["encargado_id", "dueno", "actor", "accion", "cancha_id", "ref", "detalle"]
        vals = [json.dumps(fila.get(c) or {}, ensure_ascii=False) if c == "detalle" else str(fila.get(c) or "") for c in cols]
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute(f"insert into cl_encargados_acciones ({', '.join(cols)}) values ({', '.join(['%s'] * len(cols))})", vals)
            conn.commit()
        return True

    def acciones_de(self, dueno: str, limite: int = 50) -> list[dict]:
        from db import pg
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute(f"select {', '.join(self._COLS_ACC)} from cl_encargados_acciones where dueno = %s "
                        "order by creado_en desc, id desc limit %s", (dueno, int(limite)))
            out = []
            for f in cur.fetchall():
                d = dict(zip(self._COLS_ACC, f))
                if isinstance(d.get("detalle"), str):
                    d["detalle"] = json.loads(d["detalle"] or "{}")
                d["creado_en"] = _iso(d.get("creado_en"))
                out.append(d)
            return out


_repo = RepoPG()
_cache: dict[str, tuple[float, list[dict]]] = {}
_cache_lock = threading.Lock()


def usar_repo(repo) -> None:
    """Tests: inyecta un repositorio (p. ej. `RepoMemoria()`)."""
    global _repo
    _repo = repo
    invalidar()


def repo():
    return _repo


def disponible() -> bool:
    try:
        return bool(_repo.disponible())
    except Exception:  # noqa: BLE001
        return False


def invalidar(email: str = "") -> None:
    with _cache_lock:
        if email:
            _cache.pop(email, None)
        else:
            _cache.clear()


# ── lecturas ────────────────────────────────────────────────────────────────

def activos_de(email: str) -> list[dict]:
    """Encargos ACTIVOS de este correo (los locales donde ayuda). Nunca lanza."""
    email = normalizar_correo(email)
    if not email or not disponible():
        return []
    ahora = time.monotonic()
    with _cache_lock:
        hit = _cache.get(email)
    if hit and CACHE_TTL > 0 and ahora - hit[0] < CACHE_TTL:
        return [dict(x) for x in hit[1]]
    try:
        filas = _repo.de_email(email, ("activo",))
    except Exception as ex:  # noqa: BLE001
        print(f"[encargados] activos_de falló: {str(ex)[:160]}", flush=True)
        return []
    with _cache_lock:
        _cache[email] = (ahora, filas)
    return [dict(x) for x in filas]


def invitaciones_de(email: str) -> list[dict]:
    """Invitaciones PENDIENTES de responder (banner en /anfitrion)."""
    email = normalizar_correo(email)
    if not email or not disponible():
        return []
    try:
        return _repo.de_email(email, ("invitado",))
    except Exception:  # noqa: BLE001
        return []


def de_dueno(dueno: str) -> list[dict]:
    dueno = normalizar_correo(dueno)
    if not dueno or not disponible():
        return []
    try:
        return _repo.de_dueno(dueno)
    except Exception:  # noqa: BLE001
        return []


def por_id(eid: str) -> dict | None:
    if not eid or not disponible():
        return None
    try:
        return _repo.por_id(str(eid))
    except Exception:  # noqa: BLE001
        return None


def acciones_de(dueno: str, limite: int = 50) -> list[dict]:
    if not disponible():
        return []
    try:
        return _repo.acciones_de(normalizar_correo(dueno), limite)
    except Exception:  # noqa: BLE001
        return []


# ── escrituras ──────────────────────────────────────────────────────────────

def invitar(dueno: str, local_key: str, local_nombre: str, cancha_ids: list[str], email: str) -> tuple[int, dict]:
    """(status HTTP, respuesta). El dueño ya se validó en el llamador (el local
    es suyo). Idempotente: si la persona ya tiene una invitación viva para ese
    local, se devuelve esa."""
    dueno, email = normalizar_correo(dueno), normalizar_correo(email)
    if not disponible():
        return 503, {"ok": False, "error": "no_disponible"}
    if not correo_valido(email):
        return 400, {"ok": False, "error": "correo_invalido"}
    if email == dueno:
        return 400, {"ok": False, "error": "eres_tu"}
    previas = [f for f in de_dueno(dueno) if f["local_key"] == local_key and f["estado"] in VIVOS]
    ya = next((f for f in previas if f["email"] == email), None)
    if ya:
        return 200, {"ok": True, "encargado": ya, "ya_invitado": True}
    if len(previas) >= MAX_POR_LOCAL:
        return 400, {"ok": False, "error": "tope"}
    fila = {"id": f"enc_{int(time.time() * 1_000_000)}", "dueno": dueno, "local_key": local_key,
            "local_nombre": (local_nombre or "")[:120], "cancha_ids": [str(x) for x in cancha_ids][:60],
            "email": email, "rol": ROL_RECEPCION, "estado": "invitado", "invitado_por": dueno,
            "creado": _iso(_ahora()), "aceptado_en": "", "revocado_en": "", "actualizado_en": _iso(_ahora())}
    err = _repo.crear(fila)
    if err == "ya_existe":
        ya = next((f for f in de_dueno(dueno) if f["local_key"] == local_key and f["email"] == email and f["estado"] in VIVOS), None)
        return 200, {"ok": True, "encargado": ya or fila, "ya_invitado": True}
    if err:
        return 503, {"ok": False, "error": "no_guardado"}
    invalidar(email)
    return 200, {"ok": True, "encargado": fila}


def aceptar(email: str, eid: str) -> bool:
    f = por_id(eid)
    if not f or f["email"] != normalizar_correo(email) or f["estado"] != "invitado":
        return False
    ok = _repo.cambiar_estado(f["id"], "activo", ("invitado",), "aceptado_en")
    invalidar(f["email"])
    return ok


def rechazar(email: str, eid: str) -> bool:
    f = por_id(eid)
    if not f or f["email"] != normalizar_correo(email) or f["estado"] != "invitado":
        return False
    ok = _repo.cambiar_estado(f["id"], "rechazado", ("invitado",))
    invalidar(f["email"])
    return ok


def revocar(dueno: str, eid: str) -> dict | None:
    """Quita el acceso (o anula la invitación). Solo el dueño del encargo.
    Devuelve el encargo quitado o None."""
    f = por_id(eid)
    if not f or f["dueno"] != normalizar_correo(dueno) or f["estado"] not in VIVOS:
        return None
    ok = _repo.cambiar_estado(f["id"], "revocado", VIVOS, "revocado_en")
    invalidar(f["email"])
    return f if ok else None


def registrar_accion(*, encargado_id: str, dueno: str, actor: str, accion: str, cancha_id: str = "", ref: str = "",
                     detalle: dict | None = None) -> None:
    """Bitácora best-effort: nunca rompe la acción que se está registrando."""
    if not disponible():
        return
    try:
        _repo.registrar_accion({"encargado_id": encargado_id, "dueno": normalizar_correo(dueno), "actor": normalizar_correo(actor),
                                "accion": accion, "cancha_id": cancha_id, "ref": ref, "detalle": detalle or {}})
    except Exception as ex:  # noqa: BLE001
        print(f"[encargados] bitácora falló ({accion} {ref}): {str(ex)[:160]}", flush=True)
