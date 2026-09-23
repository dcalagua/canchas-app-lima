"""Sistema de diseño de la WEB de Pichangol — el MISMO look & feel del APK
(`lib/theme.dart`, `lib/widgets/marca.dart`, estándar Airbnb del CLAUDE.md):

- Tipografía **DM Sans** (la equivalente libre de Airbnb Cereal, que es
  propietaria y no se puede descargar), pesos 500/600/700/800.
- Paleta del logo nuevo: blanco, azul noche `#0F1B2D` (texto/oscuros),
  esmeralda `#0E8F67` (CTA/acento), dorado `#D9B45A`, papel `#F4F7FA`,
  trazo `#DDE5EF`, texto tenue `#627080`, tinte esmeralda `#E7F4EF`.
- Cabecera tal cual airbnb.com (`cabecera()`): logo · pestañas con ícono ·
  "Modo anfitrión" + avatar + ☰ (menú desplegable) · buscador grande centrado
  con desplegable de recientes/zonas; se compacta al hacer scroll.
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
  /* Paleta del LOGO oficial (pin verde + pelota + arco naranja + "Pichangol" azul noche) */
  --blanco:#FFFFFF;--noche:#0A1B3D;--esmeralda:#0B8A3E;--teal:#067A38;--lima:#7CB518;--naranja:#F28C28;--dorado:#D9B45A;
  --papel:#FFFFFF;--trazo:#DDE5E0;--tenue:#5F6F7A;--tinte:#E6F4EA;--gris:#EDF1EE;
  --ok-bg:#E9F4EE;--ok-fg:#1F6E49;--warn-bg:#FDF2D6;--warn-fg:#946200;--bad-bg:#FBE7E7;--bad-fg:#C0392B;
  --rojo:#C13515;--sombra:0 2px 14px rgba(15,27,45,.06);--sombra2:0 10px 30px rgba(15,27,45,.10);
  --r:16px;--r-lg:20px;--r-btn:12px;
}
"""

CSS = TOKENS + """
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%;overflow-x:hidden}body{overflow-x:clip;max-width:100%}
body{margin:0;background:var(--papel);color:var(--noche);font-family:"DM Sans","Airbnb Cereal VF","Circular",system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;font-weight:500;line-height:1.45}
a{color:var(--esmeralda)}img{max-width:100%}
.wrap{max-width:1080px;margin:0 auto;padding:0 20px}
h1,h2,h3{font-weight:800;letter-spacing:-.3px;color:var(--noche);margin:0}
h1{font-size:28px;line-height:1.15}h2{font-size:20px}h3{font-size:16px}
.sub{color:var(--tenue);font-size:15px;margin:6px 0 0}
/* barra */
.nav{background:var(--blanco);border-bottom:1px solid var(--trazo);position:sticky;top:0;z-index:20}
.nav-in{height:64px;display:flex;align-items:center;justify-content:space-between;gap:12px}
.wm{display:inline-flex;align-items:center;gap:6px;font-weight:800;font-style:normal;font-size:22px;letter-spacing:-.4px;color:var(--noche);text-decoration:none;line-height:1}
.wm img{width:1.7em;height:1.7em;object-fit:contain;display:block}
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
/* Mis reservas = "Viajes" de Airbnb: lista a la izquierda, mapa a la derecha */
.viajes{display:grid;grid-template-columns:minmax(0,520px) minmax(0,1fr);gap:40px;align-items:start;padding-top:8px}
.viajes h1{font-size:26px;margin-top:6px}
.viajes-lista{min-width:0}
.viajes-mapa{position:sticky;top:98px}
.viajes-mapa .mapa{height:calc(100vh - 122px);min-height:420px;border-radius:24px;border:1px solid var(--trazo);box-shadow:none}
@media(max-width:900px){.viajes{grid-template-columns:minmax(0,1fr)}.viajes-mapa{display:none}}
.viajes-cards{display:flex;flex-direction:column;gap:14px;margin-top:16px}
.viaje{display:flex;gap:14px;align-items:stretch;background:var(--blanco);border:1px solid var(--trazo);border-radius:16px;padding:12px;text-decoration:none;color:inherit;box-shadow:0 2px 10px rgba(15,27,45,.06);transition:box-shadow .15s,transform .15s;min-width:0}
.viaje:hover{box-shadow:0 8px 24px rgba(15,27,45,.12);transform:translateY(-1px)}
.viaje.pasada{opacity:.85}
.viaje .vfoto{flex:none;width:96px;height:96px;border-radius:12px;overflow:hidden;background:var(--gris)}
.viaje .vfoto img{width:100%;height:100%;object-fit:cover;display:block}
.viaje .vfoto .sinfoto{width:100%;height:100%;display:flex;align-items:center;justify-content:center;font-size:36px;background:var(--tinte)}
.viaje .vtxt{flex:1;min-width:0;display:flex;flex-direction:column;justify-content:center}
.viaje .vtxt b{font-size:16px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.viaje .vcuando{font-size:13.5px;color:var(--tenue);font-weight:600;margin-top:4px}
.viaje .vpie{display:flex;align-items:center;gap:8px;margin-top:8px;flex-wrap:wrap}
.viaje .av{width:26px;height:26px;border-radius:50%;object-fit:cover;border:2px solid #fff;box-shadow:0 0 0 1px var(--trazo);display:inline-flex;align-items:center;justify-content:center;background:var(--tinte);color:var(--teal);font-weight:800;font-size:12px}
.viaje .vprecio{font-weight:800;font-size:13.5px;margin-left:auto}
.viaje .vacc .lnk{border:0;background:transparent;color:var(--noche);font-family:inherit;font-weight:700;font-size:13px;text-decoration:underline;cursor:pointer;padding:0}
.viaje-vacio{background:var(--gris);border-radius:16px;padding:22px;margin-top:16px}
.viaje-vacio .btn{margin-top:10px;padding:10px 16px;font-size:14px}
.viajes-det{margin-top:18px;border:1px solid var(--trazo);border-radius:14px;padding:4px 16px}
.viajes-det summary{cursor:pointer;list-style:none;display:flex;align-items:center;gap:10px;padding:12px 0;font-weight:700;font-size:15px}
.viajes-det summary::-webkit-details-marker{display:none}
.viajes-det summary:after{content:"›";margin-left:auto;font-size:22px;color:var(--tenue);transition:transform .15s}
.viajes-det[open] summary:after{transform:rotate(90deg)}
.viajes-det summary small{color:var(--tenue);font-weight:600}
.viajes-det .viajes-cards{margin:4px 0 12px}
.cancelada{display:flex;justify-content:space-between;gap:12px;align-items:center;padding:12px 0;border-top:1px solid var(--trazo)}
.aviso.ok{background:var(--ok-bg);color:var(--ok-fg);border-radius:14px;padding:12px 16px;font-weight:600;margin-top:8px}
/* Mis reservas (tarjetas simples, se conservan para otras páginas) */
.res{background:var(--blanco);border:1px solid var(--trazo);border-radius:var(--r);padding:16px 18px;margin-top:12px;box-shadow:var(--sombra)}
.res.pasada{opacity:.85}
.res-cab{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}.res-cab b{font-size:16px}
.res-cuando{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-top:10px;font-size:14px;font-weight:600;color:var(--noche)}
.res .acciones{margin-top:10px}.res .acciones .btn{flex:0 0 auto;min-width:0;padding:9px 14px;font-size:13.5px}
.pill.warn{background:var(--warn-bg);color:var(--warn-fg)}.pill.bad{background:var(--bad-bg);color:var(--bad-fg)}.pill.ok{background:var(--ok-bg);color:var(--ok-fg)}
/* mapa de "Cómo llegar" dentro de la ficha */
.mapa-ficha{display:none;margin:10px 0 4px}
.mapa-ficha.open{display:block}
.mapa-ficha .mapa{height:300px;border-radius:14px;border:1px solid var(--trazo);box-shadow:none}
.mapa-ficha .pie-mapa{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-top:8px;font-size:13px;color:var(--tenue);font-weight:600}
.mapa-ficha .pie-mapa a{font-weight:700}
/* Mapa de FORMULARIO (sede de academia, Pon tu cancha): siempre visible, a
   diferencia de .mapa-ficha que arranca oculto hasta "Cómo llegar". */
.mapa-sede{display:block;height:300px;border-radius:14px;border:1px solid var(--trazo);overflow:hidden;background:#EEF2F5}
/* turnos por franja (Mañana / Tarde / Noche) con precio visible */
.slots-grupo{margin:14px 0 4px}
.slots-grupo h5{margin:0 0 8px;font-size:13px;font-weight:700;color:var(--noche);display:flex;align-items:center;gap:8px}
.slots-grupo h5 small{font-weight:600;color:var(--tenue)}
.slots-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(118px,1fr));gap:8px}
.slot{display:flex;flex-direction:column;align-items:flex-start;gap:2px;padding:10px 12px;border:1px solid var(--trazo);border-radius:14px;background:var(--blanco);cursor:pointer;user-select:none;box-shadow:0 1px 3px rgba(15,27,45,.04);transition:border-color .12s,box-shadow .12s;min-width:0;position:relative}
.slot:hover{border-color:var(--noche)}
.slot b{font-size:15px;font-weight:800;color:var(--noche);line-height:1.1}
.slot b small{font-weight:600;color:var(--tenue);font-size:12px}
.slot .pr{font-size:13.5px;font-weight:700;color:var(--teal);margin-top:2px}
.slot .tag{font-size:11px;font-weight:700;color:#946200;background:var(--warn-bg);border-radius:999px;padding:2px 7px;margin-top:3px}
.slot .dia{font-size:11px;font-weight:700;color:var(--tenue)}
.slot.sel{background:var(--noche);border-color:var(--noche)}.slot.sel b,.slot.sel b small,.slot.sel .pr,.slot.sel .dia{color:#fff}
.slot.sel .tag{background:rgba(255,255,255,.18);color:#fff}
.slot.off{opacity:.45;cursor:not-allowed;background:var(--gris)}.slot.off b{text-decoration:line-through}
.slots-nota{font-size:12.5px;color:var(--tenue);font-weight:600;margin:8px 0 0}

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
[hidden]{display:none!important}
.res-busca{border:1px solid var(--borde,#E4E4E4);border-radius:14px;margin-top:6px;overflow:hidden;box-shadow:0 8px 24px rgba(0,0,0,.08);background:#fff}
.res-it{display:block;width:100%;text-align:left;border:0;background:#fff;padding:10px 12px;cursor:pointer;font:inherit;border-top:1px solid #f0f0f0}
.res-it:first-child{border-top:0}.res-it:hover{background:#f6f7f8}.res-it b{display:block}.res-it small{color:#717171}
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
.pin-precio{background:var(--blanco);color:var(--noche);font-weight:800;font-size:12.5px;padding:5px 9px;border-radius:999px;box-shadow:0 2px 8px rgba(15,27,45,.25);border:1px solid var(--trazo);white-space:nowrap;font-family:"DM Sans",system-ui,sans-serif}
.pin-precio.yo{background:var(--esmeralda);color:#fff;border-color:var(--esmeralda)}
.pin-precio.pend{background:var(--gris);color:var(--tenue)}
.card.pend img,.card.pend .sinfoto{filter:saturate(.6)}
.leaflet-popup-content-wrapper{border-radius:14px;font-family:"DM Sans",system-ui,sans-serif}
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
.pie-cols .wm{font-size:20px;margin-bottom:8px}.pie-redes{display:flex;align-items:center;gap:8px;margin-top:14px;font-size:12.5px}.pie-redes a{display:inline-flex;align-items:center;justify-content:center;width:34px;height:34px;border-radius:50%;border:1px solid var(--trazo);background:var(--blanco);color:var(--noche);margin:0}.pie-redes a:hover{background:var(--noche);color:#fff;border-color:var(--noche)}.pie-redes svg{width:16px;height:16px}.pie-cols a.libro{display:inline-flex;align-items:center;gap:8px;padding:6px 12px 6px 8px;border:1.5px solid #C8102E;border-radius:10px;color:#C8102E;font-weight:800;margin-top:10px}.pie-cols a.libro:hover{background:#C8102E;color:#fff;text-decoration:none}
.pie-bajo{border-top:1px solid var(--trazo);padding:16px 0 22px;display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;font-size:12.5px}
.pie-bajo a{color:var(--tenue);text-decoration:none;margin-right:12px}.pie-bajo a:hover{text-decoration:underline}
/* ── explorador tipo Airbnb (raíz del dominio) ── */
.wrap-xl{max-width:none;margin:0 auto;padding:0 80px}
@media(max-width:1128px){.wrap-xl{padding:0 40px}}@media(max-width:744px){.wrap-xl{padding:0 24px}}@media(max-width:560px){.wrap-xl{padding:0 16px}}
/* ── cabecera tal cual airbnb.com: logo · pestañas con ícono · Modo dueño + avatar + ☰ · buscador grande centrado ── */
.nav.abnb{border-bottom:0;box-shadow:0 1px 0 var(--trazo);background:var(--blanco)}
.cab{display:grid;grid-template-columns:minmax(max-content,1fr) minmax(0,auto) minmax(max-content,1fr);grid-template-areas:"logo tabs der" "busq busq busq";align-items:center;column-gap:16px;padding-top:8px;padding-bottom:14px}
.cab-logo{grid-area:logo;display:flex;align-items:center;height:64px}
.cab-tabs{grid-area:tabs;display:flex;justify-content:center;justify-content:safe center;align-items:flex-end;gap:4px;min-width:0;overflow-x:auto;scrollbar-width:none;-webkit-overflow-scrolling:touch}
.cab-tabs::-webkit-scrollbar{display:none}
.cab-der{grid-area:der;display:flex;justify-content:flex-end;align-items:center;gap:6px;height:64px}
.cab-busq{grid-area:busq;display:flex;justify-content:center;margin-top:2px}
.cat{display:flex;align-items:center;gap:7px;padding:14px 10px 12px;border-bottom:2px solid transparent;color:var(--tenue);font-size:13.5px;font-weight:600;white-space:nowrap;cursor:pointer;text-decoration:none;user-select:none;transition:color .15s;position:relative}
.cat .ico{font-size:24px;line-height:1;filter:grayscale(.15);transition:transform .15s}
.cat:hover{color:var(--noche)}.cat:hover .ico{transform:scale(1.08)}
.cat:hover:after{content:"";position:absolute;left:10px;right:10px;bottom:-2px;height:2px;background:var(--trazo)}
.cat.sel{color:var(--noche);font-weight:700}.cat.sel:after{content:"";position:absolute;left:10px;right:10px;bottom:-2px;height:2px;background:var(--noche)}
.cab-der a.host{color:var(--noche);text-decoration:none;font-weight:600;font-size:14px;padding:10px 14px;border-radius:999px;white-space:nowrap}
.cab-der a.host:hover{background:var(--gris)}
.redondo{width:40px;height:40px;border-radius:50%;border:0;background:var(--gris);display:inline-flex;align-items:center;justify-content:center;cursor:pointer;padding:0;color:var(--noche);text-decoration:none;flex:none;overflow:hidden}
.redondo:hover{background:#E3E8E4}.redondo svg{width:18px;height:18px}
.redondo img,.redondo .ini{width:100%;height:100%;object-fit:cover;display:inline-flex;align-items:center;justify-content:center;background:var(--tinte);color:var(--teal);font-weight:800;font-size:15px}
.menu{position:relative}
.menu-panel{display:none;position:absolute;right:0;top:48px;width:264px;background:var(--blanco);border-radius:16px;box-shadow:0 8px 28px rgba(15,27,45,.18);border:1px solid var(--trazo);padding:8px 0;z-index:40;text-align:left}
.menu-panel.open{display:block}
.menu-panel a,.menu-panel button{display:flex;align-items:center;gap:10px;width:100%;padding:11px 16px;border:0;background:transparent;color:var(--noche);text-decoration:none;font-size:14px;font-weight:500;cursor:pointer;font-family:inherit;text-align:left}
.menu-panel a:hover,.menu-panel button:hover{background:var(--gris)}
.menu-panel a.b,.menu-panel button.b{font-weight:700}
.menu-panel hr{border:0;border-top:1px solid var(--trazo);margin:6px 0}
.menu-panel .yo{display:flex;align-items:center;gap:10px;padding:10px 16px 6px;min-width:0}
.menu-panel .yo img,.menu-panel .yo .ini{width:36px;height:36px;border-radius:50%;object-fit:cover;flex:none;display:inline-flex;align-items:center;justify-content:center;background:var(--tinte);color:var(--teal);font-weight:800}
.menu-panel .yo div{min-width:0}.menu-panel .yo b{display:block;font-size:14px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.menu-panel .yo small{display:block;color:var(--tenue);font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
/* buscador grande (pastilla) */
.busq{display:flex;align-items:center;background:var(--blanco);border:1px solid var(--trazo);border-radius:999px;box-shadow:0 3px 12px rgba(15,27,45,.08);height:66px;padding-left:8px;width:100%;max-width:850px;min-width:0;position:relative;transition:box-shadow .15s}
.busq:hover{box-shadow:0 6px 20px rgba(15,27,45,.14)}
.busq .seg{display:flex;flex-direction:column;justify-content:center;padding:0 24px;min-width:0;height:100%;cursor:pointer;border-radius:999px;position:relative}
.busq .seg+.seg:before{content:"";position:absolute;left:0;top:18px;bottom:18px;width:1px;background:var(--trazo)}
.busq .seg:hover{background:var(--gris)}
.busq:focus-within{background:var(--gris)}
.busq .seg:focus-within{background:var(--blanco);box-shadow:0 6px 20px rgba(10,27,61,.16);z-index:1}
.busq .seg:focus-within+.seg:before,.busq .seg:hover+.seg:before{display:none}
.busq .seg input{caret-color:var(--noche)}
.busq .seg select{padding-right:18px;background:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath fill='none' stroke='%230A1B3D' stroke-width='2.5' stroke-linecap='round' stroke-linejoin='round' d='M6 9l6 6 6-6'/%3E%3C/svg%3E") no-repeat right center/14px;cursor:pointer}
.busq .seg small{font-size:12px;font-weight:700;color:var(--noche);line-height:1.1;margin-bottom:2px}
.busq .seg input,.busq .seg select{border:0;padding:0;margin:0;background:transparent;font-size:14px;font-weight:500;color:var(--noche);height:auto;width:100%;min-width:0;outline:none;box-shadow:none;font-family:inherit;line-height:1.2;-webkit-appearance:none;appearance:none}
.busq .seg input::placeholder{color:var(--tenue);font-weight:500}
.busq .seg.donde{flex:1.4;min-width:0}
.busq .lupa{height:50px;border-radius:999px;background:var(--esmeralda);color:#fff;border:0;display:inline-flex;align-items:center;justify-content:center;gap:8px;margin:0 8px 0 4px;padding:0 18px 0 14px;cursor:pointer;flex:none;font-weight:700;font-size:15px;font-family:inherit;transition:transform .12s,background .15s}
.busq .lupa:hover{background:var(--teal)}.busq .lupa svg{width:18px;height:18px;flex:none}
/* desplegable bajo "Dónde": búsquedas recientes + zonas sugeridas */
.sug{display:none;position:absolute;left:0;top:74px;width:min(460px,100%);background:var(--blanco);border-radius:24px;box-shadow:0 8px 32px rgba(15,27,45,.2);border:1px solid var(--trazo);padding:14px 8px 10px;z-index:41;cursor:default}
.sug.open{display:block}
.sug h5{margin:4px 16px 6px;font-size:12.5px;font-weight:700;color:var(--noche)}
.sug .it{display:flex;align-items:center;gap:14px;width:100%;padding:8px 12px;border:0;background:transparent;border-radius:12px;cursor:pointer;font-family:inherit;text-align:left;color:var(--noche);min-width:0}
.sug .it:hover{background:var(--gris)}
.sug .it .ic{width:44px;height:44px;border-radius:12px;background:var(--gris);display:inline-flex;align-items:center;justify-content:center;font-size:22px;flex:none}
.sug .it.cerca .ic{background:var(--tinte)}
.sug .it b{display:block;font-size:14px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.sug .it small{display:block;font-size:12.5px;color:var(--tenue)}
.sug .it div{min-width:0}
.sug.centro{left:0;right:0;width:auto}
.sug.der{left:auto;right:0;width:min(560px,100%)}
.busq .seg.cuando,.busq .seg.hora{flex:1;min-width:0}.busq .seg input[readonly]{cursor:pointer}
/* calendario tipo Airbnb (dos meses) */
.cal-panel{padding:18px 24px 20px}
.cal-modo{display:flex;justify-content:center;margin-bottom:8px}
.cal-modo button{border:0;background:var(--gris);color:var(--noche);font-family:inherit;font-weight:600;font-size:14px;padding:10px 26px;cursor:pointer}
.cal-modo button:first-child{border-radius:999px 0 0 999px;padding-left:30px}.cal-modo button:last-child{border-radius:0 999px 999px 0;padding-right:30px}
.cal-modo button.on{background:var(--blanco);border-radius:999px;box-shadow:0 2px 8px rgba(15,27,45,.16);border:1px solid var(--trazo)}
.cal-nav{position:relative;height:0}
.cal-nav button{position:absolute;top:8px;width:32px;height:32px;border-radius:50%;border:0;background:transparent;font-size:22px;line-height:1;cursor:pointer;color:var(--noche);font-family:inherit}
.cal-nav button:hover{background:var(--gris)}.cal-nav button:disabled{opacity:.25;cursor:default;background:transparent}
.cal-nav .cal-ant{left:0}.cal-nav .cal-sig{right:0}
.cal-meses{display:grid;grid-template-columns:1fr 1fr;gap:0 40px;padding:0 24px}
.cal-mes{min-width:0}
.cal-tit{text-align:center;font-weight:700;font-size:15px;padding:12px 0 14px}
.cal-grid{display:grid;grid-template-columns:repeat(7,1fr);gap:2px 0;justify-items:center}
.cal-dn{font-size:11.5px;color:var(--tenue);font-weight:600;padding:4px 0 8px}
.cal-d{width:40px;height:40px;border-radius:50%;border:0;background:transparent;font-family:inherit;font-weight:600;font-size:13.5px;color:var(--noche);cursor:pointer}
.cal-d:hover{box-shadow:inset 0 0 0 1.5px var(--noche)}
.cal-d.off{color:#C4CBC7;text-decoration:line-through;cursor:default;box-shadow:none}
.cal-d.hoy{font-weight:800}.cal-d.sel{background:var(--noche);color:#fff}
.cal-atajos{display:flex;gap:8px;flex-wrap:wrap;margin-top:14px;padding:0 24px}
.cal-atajos .chip{font-size:13px;padding:8px 14px}.cal-atajos .chip.sel{box-shadow:inset 0 0 0 1.5px var(--noche);background:var(--blanco);border-color:var(--noche);color:var(--noche)}
/* panel de horas */
.hora-panel{padding:14px 8px 12px}
.hgrupo{padding:4px 12px 8px}.hgrupo h5{margin:6px 0 8px 4px}
.hchips{display:flex;flex-wrap:wrap;gap:8px}
.hchip{font-size:13px;padding:8px 12px}.hchip.sel{background:var(--noche);color:#fff;border-color:var(--noche)}
.hchip.off{color:#C4CBC7;text-decoration:line-through;cursor:default;box-shadow:none;border-color:var(--gris)}
.hgrupo.off h5{color:#C4CBC7}
.hora-aviso{margin:4px 12px 8px;padding:10px 12px;border-radius:12px;background:var(--warn-bg);color:var(--warn-fg);font-size:13px;font-weight:600}
.ubic-mini #resBusq b{color:var(--noche)}.ubic-mini #resBusq button{margin-left:6px}
@media(max-width:900px){
  .cal-meses{grid-template-columns:1fr;padding:0 16px}.cal-panel{padding:14px 12px 16px}.cal-atajos{padding:0 12px}
  .cal-d{width:36px;height:36px}
  .sug.der{width:100%}
}
/* pastilla compacta (páginas interiores, como Airbnb al hacer scroll) */
.busq-mini{display:inline-flex;align-items:center;height:48px;border:1px solid var(--trazo);border-radius:999px;box-shadow:0 1px 2px rgba(15,27,45,.08),0 4px 12px rgba(15,27,45,.05);padding:0 8px 0 20px;color:var(--noche);text-decoration:none;font-size:14px;font-weight:600;white-space:nowrap;min-width:0;transition:box-shadow .15s}
.busq-mini:hover{box-shadow:0 2px 4px rgba(15,27,45,.12),0 6px 16px rgba(15,27,45,.1)}
.busq-mini span{padding:0 16px 0 0;min-width:0;overflow:hidden;text-overflow:ellipsis}
.busq-mini span+span{border-left:1px solid var(--trazo);padding-left:16px}
.busq-mini span.tenue{color:var(--tenue);font-weight:500}
.busq-mini i{width:32px;height:32px;border-radius:50%;background:var(--esmeralda);color:#fff;display:inline-flex;align-items:center;justify-content:center;flex:none;margin-left:4px}
.busq-mini i svg{width:14px;height:14px}.busq-mini .mov,.busq-mini .lupa-mov{display:none}
.cab-mini{grid-area:mini;display:none;justify-content:center;min-width:0}
/* compacta (al hacer scroll) y simple (páginas interiores): logo · pastilla chica · derecha */
.cab.chica,.cab.simple{grid-template-columns:1fr auto 1fr;grid-template-areas:"logo mini der";padding-bottom:8px}
.cab.chica .cab-tabs,.cab.chica .cab-busq{display:none}.cab.chica .cab-mini,.cab.simple .cab-mini{display:flex}
/* modo anfitrión (airbnb.com/hosting): logo · Hoy/Calendario/Reservas/Ingresos/Canchas · derecha */
.cab.anfitrion{grid-template-columns:1fr auto 1fr;grid-template-areas:"logo tabs der";padding-bottom:0}
.cab.anfitrion .cat{padding:22px 12px 20px;font-size:14px}
@media(max-width:900px){.cab.anfitrion{grid-template-columns:1fr auto;grid-template-areas:"logo der" "tabs tabs"}.cab.anfitrion .cab-tabs{justify-content:flex-start;margin:0 -20px;padding:0 20px}.cab.anfitrion .cat{padding:12px 10px 10px}}
/* menú del modo anfitrión = el del app (cabecera verde + tarjetas con ícono de color) */
.anf-hero{background:linear-gradient(135deg,var(--esmeralda),var(--teal));color:#fff;border-radius:0 0 28px 28px;margin:0 -80px;padding:22px 80px 30px;position:relative}
@media(max-width:1128px){.anf-hero{margin:0 -40px;padding:20px 40px 26px}}@media(max-width:744px){.anf-hero{margin:0 -24px;padding:16px 24px 22px}}@media(max-width:560px){.anf-hero{margin:0 -16px;padding:14px 16px 20px}}
.anf-hero h1{color:#fff;font-size:30px;display:inline-block;vertical-align:middle;margin:0}
.anf-hero .volver{color:#fff;text-decoration:none;font-size:34px;line-height:1;margin-right:14px;vertical-align:middle;display:inline-block}
.anf-hero p{margin:8px 0 0;font-size:17px;opacity:.92;max-width:640px}
.anf-menu{display:flex;flex-direction:column;gap:14px;max-width:760px;margin:22px auto 0}
.anf-item{display:flex;align-items:center;gap:16px;background:var(--blanco);border-radius:18px;padding:16px 18px;text-decoration:none;color:inherit;box-shadow:0 2px 12px rgba(15,27,45,.08);border:1px solid var(--trazo);transition:box-shadow .15s,transform .15s}
.anf-item:hover{box-shadow:0 8px 24px rgba(15,27,45,.14);transform:translateY(-1px)}
.anf-item .ico,.anf-item-ico{flex:none;width:56px;height:56px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;font-size:26px;color:#fff}
.anf-item .txt{flex:1;min-width:0}.anf-item .txt b{display:block;font-size:19px}.anf-item .txt small{display:block;color:var(--tenue);font-size:14px;font-weight:600;margin-top:2px}
.anf-item .chev{font-size:30px;color:var(--tenue);line-height:1}
@media(max-width:560px){.anf-item .pill{display:none}.anf-item .txt b{font-size:17px}.anf-item .ico{width:48px;height:48px;font-size:22px}}
.anf-back{display:inline-block;margin-top:18px;color:var(--tenue);font-weight:700;text-decoration:none;font-size:14px}.anf-back:hover{color:var(--noche)}
/* panel del anfitrión */
.anf-hola{font-size:28px;margin:26px 0 4px}
.anf-tabs{display:flex;gap:8px;flex-wrap:wrap;margin:18px 0 12px}
.anf-tabs .chip.sel{background:var(--noche);color:#fff;border-color:var(--noche)}
.anf-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:14px}
.anf-res{background:var(--blanco);border:1px solid var(--trazo);border-radius:16px;padding:14px 16px;box-shadow:var(--sombra);min-width:0}
.anf-res .hora{font-size:20px;font-weight:800}
.anf-res .quien{display:flex;align-items:center;gap:10px;margin-top:8px}
.anf-res .quien .av{width:36px;height:36px;border-radius:50%;background:var(--tinte);color:var(--teal);display:inline-flex;align-items:center;justify-content:center;font-weight:800}
.anf-res .acc{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}.anf-res .acc .btn{padding:8px 12px;font-size:13px;flex:0 0 auto;min-width:0}
.anf-vacio{background:var(--gris);border-radius:16px;padding:26px;text-align:center;color:var(--tenue);font-weight:600}
.kpis{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:14px;margin-top:16px}
.kpi{background:var(--blanco);border:1px solid var(--trazo);border-radius:16px;padding:16px 18px;box-shadow:var(--sombra)}
.kpi small{display:block;color:var(--tenue);font-weight:600;font-size:12.5px}.kpi b{font-size:24px;display:block;margin-top:4px}
.cal-sem{overflow-x:auto;margin-top:12px;border:1px solid var(--trazo);border-radius:16px}
.cal-sem table{border-collapse:collapse;min-width:760px;width:100%;font-size:12.5px}
.cal-sem th{position:sticky;top:0;background:var(--blanco);padding:10px 6px;border-bottom:1px solid var(--trazo);font-weight:700;text-align:center}
.cal-sem th.hoy{color:var(--esmeralda)}
.cal-sem td{border-top:1px solid var(--trazo);border-left:1px solid var(--trazo);padding:4px;height:44px;vertical-align:top;min-width:96px}
.cal-sem td:first-child{border-left:0;font-weight:700;white-space:nowrap;background:var(--papel);width:64px;vertical-align:middle;text-align:center}
.cal-sem .oc{background:var(--tinte);border-radius:8px;padding:5px 7px;font-weight:700;color:var(--teal);line-height:1.2}
.cal-sem .oc small{display:block;font-weight:600;color:var(--tenue)}
.cal-sem .oc.ef{background:var(--warn-bg);color:var(--warn-fg)}.cal-sem .oc.ef small{color:#8a6d1f}
.cal-sem .bl{background:var(--gris);border-radius:8px;padding:5px 7px;font-weight:700;color:var(--tenue)}
.cal-sem td.pasado{background:#FAFBFA}
.cal-nav2{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-top:14px}
.cal-nav2 .btn{padding:8px 12px;font-size:13.5px}
.anf-cancha{display:flex;gap:14px;background:var(--blanco);border:1px solid var(--trazo);border-radius:16px;padding:12px;box-shadow:var(--sombra);min-width:0}
.anf-cancha .f{flex:none;width:110px;height:110px;border-radius:12px;overflow:hidden;background:var(--tinte);display:flex;align-items:center;justify-content:center;font-size:40px}
.anf-cancha .f img{width:100%;height:100%;object-fit:cover}
.anf-cancha .acciones .btn{flex:0 0 auto;min-width:0;padding:8px 12px;font-size:13px}.anf-local{background:var(--blanco);border:1px solid var(--trazo);border-radius:18px;padding:14px;box-shadow:var(--sombra);min-width:0}.anf-local .cab{display:flex;gap:14px;align-items:flex-start}.anf-local .cab .f{flex:none;width:84px;height:84px;border-radius:12px;overflow:hidden;background:var(--tinte);display:flex;align-items:center;justify-content:center;font-size:34px}.anf-local .cab .f img{width:100%;height:100%;object-fit:cover}.anf-local .cab .ico{font-size:18px}.anf-local .filas{margin-top:12px;border-top:1px solid var(--trazo)}.anf-fila{display:flex;gap:10px;padding:12px 0;border-bottom:1px solid var(--trazo)}.anf-fila .ico{flex:none;width:32px;height:32px;border-radius:50%;background:var(--tinte);display:flex;align-items:center;justify-content:center;font-size:16px}.anf-local .acciones .btn{flex:0 0 auto;min-width:0;padding:8px 12px;font-size:13px}
/* calendario interactivo del anfitrión */
.cal-act td[data-t]{cursor:pointer}.cal-act td.libre:hover{background:var(--tinte)}.cal-act td .li{opacity:0;font-size:11px;color:var(--teal);font-weight:800;text-align:center}
.cal-act td.libre:hover .li{opacity:1}.cal-act td.res:hover .oc,.cal-act td.bloq:hover .bl{filter:brightness(.95)}
.modal .quien .av{width:36px;height:36px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;background:var(--tinte);color:var(--teal);font-weight:800;flex:none}
.chk{display:flex;align-items:center;gap:10px;font-weight:700;font-size:14px;cursor:pointer}.chk input{width:18px;height:18px;padding:0;margin:0;accent-color:var(--esmeralda)}.chk small{font-weight:500;color:var(--tenue)}
.aviso.warn{background:var(--warn-bg);color:var(--warn-fg);border-radius:14px;padding:12px 16px;font-weight:600}
.toast{position:fixed;left:50%;bottom:28px;transform:translateX(-50%) translateY(20px);background:var(--noche);color:#fff;padding:12px 20px;border-radius:12px;font-weight:700;font-size:14.5px;z-index:90;box-shadow:0 8px 24px rgba(10,27,61,.3);opacity:0;transition:opacity .25s,transform .25s;max-width:calc(100vw - 32px)}
.toast.on{opacity:1;transform:translateX(-50%) translateY(0)}
/* tienda y academia (modo anfitrión) */
.prods{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:14px;margin-top:18px}
.prod{display:flex;gap:12px;background:var(--blanco);border:1px solid var(--trazo);border-radius:16px;padding:12px;box-shadow:var(--sombra);min-width:0}
.prod .pf{flex:none;width:96px;height:96px;border-radius:12px;overflow:hidden;background:var(--tinte);display:flex;align-items:center;justify-content:center;font-size:36px}
.prod .pf img{width:100%;height:100%;object-fit:cover}.prod .pb{flex:1;min-width:0}.prod .acciones .btn{flex:0 0 auto;min-width:0;padding:8px 12px;font-size:13px}
.foto-una{width:220px;height:220px;border-radius:16px;overflow:hidden;background:var(--tinte);display:flex;align-items:center;justify-content:center;margin-top:12px;border:1px solid var(--trazo)}
.foto-una img{width:100%;height:100%;object-fit:cover}.foto-una .ph{font-size:48px}
.logo-pick{width:96px;height:96px;border-radius:50%;overflow:hidden;background:var(--tinte);display:flex;align-items:center;justify-content:center;font-size:40px;border:1px solid var(--trazo);flex:none}
.logo-pick img{width:100%;height:100%;object-fit:cover}
.tabla{overflow-x:auto;border:1px solid var(--trazo);border-radius:14px}.tabla table{width:100%;border-collapse:collapse;font-size:14px}
.tabla th{text-align:left;font-size:12.5px;color:var(--tenue);padding:10px 12px;border-bottom:1px solid var(--trazo);white-space:nowrap}.tabla td{padding:10px 12px;border-bottom:1px solid var(--trazo);vertical-align:top}
.tabla tr:last-child td{border-bottom:0}
.planes{display:flex;flex-direction:column;gap:12px;margin-top:12px}.plan-card{border:1px solid var(--trazo);border-radius:14px;padding:14px 16px}
.plan-card label{margin-top:10px}.plan-card .mini{width:30px;height:30px;border-radius:50%;border:1px solid var(--trazo);background:#fff;cursor:pointer;font-family:inherit;font-weight:800}
/* Programas y tarifario (Mi academia): programa = tarjeta, tarifas = filas adentro */
.prog-card{border:1px solid var(--trazo);border-radius:14px;padding:14px 16px}.prog-card label{margin-top:10px}
.prog-head{display:flex;justify-content:space-between;align-items:center;gap:8px}.prog-head b{font-size:16px}
.prog-card .mini{width:30px;height:30px;border-radius:50%;border:1px solid var(--trazo);background:#fff;cursor:pointer;font-family:inherit;font-weight:800;flex:none}
.tarifas{display:flex;flex-direction:column;gap:10px;margin-top:6px}.tarifa{background:#F5F7FA;border:1px solid var(--trazo);border-radius:12px;padding:10px 12px 12px}
.tarifa-top{display:flex;justify-content:space-between;align-items:center;gap:8px}.tarifa .tnombre{font-weight:800;color:var(--noche)}.tarifa label{margin-top:8px}
.btn.chico{padding:9px 14px;font-size:13.5px}
.lst .badge.aca{background:var(--tinte);color:var(--teal)}
/* Ficha de academia: tarifario por programa + comprobante de matrícula */
.prog{border:1px solid var(--trazo);border-radius:14px;padding:12px 14px;margin-top:12px}.prog-h{display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;align-items:baseline;margin-bottom:6px}.prog-h b{font-size:16px}.prog-h .sub{margin:0;font-size:13px}
.tarifa-fila{display:flex;align-items:center;gap:12px;padding:10px 0;border-top:1px solid #f0f0f0}.tarifa-fila:first-of-type{border-top:0}.tarifa-fila>div:first-child{flex:1;min-width:0}.tarifa-fila .tp{text-align:right;white-space:nowrap}.tarifa-fila .tp b{font-size:16px}.tarifa-fila .tp small{display:block;color:var(--tenue);font-weight:600;font-size:12px}
.tarifa-fila.sel{background:var(--tinte);border-radius:12px;padding:10px 12px;margin:0 -12px}.tarifa-fila .btn.chico{padding:9px 14px;font-size:13.5px;white-space:nowrap}
@media(max-width:640px){.tarifa-fila{flex-wrap:wrap}.tarifa-fila .btn.chico{width:100%}}
.check-ok{width:64px;height:64px;border-radius:50%;background:var(--tinte);color:var(--teal);font-size:34px;font-weight:800;display:flex;align-items:center;justify-content:center;margin:0 auto 10px}
.btn.red-instagram{color:#C13584}.btn.red-facebook{color:#1877F2}.btn.red-youtube{color:#E62117}.btn svg{vertical-align:-3px}.lst .app svg{vertical-align:-3px}.lst .red-instagram{color:#C13584}.lst .red-facebook{color:#1877F2}.lst .red-tiktok{color:#111}.lst .red-youtube{color:#E62117}.pin-precio.aca{background:var(--tinte);color:var(--teal);border-color:var(--esmeralda)}.grupo-aca{margin-top:28px}
.frecs{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:10px;margin-top:6px}.frec{display:flex;align-items:center;gap:10px}.frec b{min-width:58px}.frec .inp-moneda{flex:1}
.sueltos{margin-top:14px}.suelto{display:flex;justify-content:space-between;align-items:center;gap:8px;border:1px dashed var(--trazo);border-radius:12px;padding:8px 12px;margin-top:6px}
.suelto .mini{width:30px;height:30px;border-radius:50%;border:1px solid var(--trazo);background:#fff;cursor:pointer;font-family:inherit;font-weight:800;flex:none}
/* editor de cancha (como el editor de anuncios de Airbnb) */
.edit-top{margin-top:22px}.volver-lnk{font-weight:700;color:var(--noche);text-decoration:none;font-size:14px}.volver-lnk:hover{text-decoration:underline}
.edit-grid{display:grid;grid-template-columns:240px minmax(0,1fr);gap:28px;align-items:start;margin-top:18px}
.edit-nav{position:sticky;top:96px;display:flex;flex-direction:column;gap:2px}
.edit-nav-it{display:block;padding:10px 14px;border-radius:12px;color:var(--noche);text-decoration:none;font-weight:600;font-size:14.5px}
.edit-nav-it:hover{background:var(--gris)}
.edit-form{display:flex;flex-direction:column;gap:18px;max-width:760px;min-width:0}
.edit-sec h2{font-size:20px;margin:0}.edit-sec .sub{margin-top:4px}.edit-sec .chips{margin-top:12px}
.edit-sec label{margin-top:16px}.req{font-weight:600;color:var(--tenue);font-size:12px;margin-left:6px}
.edit-fotos{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:12px;margin-top:14px}
.edit-fotos .foto{position:relative;aspect-ratio:1;border-radius:14px;overflow:hidden;background:var(--tinte);border:1px solid var(--trazo)}
.edit-fotos .foto img{width:100%;height:100%;object-fit:cover;display:block}
.edit-fotos .portada{position:absolute;left:8px;top:8px;background:#fff;color:var(--noche);font-weight:800;font-size:12px;padding:4px 8px;border-radius:999px;box-shadow:0 1px 4px rgba(0,0,0,.2)}
.edit-fotos .acc{position:absolute;right:8px;top:8px;display:flex;gap:6px}
.edit-fotos .mini{width:30px;height:30px;border-radius:50%;border:0;background:rgba(255,255,255,.95);color:var(--noche);font-weight:800;cursor:pointer;box-shadow:0 1px 4px rgba(0,0,0,.25);font-family:inherit}
.edit-fotos .mini:hover{background:#fff}
.inp-moneda{display:flex;align-items:center;border:1px solid var(--trazo);border-radius:var(--r-btn);overflow:hidden;max-width:260px}
.inp-moneda span{padding:0 14px;font-weight:800;color:var(--tenue);background:var(--gris);align-self:stretch;display:flex;align-items:center}
.inp-moneda input{border:0;border-radius:0}.inp-moneda:focus-within{outline:2px solid var(--esmeralda)}.inp-moneda input:focus{outline:none}
.servs{display:flex;flex-direction:column;gap:10px;margin-top:12px}
.serv{display:flex;align-items:center;gap:12px;flex-wrap:wrap}.serv .precio-serv{display:flex;align-items:center;gap:8px;margin:0;font-weight:800;color:var(--tenue)}
.serv .precio-serv input{width:120px;padding:9px 12px}
.barra-guardar{position:sticky;bottom:0;background:var(--blanco);border-top:1px solid var(--trazo);padding:12px 0;margin-top:26px;z-index:15}
.barra-guardar .wrap-xl{display:flex;align-items:center;justify-content:space-between;gap:16px}
.barra-guardar .btn{flex:none;padding:13px 26px}#msgGuardar.err{color:var(--bad-fg);font-weight:700}
@media(max-width:560px){#msgGuardar:not(.err){display:none}.barra-guardar .btn{width:100%}}
@media(max-width:900px){.edit-grid{grid-template-columns:1fr;gap:8px}.edit-nav{position:static;flex-direction:row;overflow-x:auto;gap:6px;padding-bottom:6px}.edit-nav-it{white-space:nowrap;border:1px solid var(--trazo);padding:8px 12px;border-radius:999px;font-size:13.5px}}
.mov{display:flex;justify-content:space-between;gap:12px;padding:10px 0;border-top:1px solid var(--trazo);font-size:14px}
.mov small{display:block;color:var(--tenue);font-weight:600}
@media(max-width:1400px){
  /* las 8 pestañas ya no caben junto al logo: pasan a su propia fila, centradas bajo el buscador (como las categorías de Airbnb) */
  .cab{grid-template-columns:1fr auto;grid-template-areas:"logo der" "busq busq" "tabs tabs";column-gap:8px;padding-top:4px;padding-bottom:0}
  .cab-tabs{border-top:1px solid var(--trazo);margin-top:8px}
  .cat{padding:12px 10px 10px}
}
@media(max-width:1060px){
  .cab-logo,.cab-der{height:56px}
  .cab-tabs{justify-content:flex-start;margin:8px -20px 0;padding:0 20px}
  .cab-busq{margin:2px 0 6px}
}
@media(max-width:900px){
  .cab-der a.host{display:none}
  .busq{height:56px}.busq .seg{padding:0 12px}.busq .seg input{text-overflow:ellipsis}
  .busq .lupa{width:44px;height:44px;padding:0;margin-right:6px}.busq .lupa span{display:none}
  .sug{top:64px;width:100%;border-radius:18px}
  .busq-mini span.tenue{display:none}
  /* páginas interiores en móvil (como airbnb.com en el celular): logo + avatar arriba y la pastilla a TODO el ancho debajo;
     al hacer scroll en la portada queda solo la pastilla. Antes las tres cosas iban en una fila y el logo se montaba sobre la pastilla. */
  .cab.simple{grid-template-columns:1fr auto;grid-template-areas:"logo der" "mini mini";padding-bottom:10px}
  .cab.chica{grid-template-columns:1fr;grid-template-areas:"mini";padding-top:8px;padding-bottom:8px}
  .cab.chica .cab-logo,.cab.chica .cab-der{display:none}
  .cab-mini{width:100%}.cab-mini .busq-mini{width:100%;height:54px;padding:0 16px;gap:12px}
  .cab-mini .busq-mini span,.cab-mini .busq-mini>i:last-child{display:none}
  .cab-mini .busq-mini .lupa-mov{display:inline-flex;width:auto;height:auto;background:transparent;color:var(--noche);margin:0}.cab-mini .busq-mini .lupa-mov svg{width:18px;height:18px}
  .cab-mini .busq-mini .mov{display:flex;flex-direction:column;min-width:0;line-height:1.2}
  .cab-mini .busq-mini .mov b{font-size:14px;font-weight:700}.cab-mini .busq-mini .mov small{font-size:12px;color:var(--tenue);font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .cab-logo .wm{white-space:nowrap}
}
@media(max-width:560px){.cab-logo .wm{font-size:20px!important}.cab-der .av{width:34px;height:34px}}
@media(max-width:560px){.busq .seg{padding:0 9px}.busq .seg small{font-size:11px}.busq .seg input{font-size:13px}.busq .seg.donde{flex:1.5}.busq .seg.hora{flex:.8}.cab-tabs{margin:0 -16px;padding:0 16px}.cat{padding:12px 8px 10px}}
/* filtros del explorador (botón + chips) */
.filtros{flex:none;display:inline-flex;align-items:center;gap:8px;border:1px solid var(--trazo);border-radius:14px;padding:10px 14px;font-weight:700;font-size:13.5px;background:var(--blanco);cursor:pointer;color:var(--noche);font-family:inherit}
.filtros:hover{border-color:var(--noche)}.filtros.on{border-color:var(--noche);box-shadow:inset 0 0 0 1px var(--noche)}
.barra-filtros{display:flex;align-items:center;gap:10px;padding:12px 0 4px;min-width:0}
.barra-filtros .qchips:before{content:"";width:1px;height:28px;background:var(--trazo);flex:none;margin-right:2px}
.barra-filtros .qchips{display:flex;gap:8px;overflow-x:auto;scrollbar-width:none;min-width:0;padding:4px 0}
.barra-filtros .qchips::-webkit-scrollbar{display:none}
.barra-filtros .chip{font-size:13.5px;padding:10px 14px;border-radius:14px}
.filtros .n{display:inline-flex;align-items:center;justify-content:center;min-width:18px;height:18px;border-radius:999px;background:var(--noche);color:#fff;font-size:11px;margin-left:6px;padding:0 5px}
body.sin-scroll{overflow:hidden}
.modal{display:none;position:fixed;inset:0;background:rgba(10,27,61,.5);z-index:60;align-items:center;justify-content:center;padding:24px 16px}
.modal.open{display:flex}
.modal-caja{background:var(--blanco);border-radius:24px;width:100%;max-width:568px;max-height:calc(100vh - 48px);display:flex;flex-direction:column;box-shadow:0 12px 40px rgba(10,27,61,.3);overflow:hidden}
.modal-cab{position:relative;display:flex;align-items:center;justify-content:center;height:64px;border-bottom:1px solid var(--trazo);flex:none}
.modal-cab h3{font-size:16px}
.modal-cab .cerrar{position:absolute;left:16px;top:16px;width:32px;height:32px;border-radius:50%;border:0;background:transparent;font-size:15px;cursor:pointer;color:var(--noche);font-family:inherit}
.modal-cab .cerrar:hover{background:var(--gris)}
.modal-cuerpo{overflow-y:auto;padding:8px 24px 16px;flex:1;min-height:0}
.modal-cuerpo section{padding:22px 0;border-bottom:1px solid var(--trazo)}.modal-cuerpo section:last-child{border-bottom:0}
.modal-cuerpo h4{margin:0 0 14px;font-size:18px;font-weight:600}
.modal-cuerpo .sub{margin:-8px 0 14px;font-size:14px}
.modal-cuerpo .chips{display:flex;flex-wrap:wrap;gap:8px}.modal-cuerpo .chip small{color:var(--tenue);font-weight:600}
.modal-cuerpo .chip.sel{background:var(--noche);color:#fff;border-color:var(--noche)}.modal-cuerpo .chip.sel small{color:#cfd6d2}
.tiles{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}
@media(max-width:560px){.tiles{grid-template-columns:repeat(2,minmax(0,1fr))}}
.tile{display:flex;flex-direction:column;align-items:center;gap:10px;padding:16px 8px 14px;border:1px solid var(--trazo);border-radius:14px;background:var(--blanco);cursor:pointer;font-family:inherit;font-size:13.5px;font-weight:500;color:var(--noche);text-align:center;transition:border-color .12s,box-shadow .12s}
.tile .ico{font-size:40px;line-height:1}
.tile:hover{border-color:var(--noche)}.tile.sel{border-color:var(--noche);box-shadow:inset 0 0 0 1px var(--noche);background:var(--gris)}
.segm{display:flex;border:1px solid var(--trazo);border-radius:14px;padding:4px;background:var(--blanco)}
.segm button{flex:1;border:0;background:transparent;padding:12px 8px;border-radius:12px;font-family:inherit;font-weight:500;font-size:14px;cursor:pointer;color:var(--noche);position:relative}
.segm button+button:before{content:"";position:absolute;left:0;top:10px;bottom:10px;width:1px;background:var(--trazo)}
.segm button:hover{background:var(--gris)}.segm button.on{background:var(--gris);box-shadow:inset 0 0 0 2px var(--noche);font-weight:600}.segm button.on:before,.segm button.on+button:before{display:none}
.histo{display:flex;align-items:flex-end;gap:2px;height:64px;padding:0 8px;margin-bottom:-6px}
.histo i{flex:1;background:#D9DFDC;border-radius:3px 3px 0 0;min-width:0}.histo i.on{background:var(--esmeralda)}
.rango{position:relative;height:28px;margin:0 8px}
.rango:before{content:"";position:absolute;left:0;right:0;top:13px;height:2px;background:var(--trazo)}
.rango input[type=range]{position:absolute;left:0;right:0;top:0;width:100%;margin:0;height:28px;background:transparent;-webkit-appearance:none;appearance:none;pointer-events:none;outline:none}
.rango input[type=range]::-webkit-slider-runnable-track{height:2px;background:transparent}
.rango input[type=range]::-moz-range-track{height:2px;background:transparent}
.rango input[type=range]::-webkit-slider-thumb{-webkit-appearance:none;appearance:none;pointer-events:auto;width:30px;height:30px;border-radius:50%;background:#fff;border:1px solid var(--trazo);box-shadow:0 2px 6px rgba(10,27,61,.2);cursor:grab;margin-top:-14px}
.rango input[type=range]::-moz-range-thumb{pointer-events:auto;width:30px;height:30px;border-radius:50%;background:#fff;border:1px solid var(--trazo);box-shadow:0 2px 6px rgba(10,27,61,.2);cursor:grab}
.topes{display:flex;gap:12px;margin-top:18px}
.topes label{flex:1;font-size:12.5px;color:var(--tenue);font-weight:600}
.tope{display:flex;align-items:center;gap:6px;border:1px solid var(--trazo);border-radius:999px;padding:10px 16px;margin-top:6px;color:var(--noche);font-weight:600;font-size:14px}
.tope input{border:0;padding:0;width:100%;min-width:0;font-family:inherit;font-weight:600;font-size:14px;color:var(--noche);outline:none;background:transparent;box-shadow:none;height:auto;-moz-appearance:textfield}
.tope input::-webkit-outer-spin-button,.tope input::-webkit-inner-spin-button{-webkit-appearance:none;margin:0}
.modal-pie{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:14px 24px;border-top:1px solid var(--trazo);flex:none}
.modal-pie .limpiar{border:0;background:transparent;font-family:inherit;font-weight:600;font-size:15px;color:var(--noche);text-decoration:underline;cursor:pointer;padding:8px 0}
.modal-pie .btn{padding:14px 22px;font-size:15px}
@media(max-width:560px){.modal{padding:0}.modal-caja{max-width:none;max-height:100vh;border-radius:0;height:100%}}
.expl{display:grid;grid-template-columns:minmax(0,1fr);gap:0;align-items:start;padding-top:8px}
.expl>*{min-width:0}
.expl.con-mapa{grid-template-columns:minmax(0,1fr) minmax(0,42%);gap:24px}
.expl .mapa-lado{display:none}
.expl.con-mapa .mapa-lado{display:block;position:sticky;top:98px}
.expl.con-mapa .mapa-lado .mapa{height:calc(100vh - 122px);min-height:420px;border-radius:14px;box-shadow:none;border:1px solid var(--trazo)}
@media(max-width:900px){
  .expl.con-mapa{grid-template-columns:minmax(0,1fr)}
  .expl.con-mapa .lista{display:none}
  .expl.con-mapa .mapa-lado{position:static}
  .expl.con-mapa .mapa-lado .mapa{height:calc(100vh - 200px);min-height:360px;border-radius:14px}
}
.tit{display:flex;align-items:baseline;justify-content:space-between;gap:12px;margin:22px 0 10px}
.tit h2{font-size:22px;display:flex;align-items:center;gap:8px;flex-wrap:wrap}.tit .cerca{color:var(--tenue);font-weight:600;font-size:14px}
@media(max-width:560px){.tit h2{font-size:19px}.tit .cerca{display:none}}
.lst-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:28px 20px}
@media(max-width:760px){.lst-grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:20px 14px}}
@media(max-width:440px){.lst-grid{grid-template-columns:1fr}}
.expl.con-mapa .lst-grid{grid-template-columns:repeat(auto-fill,minmax(230px,1fr))}
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
.lst .corazon:hover svg{transform:scale(1.1)}.lst .corazon.on svg{fill:var(--naranja);stroke:var(--naranja)}
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
    """Logo oficial: pin verde con la pelota (`/static/brand/logo_pin.png`) +
    "Pichangol" en azul noche, peso 800, SIN cursiva (pedido del director)."""
    return (f"<a class='wm' href='{href}' style='font-size:{tam}px' aria-label='Pichangol'>"
            "<img src='/static/brand/logo_pin.png' alt=''><span>Pichangol</span></a>")


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


# Logos de redes sociales (inline, sin dependencias). Los usan las tarjetas y
# fichas de academia (`web/router.py`, `web/academia.py`) y el pie (redes
# OFICIALES de Pichangol configuradas en la torre → `empresa.redes()`).
RED_SVG = {
    "instagram": "<svg viewBox='0 0 24 24' width='15' height='15' fill='none' stroke='currentColor' stroke-width='2'><rect x='3' y='3' width='18' height='18' rx='5'/><circle cx='12' cy='12' r='4'/><circle cx='17.5' cy='6.5' r='1' fill='currentColor'/></svg>",
    "facebook": "<svg viewBox='0 0 24 24' width='15' height='15' fill='currentColor'><path d='M13.5 22v-8h2.7l.4-3.2h-3.1V8.8c0-.9.3-1.6 1.6-1.6h1.7V4.4c-.3 0-1.3-.1-2.5-.1-2.5 0-4.1 1.5-4.1 4.2v2.3H7.4V14h2.8v8h3.3z'/></svg>",
    "tiktok": "<svg viewBox='0 0 24 24' width='15' height='15' fill='currentColor'><path d='M16.5 2h-3v13.2a2.8 2.8 0 1 1-2.8-2.8c.3 0 .6 0 .8.1V9.4a5.9 5.9 0 1 0 5 5.8V8.6a7 7 0 0 0 4 1.3V6.8a4 4 0 0 1-4-4.8z'/></svg>",
    "youtube": "<svg viewBox='0 0 24 24' width='15' height='15' fill='currentColor'><path d='M22.5 7.2a2.8 2.8 0 0 0-2-2C18.8 4.8 12 4.8 12 4.8s-6.8 0-8.5.4a2.8 2.8 0 0 0-2 2C1 8.9 1 12 1 12s0 3.1.5 4.8a2.8 2.8 0 0 0 2 2c1.7.4 8.5.4 8.5.4s6.8 0 8.5-.4a2.8 2.8 0 0 0 2-2c.5-1.7.5-4.8.5-4.8s0-3.1-.5-4.8zM9.8 15.1V8.9l5.7 3.1-5.7 3.1z'/></svg>",
    "web": "<svg viewBox='0 0 24 24' width='15' height='15' fill='none' stroke='currentColor' stroke-width='2'><circle cx='12' cy='12' r='9'/><path d='M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18'/></svg>",
}

# Distintivo "Libro de Reclamaciones" (libro rojo, como el que INDECOPI pide
# exhibir de forma visible): enlaza a la hoja de reclamación en página propia.
LIBRO_SVG = ("<svg viewBox='0 0 24 24' width='22' height='22' aria-hidden='true'><path fill='#C8102E' d='M4 3h13a2 2 0 0 1 2 2v14.5a1.5 1.5 0 0 1-1.5 1.5H6a2 2 0 0 1-2-2V3z'/>"
             "<path fill='#fff' d='M6 5h11v12H6z' opacity='.15'/><path fill='#fff' d='M8 7h7v1.4H8zM8 10h7v1.4H8zM8 13h5v1.4H8z'/></svg>")


def redes_pie(em: dict) -> str:
    """Íconos de las redes OFICIALES (solo las configuradas en la torre)."""
    rs = em.get("redes") or []
    if not rs:
        return ""
    return ("<div class='pie-redes'><span>Síguenos</span>"
            + "".join(f"<a class='red-{r['red']}' href='{r['url']}' target='_blank' rel='noopener' aria-label='{r['nombre']} de Pichangol' title='{r['nombre']}'>{RED_SVG[r['red']]}</a>"
                      for r in rs) + "</div>")


def footer() -> str:
    """Pie de página con columnas (estilo Airbnb) + datos del comercio que
    exigen Culqi/INDECOPI (razón social, RUC, contacto, Libro de Reclamaciones,
    políticas de devolución y términos, redes oficiales) en TODAS las páginas."""
    import empresa
    em = empresa.datos()
    return (
        "<footer class='pie'><div class='wrap-xl'><div class='pie-cols'>"
        f"<div>{wordmark(20)}<div>Reserva, juega, repite.</div>"
        "<div style='margin-top:10px;font-size:12.5px'>Fútbol · Tenis · Pádel · Pickleball<br>Perú · Ecuador · Bolivia</div>"
        f"{redes_pie(em)}</div>"
        "<div><h4>Reservar</h4><a href=\"/canchas\">Todas las canchas</a><a href='/canchas?deporte=futbol'>Canchas de fútbol</a>"
        "<a href='/canchas?deporte=tenis'>Canchas de tenis</a><a href='/canchas?deporte=padel'>Canchas de pádel</a>"
        "<a href='/canchas?deporte=academias'>Academias</a><a href='/#servicios'>Servicios y precios</a></div>"
        "<div><h4>Soporte</h4><a href='/#contacto'>Contacto</a><a href='/#como'>Cómo funciona</a>"
        "<a href='/#pagos'>Pagos y seguridad</a><a href='/legal/devoluciones'>Cambios, cancelaciones y devoluciones</a>"
        f"<a class='libro' href='/libro-de-reclamaciones'>{LIBRO_SVG}<span>Libro de Reclamaciones</span></a></div>"
        "<div><h4>Pichangol</h4><a href='https://play.google.com/store/apps/details?id=pe.ebim.pichangol' rel='noopener'>Descarga la app</a>"
        "<a href='/anfitrion/nueva'>Pon tu cancha en Pichangol</a>"
        "<a href=\"/legal/terminos\">Términos y condiciones</a><a href=\"/legal/privacidad\">Política de privacidad</a>"
        "<a href=\"/legal/eliminar-cuenta\">Eliminar mi cuenta</a></div>"
        f"</div><div class='pie-bajo'><div>© {em['anio']} Pichangol · {em['razon_social']} · {em['doc_etiqueta']} {em['ruc']} · {em['ciudad']} · "
        f"<a href='mailto:{em['correo']}'>{em['correo']}</a></div>"
        "<div><a href='/legal/terminos'>Términos</a><a href='/legal/privacidad'>Privacidad</a><a href='/legal/devoluciones'>Devoluciones</a>"
        "<a href='/libro-de-reclamaciones'>Libro de Reclamaciones</a></div>"
        "</div></div></footer>")


LUPA_SVG = ("<svg viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='3' stroke-linecap='round'>"
            "<circle cx='11' cy='11' r='7'/><path d='M20 20l-3.5-3.5'/></svg>")
_HAMB_SVG = ("<svg viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2.4' stroke-linecap='round'>"
             "<path d='M4 7h16M4 12h16M4 17h16'/></svg>")
_USER_SVG = ("<svg viewBox='0 0 24 24' fill='currentColor' style='width:22px;height:22px'>"
             "<path d='M12 12a5 5 0 1 0 0-10 5 5 0 0 0 0 10zm0 2c-4.4 0-8 2.2-8 5v1h16v-1c0-2.8-3.6-5-8-5z'/></svg>")


def _avatar(ses: dict | None) -> str:
    if ses and ses.get("foto"):
        return f"<img src='{e(ses.get('foto'))}' alt=''>"
    if ses:
        return f"<span class='ini'>{e((ses.get('nombre') or ses.get('email') or '?')[:1].upper())}</span>"
    return _USER_SVG


def chip_sesion(ses: dict | None, volver: str = "/") -> str:
    """Avatar + nombre si hay sesión de Google; si no, "Iniciar sesión" (solo
    cuando el login web está configurado). Se usa en las páginas que no
    llevan la cabecera Airbnb (p. ej. /entrar)."""
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


PLAY_URL = "https://play.google.com/store/apps/details?id=pe.ebim.pichangol"


def menu_cuenta(ses: dict | None, volver: str = "/", modo: str = "") -> str:
    """Lado derecho de la cabecera, como Airbnb: "Modo anfitrión" · avatar (la
    foto de Google si hay sesión) · botón ☰ con el menú desplegable."""
    from web import sesion as _s
    from urllib.parse import quote as _q
    entrar = f"/entrar?volver={_q(volver, safe='')}"
    if ses:
        nombre = ses.get("nombre") or ses.get("email") or ""
        cuenta = (f"<div class='yo'>{_avatar(ses)}<div><b>{e(nombre)}</b><small>{e(ses.get('email'))}</small></div></div>"
                  "<hr><a class='b' href='/mis-reservas'>📅 Mis reservas</a>"
                  "<button type='button' onclick='window.pcgSalir&&pcgSalir()'>Cerrar sesión</button>")
        avatar = f"<a class='redondo' href='#' onclick='return false' title='{e(ses.get('email'))}' aria-label='Tu cuenta'>{_avatar(ses)}</a>"
    else:
        if _s.activo():
            cuenta = f"<a class='b' href='{entrar}'>Iniciar sesión o registrarse</a>"
        else:
            cuenta = f"<a class='b' href='{PLAY_URL}' rel='noopener'>Iniciar sesión en la app</a>"
        avatar = f"<a class='redondo' href='{entrar if _s.activo() else PLAY_URL}' aria-label='Iniciar sesión'>{_USER_SVG}</a>"
    # "Modo anfitrión" abre el panel del dueño EN LA WEB (como airbnb.com/hosting);
    # dentro del panel el enlace se vuelve "Cambiar a modo jugador".
    host = ("<a class='host' href='/'>Cambiar a modo jugador</a>" if modo == "anfitrion"
            else f"<a class='host' href='{'/anfitrion' if (ses or _s.activo()) else PLAY_URL}'>Modo anfitrión</a>")
    return (
        "<div class='cab-der'>"
        f"{host}"
        f"{avatar}"
        "<div class='menu'><button type='button' class='redondo' id='btnMenu' aria-label='Menú' aria-expanded='false'>"
        f"{_HAMB_SVG}</button>"
        f"<div class='menu-panel' id='menuPanel' role='menu'>{cuenta}<hr>"
        "<a href='/#como'>Cómo funciona</a><a href='/#contacto'>Centro de ayuda</a><hr>"
        + ("<a class='b' href='/'>Cambiar a modo jugador</a>" if modo == "anfitrion" else "<a class='b' href='/anfitrion'>Modo anfitrión</a>")
        + "<a href='/anfitrion/nueva'>Pon tu cancha en Pichangol</a>"
        f"<a href='{PLAY_URL}' rel='noopener'>Descarga la app</a><hr>"
        "<a href='/legal/terminos'>Términos y condiciones</a><a href='/legal/devoluciones'>Cambios y devoluciones</a>"
        "<a href='/libro-de-reclamaciones'>📕 Libro de Reclamaciones</a>"
        "</div></div></div>")


def busq_mini(href: str = "/canchas", id_: str = "") -> str:
    """Pastilla compacta de las páginas interiores (Airbnb al hacer scroll)."""
    # En móvil (≤900 px) se muestra como la de airbnb.com en el celular: lupa a
    # la izquierda + dos líneas ("¿Dónde juegas?" / "Cualquier zona · …").
    return (f"<a class='busq-mini' href='{href}'{(' id=' + chr(39) + id_ + chr(39)) if id_ else ''}><i class='lupa-mov'>{LUPA_SVG}</i>"
            "<div class='mov'><b>¿Dónde juegas?</b><small>Cualquier zona · Cualquier deporte · Cuándo quieras</small></div>"
            f"<span>Cualquier zona</span><span>Cualquier deporte</span><span class='tenue'>Cuándo quieras</span><i>{LUPA_SVG}</i></a>")


def cabecera(*, tabs: str = "", busq: str = "", ses: dict | None = None, volver: str = "/", modo: str = "") -> str:
    """Cabecera tipo airbnb.com: logo a la izquierda, pestañas con ícono al
    centro, "Modo dueño" + avatar + ☰ a la derecha y, debajo, el buscador
    grande centrado. Sin [busq] (páginas interiores) queda la fila simple."""
    clase = "" if busq else (" anfitrion" if modo == "anfitrion" else " simple")
    return ("<header class='nav abnb'>"
            f"<div class='wrap-xl cab{clase}'>"
            f"<div class='cab-logo'>{wordmark(24, '/anfitrion' if modo == 'anfitrion' else '/')}</div>"
            + (f"<nav class='cab-tabs' aria-label='Secciones'>{tabs}</nav>" if tabs else "")
            + ("" if modo == "anfitrion" else f"<div class='cab-mini'>{busq_mini('#', 'busqMini') if busq else busq_mini('/canchas')}</div>")
            + f"{menu_cuenta(ses, volver, modo)}"
            + (f"<div class='cab-busq'>{busq}</div>" if busq else "")
            + f"</div></header><script>{JS_NAV}</script>")


# JS de la cabecera: menú ☰ (abre/cierra, se cierra al hacer clic fuera o con
# Esc), desplegable del buscador y cerrar sesión.
JS_NAV = r"""
(function(){
  var b = document.getElementById('btnMenu'), p = document.getElementById('menuPanel');
  if(b && p){
    b.addEventListener('click', function(ev){ ev.stopPropagation(); var on = !p.classList.contains('open'); p.classList.toggle('open', on); b.setAttribute('aria-expanded', on ? 'true' : 'false'); });
    document.addEventListener('click', function(ev){ if(!p.contains(ev.target)){ p.classList.remove('open'); b.setAttribute('aria-expanded', 'false'); } });
    document.addEventListener('keydown', function(ev){ if(ev.key === 'Escape'){ p.classList.remove('open'); document.querySelectorAll('.sug.open').forEach(function(s){ s.classList.remove('open'); }); } });
  }
  // Al hacer scroll la cabecera se compacta (pastilla chica al centro); al tocarla vuelve el buscador grande.
  var cab = document.querySelector('.cab:not(.simple)'), mini = document.getElementById('busqMini');
  if(cab && mini){
    var compactar = function(){ cab.classList.toggle('chica', window.innerWidth > 1060 && window.scrollY > 90); };
    window.addEventListener('scroll', compactar, {passive: true}); window.addEventListener('resize', compactar); compactar();
    mini.addEventListener('click', function(ev){ ev.preventDefault(); window.scrollTo({top: 0, behavior: 'smooth'});
      setTimeout(function(){ cab.classList.remove('chica'); var q = document.getElementById('sQ'); if(q) q.focus(); }, 350); });
  }
  window.pcgSalir = function(){ fetch('/web/salir', {method: 'POST'}).then(function(){ location.reload(); }); };
})();
"""


def nav_simple(ses: dict | None = None, volver: str = "/canchas") -> str:
    return cabecera(ses=ses, volver=volver)


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
        "<link href='https://fonts.googleapis.com/css2?family=DM+Sans:opsz,wght@9..40,500;9..40,600;9..40,700;9..40,800&display=swap' rel='stylesheet'>"
        f"<style>{CSS}</style>{extra_head}"
        + (f"<script type='application/ld+json'>{jsonld}</script>" if jsonld else "")
        + f"</head><body{' class=con-barra' if con_barra else ''}>"
        f"{nav or nav_simple(sesion)}"
        f"<main class='{'wrap-xl' if ancho else 'wrap'}'>{cuerpo}</main>"
        f"{footer()}"
        "</body></html>")
    return HTMLResponse(page, headers={"Cache-Control": "no-store"})
