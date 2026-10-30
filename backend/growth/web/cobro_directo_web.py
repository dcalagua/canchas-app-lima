"""Endpoints del COBRO DIRECTO AL CLUB (plan nocturno A4 + A5 + A6).

Jugador (sesión web o ID token de Google del APK, mismo bloque apartado por
`/web/asegurar`, monto calculado por el servidor):
- `POST /web/pagar` (en `web/router.py`) → si el club tiene Culqi propio,
  cobra con SU llave (`pagar_con_culqi_del_club`).
- `POST /web/voucher` → reporta un pago manual (Yape/Plin/transferencia…) con
  la foto del voucher y el nº de operación; el apartado espera la revisión.

Dueño (identidad verificada, `auth_usuario.requiere_usuario`):
- `GET  /club/pagos`                         → su configuración + deuda + pendientes.
- `PUT  /club/pagos/culqi` · `DELETE …`       → su cuenta Culqi (sk cifrada).
- `PUT  /club/pagos/medios`                  → sus medios manuales.
- `GET  /club/pagos/vouchers[?estado=]`      → bandeja.
- `GET  /club/pagos/vouchers/{id}/imagen`    → la foto (solo el dueño).
- `POST /club/pagos/vouchers/{id}/aprobar` · `…/rechazar`.

Culqi → `POST /pagos/culqi/webhook/club/{ref}`: conciliación (vuelve a
consultar el cargo con la llave del club; confirma un apartado que quedó
cobrado sin confirmar).
"""

from __future__ import annotations

import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

import auth_usuario
import config
from pagos import cobro_directo as cd
from pagos import culqi
from web import datos, horarios

router = APIRouter(tags=["cobro-directo"])


def _wr():
    from web import router as wr  # import perezoso: web.router importa este módulo
    return wr


def _pais_del_dueno(email: str) -> str:
    from paises import pais_de_coordenadas
    for c in datos.canchas_de_dueno(email) or []:
        p = pais_de_coordenadas(c.get("lat"), c.get("lng"))
        if p:
            return p
    return "PE"


def _avisar(email: str, titulo: str, texto: str) -> None:
    try:
        from pagos.router import _aviso_push_usuario
        _aviso_push_usuario(email, titulo, texto, tipo="reserva")
    except Exception:  # noqa: BLE001 — un aviso jamás rompe un cobro
        pass


# ── confirmación común (Culqi del club o voucher aprobado) ───────────────────

def confirmar_directo(filas: list[dict], c: dict, email: str, *, plan: dict, medio: str,
                      cobro_id: str, monto_centimos: int) -> dict:
    """Confirma un bloque pagado DIRECTO al club: filas confirmadas, premio /
    bono usados, cobro en el libro (`cobro_directo`, así se puede devolver) y
    comisión de la plataforma desde el saldo del dueño (o deuda)."""
    import fidelidad as _fid
    from db.store import stores
    from web import beneficios
    wr = _wr()
    sim, iso = wr._moneda_de(c)
    ids = [str(f["id"]) for f in filas]
    ref = wr._ref_de(filas)
    es_sena = plan["es_sena"]
    datos.confirmar_reservas(ids, "sena" if es_sena else medio, 0.0, [], pagado=not es_sena)
    if plan.get("canje"):
        _fid.confirmar_canje(plan["ref"])
    beneficios.confirmar(plan["ref"], filas)
    dueno = (c.get("dueno") or "").strip().lower()
    if wr._cobro_web(ref) is None:
        stores.registrar_pago(tipo="cobro_directo", monto_centimos=int(monto_centimos), moneda=iso,
                              estado="aprobado", dueno_id=dueno, culqi_charge_id=cobro_id, email=email,
                              medio=medio, concepto=f"web:{ref}")
    # Comisión sobre el PRECIO de la reserva (con seña también: la reserva es
    # la misma); lo que cubrió un bono de horas ya pagó comisión al venderse.
    base = max(0, int(plan["total"]) - int(plan.get("bono_cubre") or 0)) * 100
    com = cd.cobrar_comision(dueno, ref, base, iso, medio,
                             concepto=f"Reserva {c.get('nombre', '')} {filas[0]['fecha']} {filas[0]['hora_inicio']}")
    rango = f"{filas[0]['hora_inicio']}–{filas[-1]['hora_fin']}"
    if dueno:
        cobrado = f"{sim} {monto_centimos / 100.0:.2f}"
        _avisar(dueno, "Nueva reserva 📅",
                f"{filas[0].get('jugador') or email} · {c.get('nombre', '')} · {horarios.fecha_larga(filas[0]['fecha'])} "
                f"{rango} · te pagó {cobrado} directo" + (f" · cobra {sim} {plan['total'] - plan['sena_total']:.2f} en la cancha"
                                                         if es_sena else ""))
        if com.get("deuda_centimos"):
            _avisar(dueno, "Recarga tu saldo",
                    f"La comisión de esta reserva ({sim} {com['deuda_centimos'] / 100.0:.2f}) quedó por pagar. "
                    "Recarga tu saldo para seguir recibiendo pagos en línea.")
    return {"ok": True, "url": wr._url_comprobante(filas), "comision": com}


def pagar_con_culqi_del_club(filas: list[dict], c: dict, email: str, *, plan: dict, token: str, medio: str,
                             nombre: str) -> dict:
    wr = _wr()
    dueno = (c.get("dueno") or "").strip().lower()
    llave = cd.llave_secreta(dueno)
    monto = int(plan["base_cobro"]) * 100
    if not llave or monto < 100:
        return {"ok": False, "error": "pago_no_disponible", "mensaje": "El pago en línea de este club no está disponible."}
    from db.store import stores
    from paises import pais_de_coordenadas
    cliente = stores.cliente_de(email, nombre=nombre, telefono=str(filas[0].get("telefono") or ""),
                                pais=(pais_de_coordenadas(c.get("lat"), c.get("lng")) or ""))
    ref = wr._ref_de(filas)
    cargo = culqi.crear_cargo(token=token, monto_centimos=monto, email=email,
                              descripcion=wr.concepto_reserva(c, filas, plan["es_sena"])[:80], moneda="PEN",
                              cliente=cliente, llave=llave,
                              metadata={"canal": "directo", "reserva_ref": ref, "cancha_id": c["id"]})
    if not cargo.get("ok"):
        wr.soltar_bloque(filas)
        msg = str(cargo.get("error") or "")
        return {"ok": False, "error": "cargo_rechazado",
                "mensaje": "El pago fue rechazado por tu banco o billetera. No se te cobró nada y el horario "
                           "quedó libre para que lo intentes de nuevo." + (f" ({msg[:80]})" if msg else "")}
    charge_id = str(cargo.get("charge_id") or "")
    vivas = datos.reservas_de([str(f["id"]) for f in filas])
    if len(vivas) != len(filas):
        # El apartado se perdió mientras Culqi cobraba: devolver YA, en el servidor.
        r = culqi.reembolsar(charge_id=charge_id, monto_centimos=monto, motivo="solicitud_comprador", llave=llave)
        print(f"[directo] {ref} cobrado sin apartado → reembolso {'ok' if r.get('ok') else r.get('error')}", flush=True)
        return {"ok": False, "error": "hold_vencido",
                "mensaje": "Tu horario se liberó antes de confirmar el pago. Te devolvimos el dinero."}
    out = confirmar_directo(filas, c, email, plan=plan, medio=medio, cobro_id=charge_id, monto_centimos=monto)
    return {**out, "charge_id": charge_id}


# ── voucher (jugador) ────────────────────────────────────────────────────────

class VoucherReq(BaseModel):
    ids: list[str] = Field(max_length=12)
    firma: str
    medio: str
    operacion: str = Field(max_length=40)
    imagen: str = Field(max_length=9_000_000)   # data URL / base64 de la foto


@router.post("/web/voucher")
def subir_voucher(req: VoucherReq, request: Request) -> dict:
    wr = _wr()
    ses = wr._sesion_o_token(request)
    if not ses:
        return {"ok": False, "error": "sesion_requerida"}
    if not wr._firma_ok(req.ids, req.firma):
        return {"ok": False, "error": "firma"}
    filas = datos.reservas_de(req.ids)
    if not filas or len(filas) != len(req.ids) or any(f.get("estado") != "nueva" or f.get("pagado") for f in filas):
        return {"ok": False, "error": "hold_vencido"}
    email = ses["email"]
    if any((f.get("usuario") or "").strip().lower() != email for f in filas):
        return {"ok": False, "error": "no_es_tu_reserva"}
    c = datos.cancha(filas[0]["cancha_id"]) or {}
    _sim, iso = wr._moneda_de(c)
    plan = wr.plan_cobro_reserva(filas)
    if plan["base_cobro"] <= 0:
        return {"ok": False, "error": "monto_invalido"}
    r = cd.registrar_voucher(filas=filas, c=c, email=email, nombre=str(filas[0].get("jugador") or ""),
                             medio=req.medio, operacion=req.operacion, imagen_b64=req.imagen,
                             monto_centimos=int(plan["base_cobro"]) * 100, iso=iso, ref=wr._ref_de(filas))
    if not r.get("ok"):
        return r
    if not datos.marcar_hold_voucher([str(f["id"]) for f in filas]):
        cd.repo().resolver_pago_manual(r["pago_id"], "vencido", "sistema", "apartado_perdido")
        return {"ok": False, "error": "hold_vencido"}
    dueno = (c.get("dueno") or "").strip().lower()
    _avisar(dueno, "Confirma un pago 🧾",
            f"{filas[0].get('jugador') or email} reportó su pago de {c.get('nombre', '')} {filas[0]['fecha']} "
            f"{filas[0]['hora_inicio']}. Revísalo en Pagos por confirmar.")
    return {"ok": True, "pago_id": r["pago_id"], "vence_en": r["vence_en"],
            "mensaje": "Recibimos tu comprobante. El club lo confirmará en breve; te avisamos."}


@router.get("/club/pagos/checkout/{cancha_id}", dependencies=auth_usuario.APP)
def checkout_publico(cancha_id: str) -> dict:
    """Qué medios de cobro DIRECTO ofrece el club de esta cancha (lo que el
    jugador ve antes de apartar). Solo datos que el club publica para cobrar:
    llave PÚBLICA de Culqi y sus medios manuales."""
    c = datos.cancha(cancha_id)
    if not c or c.get("eliminada"):
        raise HTTPException(status_code=404, detail="no_encontrada")
    _sim, iso = _wr()._moneda_de(c)
    return {"ok": True, **cd.checkout(c, iso)}


# ── dueño ────────────────────────────────────────────────────────────────────

class CulqiClubReq(BaseModel):
    public_key: str = Field(max_length=120)
    secret_key: str = Field(max_length=120)


class MediosReq(BaseModel):
    medios: list[dict] = Field(default_factory=list, max_length=cd.MAX_MEDIOS)


class RechazoReq(BaseModel):
    motivo: str = Field(default="", max_length=140)


def _iso_dueno(email: str) -> str:
    return {"PE": "PEN", "EC": "USD", "BO": "BOB"}.get(_pais_del_dueno(email), "PEN")


def estado_club(email: str, base_url: str = "") -> dict:
    """Configuración de cobro directo del club + estado de la comisión. La
    usan el APK (`GET /club/pagos`) y la web del anfitrión (Cobros del club,
    Ingresos, banner de Hoy): una sola fuente."""
    iso = _iso_dueno(email)
    pais = _pais_del_dueno(email)
    pend = cd.repo().pagos_manuales_de(email, ("en_revision",)) if cd.disponible() else []
    return {"ok": True, "disponible": cd.disponible(), "cifrado": cd.cifrado_disponible(),
            "pais": pais, "moneda": iso, "medios_permitidos": list(cd.MEDIOS_POR_PAIS.get(pais, ())),
            "culqi": (cd.resumen_pasarela(email, base_url) if iso == "PEN"
                      else {"configurada": False, "no_aplica": True}),
            "medios": cd.medios_publicos(email),
            "comision": {"deuda_centimos": cd.deuda_centimos(email, iso), "suspendido": cd.suspendido(email, iso),
                         "tope_centimos": cd._tope_deuda_centimos(iso)},
            "pendientes": len(pend)}


def pendientes_de(email: str) -> int:
    """Vouchers del club esperando revisión (insignia del modo anfitrión).
    Nunca lanza: sin base o con error = 0."""
    try:
        return len(cd.repo().pagos_manuales_de(email, ("en_revision",))) if cd.disponible() else 0
    except Exception:  # noqa: BLE001
        return 0


def conectar_culqi(email: str, public_key: str, secret_key: str) -> tuple[int, dict]:
    """(status HTTP, respuesta). Mismas reglas para el APK y la web: solo
    Perú, solo dueños con canchas, llaves verificadas con Culqi y la secreta
    cifrada (`cd.guardar_culqi`)."""
    if _iso_dueno(email) != "PEN":
        return 400, {"ok": False, "error": "culqi_solo_peru"}
    if not datos.canchas_de_dueno(email):
        return 403, {"ok": False, "error": "sin_canchas"}
    r = cd.guardar_culqi(email, public_key, secret_key)
    if not r.get("ok"):
        return (503 if r["error"] == "cifrado_no_configurado" else 400), r
    return 200, r


def guardar_medios_club(email: str, medios: list) -> tuple[int, dict]:
    """(status HTTP, respuesta) de guardar los medios manuales del club."""
    if not datos.canchas_de_dueno(email):
        return 403, {"ok": False, "error": "sin_canchas"}
    r = cd.guardar_medios(email, medios, _pais_del_dueno(email))
    if not r.get("ok"):
        return 400, r
    return 200, r


def bandeja_de(email: str, estado: str = "en_revision") -> list[dict]:
    estados = ("en_revision",) if estado == "en_revision" else ("aprobado", "rechazado", "vencido")
    pagos = cd.repo().pagos_manuales_de(email, estados) if cd.disponible() else []
    return [cd.vista_pago(p) for p in pagos]


def pago_del_dueno(pid: str, email: str) -> dict | None:
    """El voucher `pid` si es de un club de `email`; None si no existe o es
    de otro (los dos casos responden igual: 404)."""
    p = cd.repo().pago_manual(pid) if cd.disponible() else None
    if not p or p["dueno"] != email:
        return None
    return p


def bandeja_operable(email: str, estado: str = "en_revision") -> list[dict]:
    """Bandeja del dueño + la de los locales donde `email` es encargado con
    permiso de vouchers (solo los pagos de ESAS canchas). Para el dueño sin
    encargos es exactamente `bandeja_de`."""
    from web import permisos
    pagos = bandeja_de(email, estado)
    ajenos = permisos.alcance_delegado(email, permisos.VOUCHERS)
    if not ajenos:
        return pagos
    for dueno, ids in ajenos.items():
        pagos += [p for p in bandeja_de(dueno, estado) if p.get("cancha_id") in ids]
    return sorted(pagos, key=lambda p: str(p.get("creado_en") or ""), reverse=True)


def pendientes_operables(email: str) -> int:
    """Insignia de vouchers por revisar (dueño + locales donde ayuda)."""
    try:
        return len(bandeja_operable(email, "en_revision")) if cd.disponible() else 0
    except Exception:  # noqa: BLE001
        return 0


def pago_operable(pid: str, email: str) -> dict | None:
    """El voucher `pid` si lo puede revisar `email`: es de un club suyo o de
    una cancha del local donde es encargado (Recepción). None = 404."""
    p = pago_del_dueno(pid, email)
    if p is not None:
        return p
    from web import permisos
    p = cd.repo().pago_manual(pid) if cd.disponible() else None
    if not p:
        return None
    enc = permisos.encargo_en(email, str(p.get("cancha_id") or ""))
    if enc is None or enc["dueno"] != p["dueno"] or not permisos.permitido(enc["rol"], permisos.VOUCHERS):
        return None
    return p


def aprobar_voucher(p: dict, email: str) -> dict:
    """El club confirma el pago: se confirma el apartado, se registra el
    cobro directo y se cobra la comisión (saldo o deuda)."""
    from pagos import division as _div
    if _div.es_ref(p.get("reserva_ref")):   # parte de un PAGO DIVIDIDO: cuenta su parte
        return _div.voucher_aprobado(p, email)
    pid = p["id"]
    filas = datos.reservas_de(list(p["reserva_ids"]))
    if not filas or len(filas) != len(p["reserva_ids"]):
        cd.repo().resolver_pago_manual(pid, "vencido", email, "apartado_perdido")
        return {"ok": False, "error": "hold_vencido"}
    if not cd.repo().resolver_pago_manual(pid, "aprobado", email):
        return {"ok": False, "error": "ya_resuelto"}
    c = datos.cancha(p["cancha_id"]) or {}
    plan = _wr().plan_cobro_reserva(filas)
    out = confirmar_directo(filas, c, p["jugador_email"], plan=plan, medio=f"voucher_{p['medio']}",
                            cobro_id=f"pm:{pid}", monto_centimos=int(p["monto_centimos"]))
    _avisar(p["jugador_email"], "¡Reserva confirmada! ✅",
            f"{c.get('nombre', 'El club')} confirmó tu pago · {filas[0]['fecha']} {filas[0]['hora_inicio']}.")
    return {"ok": True, "comision": out.get("comision")}


# Motivos de rechazo por SELECCIÓN (web del anfitrión). Se guarda la CLAVE;
# el lado jugador la traduce (`web/router.py` MOTIVO_RECHAZO). Un motivo que
# no es clave (APK con texto) se muestra tal cual.
MOTIVOS_RECHAZO = {"no_llego": "No llegó el pago", "monto": "Monto distinto",
                   "ilegible": "Comprobante ilegible", "otro": "Otro motivo"}


def rechazar_voucher(p: dict, email: str, motivo: str = "") -> dict:
    """El club no reconoce el pago: el horario queda libre y se avisa al jugador."""
    motivo = (motivo or "").strip()
    from pagos import division as _div
    if _div.es_ref(p.get("reserva_ref")):   # parte de un PAGO DIVIDIDO: la parte vuelve a quedar libre
        return _div.voucher_rechazado(p, email, motivo)
    if not cd.repo().resolver_pago_manual(p["id"], "rechazado", email, motivo):
        return {"ok": False, "error": "ya_resuelto"}
    _wr().soltar_bloque(list(p["reserva_ids"]))
    texto = "" if motivo == "otro" else MOTIVOS_RECHAZO.get(motivo, motivo)
    _avisar(p["jugador_email"], "Pago no confirmado",
            "El club no pudo confirmar tu pago" + (f": {texto.lower() if motivo in MOTIVOS_RECHAZO else texto}" if texto else "")
            + ". El horario quedó libre; si ya pagaste, escríbele al club.")
    return {"ok": True}


@router.get("/club/pagos", dependencies=auth_usuario.APP)
def mi_config(email: str = Depends(auth_usuario.requiere_usuario)) -> dict:
    return estado_club(email)


@router.put("/club/pagos/culqi", dependencies=auth_usuario.APP)
def guardar_culqi(req: CulqiClubReq, email: str = Depends(auth_usuario.requiere_usuario)) -> dict:
    status, r = conectar_culqi(email, req.public_key, req.secret_key)
    if status != 200:
        raise HTTPException(status_code=status, detail=r["error"])
    return r


@router.delete("/club/pagos/culqi", dependencies=auth_usuario.APP)
def borrar_culqi(email: str = Depends(auth_usuario.requiere_usuario)) -> dict:
    return {"ok": cd.borrar_culqi(email)}


@router.put("/club/pagos/medios", dependencies=auth_usuario.APP)
def guardar_medios(req: MediosReq, email: str = Depends(auth_usuario.requiere_usuario)) -> dict:
    status, r = guardar_medios_club(email, req.medios)
    if status != 200:
        raise HTTPException(status_code=status, detail=r["error"])
    return r


@router.get("/club/pagos/vouchers", dependencies=auth_usuario.APP)
def bandeja(estado: str = "en_revision", email: str = Depends(auth_usuario.requiere_usuario)) -> dict:
    return {"ok": True, "pagos": bandeja_de(email, estado)}


def _pago_del_dueno(pid: str, email: str) -> dict:
    p = pago_del_dueno(pid, email)
    if p is None:
        raise HTTPException(status_code=404, detail="no_encontrado")
    return p


@router.get("/club/pagos/vouchers/{pid}/imagen", dependencies=auth_usuario.APP)
def imagen(pid: str, email: str = Depends(auth_usuario.requiere_usuario)) -> Response:
    _pago_del_dueno(pid, email)
    datos_img, mime = cd.repo().imagen_voucher(pid)
    if not datos_img:
        raise HTTPException(status_code=404, detail="sin_imagen")
    return Response(content=datos_img, media_type=mime or "image/jpeg",
                    headers={"Cache-Control": "private, no-store"})


@router.post("/club/pagos/vouchers/{pid}/aprobar", dependencies=auth_usuario.APP)
def aprobar(pid: str, email: str = Depends(auth_usuario.requiere_usuario)) -> dict:
    return aprobar_voucher(_pago_del_dueno(pid, email), email)


@router.post("/club/pagos/vouchers/{pid}/rechazar", dependencies=auth_usuario.APP)
def rechazar(pid: str, req: RechazoReq, email: str = Depends(auth_usuario.requiere_usuario)) -> dict:
    return rechazar_voucher(_pago_del_dueno(pid, email), email, req.motivo)


# ── vencimiento y conciliación ───────────────────────────────────────────────

def vencer() -> int:
    """Vouchers sin revisar a tiempo: vencen y sueltan el horario."""
    if not cd.disponible():
        return 0
    from datetime import datetime, timezone
    n = 0
    from pagos import division as _div
    for p in cd.repo().vencidos(datetime.now(timezone.utc)):
        if _div.es_ref(p.get("reserva_ref")):   # parte de un pago dividido: no suelta el horario
            n += int(_div.voucher_vencido(p))
            continue
        if cd.repo().resolver_pago_manual(p["id"], "vencido", "sistema", "sin_revision"):
            _wr().soltar_bloque(list(p["reserva_ids"]))
            _avisar(p["jugador_email"], "Tu reserva se liberó",
                    "El club no confirmó tu pago a tiempo y el horario quedó libre. Si ya pagaste, escríbele al club.")
            _avisar(p["dueno"], "Venció un pago sin revisar",
                    f"No revisaste a tiempo el pago de {p.get('jugador_nombre') or p['jugador_email']}: la reserva se liberó.")
            n += 1
    return n


def _bucle_vencer() -> None:
    while True:
        try:
            vencer()
        except Exception as e:  # noqa: BLE001
            print("[vouchers] error al vencer:", e, flush=True)
        time.sleep(60)


def arrancar_cron() -> None:
    threading.Thread(target=_bucle_vencer, name="vouchers-vencer", daemon=True).start()


@router.post("/pagos/culqi/webhook/club/{ref}")
async def webhook_club(ref: str, request: Request) -> dict:
    """Evento de la cuenta Culqi DE UN CLUB. Nunca se confía en el cuerpo: se
    re-consulta el cargo con la llave del club. Si un apartado quedó COBRADO
    sin confirmar (se cayó la conexión entre el cargo y la confirmación), aquí
    se confirma; si ya no existe, se devuelve el dinero."""
    pas = cd.repo().pasarela_por_ref(ref) if cd.disponible() else None
    if not pas:
        raise HTTPException(status_code=404, detail="no_encontrado")
    try:
        cuerpo = await request.json()
    except Exception:  # noqa: BLE001
        return {"ok": True, "ignorado": "cuerpo"}
    data = cuerpo.get("data") if isinstance(cuerpo, dict) else None
    if isinstance(data, str):
        import json as _json
        try:
            data = _json.loads(data)
        except ValueError:
            data = None
    charge_id = str((data or {}).get("id") or "")
    if not charge_id.startswith("chr_"):
        return {"ok": True, "ignorado": "no_es_cargo"}
    llave = cd.llave_secreta(pas["dueno"])
    info = culqi.obtener_cargo(charge_id, llave=llave)
    if not info.get("ok"):
        return {"ok": True, "ignorado": "consulta"}
    meta = info.get("metadata") or {}
    if meta.get("canal") == "division":   # parte de un PAGO DIVIDIDO
        from starlette.concurrency import run_in_threadpool
        from pagos import division as _div
        return await run_in_threadpool(_div.conciliar_cargo, info, charge_id, llave)
    rref = str(meta.get("reserva_ref") or "")
    if meta.get("canal") != "directo" or not rref:
        return {"ok": True, "ignorado": "sin_reserva"}
    wr = _wr()
    if wr._cobro_web(rref) is not None:
        return {"ok": True, "duplicado": True}
    filas = wr._filas_de_ref(rref) or datos.reservas_de([rref])
    if not filas:
        r = culqi.reembolsar(charge_id=charge_id, monto_centimos=int(info.get("monto_centimos") or 0), llave=llave)
        return {"ok": True, "reembolsado": bool(r.get("ok"))}
    c = datos.cancha(filas[0]["cancha_id"]) or {}
    if (c.get("dueno") or "").strip().lower() != pas["dueno"]:
        return {"ok": True, "ignorado": "otro_club"}
    plan = wr.plan_cobro_reserva(filas)
    if int(info.get("monto_centimos") or 0) != int(plan["base_cobro"]) * 100:
        print(f"[directo] webhook {rref}: monto distinto, se deja al operador", flush=True)
        return {"ok": True, "ignorado": "monto"}
    confirmar_directo(filas, c, str(filas[0].get("usuario") or ""), plan=plan, medio="tarjeta",
                      cobro_id=charge_id, monto_centimos=int(info["monto_centimos"]))
    return {"ok": True, "confirmado": True}
