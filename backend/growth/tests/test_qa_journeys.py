"""QA · VIAJES DE USUARIO de punta a punta (personas simuladas).

Cada test recorre la API como lo haría una PERSONA REAL usando el APK y la
torre, verificando en cada paso lo que esa persona VERÍA en su pantalla
(billetera, puntos, liquidaciones). Es la suite del agente QA (/qa): si algo
de plata o de flujo se rompe entre versiones, revienta aquí antes de llegar
a un dueño real.

Se mockea SOLO Culqi (la pasarela); todo lo demás es el backend real.
"""

import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config  # noqa: E402
from db.store import stores  # noqa: E402
from main import app  # noqa: E402
from pagos import culqi  # noqa: E402
from propiedad import reclamos  # noqa: E402

_ADM = {"X-Admin-Token": "adm_test"}
cli = TestClient(app, headers=_ADM)

LAT, LNG = -12.0432, -76.9540


class _CulqiFake:
    """Pasarela simulada: todo cargo aprueba y se puede reconsultar."""

    def __init__(self):
        self.cargos = {}
        self.n = 0

    def request(self, metodo, path, body=None):
        if metodo == "POST" and path == "/charges":
            self.n += 1
            cid = f"chr_qa_{self.n}"
            data = {"id": cid, "amount": body["amount"],
                    "currency_code": body["currency_code"], "captured": True,
                    "metadata": body.get("metadata", {})}
            self.cargos[cid] = data
            return {"ok": True, "data": data}
        if metodo == "GET" and path.startswith("/charges/"):
            cid = path.split("/charges/")[1]
            if cid in self.cargos:
                return {"ok": True, "data": self.cargos[cid]}
            return {"ok": False, "status": 404, "error": "no encontrado"}
        if metodo == "POST" and path == "/customers":
            return {"ok": True, "data": {"id": "cus_qa"}}
        return {"ok": False, "error": "ruta_desconocida"}


@pytest.fixture(autouse=True)
def _mundo(monkeypatch):
    stores.reset()
    monkeypatch.setattr(config, "CULQI_SECRET_KEY", "sk_test_xxx")
    monkeypatch.setattr(config, "CULQI_PUBLIC_KEY", "pk_test_xxx")
    monkeypatch.setattr(config, "APP_API_KEY", "")
    monkeypatch.setattr(config, "ADMIN_PANEL_TOKEN", "adm_test")
    monkeypatch.setattr(config, "PICHANGOL_ADMIN_WHATSAPP", "")
    fake = _CulqiFake()
    monkeypatch.setattr(culqi, "_request", fake.request)
    yield fake


def _saldo(email):
    return cli.get(f"/pagos/saldo/{email}").json()


def _movs(email):
    return cli.get(f"/pagos/movimientos/{email}").json()["movimientos"]


# ─────────────────────────────────────────────────────────────────────────────
# VIAJE 1 · Don Ramón, dueño aliado de la marcha blanca
# El operador le regala saldo; sus reservas en efectivo NO le tocan la plata
# real hasta agotar el regalo — la promesa central que le vendimos.
# ─────────────────────────────────────────────────────────────────────────────
def test_viaje_dueno_marcha_blanca_no_siente_la_comision():
    ramon = "ramon@canchas.pe"
    # El operador (torre) le regala S/200 y Pro de cortesía.
    assert cli.post("/pagos/regalo-saldo",
                    json={"email": ramon, "soles": 200}).json()["ok"] is True
    assert cli.post("/pagos/pro/cortesia",
                    json={"email": ramon, "dias": 90}).json()["ok"] is True

    # Ramón abre su billetera: ve S/0 de plata real y S/200 de regalo.
    s = _saldo(ramon)
    assert s["saldo_soles"] == 0.0 and s["saldo_promo_soles"] == 200.0
    # Y su app lo trata como Pro (bodega, reserva manual, bloqueos).
    assert stores.pro_activo(ramon) is True

    # Entra una reserva en EFECTIVO de S/120 → comisión de billetera.
    r = cli.post("/pagos/comision-reserva", json={
        "dueno_id": ramon, "monto_soles": 120.0,
        "reserva_id": "rsv_qa_ramon_1"}).json()
    assert r["ok"] is True and r["promo_usado_centimos"] == r["comision_centimos"]

    # Su plata real sigue INTACTA; el regalo bajó exactamente la comisión.
    s2 = _saldo(ramon)
    assert s2["saldo_soles"] == 0.0
    assert s2["saldo_promo_soles"] == 200.0 - r["comision_centimos"] / 100.0
    # En su historial, el movimiento le dice que fue cortesía.
    com = [m for m in _movs(ramon) if m["tipo"] == "comision_reserva"]
    assert com and "regalo" in com[0]["concepto"]


# ─────────────────────────────────────────────────────────────────────────────
# VIAJE 2 · Dueña nueva: reclama su cancha, el operador aprueba y la
# BIENVENIDA AUTOMÁTICA le llega sola (una sola vez, aunque re-reclame).
# ─────────────────────────────────────────────────────────────────────────────
def test_viaje_duena_nueva_recibe_bienvenida_al_activarse():
    stores.config["bienvenida_pro_dias"] = "60"
    stores.config["bienvenida_saldo_soles"] = "150"
    try:
        carla = "carla@lasmercedes.pe"
        r = reclamos.crear_reclamo("c_qa_carla", carla, "Las Mercedes",
                                   telefono_contacto="999888777",
                                   lat=LAT, lng=LNG)
        # Antes de aprobar: nada de regalos.
        assert _saldo(carla)["saldo_promo_soles"] == 0.0

        out = reclamos.aprobar_directo(r["reclamo_id"], "operador_qa")
        assert out["ok"] is True and out["verificada"] is True

        # Al activarse su primera cancha: Pro de cortesía + saldo de regalo.
        assert stores.pro_activo(carla) is True
        assert stores.membresias_pro[carla]["cortesia"] is True
        assert _saldo(carla)["saldo_promo_soles"] == 150.0

        # Registra una SEGUNDA cancha: el regalo NO se duplica.
        r2 = reclamos.crear_reclamo("c_qa_carla_2", carla, "Las Mercedes 2",
                                    telefono_contacto="999888777",
                                    lat=LAT + 0.01, lng=LNG + 0.01)
        reclamos.aprobar_directo(r2["reclamo_id"], "operador_qa")
        assert _saldo(carla)["saldo_promo_soles"] == 150.0
    finally:
        stores.config["bienvenida_pro_dias"] = "0"
        stores.config["bienvenida_saldo_soles"] = "0"


# ─────────────────────────────────────────────────────────────────────────────
# VIAJE 3 · Lucía paga su reserva ONLINE: el dueño con regalo recibe el
# 100% "por recibir" (billetera-first) y el operador liquida desde la torre.
# ─────────────────────────────────────────────────────────────────────────────
def test_viaje_reserva_online_liquidacion_completa():
    dueno = "club@sanborja.pe"
    cli.post("/pagos/regalo-saldo", json={"email": dueno, "soles": 100})

    # Lucía pagó online S/90 (Culqi ya cobró); el APK registra la liquidación.
    r = cli.post("/pagos/liquidacion-online", json={
        "dueno_id": dueno, "monto_soles": 90.0,
        "reserva_id": "rsv_qa_lucia_1",
        "concepto": "San Borja · Cancha 1 · Lucía · Hoy 19:00",
        "medio": "yape"}).json()
    assert r["ok"] is True and r["fuente"] == "saldo"  # billetera-first

    # El operador abre la torre: hay UNA liquidación pendiente por el BRUTO.
    pend = cli.get("/pagos/liquidaciones/pendientes").json()["pendientes"]
    fila = [p for p in pend if p["reserva_id"] == "rsv_qa_lucia_1"]
    assert fila and fila[0]["neto_soles"] == 90.0  # recibe el 100%

    # Le transfiere por Yape y la marca pagada (el modal de la torre).
    ok = cli.post("/pagos/liquidaciones/rsv_qa_lucia_1/pagar",
                  json={"metodo": "yape", "referencia": "OP-12345"})
    assert ok.status_code == 200
    pend2 = cli.get("/pagos/liquidaciones/pendientes").json()["pendientes"]
    assert not [p for p in pend2 if p["reserva_id"] == "rsv_qa_lucia_1"]

    # Doble click en "Marcar pagado" NO duplica comisión (idempotencia).
    r2 = cli.post("/pagos/liquidacion-online", json={
        "dueno_id": dueno, "monto_soles": 90.0,
        "reserva_id": "rsv_qa_lucia_1"}).json()
    assert r2["duplicada"] is True


# ─────────────────────────────────────────────────────────────────────────────
# VIAJE 4 · Pedro pide a la bodega y paga con su SALDO: cero comisión para
# el local, reembolso automático si se cancela, y sin dobles cobros.
# ─────────────────────────────────────────────────────────────────────────────
def test_viaje_bodega_pago_con_saldo_y_reembolso():
    pedro, local = "pedro@gmail.com", "bodega@sabor.pe"
    cli.post("/pagos/recarga", json={
        "token": "tkn_qa", "dueno_id": pedro, "email": pedro,
        "monto_soles": 50})

    # Pide 2 cervezas (S/20) y elige "pagar con mi saldo".
    r = cli.post("/pagos/bodega-pago", json={
        "cliente": pedro, "dueno_id": local, "monto_soles": 20.0,
        "pedido_id": "bpd_qa_1", "concepto": "Bodega · 2 Pilsen"}).json()
    assert r["ok"] is True
    assert _saldo(pedro)["saldo_soles"] == 30.0

    # El dueño VERIFICA el pago antes de entregar sin cobrar.
    assert cli.get("/pagos/bodega-pago/bpd_qa_1").json()["pagado"] is True
    # Y le queda el monto COMPLETO por recibir (bodega = cero comisión):
    # en SU billetera el movimiento dice neto S/20, comisión S/0.
    liq = stores.liquidaciones(dueno_id=local, solo_pendientes=True)
    assert len(liq) == 1 and liq[0].monto_centimos == 2000
    v = next(m for m in _movs(local) if m["tipo"] == "venta_bodega")
    assert v["comision_soles"] == 0.0 and v["neto_soles"] == 20.0
    # Y Pedro ve su egreso de S/20 en el historial.
    assert any(m["tipo"] == "bodega_pago" and m["monto_soles"] == -20.0
               for m in _movs(pedro))

    # El local no pudo atender → reembolso automático (y es idempotente).
    assert cli.post("/pagos/bodega-reembolso",
                    json={"pedido_id": "bpd_qa_1"}).json()["ok"] is True
    assert _saldo(pedro)["saldo_soles"] == 50.0
    r3 = cli.post("/pagos/bodega-reembolso",
                  json={"pedido_id": "bpd_qa_1"}).json()
    assert r3.get("duplicado") is True or _saldo(pedro)["saldo_soles"] == 50.0


# ─────────────────────────────────────────────────────────────────────────────
# VIAJE 5 · Sofía cae en las promos: bono de recarga + cupón, y todo queda
# claro en su historial (lo que una usuaria revisaría con lupa).
# ─────────────────────────────────────────────────────────────────────────────
def test_viaje_promos_bono_y_cupon_en_el_historial():
    sofia = "sofia@gmail.com"
    # El operador enciende el bono (10% desde S/50, tope S/20) y crea un cupón.
    assert cli.post("/pagos/promos/admin", json={
        "pct": 10, "minimo": 50, "tope": 20}).status_code == 200
    cup = cli.post("/pagos/cupones", json={
        "codigo": "QA-BIENVENIDA", "valor_soles": 5,
        "usos_max": 10}).json()
    assert cup["ok"] is True

    # Sofía recarga S/100 → espera ver S/110 (100 + bono 10).
    cli.post("/pagos/recarga", json={
        "token": "tkn_qa2", "dueno_id": sofia, "email": sofia,
        "monto_soles": 100})
    assert _saldo(sofia)["saldo_soles"] == 110.0

    # Canjea el cupón → S/115. Un segundo canje NO pasa.
    r = cli.post("/pagos/cupon/canjear", json={
        "email": sofia, "codigo": "QA-BIENVENIDA"}).json()
    assert r["ok"] is True
    assert _saldo(sofia)["saldo_soles"] == 115.0
    assert cli.post("/pagos/cupon/canjear", json={
        "email": sofia, "codigo": "QA-BIENVENIDA"}).json()["ok"] is False

    # Su historial cuenta la historia completa: recarga + bono + cupón.
    tipos = [m["tipo"] for m in _movs(sofia)]
    assert "recarga" in tipos and "bono_recarga" in tipos and "cupon" in tipos


# ─────────────────────────────────────────────────────────────────────────────
# VIAJE 6 · Un curioso SIN token intenta operar la torre: todo cerrado.
# ─────────────────────────────────────────────────────────────────────────────
def test_viaje_intruso_sin_token_no_opera_la_torre():
    anon = TestClient(app)  # sin X-Admin-Token
    assert anon.get("/pagos/liquidaciones/pendientes").status_code == 401
    assert anon.post("/pagos/pro/cortesia",
                     json={"email": "x@x.com", "dias": 30}).status_code == 401
    assert anon.post("/pagos/regalo-saldo",
                     json={"email": "x@x.com", "soles": 100}).status_code == 401
    assert anon.post("/pagos/pro/renovar-vencidas").status_code == 401
