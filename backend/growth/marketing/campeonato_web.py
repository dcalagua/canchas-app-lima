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
def _descarga() -> str:
    """A dónde va quien no tiene la app: Play en PRD, Release en dev/QAS
    (`config.APP_DOWNLOAD_URL`; función para que los tests lo cambien)."""
    return config.APP_DOWNLOAD_URL


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
        filas[p.get("id")] = {"id": p.get("id"), "nombre": p.get("nombre", ""), "pj": 0, "g": 0,
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


def _render_grupos(c: dict) -> str:
    """Formato grupos: tabla por grupo + la llave de la fase final (misma
    lógica que `web/campeonatos_logica`, que a su vez reusa `_tabla`)."""
    from web import campeonatos_logica as L  # import local: L importa `_tabla` de aquí
    out = []
    for letra in L.grupos_de(c):
        ms = [m for m in L.partidos_grupo(c) if m.get("grupo") == letra]
        ids = {m.get(k) for m in ms for k in ("aId", "bId")}
        out.append(f'<h3 style="margin:14px 0 6px">Grupo {letra}</h3>')
        out.append(_render_liga({"participantes": c.get("participantes") or [], "partidos": ms}, solo_ids=ids))
    out.append('<h3 style="margin:18px 0 6px">Fase final</h3>')
    if not L.grupos_completos(c):
        out.append('<p class="vacio">Los cruces se definen cuando termine la fase de grupos (clasifican los 2 primeros de cada grupo).</p>')
    out.append(_render_llave({"participantes": c.get("participantes") or [], "partidos": L.partidos_llave(c)}))
    return ''.join(out)


def _render_liga(c: dict, solo_ids=None) -> str:
    out = ['<div class="scroll"><table class="tabla"><thead><tr>'
           '<th>#</th><th class="l">Equipo</th><th>PJ</th><th>G</th><th>E</th>'
           '<th>P</th><th>GF</th><th>GC</th><th>Dif</th><th>Pts</th>'
           '</tr></thead><tbody>']
    filas = _tabla(c) if solo_ids is None else [f for f in _tabla(c) if f.get("id") in solo_ids]
    for i, f in enumerate(filas):
        out.append(
            f'<tr><td>{i + 1}</td><td class="l">{_esc(f["nombre"])}</td>'
            f'<td>{f["pj"]}</td><td>{f["g"]}</td><td>{f["e"]}</td>'
            f'<td>{f["p"]}</td><td>{f["gf"]}</td><td>{f["gc"]}</td>'
            f'<td>{f["gf"] - f["gc"]}</td>'
            f'<td class="pts">{f["g"] * 3 + f["e"]}</td></tr>')
    out.append('</tbody></table></div>')
    return ''.join(out)


def _podio(c: dict) -> tuple[str | None, str | None]:
    """(campeón, subcampeón) si el torneo TERMINÓ; (None, None) si sigue.
    Liga → 1º y 2º de la tabla con todo jugado (o torneo cerrado);
    eliminación → ganador y perdedor de la final."""
    partidos = c.get("partidos") or []
    if not partidos:
        return (None, None)
    if c.get("formato") == "liga":
        completo = all(m.get("marcadorA") is not None
                       and m.get("marcadorB") is not None for m in partidos)
        if not completo and not c.get("cerrado"):
            return (None, None)
        t = _tabla(c)
        camp = t[0]["nombre"] if t else None
        sub = t[1]["nombre"] if len(t) > 1 else None
        return (camp, sub)
    if c.get("formato") == "grupos":
        partidos = [p for p in partidos if p.get("fase") == "llave"]
        if not partidos:
            return (None, None)
    max_r = max(p.get("ronda", 0) for p in partidos)
    fin = [p for p in partidos if p.get("ronda", 0) == max_r]
    if len(fin) != 1:
        return (None, None)
    f = fin[0]
    a, b = f.get("marcadorA"), f.get("marcadorB")
    if a is None or b is None or a == b:
        return (None, None)
    gid, pid = (f.get("aId"), f.get("bId")) if a > b else (f.get("bId"),
                                                           f.get("aId"))
    return (_nombre_de(c, gid), _nombre_de(c, pid))


_EMOJI = {"tenis": "🎾", "futbol": "⚽", "padel": "🏸", "pickleball": "🏓",
          "voley": "🏐", "basquet": "🏀", "natacion": "🏊"}


def _fmt_tiempo(centesimas: int) -> str:
    m, r = divmod(int(centesimas), 6000)
    s, cc = divmod(r, 100)
    return f"{m}:{s:02d}.{cc:02d}" if m else f"{s}.{cc:02d} s"


def _render_tiempos(c: dict) -> str:
    """NATACIÓN (formato por tiempos): ranking por PRUEBA (50m Libre, etc.),
    ordenado por tiempo; DSQ al final. Es el 'fixture' de estos torneos."""
    pruebas = c.get("pruebas") or []
    if not pruebas:
        return ('<p class="vacio">Las pruebas aún no están publicadas. '
                'Vuelve pronto.</p>')
    out = []
    for p in pruebas:
        marcas = p.get("marcas") or []
        reg = sorted(
            (m for m in marcas
             if not m.get("dsq") and (m.get("centesimas") or 0) > 0),
            key=lambda m: m.get("centesimas") or 0)
        dsq = [m for m in marcas if m.get("dsq")]
        filas = []
        for i, m in enumerate(reg):
            medalla = {0: " 🥇", 1: " 🥈", 2: " 🥉"}.get(i, "")
            filas.append(
                f'<tr><td style="width:34px">{i + 1}</td>'
                f'<td class="l">{_esc(_nombre_de(c, m.get("participanteId")))}'
                f'{medalla}</td>'
                f'<td style="width:110px">{_fmt_tiempo(m.get("centesimas") or 0)}'
                f'</td></tr>')
        for m in dsq:
            filas.append(
                f'<tr><td>—</td>'
                f'<td class="l">{_esc(_nombre_de(c, m.get("participanteId")))}'
                f'</td><td>DSQ</td></tr>')
        cuerpo = ''.join(filas) or             '<tr><td class="l vacio">Sin tiempos registrados aún</td></tr>'
        out.append(
            f'<h3 class="prueba">🏊 {_esc(p.get("nombre") or "Prueba")}</h3>'
            f'<div class="scroll"><table class="tabla" style="min-width:auto">'
            f'<tbody>{cuerpo}</tbody></table></div>')
    return ''.join(out)


def _intent_unirse(campeonato_id: str, equipo: str = "") -> str:
    """URL intent:// de Android: abre la APP en la ficha del campeonato si está
    instalada; si no, cae a la descarga (browser_fallback_url). Es el botón
    'Unirme en la app' — un solo tap para el que ya usa Pichangol, y el que no,
    queda obligado a descargarla. Con `equipo` (código del equipo, fútbol) la
    app abre directo "Unirme al equipo X" sin pedir el código."""
    fallback = urllib.parse.quote(_descarga(), safe="")
    q = (f"?equipo={urllib.parse.quote(equipo.strip().upper(), safe='')}"
         if equipo and equipo.strip() else "")
    return (f"intent://c/{urllib.parse.quote(campeonato_id, safe='')}{q}"
            f"#Intent;scheme=pichangol;package=pe.ebim.pichangol;"
            f"S.browser_fallback_url={fallback};end")


def equipo_por_codigo(c: dict, codigo: str) -> dict | None:
    """El participante-equipo cuyo `codigo` (6 letras del capitán) coincide."""
    cod = (codigo or "").strip().upper()
    if not cod:
        return None
    for p in c.get("participantes") or []:
        if str(p.get("codigo") or "").strip().upper() == cod:
            return p
    return None


def html_campeonato(c: dict, campeonato_id: str = "",
                    og_image: str = "", equipo: str = "") -> str:
    """La página completa del campeonato (hero + fixture + participantes).
    `equipo` = código de equipo que viajó en el enlace (`/c/{id}?equipo=`):
    el CTA pasa a ser "Unirme al equipo X" y la app se abre directo ahí."""
    deporte = _esc(c.get("deporte", ""))
    emo = _EMOJI.get(str(c.get("deporte") or ""), "🏆")
    es_tiempos = c.get("formato") == "tiempos"
    formato = ("Liga (tabla)" if c.get("formato") == "liga"
               else "Por tiempos (pruebas)" if es_tiempos
               else "Grupos + eliminatoria" if c.get("formato") == "grupos"
               else "Eliminación (llave)")
    mapa = ""
    if c.get("sedeLat") is not None and c.get("sedeLng") is not None:
        mapa = (f'<a class="mapbtn" href="https://www.google.com/maps/search/'
                f'?api=1&query={c["sedeLat"]},{c["sedeLng"]}" target="_blank" '
                f'rel="noopener">📍 Cómo llegar</a>')
    partidos = c.get("partidos") or []
    if es_tiempos:
        fixture = _render_tiempos(c)
    elif partidos:
        fixture = (_render_liga(c) if c.get("formato") == "liga"
                   else _render_grupos(c) if c.get("formato") == "grupos" else _render_llave(c))
    else:
        fixture = '<p class="vacio">El fixture aún no está publicado. Vuelve pronto.</p>' 
    participantes = c.get("participantes") or []
    mon = str(c.get("moneda") or "").strip() or "S/"
    como = ("Ábrela y crea tu equipo (o únete con el código del capitán)."
            if c.get("deporte") == "futbol" else "Ábrela y toca “Inscribirme”.")
    inscripcion = ""
    from web import campeonatos_logica as _L
    eq = equipo_por_codigo(c, equipo) if c.get("deporte") == "futbol" else None
    # El enlace del CAPITÁN sigue valiendo con el fixture ya publicado: un
    # suplente se une al plantel mientras la inscripción siga abierta
    # (`plantel_abierto`, espejo del app). Crear equipos / inscribirse solo,
    # en cambio, se cierra al generar el fixture.
    if (c.get("inscripcionAbierta") and not partidos) or (eq is not None and _L.plantel_abierto(c)):
        costo = c.get("costoInscripcion") or 0
        costo_txt = (f" · {_esc(mon)} {float(costo):.2f}" if costo and costo > 0
                     else " · gratis")
        if costo and costo > 0 and c.get("deporte") == "futbol":
            # Cuota POR EQUIPO repartida entre el plantel (pagos/pozos.py).
            cj = _L.cuota_jugador_centimos(c)
            cupo = _L.cupo_reparto(c)
            costo_txt = (f" · {_esc(mon)} {float(costo):.2f} por equipo"
                         + (f" · cada jugador pone {_esc(mon)} {_L.fmt_monto(cj)}" if cupo > 0 else ""))
        if eq is not None:
            # Enlace del CAPITÁN: un solo toque para entrar a SU equipo.
            intent = _intent_unirse(campeonato_id, str(eq.get("codigo") or ""))
            plantel = len(eq.get("roster") or [])
            cap = str(eq.get("capitanEmail") or "").strip()
            cap_txt = (f' · capitán {_esc(cap.split("@")[0])}' if cap else "")
            en_juego = (" El fixture ya está publicado: entras como parte del "
                        "plantel." if partidos else "")
            inscripcion = (
                f'<div class="cta"><b>Te invitaron al equipo '
                f'«{_esc(str(eq.get("nombre") or ""))}»</b>{costo_txt}<br>'
                f'<span>{plantel} jugador{"es" if plantel != 1 else ""} en el '
                f'plantel{cap_txt}. Al tocar, Pichangol te une con tu cuenta; '
                f'sin escribir códigos.{en_juego}</span><br>'
                f'<a class="mapbtn" style="margin-top:10px" href="{intent}">'
                f'{emo} Unirme al equipo en la app</a><br>'
                f'<span style="font-size:12px">Si no tienes Pichangol, el '
                f'botón te lleva a descargarla; al volver a abrir este enlace '
                f'quedas en tu equipo.</span></div>')
        else:
            intent = _intent_unirse(campeonato_id)
            aviso = ""
            if equipo and equipo.strip() and c.get("deporte") == "futbol":
                aviso = ('<br><span style="font-size:12px;color:#B25E0A">El '
                         'código de equipo del enlace ya no es válido: pídele '
                         'a tu capitán el enlace actualizado.</span>')
            inscripcion = (
                f'<div class="cta"><b>Inscripciones abiertas</b>{costo_txt}<br>'
                f'<span>{como}</span>{aviso}<br>'
                f'<a class="mapbtn" style="margin-top:10px" href="{intent}">'
                f'{emo} Unirme en la app</a><br>' 
                f'<span style="font-size:12px">Si no tienes Pichangol, el botón '
                f'te lleva a descargarla.</span></div>')
    if not inscripcion:
        intent = _intent_unirse(campeonato_id)
        inscripcion = (
            f'<div class="cta"><b>Sigue el torneo en Pichangol</b><br>'
            f'<span>Resultados, llave y avisos en tu teléfono.</span><br>'
            f'<a class="mapbtn" style="margin-top:10px" href="{intent}">'
            f'{emo} Abrir en la app</a><br>' 
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
    # Torneo TERMINADO: podio (campeón / subcampeón) arriba del fixture.
    campeon, subcampeon = _podio(c)
    bloque_podio = ""
    if campeon:
        sub_html = (f' &nbsp;·&nbsp; 🥈 {_esc(subcampeon)}'
                    if subcampeon else "")
        bloque_podio = (
            f'<div class="podio">🏁 <b>Torneo finalizado</b><br>'
            f'<span class="oro">🥇 {_esc(campeon)}</span>{sub_html}</div>')
    # GALERÍA de fotos ("así se vivió") — memoria de campeonatos pasados.
    fotos = [str(u) for u in (c.get("fotos") or [])
             if str(u).startswith("http")]
    bloque_galeria = ""
    if fotos:
        imgs = "".join(
            f'<a href="{_esc(u)}" target="_blank" rel="noopener">'
            f'<img src="{_esc(u)}" alt="foto del torneo" loading="lazy">'
            f'</a>' for u in fotos)
        bloque_galeria = (f'<h2>📸 Así se vivió</h2>'
                          f'<div class="galeria">{imgs}</div>')
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
  .podio{{background:linear-gradient(135deg,var(--noche),#0B7A58);color:#fff;border-radius:14px;padding:14px 16px;margin-top:16px;font-size:14px;line-height:1.9}}
  .podio .oro{{font-size:18px;font-weight:800}}
  .prueba{{font-size:14px;font-weight:800;margin:16px 4px 8px}}
  .galeria{{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:10px}}
  .galeria img{{width:100%;height:130px;object-fit:cover;border-radius:12px;display:block}}
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
    {bloque_podio}
    {inscripcion}
    {bloque_premios}
    {bloque_auspiciador}
    <h2>{"Tabla de posiciones" if c.get("formato") == "liga" else "Pruebas y tiempos" if es_tiempos else "Grupos y fase final" if c.get("formato") == "grupos" else "Llave"}</h2>
    {fixture}
    {bloque_galeria}
    <h2>Participantes ({len(participantes)})</h2>
    <div class="scroll"><table class="tabla" style="min-width:auto"><tbody>
      {filas_part}
    </tbody></table></div>
  </div>
  <div class="foot">
    Organizado con <b>Pichangol</b> · Reserva, juega, repite.<br>
    <a href="{_descarga()}">Descargar la app</a>
  </div>
</body></html>"""


def html_simple(titulo: str, msg: str) -> str:
    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{_esc(titulo)}</title>
<style>body{{font-family:sans-serif;background:#f4f7fa;color:#333;display:flex;min-height:100vh;align-items:center;justify-content:center;text-align:center;padding:24px}}</style>
</head><body><div><h1 style="font-size:22px">{_esc(titulo)}</h1><p style="margin-top:8px;color:#777">{_esc(msg)}</p></div></body></html>"""
