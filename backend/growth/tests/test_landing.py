"""Render de la landing pública: la sección de RANKING del circuito (Fase 0-b)
se muestra solo cuando llegan filas de ranking."""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from marketing.landing import render_landing  # noqa: E402


def test_landing_muestra_ranking_cuando_hay_filas():
    html = render_landing({
        "nombre": "Academia Tenis Lima",
        "ranking": [
            {"nombre": "Ana Torres", "categoria": "7ma", "pj": 5, "pg": 4,
             "puntos": 13, "pct": 80},
            {"nombre": "Luis Paz", "categoria": "7ma", "pj": 5, "pg": 1,
             "puntos": 7, "pct": 20},
        ],
    })
    assert 'id="ranking"' in html
    assert "Ranking" in html
    assert "Ana Torres" in html
    assert "Luis Paz" in html
    assert "🥇" in html          # podio
    assert "13" in html          # puntos del líder


def test_landing_sin_ranking_no_muestra_seccion():
    html = render_landing({"nombre": "Academia Sin Partidos"})
    assert 'id="ranking"' not in html


def test_landing_ranking_vacio_no_muestra_seccion():
    html = render_landing({"nombre": "X", "ranking": []})
    assert 'id="ranking"' not in html
