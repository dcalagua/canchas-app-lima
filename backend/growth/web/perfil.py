"""PERFIL en la web (= pantalla Perfil del app): `GET /perfil`.

Movido tal cual desde `web/router.py`, que lo re-exporta.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from web import datos, sesion, ui
from web.ui import e
from config import MARCA  # noqa: E402 — nombre y dominio de marca (un solo lugar)
from web.comun import PLAY_URL

router = APIRouter()


_EMOJI_DEP = {"tenis": "🎾", "padel": "🏸", "futbol": "⚽", "pickleball": "🏓", "voley": "🏐",
              "basquet": "🏀", "natacion": "🏊", "frontón": "🎾", "fronton": "🎾"}

_CSS_PERFIL = """
.perf{display:grid;grid-template-columns:minmax(0,420px) minmax(0,1fr);gap:48px;align-items:start;max-width:1080px;margin:18px auto 110px}
.perf h1{font-size:30px;margin:0 0 18px;letter-spacing:-.3px}
.perf-id{background:#fff;border-radius:24px;box-shadow:0 6px 20px rgba(0,0,0,.08);display:grid;grid-template-columns:minmax(0,1fr) minmax(0,150px);align-items:center;padding:26px 22px}
.perf-yo{text-align:center;min-width:0}
.perf-av{position:relative;width:104px;height:104px;margin:0 auto 10px}
.perf-av img,.perf-av .ini{width:104px;height:104px;border-radius:50%;object-fit:cover;display:flex;align-items:center;justify-content:center;background:var(--noche,#0A1B3D);color:#fff;font-size:42px;font-weight:700}
.perf-av .pro{position:absolute;right:-4px;bottom:4px;background:#F2C94C;color:#3a2a00;border:3px solid #fff;border-radius:99px;font-size:12px;font-weight:800;padding:3px 8px}
.perf-av .ok{position:absolute;left:-2px;bottom:6px;background:#0B7A57;color:#fff;border:3px solid #fff;border-radius:50%;width:28px;height:28px;display:flex;align-items:center;justify-content:center;font-size:13px}
.perf-yo b{display:block;font-size:22px;line-height:1.2;overflow-wrap:anywhere}
.perf-yo small{display:block;color:#6a6a6a;font-size:13px;margin-top:4px;overflow-wrap:anywhere}
.perf-stats{border-left:1px solid #EBEBEB;padding-left:18px;display:grid;gap:10px}
.perf-stats div{border-bottom:1px solid #EBEBEB;padding-bottom:8px}
.perf-stats div:last-child{border:0;padding:0}
.perf-stats b{display:block;font-size:20px}
.perf-stats small{font-size:12px;color:#444;font-weight:600}
.perf-tiles{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px;margin:16px 0}
.perf-tile{position:relative;background:#fff;border-radius:20px;box-shadow:0 6px 20px rgba(0,0,0,.08);padding:26px 14px 18px;text-align:center;color:inherit;text-decoration:none;cursor:pointer;border:0;font:inherit}
.perf-tile .em{font-size:52px;line-height:1;display:block;margin-bottom:12px}
.perf-tile b{font-size:15px}
.perf-tile .nov{position:absolute;top:12px;right:12px;background:#0A1B3D;color:#fff;font-size:12px;font-weight:800;letter-spacing:.6px;border-radius:99px;padding:4px 8px}
.perf-ban{display:flex;gap:14px;align-items:center;background:#fff;border-radius:20px;box-shadow:0 6px 20px rgba(0,0,0,.08);padding:18px;color:inherit;text-decoration:none;margin-bottom:16px}
.perf-ban .em{font-size:44px;flex:none}
.perf-ban b{display:block;font-size:16px}
.perf-ban small{color:#6a6a6a;font-size:13.5px;line-height:1.4}
.perf-nivel{background:#fff;border-radius:20px;box-shadow:0 6px 20px rgba(0,0,0,.08);padding:18px}
.perf-nivel h3{margin:0 0 4px;font-size:16px}
.perf-nivel p{margin:0 0 10px;color:#6a6a6a;font-size:13.5px}
.perf-niv{display:flex;flex-wrap:wrap;gap:8px}
.perf-niv span{background:#F4F7FA;border-radius:99px;padding:7px 12px;font-size:13.5px;font-weight:600}
.perf-menu{display:flex;flex-direction:column}
.perf-it{display:flex;align-items:center;gap:14px;padding:16px 2px;border:0;border-bottom:1px solid #EBEBEB;background:none;color:inherit;text-decoration:none;font:inherit;font-size:16px;text-align:left;cursor:pointer;width:100%}
.perf-it .em{font-size:24px;width:30px;text-align:center;flex:none}
.perf-it .tx{flex:1;min-width:0}
.perf-it .tx small{display:block;color:#6a6a6a;font-size:13px;margin-top:2px}
.perf-it .app{font-size:12px;font-weight:700;color:#08654A;background:#E9F6EE;border-radius:99px;padding:3px 9px;white-space:nowrap}
.perf-it .bdg{background:#E0245E;color:#fff;font-size:12px;font-weight:800;border-radius:99px;min-width:22px;height:22px;padding:0 6px;display:inline-flex;align-items:center;justify-content:center}
.perf-it .chev{color:#b0b0b0;font-size:22px;line-height:1}
.perf-it.rojo{color:#C0392B}
.perf-sep{height:14px}
.perf-sub{padding-left:44px}
.perf-sub .perf-it{font-size:15px;padding:13px 2px}
details.perf-grp>summary{list-style:none}
details.perf-grp>summary::-webkit-details-marker{display:none}
details.perf-grp[open] .chev{transform:rotate(90deg)}
.perf-host{position:fixed;left:50%;transform:translateX(-50%);bottom:calc(22px + env(safe-area-inset-bottom));background:#222;color:#fff;border-radius:99px;padding:13px 20px;font-weight:700;text-decoration:none;box-shadow:0 8px 24px rgba(0,0,0,.25);display:flex;gap:8px;align-items:center;z-index:30;white-space:nowrap}
@media(max-width:900px){.perf{grid-template-columns:minmax(0,1fr);gap:22px;margin-top:6px}}
@media(max-width:420px){.perf-id{grid-template-columns:minmax(0,1fr) minmax(0,118px);padding:22px 14px}.perf-stats{padding-left:12px}.perf-av,.perf-av img,.perf-av .ini{width:88px;height:88px}.perf-yo b{font-size:19px}.perf-tile .em{font-size:44px}}
"""


def _item_perfil(em: str, titulo: str, *, href: str = "", sub: str = "", app: str = "",
                 badge: int = 0, clase: str = "", onclick: str = "") -> str:
    """Fila del menú del Perfil (= `_ItemAirbnb` del app). [app] = qué se hace
    en la app: la fila abre un modal "Esto está en la app" en vez de navegar."""
    der = ""
    if badge:
        der += f"<span class='bdg'>{badge}</span>"
    if app:
        der += "<span class='app'>En la app</span>"
    der += "<span class='chev'>›</span>"
    cuerpo = (f"<span class='em' aria-hidden='true'>{em}</span><span class='tx'>{e(titulo)}"
              + (f"<small>{e(sub)}</small>" if sub else "") + f"</span>{der}")
    cls = f"perf-it {clase}".strip()
    if app:
        return (f"<button type='button' class='{cls}' data-app='{e(app)}' data-titulo='{e(titulo)}' "
                f"data-em='{e(em)}'>{cuerpo}</button>")
    if onclick:
        return f"<button type='button' class='{cls}' onclick=\"{onclick}\">{cuerpo}</button>"
    return f"<a class='{cls}' href='{e(href)}'>{cuerpo}</a>"


@router.get("/perfil", response_class=HTMLResponse)
def pagina_perfil(request: Request) -> HTMLResponse:
    """Perfil en la web = pantalla Perfil del app (pedido del director,
    29-sep-2026: "esto no lo veo en la web"): tarjeta de identidad con foto,
    PRO y verificado + Reservas / Deportes con nivel / Retos pendientes,
    atajos Mis reservas y Marketplace, "¿Tienes una cancha o academia?",
    nivel de jugador y el MISMO menú. Lo que la web aún no tiene abre un modal
    "Esto lo encuentras en la app" (nunca un enlace roto)."""
    ses = sesion.de_request(request)
    if not ses:
        if sesion.activo():
            return HTMLResponse("", status_code=302, headers={"Location": "/entrar?volver=%2Fperfil"})
        cuerpo = ("<div class='panel' style='max-width:520px;margin:40px auto;text-align:center'>"
                  "<h1 style='font-size:22px'>Perfil</h1>"
                  "<p class='sub'>En esta web aún no está activo el inicio de sesión. Tu perfil está en la app.</p>"
                  f"<div class='acciones' style='justify-content:center'><a class='btn' href='{PLAY_URL}'>Abrir {MARCA} en Google Play</a></div></div>")
        return ui.shell("Perfil", cuerpo, sesion=None)
    from db.store import stores as _st
    from retos.router import _auto_confirmar, _lado_retado, _lado_retador, _participantes
    email = (ses.get("email") or "").strip().lower()
    nombre = ses.get("nombre") or email
    datos.precargar_perfil(email)  # reservas, niveles, verificación, matrículas y boleador: un solo viaje
    reservas = len(datos.reservas_de_usuario(email))
    niveles = datos.niveles_de(email)
    try:
        _auto_confirmar()
    except Exception:  # noqa: BLE001
        pass
    retos = 0
    for r in _st.retos:
        if email not in _participantes(r):
            continue
        if email in _lado_retado(r) and r.estado in ("pendiente", "aceptado"):
            retos += 1
        elif email in _lado_retador(r) and r.estado == "aceptado":
            retos += 1
    pro = _st.pro_activo(email)
    verificado = datos.esta_verificado(email)
    puntos = datos.puntos_de(email)["disponibles"]
    matriculas = datos.tiene_matriculas(email)
    try:
        es_boleador = bool(datos.boleador(email))
    except Exception:  # noqa: BLE001
        es_boleador = False

    ini = e((nombre or "?")[:1].upper())
    foto = (f"<img src='{e(ses.get('foto'))}' alt='' referrerpolicy='no-referrer'>" if ses.get("foto")
            else f"<span class='ini'>{ini}</span>")
    def _stat(n: int, uno: str, varios: str) -> str:
        return f"<div><b>{n}</b><small>{uno if n == 1 else varios}</small></div>"
    ident = (
        "<div class='perf-id'><div class='perf-yo'><div class='perf-av'>" + foto
        + ("<span class='pro'>👑 PRO</span>" if pro else "")
        + ("<span class='ok' title='Identidad verificada'>✓</span>" if verificado else "")
        + f"</div><b>{e(nombre)}</b><small>{e(email)}</small></div>"
        "<div class='perf-stats'>"
        + _stat(reservas, "Reserva", "Reservas")
        + _stat(len(niveles), "Deporte con nivel", "Deportes con nivel")
        + _stat(retos, "Reto pendiente", "Retos pendientes")
        + "</div></div>")
    tiles = ("<div class='perf-tiles'>"
             "<a class='perf-tile' href='/mis-reservas'><span class='em'>📅</span><b>Mis reservas</b></a>"
             "<a class='perf-tile' href='/marketplace'><span class='nov'>NOVEDAD</span><span class='em'>🛍️</span><b>Marketplace</b></a>"
             "<a class='perf-tile' href='/mensajes'><span class='nov' data-badge-mensajes hidden style='background:#E0245E'></span><span class='em'>💬</span><b>Mensajes</b></a>"
             "<a class='perf-tile' href='/mis-pedidos-bodega'><span class='em'>🧃</span><b>Pedidos a la cancha</b></a>"
             "<a class='perf-tile' href='/novedades'><span class='em'>📰</span><b>Novedades</b></a>"
             "<a class='perf-tile' href='/canales'><span class='em'>📢</span><b>Canales</b></a>"
             "</div>")
    banner = ("<a class='perf-ban' href='/anfitrion'><span class='em'>🏟️</span><span>"
              "<b>¿Tienes una cancha o academia?</b><small>Publícala y genera ingresos adicionales, ¡es muy sencillo!</small></span></a>")
    if niveles:
        chips = "".join(f"<span>{_EMOJI_DEP.get(n['deporte'].lower(), '🏅')} {e(n['deporte'].capitalize())} · {n['nivel']:.1f}</span>" for n in niveles)
        nivel = ("<div class='perf-nivel'><h3>📈 Tu nivel de jugador</h3>"
                 "<p>Sube o baja solo con tus resultados en retos y campeonatos.</p>"
                 f"<div class='perf-niv'>{chips}</div><a class='btn sec' style='margin-top:12px' href='/mi-nivel'>Reevaluar / agregar deporte</a></div>")
    else:
        nivel = ("<div class='perf-nivel'><h3>📈 Tu nivel de jugador</h3>"
                 "<p>Autoevalúate en 30 segundos y encuentra rivales de tu nivel.</p>"
                 "<a class='btn sec' href='/mi-nivel'>Autoevaluarme</a></div>")

    menu = ""
    if matriculas:
        menu += _item_perfil("🎓", "Mis clases y pagos", href="/mis-clases", sub="Cuotas, pagos y comprobantes de tu academia")
    menu += _item_perfil("🎟️", "Mis bonos", href="/mis-bonos", sub="Horas prepagadas en tus locales")
    menu += _item_perfil("🧾", "Mis pagos", href="/mis-pagos", sub="Todo lo que pagaste, con comprobantes")
    menu += _item_perfil("⭐", f"Mis puntos · {puntos} ⭐" if puntos > 0 else "Mis puntos",
                         href="/mis-puntos", sub="Ganas puntos con cada reserva pagada")
    menu += _item_perfil("⚽", "Juega ya", href="/partidos", sub="Partidos cerca, organiza el tuyo o busca partner")
    menu += _item_perfil("📅", "Pichangas de mi club", href="/pichangas", sub="Convocatorias con cupos y lista de espera")
    menu += _item_perfil("🏆", "Campeonatos", href="/anfitrion/campeonatos", sub="Únete con un código o mira dónde participas")
    menu += _item_perfil("🎁", "Invita y gana", href="/referidos", sub="Comparte tu código con tus amigos")
    tenis = (
        _item_perfil("🥇", f"Liga de tenis {MARCA}", href="/liga", sub="Ranking, retos y resultados")
        + _item_perfil("🥎", "Soy boleador" if es_boleador else "Ser boleador", href="/anfitrion/boleador",
                       sub="Bolea en las canchas de tu zona y cobra por turno"))
    menu += ("<details class='perf-grp'><summary class='perf-it'><span class='em'>🎾</span>"
             "<span class='tx'>Mundo tenis<small>Entrena, bolea y compite</small></span>"
             + (f"<span class='bdg'>{retos}</span>" if retos else "") + "<span class='chev'>›</span></summary>"
             f"<div class='perf-sub'>{tenis}</div></details>")
    menu += _item_perfil("👑", f"{MARCA} Pro", href="/pro", sub="Retos sin límite, campeonatos, bodega y más")
    menu += _item_perfil("💳", "Métodos de pago", href="/cuenta/tarjetas", sub="Tus tarjetas guardadas")
    menu += _item_perfil("👛", "Mi billetera", href="/mi-billetera", sub="Saldo, recargas, cupones y movimientos")
    menu += "<div class='perf-sep'></div>"
    menu += _item_perfil("🌎", "Mi país", href="/mi-pais", sub="Define la moneda de tu saldo")
    menu += _item_perfil("⚙️", "Configuración de la cuenta", href="/cuenta/configuracion", sub="Foto, nombre, celular e identidad")
    menu += _item_perfil("🚪", "Cierra la sesión", onclick="window.pcgSalir&&pcgSalir()")
    menu += _item_perfil("🗑️", "Eliminar mi cuenta", href="/legal/eliminar-cuenta", clase="rojo")

    cuerpo = (
        f"<style>{_CSS_PERFIL}</style>"
        "<div class='perf'><div><h1>Perfil</h1>" + ident + tiles + banner + nivel + "</div>"
        f"<div><div class='perf-menu'>{menu}</div></div></div>"
        "<a class='perf-host' href='/anfitrion'>🔁 Cambiar a modo anfitrión</a>"
        "<script>(function(){\n"
        "document.querySelectorAll('[data-app]').forEach(function(b){ b.addEventListener('click', function(ev){ ev.preventDefault();\n"
        "  pcgConfirmar({titulo: b.dataset.titulo, mensaje: b.dataset.app, icono: b.dataset.em || '📱', confirmar: 'Abrir la app', cancelar: 'Ahora no'})\n"
        f"   .then(function(ok){{ if(ok) window.open({ui.json_js(PLAY_URL)}, '_blank', 'noopener'); }});\n"
        "}); });\n"
        "})();</script>")
    return ui.shell("Perfil", cuerpo, sesion=ses, titulo_tab=f"Perfil · {MARCA}")
