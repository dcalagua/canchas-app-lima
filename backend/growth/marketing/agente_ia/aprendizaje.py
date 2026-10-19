"""LEARNER: convierte el rendimiento histórico en APRENDIZAJES que el estratega
usa al día siguiente ("los posts de los viernes generan +40 % de interacción").

Estadística simple y explicable, sin LLM (un número inventado aquí contaminaría
todas las decisiones siguientes):

* Universo: piezas publicadas en los últimos `DIAS_VENTANA` días con una
  ventana madura (7d > 72h > 24h).
* Por cada dimensión (día, franja, audiencia, tipo de oportunidad, formato,
  origen de la imagen, objetivo, zona) y valor con ≥ `MIN_MUESTRAS` piezas, se
  compara la media del grupo contra la media global: `efecto = media_g/media - 1`.
* `confianza` = 2·Φ(|t|) - 1 con t = (media_g - media) / (sd / √n_g).
* Se guardan los de |efecto| ≥ `MIN_EFECTO` y confianza ≥ `MIN_CONFIANZA`.
"""
from __future__ import annotations

import math
from datetime import timedelta

from marketing.agente_ia import analitica
from marketing.agente_ia.datos import DIAS, franja_de
from marketing.agente_ia.repo import ahora, repo

DIAS_VENTANA = 56
MIN_TOTAL = 8
MIN_MUESTRAS = 3
MIN_EFECTO = 0.15
MIN_CONFIANZA = 0.6
METRICAS = {"engagement_rate": "interacción", "clics_link": "clics al enlace", "reservas_atribuidas": "reservas"}
_FRASE = {
    "dia": lambda v: f"publicadas los {v}", "franja": lambda v: f"publicadas en la {v}",
    "audiencia": lambda v: "para dueños de canchas" if v == "duenos" else "para jugadores",
    "tipo": lambda v: f"de tipo «{v.replace('_', ' ')}»", "content_type": lambda v: f"en formato {v}",
    "media_origen": lambda v: {"foto_real": "con fotos reales", "foto_dueno": "con fotos del dueño", "diseno": "con diseño de marca",
                               "ia_conceptual": "con arte IA"}.get(v, v),
    "objetivo": lambda v: f"con objetivo «{v.replace('_', ' ')}»", "zona": lambda v: f"sobre {v}",
}


def _phi(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _filas(zona_horaria) -> list[dict]:
    out = []
    for c in repo().publicados_desde(ahora() - timedelta(days=DIAS_VENTANA)):
        p = analitica.mejor_ventana(repo().performance(c["id"]))
        if not p:
            continue
        loc = c["published_at"].astimezone(zona_horaria(c.get("pais") or "PE"))
        op = c.get("oportunidad") or {}
        out.append({"id": c["id"], "dia": DIAS[loc.weekday()], "franja": franja_de(loc.hour * 60 + loc.minute),
                    "audiencia": c.get("audiencia"), "tipo": op.get("tipo"), "content_type": c.get("content_type"),
                    "media_origen": c.get("media_origen"), "objetivo": c.get("objetivo"), "zona": (c.get("hechos") or {}).get("zona"),
                    **{m: (float(p[m]) if p.get(m) is not None else None) for m in METRICAS}})
    return out


def calcular(filas: list[dict]) -> list[dict]:
    insights = []
    for metrica, nombre_m in METRICAS.items():
        vals = [f for f in filas if f.get(metrica) is not None]
        if len(vals) < MIN_TOTAL:
            continue
        xs = [f[metrica] for f in vals]
        media = sum(xs) / len(xs)
        if media <= 0:
            continue
        sd = math.sqrt(sum((x - media) ** 2 for x in xs) / (len(xs) - 1)) or 1e-9
        for dim in _FRASE:
            grupos: dict[str, list[dict]] = {}
            for f in vals:
                if f.get(dim):
                    grupos.setdefault(str(f[dim]), []).append(f)
            for valor, g in grupos.items():
                if len(g) < MIN_MUESTRAS or len(g) == len(vals):
                    continue
                mg = sum(f[metrica] for f in g) / len(g)
                efecto = mg / media - 1
                t = (mg - media) / (sd / math.sqrt(len(g)))
                conf = 2 * _phi(abs(t)) - 1
                if abs(efecto) < MIN_EFECTO or conf < MIN_CONFIANZA:
                    continue
                signo = "más" if efecto > 0 else "menos"
                insights.append({
                    "enunciado": f"Las publicaciones {_FRASE[dim](valor)} generan {abs(efecto) * 100:.0f}% {signo} {nombre_m} "
                                 f"que el promedio ({len(g)} publicaciones).",
                    "dimension": dim, "valor": valor, "metrica": metrica, "efecto": round(efecto, 4), "muestras": len(g),
                    "confianza": round(conf, 4), "evidencia": [f["id"] for f in g][:30]})
    insights.sort(key=lambda i: (-i["confianza"], -abs(i["efecto"])))
    return insights[:20]


def actualizar(zona_horaria) -> list[dict]:
    """Recalcula y reemplaza los aprendizajes vigentes."""
    nuevos = calcular(_filas(zona_horaria))
    repo().reemplazar_insights(nuevos)
    repo().log("learner", "insights", total=len(nuevos), enunciados=[i["enunciado"] for i in nuevos[:5]])
    return nuevos


def hora_sugerida(audiencia: str, insights: list[dict], defecto: str) -> str:
    """Si hay una franja que rinde claramente mejor, se publica en ella."""
    horas = {"mañana": "09:00", "tarde": "13:00", "noche": "19:30"}
    mejores = [i for i in insights if i["dimension"] == "franja" and i["efecto"] > 0]
    return horas.get(mejores[0]["valor"], defecto) if mejores else defecto
