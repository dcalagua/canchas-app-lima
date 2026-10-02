"""FIDELIDAD DEL LOCAL — "cada N reservas, una hora gratis o un descuento"
(pedido del director, 28-sep-2026; SQL `docs/piloto/supabase_fidelidad.sql`).

Tarjeta tipo "sello de café" POR LOCAL. El dueño configura, una vez por local
(se copia a todas sus canchas como los servicios extra de ámbito local):

    fidelidad = {activa, meta, premio: hora_gratis | descuento, descuentoPct,
                 ventanaDias, aplica: todas | online}

El jugador ve en la ficha "3 de 5 reservas · a 2 de tu hora gratis" (app y
web) y, al llegar a la meta, el premio se aplica en el checkout:

* `hora_gratis`: el turno MÁS BARATO del bloque sale a 0 (una reserva de un
  turno queda gratis; solo se pagan extras/boleador/cargo).
* `descuento`: `descuentoPct` % sobre el precio de la cancha del bloque.

El premio lo absorbe el LOCAL (su promoción): la liquidación al dueño va por
el precio ya descontado y la comisión de Pichangol se calcula sobre eso. Si
el total queda en 0, no hay cargo en la pasarela ni liquidación.

CICLO sin contador aparte: cada canje guarda las reservas que lo ganaron
(`reservas_contadas`) y la reserva premiada; el conteo vigente son las
reservas PAGADAS del jugador en el local (dentro de la ventana) que no están
en ningún canje. Cancelar una reserva premiada devuelve el premio
(`devuelto`); un hold web que no se paga expira solo (`reservado` > 15 min no
cuenta). Reservas MANUALES del dueño no cuentan (no son del jugador en la
app); con `aplica = online` tampoco cuentan las pagadas en la cancha.
"""
from __future__ import annotations

import time
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

import config
import paises
from web import datos

router = APIRouter(prefix="/fidelidad", tags=["fidelidad"])

PREMIOS = ("hora_gratis", "descuento")
METAS = (2, 3, 4, 5, 6, 8, 10, 12, 15, 20)
DESCUENTOS = (10, 15, 20, 25, 30, 50)
VENTANAS = (0, 90, 180, 365)  # 0 = sin límite de tiempo
APLICA = ("todas", "online")
MEDIOS_ONLINE = ("yape", "tarjeta", "online", "web", "sena", "fidelidad")
HOLD_SEGUNDOS = 15 * 60  # un canje `reservado` sin confirmar vence con el hold

DEFAULT = {"activa": False, "meta": 5, "premio": "hora_gratis", "descuentoPct": 20,
           "ventanaDias": 180, "aplica": "todas"}


def _require_app_key(x_app_key: str | None = Header(default=None)) -> None:
    if not config.APP_API_KEY:
        return
    if x_app_key != config.APP_API_KEY:
        raise HTTPException(status_code=401, detail="app_key_invalida")


_APP = [Depends(_require_app_key)]


# ── Config del local ───────────────────────────────────────────────────────────

def normalizar(raw: dict | None) -> dict:
    """Config saneada (lo guardado puede venir de un APK/web viejos o vacío)."""
    raw = raw if isinstance(raw, dict) else {}
    try:
        meta = int(raw.get("meta") or DEFAULT["meta"])
    except (TypeError, ValueError):
        meta = DEFAULT["meta"]
    try:
        pct = int(raw.get("descuentoPct") or DEFAULT["descuentoPct"])
    except (TypeError, ValueError):
        pct = DEFAULT["descuentoPct"]
    try:
        ventana = int(raw.get("ventanaDias") if raw.get("ventanaDias") is not None else DEFAULT["ventanaDias"])
    except (TypeError, ValueError):
        ventana = DEFAULT["ventanaDias"]
    premio = str(raw.get("premio") or DEFAULT["premio"])
    aplica = str(raw.get("aplica") or DEFAULT["aplica"])
    return {
        "activa": bool(raw.get("activa")),
        "meta": meta if meta in METAS else DEFAULT["meta"],
        "premio": premio if premio in PREMIOS else DEFAULT["premio"],
        "descuentoPct": pct if pct in DESCUENTOS else DEFAULT["descuentoPct"],
        "ventanaDias": ventana if ventana in VENTANAS else DEFAULT["ventanaDias"],
        "aplica": aplica if aplica in APLICA else DEFAULT["aplica"],
    }


def validar(raw: dict | None) -> tuple[str | None, dict]:
    """Para el editor del dueño: devuelve (error, config). Todo por selección."""
    raw = raw if isinstance(raw, dict) else {}
    cfg = normalizar(raw)
    if not cfg["activa"]:
        return None, cfg
    try:
        if int(raw.get("meta")) not in METAS:
            return "meta_invalida", cfg
    except (TypeError, ValueError):
        return "meta_invalida", cfg
    if str(raw.get("premio")) not in PREMIOS:
        return "premio_invalido", cfg
    if cfg["premio"] == "descuento":
        try:
            if int(raw.get("descuentoPct")) not in DESCUENTOS:
                return "descuento_invalido", cfg
        except (TypeError, ValueError):
            return "descuento_invalido", cfg
    return None, cfg


def config_de(c: dict | None) -> dict:
    return normalizar((c or {}).get("fidelidad"))


def activa_en(c: dict | None) -> bool:
    return bool(c) and config_de(c)["activa"]


def local_key(c: dict) -> str:
    dueno = (c.get("dueno") or "").strip().lower()
    club = (c.get("club") or "").strip().lower() or (c.get("nombre") or "").strip().lower()
    return f"{dueno}|{club}"


def canchas_del_local(c: dict) -> list[dict]:
    """Todas las canchas del mismo local (mismo dueño y mismo club), incluida
    la propia: la tarjeta es del LOCAL, no de una cancha."""
    key = local_key(c)
    out = [x for x in datos.canchas_publicas() if not x.get("eliminada") and local_key(x) == key]
    if not any(x["id"] == c["id"] for x in out):
        out.append(c)
    return out


def nombre_premio(cfg: dict, sim: str = "S/") -> str:
    if cfg["premio"] == "descuento":
        return f"{cfg['descuentoPct']} % de descuento"
    return "una hora gratis"


def texto_premio_corto(cfg: dict) -> str:
    return f"−{cfg['descuentoPct']} %" if cfg["premio"] == "descuento" else "Hora gratis"


# ── Conteo ────────────────────────────────────────────────────────────────────

def _ref(r: dict) -> str:
    g = (r.get("grupo_reserva_id") or "").strip()
    return g if g else str(r.get("id"))


def _vigente(canje: dict) -> bool:
    """Un canje cuenta como consumido si está usado, o reservado hace poco
    (hold vivo). Los devueltos y los holds vencidos no consumen nada."""
    est = canje.get("estado")
    if est == "usado":
        return True
    if est != "reservado":
        return False
    try:
        # Mientras el jugador paga en una pasarela hospedada (USD / BOB) el
        # premio sigue apartado aunque pasen los 15 min.
        from web import pago_hospedado
        if pago_hospedado.ref_pendiente(str(canje.get("reserva_ref") or ""), list(canje.get("reserva_ids") or [])):
            return True
    except Exception:  # noqa: BLE001
        pass
    try:
        cr = datetime.fromisoformat(str(canje.get("creado")))
        if cr.tzinfo is None:
            cr = cr.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - cr).total_seconds() <= HOLD_SEGUNDOS
    except (TypeError, ValueError):
        return True


def estado(email: str, c: dict) -> dict:
    """Progreso del jugador en la tarjeta de ESTE local + si tiene premio."""
    cfg = config_de(c)
    sim = paises.simbolo_de_moneda(paises.moneda_de_pais(paises.pais_de_coordenadas(c.get("lat"), c.get("lng")) or "PE"))
    base = {"activa": cfg["activa"], "meta": cfg["meta"], "premio": cfg["premio"], "descuentoPct": cfg["descuentoPct"],
            "ventanaDias": cfg["ventanaDias"], "aplica": cfg["aplica"], "conteo": 0, "faltan": cfg["meta"],
            "disponible": False, "refs": [], "nombrePremio": nombre_premio(cfg, sim), "premioCorto": texto_premio_corto(cfg),
            "local": (c.get("club") or "").strip() or c.get("nombre", ""), "usados": 0}
    email = (email or "").strip().lower()
    if not cfg["activa"] or not email:
        return base
    ids = [x["id"] for x in canchas_del_local(c)]
    reservas = datos.reservas_pagadas_en(email, ids)
    hoy = date.today()
    consumidas: set[str] = set()
    usados = 0
    for cj in datos.canjes_de(email, local_key(c)):
        if not _vigente(cj):
            continue
        usados += 1 if cj.get("estado") == "usado" else 0
        consumidas.update(str(x) for x in (cj.get("reservas_contadas") or []))
        consumidas.add(str(cj.get("reserva_ref") or ""))
    vistos: dict[str, str] = {}
    for r in reservas:
        ref = _ref(r)
        if ref in consumidas or ref in vistos:
            continue
        if cfg["aplica"] == "online" and str(r.get("medio_pago") or "").lower() not in MEDIOS_ONLINE:
            continue
        if cfg["ventanaDias"]:
            try:
                if (hoy - date.fromisoformat(str(r["fecha"])[:10])).days > cfg["ventanaDias"]:
                    continue
            except (TypeError, ValueError):
                pass
        vistos[ref] = str(r.get("fecha") or "")
    refs = sorted(vistos, key=lambda k: vistos[k])
    conteo = len(refs)
    base.update({"conteo": min(conteo, cfg["meta"]), "conteoTotal": conteo, "faltan": max(0, cfg["meta"] - conteo),
                 "disponible": conteo >= cfg["meta"], "refs": refs[:cfg["meta"]], "usados": usados})
    return base


# ── Descuento ─────────────────────────────────────────────────────────────────

def descuento_para(cfg: dict, precios: list[float]) -> tuple[int, list[int]]:
    """(descuento total, descuento por slot) en unidades enteras de la moneda.
    Hora gratis → el slot más barato a 0; descuento → % sobre cada slot
    (redondeo por slot, el total es la suma)."""
    if not precios:
        return 0, []
    if cfg["premio"] == "hora_gratis":
        i = min(range(len(precios)), key=lambda k: float(precios[k]))
        por = [0] * len(precios)
        por[i] = int(round(float(precios[i])))
        return por[i], por
    pct = int(cfg["descuentoPct"])
    por = [int(round(float(p) * pct / 100.0)) for p in precios]
    return sum(por), por


# ── Canjes ────────────────────────────────────────────────────────────────────

def reservar_canje(email: str, c: dict, *, reserva_ref: str, reserva_ids: list[str], descuento: float,
                   canal: str = "app", confirmar: bool = False) -> dict:
    """Aparta el premio para esa reserva (hold) o lo usa directo (`confirmar`).
    Idempotente por `reserva_ref`. Devuelve {ok, canje} o {ok: False, error}."""
    email = (email or "").strip().lower()
    if not email or not reserva_ref:
        return {"ok": False, "error": "datos_invalidos"}
    previo = datos.canje_por_ref(reserva_ref)
    if previo:
        if confirmar and previo.get("estado") == "reservado":
            datos.actualizar_canje(previo["id"], "usado", solo_si=("reservado",))
            previo["estado"] = "usado"
        return {"ok": True, "canje": previo, "repetido": True}
    est = estado(email, c)
    if not est["disponible"]:
        return {"ok": False, "error": "sin_premio", "estado": est}
    cfg = config_de(c)
    iso = paises.moneda_de_pais(paises.pais_de_coordenadas(c.get("lat"), c.get("lng")) or "PE")
    canje = {
        "id": f"fc_{int(time.time() * 1_000_000)}", "email": email, "local_key": local_key(c), "cancha_id": c["id"],
        "reserva_ref": reserva_ref, "reserva_ids": [str(x) for x in reserva_ids], "tipo": cfg["premio"],
        "descuento": round(float(descuento or 0), 2), "moneda": iso, "estado": "usado" if confirmar else "reservado",
        "reservas_contadas": list(est["refs"]), "canal": canal,
    }
    if not datos.insertar_canje(canje):
        return {"ok": False, "error": "no_guardado"}
    canje["creado"] = datetime.now(timezone.utc).isoformat()
    print(f"[fidelidad] {canje['estado']} {canje['id']} {email} local={canje['local_key']} ref={reserva_ref} "
          f"premio={cfg['premio']} desc={canje['descuento']} contadas={len(est['refs'])}", flush=True)
    return {"ok": True, "canje": canje}


def confirmar_canje(reserva_ref: str) -> bool:
    cj = datos.canje_por_ref(reserva_ref)
    if not cj:
        return False
    if cj.get("estado") == "usado":
        return True
    return datos.actualizar_canje(cj["id"], "usado", solo_si=("reservado",))


def revertir_canje(reserva_ref: str = "", ids: list[str] | None = None) -> bool:
    """Devuelve el premio (reserva cancelada / hold liberado / pago fallido)."""
    cj = datos.canje_por_ref(reserva_ref) if reserva_ref else None
    if not cj and ids:
        cj = datos.canje_por_ids(ids)
    if not cj:
        return False
    ok = datos.actualizar_canje(cj["id"], "devuelto")
    if ok:
        print(f"[fidelidad] devuelto {cj['id']} ref={cj.get('reserva_ref')}", flush=True)
    return ok


def publico_config(c: dict) -> dict:
    cfg = config_de(c)
    return {**cfg, "nombrePremio": nombre_premio(cfg), "premioCorto": texto_premio_corto(cfg)}


# ── Endpoints (APK) ────────────────────────────────────────────────────────────

@router.get("/estado", dependencies=_APP)
def get_estado(email: str, cancha_id: str) -> dict:
    c = datos.cancha(cancha_id)
    if not c:
        return {"ok": False, "error": "no_encontrada"}
    return {"ok": True, **estado(email, c)}


@router.get("/catalogo")
def get_catalogo() -> dict:
    """Opciones del editor del dueño (todo por selección)."""
    return {"ok": True, "metas": list(METAS), "premios": list(PREMIOS), "descuentos": list(DESCUENTOS),
            "ventanas": list(VENTANAS), "aplica": list(APLICA), "default": DEFAULT}


class CanjeReq(BaseModel):
    email: str
    cancha_id: str
    reserva_ref: str
    reserva_ids: list[str] = []
    descuento: float = 0
    confirmar: bool = False


@router.post("/canje/reservar", dependencies=_APP)
def post_reservar(req: CanjeReq) -> dict:
    c = datos.cancha(req.cancha_id)
    if not c:
        return {"ok": False, "error": "no_encontrada"}
    return reservar_canje(req.email, c, reserva_ref=req.reserva_ref, reserva_ids=req.reserva_ids,
                          descuento=req.descuento, canal="app", confirmar=req.confirmar)


class RefReq(BaseModel):
    reserva_ref: str = ""
    reserva_ids: list[str] = []


@router.post("/canje/confirmar", dependencies=_APP)
def post_confirmar(req: RefReq) -> dict:
    return {"ok": confirmar_canje(req.reserva_ref)}


@router.post("/canje/revertir", dependencies=_APP)
def post_revertir(req: RefReq) -> dict:
    return {"ok": revertir_canje(req.reserva_ref, req.reserva_ids)}
