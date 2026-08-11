"""PANEL WEB de administración (piloto): protegido por token y con aprobación
DIRECTA (al aprobar, la cancha queda activa sin validación en sitio)."""

import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config  # noqa: E402
from db.store import stores  # noqa: E402
from propiedad import reclamos  # noqa: E402

TOKEN = "secreto-piloto"


@pytest.fixture(autouse=True)
def _limpio(monkeypatch):
    from propiedad import router as _router
    stores.reset()
    _router._rate_hits.clear()  # aísla el rate-limit entre tests
    monkeypatch.setattr(config, "PICHANGOL_ADMIN_WHATSAPP", "")  # no envía nada
    monkeypatch.setattr(config, "ADMIN_PANEL_TOKEN", TOKEN)
    yield


@pytest.fixture
def client():
    import main  # importa la app ya con routers incluidos
    return TestClient(main.app)


def _reclamo():
    return reclamos.crear_reclamo("c1", "due@x.com", "La Pichanga",
                                  telefono_contacto="987654321",
                                  dni="12345678", relacion="dueño")


def test_aprobar_directo_activa_la_cancha_sin_validacion_en_sitio():
    r = _reclamo()
    out = reclamos.aprobar_directo(r["reclamo_id"], revisor="dennis")
    assert out["ok"] and out["estado"] == "activada"
    c = stores.cancha("c1")
    assert c.verificada is True
    assert c.metodo_verificacion == "panel_admin"
    # Aprobación directa NO es verificación en persona.
    assert c.verificada_en_persona is False


def test_panel_requiere_token(client):
    _reclamo()
    # Sin token -> 401.
    assert client.get("/admin/api/reclamos").status_code == 401
    # Token equivocado -> 401.
    r = client.get("/admin/api/reclamos", headers={"X-Admin-Token": "malo"})
    assert r.status_code == 401
    # Token correcto -> 200.
    r = client.get("/admin/api/reclamos", headers={"X-Admin-Token": TOKEN})
    assert r.status_code == 200 and len(r.json()) == 1


def test_panel_sin_token_configurado_responde_503(client, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_PANEL_TOKEN", "")
    r = client.get("/admin/api/reclamos", headers={"X-Admin-Token": "loquesea"})
    assert r.status_code == 503


def test_decidir_aprobar_por_http_activa(client):
    r = _reclamo()
    res = client.post(f"/admin/api/reclamo/{r['reclamo_id']}/decidir",
                      json={"aprobado": True, "revisor": "panel"},
                      headers={"X-Admin-Token": TOKEN})
    assert res.status_code == 200 and res.json()["estado"] == "activada"
    assert stores.cancha("c1").verificada is True


def test_decidir_rechazar_por_http(client):
    r = _reclamo()
    res = client.post(f"/admin/api/reclamo/{r['reclamo_id']}/decidir",
                      json={"aprobado": False, "revisor": "panel"},
                      headers={"X-Admin-Token": TOKEN})
    assert res.status_code == 200 and res.json()["estado"] == "rechazada"
    assert stores.cancha("c1").verificada is False


def test_pagina_panel_se_sirve(client):
    r = client.get("/admin")
    assert r.status_code == 200
    assert "Pichangol" in r.text and "Torre de control" in r.text
    assert "Iniciar sesión" in r.text  # login usuario+contraseña
    # Fase 2: el panel incluye la sección de liquidaciones a dueños.
    assert "cargarLiquidaciones" in r.text
    assert "Liquidaciones por pagar a dueños" in r.text
    assert "/pagos/liquidaciones/pendientes" in r.text


def test_flujo_liquidacion_desde_panel(client):
    # El operador (panel) usa los endpoints de pagos con X-Admin-Token.
    h = {"X-Admin-Token": TOKEN}
    client.post("/pagos/liquidacion-online", json={
        "dueno_id": "due@x.com", "monto_soles": 120, "reserva_id": "r_panel"})
    pend = client.get("/pagos/liquidaciones/pendientes", headers=h).json()
    assert len(pend["pendientes"]) == 1
    ok = client.post("/pagos/liquidaciones/r_panel/pagar", headers=h,
                     json={"metodo": "yape", "referencia": "OP9"}).json()
    assert ok["liquidado"] is True
    # Sin token → 401 (protegido).
    assert client.get("/pagos/liquidaciones/pendientes").status_code == 401


def test_aprobar_por_http_exige_token_admin(client):
    """La administración vive en la torre de control web (no en el APK): aprobar
    por /propiedad exige X-Admin-Token. Sin token NO activa (era un hueco de
    seguridad: cualquiera se auto-aprobaba)."""
    r = _reclamo()
    # Sin token -> 401 y la cancha NO se activa.
    res = client.post(f"/propiedad/reclamo/{r['reclamo_id']}/aprobar",
                      json={"aprobado": True, "revisor": "x"})
    assert res.status_code == 401
    assert stores.cancha("c1").verificada is False
    # Con token -> activa.
    res = client.post(f"/propiedad/reclamo/{r['reclamo_id']}/aprobar",
                      json={"aprobado": True, "revisor": "dennis"},
                      headers={"X-Admin-Token": TOKEN})
    assert res.status_code == 200 and res.json()["estado"] == "activada"
    assert stores.cancha("c1").verificada is True
    # El GET de estado que consulta la app SIGUE público.
    est = client.get("/propiedad/reclamo/c1")
    assert est.status_code == 200 and est.json()["verificada"] is True


def test_reclamos_con_datos_personales_exige_token(client):
    """GET /propiedad/reclamos expone DNI/teléfono/GPS: debe exigir token
    (Ley 29733). Sin token -> 401."""
    _reclamo()
    assert client.get("/propiedad/reclamos").status_code == 401
    r = client.get("/propiedad/reclamos", headers={"X-Admin-Token": TOKEN})
    assert r.status_code == 200 and len(r.json()) == 1


def test_app_key_gatea_endpoints_publicos(client, monkeypatch):
    """Con APP_API_KEY configurada, los endpoints públicos exigen X-App-Key
    (solo el APK oficial): un cliente externo sin la clave recibe 401."""
    monkeypatch.setattr(config, "APP_API_KEY", "clave-app")
    body = {"cancha_id": "cX", "solicitante_id": "d@x.com", "nombre_local": "L"}
    # Sin clave -> 401.
    assert client.post("/propiedad/reclamo", json=body).status_code == 401
    # Con clave -> 200.
    r = client.post("/propiedad/reclamo", json=body,
                    headers={"X-App-Key": "clave-app"})
    assert r.status_code == 200 and r.json()["ok"] is True


def test_sin_app_key_configurada_no_se_exige(client, monkeypatch):
    """Rollout gradual: si APP_API_KEY está vacía, no se exige (no rompe apps
    ya instaladas que aún no mandan la clave)."""
    monkeypatch.setattr(config, "APP_API_KEY", "")
    body = {"cancha_id": "cY", "solicitante_id": "d@x.com", "nombre_local": "L"}
    assert client.post("/propiedad/reclamo", json=body).status_code == 200


def test_rate_limit_corta_el_spam_de_reclamos(client, monkeypatch):
    """Con un límite bajo, tras N reclamos desde la misma IP el siguiente da 429."""
    monkeypatch.setattr(config, "RECLAMO_RATE_LIMIT", 3)
    monkeypatch.setattr(config, "APP_API_KEY", "")  # no exige clave en este test
    body = {"cancha_id": "c", "solicitante_id": "d@x.com", "nombre_local": "L"}
    codes = [client.post("/propiedad/reclamo", json={**body, "cancha_id": f"c{i}"})
             .status_code for i in range(4)]
    assert codes[:3] == [200, 200, 200]
    assert codes[3] == 429


def test_canal_comunicacion_default_y_cambio(client):
    """El canal por defecto es 'pcg_primero' y el APK lo lee por /config/canal
    (público). El admin lo cambia por /admin/api/canal (con token)."""
    h = {"X-Admin-Token": TOKEN}
    # Público: default.
    r = client.get("/config/canal")
    assert r.status_code == 200 and r.json()["canal"] == "pcg_primero"
    # Admin sin token -> 401.
    assert client.post("/admin/api/canal", json={"canal": "solo_pcg"}).status_code == 401
    # Admin cambia a solo_pcg.
    r = client.post("/admin/api/canal", json={"canal": "solo_pcg"}, headers=h)
    assert r.status_code == 200 and r.json()["ok"] is True
    # El APK ahora lee solo_pcg (ocultará WhatsApp).
    assert client.get("/config/canal").json()["canal"] == "solo_pcg"
    # Canal inválido -> no cambia.
    r = client.post("/admin/api/canal", json={"canal": "xxx"}, headers=h)
    assert r.json()["ok"] is False
    assert client.get("/config/canal").json()["canal"] == "solo_pcg"


def test_borrar_cobros_matricula_limpia_el_reporte(client):
    """PRUEBAS: el reporte del profe (resumen de matrícula) se puede resetear sin
    tocar saldos, para que no arrastre cobros de pruebas viejas."""
    h = {"X-Admin-Token": TOKEN}
    # Registra 2 cobros de matrícula de la academia 'ac1'.
    for i in range(2):
        r = client.post("/pagos/matricula", json={
            "academia_id": "ac1", "monto_soles": 300,
            "matricula_id": f"mat_{i}", "pais": "pe",
            "concepto": "Matrícula"})
        assert r.status_code == 200
    res = client.get("/pagos/matricula/resumen/ac1").json()
    assert res["cobros"] == 2 and res["bruto_soles"] == 600.0
    # Borra los cobros de matrícula (mantenimiento).
    out = client.post("/admin/api/borrar-cobros-matricula", headers=h).json()
    assert out["ok"] and out["borrados"] == 2
    # El reporte queda en cero.
    res = client.get("/pagos/matricula/resumen/ac1").json()
    assert res["cobros"] == 0 and res["bruto_soles"] == 0.0
    # Sin token -> 401.
    assert client.post("/admin/api/borrar-cobros-matricula").status_code == 401


def test_reiniciar_pagos_deja_margenes_en_cero(client):
    """El reinicio total del libro de pagos deja el reporte de márgenes en cero."""
    h = {"X-Admin-Token": TOKEN}
    stores.registrar_pago(tipo="matricula_online", monto_centimos=30000,
                          moneda="PEN", estado="aprobado", dueno_id="acM",
                          culqi_charge_id="mM", comision_centimos=1500)
    stores.registrar_pago(tipo="suscripcion", monto_centimos=5000, moneda="PEN",
                          estado="aprobado", dueno_id="acM", culqi_charge_id="s1")
    out = client.post("/admin/api/reiniciar-pagos", headers=h).json()
    assert out["ok"] and out["borrados"] == 2
    m = client.get("/admin/api/margenes", headers=h).json()
    assert m["ingresos_pcg_soles"] == 0.0 and m["bruto_procesado_soles"] == 0.0
    assert client.post("/admin/api/reiniciar-pagos").status_code == 401


def test_reset_virgen_borra_transaccional_y_conserva_reclamos(client):
    """'Dejar en virgen' borra pagos, saldos, suscripciones, tarjetas y vistas,
    pero CONSERVA los reclamos de propiedad (las canchas siguen reclamadas)."""
    h = {"X-Admin-Token": TOKEN}
    # Estado transaccional poblado.
    stores.registrar_pago(tipo="matricula_online", monto_centimos=30000,
                          moneda="PEN", estado="aprobado", dueno_id="ac1",
                          culqi_charge_id="m1", comision_centimos=1500)
    stores.saldos["due@x.com"] = 17000
    stores.suscripciones["ac1:landing"] = {"academia_id": "ac1",
                                           "dueno_id": "due@x.com",
                                           "servicio": "landing"}
    stores.suscripciones_alumno["al1"] = {"academia_id": "ac1"}
    stores.metodos["due@x.com"] = [{"id": "crd_1", "marca": "Visa"}]
    stores.customers["due@x.com"] = "cus_1"
    stores.vistas["ac1"] = {"2026-07-01": 5}
    # Un reclamo que DEBE conservarse.
    stores.reclamos.append("reclamo-marcador")
    reclamos_antes = len(stores.reclamos)

    out = client.post("/admin/api/reset-virgen", headers=h).json()
    assert out["ok"] is True
    assert out["borrado"]["pagos"] == 1
    assert out["borrado"]["saldos"] == 1
    assert out["borrado"]["metodos_pago"] == 1

    assert stores.pagos == []
    assert stores.saldos == {}
    assert stores.suscripciones == {}
    assert stores.suscripciones_alumno == {}
    assert stores.metodos == {}
    assert stores.customers == {}
    assert stores.vistas == {}
    # Reclamos intactos → las canchas siguen reclamadas.
    assert len(stores.reclamos) == reclamos_antes
    assert "reclamo-marcador" in stores.reclamos
    # Sin token, 401.
    assert client.post("/admin/api/reset-virgen").status_code == 401


def test_pro_admin_lista_miembros_precio_y_mrr(client):
    h = {"X-Admin-Token": TOKEN}
    # Un miembro activo (hasta futuro) + uno vencido → MRR = activos × precio.
    stores.membresias_pro["a@x.com"] = {"hasta": "2999-01-01T00:00:00+00:00"}
    stores.membresias_pro["b@x.com"] = {"hasta": "2020-01-01T00:00:00+00:00"}
    out = client.get("/admin/api/pro", headers=h).json()
    assert out["precios"]["pe"] == 12.0
    assert out["activos"] == 1 and out["total"] == 2
    assert out["mrr_soles"] == 12.0
    # Cambiar el precio de Perú.
    r = client.post("/admin/api/pro/precio", json={"precio_soles": 15,
                    "pais": "pe"}, headers=h).json()
    assert r["ok"] and r["precios"]["pe"] == 15.0
    out2 = client.get("/admin/api/pro", headers=h).json()
    assert out2["mrr_soles"] == 15.0
    # Precio por país: Ecuador override.
    client.post("/admin/api/pro/precio", json={"precio_soles": 8, "pais": "ec"},
                headers=h)
    assert client.get("/admin/api/pro", headers=h).json()["precios"]["ec"] == 8.0
    # Protegido por token.
    assert client.get("/admin/api/pro",
                      headers={"X-Admin-Token": "malo"}).status_code == 401


def test_pro_mrr_por_pais_en_su_moneda(client):
    """El MRR NO suma monedas distintas: se reporta por país (S/, $, Bs)."""
    h = {"X-Admin-Token": TOKEN}
    client.post("/admin/api/pro/precio", json={"precio_soles": 8, "pais": "ec"},
                headers=h)
    stores.membresias_pro["pe@x.com"] = {
        "hasta": "2999-01-01T00:00:00+00:00", "pais": "PE"}
    stores.membresias_pro["ec@x.com"] = {
        "hasta": "2999-01-01T00:00:00+00:00", "pais": "EC"}
    out = client.get("/admin/api/pro", headers=h).json()
    assert out["mrr_por_pais"]["pe"] == 12.0  # Perú en soles
    assert out["mrr_por_pais"]["ec"] == 8.0   # Ecuador en dólares (no sumado a PE)
    assert out["mrr_por_pais"]["bo"] == 0.0
    assert out["activos_por_pais"] == {"pe": 1, "ec": 1, "bo": 0}


def test_circuito_ingresos_pro_y_torneos(client):
    h = {"X-Admin-Token": TOKEN}
    # 2 membresías Pro (S/12 c/u) + 1 ingreso de torneo (bruto 20, comisión 2).
    stores.registrar_pago(tipo="suscripcion_pro", monto_centimos=1200,
                          moneda="PEN", estado="aprobado", dueno_id="a@x.com")
    stores.registrar_pago(tipo="suscripcion_pro", monto_centimos=1200,
                          moneda="PEN", estado="aprobado", dueno_id="b@x.com")
    stores.registrar_pago(tipo="inscripcion_torneo_ingreso", monto_centimos=2000,
                          moneda="PEN", estado="aprobado", dueno_id="profe@x.com",
                          comision_centimos=200)
    out = client.get("/admin/api/circuito", headers=h).json()
    assert out["pro"]["cobros"] == 2 and out["pro"]["total_soles"] == 24.0
    assert out["torneos"]["inscripciones"] == 1
    assert out["torneos"]["comision_soles"] == 2.0
    assert out["torneos"]["bruto_soles"] == 20.0
    # Ingreso Pichangol = Pro total + comisión torneos = 24 + 2 = 26.
    assert out["ingreso_circuito_soles"] == 26.0
    # Salud del circuito: expone directorio, retos y límite gratis.
    assert out["directorio"]["total"] == 0
    assert out["retos"]["total"] == 0
    assert out["limite_retos_free"] == 3


def test_circuito_salud_directorio_y_lideres(client):
    h = {"X-Admin-Token": TOKEN}
    # 2 jugadores en el directorio (uno tenis, uno fútbol).
    client.post("/circuito/unirse", json={
        "email": "ana@x.com", "nombre": "Ana", "deporte": "tenis"})
    client.post("/circuito/unirse", json={
        "email": "luis@x.com", "nombre": "Luis", "deporte": "futbol"})
    # Un reto jugado que gana Ana → aparece de líder.
    rid = client.post("/retos/crear", json={
        "retador_email": "ana@x.com", "retador_nombre": "Ana",
        "retado_email": "luis@x.com", "retado_nombre": "Luis",
        "deporte": "tenis"}).json()["reto"]["id"]
    client.post(f"/retos/{rid}/responder", json={"aceptar": True})
    client.post(f"/retos/{rid}/resultado", json={
        "ganador_email": "ana@x.com", "reportado_por": "ana@x.com"})
    # Doble confirmación: el otro (Luis) confirma → cuenta como jugado.
    client.post(f"/retos/{rid}/confirmar", json={
        "por_email": "luis@x.com", "acepta": True})
    out = client.get("/admin/api/circuito", headers=h).json()
    assert out["directorio"]["total"] == 2
    assert out["directorio"]["por_deporte"]["tenis"] == 1
    assert out["retos"]["jugados"] == 1
    assert out["lideres_retos"][0]["email"] == "ana@x.com"
    assert out["lideres_retos"][0]["ganados"] == 1


def test_limite_retos_editable_desde_torre(client):
    h = {"X-Admin-Token": TOKEN}
    # Bajar el tope gratis a 1 desde la torre.
    r = client.post("/admin/api/circuito/limite-retos",
                    json={"limite": 1}, headers=h).json()
    assert r["ok"] is True and r["limite"] == 1
    assert client.get("/admin/api/circuito", headers=h).json()["limite_retos_free"] == 1
    # Mínimo 1 (un 0 se sube a 1).
    r0 = client.post("/admin/api/circuito/limite-retos",
                     json={"limite": 0}, headers=h).json()
    assert r0["limite"] == 1
    # Efecto real: con tope 1, el 2º reto de un no-Pro corta.
    base = {"retador_email": "ana@x.com", "retado_email": "luis@x.com",
            "deporte": "tenis"}
    assert client.post("/retos/crear", json=base).json()["ok"] is True
    assert client.post("/retos/crear", json=base).json()["error"] == "limite_retos_free"


def test_ranking_snapshot_del_app_se_ve_en_la_torre(client):
    h = {"X-Admin-Token": TOKEN}
    # Sin snapshot: vacío.
    assert client.get("/admin/api/ranking", headers=h).json()["deportes"] == []
    # El APK empuja el ranking cruzado.
    snap = {"por": "ana@x.com", "deportes": [{
        "deporte": "tenis", "temporada": "2026-T3",
        "top": [{"nombre": "Ana", "puntos": 9, "pg": 3, "pp": 0,
                 "academia": "Club X", "pro": True}],
        "campeon": {"nombre": "Ana", "puntos": 9}}]}
    r = client.post("/circuito/ranking-snapshot", json=snap).json()
    assert r["ok"] is True and r["deportes"] == 1
    out = client.get("/admin/api/ranking", headers=h).json()
    assert out["deportes"][0]["deporte"] == "tenis"
    assert out["deportes"][0]["top"][0]["nombre"] == "Ana"
    assert out["actualizado"]


def test_margenes_unifica_matriculas_reservas_y_banco(client):
    """La torre de control ve el margen total de Pichangol: comisiones (matrículas
    + reservas) menos el costo del banco sobre lo procesado por tarjeta
    (matrículas + recargas)."""
    h = {"X-Admin-Token": TOKEN}
    # Registra los pagos directo en el libro (sin pasar por Culqi):
    #  - matrícula de S/300 con comisión congelada S/15 (5%)
    stores.registrar_pago(tipo="matricula_online", monto_centimos=30000,
                          moneda="PEN", estado="aprobado", dueno_id="acM",
                          culqi_charge_id="mM", comision_centimos=1500)
    #  - recarga de saldo del dueño S/100 (pasó por tarjeta)
    stores.registrar_pago(tipo="recarga", monto_centimos=10000, moneda="PEN",
                          estado="aprobado", dueno_id="due@x.com",
                          culqi_charge_id="rec1")
    #  - comisión de reserva S/5 (se debitó del saldo)
    stores.registrar_pago(tipo="comision_reserva", monto_centimos=500,
                          moneda="PEN", estado="aprobado", dueno_id="due@x.com",
                          culqi_charge_id="rsv1")
    #  - servicio (landing/redes) S/50 que la academia le paga a PCG por tarjeta
    stores.registrar_pago(tipo="suscripcion", monto_centimos=5000, moneda="PEN",
                          estado="aprobado", dueno_id="acM", culqi_charge_id="srv1")
    # Tasa banco 4% y desglose.
    m = client.post("/admin/api/margenes/banco", json={"pct": 4}, headers=h).json()
    assert m["cobros_matricula"] == 1 and m["cobros_reserva"] == 1
    assert m["cobros_servicios"] == 1
    assert m["comision_matricula_soles"] == 15.0               # 5% de 300
    assert m["comision_reserva_soles"] == 5.0
    assert m["ingresos_servicios_soles"] == 50.0
    assert m["ingresos_pcg_soles"] == 70.0                     # 15 + 5 + 50
    assert m["bruto_procesado_soles"] == 450.0                 # 300 + 100 + 50
    assert m["costo_banco_soles"] == 18.0                      # 4% de 450
    assert m["margen_pcg_soles"] == 52.0                       # 70 − 18
    # Sin token -> 401.
    assert client.get("/admin/api/margenes").status_code == 401


def test_triage_solo_no_activa(client):
    """Contraste: el triage clásico aprueba pero NO activa. Ahora exige token."""
    r = _reclamo()
    res = client.post(f"/propiedad/reclamo/{r['reclamo_id']}/triage",
                      json={"aprobado": True, "revisor": "dennis"},
                      headers={"X-Admin-Token": TOKEN})
    assert res.status_code == 200 and res.json()["estado"] == "aprobado_triage"
    assert stores.cancha("c1").verificada is False


# ── Panel de disputas del marketplace ────────────────────────────────────────

def _venta_disputada(client):
    """Crea una venta y la deja en disputa; devuelve su id."""
    client.post("/pagos/venta", json={
        "vendedor_id": "vend@x.com", "vendedor_nombre": "Vendedor",
        "monto_soles": 100, "venta_id": "vd1", "producto_id": "p1",
        "producto_nombre": "Raqueta", "comprador_email": "comp@x.com",
        "comprador_nombre": "Comprador"})
    vid = client.get("/ventas/vendedor/vend@x.com").json()["ventas"][0]["id"]
    client.post(f"/ventas/{vid}/disputa", json={"por_email": "comp@x.com"})
    return vid


def test_panel_lista_disputas(client):
    _venta_disputada(client)
    r = client.get("/admin/api/ventas/disputas",
                   headers={"X-Admin-Token": TOKEN}).json()
    assert len(r["disputas"]) == 1
    assert r["disputas"][0]["producto_nombre"] == "Raqueta"
    assert r["disputas"][0]["neto_soles"] == 95.0  # 100 - 5%


def test_panel_disputas_exige_token(client):
    assert client.get("/admin/api/ventas/disputas").status_code == 401


def test_panel_resolver_liberar(client):
    vid = _venta_disputada(client)
    r = client.post(f"/admin/api/venta/{vid}/resolver",
                    json={"accion": "liberar"},
                    headers={"X-Admin-Token": TOKEN}).json()
    assert r["ok"] is True and r["estado"] == "recibido"
    res = client.get("/ventas/vendedor/vend@x.com").json()
    assert res["liberado_soles"] == 95.0  # ya no está en disputa


def test_panel_resolver_reembolsar(client):
    vid = _venta_disputada(client)
    r = client.post(f"/admin/api/venta/{vid}/resolver",
                    json={"accion": "reembolsar"},
                    headers={"X-Admin-Token": TOKEN}).json()
    assert r["ok"] is True and r["estado"] == "reembolsado"
    res = client.get("/ventas/vendedor/vend@x.com").json()
    assert res["liberado_soles"] == 0.0 and res["retenido_soles"] == 0.0
