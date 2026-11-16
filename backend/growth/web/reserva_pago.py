"""ASEGURAR / PAGAR / LIBERAR una reserva web: `GET /web/cotizar`,
`POST /web/asegurar` (hold de 10 min), `GET /web/fidelidad`,
`GET /web/beneficios`, `POST /web/liberar` y `POST /web/pagar` (Culqi), más
lo que comparte con la pasarela hospedada y el cobro directo
(`plan_cobro_reserva`, `concepto_reserva`, `soltar_bloque`,
`confirmar_reserva_pagada`, `sena_de`).

Movido tal cual desde `web/router.py`, que lo re-exporta (`pago_hospedado`,
`cobro_directo_web` y otros lo llaman como `wr.<función>`).
"""

from __future__ import annotations

from typing import Any
import servicios_extra as _se
import re
import time
from datetime import date, timedelta

from fastapi import APIRouter, Request
from pydantic import BaseModel

from paises import pais_de_coordenadas
from pagos import culqi
from pagos import cargo_servicio as _cs
from web import beneficios, datos, horarios, pago_hospedado, sesion
from reservas import reglas as _reglas
from pagos import cobro_directo as _cd
from web.comun import MAX_SLOTS, _deportes_de, _firma, _firma_ok, _moneda_de, _pago_web_disponible, _pais_de
from web.disponibilidad import _es_iso, _fechas_validas, _slots_del_dia
from web.cancelacion import _cobro_web, _inicio_reserva, _ref_de, _total_de, _url_comprobante

router = APIRouter()


# ── asegurar / pagar / liberar ────────────────────────────────────────────────

class HoraReq(BaseModel):
    fecha: str
    hora: str


class AsegurarReq(BaseModel):
    cancha_id: str
    horas: list[HoraReq]
    extras: list[Any] = []  # claves (APK/web viejos) o {clave, cantidad}
    deporte: str = ""
    nombre: str
    celular: str = ""
    email: str
    boleador: str = ""  # slug del boleador elegido (sparring por turno, opcional)
    fidelidad: bool = False  # usar el premio de la tarjeta de fidelidad del local
    # BONO de horas prepagadas del local (cubre todos los turnos) y canje de
    # PUNTOS Pichangol (100 pts = S/ 3), como `club_detalle._reservar` del app.
    bono: bool = False
    puntos: bool = False
    # "sena" = adelanta la SEÑA del dueño (% de los turnos) y el resto se paga en
    # la cancha; "total" = todo ahora. Vacío = total (navegadores con JS viejo).
    pago: str = ""
    # Medio elegido en la página (yape | tarjeta): en el modelo 2 el cargo
    # depende de él. Vacío = tarjeta (JS viejo).
    medio: str = ""
    # PAGO DIVIDIDO entre amigos (`pagos/division.py`): N personas (2…12, el
    # organizador incluido); 0 = pago normal.
    dividir: int = 0


_contador = {"n": 0}


def _cotizacion_reserva(c: dict, total_soles: float, deporte: str = "", medio: str | None = None) -> "_cs.Cotizacion":
    """CARGO POR SERVICIO de una reserva web (fase 2 del diseño, sep-2026): la
    MISMA cotización al asegurar (lo que ve el jugador) y al cobrar en
    `/web/pagar` (lo que se le carga). Red de seguridad con la tarifa de
    TARJETA como peor caso: lo mostrado nunca es menor que lo cobrado. Con el
    flag `cargo_activo_reservas` en 0 devuelve cargo 0 y total = base."""
    from pagos.router import cotizacion_para
    _sim, iso = _moneda_de(c)
    dep = (deporte or "").strip().lower() or ((_deportes_de(c) or [""])[0])
    # MODELO 2: el cargo depende del medio (Yape es más barato que la tarjeta);
    # sin medio = tarjeta. En el modelo 1 el medio solo toca la red de seguridad.
    return cotizacion_para("reservas", iso, int(round(float(total_soles) * 100)), medio=(medio or None), deporte=dep)


@router.get("/web/cotizar")
def web_cotizar(linea: str = "reservas", moneda: str = "PEN", base: str = "0", deporte: str = "", partes: str = "",
                medio: str = "") -> dict:
    """Cotización PÚBLICA del cargo por servicio para pintar el checkout web
    (espejo de `POST /pagos/cotizar`, que exige X-App-Key). `base` y `partes`
    (separadas por coma) en céntimos. Solo se muestra: el backend recalcula al
    cobrar y nunca confía en lo que manda el navegador."""
    from pagos.router import cotizacion_para
    b = int(base) if str(base).strip().isdigit() else 0
    if b > 50_000_000:
        return {"ok": False, "error": "base"}
    pts = [int(x) for x in (partes or "").split(",") if x.strip().isdigit()][:12]
    md = medio if medio in ("yape", "tarjeta") else None
    cot = cotizacion_para(linea if linea in _cs.LINEAS else "reservas", moneda, b, medio=md,
                          deporte=(deporte or "")[:20], partes=pts)
    return {"ok": True, **cot.dict()}


def _nuevo_id() -> str:
    _contador["n"] = (_contador["n"] + 1) % 100000
    return f"{datos.PREFIJO_ID_WEB}{int(time.time() * 1000)}_{_contador['n']}"


def sena_de(precio_turno: int, pct: int) -> int:
    """Seña de UN turno = `Cancha.senaDe` del app: % del precio redondeado al
    entero (mitad hacia arriba, como `.round()` de Dart)."""
    if pct <= 0:
        return 0
    return int(precio_turno * min(pct, 100) / 100 + 0.5)


def _sesion_o_token(request: Request | None) -> dict | None:
    """Sesión web (cookie) o, desde el APK, el ID token de Google VERIFICADO
    (`X-User-Token`): así el APK usa el MISMO flujo server-side que la web
    (montos calculados aquí, nunca en el teléfono)."""
    ses = sesion.de_request(request) if (sesion.activo() and request is not None) else None
    if ses:
        return ses
    tok = request.headers.get("X-User-Token") if request is not None else None
    if tok:
        import auth_usuario
        email = auth_usuario.usuario_de(None, tok)
        if email:
            return {"email": email, "nombre": "", "via": "app"}
    return None


@router.post("/web/asegurar")
def asegurar(req: AsegurarReq, request: Request = None) -> dict:
    """Toma los slots (INSERT 'nueva') ANTES de cobrar, igual que el APK
    (`insertarSegura`): así el UNIQUE decide quién se queda con la hora. Si el
    cliente no paga, `/web/liberar` (o el vencimiento del hold) los suelta."""
    c = datos.cancha(req.cancha_id)
    if not c or c.get("eliminada"):
        return {"ok": False, "error": "no_encontrada"}
    if not datos.reservable(c):
        return {"ok": False, "error": "no_verificada"}
    sim, iso = _moneda_de(c)
    # COBRO DIRECTO AL CLUB (plan A4-A5): si el club tiene su Culqi o sus
    # medios manuales, se cobra a SU cuenta (sin cargo por servicio de la
    # plataforma; la comisión sale de su saldo).
    directo = _cd.checkout(c, iso)
    if not _pago_web_disponible(iso) and not directo.get("directo"):
        return {"ok": False, "error": "pago_no_disponible"}
    # Con login configurado, la reserva es del CORREO de la sesión de Google
    # (como en el app); sin sesión no se reserva.
    ses = _sesion_o_token(request)
    if (sesion.activo() or directo.get("directo")) and not ses:
        return {"ok": False, "error": "sesion_requerida"}
    nombre = (req.nombre.strip() or (ses or {}).get("nombre", ""))[:80]
    email = (ses["email"] if ses else req.email.strip().lower())[:120]
    # Nombre y celular OBLIGATORIOS, misma regla que el app (`_ResumenReserva`):
    # nombre ≥ 3 letras y celular con ≥ 8 dígitos.
    if len(nombre) < 3 or "@" not in email or len(re.sub(r"\D", "", req.celular or "")) < 8:
        return {"ok": False, "error": "datos_invalidos"}
    if ses:
        datos.guardar_celular_si_falta(email, nombre, req.celular)
    if not req.horas or len(req.horas) > MAX_SLOTS:
        return {"ok": False, "error": "horas_invalidas"}
    for h in req.horas:
        if not _es_iso(h.fecha):
            return {"ok": False, "error": "fecha_invalida"}
    datos.liberar_holds_vencidos(c["id"])
    pais = _pais_de(c)
    d_min, d_max = _fechas_validas(pais)
    pedidos = {(h.fecha, h.hora) for h in req.horas}
    # Un slot de madrugada pertenece a la grilla del día ANTERIOR: se evalúan
    # ambos días base y se valida cada hora contra la grilla real.
    bases = set()
    for fb in {h.fecha for h in req.horas}:
        bases.add(fb)
        bases.add((date.fromisoformat(fb) - timedelta(days=1)).isoformat())
    validos: dict[tuple[str, str], dict] = {}
    for fb in sorted(bases):
        if d_min <= fb <= d_max:
            for s in _slots_del_dia(c, fb):
                validos[(s["fecha"], s["hora"])] = s
    deporte = (req.deporte or "").strip().lower()
    if deporte and deporte not in _deportes_de(c):
        deporte = ""
    extras_ok = []
    if req.extras:
        cat = {str(s.get("clave")): s for s in c.get("servicios_extra") or []}
        for it in req.extras:
            if isinstance(it, dict):
                k, cant = str(it.get("clave") or ""), it.get("cantidad") or 1
            else:
                k, cant = str(it or ""), 1
            s = cat.get(k)
            try:
                cant = int(cant)
            except (TypeError, ValueError):
                cant = 1
            if s and float(s.get("precio") or 0) > 0 and k not in [x["clave"] for x in extras_ok]:
                # Línea con el TOTAL (por persona × cantidad, por turno × turnos).
                extras_ok.append(_se.linea_reserva(s, cant, len(pedidos)))
    hoy = horarios.ahora_local(pais).date()
    grupo = f"grp_web_{int(time.time() * 1000)}" if len(pedidos) > 1 else ""
    # Atribución: la pieza del AI Marketing Agent que trajo al jugador (cookie del short-link /go).
    from marketing.agente_ia.router import utm_de_request
    utm_mkt = utm_de_request(request)
    filas, total = [], 0
    for i, key in enumerate(sorted(pedidos)):
        s = validos.get(key)
        if not s or s["ocupado"]:
            return {"ok": False, "error": "ocupado" if s else "hora_invalida"}
        total += s["precio"]
    # REGLAS DEL DUEÑO: turnos seguidos mín./máx. y tope de reservas por día.
    err = _reglas.validar_bloque(c, len(pedidos))
    if err:
        return {"ok": False, "error": err}
    tope = _reglas.de_cancha(c).get("max_reservas_dia_jugador")
    if tope:
        # Por DÍA (no la suma de los días pedidos) y sin contar lo cancelado
        # ni los no-show: quien cancela puede volver a reservar ese día.
        dias_pedidos = {f for f, _h in pedidos}
        por_dia: dict[str, set] = {}
        for r in datos.reservas_de_usuario(email):
            if (r.get("cancha_id") == c["id"] and r.get("fecha") in dias_pedidos
                    and not str(r.get("estado") or "").startswith("cancelad") and r.get("estado") != "noShow"):
                por_dia.setdefault(r["fecha"], set()).add(r.get("grupo_reserva_id") or r.get("id"))
        if any(len(v) >= int(tope) for v in por_dia.values()):
            return {"ok": False, "error": "tope_reservas_dia"}
    # FIDELIDAD DEL LOCAL (sep-2026): si el jugador pidió usar su premio y de
    # verdad lo tiene, el descuento sale del precio de la cancha (hora gratis =
    # el turno más barato a 0; descuento = % por turno). El servidor decide.
    import fidelidad as _fid
    desc_por = [0] * len(pedidos)
    desc_total = 0
    # SEÑA (como `club_detalle._ResumenReserva` del app): solo si el dueño la
    # configuró, el cliente la eligió y no lleva boleador (con boleador todo va
    # en línea). La seña es % del precio de los TURNOS (sin extras) y no se
    # combina con el premio de fidelidad.
    sena_pct = max(0, min(100, int(c.get("sena_pct") or 0)))
    con_sena = sena_pct > 0 and (req.pago or "").strip() == "sena" and not (req.boleador or "").strip()
    # BONO DE HORAS (= `metodo == 'bono'` del app): cubre TODOS los turnos con
    # las horas prepagadas del jugador en este local; camino propio, sin seña,
    # premio de fidelidad, puntos ni boleador. Exige sesión: el bono es de la
    # cuenta de Google, no de un correo escrito a mano.
    con_bono = bool(req.bono)
    if con_bono or req.puntos:
        if not ses or not beneficios.disponible():
            return {"ok": False, "error": "sin_bono" if con_bono else "sin_puntos"}
    if con_bono:
        if (req.boleador or "").strip():
            return {"ok": False, "error": "bono_con_boleador"}
        if beneficios.horas_bono(email, c) < len(pedidos):
            return {"ok": False, "error": "sin_bono"}
        con_sena = False
    if req.fidelidad and not con_sena and not con_bono and _fid.activa_en(c):
        if not _fid.estado(email, c)["disponible"]:
            return {"ok": False, "error": "sin_premio"}
        desc_total, desc_por = _fid.descuento_para(_fid.config_de(c), [validos[k]["precio"] for k in sorted(pedidos)])
    # BOLEADOR (sparring por turno): el servidor vuelve a comprobar que atiende
    # en esta cancha, que la franja cae en su disponibilidad y que no tiene otra
    # solicitud viva cruzada. Entra como una línea más de `extras`.
    if (req.boleador or "").strip():
        import boleadores as _bol
        primero = validos[sorted(pedidos)[0]]
        ultimo = validos[sorted(pedidos)[-1]]
        libres = {b["slug"]: b for b in _bol.disponibles(c["id"], primero["fecha"], primero["hora"], len(pedidos), deporte)}
        b = datos.boleador_por_slug(req.boleador.strip())
        if not b or _bol.slug_de(b["email"]) not in libres:
            return {"ok": False, "error": "boleador_no_disponible"}
        if datos.solicitudes_cruce(b["email"], primero["fecha"], primero["hora"], ultimo["fin"]):
            return {"ok": False, "error": "boleador_no_disponible"}
        extras_ok = [x for x in extras_ok if x.get("clave") != "boleador"] + [_bol.linea_reserva(b, len(pedidos))]
    for i, key in enumerate(sorted(pedidos)):
        s = validos[key]
        filas.append({
            "id": _nuevo_id(), "cancha_id": c["id"], "jugador": nombre, "nivel": "",
            "fecha": s["fecha"], "dia": horarios.etiqueta_dia(s["fecha"], hoy),
            "hora_inicio": s["hora"], "hora_fin": s["fin"], "estado": "nueva",
            "traida_por_app": True, "precio": max(0, int(s["precio"]) - int(desc_por[i])),
            "sena": sena_de(int(s["precio"]), sena_pct) if con_sena else 0, "pagado": False,
            "usuario": email, "deporte": deporte, "moneda": sim,
            "extras": extras_ok if i == 0 else [],
            "telefono": req.celular.strip()[:20], "grupo_reserva_id": grupo,
            "medio_pago": "web_hold", "origen": "web", "utm": utm_mkt,
        })
    precio_turnos = int(round(total - desc_total))
    total = int(round(total - desc_total + sum(x["precio"] for x in extras_ok)))
    if total < 1 and desc_total <= 0:
        return {"ok": False, "error": "monto_invalido"}
    total = max(0, total)
    # Con bono, los turnos ya están pagados (la fila guarda el precio de lista,
    # como el app): solo se cobran los servicios extra que haya elegido.
    bono_cubre = precio_turnos if con_bono else 0
    a_cobrar = total - bono_cubre
    # PUNTOS (= `canjea` del app): 100 pts = S/ 3, pagando TODO en línea en
    # soles, sin seña, sin premio de fidelidad, sin bono y con total > S/ 3.
    con_puntos = False
    if req.puntos and directo.get("directo"):
        # El descuento de puntos lo absorbe la plataforma; con cobro directo
        # no hay de dónde compensárselo al club.
        return {"ok": False, "error": "puntos_no_disponibles"}
    if req.puntos:
        _g, disp = beneficios.puntos_disponibles(email)
        if not beneficios.puede_canjear_puntos(iso=iso, total=a_cobrar, desc_fidelidad=desc_total, con_sena=con_sena,
                                               con_bono=con_bono, disponibles=disp):
            return {"ok": False, "error": "sin_puntos"}
        con_puntos = True
    # PAGO DIVIDIDO (`pagos/division.py`): solo con cobro directo al club, pago
    # total y sin beneficios; los turnos quedan con el hold largo de la división.
    n_div = int(req.dividir or 0)
    if n_div:
        from pagos import division as _division
        err = _division.validar(c=c, directo=directo, n=n_div, total_centimos=int(total) * 100,
                                inicio=_inicio_reserva(filas, pais), con_sesion=bool(ses),
                                incompatibles=bool(con_sena or con_bono or req.puntos or desc_total > 0
                                                   or (req.boleador or "").strip()))
        if err:
            return {"ok": False, "error": err, "mensaje": _division.mensaje(err)}
        for f in filas:
            f["medio_pago"] = datos.MEDIO_HOLD_DIVISION
    r = datos.insertar_reservas(filas)
    if r:
        return {"ok": False, "error": r}
    ids = [f["id"] for f in filas]
    ref = grupo or ids[0]
    if n_div:
        rd = _division.crear(filas=filas, c=c, email=email, nombre=nombre, n=n_div,
                             total_centimos=int(total) * 100, inicio=_inicio_reserva(filas, pais))
        if not rd.get("ok"):
            datos.borrar_reservas(ids)
            return {"ok": False, "error": rd.get("error"), "mensaje": _division.mensaje(str(rd.get("error") or ""))}
        return {"ok": True, "ids": ids, "grupo": grupo, "total": total, "moneda": sim, "division": rd}
    bono_out = puntos_out = None
    if con_bono:
        rb = beneficios.apartar_bono(email, c, ref=ref, ids=ids, horas=len(filas), cubre=bono_cubre, iso=iso)
        if rb:
            datos.borrar_reservas(ids)
            return {"ok": False, "error": "sin_bono" if rb == "sin_bono" else "error"}
        bono_out = {"horas": len(filas), "cubre": bono_cubre, "quedan": max(0, beneficios.horas_bono(email, c))}
    if con_puntos:
        rp = beneficios.apartar_puntos(email, c, ref=ref, ids=ids)
        if rp:
            datos.borrar_reservas(ids)
            return {"ok": False, "error": "sin_puntos" if rp == "sin_puntos" else "error"}
        puntos_out = {"puntos": beneficios.PUNTOS_CANJE, "descuento": beneficios.DESCUENTO_PUNTOS}
    fid_out = None
    if desc_total > 0:
        # Aparta el premio para ESTA reserva (hold): si alguien lo usó en otra
        # pestaña un segundo antes, se libera el horario y se avisa.
        rc = _fid.reservar_canje(email, c, reserva_ref=(grupo or ids[0]), reserva_ids=ids, descuento=desc_total, canal="web")
        if not rc.get("ok"):
            datos.borrar_reservas(ids)
            return {"ok": False, "error": "sin_premio"}
        cfg_f = _fid.config_de(c)
        fid_out = {"descuento": desc_total, "premio": cfg_f["premio"], "texto": _fid.texto_premio_corto(cfg_f)}
    # Cargo por servicio (si la línea está activa): el total a cobrar lo decide
    # el servidor; el navegador solo lo muestra y se lo pasa a Culqi. Con
    # total 0 (hora gratis sin extras) no hay cargo ni pasarela.
    sena_total = sum(int(f["sena"]) for f in filas)
    base_cobro = sena_total if con_sena else (a_cobrar - (beneficios.DESCUENTO_PUNTOS if con_puntos else 0))
    if base_cobro > 0 and directo.get("directo"):
        total_c, cargo_c, cargo_d = int(base_cobro) * 100, 0, None
    elif base_cobro > 0:
        cot = _cotizacion_reserva(c, base_cobro, deporte, req.medio if req.medio in ("yape", "tarjeta") else None)
        total_c, cargo_c, cargo_d = cot.total_centimos, cot.cargo_centimos, (cot.dict() if cot.activo else None)
    else:
        total_c, cargo_c, cargo_d = 0, 0, None
    return {"ok": True, "ids": ids, "grupo": grupo, "firma": _firma(ids),
            "pago": "sena" if con_sena else "total", "sena": sena_total if con_sena else 0,
            "sena_pct": sena_pct if con_sena else 0, "resto": (total - sena_total) if con_sena else 0,
            "total": total, "total_centimos": total_c, "moneda": sim,
            "cargo_centimos": cargo_c, "cargo": cargo_d,
            "fidelidad": fid_out, "bono": bono_out, "puntos": puntos_out, "a_pagar": base_cobro,
            "sin_pago": total_c == 0, "hold_segundos": datos.HOLD_SEGUNDOS,
            "directo": directo if directo.get("directo") else None}


@router.get("/web/fidelidad")
def web_fidelidad(cancha_id: str, request: Request = None) -> dict:
    """Progreso del jugador con sesión en la tarjeta de fidelidad de ese local
    (para la ficha web). Sin sesión, solo la config (sin conteo)."""
    import fidelidad as _fid
    c = datos.cancha(cancha_id)
    if not c or not _fid.activa_en(c):
        return {"ok": False, "error": "no_activa"}
    ses = sesion.de_request(request) if sesion.activo() else None
    email = (ses or {}).get("email", "")
    return {"ok": True, **_fid.estado(email, c)}


@router.get("/web/beneficios")
def web_beneficios(cancha_id: str, request: Request = None) -> dict:
    """Bono de horas del local y puntos Pichangol del jugador con sesión,
    para el checkout de la ficha (como el resumen de reserva del app)."""
    c = datos.cancha(cancha_id)
    ses = sesion.de_request(request) if sesion.activo() else None
    if not c or not ses:
        return {"ok": False, "error": "sesion_requerida" if c else "no_encontrada"}
    _sim, iso = _moneda_de(c)
    out = beneficios.estado(ses["email"], c, iso)
    if isinstance(out.get("puntos"), dict) and _cd.checkout(c, iso).get("directo"):
        # Con cobro directo el canje no aplica (el descuento lo pone la
        # plataforma y no hay de dónde compensárselo al club).
        out["puntos"] = {**out["puntos"], "aplica": False}
    return {"ok": True, **out}


class LiberarReq(BaseModel):
    ids: list[str]
    firma: str


@router.post("/web/liberar")
def liberar(req: LiberarReq) -> dict:
    if not _firma_ok(req.ids, req.firma):
        return {"ok": False, "error": "firma"}
    if pago_hospedado.orden_de_ids(req.ids) is not None:
        # El jugador está pagando en la pasarela (o el pago ya entró y se está
        # confirmando): el apartado lo suelta la orden, nunca el navegador.
        return {"ok": False, "error": "pago_en_curso"}
    if any((f.get("medio_pago") or "") == datos.MEDIO_HOLD_VOUCHER for f in datos.reservas_de(req.ids)):
        # Ya subió su comprobante: el apartado espera la revisión del club (lo
        # suelta el club al rechazar o el vencimiento, nunca el navegador).
        return {"ok": False, "error": "pago_en_revision"}
    if any((f.get("medio_pago") or "") == datos.MEDIO_HOLD_DIVISION for f in datos.reservas_de(req.ids)):
        # Pago dividido en curso: lo suelta la división (vence o la cancela el organizador).
        return {"ok": False, "error": "pago_en_curso"}
    import fidelidad as _fid
    _fid.revertir_canje(ids=req.ids)
    beneficios.soltar(ids=req.ids)  # bono / puntos apartados vuelven al jugador
    return {"ok": datos.borrar_reservas(req.ids)}


class PagarReq(BaseModel):
    ids: list[str]
    firma: str
    token: str
    medio: str = "tarjeta"
    email: str = ""


@router.post("/web/pagar")
def pagar(req: PagarReq, request: Request = None) -> dict:
    """Cobra con Culqi el TOTAL del bloque asegurado y confirma las filas.
    Fallo del cargo → las filas se liberan y no se cobró nada. Éxito →
    confirmada + pagado + liquidación al dueño (billetera-first) + push.
    En dólares / bolivianos el cobro va por la pasarela HOSPEDADA del país
    (`POST /web/pago/reserva`, `web/pago_hospedado.py`); aquí solo llegan,
    en esas monedas, las reservas sin cobro (hora gratis / bono sin extras)."""
    ses = _sesion_o_token(request)
    if sesion.activo() and not ses:
        return {"ok": False, "error": "sesion_requerida",
                "mensaje": "Inicia sesión con Google para pagar tu reserva."}
    if not _firma_ok(req.ids, req.firma):
        return {"ok": False, "error": "firma",
                "mensaje": "La sesión de pago venció. Vuelve a elegir el horario."}
    filas = datos.reservas_de(req.ids)
    if not filas or len(filas) != len(req.ids):
        return {"ok": False, "error": "hold_vencido",
                "mensaje": "El horario ya no está reservado para ti (pasaron más de 10 minutos). Vuelve a elegirlo."}
    if all(f.get("pagado") or f.get("estado") == "confirmada" for f in filas):
        return {"ok": True, "url": _url_comprobante(filas)}
    c = datos.cancha(filas[0]["cancha_id"]) or {}
    sim, iso = _moneda_de(c) if c else ("S/", "PEN")
    email = (ses["email"] if ses else (req.email or filas[0].get("usuario") or "")).strip().lower()
    import fidelidad as _fid
    plan = plan_cobro_reserva(filas)
    canje, ben, ref_fid = plan["canje"], plan["ben"], plan["ref"]
    if plan["a_cobrar"] <= 0:
        # RESERVA SIN COBRO: hora gratis de la tarjeta de fidelidad o turnos
        # cubiertos por el bono, sin extras. No hay cargo en Culqi ni
        # liquidación (el bono ya se le pagó al dueño al venderlo).
        if not canje and not ben["bono"]:
            return {"ok": False, "error": "monto_invalido", "mensaje": "No pudimos confirmar la reserva. Vuelve a elegir el horario."}
        datos.confirmar_reservas(req.ids, "bono" if ben["bono"] else "fidelidad", 0.0, [])
        if canje:
            _fid.confirmar_canje(ref_fid)
        beneficios.confirmar(ref_fid, filas)
        dueno = (c.get("dueno") or "").strip().lower()
        if dueno:
            try:
                from pagos.router import _aviso_push_usuario
                rango = f"{filas[0]['hora_inicio']}–{filas[-1]['hora_fin']}"
                _aviso_push_usuario(
                    dueno, "Nueva reserva 🎟️" if ben["bono"] else "Nueva reserva 🎁",
                    f"{filas[0]['jugador']} · {c.get('nombre', '')} · {horarios.fecha_larga(filas[0]['fecha'])} {rango} · "
                    + (f"pagó con su bono de horas ({len(filas)} h)" if ben["bono"] else "usó su premio de fidelidad (hora gratis)"),
                    tipo="reserva")
            except Exception:  # noqa: BLE001
                pass
        return {"ok": True, "url": _url_comprobante(filas), "charge_id": ""}
    if iso != "PEN" or any(str(f.get("medio_pago") or "") == datos.MEDIO_HOLD_PASARELA for f in filas):
        # Culqi cobra en soles; un bloque en $ / Bs (o que ya está en camino a
        # la pasarela de su país) se paga en `POST /web/pago/reserva`.
        return {"ok": False, "error": "usa_pasarela",
                "mensaje": "Esta reserva se paga con la pasarela de su país. Vuelve a la ficha e inténtalo otra vez."}
    directo = _cd.checkout(c, iso)
    if directo.get("directo"):
        # COBRO DIRECTO con la cuenta Culqi DEL CLUB (plan A4).
        if not ses:
            return {"ok": False, "error": "sesion_requerida", "mensaje": "Inicia sesión para pagar tu reserva."}
        if not directo.get("culqi_public_key"):
            return {"ok": False, "error": "usa_voucher",
                    "mensaje": "Este club recibe el pago por Yape, Plin o transferencia: sube tu comprobante."}
        from web import cobro_directo_web as _cdw
        return _cdw.pagar_con_culqi_del_club(filas, c, email, plan=plan, token=req.token.strip(),
                                             medio="yape" if req.medio == "yape" else "tarjeta",
                                             nombre=((ses or {}).get("nombre") or filas[0].get("jugador") or ""))
    # Cargo por servicio: se RECALCULA aquí (misma regla que en /web/asegurar);
    # lo que se cobra = precio + cargo. El dueño recibe sobre el precio.
    # SEÑA: la fijó /web/asegurar en cada fila; se cobra solo eso (+ su cargo
    # por servicio) y el resto queda "por cobrar en la cancha" (pagado=false).
    medio_pedido = "yape" if req.medio == "yape" else "tarjeta"
    cot = _cotizacion_reserva(c, plan["base_cobro"], str(filas[0].get("deporte") or ""), medio_pedido)
    monto_cobro = cot.total_centimos
    concepto = concepto_reserva(c, filas, plan["es_sena"])
    # Datos del pagador para el antifraude de Culqi: nombre de Google (real) o
    # el que escribió en la reserva, celular de la reserva, país de la cancha.
    from db.store import stores as _st
    cliente = _st.cliente_de(
        email, nombre=((ses or {}).get("nombre") or filas[0].get("jugador") or ""),
        telefono=str(filas[0].get("telefono") or ""), pais=(pais_de_coordenadas(c.get("lat"), c.get("lng")) or ""))
    cargo = culqi.crear_cargo(
        token=req.token.strip(), monto_centimos=monto_cobro, email=email,
        descripcion=concepto[:80], moneda=iso, cliente=cliente,
        metadata={"canal": "web", "reserva_id": filas[0]["id"], "cancha_id": filas[0]["cancha_id"],
                  "cargo_servicio_centimos": cot.cargo_centimos})
    if not cargo.get("ok"):
        soltar_bloque(filas)
        msg = str(cargo.get("error") or "")
        return {"ok": False, "error": "cargo_rechazado",
                "mensaje": "El pago fue rechazado por tu banco o billetera. No se te cobró nada y el "
                           "horario quedó libre para que lo intentes de nuevo." + (f" ({msg[:80]})" if msg else "")}
    medio = "yape" if req.medio == "yape" else "tarjeta"
    if len(datos.reservas_de(req.ids)) != len(req.ids):
        # Carrera (auditoría C2): el apartado venció/se liberó MIENTRAS Culqi
        # cobraba. Antes quedaba cobrado sin reserva; ahora se devuelve ya.
        r = culqi.reembolsar(charge_id=str(cargo.get("charge_id") or ""), monto_centimos=monto_cobro)
        print(f"[pagar] {req.ids[0]} cobrado sin apartado → reembolso {'ok' if r.get('ok') else r.get('error')}", flush=True)
        return {"ok": False, "error": "hold_vencido",
                "mensaje": "Tu horario se liberó antes de confirmar el pago. Te devolvimos el dinero."}
    confirmar_reserva_pagada(filas, c, email, plan=plan, charge_id=str(cargo.get("charge_id") or ""), medio=medio,
                             monto_cobro=monto_cobro, cargo_centimos=cot.cargo_centimos,
                             cargo_desglose=list(cot.desglose or []), cargo_ajuste=cot.ajuste_seguridad_centimos)
    return {"ok": True, "url": _url_comprobante(filas), "charge_id": cargo.get("charge_id")}


def plan_cobro_reserva(filas: list[dict]) -> dict:
    """Qué se cobra de un bloque asegurado (lo mismo para Culqi y para la
    pasarela hospedada): total de la reserva, lo que cubre el BONO, el
    descuento de PUNTOS, la SEÑA y la base del cobro (sin el cargo por
    servicio). Determinístico: se recalcula desde las filas y los apartados,
    nunca desde lo que diga el navegador."""
    total = _total_de(filas)
    ref = _ref_de(filas)
    canje = datos.canje_por_ref(ref)
    # BONO / PUNTOS apartados en /web/asegurar: con bono los turnos ya están
    # pagados (solo se cobran los extras); los puntos restan S/ 3 al cobro,
    # pero NO a la liquidación del dueño (el descuento lo pone Pichangol).
    ben = beneficios.de_ref(ref)
    bono_cubre = sum(int(f["precio"]) for f in filas) if ben["bono"] else 0
    puntos_desc = beneficios.DESCUENTO_PUNTOS if ben["puntos"] else 0
    a_cobrar = total - bono_cubre
    sena_total = sum(int(f.get("sena") or 0) for f in filas)
    es_sena = sena_total > 0
    base_cobro = sena_total if es_sena else a_cobrar - puntos_desc
    return {"total": total, "ref": ref, "canje": canje, "ben": ben, "bono_cubre": bono_cubre, "puntos_desc": puntos_desc,
            "a_cobrar": a_cobrar, "sena_total": sena_total, "es_sena": es_sena, "base_cobro": base_cobro}


def concepto_reserva(c: dict, filas: list[dict], es_sena: bool) -> str:
    return f"{'Seña · ' if es_sena else ''}Reserva {c.get('nombre', 'cancha')} {filas[0]['fecha']} {filas[0]['hora_inicio']}"


def soltar_bloque(filas_o_ids) -> None:
    """Pago que NO entró (rechazado, cancelado, vencido): el premio de
    fidelidad y el bono / puntos apartados vuelven al jugador y el horario
    queda libre. Mismo camino para Culqi y la pasarela hospedada."""
    import fidelidad as _fid
    lista = list(filas_o_ids or [])
    ids = [str(f["id"]) if isinstance(f, dict) else str(f) for f in lista]
    filas = [f for f in lista if isinstance(f, dict)] or datos.reservas_de(ids)
    ref = _ref_de(filas) if filas else ""
    try:
        if not (ref and _fid.revertir_canje(ref)):
            _fid.revertir_canje("", ids)
    except Exception:  # noqa: BLE001
        pass
    try:
        beneficios.soltar(ref, ids)  # bono / puntos apartados vuelven al jugador
    except Exception:  # noqa: BLE001
        pass
    datos.borrar_reservas(ids)


def confirmar_reserva_pagada(filas: list[dict], c: dict, email: str, *, plan: dict, charge_id: str, medio: str,
                             monto_cobro: int, cargo_centimos: int, cargo_desglose: list, cargo_ajuste: int) -> None:
    """Lo que pasa DESPUÉS de que la pasarela aprobó el cobro de una reserva
    web (Culqi en `/web/pagar`; PayPhone / Libélula / simulada en
    `web/pago_hospedado.py`): confirma las filas (con seña: confirmada sin
    pagar), usa el premio de fidelidad y el bono / puntos, deja el cobro en el
    libro (`cobro_web`, ligado a la reserva: así se puede devolver), liquida
    al dueño en la moneda de la cancha, avisa y abre la solicitud del
    boleador. `charge_id`: `chr_…` (Culqi) o `pp:` / `lib:` / `sim:` + id."""
    import fidelidad as _fid
    from db.store import stores as _st
    sim, iso = _moneda_de(c) if c else ("S/", "PEN")
    ids = [str(f["id"]) for f in filas]
    canje, ben, ref_fid = plan["canje"], plan["ben"], plan["ref"]
    es_sena, sena_total, total = plan["es_sena"], plan["sena_total"], plan["total"]
    bono_cubre, a_cobrar, base_cobro = plan["bono_cubre"], plan["a_cobrar"], plan["base_cobro"]
    # Con seña la reserva queda confirmada pero NO pagada (el dueño cobra el
    # resto en la cancha), medio 'sena' como en el app.
    datos.confirmar_reservas(ids, "sena" if es_sena else ("bono" if ben["bono"] else medio), cargo_centimos / 100.0,
                             list(cargo_desglose or []), pagado=not es_sena)
    if canje:
        _fid.confirmar_canje(ref_fid)  # el premio queda USADO con el pago aprobado
    # Bono usado y, con puntos, el canje queda en `pichangol_puntos_canjes`
    # (la tabla del app) recién ahora que el pago entró.
    beneficios.confirmar(ref_fid, filas)
    try:
        # El cargo queda en el libro (tipo cobro_web) ligado a la reserva/grupo:
        # es lo que permite REEMBOLSAR desde la web al cancelar.
        if _cobro_web(_ref_de(filas)) is None:
            _st.registrar_pago(tipo="cobro_web", monto_centimos=monto_cobro, moneda=iso, estado="aprobado",
                               culqi_charge_id=charge_id, email=email, medio=medio,
                               concepto=f"web:{_ref_de(filas)}", cargo_servicio_centimos=cargo_centimos,
                               cargo_desglose=(list(cargo_desglose or []) or None), cargo_ajuste_centimos=cargo_ajuste)
    except Exception:  # noqa: BLE001
        pass
    dueno = (c.get("dueno") or "").strip().lower()
    # La parte del BOLEADOR no es del dueño: sale del bruto de su liquidación y
    # abre la solicitud al boleador (acepta o rechaza; ver boleadores.py).
    linea_bol = next((x for f in filas for x in (f.get("extras") or []) if isinstance(x, dict) and x.get("clave") == "boleador"), None)
    bol_soles = float(linea_bol.get("precio") or 0) if linea_bol else 0.0
    # Al dueño: el precio COMPLETO (los puntos los absorbe Pichangol, como en
    # el app); con bono, solo los extras (los turnos los cobró con el pack).
    total_dueno = max(0.0, float(total) - bol_soles - bono_cubre)
    if dueno and (es_sena or total_dueno > 0):
        try:
            from pagos.router import LiquidacionOnlineReq, post_liquidacion_online, _aviso_push_usuario
            post_liquidacion_online(LiquidacionOnlineReq(
                dueno_id=dueno, monto_soles=(float(sena_total) if es_sena else total_dueno), reserva_id=filas[0]["id"],
                concepto=f"{'Seña' if es_sena else 'Reserva'} web · {c.get('nombre', '')} · {filas[0]['fecha']} {filas[0]['hora_inicio']}",
                medio=("sena" if es_sena else medio), medio_pago=medio, moneda=iso, charge_id=charge_id,
                cargo_servicio_centimos=cargo_centimos, cargo_desglose=list(cargo_desglose or []),
                cargo_ajuste_centimos=cargo_ajuste))
            rango = f"{filas[0]['hora_inicio']}–{filas[-1]['hora_fin']}"
            _aviso_push_usuario(
                dueno, "Nueva reserva 📅",
                f"{filas[0]['jugador']} · {c.get('nombre', '')} · {horarios.fecha_larga(filas[0]['fecha'])} {rango} · "
                + (f"pagó la seña de {sim} {sena_total:.2f} por la web · cobra {sim} {total - sena_total:.2f} en la cancha" if es_sena
                 else (f"pagó con su bono de horas ({len(filas)} h) y {sim} {a_cobrar:.2f} de extras por la web" if ben["bono"]
                       else f"pagó {sim} {total:.2f} por la web")) + (" · usó su premio de fidelidad" if canje else ""), tipo="reserva")
        except Exception:  # noqa: BLE001 — la contabilidad nunca deshace un cobro
            pass
    if linea_bol and bol_soles > 0:
        try:
            import boleadores as _bol
            b = datos.boleador_por_slug(str(linea_bol.get("boleador") or ""))
            if b:
                # Parte del cargo del boleador sobre lo COBRADO (con puntos, total − S/ 3), como el app.
                cargo_bol = int(round(cargo_centimos * bol_soles / float(base_cobro))) if base_cobro and cargo_centimos else 0
                _bol.crear_solicitud(boleador=b, cliente_email=email, cliente_nombre=str(filas[0].get("jugador") or ""),
                                     reserva_ids=ids, reserva_ref=_ref_de(filas), cancha=c,
                                     fecha=str(filas[0]["fecha"]), hora_inicio=str(filas[0]["hora_inicio"]),
                                     hora_fin=str(filas[-1]["hora_fin"]), turnos=len(filas),
                                     charge_id=charge_id, cargo_centimos=cargo_bol, medio=medio, canal="web")
        except Exception:  # noqa: BLE001
            pass
