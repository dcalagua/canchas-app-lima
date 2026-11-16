"""Barra del MODO ANFITRIÓN (rediseño del diseñador, 16-nov-2026).

Capturas "CanchaLibre Anfitrión" + "Modo Anfitrión - Mi Club/Negocios/…" +
"Ventanas color" de `Downloads/Soluciones EBIM_2` (plan en
`docs/plan/REDISENO_ANFITRION.md`): barra BLANCA con el logo azul, los cinco
menús desplegables (los mismos grupos de `anfitrion.GRUPOS_MENU`), la pastilla
"Modo anfitrión" y el avatar con el menú de la cuenta.

Va en TODA página `/anfitrion/*` con sesión: `ui.shell()` la pone sola (antes
academia, tienda, bodega, campeonatos, boleador y verificador salían con la
cabecera del jugador) y `ui.cabecera(modo="anfitrion")` la devuelve para las
páginas que ya la pedían. Las pestañas Hoy/Calendario/Reservas/Ingresos/Canchas
quedan como sub-navegación de Mis canchas hasta que la fase F2 las unifique.

Un solo marcado para escritorio y celular: cada grupo es un `<details>`. En
escritorio el panel flota (uno abierto a la vez, se cierra con clic fuera o
Esc); en ≤1100 px el botón "Menú" abre la lista entera y los grupos son un
acordeón. Sin JS sigue funcionando (details nativo).
"""

from __future__ import annotations

import html as _html

# Color del cuadrado de cada módulo ("Ventanas color.png") + ícono de línea
# (`web/iconos.py`) en blanco. Decorativos (aria-hidden): el texto va al lado.
ICONOS: dict[str, tuple[str, str]] = {
    "mis-canchas": ("#3056ED", "cancha"),
    "cobros-club": ("#16A15A", "billete"),
    "pagos-por-confirmar": ("#EE8A12", "recibo"),
    "encargados": ("#5B47E0", "auricular"),
    "reglas": ("#475467", "portapapeles"),
    "disponibilidad": ("#16AFD3", "interruptor"),
    "fijas": ("#1E7F45", "calendario"),
    "reportes": ("#3056ED", "barras"),
    "caja": ("#0E8FA3", "caja"),
    "clientes": ("#B02160", "comparar"),
    "llenar": ("#1C8FE0", "etiqueta"),
    "recordatorios": ("#DC3B2E", "campana"),
    "bonos": ("#B829C9", "bono"),
    "campeonatos": ("#EDA514", "trofeo"),
    "academia": ("#3056ED", "academias"),
    "cobros": ("#16A15A", "tarjeta"),
    "plan-academia": ("#7E98FF", "edificio"),
    "tienda": ("#E11D48", "tienda"),
    "bodega": ("#EC7A97", "archivo"),
    "boleador": ("#3056ED", "boleador"),
    "verificador": ("#17257A", "escudo"),
}

# Textos cortos del desplegable (los del diseñador, sin jerga de un solo país:
# Culqi/Yape/Plin solo existen en Perú — regla MULTI-PAÍS).
DESC: dict[str, str] = {
    "mis-canchas": "Registra y administra canchas, agenda y reservas",
    "cobros-club": "Tu cobro en línea, medios de pago manuales y comisión",
    "pagos-por-confirmar": "Comprobantes de pago que debes revisar",
    "encargados": "Invita a recepción a operar agenda y pagos",
    "reglas": "Horarios, días cerrados, franjas y cancelación",
    "disponibilidad": "Abre o cierra turnos de tus canchas",
    "fijas": "Pensionados: mismo día y hora, cada semana",
    "reportes": "Resumen, ocupación, cobros y cancelaciones",
    "caja": "Cobrado, por cobrar y cierre de caja",
    "clientes": "Frecuentes, VIP, en riesgo y deudores",
    "llenar": "Horas libres de hoy y mañana: pon una promo",
    "recordatorios": "Avisa a tus clientes por chat o WhatsApp",
    "bonos": "Packs de horas prepagadas de tu local",
    "campeonatos": "Organiza torneos, invita y sortea",
    "academia": "Alumnos, cuotas y cobros",
    "cobros": "Quién debe, recordatorios y cobro en efectivo",
    "plan-academia": "Tu suscripción: prueba gratis y precio fijo al mes",
    "bodega": "Caja rápida, stock, pedidos y carta con QR (Pro)",
    "boleador": "Peloteo por turno: categoría, tarifa y zona",
    "verificador": "Rol de campo: visitas con foto, GPS y firma",
}

# Páginas que no son un ítem del menú pero pertenecen a uno (para marcarlo).
_ALIAS = (
    ("/anfitrion/calendario", "mis-canchas"), ("/anfitrion/reservas", "mis-canchas"),
    ("/anfitrion/ingresos", "mis-canchas"), ("/anfitrion/canchas", "mis-canchas"),
    ("/anfitrion/cancha/", "mis-canchas"), ("/anfitrion/local/", "mis-canchas"),
    ("/anfitrion/nueva", "mis-canchas"), ("/anfitrion/verificacion/", "mis-canchas"),
    ("/anfitrion/ocupacion", "reportes"), ("/anfitrion/cancelaciones", "reportes"),
)

_CHEV_ABAJO = ("<svg class='chev' viewBox='0 0 24 24' width='16' height='16' fill='none' stroke='currentColor' stroke-width='2.6' "
               "stroke-linecap='round' stroke-linejoin='round' aria-hidden='true'><path d='M6 9l6 6 6-6'/></svg>")
_CHEV_DER = ("<svg viewBox='0 0 24 24' width='18' height='18' fill='none' stroke='currentColor' stroke-width='2.4' "
             "stroke-linecap='round' stroke-linejoin='round' aria-hidden='true'><path d='M9 6l6 6-6 6'/></svg>")
_GRILLA = ("<svg viewBox='0 0 24 24' width='20' height='20' fill='none' stroke='currentColor' stroke-width='2.2' "
           "stroke-linecap='round' aria-hidden='true'><path d='M4 7h16M4 12h16M4 17h16'/></svg>")


def e(s) -> str:
    return _html.escape(str(s if s is not None else ""), quote=True)


def clave_actual(ruta: str, items: list[tuple]) -> str:
    """Clave del módulo de la ruta: el ítem con el enlace más largo que la
    contiene (así /anfitrion/academia/plan es "plan-academia" y no "academia");
    si ninguno, los alias de `_ALIAS`. "" en el inicio /anfitrion."""
    ruta = (ruta or "").rstrip("/") or "/"
    mejor, largo = "", 0
    for it in items:
        k, href = it[0], it[5]
        if (ruta == href or ruta.startswith(href + "/")) and len(href) > largo:
            mejor, largo = k, len(href)
    if mejor:
        return mejor
    for pref, k in _ALIAS:
        p = pref.rstrip("/")
        if ruta == p or ruta.startswith(p + "/"):
            return k
    return ""


def _ocultas(ses: dict | None) -> frozenset:
    """Lo que esta cuenta no debe ver en la barra: quien SOLO es encargado
    (Recepción) no ve plata ni configuración (`permisos.MENU_SOLO_DUENO`) ni
    Encargados; sin la migración de encargados el ítem no existe; Plan Academia
    solo con el modelo de suscripción. Nunca rompe la página."""
    ocultar: set[str] = set()
    try:
        from web import encargados, permisos
        if not encargados.disponible():
            ocultar.add("encargados")
        elif ses and permisos.es_solo_encargado(ses.get("email") or ""):
            ocultar |= set(permisos.MENU_SOLO_DUENO) | {"encargados"}
    except Exception:  # noqa: BLE001 — la barra jamás tumba una página
        pass
    try:
        from web.anfitrion import _plan_academia_activo
        if not _plan_academia_activo():
            ocultar.add("plan-academia")
    except Exception:  # noqa: BLE001
        pass
    return frozenset(ocultar)


def _desc(k: str) -> str:
    if k == "tienda":
        from config import MARCA
        return f"Vende en el Marketplace {MARCA}"
    return DESC.get(k, "")


def _item(k: str, titulo: str, desc: str, href: str, sel: bool) -> str:
    from web import iconos
    color, ico = ICONOS.get(k, ("#3056ED", "estrella"))
    return (f"<a class='anf-dd-it{' sel' if sel else ''}' role='menuitem' href='{e(href)}'"
            + (" aria-current='page'" if sel else "")
            + f"><span class='ic' style='background:{color}'>{iconos.svg(ico, 20, grueso=2.2)}</span>"
            f"<span class='tx'><b>{e(titulo)}</b><small>{e(_desc(k) or desc)}</small></span>"
            f"<span class='ir'>{_CHEV_DER}</span></a>")


def menu_html(ses: dict | None, ruta: str = "") -> str:
    """Los grupos como `<details>` (desplegables en escritorio, acordeón en el
    celular). Un grupo sin ítems visibles no se pinta."""
    from web.anfitrion import GRUPOS_MENU
    items = [it for _g, its in GRUPOS_MENU for it in its]
    actual = clave_actual(ruta, items)
    ocultar = _ocultas(ses)
    out = ""
    for i, (nombre, its) in enumerate(GRUPOS_MENU):
        vis = [it for it in its if it[0] not in ocultar]
        if not vis:
            continue
        sel = any(it[0] == actual for it in vis)
        n = len(vis)
        filas = "".join(_item(it[0], it[1], it[2], it[5], it[0] == actual) for it in vis)
        out += (f"<details class='anf-dd{' sel' if sel else ''}' data-grupo='{i}'>"
                f"<summary class='anf-dd-btn'><span>{e(nombre)}</span>{_CHEV_ABAJO}</summary>"
                f"<div class='anf-dd-panel' role='menu' aria-label='{e(nombre)}'>"
                f"<div class='anf-dd-cab'><b>{e(nombre)}</b><small>{n} {'opción' if n == 1 else 'opciones'}</small></div>"
                f"{filas}</div></details>")
    return out


def _logo(ui) -> str:
    """Logo APILADO azul ("CANCHA / LIBRE" + isotipo), la variante que eligió el
    usuario para la barra; con otra marca o logo propio de la torre, el de siempre."""
    if ui._logo_propio_cl():
        from config import MARCA
        return (f"<a class='wm-cl anf-logo' href='/anfitrion' aria-label='{e(MARCA)} · inicio del modo anfitrión'>"
                "<img class='wm-ico' src='/static/brand/cl_icono_azul.png' alt='' width='34' height='36'>"
                f"<img class='anf-logo-txt' src='/static/brand/cl_apilado_azul.png' alt='{e(MARCA)}' width='84' height='36'></a>")
    return ui.wordmark(24, '/anfitrion', color='azul')


def barra(ses: dict | None, tabs: str = "", volver: str = "/anfitrion") -> str:
    """Cabecera completa del modo anfitrión (reemplaza a la barra azul de
    `ui.cabecera` en modo anfitrión). [tabs] = sub-navegación opcional."""
    from web import iconos, ui
    ruta = ui.RUTA_REQUEST.get() or ""
    cuenta = ui.menu_cuenta(ses, volver, "anfitrion")
    # Pastilla del diseño: dice en qué modo estás; tocarla cambia a modo jugador.
    pill = (f"<a class='anf-modo' href='/' title='Estás en modo anfitrión · toca para cambiar a modo jugador' "
            f"aria-label='Estás en modo anfitrión. Cambiar a modo jugador'><span>Modo anfitrión</span>{iconos.svg('intercambio', 16, grueso=2.4)}</a>")
    cuenta = cuenta.replace("<a class='host' href='/'>Cambiar a modo jugador</a>", pill)
    # En modo anfitrión "Perfil" lleva a Mi perfil del anfitrión (`web/anfitrion_perfil.py`).
    cuenta = cuenta.replace("<a class='b' href='/perfil'>👤 Perfil</a>", "<a class='b' href='/anfitrion/perfil'>👤 Mi perfil</a>")
    if ses:
        # El avatar ABRE el menú de la cuenta (el diseño no tiene ☰ aparte).
        avatar_link = f"<a class='redondo' href='/perfil' title='{e(ses.get('email'))}' aria-label='Tu perfil'>{ui._avatar(ses)}</a>"
        cuenta = cuenta.replace(avatar_link, "").replace(
            f"id='btnMenu' aria-label='Menú' aria-expanded='false'>{ui._HAMB_SVG}",
            f"id='btnMenu' aria-label='Tu cuenta' aria-expanded='false'>{ui._avatar(ses)}")
    nav = menu_html(ses, ruta) if ses else ""
    sub = (f"<div class='anf-sub'><div class='wrap-xl'><nav class='anf-subtabs' aria-label='Mis canchas'>{tabs}</nav></div></div>"
           if tabs else "")
    return ("<header class='nav anf-cab'><div class='anf-barra'><div class='wrap-xl anf-barra-in'>"
            f"<div class='cab-logo'>{_logo(ui)}</div>"
            + (f"<nav class='anf-nav' id='anfNav' aria-label='Módulos del modo anfitrión'>{nav}</nav>"
               f"<button type='button' class='anf-nav-btn' id='anfNavBtn' aria-controls='anfNav' aria-expanded='false'>{_GRILLA}<span>Menú</span></button>"
               if nav else "<div class='anf-nav-vacia'></div>")
            + f"{cuenta}</div></div>{sub}</header><script src='{ui._seg().url_nav()}'></script>")


CSS = r"""
/* ═════════ MODO ANFITRIÓN · barra con desplegables (diseñador, 16-nov-2026) ═════════ */
body.pcg-anf{background:var(--anf-fondo)}
header.anf-cab{display:block;position:sticky;top:0;z-index:30}
.anf-barra{background:#fff;border-bottom:1px solid var(--anf-borde);position:relative;z-index:2}
.anf-barra-in{display:flex;align-items:center;gap:20px;height:64px;position:relative}
.anf-barra .cab-logo{flex:none;height:64px;display:flex;align-items:center}
.anf-logo{gap:8px}.anf-logo .wm-ico{height:36px;width:auto}.anf-logo-txt{height:34px;width:auto;display:block}
.anf-nav{flex:1;display:flex;justify-content:center;gap:2px;min-width:0}
.anf-nav-vacia{flex:1}
.anf-dd{position:relative}
.anf-dd>summary{list-style:none;display:flex;align-items:center;gap:6px;padding:10px 14px;border-radius:10px;font-weight:700;font-size:15px;color:var(--anf-texto);cursor:pointer;min-height:44px;white-space:nowrap;user-select:none}
.anf-dd>summary::-webkit-details-marker{display:none}
.anf-dd>summary:hover{background:var(--anf-fondo)}
.anf-dd>summary:focus-visible{outline:2px solid var(--azul);outline-offset:2px}
.anf-dd>summary .chev{transition:transform .15s}
.anf-dd[open]>summary .chev{transform:rotate(180deg)}
.anf-dd.sel>summary{color:var(--azul)}
.anf-dd-panel{position:absolute;top:calc(100% + 10px);left:0;width:420px;max-width:calc(100vw - 24px);background:#fff;border-radius:16px;box-shadow:0 18px 44px rgba(20,33,90,.16);border:1px solid var(--anf-borde);padding:12px 8px 8px;z-index:50}
.anf-dd-panel.der{left:auto;right:0}
.anf-dd-cab{display:flex;justify-content:space-between;align-items:baseline;padding:2px 12px 10px}
.anf-dd-cab b{font-size:12px;font-weight:800;letter-spacing:.05em;text-transform:uppercase;color:var(--anf-texto)}
.anf-dd-cab small{font-size:12px;color:var(--anf-tenue)}
.anf-dd-it{display:flex;align-items:center;gap:14px;padding:11px 12px;border-radius:12px;text-decoration:none;color:var(--anf-texto);min-height:44px}
.anf-dd-it:hover,.anf-dd-it:focus-visible,.anf-dd-it.sel{background:var(--anf-fondo)}
.anf-dd-it:focus-visible{outline:2px solid var(--azul);outline-offset:-2px}
.anf-dd-it .ic{width:38px;height:38px;border-radius:10px;display:inline-flex;align-items:center;justify-content:center;color:#fff;flex:none}
.anf-dd-it .tx{flex:1;min-width:0;display:flex;flex-direction:column;gap:2px}
.anf-dd-it .tx b{font-size:15px;font-weight:700;line-height:1.25}
.anf-dd-it .tx small{font-size:13px;color:var(--anf-tenue);line-height:1.3}
.anf-dd-it .ir{color:var(--azul);display:inline-flex;flex:none}
.anf-nav-btn{display:none;align-items:center;gap:8px;min-height:42px;padding:0 14px;border-radius:999px;border:1px solid var(--anf-borde);background:#fff;color:var(--anf-texto);font:inherit;font-weight:700;font-size:14px;cursor:pointer;margin-left:auto}
.anf-cab .cab-der{height:auto;gap:10px;flex:none}
.anf-modo{display:inline-flex;align-items:center;gap:8px;background:var(--azul);color:#fff;font-weight:700;font-size:15px;border-radius:999px;padding:0 18px;min-height:42px;text-decoration:none;white-space:nowrap}
.anf-modo:hover{background:var(--azul-osc)}
.anf-cab .redondo{background:var(--azul-tinte);color:var(--azul)}
.anf-cab .redondo .ini{background:var(--azul-tinte);color:var(--azul)}
.anf-sub{background:#fff;border-bottom:1px solid var(--anf-borde)}
.anf-subtabs{display:flex;gap:8px;overflow-x:auto;padding:10px 0;scrollbar-width:none}
.anf-subtabs::-webkit-scrollbar{display:none}
.anf-subtabs .cat{padding:8px 14px;border-radius:999px;background:var(--anf-fondo);color:var(--anf-texto);font-size:14px;font-weight:600;border:0;min-height:40px}
.anf-subtabs .cat:after,.anf-subtabs .cat:hover:after{display:none}
.anf-subtabs .cat .ico{font-size:16px}
.anf-subtabs .cat.sel{background:var(--azul);color:#fff}
/* vistas: tarjetas blancas con borde suave sobre el fondo celeste */
body.pcg-anf .panel{border:1px solid var(--anf-borde);box-shadow:0 1px 2px rgba(20,33,90,.04);border-radius:16px}
body.pcg-anf .anf-hola{color:var(--anf-texto);letter-spacing:-.01em}
@media(max-width:1100px){
  .anf-nav{display:none;position:absolute;top:64px;left:0;right:0;flex-direction:column;justify-content:flex-start;gap:0;background:#fff;border-bottom:1px solid var(--anf-borde);box-shadow:0 18px 30px rgba(20,33,90,.12);padding:8px 16px 16px;max-height:calc(100vh - 64px);max-height:calc(100dvh - 64px);overflow-y:auto;overscroll-behavior:contain}
  .anf-nav.abierta{display:flex}
  .anf-nav-btn{display:inline-flex}
  .anf-dd>summary{justify-content:space-between;font-size:16px;padding:14px 8px;border-radius:0;border-bottom:1px solid var(--anf-linea)}
  .anf-dd-panel{position:static;width:auto;max-width:none;box-shadow:none;border:0;border-radius:0;padding:4px 0 8px}
  .anf-dd-cab{display:none}
  .anf-nav-vacia{display:none}
}
@media(max-width:600px){
  .anf-barra-in{gap:10px}
  .anf-modo span{display:none}.anf-modo{padding:0 12px}
  .anf-nav-btn span{display:none}.anf-nav-btn{padding:0 11px}
}
"""

JS = r"""
(function(){
  var nav = document.getElementById('anfNav'); if(!nav) return;
  var dds = Array.prototype.slice.call(nav.querySelectorAll('details.anf-dd'));
  var btn = document.getElementById('anfNavBtn');
  function escritorio(){ return window.innerWidth > 1100; }
  function cerrarMovil(){ nav.classList.remove('abierta'); if(btn) btn.setAttribute('aria-expanded', 'false'); }
  dds.forEach(function(d){
    d.addEventListener('toggle', function(){
      if(!d.open || !escritorio()) return;
      dds.forEach(function(o){ if(o !== d) o.open = false; });
      var p = d.querySelector('.anf-dd-panel'); if(!p) return;
      p.classList.remove('der'); var r = p.getBoundingClientRect();
      if(r.right > window.innerWidth - 12) p.classList.add('der');
    });
  });
  document.addEventListener('click', function(ev){
    if(escritorio()){ dds.forEach(function(d){ if(d.open && !d.contains(ev.target)) d.open = false; }); }
    else if(nav.classList.contains('abierta') && !nav.contains(ev.target) && !(btn && btn.contains(ev.target))) cerrarMovil();
  });
  document.addEventListener('keydown', function(ev){
    if(ev.key !== 'Escape') return;
    dds.forEach(function(d){ if(d.open && escritorio()){ d.open = false; var s = d.querySelector('summary'); if(s) s.focus(); } });
    if(nav.classList.contains('abierta')){ cerrarMovil(); if(btn) btn.focus(); }
  });
  if(btn) btn.addEventListener('click', function(ev){
    ev.stopPropagation(); var on = !nav.classList.contains('abierta');
    nav.classList.toggle('abierta', on); btn.setAttribute('aria-expanded', on ? 'true' : 'false');
    if(on){ dds.forEach(function(d){ d.open = d.classList.contains('sel'); }); }
  });
  window.addEventListener('resize', function(){ if(escritorio()) cerrarMovil(); });
})();
"""
