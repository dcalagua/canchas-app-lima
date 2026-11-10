"""DATA COLLECTOR del AI Marketing Agent.

Lee los datos REALES de Pichangol y arma un `snapshot` de AGREGADOS para el
estratega. Reglas:

* Nada de PII: no salen correos, teléfonos, DNI, nombres de jugadores ni
  coordenadas de usuarios. Las canchas sí van con su nombre/club (son públicas
  en el mapa) y el correo del dueño solo se usa aquí para saber si tiene Pro.
* Nada inventado: la zona sale de `zonas.zona_de` (o no hay zona), la ocupación
  de reservas + bloqueos reales sobre el horario publicado de cada cancha, las
  promos de las columnas/tablas donde viven, con su vigencia.

Dos capas para poder probarlo sin base: `cargar_crudo()` (SQL + snapshot del
growth) y `construir_snapshot(crudo, ...)` (puro).
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import date, datetime, timedelta

from marketing.agente_ia import zonas

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
FRANJAS = {"mañana": (6, 12), "tarde": (12, 18), "noche": (18, 24)}
VENTANA_HISTORIA_DIAS = 28
VENTANA_FUTURO_DIAS = 7
NUEVA_DIAS = 14
DEDUP_LEAD_M = 120          # una cancha descubierta a < 120 m de una registrada es la misma


def _hhmm(s: str | None, defecto: int | None = None) -> int | None:
    """'07:30' → 450 (minutos). None/ inválido → defecto."""
    try:
        h, m = str(s or "").strip()[:5].split(":")
        v = int(h) * 60 + int(m)
        return 24 * 60 if v == 0 and defecto == 24 * 60 else v
    except (ValueError, AttributeError):
        return defecto


def franja_de(minuto: int) -> str:
    h = minuto // 60
    for nombre, (a, b) in FRANJAS.items():
        if a <= h < b:
            return nombre
    return "noche" if h >= 18 else "mañana"


def _dist_m(lat1, lng1, lat2, lng2) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _pais(c: dict) -> str:
    from paises import pais_de_coordenadas
    if c.get("lat") is None or c.get("lng") is None:
        return "PE"
    try:
        return pais_de_coordenadas(float(c["lat"]), float(c["lng"])) or "PE"
    except (TypeError, ValueError):
        return "PE"


def _simbolo(c: dict, iso: str) -> str:
    m = str(c.get("moneda") or "").strip()
    if m in ("S/", "Bs", "$"):
        return m
    return {"PE": "S/", "BO": "Bs", "EC": "$"}.get(iso, "S/")


def _slots(c: dict) -> list[int]:
    """Inicios de turno (minutos) según el horario publicado de la cancha."""
    ap = _hhmm(c.get("hora_apertura"), 7 * 60)
    ci = _hhmm(c.get("hora_cierre"), 23 * 60)
    if ci is None or ap is None:
        return []
    if ci <= ap:                         # cierra a medianoche (00:00) o después
        ci = 24 * 60
    paso = int(c.get("duracion_slot_min") or 60) or 60
    paso = max(30, min(paso, 180))
    out, t = [], ap
    while t + paso <= ci:
        out.append(t)
        t += paso
    return out


# ── carga desde la base y el snapshot del growth ─────────────────────────────
def cargar_crudo(hoy: date) -> dict:
    """Todas las filas que necesita el snapshot. Fail-safe: lo que no se pueda
    leer queda vacío (y el estratega simplemente no verá esa oportunidad)."""
    from db import pg
    from db.store import stores
    crudo: dict = {"canchas": [], "reservas": [], "bloqueos": [], "descuentos": [], "bonos": [],
                   "descubiertas": [], "partidos": [], "solicitudes": [], "verificaciones": {}, "convocatorias": 0}
    desde = (hoy - timedelta(days=VENTANA_HISTORIA_DIAS)).isoformat()
    hasta = (hoy + timedelta(days=VENTANA_FUTURO_DIAS)).isoformat()
    consultas = {
        "canchas": ("SELECT id, nombre, club, distrito, barrio, direccion, deporte, deportes, precio_hora, precio_turno, moneda, "
                    "lat, lng, verificada, dueno, foto_url, fotos, hora_apertura, hora_cierre, duracion_slot_min, "
                    "descuento_valle, valle_desde, valle_hasta FROM pichangol_canchas "
                    "WHERE coalesce(registrada,true) AND NOT coalesce(eliminada,false)", ()),
        "reservas": ("SELECT cancha_id, fecha, hora_inicio, hora_fin, estado FROM pichangol_reservas "
                     "WHERE fecha >= %s AND fecha <= %s AND coalesce(estado,'') <> 'cancelada'", (desde, hasta)),
        "bloqueos": ("SELECT cancha_id, fecha, hora FROM pichangol_bloqueos WHERE fecha >= %s AND fecha <= %s", (desde, hasta)),
        "descuentos": ("SELECT cancha_id, fecha, hora, pct FROM pichangol_descuentos_slot WHERE fecha >= %s AND fecha <= %s AND pct > 0",
                       (hoy.isoformat(), hasta)),
        "bonos": ("SELECT id, dueno, club, nombre, horas, precio FROM pichangol_bonos WHERE coalesce(activo,false)", ()),
        "descubiertas": ("SELECT id, nombre, direccion, lat, lng, deporte FROM pichangol_canchas_cache", ()),
        "partidos": ("SELECT deporte, fecha, lat, lng, cancha_id FROM pichangol_partidos WHERE fecha >= %s", (hoy.isoformat(),)),
    }
    if pg.habilitado:
        for clave, (sql, params) in consultas.items():
            try:
                with pg.conexion() as conn, conn.cursor() as cur:
                    cur.execute(sql, params)
                    cols = [d.name for d in cur.description]
                    crudo[clave] = [dict(zip(cols, f)) for f in cur.fetchall()]
            except Exception as e:  # noqa: BLE001
                print(f"[agente_ia] collector: no se pudo leer {clave}: {str(e)[:120]}", flush=True)
    # Del snapshot del growth: cuándo se ACTIVÓ cada cancha (aprobación del
    # reclamo), lo que piden los jugadores ("pide tu cancha") y pichangas abiertas.
    try:
        for r in stores.reclamos:
            if r.estado == "activada" and r.decidido_en:
                previo = crudo["verificaciones"].get(r.cancha_id)
                f = r.decidido_en.date() if isinstance(r.decidido_en, datetime) else None
                if f and (previo is None or f > previo):
                    crudo["verificaciones"][r.cancha_id] = f
        crudo["solicitudes"] = [{"zona": s.zona, "distrito": s.distrito, "direccion": s.direccion_texto, "estado": s.estado,
                                 "creado": s.creado_en} for s in stores.solicitudes]
        crudo["convocatorias"] = sum(1 for c in stores.convocatorias if c.estado == "abierta")
    except Exception:  # noqa: BLE001
        pass
    return crudo


# ── snapshot puro ─────────────────────────────────────────────────────────────
def _destacable(c: dict, pro_activo, destacar_pro: bool) -> bool:
    """Regla del director (24-sep-2026): un local solo se nombra en la publicidad
    de la marca si su dueño tiene Pichangol Pro y la torre activó 'destacar Pro'."""
    return bool(destacar_pro and c.get("verificada") and (c.get("dueno") or "").strip()
                and pro_activo(str(c.get("dueno") or "").strip().lower()))


def _fotos_propias(c: dict) -> list[str]:
    """Fotos subidas al bucket propio (las de Google no son 'propias')."""
    urls = [c.get("foto_url")] + list(c.get("fotos") or [])
    return list(dict.fromkeys(u for u in urls if isinstance(u, str) and u.startswith("https://") and "/storage/v1/object/" in u))


def construir_snapshot(crudo: dict, *, pais: str, hoy: date, ahora_min: int, pro_activo=lambda _e: False,
                       destacar_pro: bool = False) -> dict:
    """Agregados por zona/franja para el estratega. `ahora_min` = minuto local
    actual (para no ofrecer horas de hoy que ya pasaron)."""
    canchas = []
    for c in crudo.get("canchas") or []:
        iso = _pais(c)
        if iso != pais:
            continue
        reservable = bool(c.get("verificada")) and bool((c.get("dueno") or "").strip())
        z = zonas.zona_de(c, iso)
        deps = [str(d) for d in (c.get("deportes") or [])] or ([str(c["deporte"])] if c.get("deporte") else [])
        try:
            precio = float(c.get("precio_hora") or 0)
        except (TypeError, ValueError):
            precio = 0.0
        canchas.append({
            "id": str(c["id"]), "nombre": (c.get("nombre") or "").strip(), "club": (c.get("club") or c.get("nombre") or "").strip(),
            "zona": z, "zona_nombre": zonas.mostrar(z, iso) if z else None, "deportes": deps,
            "precio_hora": round(precio, 2) if precio > 0 else None, "moneda": _simbolo(c, iso),
            "apertura": c.get("hora_apertura"), "cierre": c.get("hora_cierre"), "reservable": reservable,
            "destacable": _destacable(c, pro_activo, destacar_pro), "fotos": _fotos_propias(c),
            "lat": c.get("lat"), "lng": c.get("lng"), "_c": c,
        })
    por_id = {c["id"]: c for c in canchas}

    # Ocupación histórica y huecos de los próximos días (solo canchas reservables).
    ocupados: dict[tuple[str, str], set[int]] = defaultdict(set)
    for r in crudo.get("reservas") or []:
        cid = str(r.get("cancha_id"))
        if cid not in por_id or str(r.get("estado") or "") == "cancelada":
            continue
        ini, fin = _hhmm(r.get("hora_inicio")), _hhmm(r.get("hora_fin"), 24 * 60)
        if ini is None:
            continue
        fin = fin if fin and fin > ini else ini + 60
        for s in _slots(por_id[cid]["_c"]):
            if ini <= s < fin:
                ocupados[(cid, str(r.get("fecha")))].add(s)
    bloqueados: dict[tuple[str, str], set[int]] = defaultdict(set)
    for b in crudo.get("bloqueos") or []:
        m = _hhmm(b.get("hora"))
        if m is not None:
            bloqueados[(str(b.get("cancha_id")), str(b.get("fecha")))].add(m)

    hist = defaultdict(lambda: {"ofrecidos": 0, "reservados": 0})       # (zona, dia, franja)
    futuro = defaultdict(lambda: {"libres": 0, "canchas": set()})       # (zona, fecha, franja)
    futuro_cancha = defaultdict(lambda: defaultdict(int))               # cancha → (fecha, franja) → libres
    reservas_28d = 0
    for c in canchas:
        if not c["reservable"]:
            continue
        slots = _slots(c["_c"])
        for delta in range(-VENTANA_HISTORIA_DIAS, VENTANA_FUTURO_DIAS + 1):
            f = hoy + timedelta(days=delta)
            k = (c["id"], f.isoformat())
            dia = DIAS[f.weekday()]
            for s in slots:
                if s in bloqueados.get(k, ()):
                    continue
                fr = franja_de(s)
                if delta < 0:
                    clave = (c["zona"], dia, fr)
                    hist[clave]["ofrecidos"] += 1
                    if s in ocupados.get(k, ()):
                        hist[clave]["reservados"] += 1
                        reservas_28d += 1
                elif not (delta == 0 and s <= ahora_min) and s not in ocupados.get(k, ()):
                    clave = (c["zona"], f.isoformat(), fr)
                    futuro[clave]["libres"] += 1
                    futuro[clave]["canchas"].add(c["id"])
                    futuro_cancha[c["id"]][(f.isoformat(), fr)] += 1

    ocupacion = [{"zona": z, "dia": d, "franja": fr, "ofrecidos": v["ofrecidos"], "reservados": v["reservados"],
                  "pct": round(100.0 * v["reservados"] / v["ofrecidos"], 1) if v["ofrecidos"] else None}
                 for (z, d, fr), v in hist.items()]
    libres = [{"zona": z, "fecha": fe, "dia": DIAS[date.fromisoformat(fe).weekday()], "franja": fr, "libres": v["libres"],
               "canchas": sorted(v["canchas"])} for (z, fe, fr), v in futuro.items()]

    # Promos REALES con su vigencia.
    promos = []
    for c in canchas:
        cc = c["_c"]
        try:
            pct = int(cc.get("descuento_valle") or 0)
        except (TypeError, ValueError):
            pct = 0
        if pct > 0 and cc.get("valle_desde") and cc.get("valle_hasta") and c["reservable"]:
            promos.append({"tipo": "hora_feliz", "cancha_id": c["id"], "zona": c["zona"], "pct": pct,
                           "desde": str(cc["valle_desde"])[:5], "hasta": str(cc["valle_hasta"])[:5], "vigente_hasta": None})
    por_slot: dict[tuple[str, str], list] = defaultdict(list)
    for d in crudo.get("descuentos") or []:
        if str(d.get("cancha_id")) in por_id and por_id[str(d["cancha_id"])]["reservable"]:
            por_slot[(str(d["cancha_id"]), str(d.get("fecha")))].append(d)
    for (cid, fecha), filas in por_slot.items():
        horas = sorted(str(x.get("hora"))[:5] for x in filas)
        pct = max(int(x.get("pct") or 0) for x in filas)
        promos.append({"tipo": "descuento_turno", "cancha_id": cid, "zona": por_id[cid]["zona"], "pct": pct,
                       "fecha": fecha, "horas": horas, "vigente_hasta": fecha})
    clubes_destacables = {c["club"].lower() for c in canchas if c["destacable"]}
    for b in crudo.get("bonos") or []:
        if str(b.get("club") or "").lower() in clubes_destacables:
            promos.append({"tipo": "bono_horas", "club": b.get("club"), "nombre": b.get("nombre"), "horas": b.get("horas"),
                           "precio": float(b.get("precio") or 0), "vigente_hasta": None})

    # Canchas nuevas (activadas en los últimos NUEVA_DIAS días).
    lim = hoy - timedelta(days=NUEVA_DIAS)
    nuevas = [c["id"] for c in canchas if c["reservable"] and (crudo.get("verificaciones") or {}).get(c["id"]) and
              crudo["verificaciones"][c["id"]] >= lim]

    # Leads de dueños: canchas descubiertas (Google) aún no registradas, por zona.
    registradas = [(float(c["lat"]), float(c["lng"])) for c in canchas if c["lat"] is not None and c["lng"] is not None]
    leads = defaultdict(lambda: defaultdict(int))
    for d in crudo.get("descubiertas") or []:
        if d.get("lat") is None or d.get("lng") is None or _pais(d) != pais:
            continue
        la, ln = float(d["lat"]), float(d["lng"])
        if any(_dist_m(la, ln, a, b) < DEDUP_LEAD_M for a, b in registradas):
            continue
        z = zonas.zona_de(d, pais)
        if z:
            leads[z][str(d.get("deporte") or "otro")] += 1

    # Demanda declarada ("pide tu cancha") y comunidad.
    demanda = defaultdict(int)
    for s in crudo.get("solicitudes") or []:
        if s.get("estado") in ("solicitada", "en_captacion"):
            z = zonas.zona_de({"distrito": s.get("distrito"), "direccion": s.get("direccion")}, pais)
            if z:
                demanda[z] += 1
    partidos = sum(1 for p in crudo.get("partidos") or [] if p.get("lat") is None or _pais(p) == pais)

    por_zona = defaultdict(lambda: {"reservables": 0, "registradas": 0, "deportes": defaultdict(int)})
    for c in canchas:
        if not c["zona"]:
            continue
        pz = por_zona[c["zona"]]
        pz["registradas"] += 1
        if c["reservable"]:
            pz["reservables"] += 1
            for d in c["deportes"]:
                pz["deportes"][d] += 1

    publicas = [{k: v for k, v in c.items() if k not in ("_c", "lat", "lng")} for c in canchas]
    return {
        "pais": pais, "hoy": hoy.isoformat(), "dia": DIAS[hoy.weekday()], "ahora_min": ahora_min,
        "canchas": {"registradas": len(canchas), "reservables": sum(1 for c in canchas if c["reservable"]),
                    "sin_zona": sum(1 for c in canchas if not c["zona"]),
                    "por_zona": {z: {"nombre": zonas.mostrar(z, pais), "reservables": v["reservables"], "registradas": v["registradas"],
                                     "deportes": dict(v["deportes"])} for z, v in por_zona.items()}},
        "canchas_lista": publicas,
        "ocupacion_28d": ocupacion, "reservas_28d": reservas_28d,
        "libres_7d": libres, "libres_por_cancha": {cid: {f"{fe}|{fr}": n for (fe, fr), n in m.items()} for cid, m in futuro_cancha.items()},
        "promos": promos, "nuevas": nuevas,
        "leads_duenos": {z: {"nombre": zonas.mostrar(z, pais), "total": sum(v.values()), "por_deporte": dict(v)} for z, v in leads.items()},
        "demanda": {z: {"nombre": zonas.mostrar(z, pais), "solicitudes": n} for z, n in demanda.items()},
        "comunidad": {"partidos_abiertos": partidos, "convocatorias_abiertas": int(crudo.get("convocatorias") or 0)},
    }


def recolectar(*, pais: str, hoy: date, ahora_min: int, destacar_pro: bool) -> dict:
    from db.store import stores
    return construir_snapshot(cargar_crudo(hoy), pais=pais, hoy=hoy, ahora_min=ahora_min,
                              pro_activo=stores.pro_activo, destacar_pro=destacar_pro)


def resumen_para_ia(s: dict) -> dict:
    """Versión compacta del snapshot (sin listas largas) para el prompt."""
    return {"pais": s["pais"], "hoy": s["hoy"], "dia": s["dia"], "canchas": s["canchas"], "reservas_28d": s["reservas_28d"],
            "promos": len(s["promos"]), "nuevas": len(s["nuevas"]), "comunidad": s["comunidad"],
            "leads_duenos": {v["nombre"]: v["total"] for v in s["leads_duenos"].values()},
            "demanda": {v["nombre"]: v["solicitudes"] for v in s["demanda"].values()}}
