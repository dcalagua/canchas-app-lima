"""AI MARKETING AGENT (`marketing/agente_ia/`): datos reales → estrategia →
contenido validado → aprobación → publicación → métricas → aprendizaje."""

import json
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config  # noqa: E402
from db.store import stores  # noqa: E402
from marketing.agente_ia import (aprendizaje, analitica, creador, datos, esquema, estratega, guardrails,  # noqa: E402
                                 orquestador as orq, publicador, repo as repo_mod, zonas)

TOKEN = "secreto-mkt"
HOY = date(2026, 10, 19)          # lunes
RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def _cancha(i, **k):
    base = {"id": f"k{i}", "nombre": "Cancha 1", "club": f"Club Numero {i}", "barrio": "Surco", "deporte": "futbol",
            "deportes": ["futbol"], "precio_hora": 80, "lat": -12.13, "lng": -76.99, "verificada": True, "dueno": f"d{i}@x.pe",
            "hora_apertura": "08:00", "hora_cierre": "23:00", "duracion_slot_min": 60, "descuento_valle": 0,
            "valle_desde": None, "valle_hasta": None, "fotos": [], "moneda": "S/"}
    base.update(k)
    return base


def _crudo(n=3, **extra):
    c = {"canchas": [_cancha(i) for i in range(n)], "reservas": [], "bloqueos": [], "descuentos": [], "bonos": [],
         "descubiertas": [{"id": f"g{i}", "nombre": "X", "direccion": "Av. Universitaria 1, Los Olivos", "lat": -11.99 - i * 0.01,
                           "lng": -77.07, "deporte": "futbol"} for i in range(6)],
         "partidos": [], "solicitudes": [], "verificaciones": {}, "convocatorias": 0}
    c.update(extra)
    return c


def _snap(crudo=None, **k):
    return datos.construir_snapshot(crudo or _crudo(), pais="PE", hoy=HOY, ahora_min=600, **k)


@pytest.fixture(autouse=True)
def _limpio(monkeypatch):
    stores.reset()
    mem = repo_mod._MemRepo()
    repo_mod.usar(mem)
    monkeypatch.setattr(config, "ADMIN_PANEL_TOKEN", TOKEN)
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "")
    monkeypatch.setattr(config, "SUPABASE_URL", "")
    monkeypatch.setattr(config, "IG_USER_ID", "")
    from marketing.agente_ia import creativo
    monkeypatch.setattr(creativo, "_biblioteca_fotos", lambda n: [])
    monkeypatch.setattr(creativo, "_biblioteca_video", lambda: None)
    monkeypatch.setattr(creativo, "componer", lambda receta, **k: b"\xff\xd8JPEG")
    monkeypatch.setattr(orq, "snapshot", lambda pais: _snap())
    yield mem
    repo_mod.usar(None)


# ── esquema ──────────────────────────────────────────────────────────────────
def test_esquema_alineado_con_sql_manual():
    sql = open(os.path.join(RAIZ, "docs", "piloto", "supabase_ai_marketing.sql"), encoding="utf-8").read()
    en_sql = set(re.findall(r"create table if not exists (ai_\w+)", sql))
    en_py = {re.search(r"create table if not exists (ai_\w+)", d).group(1) for d in esquema.DDL if "create table" in d}
    assert en_sql == en_py and len(en_py) == 8
    assert all(f"alter table {t}" in " ".join(esquema.DDL).replace("  ", " ") or f"alter table {t} " in " ".join(esquema.DDL)
               for t in ["ai_content"])
    # RLS activo en todas, sin políticas para anon
    assert sum("enable row level security" in d for d in esquema.DDL) == 8
    assert "create policy" not in sql.lower()


# ── zonas ────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("c,esperado", [
    ({"direccion": "Av. La Molina 123, Ate, Lima"}, "Ate"),
    ({"barrio": "Surco"}, "Surco"),
    ({"direccion": "Jr. Lima 444, Santiago de Surco 15023"}, "Surco"),
    ({"distrito": "Jesús María"}, "Jesús María"),
    ({}, None),
])
def test_zona_real_sin_inventar(c, esperado):
    z = zonas.zona_de(c)
    assert (zonas.mostrar(z) if z else None) == esperado


# ── collector ────────────────────────────────────────────────────────────────
def test_snapshot_agregados_sin_pii():
    crudo = _crudo(2, reservas=[{"cancha_id": "k0", "fecha": "2026-10-15", "hora_inicio": "19:00", "hora_fin": "21:00", "estado": "confirmada"}],
                   bloqueos=[{"cancha_id": "k1", "fecha": "2026-10-20", "hora": "08:00"}])
    s = _snap(crudo)
    assert s["canchas"]["reservables"] == 2 and s["canchas"]["por_zona"]["santiago de surco"]["nombre"] == "Surco"
    assert s["reservas_28d"] == 2                         # 19-21 = dos turnos de 60'
    occ = next(o for o in s["ocupacion_28d"] if o["dia"] == "jueves" and o["franja"] == "noche")
    assert occ["reservados"] == 2
    assert s["libres_por_cancha"]["k1"]["2026-10-20|mañana"] == s["libres_por_cancha"]["k0"]["2026-10-20|mañana"] - 1   # bloqueo
    txt = json.dumps(s, default=str)
    assert not re.search(r"[\w.]+@[\w.]+", txt) and '"dueno"' not in txt          # sin correos
    assert s["leads_duenos"]["los olivos"]["total"] == 6


def test_leads_deduplica_canchas_ya_registradas():
    crudo = _crudo(1, descubiertas=[{"id": "g", "nombre": "Misma", "direccion": "Surco", "lat": -12.1301, "lng": -76.9901, "deporte": "futbol"}])
    assert _snap(crudo)["leads_duenos"] == {}


def test_destacable_solo_con_pro_y_flag():
    s = _snap(destacar_pro=False, pro_activo=lambda e: True)
    assert not any(c["destacable"] for c in s["canchas_lista"])
    s = _snap(destacar_pro=True, pro_activo=lambda e: e == "d1@x.pe")
    assert [c["id"] for c in s["canchas_lista"] if c["destacable"]] == ["k1"]


def test_promos_reales_con_vigencia():
    crudo = _crudo(2, descuentos=[{"cancha_id": "k0", "fecha": "2026-10-21", "hora": "09:00", "pct": 15}])
    crudo["canchas"][1].update(descuento_valle=20, valle_desde="08:00", valle_hasta="11:00")
    s = _snap(crudo)
    tipos = {(p["tipo"], p["cancha_id"], p["pct"]) for p in s["promos"]}
    assert tipos == {("descuento_turno", "k0", 15), ("hora_feliz", "k1", 20)}


# ── estratega ────────────────────────────────────────────────────────────────
def test_poca_oferta_no_vende_disponibilidad_y_prioriza_duenos():
    s = _snap()
    cands = estratega.candidatas(s, umbral=15)
    assert not any(c["tipo"] == "huecos_zona" for c in cands)
    assert any(c["tipo"] == "captar_duenos_zona" for c in cands)
    d = estratega.decidir(s, insights=[], recientes=[], n=1, usar_ia=False)
    assert d["baja_densidad"] and d["elegidas"][0]["audiencia"] == "duenos"
    assert all(c["objetivo"] and c["kpi"] for c in d["candidatas"])        # regla fundamental


def test_con_oferta_suficiente_aparecen_huecos_reales():
    s = _snap(_crudo(16))
    h = next(c for c in estratega.candidatas(s, umbral=15) if c["tipo"] == "huecos_zona")
    assert h["hechos"]["zona"] == "Surco" and h["hechos"]["dia"] in ("martes", "miércoles", "jueves")
    assert h["hechos"]["canchas_con_turnos"] == 16 and len(h["cancha_ids"]) == 16


def test_mezcla_de_audiencias_70_30():
    s = _snap()
    recientes = [{"audiencia": "duenos"}] * 7 + [{"audiencia": "jugadores"}] * 3
    assert estratega._audiencias_del_dia(1, s, 15, 0.7, 0.3, recientes) == ["jugadores"]
    assert estratega._audiencias_del_dia(1, s, 15, 0.7, 0.3, [{"audiencia": "jugadores"}] * 4) == ["duenos"]


def test_ia_solo_puede_elegir_candidatas_existentes():
    cands = estratega.candidatas(_snap())
    assert estratega.validar_ia({"elegidas": [{"id": "c999"}]}, cands, 1) is None
    r = estratega.validar_ia({"elegidas": [{"id": cands[0]["id"], "hora": "25:00", "content_type": "reel"}]}, cands, 1)
    assert r[0]["hora"] in estratega.HORA_DEFECTO.values() and r[0]["content_type"] != "reel"


def test_insights_y_repeticion_mueven_el_puntaje():
    cands = estratega.candidatas(_snap())
    base = {c["id"]: c["score"] for c in cands}
    ins = [{"dimension": "tipo", "valor": "duenos_beneficios", "efecto": 1.0, "confianza": 1.0}]
    orden = estratega.ordenar(cands, insights=ins, recientes=[{"tipo": "captar_duenos_zona", "zona": "los olivos"}])
    d = next(c for c in orden if c["tipo"] == "duenos_beneficios")
    z = next(c for c in orden if c["tipo"] == "captar_duenos_zona")
    assert d["puntaje"] == pytest.approx(base[d["id"]] * 2) and z["puntaje"] < base[z["id"]]


# ── guardrails ───────────────────────────────────────────────────────────────
OP = {"objetivo": "reservas", "kpi": "reservas_atribuidas", "destacadas": []}
H = {"pais": "PE", "zona": "Surco", "dia": "martes", "franja": "noche", "canchas_con_turnos": 4}


def _p(texto, **k):
    return {"title": k.get("title", "Pichanga"), "subtitle": "", "etiqueta": "", "body": texto, "call_to_action": "", "hashtags": []}


def _v(texto, hechos=H, **k):
    return guardrails.validar(_p(texto), hechos, oportunidad=k.pop("op", OP), **k)


LARGO = " Arma el partido con tu grupo y llega directo a jugar sin vueltas ni llamadas."


def test_guardrails_acepta_pieza_respaldada():
    v = _v("Este martes por la noche hay turnos libres en 4 canchas de Surco." + LARGO)
    assert v["ok"], v["errores"]


@pytest.mark.parametrize("texto,error", [
    ("En Surco la hora cuesta S/ 50." + LARGO, "Monto"),
    ("En Surco tienes 30% de descuento." + LARGO, "Porcentaje"),
    ("Reserva en Surco desde las 19:00." + LARGO, "Horario"),
    ("Hay 12 canchas en Surco esperándote." + LARGO, "Cifra"),
    ("Este martes hay turnos libres en Miraflores." + LARGO, "zona"),
    ("Juega en el Club Numero 3, el mejor de Surco." + LARGO, "local"),
    ("Aprovecha la promo de esta semana en Surco." + LARGO, "promoción"),
    ("Jugar en Surco es gratis esta semana." + LARGO, "gratis"),
    ("Escríbenos al 987 654 321 para reservar en Surco." + LARGO, "teléfono"),
])
def test_guardrails_rechaza_lo_inventado(texto, error):
    v = _v(texto, locales_pais=["Club Numero 3"])
    assert not v["ok"] and any(error.lower() in e.lower() for e in v["errores"]), v["errores"]


def test_guardrails_disponibilidad_exige_turnos_reales():
    for t in ("Todavía hay turnos libres para tu pichanga.", "Canchas libres esta noche para tu pichanga.",
              "Últimos turnos para tu pichanga de la semana.", "Turnos disponibles hoy para tu pichanga."):
        v = _v(t + LARGO, hechos={"pais": "PE"})
        assert not v["ok"] and any("disponibilidad" in e for e in v["errores"]), t


def test_guardrails_ia_nunca_con_cancha_concreta_ni_moneda_ajena():
    v = _v("Te esperamos en Surco este martes por la noche." + LARGO, op={**OP, "destacadas": ["k1"]}, media_origen="ia_conceptual")
    assert any("IA" in e for e in v["errores"])
    v = _v("Reserva y paga con Yape en un toque, sin vueltas." + LARGO, hechos={"pais": "BO"})
    assert any("Perú" in e for e in v["errores"])


def test_guardrails_no_repite():
    t = "Este martes por la noche hay turnos libres en 4 canchas de Surco." + LARGO
    assert any("reciente" in e for e in _v(t, recientes=[t])["errores"])


def test_banco_de_plantillas_pasa_siempre_los_guardrails():
    s = _snap(_crudo(16, descuentos=[{"cancha_id": "k0", "fecha": "2026-10-21", "hora": "09:00", "pct": 15}],
                     solicitudes=[{"zona": "lima_norte", "distrito": "Comas", "direccion": "", "estado": "solicitada"}] * 3,
                     partidos=[{"deporte": "futbol", "fecha": "2026-10-22", "lat": None, "lng": None}],
                     verificaciones={"k2": HOY}),
              destacar_pro=True, pro_activo=lambda e: e == "d0@x.pe")
    s["canchas_lista"][0]["fotos"] = ["https://x.supabase.co/storage/v1/object/public/canchas/a.jpg"]
    cands = estratega.candidatas(s, umbral=15)
    tipos = {c["tipo"] for c in cands}
    assert {"huecos_zona", "cancha_destacada", "promo_real", "canchas_nuevas", "captar_duenos_zona", "demanda_zona",
            "comunidad", "marca_jugadores", "duenos_beneficios"} <= tipos
    locales = [c["club"] for c in s["canchas_lista"]]
    for c in cands:
        for semilla in range(3):
            p = creador.redactar(c, link="https://www.pichangol.app/go/abc", usar_ia=False, locales_pais=locales, semilla=semilla)
            assert p["validacion"]["ok"], (c["tipo"], p["validacion"]["errores"], p["body"])
            assert "https://www.pichangol.app/go/abc" in p["body"] and "#pichangol" in p["body"]


def test_creador_reintenta_ia_y_cae_al_banco(monkeypatch):
    llamadas = []

    def falsa(payload):
        llamadas.append(payload)
        return {"titulo": "Oferta", "texto": "Solo hoy S/ 10 la hora en Surco, ¡corre!" + LARGO, "cta": "Reserva"}
    monkeypatch.setattr(creador, "_con_ia", falsa)
    op = next(c for c in estratega.candidatas(_snap()) if c["tipo"] == "duenos_beneficios")
    p = creador.redactar(op, link="https://x/go/1", usar_ia=True)
    assert len(llamadas) == 2 and "errores_version_anterior" in llamadas[1]
    assert p["fuente"] == "banco" and p["validacion"]["ok"] and len(p["validacion"]["intentos_ia"]) == 2


def test_creador_usa_la_ia_si_respeta_los_hechos(monkeypatch):
    monkeypatch.setattr(creador, "_con_ia", lambda payload: {
        "titulo": "Tu cancha en el mapa", "subtitulo": "", "etiqueta": "",
        "texto": "Los jugadores ya buscan dónde jugar desde el celular. Publica tu cancha, recibe reservas confirmadas y cobra en línea sin perseguir a nadie.",
        "cta": "Regístrala hoy"})
    op = next(c for c in estratega.candidatas(_snap()) if c["tipo"] == "duenos_beneficios")
    p = creador.redactar(op, link="https://x/go/1")
    assert p["fuente"] == "ia" and p["call_to_action"] == "Regístrala hoy"


# ── orquestador + publisher ──────────────────────────────────────────────────
def _fb(monkeypatch, respuestas):
    from marketing import post_redes
    monkeypatch.setattr(post_redes, "configurado", lambda: True)
    monkeypatch.setattr(post_redes, "registrar", lambda e: e)
    llamadas = []

    def pub(texto, img):
        llamadas.append(texto)
        return respuestas.pop(0) if respuestas else {"ok": True, "post_id": "1_2", "url": "https://facebook.com/1_2"}
    monkeypatch.setattr(post_redes, "publicar_facebook", pub)
    return llamadas


def test_ciclo_completo_aprobacion_humana(monkeypatch, _limpio):
    llamadas = _fb(monkeypatch, [])
    r = orq.planificar("PE", usar_ia=False)
    assert r["ok"] and len(r["piezas"]) == 1
    p = r["piezas"][0]
    assert p["status"] == "PENDING_APPROVAL" and p["objetivo"] and p["kpi"] and p["link_url"].endswith(p["codigo"])
    assert orq.planificar("PE")["motivo"] == "ya_planificado"                 # idempotente
    assert publicador.tick(snapshot_de=orq.snapshot) == 0                     # sin aprobar no sale nada
    orq.aprobar(p["id"], "ana", datetime.now(timezone.utc) - timedelta(minutes=5))
    assert publicador.tick(snapshot_de=orq.snapshot) == 1 and len(llamadas) == 1
    c = _limpio.contenido(p["id"])
    assert c["status"] == "PUBLISHED" and c["external_post_id"] == "1_2" and c["revisado_por"] == "ana"
    assert any(l["accion"] == "publicado" for l in _limpio.logs_recientes())


def test_publisher_reintenta_y_luego_falla(monkeypatch, _limpio):
    _fb(monkeypatch, [{"ok": False, "error": "timeout"}] * 3)
    p = orq.planificar("PE", usar_ia=False)["piezas"][0]
    orq.aprobar(p["id"], "ana")
    for i in range(1, 4):
        _limpio.actualizar_contenido(p["id"], scheduled_at=datetime.now(timezone.utc) - timedelta(seconds=1))
        publicador.tick(snapshot_de=orq.snapshot)
        c = _limpio.contenido(p["id"])
        assert c["intentos"] == i
    assert c["status"] == "FAILED" and c["error"] == "timeout"
    orq.reprogramar(p["id"], "ana", datetime.now(timezone.utc) + timedelta(hours=1))
    assert _limpio.contenido(p["id"])["status"] == "APPROVED" and _limpio.contenido(p["id"])["intentos"] == 0


def test_publisher_revalida_contra_datos_frescos():
    s = _snap(_crudo(16))
    c = {"oportunidad": {"tipo": "huecos_zona", "cancha_ids": ["k0"], "fecha_objetivo": "2026-10-20"},
         "hechos": {"dia": "martes", "franja": "mañana", "canchas_con_turnos": 1}}
    assert publicador.sigue_vigente(c, s) == (None, False)
    s["libres_por_cancha"]["k0"]["2026-10-20|mañana"] = 0
    assert "turnos" in publicador.sigue_vigente(c, s)[0]
    pasada = {**c, "oportunidad": {**c["oportunidad"], "fecha_objetivo": "2026-10-18"}}
    assert "pasó" in publicador.sigue_vigente(pasada, s)[0]
    vencida = {"oportunidad": {"tipo": "promo_real", "vigente_hasta": "2026-10-01"}, "hechos": {"promo": {}}}
    assert "venció" in publicador.sigue_vigente(vencida, s)[0]
    motivo, transitorio = publicador.sigue_vigente(c, None)        # sin datos frescos: no se publica, se reintenta
    assert motivo and transitorio


def test_revalida_promo_de_zona_y_conteos():
    crudo = _crudo(16)
    for i in range(3):
        crudo["canchas"][i].update(descuento_valle=20, valle_desde="08:00", valle_hasta="11:00")
    s = _snap(crudo)
    op = next(c for c in estratega.candidatas(s) if c["tipo"] == "promo_zona")
    pieza = {"oportunidad": op, "hechos": op["hechos"]}
    assert publicador.sigue_vigente(pieza, s)[0] is None
    crudo["canchas"][0]["descuento_valle"] = 0                   # un dueño apagó su hora feliz
    assert "cambiaron" in publicador.sigue_vigente(pieza, _snap(crudo))[0]
    s2 = _snap()
    lead = next(c for c in estratega.candidatas(s2) if c["tipo"] == "captar_duenos_zona")
    s2["leads_duenos"]["los olivos"]["total"] = 2
    assert "Bajó" in publicador.sigue_vigente({"oportunidad": lead, "hechos": lead["hechos"]}, s2)[0]


def test_sin_credenciales_falla_sin_reintentar(monkeypatch, _limpio):
    from marketing import post_redes
    monkeypatch.setattr(post_redes, "configurado", lambda: False)
    p = orq.planificar("PE", usar_ia=False)["piezas"][0]
    orq.aprobar(p["id"], "ana")
    _limpio.actualizar_contenido(p["id"], scheduled_at=datetime.now(timezone.utc) - timedelta(seconds=1))
    publicador.tick(snapshot_de=orq.snapshot)
    assert _limpio.contenido(p["id"])["status"] == "FAILED"


def test_pausa_detiene_publicacion(monkeypatch, _limpio):
    _fb(monkeypatch, [])
    p = orq.planificar("PE", usar_ia=False)["piezas"][0]
    orq.aprobar(p["id"], "ana")
    _limpio.actualizar_contenido(p["id"], scheduled_at=datetime.now(timezone.utc) - timedelta(seconds=1))
    orq.guardar_configuracion({"pausa": True})
    assert publicador.tick(snapshot_de=orq.snapshot) == 0


def test_editar_revalida_y_rechaza_lo_inventado(_limpio):
    p = orq.planificar("PE", usar_ia=False)["piezas"][0]
    mal = orq.editar(p["id"], "ana", {"texto": "Regístrate y gana S/ 500 el primer mes con tu cancha, sin letra chica ni vueltas raras."})
    assert mal["status"] == "REJECTED" and any("Monto" in e for e in mal["validacion"]["errores"])
    with pytest.raises(orq.Rechazo):
        orq.aprobar(p["id"], "ana")
    ok = orq.editar(p["id"], "ana", {"texto": "Tu cancha merece estar llena. Publícala en Pichangol, recibe reservas confirmadas y cobra en línea sin perseguir a nadie."})
    assert ok["status"] == "PENDING_APPROVAL" and p["link_url"] in ok["body"]
    assert orq.solo_texto(ok).startswith("Tu cancha merece")


def test_cancelar_rechazar_y_regenerar(_limpio):
    p = orq.planificar("PE", usar_ia=False)["piezas"][0]
    nueva = orq.regenerar(p["id"], "ana", usar_ia=False)
    assert _limpio.contenido(p["id"])["status"] == "CANCELLED" and nueva["id"] != p["id"]
    orq.rechazar(nueva["id"], "ana", "no me gusta el tono")
    assert _limpio.contenido(nueva["id"])["motivo_rechazo"] == "no me gusta el tono"
    with pytest.raises(orq.Rechazo):
        orq.aprobar(nueva["id"], "ana")


def test_modo_automatico_validado_con_tope(monkeypatch, _limpio):
    _fb(monkeypatch, [])
    orq.guardar_configuracion({"modo": "auto_validado", "auto_max_dia": 1, "posts_dia": 2})
    piezas = orq.planificar("PE", usar_ia=False)["piezas"]
    assert [x["status"] for x in piezas].count("APPROVED") == 1
    assert next(x for x in piezas if x["status"] == "APPROVED")["revisado_por"] == "auto"


def test_activar_el_nuevo_apaga_el_agente_viejo():
    from marketing import agente_redes
    stores.config["agente_fb_activo"] = "1"
    orq.guardar_configuracion({"activo": True})
    assert stores.config["agente_fb_activo"] == "0"
    stores.config["agente_fb_activo"] = "1"
    assert agente_redes.tick() is False                 # ai_mkt_activo manda
    assert agente_redes.configuracion()["modo"] == "aprobar"


def test_tick_planifica_a_la_hora_y_una_vez(monkeypatch, _limpio):
    orq.guardar_configuracion({"activo": True, "hora_plan": "00:00"})
    monkeypatch.setattr(analitica, "tick", lambda **k: 0)
    assert orq.tick() is True
    n = len(_limpio.contenidos)
    orq.tick()
    assert len(_limpio.contenidos) == n


# ── métricas, atribución y aprendizaje ────────────────────────────────────────
def test_analytics_mide_ventanas_vencidas(monkeypatch, _limpio):
    _fb(monkeypatch, [])
    p = orq.planificar("PE", usar_ia=False)["piezas"][0]
    orq.aprobar(p["id"], "ana")
    _limpio.actualizar_contenido(p["id"], scheduled_at=datetime.now(timezone.utc) - timedelta(seconds=1))
    publicador.tick(snapshot_de=orq.snapshot)
    pub = datetime.now(timezone.utc) - timedelta(hours=30)
    _limpio.actualizar_contenido(p["id"], published_at=pub)
    for v, h in (("a", 2), ("a", 3), ("b", 5), ("c", 26)):   # el de "c" cae fuera de la ventana de 24h
        _limpio.registrar_clic(p["id"], v)
        _limpio.clics[-1]["creado"] = pub + timedelta(hours=h)
    fb = lambda pid: ({"alcance": 200, "reacciones": 10, "comentarios": 4, "compartidos": 6}, {"ok": 1})
    n = analitica.tick(fb=fb, reservas=lambda cod, hasta: (2, 160.0))
    assert n == 2                                          # 1h y 24h
    m = _limpio.performance(p["id"])["24h"]
    assert m["interacciones"] == 20 and m["engagement_rate"] == 0.1 and m["clics_link"] == 2 and m["reservas_atribuidas"] == 2
    assert analitica.tick(fb=fb, reservas=lambda c, h: (0, 0)) == 0      # no remide


def test_learner_detecta_patron_con_evidencia():
    filas = []
    for i in range(12):
        filas.append({"id": f"x{i}", "dia": "viernes" if i < 4 else "martes", "franja": "tarde", "audiencia": "jugadores",
                      "tipo": "marca_jugadores", "content_type": "post", "media_origen": "diseno", "objetivo": "usuarios", "zona": None,
                      "engagement_rate": 0.12 if i < 4 else 0.04, "clics_link": None, "reservas_atribuidas": None})
    ins = aprendizaje.calcular(filas)
    viernes = next(i for i in ins if i["dimension"] == "dia" and i["valor"] == "viernes")
    assert viernes["efecto"] > 0.5 and viernes["muestras"] == 4 and "viernes" in viernes["enunciado"]
    assert set(viernes["evidencia"]) == {"x0", "x1", "x2", "x3"}
    assert aprendizaje.calcular(filas[:5]) == []           # sin muestra suficiente no se "aprende" nada


# ── API de la torre y short-link ─────────────────────────────────────────────
@pytest.fixture
def client():
    import main
    return TestClient(main.app)


H_ADMIN = {"X-Admin-Token": TOKEN}


def test_api_protegida_y_flujo_por_http(client, monkeypatch):
    _fb(monkeypatch, [])
    assert client.get("/admin/api/mkt").status_code == 401
    r = client.post("/admin/api/mkt/correr", json={"pais": "PE"}, headers=H_ADMIN)
    assert r.status_code == 200
    pid = r.json()["piezas"][0]["id"]
    assert client.get("/admin/api/mkt/piezas", headers=H_ADMIN).json()["piezas"][0]["id"] == pid
    assert client.get(f"/admin/api/mkt/pieza/{pid}/imagen", headers=H_ADMIN).json()["imagen"].startswith("data:image/jpeg")
    r = client.post(f"/admin/api/mkt/pieza/{pid}/publicar", json={}, headers=H_ADMIN)
    assert r.status_code == 200 and r.json()["pieza"]["status"] == "PUBLISHED"
    assert client.post(f"/admin/api/mkt/pieza/{pid}/cancelar", json={}, headers=H_ADMIN).status_code == 409
    assert client.post("/admin/api/mkt/config", json={"modo": "yolo"}, headers=H_ADMIN).status_code == 400
    assert client.get("/admin/api/mkt/logs", headers=H_ADMIN).json()["logs"]


def test_short_link_cuenta_clic_y_deja_cookie(client, monkeypatch, _limpio):
    _fb(monkeypatch, [])
    p = orq.planificar("PE", usar_ia=False)["piezas"][0]
    r = client.get(f"/go/{p['codigo']}", follow_redirects=False)
    assert r.status_code == 302 and not _limpio.clics                     # no publicada: no cuenta
    orq.publicar_ahora(p["id"], "ana")
    r = client.get(f"/go/{p['codigo']}", follow_redirects=False)
    assert r.status_code == 302 and "utm_content=" + p["codigo"] in r.headers["location"]
    assert "pg_utm=" + p["codigo"] in r.headers.get("set-cookie", "") and len(_limpio.clics) == 1
    assert client.get("/go/noexiste", follow_redirects=False).headers["location"].rstrip("/").endswith("pichangol.app")

    class _Req:
        cookies = {"pg_utm": p["codigo"]}
    from marketing.agente_ia.router import utm_de_request
    assert utm_de_request(_Req())["content"] == p["codigo"]


def test_torre_tiene_la_pestana(client):
    html = client.get("/admin").text
    assert 'id="page-marketing"' in html and "cargarMarketing" in html and "data-sec=\"marketing\"" in html


# ── integración con Postgres real (opcional) ─────────────────────────────────
PG_URL = os.getenv("AGENTE_IA_PG_URL", "")


@pytest.mark.skipif(not PG_URL, reason="AGENTE_IA_PG_URL no definido (Postgres local de prueba)")
def test_pg_repo_contra_postgres(monkeypatch):
    from db import pg
    monkeypatch.setattr(pg, "DATABASE_URL", PG_URL)
    monkeypatch.setattr(pg, "habilitado", True)
    esquema._reiniciar()
    assert esquema.asegurar()
    r = repo_mod._PgRepo()
    repo_mod.usar(r)
    with pg._conn() as c, c.cursor() as cur:
        cur.execute("TRUNCATE ai_content, ai_marketing_strategy, ai_marketing_campaigns, ai_insights, ai_agent_logs CASCADE")
        c.commit()
    _fb(monkeypatch, [])
    p = orq.planificar("PE", usar_ia=False)["piezas"][0]
    assert r.contenido(p["id"])["hechos"] == p["hechos"] and r.targets_de(p["id"]) == []
    assert orq.planificar("PE")["motivo"] == "ya_planificado"
    orq.aprobar(p["id"], "ana")
    assert r.cambiar_estado(p["id"], ("PENDING_APPROVAL",), "CANCELLED") is None      # transición atómica
    orq.publicar_ahora(p["id"], "ana")
    c = r.contenido(p["id"])
    assert c["status"] == "PUBLISHED" and c["published_at"]
    r.registrar_clic(p["id"], "v1")
    r.registrar_clic(p["id"], "v1")
    assert r.contar_clics(p["id"]) == 1
    r.guardar_performance(p["id"], "24h", {"alcance": 10, "engagement_rate": 0.2}, {"x": 1})
    r.guardar_performance(p["id"], "24h", {"alcance": 12}, {})
    assert r.performance(p["id"])["24h"]["alcance"] == 12
    r.reemplazar_insights([{"enunciado": "x", "dimension": "dia", "valor": "viernes", "metrica": "engagement_rate",
                            "efecto": 0.5, "muestras": 4, "confianza": 0.9}])
    assert r.insights_vigentes()[0]["valor"] == "viernes"
    assert r.estrategias_lista()[0]["oportunidades"]
    esquema._reiniciar()
    assert {"created_at", "origen", "utm"} == esquema.columnas_atribucion()


@pytest.mark.skipif(not PG_URL, reason="AGENTE_IA_PG_URL no definido (Postgres local de prueba)")
def test_pg_collector_y_reserva_con_atribucion(monkeypatch):
    from db import pg
    from web import datos as web_datos
    monkeypatch.setattr(pg, "DATABASE_URL", PG_URL)
    monkeypatch.setattr(pg, "habilitado", True)
    esquema._reiniciar()
    with pg._conn() as c, c.cursor() as cur:
        cur.execute("TRUNCATE pichangol_canchas, pichangol_reservas, pichangol_bloqueos, pichangol_descuentos_slot, pichangol_canchas_cache")
        cur.execute("INSERT INTO pichangol_canchas (id, nombre, club, barrio, deporte, deportes, precio_hora, lat, lng, verificada, dueno, "
                    "hora_apertura, hora_cierre, duracion_slot_min, descuento_valle, valle_desde, valle_hasta) VALUES "
                    "('k1','Cancha 1','La Bombonera','Surco','futbol','[\"futbol\"]',90,-12.13,-76.99,true,'d@x.pe','08:00','23:00',60,10,'08:00','12:00')")
        cur.execute("INSERT INTO pichangol_reservas (id, cancha_id, fecha, hora_inicio, hora_fin, estado) VALUES "
                    "('r1','k1','2026-10-14','20:00','21:00','confirmada')")
        cur.execute("INSERT INTO pichangol_canchas_cache (id, nombre, direccion, lat, lng, deporte) VALUES "
                    "('g1','Otra','Av. X 1, Los Olivos',-11.99,-77.07,'futbol')")
        c.commit()
    crudo = datos.cargar_crudo(HOY)
    s = datos.construir_snapshot(crudo, pais="PE", hoy=HOY, ahora_min=600)
    assert s["reservas_28d"] == 1 and s["promos"][0]["pct"] == 10 and s["leads_duenos"]["los olivos"]["total"] == 1
    fila = {"id": "r2", "cancha_id": "k1", "jugador": "J", "nivel": "", "fecha": "2026-10-21", "dia": "mié", "hora_inicio": "10:00",
            "hora_fin": "11:00", "estado": "nueva", "traida_por_app": True, "precio": 90, "sena": 0, "pagado": False, "usuario": "j@x.pe",
            "deporte": "futbol", "moneda": "S/", "extras": [], "telefono": "", "grupo_reserva_id": "", "medio_pago": "web_hold",
            "origen": "web", "utm": {"content": "abc123", "source": "facebook"}}
    assert web_datos.insertar_reservas([fila]) == ""
    with pg._conn() as c, c.cursor() as cur:
        cur.execute("SELECT origen, utm->>'content', created_at IS NOT NULL FROM pichangol_reservas WHERE id='r2'")
        assert cur.fetchone() == ("web", "abc123", True)
    assert analitica.reservas_atribuidas("abc123", datetime.now(timezone.utc) + timedelta(minutes=1)) == (1, 90.0)
    # Sin las columnas (SQL no corrido): la reserva entra igual, sin atribución.
    monkeypatch.setattr(esquema, "columnas_atribucion", lambda: set())
    assert web_datos.insertar_reservas([{**fila, "id": "r3", "hora_inicio": "11:00", "hora_fin": "12:00"}]) == ""


# ── regresiones de la revisión de código ──────────────────────────────────────
def _aprobada_vencida(mem):
    p = orq.planificar("PE", usar_ia=False)["piezas"][0]
    orq.aprobar(p["id"], "ana")
    mem.actualizar_contenido(p["id"], scheduled_at=datetime.now(timezone.utc) - timedelta(seconds=1))
    return mem.contenido(p["id"])


def test_reclamo_atomico_evita_doble_publicacion(monkeypatch, _limpio):
    llamadas = _fb(monkeypatch, [])
    c = _aprobada_vencida(_limpio)
    publicador.publicar(c, snapshot=_snap())
    publicador.publicar(c, snapshot=_snap())                 # misma foto de la pieza (carrera tick vs "Publicar ya")
    assert len(llamadas) == 1 and _limpio.contenido(c["id"])["status"] == "PUBLISHED"


def test_mientras_publica_no_se_puede_cancelar_ni_editar(monkeypatch, _limpio):
    from marketing import post_redes
    c = _aprobada_vencida(_limpio)
    estados = []

    def pub(texto, img):
        for f in (lambda: orq.cancelar(c["id"], "ana"), lambda: orq.editar(c["id"], "ana", {"title": "X"}),
                  lambda: orq.rechazar(c["id"], "ana", "no")):
            with pytest.raises(orq.Rechazo):
                f()
        estados.append(_limpio.contenido(c["id"])["status"])
        return {"ok": True, "post_id": "9_9", "url": "https://facebook.com/9_9"}
    monkeypatch.setattr(post_redes, "configurado", lambda: True)
    monkeypatch.setattr(post_redes, "publicar_facebook", pub)
    publicador.tick(snapshot_de=orq.snapshot)
    assert estados == ["PUBLISHING"] and _limpio.contenido(c["id"])["status"] == "PUBLISHED"


def test_si_falla_la_base_tras_publicar_no_se_republica(monkeypatch, _limpio):
    llamadas = _fb(monkeypatch, [])
    c = _aprobada_vencida(_limpio)
    original = _limpio.cambiar_estado

    def rota(cid, desde, hacia, **k):
        if hacia == "PUBLISHED":
            raise RuntimeError("base caída")
        return original(cid, desde, hacia, **k)
    monkeypatch.setattr(_limpio, "cambiar_estado", rota)
    for _ in range(3):
        publicador.tick(snapshot_de=orq.snapshot)
    assert len(llamadas) == 1 and _limpio.contenido(c["id"])["status"] == "PUBLISHING"
    monkeypatch.setattr(_limpio, "cambiar_estado", original)
    _limpio.contenidos[c["id"]]["updated_at"] = datetime.now(timezone.utc) - timedelta(hours=1)
    assert publicador.recuperar_colgadas() == 1
    assert _limpio.contenido(c["id"])["status"] == "FAILED" and "Revisa la página" in _limpio.contenido(c["id"])["error"]


def test_sin_datos_frescos_no_publica(monkeypatch, _limpio):
    llamadas = _fb(monkeypatch, [])
    c = _aprobada_vencida(_limpio)
    publicador.tick(snapshot_de=lambda pais: (_ for _ in ()).throw(RuntimeError("sin base")))
    c = _limpio.contenido(c["id"])
    assert not llamadas and c["status"] == "APPROVED" and c["scheduled_at"] > datetime.now(timezone.utc)


def test_error_de_un_pais_no_frena_la_publicacion(monkeypatch, _limpio):
    llamadas = _fb(monkeypatch, [])
    c = _aprobada_vencida(_limpio)
    orq.guardar_configuracion({"activo": True, "hora_plan": "00:00", "paises": ["BO", "PE"]})

    def snap(pais):
        if pais == "BO":
            raise RuntimeError("BO roto")
        return _snap()
    monkeypatch.setattr(orq, "snapshot", snap)
    monkeypatch.setattr(analitica, "tick", lambda **k: 0)
    orq.tick()
    assert llamadas and _limpio.contenido(c["id"])["status"] == "PUBLISHED"
    assert "BO" in json.loads(stores.config["ai_mkt_reintento_plan"])


def test_correr_ahora_reemplaza_las_piezas_no_aprobadas(_limpio):
    a = orq.planificar("PE", usar_ia=False)["piezas"][0]
    b = orq.planificar("PE", forzar=True, usar_ia=False)["piezas"][0]
    assert _limpio.contenido(a["id"])["status"] == "CANCELLED" and _limpio.contenido(b["id"])["status"] == "PENDING_APPROVAL"


def test_editar_no_choca_con_su_gemela_de_otra_red(monkeypatch, _limpio):
    monkeypatch.setattr(config, "IG_USER_ID", "123")
    from marketing import post_redes
    monkeypatch.setattr(post_redes, "configurado", lambda: True)
    orq.guardar_configuracion({"plataformas": ["facebook", "instagram"]})
    piezas = orq.planificar("PE", usar_ia=False)["piezas"]
    assert {p["platform"] for p in piezas} == {"facebook", "instagram"}
    r = orq.editar(piezas[0]["id"], "ana", {"title": "Otro título"})
    assert r["status"] == "PENDING_APPROVAL", r["validacion"]["errores"]


@pytest.mark.parametrize("texto", [
    "Escríbenos: https://wa.me/51987654321 y reserva en Surco.",
    "Visita www.canchas-gratis-miraflores.com para jugar en Surco.",
    "Este martes hay turnos en 4 canchas de Surco, Miraflores y San Isidro.",
    "Miraflores te espera este martes por la noche.",
    "Juega este martes en Ate o en SJL.",
    "Este martes por la noche #2x1 en Surco.",
    "Reserva en Surco a las 8pm este martes.",
    "Surco con 50 off este martes por la noche.",
    "Surco con dscto este martes por la noche.",
    "Reserva en Surco y la segunda hora es de regalo.",
    "Reserva en Surco por $80 la hora este martes.",
    "Reserva en Surco por cincuenta soles la hora este martes.",
    "Este martes juega en Surco como en Quito.",
])
def test_guardrails_cierran_los_atajos(texto):
    h = {**H, "cancha": None}
    v = guardrails.validar(_p(texto + LARGO), h, oportunidad=OP, link="https://www.pichangol.app/go/abc")
    assert not v["ok"], texto


def test_guardrails_formatos_de_monto_validos():
    h = {"pais": "PE", "moneda": "S/", "dia": "martes", "franja": "noche",
         "cancha": {"nombre": "Club Uno", "precio_hora": 80.5, "moneda": "S/", "deportes": ["fútbol"]}}
    for t in ("S/80.50", "S/. 80.50", "80.50 soles", "S/ 80.5"):
        v = guardrails.validar(_p(f"Club Uno este martes por la noche desde {t} la hora." + LARGO), h, oportunidad=OP)
        assert v["ok"], (t, v["errores"])
    assert not guardrails.validar(_p("Club Uno desde S/ 1,200 la hora este martes." + LARGO), h, oportunidad=OP)["ok"]


def test_zona_de_otro_pais_y_palabras_comunes():
    hb = {"pais": "BO", "moneda": "Bs", "zona": "Cochabamba"}
    assert not guardrails.validar(_p("Arma tu partido en Miraflores con tu grupo." + LARGO), hb, oportunidad=OP)["ok"]
    hp = {"pais": "PE", "zona": "Surco"}
    assert guardrails.validar(_p("Arma el partido en Surco con tu grupo de siempre." + LARGO), hp, oportunidad=OP)["ok"]


def test_la_pestana_no_pisa_la_tarjeta_de_servicios_de_marketing(client):
    html = client.get("/admin").text
    assert html.count("async function cargarMarketing(") == 1 and "async function mkCargar(" in html
    assert "mkCargar();" in html and "if(sec==='marketing') mkCargar();" in html
