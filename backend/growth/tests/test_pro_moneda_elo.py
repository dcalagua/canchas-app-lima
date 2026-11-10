"""Brechas cerradas el 1-oct-2026:

1. Renovación automática de Pro desde el APK (`POST /pagos/pro/renovacion`,
   mismo núcleo que la web `/web/pro/renovacion`).
2. Moneda REAL en Pro, su renovación y la inscripción individual a torneo
   (antes todo se registraba en PEN).
3. ELO de los retos aplicado en el SERVIDOR, una sola vez por reto, con la
   fórmula de `Nivel.calcularElo` del APK.
"""

import os
import sys
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config  # noqa: E402
from db.store import stores  # noqa: E402
from main import app  # noqa: E402
from pagos import router as pagos_router  # noqa: E402
from retos import elo  # noqa: E402

client = TestClient(app)


@pytest.fixture(autouse=True)
def _setup(monkeypatch):
    stores.reset()
    monkeypatch.setattr(config, "APP_API_KEY", "")
    monkeypatch.setattr(config, "PAGOS_AUTH_USUARIO", "")
    monkeypatch.setattr(pagos_router, "_aviso_push_usuario", lambda *a, **k: None)
    yield
    stores.reset()


# ── 1. Renovación automática de Pro desde el APK ─────────────────────────────

def test_pro_renovacion_desde_el_apk_misma_regla_que_la_web(monkeypatch):
    email = "ana@gmail.com"
    # Sin Pro vigente: no hay renovación que cambiar.
    r = client.post("/pagos/pro/renovacion", json={"email": email, "renovar": False}).json()
    assert r["ok"] is False and r["error"] == "sin_pro"
    precio = pagos_router._pro_precio_centimos("PE")
    stores.acreditar(email, precio)
    assert client.post("/pagos/pro/suscribir", json={"email": email, "pais": "PE"}).json()["ok"]
    assert client.get(f"/pagos/pro/estado/{email}").json()["renueva"] is True
    r = client.post("/pagos/pro/renovacion", json={"email": "Ana@Gmail.com", "renovar": False}).json()
    assert r == {"ok": True, "renueva": False}
    est = client.get(f"/pagos/pro/estado/{email}").json()
    assert est["renueva"] is False and est["cortesia"] is False
    # Al vencer no se debita nada (el cron respeta auto_renovar=False).
    stores.acreditar(email, precio * 2)
    saldo = stores.saldo_centimos(email)
    stores.membresias_pro[email]["hasta"] = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    pagos_router.procesar_renovaciones_pro()
    assert stores.saldo_centimos(email) == saldo
    # Reactivar (con Pro vigente otra vez).
    stores.membresias_pro[email]["hasta"] = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
    assert client.post("/pagos/pro/renovacion", json={"email": email, "renovar": True}).json()["renueva"] is True
    # Cortesía: nunca se renueva sola.
    stores.membresias_pro[email]["cortesia"] = True
    r = client.post("/pagos/pro/renovacion", json={"email": email, "renovar": True}).json()
    assert r["ok"] is False and r["error"] == "cortesia"
    assert client.get(f"/pagos/pro/estado/{email}").json()["cortesia"] is True


def test_pro_renovacion_exige_app_key_y_el_token_del_propio_usuario(monkeypatch):
    monkeypatch.setattr(config, "APP_API_KEY", "k1")
    assert client.post("/pagos/pro/renovacion", json={"email": "a@x.com", "renovar": False}).status_code == 401
    monkeypatch.setattr(config, "PAGOS_AUTH_USUARIO", "1")
    monkeypatch.setattr(pagos_router, "_email_de_token", lambda t: "otro@x.com")
    r = client.post("/pagos/pro/renovacion", json={"email": "a@x.com", "renovar": False},
                    headers={"X-App-Key": "k1", "X-User-Token": "tok"})
    assert r.status_code == 403


# ── 2. Moneda real en Pro, renovación y torneo ───────────────────────────────

@pytest.mark.parametrize("pais,moneda", [("PE", "PEN"), ("EC", "USD"), ("BO", "BOB")])
def test_pro_y_su_renovacion_se_registran_en_la_moneda_del_pais(pais, moneda):
    email = f"j_{pais.lower()}@x.com"
    stores.config["pro_precio_soles_ec"] = "4.5"
    stores.config["pro_precio_soles_bo"] = "30"
    precio = pagos_router._pro_precio_centimos(pais)
    stores.acreditar(email, precio * 3)
    assert client.post("/pagos/pro/suscribir", json={"email": email, "pais": pais}).json()["ok"]
    pagos = [p for p in stores.pagos if p.tipo == "suscripcion_pro" and p.dueno_id == email]
    assert len(pagos) == 1 and pagos[0].moneda == moneda and pagos[0].monto_centimos == precio
    stores.membresias_pro[email]["hasta"] = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    assert pagos_router.procesar_renovaciones_pro()["renovadas"] == 1
    pagos = [p for p in stores.pagos if p.tipo == "suscripcion_pro" and p.dueno_id == email]
    assert len(pagos) == 2 and all(p.moneda == moneda for p in pagos)


def test_inscripcion_a_torneo_en_la_moneda_del_campeonato(monkeypatch):
    jug, org = "jug@x.com", "org@x.com"
    monkeypatch.setattr(pagos_router, "moneda_billetera", lambda email: "USD")
    stores.acreditar(jug, 2000)  # $ 20.00
    r = client.post("/pagos/torneo/inscribir", json={
        "email": jug, "academia_dueno": org, "cuota_soles": 10, "concepto": "Copa Quito", "moneda": "$"}).json()
    assert r["ok"] is True
    # Comisión 5 % con MÍNIMO de la moneda ($ 0.50), no el de soles (S/ 2).
    assert r["comision_centimos"] == 50 and r["neto_centimos"] == 950
    egreso = next(p for p in stores.pagos if p.tipo == "inscripcion_torneo")
    ingreso = next(p for p in stores.pagos if p.tipo == "inscripcion_torneo_ingreso")
    assert egreso.moneda == "USD" and ingreso.moneda == "USD" and ingreso.comision_centimos == 50
    # Bolivia: mínimo Bs 3.
    monkeypatch.setattr(pagos_router, "moneda_billetera", lambda email: "BOB")
    stores.acreditar("bo@x.com", 5000)
    r = client.post("/pagos/torneo/inscribir", json={
        "email": "bo@x.com", "academia_dueno": org, "cuota_soles": 20, "moneda": "BOB"}).json()
    assert r["ok"] and r["comision_centimos"] == 300
    # Saldo en otra moneda: no se cobra.
    monkeypatch.setattr(pagos_router, "moneda_billetera", lambda email: "PEN")
    stores.acreditar("pe@x.com", 5000)
    r = client.post("/pagos/torneo/inscribir", json={
        "email": "pe@x.com", "academia_dueno": org, "cuota_soles": 10, "moneda": "USD"}).json()
    assert r["ok"] is False and r["error"] == "moneda_distinta"
    assert stores.saldo_centimos("pe@x.com") == 5000


def test_torneo_sin_moneda_sigue_en_soles_para_apks_viejos():
    stores.acreditar("viejo@x.com", 5000)
    r = client.post("/pagos/torneo/inscribir", json={
        "email": "viejo@x.com", "academia_dueno": "org@x.com", "cuota_soles": 10}).json()
    assert r["ok"] and r["comision_centimos"] == 200  # mínimo S/ 2
    assert next(p for p in stores.pagos if p.tipo == "inscripcion_torneo").moneda == "PEN"


def test_recarga_qr_y_regalo_en_la_moneda_de_la_billetera(monkeypatch):
    avisos = []
    monkeypatch.setattr(pagos_router, "_aviso_push_usuario", lambda email, t, c, **k: avisos.append(c))
    monkeypatch.setattr(pagos_router, "moneda_billetera", lambda email: "BOB")
    monkeypatch.setattr(config, "ADMIN_PANEL_TOKEN", "adm")
    sol = client.post("/pagos/recarga-qr", json={"email": "bo@x.com", "monto_soles": 50, "foto_url": "x"}).json()
    assert sol["ok"] and sol["solicitud"]["moneda"] == "BOB"
    r = client.post(f"/pagos/recarga-qr/{sol['solicitud']['id']}/aprobar", headers={"X-Admin-Token": "adm"}).json()
    assert r["ok"]
    rec = next(p for p in stores.pagos if p.tipo == "recarga")
    assert rec.moneda == "BOB" and avisos and avisos[0].startswith("+Bs 50.00") and "S/" not in avisos[0]
    r = client.post("/pagos/regalo-saldo", json={"email": "bo@x.com", "soles": 35},
                    headers={"X-Admin-Token": "adm"}).json()
    assert r["ok"]
    assert next(p for p in stores.pagos if p.tipo == "bono_bienvenida").moneda == "BOB"
    assert "Bs 35.00" in avisos[-1] and "S/" not in avisos[-1]


def test_matricula_se_registra_en_la_moneda_del_pais():
    r = client.post("/pagos/matricula", json={
        "academia_id": "ac_ec", "monto_soles": 40, "matricula_id": "m_ec_1", "pais": "ec"}).json()
    assert r["ok"]
    assert next(p for p in stores.pagos if p.culqi_charge_id == "m_ec_1").moneda == "USD"


# ── 3. ELO de retos en el servidor ───────────────────────────────────────────

def _apk_calcular_elo(mi, rival, gane, k=0.15):
    """Transcripción literal de `Nivel.calcularElo` (lib/models/nivel.dart)."""
    esperado = 1 / (1 + pow(10, (rival - mi) / 2))
    real = 1.0 if gane else 0.0
    return max(1.0, min(7.0, mi + k * (real - esperado)))


def test_formula_elo_igual_al_apk_ejemplo_resuelto():
    # Ana 4.0 le gana a Luis 3.0: esperado(Ana) = 1/(1+10^(-0.5)) = 0.759747
    # Ana: 4.0 + 0.15·(1 − 0.759747) = 4.036038 · Luis: 3.0 − 0.15·0.240253 = 2.963962
    assert elo.calcular_elo(4.0, 3.0, True) == pytest.approx(4.036038, abs=1e-6)
    assert elo.calcular_elo(3.0, 4.0, False) == pytest.approx(2.963962, abs=1e-6)
    for mi, rival in ((1.0, 7.0), (7.0, 1.0), (3.3, 3.3), (5.2, 2.1), (1.02, 6.9)):
        for gane in (True, False):
            assert elo.calcular_elo(mi, rival, gane) == pytest.approx(_apk_calcular_elo(mi, rival, gane))
    g, p = elo.nuevos_niveles({"nivel": 4.0, "partidos": 9, "victorias": 6}, {})
    assert g == {"nivel": pytest.approx(4.036038, abs=1e-6), "partidos": 10, "victorias": 7}
    assert p == {"nivel": pytest.approx(elo.calcular_elo(3.0, 4.0, False)), "partidos": 1, "victorias": 0}


@pytest.fixture
def base_niveles(monkeypatch):
    """`pichangol_niveles` en memoria: la misma lectura/escritura de `_aplicar_en_base`."""
    tabla: dict[tuple[str, str], dict] = {}
    caida = {"on": False}

    def _aplicar(deporte, ganador, perdedor):
        if caida["on"]:
            return None
        antes_g = dict(tabla.get((ganador, deporte)) or {"nivel": 3.0, "partidos": 0, "victorias": 0})
        antes_p = dict(tabla.get((perdedor, deporte)) or {"nivel": 3.0, "partidos": 0, "victorias": 0})
        g, p = elo.nuevos_niveles(antes_g, antes_p)
        tabla[(ganador, deporte)] = g
        tabla[(perdedor, deporte)] = p
        return {ganador: {"antes": antes_g["nivel"], "despues": g["nivel"]},
                perdedor: {"antes": antes_p["nivel"], "despues": p["nivel"]}}
    monkeypatch.setattr(elo, "_aplicar_en_base", _aplicar)
    return {"tabla": tabla, "caida": caida}


def _reto(retador="ana@x.com", retado="luis@x.com", **extra):
    j = client.post("/retos/crear", json={"retador_email": retador, "retado_email": retado,
                                          "deporte": "tenis", **extra}).json()
    assert j["ok"], j
    return j["reto"]["id"]


def test_elo_se_aplica_una_vez_al_confirmar_el_reto(base_niveles):
    t = base_niveles["tabla"]
    t[("ana@x.com", "tenis")] = {"nivel": 4.0, "partidos": 9, "victorias": 6}
    rid = _reto()
    client.post(f"/retos/{rid}/responder", json={"aceptar": True})
    client.post(f"/retos/{rid}/resultado", json={"ganador_email": "ana@x.com", "reportado_por": "ana@x.com"})
    # Por confirmar: todavía no cuenta.
    assert t[("ana@x.com", "tenis")]["nivel"] == 4.0 and ("luis@x.com", "tenis") not in t
    client.post(f"/retos/{rid}/confirmar", json={"por_email": "luis@x.com", "acepta": True})
    assert t[("ana@x.com", "tenis")] == {"nivel": pytest.approx(4.036038, abs=1e-6), "partidos": 10, "victorias": 7}
    assert t[("luis@x.com", "tenis")]["nivel"] == pytest.approx(2.963962, abs=1e-6)
    assert stores.retos_elo[str(rid)]["estado"] == "aplicado"
    # Idempotente: confirmar otra vez, listar o reintentar no lo vuelve a aplicar.
    client.post(f"/retos/{rid}/confirmar", json={"por_email": "luis@x.com", "acepta": True})
    client.get("/retos/ana@x.com")
    client.get("/retos")
    elo.marcar_jugado(next(r for r in stores.retos if r.id == rid))
    assert t[("ana@x.com", "tenis")]["partidos"] == 10
    # Viaja en el snapshot.
    estado = stores.to_state()
    assert estado["retos_elo"][str(rid)]["estado"] == "aplicado"


def test_elo_dobles_se_omite_y_auto_confirmados_cuentan(base_niveles):
    t = base_niveles["tabla"]
    stores.config["retos_confirmacion_horas"] = "0"
    rid = _reto(modalidad="dobles", retador2_email="c@x.com", retado2_email="d@x.com")
    client.post(f"/retos/{rid}/resultado", json={"ganador_email": "ana@x.com"})
    assert stores.retos_elo[str(rid)]["estado"] == "omitido" and t == {}
    # Auto-confirmado por plazo vencido también aplica (una vez).
    stores.config["retos_confirmacion_horas"] = "24"
    rid2 = _reto(retador="e@x.com", retado="f@x.com")
    client.post(f"/retos/{rid2}/resultado", json={"ganador_email": "f@x.com", "reportado_por": "f@x.com"})
    r = next(x for x in stores.retos if x.id == rid2)
    r.reportado_en = r.reportado_en - timedelta(hours=30)
    client.get("/retos/e@x.com")
    assert stores.retos_elo[str(rid2)]["estado"] == "aplicado"
    assert t[("f@x.com", "tenis")]["victorias"] == 1 and t[("e@x.com", "tenis")]["partidos"] == 1


def test_elo_migracion_retos_jugados_antes_no_se_aplican_y_reintento_si_la_base_cae(base_niveles):
    t = base_niveles["tabla"]
    # Un reto que ya estaba JUGADO antes del despliegue (lo aplicó el APK en el
    # teléfono): el servidor no lo toca nunca.
    stores.config["retos_confirmacion_horas"] = "0"
    rid = _reto()
    client.post(f"/retos/{rid}/resultado", json={"ganador_email": "ana@x.com"})
    stores.retos_elo.clear()
    t.clear()
    client.get("/retos/ana@x.com")
    client.get("/retos")
    assert t == {} and str(rid) not in stores.retos_elo
    # Base caída al confirmar: queda pendiente y se aplica al listar.
    base_niveles["caida"]["on"] = True
    rid2 = _reto(retador="g@x.com", retado="h@x.com")
    client.post(f"/retos/{rid2}/resultado", json={"ganador_email": "h@x.com"})
    assert stores.retos_elo[str(rid2)]["estado"] == "pendiente" and t == {}
    base_niveles["caida"]["on"] = False
    client.get("/retos/g@x.com")
    assert stores.retos_elo[str(rid2)]["estado"] == "aplicado"
    assert t[("h@x.com", "tenis")]["victorias"] == 1
