"""CSS de las vistas del modo anfitrión · Mis canchas (calendario unificado), Ingresos y el asistente Agregar local — web/anfitrion.py.

Va después del kit (`web/vista_anfitrion.py`). Solo tokens (`--azul`, `--anf-*`).
Todo bajo `.mc` (la vista) o `.mc-*` / `.wz-*` (piezas); el menú contextual del
turno (`.mc-menu`) y su fondo viven fuera del contenedor pero llevan prefijo.
"""

# Columnas del calendario: `.mc-nN` (N = días o canchas; sin variables CSS sueltas).
_NCOLS = "".join(f".mc-n{n} .mc-cal-cab,.mc-n{n} .mc-cal-cuerpo{{grid-template-columns:56px repeat({n},minmax(0,1fr))}}"
                 f".mc-cal.dia.mc-n{n}{{min-width:{56 + n * 130}px}}" for n in range(1, 17))

# Celular: el calendario muestra UNA columna (día o cancha) elegida con chips.
_COLS = ",".join(f".mc-cal[data-dia='{i}'] [data-col='{i}']" for i in range(16))

CSS = r"""
/* ═════════ MODO ANFITRIÓN · Mis canchas (calendario unificado, Frames 8-10) ═════════ */
.vmc .va-cab-acc .btn{white-space:nowrap}
.mc-lado{display:grid;grid-template-columns:minmax(0,280px) minmax(0,1fr);gap:16px;align-items:start}
.mc-der{min-width:0}
.mc-lat{position:sticky;top:84px;max-height:calc(100vh - 100px);overflow:auto}
.mc-loc{border-bottom:1px solid var(--anf-linea);padding-bottom:6px;margin-bottom:6px}
.mc-loc:last-of-type{border-bottom:0}
.mc-loc-cab{display:flex;align-items:center;gap:10px;padding:8px 6px;cursor:pointer;list-style:none;border-radius:10px;min-height:44px}
.mc-loc-cab::-webkit-details-marker{display:none}
.mc-loc-cab:hover{background:var(--anf-fondo)}
.mc-loc-cab:focus-visible{outline:3px solid var(--azul);outline-offset:1px}
.mc-loc-cab .va-ic{width:30px;height:30px;color:var(--azul)}
.mc-loc-cab .tx{flex:1;min-width:0;display:flex;flex-direction:column}
.mc-loc-cab .tx b{font-size:14.5px;line-height:1.25}
.mc-loc-cab .tx small{font-size:12px;color:var(--anf-tenue)}
.mc-loc-cab .tx small.ok{color:var(--ok-fg)}
.mc-chev{width:8px;height:8px;border-right:2px solid var(--anf-tenue);border-bottom:2px solid var(--anf-tenue);transform:rotate(45deg);margin:0 6px 4px 0;transition:transform var(--dur)}
.mc-loc[open] .mc-chev{transform:rotate(-135deg);margin-bottom:-2px}
.mc-loc .va-lat-it{margin-left:8px}
.mc-loc-acc{display:flex;gap:16px;padding:2px 12px 4px 46px}
.mc-loc-acc a{font-size:13px;font-weight:700;color:var(--azul);text-decoration:none;min-height:36px;display:inline-flex;align-items:center}
.mc-loc-acc a:hover{text-decoration:underline}
.vmc .btn.mc-agr,.mc-agr-m{display:flex;justify-content:center;margin:12px 4px 4px;width:calc(100% - 8px)}
.mc-agr-m{flex-direction:column;margin:12px 4px 4px}
.mc-agr-m>summary{list-style:none;cursor:pointer;margin:0;width:100%}
.mc-agr-m>summary::-webkit-details-marker{display:none}
.mc-agr-lista{display:flex;flex-direction:column;border:1px solid var(--anf-borde);border-radius:12px;margin-top:8px;overflow:hidden}
.mc-agr-lista a{padding:12px 14px;color:var(--anf-texto);text-decoration:none;font-weight:700;font-size:14px;border-top:1px solid var(--anf-linea);min-height:44px}
.mc-agr-lista a:first-child{border-top:0}.mc-agr-lista a:hover{background:var(--anf-fondo)}
.mc-ficha{display:flex;align-items:center;gap:16px;flex-wrap:wrap;padding:16px 20px}
.mc-ficha-f{width:56px;height:56px;border-radius:12px;object-fit:cover;flex:none;background:var(--azul-tinte);display:inline-flex;align-items:center;justify-content:center}
.mc-ficha-f .va-ic{width:44px;height:44px;color:var(--azul)}
.mc-ficha-t{flex:1 1 260px;min-width:0}
.mc-ficha-t h2{display:flex;align-items:center;gap:10px;flex-wrap:wrap;font-size:20px}
.mc-ficha-t p{margin:4px 0 0;color:var(--anf-tenue);font-size:13.5px}
.mc-ficha-acc{display:flex;gap:8px;flex-wrap:wrap}
.mc-calp{padding:14px 0 0;overflow:hidden}
.mc-barra{display:flex;align-items:center;gap:12px 16px;flex-wrap:wrap;padding:0 16px 12px}
.mc-nav{display:flex;align-items:center;gap:6px}
.mc-nb{min-width:44px;min-height:40px;padding:0 12px;border:1px solid var(--anf-borde);border-radius:10px;background:#fff;color:var(--anf-texto);
  font-weight:700;font-size:15px;display:inline-flex;align-items:center;justify-content:center;text-decoration:none}
.mc-nb:hover{background:var(--anf-fondo)}.mc-nb:focus-visible{outline:3px solid var(--azul);outline-offset:1px}
.mc-rango{font-size:16px;margin-left:8px;white-space:nowrap}
.mc-ley{display:flex;gap:14px;flex-wrap:wrap;margin-left:auto;font-size:13px;color:var(--anf-tenue)}
.mc-ley span{display:inline-flex;align-items:center;gap:6px}
.mc-ley i{width:4px;height:14px;border-radius:2px;background:var(--anf-verde)}
.mc-ley i.ef{background:var(--anf-naranja)}.mc-ley i.bl{background:var(--anf-tenue)}
.mc-dias{display:none;gap:8px;overflow-x:auto;padding:0 16px 10px;scrollbar-width:none}
.mc-dias::-webkit-scrollbar{display:none}
.mc-dia{flex:none;min-height:40px;padding:0 14px;border-radius:999px;border:1px solid var(--anf-borde);background:#fff;color:var(--anf-texto);font:inherit;font-size:14px;font-weight:700;cursor:pointer}
.mc-dia.sel{background:var(--azul);border-color:var(--azul);color:#fff}
.mc-scroll{overflow-x:auto;border-top:1px solid var(--anf-borde)}
.mc-cal-cab,.mc-cal-cuerpo{display:grid;grid-template-columns:56px minmax(0,1fr)}
⟦NCOLS⟧
.mc-cal-cab{position:sticky;top:0;background:#fff;z-index:3;border-bottom:1px solid var(--anf-borde)}
.mc-ch{padding:10px 4px;text-align:center;display:flex;flex-direction:column;align-items:center;gap:2px;font-size:13px;color:var(--anf-tenue);min-width:0}
.mc-ch b{font-size:14px;color:var(--anf-texto);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:100%}
.mc-ch.hoy span{color:var(--azul);font-weight:700}
.mc-ch.hoy b{background:var(--azul);color:#fff;border-radius:999px;padding:1px 10px}
.mc-ch.sel b{color:var(--azul-osc)}
.mc-ch small{font-size:12px;font-weight:700;color:var(--bad-fg)}
.mc-horas{position:relative;border-right:1px solid var(--anf-linea)}
.mc-horas span{position:absolute;right:8px;transform:translateY(-50%);font-size:12px;color:var(--anf-tenue);white-space:nowrap}
.mc-horas span:first-child{transform:none}
.mc-col{position:relative;border-left:1px solid var(--anf-linea);min-width:0;
  background-image:repeating-linear-gradient(to bottom,var(--anf-linea) 0,var(--anf-linea) 1px,transparent 1px,transparent 46px)}
.mc-col.hoy{background-color:var(--azul-suave)}
.mc-col.cerr{background-color:var(--anf-fondo)}
.mc-fuera{position:absolute;left:0;right:0;background:repeating-linear-gradient(135deg,var(--anf-linea) 0 6px,transparent 6px 12px);pointer-events:none}
.mc-pasado{position:absolute;left:0;right:0;top:0;background:rgba(27,33,64,.035);pointer-events:none}
.mc-ahora{position:absolute;left:0;right:0;height:2px;background:var(--anf-rojo);z-index:2;pointer-events:none}
.mc-ahora:before{content:"";position:absolute;left:-4px;top:-4px;width:10px;height:10px;border-radius:50%;background:var(--anf-rojo)}
.mc-cerr{position:absolute;left:4px;right:4px;top:38%;text-align:center;font-weight:700;font-size:13px;color:var(--anf-texto);display:flex;flex-direction:column;gap:2px}
.mc-cerr small{font-size:12px;font-weight:500;color:var(--anf-tenue)}
.mc-ev{position:absolute;left:4px;right:4px;border:0;border-radius:6px;padding:4px 8px;font:inherit;font-size:12.5px;line-height:1.25;text-align:left;cursor:pointer;
  overflow:hidden;white-space:nowrap;text-overflow:ellipsis;display:block;color:var(--anf-texto);background:transparent;z-index:1}
.mc-ev:focus-visible{outline:3px solid var(--azul);outline-offset:1px;z-index:4}
.mc-ev.res{border-left:3px solid var(--anf-verde);background:var(--ok-bg);color:var(--ok-fg);font-weight:700}
.mc-ev.res span{font-weight:700}
.mc-ev.res.ef{border-left-color:var(--anf-naranja);background:var(--warn-bg);color:var(--warn-fg)}
.mc-ev.res.ns{border-left-color:var(--anf-tenue);background:var(--anf-linea);color:var(--anf-tenue);text-decoration:line-through}
.mc-ev.res.pas{opacity:.7}
.mc-ev.bl{border-left:3px solid var(--anf-tenue);background:repeating-linear-gradient(135deg,var(--anf-linea) 0 6px,#fff 6px 12px);color:var(--anf-tenue);font-weight:700}
.mc-ev.bl:disabled{cursor:default;opacity:.6}
.mc-ev.li span{display:none;color:var(--azul);font-weight:700}
.mc-ev.li:hover,.mc-ev.li:focus-visible,.mc-ev.li.act{background:#fff;outline:2px dashed var(--azul);outline-offset:-2px}
.mc-ev.li:hover span,.mc-ev.li:focus-visible span,.mc-ev.li.act span{display:inline}
.mc-ev.act{box-shadow:0 0 0 2px var(--azul)}
@media (hover:none){.mc-ev.li span{display:inline;color:var(--azul-claro);font-weight:500}}
.mc-pie{display:flex;justify-content:space-between;align-items:center;gap:8px 16px;flex-wrap:wrap;margin:12px 4px 0;font-size:13.5px;color:var(--anf-tenue)}
.mc-pie p{margin:0}
.mc-ical,.mc-av-ver{background:none;border:0;padding:0;font:inherit;font-size:14px;font-weight:700;color:var(--azul);cursor:pointer;min-height:44px;display:inline-flex;align-items:center}
.mc-ical:hover,.mc-av-ver:hover{text-decoration:underline}
.mc-ical:focus-visible,.mc-av-ver:focus-visible{outline:3px solid var(--azul);outline-offset:2px}
.mc-av-sub{color:var(--anf-tenue)}
.mc-av-det{background:#fff;border:1px solid var(--anf-borde);border-radius:12px;padding:4px 16px 14px;margin:-8px 0 16px}
.mc-ical-c{display:flex;gap:8px;margin-top:10px}.mc-ical-c input{flex:1;min-width:0;font-size:13px}
/* menú contextual del turno (popover; hoja inferior en el celular) */
.mc-menu{position:absolute;z-index:60;width:300px;max-width:calc(100vw - 16px);background:#fff;border:1px solid var(--anf-borde);border-radius:14px;
  box-shadow:0 14px 40px rgba(20,33,90,.18);overflow:hidden;color:var(--anf-texto)}
.mc-menu-cab{padding:14px 16px 10px;border-bottom:1px solid var(--anf-linea);display:flex;flex-direction:column;gap:2px}
.mc-menu-cab b{font-size:15px}.mc-menu-cab small{font-size:12.5px;color:var(--anf-tenue)}
.mc-menu-its{padding:6px;display:flex;flex-direction:column;gap:2px}
.mc-mi{display:flex;align-items:center;gap:12px;width:100%;min-height:44px;padding:6px 10px;border:0;border-radius:10px;background:transparent;font:inherit;
  font-size:14.5px;font-weight:700;color:var(--anf-texto);text-align:left;cursor:pointer;text-decoration:none}
.mc-mi:hover,.mc-mi:focus-visible{background:var(--azul-tinte);outline:none}
.mc-mi.ok{color:var(--ok-fg)}.mc-mi.peligro{color:var(--bad-fg)}
.mc-mi-ic{width:30px;height:30px;border-radius:8px;background:var(--azul-tinte);color:var(--azul);display:inline-flex;align-items:center;justify-content:center;flex:none}
.mc-mi-ic.ok{background:var(--ok-bg);color:var(--ok-fg)}.mc-mi-ic.peligro{background:var(--bad-bg);color:var(--bad-fg)}
.mc-menu-pro{margin:6px 10px;font-size:13px;color:var(--warn-fg)}
.mc-fondo{position:fixed;inset:0;background:rgba(20,24,40,.38);z-index:59}
.mc-menu.hoja{position:fixed;left:0;right:0;bottom:0;top:auto;width:auto;max-width:none;border-radius:20px 20px 0 0;padding-bottom:env(safe-area-inset-bottom)}
.mc-menu.hoja .mc-menu-cab:before{content:"";width:40px;height:4px;border-radius:2px;background:var(--anf-borde);align-self:center;margin:-4px 0 8px}
.mc-modal .modal-cuerpo{padding:18px 24px}
.mc-modal .chk{margin-top:14px}.mc-nota{font-size:12.5px;margin-top:10px}
.mc-modal #calSub{margin:0 0 6px}
.mc-quien{min-width:0}.mc-pre{margin-left:auto;white-space:nowrap}
.mc-estado{margin-top:12px}.mc-err{margin-top:12px}
.vmc .btn.peligro{background:#fff;color:var(--anf-rojo);border:1px solid var(--bad-bg)}
/* listas (Ingresos, Reservas) y estados vacíos */
.vmc .mc-h2{font-size:20px;margin:24px 0 8px;color:var(--anf-texto)}.mc-h2 small{color:var(--anf-tenue);font-weight:500}
.mc-vacio{background:var(--azul-tinte);color:var(--anf-tenue);border-radius:12px;padding:16px;text-align:center;font-size:14px;margin:0}
.mc-otra{display:block;font-size:13px;color:var(--anf-tenue);font-weight:600;margin-top:2px}
.mc-fil{margin:4px 0 4px}
.mc-mov{display:flex;justify-content:space-between;gap:12px;padding:12px 0;border-top:1px solid var(--anf-linea)}
.mc-mov:first-child{border-top:0;padding-top:0}
.mc-mov-t{min-width:0}.mc-mov-t b{display:block;font-size:14.5px}.mc-mov small{display:block;font-size:12.5px;color:var(--anf-tenue)}
.mc-mov-m{text-align:right;flex:none;max-width:55%}.mc-mov-m b{font-size:15px;white-space:nowrap}.mc-mov-m b.ok{color:var(--ok-fg)}
.mc-cc h2{margin-bottom:12px}.mc-cc-acc{margin-top:12px}.mc-docnum{margin-top:6px}
.mc-ing .cc-com,.mc-ing .panel{background:#fff;border:1px solid var(--anf-borde);border-radius:16px;box-shadow:none;padding:20px 22px;margin:0 0 16px}
.mc-ing .panel h2,.mc-ing .cc-com h2{font-size:18px;margin:0}
.mc-ing .kpis{gap:12px}.mc-ing .kpi{border:1px solid var(--anf-borde);box-shadow:none;border-radius:14px}
.mc-vacio-acc{display:flex;gap:10px;flex-wrap:wrap;justify-content:center}
.mc-nota-c{text-align:center;font-size:13px;color:var(--anf-tenue);margin:8px 0 0}
@media(max-width:1000px){.mc-ley{margin-left:0}}
@media(max-width:860px){
  .mc-lado{grid-template-columns:minmax(0,1fr)}.mc-lat{position:static;max-height:none}
}
@media(max-width:700px){
  .mc-dias{display:flex}
  .mc-cal .mc-cal-cab,.mc-cal .mc-cal-cuerpo{grid-template-columns:48px minmax(0,1fr)}
  .mc-calp .mc-scroll .mc-cal.dia{min-width:0}
  .mc-cal [data-col]{display:none}
  ⟦COLS⟧{display:flex}
  .mc-cal .mc-col[data-col]{display:none}
  ⟦COLSB⟧{display:block}
  .mc-ev{font-size:13px}
  .mc-rango{margin-left:2px;font-size:15px}
}
@media(max-width:600px){
  .mc-ficha{padding:14px}.mc-ficha-acc{width:100%}.mc-ficha-acc .btn{flex:1 1 auto}
  .vmc .va-cab-acc .btn{flex:1 1 auto}
  .mc-barra{padding:0 12px 10px}.mc-dias{padding:0 12px 10px}
  .mc-mov{flex-direction:column;gap:4px}.mc-mov-m{text-align:left;max-width:none}
}
/* ═════════ Agregar local · asistente de 4 pasos (Frames 11-13) ═════════ */
.vmc .vh{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
.wz-pag .va-cab{margin-bottom:4px}
.wz-miga{margin:0 0 20px;font-size:13.5px;color:var(--anf-tenue)}.wz-miga a{color:var(--anf-tenue);text-decoration:none}.wz-miga a:hover{text-decoration:underline}
.wz{display:grid;grid-template-columns:minmax(0,240px) minmax(0,1fr) minmax(0,300px);gap:20px;align-items:start}
.wz-izq,.wz-der{position:sticky;top:84px;display:flex;flex-direction:column;gap:16px;min-width:0}
.wz-eti{display:block;font-size:12px;font-weight:700;letter-spacing:.05em;text-transform:uppercase;color:var(--anf-tenue)}
.wz-pasos{padding:16px 12px;margin:0}.wz-pasos .wz-eti{padding:0 6px 8px}
.wz-pasos ol{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:2px;position:relative}
.wz-p{display:flex;gap:12px;align-items:flex-start;width:100%;padding:10px 8px;border:0;border-radius:12px;background:none;font:inherit;text-align:left;cursor:pointer;color:var(--anf-texto);min-height:44px}
.wz-p:hover{background:var(--anf-fondo)}.wz-p:focus-visible{outline:3px solid var(--azul);outline-offset:1px}
.wz-p.act{background:var(--azul-tinte)}
.wz-n{width:28px;height:28px;border-radius:50%;border:1.5px solid var(--anf-borde);display:inline-flex;align-items:center;justify-content:center;font-size:13px;font-weight:700;color:var(--anf-tenue);flex:none;background:#fff}
.wz-p.act .wz-n{background:var(--azul);border-color:var(--azul);color:#fff}
.wz-p.hecho .wz-n{background:var(--anf-verde);border-color:var(--anf-verde);color:transparent;position:relative}
.wz-p.hecho .wz-n:after{content:"";position:absolute;width:6px;height:11px;border:solid #fff;border-width:0 2px 2px 0;transform:rotate(45deg);top:6px;left:10px}
.wz-pt{display:flex;flex-direction:column;min-width:0}.wz-pt b{font-size:14.5px}.wz-p.act .wz-pt b{color:var(--azul-osc)}
.wz-pt small{font-size:12.5px;color:var(--anf-tenue)}
.wz-que{background:var(--azul-tinte);border-radius:16px;padding:16px 18px;font-size:13.5px}
.wz-que b{font-size:14.5px}.wz-que p{margin:6px 0 0;color:var(--anf-texto);line-height:1.5}
.wz-centro{min-width:0}
.wz-centro .va-panel h2{font-size:18px}
.wz-centro label{margin-top:14px}
.wz-txt{font-size:13.5px;color:var(--anf-tenue);margin:4px 0 0}
.wz-fila{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-top:10px}
.wz-geo{grid-template-columns:repeat(3,minmax(0,1fr))}
.wz-mapa{height:260px;border-radius:12px;margin-top:8px}
.wz-subir{display:flex;flex-direction:column;align-items:center;gap:4px;margin-top:14px;padding:22px 16px;border:2px dashed var(--azul-claro);border-radius:14px;
  background:var(--azul-suave);color:var(--azul);text-align:center;cursor:pointer;min-height:44px}
.wz-subir:hover{background:var(--azul-tinte)}.wz-subir b{font-size:14.5px}.wz-subir small{font-size:12.5px;color:var(--anf-tenue)}
.wz-subir:focus-within{box-shadow:var(--foco)}
#fotosCont{display:inline-block;margin:10px 0 0}
.wz-sup{margin-top:10px}.wz-sup b{font-size:13.5px}
.wz-wa{max-width:300px}.wz-doc{max-width:220px}
.wz-canchas{display:flex;flex-direction:column;gap:8px}
.wz-ca{display:flex;gap:12px;align-items:center;padding:10px 12px;border:1px solid var(--anf-borde);border-radius:12px}
.wz-ca-ic{width:28px;height:28px;border-radius:50%;background:var(--azul-tinte);flex:none}
.wz-ca b{display:block;font-size:14.5px}.wz-ca small{font-size:12.5px;color:var(--anf-tenue)}
.wz-resumen{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(200px,100%),1fr));gap:10px}
.wz-resumen div{background:var(--anf-fondo);border-radius:12px;padding:10px 12px;min-width:0}
.wz-resumen small{display:block;font-size:12px;color:var(--anf-tenue);font-weight:700;text-transform:uppercase;letter-spacing:.04em}
.wz-resumen b{font-size:14px;overflow-wrap:anywhere}
.wz-nav{display:flex;align-items:center;gap:10px;margin-top:4px}.wz-gap{flex:1}
.wz-nav .btn[hidden]{display:none}
.wz-msg{font-size:13.5px;color:var(--anf-tenue);margin:12px 0 0}.wz-msg.err{color:var(--bad-fg);font-weight:700}
.wz-prev{background:#fff;border:1px solid var(--anf-borde);border-radius:16px;overflow:hidden}
.wz-prev-f{position:relative;aspect-ratio:16/10;background:var(--azul-tinte);display:flex;align-items:center;justify-content:center;color:var(--azul-claro)}
.wz-prev-f img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}
.wz-prev-est{position:absolute;top:10px;right:10px;background:var(--warn-bg);color:var(--warn-fg);font-size:12px;font-weight:700;border-radius:999px;padding:4px 10px}
.wz-prev-n{position:absolute;left:10px;bottom:10px;background:rgba(27,33,64,.72);color:#fff;font-size:12px;font-weight:700;border-radius:999px;padding:3px 10px}
.wz-prev-c{padding:14px 16px;display:flex;flex-direction:column;gap:4px}
.wz-prev-c>b{font-size:16px;overflow-wrap:anywhere}.wz-prev-c>small{font-size:13px;color:var(--anf-tenue)}
.wz-prev-s{display:flex;gap:6px;flex-wrap:wrap;margin-top:6px}
.wz-prev-s span{background:var(--anf-fondo);color:var(--anf-tenue);font-size:12px;font-weight:700;border-radius:999px;padding:3px 10px}
.wz-prev-pie{display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;border-top:1px solid var(--anf-linea);margin-top:8px;padding-top:10px;font-size:13.5px}
.wz-prev-pie span{color:var(--anf-tenue);min-width:0}.wz-prev-pie b{color:var(--ok-fg);white-space:nowrap}
.wz-check{margin:0}.wz-check>b{font-size:14.5px}
.wz-check ul{list-style:none;margin:10px 0 0;padding:0;display:flex;flex-direction:column;gap:8px}
.wz-check li{display:flex;align-items:center;gap:10px;font-size:13.5px;color:var(--anf-tenue)}
.wz-check li i{width:20px;height:20px;border-radius:50%;border:1.5px solid var(--anf-borde);flex:none;position:relative;background:#fff}
.wz-check li.ok{color:var(--anf-texto)}
.wz-check li.ok i{background:var(--anf-verde);border-color:var(--anf-verde)}
.wz-check li.ok i:after{content:"";position:absolute;width:5px;height:9px;border:solid #fff;border-width:0 2px 2px 0;transform:rotate(45deg);top:3px;left:6px}
/* editores (cancha, local, agregar cancha) con el kit */
.vmc .edit-grid{margin-top:0}
.vmc .edit-sec{scroll-margin-top:90px}
.vmc .edit-form>.va-panel{margin-bottom:0}
@media(max-width:1100px){.wz{grid-template-columns:minmax(0,220px) minmax(0,1fr)}.wz-der{grid-column:1/-1;position:static;display:grid;grid-template-columns:repeat(auto-fit,minmax(min(280px,100%),1fr))}}
@media(max-width:760px){
  .wz{grid-template-columns:minmax(0,1fr)}.wz-izq{position:static}
  .wz-pasos ol{flex-direction:row;overflow-x:auto;gap:6px}.wz-pasos li{flex:none}.wz-p{padding:8px}.wz-pt small{display:none}
  .wz-que{display:none}.wz-geo{grid-template-columns:minmax(0,1fr)}
  .wz-nav .btn{flex:1 1 auto}.wz-gap{display:none}
}
""".replace("⟦NCOLS⟧", _NCOLS).replace("⟦COLS⟧", _COLS).replace("⟦COLSB⟧", ",".join(f".mc-cal[data-dia='{i}'] .mc-col[data-col='{i}']" for i in range(16)))
