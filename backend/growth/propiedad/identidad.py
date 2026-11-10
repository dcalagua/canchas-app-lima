"""Consulta de DNI (identidad del reclamante) vía Factiliza.

Se usa SOLO para validar la identidad de quien reclama una cancha (filtro de
identidad), con su consentimiento. Dato personal (Ley 29733): finalidad acotada,
lo ve el equipo para validar, no se publica. El token nunca va en el APK: se lee
de `FACTILIZA_API_TOKEN` (variable del despliegue). Fail-safe: sin token o ante
error devuelve no-disponible y el flujo sigue (validación humana igual).
"""

from __future__ import annotations

import json
import urllib.error
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


# --- Cédula ECUADOR (CipherByte), espejo de consultar_dni ------------------
def cedula_disponible() -> bool:
    return bool(config.CIPHERBYTE_API_TOKEN)


def _cedula_valida(c: str | None) -> bool:
    return bool(c) and c.isdigit() and len(c) == 10


def _primero(d: dict, claves: list[str]):
    """Primer valor no vacío entre varias claves candidatas (la respuesta de
    CipherByte puede nombrar los campos de distintas formas)."""
    for k in claves:
        v = d.get(k)
        if v not in (None, ""):
            return v
    return None


def consultar_cedula(cedula: str) -> dict:
    """Consulta la cédula ecuatoriana (CipherByte). Devuelve {ok, cedula,
    nombre_completo, nombres, apellidos, fecha_nacimiento} o {ok: False, error}.
    Parseo DEFENSIVO: la respuesta puede venir anidada y con nombres de campo
    variados; se prueban varias variantes. Nunca lanza."""
    if not _cedula_valida(cedula):
        return {"ok": False, "error": "cedula_invalida"}
    if not cedula_disponible():
        return {"ok": False, "error": "no_configurado"}

    url = f"{config.CIPHERBYTE_BASE_URL}/cedula/{cedula}"

    def _pedir(headers: dict) -> tuple[dict | None, str | None, int]:
        req = urllib.request.Request(
            url, headers={"Accept": "application/json", **headers},
            method="GET")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode("utf-8")), None, 200
        except urllib.error.HTTPError as e:  # noqa: PERF203
            return None, str(e)[:160], e.code
        except Exception as e:  # noqa: BLE001
            return None, str(e)[:160], 0

    # El esquema es ApiKeyAuth: se intenta X-Api-Key y, si el gateway lo
    # rechaza por auth (401/403), se reintenta como Bearer (fallback).
    payload, err, code = _pedir({"X-Api-Key": config.CIPHERBYTE_API_TOKEN})
    if payload is None and code in (401, 403):
        payload, err, code = _pedir(
            {"Authorization": f"Bearer {config.CIPHERBYTE_API_TOKEN}"})
    if payload is None:
        return {"ok": False, "error": err or "sin_respuesta"}

    if not isinstance(payload, dict):
        return {"ok": False, "error": "respuesta_invalida"}

    # Bandera de éxito explícita (si viene y es negativa, corta).
    exito = payload.get("success", payload.get("ok", payload.get("status")))
    if exito is False or (isinstance(exito, str)
                          and exito.lower() in ("false", "error", "0", "fail")):
        return {"ok": False, "error": "no_encontrado"}

    # Desanida el contenedor de datos si la respuesta lo trae.
    data = payload
    for cont in ("data", "result", "resultado", "persona", "informacion",
                 "response", "datos"):
        if isinstance(payload.get(cont), dict):
            data = payload[cont]
            break

    nombres = _primero(data, ["nombres", "nombre", "names", "primer_nombre",
                              "firstName", "first_name"])
    apellidos = _primero(data, ["apellidos", "apellido", "lastName",
                                "last_name", "surname"])
    completo = _primero(data, ["nombre_completo", "nombreCompleto", "fullName",
                               "full_name", "nombres_completos",
                               "nombre_apellidos", "razon_social"])
    if not completo:
        completo = " ".join(x for x in [nombres, apellidos] if x) or None
    if not completo:
        # Sin nombre reconocible: trátalo como no encontrado (no rompas el flujo).
        return {"ok": False, "error": "no_encontrado"}

    fnac = _primero(data, ["fecha_nacimiento", "fechaNacimiento",
                           "fechanacimiento", "fecha_de_nacimiento",
                           "birthDate", "birth_date", "fecha_nac", "nacimiento"])
    return {
        "ok": True,
        "cedula": cedula,
        "nombre_completo": completo,
        "nombres": nombres,
        "apellidos": apellidos,
        # Para calcular la EDAD (categorías Sub-N). El APK parsea el formato.
        "fecha_nacimiento": fnac,
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
