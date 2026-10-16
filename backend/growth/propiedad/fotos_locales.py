"""FOTOS PROPIAS DE LOS LOCALES YA VERIFICADOS (pedido del director, 2-oct-2026:
"los usuarios que ya registraron sus canchas usan fotos de Google Place; deben
tener una opción para subir sus propias fotos y PCG darles un plazo… en la
torre de control debe llevarse este control… unas máximo 3 o 4 del local, de
esa manera ya vamos bajando costos").

Campaña de migración: cada LOCAL verificado (canchas reservables del mismo
dueño + mismo club, `local_key` = el de la tarjeta de fidelidad) debe tener
`fotos_local_min` fotos PROPIAS (la regla de qué es "propia" es la ÚNICA de
`fotos_reclamo`: carpeta de la cancha en NUESTRO bucket `canchas`). Las fotos
del local = unión de las propias de sus canchas.

Config en `stores.config` (espejo en `CONFIG_DEFAULT`):
- `fotos_local_min` (default 3; 0 = campaña apagada), 1..8 en la torre.
- `fotos_local_plazo_dias` (default 30).
- `fotos_local_inicio` (fecha ISO en que el operador LANZÓ la campaña; vacío =
  no lanzada).

Estado por local (`estado_local`):
- `ok`        → tiene el mínimo: se muestran SOLO sus fotos y nunca se le pide
                nada a Google (ni web ni APK).
- `pendiente` → dentro del plazo: todo sigue como hoy (Google de respaldo).
- `vencido`   → plazo pasado sin fotos: deja de recibir fotos de Google
                (placeholder del deporte). NO se esconde la cancha: no se
                pierden reservas.
- `inactiva`  → campaña apagada o no lanzada (y aún sin el mínimo).
El plazo de cada local corre desde max(inicio de la campaña, fecha en que se
ACTIVÓ su reclamo) + prórrogas que dé el operador ("Dar +15 días").

Estado de la campaña por local en `stores.fotos_locales[local_key]` (snapshot):
`{prorroga_dias, avisos: {"<motivo>:<ref>": iso}}`. Avisos al dueño (push +
correo) al lanzar, a 7 días, a 1 día y al vencer; idempotentes por clave.
"""

from __future__ import annotations

import threading
import time
from datetime import date, datetime, timedelta, timezone

from db.store import stores
from propiedad import fotos_reclamo

CLAVE_MIN = "fotos_local_min"
CLAVE_PLAZO = "fotos_local_plazo_dias"
CLAVE_INICIO = "fotos_local_inicio"
DEFAULT_MIN = 3
DEFAULT_PLAZO = 30
MAXIMO = fotos_reclamo.MAXIMO  # 8, tope de la galería
PLAZOS = (15, 30, 45, 60)
PRORROGA_DIAS = 15
SIN_GOOGLE = ("ok", "vencido")
_ORDEN = {"vencido": 0, "pendiente": 1, "ok": 2, "inactiva": 3}
_MESES = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "set", "oct", "nov", "dic")

try:
    from zoneinfo import ZoneInfo
    _TZ = ZoneInfo("America/Lima")
except Exception:  # noqa: BLE001
    _TZ = timezone(timedelta(hours=-5))


def _hoy() -> date:
    return datetime.now(_TZ).date()


def fecha_corta(d: date | str | None) -> str:
    """'15 nov' (como el resto de la web)."""
    if isinstance(d, str):
        try:
            d = date.fromisoformat(d[:10])
        except ValueError:
            return d
    if not d:
        return ""
    return f"{d.day} {_MESES[d.month - 1]}"


# ── Configuración ─────────────────────────────────────────────────────────────

def minimo() -> int:
    try:
        n = int(float(stores.cfg(CLAVE_MIN)))
    except (TypeError, ValueError):
        n = DEFAULT_MIN
    return max(0, min(MAXIMO, n))


def plazo_dias() -> int:
    try:
        n = int(float(stores.cfg(CLAVE_PLAZO)))
    except (TypeError, ValueError):
        n = DEFAULT_PLAZO
    return max(1, min(365, n))


def inicio() -> date | None:
    v = str(stores.cfg(CLAVE_INICIO) or "").strip()
    if not v or v == "0":
        return None
    try:
        return date.fromisoformat(v[:10])
    except ValueError:
        return None


def lanzada() -> bool:
    return minimo() > 0 and inicio() is not None


def config_publica() -> dict:
    ini = inicio()
    return {"minimo": minimo(), "plazo_dias": plazo_dias(), "inicio": ini.isoformat() if ini else "",
            "lanzada": lanzada(), "maximo": MAXIMO, "plazos": list(PLAZOS), "prorroga_dias": PRORROGA_DIAS}


def set_config(minimo_n=None, plazo=None) -> dict:
    if minimo_n is not None:
        try:
            v = int(minimo_n)
        except (TypeError, ValueError):
            return {"ok": False, "error": "minimo_invalido"}
        if v < 0 or v > MAXIMO:
            return {"ok": False, "error": "minimo_invalido", "max": MAXIMO}
        stores.config[CLAVE_MIN] = str(v)
    if plazo is not None:
        try:
            p = int(plazo)
        except (TypeError, ValueError):
            return {"ok": False, "error": "plazo_invalido"}
        if p < 1 or p > 365:
            return {"ok": False, "error": "plazo_invalido"}
        stores.config[CLAVE_PLAZO] = str(p)
    invalidar()
    return {"ok": True, **config_publica()}


def lanzar(hoy: date | None = None, avisar: bool = True) -> dict:
    """Fija el inicio = hoy y avisa a los dueños que aún no tienen el mínimo."""
    if minimo() <= 0:
        return {"ok": False, "error": "minimo_cero",
                "mensaje": "Elige primero cuántas fotos debe tener cada local."}
    hoy = hoy or _hoy()
    stores.config[CLAVE_INICIO] = hoy.isoformat()
    invalidar()
    print(f"[fotos-locales] campaña lanzada {hoy.isoformat()} · mínimo {minimo()} · plazo {plazo_dias()} d", flush=True)
    res = recordatorios(hoy=hoy) if avisar else {"enviados": 0}
    return {"ok": True, **config_publica(), "avisos": res.get("enviados", 0)}


def pausar() -> dict:
    """Pausa la campaña: mínimo 0 (nada se exige ni se oculta)."""
    stores.config[CLAVE_MIN] = "0"
    invalidar()
    return {"ok": True, **config_publica()}


# ── Locales ──────────────────────────────────────────────────────────────────

def local_key(c: dict) -> str:
    """Mismo local que la tarjeta de FIDELIDAD: dueño + club (o nombre)."""
    dueno = (c.get("dueno") or "").strip().lower()
    club = (c.get("club") or "").strip().lower() or (c.get("nombre") or "").strip().lower()
    return f"{dueno}|{club}"


def _verificado_en(ids: set[str]) -> date | None:
    """Fecha en que se ACTIVÓ el reclamo del local (la más antigua de sus
    canchas). None si el local se verificó antes de existir el registro."""
    bases = {i.split("_")[0] for i in ids}
    mejor: date | None = None
    for r in stores.reclamos:
        if getattr(r, "estado", "") != "activada":
            continue
        cid = str(getattr(r, "cancha_id", "") or "")
        if cid not in ids and cid.split("_")[0] not in bases:
            continue
        cuando = getattr(r, "validado_en", None) or getattr(r, "decidido_en", None) or getattr(r, "creado_en", None)
        if not isinstance(cuando, datetime):
            continue
        d = (cuando if cuando.tzinfo else cuando.replace(tzinfo=timezone.utc)).astimezone(_TZ).date()
        if mejor is None or d < mejor:
            mejor = d
    return mejor


def _reg(key: str) -> dict:
    return stores.fotos_locales.setdefault(key, {})


def estado_local(canchas: list[dict], hoy: date | None = None) -> dict:
    """Estado de UN local (sus canchas reservables del mismo dueño + club)."""
    import paises
    hoy = hoy or _hoy()
    cs = sorted(canchas, key=lambda c: str(c.get("id") or ""))
    por_cancha = {str(c.get("id")): fotos_reclamo.de_cancha(c) for c in cs}
    fotos: list[str] = []
    for c in cs:
        for u in por_cancha[str(c.get("id"))]:
            if u not in fotos:
                fotos.append(u)
    # Cancha "principal" (donde el dueño sube las fotos del local): la que ya
    # tiene más fotos propias; a igualdad, la primera.
    principal = max(cs, key=lambda c: len(por_cancha[str(c.get("id"))])) if cs else {}
    c0 = cs[0] if cs else {}
    key = local_key(c0) if c0 else ""
    m = minimo()
    n = len(fotos)
    reg = stores.fotos_locales.get(key) or {}
    prorroga = int(reg.get("prorroga_dias") or 0)
    out = {
        "key": key, "local": (c0.get("club") or c0.get("nombre") or "").strip(),
        "dueno": (c0.get("dueno") or "").strip().lower(),
        "pais": paises.pais_de_coordenadas(c0.get("lat"), c0.get("lng")) if c0 else "PE",
        "canchas": [str(c.get("id")) for c in cs], "principal": str(principal.get("id") or ""),
        "fotos": fotos[:MAXIMO], "n": n, "minimo": m, "faltan": max(0, m - n),
        "prorroga_dias": prorroga, "desde": "", "vence": "", "dias_restantes": None,
    }
    ini = inicio()
    if m <= 0:
        out["estado"] = "inactiva"
    elif n >= m:
        out["estado"] = "ok"
    elif ini is None:
        out["estado"] = "inactiva"
    else:
        ver = _verificado_en(set(out["canchas"]))
        desde = max(ini, ver) if ver else ini
        vence = desde + timedelta(days=plazo_dias() + prorroga)
        dias = (vence - hoy).days
        out.update(desde=desde.isoformat(), vence=vence.isoformat(), dias_restantes=dias,
                   estado="pendiente" if dias >= 0 else "vencido")
    out["sin_google"] = out["estado"] in SIN_GOOGLE
    return out


def agrupar(canchas: list[dict]) -> dict[str, list[dict]]:
    """Canchas RESERVABLES (verificadas con dueño) agrupadas por local."""
    from web import datos
    grupos: dict[str, list[dict]] = {}
    for c in canchas:
        if datos.reservable(c):
            grupos.setdefault(local_key(c), []).append(c)
    return grupos


def locales(hoy: date | None = None, canchas: list[dict] | None = None) -> list[dict]:
    """Estado de TODOS los locales verificados (UNA consulta)."""
    from web import datos
    if canchas is None:
        canchas = datos.canchas_publicas()
    out = [estado_local(g, hoy) for g in agrupar(canchas).values()]
    out.sort(key=lambda x: (_ORDEN.get(x["estado"], 9), x["dias_restantes"] if x["dias_restantes"] is not None else 9999,
                            x["local"].lower()))
    return out


def locales_de_dueno(email: str, hoy: date | None = None) -> list[dict]:
    from web import datos
    em = (email or "").strip().lower()
    if not em:
        return []
    return locales(hoy, datos.canchas_de_dueno(em))


def kpis(lst: list[dict]) -> dict:
    k = {"ok": 0, "pendiente": 0, "vencido": 0, "inactiva": 0}
    for x in lst:
        k[x["estado"]] = k.get(x["estado"], 0) + 1
    total = len(lst)
    k["total"] = total
    k["pct"] = round(100 * k["ok"] / total) if total else 0
    return k


# ── Mapa cacheado cancha → estado (lo consulta /web/foto y el explorador) ─────
# Una consulta cada 60 s como mucho. Se invalida al cambiar la config, al dar
# una prórroga y cuando el dueño guarda/sube fotos desde la web.

_CACHE_TTL = 60.0
_cache: dict = {"t": 0.0, "fuente": None, "mapa": {}}
_lock = threading.Lock()


def invalidar() -> None:
    with _lock:
        _cache.update(t=0.0, fuente=None, mapa={})


def _mapa() -> dict[str, dict]:
    from web import datos
    fuente = datos.canchas_publicas  # en tests cambia por prueba: no mezclar cachés
    ahora = time.monotonic()
    with _lock:
        if _cache["fuente"] is fuente and ahora - _cache["t"] < _CACHE_TTL:
            return _cache["mapa"]
    try:
        lst = locales()
    except Exception as ex:  # noqa: BLE001 — fail-open: sin dato, todo sigue como hoy
        print(f"[fotos-locales] no se pudo calcular el estado: {ex}", flush=True)
        lst = []
    mapa = {cid: est for est in lst for cid in est["canchas"]}
    with _lock:
        _cache.update(t=ahora, fuente=fuente, mapa=mapa)
    return mapa


def estado_de_cancha(c: dict | None) -> dict | None:
    """Estado del local de la cancha, o None (campaña apagada / no verificada)."""
    if not c or minimo() <= 0:
        return None
    return _mapa().get(str(c.get("id") or ""))


def fotos_para(c: dict | None) -> list[str] | None:
    """Fotos a mostrar de una cancha cuyo local ya NO usa Google (`ok` o
    `vencido`): sus propias primero y luego las del resto del local. None =
    sin restricción (se muestra lo que tenga, como siempre)."""
    est = estado_de_cancha(c)
    if not est or not est.get("sin_google"):
        return None
    out = fotos_reclamo.de_cancha(c)
    for u in est.get("fotos") or []:
        if u not in out:
            out.append(u)
    return out[:MAXIMO]


def sin_google_ids() -> list[str]:
    """Canchas cuyo local ya no usa fotos de Google (para el APK)."""
    if minimo() <= 0:
        return []
    return sorted(cid for cid, est in _mapa().items() if est.get("sin_google"))


# ── Prórroga y avisos al dueño ───────────────────────────────────────────────

def prorrogar(key: str, dias: int = PRORROGA_DIAS) -> dict:
    if not key or "|" not in key:
        return {"ok": False, "error": "local_invalido"}
    try:
        d = int(dias)
    except (TypeError, ValueError):
        return {"ok": False, "error": "dias_invalidos"}
    if d < 1 or d > 90:
        return {"ok": False, "error": "dias_invalidos"}
    reg = _reg(key)
    reg["prorroga_dias"] = int(reg.get("prorroga_dias") or 0) + d
    reg.setdefault("historial", []).append({"tipo": "prorroga", "dias": d, "en": datetime.now(timezone.utc).isoformat()})
    reg["historial"] = reg["historial"][-20:]
    invalidar()
    return {"ok": True, "key": key, "prorroga_dias": reg["prorroga_dias"]}


def texto_aviso(est: dict, motivo: str) -> tuple[str, str]:
    """(título, cuerpo) del push / asunto del correo."""
    falta = est.get("faltan") or 0
    local = est.get("local") or "tu local"
    fotos = f"{falta} foto{'s' if falta != 1 else ''}"
    if est.get("estado") == "vencido":
        return ("📷 Tu local ya no muestra fotos",
                f"Venció el plazo: {local} ya no muestra fotos en Pichangol. Sube {fotos} tuyas y vuelve a lucir.")
    dias = est.get("dias_restantes")
    cuando = f"antes del {fecha_corta(est.get('vence'))}"
    if dias is not None:
        cuando += " (hoy es el último día)" if dias == 0 else f" (te queda{'n' if dias != 1 else ''} {dias} día{'s' if dias != 1 else ''})"
    if motivo.startswith("d1"):
        return ("⏰ Mañana vence el plazo de tus fotos", f"Sube {fotos} de {local} {cuando} para seguir mostrando fotos.")
    if motivo.startswith("d7"):
        return ("📷 Te queda una semana para tus fotos", f"Sube {fotos} de {local} {cuando}. Después dejaremos de mostrar las de Google.")
    return ("📷 Sube las fotos de tu local", f"Sube {fotos} propias de {local} {cuando}. Después dejaremos de mostrar las de Google en tu ficha.")


def _motivo_de(est: dict) -> str | None:
    if est.get("estado") == "vencido":
        return f"vencido:{est['vence']}"
    if est.get("estado") != "pendiente":
        return None
    d = est.get("dias_restantes")
    if d is not None and d <= 1:
        return f"d1:{est['vence']}"
    if d is not None and d <= 7:
        return f"d7:{est['vence']}"
    return f"lanzamiento:{inicio().isoformat() if inicio() else ''}"


def _enviar(est: dict, motivo: str) -> None:
    titulo, cuerpo = texto_aviso(est, motivo)
    email = est.get("dueno") or ""
    if not email:
        return
    try:
        from pagos.router import _aviso_push_usuario
        _aviso_push_usuario(email, titulo, cuerpo, tipo="fotos_local")
    except Exception as ex:  # noqa: BLE001
        print(f"[fotos-locales] push falló {email}: {ex}", flush=True)
    try:
        import correos
        correos.encolar("fotos_local", datos={
            "clave": f"fotos_local:{est['key']}:{motivo}", "para": email, "titulo": titulo, "cuerpo": cuerpo,
            "local": est.get("local") or "", "faltan": est.get("faltan") or 0, "minimo": est.get("minimo") or 0,
            "vence": est.get("vence") or "", "estado": est.get("estado") or "", "principal": est.get("principal") or ""})
    except Exception as ex:  # noqa: BLE001
        print(f"[fotos-locales] correo falló {email}: {ex}", flush=True)
    print(f"[fotos-locales] aviso {motivo} → {email} ({est.get('local')}, {est.get('n')}/{est.get('minimo')})", flush=True)


def recordar(key: str, hoy: date | None = None) -> dict:
    """"Recordar ahora" desde la torre: siempre envía (si aún le faltan fotos)."""
    est = next((x for x in locales(hoy) if x["key"] == key), None)
    if not est:
        return {"ok": False, "error": "local_no_encontrado"}
    if est["estado"] not in ("pendiente", "vencido"):
        return {"ok": False, "error": "sin_pendiente",
                "mensaje": "Este local ya tiene sus fotos o la campaña no está lanzada."}
    motivo = f"manual:{int(time.time())}"
    _enviar(est, motivo)
    reg = _reg(key)
    reg.setdefault("avisos", {})[motivo] = datetime.now(timezone.utc).isoformat()
    reg["ultimo_aviso"] = reg["avisos"][motivo]
    return {"ok": True, "key": key}


_ETAPAS = ("lanzamiento", "d7", "d1", "vencido")


def recordatorios(hoy: date | None = None) -> dict:
    """Avisos automáticos (cron horario y al lanzar). Idempotentes: cada
    (local, etapa, vencimiento) se envía UNA vez; al avisar una etapa se dan
    por cubiertas las anteriores (un local recién aprobado con 3 días de
    plazo no recibe el "te queda una semana" después)."""
    if not lanzada():
        return {"ok": True, "enviados": 0}
    enviados = 0
    for est in locales(hoy):
        motivo = _motivo_de(est)
        if not motivo:
            continue
        reg = _reg(est["key"])
        avisos = reg.setdefault("avisos", {})
        if motivo in avisos:
            continue
        _enviar(est, motivo)
        ahora = datetime.now(timezone.utc).isoformat()
        etapa = motivo.split(":", 1)[0]
        for anterior in _ETAPAS[: _ETAPAS.index(etapa) + 1]:
            ref = (inicio().isoformat() if anterior == "lanzamiento" and inicio() else est.get("vence") or "")
            avisos.setdefault(f"{anterior}:{ref}", ahora)
        avisos[motivo] = ahora
        reg["ultimo_aviso"] = ahora
        enviados += 1
    if enviados:
        try:
            from db import pg
            pg.persistir_en_segundo_plano(stores)
        except Exception:  # noqa: BLE001
            pass
    return {"ok": True, "enviados": enviados}


# ── Para la web del dueño ────────────────────────────────────────────────────

def url_subir(est: dict) -> str:
    from urllib.parse import quote
    return f"/anfitrion/cancha/{quote(est.get('principal') or '', safe='')}/editar#sec-fotos"


def aviso_html(est: dict) -> str:
    """Banner por local para Modo anfitrión (Hoy y Mis canchas)."""
    from html import escape as e
    if est.get("estado") not in ("pendiente", "vencido"):
        return ""
    falta = est.get("faltan") or 0
    fotos = f"{falta} foto{'s' if falta != 1 else ''}"
    local = e(est.get("local") or "tu local")
    if est["estado"] == "vencido":
        clase = "err"
        txt = (f"📷 <b>{local} ya no muestra fotos.</b> Sube {fotos} tuyas del local y vuelve a lucir en Pichangol "
               f"(tienes {est['n']} de {est['minimo']}).")
    else:
        d = est.get("dias_restantes") or 0
        quedan = "hoy es el último día" if d == 0 else f"te queda{'n' if d != 1 else ''} {d} día{'s' if d != 1 else ''}"
        clase = "warn"
        txt = (f"📷 <b>Sube {fotos} de {local} antes del {fecha_corta(est.get('vence'))}</b> ({quedan}). "
               f"Llevas {est['n']} de {est['minimo']}. Después dejaremos de mostrar las fotos de Google en tu ficha.")
    return (f"<div class='aviso {clase}' style='margin:12px 0 0'>{txt} "
            "<span class='sub' style='margin:0'>Las de Google no se pueden guardar (sus términos no lo permiten): las tuyas quedan para siempre.</span> "
            f"<a href='{e(url_subir(est))}' style='font-weight:700;white-space:nowrap'>Subir fotos ›</a></div>")


def avisos_dueno(email: str, canchas: list[dict] | None = None, hoy: date | None = None) -> str:
    """Banners de todos los locales del dueño que deben subir fotos."""
    if minimo() <= 0 or inicio() is None:
        return ""
    try:
        lst = locales(hoy, canchas) if canchas is not None else locales_de_dueno(email, hoy)
    except Exception:  # noqa: BLE001
        return ""
    em = (email or "").strip().lower()
    return "".join(aviso_html(x) for x in lst if x.get("dueno") == em)


def para_app(est: dict) -> dict:
    """Lo que el APK necesita para pintar el aviso de un local."""
    titulo, cuerpo = texto_aviso(est, _motivo_de(est) or "") if est["estado"] in ("pendiente", "vencido") else ("", "")
    return {k: est.get(k) for k in ("key", "local", "estado", "n", "minimo", "faltan", "vence", "dias_restantes",
                                     "principal", "canchas")} | {"titulo": titulo, "texto": cuerpo}
