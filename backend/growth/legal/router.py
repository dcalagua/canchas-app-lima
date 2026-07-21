"""Páginas legales exigidas por Meta (y por buenas prácticas / Ley 29733):

- GET  /legal/privacidad            → Política de privacidad (pública).
- GET  /legal/eliminacion-datos     → Instrucciones de eliminación de datos.
- POST /legal/eliminacion-datos     → Data Deletion Callback de Meta: verifica la
                                      firma (signed_request con el App Secret) y
                                      BORRA de verdad las conexiones del usuario.
- GET  /legal/eliminacion-datos/estado → Página de estado de la solicitud.

Estas URLs se cargan en la app de Meta (Configuración → Básica): "URL de la
política de privacidad" y "Devolución de llamada de eliminación de datos".
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import urllib.parse

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

import config
from db.store import stores
from marketing import redes as redes_svc

router = APIRouter(tags=["legal"])

CONTACTO = "dcalagua@ebim.pe"
VIGENCIA = "21 de julio de 2026"

_ESTILO = """
<style>
 :root{--verde:#14463A;--lima:#128C7E;--tinte:#E3F2EF;--tx:#222;--mut:#666}
 *{box-sizing:border-box}
 body{margin:0;font-family:system-ui,Segoe UI,Roboto,-apple-system,sans-serif;
   color:var(--tx);line-height:1.6;background:#F7F9F7}
 .wrap{max-width:760px;margin:0 auto;padding:28px 20px 60px}
 header{background:var(--verde);color:#fff;padding:26px 20px;border-radius:0 0 18px 18px}
 header .wrap{padding:0 20px}
 h1{margin:0;font-size:24px}
 .sub{color:#AEEA94;font-size:14px;margin-top:4px}
 h2{color:var(--verde);font-size:18px;margin:26px 0 8px}
 p,li{font-size:15px}
 a{color:var(--lima)}
 .box{background:var(--tinte);border-radius:12px;padding:14px 16px;margin:16px 0}
 .mut{color:var(--mut);font-size:13px}
 ol li,ul li{margin:6px 0}
 footer{margin-top:34px;border-top:1px solid #e3e3e3;padding-top:14px}
</style>
"""


def _doc(titulo: str, cuerpo: str) -> str:
    return (
        "<!doctype html><html lang='es'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{titulo} · Pichangol</title>{_ESTILO}</head><body>"
        f"<header><div class='wrap'><h1>{titulo}</h1>"
        "<div class='sub'>Pichangol · un producto de Grupo EBIM SAC</div></div></header>"
        f"<div class='wrap'>{cuerpo}"
        "<footer><p class='mut'>Pichangol es un producto de <b>Grupo EBIM SAC</b> "
        f"(Lima, Perú). Contacto: <a href='mailto:{CONTACTO}'>{CONTACTO}</a>.</p>"
        f"<p class='mut'>Vigente desde el {VIGENCIA}.</p></footer>"
        "</div></body></html>")


@router.get("/legal/privacidad", response_class=HTMLResponse)
def privacidad() -> str:
    cuerpo = f"""
    <p>En <b>Pichangol</b> (Grupo EBIM SAC) respetamos tu privacidad y cumplimos la
    <b>Ley N.° 29733</b> de Protección de Datos Personales del Perú y las políticas
    de la plataforma de Meta. Esta política explica qué datos tratamos y para qué.</p>

    <h2>1. Quién es el responsable</h2>
    <p>Grupo EBIM SAC, responsable del tratamiento. Contacto para privacidad:
    <a href="mailto:{CONTACTO}">{CONTACTO}</a>.</p>

    <h2>2. Qué datos tratamos</h2>
    <ul>
      <li><b>De tu cuenta:</b> nombre y correo con el que ingresas a Pichangol.</li>
      <li><b>De tu academia/cancha:</b> nombre, sede, fotos que subes, tarifario y
      datos de contacto, para mostrar tu ficha, tu landing y generar contenido.</li>
      <li><b>Servicio "Gestión de redes" (opcional):</b> si conectas tu Instagram o
      Facebook, guardamos un <b>token de acceso</b> (cifrado), y el identificador y
      nombre de tu Página de Facebook y tu cuenta de Instagram profesional. Lo usamos
      <b>únicamente</b> para publicar el contenido que apruebas, en tu nombre.</li>
    </ul>
    <div class="box">No pedimos ni guardamos tu contraseña de Facebook/Instagram.
    El permiso lo otorgas tú a través de Meta y puedes revocarlo cuando quieras.</div>

    <h2>3. Para qué los usamos</h2>
    <ul>
      <li>Operar la plataforma (reservas, academias, pagos).</li>
      <li>Prestar los servicios que contratas (landing, generación de posts, y
      publicación en tus redes si activas "Gestión de redes").</li>
    </ul>

    <h2>4. Con quién se comparten</h2>
    <p>Solo con lo necesario para el servicio: <b>Meta</b> (para publicar en tus
    redes cuando tú lo apruebas) y proveedores de infraestructura que alojan la
    plataforma. <b>No vendemos</b> tus datos ni los usamos para fines ajenos.</p>

    <h2>5. Cuánto los conservamos</h2>
    <p>Mientras tu cuenta o tu servicio estén activos. Si <b>desconectas</b> tus
    redes (desde la app o desde Facebook) eliminamos el token de acceso asociado.</p>

    <h2>6. Tus derechos (ARCO — Ley 29733)</h2>
    <p>Puedes solicitar acceso, rectificación, cancelación u oposición al
    tratamiento de tus datos escribiendo a <a href="mailto:{CONTACTO}">{CONTACTO}</a>.</p>

    <h2>7. Cómo revocar el acceso a tus redes</h2>
    <ol>
      <li>En la app: <b>Servicios → Gestión de redes → Desconectar</b>.</li>
      <li>O en Facebook: <b>Configuración → Apps y sitios web</b> → quitar
      "Pichangol".</li>
      <li>O escríbenos a <a href="mailto:{CONTACTO}">{CONTACTO}</a>.</li>
    </ol>
    <p>Ver también: <a href="/legal/eliminacion-datos">Eliminación de datos</a>.</p>

    <h2>8. Cambios</h2>
    <p>Si actualizamos esta política, publicaremos la nueva versión en esta misma
    dirección con su fecha de vigencia.</p>
    """
    return _doc("Política de privacidad", cuerpo)


@router.get("/legal/eliminacion-datos", response_class=HTMLResponse)
def eliminacion_datos() -> str:
    cuerpo = f"""
    <p>Puedes eliminar los datos que Pichangol guarda de tus redes sociales en
    cualquier momento, por cualquiera de estas vías:</p>
    <ol>
      <li><b>Desde la app Pichangol:</b> entra a <b>Servicios → Gestión de redes →
      Desconectar</b>. Al desconectar, eliminamos el token de acceso y la conexión
      de tus redes.</li>
      <li><b>Desde Facebook:</b> <b>Configuración → Apps y sitios web</b>, ubica
      "Pichangol" y elimínala. Meta nos notifica y borramos tus datos asociados.</li>
      <li><b>Por correo:</b> escríbenos a <a href="mailto:{CONTACTO}">{CONTACTO}</a>
      pidiendo la eliminación; la procesamos y te confirmamos.</li>
    </ol>
    <div class="box">Al eliminar, se borra el <b>token de acceso</b> y los
    identificadores de tu Página/Instagram que teníamos guardados para publicar en
    tu nombre. Las publicaciones que ya se hicieron en tus redes permanecen en tus
    redes (son tuyas); puedes borrarlas desde tu propia cuenta.</div>
    <p class="mut">Esta página también funciona como destino del proceso automático
    de eliminación de datos de Meta.</p>
    """
    return _doc("Eliminación de datos", cuerpo)


def _b64url_decode(s: str) -> bytes:
    s = s + "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s.encode())


def _parse_signed_request(signed_request: str, secret: str) -> dict | None:
    """Verifica y decodifica el signed_request de Meta (HMAC-SHA256 con el App
    Secret). Devuelve el payload o None si la firma no valida."""
    if not signed_request or "." not in signed_request or not secret:
        return None
    sig_enc, payload_enc = signed_request.split(".", 1)
    try:
        sig = _b64url_decode(sig_enc)
    except Exception:  # noqa: BLE001
        return None
    expected = hmac.new(secret.encode(), payload_enc.encode(), hashlib.sha256).digest()
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        return json.loads(_b64url_decode(payload_enc))
    except Exception:  # noqa: BLE001
        return None


async def _leer_signed_request(request: Request) -> str:
    """Extrae signed_request del body (form-urlencoded o JSON), sin depender de
    python-multipart."""
    try:
        raw = (await request.body()).decode("utf-8", "ignore")
    except Exception:  # noqa: BLE001
        return ""
    if not raw:
        return ""
    # form-urlencoded (lo típico de Meta).
    if "signed_request=" in raw:
        vals = urllib.parse.parse_qs(raw).get("signed_request")
        if vals:
            return vals[0]
    # JSON, por si acaso.
    try:
        return str((json.loads(raw) or {}).get("signed_request", ""))
    except Exception:  # noqa: BLE001
        return ""


@router.post("/legal/eliminacion-datos")
async def data_deletion_callback(request: Request) -> JSONResponse:
    """Data Deletion Callback de Meta: llega cuando un usuario elimina la app.
    Verifica la firma, borra las conexiones de ese usuario y devuelve la URL de
    estado + un código de confirmación (formato que Meta exige)."""
    signed_request = await _leer_signed_request(request)
    data = _parse_signed_request(signed_request, config.META_APP_SECRET)
    user_id = (data or {}).get("user_id", "") if data else ""
    borrados = redes_svc.borrar_por_meta_user(user_id) if user_id else 0
    # Código de confirmación (identificador de la solicitud).
    code = f"del_{stores.next_id('eliminacion')}"
    stores.eliminaciones.append({"code": code, "user_id": user_id,
                                 "borrados": borrados})
    base = (config.PUBLIC_BASE_URL or str(request.base_url).rstrip("/")).rstrip("/")
    return JSONResponse({"url": f"{base}/legal/eliminacion-datos/estado?code={code}",
                         "confirmation_code": code})


@router.get("/legal/eliminacion-datos/estado", response_class=HTMLResponse)
def estado_eliminacion(code: str = "") -> str:
    cuerpo = f"""
    <p>Tu solicitud de eliminación de datos fue <b>recibida y procesada</b>.</p>
    <div class="box">Código de confirmación: <b>{code or '(sin código)'}</b></div>
    <p>Eliminamos el token de acceso y los datos de conexión de tus redes que
    teníamos guardados. Si tienes dudas, escríbenos a
    <a href="mailto:{CONTACTO}">{CONTACTO}</a>.</p>
    """
    return _doc("Estado de eliminación de datos", cuerpo)
