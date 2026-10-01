"""COBRO WEB EN USD / BOB por PASARELA HOSPEDADA (oct-2026, fase 2 parte 1:
"que la web cobre en dólares y bolivianos con los MISMOS módulos que usa el
APK"). Hasta aquí la web solo cobraba en soles con Culqi; las canchas y
billeteras de Ecuador y Bolivia decían "hazlo en la app".

Pasarela por moneda (la misma regla que `PaisConfig.pasarela` del APK):
- USD (Ecuador) → la fachada `pagos.pasarela_ec` (hoy PayPhone; el director
  la cambiará a Nuvei detrás de la misma fachada). Botón de pago por
  redirección: preparar → el cliente paga en la página hospedada → vuelve a
  NUESTRO retorno → CONFIRMAR antes de 5 min (si no, la pasarela lo revierte).
- BOB (Bolivia) → `pagos.libelula`: registrar deuda → página de Libélula
  (QR · tarjeta · Tigo Money) → callback servidor-a-servidor + retorno.
- Sin pasarela configurada: en PRODUCCIÓN nunca se simula (la ficha sigue
  diciendo "reserva desde la app"); en dev/QAS hay una pasarela SIMULADA
  ("Pago de prueba · QAS") para recorrer el flujo completo sin llaves.

ÓRDENES (`stores.pagos_web`, en el snapshot): {id no adivinable, email de la
sesión, pasarela, moneda, monto_centimos (lo decide el SERVIDOR), concepto,
accion: {tipo: reserva | recarga, …}, estado: pendiente → aprobado |
aprobado_sin_reserva | rechazado | cancelado | vencido}. La acción se
ejecuta UNA sola vez (candado + `accion_hecha`) por el primer camino que
pruebe el pago: retorno del navegador, callback de Libélula, sondeo de la
página de espera o el barrido del cron. El dinero se mueve con las MISMAS
funciones que el APK y que `/web/pagar`:

- reserva: `web.router.confirmar_reserva_pagada` (confirma, seña, fidelidad,
  bono, `cobro_web` ligado a la reserva, liquidación al dueño en la moneda de
  la cancha, push, boleador). El apartado del horario NO vence a los 10 min
  mientras la orden está en curso (`medio_pago = 'web_pasarela'`, ver
  `datos._SQL_HOLD_VENCIDO`); al rechazarse/cancelarse/vencer se suelta con
  `web.router.soltar_bloque` (premio, bono y puntos vuelven al jugador).
  Pago que llega TARDE (el horario ya se soltó): se devuelve a su saldo si la
  billetera es de esa moneda o queda `manual` en `stores.cancelaciones_web`
  para que el operador lo devuelva desde la torre.
- recarga: la acredita el propio módulo de la pasarela al confirmar
  (`pagos.router._confirmar_ec_inner` / `_marcar_pagada`, tipo `recarga` →
  saldo + bono de recarga), exactamente como en el APK.

Seguridad: el monto se recalcula en el servidor; el retorno se finaliza aun
sin cookie (la prueba es la confirmación de la pasarela, nunca el GET); la
página de espera y el estado solo los ve el dueño de la orden; un segundo
retorno/callback no vuelve a cobrar ni a acreditar.
"""

from __future__ import annotations

import json
import os
import secrets
import threading
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Body, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

import config
from db.store import stores
from pagos import libelula, pasarela_ec
from web import datos, sesion, ui
from web.ui import e

router = APIRouter()

_LOCK = threading.RLock()

# Vida de una orden pendiente (desde que se crea). PayPhone revierte a los
# 5 min lo que no se confirmó, así que 12 min sobra; un QR de Libélula puede
# tardar más. Todo por debajo del tope del apartado (datos.HOLD_PASARELA_MAX).
TTL = {"libelula": 30 * 60, "sim": 15 * 60}
TTL_EC = 12 * 60
CONSULTA_MIN_SEG = 8          # no consultar a la pasarela más seguido (sondeo de la página)
GUARDAR_DIAS = 45             # órdenes terminadas que se conservan (soporte)
PENDIENTES = ("pendiente",)
FINALES = ("aprobado", "aprobado_sin_reserva", "rechazado", "cancelado", "vencido")
_ENTORNOS_PRUEBA = {"QAS", "DEV", "DESARROLLO", "PRUEBAS", "TEST", "LOCAL"}
SIMBOLO = {"USD": "$", "BOB": "Bs", "PEN": "S/"}


# ── qué pasarela cobra cada moneda ────────────────────────────────────────────

def es_produccion() -> bool:
    return (config.PICHANGOL_ENTORNO or "").upper() in ("PRD", "PROD", "PRODUCCION")


def simulada_permitida() -> bool:
    """Pasarela SIMULADA: solo con un ambiente de PRUEBAS declarado
    (`PICHANGOL_ENTORNO` = QAS/DEV/…; vacío no vale: fail-closed), nunca en
    PRD ni con una llave live de Culqi cargada, y apagable con
    `WEB_PAGO_SIMULADO=0`."""
    ent = (config.PICHANGOL_ENTORNO or "").upper()
    if es_produccion() or ent not in _ENTORNOS_PRUEBA:
        return False
    if (os.getenv("WEB_PAGO_SIMULADO", "1") or "1").strip() == "0":
        return False
    if str(getattr(config, "CULQI_SECRET_KEY", "") or "").startswith("sk_live"):
        return False
    return True


def pasarela_para(iso: str) -> str:
    """Clave de la pasarela que cobra esa moneda en la web ('' = ninguna →
    "hazlo en la app"). PEN no pasa por aquí (Culqi en la misma página)."""
    iso = (iso or "").upper()
    if iso == "USD":
        if pasarela_ec.disponible():
            return pasarela_ec.clave()
    elif iso == "BOB":
        if libelula.disponible():
            return "libelula"
    else:
        return ""
    return "sim" if simulada_permitida() else ""


def es_ec(pasarela: str) -> bool:
    return bool(pasarela) and pasarela not in ("libelula", "sim")


def nombre_pasarela(pasarela: str) -> str:
    if pasarela == "libelula":
        return "Libélula"
    if pasarela == "sim":
        return "la pasarela de prueba (QAS)"
    return pasarela_ec.nombre()


def etiqueta_pasarela(pasarela: str) -> str:
    if pasarela == "libelula":
        return "Libélula · QR o tarjeta"
    if pasarela == "sim":
        return "Pago de prueba · QAS"
    return pasarela_ec.etiqueta()


def selector(pasarela: str) -> str:
    """Selector de medio del checkout para esa pasarela (un solo medio)."""
    return ui.selector_medio_pago(pasarela, nombre=nombre_pasarela(pasarela), etiqueta=etiqueta_pasarela(pasarela))


# ── órdenes ───────────────────────────────────────────────────────────────────

def _ahora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _persistir() -> None:
    from pagos.router import _persistir_ahora
    _persistir_ahora()


def _base(request: Request | None) -> str:
    """Base de las URLs de retorno: `PUBLIC_BASE_URL` del ambiente (es la que
    se registra como dominio autorizado en cada pasarela); sin ella, el host
    de la request."""
    b = (config.PUBLIC_BASE_URL or "").rstrip("/")
    if not b and request is not None:
        b = str(request.base_url).rstrip("/")
    return b


def orden(oid: str) -> dict | None:
    return stores.pagos_web.get(str(oid or ""))


def _ref_pasarela_cobro(o: dict) -> str:
    """Referencia del cobro en el libro (`culqi_charge_id` del `cobro_web`):
    `<pasarela>:<id en la pasarela>` (o `sim:<orden>`). Nunca empieza con
    `chr_`, así ningún camino de Culqi (reembolso, sincerado) la toca."""
    if o["pasarela"] == "sim":
        return f"sim:{o['id']}"
    return f"{o['pasarela']}:{o.get('ref_pasarela') or o['id']}"


def _vivas() -> list[dict]:
    return [o for o in stores.pagos_web.values()
            if o.get("estado") in PENDIENTES or (o.get("pagado") and not o.get("accion_hecha"))]


def orden_de_ids(ids: list[str]) -> dict | None:
    """Orden de reserva EN CURSO que tiene apartados esos turnos."""
    s = {str(i) for i in ids or []}
    for o in _vivas():
        a = o.get("accion") or {}
        if a.get("tipo") == "reserva" and s & {str(i) for i in a.get("ids") or []}:
            return o
    return None


def ref_pendiente(ref: str = "", ids: list[str] | None = None) -> bool:
    """¿Hay un pago hospedado en curso para esa reserva/grupo (o esos ids)?
    Lo consultan la tarjeta de fidelidad y el barrido de bono/puntos para NO
    devolverle al jugador lo apartado mientras paga en la pasarela."""
    if ids and orden_de_ids(ids):
        return True
    if not ref:
        return False
    return any((o.get("accion") or {}).get("ref") == ref for o in _vivas())


def crear_orden(*, email: str, iso: str, monto_centimos: int, concepto: str, accion: dict,
                nombre: str = "", telefono: str = "", request: Request | None = None) -> dict:
    """Crea la orden y la deja lista en la pasarela del país. Devuelve
    {ok, orden, url} (url = a dónde mandar al navegador) o {ok: False, error}."""
    iso = (iso or "").upper()
    pas = pasarela_para(iso)
    if not pas:
        return {"ok": False, "error": "pasarela_no_disponible"}
    monto_centimos = int(monto_centimos or 0)
    if monto_centimos <= 0:
        return {"ok": False, "error": "monto_invalido"}
    base = _base(request)
    if pas != "sim" and not base:
        return {"ok": False, "error": "sin_base_url"}
    oid = "pw_" + secrets.token_urlsafe(18)
    ttl = TTL.get(pas, TTL_EC)
    o = {"id": oid, "email": (email or "").strip().lower(), "nombre": (nombre or "")[:80], "pasarela": pas,
         "moneda": iso, "simbolo": SIMBOLO.get(iso, iso), "monto_centimos": monto_centimos,
         "concepto": (concepto or "Pago Pichangol")[:120], "accion": dict(accion or {}), "estado": "pendiente",
         "creado_en": _ahora_iso(), "vence_ts": time.time() + ttl, "ref_pasarela": "", "url_pasarela": "",
         "url_resultado": "", "pagado": False, "accion_hecha": False, "intentos": 0}
    tipo_mod = "recarga" if o["accion"].get("tipo") == "recarga" else "reserva_web"
    dueno_mod = o["email"] if tipo_mod == "recarga" else ""
    ref_mod = str(o["accion"].get("ref") or oid)
    if pas == "libelula":
        from pagos.router import registrar_deuda_bo
        partes = (nombre or "").split()
        r = registrar_deuda_bo(email=o["email"], monto_bs=monto_centimos / 100.0, concepto=o["concepto"],
                               tipo=tipo_mod, ref=ref_mod, dueno_id=dueno_mod,
                               nombre=(partes[0] if partes else ""), apellido=" ".join(partes[1:]),
                               retorno=f"{base}/web/pago/{oid}/retorno", base=base, orden_web=oid)
        if not r.get("ok"):
            return {"ok": False, "error": str(r.get("error") or "pasarela_error")[:120]}
        o["ref_pasarela"], o["url_pasarela"] = r["identificador"], r.get("url_pasarela") or ""
    elif pas == "sim":
        o["url_pasarela"] = f"/web/pago/{oid}/simulado"
    else:
        from pagos.router import preparar_pago_ec
        # Sin teléfono: la pasarela valida su propio formato internacional y lo
        # pide en su página si lo necesita.
        r = preparar_pago_ec(email=o["email"], monto_usd=monto_centimos / 100.0, concepto=o["concepto"],
                             response_url=f"{base}/web/pago/{oid}/retorno",
                             cancel_url=f"{base}/web/pago/{oid}/cancelado", base=base,
                             tipo=tipo_mod, ref=ref_mod, dueno_id=dueno_mod, orden_web=oid)
        if not r.get("ok"):
            return {"ok": False, "error": str(r.get("error") or "pasarela_error")[:120]}
        # El navegador pasa por la página PUENTE de nuestro dominio (dominio
        # autorizado en la pasarela), igual que el APK.
        o["ref_pasarela"], o["url_pasarela"] = r["identificador"], r.get("url_lanzador") or r.get("url_pasarela") or ""
    with _LOCK:
        stores.pagos_web[oid] = o
    print(f"[pago-web] {oid} creada {pas} {iso} {monto_centimos} {o['accion'].get('tipo')} {o['email']}", flush=True)
    return {"ok": True, "orden": oid, "url": o["url_pasarela"], "pasarela": pas}


def _pagado_en_pasarela(o: dict) -> bool:
    """La pasarela CONFIRMÓ el cobro (única prueba que vale)."""
    if o["pasarela"] == "sim":
        return bool(o.get("sim_aprobado"))
    if o["pasarela"] == "libelula":
        return bool((stores.libelula_deudas.get(o.get("ref_pasarela") or "") or {}).get("pagado"))
    return bool((stores.payphone_pagos.get(o.get("ref_pasarela") or "") or {}).get("pagado"))


def al_pagar(oid: str) -> dict | None:
    """Gancho que llaman los módulos de la pasarela al confirmar el cobro."""
    return finalizar(oid)


def finalizar(oid: str) -> dict | None:
    """Ejecuta la acción de una orden PAGADA (idempotente, una sola vez).
    También sirve para una orden ya vencida/cancelada si el pago llegó tarde:
    entonces se devuelve la plata (la reserva ya no existe)."""
    with _LOCK:
        o = orden(oid)
        if o is None or o.get("accion_hecha"):
            return o
        if not _pagado_en_pasarela(o):
            return o
        o["pagado"] = True
        o.setdefault("pagado_en", _ahora_iso())
        o["intentos"] = int(o.get("intentos") or 0) + 1
        try:
            if (o.get("accion") or {}).get("tipo") == "recarga":
                _ejecutar_recarga(o)
            else:
                _ejecutar_reserva(o)
            o["accion_hecha"] = True
            o["error"] = ""
        except Exception as ex:  # noqa: BLE001 — el barrido reintenta; la plata ya entró
            o["error"] = str(ex)[:200]
            print(f"[pago-web] {oid} pagada pero la acción falló (se reintenta): {ex}", flush=True)
        o["actualizado_en"] = _ahora_iso()
    _persistir()
    return o


def _ejecutar_reserva(o: dict) -> None:
    from web import router as R
    a = o["accion"]
    ids = [str(i) for i in a.get("ids") or []]
    filas = datos.reservas_de(ids)
    if filas and len(filas) == len(ids):
        if all(f.get("estado") == "confirmada" for f in filas):
            o["estado"], o["url_resultado"] = "aprobado", R._url_comprobante(filas)
            return
        c = datos.cancha(str(a.get("cancha_id") or filas[0]["cancha_id"])) or {}
        plan = R.plan_cobro_reserva(filas)
        R.confirmar_reserva_pagada(filas, c, o["email"], plan=plan, charge_id=_ref_pasarela_cobro(o), medio="tarjeta",
                                   monto_cobro=int(o["monto_centimos"]), cargo_centimos=int(a.get("cargo_centimos") or 0),
                                   cargo_desglose=list(a.get("cargo_desglose") or []),
                                   cargo_ajuste=int(a.get("cargo_ajuste") or 0))
        o["estado"], o["url_resultado"] = "aprobado", R._url_comprobante(filas)
        print(f"[pago-web] {o['id']} reserva confirmada {R._ref_de(filas)} {o['pasarela']} {o['moneda']} {o['monto_centimos']}", flush=True)
        return
    _devolver_pago_sin_reserva(o, filas)


def _devolver_pago_sin_reserva(o: dict, filas: list[dict]) -> None:
    """El pago entró pero el horario ya no estaba apartado (llegó tarde, tras
    vencer la orden). No se inventa una reserva: se DEVUELVE. A su saldo
    Pichangol si la billetera es de esa moneda (al instante); si no, queda
    `manual` en Cancelaciones web para que el operador devuelva al medio."""
    from pagos.router import _aviso_push_usuario, moneda_billetera
    a = o["accion"]
    email, iso, monto = o["email"], o["moneda"], int(o["monto_centimos"])
    clave = f"devpw:{o['id']}"
    sim = o.get("simbolo") or SIMBOLO.get(iso, iso)
    a_saldo = moneda_billetera(email) == iso
    if stores.pago_por_charge(clave) is None:
        stores.registrar_pago(tipo="cobro_web", monto_centimos=monto, moneda=iso,
                              estado="devuelto_saldo" if a_saldo else "aprobado",
                              culqi_charge_id=_ref_pasarela_cobro(o), email=email, medio="tarjeta",
                              concepto=f"web:pago_sin_reserva:{o['id']}")
        if a_saldo:
            stores.acreditar(email, monto)
            stores.registrar_pago(tipo="devolucion_saldo", monto_centimos=monto, moneda=iso, estado="aprobado",
                                  dueno_id=email, culqi_charge_id=clave, medio="tarjeta",
                                  concepto=f"Devolución a saldo · pago tardío · {o['concepto']}"[:160])
        else:
            stores.registrar_pago(tipo="devolucion_pendiente", monto_centimos=monto, moneda=iso, estado="pendiente",
                                  dueno_id=email, culqi_charge_id=clave, medio="tarjeta",
                                  concepto=f"Devolución por coordinar · pago tardío · {o['concepto']}"[:160])
            c = datos.cancha(str(a.get("cancha_id") or "")) or {}
            stores.cancelaciones_web.append({
                "id": stores.next_id("cancelacion_web"), "ref": str(a.get("ref") or ""), "ids": list(a.get("ids") or []),
                "usuario": email, "cancha_id": str(a.get("cancha_id") or ""), "cancha": c.get("nombre") or "",
                "club": c.get("club") or "", "fecha": str(a.get("fecha") or ""), "hora_inicio": str(a.get("hora") or ""),
                "hora_fin": "", "turnos": len(a.get("ids") or []), "monto": monto / 100.0, "moneda": sim,
                "moneda_iso": iso, "pagado": True, "horas_antes": 0, "reembolso": "manual", "refund_id": None,
                "detalle": (f"Pago tardío por {nombre_pasarela(o['pasarela'])} ({_ref_pasarela_cobro(o)}): "
                            "el horario ya se había liberado. Devolver al medio de pago."),
                "deuda_dueno_centimos": 0, "dueno": (c.get("dueno") or "").strip().lower(), "creado_en": _ahora_iso(),
                "motivo": "pago_sin_reserva", "medio_devolucion": "original", "monto_devuelto_centimos": monto,
                "cargo_centimos": int(a.get("cargo_centimos") or 0), "incluye_cargo": True, "cancela_anfitrion": False,
                "quien": "sistema", "costo_pasarela_centimos": 0, "bono_horas_devueltas": 0, "puntos_devueltos": 0,
                "pasarela": o["pasarela"], "orden_web": o["id"]})
    o["estado"] = "aprobado_sin_reserva"
    o["devolucion"] = "saldo" if a_saldo else "manual"
    o["url_resultado"] = f"/web/pago/{o['id']}"
    txt = (f"Tu pago de {sim} {monto / 100.0:.2f} llegó cuando el horario ya se había liberado. "
           + ("Te lo devolvimos a tu saldo Pichangol: ya lo puedes usar." if a_saldo
              else "Te devolvemos el 100 % al mismo medio de pago; te escribimos para coordinar."))
    try:
        _aviso_push_usuario(email, "Pago devuelto 💸", txt, tipo="reserva")
    except Exception:  # noqa: BLE001
        pass
    print(f"[pago-web] {o['id']} PAGO SIN RESERVA {o['pasarela']} {iso} {monto} → {o['devolucion']}", flush=True)


def _ejecutar_recarga(o: dict) -> None:
    """La recarga en USD/BOB la acredita el módulo de la pasarela al confirmar
    (como en el APK). La simulada de QAS se acredita aquí con la misma regla
    (saldo + bono de recarga, idempotente por orden)."""
    if o["pasarela"] == "sim":
        from pagos.router import _aplicar_bono_recarga
        clave = f"sim_recarga:{o['id']}"
        if stores.pago_por_charge(clave) is None:
            stores.acreditar(o["email"], int(o["monto_centimos"]))
            stores.registrar_pago(tipo="recarga", monto_centimos=int(o["monto_centimos"]), moneda=o["moneda"],
                                  estado="aprobado", dueno_id=o["email"], email=o["email"], culqi_charge_id=clave,
                                  concepto="Recarga (pago de prueba QAS)")
            _aplicar_bono_recarga(o["email"], int(o["monto_centimos"]) / 100.0, f"sim_{o['id']}")
    o["estado"] = "aprobado"
    o["url_resultado"] = f"/mi-billetera?recarga={o['id']}"
    print(f"[pago-web] {o['id']} recarga acreditada {o['pasarela']} {o['moneda']} {o['monto_centimos']}", flush=True)


def bono_de(o: dict) -> float:
    """Bono de recarga que dio esa orden (para el aviso de la billetera)."""
    pref = {"libelula": "lib_", "sim": "sim_"}.get(o["pasarela"], "pp_")
    ref = o["id"] if o["pasarela"] == "sim" else (o.get("ref_pasarela") or "")
    p = stores.pago_por_charge(f"{pref}{ref}_bono")
    return (p.monto_centimos / 100.0) if p is not None else 0.0


def rechazar(oid: str, estado: str = "rechazado", motivo: str = "") -> dict | None:
    """El pago NO entró (rechazo de la pasarela, el cliente canceló o la orden
    venció): el horario y lo apartado vuelven. Nunca toca una orden pagada."""
    with _LOCK:
        o = orden(oid)
        if o is None or o.get("estado") not in PENDIENTES or o.get("pagado"):
            return o
        o["estado"] = estado if estado in FINALES else "rechazado"
        o["motivo"] = (motivo or "")[:120]
        o["actualizado_en"] = _ahora_iso()
        a = o.get("accion") or {}
        if a.get("tipo") == "reserva" and a.get("ids"):
            try:
                from web import router as R
                R.soltar_bloque([str(i) for i in a["ids"]])
            except Exception as ex:  # noqa: BLE001
                print(f"[pago-web] {oid} no se pudo soltar el apartado: {ex}", flush=True)
        if o["pasarela"] == "libelula":
            d = stores.libelula_deudas.get(o.get("ref_pasarela") or "")
            if d and not d.get("pagado"):
                d["estado_web"] = o["estado"]
        print(f"[pago-web] {oid} {o['estado']} {motivo}", flush=True)
    _persistir()
    return o


def reconciliar(oid: str, *, forzar: bool = False) -> dict | None:
    """Pregunta a la pasarela por una orden viva (sondeo de la página, retorno
    sin datos, barrido): si cobró, finaliza; si la orden ya venció y no cobró,
    la vence y suelta el horario. Limitado a una consulta cada pocos segundos."""
    o = orden(oid)
    if o is None:
        return None
    if o.get("pagado") or _pagado_en_pasarela(o):
        return finalizar(oid) if not o.get("accion_hecha") else o
    if o.get("estado") not in PENDIENTES:
        return o
    ahora = time.time()
    vencida = ahora > float(o.get("vence_ts") or 0)
    if forzar or vencida or ahora - float(o.get("ult_consulta") or 0) >= CONSULTA_MIN_SEG:
        o["ult_consulta"] = ahora
        try:
            if o["pasarela"] == "libelula":
                from pagos.router import _marcar_pagada
                ref = o.get("ref_pasarela") or ""
                est = libelula.consultar_por_identificador(ref)
                if est.get("ok") and est.get("pagado"):
                    _marcar_pagada(ref)  # acredita (recarga) y llama al gancho → finalizar
            elif es_ec(o["pasarela"]):
                from pagos.router import _confirmar_ec
                d = stores.payphone_pagos.get(o.get("ref_pasarela") or "")
                if d and d.get("transaction_id") and not d.get("pagado"):
                    _confirmar_ec(o["ref_pasarela"], "")
                    if _rechazo_definitivo_ec(d):
                        return rechazar(oid, "rechazado", f"{nombre_pasarela(o['pasarela'])}: {d.get('estado')}")
        except Exception as ex:  # noqa: BLE001
            print(f"[pago-web] {oid} reconciliar: {ex}", flush=True)
        o = orden(oid)
        if o.get("pagado") or _pagado_en_pasarela(o):
            return finalizar(oid)
    if vencida and o.get("estado") in PENDIENTES:
        return rechazar(oid, "vencido", "la orden venció sin pago confirmado")
    return o


def _rechazo_definitivo_ec(d: dict) -> bool:
    """La pasarela de Ecuador CONFIRMÓ que no hubo cobro (estado distinto de
    aprobado y que no es un error de red: ese se reintenta)."""
    est = str(d.get("estado") or "").lower()
    return (bool(est) and not d.get("pagado") and est not in ("pendiente", "pending", "desconocido")
            and not est.startswith("error"))


def barrer() -> dict:
    """Cron (cada minuto, junto a los apartados web): reconcilia las órdenes
    vivas, vence las viejas soltando el horario, reintenta acciones pagadas
    que fallaron y poda el historial."""
    n = {"revisadas": 0, "finalizadas": 0, "vencidas": 0}
    for o in list(_vivas()):
        n["revisadas"] += 1
        antes = o.get("estado")
        r = reconciliar(o["id"])
        if r and r.get("accion_hecha") and antes != r.get("estado"):
            n["finalizadas"] += 1
        elif r and r.get("estado") == "vencido" and antes != "vencido":
            n["vencidas"] += 1
    # Libélula: un QR puede pagarse DESPUÉS de vencer la orden y su callback
    # podría no llegar nunca. Durante 24 h se le pregunta cada 10 min, para que
    # ese pago tardío se devuelva (nunca se queda la plata sin dueño). En
    # Ecuador no hace falta: lo que no se confirma en 5 min se revierte solo.
    ahora = time.time()
    for o in list(stores.pagos_web.values()):
        if (o.get("pasarela") == "libelula" and o.get("estado") in ("vencido", "cancelado", "rechazado")
                and not o.get("pagado") and ahora - float(o.get("vence_ts") or 0) < 86400
                and ahora - float(o.get("ult_consulta") or 0) >= 600):
            o["ult_consulta"] = ahora
            try:
                ref = o.get("ref_pasarela") or ""
                est = libelula.consultar_por_identificador(ref)
                if est.get("ok") and est.get("pagado"):
                    from pagos.router import _marcar_pagada
                    _marcar_pagada(ref)  # gancho → finalizar → devolución del pago tardío
                    n["finalizadas"] += 1
            except Exception as ex:  # noqa: BLE001
                print(f"[pago-web] {o['id']} consulta tardía: {ex}", flush=True)
    corte = time.time() - GUARDAR_DIAS * 86400
    with _LOCK:
        for k in [k for k, o in stores.pagos_web.items()
                  if o.get("estado") in FINALES and (o.get("accion_hecha") or not o.get("pagado"))
                  and float(o.get("vence_ts") or 0) < corte]:
            stores.pagos_web.pop(k, None)
    return n


# ── autorización ──────────────────────────────────────────────────────────────

def _es_del_dueno(request: Request, o: dict) -> bool:
    """La página de espera, el estado y la cancelación solo los usa quien
    creó la orden (cookie de Google). Sin login configurado (modo invitado)
    el id no adivinable de la orden hace de llave."""
    if not sesion.activo():
        return True
    ses = sesion.de_request(request)
    return bool(ses) and (ses.get("email") or "").strip().lower() == o.get("email")


# ── crear: reserva ────────────────────────────────────────────────────────────

@router.post("/web/pago/reserva")
def pagar_reserva_hospedada(request: Request, body: dict = Body(...)) -> JSONResponse:
    """El jugador confirmó el "Resumen de tu pago" de una cancha en $ / Bs:
    se recalcula el monto (mismo plan y cargo que `/web/pagar`), se crea la
    orden en la pasarela del país y el apartado pasa a "en pasarela" (no
    vence a los 10 min mientras paga). Responde la URL a la que ir."""
    from web import router as R
    ses = sesion.de_request(request) if sesion.activo() else None
    if sesion.activo() and not ses:
        return JSONResponse({"ok": False, "error": "sesion_requerida", "mensaje": "Inicia sesión con Google para pagar tu reserva."})
    ids = [str(i) for i in (body or {}).get("ids") or []][:R.MAX_SLOTS]
    if not R._firma_ok(ids, str((body or {}).get("firma") or "")):
        return JSONResponse({"ok": False, "error": "firma", "mensaje": "La sesión de pago venció. Vuelve a elegir el horario."})
    filas = datos.reservas_de(ids)
    if not filas or len(filas) != len(ids):
        return JSONResponse({"ok": False, "error": "hold_vencido",
                             "mensaje": "El horario ya no está reservado para ti. Vuelve a elegirlo."})
    if all(f.get("estado") == "confirmada" for f in filas):
        return JSONResponse({"ok": True, "url": R._url_comprobante(filas), "pagada": True})
    email = ((ses or {}).get("email") or filas[0].get("usuario") or "").strip().lower()
    if any((f.get("usuario") or "").strip().lower() != email for f in filas):
        return JSONResponse({"ok": False, "error": "ajena", "mensaje": "Ese horario no está apartado a tu nombre."})
    clave = "|".join(sorted(ids))
    with _LOCK:
        previa = orden_de_ids(ids)
        if previa is not None:
            if previa.get("email") != email:
                return JSONResponse({"ok": False, "error": "ajena", "mensaje": "Ese horario no está apartado a tu nombre."})
            return JSONResponse({"ok": True, "orden": previa["id"], "url": previa.get("url_pasarela") or f"/web/pago/{previa['id']}"})
        if clave in _CREANDO:
            # Doble clic / dos pestañas: una sola orden por bloque.
            return JSONResponse({"ok": False, "error": "en_curso", "mensaje": "Ya estamos abriendo tu pago. Espera unos segundos."})
        _CREANDO.add(clave)
    try:
        return _crear_orden_reserva(request, ses, ids, filas, email)
    finally:
        with _LOCK:
            _CREANDO.discard(clave)


_CREANDO: set[str] = set()


def _crear_orden_reserva(request: Request, ses: dict | None, ids: list[str], filas: list[dict], email: str) -> JSONResponse:
    from web import router as R
    c = datos.cancha(filas[0]["cancha_id"]) or {}
    sim, iso = R._moneda_de(c)
    if iso == "PEN":
        return JSONResponse({"ok": False, "error": "usa_culqi", "mensaje": "Esta reserva se paga con Yape o tarjeta en la misma página."})
    plan = R.plan_cobro_reserva(filas)
    if plan["a_cobrar"] <= 0 or plan["base_cobro"] <= 0:
        return JSONResponse({"ok": False, "error": "sin_pago", "mensaje": "Esta reserva no tiene nada que cobrar."})
    cot = R._cotizacion_reserva(c, plan["base_cobro"], str(filas[0].get("deporte") or ""))
    accion = {"tipo": "reserva", "ids": ids, "ref": plan["ref"], "cancha_id": c.get("id") or filas[0]["cancha_id"],
              "fecha": str(filas[0]["fecha"]), "hora": str(filas[0]["hora_inicio"]),
              "cargo_centimos": int(cot.cargo_centimos), "cargo_desglose": list(cot.desglose or []),
              "cargo_ajuste": int(cot.ajuste_seguridad_centimos), "es_sena": bool(plan["es_sena"])}
    r = crear_orden(email=email, iso=iso, monto_centimos=int(cot.total_centimos),
                    concepto=R.concepto_reserva(c, filas, plan["es_sena"]), accion=accion,
                    nombre=str((ses or {}).get("nombre") or filas[0].get("jugador") or ""),
                    telefono=str(filas[0].get("telefono") or ""), request=request)
    if not r.get("ok"):
        msg = ("El pago en línea para esta moneda no está disponible en la web por ahora. Reserva desde la app."
               if r.get("error") == "pasarela_no_disponible" else
               "No pudimos abrir la pasarela de pago. Inténtalo de nuevo en unos segundos.")
        return JSONResponse({"ok": False, "error": r.get("error"), "mensaje": msg})
    if not datos.marcar_hold_pasarela(ids):
        # El apartado venció justo ahora: la orden queda cancelada y no se cobra.
        rechazar(r["orden"], "cancelado", "el apartado venció antes de ir a pagar")
        return JSONResponse({"ok": False, "error": "hold_vencido", "mensaje": "El horario ya no está reservado para ti. Vuelve a elegirlo."})
    return JSONResponse({"ok": True, "orden": r["orden"], "url": r["url"], "pasarela": r["pasarela"],
                         "total_centimos": int(cot.total_centimos)})


# ── crear: recarga de billetera ───────────────────────────────────────────────

@router.post("/web/billetera/recargar-pasarela")
def recargar_hospedada(request: Request, body: dict = Body(...)) -> JSONResponse:
    """Recarga de una billetera en $ / Bs = `/pagos/ec/pago` | `/pagos/bo/deuda`
    del APK con tipo `recarga`: el módulo acredita saldo + bono al confirmar."""
    from web import jugador_billetera as JB
    ses = sesion.de_request(request)
    if not ses:
        return JSONResponse({"ok": False, "error": "sesion_requerida", "mensaje": "Inicia sesión para recargar."}, status_code=401)
    email = (ses.get("email") or "").strip().lower()
    iso_pais, _ = JB.pais_billetera(email)
    P = JB.PAISES[iso_pais]
    if P["pasarela"] == "culqi":
        return JSONResponse({"ok": False, "error": "usa_culqi", "mensaje": "Tu billetera es en soles: recarga con Yape o tarjeta."}, status_code=409)
    try:
        monto = float((body or {}).get("monto") or 0)
    except (TypeError, ValueError):
        monto = 0
    if monto != int(monto) or not (P["min"] <= monto <= P["max"]):
        return JSONResponse({"ok": False, "error": "monto_invalido",
                             "mensaje": f"El monto va entre {P['moneda']} {P['min']} y {P['moneda']} {P['max']}, sin decimales."}, status_code=400)
    r = crear_orden(email=email, iso=P["iso_mon"], monto_centimos=int(monto) * 100,
                    concepto="Recarga de saldo Pichangol", accion={"tipo": "recarga"},
                    nombre=str(ses.get("nombre") or ""), request=request)
    if not r.get("ok"):
        return JSONResponse({"ok": False, "error": r.get("error"),
                             "mensaje": ("La recarga en línea no está disponible en la web por ahora: hazla desde la app."
                                         if r.get("error") == "pasarela_no_disponible" else
                                         "No pudimos abrir la pasarela de pago. Inténtalo de nuevo en unos segundos.")},
                            status_code=409 if r.get("error") == "pasarela_no_disponible" else 502)
    return JSONResponse({"ok": True, "orden": r["orden"], "url": r["url"], "pasarela": r["pasarela"]})


# ── retorno / cancelación de la pasarela ──────────────────────────────────────

@router.get("/web/pago/{oid}/retorno")
def retorno(oid: str, id: str = "", clientTransactionId: str = "") -> RedirectResponse:
    """La pasarela devuelve aquí al navegador. Se CONFIRMA de inmediato con la
    pasarela (Ecuador: regla de los 5 min; Bolivia: consulta de la deuda) y se
    finaliza la orden aunque no haya cookie: la prueba es la pasarela, no
    este GET. Luego se manda a la página de la orden."""
    o = orden(oid)
    if o is None:
        return RedirectResponse("/web/pago/no-encontrado", status_code=303)
    try:
        if es_ec(o["pasarela"]) and not o.get("pagado"):
            from pagos.router import _confirmar_ec
            ref = o.get("ref_pasarela") or ""
            ctx = (clientTransactionId or "").strip()
            tx = (id or "").strip()
            if tx and (not ctx or ctx == ref):
                d = _confirmar_ec(ref, tx)  # confirma; si aprobó, el gancho finaliza
                if d is not None and _rechazo_definitivo_ec(d):
                    rechazar(oid, "rechazado", f"{nombre_pasarela(o['pasarela'])}: {d.get('estado')}")
        reconciliar(oid, forzar=True)
    except Exception as ex:  # noqa: BLE001
        print(f"[pago-web] {oid} retorno: {ex}", flush=True)
    _persistir()  # llega por GET: el middleware no guarda
    return RedirectResponse(f"/web/pago/{oid}", status_code=303)


@router.get("/web/pago/{oid}/cancelado")
def cancelado(oid: str) -> RedirectResponse:
    """El cliente canceló en la pasarela: no hubo cobro; el horario vuelve."""
    o = orden(oid)
    if o is not None and not o.get("pagado"):
        reconciliar(oid, forzar=True)  # por si pagó y luego tocó "cancelar"
        o = orden(oid)
        if o.get("estado") in PENDIENTES and not o.get("pagado"):
            rechazar(oid, "cancelado", "cancelado en la pasarela")
    return RedirectResponse(f"/web/pago/{oid}", status_code=303)


@router.post("/web/pago/{oid}/cancelar")
def cancelar_orden(oid: str, request: Request) -> JSONResponse:
    """El jugador desiste desde nuestra página de espera."""
    o = orden(oid)
    if o is None or not _es_del_dueno(request, o):
        return JSONResponse({"ok": False, "error": "no_encontrada"}, status_code=404)
    o = reconciliar(oid, forzar=True)
    if o.get("estado") in PENDIENTES and not o.get("pagado"):
        o = rechazar(oid, "cancelado", "el jugador canceló")
    return JSONResponse({"ok": True, "estado": o.get("estado"), "url": _destino(o)})


def _destino(o: dict) -> str:
    if o.get("estado") == "aprobado" and o.get("url_resultado"):
        return o["url_resultado"]
    return f"/web/pago/{o['id']}"


@router.get("/web/pago/{oid}/estado")
def estado_orden(oid: str, request: Request) -> JSONResponse:
    o = orden(oid)
    if o is None or not _es_del_dueno(request, o):
        return JSONResponse({"ok": False, "error": "no_encontrada"}, status_code=404)
    # Sin `_persistir()` aquí: finalizar / rechazar ya guardan lo que cambia
    # (el sondeo de cada pocos segundos no reescribe el snapshot).
    o = reconciliar(oid) or o
    return JSONResponse({"ok": True, "estado": o.get("estado"), "pagado": bool(o.get("pagado")), "url": _destino(o)})


# ── página de la orden (espera / resultado) ───────────────────────────────────

_JS_ESPERA = r"""
(function(){
  var O = window.__orden || {}, n = 0;
  function sondear(){
    n++;
    fetch('/web/pago/' + encodeURIComponent(O.id) + '/estado', {headers: {'X-Fondo': '1'}})
      .then(function(r){ return r.json(); })
      .then(function(j){
        if(!j || !j.ok) return;
        if(j.estado !== 'pendiente' || j.pagado){ pcgCargando(j.estado === 'aprobado' ? 'Pago confirmado. Abriendo tu comprobante…' : 'Un momento…'); location.href = j.url; return; }
        setTimeout(sondear, n < 20 ? 3000 : 6000);
      }).catch(function(){ setTimeout(sondear, 6000); });
  }
  setTimeout(sondear, 1500);
  var b = document.getElementById('btnCancelarOrden');
  if(b) b.addEventListener('click', function(){
    pcgConfirmar({titulo: '¿Cancelar este pago?', mensaje: 'Si todavía no pagaste en ' + O.pasarela + ', el horario queda libre y no se te cobra nada. Si ya pagaste, espera unos segundos a que lo confirmemos.',
                  confirmar: 'Sí, cancelar', cancelar: 'Seguir esperando', destructivo: true})
      .then(function(ok){
        if(!ok) return;
        pcgCargando('Cancelando…');
        fetch('/web/pago/' + encodeURIComponent(O.id) + '/cancelar', {method: 'POST'})
          .then(function(r){ return r.json(); })
          .then(function(j){ location.href = (j && j.url) || location.href; })
          .catch(function(){ pcgCargando(false); pcgToast('Sin conexión. Intenta de nuevo.'); });
      });
  });
})();
"""


def _monto_txt(o: dict) -> str:
    return f"{o.get('simbolo') or o['moneda']} {int(o['monto_centimos']) / 100.0:.2f}"


def _volver_de(o: dict) -> tuple[str, str]:
    a = o.get("accion") or {}
    if a.get("tipo") == "recarga":
        return "/mi-billetera", "Volver a Mi billetera"
    cid = str(a.get("cancha_id") or "")
    return (f"/reservar/{cid}" if cid else "/canchas"), "Volver a la cancha"


@router.get("/web/pago/no-encontrado", response_class=HTMLResponse)
def pagina_no_encontrada(request: Request) -> HTMLResponse:
    ses = sesion.de_request(request)
    cuerpo = ("<div class='panel' style='max-width:560px;margin:40px auto;text-align:center'><h1 style='font-size:24px'>Pago no encontrado</h1>"
              "<p class='sub'>No encontramos ese pago. Si te cobraron, escríbenos con tu correo y lo revisamos.</p>"
              "<div class='acciones' style='justify-content:center'><a class='btn' href='/canchas'>Ver canchas</a></div></div>")
    r = ui.shell("Pago no encontrado", cuerpo, sesion=ses)
    r.status_code = 404
    return r


@router.get("/web/pago/{oid}", response_class=HTMLResponse)
def pagina_orden(oid: str, request: Request):
    o = orden(oid)
    if o is None:
        return pagina_no_encontrada(request)
    ses = sesion.de_request(request)
    if not _es_del_dueno(request, o):
        cuerpo = ("<div class='panel' style='max-width:560px;margin:40px auto;text-align:center'>"
                  "<h1 style='font-size:24px'>Tu pago quedó registrado</h1>"
                  "<p class='sub'>Para ver el detalle y tu comprobante, inicia sesión con la misma cuenta con la que pagaste.</p>"
                  f"<div class='acciones' style='justify-content:center'><a class='btn' href='/entrar?volver=/web/pago/{e(oid)}'>Iniciar sesión</a></div></div>")
        return ui.shell("Tu pago", cuerpo, sesion=ses)
    if o.get("estado") in PENDIENTES:
        o = reconciliar(oid) or o
    if o.get("estado") == "aprobado" and o.get("url_resultado"):
        return RedirectResponse(o["url_resultado"], status_code=303)
    volver, volver_txt = _volver_de(o)
    pas = nombre_pasarela(o["pasarela"])
    cab = (f"<div class='sub' style='margin:2px 0 14px'>{e(o['concepto'])}</div>"
           f"<div class='total' style='display:flex;justify-content:space-between;font-weight:800;font-size:18px'><span>Total</span><span>{e(_monto_txt(o))}</span></div>")
    if o.get("estado") in PENDIENTES:
        ir = (f"<a class='btn' href='{e(o.get('url_pasarela') or '#')}'>Ir a pagar con {e(pas)}</a>" if o.get("url_pasarela") else "")
        cuerpo = ("<div class='panel' style='max-width:560px;margin:32px auto'>"
                  + ("<div class='estado' style='background:#FFF4D6;color:#8A5A00;font-weight:800;margin-bottom:12px'>🧪 PAGO DE PRUEBA · QAS — no se cobra dinero real</div>" if o["pasarela"] == "sim" else "")
                  + "<div style='display:flex;gap:12px;align-items:center'><div class='aro-mini' aria-hidden='true'></div>"
                  f"<h1 style='font-size:22px;margin:0'>Confirmando tu pago…</h1></div>{cab}"
                  f"<p class='sub'>Completa el pago en la página de {e(pas)}. Si ya pagaste, en unos segundos lo confirmamos y te llevamos a tu "
                  + ("comprobante" if (o.get("accion") or {}).get("tipo") != "recarga" else "billetera")
                  + ". Tu horario sigue apartado para ti mientras tanto.</p>"
                  f"<div class='acciones' style='flex-wrap:wrap'>{ir}<button type='button' class='btn sec' id='btnCancelarOrden'>Cancelar este pago</button></div></div>"
                  "<style>.aro-mini{width:26px;height:26px;border-radius:50%;border:3px solid #DDE7E2;border-top-color:var(--verde,#0B8A3E);animation:girar .9s linear infinite;flex:none}"
                  "@keyframes girar{to{transform:rotate(360deg)}}</style>"
                  f"<script>window.__orden={json.dumps({'id': oid, 'pasarela': pas})};</script><script>{_JS_ESPERA}</script>")
        return ui.shell("Confirmando tu pago", cuerpo, sesion=ses, titulo_tab="Confirmando tu pago · Pichangol")
    if o.get("estado") == "aprobado_sin_reserva":
        txt = ("Te lo devolvimos a tu saldo Pichangol: ya lo puedes usar." if o.get("devolucion") == "saldo"
               else "Te devolvemos el 100 % al mismo medio de pago; te escribimos para coordinar.")
        cuerpo = ("<div class='panel' style='max-width:560px;margin:32px auto'><h1 style='font-size:22px'>Recibimos tu pago, pero el horario ya se había liberado</h1>"
                  f"{cab}<p class='sub'>Tu pago llegó cuando el tiempo para pagar ya había terminado y el horario quedó libre. {e(txt)}</p>"
                  f"<div class='acciones'><a class='btn' href='{e(volver)}'>Elegir otro horario</a><a class='btn sec' href='/mi-billetera'>Mi billetera</a></div></div>")
        return ui.shell("Pago devuelto", cuerpo, sesion=ses)
    motivo = {"cancelado": "Cancelaste el pago.", "vencido": "El tiempo para pagar terminó.",
              "rechazado": f"{pas[:1].upper() + pas[1:]} no aprobó el cobro."}.get(o.get("estado"), "El pago no se completó.")
    cuerpo = ("<div class='panel' style='max-width:560px;margin:32px auto'><h1 style='font-size:22px'>No se completó el pago</h1>"
              f"{cab}<p class='sub'>{e(motivo)} No se te cobró nada"
              + (" y el horario quedó libre." if (o.get("accion") or {}).get("tipo") == "reserva" else ".") + "</p>"
              f"<div class='acciones'><a class='btn' href='{e(volver)}'>{e(volver_txt)}</a></div></div>")
    return ui.shell("Pago no completado", cuerpo, sesion=ses)


# ── pasarela SIMULADA (solo dev/QAS) ──────────────────────────────────────────

_JS_SIM = r"""
(function(){
  var O = window.__orden || {};
  function enviar(aprobar){
    pcgCargando(aprobar ? 'Aprobando el pago de prueba…' : 'Rechazando…');
    fetch('/web/pago/' + encodeURIComponent(O.id) + '/simulado', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({aprobar: aprobar})})
      .then(function(r){ return r.json(); })
      .then(function(j){ location.href = (j && j.url) || ('/web/pago/' + O.id); })
      .catch(function(){ pcgCargando(false); pcgToast('Sin conexión. Intenta de nuevo.'); });
  }
  document.getElementById('simOk').addEventListener('click', function(){ enviar(true); });
  document.getElementById('simNo').addEventListener('click', function(){ enviar(false); });
})();
"""


def _sim_ok(request: Request, o: dict | None) -> bool:
    return bool(o) and o.get("pasarela") == "sim" and simulada_permitida() and _es_del_dueno(request, o)


@router.get("/web/pago/{oid}/simulado", response_class=HTMLResponse)
def pagina_simulada(oid: str, request: Request):
    o = orden(oid)
    if not _sim_ok(request, o):
        return pagina_no_encontrada(request)
    if o.get("estado") not in PENDIENTES:
        return RedirectResponse(f"/web/pago/{oid}", status_code=303)
    ses = sesion.de_request(request)
    cuerpo = ("<div class='panel' style='max-width:520px;margin:32px auto'>"
              "<div class='estado' style='background:#FFF4D6;color:#8A5A00;font-weight:800;margin-bottom:14px'>🧪 PAGO DE PRUEBA · QAS<br>"
              "<span style='font-weight:600'>Pasarela simulada para probar el flujo. No se cobra dinero real y no existe en producción.</span></div>"
              f"<h1 style='font-size:22px;margin:0 0 4px'>{e(o['concepto'])}</h1>"
              f"<div class='total' style='display:flex;justify-content:space-between;font-weight:800;font-size:20px;margin:12px 0'><span>Total</span><span>{e(_monto_txt(o))}</span></div>"
              "<div class='acciones' style='flex-direction:column;align-items:stretch;gap:10px'>"
              "<button type='button' class='btn lg' id='simOk'>✅ Aprobar pago de prueba</button>"
              "<button type='button' class='btn sec' id='simNo'>Rechazar (simular tarjeta rechazada)</button></div></div>"
              f"<script>window.__orden={json.dumps({'id': oid})};</script><script>{_JS_SIM}</script>")
    return ui.shell("Pago de prueba · QAS", cuerpo, sesion=ses, titulo_tab="Pago de prueba · QAS")


@router.post("/web/pago/{oid}/simulado")
def simular(oid: str, request: Request, body: dict = Body(...)) -> JSONResponse:
    o = orden(oid)
    if not _sim_ok(request, o):
        return JSONResponse({"ok": False, "error": "no_encontrada"}, status_code=404)
    if bool((body or {}).get("aprobar")):
        with _LOCK:
            if o.get("estado") in PENDIENTES:
                o["sim_aprobado"] = True
        o = finalizar(oid) or o
    else:
        o = rechazar(oid, "rechazado", "rechazo simulado") or o
    return JSONResponse({"ok": True, "estado": o.get("estado"), "url": _destino(o)})

