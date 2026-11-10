"""Qué parte de `stores.config` puede salir por la API.

`stores.config` mezcla reglas de negocio editables (puntos, topes, tarifas) con
datos que NUNCA deben salir del servidor: secretos TOTP de la torre
(`admin_2fa_*`), hashes de recuperación, la cuenta de liquidaciones BCP, el logo
en base64, tokens de terceros. Antes `GET /config/incentivos` devolvía el dict
completo sin autenticación (fuga hallada en la auditoría del 26-oct-2026).

Regla: lo PÚBLICO es lista blanca (solo claves conocidas de `CONFIG_DEFAULT`
que no sean sensibles); lo SENSIBLE es lista negra por prefijo/sufijo y no sale
ni siquiera hacia un admin (los secretos tienen sus propios endpoints).
"""

from __future__ import annotations

from db.store import CONFIG_DEFAULT

# Prefijos de claves que jamás se devuelven ni se reescriben por la API genérica.
_PREFIJOS_SENSIBLES = (
    "admin_2fa",       # secreto TOTP, hashes de recuperación, fecha de enrolamiento
    "admin_",          # cualquier dato de operadores de la torre
    "liq_bcp",         # cuenta bancaria de liquidaciones
    "marca_logo_b64",  # binario: no es config, pesa y no aporta
    "meta_",           # tokens de Meta/redes
    "culqi_",
    "payphone_",
    "libelula_",
)
# Sufijos que delatan un secreto aunque la clave sea nueva.
_SUFIJOS_SENSIBLES = ("_token", "_secret", "_secreto", "_key", "_clave", "_password", "_pass")


def es_sensible(clave: str) -> bool:
    c = (clave or "").strip().lower()
    return c.startswith(_PREFIJOS_SENSIBLES) or c.endswith(_SUFIJOS_SENSIBLES)


def publica(config: dict[str, str]) -> dict[str, str]:
    """Vista anónima: solo claves de la lista blanca (CONFIG_DEFAULT) no sensibles."""
    return {k: config.get(k, v) for k, v in CONFIG_DEFAULT.items() if not es_sensible(k)}


def para_admin(config: dict[str, str]) -> dict[str, str]:
    """Vista del operador: todo lo editable, sin secretos."""
    return {k: v for k, v in config.items() if not es_sensible(k)}
