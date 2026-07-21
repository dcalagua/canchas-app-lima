"""Gestión de redes (Nivel 2): Pichangol publica DIRECTAMENTE en el
Instagram/Facebook del dueño, con su PERMISO (OAuth de Meta, revocable).

Dos modos (config.META_MODO / config.meta_modo()):
- **sandbox**: sin App Review de Meta. SIMULA la conexión y la publicación para
  poder probar TODO el flujo del APK end-to-end (conectar → estado → publicar)
  en dev/QAS. No toca ninguna red social real.
- **produccion**: OAuth y publicación REALES contra Graph API. Requiere que Meta
  haya aprobado los permisos (App Review) y que estén cargadas las credenciales
  (META_APP_ID/SECRET/REDIRECT_URI) como secrets de Railway.

El token de acceso del dueño se guarda CIFRADO (Fernet si hay META_TOKEN_KEY;
si no, ofuscado) y NUNCA se expone en ninguna respuesta (siempre enmascarado).

Todo es fail-safe: ninguna función lanza; ante error devuelve {ok: False,...}.
"""

from __future__ import annotations

import base64
import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone

import config
from db.store import stores

# Permisos que Pichangol le pide al dueño (lo que Meta debe aprobar en App
# Review). Acotados a publicar en su Página y su Instagram profesional.
SCOPES = (
    "pages_show_list,pages_manage_posts,pages_read_engagement,"
    "instagram_basic,instagram_content_publish,business_management"
)


def modo() -> str:
    return config.meta_modo()


# --- cifrado en reposo del token (fail-safe) --------------------------------
def _fernet():
    if not config.META_TOKEN_KEY:
        return None
    try:
        from cryptography.fernet import Fernet
        return Fernet(config.META_TOKEN_KEY.encode())
    except Exception:  # noqa: BLE001 — sin lib/clave inválida → sin Fernet
        return None


def cifrar(token: str) -> str:
    """Cifra el token para guardarlo. Prefijo 'f:' = Fernet, 'b:' = base64
    (ofuscación, cuando no hay clave). Nunca lanza."""
    if not token:
        return ""
    f = _fernet()
    if f is not None:
        try:
            return "f:" + f.encrypt(token.encode()).decode()
        except Exception:  # noqa: BLE001
            pass
    return "b:" + base64.urlsafe_b64encode(token.encode()).decode()


def descifrar(enc: str) -> str:
    """Recupera el token en claro (solo uso interno; jamás se devuelve al APK)."""
    if not enc:
        return ""
    try:
        if enc.startswith("f:"):
            f = _fernet()
            return f.decrypt(enc[2:].encode()).decode() if f is not None else ""
        if enc.startswith("b:"):
            return base64.urlsafe_b64decode(enc[2:].encode()).decode()
    except Exception:  # noqa: BLE001
        return ""
    return ""


# --- llamadas a Graph API (urllib, como el resto del backend) ---------------
def _graph(path: str, params: dict | None = None, *, post: bool = False) -> dict:
    """Llama a Graph API. Devuelve {ok, data} o {ok:False, error}. Nunca lanza."""
    base = f"{config.META_GRAPH_BASE}/{config.META_GRAPH_VERSION}"
    url = f"{base}/{path.lstrip('/')}"
    body = None
    method = "GET"
    if post:
        method = "POST"
        body = urllib.parse.urlencode(params or {}).encode()
    elif params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, data=body, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if isinstance(data, dict) and data.get("error"):
            return {"ok": False, "error": str(data["error"].get("message"))[:200]}
        return {"ok": True, "data": data}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:200]}


# --- estado / enmascarado ----------------------------------------------------
def _publico(conx: dict | None) -> dict:
    """Vista pública de la conexión (SIN token)."""
    if not conx:
        return {"conectado": False, "estado": "desconectado", "modo": modo()}
    estado = conx.get("estado", "desconectado")
    return {
        "conectado": estado == "conectado",
        "estado": estado,
        "plataforma": conx.get("plataforma", "meta"),
        "ig_username": conx.get("ig_username"),
        "page_nombre": conx.get("page_nombre"),
        "conectado_en": conx.get("conectado_en"),
        "publicaciones": int(conx.get("publicaciones", 0)),
        "modo": conx.get("modo", modo()),
    }


def estado(academia_id: str) -> dict:
    return _publico(stores.conexiones_redes.get(academia_id))


def login_url(academia_id: str) -> str:
    """URL del diálogo OAuth de Meta que el dueño abre para dar permiso.

    Si hay META_LOGIN_CONFIG_ID (Facebook Login for Business), el diálogo usa esa
    configuración y los permisos se definen en el panel de Meta (no por scope).
    Si no, cae al Facebook Login clásico (permisos por scope)."""
    params = {
        "client_id": config.META_APP_ID,
        "redirect_uri": config.META_REDIRECT_URI,
        "state": academia_id,
        "response_type": "code",
    }
    if config.META_LOGIN_CONFIG_ID:
        params["config_id"] = config.META_LOGIN_CONFIG_ID
    else:
        params["scope"] = SCOPES
    return (f"https://www.facebook.com/{config.META_GRAPH_VERSION}"
            f"/dialog/oauth?{urllib.parse.urlencode(params)}")


def _guardar(academia_id: str, **campos) -> dict:
    conx = stores.conexiones_redes.get(academia_id, {})
    conx.update({"academia_id": academia_id, "plataforma": "meta", **campos})
    stores.conexiones_redes[academia_id] = conx
    return conx


# --- conectar ----------------------------------------------------------------
def conectar(academia_id: str, dueno_id: str = "") -> dict:
    """Inicia la conexión. En produccion devuelve la URL de permiso (el APK la
    abre en el navegador). En sandbox SIMULA la conexión al instante para probar
    el flujo. Nunca lanza."""
    if not academia_id:
        return {"ok": False, "error": "academia_id_requerido"}
    if modo() == "produccion":
        if not config.META_REDIRECT_URI:
            return {"ok": False, "error": "falta_redirect_uri"}
        return {"ok": True, "modo": "produccion", "login_url": login_url(academia_id)}
    # sandbox: conexión simulada (cuenta de prueba) para ejercitar el APK.
    conx = _guardar(
        academia_id, dueno_id=dueno_id, estado="conectado", modo="sandbox",
        ig_username="tu_academia_demo", page_nombre="Tu Academia (demo)",
        ig_user_id="SANDBOX_IG", page_id="SANDBOX_PAGE",
        token_enc=cifrar("SANDBOX_TOKEN"),
        conectado_en=datetime.now(timezone.utc).isoformat(),
        publicaciones=int(stores.conexiones_redes.get(academia_id, {})
                          .get("publicaciones", 0)))
    return {"ok": True, "modo": "sandbox", "conexion": _publico(conx)}


def procesar_callback(code: str, state: str) -> dict:
    """Callback de OAuth (Meta redirige aquí con ?code&state). Intercambia el
    código por un token de larga duración, ubica la Página y la cuenta de IG
    profesional y guarda la conexión. state = academia_id. Nunca lanza."""
    academia_id = (state or "").strip()
    if not code or not academia_id:
        return {"ok": False, "error": "callback_incompleto"}
    if modo() != "produccion":
        # En sandbox no debería llegar un callback real; conecta simulado.
        return conectar(academia_id)

    # 1) code → token corto
    r = _graph("oauth/access_token", {
        "client_id": config.META_APP_ID,
        "client_secret": config.META_APP_SECRET,
        "redirect_uri": config.META_REDIRECT_URI,
        "code": code,
    })
    if not r["ok"]:
        return {"ok": False, "error": r["error"]}
    token = (r["data"] or {}).get("access_token", "")
    # 2) token corto → token de larga duración
    rl = _graph("oauth/access_token", {
        "grant_type": "fb_exchange_token",
        "client_id": config.META_APP_ID,
        "client_secret": config.META_APP_SECRET,
        "fb_exchange_token": token,
    })
    if rl["ok"] and (rl["data"] or {}).get("access_token"):
        token = rl["data"]["access_token"]
    # 3) Página del dueño + su token de página
    rp = _graph("me/accounts", {"access_token": token, "fields":
                                "id,name,access_token,instagram_business_account"})
    paginas = ((rp.get("data") or {}).get("data") or []) if rp["ok"] else []
    if not paginas:
        _guardar(academia_id, estado="error", modo="produccion",
                 error="sin_pagina_o_ig")
        return {"ok": False, "error": "sin_pagina_facebook"}
    pg = paginas[0]
    page_token = pg.get("access_token", token)
    ig = (pg.get("instagram_business_account") or {}).get("id")
    ig_username = None
    if ig:
        ru = _graph(ig, {"access_token": page_token, "fields": "username"})
        if ru["ok"]:
            ig_username = (ru["data"] or {}).get("username")
    conx = _guardar(
        academia_id, estado="conectado", modo="produccion",
        page_id=pg.get("id"), page_nombre=pg.get("name"),
        ig_user_id=ig, ig_username=ig_username,
        token_enc=cifrar(page_token),
        conectado_en=datetime.now(timezone.utc).isoformat())
    return {"ok": True, "conexion": _publico(conx)}


def desconectar(academia_id: str) -> dict:
    """Revoca la conexión (deja de publicar). El dueño también puede revocar el
    permiso desde su propio Facebook."""
    stores.conexiones_redes.pop(academia_id, None)
    return {"ok": True, "conexion": _publico(None)}


# --- publicar ----------------------------------------------------------------
def publicar(academia_id: str, texto: str, imagen_url: str | None = None) -> dict:
    """Publica [texto] (+imagen opcional) en las redes conectadas del dueño.
    Facebook admite solo texto; Instagram EXIGE imagen (si no hay, se omite IG).
    En sandbox simula la publicación. Devuelve {ok, resultados:{facebook, instagram}}.
    """
    conx = stores.conexiones_redes.get(academia_id)
    if not conx or conx.get("estado") != "conectado":
        return {"ok": False, "error": "no_conectado"}
    texto = (texto or "").strip()
    if not texto:
        return {"ok": False, "error": "texto_vacio"}

    if conx.get("modo") == "sandbox" or modo() != "produccion":
        conx["publicaciones"] = int(conx.get("publicaciones", 0)) + 1
        return {"ok": True, "simulado": True, "resultados": {
            "facebook": {"ok": True, "post_id": "SANDBOX_FB_POST"},
            "instagram": {"ok": bool(imagen_url),
                          "post_id": "SANDBOX_IG_POST" if imagen_url else None,
                          "nota": None if imagen_url else "IG requiere imagen"},
        }}

    token = descifrar(conx.get("token_enc", ""))
    if not token:
        return {"ok": False, "error": "token_no_disponible"}
    resultados: dict = {}

    # Facebook: post en la Página (texto, +link/imagen si hay).
    page_id = conx.get("page_id")
    if page_id:
        params = {"message": texto, "access_token": token}
        if imagen_url:
            rf = _graph(f"{page_id}/photos",
                        {"url": imagen_url, "caption": texto,
                         "access_token": token}, post=True)
        else:
            rf = _graph(f"{page_id}/feed", params, post=True)
        resultados["facebook"] = ({"ok": True, "post_id": (rf["data"] or {}).get("id")}
                                  if rf["ok"] else {"ok": False, "error": rf["error"]})

    # Instagram: requiere imagen (contenedor + publish).
    ig = conx.get("ig_user_id")
    if ig and imagen_url:
        rc = _graph(f"{ig}/media",
                    {"image_url": imagen_url, "caption": texto,
                     "access_token": token}, post=True)
        if rc["ok"] and (rc["data"] or {}).get("id"):
            rp = _graph(f"{ig}/media_publish",
                        {"creation_id": rc["data"]["id"],
                         "access_token": token}, post=True)
            resultados["instagram"] = (
                {"ok": True, "post_id": (rp["data"] or {}).get("id")}
                if rp["ok"] else {"ok": False, "error": rp["error"]})
        else:
            resultados["instagram"] = {"ok": False,
                                       "error": rc.get("error", "media_error")}
    elif ig:
        resultados["instagram"] = {"ok": False, "nota": "IG requiere imagen"}

    conx["publicaciones"] = int(conx.get("publicaciones", 0)) + 1
    ok = any(v.get("ok") for v in resultados.values())
    return {"ok": ok, "resultados": resultados}
