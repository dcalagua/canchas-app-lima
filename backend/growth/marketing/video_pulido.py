"""PULIDO de video con estilo Pichangol + SUBTÍTULOS automáticos (Whisper).

Pedido del director (24-sep-2026): enriquecer los videos que se publican en la
página como lo haría CapCut, sin depender de CapCut (no tiene API pública).
Todo corre en casa con el FFmpeg empaquetado por `imageio-ffmpeg` (el mismo del
módulo de reels) y Pillow:

  intro 1,2 s con el logo  →  video normalizado (1080p, 9:16 / 1:1 / original,
  fondo desenfocado cuando el encuadre no calza, marca de agua, rótulo con el
  título, subtítulos con palabra resaltada, volumen normalizado, música
  original de fondo si no hay audio)  →  cierre de 3 s con el título y
  www.pichangol.app.

Subtítulos: `transcribir()` extrae el audio (mono 16 kHz) y lo manda a Whisper
(`OPENAI_API_KEY`, modelo `whisper-1`, `verbose_json` con palabras). El operador
corrige el texto en la torre y `pulir()` los quema con libass (`ass=` filter,
DM Sans desde `marketing/assets`, estilo tipo CapCut: caja redondeada oscura y
la palabra en curso en lima).

El trabajo corre en un hilo (`iniciar_trabajo`) con progreso real leído de
`-progress pipe:1`; la torre sondea `estado()`.
"""
from __future__ import annotations

import io
import json
import math
import os
import re
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
import uuid

import config

_DIR = os.path.dirname(os.path.abspath(__file__))
_ASSETS = os.path.join(_DIR, "assets")
_STATIC = os.path.join(os.path.dirname(_DIR), "static", "brand")

FORMATOS = {"vertical": (1080, 1920), "cuadrado": (1080, 1080), "original": None}
INTRO_S = 1.2
CIERRE_S = 3.0
ROTULO_S = 4.5
FPS = 30
LIMA = (124, 181, 24)
VERDE = (11, 138, 62)
VERDE_OSC = (6, 122, 56)
NOCHE = (10, 27, 61)
BLANCO = (255, 255, 255)
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "whisper-1")
WHISPER_URL = "https://api.openai.com/v1/audio/transcriptions"

_trabajos: dict[str, dict] = {}
_lock = threading.Lock()


# ── ffmpeg ────────────────────────────────────────────────────────────────────
def ffmpeg_exe() -> str:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # noqa: BLE001
        return ""


def disponible() -> bool:
    return bool(ffmpeg_exe())


def subtitulos_disponibles() -> bool:
    return bool(config.OPENAI_API_KEY)


def sondear(ruta: str) -> dict:
    """Duración, tamaño (ya rotado) y si tiene audio, leyendo `ffmpeg -i`."""
    ff = ffmpeg_exe()
    if not ff:
        return {}
    p = subprocess.run([ff, "-hide_banner", "-i", ruta], capture_output=True, text=True, errors="ignore")
    err = p.stderr or ""
    dur = 0.0
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", err)
    if m:
        dur = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    w = h = 0
    m = re.search(r"Video:.*?\b(\d{2,5})x(\d{2,5})\b", err)
    if m:
        w, h = int(m.group(1)), int(m.group(2))
    rot = 0
    m = re.search(r"rotation of (-?\d+(?:\.\d+)?) degrees", err) or re.search(r"rotate\s*:\s*(-?\d+)", err)
    if m:
        try:
            rot = int(round(float(m.group(1)))) % 360
        except ValueError:
            rot = 0
    if rot in (90, 270) and w and h:
        w, h = h, w
    return {"duracion": round(dur, 3), "ancho": w, "alto": h, "audio": "Audio:" in err, "rotacion": rot}


# ── piezas de marca (Pillow) ─────────────────────────────────────────────────
def _font(peso: str, tam: int):
    from marketing import post_redes
    return post_redes._font(peso, tam)


def _logo(diam: int):
    from marketing import post_redes
    return post_redes._logo_disco(diam)


def _envolver(d, texto, f, ancho):
    from marketing import post_redes
    return post_redes._envolver(d, texto, f, ancho)


def _guardar(im, ruta: str) -> str:
    im.save(ruta, "PNG")
    return ruta


def _png_intro(W: int, H: int, ruta: str) -> str:
    from PIL import Image, ImageDraw
    im = Image.new("RGBA", (W, H), BLANCO + (255,))
    d = ImageDraw.Draw(im)
    diam = int(min(W, H) * 0.22)
    lg = _logo(diam)
    f = _font("Bold", int(min(W, H) * 0.11))
    fs = _font("Medium", int(min(W, H) * 0.036))
    tw = d.textlength("Pichangol", font=f)
    total_w = diam + int(diam * 0.18) + tw
    x = (W - total_w) // 2
    y = H // 2 - diam // 2 - int(H * 0.03)
    im.paste(lg, (int(x), int(y)), lg)
    d.text((x + diam + int(diam * 0.18), y + diam // 2), "Pichangol", font=f, fill=NOCHE, anchor="lm")
    d.text((W // 2, y + diam + int(H * 0.05)), "Reserva, juega, repite.", font=fs, fill=VERDE, anchor="mm")
    return _guardar(im, ruta)


def _png_cierre(W: int, H: int, titulo: str, ruta: str) -> str:
    from PIL import Image, ImageDraw
    im = Image.new("RGBA", (W, H), VERDE_OSC + (255,))
    # degradado vertical verde → azul noche (columna escalada, barato)
    col = Image.new("RGBA", (1, H))
    px = col.load()
    for yy in range(H):
        t = yy / max(1, H - 1)
        px[0, yy] = tuple(int(VERDE_OSC[i] * (1 - t) + NOCHE[i] * t) for i in range(3)) + (255,)
    im.paste(col.resize((W, H)))
    d = ImageDraw.Draw(im)
    diam = int(min(W, H) * 0.16)
    lg = _logo(diam)
    im.paste(lg, ((W - diam) // 2, int(H * 0.22)), lg)
    f_t = _font("Bold", int(min(W, H) * 0.072))
    lineas = _envolver(d, (titulo or "Reserva tu cancha en Pichangol").strip(), f_t, int(W * 0.82))[:3]
    y = int(H * 0.22) + diam + int(H * 0.05)
    for ln in lineas:
        d.text((W // 2, y), ln, font=f_t, fill=BLANCO, anchor="mm")
        y += int(f_t.size * 1.18)
    f_u = _font("Bold", int(min(W, H) * 0.046))
    pill_w = int(d.textlength("www.pichangol.app", font=f_u)) + int(W * 0.08)
    pill_h = int(f_u.size * 1.9)
    px0, py0 = (W - pill_w) // 2, y + int(H * 0.03)
    d.rounded_rectangle([px0, py0, px0 + pill_w, py0 + pill_h], radius=pill_h // 2, fill=BLANCO)
    d.text((W // 2, py0 + pill_h // 2), "www.pichangol.app", font=f_u, fill=NOCHE, anchor="mm")
    f_s = _font("Medium", int(min(W, H) * 0.03))
    d.text((W // 2, py0 + pill_h + int(H * 0.035)), "Descarga la app · Android", font=f_s, fill=(200, 230, 200), anchor="mm")
    return _guardar(im, ruta)


def _png_marca(W: int, H: int, ruta: str) -> str:
    """Marca de agua: disco con el logo + 'Pichangol' (transparente, esquina superior derecha)."""
    from PIL import Image, ImageDraw
    diam = int(min(W, H) * 0.07)
    f = _font("Bold", int(diam * 0.62))
    tmp = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    tw = int(tmp.textlength("Pichangol", font=f))
    w = diam + int(diam * 0.25) + tw + int(diam * 0.5)
    h = int(diam * 1.3)
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, w - 1, h - 1], radius=h // 2, fill=(0, 0, 0, 92))
    lg = _logo(diam)
    im.paste(lg, (int(diam * 0.15), (h - diam) // 2), lg)
    d.text((int(diam * 0.15) + diam + int(diam * 0.2), h // 2), "Pichangol", font=f, fill=BLANCO, anchor="lm")
    return _guardar(im, ruta)


def _png_rotulo(W: int, H: int, titulo: str, ruta: str) -> str:
    """Rótulo inferior con el título (píldora blanca + franja lima)."""
    from PIL import Image, ImageDraw
    f = _font("Bold", int(min(W, H) * 0.05))
    tmp = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    lineas = _envolver(tmp, (titulo or "").strip(), f, int(W * 0.78))[:2]
    if not lineas:
        lineas = ["Pichangol"]
    tw = max(int(tmp.textlength(ln, font=f)) for ln in lineas)
    pad_x, pad_y = int(f.size * 0.7), int(f.size * 0.45)
    w = tw + pad_x * 2 + int(f.size * 0.5)
    h = int(f.size * 1.25) * len(lineas) + pad_y * 2
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, w - 1, h - 1], radius=int(h * 0.28), fill=(255, 255, 255, 242))
    d.rounded_rectangle([0, 0, int(f.size * 0.35), h - 1], radius=int(f.size * 0.17), fill=LIMA)
    y = pad_y
    for ln in lineas:
        d.text((pad_x + int(f.size * 0.3), y), ln, font=f, fill=NOCHE)
        y += int(f.size * 1.25)
    return _guardar(im, ruta)


# ── subtítulos (ASS) ─────────────────────────────────────────────────────────
def _ass_t(seg: float) -> str:
    seg = max(0.0, float(seg))
    h = int(seg // 3600)
    m = int((seg % 3600) // 60)
    s = seg % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _limpiar_ass(t: str) -> str:
    return re.sub(r"[{}\\]", "", str(t or "")).replace("\n", " ").strip()


def partir_segmentos(segmentos: list[dict], max_palabras: int = 6, max_s: float = 4.0) -> list[dict]:
    """Segmentos cortos (≤6 palabras / ≤4 s) para que la caja no tape el video.
    Usa los tiempos por palabra si vienen; si no, reparte el tiempo por caracteres."""
    out: list[dict] = []
    for s in segmentos or []:
        texto = _limpiar_ass(s.get("texto"))
        if not texto:
            continue
        ini, fin = float(s.get("inicio", 0) or 0), float(s.get("fin", 0) or 0)
        if fin <= ini:
            fin = ini + max(0.8, len(texto) * 0.06)
        palabras = [p for p in (s.get("palabras") or []) if _limpiar_ass(p.get("p"))]
        if palabras:
            trozo: list[dict] = []
            for p in palabras:
                trozo.append({"p": _limpiar_ass(p.get("p")), "inicio": float(p.get("inicio", ini)), "fin": float(p.get("fin", ini))})
                if len(trozo) >= max_palabras or (trozo[-1]["fin"] - trozo[0]["inicio"]) >= max_s:
                    out.append({"inicio": trozo[0]["inicio"], "fin": trozo[-1]["fin"], "texto": " ".join(x["p"] for x in trozo), "palabras": trozo})
                    trozo = []
            if trozo:
                out.append({"inicio": trozo[0]["inicio"], "fin": trozo[-1]["fin"], "texto": " ".join(x["p"] for x in trozo), "palabras": trozo})
        else:
            ws = texto.split()
            grupos = [ws[i:i + max_palabras] for i in range(0, len(ws), max_palabras)] or [ws]
            total = sum(len(" ".join(g)) for g in grupos) or 1
            t = ini
            for g in grupos:
                dur = (fin - ini) * len(" ".join(g)) / total
                out.append({"inicio": t, "fin": t + dur, "texto": " ".join(g), "palabras": []})
                t += dur
    # sin solapes ni duraciones microscópicas
    for i, s in enumerate(out):
        if i + 1 < len(out) and s["fin"] > out[i + 1]["inicio"]:
            s["fin"] = out[i + 1]["inicio"]
        if s["fin"] - s["inicio"] < 0.35:
            s["fin"] = s["inicio"] + 0.35
    return out


def escribir_ass(segmentos: list[dict], W: int, H: int, ruta: str, *, desplazar: float = 0.0, resaltar: bool = True) -> str:
    """ASS estilo CapCut: DM Sans bold, caja oscura redondeada (BorderStyle 3), la
    palabra en curso pasa a LIMA con karaoke `\\k` cuando hay tiempos por palabra."""
    tam = int(min(W, H) * (0.058 if H > W else 0.046))
    margen_v = int(H * (0.17 if H > W else 0.11))
    lineas = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}", "WrapStyle: 0", "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        # Primary = color "cantado" (lima), Secondary = pendiente (blanco); BorderStyle 3 = caja (BackColour) con Outline de relleno.
        f"Style: Pichangol,DM Sans,{tam},&H0018B57C,&H00FFFFFF,&H00000000,&H6E000000,-1,0,0,0,100,100,0,0,3,{max(6, tam // 6)},0,2,{int(W * 0.06)},{int(W * 0.06)},{margen_v},1",
        f"Style: Plano,DM Sans,{tam},&H00FFFFFF,&H00FFFFFF,&H00000000,&H6E000000,-1,0,0,0,100,100,0,0,3,{max(6, tam // 6)},0,2,{int(W * 0.06)},{int(W * 0.06)},{margen_v},1",
        "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    for s in segmentos:
        ini, fin = float(s["inicio"]) + desplazar, float(s["fin"]) + desplazar
        palabras = s.get("palabras") or []
        if resaltar and palabras:
            partes = []
            t = ini
            for p in palabras:
                p_fin = max(float(p.get("fin", t)) + desplazar, t + 0.05)
                cs = max(1, int(round((p_fin - t) * 100)))
                partes.append(f"{{\\k{cs}}}{_limpiar_ass(p['p'])}")
                t = p_fin
            texto = " ".join(partes)
            estilo = "Pichangol"
        else:
            texto = _limpiar_ass(s.get("texto"))
            estilo = "Plano"
        if texto:
            lineas.append(f"Dialogue: 0,{_ass_t(ini)},{_ass_t(fin)},{estilo},,0,0,0,,{texto}")
    with open(ruta, "w", encoding="utf-8") as f:
        f.write("\n".join(lineas) + "\n")
    return ruta


# ── Whisper ──────────────────────────────────────────────────────────────────
def _extraer_audio(ruta_video: str, destino: str) -> bool:
    ff = ffmpeg_exe()
    p = subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-y", "-i", ruta_video, "-vn", "-ac", "1", "-ar", "16000",
                        "-c:a", "libmp3lame", "-b:a", "48k", destino], capture_output=True, text=True, errors="ignore")
    return p.returncode == 0 and os.path.exists(destino) and os.path.getsize(destino) > 0


def _whisper_api(ruta_audio: str, idioma: str = "es") -> dict:
    """POST multipart a OpenAI (sin SDK). Devuelve el JSON verbose (segments + words)."""
    limite = "----PichangolWhisper" + uuid.uuid4().hex
    campos = {"model": WHISPER_MODEL, "response_format": "verbose_json", "language": idioma,
              "timestamp_granularities[]": "word"}
    partes = []
    for k, v in campos.items():
        partes.append(f"--{limite}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode())
    partes.append(f"--{limite}\r\nContent-Disposition: form-data; name=\"timestamp_granularities[]\"\r\n\r\nsegment\r\n".encode())
    with open(ruta_audio, "rb") as f:
        datos = f.read()
    partes.append(f"--{limite}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"audio.mp3\"\r\nContent-Type: audio/mpeg\r\n\r\n".encode() + datos + b"\r\n")
    partes.append(f"--{limite}--\r\n".encode())
    cuerpo = b"".join(partes)
    req = urllib.request.Request(WHISPER_URL, data=cuerpo, method="POST",
                                 headers={"Authorization": f"Bearer {config.OPENAI_API_KEY}",
                                          "Content-Type": f"multipart/form-data; boundary={limite}", "Content-Length": str(len(cuerpo))})
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            detalle = json.loads(e.read().decode("utf-8", "ignore")).get("error", {}).get("message", "")
        except Exception:  # noqa: BLE001
            detalle = ""
        raise RuntimeError(f"Whisper HTTP {e.code}: {detalle[:200]}") from e


def _normalizar_transcripcion(j: dict) -> list[dict]:
    """De verbose_json (segments + words) a nuestros segmentos con palabras dentro."""
    segs = []
    palabras = [{"p": str(w.get("word", "")).strip(), "inicio": float(w.get("start", 0) or 0), "fin": float(w.get("end", 0) or 0)}
                for w in (j.get("words") or []) if str(w.get("word", "")).strip()]
    for s in j.get("segments") or []:
        ini, fin = float(s.get("start", 0) or 0), float(s.get("end", 0) or 0)
        texto = str(s.get("text", "")).strip()
        if not texto:
            continue
        dentro = [p for p in palabras if p["inicio"] >= ini - 0.05 and p["fin"] <= fin + 0.05]
        segs.append({"inicio": round(ini, 3), "fin": round(fin, 3), "texto": texto, "palabras": dentro})
    if not segs and palabras:   # solo palabras (raro): agrúpalas de 6 en 6
        segs = partir_segmentos([{"inicio": palabras[0]["inicio"], "fin": palabras[-1]["fin"], "texto": " ".join(p["p"] for p in palabras), "palabras": palabras}])
    if not segs and str(j.get("text", "")).strip():
        segs = [{"inicio": 0.0, "fin": float(j.get("duration") or 5.0), "texto": str(j["text"]).strip(), "palabras": []}]
    return segs


def transcribir(ruta_video: str) -> dict:
    """Subtítulos automáticos. Devuelve {segmentos, idioma, sin_audio}."""
    info = sondear(ruta_video)
    if not info.get("audio"):
        return {"segmentos": [], "idioma": "", "sin_audio": True}
    if not config.OPENAI_API_KEY:
        raise RuntimeError("Sin OPENAI_API_KEY: los subtítulos automáticos no están disponibles en este ambiente.")
    audio = os.path.join(tempfile.gettempdir(), f"pcg_sub_{uuid.uuid4().hex[:10]}.mp3")
    try:
        if not _extraer_audio(ruta_video, audio):
            raise RuntimeError("No se pudo extraer el audio del video.")
        if os.path.getsize(audio) > 25 * 1024 * 1024:
            raise RuntimeError("El audio supera los 25 MB que acepta Whisper; recorta el video.")
        j = _whisper_api(audio)
    finally:
        try:
            os.remove(audio)
        except OSError:
            pass
    return {"segmentos": _normalizar_transcripcion(j), "idioma": str(j.get("language") or "es"), "sin_audio": False}


# ── render ───────────────────────────────────────────────────────────────────
def _objetivo(formato: str, info: dict) -> tuple[int, int]:
    if formato in FORMATOS and FORMATOS[formato]:
        return FORMATOS[formato]
    w, h = int(info.get("ancho") or 1280), int(info.get("alto") or 720)
    k = min(1.0, 1080 / max(1, w), 1920 / max(1, h))
    W, H = int(w * k) // 2 * 2, int(h * k) // 2 * 2
    return max(320, W), max(320, H)


MODOS_MUSICA = ("auto", "fondo", "protagonista", "no")
MOODS_MUSICA = ("chill", "energetico", "epico")


def mezcla_musica(tiene_audio: bool, opciones: dict) -> dict:
    """Decide cómo entra la música original (pedido del director, sep-2026: "¿de fondo
    o en primer plano?"). `musica_modo`: `fondo` = suave bajo la voz (o sola si el video
    es mudo), `protagonista` = la música manda y el audio original queda de ambiente,
    `no` = sin música, `auto` (defecto) = fondo si hay voz / protagonista si es mudo.
    Compatibilidad: `musica: False` equivale a `no`, `musica: True` a `auto`."""
    modo = str(opciones.get("musica_modo") or "").strip().lower()
    if modo not in MODOS_MUSICA:
        m = opciones.get("musica")
        modo = "no" if m is False else "auto"
    if modo == "auto":
        modo = "fondo" if tiene_audio else "protagonista"
    mood = str(opciones.get("mood") or "").strip().lower()
    if mood == "energico":          # alias viejo
        mood = "energetico"
    if mood not in MOODS_MUSICA:
        mood = "chill"
    if modo == "no":
        return {"usar": False, "modo": "no", "mood": mood, "vol_musica": 0.0, "vol_original": 1.0}
    if modo == "protagonista":
        return {"usar": True, "modo": modo, "mood": mood, "vol_musica": 0.8, "vol_original": 0.22 if tiene_audio else 1.0}
    return {"usar": True, "modo": "fondo", "mood": mood, "vol_musica": 0.16 if tiene_audio else 0.55, "vol_original": 1.0}


def recortar_pista(ruta: str, desde: float, salida: str) -> str | None:
    """Copia de la pista que empieza en el segundo `desde` (WAV estéreo 48 kHz). None si falla."""
    ff = ffmpeg_exe()
    if not ff:
        return None
    p = subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{max(0.0, desde):.3f}", "-i", ruta, "-vn", "-ac", "2", "-ar", "48000", salida],
                       capture_output=True)
    return salida if p.returncode == 0 and os.path.exists(salida) and os.path.getsize(salida) > 1000 else None


def detectar_inicio(ruta: str, umbral_db: int = -35, max_seg: float = 15.0) -> float:
    """Segundo en que la pista EMPIEZA A SONAR (muchas canciones traen 1-3 s de silencio o
    entrada muy baja): `silencedetect` sobre los primeros `max_seg` s; 0.0 si suena desde el
    inicio o si no se pudo analizar."""
    ff = ffmpeg_exe()
    if not ff:
        return 0.0
    p = subprocess.run([ff, "-hide_banner", "-t", f"{max_seg}", "-i", ruta, "-vn", "-af", f"silencedetect=n={umbral_db}dB:d=0.25", "-f", "null", "-"],
                       capture_output=True, text=True, errors="ignore")
    ini = re.search(r"silence_start:\s*(-?[\d.]+)", p.stderr or "")
    fin = re.search(r"silence_end:\s*([\d.]+)", p.stderr or "")
    if ini and float(ini.group(1)) <= 0.05:
        return round(float(fin.group(1)), 2) if fin else 0.0
    return 0.0


def pulir(ruta: str, salida: str, opciones: dict, *, progreso=None) -> dict:
    """Renderiza la versión pulida. `opciones`: formato, logo, intro, cierre, rotulo,
    titulo, segmentos (subtítulos ya partidos o crudos), resaltar, musica_modo
    (auto|fondo|protagonista|no) + mood (chill|energetico|epico) o `musica_ruta`
    (archivo de audio propio que reemplaza a la música sintetizada); `musica` bool = compat.
    `progreso(pct, mensaje)` se llama mientras avanza. Devuelve info de la salida."""
    ff = ffmpeg_exe()
    if not ff:
        raise RuntimeError("FFmpeg no está disponible en este servidor.")
    info = sondear(ruta)
    D = float(info.get("duracion") or 0)
    if D <= 0.2:
        raise RuntimeError("No se pudo leer la duración del video.")
    W, H = _objetivo(str(opciones.get("formato") or "vertical"), info)
    tmp = tempfile.mkdtemp(prefix="pcg_pulido_")
    entradas = ["-i", ruta]
    idx = 1
    filtros = []
    con_intro = bool(opciones.get("intro", True))
    con_cierre = bool(opciones.get("cierre", True))
    titulo = str(opciones.get("titulo") or "").strip()
    sw, sh = int(info.get("ancho") or 0), int(info.get("alto") or 0)
    calza = sw and sh and abs((sw / sh) - (W / H)) < 0.03

    # 1) video principal → tamaño objetivo (fondo desenfocado si el encuadre no calza)
    if calza:
        filtros.append(f"[0:v]scale={W}:{H}:flags=lanczos,fps={FPS},format=yuv420p,setsar=1[vbase]")
    else:
        filtros.append(f"[0:v]fps={FPS},split=2[bgi][fgi];"
                       f"[bgi]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},gblur=sigma=38[bg];"
                       f"[fgi]scale={W}:{H}:force_original_aspect_ratio=decrease:flags=lanczos[fg];"
                       f"[bg][fg]overlay=(W-w)/2:(H-h)/2,format=yuv420p,setsar=1[vbase]")
    ultimo = "vbase"
    M = int(min(W, H) * 0.035)

    # 2) marca de agua
    if opciones.get("logo", True):
        p = _png_marca(W, H, os.path.join(tmp, "marca.png"))
        entradas += ["-i", p]
        filtros.append(f"[{ultimo}][{idx}:v]overlay=W-w-{M}:{M}[vmarca]")
        ultimo, idx = "vmarca", idx + 1

    # 3) rótulo con el título (primeros segundos)
    if opciones.get("rotulo", True) and titulo:
        p = _png_rotulo(W, H, titulo, os.path.join(tmp, "rotulo.png"))
        entradas += ["-i", p]
        fin_rot = min(D - 0.3, 0.6 + ROTULO_S)
        y_rot = f"H-h-{int(H * (0.30 if H > W else 0.24))}"
        filtros.append(f"[{ultimo}][{idx}:v]overlay={M}:{y_rot}:enable='between(t,0.6,{fin_rot:.2f})'[vrot]")
        ultimo, idx = "vrot", idx + 1

    # 4) subtítulos
    segmentos = partir_segmentos(opciones.get("segmentos") or [])
    if segmentos:
        ass = escribir_ass(segmentos, W, H, os.path.join(tmp, "subs.ass"), resaltar=bool(opciones.get("resaltar", True)))
        filtros.append(f"[{ultimo}]ass='{ass}':fontsdir='{_ASSETS}'[vsub]")
        ultimo = "vsub"

    # 5) fundidos del principal
    filtros.append(f"[{ultimo}]fade=t=in:st=0:d=0.35,fade=t=out:st={max(0.0, D - 0.4):.2f}:d=0.4[vmain]")

    # 6) audio del principal: normalizado; sin audio → silencio; música de fondo opcional
    if info.get("audio"):
        filtros.append("[0:a]loudnorm=I=-16:TP=-1.5:LRA=11,aformat=sample_rates=48000:channel_layouts=stereo[a0]")
    else:
        filtros.append(f"aevalsrc=0:d={D:.3f}:s=48000,aformat=sample_rates=48000:channel_layouts=stereo[a0]")
    a_main = "a0"
    mezcla = mezcla_musica(bool(info.get("audio")), opciones)
    if mezcla["usar"]:
        pista = str(opciones.get("musica_ruta") or "")          # pista propia (Mi música, Google Drive): reemplaza a la sintetizada
        wav = None
        if pista and os.path.exists(pista) and os.path.getsize(pista) > 0:
            desde = float(opciones.get("musica_desde") or 0)
            if desde > 0.05:                                       # arranca desde el segundo elegido (evita la intro silenciosa)
                pista = recortar_pista(pista, desde, os.path.join(tmp, "pista_desde.wav")) or pista
            entradas += ["-stream_loop", "-1", "-i", pista]      # en bucle si es más corta que el video; amix la corta al largo del video
            wav = b"pista"
        else:
            try:
                from marketing.musica import generar_pista
                wav = generar_pista(D + 0.5, mood=mezcla["mood"])
            except Exception:  # noqa: BLE001
                wav = None
            if wav:
                pm = os.path.join(tmp, "musica.wav")
                with open(pm, "wb") as fh:
                    fh.write(wav)
                entradas += ["-i", pm]
        if wav:
            if mezcla["vol_original"] != 1.0:
                filtros.append(f"[a0]volume={mezcla['vol_original']}[a0d]")
                a_orig = "a0d"
            else:
                a_orig = "a0"
            filtros.append(f"[{idx}:a]volume={mezcla['vol_musica']},afade=t=in:st=0:d=0.6,afade=t=out:st={max(0.0, D - 1.2):.2f}:d=1.2,aformat=sample_rates=48000:channel_layouts=stereo[amus]")
            filtros.append(f"[{a_orig}][amus]amix=inputs=2:duration=first:dropout_transition=2:normalize=0[amix]")
            a_main, idx = "amix", idx + 1

    # 7) intro / cierre como clips (imagen en bucle + silencio) y concat
    partes_v, partes_a = [], []
    if con_intro:
        p = _png_intro(W, H, os.path.join(tmp, "intro.png"))
        entradas += ["-loop", "1", "-framerate", str(FPS), "-t", f"{INTRO_S}", "-i", p]
        filtros.append(f"[{idx}:v]format=yuv420p,setsar=1,fade=t=out:st={INTRO_S - 0.3:.2f}:d=0.3[vintro]")
        filtros.append(f"aevalsrc=0:d={INTRO_S}:s=48000,aformat=sample_rates=48000:channel_layouts=stereo[aintro]")
        partes_v.append("vintro"); partes_a.append("aintro"); idx += 1
    partes_v.append("vmain"); partes_a.append(a_main)
    if con_cierre:
        p = _png_cierre(W, H, titulo, os.path.join(tmp, "cierre.png"))
        entradas += ["-loop", "1", "-framerate", str(FPS), "-t", f"{CIERRE_S}", "-i", p]
        filtros.append(f"[{idx}:v]format=yuv420p,setsar=1,fade=t=in:st=0:d=0.3[vcierre]")
        filtros.append(f"aevalsrc=0:d={CIERRE_S}:s=48000,aformat=sample_rates=48000:channel_layouts=stereo[acierre]")
        partes_v.append("vcierre"); partes_a.append("acierre"); idx += 1
    if len(partes_v) > 1:
        cadena = "".join(f"[{v}][{a}]" for v, a in zip(partes_v, partes_a))
        filtros.append(f"{cadena}concat=n={len(partes_v)}:v=1:a=1[vout][aout]")
        mapa_v, mapa_a = "[vout]", "[aout]"
    else:
        mapa_v, mapa_a = "[vmain]", f"[{a_main}]"
    total = D + (INTRO_S if con_intro else 0) + (CIERRE_S if con_cierre else 0)

    cmd = [ff, "-hide_banner", "-loglevel", "error", "-y", *entradas, "-filter_complex", ";".join(filtros),
           "-map", mapa_v, "-map", mapa_a, "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-profile:v", "high", "-pix_fmt", "yuv420p",
           "-r", str(FPS), "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-movflags", "+faststart", "-progress", "pipe:1", "-nostats", salida]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, errors="ignore")
    err_lineas: list[str] = []

    def _leer_err():
        for ln in proc.stderr:  # type: ignore[union-attr]
            err_lineas.append(ln)
    th = threading.Thread(target=_leer_err, daemon=True)
    th.start()
    for ln in proc.stdout:  # type: ignore[union-attr]
        if ln.startswith(("out_time_us=", "out_time_ms=")):
            try:
                us = int(ln.split("=", 1)[1].strip())
                pct = min(99, int(us / 1_000_000 / max(0.1, total) * 100))
                if progreso:
                    progreso(pct, "Renderizando…")
            except ValueError:
                pass
    proc.wait()
    th.join(timeout=2)
    try:
        for n in os.listdir(tmp):
            os.remove(os.path.join(tmp, n))
        os.rmdir(tmp)
    except OSError:
        pass
    if proc.returncode != 0 or not os.path.exists(salida) or os.path.getsize(salida) == 0:
        detalle = "".join(err_lineas)[-400:].strip()
        raise RuntimeError(f"FFmpeg falló: {detalle or 'sin detalle'}")
    out = sondear(salida)
    return {"ruta": salida, "ancho": W, "alto": H, "duracion": out.get("duracion", total), "bytes": os.path.getsize(salida),
            "segmentos": len(segmentos), "intro": con_intro, "cierre": con_cierre}


# ── trabajos en segundo plano ────────────────────────────────────────────────
def estado(vid: str) -> dict:
    with _lock:
        t = _trabajos.get(vid)
        return dict(t) if t else {"estado": "ninguno", "progreso": 0, "mensaje": ""}


def _poner(vid: str, **campos) -> None:
    with _lock:
        _trabajos.setdefault(vid, {"estado": "ninguno", "progreso": 0, "mensaje": "", "error": ""}).update(campos)


def olvidar(vid: str) -> None:
    with _lock:
        _trabajos.pop(vid, None)


def iniciar_trabajo(vid: str, ruta: str, salida: str, opciones: dict, *, transcripcion_previa: dict | None = None,
                    al_terminar=None) -> bool:
    """Lanza en un hilo: (transcribir si piden subtítulos y no hay) → pulir. Falso si ya hay uno corriendo."""
    with _lock:
        t = _trabajos.get(vid)
        if t and t.get("estado") in ("transcribiendo", "renderizando"):
            return False
        _trabajos[vid] = {"estado": "transcribiendo" if opciones.get("subtitulos") and not opciones.get("segmentos") and not transcripcion_previa
                          else "renderizando", "progreso": 0, "mensaje": "Preparando…", "error": "", "iniciado_en": time.time()}

    def _run():
        try:
            opts = dict(opciones)
            transcripcion = transcripcion_previa
            if opts.get("subtitulos") and not opts.get("segmentos"):
                if not transcripcion:
                    _poner(vid, estado="transcribiendo", progreso=3, mensaje="Transcribiendo el audio con Whisper…")
                    transcripcion = transcribir(ruta)
                opts["segmentos"] = (transcripcion or {}).get("segmentos") or []
            elif not opts.get("subtitulos"):
                opts["segmentos"] = []
            _poner(vid, estado="renderizando", progreso=5, mensaje="Renderizando…")
            res = pulir(ruta, salida, opts, progreso=lambda p, m: _poner(vid, progreso=max(5, p), mensaje=m))
            _poner(vid, estado="listo", progreso=100, mensaje="Listo", resultado=res, transcripcion=transcripcion)
            if al_terminar:
                al_terminar(vid, res, transcripcion)
        except Exception as e:  # noqa: BLE001
            print(f"[pulido] {vid} falló: {str(e)[:300]}", flush=True)
            _poner(vid, estado="error", mensaje="", error=str(e)[:300])
    threading.Thread(target=_run, daemon=True).start()
    return True
