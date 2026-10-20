"""Marketing IA de locales Pro: fotos reales ambientadas con IA, video con movimiento,
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

    real = ia_media.encargar_video

    def encargar(fotos, **k):
        llamadas["video"] += 1
        assert fotos[0].startswith("mem:amb_") and fotos[1:] == [FOTO.replace("a.jpg", "b.jpg")]   # ambientada + reales
        return real(fotos, **k)
    monkeypatch.setattr(ia_media, "ambientar", ambientar)
    monkeypatch.setattr(ia_media, "encargar_video", encargar)
    return llamadas


# ── tope de gasto ────────────────────────────────────────────────────────────
def test_tope_de_gasto_mensual_reserva_y_devuelve(monkeypatch):
    monkeypatch.setattr(config, "OPENAI_API_KEY", "sk-test")
    orq.guardar_configuracion({"media_tope_usd": 1, "costo_imagen": 0.4, "video_seg": 8})
    assert ia_media.alcanza_imagen() and ia_media.alcanza_video()        # el video no cuesta: basta la imagen
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


def test_video_con_movimiento_se_arma_de_verdad_con_ffmpeg(monkeypatch):
    """Sin red ni costo: las fotos → video cuadrado con logo, rótulo, cierre y música."""
    from marketing import video_pulido
    if not video_pulido.ffmpeg_exe():
        pytest.skip("FFmpeg no disponible")
    monkeypatch.setattr(ia_media, "_descargar", lambda url: _jpeg((30, 90, 60) if "a" in url else (200, 120, 40), (640, 480)))
    v = ia_media.encargar_video(["mem:amb_1", "https://x/b.jpg"], mood="chill")
    assert v["estado"] == "generando" and v["proveedor"] == "movimiento" and v["segundos"] == 12
    assert ia_media.encargar_video([])["estado"] == "fallo"
    listo = ia_media.consultar_video({**v, "segundos": 8}, titulo="Tenis en Chaclacayo")
    assert listo["estado"] == "listo", listo.get("motivo")
    mp4 = listo["_mp4"]
    assert b"ftyp" in mp4[:32] and len(mp4) > 10_000
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        f.write(mp4)
    info = video_pulido.sondear(f.name)
    os.remove(f.name)
    assert info["ancho"] == info["alto"] and float(info["duracion"]) > 6          # cuadrado, fotos + intro + cierre
    viejo = ia_media.consultar_video({"estado": "generando", "job": "video_123"})   # pedido viejo a Sora (API cerrada)
    assert viejo["estado"] == "fallo" and "Sora" in viejo["motivo"]


def test_marcar_video_marca_el_ambientado_y_quitarlo_apaga_el_video():
    cfg = orq.guardar_configuracion({"video_ia": True, "ia_ambientar": False})
    assert cfg["video_ia"] and cfg["ia_ambientar"]
    cfg = orq.guardar_configuracion({"ia_ambientar": False})
    assert not cfg["video_ia"] and not cfg["ia_ambientar"]


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


def test_video_se_espera_se_guarda_y_se_publica(pro, monkeypatch, _limpio):
    orq.guardar_configuracion({"video_ia": True})
    p = [p for p in orq.planificar("PE", usar_ia=False)["piezas"] if p["oportunidad"]["tipo"] == "local_pro"][0]
    assert p["media_origen"] == "video_ia" and pro["video"] == 1
    with pytest.raises(orq.Rechazo):
        orq.aprobar(p["id"], "ana")                                   # no se aprueba a ciegas
    monkeypatch.setattr(ia_media, "consultar_video", lambda v, **k: {**v, "estado": "listo", "_mp4": b"MP4DATA"})
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
    monkeypatch.setattr(ia_media, "consultar_video", lambda v, **k: {**v, "estado": "fallo", "motivo": "policy"})
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


def test_hacer_video_de_una_pieza_ya_ambientada(pro, monkeypatch, _limpio):
    p = [p for p in orq.planificar("PE", usar_ia=False)["piezas"] if p["oportunidad"]["tipo"] == "local_pro"][0]
    assert p["media_origen"] == "ia_ambientada"
    orq.aprobar(p["id"], "ana")
    r = orq.pedir_video(p["id"], "ana")
    assert r["media_origen"] == "video_ia" and r["status"] == "PENDING_APPROVAL"     # se revisa el video antes de salir
    assert r["oportunidad"]["media"]["video_ia"]["fotos"] == p["oportunidad"]["media"]["fotos"]
    assert guardrails.AVISO_IA in r["body"]
    with pytest.raises(orq.Rechazo):
        orq.pedir_video(p["id"], "ana")                                       # ya se está armando
    monkeypatch.setattr(ia_media, "consultar_video", lambda v, **k: {**v, "estado": "listo", "_mp4": b"MP4"})
    ia_media.procesar_videos()
    assert ia_media.gasto()["videos"] == 1 and ia_media.gasto()["usd"] == 0   # el video no suma costo (la imagen está simulada)
    orq.guardar_configuracion({"ia_ambientar": False})
    otra = [x for x in orq.planificar("PE", forzar=True, usar_ia=False)["piezas"] if x["media_origen"] == "foto_dueno"]
    if otra:
        with pytest.raises(orq.Rechazo):
            orq.pedir_video(otra[0]["id"], "ana")                             # sin foto ambientada no hay video


# ── Veo de Google (API de Gemini simulada) ───────────────────────────────────
@pytest.fixture
def veo(monkeypatch):
    for k in ("ai_mkt_video_motor", "ai_mkt_media_gasto", "ai_mkt_media_tope_usd", "ai_mkt_costo_video_seg"):
        monkeypatch.setitem(stores.config, k, "")
    monkeypatch.setattr(config, "GEMINI_API_KEY", "g-test")
    monkeypatch.setattr(config, "VEO_MODEL", "veo-test")
    monkeypatch.setattr(ia_media, "_descargar", lambda url: _jpeg((30, 90, 60), (640, 480)))
    estado = {"pedidos": [], "consultas": 0, "listo": False, "error": None, "sin_clip": False}

    def gemini(metodo, ruta, cuerpo=None, **k):
        if metodo == "POST":
            estado["pedidos"].append((ruta, cuerpo))
            return {"name": "models/veo-test/operations/op1"}
        estado["consultas"] += 1
        if not estado["listo"]:
            return {"name": ruta, "done": False}
        if estado["error"]:
            return {"name": ruta, "done": True, "error": {"message": estado["error"]}}
        if estado["sin_clip"]:
            return {"name": ruta, "done": True, "response": {"generateVideoResponse": {}}}
        return {"name": ruta, "done": True, "response": {"generateVideoResponse": {
            "generatedSamples": [{"video": {"uri": "https://generativelanguage.googleapis.com/v1beta/files/x:download"}}]}}}
    monkeypatch.setattr(ia_media, "_gemini", gemini)
    monkeypatch.setattr(ia_media, "_veo_descargar", lambda uri: b"CLIP")
    monkeypatch.setattr(ia_media, "_pulir_clip", lambda v, clip, titulo, **k: {**v, "estado": "listo", "_mp4": b"PULIDO" + clip})
    return estado


def test_motor_veo_se_elige_en_la_torre_y_exige_llave(veo, monkeypatch):
    assert ia_media.motor_video() == "movimiento"            # por defecto, en casa
    cfg = orq.guardar_configuracion({"video_motor": "veo", "costo_video_seg": 0.4})
    assert cfg["video_motor"] == "veo" and cfg["costo_video_seg"] == 0.4
    assert ia_media.motor_video() == "veo" and ia_media.costo_veo() == pytest.approx(3.2)
    with pytest.raises(ValueError):
        orq.guardar_configuracion({"video_motor": "sora"})
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")
    assert ia_media.motor_video() == "movimiento"            # sin llave, nunca Veo


def test_veo_pide_consulta_descarga_y_cobra_una_vez(veo):
    orq.guardar_configuracion({"video_motor": "veo", "costo_video_seg": 0.15, "media_tope_usd": 20})
    v = ia_media.encargar_video([FOTO], mood="chill", deporte="tenis", pais="EC")
    assert v["proveedor"] == "veo" and v["segundos"] == ia_media.VEO_SEGUNDOS
    v = ia_media.consultar_video(v, titulo="Club X")          # 1.ª vuelta: manda el pedido
    ruta, cuerpo = veo["pedidos"][0]
    assert ruta == "models/veo-test:predictLongRunning"
    inst = cuerpo["instances"][0]
    assert "tenis" in inst["prompt"] and "Ecuador" in inst["prompt"] and inst["image"]["mimeType"] == "image/jpeg"
    assert v["estado"] == "generando" and v["operacion"].endswith("op1")
    assert ia_media.gasto()["usd"] == pytest.approx(1.2)      # 8 s × 0.15 reservado al pedir
    assert ia_media.consultar_video(v) == v                  # aún no termina: sin cambios
    veo["listo"] = True
    r = ia_media.consultar_video(v, titulo="Club X")
    assert r["estado"] == "listo" and r["_mp4"] == b"PULIDOCLIP" and r["proveedor"] == "veo"
    assert len(veo["pedidos"]) == 1 and ia_media.gasto()["usd"] == pytest.approx(1.2)


@pytest.mark.parametrize("caso", ["error", "sin_clip"])
def test_veo_falla_devuelve_el_gasto_y_se_arma_en_casa(veo, monkeypatch, caso):
    orq.guardar_configuracion({"video_motor": "veo", "media_tope_usd": 20})
    casa = []
    monkeypatch.setattr("marketing.foto_video.generar", lambda fotos, salida, **k: casa.append(len(fotos)) or open(salida, "wb").write(b"x"))
    monkeypatch.setattr("marketing.video_pulido.pulir", lambda e, s, o: open(s, "wb").write(b"CASA"))
    v = ia_media.consultar_video(ia_media.encargar_video([FOTO]))
    veo["listo"] = True
    veo["error"] = "safety" if caso == "error" else None
    veo["sin_clip"] = caso == "sin_clip"
    r = ia_media.consultar_video(v)
    assert r["estado"] == "listo" and r["proveedor"] == "movimiento" and r["_mp4"] == b"CASA" and r["nota_veo"]
    assert casa == [1] and ia_media.gasto()["usd"] == 0      # Veo no cobró: se devolvió


def test_veo_sin_tope_o_que_tarda_demasiado_va_a_casa(veo, monkeypatch):
    orq.guardar_configuracion({"video_motor": "veo", "media_tope_usd": 0.5})   # 8 s × 0.15 = 1.2 no alcanza
    r = ia_media._veo_paso(ia_media.encargar_video([FOTO]), "")
    assert r["proveedor"] == "movimiento" and "tope" in r["nota_veo"] and not veo["pedidos"]
    orq.guardar_configuracion({"media_tope_usd": 20})
    v = ia_media._veo_paso(ia_media.encargar_video([FOTO]), "")
    v["enviado_en"] -= ia_media.VEO_ESPERA_MAX + 1
    r = ia_media._veo_paso(v, "")
    assert r["proveedor"] == "movimiento" and "tard" in r["nota_veo"]


def test_resumen_de_la_torre_dice_el_motor_de_video(veo):
    orq.guardar_configuracion({"video_motor": "veo"})
    mi = orq.resumen()["media_ia"]
    assert mi["veo_disponible"] and mi["veo_modelo"] == "veo-test" and mi["motor_efectivo"] == "veo"


def test_clip_de_veo_se_pule_de_verdad_con_ffmpeg(tmp_path):
    from marketing import foto_video
    crudo = tmp_path / "veo.mp4"
    foto_video.generar([_jpeg((30, 90, 60), (640, 360))], str(crudo), formato="horizontal", segundos=2)
    r = ia_media._pulir_clip({"mood": "chill"}, crudo.read_bytes(), "Club X", musica="fondo")
    assert r["estado"] == "listo" and r["_mp4"][4:8] == b"ftyp" and r["bytes"] > 1000
