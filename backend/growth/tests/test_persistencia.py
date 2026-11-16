"""Round-trip de la normalización a tablas (saldos/pagos/vistas/reclamos).

Prueba los mapeos PUROS del store (sin BD): extrae filas y las vuelve a cargar
en un store fresco, verificando que el estado crítico se reconstruye idéntico.
Es la garantía de que guardar_normalizado/cargar_normalizado (db/pg.py) no
pierden datos al ir y volver de las tablas.
"""

from db.store import ReclamoPropiedad, Stores, ahora


def _store_con_datos() -> Stores:
    s = Stores()
    # Saldo + pagos (plata)
    s.acreditar("dueno@x.com", 5000)
    s.acreditar("otro@x.com", 250)
    s.registrar_pago(
        tipo="recarga", monto_centimos=5000, moneda="PEN", estado="aprobado",
        dueno_id="dueno@x.com", culqi_charge_id="chg_1", email="dueno@x.com",
        concepto="Recarga S/50")
    s.registrar_pago(
        tipo="fee_reserva", monto_centimos=200, moneda="PEN", estado="aprobado",
        dueno_id=None, culqi_charge_id="chg_2", email="jug@x.com",
        concepto="Comisión reserva")
    # Vistas (impacto)
    s.registrar_vista("dueno@x.com", dia="2026-07-10", n=3)
    s.registrar_vista("dueno@x.com", dia="2026-07-11", n=2)
    s.registrar_vista("ac_1", dia="2026-07-11", n=7)
    # Reclamo
    s.reclamos.append(ReclamoPropiedad(
        id=s.next_id("reclamo"), cancha_id="c1", solicitante_id="dueno@x.com",
        nombre_local="Cancha La Bombonera", codigo="ABC123",
        estado="pendiente_triage", creado_en=ahora(),
        telefono_contacto="51999888777", dni="12345678", lat=-12.1, lng=-77.0,
        solicitante_lat=-12.1001, solicitante_lng=-77.0001))
    return s


def test_roundtrip_normalizado_no_pierde_datos():
    s = _store_con_datos()
    # Extrae filas como lo haría pg.guardar_normalizado.
    saldos = s.saldos_rows()
    pagos = s.pagos_rows()
    vistas = s.vistas_rows()
    reclamos = s.reclamos_rows()

    # Reconstruye en un store nuevo como lo haría pg.cargar_normalizado.
    fresh = Stores()
    fresh.cargar_saldos_rows(saldos)
    fresh.cargar_pagos_rows(pagos)
    fresh.cargar_vistas_rows(vistas)
    fresh.cargar_reclamos_rows(reclamos)

    # Saldos idénticos.
    assert fresh.saldos == s.saldos
    assert fresh.saldo_centimos("dueno@x.com") == 5000
    assert fresh.saldo_centimos("otro@x.com") == 250

    # Pagos: mismos ids, tipos y charge ids; el contador de ids se preserva.
    assert [p.id for p in fresh.pagos] == [p.id for p in s.pagos]
    assert fresh.pago_por_charge("chg_1").tipo == "recarga"
    assert fresh.pago_por_charge("chg_2").dueno_id is None
    assert fresh.next_id("pago") == s.next_id("pago")  # sigue tras el último

    # Vistas: resumen (7 días + total) coincide.
    assert fresh.vistas_resumen(["dueno@x.com"]) == s.vistas_resumen(["dueno@x.com"])
    assert fresh.vistas_resumen(["dueno@x.com"])["total"] == 5
    assert fresh.vistas_resumen(["ac_1"])["total"] == 7

    # Reclamo: reconstruido con sus campos clave y fechas.
    assert len(fresh.reclamos) == 1
    r = fresh.reclamos[0]
    assert r.cancha_id == "c1" and r.codigo == "ABC123"
    assert r.dni == "12345678" and r.telefono_contacto == "51999888777"
    assert r.creado_en == s.reclamos[0].creado_en


def test_cargar_vistas_acepta_fecha_date():
    """cargar_vistas_rows debe aceptar la fecha como `date` (lo que devuelve la
    BD) o como str ISO (snapshot), sin romper el resumen."""
    from datetime import date

    s = Stores()
    s.cargar_vistas_rows([("d1", date(2026, 7, 11), 4), ("d1", "2026-07-11", 0)])
    # Ambas claves se normalizan a str; la segunda pisa a 0 (mismo día).
    assert s.vistas["d1"]["2026-07-11"] == 0


def test_cargar_saldos_vacio_no_rompe():
    s = Stores()
    s.cargar_saldos_rows([])
    assert s.saldos == {}


def test_arranque_no_pierde_lo_que_la_tabla_no_guarda():
    """Bug real de PRD (2-oct-2026): al arrancar, `growth_pagos` (10 columnas)
    reemplazaba a los pagos del snapshot y una liquidación ya PAGADA volvía a
    'por pagar' (se perdían liquidado, medio, comisión, cargo…)."""
    from db import pg
    s = Stores()
    p = s.registrar_pago(tipo="liquidacion_online", monto_centimos=9000, moneda="PEN", estado="aprobado",
                         dueno_id="d@x.com", culqi_charge_id="res_1", medio="yape", comision_centimos=425,
                         cargo_servicio_centimos=538, cargo_id="chr_1")
    p.liquidado = True
    s.reclamos.append(ReclamoPropiedad(id=s.next_id("reclamo"), cancha_id="c1", solicitante_id="d@x.com",
                                       nombre_local="L", codigo="111111", estado="activada", creado_en=ahora(),
                                       foto_evidencia_url="https://x/ev.jpg"))
    filas_tabla = [{c: d.get(c) for c in pg._PAGO_COLS} for d in s.pagos_rows()]
    filas_tabla.append({"id": 99, "tipo": "recarga", "monto_centimos": 100, "moneda": "PEN", "estado": "aprobado",
                        "dueno_id": "z@x.com", "culqi_charge_id": "chg_99", "email": None, "concepto": None,
                        "creado_en": ahora().isoformat()})
    rec_tabla = [{c: d.get(c) for c in pg._RECLAMO_COLS} for d in s.reclamos_rows()]
    s2 = Stores()
    s2.load_state(s.to_state())          # 1) snapshot
    s2.cargar_pagos_rows(filas_tabla)    # 2) tablas normalizadas encima
    s2.cargar_reclamos_rows(rec_tabla)
    q = s2.pago_por_charge("res_1")
    assert q.liquidado is True and q.medio == "yape" and q.comision_centimos == 425
    assert q.cargo_servicio_centimos == 538 and q.cargo_id == "chr_1"
    assert s2.pago_por_charge("chg_99") is not None          # la tabla aún puede sumar los que faltan
    assert s2.next_id("pago") == 100
    assert s2.reclamos[0].foto_evidencia_url == "https://x/ev.jpg"
