"""Abrir en la APP desde el navegador del celular (pedido del director,
28-sep-2026): en Android con la app instalada, la web salta a la misma
pantalla del APK; sin app, sigue en el navegador. En escritorio no cambia nada.
Aquí se verifica que TODAS las páginas web llevan el script, que su lógica
(intent:// con fallback a la misma URL) y las rutas que enruta son las mismas
que declara el manifest del APK, y que la página del campeonato (fuera del
shell) también lo incluye."""
import os
import re
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from web import ui  # noqa: E402
from marketing import campeonato_web  # noqa: E402
from tests.test_web_reservas import client, db  # noqa: E402,F401


def test_toda_pagina_web_lleva_el_salto_a_la_app(db):
    for ruta in ("/", "/canchas", "/reservar/c_lima1", "/entrar"):
        r = client.get(ruta)
        assert r.status_code == 200, ruta
        assert "pcgAbrirApp" in r.text, ruta
        assert "scheme=pichangol;package=pe.ebim.pichangol" in r.text, ruta
    js = ui.JS_ABRIR_APP
    # Solo Android con navegador real; el WebView del propio APK y el iPhone no.
    assert "/Android/i.test(ua)" in js and "wv" in js
    # El fallback es la MISMA página con ?web=1 (sigue en el navegador, no a Play).
    assert "searchParams.set('web', '1')" in js
    assert "S.browser_fallback_url=" in js
    # Sin app se recuerda 7 días y no se insiste; banner con ✕.
    assert "pcg_sin_app" in js and "7*24*3600*1000" in js
    assert "Abrir en la app Pichangol" in js and "pcg_app_banner_off" in js
    # El paquete viene de la constante (no del texto a mano).
    assert ui.APP_PAQUETE == "pe.ebim.pichangol"


def test_rutas_del_script_son_las_del_manifest_y_del_apk():
    """Espejo: lo que la web intenta abrir en la app debe estar declarado como
    App Link en el manifest (configure_platforms) y enrutado en EnlacesService."""
    import importlib.util
    ruta_tool = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "tool", "configure_platforms.py"))
    spec = importlib.util.spec_from_file_location("configure_platforms", ruta_tool)
    cp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cp)
    manifest = ('<manifest xmlns:android="http://schemas.android.com/apk/res/android">'
                '<application><activity android:name=".MainActivity" android:launchMode="singleTop">'
                '</activity></application></manifest>')
    out = cp.android_manifest(manifest)
    for host in ("www.pichangol.app", "pichangol.app", "pg.ebim.pe"):
        assert f'android:host="{host}" android:path="/"' in out
        assert f'android:host="{host}" android:path="/canchas"' in out
        for pref in ("/c/", "/reservar/", "/reserva/", "/academia/", "/l/", "/mis-reservas", "/anfitrion"):
            assert f'android:host="{host}" android:pathPrefix="{pref}"' in out, pref
    assert 'android:autoVerify="true"' in out and 'android:scheme="pichangol"' in out
    # /admin, /legal y /lugar se quedan en el navegador.
    for fuera in ("/admin", "/legal", "/lugar"):
        assert f'pathPrefix="{fuera}' not in out
    # El regex del script acepta exactamente esas rutas.
    m = re.search(r"var RUTAS = /(.+?)/;", ui.JS_ABRIR_APP)
    assert m
    rutas_js = m.group(1)
    for esperado in ("canchas$", "reservar\\/", "reserva\\/", "academia\\/", "l\\/", "mis-reservas", "c\\/", "anfitrion"):
        assert esperado in rutas_js, esperado
    # El APK enruta las mismas secciones.
    dart = open(os.path.join(os.path.dirname(ruta_tool), "..", "lib", "services", "enlaces_service.dart"), encoding="utf-8").read()
    for caso in ("case 'reservar':", "case 'reserva':", "case 'mis-reservas':", "case 'academia':", "case 'l':", "case 'anfitrion':"):
        assert caso in dart, caso
    assert "static String rutaWebDe(Uri uri)" in dart


def test_pagina_del_campeonato_tambien_salta_a_la_app(monkeypatch):
    data = {"nombre": "Liga", "deporte": "tenis", "formato": "liga",
            "inscripcionAbierta": True, "participantes": [], "partidos": []}
    monkeypatch.setattr(campeonato_web, "obtener_campeonato", lambda _id: data)
    r = client.get("/c/camp_9")
    assert r.status_code == 200
    assert "pcgAbrirApp" in r.text and "intent://c/camp_9" in r.text
