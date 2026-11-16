"""Inicio del modo anfitrión = tablero del diseñador (16-nov-2026, fase F1 de
`docs/plan/REDISENO_ANFITRION.md`): cifras reales (nada de "—"), cobrado por
moneda, calendario semanal de una cancha, pendientes, ingresos de 7 días y
accesos rápidos."""
import re

import pytest
from fastapi.testclient import TestClient

import config
from main import app
from web import anfitrion_negocio, datos, horarios, permisos

DUENO = "dueno@x.com"
LIMA = {"id": "c_lima", "nombre": "Fútbol 5", "club": "Arena Lima", "dueno": DUENO, "moneda": "S/", "lat": -12.1, "lng": -77.03,
        "hora_apertura": "08:00", "hora_cierre": "22:00", "duracion_slot_min": 60, "precio_hora": 90, "verificada": True}
QUITO = {"id": "c_quito", "nombre": "Tenis 1", "club": "Club Quito", "dueno": DUENO, "moneda": "$", "lat": -0.18, "lng": -78.47,
         "hora_apertura": "08:00", "hora_cierre": "22:00", "duracion_slot_min": 60, "precio_hora": 20, "verificada": False}


def _res(cid, fecha, hora, jugador, precio, pagado, medio="efectivo"):
    fin = f"{int(hora[:2]) + 1:02d}:00"
    return {"id": f"r_{cid}_{fecha}_{hora}", "cancha_id": cid, "fecha": fecha, "hora_inicio": hora, "hora_fin": fin, "jugador": jugador,
            "usuario": "", "telefono": "", "precio": precio, "sena": 0, "pagado": pagado, "medio_pago": medio, "estado": "confirmada",
            "extras": [], "traida_por_app": True, "nivel": "", "moneda": ""}


@pytest.fixture
def cli(monkeypatch):
    from web import cobro_directo_web, sesion
    hoy = horarios.ahora_local("PE").date()
    ayer = hoy.fromordinal(hoy.toordinal() - 1).isoformat()
    filas = [_res("c_lima", hoy.isoformat(), "23:00", "Diego Torres", 90, True, "tarjeta"),
             _res("c_lima", hoy.isoformat(), "21:00", "Lucía Ramírez", 90, False),
             _res("c_lima", ayer, "10:00", "Andrés", 100, True, "yape"),
             _res("c_quito", hoy.isoformat(), "21:00", "Camila", 20, True, "tarjeta")]
    estado = {"canchas": [LIMA, QUITO], "solo": False}
    monkeypatch.setattr(datos, "canchas_de_dueno", lambda email: list(estado["canchas"]))
    monkeypatch.setattr(permisos, "canchas_para", lambda email, accion: list(estado["canchas"]))
    monkeypatch.setattr(permisos, "es_solo_encargado", lambda email: estado["solo"])
    monkeypatch.setattr(anfitrion_negocio, "reservas_dueno", lambda ids, d, h: [dict(r) for r in filas if r["cancha_id"] in ids and d <= r["fecha"] <= h])
    monkeypatch.setattr(datos, "reservas_de_canchas", lambda ids, d, h: [dict(r) for r in filas if r["cancha_id"] in ids and d <= r["fecha"] <= h])
    monkeypatch.setattr(datos, "bloqueos_de", lambda ids, fechas: set())
    monkeypatch.setattr(cobro_directo_web, "pendientes_operables", lambda email: 2)
    monkeypatch.setattr(config, "GOOGLE_WEB_CLIENT_ID", "cid-web")
    monkeypatch.setattr(sesion, "_tokeninfo", lambda t: {"email": DUENO, "email_verified": "true", "aud": "cid-web",
                                                         "name": "Don Dueño", "exp": "9999999999"})
    c = TestClient(app, base_url="https://testserver")
    c.post("/web/sesion", json={"credential": "x"})
    c.estado = estado
    return c


def _main(html):
    return html.split("<main", 1)[1]


def test_tablero_con_cifras_reales_y_cobrado_por_moneda(cli):
    h = _main(cli.get("/anfitrion").text)
    assert "<h1>Modo anfitrión</h1>" in h and "—" not in h
    kpis = dict(re.findall(r"<span>([^<]+)</span><div class='ai-kpi-v'><b[^>]*>([^<]+)</b>", h))
    assert kpis["Reservas de hoy"] == "3"            # 2 en Lima + 1 en Quito
    assert kpis["Pagos por confirmar"] == "2" and "aria-label='2 por revisar'" in h
    assert kpis["Cobrado hoy"] == "S/ 90"             # soles y dólares NUNCA se suman…
    assert "<small>+ $ 20</small>" in h               # …el dólar va aparte
    assert kpis["Ocupación de hoy"].endswith("%")
    # Pendientes: comprobantes, próximas reservas (de verdad) y la cancha en verificación.
    assert "2 comprobantes por revisar" in h and "Tenis 1 · Club Quito" not in h.split("Solicitudes nuevas")[1][:10]
    assert "1 cancha en verificación" in h and "/anfitrion/verificacion/c_quito" in h
    # Ingresos de 7 días en la moneda principal: ayer 100 + hoy 90.
    assert re.search(r"Ingresos <small>\(últimos 7 días\)</small></h2><b>S/ 190</b>", h)
    for href in ("/anfitrion/mis-canchas", "/anfitrion/clientes", "/anfitrion/academia", "/anfitrion/disponibilidad"):
        assert f"href='{href}'" in h


def test_calendario_semanal_de_la_cancha_elegida(cli):
    h = _main(cli.get("/anfitrion").text)
    assert "<option value='c_lima' selected>" in h and "Abrir calendario" in h
    assert re.search(r"class='ai-ev ef'[^>]*>Lucía<", h) and re.search(r"class='ai-ev'[^>]*>Andrés<", h)
    assert "Hoy en esta cancha: 1 reserva · 21:00 Lucía" in h   # las 23:00 quedan fuera del horario de esa cancha
    q = _main(cli.get("/anfitrion?cancha=c_quito").text)
    assert "<option value='c_quito' selected>" in q and ">Camila<" in q and ">Lucía<" not in q


def test_sin_canchas_bienvenida_y_recepcion_sin_plata(cli):
    cli.estado["canchas"] = []
    h = _main(cli.get("/anfitrion").text)
    assert "Registra tu primera cancha" in h and "href='/anfitrion/nueva'" in h and "ai-kpi" not in h
    cli.estado["canchas"] = [LIMA]
    cli.estado["solo"] = True
    r = _main(cli.get("/anfitrion").text)
    assert "Reservas de hoy" in r and "Pagos por confirmar" in r
    assert "Cobrado hoy" not in r and "Ingresos" not in r and "href='/anfitrion/clientes'" not in r
