"""Acceso a las tablas de Supabase que comparte con el APK (misma base de
datos que `DATABASE_URL`: `pichangol_canchas`, `pichangol_reservas`,
`pichangol_bloqueos`, `pichangol_descuentos_slot`). Postgres directo, sin RLS
(rol del backend), transacciones cortas. Sin `DATABASE_URL` todo devuelve
vacío/False y las páginas muestran "no disponible" (fail-safe).

La garantía anti doble reserva es el UNIQUE `(cancha_id, fecha, hora_inicio)`
de `pichangol_reservas`: el mismo que usa el APK (`insertarSegura`).
"""

from __future__ import annotations

import json
import time

from db import pg

COLS_CANCHA = (
    "id, nombre, club, distrito, barrio, deporte, deportes, precio_hora, lat, lng, "
    "direccion, foto_url, fotos, dueno, verificada, registrada, eliminada, "
    "hora_apertura, hora_cierre, duracion_slot_min, moneda, servicios_extra, "
    "descuento_valle, valle_desde, valle_hasta, sena_pct, superficie, amenidades"
)
_COLS = [c.strip() for c in COLS_CANCHA.split(",")]

PREFIJO_ID_WEB = "web_"
HOLD_SEGUNDOS = 10 * 60  # una reserva web sin pagar se libera a los 10 min


def _json_list(v) -> list:
    if v is None:
        return []
    if isinstance(v, list):
        return v
    try:
        j = json.loads(v)
        return j if isinstance(j, list) else []
    except (TypeError, ValueError):
        return []


def _norm_cancha(d: dict) -> dict:
    d = dict(d)
    d["deportes"] = _json_list(d.get("deportes"))
    d["fotos"] = _json_list(d.get("fotos"))
    d["servicios_extra"] = [
        s for s in _json_list(d.get("servicios_extra")) if isinstance(s, dict)]
    d["amenidades"] = _json_list(d.get("amenidades"))
    d["precio_hora"] = float(d.get("precio_hora") or 0)
    d["lat"] = float(d.get("lat") or 0)
    d["lng"] = float(d.get("lng") or 0)
    d["duracion_slot_min"] = int(d.get("duracion_slot_min") or 60)
    d["descuento_valle"] = int(d.get("descuento_valle") or 0)
    d["sena_pct"] = int(d.get("sena_pct") or 0)
    d["hora_apertura"] = (d.get("hora_apertura") or "07:00")
    d["hora_cierre"] = (d.get("hora_cierre") or "23:00")
    for k in ("nombre", "club", "distrito", "barrio", "deporte", "direccion",
              "foto_url", "dueno", "moneda", "superficie", "valle_desde", "valle_hasta"):
        d[k] = (d.get(k) or "") if d.get(k) is not None else ""
    return d


# ── Cosecha de fotos por lugar (`pichangol_lugares_fotos`) ────────────────────
# Una consulta a Google por lugar, UNA vez: la primera foto resuelta se guarda
# aquí y se refresca sola pasados 30 días (límite de caché de los términos de
# Google Maps Platform). Fail-safe: sin tabla, la web resuelve en vivo.

FOTOS_VIGENCIA_SEG = 30 * 24 * 3600


def leer_fotos_lugar(clave: str) -> tuple[list[str], bool] | None:
    """(fotos, vigente) guardadas para `clave`, o None si no hay fila/tabla.
    `vigente`=False → hay que refrescar (pero sirven mientras tanto)."""
    if not pg.habilitado or not clave:
        return None
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT fotos, extract(epoch from (now() - actualizado)) "
                        "FROM pichangol_lugares_fotos WHERE clave = %s", (clave,))
            f = cur.fetchone()
            if not f:
                return None
            fotos = [str(u) for u in _json_list(f[0]) if str(u).startswith("http")]
            return fotos, float(f[1] or 0) < FOTOS_VIGENCIA_SEG
    except Exception:  # noqa: BLE001
        return None


def guardar_fotos_lugar(clave: str, nombre: str, lat: float, lng: float, fotos: list[str]) -> bool:
    if not pg.habilitado or not clave:
        return False
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO pichangol_lugares_fotos (clave, nombre, lat, lng, fotos, actualizado) "
                "VALUES (%s, %s, %s, %s, %s::jsonb, now()) "
                "ON CONFLICT (clave) DO UPDATE SET nombre = EXCLUDED.nombre, lat = EXCLUDED.lat, "
                "lng = EXCLUDED.lng, fotos = EXCLUDED.fotos, actualizado = now()",
                (clave, (nombre or "")[:200], lat, lng, json.dumps(fotos[:3])))
            conn.commit()
        return True
    except Exception:  # noqa: BLE001
        return False


def ratings(ids: list[str]) -> dict[str, tuple[float, int]]:
    """Reputación real por cancha desde `pichangol_resenas` (las mismas
    reseñas ⭐ del APK): id → (promedio, cantidad). Fail-safe: {} sin base o
    sin tabla."""
    ids = [i for i in ids if i]
    if not pg.habilitado or not ids:
        return {}
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT cancha_id, avg(estrellas)::float, count(*)::int FROM pichangol_resenas "
                "WHERE cancha_id = ANY(%s) AND estrellas BETWEEN 1 AND 5 GROUP BY cancha_id", (ids,))
            return {str(r[0]): (float(r[1] or 0), int(r[2] or 0)) for r in cur.fetchall()}
    except Exception:  # noqa: BLE001
        return {}


def canchas_publicas() -> list[dict]:
    """TODAS las canchas publicables en la web: registradas y no eliminadas.
    Las verificadas con dueño son reservables en línea; las demás (aún sin
    verificar) se muestran con "Reservar en la app" (decisión del director,
    sep-2026: la web enseña el mismo mapa que el APK). Verificadas primero."""
    if not pg.habilitado:
        return []
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute(
                f"SELECT {COLS_CANCHA} FROM pichangol_canchas "
                "WHERE coalesce(registrada,true) AND NOT coalesce(eliminada,false) "
                "ORDER BY (coalesce(verificada,false) AND coalesce(dueno,'') <> '') DESC, club, nombre")
            return [_norm_cancha(pg._fila_a_dict(_COLS, f)) for f in cur.fetchall()]
    except Exception:  # noqa: BLE001
        return []


def reservable(c: dict) -> bool:
    """Reservable en línea = verificada + con dueño (igual que `Cancha.reservable`)."""
    return bool(c.get("verificada")) and bool((c.get("dueno") or "").strip()) and not c.get("eliminada")


def canchas_verificadas() -> list[dict]:
    """Canchas RESERVABLES en la web (las mismas que el APK deja reservar)."""
    return [c for c in canchas_publicas() if reservable(c)]


def cancha(cancha_id: str) -> dict | None:
    if not pg.habilitado or not cancha_id:
        return None
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT {COLS_CANCHA} FROM pichangol_canchas WHERE id = %s",
                        (cancha_id,))
            f = cur.fetchone()
            return _norm_cancha(pg._fila_a_dict(_COLS, f)) if f else None
    except Exception:  # noqa: BLE001
        return None


def ocupados(cancha_id: str, fechas: list[str]) -> set[tuple[str, str]]:
    """(fecha, hora_inicio) tomados: reservas vigentes (no-show no ocupa) +
    bloqueos del dueño. Incluye las reservas web en espera de pago."""
    if not pg.habilitado or not fechas:
        return set()
    out: set[tuple[str, str]] = set()
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT fecha, hora_inicio FROM pichangol_reservas "
                "WHERE cancha_id = %s AND fecha = ANY(%s) "
                "AND coalesce(estado,'') <> 'noShow'", (cancha_id, fechas))
            out.update((str(f), str(h)) for f, h in cur.fetchall())
            try:
                cur.execute(
                    "SELECT fecha, hora FROM pichangol_bloqueos "
                    "WHERE cancha_id = %s AND fecha = ANY(%s)", (cancha_id, fechas))
                out.update((str(f), str(h)) for f, h in cur.fetchall())
            except Exception:  # noqa: BLE001 — tabla opcional
                conn.rollback()
    except Exception:  # noqa: BLE001
        pass
    return out


def descuentos(cancha_id: str, fechas: list[str]) -> dict[tuple[str, str], int]:
    """Descuentos puntuales por slot que puso el dueño (%), por (fecha, hora)."""
    if not pg.habilitado or not fechas:
        return {}
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT fecha, hora, pct FROM pichangol_descuentos_slot "
                "WHERE cancha_id = %s AND fecha = ANY(%s)", (cancha_id, fechas))
            return {(str(f), str(h)): int(p or 0) for f, h, p in cur.fetchall()}
    except Exception:  # noqa: BLE001
        return {}


def liberar_holds_vencidos(cancha_id: str) -> int:
    """Borra reservas WEB que quedaron 'nueva' (sin pagar) hace más de
    HOLD_SEGUNDOS. El momento vive en el id (`web_<epoch_ms>_n`): la tabla no
    tiene columna de creación."""
    if not pg.habilitado:
        return 0
    corte = int((time.time() - HOLD_SEGUNDOS) * 1000)
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM pichangol_reservas WHERE cancha_id = %s "
                "AND estado = 'nueva' AND id LIKE %s "
                "AND split_part(id, '_', 2) ~ '^[0-9]+$' "
                "AND split_part(id, '_', 2)::bigint < %s",
                (cancha_id, PREFIJO_ID_WEB + "%", corte))
            n = cur.rowcount
            conn.commit()
            return n
    except Exception:  # noqa: BLE001
        return 0


def insertar_reservas(filas: list[dict]) -> str:
    """Inserta el bloque en UNA transacción. Devuelve '' si entró, 'ocupado'
    si algún slot ya estaba tomado (UNIQUE) o 'error'."""
    if not pg.habilitado or not filas:
        return "error"
    cols = ["id", "cancha_id", "jugador", "nivel", "fecha", "dia", "hora_inicio",
            "hora_fin", "estado", "traida_por_app", "precio", "sena", "pagado",
            "usuario", "deporte", "moneda", "extras", "telefono",
            "grupo_reserva_id", "medio_pago"]
    sql = (f"INSERT INTO pichangol_reservas ({', '.join(cols)}) VALUES "
           f"({', '.join(['%s'] * len(cols))})")
    try:
        with pg.conexion() as conn:
            try:
                with conn.cursor() as cur:
                    for f in filas:
                        vals = [f.get(c) for c in cols]
                        vals[cols.index("extras")] = json.dumps(f.get("extras") or [])
                        cur.execute(sql, vals)
                conn.commit()
                return ""
            except Exception as e:  # noqa: BLE001
                conn.rollback()
                msg = str(e).lower()
                if "uniq_slot_reserva" in msg or "duplicate key" in msg or "unique" in msg:
                    return "ocupado"
                return "error"
    except Exception:  # noqa: BLE001
        return "error"


def confirmar_reservas(ids: list[str], medio_pago: str) -> bool:
    if not pg.habilitado or not ids:
        return False
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE pichangol_reservas SET estado = 'confirmada', pagado = true, "
                "medio_pago = %s WHERE id = ANY(%s)", (medio_pago, ids))
            conn.commit()
            return True
    except Exception:  # noqa: BLE001
        return False


def borrar_reservas(ids: list[str]) -> bool:
    if not pg.habilitado or not ids:
        return False
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM pichangol_reservas WHERE id = ANY(%s) "
                        "AND estado = 'nueva'", (ids,))
            conn.commit()
            return True
    except Exception:  # noqa: BLE001
        return False


_COLS_RES = ["id", "cancha_id", "jugador", "fecha", "dia", "hora_inicio", "hora_fin",
             "estado", "precio", "sena", "pagado", "usuario", "moneda", "extras",
             "telefono", "grupo_reserva_id", "medio_pago"]


def reservas_de(ids: list[str]) -> list[dict]:
    if not pg.habilitado or not ids:
        return []
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute(
                f"SELECT {', '.join(_COLS_RES)} FROM pichangol_reservas "
                "WHERE id = ANY(%s) ORDER BY fecha, hora_inicio", (ids,))
            out = []
            for f in cur.fetchall():
                d = pg._fila_a_dict(_COLS_RES, f)
                d["extras"] = _json_list(d.get("extras"))
                d["precio"] = int(round(float(d.get("precio") or 0)))
                out.append(d)
            return out
    except Exception:  # noqa: BLE001
        return []


def reservas_por_grupo(grupo: str) -> list[dict]:
    if not pg.habilitado or not grupo:
        return []
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute(
                f"SELECT {', '.join(_COLS_RES)} FROM pichangol_reservas "
                "WHERE grupo_reserva_id = %s ORDER BY fecha, hora_inicio", (grupo,))
            out = []
            for f in cur.fetchall():
                d = pg._fila_a_dict(_COLS_RES, f)
                d["extras"] = _json_list(d.get("extras"))
                d["precio"] = int(round(float(d.get("precio") or 0)))
                out.append(d)
            return out
    except Exception:  # noqa: BLE001
        return []
