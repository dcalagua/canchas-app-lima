"""PORTADA DE TENIS `/tenis` (pedido del director, 20-oct-2026: la gente del
tenis siente que la marca "suena a fútbol" y quiere hacer sus torneos y
alquilar canchas aquí). Es la puerta de entrada de raqueta: canchas de tenis
y pádel aprobadas, torneos vivos (cada uno con la marca de SU organizador),
busco partner, liga, boleadores y, para clubes, organizar un torneo o poner su
club. No hay datos nuevos: todo sale de las mismas tablas que el explorador."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from marketing import campeonato_web
from web import campeonatos_logica as L
from web import datos, horarios, sesion, ui
from web import router as _r
from web.ui import e
from config import MARCA  # noqa: E402 — nombre y dominio de marca (un solo lugar)

router = APIRouter(include_in_schema=False)

DEPORTES = ("tenis", "padel", "pickleball")
_MAX_LOCALES = 8


def _locales() -> list[list[dict]]:
    canchas = [c for c in datos.canchas_publicas()
               if datos.reservable(c) and any(d in DEPORTES for d in _r._deportes_de(c))]
    return _r._agrupar_locales(canchas)[:_MAX_LOCALES]


def _tarjeta_local(cs: list[dict]) -> str:
    c = cs[0]
    sim, _iso = _r._moneda_de(c)
    deps = []
    for x in cs:
        for d in _r._deportes_de(x):
            if d in DEPORTES and d not in deps:
                deps.append(d)
    precios = [float(x.get("precio_hora") or 0) for x in cs if float(x.get("precio_hora") or 0) > 0]
    precio = ""
    if precios:
        barato = min(cs, key=lambda x: float(x.get("precio_hora") or 0) or 1e9)
        pvis, unidad = horarios.precio_publico(barato)
        precio = f"<span class='tn-precio'>desde {e(sim)} {float(pvis):.2f} <small>{e(unidad)}</small></span>"
    fotos = _r._fotos(c)
    foto = (f"<img src='{e(fotos[0])}' alt='' loading='lazy'>" if fotos
            else f"<div class='tn-sinfoto'>{_r._deporte(deps[0] if deps else 'tenis')[1]}</div>")
    deps_txt = " · ".join(_r._deporte(d)[0] for d in deps)
    n = len(cs)
    return (f"<a class='tn-local' href='/reservar/{e(c['id'])}'>{foto}<div class='tn-cuerpo'>"
            f"<b>{e(_r._titulo_local(c))}</b><span>{e(_r._zona(c) or c.get('direccion') or '')}</span>"
            f"<span>{n} cancha{'s' if n != 1 else ''} · {e(deps_txt)}</span>{precio}</div></a>")


def _tarjeta_torneo(c: dict) -> str:
    org = campeonato_web.organizador_de(c)
    pill = e(L.estado(c)[1])
    logo = (f"<img src='{e(org['logo'])}' alt=''>" if org["logo"]
            else f"<span class='tn-em'>{_r._deporte(c.get('deporte') or 'tenis')[1]}</span>")
    meta = " · ".join(x for x in [_r._deporte(c.get("deporte") or "tenis")[0], str(c.get("categoria") or ""),
                                  str(c.get("fechas") or "")] if x)
    return (f"<a class='tn-torneo' href='/c/{e(c['id'])}'>{logo}<div class='tn-cuerpo'>"
            f"<b>{e(c.get('nombre') or 'Torneo')}</b>"
            + (f"<span>Organiza {e(org['nombre'])}</span>" if org["nombre"] else "")
            + f"<span>{e(meta)}</span>"
            + (f"<span class='tn-pill'>{pill}</span>" if pill else "")
            + "</div></a>")


_CSS = """
.tn-hero{background:linear-gradient(135deg,#0B8A3E,#0A1B3D);color:#fff;border-radius:24px;padding:34px 28px;margin:18px 0 8px}
.tn-hero h1{font-size:clamp(26px,5vw,40px);line-height:1.1;font-weight:800;margin:0}
.tn-hero p{margin:10px 0 0;opacity:.92;font-size:16px;max-width:560px}
.tn-acc{display:flex;flex-wrap:wrap;gap:10px;margin-top:18px}
.tn-acc a{background:#fff;color:#0A1B3D;border-radius:999px;padding:10px 16px;font-weight:800;text-decoration:none;font-size:14px}
.tn-acc a.sec{background:rgba(255,255,255,.14);color:#fff}
.tn-sec{margin:28px 0 10px;display:flex;align-items:baseline;justify-content:space-between;gap:12px}
.tn-sec h2{font-size:20px;margin:0}
.tn-sec a{font-weight:700;color:var(--azul,#0A1B3D);font-size:14px}
.tn-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(250px,100%),1fr));gap:14px}
.tn-local,.tn-torneo,.tn-caja{display:flex;flex-direction:column;background:#fff;border-radius:18px;box-shadow:0 1px 8px rgba(0,0,0,.08);overflow:hidden;color:inherit;text-decoration:none;min-width:0}
.tn-local img,.tn-sinfoto{width:100%;aspect-ratio:4/3;object-fit:cover;display:flex;align-items:center;justify-content:center;font-size:44px;background:#EEF4EF}
.tn-cuerpo{padding:12px 14px 14px;display:flex;flex-direction:column;gap:3px;min-width:0}
.tn-cuerpo b{font-size:15.5px;overflow-wrap:anywhere}
.tn-cuerpo span{color:#5c6470;font-size:13.5px;overflow-wrap:anywhere}
.tn-precio{color:#222!important;font-weight:700;margin-top:4px}
.tn-torneo{flex-direction:row;align-items:center;gap:12px;padding:12px}
.tn-torneo img{width:60px;height:60px;object-fit:contain;border-radius:14px;background:#fff;flex:none;box-shadow:0 0 0 1px #E4E4E4}
.tn-torneo .tn-cuerpo{padding:0}
.tn-em{width:60px;height:60px;border-radius:14px;background:#EEF4EF;display:flex;align-items:center;justify-content:center;font-size:30px;flex:none}
.tn-pill{display:inline-block;align-self:flex-start;background:#EBEBEB;color:#222!important;border-radius:999px;padding:2px 10px;font-size:12px!important;font-weight:700;margin-top:4px}
.tn-caja{padding:18px;gap:6px}
.tn-caja .em{font-size:30px}
.tn-caja b{font-size:16px}
.tn-caja span{color:#5c6470;font-size:14px}
.tn-vacio{background:#fff;border-radius:18px;padding:18px;color:#5c6470;box-shadow:0 1px 8px rgba(0,0,0,.06)}
"""


@router.get("/tenis", response_class=HTMLResponse)
def pagina_tenis(request: Request) -> HTMLResponse:
    ses = sesion.de_request(request)
    locales = _locales()
    torneos = datos.campeonatos_publicos(DEPORTES, 12)
    canchas_html = ("<div class='tn-grid'>" + "".join(_tarjeta_local(g) for g in locales) + "</div>" if locales
                    else "<div class='tn-vacio'>Aún no hay canchas de tenis o pádel aprobadas cerca. "
                         "¿Tienes un club? <a href='/anfitrion/nueva'>Ponlo aquí</a>.</div>")
    torneos_html = ("<div class='tn-grid'>" + "".join(_tarjeta_torneo(c) for c in torneos) + "</div>" if torneos
                    else "<div class='tn-vacio'>No hay torneos abiertos ahora. Organiza el tuyo: inscripciones, "
                         "llave o grupos, resultados y afiche, con la marca de tu club.</div>")
    cajas = [
        ("🎾", "Busco partner", "Encuentra con quién jugar singles, dobles o pelotear cerca de ti.", "/partidos?tab=partner"),
        ("🥇", "Liga de tenis", "Ranking por nivel, retos y temporadas.", "/liga"),
        ("🥎", "Boleadores", "Contrata un boleador al reservar, o regístrate para bolear y cobrar.", "/anfitrion/boleador"),
        ("🏆", "Organiza tu torneo", "Con tu logo y tu nombre primero: inscripción con pago, fixture y página pública.", "/anfitrion/campeonatos"),
    ]
    cajas_html = "<div class='tn-grid'>" + "".join(
        f"<a class='tn-caja' href='{u}'><span class='em'>{em}</span><b>{e(t)}</b><span>{e(d)}</span></a>"
        for em, t, d, u in cajas) + "</div>"
    cuerpo = (f"<style>{_CSS}</style>"
              "<section class='tn-hero'><h1>🎾 Tenis y pádel, en un solo lugar</h1>"
              "<p>Reserva tu cancha, encuentra partner, juega torneos y sube en la liga. "
              "Los clubes organizan sus torneos con su propia marca.</p>"
              "<div class='tn-acc'><a href='/?deporte=tenis'>Reservar tenis</a><a href='/?deporte=padel'>Reservar pádel</a>"
              "<a class='sec' href='/anfitrion/campeonatos'>Organizar un torneo</a></div></section>"
              "<div class='tn-sec'><h2>Canchas de tenis y pádel</h2><a href='/?deporte=tenis'>Ver todas ›</a></div>"
              f"{canchas_html}"
              "<div class='tn-sec'><h2>Torneos</h2><a href='/anfitrion/campeonatos'>Organizar ›</a></div>"
              f"{torneos_html}"
              "<div class='tn-sec'><h2>Juega más</h2></div>"
              f"{cajas_html}"
              "<div class='tn-sec'><h2>¿Tienes un club?</h2></div>"
              "<div class='tn-vacio'>Pon tus canchas para recibir reservas pagadas en línea, arma tus torneos y "
              "gestiona tu academia. <a href='/anfitrion/nueva'>Pon tu club</a> · <a href='/anfitrion'>Modo anfitrión</a></div>")
    return ui.shell("Tenis y pádel", cuerpo, sesion=ses, ancho=True,
                    titulo_tab=f"Tenis y pádel · {MARCA}",
                    desc="Reserva canchas de tenis y pádel, encuentra partner, juega torneos y la liga.",
                    canonical="/tenis")
