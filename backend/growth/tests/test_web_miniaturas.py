"""Miniaturas de las fotos de la web (`web/miniaturas.py`, ronda 3).

La portada bajaba las fotos ORIGINALES (hasta 600 KB y 4000 px cada una). Ahora
las nuestras pasan por `/web/mini` (se achican UNA vez y se guardan en
`canchas/mini/…`), las de Google y Unsplash solo cambian su parámetro de ancho
y todo lo demás queda igual. Storage y HTTP simulados: nada sale a la red.
"""
import io
import os
import re
import sys
import urllib.error
from urllib.parse import quote, unquote

import pytest
from fastapi.testclient import TestClient
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import config  # noqa: E402
from main import app  # noqa: E402
from web import almacen, miniaturas  # noqa: E402
from test_web_reservas import db  # noqa: E402,F401

SB = "https://sb.test"
FOTO = f"{SB}/storage/v1/object/public/canchas/c1/web_1.jpg?v=17"
cli = TestClient(app)


def _jpeg(w=2000, h=1500, modo="RGB") -> bytes:
    b = io.BytesIO()
    Image.new(modo, (w, h), (40, 140, 90)).save(b, "JPEG" if modo == "RGB" else "PNG", quality=92)
    return b.getvalue()


class _Resp:
    def __init__(self, status=200, headers=None, cuerpo=b""):
        self.status, self.headers, self._c = status, headers or {}, cuerpo

    def read(self, n=-1):
        return self._c if n is None or n < 0 else self._c[:n]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture()
def red(monkeypatch):
    """Storage simulado: `objetos` = URL pública → (cabeceras, bytes);
    `subidas` = lo que el backend subió; `pedidos` = (método, URL)."""
    monkeypatch.setattr(config, "SUPABASE_URL", SB)
    monkeypatch.setattr(config, "SUPABASE_ANON_KEY", "anon")
    monkeypatch.delenv("WEB_MINIATURAS", raising=False)
    miniaturas._hechas.clear()
    miniaturas._fallas.clear()
    estado = {"objetos": {}, "subidas": [], "pedidos": []}

    def abrir(req):
        metodo = req.get_method()
        estado["pedidos"].append((metodo, req.full_url))
        obj = estado["objetos"].get(req.full_url)
        if obj is None:
            raise urllib.error.HTTPError(req.full_url, 400, "Object not found", {}, None)
        cab, cuerpo = obj
        return _Resp(200, cab, b"" if metodo == "HEAD" else cuerpo)

    def subir(bucket, ruta, datos, content_type="image/jpeg", *, max_bytes=None, cache_control=""):
        estado["subidas"].append({"bucket": bucket, "ruta": ruta, "datos": datos, "ct": content_type, "cache": cache_control})
        url = f"{SB}/storage/v1/object/public/{bucket}/{ruta}"
        estado["objetos"][url] = ({"Content-Type": content_type, "ETag": '"m"'}, datos)
        return url + "?v=1"

    monkeypatch.setattr(miniaturas, "_abrir", abrir)
    monkeypatch.setattr(almacen, "subir", subir)
    return estado


def _poner(red, url, cuerpo, etag='"abc123"', tipo="image/jpeg"):
    red["objetos"][url] = ({"Content-Type": tipo, "ETag": etag, "Content-Length": str(len(cuerpo))}, cuerpo)


# ── reconocer y reescribir URLs ──────────────────────────────────────────────

def test_sin_storage_todo_queda_igual(monkeypatch):
    monkeypatch.setattr(config, "SUPABASE_URL", "")
    monkeypatch.setattr(config, "SUPABASE_ANON_KEY", "")
    assert miniaturas.url(FOTO) == FOTO and miniaturas.srcset(FOTO) == ""
    assert "srcset" not in miniaturas.img(FOTO) and f"src='{FOTO.replace('&', '&amp;')}'" in miniaturas.img(FOTO)


def test_solo_nuestro_storage_va_por_web_mini(red):
    assert miniaturas.url(FOTO) == f"/web/mini?u={quote(FOTO, safe='')}&w=480"
    assert miniaturas.url(FOTO, 900) == f"/web/mini?u={quote(FOTO, safe='')}&w=960"
    prod = f"{SB}/storage/v1/object/public/productos/prod_1.jpg"
    assert miniaturas.url(prod).startswith("/web/mini?")
    for ajena in (f"{SB}/storage/v1/object/public/chat/perfiles/a.jpg",          # otro bucket
                  f"{SB}/storage/v1/object/public/verificacion/x/doc.jpg",       # privado
                  f"{SB}/storage/v1/object/public/canchas/mini/canchas/c1/a.jpg/x_480.webp",  # ya es miniatura
                  f"{SB}/storage/v1/object/public/canchas/c1/video.mp4",         # no es foto
                  f"{SB}/storage/v1/object/public/canchas/../verificacion/a.jpg",
                  f"{SB}/storage/v1/object/public/canchas/%2e%2e/verificacion/a.jpg",
                  "http://sb.test/storage/v1/object/public/canchas/c1/a.jpg",     # sin TLS
                  "https://sb.test.evil.com/storage/v1/object/public/canchas/c1/a.jpg",
                  "https://evil.com@sb.test/storage/v1/object/public/canchas/c1/a.jpg",
                  "https://otro.supabase.co/storage/v1/object/public/canchas/c1/a.jpg",
                  "https://example.com/foto.jpg"):
        assert miniaturas.objeto_nuestro(ajena) is None, ajena
        assert miniaturas.url(ajena) == ajena, ajena


def test_google_y_unsplash_solo_bajan_el_ancho_de_la_url(red):
    g = "https://lh3.googleusercontent.com/place-photos/AG9NLj=s4800-w800"
    assert miniaturas.url(g) == "https://lh3.googleusercontent.com/place-photos/AG9NLj=s4800-w480"
    assert miniaturas.url(g, 960) == g  # nunca más grande que lo que se pidió a Google
    assert miniaturas.srcset(g) == ("https://lh3.googleusercontent.com/place-photos/AG9NLj=s4800-w480 480w, "
                                    f"https://lh3.googleusercontent.com/place-photos/AG9NLj=s4800-w720 720w, {g} 960w")
    assert miniaturas.url("https://lh3.googleusercontent.com/p/AF1=w800-h600") == "https://lh3.googleusercontent.com/p/AF1=w480"
    assert miniaturas.url("https://lh3.googleusercontent.com/p/AF1=s1600") == "https://lh3.googleusercontent.com/p/AF1=s480"
    sin = "https://lh3.googleusercontent.com/place-photos/caducada"
    assert miniaturas.url(sin) == sin  # formato desconocido: tal cual
    u = "https://images.unsplash.com/photo-1?w=1200&q=70&auto=format&fit=crop"
    mini = miniaturas.url(u)
    assert "w=480" in mini and "q=70" in mini and "fit=crop" in mini and "w=1200" not in mini
    # Ningún pedido a la red para decidir esto.
    assert red["pedidos"] == []


def test_corte_de_emergencia(red, monkeypatch):
    monkeypatch.setenv("WEB_MINIATURAS", "0")
    g = "https://lh3.googleusercontent.com/p/AF1=w800"
    assert miniaturas.url(FOTO) == FOTO and miniaturas.url(g) == g
    r = cli.get("/web/mini", params={"u": FOTO, "w": 480}, follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == FOTO


def test_img_carga_diferida_prioridad_y_srcset(red):
    h = miniaturas.img(FOTO, "Club <X>")
    assert "loading='lazy'" in h and "decoding='async'" in h and "fetchpriority" not in h
    assert "srcset='/web/mini?u=" in h and "480w" in h and "960w" in h and "sizes='" in h
    assert "alt='Club &lt;X&gt;'" in h and "width='480' height='456'" in h
    p = miniaturas.img(FOTO, w=960, clase="principal", prioridad=True, dims=False)
    assert "fetchpriority='high'" in p and "loading=" not in p and "class='principal'" in p and "width=" not in p
    assert miniaturas.para_js([FOTO]) == [{"s": miniaturas.url(FOTO), "ss": miniaturas.srcset(FOTO)}]


# ── /web/mini ────────────────────────────────────────────────────────────────

def test_web_mini_genera_una_vez_guarda_en_storage_y_redirige(red):
    _poner(red, FOTO, _jpeg())
    r = cli.get("/web/mini", params={"u": FOTO, "w": 480}, follow_redirects=False)
    assert r.status_code == 302 and "max-age=604800" in r.headers["cache-control"]
    destino = r.headers["location"]
    # Ruta determinista: canchas/mini/<bucket>/<ruta original>/<clave16>_<ancho>.webp
    m = re.fullmatch(rf"{SB}/storage/v1/object/public/canchas/mini/canchas/c1/web_1\.jpg/([0-9a-f]{{16}})_480\.webp", destino)
    assert m, destino
    # Una sola descarga genera TODOS los anchos.
    gets = [u for (met, u) in red["pedidos"] if met == "GET"]
    assert gets == [FOTO]
    assert sorted(s["ruta"].rsplit("_", 1)[1] for s in red["subidas"]) == ["480.webp", "720.webp", "960.webp"]
    for s in red["subidas"]:
        assert s["bucket"] == "canchas" and s["ct"] == "image/webp" and "max-age=31536000" == s["cache"]
        im = Image.open(io.BytesIO(s["datos"]))
        ancho = int(s["ruta"].rsplit("_", 1)[1].split(".")[0])
        assert im.format == "WEBP" and im.width == ancho and im.height == round(1500 * ancho / 2000)
        assert len(s["datos"]) < 60_000
    # Ya conocida: el HTML apunta DIRECTO a la miniatura y no hay más red.
    red["pedidos"].clear()
    assert miniaturas.url(FOTO) == destino
    r2 = cli.get("/web/mini", params={"u": FOTO, "w": 960}, follow_redirects=False)
    assert r2.headers["location"].endswith(f"{m.group(1)}_960.webp") and red["pedidos"] == []


def test_variar_v_no_crea_miniaturas_nuevas_y_tras_reiniciar_se_reusa(red):
    _poner(red, FOTO, _jpeg())
    cli.get("/web/mini", params={"u": FOTO, "w": 480}, follow_redirects=False)
    n = len(red["subidas"])
    otra_v = FOTO.replace("?v=17", "?v=99999")
    _poner(red, otra_v, _jpeg())  # mismo archivo (mismo ETag), otro ?v=
    r = cli.get("/web/mini", params={"u": otra_v, "w": 480}, follow_redirects=False)
    assert r.status_code == 302 and len(red["subidas"]) == n  # existía: solo HEAD, sin bajar ni subir
    assert ("GET", otra_v) not in red["pedidos"]
    # "Reinicio" (memoria vacía): HEAD de la original + HEAD de la miniatura y listo.
    miniaturas._hechas.clear()
    red["pedidos"].clear()
    r = cli.get("/web/mini", params={"u": FOTO, "w": 480}, follow_redirects=False)
    assert r.status_code == 302 and "/mini/" in r.headers["location"]
    assert [met for met, _ in red["pedidos"]] == ["HEAD", "HEAD"] and len(red["subidas"]) == n
    # El dueño REEMPLAZA la foto en la misma ruta (ETag nuevo) → miniatura nueva.
    miniaturas._hechas.clear()
    _poner(red, FOTO, _jpeg(1200, 900), etag='"nuevo"')
    r3 = cli.get("/web/mini", params={"u": FOTO, "w": 480}, follow_redirects=False)
    assert r3.headers["location"] != r.headers["location"] and len(red["subidas"]) == n + 3


def test_web_mini_rechaza_urls_ajenas_sin_redirigir(red):
    for u in ("https://example.com/a.jpg", "https://sb.test.evil.com/storage/v1/object/public/canchas/a.jpg",
              f"{SB}/storage/v1/object/public/verificacion/a.jpg", "javascript:alert(1)", ""):
        r = cli.get("/web/mini", params={"u": u, "w": 480}, follow_redirects=False)
        assert r.status_code == 404 and "location" not in r.headers, u
    assert red["pedidos"] == []  # nunca se bajó nada ajeno


def test_falla_redirige_a_la_original_y_no_reintenta_enseguida(red):
    _poner(red, FOTO, b"<html>no soy foto</html>", tipo="text/html")
    r = cli.get("/web/mini", params={"u": FOTO, "w": 480}, follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == FOTO and "max-age=60" in r.headers["cache-control"]
    assert red["subidas"] == []
    red["pedidos"].clear()
    cli.get("/web/mini", params={"u": FOTO, "w": 480}, follow_redirects=False)
    assert red["pedidos"] == []  # caché negativa: no martilla Storage
    # Una original que no existe (borrada) también cae a la original.
    miniaturas._fallas.clear()
    del red["objetos"][FOTO]
    r = cli.get("/web/mini", params={"u": FOTO, "w": 480}, follow_redirects=False)
    assert r.headers["location"] == FOTO


def test_achicar_no_agranda_respeta_alfa_y_rechaza_bombas(monkeypatch):
    chica = Image.open(io.BytesIO(miniaturas.achicar(_jpeg(300, 200), 480)))
    assert chica.size == (300, 200)  # nunca agranda
    png = io.BytesIO()
    Image.new("RGBA", (1000, 1000), (0, 0, 0, 0)).save(png, "PNG")
    assert Image.open(io.BytesIO(miniaturas.achicar(png.getvalue(), 480))).mode == "RGBA"
    assert miniaturas.achicar(b"basura", 480) is None
    monkeypatch.setattr(miniaturas, "MAX_PIXELES", 1000)
    assert miniaturas.achicar(_jpeg(100, 100), 480) is None


def test_al_subir_una_foto_desde_la_web_las_miniaturas_quedan_listas(monkeypatch):
    """`almacen.subir` (foto de cancha/producto) dispara `precalentar` con los
    bytes en mano: el primer visitante ya encuentra la miniatura."""
    vistos, cabeceras = [], []
    monkeypatch.setattr(config, "SUPABASE_URL", SB)
    monkeypatch.setattr(config, "SUPABASE_ANON_KEY", "anon")
    monkeypatch.setattr(miniaturas, "precalentar", lambda u, d: vistos.append((u, len(d))))
    monkeypatch.setattr(almacen.urllib.request, "urlopen",
                        lambda req, timeout=0: cabeceras.append(dict(req.header_items())) or _Resp(200, {}, b"{}"))
    url = almacen.subir("canchas", "c1/web_5.jpg", b"jpgbytes", "image/jpeg")
    almacen.subir("canchas", "c1/clip.mp4", b"mp4", "video/mp4")              # video: no
    almacen.subir("canchas", "mini/canchas/c1/a.jpg/x_480.webp", b"w", "image/webp", cache_control="max-age=9")
    assert vistos == [(url, 8)]  # la miniatura y el video no disparan el gancho
    assert "Cache-control" not in cabeceras[0] and cabeceras[2]["Cache-control"] == "max-age=9"


def test_precalentar_genera_desde_los_bytes_sin_bajar_nada(red, monkeypatch):
    monkeypatch.setattr(miniaturas, "PRECALENTAR", True)

    class _Hilo:
        def __init__(self, target, **kw):
            self.t = target

        def start(self):
            self.t()

    monkeypatch.setattr(miniaturas.threading, "Thread", _Hilo)
    datos = _jpeg()
    _poner(red, FOTO, datos)
    miniaturas.precalentar(FOTO, datos)
    assert ("GET", FOTO) not in red["pedidos"] and len(red["subidas"]) == 3
    assert miniaturas.url(FOTO).startswith(f"{SB}/storage/v1/object/public/canchas/mini/canchas/c1/web_1.jpg/")
    miniaturas.precalentar("https://example.com/a.jpg", datos)  # ajena: nada
    assert len(red["subidas"]) == 3


# ── páginas ──────────────────────────────────────────────────────────────────

def test_portada_y_ficha_usan_miniaturas(red, db):
    db.canchas["c_lima"]["foto_url"] = FOTO
    db.canchas["c_lima"]["fotos"] = [FOTO, FOTO.replace("web_1", "web_2")]
    html = cli.get("/").text
    assert "/web/mini?u=" in html and "srcset='/web/mini?u=" in html and "decoding='async'" in html
    assert "fetchpriority='high'" in html  # primera foto visible: sin esperar al scroll
    assert f"src='{FOTO}'" not in html  # la original ya no viaja a la portada
    assert '"sizesTarjeta"' in html
    ficha = cli.get("/reservar/c_lima").text
    assert "class='principal'" in ficha and "w=960" in ficha and "fetchpriority='high'" in ficha
    assert f"src='{FOTO}'" not in ficha


def test_web_foto_manda_miniaturas_alineadas_sin_cambiar_fotos(red, monkeypatch):
    from web import router as wr
    g = ["https://lh3.googleusercontent.com/place-photos/A=s4800-w800", "https://lh3.googleusercontent.com/place-photos/B=s4800-w800"]
    monkeypatch.setattr(wr.descubrir, "fotos_de_lugar", lambda *a, **k: list(g))
    j = cli.get("/web/foto", params={"id": "gp_x", "nombre": "Cancha X", "lat": -12.1, "lng": -77.0}).json()
    assert j["fotos"] == g  # el APK sigue leyendo `fotos` tal cual
    assert [m["s"] for m in j["minis"]] == [x.replace("w800", "w480") for x in g]
    assert j["minis_g"][0]["s"] == g[0]  # 960 > 800: la de Google tal cual


# ── barrido de Storage ───────────────────────────────────────────────────────

def test_barrido_reconoce_miniaturas_y_nunca_las_reporta_como_desconocidas():
    import storage_limpieza as sl
    assert "'mini'" in sl._SQL_DESCONOCIDOS
    sql = sl._CONSULTAS["miniaturas"]
    assert sl._REFERENCIA["miniaturas"] == "storage.objects"
    patron = re.search(r"o\.name ~ '([^']+)'", sql).group(1)
    extrae = re.search(r"regexp_replace\(o\.name, '([^']+)', '\\1'\)", sql).group(1)
    clave = "0123456789abcdef"
    nuestra = miniaturas._ruta_mini("canchas", "u17/1787107414861_0.jpg", clave, 480)
    assert re.fullmatch(patron, nuestra)
    assert re.sub(extrae, r"\1", nuestra) == "u17/1787107414861_0.jpg"
    assert re.sub(extrae, r"\1", miniaturas._ruta_mini("productos", "prod_1.jpg", clave, 960)) == "prod_1.jpg"
    for ajena in ("mini/otra/cosa.webp", "mini/canchas/c1/a.jpg/NOHEX_480.webp", "mini/chat/x/a.jpg/" + clave + "_480.webp"):
        assert not re.fullmatch(patron, ajena), ajena
