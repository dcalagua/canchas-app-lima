"""Lógica de 'pide tu cancha': crea solicitudes, acredita puntos (con tope por
usuario/mes), agrupa solicitudes cercanas (misma cancha pedida por varios) para
medir demanda y rankea por zona (esto prioriza a los verificadores).
"""

from __future__ import annotations

import re
import unicodedata

from config import zona_de_distrito
from db.store import SolicitudCancha, ahora, como_dict, mes_de, stores
from puntos import service as puntos


def _norm(texto: str) -> str:
    s = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s.lower()).strip()


def _clave_grupo(s: SolicitudCancha) -> str:
    """Agrupa por nombre normalizado + coordenada redondeada (~100 m) si la hay."""
    base = _norm(s.nombre_cancha_libre)
    if s.lat is not None and s.lng is not None:
        return f"{base}@{round(s.lat, 3)},{round(s.lng, 3)}"
    return f"{base}@{_norm(s.distrito)}"


def crear(usuario_id: str, nombre_cancha_libre: str, direccion_texto: str,
          distrito: str | None = None, zona: str | None = None,
          lat: float | None = None, lng: float | None = None,
          idem_key: str | None = None) -> dict:
    cacheado = stores.idem_get("solicitud", idem_key)
    if cacheado is not None:
        return cacheado

    zona = zona if zona in (
        "lima_norte", "lima_sur", "lima_este", "lima_moderna", "callao"
    ) else zona_de_distrito(distrito)

    sol = SolicitudCancha(
        id=stores.next_id("solicitud"), usuario_id=usuario_id,
        nombre_cancha_libre=nombre_cancha_libre, direccion_texto=direccion_texto,
        lat=lat, lng=lng, distrito=distrito or "", zona=zona,
        estado="solicitada", cancha_id=None, creado_en=ahora())
    stores.solicitudes.append(sol)

    # Acredita puntos por pedir cancha SOLO hasta el tope por usuario/mes.
    tope = stores.cfg_int("tope_solicitudes_usuario_mes")
    usadas = puntos.cuenta_solicitudes_mes(usuario_id, mes_de(ahora()))
    punto_mov = None
    if usadas < tope:
        punto_mov = puntos.acreditar(
            usuario_id, "pedir_cancha", ref_tipo="solicitud", ref_id=str(sol.id))

    # Cuántas solicitudes hay ya en el mismo grupo (demanda).
    grupo = _clave_grupo(sol)
    en_grupo = sum(1 for x in stores.solicitudes if _clave_grupo(x) == grupo)

    resp = {
        "solicitud": como_dict(sol),
        "puntos_acreditados": (punto_mov is not None),
        "puntos_pendientes": punto_mov["puntos"] if punto_mov else 0,
        "tope_alcanzado": usadas >= tope,
        "demanda_en_grupo": en_grupo,
    }
    return stores.idem_set("solicitud", idem_key, resp)


def ranking(zona: str | None = None) -> list[dict]:
    """Ranking de canchas más pedidas (agrupadas), opcionalmente por zona.
    Prioriza a los verificadores: lo más pedido sale primero."""
    grupos: dict[str, dict] = {}
    for s in stores.solicitudes:
        if zona and s.zona != zona:
            continue
        if s.estado == "descartada":
            continue
        clave = _clave_grupo(s)
        g = grupos.setdefault(clave, {
            "clave": clave, "nombre_cancha": s.nombre_cancha_libre,
            "zona": s.zona, "distrito": s.distrito, "lat": s.lat, "lng": s.lng,
            "solicitudes": 0, "solicitud_ids": [], "estado": s.estado,
            "cancha_id": s.cancha_id})
        g["solicitudes"] += 1
        g["solicitud_ids"].append(s.id)
    return sorted(grupos.values(), key=lambda g: g["solicitudes"], reverse=True)


def _grupo_de_cancha(cancha_id: str) -> str | None:
    for s in stores.solicitudes:
        if s.cancha_id == cancha_id:
            return _clave_grupo(s)
    return None


def demanda_de_cancha(cancha_id: str) -> int:
    """# de solicitudes del grupo asociado a una cancha (para priorizar visitas)."""
    clave = _grupo_de_cancha(cancha_id)
    if not clave:
        return 0
    return sum(1 for s in stores.solicitudes if _clave_grupo(s) == clave)


def marcar_registrada(solicitud_id: int, cancha_id: str) -> dict:
    for s in stores.solicitudes:
        if s.id == solicitud_id:
            s.estado = "registrada"
            s.cancha_id = cancha_id
            return como_dict(s)
    return {"error": "solicitud no encontrada"}


def on_cancha_verificada(cancha_id: str) -> int:
    """Cuando la cancha (que vino de una solicitud) queda verificada, libera el
    premio del usuario que la pidió/trajo. Devuelve cuántos movimientos liberó."""
    liberados = 0
    for s in stores.solicitudes:
        if s.cancha_id == cancha_id:
            if s.estado != "registrada":
                s.estado = "registrada"
            liberados += puntos.liberar_por_ref(
                "solicitud", str(s.id), accion="pedir_cancha")
    return liberados
