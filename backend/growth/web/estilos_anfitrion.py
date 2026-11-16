"""Estilos del MODO ANFITRIÓN en la web (`web/anfitrion.py` y
`web/anfitrion_negocio.py`).

Antes cada tarjeta de reserva, celda del mapa de calor o fila de cancha llevaba
sus estilos en línea (`style='…'`): Reservas pesaba ~480 KB con más de 3 000
atributos `style` y el navegador recalculaba miles de reglas sueltas. Ahora
esas reglas viven aquí, UNA vez, y viajan dentro del CSS versionado del sitio
(`ui.CSS` → `/web/a/estilo.<huella>.css`, caché inmutable). También se
mudaron aquí las hojas que esas páginas metían en línea en cada respuesta
(calendario, menú, cuenta de cobro y la de "Tu negocio").

Reglas:
- Prefijo `anf-` para las clases nuevas; las del negocio conservan `ng-`/`hm-`.
- Solo tokens de color (`var(--…)`). Los pocos hex que quedan ya existían en
  línea (escala del mapa de calor y dos colores de segmento sin token) y se
  mudaron tal cual, sin colores nuevos.
- Lo que en la hoja del negocio pisa clases GENÉRICAS (`.kpis`, `.kpi`,
  `.pill.*`) va bajo `:where(.anf-ng)` (especificidad 0: se comporta igual que
  cuando la hoja iba en línea) para no tocar el resto del sitio; el envoltorio
  `.anf-ng` lo pone `anfitrion_negocio._pagina`.
- Texto mínimo 12 px y, en pantallas táctiles (`pointer:coarse`), todo lo
  tocable de estas páginas mide al menos 44 px de alto (envoltorio `.anf-pag`).
"""

from __future__ import annotations

# Mapa de calor (Ocupación): un solo tono, claro → oscuro. Nivel 0 = sin
# reservas (gris del sistema). `anfitrion_negocio` usa la misma escala.
RAMPA = ["#E6F4EA", "#BFE3CB", "#8DCBA3", "#52AC77", "#1E8F4E", "#0B6E3A"]

# Color de la insignia de segmento en Clientes (los que tienen token lo usan).
SEG_FONDO = {"vip": "#B8860B", "recurrente": "var(--esmeralda)", "nuevo": "#2F6FDE",
             "riesgo": "var(--bad-fg)", "moroso": "var(--warn-fg)"}

# ── Calendario semanal (antes `anfitrion._CSS_CAL`, en línea en cada página) ──
_CAL = (
    ".cal-dias{display:none;margin-top:12px;flex-wrap:nowrap;overflow-x:auto;gap:8px;padding-bottom:4px}"
    ".cal-dias .chip{flex:none;min-height:44px}"
    ".cal-sem td:first-child,.cal-sem th:first-child{position:sticky;left:0;z-index:1;background:var(--blanco)}"
    ".cal-sem th:first-child{z-index:2}"
    ".cal-sem td.fuera{background:repeating-linear-gradient(45deg,var(--gris) 0 6px,var(--blanco) 6px 12px)}"
    ".cal-sem th.cerr{color:var(--tenue)}"
    ".cal-cerr{display:block;font-size:12px;font-weight:700;color:var(--bad-fg);margin-top:2px}"
    ".cal-sem td[data-t]{cursor:pointer}.cal-sem td[data-t]:focus-visible{outline:3px solid var(--esmeralda);outline-offset:-3px}"
    ".cal-sem .vh{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}"
    ".cal-act td[data-t]:focus-visible .li{opacity:1}"
    # Texto mínimo 12 px: "pagada", "cobrar en cancha" y el precio del turno libre.
    ".cal-sem .oc small,.cal-sem .li small{font-size:12px}"
    "@media(max-width:600px){.cal-dias{display:flex}.cal-sem table{min-width:0}.cal-sem td{min-width:0}.cal-act td .li{opacity:1}"
    ".cal-sem [data-col]{display:none}"
    + ",".join(f".cal-sem[data-dia='{i}'] [data-col='{i}']" for i in range(7)) + "{display:table-cell}}"
)

# ── Menú del modo anfitrión y tarjeta "Cuenta de cobro" (Ingresos) ──
_MENU = (
    ".anf-grupo{display:flex;flex-direction:column;gap:14px}.anf-grupo h2{margin:12px 0 0;font-size:15px;"
    "text-transform:uppercase;letter-spacing:.06em;color:var(--tenue)}.anf-insignia{display:inline-flex!important;min-width:28px;"
    "justify-content:center;font-weight:800}.anf-item:focus-visible{outline:3px solid var(--esmeralda);outline-offset:2px}"
    ".cc-actual{display:flex;gap:12px;align-items:center;flex-wrap:wrap;background:var(--gris);border-radius:14px;padding:12px 14px}"
    ".cc-actual .ico{font-size:22px}.cc-actual>div{flex:1;min-width:200px}.cc-actual small{display:block;color:var(--tenue);font-weight:600;margin-top:2px}"
    ".cc-actual.sin{background:#FFF3D6}#ccForm label{margin-top:12px}"
)

# ── Clases que reemplazan los `style=` repetidos de anfitrion.py ──
_ANF = """
.anf-res-cab{display:flex;justify-content:space-between;gap:8px;align-items:baseline}
.anf-res .anf-res-dia{margin:0;font-weight:700}
.anf-res .anf-res-cancha{margin:2px 0 0;font-weight:700;color:var(--noche)}
.anf-res .anf-res-det{margin:0;font-size:12.5px}
.anf-precio{margin-left:auto;white-space:nowrap}
.anf-flex1{flex:1;min-width:0}
.anf-fila-tit{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.anf-pag .sub.anf-l2{margin:2px 0 0}
.anf-pag .acciones.anf-acc8{margin-top:8px}.anf-pag .acciones.anf-acc10{margin-top:10px}
.anf-nowrap{white-space:nowrap}
.anf-local .anf-local-nom{font-size:17px}
.anf-h2-26{margin-top:26px}.anf-h2-28{margin-top:28px}
.anf-h2-26 small{color:var(--tenue);font-size:14px;font-weight:600}
.anf-dia-h{margin:16px 0 8px}
.anf-col-todo{grid-column:1/-1}
.anf-mt14{margin-top:14px}
.kpi.anf-atajo{text-decoration:none}.kpi.anf-atajo b{font-size:16px}
.anf-der{text-align:right}
.anf-tabs .chip small{font-size:12px}
.anf-pag .pill.anf-pill-n{white-space:normal}
.anf-gap8{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.anf-fila-ent{display:flex;justify-content:space-between;gap:8px}
.anf-pag .sub.anf-lugar{margin:4px 0 8px}
"""

# ── "Tu negocio" (antes `anfitrion_negocio.CSS`, en línea en cada página) ──
_NG = r"""
:where(.anf-ng) .kpis{grid-template-columns:repeat(auto-fill,minmax(min(150px,100%),1fr))}:where(.anf-ng) .kpi{min-width:0}:where(.anf-ng) .kpi b{overflow-wrap:anywhere}
.ng-nav{display:flex;gap:8px;overflow-x:auto;padding:4px 0 10px;margin:8px 0 6px;scrollbar-width:none}.ng-nav::-webkit-scrollbar{display:none}
.ng-nav .chip{flex:none;font-size:13.5px;padding:8px 13px}.ng-nav .chip span{font-size:15px}
.ng-tabs{display:flex;gap:22px;border-bottom:1px solid var(--trazo);margin:6px 0 16px;overflow-x:auto;scrollbar-width:none}
.ng-tabs a{padding:10px 0;font-weight:700;color:var(--tenue);text-decoration:none;border-bottom:3px solid transparent;white-space:nowrap}
.ng-tabs a.sel{color:var(--noche);border-bottom-color:var(--esmeralda)}
.ng-mon{margin:0 0 10px}
.ng-h2{margin-top:28px;font-size:19px}.ng-h2 small{color:var(--tenue);font-size:14px;font-weight:600}
.ng-hero,.ng-card{background:var(--blanco);border:1px solid var(--trazo);border-radius:20px;padding:18px 20px;box-shadow:var(--sombra);margin-top:16px;min-width:0}
.ng-card h3{margin:0 0 8px;font-size:16px}
.ng-hero>small{display:block;color:var(--tenue);font-weight:600}.ng-hero>b{display:block;font-size:34px;color:var(--esmeralda);margin:4px 0}
.ng-barras{display:flex;align-items:flex-end;gap:8px;margin-top:10px;min-width:0}
.ng-bar{flex:1;min-width:0;display:flex;flex-direction:column;align-items:center;justify-content:flex-end;height:100%;cursor:default;outline:none}
.ng-bar i{display:block;width:100%;max-width:44px;background:var(--esmeralda);border-radius:4px 4px 0 0;transition:opacity .15s}
.ng-bar:hover i,.ng-bar:focus i{opacity:.8}
.ng-bar small{font-size:12px;font-weight:700;color:var(--noche);min-height:15px;white-space:nowrap}
.ng-bar span{font-size:12px;color:var(--tenue);margin-top:5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:100%}
.ng-tabla{margin-top:10px;font-size:13px;color:var(--tenue)}.ng-tabla summary{cursor:pointer;font-weight:700}
.ng-tabla table{border-collapse:collapse;margin-top:6px}.ng-tabla td,.ng-tabla th{padding:4px 10px;border-bottom:1px solid var(--trazo);text-align:left}
.ng-hb{margin:10px 0}.ng-hb-t{display:flex;gap:8px;align-items:baseline;min-width:0}.ng-hb-t b{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.ng-hb-t small{color:var(--tenue);font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;min-width:0}.ng-hb-t span{margin-left:auto;font-weight:800;white-space:nowrap}
.ng-hb-p{height:10px;background:var(--gris);border-radius:6px;margin-top:5px;overflow:hidden}.ng-hb-p i{display:block;height:100%;background:var(--esmeralda);border-radius:6px}
.ng-local{background:var(--blanco);border:1px solid var(--trazo);border-radius:16px;padding:12px 16px;margin-top:12px}
.ng-local-h{display:flex;justify-content:space-between;gap:8px}.ng-local-h span{font-weight:800}
.ng-rc{display:flex;justify-content:space-between;gap:10px;padding:8px 0;border-top:1px solid var(--trazo)}.ng-rc:first-of-type{border-top:0}
.ng-rc div{min-width:0}.ng-rc small{display:block;color:var(--tenue);font-size:12px}.ng-rc span{font-weight:800;color:var(--esmeralda);white-space:nowrap}
.ng-rc.tot b{font-size:15px}.ng-rc.tot span{font-size:17px}
.ng-nota{font-size:12.5px;color:var(--tenue);margin:8px 0 0}
.ng-custom{display:flex;flex-wrap:wrap;gap:10px;align-items:flex-end;margin-top:10px}.ng-custom label{display:flex;flex-direction:column;font-size:12.5px;font-weight:700;color:var(--tenue);gap:4px}
.ng-custom input{width:auto}
.ng-lista{display:flex;flex-direction:column;gap:8px;margin-top:10px}
.ng-fila{display:flex;align-items:center;gap:10px;background:var(--blanco);border:1px solid var(--trazo);border-radius:14px;padding:11px 14px;min-width:0;text-decoration:none;color:inherit;flex-wrap:wrap}
.ng-fila.pausa,.ng-fila.pasada{opacity:.6}
.ng-fila-t{flex:1;min-width:150px}.ng-fila-t b{display:block;overflow:hidden;text-overflow:ellipsis}.ng-fila-t small{display:block;color:var(--tenue);font-size:12.5px}
.ng-monto{white-space:nowrap}
.ng-sena{color:var(--teal)!important;font-weight:700}
.mini-b{padding:8px 12px!important;font-size:13px!important}
:where(.anf-ng) .pill.gris{background:var(--gris);color:var(--tenue)}:where(.anf-ng) .pill.bad{background:var(--bad-bg);color:var(--bad-fg)}:where(.anf-ng) .pill.warn{background:var(--warn-bg);color:var(--warn-fg)}:where(.anf-ng) .pill.ok{background:var(--ok-bg);color:var(--ok-fg)}
:where(.anf-ng) .kpi.bad b{color:var(--bad-fg)}:where(.anf-ng) .kpi.ok b{color:var(--esmeralda)}
.ng-atajos a{text-decoration:none;color:inherit}.ng-atajos b{font-size:15px}
.ng-dia{display:flex;align-items:center;gap:10px;margin-top:14px;flex-wrap:wrap}.ng-dia input{width:auto}.ng-dia>b{font-size:17px}
.ng-flecha{width:38px;height:38px;border-radius:50%;border:1px solid var(--trazo);display:inline-flex;align-items:center;justify-content:center;text-decoration:none;color:var(--noche);font-size:22px;background:var(--blanco);box-shadow:0 1px 3px rgba(0,0,0,.06)}
.ng-cierre-box{margin-top:16px}.ng-cierre{display:flex;gap:10px;align-items:center;flex-wrap:wrap;background:var(--ok-bg);border-radius:16px;padding:12px 16px}
.ng-cierre.auto{background:var(--warn-bg)}.ng-cierre>div{flex:1;min-width:180px}.ng-cierre small{display:block;color:var(--tenue)}
.ng-av{width:42px;height:42px;border-radius:50%;object-fit:cover;flex:none;display:inline-flex;align-items:center;justify-content:center;background:var(--esmeralda);color:#fff;font-weight:800;font-size:17px}
.ng-busca{display:flex;flex-direction:column;gap:10px;margin:14px 0 4px}
.ng-clis{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(280px,100%),1fr));gap:12px;margin-top:12px}
.ng-cli{position:relative;text-align:left;background:var(--blanco);border:1px solid var(--trazo);border-radius:18px;padding:14px 16px;box-shadow:var(--sombra);cursor:pointer;font:inherit;color:inherit;min-width:0}
.ng-cli:hover{box-shadow:var(--sombra2)}
.ng-cli-h{display:flex;gap:12px;align-items:center;min-width:0;padding-right:70px}.ng-cli-h b{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.ng-cli-h small{display:block;color:var(--tenue);font-size:12.5px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.ng-cli-h>div{min-width:0}
.ng-cli-d{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:6px;margin-top:12px;font-size:12px;color:var(--tenue)}
.ng-cli-d b{display:block;color:var(--noche);font-size:14px}
.ng-debe{margin-top:8px;font-size:12.5px;font-weight:800;color:var(--warn-fg);background:var(--warn-bg);border-radius:999px;padding:4px 10px;display:inline-block}
.ng-badge{position:absolute;top:12px;right:12px;color:#fff;font-size:12px;font-weight:800;padding:4px 9px;border-radius:999px}
.ng-ficha{text-align:left}.ng-ficha .fh{display:flex;gap:12px;align-items:center;margin-bottom:12px}.ng-ficha .fh small{display:block;color:var(--tenue)}
.ng-ficha .dts{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.ng-ficha .dts div{background:var(--gris);border-radius:12px;padding:8px 10px}
.ng-ficha .dts small{display:block;color:var(--tenue);font-size:12px}.ng-ficha .acc{display:flex;gap:8px;flex-wrap:wrap;margin:12px 0}
.ng-ficha textarea{width:100%;min-height:70px;border:1px solid var(--trazo);border-radius:12px;padding:10px;font:inherit;box-sizing:border-box}
.ng-ficha .hist{font-size:13px;margin-top:10px}.ng-ficha .hist div{display:flex;justify-content:space-between;gap:8px;padding:6px 0;border-top:1px solid var(--trazo)}
.ng-ficha .nota-l{display:block;font-weight:800;margin:14px 0 6px;text-align:left}
.ng-bonos{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(320px,100%),1fr));gap:12px;margin-top:14px}
.ng-bono{display:flex;flex-wrap:wrap;gap:12px;align-items:center;background:var(--blanco);border:1px solid var(--trazo);border-radius:18px;padding:14px;box-shadow:var(--sombra)}
.ng-bono.pausa{opacity:.7}.ng-bono b{display:block}.ng-bono small{display:block;color:var(--tenue);margin:2px 0 6px}
.ng-bono-h{width:54px;height:54px;border-radius:16px;background:var(--tinte);color:var(--teal);font-weight:800;font-size:18px;display:flex;align-items:center;justify-content:center;flex:none}
.ng-bono-a{display:flex;gap:6px;flex-wrap:wrap;width:100%}
.ng-ico{font-size:20px}
.ng-sw{position:relative;display:inline-block;width:46px;height:28px;flex:none;cursor:pointer}.ng-sw input{position:absolute;opacity:0;width:100%;height:100%;margin:0;cursor:pointer}
.ng-sw i{position:absolute;inset:0;background:#CFD8D3;border-radius:999px;transition:.2s}.ng-sw i:after{content:'';position:absolute;top:3px;left:3px;width:22px;height:22px;border-radius:50%;background:#fff;box-shadow:0 1px 3px rgba(0,0,0,.2);transition:.2s}
.ng-sw input:checked+i{background:var(--esmeralda)}.ng-sw input:checked+i:after{left:21px}.ng-sw input:disabled+i{opacity:.45}
.ng-sw input:focus-visible+i{outline:2px solid var(--noche);outline-offset:2px}
.ng-dispo{padding:6px 12px}.ng-dispo .ng-fila{border:0;border-bottom:1px solid var(--trazo);border-radius:0;box-shadow:none}.ng-dispo .ng-fila:last-child{border-bottom:0}
.ng-hora{width:56px;font-size:16px;flex:none}.ng-valle{color:var(--warn-fg)!important;font-weight:700}.ng-lock{font-size:18px}
.ng-ok{background:var(--ok-bg);color:var(--ok-fg);border-radius:14px;padding:12px 14px;font-weight:700;margin-top:12px}
.ng-rec{display:flex;flex-wrap:wrap;gap:6px 12px;align-items:center;background:var(--warn-bg);border-radius:16px;padding:14px 16px;margin-top:16px}
.ng-rec b{flex:1 1 240px}.ng-rec small{flex:1 1 100%;order:3;color:var(--warn-fg)}
.ng-form label{display:block;font-weight:700;font-size:13px;margin:12px 0 6px;text-align:left}.ng-form select,.ng-form input{width:100%;box-sizing:border-box}
.ng-form .chips{gap:6px}.ng-form .chip{padding:7px 11px;font-size:13px}.ng-form .err{color:var(--bad-fg);font-size:13px;margin-top:8px;text-align:left;min-height:1em}
.ng-cuota{display:flex;gap:8px;align-items:center;justify-content:space-between;padding:8px 0;border-top:1px solid var(--trazo);text-align:left}
.ng-cuota small{display:block;color:var(--tenue)}
.hm{display:grid;grid-template-columns:48px repeat(7,minmax(0,1fr));gap:3px;min-width:0}
.hm-d{text-align:center;font-size:12px;font-weight:800;color:var(--tenue)}.hm-h{font-size:12px;color:var(--tenue);display:flex;align-items:center}
.hm-c{height:20px;border-radius:4px;outline:none}.hm-c:hover,.hm-c:focus{box-shadow:0 0 0 2px var(--noche)}
.hm-ley{display:flex;align-items:center;gap:3px;justify-content:flex-end;margin-top:10px;font-size:12px;color:var(--tenue)}.hm-ley i{width:16px;height:12px;border-radius:3px;display:inline-block}.hm-ley span{margin:0 4px}
.ng-rep{display:flex;align-items:baseline;gap:10px}.ng-rep b{font-size:32px}.ng-rep span{color:#E0A100;font-size:18px}.ng-rep small{color:var(--tenue)}
.ng-resena{padding:8px 0;border-top:1px solid var(--trazo);font-size:14px}.ng-resena b{color:#E0A100}.ng-resena small{display:block;color:var(--tenue)}
.ng-tip{position:fixed;z-index:9999;pointer-events:none;background:var(--noche);color:#fff;font-size:12.5px;font-weight:700;padding:6px 10px;border-radius:8px;box-shadow:0 4px 14px rgba(0,0,0,.2);max-width:240px;display:none}
"""

# Escalas del mapa de calor y de las insignias de segmento (antes un
# `style='background:…'` por celda).
_ESCALAS = (
    ".hm-c.n0,.hm-ley i.n0{background:var(--gris)}"
    + "".join(f".hm-c.n{i},.hm-ley i.n{i}{{background:{c}}}" for i, c in enumerate(RAMPA) if i)
    + "".join(f".ng-badge.s-{k}{{background:{c}}}" for k, c in SEG_FONDO.items())
)

# ── Pantallas táctiles: todo lo tocable de estas páginas mide ≥ 44 px ──
# (Las celdas del mapa de calor de Ocupación quedan en 20 px: solo muestran un
# tooltip y "Ver como tabla" da la misma información; a 44 px el mapa se
# triplicaría de alto.)
_TACTIL = """
@media (pointer:coarse){
.anf-pag .anf-back,.anf-pag .volver-lnk{display:inline-flex;align-items:center;min-height:44px}
.anf-pag .edit-nav-it,.anf-pag .ng-tabs a,.anf-pag summary{display:flex;align-items:center;min-height:44px}
.anf-pag .ng-tabs a{padding-top:0;padding-bottom:0}
.anf-pag .ng-flecha{width:44px;height:44px}
.anf-pag .anf-hero .volver{display:inline-flex;align-items:center;justify-content:center;min-width:44px;min-height:44px}
.anf-pag button,.anf-pag label.btn,.anf-pag .chk,.anf-pag select,
.anf-pag input:not([type=checkbox]):not([type=radio]):not([type=range]):not([type=file]):not([type=hidden]){min-height:44px}
.anf-pag .modal-cab .cerrar{width:44px;height:44px;left:10px;top:10px}
.anf-pag .modal-pie .limpiar{min-height:44px}
.anf-pag .ng-sw::before{content:'';position:absolute;inset:-8px 0}
}
"""

CSS = _CAL + _MENU + _ANF + _NG + _ESCALAS + _TACTIL
