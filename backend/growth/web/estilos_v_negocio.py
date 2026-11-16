"""CSS de las vistas del modo anfitrión · Negocio: Reportes, Ocupación, Caja, Clientes, Cancelaciones, Bonos, Disponibilidad, Reservas fijas, Cobros de academia — web/anfitrion_negocio.py.

Va después del kit (`web/vista_anfitrion.py`). Solo tokens (`--azul`, `--anf-*`).
Todas las clases empiezan con `vn-` (o `ag-` en Agregar cuota) para no pisar
otras vistas; el color del mapa de calor reusa la rampa `hm-c n<nivel>` de
`web/estilos_anfitrion.py`.
"""

CSS = r"""
/* ═════════ MODO ANFITRIÓN · Negocio (diseñador, 16-nov-2026) ═════════ */
.vn .va-ic svg{flex:none}
.vn-c-azul{background:var(--azul)}.vn-c-verde{background:var(--anf-verde)}.vn-c-naranja{background:var(--anf-naranja)}
.vn-c-rojo{background:var(--anf-rojo)}.vn-c-morado{background:var(--anf-morado)}.vn-c-tinta{background:var(--anf-texto)}
.vn-c-claro{background:var(--azul-tinte);color:var(--azul)!important}
.vn-tenue{color:var(--anf-tenue);font-size:14px;margin:0}
.vn-nota{color:var(--anf-tenue);font-size:13px;margin:12px 0 0;display:flex;align-items:flex-start;gap:6px}.vn-nota svg{flex:none;margin-top:1px}
.vn-nota a{color:var(--azul);font-weight:700}
.vn-sec{font-size:12px!important;letter-spacing:.06em;text-transform:uppercase;color:var(--anf-tenue)!important;margin:24px 0 10px!important}
.vn-rojo{color:var(--anf-rojo)}
.vn .vh{position:absolute!important;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap;margin:0;padding:0}
.vn .btn svg{vertical-align:-3px;margin-right:4px}
.vn-mini{padding:8px 14px!important;font-size:14px!important;min-height:40px!important;display:inline-flex!important;align-items:center;gap:4px;white-space:nowrap}
.vn-mini svg{margin-right:0!important}
/* pestañas subrayadas de Reportes */
.vn-tabs{display:flex;gap:28px;border-bottom:1px solid var(--anf-borde);margin:-6px 0 20px;overflow-x:auto;scrollbar-width:none}
.vn-tabs::-webkit-scrollbar{display:none}
.vn-tabs a{display:inline-flex;align-items:center;gap:7px;padding:10px 0 11px;min-height:44px;font-weight:700;font-size:15px;color:var(--anf-tenue);
  text-decoration:none;border-bottom:3px solid transparent;white-space:nowrap;margin-bottom:-1px}
.vn-tabs a:hover{color:var(--anf-texto)}
.vn-tabs a.sel{color:var(--azul);border-bottom-color:var(--azul)}
.vn-mon a{padding:8px 12px}
/* selector (cancha / local / academia) */
.vn-sel{display:inline-flex;align-items:center;gap:8px;background:#fff;border:1px solid var(--anf-borde);border-radius:12px;padding:0 4px 0 12px;
  min-height:44px;color:var(--azul);max-width:100%;margin:0}
.vn-sel select{border:0;background:transparent;font:inherit;font-weight:700;font-size:14.5px;color:var(--anf-texto);padding:10px 8px;min-height:42px;
  max-width:300px;width:auto;cursor:pointer}
.vn-sel select:focus{outline:none}.vn-sel:focus-within{box-shadow:var(--foco)}
.vn-sel-local{color:var(--anf-tenue);font-size:14px}.vn-sel-local label{font-weight:500}.vn-sel-local b{color:var(--anf-texto);padding-right:12px}
.vn-sel-mov{display:none}
.vn-filtros{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-bottom:16px}
/* ── Reportes · Resumen ── */
.vn-dos{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,368px);gap:16px;align-items:stretch;margin-bottom:8px}
.vn-dos>.va-panel{margin-bottom:0}
.vn-col{display:grid;gap:14px;grid-auto-rows:1fr}
.vn-col .va-kpi{justify-content:space-between}
.vn-ing{position:relative;display:flex;flex-direction:column}
.vn-ing-cab{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap}
.vn-ing-t{display:flex;align-items:center;gap:12px}.vn-ing-t h2{font-size:15px!important;font-weight:600!important;color:var(--anf-tenue)!important}
.vn-ing-v{display:block;font-size:36px;line-height:1.1;color:var(--azul);margin:10px 0 6px;letter-spacing:-.01em}
.vn-graf{position:relative;height:230px;margin-top:22px}
.vn-guias{position:absolute;left:0;right:0;top:22px;bottom:26px}
.vn-guias i{position:absolute;left:0;right:0;border-top:1px solid var(--anf-linea)}
.vn-barras{position:absolute;inset:0;display:flex;align-items:stretch;gap:6px}
.vn-bar{flex:1;min-width:0;display:flex;flex-direction:column;align-items:center;outline:none;cursor:default}
.vn-bar-c{flex:1;width:100%;display:flex;flex-direction:column;justify-content:flex-end;align-items:center;padding-top:22px;min-height:0}
.vn-bar-c small{font-size:12px;font-weight:700;color:var(--anf-texto);white-space:nowrap;margin-bottom:4px}
.vn-bar i{display:block;width:100%;max-width:46px;background:var(--azul);border-radius:5px 5px 0 0}
.vn-bar.hoy i{background:var(--azul-claro)}
.vn-bar span{height:26px;line-height:26px;font-size:12px;color:var(--anf-tenue);white-space:nowrap;overflow:visible}
.vn-bar.hoy span{color:var(--anf-texto);font-weight:700}
.vn-bar:hover i,.vn-bar:focus i{filter:brightness(.92)}.vn-bar:focus-visible{box-shadow:var(--foco);border-radius:6px}
.vn-tabla{font-size:13px}
.vn-tabla>summary{list-style:none;cursor:pointer;color:var(--azul);font-weight:700;font-size:13.5px;display:inline-flex;align-items:center;min-height:32px}
.vn-tabla>summary::-webkit-details-marker{display:none}
.vn-ing .vn-tabla>summary{position:absolute;right:22px;top:96px}
.vn-tabla[open]{margin-top:10px}.vn-tabla table{margin-top:6px}
.vn-mas-g{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(260px,100%),1fr));gap:16px}
.vn-mas{display:flex;align-items:center;gap:14px;background:#fff;border:1px solid var(--anf-borde);border-radius:16px;padding:18px;text-decoration:none;color:var(--anf-texto);min-height:76px}
.vn-mas span:not(.va-ic){flex:1;min-width:0;display:flex;flex-direction:column}.vn-mas b{font-size:15.5px}.vn-mas small{font-size:13px;color:var(--anf-tenue)}
.vn-mas i{font-style:normal;color:var(--anf-tenue);font-size:22px}
.vn-mas:hover{border-color:var(--azul-claro)}.vn-mas:hover b{color:var(--azul)}
/* ── Reportes · Cobros ── */
.vn-k5 .va-kpis{grid-template-columns:repeat(auto-fit,minmax(min(190px,100%),1fr))}
.vn-rango{display:flex;align-items:flex-end;gap:10px;flex-wrap:wrap;margin:0}
.vn-rango label{display:flex;flex-direction:column;gap:4px;font-size:12.5px;font-weight:700;color:var(--anf-tenue)}
.vn-rango input{border:1px solid var(--anf-borde);border-radius:10px;padding:9px 10px;font:inherit;font-size:14px;min-height:42px;background:#fff}
.vn-rango .btn{min-height:42px;padding:9px 14px}
.vn-rango-t{margin:-6px 0 14px}
.vn-rc{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:12px 0;border-bottom:1px solid var(--anf-linea)}
.vn-rc small{display:block;color:var(--anf-tenue);font-size:13px}.vn-rc span{font-weight:800;white-space:nowrap}
.vn-rc.tot{border-bottom:0;font-size:16px}.vn-rc.tot span{color:var(--azul);font-size:18px}
.vn-local{padding:12px 0;border-bottom:1px solid var(--anf-linea)}.vn-local:last-child{border-bottom:0}
.vn-local-h{display:flex;justify-content:space-between;gap:10px;margin-bottom:6px}.vn-local-h span{font-weight:800}
.vn-hb{padding:6px 0}.vn-hb-t{display:flex;align-items:baseline;gap:8px;font-size:14px}
.vn-hb-t b{font-weight:700}.vn-hb-t small{color:var(--anf-tenue);font-size:12.5px}.vn-hb-t span{margin-left:auto;font-weight:700;white-space:nowrap}
.vn-hb-p{height:8px;border-radius:99px;background:var(--anf-linea);margin-top:6px;overflow:hidden}
.vn-hb-p i{display:block;height:100%;border-radius:99px;background:var(--azul)}
/* ── Ocupación ── */
.vn-hm-p .va-panel-cab{align-items:center}
.vn-hm-w{overflow-x:auto;padding-bottom:4px}
.vn-hm{display:grid;gap:5px;min-width:560px}
.vn-hm-h{font-size:12px;font-weight:700;color:var(--anf-tenue);text-align:center;align-self:end}
.vn-hm-d{font-size:13px;font-weight:700;color:var(--anf-texto);display:flex;align-items:center}
.vn-hm-c{height:30px!important;border-radius:6px!important}
.vn-hm-ley{display:flex;align-items:center;gap:4px;font-size:12px;color:var(--anf-tenue)}
.vn-hm-ley i{display:inline-block;width:16px;height:12px!important;border-radius:3px!important}.vn-hm-ley span{margin:0 4px}
.vn-sugs{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(340px,100%),1fr));gap:16px;margin-bottom:16px}
.vn-sug{display:flex;align-items:center;gap:14px;background:#fff;border:1px solid var(--anf-borde);border-radius:16px;padding:16px 18px;min-width:0}
.vn-sug.punta .va-ic{background:var(--ok-bg);color:var(--anf-verde)}.vn-sug.valle .va-ic{background:var(--warn-bg);color:var(--warn-fg)}
.vn-sug-t{flex:1;min-width:0}.vn-sug-t b{display:block;font-size:15px}.vn-sug-t small{color:var(--anf-tenue);font-size:13px}
.vn-sug a{font-weight:700;font-size:14px;color:var(--azul);text-decoration:none;white-space:nowrap;min-height:44px;display:inline-flex;align-items:center}
.vn-rep{display:flex;align-items:baseline;gap:10px}.vn-rep b{font-size:32px}.vn-rep span{color:var(--warn-fg);font-size:18px}
.vn-rep small{color:var(--anf-tenue)}
.vn-resena{padding:8px 0;border-top:1px solid var(--anf-linea);font-size:14px}.vn-resena b{color:var(--warn-fg)}
.vn-resena small{display:block;color:var(--anf-tenue)}
/* ── Caja del día ── */
.vn-dia{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.vn-flecha{width:44px;height:44px;border-radius:10px;border:1px solid var(--anf-borde);background:#fff;display:inline-flex;align-items:center;
  justify-content:center;color:var(--anf-texto);text-decoration:none;font-size:20px;font-weight:700;flex:none}
.vn-flecha:hover{border-color:var(--azul-claro);color:var(--azul)}
.vn-fecha{position:relative;display:inline-flex;margin:0}
.vn-fecha-t{display:inline-flex;align-items:center;gap:8px;background:#fff;border:1px solid var(--anf-borde);border-radius:10px;padding:0 14px;
  min-height:44px;font-weight:700;font-size:14px;color:var(--anf-texto);white-space:nowrap}
.vn-fecha-t svg{color:var(--azul)}
.vn-fecha input{position:absolute;inset:0;opacity:0;width:100%;height:100%;cursor:pointer;border:0;padding:0}
.vn-fecha:focus-within .vn-fecha-t{box-shadow:var(--foco)}
.vn-hoy{min-height:44px!important;padding:10px 14px!important}
.vn-lista{display:flex;flex-direction:column}
.vn-fila{display:flex;align-items:center;gap:14px;padding:14px 0;border-bottom:1px solid var(--anf-linea);text-decoration:none;color:var(--anf-texto);min-width:0}
.vn-fila:last-child{border-bottom:0}
.vn-fila .va-ic{width:34px;height:34px}
.vn-fila-t{flex:1;min-width:0;display:flex;flex-direction:column}
.vn-fila-t b{font-size:15px}.vn-fila-t small{color:var(--anf-tenue);font-size:13px}
.vn-sena{color:var(--warn-fg)!important;font-weight:700}
.vn-monto{font-size:16px;white-space:nowrap}
.vn-fila-a{display:flex;gap:8px;flex:none}
.vn-ver-todas{display:block;text-align:center;font-weight:700;font-size:14px;color:var(--azul);text-decoration:none;padding:14px 0 2px;border-top:1px solid var(--anf-linea)}
.vn-medio{display:flex;align-items:center;gap:12px;padding:8px 0}
.vn-medio .va-ic{width:32px;height:32px}
.vn-medio-t{flex:1;min-width:0}.vn-medio-t>div:first-child{display:flex;justify-content:space-between;gap:10px;font-size:14px}
.vn-medio-t span{font-weight:700;color:var(--azul)}
.vn-medio-tot{display:flex;justify-content:space-between;align-items:baseline;border-top:1px solid var(--anf-linea);margin-top:8px;padding-top:12px}
.vn-medio-tot span{font-size:13px;color:var(--anf-tenue);font-weight:700}.vn-medio-tot b{font-size:17px}
.vn-cierre .vn-arqueo{display:flex;gap:12px;align-items:flex-start}
.vn-arqueo b{display:block;font-size:15.5px}.vn-arqueo small{color:var(--anf-tenue);font-size:13px}
.vn-arqueo-a{display:flex;flex-direction:column;gap:8px;margin-top:14px}.vn-arqueo-a .btn{width:100%}
.vn-cierres{margin-top:14px;border-top:1px solid var(--anf-linea);padding-top:6px}
.vn-cierres>summary{cursor:pointer;font-weight:700;font-size:14px;color:var(--azul);min-height:44px;display:flex;align-items:center}
.vn-hist .vn-fila-t b{font-size:14px}.vn-hist .vn-monto{font-size:14.5px}
/* ── Base de clientes ── */
.vn-buscar{display:flex;align-items:center;gap:8px;background:#fff;border:1px solid var(--anf-borde);border-radius:12px;padding:0 14px;
  color:var(--anf-tenue);flex:0 1 340px;min-width:0}
.vn-buscar input{border:0;background:transparent;font:inherit;font-size:14.5px;min-height:44px;flex:1;min-width:0;width:auto}
.vn-buscar input:focus{outline:none}.vn-buscar:focus-within{box-shadow:var(--foco)}
.vn-chips{display:flex;gap:8px;flex-wrap:wrap}
.vn-chip{display:inline-flex;align-items:center;min-height:40px;padding:8px 14px;border-radius:999px;background:#fff;border:1px solid var(--anf-borde);
  font-weight:700;font-size:13.5px;color:var(--anf-texto);text-decoration:none;cursor:pointer;font-family:inherit;white-space:nowrap}
.vn-chip:hover{border-color:var(--azul-claro)}
.vn-chip.sel{background:var(--azul-tinte);border-color:var(--azul);color:var(--azul-osc)}
.vn-cli{display:flex;align-items:center;gap:12px;min-width:0;text-align:left}
.vn-cli>div{min-width:0}.vn-cli b{font-size:15px;margin-right:6px}.vn-cli small{display:block;color:var(--anf-tenue);font-size:12.5px;
  overflow:hidden;text-overflow:ellipsis}
.vn-cli .va-pill{vertical-align:2px}
.vn-av{width:36px;height:36px;border-radius:50%;object-fit:cover;flex:none;display:inline-flex;align-items:center;justify-content:center;
  background:var(--azul);color:#fff;font-weight:800;font-size:15px}
.vn-orden{color:inherit;text-decoration:none;display:inline-flex;align-items:center;min-height:32px}
.vn-orden.sel{color:var(--azul)}.vn-orden:hover{color:var(--azul)}
.vn-al-dia{color:var(--ok-fg);font-weight:700;font-size:13.5px}
.vn-td-acc{text-align:right;white-space:nowrap}.vn-th-acc{text-align:right!important}
.vn-td-acc .btn+.btn{margin-left:8px}
.vn-acc{display:inline-flex;align-items:center;gap:6px;background:none;border:0;padding:6px 4px;min-height:40px;font:inherit;font-weight:700;
  font-size:14px;color:var(--azul);text-decoration:none;cursor:pointer}
.vn-acc+.vn-acc{margin-left:10px}.vn-acc:hover{text-decoration:underline}
.vn-cli-p{padding:8px 18px}
.va-tabla tbody tr[hidden]{display:none}
/* ── Bonos ── */
.vn-bonos{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(300px,100%),1fr));gap:16px;margin-bottom:16px}
.vn-bono{background:#fff;border:1px solid var(--anf-borde);border-radius:16px;padding:20px;display:flex;flex-direction:column;min-width:0}
.vn-bono.pausa{opacity:.75}
.vn-bono-h{display:flex;gap:14px;align-items:center}
.vn-bono-h h3{font-size:16px;margin:0 0 6px}
.vn-bono-n{width:56px;height:56px;border-radius:12px;background:var(--azul-tinte);color:var(--azul);display:flex;align-items:center;justify-content:center;
  font-weight:800;font-size:18px;flex:none}
.vn-bono-p{font-size:28px;margin-top:18px;line-height:1.1}
.vn-bono-ph{color:var(--anf-tenue);font-size:13px}
.vn-bono-a{display:flex;gap:8px;flex-wrap:wrap;border-top:1px solid var(--anf-linea);margin-top:16px;padding-top:16px}
.vn-bbtn{display:inline-flex;align-items:center;gap:6px;background:#fff;border:1px solid var(--anf-borde);border-radius:10px;padding:8px 12px;
  min-height:40px;font:inherit;font-weight:700;font-size:13.5px;color:var(--anf-texto);cursor:pointer}
.vn-bbtn:hover{border-color:var(--azul-claro)}
.vn-bbtn.rojo{color:var(--anf-rojo)}.vn-bbtn.rojo:hover{border-color:var(--bad-bg);background:var(--bad-bg)}
.vn-bono-nuevo{border:2px dashed var(--azul-claro);border-radius:16px;background:var(--azul-suave);display:flex;flex-direction:column;align-items:center;
  justify-content:center;gap:6px;min-height:236px;font:inherit;cursor:pointer;color:var(--azul)}
.vn-bono-nuevo span{width:52px;height:52px;border-radius:50%;background:var(--azul);color:#fff;display:flex;align-items:center;justify-content:center;margin-bottom:6px}
.vn-bono-nuevo b{font-size:16px}.vn-bono-nuevo small{font-size:13px;color:var(--anf-tenue)}
.vn-bono-nuevo:hover span{background:var(--azul-osc)}
/* ── Reservas fijas ── */
.vn-fija-a{display:inline-flex;align-items:center;gap:10px}
.vn-fijas tr.vn-pausa td{opacity:.6}
.vn-fijas td small{display:block}
.vn-sw{position:relative;display:inline-block;width:46px;height:26px;flex:none;cursor:pointer}
.vn-sw input{position:absolute;inset:-9px -2px;opacity:0;width:auto;height:auto;margin:0;cursor:pointer;z-index:1}
.vn-sw i{position:absolute;inset:0;background:var(--trazo);border-radius:999px;transition:.2s}
.vn-sw i:after{content:'';position:absolute;top:3px;left:3px;width:20px;height:20px;border-radius:50%;background:#fff;box-shadow:0 1px 3px rgba(20,33,90,.25);transition:.2s}
.vn-sw input:checked+i{background:var(--azul)}.vn-sw input:checked+i:after{left:23px}
.vn-sw input:disabled{cursor:not-allowed}.vn-sw input:disabled+i{opacity:.45}
.vn-sw input:focus-visible+i{box-shadow:var(--foco)}
.vn-form{text-align:left}
.vn-form label{display:block;font-weight:700;font-size:13.5px;margin:14px 0 6px;color:var(--anf-texto)}
.vn-form select,.vn-form input{width:100%;box-sizing:border-box;border:1px solid var(--anf-borde);border-radius:10px;padding:10px 12px;font:inherit;
  font-size:15px;min-height:44px;background:#fff;color:var(--anf-texto)}
.vn-form select:focus,.vn-form input:focus{outline:none;box-shadow:var(--foco);border-color:var(--azul)}
.vn-form-2{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
.vn-dias{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:5px}.vn-dias .vn-chip{min-height:44px;padding:6px 2px;justify-content:center;font-size:13px}
.vn-dias .vn-chip.sel{background:var(--azul);border-color:var(--azul);color:#fff}
.vn-prev{margin-top:16px;background:var(--azul-tinte);border-radius:12px;padding:12px 14px;display:flex;flex-direction:column;gap:3px}
.vn-prev b{font-size:14.5px;color:var(--anf-texto)}.vn-prev span{font-size:14px;color:var(--anf-texto)}
.vn-prev small{font-size:12.5px;color:var(--anf-tenue)}
.vn-form .err{color:var(--bad-fg);font-size:13px;margin-top:8px;min-height:1em}
.vn-dlg-p{text-align:left;margin:0 0 8px}
/* ── Disponibilidad ── */
.vn-dispo-d{min-width:0}
.vn-semana{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.vn-dsems{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:6px;flex:1 1 420px;min-width:0}
.vn-dsem{display:flex;flex-direction:column;align-items:center;justify-content:center;border:1px solid var(--anf-borde);border-radius:10px;
  padding:6px 2px;min-height:56px;text-decoration:none;color:var(--anf-texto);background:#fff}
.vn-dsem small{font-size:12.5px;color:var(--anf-tenue)}.vn-dsem b{font-size:18px}
.vn-dsem.hoy{border-color:var(--azul-claro)}
.vn-dsem.sel{background:var(--azul);border-color:var(--azul);color:#fff}.vn-dsem.sel small{color:#fff}
.vn-dsem:hover:not(.sel){border-color:var(--azul)}
.vn-dia-cab{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;margin:0 0 14px}
.vn-resumen{display:flex;gap:8px;flex-wrap:wrap}
.vn-lote{display:flex;gap:10px;flex-wrap:wrap}
.vn .vn-lote .btn[disabled]{opacity:.5;cursor:not-allowed}
.vn-turnos{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(150px,100%),1fr));gap:12px}
.vn-turno{background:#fff;border:1px solid var(--anf-borde);border-radius:12px;padding:12px 14px;display:flex;flex-direction:column;gap:4px;min-width:0}
.vn-turno-h{display:flex;align-items:center;justify-content:space-between;gap:8px}
.vn-turno-h b{font-size:20px;letter-spacing:-.01em}
.vn-franja{display:inline-flex;align-items:center;gap:5px;font-size:13px;font-weight:700;color:var(--anf-texto)}
.vn-franja svg{color:var(--warn-fg)}
.vn-turno small{font-size:12.5px;color:var(--anf-tenue)}
.vn-turno small.vn-prio{color:var(--warn-fg);font-weight:700}
.vn-turno.pasada{background:var(--anf-fondo);border-color:var(--anf-linea)}.vn-turno.pasada .vn-turno-h b,.vn-turno.pasada .vn-franja{color:var(--anf-tenue)}
.vn-turno.cerrada{background:var(--anf-fondo)}
.vn-turno.reservada{background:var(--warn-bg);border-color:var(--warn-bg)}
.vn-lock{width:28px;height:28px;border-radius:8px;background:var(--warn-bg);border:1px solid var(--warn-fg);color:var(--warn-fg);display:inline-flex;align-items:center;justify-content:center}
.vn-turno small.vn-res{color:var(--warn-fg);font-weight:700}
.vn-dispo .va-lat{position:sticky;top:84px}
/* ── Cobros de academia ── */
.vn-banner{display:flex;align-items:center;gap:14px;flex-wrap:wrap}
.vn-banner .va-ic{background:var(--warn-bg);color:var(--warn-fg)}
.vn-banner-t{flex:1;min-width:220px}.vn-banner-t b{display:block;font-size:16px}.vn-banner-t small{color:var(--anf-tenue);font-size:13px}
.vn-deben td small{display:block}
.vn-deben-p .va-panel-cab{margin-bottom:6px}
/* ── Agregar cuota ── */
.ag-card select{width:100%;max-width:420px;padding:11px;border-radius:10px;border:1px solid var(--anf-borde);font:inherit;background:#fff;min-height:44px}
.ag-card{max-width:760px}
.ag-l{display:block;font-weight:800;margin:16px 0 8px}.ag-card>.ag-l:first-child{margin-top:0}
.ag-prog{font-weight:800;margin:12px 0 6px;color:var(--anf-tenue);font-size:13px}
.ag-op{display:flex;gap:10px;align-items:center;border:1px solid var(--anf-borde);border-radius:12px;padding:11px 13px;margin-bottom:8px;cursor:pointer;min-width:0;min-height:44px}
.ag-op input{width:auto;flex:none}.ag-op small{display:block;color:var(--anf-tenue)}
.ag-op:has(input:checked){background:var(--azul-tinte);border-color:var(--azul)}
.ag-monto{max-width:220px}
.ag-prev{margin-top:14px;background:var(--azul-tinte);color:var(--azul-osc);border-radius:12px;padding:12px;font-size:14px;line-height:1.45}
.ag-ok{margin-top:16px;width:100%}
/* ── celular ── */
@media(max-width:1000px){.vn-dos{grid-template-columns:minmax(0,1fr)}.vn-col{grid-template-columns:repeat(3,minmax(0,1fr));grid-auto-rows:auto}}
@media(max-width:860px){.vn-dispo .va-lat{display:none}.vn-sel-mov{display:flex;margin-bottom:12px}.vn-sel-mov select{flex:1;max-width:none}}
@media(max-width:600px){
  .vn-tabs{gap:20px}.vn-tabs a{font-size:14px}
  .vn-col{grid-template-columns:repeat(2,minmax(0,1fr))}.vn-col .va-kpi:last-child{grid-column:1/-1}
  .vn-ing-v{font-size:30px}
  .vn-ing .vn-tabla>summary{position:static}
  .vn-graf{height:190px}.vn-barras{gap:3px}.vn-bar-c small{font-size:12px}
  .vn-dia{width:100%}.vn-dia .vn-fecha{flex:1}.vn-dia .vn-fecha-t{width:100%;justify-content:center}
  .vn-fila{flex-wrap:wrap;gap:10px}.vn-fila-t{flex:1 1 60%}.vn-fila-a{width:100%}.vn-fila-a .btn{flex:1;justify-content:center}
  .vn-buscar{flex:1 1 100%}.vn-filtros>.va-seg{max-width:100%}
  .vn-cli-p{padding:12px}
  .vn .va-tabla td:first-child{justify-content:flex-start;text-align:left;padding-bottom:10px;border-bottom:1px solid var(--anf-linea)}
  .vn .va-tabla td:first-child:before,.vn .va-tabla td.vn-td-acc:before{display:none}
  .vn .va-tabla td.vn-td-acc{padding-top:10px}
  .va-tabla td.vn-td-acc{flex-wrap:wrap;justify-content:flex-end}
  .vn-td-acc .btn{flex:1}
  .vn-semana{gap:6px}.vn-semana .vn-dsems{order:3;flex-basis:100%}.vn-semana .vn-fecha{flex:1}.vn-semana .vn-fecha-t{width:100%;justify-content:center}
  .vn-dsem{min-height:52px}.vn-dsem b{font-size:16px}
  .vn-turnos{grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}
  .vn-lote{width:100%}.vn-lote .btn{flex:1}
  .vn-form-2{grid-template-columns:minmax(0,1fr)}
  .vn-banner .btn{width:100%}
  .vn-sel{width:100%}.vn-sel select{flex:1;max-width:none}
}
"""
