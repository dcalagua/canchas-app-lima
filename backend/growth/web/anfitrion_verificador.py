"""VERIFICADOR y VERIFICACIÓN DE PROPIEDAD en la web (espejo del app).

Tres pantallas Dart, las mismas funciones del backend:

1. `verificador_screen.dart` → `GET /anfitrion/verificador` (pestaña
   "Visitas"): rol de CAMPO. Cola de visitas de verificación física
   (`verificacion_fisica.service.visitas`) por CERCANÍA a tu GPS (25 · 50 ·
   100 km · Todas, la más pedida primero); al tocar una visita: fotos del
   SITIO (cámara del celular) + firma (tu nombre) + GPS del navegador →
   `service.captura` (coincidencia ≤ `VERIF_COINCIDENCIA_MAX_M`). Fotos en el
   mismo bucket/carpeta que el app (`canchas/verif/<vf>_<i>_<ms>.jpg`).
2. `validar_reclamo_screen.dart` → pestaña "Validar por código": el
   motorizado ingresa el CÓDIGO del reclamo estando EN el local; su GPS debe
   quedar a ≤ `RECLAMO_VALIDACION_GPS_MAX_M` de la cancha
   (`propiedad.reclamos.validar_en_sitio`, que activa o deja
   `validada_pendiente_admin` según `VALIDADOR_ACTIVA_AUTOMATICO`). Fotos
   opcionales en `canchas/validacion/`.
   Quién puede: igual que el app, cualquier cuenta con sesión (el app no
   tiene un rol aparte: la tarjeta "Verificador" sale a todos en Modo
   anfitrión; la seguridad es código + GPS). Endurecimiento web: tope de
   intentos fallidos por cuenta e IP (anti fuerza bruta del código de 6
   dígitos) y nadie valida SU PROPIO reclamo.
3. `verificar_propiedad_screen.dart` + el panel "pendiente" de
   `club_detalle_screen.dart` → `GET /anfitrion/verificacion/{cancha_id}`:
   estado REAL del reclamo con línea de tiempo, "Verificar estado ahora"
   (`reclamos.estado`; si ya fue aprobado repara el espejo en la nube con
   `datos.marcar_verificada`, que es lo que hacía el app al sincronizar),
   "Reenviar solicitud de verificación" / "Volver a solicitar"
   (`reclamos.crear_reclamo`, idempotente: recuerda al admin o crea uno nuevo
   si el anterior se perdió o fue rechazado) y el código por WhatsApp al
   teléfono del local (`propiedad.service.solicitar/confirmar`). Solo para
   canchas del correo de la sesión.
   Diferencia deliberada con el app: en la web el OTP NO activa la cancha
   (`confirmar(activar=False)`): prueba que controlas ese WhatsApp y queda
   como EVIDENCIA en el reclamo (nota + aviso al admin con el código para
   aprobar). Existir/tener el teléfono ≠ ser el dueño; la propiedad la da el
   reclamo aprobado (CLAUDE.md "Flujo de PROPIEDAD"). La pantalla del app que
   sí activaba no está enlazada en ninguna parte del APK.
"""

from __future__ import annotations

import json
import re
import threading
import time
from collections import defaultdict, deque

from fastapi import APIRouter, Body, Request
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.concurrency import run_in_threadpool

import config
import paises
from db.store import stores
from propiedad import reclamos
from propiedad import service as otp_svc
from verificacion_fisica import service as vf_svc
from web import almacen, catalogos, datos, ui
from web.anfitrion import _ESTADO_RECLAMO, _sesion_o_entrar, aviso_fotos_reclamo
from web.router import PLAY_URL, e

router = APIRouter(tags=["web-anfitrion-verificador"])

RADIOS = (25, 50, 100, None)          # km (None = todas), como el app
MAX_FOTOS = 6
_NO_TERMINALES = ("pendiente_triage", "aprobado_triage", "pendiente_validacion", "validada_pendiente_admin")
_REF_RE = re.compile(r"^[A-Za-z0-9_-]{1,40}$")

# ── Anti fuerza bruta (en memoria, por cuenta y por IP) ──────────────────────
_LIM = {"codigo": (8, 30 * 60), "captura": (12, 30 * 60), "otp_envio": (5, 60 * 60)}
_hits: dict[str, deque] = defaultdict(deque)
_lock = threading.Lock()


def _ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "?"


def _bloqueado(tipo: str, *claves: str) -> int:
    """Segundos que faltan si alguna clave agotó su cupo de [tipo]; 0 si no."""
    tope, ventana = _LIM[tipo]
    ahora = time.monotonic()
    espera = 0
    with _lock:
        for c in claves:
            dq = _hits[f"{tipo}|{c}"]
            while dq and ahora - dq[0] > ventana:
                dq.popleft()
            if len(dq) >= tope:
                espera = max(espera, int(ventana - (ahora - dq[0])) + 1)
    return espera


def _contar(tipo: str, *claves: str) -> None:
    ahora = time.monotonic()
    with _lock:
        for c in claves:
            _hits[f"{tipo}|{c}"].append(ahora)


# Quién pidió el OTP vigente de cada cancha (como `stores.otps`, vive en
# memoria y no se persiste: un código solo lo canjea la cuenta que lo pidió).
_otp_de: dict[str, str] = {}


def _reset_limites() -> None:  # tests
    with _lock:
        _hits.clear()
    _otp_de.clear()


# ── Datos ────────────────────────────────────────────────────────────────────
def _num(v) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f and abs(f) < 1e6 else None


def _coords_ok(lat, lng) -> bool:
    return lat is not None and lng is not None and -90 <= lat <= 90 and -180 <= lng <= 180


def _mi_cancha(email: str, cancha_id: str) -> dict | None:
    return next((c for c in datos.canchas_de_dueno(email) if c.get("id") == cancha_id), None)


def _mi_reclamo(cancha_id: str, email: str):
    """El reclamo MÁS RECIENTE de esta cuenta sobre ese lugar (mismo id o
    mismo sitio físico, como `reclamos.estado`)."""
    em = (email or "").strip().lower()
    pool = [r for r in reclamos._reclamos_del_lugar(cancha_id) if (r.solicitante_id or "").strip().lower() == em]
    return max(pool, key=lambda r: r.id) if pool else None


def _otp_confirmado(cancha_id: str, email: str):
    em = (email or "").strip().lower()
    confs = [c for c in stores.confirmaciones_propiedad
             if c.cancha_id == cancha_id and (c.solicitante_id or "").lower() == em and c.metodo == "otp_whatsapp"]
    return confs[-1] if confs else None


def _pais(c: dict) -> str:
    return paises.pais_de_coordenadas(c.get("lat"), c.get("lng"))


def _tel_local(tel: str | None, iso: str) -> str:
    d = re.sub(r"\D", "", tel or "")
    pre = catalogos.TEL_PREFIJO.get(iso, "51")
    if d.startswith(pre) and len(d) > catalogos.TEL_LONGITUD.get(iso, 9):
        d = d[len(pre):]
    return d


def _fecha(d) -> str:
    try:
        from zoneinfo import ZoneInfo
        return d.astimezone(ZoneInfo("America/Lima")).strftime("%d/%m/%Y %H:%M")
    except Exception:  # noqa: BLE001
        return ""


def _visitas(lat, lng, radio_km) -> list[dict]:
    """Cola del verificador (misma función que el app) + nombre, dirección y
    zona reales del local desde la nube (el app solo mostraba el id)."""
    items = vf_svc.visitas(None, None, lat, lng, radio_km)[:60]
    cache: dict[str, dict | None] = {}
    out = []
    for v in items:
        cid = str(v.get("cancha_id") or "")
        if cid not in cache:
            cache[cid] = datos.cancha(cid)
        c = cache[cid] or {}
        la, ln = v.get("lat") if v.get("lat") is not None else c.get("lat"), v.get("lng") if v.get("lng") is not None else c.get("lng")
        out.append({
            "id": v.get("id"), "cancha_id": cid, "estado": v.get("estado"), "motivo": v.get("motivo") or "",
            "demanda": int(v.get("demanda") or 0), "distancia_m": v.get("distancia_m"),
            "zona": v.get("zona") or c.get("barrio") or "", "lat": la, "lng": ln,
            "nombre": str(c.get("club") or c.get("nombre") or f"Cancha {cid}"),
            "cancha": str(c.get("nombre") or "") if c.get("club") and c.get("nombre") != c.get("club") else "",
            "direccion": str(c.get("direccion") or ""),
        })
    return out


def _fotos_validas(urls, carpeta: str) -> list[str]:
    pre = almacen.prefijo_carpeta(carpeta)
    return [u for u in (urls or []) if isinstance(u, str) and u.startswith(pre)][:MAX_FOTOS]


# ── Estilos y JS ─────────────────────────────────────────────────────────────
_CSS = """
<style>
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
.vf-dem small{display:block;color:var(--teal);font-weight:600;font-size:10px;margin-top:3px}
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
</style>"""

# Utilidades compartidas: GPS del navegador y compresión/subida de fotos.
_JS_BASE = r"""
window.vfUbicar = function(){
  return new Promise(function(res){
    if(!navigator.geolocation){ res(null); return; }
    navigator.geolocation.getCurrentPosition(function(p){ res({lat: p.coords.latitude, lng: p.coords.longitude, acc: p.coords.accuracy}); },
      function(){ res(null); }, {enableHighAccuracy: true, timeout: 15000, maximumAge: 0});
  });
};
window.vfComprimir = function(file){
  return new Promise(function(res){
    var img = new Image(), url = URL.createObjectURL(file);
    img.onload = function(){
      var k = Math.min(1, 1280 / Math.max(img.width, img.height)), c = document.createElement('canvas');
      c.width = Math.round(img.width * k); c.height = Math.round(img.height * k);
      c.getContext('2d').drawImage(img, 0, 0, c.width, c.height); URL.revokeObjectURL(url);
      c.toBlob(function(b){ res(b); }, 'image/jpeg', 0.85);
    };
    img.onerror = function(){ URL.revokeObjectURL(url); res(null); };
    img.src = url;
  });
};
window.vfFotos = function(inputId, boxId, max){
  var lista = [], inp = document.getElementById(inputId), box = document.getElementById(boxId);
  function pintar(){
    box.innerHTML = lista.map(function(b, i){ return '<div class="f"><img alt="Foto ' + (i + 1) + '" src="' + URL.createObjectURL(b) + '"><button type="button" data-i="' + i + '" aria-label="Quitar">✕</button></div>'; }).join('');
    box.querySelectorAll('button').forEach(function(bt){ bt.addEventListener('click', function(){ lista.splice(+bt.dataset.i, 1); pintar(); }); });
  }
  inp.addEventListener('change', function(){
    var fs = Array.prototype.slice.call(inp.files || []); inp.value = '';
    Promise.all(fs.map(vfComprimir)).then(function(bs){
      bs.forEach(function(b){ if(b && lista.length < max) lista.push(b); });
      if(fs.length && lista.length >= max) pcgToast && pcgToast('Máximo ' + max + ' fotos');
      pintar();
    });
  });
  return {lista: lista, limpiar: function(){ lista.length = 0; pintar(); }};
};
window.vfSubir = function(blobs, carpeta, ref){
  var urls = [], ts = Date.now();
  return blobs.reduce(function(p, b, i){
    return p.then(function(){
      return fetch('/anfitrion/verificador/foto?carpeta=' + carpeta + '&ref=' + encodeURIComponent(ref) + '&i=' + i + '&ts=' + ts,
                   {method: 'POST', headers: {'Content-Type': 'image/jpeg'}, body: b})
        .then(function(r){ return r.json(); }).then(function(j){ if(j.ok && j.url) urls.push(j.url); });
    });
  }, Promise.resolve()).then(function(){ return urls; });
};
window.vfMsg = function(id, clase, txt){ var el = document.getElementById(id); el.className = 'vf-msg ' + clase; el.textContent = txt; };
window.vfEsc = function(s){ return String(s == null ? '' : s).replace(/[&<>"']/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]; }); };
"""

_JS_VERIFICADOR = r"""
(function(){
  var C = window.__vf, pos = null, radio = C.radio, visitas = [], actual = null;
  var $ = function(id){ return document.getElementById(id); };
  function tab(t){
    document.querySelectorAll('[data-vtab]').forEach(function(ch){ ch.classList.toggle('sel', ch.dataset.vtab === t); });
    $('secVisitas').style.display = t === 'visitas' ? '' : 'none';
    $('secCodigo').style.display = t === 'codigo' ? '' : 'none';
    $('secCaptura').style.display = 'none';
    try { history.replaceState(null, '', t === 'codigo' ? '#codigo' : location.pathname); } catch(_){}
  }
  document.querySelectorAll('[data-vtab]').forEach(function(ch){ ch.addEventListener('click', function(){ tab(ch.dataset.vtab); }); });
  function lblRadio(r){ return r == null ? 'Todas' : r + ' km'; }
  function pintarRadios(){
    $('radios').innerHTML = C.radios.map(function(r){ return '<span class="chip' + (String(r) === String(radio) ? ' sel' : '') + '" data-r="' + (r == null ? '' : r) + '">' + lblRadio(r) + '</span>'; }).join('');
    $('radios').querySelectorAll('.chip').forEach(function(ch){ ch.addEventListener('click', function(){ radio = ch.dataset.r === '' ? null : +ch.dataset.r; pintarRadios(); cargar(); }); });
  }
  function dist(m){ return m < 1000 ? 'a ' + Math.round(m) + ' m' : 'a ' + (m / 1000).toFixed(1) + ' km'; }
  var MOT = {sin_documentos: 'Sin documentos', ia_no_concluyente: 'La IA no pudo confirmarla', alto_valor: 'Local de alto valor'};
  var EST = {agendada: 'Agendada', en_sitio: 'En sitio'};
  function pintar(){
    var box = $('lista');
    if(!visitas.length){ box.innerHTML = '<div class="vf-vacio">No hay visitas pendientes cerca de ti.' + (radio != null && pos ? '<br><span class="sub">Prueba con un radio mayor o "Todas".</span>' : '') + '</div>'; return; }
    box.innerHTML = visitas.map(function(v, i){
      return '<button type="button" class="vf-card" data-i="' + i + '"><div class="txt"><b>' + vfEsc(v.nombre) + (v.cancha ? ' · ' + vfEsc(v.cancha) : '') + '</b>' +
        '<small>' + vfEsc(EST[v.estado] || v.estado) + ' · ' + vfEsc(MOT[v.motivo] || v.motivo) + (v.zona ? ' · ' + vfEsc(v.zona) : '') + '</small>' +
        (v.direccion ? '<small>📍 ' + vfEsc(v.direccion) + '</small>' : '') +
        (v.distancia_m != null ? '<span class="dist">🚶 ' + dist(v.distancia_m) + '</span>' : '') + '</div>' +
        '<div class="vf-dem">' + v.demanda + '<small>pedidos</small></div></button>';
    }).join('');
    box.querySelectorAll('.vf-card').forEach(function(b){ b.addEventListener('click', function(){ abrir(visitas[+b.dataset.i]); }); });
  }
  function cargar(){
    $('lista').innerHTML = '<div class="vf-vacio">Buscando visitas…</div>';
    var q = pos ? ('?lat=' + pos.lat + '&lng=' + pos.lng + (radio != null ? '&radio_km=' + radio : '')) : '';
    $('subVisitas').textContent = pos ? 'Cerca de ti (' + lblRadio(radio) + ') · la más pedida primero.' : 'Todas las visitas · la más pedida primero.';
    fetch('/anfitrion/verificador/visitas' + q).then(function(r){ return r.json(); }).then(function(j){ visitas = (j && j.visitas) || []; pintar(); })
      .catch(function(){ $('lista').innerHTML = '<div class="vf-vacio">No pudimos cargar las visitas. Revisa tu conexión.</div>'; });
  }
  var fotosCap = vfFotos('capFotoIn', 'capFotos', C.maxFotos), fotosVal = vfFotos('valFotoIn', 'valFotos', C.maxFotos);
  function abrir(v){
    actual = v; fotosCap.limpiar(); $('capMsg').className = 'vf-msg';
    $('capTitulo').textContent = 'Verificar ' + v.nombre;
    $('capSub').textContent = (v.zona ? 'Zona ' + v.zona + ' · ' : '') + 'demanda ' + v.demanda + (v.direccion ? ' · ' + v.direccion : '');
    $('capIr').href = (v.lat != null && v.lng != null) ? 'https://www.google.com/maps/dir/?api=1&destination=' + v.lat + ',' + v.lng : '#';
    $('capIr').style.display = (v.lat != null && v.lng != null) ? '' : 'none';
    $('secVisitas').style.display = 'none'; $('secCaptura').style.display = ''; window.scrollTo(0, 0);
  }
  $('capVolver').addEventListener('click', function(){ tab('visitas'); });
  $('capEnviar').addEventListener('click', function(){
    if(!actual) return;
    if(!fotosCap.lista.length){ vfMsg('capMsg', 'bad', 'Toma al menos una foto del sitio.'); return; }
    var firma = $('capFirma').value.trim();
    if(firma.length < 3){ vfMsg('capMsg', 'bad', 'Firma con tu nombre.'); return; }
    if(!C.storage){ vfMsg('capMsg', 'bad', 'La subida de fotos no está disponible en este ambiente. Hazlo desde la app.'); return; }
    pcgCargando('Obteniendo tu ubicación…');
    vfUbicar().then(function(p){
      if(!p){ pcgCargando(false); vfMsg('capMsg', 'bad', 'No pude obtener tu ubicación. Activa el GPS y permite la ubicación al navegador.'); return; }
      pcgCargando('Subiendo fotos…');
      return vfSubir(fotosCap.lista, 'verif', String(actual.id)).then(function(urls){
        if(!urls.length){ pcgCargando(false); vfMsg('capMsg', 'bad', 'No se pudieron subir las fotos. Revisa tu conexión.'); return; }
        pcgCargando('Enviando…');
        return fetch('/anfitrion/verificador/visita/' + actual.id + '/captura', {method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({fotos: urls, lat: p.lat, lng: p.lng, precision: p.acc, firma: firma, fotos_tomadas: fotosCap.lista.length})})
          .then(function(r){ return r.json(); }).then(function(j){
            pcgCargando(false);
            if(j.ok){ pcgAvisar({titulo: 'Cancha verificada ✅', mensaje: 'La ubicación coincide' + (j.distancia_m != null ? ' (' + j.distancia_m + ' m)' : '') + '. Gracias por tu visita.', icono: '✅'}).then(function(){ tab('visitas'); cargar(); }); return; }
            if(j.estado === 'rechazada'){ vfMsg('capMsg', 'bad', '❌ La ubicación no coincide (' + j.distancia_m + ' m). Acércate al sitio.'); return; }
            vfMsg('capMsg', 'bad', j.mensaje || 'No se pudo enviar.');
          });
      });
    }).catch(function(){ pcgCargando(false); vfMsg('capMsg', 'bad', 'No se pudo enviar. Revisa tu conexión.'); });
  });
  $('valEnviar').addEventListener('click', function(){
    var cod = $('valCodigo').value.replace(/\D/g, '');
    if(cod.length < 4){ vfMsg('valMsg', 'bad', 'Ingresa el código del reclamo.'); return; }
    pcgCargando('Obteniendo tu ubicación…');
    vfUbicar().then(function(p){
      if(!p){ pcgCargando(false); vfMsg('valMsg', 'bad', 'No pude obtener tu ubicación. Activa el GPS y permite la ubicación al navegador.'); return; }
      var subir = (fotosVal.lista.length && C.storage) ? (pcgCargando('Subiendo fotos…'), vfSubir(fotosVal.lista, 'validacion', cod)) : Promise.resolve([]);
      return subir.then(function(urls){
        pcgCargando('Validando…');
        return fetch('/anfitrion/verificador/validar', {method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({codigo: cod, lat: p.lat, lng: p.lng, precision: p.acc, fotos: urls})})
          .then(function(r){ return r.json(); }).then(function(j){
            pcgCargando(false);
            if(j.ok && j.estado === 'activada'){ vfMsg('valMsg', 'ok', '✅ Validada y activada. La cancha quedó verificada en persona.'); $('valCodigo').value = ''; fotosVal.limpiar(); return; }
            if(j.ok && j.estado === 'validada_pendiente_admin'){ vfMsg('valMsg', 'ok', '✅ Validada. Falta que el equipo la active.'); $('valCodigo').value = ''; fotosVal.limpiar(); return; }
            if(j.error === 'ubicacion_no_coincide'){ vfMsg('valMsg', 'bad', '❌ No estás en el sitio (' + j.distancia_m + ' m de la cancha). Acércate al local.' + (p.acc > 100 ? ' Tu ubicación es aproximada (±' + Math.round(p.acc) + ' m): activa el GPS del celular.' : '')); return; }
            if(j.error === 'codigo_invalido'){ vfMsg('valMsg', 'bad', '❌ Código inválido o el reclamo no está listo para validar.'); return; }
            vfMsg('valMsg', 'bad', j.mensaje || 'No se pudo validar.');
          });
      });
    }).catch(function(){ pcgCargando(false); vfMsg('valMsg', 'bad', 'No se pudo enviar. Revisa tu conexión.'); });
  });
  pintarRadios();
  tab(location.hash === '#codigo' ? 'codigo' : 'visitas');
  vfUbicar().then(function(p){ pos = p; if(!p){ $('sinGps').style.display = ''; } cargar(); });
})();
"""


# ── Páginas del verificador ──────────────────────────────────────────────────
def _cab(ses: dict | None, sel: str) -> str:
    tabs = (f"<a class='cat{' sel' if sel == 'verificador' else ''}' href='/anfitrion/verificador'><span class='ico'>🛡️</span>Verificador</a>"
            f"<a class='cat{' sel' if sel == 'canchas' else ''}' href='/anfitrion/canchas'><span class='ico'>🏟️</span>Mis canchas</a>")
    return ui.cabecera(tabs=tabs, ses=ses, volver="/anfitrion", modo="anfitrion")


@router.get("/anfitrion/verificador", response_class=HTMLResponse)
def pagina_verificador(request: Request) -> HTMLResponse:
    ses, resp = _sesion_o_entrar(request, "/anfitrion/verificador")
    if resp is not None:
        return resp
    cfg = json.dumps({"radios": list(RADIOS), "radio": 50, "maxFotos": MAX_FOTOS, "storage": almacen.disponible()})
    cuerpo = (
        _CSS + "<div class='vf-wrap'><a class='anf-back' href='/anfitrion'>‹ Modo anfitrión</a>"
        "<h1 class='anf-hola' style='margin-top:6px'>Verificador</h1>"
        "<p class='sub'>Rol de campo: visitas con foto, GPS y firma. Úsalo desde el celular, estando en la cancha.</p>"
        "<div class='vf-tabs'><span class='chip sel' data-vtab='visitas'>📋 Visitas pendientes</span>"
        "<span class='chip' data-vtab='codigo'>📍 Validar reclamo por código</span></div>"
        # Visitas
        "<section id='secVisitas'>"
        "<div class='vf-info'><span>🛡️</span><span>Vas a la cancha, tomas fotos del sitio y tu GPS, y confirmas que existe: "
        "así queda “Verificada” y se puede reservar.</span></div>"
        "<p class='sub' id='subVisitas' style='margin:4px 0'>Cerca de ti · la más pedida primero.</p>"
        "<p id='sinGps' style='display:none;color:var(--rojo);font-weight:700;font-size:14px;margin:6px 0'>Activa la ubicación para ver solo las canchas cercanas a ti.</p>"
        "<div class='vf-radios chips' id='radios'></div><div class='vf-lista' id='lista'></div></section>"
        # Captura de una visita
        "<section id='secCaptura' style='display:none'><div class='panel'>"
        "<button type='button' class='btn sec' id='capVolver' style='padding:8px 14px'>‹ Visitas</button>"
        "<h2 id='capTitulo' style='margin-top:14px;overflow-wrap:anywhere'>Verificar cancha</h2><p class='sub' id='capSub'></p>"
        "<a class='btn sec' id='capIr' target='_blank' rel='noopener' href='#'>🧭 Cómo llegar</a>"
        "<div style='margin-top:18px'><label>Fotos del sitio</label>"
        f"<label class='btn' style='display:inline-flex;cursor:pointer;margin-top:6px'>📷 Tomar foto del sitio<input id='capFotoIn' type='file' accept='image/*' capture='environment' multiple style='display:none'></label>"
        "<div class='vf-fotos' id='capFotos'></div></div>"
        f"<div style='margin-top:16px'><label for='capFirma'>Firma (tu nombre)</label><input id='capFirma' maxlength='80' autocomplete='name' value='{e(ses.get('nombre') or '')}'></div>"
        "<div class='vf-msg' id='capMsg'></div>"
        "<div class='acciones' style='margin-top:18px'><button type='button' class='btn' id='capEnviar' style='width:100%'>✔️ Confirmar y firmar</button></div>"
        "<p class='vf-nota'>Las fotos son del establecimiento, no documentos personales. No se piden documentos de identidad ni recibos.</p>"
        "</div></section>"
        # Validar por código
        "<section id='secCodigo' style='display:none'><div class='panel'>"
        "<h2>Validación en sitio</h2>"
        "<p class='sub'>Ingresa el código del reclamo estando EN el local. Tu GPS debe coincidir con la ubicación de la cancha "
        f"(máximo {int(config.RECLAMO_VALIDACION_GPS_MAX_M)} m).</p>"
        "<label for='valCodigo'>Código del reclamo</label>"
        "<input id='valCodigo' class='vf-cod' inputmode='numeric' maxlength='6' autocomplete='one-time-code' placeholder='••••••'>"
        "<div style='margin-top:14px'><label class='btn sec' style='display:inline-flex;cursor:pointer'>📷 Tomar foto del sitio (opcional)"
        "<input id='valFotoIn' type='file' accept='image/*' capture='environment' multiple style='display:none'></label>"
        "<div class='vf-fotos' id='valFotos'></div></div>"
        "<div class='vf-msg' id='valMsg'></div>"
        "<div class='acciones' style='margin-top:18px'><button type='button' class='btn' id='valEnviar' style='width:100%'>📍 Validar en sitio</button></div>"
        "</div></section></div>"
        f"<script>window.__vf={cfg};</script><script>{_JS_BASE}{_JS_VERIFICADOR}</script>")
    return ui.shell("Verificador", cuerpo, nav=_cab(ses, "verificador"), sesion=ses, ancho=True,
                    titulo_tab="Verificador · Modo anfitrión")


def _ses_json(request: Request):
    ses = _sesion_o_entrar(request, "/anfitrion/verificador")[0]
    if not ses:
        return None, JSONResponse({"ok": False, "error": "sesion_requerida"}, status_code=401)
    return ses, None


@router.get("/anfitrion/verificador/visitas")
def api_visitas(request: Request, lat: float | None = None, lng: float | None = None,
                radio_km: float | None = None) -> JSONResponse:
    ses, err = _ses_json(request)
    if err:
        return err
    if not _coords_ok(lat, lng):
        lat = lng = radio_km = None
    if radio_km is not None and not (0 < radio_km <= 20000):
        radio_km = None
    return JSONResponse({"ok": True, "visitas": _visitas(lat, lng, radio_km)})


@router.post("/anfitrion/verificador/foto")
async def subir_foto(request: Request, carpeta: str = "", ref: str = "", i: int = 0, ts: int = 0) -> JSONResponse:
    cuerpo = await request.body()
    return await run_in_threadpool(_subir_foto, request, carpeta, ref, i, ts, cuerpo)


def _subir_foto(request: Request, carpeta: str, ref: str, i: int, ts: int, cuerpo: bytes) -> JSONResponse:
    """Foto del SITIO (no documentos): misma ruta que el app
    (`CanchasRepo.subirFoto('verif'|'validacion', …, sufijo: '<ref>_<i>_<ms>')`)."""
    ses, err = _ses_json(request)
    if err:
        return err
    if carpeta not in ("verif", "validacion") or not _REF_RE.match(ref or "") or not (0 <= i < MAX_FOTOS):
        return JSONResponse({"ok": False, "error": "datos_invalidos"}, status_code=400)
    if not almacen.disponible():
        return JSONResponse({"ok": False, "error": "storage_no_disponible"}, status_code=503)
    ctype = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    if ctype not in ("image/jpeg", "image/png", "image/webp") or not cuerpo:
        return JSONResponse({"ok": False, "error": "formato"}, status_code=400)
    ts = ts if 0 < ts < 10 ** 14 else int(time.time() * 1000)
    url = almacen.subir(almacen.BUCKET, f"{carpeta}/{ref}_{i}_{ts}.jpg", cuerpo, ctype)
    if not url:
        return JSONResponse({"ok": False, "error": "subida_fallo"}, status_code=502)
    return JSONResponse({"ok": True, "url": url})


def _captura(ses: dict, ip: str, vf_id: int, body) -> dict:
    if not isinstance(body, dict):
        return {"ok": False, "mensaje": "Datos inválidos."}
    email = ses["email"]
    espera = _bloqueado("captura", email, ip)
    if espera:
        return {"ok": False, "error": "demasiados_intentos", "mensaje": f"Demasiados intentos. Vuelve a intentarlo en {max(1, espera // 60)} min."}
    lat, lng = _num(body.get("lat")), _num(body.get("lng"))
    if not _coords_ok(lat, lng):
        return {"ok": False, "mensaje": "No pude obtener tu ubicación. Activa el GPS y reintenta."}
    firma = re.sub(r"\s+", " ", str(body.get("firma") or "")).strip()[:80]
    if len(firma) < 3:
        return {"ok": False, "mensaje": "Firma con tu nombre."}
    fotos = _fotos_validas(body.get("fotos"), "verif")
    if not fotos:
        return {"ok": False, "mensaje": "Toma al menos una foto del sitio."}
    vf = next((v for v in stores.verificaciones_fisicas if v.id == vf_id), None)
    if vf is None or vf.estado not in ("agendada", "en_sitio"):
        return {"ok": False, "error": "no_disponible", "mensaje": "Esta visita ya no está pendiente. Actualiza la lista."}
    res = vf_svc.captura(vf_id, fotos, lat, lng, f"{firma} <{email}>",
                         f"Verificado en sitio desde la web ({len(fotos)} fotos).")
    if not res.get("ok"):
        _contar("captura", email, ip)
    print(f"[verificador-web] {email} visita #{vf_id} ({vf.cancha_id}) → {res.get('estado') or res.get('error')} "
          f"dist={res.get('distancia_m')}", flush=True)
    return {k: v for k, v in res.items() if k in ("ok", "estado", "coincide", "distancia_m", "insignia", "error")}


@router.post("/anfitrion/verificador/visita/{vf_id}/captura")
def api_captura(vf_id: int, request: Request, body: dict | None = Body(None)) -> JSONResponse:
    ses, err = _ses_json(request)
    if err:
        return err
    return JSONResponse(_captura(ses, _ip(request), vf_id, body))


def _validar(ses: dict, ip: str, body) -> dict:
    if not isinstance(body, dict):
        return {"ok": False, "mensaje": "Datos inválidos."}
    email = ses["email"]
    espera = _bloqueado("codigo", email, ip)
    if espera:
        return {"ok": False, "error": "demasiados_intentos",
                "mensaje": f"Demasiados códigos equivocados. Vuelve a intentarlo en {max(1, espera // 60)} min."}
    codigo = re.sub(r"\D", "", str(body.get("codigo") or ""))
    if len(codigo) < 4:
        return {"ok": False, "mensaje": "Ingresa el código del reclamo."}
    lat, lng = _num(body.get("lat")), _num(body.get("lng"))
    if not _coords_ok(lat, lng):
        return {"ok": False, "mensaje": "No pude obtener tu ubicación. Activa el GPS y reintenta."}
    # Mismo criterio de búsqueda que `validar_en_sitio`: nadie valida su propio reclamo.
    r = next((x for x in stores.reclamos if x.codigo == codigo and x.estado in ("aprobado_triage", "pendiente_validacion")), None)
    if r is not None and (r.solicitante_id or "").strip().lower() == email.lower():
        return {"ok": False, "error": "propio", "mensaje": "No puedes validar tu propio reclamo: lo valida un verificador de Pichangol en el local."}
    res = reclamos.validar_en_sitio(codigo, lat, lng, email, _fotos_validas(body.get("fotos"), "validacion"))
    if res.get("error") == "codigo_invalido":
        _contar("codigo", email, ip)
    print(f"[verificador-web] {email} valida código ••{codigo[-2:]} → {res.get('estado') or res.get('error')} dist={res.get('distancia_m')}", flush=True)
    return res


@router.post("/anfitrion/verificador/validar")
def api_validar(request: Request, body: dict | None = Body(None)) -> JSONResponse:
    ses, err = _ses_json(request)
    if err:
        return err
    return JSONResponse(_validar(ses, _ip(request), body))


# ── Estado de MI verificación (ficha pendiente del app) ──────────────────────
_ICONO = {"ok": "✅", "warn": "⏳", "err": "⚠️"}


def _pasos(r, modo: str, verificada: bool, otp) -> str:
    est = r.estado if r else ""
    rech = est == "rechazada"

    def li(clase: str, n: str, tit: str, txt: str) -> str:
        return f"<li class='{clase}'><span class='n'>{n}</span><div><b>{tit}</b><small>{txt}</small></div></li>"

    pasos = [li("hecho" if r else "actual", "✓" if r else "1", "Solicitud enviada",
                f"El {e(_fecha(r.creado_en))}" if r else "Aún no hay una solicitud a tu nombre en el servidor.")]
    if otp is not None:
        pasos.append(li("hecho", "✓", "WhatsApp del local confirmado", f"Por código a {e(otp.telefono_enmascarado or '')}."))
    revisado = est in ("aprobado_triage", "pendiente_validacion", "validada_pendiente_admin", "activada")
    pasos.append(li("mal" if rech else ("hecho" if revisado or verificada else ("actual" if r else "")),
                    "✕" if rech else ("✓" if revisado or verificada else "2"), "Revisión del equipo",
                    "No pudimos confirmar que eres el dueño." if rech else
                    ("Confirmamos tus datos." if revisado or verificada else "Revisamos que eres el dueño; te avisamos por WhatsApp y en la app.")))
    if modo == "nuevo_flujo" or est in ("aprobado_triage", "pendiente_validacion", "validada_pendiente_admin") or (r and r.validado_en and r.validador and "@" in (r.validador or "")):
        hecho = est in ("validada_pendiente_admin", "activada")
        pasos.append(li("hecho" if hecho else ("actual" if est in ("aprobado_triage", "pendiente_validacion") else ""),
                        "✓" if hecho else "3", "Validación en sitio",
                        "Un verificador fue al local con el código y su GPS." if hecho else
                        "Un verificador de Pichangol irá al local con el código del reclamo."))
    pasos.append(li("hecho" if verificada else "", "✓" if verificada else "★", "Activa: recibe reservas",
                    "Tu cancha ya acepta reservas en línea." if verificada else "Se habilita al aprobar la propiedad."))
    return "<ol class='vf-pasos'>" + "".join(pasos) + "</ol>"


_JS_ESTADO = r"""
(function(){
  var C = window.__ve, $ = function(id){ return document.getElementById(id); };
  function post(url, body, msg){
    pcgCargando(msg || 'Consultando…');
    return fetch(url, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body || {})})
      .then(function(r){ return r.json(); }).then(function(j){ pcgCargando(false); return j; })
      .catch(function(){ pcgCargando(false); return {ok: false, mensaje: 'Sin conexión. Inténtalo de nuevo.'}; });
  }
  var bE = $('btnEstado');
  if(bE) bE.addEventListener('click', function(){
    post(C.base + '/estado', {}, 'Consultando al servidor…').then(function(j){
      if(j.recargar){ pcgAvisar({titulo: j.titulo || 'Estado actualizado', mensaje: j.mensaje, icono: j.icono || '✅'}).then(function(){ pcgRecargar(); }); return; }
      vfMsg('diag', j.clase || 'warn', j.mensaje || 'No se pudo consultar al servidor. Reintenta en un momento.');
    });
  });
  var bR = $('btnReenviar');
  if(bR) bR.addEventListener('click', function(){
    vfUbicar().then(function(p){
      post(C.base + '/reenviar', p ? {lat: p.lat, lng: p.lng} : {}, 'Enviando solicitud…').then(function(j){
        if(j.ok){ pcgAvisar({titulo: 'Solicitud enviada', mensaje: 'Está en revisión; te avisamos cuando se apruebe.', icono: '📨'}).then(function(){ pcgRecargar(); }); return; }
        vfMsg('diag', 'bad', j.mensaje || 'No se pudo enviar la solicitud. Reintenta en un momento.');
      });
    });
  });
  var bO = $('btnOtp');
  if(bO) bO.addEventListener('click', function(){
    var tel = ($('otpTel').value || '').replace(/\D/g, '');
    if(tel.length !== C.telLen){ vfMsg('otpMsg', 'bad', 'Ingresa el teléfono del local (' + C.telLen + ' dígitos).'); return; }
    post(C.base + '/otp/enviar', {telefono: tel}, 'Enviando código…').then(function(j){
      if(!j.ok){ vfMsg('otpMsg', 'bad', j.mensaje || 'No se pudo enviar el código.'); return; }
      $('otpPaso1').style.display = 'none'; $('otpPaso2').style.display = '';
      $('otpA').textContent = j.telefono_enmascarado || '';
      vfMsg('otpMsg', j.codigo_debug ? 'warn' : 'ok', j.codigo_debug ? ('Código de prueba: ' + j.codigo_debug) :
        (j.via === 'stub' ? 'Modo de prueba: no se envió un mensaje real.' : 'Te enviamos el código. Vence en ' + Math.round((j.expira_seg || 300) / 60) + ' min.'));
      $('otpCodigo').focus();
    });
  });
  var bC = $('btnOtpOk');
  if(bC) bC.addEventListener('click', function(){
    var cod = ($('otpCodigo').value || '').replace(/\D/g, '');
    if(cod.length < 4){ vfMsg('otpMsg', 'bad', 'Ingresa el código que te llegó.'); return; }
    post(C.base + '/otp/confirmar', {codigo: cod}, 'Verificando…').then(function(j){
      if(j.ok){ pcgAvisar({titulo: 'WhatsApp confirmado ✅', mensaje: 'Lo sumamos a tu solicitud para que el equipo la apruebe más rápido.', icono: '✅'}).then(function(){ pcgRecargar(); }); return; }
      vfMsg('otpMsg', 'bad', j.mensaje || 'No se pudo confirmar.');
    });
  });
  var bX = $('btnOtpOtro');
  if(bX) bX.addEventListener('click', function(){ $('otpPaso2').style.display = 'none'; $('otpPaso1').style.display = ''; $('otpMsg').className = 'vf-msg'; });
})();
"""


@router.get("/anfitrion/verificacion/{cancha_id}", response_class=HTMLResponse)
def pagina_verificacion(cancha_id: str, request: Request) -> HTMLResponse:
    ses, resp = _sesion_o_entrar(request, f"/anfitrion/verificacion/{cancha_id}")
    if resp is not None:
        return resp
    email = ses["email"]
    c = _mi_cancha(email, cancha_id)
    if c is None:
        from web.router import _no_encontrada
        r404 = _no_encontrada("Esta cancha no está a tu nombre")
        r404.status_code = 404
        return r404
    r = _mi_reclamo(cancha_id, email)
    try:
        est = reclamos.estado(cancha_id, email)
    except Exception:  # noqa: BLE001
        est = {}
    verificada = datos.reservable(c) or (est.get("verificada") and est.get("es_mio"))
    estado = "activada" if verificada else (str(est.get("estado") or "") if est.get("existe") else "")
    iso = _pais(c)
    otp = _otp_confirmado(cancha_id, email)
    nombre = str(c.get("club") or c.get("nombre") or "Tu cancha")
    if verificada:
        clase, tit, txt = "ok", "Verificada", "Tu cancha está activa y recibe reservas en línea."
    elif estado:
        clase, tit, txt = _ESTADO_RECLAMO.get(estado, ("warn", "En verificación", "Estamos confirmando que eres el dueño."))
    else:
        clase, tit, txt = ("warn", "Sin solicitud de verificación",
                           "No encontramos tu solicitud en el servidor (pudo perderse). Vuelve a enviarla aquí abajo.")
    clase_box = {"ok": "ok", "err": "bad"}.get(clase, "")
    rech = estado == "rechazada"
    acciones = ""
    if not verificada and estado != "reclamada_por_otro":
        acciones = ("<div class='vf-acc'>"
                    "<button type='button' class='btn sec' id='btnEstado'>🔄 Verificar estado ahora</button>"
                    f"<button type='button' class='btn' id='btnReenviar'>{'↩ Volver a solicitar' if rech or not r else '📨 Reenviar solicitud de verificación'}</button></div>")
    elif verificada and not datos.reservable(c):
        acciones = "<div class='vf-acc'><button type='button' class='btn' id='btnEstado'>🔄 Habilitar mis reservas</button></div>"
    # Código por WhatsApp: solo con un reclamo propio en curso.
    otp_html = ""
    if not verificada and r is not None and r.estado in _NO_TERMINALES:
        pre = catalogos.TEL_PREFIJO.get(iso, "51")
        n = catalogos.TEL_LONGITUD.get(iso, 9)
        if otp is not None:
            otp_html = (f"<div class='panel' style='margin-top:16px'><h2>📲 WhatsApp del local</h2>"
                        f"<p class='sub'>✅ Confirmado por código a {e(otp.telefono_enmascarado or '')} el {e(_fecha(otp.creado_en))}. "
                        "Ya está en tu solicitud para que el equipo la apruebe.</p></div>")
        else:
            otp_html = (
                "<div class='panel' style='margin-top:16px'><h2>📲 Confirma el WhatsApp del local</h2>"
                "<p class='sub'>Te enviamos un código por WhatsApp o SMS al teléfono del local. Confirmarlo acelera la "
                "revisión: prueba que controlas ese número.</p>"
                f"<div id='otpPaso1'><label for='otpTel'>Teléfono del local (WhatsApp)</label>"
                f"<div class='vf-tel'><span>+{pre}</span><input id='otpTel' inputmode='tel' maxlength='{n + 4}' placeholder='{'9' * n}' value='{e(_tel_local(r.telefono_contacto, iso))}'></div>"
                "<div class='acciones' style='margin-top:12px'><button type='button' class='btn' id='btnOtp'>Enviar código</button></div></div>"
                "<div id='otpPaso2' style='display:none'><p class='sub'>Código enviado a <b id='otpA'></b>.</p>"
                "<label for='otpCodigo'>Código de 6 dígitos</label><input id='otpCodigo' class='vf-cod' inputmode='numeric' maxlength='6' autocomplete='one-time-code' placeholder='••••••'>"
                "<div class='vf-acc'><button type='button' class='btn' id='btnOtpOk'>Confirmar código</button>"
                "<button type='button' class='btn sec' id='btnOtpOtro'>Cambiar número</button></div></div>"
                "<div class='vf-msg' id='otpMsg'></div></div>")
    cfg = json.dumps({"base": f"/anfitrion/verificacion/{cancha_id}", "telLen": catalogos.TEL_LONGITUD.get(iso, 9)})
    cuerpo = (
        _CSS + "<div class='vf-wrap'><a class='anf-back' href='/anfitrion/canchas'>‹ Mis canchas</a>"
        f"<h1 class='anf-hola' style='margin-top:6px;overflow-wrap:anywhere'>{e(nombre)}</h1>"
        "<p class='sub'>Existir no es lo mismo que ser el dueño: las reservas en línea se habilitan cuando confirmamos que el local es tuyo.</p>"
        f"<div class='panel'><div class='vf-estado {clase_box}'><span class='ico'>{_ICONO.get(clase, '⏳')}</span>"
        f"<div><h2 style='margin:0'>{e(tit)}</h2><p class='sub' style='margin:4px 0 0'>{e(txt)}</p>"
        + (f"<p class='sub' style='margin:4px 0 0;font-size:13px'>Solicitud #{r.id} · enviada el {e(_fecha(r.creado_en))}</p>" if r else "")
        + "</div></div>"
        f"{_pasos(r, stores.modo_aprobacion(cancha_id), bool(verificada), otp)}"
        f"{acciones}<div class='vf-msg' id='diag'></div></div>"
        f"{'' if verificada or estado == 'reclamada_por_otro' else aviso_fotos_reclamo(email, c)}"
        f"{otp_html}"
        + ("" if verificada else
           f"<p class='vf-nota' style='text-align:center'>¿Dudas? Escríbenos por WhatsApp desde el pie de página o sigue tu solicitud en la "
           f"<a href='{PLAY_URL}' rel='noopener'>app de Pichangol</a>.</p>")
        + "</div>"
        f"<script>window.__ve={cfg};</script><script>{_JS_BASE}{_JS_ESTADO}</script>")
    return ui.shell("Verificación de mi cancha", cuerpo, nav=_cab(ses, "canchas"), sesion=ses, ancho=True,
                    titulo_tab="Verificación · Modo anfitrión")


def _estado_ahora(email: str, cancha_id: str) -> dict:
    """"Verificar estado ahora" del app (`_verificarAhora` de la ficha)."""
    c = _mi_cancha(email, cancha_id)
    if c is None:
        return {"ok": False, "clase": "bad", "mensaje": "Esta cancha no está a tu nombre."}
    try:
        est = reclamos.estado(cancha_id, email)
    except Exception:  # noqa: BLE001
        return {"ok": False, "clase": "bad", "mensaje": "⚠️ No se pudo consultar al servidor. Reintenta en un momento."}
    if not est.get("existe"):
        return {"ok": True, "clase": "warn", "mensaje": "⚠️ No encontramos tu solicitud en el servidor. Toca “Reenviar solicitud de verificación”."}
    estado, mio = est.get("estado"), bool(est.get("es_mio"))
    if estado == "rechazada" and mio:
        return {"ok": True, "recargar": True, "titulo": "Solicitud no aprobada", "icono": "⚠️",
                "mensaje": "No pudimos confirmar que seas el dueño. Si crees que es un error, vuelve a enviarla con tus datos correctos o escríbenos."}
    if est.get("verificada") and mio:
        # Repara el espejo en la nube si la torre no alcanzó a escribirlo (el
        # APK lo hacía al sincronizar; un dueño solo-web dependía de esto).
        if not datos.reservable(c):
            r = _mi_reclamo(cancha_id, email)
            n = datos.marcar_verificada(cancha_id, email, True, r.lat if r else c.get("lat"), r.lng if r else c.get("lng"))
            print(f"[verificacion-web] {email} {cancha_id}: aprobada, nube reparada ({n} fila(s))", flush=True)
            if not n:
                return {"ok": False, "clase": "warn", "mensaje": "✅ Tu solicitud está aprobada, pero no pudimos habilitar las reservas ahora. Reintenta en un momento."}
        return {"ok": True, "recargar": True, "titulo": "¡Aprobada! ✅", "icono": "✅", "mensaje": "Tus reservas en línea quedaron habilitadas."}
    if est.get("verificada") or estado == "reclamada_por_otro":
        return {"ok": True, "clase": "bad", "mensaje": "⚠️ Este local ya tiene un dueño aprobado con otra cuenta. Si el local es tuyo, escríbenos para revisarlo."}
    txt = _ESTADO_RECLAMO.get(str(estado), ("warn", "", "Tu solicitud sigue en revisión. Te avisamos cuando se apruebe."))[2]
    return {"ok": True, "clase": "warn", "mensaje": f"⏳ {txt}"}


@router.post("/anfitrion/verificacion/{cancha_id}/estado")
def api_estado(cancha_id: str, request: Request) -> JSONResponse:
    ses, err = _ses_json(request)
    if err:
        return err
    return JSONResponse(_estado_ahora(ses["email"], cancha_id))


def _reenviar(ses: dict, cancha_id: str, body) -> dict:
    """"Reenviar solicitud de verificación" / "Volver a solicitar" del app:
    `crear_reclamo` con la cuenta de la sesión, el punto de la cancha y el GPS
    del navegador (desde dónde se reenvía). Idempotente si ya hay uno vivo."""
    email = ses["email"]
    c = _mi_cancha(email, cancha_id)
    if c is None:
        return {"ok": False, "mensaje": "Esta cancha no está a tu nombre."}
    if datos.reservable(c):
        return {"ok": False, "mensaje": "Tu cancha ya está verificada."}
    body = body if isinstance(body, dict) else {}
    slat, slng = _num(body.get("lat")), _num(body.get("lng"))
    if not _coords_ok(slat, slng):
        slat = slng = None
    prev = _mi_reclamo(cancha_id, email)
    lat, lng = _num(c.get("lat")), _num(c.get("lng"))
    try:
        res = reclamos.crear_reclamo(
            cancha_id, email, str(c.get("club") or c.get("nombre") or ""),
            prev.telefono_contacto if prev else None, None, None, prev.relacion if prev else None,
            lat if _coords_ok(lat, lng) else None, lng if _coords_ok(lat, lng) else None, slat, slng,
            solicitante_nombre=ses.get("nombre") or "",
            foto_evidencia_url=prev.foto_evidencia_url if prev else "",
            nota_reclamante=("Reenviada desde la web" + (f" · antes: {prev.nota_reclamante}" if prev and prev.nota_reclamante else ""))[:500])
    except Exception as ex:  # noqa: BLE001
        print(f"[verificacion-web] reenviar {cancha_id} falló: {ex}", flush=True)
        return {"ok": False, "mensaje": "No se pudo enviar la solicitud. Reintenta en un momento."}
    if not res.get("ok"):
        if res.get("error") == "ya_reclamada":
            return {"ok": False, "mensaje": "Este lugar ya tiene un reclamo en curso de otra persona. Si es tu cancha, escríbenos por WhatsApp."}
        return {"ok": False, "mensaje": "No se pudo enviar la solicitud. Reintenta en un momento."}
    print(f"[verificacion-web] {email} reenvió {cancha_id} → reclamo #{res.get('reclamo_id')} ({res.get('estado')})", flush=True)
    return {"ok": True, "estado": res.get("estado"), "reclamo_id": res.get("reclamo_id"), "reenviado": bool(res.get("reenviado"))}


@router.post("/anfitrion/verificacion/{cancha_id}/reenviar")
def api_reenviar(cancha_id: str, request: Request, body: dict | None = Body(None)) -> JSONResponse:
    ses, err = _ses_json(request)
    if err:
        return err
    return JSONResponse(_reenviar(ses, cancha_id, body))


def _reclamo_para_otp(email: str, cancha_id: str):
    c = _mi_cancha(email, cancha_id)
    if c is None:
        return None, None, {"ok": False, "mensaje": "Esta cancha no está a tu nombre."}
    if datos.reservable(c):
        return None, None, {"ok": False, "mensaje": "Tu cancha ya está verificada."}
    r = _mi_reclamo(cancha_id, email)
    if r is None or r.estado not in _NO_TERMINALES:
        return None, None, {"ok": False, "mensaje": "Primero envía tu solicitud de verificación."}
    return c, r, None


def _otp_enviar(ses: dict, ip: str, cancha_id: str, body) -> dict:
    email = ses["email"]
    c, r, err = _reclamo_para_otp(email, cancha_id)
    if err:
        return err
    espera = _bloqueado("otp_envio", email, ip)
    if espera:
        return {"ok": False, "mensaje": f"Pediste varios códigos seguidos. Vuelve a intentarlo en {max(1, espera // 60)} min."}
    iso = _pais(c)
    local = _tel_local(str((body or {}).get("telefono") or "") if isinstance(body, dict) else "", iso)
    if len(local) != catalogos.TEL_LONGITUD.get(iso, 9):
        return {"ok": False, "mensaje": f"Ingresa el teléfono del local ({catalogos.TEL_LONGITUD.get(iso, 9)} dígitos)."}
    tel = catalogos.TEL_PREFIJO.get(iso, "51") + local
    res = otp_svc.solicitar(cancha_id, tel)
    _contar("otp_envio", email, ip)
    if not res.get("ok"):
        if res.get("error") == "reenvio_muy_pronto":
            return {"ok": False, "mensaje": f"Espera {res.get('espera_seg')} s antes de reenviar."}
        return {"ok": False, "mensaje": "No se pudo enviar el código. Revisa el número e inténtalo otra vez."}
    _otp_de[cancha_id] = email.lower()  # el código solo lo canjea quien lo pidió
    return {k: v for k, v in res.items() if k in ("ok", "via", "telefono_enmascarado", "expira_seg", "codigo_debug")}


@router.post("/anfitrion/verificacion/{cancha_id}/otp/enviar")
def api_otp_enviar(cancha_id: str, request: Request, body: dict | None = Body(None)) -> JSONResponse:
    ses, err = _ses_json(request)
    if err:
        return err
    return JSONResponse(_otp_enviar(ses, _ip(request), cancha_id, body))


def _otp_confirmar(ses: dict, cancha_id: str, body) -> dict:
    email = ses["email"]
    c, r, err = _reclamo_para_otp(email, cancha_id)
    if err:
        return err
    if _otp_de.get(cancha_id) != email.lower():
        return {"ok": False, "mensaje": "Pide un código nuevo."}
    codigo = re.sub(r"\D", "", str((body or {}).get("codigo") or "") if isinstance(body, dict) else "")
    if len(codigo) < 4:
        return {"ok": False, "mensaje": "Ingresa el código que te llegó."}
    otp = stores.otps.get(cancha_id)
    tel = otp.telefono if otp else ""
    res = otp_svc.confirmar(cancha_id, codigo, email, None, activar=False)
    if not res.get("ok"):
        e_ = res.get("error")
        msg = {"codigo_incorrecto": f"Código incorrecto. Te quedan {res.get('intentos_restantes', 0)} intentos.",
               "otp_vencido": "El código venció. Pide uno nuevo.", "max_intentos": "Agotaste los intentos. Pide un código nuevo.",
               "sin_otp": "Pide un código nuevo."}.get(e_, "No se pudo confirmar.")
        return {"ok": False, "error": e_, "mensaje": msg}
    _otp_de.pop(cancha_id, None)
    mask = otp_svc._mask(tel)
    # Evidencia para la torre (el reclamo es lo que decide la propiedad).
    reclamos.registrar_evidencia_otp(cancha_id, email, mask, tel, origen="web")
    print(f"[verificacion-web] {email} confirmó OTP {mask} para {cancha_id} (reclamo #{r.id})", flush=True)
    return {"ok": True, "estado": res.get("estado")}


@router.post("/anfitrion/verificacion/{cancha_id}/otp/confirmar")
def api_otp_confirmar(cancha_id: str, request: Request, body: dict | None = Body(None)) -> JSONResponse:
    ses, err = _ses_json(request)
    if err:
        return err
    return JSONResponse(_otp_confirmar(ses, cancha_id, body))


# Enlace para "Mis canchas" (lo usa el coordinador en `_aviso_verificacion`).
def enlace_verificacion(cancha_id: str) -> str:
    return f"/anfitrion/verificacion/{cancha_id}"


__all__ = ["router", "enlace_verificacion"]
