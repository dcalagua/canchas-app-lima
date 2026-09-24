"""MI MÚSICA DESDE GOOGLE DRIVE (pedido del director, 24-sep-2026: "subo mi música
en una carpeta de mi Google Drive y desde ahí la elijo para los videos").

Spotify no sirve (su API no entrega audio y la música comercial la silencia
Facebook), así que la fuente son PISTAS CON DERECHOS que el director guarda en
UNA carpeta de su Drive. La torre:

1. **Conecta Google Drive** con el MISMO cliente OAuth de Google Fotos, sumando
   el scope `drive.readonly` (autorización incremental: la conexión de Fotos se
   conserva; el refresh token nuevo sirve para ambos).
2. **Elige la carpeta** (pegando el enlace de Drive o buscándola por nombre) y la
   guarda en `stores.config[gdrive_musica_carpeta]`.
3. **Sincroniza**: lista los audios de la carpeta (mp3, m4a, wav, ogg, aac, flac),
   descarga los nuevos o cambiados y los sube a Storage `canchas/marca/musica/`
   (así el render y el agente no dependen del token de Drive), y quita del
   catálogo los que ya no están en la carpeta. Catálogo en `stores.musica_marca`.
4. **Usa**: el pulido de video acepta `musica_pista=<id>` (la pista reemplaza a la
   música sintetizada, en bucle si es más corta, con el volumen del modo elegido)
   y el agente 24×7 rota la pista menos usada.
"""
from __future__ import annotations

import os
import re
import tempfile
import time
import urllib.parse
import urllib.request
import uuid

import config
from db.store import stores
from marketing import biblioteca as _bib

SCOPE_DRIVE = "https://www.googleapis.com/auth/drive.readonly"
DRIVE = "https://www.googleapis.com/drive/v3"
CARPETA_STORAGE = "marca/musica"
CFG_CARPETA = "gdrive_musica_carpeta"
CFG_CARPETA_NOMBRE = "gdrive_musica_carpeta_nombre"
CFG_SYNC = "gdrive_musica_sync_en"
PISTA_MAX_BYTES = int(os.getenv("MUSICA_PISTA_MAX_MB", "30") or 30) * 1024 * 1024
MAX_PISTAS = 200
EXT_AUDIO = {"mp3": "audio/mpeg", "m4a": "audio/mp4", "wav": "audio/wav", "ogg": "audio/ogg", "aac": "audio/aac", "flac": "audio/flac", "opus": "audio/ogg"}


# ── estado / conexión ────────────────────────────────────────────────────────
def conectado() -> bool:
    """Google conectado Y con el permiso de Drive (los scopes se guardan al canjear el código)."""
    return _bib.conectado() and SCOPE_DRIVE in (stores.config.get(_bib.CFG_SCOPES, "") or "")


def carpeta() -> dict:
    return {"id": stores.config.get(CFG_CARPETA, "") or "", "nombre": stores.config.get(CFG_CARPETA_NOMBRE, "") or ""}


def estado() -> dict:
    c = carpeta()
    return {"credenciales": _bib.credenciales(), "google": _bib.conectado(), "conectado": conectado(), "cuenta": stores.config.get(_bib.CFG_CUENTA, ""),
            "carpeta": c, "storage": _bib._storage_disponible(), "pistas": len(stores.musica_marca),
            "sync_en": float(stores.config.get(CFG_SYNC, "0") or 0), "max_mb": PISTA_MAX_BYTES // (1024 * 1024)}


def url_autorizacion() -> str:
    """OAuth con Fotos + Drive (incremental)."""
    return _bib.url_autorizacion(scopes_extra=[SCOPE_DRIVE])


def _persistir() -> None:
    _bib._persistir()


# ── Drive API ────────────────────────────────────────────────────────────────
def _get(path: str, **params) -> dict:
    params.setdefault("supportsAllDrives", "true")
    q = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    return _bib._http_json(f"{DRIVE}/{path}?{q}", token=_bib._access_token())


def carpeta_desde_enlace(texto: str) -> str:
    """ID de carpeta desde un enlace de Drive (…/folders/<id>, ?id=<id>) o el ID pelado."""
    t = (texto or "").strip()
    m = re.search(r"/folders/([A-Za-z0-9_-]{10,})", t) or re.search(r"[?&]id=([A-Za-z0-9_-]{10,})", t)
    if m:
        return m.group(1)
    return t if re.fullmatch(r"[A-Za-z0-9_-]{10,}", t) else ""


def elegir_carpeta(enlace_o_id: str) -> dict:
    """Valida contra Drive que sea una carpeta accesible y la guarda."""
    fid = carpeta_desde_enlace(enlace_o_id)
    if not fid:
        raise RuntimeError("Pega el enlace de la carpeta de Drive (…/drive/folders/…) o su ID.")
    meta = _get(f"files/{urllib.parse.quote(fid)}", fields="id,name,mimeType")
    if meta.get("mimeType") != "application/vnd.google-apps.folder":
        raise RuntimeError(f"\"{meta.get('name') or fid}\" no es una carpeta de Drive.")
    stores.config[CFG_CARPETA] = str(meta["id"])
    stores.config[CFG_CARPETA_NOMBRE] = str(meta.get("name") or "")
    _persistir()
    return {"id": meta["id"], "nombre": meta.get("name") or ""}


def buscar_carpetas(q: str = "") -> list[dict]:
    """Carpetas del Drive del director (por nombre, o las últimas modificadas)."""
    filtro = "mimeType='application/vnd.google-apps.folder' and trashed=false"
    if (q or "").strip():
        filtro += " and name contains '" + q.strip().replace("\\", "\\\\").replace("'", "\\'") + "'"
    r = _get("files", q=filtro, fields="files(id,name,modifiedTime,parents)", pageSize=25, orderBy="modifiedTime desc",
             includeItemsFromAllDrives="true", corpora="allDrives")
    return [{"id": f["id"], "nombre": f.get("name", ""), "modificada": f.get("modifiedTime", "")} for f in r.get("files") or []]


def _ext_de(nombre: str, mime: str) -> str:
    ext = (nombre.rsplit(".", 1)[-1].lower() if "." in nombre else "")
    if ext in EXT_AUDIO:
        return ext
    for e, m in EXT_AUDIO.items():
        if mime and mime.split(";")[0] == m:
            return e
    return "mp3" if (mime or "").startswith("audio/") else ""


def listar_audio(carpeta_id: str) -> list[dict]:
    out, page = [], ""
    while True:
        r = _get("files", q=f"'{carpeta_id}' in parents and trashed=false", fields="nextPageToken,files(id,name,mimeType,size,md5Checksum,modifiedTime)",
                 pageSize=200, pageToken=page or None, includeItemsFromAllDrives="true", orderBy="name")
        for f in r.get("files") or []:
            ext = _ext_de(str(f.get("name") or ""), str(f.get("mimeType") or ""))
            if ext:
                out.append({"drive_id": f["id"], "nombre": f.get("name", ""), "mime": EXT_AUDIO[ext], "ext": ext, "bytes": int(f.get("size") or 0),
                            "md5": f.get("md5Checksum", ""), "modificado": f.get("modifiedTime", "")})
        page = str(r.get("nextPageToken") or "")
        if not page or len(out) >= MAX_PISTAS:
            break
    return out


def sincronizar() -> dict:
    """Trae a Storage los audios nuevos/cambiados de la carpeta y quita los que ya no están."""
    if not conectado():
        raise RuntimeError("Conecta Google Drive primero.")
    c = carpeta()
    if not c["id"]:
        raise RuntimeError("Elige la carpeta de música primero.")
    tok = _bib._access_token()
    en_drive = listar_audio(c["id"])
    actuales = {x.get("drive_id"): x for x in stores.musica_marca}
    nuevos, actualizados, quitados, omitidos, detalle = 0, 0, 0, 0, []
    vistos = set()
    for f in en_drive:
        vistos.add(f["drive_id"])
        prev = actuales.get(f["drive_id"])
        if prev and prev.get("md5") == f["md5"] and prev.get("md5"):
            continue                                        # sin cambios
        if f["bytes"] > PISTA_MAX_BYTES:
            omitidos += 1
            detalle.append(f"{f['nombre']}: pesa más de {PISTA_MAX_BYTES // (1024 * 1024)} MB")
            continue
        try:
            datos = _bib._descargar(f"{DRIVE}/files/{urllib.parse.quote(f['drive_id'])}?alt=media&supportsAllDrives=true", tok, PISTA_MAX_BYTES)
            iid = prev["id"] if prev else "mm_" + uuid.uuid4().hex[:12]
            url = _bib._subir(f"{CARPETA_STORAGE}/{iid}.{f['ext']}", datos, f["mime"])
            fila = {"id": iid, "drive_id": f["drive_id"], "nombre": f["nombre"], "mime": f["mime"], "ext": f["ext"], "url": url, "bytes": len(datos),
                    "md5": f["md5"], "modificado": f["modificado"], "creado_en": prev["creado_en"] if prev else time.time(),
                    "usos": int(prev.get("usos") or 0) if prev else 0, "ultimo_uso": float(prev.get("ultimo_uso") or 0) if prev else 0.0, "origen": "google_drive"}
            if prev:
                stores.musica_marca[:] = [fila if x.get("id") == iid else x for x in stores.musica_marca]
                actualizados += 1
            else:
                stores.musica_marca.append(fila)
                nuevos += 1
            _olvidar_temporal(iid)
        except Exception as e:  # noqa: BLE001
            omitidos += 1
            detalle.append(f"{f['nombre']}: {str(e)[:120]}")
    for x in list(stores.musica_marca):
        if x.get("origen") == "google_drive" and x.get("drive_id") not in vistos:
            quitar(x["id"], persistir=False)
            quitados += 1
    stores.musica_marca.sort(key=lambda x: (x.get("nombre") or "").lower())
    del stores.musica_marca[MAX_PISTAS:]
    stores.config[CFG_SYNC] = str(time.time())
    _persistir()
    print(f"[musica] Drive sincronizado: {nuevos} nuevas · {actualizados} actualizadas · {quitados} quitadas · {omitidos} omitidas", flush=True)
    return {"nuevos": nuevos, "actualizados": actualizados, "quitados": quitados, "omitidos": omitidos, "detalle": detalle[:20], "total": len(stores.musica_marca)}


# ── catálogo ─────────────────────────────────────────────────────────────────
def items() -> list[dict]:
    return [dict(x) for x in stores.musica_marca]


def item(iid: str) -> dict | None:
    return next((dict(x) for x in stores.musica_marca if x.get("id") == iid), None)


def quitar(iid: str, *, persistir: bool = True) -> bool:
    x = item(iid)
    if not x:
        return False
    try:
        from web import almacen
        almacen.borrar_foto(x.get("url") or "")
    except Exception:  # noqa: BLE001
        pass
    stores.musica_marca[:] = [y for y in stores.musica_marca if y.get("id") != iid]
    _olvidar_temporal(iid)
    if persistir:
        _persistir()
    return True


def marcar_uso(iid: str) -> None:
    for y in stores.musica_marca:
        if y.get("id") == iid:
            y["usos"] = int(y.get("usos") or 0) + 1
            y["ultimo_uso"] = time.time()


def elegir_pista() -> dict | None:
    """La pista MENOS usada (y con el último uso más antiguo): rotación justa para el agente."""
    pistas = sorted(items(), key=lambda x: (int(x.get("usos") or 0), float(x.get("ultimo_uso") or 0)))
    return pistas[0] if pistas else None


def _ruta_temporal(iid: str, ext: str) -> str:
    return os.path.join(tempfile.gettempdir(), f"pcg_mus_{iid}.{ext}")


def _olvidar_temporal(iid: str) -> None:
    for ext in EXT_AUDIO:
        try:
            os.remove(_ruta_temporal(iid, ext))
        except OSError:
            pass


def descargar_a_temporal(iid: str) -> str:
    """Copia local de la pista (desde Storage) para pasársela a FFmpeg."""
    x = item(iid)
    if not x:
        raise RuntimeError("Esa pista ya no está en Mi música.")
    ruta = _ruta_temporal(iid, x.get("ext") or "mp3")
    if os.path.exists(ruta) and os.path.getsize(ruta) > 0:
        return ruta
    req = urllib.request.Request(x["url"], headers={"User-Agent": "Pichangol-Torre/1.0"})
    with urllib.request.urlopen(req, timeout=120) as r, open(ruta, "wb") as f:
        while True:
            trozo = r.read(1024 * 1024)
            if not trozo:
                break
            f.write(trozo)
    return ruta
