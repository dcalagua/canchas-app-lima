"""Verificación física (carril informal).

Regla rectora: IA PRIMERO, visita solo si hace falta.
  1. Corre la verificación remota por IA (reusa módulo de existencia). Si el
     score supera el umbral → cancha verificada SIN visita (estado no_requerida).
  2. Si la IA no concluye → crea verificación física 'agendada' y la asigna por
     zona, priorizando las canchas más pedidas (cruce con solicitudes).
  3. La app del verificador captura fotos GEO del sitio, confirma coincidencia
     con la ubicación declarada y firma.
  4. Al confirmar → cancha verificada por carril físico (metodo='en_sitio'). La
     insignia pública es ÚNICA ('cancha verificada'); 'en persona' es un PLUS.
  5. Visita por_encargo → se registra para liquidación (STUB, sin pago real).
"""

from __future__ import annotations

import math

from config import COINCIDENCIA_MAX_M, zona_de_distrito
from db.store import VerificacionFisica, ahora, como_dict, stores
from puntos import service as puntos
from solicitudes import service as solicitudes


def _haversine_m(a_lat, a_lng, b_lat, b_lng) -> float:
    r = 6371000.0
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dphi = math.radians(b_lat - a_lat)
    dl = math.radians(b_lng - a_lng)
    h = (math.sin(dphi / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2)
    return round(2 * r * math.asin(min(1.0, math.sqrt(h))), 1)


def _marcar_cancha_verificada(cancha_id: str, metodo: str,
                              en_persona: bool) -> dict:
    """Verifica la cancha (insignia única) y dispara liberaciones de puntos."""
    c = stores.cancha(cancha_id)
    c.verificada = True
    c.metodo_verificacion = metodo
    if en_persona:
        c.verificada_en_persona = True  # PLUS; nunca se baja de categoría
    # Disparos conectados:
    pedir = solicitudes.on_cancha_verificada(cancha_id)
    traer = puntos.intentar_liberar_traer_cancha(cancha_id)
    return {"pedir_cancha_liberados": pedir, "traer_cancha_liberados": traer}


def _zona_de(req_zona: str | None, distrito: str | None,
             solicitud_id: int | None) -> str:
    if req_zona:
        return req_zona
    if solicitud_id is not None:
        for s in stores.solicitudes:
            if s.id == solicitud_id:
                return s.zona
    return zona_de_distrito(distrito)


def _asignar_verificador(zona: str) -> int | None:
    for v in stores.verificadores:
        if v.activo and v.zona == zona:
            return v.id
    return None


def evaluar(cancha_id: str, direccion: str, ruc: str | None,
            lat: float | None, lng: float | None, zona: str | None,
            distrito: str | None, solicitud_id: int | None,
            motivo: str) -> dict:
    # Guarda la ubicación declarada (para validar coincidencia en la visita).
    c = stores.cancha(cancha_id)
    if lat is not None and lng is not None:
        c.lat_declarada, c.lng_declarada = lat, lng
    zona_final = _zona_de(zona, distrito, solicitud_id)
    c.zona = zona_final

    # 1) IA primero.
    from verificacion_fisica import existencia_client
    res = existencia_client.verificar(cancha_id, direccion, ruc, lat, lng)
    score = res["score"]
    umbral = stores.cfg_int("umbral_ia_verificacion")

    if score >= umbral:
        disparos = _marcar_cancha_verificada(cancha_id, "documental", False)
        vf = VerificacionFisica(
            id=stores.next_id("vf"), cancha_id=cancha_id,
            solicitud_id=solicitud_id, motivo=motivo, verificador_id=None,
            estado="no_requerida", fotos_geo_urls=[], lat_sitio=None,
            lng_sitio=None, firma_verificador=None,
            observaciones=f"IA score={score} (>= umbral {umbral})",
            metodo="documental", creado_en=ahora(), cerrada_en=ahora())
        stores.verificaciones_fisicas.append(vf)
        return {"verificada": True, "via": "ia", "score": score,
                "verificacion_fisica": como_dict(vf), **disparos}

    # 2) IA no concluye → agenda visita, asigna por zona.
    verificador_id = _asignar_verificador(zona_final)
    vf = VerificacionFisica(
        id=stores.next_id("vf"), cancha_id=cancha_id, solicitud_id=solicitud_id,
        motivo="ia_no_concluyente" if motivo == "sin_documentos" else motivo,
        verificador_id=verificador_id, estado="agendada", fotos_geo_urls=[],
        lat_sitio=None, lng_sitio=None, firma_verificador=None,
        observaciones=f"IA score={score} (< umbral {umbral})", metodo=None,
        creado_en=ahora())
    stores.verificaciones_fisicas.append(vf)
    return {"verificada": False, "via": "fisica", "score": score,
            "zona": zona_final, "verificador_id": verificador_id,
            "demanda": solicitudes.demanda_de_cancha(cancha_id),
            "verificacion_fisica": como_dict(vf)}


def visitas(zona: str | None = None,
            verificador_id: int | None = None) -> list[dict]:
    """Lista de visitas pendientes (agendada/en_sitio) ORDENADAS por prioridad:
    las canchas más pedidas (mayor demanda) salen primero."""
    items = []
    for vf in stores.verificaciones_fisicas:
        if vf.estado not in ("agendada", "en_sitio"):
            continue
        c = stores.cancha(vf.cancha_id)
        if zona and c.zona != zona:
            continue
        if verificador_id is not None and vf.verificador_id != verificador_id:
            continue
        d = como_dict(vf)
        d["zona"] = c.zona
        d["demanda"] = solicitudes.demanda_de_cancha(vf.cancha_id)
        items.append(d)
    items.sort(key=lambda x: x["demanda"], reverse=True)
    return items


def captura(vf_id: int, fotos_geo_urls: list[str], lat_sitio: float,
            lng_sitio: float, firma_verificador: str,
            observaciones: str | None) -> dict:
    vf = next((v for v in stores.verificaciones_fisicas if v.id == vf_id), None)
    if vf is None:
        return {"ok": False, "error": "verificación no encontrada"}
    if vf.estado not in ("agendada", "en_sitio"):
        return {"ok": False, "error": f"estado inválido: {vf.estado}"}

    vf.fotos_geo_urls = list(fotos_geo_urls)   # fotos del SITIO (no personales)
    vf.lat_sitio, vf.lng_sitio = lat_sitio, lng_sitio
    vf.firma_verificador = firma_verificador
    vf.observaciones = observaciones
    vf.cerrada_en = ahora()

    # Coincidencia con la ubicación declarada.
    c = stores.cancha(vf.cancha_id)
    coincide, distancia = True, None
    if c.lat_declarada is not None and c.lng_declarada is not None:
        distancia = _haversine_m(c.lat_declarada, c.lng_declarada,
                                 lat_sitio, lng_sitio)
        coincide = distancia <= COINCIDENCIA_MAX_M

    if not coincide:
        vf.estado = "rechazada"
        vf.metodo = None
        return {"ok": False, "estado": "rechazada", "coincide": False,
                "distancia_m": distancia,
                "verificacion_fisica": como_dict(vf)}

    vf.estado = "confirmada"
    vf.metodo = "en_sitio"
    disparos = _marcar_cancha_verificada(vf.cancha_id, "en_sitio", True)

    # Liquidación al verificador por_encargo (STUB, sin pago real).
    v = next((x for x in stores.verificadores if x.id == vf.verificador_id), None)
    if v and v.tipo == "por_encargo":
        stores.visitas_liquidacion.append({
            "vf_id": vf.id, "verificador_id": v.id, "cancha_id": vf.cancha_id,
            "fecha": ahora().isoformat(), "estado": "por_liquidar"})

    return {"ok": True, "estado": "confirmada", "coincide": True,
            "distancia_m": distancia,
            "insignia": "cancha verificada", "verificada_en_persona": True,
            "verificacion_fisica": como_dict(vf), **disparos}
