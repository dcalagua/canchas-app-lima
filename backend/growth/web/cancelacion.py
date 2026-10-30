"""CANCELACIÓN de una reserva web con la política de devoluciones:
`estado_cancelacion`, `_cancelar_reserva` (el único que mueve plata),
`POST /web/cancelar`, el modal y el JS de cancelar y los ayudantes del bloque
(`_total_de`, `_ref_de`, `_cobro_web`, `_url_comprobante`…).

Movido tal cual desde `web/router.py`, que lo re-exporta (`pagos/router.py`,
`pagos/division.py` y la torre lo llaman como `wr.<función>`).
"""

from __future__ import annotations

import json
from datetime import date, datetime

from fastapi import APIRouter, Request
from pydantic import BaseModel

from pagos import culqi
from pagos import devoluciones as _dev
from web import beneficios, datos, horarios, sesion, ui
from pagos import cobro_directo as _cd
from web.ui import e
from config import MARCA  # noqa: E402 — nombre y dominio de marca (un solo lugar)
from web.comun import _moneda_de, _pais_de

router = APIRouter()


def _total_de(filas: list[dict]) -> int:
    total = sum(int(f["precio"]) for f in filas)
    total += int(round(sum(float(x.get("precio") or 0) for f in filas for x in (f.get("extras") or []))))
    return total


def _ref_de(filas: list[dict]) -> str:
    g = (filas[0].get("grupo_reserva_id") or "").strip()
    return g if g else str(filas[0]["id"])


def _inicio_reserva(filas: list[dict], pais: str) -> datetime | None:
    """Fecha-hora LOCAL (zona del país de la cancha) del primer turno."""
    try:
        f = min(filas, key=lambda x: (str(x.get("fecha")), str(x.get("hora_inicio"))))
        d = date.fromisoformat(str(f["fecha"]))
        m = horarios.hora_en_minutos(str(f["hora_inicio"])) or 0
        return datetime(d.year, d.month, d.day, m // 60, m % 60, tzinfo=horarios.ahora_local(pais).tzinfo)
    except (ValueError, TypeError, KeyError):
        return None


def _cobro_web(ref: str):
    """Cobro de la reserva en el libro: `cobro_web` (cuenta de la plataforma)
    o `cobro_directo` (cuenta Culqi / voucher del CLUB, plan A4-A5)."""
    from db.store import stores as _st
    for p in reversed(_st.pagos):
        if p.tipo in ("cobro_web", "cobro_directo") and p.concepto == f"web:{ref}":
            return p
    return None


def _es_directo(cobro) -> bool:
    return cobro is not None and getattr(cobro, "tipo", "") == "cobro_directo"


def _cargo_pagado(filas: list[dict], cobro) -> tuple[int, list]:
    """Cargo por servicio que pagó el jugador (céntimos) y su desglose: del
    `cobro_web` si la reserva se pagó en la web; de la fila (`cargo_servicio`,
    SQL supabase_reservas_cargo.sql) si se pagó en el app."""
    if cobro is not None and int(getattr(cobro, "cargo_servicio_centimos", 0) or 0) > 0:
        return int(cobro.cargo_servicio_centimos), list(getattr(cobro, "cargo_desglose", None) or [])
    try:
        c = int(round(float(filas[0].get("cargo_servicio") or 0) * 100))
    except (TypeError, ValueError):
        c = 0
    raw = filas[0].get("cargo_desglose")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            raw = []
    return max(c, 0), (list(raw) if isinstance(raw, list) else [])


def _horas_desde_pago(cobro) -> float | None:
    """Horas desde el pago: del `cobro_web` (web) o de la liquidación / el cargo
    de Culqi (app), lo que haya."""
    if cobro is None or not getattr(cobro, "creado_en", None):
        return None
    from db.store import ahora as _ahora
    try:
        return max((_ahora() - cobro.creado_en).total_seconds() / 3600.0, 0.0)
    except TypeError:
        return None


def _cargo_app(ids: list[str]):
    """Reserva pagada EN EL APP: la liquidación del dueño (`culqi_charge_id` =
    id de la reserva) y la fila del CARGO de Culqi (`chr_…`) con el que pagó el
    jugador, ligada por `PagoRegistro.cargo_id` (APK desde sep-2026) o
    inferida por `tarifas_pasarela.cargo_de` (APKs viejos: mismo monto y
    moneda a ±20 min). Con el cargo a la mano la devolución al medio original
    va DIRECTO a Culqi, igual que una reserva web; sin él queda `manual`.
    Devuelve (liquidación, cargo) — cualquiera puede ser None."""
    from db.store import stores as _st
    from pagos import tarifas_pasarela as _tp
    liq = _st.pago_por_charge(ids[0]) if ids else None
    if liq is None or liq.tipo not in ("liquidacion_online", "liquidacion_full"):
        return None, None
    try:
        cargo = _tp.cargo_de(liq)
    except Exception:  # noqa: BLE001 — la inferencia nunca rompe una cancelación
        cargo = None
    if cargo is not None and not str(cargo.culqi_charge_id or "").startswith("chr_"):
        cargo = None
    return liq, cargo


def _es_cargo_culqi(p) -> bool:
    """¿Esa fila es un cargo de Culqi (`chr_…`, reembolsable por su API)? Los
    cobros por pasarela hospedada (`<pasarela>:…`, `sim:…`) no lo son: su
    devolución al medio original queda `manual` (la atiende el operador)."""
    return str(getattr(p, "culqi_charge_id", "") or "").startswith("chr_")


def _reembolso_ec_posible(p) -> bool:
    """Cobro web por la pasarela de Ecuador cuyo módulo SÍ reembolsa por API
    (hoy PayPhone no: queda `manual`)."""
    from pagos import pasarela_ec
    return (str(getattr(p, "culqi_charge_id", "") or "").startswith(pasarela_ec.clave() + ":")
            and pasarela_ec.soporta_reembolso())


def _reembolsar_ec(p, monto_centimos: int) -> dict:
    from db.store import stores as _st
    from pagos import pasarela_ec
    ident = str(p.culqi_charge_id).split(":", 1)[1]
    d = _st.payphone_pagos.get(ident) or {}
    return pasarela_ec.reembolsar(transaction_id=str(d.get("transaction_id") or ""), client_tx_id=ident,
                                  monto_centavos=min(int(monto_centimos), int(p.monto_centimos)))


def _saldo_en_moneda(email: str, iso: str) -> bool:
    try:
        from pagos.router import moneda_billetera
        return moneda_billetera(email) == (iso or "PEN")
    except Exception:  # noqa: BLE001
        return iso == "PEN"


def _filas_de_ref(ref: str) -> list[dict]:
    """Turnos de una referencia (grupo `grp_…` o id de un turno suelto),
    ordenados y sin retenciones web sin pagar."""
    ref = (ref or "").strip()
    if not ref:
        return []
    filas = datos.reservas_por_grupo(ref) if ref.startswith("grp_") else datos.reservas_de([ref])
    return sorted([f for f in filas if f.get("estado") != "nueva" or f.get("pagado")],
                  key=lambda x: (str(x.get("fecha")), str(x.get("hora_inicio"))))


def estado_cancelacion(filas: list[dict], c: dict | None, email: str, cancela_anfitrion: bool = False) -> dict:
    """Qué pasa si se cancela AHORA: si se puede, cuántas horas faltan y qué
    devolución corresponde según la POLÍTICA (`pagos/devoluciones.py`): a
    saldo 100 % con cargo; al medio original el precio sin el cargo;
    arrepentimiento (1 h del pago y > 24 h para el turno) y cancelación del
    anfitrión = 100 % con cargo; tarde = sin devolución. [email] = el jugador;
    con [cancela_anfitrion] no se exige que sea quien cancela."""
    if not filas or not email:
        return {"puede": False, "motivo": "sin_reserva"}
    if not cancela_anfitrion and any((f.get("usuario") or "").strip().lower() != email for f in filas):
        return {"puede": False, "motivo": "ajena"}
    if any(str(f.get("estado") or "") in ("cancelada", "noShow") for f in filas):
        return {"puede": False, "motivo": "ya_cancelada"}
    pais = _pais_de(c) if c else "PE"
    inicio = _inicio_reserva(filas, pais)
    if inicio is None:
        return {"puede": False, "motivo": "sin_fecha"}
    horas = (inicio - horarios.ahora_local(pais)).total_seconds() / 3600.0
    if horas <= 0:
        return {"puede": False, "motivo": "ya_empezo", "horas": horas}
    pagado_online = all(f.get("pagado") for f in filas) and str(filas[0].get("medio_pago") or "") in ("yape", "tarjeta")
    pagado = all(f.get("pagado") for f in filas)
    sim = filas[0].get("moneda") or "S/"
    # Lo que el jugador PAGÓ en plata: sin los turnos que cubrió su bono ni
    # los S/ 3 de puntos (esos vuelven como horas / puntos, no como dinero).
    aj = beneficios.ajustes(filas, c)
    precio_c = max(0, _total_de(filas) - aj["bono_cubre"] - aj["puntos_desc"]) * 100
    cobro = _cobro_web(_ref_de(filas))
    liq, cargo_app = (None, None) if cobro is not None else _cargo_app([str(f["id"]) for f in filas])
    cargo_c, _desg = _cargo_pagado(filas, cobro)
    if cargo_c <= 0 and liq is not None:
        cargo_c = max(int(getattr(liq, "cargo_servicio_centimos", 0) or 0), 0)
    # NUNCA se devuelve más plata de la que entró: (1) con bono, si no hay
    # ningún cobro registrado (APKs anteriores dejaban los servicios extra en
    # la fila SIN cobrarlos) no hay plata pagada; (2) con el cargo de la
    # pasarela a la mano, lo pagado tope = ese cargo (precio + cargo).
    fila_pago = cobro if cobro is not None else cargo_app
    if aj["bono_horas"] and fila_pago is None and liq is None:
        precio_c, cargo_c = 0, 0
    if fila_pago is not None and int(getattr(fila_pago, "monto_centimos", 0) or 0) > 0:
        tope = int(fila_pago.monto_centimos)
        cargo_c = min(cargo_c, tope)
        precio_c = min(precio_c, max(0, tope - cargo_c))
    precio = precio_c // 100 if precio_c % 100 == 0 else precio_c / 100.0
    pol = _dev.resumen(pagado=pagado, horas_para_inicio=horas,
                       horas_desde_pago=_horas_desde_pago(cobro if cobro is not None else (cargo_app or liq)),
                       precio_centimos=precio_c, cargo_centimos=cargo_c, simbolo=sim, cancela_anfitrion=cancela_anfitrion,
                       cancha=c)
    # ¿La devolución al medio original sale sola por Culqi (tenemos el cargo)
    # o la coordina el operador (pago viejo del app sin cargo ligado, o pago
    # por una pasarela hospedada —Ecuador / Bolivia— sin reembolso por API)?
    directo = (cobro is not None and _es_cargo_culqi(cobro)) or cargo_app is not None
    iso_c = _moneda_de(c)[1] if c else "PEN"
    if pagado and (not _saldo_en_moneda(email, iso_c) or _es_directo(cobro)):
        # Devolver a SALDO solo si la billetera es de la moneda de la reserva
        # (nunca se mezclan $ o Bs en un saldo en soles, ni al revés). Un
        # COBRO DIRECTO al club nunca va a saldo: la plata está en la cuenta
        # del club, no en la plataforma.
        pol["opciones"] = [o for o in pol.get("opciones") or [] if o.get("medio") != "saldo"]
    if pagado and _es_directo(cobro) and not str(cobro.culqi_charge_id or "").startswith("chr_"):
        directo = False  # voucher: lo devuelve el club (se le avisa)
    if iso_c != "PEN":
        for o in pol.get("opciones") or []:
            if o.get("medio") == "original":
                o["etiqueta"] = "Al mismo medio de pago (tarjeta / QR)"
    if pagado and not directo:
        es_div = _es_directo(cobro) and str(cobro.culqi_charge_id or "").startswith("div:")
        for o in pol.get("opciones") or []:
            if o.get("medio") == "original":
                o["nota"] = (("100 %, incluido el cargo por servicio. " if o.get("incluye_cargo") else
                              "Se devuelve el precio de la reserva; el cargo por servicio no se devuelve. ")
                             + ("Pago dividido: cada uno recibe su parte por el medio con el que pagó." if es_div
                                else "Te escribimos para coordinar la devolución."))
    reembolsable = pol["motivo"] in ("plazo", "arrepentimiento", "anfitrion")
    if precio_c <= 0 and cargo_c <= 0:
        pol["opciones"] = []  # todo con bono: no hay plata que devolver, solo horas
    return {"puede": True, "horas": round(horas, 1), "pagado": pagado, "pagado_online": pagado_online,
            "bono_horas": aj["bono_horas"], "puntos": aj["puntos"],
            "reembolsable": reembolsable, "minimo_horas": _dev.horas_minimas(c),
            "monto": precio, "monto_centimos": precio_c, "moneda": sim, "cargo_centimos": cargo_c,
            "total_pagado": (precio_c + cargo_c) / 100.0,
            "reembolso_directo": directo, "politica": pol}


class CancelarReq(BaseModel):
    ref: str
    # A dónde va la devolución (política fase 4): 'saldo' (100 % con cargo,
    # al instante) u 'original' (tarjeta/Yape vía Culqi: el precio, sin el
    # cargo salvo arrepentimiento o cancelación del anfitrión). Los clientes
    # viejos no lo mandan → original.
    medio: str = "original"


def _cancelar_reserva(filas: list[dict], c: dict | None, email: str, *, medio: str = "original",
                      cancela_anfitrion: bool = False, quien: str = "") -> dict:
    """Cancela un bloque (del jugador o del anfitrión), libera el horario y
    DEVUELVE según la política: a SALDO acredita al instante en la billetera
    del jugador (registro `devolucion_saldo`); al medio ORIGINAL reembolsa en
    Culqi el monto que corresponda (cargo web) o queda `manual` (pagó en el
    app). Revierte la liquidación del dueño si el jugador recupera su plata;
    si el dueño ya cobró, deja la deuda anotada; si cancela el anfitrión, el
    costo de pasarela de la devolución también es deuda suya."""
    from db.store import stores as _st, ahora as _ahora
    from pagos import tarifas_pasarela as _tp
    medio = _dev.medio_valido(medio)
    est = estado_cancelacion(filas, c, email, cancela_anfitrion=cancela_anfitrion)
    if medio == "saldo" and est.get("puede") and not any(o.get("medio") == "saldo" for o in (est.get("politica") or {}).get("opciones") or []):
        medio = "original"  # su billetera es de otra moneda: va al medio de pago
    if not est.get("puede"):
        msgs = {"sin_reserva": "No encontramos esa reserva.", "ajena": "Esa reserva no es de tu cuenta.",
                "ya_cancelada": "Esa reserva ya estaba cancelada.", "ya_empezo": "El turno ya empezó o ya pasó: no se puede cancelar.",
                "sin_fecha": "No pudimos leer la fecha de la reserva."}
        return {"ok": False, "error": est.get("motivo"), "mensaje": msgs.get(est.get("motivo"), "No se pudo cancelar.")}
    ref = _ref_de(filas)
    ids = [str(f["id"]) for f in filas]
    monto = est["monto"]; monto_c = int(est["monto_centimos"]); sim = est["moneda"]; iso = _moneda_de(c)[1] if c else "PEN"
    pol = est["politica"]; mot = pol["motivo"]
    cargo_c = int(est["cargo_centimos"])
    monto_dev, incluye_cargo = _dev.monto_devolucion(mot, medio, monto_c, cargo_c)
    cobro = _cobro_web(ref)
    _liq, cargo_app = (None, None) if cobro is not None else _cargo_app(ids)
    # Fila del cargo de Culqi que se reembolsa: el `cobro_web` (web) o el cargo
    # del app ligado a la liquidación (`chr_…`). Sin ninguno → manual.
    fila_cargo = cobro if cobro is not None else cargo_app
    if fila_cargo is not None and int(fila_cargo.monto_centimos or 0) > 0:
        # Ni a saldo ni al medio original se devuelve más de lo cobrado.
        monto_dev = min(monto_dev, int(fila_cargo.monto_centimos))
    reembolso, refund_id, detalle = "no_aplica", None, ""
    medio_pago = str(filas[0].get("medio_pago") or "")
    if est["pagado"] and monto_dev > 0 and _es_directo(fila_cargo) and medio == "saldo":
        medio = "original"  # la plata está en la cuenta del club: nunca a saldo
    if est["pagado"] and monto_dev > 0:
        if medio == "saldo":
            # A la billetera del JUGADOR, al instante y sin pasar por Culqi.
            if _st.pago_por_charge(f"dev:{ref}") is None:
                _st.acreditar(email, monto_dev)
                _st.registrar_pago(tipo="devolucion_saldo", monto_centimos=monto_dev, moneda=iso, estado="aprobado",
                                   dueno_id=email, culqi_charge_id=f"dev:{ref}", medio=medio_pago,
                                   concepto=f"Devolución a saldo · {(c or {}).get('nombre', 'reserva')} · {filas[0]['fecha']} {filas[0]['hora_inicio']}")
            if fila_cargo is not None and fila_cargo.estado == "aprobado":
                fila_cargo.estado = "devuelto_saldo"
            reembolso = "saldo"
        elif (_es_directo(fila_cargo) and fila_cargo.estado == "aprobado"
              and str(fila_cargo.culqi_charge_id or "").startswith("div:")):
            # PAGO DIVIDIDO: cada parte vuelve a quien la pagó (Culqi del club o el club a mano).
            from pagos import division as _division
            reembolso, detalle = _division.devolver_por_cancelacion(_division.id_de_cobro(fila_cargo.culqi_charge_id), monto_dev)
            if reembolso == "reembolsado":
                fila_cargo.estado = "reembolsado"
        elif fila_cargo is not None and _es_cargo_culqi(fila_cargo) and fila_cargo.estado == "aprobado" and (
                not _es_directo(fila_cargo) or _cd.llave_secreta(fila_cargo.dueno_id or "")):
            # Cobro DIRECTO: se devuelve desde la cuenta Culqi del CLUB.
            kw = {"llave": _cd.llave_secreta(fila_cargo.dueno_id or "")} if _es_directo(fila_cargo) else {}
            r = culqi.reembolsar(charge_id=fila_cargo.culqi_charge_id, monto_centimos=min(monto_dev, fila_cargo.monto_centimos),
                                 **kw)
            if r.get("ok"):
                reembolso, refund_id = "reembolsado", r.get("refund_id")
                fila_cargo.estado = "reembolsado"
            else:
                reembolso, detalle = "fallo", str(r.get("error") or "")[:160]
        elif fila_cargo is not None and fila_cargo.estado == "aprobado" and _reembolso_ec_posible(fila_cargo):
            # Pasarela de Ecuador con reembolso por API (si el módulo lo trae).
            r = _reembolsar_ec(fila_cargo, monto_dev)
            if r.get("ok"):
                reembolso, refund_id = "reembolsado", r.get("refund_id")
                fila_cargo.estado = "reembolsado"
            else:
                reembolso, detalle = "fallo", str(r.get("error") or "")[:160]
        else:
            reembolso = "manual"  # pago viejo del app sin cargo ligado: el operador devuelve
    elif est["pagado"]:
        # Todo con bono (sin plata de por medio): a tiempo se devuelven las
        # horas; tarde, no (misma política que el dinero).
        reembolso = "bono" if (est["reembolsable"] and est.get("bono_horas")) else "sin_reembolso"
    # BONO y PUNTOS: si la cancelación tiene devolución, vuelven al jugador
    # (horas a sus créditos del local; puntos con una fila negativa en
    # `pichangol_puntos_canjes`). Tarde se pierden, como el dinero.
    ben_dev = {"horas": 0, "puntos": 0}
    if est["pagado"] and est["reembolsable"] and (est.get("bono_horas") or est.get("puntos")):
        try:
            ben_dev = beneficios.devolver_por_cancelacion(ref, filas, c, email)
        except Exception as ex:  # noqa: BLE001
            print(f"[cancelar] {ref} no se pudieron devolver bono/puntos: {ex}", flush=True)
    # Reversa contable del dueño solo si el cliente recupera su dinero.
    deuda = 0
    costo_pasarela = 0
    dueno = (c.get("dueno") or "").strip().lower() if c else ""
    if _es_directo(fila_cargo) and reembolso in ("reembolsado", "manual"):
        # Cobro directo devuelto: la comisión de la plataforma vuelve al club.
        _cd.revertir_comision(ref)
        if reembolso == "manual" and dueno and not detalle.startswith("division:"):  # el pago dividido avisa por parte
            try:
                from pagos.router import _aviso_push_usuario
                _aviso_push_usuario(dueno, "Devuelve un pago 💸",
                                    f"{filas[0].get('jugador') or email} canceló a tiempo {(c or {}).get('nombre', '')} "
                                    f"{filas[0]['fecha']} {filas[0]['hora_inicio']}: devuélvele {sim} {monto_dev / 100.0:.2f} "
                                    "por el mismo medio con el que te pagó.", tipo="reserva")
            except Exception:  # noqa: BLE001
                pass
    if reembolso in ("reembolsado", "fallo", "manual", "saldo") and dueno:
        liq = _st.pago_por_charge(ids[0])
        if liq is not None and liq.tipo in ("liquidacion_online", "liquidacion_full") and liq.estado == "aprobado":
            if liq.liquidado:
                from pagos.router import comision_centimos as _com
                deuda = liq.monto_centimos - (_com(liq.monto_centimos / 100.0, liq.moneda) if liq.tipo == "liquidacion_online" else 0)
            else:
                liq.estado = "anulado"
                com = _st.pago_por_charge(f"{ids[0]}_com")
                if com is not None and com.estado == "aprobado":
                    com.estado = "anulado"
                    promo = min(int(com.promo_centimos or 0), com.monto_centimos)
                    if promo:
                        _st.acreditar_promo(dueno, promo)
                    if com.monto_centimos - promo > 0:
                        _st.acreditar(dueno, com.monto_centimos - promo)
        if cancela_anfitrion and reembolso != "saldo":
            # Culpa del anfitrión: el costo de la pasarela de esa devolución
            # (Culqi no devuelve su comisión) se le descuenta en la siguiente
            # liquidación. A saldo no hay costo.
            base_pasarela = fila_cargo.monto_centimos if fila_cargo is not None else monto_c + cargo_c
            costo_pasarela = _tp.costo_centimos(base_pasarela, iso, medio_pago or "tarjeta", "liquidacion_online")
            deuda += costo_pasarela
        if deuda > 0:
            _st.registrar_pago(tipo="ajuste_cancelacion", monto_centimos=deuda, moneda=iso, estado="pendiente",
                               dueno_id=dueno, culqi_charge_id=f"{ids[0]}_ajuste",
                               concepto=(f"{'Cancelación del local' if cancela_anfitrion else 'Descuento por cancelación web'} · "
                                         f"{(c or {}).get('nombre', '')} · {filas[0]['fecha']} {filas[0]['hora_inicio']}"
                                         + (f" (incluye pasarela {sim} {costo_pasarela / 100.0:.2f})" if costo_pasarela else "")))
    try:
        import fidelidad as _fid
        _fid.revertir_canje(ref)  # la reserva premiada se cancela → el premio vuelve al jugador
    except Exception:  # noqa: BLE001
        pass
    if not datos.eliminar_reservas(ids):
        return {"ok": False, "error": "no_se_pudo", "mensaje": "No pudimos liberar el horario. Inténtalo de nuevo."}
    try:   # quien esperaba estos turnos recibe "¡Se liberó tu hora!" (como el app)
        from web import jugador_espera as _je
        _je.avisar_liberados([(str(f.get("cancha_id")), str(f.get("fecha")), str(f.get("hora_inicio"))) for f in filas],
                             salvo=email)
    except Exception:  # noqa: BLE001
        pass
    # Boleador contratado en esta reserva: su solicitud se cancela y su
    # liquidación se revierte (la devolución al jugador ya incluyó su parte).
    try:
        import boleadores as _bol
        _bol.cancelar_por_reserva(ref, ids, quien=("local" if cancela_anfitrion else "cliente"))
    except Exception:  # noqa: BLE001
        pass
    reg = {"id": _st.next_id("cancelacion_web"), "ref": ref, "ids": ids, "usuario": email, "cancha_id": filas[0]["cancha_id"],
           "cancha": (c or {}).get("nombre") or "", "club": (c or {}).get("club") or "", "fecha": str(filas[0]["fecha"]),
           "hora_inicio": str(filas[0]["hora_inicio"]), "hora_fin": str(filas[-1]["hora_fin"]), "turnos": len(filas),
           "monto": monto, "moneda": sim, "moneda_iso": iso, "pagado": bool(est["pagado"]), "horas_antes": est["horas"],
           "reembolso": reembolso, "refund_id": refund_id, "detalle": detalle, "deuda_dueno_centimos": deuda,
           "dueno": dueno, "creado_en": _ahora().isoformat(),
           # Política fase 4: qué se devolvió, por dónde y por qué.
           "motivo": mot, "medio_devolucion": medio if monto_dev > 0 else "", "monto_devuelto_centimos": monto_dev if reembolso != "sin_reembolso" else 0,
           "cargo_centimos": cargo_c, "incluye_cargo": bool(incluye_cargo and monto_dev > 0),
           "cancela_anfitrion": bool(cancela_anfitrion), "quien": quien or email, "costo_pasarela_centimos": costo_pasarela,
           "bono_horas_devueltas": ben_dev["horas"], "puntos_devueltos": ben_dev["puntos"]}
    _st.cancelaciones_web.append(reg)
    try:
        from pagos.router import _aviso_push_usuario
        rango = f"{filas[0]['hora_inicio']}–{filas[-1]['hora_fin']}"
        dev_txt = f"{sim} {monto_dev / 100.0:.2f}"
        if dueno and not cancela_anfitrion:
            _aviso_push_usuario(dueno, "Reserva cancelada 📅",
                                f"{filas[0].get('jugador') or email} canceló {(c or {}).get('nombre', '')} · {horarios.fecha_larga(str(filas[0]['fecha']))} {rango}. El horario quedó libre.",
                                tipo="reserva")
        txt = {"reembolsado": f"Te devolvemos {dev_txt} al mismo medio de pago (3 a 7 días hábiles)."
                              + ("" if incluye_cargo else " El cargo por servicio no se devuelve."),
               "saldo": f"Te devolvimos {dev_txt} a tu saldo {MARCA} (100 %, cargo incluido). Ya lo puedes usar.",
               "manual": f"Te devolvemos {dev_txt}; te escribimos para coordinar.",
               "fallo": "Tu devolución está en proceso; te escribimos en breve.",
               "bono": "",
               "sin_reembolso": f"Cancelaste con menos de {int(_dev.horas_minimas(c))} horas: sin devolución.", "no_aplica": ""}[reembolso]
        if ben_dev["horas"]:
            txt = (txt + f" Te devolvimos {ben_dev['horas']} h a tu bono de este local.").strip()
        if ben_dev["puntos"]:
            txt = (txt + f" Recuperaste tus {ben_dev['puntos']} puntos {MARCA}.").strip()
        quien_txt = "El local canceló" if cancela_anfitrion else "Reserva cancelada"
        _aviso_push_usuario(email, quien_txt if cancela_anfitrion else "Reserva cancelada",
                            f"{(c or {}).get('nombre', '')} · {horarios.fecha_larga(str(filas[0]['fecha']))} {rango}. {txt}".strip(), tipo="reserva")
    except Exception:  # noqa: BLE001
        pass
    print(f"[cancelar] {ref} {email} {reembolso} motivo={mot} medio={medio} monto={monto} dev={monto_dev} "
          f"cargo={cargo_c} horas={est['horas']} deuda={deuda} anfitrion={int(cancela_anfitrion)} "
          f"bono_h={ben_dev['horas']} puntos={ben_dev['puntos']} {detalle}", flush=True)
    return {"ok": True, "reembolso": reembolso, "monto": monto, "moneda": sim, "horas": est["horas"], "refund_id": refund_id,
            "bono_horas_devueltas": ben_dev["horas"], "puntos_devueltos": ben_dev["puntos"],
            "motivo": mot, "medio": medio if monto_dev > 0 else "", "monto_devuelto": monto_dev / 100.0,
            "incluye_cargo": bool(incluye_cargo and monto_dev > 0), "cargo": cargo_c / 100.0}


@router.post("/web/cancelar")
def cancelar(req: CancelarReq, request: Request = None) -> dict:
    """Cancela una reserva del usuario con sesión (grupo o turno suelto) y
    devuelve según la política (`pagos/devoluciones.py`, fase 4): `medio`
    'saldo' = 100 % con cargo a su billetera; 'original' = el precio a la
    tarjeta/Yape (el cargo solo en arrepentimiento). Todo queda en
    `stores.cancelaciones_web`."""
    ses = sesion.de_request(request)
    if not ses:
        return {"ok": False, "error": "sesion_requerida", "mensaje": "Inicia sesión con Google para cancelar."}
    email = ses["email"]
    filas = _filas_de_ref(req.ref)
    c = datos.cancha(filas[0]["cancha_id"]) if filas else None
    return _cancelar_reserva(filas, c, email, medio=req.medio)


_MODAL_CANCELAR = (
    "<div class='modal' id='modalCancelar' role='dialog' aria-modal='true'><div class='modal-caja' style='max-width:520px'>"
    "<div class='modal-cab'><button type='button' class='cerrar' id='cerrarCancelar' aria-label='Cerrar'>✕</button><h3>Cancelar reserva</h3></div>"
    "<div class='modal-cuerpo' style='padding:20px 24px'>"
    "<h4 id='cancTit' style='margin:0 0 6px'>¿Seguro que quieres cancelar?</h4>"
    "<p class='sub' id='cancTxt' style='margin:0 0 14px'></p>"
    "<div class='estado' id='cancPol' style='text-align:left'></div>"
    "<div id='cancOpc' style='display:none;margin-top:12px'><div style='font-weight:800;margin-bottom:6px'>¿A dónde te devolvemos?</div><div id='cancOpcLista'></div></div>"
    "<div class='estado bad' id='cancErr' style='display:none'></div></div>"
    "<div class='modal-pie'><button type='button' class='limpiar' id='cancNo'>Mantener reserva</button>"
    "<button type='button' class='btn dark' id='cancSi'>Sí, cancelar</button></div></div></div>")

JS_CANCELAR = (r"""
(function(){
  var m = document.getElementById('modalCancelar'); if(!m) return;
  var ref = '', datos = null;
  function abrir(on){ m.classList.toggle('open', on); document.body.classList.toggle('sin-scroll', on); }
  function fmt(mon, n){ return mon + ' ' + Number(n).toFixed(2); }
  document.addEventListener('click', function(ev){
    var b = ev.target.closest('[data-cancelar]'); if(!b) return;
    ev.preventDefault(); ev.stopPropagation();
    ref = b.dataset.cancelar; datos = b.dataset;
    document.getElementById('cancTit').textContent = '¿Cancelar ' + (datos.nombre || 'la reserva') + '?';
    document.getElementById('cancTxt').textContent = (datos.cuando || '') + (datos.monto ? ' · ' + fmt(datos.moneda || 'S/', datos.monto) : '');
    var pol = document.getElementById('cancPol'), opc = document.getElementById('cancOpc'), lista = document.getElementById('cancOpcLista');
    var opciones = []; try { opciones = JSON.parse(datos.opciones || '[]'); } catch(e){ opciones = []; }
    opc.style.display = 'none'; lista.innerHTML = '';
    if(datos.pagado !== '1' && parseInt(datos.sena || '0') > 0){ pol.className = 'estado'; pol.textContent = 'Adelantaste una seña de ' + fmt(datos.moneda || 'S/', datos.sena) + ': la seña no es reembolsable (queda a favor de la cancha). El horario queda libre para otro jugador.'; }
    else if(datos.pagado !== '1'){ pol.className = 'estado ok'; pol.textContent = 'Pagabas en la cancha: cancelar no tiene costo. El horario queda libre para otro jugador.'; }
    else if(datos.reembolsable === '1' && !opciones.length && parseInt(datos.bono || '0') > 0){
      pol.className = 'estado ok'; pol.textContent = 'Reservaste con tu bono: faltan ' + datos.horas + ' h, así que te devolvemos ' + datos.bono + ' h a tu bono de este local.';
    }
    else if(datos.reembolsable === '1' && opciones.length){
      pol.className = 'estado ok';
      pol.textContent = (datos.motivo === 'arrepentimiento' ? 'Pagaste hace menos de ' + (datos.arrep || '1') + ' h y faltan más de 24 h: te devolvemos el 100 %, cargo por servicio incluido, por el medio que elijas.'
                        : 'Faltan ' + datos.horas + ' h: puedes cancelar con devolución. Elige a dónde te la mandamos.');
      opciones.forEach(function(o, i){
        lista.innerHTML += '<label style="display:flex;gap:10px;align-items:flex-start;padding:10px 12px;border:1px solid var(--trazo);border-radius:12px;margin-bottom:8px;cursor:pointer">' +
          '<input type="radio" name="cancMedio" value="' + o.medio + '"' + (i === 0 ? ' checked' : '') + ' style="width:auto;flex:none;margin-top:3px">' +
          '<span style="flex:1"><b>' + o.etiqueta + ' · ' + fmt(o.simbolo || datos.moneda || 'S/', o.monto) + '</b>' + (i === 0 ? ' <span class="pill ok" style="font-size:12px">Recomendado</span>' : '') +
          '<div class="sub" style="font-size:12.5px;margin-top:2px">' + o.nota + '</div></span></label>';
      });
      opc.style.display = '';
      if(parseInt(datos.bono || '0') > 0) pol.textContent += ' Además te devolvemos ' + datos.bono + ' h a tu bono.';
      if(parseInt(datos.puntos || '0') > 0) pol.textContent += ' Recuperas tus ' + datos.puntos + ' puntos ⟦MARCA⟧.';
    }
    else { pol.className = 'estado bad'; pol.textContent = 'Faltan menos de ' + datos.minimo + ' h para el turno: la cancelación NO tiene devolución (política publicada)' + (parseInt(datos.bono || '0') > 0 ? ' y las horas de tu bono no vuelven' : '') + '. Puedes mantener la reserva y jugar.'; }
    document.getElementById('cancErr').style.display = 'none';
    var si = document.getElementById('cancSi'); si.disabled = false; si.textContent = datos.pagado === '1' && datos.reembolsable !== '1' ? 'Cancelar sin devolución' : 'Sí, cancelar';
    abrir(true);
  });
  document.getElementById('cerrarCancelar').addEventListener('click', function(){ abrir(false); });
  document.getElementById('cancNo').addEventListener('click', function(){ abrir(false); });
  m.addEventListener('click', function(ev){ if(ev.target === m) abrir(false); });
  document.getElementById('cancSi').addEventListener('click', function(){
    var si = this; si.disabled = true; si.textContent = 'Cancelando…';
    var sel = document.querySelector('input[name=cancMedio]:checked'), medio = sel ? sel.value : 'original';
    fetch('/web/cancelar', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ref: ref, medio: medio})})
      .then(function(r){ return r.json(); })
      .then(function(j){
        if(!j.ok){ var e = document.getElementById('cancErr'); e.textContent = j.mensaje || 'No pudimos cancelar.'; e.style.display = 'block'; si.disabled = false; si.textContent = 'Reintentar'; return; }
        var dev = fmt(j.moneda, j.monto_devuelto != null ? j.monto_devuelto : j.monto);
        var msg = {reembolsado: 'Reserva cancelada. Te devolvemos ' + dev + ' al mismo medio de pago en 3 a 7 días hábiles.' + (j.incluye_cargo === false && j.cargo > 0 ? ' El cargo por servicio no se devuelve.' : ''),
                   saldo: 'Reserva cancelada. Te devolvimos ' + dev + ' a tu saldo ⟦MARCA⟧ (cargo incluido): ya lo puedes usar.',
                   manual: 'Reserva cancelada. Te devolvemos ' + dev + '; te escribimos para coordinar.',
                   fallo: 'Reserva cancelada. Tu devolución está en proceso; te escribimos en breve.',
                   bono: 'Reserva cancelada.',
                   sin_reembolso: 'Reserva cancelada sin devolución.', no_aplica: 'Reserva cancelada. El horario quedó libre.'}[j.reembolso] || 'Reserva cancelada.';
        if(j.bono_horas_devueltas > 0) msg += ' Te devolvimos ' + j.bono_horas_devueltas + ' h a tu bono.';
        if(j.puntos_devueltos > 0) msg += ' Recuperaste tus ' + j.puntos_devueltos + ' puntos.';
        try { sessionStorage.setItem('pcg_aviso', msg); } catch(e){}
        location.href = '/mis-reservas';
      }).catch(function(){ var e = document.getElementById('cancErr'); e.textContent = 'Sin conexión. Inténtalo de nuevo.'; e.style.display = 'block'; si.disabled = false; si.textContent = 'Reintentar'; });
  });
})();
""").replace('⟦MARCA⟧', MARCA)


def _boton_cancelar(filas: list[dict], c: dict | None, ses: dict | None, clase: str = "btn sec") -> str:
    """Botón "Cancelar reserva" (solo si la reserva es del usuario con sesión
    y aún no empieza); lleva los datos que el modal necesita explicar."""
    if not ses:
        return ""
    filas = sorted(filas, key=lambda x: (str(x.get("fecha")), str(x.get("hora_inicio"))))
    est = estado_cancelacion(filas, c, ses["email"])
    if not est.get("puede"):
        return ""
    cuando = f"{horarios.fecha_larga(str(filas[0]['fecha']))} · {filas[0]['hora_inicio']}–{filas[-1]['hora_fin']}"
    pol = est.get("politica") or {}
    opciones = ui.json_js([{k: o[k] for k in ("medio", "monto", "etiqueta", "nota", "simbolo", "incluye_cargo")} for o in pol.get("opciones") or []],
                          ensure_ascii=False)
    return (f"<button type='button' class='{clase}' data-cancelar='{e(_ref_de(filas))}' data-nombre='{e((c or {}).get('nombre') or 'la reserva')}' "
            f"data-cuando='{e(cuando)}' data-monto='{est['monto']}' data-moneda='{e(est['moneda'])}' data-pagado='{1 if est['pagado'] else 0}' "
            f"data-sena='{sum(int(f.get('sena') or 0) for f in filas) if str(filas[0].get('medio_pago') or '') == 'sena' else 0}' "
            f"data-reembolsable='{1 if est['reembolsable'] else 0}' data-horas='{est['horas']}' data-minimo='{int(est['minimo_horas'])}' "
            f"data-motivo='{e(pol.get('motivo') or '')}' data-arrep='{pol.get('arrepentimiento_horas', 1):g}' data-opciones='{e(opciones)}' "
            f"data-bono='{int(est.get('bono_horas') or 0)}' data-puntos='{int(est.get('puntos') or 0)}'>Cancelar reserva</button>")


def _url_comprobante(filas: list[dict]) -> str:
    g = (filas[0].get("grupo_reserva_id") or "").strip()
    return f"/reserva/{g if g else filas[0]['id']}"
