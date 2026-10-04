"""REEL vertical (video 9:16) para el community manager autónomo (CM Fase 0).

Auto-arma un REEL corto (MP4 1080x1920) a partir de las FOTOS del negocio:
portada de marca → fotos con efecto Ken Burns (zoom lento) y texto → cierre con
CTA de WhatsApp. Sin música (el dueño le pone la de Historias en IG/FB al subir),
para no cargar con licencias.

Es Pillow (frames) + ffmpeg EMPAQUETADO por `imageio-ffmpeg` (un binario estático
que viaja en el wheel, sin depender de apt en Railway). Reusa la identidad y los
helpers del flyer para que reel y flyer se vean de la MISMA marca.

Fail-safe: si Pillow o el ffmpeg empaquetado no están, devuelve None y el resto
del CM sigue funcionando (solo con el flyer/imagen).
"""

from __future__ import annotations

import os
import tempfile

from .musica import generar_pista
from .flyer import (
    _AMARILLO,
    _BOSQUE,
    _BOSQUE2,
    _LIMA,
    _TEAL,
    _TIPOS,
    _WA,
    _ancho,
    _bajar_imagen,
    _cover,
    _envolver,
    _font,
    _limpiar,
)

_W, _H = 1080, 1920          # vertical 9:16 (formato reel/historia)
_FPS = 30
_DUR = 2.3                   # segundos por slide
_TRANS = 9                   # frames de crossfade entre slides
_ZOOM = 1.12                 # sobre-escala para el Ken Burns

# El "mood" de la música según el tipo de post (para que audio y mensaje peguen).
_MOOD_POR_TIPO = {
    "promo": "energetico",
    "resultado": "epico",
    "horario": "chill",
    "testimonio": "chill",
    "tip": "chill",
}


def _overlay_texto(kicker: str, titulo: str, sub: str, acento, *,
                   cta: bool = False):
    """Capa RGBA (transparente) con degradado inferior + textos de marca. Se pega
    ESTÁTICA sobre la foto que se mueve → texto firme, imagen viva."""
    from PIL import Image, ImageDraw

    cap = Image.new("RGBA", (_W, _H), (0, 0, 0, 0))
    d = ImageDraw.Draw(cap)
    # Scrim: transparente arriba → bosque casi opaco abajo (para leer el texto).
    for y in range(_H):
        t = y / _H
        a = int(min(232, max(0, (t - 0.34) / 0.66 * 250)))
        d.line([(0, y), (_W, y)], fill=(_BOSQUE2[0], _BOSQUE2[1], _BOSQUE2[2], a))

    m = 84
    y = _H - 150

    if cta:
        f_cta = _font(48)
        txt = "Reserva por WhatsApp"
        h = 108
        d.rounded_rectangle([m, y - h, _W - m, y], radius=54, fill=_WA)
        cw = _ancho(d, txt, f_cta)
        d.text(((_W - cw) / 2, y - h + 28), txt, font=f_cta, fill=(255, 255, 255))
        y -= h + 30

    if sub:
        f_s = _font(46, bold=False)
        sl = _envolver(d, _limpiar(sub), f_s, _W - 2 * m, 2)
        for ln in reversed(sl):
            y -= 58
            d.text((m, y), ln, font=f_s, fill=(238, 244, 238))
        y -= 12

    if titulo:
        tam = 92
        while tam > 54:
            f_t = _font(tam)
            tl = _envolver(d, _limpiar(titulo), f_t, _W - 2 * m, 2)
            if len(tl) <= 2 and all(_ancho(d, x, f_t) <= _W - 2 * m for x in tl):
                break
            tam -= 6
        f_t = _font(tam)
        tl = _envolver(d, _limpiar(titulo), f_t, _W - 2 * m, 2)
        for ln in reversed(tl):
            y -= tam + 8
            d.text((m, y), ln, font=f_t, fill=(255, 255, 255))

    if kicker:
        f_k = _font(40)
        y -= 56
        d.text((m, y), _limpiar(kicker).upper(), font=f_k, fill=acento)

    # Barrita de acento + wordmark arriba.
    d.rounded_rectangle([m - 24, y + 4, m - 14, _H - 230], radius=6, fill=acento)
    d.text((m, 84), "PICHANGOL", font=_font(46), fill=_LIMA)
    return cap


def _fondo_grande(datos: dict, foto):
    """Lienzo de foto SOBRE-ESCALADO (para poder hacer zoom sin pixelar). Si no
    hay foto, un degradado de marca."""
    from PIL import Image, ImageDraw

    bw, bh = int(_W * _ZOOM), int(_H * _ZOOM)
    if foto is not None:
        return _cover(foto, bw, bh).convert("RGB")
    img = Image.new("RGB", (bw, bh), _BOSQUE)
    d = ImageDraw.Draw(img)
    for y in range(bh):
        t = y / bh
        r = int(_BOSQUE[0] + (_BOSQUE2[0] - _BOSQUE[0]) * t)
        g = int(_BOSQUE[1] + (_BOSQUE2[1] - _BOSQUE[1]) * t)
        b = int(_BOSQUE[2] + (_BOSQUE2[2] - _BOSQUE[2]) * t)
        d.line([(0, y), (bw, y)], fill=(r, g, b))
    return img


# Movimientos Ken Burns disponibles (para que los reels NO se vean iguales).
_MOVS = ("zoom_in", "zoom_out", "pan_left", "pan_right", "pan_up", "pan_down")


def _frame(base_grande, overlay, prog: float, mov: str):
    """Un frame WxH: recorta una ventana del lienzo grande con el movimiento [mov]
    (zoom o paneo) y pega el overlay ESTÁTICO encima. prog 0→1 avanza el gesto."""
    from PIL import Image

    bw, bh = base_grande.size
    zf = 1.0 / _ZOOM  # ventana "acercada" (deja margen para panear)

    if mov == "zoom_in":
        f = 1.0 - (1.0 - zf) * prog        # ventana se achica → acerca
    elif mov == "zoom_out":
        f = zf + (1.0 - zf) * prog          # ventana crece → aleja
    else:
        f = zf                               # paneo: zoom fijo, se mueve
    ww, wh = min(int(bw * f), bw), min(int(bh * f), bh)
    rx, ry = bw - ww, bh - wh

    if mov == "pan_left":
        x, y = int(rx * prog), ry // 2
    elif mov == "pan_right":
        x, y = int(rx * (1.0 - prog)), ry // 2
    elif mov == "pan_up":
        x, y = rx // 2, int(ry * (1.0 - prog))
    elif mov == "pan_down":
        x, y = rx // 2, int(ry * prog)
    else:  # zoom: centrado con deriva vertical muy suave
        x = rx // 2
        y = int(ry * (0.5 + 0.12 * (prog - 0.5)))
    x = max(0, min(rx, x))
    y = max(0, min(ry, y))

    win = base_grande.crop((x, y, x + ww, y + wh))
    if win.size != (_W, _H):
        win = win.resize((_W, _H), Image.LANCZOS)
    if overlay is not None:
        win = Image.alpha_composite(win.convert("RGBA"), overlay).convert("RGB")
    return win


def _slides(datos: dict, gancho: str, tipo: str | None):
    """Arma la lista de slides: (foto|None, overlay, movimiento). Portada + fotos
    + cierre, cada uno con un gesto Ken Burns distinto para dar variedad."""
    import random

    tag_label, acento = _TIPOS.get(tipo or "", ("PICHANGOL", _LIMA))
    # Barajado del orden de movimientos → cada reel se siente distinto.
    orden = list(_MOVS)
    random.shuffle(orden)

    def _mov(i: int) -> str:
        return orden[i % len(orden)]

    nombre = _limpiar(str(datos.get("nombre") or "Academia")) or "Academia"
    deporte = _limpiar(str(datos.get("deporte") or "")).capitalize()
    sede = _limpiar(str(datos.get("sede") or ""))
    sub = "  ·  ".join(x for x in [deporte, sede] if x)
    frase = _limpiar(gancho)
    if "." in frase:
        frase = frase.split(".")[0].strip()

    urls = []
    fotos = datos.get("fotos")
    if isinstance(fotos, list):
        urls = [str(u) for u in fotos if str(u or "").startswith("http")][:4]

    fotos_pil = [f for f in (_bajar_imagen(u) for u in urls) if f is not None]

    slides = []
    # 1) Portada de marca: primera foto (o degradado) + nombre + eyebrow. Siempre
    # abre con un zoom-in (entrada clásica de reel).
    portada_foto = fotos_pil[0] if fotos_pil else None
    slides.append((portada_foto,
                   _overlay_texto(tag_label, nombre, sub, acento), "zoom_in"))

    # 2) Fotos con frases CORTAS y punchy (los reels no llevan párrafos). Del
    # gancho se toma sólo el arranque para que no se corte a medias.
    corto = " ".join(frase.split()[:4]) if frase else ""
    frases = [corto or "Ven a jugar", "Cupos disponibles",
              sub or "Te esperamos", "Reserva fácil, juega hoy"]
    for i, f in enumerate(fotos_pil):
        slides.append((f, _overlay_texto("", frases[i % len(frases)], "",
                                         acento), _mov(i)))

    # Si no hubo fotos, agrega una tarjeta de marca extra para que dure.
    if not fotos_pil:
        slides.append((None, _overlay_texto("", frase or "Reserva tu cancha",
                                            sub, acento), "pan_up"))

    # 3) Cierre con CTA de WhatsApp — cierra alejando (zoom-out) para "cerrar".
    cierre_foto = fotos_pil[-1] if fotos_pil else None
    slides.append((cierre_foto,
                   _overlay_texto("", "Reserva ahora", nombre, acento,
                                  cta=True), "zoom_out"))
    return slides


def generar_reel(datos: dict, gancho: str, tipo: str | None = None,
                 con_musica: bool = True) -> bytes | None:
    """Devuelve el MP4 (bytes) del reel, o None si falta Pillow / el ffmpeg
    empaquetado. Vertical 1080x1920, ~10-14 s. Con [con_musica] le pega una pista
    ORIGINAL (libre de regalías) acorde al tipo de post."""
    try:
        import numpy as np
        import imageio.v2 as imageio
        from PIL import Image
    except Exception:  # noqa: BLE001
        return None

    try:
        slides = _slides(datos or {}, gancho, tipo)
        # Pre-render de cada lienzo grande (una vez por slide).
        lienzos = [(_fondo_grande(datos or {}, foto), ov, mov)
                   for foto, ov, mov in slides]
    except Exception:  # noqa: BLE001
        return None

    n_frames = max(1, int(_FPS * _DUR))
    negro = Image.new("RGB", (_W, _H), (0, 0, 0))

    # Duración total del video (para generar una pista que calce exacto).
    total_frames = len(lienzos) * (_TRANS + n_frames) + _TRANS
    dur_seg = total_frames / _FPS

    ruta = os.path.join(tempfile.gettempdir(),
                        f"reel_{os.getpid()}_{id(datos)}.mp4")
    ruta_wav = ""
    if con_musica:
        try:
            mood = _MOOD_POR_TIPO.get(tipo or "", "chill")
            wav = generar_pista(dur_seg, mood=mood)
            if wav:
                ruta_wav = os.path.join(
                    tempfile.gettempdir(),
                    f"reel_{os.getpid()}_{id(datos)}.wav")
                with open(ruta_wav, "wb") as fh:
                    fh.write(wav)
        except Exception:  # noqa: BLE001
            ruta_wav = ""

    extra = {"audio_path": ruta_wav, "audio_codec": "aac"} if ruta_wav else {}
    w = None
    try:
        w = imageio.get_writer(
            ruta, fps=_FPS, codec="libx264", format="FFMPEG",
            pixelformat="yuv420p", macro_block_size=None, quality=None,
            output_params=["-crf", "26", "-preset", "veryfast", "-shortest",
                           "-movflags", "+faststart"], **extra)

        prev_last = None
        for base, ov, mov in lienzos:
            primer = _frame(base, ov, 0.0, mov)
            # Fade-in del arranque / crossfade con el slide anterior.
            if prev_last is None:
                for t in range(1, _TRANS + 1):
                    w.append_data(np.asarray(
                        Image.blend(negro, primer, t / (_TRANS + 1))))
            else:
                for t in range(1, _TRANS + 1):
                    w.append_data(np.asarray(
                        Image.blend(prev_last, primer, t / (_TRANS + 1))))
            # Frames del slide (Ken Burns con el movimiento del slide).
            ultimo = primer
            for i in range(n_frames):
                fr = _frame(base, ov, i / max(1, n_frames - 1), mov)
                w.append_data(np.asarray(fr))
                ultimo = fr
            prev_last = ultimo

        # Fade-out final a negro.
        if prev_last is not None:
            for t in range(1, _TRANS + 1):
                w.append_data(np.asarray(
                    Image.blend(prev_last, negro, t / (_TRANS + 1))))
        w.close()
        w = None
        with open(ruta, "rb") as fh:
            return fh.read()
    except Exception:  # noqa: BLE001
        return None
    finally:
        if w is not None:
            try:
                w.close()
            except Exception:  # noqa: BLE001
                pass
        for p in (ruta, ruta_wav):
            if p:
                try:
                    os.remove(p)
                except OSError:
                    pass
