"""CARTA DIGITAL de la bodega de un local — `GET /b/{carta_id}` (pública).

El dueño administra su bodega en el APK (Mi bodega, función Pro) e imprime el
QR (`GET /b/{carta_id}/qr.png`) para pegarlo junto a su Yape: los clientes ven
la carta con precios siempre al día y PAGAN CON EL DUEÑO como siempre (la
plata no pasa por Pichangol). Los productos viven en Supabase
(`pichangol_bodega_productos`); se leen por REST con la anon key, filtrando
por `carta_id` (derivado del correo del dueño SIN exponerlo). Fail-safe.
"""

from __future__ import annotations

import html
import json
import urllib.error
import urllib.parse
import urllib.request

import config

_ESMERALDA = "#0E8F67"
_NAVY = "#0F1B2D"

_EMOJI_CAT = {
    "Bebidas": "🥤", "Cervezas": "🍺", "Deportivo": "🎾",
    "Snacks": "🍿", "Otros": "🛒",
}

# "Imagen" automática del producto: emoji según QUÉ es (no la marca) — igual
# en los 3 países (Pilsen/Paceña/Pilsener → 🍺). Espejo del APK
# (emojiProductoBodega en lib/models/bodega.dart).
_EMOJI_KEYS = [
    ("agua", "💧"), ("jugo", "🧃"), ("frugos", "🧃"), ("cifrut", "🧃"),
    ("gatorade", "⚡"), ("powerade", "⚡"), ("sporade", "⚡"),
    ("volt", "⚡"), ("profit", "⚡"),
    ("paleta", "🏓"), ("pelota", "🎾"),
    ("papita", "🍟"), ("lays", "🍟"), ("dorito", "🍟"), ("chifle", "🍟"),
    ("chizito", "🍟"), ("kchito", "🍟"),
    ("galleta", "🍪"), ("chocolate", "🍫"), ("sublime", "🍫"),
    ("maní", "🥜"), ("mani", "🥜"), ("sandwich", "🥪"),
    ("hielo", "🧊"), ("cigarro", "🚬"), ("gorra", "🧢"),
]


def _emoji_producto(nombre: str, categoria: str) -> str:
    n = (nombre or "").lower()
    for clave, emo in _EMOJI_KEYS:
        if clave in n:
            return emo
    return _EMOJI_CAT.get(categoria, "🛒")


# TIPO de packshot IA (imagen genérica sin marca, `/bodega/packshot/{tipo}`).
# Espejo del APK (packshotTipoDe en lib/models/bodega.dart).
_PACKSHOT_KEYS = [
    ("agua", "agua"), ("jugo", "jugo"), ("frugos", "jugo"),
    ("cifrut", "jugo"),
    ("gatorade", "rehidratante"), ("powerade", "rehidratante"),
    ("sporade", "rehidratante"), ("volt", "rehidratante"),
    ("profit", "rehidratante"),
    ("paleta", "paleta"), ("pelota", "pelotas"),
    ("papita", "papitas"), ("lays", "papitas"), ("dorito", "papitas"),
    ("chifle", "papitas"), ("chizito", "papitas"), ("kchito", "papitas"),
    ("galleta", "galletas"), ("chocolate", "chocolate"),
    ("sublime", "chocolate"),
    ("maní", "mani"), ("mani", "mani"), ("sandwich", "sandwich"),
    ("sánguche", "sandwich"),
    ("hielo", "hielo"), ("gorra", "gorra"), ("toalla", "toalla"),
]

_PACKSHOT_CAT = {
    "Cervezas": "cerveza", "Bebidas": "gaseosa", "Snacks": "papitas",
    "Deportivo": "pelotas",
}


def _packshot_tipo(nombre: str, categoria: str) -> str:
    n = (nombre or "").lower()
    if "cerveza" in n:
        return "cerveza"
    for clave, tipo in _PACKSHOT_KEYS:
        if clave in n:
            return tipo
    return _PACKSHOT_CAT.get(categoria, "generico")


def _esc(s) -> str:
    return html.escape(str(s if s is not None else ""), quote=True)


def obtener_productos(carta_id: str) -> list[dict] | None:
    """Productos vigentes de la carta. None = sin configuración de Supabase.
    Lanza errores de red (los maneja la ruta)."""
    if not config.SUPABASE_URL or not config.SUPABASE_ANON_KEY:
        return None
    base = config.SUPABASE_URL.strip().strip('"').strip("'").rstrip("/")
    if not base.startswith("http"):
        base = f"https://{base}"
    q = urllib.parse.quote(carta_id, safe="")

    def _leer(columnas: str) -> list[dict]:
        url = (f"{base}/rest/v1/pichangol_bodega_productos"
               f"?carta_id=eq.{q}&eliminado=eq.false"
               f"&select={columnas}&order=categoria,nombre")
        req = urllib.request.Request(url, headers={
            "apikey": config.SUPABASE_ANON_KEY,
            "Authorization": f"Bearer {config.SUPABASE_ANON_KEY}",
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            rows = json.loads(resp.read().decode("utf-8"))
        return rows if isinstance(rows, list) else []

    try:
        # Con moneda (país del local: S/, Bs, $).
        return _leer("nombre,categoria,precio,stock,foto_url,moneda")
    except urllib.error.HTTPError:
        # La columna moneda aún no existe (falta supabase_bodega_moneda.sql).
        return _leer("nombre,categoria,precio,stock,foto_url")


def html_carta(productos: list[dict], con_packshots: bool = False) -> str:
    """La carta pública: productos agrupados por categoría, con precio y
    "Agotado" cuando no hay stock. [con_packshots] (hay proveedor IA): los
    productos SIN foto real muestran el packshot genérico por tipo, con el
    emoji debajo por si el packshot no carga."""
    por_cat: dict[str, list[dict]] = {}
    for p in productos:
        por_cat.setdefault(str(p.get("categoria") or "Otros"), []).append(p)

    secciones = []
    for cat, items in por_cat.items():
        emoji = _EMOJI_CAT.get(cat, "🛒")
        filas = []
        for p in items:
            agotado = (p.get("stock") or 0) <= 0
            foto = str(p.get("foto_url") or "").strip()
            emo_prod = _emoji_producto(
                str(p.get("nombre") or ""), cat)
            if foto.startswith("http"):
                img = f'<img src="{_esc(foto)}" alt="" loading="lazy">'
            elif con_packshots:
                tipo = _packshot_tipo(str(p.get("nombre") or ""), cat)
                img = (f'<span class="ph">{emo_prod}'
                       f'<img src="/bodega/packshot/{tipo}" alt="" '
                       'loading="lazy" onerror="this.remove()"></span>')
            else:
                img = f'<span class="ph">{emo_prod}</span>'
            precio = float(p.get("precio") or 0)
            mon = str(p.get("moneda") or "S/").strip() or "S/"
            filas.append(
                f'<div class="item{" off" if agotado else ""}">{img}'
                f'<div class="nom">{_esc(p.get("nombre"))}'
                f'{"<span class=agot>Agotado</span>" if agotado else ""}</div>'
                f'<div class="pre">{_esc(mon)} {precio:.2f}</div></div>')
        secciones.append(
            f'<h2>{emoji} {_esc(cat)}</h2><div class="lista">'
            + "".join(filas) + "</div>")

    cuerpo = ("".join(secciones) if secciones else
              '<p class="vacio">La carta aún no tiene productos.</p>')
    return f"""<!doctype html><html lang="es"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Carta de la bodega · Pichangol</title>
<meta property="og:title" content="🧃 Carta de la bodega">
<meta property="og:description" content="Precios al día. Pide en el mostrador.">
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#f4f7fa;color:#1c1c1c;padding-bottom:40px}}
  .hero{{background:linear-gradient(135deg,{_ESMERALDA},{_NAVY});color:#fff;padding:26px 20px 20px;border-radius:0 0 22px 22px}}
  .hero h1{{font-size:24px;font-weight:800}}
  .hero p{{margin-top:6px;font-size:13.5px;opacity:.92}}
  .wrap{{max-width:640px;margin:0 auto;padding:6px 16px 0}}
  h2{{font-size:15px;font-weight:800;margin:20px 4px 8px}}
  .lista{{background:#fff;border-radius:16px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,.06)}}
  .item{{display:flex;align-items:center;gap:12px;padding:11px 14px;border-bottom:1px solid #f0f3f7}}
  .item:last-child{{border-bottom:none}}
  .item img,.item .ph{{width:42px;height:42px;border-radius:10px;object-fit:cover;flex:none;display:flex;align-items:center;justify-content:center;background:#e9f6ef;font-size:20px}}
  .ph{{position:relative}}
  .ph img{{position:absolute;inset:0;width:100%;height:100%;border-radius:10px;object-fit:cover}}
  .nom{{flex:1;font-weight:700;font-size:14.5px}}
  .pre{{font-weight:800;color:{_ESMERALDA};font-variant-numeric:tabular-nums}}
  .off .nom,.off .pre{{color:#a5aeb8}}
  .agot{{display:inline-block;margin-left:8px;background:#fdeaea;color:#c0392b;font-size:10.5px;font-weight:800;padding:2px 8px;border-radius:10px;vertical-align:middle}}
  .vacio{{color:#627080;padding:26px 6px;text-align:center}}
  .foot{{max-width:640px;margin:26px auto 0;padding:16px;text-align:center;color:#8a94a0;font-size:12px}}
  .foot b{{color:{_NAVY}}}
</style></head><body>
  <div class="hero">
    <h1>🧃 Carta de la bodega</h1>
    <p>Pide en el mostrador y paga ahí mismo. Precios siempre al día.</p>
  </div>
  <div class="wrap">{cuerpo}</div>
  <div class="foot">Bodega administrada con <b>Pichangol</b> · Reserva, juega, repite.</div>
</body></html>"""
