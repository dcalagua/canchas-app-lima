"""Catálogo GLOBAL de SERVICIOS EXTRA (add-ons de pago de una reserva).

Decisión del director (sep-2026): el catálogo lo administra el OPERADOR en la
torre `/admin` (curado, sin texto libre para el dueño) y cada dueño lo ACTIVA y
le pone precio por local o por cancha. Antes era una lista fija de 6 claves
duplicada en el app (`ServicioExtra.catalogo`) y en la web
(`catalogos.SERVICIOS_EXTRA`); ahora ambos leen `GET /config/servicios-extra`
(el app lo cachea; sin red usa su lista empaquetada).

Cada servicio:
- `clave`   id estable (slug), lo que se guarda en `pichangol_canchas.servicios_extra`
            y en `extras` de la reserva.
- `nombre`, `emoji`  cómo se muestra.
- `tipo`    cómo se cobra: `reserva` (una vez por reserva), `persona` (× cantidad
            de personas, p. ej. piscina o entrada general), `turno` (× nº de
            turnos reservados, p. ej. clase con entrenador).
- `ambito`  `local` (es del recinto: piscina, sauna; al guardarlo en una cancha
            se propaga a todas las canchas del mismo local) o `cancha` (árbitro,
            petos: solo de esa cancha).
- `deportes` lista de deportes donde aplica ([] = todos).
- `activo`  desactivado = no se ofrece a dueños nuevos (lo ya guardado sigue).

Lo que se guarda en la cancha lleva ADEMÁS `nombre/emoji/tipo/ambito`
congelados, así la ficha, el comprobante y un APK sin red muestran el servicio
aunque el catálogo cambie después.
"""
from __future__ import annotations

import re
import time
from typing import Iterable

from db.store import stores

TIPOS = {"reserva": "por reserva", "persona": "por persona", "turno": "por turno"}
AMBITOS = {"local": "Del local", "cancha": "De la cancha"}
_CLAVE_RE = re.compile(r"^[a-z0-9_]{2,40}$")

# Semilla: los 6 de siempre (misma clave, mismo cobro: no cambia data existente)
# + los que pidió el director para clubes con más instalaciones.
DEFAULTS: list[dict] = [
    {"clave": "arbitro", "nombre": "Árbitro", "emoji": "🧑‍⚖️", "tipo": "reserva", "ambito": "cancha"},
    {"clave": "pelotero", "nombre": "Pelotero (recoge pelotas)", "emoji": "🏃", "tipo": "reserva", "ambito": "cancha"},
    {"clave": "pelota", "nombre": "Alquiler de pelota", "emoji": "🎾", "tipo": "reserva", "ambito": "cancha"},
    {"clave": "pecheras", "nombre": "Petos / pecheras", "emoji": "🦺", "tipo": "reserva", "ambito": "cancha"},
    {"clave": "hidratacion", "nombre": "Hidratación", "emoji": "💧", "tipo": "reserva", "ambito": "cancha"},
    {"clave": "parrilla", "nombre": "Parrilla / grill", "emoji": "🔥", "tipo": "reserva", "ambito": "local"},
    {"clave": "piscina", "nombre": "Piscina", "emoji": "🏊", "tipo": "persona", "ambito": "local"},
    {"clave": "entrada_general", "nombre": "Entrada general (pase de día)", "emoji": "🎟️", "tipo": "persona", "ambito": "local"},
    {"clave": "sauna", "nombre": "Sauna / jacuzzi", "emoji": "🧖", "tipo": "persona", "ambito": "local"},
    {"clave": "gimnasio", "nombre": "Gimnasio", "emoji": "🏋️", "tipo": "persona", "ambito": "local"},
    {"clave": "toallas", "nombre": "Toallas", "emoji": "🧺", "tipo": "persona", "ambito": "local"},
    {"clave": "locker", "nombre": "Locker / casillero", "emoji": "🔐", "tipo": "reserva", "ambito": "local"},
    {"clave": "estacionamiento_pago", "nombre": "Estacionamiento", "emoji": "🅿️", "tipo": "reserva", "ambito": "local"},
    {"clave": "clase", "nombre": "Clase con entrenador", "emoji": "🎓", "tipo": "turno", "ambito": "cancha"},
    {"clave": "iluminacion", "nombre": "Iluminación nocturna", "emoji": "💡", "tipo": "turno", "ambito": "cancha"},
    {"clave": "grabacion", "nombre": "Grabación del partido", "emoji": "🎥", "tipo": "reserva", "ambito": "cancha"},
]


def _norm(item: dict, orden: int) -> dict:
    return {
        "clave": str(item.get("clave") or "").strip().lower(),
        "nombre": str(item.get("nombre") or "").strip()[:60],
        "emoji": str(item.get("emoji") or "").strip()[:8] or "➕",
        "tipo": item.get("tipo") if item.get("tipo") in TIPOS else "reserva",
        "ambito": item.get("ambito") if item.get("ambito") in AMBITOS else "cancha",
        "deportes": [str(d).lower() for d in (item.get("deportes") or []) if str(d).strip()],
        "activo": bool(item.get("activo", True)),
        "orden": int(item.get("orden", orden)),
    }


def _asegurar() -> dict[str, dict]:
    """Siembra el catálogo si el snapshot no lo tenía (ambientes viejos) y
    agrega las claves nuevas de DEFAULTS que falten, sin pisar lo editado."""
    cat = stores.servicios_extra
    cambiado = False
    for i, d in enumerate(DEFAULTS):
        if d["clave"] not in cat:
            cat[d["clave"]] = _norm(d, i)
            cambiado = True
    if cambiado:
        stores.servicios_extra_version += 1
    return cat


def catalogo(solo_activos: bool = True) -> list[dict]:
    cat = _asegurar()
    out = [dict(v) for v in cat.values() if v.get("activo", True) or not solo_activos]
    out.sort(key=lambda x: (int(x.get("orden", 0)), x["clave"]))
    return out


def por_clave() -> dict[str, dict]:
    return {v["clave"]: dict(v) for v in catalogo(solo_activos=False)}


def para_deporte(deporte: str | None) -> list[dict]:
    d = (deporte or "").lower()
    return [s for s in catalogo() if not s.get("deportes") or not d or d in s["deportes"]]


def etiqueta_tipo(tipo: str) -> str:
    return TIPOS.get(tipo or "reserva", TIPOS["reserva"])


def congelar(clave: str, precio: float) -> dict | None:
    """Fila `{clave, precio, nombre, emoji, tipo, ambito}` para guardar en la
    cancha. None si la clave no existe en el catálogo."""
    s = por_clave().get(clave)
    if not s:
        return None
    return {"clave": clave, "precio": round(float(precio), 2), "nombre": s["nombre"], "emoji": s["emoji"],
            "tipo": s["tipo"], "ambito": s["ambito"]}


def completar(s: dict) -> dict:
    """Devuelve la fila de una cancha con nombre/emoji/tipo/ambito rellenados
    desde el catálogo si le faltan (datos guardados por un APK viejo)."""
    s = dict(s or {})
    ref = por_clave().get(str(s.get("clave") or ""), {})
    for k, default in (("nombre", str(s.get("clave") or "").replace("_", " ").capitalize()), ("emoji", "➕"), ("tipo", "reserva"), ("ambito", "cancha")):
        if not s.get(k):
            s[k] = ref.get(k) or default
    return s


def linea_reserva(s: dict, cantidad: int, turnos: int) -> dict:
    """Línea que se guarda en `extras` de la RESERVA. `precio` = TOTAL de la
    línea (compatible con los APKs que solo suman `precio`); `unitario` y
    `cantidad` para mostrar "Piscina × 3"."""
    s = completar(s)
    unit = round(float(s.get("precio") or 0), 2)
    if s["tipo"] == "persona":
        cant = max(1, min(int(cantidad or 1), 50))
    elif s["tipo"] == "turno":
        cant = max(1, int(turnos or 1))
    else:
        cant = 1
    return {"clave": s["clave"], "precio": round(unit * cant, 2), "unitario": unit, "cantidad": cant,
            "nombre": s["nombre"], "emoji": s["emoji"], "tipo": s["tipo"]}


def validar(item: dict, nuevo: bool) -> dict:
    """Valida un alta/edición desde la torre. Lanza ValueError con el motivo."""
    clave = str(item.get("clave") or "").strip().lower().replace(" ", "_")
    if not _CLAVE_RE.match(clave):
        raise ValueError("La clave debe tener 2-40 caracteres: letras minúsculas, números o guion bajo (ej. piscina, pase_dia).")
    if nuevo and clave in stores.servicios_extra:
        raise ValueError("Ya existe un servicio con esa clave.")
    nombre = str(item.get("nombre") or "").strip()
    if len(nombre) < 3:
        raise ValueError("Pon el nombre del servicio (mínimo 3 caracteres).")
    if item.get("tipo") not in TIPOS:
        raise ValueError("Tipo de cobro no válido.")
    if item.get("ambito") not in AMBITOS:
        raise ValueError("Ámbito no válido.")
    return {**item, "clave": clave, "nombre": nombre[:60]}


def guardar(item: dict, nuevo: bool) -> dict:
    cat = _asegurar()
    v = validar(item, nuevo)
    actual = cat.get(v["clave"]) or {}
    orden = actual.get("orden", len(cat))
    fila = _norm({**actual, **v, "orden": v.get("orden", orden)}, orden)
    cat[fila["clave"]] = fila
    stores.servicios_extra_version += 1
    return fila


def activar(clave: str, activo: bool) -> dict | None:
    cat = _asegurar()
    s = cat.get(clave)
    if not s:
        return None
    s["activo"] = bool(activo)
    stores.servicios_extra_version += 1
    return dict(s)


# ── Sugerencias de dueños ("mi local ofrece X y no está en la lista") ─────────

def sugerir(email: str, texto: str, cancha_id: str = "", local: str = "") -> dict:
    t = re.sub(r"\s+", " ", (texto or "")).strip()[:200]
    if len(t) < 3:
        raise ValueError("Cuéntanos qué servicio ofrece tu local (mínimo 3 caracteres).")
    s = {"id": f"sug_{int(time.time() * 1000)}_{stores.next_id('sugerencia_servicio')}", "email": (email or "").lower(),
         "texto": t, "cancha_id": cancha_id or "", "local": (local or "")[:80], "creado_en": time.time(), "estado": "pendiente"}
    stores.sugerencias_servicios.append(s)
    return dict(s)


def sugerencias(pendientes: bool = False) -> list[dict]:
    out = [dict(s) for s in stores.sugerencias_servicios if not pendientes or s.get("estado") == "pendiente"]
    out.sort(key=lambda s: -float(s.get("creado_en") or 0))
    return out


def atender_sugerencia(sug_id: str, estado: str) -> dict | None:
    for s in stores.sugerencias_servicios:
        if s.get("id") == sug_id:
            s["estado"] = estado if estado in ("atendida", "descartada", "pendiente") else "atendida"
            s["atendida_en"] = time.time()
            return dict(s)
    return None


def publico() -> dict:
    """Respuesta de `GET /config/servicios-extra` (APK + web)."""
    return {"version": stores.servicios_extra_version, "tipos": TIPOS, "ambitos": AMBITOS, "servicios": catalogo()}


def claves(items: Iterable[dict]) -> set[str]:
    return {str(s.get("clave") or "") for s in items}
