"""Integración REAL (Postgres local) del repositorio de cobro directo: llave
cifrada, medios, vouchers con índices únicos anti-fraude y resolución
condicional (dos revisores a la vez no aprueban dos veces)."""

import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from pagos import cobro_directo as cd  # noqa: E402
from tests.conftest_pg import pg_local  # noqa: E402,F401


def _limpiar(pg):
    with pg.conexion() as conn, conn.cursor() as cur:
        for t in ("cl_pagos_manuales", "cl_medios_pago_club", "cl_pasarela_club"):
            cur.execute(f"delete from {t} where dueno like 'it_%%'")
        conn.commit()


def _pm(i, **kw):
    ahora = datetime.now(timezone.utc)
    base = {"id": f"pgm_it_{i}", "reserva_ref": f"ref_{i}", "reserva_ids": [f"web_{i}"], "cancha_id": "c1",
            "dueno": "it_club@x.com", "jugador_email": "ana@x.com", "jugador_nombre": "Ana", "monto_centimos": 3000,
            "moneda": "PEN", "medio": "yape", "operacion": f"OP{i}", "voucher_img": b"\xff\xd8jpeg",
            "voucher_mime": "image/jpeg", "voucher_hash": f"h{i}", "estado": "en_revision", "motivo_rechazo": "",
            "vence_en": ahora + timedelta(minutes=60), "resuelto_en": None, "resuelto_por": ""}
    return {**base, **kw}


def test_repo_pg_completo(pg_local):
    pg = pg_local
    _limpiar(pg)
    r = cd.RepoPG()
    r.guardar_pasarela({"dueno": "it_club@x.com", "proveedor": "culqi", "public_key": "pk_test_1",
                        "secret_key_cifrada": "gAAAA-cifrado", "secret_key_ult4": "9876", "modo": "test",
                        "webhook_ref": "wh_it", "activo": True, "verificada": True})
    assert r.pasarela_de("it_club@x.com")["public_key"] == "pk_test_1"
    assert r.pasarela_por_ref("wh_it")["dueno"] == "it_club@x.com"
    r.reemplazar_medios("it_club@x.com", [{"tipo": "yape", "titular": "Club", "numero": "987654321", "banco": "",
                                           "cuenta": "", "cci": "", "qr_url": "", "nota": ""}])
    r.reemplazar_medios("it_club@x.com", [{"tipo": "plin", "titular": "Club", "numero": "912345678", "banco": "",
                                           "cuenta": "", "cci": "", "qr_url": "", "nota": ""}])
    assert [m["tipo"] for m in r.medios_de("it_club@x.com")] == ["plin"]
    assert r.crear_pago_manual(_pm(1)) == ""
    assert r.crear_pago_manual(_pm(2, operacion="OP1")) == "operacion_repetida"
    assert r.crear_pago_manual(_pm(3, voucher_hash="h1")) == "voucher_repetido"
    assert r.crear_pago_manual(_pm(4, reserva_ref="ref_1")) == "ya_existe"
    assert r.imagen_voucher("pgm_it_1") == (b"\xff\xd8jpeg", "image/jpeg")
    assert r.pago_manual("pgm_it_1")["reserva_ids"] == ["web_1"]
    assert r.resolver_pago_manual("pgm_it_1", "aprobado", "it_club@x.com") is True
    assert r.resolver_pago_manual("pgm_it_1", "rechazado", "it_club@x.com") is False   # ya resuelto
    # Un voucher RECHAZADO libera su nº de operación (el jugador puede reintentar bien).
    assert r.crear_pago_manual(_pm(5, operacion="OP5")) == ""
    assert r.resolver_pago_manual("pgm_it_5", "rechazado", "it_club@x.com")
    assert r.crear_pago_manual(_pm(6, operacion="OP5", reserva_ref="ref_5")) == ""
    assert {p["id"] for p in r.pagos_manuales_de("it_club@x.com", ("en_revision",))} == {"pgm_it_6"}
    assert r.vencidos(datetime.now(timezone.utc) + timedelta(hours=2))[0]["id"] == "pgm_it_6"
    _limpiar(pg)
