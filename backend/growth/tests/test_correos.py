"""Correos de PAGO (`correos.py`): cada pago manda el RECIBO a quien pagó y el
AVISO a quien recibe (dueño de la cancha, academia, vendedor, organizador,
boleador), uno por reserva/pago aunque el APK liquide turno por turno, sin
repetirse y con reintentos."""

import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config  # noqa: E402
import correos  # noqa: E402
from db.store import stores  # noqa: E402
from web import datos  # noqa: E402

JUG, DUENO, PROFE, VEND = "jugador@gmail.com", "dueno@gmail.com", "profe@gmail.com", "vende@gmail.com"

CANCHA = {"id": "u1", "nombre": "Fútbol 1", "club": "Golazo Surco", "dueno": DUENO, "direccion": "Av. Siempre Viva 123",
          "lat": -12.1, "lng": -77.0}
FILAS = [
    {"id": "r1", "cancha_id": "u1", "jugador": "Ana Pérez", "fecha": "2026-10-10", "hora_inicio": "19:00", "hora_fin": "20:00",
     "precio": 60, "usuario": JUG, "extras": [{"clave": "arbitro", "nombre": "Árbitro", "precio": 20}], "telefono": "987654321",
     "grupo_reserva_id": "g1", "medio_pago": "yape", "moneda": "S/"},
    {"id": "r2", "cancha_id": "u1", "jugador": "Ana Pérez", "fecha": "2026-10-10", "hora_inicio": "20:00", "hora_fin": "21:00",
     "precio": 60, "usuario": JUG, "extras": [], "telefono": "987654321", "grupo_reserva_id": "g1", "medio_pago": "yape", "moneda": "S/"},
]


@pytest.fixture(autouse=True)
def _limpio(monkeypatch):
    stores.reset()
    stores.correos, stores.correos_eventos = [], []
    monkeypatch.setattr(config, "APP_API_KEY", "", raising=False)
    import pagos.router as PR
    monkeypatch.setattr(PR, "_aviso_push_usuario", lambda *a, **k: None)
    monkeypatch.setattr(datos, "reservas_de", lambda ids: [dict(f) for f in FILAS if f["id"] in ids])
    monkeypatch.setattr(datos, "reservas_por_grupo", lambda g: [dict(f) for f in FILAS if f["grupo_reserva_id"] == g])
    monkeypatch.setattr(datos, "cancha", lambda cid: dict(CANCHA) if cid == "u1" else None)
    yield


def _despues(seg=120):
    return datetime.now(timezone.utc) + timedelta(seconds=seg)


def _correr(enviados, seg=120):
    return correos.procesar(_despues(seg), enviar_fn=lambda m: enviados.append(dict(m)) or "id_prov")


def test_reserva_de_dos_turnos_un_recibo_al_jugador_y_un_aviso_al_dueno():
    from pagos.router import LiquidacionOnlineReq, post_liquidacion_online
    stores.registrar_pago(tipo="reserva", monto_centimos=14600, moneda="PEN", estado="aprobado", email=JUG,
                          culqi_charge_id="chr_test_abc123", medio="yape")
    # El APK liquida TURNO por TURNO (dos llamadas) con el mismo cargo.
    for rid, monto in (("r1", 80), ("r2", 60)):
        post_liquidacion_online(LiquidacionOnlineReq(dueno_id=DUENO, monto_soles=monto, reserva_id=rid, medio="yape",
                                                     moneda="PEN", charge_id="chr_test_abc123",
                                                     cargo_servicio_centimos=300 if rid == "r1" else 300))
    # Antes del rebote no sale nada.
    enviados = []
    assert correos.procesar(datetime.now(timezone.utc), enviar_fn=lambda m: enviados.append(dict(m)))["armados"] == 0
    r = _correr(enviados)
    assert r["enviados"] == 2 and len(enviados) == 2
    cli = next(m for m in enviados if m["rol"] == "cliente")
    due = next(m for m in enviados if m["rol"] == "dueno")
    assert cli["para"] == JUG and "Golazo Surco" in cli["asunto"]
    for txt in ("19:00–21:00", "Árbitro", "Cargo por servicio Pichangol", "S/ 146.00", "chr_test_abc123", "/reserva/g1"):
        assert txt in cli["html"], txt
    assert due["para"] == DUENO and "Recibes" in due["html"] and "Comisión Pichangol" in due["html"]
    assert "Ana Pérez" in due["html"] and "987654321" in due["html"]
    # Sin repetir: otra pasada no vuelve a mandar.
    assert _correr(enviados)["enviados"] == 0 and len(enviados) == 2
    assert all(m["estado"] == "enviado" and not m["html"] for m in stores.correos)


def test_sena_dice_cuanto_falta_pagar_en_la_cancha():
    from pagos.router import LiquidacionOnlineReq, post_liquidacion_online
    post_liquidacion_online(LiquidacionOnlineReq(dueno_id=DUENO, monto_soles=42, reserva_id="r1", medio="sena", moneda="PEN"))
    enviados = []
    _correr(enviados)
    cli = next(m for m in enviados if m["rol"] == "cliente")
    assert "Por pagar en la cancha" in cli["html"] and "S/ 98.00" in cli["html"]  # 140 − 42


def test_matricula_familiar_recibo_al_pagador_y_aviso_a_la_academia(monkeypatch):
    from pagos.router import MatriculaReq, post_matricula
    aca = {"id": "ac_1", "nombre": "Academia Bola Verde", "dueno": PROFE, "moneda": "S/"}
    alumnos = [
        {"id": "al_1", "nombre": "Luis", "email": JUG, "cuotas": [{"concepto": "Bola Verde · 2x/sem · Octubre", "monto": 250, "operacionId": "chr_fam_999"}]},
        {"id": "al_2", "nombre": "Sofía", "email": JUG, "cuotas": [{"concepto": "Bola Naranja · 2x/sem · Octubre", "monto": 200, "operacionId": "chr_fam_999"}]},
    ]
    monkeypatch.setattr(datos, "academia", lambda aid: dict(aca) if aid == "ac_1" else None)
    monkeypatch.setattr(datos, "matriculas_por_operacion", lambda aid, op: alumnos if op == "chr_fam_999" else [])
    stores.registrar_pago(tipo="cobro_web", monto_centimos=43500, moneda="PEN", estado="aprobado", email=JUG,
                          culqi_charge_id="chr_fam_999", medio="tarjeta")
    post_matricula(MatriculaReq(academia_id="ac_1", monto_soles=430, matricula_id="chr_fam_999", charge_id="chr_fam_999",
                                cargo_servicio_centimos=500))
    enviados = []
    _correr(enviados)
    cli = next(m for m in enviados if m["rol"] == "cliente")
    due = next(m for m in enviados if m["rol"] == "dueno")
    assert cli["para"] == JUG and due["para"] == PROFE
    for txt in ("Luis", "Sofía", "Descuentos", "S/ 435.00", "chr_fam_999"):
        assert txt in cli["html"], txt
    assert "Recibes" in due["html"] and "Luis, Sofía" in due["html"]


def test_venta_marketplace_comprador_y_vendedor():
    from pagos.router import VentaProductoReq, post_venta
    post_venta(VentaProductoReq(vendedor_id=VEND, monto_soles=120, venta_id="chr_v1", producto_nombre="Raqueta Wilson",
                                comprador_email=JUG, comprador_nombre="Ana", vendedor_nombre="Tienda Beto", moneda="PEN"))
    enviados = []
    _correr(enviados)
    assert {(m["rol"], m["para"]) for m in enviados} == {("cliente", JUG), ("dueno", VEND)}
    assert all("Raqueta Wilson" in m["html"] for m in enviados)


def test_recarga_y_pro_solo_a_quien_paga_y_multimoneda():
    stores.registrar_pago(tipo="recarga", monto_centimos=2000, moneda="USD", estado="aprobado", dueno_id=JUG, email=JUG,
                          concepto="Recarga (PayPhone)")
    # Movimientos internos (comisión, bonos) no mandan correo.
    stores.registrar_pago(tipo="comision_reserva", monto_centimos=200, moneda="PEN", estado="aprobado", dueno_id=DUENO)
    stores.registrar_pago(tipo="recarga", monto_centimos=500, moneda="PEN", estado="rechazado", dueno_id=JUG)
    enviados = []
    _correr(enviados)
    assert len(enviados) == 1 and enviados[0]["para"] == JUG and "$ 20.00" in enviados[0]["asunto"]


def test_boleador_recibe_solicitud_pagada_y_confirmacion():
    correos.encolar("boleo_solicitud", datos={"id": "bs_1", "boleador_email": "bol@gmail.com", "cliente_nombre": "Ana",
                                              "club": "Club Raqueta", "fecha": "2026-10-10", "hora_inicio": "08:00",
                                              "hora_fin": "09:00", "turnos": 1, "monto_centimos": 2000, "comision_centimos": 200,
                                              "moneda": "PEN", "data": {"boleador_nombre": "Rafa"}})
    stores.registrar_pago(tipo="liquidacion_boleador", monto_centimos=2000, moneda="PEN", estado="aprobado",
                          dueno_id="bol@gmail.com", culqi_charge_id="bol:bs_1", comision_centimos=200, concepto="🎾 Boleador · Rafa")
    enviados = []
    _correr(enviados)
    assert [m["para"] for m in enviados] == ["bol@gmail.com", "bol@gmail.com"]
    assert any("Ganas" in m["html"] and "S/ 18.00" in m["html"] for m in enviados)


def test_sin_proveedor_queda_visible_y_fallos_se_reintentan(monkeypatch):
    for k in ("RESEND_API_KEY", "SMTP_HOST"):
        monkeypatch.delenv(k, raising=False)
    stores.registrar_pago(tipo="recarga", monto_centimos=2000, moneda="PEN", estado="aprobado", dueno_id=JUG, email=JUG)
    r = correos.procesar(_despues())
    assert r["sin_proveedor"] == 1 and stores.correos[0]["estado"] == "sin_proveedor"
    # La torre lo puede reintentar; si el proveedor falla, se reintenta con espera.
    assert correos.reintentar(stores.correos[0]["id"])

    def falla(m):
        raise RuntimeError("Resend 500")
    correos.procesar(_despues(), enviar_fn=falla)
    m = stores.correos[0]
    assert m["estado"] == "pendiente" and m["intentos"] == 1 and "500" in m["error"]
    enviados = []
    correos.procesar(_despues(30), enviar_fn=lambda x: enviados.append(dict(x)))  # aún no toca
    assert not enviados
    correos.procesar(_despues(200), enviar_fn=lambda x: enviados.append(dict(x)) or "ok")
    assert enviados and stores.correos[0]["estado"] == "enviado"


def test_la_cola_viaja_en_el_snapshot_y_la_torre_la_ve():
    stores.registrar_pago(tipo="recarga", monto_centimos=2000, moneda="PEN", estado="aprobado", dueno_id=JUG, email=JUG)
    st = stores.to_state()
    assert st["correos_eventos"] and st["correos_eventos"][0]["tipo"] == "recarga"
    stores.correos_eventos = []
    stores.load_state(st)
    assert stores.correos_eventos[0]["pago_id"]
    res = correos.resumen()
    assert res["en_espera"] == 1 and "remitente" in res


def test_reserva_sin_filas_espera_y_luego_se_descarta():
    stores.registrar_pago(tipo="liquidacion_online", monto_centimos=5000, moneda="PEN", estado="aprobado",
                          dueno_id=DUENO, culqi_charge_id="no_existe")
    enviados = []
    for i in range(1, correos.MAX_ARMADO + 1):
        correos.procesar(_despues(120 + 120 * i * i), enviar_fn=lambda m: enviados.append(dict(m)))
    assert not enviados and not stores.correos_eventos
