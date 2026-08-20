"""Página PÚBLICA de un campeonato — servida por el BACKEND (Railway), ruta
`GET /c/{campeonato_id}`. Reemplaza a la Edge Function `campeonato-web` de
Supabase: el deploy de la función era manual y su versión desplegada devolvía
el HTML como texto plano (el navegador mostraba el código fuente). Aquí el
Content-Type lo pone FastAPI (`HTMLResponse`, text/html; charset=utf-8) y el
redeploy es automático con cada push.

Los datos del campeonato viven en Supabase (`pichangol_campeonatos.data`):
se leen por REST con la anon key (pública, la misma que lleva el APK).
Requiere en Railway las envs `SUPABASE_URL` y `SUPABASE_ANON_KEY`.
Todo fail-safe: sin envs o sin red → página de aviso, nunca un stacktrace.
"""

from __future__ import annotations

import html
import json
import urllib.parse
import urllib.request

import urllib.error

import config

# Paleta del logo nuevo (la misma del APK).
_ESMERALDA = "#0E8F67"
_NAVY = "#0F1B2D"
_RELEASE = "https://github.com/dcalagua/canchas-app-lima/releases/tag/v0.1.0"


def _esc(s) -> str:
    return html.escape(str(s if s is not None else ""), quote=True)


def obtener_campeonato(campeonato_id: str) -> dict | None:
    """Lee el campeonato de Supabase (columna `data`). None = no existe /
    eliminado / sin configuración. Lanza sólo errores de red (los maneja la
    ruta)."""
    if not config.SUPABASE_URL or not config.SUPABASE_ANON_KEY:
        raise RuntimeError("supabase_sin_configurar")
    base = config.SUPABASE_URL.strip().strip('"').strip("'").rstrip("/")
    # Tolerante: si pegaron el host pelado (sin https://), se lo ponemos.
    if not base.startswith("http"):
        base = f"https://{base}"
    if "." not in base.split("//", 1)[-1]:
        raise RuntimeError("supabase_url_invalida")
    q = urllib.parse.quote(campeonato_id, safe="")
    url = (f"{base}/rest/v1/pichangol_campeonatos"
           f"?id=eq.{q}&select=data,eliminado")
    req = urllib.request.Request(url, headers={
        "apikey": config.SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {config.SUPABASE_ANON_KEY}",
    })
    with urllib.request.urlopen(req, timeout=10) as resp:
        rows = json.loads(resp.read().decode("utf-8"))
    fila = rows[0] if isinstance(rows, list) and rows else None
    if not fila or fila.get("eliminado") is True or not fila.get("data"):
        return None
    data = fila["data"]
    return data if isinstance(data, dict) else json.loads(data)


# ── Tabla de posiciones (formato liga), misma lógica que la app ──────────────
def _tabla(c: dict) -> list[dict]:
    filas: dict[str, dict] = {}
    for p in c.get("participantes") or []:
        filas[p.get("id")] = {"nombre": p.get("nombre", ""), "pj": 0, "g": 0,
                              "e": 0, "p": 0, "gf": 0, "gc": 0}
    for m in c.get("partidos") or []:
        if m.get("marcadorA") is None or m.get("marcadorB") is None:
            continue
        fa, fb = filas.get(m.get("aId")), filas.get(m.get("bId"))
        if not fa or not fb:
            continue
        a, b = m["marcadorA"], m["marcadorB"]
        fa["pj"] += 1; fb["pj"] += 1
        fa["gf"] += a; fa["gc"] += b
        fb["gf"] += b; fb["gc"] += a
        if a > b:
            fa["g"] += 1; fb["p"] += 1
        elif b > a:
            fb["g"] += 1; fa["p"] += 1
        else:
            fa["e"] += 1; fb["e"] += 1
    return sorted(
        filas.values(),
        key=lambda f: (-(f["g"] * 3 + f["e"]), -(f["gf"] - f["gc"]), -f["gf"]))


def _etiqueta_ronda(ronda: int, max_ronda: int) -> str:
    return {0: "Final", 1: "Semifinal", 2: "Cuartos de final",
            3: "Octavos de final"}.get(max_ronda - ronda, f"Ronda {ronda + 1}")


def _nombre_de(c: dict, pid) -> str:
    if not pid:
        return "—"
    for p in c.get("participantes") or []:
        if p.get("id") == pid:
            return p.get("nombre", "")
    return "Por definir"


def _render_llave(c: dict) -> str:
    partidos = c.get("partidos") or []
    rondas = sorted({p.get("ronda", 0) for p in partidos})
    max_r = rondas[-1] if rondas else 0
    out = ['<div class="scroll"><div class="llave">']
    for r in rondas:
        ps = sorted((p for p in partidos if p.get("ronda", 0) == r),
                    key=lambda p: p.get("idx", 0))
        out.append(f'<div class="col"><h3>{_esc(_etiqueta_ronda(r, max_r))}</h3>')
        for m in ps:
            jugado = m.get("marcadorA") is not None and m.get("marcadorB") is not None
            ga = jugado and m["marcadorA"] > m["marcadorB"]
            gb = jugado and m["marcadorB"] > m["marcadorA"]
            out.append(
                f'<div class="match">'
                f'<div class="side {"win" if ga else ""}">'
                f'<span>{_esc(_nombre_de(c, m.get("aId")))}</span>'
                f'<b>{m["marcadorA"] if jugado else ""}</b></div>'
                f'<div class="side {"win" if gb else ""}">'
                f'<span>{_esc(_nombre_de(c, m.get("bId")))}</span>'
                f'<b>{m["marcadorB"] if jugado else ""}</b></div>'
                f'</div>')
        out.append('</div>')
    out.append('</div></div>')
    return ''.join(out)


def _render_liga(c: dict) -> str:
    out = ['<div class="scroll"><table class="tabla"><thead><tr>'
           '<th>#</th><th class="l">Equipo</th><th>PJ</th><th>G</th><th>E</th>'
           '<th>P</th><th>GF</th><th>GC</th><th>Dif</th><th>Pts</th>'
           '</tr></thead><tbody>']
    for i, f in enumerate(_tabla(c)):
        out.append(
            f'<tr><td>{i + 1}</td><td class="l">{_esc(f["nombre"])}</td>'
            f'<td>{f["pj"]}</td><td>{f["g"]}</td><td>{f["e"]}</td>'
            f'<td>{f["p"]}</td><td>{f["gf"]}</td><td>{f["gc"]}</td>'
            f'<td>{f["gf"] - f["gc"]}</td>'
            f'<td class="pts">{f["g"] * 3 + f["e"]}</td></tr>')
    out.append('</tbody></table></div>')
    return ''.join(out)


def _intent_unirse(campeonato_id: str) -> str:
    """URL intent:// de Android: abre la APP en la ficha del campeonato si está
    instalada; si no, cae a la descarga (browser_fallback_url). Es el botón
    'Unirme en la app' — un solo tap para el que ya usa Pichangol, y el que no,
    queda obligado a descargarla."""
    fallback = urllib.parse.quote(_RELEASE, safe="")
    return (f"intent://c/{urllib.parse.quote(campeonato_id, safe='')}"
            f"#Intent;scheme=pichangol;package=pe.ebim.pichangol;"
            f"S.browser_fallback_url={fallback};end")


def html_campeonato(c: dict, campeonato_id: str = "",
                    og_image: str = "") -> str:
    """La página completa del campeonato (hero + fixture + participantes)."""
    deporte = _esc(c.get("deporte", ""))
    formato = "Liga (tabla)" if c.get("formato") == "liga" else "Eliminación (llave)"
    mapa = ""
    if c.get("sedeLat") is not None and c.get("sedeLng") is not None:
        mapa = (f'<a class="mapbtn" href="https://www.google.com/maps/search/'
                f'?api=1&query={c["sedeLat"]},{c["sedeLng"]}" target="_blank" '
                f'rel="noopener">📍 Cómo llegar</a>')
    partidos = c.get("partidos") or []
    if partidos:
        fixture = _render_liga(c) if c.get("formato") == "liga" else _render_llave(c)
    else:
        fixture = '<p class="vacio">El fixture aún no está publicado. Vuelve pronto.</p>'
    participantes = c.get("participantes") or []
    mon = str(c.get("moneda") or "").strip() or "S/"
    como = ("Ábrela y crea tu equipo (o únete con el código del capitán)."
            if c.get("deporte") == "futbol" else "Ábrela y toca “Inscribirme”.")
    inscripcion = ""
    if c.get("inscripcionAbierta") and not partidos:
        costo = c.get("costoInscripcion") or 0
        costo_txt = (f" · {_esc(mon)} {float(costo):.2f}" if costo and costo > 0
                     else " · gratis")
        intent = _intent_unirse(campeonato_id)
        inscripcion = (
            f'<div class="cta"><b>Inscripciones abiertas</b>{costo_txt}<br>'
            f'<span>{como}</span><br>'
            f'<a class="mapbtn" style="margin-top:10px" href="{intent}">'
            f'🎾 Unirme en la app</a><br>'
            f'<span style="font-size:12px">Si no tienes Pichangol, el botón '
            f'te lleva a descargarla.</span></div>')
    if not inscripcion:
        intent = _intent_unirse(campeonato_id)
        inscripcion = (
            f'<div class="cta"><b>Sigue el torneo en Pichangol</b><br>'
            f'<span>Resultados, llave y avisos en tu teléfono.</span><br>'
            f'<a class="mapbtn" style="margin-top:10px" href="{intent}">'
            f'🎾 Abrir en la app</a><br>'
            f'<span style="font-size:12px">Si no tienes Pichangol, el botón '
            f'te lleva a descargarla.</span></div>')
    # ── Publicidad: premios + auspiciador (espacio de marca) ──
    auspiciador = str(c.get("auspiciador") or "").strip()
    premios = [l.strip() for l in str(c.get("premios") or "").split("\n")
               if l.strip()]
    bloque_premios = ""
    if premios:
        items = "".join(f'<li>✅ {_esc(p)}</li>' for p in premios)
        bloque_premios = (f'<h2>🎁 Premios</h2>'
                          f'<ul class="premios">{items}</ul>')
    bloque_auspiciador = ""
    if auspiciador:
        bloque_auspiciador = (
            f'<div class="auspicio">🤝 Agradecimiento especial a '
            f'<b>{_esc(auspiciador)}</b>, nuestro auspiciador oficial.</div>')
    # Franja de LOGOS de auspiciadores (varias empresas pueden auspiciar).
    logos_ausp = [str(u) for u in (c.get("auspiciadoresLogos") or [])
                  if str(u).startswith("http")]
    if logos_ausp:
        tiles = "".join(
            f'<span class="ausplogo"><img src="{_esc(u)}" alt="auspiciador" '
            f'loading="lazy"></span>' for u in logos_ausp)
        bloque_auspiciador += (
            f'<h2>🤝 Auspician</h2><div class="ausps">{tiles}</div>')
    byline = (f'<div class="byline">by <b>{_esc(auspiciador)}</b></div>'
              if auspiciador else "")
    # Vista previa RICA en WhatsApp (og:tags): título, descripción y logo.
    og_titulo = f'🏆 {c.get("nombre", "Campeonato")}' + (
        f' by {auspiciador}' if auspiciador else '')
    og_desc = " · ".join(x for x in [
        deporte, formato,
        f'Inicio {c.get("fechas")}' if c.get("fechas") else "",
        "Inscripciones abiertas" if c.get("inscripcionAbierta") else "",
    ] if x)
    logo = og_image or str(c.get("logoUrl") or "").strip()
    og_img = (f'<meta property="og:image" content="{_esc(logo)}">'
              if logo.startswith("http") else "")
    cat = (f'<span class="cat">{_esc(c["categoria"])}</span><br>'
           if c.get("categoria") else "")
    fechas = f'📅 {_esc(c["fechas"])}<br>' if c.get("fechas") else ""
    sede = f'📍 {_esc(c["sede"])}' if c.get("sede") else ""
    filas_part = ''.join(
        f'<tr><td style="width:34px">{i + 1}</td><td class="l">{_esc(p.get("nombre", ""))}</td></tr>'
        for i, p in enumerate(participantes)
    ) or '<tr><td class="l vacio">Aún sin participantes</td></tr>'

    return f"""<!-- campeonato-web railway v1 --><!doctype html><html lang="es"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(c.get("nombre", "Campeonato"))} · Pichangol</title>
<meta property="og:title" content="{_esc(og_titulo)}">
<meta property="og:description" content="{_esc(og_desc)}">
<meta property="og:type" content="website">
{og_img}
<style>
  :root{{--acento:{_ESMERALDA};--noche:{_NAVY};}}
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#f4f7fa;color:#1c1c1c;padding:0 0 40px}}
  .hero{{background:linear-gradient(135deg,var(--acento),var(--noche));color:#fff;padding:28px 20px 22px;border-radius:0 0 22px 22px}}
  .hero .cat{{display:inline-block;background:rgba(255,255,255,.16);padding:3px 10px;border-radius:20px;font-size:12px;font-weight:700;margin-bottom:10px}}
  .hero h1{{font-size:26px;line-height:1.15;font-weight:800}}
  .hero .meta{{margin-top:8px;font-size:14px;opacity:.92;line-height:1.5}}
  .wrap{{max-width:760px;margin:0 auto;padding:18px 16px 0}}
  .mapbtn{{display:inline-block;margin-top:12px;background:#fff;color:var(--noche);padding:9px 16px;border-radius:12px;text-decoration:none;font-weight:800;font-size:14px}}
  .wrap .mapbtn{{background:var(--acento);color:#fff}}
  h2{{font-size:16px;font-weight:800;margin:22px 4px 10px}}
  .scroll{{overflow-x:auto;-webkit-overflow-scrolling:touch}}
  .tabla{{width:100%;border-collapse:collapse;background:#fff;border-radius:14px;overflow:hidden;font-size:13px;min-width:520px}}
  .tabla th,.tabla td{{padding:9px 6px;text-align:center;border-bottom:1px solid #e9eef4}}
  .tabla th{{background:#e9eef4;color:var(--noche);font-weight:800}}
  .tabla td.l,.tabla th.l{{text-align:left;font-weight:700}}
  .tabla .pts{{font-weight:800;color:var(--noche)}}
  .llave{{display:flex;gap:16px;padding:4px;min-width:min-content}}
  .col{{min-width:190px}}
  .col h3{{font-size:12px;text-transform:uppercase;letter-spacing:.5px;color:#627080;margin-bottom:10px}}
  .match{{background:#fff;border-radius:12px;margin-bottom:14px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,.06)}}
  .side{{display:flex;justify-content:space-between;align-items:center;padding:9px 12px;font-size:14px;border-bottom:1px solid #f0f3f7}}
  .side:last-child{{border-bottom:none}}
  .side b{{font-variant-numeric:tabular-nums;color:#8a94a0}}
  .side.win{{background:#e7f4ef}}
  .side.win span{{font-weight:800;color:var(--noche)}}
  .side.win b{{color:var(--noche)}}
  .cta{{background:#fff;border:1.5px solid var(--acento);border-radius:14px;padding:14px 16px;margin-top:16px;font-size:14px}}
  .cta span{{color:#627080;font-size:13px}}
  .vacio{{color:#627080;padding:16px 4px}}
  .byline{{margin-top:4px;font-size:14px;opacity:.95}}
  .premios{{list-style:none;background:#fff;border-radius:14px;padding:12px 16px;font-size:14px;line-height:2}}
  .auspicio{{background:#fff;border-left:4px solid {_ESMERALDA};border-radius:12px;padding:12px 14px;margin-top:12px;font-size:13.5px;color:#333}}
  .ausps{{display:flex;flex-wrap:wrap;gap:12px}}
  .ausplogo{{display:flex;align-items:center;justify-content:center;width:104px;height:76px;background:#fff;border-radius:14px;box-shadow:0 1px 4px rgba(0,0,0,.06);padding:8px}}
  .ausplogo img{{max-width:100%;max-height:100%;object-fit:contain}}
  .foot{{max-width:760px;margin:26px auto 0;padding:16px;text-align:center;color:#8a94a0;font-size:12px}}
  .foot a{{color:var(--noche);font-weight:700;text-decoration:none}}
</style></head><body>
  <div class="hero">
    {cat}
    <h1>🏆 {_esc(c.get("nombre", ""))}</h1>
    {byline}
    <div class="meta">
      {deporte} · {formato}<br>
      {fechas}
      {sede}
    </div>
    {mapa}
  </div>
  <div class="wrap">
    {inscripcion}
    {bloque_premios}
    {bloque_auspiciador}
    <h2>{"Tabla de posiciones" if c.get("formato") == "liga" else "Llave"}</h2>
    {fixture}
    <h2>Participantes ({len(participantes)})</h2>
    <div class="scroll"><table class="tabla" style="min-width:auto"><tbody>
      {filas_part}
    </tbody></table></div>
  </div>
  <div class="foot">
    Organizado con <b>Pichangol</b> · Reserva, juega, repite.<br>
    <a href="{_RELEASE}">Descargar la app</a>
  </div>
</body></html>"""


def html_simple(titulo: str, msg: str) -> str:
    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{_esc(titulo)}</title>
<style>body{{font-family:sans-serif;background:#f4f7fa;color:#333;display:flex;min-height:100vh;align-items:center;justify-content:center;text-align:center;padding:24px}}</style>
</head><body><div><h1 style="font-size:22px">{_esc(titulo)}</h1><p style="margin-top:8px;color:#777">{_esc(msg)}</p></div></body></html>"""
