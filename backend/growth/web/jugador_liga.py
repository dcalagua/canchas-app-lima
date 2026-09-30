"""NIVEL DE JUGADOR + LIGA DE TENIS PICHANGOL en la web (pedido del director,
29-sep-2026: "en la web implementa las mismas funcionalidades que existen
actualmente en el app").

Espejo de estas pantallas del APK, con los MISMOS datos:

- `GET /mi-nivel` = `nivel_onboarding_screen.dart`: autoevaluación por deporte
  (años jugando 0-10, veces por semana 0-5, ¿compites?) y la MISMA fórmula
  `Nivel.seedDesde`; guarda en `pichangol_niveles` (clave email+deporte,
  formato `Nivel.toRow`). Al reevaluar solo cambia `nivel` y `actualizado`:
  partidos, victorias y confiabilidad que ya existan NO se pisan (el historial
  de resultados no se borra por volver a autoevaluarse).
- `GET /liga` = `circuito_screen.dart` (hero + estado en el circuito) con
  pestañas:
    · Ranking = `ranking_global_screen.dart`: ranking cruzado de TODAS las
      academias + retos jugados + campeonatos independientes (port exacto de
      `AppState.rankingGlobal` / `rankingDobles` / `temporadasConDatos` /
      `categoriasGlobalDe` / `zonasGlobalDe` / `campeonGlobal`), filtros por
      deporte, singles/dobles, zona, temporada y categoría, corona 👑 al campeón
      vigente, PRO, "Tu posición" y "Retar" en cada fila.
    · Mis retos = `mis_retos_screen.dart`: recibidos/enviados con Aceptar /
      Rechazar, Reportar resultado, Confirmar / Disputar (doble confirmación).
    · Retar = `jugadores_disponibles_screen.dart` (+ buscador de
      `buscar_usuario_screen`): unirse/editar/salir del circuito, directorio,
      "De mi nivel" y Retar.
    · Dobles = `reto_dobles_screen.dart`: compañero + dos rivales.
  Todas las acciones van con el correo de la SESIÓN y llaman como funciones a
  `retos/router.py` y `circuito/router.py` (mismas reglas: tope semanal de
  retos sin Pro, 4 jugadores distintos en dobles, quién confirma…). Los pushes
  son los de `AvisosService` (fila en `pichangol_avisos`) y el mensaje directo
  del reto el de `reto_flow.dart` (`pichangol_mensajes`).

El navegador nunca ve correos de otros jugadores: cada jugador listado viaja
como un `ref` cifrado (Fernet con el secreto del backend) que solo el servidor
descifra.
"""

from __future__ import annotations

import base64
import hashlib
import json
import time
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote, urlencode
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Body, Request
from fastapi.responses import HTMLResponse, JSONResponse

import config
from db import pg
from db.store import stores
from web import campeonatos_logica as L
from web import catalogos, sesion, ui
from web.ui import e

router = APIRouter()

PLAY_URL = "https://play.google.com/store/apps/details?id=pe.ebim.pichangol"
_TZ = ZoneInfo("America/Lima")

# Enum `Deporte` del app (orden = índice, así ordena `deportesConRanking`).
DEPORTES: dict[str, tuple[str, str]] = {
    "tenis": ("Tenis", "🎾"), "padel": ("Pádel", "🏸"), "futbol": ("Fútbol", "⚽"),
    "pickleball": ("Pickleball", "🏓"), "voley": ("Vóley", "🏐"), "basquet": ("Básquet", "🏀"),
    "natacion": ("Natación", "🏊"),
}
_ORDEN = list(DEPORTES)
DEPORTES_ACTIVOS = ["futbol", "tenis", "pickleball", "voley", "basquet"]   # `deportesActivos`
DEPORTES_CIRCUITO = ["tenis", "padel", "pickleball"]                        # `deportesCircuito`
CATEGORIAS_LIGA = ["5P", "5A", "5B", "4ta", "3ra", "2da", "1ra"]           # `_UnirseSheet._categorias`
PUNTOS_VICTORIA, PUNTOS_DERROTA = 3, 1                                     # `Academia.puntosVictoria/Derrota`
PAISES = [("PE", "Perú"), ("BO", "Bolivia"), ("EC", "Ecuador")]


def _etq(dep: str) -> str:
    return DEPORTES.get(dep, (dep.capitalize() if dep else "", ""))[0]


def _emo(dep: str) -> str:
    return DEPORTES.get(dep, ("", "🏅"))[1]


# ── Utilidades compartidas con jugador_cuenta.py ─────────────────────────────

def sin_sesion(request: Request, ruta: str, titulo: str, que: str) -> HTMLResponse:
    """Sin sesión: con login activo → a /entrar y volver; si no, "está en la app"."""
    if sesion.activo():
        return HTMLResponse("", status_code=302, headers={"Location": "/entrar?volver=" + quote(ruta, safe="")})
    cuerpo = ("<div class='panel' style='max-width:520px;margin:40px auto;text-align:center'>"
              f"<h1 style='font-size:22px'>{e(titulo)}</h1>"
              f"<p class='sub'>En esta web aún no está activo el inicio de sesión. {e(que)} está en la app.</p>"
              f"<div class='acciones' style='justify-content:center'><a class='btn' href='{PLAY_URL}'>Abrir Pichangol en Google Play</a></div></div>")
    return ui.shell(titulo, cuerpo, sesion=None)


def perfiles(emails) -> dict[str, dict]:
    """`PerfilesRepo.obtenerVarios`: {correo: {nombre, foto_url, celular, bio}}. Fail-safe."""
    es = sorted({(x or "").strip().lower() for x in emails if (x or "").strip()})
    if not pg.habilitado or not es:
        return {}
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT email, nombre, foto_url, celular FROM pichangol_perfiles WHERE lower(email) = ANY(%s)", (es,))
            return {str(f[0]).lower(): {"nombre": str(f[1] or ""), "foto_url": str(f[2] or ""), "celular": str(f[3] or "")}
                    for f in cur.fetchall()}
    except Exception:  # noqa: BLE001
        return {}


def mi_nombre(ses: dict) -> str:
    """Nombre con el que se muestra el usuario (el del perfil de Pichangol, como
    `appState.usuario.nombre`; si no eligió uno, el de Google)."""
    email = (ses.get("email") or "").lower()
    p = perfiles([email]).get(email) or {}
    return (p.get("nombre") or ses.get("nombre") or email.split("@")[0]).strip()


def avatar(nombre: str, foto: str, clase: str = "lg-av") -> str:
    """Foto real del jugador; inicial de color si no hay (regla del app)."""
    if foto:
        return f"<img class='{clase}' src='{e(foto)}' alt='' loading='lazy' referrerpolicy='no-referrer'>"
    return f"<span class='{clase} ini'>{e((nombre.strip() or '?')[:1].upper())}</span>"


def aviso_push(email: str, titulo: str, cuerpo: str, tipo: str = "aviso", data: dict | None = None) -> None:
    """`AvisosService.enviar`: fila en `pichangol_avisos` (el webhook dispara el
    push). Best-effort: nunca rompe la acción."""
    em = (email or "").strip().lower()
    if not em:
        return
    if pg.habilitado:
        try:
            with pg.conexion() as conn, conn.cursor() as cur:
                if data:
                    cur.execute("INSERT INTO pichangol_avisos (email, titulo, cuerpo, tipo, data, creado) "
                                "VALUES (%s, %s, %s, %s, %s::jsonb, now())", (em, titulo, cuerpo, tipo, json.dumps(data)))
                else:
                    cur.execute("INSERT INTO pichangol_avisos (email, titulo, cuerpo, tipo, creado) VALUES (%s, %s, %s, %s, now())",
                                (em, titulo, cuerpo, tipo))
                conn.commit()
                return
        except Exception:  # noqa: BLE001
            pass
    try:
        from pagos.router import _aviso_push_usuario
        _aviso_push_usuario(em, titulo, cuerpo, tipo)
    except Exception:  # noqa: BLE001
        pass


@lru_cache(maxsize=4)
def _hojas_geo(iso: str) -> frozenset:
    f = Path(__file__).parent / "geo" / f"{iso.lower()}_geo.json"
    try:
        arbol = json.loads(f.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return frozenset()
    return frozenset(h for n1 in arbol.values() for hojas in n1.values() for h in hojas)


def zona_valida(zona: str) -> bool:
    """La zona es una hoja del árbol político-administrativo (`SelectorUbicacion`)."""
    return any(zona in _hojas_geo(iso) for iso, _ in PAISES)


def pais_de_zona(zona: str) -> str:
    for iso, _ in PAISES:
        if zona and zona in _hojas_geo(iso):
            return iso
    return "PE"


def _fernet():
    from cryptography.fernet import Fernet
    k = hashlib.sha256(sesion._secreto() + b"|pcg-jugador-ref").digest()
    return Fernet(base64.urlsafe_b64encode(k))


def ref_de(email: str) -> str:
    """Identificador OPACO de un jugador para el navegador (no expone su correo)."""
    return _fernet().encrypt((email or "").strip().lower().encode()).decode()


def email_de_ref(ref: str) -> str:
    try:
        v = _fernet().decrypt((ref or "").encode(), ttl=7 * 24 * 3600).decode()
    except Exception:  # noqa: BLE001
        return ""
    return v if "@" in v else ""


def _ocultar_correo(email: str) -> str:
    u, _, d = (email or "").partition("@")
    return (u[:2] + "•••@" + d) if d else ""


_CSS_BASE = """
.lg-av{width:40px;height:40px;border-radius:50%;object-fit:cover;flex:none;display:inline-flex;align-items:center;justify-content:center;background:#0E8F67;color:#fff;font-weight:800;font-size:16px}
.lg-wrap{max-width:760px;margin:10px auto 60px}
.lg-wrap h1{font-size:28px;margin:4px 0 6px;letter-spacing:-.3px}
.lg-card{background:#fff;border-radius:18px;box-shadow:0 6px 20px rgba(0,0,0,.07);padding:16px;margin:0 0 12px;min-width:0}
.lg-chips{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0}
.lg-chips .chip,.lg-fil .chip{max-width:100%;white-space:normal}
.lg-sec{font-weight:800;font-size:16px;margin:18px 0 8px}
.lg-vacio{text-align:center;color:#6a6a6a;padding:28px 12px}
.lg-vacio .em{font-size:52px;display:block;margin-bottom:8px}
.pcg-dlg .caja .lg-opc{display:flex;align-items:center;gap:12px;width:100%;border:1px solid #E4E4E4;background:#fff;border-radius:12px;padding:8px 10px;margin:0 0 8px;font:inherit;cursor:pointer;text-align:left}
.pcg-dlg .caja .lg-opc.sel{border:1.5px solid #0B8A3E;background:#EAF7EF}
.pcg-dlg .caja .lg-opc b{flex:1;min-width:0;overflow-wrap:anywhere}
.lg-sets{display:grid;grid-template-columns:minmax(0,1fr) 72px 72px;gap:6px;align-items:center;margin-top:6px;font-size:13.5px}
.lg-sets select{padding:8px;border-radius:10px;border:1px solid #E4E4E4;font:inherit;width:100%}
"""


# ═════════════════════════════════ NIVEL ══════════════════════════════════════

def seed_desde(anios: int, frecuencia: int, compite: bool) -> float:
    """`Nivel.seedDesde` (misma fórmula del app)."""
    n = 2.0 + max(0, min(10, anios)) * 0.25 + max(0, min(5, frecuencia)) * 0.2 + (1.0 if compite else 0.0)
    return max(1.0, min(7.0, n))


def niveles_completos(email: str) -> list[dict]:
    """`NivelesRepo.deJugador` (todas las columnas de `Nivel.fromRow`)."""
    em = (email or "").strip().lower()
    if not pg.habilitado or not em:
        return []
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT deporte, nivel, partidos, victorias, confiabilidad FROM pichangol_niveles "
                        "WHERE lower(email) = %s", (em,))
            out = [{"deporte": str(f[0] or ""), "nivel": float(f[1] if f[1] is not None else 3.0),
                    "partidos": int(f[2] or 0), "victorias": int(f[3] or 0),
                    "confiabilidad": float(f[4] if f[4] is not None else 1.0)} for f in cur.fetchall()]
    except Exception:  # noqa: BLE001
        return []
    out.sort(key=lambda n: _ORDEN.index(n["deporte"]) if n["deporte"] in _ORDEN else 99)
    return out


def niveles_de_varios(emails) -> dict[str, float]:
    """`NivelesRepo.deVarios`: {"correo|deporte": nivel}."""
    es = sorted({(x or "").strip().lower() for x in emails if (x or "").strip()})
    if not pg.habilitado or not es:
        return {}
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT lower(email), deporte, nivel FROM pichangol_niveles WHERE lower(email) = ANY(%s)", (es,))
            return {f"{f[0]}|{f[1]}": float(f[2] if f[2] is not None else 3.0) for f in cur.fetchall()}
    except Exception:  # noqa: BLE001
        return {}


def guardar_nivel(email: str, deporte: str, nivel: float) -> bool:
    """UPSERT por (email, deporte) como `NivelesRepo.guardar`. Fila nueva =
    `Nivel(...)` con partidos 0, victorias 0, confiabilidad 1.0; si ya existe,
    solo se actualizan nivel y fecha (no se borra el historial de resultados)."""
    em = (email or "").strip().lower()
    if not pg.habilitado or not em or not deporte:
        return False
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO pichangol_niveles (email, deporte, nivel, partidos, victorias, confiabilidad, actualizado) "
                        "VALUES (%s, %s, %s, 0, 0, 1.0, now()) ON CONFLICT (email, deporte) DO UPDATE "
                        "SET nivel = EXCLUDED.nivel, actualizado = now()", (em, deporte, round(float(nivel), 4)))
            conn.commit()
            return True
    except Exception:  # noqa: BLE001
        return False


def chip_nivel(deporte: str, nivel: float, compacto: bool = False) -> str:
    """`NivelChip`: "🎾 Tenis · 4.3" (compacto: "🎾 4.3")."""
    txt = f"{_emo(deporte)} {'' if compacto else e(_etq(deporte)) + ' · '}<b>{nivel:.1f}</b>"
    return f"<span class='lg-niv{' c' if compacto else ''}'>{txt}</span>"


_CSS_NIVEL = """
.lg-niv{display:inline-flex;align-items:center;gap:4px;background:#fff;border:1px solid #E4E4E4;border-radius:99px;padding:7px 12px;box-shadow:0 2px 6px rgba(0,0,0,.06);font-size:14px;font-weight:600;white-space:nowrap}
.lg-niv b{color:#067A38;font-weight:900}
.lg-niv.c{padding:3px 9px;font-size:12.5px}
.nv-q{margin:18px 0 4px}
.nv-q .t{display:flex;justify-content:space-between;gap:10px;font-weight:700}
.nv-q .t span{color:#0E8F67;font-weight:800;white-space:nowrap}
.nv-q input[type=range]{width:100%;accent-color:#0B8A3E;margin-top:8px}
.nv-sw{display:flex;align-items:center;justify-content:space-between;gap:12px;margin:18px 0 6px;font-weight:700}
.nv-sw input{width:auto;flex:none;transform:scale(1.4);accent-color:#0B8A3E}
.nv-res{text-align:center;padding:26px 10px}
.nv-res .em{font-size:56px;display:block}
.nv-res .lg-niv{font-size:18px;padding:10px 18px;margin:14px 0}
.nv-tabla{display:grid;gap:8px}
.nv-fila{display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap;border-bottom:1px solid #EBEBEB;padding:8px 0}
.nv-fila:last-child{border:0}
.nv-fila small{color:#6a6a6a}
"""


@router.get("/mi-nivel", response_class=HTMLResponse)
def pagina_mi_nivel(request: Request, deporte: str = "") -> HTMLResponse:
    ses = sesion.de_request(request)
    if not ses:
        return sin_sesion(request, "/mi-nivel", "Tu nivel de jugador", "Tu nivel de jugador")
    email = ses["email"].lower()
    niveles = niveles_completos(email)
    dep0 = deporte if deporte in DEPORTES_ACTIVOS else "futbol"
    mis = ""
    if niveles:
        filas = "".join(
            f"<div class='nv-fila'>{chip_nivel(n['deporte'], n['nivel'])}"
            f"<small>{n['partidos']} partido{'s' if n['partidos'] != 1 else ''} · {n['victorias']} victoria{'s' if n['victorias'] != 1 else ''}</small></div>"
            for n in niveles)
        mis = ("<div class='lg-card'><div class='lg-sec' style='margin-top:0'>📈 Tus niveles</div>"
               "<p class='sub' style='margin:0 0 6px'>Suben o bajan solos con tus resultados en retos y campeonatos.</p>"
               f"<div class='nv-tabla'>{filas}</div></div>")
    chips = "".join(f"<button type='button' class='chip{' sel' if d == dep0 else ''}' data-dep='{d}'>{_emo(d)} {_etq(d)}</button>"
                    for d in DEPORTES_ACTIVOS)
    cuerpo = (
        f"<style>{_CSS_BASE}{_CSS_NIVEL}</style>"
        "<div class='lg-wrap' style='max-width:560px'>"
        "<a class='sub' href='/perfil' style='text-decoration:none'>‹ Perfil</a>"
        "<h1>Tu nivel de jugador</h1>" + mis +
        "<div class='lg-card' id='nvForm'>"
        "<div style='font-size:20px;font-weight:800'>Autoevalúate</div>"
        "<p class='sub' style='margin:4px 0 0'>Estimamos tu nivel (1 a 7, como Playtomic). Luego se ajusta solo con tus resultados en retos y campeonatos.</p>"
        "<div class='lg-sec'>Deporte</div>"
        f"<div class='lg-chips' id='nvDep'>{chips}</div>"
        "<div class='nv-q'><div class='t'>¿Cuántos años llevas jugando?<span id='nvAnT'></span></div>"
        "<input type='range' id='nvAn' min='0' max='10' step='1' value='2' aria-label='Años jugando'></div>"
        "<div class='nv-q'><div class='t'>¿Cuántas veces juegas por semana?<span id='nvFrT'></span></div>"
        "<input type='range' id='nvFr' min='0' max='5' step='1' value='2' aria-label='Veces por semana'></div>"
        "<label class='nv-sw'>¿Compites en torneos o ligas?<input type='checkbox' id='nvComp'></label>"
        "<button type='button' class='btn lg' id='nvCalc' style='margin-top:16px'>Calcular mi nivel</button>"
        "</div>"
        "<div class='lg-card nv-res' id='nvRes' hidden><span class='em'>🏆</span>"
        "<div style='font-size:19px;font-weight:800;margin-top:8px'>¡Listo! Este es tu nivel</div>"
        "<div id='nvChip'></div>"
        "<p class='sub'>Subirá o bajará solo según tus resultados. Ahora puedes buscar rivales de tu nivel.</p>"
        "<div class='acciones' style='justify-content:center'><a class='btn' href='/liga?tab=retar'>Buscar rivales</a>"
        "<button type='button' class='btn sec' id='nvOtro'>Evaluar otro deporte</button></div></div>"
        "</div>"
        "<script>(function(){\n"
        "var dep=" + json.dumps(dep0) + ",$=function(i){return document.getElementById(i)};\n"
        "function pinta(){var a=+$('nvAn').value,f=+$('nvFr').value;$('nvAnT').textContent=a+' '+(a===1?'año':'años')+(a>=10?'+':'');$('nvFrT').textContent=f+(f>=5?'+':'')+' por semana'}\n"
        "$('nvAn').oninput=pinta;$('nvFr').oninput=pinta;pinta();\n"
        "$('nvDep').addEventListener('click',function(ev){var b=ev.target.closest('[data-dep]');if(!b)return;dep=b.dataset.dep;"
        "this.querySelectorAll('.chip').forEach(function(c){c.classList.toggle('sel',c===b)})});\n"
        "$('nvCalc').onclick=function(){var btn=this;if(btn.disabled)return;btn.disabled=true;pcgCargando('Calculando…');\n"
        " fetch('/web/mi-nivel',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({deporte:dep,anios:+$('nvAn').value,frecuencia:+$('nvFr').value,compite:$('nvComp').checked})})\n"
        " .then(function(r){return r.json()}).then(function(j){pcgCargando(false);btn.disabled=false;\n"
        "  if(!j.ok){pcgAvisar({titulo:'No se pudo guardar',mensaje:j.mensaje||'Reintenta en un momento.',icono:'⚠️'});return}\n"
        "  $('nvChip').innerHTML=j.chip;$('nvForm').hidden=true;$('nvRes').hidden=false;window.scrollTo(0,0)})\n"
        " .catch(function(){pcgCargando(false);btn.disabled=false;pcgAvisar({titulo:'Sin conexión',mensaje:'Revisa tu internet y reintenta.',icono:'📶'})})};\n"
        "$('nvOtro').onclick=function(){pcgRecargar('Un momento…')};\n"
        "})();</script>")
    return ui.shell("Tu nivel de jugador", cuerpo, sesion=ses, titulo_tab="Tu nivel · Pichangol")


@router.post("/web/mi-nivel")
def guardar_mi_nivel(request: Request, body: dict = Body(default_factory=dict)) -> JSONResponse:
    """`AppState.sembrarMiNivel` para el correo de la sesión."""
    ses = sesion.de_request(request)
    if not ses:
        return JSONResponse({"ok": False, "error": "sesion_requerida", "mensaje": "Inicia sesión."}, status_code=401)
    dep = str(body.get("deporte") or "")
    if dep not in DEPORTES_ACTIVOS:
        return JSONResponse({"ok": False, "error": "deporte_invalido", "mensaje": "Elige un deporte."}, status_code=400)
    try:
        anios, frec = int(body.get("anios")), int(body.get("frecuencia"))
    except (TypeError, ValueError):
        return JSONResponse({"ok": False, "error": "datos_invalidos", "mensaje": "Datos inválidos."}, status_code=400)
    if not (0 <= anios <= 10 and 0 <= frec <= 5):
        return JSONResponse({"ok": False, "error": "datos_invalidos", "mensaje": "Datos inválidos."}, status_code=400)
    nivel = seed_desde(anios, frec, bool(body.get("compite")))
    if not guardar_nivel(ses["email"], dep, nivel):
        return JSONResponse({"ok": False, "error": "no_guardado", "mensaje": "No pudimos guardar tu nivel. Reintenta."}, status_code=503)
    return JSONResponse({"ok": True, "deporte": dep, "nivel": round(nivel, 2), "chip": chip_nivel(dep, nivel)})


# ═══════════════════════════ RANKING GLOBAL (port) ═══════════════════════════

def _dt(v) -> datetime | None:
    """Fecha local (Lima) sin zona, como `DateTime.tryParse(...).toLocal()`."""
    if isinstance(v, datetime):
        d = v
    else:
        try:
            d = datetime.fromisoformat(str(v or "").replace("Z", "+00:00"))
        except ValueError:
            return None
    return d.astimezone(_TZ).replace(tzinfo=None) if d.tzinfo else d


def _ahora() -> datetime:
    return datetime.now(_TZ).replace(tzinfo=None)


# Temporada = (año, trimestre), como `Temporada` del app.
def temporada_de(d: datetime) -> tuple[int, int]:
    return (d.year, (d.month - 1) // 3 + 1)


def _tid(t: tuple[int, int]) -> str:
    return f"{t[0]}-T{t[1]}"


def _tdesde(tid: str) -> tuple[int, int] | None:
    try:
        a, t = tid.split("-T")
        a, t = int(a), int(t)
        return (a, t) if 1 <= t <= 4 else None
    except (ValueError, AttributeError):
        return None


def _t_anterior(t: tuple[int, int]) -> tuple[int, int]:
    return (t[0] - 1, 4) if t[1] <= 1 else (t[0], t[1] - 1)


def _t_fin(t: tuple[int, int]) -> datetime:
    return datetime(t[0] + 1, 1, 1) if t[1] >= 4 else datetime(t[0], t[1] * 3 + 1, 1)


_MESES_T = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Set", "Oct", "Nov", "Dic"]


def _t_nombre(t: tuple[int, int]) -> str:
    b = (t[1] - 1) * 3
    return f"{_MESES_T[b]}–{_MESES_T[b + 2]} {t[0]}"


def _t_contiene(t: tuple[int, int] | None, d: datetime | None) -> bool:
    return t is None or (d is not None and temporada_de(d) == t)


_CACHE: dict[str, tuple[float, list]] = {}


def _cacheado(clave: str, fn, ttl: float = 60.0) -> list:
    hit = _CACHE.get(clave)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    v = fn()
    _CACHE[clave] = (time.time(), v)
    return v


def _academias_ranking() -> list[dict]:
    """Todas las academias no eliminadas (`cargarAcademiasRemotas`), con sus
    partidos de ranking embebidos (`Academia.toJson`)."""
    if not pg.habilitado:
        return []
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id, data FROM pichangol_academias WHERE coalesce(eliminada,false) = false")
            out = []
            for aid, data in cur.fetchall():
                d = data if isinstance(data, dict) else (json.loads(data) if data else {})
                if isinstance(d, dict):
                    d["id"] = aid
                    out.append(d)
            return out
    except Exception:  # noqa: BLE001
        return []


def _campeonatos_ranking() -> list[dict]:
    """Todos los campeonatos no eliminados (`CampeonatosRepo.fetchRemotos`)."""
    if not pg.habilitado:
        return []
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id, academia_id, data FROM pichangol_campeonatos WHERE coalesce(eliminado,false) = false")
            out = []
            for cid, aid, data in cur.fetchall():
                d = data if isinstance(data, dict) else (json.loads(data) if data else {})
                if isinstance(d, dict):
                    d["id"] = cid
                    d.setdefault("academiaId", aid or "")
                    out.append(d)
            return out
    except Exception:  # noqa: BLE001
        return []


def datos_ranking() -> dict:
    """Las tres fuentes del ranking (academias, campeonatos, retos jugados)."""
    from retos.router import resultados_para_ranking
    try:
        retos = resultados_para_ranking()["resultados"]
    except Exception:  # noqa: BLE001
        retos = []
    return {"academias": _cacheado("academias", _academias_ranking),
            "campeonatos": _cacheado("campeonatos", _campeonatos_ranking),
            "retos": retos}


def _fecha_reto(r: dict) -> datetime:
    return _dt(r.get("jugado_en") or r.get("creado_en")) or _ahora()


def _nombre_de(p: dict, jid: str) -> str:
    return str((p.get("jugadorANombre") if jid == p.get("jugadorAId") else p.get("jugadorBNombre")) or "")


def _email_de(p: dict, jid: str) -> str:
    return str((p.get("jugadorAEmail") if jid == p.get("jugadorAId") else p.get("jugadorBEmail")) or "")


def _es_dobles(r: dict) -> bool:
    return str(r.get("modalidad") or "singles") == "dobles"


def _filas(agg: dict) -> list[dict]:
    filas = []
    for key, g in agg.items():
        if g["pj"] == 0:
            continue
        primaria, maxn = "", -1
        for n, c in g["por"].items():  # academia primaria = donde tiene más partidos
            if c > maxn:
                maxn, primaria = c, n
        filas.append({"key": key, "nombre": g["nombre"], "categoria": g["categoria"], "academia": primaria,
                      "academias": len(g["ids"]), "deporte": g["deporte"], "pj": g["pj"], "pg": g["pg"], "pp": g["pp"],
                      "puntos": g["pg"] * PUNTOS_VICTORIA + g["pp"] * PUNTOS_DERROTA,
                      "pct": (g["pg"] / g["pj"] * 100) if g["pj"] else 0.0,
                      "email": key[2:] if key.startswith("e:") else ""})
    filas.sort(key=lambda f: (-f["puntos"], -f["pct"], -f["pg"]))
    return filas


def _agg(agg: dict, key: str, dep: str) -> dict:
    return agg.setdefault(key, {"deporte": dep, "pj": 0, "pg": 0, "pp": 0, "nombre": "", "categoria": "", "ids": set(), "por": {}})


def ranking_global(d: dict, deporte: str | None = None, categoria: str | None = None,
                   zona: str | None = None, temporada: tuple[int, int] | None = None) -> list[dict]:
    """`AppState.rankingGlobal`: academias + retos (singles) + campeonatos
    independientes, dedupe por correo, 3 pts victoria / 1 derrota."""
    agg: dict[str, dict] = {}
    for a in d["academias"]:
        adep = str(a.get("deporte") or "tenis")
        if deporte and adep != deporte:
            continue
        if zona and str(a.get("zona") or "").strip() != zona:
            continue
        cats = a.get("categorias") or {}
        for p in a.get("partidos") or []:
            if temporada and not _t_contiene(temporada, _dt(p.get("fecha")) or _ahora()):
                continue
            for jid in (p.get("jugadorAId") or "", p.get("jugadorBId") or ""):
                if not jid:
                    continue
                cat = str(cats.get(jid) or "")
                if categoria and cat != categoria:
                    continue
                nombre = _nombre_de(p, jid)
                email = _email_de(p, jid).strip().lower()
                g = _agg(agg, f"e:{email}" if email else f"a:{a.get('id')}|{jid}", adep)
                g["pj"] += 1
                if p.get("ganadorId") == jid:
                    g["pg"] += 1
                else:
                    g["pp"] += 1
                if nombre:
                    g["nombre"] = nombre
                if cat:
                    g["categoria"] = cat
                g["ids"].add(a.get("id"))
                an = str(a.get("nombre") or "")
                g["por"][an] = g["por"].get(an, 0) + 1
    if not categoria:
        for r in d["retos"]:
            if _es_dobles(r):
                continue
            rdep = str(r.get("deporte") or "")
            if deporte and rdep != deporte:
                continue
            if zona and str(r.get("zona") or "").strip() != zona:
                continue
            if temporada and not _t_contiene(temporada, _fecha_reto(r)):
                continue
            ganador = str(r.get("ganador_email") or "").strip().lower()
            if not ganador:
                continue
            for side in ("retador", "retado"):
                email = str(r.get(f"{side}_email") or "").strip().lower()
                if not email:
                    continue
                g = _agg(agg, f"e:{email}", deporte or (rdep if rdep in DEPORTES else "tenis"))
                g["pj"] += 1
                if ganador == email:
                    g["pg"] += 1
                else:
                    g["pp"] += 1
                nombre = str(r.get(f"{side}_nombre") or "")
                if nombre:
                    g["nombre"] = nombre
                g["por"]["Retos"] = g["por"].get("Retos", 0) + 1
    for c in d["campeonatos"]:
        if c.get("academiaId"):
            continue
        cdep = str(c.get("deporte") or "")
        if deporte and cdep != deporte:
            continue
        if zona:
            continue
        if categoria and str(c.get("categoria") or "") != categoria:
            continue
        fecha = _dt(c.get("inicio")) or _dt(c.get("inscripcionHasta")) or _ahora()
        if temporada and not _t_contiene(temporada, fecha):
            continue
        por_id = {p.get("id"): p for p in c.get("participantes") or []}
        for pt in c.get("partidos") or []:
            if not L.jugado(pt):
                continue
            aid, bid, gid = pt.get("aId"), pt.get("bId"), L.ganador_id(pt)
            if aid is None or bid is None or gid is None:
                continue
            for pid in (aid, bid):
                p = por_id.get(pid)
                if p is None:
                    continue
                email = str(p.get("email") or "").strip().lower()
                key = f"t:{c.get('id')}|{pid}" if L.es_equipo(p) else (f"e:{email}" if email else f"c:{c.get('id')}|{pid}")
                g = _agg(agg, key, cdep)
                g["pj"] += 1
                if gid == pid:
                    g["pg"] += 1
                else:
                    g["pp"] += 1
                if p.get("nombre"):
                    g["nombre"] = str(p["nombre"])
                if c.get("categoria"):
                    g["categoria"] = str(c["categoria"])
                cn = str(c.get("nombre") or "")
                g["por"][cn] = g["por"].get(cn, 0) + 1
    return _filas(agg)


def _clave_pareja(lado: list[tuple]) -> str | None:
    correos = sorted(x for x in (str(a or "").strip().lower() for a, _ in lado) if x)
    return f"d:{correos[0]}|{correos[1]}" if len(correos) == 2 else None


def _nombre_pareja(lado: list[tuple]) -> str:
    ns = []
    for c, n in lado:
        n = str(n or "").strip()
        if not n:
            c = str(c or "").strip()
            n = c.split("@")[0] if "@" in c else c
        if n:
            ns.append(n)
    return " / ".join(ns)


def ranking_dobles(d: dict, deporte: str | None = None, zona: str | None = None,
                   temporada: tuple[int, int] | None = None) -> list[dict]:
    """`AppState.rankingDobles`: tabla de PAREJAS (clave `d:a|b` ordenada)."""
    agg: dict[str, dict] = {}
    nombres: dict[str, str] = {}
    for r in d["retos"]:
        if not _es_dobles(r):
            continue
        dep = str(r.get("deporte") or "")
        dep = dep if dep in DEPORTES else "tenis"
        if deporte and dep != deporte:
            continue
        if zona and str(r.get("zona") or "").strip() != zona:
            continue
        if temporada and not _t_contiene(temporada, _fecha_reto(r)):
            continue
        ganador = str(r.get("ganador_email") or "").strip().lower()
        if not ganador:
            continue
        l1 = [(r.get("retador_email"), r.get("retador_nombre")), (r.get("retador2_email"), r.get("retador2_nombre"))]
        l2 = [(r.get("retado_email"), r.get("retado_nombre")), (r.get("retado2_email"), r.get("retado2_nombre"))]
        k1, k2 = _clave_pareja(l1), _clave_pareja(l2)
        if not k1 or not k2:
            continue
        nombres.setdefault(k1, _nombre_pareja(l1))
        nombres.setdefault(k2, _nombre_pareja(l2))
        gano1 = ganador in {str(a or "").strip().lower() for a, _ in l1}
        for k, gano in ((k1, gano1), (k2, not gano1)):
            g = _agg(agg, k, dep)
            g["pj"] += 1
            if gano:
                g["pg"] += 1
            else:
                g["pp"] += 1
            g["nombre"] = nombres.get(k, g["nombre"])
            g["por"]["Dobles"] = g["por"].get("Dobles", 0) + 1
    filas = _filas(agg)
    for f in filas:
        f["academia"], f["academias"], f["email"] = "Dobles", 0, ""
    return filas


def deportes_con_ranking(d: dict) -> list[str]:
    s = {str(a.get("deporte") or "tenis") for a in d["academias"] if a.get("partidos")}
    s |= {str(r.get("deporte") or "") for r in d["retos"] if str(r.get("deporte") or "") in DEPORTES}
    s |= {str(c.get("deporte") or "") for c in d["campeonatos"]
          if not c.get("academiaId") and any(L.jugado(p) for p in c.get("partidos") or [])}
    return sorted((x for x in s if x in DEPORTES), key=_ORDEN.index)


def categorias_de(d: dict, dep: str) -> list[str]:
    s = set()
    for a in d["academias"]:
        if str(a.get("deporte") or "tenis") == dep:
            s |= {str(c) for c in (a.get("categorias") or {}).values() if c}
    return sorted(s)


def zonas_de(d: dict, dep: str) -> list[str]:
    s = {str(a.get("zona") or "").strip() for a in d["academias"]
         if str(a.get("deporte") or "tenis") == dep and a.get("partidos")}
    s |= {str(r.get("zona") or "").strip() for r in d["retos"] if str(r.get("deporte") or "") == dep}
    return sorted(x for x in s if x)


def temporadas_de(d: dict, dep: str) -> list[tuple[int, int]]:
    s = {temporada_de(_ahora())}
    for a in d["academias"]:
        if str(a.get("deporte") or "tenis") != dep:
            continue
        for p in a.get("partidos") or []:
            s.add(temporada_de(_dt(p.get("fecha")) or _ahora()))
    for r in d["retos"]:
        if str(r.get("deporte") or "") == dep:
            s.add(temporada_de(_fecha_reto(r)))
    return sorted(s, reverse=True)


def hay_dobles(d: dict, dep: str) -> bool:
    return any(_es_dobles(r) and (str(r.get("deporte") or "") if str(r.get("deporte") or "") in DEPORTES else "tenis") == dep
               for r in d["retos"])


# ═════════════════════════════ LIGA (páginas) ════════════════════════════════

_CSS_LIGA = """
.lg-hero{background:linear-gradient(135deg,#067A38,#0E8F67);color:#fff;border-radius:20px;padding:18px;box-shadow:0 10px 24px rgba(0,0,0,.14);margin:6px 0 14px}
.lg-hero .top{display:flex;gap:14px;align-items:center}
.lg-hero .bola{width:56px;height:56px;border-radius:50%;background:rgba(255,255,255,.22);display:flex;align-items:center;justify-content:center;font-size:30px;flex:none}
.lg-hero b{font-size:19px;display:block}
.lg-hero small{color:rgba(255,255,255,.8);font-size:13px}
.lg-hero .est{display:inline-flex;gap:8px;align-items:center;background:rgba(255,255,255,.16);border-radius:99px;padding:8px 12px;margin-top:14px;font-weight:700;font-size:13px;max-width:100%;overflow-wrap:anywhere}
.lg-hero .acc{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}
.lg-hero .acc .btn{margin:0;background:#fff;color:#0A1B3D;padding:9px 14px;font-size:13.5px}
.lg-tabs{display:flex;gap:4px;border-bottom:1px solid #EBEBEB;margin:0 0 14px;overflow-x:auto;scrollbar-width:none}
.lg-tabs a{padding:10px 12px;font-weight:700;color:#6a6a6a;text-decoration:none;border-bottom:2px solid transparent;white-space:nowrap;display:inline-flex;gap:6px;align-items:center}
.lg-tabs a.sel{color:#0A1B3D;border-color:#0A1B3D}
.lg-bdg{background:#E0245E;color:#fff;border-radius:99px;font-size:11.5px;font-weight:800;min-width:20px;height:20px;padding:0 6px;display:inline-flex;align-items:center;justify-content:center}
.lg-fil{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 10px}
.lg-fil a.chip{text-decoration:none}
.lg-info{display:flex;gap:12px;align-items:center;background:#EAF7EF;color:#067A38;border-radius:16px;padding:12px 14px;margin:0 0 10px;font-size:13.5px;line-height:1.35}
.lg-info .em{font-size:24px;flex:none}
.lg-campeon{display:flex;gap:12px;align-items:center;background:linear-gradient(135deg,#067A38,#0E8F67);color:#fff;border-radius:18px;padding:14px 16px;margin:10px 0}
.lg-campeon .em{font-size:34px}
.lg-campeon b{font-size:18px;display:block;overflow-wrap:anywhere}
.lg-campeon small{color:rgba(255,255,255,.8)}
.lg-mipos{display:flex;align-items:center;gap:12px;border:1.5px solid #0B8A3E;background:#fff;border-radius:16px;padding:12px 14px;margin:0 0 12px}
.lg-mipos .pos{font-size:26px;font-weight:900;color:#067A38;flex:none}
.lg-fila{display:flex;align-items:center;gap:10px;background:#fff;border:1px solid #EBEBEB;border-radius:14px;padding:10px 12px;margin:0 0 8px;min-width:0}
.lg-fila.yo{border-color:#0B8A3E;background:#F4FBF6}
.lg-fila .n{width:26px;text-align:center;font-weight:800;color:#6a6a6a;flex:none}
.lg-fila .n.med{font-size:19px}
.lg-fila .q{flex:1;min-width:0}
.lg-fila .q b{display:flex;gap:6px;align-items:center;min-width:0}
.lg-fila .q b span.t{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0}
.lg-fila .q small{display:block;color:#6a6a6a;font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.lg-pro{background:#0A1B3D;color:#fff;font-size:9.5px;font-weight:900;border-radius:6px;padding:2px 6px;letter-spacing:.5px;flex:none}
.lg-st{display:flex;gap:2px;flex:none}
.lg-st div{width:28px;text-align:center}
.lg-st div.pts{width:38px}
.lg-st b{display:block;font-size:14px}
.lg-st .pts b{font-size:17px;color:#067A38}
.lg-st small{font-size:9.5px;color:#6a6a6a;font-weight:600}
.lg-st .g b{color:#0B8A3E}.lg-st .p b{color:#C0392B}
.lg-fila .btn{margin:0;padding:7px 12px;font-size:13px;flex:none}
.lg-reto{background:#fff;border:1px solid #EBEBEB;border-radius:14px;padding:14px;margin:0 0 8px}
.lg-reto .cab{display:flex;gap:12px;align-items:flex-start}
.lg-reto .ico{width:44px;height:44px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:20px;flex:none}
.lg-reto .q{flex:1;min-width:0}
.lg-reto .q .r1{display:flex;gap:8px;align-items:flex-start;justify-content:space-between}
.lg-reto .q .r1 b{overflow-wrap:anywhere}
.lg-reto .est{border-radius:8px;padding:3px 8px;font-size:11.5px;font-weight:800;white-space:nowrap;flex:none}
.lg-reto small{display:block;color:#6a6a6a;font-size:12.5px;margin-top:2px}
.lg-reto .acc{display:flex;gap:10px;margin-top:10px}
.lg-reto .acc .btn{flex:1;margin:0}
.lg-reto .btn.mal{background:#fff;color:#C0392B;border:1px solid #C0392B}
.lg-jug{display:flex;align-items:center;gap:12px;background:#fff;border:1px solid #EBEBEB;border-radius:14px;padding:10px 12px;margin:0 0 8px;min-width:0}
.lg-jug .q{flex:1;min-width:0}
.lg-jug .q b{display:flex;gap:6px;align-items:center;flex-wrap:wrap}
.lg-jug .q small{display:block;color:#6a6a6a;font-size:12.5px;overflow-wrap:anywhere}
.lg-jug .btn{margin:0;flex:none;padding:8px 14px}
.lg-yo{display:flex;align-items:center;gap:12px;background:#EAF7EF;border-radius:18px;padding:14px;margin:0 0 12px;flex-wrap:wrap}
.lg-yo .q{flex:1;min-width:0;color:#067A38}
.lg-yo .q b{display:block}
.lg-yo .btn{margin:0;padding:8px 12px;font-size:13.5px}
.lg-invita{background:linear-gradient(135deg,#067A38,#0E8F67);color:#fff;border-radius:18px;padding:16px;margin:0 0 12px}
.lg-invita b{font-size:17px}
.lg-invita p{color:rgba(255,255,255,.85);font-size:13px;margin:4px 0 12px}
.lg-invita .btn{margin:0;width:100%}
.lg-busca{display:flex;gap:8px;margin:6px 0 10px}
.lg-busca input{flex:1;min-width:0}
.lg-slot{display:flex;align-items:center;gap:12px;background:#fff;border:1px solid #EBEBEB;border-radius:14px;padding:12px;margin:0 0 8px;width:100%;font:inherit;text-align:left;cursor:pointer}
.lg-slot.fijo{cursor:default}
.lg-slot .q{flex:1;min-width:0}
.lg-slot .q small{display:block;color:#6a6a6a;font-size:12px}
.lg-slot .q b{overflow-wrap:anywhere}
.lg-slot.nada .lg-av{background:#EBEBEB;color:#6a6a6a}
.lg-geo{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}
.lg-geo select{width:100%;min-width:0;padding:10px;border-radius:12px;border:1px solid #E4E4E4;font:inherit;background:#fff}
.lg-res{max-height:48vh;overflow:auto;margin-top:8px}
.lg-res .lg-jug{cursor:pointer}
@media(max-width:560px){.lg-geo{grid-template-columns:minmax(0,1fr)}.lg-st div{width:24px}.lg-st div.pts{width:32px}.lg-fila{padding:9px 8px;gap:7px}.lg-fila .n{width:20px}.lg-fila .lg-av{width:32px;height:32px;font-size:14px}.lg-fila .btn{padding:6px 9px;font-size:12px}}
"""

_TABS = [("ranking", "🏆 Ranking"), ("retos", "⚔️ Mis retos"), ("retar", "👥 Retar"), ("dobles", "🎾 Dobles")]


def _retos_pendientes(email: str) -> int:
    """`AppState.cargarRetosPendientes`: recibidos pendientes/aceptados + enviados aceptados."""
    from retos.router import listar_retos
    try:
        r = listar_retos(email)
    except Exception:  # noqa: BLE001
        return 0
    return (sum(1 for x in r["recibidos"] if x["estado"] in ("pendiente", "aceptado"))
            + sum(1 for x in r["enviados"] if x["estado"] == "aceptado"))


def _url(**kw) -> str:
    q = {k: v for k, v in kw.items() if v not in (None, "", False)}
    return "/liga" + ("?" + urlencode(q) if q else "")


@router.get("/liga", response_class=HTMLResponse)
def pagina_liga(request: Request, tab: str = "ranking", deporte: str = "", modalidad: str = "",
                zona: str = "", temporada: str = "", categoria: str = "", parejos: str = "") -> HTMLResponse:
    ses = sesion.de_request(request)
    if not ses:
        return sin_sesion(request, "/liga" + ("?" + request.url.query if request.url.query else ""),
                          "Liga de tenis Pichangol", "La Liga de tenis")
    from circuito.router import perfil as circ_perfil
    email = ses["email"].lower()
    tab = tab if tab in dict(_TABS) else "ranking"
    mi_circ = circ_perfil(email)["jugador"]
    pend = _retos_pendientes(email)
    pro = stores.pro_activo(email)

    det = " · ".join(x for x in ((mi_circ or {}).get("zona"), ("Cat. " + mi_circ["categoria"]) if (mi_circ or {}).get("categoria") else "") if x)
    estado = ((f"✅ Estás en el circuito{' · ' + e(det) if det else ''}") if mi_circ else "🏆 Únete al circuito y deja que te reten")
    hero = ("<div class='lg-hero'><div class='top'><span class='bola'>🎾</span><div><b>Liga de tenis Pichangol</b>"
            "<small>Rankea, reta y sube en tu ciudad</small></div></div>"
            f"<div class='est'>{estado}</div><div class='acc'>"
            + ("" if mi_circ else "<button type='button' class='btn' onclick='lgUnirme()'>Unirme al circuito</button>")
            + "<a class='btn' href='/anfitrion/campeonatos'>🔗 Unirme a un campeonato</a>"
            + ("<span class='btn' style='cursor:default'>👑 Pichangol Pro ✓</span>" if pro
               else "<button type='button' class='btn' onclick='lgPro()'>⭐ Hazte Pichangol Pro</button>")
            + "</div></div>")
    tabs = "<nav class='lg-tabs'>" + "".join(
        f"<a class='{'sel' if k == tab else ''}' href='/liga?tab={k}'>{t}"
        + (f" <span class='lg-bdg'>{pend}</span>" if k == "retos" and pend else "") + "</a>" for k, t in _TABS) + "</nav>"

    if tab == "retos":
        contenido = _tab_retos(email)
    elif tab == "retar":
        contenido = _tab_retar(email, mi_circ, deporte, parejos == "1")
    elif tab == "dobles":
        contenido = _tab_dobles(ses)
    else:
        contenido = _tab_ranking(email, mi_circ, deporte, modalidad, zona, temporada, categoria)

    cfg = {"circ": {k: (mi_circ or {}).get(k, "") for k in ("deporte", "zona", "categoria")} if mi_circ else {}, "categorias": CATEGORIAS_LIGA, "deportes": [[d, _etq(d)] for d in DEPORTES_CIRCUITO],
           "paises": PAISES, "labels": catalogos.GEO_LABELS, "pais": pais_de_zona((mi_circ or {}).get("zona") or ""),
           "play": PLAY_URL}
    cuerpo = (f"<style>{_CSS_BASE}{_CSS_NIVEL}{_CSS_LIGA}</style><div class='lg-wrap'>"
              "<a class='sub' href='/perfil' style='text-decoration:none'>‹ Perfil</a>"
              + hero + tabs + contenido + "</div>"
              "<script>window.LG=" + json.dumps(cfg).replace("</", "<\\/") + ";</script><script>" + _JS_LIGA + "</script>")
    return ui.shell("Liga de tenis Pichangol", cuerpo, sesion=ses, titulo_tab="Liga de tenis · Pichangol")


def _medalla(pos: int) -> str:
    return {1: "🥇", 2: "🥈", 3: "🥉"}.get(pos, "")


def _tab_ranking(email: str, mi_circ: dict | None, deporte: str, modalidad: str, zona: str,
                 temporada: str, categoria: str) -> str:
    d = datos_ranking()
    deportes = deportes_con_ranking(d)
    if not deportes:
        en = bool(mi_circ)
        return ("<div class='lg-vacio'><span class='em'>🏆</span><b style='font-size:18px;color:#0A1B3D'>El ranking global está por arrancar</b>"
                "<p>" + ("Ya estás en el circuito. Reta a otros jugadores para ser de los primeros en aparecer en la tabla de tu ciudad."
                         if en else "Únete al circuito, reta a otros jugadores y sé de los primeros en aparecer en la tabla de tu ciudad.") + "</p>"
                + ("<a class='btn' href='/liga?tab=retar'>🎾 Ver jugadores para retar</a>" if en
                   else "<button type='button' class='btn' onclick='lgUnirme()'>Unirme al circuito</button>") + "</div>")
    dep = deporte if deporte in deportes else deportes[0]
    cats = categorias_de(d, dep)
    cat = categoria if categoria in cats else ""
    zonas = zonas_de(d, dep)
    zon = zona if zona in zonas else ""
    temps = temporadas_de(d, dep)
    tsel = _tdesde(temporada)
    tsel = tsel if tsel in temps else None
    dob_hay = hay_dobles(d, dep)
    dobles = modalidad == "dobles" and dob_hay
    tabla = (ranking_dobles(d, dep, zon or None, tsel) if dobles
             else ranking_global(d, dep, cat or None, zon or None, tsel))
    ahora = _ahora()
    actual = temporada_de(ahora)
    campeon = ranking_global(d, dep, None, zon or None, _t_anterior(actual))
    campeon_email = campeon[0]["email"] if campeon else ""
    base = {"tab": "ranking", "deporte": dep, "modalidad": "dobles" if dobles else "", "zona": zon,
            "temporada": _tid(tsel) if tsel else "", "categoria": cat}

    def chip(txt: str, sel: bool, **cambios) -> str:
        return f"<a class='chip{' sel' if sel else ''}' href='{e(_url(**{**base, **cambios}))}'>{txt}</a>"

    h = ("<div class='lg-info'><span class='em'>🌎</span><span>Ranking cruzado de todas las academias. Juega, sube en tu ciudad y presume tu carnet.</span></div>")
    h += "<div class='lg-fil'>" + "".join(chip(f"{_emo(x)} {_etq(x)}", x == dep, deporte=x, zona="", categoria="", modalidad="") for x in deportes) + "</div>"
    if dob_hay:
        h += "<div class='lg-fil'>" + chip("Singles", not dobles, modalidad="") + chip("Dobles", dobles, modalidad="dobles") + "</div>"
    if zonas:
        h += "<div class='lg-fil'>" + chip("📍 Toda la ciudad", not zon, zona="") + "".join(chip(e(z), z == zon, zona=z) for z in zonas) + "</div>"
    h += "<div class='lg-fil'>" + chip("♾️ Histórico", tsel is None, temporada="") + "".join(
        chip(("🔥 " if t == actual else "🏆 ") + f"T{t[1]} {t[0]}" + (" · en curso" if t == actual else ""), t == tsel, temporada=_tid(t))
        for t in temps) + "</div>"
    if not dobles and cats:
        h += "<div class='lg-fil'>" + chip("Todas", not cat, categoria="") + "".join(chip(e(c), c == cat, categoria=c) for c in cats) + "</div>"
    if not dobles and tsel is not None:
        if _t_fin(tsel) <= ahora and tabla:
            f0 = tabla[0]
            h += (f"<div class='lg-campeon'><span class='em'>🏆</span><div style='min-width:0'><small>Campeón · {_t_nombre(tsel)}</small>"
                  f"<b>{e(f0['nombre'] or 'Jugador')}</b><small>{f0['puntos']} pts · {f0['pg']}G-{f0['pp']}P</small></div></div>")
        elif tsel == actual:
            h += f"<div class='lg-info'><span class='em'>🔥</span><span>Temporada {_t_nombre(tsel)} en curso. Juega y reporta resultados: el ranking se reinicia cada trimestre.</span></div>"
        elif not tabla:
            h += f"<div class='lg-info'><span class='em'>🏆</span><span>La temporada {_t_nombre(tsel)} no tuvo partidos.</span></div>"

    if not tabla:
        return h + "<div class='lg-vacio'>Aún no hay partidos en este filtro.</div>"
    mostrar = tabla[:200]
    fotos = perfiles(f["email"] for f in mostrar if f["email"])
    vivas = tsel is None or tsel == actual
    raqueta = dep in DEPORTES_CIRCUITO
    mipos = next((i for i, f in enumerate(tabla) if f["email"] == email), None) if not dobles else None
    if mipos is not None:
        f = tabla[mipos]
        h += (f"<div class='lg-mipos'><span class='pos'>#{mipos + 1}</span><div style='flex:1;min-width:0'><b>Tu posición</b>"
              f"<div class='sub' style='margin:0;font-size:13px'>{f['puntos']} pts · {f['pj']} jugados · {f['pg']} ganados · {f['pp']} perdidos</div></div></div>")
    filas = ""
    for i, f in enumerate(mostrar):
        pos = i + 1
        med = _medalla(pos)
        p = fotos.get(f["email"]) or {}
        nombre = f["nombre"] or p.get("nombre") or "Jugador"
        corona = " 👑" if (not dobles and vivas and campeon_email and f["email"] == campeon_email) else ""
        pro = "<span class='lg-pro'>PRO</span>" if (not dobles and f["email"] and stores.pro_activo(f["email"])) else ""
        sub = (f["academia"] + (f" +{f['academias'] - 1}" if f["academias"] > 1 else "") + (f" · {f['categoria']}" if f["categoria"] else ""))
        retar = ""
        if not dobles and raqueta and f["email"] and f["email"] != email:
            retar = (f"<button type='button' class='btn chico' data-retar='{e(ref_de(f['email']))}' data-nombre='{e(nombre)}' "
                     f"data-dep='{dep}' data-zona=''>Retar</button>")
        filas += (f"<div class='lg-fila{' yo' if f['email'] and f['email'] == email else ''}'>"
                  f"<span class='n{' med' if med else ''}'>{med or pos}</span>"
                  + avatar(nombre, "" if dobles else p.get("foto_url", ""))
                  + (f"<div class='q'><b><a class='t' href='/jugador/{e(ref_de(f['email']))}?deporte={e(dep)}' style='color:inherit'>{e(nombre)}</a>{corona}{pro}</b><small>{e(sub)}</small></div>"
                     if (not dobles and f["email"]) else
                     f"<div class='q'><b><span class='t'>{e(nombre)}</span>{corona}{pro}</b><small>{e(sub)}</small></div>") +
                  f"<div class='lg-st'><div><b>{f['pj']}</b><small>PJ</small></div><div class='g'><b>{f['pg']}</b><small>G</small></div>"
                  f"<div class='p'><b>{f['pp']}</b><small>P</small></div><div class='pts'><b>{f['puntos']}</b><small>Pts</small></div></div>"
                  f"{retar}</div>")
    if len(tabla) > len(mostrar):
        filas += f"<p class='sub' style='text-align:center'>Mostrando los primeros {len(mostrar)} de {len(tabla)}.</p>"
    return h + filas


_ESTADOS = {"pendiente": ("Pendiente", "#B7791F", "#FFF6E0", "⏳"), "aceptado": ("Aceptado", "#067A38", "#EAF7EF", "🤝"),
            "por_confirmar": ("Por confirmar", "#D9730D", "#FDEFE3", "🕓"), "jugado": ("Jugado", "#6B46C1", "#F1ECFB", "🏆"),
            "disputado": ("En disputa", "#C0392B", "#FBEAEA", "⚠️"), "rechazado": ("Rechazado", "#C0392B", "#FBEAEA", "❌")}


def _lado_nombre(r: dict, lado: str) -> str:
    n1 = str(r.get(f"{lado}_nombre") or ("Retador" if lado == "retador" else "Retado"))
    n2 = str(r.get(f"{lado}2_nombre") or "")
    return f"{n1} / {n2}" if _es_dobles(r) and n2.strip() else n1


def _tarjeta_reto(r: dict, soy_retado: bool, email: str) -> str:
    estado = str(r.get("estado") or "")
    etq, color, fondo, emo = _ESTADOS.get(estado, (estado, "#0E8F67", "#EAF7EF", "🎾"))
    lr, ld = _lado_nombre(r, "retador"), _lado_nombre(r, "retado")
    otro = lr if soy_retado else ld
    ganador = str(r.get("ganador_email") or "").lower()
    gano_retador = ganador in {str(r.get("retador_email") or "").lower(), str(r.get("retador2_email") or "").lower()}
    marcador = str(r.get("marcador") or "")
    dep = str(r.get("deporte") or "")
    zona = str(r.get("zona") or "")
    rid = int(r["id"])
    info = f"<small>{e(_etq(dep))}{' · ' + e(zona) if zona else ''}{' · Dobles' if _es_dobles(r) else ''}</small>"
    if estado in ("jugado", "por_confirmar") and marcador:
        info += f"<small>Resultado: {e(marcador)}</small>"
    if estado == "por_confirmar" and ganador:
        info += f"<small style='color:#D9730D;font-weight:700'>Reportaron que ganó {e(lr if gano_retador else ld)}</small>"
    if estado == "jugado" and ganador:
        info += f"<small style='font-weight:700;color:#0A1B3D'>Ganó {e(lr if gano_retador else ld)}{' (confirmado por plazo)' if r.get('auto_confirmado') else ''}</small>"
    datos = (f" data-id='{rid}' data-retador='{e(lr)}' data-retado='{e(ld)}' data-otro='{e(otro)}'")
    acc = ""
    if estado == "pendiente" and soy_retado:
        acc = ("<div class='acc'><button type='button' class='btn mal' data-acc='rechazar'>Rechazar</button>"
               "<button type='button' class='btn' data-acc='aceptar'>Aceptar</button></div>")
    elif estado == "aceptado":
        acc = "<div class='acc'><button type='button' class='btn' data-acc='reportar'>🏆 Reportar resultado</button></div>"
    elif estado == "por_confirmar":
        if str(r.get("reportado_por") or "").lower() == email:
            acc = f"<small style='margin-top:10px'>Esperando que {e(otro)} confirme el resultado…</small>"
        else:
            acc = ("<div class='acc'><button type='button' class='btn mal' data-acc='disputar'>Disputar</button>"
                   "<button type='button' class='btn' data-acc='confirmar'>✓ Confirmar</button></div>")
    elif estado == "disputado":
        acc = ("<small style='margin-top:10px'>El resultado quedó en disputa. Coordinen y vuelvan a reportarlo.</small>"
               "<div class='acc'><button type='button' class='btn sec' data-acc='reportar'>🏆 Reportar de nuevo</button></div>")
    return (f"<div class='lg-reto'{datos}><div class='cab'><span class='ico' style='background:{fondo}'>{emo}</span>"
            f"<div class='q'><div class='r1'><b>{'Te retó' if soy_retado else 'Retaste a'} {e(otro)}</b>"
            f"<span class='est' style='color:{color};background:{fondo}'>{etq}</span></div>{info}</div></div>{acc}</div>")


def _tab_retos(email: str) -> str:
    from retos.router import listar_retos
    r = listar_retos(email)
    rec, env = r["recibidos"], r["enviados"]
    if not rec and not env:
        return ("<div class='lg-vacio'><span class='em'>⚔️</span>Aún no tienes retos. Abre el Ranking o la lista de jugadores y reta a alguien."
                "<div class='acciones' style='justify-content:center'><a class='btn' href='/liga?tab=retar'>Retar a alguien</a></div></div>")
    h = "<div id='lgRetos'>"
    if rec:
        h += "<div class='lg-sec'>Recibidos</div>" + "".join(_tarjeta_reto(x, True, email) for x in rec)
    if env:
        h += "<div class='lg-sec'>Enviados</div>" + "".join(_tarjeta_reto(x, False, email) for x in env)
    return h + "</div>"


def _fila_jugador(email_j: str, nombre: str, foto: str, detalle: str, extra: str, boton: str) -> str:
    return (f"<div class='lg-jug'>{avatar(nombre, foto)}<div class='q'><b>{e(nombre or 'Jugador')}{extra}</b>"
            + (f"<small>{e(detalle)}</small>" if detalle else "") + f"</div>{boton}</div>")


def _tab_retar(email: str, mi_circ: dict | None, deporte: str, parejos: bool) -> str:
    from circuito.router import jugadores as circ_jugadores
    filtro = deporte if deporte in DEPORTES_CIRCUITO else ""
    lista = [j for j in circ_jugadores(deporte=filtro or None)["jugadores"] if j.get("email") != email]
    emails = [j["email"] for j in lista]
    fotos = perfiles(emails)
    nivs = niveles_de_varios(emails + [email])
    mis = {k.split("|", 1)[1]: v for k, v in nivs.items() if k.startswith(email + "|")}
    if mi_circ:
        det = " · ".join(x for x in (_etq(mi_circ.get("deporte") or ""), mi_circ.get("zona"), mi_circ.get("categoria")) if x)
        h = ("<div class='lg-yo'><span style='font-size:24px'>✅</span><div class='q'><b>Estás en el circuito</b>"
             f"<span style='font-size:13px'>{e(det)}</span></div>"
             "<button type='button' class='btn sec' onclick='lgUnirme()'>Editar</button>"
             "<button type='button' class='btn sec' style='color:#C0392B' onclick='lgSalir()'>Salir</button></div>")
    else:
        h = ("<div class='lg-invita'><b>¿Quieres que te reten?</b><p>Únete al circuito con tu deporte y zona. Aparecerás aquí para que otros te reten y empieces a sumar en el ranking.</p>"
             "<button type='button' class='btn' style='background:#fff;color:#067A38' onclick='lgUnirme()'>＋ Unirme al circuito</button></div>")
    h += ("<div class='lg-card' style='padding:12px 14px'><b>🔎 Buscar a un jugador</b>"
          "<div class='lg-busca'><input type='search' id='lgQ' placeholder='Nombre del jugador' autocomplete='off' aria-label='Buscar jugador'></div>"
          "<div class='lg-res' id='lgQRes'></div></div>")

    def chip(txt: str, sel: bool, dep: str, par: bool) -> str:
        return f"<a class='chip{' sel' if sel else ''}' href='{e(_url(tab='retar', deporte=dep, parejos='1' if par else ''))}'>{txt}</a>"
    h += "<div class='lg-fil'>" + chip("Todos", not filtro, "", parejos) + "".join(
        chip(_etq(d), d == filtro, d, parejos) for d in DEPORTES_CIRCUITO)
    if mis:
        h += chip("📊 De mi nivel", parejos, filtro, not parejos)
    h += "</div>"

    def es_parejo(j: dict) -> bool:
        dep = j.get("deporte") or ""
        mio, suyo = mis.get(dep), nivs.get(f"{j['email']}|{dep}")
        return mio is None or suyo is None or abs(mio - suyo) <= 1.0
    visibles = [j for j in lista if not parejos or es_parejo(j)]
    if not visibles:
        txt = ("No hay jugadores de tu nivel ahora. Quita el filtro \"De mi nivel\" para ver a todos." if parejos
               else "Aún no hay otros jugadores disponibles. Invita a tus amigos a unirse al circuito." if mi_circ
               else "Sé el primero en unirte al circuito y deja que te reten.")
        return h + f"<div class='lg-vacio'><span class='em'>👥</span>{e(txt)}</div>"
    for j in visibles:
        p = fotos.get(j["email"]) or {}
        nombre = j.get("nombre") or p.get("nombre") or "Jugador"
        dep = j.get("deporte") or ""
        det = " · ".join(x for x in (_etq(dep), j.get("zona"), j.get("categoria")) if x)
        extra = ("<span class='lg-pro'>PRO</span>" if stores.pro_activo(j["email"]) else "")
        nv = nivs.get(f"{j['email']}|{dep}")
        if nv is not None:
            extra += chip_nivel(dep, nv, compacto=True)
        boton = (f"<button type='button' class='btn' data-retar='{e(ref_de(j['email']))}' data-nombre='{e(nombre)}' "
                 f"data-dep='{e(dep)}' data-zona='{e(j.get('zona') or '')}'>Retar</button>")
        h += _fila_jugador(j["email"], nombre, p.get("foto_url", ""), det, extra, boton)
    return h


def _tab_dobles(ses: dict) -> str:
    email = ses["email"].lower()
    p = perfiles([email]).get(email) or {}
    yo_nombre = p.get("nombre") or ses.get("nombre") or "Tú"
    foto = p.get("foto_url") or ses.get("foto") or ""

    def slot(k: str, titulo: str, sub: str) -> str:
        return (f"<button type='button' class='lg-slot nada' data-slot='{k}'>{avatar('+', '')}"
                f"<span class='q'><small>{titulo}</small><b>{sub}</b></span><span style='color:#b0b0b0;font-size:22px'>›</span></button>")
    return ("<div class='lg-card'><div style='font-weight:800;font-size:18px'>🎾 Dobles de Tenis</div>"
            "<p class='sub' style='margin:4px 0 12px'>Arma el partido: tu pareja vs la pareja rival. Los cuatro deben estar registrados en Pichangol.</p>"
            "<div class='lg-sec' style='margin-top:4px'>Tu pareja</div>"
            f"<div class='lg-slot fijo'>{avatar(yo_nombre, foto)}<span class='q'><small>Tú</small><b>{e(yo_nombre)}</b></span></div>"
            + slot("companero", "Compañero", "Elegir compañero")
            + "<div class='lg-sec'>Pareja rival</div>"
            + slot("rival1", "Rival 1", "Elegir rival") + slot("rival2", "Rival 2", "Elegir rival")
            + "<button type='button' class='btn lg' id='lgDobEnviar' disabled style='margin-top:14px;opacity:.5'>⚔️ Enviar reto de dobles</button></div>")


# ═════════════════════════════ LIGA (acciones) ═══════════════════════════════

def _ses_o_401(request: Request):
    ses = sesion.de_request(request)
    if not ses:
        return None, JSONResponse({"ok": False, "error": "sesion_requerida", "mensaje": "Inicia sesión para continuar."}, status_code=401)
    return ses, None


def _reto(rid: int):
    return next((x for x in stores.retos if x.id == rid), None)


@router.get("/web/liga/buscar")
def buscar_jugadores(request: Request, q: str = "") -> JSONResponse:
    """`PerfilesRepo.buscar` (nombre o correo, ≥2 letras): devuelve refs opacos,
    nombre, foto y el correo OCULTO (para distinguir homónimos)."""
    ses, err = _ses_o_401(request)
    if err:
        return err
    q = (q or "").strip()
    if len(q) < 2 or not pg.habilitado:
        return JSONResponse({"ok": True, "jugadores": []})
    yo = ses["email"].lower()
    patron = "%" + q.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT email, nombre, foto_url FROM pichangol_perfiles WHERE lower(nombre) LIKE %s OR lower(email) LIKE %s "
                        "ORDER BY nombre LIMIT 25", (patron, patron))
            filas = cur.fetchall()
    except Exception:  # noqa: BLE001
        filas = []
    out = [{"ref": ref_de(str(f[0])), "nombre": str(f[1] or "") or str(f[0]).split("@")[0], "foto": str(f[2] or ""),
            "sub": _ocultar_correo(str(f[0]).lower())} for f in filas if str(f[0] or "").lower() not in ("", yo)]
    return JSONResponse({"ok": True, "jugadores": out})


@router.post("/web/liga/unirse")
def unirse_circuito(request: Request, body: dict = Body(default_factory=dict)) -> JSONResponse:
    """`_UnirseSheet._guardar` → `/circuito/unirse` (categoría obligatoria)."""
    ses, err = _ses_o_401(request)
    if err:
        return err
    from circuito.router import UnirseReq, unirse
    dep, zona, cat = str(body.get("deporte") or ""), str(body.get("zona") or "").strip(), str(body.get("categoria") or "")
    if dep not in DEPORTES_CIRCUITO:
        return JSONResponse({"ok": False, "mensaje": "Elige tu deporte."}, status_code=400)
    if cat not in CATEGORIAS_LIGA:
        return JSONResponse({"ok": False, "mensaje": "Elige tu categoría (5P, 5A, 5B, 4ta…) para unirte."}, status_code=400)
    if zona and not zona_valida(zona):
        return JSONResponse({"ok": False, "mensaje": "Elige tu zona de la lista."}, status_code=400)
    r = unirse(UnirseReq(email=ses["email"], nombre=mi_nombre(ses), deporte=dep, zona=zona, categoria=cat))
    return JSONResponse({"ok": bool(r.get("ok")), "mensaje": "" if r.get("ok") else "No se pudo. Reintenta."})


@router.post("/web/liga/salir")
def salir_circuito(request: Request) -> JSONResponse:
    ses, err = _ses_o_401(request)
    if err:
        return err
    from circuito.router import UnirseReq, salir
    salir(UnirseReq(email=ses["email"]))
    return JSONResponse({"ok": True})


def _texto_limite(r: dict) -> JSONResponse:
    return JSONResponse({"ok": False, "error": "limite_retos_free", "limite": int(r.get("limite") or 3),
                         "mensaje": f"Los jugadores sin Pichangol Pro pueden enviar {int(r.get('limite') or 3)} retos por semana. Hazte Pro y reta sin límites."})


@router.post("/web/liga/retar")
def retar(request: Request, body: dict = Body(default_factory=dict)) -> JSONResponse:
    """`enviarRetoConGuardia`: crea el reto (tope semanal sin Pro), push
    "¡Te retaron! 🎾" y el mensaje directo para coordinar la cancha."""
    ses, err = _ses_o_401(request)
    if err:
        return err
    from retos.router import CrearRetoReq, crear_reto
    yo = ses["email"].lower()
    rival = email_de_ref(str(body.get("ref") or ""))
    dep = str(body.get("deporte") or "")
    zona = str(body.get("zona") or "").strip()[:60]
    if not rival:
        return JSONResponse({"ok": False, "mensaje": "Ese jugador ya no está disponible. Recarga la página."}, status_code=400)
    if rival == yo:
        return JSONResponse({"ok": False, "mensaje": "No puedes retarte a ti mismo."}, status_code=400)
    if dep not in DEPORTES:
        return JSONResponse({"ok": False, "mensaje": "Deporte inválido."}, status_code=400)
    p = perfiles([rival]).get(rival) or {}
    rival_nombre = (str(body.get("nombre") or "").strip()[:80] or p.get("nombre") or "Jugador")
    minom = mi_nombre(ses)
    r = crear_reto(CrearRetoReq(retador_email=yo, retador_nombre=minom, retado_email=rival, retado_nombre=rival_nombre,
                                deporte=dep, zona=zona))
    if r.get("error") == "limite_retos_free":
        return _texto_limite(r)
    if not r.get("ok"):
        return JSONResponse({"ok": False, "mensaje": "No se pudo enviar el reto. Reintenta."}, status_code=400)
    aviso_push(rival, "¡Te retaron! 🎾", f'{minom} te retó a un partido. Ábrelo en "Mis retos".', "reto",
               {"accion": "reto", "deporte": dep})
    _mensaje_directo(yo, minom, rival, f"⚔️ Te reté en Pichangol ({dep}). Coordinemos cancha y horario.")
    return JSONResponse({"ok": True, "mensaje": f'Reto enviado a {rival_nombre}. Coordinen la cancha y repórtenlo en "Mis retos".'})


def _mensaje_directo(de: str, de_nombre: str, para: str, texto: str) -> None:
    """`AppState.enviarMensajeDirecto` (hilo `directo_a|b`, `pichangol_mensajes`). Best-effort."""
    if not pg.habilitado:
        return
    a, b = sorted([de.lower(), para.lower()])
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO pichangol_mensajes (id, hilo, tipo, ref_id, cuenta_email, autor_email, autor_nombre, es_profe, texto) "
                        "VALUES (%s, %s, 'directo', '', %s, %s, %s, false, %s)",
                        (f"msg_{time.time_ns() // 1000}", f"directo_{a}|{b}", para.lower(), de.lower(), de_nombre, texto))
            conn.commit()
    except Exception:  # noqa: BLE001
        pass


@router.post("/web/liga/retar-dobles")
def retar_dobles(request: Request, body: dict = Body(default_factory=dict)) -> JSONResponse:
    """`enviarRetoDoblesConGuardia`: yo + compañero vs rival1 + rival2 (4 distintos)."""
    ses, err = _ses_o_401(request)
    if err:
        return err
    from retos.router import CrearRetoReq, crear_reto
    yo = ses["email"].lower()
    comp, r1, r2 = (email_de_ref(str(body.get(k) or "")) for k in ("companero", "rival1", "rival2"))
    if not comp or not r1 or not r2:
        return JSONResponse({"ok": False, "mensaje": "Elige a tu compañero y a los dos rivales."}, status_code=400)
    if len({yo, comp, r1, r2}) != 4:
        return JSONResponse({"ok": False, "mensaje": "Los cuatro jugadores deben ser distintos."}, status_code=400)
    ps = perfiles([comp, r1, r2])

    def nom(x: str, defecto: str) -> str:
        return (ps.get(x) or {}).get("nombre") or defecto
    minom = mi_nombre(ses)
    r = crear_reto(CrearRetoReq(retador_email=yo, retador_nombre=minom, retado_email=r1, retado_nombre=nom(r1, "Rival"),
                                deporte="tenis", modalidad="dobles", retador2_email=comp,
                                retador2_nombre=nom(comp, "Compañero"), retado2_email=r2, retado2_nombre=nom(r2, "Rival 2")))
    if r.get("error") == "limite_retos_free":
        return _texto_limite(r)
    if not r.get("ok"):
        msg = "Los cuatro jugadores deben ser distintos." if r.get("error") == "jugadores_repetidos" else "No se pudo enviar el reto. Reintenta."
        return JSONResponse({"ok": False, "mensaje": msg}, status_code=400)
    for x in (r1, r2):
        aviso_push(x, "¡Te retaron! 🎾", f'{minom} te retó a un partido. Ábrelo en "Mis retos".', "reto",
                   {"accion": "reto", "deporte": "tenis"})
    return JSONResponse({"ok": True, "mensaje": 'Reto de dobles enviado. Coordinen y repórtenlo en "Mis retos".'})


@router.post("/web/liga/reto/{rid}/responder")
def responder(request: Request, rid: int, body: dict = Body(default_factory=dict)) -> JSONResponse:
    """Aceptar / Rechazar: solo el lado RETADO y solo si está pendiente."""
    ses, err = _ses_o_401(request)
    if err:
        return err
    from retos.router import ResponderReq, _lado_retado, responder_reto
    yo = ses["email"].lower()
    r = _reto(rid)
    if r is None or yo not in _lado_retado(r):
        return JSONResponse({"ok": False, "mensaje": "Ese reto no es tuyo."}, status_code=404)
    if r.estado != "pendiente":
        return JSONResponse({"ok": False, "mensaje": "Ese reto ya fue respondido."}, status_code=409)
    aceptar = bool(body.get("aceptar"))
    responder_reto(rid, ResponderReq(aceptar=aceptar))
    aviso_push(r.retador_email, "¡Reto aceptado! 🔥" if aceptar else "Reto rechazado",
               (f"{r.retado_nombre or 'Tu rival'} aceptó tu reto. Coordinen la cancha y jueguen." if aceptar
                else f"{r.retado_nombre or 'Tu rival'} no pudo aceptar tu reto esta vez."),
               "reto", {"accion": "respondido", "aceptado": aceptar})
    return JSONResponse({"ok": True})


_MARCADOR_OK = set("0123456789- ()")


@router.post("/web/liga/reto/{rid}/resultado")
def reportar(request: Request, rid: int, body: dict = Body(default_factory=dict)) -> JSONResponse:
    """Reportar resultado (aceptado o en disputa): queda por confirmar por el
    lado contrario (o jugado al instante si el plazo de la torre es 0)."""
    ses, err = _ses_o_401(request)
    if err:
        return err
    from retos.router import ResultadoReq, _lado_de, _participantes, resultado_reto
    yo = ses["email"].lower()
    r = _reto(rid)
    if r is None or yo not in _participantes(r):
        return JSONResponse({"ok": False, "mensaje": "Ese reto no es tuyo."}, status_code=404)
    if r.estado not in ("aceptado", "disputado"):
        return JSONResponse({"ok": False, "mensaje": "Este reto no está para reportar."}, status_code=409)
    lado = str(body.get("ganador") or "")
    if lado not in ("retador", "retado"):
        return JSONResponse({"ok": False, "mensaje": "Elige quién ganó."}, status_code=400)
    marcador = str(body.get("marcador") or "").strip()[:40]
    if any(ch not in _MARCADOR_OK for ch in marcador):
        return JSONResponse({"ok": False, "mensaje": "Marcador inválido."}, status_code=400)
    ganador = r.retador_email if lado == "retador" else r.retado_email
    res = resultado_reto(rid, ResultadoReq(ganador_email=ganador, marcador=marcador, reportado_por=yo))
    if not res.get("ok"):
        return JSONResponse({"ok": False, "mensaje": "No se pudo guardar."}, status_code=400)
    soy_retador = _lado_de(r, yo) == "retador"
    minom = mi_nombre(ses)
    otros = [x for x in ((r.retado_email, r.retado2_email) if soy_retador else (r.retador_email, r.retador2_email)) if x]
    for x in otros:
        aviso_push(x, "Confirma el resultado 🎾",
                   (f'{minom} reportó: {marcador}. Confírmalo o dispútalo en "Mis retos".' if marcador
                    else f'{minom} reportó el resultado. Confírmalo o dispútalo en "Mis retos".'),
                   "reto", {"accion": "por_confirmar"})
    d = res["reto"]
    otro = _lado_nombre(d, "retado" if soy_retador else "retador")
    msg = ("Resultado registrado. Ya suma al ranking." if r.estado == "jugado"
           else f"Resultado enviado. Falta que {otro} lo confirme.")
    return JSONResponse({"ok": True, "mensaje": msg})


@router.post("/web/liga/reto/{rid}/confirmar")
def confirmar(request: Request, rid: int, body: dict = Body(default_factory=dict)) -> JSONResponse:
    """El lado CONTRARIO al que reportó confirma (suma al ranking) o disputa."""
    ses, err = _ses_o_401(request)
    if err:
        return err
    from retos.router import ConfirmarReq, _lado_retador, _participantes, confirmar_reto
    yo = ses["email"].lower()
    r = _reto(rid)
    if r is None or yo not in _participantes(r):
        return JSONResponse({"ok": False, "mensaje": "Ese reto no es tuyo."}, status_code=404)
    if r.estado != "por_confirmar":
        return JSONResponse({"ok": False, "mensaje": "Este resultado ya no está por confirmar."}, status_code=409)
    acepta = bool(body.get("acepta"))
    res = confirmar_reto(rid, ConfirmarReq(por_email=yo, acepta=acepta))
    if not res.get("ok"):
        msg = ("Tú reportaste este resultado: lo confirma tu rival." if res.get("error") == "reportador_no_confirma"
               else "No se pudo. Reintenta.")
        return JSONResponse({"ok": False, "mensaje": msg}, status_code=400)
    minom = mi_nombre(ses)
    d = res["reto"]
    if acepta:
        lado_ret = _lado_retador(r)
        gano_retador = r.ganador_email in lado_ret
        reportador_gano = (r.reportado_por in lado_ret) == gano_retador
        aviso_push(r.reportado_por, "¡Ganaste! 🏆" if reportador_gano else "Resultado del reto",
                   ("¡Felicidades! Sumaste al ranking de tenis." if reportador_gano
                    else f"Se confirmó el resultado vs {minom}. Esta vez perdiste."),
                   "reto", {"accion": "desenlace", "gano": reportador_gano})
        ganador_nombre = _lado_nombre(d, "retador" if gano_retador else "retado")
        foto = (perfiles([r.ganador_email]).get(r.ganador_email) or {}).get("foto_url", "") if not _es_dobles(d) else ""
        return JSONResponse({"ok": True, "ganador": ganador_nombre, "foto": foto})
    aviso_push(r.reportado_por, "Resultado en disputa ⚠️",
               f"{minom} no está de acuerdo con el resultado. Coordinen y vuelvan a reportarlo.", "reto", {"accion": "disputado"})
    return JSONResponse({"ok": True, "mensaje": "Marcaste el resultado en disputa. Vuelvan a reportarlo cuando coincidan."})


_JS_LIGA = r"""
(function(){
var C = window.LG || {};
function esc(s){ return String(s == null ? '' : s).replace(/[&<>"']/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]; }); }
function post(url, body, msg){
  pcgCargando(msg || 'Un momento…');
  return fetch(url, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body || {})})
    .then(function(r){ return r.json().catch(function(){ return {ok: false}; }); })
    .then(function(j){ pcgCargando(false); return j || {ok: false}; })
    .catch(function(){ pcgCargando(false); return {ok: false, mensaje: 'Sin conexión. Revisa tu internet y reintenta.'}; });
}
function fallo(j, t){ pcgAvisar({titulo: t || 'No se pudo', mensaje: (j && j.mensaje) || 'Reintenta en un momento.', icono: '⚠️'}); }
function av(nombre, foto){ return foto ? "<img class='lg-av' src='" + esc(foto) + "' alt='' referrerpolicy='no-referrer'>" : "<span class='lg-av ini'>" + esc((nombre || '?').trim().charAt(0).toUpperCase() || '?') + "</span>"; }
window.lgPro = function(){
  pcgConfirmar({titulo: 'Pichangol Pro', icono: '⭐', mensaje: 'Tu carnet oficial, el ranking del circuito y retos sin límite. La membresía se activa desde la app.', confirmar: 'Abrir la app', cancelar: 'Ahora no'})
    .then(function(ok){ if(ok) window.open(C.play, '_blank', 'noopener'); });
};
function limite(j){
  pcgConfirmar({titulo: 'Llegaste a tu límite de retos', icono: '👑', mensaje: j.mensaje, confirmar: 'Ver Pro', cancelar: 'Ahora no'})
    .then(function(ok){ if(ok) window.open(C.play, '_blank', 'noopener'); });
}
// ── Retar (ranking, jugadores, buscador) ─────────────────────────────────
var enVuelo = {};
document.addEventListener('click', function(ev){
  var b = ev.target.closest('[data-retar]'); if(!b) return;
  var ref = b.dataset.retar; if(enVuelo[ref]) return;
  pcgConfirmar({titulo: 'Retar a ' + b.dataset.nombre, icono: '⚔️', mensaje: 'Le llegará tu reto. Si acepta, coordinan la cancha y reportan el resultado aquí o en la app.', confirmar: 'Enviar reto', cancelar: 'Cancelar'})
    .then(function(ok){ if(!ok) return; enVuelo[ref] = 1;
      post('/web/liga/retar', {ref: ref, nombre: b.dataset.nombre, deporte: b.dataset.dep, zona: b.dataset.zona || ''}, 'Enviando reto…').then(function(j){
        delete enVuelo[ref];
        if(j.error === 'limite_retos_free') return limite(j);
        if(!j.ok) return fallo(j);
        pcgAvisar({titulo: '¡Reto enviado!', icono: '⚔️', mensaje: j.mensaje}).then(function(){ pcgIr('/liga?tab=retos', 'Abriendo tus retos…'); });
      }); });
});
// ── Unirse / salir del circuito ──────────────────────────────────────────
window.lgUnirme = function(){
  var c = C.circ || {}, dep = c.deporte || 'tenis', cat = c.categoria || '', pais = C.pais || 'PE';
  var h = "<div style='text-align:left'><div class='lg-sec' style='margin-top:0'>Deporte</div><div class='lg-chips' id='uDep'>" +
    C.deportes.map(function(d){ return "<button type='button' class='chip" + (d[0] === dep ? ' sel' : '') + "' data-v='" + d[0] + "'>" + esc(d[1]) + "</button>"; }).join('') +
    "</div><div class='lg-sec'>Zona</div><div class='lg-chips' id='uPais'>" +
    C.paises.map(function(p){ return "<button type='button' class='chip" + (p[0] === pais ? ' sel' : '') + "' data-v='" + p[0] + "'>" + esc(p[1]) + "</button>"; }).join('') +
    "</div><div class='lg-geo'><select id='g1'></select><select id='g2'></select><select id='g3'></select></div>" +
    "<div class='lg-sec'>Categoría *</div><div class='sub' style='margin:-4px 0 6px;font-size:12.5px'>Obligatoria: la liga te ordena y te reta por tu nivel.</div><div class='lg-chips' id='uCat'>" +
    C.categorias.map(function(k){ return "<button type='button' class='chip" + (k === cat ? ' sel' : '') + "' data-v='" + esc(k) + "'>" + esc(k) + "</button>"; }).join('') + "</div></div>";
  var arbol = null;
  function opts(sel, lista, val, ph){ sel.innerHTML = "<option value=''>" + esc(ph) + "</option>" + lista.map(function(o){ return "<option" + (o === val ? ' selected' : '') + ">" + esc(o) + "</option>"; }).join(''); }
  function geo(pre){ var lb = C.labels[pais]; fetch('/web/geo/' + pais).then(function(r){ return r.json(); }).then(function(j){ if(!j.ok) return; arbol = j.arbol; var p = ['', '', ''];
      if(pre){ for(var a in arbol){ for(var b in arbol[a]){ if(arbol[a][b].indexOf(pre) >= 0) p = [a, b, pre]; } } }
      opts(document.getElementById('g1'), Object.keys(arbol), p[0], lb[0]); opts(document.getElementById('g2'), p[0] ? Object.keys(arbol[p[0]]) : [], p[1], lb[1]); opts(document.getElementById('g3'), p[1] ? arbol[p[0]][p[1]] : [], p[2], lb[2]); }).catch(function(){}); }
  var pr = pcgConfirmar({titulo: 'Unirme al circuito', icono: '🎾', html: h, confirmar: 'Guardar y aparecer', cancelar: 'Cancelar'});
  function sel1(id, cb){ document.getElementById(id).addEventListener('click', function(ev){ var b = ev.target.closest('[data-v]'); if(!b) return; this.querySelectorAll('.chip').forEach(function(x){ x.classList.toggle('sel', x === b); }); cb(b.dataset.v); }); }
  sel1('uDep', function(v){ dep = v; }); sel1('uCat', function(v){ cat = v; }); sel1('uPais', function(v){ pais = v; geo(''); });
  document.getElementById('g1').onchange = function(){ var lb = C.labels[pais]; opts(document.getElementById('g2'), this.value ? Object.keys(arbol[this.value]) : [], '', lb[1]); opts(document.getElementById('g3'), [], '', lb[2]); };
  document.getElementById('g2').onchange = function(){ var lb = C.labels[pais]; opts(document.getElementById('g3'), this.value ? arbol[document.getElementById('g1').value][this.value] : [], '', lb[2]); };
  geo(c.zona || '');
  pr.then(function(ok){ if(!ok) return; var zona = (document.getElementById('g3') || {}).value || '';
    if(!cat){ pcgAvisar({titulo: 'Falta tu categoría', icono: '🎾', mensaje: 'Elige tu categoría (5P, 5A, 5B, 4ta…) para unirte.'}).then(lgUnirme); return; }
    post('/web/liga/unirse', {deporte: dep, zona: zona, categoria: cat}, 'Guardando…').then(function(j){
      if(!j.ok) return fallo(j);
      pcgToast('¡Estás en el circuito! Ya pueden retarte.'); pcgRecargar('Actualizando…'); }); });
};
window.lgSalir = function(){
  pcgConfirmar({titulo: '¿Salir del circuito?', icono: '🚪', mensaje: 'Dejarás de aparecer en la lista de jugadores para retar. Tus resultados siguen en el ranking.', confirmar: 'Salir', cancelar: 'Cancelar', destructivo: true})
    .then(function(ok){ if(!ok) return; post('/web/liga/salir', {}, 'Saliendo…').then(function(j){ if(!j.ok) return fallo(j); pcgRecargar('Actualizando…'); }); });
};
// ── Buscador de jugadores ────────────────────────────────────────────────
function buscador(input, caja, alElegir){
  var t = null;
  input.addEventListener('input', function(){ clearTimeout(t); var q = input.value.trim();
    if(q.length < 2){ caja.innerHTML = q ? "<p class='sub' style='font-size:13px'>Escribe al menos 2 letras para buscar.</p>" : ''; return; }
    t = setTimeout(function(){ fetch('/web/liga/buscar?q=' + encodeURIComponent(q)).then(function(r){ return r.json(); }).then(function(j){
      if(input.value.trim() !== q) return; var l = (j && j.jugadores) || [];
      caja.innerHTML = l.length ? l.map(function(x, i){ return "<div class='lg-jug' data-i='" + i + "'>" + av(x.nombre, x.foto) + "<div class='q'><b>" + esc(x.nombre) + "</b><small>" + esc(x.sub) + "</small></div>" + alElegir.boton(x) + "</div>"; }).join('')
        : "<p class='sub' style='font-size:13px'>Nadie con ese nombre. La persona debe haber entrado a Pichangol al menos una vez.</p>";
      caja.querySelectorAll('.lg-jug').forEach(function(el){ var x = l[+el.dataset.i]; if(alElegir.click) el.addEventListener('click', function(){ alElegir.click(x); }); });
    }).catch(function(){}); }, 350); });
}
var q = document.getElementById('lgQ');
if(q) buscador(q, document.getElementById('lgQRes'), {boton: function(x){ return "<button type='button' class='btn' data-retar='" + esc(x.ref) + "' data-nombre='" + esc(x.nombre) + "' data-dep='tenis' data-zona=''>Retar</button>"; }});
// ── Dobles ───────────────────────────────────────────────────────────────
var slots = {}, envBtn = document.getElementById('lgDobEnviar');
function listo(){ var ok = slots.companero && slots.rival1 && slots.rival2; envBtn.disabled = !ok; envBtn.style.opacity = ok ? 1 : .5; }
document.querySelectorAll('[data-slot]').forEach(function(s){ s.addEventListener('click', function(){
  var k = s.dataset.slot;
  var p = pcgConfirmar({titulo: s.querySelector('small').textContent, icono: '🔎', html: "<input type='search' id='dqQ' placeholder='Nombre del jugador' autocomplete='off' style='width:100%'><div class='lg-res' id='dqRes'></div>", confirmar: 'Cerrar', cancelar: 'Cancelar'});
  var inp = document.getElementById('dqQ'); setTimeout(function(){ inp.focus(); }, 60);
  buscador(inp, document.getElementById('dqRes'), {boton: function(){ return ''; }, click: function(x){
    var usado = Object.keys(slots).some(function(o){ return o !== k && slots[o] && slots[o].ref === x.ref; });
    var dup = Object.keys(slots).some(function(o){ return o !== k && slots[o] && slots[o].nombre === x.nombre && slots[o].sub === x.sub; });
    if(usado || dup){ pcgToast('Ese jugador ya está en el partido.'); return; }
    slots[k] = x; s.classList.remove('nada'); s.querySelector('.lg-av').outerHTML = av(x.nombre, x.foto); s.querySelector('b').textContent = x.nombre; listo();
    var ok = document.getElementById('pcgDlgOk'); if(ok) ok.click(); }});
  p.then(function(){});
}); });
if(envBtn) envBtn.addEventListener('click', function(){ if(envBtn.disabled) return; envBtn.disabled = true;
  post('/web/liga/retar-dobles', {companero: slots.companero.ref, rival1: slots.rival1.ref, rival2: slots.rival2.ref}, 'Enviando reto…').then(function(j){
    envBtn.disabled = false;
    if(j.error === 'limite_retos_free') return limite(j);
    if(!j.ok) return fallo(j);
    pcgAvisar({titulo: '¡Reto enviado!', icono: '⚔️', mensaje: j.mensaje}).then(function(){ pcgIr('/liga?tab=retos', 'Abriendo tus retos…'); }); }); });
// ── Mis retos ────────────────────────────────────────────────────────────
function reportar(card){
  var ganador = '', rt = card.dataset.retador, rd = card.dataset.retado;
  var sets = '';
  for(var i = 1; i <= 3; i++){ var o = "<option value=''>–</option>"; for(var n = 0; n <= 7; n++) o += '<option>' + n + '</option>';
    sets += "<span>Set " + i + "</span><select data-s='" + i + "a' aria-label='Set " + i + " " + esc(rt) + "'>" + o + "</select><select data-s='" + i + "b' aria-label='Set " + i + " " + esc(rd) + "'>" + o + "</select>"; }
  var h = "<div style='text-align:left'><b>¿Quién ganó?</b><div style='margin-top:8px'>" +
    "<button type='button' class='lg-opc' data-g='retador'><span class='lg-av ini'>" + esc(rt.charAt(0).toUpperCase()) + "</span><b>" + esc(rt) + "</b><span>○</span></button>" +
    "<button type='button' class='lg-opc' data-g='retado'><span class='lg-av ini'>" + esc(rd.charAt(0).toUpperCase()) + "</span><b>" + esc(rd) + "</b><span>○</span></button></div>" +
    "<b>Marcador (opcional)</b><div class='lg-sets'><span></span><small style='font-weight:700;overflow:hidden;text-overflow:ellipsis'>" + esc(rt) + "</small><small style='font-weight:700;overflow:hidden;text-overflow:ellipsis'>" + esc(rd) + "</small>" + sets + "</div></div>";
  var pr = pcgConfirmar({titulo: 'Reportar resultado', icono: '🏆', html: h, confirmar: 'Guardar', cancelar: 'Cancelar'});
  document.querySelectorAll('#pcgDlgMsg .lg-opc').forEach(function(b){ b.addEventListener('click', function(){ ganador = b.dataset.g;
    document.querySelectorAll('#pcgDlgMsg .lg-opc').forEach(function(x){ x.classList.toggle('sel', x === b); x.lastChild.textContent = x === b ? '✓' : '○'; }); }); });
  pr.then(function(ok){ if(!ok) return;
    var partes = [];
    for(var i = 1; i <= 3; i++){ var a = document.querySelector("#pcgDlgMsg [data-s='" + i + "a']"), b = document.querySelector("#pcgDlgMsg [data-s='" + i + "b']");
      if(a && b && a.value !== '' && b.value !== '') partes.push(a.value + '-' + b.value); }
    if(!ganador){ pcgAvisar({titulo: 'Elige quién ganó', icono: '🏆', mensaje: 'Toca al jugador o pareja ganadora.'}).then(function(){ reportar(card); }); return; }
    post('/web/liga/reto/' + card.dataset.id + '/resultado', {ganador: ganador, marcador: partes.join(' ')}, 'Guardando…').then(function(j){
      if(!j.ok) return fallo(j); pcgAvisar({titulo: 'Listo', icono: '✅', mensaje: j.mensaje}).then(function(){ pcgRecargar('Actualizando…'); }); }); });
}
var retos = document.getElementById('lgRetos');
if(retos) retos.addEventListener('click', function(ev){
  var b = ev.target.closest('[data-acc]'); if(!b) return; var card = b.closest('.lg-reto'), id = card.dataset.id, acc = b.dataset.acc;
  if(acc === 'aceptar' || acc === 'rechazar'){
    var go = acc === 'aceptar' ? Promise.resolve(true) : pcgConfirmar({titulo: '¿Rechazar el reto?', icono: '❌', mensaje: 'Le avisaremos a ' + card.dataset.otro + ' que esta vez no puedes.', confirmar: 'Rechazar', cancelar: 'Volver', destructivo: true});
    go.then(function(ok){ if(!ok) return; post('/web/liga/reto/' + id + '/responder', {aceptar: acc === 'aceptar'}).then(function(j){ if(!j.ok) return fallo(j);
      if(acc === 'aceptar') pcgToast('¡Reto aceptado! Coordinen la cancha.'); pcgRecargar('Actualizando…'); }); });
  } else if(acc === 'reportar'){ reportar(card); }
  else if(acc === 'confirmar' || acc === 'disputar'){
    var conf = acc === 'confirmar';
    pcgConfirmar(conf ? {titulo: '¿Confirmar el resultado?', icono: '✅', mensaje: 'Al confirmarlo, suma al ranking y ya no se puede cambiar.', confirmar: 'Confirmar', cancelar: 'Volver'}
                      : {titulo: '¿Disputar el resultado?', icono: '⚠️', mensaje: 'No contará hasta que lo vuelvan a reportar y ambos coincidan.', confirmar: 'Disputar', cancelar: 'Volver', destructivo: true})
      .then(function(ok){ if(!ok) return; post('/web/liga/reto/' + id + '/confirmar', {acepta: conf}).then(function(j){ if(!j.ok) return fallo(j);
        if(conf) pcgAvisar({titulo: '¡' + j.ganador + ' ganó!', html: "<div style='text-align:center'>" + (j.foto ? av(j.ganador, j.foto).replace("class='lg-av'", "class='lg-av' style='width:64px;height:64px'") : '') + "<p>Sumó al ranking de tenis 🎾</p></div>", icono: '🏆'}).then(function(){ pcgRecargar('Actualizando…'); });
        else pcgAvisar({titulo: 'Resultado en disputa', icono: '⚠️', mensaje: j.mensaje}).then(function(){ pcgRecargar('Actualizando…'); }); }); });
  }
});
})();
"""
