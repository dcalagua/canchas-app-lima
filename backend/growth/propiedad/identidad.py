"""Consulta de DNI (identidad del reclamante) vía Factiliza.

Se usa SOLO para validar la identidad de quien reclama una cancha (filtro de
identidad), con su consentimiento. Dato personal (Ley 29733): finalidad acotada,
lo ve el equipo para validar, no se publica. El token nunca va en el APK: se lee
de `FACTILIZA_API_TOKEN` (variable del despliegue). Fail-safe: sin token o ante
error devuelve no-disponible y el flujo sigue (validación humana igual).
"""

from __future__ import annotations

import json
import urllib.request

import config


def disponible() -> bool:
    return bool(config.FACTILIZA_API_TOKEN)


def _valido(dni: str | None) -> bool:
    return bool(dni) and dni.isdigit() and len(dni) == 8


def consultar_dni(dni: str) -> dict:
    """Devuelve {ok, dni, nombre_completo, nombres, apellido_paterno,
    apellido_materno} o {ok: False, error}. Nunca lanza."""
    if not _valido(dni):
        return {"ok": False, "error": "dni_invalido"}
    if not disponible():
        return {"ok": False, "error": "no_configurado"}

    url = f"{config.FACTILIZA_BASE_URL}/dni/info/{dni}"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {config.FACTILIZA_API_TOKEN}",
            "Accept": "application/json",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:160]}

    if not payload.get("success"):
        return {"ok": False, "error": "no_encontrado"}
    data = payload.get("data") or {}
    nombres = data.get("nombres")
    ap = data.get("apellido_paterno")
    am = data.get("apellido_materno")
    completo = data.get("nombre_completo") or " ".join(
        x for x in [nombres, ap, am] if x)
    return {
        "ok": True,
        "dni": dni,
        "nombre_completo": completo,
        "nombres": nombres,
        "apellido_paterno": ap,
        "apellido_materno": am,
        # Para calcular la EDAD real (categorías Sub-N de campeonatos). Formato
        # de Factiliza; el APK parsea y calcula la edad actual.
        "fecha_nacimiento": data.get("fecha_nacimiento"),
    }


def _ruc_valido(ruc: str | None) -> bool:
    return bool(ruc) and ruc.isdigit() and len(ruc) == 11


def consultar_ruc(ruc: str) -> dict:
    """Devuelve {ok, ruc, razon_social, estado, direccion} o {ok: False, error}.
    Identifica el NEGOCIO (no es dato personal). Nunca lanza."""
    if not _ruc_valido(ruc):
        return {"ok": False, "error": "ruc_invalido"}
    if not disponible():
        return {"ok": False, "error": "no_configurado"}

    url = f"{config.FACTILIZA_BASE_URL}/ruc/info/{ruc}"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {config.FACTILIZA_API_TOKEN}",
            "Accept": "application/json",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:160]}

    if not payload.get("success"):
        return {"ok": False, "error": "no_encontrado"}
    data = payload.get("data") or {}
    razon = (data.get("nombre_o_razon_social") or data.get("razon_social")
             or data.get("nombre"))
    return {
        "ok": True,
        "ruc": ruc,
        "razon_social": razon,
        "estado": (data.get("estado") or "").upper() or None,
        "direccion": data.get("direccion_completa") or data.get("direccion"),
    }
