"""Render de la LANDING pública de una academia/cancha (fulfillment del servicio
de marketing). Toma los datos que manda el APK y produce una página HTML real,
responsive, que el backend sirve en GET /l/{academia_id}.

No es una maqueta: la página se arma con los datos reales de la academia
(nombre, sede, descripción, tarifario, fotos, redes, ubicación) y queda con una
URL pública compartible.
"""

from __future__ import annotations

import html


def _e(v) -> str:
    return html.escape(str(v or "")).strip()


def _num(v) -> str:
    try:
        f = float(v)
        return str(int(f)) if f == int(f) else f"{f:.2f}"
    except (TypeError, ValueError):
        return "0"


def _wa_link(whatsapp: str, nombre: str) -> str:
    tel = "".join(c for c in str(whatsapp or "") if c.isdigit())
    if not tel:
        return ""
    msg = f"Hola {nombre}, quiero más información y reservar."
    from urllib.parse import quote
    return f"https://wa.me/{tel}?text={quote(msg)}"


def render_landing(d: dict) -> str:
    nombre = _e(d.get("nombre")) or "Academia"
    deporte = _e(d.get("deporte"))
    sede = _e(d.get("sede"))
    desc = _e(d.get("descripcion"))
    moneda = _e(d.get("moneda")) or "S/"
    recargo = float(d.get("recargo_invitado") or 0)
    instagram = _e(d.get("instagram"))
    fotos = [f for f in (d.get("fotos") or []) if isinstance(f, str) and f.startswith("http")]
    lat, lng = d.get("lat"), d.get("lng")
    wa = _wa_link(d.get("whatsapp", ""), nombre)

    ig_url = ""
    if instagram:
        h = instagram.lstrip("@")
        ig_url = instagram if instagram.startswith("http") else f"https://instagram.com/{h}"

    # --- Tarifario (programas con frecuencia + socio/invitado) ---------------
    prog_html = ""
    programas = d.get("programas") or []
    if programas:
        filas = ""
        # columnas = unión de frecuencias presentes (2..5), ordenadas
        frecs = sorted({int(p.get("frec")) for prog in programas
                        for p in (prog.get("precios") or []) if p.get("frec")})
        heads = "".join(f"<th>{f}×/sem</th>" for f in frecs)
        for prog in programas:
            precios = {int(p["frec"]): p for p in (prog.get("precios") or []) if p.get("frec")}
            celdas = ""
            for f in frecs:
                if f in precios:
                    socio = float(precios[f].get("socio") or 0)
                    inv = ""
                    if recargo > 0:
                        inv = f"<span class='inv'>Inv. {moneda} {_num(socio + recargo)}</span>"
                    celdas += (f"<td><span class='socio'>{moneda} {_num(socio)}</span>{inv}</td>")
                else:
                    celdas += "<td>—</td>"
            meta = " · ".join(x for x in [_e(prog.get('etapa')), _e(prog.get('duracion'))] if x)
            filas += (f"<tr><th><span class='prog'>{_e(prog.get('nombre'))}</span>"
                      f"<span class='meta'>{meta}</span></th>{celdas}</tr>")
        nota = ("<p class='tleyenda'>Tarifa socio del club · «Inv.» = invitado (no socio).</p>"
                if recargo > 0 else "")
        prog_html = f"""
        <section class="section" id="tarifas">
          <div class="wrap">
            <div class="tag">Tarifario</div>
            <h2 class="h2">Planes y precios</h2>
            <div class="tarifa-wrap"><table class="tarifa">
              <thead><tr><th>Programa</th>{heads}</tr></thead>
              <tbody>{filas}</tbody>
            </table></div>
            {nota}
          </div>
        </section>"""

    # --- Planes simples ------------------------------------------------------
    simples = d.get("planes") or []
    simples_html = ""
    if simples and not programas:
        cards = "".join(
            f"<div class='plan'><b>{_e(p.get('nombre'))}</b>"
            f"<span>{moneda} {_num(p.get('precio'))}{_e(p.get('sufijo'))}</span></div>"
            for p in simples)
        simples_html = f"""
        <section class="section" id="tarifas"><div class="wrap">
          <div class="tag">Planes</div><h2 class="h2">Precios</h2>
          <div class="planes">{cards}</div>
        </div></section>"""

    # --- Fotos ---------------------------------------------------------------
    fotos_html = ""
    if fotos:
        imgs = "".join(f"<figure><img src='{_e(u)}' loading='lazy' alt='{nombre}'></figure>"
                       for u in fotos[:6])
        fotos_html = f"""
        <section class="section" style="padding-top:0"><div class="wrap">
          <div class="galeria">{imgs}</div>
        </div></section>"""

    # --- Ubicación -----------------------------------------------------------
    ubic_html = ""
    if isinstance(lat, (int, float)) and isinstance(lng, (int, float)):
        maps = f"https://www.google.com/maps/search/?api=1&query={lat},{lng}"
        ubic_html = (f"<a class='btn btn-ghost' href='{maps}' target='_blank' "
                     f"rel='noopener'>📍 Cómo llegar</a>")

    ig_btn = (f"<a class='btn btn-ghost' href='{ig_url}' target='_blank' rel='noopener'>Instagram</a>"
              if ig_url else "")
    wa_btn = (f"<a class='btn btn-wa' href='{wa}' target='_blank' rel='noopener'>💬 Escríbenos por WhatsApp</a>"
              if wa else "")
    hero_photo = (f"<div class='hero-photo'><img src='{_e(fotos[0])}' alt='{nombre}'></div>"
                  if fotos else "")

    subt = " · ".join(x for x in [deporte.capitalize(), sede] if x)

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{nombre}{(' — ' + sede) if sede else ''}</title>
<meta name="description" content="{desc or nombre}">
<meta name="theme-color" content="#0F2E12">
<meta property="og:title" content="{nombre}">
<meta property="og:description" content="{desc or nombre}">
{f'<meta property="og:image" content="{_e(fotos[0])}">' if fotos else ''}
<meta property="og:type" content="website">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Anton&family=Outfit:wght@400;600;700;800&display=swap" rel="stylesheet">
<style>
:root{{--verde-osc:#0F2E12;--verde:#128C7E;--wa:#25D366;--crema:#FAF7F2;--ball:#CDDC39;--tinta:#1E1E1E;--gris:#6B6257}}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'Outfit',system-ui,sans-serif;color:var(--tinta);background:var(--crema);line-height:1.6}}
h1,h2,.h2{{font-family:'Anton',Impact,sans-serif;font-weight:400;line-height:1.05}}
img{{max-width:100%;display:block}}a{{color:inherit;text-decoration:none}}
.wrap{{max-width:1000px;margin:0 auto;padding:0 22px}}
.section{{padding:56px 0}}
.tag{{color:var(--verde);font-weight:800;text-transform:uppercase;letter-spacing:1px;font-size:12px}}
.h2{{font-size:clamp(26px,4vw,40px);color:var(--verde-osc);margin:6px 0 10px}}
.btn{{display:inline-flex;align-items:center;gap:8px;padding:13px 22px;border-radius:999px;font-weight:700;border:0;cursor:pointer;margin:4px}}
.btn-wa{{background:var(--wa);color:#0b3d1e}}
.btn-ghost{{background:transparent;color:#fff;border:2px solid rgba(255,255,255,.5)}}
.hero{{background:var(--verde-osc);color:#fff;text-align:center;padding:56px 0}}
.hero h1{{font-size:clamp(34px,6vw,64px);color:#fff}}
.hero .st{{color:var(--ball);font-weight:700;letter-spacing:2px;text-transform:uppercase;font-size:13px;margin-bottom:8px}}
.hero p{{color:#e7e3da;max-width:600px;margin:10px auto 22px}}
.hero-photo{{max-width:680px;margin:26px auto 0;border-radius:18px;overflow:hidden;box-shadow:0 16px 40px rgba(0,0,0,.4)}}
.hero-photo img{{width:100%;height:auto}}
.tarifa-wrap{{overflow-x:auto;border-radius:14px;box-shadow:0 8px 24px rgba(15,46,18,.08);margin-top:20px}}
table.tarifa{{width:100%;border-collapse:collapse;background:#fff;min-width:560px}}
table.tarifa th,table.tarifa td{{padding:13px 12px;text-align:center;border-bottom:1px solid #eee}}
table.tarifa thead th{{background:var(--verde-osc);color:var(--ball);font-family:'Anton'}}
table.tarifa tbody th{{text-align:left;background:#fafafa}}
.prog{{font-weight:800;color:var(--verde-osc);display:block}}
.meta{{display:block;color:var(--gris);font-size:12px;font-weight:500}}
.socio{{font-family:'Anton';color:var(--verde);font-size:19px}}
.inv{{display:block;color:var(--gris);font-size:12px}}
.tleyenda{{color:var(--gris);font-size:13px;margin-top:10px}}
.planes{{display:flex;flex-wrap:wrap;gap:12px;margin-top:16px}}
.plan{{background:#fff;border-radius:14px;padding:16px 18px;box-shadow:0 6px 18px rgba(15,46,18,.07)}}
.plan b{{display:block;color:var(--verde-osc)}}.plan span{{font-family:'Anton';color:var(--verde);font-size:20px}}
.galeria{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}}
.galeria img{{width:100%;height:200px;object-fit:cover;border-radius:14px}}
.cta{{background:var(--verde);color:#fff;text-align:center}}
.cta .h2{{color:#fff}}
footer{{background:var(--verde-osc);color:#cbd3c0;text-align:center;padding:22px;font-size:13px}}
@media(max-width:700px){{.galeria{{grid-template-columns:1fr 1fr}}}}
</style>
</head>
<body>
<header class="hero">
  <div class="wrap">
    {f'<div class="st">{subt}</div>' if subt else ''}
    <h1>{nombre}</h1>
    {f'<p>{desc}</p>' if desc else ''}
    <div>{wa_btn}{ig_btn}{ubic_html}</div>
    {hero_photo}
  </div>
</header>
{prog_html}{simples_html}{fotos_html}
<section class="section cta"><div class="wrap">
  <div class="tag" style="color:#dff">Inscripciones abiertas</div>
  <h2 class="h2">Reserva tu lugar</h2>
  <div>{wa_btn}{ig_btn}</div>
</div></section>
<footer>{nombre}{(' · ' + sede) if sede else ''} · Hecho con Pichangol</footer>
</body>
</html>"""
