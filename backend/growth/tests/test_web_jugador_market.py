"""Marketplace, Mis compras y Mis bonos del JUGADOR en la web = mismas
pantallas y misma contabilidad que el APK (marketplace_screen,
producto_detalle_screen, mis_ordenes_screen, mis_bonos_screen, _SeccionBonos)."""
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

import config
from db.store import Venta, stores
from main import app
from pagos import culqi
from pagos import router as pr
from web import datos, sesion
from web import jugador_market as jm

AHORA = datetime.now(timezone.utc).isoformat()


def _prod(**kw):
    p = {"id": "prod_1_w", "vendedor_email": "vende@x.com", "vendedor_nombre": "Tienda Raqueta", "nombre": "Raqueta Wilson",
         "descripcion": "Nueva, con funda.", "precio": 120.0, "moneda": "S/", "categoria": "raquetas", "foto_url": "https://img/r.jpg",
         "stock": 2, "activo": True, "creado_en": AHORA}
    p.update(kw)
    return p


def _cli(monkeypatch, email="ana@gmail.com"):
    monkeypatch.setattr(config, "GOOGLE_WEB_CLIENT_ID", "cid-web")
    cli = TestClient(app, base_url="https://testserver")
    cli.cookies.set(sesion.COOKIE, sesion.emitir({"email": email, "nombre": "Ana Pérez", "foto": ""}))
    return cli


@pytest.fixture(autouse=True)
def _limpio(monkeypatch):
    antes_v, antes_p = list(stores.ventas), list(stores.pagos)
    monkeypatch.setattr(config, "CULQI_PUBLIC_KEY", "pk_test_x")
    monkeypatch.setattr(jm, "perfiles", lambda es: {"vende@x.com": {"nombre": "Tienda", "foto_url": "", "celular": "987654321"}})
    monkeypatch.setattr(datos, "celular_de_perfil", lambda e: "999888777")
    yield
    stores.ventas[:] = antes_v
    stores.pagos[:] = antes_p


def test_feed_con_categorias_presentes_moneda_stock_y_verificado(monkeypatch):
    prods = [_prod(), _prod(id="p2", nombre="Pelotas Head", categoria="pelotas", precio=30, moneda="Bs", stock=0,
                            vendedor_email="otro@x.com", vendedor_nombre="Otro"),
             _prod(id="p3", nombre="Polo", categoria="indumentaria", precio=15, moneda="$", stock=None)]
    monkeypatch.setattr(jm, "productos_activos", lambda: prods)
    monkeypatch.setattr(jm, "verificados", lambda es: {"vende@x.com"})
    html = TestClient(app).get("/marketplace").text
    assert "Marketplace Pichangol" in html and "href='/anfitrion/tienda'" in html and "href='/mis-ordenes'" in html
    assert "S/ 120.00" in html and "Bs 30.00" in html and "$ 15.00" in html
    assert "Quedan 2" in html and "Agotado" in html
    assert html.count("class='vok'") == 2  # solo los del vendedor verificado (2 de 3)
    # Solo las categorías presentes (como el app) + "Todo".
    assert "data-cat='raquetas'>" in html and "data-cat='calzado'" not in html and ">Todo<" in html
    assert "confirm(" not in html.split("mkQ")[1] and "alert(" not in html.split("mkQ")[1]


def test_feed_vacio(monkeypatch):
    monkeypatch.setattr(jm, "productos_activos", lambda: [])
    monkeypatch.setattr(jm, "verificados", lambda es: set())
    assert "Aún no hay productos" in TestClient(app).get("/marketplace").text


def test_ficha_producto_estados(monkeypatch):
    monkeypatch.setattr(datos, "esta_verificado", lambda e: True)
    monkeypatch.setattr(jm, "producto", lambda pid: _prod())
    html = _cli(monkeypatch).get("/marketplace/prod_1_w").text
    assert "Comprar · S/ 120.00" in html and "Vendedor verificado ✓" in html and "pcgResumenPago" in html
    assert "checkout.culqi.com" in html and "id='medioPago'" in html
    # El vendedor no puede comprarse a sí mismo.
    html = _cli(monkeypatch, "vende@x.com").get("/marketplace/prod_1_w").text
    assert "Este producto es tuyo" in html and "data-pagar" not in html
    # Otra moneda → a la app.
    monkeypatch.setattr(jm, "producto", lambda pid: _prod(moneda="$"))
    assert "Cómpralo en la app" in _cli(monkeypatch).get("/marketplace/prod_1_w").text
    # Agotado.
    monkeypatch.setattr(jm, "producto", lambda pid: _prod(stock=0))
    html = _cli(monkeypatch).get("/marketplace/prod_1_w").text
    assert "Agotado" in html and "data-pagar" not in html
    # Pausado: 404 para los demás.
    monkeypatch.setattr(jm, "producto", lambda pid: _prod(activo=False))
    assert "Producto no disponible" in _cli(monkeypatch).get("/marketplace/prod_1_w").text


def test_comprar_registra_venta_como_el_app(monkeypatch):
    monkeypatch.setattr(jm, "producto", lambda pid: _prod())
    apartados, devueltos, cargos, pushes = [], [], [], []
    monkeypatch.setattr(jm, "apartar_unidad", lambda pid: apartados.append(pid) or True)
    monkeypatch.setattr(jm, "devolver_unidad", lambda pid: devueltos.append(pid))
    monkeypatch.setattr(culqi, "crear_cargo", lambda **kw: cargos.append(kw) or {"ok": True, "charge_id": "chr_mk1"})
    monkeypatch.setattr(pr, "_aviso_push_usuario", lambda email, titulo, cuerpo, tipo="aviso": pushes.append((email, titulo, tipo)))
    cli = _cli(monkeypatch)
    # Sin sesión → exige login.
    r = TestClient(app).post("/web/marketplace/comprar", json={"producto_id": "prod_1_w", "token": "tkn"})
    assert r.json()["error"] == "sesion_requerida"
    r = cli.post("/web/marketplace/comprar", json={"producto_id": "prod_1_w", "token": "tkn_1", "medio": "yape"}).json()
    assert r["ok"] and r["charge_id"] == "chr_mk1" and r["url"].startswith("/mis-ordenes?nueva=")
    assert apartados == ["prod_1_w"] and not devueltos
    k = cargos[0]
    assert k["monto_centimos"] == 12000 and k["moneda"] == "PEN" and k["email"] == "ana@gmail.com"
    assert k["cliente"]["telefono"] == "999888777" and k["cliente"]["nombre"] == "Ana Pérez"
    venta = next(p for p in stores.pagos if p.tipo == "venta_producto" and p.culqi_charge_id == "chr_mk1")
    assert venta.monto_centimos == 12000 and venta.dueno_id == "vende@x.com" and venta.moneda == "PEN"
    assert any(p.tipo == "cobro_web" and p.concepto == "venta:prod_1_w" for p in stores.pagos)
    orden = stores.ventas[-1]
    assert orden.estado == "pagado" and orden.comprador_email == "ana@gmail.com" and orden.producto_id == "prod_1_w"
    assert pushes == [("vende@x.com", "¡Te compraron! 🛍️", "venta")]


def test_comprar_rechazos(monkeypatch):
    monkeypatch.setattr(jm, "producto", lambda pid: _prod())
    devueltos = []
    monkeypatch.setattr(jm, "apartar_unidad", lambda pid: True)
    monkeypatch.setattr(jm, "devolver_unidad", lambda pid: devueltos.append(pid))
    monkeypatch.setattr(culqi, "crear_cargo", lambda **kw: {"ok": False, "error": "tarjeta_rechazada"})
    r = _cli(monkeypatch).post("/web/marketplace/comprar", json={"producto_id": "prod_1_w", "token": "t"}).json()
    assert r["error"] == "cargo_rechazado" and devueltos == ["prod_1_w"]  # la unidad vuelve al stock
    # Propio producto.
    r = _cli(monkeypatch, "vende@x.com").post("/web/marketplace/comprar", json={"producto_id": "prod_1_w", "token": "t"}).json()
    assert r["error"] == "propio"
    # Se agotó en carrera: no se cobra.
    monkeypatch.setattr(jm, "apartar_unidad", lambda pid: False)
    llamado = []
    monkeypatch.setattr(culqi, "crear_cargo", lambda **kw: llamado.append(1) or {"ok": True, "charge_id": "x"})
    r = _cli(monkeypatch).post("/web/marketplace/comprar", json={"producto_id": "prod_1_w", "token": "t"}).json()
    assert r["error"] == "agotado" and not llamado
    # Otra moneda.
    monkeypatch.setattr(jm, "producto", lambda pid: _prod(moneda="Bs"))
    assert _cli(monkeypatch).post("/web/marketplace/comprar", json={"producto_id": "prod_1_w", "token": "t"}).json()["error"] == "moneda"


def test_mis_ordenes_confirmar_y_disputar(monkeypatch):
    monkeypatch.setattr(config, "GOOGLE_WEB_CLIENT_ID", "cid-web")
    r = TestClient(app).get("/mis-ordenes", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == "/entrar?volver=%2Fmis-ordenes"
    monkeypatch.setattr(jm, "productos_por_ids", lambda ids: {"prod_1_w": _prod()})
    ahora = datetime.now(timezone.utc)
    stores.ventas.append(Venta(id=9901, producto_id="prod_1_w", producto_nombre="Raqueta Wilson", comprador_email="ana@gmail.com",
                               comprador_nombre="Ana", vendedor_email="vende@x.com", vendedor_nombre="Tienda", monto_soles=120.0,
                               creado_en=ahora))
    stores.ventas.append(Venta(id=9902, producto_id="p9", producto_nombre="Ajena", comprador_email="otro@x.com",
                               comprador_nombre="Otro", vendedor_email="vende@x.com", vendedor_nombre="Tienda", monto_soles=10.0,
                               creado_en=ahora))
    pushes = []
    monkeypatch.setattr(pr, "_aviso_push_usuario", lambda email, titulo, cuerpo, tipo="aviso": pushes.append((email, titulo)))
    cli = _cli(monkeypatch)
    html = cli.get("/mis-ordenes?nueva=9901").text
    assert "Raqueta Wilson" in html and "Ajena" not in html and "Pagado · retenido" in html
    assert "¡Compra realizada! ✓" in html and "Confirmar recepción" in html
    assert "wa.me/51987654321" in html  # WhatsApp del vendedor con prefijo del país
    # No puedo tocar una orden ajena.
    assert cli.post("/web/ordenes/9902/recibido").json()["error"] == "no_encontrada"
    r = cli.post("/web/ordenes/9901/problema").json()
    assert r["ok"] and r["estado"] == "disputado" and pushes[-1] == ("vende@x.com", "Problema con una venta ⚠️")
    stores.ventas[-2].estado = "entregado"
    r = cli.post("/web/ordenes/9901/recibido").json()
    assert r["ok"] and r["estado"] == "recibido" and pushes[-1] == ("vende@x.com", "Pago liberado ✅")
    assert "Completado · liberado" in cli.get("/mis-ordenes").text


def _cancha(**kw):
    c = {"id": "c1", "club": "Club Raqueta", "dueno": "dueno@x.com", "moneda": "S/", "lat": -12.1, "lng": -77.0,
         "precio_hora": 50.0, "verificada": True, "eliminada": False}
    c.update(kw)
    return c


def test_mis_bonos_y_compra_de_bono_como_el_app(monkeypatch):
    oferta = {"id": "of1", "dueno": "dueno@x.com", "club": "Club Raqueta", "nombre": "", "horas": 10, "precio": 400.0, "activo": True}
    registrados = []
    comprados = [{"id": "bono_chr_old", "bono_id": "of1", "dueno": "dueno@x.com", "club": "Club Raqueta", "comprador": "ana@gmail.com",
                  "comprador_nombre": "Ana", "horas_total": 10, "horas_usadas": 3, "precio": 400.0, "venta_id": "chr_old", "saldo": 7}]
    monkeypatch.setattr(datos, "cancha", lambda cid: _cancha())
    monkeypatch.setattr(jm, "ofertas_de_local", lambda club, dueno: [oferta])
    monkeypatch.setattr(jm, "oferta", lambda oid: dict(oferta))
    monkeypatch.setattr(jm, "bonos_de", lambda e: comprados)
    monkeypatch.setattr(jm, "canchas_de_locales", lambda pares: {("Club Raqueta", "dueno@x.com"): {"id": "c1", "moneda": "S/", "lat": -12.1, "lng": -77.0}})
    monkeypatch.setattr(jm, "registrar_bono", lambda fila: registrados.append(fila) or True)
    pushes = []
    monkeypatch.setattr(pr, "_aviso_push_usuario", lambda email, titulo, cuerpo, tipo="aviso": pushes.append((email, titulo, tipo)))
    monkeypatch.setattr(culqi, "crear_cargo", lambda **kw: {"ok": True, "charge_id": "chr_b1"})
    cli = _cli(monkeypatch)
    html = cli.get("/mis-bonos").text
    assert "Club Raqueta" in html and "Compraste 10 h · S/ 400.00" in html and "Te quedan 7 h" in html and "Usaste 3 de 10 h" in html
    assert "href='/bonos/c1'" in html
    html = cli.get("/bonos/c1").text
    assert "Tienes 7 horas de bono en este local" in html and "S/ 40.00/hora · ahorras 20 %" in html and "data-oferta='of1'" in html
    r = cli.post("/web/bonos/comprar", json={"cancha_id": "c1", "oferta_id": "of1", "token": "tkn"}).json()
    assert r["ok"] and r["url"] == "/mis-bonos?nuevo=bono_chr_b1"
    f = registrados[0]
    assert f["id"] == "bono_chr_b1" and f["comprador"] == "ana@gmail.com" and f["horas_total"] == 10 and f["venta_id"] == "chr_b1"
    venta = next(p for p in stores.pagos if p.tipo == "venta_producto" and p.culqi_charge_id == "chr_b1")
    assert venta.dueno_id == "dueno@x.com" and venta.monto_centimos == 40000
    assert pushes == [("dueno@x.com", "¡Vendiste un bono! 🎟️", "bono")]
    # El dueño no compra su propio bono; un local en Bs va a la app.
    assert _cli(monkeypatch, "dueno@x.com").post("/web/bonos/comprar", json={"cancha_id": "c1", "oferta_id": "of1", "token": "t"}).json()["error"] == "propio"
    monkeypatch.setattr(datos, "cancha", lambda cid: _cancha(moneda="Bs", lat=-16.5, lng=-68.1))
    assert cli.post("/web/bonos/comprar", json={"cancha_id": "c1", "oferta_id": "of1", "token": "t"}).json()["error"] == "moneda"
    assert "Bs 400.00" in cli.get("/bonos/c1").text


def test_mis_bonos_vacio_y_sin_sesion(monkeypatch):
    monkeypatch.setattr(config, "GOOGLE_WEB_CLIENT_ID", "cid-web")
    r = TestClient(app).get("/mis-bonos", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == "/entrar?volver=%2Fmis-bonos"
    monkeypatch.setattr(jm, "bonos_de", lambda e: [])
    monkeypatch.setattr(jm, "canchas_de_locales", lambda pares: {})
    assert "Aún no tienes bonos" in _cli(monkeypatch).get("/mis-bonos").text
