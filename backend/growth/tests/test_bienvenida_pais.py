"""Regalo de bienvenida POR PAÍS (decisión del director, sep-2026): S/ 20 en
Perú, $ 5 en Ecuador y Bs 35 en Bolivia, según las coordenadas de la cancha
activada. Un solo número para los tres países regalaba cuatro veces más en
Guayaquil que en Lima."""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from db.store import stores  # noqa: E402
from pagos.router import otorgar_bienvenida  # noqa: E402
from paises import moneda_de_pais, pais_de_coordenadas  # noqa: E402
from propiedad.reclamos import _bienvenida_al_activar  # noqa: E402


@pytest.fixture(autouse=True)
def _cfg():
    stores.config["bienvenida_pro_dias"] = "30"
    stores.config["bienvenida_saldo_soles"] = "20"
    stores.config["bienvenida_saldo_usd"] = "5"
    stores.config["bienvenida_saldo_bob"] = "35"
    yield
    for k in ("bienvenida_pro_dias", "bienvenida_saldo_soles",
              "bienvenida_saldo_usd", "bienvenida_saldo_bob"):
        stores.config[k] = "0"


def test_pais_por_coordenadas_espejo_del_apk():
    assert pais_de_coordenadas(-12.046, -77.043) == "PE"   # Lima
    assert pais_de_coordenadas(-2.170, -79.922) == "EC"    # Guayaquil
    assert pais_de_coordenadas(-0.180, -78.468) == "EC"    # Quito
    assert pais_de_coordenadas(-16.500, -68.150) == "BO"   # La Paz
    assert pais_de_coordenadas(-17.784, -63.182) == "BO"   # Santa Cruz
    assert pais_de_coordenadas(-15.840, -70.020) == "PE"   # Puno (solape)
    assert pais_de_coordenadas(None, None) == "PE"
    assert moneda_de_pais("EC") == "USD" and moneda_de_pais("BO") == "BOB"


def test_regalo_en_la_moneda_del_pais():
    for email, pais, cent, moneda in (
            ("pe@x.com", "PE", 2000, "PEN"),
            ("ec@x.com", "EC", 500, "USD"),
            ("bo@x.com", "BO", 3500, "BOB")):
        stores.bienvenidas.pop(email, None)
        stores.saldos_promo.pop(email, None)
        r = otorgar_bienvenida(email, pais=pais)
        assert r["ok"] and r["pais"] == pais and r["moneda"] == moneda
        assert stores.saldo_promo_centimos(email) == cent
        p = [x for x in stores.pagos
             if x.tipo == "bono_bienvenida" and x.dueno_id == email][-1]
        assert p.moneda == moneda and p.monto_centimos == cent
        assert stores.membresias_pro[email]["pais"] == pais


def test_activar_reclamo_usa_las_coordenadas_de_la_cancha():
    class R:  # lo mínimo que mira _bienvenida_al_activar
        solicitante_id = "gye@x.com"
        lat, lng = -2.19, -79.88  # Guayaquil
    stores.bienvenidas.pop("gye@x.com", None)
    stores.saldos_promo.pop("gye@x.com", None)
    _bienvenida_al_activar(R())
    assert stores.saldo_promo_centimos("gye@x.com") == 500  # $ 5, no S/ 20


def test_pais_desconocido_cae_a_peru_y_apagada_por_pais():
    stores.bienvenidas.pop("xx@x.com", None)
    stores.saldos_promo.pop("xx@x.com", None)
    r = otorgar_bienvenida("xx@x.com", pais="AR")
    assert r["pais"] == "PE" and stores.saldo_promo_centimos("xx@x.com") == 2000
    # Sin días y con $ 0 para Ecuador, en Ecuador no se regala nada.
    stores.config["bienvenida_pro_dias"] = "0"
    stores.config["bienvenida_saldo_usd"] = "0"
    stores.bienvenidas.pop("ec0@x.com", None)
    assert otorgar_bienvenida("ec0@x.com", pais="EC").get("apagada") is True
