"""RETOS P2P: un jugador reta a otro (por correo). Coordinan la cancha y reportan
el resultado; el resultado suma al ranking global (el APK lo pliega por correo).
Une reservas y circuito. Público (app del jugador), protegido por X-App-Key.
"""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

import config
from db.store import Reto, ahora, stores

router = APIRouter(prefix="/retos", tags=["retos"])

# Retos que un jugador SIN Pichangol Pro puede ENVIAR por semana (rolling 7 días).
# Pro = ilimitado. Es el perk funcional que justifica la membresía. Este es el
# valor por defecto; el efectivo se lee de la config (editable en la torre).
RETOS_FREE_LIMITE_SEMANA = 3


def _limite_free() -> int:
    n = stores.cfg_int("retos_free_limite_semana")
    return n if n > 0 else RETOS_FREE_LIMITE_SEMANA


def _require_app_key(x_app_key: str | None = Header(default=None)) -> None:
    if not config.APP_API_KEY:
        return
    if x_app_key != config.APP_API_KEY:
        raise HTTPException(status_code=401, detail="app_key_invalida")


_APP = [Depends(_require_app_key)]


def _dict(r: Reto) -> dict:
    return {
        "id": r.id,
        "retador_email": r.retador_email,
        "retador_nombre": r.retador_nombre,
        "retado_email": r.retado_email,
        "retado_nombre": r.retado_nombre,
        "deporte": r.deporte,
        "zona": r.zona,
        "estado": r.estado,
        "ganador_email": r.ganador_email,
        "marcador": r.marcador,
        "mensaje": r.mensaje,
        "creado_en": r.creado_en.isoformat(),
        "jugado_en": r.jugado_en.isoformat() if r.jugado_en else None,
        "reportado_por": r.reportado_por,
        "reportado_en": r.reportado_en.isoformat() if r.reportado_en else None,
        "auto_confirmado": r.auto_confirmado,
    }


def _confirmacion_horas() -> int:
    """Plazo (horas) para confirmar un resultado antes de auto-confirmarlo.
    Editable en la torre; negativo se trata como 0 (confirmación inmediata)."""
    n = stores.cfg_int("retos_confirmacion_horas")
    return max(0, n)


def _auto_confirmar() -> None:
    """Promueve a JUGADO (confirmado) los retos 'por_confirmar' cuyo plazo venció:
    si el otro jugador no confirmó ni disputó a tiempo, gana el reportado. Lazy:
    se llama al leer retos/resultados, así no hace falta un cron."""
    horas = _confirmacion_horas()
    limite = ahora() - timedelta(hours=horas)
    for r in stores.retos:
        if r.estado == "por_confirmar" and r.reportado_en and r.reportado_en <= limite:
            r.estado = "jugado"
            r.jugado_en = ahora()
            r.auto_confirmado = True


class CrearRetoReq(BaseModel):
    retador_email: str
    retador_nombre: str = ""
    retado_email: str
    retado_nombre: str = ""
    deporte: str = ""
    zona: str = ""
    mensaje: str = ""


@router.post("/crear", dependencies=_APP)
def crear_reto(req: CrearRetoReq) -> dict:
    """Crea un reto pendiente del retador al retado."""
    retador = req.retador_email.strip().lower()
    retado = req.retado_email.strip().lower()
    if not retador or not retado:
        return {"ok": False, "error": "correos_requeridos"}
    if retador == retado:
        return {"ok": False, "error": "no_puedes_retarte"}
    # Perk Pro: los no-Pro tienen tope semanal de retos enviados.
    if not stores.pro_activo(retador):
        limite = _limite_free()
        hace_semana = ahora() - timedelta(days=7)
        enviados = sum(1 for x in stores.retos
                       if x.retador_email == retador and x.creado_en >= hace_semana)
        if enviados >= limite:
            return {"ok": False, "error": "limite_retos_free", "limite": limite}
    r = Reto(
        id=stores.next_id("reto"),
        retador_email=retador, retador_nombre=req.retador_nombre.strip(),
        retado_email=retado, retado_nombre=req.retado_nombre.strip(),
        deporte=req.deporte.strip(), zona=req.zona.strip(),
        mensaje=req.mensaje.strip(), creado_en=ahora())
    stores.retos.append(r)
    return {"ok": True, "reto": _dict(r)}


@router.get("/{email}", dependencies=_APP)
def listar_retos(email: str) -> dict:
    """Retos donde el usuario es retador (enviados) o retado (recibidos), del más
    reciente al más antiguo."""
    _auto_confirmar()  # promueve los por_confirmar vencidos antes de listar
    e = email.strip().lower()
    mios = [r for r in stores.retos
            if r.retador_email == e or r.retado_email == e]
    mios.sort(key=lambda r: r.creado_en, reverse=True)
    return {
        "recibidos": [_dict(r) for r in mios if r.retado_email == e],
        "enviados": [_dict(r) for r in mios if r.retador_email == e],
    }


class ResponderReq(BaseModel):
    aceptar: bool


@router.post("/{reto_id}/responder", dependencies=_APP)
def responder_reto(reto_id: int, req: ResponderReq) -> dict:
    """El retado acepta o rechaza (solo si está pendiente)."""
    r = next((x for x in stores.retos if x.id == reto_id), None)
    if r is None:
        raise HTTPException(status_code=404, detail="reto_no_encontrado")
    if r.estado != "pendiente":
        return {"ok": True, "reto": _dict(r)}  # idempotente
    r.estado = "aceptado" if req.aceptar else "rechazado"
    return {"ok": True, "reto": _dict(r)}


class ResultadoReq(BaseModel):
    ganador_email: str
    marcador: str = ""
    reportado_por: str = ""  # quién reporta (para la doble confirmación)


@router.post("/{reto_id}/resultado", dependencies=_APP)
def resultado_reto(reto_id: int, req: ResultadoReq) -> dict:
    """Un jugador REPORTA el resultado (ganador = uno de los dos). Queda 'por
    confirmar': NO suma al ranking hasta que el OTRO confirme, o hasta que venza
    el plazo (auto-confirmación a favor del reportado). Con plazo 0, confirma al
    instante (sin doble confirmación)."""
    r = next((x for x in stores.retos if x.id == reto_id), None)
    if r is None:
        raise HTTPException(status_code=404, detail="reto_no_encontrado")
    g = req.ganador_email.strip().lower()
    if g not in (r.retador_email, r.retado_email):
        return {"ok": False, "error": "ganador_invalido"}
    r.ganador_email = g
    r.marcador = req.marcador.strip()
    r.reportado_por = (req.reportado_por.strip().lower()
                       or r.retador_email)
    r.reportado_en = ahora()
    r.auto_confirmado = False
    if _confirmacion_horas() <= 0:
        # Sin doble confirmación: cuenta de una.
        r.estado = "jugado"
        r.jugado_en = ahora()
    else:
        r.estado = "por_confirmar"
        r.jugado_en = None
    return {"ok": True, "reto": _dict(r)}


class ConfirmarReq(BaseModel):
    por_email: str          # quién confirma/disputa (debe ser el OTRO, no el que reportó)
    acepta: bool = True     # True = confirma (cuenta) | False = disputa (no cuenta)


@router.post("/{reto_id}/confirmar", dependencies=_APP)
def confirmar_reto(reto_id: int, req: ConfirmarReq) -> dict:
    """El OTRO jugador CONFIRMA o DISPUTA el resultado reportado. Solo puede
    hacerlo quien NO reportó. Confirmar → jugado (suma al ranking). Disputar →
    disputado (no suma; se puede re-reportar/escalar)."""
    r = next((x for x in stores.retos if x.id == reto_id), None)
    if r is None:
        raise HTTPException(status_code=404, detail="reto_no_encontrado")
    quien = req.por_email.strip().lower()
    if r.estado != "por_confirmar":
        return {"ok": True, "reto": _dict(r)}  # idempotente
    if quien not in (r.retador_email, r.retado_email):
        return {"ok": False, "error": "no_participa"}
    if quien == r.reportado_por:
        return {"ok": False, "error": "reportador_no_confirma"}
    if req.acepta:
        r.estado = "jugado"
        r.jugado_en = ahora()
    else:
        r.estado = "disputado"
        r.jugado_en = None
    return {"ok": True, "reto": _dict(r)}


@router.get("", dependencies=_APP)
def resultados_para_ranking(deporte: str | None = None,
                            zona: str | None = None) -> dict:
    """Retos JUGADOS (confirmados), para que el APK los sume al ranking global.
    Filtra por deporte/zona si se indica."""
    _auto_confirmar()  # promueve los por_confirmar vencidos antes de listar
    out = []
    for r in stores.retos:
        if r.estado != "jugado" or not r.ganador_email:
            continue
        if deporte and r.deporte != deporte:
            continue
        if zona and r.zona != zona:
            continue
        out.append(_dict(r))
    return {"resultados": out}
