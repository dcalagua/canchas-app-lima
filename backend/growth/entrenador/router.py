"""ENTRENADOR VIRTUAL (visión IA) — "un coach que ve tu video".

El jugador graba un clip corto de su golpe (saque, revés, bandeja…), el APK lo
sube al bucket `canchas` y llama a `POST /entrenador/analizar`. Aquí:

1. Se descarga el video, se extraen fotogramas clave (imageio-ffmpeg, ya
   empaquetado para los reels del CM) y se mandan a un modelo de VISIÓN con un
   prompt de entrenador profesional del deporte.
2. Se devuelve un INFORME estructurado (fortalezas, correcciones con su tip
   corto, drills) y se persiste en Supabase (`pichangol_entrenador_analisis`)
   para el historial device-first del APK.
3. **Tips al RELOJ**: si el jugador lo pidió, las correcciones se mandan como
   avisos push cortos (`pichangol_avisos` → push-aviso → FCM). Android espeja
   las notificaciones a cualquier smartwatch emparejado, así que el jugador
   las ve vibrar en la muñeca sin que exista una app de reloj. Sin reloj, los
   mismos tips quedan en el informe.

Candados: X-App-Key (APK oficial), Pro opcional (`ENTRENADOR_REQUIERE_PRO`,
fail-open como el CM), límite mensual por correo y tope de tamaño del video.
Multi-país: el análisis es por DEPORTE, nada depende del país.
Privacidad: el video NO se conserva aquí (se procesa y se descarta); en el
bucket el APK lo sube bajo `entrenador/` y la retención se poda como la media
del chat. El informe no incluye datos personales.
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import tempfile
import urllib.parse
import urllib.request
import uuid
from typing import Any

from fastapi import Depends, Header, HTTPException
from fastapi.routing import APIRouter
from pydantic import BaseModel

import config
from db.store import stores

router = APIRouter(prefix="/entrenador", tags=["entrenador"])


def _require_app_key(x_app_key: str | None = Header(default=None)) -> None:
    if not config.APP_API_KEY:
        return
    if x_app_key != config.APP_API_KEY:
        raise HTTPException(status_code=401, detail="app_key_invalida")


_APP = [Depends(_require_app_key)]

# Golpes conocidos por deporte (el APK manda por SELECCIÓN; esto solo acota el
# prompt — un golpe fuera de la lista igual se analiza como texto saneado).
_DEPORTES = {"tenis", "padel", "pickleball", "futbol", "voley", "basquet"}


class AnalizarReq(BaseModel):
    email: str
    deporte: str = "tenis"
    golpe: str = "saque"
    video_url: str
    tips_reloj: bool = False


def _limite_mes() -> int:
    try:
        return max(1, int(config.ENTRENADOR_LIMITE_MES))
    except (TypeError, ValueError):
        return 20


def _analisis_del_mes(email: str) -> int:
    """Cuántos análisis lleva el correo este mes (Supabase REST, fail-open)."""
    if not (config.SUPABASE_URL and config.SUPABASE_ANON_KEY):
        return 0
    try:
        from datetime import datetime, timezone
        ini = datetime.now(timezone.utc).replace(
            day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
        url = (f"{config.SUPABASE_URL}/rest/v1/pichangol_entrenador_analisis"
               f"?email=eq.{urllib.parse.quote(email)}"
               f"&creado=gte.{urllib.parse.quote(ini)}&select=id")
        req = urllib.request.Request(url, headers={
            "apikey": config.SUPABASE_ANON_KEY,
            "Authorization": f"Bearer {config.SUPABASE_ANON_KEY}",
        })
        with urllib.request.urlopen(req, timeout=10) as r:  # noqa: S310
            return len(json.loads(r.read() or b"[]"))
    except Exception:  # noqa: BLE001 — sin nube no se bloquea el análisis
        return 0


def _descargar_video(url: str) -> bytes:
    """Baja el clip (solo del propio Supabase del proyecto) con tope de MB."""
    base = (config.SUPABASE_URL or "").rstrip("/")
    if not base or not url.startswith(base):
        raise HTTPException(status_code=400, detail="video_url_invalida")
    try:
        max_bytes = int(float(config.ENTRENADOR_MAX_MB) * 1024 * 1024)
    except (TypeError, ValueError):
        max_bytes = 40 * 1024 * 1024
    try:
        with urllib.request.urlopen(url, timeout=60) as r:  # noqa: S310
            datos = r.read(max_bytes + 1)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502,
                            detail="video_no_descargable") from e
    if not datos:
        raise HTTPException(status_code=400, detail="video_vacio")
    if len(datos) > max_bytes:
        raise HTTPException(status_code=413, detail="video_muy_pesado")
    return datos


def _duracion_seg(exe: str, vin: str) -> float:
    """Duración del clip leyendo el stderr de `ffmpeg -i` (no hay ffprobe)."""
    import re
    out = subprocess.run(  # noqa: S603 — exe empaquetado, args fijos
        [exe, "-i", vin], check=False, capture_output=True, text=True,
        timeout=30)
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", out.stderr or "")
    if not m:
        return 0.0
    h, mi, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
    return h * 3600 + mi * 60 + s


def _extraer_frames(video: bytes, max_frames: int = 16) -> list[bytes]:
    """Fotogramas JPEG repartidos PAREJO por todo el clip (imageio-ffmpeg).

    Un golpe dura ~1.5 s: muestrear cada 2 s (versión inicial) casi nunca
    capturaba el swing y el coach reclamaba el encuadre. Ahora se lee la
    duración real y se extraen hasta [max_frames] cuadros equiespaciados
    (en un clip de 8 s ≈ uno cada 0.5 s: preparación, lanzamiento, impacto
    y terminación), a 800px para que se vea la mecánica.
    """
    import imageio_ffmpeg
    exe = imageio_ffmpeg.get_ffmpeg_exe()
    with tempfile.TemporaryDirectory() as d:
        vin = os.path.join(d, "clip.mp4")
        with open(vin, "wb") as f:
            f.write(video)
        dur = _duracion_seg(exe, vin)
        # Intervalo parejo sobre TODO el clip; nunca más fino que 0.15 s.
        intervalo = max(dur / max_frames if dur > 0 else 0.5, 0.15)
        patron = os.path.join(d, "f%02d.jpg")
        subprocess.run(  # noqa: S603 — exe empaquetado, args fijos
            [exe, "-y", "-i", vin, "-vf",
             f"fps=1/{intervalo:.3f},scale=800:-2",
             "-frames:v", str(max_frames), "-q:v", "4", patron],
            check=True, capture_output=True, timeout=120)
        frames = []
        for n in sorted(os.listdir(d)):
            if n.endswith(".jpg"):
                with open(os.path.join(d, n), "rb") as f:
                    frames.append(f.read())
    if not frames:
        raise HTTPException(status_code=422, detail="video_sin_frames")
    return frames


_INFORME_SPEC = (
    'Responde SOLO un JSON válido con esta forma exacta: {"encuadre_ok": bool, '
    '"resumen": str (2-3 frases, cálido y directo), '
    '"fortalezas": [str, máx 3], '
    '"correcciones": [{"titulo": str, "detalle": str, '
    '"tip_reloj": str (imperativo, MÁXIMO 42 caracteres, ej. '
    '"Lanza la pelota más arriba")}, máx 3], '
    '"drills": [str (ejercicio concreto para la próxima sesión), máx 3]}. '
    "REGLA DE ORO: ANALIZA PRIMERO. Los fotogramas son un muestreo del video "
    "(puede faltar el instante exacto del impacto): trabaja con las FASES que "
    "sí se ven (postura, preparación, lanzamiento, terminación) y entrega "
    "SIEMPRE fortalezas, correcciones y drills con lo observable. Pon "
    "encuadre_ok=false SOLO si la persona sale diminuta o cortada en la "
    "MAYORÍA de los fotogramas y de verdad no se distingue ninguna fase — e "
    "incluso en ese caso, entrega el análisis parcial de lo que se alcance a "
    "ver además de la sugerencia de encuadre. Nunca devuelvas las listas "
    "vacías solo por el encuadre."
)


def _ia_analizar(frames: list[bytes], deporte: str, golpe: str) -> dict | None:
    """Manda los fotogramas al modelo de visión. None si no hay IA disponible."""
    if not config.ANTHROPIC_API_KEY:
        return None
    try:
        import anthropic  # import perezoso, como el concierge
    except Exception:  # noqa: BLE001
        return None
    try:
        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        contenido: list[dict[str, Any]] = [{
            "type": "text",
            "text": (f"Fotogramas en orden cronológico (muestreo parejo de "
                     f"todo el clip) de mi {golpe} de {deporte}. "
                     "Analízalos como mi entrenador."),
        }]
        for fr in frames:
            contenido.append({
                "type": "image",
                "source": {"type": "base64", "media_type": "image/jpeg",
                           "data": base64.b64encode(fr).decode()},
            })
        resp = client.messages.create(
            model=config.ENTRENADOR_MODEL,
            max_tokens=1200,
            system=(
                f"Eres un entrenador profesional de {deporte} en Lima, con 20 "
                "años formando jugadores amateur. Analizas la técnica del "
                f"golpe '{golpe}' viendo fotogramas de un video del alumno. "
                "Hablas en español peruano, cercano y motivador, pero tus "
                "correcciones son técnicas y concretas (preparación, punto de "
                "impacto, transferencia de peso, terminación). Nunca inventas "
                "lo que no se ve. " + _INFORME_SPEC
            ),
            messages=[{"role": "user", "content": contenido}],
        )
        texto = next(
            (b.text for b in resp.content if getattr(b, "type", "") == "text"),
            "")
        data = _parsear_json(texto)
        return data if isinstance(data, dict) and data.get("resumen") else None
    except Exception:  # noqa: BLE001 — la IA nunca tumba el endpoint
        return None


def _parsear_json(texto: str) -> Any:
    t = (texto or "").strip()
    if t.startswith("```"):
        t = t.strip("`")
        if t[:4].lower() == "json":
            t = t[4:]
    ini, fin = t.find("{"), t.rfind("}")
    if ini < 0 or fin <= ini:
        return None
    try:
        return json.loads(t[ini:fin + 1])
    except (ValueError, TypeError):
        return None


def _persistir(analisis_id: str, email: str, deporte: str, golpe: str,
               informe: dict) -> None:
    """Guarda el informe en Supabase para el historial. Best-effort."""
    if not (config.SUPABASE_URL and config.SUPABASE_ANON_KEY):
        return
    try:
        cuerpo = json.dumps({
            "id": analisis_id, "email": email, "deporte": deporte,
            "golpe": golpe, "informe": informe,
        }).encode()
        req = urllib.request.Request(
            f"{config.SUPABASE_URL}/rest/v1/pichangol_entrenador_analisis",
            data=cuerpo, method="POST",
            headers={
                "apikey": config.SUPABASE_ANON_KEY,
                "Authorization": f"Bearer {config.SUPABASE_ANON_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal",
            })
        with urllib.request.urlopen(req, timeout=10) as r:  # noqa: S310
            r.read()
    except Exception:  # noqa: BLE001
        pass


def _tips_al_reloj(email: str, deporte: str, informe: dict) -> int:
    """Manda las correcciones como avisos push CORTOS (el teléfono los espeja
    al smartwatch emparejado). Devuelve cuántos tips salieron."""
    tips = [
        (c.get("tip_reloj") or "").strip()
        for c in (informe.get("correcciones") or [])
        if isinstance(c, dict) and (c.get("tip_reloj") or "").strip()
    ][:3]
    if not tips:
        return 0
    from pagos.router import _aviso_push_usuario
    emoji = {"tenis": "🎾", "padel": "🎾", "pickleball": "🏓",
             "futbol": "⚽", "voley": "🏐", "basquet": "🏀"}.get(deporte, "🏅")
    for tip in tips:
        _aviso_push_usuario(email, f"{emoji} Tip de tu entrenador",
                            tip[:60], tipo="entrenador")
    return len(tips)


@router.post("/analizar", dependencies=_APP)
def post_analizar(req: AnalizarReq) -> dict:
    email = req.email.strip().lower()
    if not email or "@" not in email:
        return {"ok": False, "error": "email_requerido"}
    deporte = req.deporte if req.deporte in _DEPORTES else "tenis"
    golpe = (req.golpe or "saque").strip()[:30]

    # Candado Pro (fail-open, mismo criterio que el CM): apagado por defecto;
    # encendido, solo bloquea a quien SÍ se identifica y no es Pro.
    if config.ENTRENADOR_REQUIERE_PRO and not stores.pro_activo(email):
        raise HTTPException(status_code=402, detail="requiere_pro")

    # Límite mensual (control de costo de visión).
    limite = _limite_mes()
    usados = _analisis_del_mes(email)
    if usados >= limite:
        raise HTTPException(status_code=429, detail="limite_mensual")

    video = _descargar_video(req.video_url)
    frames = _extraer_frames(video)
    informe = _ia_analizar(frames, deporte, golpe)
    if informe is None:
        # Sin IA configurada / caída: nunca dejamos al jugador sin respuesta.
        raise HTTPException(status_code=503, detail="entrenador_no_disponible")

    analisis_id = f"ent_{uuid.uuid4().hex[:12]}"
    _persistir(analisis_id, email, deporte, golpe, informe)
    tips = _tips_al_reloj(email, deporte, informe) if req.tips_reloj else 0
    return {"ok": True, "id": analisis_id, "informe": informe,
            "tips_reloj_enviados": tips,
            "analisis_restantes_mes": max(0, limite - usados - 1)}
