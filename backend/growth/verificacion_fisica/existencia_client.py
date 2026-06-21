"""Cliente del módulo de EXISTENCIA (Capa IA). REUSA el verificador de existencia
ya construido (`/verificacion/existencia`).

Si `EXISTENCIA_API_URL` está definido, llama por HTTP a ese servicio. Si no, usa
un STUB determinista para correr/testear sin servicios reales.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from config import EXISTENCIA_API_URL


def verificar(cancha_id: str, direccion: str, ruc: str | None,
              lat: float | None, lng: float | None) -> dict:
    """Devuelve {score, fuente}. Fail-safe: ante error → stub."""
    if EXISTENCIA_API_URL:
        try:
            body = {"cancha_id": cancha_id, "direccion": direccion}
            if ruc:
                body["ruc"] = ruc
            if lat is not None and lng is not None:
                body["lat"] = lat
                body["lng"] = lng
            req = urllib.request.Request(
                f"{EXISTENCIA_API_URL.rstrip('/')}/verificacion/existencia",
                data=json.dumps(body).encode("utf-8"), method="POST",
                headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                j = json.loads(resp.read().decode("utf-8"))
            return {"score": int(j.get("score_existencia", 0)), "fuente": "existencia-api"}
        except Exception:
            pass  # cae al stub
    return _stub(direccion, ruc, lat, lng)


def _stub(direccion: str, ruc: str | None, lat: float | None,
          lng: float | None) -> dict:
    """Score determinista: con RUC + coords cae alto; informal sin datos, bajo."""
    score = 50
    if ruc:
        score += 25
    if lat is not None and lng is not None:
        score += 15
    if any(ch.isdigit() for ch in (direccion or "")):
        score += 5  # tiene número de calle
    return {"score": min(score, 100), "fuente": "stub"}
