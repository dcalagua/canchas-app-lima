"""MI PERFIL del modo anfitrión (`/anfitrion/perfil`, rediseño 16-nov-2026):
identidad, datos, verificación, saldo/Pro/Plan Academia, preferencias de
avisos (que SÍ se respetan al enviar) y cerrar sesión en todos los
dispositivos."""
import pathlib
import urllib.request

import pytest
from fastapi.testclient import TestClient

import config
import correos
import prefs_avisos
from db.store import stores
from main import app
from pagos import router as pagos_router
from web import datos, jugador_cuenta, permisos, sesion

YO = "carlos@demo.pe"
LIMA = {"lat": -12.09, "lng": -77.03}
LA_PAZ = {"lat": -16.5, "lng": -68.15}


@pytest.fixture(autouse=True)
def _estado(monkeypatch):
    antes = stores.to_state()
    monkeypatch.setattr(config, "GOOGLE_WEB_CLIENT_ID", "cid-web")
    monkeypatch.setattr(datos, "canchas_de_dueno", lambda e: [])
    monkeypatch.setattr(datos, "academias_de_dueno", lambda e: [])
    monkeypatch.setattr(datos, "esta_verificado", lambda e: False)
    monkeypatch.setattr(permisos, "es_solo_encargado", lambda e: False)
    monkeypatch.setattr(jugador_cuenta, "perfil_completo",
                        lambda e: {"nombre": "Carlos Paredes Ruiz", "foto_url": "", "celular": "51987654321",
                                   "bio": {"estilo": "Ofensivo"}})
    yield
    stores.load_state(antes)


def _cli(email=YO):
    cli = TestClient(app, base_url="https://testserver")
    cli.cookies.set(sesion.COOKIE, sesion.emitir({"email": email, "nombre": "Carlos", "foto": ""}))
    return cli


def _cancha(i, club, punto):
    return {"id": f"c{i}", "nombre": f"Cancha {i}", "club": club, "dueno": YO, "verificada": True, **punto}


def test_sin_sesion_va_a_entrar():
    r = TestClient(app, base_url="https://testserver").get("/anfitrion/perfil", follow_redirects=False)
    assert r.status_code in (302, 303) and "/entrar?volver=" in r.headers["location"]


def test_mi_perfil_con_datos_reales(monkeypatch):
    canchas = [_cancha(1, "Club A", LIMA), _cancha(2, "Club A", LIMA), _cancha(3, "Club B", LIMA)]
    monkeypatch.setattr(datos, "canchas_de_dueno", lambda e: canchas)
    monkeypatch.setattr(datos, "academias_de_dueno",
                        lambda e: [{"id": "ac1", "nombre": "Academia Uno", "dueno": YO, **LIMA}])
    stores.config["pro_precio_soles"] = "17"
    html = _cli().get("/anfitrion/perfil").text
    # identidad y cuenta
    assert "Mi perfil" in html and "‹ Modo anfitrión" in html
    assert "2 locales · 3 canchas · 1 academia" in html
    assert "Anfitrión" in html and "Identidad pendiente" in html
    # nombre completo partido sin perder nada (apellidos = 2.ª mitad)
    assert "value='Carlos'" in html and "value='Paredes Ruiz'" in html
    assert "value='987654321'" in html and "readonly" in html
    # la bio viaja para no borrarla al guardar con el mismo endpoint de Configuración
    assert '"estilo": "Ofensivo"' in html and "/web/cuenta/perfil" in html
    # verificación por país, saldo, Pro con su precio real y Plan Academia
    assert "Verificar DNI" in html and "/cuenta/identidad?pais=PE" in html
    assert "S/ 0.00" in html and "/mi-billetera#recargar" in html
    assert "Activar · S/ 17.00/mes" in html or "Activar · S/ 17/mes" in html
    assert "Plan Academia" in html and "Prueba gratis" in html and "/anfitrion/academia/plan?academia=ac1" in html
    # notificaciones (todo encendido por defecto) + nota de recibos
    # lo operativo nace encendido; Novedades (promociones) nace APAGADA (consentimiento, Ley 29733)
    assert html.count("role='switch' aria-checked='true'") == 3 and html.count("role='switch' aria-checked='false'") == 1
    assert "Yape, Plin" in html and "recibos y comprobantes de pago por correo" in html
    # sin selector de idioma; acciones de privacidad
    assert "Idioma" not in html and "vpCerrarTodas" in html and "/legal/eliminar-cuenta" in html
    assert "confirm(" not in html and "alert(" not in html


def test_mi_perfil_multi_pais_y_verificado(monkeypatch):
    monkeypatch.setattr(datos, "canchas_de_dueno", lambda e: [_cancha(1, "Club Paz", LA_PAZ)])
    monkeypatch.setattr(datos, "esta_verificado", lambda e: True)
    monkeypatch.setattr(jugador_cuenta, "perfil_completo", lambda e: {"nombre": "Ana", "celular": ""})
    stores.acreditar(YO, 2500)
    html = _cli().get("/anfitrion/perfil").text
    assert "Bs 25.00" in html and "S/ 0" not in html
    assert "Yape" not in html and "QR o transferencia" in html
    assert "Identidad verificada" in html and "Verificar CI" not in html
    # con saldo el país queda bloqueado con la explicación
    assert "id='vpPaisCasa'" in html and " disabled aria-describedby='vpPaisNota'" in html
    assert "primero úsalo o solicita su liquidación" in html


def test_prefs_avisos_endpoint_y_snapshot():
    assert TestClient(app, base_url="https://testserver").post("/web/avisos/prefs", json={"clave": "reservas", "on": False}).status_code == 401
    cli = _cli()
    assert cli.post("/web/avisos/prefs", json={"clave": "otra", "on": False}).status_code == 400
    assert cli.post("/web/avisos/prefs", json={"clave": "reservas", "on": "no"}).status_code == 400
    r = cli.post("/web/avisos/prefs", json={"clave": "reservas", "on": False}).json()
    assert r["ok"] and r["prefs"] == {"reservas": False, "pagos": True, "academia": True, "novedades": False}
    assert cli.get("/web/avisos/prefs").json()["prefs"]["reservas"] is False
    # viaja en el snapshot
    estado = stores.to_state()
    stores.avisos_prefs.clear()
    stores.load_state(estado)
    assert prefs_avisos.quiere(YO, "reservas") is False and prefs_avisos.quiere(YO, "pagos") is True
    html = cli.get("/anfitrion/perfil").text
    assert "aria-checked='false' aria-labelledby='vpAv_reservas'" in html


def _capturar_push(monkeypatch) -> list[dict]:
    import json
    enviados: list[dict] = []
    monkeypatch.setattr(config, "SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setattr(config, "SUPABASE_ANON_KEY", "anon")

    class _R:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b""

    def _urlopen(req, timeout=None):
        enviados.append(json.loads(req.data.decode()))
        return _R()
    monkeypatch.setattr(urllib.request, "urlopen", _urlopen)
    return enviados


def test_preferencia_apagada_evita_el_push_y_lo_demas_sigue(monkeypatch):
    enviados = _capturar_push(monkeypatch)
    prefs_avisos.guardar(YO, {"reservas": False, "academia": False, "novedades": False})
    pagos_router._aviso_push_usuario(YO, "Nueva reserva 📅", "Ana · Cancha 1", tipo="reserva")
    pagos_router._aviso_push_usuario(YO, "Nueva reserva 🎁", "premio", tipo="reserva")
    pagos_router._aviso_push_usuario(YO, "Nuevo alumno 🎓", "Luis", tipo="academia")
    pagos_router._aviso_push_usuario(YO, "3 alumnos nuevos 🎓", "familia", tipo="academia")
    pagos_router._aviso_push_usuario(YO, "Cuota pagada 💰", "Luis", tipo="academia")
    pagos_router._aviso_push_usuario(YO, "Llegó algo nuevo", "promo", tipo="novedades")
    assert enviados == []
    # Lo que no se apaga: cancelaciones, devoluciones, avisos como jugador/alumno, plan academia.
    pagos_router._aviso_push_usuario(YO, "Reserva cancelada 📅", "libre", tipo="reserva")
    pagos_router._aviso_push_usuario(YO, "Devuelve un pago 💸", "devuelve", tipo="reserva")
    pagos_router._aviso_push_usuario(YO, "¡Reserva confirmada! ✅", "jugador", tipo="reserva")
    pagos_router._aviso_push_usuario(YO, "Hoy vence tu cuota de Academia X", "alumno", tipo="academia")
    pagos_router._aviso_push_usuario(YO, "Confirma un pago 🧾", "voucher")  # pagos sigue encendido
    assert [x["titulo"] for x in enviados] == ["Reserva cancelada 📅", "Devuelve un pago 💸", "¡Reserva confirmada! ✅",
                                                "Hoy vence tu cuota de Academia X", "Confirma un pago 🧾"]
    # otra cuenta (sin preferencias) recibe todo
    pagos_router._aviso_push_usuario("otro@x.pe", "Nueva reserva 📅", "x", tipo="reserva")
    assert enviados[-1]["email"] == "otro@x.pe"
    prefs_avisos.guardar(YO, {"pagos": False})
    n = len(enviados)
    pagos_router._aviso_push_usuario(YO, "Confirma un pago 🧾", "voucher")
    assert len(enviados) == n


def test_titulos_clasificados_existen_en_el_codigo_que_los_envia():
    """Si alguien cambia el título de un aviso al dueño, la preferencia dejaría
    de aplicarse en silencio: este test lo detecta."""
    base = pathlib.Path(__file__).resolve().parent.parent
    fuentes = {
        "Nueva reserva 📅": "web/reserva_pago.py", "Nueva reserva 🎁": "web/reserva_pago.py",
        "Confirma un pago 🧾": "web/cobro_directo_web.py", "Nuevo alumno 🎓": "web/academia.py",
        "alumnos nuevos 🎓": "web/academia.py", "Cuota pagada 💰": "web/jugador_clases.py",
        "Pago por confirmar 💜": "academia_plan.py", "Pago confirmado solo ✅": "academia_plan.py",
    }
    for titulo, archivo in fuentes.items():
        assert titulo in (base / archivo).read_text(encoding="utf-8"), (titulo, archivo)
        tipo = "academia" if "alumno" in titulo or "Cuota" in titulo or "💜" in titulo or "solo" in titulo else "reserva"
        assert prefs_avisos.categoria_push(titulo if not titulo.startswith("alumnos") else "2 " + titulo, tipo)
    assert prefs_avisos.categoria_push("Reserva cancelada 📅", "reserva") is None
    assert prefs_avisos.categoria_push("Novedad", "marketing") == "novedades"


def test_correo_con_categoria_respeta_la_preferencia_y_los_recibos_no(monkeypatch):
    prefs_avisos.guardar(YO, {"novedades": False})
    antes = len(stores.correos_eventos)
    r = correos.encolar("aviso", datos={"para": YO, "titulo": "Novedades", "categoria": "novedades"})
    assert r.get("omitido") == "preferencia" and len(stores.correos_eventos) == antes
    correos.encolar("aviso", datos={"para": YO, "titulo": "Recordatorio de pago"})  # sin categoría: siempre
    correos.encolar("reserva", pago_id=1)  # recibo de pago: siempre
    assert len(stores.correos_eventos) == antes + 2
    # otra cuenta que NUNCA eligió: tampoco recibe novedades (nacen apagadas)…
    correos.encolar("aviso", datos={"para": "otro@x.pe", "titulo": "Novedades", "categoria": "novedades"})
    assert len(stores.correos_eventos) == antes + 2
    # …y si las enciende, sí.
    prefs_avisos.guardar("otro@x.pe", {"novedades": True})
    correos.encolar("aviso", datos={"para": "otro@x.pe", "titulo": "Novedades", "categoria": "novedades"})
    assert len(stores.correos_eventos) == antes + 3


def test_cerrar_sesion_en_todos_los_dispositivos():
    otra = sesion.emitir({"email": YO, "nombre": "Carlos", "foto": ""})  # otro navegador
    cli = _cli()
    assert sesion.leer(otra)["email"] == YO
    assert TestClient(app, base_url="https://testserver").post("/web/sesion/cerrar-todas").status_code == 401
    r = cli.post("/web/sesion/cerrar-todas")
    assert r.status_code == 200 and r.json()["ok"]
    nueva = r.cookies.get(sesion.COOKIE)
    assert sesion.leer(otra) is None                      # la del otro navegador ya no vale
    assert sesion.leer(nueva)["email"] == YO              # este navegador sigue dentro
    assert cli.get("/anfitrion/perfil").status_code == 200
    # la época viaja en el snapshot (sobrevive a un reinicio)
    estado = stores.to_state()
    stores.sesion_epocas.clear()
    stores.load_state(estado)
    assert sesion.leer(otra) is None and sesion.leer(nueva)["email"] == YO
    # otra cuenta no se ve afectada
    assert sesion.leer(sesion.emitir({"email": "otro@x.pe"}))["email"] == "otro@x.pe"
