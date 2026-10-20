"""MARKETING STRATEGIST: ¿qué publicamos hoy, para quién, dónde y para qué?

Dos pasos, para que la IA no pueda inventar nada:

1. `candidatas(snapshot, ...)`: reglas DETERMINISTAS sobre el snapshot real
   generan oportunidades, cada una con su objetivo medible (KPI), su razón (con
   las cifras reales) y sus `hechos`: lo ÚNICO que el copy podrá afirmar.
2. `decidir(...)`: la IA (si hay llave) elige entre esas candidatas, con el
   historial y los aprendizajes; solo puede devolver ids de candidatas. Sin IA
   o si responde mal, se eligen por puntaje.

Peso jugadores ↔ dueños (`PLAN_FUTBOL.md`, regla de oro): con < `umbral`
canchas reservables en una zona no se le vende disponibilidad al jugador en esa
zona; el día se inclina a CAPTAR DUEÑOS (`mix_duenos_baja`, 70 % por defecto).
"""
from __future__ import annotations

import json
import re

from marketing.agente_ia import datos as _d
from config import MARCA  # noqa: E402 — nombre y dominio de marca (un solo lugar)

OBJETIVOS = ("reservas", "usuarios", "promo_cancha", "captar_duenos", "promo_zona", "interaccion", "trafico", "promo_real")
KPI = {"reservas": "reservas_atribuidas", "promo_cancha": "reservas_atribuidas", "promo_real": "reservas_atribuidas",
       "promo_zona": "clics_link", "usuarios": "clics_link", "trafico": "clics_link", "captar_duenos": "clics_link",
       "interaccion": "engagement_rate"}
TIPOS_CONTENIDO = ("post", "reel", "pregunta", "encuesta", "educativo", "meme", "story", "carrusel")
ENFOQUES_MARCA = ["beneficio", "tip", "humor", "historia", "comunidad"]
HORA_DEFECTO = {"jugadores": "12:30", "duenos": "09:00"}
_DEP = {"futbol": "fútbol", "tenis": "tenis", "padel": "pádel", "pickleball": "pickleball", "voley": "vóley",
        "basquet": "básquet", "natacion": "natación", "futsal": "futsal"}


def _cand(i: int, **k) -> dict:
    k.setdefault("content_type", "post")
    k.setdefault("zona", None)
    k.setdefault("cancha_ids", [])
    k.setdefault("destacadas", [])
    k["kpi"] = KPI[k["objetivo"]]
    k["id"] = f"c{i}"
    return k


def _base_hechos(s: dict) -> dict:
    return {"pais": s["pais"], "moneda": {"PE": "S/", "BO": "Bs", "EC": "$"}.get(s["pais"], "S/")}


def _proximos(hoy_iso: str, n: int = 3) -> list[str]:
    """Fechas ISO de los n días SIGUIENTES (desde mañana): la pieza sale a
    mediodía y la franja de hoy puede haber pasado o estar por pasar. Fechas y
    no nombres de día: "jueves" de esta semana ≠ "jueves" de la próxima."""
    from datetime import date, timedelta
    hoy = date.fromisoformat(hoy_iso)
    return [(hoy + timedelta(days=k)).isoformat() for k in range(1, n + 1)]


def _dia(fecha_iso: str) -> str:
    from datetime import date
    return _d.DIAS[date.fromisoformat(fecha_iso).weekday()]


def _cancha_hechos(c: dict) -> dict:
    return {"id": c["id"], "nombre": c["club"] or c["nombre"], "zona": c.get("zona_nombre"),
            "deportes": [_DEP.get(x, x) for x in c["deportes"]], "precio_hora": c.get("precio_hora"),
            "moneda": c["moneda"], "horario": (f"{str(c['apertura'])[:5]}–{str(c['cierre'])[:5]}" if c.get("apertura") and c.get("cierre") else None)}


def candidatas(s: dict, *, umbral: int = 15, dia_rotacion: int = 0) -> list[dict]:
    """Oportunidades REALES del día. `dia_rotacion` (p. ej. el ordinal de la
    fecha) rota el enfoque de marca para no repetir siempre el mismo."""
    out: list[dict] = []
    por_zona = s["canchas"]["por_zona"]
    densas = {z for z, v in por_zona.items() if v["reservables"] >= umbral}
    lista = {c["id"]: c for c in s["canchas_lista"]}
    proximos = _proximos(s["hoy"])
    i = 0

    # 1) Huecos de agenda en zonas con oferta suficiente → reservas.
    huecos = [x for x in s["libres_7d"] if x["zona"] in densas and x["fecha"] in proximos and x["libres"] > 0]
    mejor_por_zona: dict[str, dict] = {}
    for h in sorted(huecos, key=lambda x: -x["libres"]):
        mejor_por_zona.setdefault(h["zona"], h)
    for z, h in mejor_por_zona.items():
        i += 1
        nombre = por_zona[z]["nombre"]
        n = len(h["canchas"])
        out.append(_cand(i, tipo="huecos_zona", objetivo="reservas", audiencia="jugadores", zona=z,
                         razon=f"{n} canchas de {nombre} tienen {h['libres']} turnos libres el {h['dia']} por la {h['franja']}.",
                         score=3.0 + min(h["libres"], 60) / 20, cancha_ids=h["canchas"][:20], dia_objetivo=h["dia"], franja=h["franja"],
                         fecha_objetivo=h["fecha"],
                         hechos={**_base_hechos(s), "zona": nombre, "dia": h["dia"], "franja": h["franja"], "canchas_con_turnos": n}))

    # 2) Canchas destacables (dueño Pro + destacar Pro): la cancha es protagonista.
    for c in s["canchas_lista"]:
        if not (c["destacable"] and c["reservable"]):
            continue
        libres = s["libres_por_cancha"].get(c["id"]) or {}
        prox = sorted(((k, n) for k, n in libres.items() if k.split("|")[0] in proximos), key=lambda kv: -kv[1])
        if not prox:
            continue
        (fecha, franja), n = prox[0][0].split("|"), prox[0][1]
        dia = _dia(fecha)
        i += 1
        out.append(_cand(i, tipo="cancha_destacada", objetivo="promo_cancha", audiencia="jugadores", zona=c["zona"],
                         razon=f"{c['club']} (Pro) tiene {n} turnos libres el {dia} por la {franja}.",
                         score=3.5 + min(n, 12) / 6, cancha_ids=[c["id"]], destacadas=[c["id"]], dia_objetivo=dia, franja=franja,
                         fecha_objetivo=fecha, hechos={**_base_hechos(s), "zona": c.get("zona_nombre"), "dia": dia, "franja": franja, "cancha": _cancha_hechos(c)}))

    # 3) Promos reales vigentes.
    for p in s["promos"]:
        c = lista.get(p.get("cancha_id") or "")
        if p["tipo"] in ("hora_feliz", "descuento_turno") and c:
            if c["destacable"]:
                i += 1
                # La fecha ISO va en la oportunidad (para revalidar), no en `hechos`: sus
                # dígitos (2026, 10…) no deben quedar "permitidos" en el copy.
                promo = {"tipo": p["tipo"], "pct": p["pct"], **({"desde": p["desde"], "hasta": p["hasta"]} if p["tipo"] == "hora_feliz"
                                                                 else {"dia": f"{_dia(p['fecha'])} {int(p['fecha'][8:10])}", "horas": p["horas"]})}
                out.append(_cand(i, tipo="promo_real", objetivo="promo_real", audiencia="jugadores", zona=c["zona"],
                                 razon=f"{c['club']} tiene {p['pct']}% de descuento ({p['tipo'].replace('_', ' ')}).",
                                 score=4.5, cancha_ids=[c["id"]], destacadas=[c["id"]], promo_tipo=p["tipo"],
                                 fecha_objetivo=p.get("fecha"), vigente_hasta=p.get("vigente_hasta"),
                                 hechos={**_base_hechos(s), "zona": c.get("zona_nombre"), "cancha": _cancha_hechos(c), "promo": promo}))
    zonas_promo: dict[str, list[dict]] = {}
    for p in s["promos"]:
        c = lista.get(p.get("cancha_id") or "")
        if c and not c["destacable"] and p["tipo"] == "hora_feliz" and c["zona"] in densas:
            zonas_promo.setdefault(c["zona"], []).append(p)
    for z, ps in zonas_promo.items():
        i += 1
        nombre = por_zona[z]["nombre"]
        out.append(_cand(i, tipo="promo_zona", objetivo="promo_zona", audiencia="jugadores", zona=z,
                         razon=f"{len(ps)} canchas de {nombre} tienen hora feliz (hasta {max(p['pct'] for p in ps)}%).",
                         score=3.8, cancha_ids=[p["cancha_id"] for p in ps],
                         hechos={**_base_hechos(s), "zona": nombre, "canchas_con_promo": len(ps), "pct_max": max(p["pct"] for p in ps),
                                 "promo": {"tipo": "hora_feliz"}}))

    # 4) Canchas nuevas por zona.
    nuevas_zona: dict[str | None, list[str]] = {}
    for cid in s["nuevas"]:
        c = lista.get(cid)
        if c and c["zona"]:
            nuevas_zona.setdefault(c["zona"], []).append(cid)
    for z, ids in nuevas_zona.items():
        i += 1
        nombre = por_zona[z]["nombre"]
        out.append(_cand(i, tipo="canchas_nuevas", objetivo="usuarios", audiencia="jugadores", zona=z,
                         razon=f"{len(ids)} cancha(s) nueva(s) en {nombre} en los últimos {_d.NUEVA_DIAS} días.",
                         score=2.8 if z in densas else 2.2, cancha_ids=ids,
                         destacadas=[x for x in ids if lista[x]["destacable"]],
                         hechos={**_base_hechos(s), "zona": nombre, "canchas_nuevas": len(ids),
                                 "canchas": [_cancha_hechos(lista[x]) for x in ids if lista[x]["destacable"]]}))

    # 5) Captación de dueños donde hay oferta sin digitalizar.
    for z, v in sorted(s["leads_duenos"].items(), key=lambda kv: -kv[1]["total"]):
        if z in densas or v["total"] < 3:
            continue
        i += 1
        out.append(_cand(i, tipo="captar_duenos_zona", objetivo="captar_duenos", audiencia="duenos", zona=z,
                         razon=f"{v['total']} canchas de {v['nombre']} ya aparecen en el mapa de {MARCA} y no tienen dueño registrado.",
                         score=2.5 + min(v["total"], 80) / 40,
                         hechos={**_base_hechos(s), "zona": v["nombre"], "canchas_sin_dueno": v["total"], "registro_gratis": True}))
        if i > 40:
            break
    for z, v in s["demanda"].items():
        if v["solicitudes"] >= 2:
            i += 1
            out.append(_cand(i, tipo="demanda_zona", objetivo="captar_duenos", audiencia="duenos", zona=z,
                             razon=f"{v['solicitudes']} jugadores pidieron canchas en {v['nombre']} desde la app.",
                             score=3.0 + min(v["solicitudes"], 20) / 10,
                             hechos={**_base_hechos(s), "zona": v["nombre"], "solicitudes_jugadores": v["solicitudes"], "registro_gratis": True}))

    # 6) Comunidad (pichangas / convocatorias abiertas).
    com = s["comunidad"]
    if com["partidos_abiertos"] or com["convocatorias_abiertas"]:
        i += 1
        out.append(_cand(i, tipo="comunidad", objetivo="interaccion", audiencia="jugadores", content_type="pregunta",
                         razon=f"{com['partidos_abiertos']} partidos abiertos y {com['convocatorias_abiertas']} convocatorias buscando jugadores.",
                         score=2.4, hechos={**_base_hechos(s), "partidos_abiertos": com["partidos_abiertos"],
                                            "convocatorias_abiertas": com["convocatorias_abiertas"]}))

    # 7) Siempre disponibles: marca para jugadores y propuesta para dueños.
    enfoque = ENFOQUES_MARCA[dia_rotacion % len(ENFOQUES_MARCA)]
    i += 1
    out.append(_cand(i, tipo="marca_jugadores", objetivo="usuarios", audiencia="jugadores",
                     content_type="educativo" if enfoque == "tip" else ("meme" if enfoque == "humor" else "post"),
                     razon=f"Contenido de marca ({enfoque}): que descarguen la app o reserven en la web.", score=1.5, enfoque=enfoque,
                     hechos=_base_hechos(s)))
    i += 1
    out.append(_cand(i, tipo="duenos_beneficios", objetivo="captar_duenos", audiencia="duenos",
                     razon="Propuesta de valor para dueños: registro gratis, agenda y cobros en línea.", score=1.6,
                     hechos={**_base_hechos(s), "registro_gratis": True}))
    return out


# ── locales Pro: cupo fijo al mes ─────────────────────────────────────────────
def club_de(c: dict) -> str:
    return str(c.get("club") or c.get("nombre") or c.get("id") or "").strip().lower()


def pro_del_dia(s: dict, *, cupo: int, usados: dict[str, int], ultimo: dict[str, str] | None = None,
                ya: set[str] | None = None, max_dia: int = 1) -> list[dict]:
    """Piezas EXTRA del día para cumplir el cupo mensual de cada local Pro
    destacable (dueño Pro + "destacar Pro" encendido). El cupo se reparte
    parejo en el mes: hoy toca el local que va ATRASADO respecto a su ritmo
    (cupo × día / días del mes); entre atrasados, el más atrasado y luego el
    que hace más tiempo no sale. `usados` cuenta lo que ya tiene el local este
    mes (por club); `ya` = clubes que ya salen hoy. Solo locales con fotos
    reales (la IA ambienta SUS fotos, no inventa el lugar)."""
    import calendar
    import math
    from datetime import date
    if cupo <= 0 or max_dia <= 0:
        return []
    hoy = date.fromisoformat(s["hoy"])
    dias_mes = calendar.monthrange(hoy.year, hoy.month)[1]
    meta_hoy = math.ceil(cupo * hoy.day / dias_mes)
    ultimo, ya = ultimo or {}, ya or set()
    por_club: dict[str, dict] = {}
    for c in s["canchas_lista"]:
        if not (c.get("destacable") and c.get("reservable") and c.get("fotos")):
            continue
        k = club_de(c)
        if k in ya:
            continue
        actual = por_club.get(k)
        if actual is None or len(c["fotos"]) > len(actual["fotos"]):
            por_club[k] = c
    atrasados = []
    for k, c in por_club.items():
        n = int(usados.get(k) or 0)
        if n >= cupo or n >= meta_hoy:
            continue
        atrasados.append((meta_hoy - n, ultimo.get(k) or "", k, c))
    atrasados.sort(key=lambda t: (-t[0], t[1], t[2]))
    out = []
    for i, (deuda, _u, k, c) in enumerate(atrasados[:max_dia], start=1):
        n = int(usados.get(k) or 0)
        out.append({**_cand(900 + i, tipo="local_pro", objetivo="promo_cancha", audiencia="jugadores", zona=c["zona"], content_type="post",
                             razon=f"{c['club']} es Pro: lleva {n} de {cupo} publicaciones este mes.",
                             score=5.0, cancha_ids=[c["id"]], destacadas=[c["id"]],
                             hechos={**_base_hechos(s), "zona": c.get("zona_nombre"), "cancha": _cancha_hechos(c)}),
                    "hora": HORA_DEFECTO["jugadores"], "por_que": f"Cupo Pro del mes ({n + 1} de {cupo}) para {c['club']}.",
                    "puntaje": 5.0})
    return out


def _sin_pro_agotado(cands: list[dict], lista: dict[str, dict], cupo: int | None, usados: dict[str, int]) -> list[dict]:
    """Con cupo, una oportunidad que nombra a un local que ya llegó a su cupo del mes no se ofrece."""
    if cupo is None:
        return cands
    out = []
    for c in cands:
        clubes = {club_de(lista[x]) for x in c.get("destacadas") or [] if x in lista}
        if clubes and any(int(usados.get(k) or 0) >= cupo for k in clubes):
            continue
        out.append(c)
    return out


def _club_repetido(c: dict, usados: set[str], lista: dict[str, dict]) -> bool:
    clubes = {club_de(lista[x]) for x in c.get("destacadas") or [] if x in lista}
    if clubes & usados:
        return True
    usados |= clubes
    return False


# ── decisión ─────────────────────────────────────────────────────────────────
def _baja_densidad(s: dict, umbral: int) -> bool:
    return not any(v["reservables"] >= umbral for v in s["canchas"]["por_zona"].values())


def _boost(c: dict, insights: list[dict]) -> float:
    f = 1.0
    for ins in insights:
        valor = {"tipo": c["tipo"], "audiencia": c["audiencia"], "content_type": c["content_type"], "objetivo": c["objetivo"],
                 "zona": c.get("hechos", {}).get("zona"), "enfoque": c.get("enfoque")}.get(ins.get("dimension"))
        if valor is not None and str(valor) == str(ins.get("valor")):
            f *= 1 + max(-0.5, min(1.0, float(ins["efecto"]))) * float(ins["confianza"])
    return f


def _penalizacion(c: dict, recientes: list[dict]) -> float:
    """Recientes = oportunidades de los últimos días (más nuevo primero)."""
    f = 1.0
    for n, r in enumerate(recientes[:14]):
        if r.get("tipo") == c["tipo"] and r.get("zona") == c.get("zona"):
            f *= 0.45 if n < 7 else 0.75
        elif r.get("tipo") == c["tipo"] and n < 2:
            f *= 0.7
    return f


def ordenar(cands: list[dict], *, insights: list[dict], recientes: list[dict]) -> list[dict]:
    for c in cands:
        c["puntaje"] = round(c["score"] * _boost(c, insights) * _penalizacion(c, recientes), 4)
    return sorted(cands, key=lambda c: -c["puntaje"])


def _audiencias_del_dia(n: int, s: dict, umbral: int, mix_duenos_baja: float, mix_duenos_alta: float,
                        recientes: list[dict]) -> list[str]:
    """Reparte las N piezas del día entre audiencias para acercarse a la mezcla
    objetivo, mirando lo publicado/planificado en los últimos días."""
    objetivo = mix_duenos_baja if _baja_densidad(s, umbral) else mix_duenos_alta
    hist = [r.get("audiencia") for r in recientes[:10] if r.get("audiencia")]
    out = []
    for _ in range(n):
        share = (sum(1 for a in hist if a == "duenos") / len(hist)) if hist else 0.0
        aud = "duenos" if share < objetivo else "jugadores"
        out.append(aud)
        hist.insert(0, aud)
    return out


def por_reglas(cands: list[dict], n: int, auds: list[str], lista: dict[str, dict] | None = None) -> list[dict]:
    elegidas, usados, clubes = [], set(), set()
    lista = lista or {}
    for aud in auds:
        libres = [c for c in cands if c["id"] not in usados and not ({club_de(lista[x]) for x in c.get("destacadas") or [] if x in lista} & clubes)]
        c = next((c for c in libres if c["audiencia"] == aud), None) or next(iter(libres), None)
        if c:
            usados.add(c["id"])
            _club_repetido(c, clubes, lista)
            elegidas.append({**c, "hora": HORA_DEFECTO.get(c["audiencia"], "12:30"), "por_que": c["razon"]})
    return elegidas[:n]


_SYSTEM = (
    f"Eres el estratega de marketing de {MARCA} (marketplace para reservar canchas en Perú, Bolivia y Ecuador). "
    "Cada día eliges QUÉ publicar en la página de Facebook entre oportunidades ya calculadas con datos reales. "
    "Regla fundamental: cada publicación debe tener un objetivo medible y una razón de negocio; no se publica por publicar. "
    "Solo puedes elegir ids de la lista de candidatas; no inventes oportunidades, cifras, promociones ni lugares. "
    "Respeta la mezcla de audiencias pedida, usa los aprendizajes (insights) y evita repetir lo reciente. "
    "Devuelve SOLO JSON: {\"elegidas\": [{\"id\": \"c3\", \"content_type\": \"post|reel|pregunta|encuesta|educativo|meme\", "
    "\"hora\": \"HH:MM\", \"por_que\": \"1-2 frases: qué comportamiento queremos generar y por qué hoy\"}]}"
)


_ESQUEMA = {
    "type": "object",
    "properties": {"elegidas": {"type": "array", "items": {
        "type": "object",
        "properties": {"id": {"type": "string"}, "content_type": {"type": "string"},
                       "hora": {"type": "string"}, "por_que": {"type": "string"}},
        "required": ["id", "content_type", "hora", "por_que"],
        "additionalProperties": False}}},
    "required": ["elegidas"],
    "additionalProperties": False,
}


def _con_ia(payload: dict) -> dict | None:
    import config
    from . import ia
    return ia.pedir_json(modelo=config.MARKETING_STRATEGY_MODEL, sistema=_SYSTEM, esquema=_ESQUEMA,
                         contenido=json.dumps(payload, ensure_ascii=False, default=str), etiqueta="agente_ia estratega")


def _hora_ok(h) -> str | None:
    m = re.fullmatch(r"([01]?\d|2[0-3]):([0-5]\d)", str(h or "").strip())
    return f"{int(m.group(1)):02d}:{m.group(2)}" if m else None


def validar_ia(resp: dict | None, cands: list[dict], n: int, lista: dict[str, dict] | None = None) -> list[dict] | None:
    """Solo acepta ids existentes, sin duplicar (ni el mismo local dos veces), con tipo y hora válidos."""
    if not isinstance(resp, dict) or not isinstance(resp.get("elegidas"), list):
        return None
    por_id = {c["id"]: c for c in cands}
    out, vistos, clubes, lista = [], set(), set(), lista or {}
    for e in resp["elegidas"]:
        if not isinstance(e, dict):
            continue
        c = por_id.get(str(e.get("id")))
        if not c or c["id"] in vistos or _club_repetido(c, clubes, lista):
            continue
        vistos.add(c["id"])
        tipo = e.get("content_type") if e.get("content_type") in TIPOS_CONTENIDO else c["content_type"]
        if tipo == "reel" and c["content_type"] != "reel":
            tipo = c["content_type"]                     # un reel exige video real; lo decide el creativo
        out.append({**c, "content_type": tipo, "hora": _hora_ok(e.get("hora")) or HORA_DEFECTO.get(c["audiencia"], "12:30"),
                    "por_que": str(e.get("por_que") or c["razon"])[:400]})
    return out[:n] or None


def decidir(s: dict, *, insights: list[dict], recientes: list[dict], n: int = 1, umbral: int = 15,
            mix_duenos_baja: float = 0.7, mix_duenos_alta: float = 0.3, dia_rotacion: int = 0, usar_ia: bool = True,
            cupo_pro: int | None = None, usados_pro: dict[str, int] | None = None) -> dict:
    lista = {c["id"]: c for c in s["canchas_lista"]}
    cands = _sin_pro_agotado(candidatas(s, umbral=umbral, dia_rotacion=dia_rotacion), lista, cupo_pro, usados_pro or {})
    cands = ordenar(cands, insights=insights, recientes=recientes)
    auds = _audiencias_del_dia(n, s, umbral, mix_duenos_baja, mix_duenos_alta, recientes)
    elegidas, fuente = None, "reglas"
    if usar_ia:
        payload = {"snapshot": _d.resumen_para_ia(s), "audiencias_pedidas": auds, "cuantas": n,
                   "candidatas": [{k: c.get(k) for k in ("id", "tipo", "objetivo", "kpi", "audiencia", "razon", "content_type", "puntaje")}
                                  for c in cands[:15]],
                   "insights": [{k: i.get(k) for k in ("enunciado", "dimension", "valor", "efecto", "confianza")} for i in insights[:10]],
                   "recientes": [{k: r.get(k) for k in ("tipo", "audiencia", "zona", "fecha")} for r in recientes[:10]]}
        elegidas = validar_ia(_con_ia(payload), cands, n, lista)
        if elegidas:
            fuente = "ia"
    if not elegidas:
        elegidas = por_reglas(cands, n, auds, lista)
    return {"candidatas": cands, "elegidas": elegidas, "audiencias": auds, "fuente": fuente,
            "baja_densidad": _baja_densidad(s, umbral)}
