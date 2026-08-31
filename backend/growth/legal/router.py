"""Páginas legales exigidas por Meta (y por buenas prácticas / Ley 29733):

- GET  /legal/privacidad            → Política de privacidad (pública).
- GET  /legal/eliminar-cuenta       → Eliminación de CUENTA (la exige Google Play
                                      para toda app con registro de usuarios).
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
VIGENCIA = "29 de agosto de 2026"

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
    <p>En <b>Pichangol</b> (Grupo EBIM SAC) tratamos tus datos conforme a la
    <b>Ley N.° 29733</b> de Protección de Datos Personales del Perú y su
    reglamento. Esta política explica <b>qué recogemos, para qué, con quién se
    comparte y cómo lo borras</b>.</p>

    <h2>1. Responsable</h2>
    <p><b>Grupo EBIM SAC</b> (Lima, Perú), responsable del tratamiento.
    Contacto para privacidad: <a href="mailto:{CONTACTO}">{CONTACTO}</a>.</p>

    <h2>2. Qué datos tratamos</h2>
    <ul>
      <li><b>Cuenta:</b> nombre, correo y foto de tu cuenta de Google al iniciar
      sesión. Opcionalmente celular y una foto de perfil que tú elijas.</li>
      <li><b>Ubicación:</b> tu ubicación aproximada para mostrarte canchas
      cercanas. En dos casos usamos ubicación precisa y sólo en ese momento:
      cuando reclamas ser dueño de una cancha (anti-fraude) y cuando pides a la
      bodega del local. <b>No hacemos seguimiento en segundo plano.</b></li>
      <li><b>Reservas y pagos:</b> qué cancha, día y hora reservaste, el importe
      y el medio de pago. Los <b>datos de tu tarjeta los procesa Culqi</b>
      (pasarela autorizada): Pichangol <b>nunca</b> ve ni guarda el número
      completo de tu tarjeta.</li>
      <li><b>Contenido que subes:</b> fotos de tus canchas o productos, fotos y
      videos de estados, publicaciones de canales, y las fotos, audios o archivos
      que envías por chat.</li>
      <li><b>Mensajes:</b> el contenido de tus conversaciones dentro de la app,
      necesario para entregarlo a tu destinatario.</li>
      <li><b>Verificación de identidad (opcional):</b> si decides verificarte,
      tu número de documento. En Perú lo validamos contra el registro oficial y
      <b>no guardamos la foto del documento</b>. Si en tu país la validación
      requiere imagen, esa imagen se guarda en un espacio privado y se elimina
      cuando dejas de necesitarla o cuando borras tus datos.</li>
      <li><b>Notificaciones:</b> un identificador del dispositivo para enviarte
      avisos (reserva confirmada, pedido listo). No identifica a la persona.</li>
      <li><b>Entrenador virtual (opcional):</b> el video corto de tu golpe. Se
      analiza y <b>el video se borra automáticamente</b> apenas se genera tu
      informe; sólo queda el texto del análisis.</li>
      <li><b>Redes sociales (opcional, sólo dueños):</b> si conectas Instagram o
      Facebook, un token de acceso cifrado y el identificador de tu página. No
      pedimos ni guardamos tu contraseña.</li>
    </ul>

    <h2>3. Para qué los usamos</h2>
    <ul>
      <li>Crear tu cuenta y mostrarte canchas cerca de ti.</li>
      <li>Gestionar reservas, cobros, comisiones y liquidaciones a los dueños.</li>
      <li>Permitir la comunicación entre jugador y cancha.</li>
      <li>Prevenir fraude (que quien reclama una cancha esté realmente en ella).</li>
      <li>Enviarte avisos sobre TUS reservas y pedidos.</li>
      <li>Cumplir obligaciones contables y legales.</li>
    </ul>
    <div class="box"><b>No vendemos tus datos</b> ni los cedemos a terceros para
    publicidad.</div>

    <h2>4. Con quién se comparten</h2>
    <ul>
      <li><b>El dueño de la cancha que reservas:</b> tu nombre, tu contacto y los
      datos de esa reserva. Es indispensable para que te atienda.</li>
      <li><b>Culqi</b> (Perú): procesamiento de pagos con tarjeta y Yape.</li>
      <li><b>Google</b>: inicio de sesión, mapas y envío de notificaciones.</li>
      <li><b>Supabase y Railway</b>: alojamiento de la base de datos y del
      servicio.</li>
      <li><b>Anthropic</b>: sólo si usas el entrenador virtual, para analizar los
      fotogramas de tu video. No se usan para entrenar modelos.</li>
      <li><b>Meta</b>: sólo si un dueño activa la publicación en sus redes.</li>
      <li><b>Autoridades</b>, cuando la ley lo exija.</li>
    </ul>
    <p><b>Transferencia internacional:</b> algunos de estos proveedores procesan
    la información en servidores fuera del Perú. Al usar Pichangol aceptas esa
    transferencia, que se realiza con proveedores que ofrecen niveles adecuados
    de protección.</p>

    <h2>5. Cuánto tiempo los conservamos</h2>
    <ul>
      <li>Mientras tu cuenta esté activa.</li>
      <li>Los <b>estados</b> duran 24 horas y su foto o video se borra solo.</li>
      <li>Los <b>videos del entrenador</b> se borran apenas se genera el informe.</li>
      <li>Al eliminar una cancha, un producto o una publicación, sus imágenes se
      borran del almacenamiento.</li>
      <li>Los <b>registros de pagos</b> se conservan el plazo que exigen las
      normas contables y tributarias, aunque cierres tu cuenta.</li>
    </ul>

    <h2>6. Menores de edad</h2>
    <p>Pichangol está dirigido a mayores de edad. Un padre, madre o apoderado
    puede matricular a un menor en una academia; en ese caso trata esos datos
    bajo su responsabilidad y con su consentimiento.</p>

    <h2>7. Seguridad</h2>
    <p>Ciframos las comunicaciones, restringimos el acceso a la información y los
    documentos de identidad se guardan en un espacio privado, no público. Ningún
    sistema es infalible: si ocurriera un incidente que te afecte, te lo
    comunicaremos.</p>

    <h2>8. Tus derechos (ARCO — Ley 29733)</h2>
    <p>Puedes pedir <b>acceso, rectificación, cancelación u oposición</b> al
    tratamiento de tus datos escribiendo a
    <a href="mailto:{CONTACTO}">{CONTACTO}</a>. Responderemos en los plazos que
    fija la ley. También puedes reclamar ante la Autoridad Nacional de Protección
    de Datos Personales del Perú.</p>

    <h2>9. Eliminar tu cuenta</h2>
    <p>Puedes pedir la eliminación de tu cuenta y tus datos en cualquier momento:
    <a href="/legal/eliminar-cuenta">cómo eliminar tu cuenta</a>.</p>

    <h2>10. Cambios</h2>
    <p>Si actualizamos esta política publicaremos la nueva versión en esta misma
    dirección, con su fecha de vigencia.</p>
    """
    return _doc("Política de privacidad", cuerpo)


@router.get("/legal/eliminar-cuenta", response_class=HTMLResponse)
def eliminar_cuenta() -> str:
    """Página de ELIMINACIÓN DE CUENTA que exige Google Play para toda app con
    registro de usuarios. Debe ser pública y accesible sin instalar la app."""
    cuerpo = f"""
    <p>Puedes pedir la eliminación de tu cuenta de <b>Pichangol</b> y de los
    datos asociados en cualquier momento. No necesitas tener la app instalada.</p>

    <h2>Cómo solicitarla</h2>
    <ol>
      <li>Escribe a <a href="mailto:{CONTACTO}?subject=Eliminar%20mi%20cuenta%20Pichangol">{CONTACTO}</a>
      desde <b>el mismo correo con el que ingresas</b> a Pichangol, con el asunto
      «Eliminar mi cuenta».</li>
      <li>Verificamos que la solicitud venga de tu cuenta y la procesamos.</li>
      <li>Te confirmamos por correo cuando esté hecha.</li>
    </ol>
    <p><b>Plazo:</b> hasta <b>30 días calendario</b> desde tu solicitud;
    normalmente mucho antes.</p>

    <h2>Qué se elimina</h2>
    <ul>
      <li>Tu perfil: nombre, correo, celular y foto.</li>
      <li>Tus reservas y tu historial de actividad.</li>
      <li>Tus mensajes, estados y publicaciones.</li>
      <li>Las fotos y videos que subiste, incluidos los de verificación de
      identidad.</li>
      <li>Tus canchas o productos publicados, si eres dueño.</li>
      <li>Tus tokens de notificaciones y de redes sociales conectadas.</li>
    </ul>

    <h2>Qué se conserva, y por qué</h2>
    <ul>
      <li><b>Comprobantes de pagos y liquidaciones:</b> las normas contables y
      tributarias del Perú obligan a conservarlos por el plazo legal, aun después
      de cerrar la cuenta. Se guardan disociados de tu perfil siempre que sea
      posible.</li>
      <li><b>Mensajes que enviaste a otra persona:</b> permanecen en la
      conversación de quien los recibió, igual que en cualquier app de mensajería.</li>
      <li><b>Publicaciones ya hechas en tus propias redes sociales:</b> son tuyas
      y viven en tu cuenta; puedes borrarlas desde ahí.</li>
    </ul>

    <div class="box">Eliminar tu cuenta es <b>irreversible</b>. Si eres dueño de
    una cancha con reservas futuras, avísanos para coordinar su cancelación y no
    dejar a jugadores sin su hora.</div>

    <p class="mut">¿Sólo quieres desconectar tus redes sociales, sin borrar la
    cuenta? Mira <a href="/legal/eliminacion-datos">eliminación de datos de redes</a>.</p>
    """
    return _doc("Eliminar tu cuenta", cuerpo)


@router.get("/legal/terminos", response_class=HTMLResponse)
def terminos() -> str:
    cuerpo = f"""
    <p>Estos Términos y Condiciones regulan el uso de <b>Pichangol</b>, plataforma
    operada por <b>Grupo EBIM SAC</b> (Lima, Perú). Al crear una cuenta o usar la
    app aceptas estos términos.</p>

    <h2>1. Qué es Pichangol</h2>
    <p>Pichangol es un <b>marketplace</b> para descubrir y reservar canchas
    deportivas, gestionar academias y publicar contenido. Facilitamos la conexión
    entre jugadores, dueños de canchas y academias; el servicio deportivo lo presta
    el establecimiento, no Pichangol.</p>

    <h2>2. Cuenta y elegibilidad</h2>
    <ul>
      <li>Ingresas con tu cuenta de Google; eres responsable del uso de tu cuenta.</li>
      <li>Debes brindar información veraz. Para publicar o vender puede exigirse una
      <b>verificación</b> de identidad o de propiedad de la cancha.</li>
    </ul>

    <h2>3. Reservas y pagos</h2>
    <ul>
      <li>Al reservar puedes pagar una <b>seña</b> o el total según configure el
      establecimiento. Los pagos se procesan mediante pasarelas de terceros.</li>
      <li>Pichangol puede cobrar una <b>comisión</b> por las operaciones realizadas
      en la plataforma (reservas y ventas del marketplace), informada al momento de
      la operación.</li>
      <li>Las políticas de cancelación y reembolso dependen de cada establecimiento.</li>
    </ul>

    <h2>4. Contenido que publicas</h2>
    <p>Eres dueño del contenido que subes (fotos, textos, productos, publicaciones de
    tu canal). Nos otorgas una licencia limitada para mostrarlo dentro de la
    plataforma y, si activas <b>"Gestión de redes"</b>, para publicarlo en tus redes
    en tu nombre. Eres responsable de tener los derechos sobre lo que publicas.</p>

    <h2>5. Contenido generado con IA</h2>
    <p>El servicio de <b>community manager con IA</b> genera borradores de posts como
    sugerencia. <b>Tú los revisas, editas y apruebas</b> antes de publicar; eres
    responsable del contenido final que difundes.</p>

    <h2>6. Uso permitido</h2>
    <p>No puedes usar Pichangol para fines ilícitos, publicar contenido falso,
    ofensivo o que infrinja derechos de terceros, ni intentar vulnerar la seguridad
    de la plataforma. Podemos suspender cuentas que incumplan estos términos.</p>

    <h2>7. Responsabilidad</h2>
    <p>Pichangol se ofrece "tal cual". No garantizamos la disponibilidad de las
    canchas ni el resultado de los servicios de terceros. En lo permitido por la ley,
    nuestra responsabilidad se limita a los montos efectivamente cobrados como
    comisión por la operación involucrada.</p>

    <h2>8. Privacidad</h2>
    <p>El tratamiento de tus datos se rige por nuestra
    <a href="/legal/privacidad">Política de privacidad</a>, conforme a la
    <b>Ley N.° 29733</b>.</p>

    <h2>9. Cambios y ley aplicable</h2>
    <p>Podemos actualizar estos términos publicando la nueva versión en esta misma
    dirección. Se rigen por las leyes de la <b>República del Perú</b> y cualquier
    controversia se somete a los jueces de <b>Lima</b>.</p>

    <h2>10. Contacto</h2>
    <p>Escríbenos a <a href="mailto:{CONTACTO}">{CONTACTO}</a>.</p>
    """
    return _doc("Términos y Condiciones", cuerpo)


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
