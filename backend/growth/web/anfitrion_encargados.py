"""ENCARGADOS DEL LOCAL en el modo anfitrión web (rol único "Recepción").

- El DUEÑO, en `/anfitrion/encargados?local=<cancha_id>` (o desde Editar
  local → Encargados): ve a su equipo por local, invita por correo de Google
  (el único campo de texto), quita el acceso y ve la bitácora de lo que hizo
  su recepción.
- La persona invitada recibe push + correo y, al entrar a `/anfitrion`, ve
  "Te invitaron a ayudar en <local> · Aceptar / Rechazar". Aceptado, el menú
  le muestra los locales donde ayuda y las MISMAS páginas del dueño (Hoy,
  Calendario, Reservas, Pagos por confirmar) recortadas a ese local; lo que
  su rol no incluye responde con `sin_permiso` (403).

Reglas de quién puede qué: `web/permisos.py`. Datos: `web/encargados.py`
(migración `0005_encargados.sql`; sin ella todo queda oculto).
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.concurrency import run_in_threadpool

import fidelidad
from config import MARCA
from web import anfitrion as _anf
from web import datos, encargados, permisos, ui
from web.anfitrion import _cabecera, _sesion_o_entrar
from web.router import _pais_de, e

router = APIRouter(tags=["web-anfitrion-encargados"])

ERRORES = {
    "correo_invalido": "Escribe el correo de Google de la persona (ej. nombre@gmail.com).",
    "eres_tu": "Ese es tu propio correo: tú ya eres el dueño del local.",
    "tope": f"Un local puede tener hasta {encargados.MAX_POR_LOCAL} encargados. Quita a alguien para invitar a otra persona.",
    "no_disponible": "Los encargados aún no están disponibles en este ambiente.",
    "no_guardado": "No pudimos guardar en este momento. Intenta de nuevo.",
    "local_ajeno": "Ese local no está a tu nombre.",
    "no_encontrado": "Esta invitación ya no existe o ya se respondió.",
}
PUEDE = ["Ver Hoy, Calendario y Reservas del local (con nombre y celular del jugador)",
         "Registrar reservas manuales y quitarlas", "Bloquear y desbloquear turnos",
         "Marcar reservas como cobradas o por cobrar, y no-show", "Aprobar o rechazar comprobantes en Pagos por confirmar"]
NO_PUEDE = ["Ver ingresos, billetera, reportes, caja ni liquidaciones", "Cambiar precios, reglas, horarios, fotos o datos del local",
            "Tocar la cuenta Culqi, los medios de pago ni la cuenta de cobro",
            "Cancelar con devolución, eliminar canchas ni invitar a otros"]
ACCIONES_TXT = {"reserva_manual": "registró una reserva manual", "quitar_manual": "quitó una reserva manual",
                "bloquear": "bloqueó un turno", "desbloquear": "desbloqueó un turno",
                "marcar_pagada": "marcó una reserva como cobrada", "marcar_por_cobrar": "marcó una reserva por cobrar",
                "noshow": "marcó un no-show", "voucher_aprobado": "aprobó un comprobante", "voucher_rechazado": "rechazó un comprobante"}
PILL = {"invitado": "warn", "activo": "ok", "rechazado": "gris", "revocado": "gris"}

CSS = """
.enc-fila{display:flex;align-items:center;gap:12px;padding:12px 0;border-top:1px solid var(--trazo);min-width:0}
.enc-fila:first-child{border-top:0}.enc-fila .av{flex:none;width:36px;height:36px;border-radius:50%;background:var(--tinte);color:var(--teal);
 display:inline-flex;align-items:center;justify-content:center;font-weight:800}
.enc-fila{flex-wrap:wrap}.enc-fila .pill{flex:none}
.enc-fila .txt{min-width:0;flex:1 1 200px}.enc-fila .txt b{display:block;overflow-wrap:anywhere}
.enc-fila .txt small{color:var(--tenue)}.enc-fila .btn{flex:none}
.enc-lista{list-style:none;margin:8px 0 0;padding:0}.enc-lista li{margin:4px 0;color:var(--tenue)}
.enc-lista.si li::before{content:'✓ ';color:var(--esmeralda);font-weight:800}.enc-lista.no li::before{content:'✕ ';color:var(--rojo);font-weight:800}
.enc-inv{display:flex;gap:10px;flex-wrap:wrap;align-items:flex-end;margin-top:8px}.enc-inv>div{flex:1 1 240px;min-width:0}
.enc-inv input{width:100%}.enc-reglas{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(260px,100%),1fr));gap:16px}
.enc-act{list-style:none;margin:6px 0 0;padding:0}.enc-act li{padding:8px 0;border-top:1px solid var(--trazo);overflow-wrap:anywhere}
.enc-act li:first-child{border-top:0}.enc-act small{display:block;color:var(--tenue)}
.enc-banner{border:1px solid var(--trazo);border-radius:var(--r);padding:16px;background:var(--papel);display:flex;
 flex-direction:column;gap:10px}.enc-banner b{overflow-wrap:anywhere}
"""

JS = r"""
(function(){
function post(url,body){return fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body||{})}).then(function(r){return r.json()})}
var f=document.getElementById('encInvitar');
if(f){f.addEventListener('submit',async function(ev){ev.preventDefault();var em=document.getElementById('encEmail'),b=f.querySelector('button');
  var v=(em.value||'').trim();if(!v){pcgAvisar({titulo:'Falta el correo',mensaje:'Escribe el correo de Google de la persona.',icono:'✉️'});return}
  b.disabled=true;pcgCargando('Enviando invitación…');
  try{var j=await post('/anfitrion/encargados/invitar',{cancha_id:f.dataset.cancha,email:v});
    if(j.ok){pcgRecargar(j.ya_invitado?'Esa persona ya estaba invitada':'Invitación enviada ✉️');return}
    pcgCargando(false);pcgAvisar({titulo:'No se pudo invitar',mensaje:j.mensaje||j.error,icono:'⚠️'})}
  catch(e){pcgCargando(false);pcgAvisar({titulo:'Sin conexión',mensaje:'Revisa tu conexión e intenta de nuevo.'})}
  b.disabled=false})}
document.addEventListener('click',async function(ev){
  var q=ev.target.closest('[data-revocar]');
  if(q){if(!await pcgConfirmar({titulo:'¿Quitar el acceso?',mensaje:q.dataset.email+' dejará de ver la agenda y los pagos de este local.',confirmar:'Quitar acceso',destructivo:true,icono:'🔒'}))return;
    q.disabled=true;pcgCargando('Quitando el acceso…');
    try{var j=await post('/anfitrion/encargados/'+encodeURIComponent(q.dataset.revocar)+'/revocar',{});if(j.ok){pcgRecargar('Acceso quitado');return}
      pcgCargando(false);pcgAvisar({titulo:'No se pudo',mensaje:j.mensaje||j.error})}catch(e){pcgCargando(false);pcgAvisar({titulo:'Sin conexión',mensaje:'Intenta de nuevo.'})}
    q.disabled=false;return}
  var a=ev.target.closest('[data-encargo]');
  if(a){var acc=a.dataset.acc;
    if(acc==='rechazar'&&!await pcgConfirmar({titulo:'¿Rechazar la invitación?',mensaje:'No tendrás acceso a este local. El dueño puede volver a invitarte.',confirmar:'Rechazar',destructivo:true}))return;
    a.disabled=true;pcgCargando(acc==='aceptar'?'Aceptando…':'Rechazando…');
    try{var j=await post('/anfitrion/encargos/'+encodeURIComponent(a.dataset.encargo)+'/'+acc,{});
      if(j.ok){if(acc==='aceptar'){pcgIr(j.ir||'/anfitrion/mis-canchas','¡Listo! Ya ayudas en este local');return}pcgRecargar('Invitación rechazada');return}
      pcgCargando(false);pcgAvisar({titulo:'No se pudo',mensaje:j.mensaje||j.error})}catch(e){pcgCargando(false);pcgAvisar({titulo:'Sin conexión',mensaje:'Intenta de nuevo.'})}
    a.disabled=false}
});
})();
"""


def _err(error: str, status: int = 400, **kw) -> JSONResponse:
    return JSONResponse({"ok": False, "error": error, "mensaje": ERRORES.get(error, error), **kw}, status_code=status)


def _cuando(iso: str, pais: str = "PE") -> str:
    try:
        d = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return ""
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    from web import horarios
    loc = d.astimezone(horarios.ahora_local(pais).tzinfo)
    return f"{loc.day} {horarios.MESES[loc.month - 1]} · {loc:%H:%M}"


def _iniciales(email: str) -> str:
    return (email[:1] or "?").upper()


def locales_de(dueno: str) -> list[dict]:
    """Locales del dueño: [{key, nombre, canchas, ancla}] (mismo agrupado
    que la tarjeta de fidelidad y Mis canchas)."""
    grupos: dict[str, dict] = {}
    for c in datos.canchas_de_dueno(dueno):
        k = fidelidad.local_key(c)
        g = grupos.setdefault(k, {"key": k, "nombre": (c.get("club") or "").strip() or c.get("nombre") or "Mi local",
                                  "canchas": [], "ancla": c})
        g["canchas"].append(c)
    return list(grupos.values())


# ── piezas que usan otras páginas ────────────────────────────────────────────

def sin_permiso(ses: dict, seccion: str = "") -> HTMLResponse:
    """403 para quien SOLO es encargado y abre una sección del dueño."""
    activos = encargados.activos_de(ses["email"])
    locales = ", ".join(dict.fromkeys(a.get("local_nombre") or "el local" for a in activos)) or "un local"
    cuerpo = ("<a class='anf-back' href='/anfitrion'>‹ Modo anfitrión</a>"
              "<div class='panel' style='max-width:640px;margin:24px auto 0'>"
              "<h1 class='anf-hola' style='margin-top:0'>Tu rol no incluye esta sección</h1>"
              f"<p class='sub'>Eres <b>Recepción</b> en {e(locales)}. Puedes ver la agenda, registrar reservas, bloquear turnos, "
              "marcar pagos y confirmar comprobantes. La plata, los precios y la configuración del local los maneja el dueño.</p>"
              "<div class='acciones'><a class='btn' href='/anfitrion/mis-canchas'>Ir a Hoy</a>"
              "<a class='btn sec' href='/anfitrion/calendario'>Calendario</a>"
              "<a class='btn sec' href='/anfitrion/pagos-por-confirmar'>Pagos por confirmar</a></div></div>")
    r = ui.shell("Sin acceso", cuerpo, nav=_cabecera(seccion, ses), sesion=ses, ancho=True, titulo_tab=f"Sin acceso · Modo anfitrión · {MARCA}")
    r.status_code = 403
    return r


def para_menu(email: str) -> tuple[str, frozenset, int]:
    """(html para arriba del menú /anfitrion, claves del menú a ocultar,
    vouchers por revisar). Invitaciones pendientes con Aceptar/Rechazar y los
    locales donde ayuda. Sin la migración: nada y el ítem "Encargados" oculto."""
    from web import cobro_directo_web as cdw
    n_vouchers = cdw.pendientes_operables(email)
    if not encargados.disponible():
        return "", frozenset({"encargados"}), n_vouchers
    html = ""
    for inv in encargados.invitaciones_de(email):
        html += ("<div class='enc-banner' role='region' aria-label='Invitación'>"
                 f"<b>👥 Te invitaron a ayudar en {e(inv.get('local_nombre') or 'un local')}</b>"
                 f"<span class='sub' style='margin:0'>{e(inv['dueno'])} quiere que seas su <b>Recepción</b>: verás la agenda del local, "
                 "registrarás reservas, bloquearás turnos, marcarás pagos y confirmarás comprobantes. No verás su plata.</span>"
                 f"<div class='acciones' style='margin:0'><button type='button' class='btn' data-encargo='{e(inv['id'])}' data-acc='aceptar'>Aceptar</button>"
                 f"<button type='button' class='btn sec' data-encargo='{e(inv['id'])}' data-acc='rechazar'>Rechazar</button></div></div>")
    activos = encargados.activos_de(email)
    if activos:
        its = ""
        for a in activos:
            nombre = a.get("local_nombre") or "Local"
            its += (f"<a class='anf-item' href='/anfitrion/mis-canchas'><span class='ico' style='background:var(--esmeralda)' aria-hidden='true'>🛎️</span>"
                    f"<span class='txt'><b>{e(nombre)}</b><small>Recepción · dueño {e(a['dueno'])} · agenda, reservas y pagos</small></span>"
                    "<span class='chev' aria-hidden='true'>›</span></a>")
        html += f"<section class='anf-grupo' aria-label='Locales donde ayudas'><h2>Locales donde ayudas</h2>{its}</section>"
    ocultar = frozenset()
    if permisos.es_solo_encargado(email):
        ocultar = permisos.MENU_SOLO_DUENO | {"encargados", "mis-canchas"}
    if html:
        html += f"<style>{CSS}</style><script>{JS}</script>"
    return html, ocultar, n_vouchers


def seccion_editar_local(email: str, c: dict) -> str:
    """Sección "Encargados" de Editar local (resumen + enlace)."""
    if not encargados.disponible():
        return ""
    k = fidelidad.local_key(c)
    vivos = [f for f in encargados.de_dueno(email) if f["local_key"] == k and f["estado"] in encargados.VIVOS]
    filas = "".join(f"<li><b>{e(f['email'])}</b> · <span class='pill {PILL[f['estado']]}'>{e(encargados.ESTADOS[f['estado']])}</span></li>"
                    for f in vivos[:6])
    return ("<section class='panel edit-sec' id='sec-encargados'><h2>👥 Encargados</h2>"
            "<p class='sub'>Invita a quien te ayuda en la recepción: opera la agenda, las reservas y los pagos de este local, "
            "sin ver tu plata ni cambiar precios.</p>"
            + (f"<ul class='sub' style='margin:0 0 0 18px'>{filas}</ul>" if filas else "")
            + f"<div class='acciones' style='margin-top:10px'><a class='btn sec' href='/anfitrion/encargados?local={e(c['id'])}'>"
            + ("Administrar encargados" if vivos else "＋ Invitar a un encargado") + "</a></div></section>")


# ── página del dueño ─────────────────────────────────────────────────────────

def _fila(f: dict, pais: str) -> str:
    est = f["estado"]
    cuando = _cuando(f.get("aceptado_en") or f.get("creado") or "", pais)
    det = ("Aceptó el " if est == "activo" and f.get("aceptado_en") else "Invitado el ") + cuando if cuando else ""
    boton = (f"<button type='button' class='btn sec' data-revocar='{e(f['id'])}' data-email='{e(f['email'])}' style='color:var(--rojo)'>"
             + ("Quitar acceso" if est == "activo" else "Anular invitación") + "</button>") if est in encargados.VIVOS else ""
    return (f"<div class='enc-fila'><span class='av' aria-hidden='true'>{e(_iniciales(f['email']))}</span>"
            f"<div class='txt'><b>{e(f['email'])}</b><small>{e(encargados.ROLES.get(f['rol'], f['rol']))}{(' · ' + e(det)) if det else ''}</small></div>"
            f"<span class='pill {PILL.get(est, 'gris')}'>{e(encargados.ESTADOS.get(est, est))}</span>{boton}</div>")


def _actividad(dueno: str, ids: set[str], nombres: dict, pais: str) -> str:
    acts = [a for a in encargados.acciones_de(dueno, 120) if a.get("cancha_id") in ids][:30]
    if not acts:
        return "<p class='sub' style='margin:6px 0 0'>Aún no hay acciones de tu recepción en este local.</p>"
    out = ""
    for a in acts:
        det = a.get("detalle") or {}
        extra = " · ".join(str(x) for x in (det.get("cliente"), det.get("fecha"), det.get("hora")) if x) or str(a.get("ref") or "")
        out += (f"<li><b>{e(a.get('actor'))}</b> {e(ACCIONES_TXT.get(a.get('accion'), a.get('accion')))}"
                f"<small>{e(nombres.get(a.get('cancha_id'), 'Cancha'))}{(' · ' + e(extra)) if extra else ''} · {e(_cuando(a.get('creado_en'), pais))}</small></li>")
    return f"<ul class='enc-act'>{out}</ul>"


@router.get("/anfitrion/encargados", response_class=HTMLResponse)
def pagina_encargados(request: Request, local: str = "") -> HTMLResponse:
    ses, resp = _sesion_o_entrar(request, "/anfitrion/encargados" + (f"?local={local}" if local else ""))
    if resp is not None:
        return resp
    email = ses["email"]
    locales = locales_de(email)
    if not locales:
        if permisos.es_solo_encargado(email):
            return sin_permiso(ses, "")
        cuerpo = ("<a class='anf-back' href='/anfitrion'>‹ Modo anfitrión</a><h1 class='anf-hola'>Encargados</h1>"
                  "<div class='anf-vacio' style='margin-top:16px'>Primero registra tu cancha: luego podrás invitar a tu recepción.</div>"
                  "<p style='margin-top:14px'><a class='btn' href='/anfitrion/nueva'>Registrar mi cancha</a></p>")
        return ui.shell("Encargados", cuerpo, nav=_cabecera("", ses), sesion=ses, ancho=True, titulo_tab=f"Encargados · Modo anfitrión · {MARCA}")
    sel = next((g for g in locales if any(c["id"] == local for c in g["canchas"])), locales[0])
    pais = _pais_de(sel["ancla"])
    chips = ("<div class='chips' role='group' aria-label='Local' style='margin-top:12px'>"
             + "".join(f"<a class='chip{' sel' if g is sel else ''}' href='/anfitrion/encargados?local={e(g['ancla']['id'])}'"
                       f"{' aria-current=page' if g is sel else ''}>{e(g['nombre'])}</a>" for g in locales) + "</div>") if len(locales) > 1 else ""
    reglas = ("<div class='enc-reglas'><div><h3 style='margin:0'>Recepción puede</h3><ul class='enc-lista si'>"
              + "".join(f"<li>{e(x)}</li>" for x in PUEDE) + "</ul></div><div><h3 style='margin:0'>No puede</h3><ul class='enc-lista no'>"
              + "".join(f"<li>{e(x)}</li>" for x in NO_PUEDE) + "</ul></div></div>")
    if not encargados.disponible():
        cuerpo = ("<a class='anf-back' href='/anfitrion'>‹ Modo anfitrión</a><h1 class='anf-hola'>Encargados</h1>"
                  f"<div class='aviso warn' style='margin-top:16px'>{e(ERRORES['no_disponible'])}</div>"
                  f"<section class='panel' style='margin-top:16px'>{reglas}</section><style>{CSS}</style>")
        return ui.shell("Encargados", cuerpo, nav=_cabecera("", ses), sesion=ses, ancho=True, titulo_tab=f"Encargados · Modo anfitrión · {MARCA}")
    todos = [f for f in encargados.de_dueno(email) if f["local_key"] == sel["key"]]
    vivos = [f for f in todos if f["estado"] in encargados.VIVOS]
    viejos = [f for f in todos if f["estado"] not in encargados.VIVOS]
    lista = "".join(_fila(f, pais) for f in vivos) or "<p class='sub' style='margin:6px 0 0'>Todavía no invitaste a nadie a este local.</p>"
    hist = (f"<details style='margin-top:12px'><summary class='sub'>Anteriores ({len(viejos)})</summary>"
            + "".join(_fila(f, pais) for f in viejos[:20]) + "</details>") if viejos else ""
    ids = {c["id"] for c in sel["canchas"]}
    nombres = {c["id"]: c.get("nombre") or "Cancha" for c in sel["canchas"]}
    cuerpo = (
        "<a class='anf-back' href='/anfitrion'>‹ Modo anfitrión</a>"
        "<h1 class='anf-hola'>Encargados</h1>"
        f"<p class='sub'>Invita a quien te ayuda en la recepción de tu local. Entra con su propia cuenta de Google y solo ve lo que necesita para operar.</p>{chips}"
        f"<section class='panel' style='margin-top:16px' aria-labelledby='tEq'><h2 id='tEq'>Equipo de {e(sel['nombre'])}</h2>"
        f"<p class='sub'>{len(sel['canchas'])} cancha{'s' if len(sel['canchas']) != 1 else ''} · rol <span class='pill gris'>Recepción</span></p>{lista}{hist}"
        f"<form id='encInvitar' class='enc-inv' data-cancha='{e(sel['ancla']['id'])}' novalidate>"
        "<div><label for='encEmail'>Correo de Google de la persona</label>"
        "<input id='encEmail' type='email' inputmode='email' autocomplete='off' maxlength='120' placeholder='nombre@gmail.com'></div>"
        "<button type='submit' class='btn'>Invitar</button></form>"
        "<p class='sub' style='font-size:13px;margin-top:8px'>Le llega un aviso y un correo. Cuando acepte, aparece como Activo.</p></section>"
        f"<section class='panel' style='margin-top:16px'>{reglas}</section>"
        f"<section class='panel' style='margin-top:16px' aria-labelledby='tAct'><h2 id='tAct'>Actividad de tu recepción</h2>{_actividad(email, ids, nombres, pais)}</section>"
        f"<style>{CSS}</style><script>{JS}</script>")
    return ui.shell("Encargados", cuerpo, nav=_cabecera("", ses), sesion=ses, ancho=True, titulo_tab=f"Encargados · Modo anfitrión · {MARCA}")


# ── endpoints JSON ───────────────────────────────────────────────────────────

async def _cuerpo(request: Request):
    from web.anfitrion_cobros_club import _cuerpo as _c  # mismo guardia: JSON + mismo origen + sesión
    return await _c(request)


def _push(email: str, titulo: str, texto: str) -> None:
    from pagos import router as pr
    _anf._en_segundo_plano(pr._aviso_push_usuario, email, titulo, texto, "encargado")


def _invitar(dueno: str, cancha_id: str, email: str) -> JSONResponse:
    g = next((g for g in locales_de(dueno) if any(c["id"] == cancha_id for c in g["canchas"])), None)
    if g is None:
        return _err("local_ajeno", 404)
    status, r = encargados.invitar(dueno, g["key"], g["nombre"], [c["id"] for c in g["canchas"]], email)
    if not r.get("ok"):
        return _err(r["error"], status)
    if not r.get("ya_invitado"):
        inv = r["encargado"]
        _push(inv["email"], "Te invitaron a ayudar 👥", f"{dueno} te invitó a ser Recepción en {g['nombre']}. Acepta en Modo anfitrión.")
        try:
            import correos
            correos.encolar("aviso", datos={
                "para": inv["email"], "clave": f"encargado:{inv['id']}", "titulo": f"Te invitaron a ayudar en {g['nombre']}",
                "intro": f"{dueno} quiere que seas su Recepción en {MARCA}: verás la agenda del local, registrarás reservas, "
                         "bloquearás turnos, marcarás pagos y confirmarás comprobantes. Entra con esta misma cuenta de Google y acepta.",
                "datos": [["Local", g["nombre"]], ["Rol", "Recepción"], ["Invita", dueno]],
                "boton": ["Ver la invitación", "/anfitrion"], "etiqueta": "Invitación"})
        except Exception as ex:  # noqa: BLE001 — el correo nunca rompe la invitación
            print(f"[encargados] correo no encolado: {ex}", flush=True)
        print(f"[encargados] {dueno} invitó a {inv['email']} a {g['key']}", flush=True)
    return JSONResponse({"ok": True, "ya_invitado": bool(r.get("ya_invitado")), "id": r["encargado"]["id"]})


@router.post("/anfitrion/encargados/invitar")
async def invitar(request: Request) -> JSONResponse:
    ses, b, malo = await _cuerpo(request)
    if malo is not None:
        return malo
    return await run_in_threadpool(_invitar, ses["email"], str(b.get("cancha_id") or ""), str(b.get("email") or ""))


def _revocar(dueno: str, eid: str) -> JSONResponse:
    f = encargados.revocar(dueno, eid)
    if f is None:
        return _err("no_encontrado", 404)
    if f["estado"] == "activo":
        _push(f["email"], "Ya no tienes acceso a un local", f"{dueno} quitó tu acceso de Recepción en {f.get('local_nombre') or 'su local'}.")
    print(f"[encargados] {dueno} quitó a {f['email']} de {f['local_key']}", flush=True)
    return JSONResponse({"ok": True})


@router.post("/anfitrion/encargados/{eid}/revocar")
async def revocar(request: Request, eid: str) -> JSONResponse:
    ses, _b, malo = await _cuerpo(request)
    if malo is not None:
        return malo
    return await run_in_threadpool(_revocar, ses["email"], eid)


def _responder(email: str, eid: str, aceptar: bool) -> JSONResponse:
    f = encargados.por_id(eid)
    ok = encargados.aceptar(email, eid) if aceptar else encargados.rechazar(email, eid)
    if not ok or f is None:
        return _err("no_encontrado", 404)
    _push(f["dueno"], "Tu recepción aceptó 👥" if aceptar else "Invitación rechazada",
          f"{email} {'ya ayuda' if aceptar else 'no aceptó ayudar'} en {f.get('local_nombre') or 'tu local'}.")
    print(f"[encargados] {email} {'aceptó' if aceptar else 'rechazó'} {eid}", flush=True)
    return JSONResponse({"ok": True, "ir": "/anfitrion/mis-canchas" if aceptar else "/anfitrion"})


@router.post("/anfitrion/encargos/{eid}/aceptar")
async def aceptar(request: Request, eid: str) -> JSONResponse:
    ses, _b, malo = await _cuerpo(request)
    if malo is not None:
        return malo
    return await run_in_threadpool(_responder, ses["email"], eid, True)


@router.post("/anfitrion/encargos/{eid}/rechazar")
async def rechazar(request: Request, eid: str) -> JSONResponse:
    ses, _b, malo = await _cuerpo(request)
    if malo is not None:
        return malo
    return await run_in_threadpool(_responder, ses["email"], eid, False)
