"""CSS de las vistas del modo anfitrión · Mi club: Cobros del club, Pagos por confirmar, Reglas, Encargados — web/anfitrion_cobros_club.py, web/anfitrion_encargados.py.

Va después del kit (`web/vista_anfitrion.py`). Solo tokens (`--azul`, `--anf-*`).
Todo bajo el prefijo `.vcl` (la vista) o `.vcl-*` (piezas), salvo lo que se
pinta DENTRO del diálogo global (`pcgConfirmar`): `.vcl-dlg-*` y `.vv-zoom`.
"""

# Ancho de la barra "deuda vs. tope" sin estilos en línea: clases p0…p100.
_BARRA = "".join(f".vcl-barra i.p{p}{{width:{p}%}}" for p in range(0, 101, 5))

CSS = r"""
/* ═════════ MODO ANFITRIÓN · Mi club (Cobros, Pagos por confirmar, Reglas, Encargados) ═════════ */
.vcl h3{margin:0}
.vcl .vh{position:absolute!important;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap;margin:0;padding:0}
.vcl label{color:var(--anf-texto)}
.vcl input,.vcl select{border-color:var(--anf-borde);background:#fff;color:var(--anf-texto);font-size:15px}
.vcl select{min-height:46px;padding:10px 12px}
.vcl-ic{background:var(--azul)}.vcl-ic.verde{background:var(--anf-verde)}.vcl-ic.naranja{background:var(--anf-naranja)}
.vcl-ic.morado{background:var(--anf-morado)}.vcl-ic.rojo{background:var(--anf-rojo)}
.vcl-link{background:none;border:0;padding:0 4px;font:inherit;font-weight:700;font-size:14px;color:var(--azul);cursor:pointer;
  min-height:44px;display:inline-flex;align-items:center;text-decoration:none}
.vcl-link:hover{text-decoration:underline}.vcl-link.rojo{color:var(--anf-rojo)}
.vcl-link:focus-visible,.vcl-agregar:focus-visible,.vcl-chip:focus-visible,.vcl-mini-img:focus-visible,.vcl-ver:focus-visible{outline:3px solid var(--azul);outline-offset:2px}
.vcl-nota{font-size:12.5px;color:var(--anf-tenue);margin:10px 0 0}
.vcl-nota a{color:var(--azul);font-weight:700}
.vcl-nada{color:var(--anf-tenue);font-size:14px;margin:4px 0}
.vcl-p{margin:0 0 14px;color:var(--anf-tenue);font-size:15px}
.vcl-col{min-width:0;display:flex;flex-direction:column}
.vcl-col>.va-panel{margin-bottom:16px}
.vcl-form{background:var(--anf-fondo);border:1px solid var(--anf-borde);border-radius:14px;padding:4px 16px 16px;margin-top:14px}
.vcl-form label{margin-top:12px}
.vcl-form-acc{display:flex;gap:10px;flex-wrap:wrap;margin-top:14px}
.vcl-fila2{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
.vcl-fila2 label span,.vcl-luz label span,.rg-horas label span{display:block;font-size:12.5px;color:var(--anf-tenue);margin-bottom:6px}
.vcl-fila2 label,.vcl-luz label,.rg-horas label{margin:12px 0 0;font-weight:700}
.vcl-det{margin-top:12px}.vcl-det summary{cursor:pointer;color:var(--anf-tenue);font-weight:700;font-size:14px;min-height:44px;display:flex;align-items:center}

/* panel con ícono a la izquierda del título */
.vcl-pcab{display:flex;align-items:flex-start;gap:14px;margin-bottom:16px;flex-wrap:wrap}
.vcl-pcab-t{flex:1 1 220px;min-width:0}.vcl-pcab-t p{margin:4px 0 0;color:var(--anf-tenue);font-size:13.5px}
.vcl-pcab-acc{display:flex;gap:8px;align-items:center}

/* ── Cobros de tu club ── */
.vcl-est{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(300px,100%),1fr));gap:16px;margin-bottom:16px}
.vcl-est-it{background:#fff;border:1px solid var(--anf-borde);border-radius:16px;padding:16px 18px;display:flex;align-items:center;gap:14px;min-width:0}
.vcl-est-it .tx{flex:1;min-width:0}.vcl-est-it .tx b{display:block;font-size:14.5px}
.vcl-est-it .tx small{display:block;font-size:12.5px;color:var(--anf-tenue);margin-top:2px}
.vcl-cobros{grid-template-columns:minmax(0,1fr) minmax(0,380px)}
.vcl-llaves{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}
.vcl-llaves label{margin-top:0}
.vcl-pie{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-top:16px}
.vcl-candado{display:inline-flex;align-items:center;gap:6px;color:var(--anf-tenue);font-size:12.5px;flex:1 1 240px}
.vcl-ok{display:flex;align-items:center;gap:10px;background:var(--ok-bg);color:var(--ok-fg);border-radius:12px;padding:12px 14px;flex-wrap:wrap}
.vcl-ok b{flex:1}
.vcl-dl{display:grid;grid-template-columns:auto minmax(0,1fr);gap:8px 14px;margin:14px 0}
.vcl-dl dt{color:var(--anf-tenue);font-weight:700;font-size:13.5px}.vcl-dl dd{margin:0;overflow-wrap:anywhere}
.vcl-copiar{display:flex;gap:8px}.vcl-copiar input{flex:1;min-width:0}.vcl-copiar .btn{display:inline-flex;align-items:center;gap:6px;flex:none}
.vcl-med{display:flex;align-items:center;gap:12px}.vcl-med .va-ic{width:32px;height:32px}.vcl-med b{font-size:15px}
.vcl-c>small,.vcl-c>b{display:block}
.vcl-cta b{display:block;font-weight:600;overflow-wrap:anywhere}.vcl-cta small{display:block}
.vcl-qr{width:44px;height:44px;object-fit:cover;border-radius:8px;float:left;margin-right:10px}
.vcl-acc-t{display:flex;justify-content:flex-end;gap:8px}
.vcl-vacio-c{padding:20px 12px}
.vcl-saldo{background:var(--anf-fondo);border-radius:14px;padding:18px}
.vcl-saldo small{font-size:14px;color:var(--anf-tenue)}.vcl-saldo b{display:block;font-size:34px;line-height:1.15;margin:6px 0}
.vcl-saldo p{margin:0;font-size:12.5px;color:var(--anf-tenue)}
.vcl-mini{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin:14px 0}
.vcl-mini>div{border:1px solid var(--anf-borde);border-radius:12px;padding:12px 14px;min-width:0}
.vcl-mini small{font-size:12.5px;color:var(--anf-tenue)}.vcl-mini b{display:block;font-size:19px;margin:6px 0 2px}
.vcl-mini p{margin:0;font-size:12px;color:var(--anf-tenue)}
.vcl-barra-t{display:flex;justify-content:space-between;gap:8px;font-size:13.5px;flex-wrap:wrap}
.vcl-barra-t span{color:var(--anf-tenue);font-weight:700}
.vcl-barra{height:8px;background:var(--anf-linea);border-radius:99px;margin-top:8px;overflow:hidden}
.vcl-barra i{display:block;height:100%;min-width:6px;border-radius:99px;background:var(--anf-verde)}
.vcl-barra.warn i{background:var(--anf-naranja)}.vcl-barra.bad i{background:var(--anf-rojo)}
.vcl-com .va-aviso{margin:14px 0 0}
.vcl .vcl-ancho{width:100%;display:flex;justify-content:center;align-items:center;gap:8px;margin-top:18px}
.vcl-link-c{display:flex;justify-content:center;align-items:center;min-height:44px;margin-top:6px;color:var(--azul);font-weight:700;font-size:14px;text-decoration:none}
.vcl-link-c:hover{text-decoration:underline}

/* ── Pagos por confirmar ── */
.vcl-barra-f{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:16px}
.vcl-filtros{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.vcl-sel{margin:0;display:inline-flex;align-items:center;gap:8px}
.vcl-sel select{width:auto;min-width:200px;font-weight:700}
.vcl-chips{display:flex;gap:8px;flex-wrap:wrap}
.vcl-chip{display:inline-flex;align-items:center;gap:6px;border-radius:999px;padding:6px 12px;font-size:13px;font-weight:700;text-decoration:none;
  min-height:36px;border:1.5px solid transparent}
.vcl-chip.ok{background:var(--ok-bg);color:var(--ok-fg)}.vcl-chip.bad{background:var(--bad-bg);color:var(--bad-fg)}
.vcl-chip.gris{background:var(--anf-linea);color:var(--anf-tenue)}.vcl-chip.sel{border-color:currentColor}
.vcl-tabla-p{padding-top:8px;padding-bottom:8px}
.vcl-mini-img{position:relative;width:64px;height:64px;border-radius:12px;background:var(--azul-tinte);color:var(--azul-claro);border:1px solid var(--anf-borde);
  display:flex;align-items:center;justify-content:center;overflow:hidden;padding:0;cursor:zoom-in}
.vcl-mini-img img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}
.vcl-monto{display:block;font-size:18px}
.vcl-medio{display:flex!important;align-items:center;gap:4px;margin-top:2px}
.vcl-vv td>b{display:block}
.vcl-vv .va-pill{margin-bottom:4px}
.vcl-ver{background:none;border:0;font:inherit;font-weight:700;font-size:14px;color:var(--azul);cursor:pointer;min-height:44px;padding:0 6px}
.vcl-acc{display:flex;gap:8px;justify-content:flex-end;flex-wrap:wrap}
.vcl .vcl-acc .btn{padding:9px 14px;font-size:14px}
.vv-vence{font-weight:700;color:var(--warn-fg)!important}.vv-vence.tarde{color:var(--bad-fg)!important}
.vv-zoom{max-width:100%;max-height:70vh;border-radius:12px;display:block;margin:0 auto}

/* ── Reglas de reserva ── */
.vcl-rg{align-items:start}
.vcl-rg-main{min-width:0}
.vcl-rg-top{display:flex;justify-content:space-between;align-items:center;gap:12px 16px;flex-wrap:wrap}
.vcl-rg-tit{min-width:0}.vcl-rg-tit h2{font-size:20px}.vcl-rg-tit p{margin:4px 0 0;color:var(--anf-tenue);font-size:13.5px}
.vcl-rg-acc{display:flex;gap:10px;flex-wrap:wrap}.vcl-rg-acc .btn{display:inline-flex;align-items:center;gap:6px}
.vcl-rg-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0 16px;align-items:start}
.rg-dia{display:grid;grid-template-columns:96px minmax(0,1fr);gap:8px 12px;align-items:center;padding:8px 0}
.rg-dia>b{font-size:14.5px}
.rg-dia-c{min-width:0}
.rg-horas{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}
.vcl-rg-pie{margin-top:4px}
.vcl-h3{font-size:15px;margin-top:18px!important;padding-top:16px;border-top:1px solid var(--anf-linea)}
.vcl-nota-a{margin-top:4px}
.vcl-franjas td.vcl-num,.vcl-franjas th:nth-child(3){text-align:right}
.vcl-franjas td small{display:block}
.vcl-base td{color:var(--anf-tenue)}
.vcl-luz{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(150px,100%),1fr));gap:0 12px}
.vcl-cierres{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:8px}
.vcl-cierres li{display:flex;align-items:center;justify-content:space-between;gap:10px;background:var(--anf-fondo);border-radius:12px;padding:8px 8px 8px 14px}
.vcl-cierres li small{display:block;font-size:12.5px;color:var(--anf-tenue)}
.vcl-agregar{width:100%;margin-top:12px;min-height:48px;border:1.5px solid var(--azul-claro);background:#fff;color:var(--azul);font:inherit;font-weight:700;
  font-size:14.5px;border-radius:12px;cursor:pointer}
.vcl-agregar:hover{background:var(--azul-tinte)}
.vcl-pol{display:flex;flex-direction:column}
.vcl-pol-f{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,210px);align-items:center;gap:8px 14px;margin:0;padding:8px 0;
  border-top:1px solid var(--anf-linea);font-size:14.5px}
.vcl-pol-f:first-child{border-top:0}
.vcl-rg-vista{display:flex;align-items:flex-end;gap:12px;flex-wrap:wrap;margin-bottom:12px}
.vcl-rg-vista>div{flex:0 1 220px}.vcl-rg-vista label{margin-top:0}
.rg-turnos{display:flex;flex-wrap:wrap;gap:8px;margin-top:8px}
.rg-t{border:1px solid var(--anf-borde);border-radius:12px;padding:8px 10px;min-width:104px;background:#fff}
.rg-t b{display:block;font-size:14px}.rg-t small{display:block;color:var(--anf-tenue);font-weight:600;font-size:12px}
.vcl-rg-barra{display:none}
.vcl-dlg-p{text-align:left;margin:0 0 10px;font-size:14.5px}
.vcl-dlg-g{text-align:left;margin:10px 0}.vcl-dlg-g>small{display:block;font-size:12px;font-weight:700;letter-spacing:.04em;text-transform:uppercase;
  color:var(--anf-tenue);margin-bottom:6px}

/* ── Encargados ── */
.vcl-sel-local{background:#fff;border:1px solid var(--anf-borde);border-radius:12px;padding:4px 6px 4px 14px;min-height:48px;font-size:14px;color:var(--anf-tenue);font-weight:600}
.vcl-sel-local select{border:0;min-width:180px;padding:8px;font-weight:700;color:var(--anf-texto)}
.vcl-sel-local>b{color:var(--anf-texto);padding-right:10px}
.vcl-inv{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,190px) auto;gap:10px;align-items:end;background:var(--anf-fondo);
  border-radius:14px;padding:14px 16px}
.vcl-inv label{margin:0 0 6px}.vcl-inv .btn{min-height:46px}
.vcl-inv-r select{font-weight:700}
.vcl-equipo .va-tabla-w{margin-top:14px}
.vcl-persona{display:flex;align-items:center;gap:10px;min-width:0}
.vcl-persona .tx{min-width:0}.vcl-persona .tx b{display:block;overflow-wrap:anywhere}
.vcl-av{flex:none;width:34px;height:34px;border-radius:50%;background:var(--azul-tinte);color:var(--azul-osc);display:inline-flex;align-items:center;
  justify-content:center;font-weight:800;font-size:14px}
.vcl-enc-cab{display:grid;grid-template-columns:minmax(0,1.6fr) repeat(3,minmax(0,.7fr));gap:8px;margin-top:16px;padding:10px 8px;
  border-bottom:1px solid var(--anf-borde);font-size:12px;letter-spacing:.04em;text-transform:uppercase;color:var(--anf-tenue);font-weight:700}
.vcl-enc-cab span:last-child{text-align:right}
.vcl-enc-vacio{display:flex;gap:12px;align-items:center;padding:14px 8px}
.vcl-enc-vacio b{display:block;font-size:14.5px}.vcl-enc-vacio small{display:block;font-size:13px;color:var(--anf-tenue);margin-top:2px}
.vcl-7d{font-size:13.5px;color:var(--anf-tenue)}
.vcl-caja{background:var(--anf-fondo);border-radius:12px;padding:14px 16px;margin:0;color:var(--anf-tenue);font-size:14px}
.vcl-act{list-style:none;margin:0;padding:0}
.vcl-act li{display:flex;gap:12px;align-items:flex-start;padding:10px 0;border-top:1px solid var(--anf-linea);overflow-wrap:anywhere;font-size:14.5px}
.vcl-act li:first-child{border-top:0}.vcl-act li>div{min-width:0}.vcl-act small{display:block;color:var(--anf-tenue);font-size:12.5px;margin-top:2px}
.vcl-puede h2{text-align:center;margin-bottom:6px!important}
.vcl-puede h3{font-size:12px;letter-spacing:.05em;text-transform:uppercase;margin-top:16px!important}
.vcl-puede h3.si{color:var(--ok-fg)}.vcl-puede h3.no{color:var(--bad-fg);padding-top:14px;border-top:1px solid var(--anf-linea)}
.vcl-puede ul{list-style:none;margin:8px 0 0;padding:0}
.vcl-puede li{display:flex;gap:10px;align-items:flex-start;padding:6px 0;font-size:14.5px}
.vcl-puede li svg{flex:none;margin-top:2px}
.vcl-puede ul.si svg{color:var(--anf-verde)}.vcl-puede ul.no svg{color:var(--anf-rojo)}.vcl-puede ul.no span{color:var(--anf-tenue)}
.vcl-puede .vcl-nota{text-align:center;margin-top:16px}
.vcl-enc-g{grid-template-columns:minmax(0,1fr) minmax(0,320px)}

@media(max-width:1000px){.vcl-cobros,.vcl-enc-g{grid-template-columns:minmax(0,1fr)}}
@media(max-width:860px){
  .vcl-rg-grid{grid-template-columns:minmax(0,1fr)}
  .vcl .vcl-rg-top .rg-guardar{display:none}
  .vcl-rg-acc,.vcl-rg-acc .btn{width:100%}
  .vcl-rg-barra{display:flex;position:sticky;bottom:0;gap:10px;justify-content:flex-end;background:#fff;border-top:1px solid var(--anf-borde);
    padding:12px 16px;margin:8px -16px 0;z-index:5}
  .vcl-rg-barra .btn{flex:1}
}
@media(max-width:600px){
  .vcl-llaves,.vcl-mini{grid-template-columns:minmax(0,1fr)}
  .vcl-inv{grid-template-columns:minmax(0,1fr)}
  .vcl-enc-cab{display:none}
  .vcl-pol-f{grid-template-columns:minmax(0,1fr)}
  .rg-dia{grid-template-columns:minmax(0,1fr)}
  .vcl-sel select{min-width:0;width:100%}.vcl-sel,.vcl-filtros{width:100%}
  .vcl-acc{justify-content:flex-end}.vcl .vcl-acc .btn{flex:1}
  .vcl .va-tabla td>.vcl-c{min-width:0;text-align:right;display:flex;flex-direction:column;align-items:flex-end}
  .vcl .va-tabla td .vcl-medio{justify-content:flex-end}
  .vcl .va-tabla td>.vcl-c>.vcl-acc{width:100%}
  .vcl-vv td .vcl-mini-img{margin-left:auto}
  .vcl-pcab-acc{width:100%}.vcl-pcab-acc .btn{flex:1}
  .vcl-acc-t{justify-content:flex-start}
  .vcl-qr{float:none;display:block;margin:0 0 6px auto}
}
""" + _BARRA
