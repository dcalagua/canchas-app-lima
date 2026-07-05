"""Configuración por entorno (no secretos en código). Las reglas de incentivos
viven en la tabla `config_incentivos` (ver db/store.py), no aquí."""

from __future__ import annotations

import os

# URL del módulo de existencia (Capa IA). Si está vacío, se usa el stub.
EXISTENCIA_API_URL = os.getenv("EXISTENCIA_API_URL", "")

# --- Factiliza (consulta de DNI = identidad del reclamante) -----------------
# El token nunca va en el APK; se lee aquí. Sin token, la consulta queda
# inactiva (fail-safe) y el flujo sigue con validación humana.
FACTILIZA_API_TOKEN = os.getenv("FACTILIZA_API_TOKEN", "")
FACTILIZA_BASE_URL = os.getenv("FACTILIZA_BASE_URL", "https://api.factiliza.com/v1")

# --- WhatsApp Cloud API (OTP de PROPIEDAD) ---------------------------------
# Credenciales que se cargan como secrets en Railway tras seguir la guía
# docs/whatsapp-cloud-api-setup.md. Si el token está vacío, el adapter corre en
# modo STUB (no envía nada real; el código se devuelve sólo en entorno de prueba).
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
WHATSAPP_API_VERSION = os.getenv("WHATSAPP_API_VERSION", "v21.0")
# Plantilla de AUTENTICACIÓN aprobada por Meta (categoría Authentication).
WHATSAPP_OTP_TEMPLATE = os.getenv("WHATSAPP_OTP_TEMPLATE", "pichangol_otp")
WHATSAPP_OTP_LANG = os.getenv("WHATSAPP_OTP_LANG", "es")
# Sólo en entornos de prueba: devolver el código en la respuesta (NUNCA en prod).
OTP_DEBUG_DEVOLVER_CODIGO = os.getenv("OTP_DEBUG_DEVOLVER_CODIGO", "0") == "1"

# Parámetros del OTP de propiedad.
OTP_TTL_SEG = int(os.getenv("OTP_TTL_SEG", "300"))        # vence en 5 min
OTP_MAX_INTENTOS = int(os.getenv("OTP_MAX_INTENTOS", "5"))
OTP_REENVIO_MIN_SEG = int(os.getenv("OTP_REENVIO_MIN_SEG", "60"))

# --- Twilio (OTP por SMS, alternativa/respaldo a WhatsApp) ------------------
# Independiente de Meta: sirve mientras WhatsApp Cloud API no esté habilitado.
# Si TWILIO_ACCOUNT_SID/TWILIO_AUTH_TOKEN no están, el adapter queda inactivo.
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
# Remitente: un número Twilio (+1...) o un Messaging Service SID (MG...).
TWILIO_FROM = os.getenv("TWILIO_FROM", "")
TWILIO_MESSAGING_SERVICE_SID = os.getenv("TWILIO_MESSAGING_SERVICE_SID", "")
# Remitente de WhatsApp por Twilio (sandbox o número aprobado), ej.
# "+14155238886" (sandbox). Si está, se puede mandar el OTP por WhatsApp vía
# Twilio SIN depender de la aprobación de Meta.
TWILIO_WHATSAPP_FROM = os.getenv("TWILIO_WHATSAPP_FROM", "")
# URL pública EXACTA del webhook entrante de WhatsApp (la que se configura en la
# consola de Twilio, ej. https://<backend>/propiedad/webhook/whatsapp). Se usa
# para validar la firma X-Twilio-Signature de forma confiable detrás del proxy.
TWILIO_WEBHOOK_URL = os.getenv("TWILIO_WEBHOOK_URL", "")
# Canal preferido: "whatsapp" (Meta) | "twilio_whatsapp" | "sms".
OTP_CANAL_PREFERIDO = os.getenv("OTP_CANAL_PREFERIDO", "whatsapp")

# --- Reclamo de propiedad con intervención humana (concierge) ---------------
# Número (E.164, ej. +51987654321) al que llegan los avisos de admin por WhatsApp
# cuando alguien reclama una cancha y cuando un validador la confirma en sitio.
PICHANGOL_ADMIN_WHATSAPP = os.getenv("PICHANGOL_ADMIN_WHATSAPP", "")
# Token que protege el PANEL WEB de administración (/admin). Sin token, el panel
# queda deshabilitado (503). No viaja en la URL: la página lo guarda en el
# navegador y lo envía en la cabecera X-Admin-Token.
ADMIN_PANEL_TOKEN = os.getenv("ADMIN_PANEL_TOKEN", "")
# Clave compartida APP↔BACKEND para que SOLO el APK oficial pueda llamar a los
# endpoints públicos del dueño (crear reclamo, estado, OTP, identidad…). El APK la
# envía en la cabecera X-App-Key (viene de un --dart-define en el build). Si está
# VACÍA, no se exige (permite un despliegue gradual sin romper apps ya instaladas);
# una vez configurada aquí y en el APK, un curl externo sin la clave recibe 401.
APP_API_KEY = os.getenv("APP_API_KEY", "")
# Si true, la validación en sitio del motorizado activa la cancha automáticamente
# (y se avisa al admin). Si false, queda lista y el admin la activa a mano.
VALIDADOR_ACTIVA_AUTOMATICO = os.getenv("VALIDADOR_ACTIVA_AUTOMATICO", "1") == "1"
# Distancia máx (m) entre el GPS del validador y la ubicación de la cancha para
# considerar que la visita "coincide".
RECLAMO_VALIDACION_GPS_MAX_M = float(
    os.getenv("RECLAMO_VALIDACION_GPS_MAX_M", "150"))
# Distancia máx (m) entre el GPS del DISPOSITIVO del reclamante (desde dónde envió
# la solicitud) y la ubicación de la cancha, para considerar que "está en el
# lugar". Sólo se exige si el admin activa el modo (config exigir_ubicacion_reclamo).
RECLAMO_UBICACION_MAX_M = float(
    os.getenv("RECLAMO_UBICACION_MAX_M", "150"))

# Distancia máx (m) entre la ubicación declarada y la del sitio para considerar
# que la verificación física "coincide".
COINCIDENCIA_MAX_M = float(os.getenv("VERIF_COINCIDENCIA_MAX_M", "200"))

ZONAS = ("lima_norte", "lima_sur", "lima_este", "lima_moderna", "callao")

# Mapeo distrito -> zona (parcial; lo no mapeado cae a 'lima_moderna').
DISTRITO_ZONA: dict[str, str] = {
    # Lima Norte
    "los olivos": "lima_norte", "san martin de porres": "lima_norte",
    "comas": "lima_norte", "carabayllo": "lima_norte", "puente piedra": "lima_norte",
    "independencia": "lima_norte",
    # Lima Sur
    "villa el salvador": "lima_sur", "villa maria del triunfo": "lima_sur",
    "san juan de miraflores": "lima_sur", "chorrillos": "lima_sur",
    "lurin": "lima_sur",
    # Lima Este
    "ate": "lima_este", "santa anita": "lima_este", "el agustino": "lima_este",
    "san juan de lurigancho": "lima_este", "lurigancho": "lima_este",
    "chosica": "lima_este", "la molina": "lima_este",
    # Lima Moderna
    "miraflores": "lima_moderna", "san isidro": "lima_moderna",
    "surco": "lima_moderna", "santiago de surco": "lima_moderna",
    "san borja": "lima_moderna", "barranco": "lima_moderna",
    "jesus maria": "lima_moderna", "magdalena": "lima_moderna",
    "lince": "lima_moderna", "pueblo libre": "lima_moderna",
    # Callao
    "callao": "callao", "bellavista": "callao", "la perla": "callao",
    "ventanilla": "callao",
}


def zona_de_distrito(distrito: str | None) -> str:
    if not distrito:
        return "lima_moderna"
    return DISTRITO_ZONA.get(distrito.strip().lower(), "lima_moderna")
