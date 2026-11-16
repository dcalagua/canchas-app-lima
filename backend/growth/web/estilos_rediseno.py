"""CSS del REDISEÑO AZUL de la web (PDF "Soluciones EBIM", nov-2026).

Va al FINAL de `ui.CSS` (después del modo anfitrión) para ganar en la cascada
sin reescribir las ~700 reglas de antes. Los tokens están en `ui.TOKENS`
(`--azul #3056ED`, `--azul-osc #2442C4`, `--azul-claro #7E98FF` solo
decoración, `--azul-tinte #E3E8FF`, `--carbon #333333`).

Piezas (en orden):
1. cabecera en tres franjas (`ui.cabecera`): barra azul fija, pastillas por
   deporte, franja celeste con el buscador y las amenidades;
2. buscador grande y chico;
3. explorador: títulos, tarjetas, "Mostrar mapa";
4. pie azul;
5. ficha de reserva, login, Libro y páginas legales;
6. modo anfitrión (las pestañas van blancas dentro de la barra).

Contraste: blanco sobre `#3056ED` = 5,7:1 y sobre `#2442C4` = 7,9:1 (AA);
`#3056ED` sobre `#E3E8FF` = 4,7:1. Nunca texto blanco sobre `#7E98FF` (2,7:1).
"""

CSS = r"""
/* ═════════ REDISEÑO AZUL · 1. cabecera ═════════ */
header.cl{display:contents}
.cl-barra{position:sticky;top:0;z-index:30;background:var(--azul);color:#fff;box-shadow:0 1px 0 rgba(255,255,255,.08)}
.cl-barra .cab{display:flex;align-items:center;gap:20px;height:72px;padding-top:0;padding-bottom:0;column-gap:20px}
.cl-barra .cab-logo{height:72px;flex:none}
.wm-cl{display:inline-flex;align-items:center;gap:12px;text-decoration:none;min-height:44px}
.wm-cl .wm-ico{height:40px;width:auto;display:block}
.wm-cl .wm-txt{height:17px;width:auto;display:block}
.wm.sobre-azul,.wm.sobre-azul span{color:#fff}
.cab-links{flex:1;display:flex;justify-content:center;gap:6px;min-width:0}
.cab-links a{color:#fff;text-decoration:none;font-weight:600;font-size:15px;padding:10px 14px;border-radius:999px;white-space:nowrap}
.cab-links a:hover{background:rgba(255,255,255,.14)}
.cl-barra .cab-mini{display:none;flex:1;justify-content:center;min-width:0}
.cl-barra .cab.chica .cab-links{display:none}.cl-barra .cab.chica .cab-mini{display:flex}
.cl-barra .cab-der{height:auto;gap:10px;margin-left:auto;flex:none}
.cl-barra .cab-der a.host{color:#fff;border:1.5px solid rgba(255,255,255,.6);background:rgba(255,255,255,.12);font-weight:700;padding:9px 16px;font-size:14.5px;min-height:42px;display:inline-flex;align-items:center}
.cl-barra .cab-der a.host:hover{background:rgba(255,255,255,.24)}
.entrar-pill{display:inline-flex;align-items:center;min-height:42px;background:var(--azul-osc);color:#fff;border:1.5px solid rgba(255,255,255,.6);border-radius:999px;padding:0 18px;font-weight:700;font-size:14px;text-decoration:none;white-space:nowrap}
.entrar-pill:hover{background:#1C37A8}.entrar-pill .c{display:none}
.cl-barra .redondo{background:rgba(255,255,255,.16);color:#fff}
.cl-barra .redondo:hover{background:rgba(255,255,255,.28)}
.cl-barra .redondo img,.cl-barra .redondo .ini{background:#fff;color:var(--azul)}
.cl-barra a:focus-visible,.cl-barra button:focus-visible{outline:3px solid #fff;outline-offset:2px}
/* modo anfitrión: las pestañas (Hoy, Calendario…) van blancas dentro de la barra */
.cl-barra .cab.anfitrion .cab-tabs{flex:1;justify-content:center;justify-content:safe center;height:72px;align-items:stretch}
.cl-barra .cab.anfitrion .cat{color:rgba(255,255,255,.85);padding:0 12px;display:flex;align-items:center;border-bottom:0}
.cl-barra .cab.anfitrion .cat:hover{color:#fff}.cl-barra .cab.anfitrion .cat:hover:after{background:rgba(255,255,255,.45);bottom:0}
.cl-barra .cab.anfitrion .cat.sel{color:#fff;font-weight:800}.cl-barra .cab.anfitrion .cat.sel:after{background:#fff;height:3px;bottom:0;border-radius:3px 3px 0 0}
/* pastillas por deporte (fila blanca) */
.cl-fila-tabs{background:#fff;border-bottom:1px solid var(--trazo)}
.cl-fila-tabs .cab-tabs{border-top:0;margin:0;padding:12px 2px;gap:10px;justify-content:center;justify-content:safe center;align-items:center}
.cl-pills .cat{gap:8px;padding:0 16px;height:42px;border:1px solid var(--trazo);border-radius:999px;background:#fff;color:var(--carbon);font-weight:600;font-size:14px;box-shadow:0 1px 3px rgba(17,24,39,.06);flex:none}
.cl-pills .cat .ico{color:var(--azul);font-size:18px;display:inline-flex;filter:none}
.cl-pills .cat:after,.cl-pills .cat:hover:after{display:none}
.cl-pills .cat:hover{border-color:var(--azul-claro);color:var(--carbon)}.cl-pills .cat:hover .ico{transform:none}
.cl-pills .cat[data-dep=academias]:not(.sel){background:var(--azul-tinte);border-color:transparent;color:var(--azul-osc)}
.cl-pills .cat.sel{background:var(--carbon);color:#fff;border-color:var(--carbon);font-weight:700}
.cl-pills .cat.sel .ico{color:#fff}
/* franja celeste del buscador */
.cl-banda{background:var(--azul-tinte);position:relative;z-index:25}
.cl-banda.grande{padding:34px 0 26px}
.cl-banda:not(.grande){padding:16px 0}
.cl-banda-in{position:relative;z-index:1;display:flex;flex-direction:column;align-items:center;gap:14px}
.cl-banda.grande::before{content:"";position:absolute;left:clamp(16px,6vw,140px);top:50%;width:200px;height:212px;transform:translateY(-50%) rotate(-12deg);background:url(/static/brand/cl_icono_blanco.png) no-repeat center/contain;opacity:.55;pointer-events:none}
.cl-banda.grande::after{content:"¡YA TENEMOS CANCHA!";position:absolute;right:clamp(16px,5vw,90px);top:30px;transform:rotate(9deg);font-weight:800;font-size:30px;letter-spacing:.5px;color:#C3CDFB;pointer-events:none;white-space:nowrap}
@media(max-width:1280px){.cl-banda.grande::after{display:none}}
@media(max-width:1100px){.cl-banda.grande::before{display:none}}
.cl-banda .cab-busq{width:100%;display:flex;justify-content:center;margin:0}
/* ═════════ 2. buscador ═════════ */
.cl .busq{border:0;border-radius:18px;height:78px;max-width:680px;box-shadow:0 8px 24px rgba(48,86,237,.14);padding-left:6px}
.cl .busq .seg{border-radius:14px;padding:0 20px}
.cl .busq .seg small{display:flex;align-items:center;gap:7px;font-size:16px;font-weight:800;color:var(--carbon);margin-bottom:3px}
.cl .busq .seg small svg{color:var(--azul);flex:none}
.cl .busq .seg input{font-size:13.5px;color:var(--carbon)}
.cl .busq .seg input::placeholder{color:var(--tenue)}
.cl .busq .lupa{background:var(--azul);height:42px;border-radius:999px;padding:0 18px 0 14px;font-size:14.5px;margin-right:16px}
.cl .busq .lupa:hover{background:var(--azul-osc)}
.cl .busq:focus-within{background:#fff}
.cl .busq .seg:hover{background:var(--azul-suave)}
/* amenidades rápidas + Filtros, dentro de la franja */
.cl-banda .barra-filtros{justify-content:center;padding:0;max-width:680px;width:100%;gap:10px;min-width:0}
.cl-banda .barra-filtros .qchips{min-width:0;padding:2px;flex-wrap:wrap;justify-content:center;overflow:visible}
.cl-banda .barra-filtros .qchips:before{display:none}
.cl-banda .barra-filtros .chip{background:#fff;border:0;border-radius:999px;box-shadow:0 1px 4px rgba(48,86,237,.12);font-weight:600;font-size:13.5px;padding:9px 16px;gap:8px}
.cl-banda .barra-filtros .chip svg{color:var(--azul)}
.cl-banda .barra-filtros .chip.sel{background:var(--carbon);color:#fff}.cl-banda .barra-filtros .chip.sel svg{color:#fff}
.cl-banda .filtros{background:var(--azul);color:#fff;border:0;border-radius:999px;padding:9px 18px;min-height:40px}
.cl-banda .filtros:hover{background:var(--azul-osc);border-color:transparent}
.cl-banda .filtros.on{box-shadow:0 0 0 2px var(--carbon) inset}
.cl-banda .filtros .n{background:#fff;color:var(--azul)}
/* buscador chico (páginas interiores y barra compacta) */
.cl .busq-mini{background:#fff;border:0;height:52px;padding:0 6px 0 22px;box-shadow:0 6px 18px rgba(48,86,237,.14);gap:0}
.cl .busq-mini span{display:inline-flex;align-items:center;gap:7px;font-weight:800;color:var(--carbon);padding:0 18px 0 0;font-size:15px}
.cl .busq-mini span+span{border-left:0;padding-left:0}
.cl .busq-mini span svg{color:var(--azul)}
.cl .busq-mini>i:last-child{width:auto;height:38px;padding:0 16px;border-radius:999px;background:var(--azul);gap:6px;margin-left:6px}
.cl .busq-mini>i:last-child b{font-size:14px;color:#fff;font-style:normal}
.cl-barra .busq-mini{height:44px;box-shadow:none}
/* ═════════ 3. explorador ═════════ */
.tit h2{color:var(--azul);font-size:26px;font-weight:800}
.tit h2 .flag{display:none}
.grupo-aca .tit h2,#descubiertas .tit h2{color:var(--azul)}
.lst-grid{grid-template-columns:repeat(auto-fill,minmax(min(320px,100%),1fr));gap:28px}
@media(max-width:760px){.lst-grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}}
@media(max-width:600px){.lst-grid{grid-template-columns:minmax(0,1fr)}}
.lst{background:#fff;border-radius:10px;box-shadow:0 2px 14px rgba(17,24,39,.09);padding:8px 8px 16px;transition:box-shadow .15s,transform .15s}
.lst:hover{box-shadow:0 8px 26px rgba(17,24,39,.14);transform:translateY(-1px)}
.lst .foto{border-radius:6px}
.lst .lb{padding:12px 8px 0}
.lst .l1 b{font-size:16px}
.lst .l2{color:var(--carbon);font-weight:500;font-size:13.5px}
.lst .l3 b{font-size:16px}
.lst .badge{background:var(--ok-fg);color:#fff;box-shadow:none;padding:6px 10px}
.lst .badge.pend{background:rgba(255,255,255,.94);color:var(--carbon)}
.lst .badge.aca{background:var(--azul);color:#fff}
.lst .corazon{width:34px;height:34px;border-radius:50%;background:#fff;box-shadow:0 1px 4px rgba(17,24,39,.2);top:10px;right:10px}
.lst .corazon svg{width:18px;height:18px;fill:none;stroke:#E5484D;stroke-width:2.4}
.lst .corazon.on{background:#E5484D}.lst .corazon.on svg{fill:#fff;stroke:#fff}
.lst .l3 .app{border-color:var(--azul-claro);color:var(--azul-osc)}
.btn-mapa{background:#1B1B1F;font-size:15px;padding:14px 24px}
.ubic-mini{color:var(--carbon);font-weight:700}
.ubic-mini button{color:var(--azul)}
/* ═════════ 4. pie azul ═════════ */
footer.pie{background:var(--azul);color:rgba(255,255,255,.92);border-top:0;position:relative;overflow:hidden;margin-top:72px;font-size:14px}
footer.pie::before{content:"";position:absolute;left:-60px;bottom:-140px;width:460px;height:490px;background:url(/static/brand/cl_icono_blanco.png) no-repeat center/contain;opacity:.08;transform:rotate(-8deg);pointer-events:none}
footer.pie>*{position:relative}
.pie-cols{grid-template-columns:1.3fr 1fr 1fr 1fr;padding:64px 0 32px;gap:32px}
@media(max-width:900px){.pie-cols{grid-template-columns:1fr 1fr}}@media(max-width:560px){.pie-cols{grid-template-columns:1fr}}
.pie-cols h4{color:#fff;font-size:15px}
.pie-cols a{color:#fff;font-weight:500;font-size:15px}.pie-cols a:hover{color:#fff}
.wm-apilado{display:inline-block;margin-bottom:14px}.wm-apilado img{width:236px;height:auto;display:block}
.pie-lema{font-size:16px;color:#fff;margin-bottom:10px}
.pie-deps{font-size:15px;line-height:1.7;color:#fff}
.pie-redes{font-size:15px;color:#fff;margin-top:22px}
.pie-redes a{background:#fff;color:var(--azul);border:0}.pie-redes a:hover{background:var(--azul-tinte);color:var(--azul-osc)}
.pie-cols a.libro{background:#D93025;color:#fff;border:0;border-radius:8px;font-size:12.5px;padding:6px 12px 6px 8px}
.pie-cols a.libro:hover{background:#B3261E}
.pie-cols a.libro svg path:first-child{fill:#fff}
.pie-bajo{border-top:1px solid rgba(255,255,255,.22);color:#fff;font-size:13px}
.pie-bajo a{color:#fff}
/* ═════════ 5. botones, chips y componentes ═════════ */
.btn{border-radius:10px}
.btn.sec{border-color:var(--trazo)}
.btn.dark{background:#1B1B1F}
.chip.sel{background:var(--azul-tinte);border-color:var(--azul);color:var(--azul-osc)}
.slot.sel{background:var(--azul);border-color:var(--azul)}
.slot .pr{color:var(--azul-osc)}
.slot:hover{border-color:var(--azul)}
.cal-d.sel{background:var(--azul)}
.cal-modo button.on{border-color:var(--azul);box-shadow:0 0 0 1.5px var(--azul) inset}
.hchip.sel{background:var(--azul);border-color:var(--azul)}
.panel{border-radius:14px}
.galeria{border-radius:10px}
.precio{color:var(--carbon)}
.pill{background:var(--azul-tinte);color:var(--azul-osc)}
.check{background:var(--azul-tinte)}
.login-box{background:var(--azul-suave);border:1px solid var(--azul-tinte)}
.acc-local .btn{min-height:46px;font-size:16px}.acc-local .btn svg{flex:none}
.acc-local .btn.dark:hover{background:#000}
.pill.sello-ok{background:var(--ok-fg);color:#fff}
.sr-solo-pie{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0)}
/* login (/entrar): tarjeta centrada + ilustración a la izquierda (Frame 7) */
.entrar-esc{position:relative}
.entrar-esc .ilus{display:none}
@media(min-width:1200px){.entrar-esc .ilus{display:block;position:absolute;left:calc(50% - 560px);bottom:-40px;width:300px;height:auto;pointer-events:none;z-index:0}}
.entrar-esc>.panel{position:relative;z-index:1;padding:40px 36px 30px;border-radius:20px;box-shadow:0 10px 40px rgba(48,86,237,.10)}
.entrar-logo{display:flex;flex-direction:column;align-items:center;gap:22px;margin:6px 0 20px;text-decoration:none}
.entrar-logo img:first-child{width:122px;height:auto}.entrar-logo img+img{width:min(300px,80%);height:auto}
@media(max-width:560px){.entrar-esc>.panel{padding:28px 20px 22px}.entrar-logo img:first-child{width:90px}}
/* Libro de Reclamaciones y páginas legales */
.lr-cab{display:flex;align-items:center;gap:14px;color:var(--azul)}
.lr-cab h1{color:var(--azul)}
/* ═════════ 6. móvil ═════════ */
@media(max-width:1060px){.cab-links a{padding:10px 10px;font-size:14px}}
@media(max-width:900px){
  .cl-barra .cab{height:64px;gap:10px}.cl-barra .cab-logo{height:64px}
  .cab-links{display:none}
  .cl-barra .cab-der a.host{display:none}
  .wm-cl .wm-ico{height:34px}.wm-cl .wm-txt{height:14px}
  .cl-barra .cab.anfitrion{flex-wrap:wrap;height:auto;row-gap:0;padding-top:0}
  .cl-barra .cab.anfitrion .cab-tabs{order:3;flex:0 0 100%;height:48px;justify-content:flex-start;margin:0 -20px;padding:0 20px;width:auto}
  .cl-fila-tabs .cab-tabs{justify-content:flex-start;margin:0 -20px;padding:10px 20px}
  .cl-banda.grande{padding:18px 0 14px}
  .cl .busq{height:60px;border-radius:16px}
  .cl .busq .seg{padding:0 10px}.cl .busq .seg small{font-size:13px;gap:5px}.cl .busq .seg small svg{width:15px;height:15px}
  .cl .busq .lupa{width:44px;height:44px;padding:0;margin-right:8px}
  .cl-banda .barra-filtros{justify-content:flex-start}
  .cl-banda .barra-filtros .qchips{flex:1;flex-wrap:nowrap;justify-content:flex-start;overflow-x:auto}
  .cl-banda .busq-mini,.cl-banda a.busq-mini{width:100%;height:54px;padding:0 16px;gap:12px}
  .cl-banda .busq-mini span,.cl-banda .busq-mini>i:last-child{display:none}
  .cl-banda .busq-mini .lupa-mov{display:inline-flex;width:auto;height:auto;background:transparent;color:var(--azul);margin:0}.cl-banda .busq-mini .lupa-mov svg{width:18px;height:18px}
  .cl-banda .busq-mini .mov{display:flex;flex-direction:column;min-width:0;line-height:1.2}
  .cl-banda .busq-mini .mov b{font-size:14px;font-weight:800}.cl-banda .busq-mini .mov small{font-size:12px;color:var(--tenue);font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  body.pcg-msj .cl-banda{display:none}
  .tit h2{font-size:21px}
}
@media(max-width:744px){.cl-barra .cab.anfitrion .cab-tabs,.cl-fila-tabs .cab-tabs{margin:0 -24px;padding-left:24px;padding-right:24px}}
@media(max-width:560px){
  .cl-barra .cab.anfitrion .cab-tabs,.cl-fila-tabs .cab-tabs{margin:0 -16px;padding-left:16px;padding-right:16px}
  .entrar-pill{padding:0 14px}.entrar-pill .l{display:none}.entrar-pill .c{display:inline}
  .wm-cl{gap:8px}.wm-cl .wm-ico{height:30px}.wm-cl .wm-txt{height:12px}
}
@media(max-width:380px){.wm-cl .wm-txt{display:none}}
/* el chat a pantalla completa en el celular sigue sin la cabecera del sitio */
@media(max-width:899px){body.pcg-chat .cl-barra,body.pcg-chat .cl-fila-tabs,body.pcg-chat .cl-banda{display:none}}
"""
