"""Lógica de CAMPEONATOS, espejo 1:1 de `lib/models/campeonato.dart`
(`TorneoFixture`, getters de `Campeonato`, `Natacion`) para que la web haga
exactamente lo mismo que el app sobre la MISMA fila `pichangol_campeonatos.data`.

Un campeonato es un dict con las claves de `Campeonato.toJson`. Aquí no hay
clases: se trabaja sobre los dicts tal como viajan a Supabase, y cada función
deja el JSON con las mismas claves (y las mismas omisiones) que escribe el app.
"""

from __future__ import annotations

import re
import time
from datetime import date, datetime

from marketing.campeonato_web import _tabla as tabla  # noqa: F401  (misma tabla que la página pública)

FORMATOS = {"eliminacion": "Eliminación (llave)", "liga": "Liga (tabla)", "grupos": "Grupos + eliminatoria", "tiempos": "Por tiempos (natación)"}
MIN_PARTIDOS = [2, 3]  # opciones de "cada equipo juega al menos N partidos" (formato grupos)
MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "set", "oct", "nov", "dic"]
DISTANCIAS = [25, 50, 100, 200, 400]
ESTILOS = ["Libre", "Espalda", "Pecho", "Mariposa", "Combinado"]


def formato_de(c: dict) -> str:
    """`FormatoTorneoX.desde`: liga / tiempos; cualquier otra cosa = eliminación."""
    f = str(c.get("formato") or "")
    return f if f in ("liga", "tiempos", "grupos") else "eliminacion"


def min_partidos(c: dict) -> int:
    """`Campeonato.minPartidos`: partidos mínimos por equipo en la fase de grupos (2 por defecto)."""
    try:
        v = int(c.get("minPartidos") or 2)
    except (TypeError, ValueError):
        v = 2
    return v if v in MIN_PARTIDOS else 2


def nuevo_id() -> str:
    return f"camp_{int(time.time() * 1_000_000)}"


def nuevo_codigo() -> str:
    """`_nuevoCodigoEquipo` del app: últimos 6 caracteres de los microsegundos en base 36, en mayúsculas."""
    micros = int(time.time() * 1_000_000)
    digitos = "0123456789abcdefghijklmnopqrstuvwxyz"
    s = ""
    while micros:
        micros, r = divmod(micros, 36)
        s = digitos[r] + s
    return s[-6:].upper()


def fmt_rango(a: date, b: date) -> str:
    """`_fmtRango` de `crear_campeonato_screen`."""
    if a == b:
        return f"{a.day} {MESES[a.month - 1]} {a.year}"
    if a.year == b.year and a.month == b.month:
        return f"{a.day}–{b.day} {MESES[a.month - 1]} {a.year}"
    return f"{a.day} {MESES[a.month - 1]} – {b.day} {MESES[b.month - 1]} {b.year}"


def _dt(v) -> datetime | None:
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


# ── Participantes ────────────────────────────────────────────────────────────
def es_equipo(p: dict) -> bool:
    return bool(p.get("capitanEmail") or p.get("codigo"))


def es_menor(p: dict) -> bool:
    return bool(p.get("apoderadoNombre"))


def usa_cupo_equipos(c: dict) -> bool:
    return c.get("deporte") == "futbol" and int(c.get("minJugadoresEquipo") or 0) > 0


def equipo_completo(c: dict, p: dict) -> bool:
    return usa_cupo_equipos(c) and len(p.get("roster") or []) >= int(c.get("minJugadoresEquipo") or 0)


# ── Pozo del equipo (cuota repartida entre el plantel, ver pagos/pozos.py) ──
def max_jugadores(c: dict) -> int:
    """Tope de plantel (titulares + suplentes). 0 = sin tope."""
    return int(c.get("maxJugadoresEquipo") or 0) if c.get("deporte") == "futbol" else 0


def cupo_reparto(c: dict) -> int:
    """Entre cuántos se reparte la cuota del equipo: el máximo; si no hay, el
    mínimo; si no hay ninguno, 0 (= la cuota entera la pone quien crea)."""
    return max_jugadores(c) or int(c.get("minJugadoresEquipo") or 0)


def cuota_equipo_centimos(c: dict) -> int:
    return int(round(float(c.get("costoInscripcion") or 0) * 100))


def cuota_jugador_centimos(c: dict) -> int:
    """`Campeonato.cuotaJugadorCentimos` del app: cuota ÷ cupo, hacia arriba a 0.50."""
    from pagos import pozos
    return pozos.cuota_jugador_centimos(cuota_equipo_centimos(c), cupo_reparto(c))


def equipo_lleno(c: dict, p: dict) -> bool:
    m = max_jugadores(c)
    return m > 0 and len(p.get("roster") or []) >= m


def fmt_monto(centimos: int) -> str:
    v = centimos / 100.0
    return f"{v:.0f}" if abs(v - round(v)) < 0.005 else f"{v:.2f}"


def participante(c: dict, pid) -> dict | None:
    return next((p for p in (c.get("participantes") or []) if p.get("id") == pid), None)


# ── Partidos ─────────────────────────────────────────────────────────────────
def jugado(m: dict) -> bool:
    return m.get("marcadorA") is not None and m.get("marcadorB") is not None


def ganador_id(m: dict):
    """`PartidoTorneo.ganadorId`: jugado → el de mayor marcador (empate = None);
    sin jugar, en la ronda 0 con un solo lado (bye) avanza el presente."""
    if jugado(m):
        a, b = int(m["marcadorA"]), int(m["marcadorB"])
        if a == b:
            return None
        return m.get("aId") if a > b else m.get("bId")
    if int(m.get("ronda") or 0) == 0 and ((m.get("aId") is None) != (m.get("bId") is None)):
        return m.get("aId") if m.get("aId") is not None else m.get("bId")
    return None


def _partido(id_: str, ronda: int, idx: int, a=None, b=None, ma=None, mb=None, fase=None, grupo=None) -> dict:
    d = {"id": id_, "ronda": ronda, "idx": idx}
    if fase:
        d["fase"] = fase
    if grupo:
        d["grupo"] = grupo
    if a is not None:
        d["aId"] = a
    if b is not None:
        d["bId"] = b
    if ma is not None:
        d["marcadorA"] = ma
    if mb is not None:
        d["marcadorB"] = mb
    return d


def _esqueleto_eliminacion(ps: list[dict]) -> list[dict]:
    n = len(ps)
    size = 1
    while size < n:
        size *= 2
    slots = [ps[i]["id"] if i < n else None for i in range(size)]
    todos = [_partido(f"r0_{i}", 0, i, slots[2 * i], slots[2 * i + 1]) for i in range(size // 2)]
    matches, r = size // 2, 1
    while matches > 1:
        matches //= 2
        todos.extend(_partido(f"r{r}_{i}", r, i) for i in range(matches))
        r += 1
    return todos


def recomputar_llave(partidos: list[dict]) -> list[dict]:
    """`TorneoFixture.recomputarLlave`: propaga ganadores/byes a las rondas ≥ 1;
    si el cruce cambió, resetea su marcador."""
    por_ronda: dict[int, list[dict]] = {}
    for p in partidos:
        por_ronda.setdefault(int(p.get("ronda") or 0), []).append(p)
    for lst in por_ronda.values():
        lst.sort(key=lambda x: int(x.get("idx") or 0))
    max_r = max(por_ronda) if por_ronda else 0
    for r in range(1, max_r + 1):
        prev, cur = por_ronda.get(r - 1), por_ronda.get(r)
        if prev is None or cur is None:
            continue
        for i, m in enumerate(cur):
            a = ganador_id(prev[2 * i]) if 2 * i < len(prev) else None
            b = ganador_id(prev[2 * i + 1]) if 2 * i + 1 < len(prev) else None
            mismos = m.get("aId") == a and m.get("bId") == b
            cur[i] = _partido(m["id"], r, i, a, b, m.get("marcadorA") if mismos else None, m.get("marcadorB") if mismos else None,
                              m.get("fase"), m.get("grupo"))
    return [p for r in range(0, max_r + 1) for p in por_ronda.get(r, [])]


def _generar_liga(ps: list[dict]) -> list[dict]:
    lista = [p["id"] for p in ps]
    if len(lista) % 2 == 1:
        lista.append(None)
    n = len(lista)
    jornadas, mitad = n - 1, n // 2
    partidos, arr = [], list(lista)
    for j in range(jornadas):
        idx = 0
        for i in range(mitad):
            a, b = arr[i], arr[n - 1 - i]
            if a is not None and b is not None:
                partidos.append(_partido(f"j{j}_{idx}", j, idx, a, b))
                idx += 1
        fijo, resto = arr[0], arr[1:]
        resto.insert(0, resto.pop())
        arr = [fijo, *resto]
    return partidos


# ── Grupos + eliminatoria (`TorneoFixture` formato `grupos`, sep-2026) ───────
# Pedido del director: "quiero asegurar que al menos cada equipo juegue 2
# partidos a más". Fase de GRUPOS (todos contra todos dentro del grupo, tamaño
# mínimo = minPartidos + 1) y luego LLAVE con los 2 primeros de cada grupo.
LETRAS = "ABCDEFGHIJKLMNOP"


def armar_grupos(n: int, min_partidos: int = 2) -> list[int]:
    """Tamaños de grupo para `n` equipos garantizando `min_partidos` partidos a
    cada uno (grupo de k → k-1 partidos). Prefiere grupos de 4 cuando el
    mínimo es 2 (3 partidos y una llave más pareja); reparte lo más parejo
    posible (tamaños que difieren a lo sumo en 1). Con menos de 3 equipos no
    hay cómo garantizarlo: devuelve [] (se juega solo la final)."""
    tam = max(2, int(min_partidos)) + 1
    if n < 3 or n < tam:
        return []
    g = max(1, n // tam)
    if min_partidos <= 2:
        g = min(g, max(1, int(n / 4 + 0.5)))
    base, extra = divmod(n, g)
    return [base + (1 if i < extra else 0) for i in range(g)]


def _orden_siembra(size: int) -> list[int]:
    """Posiciones de siembra estándar (1 vs size, 2 vs size-1…): [1,8,4,5,2,7,3,6] para 8."""
    seq = [1]
    while len(seq) < size:
        k = len(seq) * 2
        seq = [x for s in seq for x in (s, k + 1 - s)]
    return seq


def _generar_grupos(ps: list[dict], minp: int) -> list[dict]:
    ids = [p["id"] for p in ps]
    tams = armar_grupos(len(ids), minp)
    if not tams:  # menos de 3 → llave directa (una final)
        return recomputar_llave(_esqueleto_eliminacion(ps))
    partidos, pos = [], 0
    for gi, t in enumerate(tams):
        letra = LETRAS[gi]
        miembros = [{"id": i} for i in ids[pos:pos + t]]
        pos += t
        for m in _generar_liga(miembros):
            partidos.append(_partido(f"g{letra}_{m['id']}", m["ronda"], m["idx"], m.get("aId"), m.get("bId"), fase="grupo", grupo=letra))
    # Esqueleto de la llave: clasifican 2 por grupo; potencia de 2 con byes.
    q = 2 * len(tams)
    size = 1
    while size < q:
        size *= 2
    llave = [_partido(f"k0_{i}", 0, i, fase="llave") for i in range(size // 2)]
    matches, r = size // 2, 1
    while matches > 1:
        matches //= 2
        llave.extend(_partido(f"k{r}_{i}", r, i, fase="llave") for i in range(matches))
        r += 1
    return partidos + llave


def partidos_grupo(c: dict) -> list[dict]:
    return [m for m in (c.get("partidos") or []) if m.get("fase") == "grupo"]


def partidos_llave(c: dict) -> list[dict]:
    """La llave: en `grupos` los partidos `fase == 'llave'`; en `eliminacion` todos."""
    if formato_de(c) == "grupos":
        return [m for m in (c.get("partidos") or []) if m.get("fase") == "llave"]
    return list(c.get("partidos") or [])


def grupos_de(c: dict) -> list[str]:
    return sorted({str(m.get("grupo")) for m in partidos_grupo(c) if m.get("grupo")})


def tabla_grupo(c: dict, letra: str) -> list[dict]:
    """Tabla del grupo `letra` (solo sus equipos y sus partidos), ordenada como `tabla`."""
    ms = [m for m in partidos_grupo(c) if m.get("grupo") == letra]
    ids = {m.get("aId") for m in ms} | {m.get("bId") for m in ms}
    sub = {"participantes": [p for p in (c.get("participantes") or []) if p.get("id") in ids], "partidos": ms}
    return tabla(sub)


def grupos_completos(c: dict) -> bool:
    ms = partidos_grupo(c)
    return bool(ms) and all(jugado(m) for m in ms)


def clasificados(c: dict) -> list[dict]:
    """Los 2 primeros de cada grupo con su siembra: primeros ordenados por
    campaña, luego segundos ordenados por campaña. Cada uno: {id, grupo, pos}."""
    primeros, segundos = [], []
    for letra in grupos_de(c):
        t = tabla_grupo(c, letra)
        if t:
            primeros.append((t[0], letra))
        if len(t) > 1:
            segundos.append((t[1], letra))
    llave_campana = lambda x: (-(x[0]["g"] * 3 + x[0]["e"]), -(x[0]["gf"] - x[0]["gc"]), -x[0]["gf"])  # noqa: E731
    primeros.sort(key=llave_campana)
    segundos.sort(key=llave_campana)
    return [{"id": f["id"], "grupo": g, "pos": 1} for f, g in primeros] + [{"id": f["id"], "grupo": g, "pos": 2} for f, g in segundos]


def _sembrar(llave_r0: list[dict], sembrados: list[dict]) -> list[dict]:
    """Rellena la ronda 0 de la llave con la siembra estándar (los mejores
    primeros reciben los byes) evitando, si se puede, que dos del mismo grupo
    se vuelvan a cruzar en la primera ronda."""
    size = len(llave_r0) * 2
    orden = _orden_siembra(size)
    slots = [sembrados[o - 1] if o - 1 < len(sembrados) else None for o in orden]
    pares = [[slots[2 * i], slots[2 * i + 1]] for i in range(len(llave_r0))]
    for i, (a, b) in enumerate(pares):
        if a and b and a["grupo"] == b["grupo"]:
            for j, (c2, d2) in enumerate(pares):
                if j == i or not c2 or not d2:
                    continue
                # intercambia los segundos (pos 2) entre cruces
                if b["pos"] == 2 and d2["pos"] == 2 and d2["grupo"] != a["grupo"] and b["grupo"] != c2["grupo"]:
                    pares[i][1], pares[j][1] = d2, b
                    break
    out = []
    for i, m in enumerate(sorted(llave_r0, key=lambda x: int(x.get("idx") or 0))):
        a, b = pares[i]
        out.append(_partido(m["id"], 0, i, a["id"] if a else None, b["id"] if b else None, fase="llave"))
    return out


def recomputar_grupos(c: dict, partidos: list[dict]) -> list[dict]:
    """Con la fase de grupos completa siembra la llave (una sola vez: mientras
    ningún partido de llave tenga resultado) y propaga ganadores/byes."""
    grupo = [m for m in partidos if m.get("fase") == "grupo"]
    llave = [m for m in partidos if m.get("fase") == "llave"]
    if not llave:
        return partidos
    tmp = {"participantes": c.get("participantes") or [], "partidos": grupo, "formato": "grupos"}
    completo = grupos_completos(tmp)
    r0 = [m for m in llave if int(m.get("ronda") or 0) == 0]
    resto = [m for m in llave if int(m.get("ronda") or 0) != 0]
    if not any(jugado(m) for m in llave):
        if completo:
            r0 = _sembrar(r0, clasificados(tmp))
        else:
            r0 = [_partido(m["id"], 0, int(m.get("idx") or 0), fase="llave") for m in r0]
    return grupo + recomputar_llave(r0 + resto)


def generar_fixture(c: dict) -> list[dict]:
    """`TorneoFixture.generar`: ≥ 2 participantes; liga → círculo; grupos →
    fase de grupos + llave (garantiza `minPartidos`); si no → llave."""
    ps = [p for p in (c.get("participantes") or []) if p.get("id")]
    if len(ps) < 2:
        return []
    fmt = formato_de(c)
    if fmt == "liga":
        return _generar_liga(ps)
    if fmt == "grupos":
        return _generar_grupos(ps, min_partidos(c))
    return recomputar_llave(_esqueleto_eliminacion(ps))


def es_partido_llave(c: dict, m: dict) -> bool:
    """¿Este partido es de eliminación directa (no admite empate)?"""
    fmt = formato_de(c)
    return fmt == "eliminacion" or (fmt == "grupos" and m.get("fase") == "llave")


def partidos_de(c: dict, pid: str) -> int:
    """Cuántos partidos con rival definido tiene el participante (para verificar el mínimo)."""
    return sum(1 for m in (c.get("partidos") or []) if pid in (m.get("aId"), m.get("bId")) and m.get("aId") and m.get("bId"))


def set_resultado(c: dict, partido_id: str, a: int, b: int) -> bool:
    """`AppState.setResultado`: pone el marcador y, en llave, recomputa los cruces."""
    partidos = list(c.get("partidos") or [])
    for i, m in enumerate(partidos):
        if m.get("id") == partido_id:
            partidos[i] = _partido(m["id"], int(m.get("ronda") or 0), int(m.get("idx") or 0), m.get("aId"), m.get("bId"), int(a), int(b),
                                   m.get("fase"), m.get("grupo"))
            break
    else:
        return False
    fmt = formato_de(c)
    if fmt == "grupos":
        c["partidos"] = recomputar_grupos(c, partidos)
    elif fmt == "liga":
        c["partidos"] = partidos
    else:
        c["partidos"] = recomputar_llave(partidos)
    return True


# ── Estado del torneo (getters de `Campeonato`) ──────────────────────────────
def fixture_generado(c: dict) -> bool:
    return bool(c.get("partidos"))


def inscripcion_vencida(c: dict) -> bool:
    h = _dt(c.get("inscripcionHasta"))
    return h is not None and datetime.now() > h


def terminado(c: dict) -> bool:
    if c.get("cerrado"):
        return True
    partidos = c.get("partidos") or []
    if not partidos:
        return False
    if formato_de(c) == "liga":
        return all(jugado(m) or m.get("aId") is None or m.get("bId") is None for m in partidos)
    llave = partidos_llave(c)
    if not llave:
        return False
    max_r = max(int(p.get("ronda") or 0) for p in llave)
    fin = [p for p in llave if int(p.get("ronda") or 0) == max_r]
    return len(fin) == 1 and ganador_id(fin[0]) is not None


def campeon_y_subcampeon(c: dict) -> tuple[str | None, str | None]:
    """Ids de campeón y subcampeón (liga: 1.º y 2.º de la tabla; llave: final)."""
    partidos = c.get("partidos") or []
    if not partidos:
        return None, None
    if formato_de(c) == "liga":
        t = tabla(c)
        ids = [p["id"] for p in (c.get("participantes") or [])]
        # `tabla` devuelve filas sin id: se reconstruye por nombre en orden.
        nombres = {p.get("nombre"): p["id"] for p in (c.get("participantes") or [])}
        camp = nombres.get(t[0]["nombre"]) if t else None
        sub = nombres.get(t[1]["nombre"]) if len(t) > 1 else None
        return (camp if camp in ids else None), (sub if sub in ids else None)
    llave = partidos_llave(c)
    if not llave:
        return None, None
    max_r = max(int(p.get("ronda") or 0) for p in llave)
    fin = [p for p in llave if int(p.get("ronda") or 0) == max_r]
    if len(fin) != 1 or not jugado(fin[0]):
        return None, None
    g = ganador_id(fin[0])
    if g is None:
        return None, None
    f = fin[0]
    return g, (f.get("bId") if g == f.get("aId") else f.get("aId"))


def estado(c: dict) -> tuple[str, str, str]:
    """Pill `_EstadoCampeonato`: (clave, emoji+texto, color)."""
    if c.get("cerrado"):
        return "finalizado", "🏁 Finalizado", "teal"
    en_juego = bool(c.get("pruebas")) if formato_de(c) == "tiempos" else fixture_generado(c)
    if en_juego:
        return "en_juego", "🏆 En juego", "morado"
    if inscripcion_vencida(c):
        return "vencida", "⏳ Inscripciones cerradas · esperando " + ("pruebas" if formato_de(c) == "tiempos" else "fixture"), "naranja"
    return "abierta", "📝 Inscripciones abiertas", "lima"


def etiqueta_ronda(ronda: int, max_ronda: int) -> str:
    return {0: "Final", 1: "Semifinal", 2: "Cuartos de final", 3: "Octavos de final"}.get(max_ronda - ronda, f"Ronda {ronda + 1}")


# ── Natación (`Natacion`) ────────────────────────────────────────────────────
def fmt_tiempo(cc: int) -> str:
    """`Natacion.fmt`: m:ss.cc, '—' si ≤ 0."""
    cc = int(cc or 0)
    if cc <= 0:
        return "—"
    m, r = divmod(cc, 6000)
    s, c = divmod(r, 100)
    return f"{m}:{s:02d}.{c:02d}"


def parse_tiempo(texto: str) -> int | None:
    """`Natacion.parse`: mm:ss.cc, ss.cc o ss (coma o punto); segundos 0-59; 1 dígito de cc = ×10."""
    t = (texto or "").strip().replace(",", ".")
    if not t:
        return None
    m = re.match(r"^(?:(\d{1,3}):)?(\d{1,2})(?:\.(\d{1,2}))?$", t)
    if not m:
        return None
    minutos = int(m.group(1) or 0)
    seg = int(m.group(2))
    if seg > 59:
        return None
    frac = m.group(3) or "0"
    cent = int(frac) * 10 if len(frac) == 1 else int(frac)
    return minutos * 6000 + seg * 100 + cent


def marca_registrada(m: dict) -> bool:
    return int(m.get("centesimas") or 0) > 0 or bool(m.get("dsq"))


def ranking_prueba(p: dict) -> list[dict]:
    """`Natacion.ranking`: con tiempo ascendente, luego DSQ; sin registrar fuera."""
    marcas = [m for m in (p.get("marcas") or []) if marca_registrada(m)]
    con = sorted((m for m in marcas if not m.get("dsq")), key=lambda m: int(m.get("centesimas") or 0))
    return con + [m for m in marcas if m.get("dsq")]


def marca_json(participante_id: str, centesimas: int = 0, serie: int = 0, carril: int = 0, dsq: bool = False) -> dict:
    d = {"participanteId": participante_id, "centesimas": int(centesimas or 0)}
    if serie:
        d["serie"] = int(serie)
    if carril:
        d["carril"] = int(carril)
    if dsq:
        d["dsq"] = True
    return d


# ── Ranking de academia (`importarCampeonatoAlRanking`) ──────────────────────
def importar_al_ranking(c: dict, academia: dict) -> tuple[dict, int]:
    """Convierte los partidos JUGADOS con ganador en `PartidoRanking` de la
    academia (id `cmp_<camp>_<partido>`, conserva la fecha de los ya importados)
    y devuelve (academia actualizada, cuántos partidos)."""
    prefijo = f"cmp_{c.get('id')}_"
    previos = {p.get("id"): p.get("fecha") for p in (academia.get("partidos") or []) if str(p.get("id") or "").startswith(prefijo)}
    part = {p.get("id"): p for p in (c.get("participantes") or [])}
    ahora = datetime.now().isoformat(timespec="microseconds")
    nuevos, cats = [], dict(academia.get("categorias") or {})
    for pt in c.get("partidos") or []:
        if not jugado(pt):
            continue
        a, b, g = pt.get("aId"), pt.get("bId"), ganador_id(pt)
        if a is None or b is None or g is None:
            continue
        pa, pb = part.get(a), part.get(b)
        if pa is None or pb is None:
            continue
        pid = f"{prefijo}{pt.get('id')}"
        d = {"id": pid, "fecha": previos.get(pid) or ahora, "jugadorAId": a, "jugadorANombre": pa.get("nombre", ""),
             "jugadorBId": b, "jugadorBNombre": pb.get("nombre", "")}
        if (pa.get("email") or "").strip():
            d["jugadorAEmail"] = pa["email"].strip().lower()
        if (pb.get("email") or "").strip():
            d["jugadorBEmail"] = pb["email"].strip().lower()
        d.update({"marcador": f"{pt['marcadorA']}-{pt['marcadorB']}", "ganadorId": g, "sedeId": ""})
        nuevos.append(d)
        if c.get("categoria"):
            cats.setdefault(a, c["categoria"])
            cats.setdefault(b, c["categoria"])
    resto = [p for p in (academia.get("partidos") or []) if not str(p.get("id") or "").startswith(prefijo)]
    out = dict(academia)
    out["partidos"] = resto + nuevos
    out["categorias"] = cats
    return out, len(nuevos)
