"""MI BODEGA en la web = `bodega_screen.dart` (dueño) + `pedir_bodega_screen.dart`
(jugador): mismas tablas, mismos candados de concurrencia y la MISMA
contabilidad del backend para el prepago con saldo (`/pagos/bodega-pago` y
`/pagos/bodega-reembolso`)."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

import config
from db.store import stores
from main import app
from web import anfitrion_bodega as ab
from web import bodega_datos as bd
from web import datos, jugador_bodega as jb, sesion

DUENO = "dueno@gmail.com"
JUGADOR = "ana@gmail.com"
LIMA = {"id": "c1", "nombre": "Fútbol 1", "club": "Sabor Golazo", "dueno": DUENO, "verificada": True,
        "lat": -12.1, "lng": -77.0, "moneda": "S/"}


class Fake:
    """Las 5 tablas de la bodega en memoria, con los MISMOS candados que el SQL."""

    def __init__(self):
        self.prods, self.ventas, self.pedidos, self.cuentas, self.cfg = {}, [], {}, {}, {}

    def instalar(self, mp):
        def productos_de(d):
            return sorted([dict(p) for p in self.prods.values() if p["dueno"] == d.lower() and not p.get("eliminado")],
                          key=lambda p: (p["categoria"], p["nombre"]))

        def guardar_producto(p):
            if p["id"] in self.prods and self.prods[p["id"]]["dueno"] != p["dueno"]:
                return False
            self.prods[p["id"]] = dict(p)
            return True

        def eliminar_producto(pid, d):
            p = self.prods.get(pid)
            if not p or p["dueno"] != d:
                return False
            p["eliminado"] = True
            return True

        def _desc(des, d):
            for pid, n in des.items():
                if pid in self.prods and self.prods[pid]["dueno"] == d:
                    self.prods[pid]["stock"] = max(0, self.prods[pid]["stock"] - n)

        def registrar_venta(v, des):
            self.ventas.append(dict(v, creado=bd.ahora()))
            _desc(des, v["dueno"])
            return True

        def cambiar_estado_si(pid, nuevo, *, desde, dueno="", cliente=""):
            p = self.pedidos.get(pid)
            if not p or (dueno and p["dueno"] != dueno) or (cliente and p["cliente"] != cliente):
                return False, None
            if p["estado"] != desde:
                return False, p["estado"]
            p["estado"] = nuevo
            return True, None

        def cuenta_abierta(c, d):
            return next((dict(x) for x in self.cuentas.values() if x["cliente"] == c and x["dueno"] == d and x["estado"] == "abierta"), None)

        def anotar(*, dueno, cliente, cliente_nombre, items, moneda):
            ab_ = cuenta_abierta(cliente, dueno)
            if ab_ is None:
                cid = bd.nuevo_id("bc")
                self.cuentas[cid] = {"id": cid, "dueno": dueno, "cliente": cliente, "cliente_nombre": cliente_nombre,
                                     "items": list(items), "total": bd.total_items(items), "moneda": moneda,
                                     "estado": "abierta", "medio_pago": "", "creado": bd.ahora()}
                return dict(self.cuentas[cid])
            x = self.cuentas[ab_["id"]]
            x["items"] = x["items"] + list(items)
            x["total"] = round(x["total"] + bd.total_items(items), 2)
            return dict(x)

        def cerrar(cid, medio, d):
            x = self.cuentas.get(cid)
            if not x or x["estado"] != "abierta" or x["dueno"] != d:
                return False
            x.update(estado="cerrada", medio_pago=medio)
            return True

        mp.setattr(bd, "productos_de", productos_de)
        mp.setattr(bd, "guardar_producto", guardar_producto)
        mp.setattr(bd, "poner_foto", lambda pid, d, url: self.prods[pid].update(foto_url=url) or True)
        mp.setattr(bd, "eliminar_producto", eliminar_producto)
        mp.setattr(bd, "registrar_venta", registrar_venta)
        mp.setattr(bd, "descontar_stock", lambda des, d: _desc(des, d) or True)
        mp.setattr(bd, "ventas_de", lambda d, dias=30: [v for v in reversed(self.ventas) if v["dueno"] == d])
        mp.setattr(bd, "config_de", lambda d: dict(self.cfg.get(d) or bd.config_defecto(d)))
        mp.setattr(bd, "guardar_config", lambda c: self.cfg.__setitem__(c["dueno"], dict(c)) or True)
        mp.setattr(bd, "crear_pedido", lambda p: self.pedidos.__setitem__(p["id"], dict(p, creado=bd.ahora())) or True)
        mp.setattr(bd, "pedidos_de_dueno", lambda d: [dict(p) for p in self.pedidos.values() if p["dueno"] == d])
        mp.setattr(bd, "pedidos_de_cliente", lambda c, dueno="", dias=30: [
            dict(p) for p in self.pedidos.values() if p["cliente"] == c and (not dueno or p["dueno"] == dueno)])
        mp.setattr(bd, "pedido", lambda pid: dict(self.pedidos[pid]) if pid in self.pedidos else None)
        mp.setattr(bd, "cambiar_estado_si", cambiar_estado_si)
        mp.setattr(bd, "forzar_estado", lambda pid, est, d: self.pedidos[pid].update(estado=est) or True)
        mp.setattr(bd, "cuentas_de", lambda d: [dict(x) for x in self.cuentas.values() if x["dueno"] == d])
        mp.setattr(bd, "cuenta_abierta", cuenta_abierta)
        mp.setattr(bd, "cuentas_abiertas_cliente", lambda c: [dict(x) for x in self.cuentas.values() if x["cliente"] == c and x["estado"] == "abierta"])
        mp.setattr(bd, "anotar_a_cuenta", anotar)
        mp.setattr(bd, "cerrar_cuenta_si", cerrar)
        mp.setattr(bd, "cuenta_de", lambda cid, d: dict(self.cuentas[cid]) if cid in self.cuentas and self.cuentas[cid]["dueno"] == d else None)
        mp.setattr(bd, "clientes_registrados", lambda d, hoy=None: [{"email": JUGADOR, "nombre": "Ana Pérez", "hoy": True}])
        mp.setattr(bd, "locales_de", lambda ds: {DUENO: {"cancha_id": "c1", "club": "Sabor Golazo", "lat": -12.1, "lng": -77.0}})

    def producto(self, pid, nombre, precio, stock, cat="Cervezas", stock_min=2, moneda="S/"):
        self.prods[pid] = {"id": pid, "dueno": DUENO, "carta_id": bd.carta_id_de(DUENO), "nombre": nombre, "categoria": cat,
                           "precio": precio, "stock": stock, "stock_min": stock_min, "foto_url": "", "moneda": moneda}


@pytest.fixture
def fk(monkeypatch):
    f = Fake()
    f.instalar(monkeypatch)
    avisos = []
    monkeypatch.setattr(ab, "_en_fondo", lambda fn, *a: fn(*a))
    import web.jugador_liga as jl
    monkeypatch.setattr(jl, "aviso_push", lambda email, t, c, tipo="aviso", data=None: avisos.append((email, t, c, tipo, data)))
    monkeypatch.setattr(datos, "cancha", lambda cid: dict(LIMA) if cid == "c1" else None)
    monkeypatch.setattr(datos, "canchas_de_dueno", lambda e: [dict(LIMA)] if e == DUENO else [])
    monkeypatch.setattr(ab.packshot_svc, "disponible", lambda: False)
    f.avisos = avisos
    antes = (list(stores.pagos), dict(stores.saldos), dict(stores.membresias_pro))
    stores.membresias_pro[DUENO] = {"hasta": "2099-01-01T00:00:00+00:00"}
    yield f
    stores.pagos[:] = antes[0]
    stores.saldos.clear(); stores.saldos.update(antes[1])
    stores.membresias_pro.clear(); stores.membresias_pro.update(antes[2])


def _cli(monkeypatch, email):
    monkeypatch.setattr(config, "GOOGLE_WEB_CLIENT_ID", "cid-web")
    cli = TestClient(app, base_url="https://testserver")
    cli.cookies.set(sesion.COOKIE, sesion.emitir({"email": email, "nombre": "Ana Pérez" if email == JUGADOR else "Dueño", "foto": ""}))
    return cli


def test_carta_id_espejo_del_app():
    # FNV-1a de 32 bits x2 (seed 0 y 0x9e3779b9) sobre las unidades UTF-16, como BodegaRepo.cartaIdDe.
    def ref(s):
        def fnv(seed):
            h = (0x811C9DC5 ^ seed) & 0xFFFFFFFF
            for ch in s.encode("utf-16-le")[::2]:
                h = ((h ^ ch) * 0x01000193) & 0xFFFFFFFF
            return h
        return "b" + (f"{fnv(0):08x}{fnv(0x9E3779B9):08x}")[:12]
    assert bd.carta_id_de("  Dueno@Gmail.com ") == ref("dueno@gmail.com")
    assert len(bd.carta_id_de("x@y.pe")) == 13 and bd.carta_id_de("x@y.pe").startswith("b")


def test_sin_sesion_y_candado_pro(monkeypatch, fk):
    monkeypatch.setattr(config, "GOOGLE_WEB_CLIENT_ID", "cid-web")
    r = TestClient(app, base_url="https://testserver").get("/anfitrion/bodega", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == "/entrar?volver=%2Fanfitrion%2Fbodega"
    stores.membresias_pro.pop(DUENO)
    html = _cli(monkeypatch, DUENO).get("/anfitrion/bodega").text
    assert "Administra tu bodega" in html and "Activar con Pichangol Pro" in html and "bTicket" not in html
    r = _cli(monkeypatch, DUENO).post("/anfitrion/bodega/producto", json={"nombre": "Pilsen", "precio": 7})
    assert r.status_code == 402 and r.json()["requiere_pro"]


def test_productos_caja_reporte_y_carta(monkeypatch, fk):
    cli = _cli(monkeypatch, DUENO)
    html = cli.get("/anfitrion/bodega").text
    assert "Arma tu bodega en 2 minutos" in html
    for js in (ab.JS, jb.JS):  # nunca diálogos nativos del navegador
        assert not any(x in js.replace("pcgConfirmar(", "") for x in ("confirm(", "alert(", "prompt("))
    # Sugerencias POR PAÍS (Perú: Pilsen, Inca Kola) y carta con QR.
    assert "Pilsen" in html and "Inca Kola" in html and "Paceña" not in html
    assert f"/b/{bd.carta_id_de(DUENO)}/qr.png" in html
    assert cli.post("/anfitrion/bodega/producto", json={"nombre": "", "precio": 5}).json()["error"] == "Ponle nombre al producto."
    assert cli.post("/anfitrion/bodega/producto", json={"nombre": "Pilsen", "precio": 0}).json()["error"] == "Ponle el precio de venta."
    r = cli.post("/anfitrion/bodega/producto", json={"nombre": "Pilsen", "categoria": "Cervezas", "precio": "7,5", "stock": 5, "stock_min": 2}).json()
    assert r["ok"] and r["id"].startswith("bp_")
    p = fk.prods[r["id"]]
    assert p["precio"] == 7.5 and p["moneda"] == "S/" and p["carta_id"] == bd.carta_id_de(DUENO)
    fk.producto("agua", "Agua San Luis", 2.5, 10, cat="Bebidas")
    html = cli.get("/anfitrion/bodega?tab=caja").text
    assert "S/ 7.50" in html and "Stock: 5" in html and "data-cat='Cervezas'" in html
    # Vender: precio del SERVIDOR, stock descontado y alerta de reposición.
    j = cli.post("/anfitrion/bodega/vender", json={"items": [{"id": r["id"], "cantidad": 3}, {"id": "agua", "cantidad": 1}], "medio": "yape"}).json()
    assert j["ok"] and "Repón: Pilsen (2)" in j["mensaje"]
    assert fk.prods[r["id"]]["stock"] == 2 and fk.ventas[-1]["total"] == 25.0 and fk.ventas[-1]["medio_pago"] == "yape"
    # No se vende más de lo que hay; cortesía registra total 0.
    assert "Solo te quedan 2 de Pilsen" in cli.post("/anfitrion/bodega/vender", json={"items": [{"id": r["id"], "cantidad": 3}], "medio": "efectivo"}).json()["error"]
    assert cli.post("/anfitrion/bodega/vender", json={"items": [{"id": "agua", "cantidad": 1}], "medio": "cortesia"}).json()["ok"]
    assert fk.ventas[-1]["total"] == 0
    rep = cli.get("/anfitrion/bodega?tab=reporte").text
    assert "S/ 25.00" in rep and "Para reponer" in rep and "Pilsen — 3 und." in rep and "<b>2</b>" in rep
    # Producto ajeno no se edita.
    fk.prods["ajeno"] = dict(fk.prods["agua"], id="ajeno", dueno="otro@x.com")
    assert cli.post("/anfitrion/bodega/producto", json={"id": "ajeno", "nombre": "X", "precio": 1}).status_code == 404
    assert cli.post(f"/anfitrion/bodega/producto/{r['id']}/eliminar").json()["ok"] and fk.prods[r["id"]]["eliminado"]


def test_pedido_a_la_cancha_con_gps_zona_y_entrega(monkeypatch, fk):
    fk.producto("pil", "Pilsen", 7, 10)
    jug, due = _cli(monkeypatch, JUGADOR), _cli(monkeypatch, DUENO)
    base = {"cancha_id": "c1", "zona": "Cancha 2", "items": [{"id": "pil", "cantidad": 2}], "lat": -12.1005, "lng": -77.0005}
    # Sin "Acepto pedidos": se ve la carta sin +/-.
    html = jug.get("/bodega/c1/pedir").text
    assert "Este local aún no recibe pedidos" in html and "data-mas" not in html
    assert jug.post("/web/bodega/pedir", json=base).status_code == 409
    assert due.post("/anfitrion/bodega/config", json={"acepta_pedidos": True}).json()["ok"]
    html = jug.get("/bodega/c1/pedir").text
    assert "Toca para agregar a tu pedido" in html and "data-mas='pil'" in html and "navigator.geolocation" in html
    # GPS obligatorio y a ≤ 250 m; zona de la lista del dueño.
    assert jug.post("/web/bodega/pedir", json=dict(base, lat=None)).json()["error"].startswith("Activa tu ubicación")
    assert jug.post("/web/bodega/pedir", json=dict(base, lat=-12.2)).json().get("lejos")
    assert jug.post("/web/bodega/pedir", json=dict(base, zona="Techo")).status_code == 400
    assert "Solo quedan 10" in jug.post("/web/bodega/pedir", json=dict(base, items=[{"id": "pil", "cantidad": 11}])).json()["error"]
    j = jug.post("/web/bodega/pedir", json=base).json()
    assert j["ok"]
    p = fk.pedidos[j["id"]]
    assert p["total"] == 14 and p["zona"] == "Cancha 2" and not p["pagado"] and p["cliente_nombre"] == "Ana Pérez"
    assert fk.avisos[-1][0] == DUENO and fk.avisos[-1][1] == "🧃 Pedido a la Cancha 2" and fk.avisos[-1][4] == {"destino": "dueno"}
    # El dueño ve el pedido pendiente (badge) y confirma; el cliente ya no puede cancelar.
    html = due.get("/anfitrion/bodega?tab=pedidos").text
    assert "🛎️ Pedidos (1)" in html and "Confirmar ✅" in html
    assert due.post(f"/anfitrion/bodega/pedido/{j['id']}/responder", json={"confirmar": True}).json()["ok"]
    assert fk.avisos[-1][1] == "Pedido confirmado 🏃" and fk.avisos[-1][4] == {"destino": "cliente", "dueno": DUENO}
    r = jug.post(f"/web/bodega/pedido/{j['id']}/cancelar").json()
    assert not r["ok"] and r["aviso"]["titulo"] == "Ya va en camino 🏃"
    assert "En camino" in jug.get("/bodega/c1/pedir").text
    # Entregar y cobrar: RECLAMA el pedido (dos equipos → una sola venta).
    assert due.post(f"/anfitrion/bodega/pedido/{j['id']}/entregar", json={"medio": "efectivo"}).json()["ok"]
    assert fk.prods["pil"]["stock"] == 8 and len(fk.ventas) == 1
    r2 = due.post(f"/anfitrion/bodega/pedido/{j['id']}/entregar", json={"medio": "efectivo"}).json()
    assert r2["aviso"]["titulo"] == "Ya estaba cobrado" and len(fk.ventas) == 1
    # Un pendiente que el cliente canceló primero: el dueño se entera.
    j2 = jug.post("/web/bodega/pedir", json=base).json()
    assert jug.post(f"/web/bodega/pedido/{j2['id']}/cancelar").json()["ok"]
    assert due.post(f"/anfitrion/bodega/pedido/{j2['id']}/responder", json={"confirmar": True}).json()["aviso"]["titulo"] == "El cliente lo canceló"
    # El dueño en su propia bodega → a Mi bodega; otro cliente no cancela lo ajeno.
    assert "Esta es tu bodega" in due.get("/bodega/c1/pedir").text
    assert _cli(monkeypatch, "eva@x.com").post(f"/web/bodega/pedido/{j2['id']}/cancelar").status_code == 404
    mis = jug.get("/mis-pedidos-bodega").text
    assert "Pedidos anteriores" in mis and "Sabor Golazo" in mis and "/bodega/c1/pedir" in mis


def test_prepago_con_saldo_verificado_y_reembolso(monkeypatch, fk):
    fk.producto("pil", "Pilsen", 7, 10)
    fk.cfg[DUENO] = dict(bd.config_defecto(DUENO), acepta_pedidos=True)
    stores.acreditar(JUGADOR, 2000)  # S/ 20
    jug, due = _cli(monkeypatch, JUGADOR), _cli(monkeypatch, DUENO)
    base = {"cancha_id": "c1", "zona": "Mesa", "items": [{"id": "pil", "cantidad": 2}], "lat": -12.1, "lng": -77.0, "con_saldo": True}
    j = jug.post("/web/bodega/pedir", json=base).json()
    assert j["ok"] and fk.pedidos[j["id"]]["pagado"]
    assert stores.saldo_centimos(JUGADOR) == 600
    venta = stores.pago_por_charge(f"bod_{j['id']}")
    assert venta.tipo == "venta_bodega" and venta.dueno_id == DUENO and venta.monto_centimos == 1400 and venta.comision_centimos == 0
    assert venta.moneda == "PEN"
    assert fk.avisos[-1][1] == "💳 Pedido PAGADO a la Mesa"
    # Saldo insuficiente → pedido cancelado y NADA cobrado.
    r = jug.post("/web/bodega/pedir", json=dict(base, items=[{"id": "pil", "cantidad": 1}])).json()
    assert not r["ok"] and r.get("saldo_insuficiente") and stores.saldo_centimos(JUGADOR) == 600
    # Rechazar un prepagado → reembolso automático (misma función del backend).
    assert due.post(f"/anfitrion/bodega/pedido/{j['id']}/responder", json={"confirmar": False}).json()["ok"]
    assert stores.saldo_centimos(JUGADOR) == 2000 and venta.estado == "anulado"
    assert fk.avisos[-1][2].endswith("Tu saldo se devuelve solo 💸")
    # Otro prepagado: entregar verifica el pago y registra venta con medio 'saldo' + puntos.
    j2 = jug.post("/web/bodega/pedir", json=base).json()
    assert due.post(f"/anfitrion/bodega/pedido/{j2['id']}/responder", json={"confirmar": True}).json()["ok"]
    html = due.get("/anfitrion/bodega?tab=pedidos").text
    assert "PAGADO con saldo Pichangol" in html and "ya pagado con saldo" in html
    assert due.post(f"/anfitrion/bodega/pedido/{j2['id']}/entregar", json={}).json()["ok"]
    assert fk.ventas[-1]["medio_pago"] == "saldo" and fk.ventas[-1]["total"] == 14
    assert [a[1] for a in fk.avisos[-2:]] == ["Pedido entregado ✅", "¡Te llegaron puntos! ⭐"] and fk.avisos[-1][3] == "puntos"
    # Cancelar un prepagado pendiente devuelve el saldo.
    stores.acreditar(JUGADOR, 1400)
    j3 = jug.post("/web/bodega/pedir", json=base).json()
    assert "te devolvimos S/ 14.00" in jug.post(f"/web/bodega/pedido/{j3['id']}/cancelar").json()["mensaje"]
    # Pago que el backend no confirma → no se entrega "sin cobrar".
    fk.pedidos["falso"] = dict(fk.pedidos[j3["id"]], id="falso", estado="confirmado", pagado=True)
    assert due.post("/anfitrion/bodega/pedido/falso/entregar", json={}).json()["aviso"]["titulo"] == "Pago no confirmado"


def test_saldo_en_otra_moneda_no_paga_la_bodega(monkeypatch, fk):
    fk.producto("pil", "Paceña", 15, 10, moneda="Bs")
    fk.cfg[DUENO] = dict(bd.config_defecto(DUENO), acepta_pedidos=True)
    stores.acreditar(JUGADOR, 10000)
    r = _cli(monkeypatch, JUGADOR).post("/web/bodega/pedir", json={"cancha_id": "c1", "zona": "Mesa", "items": [{"id": "pil", "cantidad": 1}],
                                                                   "lat": -12.1, "lng": -77.0, "con_saldo": True}).json()
    assert not r["ok"] and r["saldo_insuficiente"] and stores.saldo_centimos(JUGADOR) == 10000


def test_cuenta_abierta_tope_y_cierre(monkeypatch, fk):
    fk.producto("pil", "Pilsen", 30, 20)
    fk.cfg[DUENO] = dict(bd.config_defecto(DUENO), acepta_pedidos=True)
    due, jug = _cli(monkeypatch, DUENO), _cli(monkeypatch, JUGADOR)
    ticket = {"items": [{"id": "pil", "cantidad": 2}], "medio": "cuenta", "cliente": JUGADOR}
    assert due.post("/anfitrion/bodega/vender", json=ticket).status_code == 409  # cuenta abierta apagada
    assert due.post("/anfitrion/bodega/config", json={"permite_cuenta": True, "tope_cuenta": 100}).json()["ok"]
    assert due.post("/anfitrion/bodega/config", json={"tope_cuenta": 75}).status_code == 400
    # Solo clientes REGISTRADOS del local.
    assert due.post("/anfitrion/bodega/vender", json=dict(ticket, cliente="extra@x.com")).status_code == 400
    j = due.post("/anfitrion/bodega/vender", json=ticket).json()
    assert j["ok"] and "lleva S/ 60.00" in j["mensaje"] and fk.prods["pil"]["stock"] == 18 and not fk.ventas
    assert fk.avisos[-1][1] == "Anotado en tu cuenta 📒"
    # Pasado el tope → se cobra al entregar (no se anota).
    r = due.post("/anfitrion/bodega/vender", json=ticket).json()
    assert r["aviso"]["titulo"] == "Tope de cuenta alcanzado" and fk.prods["pil"]["stock"] == 18
    # El jugador ve "llevas S/ 60.00" en la bodega del local.
    html = jug.get("/bodega/c1/pedir").text
    assert "Tu cuenta abierta" in html and "S/ 60.00" in html
    cid = next(iter(fk.cuentas))
    html = due.get("/anfitrion/bodega?tab=cuentas").text
    assert "📒 Cuentas (1)" in html and "Cobrar y cerrar cuenta" in html and "Sin tope" in html
    assert due.post(f"/anfitrion/bodega/cuenta/{cid}/cerrar", json={"medio": "efectivo"}).json()["ok"]
    assert fk.ventas[-1]["total"] == 60 and fk.prods["pil"]["stock"] == 18  # stock ya había bajado
    assert due.post(f"/anfitrion/bodega/cuenta/{cid}/cerrar", json={"medio": "efectivo"}).json()["aviso"]["titulo"] == "Ya estaba cerrada"
    assert len(fk.ventas) == 1


def test_bodega_no_disponible_y_mis_pedidos_sin_sesion(monkeypatch, fk):
    monkeypatch.setattr(config, "GOOGLE_WEB_CLIENT_ID", "cid-web")
    cli = TestClient(app, base_url="https://testserver")
    assert cli.get("/bodega/nope/pedir").status_code == 404
    r = cli.get("/mis-pedidos-bodega", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == "/entrar?volver=%2Fmis-pedidos-bodega"
    # Sin sesión la carta se ve y pedir exige iniciar sesión.
    fk.producto("pil", "Pilsen", 7, 10)
    fk.cfg[DUENO] = dict(bd.config_defecto(DUENO), acepta_pedidos=True)
    html = cli.get("/bodega/c1/pedir").text
    assert "Pilsen" in html and "\"sesion\": false" in html
    assert cli.post("/web/bodega/pedir", json={"cancha_id": "c1"}).status_code == 401


def test_expira_a_los_10_minutos():
    p = {"estado": "pendiente", "creado": datetime.now(timezone.utc) - timedelta(minutes=11)}
    assert bd.expirado(p) and not bd.expirado(dict(p, creado=datetime.now(timezone.utc)))
    assert not bd.expirado(dict(p, estado="confirmado"))
