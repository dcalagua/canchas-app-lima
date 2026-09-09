"""Sistema de diseño de la WEB de Pichangol — el MISMO look & feel del APK
(`lib/theme.dart`, `lib/widgets/marca.dart`, estándar Airbnb del CLAUDE.md):

- Tipografía **Montserrat** (la del app), pesos 600/700/800.
- Paleta del logo nuevo: blanco, azul noche `#0F1B2D` (texto/oscuros),
  esmeralda `#0E8F67` (CTA/acento), dorado `#D9B45A`, papel `#F4F7FA`,
  trazo `#DDE5EF`, texto tenue `#627080`, tinte esmeralda `#E7F4EF`.
- Wordmark **Pichang[o]l** con la 'o' = pelota (SVG esmeralda), pin oficial
  (`/static/brand/logo_pin.png`), sello "✓ Verificada", chips blancas con
  borde suave (seleccionada = tinte), tarjetas radio 16-20 con sombra sutil,
  botones esmeralda radio 12, marcas de pago dibujadas (Yape/Visa/Mastercard).

Todo lo público del dominio (home, catálogo, reserva, comprobante, 404) pasa
por `shell()` para que se vea como UNA sola marca.
"""

from __future__ import annotations

import html as _html

from fastapi.responses import HTMLResponse

TOKENS = """
:root{
  --blanco:#FFFFFF;--noche:#0F1B2D;--esmeralda:#0E8F67;--teal:#0B7A58;--dorado:#D9B45A;
  --papel:#F4F7FA;--trazo:#DDE5EF;--tenue:#627080;--tinte:#E7F4EF;--gris:#E9EEF4;
  --ok-bg:#E9F4EE;--ok-fg:#1F6E49;--warn-bg:#FDF2D6;--warn-fg:#946200;--bad-bg:#FBE7E7;--bad-fg:#C0392B;
  --rojo:#C13515;--sombra:0 2px 14px rgba(15,27,45,.06);--sombra2:0 10px 30px rgba(15,27,45,.10);
  --r:16px;--r-lg:20px;--r-btn:12px;
}
"""

CSS = TOKENS + """
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--papel);color:var(--noche);font-family:"Montserrat",system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;font-weight:500;line-height:1.45}
a{color:var(--esmeralda)}img{max-width:100%}
.wrap{max-width:1080px;margin:0 auto;padding:0 20px}
h1,h2,h3{font-weight:800;letter-spacing:-.3px;color:var(--noche);margin:0}
h1{font-size:28px;line-height:1.15}h2{font-size:20px}h3{font-size:16px}
.sub{color:var(--tenue);font-size:15px;margin:6px 0 0}
/* barra */
.nav{background:var(--blanco);border-bottom:1px solid var(--trazo);position:sticky;top:0;z-index:20}
.nav-in{height:64px;display:flex;align-items:center;justify-content:space-between;gap:12px}
.wm{display:inline-flex;align-items:center;font-weight:800;font-size:22px;letter-spacing:-.5px;color:var(--noche);text-decoration:none;line-height:1}
.wm svg{width:.92em;height:.92em;margin:0 .03em;vertical-align:middle}
.links{display:flex;gap:6px;align-items:center}
.links a{color:var(--noche);text-decoration:none;font-weight:700;font-size:14px;padding:9px 12px;border-radius:999px}
.links a:hover{background:var(--gris)}.links a.cta{background:var(--esmeralda);color:#fff;padding:10px 16px}
@media(max-width:640px){.links a:not(.cta){display:none}}
/* botones */
.btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;background:var(--esmeralda);color:#fff;font-weight:700;font-size:15px;padding:13px 20px;border-radius:var(--r-btn);border:0;cursor:pointer;text-decoration:none;font-family:inherit;transition:filter .15s}
.btn:hover{filter:brightness(1.05)}.btn:disabled{opacity:.5;cursor:default;filter:none}
.btn.sec{background:var(--blanco);color:var(--noche);border:1px solid var(--trazo)}
.btn.sec:hover{background:var(--gris)}.btn.lg{padding:15px 24px;font-size:16px;width:100%}
.btn.dark{background:var(--noche)}
/* chips */
.chip{display:inline-flex;align-items:center;gap:6px;background:var(--blanco);border:1px solid var(--trazo);border-radius:999px;padding:9px 14px;font-weight:700;font-size:14px;color:var(--noche);cursor:pointer;user-select:none;text-decoration:none;box-shadow:0 1px 3px rgba(15,27,45,.04);white-space:nowrap}
.chip:hover{border-color:#C9D3E0}.chip.sel{background:var(--tinte);border-color:var(--esmeralda);color:var(--teal)}
.chip.off{opacity:.38;cursor:not-allowed;text-decoration:line-through}.chip small{font-weight:600;color:var(--tenue)}
.chip.sel small{color:var(--teal)}.chips{display:flex;flex-wrap:wrap;gap:10px}
.strip{display:flex;gap:10px;overflow-x:auto;padding:4px 2px 8px;scrollbar-width:none}.strip::-webkit-scrollbar{display:none}
.strip .chip{flex-direction:column;gap:2px;padding:10px 14px;min-width:74px;align-items:center}
.strip .chip b{font-size:15px}.strip .chip small{font-size:11.5px}
/* tarjetas */
.card{background:var(--blanco);border-radius:var(--r-lg);box-shadow:var(--sombra);overflow:hidden;display:flex;flex-direction:column}
.card:hover{box-shadow:var(--sombra2)}
.card img,.card .sinfoto{width:100%;aspect-ratio:4/3;object-fit:cover;display:block;background:var(--gris)}
.sinfoto{display:flex;align-items:center;justify-content:center;font-size:54px;background:linear-gradient(135deg,#E7F4EF,#CFE9DD)}
.cb{padding:14px 16px 16px;display:flex;flex-direction:column;gap:5px;flex:1}
.cb .m{font-size:13px;color:var(--tenue);font-weight:600}
.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}
@media(max-width:900px){.grid{grid-template-columns:repeat(2,1fr)}}@media(max-width:560px){.grid{grid-template-columns:1fr}}
.panel{background:var(--blanco);border-radius:var(--r-lg);box-shadow:var(--sombra);padding:20px 22px}
.pill{display:inline-flex;align-items:center;gap:5px;background:var(--tinte);color:var(--teal);font-weight:800;font-size:12px;padding:5px 10px;border-radius:999px;line-height:1}
.pill.dorado{background:#FBF3DC;color:#8A6400}.pill.gris{background:var(--gris);color:var(--tenue)}
.precio{font-weight:800;font-size:18px}.precio small{font-weight:600;color:var(--tenue);font-size:12.5px}
/* formulario */
label{display:block;font-size:13px;font-weight:700;color:var(--noche);margin:14px 0 6px}
input,select,textarea{width:100%;padding:13px 14px;border:1px solid var(--trazo);border-radius:var(--r-btn);font-size:15px;font-family:inherit;font-weight:500;background:var(--blanco);color:var(--noche)}
input:focus,select:focus{outline:2px solid var(--esmeralda);outline-offset:0;border-color:transparent}
.row{display:grid;grid-template-columns:1fr 1fr;gap:12px}@media(max-width:560px){.row{grid-template-columns:1fr}}
.paso{display:flex;align-items:center;gap:10px;font-weight:800;font-size:16px;margin:22px 0 10px}
.paso span{background:var(--noche);color:#fff;border-radius:50%;width:26px;height:26px;display:inline-flex;align-items:center;justify-content:center;font-size:13px}
.estado{border-radius:var(--r-btn);padding:12px 14px;font-size:14px;font-weight:600;margin-top:12px}
.estado.ok{background:var(--ok-bg);color:var(--ok-fg)}.estado.warn{background:var(--warn-bg);color:var(--warn-fg)}
.estado.bad{background:var(--bad-bg);color:var(--bad-fg);display:none}
/* layout reserva */
.dos{display:grid;grid-template-columns:1fr 360px;gap:22px;align-items:start}
@media(max-width:900px){.dos{grid-template-columns:1fr}}
.resumen{position:sticky;top:80px}
@media(max-width:900px){.resumen{position:static}}
.linea{display:flex;justify-content:space-between;gap:10px;font-size:14px;padding:7px 0;border-bottom:1px solid var(--trazo)}
.linea:last-child{border-bottom:0}.linea b{font-weight:700}
.total{display:flex;justify-content:space-between;align-items:center;font-weight:800;font-size:20px;padding-top:12px}
.barra-fija{display:none}
@media(max-width:900px){
  .barra-fija{display:flex;position:fixed;left:0;right:0;bottom:0;background:var(--blanco);border-top:1px solid var(--trazo);padding:12px 16px calc(12px + env(safe-area-inset-bottom));gap:12px;align-items:center;justify-content:space-between;z-index:30;box-shadow:0 -6px 20px rgba(15,27,45,.08)}
  .barra-fija .t{font-weight:800;font-size:18px}.barra-fija .btn{flex:1;max-width:60%}
  body.con-barra{padding-bottom:88px}
}
/* marcas de pago */
.marcas{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.yape{background:#742284;color:#fff;font-weight:800;border-radius:7px;padding:4px 9px;font-size:13px;letter-spacing:-.3px;line-height:1.2}
.visa{color:#1A1F71;font-weight:800;font-style:italic;font-size:17px;letter-spacing:-.5px;line-height:1}
.mc{display:inline-block;width:34px;height:21px;position:relative}.mc i{position:absolute;top:0;width:21px;height:21px;border-radius:50%}
.mc i:first-child{left:0;background:#EB001B}.mc i:last-child{left:13px;background:#F79E1B;opacity:.92}
.candado{display:inline-flex;align-items:center;gap:6px;background:var(--noche);color:#fff;font-size:12px;font-weight:700;padding:6px 10px;border-radius:10px}
/* hero ficha */
.galeria{display:grid;grid-template-columns:2fr 1fr;grid-template-rows:170px 170px;gap:8px;border-radius:var(--r-lg);overflow:hidden}
.galeria img,.galeria .sinfoto{width:100%;height:100%;object-fit:cover;aspect-ratio:auto}
.galeria .principal{grid-row:1/3}
@media(max-width:640px){.galeria{grid-template-columns:1fr;grid-template-rows:220px}.galeria .principal{grid-row:auto}.galeria>*:not(.principal){display:none}}
ul.datos{list-style:none;padding:0;margin:10px 0 0;font-size:14px;color:var(--tenue);font-weight:600}
ul.datos li{margin:6px 0;display:flex;gap:8px;align-items:flex-start}
.amen{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px}.amen span{background:var(--gris);border-radius:999px;padding:5px 10px;font-size:12.5px;font-weight:700;color:var(--tenue)}
/* skeleton / loading */
.skel{background:linear-gradient(90deg,var(--gris) 25%,#F6F8FB 37%,var(--gris) 63%);background-size:400% 100%;animation:sk 1.2s infinite;border-radius:999px;height:38px;width:110px;display:inline-block}
@keyframes sk{0%{background-position:100% 0}100%{background-position:0 0}}
/* comprobante */
.check{width:76px;height:76px;border-radius:50%;background:var(--tinte);display:flex;align-items:center;justify-content:center;margin:0 auto 14px;animation:pop .5s cubic-bezier(.2,.9,.3,1.4)}
.check svg{width:40px;height:40px}
@keyframes pop{0%{transform:scale(.4);opacity:0}100%{transform:scale(1);opacity:1}}
.acciones{display:flex;flex-wrap:wrap;gap:10px;margin-top:16px}
.acciones .btn{flex:1;min-width:160px}
footer{margin:56px 0 28px;color:var(--tenue);font-size:13px;text-align:center;font-weight:600}
footer .wm{font-size:18px;margin-bottom:6px}footer a{color:var(--tenue);margin:0 7px;text-decoration:none}footer a:hover{color:var(--noche)}
.ebim{font-size:12px;margin-top:8px}
"""


def e(s) -> str:
    return _html.escape(str(s if s is not None else ""), quote=True)


PELOTA_SVG = (
    "<svg viewBox='0 0 24 24' aria-hidden='true'><circle cx='12' cy='12' r='10' fill='#0E8F67'/>"
    "<path fill='#fff' d='M12 6.2l3.3 2.4-1.3 3.9H10l-1.3-3.9L12 6.2z'/>"
    "<path fill='none' stroke='#fff' stroke-width='1.4' d='M12 6.2V3.5M15.3 8.6l2.6-.9M14 12.5l1.9 2.3M10 12.5l-1.9 2.3M8.7 8.6l-2.6-.9'/>"
    "<path fill='#fff' opacity='.9' d='M6.2 8.5l2.5-.8.9 2.6-2.3 1.8-1.7-1.3zM17.8 8.5l-2.5-.8-.9 2.6 2.3 1.8 1.7-1.3zM9.1 15.6h5.8l.8 2.6-3.7 1.9-3.7-1.9z'/></svg>"
)


def wordmark(tam: int = 22, href: str = "/") -> str:
    """Pichang[o]l con la pelota como 'o' (espejo de `PichangolWordmark`)."""
    return (f"<a class='wm' href='{href}' style='font-size:{tam}px' aria-label='Pichangol'>"
            f"Pichang{PELOTA_SVG}l</a>")


def marcas_pago() -> str:
    return ("<div class='marcas'><span class='yape'>Yape</span><span class='visa'>VISA</span>"
            "<span class='mc'><i></i><i></i></span>"
            "<span class='candado'>🔒 Pago seguro · Culqi</span></div>")


def sello_verificada() -> str:
    return "<span class='pill'>✓ Verificada</span>"


def check_svg() -> str:
    return ("<div class='check'><svg viewBox='0 0 24 24'><path fill='none' stroke='#0E8F67' stroke-width='3' "
            "stroke-linecap='round' stroke-linejoin='round' d='M5 12.5l4.5 4.5L19 7'/></svg></div>")


def shell(titulo: str, cuerpo: str, *, desc: str = "", extra_head: str = "",
          canonical: str = "", og_image: str = "/static/brand/logo_pichangol.png",
          con_barra: bool = False, jsonld: str = "") -> HTMLResponse:
    page = (
        "<!doctype html><html lang='es'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1,viewport-fit=cover'>"
        f"<title>{e(titulo)} · Pichangol</title>"
        f"<meta name='description' content='{e(desc or titulo)}'>"
        f"<meta property='og:title' content='{e(titulo)} · Pichangol'>"
        f"<meta property='og:description' content='{e(desc or 'Reserva, juega, repite.')}'>"
        f"<meta property='og:image' content='{e(og_image)}'><meta property='og:type' content='website'>"
        + (f"<link rel='canonical' href='{e(canonical)}'><meta property='og:url' content='{e(canonical)}'>" if canonical else "")
        + "<meta name='theme-color' content='#0F1B2D'>"
        "<link rel='icon' type='image/png' href='/static/brand/logo_pin.png'>"
        "<link rel='apple-touch-icon' href='/static/brand/logo_pin.png'>"
        "<link rel='preconnect' href='https://fonts.googleapis.com'><link rel='preconnect' href='https://fonts.gstatic.com' crossorigin>"
        "<link href='https://fonts.googleapis.com/css2?family=Montserrat:wght@500;600;700;800&display=swap' rel='stylesheet'>"
        f"<style>{CSS}</style>{extra_head}"
        + (f"<script type='application/ld+json'>{jsonld}</script>" if jsonld else "")
        + f"</head><body{' class=con-barra' if con_barra else ''}>"
        "<header class='nav'><div class='wrap nav-in'>"
        f"{wordmark()}"
        "<nav class='links'><a href='/canchas'>Canchas</a><a href='/#servicios'>Servicios</a>"
        "<a href='/#contacto'>Contacto</a><a class='cta' href='/canchas'>Reservar</a></nav>"
        "</div></header>"
        f"<main class='wrap'>{cuerpo}</main>"
        f"<footer><div>{wordmark(18)}</div><div>Reserva, juega, repite.</div>"
        "<div style='margin-top:8px'><a href='/#terminos'>Términos</a><a href='/#devoluciones'>Cancelaciones</a>"
        "<a href='/legal/privacidad'>Privacidad</a><a href='/#reclamaciones'>Libro de Reclamaciones</a>"
        "<a href='/#contacto'>Contacto</a></div>"
        "<div class='ebim'>GRUPO EBIM S.A.C. · RUC 20602517986 · Lima, Perú</div></footer>"
        "</body></html>")
    return HTMLResponse(page, headers={"Cache-Control": "no-store"})
