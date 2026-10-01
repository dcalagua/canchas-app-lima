"""REFERIDOS · "Invita y gana" con el bono en el BACKEND (1-oct-2026).

Antes el bono vivía SOLO en el teléfono: `AppState._acreditarBono` sumaba 10 al
saldo local y `sincronizarSaldo` lo pisaba con el saldo del backend, así que la
plata nunca existía de verdad. Ahora el canje y los dos bonos (invitado y quien
invitó) se acreditan AQUÍ, en la billetera única del correo, como un cupón:
`stores.acreditar` + pago auditable `bono_referido` (sale en Mis pagos / Mi
billetera del app y de la web).

Reglas:
- Código = `AppState.codigoReferido` (`PCG` + 6, hash del correo).
- Un canje por invitado; no el propio código; el código debe ser de una
  cuenta real (registro `stores.referidos_codigos` o perfiles conocidos).
- Bono por MONEDA de la billetera de cada lado (`referido_bono_soles|usd|bob`
  en `stores.config`, 0 = apagado).
- Tope de invitados que le pagan a UN referidor (`referido_tope_referidor`);
  pasado el tope, el invitado igual recibe el suyo.
- Idempotente por invitado (clave de pago `referido_inv:<correo>` /
  `referido_ref:<correo>`), con candado de hilo para canjes simultáneos.
- MIGRACIÓN: las filas de `pichangol_referidos` que dejó el APK viejo (canjes
  cuyo bono nunca llegó al backend) se acreditan una vez al abrir "Invita y
  gana" (app o web) de cualquiera de los dos lados (`sincronizar`).
"""

from __future__ import annotations

import hashlib
import re
import threading
from datetime import datetime, timezone

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

import paises
from db import pg
from db.store import stores

router = APIRouter(prefix="/referidos", tags=["referidos"])

_LOCK = threading.RLock()
_TABLA = "pichangol_referidos"
_RX_CODIGO = re.compile(r"^PCG[0-9A-Z]{6}$")
_CLAVE_BONO = {"PEN": "referido_bono_soles", "USD": "referido_bono_usd",
               "BOB": "referido_bono_bob"}


def _low(email: str) -> str:
    return (email or "").strip().lower()


def codigo_referido(email: str) -> str:
    """`AppState.codigoReferido`: hash de las unidades UTF-16 del correo."""
    em = _low(email)
    if not em:
        return ""
    h = 7
    u = em.encode("utf-16-le")
    for i in range(0, len(u), 2):
        h = (h * 31 + (u[i] | (u[i + 1] << 8))) & 0x7FFFFFFF
    dig = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    s = ""
    n = h
    while True:
        n, r = divmod(n, 36)
        s = dig[r] + s
        if n == 0:
            break
    return "PCG" + s.rjust(6, "0")[-6:]


def normalizar_codigo(codigo: str) -> str:
    return re.sub(r"[^0-9A-Z]", "", (codigo or "").upper())


def bono_centimos(moneda: str) -> int:
    clave = _CLAVE_BONO.get((moneda or "PEN").upper(), "referido_bono_soles")
    try:
        return max(0, int(round(float(stores.cfg(clave) or 0) * 100)))
    except (TypeError, ValueError):
        return 0


def tope_referidor() -> int:
    return max(0, stores.cfg_int("referido_tope_referidor"))


def _moneda_billetera(email: str) -> str:
    from pagos.router import moneda_billetera
    return moneda_billetera(email)


def _simbolo(moneda: str) -> str:
    return paises.simbolo_de_moneda(moneda)


def _fmt(centimos: int, moneda: str) -> str:
    v = centimos / 100.0
    txt = f"{v:.2f}".rstrip("0").rstrip(".") if v != int(v) else str(int(v))
    return f"{_simbolo(moneda)} {txt}"


# ─────────────────────────── código → correo ────────────────────────────────

def registrar_codigo(email: str) -> str:
    """Anota código → correo (lo llama "Invita y gana" al abrirse). Así un
    código compartido siempre se resuelve aunque el referidor nunca haya
    recargado ni tenga perfil."""
    em = _low(email)
    cod = codigo_referido(em)
    if cod and stores.referidos_codigos.get(cod) != em:
        stores.referidos_codigos[cod] = em
    return cod


def _correos_conocidos() -> set[str]:
    out: set[str] = set()
    for k in list(stores.saldos.keys()) + list(stores.clientes_pago.keys()):
        if "@" in str(k):
            out.add(_low(k))
    for p in stores.pagos:
        if "@" in str(p.dueno_id or ""):
            out.add(_low(p.dueno_id))
    if pg.habilitado:
        try:
            with pg.conexion() as conn, conn.cursor() as cur:
                cur.execute("SELECT lower(email) FROM pichangol_perfiles WHERE email IS NOT NULL")
                out.update(str(f[0]) for f in cur.fetchall() if f and f[0])
        except Exception:  # noqa: BLE001
            pass
    return out


def referidor_de(codigo: str) -> str:
    """Correo dueño del código, o '' si no corresponde a ninguna cuenta."""
    cod = normalizar_codigo(codigo)
    if not _RX_CODIGO.match(cod):
        return ""
    em = stores.referidos_codigos.get(cod, "")
    if em:
        return em
    for e in _correos_conocidos():
        if codigo_referido(e) == cod:
            stores.referidos_codigos[cod] = e
            return e
    return ""


# ─────────────────────────── espejo en Supabase ─────────────────────────────

def _id_fila(invitado: str) -> str:
    return "ref_" + hashlib.sha1(_low(invitado).encode()).hexdigest()[:12]


def _filas_pg(*, codigo: str = "", invitado: str = "") -> list[dict]:
    """Filas de `pichangol_referidos` (las que escribió el APK viejo y las
    nuevas). Fail-safe: sin base, lista vacía."""
    if not pg.habilitado or not (codigo or invitado):
        return []
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            if codigo:
                cur.execute(f"SELECT invitado_email, referido_codigo FROM {_TABLA} "
                            "WHERE upper(referido_codigo) = %s", (codigo.upper(),))
            else:
                cur.execute(f"SELECT invitado_email, referido_codigo FROM {_TABLA} "
                            "WHERE lower(invitado_email) = %s", (_low(invitado),))
            return [{"invitado": _low(f[0]), "codigo": normalizar_codigo(f[1])}
                    for f in cur.fetchall() if f and f[0]]
    except Exception:  # noqa: BLE001
        return []


def _guardar_pg(invitado: str, codigo: str) -> None:
    """Deja la fila (para el conteo del APK viejo y la web) ya marcada como
    pagada al referidor: el bono lo paga el backend, no el teléfono."""
    if not pg.habilitado:
        return
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute(
                f"INSERT INTO {_TABLA} (id, invitado_email, referido_codigo, referidor_dado) "
                "VALUES (%s, %s, %s, true) ON CONFLICT DO NOTHING",
                (_id_fila(invitado), _low(invitado), codigo.upper()))
            cur.execute(f"UPDATE {_TABLA} SET referidor_dado = true "
                        "WHERE lower(invitado_email) = %s", (_low(invitado),))
    except Exception as ex:  # noqa: BLE001
        print(f"[referidos] no se pudo espejar en Supabase: {ex}", flush=True)


# ─────────────────────────────── acreditar ──────────────────────────────────

def _ya_pagado(clave: str) -> bool:
    return any(p.culqi_charge_id == clave and p.tipo == "bono_referido" for p in stores.pagos)


def _pagar(email: str, clave: str, concepto: str) -> tuple[int, str]:
    """Acredita el bono a [email] en la moneda de SU billetera. Idempotente
    por [clave]. Devuelve (céntimos, moneda); (0, moneda) si no corresponde."""
    moneda = _moneda_billetera(email)
    cent = bono_centimos(moneda)
    if cent <= 0 or _ya_pagado(clave):
        return 0, moneda
    stores.acreditar(email, cent)
    stores.registrar_pago(
        tipo="bono_referido", monto_centimos=cent, moneda=moneda, estado="aprobado",
        dueno_id=email, culqi_charge_id=clave, concepto=concepto)
    return cent, moneda


def _pagados_a_referidor(referidor: str) -> int:
    return sum(1 for r in stores.referidos.values()
               if r.get("referidor") == referidor and int(r.get("ref_centimos") or 0) > 0)


def _registrar_canje(invitado: str, codigo: str, referidor: str, origen: str) -> dict:
    """Acredita a ambos lados y guarda el canje. El llamador tiene `_LOCK`."""
    inv_cent, inv_mon = _pagar(invitado, f"referido_inv:{invitado}",
                               f"Bono de bienvenida · código {codigo}")
    ref_cent, ref_mon = 0, _moneda_billetera(referidor)
    tope = tope_referidor()
    if referidor and (tope == 0 or _pagados_a_referidor(referidor) < tope):
        ref_cent, ref_mon = _pagar(referidor, f"referido_ref:{invitado}",
                                   "Bono por invitar a un amigo")
    reg = {"codigo": codigo, "referidor": referidor, "origen": origen,
           "creado_en": datetime.now(timezone.utc).isoformat(),
           "inv_centimos": inv_cent, "inv_moneda": inv_mon,
           "ref_centimos": ref_cent, "ref_moneda": ref_mon}
    stores.referidos[invitado] = reg
    print(f"[referidos] {invitado} canjeó {codigo} de {referidor or '?'} ({origen}): "
          f"invitado {inv_cent} {inv_mon}, referidor {ref_cent} {ref_mon}", flush=True)
    return reg


def _avisar(reg: dict, invitado: str) -> None:
    try:
        from pagos.router import _aviso_push_usuario
        if reg.get("ref_centimos") and reg.get("referidor"):
            _aviso_push_usuario(
                reg["referidor"], "¡Un amigo usó tu código! 🎁",
                f"Te sumamos {_fmt(reg['ref_centimos'], reg['ref_moneda'])} a tu saldo Pichangol.",
                tipo="saldo")
        if reg.get("inv_centimos"):
            _aviso_push_usuario(
                invitado, "Bono de bienvenida 🎁",
                f"Te sumamos {_fmt(reg['inv_centimos'], reg['inv_moneda'])} a tu saldo Pichangol.",
                tipo="saldo")
    except Exception:  # noqa: BLE001
        pass


def sincronizar(email: str) -> int:
    """MIGRACIÓN de los canjes que el APK viejo dejó en `pichangol_referidos`
    sin bono real: los acredita una vez (lado invitado y lado referidor).
    Devuelve cuántos canjes importó."""
    em = _low(email)
    if not em:
        return 0
    cod = registrar_codigo(em)
    filas = _filas_pg(codigo=cod) + _filas_pg(invitado=em)
    nuevos = 0
    with _LOCK:
        for f in filas:
            inv = f["invitado"]
            if not inv or inv in stores.referidos:
                continue
            c = f["codigo"]
            ref = em if c == cod else referidor_de(c)
            if not ref or ref == inv:
                continue
            reg = _registrar_canje(inv, c, ref, "app_anterior")
            _guardar_pg(inv, c)
            _avisar(reg, inv)
            nuevos += 1
    return nuevos


def canjear(invitado: str, codigo: str, origen: str = "app") -> dict:
    """El invitado canjea el código de un amigo. Núcleo único (APK y web);
    el llamador ya comprobó que [invitado] es el usuario autenticado."""
    inv = _low(invitado)
    cod = normalizar_codigo(codigo)
    if not inv or "@" not in inv:
        return {"ok": False, "error": "email_invalido", "mensaje": "Inicia sesión para canjear."}
    if not _RX_CODIGO.match(cod):
        return {"ok": False, "error": "codigo_invalido",
                "mensaje": "Ese código no existe. Revisa que empiece con PCG y tenga 9 caracteres."}
    if cod == codigo_referido(inv):
        return {"ok": False, "error": "codigo_propio", "mensaje": "Ese es tu propio código: compártelo con tus amigos."}
    sincronizar(inv)  # un canje del APK viejo cuenta como "ya canjeaste"
    with _LOCK:
        if inv in stores.referidos:
            return {"ok": False, "error": "ya_canjeaste",
                    "mensaje": f"Ya canjeaste el código {stores.referidos[inv].get('codigo', '')}. Solo se puede uno por cuenta."}
        ref = referidor_de(cod)
        if not ref:
            return {"ok": False, "error": "codigo_invalido",
                    "mensaje": "Ese código no corresponde a ninguna cuenta de Pichangol."}
        if ref == inv:
            return {"ok": False, "error": "codigo_propio", "mensaje": "Ese es tu propio código."}
        reg = _registrar_canje(inv, cod, ref, origen)
    _guardar_pg(inv, cod)
    _avisar(reg, inv)
    return {"ok": True, "codigo": cod, "bono_centimos": reg["inv_centimos"],
            "moneda": reg["inv_moneda"], "simbolo": _simbolo(reg["inv_moneda"]),
            "saldo_centimos": stores.saldos.get(inv, 0)}


def estado(email: str) -> dict:
    """Lo que muestra "Invita y gana" (APK y web). Registra el código, importa
    canjes viejos y devuelve conteos y lo ganado."""
    em = _low(email)
    if not em:
        return {"ok": False, "error": "email_invalido"}
    importados = sincronizar(em)
    cod = codigo_referido(em)
    mios = [r for r in stores.referidos.values() if r.get("referidor") == em]
    ganado = sum(int(r.get("ref_centimos") or 0) for r in mios)
    propio = stores.referidos.get(em)
    if propio:
        ganado += int(propio.get("inv_centimos") or 0)
    moneda = _moneda_billetera(em)
    tope = tope_referidor()
    return {"ok": True, "codigo": cod, "invitados": len(mios),
            "ganado_centimos": ganado, "moneda": moneda, "simbolo": _simbolo(moneda),
            "bono_centimos": bono_centimos(moneda),
            "canjeado": (propio or {}).get("codigo", ""),
            "tope": tope, "tope_alcanzado": bool(tope) and _pagados_a_referidor(em) >= tope,
            "importados": importados}


# ─────────────────────────────── endpoints ──────────────────────────────────

class CanjeReq(BaseModel):
    email: str
    codigo: str


def _deps():
    from pagos.router import _APP
    return _APP


@router.get("/estado", dependencies=_deps())
def get_estado(email: str, x_user_token: str | None = Header(default=None)) -> dict:
    from pagos.router import _require_usuario
    em = _low(email)
    if not em:
        raise HTTPException(status_code=400, detail="email_invalido")
    _require_usuario(em, x_user_token)
    return estado(em)


@router.post("/canjear", dependencies=_deps())
def post_canjear(req: CanjeReq, x_user_token: str | None = Header(default=None)) -> dict:
    from pagos.router import _require_usuario
    em = _low(req.email)
    if not em:
        raise HTTPException(status_code=400, detail="email_invalido")
    _require_usuario(em, x_user_token)
    return canjear(em, req.codigo, origen="app")
