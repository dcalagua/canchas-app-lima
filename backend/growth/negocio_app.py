"""NEGOCIO DEL DUEÑO para el APK (`/negocio/*`): cierres de caja, reservas
fijas ("pensionados"), notas privadas de clientes y "ya recordado" (cobro de
academia y reservas).

Antes el APK guardaba todo esto SOLO en el teléfono (SharedPreferences) y la
web en el snapshot (`stores.negocio_web[correo]`), así que el dueño veía cosas
distintas en cada lado. Ahora la FUENTE ÚNICA es el snapshot y estos
endpoints son la puerta del APK: llaman a las MISMAS funciones que la web
(`web/anfitrion_negocio.py`: `cerrar_caja_de`, `autocerrar_de`, `crear_fija`,
`generar_fijas`, `guardar_nota_de`, `marcar_recordado_de`…), así web y app
producen un solo cierre por día y moneda y UNA sola serie de reservas fijas
(con bloqueos, turnos pasados y fechas ya generadas respetados en el servidor).

El APK queda device-first: pinta desde su caché y sincroniza con
`GET /negocio/estado`; lo que hace sin red va a una cola que reintenta.
`POST /negocio/migrar` sube UNA vez por equipo lo que el teléfono tenía
guardado de antes (el servidor gana en los choques).

Seguridad como el resto del APK: `X-App-Key` + (con `PAGOS_AUTH_USUARIO=1`)
el ID token de Google del MISMO correo. Las reservas fijas solo sobre canchas
de ese correo.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timezone

from fastapi import APIRouter, Body, Header
from fastapi.responses import JSONResponse

from web import anfitrion_negocio as ng
from web import datos


def _deps():
    from pagos.router import _APP
    return _APP


router = APIRouter(prefix="/negocio", tags=["negocio-app"], dependencies=_deps())

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_MONEDAS = ("PEN", "USD", "BOB")


def _auth(email: str, token: str | None) -> str:
    """Correo normalizado tras validar la identidad (o error 400/403)."""
    from pagos.router import _require_usuario
    em = str(email or "").strip().lower()
    if not _EMAIL_RE.match(em):
        raise ng.ErrNegocio("Correo inválido.", 400)
    _require_usuario(em, token)
    return em


def _err(ex: ng.ErrNegocio) -> JSONResponse:
    return JSONResponse({"ok": False, "error": ex.msg}, status_code=ex.status)


def estado(email: str) -> dict:
    """Lo que el APK cachea: el MISMO contenido que muestra la web."""
    neg = ng._negocio(email)
    fijas = [{k: v for k, v in f.items() if k != "hechas"} for f in neg["fijas"]]
    return {"ok": True, "cierres": list(neg["cierres"]), "fijas": fijas, "notas": dict(neg["notas"]),
            "recordados": dict(neg["recordados"])}


def _ok(email: str, **extra) -> dict:
    return {**estado(email), **extra}


def _persistir() -> None:
    ng._persistir()


@router.get("/estado")
def get_estado(email: str, autocerrar: int = 0, x_user_token: str | None = Header(default=None)):
    """Estado del negocio. Con `autocerrar=1` primero genera los cierres
    automáticos de respaldo (todas las monedas), igual que la web al abrir la
    caja; como es un GET que cambia el snapshot, lo persiste aparte."""
    try:
        em = _auth(email, x_user_token)
    except ng.ErrNegocio as ex:
        return _err(ex)
    if autocerrar and ng.autocerrar_de(em):
        _persistir()
    return _ok(em)


# ── Caja del día ────────────────────────────────────────────────────────────

@router.post("/caja/cerrar")
def post_cerrar(body: dict = Body(default_factory=dict), x_user_token: str | None = Header(default=None)):
    """Arqueo CONFIRMADO de un día en una moneda (`moneda` ISO o símbolo;
    vacío = la primera del dueño, como la web)."""
    try:
        em = _auth(body.get("email"), x_user_token)
        r = ng.cerrar_caja_de(em, str(body.get("fecha") or ""), _iso(body.get("moneda")))
    except ng.ErrNegocio as ex:
        return _err(ex)
    return _ok(em, cierre=r["cierre"], cobrado=r["cobrado"], simbolo=r["simbolo"])


@router.post("/caja/reabrir")
def post_reabrir(body: dict = Body(default_factory=dict), x_user_token: str | None = Header(default=None)):
    try:
        em = _auth(body.get("email"), x_user_token)
    except ng.ErrNegocio as ex:
        return _err(ex)
    ng.reabrir_caja_de(em, str(body.get("fecha") or ""), _iso(body.get("moneda")) or "PEN")
    return _ok(em)


def _iso(m) -> str:
    """ISO de moneda desde ISO o símbolo ('S/' → PEN). Vacío si no viene."""
    t = str(m or "").strip()
    if not t:
        return ""
    from pagos.router import moneda_iso
    return moneda_iso(t)


# ── Reservas fijas ──────────────────────────────────────────────────────────

@router.post("/fijas")
def post_fija(body: dict = Body(default_factory=dict), x_user_token: str | None = Header(default=None)):
    """Nuevo cliente fijo + su serie de 4 semanas (generada en el servidor).
    El APK manda su `id` (`fija_<µs>`): reintentar no duplica."""
    try:
        em = _auth(body.get("email"), x_user_token)
        datos_fija = {"cancha_id": body.get("cancha_id"), "dia": body.get("dia"), "hora": body.get("hora"),
                      "nombre": body.get("nombre"), "telefono": body.get("telefono"), "email": body.get("cliente_email")}
        res = ng.crear_fija(em, datos.canchas_de_dueno(em), datos_fija, fid=str(body.get("id") or ""))
    except ng.ErrNegocio as ex:
        return _err(ex)
    return _ok(em, id=res["id"], creadas=res["creadas"], omitidas=res["omitidas"])


@router.post("/fijas/generar")
def post_generar(body: dict = Body(default_factory=dict), x_user_token: str | None = Header(default=None)):
    """Completa las próximas 4 semanas de TODAS las fijas activas del dueño
    (lo que el APK hacía en el teléfono al arrancar). Idempotente."""
    try:
        em = _auth(body.get("email"), x_user_token)
    except ng.ErrNegocio as ex:
        return _err(ex)
    canchas = datos.canchas_de_dueno(em)
    res = ng.generar_fijas(em, canchas) if canchas else {"creadas": 0, "omitidas": []}
    return _ok(em, creadas=res["creadas"], omitidas=res["omitidas"])


@router.post("/fijas/{fid}/activo")
def post_activo(fid: str, body: dict = Body(default_factory=dict), x_user_token: str | None = Header(default=None)):
    try:
        em = _auth(body.get("email"), x_user_token)
        res = ng.activar_fija_de(em, fid, bool(body.get("activo")))
    except ng.ErrNegocio as ex:
        return _err(ex)
    return _ok(em, creadas=res["creadas"], omitidas=res["omitidas"])


@router.post("/fijas/{fid}/quitar")
def post_quitar(fid: str, body: dict = Body(default_factory=dict), x_user_token: str | None = Header(default=None)):
    """Deja de generar. Quitar algo que ya no está también es "ok" (el APK
    reintenta desde su cola y no debe quedarse atascado)."""
    try:
        em = _auth(body.get("email"), x_user_token)
    except ng.ErrNegocio as ex:
        return _err(ex)
    quitada = ng.quitar_fija_de(em, fid)
    return _ok(em, quitada=quitada)


# ── Notas de clientes y recordatorios ───────────────────────────────────────

@router.post("/notas")
def post_nota(body: dict = Body(default_factory=dict), x_user_token: str | None = Header(default=None)):
    try:
        em = _auth(body.get("email"), x_user_token)
        ng.guardar_nota_de(em, str(body.get("clave") or ""), str(body.get("texto") or ""))
    except ng.ErrNegocio as ex:
        return _err(ex)
    return _ok(em)


@router.post("/recordados")
def post_recordados(body: dict = Body(default_factory=dict), x_user_token: str | None = Header(default=None)):
    """"Ya le recordé": `claves` = ids de matrícula (cobro de academia) o
    `res:<id>` (recordatorio de reserva). `cuando` opcional (cola offline)."""
    try:
        em = _auth(body.get("email"), x_user_token)
        claves = [str(x) for x in (body.get("claves") or [])][:100]
        if body.get("clave"):
            claves.append(str(body.get("clave")))
        if not claves:
            raise ng.ErrNegocio("Falta a quién se le recordó.")
        for k in claves:
            ng.marcar_recordado_de(em, k, str(body.get("cuando") or ""))
    except ng.ErrNegocio as ex:
        return _err(ex)
    return _ok(em)


@router.post("/borrar")
def post_borrar(body: dict = Body(default_factory=dict), x_user_token: str | None = Header(default=None)):
    """"Dejar en virgen" / "Eliminar mi cuenta" del APK: borra los cierres,
    fijas, notas y recordatorios del dueño (las reservas ya creadas no)."""
    try:
        em = _auth(body.get("email"), x_user_token)
    except ng.ErrNegocio as ex:
        return _err(ex)
    with ng._LOCK:
        ng.stores.negocio_web.pop(em, None)
    return {"ok": True}


# ── Migración: lo que el teléfono guardaba solo para sí ─────────────────────

def _entero(v) -> int:
    try:
        return int(round(float(v or 0)))
    except (TypeError, ValueError):
        return 0


def migrar(email: str, dispositivo: str, cierres: list, fijas: list, notas: dict, recordados: dict) -> dict:
    """Une UNA vez por equipo lo que el APK tenía solo en el teléfono. El
    servidor gana: no pisa un cierre (fecha + moneda), una fija (id o mismo
    turno), una nota ni una marca más nueva que ya tenga; no resucita fijas
    quitadas. Sin canchas ni academias a su nombre no migra (lo guardado
    puede ser de otra cuenta del mismo teléfono) y el APK reintenta después."""
    dispositivo = re.sub(r"[^\w\-]", "", str(dispositivo or ""))[:80]
    if not dispositivo:
        raise ng.ErrNegocio("Falta el identificador del equipo.")
    canchas = datos.canchas_de_dueno(email)
    try:
        academias = datos.academias_de_dueno(email)
    except Exception:  # noqa: BLE001
        academias = []
    neg = ng._negocio(email)
    if dispositivo in neg["migraciones"]:
        return {"migrado": True, "ya": True, "cierres": 0, "fijas": 0, "notas": 0, "recordados": 0}
    if not canchas and not academias:
        return {"migrado": False, "motivo": "sin_negocio", "cierres": 0, "fijas": 0, "notas": 0, "recordados": 0}
    ids = {c["id"]: c for c in canchas}
    mon_def = ng._monedas(canchas)[0][0] if canchas else "PEN"
    n = {"cierres": 0, "fijas": 0, "notas": 0, "recordados": 0}
    with ng._LOCK:
        if dispositivo in neg["migraciones"]:
            return {"migrado": True, "ya": True, "cierres": 0, "fijas": 0, "notas": 0, "recordados": 0}
        if canchas:
            hechos = {(x.get("fecha"), x.get("moneda", "PEN")) for x in neg["cierres"]}
            for x in (cierres or [])[:400]:
                if not isinstance(x, dict):
                    continue
                f = str(x.get("fecha") or "")[:10]
                try:
                    date.fromisoformat(f)
                except ValueError:
                    continue
                mon = _iso(x.get("moneda")) or mon_def
                if mon not in _MONEDAS or (f, mon) in hechos:
                    continue
                cerrada = str(x.get("cerradaEn") or "") or datetime.now(timezone.utc).isoformat()
                medios = x.get("medios") if isinstance(x.get("medios"), dict) else {}
                neg["cierres"].append({"fecha": f, "moneda": mon, "cobrado": _entero(x.get("cobrado")),
                                       "porCobrar": _entero(x.get("porCobrar")), "reservas": _entero(x.get("reservas")),
                                       "cerradaEn": cerrada[:40], "automatico": bool(x.get("automatico")),
                                       "medios": {str(k)[:20]: _entero(v) for k, v in medios.items()}, "origen": "app"})
                hechos.add((f, mon))
                n["cierres"] += 1
            ng._ordenar_cierres(neg)
            existentes = {f.get("id") for f in neg["fijas"]}
            for x in (fijas or [])[:100]:
                if not isinstance(x, dict):
                    continue
                fid = re.sub(r"[^\w\-]", "", str(x.get("id") or ""))[:60]
                c = ids.get(str(x.get("canchaId") or ""))
                dia = _entero(x.get("diaSemana"))
                hora = str(x.get("hora") or "")
                nombre = re.sub(r"\s+", " ", str(x.get("clienteNombre") or "")).strip()[:80]
                if not fid or c is None or fid in existentes or fid in neg["fijas_quitadas"] or not 1 <= dia <= 7:
                    continue
                if hora not in ng._slots(c):
                    continue
                activo = x.get("activo", True) is not False
                if activo and any(f.get("canchaId") == c["id"] and int(f.get("diaSemana") or 0) == dia and f.get("hora") == hora
                                  and f.get("activo", True) for f in neg["fijas"]):
                    continue
                correo = str(x.get("clienteEmail") or "").strip().lower()[:120]
                neg["fijas"].append({"id": fid, "canchaId": c["id"], "diaSemana": dia, "hora": hora,
                                     "clienteNombre": nombre or "Cliente",
                                     "clienteEmail": correo if _EMAIL_RE.match(correo) else "",
                                     "clienteTelefono": re.sub(r"[^\d+ ]", "", str(x.get("clienteTelefono") or "")).strip()[:20],
                                     "activo": activo, "hechas": []})
                existentes.add(fid)
                n["fijas"] += 1
        for k, v in list((notas or {}).items())[:2000]:
            clave = str(k or "").strip().lower()[:160]
            texto = re.sub(r"[ \t]+", " ", str(v or "")).strip()[:600]
            if clave and texto and clave not in neg["notas"]:
                neg["notas"][clave] = texto
                n["notas"] += 1
        for k, v in list((recordados or {}).items())[:2000]:
            antes = neg["recordados"].get(str(k or "").strip()[:120])
            try:
                ng.marcar_recordado_de(email, str(k), str(v or ""))
            except ng.ErrNegocio:
                continue
            if neg["recordados"].get(str(k or "").strip()[:120]) != antes:
                n["recordados"] += 1
        neg["migraciones"] = (neg["migraciones"] + [dispositivo])[-50:]
    return {"migrado": True, "ya": False, **n}


@router.post("/migrar")
def post_migrar(body: dict = Body(default_factory=dict), x_user_token: str | None = Header(default=None)):
    """Sube lo que el teléfono tenía guardado (una vez por equipo) y devuelve
    el estado unificado. Luego genera la serie de las fijas recién subidas en
    el servidor (las fechas que el teléfono ya había creado quedan como
    ocupadas, no se duplican)."""
    try:
        em = _auth(body.get("email"), x_user_token)
        notas = body.get("notas") if isinstance(body.get("notas"), dict) else {}
        recordados = body.get("recordados") if isinstance(body.get("recordados"), dict) else {}
        res = migrar(em, str(body.get("dispositivo") or ""), body.get("cierres") or [], body.get("fijas") or [],
                     notas, recordados)
    except ng.ErrNegocio as ex:
        return _err(ex)
    if res.get("fijas"):
        canchas = datos.canchas_de_dueno(em)
        if canchas:
            ng.generar_fijas(em, canchas)
    return _ok(em, migracion=res)
