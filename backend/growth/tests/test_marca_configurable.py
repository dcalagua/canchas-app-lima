"""Marca configurable (pedido del director, 20-oct-2026: los del tenis piden un
nombre más genérico que "Pichangol"). El nombre y el dominio de marca viven en
UN solo lugar: `config.MARCA` / `config.MARCA_DOMINIO` (env MARCA_NOMBRE /
MARCA_DOMINIO). Estos tests impiden que alguien vuelva a escribirlos a mano."""
from __future__ import annotations

import ast
import io
import os
import re
import subprocess
import sys
import tokenize

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RX = re.compile(r"(?<![\w/@.\-])(Pichangol|www\.pichangol\.app)(?![\w\-])")


def _archivos():
    for raiz, dirs, archs in os.walk(RAIZ):
        dirs[:] = [d for d in dirs if d not in ("tests", "__pycache__", ".venv", "venv")]
        for a in archs:
            if a.endswith(".py") and a != "config.py":
                yield os.path.join(raiz, a)


def test_ningun_texto_de_python_escribe_la_marca_a_mano():
    """Los docstrings y comentarios pueden decir Pichangol; los textos que ve la gente no."""
    malos = []
    for r in _archivos():
        src = open(r, encoding="utf-8").read()
        docs = set()
        for n in ast.walk(ast.parse(src)):
            if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and n.body \
                    and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant):
                docs.update(range(n.body[0].lineno, n.body[0].end_lineno + 1))
        for tk in tokenize.generate_tokens(io.StringIO(src).readline):
            if tk.type in (tokenize.STRING, getattr(tokenize, "FSTRING_MIDDLE", -1)) \
                    and tk.start[0] not in docs and RX.search(tk.string):
                malos.append(f"{os.path.relpath(r, RAIZ)}:{tk.start[0]}")
    assert not malos, "Usa config.MARCA / config.MARCA_DOMINIO en: " + ", ".join(malos[:20])


def test_html_de_marca_usa_marcadores():
    html = open(os.path.join(RAIZ, "legal", "home.html"), encoding="utf-8").read()
    assert not RX.search(html), "legal/home.html: usa {{MARCA}} / {{MARCA_DOMINIO}}"


def test_con_otro_nombre_las_paginas_lo_muestran():
    codigo = r"""
import re
from fastapi.testclient import TestClient
import main
c = TestClient(main.app)
for ruta in ["/", "/legal/terminos", "/legal/privacidad", "/libro-de-reclamaciones", "/entrar"]:
    t = c.get(ruta, follow_redirects=True).text
    assert "CanchaLibre" in t, ruta
    assert not re.search(r"(?<![\w/@.\-])Pichangol(?![\w\-])", t), (ruta, re.findall(r".{0,40}Pichangol.{0,40}", t)[:3])
print("ok")
"""
    env = dict(os.environ, MARCA_NOMBRE="CanchaLibre", MARCA_DOMINIO="www.canchalibre.app", DATABASE_URL="")
    r = subprocess.run([sys.executable, "-c", codigo], cwd=RAIZ, env=env, capture_output=True, text=True, timeout=240)
    assert r.returncode == 0 and "ok" in r.stdout, r.stderr[-2000:]
