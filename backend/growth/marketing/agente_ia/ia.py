"""Llamada a Claude que devuelve JSON, compartida por el estratega y el creador.

* SDK `anthropic` 1.x: `temperature`/`top_p`/`top_k` ya NO son argumentos de
  `messages.create()` (pasarlos es un `TypeError` antes de salir la petición;
  así falló en QAS el 20-oct-2026 y todo caía en silencio a reglas/plantillas).
* El JSON se pide con salida estructurada (`output_config.format` con un
  esquema): la respuesta llega como texto JSON válido. Si el modelo configurado
  no la admite (400), se reintenta UNA vez sin el formato y se extrae el JSON
  del texto.
* `max_tokens` amplio: en los modelos actuales el pensamiento adaptativo usa
  tokens de salida; con un tope chico la respuesta podía quedar sin texto.
* Nunca lanza: devuelve el dict o None (el llamador cae a su respaldo).
"""
from __future__ import annotations

import json
import re

MAX_TOKENS = 16000


def _texto(resp) -> str:
    return "".join(getattr(b, "text", "") for b in (resp.content or []) if getattr(b, "type", "") == "text")


def _json_de(texto: str) -> dict | None:
    try:
        d = json.loads(texto)
    except (TypeError, ValueError):
        m = re.search(r"\{.*\}", texto or "", re.DOTALL)
        if not m:
            return None
        try:
            d = json.loads(m.group(0))
        except ValueError:
            return None
    return d if isinstance(d, dict) else None


def pedir_json(*, modelo: str, sistema: str, contenido: str, esquema: dict, esfuerzo: str | None = None,
               etiqueta: str = "agente_ia") -> dict | None:
    import config
    if not config.ANTHROPIC_API_KEY:
        return None
    try:
        import anthropic
    except Exception:  # noqa: BLE001
        return None
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    base = {"model": modelo, "max_tokens": MAX_TOKENS, "system": sistema,
            "messages": [{"role": "user", "content": contenido}]}
    salida = {"format": {"type": "json_schema", "schema": esquema}}
    if esfuerzo:
        salida["effort"] = esfuerzo
    intentos = [dict(base, output_config=salida),
                dict(base, **({"output_config": {"effort": esfuerzo}} if esfuerzo else {}))]
    for i, params in enumerate(intentos):
        try:
            resp = client.messages.create(**params)
        except anthropic.BadRequestError as e:
            if i == 0:
                print(f"[{etiqueta}] el modelo {modelo} no aceptó salida estructurada, reintento sin ella: {str(e)[:160]}", flush=True)
                continue
            print(f"[{etiqueta}] IA rechazó la petición: {str(e)[:160]}", flush=True)
            return None
        except Exception as e:  # noqa: BLE001 — red, límites, auth: el llamador usa su respaldo
            print(f"[{etiqueta}] IA no respondió: {str(e)[:160]}", flush=True)
            return None
        if getattr(resp, "stop_reason", "") in ("refusal", "max_tokens"):
            print(f"[{etiqueta}] IA terminó con {resp.stop_reason}; se usa el respaldo", flush=True)
            return None
        return _json_de(_texto(resp))
    return None
