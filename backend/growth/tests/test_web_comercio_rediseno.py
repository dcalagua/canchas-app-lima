"""Rediseño del modo anfitrión · frente "comercio" (16-nov-2026): Mi tienda,
Mi bodega, Mis campeonatos, Llenar cancha, Recordar reservas y Pro. Aquí van
las reglas NUEVAS que trajo el rediseño (cifras reales por moneda, comisión de
la configuración, mensaje extra por selección, "Ver los N jugadores", solo
beneficios Pro que existen, aviso Pro que ya no se abre solo)."""
import pytest
from fastapi.testclient import TestClient

import config
from db.store import stores
from main import app
from web import anfitrion_negocio as neg
from web import anfitrion_tienda as tienda
from web import datos, sesion
from web import jugador_partidos as JP
from web import jugador_pro as jp

DUENO = "dueno@gmail.com"


@pytest.fixture(autouse=True)
def _estado(monkeypatch):
    antes = stores.to_state()
    monkeypatch.setattr(config, "GOOGLE_WEB_CLIENT_ID", "cid-web")
    monkeypatch.setattr(datos, "celular_de_perfil", lambda e: "")
    yield
    stores.load_state(antes)


def _cli(email=DUENO, nombre="Dueño"):
    cli = TestClient(app, base_url="https://testserver")
    cli.cookies.set(sesion.COOKIE, sesion.emitir({"email": email, "nombre": nombre, "foto": ""}))
    return cli


def _cancha(cid="k1", **kw):
    c = {"id": cid, "nombre": f"Cancha {cid}", "club": "Club K", "deporte": "futbol", "deportes": ["futbol"], "hora_apertura": "07:00",
         "hora_cierre": "23:00", "duracion_slot_min": 60, "precio_hora": 80, "precio_turno": 0, "verificada": True, "dueno": DUENO,
         "lat": -12.1, "lng": -77.0, "moneda": "S/", "foto_url": ""}
    c.update(kw)
    return c


def _prod(pid, nombre, stock, activo=True, moneda="S/"):
    return {"id": pid, "vendedor_email": DUENO, "vendedor_nombre": "Dueño", "nombre": nombre, "descripcion": "", "precio": 50.0,
            "moneda": moneda, "categoria": "pelotas", "foto_url": "", "stock": stock, "activo": activo, "creado_en": "2026-11-01"}


def test_mi_tienda_cifras_reales_por_moneda_y_comision_de_la_configuracion(monkeypatch):
    monkeypatch.setattr(datos, "canchas_de_dueno", lambda e: [_cancha()] if e == DUENO else [])
    monkeypatch.setattr(datos, "esta_verificado", lambda e: False)
    monkeypatch.setattr(datos, "productos_de_vendedor", lambda e: [
        _prod("prod_1000001", "Pelota", 12), _prod("prod_1000002", "Pala", 1), _prod("prod_1000003", "Pechera", None, activo=False),
        _prod("prod_1000004", "Tubo", 0)])
    monkeypatch.setattr(config, "COMISION_PORC", 7.0)
    monkeypatch.setattr(config, "COMISION_MIN_SOLES", 2.5)
    # Ventas por liquidar: una en soles y otra en dólares (nunca se suman); la ajena no cuenta.
    stores.registrar_pago(tipo="venta_producto", monto_centimos=10000, moneda="PEN", estado="aprobado", dueno_id=DUENO,
                          culqi_charge_id="v_pen", concepto="Venta")
    stores.registrar_pago(tipo="venta_producto", monto_centimos=2000, moneda="USD", estado="aprobado", dueno_id=DUENO,
                          culqi_charge_id="v_usd", concepto="Venta")
    stores.registrar_pago(tipo="venta_producto", monto_centimos=9900, moneda="PEN", estado="aprobado", dueno_id="otro@x.com",
                          culqi_charge_id="v_otro", concepto="Venta")
    neto = tienda.neto_por_recibir(DUENO)
    assert neto == {"PEN": 93.0, "USD": 18.6}   # 100 − 7 % ; 20 − 7 % (sobre el mínimo de $ 0.50)
    html = _cli().get("/anfitrion/tienda").text
    assert "S/ 93.00" in html and "+ $ 18.60" in html
    assert "7 %" in html and "mín. S/ 2.50" in html and "5 %" not in html   # % y mínimo REALES, no el 5 % del diseño
    assert "3 publicados" in html and "data-filtro='pau'" in html and "Pausados<i>1</i>" in html
    assert "Stock 12" in html and "Último en stock" in html and "Stock ilimitado" in html and "Sin stock" in html
    assert "data-activo='prod_1000001'" in html and "data-eliminar='prod_1000001'" in html
    assert "anf-back" not in html and "confirm(" not in tienda._JS_TIENDA.replace("pcgConfirmar(", "")


def test_llenar_cancha_mensaje_extra_solo_por_seleccion(monkeypatch):
    c = _cancha(hora_apertura="18:00", hora_cierre="20:00", descuento_valle=20, valle_desde="18:00", valle_hasta="19:00")
    monkeypatch.setattr(datos, "canchas_de_dueno", lambda e: [c] if e == DUENO else [])
    monkeypatch.setattr(datos, "ocupados", lambda cid, fs: set())
    monkeypatch.setattr(datos, "descuentos", lambda cid, fs: {})
    monkeypatch.setattr(datos, "reservas_de_canchas", lambda ids, a, b: [{"usuario": "juan@x.com", "jugador": "Juan", "telefono": ""}])
    monkeypatch.setattr(JP, "aplicar_descuento_slot", lambda *a: True)
    msgs = []
    import web.jugador_mensajes as JM
    monkeypatch.setattr(JM, "insertar_mensaje", lambda f: msgs.append(f) or f)
    cli = _cli()
    html = cli.get("/anfitrion/llenar?dia=1").text
    assert "id='llPromo'" in html and "data-promo='amigos'" in html and "Así les llega" in html
    assert "<input type='text' id='llPromoTxt'" in html and "maxlength='160'" in html   # texto libre (ya existía) + sugerencias
    assert '"v": true' in html                                    # 18:00 es hora feliz → ícono de valle
    assert "va-lat" in html and "Mañana" in html
    cuerpo = {"cancha_id": c["id"], "dia": 1, "horas": ["18:00"], "descuento": 0}
    assert cli.post("/anfitrion/llenar/avisar", json={**cuerpo, "promo": "amigos"}).json()["ok"]
    assert msgs[-1]["texto"].endswith("\n" + JP.PROMOS_LLENAR["amigos"])
    # El texto libre del dueño viaja tal cual (normalizado, máx. 160), como siempre.
    assert cli.post("/anfitrion/llenar/avisar", json={**cuerpo, "promo": "  20%   off hoy  " + "x" * 300}).json()["ok"]
    assert msgs[-1]["texto"].split("\n")[-1] == ("20% off hoy " + "x" * 300)[:160]
    assert cli.post("/anfitrion/llenar/avisar", json={**cuerpo, "promo": ""}).json()["ok"]
    assert msgs[-1]["texto"].endswith("respóndeme por aquí.")


def test_recordar_reservas_muchos_jugadores_y_recordar_a_todos(monkeypatch):
    canchas = [_cancha()]
    monkeypatch.setattr(datos, "canchas_de_dueno", lambda e: canchas if e == DUENO else [])
    hoy = neg._hoy_de(canchas).date().isoformat()
    filas = [{"id": f"r{i}", "cancha_id": "k1", "jugador": f"Jugador {i}", "usuario": f"j{i}@x.com", "telefono": "", "fecha": hoy,
              "hora_inicio": f"{8 + i:02d}:00", "hora_fin": f"{9 + i:02d}:00", "estado": "confirmada", "grupo_reserva_id": ""}
             for i in range(10)]
    monkeypatch.setattr(neg, "reservas_dueno", lambda ids, d, h: [dict(f) for f in filas if d <= f["fecha"] <= h])
    monkeypatch.setattr(jp, "recordados_por_app", lambda d, ids: {"r0"})
    enviados = []
    import web.jugador_mensajes as JM
    monkeypatch.setattr(JM, "insertar_mensaje", lambda f: enviados.append(f) or f)
    cli = _cli()
    html = cli.get("/anfitrion/recordatorios?dia=hoy").text
    assert "9 jugadores con la app por recordar" in html and "id='recTodos'" in html
    assert "Ver los 10 jugadores" in html and html.count("class=vc-mas") == 2
    assert "Chat de la app" in html and "Recordado" in html and html.count("class='btn' data-acc='app'") == 9
    # "Recordar a todos" = el mismo envío en lote; el ya recordado no se repite.
    j = cli.post("/anfitrion/recordatorios/enviar", json={"fecha": hoy, "ids": [f["id"] for f in filas]}).json()
    assert j == {"ok": True, "enviados": 9} and all(not m["id"].endswith("_r0") for m in enviados)


def test_pro_solo_promete_beneficios_que_existen(monkeypatch):
    monkeypatch.setattr(datos, "canchas_de_dueno", lambda e: [_cancha()] if e == DUENO else [])
    monkeypatch.setattr(config, "WEB_MANUAL_REQUIERE_PRO", False)
    local, ti = jp.beneficios_pro(True)
    titulos = [t for _i, t, _d in local + ti]
    assert "Mi bodega" in titulos and "Retos sin límite" in titulos and "Reserva manual y bloqueos" not in titulos
    monkeypatch.setattr(config, "WEB_MANUAL_REQUIERE_PRO", True)
    assert "Reserva manual y bloqueos" in [t for _i, t, _d in jp.beneficios_pro(True)[0]]
    local, ti = jp.beneficios_pro(False)
    assert local == [] and "Campeonatos con tu marca" in [t for _i, t, _d in ti]
    html = _cli().get("/pro").text
    assert "Prioridad en torneos" not in html and "Apoyas tu comunidad" not in html
    assert "Para tu local" in html and "Para ti" in html and "Compara Gratis vs Pro" in html and "Tu saldo hoy" in html


def test_aviso_pro_de_campeonatos_no_se_abre_solo(monkeypatch):
    for fn, v in (("campeonatos_de_dueno", []), ("campeonatos_donde_participa", [])):
        monkeypatch.setattr(datos, fn, lambda e, _v=v: _v)
    monkeypatch.setattr(datos, "canchas_de_dueno", lambda e: [])
    cli = _cli()
    stores.membresias_pro[DUENO] = {"hasta": "2099-01-01T00:00:00+00:00"}
    html = cli.get("/anfitrion/campeonatos").text
    assert "class='modal open'" not in html and "href='/anfitrion/campeonatos/nuevo'" in html   # con Pro: nada se abre solo
    stores.membresias_pro.pop(DUENO)
    assert "class='modal open'" not in cli.get("/anfitrion/campeonatos").text
    html = cli.get("/anfitrion/campeonatos?pro=1").text                                        # vuelve de /nuevo sin Pro
    assert "class='modal open'" in html and "data-abrir='modalPro'" in html
    assert "Fútbol" in html and "Aún no tienes campeonatos" in html


def test_bodega_sin_pro_precio_real_y_jerga_por_pais(monkeypatch):
    monkeypatch.setattr(datos, "canchas_de_dueno", lambda e: [_cancha(lat=-0.18, lng=-78.47, moneda="$")] if e == DUENO else [])
    stores.membresias_pro.pop(DUENO, None)
    html = _cli().get("/anfitrion/bodega").text
    assert "La bodega es parte de" in html and "Yape" not in html and "tu QR o transferencia" in html
    assert "Caja rápida" in html and "Stock con alertas" in html and "Reportes de venta" in html and "Carta digital con QR" in html
