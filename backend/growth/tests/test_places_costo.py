"""Costo de Google Places en la web (factura oct-2026): cosecha primero, una
consulta por zona cada 30 días aunque se redespliegue, y tope diario."""
from db.store import stores
from web import descubrir as d

CRUDO = [{"id": "Z1", "displayName": {"text": "Complejo Deportivo El Sol"}, "types": ["sports_complex"],
          "location": {"latitude": -12.10, "longitude": -77.01}, "formattedAddress": "Av. Sol 1"}]


def _preparar(monkeypatch, cosecha=None):
    d.limpiar_cache()
    llamadas, guardadas = [], []
    monkeypatch.setattr(d, "_llamar_edge", lambda *a, **k: (llamadas.append(a) or CRUDO))
    monkeypatch.setattr(d, "leer_cosecha", lambda *a, **k: list(cosecha or []))
    monkeypatch.setattr(d, "guardar_cosecha", lambda lista: guardadas.extend(lista))
    return llamadas, guardadas


def test_una_consulta_por_zona_aunque_se_redespliegue(monkeypatch):
    llamadas, guardadas = _preparar(monkeypatch)
    r = d.descubrir_cerca(-12.10, -77.00)
    assert [c["id"] for c in r] == ["gp_Z1"] and len(llamadas) == 1
    assert guardadas[0]["id"] == "gp_Z1"           # queda en la cosecha compartida
    assert llamadas[0][4] is False                  # nunca pide fotos a la Edge
    # "Redespliegue": se pierde la caché en memoria, NO el registro de zonas.
    d._cache.clear()
    d.descubrir_cerca(-12.101, -77.002, fotos=True)
    assert len(llamadas) == 1
    estado = stores.to_state()
    assert estado["places_zonas"] and estado["places_uso"]["llamadas"] == 1


def test_zona_vigente_sirve_desde_la_cosecha(monkeypatch):
    cos = [{"id": "gp_C1", "nombre": "Cancha Cosechada", "direccion": "", "lat": -12.1,
            "lng": -77.0, "deporte": "futbol", "fotos": []}]
    llamadas, _ = _preparar(monkeypatch, cos)
    d._marcar_zona(d._zona(-12.1, -77.0, "PE"), -12.1, -77.0)
    r = d.descubrir_cerca(-12.1, -77.0)
    assert [c["id"] for c in r] == ["gp_C1"] and llamadas == []


def test_tope_diario_corta_google(monkeypatch):
    llamadas, _ = _preparar(monkeypatch)
    stores.config["places_web_tope_dia"] = "1"
    try:
        d.descubrir_cerca(-12.10, -77.00)
        d.descubrir_cerca(-13.50, -76.00)       # otra zona, pero ya no hay cupo
        assert len(llamadas) == 1
    finally:
        stores.config["places_web_tope_dia"] = "120"


def test_robots_bloquea_rutas_que_cuestan():
    from fastapi.testclient import TestClient
    from main import app
    client = TestClient(app)
    t = client.get("/robots.txt").text
    assert "Disallow: /web/" in t and "Disallow: /admin" in t


def test_explorador_web_no_busca_solo_al_mover_ni_pide_fotos_a_google():
    from fastapi.testclient import TestClient
    from main import app
    client = TestClient(app)
    html = client.get("/canchas").text
    assert "&fotos=1" not in html
    assert "Buscar canchas en esta zona" in html
