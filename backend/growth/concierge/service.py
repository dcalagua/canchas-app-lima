"""Concierge de reservas (primer agente de IA de Pichangol).

El APK manda el mensaje en lenguaje natural del jugador ("quiero fútbol mañana a
las 7pm por Surco") + la lista de canchas que ya conoce (con distancias). Aquí
Claude interpreta la intención (deporte, día, hora, zona) y **rankea** esas
canchas, devolviendo una respuesta amable + sugerencias ordenadas.

Diseño fail-safe: la data de canchas la pone la app (no el backend), así el
agente no necesita acceso a Supabase. Si no hay ANTHROPIC_API_KEY o Claude
falla, cae a una heurística simple (filtra por deporte + ordena por distancia)
para que la función nunca deje al usuario sin respuesta.

Modelo por defecto: claude-opus-4-8 (override con CONCIERGE_MODEL; para bajar
costo en alto volumen se puede poner claude-haiku-4-5).
"""

from __future__ import annotations

import json
import unicodedata
from typing import Any

import config

_SYSTEM = (
    "Eres el concierge de reservas de Pichangol, un marketplace para reservar "
    "canchas de fútbol, tenis, pádel y más en Lima, Perú. Hablas SIEMPRE en "
    "español peruano, cercano y breve.\n\n"
    "Recibes el mensaje del jugador y una lista JSON de CANCHAS DISPONIBLES "
    "(cada una con id, nombre, deporte, distrito, precioHora y, si se conoce, "
    "distanciaKm). Tu trabajo:\n"
    "1) Interpretar la intención: deporte, día, hora y zona.\n"
    "2) Elegir y ORDENAR las mejores canchas de la lista para ese pedido "
    "(cercanía, deporte correcto, precio razonable). Usa SOLO ids que estén en "
    "la lista; no inventes canchas.\n"
    "3) Escribir una respuesta corta y amable que resuma qué encontraste.\n\n"
    "Responde ÚNICAMENTE con un objeto JSON válido, sin texto adicional ni "
    "```: {\"respuesta\": str, \"intencion\": {\"deporte\": str, \"dia\": str, "
    "\"hora\": str, \"zona\": str}, \"sugerencias\": [{\"canchaId\": str, "
    "\"motivo\": str}]}. Si un dato de la intención no se menciona, ponlo como "
    "cadena vacía. Máximo 5 sugerencias."
)

# Sinónimos → deporte canónico (mismos names que el modelo Flutter Deporte).
_DEPORTES = {
    "futbol": ["futbol", "pichanga", "cascarita", "fulbito", "gras", "grass", "loza", "fut"],
    "tenis": ["tenis", "tennis"],
    "padel": ["padel"],
    "pickleball": ["pickleball", "pickle"],
    "basquet": ["basquet", "basket", "basketball", "basquetbol"],
    "voley": ["voley", "voleibol", "volley"],
}

# Zonas/distritos de Lima → palabras clave para detectarlas en el mensaje.
# El display (clave) se usa en la respuesta; las claves sirven para detectar y
# para preferir canchas cuyo distrito coincida.
_ZONAS = {
    "Surco": ["surco"],
    "La Molina": ["la molina", "molina"],
    "San Borja": ["san borja"],
    "Miraflores": ["miraflores"],
    "San Isidro": ["san isidro"],
    "Barranco": ["barranco"],
    "Chorrillos": ["chorrillos"],
    "San Miguel": ["san miguel"],
    "Jesús María": ["jesus maria"],
    "Magdalena": ["magdalena"],
    "Pueblo Libre": ["pueblo libre"],
    "Lince": ["lince"],
    "Surquillo": ["surquillo"],
    "La Victoria": ["la victoria"],
    "Ate": ["ate", "santa clara"],
    "Chaclacayo": ["chaclacayo"],
    "Chosica": ["chosica", "lurigancho"],
    "SJL": ["san juan de lurigancho", "sjl"],
    "SJM": ["san juan de miraflores", "sjm"],
    "Los Olivos": ["los olivos"],
    "Comas": ["comas"],
    "Callao": ["callao"],
}


def _norm(s: Any) -> str:
    t = unicodedata.normalize("NFD", str(s or "").lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def _deporte_en(texto: str) -> str | None:
    t = _norm(texto)
    for dep, claves in _DEPORTES.items():
        if any(k in t for k in claves):
            return dep
    return None


def _zona_en(texto: str) -> tuple[str, list[str]] | None:
    """Detecta una zona/distrito en el mensaje. Devuelve (display, claves)."""
    t = _norm(texto)
    for zona, claves in _ZONAS.items():
        if any(k in t for k in claves):
            return zona, claves
    return None


def recomendar(
    mensaje: str,
    canchas: list[dict],
    ahora: str | None = None,
    presupuesto: float | None = None,
) -> dict:
    """Devuelve {respuesta, intencion, sugerencias}. Nunca lanza."""
    if config.ANTHROPIC_API_KEY:
        via_ia = _con_claude(mensaje, canchas, ahora, presupuesto)
        if via_ia is not None:
            return via_ia
    return _fallback(mensaje, canchas)


def _con_claude(
    mensaje: str, canchas: list[dict], ahora: str | None, presupuesto: float | None
) -> dict | None:
    try:
        import anthropic  # import perezoso: sólo si hay key configurada
    except Exception:  # noqa: BLE001 — SDK no instalado
        return None
    try:
        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        contexto = {
            "ahora": ahora,
            "presupuesto": presupuesto,
            "canchas": canchas,
        }
        resp = client.messages.create(
            model=config.CONCIERGE_MODEL,
            max_tokens=1024,
            system=_SYSTEM,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"{mensaje}\n\nCANCHAS DISPONIBLES (JSON):\n"
                        + json.dumps(contexto, ensure_ascii=False)
                    ),
                }
            ],
        )
        texto = next(
            (b.text for b in resp.content if getattr(b, "type", "") == "text"), ""
        )
        data = _parsear_json(texto)
        if not isinstance(data, dict):
            return None
        # Sanea: quedarse sólo con ids que existan realmente.
        ids = {c.get("id") for c in canchas}
        sugs = [
            s
            for s in (data.get("sugerencias") or [])
            if isinstance(s, dict) and s.get("canchaId") in ids
        ]
        return {
            "respuesta": str(data.get("respuesta") or ""),
            "intencion": data.get("intencion") or {},
            "sugerencias": sugs[:5],
            "via": "ia",
        }
    except Exception:  # noqa: BLE001 — cualquier fallo cae al heurístico
        return None


def _parsear_json(texto: str) -> Any:
    """Extrae el primer objeto JSON del texto (tolera ``` y prosa alrededor)."""
    t = texto.strip()
    if t.startswith("```"):
        t = t.strip("`")
        if t[:4].lower() == "json":
            t = t[4:]
    ini = t.find("{")
    fin = t.rfind("}")
    if ini < 0 or fin <= ini:
        return None
    try:
        return json.loads(t[ini : fin + 1])
    except Exception:  # noqa: BLE001
        return None


def _fallback(mensaje: str, canchas: list[dict]) -> dict:
    """Sin IA: filtra por deporte + zona detectados y ordena por distancia."""
    dep = _deporte_en(mensaje)
    zona = _zona_en(mensaje)
    zona_nombre = zona[0] if zona else ""
    cands = list(canchas)
    if dep:
        filtradas = [c for c in cands if _norm(c.get("deporte")) == dep]
        if filtradas:
            cands = filtradas
    # Si se mencionó una zona y hay canchas de ese distrito, priorízalas.
    if zona:
        del_distrito = [
            c for c in cands
            if any(k in _norm(c.get("distrito")) for k in zona[1])
        ]
        if del_distrito:
            cands = del_distrito

    def _dist(c: dict) -> float:
        d = c.get("distanciaKm")
        return float(d) if isinstance(d, (int, float)) else 9999.0

    cands.sort(key=_dist)
    top = cands[:4]
    if not top:
        respuesta = (
            f"No encontré canchas{' de ' + dep if dep else ''}"
            f"{' por ' + zona_nombre if zona_nombre else ''}. Prueba ampliando "
            "la zona o cambiando de deporte."
        )
    else:
        que = f"canchas de {dep}" if dep else "canchas"
        donde = f" cerca de {zona_nombre}" if zona_nombre else " más cercanas"
        respuesta = f"Estas son las {que}{donde} para tu pedido."
    motivo = f"Cerca de {zona_nombre}" if zona_nombre else "Cercana"
    return {
        "respuesta": respuesta,
        "intencion": {
            "deporte": dep or "",
            "dia": "",
            "hora": "",
            "zona": zona_nombre,
        },
        "sugerencias": [
            {"canchaId": c.get("id"), "motivo": motivo} for c in top
        ],
        "via": "heuristica",
    }
