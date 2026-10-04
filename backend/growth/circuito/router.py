"""CIRCUITO: onboarding de jugadores al ranking. Un jugador se declara
"disponible para retar" (deporte + zona + categoría) y aparece en el directorio
aunque todavía no haya jugado. Resuelve el arranque en frío del ranking: sin
esto, para que te reten tienes que haber jugado, y para jugar necesitas a quién
retar. Público (app del jugador), protegido por X-App-Key.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

import config
from db.store import ahora, stores

router = APIRouter(prefix="/circuito", tags=["circuito"])


def _require_app_key(x_app_key: str | None = Header(default=None)) -> None:
    if not config.APP_API_KEY:
        return
    if x_app_key != config.APP_API_KEY:
        raise HTTPException(status_code=401, detail="app_key_invalida")


_APP = [Depends(_require_app_key)]


class UnirseReq(BaseModel):
    email: str
    nombre: str = ""
    deporte: str = ""
    zona: str = ""
    categoria: str = ""


def _perfil(email: str) -> dict | None:
    d = stores.jugadores_circuito.get(email.strip().lower())
    if not d:
        return None
    return {"email": email.strip().lower(), **d}


@router.post("/unirse", dependencies=_APP)
def unirse(req: UnirseReq) -> dict:
    """El jugador se declara disponible para retar (crea/actualiza su perfil)."""
    email = req.email.strip().lower()
    if not email:
        return {"ok": False, "error": "correo_requerido"}
    # Categoría OBLIGATORIA (regla del director): la liga ordena y reta por
    # nivel (5P, 5A, 5B, 4ta…). Sin categoría no se entra al directorio.
    if not req.categoria.strip():
        return {"ok": False, "error": "categoria_requerida"}
    stores.jugadores_circuito[email] = {
        "nombre": req.nombre.strip(),
        "deporte": req.deporte.strip(),
        "zona": req.zona.strip(),
        "categoria": req.categoria.strip(),
        "actualizado": ahora().isoformat(),
    }
    return {"ok": True, "jugador": _perfil(email)}


@router.post("/salir", dependencies=_APP)
def salir(req: UnirseReq) -> dict:
    """El jugador se retira del directorio de disponibles."""
    email = req.email.strip().lower()
    estaba = stores.jugadores_circuito.pop(email, None) is not None
    return {"ok": True, "estaba": estaba}


@router.get("/perfil/{email}", dependencies=_APP)
def perfil(email: str) -> dict:
    """Perfil de circuito del jugador (para saber si ya se unió)."""
    return {"jugador": _perfil(email)}


class RankingSnapshotReq(BaseModel):
    # deportes: [{deporte, temporada, top:[{nombre,puntos,pg,pp,academia,pro}],
    #            campeon:{nombre,puntos}|null}]
    deportes: list[dict] = []
    por: str = ""  # correo de quien lo envió (informativo)


@router.post("/ranking-snapshot", dependencies=_APP)
def ranking_snapshot(req: RankingSnapshotReq) -> dict:
    """El APK EMPUJA el ranking global cruzado (que computa con las academias de
    Supabase) para que la torre lo pueda mostrar. Guarda el último snapshot."""
    stores.ranking_snapshot = {
        "deportes": req.deportes,
        "por": req.por.strip().lower(),
        "actualizado": ahora().isoformat(),
    }
    return {"ok": True, "deportes": len(req.deportes)}


@router.get("/jugadores", dependencies=_APP)
def jugadores(deporte: str | None = None, zona: str | None = None) -> dict:
    """Directorio de jugadores disponibles para retar. Filtra por deporte/zona.
    Más recientes primero.

    Incluye DOS fuentes, unidas por correo:
      1) quienes se declararon disponibles (`/circuito/unirse`), y
      2) quienes YA JUGARON un reto (aparecen en el ranking) — así cualquiera
         que compite es retable de nuevo aunque no haya tocado "Unirme". El
         perfil explícito tiene prioridad (conserva su zona/categoría)."""
    por_email: dict[str, dict] = {}
    # 1) Directorio explícito.
    for email, d in stores.jugadores_circuito.items():
        por_email[email] = {"email": email, **d}
    # 2) Participantes de retos (retador/retado + parejas en dobles).
    for r in stores.retos:
        for em, nm in (
            (r.retador_email, r.retador_nombre),
            (r.retado_email, r.retado_nombre),
            (r.retador2_email, r.retador2_nombre),
            (r.retado2_email, r.retado2_nombre),
        ):
            e = (em or "").strip().lower()
            if not e or e in por_email:
                continue
            por_email[e] = {
                "email": e,
                "nombre": (nm or "").strip(),
                "deporte": r.deporte,
                "zona": "",
                "categoria": "",
                "actualizado": r.creado_en.isoformat(),
            }
    out = []
    for d in por_email.values():
        if deporte and d.get("deporte", "") != deporte:
            continue
        if zona and d.get("zona", "") != zona:
            continue
        out.append(d)
    out.sort(key=lambda j: j.get("actualizado", ""), reverse=True)
    return {"jugadores": out}
