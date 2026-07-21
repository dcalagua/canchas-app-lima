"""Agente de CONTENIDO para redes (community manager con IA).

Genera posts listos para Instagram/Facebook (texto + hashtags + mejor hora) a
partir de los datos de la academia/cancha y un tema opcional del dueño. Usa
Anthropic si hay ANTHROPIC_API_KEY; si no, cae a plantillas (contenido real,
sin IA) para que el flujo funcione igual en dev/QAS.

Publicar en Meta (IG/FB) automáticamente es una fase aparte (requiere la API de
Meta). Aquí el dueño APRUEBA y comparte con un tap.
"""

from __future__ import annotations

import json
import re

import config

_SYSTEM = (
    "Eres el community manager de una academia o cancha deportiva en Perú / "
    "Latinoamérica. Escribes en español peruano, cercano y motivador, con "
    "emojis con mesura. Cada post lleva un gancho, algo concreto de la "
    "academia (programa, tarifa, resultado, horario) y un CTA claro para "
    "escribir por WhatsApp o inscribirse. Devuelves SOLO JSON válido con la "
    "forma: {\"posts\":[{\"texto\":\"...\",\"hashtags\":[\"#..\"],"
    "\"hora_sugerida\":\"Mar 7:00 pm\"}]}. 6 a 10 hashtags relevantes y locales. "
    "No inventes datos que no estén en la info dada."
)


def _parsear_json(texto: str) -> dict | None:
    m = re.search(r"\{.*\}", texto or "", re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except (ValueError, TypeError):
        return None


def _con_claude(datos: dict, contexto: str, cantidad: int) -> list[dict] | None:
    try:
        import anthropic
    except Exception:  # noqa: BLE001
        return None
    try:
        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        payload = {"academia": datos, "tema": contexto or "difusión general",
                   "cantidad": cantidad}
        resp = client.messages.create(
            model=config.CONCIERGE_MODEL,
            max_tokens=1400,
            system=_SYSTEM,
            messages=[{"role": "user", "content":
                       "Genera los posts para esta academia (JSON):\n"
                       + json.dumps(payload, ensure_ascii=False)}],
        )
        texto = next((b.text for b in resp.content
                      if getattr(b, "type", "") == "text"), "")
        data = _parsear_json(texto)
        if not isinstance(data, dict):
            return None
        posts = data.get("posts")
        return posts if isinstance(posts, list) and posts else None
    except Exception:  # noqa: BLE001 — cualquier fallo cae a plantilla
        return None


def _plantillas(datos: dict, contexto: str, cantidad: int) -> list[dict]:
    nombre = (datos.get("nombre") or "nuestra academia").strip()
    deporte = (datos.get("deporte") or "").strip()
    sede = (datos.get("sede") or "").strip()
    ig = (datos.get("instagram") or "").strip().lstrip("@")
    dep = deporte or "deporte"
    en_sede = f" en {sede}" if sede else ""
    tags = ["#" + (deporte or "deporte"), "#academiadeportiva", "#Peru",
            "#inscripcionesabiertas", "#" + re.sub(r"\W+", "", nombre.lower())[:20],
            "#deporte", "#niños", "#clases"]
    base = [
        {"texto": f"🎾 ¡Inscripciones abiertas en {nombre}{en_sede}! "
                  f"Aprende {dep} por etapas, con profes que llevan a sus alumnos "
                  f"a competir. Escríbenos por WhatsApp y reserva tu evaluación. 💬",
         "hashtags": tags, "hora_sugerida": "Mar 7:00 pm"},
        {"texto": f"🔥 ¿Buscas dónde entrenar {dep}{en_sede}? En {nombre} tenemos "
                  f"grupos por nivel y horarios flexibles. Cupos limitados — "
                  f"asegura el tuyo hoy. 📲",
         "hashtags": tags, "hora_sugerida": "Jue 12:30 pm"},
        {"texto": f"🏆 En {nombre} formamos más que jugadores: actitud, disciplina "
                  f"y técnica. Ven a una clase de prueba y compruébalo. "
                  + (f"Síguenos en @{ig}. " if ig else "") + "💪",
         "hashtags": tags, "hora_sugerida": "Sáb 10:00 am"},
    ]
    if contexto:
        base.insert(0, {
            "texto": f"📣 {contexto} — en {nombre}{en_sede}. Escríbenos por "
                     f"WhatsApp para más info e inscripciones. 🙌",
            "hashtags": tags, "hora_sugerida": "Hoy 6:00 pm"})
    return base[:max(1, cantidad)]


def generar_posts(datos: dict, contexto: str = "", cantidad: int = 3) -> list[dict]:
    """Devuelve una lista de posts. Nunca lanza."""
    cantidad = max(1, min(int(cantidad or 3), 5))
    if config.ANTHROPIC_API_KEY:
        via_ia = _con_claude(datos, contexto, cantidad)
        if via_ia:
            # Normaliza la forma.
            out = []
            for p in via_ia[:cantidad]:
                if not isinstance(p, dict):
                    continue
                hs = p.get("hashtags")
                out.append({
                    "texto": str(p.get("texto") or "").strip(),
                    "hashtags": [str(h) for h in hs] if isinstance(hs, list) else [],
                    "hora_sugerida": str(p.get("hora_sugerida") or "").strip(),
                })
            if out:
                return out
    return _plantillas(datos, contexto, cantidad)
