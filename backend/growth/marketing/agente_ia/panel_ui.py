"""Pestaña "Marketing IA" de la torre de control (`/admin`).

Se inyecta en el HTML de `propiedad/panel.py` (estilos + script) para no
engordar más ese archivo. Usa los helpers de la torre: `headers()`, `salir()`,
`toast()`, `esc()`. Todo pasa por `/admin/api/mkt/*` (sesión admin).
"""

BLOQUE = r"""
<style>
  #page-marketing .mk-bar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:0 0 14px}
  #page-marketing .mk-pill{display:inline-flex;align-items:center;gap:6px;border-radius:999px;padding:5px 11px;font-size:12px;
    font-weight:700;border:1px solid var(--border);background:#fff;color:var(--muted)}
  #page-marketing .mk-pill.ok{background:#E7F8EE;border-color:#BBE8CF;color:#1F8F4E}
  #page-marketing .mk-pill.no{background:#FDECEE;border-color:#F3C9CE;color:#9A1722}
  #page-marketing .mk-pill.warn{background:#FFF6DA;border-color:#F2DF9B;color:#8A6D00}
  #page-marketing .mk-tabs{display:flex;gap:6px;flex-wrap:wrap;margin:6px 0 16px}
  #page-marketing .mk-tab{border:1px solid var(--border);background:#fff;border-radius:999px;padding:7px 14px;font:inherit;
    font-weight:700;font-size:13px;cursor:pointer;color:var(--text)}
  #page-marketing .mk-tab.on{background:var(--verde);border-color:var(--verde);color:#fff}
  #page-marketing .mk-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:14px}
  #page-marketing .mk-card{background:#fff;border:1px solid var(--border);border-radius:16px;padding:14px;display:flex;
    flex-direction:column;gap:8px;min-width:0}
  #page-marketing .mk-img{width:100%;aspect-ratio:1/1;object-fit:cover;border-radius:12px;background:#eef3f0}
  #page-marketing .mk-meta{display:flex;flex-wrap:wrap;gap:5px}
  #page-marketing .mk-tag{font-size:11px;font-weight:700;border-radius:8px;padding:3px 8px;background:#eef3f0;color:var(--green-deep)}
  #page-marketing .st{font-size:11px;font-weight:800;border-radius:999px;padding:3px 9px}
  #page-marketing .st-PENDING_APPROVAL{background:#FBEAD2;color:#9A5B12}
  #page-marketing .st-APPROVED,#page-marketing .st-PUBLISHING{background:#DDEBFF;color:#1E4FA3}
  #page-marketing .st-PUBLISHED{background:#D7F5E3;color:#1F8F4E}
  #page-marketing .st-REJECTED,#page-marketing .st-FAILED{background:#FAD7DB;color:#9A1722}
  #page-marketing .st-CANCELLED,#page-marketing .st-DRAFT{background:#eee;color:#666}
  #page-marketing .mk-why{font-size:12.5px;color:var(--muted);background:#f7faf9;border-radius:10px;padding:8px 10px}
  #page-marketing .mk-err{font-size:12.5px;color:#9A1722;background:#FDECEE;border-radius:10px;padding:8px 10px}
  #page-marketing textarea,#page-marketing input,#page-marketing select{width:100%;font:inherit;font-size:13px;border:1px solid var(--border);
    border-radius:10px;padding:8px 10px;background:#fff;color:var(--text)}
  #page-marketing textarea{min-height:130px;resize:vertical}
  #page-marketing .mk-acts{display:flex;flex-wrap:wrap;gap:6px}
  #page-marketing .mk-acts button{flex:1 1 auto;border-radius:12px;padding:8px 10px;font:inherit;font-weight:800;font-size:12.5px;
    cursor:pointer;border:1px solid var(--border);background:#fff;color:var(--bosque)}
  #page-marketing .mk-acts button.pri{background:var(--verde);border-color:var(--verde);color:#fff}
  #page-marketing .mk-acts button.dan{color:var(--rojo);border-color:#F3C9CE}
  #page-marketing .mk-cal{display:grid;grid-template-columns:repeat(7,minmax(120px,1fr));gap:8px;overflow-x:auto}
  #page-marketing .mk-dia{background:#fff;border:1px solid var(--border);border-radius:12px;padding:8px;min-height:140px}
  #page-marketing .mk-dia h4{margin:0 0 6px;font-size:12px;color:var(--muted);text-transform:capitalize}
  #page-marketing .mk-ev{font-size:12px;border-radius:8px;padding:6px;margin-bottom:6px;cursor:pointer;background:#f4f7f6}
  #page-marketing .mk-kv{display:grid;grid-template-columns:repeat(auto-fill,minmax(110px,1fr));gap:6px}
  #page-marketing .mk-kv div{background:#f7faf9;border-radius:10px;padding:6px 8px;font-size:11.5px;color:var(--muted)}
  #page-marketing .mk-kv b{display:block;font-size:15px;color:var(--text)}
  #page-marketing .mk-form{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:12px}
  #page-marketing .mk-form label{font-size:12px;font-weight:700;color:var(--muted);display:flex;flex-direction:column;gap:4px}
  #page-marketing details summary{cursor:pointer;font-size:12px;color:var(--muted)}
  #page-marketing pre{white-space:pre-wrap;font-size:11.5px;background:#f7faf9;border-radius:10px;padding:8px;margin:6px 0 0;max-height:220px;overflow:auto}
  #page-marketing table{width:100%;border-collapse:collapse;font-size:12.5px}
  #page-marketing td,#page-marketing th{border-bottom:1px solid var(--border);padding:6px;text-align:left;vertical-align:top}
  #page-marketing{min-width:0;max-width:100%}
  #page-marketing .card{overflow-x:auto;max-width:100%}
  #page-marketing td small{word-break:break-word}
  #page-marketing .mk-cal{max-width:100%}
  @media (max-width:640px){#page-marketing .mk-grid{grid-template-columns:1fr}
    #page-marketing .mk-cal{grid-template-columns:repeat(7,minmax(150px,1fr))}}
</style>
<script>
const MK = {tab:'bandeja', resumen:null, piezas:[], semana:0};
const MK_ESTADO = {DRAFT:'Borrador', PENDING_APPROVAL:'Por aprobar', APPROVED:'Aprobada', PUBLISHED:'Publicada',
  REJECTED:'Rechazada', FAILED:'Falló', CANCELLED:'Cancelada', PUBLISHING:'Publicando…'};
const MK_ORIGEN = {foto_real:'📷 Foto real', foto_dueno:'🏟️ Foto del dueño', diseno:'🎨 Diseño de marca', ia_conceptual:'✨ IA conceptual'};
function mkFecha(s){ if(!s) return '—'; const d=new Date(s); return d.toLocaleString('es-PE',{weekday:'short',day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit'}); }
function mkLocalInput(s){ const d=s?new Date(s):new Date(Date.now()+3600e3); const p=n=>String(n).padStart(2,'0');
  return `${d.getFullYear()}-${p(d.getMonth()+1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`; }
async function mkApi(ruta, cuerpo){
  const r = await fetch('/admin/api/mkt'+ruta, cuerpo===undefined ? {headers:headers()} : {method:'POST',headers:headers(),body:JSON.stringify(cuerpo)});
  if(r.status===401){ salir(); throw new Error('sesión'); }
  const j = await r.json().catch(()=>({}));
  if(!r.ok){ const m = typeof j.detail==='string' ? j.detail : (j.detail&&j.detail[0]&&j.detail[0].msg) || 'Error'; toast(m); throw new Error(m); }
  return j;
}
async function mkCargar(){
  const box = document.getElementById('mkBox'); if(!box) return;
  try{
    MK.resumen = await mkApi('');
    const desde = new Date(Date.now()-30*864e5).toISOString();
    MK.piezas = (await mkApi('/piezas?desde='+encodeURIComponent(desde))).piezas;
  }catch(e){ return; }
  mkRender();
}
function mkBar(){
  const R = MK.resumen, c = R.config;
  const pill = (ok, txt, warn) => `<span class="mk-pill ${ok?'ok':(warn?'warn':'no')}">${txt}</span>`;
  return `<div class="mk-bar">
    ${pill(c.activo, c.activo?'● Agente activo':'○ Agente apagado')}
    ${pill(c.modo==='aprobar', c.modo==='aprobar'?'Modo: aprobación humana':'Modo: automático validado', true)}
    ${c.pausa?pill(false,'⏸ Publicación en pausa'):''}
    ${pill(R.facebook_listo, R.facebook_listo?'Facebook conectado':'Facebook sin token')}
    ${pill(R.instagram_listo, R.instagram_listo?'Instagram conectado':'Instagram apagado', true)}
    ${pill(R.ia, R.ia?'IA disponible':'Sin IA: reglas + plantillas', true)}
    ${pill(R.atribucion.length===3, R.atribucion.length===3?'Atribución de reservas lista':'Falta SQL de atribución', true)}
    ${R.agente_viejo_activo?pill(false,'⚠ El agente de calendario fijo sigue activo'):''}
    <span style="flex:1"></span>
    <select id="mkPais" style="width:auto">${['PE','BO','EC'].map(p=>`<option ${c.paises.includes(p)?'':'disabled'}>${p}</option>`).join('')}</select>
    <button class="mk-tab" onclick="mkCorrer()">▶ Correr ahora</button>
  </div>`;
}
function mkRender(){
  const box = document.getElementById('mkBox'); if(!box) return;
  const n = MK.resumen.conteo;
  const tabs = [['bandeja',`Por aprobar (${n.PENDING_APPROVAL||0})`],['calendario','Calendario'],['publicadas',`Publicadas (${n.PUBLISHED||0})`],
    ['rechazadas',`Rechazadas / fallidas (${(n.REJECTED||0)+(n.FAILED||0)})`],['estrategia','Estrategia y aprendizajes'],['config','Configuración'],['bitacora','Bitácora']];
  let cuerpo = '';
  if(MK.tab==='bandeja') cuerpo = mkGrid(MK.piezas.filter(p=>p.status==='PENDING_APPROVAL'||p.status==='APPROVED'), 'No hay piezas pendientes. El agente crea las del día a la hora de planificación.');
  if(MK.tab==='publicadas') cuerpo = mkGrid(MK.piezas.filter(p=>p.status==='PUBLISHED'), 'Aún no hay publicaciones.');
  if(MK.tab==='rechazadas') cuerpo = mkGrid(MK.piezas.filter(p=>['REJECTED','FAILED'].includes(p.status)), 'Nada rechazado ni fallido.');
  if(MK.tab==='calendario') cuerpo = mkCalendario();
  if(MK.tab==='estrategia') cuerpo = mkEstrategia();
  if(MK.tab==='config') cuerpo = mkConfig();
  if(MK.tab==='bitacora'){ cuerpo = '<div id="mkLogs" class="card">Cargando…</div>'; setTimeout(mkLogs,0); }
  box.innerHTML = mkBar() + `<div class="mk-tabs">${tabs.map(([k,l])=>`<button class="mk-tab ${MK.tab===k?'on':''}" onclick="MK.tab='${k}';mkRender()">${l}</button>`).join('')}</div>` + cuerpo;
  box.querySelectorAll('img[data-mk]').forEach(mkImagen);
}
function mkGrid(lista, vacio){
  if(!lista.length) return `<div class="card">${vacio}</div>`;
  return `<div class="mk-grid">${lista.map(mkCard).join('')}</div>`;
}
async function mkImagen(img){
  try{ const j = await mkApi('/pieza/'+img.dataset.mk+'/imagen'); img.src = j.imagen; }catch(e){}
}
function mkMetricas(m){
  if(!m) return '';
  const k = (lbl,v)=> v==null?'':`<div>${lbl}<b>${v}</b></div>`;
  return `<div class="mk-kv">${k('Alcance',m.alcance)}${k('Interacciones',m.interacciones)}${k('Engagement',m.engagement_rate!=null?(m.engagement_rate*100).toFixed(1)+'%':null)}
    ${k('Clics enlace',m.clics_link)}${k('Reservas',m.reservas_atribuidas)}${k('Comentarios',m.comentarios)}${k('Compartidos',m.compartidos)}</div>`;
}
function mkCard(p){
  const op = p.oportunidad||{}, v = p.validacion||{};
  const editable = ['PENDING_APPROVAL','REJECTED','FAILED','APPROVED'].includes(p.status);
  const texto = (p.body||'').split('\n\n').filter(x=>!x.includes(p.link_url||'\u0000') && !x.trim().startsWith('#')).join('\n\n');
  const acts = [];
  if(p.status==='PENDING_APPROVAL') acts.push(`<button class="pri" onclick="mkAccion('${p.id}','aprobar')">✓ Aprobar</button>`);
  if(['PENDING_APPROVAL','APPROVED'].includes(p.status)) acts.push(`<button onclick="mkAccion('${p.id}','publicar')">🚀 Publicar ya</button>`);
  if(['PENDING_APPROVAL','APPROVED','FAILED'].includes(p.status)) acts.push(`<button onclick="mkReprogramar('${p.id}')">🗓 Reprogramar</button>`);
  if(editable) acts.push(`<button onclick="mkGuardar('${p.id}')">💾 Guardar edición</button>`);
  if(p.status!=='PUBLISHED') acts.push(`<button onclick="mkAccion('${p.id}','regenerar')">↻ Otra versión</button>`);
  if(['PENDING_APPROVAL','APPROVED','FAILED'].includes(p.status)) acts.push(`<button class="dan" onclick="mkRechazar('${p.id}')">✕ Rechazar</button>`);
  if(['PENDING_APPROVAL','APPROVED','FAILED','REJECTED'].includes(p.status)) acts.push(`<button class="dan" onclick="mkAccion('${p.id}','cancelar')">Cancelar</button>`);
  const f = (id,val,tope)=>`<input id="mk_${id}_${p.id}" value="${esc(val||'').replace(/"/g,'&quot;')}" maxlength="${tope}" ${editable?'':'disabled'}>`;
  return `<div class="mk-card">
    <div class="mk-meta"><span class="st st-${p.status}">${MK_ESTADO[p.status]||p.status}</span>
      <span class="mk-tag">${p.platform}</span><span class="mk-tag">${p.audiencia==='duenos'?'Dueños':'Jugadores'}</span>
      <span class="mk-tag">🎯 ${esc(p.objetivo)} · KPI ${esc(p.kpi)}</span>${p.zona?`<span class="mk-tag">📍 ${esc(p.zona)}</span>`:''}
      <span class="mk-tag">${MK_ORIGEN[p.media_origen]||''}</span><span class="mk-tag">${{ia:'✍️ Copy IA', banco:'✍️ Plantilla'}[(p.fuente||'').split('+')[0]]||esc(p.fuente)}${(p.fuente||'').includes('editado')?' · editado':''}</span></div>
    <img class="mk-img" data-mk="${p.id}" alt="">
    <div class="row">🕒 ${p.status==='PUBLISHED'?'Publicada '+mkFecha(p.published_at):'Programada '+mkFecha(p.scheduled_at)}
      ${/^https:\/\/[^"'<>\s]+$/.test(p.permalink||'')?` · <a href="${p.permalink}" target="_blank" rel="noopener">ver post</a>`:''}</div>
    <div class="mk-why"><b>¿Por qué?</b> ${esc(op.por_que||op.razon||'')}</div>
    ${(v.errores||[]).length?`<div class="mk-err"><b>No pasa la validación:</b><br>${v.errores.map(esc).join('<br>')}</div>`:''}
    ${p.error?`<div class="mk-err">${esc(p.error)}</div>`:''}
    ${p.motivo_rechazo && p.status==='REJECTED' && !(v.errores||[]).length?`<div class="mk-err">${esc(p.motivo_rechazo)}</div>`:''}
    ${f('title',p.title,36)}${f('subtitle',p.subtitle,80)}${f('etiqueta',p.etiqueta,14)}
    <textarea id="mk_texto_${p.id}" ${editable?'':'disabled'}>${esc(texto)}</textarea>
    ${f('call_to_action',p.call_to_action,90)}
    <div class="row">🔗 ${esc(p.link_url||'')} · ${(p.hashtags||[]).map(esc).join(' ')}</div>
    ${mkMetricas(p.metricas)}
    <details><summary>Datos reales que respaldan la pieza</summary><pre>${esc(JSON.stringify(p.hechos,null,2))}</pre>
      ${(p.targets||[]).length?`<div class="row">Canchas asociadas: ${p.targets.map(t=>esc(t.cancha_id)+(t.rol==='destacada'?' ★':'')).join(', ')}</div>`:''}</details>
    <div class="mk-acts">${acts.join('')}</div>
  </div>`;
}
async function mkAccion(id, accion, extra){
  try{ await mkApi('/pieza/'+id+'/'+accion, extra||{}); toast('Listo'); }catch(e){ return; }
  mkCargar();
}
async function mkGuardar(id){
  const g = k => document.getElementById(`mk_${k}_${id}`).value;
  try{ const j = await mkApi('/pieza/'+id+'/editar', {title:g('title'), subtitle:g('subtitle'), etiqueta:g('etiqueta'), texto:g('texto'), call_to_action:g('call_to_action')});
    toast(j.pieza.status==='PENDING_APPROVAL'?'Guardado y validado ✓':'Guardado, pero no pasa la validación'); }catch(e){ return; }
  mkCargar();
}
function mkRechazar(id){ const m = prompt('Motivo del rechazo (ayuda al agente a aprender):',''); if(m===null) return; mkAccion(id,'rechazar',{motivo:m}); }
function mkReprogramar(id){
  const p = MK.piezas.find(x=>x.id===id);
  const v = prompt('Nueva fecha y hora (AAAA-MM-DDTHH:MM, hora de tu navegador):', mkLocalInput(p&&p.scheduled_at));
  if(!v) return;
  const d = new Date(v); if(isNaN(d)) { toast('Fecha inválida'); return; }
  mkAccion(id,'reprogramar',{cuando:d.toISOString()});
}
async function mkCorrer(){
  const pais = document.getElementById('mkPais').value;
  toast('Analizando datos y creando piezas…');
  try{ const j = await mkApi('/correr',{pais}); toast(`${j.piezas.length} pieza(s) creada(s) (${j.fuente==='ia'?'IA':'reglas'})`); }catch(e){ return; }
  MK.tab='bandeja'; mkCargar();
}
function mkCalendario(){
  const ini = new Date(); ini.setHours(0,0,0,0); ini.setDate(ini.getDate()-((ini.getDay()+6)%7)+7*MK.semana);
  const dias = [...Array(7)].map((_,i)=>{ const d=new Date(ini); d.setDate(d.getDate()+i); return d; });
  const visibles = MK.piezas.filter(p=>!['CANCELLED'].includes(p.status));
  const col = d => { const fin = new Date(d); fin.setDate(fin.getDate()+1);
    const ev = visibles.filter(p=>{ const t=new Date(p.published_at||p.scheduled_at||p.created_at); return t>=d && t<fin; })
      .sort((a,b)=>new Date(a.published_at||a.scheduled_at)-new Date(b.published_at||b.scheduled_at));
    return `<div class="mk-dia"><h4>${d.toLocaleDateString('es-PE',{weekday:'long',day:'2-digit',month:'short'})}</h4>
      ${ev.map(p=>`<div class="mk-ev" onclick="MK.tab='${p.status==='PUBLISHED'?'publicadas':(['REJECTED','FAILED'].includes(p.status)?'rechazadas':'bandeja')}';mkRender()">
        <span class="st st-${p.status}">${MK_ESTADO[p.status]}</span><br>${new Date(p.published_at||p.scheduled_at).toLocaleTimeString('es-PE',{hour:'2-digit',minute:'2-digit'})} · ${esc(p.title||'')}<br>
        <small>${p.platform} · ${p.audiencia==='duenos'?'dueños':'jugadores'}</small></div>`).join('')||'<small style="color:var(--muted)">—</small>'}</div>`; };
  return `<div class="mk-bar"><button class="mk-tab" onclick="MK.semana--;mkRender()">← Semana anterior</button>
    <button class="mk-tab" onclick="MK.semana=0;mkRender()">Esta semana</button><button class="mk-tab" onclick="MK.semana++;mkRender()">Semana siguiente →</button></div>
    <div class="mk-cal">${dias.map(col).join('')}</div>`;
}
function mkEstrategia(){
  const R = MK.resumen;
  const ins = R.insights.length ? `<table><tr><th>Aprendizaje</th><th>Confianza</th><th>Muestras</th></tr>${R.insights.map(i=>`<tr><td>${esc(i.enunciado)}</td><td>${(i.confianza*100).toFixed(0)}%</td><td>${i.muestras}</td></tr>`).join('')}</table>`
    : '<p class="row">Aún no hay aprendizajes: se calculan cada lunes cuando hay al menos 8 publicaciones medidas.</p>';
  const est = R.estrategias.map(e=>`<tr><td>${esc(e.fecha)} · ${esc(e.pais)}</td><td>${e.fuente==='ia'?'IA':'reglas'}</td>
    <td>${(e.oportunidades||[]).map(o=>`<b>${esc(o.tipo)}</b> (${esc(o.audiencia)}, ${esc(o.objetivo)}): ${esc(o.por_que||o.razon)}`).join('<br>')}</td></tr>`).join('');
  return `<div class="card"><h3>Aprendizajes vigentes</h3>${ins}</div><br>
    <div class="card"><h3>Estrategia de los últimos días</h3><table><tr><th>Día</th><th>Fuente</th><th>Oportunidades elegidas</th></tr>${est||'<tr><td colspan=3>Sin corridas aún.</td></tr>'}</table></div>`;
}
function mkConfig(){
  const c = MK.resumen.config;
  const chk = (k,l)=>`<label><span><input type="checkbox" id="mkc_${k}" style="width:auto" ${c[k]?'checked':''}> ${l}</span></label>`;
  const num = (k,l,min,max,step)=>`<label>${l}<input type="number" id="mkc_${k}" value="${c[k]}" min="${min}" max="${max}" step="${step||1}"></label>`;
  return `<div class="card"><div class="mk-form">
    ${chk('activo','Agente activo (reemplaza al calendario fijo)')}
    <label>Modo<select id="mkc_modo"><option value="aprobar" ${c.modo==='aprobar'?'selected':''}>Aprobación humana</option>
      <option value="auto_validado" ${c.modo==='auto_validado'?'selected':''}>Automático validado (fase 6)</option></select></label>
    ${chk('pausa','⏸ Pausar toda publicación (freno de emergencia)')}
    <label>Hora de planificación (hora local)<input id="mkc_hora_plan" value="${c.hora_plan}"></label>
    <label>Países (coma)<input id="mkc_paises" value="${c.paises.join(',')}"></label>
    <label>Redes (coma)<input id="mkc_plataformas" value="${c.plataformas.join(',')}"></label>
    ${num('posts_dia','Piezas por día',1,3)}
    ${num('auto_max_dia','Tope diario en modo automático',0,5)}
    ${num('umbral','Canchas reservables por zona para vender disponibilidad',1,200)}
    ${num('mix_baja','% dueños con poca oferta (0-1)',0,1,0.05)}
    ${num('mix_alta','% dueños con oferta suficiente (0-1)',0,1,0.05)}
    <label>Tono<select id="mkc_tono">${['cercano','divertido','informativo','motivador'].map(t=>`<option ${c.tono===t?'selected':''}>${t}</option>`).join('')}</select></label>
    ${chk('destacar_pro','Destacar locales Pro por nombre')}
    ${chk('arte_ia','Permitir arte IA conceptual (si no hay fotos reales)')}
  </div><div class="mk-acts" style="margin-top:14px"><button class="pri" onclick="mkGuardarConfig()">Guardar configuración</button></div></div>`;
}
async function mkGuardarConfig(){
  const g = k => document.getElementById('mkc_'+k);
  const cuerpo = {activo:g('activo').checked, modo:g('modo').value, pausa:g('pausa').checked, hora_plan:g('hora_plan').value,
    paises:g('paises').value.split(',').map(s=>s.trim().toUpperCase()).filter(Boolean), plataformas:g('plataformas').value.split(',').map(s=>s.trim().toLowerCase()).filter(Boolean),
    posts_dia:+g('posts_dia').value, auto_max_dia:+g('auto_max_dia').value, umbral:+g('umbral').value, mix_baja:+g('mix_baja').value, mix_alta:+g('mix_alta').value,
    tono:g('tono').value, destacar_pro:g('destacar_pro').checked, arte_ia:g('arte_ia').checked};
  if(cuerpo.modo==='auto_validado' && !confirm('En modo automático el agente publica sin revisión humana las piezas que pasan todos los controles. ¿Continuar?')) return;
  try{ await mkApi('/config', cuerpo); toast('Configuración guardada'); }catch(e){ return; }
  mkCargar();
}
async function mkLogs(){
  const box = document.getElementById('mkLogs'); if(!box) return;
  try{ const j = await mkApi('/logs');
    box.innerHTML = `<table><tr><th>Cuándo</th><th>Agente</th><th>Acción</th><th>Detalle</th></tr>${j.logs.map(l=>`<tr><td>${mkFecha(l.created_at)}</td><td>${esc(l.agente)}</td>
      <td>${l.nivel!=='info'?'⚠ ':''}${esc(l.accion)}</td><td><small>${esc(JSON.stringify(l.detalle)).slice(0,300)}</small></td></tr>`).join('')}</table>`;
  }catch(e){}
}
</script>
"""

SECCION = """    <section id="page-marketing" class="page" style="display:none">
      <div class="page-head">
        <div class="page-eyebrow">Crecimiento</div>
        <h1 class="page-h">Marketing IA</h1>
        <p class="page-sub">El agente analiza los datos reales de Pichangol, decide qué comunicar y a quién,
          crea las piezas y las deja aquí para aprobar. Nada se publica sin pasar los controles: sin precios,
          zonas, locales ni promociones que no estén en la base.</p>
      </div>
      <div id="mkBox"><div class="card">Cargando…</div></div>
    </section>
"""

BOTON = """      <button class="topnav-tab" data-sec="marketing" onclick="mostrarSeccion('marketing')" title="Marketing IA"><span class="ico">📣</span> <span class="tx">Marketing IA</span></button>
"""


def inyectar(html: str) -> str:
    """Agrega botón, sección, estilos y script a la torre (idempotente)."""
    if 'id="page-marketing"' in html:
        return html
    html = html.replace("""      <button class="topnav-tab" data-sec="pruebas" """, BOTON + """      <button class="topnav-tab" data-sec="pruebas" """, 1)
    html = html.replace("""    <section id="page-pruebas" class="page" """, SECCION + """    <section id="page-pruebas" class="page" """, 1)
    html = html.replace("comunicacion:'Comunicación', pruebas:'Pruebas'};", "comunicacion:'Comunicación', marketing:'Marketing IA', pruebas:'Pruebas'};", 1)
    html = html.replace("  if(sec==='pruebas') cargarSeguridad();", "  if(sec==='pruebas') cargarSeguridad();\n  if(sec==='marketing') mkCargar();", 1)
    return html.replace("</body>\n</html>", BLOQUE + "</body>\n</html>", 1)
