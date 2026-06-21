"""Orquestación de la verificación de existencia.

Flujo:
  1. Consulta adaptadores (SUNAT, Places, Social) — todos STUB por ahora.
  2. Deriva señales [0..1] por factor (sin datos personales).
  3. Calcula el score EXPLICABLE (scoring.py).
  4. Persiste SOLO el resultado (bool + score + fecha + evidencias no personales).
  5. Devuelve la respuesta (sin datos personales).
"""

from __future__ import annotations

from adapters.address_normalizer import similitud
from adapters.places_adapter import PlacesResultado, get_places_adapter
from adapters.social_adapter import SocialResultado, get_social_adapter
from adapters.sunat_adapter import SunatResultado, get_sunat_adapter
from compliance import access_log
from db.repository import (ResultadoVerificacion, ahora_utc,
                           verificaciones_repo)
from models import (Evidencia, ExistenciaRequest, ExistenciaResponse, MapsInfo,
                    SunatInfo)
from scoring import Senales, calcular_score

# Distancia (m) a partir de la cual la cercanía vale 0; <=150 m vale 1.0.
_DIST_MIN, _DIST_MAX = 150.0, 2000.0


def _senal_sunat_activo(s: SunatResultado) -> float | None:
    if not s.consultado:
        return None
    if not s.existe:
        return 0.0
    activo = (s.estado or "").upper().startswith("ACTIVO")
    habido = (s.condicion or "").upper() == "HABIDO"
    if activo and habido:
        return 1.0
    if activo and not habido:
        return 0.5
    return 0.0  # BAJA / SUSPENSION → penaliza


def _senal_distancia(dist_m: float | None) -> float | None:
    if dist_m is None:
        return None
    if dist_m <= _DIST_MIN:
        return 1.0
    if dist_m >= _DIST_MAX:
        return 0.0
    return round(1.0 - (dist_m - _DIST_MIN) / (_DIST_MAX - _DIST_MIN), 4)


def _senal_maps(p: PlacesResultado) -> float | None:
    if not p.consultado or not p.encontrado:
        return None
    return 1.0 if p.operativo else 0.3


def _senal_social(s: SocialResultado) -> float | None:
    if not s.consultado or not s.encontrado:
        return None
    return s.actividad_score


def verificar_existencia(req: ExistenciaRequest) -> ExistenciaResponse:
    access_log.log_acceso(
        rol="sistema_verificacion", recurso="/verificacion/existencia",
        accion="procesar", sujeto_id=req.cancha_id)

    # 1) Adaptadores (STUB). El RUC es opcional: si no hay, SUNAT no se consulta.
    sunat = (get_sunat_adapter().consultar_ruc(req.ruc)
             if req.ruc else SunatResultado.no_consultado())
    places = get_places_adapter().buscar(req.direccion, req.lat, req.lng)
    social = get_social_adapter().consultar(req.razon_social, req.direccion)

    # 2) Señales [0..1] (sin exponer ni guardar el texto de domicilios).
    domicilio_sim = (similitud(req.direccion, sunat.domicilio_fiscal)
                     if sunat.domicilio_fiscal else None)
    senales = Senales(
        sunat_activo=_senal_sunat_activo(sunat),
        sunat_domicilio=domicilio_sim,
        maps_operativo=_senal_maps(places),
        maps_distancia=_senal_distancia(places.distancia_m),
        social=_senal_social(social),
    )

    # 3) Score explicable.
    resultado = calcular_score(senales)

    # 4) Persistir SOLO el resultado (sin datos personales).
    evidencias = [
        {"factor": a.factor, "peso": a.peso, "valor": a.valor,
         "aporte": a.aporte, "disponible": a.disponible}
        for a in resultado.desglose
    ]
    fecha = ahora_utc()
    verificaciones_repo.guardar(ResultadoVerificacion(
        cancha_id=req.cancha_id, score_existencia=resultado.score,
        aprobado=resultado.aprobado, nivel=resultado.nivel, fecha=fecha,
        evidencias=evidencias, fuente_sunat=sunat.fuente))

    # 5) Respuesta (sin datos personales).
    return ExistenciaResponse(
        cancha_id=req.cancha_id,
        score_existencia=resultado.score,
        nivel=resultado.nivel,
        aprobado=resultado.aprobado,
        justificacion=resultado.justificacion,
        sunat=SunatInfo(
            consultado=sunat.consultado, existe=sunat.existe,
            estado=sunat.estado, condicion=sunat.condicion,
            domicilio_coincide=domicilio_sim,
            establecimientos_anexos=len(sunat.establecimientos_anexos),
            fuente=sunat.fuente),
        maps=MapsInfo(
            consultado=places.consultado, encontrado=places.encontrado,
            operativo=places.operativo, distancia_m=places.distancia_m,
            fuente=places.fuente),
        social={
            "consultado": social.consultado, "encontrado": social.encontrado,
            "antiguedad_meses": social.antiguedad_meses,
            "resenas": social.resenas, "rating": social.rating,
            "fuente": social.fuente},
        evidencias=[Evidencia(**e | {"detalle": d.detalle})
                    for e, d in zip(evidencias, resultado.desglose)],
        fecha=fecha.isoformat(),
        sin_datos_personales=True,
    )
