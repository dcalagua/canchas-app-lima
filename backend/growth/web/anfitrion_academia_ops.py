"""OPERACIÓN DE LA ACADEMIA en la web (Modo anfitrión → Mi academia), lado
DUEÑO/PROFE: lo que el app hace en `mi_academia_screen` y sus pantallas hijas y
que la web aún no tenía (Mi academia web ya edita la academia y lista alumnos
en `web/anfitrion_academia.py`; esto NO lo duplica).

- COBROS de cuotas: NO aquí. Viven en `/anfitrion/cobros?academia=<id>`
  (`web/anfitrion_negocio.py`, = `cobros_screen.dart`); la pestaña enlaza ahí.
- `/anfitrion/academia/asistencia`   = `asistencia_screen.dart` (día, presente/
  falta, "Todos presentes", "Avisar a los padres": chat del app a los que tienen
  cuenta + WhatsApp a los que no).
- `/anfitrion/academia/evaluaciones` = `evaluar_alumno_screen.dart` sobre los
  PLANES DE TRABAJO propios de la academia (`pichangol_academia_planes`, los
  arma el profe en el app) o, sin ellos, la PLANTILLA Pichangol del deporte
  (`planes_semilla.dart` → `planes_semilla.json`): rúbrica Inicial · En proceso
  · Logrado por habilidad + bitácora de clase.
- `/anfitrion/academia/ranking`      = `ranking_academia_screen.dart`: tabla de
  posiciones (3 pts victoria, 1 derrota), filtros sede/categoría, registrar /
  quitar partido y categoría por alumno. Escribe `data.partidos` / `data.
  categorias` de `pichangol_academias` con el formato de `PartidoRanking.toJson`
  (el ranking GLOBAL web de `jugador_liga.py` los consume igual).
- `/anfitrion/academia/reportes`     = `reporte_academia_screen.dart`: cobrado /
  por cobrar / vencido por período y sede, ingresos 6 meses, morosidad, alumnos
  por programa, comisión por cobro digital (`/pagos/matricula/resumen`),
  liquidación al club y movimientos con boleta correlativa.
- `/anfitrion/academia/chats`        = `chats_academia_screen.dart`: la bandeja
  de la academia (un hilo `<academiaId>|<correo>` por cuenta de alumno, tabla
  `pichangol_mensajes`); cada conversación se abre en la mensajería web
  (`/mensajes/{clave}`, `web/jugador_mensajes.py`). Aquí solo se escribe el
  PRIMER mensaje a un alumno que aún no tiene hilo.
- `/anfitrion/academia/sedes`        = la sección "Sedes y horarios" de
  `crear_academia_screen.dart`: sedes, horario por (sede, programa) y precio
  por (sede, plan), que la web antes solo CONSERVABA.

ASISTENCIA, EVALUACIONES, BITÁCORA y PLANES DE TRABAJO son las MISMAS filas en
el app y la web: tablas `pichangol_academia_asistencias|evaluaciones|notas|
planes` (`docs/piloto/supabase_academia_operacion.sql` +
`supabase_academia_operacion_rls.sql`, que da acceso al APK y crea la de
planes). El APK las sincroniza en `AppState.sincronizarOperacionAcademia`
(`lib/data/academia_ops_repo.dart`). Sin esas tablas, las páginas lo dicen y no
rompen.

Todo escribe SOLO sobre academias cuyo `dueno` es el correo de la sesión
(`FOR UPDATE` al tocar cuotas y al mezclar `data`)."""

from __future__ import annotations

import json
import re
import time
import urllib.parse as up
from datetime import date, datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Body, Request
from fastapi.responses import HTMLResponse, JSONResponse

import paises
from db import pg
from web import datos, sesion, ui
from web.router import PLAY_URL, e

router = APIRouter(tags=["web-anfitrion-academia-ops"])

MESES_CORTOS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "set", "oct", "nov", "dic"]
DIAS_CORTOS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
NIVELES = {"inicial": ("Inicial", 0, "bad"), "enProceso": ("En proceso", 1, "warn"), "logrado": ("Logrado", 2, "ok")}
DESEMPENOS = {"muyBien": ("Muy bien", "ok"), "bien": ("Bien", "warn"), "aReforzar": ("A reforzar", "bad")}
# Observaciones de la bitácora por SELECCIÓN (regla del app: nada de texto libre).
OBSERVACIONES = ["Buena actitud", "Mejoró su técnica", "Muy concentrado(a)", "Trabajó en equipo",
                 "Le costó el ejercicio", "Le faltó concentración", "Llegó tarde", "Practicar en casa",
                 "Listo(a) para subir de nivel"]
CATEGORIAS_RANKING = ["Iniciación", "Intermedio", "Avanzado", "Sub-8", "Sub-10", "Sub-12", "Sub-14",
                      "Sub-16", "5P", "5A", "5B", "4ta", "3ra", "2da", "1ra"]
PUNTOS_VICTORIA, PUNTOS_DERROTA = 3, 1       # `Academia.puntosVictoria / puntosDerrota`
_ZONA = {"PE": "America/Lima", "EC": "America/Guayaquil", "BO": "America/La_Paz"}
_PLANES = json.loads((Path(__file__).parent / "planes_semilla.json").read_text(encoding="utf-8"))
_RE_MARCADOR = re.compile(r"^[0-9 ()\-/,.]{0,40}$")


# ── utilidades ────────────────────────────────────────────────────────────────

def _json(v) -> dict:
    if isinstance(v, dict):
        return v
    try:
        d = json.loads(v or "{}")
        return d if isinstance(d, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _us() -> int:
    return time.time_ns() // 1000


def _pais(a: dict) -> str:
    return paises.pais_de_coordenadas(a.get("lat"), a.get("lng"))


def _sim(a: dict) -> str:
    """Moneda congelada de la academia; vacía = la del país de la sede."""
    m = str(a.get("moneda") or "").strip()
    if m in ("S/", "$", "Bs"):
        return m
    if m in ("PEN", "USD", "BOB"):
        return paises.simbolo_de_moneda(m)
    return paises.simbolo_de_moneda(paises.moneda_de_pais(_pais(a)))


def _ahora(a: dict) -> datetime:
    """Hora LOCAL de la sede, sin zona (como `DateTime.now().toIso8601String()`)."""
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo(_ZONA.get(_pais(a), "America/Lima"))).replace(tzinfo=None)
    except Exception:  # noqa: BLE001
        return datetime.utcnow() - timedelta(hours=5)


def _iso(d: datetime) -> str:
    return d.isoformat(timespec="milliseconds")


def _dt(v) -> datetime | None:
    try:
        return datetime.fromisoformat(str(v or "")[:19]) if v else None
    except ValueError:
        return None


def _f(d: datetime | date | None, anio: bool = True) -> str:
    if not d:
        return ""
    return f"{d.day} {MESES_CORTOS[d.month - 1]}" + (f" {d.year}" if anio else "")


def _sumar_meses(d: datetime, i: int) -> datetime:
    """`DateTime(y, m + i, d)` de Dart (desborda al mes siguiente si el día no existe)."""
    m = d.month - 1 + i
    y, m = d.year + m // 12, m % 12 + 1
    import calendar
    ult = calendar.monthrange(y, m)[1]
    if d.day <= ult:
        return d.replace(year=y, month=m)
    return d.replace(year=y, month=m, day=ult) + timedelta(days=d.day - ult)


def _num(v, defecto: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return defecto


def _es_menor(m: dict) -> bool:
    return bool(str(m.get("apoderadoNombre") or "").strip())


def _wa_contacto(m: dict) -> str:
    """`Alumno.whatsappContacto`: el del apoderado si es menor."""
    if _es_menor(m) and str(m.get("apoderadoWhatsapp") or "").strip():
        return str(m.get("apoderadoWhatsapp"))
    return str(m.get("whatsapp") or "")


def _tel_wa(tel: str, a: dict) -> str:
    """Número para wa.me: si es local, se le antepone el prefijo del país de la sede."""
    from web import catalogos
    d = "".join(ch for ch in str(tel or "") if ch.isdigit())
    if not d:
        return ""
    iso = _pais(a)
    pref = catalogos.TEL_PREFIJO.get(iso, "51")
    if len(d) <= catalogos.TEL_LONGITUD.get(iso, 9):
        return pref + d
    return d


def _cuotas(m: dict) -> list[dict]:
    return [c for c in (m.get("cuotas") or []) if isinstance(c, dict)]


def _vencida(c: dict, hoy: date) -> bool:
    v = _dt(c.get("vencimiento"))
    return (not c.get("pagada")) and bool(v) and v.date() < hoy


# ── datos (Postgres directo, fail-safe) ──────────────────────────────────────

def academias_de(email: str) -> list[dict]:
    return datos.academias_de_dueno(email)


def matriculas_de(aid: str) -> list[dict]:
    return datos.matriculas_de_academias([aid]) if aid else []


def mutar_matricula(alumno_id: str, dueno: str, fn):
    """Bloquea la matrícula (FOR UPDATE) SOLO si su academia es del `dueno`,
    aplica `fn(data) -> resultado` y guarda si el resultado no es None."""
    dueno = (dueno or "").strip().lower()
    if not pg.habilitado or not alumno_id or not dueno:
        return None
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT m.data, m.academia_id FROM pichangol_matriculas m JOIN pichangol_academias a ON a.id = m.academia_id "
                        "WHERE m.id = %s AND coalesce(m.eliminada,false) = false AND coalesce(a.eliminada,false) = false "
                        "AND lower(a.dueno) = %s FOR UPDATE OF m", (alumno_id, dueno))
            row = cur.fetchone()
            if not row:
                conn.rollback()
                return None
            data = _json(row[0])
            data.setdefault("id", alumno_id)
            data["academiaId"] = row[1]
            res = fn(data)
            if res is None:
                conn.rollback()
                return None
            cur.execute("UPDATE pichangol_matriculas SET data = %s::jsonb, updated_at = now() WHERE id = %s",
                        (json.dumps(data), alumno_id))
            conn.commit()
            return res
    except Exception as ex:  # noqa: BLE001
        print(f"[academia-ops] no se pudo actualizar la matrícula {alumno_id}: {ex}", flush=True)
        return None


def mutar_academia(aid: str, dueno: str, fn):
    """MERGE seguro sobre `pichangol_academias.data` (fila bloqueada, solo del dueño)."""
    dueno = (dueno or "").strip().lower()
    if not pg.habilitado or not aid or not dueno:
        return None
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT data FROM pichangol_academias WHERE id = %s AND lower(dueno) = %s "
                        "AND coalesce(eliminada,false) = false FOR UPDATE", (aid, dueno))
            row = cur.fetchone()
            if not row:
                conn.rollback()
                return None
            data = _json(row[0])
            res = fn(data)
            if res is None:
                conn.rollback()
                return None
            cur.execute("UPDATE pichangol_academias SET data = %s::jsonb, updated_at = now() WHERE id = %s",
                        (json.dumps(data), aid))
            conn.commit()
            return res
    except Exception as ex:  # noqa: BLE001
        print(f"[academia-ops] no se pudo actualizar la academia {aid}: {ex}", flush=True)
        return None


_TABLAS_OK: set[str] = set()


def tabla_existe(nombre: str) -> bool:
    """¿Ya se corrió el SQL de la tabla? Se cachea solo el SÍ (el NO se reintenta)."""
    if nombre in _TABLAS_OK:
        return True
    if not pg.habilitado:
        return False
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT to_regclass(%s)", (f"public.{nombre}",))
            ok = bool((cur.fetchone() or [None])[0])
    except Exception:  # noqa: BLE001
        return False
    if ok:
        _TABLAS_OK.add(nombre)
    return ok


def asistencias_de(aid: str, dia: str) -> dict[str, dict]:
    """{alumno_id: {presente, avisado}} de un día."""
    if not tabla_existe("pichangol_academia_asistencias"):
        return {}
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT alumno_id, presente, avisado FROM pichangol_academia_asistencias WHERE academia_id = %s AND dia = %s",
                        (aid, dia))
            return {r[0]: {"presente": bool(r[1]), "avisado": bool(r[2])} for r in cur.fetchall()}
    except Exception:  # noqa: BLE001
        return {}


def clases_asistidas(aid: str) -> dict[str, int]:
    """`AppState.clasesAsistidas` por alumno."""
    if not tabla_existe("pichangol_academia_asistencias"):
        return {}
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT alumno_id, count(*) FROM pichangol_academia_asistencias WHERE academia_id = %s AND presente "
                        "GROUP BY alumno_id", (aid,))
            return {r[0]: int(r[1]) for r in cur.fetchall()}
    except Exception:  # noqa: BLE001
        return {}


def guardar_asistencia(aid: str, alumno_ids: list[str], dia: str, presente: bool) -> bool:
    """`marcarAsistencia` / `marcarAsistenciaTodos` (upsert por alumno + día)."""
    if not alumno_ids or not tabla_existe("pichangol_academia_asistencias"):
        return False
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO pichangol_academia_asistencias (academia_id, alumno_id, dia, presente, actualizado) "
                "VALUES (%s, %s, %s, %s, now()) ON CONFLICT (alumno_id, dia) DO UPDATE SET presente = EXCLUDED.presente, "
                "academia_id = EXCLUDED.academia_id, actualizado = now()",
                [(aid, x, dia, presente) for x in alumno_ids])
            conn.commit()
            return True
    except Exception as ex:  # noqa: BLE001
        print(f"[academia-ops] asistencia no guardada: {ex}", flush=True)
        return False


def marcar_avisados(aid: str, alumno_ids: list[str], dia: str) -> None:
    """`marcarAsistenciaAvisada`: el aviso de ese día ya salió (no se reenvía).
    Si aún no había fila (no se marcó nada), cuenta como FALTA, igual que el app."""
    if not alumno_ids or not tabla_existe("pichangol_academia_asistencias"):
        return
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO pichangol_academia_asistencias (academia_id, alumno_id, dia, presente, avisado, actualizado) "
                "VALUES (%s, %s, %s, false, true, now()) ON CONFLICT (alumno_id, dia) DO UPDATE SET avisado = true, actualizado = now()",
                [(aid, x, dia) for x in alumno_ids])
            conn.commit()
    except Exception:  # noqa: BLE001
        pass


def evaluaciones_de(aid: str, plan_id: str) -> dict[tuple[str, str], str]:
    """{(alumno_id, habilidad): nivel}."""
    if not tabla_existe("pichangol_academia_evaluaciones"):
        return {}
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT alumno_id, habilidad, nivel FROM pichangol_academia_evaluaciones WHERE academia_id = %s AND plan_id = %s",
                        (aid, plan_id))
            return {(r[0], r[1]): r[2] for r in cur.fetchall()}
    except Exception:  # noqa: BLE001
        return {}


def guardar_evaluacion(aid: str, alumno_id: str, plan_id: str, habilidad: str, nivel: str) -> bool:
    """`AppState.evaluar` (upsert por alumno + plan + habilidad)."""
    if not tabla_existe("pichangol_academia_evaluaciones"):
        return False
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO pichangol_academia_evaluaciones (academia_id, alumno_id, plan_id, habilidad, nivel, ts) "
                        "VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (alumno_id, plan_id, habilidad) DO UPDATE SET "
                        "nivel = EXCLUDED.nivel, ts = EXCLUDED.ts, academia_id = EXCLUDED.academia_id",
                        (aid, alumno_id, plan_id, habilidad, nivel, int(time.time() * 1000)))
            conn.commit()
            return True
    except Exception as ex:  # noqa: BLE001
        print(f"[academia-ops] evaluación no guardada: {ex}", flush=True)
        return False


def notas_de(aid: str, alumno_id: str) -> list[dict]:
    """Bitácora del alumno (`NotaClase`), más recientes primero."""
    if not tabla_existe("pichangol_academia_notas"):
        return []
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id, plan_id, sesion_numero, fecha, desempeno, nota FROM pichangol_academia_notas "
                        "WHERE academia_id = %s AND alumno_id = %s ORDER BY creado DESC LIMIT 200", (aid, alumno_id))
            return [{"id": r[0], "planId": r[1], "sesionNumero": int(r[2] or 0), "fecha": str(r[3] or ""),
                     "desempeno": r[4], "nota": r[5] or ""} for r in cur.fetchall()]
    except Exception:  # noqa: BLE001
        return []


def guardar_nota(aid: str, nota: dict) -> bool:
    if not tabla_existe("pichangol_academia_notas"):
        return False
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO pichangol_academia_notas (id, academia_id, alumno_id, plan_id, sesion_numero, fecha, desempeno, nota) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                        (nota["id"], aid, nota["alumnoId"], nota["planId"], nota["sesionNumero"], nota["fecha"],
                         nota["desempeno"], nota["nota"]))
            conn.commit()
            return True
    except Exception as ex:  # noqa: BLE001
        print(f"[academia-ops] nota no guardada: {ex}", flush=True)
        return False


def borrar_nota(aid: str, nota_id: str) -> bool:
    if not tabla_existe("pichangol_academia_notas"):
        return False
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM pichangol_academia_notas WHERE id = %s AND academia_id = %s", (nota_id, aid))
            n = cur.rowcount
            conn.commit()
            return n == 1
    except Exception:  # noqa: BLE001
        return False


def _plan_normal(d: dict, aid: str = "") -> dict | None:
    """`PlanTrabajo.fromJson` → la forma que usa la página (igual a la semilla)."""
    if not isinstance(d, dict) or not str(d.get("id") or "").strip():
        return None
    ses = []
    for s in d.get("sesiones") or []:
        if not isinstance(s, dict):
            continue
        try:
            n = int(s.get("numero") or 0)
        except (TypeError, ValueError):
            continue
        if n > 0:
            ses.append({"numero": n, "titulo": str(s.get("titulo") or f"Clase {n}")})
    ses.sort(key=lambda s: s["numero"])
    return {"id": str(d["id"]), "academiaId": str(d.get("academiaId") or aid), "deporte": str(d.get("deporte") or ""),
            "nombre": str(d.get("nombre") or "Plan de trabajo"), "nivel": str(d.get("nivel") or ""),
            "habilidades": [str(h) for h in (d.get("habilidades") or []) if str(h).strip()],
            "sesiones": ses, "propio": True}


def planes_de(aid: str) -> list[dict]:
    """Planes de trabajo PROPIOS de la academia (`pichangol_academia_planes`,
    `data` = `PlanTrabajo.toJson` del app), más recientes primero. [] sin tabla."""
    if not aid or not pg.habilitado or not tabla_existe("pichangol_academia_planes"):
        return []
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT data FROM pichangol_academia_planes WHERE academia_id = %s AND NOT eliminado "
                        "ORDER BY actualizado DESC LIMIT 50", (aid,))
            out = []
            for (d,) in cur.fetchall():
                p = _plan_normal(_json(d), aid)
                if p:
                    out.append(p)
            return out
    except Exception:  # noqa: BLE001
        return []


def mensajes_de_academia(aid: str) -> list[dict]:
    """Mensajes de los hilos de la academia (`MensajesRepo.mensajesDeAcademias`)."""
    if not pg.habilitado or not aid:
        return []
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id, hilo, cuenta_email, autor_email, autor_nombre, es_profe, texto, media_url, creado "
                        "FROM pichangol_mensajes WHERE academia_id = %s ORDER BY creado ASC LIMIT 3000", (aid,))
            return [{"id": r[0], "hilo": r[1], "cuenta": (r[2] or "").lower(), "autor": (r[3] or "").lower(),
                     "autorNombre": r[4] or "", "esProfe": bool(r[5]), "texto": r[6] or "", "media": r[7] or "",
                     "creado": r[8]} for r in cur.fetchall()]
    except Exception:  # noqa: BLE001
        return []


def enviar_mensaje(aid: str, cuenta: str, autor: str, autor_nombre: str, texto: str, sufijo: str = "") -> bool:
    """`MensajesRepo.enviar` de un mensaje de academia escrito por el profe."""
    cuenta = (cuenta or "").strip().lower()
    if not pg.habilitado or not aid or not cuenta or not texto:
        return False
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO pichangol_mensajes (id, hilo, tipo, ref_id, academia_id, cuenta_email, autor_email, autor_nombre, es_profe, texto) "
                        "VALUES (%s, %s, 'academia', %s, %s, %s, %s, %s, true, %s)",
                        (f"msg_{_us()}{sufijo}", f"{aid}|{cuenta}", aid, aid, cuenta, autor.lower(), autor_nombre, texto))
            conn.commit()
            return True
    except Exception as ex:  # noqa: BLE001
        print(f"[academia-ops] mensaje no enviado: {ex}", flush=True)
        return False


# ── sesión / cabecera ─────────────────────────────────────────────────────────

_TABS = [("asistencia", "✅", "Asistencia"), ("evaluaciones", "📋", "Evaluación"),
         ("ranking", "🏆", "Ranking"), ("reportes", "📊", "Reportes"), ("chats", "💬", "Chats"), ("sedes", "📍", "Sedes")]


def _cab(ses: dict) -> str:
    """Cabecera del modo anfitrión con las MISMAS pestañas de Mi academia web."""
    tabs = ("<a class='cat' href='/anfitrion/academia'><span class='ico'>📣</span>Mis academias</a>"
            "<a class='cat' href='/anfitrion/academia/alumnos'><span class='ico'>🎓</span>Alumnos</a>")
    return ui.cabecera(tabs=tabs, ses=ses, volver="/anfitrion", modo="anfitrion")


def _secciones(sel: str, aid: str) -> str:
    """Tira de secciones de la operación (el menú de `mi_academia_screen`);
    Cobros lleva al módulo existente `/anfitrion/cobros`."""
    q = f"?academia={up.quote(aid)}" if aid else ""
    items = [f"<a class='chip' href='/anfitrion/cobros{q}'>💰 Cobros</a>"]
    items += [f"<a class='chip{' sel' if k == sel else ''}' href='/anfitrion/academia/{k}{q}'>{ico} {t}</a>" for k, ico, t in _TABS]
    return "<nav class='aco-secc aco-noimp' aria-label='Secciones de la academia'>" + "".join(items) + "</nav>"


def _entrar_o_app(request: Request, ruta: str):
    ses = sesion.de_request(request)
    if ses:
        return ses, None
    if sesion.activo():
        return None, HTMLResponse("", status_code=302, headers={"Location": "/entrar?volver=" + up.quote(ruta, safe="")})
    cuerpo = ("<div class='panel' style='max-width:520px;margin:40px auto;text-align:center'>"
              "<h1 style='font-size:22px'>Mi academia</h1>"
              "<p class='sub'>En esta web aún no está activo el inicio de sesión. Administra tu academia desde la app.</p>"
              f"<div class='acciones' style='justify-content:center'><a class='btn' href='{PLAY_URL}'>Abrir Pichangol en Google Play</a></div></div>")
    return None, ui.shell("Mi academia", cuerpo, sesion=None)


def _contexto(request: Request, ruta: str, academia: str):
    """(ses, academias, academia elegida, respuesta de corte)."""
    ruta_q = ruta + (f"?academia={up.quote(academia)}" if academia else "")
    ses, resp = _entrar_o_app(request, ruta_q)
    if resp is not None:
        return None, [], None, resp
    acads = academias_de(ses["email"])
    if not acads:
        return ses, [], None, HTMLResponse("", status_code=302, headers={"Location": "/anfitrion/academia"})
    a = next((x for x in acads if x.get("id") == academia), acads[0])
    return ses, acads, a, None


def _chips_academia(acads: list[dict], a: dict, ruta: str) -> str:
    if len(acads) < 2:
        return ""
    return "<div class='chips' style='margin-top:12px'>" + "".join(
        f"<a class='chip{' sel' if x['id'] == a['id'] else ''}' href='{ruta}?academia={e(up.quote(x['id']))}'>{e(x.get('nombre') or 'Academia')}</a>"
        for x in acads) + "</div>"


def _pagina(ses: dict, acads: list[dict], a: dict, sel: str, titulo: str, sub: str, cuerpo: str, js: str = "",
            extra_head: str = "") -> HTMLResponse:
    ruta = f"/anfitrion/academia/{sel}"
    cfg = json.dumps({"aid": a["id"], "sim": _sim(a)}, ensure_ascii=False).replace("</", "<\\/")
    html = ("<a class='anf-back' href='/anfitrion/academia'>‹ Mi academia</a>"
            f"<h1 class='anf-hola' style='margin-top:6px'>{e(titulo)}</h1><p class='sub'>{e(a.get('nombre') or 'Academia')} · {sub}</p>"
            f"{_secciones(sel, a['id'])}{_chips_academia(acads, a, ruta)}{cuerpo}"
            f"<style>{_CSS}</style><script>window.ACO={cfg};{_JS_BASE}{js}</script>")
    return ui.shell(titulo, html, nav=_cab(ses), sesion=ses, ancho=True,
                    titulo_tab=f"{titulo} · Mi academia", extra_head=extra_head)


def _ses_json(request: Request):
    ses = sesion.de_request(request)
    if not ses:
        return None, JSONResponse({"ok": False, "error": "sesion_requerida", "mensaje": "Inicia sesión para continuar."}, status_code=401)
    return ses, None


def _mia(ses: dict, aid: str) -> dict | None:
    return next((x for x in academias_de(ses["email"]) if x.get("id") == aid), None)


def _no_encontrada() -> JSONResponse:
    return JSONResponse({"ok": False, "error": "no_encontrada", "mensaje": "No encontramos esa academia en tu cuenta."}, status_code=404)


_CSS = """
.aco-secc{display:flex;gap:8px;overflow-x:auto;margin-top:14px;padding-bottom:4px;scrollbar-width:none}
.aco-secc::-webkit-scrollbar{display:none}
.aco-secc .chip{flex:none}
.aco-card{background:var(--blanco);border:1px solid var(--trazo);border-radius:18px;padding:16px 18px;box-shadow:var(--sombra);min-width:0}
.aco-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(340px,100%),1fr));gap:14px;margin-top:16px}
.aco-fila{display:flex;align-items:center;gap:12px;min-width:0}
.aco-fila>div{min-width:0}
.aco-av{width:44px;height:44px;border-radius:50%;flex:none;display:flex;align-items:center;justify-content:center;font-weight:800;color:#fff;background:var(--esmeralda);overflow:hidden;font-size:17px}
.aco-av img{width:100%;height:100%;object-fit:cover}
.aco-cuota{display:flex;justify-content:space-between;gap:10px;align-items:center;padding:10px 0;border-top:1px solid var(--trazo);flex-wrap:wrap}
.aco-cuota .t{min-width:0;flex:1 1 180px}
.aco-cuota .acc{display:flex;gap:6px;flex-wrap:wrap}
.aco-mini{font-size:13px;padding:7px 11px;border-radius:999px}
.aco-n{font-size:12.5px;color:var(--tenue)}
.aco-bar{display:flex;align-items:flex-end;gap:10px;height:150px;margin-top:10px}
.aco-bar div{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:flex-end;height:100%;min-width:0}
.aco-bar i{display:block;width:100%;max-width:46px;border-radius:8px 8px 3px 3px;background:var(--esmeralda)}
.aco-bar small{font-size:11.5px;color:var(--tenue);margin-top:4px}
.aco-bar b{font-size:11px;margin-bottom:3px;white-space:nowrap}
.aco-rub{display:flex;gap:6px;flex-wrap:wrap}
.aco-rub .chip{padding:7px 12px;font-size:13px}
.aco-rub .chip.ok.sel{background:var(--ok-bg);border-color:var(--ok-fg);color:var(--ok-fg)}
.aco-rub .chip.warn.sel{background:var(--warn-bg);border-color:var(--warn-fg);color:var(--warn-fg)}
.aco-rub .chip.bad.sel{background:var(--bad-bg);border-color:var(--bad-fg);color:var(--bad-fg)}
.aco-hab{display:flex;justify-content:space-between;align-items:center;gap:10px;padding:10px 0;border-top:1px solid var(--trazo);flex-wrap:wrap}
.aco-prog{height:8px;border-radius:99px;background:var(--gris);overflow:hidden;margin-top:6px}
.aco-prog i{display:block;height:100%;background:var(--esmeralda)}
.aco-rk td:first-child{font-weight:800;width:52px;white-space:nowrap}
.aco-msgs{display:flex;flex-direction:column;gap:8px;max-height:60vh;overflow-y:auto;padding:14px;background:#EFEAE2;border-radius:16px}
.aco-msg{max-width:78%;padding:8px 12px;border-radius:14px;background:#fff;font-size:14.5px;overflow-wrap:anywhere;box-shadow:0 1px 1px rgba(0,0,0,.06)}
.aco-msg.yo{align-self:flex-end;background:#D9FDD3}
.aco-msg small{display:block;font-size:11px;color:var(--tenue);margin-top:2px;text-align:right}
.aco-dlg label{display:block;font-weight:700;font-size:13.5px;margin:12px 0 6px}
.aco-dlg .chips{margin:0}
.aco-dlg select,.aco-dlg input{width:100%}
.aco-sede{border:1px solid var(--trazo);border-radius:16px;padding:14px;margin-top:12px}
.aco-sede .mapa{height:200px;border-radius:12px;margin-top:8px}
.aco-dos{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(200px,100%),1fr));gap:10px}
.aco-aviso{margin-top:14px}
@media print{.cab,header,footer,.aco-noimp,.chips,.anf-back{display:none!important}.aco-card{box-shadow:none}}
"""

_JS_BASE = r"""
function acoPost(url,body,msg){pcgCargando(msg||'Guardando…',{demora:250});return fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body||{})}).then(function(r){return r.json().catch(function(){return {ok:false}})}).catch(function(){return {ok:false,mensaje:'No se pudo guardar. Revisa tu conexión.'}}).then(function(j){pcgCargando(false);return j})}
function acoErr(j){pcgAvisar({titulo:'No se pudo',mensaje:(j&&(j.mensaje||j.error))||'Inténtalo otra vez.',icono:'⚠️'})}
function acoDlg(){return document.getElementById('pcgDlgMsg')}
document.addEventListener('click',function(ev){var c=ev.target.closest('.aco-dlg [data-g] .chip');if(!c)return;var g=c.closest('[data-g]');if(g.dataset.multi){c.classList.toggle('sel')}else{g.querySelectorAll('.chip').forEach(function(x){x.classList.toggle('sel',x===c)})}});
function acoSel(g){var d=acoDlg();var s=d.querySelectorAll('[data-g="'+g+'"] .chip.sel');return Array.prototype.map.call(s,function(x){return x.dataset.v})}
function acoEsc(s){return String(s==null?'':s).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]})}
"""


# ══ COBROS ════════════════════════════════════════════════════════════════════

def _deuda(m: dict, hoy: date) -> tuple[float, bool]:
    """`_deudaDe` de mi_academia_screen: total pendiente y si hay algo vencido."""
    deuda, venc = 0.0, False
    for c in _cuotas(m):
        if not c.get("pagada"):
            deuda += _num(c.get("monto"))
            venc = venc or _vencida(c, hoy)
    return deuda, venc


def _av(m: dict) -> str:
    foto = str(m.get("fotoUrl") or "")
    ini = (str(m.get("nombre") or "?").strip()[:1] or "?").upper()
    return f"<div class='aco-av'>{f'<img src={chr(39)}{e(foto)}{chr(39)} alt={chr(39)}{chr(39)}>' if foto else e(ini)}</div>"


# ══ ASISTENCIA ════════════════════════════════════════════════════════════════

def _falta_sql(que: str) -> str:
    return (f"<div class='aviso warn aco-aviso'>⚙️ {que} en la web se activa cuando el equipo de Pichangol termine de "
            "configurarla. Mientras tanto, regístrala en la app.</div>")


@router.get("/anfitrion/academia/asistencia", response_class=HTMLResponse)
def pagina_asistencia(request: Request, academia: str = "", dia: str = "") -> HTMLResponse:
    ses, acads, a, resp = _contexto(request, "/anfitrion/academia/asistencia", academia)
    if resp is not None:
        return resp
    hoy = _ahora(a).date()
    try:
        d = date.fromisoformat(dia) if dia else hoy
    except ValueError:
        d = hoy
    clave = d.isoformat()
    mats = sorted(matriculas_de(a["id"]), key=lambda m: str(m.get("nombre") or "").lower())
    activa = tabla_existe("pichangol_academia_asistencias")
    marcas = asistencias_de(a["id"], clave) if activa else {}
    totales = clases_asistidas(a["id"]) if activa else {}
    presentes = sum(1 for m in mats if (marcas.get(m.get("id")) or {}).get("presente"))
    q = f"academia={up.quote(a['id'])}"
    nav_dia = (f"<div class='aco-noimp' style='display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-top:14px'>"
               f"<a class='chip' href='/anfitrion/academia/asistencia?{q}&dia={(d - timedelta(days=1)).isoformat()}'>‹</a>"
               f"<b style='font-size:17px'>{DIAS_CORTOS[d.weekday()]} {_f(d)}{' · Hoy' if d == hoy else ''}</b>"
               f"<a class='chip' href='/anfitrion/academia/asistencia?{q}&dia={(d + timedelta(days=1)).isoformat()}'>›</a>"
               f"<input type='date' id='acoDia' value='{clave}' style='max-width:170px'>"
               + ("" if d == hoy else f"<a class='chip' href='/anfitrion/academia/asistencia?{q}'>Hoy</a>") + "</div>")
    filas = ""
    for m in mats:
        mk = marcas.get(m.get("id")) or {}
        pres = bool(mk.get("presente"))
        filas += (f"<div class='aco-card aco-fila' style='justify-content:space-between;flex-wrap:wrap'>"
                  f"<div class='aco-fila' style='flex:1 1 200px'>{_av(m)}<div><b>{e(m.get('nombre') or 'Alumno')}</b>"
                  f"<div class='aco-n'>{totales.get(m.get('id'), 0)} clases{' · avisado ✓' if mk.get('avisado') else ''}"
                  f"{' · sin app' if not m.get('email') else ''}</div></div></div>"
                  f"<div class='aco-rub'><span class='chip ok{' sel' if pres else ''}' data-asis='{e(m.get('id'))}' data-v='1'>✅ Vino</span>"
                  f"<span class='chip bad{' sel' if mk and not pres else ''}' data-asis='{e(m.get('id'))}' data-v='0'>✖ Faltó</span></div></div>")
    cuerpo = (nav_dia + ("" if activa else _falta_sql("La asistencia"))
              + (f"<div class='kpis' style='margin-top:14px'><div class='kpi'><small>Presentes</small><b>{presentes} de {len(mats)}</b></div></div>"
                 "<div class='acciones aco-noimp' style='margin-top:14px'>"
                 f"<button class='btn sec' id='acoTodos' {'disabled' if not activa else ''}>✅ Todos presentes</button>"
                 f"<button class='btn' id='acoAvisar' {'disabled' if not activa else ''}>🔔 Avisar a los padres</button></div>"
                 f"<div style='display:grid;gap:10px;margin-top:14px'>{filas}</div>" if mats else
                 "<div class='anf-vacio' style='margin-top:18px'>Aún no tienes alumnos en esta academia.</div>"))
    js = "window.ACO.dia=" + json.dumps(clave) + ";window.ACO.ids=" + json.dumps([m.get("id") for m in mats]) + ";" + _JS_ASIS
    return _pagina(ses, acads, a, "asistencia", "Asistencia", "Marca quién vino y avisa a los padres.", cuerpo, js)


_JS_ASIS = r"""
var di=document.getElementById('acoDia');if(di)di.addEventListener('change',function(){if(di.value)pcgIr('?academia='+encodeURIComponent(ACO.aid)+'&dia='+di.value,'Cargando…')});
document.addEventListener('click',async function(ev){var c=ev.target.closest('[data-asis]');if(!c)return;
 var j=await acoPost('/anfitrion/academia/asistencia/marcar',{academia_id:ACO.aid,dia:ACO.dia,alumno_ids:[c.dataset.asis],presente:c.dataset.v==='1'});
 if(j.ok){c.parentNode.querySelectorAll('.chip').forEach(function(x){x.classList.toggle('sel',x===c)});pcgToast(c.dataset.v==='1'?'✅ Presente':'Falta registrada')}else acoErr(j)});
var bt=document.getElementById('acoTodos');if(bt)bt.addEventListener('click',async function(){var j=await acoPost('/anfitrion/academia/asistencia/marcar',{academia_id:ACO.aid,dia:ACO.dia,alumno_ids:ACO.ids,presente:true});if(j.ok)pcgRecargar('✅ Todos presentes');else acoErr(j)});
var ba=document.getElementById('acoAvisar');if(ba)ba.addEventListener('click',async function(){
 if(!await pcgConfirmar({titulo:'Avisar a los padres',mensaje:'A los que tienen la app les llega un mensaje al instante (✅ asistió / ⚠️ faltó). A los demás te dejamos el WhatsApp listo para enviar. A quien ya avisaste hoy no se le reenvía.',confirmar:'Avisar',icono:'🔔'}))return;
 var j=await acoPost('/anfitrion/academia/asistencia/avisar',{academia_id:ACO.aid,dia:ACO.dia},'Avisando a los padres…');if(!j.ok){acoErr(j);return}
 var h='<p style="margin:0">'+(j.enviados?('✅ Avisé a '+j.enviados+' padre(s) por la app.'):(j.pendientes?'Ningún padre con la app en esta lista.':'Ya avisaste a todos hoy. 🎉'))+'</p>';
 if((j.whatsapp||[]).length){h+='<p style="margin:12px 0 6px"><b>Sin la app · envía por WhatsApp</b></p>';j.whatsapp.forEach(function(w){h+='<div class="aco-cuota"><span>'+acoEsc(w.nombre)+'</span>'+(w.url?'<a class="btn aco-mini" target="_blank" rel="noopener" data-wa-av="'+acoEsc(w.id)+'" href="'+acoEsc(w.url)+'">Enviar</a>':'<span class="aco-n">Sin WhatsApp</span>')+'</div>'})}
 await pcgAvisar({titulo:'Avisos',html:h,icono:'🔔'});location.reload()});
document.addEventListener('click',function(ev){var w=ev.target.closest('[data-wa-av]');if(!w)return;fetch('/anfitrion/academia/asistencia/avisado',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({academia_id:ACO.aid,dia:ACO.dia,alumno_id:w.dataset.waAv})});w.textContent='Enviado ✓'});
"""


def _dia_ok(v) -> str:
    try:
        return date.fromisoformat(str(v or "")).isoformat()
    except ValueError:
        return ""


@router.post("/anfitrion/academia/asistencia/marcar")
def marcar_asistencia(request: Request, body: dict = Body(default_factory=dict)) -> JSONResponse:
    ses, err = _ses_json(request)
    if err:
        return err
    a = _mia(ses, str(body.get("academia_id") or ""))
    if not a:
        return _no_encontrada()
    dia = _dia_ok(body.get("dia"))
    validos = {m.get("id") for m in matriculas_de(a["id"])}
    ids = [str(x) for x in (body.get("alumno_ids") or []) if str(x) in validos]
    if not dia or not ids:
        return JSONResponse({"ok": False, "error": "datos", "mensaje": "Elige el día y el alumno."}, status_code=400)
    if not tabla_existe("pichangol_academia_asistencias"):
        return JSONResponse({"ok": False, "error": "no_disponible", "mensaje": "La asistencia en la web aún no está activa. Regístrala en la app."}, status_code=503)
    if not guardar_asistencia(a["id"], ids, dia, bool(body.get("presente"))):
        return JSONResponse({"ok": False, "error": "no_guardado", "mensaje": "No se pudo guardar la asistencia."}, status_code=500)
    return JSONResponse({"ok": True})


@router.post("/anfitrion/academia/asistencia/avisar")
def avisar_asistencia(request: Request, body: dict = Body(default_factory=dict)) -> JSONResponse:
    """`AsistenciaScreen._avisar`: mensaje de chat del app a los alumnos con
    cuenta (hilo `<academia>|<correo>`) y WhatsApp armado para los que no."""
    ses, err = _ses_json(request)
    if err:
        return err
    a = _mia(ses, str(body.get("academia_id") or ""))
    if not a:
        return _no_encontrada()
    dia = _dia_ok(body.get("dia"))
    if not dia or not tabla_existe("pichangol_academia_asistencias"):
        return JSONResponse({"ok": False, "error": "no_disponible", "mensaje": "La asistencia en la web aún no está activa."}, status_code=503)
    marcas = asistencias_de(a["id"], dia)
    nombre_ac = a.get("nombre") or "la academia"
    pendientes = [m for m in matriculas_de(a["id"]) if not (marcas.get(m.get("id")) or {}).get("avisado")]
    enviados, avisados, wa = 0, [], []
    for m in pendientes:
        pres = bool((marcas.get(m.get("id")) or {}).get("presente"))
        txt = f"✅ {m.get('nombre')} asistió hoy a {nombre_ac}." if pres else f"⚠️ {m.get('nombre')} faltó hoy a {nombre_ac}."
        if m.get("email"):
            if enviar_mensaje(a["id"], m["email"], ses["email"], ses.get("nombre") or "", txt, sufijo=f"_{m.get('id')}"):
                enviados += 1
                avisados.append(m["id"])
        else:
            tel = _tel_wa(_wa_contacto(m), a)
            wa.append({"id": m.get("id"), "nombre": m.get("nombre"), "url": ui.enlace_whatsapp(txt, tel) if tel else ""})
    marcar_avisados(a["id"], avisados, dia)
    return JSONResponse({"ok": True, "enviados": enviados, "pendientes": len(pendientes), "whatsapp": wa})


@router.post("/anfitrion/academia/asistencia/avisado")
def marcar_avisado(request: Request, body: dict = Body(default_factory=dict)) -> JSONResponse:
    ses, err = _ses_json(request)
    if err:
        return err
    a = _mia(ses, str(body.get("academia_id") or ""))
    if not a:
        return _no_encontrada()
    dia, aid_al = _dia_ok(body.get("dia")), str(body.get("alumno_id") or "")
    if dia and aid_al in {m.get("id") for m in matriculas_de(a["id"])}:
        marcar_avisados(a["id"], [aid_al], dia)
    return JSONResponse({"ok": True})


# ══ EVALUACIÓN ════════════════════════════════════════════════════════════════

def plantilla_de(a: dict) -> dict | None:
    """Plantilla Pichangol del deporte (`plantillaPara`)."""
    return _PLANES.get(str(a.get("deporte") or "tenis"))


def opciones_plan(a: dict) -> list[dict]:
    """Planes sobre los que se evalúa: los PROPIOS de la academia (los que el
    profe armó en el app o en otra pantalla; misma tabla) y la plantilla del
    deporte solo si no hay propios o si ya tiene evaluaciones guardadas (así no
    se esconde lo evaluado antes de crear un plan propio)."""
    propios = planes_de(str(a.get("id") or ""))
    base = plantilla_de(a)
    if base and (not propios or (tabla_existe("pichangol_academia_evaluaciones")
                                 and evaluaciones_de(str(a.get("id") or ""), base["id"]))):
        return propios + [base]
    return propios


def plan_de(a: dict, plan_id: str = "", opciones: list[dict] | None = None) -> dict | None:
    """El plan pedido (si es de la academia) o el primero: el propio más
    reciente y, sin propios, la plantilla Pichangol del deporte."""
    ops_ = opciones if opciones is not None else opciones_plan(a)
    if plan_id:
        return next((p for p in ops_ if p["id"] == plan_id), None)
    return ops_[0] if ops_ else None


def progreso(plan: dict, niveles: dict[str, str]) -> dict:
    """`AppState.progresoAlumno`: conteos y % sobre el máximo (todas Logrado)."""
    out = {"total": len(plan["habilidades"]), "logrado": 0, "enProceso": 0, "inicial": 0, "sinEvaluar": 0}
    suma = 0
    for h in plan["habilidades"]:
        n = niveles.get(h)
        if n not in NIVELES:
            out["sinEvaluar"] += 1
            continue
        suma += NIVELES[n][1]
        out[n] += 1
    out["pct"] = (suma / (out["total"] * 2) * 100) if out["total"] else 0.0
    return out


@router.get("/anfitrion/academia/evaluaciones", response_class=HTMLResponse)
def pagina_evaluaciones(request: Request, academia: str = "", alumno: str = "", plan: str = "") -> HTMLResponse:
    ses, acads, a, resp = _contexto(request, "/anfitrion/academia/evaluaciones", academia)
    if resp is not None:
        return resp
    opciones = opciones_plan(a)
    plan = plan_de(a, plan, opciones) or plan_de(a, "", opciones)
    mats = sorted(matriculas_de(a["id"]), key=lambda m: str(m.get("nombre") or "").lower())
    q = f"academia={up.quote(a['id'])}"
    if not plan:
        cuerpo = ("<div class='anf-vacio' style='margin-top:18px'>Aún no tienes un plan de trabajo para este deporte. "
                  "Arma tu plan en la app (Mi academia → Planes de trabajo) y aparecerá aquí.</div>")
        return _pagina(ses, acads, a, "evaluaciones", "Evaluación", "Rúbrica y bitácora de clases.", cuerpo)
    q = f"{q}&plan={up.quote(plan['id'])}"
    chips_plan = ""
    if len(opciones) > 1:
        chips_plan = "<div class='chips aco-noimp' style='margin-top:12px'>" + "".join(
            f"<a class='chip{' sel' if p['id'] == plan['id'] else ''}' href='/anfitrion/academia/evaluaciones?academia={e(up.quote(a['id']))}"
            f"&plan={e(up.quote(p['id']))}{('&alumno=' + e(up.quote(alumno))) if alumno else ''}'>"
            f"{'📘' if p.get('propio') else '📗'} {e(p['nombre'])}</a>" for p in opciones) + "</div>"
    activa = tabla_existe("pichangol_academia_evaluaciones")
    evals = evaluaciones_de(a["id"], plan["id"]) if activa else {}
    sel = next((m for m in mats if m.get("id") == alumno), None)
    if not sel:
        tarjetas = ""
        for m in mats:
            p = progreso(plan, {h: n for (al, h), n in evals.items() if al == m.get("id")})
            tarjetas += (f"<a class='aco-card aco-fila' style='text-decoration:none;color:inherit' href='/anfitrion/academia/evaluaciones?{q}&alumno={e(up.quote(str(m.get('id'))))}'>"
                         f"{_av(m)}<div style='flex:1'><b>{e(m.get('nombre') or 'Alumno')}</b>"
                         f"<div class='aco-n'>{p['logrado']} logradas · {p['enProceso']} en proceso · {p['sinEvaluar']} sin evaluar</div>"
                         f"<div class='aco-prog'><i style='width:{p['pct']:.0f}%'></i></div></div><b>{p['pct']:.0f}%</b></a>")
        cuerpo = ((_falta_sql("La evaluación") if not activa else "") + chips_plan
                  + f"<div class='aco-card' style='margin-top:14px'><b>📘 {e(plan['nombre'])}</b><div class='aco-n'>{e(plan['nivel'])} · {len(plan['habilidades'])} habilidades · {len(plan['sesiones'])} clases</div></div>"
                  + (f"<div class='aco-grid'>{tarjetas}</div>" if mats else "<div class='anf-vacio' style='margin-top:18px'>Aún no tienes alumnos en esta academia.</div>"))
        return _pagina(ses, acads, a, "evaluaciones", "Evaluación", "Toca un alumno para evaluarlo.", cuerpo)
    niveles = {h: n for (al, h), n in evals.items() if al == sel.get("id")}
    p = progreso(plan, niveles)
    rub = ""
    for h in plan["habilidades"]:
        chips = "".join(f"<span class='chip {cls}{' sel' if niveles.get(h) == k else ''}' data-eval='{e(h)}' data-v='{k}'>{t}</span>"
                        for k, (t, _v, cls) in NIVELES.items())
        rub += f"<div class='aco-hab'><b style='font-size:14.5px'>{e(h)}</b><div class='aco-rub'>{chips}</div></div>"
    notas = notas_de(a["id"], str(sel.get("id"))) if tabla_existe("pichangol_academia_notas") else []
    titulos = {s["numero"]: s["titulo"] for s in plan["sesiones"]}
    dadas = len({n["sesionNumero"] for n in notas if n["planId"] == plan["id"] and n["sesionNumero"] > 0})
    bit = ""
    for n in notas:
        t, cls = DESEMPENOS.get(n["desempeno"], ("", "gris"))
        f = _dt(n["fecha"])
        ses_t = f"Clase {n['sesionNumero']}: {titulos.get(n['sesionNumero'], '')}" if n["sesionNumero"] > 0 else "Clase suelta"
        bit += (f"<div class='aco-cuota'><div class='t'><b>{_f(f)}</b> <span class='pill {cls}'>{e(t)}</span>"
                f"<div class='aco-n'>{e(ses_t)}</div>{('<div>' + e(n['nota']) + '</div>') if n['nota'] else ''}</div>"
                f"<button class='btn sec aco-mini' data-nota-borrar='{e(n['id'])}'>Quitar</button></div>")
    cuerpo = (f"<a class='anf-back' href='/anfitrion/academia/evaluaciones?{q}'>‹ Todos los alumnos</a>"
              + ("" if activa else _falta_sql("La evaluación")) + chips_plan
              + f"<div class='aco-card aco-fila' style='margin-top:12px'>{_av(sel)}<div style='flex:1'><b style='font-size:17px'>{e(sel.get('nombre'))}</b>"
              f"<div class='aco-n'>{e(plan['nombre'])}</div><div class='aco-prog'><i style='width:{p['pct']:.0f}%'></i></div></div>"
              f"<b style='font-size:22px'>{p['pct']:.0f}%</b></div>"
              f"<div class='aco-card' style='margin-top:14px'><b>Habilidades</b><div class='aco-n'>Cada toque se guarda al instante.</div>{rub}</div>"
              f"<div class='aco-card' style='margin-top:14px'><div style='display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;align-items:center'>"
              f"<div><b>Bitácora de clases</b><div class='aco-n'>{dadas}/{len(plan['sesiones'])} clases del plan</div></div>"
              f"<button class='btn' id='acoNota'>＋ Registrar clase de hoy</button></div>"
              + (bit or "<p class='aco-n'>Aún no registras clases de este alumno.</p>") + "</div>")
    cfg = {"alumno": sel.get("id"), "plan": plan["id"], "sesiones": plan["sesiones"], "obs": OBSERVACIONES,
           "desemp": {k: v[0] for k, v in DESEMPENOS.items()}}
    js = "Object.assign(window.ACO," + json.dumps(cfg, ensure_ascii=False).replace("</", "<\\/") + ");" + _JS_EVAL
    return _pagina(ses, acads, a, "evaluaciones", "Evaluación", "Rúbrica por habilidad y bitácora de clases.", cuerpo, js)


_JS_EVAL = r"""
document.addEventListener('click',async function(ev){
 var c=ev.target.closest('[data-eval]');
 if(c){var j=await acoPost('/anfitrion/academia/evaluaciones/evaluar',{academia_id:ACO.aid,alumno_id:ACO.alumno,plan_id:ACO.plan,habilidad:c.dataset.eval,nivel:c.dataset.v});
  if(j.ok){c.parentNode.querySelectorAll('.chip').forEach(function(x){x.classList.toggle('sel',x===c)});pcgToast('Guardado')}else acoErr(j);return}
 var d=ev.target.closest('[data-nota-borrar]');
 if(d){if(!await pcgConfirmar({titulo:'Quitar esta clase',mensaje:'Se borra de la bitácora del alumno.',confirmar:'Quitar',destructivo:true}))return;
  var j2=await acoPost('/anfitrion/academia/evaluaciones/nota/eliminar',{academia_id:ACO.aid,nota_id:d.dataset.notaBorrar});if(j2.ok)pcgRecargar('Quitada');else acoErr(j2)}
});
var bn=document.getElementById('acoNota');if(bn)bn.addEventListener('click',async function(){
 var h="<div class='aco-dlg'><label>¿Cómo le fue?</label><div class='chips' data-g='des'>";Object.keys(ACO.desemp).forEach(function(k,i){h+="<span class='chip"+(i===0?' sel':'')+"' data-v='"+k+"'>"+ACO.desemp[k]+"</span>"});
 h+="</div><label>Clase del plan</label><select id='acoSes'><option value='0'>Clase suelta</option>";ACO.sesiones.forEach(function(s){h+="<option value='"+s.numero+"'>Clase "+s.numero+": "+acoEsc(s.titulo)+"</option>"});
 h+="</select><label>Observaciones <span class='aco-n'>(opcional)</span></label><div class='chips' data-g='obs' data-multi='1'>";ACO.obs.forEach(function(o){h+="<span class='chip' data-v='"+acoEsc(o)+"'>"+acoEsc(o)+"</span>"});h+="</div></div>";
 if(!await pcgConfirmar({titulo:'Clase de hoy',html:h,confirmar:'Guardar clase',icono:'📝'}))return;
 var j=await acoPost('/anfitrion/academia/evaluaciones/nota',{academia_id:ACO.aid,alumno_id:ACO.alumno,plan_id:ACO.plan,sesion:+document.getElementById('acoSes').value,desempeno:acoSel('des')[0]||'bien',observaciones:acoSel('obs')});
 if(j.ok)pcgRecargar('📝 Clase registrada');else acoErr(j)});
"""


def _alumno_de(a: dict, alumno_id: str) -> dict | None:
    return next((m for m in matriculas_de(a["id"]) if m.get("id") == alumno_id), None)


@router.post("/anfitrion/academia/evaluaciones/evaluar")
def evaluar(request: Request, body: dict = Body(default_factory=dict)) -> JSONResponse:
    ses, err = _ses_json(request)
    if err:
        return err
    a = _mia(ses, str(body.get("academia_id") or ""))
    if not a:
        return _no_encontrada()
    plan = plan_de(a, str(body.get("plan_id") or ""))
    hab, nivel = str(body.get("habilidad") or ""), str(body.get("nivel") or "")
    if not plan or hab not in plan["habilidades"] or nivel not in NIVELES or not _alumno_de(a, str(body.get("alumno_id") or "")):
        return JSONResponse({"ok": False, "error": "datos", "mensaje": "Elige una habilidad y un nivel."}, status_code=400)
    if not guardar_evaluacion(a["id"], str(body["alumno_id"]), plan["id"], hab, nivel):
        return JSONResponse({"ok": False, "error": "no_disponible", "mensaje": "La evaluación en la web aún no está activa. Regístrala en la app."}, status_code=503)
    return JSONResponse({"ok": True})


@router.post("/anfitrion/academia/evaluaciones/nota")
def nota_clase(request: Request, body: dict = Body(default_factory=dict)) -> JSONResponse:
    """`AppState.agregarNotaClase` (una entrada por clase; historial, no se pisa)."""
    ses, err = _ses_json(request)
    if err:
        return err
    a = _mia(ses, str(body.get("academia_id") or ""))
    if not a:
        return _no_encontrada()
    plan = plan_de(a, str(body.get("plan_id") or ""))
    alumno_id = str(body.get("alumno_id") or "")
    des = str(body.get("desempeno") or "")
    sesion_n = int(_num(body.get("sesion"), 0))
    if not plan or des not in DESEMPENOS or not _alumno_de(a, alumno_id) or (sesion_n and sesion_n not in {s["numero"] for s in plan["sesiones"]}):
        return JSONResponse({"ok": False, "error": "datos", "mensaje": "Elige cómo le fue."}, status_code=400)
    obs = [o for o in (body.get("observaciones") or []) if o in OBSERVACIONES]
    nota = {"id": f"nota_{_us()}", "alumnoId": alumno_id, "planId": plan["id"], "sesionNumero": sesion_n,
            "fecha": _ahora(a).date().isoformat(), "desempeno": des, "nota": " · ".join(obs)}
    if not guardar_nota(a["id"], nota):
        return JSONResponse({"ok": False, "error": "no_disponible", "mensaje": "La bitácora en la web aún no está activa. Regístrala en la app."}, status_code=503)
    return JSONResponse({"ok": True, "id": nota["id"]})


@router.post("/anfitrion/academia/evaluaciones/nota/eliminar")
def eliminar_nota(request: Request, body: dict = Body(default_factory=dict)) -> JSONResponse:
    ses, err = _ses_json(request)
    if err:
        return err
    a = _mia(ses, str(body.get("academia_id") or ""))
    if not a:
        return _no_encontrada()
    if not borrar_nota(a["id"], str(body.get("nota_id") or "")):
        return JSONResponse({"ok": False, "error": "no_encontrada", "mensaje": "No encontramos esa clase."}, status_code=404)
    return JSONResponse({"ok": True})


# ══ RANKING INTERNO ═══════════════════════════════════════════════════════════

def ranking(a: dict, alumnos: list[dict], sede: str = "", categoria: str = "") -> list[dict]:
    """`Academia.ranking`: todos los alumnos (los que no jugaron al fondo),
    filtros por sede y categoría; orden puntos → % victorias → PG."""
    cats = a.get("categorias") or {}
    st: dict[str, dict] = {}
    for m in alumnos:
        c = str(cats.get(m.get("id")) or "")
        if categoria and c != categoria:
            continue
        st[m["id"]] = {"id": m["id"], "nombre": m.get("nombre") or "", "foto": m.get("fotoUrl") or "", "categoria": c, "pg": 0, "pp": 0}
    for p in a.get("partidos") or []:
        if not isinstance(p, dict) or (sede and str(p.get("sedeId") or "") != sede):
            continue
        for j in (p.get("jugadorAId"), p.get("jugadorBId")):
            s = st.get(j)
            if s is not None:
                s["pg" if p.get("ganadorId") == j else "pp"] += 1
    out = []
    for s in st.values():
        pj = s["pg"] + s["pp"]
        s.update(pj=pj, puntos=s["pg"] * PUNTOS_VICTORIA + s["pp"] * PUNTOS_DERROTA, pct=(s["pg"] / pj * 100) if pj else 0.0)
        out.append(s)
    out.sort(key=lambda s: (-s["puntos"], -s["pct"], -s["pg"]))
    return out


@router.get("/anfitrion/academia/ranking", response_class=HTMLResponse)
def pagina_ranking(request: Request, academia: str = "", sede: str = "", categoria: str = "") -> HTMLResponse:
    ses, acads, a, resp = _contexto(request, "/anfitrion/academia/ranking", academia)
    if resp is not None:
        return resp
    mats = matriculas_de(a["id"])
    cats_usadas = sorted({str(c) for c in (a.get("categorias") or {}).values() if c})
    sedes = [s for s in (a.get("sedes") or []) if isinstance(s, dict)]
    tabla = ranking(a, mats, sede, categoria)
    q = f"academia={up.quote(a['id'])}"
    filtros = ""
    if len(sedes) > 1:
        filtros += "<div class='chips aco-noimp' style='margin-top:12px'>" + f"<a class='chip{'' if sede else ' sel'}' href='?{q}&categoria={e(up.quote(categoria))}'>Todas las sedes</a>" + "".join(
            f"<a class='chip{' sel' if s.get('id') == sede else ''}' href='?{q}&sede={e(up.quote(str(s.get('id'))))}&categoria={e(up.quote(categoria))}'>📍 {e(s.get('nombre'))}</a>" for s in sedes) + "</div>"
    if cats_usadas:
        filtros += "<div class='chips aco-noimp' style='margin-top:10px'>" + f"<a class='chip{'' if categoria else ' sel'}' href='?{q}&sede={e(up.quote(sede))}'>Todas</a>" + "".join(
            f"<a class='chip{' sel' if c == categoria else ''}' href='?{q}&sede={e(up.quote(sede))}&categoria={e(up.quote(c))}'>{e(c)}</a>" for c in cats_usadas) + "</div>"
    filas = "".join(
        f"<tr><td>{i + 1}{' 🥇' if i == 0 and s['pj'] else (' 🥈' if i == 1 and s['pj'] else (' 🥉' if i == 2 and s['pj'] else ''))}</td>"
        f"<td><b>{e(s['nombre'])}</b>{('<div class=aco-n>' + e(s['categoria']) + '</div>') if s['categoria'] else ''}</td>"
        f"<td><b>{s['puntos']}</b></td><td>{s['pj']}</td><td>{s['pg']}</td><td>{s['pp']}</td><td>{s['pct']:.0f}%</td>"
        f"<td><button class='chip aco-mini aco-noimp' data-cat='{e(s['id'])}' data-nombre='{e(s['nombre'])}' data-actual='{e(s['categoria'])}'>🏷️ Categoría</button></td></tr>"
        for i, s in enumerate(tabla))
    nombres_sede = {s.get("id"): s.get("nombre") for s in sedes}
    partidos = sorted([p for p in (a.get("partidos") or []) if isinstance(p, dict)], key=lambda p: str(p.get("fecha") or ""), reverse=True)
    lista = ""
    for p in partidos[:60]:
        gan = p.get("jugadorANombre") if p.get("ganadorId") == p.get("jugadorAId") else p.get("jugadorBNombre")
        f = _dt(p.get("fecha"))
        lista += (f"<div class='aco-cuota'><div class='t'><b>{e(p.get('jugadorANombre'))}</b> vs <b>{e(p.get('jugadorBNombre'))}</b>"
                  f"<div class='aco-n'>{_f(f)} · ganó {e(gan)}{(' · ' + e(p.get('marcador'))) if p.get('marcador') else ''}"
                  f"{(' · 📍 ' + e(nombres_sede.get(p.get('sedeId'), ''))) if p.get('sedeId') and nombres_sede.get(p.get('sedeId')) else ''}</div></div>"
                  f"<button class='btn sec aco-mini aco-noimp' data-partido-borrar='{e(p.get('id'))}'>Quitar</button></div>")
    cuerpo = (filtros
              + "<div class='acciones aco-noimp' style='margin-top:14px'><button class='btn' id='acoPartido'"
              + (" disabled" if len(mats) < 2 else "") + ">＋ Registrar resultado</button></div>"
              + (f"<div class='tabla aco-rk' style='margin-top:14px'><table><thead><tr><th>#</th><th>Jugador</th><th>Pts</th><th>PJ</th><th>PG</th><th>PP</th><th>%</th><th></th></tr></thead><tbody>{filas}</tbody></table></div>"
                 if tabla else "<div class='anf-vacio' style='margin-top:18px'>Aún no hay alumnos en esta vista.</div>")
              + f"<p class='aco-n' style='margin-top:8px'>Victoria {PUNTOS_VICTORIA} pts · derrota {PUNTOS_DERROTA} pt. Estos partidos también suman al ranking global de Pichangol.</p>"
              + f"<div class='aco-card' style='margin-top:16px'><b>Partidos ({len(partidos)})</b>{lista or '<p class=aco-n>Aún no registras partidos.</p>'}</div>")
    cfg = {"alumnos": sorted([{"id": m.get("id"), "nombre": m.get("nombre")} for m in mats], key=lambda x: str(x["nombre"] or "").lower()),
           "sedes": [{"id": s.get("id"), "nombre": s.get("nombre")} for s in sedes] if len(sedes) > 1 else [],
           "cats": sorted(set(CATEGORIAS_RANKING) | set(cats_usadas), key=lambda c: (c not in CATEGORIAS_RANKING, CATEGORIAS_RANKING.index(c) if c in CATEGORIAS_RANKING else 0, c))}
    js = "Object.assign(window.ACO," + json.dumps(cfg, ensure_ascii=False).replace("</", "<\\/") + ");" + _JS_RANK
    return _pagina(ses, acads, a, "ranking", "Ranking", "Tabla de posiciones de tus alumnos.", cuerpo, js)


_JS_RANK = r"""
function opts(sel){var h='<option value="">Elige…</option>';ACO.alumnos.forEach(function(a){h+='<option value="'+acoEsc(a.id)+'"'+(a.id===sel?' selected':'')+'>'+acoEsc(a.nombre)+'</option>'});return h}
var bp=document.getElementById('acoPartido');if(bp)bp.addEventListener('click',async function(){
 var h="<div class='aco-dlg'><label>Jugador A</label><select id='acoA'>"+opts('')+"</select><label>Jugador B</label><select id='acoB'>"+opts('')+"</select>"+
  "<label>¿Quién ganó?</label><div class='chips' data-g='gan'><span class='chip sel' data-v='A'>Jugador A</span><span class='chip' data-v='B'>Jugador B</span></div>"+
  "<label>Marcador <span class='aco-n'>(opcional, ej. 6-3 6-4)</span></label><input id='acoMarc' maxlength='40' inputmode='numeric' pattern='[0-9 ()\\-/,.]*' placeholder='6-3 6-4'>";
 if(ACO.sedes.length){h+="<label>Sede</label><select id='acoSede'><option value=''>Sin sede</option>";ACO.sedes.forEach(function(s){h+="<option value='"+acoEsc(s.id)+"'>"+acoEsc(s.nombre)+"</option>"});h+="</select>"}
 h+="</div>";
 if(!await pcgConfirmar({titulo:'Registrar resultado',html:h,confirmar:'Guardar',icono:'🏆'}))return;
 var A=document.getElementById('acoA').value,B=document.getElementById('acoB').value,g=acoSel('gan')[0];
 if(!A||!B){pcgAvisar({titulo:'Faltan datos',mensaje:'Elige los dos jugadores.'});return}if(A===B){pcgAvisar({titulo:'Revisa',mensaje:'Deben ser jugadores distintos.'});return}
 var j=await acoPost('/anfitrion/academia/ranking/partido',{academia_id:ACO.aid,jugador_a:A,jugador_b:B,ganador:g==='B'?B:A,marcador:document.getElementById('acoMarc').value,sede_id:(document.getElementById('acoSede')||{}).value||''});
 if(j.ok)pcgRecargar('Resultado registrado. Ranking actualizado.');else acoErr(j)});
document.addEventListener('click',async function(ev){
 var d=ev.target.closest('[data-partido-borrar]');
 if(d){if(!await pcgConfirmar({titulo:'Quitar partido',mensaje:'El ranking se recalcula sin este resultado.',confirmar:'Quitar',destructivo:true}))return;
  var j=await acoPost('/anfitrion/academia/ranking/partido/eliminar',{academia_id:ACO.aid,partido_id:d.dataset.partidoBorrar});if(j.ok)pcgRecargar('Partido quitado');else acoErr(j);return}
 var c=ev.target.closest('[data-cat]');
 if(c){var h="<div class='aco-dlg'><p style='margin:0'>"+acoEsc(c.dataset.nombre)+"</p><label>Categoría</label><div class='chips' data-g='cat'><span class='chip"+(c.dataset.actual?'':' sel')+"' data-v=''>Sin categoría</span>";
  ACO.cats.forEach(function(k){h+="<span class='chip"+(k===c.dataset.actual?' sel':'')+"' data-v='"+acoEsc(k)+"'>"+acoEsc(k)+"</span>"});h+="</div></div>";
  if(!await pcgConfirmar({titulo:'Categoría del jugador',html:h,confirmar:'Guardar',icono:'🏷️'}))return;
  var j2=await acoPost('/anfitrion/academia/ranking/categoria',{academia_id:ACO.aid,alumno_id:c.dataset.cat,categoria:acoSel('cat')[0]||''});if(j2.ok)pcgRecargar('Categoría guardada');else acoErr(j2)}
});
"""


@router.post("/anfitrion/academia/ranking/partido")
def registrar_partido(request: Request, body: dict = Body(default_factory=dict)) -> JSONResponse:
    """`_RegistrarResultadoSheet._guardar` + `AppState.registrarPartido`."""
    ses, err = _ses_json(request)
    if err:
        return err
    aid = str(body.get("academia_id") or "")
    a = _mia(ses, aid)
    if not a:
        return _no_encontrada()
    ja, jb, gan = str(body.get("jugador_a") or ""), str(body.get("jugador_b") or ""), str(body.get("ganador") or "")
    marcador = str(body.get("marcador") or "").strip()
    sede = str(body.get("sede_id") or "")
    mats = {m.get("id"): m for m in matriculas_de(aid)}
    if ja not in mats or jb not in mats:
        return JSONResponse({"ok": False, "error": "jugadores", "mensaje": "Elige los dos jugadores."}, status_code=400)
    if ja == jb:
        return JSONResponse({"ok": False, "error": "iguales", "mensaje": "Deben ser jugadores distintos."}, status_code=400)
    if gan not in (ja, jb):
        return JSONResponse({"ok": False, "error": "ganador", "mensaje": "Marca quién ganó."}, status_code=400)
    if not _RE_MARCADOR.match(marcador):
        return JSONResponse({"ok": False, "error": "marcador", "mensaje": "El marcador solo lleva números (ej. 6-3 6-4)."}, status_code=400)
    if sede and sede not in {s.get("id") for s in (a.get("sedes") or []) if isinstance(s, dict)}:
        sede = ""
    A, B = mats[ja], mats[jb]
    partido = {"id": f"pr_{_us()}", "fecha": _iso(_ahora(a)), "jugadorAId": ja, "jugadorANombre": A.get("nombre") or "",
               "jugadorBId": jb, "jugadorBNombre": B.get("nombre") or "", "marcador": marcador, "ganadorId": gan, "sedeId": sede}
    if str(A.get("email") or "").strip():
        partido["jugadorAEmail"] = str(A["email"]).strip().lower()
    if str(B.get("email") or "").strip():
        partido["jugadorBEmail"] = str(B["email"]).strip().lower()

    def aplicar(data: dict):
        data["partidos"] = [p for p in (data.get("partidos") or []) if isinstance(p, dict)] + [partido]
        return True

    if not mutar_academia(aid, ses["email"], aplicar):
        return JSONResponse({"ok": False, "error": "no_guardado", "mensaje": "No se pudo guardar el resultado."}, status_code=500)
    return JSONResponse({"ok": True, "partido": partido})


@router.post("/anfitrion/academia/ranking/partido/eliminar")
def eliminar_partido(request: Request, body: dict = Body(default_factory=dict)) -> JSONResponse:
    ses, err = _ses_json(request)
    if err:
        return err
    aid, pid = str(body.get("academia_id") or ""), str(body.get("partido_id") or "")

    def aplicar(data: dict):
        antes = [p for p in (data.get("partidos") or []) if isinstance(p, dict)]
        data["partidos"] = [p for p in antes if p.get("id") != pid]
        return True if len(data["partidos"]) < len(antes) else None

    if not pid or not mutar_academia(aid, ses["email"], aplicar):
        return JSONResponse({"ok": False, "error": "no_encontrado", "mensaje": "No encontramos ese partido."}, status_code=404)
    return JSONResponse({"ok": True})


@router.post("/anfitrion/academia/ranking/categoria")
def fijar_categoria(request: Request, body: dict = Body(default_factory=dict)) -> JSONResponse:
    """`AppState.setCategoriaAlumno` (vacío = quita la categoría)."""
    ses, err = _ses_json(request)
    if err:
        return err
    aid, alumno_id = str(body.get("academia_id") or ""), str(body.get("alumno_id") or "")
    cat = str(body.get("categoria") or "").strip()
    a = _mia(ses, aid)
    if not a:
        return _no_encontrada()
    permitidas = set(CATEGORIAS_RANKING) | {str(c) for c in (a.get("categorias") or {}).values()}
    if cat and cat not in permitidas:
        return JSONResponse({"ok": False, "error": "categoria", "mensaje": "Elige una categoría de la lista."}, status_code=400)
    if not _alumno_de(a, alumno_id):
        return JSONResponse({"ok": False, "error": "alumno", "mensaje": "No encontramos a ese alumno."}, status_code=404)

    def aplicar(data: dict):
        cats = dict(data.get("categorias") or {})
        if cat:
            cats[alumno_id] = cat
        else:
            cats.pop(alumno_id, None)
        data["categorias"] = cats
        return True

    if not mutar_academia(aid, ses["email"], aplicar):
        return JSONResponse({"ok": False, "error": "no_guardado", "mensaje": "No se pudo guardar la categoría."}, status_code=500)
    return JSONResponse({"ok": True})


# ══ REPORTES ══════════════════════════════════════════════════════════════════

RANGOS = {"mes": "Este mes", "pasado": "Mes pasado", "tres": "Últimos 3 meses", "todo": "Todo"}


def rango(clave: str, hoy: date) -> tuple[datetime, datetime]:
    """`_rangoActual` del reporte."""
    ini_mes = datetime(hoy.year, hoy.month, 1)
    fin_mes = _sumar_meses(ini_mes, 1) - timedelta(seconds=1)
    if clave == "pasado":
        return _sumar_meses(ini_mes, -1), ini_mes - timedelta(seconds=1)
    if clave == "tres":
        return _sumar_meses(ini_mes, -2), fin_mes
    if clave == "todo":
        return datetime(2020, 1, 1), datetime(hoy.year + 5, 1, 1)
    return ini_mes, fin_mes


def _ref(c: dict) -> datetime | None:
    """Fecha de referencia: cuándo se cobró si está pagada; si no, su vencimiento."""
    return (_dt(c.get("fechaPago")) or _dt(c.get("vencimiento"))) if c.get("pagada") else _dt(c.get("vencimiento"))


def _programa_de(m: dict, planes: list[dict]) -> str:
    """Programa del alumno según la última cuota (el concepto empieza con el plan)."""
    for c in sorted(_cuotas(m), key=lambda c: str(c.get("vencimiento") or ""), reverse=True):
        con = str(c.get("concepto") or "")
        for p in planes:
            nom = str(p.get("nombre") or "")
            if nom and (con.startswith(nom) or nom in con):
                return str(p.get("programa") or "") or nom
    return "Sin plan"


def reporte(a: dict, mats: list[dict], clave: str, sede: str, hoy: date) -> dict:
    ini, fin = rango(clave, hoy)
    sedes = [s for s in (a.get("sedes") or []) if isinstance(s, dict)]
    primera = sedes[0].get("id") if sedes else ""
    sede_de = {m.get("id"): (m.get("sedeId") or primera or "") for m in mats}
    nombres = {m.get("id"): m.get("nombre") or "" for m in mats}
    todas = [c for m in mats for c in _cuotas(m)]
    pagadas = sorted([c for c in todas if c.get("pagada") and _ref(c)], key=lambda c: _ref(c))
    boletas = {c.get("id"): i + 1 for i, c in enumerate(pagadas)}
    en_rango = [c for c in todas if _ref(c) and ini.date() <= _ref(c).date() and _ref(c) <= fin]
    vis = en_rango if (len(sedes) < 2 or not sede) else [c for c in en_rango if sede_de.get(c.get("alumnoId")) == sede]
    cobrado = sum(_num(c.get("monto")) for c in vis if c.get("pagada"))
    por_cobrar = sum(_num(c.get("monto")) for c in vis if not c.get("pagada"))
    vencido = sum(_num(c.get("monto")) for c in vis if _vencida(c, hoy))
    # Barras: cobrado por mes, últimos 6 (todas las sedes o la filtrada).
    meses = []
    base = datetime(hoy.year, hoy.month, 1)
    for i in range(5, -1, -1):
        m0 = _sumar_meses(base, -i)
        tot = sum(_num(c.get("monto")) for c in todas if c.get("pagada") and _ref(c)
                  and (_ref(c).year, _ref(c).month) == (m0.year, m0.month)
                  and (len(sedes) < 2 or not sede or sede_de.get(c.get("alumnoId")) == sede))
        meses.append({"mes": MESES_CORTOS[m0.month - 1], "total": tot})
    # Morosidad (hoy, sin filtro de período): quién debe y cuánto.
    morosos = []
    for m in mats:
        d, v = _deuda(m, hoy)
        if d > 0 and (len(sedes) < 2 or not sede or sede_de.get(m.get("id")) == sede):
            dias = max(((hoy - _dt(c.get("vencimiento")).date()).days for c in _cuotas(m) if _vencida(c, hoy)), default=0)
            morosos.append({"nombre": m.get("nombre") or "", "deuda": d, "vencido": v, "dias": dias})
    morosos.sort(key=lambda x: -x["deuda"])
    planes = [p for p in (a.get("planes") or []) if isinstance(p, dict)]
    por_prog: dict[str, int] = {}
    for m in mats:
        if len(sedes) < 2 or not sede or sede_de.get(m.get("id")) == sede:
            k = _programa_de(m, planes)
            por_prog[k] = por_prog.get(k, 0) + 1
    por_sede = []
    if len(sedes) > 1:
        for s in sedes:
            por_sede.append({"id": s.get("id"), "nombre": s.get("nombre") or "",
                             "cobrado": sum(_num(c.get("monto")) for c in en_rango if c.get("pagada") and sede_de.get(c.get("alumnoId")) == s.get("id")),
                             "alumnos": sum(1 for m in mats if sede_de.get(m.get("id")) == s.get("id"))})
    movs = sorted(vis, key=lambda c: _ref(c), reverse=True)
    return {"ini": ini, "fin": fin, "cobrado": cobrado, "por_cobrar": por_cobrar, "vencido": vencido, "meses": meses,
            "morosos": morosos, "por_programa": sorted(por_prog.items(), key=lambda kv: -kv[1]), "por_sede": por_sede,
            "movs": movs, "boletas": boletas, "nombres": nombres, "alumnos": len(mats)}


def _comision_digital(a: dict, ini: datetime, fin: datetime) -> tuple[float, dict]:
    try:
        from pagos.router import _comision_matricula_pct, get_matricula_resumen
        pct = float(_comision_matricula_pct(_pais(a).lower()))
        res = get_matricula_resumen(a["id"], desde=ini.isoformat(), hasta=fin.isoformat())
        return pct, res
    except Exception:  # noqa: BLE001
        return 0.0, {}


@router.get("/anfitrion/academia/reportes", response_class=HTMLResponse)
def pagina_reportes(request: Request, academia: str = "", rango_sel: str = "mes", sede: str = "") -> HTMLResponse:
    ses, acads, a, resp = _contexto(request, "/anfitrion/academia/reportes", academia)
    if resp is not None:
        return resp
    rango_sel = rango_sel if rango_sel in RANGOS else "mes"
    sim = _sim(a)
    hoy = _ahora(a).date()
    mats = matriculas_de(a["id"])
    r = reporte(a, mats, rango_sel, sede, hoy)
    q = f"academia={up.quote(a['id'])}"
    chips = "<div class='chips aco-noimp' style='margin-top:12px'>" + "".join(
        f"<a class='chip{' sel' if k == rango_sel else ''}' href='?{q}&rango_sel={k}&sede={e(up.quote(sede))}'>{t}</a>" for k, t in RANGOS.items()) + "</div>"
    if r["por_sede"]:
        chips += "<div class='chips aco-noimp' style='margin-top:10px'>" + f"<a class='chip{'' if sede else ' sel'}' href='?{q}&rango_sel={rango_sel}'>Todas las sedes</a>" + "".join(
            f"<a class='chip{' sel' if s['id'] == sede else ''}' href='?{q}&rango_sel={rango_sel}&sede={e(up.quote(str(s['id'])))}'>📍 {e(s['nombre'])}</a>" for s in r["por_sede"]) + "</div>"
    mx = max([x["total"] for x in r["meses"]] + [1])
    barras = "".join(f"<div><b>{('' if not x['total'] else e(sim) + ' ' + format(x['total'], '.0f'))}</b><i style='height:{max(3, x['total'] / mx * 110):.0f}px;{'opacity:.25' if not x['total'] else ''}'></i><small>{x['mes']}</small></div>"
                     for x in r["meses"])
    moros = "".join(f"<div class='aco-cuota'><div class='t'><b>{e(x['nombre'])}</b><div class='aco-n'>{'vencido hace ' + str(x['dias']) + ' días' if x['vencido'] else 'por vencer'}</div></div>"
                    f"<b style='color:{'var(--bad-fg)' if x['vencido'] else 'var(--noche)'}'>{e(sim)} {x['deuda']:.2f}</b></div>" for x in r["morosos"][:30])
    progs = "".join(f"<div class='aco-cuota'><span>{e(k)}</span><b>{v} alumno{'s' if v != 1 else ''}</b></div>" for k, v in r["por_programa"])
    sedes_html = "".join(f"<div class='aco-cuota'><span>📍 {e(s['nombre'])} · {s['alumnos']} alumno{'s' if s['alumnos'] != 1 else ''}</span><b>{e(sim)} {s['cobrado']:.2f}</b></div>" for s in r["por_sede"])
    pct, res = _comision_digital(a, r["ini"], r["fin"])
    bruto, com, neto = _num(res.get("bruto_soles")), _num(res.get("comision_soles")), _num(res.get("neto_soles"))
    pct_ef = (com / bruto * 100) if bruto > 0 else pct
    comision = (f"<div class='aco-card'><b>💳 Cobro digital · es como tu POS</b><div class='aco-n'>Lo que tus alumnos pagan en línea lleva {pct_ef:.1f}% de comisión; el efectivo 0%.</div>"
                f"<div class='aco-cuota'><span>{int(_num(res.get('cobros')))} cobros en línea</span><b>{e(sim)} {bruto:.2f}</b></div>"
                f"<div class='aco-cuota'><span>Comisión Pichangol</span><b>− {e(sim)} {com:.2f}</b></div>"
                f"<div class='aco-cuota'><span><b>Neto para tu academia</b></span><b>{e(sim)} {neto:.2f}</b></div></div>")
    ret = _num(a.get("retribucionClubPct"))
    club = ""
    if ret > 0:
        al_club = r["cobrado"] * ret / 100
        club = (f"<div class='aco-card'><b>🤝 Liquidación al club · {ret:g}%</b>"
                f"<div class='aco-cuota'><span>Cobrado en el período</span><b>{e(sim)} {r['cobrado']:.2f}</b></div>"
                f"<div class='aco-cuota'><span>Para el club</span><b>{e(sim)} {al_club:.2f}</b></div>"
                f"<div class='aco-cuota'><span><b>Para la academia</b></span><b>{e(sim)} {r['cobrado'] - al_club:.2f}</b></div></div>")
    def _estado_mov(c: dict) -> str:
        if c.get("pagada"):
            return f"<span class='pill ok'>Pagada · B-{str(r['boletas'].get(c.get('id'), 0)).zfill(4)}</span>"
        return "<span class='pill bad'>Vencida</span>" if _vencida(c, hoy) else "<span class='pill warn'>Por cobrar</span>"

    movs = "".join(
        f"<tr><td>{_f(_ref(c))}</td><td>{e(r['nombres'].get(c.get('alumnoId'), ''))}</td><td>{e(c.get('concepto'))}</td><td>{e(sim)} {_num(c.get('monto')):.2f}</td>"
        f"<td>{_estado_mov(c)}</td></tr>"
        for c in r["movs"][:400])
    cuerpo = (chips + f"<p class='aco-n' style='margin-top:10px'>{_f(r['ini'])} – {_f(r['fin'] if rango_sel != 'todo' else hoy)}</p>"
              "<div class='kpis' style='margin-top:10px'>"
              f"<div class='kpi'><small>Cobrado</small><b>{e(sim)} {r['cobrado']:.2f}</b></div>"
              f"<div class='kpi'><small>Por cobrar</small><b>{e(sim)} {r['por_cobrar']:.2f}</b></div>"
              f"<div class='kpi'><small>Vencido</small><b style='color:var(--bad-fg)'>{e(sim)} {r['vencido']:.2f}</b></div>"
              f"<div class='kpi'><small>Alumnos</small><b>{r['alumnos']}</b></div></div>"
              f"<div class='aco-grid'><div class='aco-card'><b>Ingresos cobrados · últimos 6 meses</b><div class='aco-bar'>{barras}</div></div>"
              f"<div class='aco-card'><b>Morosidad hoy ({len(r['morosos'])})</b>{moros or '<p class=aco-n>Nadie debe. 🎉</p>'}</div>"
              f"<div class='aco-card'><b>Alumnos por programa</b>{progs or '<p class=aco-n>Sin alumnos.</p>'}</div>"
              + (f"<div class='aco-card'><b>Cobrado y alumnos por sede</b>{sedes_html}</div>" if sedes_html else "")
              + comision + club + "</div>"
              f"<div style='display:flex;justify-content:space-between;align-items:center;gap:10px;margin-top:18px;flex-wrap:wrap'><b>Movimientos ({len(r['movs'])})</b>"
              "<button class='btn sec aco-noimp' onclick='window.print()'>🖨️ Imprimir / guardar PDF</button></div>"
              + (f"<div class='tabla' style='margin-top:10px'><table><thead><tr><th>Fecha</th><th>Alumno</th><th>Concepto</th><th>Monto</th><th>Estado</th></tr></thead><tbody>{movs}</tbody></table></div>"
                 if movs else "<div class='anf-vacio' style='margin-top:10px'>Sin movimientos en este rango.</div>"))
    return _pagina(ses, acads, a, "reportes", "Reportes", "Ingresos, morosidad y alumnos.", cuerpo)


# ══ CHATS ═════════════════════════════════════════════════════════════════════

_NUEVO = "<span class='pill warn'>Nuevo</span>"


def _cuentas_alumnos(mats: list[dict]) -> dict[str, list[str]]:
    """Correo de cada cuenta de alumno-app → nombres de sus alumnos (un hilo por cuenta)."""
    out: dict[str, list[str]] = {}
    for m in mats:
        em = str(m.get("email") or "").strip().lower()
        if em:
            out.setdefault(em, []).append(str(m.get("nombre") or ""))
    return out


def url_chat(aid: str, cuenta: str) -> str:
    """Conversación de la academia en la mensajería web (`/mensajes/{clave}`;
    la clave es opaca: los correos nunca viajan en claro)."""
    try:
        from web.jugador_mensajes import clave_de
        return "/mensajes/" + up.quote(clave_de([f"{aid}|{cuenta.strip().lower()}"]), safe="")
    except Exception:  # noqa: BLE001
        return "/mensajes"


def ref_cuenta(email: str) -> str:
    """Referencia OPACA de la cuenta del alumno para el navegador (el correo no
    viaja en claro): HMAC corto, validado contra las cuentas de la academia."""
    import hashlib
    import hmac
    return hmac.new(sesion._secreto() + b"|academia-chat", email.strip().lower().encode(), hashlib.sha256).hexdigest()[:24]


@router.get("/anfitrion/academia/chats", response_class=HTMLResponse)
def pagina_chats(request: Request, academia: str = "") -> HTMLResponse:
    ses, acads, a, resp = _contexto(request, "/anfitrion/academia/chats", academia)
    if resp is not None:
        return resp
    mats = matriculas_de(a["id"])
    cuentas = _cuentas_alumnos(mats)
    por_hilo: dict[str, list[dict]] = {}
    for x in mensajes_de_academia(a["id"]):
        por_hilo.setdefault(x["cuenta"] or x["hilo"].split("|", 1)[-1], []).append(x)
    for em in por_hilo:
        cuentas.setdefault(em, [])
    filas = []
    for em, noms in cuentas.items():
        h = por_hilo.get(em, [])
        ult = h[-1] if h else None
        ts = ult["creado"].timestamp() if ult and hasattr(ult["creado"], "timestamp") else 0
        filas.append((ts, em, noms, ult))
    filas.sort(key=lambda t: t[0], reverse=True)
    lista = ""
    for _t, em, noms, ult in filas:
        titulo = ", ".join(n for n in noms if n) or "Alumno"
        ini = e(titulo[:1].upper())
        if ult:
            prev = ("Tú: " if ult["esProfe"] else "") + (ult["texto"] or "📎 Adjunto")
            lista += (f"<a class='aco-card aco-fila' style='text-decoration:none;color:inherit' href='{e(url_chat(a['id'], em))}'>"
                      f"<div class='aco-av'>{ini}</div><div style='flex:1'><b>{e(titulo)}</b>"
                      f"<div class='aco-n' style='white-space:nowrap;overflow:hidden;text-overflow:ellipsis'>{e(prev)}</div></div>"
                      f"{_NUEVO if not ult['esProfe'] else ''}</a>")
        else:
            lista += (f"<div class='aco-card aco-fila'><div class='aco-av'>{ini}</div><div style='flex:1'><b>{e(titulo)}</b>"
                      f"<div class='aco-n'>Sin mensajes todavía</div></div>"
                      f"<button class='btn sec aco-mini' data-escribir='{e(ref_cuenta(em))}' data-nombre='{e(titulo)}'>✉️ Escribir</button></div>")
    cuerpo = ((f"<div style='display:grid;gap:10px;margin-top:14px'>{lista}</div>" if lista else
               "<div class='anf-vacio' style='margin-top:18px'>Aún no hay alumnos con la app en esta academia. Cuando se matriculen con su cuenta, aquí aparece su chat.</div>")
              + "<p class='aco-n' style='margin-top:14px'>Las conversaciones se abren en <a href='/mensajes'>Mensajes</a>, igual que en la app.</p>")
    return _pagina(ses, acads, a, "chats", "Chats", "Un chat por cada cuenta de alumno.", cuerpo, _JS_CHAT)


_JS_CHAT = r"""
document.addEventListener('click',async function(ev){var b=ev.target.closest('[data-escribir]');if(!b)return;
 var h="<div class='aco-dlg'><p style='margin:0'>Para <b>"+acoEsc(b.dataset.nombre)+"</b></p><label>Mensaje</label><input id='acoTxt' maxlength='2000' autocomplete='off' placeholder='Escribe tu mensaje'></div>";
 if(!await pcgConfirmar({titulo:'Nuevo mensaje',html:h,confirmar:'Enviar',icono:'💬'}))return;var v=(document.getElementById('acoTxt').value||'').trim();if(!v)return;
 var j=await acoPost('/anfitrion/academia/chats/enviar',{academia_id:ACO.aid,cuenta:b.dataset.escribir,texto:v},'Enviando…');if(j.ok)pcgIr(j.url||'/mensajes','Abriendo el chat…');else acoErr(j)});
"""


@router.post("/anfitrion/academia/chats/enviar")
def enviar_chat(request: Request, body: dict = Body(default_factory=dict)) -> JSONResponse:
    """Primer mensaje del profe a una cuenta de alumno de SU academia (fila
    `Mensaje.toInsert` de academia); la conversación sigue en /mensajes."""
    ses, err = _ses_json(request)
    if err:
        return err
    aid = str(body.get("academia_id") or "")
    a = _mia(ses, aid)
    if not a:
        return _no_encontrada()
    ref = str(body.get("cuenta") or "")
    texto = str(body.get("texto") or "").strip()[:2000]
    cuenta = next((em for em in _cuentas_alumnos(matriculas_de(aid)) if ref_cuenta(em) == ref), "")
    if not texto or not cuenta:
        return JSONResponse({"ok": False, "error": "datos", "mensaje": "Escribe un mensaje para un alumno de tu academia."}, status_code=400)
    if not enviar_mensaje(aid, cuenta, ses["email"], ses.get("nombre") or "", texto):
        return JSONResponse({"ok": False, "error": "no_enviado", "mensaje": "No se pudo enviar. Inténtalo otra vez."}, status_code=500)
    return JSONResponse({"ok": True, "url": url_chat(aid, cuenta)})


# ══ SEDES, HORARIOS Y PRECIOS POR SEDE ════════════════════════════════════════

def _programas(a: dict) -> list[str]:
    """`_programasDistintos`: programas del tarifario ('General' = sin programa)."""
    out: list[str] = []
    for p in a.get("planes") or []:
        if isinstance(p, dict):
            g = str(p.get("programa") or "") or "General"
            if g not in out:
                out.append(g)
    return out


@router.get("/anfitrion/academia/sedes", response_class=HTMLResponse)
def pagina_sedes(request: Request, academia: str = "") -> HTMLResponse:
    ses, acads, a, resp = _contexto(request, "/anfitrion/academia/sedes", academia)
    if resp is not None:
        return resp
    planes = [{"id": p.get("id"), "nombre": p.get("nombre"), "precio": _num(p.get("precioMes"))} for p in (a.get("planes") or []) if isinstance(p, dict)]
    cfg = {"sedes": [s for s in (a.get("sedes") or []) if isinstance(s, dict)], "horarios": a.get("horarios") or {},
           "precios": a.get("preciosSede") or {}, "programas": _programas(a), "planes": planes,
           "centro": [a.get("lat") or -12.0464, a.get("lng") or -77.0428]}
    cuerpo = ("<div class='aco-card' style='margin-top:14px'><b>¿Entrenas en varios lugares?</b><div class='aco-n'>Agrega tus sedes. Cada programa puede tener su horario "
              "en cada sede y cada plan su precio en esa sede (vacío = precio base del plan). Tus alumnos lo ven al matricularse.</div></div>"
              "<div id='acoSedes'></div>"
              "<div class='acciones aco-noimp' style='margin-top:14px'><button class='btn sec' id='acoSedeMas'>＋ Agregar sede</button>"
              "<button class='btn' id='acoSedesGuardar'>Guardar cambios</button></div>")
    lf = ("<link rel='stylesheet' href='https://unpkg.com/leaflet@1.9.4/dist/leaflet.css' crossorigin=''>"
          "<script src='https://unpkg.com/leaflet@1.9.4/dist/leaflet.js' crossorigin=''></script>")
    js = "Object.assign(window.ACO," + json.dumps(cfg, ensure_ascii=False).replace("</", "<\\/") + ");" + _JS_SEDES
    return _pagina(ses, acads, a, "sedes", "Sedes y horarios", "Sedes, horario por programa y precio por sede.", cuerpo, js, extra_head=lf)


_JS_SEDES = r"""
var S=ACO.sedes.map(function(s){return {id:s.id,nombre:s.nombre||'',direccion:s.direccion||'',lat:s.lat,lng:s.lng}});
function pintar(){var box=document.getElementById('acoSedes');var h='';
 if(!S.length)h="<div class='anf-vacio' style='margin-top:12px'>Aún no agregas sedes: tu academia usa su sede principal.</div>";
 S.forEach(function(s,i){h+="<div class='aco-sede' data-i='"+i+"'><div style='display:flex;justify-content:space-between;gap:8px;align-items:center'><b>📍 Sede "+(i+1)+"</b><button class='btn sec aco-mini' data-quitar='"+i+"'>Quitar</button></div>"+
  "<div class='aco-dos' style='margin-top:8px'><div><label class='aco-n'>Nombre del local</label><input data-k='nombre' maxlength='80' value='"+acoEsc(s.nombre)+"' placeholder='Ej. Club Las Palmas'></div>"+
  "<div><label class='aco-n'>Dirección <span>(opcional)</span></label><input data-k='direccion' maxlength='120' value='"+acoEsc(s.direccion)+"' placeholder='Calle y número'></div></div>"+
  "<div class='aco-n' style='margin-top:8px'>Toca el mapa para ubicarla "+(s.lat?'· ✓ ubicada':'(opcional)')+"</div><div class='mapa' id='mapa"+i+"'></div>";
  h+="<div style='margin-top:12px'><b style='font-size:14px'>Horario por programa</b>";
  if(!ACO.programas.length)h+="<div class='aco-n'>Agrega programas en tu tarifario para fijar horarios por sede.</div>";
  ACO.programas.forEach(function(p){var k=s.id+'|'+p;h+="<label class='aco-n' style='display:block;margin-top:6px'>"+acoEsc(p)+"</label><input data-h='"+acoEsc(k)+"' maxlength='80' value='"+acoEsc(ACO.horarios[k]||'')+"' placeholder='Ej. Lun-Mié-Vie 4-6pm'>"});
  h+="</div>";
  if(ACO.planes.length){h+="<div style='margin-top:12px'><b style='font-size:14px'>Precios en esta sede</b> <span class='aco-n'>(opcional · vacío = precio base)</span><div class='aco-dos' style='margin-top:6px'>";
   ACO.planes.forEach(function(p){var k=s.id+'|'+p.id,v=ACO.precios[k];h+="<div><label class='aco-n'>"+acoEsc(p.nombre)+"</label><input type='number' min='0' step='0.5' inputmode='decimal' data-p='"+acoEsc(k)+"' value='"+(v>0?(+v).toFixed(2):'')+"' placeholder='Base: "+ACO.sim+' '+p.precio.toFixed(2)+"'></div>"});h+="</div></div>"}
  h+="</div>"});
 box.innerHTML=h;
 if(window.L)S.forEach(function(s,i){var c=s.lat?[s.lat,s.lng]:ACO.centro;var m=L.map('mapa'+i,{scrollWheelZoom:false}).setView(c,s.lat?16:12);L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'© OpenStreetMap'}).addTo(m);
  var mk=s.lat?L.marker(c).addTo(m):null;m.on('click',function(ev){s.lat=+ev.latlng.lat.toFixed(6);s.lng=+ev.latlng.lng.toFixed(6);if(mk)mk.setLatLng(ev.latlng);else mk=L.marker(ev.latlng).addTo(m)})})}
function leer(){document.querySelectorAll('.aco-sede').forEach(function(el){var s=S[+el.dataset.i];el.querySelectorAll('[data-k]').forEach(function(i){s[i.dataset.k]=i.value.trim()})});
 document.querySelectorAll('[data-h]').forEach(function(i){ACO.horarios[i.dataset.h]=i.value.trim()});document.querySelectorAll('[data-p]').forEach(function(i){ACO.precios[i.dataset.p]=parseFloat(i.value)||0})}
document.getElementById('acoSedeMas').addEventListener('click',function(){leer();S.push({id:'sede_'+Date.now()+'000',nombre:'',direccion:''});pintar()});
document.addEventListener('click',async function(ev){var q=ev.target.closest('[data-quitar]');if(!q)return;leer();
 if(!await pcgConfirmar({titulo:'Quitar sede',mensaje:'Se quitan también sus horarios y precios. Los alumnos que entrenaban ahí pasan a la sede principal.',confirmar:'Quitar',destructivo:true}))return;S.splice(+q.dataset.quitar,1);pintar()});
document.getElementById('acoSedesGuardar').addEventListener('click',async function(){leer();
 var j=await acoPost('/anfitrion/academia/sedes/guardar',{academia_id:ACO.aid,sedes:S,horarios:ACO.horarios,precios:ACO.precios});if(j.ok)pcgRecargar('✅ Sedes guardadas');else acoErr(j)});
pintar();
"""


def validar_sedes(body: dict, a: dict) -> tuple[dict | None, str]:
    """Normaliza como `crear_academia_screen._guardar`: sedes con nombre, horarios
    solo de sedes vigentes y con texto, precios > 0 de (sede vigente, plan vigente)."""
    sedes, vistos = [], set()
    for s in (body.get("sedes") or [])[:20]:
        if not isinstance(s, dict):
            continue
        sid = str(s.get("id") or "").strip()[:60]
        nombre = str(s.get("nombre") or "").strip()[:80]
        if not re.match(r"^[A-Za-z0-9_\-]{1,60}$", sid) or sid in vistos:
            return None, "Sede inválida. Recarga la página."
        if not nombre:
            return None, "Ponle nombre a cada sede."
        vistos.add(sid)
        sede = {"id": sid, "nombre": nombre, "direccion": str(s.get("direccion") or "").strip()[:120]}
        try:
            lat, lng = float(s.get("lat")), float(s.get("lng"))
            if -90 <= lat <= 90 and -180 <= lng <= 180:
                sede.update(lat=lat, lng=lng)
        except (TypeError, ValueError):
            pass
        sedes.append(sede)
    horarios = {}
    for k, v in (body.get("horarios") or {}).items():
        v = str(v or "").strip()[:80]
        if v and str(k).split("|", 1)[0] in vistos:
            horarios[str(k)[:200]] = v
    plan_ids = {str(p.get("id")) for p in (a.get("planes") or []) if isinstance(p, dict)}
    precios = {}
    for k, v in (body.get("precios") or {}).items():
        k = str(k)
        i = k.find("|")
        if i < 0 or k[:i] not in vistos or k[i + 1:] not in plan_ids:
            continue
        n = round(_num(v), 2)
        if 0 < n <= 100000:
            precios[k] = n
    return {"sedes": sedes, "horarios": horarios, "preciosSede": precios}, ""


@router.post("/anfitrion/academia/sedes/guardar")
def guardar_sedes(request: Request, body: dict = Body(default_factory=dict)) -> JSONResponse:
    ses, err = _ses_json(request)
    if err:
        return err
    aid = str(body.get("academia_id") or "")
    a = _mia(ses, aid)
    if not a:
        return _no_encontrada()
    campos, msj = validar_sedes(body, a)
    if campos is None:
        return JSONResponse({"ok": False, "error": "datos", "mensaje": msj}, status_code=400)

    def aplicar(data: dict):
        data.update(campos)
        return True

    if not mutar_academia(aid, ses["email"], aplicar):
        return JSONResponse({"ok": False, "error": "no_guardado", "mensaje": "No se pudo guardar. Inténtalo otra vez."}, status_code=500)
    return JSONResponse({"ok": True, "sedes": len(campos["sedes"])})
