"""Marketing IA de locales Pro: fotos reales ambientadas con IA, video Sora,
cupo fijo al mes y tope de gasto (OpenAI simulado: nada sale a la red)."""

import base64
import io
import json
import os
import sys
import urllib.error
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config  # noqa: E402
from db.store import stores  # noqa: E402
from marketing.agente_ia import creativo, estratega, guardrails, ia_media, orquestador as orq, publicador  # noqa: E402
from tests.test_agente_ia import _cancha, _crudo, _fb, _limpio, _snap  # noqa: E402,F401

FOTO = "https://abc.supabase.co/storage/v1/object/public/canchas/k1/a.jpg"


def _jpeg(color=(20, 120, 60), tam=(64, 48)) -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", tam, color).save(buf, "JPEG")
    return buf.getvalue()


def _crudo_pro():
    c = _crudo()
    c["canchas"][1] = _cancha(1, fotos=[FOTO, FOTO.replace("a.jpg", "b.jpg")])
    return c


def _snap_pro():
    return _snap(_crudo_pro(), destacar_pro=True, pro_activo=lambda e: e == "d1@x.pe")


@pytest.fixture
def pro(monkeypatch):
    monkeypatch.setattr(orq, "snapshot", lambda pais: _snap_pro())
    monkeypatch.setattr(config, "OPENAI_API_KEY", "sk-test")
    orq.guardar_configuracion({"destacar_pro": True, "ia_ambientar": True, "pro_cupo_mes": 4})
    llamadas = {"ambientar": 0, "video": 0}

    def ambientar(url, **k):
        llamadas["ambientar"] += 1
        assert url == FOTO                      # siempre la foto REAL del dueño
        return _jpeg(), "ok"

    def encargar(url, **k):
        llamadas["video"] += 1
        assert url == FOTO                      # Sora parte de la foto real (sin personas)
        return {"estado": "generando", "job": "video_123", "segundos": 8, "usd": 0.8, "pedido_en": 0}
    monkeypatch.setattr(ia_media, "ambientar", ambientar)
    monkeypatch.setattr(ia_media, "encargar_video", encargar)
    return llamadas


# ── tope de gasto ────────────────────────────────────────────────────────────
def test_tope_de_gasto_mensual_reserva_y_devuelve(monkeypatch):
    monkeypatch.setattr(config, "OPENAI_API_KEY", "sk-test")
    orq.guardar_configuracion({"media_tope_usd": 1, "costo_imagen": 0.4, "costo_video_seg": 0.1, "video_seg": 4})
    assert ia_media.alcanza_imagen() and ia_media.alcanza_video()        # 0.4 + 0.4 ≤ 1
    assert ia_media._reservar(0.4, "imagen") and ia_media._reservar(0.4, "imagen")
    assert not ia_media.alcanza_imagen() and not ia_media._reservar(0.4, "imagen")
    ia_media._devolver(0.4, "imagen")
    g = ia_media.gasto()
    assert g["usd"] == 0.4 and g["imagenes"] == 1 and g["disponible_usd"] == 0.6
    stores.config["ai_mkt_media_gasto"] = json.dumps({"mes": "2020-01", "usd": 99})
    assert ia_media.gasto()["usd"] == 0                                # mes nuevo, contador nuevo
    with pytest.raises(ValueError):
        orq.guardar_configuracion({"video_seg": 7})
    monkeypatch.setattr(config, "OPENAI_API_KEY", "")
    assert not ia_media.alcanza_imagen()


def test_ambientar_edita_la_foto_real_y_conserva_el_lugar(monkeypatch):
    monkeypatch.setattr(config, "OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(ia_media, "_descargar", lambda url: _jpeg())
    vistos = []

    def fake(metodo, ruta, *, cuerpo=None, tipo=None, **k):
        vistos.append((metodo, ruta, cuerpo, tipo))
        return {"data": [{"b64_json": base64.b64encode(_jpeg((200, 200, 0))).decode()}]}
    monkeypatch.setattr(ia_media, "_openai", fake)
    jpg, motivo = ia_media.ambientar(FOTO, deporte="fútbol", pais="PE", hora=20)
    assert motivo == "ok" and jpg[:2] == b"\xff\xd8"
    metodo, ruta, cuerpo, tipo = vistos[0]
    assert (metodo, ruta) == ("POST", "images/edits") and tipo.startswith("multipart/form-data")
    assert b"Keep the venue EXACTLY" in cuerpo and b"input_fidelity" in cuerpo and b"floodlights" in cuerpo
    assert ia_media.gasto()["imagenes"] == 1

    def rechazo(*a, **k):
        raise urllib.error.HTTPError("u", 400, "bad", {}, io.BytesIO(b'{"error":{"message":"moderation"}}'))
    monkeypatch.setattr(ia_media, "_openai", rechazo)
    jpg, motivo = ia_media.ambientar(FOTO, deporte="fútbol")
    assert jpg is None and "moderation" in motivo
    assert ia_media.gasto()["imagenes"] == 1                           # el rechazo no se cobra


def test_sora_encarga_y_consulta_sin_bloquear(monkeypatch):
    monkeypatch.setattr(config, "OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(ia_media, "_descargar", lambda url: _jpeg(tam=(1000, 800)))
    vistos = []

    def fake(metodo, ruta, *, cuerpo=None, tipo=None, crudo=False, **k):
        vistos.append((metodo, ruta))
        if metodo == "POST":
            assert b'name="input_reference"' in cuerpo and b"720x1280" in cuerpo
            return {"id": "video_9", "status": "queued"}
        if ruta.endswith("/content"):
            return b"MP4"
        return {"status": "completed"}
    monkeypatch.setattr(ia_media, "_openai", fake)
    v = ia_media.encargar_video(FOTO, deporte="tenis")
    assert v["estado"] == "generando" and v["job"] == "video_9" and ia_media.gasto()["videos"] == 1
    listo = ia_media.consultar_video(v)
    assert listo["estado"] == "listo" and listo["_mp4"] == b"MP4"
    monkeypatch.setattr(ia_media, "_openai", lambda *a, **k: {"status": "failed", "error": {"message": "policy"}})
    assert ia_media.consultar_video(v) == {**v, "estado": "fallo", "motivo": "policy"}


# ── cupo fijo al mes ─────────────────────────────────────────────────────────
def test_cupo_pro_se_reparte_en_el_mes_y_rota():
    s = _snap(_crudo(4, canchas=[_cancha(i, fotos=[FOTO]) for i in range(4)]), destacar_pro=True, pro_activo=lambda e: True)
    # 19 de octubre, cupo 4 → a esta altura cada local debería llevar ceil(4·19/31) = 3.
    out = estratega.pro_del_dia(s, cupo=4, usados={"club numero 0": 3, "club numero 1": 1, "club numero 2": 2},
                                ultimo={"club numero 2": "2026-10-01"}, max_dia=2)
    assert [o["destacadas"] for o in out] == [["k3"], ["k1"]]       # el más atrasado primero
    assert all(o["tipo"] == "local_pro" and o["hechos"]["cancha"]["nombre"] for o in out)
    assert estratega.pro_del_dia(s, cupo=4, usados={}, ya={"club numero 0", "club numero 1", "club numero 2"}, max_dia=3)[0]["destacadas"] == ["k3"]
    assert estratega.pro_del_dia(s, cupo=0, usados={}) == []
    sin_fotos = _snap(_crudo(2), destacar_pro=True, pro_activo=lambda e: True)
    assert estratega.pro_del_dia(sin_fotos, cupo=4, usados={}) == []   # sin fotos reales no hay pieza Pro


def test_local_que_llego_a_su_cupo_no_aparece_en_otras_oportunidades():
    s = _snap_pro()
    lista = {c["id"]: c for c in s["canchas_lista"]}
    cands = [{"id": "c1", "destacadas": ["k1"]}, {"id": "c2", "destacadas": []}]
    assert [c["id"] for c in estratega._sin_pro_agotado(cands, lista, 4, {"club numero 1": 4})] == ["c2"]
    assert [c["id"] for c in estratega._sin_pro_agotado(cands, lista, None, {"club numero 1": 9})] == ["c1", "c2"]


# ── ciclo completo ───────────────────────────────────────────────────────────
def test_pieza_pro_con_foto_ambientada_avisa_que_es_ia(pro, _limpio):
    r = orq.planificar("PE", usar_ia=False)
    pro_p = [p for p in r["piezas"] if (p["oportunidad"] or {}).get("tipo") == "local_pro"]
    assert len(pro_p) == 1, [p["oportunidad"]["tipo"] for p in r["piezas"]]
    p = pro_p[0]
    assert p["media_origen"] == "ia_ambientada" and p["status"] == "PENDING_APPROVAL", p["validacion"]
    assert p["body"].endswith(guardrails.AVISO_IA)
    receta = p["oportunidad"]["media"]
    assert receta["fotos"][0].startswith("mem:amb_") and receta["fotos"][1] == FOTO.replace("a.jpg", "b.jpg")
    assert orq.uso_pro("PE")[0] == {"club numero 1": 1}
    # editar no duplica ni pierde el aviso; quitarlo a mano no es posible
    e = orq.editar(p["id"], "ana", {"texto": orq.solo_texto(p) + "\n\n" + guardrails.AVISO_IA})
    assert e["body"].count(guardrails.AVISO_IA) == 1 and e["status"] == "PENDING_APPROVAL"
    # otra versión reusa la imagen ya pagada
    n = orq.regenerar(p["id"], "ana", usar_ia=False)
    assert pro["ambientar"] == 1 and n["oportunidad"]["media"]["fotos"] == receta["fotos"]


OP = {"destacadas": ["k1"], "objetivo": "promo_cancha", "kpi": "reservas_atribuidas"}


def test_guardrail_exige_el_aviso_de_ia():
    h = {"pais": "PE", "moneda": "S/", "cancha": {"nombre": "Club Numero 1"}}
    p = {"title": "Juega en Club Numero 1", "subtitle": "", "etiqueta": "", "body": "Arma tu pichanga en Club Numero 1.", "hashtags": []}
    v = guardrails.validar(p, h, oportunidad=OP, media_origen="ia_ambientada")
    assert any("aviso de IA" in e for e in v["errores"])
    v = guardrails.validar({**p, "body": p["body"] + "\n\n" + guardrails.AVISO_IA}, h, oportunidad=OP,
                           media_origen="ia_ambientada")
    assert v["ok"], v["errores"]
    v = guardrails.validar({**p, "body": "Así luce la cancha hoy.\n\n" + guardrails.AVISO_IA}, h, oportunidad=OP,
                           media_origen="video_ia")
    assert not v["ok"]


def test_sin_tope_o_sin_ia_sale_con_las_fotos_reales(pro, monkeypatch, _limpio):
    orq.guardar_configuracion({"media_tope_usd": 0})
    p = [p for p in orq.planificar("PE", usar_ia=False)["piezas"] if p["oportunidad"]["tipo"] == "local_pro"][0]
    assert p["media_origen"] == "foto_dueno" and guardrails.AVISO_IA not in p["body"] and pro["ambientar"] == 0


def test_video_sora_se_espera_se_guarda_y_se_publica(pro, monkeypatch, _limpio):
    orq.guardar_configuracion({"video_ia": True})
    p = [p for p in orq.planificar("PE", usar_ia=False)["piezas"] if p["oportunidad"]["tipo"] == "local_pro"][0]
    assert p["media_origen"] == "video_ia" and pro["video"] == 1
    with pytest.raises(orq.Rechazo):
        orq.aprobar(p["id"], "ana")                                   # no se aprueba a ciegas
    monkeypatch.setattr(ia_media, "consultar_video", lambda v: {**v, "estado": "listo", "_mp4": b"MP4DATA"})
    assert ia_media.procesar_videos() == 1
    v = _limpio.contenido(p["id"])["oportunidad"]["media"]["video_ia"]
    assert v["estado"] == "listo" and v["url"] == f"mem:{p['id']}.mp4"
    from marketing import post_redes
    monkeypatch.setattr(post_redes, "configurado", lambda: True)
    monkeypatch.setattr(post_redes, "registrar", lambda e: e)
    subidos = []

    def video(texto, titulo, ruta):
        subidos.append((texto, open(ruta, "rb").read()))
        return {"ok": True, "post_id": "v1", "url": "https://facebook.com/v1"}
    monkeypatch.setattr(post_redes, "publicar_video_facebook", video)
    monkeypatch.setattr(post_redes, "publicar_facebook", lambda *a: pytest.fail("debió subir el video"))
    orq.aprobar(p["id"], "ana", datetime.now(timezone.utc) - timedelta(minutes=1))
    assert publicador.tick(snapshot_de=orq.snapshot) >= 1
    assert subidos and subidos[0][1] == b"MP4DATA" and guardrails.AVISO_IA in subidos[0][0]
    assert _limpio.contenido(p["id"])["status"] == "PUBLISHED"


def test_video_en_curso_no_se_publica_y_si_falla_sale_la_foto(pro, monkeypatch, _limpio):
    orq.guardar_configuracion({"video_ia": True, "modo": "auto_validado"})
    llamadas = _fb(monkeypatch, [])
    p = [p for p in orq.planificar("PE", usar_ia=False)["piezas"] if p["oportunidad"]["tipo"] == "local_pro"][0]
    _limpio.actualizar_contenido(p["id"], status="APPROVED", scheduled_at=datetime.now(timezone.utc) - timedelta(minutes=1))
    publicador.publicar(_limpio.contenido(p["id"]), snapshot=orq.snapshot("PE"))
    c = _limpio.contenido(p["id"])
    assert c["status"] == "APPROVED" and c["intentos"] == 0 and "video" in c["error"] and not llamadas
    monkeypatch.setattr(ia_media, "consultar_video", lambda v: {**v, "estado": "fallo", "motivo": "policy"})
    ia_media.procesar_videos()
    _limpio.actualizar_contenido(p["id"], scheduled_at=datetime.now(timezone.utc) - timedelta(minutes=1))
    publicador.publicar(_limpio.contenido(p["id"]), snapshot=orq.snapshot("PE"))
    assert _limpio.contenido(p["id"])["status"] == "PUBLISHED" and len(llamadas) == 1


def test_cupo_se_cumple_y_no_pasa_del_mes(pro, _limpio):
    orq.guardar_configuracion({"pro_cupo_mes": 1})
    primera = orq.planificar("PE", usar_ia=False)
    assert sum(p["oportunidad"]["tipo"] == "local_pro" for p in primera["piezas"]) == 1
    otra = orq.planificar("PE", forzar=True, usar_ia=False)              # reemplaza las no aprobadas → vuelve a tocar
    assert sum(p["oportunidad"]["tipo"] == "local_pro" for p in otra["piezas"]) == 1
    pid = next(p["id"] for p in otra["piezas"] if p["oportunidad"]["tipo"] == "local_pro")
    orq.aprobar(pid, "ana")
    _limpio.actualizar_contenido(pid, status="PUBLISHED")
    stores.config["ai_mkt_ultimo_plan"] = "{}"
    tercera = orq.planificar("PE", forzar=True, usar_ia=False)
    assert not any(p["oportunidad"]["tipo"] in ("local_pro", "cancha_destacada", "promo_real") for p in tercera["piezas"])
