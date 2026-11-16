"""MI TIENDA en la web (Modo anfitrión → Mi tienda): el mismo Marketplace del
app (`mis_productos_screen` + `editar_producto_screen`) desde la laptop.

Lista de productos (publicados y pausados), publicar/editar (foto, nombre,
categoría, descripción, precio en la moneda del país, stock, publicado),
pausar/publicar, eliminar y las VENTAS del backend (órdenes en custodia,
`stores.ventas`). Misma tabla `pichangol_productos` y bucket `productos`
que el app. Candado = el del app: `puedeVender` = identidad verificada o
dueño de canchas.
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone

from starlette.concurrency import run_in_threadpool
from config import MARCA  # noqa: E402 — nombre y dominio de marca (un solo lugar)

_JSON_INVALIDO = object()


def _leer_json(v):
    """El wrapper async ya leyó el JSON en el event loop; aquí solo se valida (la lógica corre en el threadpool, sin frenar el loop)."""
    if v is _JSON_INVALIDO:
        raise ValueError("json inválido")
    return v
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

import paises
from db.store import stores
import config
from web import almacen, catalogos, datos, sesion, ui
from web import estilos_v_comercio as vc
from web import vista_anfitrion as va
from web.anfitrion import _en_segundo_plano, _entrar, _sesion_o_entrar
from web.router import PLAY_URL, e

router = APIRouter(tags=["web-anfitrion-tienda"])
BUCKET = "productos"


def _puede_vender(email: str) -> bool:
    """Espejo de `appState.puedeVender`: verificado O dueño de canchas."""
    return datos.esta_verificado(email) or bool(datos.canchas_de_dueno(email))


def _moneda_defecto(email: str) -> str:
    """Moneda del país de su 1.ª cancha (como `paisActual.moneda` del dueño); S/ si no tiene."""
    cs = datos.canchas_de_dueno(email)
    if cs:
        iso = paises.pais_de_coordenadas(cs[0].get("lat"), cs[0].get("lng"))
        return paises.simbolo_de_moneda(paises.moneda_de_pais(iso))
    return "S/"


def _shell(titulo: str, cuerpo: str, ses: dict, tab: str) -> HTMLResponse:
    # La barra del modo anfitrión la pone `ui.shell` sola en toda ruta /anfitrion/*.
    return ui.shell(titulo, va.vista(cuerpo, "vc-tienda"), sesion=ses, ancho=True, titulo_tab=tab)


def _candado(ses: dict) -> HTMLResponse:
    cta = (f"<div class='va-cab-acc' style='justify-content:center'><a class='btn' href='{PLAY_URL}' rel='noopener'>Abrir en la app</a>"
           "<a class='btn sec' href='/anfitrion'>Volver al inicio</a></div>")
    cuerpo = (va.cabecera("Mi tienda", f"Vende en el Marketplace {MARCA}: el comprador paga en la app y coordinas la entrega por chat.")
              + va.panel(va.vacio("escudo", "Verifica tu identidad para vender",
                                  f"En el Marketplace {MARCA} venden dueños de canchas y jugadores con identidad verificada "
                                  "(badge «Vendedor verificado ✓»). Verifícate desde la app: Perfil → Verificar identidad.", cta)))
    return _shell("Mi tienda", cuerpo, ses, "Mi tienda · Modo anfitrión")


def _stock_txt(stock) -> tuple[str, bool]:
    """(texto, en rojo)."""
    if stock is None:
        return "Stock ilimitado", False
    if stock <= 0:
        return "Sin stock", True
    if stock == 1:
        return "Último en stock", True
    return f"Stock {stock}", False


def _tarjeta(p: dict) -> str:
    cat = catalogos.CATEGORIAS_PRODUCTO.get(p["categoria"], ("Otros", "📦"))
    foto = (f"<img src='{e(p['foto_url'])}' alt='' loading='lazy'>" if p["foto_url"]
            else f"<span class='vc-ph'>{vc.ico('imagen', 56, 1.6)}</span>")
    pill = va.pill("Publicado", "ok", "check") if p["activo"] else va.pill("Pausado", "gris", "pausa")
    st, rojo = _stock_txt(p["stock"])
    activo = bool(p["activo"])
    return (f"<article class='vc-prod' data-id='{e(p['id'])}' data-estado='{'pub' if activo else 'pau'}'>"
            f"<div class='vc-prod-f'>{foto}{pill}</div><div class='vc-prod-b'><h3>{e(p['nombre'])}</h3>"
            f"<div class='vc-prod-m'><span class='vc-cat'>{cat[1]} {e(cat[0])}</span><span class='vc-st{' bajo' if rojo else ''}'>{e(st)}</span></div>"
            f"<div class='vc-precio'>{e(p['moneda'])} {p['precio']:.2f}</div>"
            "<div class='vc-prod-acc'>"
            f"<a class='btn sec' href='/anfitrion/tienda/{e(p['id'])}/editar'>{vc.ico('lapiz', 16)}Editar</a>"
            f"<button type='button' class='btn sec' data-activo='{e(p['id'])}' data-v='{0 if activo else 1}'>"
            f"{vc.ico('pausa' if activo else 'play', 16)}{'Pausar' if activo else 'Publicar'}</button>"
            f"<button type='button' class='btn peligro vc-ico-btn vc-borrar' data-eliminar='{e(p['id'])}' aria-label='Eliminar {e(p['nombre'])}' "
            f"title='Eliminar'>{vc.ico('papelera', 18)}</button>"
            "</div></div></article>")


def _ventas_de(email: str) -> list:
    return sorted([v for v in stores.ventas if (v.vendedor_email or "").lower() == email],
                  key=lambda v: str(v.creado_en), reverse=True)


def neto_por_recibir(email: str) -> dict[str, float]:
    """Neto de las VENTAS del Marketplace aún no liquidadas, POR MONEDA (ISO →
    monto). Misma cuenta que "Por recibir" de la billetera
    (`stores.liquidaciones` + `_liquidacion_dict`), solo las de tipo
    `venta_producto`; nunca se suman soles con dólares."""
    from pagos.router import _liquidacion_dict, moneda_iso
    out: dict[str, float] = {}
    for p in stores.liquidaciones(solo_pendientes=True):
        if p.tipo != "venta_producto" or (p.dueno_id or "").strip().lower() != email:
            continue
        iso = moneda_iso(p.moneda)
        out[iso] = round(out.get(iso, 0.0) + float(_liquidacion_dict(p)["neto_soles"]), 2)
    return out


_ESTADO_VENTA = {"pagado": ("Pagado · retenido", "warn"), "entregado": ("Entregado", "azul"), "recibido": ("Recibido · liberado", "ok"),
                 "liberado": ("Liberado", "ok"), "disputado": ("En disputa", "bad")}

_JS_TIENDA = r"""
document.addEventListener('click',async function(ev){
  var f=ev.target.closest('[data-filtro]');if(f){var v=f.dataset.filtro;document.querySelectorAll('[data-filtro]').forEach(function(b){var s=b===f;b.classList.toggle('sel',s);b.setAttribute('aria-pressed',s?'true':'false')});
    var n=0;document.querySelectorAll('.vc-prod').forEach(function(c){var ok=v==='todos'||c.dataset.estado===v;c.hidden=!ok;if(ok)n++});var x=document.getElementById('tdSin');if(x)x.hidden=n>0;return}
  var a=ev.target.closest('[data-activo]');if(a){a.disabled=true;try{var j=await (await fetch('/anfitrion/tienda/'+encodeURIComponent(a.dataset.activo)+'/activo',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({activo:a.dataset.v==='1'})})).json();if(j.ok){pcgRecargar(a.dataset.v==='1'?'Publicando…':'Pausando…');return}pcgToast(j.error||'No se pudo guardar.')}catch(e){pcgToast('No se pudo guardar.')}a.disabled=false;return}
  var d=ev.target.closest('[data-eliminar]');if(d){if(!await pcgConfirmar({titulo:'Eliminar producto',mensaje:'Se quita del Marketplace y se borra su foto.',confirmar:'Eliminar',destructivo:true}))return;d.disabled=true;pcgCargando('Eliminando…');try{var j=await (await fetch('/anfitrion/tienda/'+encodeURIComponent(d.dataset.eliminar)+'/eliminar',{method:'POST'})).json();if(j.ok){pcgRecargar();return}pcgCargando(false);pcgToast(j.error||'No se pudo eliminar.')}catch(e){pcgCargando(false);pcgToast('No se pudo eliminar.')}d.disabled=false}
});
"""


@router.get("/anfitrion/tienda", response_class=HTMLResponse)
def pagina_tienda(request: Request, guardado: str = "") -> HTMLResponse:
    ses, resp = _sesion_o_entrar(request, "/anfitrion/tienda")
    if resp is not None:
        return resp
    email = ses["email"]
    if not _puede_vender(email):
        return _candado(ses)
    from pagos.router import moneda_iso, moneda_simbolo
    prods = datos.productos_de_vendedor(email)
    ventas = _ventas_de(email)
    activos = sum(1 for p in prods if p["activo"])
    mon_def = _moneda_defecto(email)
    iso_def = moneda_iso(mon_def)
    # Neto por recibir POR MONEDA: la principal (la del país del vendedor) grande y las otras como "+ $ 20.00".
    neto = neto_por_recibir(email)
    principal = iso_def if (iso_def in neto or not neto) else max(neto, key=lambda k: neto[k])
    neto_v = f"{e(moneda_simbolo(principal))} {neto.get(principal, 0.0):.2f}"
    otras = " · ".join(f"+ {moneda_simbolo(k)} {v:.2f}" for k, v in neto.items() if k != principal)
    pct = config.COMISION_PORC
    kpis = va.kpis([
        va.kpi("tienda", "Productos", str(len(prods)), sub=f"{activos} publicado{'s' if activos != 1 else ''}"),
        va.kpi("recibo", "Ventas", str(len(ventas)), sub="órdenes del Marketplace"),
        va.kpi("billete", "Neto por recibir", neto_v, sub=otras or "de ventas por liquidar"),
        va.kpi("etiqueta", f"Comisión {MARCA}", f"{pct:g} %",
               sub=f"mín. {moneda_simbolo(iso_def)} {config.comision_min(iso_def):.2f} por venta"),
    ])
    aviso = va.aviso("Producto guardado. Ya se ve en el Marketplace de la app.", "ok", ico="check") if guardado else ""
    if prods:
        seg = ("<div class='va-seg' role='group' aria-label='Filtrar productos'>"
               f"<button type='button' class='sel' data-filtro='todos' aria-pressed='true'>Todos<i>{len(prods)}</i></button>"
               f"<button type='button' data-filtro='pub' aria-pressed='false'>Publicados<i>{activos}</i></button>"
               f"<button type='button' data-filtro='pau' aria-pressed='false'>Pausados<i>{len(prods) - activos}</i></button></div>")
        grid = (f"<div class='vc-sec-t'><b>Productos</b>{seg}</div><div class='vc-prods'>{''.join(_tarjeta(p) for p in prods)}</div>"
                "<p class='vc-nota' id='tdSin' hidden>No hay productos con ese filtro.</p>")
    else:
        grid = va.panel(va.vacio("tienda", "Aún no publicas productos",
                                 f"Raquetas, pelotas, indumentaria… lo que vendas llega a todos los jugadores de {MARCA}.",
                                 f"<a class='btn' href='/anfitrion/tienda/nuevo'>{vc.ico('bolsa', 18)}Publicar mi primer producto</a>"))
    por_id = {p["id"]: p for p in prods}
    filas_v = []
    for v in ventas[:100]:
        mon = (por_id.get(v.producto_id) or {}).get("moneda") or mon_def
        txt, tono = _ESTADO_VENTA.get(v.estado, (v.estado, "gris"))
        filas_v.append([e(str(v.creado_en)[:10]), f"<b>{e(v.producto_nombre)}</b>",
                        f"{e(v.comprador_nombre or v.comprador_email)}<small>{e(v.comprador_email)}</small>",
                        f"{e(mon)} {float(v.monto_soles or 0):.2f}", va.pill(txt, tono)])
    if ventas:
        sec_ventas = va.panel(va.tabla(["Fecha", "Producto", "Comprador", "Monto", "Estado"], filas_v), "Ventas",
                              f"{len(ventas)} venta{'s' if len(ventas) != 1 else ''} · el dinero queda retenido hasta que el comprador confirme que recibió",
                              id_="ventas")
    else:
        sec_ventas = va.panel("<div class='vc-vacio-fila'>" + va.icono("tienda", "claro") + "<div><b>Todavía no tienes ventas.</b>"
                              "<small>Cuando un jugador compre, verás aquí la orden y coordinarás la entrega por chat en la app.</small></div></div>",
                              "Ventas", id_="ventas")
    cuerpo = (va.cabecera("Mi tienda", f"Vende en el Marketplace {MARCA}: el comprador paga en la app y coordinas la entrega por chat.",
                          acciones=f"<a class='btn' href='/anfitrion/tienda/nuevo'>{vc.ico('bolsa', 18)}Publicar producto</a>")
              + aviso + kpis + grid + sec_ventas + f"<script>{_JS_TIENDA}</script>")
    from web.anfitrion import JS_PAGAR  # pcgToast
    cuerpo += f"<script>{JS_PAGAR}</script>"
    return _shell("Mi tienda", cuerpo, ses, "Mi tienda · Modo anfitrión")


def _mio(email: str, pid: str) -> dict | None:
    return next((p for p in datos.productos_de_vendedor(email) if p["id"] == pid), None)


@router.get("/anfitrion/tienda/nuevo", response_class=HTMLResponse)
def pagina_nuevo_producto(request: Request) -> HTMLResponse:
    ses, resp = _sesion_o_entrar(request, "/anfitrion/tienda/nuevo")
    if resp is not None:
        return resp
    if not _puede_vender(ses["email"]):
        return _candado(ses)
    nuevo = {"id": f"prod_{int(time.time() * 1_000_000)}_w", "nombre": "", "descripcion": "", "precio": 0.0,
             "moneda": _moneda_defecto(ses["email"]), "categoria": "otros", "foto_url": "", "stock": None, "activo": True}
    return _editor(ses, nuevo, nuevo=True)


@router.get("/anfitrion/tienda/{pid}/editar", response_class=HTMLResponse)
def pagina_editar_producto(request: Request, pid: str) -> HTMLResponse:
    ses, resp = _sesion_o_entrar(request, f"/anfitrion/tienda/{pid}/editar")
    if resp is not None:
        return resp
    p = _mio(ses["email"], pid)
    if p is None:
        from web.router import _no_encontrada
        r = _no_encontrada("Este producto no es tuyo"); r.status_code = 404
        return r
    return _editor(ses, p, nuevo=False)


def _editor(ses: dict, p: dict, *, nuevo: bool) -> HTMLResponse:
    cats = "".join(f"<button type='button' class='chip{' sel' if k == p['categoria'] else ''}' data-g='categoria' data-v='{k}'>{ico} {e(n)}</button>"
                   for k, (n, ico) in catalogos.CATEGORIAS_PRODUCTO.items())
    monedas = "".join(f"<button type='button' class='chip{' sel' if m == p['moneda'] else ''}' data-g='moneda' data-v='{m}'{' disabled' if not nuevo else ''}>{m}</button>"
                      for m in catalogos.MONEDAS)
    foto = f"<img src='{e(p['foto_url'])}' alt=''>" if p["foto_url"] else "<span class='ph'>📷</span>"
    cfg = {"id": p["id"], "foto": p["foto_url"], "nuevo": nuevo, "storage": almacen.disponible()}
    cab = va.cabecera("Publicar producto" if nuevo else "Editar producto",
                      f"Aparece en el Marketplace de todos los jugadores de {MARCA}." if nuevo else p["nombre"], volver="/anfitrion/tienda")
    cuerpo = f"""
{cab}
<div class='edit-grid'><nav class='edit-nav'><a class='edit-nav-it' href='#sec-foto'>Foto</a><a class='edit-nav-it' href='#sec-datos'>Producto</a><a class='edit-nav-it' href='#sec-precio'>Precio y stock</a></nav>
<form id='fProd' class='edit-form' autocomplete='off' novalidate>
 <section class='va-panel edit-sec' id='sec-foto'><h2>Foto</h2><p class='sub'>Una foto clara sobre fondo simple vende más.</p>
  <div class='foto-una' id='fotoBox'>{foto}</div>
  <div class='acciones' style='margin-top:12px'><label class='btn sec' for='inFoto'>📷 {'Subir foto' if not p['foto_url'] else 'Cambiar foto'}</label><input type='file' id='inFoto' accept='image/*' hidden{'' if almacen.disponible() else ' disabled'}>
  <span class='sub' id='fotoMsg' style='margin:0'>{'' if almacen.disponible() else 'La subida de fotos no está disponible en este ambiente; súbela desde la app.'}</span></div>
 </section>
 <section class='va-panel edit-sec' id='sec-datos'><h2>Producto</h2>
  <label for='nombre'>Nombre</label><input id='nombre' maxlength='80' value='{e(p['nombre'])}' placeholder='Ej. Raqueta Wilson Pro Staff'>
  <label>Categoría</label><div class='chips' data-grupo='categoria'>{cats}</div>
  <label for='desc'>Descripción <span class='req'>opcional</span></label><textarea id='desc' rows='3' maxlength='500' placeholder='Estado, marca, talla, detalles…'>{e(p['descripcion'])}</textarea>
 </section>
 <section class='va-panel edit-sec' id='sec-precio'><h2>Precio y stock</h2>
  <label>Moneda{'' if nuevo else ' <span class=req>fija al crear</span>'}</label><div class='chips' data-grupo='moneda'>{monedas}</div>
  <label for='precio'>Precio</label><div class='inp-moneda'><span id='monSpan'>{e(p['moneda'])}</span><input id='precio' type='number' min='0.5' step='0.5' inputmode='decimal' value='{p['precio']:.2f}' placeholder='0.00'></div>
  <label for='stock'>Stock <span class='req'>vacío = ilimitado</span></label><input id='stock' type='number' min='0' step='1' inputmode='numeric' value='{'' if p['stock'] is None else p['stock']}' placeholder='ilimitado' style='max-width:200px'>
  <label class='chk' style='margin-top:16px'><input type='checkbox' id='activo'{' checked' if p['activo'] else ''}> Publicado <small>(desmarcado = pausado, no aparece en el feed)</small></label>
 </section>
</form></div>
<div class='barra-guardar'><div class='wrap-xl'><span class='sub' id='msgGuardar' style='margin:0'>Se guarda en el Marketplace al instante.</span>
<button type='button' class='btn' id='btnGuardar'>{'Publicar' if nuevo else 'Guardar cambios'}</button></div></div>
<script>var CFG={ui.json_js(cfg, ensure_ascii=False)};</script><script>{_JS_EDITOR}</script>"""
    return _shell("Producto", cuerpo, ses, "Producto · Mi tienda")


_JS_EDITOR = r"""
(function(){
var foto=CFG.foto, subiendo=false;
function $(id){return document.getElementById(id)}
function sel(g){var b=document.querySelector(".chip.sel[data-g='"+g+"']");return b?b.dataset.v:''}
document.addEventListener('click',function(ev){var b=ev.target.closest('.chip[data-g]');if(!b||b.disabled)return;b.closest('.chips').querySelectorAll('.chip').forEach(function(x){x.classList.remove('sel')});b.classList.add('sel');if(b.dataset.g==='moneda')$('monSpan').textContent=b.dataset.v});
function comprimir(file){return new Promise(function(res,rej){var img=new Image(),url=URL.createObjectURL(file);img.onload=function(){var M=1200,w=img.width,h=img.height,k=Math.min(1,M/Math.max(w,h));var cv=document.createElement('canvas');cv.width=Math.round(w*k);cv.height=Math.round(h*k);cv.getContext('2d').drawImage(img,0,0,cv.width,cv.height);URL.revokeObjectURL(url);cv.toBlob(function(b){b?res(b):rej(new Error('img'))},'image/jpeg',0.85)};img.onerror=function(){URL.revokeObjectURL(url);rej(new Error('img'))};img.src=url})}
$('inFoto').addEventListener('change',async function(){var f=this.files&&this.files[0];this.value='';if(!f)return;var msg=$('fotoMsg');subiendo=true;msg.textContent='Subiendo foto…';
  try{var blob=await comprimir(f);var r=await fetch('/anfitrion/tienda/'+encodeURIComponent(CFG.id)+'/foto',{method:'POST',body:blob,headers:{'Content-Type':'image/jpeg'}});var j=await r.json();
    if(j.ok&&j.url){foto=j.url;$('fotoBox').innerHTML="<img src='"+foto.replace(/'/g,'&#39;')+"' alt=''>";msg.textContent=''}else{msg.textContent=j.error||'No se pudo subir la foto.'}}
  catch(e){msg.textContent='No se pudo subir la foto. Revisa tu conexión.'} subiendo=false});
$('btnGuardar').addEventListener('click',async function(){var btn=this,msg=$('msgGuardar');if(subiendo){msg.textContent='Espera a que termine de subir la foto.';return}
  var body={id:CFG.id,nombre:$('nombre').value,categoria:sel('categoria'),descripcion:$('desc').value,moneda:sel('moneda'),precio:parseFloat($('precio').value),stock:$('stock').value===''?null:parseInt($('stock').value),activo:$('activo').checked,foto_url:foto};
  btn.disabled=true;msg.classList.remove('err');msg.textContent='Guardando…';
  try{var r=await fetch('/anfitrion/tienda/guardar',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});var j=await r.json();
    if(j.ok){location.href='/anfitrion/tienda?guardado=1';return}msg.classList.add('err');msg.textContent=j.error||'No se pudo guardar.';if(j.campo){var el=document.getElementById('sec-'+j.campo);if(el)el.scrollIntoView({behavior:'smooth'})}}
  catch(e){msg.classList.add('err');msg.textContent='No se pudo guardar. Revisa tu conexión.'} btn.disabled=false});
})();
"""


def _sesion_vendedor(request: Request):
    ses = sesion.de_request(request)
    if not ses:
        return None, JSONResponse({"ok": False, "error": "sesion_requerida"}, status_code=401)
    if not _puede_vender(ses["email"]):
        return None, JSONResponse({"ok": False, "error": "Verifica tu identidad en la app para vender."}, status_code=403)
    return ses, None


def _id_ok(pid: str) -> bool:
    return bool(re.match(r"^prod_[0-9]{6,}(_w)?$", pid or ""))


@router.post("/anfitrion/tienda/guardar")
async def guardar_producto(request: Request) -> JSONResponse:
    try:
        _cuerpo_json = await request.json()
    except Exception:  # noqa: BLE001
        _cuerpo_json = _JSON_INVALIDO
    return await run_in_threadpool(_guardar_producto, request, _cuerpo_json)


def _guardar_producto(request: Request, _cuerpo_json) -> JSONResponse:
    ses, err = _sesion_vendedor(request)
    if err is not None:
        return err
    try:
        b = _leer_json(_cuerpo_json)
    except Exception:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": "Datos inválidos."}, status_code=400)
    if not isinstance(b, dict):
        return JSONResponse({"ok": False, "error": "Datos inválidos."}, status_code=400)
    email = ses["email"]
    pid = str(b.get("id") or "")
    if not _id_ok(pid):
        return JSONResponse({"ok": False, "error": "Producto inválido."}, status_code=400)
    actual = datos.producto_por_id(pid)
    if actual is not None and actual["vendedor_email"].lower() != email:
        return JSONResponse({"ok": False, "error": "Este producto no es tuyo."}, status_code=404)
    nombre = re.sub(r"\s+", " ", str(b.get("nombre") or "")).strip()[:80]
    if len(nombre) < 2:
        return JSONResponse({"ok": False, "error": "Ponle un nombre al producto.", "campo": "datos"}, status_code=400)
    categoria = str(b.get("categoria") or "otros")
    if categoria not in catalogos.CATEGORIAS_PRODUCTO:
        return JSONResponse({"ok": False, "error": "Elige una categoría.", "campo": "datos"}, status_code=400)
    try:
        precio = round(float(b.get("precio")), 2)
    except (TypeError, ValueError):
        return JSONResponse({"ok": False, "error": "Pon el precio.", "campo": "precio"}, status_code=400)
    if not (0 < precio <= 100000):
        return JSONResponse({"ok": False, "error": "El precio debe ser mayor a 0.", "campo": "precio"}, status_code=400)
    moneda = actual["moneda"] if actual else str(b.get("moneda") or _moneda_defecto(email))
    if moneda not in catalogos.MONEDAS:
        return JSONResponse({"ok": False, "error": "Moneda no válida.", "campo": "precio"}, status_code=400)
    stock = b.get("stock")
    if stock not in (None, ""):
        try:
            stock = int(stock)
        except (TypeError, ValueError):
            return JSONResponse({"ok": False, "error": "Stock inválido.", "campo": "precio"}, status_code=400)
        if stock < 0 or stock > 100000:
            return JSONResponse({"ok": False, "error": "Stock inválido.", "campo": "precio"}, status_code=400)
    else:
        stock = None
    foto = str(b.get("foto_url") or "").strip()
    propia = almacen.url_publica(f"{pid}.jpg", BUCKET) if almacen.disponible() else None  # misma ruta que sube `/foto`
    if foto and not ((actual and foto == actual["foto_url"]) or (propia and foto.startswith(propia))):
        foto = actual["foto_url"] if actual else ""
    fila = {"id": pid, "vendedor_email": email, "vendedor_nombre": (ses.get("nombre") or email)[:80], "nombre": nombre,
            "descripcion": str(b.get("descripcion") or "").strip()[:500], "precio": precio, "moneda": moneda,
            "categoria": categoria, "foto_url": foto, "stock": stock, "activo": bool(b.get("activo", True)),
            "creado_en": (actual or {}).get("creado_en") or datetime.now(timezone.utc).isoformat()}
    if not datos.guardar_producto(fila):
        return JSONResponse({"ok": False, "error": "No pudimos guardar en este momento. Inténtalo de nuevo."}, status_code=503)
    print(f"[tienda-web] {email} guardó {pid}: {nombre} · {moneda} {precio} · activo={fila['activo']}", flush=True)
    return JSONResponse({"ok": True, "id": pid})


@router.post("/anfitrion/tienda/{pid}/foto")
async def subir_foto_producto(request: Request, pid: str) -> JSONResponse:
    _cuerpo_bytes = await request.body()
    return await run_in_threadpool(_subir_foto_producto, request, pid, _cuerpo_bytes)


def _subir_foto_producto(request: Request, pid: str, _cuerpo_bytes: bytes = b"") -> JSONResponse:
    ses, err = _sesion_vendedor(request)
    if err is not None:
        return err
    if not _id_ok(pid):
        return JSONResponse({"ok": False, "error": "Producto inválido."}, status_code=400)
    actual = datos.producto_por_id(pid)
    if actual is not None and actual["vendedor_email"].lower() != ses["email"]:
        return JSONResponse({"ok": False, "error": "Este producto no es tuyo."}, status_code=404)
    if not almacen.disponible():
        return JSONResponse({"ok": False, "error": "La subida de fotos no está disponible en este ambiente."}, status_code=503)
    ctype = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    if ctype not in ("image/jpeg", "image/png", "image/webp"):
        return JSONResponse({"ok": False, "error": "Formato no admitido (usa JPG, PNG o WebP)."}, status_code=415)
    cuerpo = _cuerpo_bytes
    if not cuerpo or len(cuerpo) > almacen.MAX_BYTES:
        return JSONResponse({"ok": False, "error": "La foto pesa demasiado (máx. 6 MB)."}, status_code=413)
    url = almacen.subir(BUCKET, f"{pid}.jpg", cuerpo, ctype)  # misma ruta que el app (upsert)
    if not url:
        return JSONResponse({"ok": False, "error": "No se pudo subir la foto. Inténtalo de nuevo."}, status_code=502)
    return JSONResponse({"ok": True, "url": url})


@router.post("/anfitrion/tienda/{pid}/activo")
async def activar_producto(request: Request, pid: str) -> JSONResponse:
    try:
        _cuerpo_json = await request.json()
    except Exception:  # noqa: BLE001
        _cuerpo_json = _JSON_INVALIDO
    return await run_in_threadpool(_activar_producto, request, pid, _cuerpo_json)


def _activar_producto(request: Request, pid: str, _cuerpo_json) -> JSONResponse:
    ses, err = _sesion_vendedor(request)
    if err is not None:
        return err
    p = _mio(ses["email"], pid)
    if p is None:
        return JSONResponse({"ok": False, "error": "Producto no encontrado."}, status_code=404)
    try:
        b = _leer_json(_cuerpo_json)
    except Exception:  # noqa: BLE001
        b = {}
    p["activo"] = bool((b or {}).get("activo", True))
    if not datos.guardar_producto(p):
        return JSONResponse({"ok": False, "error": "No pudimos guardar en este momento."}, status_code=503)
    return JSONResponse({"ok": True, "activo": p["activo"]})


@router.post("/anfitrion/tienda/{pid}/eliminar")
async def eliminar_producto(request: Request, pid: str) -> JSONResponse:
    return await run_in_threadpool(_eliminar_producto, request, pid)


def _eliminar_producto(request: Request, pid: str) -> JSONResponse:
    ses, err = _sesion_vendedor(request)
    if err is not None:
        return err
    p = _mio(ses["email"], pid)
    if p is None:
        return JSONResponse({"ok": False, "error": "Producto no encontrado."}, status_code=404)
    if not datos.eliminar_producto(pid, ses["email"]):
        return JSONResponse({"ok": False, "error": "No pudimos eliminarlo en este momento."}, status_code=503)
    if p["foto_url"]:
        _en_segundo_plano(almacen.borrar_foto, p["foto_url"])
    print(f"[tienda-web] {ses['email']} eliminó {pid}", flush=True)
    return JSONResponse({"ok": True})
