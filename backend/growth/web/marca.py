"""Secciones de MARCA / comercio que van debajo del explorador en la raíz del
dominio (`GET /`): qué ofrecemos, servicios y precios, cómo funciona, pagos,
contacto, términos, cancelaciones, privacidad y el Libro de Reclamaciones.

Viven en `legal/home.html` (texto legal que edita el equipo sin tocar Python;
los datos de la empresa van como marcadores `{{EMPRESA}}`, `{{RUC}}`, `{{CORREO}}`…
que `empresa.rellenar` sustituye con lo configurado en la torre)
y aquí se EXTRAEN y se ANIDAN dentro de la página tipo Airbnb: el CSS de esa
página se re-escribe con el prefijo `.marca` para que no pise el sistema de
diseño de `web/ui.py` (`.card`, `.grid`, `label`, `input`, …).

Culqi / INDECOPI revisan la URL raíz del comercio: razón social, RUC,
contacto, catálogo con foto+precio+botón, términos, política de cancelación
y Libro de Reclamaciones INTEGRADO (POST /reclamaciones). Todo eso sigue en
la raíz, después de las canchas.
"""

from __future__ import annotations

import os
import re

import empresa

_HOME = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "legal", "home.html")

_INICIO = "<!-- QUÉ OFRECEMOS -->"
_FIN = "<footer>"
# Reglas que NO tienen sentido anidadas (las define ui.py para toda la página).
_DESCARTAR = {"*", "html", "body", "header.nav", ".nav-in", ".wm", ".wm svg", "nav.links",
              "nav.links a", "nav.links a:hover", "nav.links a.ctan", ".hero", ".hero .pill",
              ".hero h1", ".hero p.lead", ".hero .cta.sec", "footer", "footer .wrap", "footer a"}


def _leer() -> str:
    try:
        with open(_HOME, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def _scope_bloque(css: str, prefijo: str) -> str:
    """Prefija cada selector de `css` (sin @media anidados) con `prefijo`."""
    out = []
    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
        selectores = [s.strip() for s in m.group(1).split(",") if s.strip()]
        cuerpo = m.group(2).strip()
        keep = []
        for s in selectores:
            if s == ":root":
                continue  # los tokens ya los define ui.py con los mismos valores
            if s in _DESCARTAR:
                continue
            keep.append(f"{prefijo} {s}")
        if keep and cuerpo:
            out.append(f"{', '.join(keep)}{{{cuerpo}}}")
    return "".join(out)


def scope_css(css: str, prefijo: str = ".marca") -> str:
    """Re-escribe una hoja simple (reglas + @media de un nivel) bajo `prefijo`."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    out = []
    i = 0
    while i < len(css):
        m = re.search(r"@media[^{]*\{", css[i:])
        if not m:
            out.append(_scope_bloque(css[i:], prefijo))
            break
        out.append(_scope_bloque(css[i:i + m.start()], prefijo))
        # cuerpo del @media: hasta la llave que cierra su nivel
        j = i + m.end()
        depth = 1
        k = j
        while k < len(css) and depth:
            if css[k] == "{":
                depth += 1
            elif css[k] == "}":
                depth -= 1
            k += 1
        interior = css[j:k - 1]
        out.append(f"{css[i + m.start():i + m.end()]}{_scope_bloque(interior, prefijo)}}}")
        i = k
    return "".join(out)


def secciones() -> tuple[str, str, str]:
    """(css_scoped, html_secciones, js) de la home de marca; vacíos si falta."""
    doc = empresa.rellenar(_leer())
    if not doc:
        return "", "", ""
    css = ""
    m = re.search(r"<style>(.*?)</style>", doc, flags=re.S)
    if m:
        css = scope_css(m.group(1))
    a = doc.find(_INICIO)
    b = doc.find(_FIN)
    html = doc[a:b] if a >= 0 and b > a else ""
    js = ""
    for s in re.finditer(r"<script>(.*?)</script>", doc, flags=re.S):
        if "lr-form" in s.group(1):
            js = s.group(1)
    return css, html, js
