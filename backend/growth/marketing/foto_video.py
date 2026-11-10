"""FOTOS → VIDEO CON MOVIMIENTO (pedido del director, 24-sep-2026: "me gustaría
hacer videos y trabajar con fotos para que salgan estilos con movimiento, como
CapCut").

Convierte las fotos elegidas en la torre en un clip con efecto Ken Burns (zoom y
paneo lentos, distinto en cada foto) y fundidos cruzados, en 9:16 (Reels) o 1:1.
NO lleva textos ni música: el clip entra al flujo de PULIDO, que le pone intro,
rótulo, marca de agua, cierre y la música (original o de Mi música). Pillow para
los frames + el FFmpeg empaquetado de `imageio-ffmpeg` para codificar.
"""
from __future__ import annotations

import io
import os
import random
import subprocess
import tempfile

FORMATOS = {"vertical": (1080, 1920), "cuadrado": (1080, 1080), "horizontal": (1280, 720)}
FPS = 30
SEG_MIN, SEG_MAX = 1.5, 6.0
TRANS_S = 0.5
ZOOM = 1.18
MOVS = ("zoom_in", "zoom_out", "pan_left", "pan_right", "pan_up", "pan_down")
MAX_FOTOS = 10


def _lienzo(datos: bytes, W: int, H: int):
    """Foto cubriendo un lienzo ZOOM veces más grande que la salida (margen para mover)."""
    from PIL import Image, ImageOps
    im = ImageOps.exif_transpose(Image.open(io.BytesIO(datos))).convert("RGB")
    bw, bh = int(W * ZOOM), int(H * ZOOM)
    iw, ih = im.size
    esc = max(bw / iw, bh / ih)
    im = im.resize((max(1, int(iw * esc)), max(1, int(ih * esc))), Image.LANCZOS)
    x, y = (im.width - bw) // 2, (im.height - bh) // 2
    return im.crop((x, y, x + bw, y + bh))


def _frame(base, prog: float, mov: str, W: int, H: int):
    from PIL import Image
    bw, bh = base.size
    zf = 1.0 / ZOOM
    if mov == "zoom_in":
        f = 1.0 - (1.0 - zf) * prog
    elif mov == "zoom_out":
        f = zf + (1.0 - zf) * prog
    else:
        f = zf
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
    else:
        x, y = rx // 2, int(ry * (0.5 + 0.12 * (prog - 0.5)))
    x, y = max(0, min(rx, x)), max(0, min(ry, y))
    win = base.crop((x, y, x + ww, y + wh))
    return win if win.size == (W, H) else win.resize((W, H), Image.LANCZOS)


def _suave(t: float) -> float:
    """Ease in-out: el gesto arranca y termina despacio (se siente más 'de editor')."""
    return t * t * (3 - 2 * t)


def generar(fotos: list[bytes], salida: str, *, formato: str = "vertical", segundos: float = 2.8, semilla: int | None = None) -> dict:
    """Escribe el MP4 en `salida` y devuelve {duracion, ancho, alto, fotos}."""
    from PIL import Image
    import imageio_ffmpeg
    if not fotos:
        raise ValueError("Elige al menos una foto.")
    fotos = fotos[:MAX_FOTOS]
    W, H = FORMATOS.get(formato, FORMATOS["vertical"])
    seg = min(SEG_MAX, max(SEG_MIN, float(segundos or 2.8)))
    rnd = random.Random(semilla)
    orden = list(MOVS)
    rnd.shuffle(orden)
    lienzos = [_lienzo(b, W, H) for b in fotos]
    n_frames = max(2, int(FPS * seg))
    n_trans = int(FPS * TRANS_S)
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [ff, "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p", "-movflags", "+faststart", salida]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    total = 0
    negro = Image.new("RGB", (W, H), (0, 0, 0))
    try:
        prev = None
        for i, base in enumerate(lienzos):
            mov = orden[i % len(orden)] if i else "zoom_in"       # abre siempre acercando, como un reel
            primero = _frame(base, 0.0, mov, W, H)
            desde = prev if prev is not None else negro
            for t in range(1, n_trans + 1):                       # fundido desde negro / cruzado con la anterior
                proc.stdin.write(Image.blend(desde, primero, t / (n_trans + 1)).tobytes())
                total += 1
            ultimo = primero
            for k in range(n_frames):
                ultimo = _frame(base, _suave(k / max(1, n_frames - 1)), mov, W, H)
                proc.stdin.write(ultimo.tobytes())
                total += 1
            prev = ultimo
        for t in range(1, n_trans + 1):                           # cierre a negro
            proc.stdin.write(Image.blend(prev, negro, t / (n_trans + 1)).tobytes())
            total += 1
        proc.stdin.close()
        err = proc.stderr.read().decode("utf-8", "ignore")
        if proc.wait() != 0:
            raise RuntimeError("FFmpeg no pudo codificar el video: " + err[-300:])
    finally:
        try:
            proc.stdin.close()
        except Exception:  # noqa: BLE001
            pass
    return {"duracion": round(total / FPS, 2), "ancho": W, "alto": H, "fotos": len(fotos), "ruta": salida}
