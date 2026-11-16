"""Las llamadas a Claude del marketing deben ser válidas para el SDK instalado.

Caso real (QAS, oct-2026): el SDK 1.x ya no acepta `temperature` y la llamada
fallaba con TypeError antes de salir; todo caía en silencio a reglas/plantillas.
Aquí se intercepta `messages.create` y se validan los argumentos contra su firma
REAL, así un argumento que el SDK no conoce rompe el test y no la producción.
"""
import inspect
import json
from types import SimpleNamespace

import anthropic
import pytest

import config
from marketing import post_redes
from marketing.agente_ia import creador, estratega, ia

FIRMA = inspect.signature(anthropic.resources.Messages.create)


class _Mensajes:
    def __init__(self, respuestas):
        self.llamadas, self._resp = [], list(respuestas)

    def create(self, **kw):
        FIRMA.bind(None, **kw)          # TypeError si el SDK no acepta algún argumento
        self.llamadas.append(kw)
        r = self._resp.pop(0)
        if isinstance(r, Exception):
            raise r
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=r)])


@pytest.fixture
def cliente(monkeypatch):
    estado = {}

    def fabricar(respuestas):
        m = _Mensajes(respuestas)
        estado["m"] = m
        monkeypatch.setattr(anthropic, "Anthropic", lambda **_: SimpleNamespace(messages=m))
        return m

    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "sk-prueba")
    return fabricar


def test_estratega_pide_json_estructurado_sin_argumentos_viejos(cliente):
    m = cliente([json.dumps({"elegidas": [{"id": "c1", "content_type": "post", "hora": "18:00", "por_que": "x"}]})])
    d = estratega._con_ia({"candidatas": []})
    assert d["elegidas"][0]["id"] == "c1"
    kw = m.llamadas[0]
    assert "temperature" not in kw and kw["output_config"]["format"]["type"] == "json_schema"
    assert kw["max_tokens"] >= 4000


def test_creador_pide_json_estructurado(cliente):
    m = cliente([json.dumps({"titulo": "T", "subtitulo": "S", "etiqueta": "", "texto": "Hola", "cta": "Reserva"})])
    assert creador._con_ia({"hechos": {}})["texto"] == "Hola"
    assert m.llamadas[0]["model"] == config.MARKETING_COPY_MODEL


def test_si_el_modelo_no_acepta_salida_estructurada_reintenta_sin_ella(cliente):
    err = anthropic.BadRequestError.__new__(anthropic.BadRequestError)
    Exception.__init__(err, "output_config no soportado")
    m = cliente([err, 'Aquí va: {"titulo":"T","subtitulo":"","etiqueta":"","texto":"Ok","cta":""}'])
    assert creador._con_ia({})["texto"] == "Ok"
    assert "output_config" in m.llamadas[0] and "output_config" not in m.llamadas[1]


def test_rechazo_o_corte_cae_al_respaldo(cliente, monkeypatch):
    m = cliente(["{}"])
    orig = m.create

    def cortado(**kw):
        r = orig(**kw)
        r.stop_reason = "max_tokens"
        return r
    m.create = cortado
    assert ia.pedir_json(modelo="x", sistema="s", contenido="c", esquema={"type": "object"}) is None


def test_redactor_de_facebook_sin_argumentos_viejos(cliente):
    m = cliente([json.dumps({"titulo": "T", "subtitulo": "S", "etiqueta": "", "texto": "Hola"})])
    assert post_redes._con_claude_redactor({})["texto"] == "Hola"
    assert "temperature" not in m.llamadas[0]
