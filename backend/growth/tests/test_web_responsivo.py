"""La web debe entrar en la pantalla del celular (queja del director,
29-sep-2026: el botón "Editar" de Mis canchas se salía a 390 px).

Una grilla `minmax(420px,1fr)` obliga columnas de 420 px aunque la pantalla
mida 360-390: toda la tarjeta se desborda. Regla: los mínimos de grilla van
con `min(Npx,100%)`. El barrido visual real (Playwright a 360/390/768/1024 px
sobre ~30 páginas) vive fuera de la suite; esto blinda la regla en el código.
"""
import pathlib
import re

RAIZ = pathlib.Path(__file__).resolve().parents[1]
ARCHIVOS = ["web/ui.py", "web/anfitrion.py", "web/anfitrion_academia.py",
            "web/anfitrion_campeonatos.py", "legal/router.py", "propiedad/panel.py"]


def test_grillas_no_obligan_columnas_mas_anchas_que_el_celular():
    malas = []
    for rel in ARCHIVOS:
        texto = (RAIZ / rel).read_text(encoding="utf-8")
        for m in re.finditer(r"minmax\((\d+)px", texto):
            if int(m.group(1)) >= 180:
                malas.append(f"{rel}: {m.group(0)}")
    assert not malas, "Usa minmax(min(Npx,100%),1fr): " + ", ".join(malas)


def test_chips_largos_se_parten_y_pestanas_del_anfitrion_no_desbordan():
    ui = (RAIZ / "web/ui.py").read_text(encoding="utf-8")
    assert ".chips .chip{max-width:100%;white-space:normal" in ui
    assert "@media(max-width:560px){.cab.anfitrion .cab-tabs{margin:0 -16px;padding:0 16px}}" in ui
