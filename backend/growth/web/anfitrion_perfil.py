"""MI PERFIL del modo anfitrión (captura "CanchaLibre Perfil", rediseño del
diseñador, 16-nov-2026): `GET /anfitrion/perfil`.

Junta en UNA página lo que estaba repartido en `/perfil`, `/cuenta/*`,
`/mi-billetera`, `/pro` y `/mi-pais`, sin duplicar reglas:

- Identidad: foto (sube con el MISMO `POST /web/cuenta/foto` de Configuración),
  nombre, correo, "Anfitrión"/"Recepción", identidad verificada o pendiente
  (`datos.esta_verificado`) y "N locales · N canchas · N academias" reales.
- Datos personales: Nombre + Apellido (el modelo guarda el nombre COMPLETO:
  se parte con `culqi.partir_nombre` y se une al guardar, sin perder nada),
  correo de Google (bloqueado) y WhatsApp con prefijo por país; se guardan con
  `POST /web/cuenta/perfil` (mismas validaciones; se reenvía la bio actual
  para no borrarla).
- Verificación: estado real + "Verificar DNI/CI/cédula" → `/cuenta/identidad`.
- Saldo y suscripciones: saldo de la billetera en su moneda, Pro (precio de
  `pagos.router._pro_precio_centimos`) y Plan Academia (`academia_plan`, solo
  con academia y modelo de suscripción).
- Notificaciones (NUEVO): 4 interruptores → `POST /web/avisos/prefs`
  (`prefs_avisos.py`); `pagos.router._aviso_push_usuario` y `correos.encolar`
  los respetan. Los recibos de pago por correo no se apagan.
- Preferencias: país de la billetera (= `/mi-pais`, solo con saldo 0;
  `POST /web/mi-pais`). Sin selector de idioma: la plataforma es en español.
- Privacidad y seguridad: "Cerrar sesión en todos los dispositivos" (NUEVO,
  `POST /web/sesion/cerrar-todas` → `sesion.cerrar_todas`: sube la época de
  sesión del correo y re-emite la cookie de este navegador), modo jugador y
  Eliminar mi cuenta.
"""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Body, Request
from fastapi.responses import HTMLResponse, JSONResponse

from config import MARCA
from web import sesion, ui
from web import vista_anfitrion as va
from web.ui import e

router = APIRouter()

# Íconos que no están en `web/iconos.py` (mismo trazo: 24×24, línea 2.2).
_SVG = {
    "persona": "<circle cx='12' cy='8' r='4'/><path d='M4.5 20.5c.8-4 3.8-6.2 7.5-6.2s6.7 2.2 7.5 6.2'/>",
    "candado": "<rect x='4.5' y='10.5' width='15' height='10.5' rx='2'/><path d='M8 10.5V7.5a4 4 0 0 1 8 0v3'/>",
    "salir": "<path d='M14 4.5h4.5a1.5 1.5 0 0 1 1.5 1.5v12a1.5 1.5 0 0 1-1.5 1.5H14'/><path d='M10 8l-4 4 4 4M6 12h10'/>",
    "camara": "<path d='M4 8.5a1.5 1.5 0 0 1 1.5-1.5h2.2l1.5-2h5.6l1.5 2h2.2A1.5 1.5 0 0 1 20 8.5v9a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 17.5z'/><circle cx='12' cy='12.8' r='3.3'/>",
    "corona": "<path d='M3.5 8l4.2 3.6L12 5l4.3 6.6L20.5 8l-1.8 10.5H5.3z'/>",
    "megafono": "<path d='M4 10v4h3l7 4.5v-13L7 10z'/><path d='M17.5 9a4 4 0 0 1 0 6'/>",
    "papelera": "<path d='M4.5 7h15M9.5 7V4.5h5V7M6.5 7l1 13h9l1-13'/>",
    "celular": "<rect x='6.5' y='2.5' width='11' height='19' rx='2.4'/><path d='M10.5 18.5h3'/>",
    "billetera": "<path d='M4 7.5A2.5 2.5 0 0 1 6.5 5H18v3'/><rect x='4' y='7.5' width='16.5' height='12' rx='2'/><path d='M16 13.5h.01' stroke-width='3'/>",
    "alerta": "<path d='M12 4l9 15.5H3z'/><path d='M12 10v4.2M12 17h.01'/>",
    "correo": "<rect x='3' y='5.5' width='18' height='13' rx='2'/><path d='M3.5 7l8.5 6.2L20.5 7'/>",
    "documento": "<rect x='3' y='5' width='18' height='14' rx='2'/><circle cx='8.5' cy='11' r='2.2'/><path d='M5.5 16c.5-1.6 1.6-2.4 3-2.4s2.5.8 3 2.4M14 10h4M14 13.5h4'/>",
}


def _svg(clave: str, tam: int = 18, grueso: float = 2.2) -> str:
    from web import iconos
    cuerpo = _SVG.get(clave)
    if not cuerpo:
        return iconos.svg(clave, tam, grueso=grueso)
    return (f"<svg viewBox='0 0 24 24' width='{tam}' height='{tam}' fill='none' stroke='currentColor' stroke-width='{grueso}' "
            f"stroke-linecap='round' stroke-linejoin='round' aria-hidden='true'>{cuerpo}</svg>")


def _ic(clave: str, tono: str = "suave") -> str:
    """Ícono en cuadrado: [tono] suave (celeste con ícono azul, como el diseño) o azul (blanco sobre azul)."""
    return f"<span class='vp-ic {tono}'>{_svg(clave)}</span>"


def _plural(n: int, uno: str, varios: str) -> str:
    return f"{n} {uno if n == 1 else varios}"


def _monto(sim: str, v: float) -> str:
    return f"{sim} {float(v or 0):,.2f}"


SECCIONES = (("datos", "Datos personales", "persona"), ("verificacion", "Verificación", "escudo"),
             ("saldo", "Saldo y suscripciones", "billetera"), ("avisos", "Notificaciones", "campana"),
             ("preferencias", "Preferencias", "filtros"), ("privacidad", "Privacidad y seguridad", "candado"))


def _avisos_filas(iso: str, prefs: dict) -> list[tuple[str, str, str, str]]:
    """(clave, ícono, título, descripción). La descripción de los pagos sigue el
    país: Yape/Plin solo en Perú (regla multi-país)."""
    comp = "Comprobantes de Yape, Plin o transferencia" if iso == "PE" else "Comprobantes de QR o transferencia"
    return [("reservas", "calendario", "Nuevas reservas", "Cuando un jugador reserva en tus canchas"),
            ("pagos", "recibo", "Pagos por confirmar", f"{comp} que debes revisar"),
            ("academia", "academias", "Cuotas de la academia", "Alumnos nuevos, cuotas pagadas y pagos por confirmar"),
            ("novedades", "megafono", f"Novedades de {MARCA}", "Funciones nuevas y promociones")]


def _contexto_perfil(email: str, ses: dict) -> dict:
    """Todo lo que pinta la página (lecturas, sin escribir nada salvo el
    arranque de la prueba del Plan Academia, que ya hace cualquier panel)."""
    import academia_plan
    import prefs_avisos
    from db.store import stores
    from pagos import culqi
    from web import datos, permisos
    from web.jugador_billetera import PAISES, pais_billetera, puede_cambiar_pais
    from web.jugador_cuenta import DOC, partir_celular, perfil_completo
    from web.jugador_pro import estado_pro

    p = perfil_completo(email)
    canchas = datos.canchas_de_dueno(email)
    try:
        academias = datos.academias_de_dueno(email)
    except Exception:  # noqa: BLE001
        academias = []
    iso, fuente = pais_billetera(email, canchas)
    cel = p.get("celular") or ""
    pais_cel, local = partir_celular(cel) if cel else (iso, "")
    nombre_completo = p.get("nombre") or ses.get("nombre") or ""
    nombre, apellido = culqi.partir_nombre(nombre_completo)
    plan = None
    if academias and academia_plan.es_suscripcion():
        visibles = [a for a in academias if academia_plan.habilitada(a)] or academias
        estados = []
        for a in visibles:
            try:
                estados.append((a, academia_plan.estado(a)))
            except Exception:  # noqa: BLE001
                continue
        if estados:
            # La que más apura: vencida primero, luego la que vence antes.
            orden = {"vencida": 0, "prueba": 1, "activa": 2}
            a, st = min(estados, key=lambda x: (orden.get(x[1].get("estado"), 3), x[1].get("dias_restantes") or 0))
            plan = {"academia": a, "estado": st, "n": len(estados)}
    return {
        "nombre": nombre, "apellido": apellido, "nombre_completo": nombre_completo,
        "foto": p.get("foto_url") or ses.get("foto") or "", "bio": p.get("bio") or {},
        "pais_cel": pais_cel, "local": local,
        "canchas": canchas, "locales": len({(c.get("club") or c.get("nombre") or c.get("id")) for c in canchas}),
        "academias": academias,
        "verificado": datos.esta_verificado(email),
        "solo_encargado": (not canchas) and permisos.es_solo_encargado(email),
        "iso": iso, "fuente": fuente, "P": PAISES.get(iso) or PAISES["PE"], "PAISES": PAISES,
        "puede_pais": puede_cambiar_pais(email),
        "saldo": stores.saldo_centimos(email) / 100.0, "regalo": stores.saldo_promo_centimos(email) / 100.0,
        "pro": estado_pro(email), "plan": plan, "prefs": prefs_avisos.prefs(email),
        "doc": DOC.get(pais_cel if cel else iso, DOC["PE"])[0],
        "doc_iso": pais_cel if cel else iso,
    }


# ── Piezas ────────────────────────────────────────────────────────────────────

def _identidad(email: str, cx: dict) -> str:
    from web import almacen
    nombre = cx["nombre_completo"] or email
    foto = (f"<img id='vpFoto' src='{e(cx['foto'])}' alt='' referrerpolicy='no-referrer'>" if cx["foto"]
            else f"<span class='ini' id='vpFoto'>{e(nombre[:1].upper())}</span>")
    cam = ""
    if almacen.disponible():
        cam = (f"<button type='button' class='vp-cam' id='vpCam' aria-label='Cambiar mi foto'>{_svg('camara', 16)}</button>"
               "<input type='file' id='vpArchivo' accept='image/*' hidden>")
    rol = (va.pill("Recepción", "info", "comparar") if cx["solo_encargado"] else va.pill("Anfitrión", "info", "cancha"))
    ident = (va.pill("Identidad verificada", "ok", "escudo") if cx["verificado"]
             else f"<span class='va-pill warn'>{_svg('alerta', 13, 2.6)}Identidad pendiente</span>")
    partes = []
    if cx["locales"]:
        partes.append(_plural(cx["locales"], "local", "locales"))
    if cx["canchas"]:
        partes.append(_plural(len(cx["canchas"]), "cancha", "canchas"))
    if cx["academias"]:
        partes.append(_plural(len(cx["academias"]), "academia", "academias"))
    cuenta = " · ".join(partes) or "Aún no registras locales ni academias"
    return (f"<section class='vp-card vp-yo' aria-label='Tu cuenta'><div class='vp-av'>{foto}{cam}</div>"
            f"<b class='vp-nom' id='vpNomCard'>{e(nombre)}</b><small class='vp-mail'>{e(email)}</small>"
            f"<div class='vp-pills'>{rol}{ident}</div><p class='vp-cuenta'>{e(cuenta)}</p></section>")


_ACTUAL = " aria-current='true'"


def _menu() -> str:
    filas = "".join(
        f"<a href='#{k}' data-sec='{k}'{_ACTUAL if i == 0 else ''}>{_svg(ic, 18)}<span>{e(t)}</span>"
        f"<i aria-hidden='true'>›</i></a>" for i, (k, t, ic) in enumerate(SECCIONES))
    return (f"<nav class='vp-card vp-nav' aria-label='Secciones de tu perfil'>{filas}"
            f"<button type='button' class='vp-salir' onclick='window.pcgSalir&&pcgSalir()'>{_svg('salir', 18)}<span>Cerrar sesión</span></button></nav>")


def _cab_panel(ic: str, titulo: str, sub: str, acc: str = "", id_t: str = "") -> str:
    return (f"<div class='vp-pcab'>{_ic(ic)}<div class='vp-pcab-t'><h2" + (f" id='{id_t}'" if id_t else "") + f">{e(titulo)}</h2>"
            f"<p>{e(sub)}</p></div>" + (f"<div class='vp-pcab-acc'>{acc}</div>" if acc else "") + "</div>")


def _datos_personales(email: str, cx: dict) -> str:
    from web import catalogos
    pais = cx["pais_cel"]
    opciones = "".join(f"<option value='{iso}'{' selected' if iso == pais else ''}>+{catalogos.TEL_PREFIJO[iso]} {iso}</option>"
                       for iso, v in cx["PAISES"].items())
    largo = catalogos.TEL_LONGITUD[pais]
    return (f"<section class='vp-card vp-sec' id='datos' aria-labelledby='vpDatosT'>"
            + _cab_panel("persona", "Datos personales", "Así te ven tus jugadores, encargados y alumnos.",
                         "<button type='button' class='btn' id='vpGuardar'>Guardar cambios</button>", "vpDatosT")
            + "<div class='vp-form'>"
            f"<label class='vp-campo'><span>Nombre</span><span class='vp-in'>{_svg('persona', 16)}"
            f"<input id='vpNombre' maxlength='60' autocomplete='given-name' value='{e(cx['nombre'])}'></span></label>"
            f"<label class='vp-campo'><span>Apellido</span><span class='vp-in'>{_svg('persona', 16)}"
            f"<input id='vpApellido' maxlength='60' autocomplete='family-name' value='{e(cx['apellido'])}'></span></label>"
            f"<label class='vp-campo'><span>Correo de Google (inicio de sesión)</span><span class='vp-in bloq'>{_svg('correo', 16)}"
            f"<input value='{e(email)}' readonly aria-readonly='true' tabindex='-1'>{_svg('candado', 16)}</span></label>"
            "<div class='vp-campo'><span id='vpCelEt'>WhatsApp</span><div class='vp-cel'>"
            f"<label class='vh' for='vpPais'>País del WhatsApp</label><select id='vpPais' aria-label='País del WhatsApp'>{opciones}</select>"
            f"<span class='vp-in'>{_svg('whatsapp', 16)}<input id='vpCel' inputmode='numeric' autocomplete='tel-national' maxlength='{largo}' "
            f"placeholder='{largo} dígitos' value='{e(cx['local'])}' aria-labelledby='vpCelEt'></span></div>"
            "<small class='vp-err' id='vpErr' role='alert'></small></div>"
            "</div></section>")


def _verificacion(cx: dict) -> str:
    doc = cx["doc"]
    if cx["verificado"]:
        acc = va.pill("Verificada", "ok", "escudo")
        sub = f"Tu {doc} ya está validado: jugadores y alumnos ven tu insignia de verificado."
    else:
        acc = (f"<span class='va-pill warn'>{_svg('alerta', 13, 2.6)}Pendiente</span>"
               f"<a class='btn' href='/cuenta/identidad?pais={e(cx['doc_iso'])}'>{_svg('escudo', 16)}Verificar {e(doc)}</a>")
        sub = f"Valida tu {doc} para dar confianza a jugadores y alumnos."
    return (f"<section class='vp-card vp-sec' id='verificacion' aria-labelledby='vpVerT'>"
            + _cab_panel("escudo", "Verificación de identidad", sub, acc, "vpVerT") + "</section>")


def _saldo(cx: dict) -> str:
    sim = cx["P"]["moneda"]
    regalo = (f"<small class='vp-t-nota'>+ {e(_monto(sim, cx['regalo']))} de regalo para comisiones</small>"
              if cx["regalo"] > 0 else "")
    t_saldo = (f"<div class='vp-t'><div class='vp-t-top'>{_ic('billetera', 'azul')}</div><small>Saldo {e(MARCA)}</small>"
               f"<b class='vp-t-v{' cero' if cx['saldo'] <= 0 else ''}'>{e(_monto(sim, cx['saldo']))}</b>{regalo}"
               "<a class='vp-t-ir' href='/mi-billetera#recargar'>Recargar saldo ›</a></div>")
    pro = cx["pro"]
    p_txt = _monto(pro["sim"], pro["precio"])
    if pro["activa"]:
        from web.jugador_pro import _fecha
        hasta = _fecha(pro.get("hasta"))
        pill = va.pill("Cortesía" if pro.get("cortesia") else "Activo", "ok")
        val, ir = "Activo", f"<a class='vp-t-ir' href='/pro'>Ver mi plan · {e(p_txt)}/mes ›</a>"
        extra = f"<small class='vp-t-nota'>Hasta el {e(hasta)}</small>" if hasta else ""
    else:
        pill, val, extra = va.pill("Inactivo", "gris"), "No activo", ""
        ir = f"<a class='vp-t-ir' href='/pro'>Activar · {e(p_txt)}/mes ›</a>"
    t_pro = (f"<div class='vp-t'><div class='vp-t-top'>{_ic('corona', 'azul')}{pill}</div><small>{e(MARCA)} Pro</small>"
             f"<b class='vp-t-v'>{e(val)}</b>{extra}{ir}</div>")
    t_plan = ""
    if cx["plan"]:
        a, st = cx["plan"]["academia"], cx["plan"]["estado"]
        precio = _monto(st.get("simbolo") or "S/", st.get("precio") or 0)
        dias = int(st.get("dias_restantes") or 0)
        est = st.get("estado")
        if est == "prueba":
            pill, val = va.pill(_plural(dias, "día", "días"), "warn"), "Prueba gratis"
        elif est == "activa":
            pill, val = va.pill(_plural(dias, "día", "días"), "ok"), "Vigente"
        else:
            pill, val = va.pill("Vencido", "bad"), "Vencido"
        nombre = a.get("nombre") or "Tu academia"
        mas = cx["plan"]["n"] - 1
        sub = nombre + (f" y {_plural(mas, 'academia más', 'academias más')}" if mas > 0 else "")
        t_plan = (f"<div class='vp-t'><div class='vp-t-top'>{_ic('academias', 'azul')}{pill}</div><small>Plan Academia</small>"
                  f"<b class='vp-t-v{' bad' if est == 'vencida' else ''}'>{e(val)}</b><small class='vp-t-nota'>{e(sub)}</small>"
                  f"<a class='vp-t-ir' href='/anfitrion/academia/plan?academia={e(quote(str(a.get('id') or '')))}'>"
                  f"{'Renovar' if est == 'vencida' else 'Ver plan'} · {e(precio)}/mes ›</a></div>")
    return (f"<section class='vp-card vp-sec' id='saldo' aria-labelledby='vpSaldoT'>"
            + _cab_panel("billetera", "Saldo y suscripciones", f"Se cobran de tu saldo {MARCA}, la misma billetera de la app.", "", "vpSaldoT")
            + f"<div class='vp-tarjetas{' tres' if t_plan else ''}'>{t_saldo}{t_pro}{t_plan}</div></section>")


def _avisos(cx: dict) -> str:
    filas = "".join(
        f"<div class='vp-av-f'><span class='vp-av-ic'>{_svg(ic, 18)}</span><span class='tx'><b id='vpAv_{k}'>{e(t)}</b><small>{e(d)}</small></span>"
        f"<button type='button' class='vp-sw' role='switch' aria-checked='{'true' if cx['prefs'].get(k, True) else 'false'}' "
        f"aria-labelledby='vpAv_{k}' data-pref='{k}'><i></i></button></div>"
        for k, ic, t, d in _avisos_filas(cx["iso"], cx["prefs"]))
    nota = ("<p class='vp-nota'>" + _svg("recibo", 16) + "<span>Los <b>recibos y comprobantes de pago por correo</b> te llegan siempre: "
            "son la constancia de cada cobro. Las devoluciones que debas hacer y las cancelaciones también se avisan siempre. "
            "Si apagas «Pagos por confirmar», revisa esa bandeja a diario: los comprobantes sin revisar vencen y liberan el horario.</span></p>")
    return (f"<section class='vp-card vp-sec' id='avisos' aria-labelledby='vpAvT'>"
            + _cab_panel("campana", "Notificaciones", "Te avisamos en tu celular (app) cuando pasa algo en tu negocio.", "", "vpAvT")
            + f"<div class='vp-av-lista'>{filas}</div>{nota}</section>")


def _preferencias(cx: dict) -> str:
    P, iso = cx["P"], cx["iso"]
    opciones = "".join(f"<option value='{k}'{' selected' if k == iso else ''}>{e(v['nombre'])} · {e(v['moneda'])}</option>"
                       for k, v in cx["PAISES"].items())
    if cx["puede_pais"]:
        nota = f"Define la moneda de tu billetera. Recargas con {P['pasarela_nombre']}."
        dis = ""
    else:
        nota = (f"Tu billetera tiene saldo en {P['moneda']}: para cambiar de país primero úsalo o solicita su liquidación. "
                "Después podrás elegir otro país.")
        dis = " disabled aria-describedby='vpPaisNota'"
    return (f"<section class='vp-card vp-sec' id='preferencias' aria-labelledby='vpPrefT'>"
            + _cab_panel("filtros", "Preferencias", "País y moneda de tu cuenta.", "", "vpPrefT")
            + "<div class='vp-campo'><span id='vpPaisEt'>País</span>"
            f"<span class='vp-in sel'><span class='vp-flag'>{ui.bandera(iso)}</span>"
            f"<select id='vpPaisCasa' aria-labelledby='vpPaisEt' data-actual='{e(iso)}'{dis}>{opciones}</select></span>"
            f"<small class='vp-ayuda{' warn' if not cx['puede_pais'] else ''}' id='vpPaisNota'>{e(nota)}</small></div>"
            "</section>")


def _privacidad() -> str:
    def fila(ic: str, titulo: str, accion: str, *, href: str = "", btn_id: str = "", rojo: bool = False, clase: str = "") -> str:
        cls = f"vp-pf{' rojo' if rojo else ''} {clase}".strip()
        cuerpo = f"<span class='vp-pf-ic'>{_svg(ic, 18)}</span><span class='tx'>{e(titulo)}</span><span class='ir'>{e(accion)}</span>"
        if btn_id:
            return f"<button type='button' class='{cls}' id='{btn_id}'>{cuerpo}</button>"
        return f"<a class='{cls}' href='{e(href)}'>{cuerpo}</a>"
    return (f"<section class='vp-card vp-sec' id='privacidad' aria-labelledby='vpPrivT'>"
            + _cab_panel("candado", "Privacidad y seguridad", "Tu cuenta y tus sesiones.", "", "vpPrivT")
            + "<div class='vp-pf-lista'>"
            + fila("celular", "Cerrar sesión en todos los dispositivos", "Cerrar ›", btn_id="vpCerrarTodas")
            + fila("intercambio", "Cambiar a modo jugador", "Cambiar ›", href="/")
            + "<button type='button' class='vp-pf vp-solo-mov' onclick='window.pcgSalir&&pcgSalir()'>"
              f"<span class='vp-pf-ic'>{_svg('salir', 18)}</span><span class='tx'>Cerrar sesión en este navegador</span><span class='ir'>Salir ›</span></button>"
            + fila("papelera", "Eliminar mi cuenta", "Eliminar", href="/legal/eliminar-cuenta", rojo=True)
            + "</div></section>")


# ── Página ────────────────────────────────────────────────────────────────────

@router.get("/anfitrion/perfil", response_class=HTMLResponse)
def pagina_perfil_anfitrion(request: Request) -> HTMLResponse:
    from web.anfitrion import _sesion_o_entrar
    ses, resp = _sesion_o_entrar(request, "/anfitrion/perfil")
    if resp is not None:
        return resp
    email = (ses.get("email") or "").strip().lower()
    cx = _contexto_perfil(email, ses)
    from web import catalogos
    from web import almacen
    cfg = {"bio": cx["bio"], "largo": catalogos.TEL_LONGITUD, "subida": almacen.disponible()}
    cuerpo = va.vista(
        va.cabecera("Mi perfil", "Tus datos, verificación, saldo, suscripciones y cómo quieres que te avisemos.",
                    volver="/anfitrion", volver_txt="Modo anfitrión")
        + "<div class='vp-grid'><aside class='vp-lado'>" + _identidad(email, cx) + _menu() + "</aside>"
        + "<div class='vp-main'>" + _datos_personales(email, cx) + _verificacion(cx) + _saldo(cx) + _avisos(cx)
        + "<div class='vp-dos'>" + _preferencias(cx) + _privacidad() + "</div></div></div>", clase="vp")
    cuerpo += "<script>window.VP=" + ui.json_js(cfg, ensure_ascii=False) + ";</script><script>" + JS + "</script>"
    return ui.shell("Mi perfil", cuerpo, sesion=ses, ancho=True, titulo_tab=f"Mi perfil · {MARCA}")


# ── JSON ──────────────────────────────────────────────────────────────────────

@router.get("/web/avisos/prefs")
def ver_prefs_avisos(request: Request):
    import prefs_avisos
    ses = sesion.de_request(request)
    if not ses:
        return JSONResponse({"ok": False, "error": "sesion_requerida", "mensaje": "Inicia sesión."}, status_code=401)
    return {"ok": True, "prefs": prefs_avisos.prefs(ses["email"])}


@router.post("/web/avisos/prefs")
def guardar_prefs_avisos(request: Request, body: dict = Body(default_factory=dict)):
    """{clave, on} (un interruptor) o {prefs: {clave: bool}} (varios)."""
    import prefs_avisos
    ses = sesion.de_request(request)
    if not ses:
        return JSONResponse({"ok": False, "error": "sesion_requerida", "mensaje": "Inicia sesión."}, status_code=401)
    body = body if isinstance(body, dict) else {}
    cambios = body.get("prefs") if isinstance(body.get("prefs"), dict) else {}
    if body.get("clave") is not None:
        cambios = {str(body.get("clave")): body.get("on")}
    cambios = {k: v for k, v in cambios.items() if k in prefs_avisos.TIPOS and isinstance(v, bool)}
    if not cambios:
        return JSONResponse({"ok": False, "error": "pref_invalida", "mensaje": "Elige un aviso válido."}, status_code=400)
    return {"ok": True, "prefs": prefs_avisos.guardar(ses["email"], cambios)}


@router.post("/web/sesion/cerrar-todas")
def cerrar_todas_las_sesiones(request: Request):
    """Cierra la sesión en TODOS los navegadores (sube la época del correo) y
    re-emite la cookie de este, para que quien lo pidió siga dentro."""
    ses = sesion.de_request(request)
    if not ses:
        return JSONResponse({"ok": False, "error": "sesion_requerida", "mensaje": "Inicia sesión."}, status_code=401)
    sesion.cerrar_todas(ses["email"])
    print(f"[sesion] {ses['email']} cerró la sesión en todos los dispositivos", flush=True)
    resp = JSONResponse({"ok": True, "mensaje": "Cerramos tu sesión en los demás navegadores. Aquí sigues dentro."})
    sesion.poner_cookie(resp, sesion.emitir(ses))
    return resp


JS = r"""
(function(){
var C = window.VP || {}, $ = function(i){ return document.getElementById(i); };
// Menú de secciones: marca la que está a la vista.
var links = document.querySelectorAll('.vp-nav a[data-sec]');
function marcar(id){ links.forEach(function(a){ if(a.dataset.sec === id){ a.setAttribute('aria-current', 'true'); if(a.scrollIntoView && window.innerWidth <= 860){ var n = a.parentNode; n.scrollLeft = a.offsetLeft - 16; } } else a.removeAttribute('aria-current'); }); }
if('IntersectionObserver' in window){
  var io = new IntersectionObserver(function(ent){ ent.forEach(function(x){ if(x.isIntersecting) marcar(x.target.id); }); }, {rootMargin: '-35% 0px -60% 0px'});
  document.querySelectorAll('.vp-sec[id]').forEach(function(s){ io.observe(s); });
}
links.forEach(function(a){ a.addEventListener('click', function(){ marcar(a.dataset.sec); }); });
// Foto: mismo endpoint de Configuración (se comprime a 800 px).
function comprimir(file){ return new Promise(function(res, rej){ var img = new Image(), u = URL.createObjectURL(file);
  img.onload = function(){ var k = Math.min(1, 800 / Math.max(img.width, img.height)), cv = document.createElement('canvas'); cv.width = Math.round(img.width * k); cv.height = Math.round(img.height * k);
    cv.getContext('2d').drawImage(img, 0, 0, cv.width, cv.height); URL.revokeObjectURL(u); cv.toBlob(function(b){ b ? res(b) : rej(); }, 'image/jpeg', 0.82); };
  img.onerror = function(){ URL.revokeObjectURL(u); rej(); }; img.src = u; }); }
if($('vpCam')){ $('vpCam').onclick = function(){ $('vpArchivo').click(); };
  $('vpArchivo').onchange = function(){ var f = this.files && this.files[0]; this.value = ''; if(!f) return;
    pcgCargando('Subiendo tu foto…');
    comprimir(f).then(function(b){ return fetch('/web/cuenta/foto', {method: 'POST', headers: {'Content-Type': 'image/jpeg'}, body: b}); })
      .then(function(r){ return r.json(); }).then(function(j){ pcgCargando(false);
        if(!j.ok) return pcgAvisar({titulo: 'No se pudo', icono: '⚠️', mensaje: j.mensaje || 'Reintenta.'});
        var el = $('vpFoto'), im = document.createElement('img'); im.id = 'vpFoto'; im.alt = ''; im.src = j.foto; el.replaceWith(im); pcgToast('Foto actualizada.'); })
      .catch(function(){ pcgCargando(false); pcgAvisar({titulo: 'No se pudo', icono: '⚠️', mensaje: 'No se pudo subir la foto. Reintenta.'}); }); }; }
// Datos personales: el MISMO guardado de Configuración (nombre completo + celular + la bio que ya tenía).
var pais = $('vpPais');
pais.addEventListener('change', function(){ var l = C.largo[pais.value]; $('vpCel').maxLength = l; $('vpCel').placeholder = l + ' dígitos'; $('vpErr').textContent = ''; });
$('vpCel').addEventListener('input', function(){ this.value = this.value.replace(/\D/g, ''); $('vpErr').textContent = ''; });
$('vpGuardar').onclick = function(){ var btn = this; if(btn.disabled) return;
  var n = $('vpNombre').value.trim(), a = $('vpApellido').value.trim(), cel = $('vpCel').value.trim();
  if(!n){ pcgAvisar({titulo: 'Falta tu nombre', icono: '✍️', mensaje: 'Escribe tu nombre.'}).then(function(){ $('vpNombre').focus(); }); return; }
  if(cel && cel.length !== C.largo[pais.value]){ $('vpErr').textContent = 'El WhatsApp tiene ' + C.largo[pais.value] + ' dígitos.'; $('vpCel').focus(); return; }
  btn.disabled = true; pcgCargando('Guardando…');
  fetch('/web/cuenta/perfil', {method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({nombre: (n + ' ' + a).trim(), pais: pais.value, celular: cel, bio: C.bio || {}})})
    .then(function(r){ return r.json(); }).then(function(j){ btn.disabled = false; pcgCargando(false);
      if(!j.ok){ if(j.campo === 'celular'){ $('vpErr').textContent = j.mensaje; $('vpCel').focus(); return; }
        return pcgAvisar({titulo: 'No se pudo guardar', icono: '⚠️', mensaje: j.mensaje || 'Reintenta.'}); }
      $('vpNomCard').textContent = (n + ' ' + a).trim(); pcgToast('Datos guardados.'); })
    .catch(function(){ btn.disabled = false; pcgCargando(false); pcgAvisar({titulo: 'Sin conexión', icono: '📶', mensaje: 'Revisa tu internet y reintenta.'}); }); };
// Notificaciones: cada interruptor se guarda al instante; si falla vuelve atrás.
document.querySelectorAll('.vp-sw[data-pref]').forEach(function(sw){ sw.addEventListener('click', function(){
  if(sw.dataset.ocupado) return; var on = sw.getAttribute('aria-checked') !== 'true'; sw.dataset.ocupado = '1'; sw.setAttribute('aria-checked', on ? 'true' : 'false');
  fetch('/web/avisos/prefs', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({clave: sw.dataset.pref, on: on})})
    .then(function(r){ return r.json(); }).then(function(j){ delete sw.dataset.ocupado;
      if(!j.ok) throw 0; pcgToast(on ? 'Aviso encendido.' : 'Aviso apagado.'); })
    .catch(function(){ delete sw.dataset.ocupado; sw.setAttribute('aria-checked', on ? 'false' : 'true'); pcgToast('No se pudo guardar. Reintenta.'); });
}); });
// País de la billetera: misma regla y endpoint que Mi país.
var pc = $('vpPaisCasa');
pc.addEventListener('change', function(){ var nuevo = pc.value, nom = pc.options[pc.selectedIndex].text.split(' · ')[0];
  pcgConfirmar({titulo: 'Cambiar a ' + nom, icono: '🌎', confirmar: 'Sí, cambiar', cancelar: 'Cancelar',
                mensaje: 'Tu billetera pasará a la moneda de ' + nom + ' y tu próxima recarga será en esa moneda.'}).then(function(ok){
    if(!ok){ pc.value = pc.dataset.actual; return; } pcgCargando('Guardando…');
    fetch('/web/mi-pais', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({iso: nuevo})})
      .then(function(r){ return r.json(); }).then(function(p){ pcgCargando(false);
        if(p.ok){ pcgAvisar({titulo: 'Listo', icono: '✅', confirmar: 'Entendido', mensaje: p.mensaje}).then(function(){ pcgRecargar(); }); }
        else { pc.value = pc.dataset.actual; pcgAvisar({titulo: 'No se pudo cambiar', icono: '👛', confirmar: 'Entendido', mensaje: p.mensaje || 'Intenta de nuevo.'}); } })
      .catch(function(){ pcgCargando(false); pc.value = pc.dataset.actual; pcgToast('Sin conexión. Intenta de nuevo.'); });
  }); });
// Cerrar sesión en todos los dispositivos.
$('vpCerrarTodas').onclick = function(){
  pcgConfirmar({titulo: 'Cerrar sesión en todos lados', icono: '🔒', destructivo: true, confirmar: 'Cerrar las demás', cancelar: 'Cancelar',
                mensaje: 'Cerraremos tu sesión web en todos los navegadores donde entraste con esta cuenta (computadoras, celulares, tablets). En este navegador sigues dentro.'}).then(function(ok){
    if(!ok) return; pcgCargando('Cerrando sesiones…');
    fetch('/web/sesion/cerrar-todas', {method: 'POST'}).then(function(r){ return r.json(); }).then(function(j){ pcgCargando(false);
      if(!j.ok) return pcgAvisar({titulo: 'No se pudo', icono: '⚠️', mensaje: j.mensaje || 'Reintenta.'});
      pcgAvisar({titulo: 'Sesiones cerradas', icono: '✅', confirmar: 'Entendido', mensaje: j.mensaje}); })
      .catch(function(){ pcgCargando(false); pcgToast('Sin conexión. Intenta de nuevo.'); });
  }); };
})();
"""
