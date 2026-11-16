"""CSS de las vistas del modo anfitrión · Mi tienda, Mi bodega, Mis campeonatos, Llenar cancha, Recordar reservas, Pro — anfitrion_tienda/bodega/campeonatos, jugador_partidos (llenar), jugador_pro.

Va después del kit (`web/vista_anfitrion.py`). Solo tokens (`--azul`, `--anf-*`).

Además de la hoja, aquí viven los íconos de línea que el diseño usa en estas
vistas y que `web/iconos.py` no trae (corona, QR, lápiz, pausa, papelera,
enviar, check…): `ico()` los pinta con el mismo trazo que el kit y, si el
nombre no es de aquí, cae a `iconos.svg`. `cuadro()` = el cuadrado de color
del kit (`.va-ic`) con cualquiera de esos íconos.
"""

from __future__ import annotations

_EXTRA = {
    "corona": "<path d='M3 8l4.5 4L12 5l4.5 7L21 8l-2 11H5z'/>",
    "qr": ("<rect x='4' y='4' width='6' height='6' rx='1'/><rect x='14' y='4' width='6' height='6' rx='1'/>"
           "<rect x='4' y='14' width='6' height='6' rx='1'/><path d='M14 14h2v2h-2zM18 14h2M14 18v2M18 18h2v2'/>"),
    "lapiz": "<path d='M4 20h4L19 9l-4-4L4 16z'/><path d='M14 6l4 4'/>",
    "pausa": "<path d='M9 5v14M15 5v14'/>",
    "play": "<path d='M8 5l11 7-11 7z'/>",
    "papelera": "<path d='M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13'/>",
    "enviar": "<path d='M4 12l16-8-6 16-3-7z'/>",
    "check": "<path d='M5 12.5l4.5 4.5L19 7.5'/>",
    "check_c": "<circle cx='12' cy='12' r='9'/><path d='M8 12.5l3 3 5-6'/>",
    "imagen": "<rect x='3' y='5' width='18' height='14' rx='2'/><circle cx='9' cy='10' r='2'/><path d='M21 17l-5-5-9 7'/>",
    "sol": ("<circle cx='12' cy='12' r='4'/><path d='M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.3 5.3l1.4 1.4"
            "M17.3 17.3l1.4 1.4M5.3 18.7l1.4-1.4M17.3 6.7l1.4-1.4'/>"),
    "megafono": "<path d='M3 10.5v3a1 1 0 001 1h3l7 4.5V5L7 9.5H4a1 1 0 00-1 1z'/><path d='M18 9a4 4 0 010 6'/>",
    "info": "<circle cx='12' cy='12' r='9'/><path d='M12 11v5M12 7.6v.1'/>",
    "bolsa": "<path d='M5 8h14l-1.2 12H6.2z'/><path d='M9 8V6.5a3 3 0 016 0V8'/>",
    "cartera": "<rect x='3' y='6' width='18' height='13' rx='2.5'/><path d='M3 10h18M16 14.5h2'/>",
    "carnet": ("<rect x='3' y='5' width='18' height='14' rx='2'/><circle cx='9' cy='11' r='2'/>"
               "<path d='M14 10h4M14 14h4M6 16.5c.6-1.4 1.7-2 3-2s2.4.6 3 2'/>"),
    "rayo": "<path d='M13 3L5 13.5h6L10 21l8-10.5h-6z'/>",
    "candado": "<rect x='5' y='11' width='14' height='9' rx='2'/><path d='M8 11V8a4 4 0 018 0v3'/>",
    "ticket": "<path d='M4 7h16v3a2 2 0 000 4v3H4v-3a2 2 0 000-4z'/><path d='M10 7v10' stroke-dasharray='2 2'/>",
}


def ico(nombre: str, tam: int = 18, grueso: float = 2.2) -> str:
    """Ícono de línea (`currentColor`) con el trazo del kit."""
    cuerpo = _EXTRA.get(nombre)
    if cuerpo is None:
        from web import iconos
        return iconos.svg(nombre, tam, grueso=grueso)
    return (f"<svg class='ic-l' viewBox='0 0 24 24' width='{tam}' height='{tam}' fill='none' stroke='currentColor' "
            f"stroke-width='{grueso}' stroke-linecap='round' stroke-linejoin='round' aria-hidden='true'>{cuerpo}</svg>")


def cuadro(nombre: str, color: str = "azul", tam: int = 18, suave: bool = False) -> str:
    """Cuadrado de color del kit (`.va-ic`) con un ícono de aquí o de `iconos`."""
    if suave:
        return f"<span class='va-ic suave'>{ico(nombre, tam)}</span>"
    from web.vista_anfitrion import COLORES
    return f"<span class='va-ic' style='background:{COLORES.get(color, color)}'>{ico(nombre, tam)}</span>"


CSS = r"""
/* ── comercio: piezas comunes ── */
.vc-sec-t{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;margin:8px 0 14px}
.vc-sec-t>b{font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:var(--anf-tenue)}
.va-seg button{display:inline-flex;align-items:center;gap:8px;padding:8px 16px;border-radius:9px;color:var(--anf-tenue);font:inherit;font-weight:700;font-size:14px;background:transparent;border:0;cursor:pointer;white-space:nowrap;min-height:38px}
.va-seg button.sel{background:#fff;color:var(--anf-texto);box-shadow:0 1px 3px rgba(20,33,90,.08)}
.va-seg button i{font-style:normal;background:var(--azul-tinte);color:var(--azul-osc);border-radius:999px;padding:1px 8px;font-size:12px}
.va .btn .ic-l{flex:none}
.va .btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;text-decoration:none}
.vc-ico-btn{width:44px;padding:0 !important;flex:none}
.vc-nota{display:flex;gap:8px;align-items:flex-start;color:var(--anf-tenue);font-size:13px;line-height:1.45}
.vc-nota .ic-l{flex:none;margin-top:1px}

/* ── Mi tienda ── */
.vc-prods{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(240px,100%),1fr));gap:16px;margin-bottom:16px}
.vc-prod{background:#fff;border:1px solid var(--anf-borde);border-radius:16px;overflow:hidden;display:flex;flex-direction:column;min-width:0}
.vc-prod[hidden]{display:none}
.vc-prod-f{position:relative;aspect-ratio:16/10;background:var(--azul-tinte);display:flex;align-items:center;justify-content:center;color:var(--azul-suave)}
.vc-prod-f img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;display:block}
.vc-prod-f .va-pill{position:absolute;top:10px;left:10px}
.vc-prod-f .vc-ph{color:#fff;opacity:.95}
.vc-prod-b{padding:14px 16px 16px;display:flex;flex-direction:column;gap:6px;flex:1;min-width:0}
.vc-prod-b h3{font-size:15px;margin:0;line-height:1.3;color:var(--anf-texto);overflow-wrap:anywhere}
.vc-prod-m{display:flex;justify-content:space-between;align-items:center;gap:8px;font-size:12.5px;color:var(--anf-tenue)}
.vc-prod-m .vc-cat{display:inline-flex;align-items:center;gap:5px;min-width:0;padding:0;margin:0}
.vc-prod-m .vc-st{white-space:nowrap}.vc-prod-m .vc-st.bajo{color:var(--anf-rojo);font-weight:700}
.vc-precio{font-size:21px;font-weight:800;color:var(--anf-texto);margin:4px 0 6px}
.vc-prod-acc{display:flex;gap:8px;margin-top:auto;align-items:center}
.vc-prod-acc .btn{padding:8px 12px;font-size:14px}
.vc-prod-acc .vc-borrar{margin-left:auto}
.vc-vacio-fila{display:flex;align-items:center;gap:14px}
@media(max-width:600px){.vc-sec-t .va-seg{width:100%}.vc-sec-t .va-seg button{flex:1;justify-content:center;padding:8px 6px}.vc-prod-f{aspect-ratio:16/8}}
.vc-vacio-fila b{display:block;font-size:14.5px}.vc-vacio-fila small{display:block;color:var(--anf-tenue);font-size:13px;margin-top:2px}

/* ── Mi bodega ── */
.vc-pro-banner{display:flex;align-items:center;gap:14px;flex-wrap:wrap;background:var(--azul-tinte);border:1px solid var(--azul-suave);border-radius:16px;padding:16px 20px;margin-bottom:16px}
.vc-pro-banner .tx{flex:1;min-width:220px}.vc-pro-banner .tx b{display:block;font-size:15.5px}
.vc-pro-banner .tx small{display:block;color:var(--anf-tenue);font-size:13px;margin-top:3px}
.vc-func{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}
@media(max-width:700px){.vc-func{grid-template-columns:minmax(0,1fr)}}
.vc-func-it{position:relative;background:#fff;border:1px solid var(--anf-borde);border-radius:16px;padding:20px;min-width:0}
.vc-func-it .va-ic{width:44px;height:44px;border-radius:12px}
.vc-func-it h3{font-size:16px;margin:14px 0 4px}.vc-func-it p{margin:0;color:var(--anf-tenue);font-size:13.5px;line-height:1.45}
.vc-func-it .va-pill{position:absolute;top:16px;right:16px}
.vc-bod-tabs{margin-bottom:16px}
@media(max-width:600px){.vc-bod-tabs .va-seg{width:100%}.vc-bod-tabs .va-seg a{padding:8px 11px;flex:1;justify-content:center}}
.va .bod{max-width:none;padding-bottom:110px}
.va .bgrid{grid-template-columns:repeat(auto-fill,minmax(min(180px,100%),1fr))}
.va .bprod{border-color:var(--anf-borde)}
.va .bprod.en{border-color:var(--azul);background:var(--azul-tinte)}
.va .bprod .cant{background:var(--azul)}
.va .bticket{border-color:var(--azul)}
.va .bfila,.va .bped,.va .bsec,.va .bcerr{border-color:var(--anf-borde)}
.va .bfila .stk b{color:var(--azul)}
.va .bfila .stk.bajo b,.va .bfila .stk.bajo small,.va .bprod .st.bajo,.va .brep .bajo{color:var(--anf-rojo)}
.va .bped.pend{border-color:var(--warn-fg);background:var(--warn-bg)}
.va .bcta{border-color:var(--azul);background:var(--azul-tinte)}
.va .bsw .sw.on{background:var(--azul)}
.va .bbusca{border-color:var(--anf-borde);min-height:44px}
.va .brep h3{font-size:16px;margin:18px 0 8px}

/* ── Mis campeonatos ── */
.vc-cmp{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,440px);gap:16px;align-items:start}
.vc-cmp-vacio .va-vacio{padding:28px 8px 12px}
.vc-deps{display:flex;flex-wrap:wrap;gap:8px;justify-content:center;margin:4px 0 18px}
.vc-deps span{border:1px solid var(--anf-borde);border-radius:999px;padding:6px 14px;font-size:13px;font-weight:700;color:var(--anf-texto);background:#fff}
.vc-cmp-vacio .btn{min-width:min(400px,100%)}
.vc-codigo-cab{display:flex;gap:12px;align-items:center;margin-bottom:18px}
.vc-codigo-cab b{display:block;font-size:16px}.vc-codigo-cab small{display:block;color:var(--anf-tenue);font-size:13px}
.vc-codigo label{display:block;font-weight:700;font-size:13.5px;margin-bottom:6px}
.vc-codigo input{width:100%;text-transform:uppercase;letter-spacing:.12em;font-weight:800;min-height:46px}
.vc-codigo .btn{width:100%;margin-top:12px}
.vc-codigo-p hr{border:0;border-top:1px solid var(--anf-linea);margin:18px 0 14px}
.vc-codigo .vc-err{color:var(--anf-rojo);font-size:13px;margin:8px 0 0}
.vc-cmp-it{display:flex;align-items:center;gap:14px;padding:12px 4px;border-top:1px solid var(--anf-linea);text-decoration:none;color:inherit;min-height:44px}
.vc-cmp-it:first-child{border-top:0}
.vc-cmp-it:hover b{color:var(--azul-osc)}
.vc-cmp-logo{width:52px;height:52px;border-radius:12px;background:var(--azul-tinte);display:flex;align-items:center;justify-content:center;font-size:24px;overflow:hidden;flex:none}
.vc-cmp-logo img{width:100%;height:100%;object-fit:cover}
.vc-cmp-it .tx{flex:1;min-width:0}.vc-cmp-it .tx b{display:block;font-size:15px;overflow-wrap:anywhere}
.vc-cmp-it .tx small{display:block;color:var(--anf-tenue);font-size:12.5px;margin:2px 0 6px}
.vc-cmp-it .ir{color:var(--anf-tenue);font-size:22px}
@media(max-width:900px){.vc-cmp{grid-template-columns:minmax(0,1fr)}}

/* ── Llenar cancha ── */
.vc-ll .va-lat{max-height:none}
.vc-slots{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(104px,100%),1fr));gap:10px}
.vc-slot{position:relative;text-align:left;background:#fff;border:1.5px solid var(--anf-borde);border-radius:12px;padding:10px 12px;font:inherit;color:var(--anf-texto);cursor:pointer;min-height:64px;display:flex;flex-direction:column;gap:2px}
.vc-slot b{font-size:18px}.vc-slot small{font-size:12.5px;color:var(--anf-tenue);display:inline-flex;align-items:center;gap:4px}
.vc-slot .valle{color:var(--warn-fg)}
.vc-slot .chk{position:absolute;top:9px;right:9px;width:20px;height:20px;border-radius:50%;background:var(--azul);color:#fff;display:none;align-items:center;justify-content:center}
.vc-slot.sel{border-color:var(--azul);background:var(--azul-tinte)}
.vc-slot.sel b{color:var(--azul-osc)}.vc-slot.sel small{color:var(--warn-fg);font-weight:700}
.vc-slot.sel .chk{display:flex}
.vc-slot:focus-visible{outline:none;box-shadow:var(--foco)}
.vc-ll-sel{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin:14px 0 4px;font-size:14px}
.vc-ll-sel b{font-weight:700}
.vc-link{background:none;border:0;color:var(--azul);font:inherit;font-weight:700;cursor:pointer;padding:6px 0;min-height:36px}
.vc-ll-lbl{display:block;font-weight:700;font-size:14px;margin:16px 0 8px}
.vc-chips{display:flex;flex-wrap:wrap;gap:8px}
.vc-chips button{border:1px solid var(--anf-borde);background:#fff;border-radius:999px;padding:8px 14px;font:inherit;font-size:13.5px;font-weight:700;color:var(--anf-texto);cursor:pointer;min-height:40px}
.vc-ll-txt{width:100%;border:1px solid var(--anf-borde);border-radius:10px;padding:11px 14px;font:inherit;font-size:15px;min-height:44px;margin-bottom:8px}
.vc-ll-txt:focus{outline:none;box-shadow:var(--foco);border-color:var(--azul)}
.vc-sug button{font-weight:600;font-size:13px;min-height:36px}
.vc-chips button.sel{background:var(--azul-tinte);border-color:var(--azul);color:var(--azul-osc)}
.vc-ayuda{font-size:12.5px;color:var(--anf-tenue);margin:8px 0 0}
.vc-chat{background:var(--anf-fondo);border-radius:14px;padding:14px}
.vc-chat-cab{display:flex;align-items:center;gap:10px;margin-bottom:10px}
.vc-chat-av{width:34px;height:34px;border-radius:50%;background:var(--azul);color:#fff;font-weight:800;display:flex;align-items:center;justify-content:center;flex:none}
.vc-chat-cab b{display:block;font-size:14px}.vc-chat-cab small{display:block;font-size:12px;color:var(--anf-tenue)}
.vc-burbuja{background:#fff;border:1px solid var(--anf-borde);border-radius:4px 14px 14px 14px;padding:12px 14px;font-size:13.5px;line-height:1.5;white-space:pre-line;overflow-wrap:anywhere;color:var(--anf-texto)}
.vc-burbuja.vacia{color:var(--anf-tenue)}
.vc-ll-go{width:100%;margin-top:16px}
.vc-ll-cli{margin-top:12px}

/* ── Recordar reservas ── */
.vc-rec-banner{display:flex;align-items:center;gap:14px;flex-wrap:wrap}
.vc-rec-banner .tx{flex:1;min-width:220px}.vc-rec-banner .tx b{display:block;font-size:15.5px}
.vc-rec-banner .tx small{display:block;color:var(--anf-tenue);font-size:13px;margin-top:3px}
.vc-rec .va-panel.vc-rec-banner{padding:16px 20px}
.vc-hora{display:inline-flex;align-items:center;gap:8px;font-weight:700;white-space:nowrap}
.vc-hora .ic-l{color:var(--azul)}
.vc-jug{display:inline-flex;align-items:center;gap:10px;font-weight:700}
.vc-av{width:32px;height:32px;border-radius:50%;background:var(--anf-verde);color:#fff;font-weight:800;display:inline-flex;align-items:center;justify-content:center;flex:none;font-size:14px}
.vc-rec .btn{padding:8px 14px;font-size:14px;background:#fff;color:var(--azul);border:1.5px solid var(--azul)}
.vc-rec .btn:hover{background:var(--azul-tinte)}
.vc-rec .vc-rec-banner .btn{background:var(--azul);color:#fff;border:0;padding:11px 20px}
.vc-rec .vc-rec-banner .btn:hover{background:var(--azul-osc)}
.vc-rec td:last-child,.vc-rec th:last-child{text-align:right}
.vc-cel{display:flex;flex-direction:column;min-width:0}
.vc-rec tr.vc-mas{display:none}.vc-rec .vc-todos tr.vc-mas{display:table-row}
.vc-ver{display:block;text-align:center;margin-top:10px}
@media(max-width:600px){.vc-rec .vc-todos tr.vc-mas{display:block}.vc-cel{align-items:flex-end;text-align:right}.vc-rec .vc-rec-banner .btn{width:100%}}

/* ── Pro ── */
.vc-pro{display:grid;grid-template-columns:minmax(0,420px) minmax(0,1fr);gap:24px;align-items:start}
.vc-plan{background:#fff;border:1px solid var(--anf-borde);border-radius:18px;overflow:hidden}
.vc-plan-cab{background:linear-gradient(135deg,var(--azul-osc),var(--azul));color:#fff;padding:24px}
.vc-plan-t{display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.vc-plan-t h2{color:#fff !important;font-size:22px !important;margin:0}
.vc-corona{width:42px;height:42px;border-radius:11px;background:var(--warn-bg);color:var(--warn-fg);display:flex;align-items:center;justify-content:center;flex:none}
.vc-activo{background:#fff;color:var(--azul-osc);border-radius:999px;padding:4px 11px;font-size:12px;font-weight:800}
.vc-plan-cab .pr-precio{display:flex;align-items:baseline;gap:8px;margin-top:22px}
.vc-plan-cab .pr-precio b{font-size:42px;line-height:1;font-weight:800}
.vc-plan-cab .pr-precio span{color:rgba(255,255,255,.85);font-size:16px}
.vc-plan-cab p{margin:6px 0 0;color:rgba(255,255,255,.88);font-size:13px}
.vc-plan-b{padding:20px 24px 22px}
.vc-saldo{display:flex;gap:10px;align-items:flex-start;background:var(--anf-fondo);border-radius:12px;padding:14px}
.vc-saldo .ic-l{color:var(--azul);flex:none;margin-top:1px}
.vc-saldo b{display:block;font-size:14px}.vc-saldo small{display:block;font-size:13px;color:var(--anf-tenue);margin-top:2px}
.vc-saldo .fila{display:flex;gap:14px;flex-wrap:wrap;margin-top:4px;font-size:13px;font-weight:700}
.vc-saldo .poco{color:var(--anf-rojo)}.vc-saldo a{color:var(--azul);text-decoration:none}
.vc-plan .pr-cta{width:100%;margin-top:16px;padding:14px;font-size:16px}
.vc-plan .pr-link{text-align:center;margin:14px 0 0}
.vc-plan .pr-link a{font-weight:700;color:var(--azul);text-decoration:none;display:inline-flex;min-height:36px;align-items:center}
.vc-renov{border:1px solid var(--anf-borde);border-radius:12px;padding:12px 14px;margin-top:12px;display:flex;flex-direction:column;gap:8px}
.vc-renov.warn{background:var(--warn-bg);border-color:var(--warn-bg)}
.vc-renov b{font-size:14px}.vc-renov small{color:var(--anf-tenue);font-size:13px}
.vc-renov .btn{align-self:flex-start;padding:8px 14px;font-size:14px}
.va .vc-ben-t{font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:var(--anf-tenue);font-weight:700;margin:4px 0 10px}
.vc-ben{list-style:none;margin:0 0 22px;padding:4px 18px;background:#fff;border:1px solid var(--anf-borde);border-radius:16px}
.vc-ben li{display:flex;align-items:center;gap:14px;padding:14px 0;border-top:1px solid var(--anf-linea)}
.vc-ben li:first-child{border-top:0}
.vc-ben .tx{flex:1;min-width:0}.vc-ben b{display:block;font-size:15px}.vc-ben small{display:block;font-size:13px;color:var(--anf-tenue);margin-top:2px}
.vc-ben .ok{color:var(--anf-verde);flex:none}
@media(max-width:900px){.vc-pro{grid-template-columns:minmax(0,1fr)}}
"""
