"""FACHADA de la pasarela de ECUADOR (USD).

Ecuador cobra con PayPhone (`pagos/payphone.py`). Para que cambiar de
pasarela algún día sea enchufar un módulo y no tocar los flujos, TODO el código que cobra en dólares —los
endpoints `/pagos/ec/*` del APK y el cobro web hospedado
(`web/pago_hospedado.py`)— habla con ESTA fachada y nunca con el módulo de la
pasarela directamente.

Cuál se usa lo decide la env `PASARELA_EC` (default `payphone`). Contrato que
debe cumplir cada módulo enchufado (el de PayPhone ya lo cumple):

- `disponible() -> bool`: credenciales cargadas.
- `preparar(*, client_tx_id, monto_usd, concepto, response_url, cancel_url,
  email="", telefono="", documento="") -> {ok, payment_id, url_tarjeta,
  url_payphone}` (las URLs hospedadas a las que se manda al cliente) o
  `{ok: False, error}`. Nunca lanza.
- `confirmar(*, transaction_id, client_tx_id) -> {ok, aprobado, estado,
  transaction_id, autorizacion, monto_centavos, …}` o `{ok: False, error}`:
  la ÚNICA fuente de verdad del cobro (un GET al retorno no prueba nada).
- `centavos(monto_usd) -> int`.
- Opcional `reembolsar(*, transaction_id, client_tx_id, monto_centavos)`:
  PayPhone no expone reembolso por API en este módulo, así que hoy
  `soporta_reembolso()` es False y las devoluciones al medio original quedan
  `manual` (las atiende el operador en la torre).

Los textos que ve el usuario usan `nombre()` / `etiqueta()`, nunca
"PayPhone" fijo.
"""

from __future__ import annotations

import os

from . import payphone

# Clave → (nombre visible, etiqueta del medio). Otra pasarela se agrega aquí
# con su módulo y el mismo contrato.
_NOMBRES = {"payphone": ("PayPhone", "PayPhone · tarjeta")}


def clave() -> str:
    """Pasarela vigente de Ecuador (`PASARELA_EC`, default payphone). Una
    clave desconocida cae a PayPhone (fail-safe: nunca queda sin módulo)."""
    k = (os.getenv("PASARELA_EC", "") or "payphone").strip().lower()
    return k if k in _NOMBRES else "payphone"


def _mod():
    # Hoy hay un solo módulo; la búsqueda es dinámica (los tests parchean
    # `payphone.preparar` / `payphone.confirmar`).
    return payphone


def nombre() -> str:
    return _NOMBRES[clave()][0]


def etiqueta() -> str:
    """Texto del medio en el checkout web ("PayPhone · tarjeta")."""
    return _NOMBRES[clave()][1]


def disponible() -> bool:
    return bool(_mod().disponible())


def centavos(monto_usd: float) -> int:
    return _mod().centavos(monto_usd)


def preparar(**kw) -> dict:
    return _mod().preparar(**kw)


def confirmar(**kw) -> dict:
    return _mod().confirmar(**kw)


def soporta_reembolso() -> bool:
    return callable(getattr(_mod(), "reembolsar", None))


def reembolsar(**kw) -> dict:
    """Devolución al medio original, si el módulo la soporta. Si no, responde
    `no_soportado` y el llamador deja la devolución como `manual`."""
    f = getattr(_mod(), "reembolsar", None)
    if not callable(f):
        return {"ok": False, "error": "no_soportado"}
    return f(**kw)
