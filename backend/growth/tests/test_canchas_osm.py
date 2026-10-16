"""Canchas de OpenStreetMap como COMPLEMENTO de Google (oct-2026, director:
"siembra OSM solo con nombre … bajar costo SIN QUE AFECTE LO ACTUAL")."""
import gzip
import json

from fastapi.testclient import TestClient

from db.store import stores
from web import descubrir as d
from web import osm

CRUDO_GOOGLE = [{"id": "Z1", "displayName": {"text": "Complejo Deportivo El Sol"}, "types": ["sports_complex"],
                 "location": {"latitude": -12.10, "longitude": -77.01}, "formattedAddress": "Av. Sol 1"}]

FILAS = [
    # [lat, lng, sport, nombre, ciudad, osm_id, leisure]
    [-12.1200, -77.0000, "soccer", "La Bombonera de Surquillo", "lima", "w1", "pitch"],
    [-12.1201, -77.0002, "soccer", "La Bombonera de Surquillo", "lima", "w2", "pitch"],      # mismo local
    [-12.1202, -77.0001, "futsal", "La Bombonera de Surquillo", "lima", "n3", "sports_centre"],
    [-12.1100, -77.0100, "tennis", "Club Tenis Los Pinos", "lima", "w4", "pitch"],
    [-12.1300, -77.0200, "", "Complejo Deportivo Santa Rosa", "lima", "w5", "sports_centre"],
    [-12.1301, -77.0201, "", "Club Social Los Amigos", "lima", "w6", "sports_centre"],        # sin deporte
    [-12.1400, -77.0300, "soccer", "Cancha 2", "lima", "w7", "pitch"],                        # genérico
    [-12.1401, -77.0301, "multi", "Losa deportiva", "lima", "w8", "pitch"],                    # genérico
    [-12.1402, -77.0302, "basketball", "Losa Deportiva Las Flores", "lima", "w9", "pitch"],    # loza municipal
    [-12.1403, -77.0303, "baseball", "Estadio de Béisbol Nikkei", "lima", "w10", "pitch"],     # no reservable
    [-12.1004, -77.0100, "soccer", "Complejo Deportivo El Sol", "lima", "w11", "pitch"],      # = Google
    [-12.1009, -77.0103, "padel", "Padel Point Miraflores", "lima", "w12", "pitch"],          # a ~100 m de Google
    [-16.5000, -68.1500, "multi", "Cancha Los Andes", "la_paz_el_alto", "w13", "pitch"],
    [-12.1500, -77.0400, "volleyball", "Coliseo Chabuca", "lima", "x14", "pitch"],            # id inválido
]


def _con_datos(monkeypatch, filas=FILAS):
    lista = osm.procesar(filas)
    monkeypatch.setattr(osm, "_datos", ("v-prueba", lista))
    return lista


def _preparar_google(monkeypatch):
    d.limpiar_cache()
    llamadas = []
    monkeypatch.setattr(d, "_llamar_edge", lambda *a, **k: (llamadas.append(a) or CRUDO_GOOGLE))
    monkeypatch.setattr(d, "leer_cosecha", lambda *a, **k: [])
    guardadas = []
    monkeypatch.setattr(d, "guardar_cosecha", lambda lista: guardadas.extend(lista))
    return llamadas, guardadas


def test_mapeo_de_deporte_y_nombres_genericos():
    assert osm.deporte_osm("soccer", "Bombonera") == "futbol"
    assert osm.deporte_osm("futsal", "Bombonera") == "futbol"
    assert osm.deporte_osm("tennis", "Los Pinos") == "tenis"
    assert osm.deporte_osm("padel", "Point") == "padel"
    assert osm.deporte_osm("basketball", "Los Halcones") == "basquet"
    assert osm.deporte_osm("volleyball", "Las Matadoras") == "voley"
    assert osm.deporte_osm("multi", "Club de Pádel Sur") == "padel"      # se infiere del nombre
    assert osm.deporte_osm("multi", "Los Andes") == "futbol"             # multiuso → fútbol
    assert osm.deporte_osm("", "Complejo Deportivo Santa Rosa") == "futbol"
    assert osm.deporte_osm("", "Club Social Los Amigos") is None          # sin señal: fuera
    assert osm.deporte_osm("baseball", "Nikkei") is None
    assert osm.deporte_osm("five-a-side", "Azkunaga") == "futbol"
    assert osm.deporte_osm("voleyball", "Ecuavoley Central") == "voley"
    assert osm.deporte_osm("multi", "Cancha de toros El Qorilazo") is None
    assert osm.deporte_osm("wallyball", "Wally Los Chicos") is None      # no es deporte de Pichangol
    assert osm.deporte_osm("multi", "Cancha Polifuncional Barrio Sur") is None  # = loza municipal (como el APK)
    assert osm.deporte_osm("soccer", "Gimnasio Municipal Sur") is None   # descarte de la heurística
    assert osm.deporte_osm("soccer", "I.E. 2034 San Martín") is None     # colegio
    for g in ["Cancha", "Cancha 2", "Losa deportiva", "Campo de fútbol", "Cancha de Fútbol N° 3",
              "Losa Multideportiva II", "12", "Polideportivo", "Cancha A", "Cancha sintética"]:
        assert not osm.nombre_util(g), g
    for b in ["La Bombonera de Surquillo", "Cancha Los Pinos", "Club Tenis Lima", "Estadio Monumental"]:
        assert osm.nombre_util(b), b


def test_procesar_agrupa_mismo_nombre_a_150m_y_descarta():
    lista = osm.procesar(FILAS)
    ids = {c["id"] for c in lista}
    # La Bombonera: 3 filas = 1 local; representante = el complejo, deporte = fútbol.
    bomb = [c for c in lista if c["nombre"] == "La Bombonera de Surquillo"]
    assert len(bomb) == 1 and bomb[0]["id"] == "osm_n3" and bomb[0]["deporte"] == "futbol"
    assert {"osm_w4", "osm_w5", "osm_w13"} <= ids
    assert not ids & {"osm_w6", "osm_w7", "osm_w8", "osm_w9", "osm_w10", "osm_x14"}
    andes = next(c for c in lista if c["id"] == "osm_w13")
    assert andes["pais"] == "BO" and andes["deporte"] == "futbol"
    # Mismo nombre pero LEJOS (> 150 m) = otro local.
    otra = osm.procesar([[-12.12, -77.0, "soccer", "La Bombonera", "lima", "w1", "pitch"],
                         [-12.13, -77.0, "soccer", "La Bombonera", "lima", "w2", "pitch"]])
    assert len(otra) == 2


def test_web_suma_osm_sin_duplicar_google_ni_registradas(monkeypatch):
    _con_datos(monkeypatch)
    llamadas, guardadas = _preparar_google(monkeypatch)
    reg = [{"nombre": "Fútbol 1", "club": "Club Tenis Los Pinos - Sede Sur", "lat": -12.2, "lng": -77.2}]
    r = d.descubrir_cerca(-12.10, -77.00, registradas=reg)
    ids = [c["id"] for c in r]
    assert "gp_Z1" in ids and len(llamadas) == 1
    assert "osm_n3" in ids and "osm_w5" in ids
    assert "osm_w11" not in ids     # mismo nombre que el de Google: gana Google
    assert "osm_w12" not in ids     # a ≤150 m del de Google
    assert "osm_w4" not in ids      # mismo nombre que el club registrado (sin la sede)
    assert "osm_w13" not in ids     # Bolivia: fuera del radio
    o = next(c for c in r if c["id"] == "osm_n3")
    assert o["fuente"] == "osm" and o["fotos"] == [] and o["km"] is not None
    # La cosecha (de Google) nunca recibe filas OSM.
    assert all(c["id"].startswith("gp_") for c in guardadas)
    # Ordenado por distancia.
    assert [c["km"] for c in r] == sorted(c["km"] for c in r)


def test_sin_datos_osm_la_web_queda_igual(monkeypatch):
    _preparar_google(monkeypatch)
    monkeypatch.setattr(osm, "_datos", ("", []))
    sin = d.descubrir_cerca(-12.10, -77.00)
    assert [c["id"] for c in sin] == ["gp_Z1"]
    assert "fuente" not in sin[0]
    # Archivo inexistente → ('', []) sin romper.
    assert osm.cargar("/no/existe.json.gz") == ("", [])


def test_google_conserva_su_tope_y_osm_va_aparte(monkeypatch):
    _con_datos(monkeypatch)
    d.limpiar_cache()
    muchos = [{"id": f"G{i}", "displayName": {"text": f"Complejo Deportivo Num {i}"}, "types": ["sports_complex"],
               "location": {"latitude": -12.10 + i * 0.0005, "longitude": -76.95}} for i in range(70)]
    monkeypatch.setattr(d, "_llamar_edge", lambda *a, **k: muchos)
    monkeypatch.setattr(d, "leer_cosecha", lambda *a, **k: [])
    monkeypatch.setattr(d, "guardar_cosecha", lambda lista: None)
    r = d.descubrir_cerca(-12.10, -76.95)
    assert len([c for c in r if c["id"].startswith("gp_")]) == d.MAX_RESULTADOS
    assert any(c["id"].startswith("osm_") for c in r)


def test_foto_de_un_lugar_osm_nunca_llama_a_google(monkeypatch):
    from main import app

    def _prohibido(*a, **k):
        raise AssertionError("no se debe llamar a Google / la Edge para un lugar OSM")
    monkeypatch.setattr(d, "fotos_de_lugar", _prohibido)
    monkeypatch.setattr(d, "_llamar_edge", _prohibido)
    monkeypatch.setattr(d, "_fotos_directo", _prohibido)
    client = TestClient(app)
    for i in ("osm_w5", "gp_osm_w5"):
        j = client.get(f"/web/foto?id={i}&nombre=Complejo%20Deportivo%20Santa%20Rosa&lat=-12.13&lng=-77.02").json()
        assert j == {"ok": True, "fotos": [], "origen": "osm"}


def test_ficha_de_lugar_osm_con_atribucion_y_sin_foto_de_google():
    from main import app
    client = TestClient(app)
    r = client.get("/lugar/osm_w5?nombre=Complejo%20Deportivo%20Santa%20Rosa&direccion=&lat=-12.13&lng=-77.02&deporte=futbol")
    assert r.status_code == 200
    t = r.text
    assert "openstreetmap.org/copyright" in t and "OpenStreetMap" in t
    assert "/web/foto?" not in t                       # no pide foto
    assert "place=osm_w5" in t                         # "Reclámala" igual que una descubierta
    assert "Cómo llegar" in t or "Indicaciones" in t
    # Un id que no es ni de Google ni de OSM sigue dando 404.
    assert client.get("/lugar/xyz?nombre=A&lat=-12&lng=-77").status_code == 404


def test_explorador_pinta_osm_sin_pedir_foto_y_con_atribucion():
    from main import app
    html = TestClient(app).get("/canchas").text
    assert "c.fuente === 'osm'" in html
    assert "openstreetmap.org/copyright" in html
    assert "indexOf('osm_') === 0" in html


def test_terminos_atribuyen_openstreetmap():
    from main import app
    t = TestClient(app).get("/legal/terminos").text
    assert "OpenStreetMap" in t and "ODbL" in t


class _Cur:
    def __init__(self, db):
        self.db, self.rowcount = db, 0

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        self.db["sql"].append(sql.split()[0])
        if sql.startswith("SELECT count"):
            self._uno = (len(self.db["filas"]),)
        elif sql.startswith("DELETE"):
            vivos = set(params[0])
            antes = len(self.db["filas"])
            self.db["filas"] = {k: v for k, v in self.db["filas"].items() if k in vivos}
            self.rowcount = antes - len(self.db["filas"])

    def executemany(self, sql, filas):
        self.db["lotes"] += 1
        for f in filas:
            self.db["filas"][f[0]] = f

    def fetchone(self):
        return self._uno


class _Conn:
    def __init__(self, db):
        self.db = db

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def cursor(self):
        return _Cur(self.db)

    def commit(self):
        self.db["commits"] += 1


def test_siembra_idempotente_solo_si_vacia_o_cambia_el_archivo(monkeypatch, tmp_path):
    from db import pg
    ruta = tmp_path / "osm.json.gz"
    ruta.write_bytes(gzip.compress(json.dumps(FILAS).encode()))
    db = {"filas": {"osm_viejo": ("osm_viejo",)}, "sql": [], "lotes": 0, "commits": 0}
    monkeypatch.setattr(pg, "habilitado", True)
    monkeypatch.setattr(pg, "_conn", lambda: _Conn(db))
    monkeypatch.setattr(pg, "persistir_en_segundo_plano", lambda st: None)
    stores.config.pop("osm_semilla_version", None)
    try:
        r = osm.sembrar(str(ruta))
        assert r["ok"] and r["motivo"] == "sembrado" and r["borradas"] == 1
        n = len(db["filas"])
        assert n == len(osm.procesar(FILAS)) and "osm_viejo" not in db["filas"]
        assert stores.config["osm_semilla_version"] == osm.version_archivo(str(ruta))
        # Segunda vez, mismo archivo y tabla llena: no escribe nada.
        lotes = db["lotes"]
        r2 = osm.sembrar(str(ruta))
        assert r2["motivo"] == "al_dia" and db["lotes"] == lotes
        # Tabla vacía (p. ej. la borraron): vuelve a sembrar aunque la versión coincida.
        db["filas"] = {}
        assert osm.sembrar(str(ruta))["motivo"] == "sembrado" and len(db["filas"]) == n
        # Archivo distinto → nueva versión → re-siembra.
        ruta.write_bytes(gzip.compress(json.dumps(FILAS[:5]).encode()))
        r3 = osm.sembrar(str(ruta))
        assert r3["motivo"] == "sembrado" and len(db["filas"]) == len(osm.procesar(FILAS[:5]))
    finally:
        stores.config.pop("osm_semilla_version", None)


def test_archivo_real_de_osm_se_procesa():
    """El archivo que viaja en el repo (12 ciudades de PE, EC y BO) carga,
    filtra y deja locales en los 3 países, todos con deporte de Pichangol."""
    version, lista = osm.cargar(osm.ARCHIVO)
    if not version:  # sin el archivo (otro checkout): nada que probar
        return
    assert len(lista) > 1000
    assert {c["pais"] for c in lista} == {"PE", "EC", "BO"}
    assert {c["deporte"] for c in lista} <= {"futbol", "tenis", "padel", "pickleball", "voley", "basquet"}
    assert all(c["id"].startswith("osm_") and osm.nombre_util(c["nombre"]) for c in lista)
    assert len({c["id"] for c in lista}) == len(lista)


def test_sin_base_la_siembra_no_hace_nada(monkeypatch):
    from db import pg
    monkeypatch.setattr(pg, "habilitado", False)
    assert osm.sembrar() == {"ok": False, "motivo": "sin_base"}
