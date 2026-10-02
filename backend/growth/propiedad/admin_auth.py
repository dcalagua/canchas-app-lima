"""Autenticación de la TORRE DE CONTROL (/admin) por usuario + contraseña.

Los operadores se configuran en la env `ADMIN_PANEL_USUARIOS` con el formato
"correo:clave" separados por coma, p. ej.:

    ADMIN_PANEL_USUARIOS="dcalagua@ebim.pe:MiClaveSegura, soporte@ebim.pe:Otra"

El login (`POST /admin/api/login`) valida las credenciales y emite una SESIÓN
FIRMADA con expiración (HMAC-SHA256 con `ADMIN_PANEL_TOKEN` como llave de
firma). Esa sesión viaja en la cabecera `X-Admin-Token` igual que antes, así
todos los endpoints admin existentes siguen funcionando sin cambios.

Compatibilidad: el token clásico `ADMIN_PANEL_TOKEN` sigue siendo aceptado
(scripts/ops y respaldo si aún no se configuran usuarios). Fail-closed: sin
`ADMIN_PANEL_TOKEN` no hay firma posible y todo el panel responde 503.

VERIFICACIÓN EN DOS PASOS (sep-2026, pedido del director: "esta dirección es
crackeable"): con `ADMIN_2FA=1` (default), después de usuario+contraseña el
login exige un código TOTP (RFC 6238: Google/Microsoft Authenticator, Authy;
6 dígitos, 30 s, ±1 ventana, sin reuso del mismo código). El secreto de cada
operador se guarda CIFRADO en `stores.config[admin_2fa_<correo>]` (Fernet con
`META_TOKEN_KEY` vía `redes.cifrar`); la primera vez el operador ENROLA su
app escaneando el QR y recibe 8 códigos de recuperación de un solo uso
(solo se guarda su SHA-256). "Confiar en este dispositivo 30 días" emite un
token firmado `d1.` que se guarda en el navegador y salta el 2.º paso; se
invalida al "olvidar dispositivos" (epoch por usuario). Entre pasos viaja un
pre-token firmado `p1.` de 5 min, que NO sirve como sesión.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import struct
import time

import config
from db.store import stores

# Duración de la sesión del panel. Vencida, el panel devuelve 401 y la página
# vuelve sola al login (mismo manejo de 401 que ya existía).
SESION_HORAS = 12

_PREFIJO = "s1"  # versión del formato de sesión: s1.<usuario_b64>.<exp>.<firma>


def usuarios_configurados() -> dict[str, str]:
    """Mapa correo→clave desde ADMIN_PANEL_USUARIOS. Vacío si no está seteada."""
    out: dict[str, str] = {}
    for par in (config.ADMIN_PANEL_USUARIOS or "").split(","):
        par = par.strip()
        if not par or ":" not in par:
            continue
        correo, clave = par.split(":", 1)
        correo, clave = correo.strip().lower(), clave.strip()
        if correo and clave:
            out[correo] = clave
    return out


def credenciales_validas(usuario: str | None, clave: str | None) -> bool:
    esperada = usuarios_configurados().get((usuario or "").strip().lower())
    if esperada is None:
        # Comparar igual para no delatar por tiempo si el correo existe.
        hmac.compare_digest(clave or "", "x")
        return False
    return hmac.compare_digest(clave or "", esperada)


def _firma(usuario_b64: str, exp: int) -> str:
    return hmac.new(
        config.ADMIN_PANEL_TOKEN.encode(),
        f"{_PREFIJO}.{usuario_b64}.{exp}".encode(),
        hashlib.sha256,
    ).hexdigest()


def crear_sesion(usuario: str) -> str:
    """Token de sesión firmado, con expiración, para X-Admin-Token."""
    exp = int(time.time()) + SESION_HORAS * 3600
    ub = base64.urlsafe_b64encode(usuario.encode()).decode().rstrip("=")
    return f"{_PREFIJO}.{ub}.{exp}.{_firma(ub, exp)}"


def _sesion_valida(token: str) -> bool:
    partes = token.split(".")
    if len(partes) != 4 or partes[0] != _PREFIJO:
        return False
    _, ub, exp_txt, firma = partes
    try:
        exp = int(exp_txt)
    except ValueError:
        return False
    if exp < time.time():
        return False  # sesión vencida
    return hmac.compare_digest(firma, _firma(ub, exp))


def token_admin_valido(token: str | None) -> bool:
    """¿La cabecera X-Admin-Token trae el token clásico O una sesión vigente?"""
    if not config.ADMIN_PANEL_TOKEN or not token:
        return False
    if hmac.compare_digest(token, config.ADMIN_PANEL_TOKEN):
        return True
    return _sesion_valida(token)


# ── Verificación en dos pasos (TOTP) ─────────────────────────────────────────
PRE_MINUTOS = 5            # vigencia del pre-token entre contraseña y código
DISPOSITIVO_DIAS = 30      # "confiar en este dispositivo"
TOTP_PASO = 30
TOTP_DIGITOS = 6
TOTP_VENTANA = 1           # ±1 paso (reloj del teléfono desfasado ≤30 s)
RECUPERACION_N = 8
EMISOR = "Pichangol Torre"

_CFG_SECRETO = "admin_2fa_{u}"        # secreto TOTP cifrado
_CFG_DESDE = "admin_2fa_desde_{u}"    # epoch de enrolamiento
_CFG_REC = "admin_2fa_rec_{u}"        # json: hashes sha256 de los códigos de recuperación
_CFG_DISP_EPOCH = "admin_disp_epoch_{u}"  # dispositivos emitidos antes de esto no valen

_ultimo_contador: dict[str, int] = {}     # usuario -> último contador TOTP aceptado (anti-reuso)
_enrolando: dict[str, tuple[str, float]] = {}  # usuario -> (secreto pendiente, vence)


def dos_pasos_activo() -> bool:
    """`ADMIN_2FA=0` apaga el segundo paso (corte de emergencia). Default: encendido."""
    return (getattr(config, "ADMIN_2FA", "1") or "1").strip() not in ("0", "false", "no", "off")


def _cfg_key(plantilla: str, usuario: str) -> str:
    return plantilla.format(u=(usuario or "").strip().lower())


def totp_generar_secreto() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def totp_codigo(secreto: str, contador: int) -> str:
    """Código HOTP del contador (TOTP = contador de 30 s). SHA-1 como exigen las apps."""
    pad = "=" * (-len(secreto) % 8)
    llave = base64.b32decode((secreto + pad).upper())
    mac = hmac.new(llave, struct.pack(">Q", contador), hashlib.sha1).digest()
    off = mac[-1] & 0x0F
    num = (struct.unpack(">I", mac[off:off + 4])[0] & 0x7FFFFFFF) % (10 ** TOTP_DIGITOS)
    return str(num).zfill(TOTP_DIGITOS)


def totp_valido(usuario: str, secreto: str, codigo: str, ahora: float | None = None) -> bool:
    """Acepta el código del paso actual o ±TOTP_VENTANA; un mismo contador no se
    acepta dos veces (anti-reuso dentro de la ventana)."""
    cod = "".join(ch for ch in (codigo or "") if ch.isdigit())
    if len(cod) != TOTP_DIGITOS or not secreto:
        return False
    base = int((ahora if ahora is not None else time.time()) // TOTP_PASO)
    u = (usuario or "").strip().lower()
    for delta in range(-TOTP_VENTANA, TOTP_VENTANA + 1):
        c = base + delta
        if hmac.compare_digest(totp_codigo(secreto, c), cod):
            if c <= _ultimo_contador.get(u, -1):
                return False
            _ultimo_contador[u] = c
            return True
    return False


def otpauth_uri(usuario: str, secreto: str) -> str:
    from urllib.parse import quote
    etiqueta = quote(f"{EMISOR}:{usuario}", safe="")
    return f"otpauth://totp/{etiqueta}?secret={secreto}&issuer={quote(EMISOR)}&algorithm=SHA1&digits={TOTP_DIGITOS}&period={TOTP_PASO}"


def _cifrar(texto: str) -> str:
    from marketing import redes
    return redes.cifrar(texto)


def _descifrar(enc: str) -> str:
    from marketing import redes
    return redes.descifrar(enc)


def secreto_de(usuario: str) -> str:
    """Secreto TOTP en claro del operador enrolado ("" si no enroló)."""
    return _descifrar(stores.config.get(_cfg_key(_CFG_SECRETO, usuario), "") or "")


def enrolado(usuario: str) -> bool:
    return bool(secreto_de(usuario))


def iniciar_enrolamiento(usuario: str) -> str:
    """Secreto PENDIENTE (en memoria, 15 min): solo queda guardado cuando el
    operador demuestra que su app lo tiene, escribiendo un código válido."""
    u = (usuario or "").strip().lower()
    sec, vence = _enrolando.get(u, ("", 0.0))
    if not sec or vence < time.time():
        sec = totp_generar_secreto()
    _enrolando[u] = (sec, time.time() + 15 * 60)
    return sec


def _hash_rec(codigo: str) -> str:
    limpio = "".join(ch for ch in (codigo or "").upper() if ch.isalnum())
    return hashlib.sha256(f"rec:{limpio}".encode()).hexdigest()


def generar_recuperacion(usuario: str) -> list[str]:
    """8 códigos de un solo uso (XXXX-XXXX). Se guardan hasheados; se muestran UNA vez."""
    codigos = []
    for _ in range(RECUPERACION_N):
        raw = secrets.token_hex(4).upper()
        codigos.append(f"{raw[:4]}-{raw[4:]}")
    stores.config[_cfg_key(_CFG_REC, usuario)] = json.dumps([_hash_rec(c) for c in codigos])
    return codigos


def recuperacion_restantes(usuario: str) -> int:
    try:
        return len(json.loads(stores.config.get(_cfg_key(_CFG_REC, usuario), "") or "[]"))
    except Exception:  # noqa: BLE001
        return 0


def usar_recuperacion(usuario: str, codigo: str) -> bool:
    """Consume un código de recuperación (si existe). Cada uno vale una sola vez."""
    k = _cfg_key(_CFG_REC, usuario)
    try:
        hashes = json.loads(stores.config.get(k, "") or "[]")
    except Exception:  # noqa: BLE001
        hashes = []
    h = _hash_rec(codigo)
    ok = False
    restantes = []
    for x in hashes:
        if not ok and hmac.compare_digest(x, h):
            ok = True
            continue
        restantes.append(x)
    if ok:
        stores.config[k] = json.dumps(restantes)
    return ok


def confirmar_enrolamiento(usuario: str, codigo: str) -> list[str] | None:
    """Si el código coincide con el secreto pendiente, lo guarda cifrado y
    devuelve los códigos de recuperación. None si el código no vale."""
    u = (usuario or "").strip().lower()
    sec, vence = _enrolando.get(u, ("", 0.0))
    if not sec or vence < time.time() or not totp_valido(u, sec, codigo):
        return None
    stores.config[_cfg_key(_CFG_SECRETO, u)] = _cifrar(sec)
    stores.config[_cfg_key(_CFG_DESDE, u)] = str(int(time.time()))
    _enrolando.pop(u, None)
    return generar_recuperacion(u)


def restablecer(usuario: str) -> None:
    """Quita el 2.º paso del operador (perdió el teléfono): en su próximo login
    vuelve a enrolar. También olvida sus dispositivos de confianza."""
    u = (usuario or "").strip().lower()
    for plantilla in (_CFG_SECRETO, _CFG_DESDE, _CFG_REC):
        stores.config.pop(_cfg_key(plantilla, u), None)
    _enrolando.pop(u, None)
    _ultimo_contador.pop(u, None)
    olvidar_dispositivos(u)


def enrolado_desde(usuario: str) -> int:
    try:
        return int(stores.config.get(_cfg_key(_CFG_DESDE, usuario), "") or 0)
    except ValueError:
        return 0


# ── Tokens firmados auxiliares: pre-sesión (p1) y dispositivo de confianza (d1) ──
def _firmar(prefijo: str, ub: str, exp: int, extra: str = "") -> str:
    return hmac.new(config.ADMIN_PANEL_TOKEN.encode(), f"{prefijo}.{ub}.{exp}.{extra}".encode(),
                    hashlib.sha256).hexdigest()


def _ub(usuario: str) -> str:
    return base64.urlsafe_b64encode(usuario.strip().lower().encode()).decode().rstrip("=")


def _de_ub(ub: str) -> str:
    try:
        return base64.urlsafe_b64decode((ub + "=" * (-len(ub) % 4)).encode()).decode()
    except Exception:  # noqa: BLE001
        return ""


def crear_pre_sesion(usuario: str) -> str:
    exp = int(time.time()) + PRE_MINUTOS * 60
    ub = _ub(usuario)
    return f"p1.{ub}.{exp}.{_firmar('p1', ub, exp)}"


def usuario_de_pre_sesion(token: str | None) -> str:
    """Usuario del pre-token vigente, o "" si no vale (o si ya venció)."""
    if not config.ADMIN_PANEL_TOKEN or not token:
        return ""
    partes = token.split(".")
    if len(partes) != 4 or partes[0] != "p1":
        return ""
    _, ub, exp_txt, firma = partes
    try:
        exp = int(exp_txt)
    except ValueError:
        return ""
    if exp < time.time() or not hmac.compare_digest(firma, _firmar("p1", ub, exp)):
        return ""
    return _de_ub(ub)


def crear_dispositivo(usuario: str) -> str:
    """Token "confío en este dispositivo": lleva la fecha de emisión para poder
    invalidar todos los anteriores con `olvidar_dispositivos`."""
    exp = int(time.time()) + DISPOSITIVO_DIAS * 86400
    emitido = int(time.time())
    ub = _ub(usuario)
    return f"d1.{ub}.{exp}.{emitido}.{_firmar('d1', ub, exp, str(emitido))}"


def dispositivo_valido(token: str | None, usuario: str) -> bool:
    if not config.ADMIN_PANEL_TOKEN or not token:
        return False
    partes = token.split(".")
    if len(partes) != 5 or partes[0] != "d1":
        return False
    _, ub, exp_txt, emitido_txt, firma = partes
    try:
        exp, emitido = int(exp_txt), int(emitido_txt)
    except ValueError:
        return False
    if exp < time.time() or _de_ub(ub) != (usuario or "").strip().lower():
        return False
    if not hmac.compare_digest(firma, _firmar("d1", ub, exp, str(emitido))):
        return False
    epoch = int(stores.config.get(_cfg_key(_CFG_DISP_EPOCH, usuario), "") or 0)
    return emitido >= epoch


def olvidar_dispositivos(usuario: str) -> None:
    stores.config[_cfg_key(_CFG_DISP_EPOCH, usuario)] = str(int(time.time()) + 1)


def usuario_de_sesion(token: str | None) -> str:
    """Correo del operador de una sesión `s1.` vigente; "token" si es el token
    clásico de ADMIN_PANEL_TOKEN; "" si no vale."""
    if not config.ADMIN_PANEL_TOKEN or not token:
        return ""
    if hmac.compare_digest(token, config.ADMIN_PANEL_TOKEN):
        return "token"
    if not _sesion_valida(token):
        return ""
    return _de_ub(token.split(".")[1])


def es_token_clasico(token: str | None) -> bool:
    return bool(config.ADMIN_PANEL_TOKEN and token) and hmac.compare_digest(token, config.ADMIN_PANEL_TOKEN)
