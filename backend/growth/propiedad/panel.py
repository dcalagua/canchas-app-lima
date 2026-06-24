"""PANEL WEB de administración (piloto).

El admin de Pichangol entra desde el navegador, ve los reclamos de canchas y los
aprueba/rechaza. La aprobación es DIRECTA: al aprobar, la cancha queda activa
(sin validación en sitio todavía).

Seguridad: protegido por ADMIN_PANEL_TOKEN. El token NO viaja en la URL; la
página lo guarda en el navegador (localStorage) y lo manda en la cabecera
X-Admin-Token. Si el token no está configurado, el panel responde 503.
"""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

import config
from propiedad import reclamos

router = APIRouter(tags=["panel"])


def _check(token: str | None) -> None:
    if not config.ADMIN_PANEL_TOKEN:
        raise HTTPException(status_code=503, detail="panel_no_configurado")
    if token != config.ADMIN_PANEL_TOKEN:
        raise HTTPException(status_code=401, detail="token_invalido")


class DecidirRequest(BaseModel):
    aprobado: bool
    revisor: str | None = None


@router.get("/admin/api/sesion")
def sesion(x_admin_token: str | None = Header(default=None)) -> dict:
    """Valida el token (lo usa la pantalla de login del panel)."""
    _check(x_admin_token)
    return {"ok": True}


@router.get("/admin/api/reclamos")
def listar(estado: str | None = None,
           x_admin_token: str | None = Header(default=None)) -> list[dict]:
    _check(x_admin_token)
    return reclamos.listar(estado)


@router.post("/admin/api/reclamo/{reclamo_id}/decidir")
def decidir(reclamo_id: int, req: DecidirRequest,
            x_admin_token: str | None = Header(default=None)) -> dict:
    """Aprobar = aprobación directa (cancha activa). Rechazar = triage rechazado."""
    _check(x_admin_token)
    if req.aprobado:
        return reclamos.aprobar_directo(reclamo_id, req.revisor)
    return reclamos.triage(reclamo_id, False, req.revisor)


@router.get("/admin", response_class=HTMLResponse)
def panel() -> str:
    return _HTML


_HTML = r"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Pichangol · Panel de canchas</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;700;800;900&display=swap" rel="stylesheet">
<style>
  :root{
    --bg:#F3F5F5; --card:#fff; --border:#E2E8E7; --text:#0F1B1C; --muted:#5C6B6C;
    --verde:#AEEA94; --bosque:#14463A; --accent:#5AA97F; --teal:#056769;
    --amarillo:#F2C94C; --limaSuave:#E9F4EE; --rojo:#D11F2E;
  }
  *{box-sizing:border-box}
  body{margin:0;font-family:'DM Sans',system-ui,sans-serif;background:var(--bg);color:var(--text)}
  header{position:sticky;top:0;z-index:5;background:var(--bosque);color:#fff;
    padding:14px 20px;display:flex;align-items:center;gap:12px;
    box-shadow:0 2px 8px rgba(0,0,0,.08)}
  header .pin{width:30px;height:30px;border-radius:50%;background:var(--verde);
    display:flex;align-items:center;justify-content:center;font-size:16px}
  header h1{font-size:17px;font-weight:900;margin:0;letter-spacing:-.3px}
  header .sp{flex:1}
  header button{background:rgba(255,255,255,.14);color:#fff;border:0;border-radius:10px;
    padding:8px 12px;font-family:inherit;font-weight:700;cursor:pointer;font-size:13px}
  header button:hover{background:rgba(255,255,255,.24)}
  .wrap{max-width:760px;margin:0 auto;padding:18px 16px 60px}
  .tabs{display:flex;gap:8px;overflow:auto;padding:4px 0 14px}
  .tab{white-space:nowrap;border:1px solid var(--border);background:#fff;color:var(--text);
    border-radius:999px;padding:8px 14px;font-weight:700;font-size:13px;cursor:pointer}
  .tab.on{background:var(--bosque);color:var(--verde);border-color:var(--bosque)}
  .tab .n{display:inline-block;margin-left:6px;background:var(--limaSuave);color:var(--bosque);
    border-radius:999px;padding:0 7px;font-size:11px;font-weight:900}
  .tab.on .n{background:rgba(255,255,255,.2);color:#fff}
  .card{background:var(--card);border:1px solid var(--border);border-radius:16px;
    padding:16px;margin-bottom:12px}
  .card .top{display:flex;align-items:flex-start;gap:10px}
  .card h3{margin:0;font-size:16px;font-weight:800;flex:1}
  .cod{background:#EAF6C2;color:var(--bosque);font-weight:900;font-size:12px;
    border-radius:999px;padding:5px 10px;white-space:nowrap}
  .row{font-size:13px;color:var(--muted);margin-top:5px}
  .row b{color:var(--text);font-weight:700}
  .chip{display:inline-block;border-radius:999px;padding:3px 10px;font-size:11px;
    font-weight:800;margin-top:8px}
  .est-pendiente_triage{background:#FBEAD2;color:#9A5B12}
  .est-aprobado_triage{background:#DDEBFF;color:#1E4FA3}
  .est-pendiente_validacion{background:#FFF3C4;color:#8A6D00}
  .est-activada{background:#D7F5E3;color:#1F8F4E}
  .est-rechazada{background:#FAD7DB;color:#9A1722}
  .wa{display:inline-flex;align-items:center;gap:7px;margin-top:10px;text-decoration:none;
    background:#E7F8EE;border:1px solid #BBE8CF;border-radius:10px;padding:8px 12px;
    color:#1F8F4E;font-weight:800;font-size:13px}
  .actions{display:flex;gap:10px;margin-top:14px}
  .actions button{flex:1;border-radius:12px;padding:11px;font-family:inherit;
    font-weight:800;font-size:14px;cursor:pointer;border:1px solid var(--border)}
  .btn-ap{background:var(--bosque);color:var(--verde);border-color:var(--bosque)}
  .btn-rc{background:#fff;color:var(--rojo);border-color:#F3C9CE}
  .btn-ap:disabled,.btn-rc:disabled{opacity:.5;cursor:default}
  .empty{text-align:center;color:var(--muted);padding:50px 10px}
  .toast{position:fixed;left:50%;bottom:24px;transform:translateX(-50%);
    background:var(--bosque);color:#fff;padding:12px 18px;border-radius:12px;
    font-weight:700;font-size:14px;z-index:20;box-shadow:0 6px 20px rgba(0,0,0,.2)}
  /* login */
  .gate{position:fixed;inset:0;background:var(--bg);display:flex;align-items:center;
    justify-content:center;padding:24px;z-index:30}
  .gate .box{background:#fff;border:1px solid var(--border);border-radius:18px;
    padding:28px 24px;max-width:380px;width:100%;text-align:center}
  .gate .pin{width:54px;height:54px;border-radius:50%;background:var(--verde);
    display:flex;align-items:center;justify-content:center;font-size:28px;margin:0 auto 14px}
  .gate h2{margin:0 0 4px;font-weight:900}
  .gate p{margin:0 0 18px;color:var(--muted);font-size:14px}
  .gate input{width:100%;padding:12px 14px;border:1px solid var(--border);border-radius:10px;
    font-family:inherit;font-size:15px;margin-bottom:12px}
  .gate button{width:100%;background:var(--bosque);color:var(--verde);border:0;
    border-radius:12px;padding:13px;font-family:inherit;font-weight:800;font-size:15px;cursor:pointer}
  .gate .err{color:var(--rojo);font-size:13px;font-weight:700;min-height:18px;margin-bottom:8px}
</style>
</head>
<body>
<div class="gate" id="gate">
  <div class="box">
    <div class="pin">📍</div>
    <h2>Pichangol</h2>
    <p>Panel de administración de canchas</p>
    <div class="err" id="gateErr"></div>
    <input id="tok" type="password" placeholder="Token de administrador" autocomplete="off">
    <button onclick="entrar()">Entrar</button>
  </div>
</div>

<header style="display:none" id="hdr">
  <div class="pin">📍</div>
  <h1>Pichangol · Canchas</h1>
  <div class="sp"></div>
  <button onclick="cargar()">↻ Actualizar</button>
  <button onclick="salir()">Salir</button>
</header>

<div class="wrap" id="app" style="display:none">
  <div class="tabs" id="tabs"></div>
  <div id="lista"></div>
</div>

<script>
const FILTROS = [
  ['pendiente_triage','Por aprobar'],
  ['activada','Activadas'],
  ['rechazada','Rechazadas'],
  ['','Todas'],
];
let filtro = 'pendiente_triage';
let cache = [];

function tok(){ return localStorage.getItem('pichangol_admin_tok') || ''; }
function headers(){ return {'Content-Type':'application/json','X-Admin-Token':tok()}; }

async function entrar(){
  const t = document.getElementById('tok').value.trim();
  const err = document.getElementById('gateErr');
  err.textContent='';
  if(!t){ err.textContent='Ingresa el token.'; return; }
  const r = await fetch('/admin/api/sesion',{headers:{'X-Admin-Token':t}});
  if(r.ok){
    localStorage.setItem('pichangol_admin_tok',t);
    mostrarApp();
  } else if(r.status===503){
    err.textContent='El panel no está configurado en el servidor (ADMIN_PANEL_TOKEN).';
  } else {
    err.textContent='Token inválido.';
  }
}
function salir(){ localStorage.removeItem('pichangol_admin_tok'); location.reload(); }
function mostrarApp(){
  document.getElementById('gate').style.display='none';
  document.getElementById('hdr').style.display='flex';
  document.getElementById('app').style.display='block';
  renderTabs();
  cargar();
}
function toast(msg){
  const d=document.createElement('div'); d.className='toast'; d.textContent=msg;
  document.body.appendChild(d); setTimeout(()=>d.remove(),2600);
}
function esc(s){ return (s==null?'':String(s)).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c])); }

function renderTabs(){
  const counts = {};
  cache.forEach(r=>{counts[r.estado]=(counts[r.estado]||0)+1;});
  document.getElementById('tabs').innerHTML = FILTROS.map(([k,lbl])=>{
    const n = k==='' ? cache.length : (counts[k]||0);
    return `<div class="tab ${filtro===k?'on':''}" onclick="setFiltro('${k}')">${lbl}<span class="n">${n}</span></div>`;
  }).join('');
}
function setFiltro(k){ filtro=k; renderTabs(); render(); }

async function cargar(){
  const r = await fetch('/admin/api/reclamos',{headers:headers()});
  if(r.status===401){ salir(); return; }
  cache = await r.json();
  cache.reverse(); // más recientes primero
  renderTabs(); render();
}

function waLink(tel,nombre,cod){
  let d=(tel||'').replace(/[^0-9]/g,'');
  if(d.length===9 && d[0]==='9') d='51'+d;
  const msg=encodeURIComponent('Hola, te escribo de Pichangol por el reclamo de "'+(nombre||'')+'". Tu código es '+(cod||'')+'. ¿Validamos que eres el dueño?');
  return 'https://wa.me/'+d+'?text='+msg;
}

function render(){
  const items = filtro==='' ? cache : cache.filter(r=>r.estado===filtro);
  const cont = document.getElementById('lista');
  if(!items.length){ cont.innerHTML='<div class="empty">No hay reclamos en este estado.</div>'; return; }
  cont.innerHTML = items.map(r=>{
    const pend = r.estado==='pendiente_triage';
    const titular = r.nombre_titular ? `<div class="row">👤 <b>${esc(r.nombre_titular)}</b> · DNI ${esc(r.dni||'—')}</div>`
      : (r.dni ? `<div class="row">DNI ${esc(r.dni)} <i>(sin datos)</i></div>` : '');
    const razon = r.razon_social ? `<div class="row">🏢 ${esc(r.razon_social)} · RUC ${esc(r.ruc||'')}</div>` : '';
    const rel = r.relacion ? `<div class="row">Relación: <b>${esc(r.relacion)}</b></div>` : '';
    const wa = r.telefono_contacto ? `<a class="wa" href="${waLink(r.telefono_contacto,r.nombre_local,r.codigo)}" target="_blank" rel="noopener">💬 ${esc(r.telefono_contacto)} · Escribir</a>` : '';
    const acc = pend ? `<div class="actions">
        <button class="btn-rc" onclick="decidir(${r.id},false,this)">Rechazar</button>
        <button class="btn-ap" onclick="decidir(${r.id},true,this)">Aprobar y activar</button>
      </div>` : '';
    return `<div class="card">
      <div class="top">
        <h3>${esc(r.nombre_local||'Local')}</h3>
        <span class="cod">cód. ${esc(r.codigo||'------')}</span>
      </div>
      ${titular}${razon}${rel}
      <div class="row">Solicitante: ${esc(r.solicitante_id||'—')}</div>
      ${wa}
      <div><span class="chip est-${esc(r.estado)}">${esc(r.estado)}</span></div>
      ${acc}
    </div>`;
  }).join('');
}

async function decidir(id, aprobado, btn){
  const card = btn.closest('.card');
  card.querySelectorAll('button').forEach(b=>b.disabled=true);
  const r = await fetch('/admin/api/reclamo/'+id+'/decidir',{
    method:'POST', headers:headers(),
    body: JSON.stringify({aprobado:aprobado, revisor:'panel'})
  });
  if(r.status===401){ salir(); return; }
  const j = await r.json();
  if(j.ok){
    toast(aprobado?'✅ Cancha aprobada y activada':'❌ Reclamo rechazado');
    cargar();
  } else {
    toast('No se pudo: '+(j.error||'error'));
    card.querySelectorAll('button').forEach(b=>b.disabled=false);
  }
}

// auto-login si ya hay token guardado
if(tok()){
  fetch('/admin/api/sesion',{headers:headers()}).then(r=>{ if(r.ok) mostrarApp(); });
}
document.getElementById('tok').addEventListener('keydown',e=>{ if(e.key==='Enter') entrar(); });
</script>
</body>
</html>"""
