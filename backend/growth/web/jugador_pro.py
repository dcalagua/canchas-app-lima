"""PICHANGOL PRO, TARJETAS, BÚSQUEDA GUIADA Y RECORDATORIOS EN LA WEB (fase 2,
pedido del director: "en la web implementa las mismas funcionalidades que
existen en el app"). Espejo de estas pantallas del APK:

- `GET /pro` = `hazte_pro_screen.dart`: membresía mensual que se cobra de la
  BILLETERA ÚNICA (saldo del correo), con las MISMAS funciones del backend que
  el app: precio `pagos.router._pro_precio_centimos(pais)`, estado
  `_pro_estado` y `post_pro_suscribir` (debita 1 mes y extiende +30 días desde
  el vencimiento vigente). Igual que el app, Pro NO se paga con tarjeta suelta:
  si falta saldo se manda a recargar (en la web: `/mi-billetera#recargar`,
  Culqi Yape/tarjeta en soles). El país del precio es el de la BILLETERA
  (`jugador_billetera.pais_billetera`), así el monto y el símbolo son los del
  saldo que se debita. Extra web: "Cancelar la renovación automática"
  (`auto_renovar=False` en `stores.membresias_pro[email]`, que
  `procesar_renovaciones_pro` respeta); pagar de nuevo a mano la reactiva.
- `GET /pro/planes`: comparación Gratis vs Pro con los candados REALES del
  backend (tope de retos `retos_free_limite_semana`, campeonatos, bodega,
  reserva manual si `WEB_MANUAL_REQUIERE_PRO`).
- `GET /cuenta/tarjetas` = `metodos_pago_screen.dart`: tarjetas guardadas
  (Culqi One Click) con las funciones de `/pagos/metodos`
  (`get_metodos`/`post_metodo`/`del_metodo`, `user_id` = correo como el app).
  La tarjeta la tokeniza Culqi Checkout v4 EN EL NAVEGADOR; al servidor solo
  llega el `tkn_` y en el snapshot solo queda `crd_` + marca + últimos 4.
- `GET /buscar` = `busqueda_guiada_screen.dart` + `asistente_screen.dart`:
  "¿Qué quieres jugar?" por SELECCIÓN (dónde → deporte → cuándo → hora →
  presupuesto). Como el asistente (`BusquedaLocal`, reglas sin IA), sugiere
  canchas reservables filtradas por deporte, zona, turno LIBRE real
  (`router._hora_libre` + `datos.ocupados_varias`) y orden por cercanía o
  precio, con enlace a la ficha `/reservar/{id}?fecha=&hora=`, y "Ver todas en
  el explorador" → `/?deporte=&fecha=&hora=`.
- `GET /anfitrion/recordatorios` = `recordar_reservas_screen.dart` (anti
  no-show del dueño): reservas de hoy/mañana de sus canchas; a quien tiene
  cuenta se le escribe por el CHAT del local (misma fila `pichangol_mensajes`
  que el app: id `msg_<µs>_<reservaId>`, hilo `cancha_<dueño>|<jugador>`; el
  trigger dispara el push) y a quien no, por WhatsApp. "Ya recordado" sale de la
  NUBE: del id del mensaje (el app lo guarda así) o de la marca que la web deja
  en `stores.negocio_web[dueño].recordados["res:<id>"]` (snapshot).

`planes_screen.dart`/`plan_detalle_screen.dart` son el "Plan de trabajo" del
profe (malla + evaluaciones) y viven SOLO en el teléfono (SharedPreferences
`planes_trabajo_json`), sin tabla en la nube: la web no los puede mostrar.
`reservas_hub_screen.dart` (Lista + Calendario del dueño) ya existe en la web
como `/anfitrion/reservas` y `/anfitrion/calendario`.
"""

from __future__ import annotations

import json
import re
import time
from datetime import date, datetime, timedelta, timezone
from math import asin, cos, radians, sin, sqrt
from urllib.parse import quote, urlencode

from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

import config
from db import pg
from db.store import stores
from pagos import culqi
from pagos import router as _pagos
from web import catalogos, datos, horarios, sesion, ui
from web.ui import PLAY_URL, e

router = APIRouter(tags=["web-jugador-pro"])

_LIMA = timezone(timedelta(hours=-5))
MESES_CORTO = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "set", "oct", "nov", "dic"]
_MARCA = {"visa": ("Visa", "#1A1F71"), "mastercard": ("Mastercard", "#EB001B"), "amex": ("American Express", "#2E77BC"),
          "american express": ("American Express", "#2E77BC"), "diners": ("Diners Club", "#0079BE")}


def _email(ses: dict) -> str:
    return (ses.get("email") or "").strip().lower()


def _gate(request: Request, ruta: str, titulo: str, en_app: str):
    from web.jugador_billetera import _gate as g
    return g(request, ruta, titulo, en_app)


def _ses_json(request: Request) -> str:
    ses = sesion.de_request(request)
    em = _email(ses) if ses else ""
    if not em:
        raise HTTPException(status_code=401, detail="sesion_requerida")
    return em


def _err(msg: str, status: int = 400, **kw) -> JSONResponse:
    return JSONResponse({"ok": False, "mensaje": msg, **kw}, status_code=status)


def _fecha(iso: str | None) -> str:
    """"30 oct 2026" (como `_fecha` de hazte_pro_screen), en hora de Lima."""
    try:
        d = datetime.fromisoformat(str(iso or "").replace("Z", "+00:00"))
    except ValueError:
        return ""
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    d = d.astimezone(_LIMA)
    return f"{d.day} {MESES_CORTO[d.month - 1]} {d.year}"


def _monto(sim: str, v: float) -> str:
    return f"{sim} {v:.0f}" if float(v) == int(v) else f"{sim} {v:.2f}"


# ══════════════════════════ PICHANGOL PRO ══════════════════════════════════════

def estado_pro(email: str) -> dict:
    """Todo lo que pinta /pro, con las funciones del backend del app."""
    from web.jugador_billetera import PAISES, pais_billetera
    iso, _fuente = pais_billetera(email)
    P = PAISES.get(iso) or PAISES["PE"]
    activa, hasta = _pagos._pro_estado(email)
    m = stores.membresias_pro.get(email) or {}
    cortesia = bool(m.get("cortesia"))
    return {"iso": iso, "sim": P["moneda"], "precio": _pagos._pro_precio_centimos(iso) / 100.0,
            "activa": activa, "hasta": hasta, "cortesia": cortesia,
            "auto": bool(m) and not cortesia and m.get("auto_renovar", True) is not False,
            "saldo": stores.saldo_centimos(email) / 100.0}


_BENEFICIOS = [("🪪", "Carnet oficial verificado", "Tu ficha de jugador con la insignia Pro."),
               ("📊", "Ranking y estadísticas", "Apareces en el ranking del circuito con tus números."),
               ("🏆", "Prioridad en torneos", "Acceso preferente cuando abramos inscripciones."),
               ("💚", "Apoyas tu comunidad", "Ayudas a que tu academia crezca su circuito.")]


@router.get("/pro", response_class=HTMLResponse)
def pagina_pro(request: Request) -> HTMLResponse:
    ses, resp = _gate(request, "/pro", "Pichangol Pro", "La membresía Pichangol Pro se activa desde la app.")
    if resp:
        return resp
    email = _email(ses)
    st = estado_pro(email)
    sim, precio = st["sim"], st["precio"]
    p_txt = _monto(sim, precio)
    if st["activa"]:
        sub = f"Eres Pro. Vigente hasta el {_fecha(st['hasta'])}."
    elif st["hasta"]:
        sub = f"Tu membresía venció el {_fecha(st['hasta'])}. Reactívala y vuelve al circuito."
    else:
        sub = "Sé parte del circuito: tu carnet oficial, tu ranking y tus estadísticas."
    hero = ("<section class='pr-hero'><div class='pr-hero-t'><span class='pr-corona'>👑</span><b>Pichangol Pro</b>"
            + ("<span class='pr-activo'>ACTIVO</span>" if st["activa"] else "") + "</div>"
            f"<p>{e(sub)}</p><div class='pr-precio'><b>{e(p_txt)}</b><span>/mes</span></div></section>")
    bens = "".join(f"<li><span class='pr-ic'>{ic}</span><div><b>{e(t)}</b><small>{e(d)}</small></div></li>" for ic, t, d in _BENEFICIOS)
    nota = (f"<div class='pr-nota'><span class='pr-bur'>👛</span><div>Se cobra de tu saldo Pichangol (la misma billetera de la app). "
            f"Tu saldo hoy: <b>{e(_monto(sim, st['saldo']))}</b>. "
            + ("Se renueva solo cada mes." if not st["cortesia"] else "")
            + " <a href='/mi-billetera#recargar'>Recargar saldo</a></div></div>")
    # Estado de la renovación (solo con membresía vigente).
    renov = ""
    if st["activa"] and st["cortesia"]:
        renov = ("<div class='pr-card'><b>🎁 Pro de cortesía</b><small>Te lo regaló Pichangol. No se renueva solo: al vencer, "
                 "puedes seguir pagando desde tu saldo.</small></div>")
    elif st["activa"]:
        if st["auto"]:
            renov = ("<div class='pr-card'><div class='pr-card-t'><b>🔄 Renovación automática activada</b>"
                     f"<small>El {e(_fecha(st['hasta']))} se cobrará {e(p_txt)} de tu saldo. Si no te alcanza, la membresía simplemente vence.</small></div>"
                     "<button type='button' class='btn sec' id='btnAuto' data-auto='0'>Cancelar renovación</button></div>")
        else:
            renov = ("<div class='pr-card warn'><div class='pr-card-t'><b>⏸️ Renovación automática cancelada</b>"
                     f"<small>Sigues siendo Pro hasta el {e(_fecha(st['hasta']))}; después no se cobrará nada.</small></div>"
                     "<button type='button' class='btn sec' id='btnAuto' data-auto='1'>Reactivar renovación</button></div>")
    boton = (f"Renovar 1 mes ({p_txt})" if st["activa"] else f"Activar por {p_txt}/mes")
    cfg = {"sim": sim, "precio": precio, "saldo": st["saldo"], "activa": st["activa"], "hasta": _fecha(st["hasta"])}
    cuerpo = (
        "<div class='pr-wrap'><a class='pr-back' href='/perfil'>‹ Perfil</a>" + hero
        + "<h2 class='pr-h2'>Qué incluye</h2><ul class='pr-ben'>" + bens + "</ul>"
        + "<p class='pr-link'><a href='/pro/planes'>Compara Gratis vs Pro ›</a></p>"
        + renov + nota
        + f"<button type='button' class='btn pr-cta' id='btnPro'>{e(boton)}</button>"
        + "</div>"
        + f"<style>{CSS}</style><script>window.__pro={json.dumps(cfg, ensure_ascii=False)};{JS_PRO}</script>")
    return ui.shell("Pichangol Pro", cuerpo, sesion=ses, titulo_tab="Pichangol Pro",
                    desc="Membresía Pichangol Pro: carnet oficial, ranking y retos sin límite.")


@router.post("/web/pro/suscribir")
def suscribir_pro(request: Request) -> JSONResponse:
    """= `AppState.suscribirPro` → `POST /pagos/pro/suscribir` (misma función)."""
    try:
        email = _ses_json(request)
    except HTTPException:
        return _err("Inicia sesión para activar Pro.", 401, error="sesion_requerida")
    st = estado_pro(email)
    r = _pagos.post_pro_suscribir(_pagos.ProSuscribirReq(email=email, pais=st["iso"]))
    if r.get("ok"):
        print(f"[pro] web {email} pagó {st['sim']} {st['precio']:.2f} hasta {r.get('hasta')}", flush=True)
        return JSONResponse({"ok": True, "hasta": _fecha(r.get("hasta")), "saldo": r.get("saldo_soles")})
    if r.get("falta_saldo"):
        return JSONResponse({"ok": False, "falta_saldo": True, "requerido": r.get("requerido_soles"), "saldo": (r.get("saldo_centimos") or 0) / 100.0})
    return JSONResponse({"ok": False, "mensaje": "No se pudo activar. Reintenta."})


@router.post("/web/pro/renovacion")
def renovacion_pro(request: Request, body: dict = Body(default_factory=dict)) -> JSONResponse:
    """Cancela / reactiva la renovación automática (`auto_renovar` en la
    membresía, que `procesar_renovaciones_pro` respeta). Solo con Pro vigente
    y pagado (la cortesía nunca se renueva sola)."""
    try:
        email = _ses_json(request)
    except HTTPException:
        return _err("Inicia sesión.", 401, error="sesion_requerida")
    m = stores.membresias_pro.get(email)
    activa, _h = _pagos._pro_estado(email)
    if not m or not activa:
        return _err("No tienes una membresía Pro vigente.", 409)
    if m.get("cortesia"):
        return _err("El Pro de cortesía no se renueva solo.", 409)
    auto = bool((body or {}).get("auto"))
    m["auto_renovar"] = auto
    print(f"[pro] {email} renovación automática {'ON' if auto else 'OFF'}", flush=True)
    return JSONResponse({"ok": True, "auto": auto})


@router.get("/pro/planes", response_class=HTMLResponse)
def pagina_planes_pro(request: Request) -> HTMLResponse:
    ses = sesion.de_request(request)
    email = _email(ses) if ses else ""
    iso = "PE"
    if email:
        from web.jugador_billetera import pais_billetera
        iso, _ = pais_billetera(email)
    from web.jugador_billetera import PAISES
    sim = (PAISES.get(iso) or PAISES["PE"])["moneda"]
    precio = _pagos._pro_precio_centimos(iso) / 100.0
    try:
        lim = int(stores.cfg("retos_free_limite_semana") or 3)
    except (TypeError, ValueError):
        lim = 3
    si, no = "<span class='pr-si'>✓</span>", "<span class='pr-no'>—</span>"
    filas = [("🏟️", "Reservar canchas y pagar en línea", si, si),
             ("🎓", "Matricularte en academias", si, si),
             ("⚔️", "Retos en la liga", f"{lim} por semana", "Sin límite"),
             ("👑", "Insignia PRO en el ranking y carnet oficial", no, si),
             ("🏆", "Crear y administrar tus campeonatos", no, si),
             ("🛒", "Mi bodega (caja y carta digital del local)", no, si)]
    if config.WEB_MANUAL_REQUIERE_PRO:
        filas.append(("📝", "Reserva manual y bloqueo de horas (dueños)", no, si))
    tabla = "".join(f"<div class='pr-fila'><span class='pr-f-t'><span>{ic}</span>{e(t)}</span><span class='pr-c'>{a}</span><span class='pr-c pro'>{b}</span></div>"
                    for ic, t, a, b in filas)
    cuerpo = ("<div class='pr-wrap'><a class='pr-back' href='/pro'>‹ Pichangol Pro</a><h1 class='pr-h1'>Gratis vs Pro</h1>"
              f"<p class='sub'>Pro cuesta {e(_monto(sim, precio))} al mes y se cobra de tu saldo Pichangol.</p>"
              "<div class='pr-tabla'><div class='pr-fila cab'><span></span><span class='pr-c'>Gratis</span><span class='pr-c pro'>👑 Pro</span></div>"
              + tabla + "</div><a class='btn pr-cta' href='/pro'>Quiero ser Pro</a></div>"
              + f"<style>{CSS}</style>")
    return ui.shell("Gratis vs Pro", cuerpo, sesion=ses, titulo_tab="Planes · Pichangol Pro")


# ══════════════════════════ TARJETAS GUARDADAS ═════════════════════════════════

def _tarjetas(email: str) -> list[dict]:
    return list(_pagos.get_metodos(email).get("metodos") or [])


@router.get("/cuenta/tarjetas", response_class=HTMLResponse)
def pagina_tarjetas(request: Request) -> HTMLResponse:
    ses, resp = _gate(request, "/cuenta/tarjetas", "Métodos de pago", "Tus tarjetas guardadas se administran desde la app.")
    if resp:
        return resp
    email = _email(ses)
    lst = _tarjetas(email)
    filas = ""
    for m in lst:
        nom, col = _MARCA.get(str(m.get("marca") or "").strip().lower(), (str(m.get("marca") or "Tarjeta").title(), "#0A1B3D"))
        filas += (f"<div class='pr-tj' data-id='{e(m.get('id'))}'><span class='pr-tj-ic' style='background:{col}'>💳</span>"
                  f"<div class='pr-tj-t'><b>{e(nom)} ···· {e(m.get('ultimos4') or '')}</b><small>Guardada para 1 toque</small></div>"
                  "<button type='button' class='btn sec pr-del'>Eliminar</button></div>")
    vacio = ("<div class='pr-vacio'><span>💳</span><b>Aún no tienes tarjetas guardadas</b>"
             "<small>Guárdala una vez y paga en un toque desde la app.</small></div>")
    disponible = bool(config.CULQI_PUBLIC_KEY) and culqi.disponible()
    agregar = ("<button type='button' class='btn pr-cta' id='btnTarjeta'>＋ Agregar tarjeta</button>" if disponible else
               "<p class='aviso warn'>El registro de tarjetas no está disponible por ahora. Inténtalo más tarde.</p>")
    cuerpo = ("<div class='pr-wrap'><a class='pr-back' href='/mi-billetera'>‹ Mi billetera</a><h1 class='pr-h1'>Métodos de pago</h1>"
              "<p class='sub'>Las tarjetas que guardes aquí son las mismas de la app (pago en un toque, débito automático de academias).</p>"
              + (f"<div class='pr-lista' id='tjs'>{filas}</div>" if filas else vacio) + agregar
              + "<p class='pr-seg'>🔒 Tus tarjetas se guardan de forma segura en Culqi. Pichangol nunca ve ni guarda el número completo: "
                "solo la marca y los últimos 4 dígitos.</p></div>"
              + f"<style>{CSS}</style><script>window.__tj={json.dumps({'pk': config.CULQI_PUBLIC_KEY if disponible else ''})};{JS_TARJETAS}</script>")
    head = "<script src='https://checkout.culqi.com/js/v4'></script>" if disponible else ""
    return ui.shell("Métodos de pago", cuerpo, sesion=ses, titulo_tab="Métodos de pago", extra_head=head)


@router.post("/web/tarjetas/agregar")
def agregar_tarjeta(request: Request, body: dict = Body(default_factory=dict)) -> JSONResponse:
    """= `metodos_pago_screen._guardar` → `POST /pagos/metodos` (`post_metodo`):
    crea/reusa el customer de Culqi y convierte el token en `crd_`."""
    ses = sesion.de_request(request)
    email = _email(ses) if ses else ""
    if not email:
        return _err("Inicia sesión.", 401, error="sesion_requerida")
    token = str((body or {}).get("token") or "").strip()
    if not re.fullmatch(r"tkn_[A-Za-z0-9_\-]{4,80}", token):
        return _err("No recibimos la tarjeta. Vuelve a intentarlo.")
    if len(_tarjetas(email)) >= 10:
        return _err("Ya tienes 10 tarjetas guardadas. Elimina alguna para agregar otra.", 409)
    nombre, apellido = culqi.partir_nombre(str(ses.get("nombre") or ""))
    try:
        r = _pagos.post_metodo(_pagos.MetodoReq(token=token, user_id=email, email=email, nombre=nombre, apellido=apellido,
                                                telefono=datos.celular_de_perfil(email) or ""))
    except HTTPException:
        return _err("El registro de tarjetas no está disponible por ahora.", 503)
    if not r.get("ok"):
        return _err(r.get("merchant") or "Culqi no aceptó la tarjeta. Revisa los datos o usa otra.", 400, error=r.get("error"))
    print(f"[tarjetas] web {email} guardó {r['metodo'].get('marca')} {r['metodo'].get('ultimos4')}", flush=True)
    return JSONResponse({"ok": True, "metodo": r["metodo"]})


@router.post("/web/tarjetas/eliminar")
def eliminar_tarjeta(request: Request, body: dict = Body(default_factory=dict)) -> JSONResponse:
    """= `DELETE /pagos/metodos/{user_id}/{card_id}` (`del_metodo`), solo sobre
    las tarjetas del correo de la sesión."""
    ses = sesion.de_request(request)
    email = _email(ses) if ses else ""
    if not email:
        return _err("Inicia sesión.", 401, error="sesion_requerida")
    cid = str((body or {}).get("id") or "")
    if not any(str(m.get("id")) == cid for m in _tarjetas(email)):
        return _err("Esa tarjeta no es tuya.", 404)
    _pagos.del_metodo(email, cid)
    return JSONResponse({"ok": True})


# ══════════════════════════ BÚSQUEDA GUIADA / ASISTENTE ════════════════════════

_DEPORTES_BUSQ = [("futbol", "Fútbol", "⚽"), ("tenis", "Tenis", "🎾"), ("padel", "Pádel", "🏓"), ("futsal", "Futsal", "🥅"),
                  ("pickleball", "Pickleball", "🥒"), ("voley", "Vóley", "🏐"), ("basquet", "Básquet", "🏀")]
_DIAS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]


def _km(a_lat, a_lng, b_lat, b_lng) -> float | None:
    try:
        la1, lo1, la2, lo2 = map(float, (a_lat, a_lng, b_lat, b_lng))
    except (TypeError, ValueError):
        return None
    dlat, dlng = radians(la2 - la1), radians(lo2 - lo1)
    h = sin(dlat / 2) ** 2 + cos(radians(la1)) * cos(radians(la2)) * sin(dlng / 2) ** 2
    return 2 * 6371 * asin(sqrt(h))


def turnos_libres(c: dict, fecha: str, ocup: set) -> list[str]:
    """Inicios de turno LIBRES ese día (sin los que ya pasaron), con la misma
    regla de slots, madrugada y fecha real que la ficha."""
    from web.router import _pais_de
    ap, ci, paso = c["hora_apertura"], c["hora_cierre"], int(c.get("duracion_slot_min") or 60)
    ahora = horarios.ahora_local(_pais_de(c))
    desde = ahora.hour * 60 + ahora.minute + 1 if fecha == ahora.date().isoformat() else None
    return [s for s in horarios.slots(ap, ci, paso, desde) if (horarios.fecha_real(fecha, ap, ci, s), s) not in ocup]


def sugerencias(deporte: str, fecha: str, hora: str, zona: str, orden: str, lat=None, lng=None, limite: int = 12) -> list[dict]:
    """= `BusquedaLocal.recomendar`: canchas RESERVABLES del deporte con turno
    libre (a esa hora si se eligió), en la zona si se eligió, ordenadas por
    cercanía (o precio si "barato"). Una por local (la más barata que sirve)."""
    from web.router import _deportes_de, _hora_libre, _moneda_de, _zona
    todas = [c for c in datos.canchas_publicas() if datos.reservable(c)]
    if deporte:
        todas = [c for c in todas if deporte in _deportes_de(c)]
    if zona:
        z = zona.strip().lower()
        todas = [c for c in todas if z in _zona(c).lower() or z in str(c.get("direccion") or "").lower()]
    if not todas:
        return []
    d = date.fromisoformat(fecha)
    ocup = datos.ocupados_varias([c["id"] for c in todas], [fecha, (d + timedelta(days=1)).isoformat()])
    out: dict[str, dict] = {}
    for c in todas:
        oc = ocup.get(c["id"], set())
        libres = turnos_libres(c, fecha, oc)
        if hora:
            if not _hora_libre(c, fecha, hora, oc):
                continue
        elif not libres:
            continue
        monto, unidad = horarios.precio_publico(c)
        sim, _iso = _moneda_de(c)
        km = _km(lat, lng, c.get("lat"), c.get("lng")) if lat is not None and lng is not None else None
        if km is not None and km > 50:  # `BusquedaLocal._radioKm`: más lejos no es "de tu zona"
            continue
        it = {"c": c, "monto": monto, "unidad": unidad, "sim": sim, "km": km, "libres": libres,
              "equiv": float(c.get("precio_hora") or monto)}
        k = (c.get("club") or "").strip().lower() or f"id:{c['id']}"
        if k not in out or it["equiv"] < out[k]["equiv"]:
            out[k] = it
    lst = list(out.values())
    if orden == "barato":
        lst.sort(key=lambda x: (x["equiv"], x["km"] if x["km"] is not None else 9e9))
    else:
        lst.sort(key=lambda x: (x["km"] if x["km"] is not None else 9e9, x["equiv"]))
    return lst[:limite]


def _chip_radio(nombre: str, valor: str, texto: str, sel: bool, extra: str = "") -> str:
    return (f"<label class='chip pr-rc{' sel' if sel else ''}'><input type='radio' name='{nombre}' value='{e(valor)}'"
            f"{' checked' if sel else ''}{extra}>{texto}</label>")


@router.get("/buscar", response_class=HTMLResponse)
def pagina_buscar(request: Request, deporte: str = "", fecha: str = "", hora: str = "", zona: str = "",
                  orden: str = "", lat: str = "", lng: str = "", ir: str = "") -> HTMLResponse:
    from web.router import _zona, _zonas_sugeridas, _deporte
    ses = sesion.de_request(request)
    hoy = horarios.ahora_local("PE").date()
    try:
        f = date.fromisoformat(fecha) if fecha else hoy
    except ValueError:
        f = hoy
    if not (hoy <= f <= hoy + timedelta(days=30)):
        f = hoy
    fecha = f.isoformat()
    deporte = deporte if deporte in {k for k, _n, _i in _DEPORTES_BUSQ} else ""
    hora = hora if re.fullmatch(r"([01]\d|2[0-3]):00", hora or "") else ""
    orden = "barato" if orden == "barato" else ""
    zona = (zona or "").strip()[:60]
    cerca = zona == "__cerca"
    try:
        la, lo = (float(lat), float(lng)) if cerca and lat and lng else (None, None)
    except ValueError:
        la, lo = None, None
    publicas = [c for c in datos.canchas_publicas() if datos.reservable(c)]
    zonas = _zonas_sugeridas(publicas, 8)
    deps_con = {d for c in publicas for d in ([str(x).lower() for x in (c.get("deportes") or [])] + [str(c.get("deporte") or "").lower()])}
    # ── Paso 1: ¿Dónde?
    z_chips = (_chip_radio("zona", "", "🌎 Cualquier zona", not zona)
               + _chip_radio("zona", "__cerca", "📍 Cerca de ti", cerca)
               + "".join(_chip_radio("zona", z, f"{e(z)} <small>{n}</small>", zona.lower() == z.lower()) for z, n in zonas))
    d_chips = "".join(_chip_radio("deporte", k, f"{ic} {e(n)}", deporte == k)
                      for k, n, ic in _DEPORTES_BUSQ if k in deps_con or deporte == k or not publicas)
    dias = ""
    for i in range(14):
        di = hoy + timedelta(days=i)
        et = "Hoy" if i == 0 else ("Mañana" if i == 1 else f"{_DIAS[di.weekday()]} {di.day}")
        dias += _chip_radio("fecha", di.isoformat(), e(et), di == f)
    horas = _chip_radio("hora", "", "Cualquier hora", not hora) + "".join(
        _chip_radio("hora", f"{h:02d}:00", f"{h:02d}:00", hora == f"{h:02d}:00") for h in range(6, 24))
    o_chips = _chip_radio("orden", "", "📍 Lo más cerca", not orden) + _chip_radio("orden", "barato", "💸 Lo más barato", orden == "barato")
    form = (
        "<form class='pr-busq' id='fBusq' method='get' action='/buscar'><input type='hidden' name='ir' value='1'>"
        f"<input type='hidden' name='lat' id='bLat' value='{e(lat)}'><input type='hidden' name='lng' id='bLng' value='{e(lng)}'>"
        f"<section class='pr-paso'><h2>¿Dónde juegas?</h2><div class='chips pr-scroll'>{z_chips}</div></section>"
        f"<section class='pr-paso'><h2>¿Qué deporte?</h2><div class='chips'>{d_chips}</div></section>"
        f"<section class='pr-paso'><h2>¿Cuándo?</h2><div class='chips pr-scroll'>{dias}</div>"
        f"<h3>Hora</h3><div class='chips pr-scroll'>{horas}</div></section>"
        f"<section class='pr-paso'><h2>¿Qué prefieres?</h2><div class='chips'>{o_chips}</div></section>"
        "<div class='pr-pie'><a class='pr-limpiar' href='/buscar'>Limpiar</a>"
        "<button class='btn pr-buscar' type='submit'>🔎 Buscar canchas</button></div></form>")
    # ── Resultados (como las tarjetas del asistente)
    res = ""
    if ir:
        lst = sugerencias(deporte, fecha, hora, "" if cerca else zona, orden, la, lo)
        explorar = "/?" + urlencode({k: v for k, v in (("deporte", deporte), ("fecha", fecha), ("hora", hora)) if v})
        dep_txt = _deporte(deporte)[0].lower() if deporte else "canchas"
        cuando = horarios.etiqueta_dia(fecha, hoy) + (f" a las {hora}" if hora else "")
        if lst:
            cards = ""
            for it in lst:
                c = it["c"]
                q = {"fecha": fecha}
                if hora:
                    q["hora"] = hora
                motivo = ("💸 Buen precio" if orden == "barato" else
                          (f"📍 A {it['km']:.1f} km" if it["km"] is not None else ("⭐ Verificada")))
                prox = "" if hora else (" · libre desde " + it["libres"][0] if it["libres"] else "")
                foto = next((u for u in [c.get("foto_url")] + list(c.get("fotos") or []) if str(u or "").startswith("http")), "")
                img = (f"<img src='{e(foto)}' alt='' loading='lazy'>" if foto else f"<span>{_deporte(c.get('deporte'))[1]}</span>")
                cards += (f"<a class='pr-sug' href='{e('/reservar/' + quote(str(c['id'])) + '?' + urlencode(q))}'><div class='pr-sug-f'>{img}</div>"
                          f"<div class='pr-sug-t'><b>{e(c.get('club') or c.get('nombre'))}</b>"
                          f"<small>{e(c.get('nombre') or '')}{' · ' + e(_zona(c)) if _zona(c) else ''}</small>"
                          f"<small>{e(motivo)}{e(prox)}</small>"
                          f"<span class='pr-sug-p'><b>{e(it['sim'])} {it['monto']:.2f}</b> {e(it['unidad'])}</span></div>"
                          "<span class='pr-sug-b'>Ver horarios ›</span></a>")
            res = (f"<section class='pr-res' id='resultados'><div class='pr-bot'>🤖 Te encontré {len(lst)} opcion{'es' if len(lst) != 1 else ''} de "
                   f"{e(dep_txt)} para {e(cuando)}{' cerca de ti' if cerca and la is not None else (' en ' + e(zona) if zona and not cerca else '')}.</div>"
                   f"<div class='pr-sugs'>{cards}</div>"
                   f"<a class='btn sec pr-cta' href='{e(explorar)}'>Ver todas en el explorador</a></section>")
        else:
            res = (f"<section class='pr-res' id='resultados'><div class='pr-bot'>😕 No encontré {e(dep_txt)} con turno libre para {e(cuando)}"
                   f"{' en ' + e(zona) if zona and not cerca else ''}. Prueba otra hora, otro día u otra zona.</div>"
                   f"<a class='btn sec pr-cta' href='{e(explorar)}'>Abrir el explorador</a></section>")
    cuerpo = ("<div class='pr-wrap'><h1 class='pr-h1'>¿Qué quieres jugar?</h1>"
              "<p class='sub'>Elige y te busco cancha con turno libre al toque.</p>" + form + res + "</div>"
              + f"<style>{CSS}</style><script>{JS_BUSCAR}</script>")
    return ui.shell("Busca tu cancha", cuerpo, sesion=ses, titulo_tab="Busca tu cancha",
                    desc="Búsqueda guiada: deporte, zona, día y hora; canchas con turno libre para reservar.")


# ══════════════════════════ RECORDATORIOS (dueño) ══════════════════════════════

def _tel_wa(tel: str, c: dict) -> str:
    from web.router import _pais_de
    d = re.sub(r"\D", "", tel or "")
    if not d:
        return ""
    return d if len(d) > 10 else catalogos.TEL_PREFIJO.get(_pais_de(c), "51") + d


def recordados_por_app(dueno: str, ids: list[str]) -> set[str]:
    """Reservas ya recordadas por el CHAT: el app (y la web) guardan el mensaje
    con id `msg_<µs>_<reservaId>` → se leen de la nube."""
    if not pg.habilitado or not ids:
        return set()
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id FROM pichangol_mensajes WHERE tipo = 'cancha' AND lower(ref_id) = %s "
                        "AND creado > now() - interval '4 days' AND id LIKE 'msg\\_%%'", (dueno.lower(),))
            sufijos = {str(r[0]).split("_", 2)[2] for r in cur.fetchall() if str(r[0]).count("_") >= 2}
    except Exception:  # noqa: BLE001
        return set()
    return {i for i in ids if i in sufijos}


def _marcas(dueno: str) -> dict:
    from web.anfitrion_negocio import _negocio
    return _negocio(dueno)["recordados"]


def _reservas_dia(canchas: list[dict], iso: str) -> list[dict]:
    from web.anfitrion_negocio import es_noshow, reservas_dueno
    return [r for r in reservas_dueno([c["id"] for c in canchas], iso, iso) if not es_noshow(r)]


def _grupos(filas: list[dict]) -> list[list[dict]]:
    """Una tarjeta por reserva (los turnos de un mismo bloque, juntos)."""
    orden, mapa = [], {}
    for r in filas:
        k = r.get("grupo_reserva_id") or r["id"]
        if k not in mapa:
            orden.append(k)
            mapa[k] = []
        mapa[k].append(r)
    return [mapa[k] for k in orden]


def _texto_rec(r: dict, dia: str, c: dict | None) -> str:
    """= `RecordarReservasScreen._texto`."""
    lugar = "la cancha" if not c else (f"{c['club']} · {c['nombre']}" if c.get("club") else c.get("nombre") or "la cancha")
    jug = (r.get("jugador") or "").strip()
    return (f"Hola {jug + ' ' if jug else ''}🎾 Te recuerdo tu reserva {dia} {r.get('hora_inicio')} en {lugar}. "
            "¡Te esperamos! Si no puedes venir, avísame por aquí.")


@router.get("/anfitrion/recordatorios", response_class=HTMLResponse)
def pagina_recordatorios(request: Request, dia: str = "manana") -> HTMLResponse:
    from web.anfitrion import _contexto
    from web.anfitrion_negocio import _hoy_de, _pagina
    ses, canchas, resp = _contexto(request, "/anfitrion/recordatorios")
    if resp is not None:
        return resp
    manana = dia != "hoy"
    base = _hoy_de(canchas).date() + timedelta(days=1 if manana else 0)
    iso = base.isoformat()
    dlab = "mañana" if manana else "hoy"
    por_id = {c["id"]: c for c in canchas}
    filas = _reservas_dia(canchas, iso)
    app_ok = recordados_por_app(ses["email"], [r["id"] for r in filas])
    marcas = _marcas(ses["email"])
    items, pend_app, pend_wa = "", 0, 0
    fichas = {}
    for g in _grupos(filas):
        r = g[0]
        c = por_id.get(r.get("cancha_id"))
        ids = [x["id"] for x in g]
        ya = any(i in app_ok or f"res:{i}" in marcas for i in ids)
        usuario = (r.get("usuario") or "").strip()
        tel = _tel_wa(r.get("telefono") or "", c or {})
        canal = "app" if usuario else ("wa" if tel else "")
        txt = _texto_rec(r, dlab, c)
        fichas[r["id"]] = {"ids": ids, "canal": canal}
        if not ya and canal == "app":
            pend_app += 1
        if not ya and canal == "wa":
            pend_wa += 1
        fin = g[-1].get("hora_fin") or ""
        lugar = (c.get("club") + " · " if c and c.get("club") else "") + (c.get("nombre") if c else "Cancha")
        if ya:
            acc = "<span class='pill ok'>✓ Recordado</span>"
        elif canal == "app":
            acc = "<button type='button' class='btn mini-b' data-acc='app'>Recordar 📲</button>"
        elif canal == "wa":
            acc = (f"<a class='btn mini-b pr-wa' data-acc='wa' target='_blank' rel='noopener' "
                   f"href='{e(ui.enlace_whatsapp(txt, tel))}'>WhatsApp</a>")
        else:
            acc = "<span class='pill'>Sin contacto</span>"
        ini = (r.get("jugador") or "?").strip()[:1].upper() or "?"
        items += (f"<div class='ng-fila' data-res='{e(r['id'])}'><span class='pr-ini'>{e(ini)}</span>"
                  f"<div class='ng-fila-t'><b>{e(r.get('jugador') or 'Cliente')}</b>"
                  f"<small>{e(r.get('hora_inicio') or '')}{'–' + e(fin) if fin else ''} · {e(lugar)}"
                  f"{' · 📲 tiene la app' if canal == 'app' else (' · WhatsApp' if canal == 'wa' else '')}</small></div>{acc}</div>")
    chips = (f"<div class='chips' style='margin-top:12px'><a class='chip{'' if manana else ' sel'}' href='?dia=hoy'>Hoy</a>"
             f"<a class='chip{' sel' if manana else ''}' href='?dia=manana'>Mañana</a></div>")
    banner = ""
    if pend_app:
        banner = (f"<div class='ng-rec'><b>🔔 {pend_app} jugador{'es' if pend_app != 1 else ''} con la app por recordar</b>"
                  "<small>Les llega por el chat del local con notificación.</small>"
                  "<button type='button' class='btn' id='recTodos'>Recordar a todos</button></div>")
    elif pend_wa:
        banner = (f"<div class='ng-rec'><b>📱 {pend_wa} por recordar por WhatsApp</b><small>No tienen la app: toca “WhatsApp” en cada uno.</small></div>")
    cuerpo = ("<h1 class='anf-hola'>Recordar reservas</h1><p class='sub'>Evita que te dejen plantada la cancha: recuérdales su reserva "
              f"de {dlab}. A quien tiene la app le llega por el chat; a los demás, por WhatsApp.</p>" + chips + banner
              + (f"<div class='ng-lista' id='recLista'>{items}</div>" if items else
                 f"<div class='anf-vacio' style='margin-top:16px'>No tienes reservas para {dlab}.</div>")
              + f"<style>{CSS}</style><script>window.__rec={json.dumps({'fecha': iso, 'fichas': fichas})};{JS_RECORDAR}</script>")
    return _pagina("Recordar reservas", cuerpo, ses, "")


def _validar_reservas(email: str, fecha: str, ids: list[str]):
    """(canchas, filas de esas reservas) SOLO si son de canchas del correo."""
    canchas = datos.canchas_de_dueno(email)
    try:
        date.fromisoformat(fecha)
    except ValueError:
        return canchas, []
    filas = [r for r in _reservas_dia(canchas, fecha) if r["id"] in set(ids)]
    return canchas, filas


@router.post("/anfitrion/recordatorios/enviar")
def enviar_recordatorios(request: Request, body: dict = Body(default_factory=dict)) -> JSONResponse:
    """Recordatorio por el CHAT del local (= `MensajesRepo.enviar` del app) a
    los jugadores con cuenta; los grupos se recuerdan una sola vez."""
    from web.jugador_liga import mi_nombre
    from web.jugador_mensajes import hilo_cancha, insertar_mensaje
    ses = sesion.de_request(request)
    if not ses:
        return _err("sesion_requerida", 401)
    email = _email(ses)
    fecha = str(body.get("fecha") or "")
    ids = [str(x) for x in (body.get("ids") or [])][:200]
    canchas, filas = _validar_reservas(email, fecha, ids)
    if not filas:
        return _err("Esas reservas no son de tus canchas.", 404)
    hoy = datetime.now(_LIMA).date()
    dlab = "hoy" if fecha == hoy.isoformat() else ("mañana" if fecha == (hoy + timedelta(days=1)).isoformat() else f"el {horarios.fecha_larga(fecha)}")
    por_id = {c["id"]: c for c in canchas}
    ya = recordados_por_app(email, [r["id"] for r in filas])
    nombre = mi_nombre(ses)
    enviados, vistos = 0, set()
    for r in filas:
        k = r.get("grupo_reserva_id") or r["id"]
        jug = (r.get("usuario") or "").strip().lower()
        if k in vistos or not jug or r["id"] in ya:
            continue
        vistos.add(k)
        fila = {"id": f"msg_{time.time_ns() // 1000}_{r['id']}", "hilo": hilo_cancha(email, jug), "tipo": "cancha",
                "ref_id": email, "cuenta_email": jug, "autor_email": email, "autor_nombre": nombre, "es_profe": True,
                "texto": _texto_rec(r, dlab, por_id.get(r.get("cancha_id")))}
        if insertar_mensaje(fila):
            enviados += 1
    if not enviados and vistos:
        return _err("No se pudo enviar por la app. Reintenta.", 503)
    return JSONResponse({"ok": True, "enviados": enviados})


@router.post("/anfitrion/recordatorios/marcar")
def marcar_recordatorio(request: Request, body: dict = Body(default_factory=dict)) -> JSONResponse:
    """Recordado por WhatsApp (lo abre el navegador): se anota en la nube."""
    ses = sesion.de_request(request)
    if not ses:
        return _err("sesion_requerida", 401)
    email = _email(ses)
    ids = [str(x) for x in (body.get("ids") or [])][:50]
    _c, filas = _validar_reservas(email, str(body.get("fecha") or ""), ids)
    if not filas:
        return _err("Esas reservas no son de tus canchas.", 404)
    m = _marcas(email)
    ahora = datetime.now(timezone.utc).isoformat()
    for r in filas:
        m[f"res:{r['id']}"] = ahora
    # Limpieza: las marcas de reservas viejas no se acumulan.
    corte = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    for k in [k for k, v in m.items() if k.startswith("res:") and str(v) < corte]:
        m.pop(k, None)
    return JSONResponse({"ok": True})


# ══════════════════════════ estilos y scripts ══════════════════════════════════

CSS = r"""
.pr-wrap{max-width:640px;margin:0 auto;padding:8px 0 40px;min-width:0}
.pr-back{display:inline-block;margin:6px 0 12px;color:var(--tenue);font-weight:700;text-decoration:none}
.pr-h1{font-size:26px;margin:4px 0 6px}.pr-h2{font-size:18px;margin:22px 0 10px}
.pr-hero{background:linear-gradient(135deg,#14463A,#1E5C4C);color:#fff;border-radius:22px;padding:22px}
.pr-hero-t{display:flex;align-items:center;gap:10px;font-size:22px}.pr-hero-t b{font-weight:900}
.pr-corona{font-size:28px}.pr-activo{margin-left:auto;background:#7CB518;color:#fff;border-radius:999px;padding:4px 11px;font-size:11px;font-weight:900}
.pr-hero p{margin:10px 0 0;color:rgba(255,255,255,.9);line-height:1.4}
.pr-precio{margin-top:14px;display:flex;align-items:flex-end;gap:4px}.pr-precio b{font-size:32px;font-weight:900}.pr-precio span{color:rgba(255,255,255,.75);padding-bottom:6px}
.pr-ben{list-style:none;margin:0;padding:0;display:grid;gap:12px}
.pr-ben li{display:flex;gap:12px;align-items:flex-start}.pr-ben b{display:block;font-size:15px}.pr-ben small{color:var(--tenue)}
.pr-ic{width:40px;height:40px;flex:none;border-radius:12px;background:#F4F1FF;display:grid;place-items:center;font-size:21px}
.pr-link a{font-weight:800;color:var(--esmeralda,#0B8A3E)}
.pr-card{display:flex;gap:12px;align-items:center;justify-content:space-between;flex-wrap:wrap;background:#fff;border:1px solid var(--trazo);border-radius:18px;padding:14px 16px;margin-top:16px;box-shadow:var(--sombra)}
.pr-card.warn{background:#FFF8EC;border-color:#F2C77E}.pr-card small{display:block;color:var(--tenue);margin-top:3px}.pr-card-t{flex:1 1 240px;min-width:0}
.pr-nota{display:flex;gap:10px;align-items:flex-start;background:#EEF7E3;color:#14463A;border-radius:14px;padding:12px;margin-top:16px;font-size:13.5px;line-height:1.4}
.pr-nota a{font-weight:800;color:#067A38}.pr-bur{width:32px;height:32px;flex:none;border-radius:50%;background:#7CB518;display:grid;place-items:center}
.btn.pr-cta{display:block;width:100%;margin-top:20px;padding:15px;font-size:16px;text-align:center;box-sizing:border-box}
.pr-tabla{border:1px solid var(--trazo);border-radius:18px;overflow:hidden;background:#fff;margin-top:14px}
.pr-fila{display:grid;grid-template-columns:minmax(0,1fr) 92px 92px;gap:8px;align-items:center;padding:12px 14px;border-top:1px solid var(--trazo)}
.pr-fila.cab{border-top:0;background:#F7F7F7;font-weight:800}.pr-f-t{display:flex;gap:8px;min-width:0;overflow-wrap:anywhere}
.pr-c{text-align:center;font-size:13.5px}.pr-c.pro{font-weight:800}.pr-si{color:#0B8A3E;font-weight:900;font-size:17px}.pr-no{color:#B0B0B0}
.pr-lista{display:grid;gap:10px;margin-top:14px}
.pr-tj{display:flex;gap:12px;align-items:center;background:#fff;border:1px solid var(--trazo);border-radius:16px;padding:12px 14px;box-shadow:var(--sombra)}
.pr-tj-ic{width:44px;height:30px;border-radius:7px;display:grid;place-items:center;flex:none}.pr-tj-t{flex:1;min-width:0}.pr-tj-t small{display:block;color:var(--tenue)}
.pr-vacio{text-align:center;padding:30px 12px;border:1px dashed var(--trazo);border-radius:18px;margin-top:14px}.pr-vacio span{font-size:40px;display:block}
.pr-vacio small{display:block;color:var(--tenue);margin-top:4px}.pr-seg{color:var(--tenue);font-size:12.5px;margin-top:14px;line-height:1.4}
.pr-paso{background:#fff;border:1px solid var(--trazo);border-radius:20px;padding:16px 16px 10px;margin-top:14px;box-shadow:var(--sombra);min-width:0}
.pr-paso h2{font-size:17px;margin:0 0 10px}.pr-paso h3{font-size:13px;color:var(--tenue);margin:12px 0 8px}
.pr-scroll{flex-wrap:nowrap;overflow-x:auto;padding-bottom:6px;scrollbar-width:thin}.pr-scroll .chip{flex:none}
.pr-rc{cursor:pointer;user-select:none;position:relative}.pr-scroll{position:relative}.pr-rc input{position:absolute;opacity:0;width:1px;height:1px;pointer-events:none}.pr-rc small{color:var(--tenue);margin-left:3px}
.pr-rc.sel,.pr-rc:has(input:checked){background:#EBEBEB;border-color:#D8D8D8;font-weight:800}
.pr-pie{position:sticky;bottom:0;display:flex;align-items:center;justify-content:space-between;gap:12px;background:#fff;padding:12px 0 calc(12px + env(safe-area-inset-bottom));margin-top:14px;border-top:1px solid var(--trazo)}
.pr-limpiar{font-weight:800;color:var(--noche);text-decoration:underline}.btn.pr-buscar{padding:13px 22px;font-size:15px}
.pr-res{margin-top:22px}.pr-bot{background:#F4F7FA;border-radius:18px 18px 18px 4px;padding:12px 14px;font-weight:600;line-height:1.4}
.pr-sugs{display:grid;gap:12px;margin-top:12px}
.pr-sug{display:flex;gap:12px;align-items:center;background:#fff;border:1px solid var(--trazo);border-radius:18px;padding:10px;text-decoration:none;color:inherit;box-shadow:var(--sombra);min-width:0}
.pr-sug-f{width:84px;height:84px;flex:none;border-radius:14px;overflow:hidden;background:#EEF3EE;display:grid;place-items:center;font-size:32px}
.pr-sug-f img{width:100%;height:100%;object-fit:cover}.pr-sug-t{flex:1;min-width:0}.pr-sug-t b{display:block;overflow-wrap:anywhere}
.pr-sug-t small{display:block;color:var(--tenue);font-size:12.5px;overflow-wrap:anywhere}.pr-sug-p{display:block;margin-top:4px;font-size:13px}
.pr-sug-b{flex:none;font-weight:800;color:#0B8A3E;font-size:13px}
.pr-ini{width:38px;height:38px;border-radius:50%;background:#0F8F7E;color:#fff;display:grid;place-items:center;font-weight:800;flex:none}
@media (max-width:600px){.pr-fila{grid-template-columns:minmax(0,1fr) 64px 70px;padding:11px 10px}.pr-sug-b{display:none}.pr-sug-f{width:72px;height:72px}}
"""

JS_PRO = r"""
(function(){
  var C = window.__pro || {}, $ = function(id){ return document.getElementById(id); };
  function fmt(n){ n = Number(n || 0); return C.sim + ' ' + (n % 1 === 0 ? n.toFixed(0) : n.toFixed(2)); }
  function post(url, body){ return fetch(url, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body || {})}).then(function(r){ return r.json(); }); }
  var b = $('btnPro');
  if(b) b.addEventListener('click', function(){
    pcgConfirmar({titulo: C.activa ? 'Renovar Pichangol Pro' : 'Activar Pichangol Pro', icono: '👑',
                  mensaje: 'Se debitará ' + fmt(C.precio) + ' de tu saldo Pichangol por 1 mes' + (C.activa ? ' (se suma a tu vigencia actual).' : '.'),
                  confirmar: 'Pagar ' + fmt(C.precio), cancelar: 'Ahora no'}).then(function(ok){
      if(!ok) return;
      pcgCargando('Activando…');
      post('/web/pro/suscribir').then(function(j){
        pcgCargando(false);
        if(j.ok){ pcgAvisar({titulo: '¡Ya eres Pro! 🎾', icono: '👑', confirmar: 'Genial', mensaje: 'Tu membresía Pichangol Pro está activa hasta el ' + j.hasta + '. Se renueva sola desde tu saldo.'}).then(function(){ pcgRecargar('Actualizando…'); }); return; }
        if(j.falta_saldo){
          pcgConfirmar({titulo: 'Te falta saldo', icono: '👛', confirmar: 'Recargar saldo', cancelar: 'Ahora no',
                        mensaje: 'Pichangol Pro se cobra de tu saldo (' + fmt(j.requerido || C.precio) + '/mes). Tu saldo es ' + fmt(j.saldo) + '. Recarga y actívalo al toque.'})
            .then(function(ok){ if(ok) pcgIr('/mi-billetera#recargar', 'Abriendo tu billetera…'); });
          return;
        }
        pcgAvisar({titulo: 'No se pudo', icono: '⚠️', mensaje: j.mensaje || 'No se pudo activar. Reintenta.'});
      }).catch(function(){ pcgCargando(false); pcgAvisar({titulo: 'Sin conexión', icono: '⚠️', mensaje: 'Revisa tu conexión y reintenta.'}); });
    });
  });
  var a = $('btnAuto');
  if(a) a.addEventListener('click', function(){
    var on = a.dataset.auto === '1';
    pcgConfirmar(on ? {titulo: 'Reactivar la renovación', icono: '🔄', confirmar: 'Reactivar', cancelar: 'Volver',
                       mensaje: 'Al vencer, se cobrará ' + fmt(C.precio) + ' de tu saldo para seguir siendo Pro.'}
                    : {titulo: '¿Cancelar la renovación automática?', icono: '⏸️', destructivo: true, confirmar: 'Cancelar renovación', cancelar: 'Seguir renovando',
                       mensaje: 'Seguirás siendo Pro hasta el ' + C.hasta + '. Después no se cobrará nada y perderás tu insignia y los retos sin límite.'})
      .then(function(ok){
        if(!ok) return;
        pcgCargando('Guardando…', {demora: 250});
        post('/web/pro/renovacion', {auto: on}).then(function(j){
          if(j.ok) pcgRecargar('Actualizando…');
          else { pcgCargando(false); pcgAvisar({titulo: 'No se pudo', icono: '⚠️', mensaje: j.mensaje || 'Reintenta.'}); }
        }).catch(function(){ pcgCargando(false); pcgAvisar({titulo: 'Sin conexión', icono: '⚠️', mensaje: 'Reintenta.'}); });
      });
  });
})();
"""

JS_TARJETAS = r"""
(function(){
  var C = window.__tj || {}, $ = function(id){ return document.getElementById(id); };
  function post(url, body){ return fetch(url, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body || {})}).then(function(r){ return r.json(); }); }
  document.querySelectorAll('.pr-tj .pr-del').forEach(function(b){
    b.addEventListener('click', function(){
      var fila = b.closest('.pr-tj'), nom = fila.querySelector('b').textContent;
      pcgConfirmar({titulo: '¿Eliminar esta tarjeta?', icono: '💳', destructivo: true, confirmar: 'Eliminar', cancelar: 'Cancelar',
                    mensaje: nom + ' dejará de estar disponible para pagar en un toque (también en la app).'}).then(function(ok){
        if(!ok) return;
        pcgCargando('Eliminando…', {demora: 250});
        post('/web/tarjetas/eliminar', {id: fila.dataset.id}).then(function(j){
          if(j.ok) pcgRecargar('Actualizando…');
          else { pcgCargando(false); pcgAvisar({titulo: 'No se pudo', icono: '⚠️', mensaje: j.mensaje || 'Reintenta.'}); }
        }).catch(function(){ pcgCargando(false); pcgAvisar({titulo: 'Sin conexión', icono: '⚠️', mensaje: 'Reintenta.'}); });
      });
    });
  });
  var b = $('btnTarjeta');
  if(b) b.addEventListener('click', function(){
    if(!C.pk || !window.Culqi){ pcgAvisar({titulo: 'No disponible', icono: '⚠️', mensaje: 'El registro de tarjetas no está disponible por ahora.'}); return; }
    pcgConfirmar({titulo: 'Agregar tarjeta', icono: '💳', confirmar: 'Continuar', cancelar: 'Volver',
                  mensaje: 'Culqi te pedirá los datos de tu tarjeta. NO se hace ningún cobro: el monto de S/ 1.00 que muestra Culqi es solo de validación. La tarjeta queda guardada en Culqi para pagar en un toque.'})
      .then(function(ok){
        if(!ok) return;
        Culqi.publicKey = C.pk;
        Culqi.settings({title: 'Guardar tarjeta', currency: 'PEN', amount: 100});
        Culqi.options({lang: 'es', installments: false,
          paymentMethods: {tarjeta: true, yape: false, bancaMovil: false, agente: false, billetera: false, cuotealo: false},
          style: {logo: '', bannerColor: '#0F1B2D', buttonBackground: '#0E8F67', buttonText: 'Guardar tarjeta', buttonTextColor: '#FFFFFF'}});
        window.culqi = function(){
          if(Culqi.token){
            var token = Culqi.token.id;
            Culqi.close(); pcgCargando('Guardando tu tarjeta…');
            post('/web/tarjetas/agregar', {token: token}).then(function(j){
              pcgCargando(false);
              if(j.ok) pcgAvisar({titulo: 'Tarjeta guardada ✅', icono: '💳', confirmar: 'Listo', mensaje: 'Ya puedes pagar en un toque con tu ' + (j.metodo.marca || 'tarjeta') + ' ···· ' + (j.metodo.ultimos4 || '') + '.'}).then(function(){ pcgRecargar('Actualizando…'); });
              else pcgAvisar({titulo: 'No se pudo guardar', icono: '⚠️', mensaje: j.mensaje || 'Reintenta con otra tarjeta.'});
            }).catch(function(){ pcgCargando(false); pcgAvisar({titulo: 'Sin conexión', icono: '⚠️', mensaje: 'Reintenta.'}); });
          } else { pcgAvisar({titulo: 'No se pudo', icono: '⚠️', mensaje: (Culqi.error && Culqi.error.user_message) || 'Culqi no pudo leer la tarjeta.'}); }
        };
        Culqi.open();
      });
  });
})();
"""

JS_BUSCAR = r"""
(function(){
  var f = document.getElementById('fBusq'); if(!f) return;
  f.querySelectorAll('.pr-rc input').forEach(function(i){
    i.addEventListener('change', function(){ f.querySelectorAll("input[name='" + i.name + "']").forEach(function(o){ o.closest('.pr-rc').classList.toggle('sel', o.checked); }); });
  });
  f.addEventListener('submit', function(ev){
    var z = f.querySelector("input[name='zona']:checked");
    if(z && z.value === '__cerca' && !document.getElementById('bLat').value){
      ev.preventDefault();
      if(!navigator.geolocation){ pcgAvisar({titulo: 'Ubicación no disponible', icono: '📍', mensaje: 'Tu navegador no permite ubicación. Elige una zona.'}); return; }
      pcgCargando('Buscando dónde estás…');
      navigator.geolocation.getCurrentPosition(function(p){
        document.getElementById('bLat').value = p.coords.latitude.toFixed(5); document.getElementById('bLng').value = p.coords.longitude.toFixed(5);
        pcgCargando('Buscando canchas…'); f.submit();
      }, function(){ pcgCargando(false); pcgAvisar({titulo: 'No pudimos leer tu ubicación', icono: '📍', mensaje: 'Revisa el permiso del navegador o elige una zona.'}); }, {timeout: 10000, maximumAge: 300000});
      return;
    }
    if(!(z && z.value === '__cerca')){ document.getElementById('bLat').value = ''; document.getElementById('bLng').value = ''; }
    pcgCargando('Buscando canchas…', {demora: 250});
  });
  var r = document.getElementById('resultados'); if(r) r.scrollIntoView({block: 'start'});
})();
"""

JS_RECORDAR = r"""
(function(){
  var C = window.__rec || {}, lista = document.getElementById('recLista');
  function post(url, body){ return fetch(url, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body || {})}).then(function(r){ return r.json(); }); }
  function hecho(fila){ var b = fila.querySelector('[data-acc]'); if(b) b.outerHTML = "<span class='pill ok'>✓ Recordado</span>"; }
  if(lista) lista.addEventListener('click', function(ev){
    var b = ev.target.closest('[data-acc]'); if(!b) return;
    var fila = b.closest('[data-res]'), f = C.fichas[fila.dataset.res]; if(!f) return;
    if(b.dataset.acc === 'wa'){ post('/anfitrion/recordatorios/marcar', {fecha: C.fecha, ids: f.ids}).then(function(j){ if(j.ok) hecho(fila); }); return; }
    pcgCargando('Enviando…', {demora: 250});
    post('/anfitrion/recordatorios/enviar', {fecha: C.fecha, ids: f.ids}).then(function(j){
      pcgCargando(false);
      if(j.ok){ hecho(fila); pcgToast('Le recordé por la app 📲'); }
      else pcgAvisar({titulo: 'No se pudo', icono: '⚠️', mensaje: j.mensaje || 'Reintenta.'});
    }).catch(function(){ pcgCargando(false); pcgAvisar({titulo: 'Sin conexión', icono: '⚠️', mensaje: 'Reintenta.'}); });
  });
  var t = document.getElementById('recTodos');
  if(t) t.addEventListener('click', function(){
    var ids = [];
    Object.keys(C.fichas).forEach(function(k){ var f = C.fichas[k], fila = document.querySelector("[data-res='" + k + "'] [data-acc='app']"); if(f.canal === 'app' && fila) ids = ids.concat(f.ids); });
    if(!ids.length){ pcgToast('No queda nadie por recordar por la app.'); return; }
    pcgCargando('Recordando a tus clientes…');
    post('/anfitrion/recordatorios/enviar', {fecha: C.fecha, ids: ids}).then(function(j){
      if(j.ok) pcgAvisar({titulo: '✅ Recordatorios enviados', icono: '📲', confirmar: 'Listo', mensaje: 'Recordé a ' + j.enviados + ' jugador(es) por la app. Los que no tienen la app: tócales “WhatsApp”.'}).then(function(){ pcgRecargar('Actualizando…'); });
      else { pcgCargando(false); pcgAvisar({titulo: 'No se pudo', icono: '⚠️', mensaje: j.mensaje || 'Reintenta.'}); }
      pcgCargando(false);
    }).catch(function(){ pcgCargando(false); pcgAvisar({titulo: 'Sin conexión', icono: '⚠️', mensaje: 'Reintenta.'}); });
  });
})();
"""
