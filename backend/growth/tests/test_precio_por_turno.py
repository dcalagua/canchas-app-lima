"""PRECIO POR HORA o POR TURNO (pedido del director, 29-sep-2026: "debo tener
la opción de cobrar 15 soles la hora o 15 por 1.5 h") + UNA sola fórmula de
precio en web y app ("todo el funcionamiento de la web y app debe estar
alineado e igual").

Espejo en Dart: `Cancha.precioBaseTurno` + `AppState.precioSlotEfectivo`
(`lib/models/models.dart`, `lib/state/app_state.dart`)."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from main import app  # noqa: E402
from web import datos, horarios  # noqa: E402
from tests.test_web_reservas import db, _manana  # noqa: E402,F401


def test_formula_unica_del_turno_igual_que_el_app():
    # Por hora: hora × duración / 60, .50 redondea hacia ARRIBA como Dart
    # (antes la web daba 22 y el app 23 por el mismo turno).
    assert horarios.precio_slot(15, 90) == 23
    assert horarios.redondear_precio(22.5) == 23 and horarios.redondear_precio(22.49) == 22
    # Por turno: el monto fijo del dueño, dure lo que dure.
    assert horarios.precio_slot(10, 90, precio_turno=15) == 15
    assert horarios.precio_slot(999, 120, precio_turno=40) == 40
    # Un solo descuento: el puntual del turno manda sobre la hora feliz
    # (antes la web los ACUMULABA y el app no).
    assert horarios.precio_slot(60, 60, 10, descuento_valle=50, en_valle=True) == 54
    assert horarios.precio_slot(60, 60, 0, descuento_valle=50, en_valle=True) == 30
    assert horarios.precio_slot(0, 90, 20, precio_turno=15) == 12
    # Equivalente por hora para APKs viejos: turno × 60 / duración.
    assert horarios.precio_hora_equivalente(15, 90) == 10
    assert horarios.precio_slot(horarios.precio_hora_equivalente(20, 90), 90) == 20
    assert horarios.duracion_texto(90) == "1 h 30" and horarios.duracion_texto(60) == "1 h"
    assert horarios.precio_publico({"precio_turno": 15, "duracion_slot_min": 90}) == (15, "por turno de 1 h 30")
    assert horarios.precio_publico({"precio_hora": 60, "duracion_slot_min": 90}) == (60, "por hora")


def test_dueno_cobra_por_turno_desde_la_web_y_la_ficha_lo_respeta(db, monkeypatch):
    from web import sesion
    monkeypatch.setattr(config, "GOOGLE_WEB_CLIENT_ID", "cid-web")
    cli = TestClient(app, base_url="https://testserver")
    monkeypatch.setattr(sesion, "_tokeninfo", lambda t: {"email": "dueno@x.com", "email_verified": "true", "aud": "cid-web", "name": "Don Dueño", "exp": "9999999999"})
    cli.post("/web/sesion", json={"credential": "x"})
    url = "/anfitrion/cancha/c_lima/editar"
    html = cli.get(url).text
    assert "¿Cómo cobras?" in html and "data-g='modo_precio'" in html and "Por turno" in html and "precioPrev" in html
    base = {"nombre": "Cancha Central", "deportes": ["futbol"], "superficie": "Grass sintético",
            "descuento_valle": 0, "valle_desde": "07:00", "valle_hasta": "12:00", "sena_pct": 0,
            "hora_apertura": "07:00", "hora_cierre": "23:00", "duracion_slot_min": 90, "servicios_extra": [], "fotos": []}
    r = cli.post(url, json={**base, "modo_precio": "turno", "precio": 0})
    assert r.status_code == 400 and r.json()["campo"] == "precio" and "turno" in r.json()["error"]
    r = cli.post(url, json={**base, "modo_precio": "turno", "precio": 15})
    assert r.status_code == 200, r.text
    c = db.canchas["c_lima"]
    assert c["precio_turno"] == 15 and c["precio_hora"] == 10  # equivalente para APKs viejos
    # La ficha muestra "por turno" y cada turno de 1 h 30 cuesta S/ 15.
    ficha = cli.get("/reservar/c_lima").text
    assert "por turno de 1 h 30" in ficha
    d = cli.get(f"/web/disponibilidad/c_lima?fecha={_manana()}").json()
    assert d["slots"] and all(s["precio"] == 15 for s in d["slots"])
    # El editor lo muestra prellenado en modo turno.
    assert "<button type='button' class='chip sel' data-g='modo_precio' data-v='turno'>" in cli.get(url).text
    # Volver a POR HORA limpia el precio por turno.
    r = cli.post(url, json={**base, "modo_precio": "hora", "precio": 15})
    assert r.status_code == 200 and not db.canchas["c_lima"]["precio_turno"] and db.canchas["c_lima"]["precio_hora"] == 15
    d = cli.get(f"/web/disponibilidad/c_lima?fecha={_manana()}").json()
    assert all(s["precio"] == 23 for s in d["slots"])  # 15 × 1.5 = 22.50 → 23, igual que el app
    # Un cliente viejo que solo manda precio_hora sigue funcionando (por hora).
    r = cli.post(url, json={**base, "precio_hora": 60})
    assert r.status_code == 200 and db.canchas["c_lima"]["precio_hora"] == 60


def test_columna_precio_turno_opcional(monkeypatch):
    """Sin el SQL, la web no intenta escribir `precio_turno` (queda solo el
    equivalente por hora)."""
    monkeypatch.setattr(datos, "col_precio_turno_disponible", lambda: False)
    monkeypatch.setattr(datos, "col_fidelidad_disponible", lambda: False)
    assert "precio_turno" not in datos._cols_cancha()
    assert "precio_turno" in datos.COLS_EDITABLES and "precio_turno" in datos.COLS_ADOPCION
