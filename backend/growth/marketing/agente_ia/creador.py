"""CONTENT CREATOR: copy de la pieza a partir de UNA oportunidad y sus hechos.

* La IA recibe SOLO los `hechos` de la oportunidad y escribe título, subtítulo,
  etiqueta, texto y llamado a la acción. Los hashtags y el enlace los pone el
  código (no se le deja inventar una zona en un hashtag ni un link).
* Cada versión pasa por `guardrails.validar`; si falla, se le devuelven los
  errores a la IA para una segunda versión; si vuelve a fallar (o no hay IA),
  se usa el banco de plantillas, escrito para pasar los guardrails con
  cualquier conjunto de hechos.
"""
from __future__ import annotations

import json
import random
import re

from marketing.agente_ia import guardrails, zonas

CTA = {
    "jugadores": "Reserva en la web o descarga la app Pichangol",
    "duenos": "Registra tu cancha en Modo anfitrión",
}
TONOS = {"cercano": "cercano y natural, como un amigo que juega", "divertido": "divertido y con chispa, sin payasadas",
         "informativo": "claro, directo y útil", "motivador": "motivador y energético, sin gritar"}
_PAIS = {"PE": "Perú", "BO": "Bolivia", "EC": "Ecuador"}
_TAG_DEP = {"fútbol": "futbol", "pádel": "padel", "vóley": "voley", "básquet": "basquet", "natación": "natacion"}

_SYSTEM = (
    "Escribes las publicaciones de la página de Facebook/Instagram de Pichangol, una app (Android y web www.pichangol.app) "
    "para reservar canchas y armar partidos, presente en Perú, Bolivia y Ecuador. Español latinoamericano natural "
    "(del país indicado), como una persona, no como una marca gritando.\n"
    "REGLAS ESTRICTAS:\n"
    "1. Usa SOLO los datos del objeto `hechos`. No inventes precios, porcentajes, cifras, horarios, nombres de locales, "
    "zonas, promociones, testimonios ni resultados. Si un dato no está, no lo menciones.\n"
    "2. Ningún número que no esté en `hechos` (ni siquiera '1 minuto' o 'fútbol 7').\n"
    "3. Solo nombra un local si viene en hechos.cancha o hechos.canchas. Solo nombra la zona de hechos.zona.\n"
    "4. No digas 'gratis' salvo que hechos.registro_gratis sea true. No hables de promos/descuentos sin hechos.promo.\n"
    "5. No afirmes que hay turnos/canchas libres salvo que hechos.dia exista.\n"
    "6. Moneda y jerga del país (nada de Yape, Plin ni soles fuera de Perú).\n"
    "7. Sonar DISTINTO a las publicaciones recientes que te paso (otro gancho, otra primera frase).\n"
    "8. De 0 a 3 emojis. Sin hashtags ni enlaces (los agrega el sistema). Sin comillas alrededor.\n"
    "9. El objetivo de la pieza manda: escribe para provocar ESE comportamiento.\n"
    "Devuelve SOLO JSON: {\"titulo\": \"<= 36 caracteres, va sobre la imagen, sin emoji\", \"subtitulo\": \"<= 80 caracteres\", "
    "\"etiqueta\": \"<= 14 caracteres o vacío\", \"texto\": \"cuerpo del post, 200 a 600 caracteres, con saltos de línea\", "
    "\"cta\": \"llamado a la acción corto\"}"
)


def _limpiar(v, tope: int) -> str:
    t = re.sub(r"[ \t]+", " ", str(v or "")).strip().strip('"“”')
    return t[:tope].rstrip()


def hashtags(op: dict) -> list[str]:
    h = op.get("hechos") or {}
    tags = ["#pichangol"]
    deps = [d for c in [h.get("cancha")] + list(h.get("canchas") or []) if c for d in c.get("deportes") or []]
    if deps:
        tags.append("#" + zonas.norm(_TAG_DEP.get(deps[0], deps[0])).replace(" ", ""))
    if h.get("zona"):
        tags.append("#" + zonas.norm(h["zona"]).replace(" ", ""))
    tags.append("#reservajuegarepite" if op["audiencia"] == "jugadores" else "#duenosdecanchas")
    return list(dict.fromkeys(tags))[:6]


def componer_cuerpo(texto: str, cta: str, link: str, tags: list[str]) -> str:
    partes = [texto.strip()]
    if cta or link:
        partes.append(f"{cta.strip().rstrip('.:')}: {link}" if link else cta.strip())
    if tags:
        partes.append(" ".join(tags))
    return "\n\n".join(p for p in partes if p)


# ── banco de plantillas (sin IA) ──────────────────────────────────────────────
def _banco(op: dict) -> list[dict]:
    h = op.get("hechos") or {}
    z = h.get("zona") or ""
    dia, franja = h.get("dia") or "", h.get("franja") or ""
    c = h.get("cancha") or {}
    loc = c.get("nombre") or ""
    tipo = op["tipo"]
    if tipo == "huecos_zona":
        n = h.get("canchas_con_turnos")
        return [
            {"titulo": f"¿Pichanga el {dia}?", "subtitulo": f"Hay turnos libres en {z} por la {franja}", "etiqueta": "Esta semana",
             "texto": f"Si el grupo anda con ganas, este {dia} por la {franja} hay turnos libres en {n} canchas de {z}.\n\n"
                      f"Mira los horarios, elige el tuyo y llega directo a jugar."},
            {"titulo": f"{z}: cancha para el {dia}", "subtitulo": f"Turnos libres por la {franja}", "etiqueta": "",
             "texto": f"¿Ya armaron el partido del {dia}? En {z} todavía hay turnos libres por la {franja}.\n\n"
                      f"Reserva en un toque y deja de perseguir al que nunca confirma."},
        ]
    if tipo == "cancha_destacada":
        precio = f" desde {c['moneda']} {c['precio_hora']:g} la hora" if c.get("precio_hora") else ""
        return [
            {"titulo": loc[:36], "subtitulo": f"Turnos libres el {dia} por la {franja}", "etiqueta": "Destacado",
             "texto": f"{loc}{(' en ' + z) if z else ''} tiene turnos libres este {dia} por la {franja}{precio}.\n\n"
                      f"Elige tu hora y confirma al instante."},
            {"titulo": f"{z or loc}: turnos este {dia}"[:36], "subtitulo": f"{loc} por la {franja}"[:80], "etiqueta": "",
             "texto": f"¿Buscando dónde jugar este {dia}? En {loc} quedan turnos libres por la {franja}{precio}.\n\n"
                      f"Reserva desde el celular y llega directo a la cancha."},
        ]
    if tipo == "promo_real":
        p = h.get("promo") or {}
        if p.get("tipo") == "hora_feliz":
            franja_txt = f"de {p['desde']} a {p['hasta']}"
        else:
            franja_txt = f"el {p.get('dia', '')}"
        return [
            {"titulo": f"{p.get('pct')}% en {loc}"[:36], "subtitulo": f"Hora feliz {franja_txt}" if p.get("tipo") == "hora_feliz" else "Descuento en turnos seleccionados",
             "etiqueta": "Promo",
             "texto": f"{loc}{(' en ' + z) if z else ''} tiene {p.get('pct')}% de descuento {franja_txt}.\n\n"
                      f"Reserva por Pichangol y el descuento se aplica solo."},
            {"titulo": f"Promo en {loc}"[:36], "subtitulo": f"{p.get('pct')}% de descuento", "etiqueta": "Promo",
             "texto": f"Dato para tu próximo partido: {loc} tiene {p.get('pct')}% de descuento {franja_txt}.\n\n"
                      f"Aparta tu turno en Pichangol antes de que se llene."},
        ]
    if tipo == "promo_zona":
        return [
            {"titulo": f"Hora feliz en {z}"[:36], "subtitulo": f"Hasta {h.get('pct_max')}% en canchas de la zona", "etiqueta": "Promo",
             "texto": f"Hay {h.get('canchas_con_promo')} canchas de {z} con hora feliz: hasta {h.get('pct_max')}% de descuento en sus horarios valle.\n\n"
                      f"Búscalas en el mapa de Pichangol y arma el partido."},
            {"titulo": f"{z}: juega con descuento"[:36], "subtitulo": f"{h.get('canchas_con_promo')} canchas con hora feliz", "etiqueta": "Promo",
             "texto": f"Si juegas en {z}, mira esto: {h.get('canchas_con_promo')} canchas tienen hora feliz con hasta {h.get('pct_max')}% de descuento.\n\n"
                      f"Elige la tuya en Pichangol y reserva en un toque."},
        ]
    if tipo == "canchas_nuevas":
        return [
            {"titulo": f"Nuevas canchas en {z}"[:36], "subtitulo": "Ya se reservan en Pichangol", "etiqueta": "Nuevo",
             "texto": f"Sumamos {h.get('canchas_nuevas')} cancha(s) en {z} que ya puedes reservar desde Pichangol.\n\n"
                      f"Mira horarios en vivo y confirma sin llamadas."},
            {"titulo": f"{z} suma canchas"[:36], "subtitulo": "Nuevas opciones para tu partido", "etiqueta": "Nuevo",
             "texto": f"Más opciones para jugar en {z}: {h.get('canchas_nuevas')} cancha(s) nueva(s) ya están en Pichangol.\n\n"
                      f"Entra, mira sus horarios y arma el partido."},
        ]
    if tipo == "captar_duenos_zona":
        return [
            {"titulo": f"Dueños de canchas en {z}"[:36], "subtitulo": "Tu cancha ya está en el mapa: reclámala", "etiqueta": "Para dueños",
             "texto": f"En {z} hay {h.get('canchas_sin_dueno')} canchas que los jugadores ya ven en el mapa de Pichangol, pero sin su dueño.\n\n"
                      f"Si una es tuya, regístrala gratis: recibes reservas, cobras en línea y ordenas tu agenda."},
            {"titulo": f"¿Tienes cancha en {z}?"[:36], "subtitulo": "Los jugadores ya la buscan en el mapa", "etiqueta": "Para dueños",
             "texto": f"Hay {h.get('canchas_sin_dueno')} canchas de {z} que ya aparecen en Pichangol esperando a su dueño.\n\n"
                      f"Reclama la tuya gratis y empieza a recibir reservas con cobro en línea."},
        ]
    if tipo == "demanda_zona":
        return [
            {"titulo": f"Buscan cancha en {z}"[:36], "subtitulo": "Jugadores lo están pidiendo en la app", "etiqueta": "Para dueños",
             "texto": f"{h.get('solicitudes_jugadores')} jugadores pidieron canchas en {z} desde Pichangol.\n\n"
                      f"Si tienes una, regístrala gratis y empieza a recibir esas reservas."},
            {"titulo": f"{z} quiere jugar"[:36], "subtitulo": "La demanda ya está, falta tu cancha", "etiqueta": "Para dueños",
             "texto": f"Desde la app, {h.get('solicitudes_jugadores')} jugadores pidieron canchas en {z}.\n\n"
                      f"Si administras una, publícala gratis en Pichangol y recibe esas reservas."},
        ]
    if tipo == "comunidad":
        return [
            {"titulo": "¿Te falta uno para la pichanga?", "subtitulo": "Hay partidos buscando jugadores", "etiqueta": "Comunidad",
             "texto": f"Ahora mismo hay {h.get('partidos_abiertos')} partidos abiertos en Pichangol buscando jugadores.\n\n"
                      f"Cuéntanos: ¿qué posición juegas y quién es el que siempre llega tarde?"},
            {"titulo": "Partidos buscando jugadores", "subtitulo": "Súmate a una pichanga", "etiqueta": "Comunidad",
             "texto": f"¿Sin equipo esta semana? Hay {h.get('partidos_abiertos')} partidos abiertos en Pichangol que necesitan gente.\n\n"
                      f"Comenta tu deporte favorito y entra a sumarte."},
        ]
    if tipo == "duenos_beneficios":
        return [
            {"titulo": "Tu cancha, siempre llena", "subtitulo": "Agenda, cobros y reservas en un solo lugar", "etiqueta": "Para dueños",
             "texto": "¿Sigues anotando reservas en un cuaderno y respondiendo mensajes a medianoche?\n\n"
                      "Con Pichangol publicas tu cancha gratis, recibes reservas con confirmación y cobras en línea."},
            {"titulo": "Horas vacías, a llenarlas", "subtitulo": "Jugadores nuevos buscando dónde jugar", "etiqueta": "Para dueños",
             "texto": "Cada hora sin jugar es plata que no vuelve. En Pichangol los jugadores ven tu cancha en el mapa y reservan solos.\n\n"
                      "El registro es gratis y te acompañamos a activarla."},
        ]
    # marca_jugadores
    enfoque = op.get("enfoque") or "beneficio"
    return {
        "tip": [{"titulo": "Calienta antes de jugar", "subtitulo": "Tu rodilla te lo va a agradecer", "etiqueta": "Tip",
                 "texto": "Antes del partido: trote suave, movilidad de cadera y tobillos, y unos piques cortos.\n\n"
                          "Llegas suelto, juegas mejor y te evitas el tirón del segundo tiempo."}],
        "humor": [{"titulo": "Siempre hay uno así", "subtitulo": "El que confirma y no llega", "etiqueta": "",
                   "texto": "Todos tenemos en el grupo al que dice 'ya estoy saliendo' desde la ducha.\n\n"
                            "Etiquétalo y que esta vez llegue: la cancha ya la reservaste tú."}],
        "historia": [{"titulo": "Hecha para jugar más", "subtitulo": "Reservar cancha sin complicarse", "etiqueta": "",
                      "texto": "Pichangol nació de una pregunta simple: ¿por qué conseguir cancha es más difícil que jugar?\n\n"
                               "Por eso puedes ver horarios, reservar y armar tu partido desde el celular."}],
        "comunidad": [{"titulo": "¿Con quién juegas hoy?", "subtitulo": "Arma el partido con tu grupo", "etiqueta": "",
                       "texto": "Cuéntanos en los comentarios: ¿cuál es tu deporte y cuál es tu horario favorito para jugar?\n\n"
                                "En Pichangol encuentras cancha y gente con quien armarlo."}],
    }.get(enfoque, [{"titulo": "Reserva sin llamar", "subtitulo": "Horarios a la vista, confirmación al instante", "etiqueta": "",
                     "texto": "Olvídate de llamar a preguntar si hay cancha. En Pichangol ves los horarios, eliges y confirmas.\n\n"
                              "Así de simple para organizar la próxima pichanga."}])


# ── IA ───────────────────────────────────────────────────────────────────────
_ESQUEMA = {
    "type": "object",
    "properties": {k: {"type": "string"} for k in ("titulo", "subtitulo", "etiqueta", "texto", "cta")},
    "required": ["titulo", "subtitulo", "etiqueta", "texto", "cta"],
    "additionalProperties": False,
}


def _con_ia(payload: dict) -> dict | None:
    import config
    from . import ia
    d = ia.pedir_json(modelo=config.MARKETING_COPY_MODEL, sistema=_SYSTEM, esquema=_ESQUEMA,
                      contenido=json.dumps(payload, ensure_ascii=False, default=str), etiqueta="agente_ia creador")
    return d if isinstance(d, dict) and str(d.get("texto") or "").strip() else None


def _a_pieza(d: dict, op: dict, link: str) -> dict:
    tags = hashtags(op)
    cta = _limpiar(d.get("cta"), 90) or CTA[op["audiencia"]]
    texto = _limpiar(d.get("texto"), 1500)
    return {"title": _limpiar(d.get("titulo"), 36), "subtitle": _limpiar(d.get("subtitulo"), 80), "etiqueta": _limpiar(d.get("etiqueta"), 14),
            "texto": texto, "call_to_action": cta, "hashtags": tags, "body": componer_cuerpo(texto, cta, link, tags)}


def redactar(op: dict, *, link: str, tono: str = "cercano", plataforma: str = "facebook", recientes: list[str] | None = None,
             locales_pais: list[str] | None = None, media_origen: str | None = None, usar_ia: bool = True,
             semilla: int | None = None) -> dict:
    """Devuelve la pieza + `validacion` + `fuente` ('ia' | 'banco')."""
    from marketing.agente_redes import AUDIENCIAS
    hechos = op.get("hechos") or {}
    recientes = recientes or []

    def _validar(p: dict) -> dict:
        return guardrails.validar(p, hechos, oportunidad=op, media_origen=media_origen, recientes=recientes, locales_pais=locales_pais,
                                  link=link)

    intentos = []
    if usar_ia:
        payload = {"plataforma": plataforma, "formato": op.get("content_type"), "pais": _PAIS.get(hechos.get("pais"), "Perú"),
                   "audiencia": op["audiencia"], "objetivo_comercial": AUDIENCIAS[op["audiencia"]]["objetivo"],
                   "objetivo_de_la_pieza": op["objetivo"], "kpi": op["kpi"], "por_que": op.get("por_que") or op.get("razon"),
                   "enfoque": op.get("enfoque"), "tono": TONOS.get(tono, TONOS["cercano"]), "hechos": hechos,
                   "recientes": [next((l for l in r.splitlines() if l.strip()), "")[:140] for r in recientes[:12]]}
        for _ in range(2):
            d = _con_ia(payload)
            if not d:
                break
            p = _a_pieza(d, op, link)
            v = _validar(p)
            intentos.append(v["errores"])
            if v["ok"]:
                return {**p, "validacion": {**v, "intentos_ia": intentos}, "fuente": "ia"}
            payload["errores_version_anterior"] = v["errores"]
    banco = _banco(op)
    rnd = random.Random(semilla)
    rnd.shuffle(banco)
    ultimo = None
    for d in banco:
        p = _a_pieza({**d, "cta": CTA[op["audiencia"]]}, op, link)
        v = _validar(p)
        ultimo = (p, v)
        if v["ok"]:
            return {**p, "validacion": {**v, "intentos_ia": intentos}, "fuente": "banco"}
    p, v = ultimo
    return {**p, "validacion": {**v, "intentos_ia": intentos}, "fuente": "banco"}
