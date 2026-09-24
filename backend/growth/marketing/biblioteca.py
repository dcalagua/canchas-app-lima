"""BIBLIOTECA DE MARCA + GOOGLE FOTOS (pedido del director, 24-sep-2026: "quiero
enlazar mi Google Fotos para que desde ahí agarres las fotos y videos y hagas el
post; los videos deben tener música").

Google cerró en 2025 la lectura de la biblioteca completa por API: hoy una app
solo puede leer lo que el usuario ELIGE en el selector oficial de Google Fotos
(**Google Photos Picker API**). El flujo, entonces:

1. **Conectar** (una vez): OAuth de Google con `GOOGLE_WEB_CLIENT_ID` +
   `GOOGLE_WEB_CLIENT_SECRET` (el mismo cliente "Aplicación web" del login; hay
   que registrar como URI de redirección
   `{PUBLIC_BASE_URL}/admin/api/redes/biblioteca/google/callback` y habilitar la
   "Google Photos Picker API" en el proyecto). Se guarda el *refresh token*
   cifrado en el snapshot (`stores.config`), como el token de Facebook.
2. **Elegir**: la torre abre una sesión del Picker (`pickerUri`); el director
   marca fotos y videos en la interfaz de Google Fotos; la torre sondea la
   sesión y, cuando terminó, **importa** cada elemento (descarga con el token y
   lo sube a Supabase Storage `canchas/marca/biblioteca/`) porque las URLs de
   Google caducan en ~1 h. Queda un catálogo en `stores.biblioteca_marca`.
3. **Usar**: el pane de Facebook ofrece la biblioteca (fotos → collage; video →
   flujo de pulido con MÚSICA por defecto) y el agente 24×7 la prefiere sobre el
   arte IA: fotos menos usadas primero y, cuando hay un video sin usar, publica
   video pulido con intro, marca de agua, cierre y música original.

Fail-safe: sin credenciales de Google la sección explica qué falta; sin Storage
no se importa nada (se avisa). Nada de esto toca la app del jugador.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

import config
from db.store import stores

SCOPES = "https://www.googleapis.com/auth/photospicker.mediaitems.readonly openid email"
PICKER = "https://photospicker.googleapis.com/v1"
CARPETA = "marca/biblioteca"
CFG_REFRESH = "gfotos_refresh_cifrado"
CFG_CUENTA = "gfotos_cuenta"
CFG_CONECTADO = "gfotos_conectado_en"
FOTO_MAX_BYTES = 12 * 1024 * 1024
VIDEO_MAX_BYTES = int(os.getenv("BIBLIOTECA_VIDEO_MAX_MB", "150") or 150) * 1024 * 1024
MAX_ITEMS = 400
_access: dict = {"token": "", "hasta": 0.0}


# ── configuración / estado ───────────────────────────────────────────────────
def credenciales() -> bool:
    return bool(config.GOOGLE_WEB_CLIENT_ID and config.GOOGLE_WEB_CLIENT_SECRET)


def redirect_uri() -> str:
    base = (config.PUBLIC_BASE_URL or "").rstrip("/")
    return f"{base}/admin/api/redes/biblioteca/google/callback" if base else ""


def conectado() -> bool:
    return bool(stores.config.get(CFG_REFRESH))


def estado() -> dict:
    return {"credenciales": credenciales(), "conectado": conectado(), "cuenta": stores.config.get(CFG_CUENTA, ""),
            "conectado_en": float(stores.config.get(CFG_CONECTADO, "0") or 0), "redirect_uri": redirect_uri(),
            "storage": _storage_disponible(), "fotos": sum(1 for x in items() if x.get("tipo") == "foto"),
            "videos": sum(1 for x in items() if x.get("tipo") == "video")}


def _storage_disponible() -> bool:
    try:
        from web import almacen
        return almacen.disponible()
    except Exception:  # noqa: BLE001
        return False


def _persistir() -> None:
    try:
        from pagos.router import _persistir_ahora
        _persistir_ahora()
    except Exception:  # noqa: BLE001
        pass


# ── OAuth ────────────────────────────────────────────────────────────────────
def _secreto() -> bytes:
    return (config.ADMIN_PANEL_TOKEN or config.APP_API_KEY or "pichangol-biblioteca").encode()


def firmar_estado() -> str:
    """`state` de OAuth firmado (10 min): el callback vuelve SIN cabecera de admin,
    así que la firma es lo que prueba que la autorización la inició la torre."""
    ts = str(int(time.time()))
    firma = hmac.new(_secreto(), ts.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{ts}.{firma}"


def estado_valido(state: str) -> bool:
    try:
        ts, firma = (state or "").split(".", 1)
        if abs(time.time() - int(ts)) > 600:
            return False
        return hmac.compare_digest(hmac.new(_secreto(), ts.encode(), hashlib.sha256).hexdigest()[:32], firma)
    except (ValueError, AttributeError):
        return False


def url_autorizacion() -> str:
    q = {"client_id": config.GOOGLE_WEB_CLIENT_ID, "redirect_uri": redirect_uri(), "response_type": "code", "scope": SCOPES,
         "access_type": "offline", "prompt": "consent", "include_granted_scopes": "true", "state": firmar_estado()}
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(q)


def _http_json(url: str, *, datos: dict | None = None, form: dict | None = None, token: str = "", metodo: str | None = None, timeout: int = 30) -> dict:
    cuerpo = None
    headers = {}
    if form is not None:
        cuerpo = urllib.parse.urlencode(form).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    elif datos is not None:
        cuerpo = json.dumps(datos).encode()
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=cuerpo, method=metodo or ("POST" if cuerpo is not None else "GET"), headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8")
            return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as e:
        try:
            detalle = json.loads(e.read().decode("utf-8", "ignore"))
            msg = (detalle.get("error") or {}).get("message") if isinstance(detalle.get("error"), dict) else detalle.get("error_description") or detalle.get("error")
        except Exception:  # noqa: BLE001
            msg = ""
        raise RuntimeError(f"Google respondió {e.code}: {msg or 'error'}") from e


def canjear_codigo(code: str) -> dict:
    """code → refresh token (se guarda cifrado) + cuenta. Devuelve {cuenta}."""
    from marketing import redes
    t = _http_json("https://oauth2.googleapis.com/token", form={"code": code, "client_id": config.GOOGLE_WEB_CLIENT_ID,
                                                                 "client_secret": config.GOOGLE_WEB_CLIENT_SECRET,
                                                                 "redirect_uri": redirect_uri(), "grant_type": "authorization_code"})
    refresh = str(t.get("refresh_token") or "")
    if not refresh:
        raise RuntimeError("Google no entregó un refresh token. Vuelve a conectar y acepta todos los permisos (si ya habías autorizado antes, "
                           "revoca el acceso en myaccount.google.com/permissions y repite).")
    cuenta = ""
    try:
        info = _http_json("https://openidconnect.googleapis.com/v1/userinfo", token=str(t.get("access_token") or ""))
        cuenta = str(info.get("email") or "")
    except Exception:  # noqa: BLE001
        pass
    stores.config[CFG_REFRESH] = redes.cifrar(refresh)
    stores.config[CFG_CUENTA] = cuenta
    stores.config[CFG_CONECTADO] = str(time.time())
    _access.update(token=str(t.get("access_token") or ""), hasta=time.time() + int(t.get("expires_in") or 3000) - 60)
    _persistir()
    return {"cuenta": cuenta}


def desconectar() -> None:
    stores.config.pop(CFG_REFRESH, None)
    stores.config.pop(CFG_CUENTA, None)
    stores.config.pop(CFG_CONECTADO, None)
    _access.update(token="", hasta=0.0)


def _access_token() -> str:
    from marketing import redes
    if _access["token"] and _access["hasta"] > time.time():
        return _access["token"]
    refresh = redes.descifrar(stores.config.get(CFG_REFRESH, "") or "")
    if not refresh:
        raise RuntimeError("Google Fotos no está conectado.")
    try:
        t = _http_json("https://oauth2.googleapis.com/token", form={"refresh_token": refresh, "client_id": config.GOOGLE_WEB_CLIENT_ID,
                                                                     "client_secret": config.GOOGLE_WEB_CLIENT_SECRET, "grant_type": "refresh_token"})
    except RuntimeError as e:
        if "invalid_grant" in str(e) or "401" in str(e) or "400" in str(e):
            desconectar()
            raise RuntimeError("Google revocó el acceso a Google Fotos: vuelve a conectar la cuenta desde la torre.") from e
        raise
    _access.update(token=str(t.get("access_token") or ""), hasta=time.time() + int(t.get("expires_in") or 3000) - 60)
    return _access["token"]


# ── Picker API ───────────────────────────────────────────────────────────────
def crear_sesion() -> dict:
    s = _http_json(f"{PICKER}/sessions", datos={}, token=_access_token())
    return {"id": s.get("id", ""), "pickerUri": s.get("pickerUri", ""),
            "poll_ms": int(str((s.get("pollingConfig") or {}).get("pollInterval", "3s")).rstrip("s") or 3) * 1000}


def estado_sesion(sesion_id: str) -> dict:
    s = _http_json(f"{PICKER}/sessions/{urllib.parse.quote(sesion_id)}", token=_access_token())
    return {"listo": bool(s.get("mediaItemsSet")), "raw": s}


def _items_sesion(sesion_id: str) -> list[dict]:
    tok = _access_token()
    out, page = [], ""
    while True:
        q = {"sessionId": sesion_id, "pageSize": "100"}
        if page:
            q["pageToken"] = page
        r = _http_json(f"{PICKER}/mediaItems?{urllib.parse.urlencode(q)}", token=tok)
        out.extend(r.get("mediaItems") or [])
        page = str(r.get("nextPageToken") or "")
        if not page or len(out) >= MAX_ITEMS:
            break
    return out


def _cerrar_sesion(sesion_id: str) -> None:
    try:
        _http_json(f"{PICKER}/sessions/{urllib.parse.quote(sesion_id)}", token=_access_token(), metodo="DELETE")
    except Exception:  # noqa: BLE001
        pass


def _descargar(url: str, token: str, tope: int, timeout: int = 180) -> bytes:
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        datos = r.read(tope + 1)
    if len(datos) > tope:
        raise RuntimeError("archivo demasiado grande")
    return datos


def _subir(ruta: str, datos: bytes, mime: str) -> str:
    from web import almacen
    url = almacen.subir(almacen.BUCKET, ruta, datos, mime, max_bytes=max(FOTO_MAX_BYTES, VIDEO_MAX_BYTES))
    if not url:
        raise RuntimeError("Storage rechazó la subida (revisa SUPABASE_URL/ANON_KEY y el tamaño máximo del bucket).")
    return url.split("?")[0]


def importar_sesion(sesion_id: str) -> dict:
    """Trae a la biblioteca lo elegido en el Picker. Devuelve {importados, omitidos, detalle}."""
    tok = _access_token()
    elegidos = _items_sesion(sesion_id)
    importados, omitidos, detalle = 0, 0, []
    existentes = {x.get("google_id") for x in items()}
    for m in elegidos:
        gid = str(m.get("id") or "")
        mf = m.get("mediaFile") or {}
        mime = str(mf.get("mimeType") or "")
        base = str(mf.get("baseUrl") or "")
        tipo = "video" if str(m.get("type") or "").upper() == "VIDEO" or mime.startswith("video/") else "foto"
        if not gid or not base:
            omitidos += 1
            continue
        if gid in existentes:
            omitidos += 1
            detalle.append(f"{mf.get('filename') or gid}: ya estaba en la biblioteca")
            continue
        meta = mf.get("mediaFileMetadata") or {}
        try:
            if tipo == "video":
                estado_v = str(((meta.get("videoMetadata") or {}).get("processingStatus") or "READY")).upper()
                if estado_v not in ("READY", "PROCESSING_STATUS_UNSPECIFIED"):
                    raise RuntimeError("Google aún está procesando el video; inténtalo en unos minutos")
                datos = _descargar(base + "=dv", tok, VIDEO_MAX_BYTES)
                ext = "mp4" if "mp4" in mime or not mime else re.sub(r"[^a-z0-9]", "", mime.split("/")[-1])[:4] or "mp4"
                mime_sub = mime or "video/mp4"
            else:
                datos = _descargar(base + "=w2048-h2048", tok, FOTO_MAX_BYTES)
                ext, mime_sub = "jpg", "image/jpeg"
            iid = "bm_" + uuid.uuid4().hex[:12]
            url = _subir(f"{CARPETA}/{iid}.{ext}", datos, mime_sub)
            ancho, alto = int(meta.get("width") or 0), int(meta.get("height") or 0)
            dur_ms = 0
            vm = meta.get("videoMetadata") or {}
            if vm.get("fps") is not None or tipo == "video":
                dur_ms = int(float(str(m.get("duration") or vm.get("duration") or "0s").rstrip("s") or 0) * 1000) if isinstance(m.get("duration") or vm.get("duration"), str) else 0
            stores.biblioteca_marca.insert(0, {"id": iid, "google_id": gid, "tipo": tipo, "url": url, "mime": mime_sub, "nombre": str(mf.get("filename") or ""),
                                               "ancho": ancho, "alto": alto, "duracion_ms": dur_ms, "bytes": len(datos), "creado_en": time.time(),
                                               "tomada_en": str(m.get("createTime") or ""), "origen": "google_fotos", "usos": 0, "ultimo_uso": 0.0})
            existentes.add(gid)
            importados += 1
        except Exception as e:  # noqa: BLE001
            omitidos += 1
            detalle.append(f"{mf.get('filename') or gid}: {str(e)[:120]}")
    del stores.biblioteca_marca[MAX_ITEMS:]
    _cerrar_sesion(sesion_id)
    if importados:
        _persistir()
        print(f"[biblioteca] importados {importados} de Google Fotos (omitidos {omitidos})", flush=True)
    return {"importados": importados, "omitidos": omitidos, "detalle": detalle[:20]}


# ── catálogo ─────────────────────────────────────────────────────────────────
def items(tipo: str | None = None) -> list[dict]:
    return [dict(x) for x in stores.biblioteca_marca if not tipo or x.get("tipo") == tipo]


def item(iid: str) -> dict | None:
    return next((dict(x) for x in stores.biblioteca_marca if x.get("id") == iid), None)


def quitar(iid: str) -> bool:
    x = item(iid)
    if not x:
        return False
    try:
        from web import almacen
        almacen.borrar_foto(x.get("url") or "")
    except Exception:  # noqa: BLE001
        pass
    stores.biblioteca_marca[:] = [y for y in stores.biblioteca_marca if y.get("id") != iid]
    return True


def marcar_uso(ids: list[str]) -> None:
    for y in stores.biblioteca_marca:
        if y.get("id") in ids:
            y["usos"] = int(y.get("usos") or 0) + 1
            y["ultimo_uso"] = time.time()


def elegir_fotos(n: int = 3) -> list[dict]:
    """Las fotos MENOS usadas y más antiguas en su último uso (rotación justa)."""
    fotos = sorted(items("foto"), key=lambda x: (int(x.get("usos") or 0), float(x.get("ultimo_uso") or 0)))
    return fotos[:max(0, n)]


def elegir_video(dias_descanso: int = 14) -> dict | None:
    """Un video que no se haya usado en `dias_descanso` días (el menos usado primero)."""
    limite = time.time() - dias_descanso * 86400
    vids = [v for v in items("video") if float(v.get("ultimo_uso") or 0) < limite]
    vids.sort(key=lambda x: (int(x.get("usos") or 0), float(x.get("ultimo_uso") or 0)))
    return vids[0] if vids else None


def descargar_a_temporal(iid: str) -> str:
    """Copia local del archivo de Storage (para pulir un video). Ruta temporal."""
    x = item(iid)
    if not x:
        raise RuntimeError("El elemento ya no está en la biblioteca.")
    ext = "mp4" if x.get("tipo") == "video" else "jpg"
    ruta = os.path.join(tempfile.gettempdir(), f"pcg_bib_{iid}.{ext}")
    if os.path.exists(ruta) and os.path.getsize(ruta) > 0:
        return ruta
    req = urllib.request.Request(x["url"], headers={"User-Agent": "Pichangol-Torre/1.0"})
    with urllib.request.urlopen(req, timeout=300) as r, open(ruta, "wb") as f:
        while True:
            trozo = r.read(1024 * 1024)
            if not trozo:
                break
            f.write(trozo)
    return ruta
