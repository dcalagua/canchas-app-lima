"""Música ORIGINAL (libre de regalías) para los reels del community manager.

La componemos nosotros con numpy (síntesis): acordes tipo pad + un kick suave, en
distintos "moods". Al generarla nosotros es **100% libre de derechos** (no viaja
ningún audio de terceros, no hay licencias que gestionar) y corre offline en
Railway. Devuelve un WAV (16-bit PCM) que el reel muxea con el ffmpeg empaquetado.

Fail-safe: si numpy no está, devuelve None y el reel sale sin audio (como antes).
"""

from __future__ import annotations

import io
import wave

_SR = 44100  # sample rate

# MIDI de las notas de cada acorde por "mood" (progresión de 4 acordes). Se elige
# el mood para que cada reel suene distinto pero siempre agradable de fondo.
_MOODS = {
    # Mayor, brillante y movido (para promos / energía).
    "energetico": {
        "bpm": 120,
        "acordes": [[60, 64, 67], [67, 71, 74], [69, 72, 76], [65, 69, 72]],
        "kick": True,
    },
    # Menor 7 suave, relajado (para tips / testimonios).
    "chill": {
        "bpm": 88,
        "acordes": [[57, 60, 64, 67], [62, 65, 69], [55, 59, 62], [60, 64, 67]],
        "kick": True,
    },
    # Menor amplio, algo épico (para logros / resultados).
    "epico": {
        "bpm": 100,
        "acordes": [[57, 60, 64], [53, 57, 60], [55, 59, 62], [58, 62, 65]],
        "kick": True,
    },
}

MOODS = tuple(_MOODS.keys())


def _freq(midi: int) -> float:
    return 440.0 * (2.0 ** ((midi - 69) / 12.0))


def _pad(np, notas: list[int], dur: float) -> "any":
    """Un acorde tipo 'pad': suma de notas con timbre suave (fundamental + 5ª +
    octava tenues) y envolvente de ataque/caída lento."""
    n = int(dur * _SR)
    t = np.linspace(0, dur, n, endpoint=False)
    onda = np.zeros(n, dtype=np.float64)
    for m in notas:
        f = _freq(m)
        onda += np.sin(2 * np.pi * f * t)
        onda += 0.28 * np.sin(2 * np.pi * f * 2 * t)   # octava (brillo)
        onda += 0.16 * np.sin(2 * np.pi * f * 1.5 * t)  # 5ª (cuerpo)
    onda /= max(1, len(notas)) * 1.4
    # Envolvente suave (ataque 12%, caída larga) → nada de clicks.
    env = np.ones(n)
    a = int(0.12 * n)
    d = int(0.25 * n)
    if a > 0:
        env[:a] = np.linspace(0, 1, a)
    if d > 0:
        env[-d:] = np.linspace(1, 0.55, d)
    return onda * env


def _kick(np, dur_total: float, bpm: int) -> "any":
    """Bombo suave: un pulso grave con caída rápida en cada tiempo."""
    n = int(dur_total * _SR)
    out = np.zeros(n, dtype=np.float64)
    paso = 60.0 / bpm  # segundos por tiempo
    ln = int(0.12 * _SR)
    tt = np.linspace(0, 0.12, ln, endpoint=False)
    # Barrido de frecuencia 110→45 Hz con caída exponencial (thump).
    puls = np.sin(2 * np.pi * (110 - 65 * tt / 0.12) * tt) * np.exp(-tt * 26)
    tiempo = 0.0
    while tiempo < dur_total:
        i = int(tiempo * _SR)
        j = min(n, i + ln)
        out[i:j] += puls[: j - i]
        tiempo += paso
    return out * 0.6


def generar_pista(segundos: float, mood: str | None = None) -> bytes | None:
    """Devuelve un WAV (bytes) de [segundos] con música original del [mood], o
    None si numpy no está. Pensada como fondo (volumen moderado)."""
    try:
        import numpy as np
    except Exception:  # noqa: BLE001
        return None

    dur = max(1.0, float(segundos))
    if mood not in _MOODS:
        mood = "chill"
    cfg = _MOODS[mood]
    bpm = int(cfg["bpm"])
    compas = 4 * (60.0 / bpm)  # 4 tiempos por acorde

    # Construye la progresión repitiéndola hasta cubrir la duración.
    trozos = []
    total = 0.0
    idx = 0
    acordes = cfg["acordes"]
    while total < dur:
        onda = _pad(np, acordes[idx % len(acordes)], compas)
        trozos.append(onda)
        total += compas
        idx += 1
    pista = np.concatenate(trozos)[: int(dur * _SR)]

    if cfg.get("kick"):
        pista = pista + _kick(np, dur, bpm)[: len(pista)]

    # Normaliza y deja headroom (fondo, no debe tapar nada).
    pico = float(np.max(np.abs(pista))) or 1.0
    pista = pista / pico * 0.72

    # Fade in/out global (2% cada lado) para que entre y salga limpio.
    n = len(pista)
    f = max(1, int(0.03 * n))
    pista[:f] *= np.linspace(0, 1, f)
    pista[-f:] *= np.linspace(1, 0, f)

    pcm = np.clip(pista * 32767, -32768, 32767).astype("<i2")

    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(_SR)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()
