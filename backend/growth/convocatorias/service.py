"""Lógica de CONVOCATORIAS ("pichangas" programadas).

Resuelve el dolor del chat de WhatsApp de los jueves de un club: en vez de que
14 personas se anoten a mano y el resto quede fuera sin trazabilidad, aquí hay
cupos, lista de espera automática y 3 modos de asignación que el admin del club
elige por convocatoria (o deja el default global, configurable en caliente):

- ``orden_llegada``: el que se anota primero entra; feedback inmediato.
- ``sorteo``: ventana de inscripción; al cerrar se sortea de forma reproducible.
- ``equidad``: al cerrar prioriza a quien más veces quedó fuera y mejor asiste,
  y penaliza a quien ya jugó las últimas fechas o no se presentó (no-show).

Además expone un ranking de recurrencia por socio (la trazabilidad pedida).
Todo vive en `stores` (en memoria + snapshot a Postgres), igual que el resto del
backend growth.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from db.store import (
    MODOS_ASIGNACION,
    Convocatoria,
    Inscripcion,
    ahora,
    como_dict,
    stores,
)


# --- utilidades ------------------------------------------------------------
def _parse_dt(valor) -> datetime | None:
    """Acepta datetime o texto ISO. Normaliza a UTC si viene sin zona (para poder
    compararlo con `ahora()`, que es tz-aware)."""
    if not valor:
        return None
    dt = valor if isinstance(valor, datetime) else datetime.fromisoformat(valor)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _get(conv_id: int) -> Convocatoria | None:
    for c in stores.convocatorias:
        if c.id == conv_id:
            return c
    return None


def _inscripciones(conv_id: int) -> list[Inscripcion]:
    """Inscripciones ACTIVAS (no canceladas) de una convocatoria."""
    return [
        i for i in stores.inscripciones
        if i.convocatoria_id == conv_id and i.estado != "cancelado"
    ]


def modo_efectivo(conv: Convocatoria) -> str:
    return stores.modo_asignacion(conv.modo_asignacion)


def _abierta(conv: Convocatoria) -> bool:
    """¿Se puede inscribir AHORA? (abierta + dentro de la ventana de tiempo)."""
    if conv.estado != "abierta":
        return False
    now = ahora()
    if conv.apertura and now < conv.apertura:
        return False
    if conv.cierre and now > conv.cierre:
        return False
    return True


# --- asignación (los 3 modos) ---------------------------------------------
def _hash(semilla: str, socio_id: str) -> str:
    return hashlib.sha256(f"{semilla}:{socio_id}".encode()).hexdigest()


def _puntaje_equidad(conv: Convocatoria, socio_id: str) -> int:
    """Puntaje de equidad de un socio (mayor = más prioridad). Mira las
    convocatorias CERRADAS del mismo club: suma por cada vez que quedó en lista
    de espera; resta si jugó (confirmado) en las últimas `ventana` fechas y por
    cada no-show. Pesos configurables por el admin."""
    peso_espera = stores.cfg_int("convocatoria_equidad_peso_espera")
    peso_jugo = stores.cfg_int("convocatoria_equidad_peso_jugo")
    peso_noshow = stores.cfg_int("convocatoria_equidad_peso_noshow")
    ventana = stores.cfg_int("convocatoria_equidad_ventana") or 4

    historicas = sorted(
        [c for c in stores.convocatorias
         if c.club_id == conv.club_id and c.id != conv.id and c.estado == "cerrada"],
        key=lambda c: c.cerrado_en or c.creado_en, reverse=True)

    veces_fuera = jugo_reciente = no_shows = 0
    for idx, c in enumerate(historicas):
        ins = next((i for i in _inscripciones(c.id) if i.socio_id == socio_id), None)
        if not ins:
            continue
        if ins.estado == "lista_espera":
            veces_fuera += 1
        if ins.estado == "confirmado" and idx < ventana:
            jugo_reciente += 1
        if ins.asistio is False:
            no_shows += 1
    return (veces_fuera * peso_espera
            - jugo_reciente * peso_jugo
            - no_shows * peso_noshow)


def _ordenar(conv: Convocatoria, inscripciones: list[Inscripcion],
             modo: str) -> list[Inscripcion]:
    """Ordena las inscripciones por prioridad (mejor primero) según el modo."""
    if modo == "sorteo":
        semilla = conv.semilla or str(conv.id)
        return sorted(inscripciones, key=lambda i: _hash(semilla, i.socio_id))
    if modo == "equidad":
        # Mayor puntaje primero; empate → el que se anotó antes.
        return sorted(
            inscripciones,
            key=lambda i: (-_puntaje_equidad(conv, i.socio_id), i.creado_en))
    # orden_llegada (default): por marca de inscripción.
    return sorted(inscripciones, key=lambda i: i.creado_en)


def _resolver(conv: Convocatoria) -> tuple[list[Inscripcion], list[Inscripcion]]:
    """Devuelve (confirmados, lista_espera) ordenados para mostrar.

    - Cerrada: refleja la asignación congelada (por `posicion`), auto-promoviendo
      si alguien canceló después.
    - Abierta + orden_llegada: confirma en vivo por orden de llegada.
    - Abierta + sorteo/equidad: nadie confirmado aún (todos "en la bolsa"); se
      resuelve al cerrar. Se listan como espera provisional por orden de llegada.
    """
    activas = _inscripciones(conv.id)
    if conv.estado == "cerrada":
        ordenadas = sorted(
            activas, key=lambda i: (i.posicion if i.posicion is not None else 10**9,
                                    i.creado_en))
        return ordenadas[:conv.cupos], ordenadas[conv.cupos:]

    modo = modo_efectivo(conv)
    if modo == "orden_llegada":
        ordenadas = _ordenar(conv, activas, modo)
        return ordenadas[:conv.cupos], ordenadas[conv.cupos:]

    # sorteo / equidad en vivo: sin confirmar hasta el cierre.
    return [], sorted(activas, key=lambda i: i.creado_en)


def _estado_socio(conv: Convocatoria, socio_id: str) -> dict:
    """Estado efectivo de un socio en una convocatoria, para la ficha del jugador."""
    ins = next((i for i in _inscripciones(conv.id) if i.socio_id == socio_id), None)
    if not ins:
        return {"estado_efectivo": "sin_inscripcion", "posicion": None,
                "cupos": conv.cupos}
    if conv.estado == "abierta" and modo_efectivo(conv) in ("sorteo", "equidad"):
        return {"estado_efectivo": "en_bolsa", "posicion": None,
                "cupos": conv.cupos, "inscritos": len(_inscripciones(conv.id))}
    conf, espera = _resolver(conv)
    for pos, i in enumerate(conf, start=1):
        if i.socio_id == socio_id:
            return {"estado_efectivo": "confirmado", "posicion": pos,
                    "cupos": conv.cupos}
    for pos, i in enumerate(espera, start=1):
        if i.socio_id == socio_id:
            return {"estado_efectivo": "lista_espera", "posicion": pos,
                    "cupos": conv.cupos}
    return {"estado_efectivo": "sin_inscripcion", "posicion": None,
            "cupos": conv.cupos}


def estado_socio(conv_id: int, socio_id: str) -> dict:
    conv = _get(conv_id)
    if not conv:
        return {"estado_efectivo": "sin_inscripcion", "posicion": None}
    return _estado_socio(conv, socio_id)


# --- API del servicio ------------------------------------------------------
def crear(club_id: str, titulo: str, deporte: str, cupos: int, *,
          categoria: str | None = None, fecha_partido: str | None = None,
          apertura: str | None = None, cierre: str | None = None,
          modo_asignacion: str | None = None, creado_por: str = "",
          idem_key: str | None = None) -> dict:
    cacheado = stores.idem_get("convocatoria", idem_key)
    if cacheado is not None:
        return cacheado
    modo = modo_asignacion if modo_asignacion in MODOS_ASIGNACION else None
    conv = Convocatoria(
        id=stores.next_id("convocatoria"), club_id=club_id, titulo=titulo,
        deporte=deporte, cupos=max(0, int(cupos)), estado="abierta",
        creado_en=ahora(), categoria=categoria, fecha_partido=fecha_partido,
        apertura=_parse_dt(apertura) or ahora(), cierre=_parse_dt(cierre),
        modo_asignacion=modo, creado_por=creado_por)
    stores.convocatorias.append(conv)
    return stores.idem_set("convocatoria", idem_key, detalle(conv.id))


def inscribir(conv_id: int, socio_id: str, socio_nombre: str = "",
              idem_key: str | None = None) -> dict:
    cacheado = stores.idem_get("inscripcion", idem_key)
    if cacheado is not None:
        return cacheado
    conv = _get(conv_id)
    if not conv:
        return {"ok": False, "error": "convocatoria_no_encontrada"}
    if conv.estado == "cerrada":
        return {"ok": False, "error": "convocatoria_cerrada"}
    now = ahora()
    if conv.apertura and now < conv.apertura:
        return {"ok": False, "error": "aun_no_abre",
                "abre_en": conv.apertura.isoformat()}
    if conv.cierre and now > conv.cierre:
        return {"ok": False, "error": "inscripcion_cerrada"}

    activa = next((i for i in _inscripciones(conv_id) if i.socio_id == socio_id),
                  None)
    if activa:
        return {"ok": True, "ya_inscrito": True, "inscripcion": como_dict(activa),
                **_estado_socio(conv, socio_id)}

    # Reutiliza una inscripción cancelada del mismo socio (vuelve al final).
    cancelada = next(
        (i for i in stores.inscripciones
         if i.convocatoria_id == conv_id and i.socio_id == socio_id
         and i.estado == "cancelado"), None)
    if cancelada:
        cancelada.estado = "pendiente"
        cancelada.creado_en = now
        cancelada.posicion = None
        cancelada.asistio = None
        insc = cancelada
    else:
        insc = Inscripcion(
            id=stores.next_id("inscripcion"), convocatoria_id=conv_id,
            socio_id=socio_id, socio_nombre=socio_nombre or socio_id,
            estado="pendiente", creado_en=now)
        stores.inscripciones.append(insc)

    resp = {"ok": True, "inscripcion": como_dict(insc),
            **_estado_socio(conv, socio_id)}
    return stores.idem_set("inscripcion", idem_key, resp)


def cancelar(conv_id: int, socio_id: str) -> dict:
    conv = _get(conv_id)
    if not conv:
        return {"ok": False, "error": "convocatoria_no_encontrada"}
    ins = next((i for i in _inscripciones(conv_id) if i.socio_id == socio_id), None)
    if not ins:
        return {"ok": False, "error": "no_inscrito"}
    ins.estado = "cancelado"
    ins.posicion = None
    # Si ya estaba cerrada, resincroniza estados: promueve al primero de la espera.
    if conv.estado == "cerrada":
        _sync_estados(conv)
    return {"ok": True, "cancelado": True, **detalle(conv_id)}


def _sync_estados(conv: Convocatoria) -> None:
    """Recalcula confirmado/lista_espera de las inscripciones activas por su
    `posicion` congelada (para auto-promover tras una cancelación)."""
    activas = sorted(
        _inscripciones(conv.id),
        key=lambda i: (i.posicion if i.posicion is not None else 10**9, i.creado_en))
    for idx, i in enumerate(activas):
        i.estado = "confirmado" if idx < conv.cupos else "lista_espera"


def cerrar(conv_id: int, semilla: str | None = None) -> dict:
    """Cierra la inscripción y resuelve la asignación final según el modo."""
    conv = _get(conv_id)
    if not conv:
        return {"ok": False, "error": "convocatoria_no_encontrada"}
    if conv.estado == "cerrada":
        return {"ok": True, "ya_cerrada": True, **detalle(conv_id)}
    modo = modo_efectivo(conv)
    if modo == "sorteo":
        conv.semilla = semilla or str(conv.id)
    ordenadas = _ordenar(conv, _inscripciones(conv_id), modo)
    for rank, i in enumerate(ordenadas, start=1):
        i.posicion = rank
        i.estado = "confirmado" if rank <= conv.cupos else "lista_espera"
    conv.estado = "cerrada"
    conv.cerrado_en = ahora()
    return {"ok": True, "modo": modo, **detalle(conv_id)}


def reabrir(conv_id: int) -> dict:
    """Reabre una convocatoria cerrada (por si el admin cerró por error)."""
    conv = _get(conv_id)
    if not conv:
        return {"ok": False, "error": "convocatoria_no_encontrada"}
    conv.estado = "abierta"
    conv.cerrado_en = None
    for i in _inscripciones(conv_id):
        i.estado = "pendiente"
        i.posicion = None
    return {"ok": True, **detalle(conv_id)}


def marcar_asistencia(conv_id: int, asistencias: list[dict]) -> dict:
    """Marca quién asistió realmente (alimenta el puntaje de equidad y el ranking)."""
    conv = _get(conv_id)
    if not conv:
        return {"ok": False, "error": "convocatoria_no_encontrada"}
    mapa = {a["socio_id"]: bool(a["asistio"]) for a in asistencias}
    n = 0
    for i in _inscripciones(conv_id):
        if i.socio_id in mapa:
            i.asistio = mapa[i.socio_id]
            n += 1
    return {"ok": True, "marcadas": n, **detalle(conv_id)}


def detalle(conv_id: int) -> dict:
    conv = _get(conv_id)
    if not conv:
        return {"ok": False, "error": "convocatoria_no_encontrada"}
    conf, espera = _resolver(conv)
    return {
        "ok": True,
        "convocatoria": como_dict(conv),
        "modo_efectivo": modo_efectivo(conv),
        "abierta_ahora": _abierta(conv),
        "confirmados": [como_dict(i) for i in conf],
        "lista_espera": [como_dict(i) for i in espera],
        "cupos": conv.cupos,
        "cupos_libres": max(0, conv.cupos - len(conf)),
        "total_inscritos": len(_inscripciones(conv_id)),
    }


def listar(club_id: str | None = None, estado: str | None = None) -> list[dict]:
    filas = []
    for c in stores.convocatorias:
        if club_id and c.club_id != club_id:
            continue
        if estado and c.estado != estado:
            continue
        conf, espera = _resolver(c)
        d = como_dict(c)
        d.update({
            "modo_efectivo": modo_efectivo(c),
            "abierta_ahora": _abierta(c),
            "confirmados_n": len(conf),
            "espera_n": len(espera),
            "cupos_libres": max(0, c.cupos - len(conf)),
            "total_inscritos": len(_inscripciones(c.id)),
        })
        filas.append(d)
    filas.sort(key=lambda d: d.get("creado_en") or "", reverse=True)
    return filas


def ranking_socios(club_id: str | None = None) -> list[dict]:
    """Trazabilidad: recurrencia por socio (inscripciones, veces confirmado, veces
    en espera, partidos jugados y no-shows). Ordena por partidos jugados."""
    agg: dict[str, dict] = {}
    for c in stores.convocatorias:
        if club_id and c.club_id != club_id:
            continue
        for i in _inscripciones(c.id):
            a = agg.setdefault(i.socio_id, {
                "socio_id": i.socio_id, "socio_nombre": i.socio_nombre,
                "inscripciones": 0, "confirmado": 0, "lista_espera": 0,
                "jugo": 0, "no_show": 0})
            a["socio_nombre"] = i.socio_nombre or a["socio_nombre"]
            a["inscripciones"] += 1
            if c.estado == "cerrada":
                if i.estado == "confirmado":
                    a["confirmado"] += 1
                elif i.estado == "lista_espera":
                    a["lista_espera"] += 1
            if i.asistio is True:
                a["jugo"] += 1
            elif i.asistio is False:
                a["no_show"] += 1
    filas = list(agg.values())
    filas.sort(key=lambda a: (a["jugo"], a["inscripciones"]), reverse=True)
    return filas


# --- configuración del modo global (torre de control) ----------------------
def config_modo() -> dict:
    return {"global": stores.modo_asignacion(), "modos": list(MODOS_ASIGNACION)}


def set_modo_global(modo: str) -> dict:
    if modo not in MODOS_ASIGNACION:
        return {"ok": False, "error": "modo_invalido", "modos": list(MODOS_ASIGNACION)}
    stores.config["convocatoria_modo_asignacion"] = modo
    return {"ok": True, "global": stores.modo_asignacion()}
