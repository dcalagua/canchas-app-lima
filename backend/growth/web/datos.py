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
# FIDELIDAD DEL LOCAL (SQL `docs/piloto/supabase_fidelidad.sql`): la columna
# `fidelidad` se lee solo si existe en esta base (chequeo cacheado), igual que
# las columnas del cargo por servicio en reservas.
_col_fid_cache: dict = {}


def _col_cancha_existe(nombre: str) -> bool:
    """¿Existe la columna `nombre` en `pichangol_canchas`? (cacheado). Las
    columnas nuevas se leen/escriben solo si su SQL ya corrió en esta base."""
    if nombre in _col_fid_cache:
        return _col_fid_cache[nombre]
    if not pg.habilitado:
        return False
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM information_schema.columns WHERE table_schema = 'public' "
                        "AND table_name = 'pichangol_canchas' AND column_name = %s", (nombre,))
            ok = int(cur.fetchone()[0]) == 1
    except Exception:  # noqa: BLE001
        return False
    _col_fid_cache[nombre] = ok
    return ok


def col_fidelidad_disponible() -> bool:
    return _col_cancha_existe("fidelidad")


def col_precio_turno_disponible() -> bool:
    """PRECIO POR TURNO (SQL `docs/piloto/supabase_precio_turno.sql`)."""
    return _col_cancha_existe("precio_turno")


def _cols_cancha() -> list[str]:
    return (_COLS + (["fidelidad"] if col_fidelidad_disponible() else [])
            + (["precio_turno"] if col_precio_turno_disponible() else []))


def _sel_cancha() -> str:
    return ", ".join(_cols_cancha())

PREFIJO_ID_WEB = "web_"
# Un apartado web sin pagar con más de HOLD_SEGUNDOS NO ocupa el turno (caso
# real PRD, 1-oct-2026: uno abandonado bloqueó las 20:00 toda la noche porque
# solo se borraba cuando otro cliente intentaba reservar esa cancha).
_SQL_SIN_HOLD_VENCIDO = (
    " AND NOT (coalesce(estado,'') = 'nueva' AND NOT coalesce(pagado,false) AND id LIKE 'web\\_%%' "
    "AND (CASE WHEN split_part(id, '_', 2) ~ '^[0-9]+$' THEN split_part(id, '_', 2)::bigint ELSE NULL END) < %s)")


def _corte_hold() -> int:
    return int((time.time() - HOLD_SEGUNDOS) * 1000)
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


def _json_dict(v) -> dict:
    if isinstance(v, dict):
        return v
    if v is None:
        return {}
    try:
        j = json.loads(v)
        return j if isinstance(j, dict) else {}
    except (TypeError, ValueError):
        return {}


def _norm_cancha(d: dict) -> dict:
    d = dict(d)
    d["fidelidad"] = _json_dict(d.get("fidelidad"))
    d["deportes"] = _json_list(d.get("deportes"))
    d["fotos"] = _json_list(d.get("fotos"))
    d["servicios_extra"] = [
        s for s in _json_list(d.get("servicios_extra")) if isinstance(s, dict)]
    d["amenidades"] = _json_list(d.get("amenidades"))
    d["precio_hora"] = float(d.get("precio_hora") or 0)
    d["precio_turno"] = float(d.get("precio_turno") or 0)
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
                f"SELECT {_sel_cancha()} FROM pichangol_canchas "
                "WHERE coalesce(registrada,true) AND NOT coalesce(eliminada,false) "
                "ORDER BY (coalesce(verificada,false) AND coalesce(dueno,'') <> '') DESC, club, nombre")
            return [_norm_cancha(pg._fila_a_dict(_cols_cancha(), f)) for f in cur.fetchall()]
    except Exception:  # noqa: BLE001
        return []


def reservable(c: dict) -> bool:
    """Reservable en línea = verificada + con dueño (igual que `Cancha.reservable`)."""
    return bool(c.get("verificada")) and bool((c.get("dueno") or "").strip()) and not c.get("eliminada")


def canchas_verificadas() -> list[dict]:
    """Canchas RESERVABLES en la web (las mismas que el APK deja reservar)."""
    return [c for c in canchas_publicas() if reservable(c)]


def canchas_de_dueno(email: str) -> list[dict]:
    """Canchas del DUEÑO (modo anfitrión web): registradas, no eliminadas,
    `dueno` = correo de Google (mismo criterio que "Mis canchas" del app)."""
    email = (email or "").strip().lower()
    if not pg.habilitado or not email:
        return []
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT {_sel_cancha()} FROM pichangol_canchas WHERE lower(dueno) = %s "
                        "AND coalesce(eliminada,false) = false ORDER BY verificada DESC, nombre", (email,))
            return [_norm_cancha(pg._fila_a_dict(_cols_cancha(), f)) for f in cur.fetchall()]
    except Exception:  # noqa: BLE001
        return []


# Columnas que el dueño puede EDITAR desde la web (espejo del formulario del
# app `editar_cancha_screen`). Cualquier otra clave se ignora.
COLS_EDITABLES = {
    "nombre", "club", "deporte", "deportes", "precio_hora", "hora_apertura",
    "hora_cierre", "duracion_slot_min", "descuento_valle", "valle_desde",
    "valle_hasta", "sena_pct", "superficie", "amenidades", "servicios_extra",
    "fotos", "foto_url", "direccion", "fidelidad", "precio_turno",
}
_COLS_JSON = {"deportes", "amenidades", "servicios_extra", "fotos", "fidelidad"}


def actualizar_cancha(cancha_id: str, dueno: str, campos: dict) -> bool:
    """UPDATE de la cancha del DUEÑO (modo anfitrión web). Solo toca la fila
    si `lower(dueno)` = correo de la sesión y no está eliminada: nadie edita
    una cancha ajena aunque conozca el id. Devuelve True si cambió 1 fila."""
    dueno = (dueno or "").strip().lower()
    sets = {k: v for k, v in (campos or {}).items() if k in COLS_EDITABLES}
    if "precio_turno" in sets and not col_precio_turno_disponible():
        sets.pop("precio_turno")  # sin el SQL, precio_hora ya lleva el equivalente
    if "fidelidad" in sets and not col_fidelidad_disponible():
        sets.pop("fidelidad")
    if not pg.habilitado or not cancha_id or not dueno or not sets:
        return False
    cols = sorted(sets)
    vals = [json.dumps(sets[c]) if c in _COLS_JSON else sets[c] for c in cols]
    asig = ", ".join(f"{c} = %s::jsonb" if c in _COLS_JSON else f"{c} = %s" for c in cols)
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute(f"UPDATE pichangol_canchas SET {asig} WHERE id = %s AND lower(dueno) = %s "
                        "AND coalesce(eliminada,false) = false", vals + [cancha_id, dueno])
            n = cur.rowcount
            conn.commit()
            return n == 1
    except Exception as e:  # noqa: BLE001
        print(f"[editar-web] no se pudo guardar {cancha_id}: {e}", flush=True)
        return False


# Columnas que escribe el REGISTRO desde la web (espejo de `CanchasRepo._toRow`
# del app al registrar: la fila nace `registrada`, `verificada=false` y con
# `dueno` = correo de Google; la torre la activa al aprobar el reclamo).
COLS_REGISTRO = [
    "id", "nombre", "club", "distrito", "barrio", "deporte", "deportes", "precio_hora", "lat", "lng",
    "club_fundador", "digitalizada", "direccion", "registrada", "foto_url", "fotos", "dueno", "verificada",
    "hora_apertura", "hora_cierre", "duracion_slot_min", "eliminada", "amenidades", "superficie", "moneda",
    "servicios_extra", "descuento_valle", "valle_desde", "valle_hasta", "sena_pct",
]


def insertar_canchas(filas: list[dict]) -> bool:
    """INSERT de las canchas recién REGISTRADAS desde la web (una por deporte
    si son canchas separadas). Todo o nada: si una falla, ninguna queda."""
    if not pg.habilitado or not filas:
        return False
    cols = COLS_REGISTRO + (["precio_turno"] if col_precio_turno_disponible() else [])
    marcas = ", ".join("%s::jsonb" if c in _COLS_JSON else "%s" for c in cols)
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            for f in filas:
                vals = [json.dumps(f.get(c) if f.get(c) is not None else []) if c in _COLS_JSON else f.get(c) for c in cols]
                cur.execute(f"INSERT INTO pichangol_canchas ({', '.join(cols)}) VALUES ({marcas})", vals)
            conn.commit()
            return True
    except Exception as e:  # noqa: BLE001
        print(f"[registro-web] no se pudo insertar: {e}", flush=True)
        return False


def borrar_canchas(ids: list[str], dueno: str) -> int:
    """DELETE físico de canchas del dueño recién registradas (se revierte un
    registro que la torre no aceptó, p. ej. el lugar ya tenía reclamo ajeno).
    Solo borra filas del propio correo y aún NO verificadas."""
    dueno = (dueno or "").strip().lower()
    if not pg.habilitado or not ids or not dueno:
        return 0
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM pichangol_canchas WHERE id = ANY(%s) AND lower(dueno) = %s "
                        "AND coalesce(verificada,false) = false", (list(ids), dueno))
            n = cur.rowcount
            conn.commit()
            return n
    except Exception as e:  # noqa: BLE001
        print(f"[registro-web] no se pudo revertir: {e}", flush=True)
        return 0


COLS_ADOPCION = {"nombre", "club", "deporte", "deportes", "superficie", "precio_hora", "hora_apertura", "hora_cierre",
                 "duracion_slot_min", "barrio", "direccion", "fotos", "foto_url", "moneda", "precio_turno"}


def adoptar_cancha(cancha_id: str, dueno: str, campos: dict) -> bool:
    """RECLAMO de una cancha ya registrada SIN dueño (legado reclamable, mismo
    criterio que `AppState.misCanchas`): la pone a nombre del correo y actualiza
    lo que el dueño completó. Solo si sigue sin dueño y sin verificar."""
    dueno = (dueno or "").strip().lower()
    sets = {k: v for k, v in (campos or {}).items() if k in COLS_ADOPCION}
    if "precio_turno" in sets and not col_precio_turno_disponible():
        sets.pop("precio_turno")
    if not pg.habilitado or not cancha_id or not dueno:
        return False
    cols = sorted(sets)
    vals = [json.dumps(sets[c]) if c in _COLS_JSON else sets[c] for c in cols]
    asig = ", ".join([f"{c} = %s::jsonb" if c in _COLS_JSON else f"{c} = %s" for c in cols] + ["dueno = %s"])
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute(f"UPDATE pichangol_canchas SET {asig} WHERE id = %s AND coalesce(dueno,'') = '' "
                        "AND coalesce(verificada,false) = false AND coalesce(eliminada,false) = false",
                        vals + [dueno, cancha_id])
            n = cur.rowcount
            conn.commit()
            return n == 1
    except Exception as e:  # noqa: BLE001
        print(f"[reclamo-web] no se pudo adoptar {cancha_id}: {e}", flush=True)
        return False


def desadoptar_cancha(cancha_id: str, dueno: str) -> bool:
    """Revierte `adoptar_cancha` (el reclamo no se pudo crear)."""
    dueno = (dueno or "").strip().lower()
    if not pg.habilitado or not cancha_id or not dueno:
        return False
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE pichangol_canchas SET dueno = '' WHERE id = %s AND lower(dueno) = %s "
                        "AND coalesce(verificada,false) = false", (cancha_id, dueno))
            n = cur.rowcount
            conn.commit()
            return n == 1
    except Exception:  # noqa: BLE001
        return False


def marcar_verificada(cancha_id: str, dueno: str, verificada: bool, lat: float | None = None, lng: float | None = None) -> int:
    """La torre aprobó (o rechazó) el reclamo: refleja `verificada` en la
    NUBE para la cancha reclamada y sus HERMANAS: mismo registro (`u<ts>` /
    `u<ts>_<deporte>`, el app reclama solo la primera) o, para canchas de
    legado reclamadas, las del mismo dueño en el MISMO lugar (≈150 m).
    Antes solo el APK escribía esto al sincronizar; un dueño que registró
    desde la web no abría el app y su cancha nunca quedaba reservable."""
    dueno = (dueno or "").strip().lower()
    if not pg.habilitado or not cancha_id or not dueno:
        return 0
    base = cancha_id.split("_")[0]
    cerca = "OR (abs(lat - %s) < 0.0014 AND abs(lng - %s) < 0.0014)" if lat is not None and lng is not None else ""
    extra = [lat, lng] if cerca else []
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE pichangol_canchas SET verificada = %s WHERE lower(dueno) = %s "
                        f"AND (id = %s OR id LIKE %s {cerca}) AND coalesce(eliminada,false) = false",
                        [bool(verificada), dueno, cancha_id, base + "\\_%"] + extra)  # hermanas u<ts>_<deporte>
            n = cur.rowcount
            conn.commit()
            return n
    except Exception as e:  # noqa: BLE001
        print(f"[reclamo-web] no se pudo marcar verificada={verificada} {cancha_id}: {e}", flush=True)
        return 0


def bloquear(cancha_id: str, fecha: str, hora: str, bloquear: bool = True) -> bool:
    """Bloqueo de un turno por el dueño (misma tabla y clave que
    `BloqueosRepo` del app: PK (cancha_id, fecha, hora)). Idempotente."""
    if not pg.habilitado or not cancha_id or not fecha or not hora:
        return False
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            if bloquear:
                cur.execute("INSERT INTO pichangol_bloqueos (cancha_id, fecha, hora) VALUES (%s, %s, %s) "
                            "ON CONFLICT DO NOTHING", (cancha_id, fecha, hora))
            else:
                cur.execute("DELETE FROM pichangol_bloqueos WHERE cancha_id = %s AND fecha = %s AND hora = %s",
                            (cancha_id, fecha, hora))
            conn.commit()
            return True
    except Exception as e:  # noqa: BLE001
        print(f"[bloqueo-web] falló {cancha_id} {fecha} {hora}: {e}", flush=True)
        return False


def reserva_de_dueno(res_id: str, cancha_ids: list[str]) -> dict | None:
    """Una reserva SOLO si es de una cancha del dueño (candado del WHERE)."""
    if not pg.habilitado or not res_id or not cancha_ids:
        return None
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT {', '.join(_cols_res())} FROM pichangol_reservas WHERE id = %s AND cancha_id = ANY(%s)",
                        (res_id, cancha_ids))
            f = cur.fetchone()
            if not f:
                return None
            d = pg._fila_a_dict(_cols_res(), f)
            d["extras"] = _json_list(d.get("extras"))
            d["precio"] = int(round(float(d.get("precio") or 0)))
            return d
    except Exception:  # noqa: BLE001
        return None


def marcar_pagado(res_id: str, cancha_ids: list[str], pagado: bool) -> bool:
    """Marca cobrada (o vuelve a "por cobrar") una reserva de una cancha del
    dueño: lo mismo que `marcarPago` del app (`pagado`)."""
    if not pg.habilitado or not res_id or not cancha_ids:
        return False
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE pichangol_reservas SET pagado = %s WHERE id = %s AND cancha_id = ANY(%s)",
                        (pagado, res_id, cancha_ids))
            n = cur.rowcount
            conn.commit()
            return n == 1
    except Exception:  # noqa: BLE001
        return False


def borrar_reserva_manual(res_id: str, cancha_ids: list[str]) -> bool:
    """Quita una reserva MANUAL (la registró el dueño) de una cancha suya.
    Las reservas pagadas por la app/web se cancelan con reembolso, no aquí."""
    if not pg.habilitado or not res_id or not cancha_ids:
        return False
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM pichangol_reservas WHERE id = %s AND cancha_id = ANY(%s) "
                        "AND coalesce(medio_pago,'') = 'manual'", (res_id, cancha_ids))
            n = cur.rowcount
            conn.commit()
            return n == 1
    except Exception:  # noqa: BLE001
        return False


def reservas_de_canchas(ids: list[str], desde: str, hasta: str) -> list[dict]:
    """Agenda del dueño: reservas de sus canchas entre dos fechas (ISO,
    inclusive), sin las retenciones web sin pagar ni las canceladas."""
    if not pg.habilitado or not ids:
        return []
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute(
                f"SELECT {', '.join(_cols_res())} FROM pichangol_reservas "
                "WHERE cancha_id = ANY(%s) AND fecha BETWEEN %s AND %s "
                "AND NOT (coalesce(estado,'') = 'nueva' AND NOT coalesce(pagado,false)) "
                "AND coalesce(estado,'') <> 'cancelada' ORDER BY fecha, hora_inicio", (ids, desde, hasta))
            out = []
            for f in cur.fetchall():
                d = pg._fila_a_dict(_cols_res(), f)
                d["extras"] = _json_list(d.get("extras"))
                d["precio"] = int(round(float(d.get("precio") or 0)))
                out.append(d)
            return out
    except Exception:  # noqa: BLE001
        return []


def bloqueos_de(ids: list[str], fechas: list[str]) -> set[tuple[str, str, str]]:
    """(cancha_id, fecha, hora) bloqueados por el dueño (tabla opcional)."""
    if not pg.habilitado or not ids or not fechas:
        return set()
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT cancha_id, fecha, hora FROM pichangol_bloqueos "
                        "WHERE cancha_id = ANY(%s) AND fecha = ANY(%s)", (ids, fechas))
            return {(str(c), str(f), str(h)) for c, f, h in cur.fetchall()}
    except Exception:  # noqa: BLE001
        return set()


def cancha(cancha_id: str) -> dict | None:
    if not pg.habilitado or not cancha_id:
        return None
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT {_sel_cancha()} FROM pichangol_canchas WHERE id = %s",
                        (cancha_id,))
            f = cur.fetchone()
            return _norm_cancha(pg._fila_a_dict(_cols_cancha(), f)) if f else None
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
                "AND coalesce(estado,'') <> 'noShow'" + _SQL_SIN_HOLD_VENCIDO, (cancha_id, fechas, _corte_hold()))
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


def ocupados_varias(ids: list[str], fechas: list[str]) -> dict[str, set[tuple[str, str]]]:
    """Como `ocupados`, pero para MUCHAS canchas en una sola consulta (el
    buscador de la portada pregunta por todas a la vez)."""
    if not pg.habilitado or not ids or not fechas:
        return {}
    out: dict[str, set[tuple[str, str]]] = {}
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT cancha_id, fecha, hora_inicio FROM pichangol_reservas "
                "WHERE cancha_id = ANY(%s) AND fecha = ANY(%s) "
                "AND coalesce(estado,'') <> 'noShow'" + _SQL_SIN_HOLD_VENCIDO, (ids, fechas, _corte_hold()))
            for cid, f, h in cur.fetchall():
                out.setdefault(str(cid), set()).add((str(f), str(h)))
            try:
                cur.execute(
                    "SELECT cancha_id, fecha, hora FROM pichangol_bloqueos "
                    "WHERE cancha_id = ANY(%s) AND fecha = ANY(%s)", (ids, fechas))
                for cid, f, h in cur.fetchall():
                    out.setdefault(str(cid), set()).add((str(f), str(h)))
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


def liberar_holds_vencidos_todos() -> list[dict]:
    """Borra los apartados web vencidos de TODAS las canchas (cron de 1 min en
    `main.py`). Devuelve lo borrado (para el log)."""
    if not pg.habilitado:
        return []
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM pichangol_reservas WHERE estado = 'nueva' AND NOT coalesce(pagado,false) "
                "AND id LIKE %s AND split_part(id, '_', 2) ~ '^[0-9]+$' "
                "AND split_part(id, '_', 2)::bigint < %s RETURNING id, cancha_id, fecha, hora_inicio",
                (PREFIJO_ID_WEB.replace("_", "\\_") + "%", _corte_hold()))
            filas = [{"id": a, "cancha_id": b, "fecha": str(c), "hora": str(d)} for a, b, c, d in cur.fetchall()]
            conn.commit()
            return filas
    except Exception as ex:  # noqa: BLE001
        print(f"[holds] no se pudo liberar: {ex}", flush=True)
        return []


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


def confirmar_reservas(ids: list[str], medio_pago: str, cargo_soles: float = 0.0, cargo_desglose: list | None = None,
                       pagado: bool = True) -> bool:
    """Confirma el bloque pagado. El CARGO POR SERVICIO (si lo hubo) queda en la
    PRIMERA fila del bloque (como los extras), si la base tiene las columnas."""
    if not pg.habilitado or not ids:
        return False
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE pichangol_reservas SET estado = 'confirmada', pagado = %s, "
                "medio_pago = %s WHERE id = ANY(%s)", (bool(pagado), medio_pago, ids))
            if cargo_soles and cargo_soles > 0 and col_cargo_disponible():
                cur.execute("UPDATE pichangol_reservas SET cargo_servicio = %s, cargo_desglose = %s WHERE id = %s",
                            (round(float(cargo_soles), 2), json.dumps(cargo_desglose or []), ids[0]))
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
# Columnas del cargo por servicio (SQL `docs/piloto/supabase_reservas_cargo.sql`).
# Se leen/escriben solo si existen en esta base (chequeo cacheado): así la web
# no se rompe en un ambiente donde el SQL aún no corrió.
_COLS_CARGO = ["cargo_servicio", "cargo_desglose"]
_col_cargo_cache: dict = {}


def col_cargo_disponible() -> bool:
    if "ok" in _col_cargo_cache:
        return _col_cargo_cache["ok"]
    if not pg.habilitado:
        return False
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM information_schema.columns WHERE table_schema = 'public' "
                        "AND table_name = 'pichangol_reservas' AND column_name = ANY(%s)", (_COLS_CARGO,))
            ok = int(cur.fetchone()[0]) == len(_COLS_CARGO)
    except Exception:  # noqa: BLE001
        return False  # sin cachear: se reintenta en la siguiente
    _col_cargo_cache["ok"] = ok
    return ok


def _cols_res() -> list[str]:
    return _COLS_RES + (_COLS_CARGO if col_cargo_disponible() else [])


def eliminar_reservas(ids: list[str]) -> bool:
    """Cancelación: borra las filas (como hace el app al cancelar) para liberar
    el horario. El historial y la plata quedan en el backend growth."""
    if not pg.habilitado or not ids:
        return False
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM pichangol_reservas WHERE id = ANY(%s)", (ids,))
            conn.commit()
            return True
    except Exception:  # noqa: BLE001
        return False


def reservas_de(ids: list[str]) -> list[dict]:
    if not pg.habilitado or not ids:
        return []
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute(
                f"SELECT {', '.join(_cols_res())} FROM pichangol_reservas "
                "WHERE id = ANY(%s) ORDER BY fecha, hora_inicio", (ids,))
            out = []
            for f in cur.fetchall():
                d = pg._fila_a_dict(_cols_res(), f)
                d["extras"] = _json_list(d.get("extras"))
                d["precio"] = int(round(float(d.get("precio") or 0)))
                out.append(d)
            return out
    except Exception:  # noqa: BLE001
        return []


def reservas_de_usuario(email: str, limite: int = 200) -> list[dict]:
    """Reservas del CORREO de Google (`usuario`), las mismas que ve "Mis
    reservas" del app: pagadas o confirmadas (incluye efectivo), canceladas y
    no-show; se omiten las retenciones web sin pagar (estado `nueva`)."""
    email = (email or "").strip().lower()
    if not pg.habilitado or not email:
        return []
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute(
                f"SELECT {', '.join(_cols_res())} FROM pichangol_reservas "
                "WHERE lower(usuario) = %s AND NOT (coalesce(estado,'') = 'nueva' AND NOT coalesce(pagado,false)) "
                "ORDER BY fecha DESC, hora_inicio DESC LIMIT %s", (email, limite))
            out = []
            for f in cur.fetchall():
                d = pg._fila_a_dict(_cols_res(), f)
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
                f"SELECT {', '.join(_cols_res())} FROM pichangol_reservas "
                "WHERE grupo_reserva_id = %s ORDER BY fecha, hora_inicio", (grupo,))
            out = []
            for f in cur.fetchall():
                d = pg._fila_a_dict(_cols_res(), f)
                d["extras"] = _json_list(d.get("extras"))
                d["precio"] = int(round(float(d.get("precio") or 0)))
                out.append(d)
            return out
    except Exception:  # noqa: BLE001
        return []


# ── MODO ANFITRIÓN: academias, alumnos, tienda (mismas tablas del app) ─────────
# `pichangol_academias` (id, dueno, data jsonb, eliminada), `pichangol_matriculas`
# (id, academia_id, email, data jsonb, eliminada), `pichangol_productos` (columnas
# planas, ver `Producto.toRow`), `pichangol_verificaciones` (email, estado).

def _json_dict(v) -> dict:
    if isinstance(v, dict):
        return v
    try:
        j = json.loads(v) if v else {}
        return j if isinstance(j, dict) else {}
    except (TypeError, ValueError):
        return {}


def academias_publicas() -> list[dict]:
    """Todas las academias no eliminadas (para el explorador web: salen por
    deporte y por cercanía como las canchas). `data` = `Academia.toJson`."""
    if not pg.habilitado:
        return []
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id, data FROM pichangol_academias WHERE coalesce(eliminada,false) = false "
                        "ORDER BY updated_at DESC LIMIT 500")
            out = []
            for aid, data in cur.fetchall():
                d = _json_dict(data)
                d["id"] = aid
                out.append(d)
            return out
    except Exception:  # noqa: BLE001
        return []


def academia(academia_id: str) -> dict | None:
    """Una academia por id (no eliminada), con `id` y `dueno` dentro del dict."""
    if not pg.habilitado or not academia_id:
        return None
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id, dueno, data FROM pichangol_academias WHERE id = %s AND coalesce(eliminada,false) = false", (academia_id,))
            row = cur.fetchone()
            if not row:
                return None
            d = _json_dict(row[2])
            d["id"] = row[0]
            d["dueno"] = row[1] or d.get("dueno") or ""
            return d
    except Exception:  # noqa: BLE001
        return None


def insertar_matricula(alumno_id: str, academia_id: str, email: str, data: dict) -> bool:
    """Fila de `pichangol_matriculas` con la MISMA forma que `MatriculasRepo.guardar`
    del app (`data` = `Alumno.toJson` + `cuotas`). Solo inserta (id nuevo)."""
    if not pg.habilitado or not alumno_id or not academia_id:
        return False
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO pichangol_matriculas (id, academia_id, email, data, eliminada, updated_at) "
                        "VALUES (%s, %s, %s, %s::jsonb, false, now()) ON CONFLICT (id) DO NOTHING",
                        (alumno_id, academia_id, (email or "").strip().lower(), json.dumps(data)))
            n = cur.rowcount
            conn.commit()
            return n == 1
    except Exception as e:  # noqa: BLE001
        print(f"[matricula-web] no se pudo guardar {alumno_id}: {e}", flush=True)
        return False


def matriculas_de_pagador(academia_id: str, email: str) -> list[dict]:
    """Matrículas que PAGA este correo en la academia (titular + pareja +
    hijos): base del orden del descuento familiar. ESPEJO de lo que el app
    cuenta en `Academia.ordenFamiliarPara`."""
    email = (email or "").strip().lower()
    if not pg.habilitado or not academia_id or not email:
        return []
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id, academia_id, email, data FROM pichangol_matriculas WHERE academia_id = %s AND lower(email) = %s "
                        "AND coalesce(eliminada,false) = false ORDER BY id", (academia_id, email))
            out = []
            for mid, aid, em, data in cur.fetchall():
                d = _json_dict(data)
                d["id"] = mid
                d.setdefault("academiaId", aid)
                d.setdefault("email", em or "")
                out.append(d)
            return out
    except Exception:  # noqa: BLE001
        return []


def matricula(alumno_id: str) -> dict | None:
    """Una matrícula por id (no eliminada): `data` + `id`, `academiaId`, `email`."""
    if not pg.habilitado or not alumno_id:
        return None
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id, academia_id, email, data FROM pichangol_matriculas WHERE id = %s AND coalesce(eliminada,false) = false", (alumno_id,))
            row = cur.fetchone()
            if not row:
                return None
            d = _json_dict(row[3])
            d.setdefault("id", row[0])
            d["academiaId"] = row[1]
            d.setdefault("email", row[2] or "")
            return d
    except Exception:  # noqa: BLE001
        return None


def matriculas_por_operacion(academia_id: str, operacion: str) -> list[dict]:
    """Matrículas de la academia con alguna cuota pagada con ese N.º de
    operación (`cuotas[].operacionId`): las personas de UN pago (carrito,
    familia o cuotas sueltas). Para el correo de pago (`correos.py`)."""
    operacion = (operacion or "").strip()
    if not pg.habilitado or not operacion or len(operacion) < 6:
        return []
    patron = "%" + operacion.replace("\\", "").replace("%", "").replace("_", "\\_") + "%"
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            if academia_id:
                cur.execute("SELECT id, academia_id, email, data FROM pichangol_matriculas WHERE academia_id = %s "
                            "AND coalesce(eliminada,false) = false AND data::text LIKE %s ORDER BY id LIMIT 20",
                            (academia_id, patron))
            else:
                cur.execute("SELECT id, academia_id, email, data FROM pichangol_matriculas WHERE "
                            "coalesce(eliminada,false) = false AND data::text LIKE %s ORDER BY id LIMIT 20", (patron,))
            out = []
            for mid, aid, em, data in cur.fetchall():
                d = _json_dict(data)
                d["id"] = mid
                d["academiaId"] = aid
                d.setdefault("email", em or "")
                out.append(d)
            return out
    except Exception:  # noqa: BLE001
        return []


def academias_de_dueno(email: str) -> list[dict]:
    email = (email or "").strip().lower()
    if not pg.habilitado or not email:
        return []
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id, data FROM pichangol_academias WHERE lower(dueno) = %s "
                        "AND coalesce(eliminada,false) = false ORDER BY updated_at DESC", (email,))
            out = []
            for aid, data in cur.fetchall():
                d = _json_dict(data)
                d["id"] = aid
                out.append(d)
            return out
    except Exception:  # noqa: BLE001
        return []


def guardar_academia(academia_id: str, dueno: str, data: dict) -> bool:
    """UPSERT por id (como `AcademiasRepo.guardar`). Si el id ya existe a nombre
    de OTRO correo, no se toca (el WHERE del ON CONFLICT lo impide)."""
    dueno = (dueno or "").strip().lower()
    if not pg.habilitado or not academia_id or not dueno:
        return False
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO pichangol_academias (id, dueno, data, eliminada, updated_at) VALUES (%s, %s, %s::jsonb, false, now()) "
                "ON CONFLICT (id) DO UPDATE SET data = EXCLUDED.data, eliminada = false, updated_at = now() "
                "WHERE lower(pichangol_academias.dueno) = %s", (academia_id, dueno, json.dumps(data), dueno))
            n = cur.rowcount
            conn.commit()
            return n == 1
    except Exception as e:  # noqa: BLE001
        print(f"[academia-web] no se pudo guardar {academia_id}: {e}", flush=True)
        return False


def eliminar_academia(academia_id: str, dueno: str) -> bool:
    """Borrado lógico (como el app)."""
    dueno = (dueno or "").strip().lower()
    if not pg.habilitado or not academia_id or not dueno:
        return False
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE pichangol_academias SET eliminada = true, updated_at = now() "
                        "WHERE id = %s AND lower(dueno) = %s", (academia_id, dueno))
            n = cur.rowcount
            conn.commit()
            return n == 1
    except Exception:  # noqa: BLE001
        return False


def matriculas_de_academias(ids: list[str]) -> list[dict]:
    """Alumnos (con sus cuotas dentro de `data`) de las academias dadas."""
    if not pg.habilitado or not ids:
        return []
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id, academia_id, email, data FROM pichangol_matriculas "
                        "WHERE academia_id = ANY(%s) AND coalesce(eliminada,false) = false", (ids,))
            out = []
            for mid, aid, em, data in cur.fetchall():
                d = _json_dict(data)
                d.setdefault("id", mid)
                d["academiaId"] = aid
                d.setdefault("email", em or "")
                out.append(d)
            return out
    except Exception:  # noqa: BLE001
        return []


_COLS_PROD = ["id", "vendedor_email", "vendedor_nombre", "nombre", "descripcion", "precio", "moneda",
              "categoria", "foto_url", "stock", "activo", "creado_en"]


def _norm_producto(d: dict) -> dict:
    d["precio"] = float(d.get("precio") or 0)
    d["stock"] = int(d["stock"]) if d.get("stock") is not None else None
    d["activo"] = bool(d.get("activo"))
    for k in ("nombre", "descripcion", "moneda", "categoria", "foto_url", "vendedor_nombre", "vendedor_email"):
        d[k] = d.get(k) or ""
    return d


def productos_de_vendedor(email: str) -> list[dict]:
    email = (email or "").strip().lower()
    if not pg.habilitado or not email:
        return []
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT {', '.join(_COLS_PROD)} FROM pichangol_productos WHERE lower(vendedor_email) = %s "
                        "ORDER BY creado_en DESC", (email,))
            return [_norm_producto(pg._fila_a_dict(_COLS_PROD, f)) for f in cur.fetchall()]
    except Exception:  # noqa: BLE001
        return []


def guardar_producto(fila: dict) -> bool:
    """UPSERT por id (como `ProductosRepo.guardar`); si el id es de otro
    vendedor no se toca."""
    if not pg.habilitado or not fila.get("id") or not fila.get("vendedor_email"):
        return False
    cols = [c for c in _COLS_PROD if c in fila]
    upd = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c not in ("id", "vendedor_email", "creado_en"))
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute(
                f"INSERT INTO pichangol_productos ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))}) "
                f"ON CONFLICT (id) DO UPDATE SET {upd} WHERE lower(pichangol_productos.vendedor_email) = %s",
                [fila[c] for c in cols] + [fila["vendedor_email"].lower()])
            n = cur.rowcount
            conn.commit()
            return n == 1
    except Exception as e:  # noqa: BLE001
        print(f"[tienda-web] no se pudo guardar {fila.get('id')}: {e}", flush=True)
        return False


def eliminar_producto(producto_id: str, email: str) -> bool:
    email = (email or "").strip().lower()
    if not pg.habilitado or not producto_id or not email:
        return False
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM pichangol_productos WHERE id = %s AND lower(vendedor_email) = %s", (producto_id, email))
            n = cur.rowcount
            conn.commit()
            return n == 1
    except Exception:  # noqa: BLE001
        return False


def esta_verificado(email: str) -> bool:
    """¿Jugador con identidad verificada? (`pichangol_verificaciones`, espejo de
    `appState.jugadorVerificado`)."""
    email = (email or "").strip().lower()
    if not pg.habilitado or not email:
        return False
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pichangol_verificaciones WHERE lower(email) = %s AND estado = 'verificado' LIMIT 1", (email,))
            return cur.fetchone() is not None
    except Exception:  # noqa: BLE001
        return False


def producto_por_id(producto_id: str) -> dict | None:
    """Fila del producto sin filtrar por vendedor (para saber si un id ya es
    de otro antes de subirle una foto)."""
    if not pg.habilitado or not producto_id:
        return None
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT {', '.join(_COLS_PROD)} FROM pichangol_productos WHERE id = %s", (producto_id,))
            f = cur.fetchone()
            return _norm_producto(pg._fila_a_dict(_COLS_PROD, f)) if f else None
    except Exception:  # noqa: BLE001
        return None


def academia_existe(academia_id: str) -> bool:
    """¿Hay una fila con ese id (de quien sea)? Para no subir imágenes a la
    carpeta de una academia ajena."""
    if not pg.habilitado or not academia_id:
        return False
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pichangol_academias WHERE id = %s LIMIT 1", (academia_id,))
            return cur.fetchone() is not None
    except Exception:  # noqa: BLE001
        return False


# ── Campeonatos (`pichangol_campeonatos`: una fila = un campeonato, `data` = `Campeonato.toJson`) ──
def campeonatos_de_dueno(email: str) -> list[dict]:
    """`misCampeonatosOrganizados`: los que organiza este correo, el más nuevo primero (id descendente, como el app)."""
    email = (email or "").strip().lower()
    if not pg.habilitado or not email:
        return []
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id, academia_id, data FROM pichangol_campeonatos WHERE lower(dueno) = %s "
                        "AND coalesce(eliminado,false) = false ORDER BY id DESC", (email,))
            out = []
            for cid, aid, data in cur.fetchall():
                d = _json_dict(data)
                d["id"] = cid
                d.setdefault("academiaId", aid or "")
                out.append(d)
            return out
    except Exception:  # noqa: BLE001
        return []


def campeonato_por_codigo(codigo: str) -> tuple[dict | None, bool]:
    """`buscarCampeonato` + `porCodigoEquipo` del app: el código corto del
    TORNEO (`data->>'codigo'`) o el de un EQUIPO de fútbol (dentro de
    `participantes`). Devuelve (campeonato, es_codigo_de_equipo)."""
    cod = (codigo or "").strip().upper()
    if not pg.habilitado or not cod or len(cod) > 12:
        return None, False
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id, academia_id, dueno, data FROM pichangol_campeonatos WHERE upper(data->>'codigo') = %s "
                        "AND coalesce(eliminado,false) = false LIMIT 1", (cod,))
            f = cur.fetchone()
            equipo = False
            if not f:
                cur.execute("SELECT id, academia_id, dueno, data FROM pichangol_campeonatos WHERE data->'participantes' @> %s::jsonb "
                            "AND coalesce(eliminado,false) = false LIMIT 1", (json.dumps([{"codigo": cod}]),))
                f = cur.fetchone()
                equipo = f is not None
            if not f:
                return None, False
            d = _json_dict(f[3])
            d["id"] = f[0]
            d.setdefault("academiaId", f[1] or "")
            d.setdefault("dueno", f[2] or "")
            return d, equipo
    except Exception:  # noqa: BLE001
        return None, False


def campeonatos_donde_participa(email: str) -> list[dict]:
    """`campeonatosDondeParticipo` del app: torneos que NO organiza y donde
    está inscrito, es capitán o juega en un plantel. Prefiltro por texto en la
    base y regla exacta en Python (espejo del app)."""
    email = (email or "").strip().lower()
    if not pg.habilitado or not email:
        return []
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id, academia_id, dueno, data FROM pichangol_campeonatos WHERE lower(data::text) LIKE %s "
                        "AND lower(coalesce(dueno,'')) <> %s AND coalesce(eliminado,false) = false ORDER BY id DESC LIMIT 200",
                        ("%" + email + "%", email))
            out = []
            for cid, aid, dueno, data in cur.fetchall():
                d = _json_dict(data)
                d["id"] = cid
                d.setdefault("academiaId", aid or "")
                d.setdefault("dueno", dueno or "")
                if participa_en(d, email):
                    out.append(d)
            return out
    except Exception:  # noqa: BLE001
        return []


def participa_en(c: dict, email: str) -> bool:
    email = (email or "").strip().lower()
    for p in c.get("participantes") or []:
        if str(p.get("email") or "").lower() == email or str(p.get("capitanEmail") or "").lower() == email:
            return True
        if any(str(i.get("email") or "").lower() == email for i in (p.get("roster") or [])):
            return True
    return False


def campeonato(campeonato_id: str) -> dict | None:
    if not pg.habilitado or not campeonato_id:
        return None
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id, academia_id, dueno, data FROM pichangol_campeonatos WHERE id = %s AND coalesce(eliminado,false) = false", (campeonato_id,))
            f = cur.fetchone()
            if not f:
                return None
            d = _json_dict(f[3])
            d["id"] = f[0]
            d.setdefault("academiaId", f[1] or "")
            d.setdefault("dueno", f[2] or "")
            return d
    except Exception:  # noqa: BLE001
        return None


def mutar_campeonato(campeonato_id: str, fn):
    """Lee el campeonato con `SELECT … FOR UPDATE` (la fila queda bloqueada
    hasta el commit: dos jugadores que se unen al mismo equipo a la vez se
    atienden de uno en uno) y llama `fn(data)`, que devuelve `(guardar,
    resultado)`. Con `guardar` se escribe `data` en la MISMA transacción.
    Devuelve `(encontrado, resultado)`. Una excepción dentro de `fn` o al
    guardar deshace la transacción y se propaga (el llamador revierte lo que
    `fn` hizo fuera de la base, p. ej. un débito de saldo)."""
    if not pg.habilitado or not campeonato_id:
        return False, None
    with pg.conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT id, academia_id, dueno, data FROM pichangol_campeonatos WHERE id = %s "
                    "AND coalesce(eliminado,false) = false FOR UPDATE", (campeonato_id,))
        f = cur.fetchone()
        if not f:
            return False, None
        d = _json_dict(f[3])
        d["id"] = f[0]
        d.setdefault("academiaId", f[1] or "")
        d.setdefault("dueno", f[2] or "")
        guardar, resultado = fn(d)
        if guardar:
            cur.execute("UPDATE pichangol_campeonatos SET data = %s::jsonb, updated_at = now() WHERE id = %s",
                        (json.dumps(d), campeonato_id))
    return True, resultado


def campeonato_existe(campeonato_id: str) -> bool:
    if not pg.habilitado or not campeonato_id:
        return False
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pichangol_campeonatos WHERE id = %s", (campeonato_id,))
            return cur.fetchone() is not None
    except Exception:  # noqa: BLE001
        return False


def guardar_campeonato(campeonato_id: str, dueno: str, data: dict) -> bool:
    """UPSERT como `CampeonatosRepo.guardar` (id, academia_id, dueno, data,
    eliminado=false) + `updated_at=now()` (el app no lo refresca y
    `buscarPorNombre` ordena por él). Un id a nombre de OTRO correo no se toca."""
    dueno = (dueno or "").strip().lower()
    if not pg.habilitado or not campeonato_id or not dueno:
        return False
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO pichangol_campeonatos (id, academia_id, dueno, data, eliminado, updated_at) VALUES (%s, %s, %s, %s::jsonb, false, now()) "
                "ON CONFLICT (id) DO UPDATE SET data = EXCLUDED.data, academia_id = EXCLUDED.academia_id, eliminado = false, updated_at = now() "
                "WHERE lower(pichangol_campeonatos.dueno) = %s", (campeonato_id, str(data.get("academiaId") or ""), dueno, json.dumps(data), dueno))
            n = cur.rowcount
            conn.commit()
            return n == 1
    except Exception as e:  # noqa: BLE001
        print(f"[campeonato-web] no se pudo guardar {campeonato_id}: {e}", flush=True)
        return False


def eliminar_campeonato(campeonato_id: str, dueno: str) -> bool:
    """Borrado lógico (`eliminado=true`), como el app."""
    dueno = (dueno or "").strip().lower()
    if not pg.habilitado or not campeonato_id or not dueno:
        return False
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE pichangol_campeonatos SET eliminado = true, updated_at = now() WHERE id = %s AND lower(dueno) = %s", (campeonato_id, dueno))
            n = cur.rowcount
            conn.commit()
            return n == 1
    except Exception:  # noqa: BLE001
        return False


def canchas_para_sede() -> list[dict]:
    """`todasLasCanchas()` del selector de sede del app: nombre, dirección y
    punto de TODAS las canchas registradas (no eliminadas), únicas por nombre."""
    if not pg.habilitado:
        return []
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT nombre, club, direccion, lat, lng FROM pichangol_canchas WHERE coalesce(eliminada,false) = false ORDER BY nombre")
            out, vistos = [], set()
            for nombre, club, direccion, lat, lng in cur.fetchall():
                n = str(nombre or club or "").strip()
                if not n or n.lower() in vistos:
                    continue
                vistos.add(n.lower())
                out.append({"nombre": n, "club": str(club or ""), "direccion": str(direccion or ""),
                            "lat": float(lat) if lat is not None else None, "lng": float(lng) if lng is not None else None})
            return out
    except Exception:  # noqa: BLE001
        return []


# ── BOLEADORES (sparring por turno, sep-2026; docs/diseno-boleadores.md) ───────
# `pichangol_boleadores` (email PK, deporte, categoria, tarifa, moneda, activo,
# data jsonb) y `pichangol_boleador_solicitudes` (una por reserva con boleador).
# SQL `docs/piloto/supabase_boleadores.sql`. Solo el backend las toca.

_COLS_BOL = ["email", "deporte", "categoria", "tarifa", "moneda", "activo", "data", "creado", "actualizado"]


def _norm_boleador(f) -> dict:
    d = pg._fila_a_dict(_COLS_BOL, f)
    data = _json_dict(d.get("data"))
    out = dict(data)
    out.update({
        "email": str(d.get("email") or "").lower(),
        "deporte": str(d.get("deporte") or "tenis"),
        "categoria": str(d.get("categoria") or ""),
        "tarifa": float(d.get("tarifa") or 0),
        "moneda": str(d.get("moneda") or "PEN"),
        "activo": bool(d.get("activo")),
        "creado": d["creado"].isoformat() if d.get("creado") else "",
        "actualizado": d["actualizado"].isoformat() if d.get("actualizado") else "",
    })
    out["canchas"] = [str(x) for x in (data.get("canchas") or []) if x]
    out["locales"] = [x for x in (data.get("locales") or []) if isinstance(x, dict)]
    out["etiquetas"] = [str(x) for x in (data.get("etiquetas") or [])]
    out["disponibilidad"] = data.get("disponibilidad") if isinstance(data.get("disponibilidad"), dict) else {}
    out["stats"] = data.get("stats") if isinstance(data.get("stats"), dict) else {}
    return out


def boleador(email: str) -> dict | None:
    email = (email or "").strip().lower()
    if not pg.habilitado or not email:
        return None
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT {', '.join(_COLS_BOL)} FROM pichangol_boleadores WHERE email = %s", (email,))
            f = cur.fetchone()
            return _norm_boleador(f) if f else None
    except Exception:  # noqa: BLE001
        return None


def boleador_por_slug(slug: str) -> dict | None:
    """El público no ve correos: la ficha/checkout identifican al boleador por
    `data.slug` (hash corto del correo)."""
    slug = (slug or "").strip()
    if not pg.habilitado or not slug:
        return None
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT {', '.join(_COLS_BOL)} FROM pichangol_boleadores WHERE data->>'slug' = %s", (slug,))
            f = cur.fetchone()
            return _norm_boleador(f) if f else None
    except Exception:  # noqa: BLE001
        return None


def guardar_boleador(email: str, *, deporte: str, categoria: str, tarifa: float, moneda: str,
                     activo: bool, data: dict) -> bool:
    """UPSERT del perfil de boleador (crea o actualiza el suyo)."""
    email = (email or "").strip().lower()
    if not pg.habilitado or not email:
        return False
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO pichangol_boleadores (email, deporte, categoria, tarifa, moneda, activo, data, creado, actualizado) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, now(), now()) "
                "ON CONFLICT (email) DO UPDATE SET deporte = EXCLUDED.deporte, categoria = EXCLUDED.categoria, "
                "tarifa = EXCLUDED.tarifa, moneda = EXCLUDED.moneda, activo = EXCLUDED.activo, data = EXCLUDED.data, actualizado = now()",
                (email, deporte, categoria, float(tarifa), moneda, bool(activo), json.dumps(data)))
            conn.commit()
            return True
    except Exception:  # noqa: BLE001
        return False


def actualizar_boleador(email: str, *, activo: bool | None = None, data_merge: dict | None = None) -> bool:
    """Cambios puntuales (pausar, stats/faltas) sin pisar el resto del perfil."""
    email = (email or "").strip().lower()
    if not pg.habilitado or not email:
        return False
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            if data_merge:
                cur.execute("UPDATE pichangol_boleadores SET data = data || %s::jsonb, actualizado = now() WHERE email = %s",
                            (json.dumps(data_merge), email))
            if activo is not None:
                cur.execute("UPDATE pichangol_boleadores SET activo = %s, actualizado = now() WHERE email = %s", (bool(activo), email))
            conn.commit()
            return True
    except Exception:  # noqa: BLE001
        return False


def boleadores_de_cancha(cancha_id: str, deporte: str = "") -> list[dict]:
    """Boleadores ACTIVOS que atienden en esa cancha (su `data.canchas` la
    incluye) y, si se pide, de ese deporte."""
    if not pg.habilitado or not cancha_id:
        return []
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            sql = (f"SELECT {', '.join(_COLS_BOL)} FROM pichangol_boleadores "
                   "WHERE activo = true AND data->'canchas' ? %s")
            args: list = [cancha_id]
            if deporte:
                sql += " AND deporte = %s"
                args.append(deporte)
            cur.execute(sql + " ORDER BY tarifa, email", args)
            return [_norm_boleador(f) for f in cur.fetchall()]
    except Exception:  # noqa: BLE001
        return []


def permite_boleadores(cancha_id: str) -> bool:
    """`pichangol_canchas.permite_boleadores` (default true; sin la columna, true)."""
    if not pg.habilitado or not cancha_id:
        return True
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT coalesce(permite_boleadores, true) FROM pichangol_canchas WHERE id = %s", (cancha_id,))
            f = cur.fetchone()
            return bool(f[0]) if f else True
    except Exception:  # noqa: BLE001
        return True


_COLS_SOL = ["id", "boleador_email", "cliente_email", "cliente_nombre", "reserva_ref", "cancha_id", "club",
             "fecha", "hora_inicio", "hora_fin", "turnos", "monto_centimos", "comision_centimos", "moneda",
             "estado", "canal", "charge_id", "vence_en", "respondido_en", "creado", "data"]


def _norm_sol(f) -> dict:
    d = pg._fila_a_dict(_COLS_SOL, f)
    d["data"] = _json_dict(d.get("data"))
    for k in ("turnos", "monto_centimos", "comision_centimos"):
        d[k] = int(d.get(k) or 0)
    for k in ("vence_en", "respondido_en", "creado"):
        v = d.get(k)
        d[k] = v.isoformat() if hasattr(v, "isoformat") else (str(v) if v else "")
    for k in ("boleador_email", "cliente_email", "cliente_nombre", "reserva_ref", "cancha_id", "club",
              "fecha", "hora_inicio", "hora_fin", "moneda", "estado", "canal", "charge_id"):
        d[k] = str(d.get(k) or "")
    return d


def insertar_solicitud(s: dict) -> bool:
    if not pg.habilitado or not s.get("id"):
        return False
    cols = [c for c in _COLS_SOL if c != "creado"]
    vals = []
    for c in cols:
        v = s.get(c)
        if c == "data":
            v = json.dumps(v or {})
        vals.append(v)
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute(f"INSERT INTO pichangol_boleador_solicitudes ({', '.join(cols)}) VALUES "
                        f"({', '.join(['%s::jsonb' if c == 'data' else '%s' for c in cols])})", vals)
            conn.commit()
            return True
    except Exception:  # noqa: BLE001
        return False


def solicitud(sol_id: str) -> dict | None:
    if not pg.habilitado or not sol_id:
        return None
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT {', '.join(_COLS_SOL)} FROM pichangol_boleador_solicitudes WHERE id = %s", (sol_id,))
            f = cur.fetchone()
            return _norm_sol(f) if f else None
    except Exception:  # noqa: BLE001
        return None


def solicitud_por_reserva(ref: str) -> dict | None:
    """La solicitud viva (no rechazada/vencida/cancelada) de una reserva; si no
    hay viva, la última."""
    if not pg.habilitado or not ref:
        return None
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT {', '.join(_COLS_SOL)} FROM pichangol_boleador_solicitudes WHERE reserva_ref = %s "
                        "ORDER BY (estado IN ('pendiente','aceptada')) DESC, creado DESC LIMIT 1", (ref,))
            f = cur.fetchone()
            return _norm_sol(f) if f else None
    except Exception:  # noqa: BLE001
        return None


def solicitudes_de_boleador(email: str, estados: tuple[str, ...] = (), limite: int = 100) -> list[dict]:
    email = (email or "").strip().lower()
    if not pg.habilitado or not email:
        return []
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            sql = f"SELECT {', '.join(_COLS_SOL)} FROM pichangol_boleador_solicitudes WHERE boleador_email = %s"
            args: list = [email]
            if estados:
                sql += " AND estado = ANY(%s)"
                args.append(list(estados))
            cur.execute(sql + " ORDER BY fecha DESC, hora_inicio DESC LIMIT %s", args + [int(limite)])
            return [_norm_sol(f) for f in cur.fetchall()]
    except Exception:  # noqa: BLE001
        return []


def solicitudes_de_cliente(email: str, limite: int = 100) -> list[dict]:
    email = (email or "").strip().lower()
    if not pg.habilitado or not email:
        return []
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT {', '.join(_COLS_SOL)} FROM pichangol_boleador_solicitudes WHERE cliente_email = %s "
                        "ORDER BY creado DESC LIMIT %s", (email, int(limite)))
            return [_norm_sol(f) for f in cur.fetchall()]
    except Exception:  # noqa: BLE001
        return []


def solicitudes_cruce(boleador_email: str, fecha: str, hora_inicio: str, hora_fin: str) -> list[dict]:
    """Solicitudes VIVAS (pendiente/aceptada) del boleador que se cruzan con
    [hora_inicio, hora_fin) ese día: si hay alguna, no está disponible."""
    email = (boleador_email or "").strip().lower()
    if not pg.habilitado or not email or not fecha:
        return []
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT {', '.join(_COLS_SOL)} FROM pichangol_boleador_solicitudes "
                        "WHERE boleador_email = %s AND fecha = %s AND estado IN ('pendiente','aceptada') "
                        "AND hora_inicio < %s AND hora_fin > %s", (email, fecha, hora_fin, hora_inicio))
            return [_norm_sol(f) for f in cur.fetchall()]
    except Exception:  # noqa: BLE001
        return []


def solicitudes_vencidas() -> list[dict]:
    """Pendientes cuyo plazo para aceptar ya pasó (las procesa el cron)."""
    if not pg.habilitado:
        return []
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT {', '.join(_COLS_SOL)} FROM pichangol_boleador_solicitudes "
                        "WHERE estado = 'pendiente' AND vence_en IS NOT NULL AND vence_en < now() ORDER BY vence_en LIMIT 200")
            return [_norm_sol(f) for f in cur.fetchall()]
    except Exception:  # noqa: BLE001
        return []


def actualizar_solicitud(sol_id: str, *, estado: str | None = None, data_merge: dict | None = None,
                         respondida: bool = False, solo_si_estado: tuple[str, ...] = ()) -> bool:
    """Cambia estado/data de una solicitud. Con `solo_si_estado` es atómico:
    solo escribe si el estado actual está en la tupla (evita aceptar dos veces
    o aceptar algo ya vencido). Devuelve True si tocó la fila."""
    if not pg.habilitado or not sol_id:
        return False
    sets, args = [], []
    if estado is not None:
        sets.append("estado = %s"); args.append(estado)
    if data_merge:
        sets.append("data = data || %s::jsonb"); args.append(json.dumps(data_merge))
    if respondida:
        sets.append("respondido_en = now()")
    if not sets:
        return False
    sql = f"UPDATE pichangol_boleador_solicitudes SET {', '.join(sets)} WHERE id = %s"
    args.append(sol_id)
    if solo_si_estado:
        sql += " AND estado = ANY(%s)"
        args.append(list(solo_si_estado))
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute(sql, args)
            n = cur.rowcount
            conn.commit()
            return n == 1
    except Exception:  # noqa: BLE001
        return False


def marcar_extra_boleador(reserva_ids: list[str], estado: str) -> bool:
    """Actualiza el `estado` de la línea `boleador` dentro de `extras` de la
    reserva (la primera fila del bloque la lleva) para que el app/web muestren
    Esperando confirmación / Confirmado / No disponible."""
    if not pg.habilitado or not reserva_ids:
        return False
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id, extras FROM pichangol_reservas WHERE id = ANY(%s)", (list(reserva_ids),))
            for rid, extras in cur.fetchall():
                lst = _json_list(extras)
                cambio = False
                for x in lst:
                    if isinstance(x, dict) and x.get("clave") == "boleador":
                        x["estado"] = estado
                        cambio = True
                if cambio:
                    cur.execute("UPDATE pichangol_reservas SET extras = %s WHERE id = %s", (json.dumps(lst), rid))
            conn.commit()
            return True
    except Exception:  # noqa: BLE001
        return False


# ── FIDELIDAD DEL LOCAL (sep-2026) ───────────────────────────────────────────

def reservas_pagadas_en(email: str, cancha_ids: list[str], limite: int = 400) -> list[dict]:
    """Reservas PAGADAS del correo en esas canchas (las que suman en la tarjeta
    de fidelidad del local): sin canceladas/no-show ni retenciones."""
    email = (email or "").strip().lower()
    if not pg.habilitado or not email or not cancha_ids:
        return []
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT id, cancha_id, fecha, hora_inicio, precio, medio_pago, grupo_reserva_id, estado "
                "FROM pichangol_reservas WHERE lower(usuario) = %s AND cancha_id = ANY(%s) "
                "AND coalesce(pagado,false) AND coalesce(estado,'') NOT IN ('cancelada','no_show','nueva') "
                "ORDER BY fecha, hora_inicio LIMIT %s", (email, list(cancha_ids), limite))
            cols = ["id", "cancha_id", "fecha", "hora_inicio", "precio", "medio_pago", "grupo_reserva_id", "estado"]
            out = []
            for f in cur.fetchall():
                d = pg._fila_a_dict(cols, f)
                d["fecha"] = str(d.get("fecha") or "")
                d["precio"] = float(d.get("precio") or 0)
                out.append(d)
            return out
    except Exception:  # noqa: BLE001
        return []


_COLS_CANJE = ["id", "email", "local_key", "cancha_id", "reserva_ref", "reserva_ids", "tipo", "descuento",
               "moneda", "estado", "reservas_contadas", "canal", "creado", "actualizado"]


def _norm_canje(d: dict) -> dict:
    d = dict(d)
    d["reserva_ids"] = _json_list(d.get("reserva_ids"))
    d["reservas_contadas"] = _json_list(d.get("reservas_contadas"))
    d["descuento"] = float(d.get("descuento") or 0)
    for k in ("creado", "actualizado"):
        v = d.get(k)
        if hasattr(v, "isoformat"):
            d[k] = v.isoformat()
    return d


def insertar_canje(c: dict) -> bool:
    if not pg.habilitado:
        return False
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO pichangol_fidelidad_canjes (id, email, local_key, cancha_id, reserva_ref, reserva_ids, "
                "tipo, descuento, moneda, estado, reservas_contadas, canal) VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s::jsonb,%s)",
                (c["id"], c["email"], c["local_key"], c["cancha_id"], c["reserva_ref"], json.dumps(c.get("reserva_ids") or []),
                 c["tipo"], float(c.get("descuento") or 0), c.get("moneda") or "PEN", c.get("estado") or "reservado",
                 json.dumps(c.get("reservas_contadas") or []), c.get("canal") or "app"))
            conn.commit()
            return True
    except Exception as e:  # noqa: BLE001
        print(f"[fidelidad] no se pudo guardar el canje {c.get('id')}: {e}", flush=True)
        return False


def canjes_de(email: str, local_key: str) -> list[dict]:
    email = (email or "").strip().lower()
    if not pg.habilitado or not email or not local_key:
        return []
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT {', '.join(_COLS_CANJE)} FROM pichangol_fidelidad_canjes "
                        "WHERE email = %s AND local_key = %s ORDER BY creado", (email, local_key))
            return [_norm_canje(pg._fila_a_dict(_COLS_CANJE, f)) for f in cur.fetchall()]
    except Exception:  # noqa: BLE001
        return []


def canje_por_ref(reserva_ref: str) -> dict | None:
    """El canje (no devuelto) ligado a esa reserva/grupo, si lo hay."""
    if not pg.habilitado or not reserva_ref:
        return None
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT {', '.join(_COLS_CANJE)} FROM pichangol_fidelidad_canjes "
                        "WHERE reserva_ref = %s AND estado <> 'devuelto' ORDER BY creado DESC LIMIT 1", (reserva_ref,))
            f = cur.fetchone()
            return _norm_canje(pg._fila_a_dict(_COLS_CANJE, f)) if f else None
    except Exception:  # noqa: BLE001
        return None


def canje_por_ids(ids: list[str]) -> dict | None:
    """Canje cuyo `reserva_ids` contiene alguna de esas reservas (hold web)."""
    if not pg.habilitado or not ids:
        return None
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT {', '.join(_COLS_CANJE)} FROM pichangol_fidelidad_canjes "
                        "WHERE estado <> 'devuelto' AND reserva_ids ?| %s ORDER BY creado DESC LIMIT 1", (list(ids),))
            f = cur.fetchone()
            return _norm_canje(pg._fila_a_dict(_COLS_CANJE, f)) if f else None
    except Exception:  # noqa: BLE001
        return None


def actualizar_canje(canje_id: str, estado: str, solo_si: tuple = ()) -> bool:
    if not pg.habilitado or not canje_id:
        return False
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            if solo_si:
                cur.execute("UPDATE pichangol_fidelidad_canjes SET estado = %s, actualizado = now() "
                            "WHERE id = %s AND estado = ANY(%s)", (estado, canje_id, list(solo_si)))
            else:
                cur.execute("UPDATE pichangol_fidelidad_canjes SET estado = %s, actualizado = now() WHERE id = %s",
                            (estado, canje_id))
            n = cur.rowcount
            conn.commit()
            return n == 1
    except Exception:  # noqa: BLE001
        return False


# ── Celular del PERFIL (`pichangol_perfiles`, la misma tabla del APK) ─────────
# La ficha web lo PRELLENA (como el app, que usa `appState.miCelular`) y, si la
# cuenta aún no tenía celular, el que escribe al reservar queda en su perfil.

def celular_de_perfil(email: str) -> str:
    e = (email or "").strip().lower()
    if not pg.habilitado or not e:
        return ""
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT celular FROM pichangol_perfiles WHERE email = %s", (e,))
            f = cur.fetchone()
            return str((f[0] if f else "") or "").strip()
    except Exception:  # noqa: BLE001
        return ""


def guardar_celular_si_falta(email: str, nombre: str, celular: str) -> bool:
    """Deja el celular en el perfil SOLO si no tenía (nunca pisa uno puesto
    por el usuario en el app). Fail-safe."""
    e, cel = (email or "").strip().lower(), (celular or "").strip()[:20]
    if not pg.habilitado or not e or not cel:
        return False
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO pichangol_perfiles (email, nombre, celular) VALUES (%s, %s, %s) "
                        "ON CONFLICT (email) DO UPDATE SET celular = EXCLUDED.celular "
                        "WHERE coalesce(pichangol_perfiles.celular, '') = ''",
                        (e, (nombre or "").strip()[:80] or e.split("@")[0], cel))
            conn.commit()
            return True
    except Exception:  # noqa: BLE001
        return False



# --- Perfil del jugador (web = pantalla Perfil del app) ----------------------

def niveles_de(email: str) -> list[dict]:
    """Niveles del jugador por deporte (`pichangol_niveles`, = `NivelesRepo.
    deJugador`). Fail-safe: sin base o sin tabla, lista vacía."""
    e = (email or "").strip().lower()
    if not pg.habilitado or not e:
        return []
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT deporte, nivel, partidos, victorias FROM pichangol_niveles "
                        "WHERE lower(email) = %s ORDER BY deporte", (e,))
            return [{"deporte": str(f[0] or ""), "nivel": float(f[1] or 3.0),
                     "partidos": int(f[2] or 0), "victorias": int(f[3] or 0)} for f in cur.fetchall()]
    except Exception:  # noqa: BLE001
        return []


def puntos_de(email: str) -> dict:
    """Puntos Pichangol DISPONIBLES, misma cuenta que `AppState.
    misPuntosDisponibles`: 1 punto por S/ 1 de precio + extras de las reservas
    TRAÍDAS POR LA APP y PAGADAS de los últimos 12 meses (sin no-show) + los
    pedidos de bodega pagados con saldo y entregados, menos lo canjeado
    (`pichangol_puntos_canjes`). Cada parte es fail-safe por separado."""
    e = (email or "").strip().lower()
    from datetime import datetime, timedelta, timezone
    out = {"ganados": 0, "canjeados": 0, "disponibles": 0}
    if not pg.habilitado or not e:
        return out
    desde = (datetime.now(timezone.utc) - timedelta(days=365))
    ganados = 0
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT precio, extras, fecha FROM pichangol_reservas WHERE lower(usuario) = %s "
                "AND coalesce(traida_por_app, true) AND coalesce(pagado, false) "
                "AND coalesce(estado, '') NOT IN ('noShow', 'no_show')", (e,))
            lim = desde.date().isoformat()
            for precio, extras, fecha in cur.fetchall():
                if str(fecha or "") < lim:
                    continue
                tot = float(precio or 0) + sum(float((x or {}).get("precio") or 0) for x in _json_list(extras) if isinstance(x, dict))
                ganados += int(round(tot))
    except Exception:  # noqa: BLE001
        pass
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT coalesce(sum(total), 0) FROM pichangol_bodega_pedidos WHERE lower(cliente) = %s "
                        "AND pagado AND estado = 'entregado' AND creado >= %s", (e, desde))
            ganados += int(round(float((cur.fetchone() or [0])[0] or 0)))
    except Exception:  # noqa: BLE001
        pass
    canjeados = 0
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT coalesce(sum(puntos), 0) FROM pichangol_puntos_canjes WHERE lower(email) = %s", (e,))
            canjeados = int((cur.fetchone() or [0])[0] or 0)
    except Exception:  # noqa: BLE001
        pass
    out.update(ganados=ganados, canjeados=canjeados, disponibles=max(0, ganados - canjeados))
    return out


def tiene_matriculas(email: str) -> bool:
    """¿Paga (o es) alumno de alguna academia? (= `appState.misMatriculas`)."""
    e = (email or "").strip().lower()
    if not pg.habilitado or not e:
        return False
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pichangol_matriculas WHERE (lower(email) = %s "
                        "OR lower(data->>'emailAlumno') = %s) AND coalesce(eliminada,false) = false LIMIT 1", (e, e))
            return cur.fetchone() is not None
    except Exception:  # noqa: BLE001
        return False
