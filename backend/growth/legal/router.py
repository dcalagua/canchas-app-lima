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

from datetime import datetime, timezone

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

import config
import empresa
from db.store import stores
from marketing import redes as redes_svc

router = APIRouter(tags=["legal"])



def _em() -> dict[str, str]:
    """Datos de la empresa configurados en la torre (`empresa.py`)."""
    return empresa.datos()


class _Contacto:
    """Correo de privacidad/legal VIGENTE: se lee en cada request para que un
    cambio en la torre salga al instante (antes era la constante CONTACTO)."""

    def __str__(self) -> str:
        return _em()["correo_privacidad"]

    def __format__(self, spec: str) -> str:
        return format(str(self), spec)


CONTACTO = _Contacto()
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
    em = _em()
    return (
        "<!doctype html><html lang='es'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{titulo} · Pichangol</title>{_ESTILO}</head><body>"
        f"<header><div class='wrap'><h1>{titulo}</h1>"
        f"<div class='sub'>Pichangol · un producto de {em['razon_social']}</div></div></header>"
        f"<div class='wrap'>{cuerpo}"
        f"<footer><p class='mut'>Pichangol es un producto de <b>{em['razon_social']}</b> "
        f"({em['doc_etiqueta']} {em['ruc']} · {em['direccion']}). Contacto: <a href='mailto:{CONTACTO}'>{CONTACTO}</a>.</p>"
        f"<p class='mut'>Vigente desde el {VIGENCIA}.</p></footer>"
        "</div></body></html>")


# La HOME de marca (`home.html`, junto a este archivo) ya no se sirve entera:
# la raíz del dominio es el explorador tipo Airbnb (`web/router.py::_explorar`)
# y `web/marca.py` extrae de este archivo las secciones de comercio (servicios
# y precios, términos, cancelaciones, contacto y Libro de Reclamaciones) para
# ponerlas debajo de las canchas. Editar el texto legal = editar home.html.


class ReclamacionReq(BaseModel):
    """Hoja de reclamación (campos del D.S. 011-2011-PCM)."""
    c_nombre: str
    c_doc: str
    c_tel: str = ""
    c_email: str
    c_dir: str = ""
    c_menor: str = "No"
    c_apoderado: str = ""   # padre/madre/tutor cuando el consumidor es menor de edad
    b_tipo: str = "Servicio"
    b_monto: str = ""
    b_desc: str = ""
    d_tipo: str = "Reclamo"
    d_detalle: str
    d_pedido: str


def _lim(v: str, n: int) -> str:
    return (v or "").strip()[:n]


@router.post("/reclamaciones")
def post_reclamacion(req: ReclamacionReq) -> dict:
    """LIBRO DE RECLAMACIONES integrado (lo exige INDECOPI y lo revisa Culqi
    al afiliar: no puede depender de correo ni formularios externos). Registra
    la hoja con número correlativo y fecha; el operador la atiende desde la
    torre (/admin → Cobros → Libro de Reclamaciones) en ≤ 15 días hábiles.
    Pública y sin login; el middleware persiste el snapshot (POST)."""
    nombre = _lim(req.c_nombre, 120)
    doc = _lim(req.c_doc, 20)
    email = _lim(req.c_email, 120).lower()
    detalle = _lim(req.d_detalle, 2000)
    pedido = _lim(req.d_pedido, 1000)
    if not nombre or not doc or "@" not in email or not detalle or not pedido:
        return {"ok": False, "error": "faltan_campos"}
    if len(stores.reclamaciones) >= 20000:  # tope defensivo
        return {"ok": False, "error": "libro_lleno"}
    ahora = datetime.now(timezone.utc)
    n = stores.next_id("reclamacion")
    numero = f"PICH-{ahora.strftime('%Y%m%d')}-{n:04d}"
    hoja = {
        "id": n, "numero": numero, "fecha": ahora.isoformat(),
        "estado": "pendiente", "respuesta": "", "respondida_en": "",
        "consumidor": {
            "nombre": nombre, "doc": doc, "tel": _lim(req.c_tel, 30),
            "email": email, "dir": _lim(req.c_dir, 200),
            "menor": _lim(req.c_menor, 3) or "No", "apoderado": _lim(req.c_apoderado, 120)},
        "bien": {
            "tipo": "Producto" if _lim(req.b_tipo, 12) == "Producto" else "Servicio",
            "monto": _lim(req.b_monto, 20), "desc": _lim(req.b_desc, 300)},
        "detalle": {
            "tipo": "Queja" if _lim(req.d_tipo, 10) == "Queja" else "Reclamo",
            "detalle": detalle, "pedido": pedido},
    }
    stores.reclamaciones.append(hoja)
    return {"ok": True, "numero": numero, "fecha": hoja["fecha"],
            "plazo": "15 días hábiles", "contacto": _em()["correo"]}


@router.get("/legal/privacidad", response_class=HTMLResponse)
def privacidad() -> str:
    cuerpo = f"""
    <p>En <b>Pichangol</b> ({_em()["razon_social"]}) tratamos tus datos conforme a la
    <b>Ley N.° 29733</b> de Protección de Datos Personales del Perú y su
    reglamento. Esta política explica <b>qué recogemos, para qué, con quién se
    comparte y cómo lo borras</b>.</p>

    <h2>1. Responsable</h2>
    <p><b>{_em()["razon_social"]}</b> ({_em()["doc_etiqueta"]} {_em()["ruc"]}, {_em()["direccion"]}), responsable del tratamiento.
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

    <h2>Cómo eliminarla</h2>
    <div class="box"><b>Desde la app (inmediato):</b> entra a
    <b>Perfil → Eliminar mi cuenta</b>, confirma, y se borra al momento.</div>
    <p><b>Si ya no tienes la app instalada</b>, escríbenos:</p>
    <ol>
      <li>Envía un correo a <a href="mailto:{CONTACTO}?subject=Eliminar%20mi%20cuenta%20Pichangol">{CONTACTO}</a>
      desde <b>el mismo correo con el que ingresas</b> a Pichangol, con el asunto
      «Eliminar mi cuenta».</li>
      <li>Verificamos que la solicitud venga de tu cuenta y la procesamos.</li>
      <li>Te confirmamos por correo cuando esté hecha.</li>
    </ol>
    <p><b>Plazo por esta vía:</b> hasta <b>30 días calendario</b> desde tu
    solicitud; normalmente mucho antes.</p>

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
    operada por <b>{_em()["razon_social"]}</b> ({_em()["doc_etiqueta"]} {_em()["ruc"]}, {_em()["direccion"]}). Al crear una cuenta o usar la
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
      <li>Las cancelaciones y devoluciones se rigen por nuestra
      <a href="/legal/devoluciones">Política de cambios, cancelaciones y devoluciones</a>.</li>
    </ul>

    <h2>3-bis. Compras en la web (pichangol.app)</h2>
    <ul>
      <li>Desde la web puedes <b>reservar canchas</b> y <b>matricularte en academias</b>
      con tu cuenta de Google. El <b>precio</b>, la moneda, los extras y el total se
      muestran antes de confirmar; no hay cargos ocultos.</li>
      <li>El pago en línea se procesa con <b>Culqi</b> (tarjetas Visa/Mastercard y
      Yape) en un formulario seguro (HTTPS). Pichangol no almacena los datos de tu
      tarjeta.</li>
      <li>Al pagar recibes un <b>comprobante en pantalla</b> con el número de
      operación y la reserva o matrícula queda registrada a nombre de tu correo;
      la ves también en la app ("Mis reservas").</li>
      <li>Una reserva confirma el uso de la cancha en la fecha y hora elegidas; una
      matrícula confirma tu plaza en el programa y la frecuencia elegidos. El
      servicio deportivo lo presta el establecimiento o la academia.</li>
      <li>Reclamos y quejas: <a href="/libro-de-reclamaciones">Libro de
      Reclamaciones</a> (respuesta en un máximo de 15 días hábiles).</li>
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


@router.get("/legal/devoluciones", response_class=HTMLResponse)
def devoluciones() -> str:
    """Política de CAMBIOS, CANCELACIONES y DEVOLUCIONES en página propia
    (Culqi la exige publicada y con la razón social explícita)."""
    em = _em()
    horas = int(getattr(config, "WEB_CANCELACION_HORAS", 6) or 6)
    cuerpo = f"""
    <p>Esta política es aplicada por <b>{em["razon_social"]}</b> ({em["doc_etiqueta"]}
    {em["ruc"]}, {em["direccion"]}), operadora de la plataforma <b>Pichangol</b>
    (web <b>pichangol.app</b> y app), a todas las compras realizadas en ella.</p>

    <h2>1. Reservas de canchas</h2>
    <ul>
      <li><b>Cancelación por el jugador con {horas} horas o más de anticipación</b> al inicio
      del turno: devolución del <b>100 %</b> de lo pagado en línea.</li>
      <li><b>Con menos de {horas} horas</b>: la reserva no es reembolsable, porque el
      horario quedó bloqueado para ti y el establecimiento reservó el espacio.</li>
      <li><b>Cambio de fecha u hora</b>: con {horas} horas o más de anticipación puedes cancelar
      sin costo y reservar de nuevo el horario que prefieras, sujeto a disponibilidad.</li>
      <li><b>Cancelación por el establecimiento</b> (clima, fuerza mayor u otro motivo):
      tienes derecho a <b>reprogramar sin costo</b> o a la <b>devolución del 100 %</b>.</li>
      <li>Las reservas que se pagan en la cancha no generan cobro en línea ni devolución.</li>
    </ul>

    <h2>2. Matrículas en academias</h2>
    <ul>
      <li><b>Antes de la primera clase</b>: devolución del <b>100 %</b> del monto pagado.</li>
      <li><b>Con clases iniciadas</b>: el mes en curso no es reembolsable; los meses pagados
      por adelantado que aún no empezaron se devuelven al <b>100 %</b>.</li>
      <li>Si la academia cancela el programa, se devuelve íntegramente lo no utilizado.</li>
    </ul>

    <h2>3. Productos del marketplace (app)</h2>
    <p>Puedes solicitar el <b>cambio o la devolución</b> de un producto dentro de los
    <b>7 días calendario</b> siguientes a la entrega si llegó dañado, incompleto o distinto
    a lo ofrecido. La entrega la coordina el vendedor por el chat de la app; Pichangol
    media en la solicitud y, si corresponde, devuelve el pago.</p>

    <h2>4. Saldo Pichangol y suscripciones</h2>
    <p>Las recargas de saldo se usan dentro de la plataforma y solo se devuelven ante un
    cobro erróneo o duplicado. La suscripción <b>Pichangol Pro</b> puede cancelarse en
    cualquier momento y no se renueva; el período ya pagado no se prorratea.</p>

    <h2>5. Cómo pedir una devolución</h2>
    <ul>
      <li>Desde la web: <b>Mis reservas → Cancelar reserva</b> (la devolución se procesa
      automáticamente si cumple el plazo).</li>
      <li>Desde la app: <b>Mis reservas</b> o <b>Mi academia</b>.</li>
      <li>O escríbenos a <a href="mailto:{CONTACTO}">{CONTACTO}</a> o por WhatsApp
      ({em["whatsapp_bonito"] or "ver Contacto"}) indicando tu nombre, la fecha y hora de la
      compra y el motivo.</li>
    </ul>
    <p>Las devoluciones aprobadas se realizan por el <b>mismo medio de pago</b> (tarjeta
    o Yape, a través de Culqi) en un plazo de <b>hasta 7 días hábiles</b>, según los tiempos
    de la pasarela y del banco emisor. El monto devuelto es el efectivamente pagado.</p>

    <h2>6. Reclamos</h2>
    <p>Si no estás conforme, registra tu reclamo en nuestro
    <a href="/libro-de-reclamaciones">Libro de Reclamaciones</a>; respondemos en un
    máximo de 15 días hábiles. Esta política no limita los derechos que te reconoce el
    Código de Protección y Defensa del Consumidor (Ley N.° 29571).</p>
    """
    return _doc("Política de cambios, cancelaciones y devoluciones", cuerpo)


_LIBRO_JS = """
(function(){
  var form = document.getElementById('lr-form'); if(!form) return;
  var ok = document.getElementById('lr-ok'), err = document.getElementById('lr-err'), hoja = document.getElementById('lr-hoja');
  var menor = form.querySelectorAll('input[name=c_menor]'), apo = document.getElementById('apoBox');
  menor.forEach(function(r){ r.addEventListener('change', function(){ apo.style.display = form.c_menor.value === 'Sí' ? '' : 'none'; }); });
  function v(n){ var el = form.elements[n]; return el ? (el.value || '').trim() : ''; }
  function t(id, txt){ var el = document.getElementById(id); if(el) el.textContent = txt || '—'; }
  form.addEventListener('submit', function(ev){
    ev.preventDefault(); ok.style.display = 'none'; err.style.display = 'none';
    if(!form.checkValidity()){ form.reportValidity(); return; }
    var btn = form.querySelector('button[type=submit]'); btn.disabled = true; btn.textContent = 'Registrando…';
    var d = {}; ['c_nombre','c_doc','c_tel','c_email','c_dir','c_menor','c_apoderado','b_tipo','b_monto','b_desc','d_tipo','d_detalle','d_pedido'].forEach(function(k){ d[k] = v(k); });
    fetch('/reclamaciones', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(d)})
      .then(function(r){ return r.json(); })
      .then(function(j){
        if(!j || !j.ok){ err.style.display = ''; return; }
        var f = new Date(j.fecha); var fecha = f.toLocaleDateString('es-PE', {day:'2-digit', month:'long', year:'numeric'}) + ' ' + f.toLocaleTimeString('es-PE', {hour:'2-digit', minute:'2-digit'});
        t('h-num', j.numero); t('h-fecha', fecha); t('lr-num', j.numero);
        t('h-nombre', d.c_nombre); t('h-doc', d.c_doc); t('h-tel', d.c_tel); t('h-email', d.c_email); t('h-dir', d.c_dir);
        t('h-menor', d.c_menor === 'Sí' ? ('Sí · ' + (d.c_apoderado || 'padre/madre/tutor')) : 'No');
        t('h-btipo', d.b_tipo); t('h-monto', d.b_monto ? ('S/ ' + d.b_monto) : '—'); t('h-bdesc', d.b_desc);
        t('h-dtipo', d.d_tipo); t('h-detalle', d.d_detalle); t('h-pedido', d.d_pedido);
        form.style.display = 'none'; ok.style.display = ''; hoja.style.display = '';
        window.scrollTo({top: ok.getBoundingClientRect().top + window.scrollY - 90, behavior: 'smooth'});
      })
      .catch(function(){ err.style.display = ''; })
      .then(function(){ btn.disabled = false; btn.textContent = 'Registrar reclamo'; });
  });
  var bp = document.getElementById('btnImprimir'); if(bp) bp.addEventListener('click', function(){ window.print(); });
})();
"""

_LIBRO_CSS = """
.libro-cab{display:flex;align-items:center;gap:14px;flex-wrap:wrap;margin-top:22px}
.libro-cab .sello{display:inline-flex;align-items:center;gap:10px;padding:10px 16px;border:2px solid #C8102E;border-radius:12px;color:#C8102E;font-weight:800;font-size:15px}
.libro-cab .sello svg{width:28px;height:28px}
.prov{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:6px 18px;font-size:14px;margin:14px 0 4px}
.prov b{color:var(--noche)}
.lr h3{margin:22px 0 8px;font-size:16px}
.lr label{display:block;font-size:13px;font-weight:700;margin:12px 0 5px;color:var(--noche)}
.lr input:not([type=radio]),.lr select,.lr textarea{width:100%;padding:11px 12px;border:1px solid var(--trazo);border-radius:10px;font:inherit;font-size:14px;background:#fff}
.lr textarea{min-height:96px;resize:vertical}
.lr .row{display:grid;grid-template-columns:1fr 1fr;gap:0 14px}@media(max-width:620px){.lr .row{grid-template-columns:1fr}}
.lr .radio-row{display:flex;gap:16px;flex-wrap:wrap;font-size:14px;margin-top:8px}.lr .radio-row label{display:inline-flex;align-items:center;gap:6px;margin:0;font-weight:600}
.lr .hint{font-size:12.5px;color:var(--tenue);margin-left:10px}
.lr .aviso{display:none;margin-top:16px;padding:14px 16px;border-radius:12px;border:1px solid #BFE3CF;background:#F1FAF5;font-size:14px}
.lr .aviso.err{border-color:#E7B4B4;background:#FFF4F4}
.hoja{display:none;margin-top:18px;border:1px solid var(--trazo);border-radius:14px;padding:18px 20px;background:#fff}
.hoja h2{font-size:18px;margin:0 0 4px}.hoja .meta{font-size:13px;color:var(--tenue);margin-bottom:12px}
.hoja h4{margin:14px 0 6px;font-size:13.5px;text-transform:uppercase;letter-spacing:.3px;color:var(--tenue)}
.hoja dl{display:grid;grid-template-columns:180px 1fr;gap:4px 12px;font-size:14px;margin:0}.hoja dt{font-weight:700;color:var(--noche)}.hoja dd{margin:0;white-space:pre-wrap}
@media(max-width:620px){.hoja dl{grid-template-columns:1fr}.hoja dt{margin-top:6px}}
.hoja .obs{border:1px dashed var(--trazo);border-radius:10px;padding:10px 12px;font-size:13.5px;color:var(--tenue);min-height:48px}
@media print{header,footer.pie,.cab,.lr,.acciones,.no-print{display:none !important}.hoja{display:block !important;border:none;padding:0}body{background:#fff}}
"""


def _libro_html() -> str:
    em = _em()
    prov = (f"<div class='prov'><div><b>Razón social:</b> {em['razon_social']}</div><div><b>{em['doc_etiqueta']}:</b> {em['ruc']}</div>"
            f"<div><b>Domicilio:</b> {em['direccion']}</div><div><b>Correo:</b> <a href='mailto:{em['correo']}'>{em['correo']}</a></div></div>")
    return f"""
<div class='libro-cab'><span class='sello'>{_libro_svg()} LIBRO DE RECLAMACIONES</span>
  <span style='font-size:13.5px;color:var(--tenue)'>Conforme al Código de Protección y Defensa del Consumidor (Ley N.° 29571) y su
  Reglamento del Libro de Reclamaciones (D.S. 011-2011-PCM y modificatorias).</span></div>
<h1 style='margin-top:14px'>Hoja de reclamación</h1>
<p class='sub'>Registra aquí tu <b>reclamo</b> (disconformidad con el producto o servicio) o tu <b>queja</b> (malestar por la
atención). Recibirás un <b>número de hoja</b> al instante y te responderemos al correo indicado en un plazo máximo de
<b>15 días hábiles</b>. Este Libro es virtual y forma parte de nuestra web; no necesitas descargar nada.</p>
<h3 style='margin:18px 0 2px'>Datos del proveedor</h3>{prov}
<form id='lr-form' class='lr' novalidate>
  <h3>1. Identificación del consumidor reclamante</h3>
  <div class='row'>
    <div><label for='c_nombre'>Nombre completo *</label><input id='c_nombre' name='c_nombre' required autocomplete='name'></div>
    <div><label for='c_doc'>DNI / CE / pasaporte *</label><input id='c_doc' name='c_doc' required></div>
  </div>
  <div class='row'>
    <div><label for='c_tel'>Teléfono *</label><input id='c_tel' name='c_tel' required inputmode='tel' autocomplete='tel'></div>
    <div><label for='c_email'>Correo electrónico *</label><input id='c_email' name='c_email' type='email' required autocomplete='email'></div>
  </div>
  <label for='c_dir'>Domicilio</label><input id='c_dir' name='c_dir' autocomplete='street-address'>
  <div class='radio-row'><span style='font-weight:700;font-size:13px;color:var(--noche)'>¿El consumidor es menor de edad?</span>
    <label><input type='radio' name='c_menor' value='No' checked> No</label>
    <label><input type='radio' name='c_menor' value='Sí'> Sí</label></div>
  <div id='apoBox' style='display:none'><label for='c_apoderado'>Nombre del padre, madre o tutor que presenta el reclamo</label><input id='c_apoderado' name='c_apoderado'></div>

  <h3>2. Identificación del bien contratado</h3>
  <div class='row'>
    <div><label for='b_tipo'>Tipo *</label><select id='b_tipo' name='b_tipo'><option value='Servicio'>Servicio (reserva, matrícula, suscripción)</option><option value='Producto'>Producto (marketplace)</option></select></div>
    <div><label for='b_monto'>Monto reclamado (S/)</label><input id='b_monto' name='b_monto' inputmode='decimal' placeholder='Ej.: 60.00'></div>
  </div>
  <label for='b_desc'>Descripción del bien o servicio</label><input id='b_desc' name='b_desc' placeholder='Ej.: Reserva de cancha de fútbol · 12/07 20:00 · N.º de operación'>

  <h3>3. Detalle de la reclamación</h3>
  <div class='radio-row'>
    <label><input type='radio' name='d_tipo' value='Reclamo' checked> <b>Reclamo</b> (disconformidad con el producto o servicio)</label>
    <label><input type='radio' name='d_tipo' value='Queja'> <b>Queja</b> (malestar por la atención al público)</label></div>
  <label for='d_detalle'>Detalle *</label><textarea id='d_detalle' name='d_detalle' required></textarea>
  <label for='d_pedido'>Pedido del consumidor *</label><textarea id='d_pedido' name='d_pedido' required placeholder='¿Qué solución solicitas?'></textarea>
  <div class='acciones' style='margin-top:18px;align-items:center'><button type='submit' class='btn'>Registrar reclamo</button><span class='hint'>Los campos con * son obligatorios.</span></div>
  <p style='font-size:12.5px;color:var(--tenue);margin-top:14px'>La formulación del reclamo no impide acudir a otras vías de solución de controversias ni es requisito previo
  para interponer una denuncia ante INDECOPI. El proveedor debe dar respuesta en un plazo no mayor a quince (15) días hábiles,
  prorrogable por otros quince (15) cuando la naturaleza del reclamo lo justifique, comunicándolo al consumidor.</p>
  <div class='aviso err' id='lr-err'><b>No pudimos registrar tu reclamo.</b> Inténtalo de nuevo en unos minutos o escríbenos a
  <a href='mailto:{em['correo']}'>{em['correo']}</a> y lo registramos por ti.</div>
</form>
<div class='aviso' id='lr-ok' style='display:none;margin-top:18px;padding:14px 16px;border-radius:12px;border:1px solid #BFE3CF;background:#F1FAF5;font-size:14px'>
  <b>✅ Reclamo registrado.</b> Tu hoja es la <b id='lr-num'></b>. Guarda tu copia (abajo puedes imprimirla o guardarla como PDF).
  Te responderemos al correo indicado en un máximo de <b>15 días hábiles</b>.
  <div class='acciones no-print' style='margin-top:10px'><button type='button' class='btn sec' id='btnImprimir'>🖨️ Imprimir / guardar copia</button><a class='btn sec' href='/'>Volver al inicio</a></div>
</div>
<div class='hoja' id='lr-hoja'>
  <h2>Hoja de reclamación <span id='h-num'></span></h2>
  <div class='meta'>Fecha y hora de registro: <span id='h-fecha'></span> · Libro de Reclamaciones virtual de {em['razon_social']} ({em['doc_etiqueta']} {em['ruc']}), {em['direccion']}</div>
  <h4>1. Consumidor reclamante</h4>
  <dl><dt>Nombre</dt><dd id='h-nombre'></dd><dt>Documento</dt><dd id='h-doc'></dd><dt>Teléfono</dt><dd id='h-tel'></dd><dt>Correo</dt><dd id='h-email'></dd><dt>Domicilio</dt><dd id='h-dir'></dd><dt>Menor de edad</dt><dd id='h-menor'></dd></dl>
  <h4>2. Bien contratado</h4>
  <dl><dt>Tipo</dt><dd id='h-btipo'></dd><dt>Monto reclamado</dt><dd id='h-monto'></dd><dt>Descripción</dt><dd id='h-bdesc'></dd></dl>
  <h4>3. Detalle de la reclamación</h4>
  <dl><dt>Tipo</dt><dd id='h-dtipo'></dd><dt>Detalle</dt><dd id='h-detalle'></dd><dt>Pedido</dt><dd id='h-pedido'></dd></dl>
  <h4>4. Observaciones y acciones adoptadas por el proveedor</h4>
  <div class='obs'>Pendiente. {em['razon_social']} responderá al correo del consumidor dentro de los 15 días hábiles siguientes a la fecha de registro.</div>
  <h4>5. Fecha de comunicación de la respuesta</h4>
  <div class='obs'>Se consignará al responder.</div>
</div>
<script>{_LIBRO_JS}</script>"""


def _libro_svg() -> str:
    try:
        from web.ui import LIBRO_SVG
        return LIBRO_SVG
    except Exception:  # noqa: BLE001
        return "📕"


@router.get("/libro-de-reclamaciones", response_class=HTMLResponse)
@router.get("/legal/libro-de-reclamaciones", response_class=HTMLResponse)
def libro_de_reclamaciones(request: Request) -> HTMLResponse:
    """LIBRO DE RECLAMACIONES en página propia, con el formato de hoja de
    reclamación del D.S. 011-2011-PCM (datos del proveedor, número y fecha,
    consumidor, bien contratado, detalle, pedido, observaciones del proveedor)
    y copia imprimible para el consumidor. Integrado en la web: la hoja se
    registra en `POST /reclamaciones` y el operador la atiende en la torre.
    (Culqi observó en sep-2026 que la sección anclada en la portada "no estaba
    implementada de forma correcta": ahora hay URL propia y hoja completa.)"""
    from web import sesion, ui
    ses = sesion.de_request(request)
    cuerpo = f"<style>{_LIBRO_CSS}</style><div style='padding-top:6px'>{_libro_html()}</div>"
    return ui.shell("Libro de Reclamaciones", cuerpo, sesion=ses, nav=ui.nav_simple(ses, volver="/"),
                    desc="Libro de Reclamaciones virtual de Pichangol: registra tu reclamo o queja y recibe respuesta en 15 días hábiles.")


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
