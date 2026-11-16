"""CSS de las vistas del modo anfitrión · Mi academia, Plan Academia, operación de academia, Soy boleador, Verificador — anfitrion_academia*, academia_plan_web, anfitrion_boleadores, anfitrion_verificador.

Va después del kit (`web/vista_anfitrion.py`). Solo tokens (`--azul`, `--anf-*`).

Además de la hoja, aquí vive `svg()`: los íconos de línea de `web/iconos.py`
más unos pocos que solo usan estas vistas (regalo, candado, cámara, lápiz,
documento, check), con el mismo trazo.
"""

from __future__ import annotations

# Íconos de línea propios de estas vistas (mismo estilo que `web/iconos.py`).
_EXTRA = {
    "regalo": "<rect x='3.5' y='8.5' width='17' height='4' rx='1'/><path d='M5 12.5v7.5h14v-7.5M12 8.5v11.5'/>"
              "<path d='M12 8.5c-1.6-3.6-5.6-4-5.6-1.6 0 1.6 2.6 1.6 5.6 1.6zM12 8.5c1.6-3.6 5.6-4 5.6-1.6 0 1.6-2.6 1.6-5.6 1.6z'/>",
    "candado": "<rect x='5' y='10.5' width='14' height='10' rx='2.2'/><path d='M8.2 10.5V7.8a3.8 3.8 0 0 1 7.6 0v2.7'/><path d='M12 14.6v2.4'/>",
    "camara": "<path d='M4 8.2h3.2L9 5.6h6l1.8 2.6H20a1 1 0 0 1 1 1V18a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V9.2a1 1 0 0 1 1-1z'/><circle cx='12' cy='13.2' r='3.4'/>",
    "lapiz": "<path d='M4 20l1-4.2L15.6 5.2a2 2 0 0 1 2.8 0l.4.4a2 2 0 0 1 0 2.8L8.2 19 4 20z'/><path d='M13.8 7l3.2 3.2'/>",
    "documento": "<rect x='3' y='5.5' width='18' height='13' rx='2'/><circle cx='8.5' cy='11' r='2'/><path d='M5.8 15.6c.5-1.4 1.5-2.1 2.7-2.1s2.2.7 2.7 2.1M14 10h4.5M14 13.5h3'/>",
    "check": "<path d='M5 12.5l4.4 4.4L19 7.4'/>",
    "escudo_ok": "<path d='M12 3l7.5 3v5.6c0 4.6-3.2 8.2-7.5 9.4-4.3-1.2-7.5-4.8-7.5-9.4V6L12 3z'/><path d='M8.6 12.2l2.4 2.4 4.4-4.6'/>",
    "pagina": "<rect x='4' y='3.5' width='16' height='17' rx='2'/><path d='M4 8h16M8 12h8M8 15.5h5'/>",
}


def svg(nombre: str, tam: int = 18, grueso: float = 2.2) -> str:
    """Ícono de línea (`iconos.py` o uno de `_EXTRA`) como <svg> en línea."""
    if nombre in _EXTRA:
        return (f"<svg class='ic-l' viewBox='0 0 24 24' width='{tam}' height='{tam}' fill='none' stroke='currentColor' "
                f"stroke-width='{grueso}' stroke-linecap='round' stroke-linejoin='round' aria-hidden='true'>{_EXTRA[nombre]}</svg>")
    from web import iconos
    return iconos.svg(nombre, tam, grueso=grueso)


def cuadro(nombre: str, color: str = "var(--azul)", tam: int = 18, clase: str = "") -> str:
    """Ícono blanco en cuadrado de color (como `vista_anfitrion.icono`, con los extra)."""
    return f"<span class='va-ic {clase}' style='background:{color}'>{svg(nombre, tam)}</span>"


def suave(nombre: str, tam: int = 18) -> str:
    """Ícono azul sobre cuadrado celeste (tarjetas de "Qué incluye", pasos)."""
    return f"<span class='va-ic suave'>{svg(nombre, tam)}</span>"


CSS = r"""
/* ═════════ Academia · Plan · Boleador · Verificador (rediseño 16-nov-2026) ═════════ */
.vac-barra{height:8px;border-radius:999px;background:var(--anf-linea);overflow:hidden}
.vac-barra i{display:block;height:100%;border-radius:999px;background:var(--azul)}
.vac-barra.warn{background:var(--warn-bg)}
.vac-banner .vac-barra.warn{background:rgba(255,255,255,.75)}.vac-barra.warn i{background:var(--warn-fg)}
.vac-barra.bad i{background:var(--anf-rojo)}
/* Banner del Plan Academia (Mi academia) */
.vac-banner{display:flex;align-items:center;gap:14px 18px;flex-wrap:wrap;border-radius:14px;padding:14px 16px;margin-bottom:16px;border:1px solid var(--anf-borde);background:#fff}
.vac-banner.warn{background:var(--warn-bg);border-color:var(--warn-bg)}
.vac-banner.bad{background:var(--bad-bg);border-color:var(--bad-bg)}
.vac-banner.ok{background:var(--ok-bg);border-color:var(--ok-bg)}
.vac-banner .va-ic{background:#fff;color:var(--warn-fg)}
.vac-banner.bad .va-ic{color:var(--anf-rojo)}.vac-banner.ok .va-ic{color:var(--ok-fg)}
.vac-banner-t{flex:1 1 260px;min-width:0}
.vac-banner-t b{display:block;font-size:15px;color:var(--anf-texto);overflow-wrap:anywhere}
.vac-banner.warn .vac-banner-t b{color:var(--warn-fg)}
.vac-banner-t small{display:block;font-size:13px;color:var(--anf-texto);margin-top:2px;overflow-wrap:anywhere}
.vac-banner-bar{flex:0 1 240px;min-width:160px;text-align:center}
.vac-banner-bar small{display:block;font-size:12px;font-weight:700;color:var(--warn-fg);margin-top:6px}
.vac-banner .btn{flex:none}
/* Tarjeta de cada academia */
.vac-card{padding:22px}
.vac-card-top{display:grid;grid-template-columns:120px minmax(0,1fr) auto;gap:20px;align-items:start}
.vac-logo{width:120px;height:120px;border-radius:14px;background:var(--azul-tinte);color:var(--azul);display:flex;align-items:center;justify-content:center;overflow:hidden}
.vac-logo img{width:100%;height:100%;object-fit:cover;display:block}
.vac-card-t{min-width:0}
.vac-card-t h2{font-size:22px;line-height:1.2;overflow-wrap:anywhere}
.vac-pills{display:flex;gap:8px;flex-wrap:wrap;margin:8px 0 10px}
.vac-lugar{display:flex;align-items:center;gap:6px;font-size:14px;color:var(--anf-tenue);overflow-wrap:anywhere}
.vac-lugar svg{flex:none}
.vac-stats{display:flex;gap:16px 44px;flex-wrap:wrap;margin-top:12px}
.vac-stats small{display:block;font-size:12px;font-weight:700;letter-spacing:.04em;text-transform:uppercase;color:var(--anf-tenue)}
.vac-stats b{display:block;font-size:19px;color:var(--anf-texto);margin-top:2px;white-space:nowrap}
.vac-card-acc{display:flex;gap:10px;flex-wrap:wrap;justify-content:flex-end}
.vac-gest{border-top:1px solid var(--anf-linea);margin-top:20px;padding-top:18px}
.vac-gest>small{display:block;font-size:12px;font-weight:700;letter-spacing:.05em;text-transform:uppercase;color:var(--anf-tenue);margin-bottom:12px}
.vac-tiles{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(180px,100%),1fr));gap:12px}
.vac-tile{display:flex;flex-direction:column;gap:4px;border:1px solid var(--anf-borde);border-radius:14px;padding:16px;text-decoration:none;color:var(--anf-texto);min-height:120px;min-width:0;background:#fff;transition:border-color .15s,box-shadow .15s}
.vac-tile:hover{border-color:var(--azul);box-shadow:0 2px 10px rgba(48,86,237,.10)}
.vac-tile:focus-visible{box-shadow:var(--foco);outline:none}
.vac-tile-top{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:14px}
.vac-tile-top .chev{color:var(--anf-tenue);font-size:22px;line-height:1}
.vac-tile b{font-size:15px}
.vac-tile small{font-size:12.5px;color:var(--anf-tenue);overflow-wrap:anywhere}
.vac-tile small.bad{color:var(--anf-rojo);font-weight:700}
.vac-tile small.ok{color:var(--ok-fg);font-weight:700}
.vac-tile.lock .va-ic{background:var(--anf-tenue)!important}
.vac-tile.lock small{color:var(--anf-tenue)}
@media(max-width:760px){
  .vac-card{padding:16px}
  .vac-card-top{grid-template-columns:76px minmax(0,1fr);gap:14px}
  .vac-logo{width:76px;height:76px}
  .vac-card-acc{grid-column:1/-1;justify-content:stretch}.vac-card-acc .btn{flex:1}
  .vac-card-t h2{font-size:19px}
  .vac-stats{gap:10px 22px}.vac-stats b{font-size:17px}
  .vac-tiles{grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}
  .vac-tile{min-height:108px;padding:14px}
  .vac-banner-bar{flex:1 1 100%}.vac-banner .btn{flex:1 1 100%}
}
/* Editor de academia: la barra de guardar dentro de la vista */
.vac-editor .barra-guardar{border:1px solid var(--anf-borde);border-radius:14px 14px 0 0;padding:12px 16px}
.vac-editor .barra-guardar .wrap-xl{padding:0;max-width:none}
/* Plan Academia */
.vac-plan{display:grid;grid-template-columns:minmax(0,440px) minmax(0,1fr);gap:24px;align-items:start}
.vac-plan-card{background:#fff;border:1px solid var(--anf-borde);border-radius:18px;overflow:hidden;box-shadow:0 6px 24px rgba(20,33,90,.08)}
.vac-plan-top{background:linear-gradient(135deg,var(--azul-osc),var(--azul));color:#fff;padding:24px}
.vac-plan-pill{display:inline-flex;align-items:center;gap:6px;background:rgba(255,255,255,.18);border-radius:999px;padding:6px 12px;font-size:13px;font-weight:700}
.vac-plan-pill.bad{background:var(--anf-rojo)}
.vac-plan-top h2{color:#fff;font-size:22px;margin:16px 0 2px}
.vac-plan-top .acad{font-size:14px;opacity:.88;overflow-wrap:anywhere}
.vac-plan-precio{display:flex;align-items:baseline;gap:14px;margin-top:14px}
.vac-plan-precio b{font-size:40px;line-height:1;letter-spacing:-.02em}
.vac-plan-precio span{font-size:14px;opacity:.88}
.vac-plan-body{padding:20px 24px 24px}
.vac-plan-fila{display:flex;justify-content:space-between;gap:10px;font-size:13px;color:var(--anf-tenue);margin-bottom:8px;flex-wrap:wrap}
.vac-plan-fila b{color:var(--anf-texto)}
.vac-plan-nota{font-size:13px;color:var(--anf-tenue);margin:12px 0 18px;line-height:1.45}
.vac-plan .btn.ancho{width:100%;min-height:48px;font-size:16px}
.vac-saldo{display:flex;align-items:center;justify-content:center;gap:6px;flex-wrap:wrap;font-size:13px;color:var(--anf-tenue);margin-top:10px}
.vac-saldo a{font-weight:700;color:var(--azul);text-decoration:none;min-height:32px;display:inline-flex;align-items:center}
.vac-sw{display:flex;gap:12px;align-items:flex-start;font-weight:400;background:var(--anf-fondo);border-radius:12px;padding:14px 16px;margin-top:18px;cursor:pointer}
.vac-sw>svg{flex:none;color:var(--azul);margin-top:2px}
.vac-sw .tx{flex:1;min-width:0}
.vac-sw .tx b{display:block;font-size:14px;color:var(--anf-texto)}
.vac-sw .tx small{display:block;font-weight:400;font-size:12.5px;color:var(--anf-tenue);margin-top:2px;line-height:1.4}
.vac-sw input[type=checkbox]{appearance:none;-webkit-appearance:none;width:44px;min-width:44px;height:26px;border-radius:999px;background:var(--anf-borde);position:relative;cursor:pointer;flex:none;margin:0;padding:0;border:0;transition:background .15s}
.vac-sw input[type=checkbox]:after{content:"";position:absolute;top:3px;left:3px;width:20px;height:20px;border-radius:50%;background:#fff;box-shadow:0 1px 3px rgba(20,33,90,.25);transition:left .15s}
.vac-sw input[type=checkbox]:checked{background:var(--azul)}
.vac-sw input[type=checkbox]:checked:after{left:21px}
.vac-sw input[type=checkbox]:focus-visible{box-shadow:var(--foco);outline:none}
.vac-incl-t{display:block;font-size:12px;font-weight:700;letter-spacing:.05em;text-transform:uppercase;color:var(--anf-tenue);margin:4px 0 12px}
.vac-ben{display:flex;gap:16px;align-items:flex-start;background:#fff;border:1px solid var(--anf-borde);border-radius:14px;padding:16px 18px;margin-bottom:12px;text-align:left}
.vac-ben b{display:block;font-size:15px;color:var(--anf-texto)}
.vac-ben small{display:block;font-size:13px;color:var(--anf-tenue);margin-top:3px;line-height:1.45}
.vac-franja{display:flex;gap:12px;align-items:flex-start;background:var(--ok-bg);border-radius:14px;padding:14px 18px;color:var(--ok-fg)}
.vac-franja .ck{width:24px;height:24px;border-radius:50%;background:var(--anf-verde);color:#fff;display:inline-flex;align-items:center;justify-content:center;flex:none}
.vac-franja b{display:block;font-size:14px}.vac-franja small{display:block;font-size:13px;color:var(--anf-texto);margin-top:2px}
@media(max-width:900px){.vac-plan{grid-template-columns:minmax(0,1fr)}}
@media(max-width:600px){.vac-plan-top,.vac-plan-body{padding-left:18px;padding-right:18px}.vac-plan-precio b{font-size:34px}}
/* Candado del plan vencido (páginas de gestión y Cobros) */
.vac-pw{max-width:640px;margin:8px auto 0;text-align:center}
.vac-pw-ic{width:64px;height:64px;border-radius:50%;background:var(--azul-tinte);color:var(--azul);display:inline-flex;align-items:center;justify-content:center;margin-bottom:10px}
.vac-pw h2{font-size:20px;margin:0 0 6px}
.vac-pw>p{color:var(--anf-tenue);font-size:14px;line-height:1.5;margin:0 0 16px}
.vac-pw .vac-ben{margin-bottom:10px}
.vac-pw-acc{display:flex;gap:10px;flex-wrap:wrap;justify-content:center;margin-top:16px}
/* Segmentado con botones (pestañas que cambia el JS sin recargar) */
.va .va-seg button{display:inline-flex;align-items:center;gap:8px;padding:8px 16px;border-radius:9px;color:var(--anf-tenue);font-weight:700;font-size:14px;white-space:nowrap;min-height:38px;border:0;background:transparent;cursor:pointer;font-family:inherit}
.va .va-seg button.sel{background:#fff;color:var(--anf-texto);box-shadow:0 1px 3px rgba(20,33,90,.08)}
.va .va-seg button:focus-visible{box-shadow:var(--foco);outline:none}
.vac-lbl{display:block;font-size:13.5px;font-weight:700;color:var(--anf-texto);margin:16px 0 8px}
/* Soy boleador */
.vac-bol{display:grid;grid-template-columns:minmax(0,420px) minmax(0,1fr);gap:24px;align-items:start}
.vac-bol .va-panel{padding:24px}
.vac-bol h2{font-size:20px}
.vac-bol-intro{font-size:14px;color:var(--anf-tenue);line-height:1.5;margin:8px 0 22px}
.vac-bol-ic{width:48px;height:48px;border-radius:12px;background:var(--azul);color:#fff;display:inline-flex;align-items:center;justify-content:center;margin-bottom:16px}
.vac-tl{list-style:none;margin:0;padding:0}
.vac-tl li{display:grid;grid-template-columns:36px minmax(0,1fr);gap:12px;position:relative;padding-bottom:18px}
.vac-tl li:last-child{padding-bottom:0}
.vac-tl li:not(:last-child):before{content:"";position:absolute;left:17px;top:38px;bottom:2px;width:2px;background:var(--azul-tinte)}
.vac-tl .n{width:36px;height:36px;border-radius:50%;background:var(--azul-tinte);color:var(--azul);display:inline-flex;align-items:center;justify-content:center}
.vac-tl li.sel .n{background:var(--azul);color:#fff}
.vac-tl li.ok .n{background:var(--ok-bg);color:var(--ok-fg)}
.vac-tl b{display:block;font-size:15px;color:var(--anf-texto);margin-top:2px}
.vac-tl li.sel b{color:var(--azul)}
.vac-tl small{display:block;font-size:13px;color:var(--anf-tenue)}
.vac-doc{position:relative}
.vac-doc>svg{position:absolute;left:14px;top:50%;transform:translateY(-50%);color:var(--anf-tenue);pointer-events:none}
.vac-doc input{padding-left:46px;min-height:50px;border:1px solid var(--anf-borde);border-radius:12px;font-size:16px;width:100%}
.vac-doc input:focus{border-color:var(--azul)}
.vac-err{color:var(--anf-rojo);font-size:13px;font-weight:700;min-height:18px;margin-top:6px}
.vac-bol .btn.ancho{width:100%;min-height:50px;font-size:16px;margin-top:4px}
.vac-nota{display:flex;gap:12px;align-items:flex-start;background:var(--anf-fondo);border-radius:12px;padding:14px 16px;margin-top:20px;font-size:13px;color:var(--anf-texto);line-height:1.5}
.vac-nota svg{flex:none;color:var(--warn-fg);margin-top:1px}
.vac-bo{background:var(--azul-tinte);border-radius:12px;padding:16px;font-size:14px;line-height:1.5;color:var(--anf-texto)}
.vac-bo b{display:block;margin-bottom:4px}
.vac-bo .btn{margin-top:12px}
.vac-bol-ops{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,380px);grid-template-areas:"perfil sols";gap:16px;align-items:start}
.vac-bol-ops>.vac-sols{grid-area:sols;min-width:0}.vac-bol-ops>.vac-perfil{grid-area:perfil;min-width:0}
.vac-sols .va-panel h2 .va-pill{margin-left:6px;vertical-align:middle}
.vac-sols .bol-sol{border-color:var(--anf-borde);border-radius:14px}
.vac-sols .bol-sol.pend{border-color:var(--warn-bg);background:var(--warn-bg)}
.vac-sols .bol-sol .acc .btn{min-height:44px}
.vac-lista{display:grid;gap:10px}
.vac-h2{display:flex;align-items:center;gap:8px;margin:0 0 14px!important}
.vac-sol-cab{display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;align-items:center}
.vac-pasos-h{padding:18px 22px}.vac-pasos-h .vac-tl{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}
.vac-pasos-h .vac-tl li{padding-bottom:0}.vac-pasos-h .vac-tl li:before{display:none}
@media(max-width:700px){.vac-pasos-h .vac-tl{grid-template-columns:minmax(0,1fr)}}
.vac-perfil .chips{gap:8px}
.vac-perfil .bol-box{grid-template-columns:repeat(auto-fill,minmax(min(260px,100%),1fr))}
.vac-perfil .bol-card>div{flex:1;min-width:0}.vac-perfil .bol-card .nom{overflow-wrap:anywhere}
.vac-perfil .row{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(200px,100%),1fr));gap:12px}
.vac-perfil .vac-lbl:first-child{margin-top:0}
.vac-check{display:flex;gap:10px;align-items:center;font-weight:700;min-height:44px;margin-top:12px}
.vac-check input{width:auto;flex:none}
@media(max-width:1000px){.vac-bol-ops{grid-template-columns:minmax(0,1fr);grid-template-areas:"sols" "perfil"}}
@media(max-width:900px){.vac-bol{grid-template-columns:minmax(0,1fr)}}
@media(max-width:600px){.vac-bol .va-panel{padding:18px}}
/* Verificador (clases .vf-* de siempre + las del rediseño) */
.vf-wrap{max-width:760px;margin:0 auto}
.vf-tabs{display:flex;gap:8px;margin:18px 0 6px;flex-wrap:wrap}
.vf-tabs .chip{cursor:pointer}
.vf-info{display:flex;gap:10px;align-items:flex-start;background:var(--tinte);color:var(--teal);border-radius:14px;padding:12px 14px;font-size:14px;line-height:1.4;margin:12px 0}
.vf-radios{display:flex;gap:8px;overflow-x:auto;padding:4px 0 8px;scrollbar-width:none}
.vf-radios::-webkit-scrollbar{display:none}
.vf-lista{display:grid;gap:10px;margin-top:8px}
.vf-card{display:flex;gap:12px;align-items:center;background:var(--blanco);border-radius:16px;box-shadow:var(--sombra);padding:14px 16px;cursor:pointer;border:1px solid transparent;min-width:0;text-align:left;width:100%;font-family:inherit;color:inherit}
.vf-card:hover{border-color:var(--trazo)}
.vf-card .txt{flex:1;min-width:0}.vf-card b{display:block;font-size:15.5px;overflow-wrap:anywhere}
.vf-card small{display:block;color:var(--tenue);font-size:13px;overflow-wrap:anywhere}
.vf-card .dist{color:var(--teal);font-weight:800;font-size:13px}
.vf-dem{flex:none;background:var(--tinte);color:var(--teal);border-radius:12px;padding:8px 10px;text-align:center;font-weight:900;font-size:18px;line-height:1}
.vf-dem small{display:block;color:var(--teal);font-weight:600;font-size:12px;margin-top:3px}
.vf-fotos{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}
.vf-fotos .f{position:relative;width:84px;height:84px;border-radius:12px;overflow:hidden;background:var(--gris)}
.vf-fotos .f img{width:100%;height:100%;object-fit:cover;display:block}
.vf-fotos .f button{position:absolute;top:4px;right:4px;width:24px;height:24px;border-radius:50%;border:0;background:rgba(0,0,0,.6);color:#fff;cursor:pointer;font-size:13px;line-height:1}
.vf-msg{margin-top:12px;border-radius:12px;padding:11px 14px;font-weight:600;font-size:14px;line-height:1.4;display:none}
.vf-msg.ok{display:block;background:var(--ok-bg);color:var(--ok-fg)}.vf-msg.bad{display:block;background:var(--bad-bg);color:var(--bad-fg)}.vf-msg.warn{display:block;background:var(--warn-bg);color:var(--warn-fg)}
.vf-cod{font-size:26px!important;letter-spacing:8px;text-align:center;font-weight:800;max-width:260px}
.vf-nota{font-size:12.5px;color:var(--tenue);font-style:italic;margin-top:12px}
.vf-vacio{text-align:center;color:var(--tenue);padding:40px 10px}
.vf-pasos{list-style:none;margin:16px 0 0;padding:0;display:grid;gap:0}
.vf-pasos li{display:grid;grid-template-columns:30px minmax(0,1fr);gap:12px;position:relative;padding-bottom:16px}
.vf-pasos li:not(:last-child)::before{content:'';position:absolute;left:14px;top:30px;bottom:0;width:2px;background:var(--trazo)}
.vf-pasos .n{width:30px;height:30px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:800;font-size:13px;background:var(--gris);color:var(--tenue)}
.vf-pasos li.hecho .n{background:var(--ok-bg);color:var(--ok-fg)}.vf-pasos li.actual .n{background:var(--warn-bg);color:var(--warn-fg)}.vf-pasos li.mal .n{background:var(--bad-bg);color:var(--bad-fg)}
.vf-pasos b{display:block;font-size:15px}.vf-pasos small{display:block;color:var(--tenue);font-size:13px;line-height:1.35}
.vf-acc{display:flex;gap:10px;flex-wrap:wrap;margin-top:16px}.vf-acc .btn{flex:1 1 220px}
.vf-tel{display:flex;align-items:center;border:1px solid var(--trazo);border-radius:12px;overflow:hidden;max-width:320px;background:var(--blanco)}
.vf-tel span{padding:0 10px;font-weight:800;color:var(--tenue)}.vf-tel input{border:0!important;border-radius:0!important;min-width:0}
.vf-estado{display:flex;gap:12px;align-items:flex-start}
.vf-estado .ico{flex:none;width:44px;height:44px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:22px;background:var(--warn-bg)}
.vf-estado.ok .ico{background:var(--ok-bg)}.vf-estado.bad .ico{background:var(--bad-bg)}
@media(max-width:560px){.vf-card{padding:12px 13px}.vf-acc .btn{flex:1 1 100%}}

.vac-vf{display:grid;grid-template-columns:minmax(0,340px) minmax(0,1fr);gap:16px;align-items:start}
.vac-vf h2{font-size:18px}
.vac-vf .va-seg{display:flex;width:100%}.vac-vf .va-seg button{flex:1;justify-content:center;padding:8px 6px}
.vac-gps{background:var(--bad-bg);border-radius:12px;padding:14px 16px;margin-top:14px}
.vac-gps b{display:flex;align-items:center;gap:6px;color:var(--anf-rojo);font-size:14px}
.vac-gps p{margin:4px 0 10px;font-size:13px;color:var(--anf-texto)}
.va .vac-gps .btn{min-height:40px;padding:8px 14px;font-size:13.5px}
.vac-vf select{width:100%;min-height:46px;border:1px solid var(--anf-borde);border-radius:10px;padding:0 12px;font:inherit;font-size:14.5px;background:#fff}
.vac-cnt{display:inline-flex;align-items:center;justify-content:center;min-width:26px;height:24px;border-radius:999px;background:var(--anf-linea);color:var(--anf-tenue);font-size:12.5px;font-weight:700;padding:0 8px;margin-left:8px;vertical-align:middle}
.va .vf-card{border:1px solid var(--anf-borde);box-shadow:none;border-radius:14px}
.va .vf-card:hover{border-color:var(--azul)}
.va .vf-card .dist{color:var(--azul)}
.va .vf-dem{background:var(--azul-tinte);color:var(--azul-osc)}.va .vf-dem small{color:var(--azul-osc)}
.va .vf-info{background:var(--azul-tinte);color:var(--anf-texto)}
.va .vf-vacio{padding:0}
.vac-vf .va-vacio .btn{margin-top:4px}
.vac-cap{max-width:760px}
.vac .vf-wrap{margin:0}.vac .vf-wrap>.va-panel{margin-top:0}
@media(max-width:860px){.vac-vf{grid-template-columns:minmax(0,1fr)}}
@media(max-width:600px){.vac .va-cab-acc .va-seg{display:flex;width:100%}.vac .va-cab-acc .va-seg button{flex:1;white-space:normal;justify-content:center;text-align:center;padding:8px 10px;line-height:1.25}
  .vac .va-pasos{gap:8px}.vac .va-paso{padding:12px 14px}}
/* Operación de la academia (asistencia, evaluación, ranking, reportes, chats, sedes, alumnos) */
.vac-secc{margin-bottom:16px;max-width:100%}
.vac-secc .va-seg{display:flex;max-width:100%}
.vac-acads{margin-bottom:16px}
.aco-card{background:#fff;border:1px solid var(--anf-borde);border-radius:16px;padding:16px 18px;min-width:0}
.aco-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(340px,100%),1fr));gap:14px;margin-top:16px}
.aco-fila{display:flex;align-items:center;gap:12px;min-width:0}
.aco-fila>div{min-width:0}
.aco-av{width:44px;height:44px;border-radius:50%;flex:none;display:flex;align-items:center;justify-content:center;font-weight:800;color:#fff;background:var(--azul);overflow:hidden;font-size:17px}
.aco-av img{width:100%;height:100%;object-fit:cover}
.aco-cuota{display:flex;justify-content:space-between;gap:10px;align-items:center;padding:10px 0;border-top:1px solid var(--anf-linea);flex-wrap:wrap}
.aco-cuota .t{min-width:0;flex:1 1 180px}
.aco-cuota .acc{display:flex;gap:6px;flex-wrap:wrap}
.va .aco-mini{font-size:13px;padding:8px 12px;border-radius:999px;min-height:40px}
.aco-n{font-size:12.5px;color:var(--anf-tenue)}
.aco-bar{display:flex;align-items:flex-end;gap:10px;height:150px;margin-top:10px}
.aco-bar div{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:flex-end;height:100%;min-width:0}
.aco-bar i{display:block;width:100%;max-width:46px;border-radius:8px 8px 3px 3px;background:var(--azul)}
.aco-bar small{font-size:12px;color:var(--anf-tenue);margin-top:4px}
.aco-bar b{font-size:12px;margin-bottom:3px;white-space:nowrap}
.aco-rub{display:flex;gap:6px;flex-wrap:wrap}
.aco-rub .chip{padding:7px 12px;font-size:13px}
.aco-rub .chip.ok.sel{background:var(--ok-bg);border-color:var(--ok-fg);color:var(--ok-fg)}
.aco-rub .chip.warn.sel{background:var(--warn-bg);border-color:var(--warn-fg);color:var(--warn-fg)}
.aco-rub .chip.bad.sel{background:var(--bad-bg);border-color:var(--bad-fg);color:var(--bad-fg)}
.aco-hab{display:flex;justify-content:space-between;align-items:center;gap:10px;padding:10px 0;border-top:1px solid var(--anf-linea);flex-wrap:wrap}
.aco-prog{height:8px;border-radius:99px;background:var(--anf-linea);overflow:hidden;margin-top:6px}
.aco-prog i{display:block;height:100%;background:var(--azul)}
.aco-rk td:first-child{font-weight:800;width:52px;white-space:nowrap}
.aco-msgs{display:flex;flex-direction:column;gap:8px;max-height:60vh;overflow-y:auto;padding:14px;background:var(--anf-fondo);border-radius:16px}
.aco-msg{max-width:78%;padding:8px 12px;border-radius:14px;background:#fff;font-size:14.5px;overflow-wrap:anywhere}
.aco-msg.yo{align-self:flex-end;background:var(--azul-tinte)}
.aco-msg small{display:block;font-size:12px;color:var(--anf-tenue);margin-top:2px;text-align:right}
.aco-dlg label{display:block;font-weight:700;font-size:13.5px;margin:12px 0 6px}
.aco-dlg .chips{margin:0}
.aco-dlg select,.aco-dlg input{width:100%}
.aco-sede{border:1px solid var(--anf-borde);border-radius:16px;padding:14px;margin-top:12px;background:#fff}
.aco-sede .mapa{height:200px;border-radius:12px;margin-top:8px}
.aco-dos{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(200px,100%),1fr));gap:10px}
.aco-aviso{margin-top:14px}
.vac-acc{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin:0 0 14px}
.vac-dia{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:16px}
.vac-dia b{font-size:17px}
.vac-dia input{max-width:170px;min-height:44px}
.vac-filtros{display:flex;flex-direction:column;gap:10px;margin-bottom:16px}
.vac-sub-t{display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap;margin:18px 0 10px}
.vac-sub-t b{font-size:16px}
.aco-asis{justify-content:space-between;flex-wrap:wrap}.aco-asis>.aco-fila{flex:1 1 200px}
.aco-link{text-decoration:none;color:inherit}.aco-link:hover{border-color:var(--azul)}
.aco-crece{flex:1;min-width:0}
.aco-alumno{margin-bottom:14px}.aco-alumno .aco-crece>b{font-size:17px}
.aco-pct{font-size:22px}
.vac .aco-card+.aco-card,.vac .aco-card+.aco-grid{margin-top:14px}
.vac-filtros+.aco-card,.vac-filtros+.aco-grid,.aco-grid>.aco-card,.vac-lista>.aco-card{margin-top:0}
.aco-hab>b{font-size:14.5px}
.aco-nota{margin:-6px 0 14px}
.aco-rojo{color:var(--anf-rojo)}
.aco-corta{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.aco-rango{margin:0 0 12px}
.aco-grid{margin:0 0 16px}
.vac-acc-fin{margin-top:16px}
.vac .chips.vac-filtros{flex-direction:row;flex-wrap:wrap;gap:8px}
@media(pointer:coarse){.va .aco-mini{min-height:44px}}
@media(max-width:600px){.vac-acc .btn{flex:1 1 auto}}
@media print{.anf-cab,.anf-sub,header,footer,.aco-noimp,.va-seg,.va-volver,.va-cab-acc{display:none!important}.aco-card{box-shadow:none}}
"""
