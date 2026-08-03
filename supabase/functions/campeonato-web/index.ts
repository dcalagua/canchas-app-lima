// Edge Function: campeonato-web
// Página PÚBLICA de un campeonato (para compartir a quien NO tiene la app).
// Lee el campeonato de la tabla `pichangol_campeonatos` (columna `data` jsonb)
// y devuelve una página HTML self-contained con la llave o la tabla, sede + mapa
// y datos de inscripción. Sin secretos: usa la anon key que Supabase inyecta.
//
// Deploy (público, sin JWT):
//   supabase functions deploy campeonato-web --no-verify-jwt
// URL: https://<proyecto>.supabase.co/functions/v1/campeonato-web?id=<campeonatoId>

import { serve } from "https://deno.land/std@0.168.0/http/server.ts";

const SB_URL = Deno.env.get("SUPABASE_URL") ?? "";
const ANON = Deno.env.get("SUPABASE_ANON_KEY") ?? "";

const LIMA = "#AEEA94";
const BOSQUE = "#14463A";

function esc(s: unknown): string {
  return String(s ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

// Tabla de posiciones (formato liga), misma lógica que la app.
function tabla(c: any) {
  const filas: Record<string, any> = {};
  for (const p of c.participantes ?? []) {
    filas[p.id] = { nombre: p.nombre, pj: 0, g: 0, e: 0, p: 0, gf: 0, gc: 0 };
  }
  for (const m of c.partidos ?? []) {
    if (m.marcadorA == null || m.marcadorB == null || !m.aId || !m.bId) continue;
    const fa = filas[m.aId], fb = filas[m.bId];
    if (!fa || !fb) continue;
    fa.pj++; fb.pj++;
    fa.gf += m.marcadorA; fa.gc += m.marcadorB;
    fb.gf += m.marcadorB; fb.gc += m.marcadorA;
    if (m.marcadorA > m.marcadorB) { fa.g++; fb.p++; }
    else if (m.marcadorB > m.marcadorA) { fb.g++; fa.p++; }
    else { fa.e++; fb.e++; }
  }
  const arr = Object.values(filas) as any[];
  arr.sort((a, b) => {
    const pa = a.g * 3 + a.e, pb = b.g * 3 + b.e;
    if (pb !== pa) return pb - pa;
    const da = a.gf - a.gc, db = b.gf - b.gc;
    if (db !== da) return db - da;
    return b.gf - a.gf;
  });
  return arr;
}

// Etiqueta de la ronda de una llave según cuántas rondas faltan para la final.
function etiquetaRonda(ronda: number, maxRonda: number): string {
  const desdeElFinal = maxRonda - ronda; // 0 = final
  switch (desdeElFinal) {
    case 0: return "Final";
    case 1: return "Semifinal";
    case 2: return "Cuartos de final";
    case 3: return "Octavos de final";
    default: return `Ronda ${ronda + 1}`;
  }
}

function nombreDe(c: any, pid: string | null | undefined): string {
  if (!pid) return "—";
  for (const p of c.participantes ?? []) if (p.id === pid) return p.nombre;
  return "Por definir";
}

function renderLlave(c: any): string {
  const partidos = (c.partidos ?? []) as any[];
  const rondas = [...new Set(partidos.map((p) => p.ronda))].sort((a, b) => a - b);
  const maxR = rondas.length ? rondas[rondas.length - 1] : 0;
  let out = '<div class="scroll"><div class="llave">';
  for (const r of rondas) {
    const ps = partidos.filter((p) => p.ronda === r).sort((a, b) => a.idx - b.idx);
    out += `<div class="col"><h3>${esc(etiquetaRonda(r, maxR))}</h3>`;
    for (const m of ps) {
      const jugado = m.marcadorA != null && m.marcadorB != null;
      const gaA = jugado && m.marcadorA > m.marcadorB;
      const gaB = jugado && m.marcadorB > m.marcadorA;
      out += `<div class="match">
        <div class="side ${gaA ? "win" : ""}"><span>${esc(nombreDe(c, m.aId))}</span><b>${jugado ? m.marcadorA : ""}</b></div>
        <div class="side ${gaB ? "win" : ""}"><span>${esc(nombreDe(c, m.bId))}</span><b>${jugado ? m.marcadorB : ""}</b></div>
      </div>`;
    }
    out += `</div>`;
  }
  out += "</div></div>";
  return out;
}

function renderLiga(c: any): string {
  const filas = tabla(c);
  let out = `<div class="scroll"><table class="tabla">
    <thead><tr><th>#</th><th class="l">Equipo</th><th>PJ</th><th>G</th><th>E</th><th>P</th><th>GF</th><th>GC</th><th>Dif</th><th>Pts</th></tr></thead><tbody>`;
  filas.forEach((f, i) => {
    out += `<tr><td>${i + 1}</td><td class="l">${esc(f.nombre)}</td><td>${f.pj}</td><td>${f.g}</td><td>${f.e}</td><td>${f.p}</td><td>${f.gf}</td><td>${f.gc}</td><td>${f.gf - f.gc}</td><td class="pts">${f.g * 3 + f.e}</td></tr>`;
  });
  out += "</tbody></table></div>";
  return out;
}

function paginaHtml(c: any): string {
  const deporte = esc(c.deporte ?? "");
  const formato = c.formato === "liga" ? "Liga (tabla)" : "Eliminación (llave)";
  const mapa = (c.sedeLat != null && c.sedeLng != null)
    ? `<a class="mapbtn" href="https://www.google.com/maps/search/?api=1&query=${c.sedeLat},${c.sedeLng}" target="_blank" rel="noopener">📍 Cómo llegar</a>`
    : "";
  const fixture = (c.partidos && c.partidos.length)
    ? (c.formato === "liga" ? renderLiga(c) : renderLlave(c))
    : `<p class="vacio">El fixture aún no está publicado. Vuelve pronto.</p>`;
  const nPart = (c.participantes ?? []).length;
  // Moneda del campeonato (congelada por país: S/ · Bs · $). No hardcodear S/.
  const mon = (c.moneda && String(c.moneda).trim()) || "S/";
  const comoInscribe = c.deporte === "futbol"
    ? "Ábrela y crea tu equipo (o únete con el código del capitán)."
    : "Ábrela y toca “Inscribirme”.";
  const inscripcion = c.inscripcionAbierta && !c.partidos?.length
    ? `<div class="cta"><b>Inscripciones abiertas</b>${c.costoInscripcion > 0 ? ` · ${esc(mon)} ${Number(c.costoInscripcion).toFixed(2)}` : " · gratis"}<br><span>${comoInscribe}</span><br><a class="mapbtn" style="margin-top:10px" href="https://github.com/dcalagua/canchas-app-lima/releases/tag/v0.1.0">Descargar / abrir Pichangol</a></div>`
    : "";

  return `<!doctype html><html lang="es"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>${esc(c.nombre)} · Pichangol</title>
<style>
  :root{--lima:${LIMA};--bosque:${BOSQUE};}
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#f4f6f5;color:#1c1c1c;padding:0 0 40px}
  .hero{background:linear-gradient(135deg,#2b6f5e,var(--bosque));color:#fff;padding:28px 20px 22px;border-radius:0 0 22px 22px}
  .hero .cat{display:inline-block;background:rgba(255,255,255,.16);padding:3px 10px;border-radius:20px;font-size:12px;font-weight:700;margin-bottom:10px}
  .hero h1{font-size:26px;line-height:1.15;font-weight:800}
  .hero .meta{margin-top:8px;font-size:14px;opacity:.92;line-height:1.5}
  .wrap{max-width:760px;margin:0 auto;padding:18px 16px 0}
  .mapbtn{display:inline-block;margin-top:12px;background:var(--lima);color:var(--bosque);padding:9px 16px;border-radius:12px;text-decoration:none;font-weight:800;font-size:14px}
  h2{font-size:16px;font-weight:800;margin:22px 4px 10px}
  .scroll{overflow-x:auto;-webkit-overflow-scrolling:touch}
  .tabla{width:100%;border-collapse:collapse;background:#fff;border-radius:14px;overflow:hidden;font-size:13px;min-width:520px}
  .tabla th,.tabla td{padding:9px 6px;text-align:center;border-bottom:1px solid #eee}
  .tabla th{background:#eef3f1;color:var(--bosque);font-weight:800}
  .tabla td.l,.tabla th.l{text-align:left;font-weight:700}
  .tabla .pts{font-weight:800;color:var(--bosque)}
  .llave{display:flex;gap:16px;padding:4px;min-width:min-content}
  .col{min-width:190px}
  .col h3{font-size:12px;text-transform:uppercase;letter-spacing:.5px;color:#6b7770;margin-bottom:10px}
  .match{background:#fff;border-radius:12px;margin-bottom:14px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,.06)}
  .side{display:flex;justify-content:space-between;align-items:center;padding:9px 12px;font-size:14px;border-bottom:1px solid #f0f0f0}
  .side:last-child{border-bottom:none}
  .side b{font-variant-numeric:tabular-nums;color:#8a8a8a}
  .side.win{background:#f2fbec}
  .side.win span{font-weight:800;color:var(--bosque)}
  .side.win b{color:var(--bosque)}
  .cta{background:#fff;border:1.5px solid var(--lima);border-radius:14px;padding:14px 16px;margin-top:16px;font-size:14px}
  .cta span{color:#6b7770;font-size:13px}
  .vacio{color:#6b7770;padding:16px 4px}
  .foot{max-width:760px;margin:26px auto 0;padding:16px;text-align:center;color:#8a8a8a;font-size:12px}
  .foot a{color:var(--bosque);font-weight:700;text-decoration:none}
</style></head><body>
  <div class="hero">
    ${c.categoria ? `<span class="cat">${esc(c.categoria)}</span><br>` : ""}
    <h1>🏆 ${esc(c.nombre)}</h1>
    <div class="meta">
      ${esc(deporte)} · ${formato}<br>
      ${c.fechas ? `📅 ${esc(c.fechas)}<br>` : ""}
      ${c.sede ? `📍 ${esc(c.sede)}` : ""}
    </div>
    ${mapa}
  </div>
  <div class="wrap">
    ${inscripcion}
    <h2>${c.formato === "liga" ? "Tabla de posiciones" : "Llave"}</h2>
    ${fixture}
    <h2>Participantes (${nPart})</h2>
    <div class="scroll"><table class="tabla" style="min-width:auto"><tbody>
      ${(c.participantes ?? []).map((p: any, i: number) => `<tr><td style="width:34px">${i + 1}</td><td class="l">${esc(p.nombre)}</td></tr>`).join("") || `<tr><td class="l vacio">Aún sin participantes</td></tr>`}
    </tbody></table></div>
  </div>
  <div class="foot">
    Organizado con <b>Pichangol</b> · Reserva, juega, repite.<br>
    <a href="https://github.com/dcalagua/canchas-app-lima/releases/tag/v0.1.0">Descargar la app</a>
  </div>
</body></html>`;
}

function htmlSimple(titulo: string, msg: string): string {
  return `<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>${esc(titulo)}</title>
<style>body{font-family:sans-serif;background:#f4f6f5;color:#333;display:flex;min-height:100vh;align-items:center;justify-content:center;text-align:center;padding:24px}</style>
</head><body><div><h1 style="font-size:22px">${esc(titulo)}</h1><p style="margin-top:8px;color:#777">${esc(msg)}</p></div></body></html>`;
}

serve(async (req) => {
  const url = new URL(req.url);
  const id = url.searchParams.get("id") ?? "";
  const headers = { "Content-Type": "text/html; charset=utf-8" };

  if (!id) {
    return new Response(htmlSimple("Campeonato", "Falta el identificador."), {
      status: 400, headers,
    });
  }
  if (!SB_URL || !ANON) {
    return new Response(htmlSimple("Sin conexión", "Servidor no configurado."), {
      status: 500, headers,
    });
  }
  try {
    const r = await fetch(
      `${SB_URL}/rest/v1/pichangol_campeonatos?id=eq.${encodeURIComponent(id)}&select=data,eliminado`,
      { headers: { apikey: ANON, Authorization: `Bearer ${ANON}` } },
    );
    const rows = await r.json();
    const fila = Array.isArray(rows) ? rows[0] : null;
    if (!fila || fila.eliminado === true || !fila.data) {
      return new Response(
        htmlSimple("No encontrado", "Este campeonato no existe o fue eliminado."),
        { status: 404, headers },
      );
    }
    return new Response(paginaHtml(fila.data), { status: 200, headers });
  } catch (_e) {
    return new Response(
      htmlSimple("Error", "No se pudo cargar el campeonato. Intenta más tarde."),
      { status: 500, headers },
    );
  }
});
