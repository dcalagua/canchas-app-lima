"""CSS de las vistas del modo anfitrión · Mi perfil del anfitrión — web/anfitrion_perfil.py.

Va después del kit (`web/vista_anfitrion.py`). Solo tokens (`--azul`, `--anf-*`).
"""

CSS = r"""
/* ═════════ MODO ANFITRIÓN · Mi perfil (captura "CanchaLibre Perfil") ═════════ */
.vp .vh{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
.vp-grid{display:grid;grid-template-columns:minmax(0,300px) minmax(0,1fr);gap:20px;align-items:start}
.vp-lado{display:flex;flex-direction:column;gap:16px;position:sticky;top:96px;min-width:0}
.vp-main{display:flex;flex-direction:column;gap:16px;min-width:0}
.vp-card{background:#fff;border:1px solid var(--anf-borde);border-radius:16px;min-width:0}
.vp-sec{padding:22px 24px;scroll-margin-top:96px}
.vp-ic{width:36px;height:36px;border-radius:10px;display:inline-flex;align-items:center;justify-content:center;flex:none}
.vp-ic.suave{background:var(--azul-tinte);color:var(--azul)}
.vp-ic.azul{background:var(--azul);color:#fff;width:32px;height:32px;border-radius:8px}
/* identidad */
.vp-yo{padding:24px 20px 20px;text-align:center;display:flex;flex-direction:column;align-items:center}
.vp-av{position:relative;width:92px;height:92px;margin-bottom:12px}
.vp-av img,.vp-av .ini{width:92px;height:92px;border-radius:50%;object-fit:cover;display:flex;align-items:center;justify-content:center;background:var(--azul);color:#fff;font-size:38px;font-weight:700}
.vp-cam{position:absolute;right:-6px;bottom:-6px;width:44px;height:44px;border-radius:50%;border:0;background:transparent;display:flex;align-items:center;justify-content:center;cursor:pointer;padding:0;color:var(--azul)}
.vp-cam svg{box-sizing:content-box;background:#fff;border:2px solid var(--azul-tinte);border-radius:50%;padding:5px;box-shadow:0 2px 6px rgba(20,33,90,.15)}
.vp-cam:hover svg{background:var(--azul-tinte)}
.vp-cam:focus-visible{outline:none}.vp-cam:focus-visible svg{box-shadow:var(--foco)}
.vp-nom{font-size:19px;color:var(--anf-texto);line-height:1.25;overflow-wrap:anywhere}
.vp-mail{font-size:13px;color:var(--anf-tenue);margin-top:4px;overflow-wrap:anywhere}
.vp-pills{display:flex;flex-wrap:wrap;justify-content:center;gap:6px;margin-top:12px}
.vp-cuenta{margin:12px 0 0;font-size:13px;font-weight:700;color:var(--anf-texto)}
/* menú de secciones */
.vp-nav{padding:10px;display:flex;flex-direction:column;gap:2px}
.vp-nav a,.vp-salir{display:flex;align-items:center;gap:12px;min-height:46px;padding:0 12px;border-radius:10px;color:var(--anf-texto);text-decoration:none;font-weight:700;font-size:15px;position:relative;background:none;border:0;font-family:inherit;cursor:pointer;text-align:left;width:100%}
.vp-nav a svg{color:var(--anf-tenue);flex:none}
.vp-nav a span{flex:1;min-width:0}
.vp-nav a i{font-style:normal;color:var(--anf-tenue);font-size:20px;line-height:1}
.vp-nav a:hover{background:var(--anf-fondo)}
.vp-nav a[aria-current]{background:var(--azul-tinte);color:var(--azul-osc)}
.vp-nav a[aria-current] svg{color:var(--azul)}
.vp-nav a[aria-current]:before{content:"";position:absolute;left:-10px;top:8px;bottom:8px;width:3px;border-radius:3px;background:var(--azul)}
.vp-salir{color:var(--anf-rojo);margin-top:8px;border-top:1px solid var(--anf-linea);border-radius:0 0 10px 10px;padding-top:6px}
.vp-salir:hover{background:var(--bad-bg)}
/* cabecera de cada panel */
.vp-pcab{display:flex;align-items:center;gap:14px;flex-wrap:wrap}
.vp-pcab-t{flex:1 1 240px;min-width:0}
.vp-pcab h2{font-size:18px;margin:0;color:var(--anf-texto);font-weight:700}
.vp-pcab p{margin:3px 0 0;font-size:13.5px;color:var(--anf-tenue)}
.vp-pcab-acc{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.vp-pcab-acc .btn,.vp .btn{display:inline-flex;align-items:center;gap:8px;justify-content:center;text-decoration:none;margin:0}
/* formulario */
.vp-form{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px 18px;margin-top:20px}
.vp-campo,.vp label.vp-campo{display:flex;flex-direction:column;gap:6px;min-width:0;margin:0;font-weight:400}
.vp-campo>span:first-child{font-size:13px;font-weight:700;color:var(--anf-texto)}
.vp-in{display:flex;align-items:center;gap:10px;border:1px solid var(--anf-borde);border-radius:10px;padding:0 12px;background:#fff;min-height:46px;color:var(--anf-tenue);min-width:0}
.vp-in:focus-within{border-color:var(--azul);box-shadow:var(--foco)}
.vp-in input,.vp-in select{border:0;background:transparent;font:inherit;font-size:15px;color:var(--anf-texto);flex:1;min-width:0;width:auto;padding:12px 0;margin:0;box-shadow:none}
.vp-in input:focus,.vp-in select:focus{outline:none;box-shadow:none}
.vp-in.bloq{background:var(--anf-fondo)}
.vp-in.bloq input{color:var(--anf-tenue)}
.vp-cel{display:flex;gap:8px;min-width:0}
.vp-cel select{flex:none;width:auto;max-width:120px;border:1px solid var(--anf-borde);border-radius:10px;background:#fff;font:inherit;font-size:14px;font-weight:700;color:var(--anf-texto);padding:0 10px;min-height:46px;margin:0}
.vp-cel select:focus{border-color:var(--azul);box-shadow:var(--foco);outline:none}
.vp-cel .vp-in{flex:1}
.vp-err{color:var(--anf-rojo);font-size:13px;font-weight:600;min-height:0}
.vp-err:empty{display:none}
/* saldo y suscripciones */
.vp-tarjetas{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px;margin-top:18px}
.vp-tarjetas.tres{grid-template-columns:repeat(3,minmax(0,1fr))}
.vp-t{border:1px solid var(--anf-borde);border-radius:14px;padding:16px;display:flex;flex-direction:column;gap:4px;min-width:0}
.vp-t-top{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:8px}
.vp-t>small{font-size:13px;color:var(--anf-tenue)}
.vp-t-v{font-size:21px;color:var(--anf-texto);line-height:1.2;overflow-wrap:anywhere}
.vp-t-v.cero{color:var(--anf-rojo)}.vp-t-v.bad{color:var(--anf-rojo)}
.vp-t small.vp-t-nota{font-size:12.5px;color:var(--anf-tenue)}
.vp-t-ir{margin-top:auto;padding-top:8px;font-weight:700;font-size:14px;color:var(--azul);text-decoration:none;min-height:32px;display:inline-flex;align-items:center}
.vp-t-ir:hover{text-decoration:underline}
/* notificaciones */
.vp-av-lista{margin-top:12px}
.vp-av-f{display:flex;align-items:center;gap:14px;padding:12px 0;border-top:1px solid var(--anf-linea)}
.vp-av-ic{color:var(--azul);display:inline-flex;flex:none}
.vp-av-f .tx{flex:1;min-width:0;display:flex;flex-direction:column}
.vp-av-f .tx b{font-size:15px;color:var(--anf-texto)}
.vp-av-f .tx small{font-size:13px;color:var(--anf-tenue)}
.vp-sw{flex:none;width:58px;height:44px;border:0;background:transparent;padding:0;cursor:pointer;display:flex;align-items:center;justify-content:center}
.vp-sw i{display:block;width:46px;height:26px;border-radius:999px;background:var(--trazo);position:relative;transition:background .15s}
.vp-sw i:after{content:"";position:absolute;left:3px;top:3px;width:20px;height:20px;border-radius:50%;background:#fff;box-shadow:0 1px 3px rgba(0,0,0,.25);transition:transform .15s}
.vp-sw[aria-checked='true'] i{background:var(--azul)}
.vp-sw[aria-checked='true'] i:after{transform:translateX(20px)}
.vp-sw:focus-visible{outline:none}.vp-sw:focus-visible i{box-shadow:var(--foco)}
.vp-nota{display:flex;gap:10px;align-items:flex-start;margin:12px 0 0;padding:12px 14px;border-radius:12px;background:var(--anf-fondo);font-size:13px;color:var(--anf-texto);line-height:1.45}
.vp-nota svg{flex:none;color:var(--azul);margin-top:1px}
/* preferencias y privacidad */
.vp-dos{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;align-items:stretch}
.vp-dos .vp-campo{margin-top:20px}
.vp-in.sel{padding-right:6px}
.vp-flag{display:inline-flex;flex:none}.vp-flag svg{width:22px;height:auto;border-radius:3px}
.vp-in.sel select{cursor:pointer}
.vp-in.sel select:disabled{cursor:not-allowed;color:var(--anf-tenue)}
.vp-ayuda{display:block;margin:8px 0 0;font-size:13px;color:var(--anf-tenue);line-height:1.4}
.vp-ayuda.warn{color:var(--warn-fg)}
.vp-pf-lista{margin-top:12px}
.vp-pf{display:flex;align-items:center;gap:12px;width:100%;min-height:52px;padding:6px 0;border:0;border-top:1px solid var(--anf-linea);background:none;font:inherit;text-align:left;cursor:pointer;color:var(--anf-texto);text-decoration:none}
.vp-pf-ic{color:var(--anf-tenue);display:inline-flex;flex:none}
.vp-pf .tx{flex:1;min-width:0;font-weight:700;font-size:15px}
.vp-pf .ir{font-weight:700;font-size:13.5px;color:var(--azul);white-space:nowrap}
.vp-pf:hover .tx{color:var(--azul)}
.vp-pf.rojo .tx,.vp-pf.rojo .ir,.vp-pf.rojo .vp-pf-ic{color:var(--anf-rojo)}
.vp-solo-mov{display:none}
@media(max-width:1100px){.vp-tarjetas.tres{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:1000px){.vp-dos{grid-template-columns:minmax(0,1fr)}}
@media(max-width:860px){
  .vp-grid{grid-template-columns:minmax(0,1fr);gap:14px}
  .vp-lado{position:static;gap:12px}
  /* el menú pasa arriba como tira desplazable */
  .vp-nav{flex-direction:row;overflow-x:auto;gap:6px;padding:8px;scrollbar-width:none;position:sticky;top:64px;z-index:5}
  .vp-nav::-webkit-scrollbar{display:none}
  .vp-nav a{flex:none;width:auto;white-space:nowrap;min-height:44px;font-size:14px;padding:0 14px;border-radius:999px;background:var(--anf-fondo)}
  .vp-nav a i{display:none}
  .vp-nav a[aria-current]:before{display:none}
  .vp-nav a[aria-current]{background:var(--azul);color:#fff}.vp-nav a[aria-current] svg{color:#fff}
  .vp-salir{display:none}
  .vp-solo-mov{display:flex}
  .vp-sec{scroll-margin-top:150px}
}
@media(max-width:600px){
  .vp-sec{padding:16px}
  .vp-form{grid-template-columns:minmax(0,1fr)}
  .vp-tarjetas,.vp-tarjetas.tres{grid-template-columns:minmax(0,1fr)}
  .vp-pcab-acc{width:100%}.vp-pcab-acc .btn{flex:1}
  .vp-yo{flex-direction:row;flex-wrap:wrap;text-align:left;align-items:center;gap:0 14px;padding:16px}
  .vp-av{width:72px;height:72px;margin:0}.vp-av img,.vp-av .ini{width:72px;height:72px;font-size:30px}
  .vp-yo .vp-nom{flex:1;min-width:0;font-size:17px}
  .vp-mail{width:100%;order:3;margin-top:8px}
  .vp-pills{justify-content:flex-start;order:4;width:100%}
  .vp-cuenta{order:5;width:100%}
}
"""
