// BARRIDO WEB (CI): recorre las pantallas públicas, del jugador y del anfitrión
// a 390 px (móvil) y 1440 px (escritorio) y FALLA si alguna pantalla:
//   · no responde 200 (salvo las 404 a propósito),
//   · tiene un error de JavaScript (pageerror o console.error),
//   · abre un diálogo del navegador (alert/confirm/prompt: regla "Popups en la WEB"),
//   · se desborda a lo ancho (un elemento pasa el borde derecho fuera de un
//     contenedor con scroll: regla "RESPONSIVO EN TODA LA WEB"),
//   · no tiene <h1>,
//   · viola la CSP (evento securitypolicyviolation: también en modo reporte),
//   · o una petición propia responde 5xx.
// Además un flujo: ficha → día → turno libre → "Resumen de tu pago" (sin pagar).
//
// Variables:
//   BASE          URL del servidor (default http://localhost:8000)
//   E2E_JUGADOR   correo:clave de la cuenta de revisión del jugador
//   E2E_DUENO     correo:clave de la cuenta de revisión del dueño
//   PW_CHROMIUM   ruta a un Chromium ya instalado (laptop); vacío = el de Playwright
//   E2E_SALIDA    carpeta de capturas y reporte (default ./salida)
//   E2E_SOLO      filtro por nombre de ruta (regex), para depurar
//   E2E_CANCHA_FLUJO  cancha del flujo de pago (default demo_bombo_f1)
//
// Uso: node barrido.mjs   (código de salida 1 si hay fallas)

import { chromium } from 'playwright';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const AQUI = path.dirname(fileURLToPath(import.meta.url));
const BASE = (process.env.BASE || 'http://localhost:8000').replace(/\/$/, '');
const OUT = process.env.E2E_SALIDA || path.join(AQUI, 'salida');
const SOLO = process.env.E2E_SOLO ? new RegExp(process.env.E2E_SOLO) : null;
const CANCHA_FLUJO = process.env.E2E_CANCHA_FLUJO || 'demo_bombo_f1';
fs.mkdirSync(path.join(OUT, 'capturas'), { recursive: true });

const cuenta = v => { const s = process.env[v] || ''; const i = s.indexOf(':'); return i > 0 ? { usuario: s.slice(0, i), clave: s.slice(i + 1) } : null; };
const CUENTAS = { anon: null, jugador: cuenta('E2E_JUGADOR'), dueno: cuenta('E2E_DUENO') };

// [nombre, ruta, quién, status esperado]
const RUTAS = [
  // públicas (sin sesión)
  ['portada', '/', 'anon'], ['canchas', '/canchas', 'anon'], ['canchas_tenis', '/canchas?deporte=tenis', 'anon'],
  ['academias', '/canchas?deporte=academias', 'anon'], ['ficha', '/reservar/demo_arena_f7', 'anon'],
  ['ficha_otro', '/reservar/demo_bombo_f1', 'anon'], ['ficha_tenis', '/reservar/demo_raqueta_t1', 'anon'],
  ['lugar', '/lugar/gp_demo?nombre=Club%20X&direccion=Av.%20Prueba%20123&lat=-12.11&lng=-77.03&deporte=futbol', 'anon'],
  ['academia', '/academia/demo_ac_raqueta', 'anon'], ['buscar', '/buscar', 'anon'], ['tenis', '/tenis', 'anon'],
  ['marketplace', '/marketplace', 'anon'], ['producto', '/marketplace/demo_prod_1', 'anon'], ['bonos_local', '/bonos/demo_arena_f7', 'anon'],
  ['terminos', '/legal/terminos', 'anon'], ['privacidad', '/legal/privacidad', 'anon'], ['devoluciones', '/legal/devoluciones', 'anon'],
  ['eliminar_cuenta', '/legal/eliminar-cuenta', 'anon'], ['libro', '/libro-de-reclamaciones', 'anon'], ['ayuda', '/ayuda', 'anon'],
  ['zona', '/canchas/futbol/miraflores', 'anon'], ['entrar', '/entrar', 'anon'],
  ['no_existe', '/reservar/no-existe-123', 'anon', 404], ['ruta_404', '/esto-no-existe', 'anon', 404],
  // jugador
  ['perfil', '/perfil', 'jugador'], ['mis_reservas', '/mis-reservas', 'jugador'], ['comprobante', '/reserva/grp_demo_g_0001', 'jugador'],
  ['comprobante_pasado', '/reserva/demo_r_0004', 'jugador'], ['reprogramar', '/reserva/grp_demo_g_0001/cambiar', 'jugador'],
  ['ficha_sesion', '/reservar/demo_bombo_f1', 'jugador'], ['academia_sesion', '/academia/demo_ac_raqueta', 'jugador'],
  ['billetera', '/mi-billetera', 'jugador'], ['estado_cuenta', '/mi-billetera/estado-de-cuenta', 'jugador'],
  ['mis_pagos', '/mis-pagos', 'jugador'], ['mis_puntos', '/mis-puntos', 'jugador'], ['mis_bonos', '/mis-bonos', 'jugador'],
  ['mis_ordenes', '/mis-ordenes', 'jugador'], ['mi_nivel', '/mi-nivel', 'jugador'], ['mi_pais', '/mi-pais', 'jugador'],
  ['liga', '/liga', 'jugador'], ['partidos', '/partidos', 'jugador'], ['partner', '/partidos?tab=partner', 'jugador'],
  ['pichangas', '/pichangas', 'jugador'], ['referidos', '/referidos', 'jugador'], ['novedades', '/novedades', 'jugador'],
  ['canales', '/canales', 'jugador'], ['mensajes', '/mensajes', 'jugador'], ['chat_nuevo', '/mensajes/nuevo?cancha=demo_bombo_f1', 'jugador'],
  ['pro', '/pro', 'jugador'], ['pro_planes', '/pro/planes', 'jugador'], ['config', '/cuenta/configuracion', 'jugador'],
  ['identidad', '/cuenta/identidad', 'jugador'], ['tarjetas', '/cuenta/tarjetas', 'jugador'], ['mis_clases', '/mis-clases', 'jugador'],
  ['pedidos_bodega', '/mis-pedidos-bodega', 'jugador'], ['notificaciones', '/notificaciones', 'jugador'],
  ['favoritos', '/mis-favoritos', 'jugador'],
  // anfitrión
  ['anf_menu', '/anfitrion', 'dueno'], ['anf_calendario', '/anfitrion/calendario', 'dueno'],
  ['anf_reservas', '/anfitrion/reservas', 'dueno'], ['anf_ingresos', '/anfitrion/ingresos', 'dueno'],
  ['anf_canchas', '/anfitrion/mis-canchas', 'dueno'], ['anf_editar_local', '/anfitrion/local/demo_arena_f7/editar', 'dueno'],
  ['anf_editar_cancha', '/anfitrion/cancha/demo_arena_f7/editar', 'dueno'], ['anf_agregar', '/anfitrion/cancha/demo_arena_f7/agregar', 'dueno'],
  ['anf_nueva', '/anfitrion/nueva', 'dueno'], ['anf_verificacion', '/anfitrion/verificacion/demo_arena_f7', 'dueno'],
  ['anf_verificador', '/anfitrion/verificador', 'dueno'], ['anf_cobros_club', '/anfitrion/cobros-club', 'dueno'],
  ['anf_por_confirmar', '/anfitrion/pagos-por-confirmar', 'dueno'], ['anf_reglas', '/anfitrion/reglas/demo_arena_f7', 'dueno'],
  ['anf_reportes', '/anfitrion/reportes', 'dueno'], ['anf_reportes_cobros', '/anfitrion/reportes/cobros', 'dueno'],
  ['anf_ocupacion', '/anfitrion/ocupacion', 'dueno'], ['anf_cancelaciones', '/anfitrion/cancelaciones', 'dueno'],
  ['anf_caja', '/anfitrion/caja', 'dueno'], ['anf_clientes', '/anfitrion/clientes', 'dueno'], ['anf_bonos', '/anfitrion/bonos', 'dueno'],
  ['anf_fijas', '/anfitrion/fijas', 'dueno'], ['anf_disponibilidad', '/anfitrion/disponibilidad', 'dueno'],
  ['anf_llenar', '/anfitrion/llenar', 'dueno'], ['anf_recordatorios', '/anfitrion/recordatorios', 'dueno'],
  ['anf_bodega', '/anfitrion/bodega', 'dueno'], ['anf_tienda', '/anfitrion/tienda', 'dueno'], ['anf_tienda_nuevo', '/anfitrion/tienda/nuevo', 'dueno'],
  ['anf_academia', '/anfitrion/academia', 'dueno'], ['anf_acad_editar', '/anfitrion/academia/demo_ac_raqueta/editar', 'dueno'],
  ['anf_alumnos', '/anfitrion/academia/alumnos?academia=demo_ac_raqueta', 'dueno'],
  ['anf_asistencia', '/anfitrion/academia/asistencia?academia=demo_ac_raqueta', 'dueno'],
  ['anf_eval', '/anfitrion/academia/evaluaciones?academia=demo_ac_raqueta', 'dueno'],
  ['anf_acad_rep', '/anfitrion/academia/reportes?academia=demo_ac_raqueta', 'dueno'],
  ['anf_acad_plan', '/anfitrion/academia/plan?academia=demo_ac_raqueta', 'dueno'],
  ['anf_cobros', '/anfitrion/cobros?academia=demo_ac_raqueta', 'dueno'],
  ['anf_cobros_agregar', '/anfitrion/cobros/agregar?academia=demo_ac_raqueta', 'dueno'],
  ['anf_campeonatos', '/anfitrion/campeonatos', 'dueno'], ['anf_boleador', '/anfitrion/boleador', 'dueno'],
  ['anf_mensajes', '/mensajes', 'dueno'],
].filter(r => !SOLO || SOLO.test(r[0]));

const VISTAS = [['mov', { width: 390, height: 844 }, true], ['pc', { width: 1440, height: 900 }, false]];

// Recolector de CSP en cada documento (también en modo solo-reporte el navegador dispara el evento).
const INIT = () => {
  document.addEventListener('securitypolicyviolation', ev => {
    try {
      window.__pcgCsp && window.__pcgCsp({ directiva: ev.effectiveDirective || ev.violatedDirective, bloqueado: String(ev.blockedURI || ''),
        fuente: String(ev.sourceFile || ''), linea: ev.lineNumber || 0, muestra: String(ev.sample || '').slice(0, 80), modo: ev.disposition });
    } catch (e) { /* nada */ }
  });
};

async function metricas(pg) {
  return pg.evaluate(() => {
    const W = document.documentElement.clientWidth;
    const desc = el => {
      let s = el.tagName.toLowerCase();
      if (el.id) s += '#' + el.id;
      else if (el.className && typeof el.className === 'string') s += '.' + el.className.trim().split(/\s+/).slice(0, 2).join('.');
      return s;
    };
    const fuera = [...document.querySelectorAll('body *')].filter(el => {
      const r = el.getBoundingClientRect();
      if (!r.width || r.right <= W + 2) return false;
      const cs = getComputedStyle(el);
      if (cs.position === 'fixed' || cs.visibility === 'hidden') return false;
      for (let p = el.parentElement; p; p = p.parentElement) {
        const s = getComputedStyle(p);
        if (p !== document.body && p !== document.documentElement && /(auto|scroll|hidden|clip)/.test(s.overflowX)) return false;
        if (s.position === 'fixed' || s.display === 'none' || s.visibility === 'hidden') return false;
      }
      return true;
    });
    // Solo el más externo de cada rama (no reportar sus hijos).
    const raiz = fuera.filter(el => !fuera.some(o => o !== el && o.contains(el)));
    return {
      h1: document.querySelectorAll('h1').length,
      titulo: document.title.slice(0, 70),
      fuera: raiz.length,
      fueraDe: raiz.slice(0, 5).map(el => `${desc(el)} (${Math.round(el.getBoundingClientRect().right)}px)`),
      anchoDoc: document.documentElement.scrollWidth,
      ancho: W,
    };
  });
}

// En CI el botón de Google se carga con un client id FALSO ("ci"): Google responde 403
// "client ID is not found". Es del ambiente, no de la página; cualquier otro error cuenta.
function esRuidoDeCI(texto, donde) {
  if (process.env.E2E_GOOGLE_REAL === '1') return false;
  if (/^\[GSI_LOGGER\]: The given client ID is not found/.test(texto)) return true;
  return /Failed to load resource.*403/.test(texto) && /^https:\/\/accounts\.google\.com\//.test(donde);
}

function nuevoRegistro() { return { errores: [], consola: [], dialogos: [], csp: [], http: [] }; }

async function abrirContexto(b, vp, mob, quien) {
  const ctx = await b.newContext({ viewport: vp, isMobile: mob, hasTouch: mob, locale: 'es-PE', timezoneId: 'America/Lima',
    geolocation: { latitude: -12.11, longitude: -77.03 }, permissions: ['geolocation'] });
  const reg = { actual: nuevoRegistro() };
  await ctx.exposeBinding('__pcgCsp', (_src, v) => { reg.actual.csp.push(v); });
  await ctx.addInitScript(INIT);
  // Sin "Abrir en la app" ni intentos de intent:// (solo Android) y sin banners guardados.
  await ctx.addInitScript(() => { try { sessionStorage.setItem('pcg_app_try', '1'); } catch (e) { /* nada */ } });
  if (CUENTAS[quien]) {
    const r = await ctx.request.post(BASE + '/web/sesion/prueba', { data: CUENTAS[quien] });
    const j = await r.json().catch(() => ({}));
    if (!r.ok() || !j.ok) throw new Error(`login ${quien} falló: ${r.status()} ${JSON.stringify(j).slice(0, 200)}`);
  }
  const pg = await ctx.newPage();
  pg.on('pageerror', e => reg.actual.errores.push(String(e).slice(0, 300)));
  pg.on('console', m => {
    if (m.type() !== 'error') return;
    const donde = (m.location() || {}).url || '';
    if (esRuidoDeCI(m.text(), donde)) return;
    reg.actual.consola.push(`${m.text().slice(0, 240)}${donde ? ' @ ' + donde.replace(BASE, '').slice(0, 120) : ''}`);
  });
  pg.on('dialog', d => { reg.actual.dialogos.push(`${d.type()}: ${d.message().slice(0, 160)}`); d.dismiss().catch(() => {}); });
  pg.on('response', r => {
    const u = r.url();
    if (u.startsWith(BASE) && r.status() >= 400 && !u.includes('/web/csp-reporte')) reg.actual.http.push(`${r.status()} ${u.replace(BASE, '').slice(0, 100)}`);
  });
  return { ctx, pg, reg };
}

function evaluar(fila, esperado) {
  const fallas = [];
  if (fila.st !== esperado) fallas.push(`HTTP ${fila.st} (esperado ${esperado})`);
  if (fila.redirigido) fallas.push(`terminó en ${fila.url}`);
  if (fila.errores.length) fallas.push(`JS: ${fila.errores[0]}`);
  // En las 404 a propósito el propio documento se anota como "Failed to load resource".
  const consola = fila.consola.filter(t => !(esperado === 404 && /Failed to load resource.*404/.test(t)));
  if (consola.length) fallas.push(`consola: ${consola[0]}`);
  if (fila.dialogos.length) fallas.push(`diálogo del navegador: ${fila.dialogos[0]}`);
  if (fila.fuera) fallas.push(`desborde: ${fila.fueraDe.join(', ')}`);
  if (!fila.h1) fallas.push('sin <h1>');
  if (fila.st !== 'timeout' && !fila.cspModo) fallas.push('la página no trae cabecera CSP');
  if (fila.csp.length) fallas.push(`CSP: ${fila.csp[0].directiva} ${fila.csp[0].bloqueado || fila.csp[0].muestra}`);
  const http5 = fila.http.filter(h => /^5\d\d /.test(h));
  if (http5.length) fallas.push(`petición ${http5[0]}`);
  return fallas;
}

async function visitar(pg, reg, nombre, ruta, vista, esperado) {
  reg.actual = nuevoRegistro();
  let st = 0, csp = ''; const t0 = Date.now();
  try {
    const r = await pg.goto(BASE + ruta, { waitUntil: 'load', timeout: 45000 });
    st = r ? r.status() : 0;
    if (r) { const h = r.headers(); csp = h['content-security-policy'] ? 'bloqueo' : (h['content-security-policy-report-only'] ? 'reporte' : ''); }
  } catch (e) { st = 'timeout'; reg.actual.errores.push(String(e).slice(0, 200)); }
  const ms = Date.now() - t0;
  await pg.waitForLoadState('networkidle', { timeout: 6000 }).catch(() => {});
  await pg.waitForTimeout(500);
  const m = await metricas(pg).catch(e => ({ h1: 0, fuera: 0, fueraDe: [], titulo: String(e).slice(0, 60) }));
  await pg.screenshot({ path: path.join(OUT, 'capturas', `${nombre}_${vista}.png`) }).catch(() => {});
  const url = pg.url().replace(BASE, '');
  const redirigido = /^\/entrar/.test(url) && !/^\/entrar/.test(ruta);
  const fila = { nombre, ruta, vista, st, ms, url, redirigido, cspModo: csp, ...m, ...reg.actual };
  fila.fallas = evaluar(fila, esperado || 200);
  return fila;
}

async function flujoPago(pg, reg, vista, mob) {
  reg.actual = nuevoRegistro();
  const f = { nombre: 'flujo_pago', ruta: `/reservar/${CANCHA_FLUJO}`, vista, pasos: [], fallas: [] };
  try {
    await pg.goto(BASE + f.ruta, { waitUntil: 'load' });
    await pg.waitForSelector('#dias > *', { timeout: 10000 });
    await pg.click('#dias > *:nth-child(3)');
    await pg.waitForSelector('#slots button.slot:not([disabled])', { timeout: 10000 });
    f.pasos.push('día elegido');
    await pg.click('#slots button.slot:not([disabled])');
    f.pasos.push('turno elegido');
    const boton = mob ? '#btnPagarBarra' : '#btnPagar';
    await pg.waitForSelector(boton + ':not([disabled])', { timeout: 8000 });
    await pg.click(boton);
    await pg.waitForSelector('.pcg-dlg.open .pcg-rp, .pcg-dlg.open', { timeout: 15000 }).catch(() => {});
    await pg.waitForTimeout(700);   // la hoja inferior termina de subir
    const resumen = await pg.evaluate(() => {
      const d = document.querySelector('.pcg-rp') || document.querySelector('.pcg-dlg');
      return d && d.offsetParent !== null ? d.innerText.replace(/\s+/g, ' ').slice(0, 300) : '';
    });
    await pg.screenshot({ path: path.join(OUT, 'capturas', `flujo_resumen_${vista}.png`) }).catch(() => {});
    if (!/Resumen|Total/i.test(resumen)) f.fallas.push('no apareció el "Resumen de tu pago"');
    else f.pasos.push('resumen de pago visible');
    f.resumen = resumen;
    // No se paga: "Volver" suelta el apartado.
    const no = await pg.$('#pcgDlgNo');
    if (no) { await no.click(); await pg.waitForTimeout(1200); f.pasos.push('volver (apartado liberado)'); }
  } catch (e) { f.fallas.push('flujo: ' + String(e).split('\n')[0].slice(0, 200)); }
  Object.assign(f, reg.actual);
  if (f.errores.length) f.fallas.push(`JS: ${f.errores[0]}`);
  if (f.consola.length) f.fallas.push(`consola: ${f.consola[0]}`);
  if (f.dialogos.length) f.fallas.push(`diálogo del navegador: ${f.dialogos[0]}`);
  if (f.csp.length) f.fallas.push(`CSP: ${f.csp[0].directiva} ${f.csp[0].bloqueado}`);
  return f;
}

(async () => {
  const b = await chromium.launch(process.env.PW_CHROMIUM ? { executablePath: process.env.PW_CHROMIUM } : {});
  const filas = [];
  const t0 = Date.now();
  for (const [vista, vp, mob] of VISTAS) {
    for (const quien of ['anon', 'jugador', 'dueno']) {
      const rutas = RUTAS.filter(r => r[2] === quien);
      if (!rutas.length) continue;
      if (quien !== 'anon' && !CUENTAS[quien]) { console.log(`(sin cuenta ${quien}: se saltan ${rutas.length} rutas)`); continue; }
      const { ctx, pg, reg } = await abrirContexto(b, vp, mob, quien);
      for (const [nombre, ruta, , esperado] of rutas) filas.push(await visitar(pg, reg, nombre, ruta, vista, esperado));
      // Chat real: el primer hilo de la bandeja (la clave va cifrada, no se puede escribir a mano).
      if ((quien === 'jugador' || quien === 'dueno') && (!SOLO || SOLO.test('chat'))) {
        await pg.goto(BASE + '/mensajes', { waitUntil: 'load' });
        const href = await pg.evaluate(() => {
          const a = [...document.querySelectorAll('a[href^="/mensajes/"]')].map(x => x.getAttribute('href'))
            .find(h => !/\/mensajes\/(nuevo|grupo)/.test(h));
          return a || '';
        });
        if (href) filas.push(await visitar(pg, reg, `chat_${quien}`, href, vista));
        else filas.push({ nombre: `chat_${quien}`, ruta: '/mensajes/…', vista, st: '-', fallas: ['la bandeja no tiene ningún chat (¿semilla?)'],
          errores: [], consola: [], dialogos: [], csp: [], http: [] });
      }
      if (quien === 'jugador' && (!SOLO || SOLO.test('flujo'))) filas.push(await flujoPago(pg, reg, vista, mob));
      await ctx.close();
    }
  }
  await b.close();

  const malas = filas.filter(f => f.fallas.length);
  const csp = {};
  for (const f of filas) for (const v of f.csp || []) {
    const k = `${v.directiva} ${v.bloqueado || '(inline) ' + v.muestra}`;
    (csp[k] = csp[k] || new Set()).add(f.nombre);
  }
  const seg = Math.round((Date.now() - t0) / 1000);
  const modos = [...new Set(filas.map(f => f.cspModo).filter(Boolean))].join('/') || '—';
  const resumen = { base: BASE, csp_modo: modos, pantallas: filas.length, fallas: malas.length, segundos: seg,
    csp: Object.fromEntries(Object.entries(csp).map(([k, v]) => [k, [...v]])) };
  fs.writeFileSync(path.join(OUT, 'reporte.json'), JSON.stringify({ resumen, filas }, null, 1));

  const md = [`# Barrido web · ${filas.length} pantallas · ${malas.length} con fallas · ${seg} s`, '', `Servidor: ${BASE} · CSP en modo ${modos}`, '',
    '| Pantalla | Vista | HTTP | ms | h1 | Fallas |', '|---|---|---|---|---|---|',
    ...filas.map(f => `| ${f.nombre} | ${f.vista} | ${f.st} | ${f.ms ?? ''} | ${f.h1 ?? ''} | ${f.fallas.length ? '❌ ' + f.fallas.join(' · ').replace(/\|/g, '/') : '✅'} |`)];
  if (Object.keys(csp).length) md.push('', '## Violaciones de CSP', '', ...Object.entries(csp).map(([k, v]) => `- \`${k}\` en ${[...v].join(', ')}`));
  fs.writeFileSync(path.join(OUT, 'reporte.md'), md.join('\n') + '\n');
  if (process.env.GITHUB_STEP_SUMMARY) fs.appendFileSync(process.env.GITHUB_STEP_SUMMARY, md.join('\n') + '\n');

  const pad = (s, n) => String(s ?? '').padEnd(n).slice(0, n);
  console.log(`${pad('pantalla', 22)} ${pad('vista', 4)} ${pad('http', 7)} ${pad('ms', 6)} resultado`);
  for (const f of filas) console.log(`${pad(f.nombre, 22)} ${pad(f.vista, 4)} ${pad(f.st, 7)} ${pad(f.ms, 6)} ${f.fallas.length ? 'FALLA ' + f.fallas.join(' · ') : 'ok'}`);
  if (Object.keys(csp).length) { console.log('\nCSP:'); for (const [k, v] of Object.entries(csp)) console.log(`  ${k}  ←  ${[...v].join(', ')}`); }
  console.log(`\n${filas.length} pantallas, ${malas.length} con fallas, ${seg} s. Reporte: ${path.join(OUT, 'reporte.md')}`);
  process.exit(malas.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
