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
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}html,body{overflow-x:hidden;max-width:100%}
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
.links a{color:var(--noche);text-decoration:none;font-weight:700;font-size:14px;padding:9px 12px;border-radius:999px;white-space:nowrap}
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
.strip{display:flex;gap:10px;overflow-x:auto;padding:4px 2px 8px;min-width:0;max-width:100%;scrollbar-width:none;-webkit-overflow-scrolling:touch}.strip::-webkit-scrollbar{display:none}
.strip .chip{flex-direction:column;gap:2px;padding:10px 14px;min-width:74px;align-items:center}
.strip .chip b{font-size:15px}.strip .chip small{font-size:11.5px}
/* tarjetas */
.card{background:var(--blanco);border-radius:var(--r-lg);box-shadow:var(--sombra);overflow:hidden;display:flex;flex-direction:column}
.card:hover{box-shadow:var(--sombra2)}
.card img{width:100%;aspect-ratio:4/3;object-fit:cover;display:block;background:var(--gris)}
.sinfoto{width:100%;aspect-ratio:4/3;display:flex;align-items:center;justify-content:center;font-size:54px;background:linear-gradient(135deg,#E7F4EF,#CFE9DD)}
.cb{padding:14px 16px 16px;display:flex;flex-direction:column;gap:5px;flex:1}
.cb .m{font-size:13px;color:var(--tenue);font-weight:600}
.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}
@media(max-width:900px){.grid{grid-template-columns:repeat(2,1fr)}}@media(max-width:560px){.grid{grid-template-columns:1fr}}
.panel{background:var(--blanco);border-radius:var(--r-lg);box-shadow:var(--sombra);padding:20px 22px;min-width:0}
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
.dos{display:grid;grid-template-columns:minmax(0,1fr) 360px;gap:22px;align-items:start}.dos>*{min-width:0}
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
.galeria.una{grid-template-columns:1fr;grid-template-rows:300px}.galeria.una .principal{grid-row:auto}
@media(max-width:640px){.galeria.una{grid-template-rows:220px}}
.galeria .principal{grid-row:1/3}
@media(max-width:640px){.galeria{grid-template-columns:1fr;grid-template-rows:220px}.galeria .principal{grid-row:auto}.galeria>*:not(.principal){display:none}}
ul.datos{list-style:none;padding:0;margin:10px 0 0;font-size:14px;color:var(--tenue);font-weight:600}
ul.datos li{margin:6px 0;display:flex;gap:8px;align-items:flex-start}
.amen{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px}.amen span{background:var(--gris);border-radius:999px;padding:5px 10px;font-size:12.5px;font-weight:700;color:var(--tenue)}
/* banderas (SVG: en Windows los emoji de bandera salen como texto) */
.flag{display:inline-block;width:18px;height:13px;border-radius:2px;vertical-align:-1px;box-shadow:0 0 0 1px rgba(15,27,45,.12)}
/* explorar: mapa + ubicación */
.mapa{height:360px;border-radius:var(--r-lg);overflow:hidden;box-shadow:var(--sombra);background:var(--gris);position:relative;z-index:0}
@media(max-width:640px){.mapa{height:240px}}
.pin-precio{background:var(--blanco);color:var(--noche);font-weight:800;font-size:12.5px;padding:5px 9px;border-radius:999px;box-shadow:0 2px 8px rgba(15,27,45,.25);border:1px solid var(--trazo);white-space:nowrap;font-family:"Montserrat",system-ui,sans-serif}
.pin-precio.yo{background:var(--esmeralda);color:#fff;border-color:var(--esmeralda)}
.pin-precio.pend{background:var(--gris);color:var(--tenue)}
.card.pend img,.card.pend .sinfoto{filter:saturate(.6)}
.leaflet-popup-content-wrapper{border-radius:14px;font-family:"Montserrat",system-ui,sans-serif}
.leaflet-popup-content{margin:12px 14px;font-size:13.5px}.leaflet-popup-content b{font-size:14px}
.leaflet-popup-content .btn{padding:8px 12px;font-size:13px;margin-top:8px}
.ubic{display:flex;align-items:center;gap:12px;flex-wrap:wrap;background:var(--tinte);border-radius:var(--r);padding:12px 14px;margin-bottom:14px}
.ubic .btn{padding:10px 14px;font-size:14px}.ubic .t{flex:1;min-width:200px;font-size:14px;font-weight:600;color:var(--teal)}
.dist{color:var(--teal);font-weight:800}
.vista{display:none;gap:8px}@media(max-width:640px){.vista{display:flex;margin:10px 0}}
/* skeleton / loading */
.skel{background:linear-gradient(90deg,var(--gris) 25%,#F6F8FB 37%,var(--gris) 63%);background-size:400% 100%;animation:sk 1.2s infinite;border-radius:999px;height:38px;width:110px;display:inline-block}
@keyframes sk{0%{background-position:100% 0}100%{background-position:0 0}}
/* comprobante */
.check{width:76px;height:76px;border-radius:50%;background:var(--tinte);display:flex;align-items:center;justify-content:center;margin:0 auto 14px;animation:pop .5s cubic-bezier(.2,.9,.3,1.4)}
.check svg{width:40px;height:40px}
@keyframes pop{0%{transform:scale(.4);opacity:0}100%{transform:scale(1);opacity:1}}
.acciones{display:flex;flex-wrap:wrap;gap:10px;margin-top:16px}
.acciones .btn{flex:1;min-width:160px}
/* ── footer (columnas, estilo Airbnb) ── */
footer.pie{margin-top:56px;background:var(--blanco);border-top:1px solid var(--trazo);color:var(--tenue);font-size:13.5px;font-weight:600}
.pie-cols{display:grid;grid-template-columns:repeat(4,1fr);gap:24px;padding:36px 0 24px}
@media(max-width:900px){.pie-cols{grid-template-columns:1fr 1fr}}@media(max-width:560px){.pie-cols{grid-template-columns:1fr}}
.pie-cols h4{margin:0 0 10px;font-size:14px;color:var(--noche);font-weight:800}
.pie-cols a{display:block;color:var(--tenue);text-decoration:none;margin:7px 0}.pie-cols a:hover{color:var(--noche);text-decoration:underline}
.pie-cols .wm{font-size:20px;margin-bottom:8px}
.pie-bajo{border-top:1px solid var(--trazo);padding:16px 0 22px;display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;font-size:12.5px}
.pie-bajo a{color:var(--tenue);text-decoration:none;margin-right:12px}.pie-bajo a:hover{text-decoration:underline}
/* ── explorador tipo Airbnb (raíz del dominio) ── */
.wrap-xl{max-width:1440px;margin:0 auto;padding:0 40px}
@media(max-width:900px){.wrap-xl{padding:0 20px}}@media(max-width:560px){.wrap-xl{padding:0 16px}}
.nav.abnb{border-bottom:0;box-shadow:0 1px 0 var(--trazo)}
.nav.abnb .nav-in{height:80px}
@media(max-width:900px){.nav.abnb .nav-in{height:auto;padding:12px 0 10px;flex-wrap:wrap}}
.busq{display:flex;align-items:center;background:var(--blanco);border:1px solid var(--trazo);border-radius:999px;box-shadow:0 3px 12px rgba(15,27,45,.08);height:48px;padding-left:8px;flex:0 1 auto;min-width:0;transition:box-shadow .15s}
.busq:hover{box-shadow:0 6px 20px rgba(15,27,45,.14)}
.busq .seg{display:flex;flex-direction:column;justify-content:center;padding:0 16px;min-width:0;height:100%;cursor:pointer;border-radius:999px;position:relative}
.busq .seg+.seg:before{content:"";position:absolute;left:0;top:14px;bottom:14px;width:1px;background:var(--trazo)}
.busq .seg:hover{background:var(--gris)}
.busq .seg small{font-size:11px;font-weight:800;color:var(--noche);line-height:1.1}
.busq .seg input,.busq .seg select{border:0;padding:0;margin:0;background:transparent;font-size:13.5px;font-weight:600;color:var(--noche);height:auto;width:100%;min-width:0;outline:none;box-shadow:none;font-family:inherit;line-height:1.2;-webkit-appearance:none;appearance:none}
.busq .seg input::placeholder{color:var(--tenue);font-weight:600}
.busq .seg.donde{min-width:190px}.busq .seg.dep{min-width:130px}.busq .seg.cuando{min-width:140px}
.busq .lupa{width:40px;height:40px;border-radius:50%;background:var(--esmeralda);color:#fff;border:0;display:inline-flex;align-items:center;justify-content:center;margin:0 4px 0 6px;cursor:pointer;flex:none}
.busq .lupa svg{width:18px;height:18px}
.nav.abnb .links{gap:4px}.links a.host{font-weight:700}
@media(max-width:900px){
  .nav.abnb .busq{order:3;width:100%;flex:1 0 100%;height:52px}
  .busq .seg{padding:0 12px}.busq .seg.donde{min-width:0;flex:1}.busq .seg.dep,.busq .seg.cuando{min-width:0;flex:0 0 auto}
  .busq .seg.cuando{display:none}.links a.host{display:none}
}
@media(max-width:560px){.busq .seg.dep{display:none}}
.cats{display:flex;align-items:center;gap:10px;padding:8px 0 0;position:relative}
.cats .cat-strip{display:flex;gap:6px;overflow-x:auto;min-width:0;flex:1;scrollbar-width:none;-webkit-overflow-scrolling:touch}
.cats .cat-strip::-webkit-scrollbar{display:none}
.cat{display:flex;flex-direction:column;align-items:center;gap:6px;padding:12px 14px 10px;border-bottom:2px solid transparent;color:var(--tenue);font-size:12px;font-weight:700;white-space:nowrap;cursor:pointer;text-decoration:none;user-select:none;opacity:.8;transition:opacity .15s}
.cat .ico{font-size:24px;line-height:1;filter:grayscale(.15)}
.cat:hover{opacity:1;color:var(--noche);border-bottom-color:var(--trazo)}
.cat.sel{opacity:1;color:var(--noche);border-bottom-color:var(--noche)}
.cats .filtros{flex:none;display:inline-flex;align-items:center;gap:8px;border:1px solid var(--trazo);border-radius:12px;padding:10px 14px;font-weight:700;font-size:13px;background:var(--blanco);cursor:pointer;color:var(--noche);font-family:inherit}
.cats .filtros:hover{border-color:var(--noche)}.cats .filtros.on{border-color:var(--noche);box-shadow:inset 0 0 0 1px var(--noche)}
.filtros-panel{display:none;gap:10px;flex-wrap:wrap;align-items:center;padding:10px 0 4px}
.filtros-panel.open{display:flex}
.expl{display:grid;grid-template-columns:minmax(0,1fr);gap:0;align-items:start;padding-top:8px}
.expl>*{min-width:0}
.expl.con-mapa{grid-template-columns:minmax(0,1fr) minmax(0,42%);gap:24px}
.expl .mapa-lado{display:none}
.expl.con-mapa .mapa-lado{display:block;position:sticky;top:100px}
.expl.con-mapa .mapa-lado .mapa{height:calc(100vh - 124px);min-height:420px;border-radius:14px;box-shadow:none;border:1px solid var(--trazo)}
@media(max-width:900px){
  .expl.con-mapa{grid-template-columns:minmax(0,1fr)}
  .expl.con-mapa .lista{display:none}
  .expl.con-mapa .mapa-lado{position:static}
  .expl.con-mapa .mapa-lado .mapa{height:calc(100vh - 200px);min-height:360px;border-radius:14px}
}
.tit{display:flex;align-items:baseline;justify-content:space-between;gap:12px;margin:22px 0 10px}
.tit h2{font-size:22px;display:flex;align-items:center;gap:8px;flex-wrap:wrap}.tit .cerca{color:var(--tenue);font-weight:600;font-size:14px}
@media(max-width:560px){.tit h2{font-size:19px}.tit .cerca{display:none}}
.lst-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:24px 20px}
@media(max-width:1180px){.lst-grid{grid-template-columns:repeat(3,minmax(0,1fr))}}
@media(max-width:760px){.lst-grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:20px 14px}}
@media(max-width:440px){.lst-grid{grid-template-columns:1fr}}
.expl.con-mapa .lst-grid{grid-template-columns:repeat(2,minmax(0,1fr))}
@media(max-width:1180px){.expl.con-mapa .lst-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
.lst{display:block;color:inherit;text-decoration:none;min-width:0}
.lst .foto{position:relative;border-radius:14px;overflow:hidden;aspect-ratio:1/0.95;background:var(--gris)}
.lst .fotos{display:flex;height:100%;overflow-x:auto;scroll-snap-type:x mandatory;scrollbar-width:none}
.lst .fotos::-webkit-scrollbar{display:none}
.lst .fotos img,.lst .fotos .sinfoto{flex:0 0 100%;width:100%;height:100%;object-fit:cover;scroll-snap-align:start;aspect-ratio:auto;display:block}
.lst .fotos .sinfoto{font-size:56px;display:flex}
.lst .fotos img{color:transparent}
.lst .foto img{transition:transform .35s}.lst:hover .foto img{transform:scale(1.03)}
.lst .badge{position:absolute;top:12px;left:12px;background:var(--blanco);color:var(--noche);font-size:12px;font-weight:800;padding:6px 10px;border-radius:999px;box-shadow:0 1px 4px rgba(15,27,45,.2)}
.lst .badge.pend{background:rgba(255,255,255,.92);color:var(--tenue)}
.lst .corazon{position:absolute;top:10px;right:10px;width:32px;height:32px;border:0;background:transparent;cursor:pointer;padding:0;display:inline-flex;align-items:center;justify-content:center}
.lst .corazon svg{width:24px;height:24px;fill:rgba(15,27,45,.5);stroke:#fff;stroke-width:2;transition:transform .15s}
.lst .corazon:hover svg{transform:scale(1.1)}.lst .corazon.on svg{fill:var(--rojo);stroke:var(--rojo)}
.lst .dots{position:absolute;left:0;right:0;bottom:10px;display:flex;justify-content:center;gap:4px;pointer-events:none}
.lst .dots i{width:6px;height:6px;border-radius:50%;background:rgba(255,255,255,.6)}.lst .dots i:first-child{background:#fff}
.lst .flecha{position:absolute;top:50%;transform:translateY(-50%);width:28px;height:28px;border-radius:50%;background:rgba(255,255,255,.92);border:0;display:none;align-items:center;justify-content:center;cursor:pointer;box-shadow:0 1px 4px rgba(15,27,45,.25);font-size:14px;font-weight:800;color:var(--noche);padding:0}
.lst .flecha.izq{left:10px}.lst .flecha.der{right:10px}
@media(hover:hover){.lst:hover .flecha{display:inline-flex}}
.lst .lb{padding:10px 2px 0;display:flex;flex-direction:column;gap:2px;font-size:14px}
.lst .l1{display:flex;justify-content:space-between;gap:8px;align-items:baseline}
.lst .l1 b{font-weight:800;font-size:15px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;min-width:0}
.lst .rate{white-space:nowrap;font-weight:700;font-size:13.5px;color:var(--noche)}
.lst .l2{color:var(--tenue);font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.lst .l3{margin-top:4px}.lst .l3 b{font-weight:800;font-size:15px}
.lst .l3 .app{display:inline-block;margin-top:6px;border:1px solid var(--trazo);border-radius:8px;padding:5px 9px;font-size:12px;font-weight:700;color:var(--noche)}
.lst.pend .foto img,.lst.pend .foto .sinfoto{filter:saturate(.55)}
.btn-mapa{position:fixed;left:50%;transform:translateX(-50%);bottom:24px;z-index:25;background:var(--noche);color:#fff;border:0;border-radius:999px;padding:13px 20px;font-weight:800;font-size:14px;cursor:pointer;box-shadow:0 8px 24px rgba(15,27,45,.28);display:inline-flex;align-items:center;gap:8px;font-family:inherit}
.btn-mapa:hover{transform:translateX(-50%) scale(1.03)}
.ubic-mini{display:flex;align-items:center;gap:8px;flex-wrap:wrap;font-size:13.5px;font-weight:600;color:var(--tenue);padding:14px 0 0}
.ubic-mini button{border:0;background:transparent;color:var(--esmeralda);font-weight:800;cursor:pointer;font-family:inherit;font-size:13.5px;padding:0;text-decoration:underline}
.vacio{padding:40px 0;text-align:center;color:var(--tenue);font-weight:600}
/* sesión con Google */
.links a.yo{display:inline-flex;align-items:center;gap:8px;padding:5px 10px 5px 5px;border:1px solid var(--trazo);border-radius:999px;background:var(--blanco)}
.links a.yo:hover{background:var(--blanco);box-shadow:var(--sombra)}
.avatar{width:28px;height:28px;border-radius:50%;object-fit:cover;display:inline-flex;align-items:center;justify-content:center;background:var(--tinte);color:var(--teal);font-weight:800;font-size:13px}
@media(max-width:640px){.links a.yo,.links a.entrar{display:inline-flex}.links a.yo .nom{display:none}}
.login-box{background:var(--tinte);border-radius:var(--r);padding:16px 18px;margin-top:8px}
.login-box b{font-size:15px}
.quien{display:flex;align-items:center;gap:12px;margin:10px 0 4px;padding:12px 14px;border:1px solid var(--trazo);border-radius:var(--r);background:var(--blanco)}
.quien img{width:40px;height:40px;border-radius:50%;object-fit:cover}
.quien .m{font-size:13px;color:var(--tenue);font-weight:600}
.quien>div{flex:1;min-width:0}.quien .btn{padding:8px 12px;font-size:13px}
.marca{margin-top:48px;border-top:1px solid var(--trazo)}
.marca section{padding:44px 0}
.marca section:first-child{border-top:0}
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


_FLAGS = {
    "PE": "<svg class='flag' viewBox='0 0 3 2'><rect width='3' height='2' fill='#D91023'/><rect x='1' width='1' height='2' fill='#fff'/></svg>",
    "EC": "<svg class='flag' viewBox='0 0 4 2'><rect width='4' height='2' fill='#FFD100'/><rect y='1' width='4' height='.5' fill='#0057B8'/><rect y='1.5' width='4' height='.5' fill='#D91023'/></svg>",
    "BO": "<svg class='flag' viewBox='0 0 3 2'><rect width='3' height='2' fill='#007934'/><rect width='3' height='1.34' fill='#F4E400'/><rect width='3' height='.67' fill='#D52B1E'/></svg>",
}


def bandera(iso: str) -> str:
    """Bandera como SVG inline (los emoji 🇵🇪 no se renderizan en Windows)."""
    return _FLAGS.get((iso or "").upper(), "")


def sello_verificada() -> str:
    return "<span class='pill'>✓ Verificada</span>"


def check_svg() -> str:
    return ("<div class='check'><svg viewBox='0 0 24 24'><path fill='none' stroke='#0E8F67' stroke-width='3' "
            "stroke-linecap='round' stroke-linejoin='round' d='M5 12.5l4.5 4.5L19 7'/></svg></div>")


def footer() -> str:
    """Pie de página con columnas (estilo Airbnb) + datos del comercio que
    exigen Culqi/INDECOPI (razón social, RUC, contacto) en TODAS las páginas."""
    return (
        "<footer class='pie'><div class='wrap-xl'><div class='pie-cols'>"
        f"<div>{wordmark(20)}<div>Reserva, juega, repite.</div>"
        "<div style='margin-top:10px;font-size:12.5px'>Fútbol · Tenis · Pádel · Pickleball<br>Perú · Ecuador · Bolivia</div></div>"
        "<div><h4>Reservar</h4><a href=\"/canchas\">Todas las canchas</a><a href='/canchas?deporte=futbol'>Canchas de fútbol</a>"
        "<a href='/canchas?deporte=tenis'>Canchas de tenis</a><a href='/canchas?deporte=padel'>Canchas de pádel</a>"
        "<a href='/#servicios'>Servicios y precios</a></div>"
        "<div><h4>Soporte</h4><a href='/#contacto'>Contacto</a><a href='/#como'>Cómo funciona</a>"
        "<a href='/#pagos'>Pagos y seguridad</a><a href='/#devoluciones'>Cancelaciones y devoluciones</a>"
        "<a href='/#reclamaciones'>📕 Libro de Reclamaciones</a></div>"
        "<div><h4>Pichangol</h4><a href='https://play.google.com/store/apps/details?id=pe.ebim.pichangol' rel='noopener'>Descarga la app</a>"
        "<a href='https://play.google.com/store/apps/details?id=pe.ebim.pichangol' rel='noopener'>Pon tu cancha en Pichangol</a>"
        "<a href=\"/legal/terminos\">Términos y condiciones</a><a href=\"/legal/privacidad\">Política de privacidad</a>"
        "<a href=\"/legal/eliminar-cuenta\">Eliminar mi cuenta</a></div>"
        "</div><div class='pie-bajo'><div>© 2026 Pichangol · GRUPO EBIM S.A.C. · RUC 20602517986 · San Isidro, Lima, Perú · "
        "<a href='mailto:contacto@ebim.pe'>contacto@ebim.pe</a></div>"
        "<div><a href='/#terminos'>Términos</a><a href='/#privacidad'>Privacidad</a><a href='/#reclamaciones'>Libro de Reclamaciones</a></div>"
        "</div></div></footer>")


def chip_sesion(ses: dict | None, volver: str = "/") -> str:
    """Avatar + nombre si hay sesión de Google; si no, "Iniciar sesión" (solo
    cuando el login web está configurado)."""
    from web import sesion as _s
    if ses:
        foto = (f"<img class='avatar' src='{e(ses.get('foto'))}' alt=''>" if ses.get("foto")
                else f"<span class='avatar ini'>{e((ses.get('nombre') or ses.get('email') or '?')[:1].upper())}</span>")
        return (f"<a class='yo' href='/entrar' title='{e(ses.get('email'))}' onclick='return false'>{foto}"
                f"<span class='nom'>{e((ses.get('nombre') or ses.get('email') or '').split(' ')[0])}</span></a>")
    if not _s.activo():
        return ""
    from urllib.parse import quote as _q
    return f"<a class='entrar' href='/entrar?volver={_q(volver, safe='')}'>Iniciar sesión</a>"


def nav_simple(ses: dict | None = None) -> str:
    return ("<header class='nav'><div class='wrap nav-in'>"
            f"{wordmark()}"
            "<nav class='links'><a href='/canchas'>Canchas</a><a href='/#servicios'>Servicios</a>"
            f"<a href='/#contacto'>Contacto</a>{chip_sesion(ses, '/canchas')}<a class='cta' href='/canchas'>Reservar</a></nav>"
            "</div></header>")


def shell(titulo: str, cuerpo: str, *, desc: str = "", extra_head: str = "",
          canonical: str = "", og_image: str = "/static/brand/logo_pichangol.png",
          con_barra: bool = False, jsonld: str = "", nav: str = "",
          ancho: bool = False, titulo_tab: str = "", sesion: dict | None = None) -> HTMLResponse:
    """Envuelve una página pública. [nav] = cabecera propia (la raíz lleva el
    buscador tipo Airbnb); [ancho] = contenedor 1440 px (grilla de canchas)."""
    page = (
        "<!doctype html><html lang='es'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1,viewport-fit=cover'>"
        f"<title>{e(titulo_tab or (titulo + ' · Pichangol'))}</title>"
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
        f"{nav or nav_simple(sesion)}"
        f"<main class='{'wrap-xl' if ancho else 'wrap'}'>{cuerpo}</main>"
        f"{footer()}"
        "</body></html>")
    return HTMLResponse(page, headers={"Cache-Control": "no-store"})
