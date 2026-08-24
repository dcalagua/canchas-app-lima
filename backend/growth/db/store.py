"""Capa de datos en memoria (stub) de los 3 subsistemas: PUNTOS/PREMIOS,
SOLICITUDES POR ZONA y VERIFICACION FISICA.

En producción se reemplaza por Postgres/Supabase usando `db/schema.sql` sin
cambiar la interfaz de los servicios. Aquí todo vive en memoria para poder correr
y testear sin base de datos ni servicios externos reales.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone, timedelta


def ahora() -> datetime:
    return datetime.now(timezone.utc)


def mes_de(dt: datetime) -> str:
    return dt.strftime("%Y-%m")


# === config_incentivos (TODO configurable, nada hardcodeado en la lógica) ======
CONFIG_DEFAULT: dict[str, str] = {
    # WhatsApp de contacto de Pichangol/EBIM para SERVICIOS (landing, redes),
    # por PAÍS y editable desde la torre de control. Se guarda el número LOCAL
    # (sin código de país); el backend antepone el código (PE 51 / EC 593 / BO 591).
    "contacto_whatsapp_pe": "",
    "contacto_whatsapp_ec": "998706994",
    "contacto_whatsapp_bo": "",
    # Respaldo global (legado) si ningún país tiene número.
    "contacto_whatsapp": "593998706994",
    # Precios MENSUALES (soles) de los servicios de marketing de Pichangol.
    # Editables desde la torre de control. Es lo que se debita del saldo del dueño.
    "servicio_landing_soles": "49",
    # "Manejo de redes" (unificado): contenido con IA + publicación automática en
    # IG/FB si el dueño conecta sus cuentas (o compartir con un tap). Editable.
    "servicio_redes_soles": "129",
    "servicio_presencia_soles": "149",
    # Precios DIFERENCIADOS por tipo de negocio (Fase 3): los de arriba son la
    # tarifa base (academias). Un CLUB/cancha puede tener su propia tarifa; si el
    # override está VACÍO ("") se usa el precio base. Editable en la torre de
    # control. El negocio UNIFICADO (mixto) usa la tarifa base (academia).
    "servicio_landing_soles_club": "",
    "servicio_redes_soles_club": "",
    "servicio_presencia_soles_club": "",
    # (Legado) "Gestión de redes" se fusionó en "Manejo de redes". Se conserva la
    # clave por compatibilidad con datos antiguos; ya no se ofrece en el catálogo.
    "servicio_gestion_soles": "199",
    # Comisión por COBRO DIGITAL de matrícula (cuando el alumno paga por la app).
    # Es una tarifa única "tipo POS" que la academia absorbe (el alumno paga el
    # precio limpio). Por país y editable desde la torre de control. Efectivo = 0%
    # (un pago que el profe marca a mano NO pasa por aquí). Perú arranca en 5%;
    # los demás países en 0 hasta que se configuren.
    "comision_matricula_pct_pe": "5",
    "comision_matricula_pct_ec": "0",
    "comision_matricula_pct_bo": "0",
    # Tope de generaciones de posts con IA por academia/mes (control de costo).
    # Editable desde la torre de control. 0 = sin tope.
    "marketing_posts_limite_mes": "30",
    # PICHANGOL PRO: membresía mensual del JUGADOR (se debita de su billetera
    # única/saldo). Precio BASE (Perú) editable desde la torre de control, con
    # override por país (vacío = usa el base). Rollout LATAM.
    "pro_precio_soles": "12",
    "pro_precio_soles_ec": "",
    "pro_precio_soles_bo": "",
    # Retos que un jugador SIN Pichangol Pro puede enviar por semana (Pro =
    # ilimitado). Editable desde la torre de control.
    "retos_free_limite_semana": "3",
    # Horas para CONFIRMAR el resultado de un reto. Si el otro jugador no
    # confirma ni disputa en este plazo, se da por ganador al reportado (auto-
    # confirmación). Editable desde la torre. 0 = confirmación inmediata.
    "retos_confirmacion_horas": "24",
    # Días para que una venta del marketplace se libere sola si el comprador no
    # confirma recepción ni disputa (auto-liberación a favor del vendedor).
    "ventas_liberacion_dias": "7",
    "puntos_traer_cancha": "500",
    "puntos_invitar_jugador": "100",
    "puntos_pedir_cancha": "50",
    # 100 puntos = S/ 1 de vale
    "equivalencia_puntos_por_sol": "100",
    # --- FIDELIDAD del JUGADOR (reservas pagadas, ago-2026) -----------------
    # Puntos por unidad de moneda pagada (S/ 1 o Bs 1 = 1 punto); en USD
    # (Ecuador) $1 = 3 puntos para emparejar el valor. Todo editable en torre.
    "fidelidad_puntos_por_unidad": "1",
    "fidelidad_puntos_por_usd": "3",
    # Valor del canje: 100 puntos = 3 unidades de moneda local (retorno ~3%,
    # lo absorbe la comisión de Pichangol, no el neto del dueño).
    "fidelidad_valor_100_puntos": "3",
    # Caducidad de los puntos LIBERADOS en días (0 = no caducan).
    "fidelidad_caducidad_dias": "180",
    # --- PROMOCIONES de la billetera (ago-2026, editable en torre) ----------
    # BONO DE RECARGA: % extra que se regala al recargar (0 = promo apagada),
    # con recarga mínima que la activa y tope del bono por recarga (en la
    # moneda local del saldo). Lo paga Pichangol (costo de marketing).
    "promo_bono_recarga_pct": "0",
    "promo_bono_recarga_min": "50",
    "promo_bono_recarga_tope": "20",
    # tope mensual de premios financiados por Pichangol (en soles)
    "tope_mensual_premios_pichangol_soles": "500",
    # tope de solicitudes que ACREDITAN puntos por usuario/mes
    "tope_solicitudes_usuario_mes": "5",
    # umbral de score de la IA para verificar SIN visita
    "umbral_ia_verificacion": "70",
    # modo GLOBAL de aprobación de canchas: "marcha_blanca" (aprobación directa
    # del admin, activa al instante) | "nuevo_flujo" (exige validación en sitio
    # antes de activar). Se puede sobreescribir por cancha (modo_aprobacion_overrides).
    "modo_aprobacion": "marcha_blanca",
    # Si "1", el admin sólo puede APROBAR un reclamo si el GPS del dispositivo
    # desde donde se envió coincide con la ubicación de la cancha (anti-fraude
    # ligero: "estar en el lugar" al reclamar). "0" = no se exige (piloto).
    "exigir_ubicacion_reclamo": "0",
    # Tasa efectiva de la PASARELA/BANCO (Culqi) sobre el BRUTO de cada cobro
    # digital: es el COSTO real que paga Pichangol al procesar la tarjeta. Se
    # resta de la comisión que PCG le cobra a la academia para saber el MARGEN
    # neto de Pichangol (torre de control → Márgenes). Culqi Perú ≈ 3.44% + IGV
    # ≈ 4.06%; editable por el operador con su tarifa real.
    "comision_banco_pct": "4.06",
    # Canal de comunicación que muestra el APK en la ficha de la academia/cancha:
    # "pcg_primero" (chat interno principal + WhatsApp de respaldo) |
    # "solo_pcg" (oculta WhatsApp: todos usan el chat del app) |
    # "whatsapp_libre" (chat + WhatsApp visibles por igual). Política de PCG
    # para empujar la retención por el chat propio sin perder al que usa WhatsApp.
    "canal_comunicacion": "pcg_primero",
    # --- CONVOCATORIAS ("pichangas" programadas) ---------------------------
    # Modo GLOBAL de asignación de cupos cuando una convocatoria no fija el suyo
    # (se puede sobreescribir por convocatoria). Los 3 modos son configurables por
    # el admin del club: "orden_llegada" (el que se anota primero entra, feedback
    # inmediato) | "sorteo" (ventana de inscripción y sorteo al cerrar) |
    # "equidad" (al cerrar prioriza a quien más quedó fuera y mejor asiste).
    "convocatoria_modo_asignacion": "orden_llegada",
    # Pesos del puntaje de EQUIDAD (todo configurable, nada hardcodeado):
    # sube quien más semanas quedó en lista de espera; baja quien ya jugó en las
    # últimas fechas y quien no se presentó (no-show).
    "convocatoria_equidad_peso_espera": "3",
    "convocatoria_equidad_peso_jugo": "2",
    "convocatoria_equidad_peso_noshow": "5",
    # Cuántas convocatorias cerradas recientes cuentan como "jugó reciente".
    "convocatoria_equidad_ventana": "4",
}

# Modos de aprobación válidos.
MODOS_APROBACION = ("marcha_blanca", "nuevo_flujo")

# Canales de comunicación válidos (qué muestra el APK para contactar al profe).
CANALES_COMUNICACION = ("pcg_primero", "solo_pcg", "whatsapp_libre")

# Modos de asignación de cupos de una convocatoria válidos.
MODOS_ASIGNACION = ("orden_llegada", "sorteo", "equidad")


@dataclass
class PuntosMovimiento:
    id: int
    usuario_id: str
    accion: str                 # traer_cancha | invitar_jugador | pedir_cancha
    puntos: int
    estado: str                 # pendiente | liberado | anulado
    ref_tipo: str | None
    ref_id: str | None
    creado_en: datetime
    liberado_en: datetime | None = None


@dataclass
class PremioCanje:
    id: int
    usuario_id: str
    puntos_usados: int
    tipo_premio: str
    vale_id: str
    fuente_financiamiento: str   # pichangol | dueno
    estado: str                  # emitido | aplicado | anulado
    valor_soles: float
    creado_en: datetime


@dataclass
class SolicitudCancha:
    id: int
    usuario_id: str
    nombre_cancha_libre: str
    direccion_texto: str
    lat: float | None
    lng: float | None
    distrito: str
    zona: str                    # lima_norte|lima_sur|lima_este|lima_moderna|callao
    estado: str                  # solicitada|en_captacion|registrada|descartada
    cancha_id: str | None
    creado_en: datetime


@dataclass
class VerificacionFisica:
    id: int
    cancha_id: str
    solicitud_id: int | None
    motivo: str                  # sin_documentos|ia_no_concluyente|alto_valor
    verificador_id: int | None
    estado: str                  # no_requerida|agendada|en_sitio|confirmada|rechazada
    fotos_geo_urls: list[str]
    lat_sitio: float | None
    lng_sitio: float | None
    firma_verificador: str | None
    observaciones: str | None
    metodo: str | None           # documental | en_sitio (interno)
    creado_en: datetime
    cerrada_en: datetime | None = None


@dataclass
class Verificador:
    id: int
    nombre: str
    zona: str
    tipo: str                    # por_encargo | dedicado
    activo: bool = True


@dataclass
class OtpPropiedad:
    """Código OTP transitorio para validar la PROPIEDAD de una cancha. NO se
    persiste (seguridad): vive en memoria con TTL y se borra al usarse/vencer.
    Sólo guardamos el hash del código, nunca el texto plano."""
    cancha_id: str
    telefono: str                # E.164 sin '+', sólo en memoria
    codigo_hash: str
    expira_en: datetime
    creado_en: datetime
    intentos: int = 0
    enviado_via: str = "stub"     # whatsapp | stub


@dataclass
class ConfirmacionPropiedad:
    """Registro durable de la DECISIÓN de propiedad (auditable). No guarda el
    teléfono completo, sólo enmascarado."""
    id: int
    cancha_id: str
    solicitante_id: str
    metodo: str                  # otp_whatsapp | manual | en_sitio
    estado: str                  # confirmada | pendiente_revision | rechazada
    telefono_enmascarado: str | None
    creado_en: datetime
    decidido_en: datetime | None = None
    nota: str | None = None


@dataclass
class ReclamoPropiedad:
    """Solicitud de reclamo con intervención humana primero (modelo concierge):
    el reclamante pide la cancha → Pichangol (admin) recibe un WhatsApp con el
    código y lo vetea → tras aprobar, el dueño configura → al guardar queda
    pendiente de validación EN SITIO por un motorizado que ingresa el código y
    cuyo GPS debe coincidir con la cancha → recién ahí se activa."""
    id: int
    cancha_id: str
    solicitante_id: str          # correo del reclamante (login)
    nombre_local: str
    codigo: str
    estado: str  # pendiente_triage|aprobado_triage|pendiente_validacion|activada|rechazada
    creado_en: datetime
    telefono_contacto: str | None = None
    dni: str | None = None
    nombre_titular: str | None = None
    ruc: str | None = None
    razon_social: str | None = None
    relacion: str | None = None
    lat: float | None = None      # ubicación de la CANCHA (del pin / Google)
    lng: float | None = None
    # Ubicación del DISPOSITIVO desde donde se envió la solicitud (GPS del
    # reclamante al reclamar). Sirve para contrastar que estaba en el lugar.
    solicitante_lat: float | None = None
    solicitante_lng: float | None = None
    decidido_en: datetime | None = None
    validado_en: datetime | None = None
    validador: str | None = None
    nota: str | None = None
    solicitante_nombre: str = ""  # nombre del reclamante (de su cuenta Google)
    # Prueba de propiedad (opcional) que dejó el reclamante para el triage.
    foto_evidencia_url: str = ""
    nota_reclamante: str = ""


@dataclass
class CanchaEstado:
    """Estado relevante de una cancha para estos subsistemas (en producción es la
    fila de `pichangol_canchas`)."""
    cancha_id: str
    verificada: bool = False
    metodo_verificacion: str | None = None   # documental | en_sitio
    verificada_en_persona: bool = False      # PLUS, nunca categoría menor
    primera_reserva: bool = False
    lat_declarada: float | None = None
    lng_declarada: float | None = None
    zona: str | None = None


@dataclass
class Convocatoria:
    """Una 'pichanga' programada de un club: partido con cupos, ventana de
    inscripción y un modo de asignación (orden_llegada|sorteo|equidad). Resuelve
    el caos del chat de WhatsApp de los jueves con lista de espera y reparto
    justo. `modo_asignacion=None` usa el modo global del club/config."""
    id: int
    club_id: str
    titulo: str
    deporte: str
    cupos: int
    estado: str                       # abierta | cerrada
    creado_en: datetime
    categoria: str | None = None      # master | menor | libre
    fecha_partido: str | None = None  # ISO/texto del partido (display)
    apertura: datetime | None = None  # desde cuándo se puede inscribir
    cierre: datetime | None = None    # hasta cuándo (y cuándo se resuelve)
    modo_asignacion: str | None = None
    semilla: str | None = None        # fijada al cerrar (sorteo reproducible)
    creado_por: str = ""
    cerrado_en: datetime | None = None


@dataclass
class Inscripcion:
    """Un socio anotado a una convocatoria. `creado_en` es la marca de tiempo de
    inscripción (clave para orden_llegada). `posicion` y el estado final se
    congelan al cerrar; `asistio` lo marca el admin tras el partido (alimenta el
    puntaje de equidad)."""
    id: int
    convocatoria_id: int
    socio_id: str
    socio_nombre: str
    estado: str                       # pendiente | confirmado | lista_espera | cancelado
    creado_en: datetime
    posicion: int | None = None
    asistio: bool | None = None


@dataclass
class Reto:
    """Un RETO P2P: un jugador reta a otro (por correo). Coordinan la cancha y
    reportan el resultado; el resultado suma al ranking global. Une reservas y
    circuito. Identidad = correo (misma que el ranking global)."""
    id: int
    retador_email: str
    retador_nombre: str
    retado_email: str
    retado_nombre: str
    deporte: str
    creado_en: datetime
    zona: str = ""
    # pendiente | aceptado | rechazado | por_confirmar | jugado | disputado
    estado: str = "pendiente"
    ganador_email: str = ""
    marcador: str = ""
    mensaje: str = ""
    jugado_en: datetime | None = None  # cuándo quedó CONFIRMADO (temporada/ranking)
    # Doble confirmación del resultado: quién lo reportó y cuándo. Si el otro no
    # confirma/disputa en el plazo, se auto-confirma a favor del reportado.
    reportado_por: str = ""
    reportado_en: datetime | None = None
    auto_confirmado: bool = False
    # ── DOBLES (2 vs 2) ──────────────────────────────────────────────────────
    # modalidad: 'singles' (1v1, por defecto) | 'dobles' (2v2). En dobles, cada
    # lado tiene un COMPAÑERO: lado retador = {retador, retador2}, lado retado =
    # {retado, retado2}. El `ganador_email` es CUALQUIER integrante del lado
    # ganador; el lado se deriva de a qué pareja pertenece ese correo.
    modalidad: str = "singles"
    retador2_email: str = ""
    retador2_nombre: str = ""
    retado2_email: str = ""
    retado2_nombre: str = ""


@dataclass
class Venta:
    """Una ORDEN del Marketplace (escrow simple). El comprador ya pagó (Culqi);
    el dinero queda RETENIDO hasta que confirme la recepción, y recién ahí se
    libera el neto al vendedor. Estados:
      pagado    → pagado, retenido (esperando entrega/recepción)
      entregado → el vendedor marcó que entregó (sigue retenido)
      recibido  → el comprador confirmó → LIBERADO (neto pagable al vendedor)
      disputado → el comprador abrió disputa (no se libera; lo revisa el operador)
    """
    id: int
    producto_id: str
    producto_nombre: str
    comprador_email: str
    comprador_nombre: str
    vendedor_email: str
    vendedor_nombre: str
    monto_soles: float
    creado_en: datetime
    estado: str = "pagado"
    entregado_en: datetime | None = None
    recibido_en: datetime | None = None
    auto_liberado: bool = False  # se liberó por vencimiento del plazo, no por el comprador


@dataclass
class PagoRegistro:
    """Un movimiento de pasarela (Culqi). Es plata: autoritativo en el backend.
    - tipo=recarga → acredita saldo del dueño (dueno_id).
    - tipo=fee_reserva → comisión que el jugador paga a Pichangol (saldo cero);
      NO acredita saldo de nadie, es ingreso de Pichangol.
    monto_centimos en céntimos de sol (entero), como maneja Culqi."""
    id: int
    tipo: str                    # recarga | fee_reserva
    monto_centimos: int
    moneda: str                  # PEN
    estado: str                  # aprobado | rechazado
    creado_en: datetime
    dueno_id: str | None = None
    culqi_charge_id: str | None = None
    email: str | None = None
    concepto: str | None = None
    # Comisión congelada al momento del cobro (tipo=matricula_online): la tarifa
    # por cobro digital depende del país y es editable, así que se guarda aquí y
    # NO se recalcula después. neto = monto_centimos - comision_centimos.
    comision_centimos: int = 0
    # Liquidación (solo tipo=liquidacion_online): estado del pago del NETO al
    # dueño. liquidado=False → Pichangol aún le debe; True → ya se le transfirió.
    liquidado: bool = False
    liquidado_en: datetime | None = None
    metodo_liquidacion: str | None = None      # yape | transferencia | efectivo
    referencia_liquidacion: str | None = None  # nº de operación / nota
    # MEDIO con el que pagó el JUGADOR (yape | tarjeta | sena): trazabilidad
    # del origen del cobro para el estado de cuenta del dueño.
    medio: str | None = None


class Stores:
    def __init__(self) -> None:
        self.config: dict[str, str] = dict(CONFIG_DEFAULT)
        self.movimientos: list[PuntosMovimiento] = []
        self.canjes: list[PremioCanje] = []
        self.solicitudes: list[SolicitudCancha] = []
        self.verificaciones_fisicas: list[VerificacionFisica] = []
        self.verificadores: list[Verificador] = []
        self.canchas: dict[str, CanchaEstado] = {}
        self.visitas_liquidacion: list[dict] = []   # pagos a verificadores (stub)
        # OTP de propiedad: transitorio, NO se persiste (uno activo por cancha).
        self.otps: dict[str, OtpPropiedad] = {}
        self.confirmaciones_propiedad: list[ConfirmacionPropiedad] = []
        self.reclamos: list[ReclamoPropiedad] = []
        # Override del modo de aprobación POR cancha: {cancha_id: modo}. Si una
        # cancha no está aquí, usa el modo global (config["modo_aprobacion"]).
        self.modo_aprobacion_overrides: dict[str, str] = {}
        # Convocatorias ("pichangas" programadas) y sus inscripciones.
        self.convocatorias: list[Convocatoria] = []
        self.inscripciones: list[Inscripcion] = []
        # RETOS P2P (jugador reta a jugador; el resultado suma al ranking).
        self.retos: list[Reto] = []
        # VENTAS del Marketplace (escrow: retenido hasta que el comprador confirme).
        self.ventas: list[Venta] = []
        # Anti-fraude "1 DNI = 1 cuenta": hash(DNI) -> correo verificado. Solo se
        # guarda el HASH (Ley 29733: nunca el número). Si un DNI ya está ligado a
        # otra cuenta, no se puede verificar una segunda.
        self.dni_verificados: dict[str, str] = {}
        # CIRCUITO: jugadores que se declararon "disponibles para retar" (aunque
        # aún no hayan jugado). Resuelve el arranque en frío del ranking.
        # email -> {nombre, deporte, zona, categoria, actualizado}.
        self.jugadores_circuito: dict[str, dict] = {}
        # RANKING GLOBAL (vista para la torre): el ranking cruzado se computa en
        # el APK (las academias viven en Supabase), así que el app EMPUJA un
        # snapshot {deportes:[...], actualizado, por} que la torre solo lee.
        self.ranking_snapshot: dict = {}
        # PAGOS (Culqi): saldo prepago por dueño (céntimos) + libro de pagos.
        self.saldos: dict[str, int] = {}          # dueno_id -> céntimos
        self.pagos: list[PagoRegistro] = []
        # RECARGAS POR QR (Yape directo, sin pasarela): solicitudes que el
        # usuario manda con su constancia y el OPERADOR aprueba/rechaza en la
        # torre. {id, email, monto_soles, foto_url, estado, creado_en,
        # resuelto_en, motivo} — estado: pendiente | aprobada | rechazada.
        self.recargas_qr: list[dict] = []
        # CUPONES de saldo (promos): {CODIGO: {valor_soles, usos_max, activo,
        # creado_en, usados: [emails]}}. Un canje por usuario por cupón; el
        # operador los crea/desactiva en la torre.
        self.cupones: dict[str, dict] = {}
        # SUSCRIPCIONES a servicios de marketing (landing/redes/presencia). Clave
        # "{academia_id}:{servicio}" -> dict con estado y próximo cobro. Se debita
        # del saldo del dueño cada mes (mismo saldo prepago de Culqi).
        self.suscripciones: dict[str, dict] = {}
        # LANDINGS generadas (fulfillment del servicio). academia_id -> datos que
        # el backend renderiza como página pública en GET /l/{academia_id}.
        self.landings: dict[str, dict] = {}
        # USO de generación de posts con IA: academia_id -> {"YYYY-MM": conteo}.
        # Sirve para el tope mensual (control de costo Anthropic).
        self.marketing_uso: dict[str, dict] = {}
        # COMMUNITY MANAGER autónomo (Fase 0): academia_id -> config + post del día
        # {activo, cada_dias, contexto, datos, ultimo_post, ultimo_generado}. El
        # scheduler pre-genera el post; la imagen (flyer) vive en memoria.
        self.cm: dict[str, dict] = {}
        # CONEXIONES de redes (Gestión de redes / Nivel 2): academia_id -> dict con
        # el permiso OAuth de Meta del dueño (IG/FB) para publicar por él. El token
        # va CIFRADO en "token_enc" y NUNCA se expone en respuestas (se enmascara).
        self.conexiones_redes: dict[str, dict] = {}
        # Solicitudes de eliminación de datos (callback de Meta): auditoría ligera.
        self.eliminaciones: list[dict] = []
        # IMÁGENES para publicar (hosting transitorio): id -> {bytes, content_type}.
        # NO se persiste (Meta las descarga al instante al publicar); se descartan
        # las más viejas al pasar el tope (config.IMG_MAX_RETENIDAS).
        self.imagenes: "dict[str, dict]" = {}
        # VIDEOS (reels) para publicar (hosting transitorio): id -> {bytes,
        # content_type}. Igual que imágenes pero con tope MUCHO menor (pesan
        # más): se conservan sólo los últimos pocos. NO se persiste.
        self.videos: "dict[str, dict]" = {}
        # VISTAS de destacados (métrica de impacto del boost): por id (dueno_id
        # de canchas o id de academia) → {YYYY-MM-DD: nº impresiones ese día}.
        self.vistas: dict[str, dict[str, int]] = {}
        # Métodos de pago guardados (One Click). NO se guarda la tarjeta, sólo el
        # token permanente de Culqi (crd_...) + marca y últimos 4 para mostrar.
        self.customers: dict[str, str] = {}       # user_id -> cus_id de Culqi
        self.metodos: dict[str, list[dict]] = {}  # user_id -> [{id, marca, ultimos4, creado_en}]
        # Tarjeta de DÉBITO AUTOMÁTICO por academia para las suscripciones: al
        # renovar, si no hay saldo, se cobra a esta tarjeta guardada (crd_ de
        # Culqi). Guarda email + marca + últimos4, NUNCA el número completo.
        self.metodo_suscripcion: dict[str, dict] = {}  # academia_id -> {card_id,email,marca,ultimos4}
        # SUSCRIPCIÓN MENSUAL del ALUMNO a una academia (pago "mes a mes"): al
        # matricularse en modo mes a mes, paga 1 mes y guarda su tarjeta; el cron
        # cobra cada mes y acredita el neto a la academia (misma comisión POS).
        # Clave = alumno_id -> {alumno_id, academia_id, email, card_id, marca,
        # ultimos4, monto_centimos, pais, proximo_cobro, estado, concepto}.
        self.suscripciones_alumno: dict[str, dict] = {}
        # PICHANGOL PRO: membresía mensual del jugador. email -> {hasta: iso,
        # ultimo_cobro: iso}. Se debita de la billetera única (saldo del email).
        self.membresias_pro: dict[str, dict] = {}
        # LIBÉLULA (Bolivia): deudas registradas para cobro. identificador ->
        # {identificador, id_transaccion, email, monto_bs, concepto, pagado,
        # fecha_pago, tipo, ref, dueno_id, creado_en}. La app la crea (pendiente),
        # el callback la marca pagada; sobrevive reinicios vía snapshot.
        self.libelula_deudas: dict[str, dict] = {}
        self._idem: dict[tuple[str, str], dict] = {}
        self._ids: dict[str, int] = {}

    # --- utilidades ---
    def next_id(self, scope: str) -> int:
        self._ids[scope] = self._ids.get(scope, 0) + 1
        return self._ids[scope]

    def cfg(self, clave: str) -> str:
        return self.config.get(clave, CONFIG_DEFAULT.get(clave, "0"))

    def cfg_int(self, clave: str) -> int:
        try:
            return int(float(self.cfg(clave)))
        except ValueError:
            return 0

    def modo_aprobacion(self, cancha_id: str | None = None) -> str:
        """Modo de aprobación efectivo: el override de la cancha si existe, si no
        el global. Siempre devuelve un modo válido."""
        glob = self.cfg("modo_aprobacion")
        if glob not in MODOS_APROBACION:
            glob = "marcha_blanca"
        if cancha_id and cancha_id in self.modo_aprobacion_overrides:
            ov = self.modo_aprobacion_overrides[cancha_id]
            if ov in MODOS_APROBACION:
                return ov
        return glob

    def pro_activo(self, email: str) -> bool:
        """¿El correo tiene membresía Pichangol Pro vigente (hasta > ahora)?"""
        m = self.membresias_pro.get((email or "").strip().lower())
        if not m:
            return False
        hasta = m.get("hasta")
        try:
            dt = datetime.fromisoformat(hasta) if hasta else None
        except (TypeError, ValueError):
            dt = None
        return dt is not None and dt > ahora()

    def pro_emails_activos(self) -> list[str]:
        """Correos con Pro vigente (para pintar la insignia PRO en el ranking)."""
        return [e for e in self.membresias_pro if self.pro_activo(e)]

    def modo_asignacion(self, override: str | None = None) -> str:
        """Modo de asignación efectivo de una convocatoria: el override de la
        convocatoria si es válido, si no el global. Siempre devuelve válido."""
        if override in MODOS_ASIGNACION:
            return override
        glob = self.cfg("convocatoria_modo_asignacion")
        return glob if glob in MODOS_ASIGNACION else "orden_llegada"

    # --- pagos / saldo prepago (Culqi) --------------------------------------
    def saldo_centimos(self, dueno_id: str) -> int:
        return self.saldos.get(dueno_id, 0)

    def acreditar(self, dueno_id: str, centimos: int) -> int:
        """Suma [centimos] al saldo del dueño y devuelve el nuevo saldo."""
        self.saldos[dueno_id] = self.saldos.get(dueno_id, 0) + int(centimos)
        return self.saldos[dueno_id]

    def debitar(self, dueno_id: str, centimos: int) -> int:
        """Resta [centimos] del saldo del dueño (nunca baja de 0) y devuelve el
        nuevo saldo. Se usa para cobrar la comisión de Pichangol de las reservas
        pagadas en efectivo (el jugador paga la cancha; PCG cobra del saldo)."""
        nuevo = max(0, self.saldos.get(dueno_id, 0) - int(centimos))
        self.saldos[dueno_id] = nuevo
        return nuevo

    def transferir_saldo(self, desde_id: str, hacia_id: str) -> int:
        """BILLETERA ÚNICA por usuario: mueve TODO el saldo prepago de [desde_id]
        a [hacia_id]. Se usa para consolidar el saldo que quedó bajo una llave
        secundaria (p. ej. el id de una academia) en la billetera del dueño (su
        correo). Idempotente: tras mover, [desde_id] queda en 0, así que re-llamar
        mueve 0. Devuelve el nuevo saldo de [hacia_id]. No registra un pago (no
        crea ni destruye recargas: el libro de márgenes no se altera)."""
        if not desde_id or not hacia_id or desde_id == hacia_id:
            return self.saldos.get(hacia_id, 0)
        # Re-apunta las suscripciones que cobraban de la llave secundaria para que
        # el cron de servicios siga debitando de la billetera del dueño (correo).
        # Corre SIEMPRE (aunque no haya saldo que mover): una sub puede existir
        # sin saldo actual y hay que reencaminar su cobro igual.
        for s in self.suscripciones.values():
            if s.get("dueno_id") == desde_id:
                s["dueno_id"] = hacia_id
        monto = self.saldos.get(desde_id, 0)
        if monto <= 0:
            return self.saldos.get(hacia_id, 0)
        self.saldos[desde_id] = 0
        self.saldos[hacia_id] = self.saldos.get(hacia_id, 0) + monto
        return self.saldos[hacia_id]

    def pago_por_charge(self, charge_id: str | None) -> "PagoRegistro | None":
        if not charge_id:
            return None
        for p in self.pagos:
            if p.culqi_charge_id == charge_id:
                return p
        return None

    def registrar_pago(self, **kw) -> "PagoRegistro":
        p = PagoRegistro(id=self.next_id("pago"), creado_en=ahora(), **kw)
        self.pagos.append(p)
        return p

    def borrar_cobros_matricula(self, academia_id: str | None = None) -> int:
        """PRUEBAS: elimina los cobros digitales de matrícula (tipo
        'matricula_online') del libro de pagos, para que el reporte del profe no
        arrastre registros de pruebas viejas tras 'Empezar de cero'. Si se pasa
        [academia_id], borra solo los de esa academia; si no, todos. Devuelve
        cuántos borró. No toca liquidaciones ni saldos."""
        antes = len(self.pagos)
        self.pagos = [
            p for p in self.pagos
            if not (p.tipo == "matricula_online"
                    and (academia_id is None or p.dueno_id == academia_id))
        ]
        return antes - len(self.pagos)

    def reiniciar_libro_pagos(self) -> int:
        """PRUEBAS: vacía TODO el libro de pagos (matrículas, reservas, recargas,
        servicios, liquidaciones). Deja el reporte de márgenes en cero para
        re-probar desde limpio. No toca saldos (se guardan aparte)."""
        n = len(self.pagos)
        self.pagos = []
        return n

    def reset_virgen(self) -> dict:
        """Deja el sistema VIRGEN conservando SOLO los reclamos de propiedad (para
        que las canchas sigan RECLAMADAS) y la config del operador. Borra todo lo
        transaccional del servidor: libro de pagos, saldos de billetera,
        suscripciones de servicios y de alumnos, tarjetas guardadas + customers de
        Culqi, y métricas de vistas. NO toca `reclamos` ni la config. Devuelve un
        conteo de lo borrado para confirmar."""
        conteo = {
            "pagos": len(self.pagos),
            "saldos": len(self.saldos),
            "suscripciones": len(self.suscripciones),
            "suscripciones_alumno": len(self.suscripciones_alumno),
            "metodos_pago": sum(len(v) for v in self.metodos.values()),
            "customers": len(self.customers),
            "vistas": len(self.vistas),
            "membresias_pro": len(self.membresias_pro),
            "retos": len(self.retos),
            "jugadores_circuito": len(self.jugadores_circuito),
        }
        self.pagos = []
        self.retos = []
        self.ventas = []
        self.saldos = {}
        self.suscripciones = {}
        self.suscripciones_alumno = {}
        self.metodo_suscripcion = {}
        self.metodos = {}
        self.customers = {}
        self.vistas = {}
        self.membresias_pro = {}
        self.jugadores_circuito = {}
        self.ranking_snapshot = {}
        # Se conservan: reclamos (propiedad), config/incentivos/modo del operador.
        return conteo

    def reset_billetera_de(self, dueno_id: str) -> dict:
        """Deja la BILLETERA de UN usuario como en PRD: saldo 0 y sin movimientos.
        Borra su saldo prepago y TODOS sus pagos (recargas, comisiones,
        liquidaciones "por recibir", suscripciones, etc.). Lo usa el APK al 'dejar
        en virgen' para que su billetera quede realmente vacía (el saldo/pagos
        viven en el backend y volverían al re-sincronizar). Solo toca al usuario
        que se manda; no afecta a otros. Devuelve cuánto borró."""
        clave = (dueno_id or "").strip().lower()
        if not clave:
            return {"saldo": 0, "pagos": 0}

        def _match(v: str | None) -> bool:
            return (v or "").strip().lower() == clave

        saldo_habia = 1 if clave in {k.strip().lower() for k in self.saldos} else 0
        # Quita el saldo (cualquier variante de caja del mismo correo).
        for k in [k for k in list(self.saldos) if _match(k)]:
            self.saldos.pop(k, None)
        antes = len(self.pagos)
        self.pagos = [p for p in self.pagos if not _match(p.dueno_id)]
        return {"saldo": saldo_habia, "pagos": antes - len(self.pagos)}

    def borrar_reclamos_de(self, solicitante: str) -> int:
        """Borra los reclamos de propiedad de un SOLICITANTE (por su correo/id).
        Lo usa el APK cuando el dueño 'deja en virgen' para que sus canchas
        reclamadas desaparezcan también de la torre de control (y pueda volver a
        reclamarlas de cero). Devuelve cuántos se borraron. Solo toca los del
        propio solicitante (no los de otros usuarios)."""
        clave = (solicitante or "").strip().lower()
        if not clave:
            return 0
        antes = len(self.reclamos)
        self.reclamos = [
            r for r in self.reclamos
            if (r.solicitante_id or "").strip().lower() != clave
        ]
        return antes - len(self.reclamos)

    def liquidaciones(self, dueno_id: str | None = None,
                      solo_pendientes: bool = False) -> "list[PagoRegistro]":
        """Liquidaciones (neto que Pichangol le debe al dueño): reservas online y
        ventas del marketplace. Filtra por dueño y/o solo las pendientes."""
        out = []
        for p in self.pagos:
            if p.tipo not in ("liquidacion_online", "liquidacion_full",
                              "venta_producto", "venta_bodega"):
                continue
            if p.estado != "aprobado":
                continue  # reembolsados/anulados no se liquidan
            if dueno_id is not None and p.dueno_id != dueno_id:
                continue
            if solo_pendientes and p.liquidado:
                continue
            out.append(p)
        return out

    def marcar_liquidacion_pagada(self, reserva_id: str, metodo: str | None,
                                  referencia: str | None) -> "PagoRegistro | None":
        """Marca una liquidación como PAGADA (Pichangol transfirió el neto al
        dueño). Idempotente: si ya estaba pagada, la devuelve igual."""
        for p in self.pagos:
            if (p.tipo in ("liquidacion_online", "liquidacion_full",
                           "venta_producto")
                    and p.culqi_charge_id == reserva_id):
                if not p.liquidado:
                    p.liquidado = True
                    p.liquidado_en = ahora()
                    p.metodo_liquidacion = metodo
                    p.referencia_liquidacion = referencia
                return p
        return None

    # --- vistas / impresiones de destacados (métrica de impacto del boost) ---
    def registrar_vista(self, id_: str, dia: str | None = None, n: int = 1) -> None:
        """Suma [n] impresiones a [id_] (dueno_id o academia_id) en [dia]
        (YYYY-MM-DD; por defecto hoy UTC)."""
        if not id_:
            return
        dia = dia or datetime.now(timezone.utc).date().isoformat()
        d = self.vistas.setdefault(id_, {})
        d[dia] = d.get(dia, 0) + int(n)

    def vistas_resumen(self, ids: list[str]) -> dict:
        """Impresiones agregadas de [ids]: total histórico y últimos 7 días."""
        hoy = datetime.now(timezone.utc).date()
        ventana = {(hoy - timedelta(days=i)).isoformat() for i in range(7)}
        total = 0
        semana = 0
        for id_ in ids:
            for dia, n in self.vistas.get(id_, {}).items():
                total += n
                if dia in ventana:
                    semana += n
        return {"semana": semana, "total": total}

    def migrar_suscripciones_legacy(self) -> int:
        """Unificación: renombra suscripciones del plan retirado 'gestion' a
        'redes' (Manejo de redes) para que aparezcan como activas en el catálogo
        nuevo. No pisa un 'redes' ya existente. Devuelve cuántas migró."""
        migradas = 0
        for key in list(self.suscripciones.keys()):
            s = self.suscripciones.get(key) or {}
            if s.get("servicio") != "gestion":
                continue
            aid = s.get("academia_id")
            s["servicio"] = "redes"
            destino = f"{aid}:redes"
            if destino not in self.suscripciones:
                self.suscripciones[destino] = s
            if key != destino:
                self.suscripciones.pop(key, None)
            migradas += 1
        return migradas

    def resolver_solapamiento_servicios(self) -> int:
        """Si una academia tiene 'presencia' (paquete) activa, cancela sus planes
        individuales 'landing'/'redes' activos (ya están incluidos). Evita doble
        cobro. Devuelve cuántas suscripciones canceló."""
        con_presencia = {
            s.get("academia_id")
            for s in self.suscripciones.values()
            if s.get("servicio") == "presencia"
            and s.get("estado") in ("activa", "pendiente_pago")
        }
        canceladas = 0
        for s in self.suscripciones.values():
            if (s.get("academia_id") in con_presencia
                    and s.get("servicio") in ("landing", "redes")
                    and s.get("estado") in ("activa", "pendiente_pago")):
                s["estado"] = "cancelada"
                canceladas += 1
        return canceladas

    def cancha(self, cancha_id: str) -> CanchaEstado:
        c = self.canchas.get(cancha_id)
        if c is None:
            c = CanchaEstado(cancha_id=cancha_id)
            self.canchas[cancha_id] = c
        return c

    # --- imágenes transitorias para publicar (hosting efímero) --------------
    def guardar_imagen(self, datos: bytes, content_type: str,
                       tope: int = 80) -> str:
        """Guarda una imagen en memoria y devuelve su id. Descarta las más
        viejas si se pasa el tope (dict conserva orden de inserción)."""
        img_id = f"{self.next_id('img')}"
        self.imagenes[img_id] = {"bytes": datos, "content_type": content_type}
        while len(self.imagenes) > max(1, tope):
            self.imagenes.pop(next(iter(self.imagenes)))
        return img_id

    def guardar_video(self, datos: bytes, content_type: str = "video/mp4",
                      tope: int = 6) -> str:
        """Guarda un video (reel) en memoria y devuelve su id. Tope bajo: los
        reels pesan, así que se conservan sólo los últimos pocos."""
        vid_id = f"{self.next_id('vid')}"
        self.videos[vid_id] = {"bytes": datos, "content_type": content_type}
        while len(self.videos) > max(1, tope):
            self.videos.pop(next(iter(self.videos)))
        return vid_id

    # --- idempotencia ---
    def idem_get(self, scope: str, key: str | None) -> dict | None:
        if not key:
            return None
        return self._idem.get((scope, key))

    def idem_set(self, scope: str, key: str | None, valor: dict) -> dict:
        if key:
            self._idem[(scope, key)] = valor
        return valor

    def reset(self) -> None:
        """Reinicia todo (para tests)."""
        self.__init__()

    # --- persistencia por snapshot (JSON) -----------------------------------
    def to_state(self) -> dict:
        """Serializa TODO el estado durable a un dict JSON-able."""
        return {
            "ids": dict(self._ids),
            "config": dict(self.config),
            "movimientos": [como_dict(m) for m in self.movimientos],
            "canjes": [como_dict(c) for c in self.canjes],
            "solicitudes": [como_dict(s) for s in self.solicitudes],
            "vfs": [como_dict(v) for v in self.verificaciones_fisicas],
            "verificadores": [como_dict(v) for v in self.verificadores],
            "canchas": {k: como_dict(v) for k, v in self.canchas.items()},
            "visitas_liquidacion": list(self.visitas_liquidacion),
            # OTPs NO se persisten (transitorios/seguridad). Sólo las decisiones.
            "confirmaciones_propiedad": [
                como_dict(c) for c in self.confirmaciones_propiedad
            ],
            "reclamos": [como_dict(r) for r in self.reclamos],
            "modo_aprobacion_overrides": dict(self.modo_aprobacion_overrides),
            "convocatorias": [como_dict(c) for c in self.convocatorias],
            "retos": [como_dict(r) for r in self.retos],
            "ventas": [como_dict(v) for v in self.ventas],
            "dni_verificados": dict(self.dni_verificados),
            "inscripciones": [como_dict(i) for i in self.inscripciones],
            "saldos": dict(self.saldos),
            "pagos": [como_dict(p) for p in self.pagos],
            "suscripciones": {k: dict(v) for k, v in self.suscripciones.items()},
            "landings": {k: dict(v) for k, v in self.landings.items()},
            "marketing_uso": {k: dict(v) for k, v in self.marketing_uso.items()},
            "cm": {k: dict(v) for k, v in self.cm.items()},
            "conexiones_redes": {k: dict(v) for k, v in self.conexiones_redes.items()},
            "vistas": {k: dict(v) for k, v in self.vistas.items()},
            "customers": dict(self.customers),
            "metodos": {k: list(v) for k, v in self.metodos.items()},
            "metodo_suscripcion": {k: dict(v) for k, v in self.metodo_suscripcion.items()},
            "suscripciones_alumno": {
                k: dict(v) for k, v in self.suscripciones_alumno.items()},
            "membresias_pro": {
                k: dict(v) for k, v in self.membresias_pro.items()},
            "libelula_deudas": {
                k: dict(v) for k, v in self.libelula_deudas.items()},
            "jugadores_circuito": {
                k: dict(v) for k, v in self.jugadores_circuito.items()},
            "ranking_snapshot": dict(self.ranking_snapshot),
            "recargas_qr": [dict(r) for r in self.recargas_qr],
            "cupones": {k: dict(v) for k, v in self.cupones.items()},
        }

    def load_state(self, data: dict) -> None:
        """Reconstruye el estado desde un snapshot (al arrancar)."""
        self.reset()
        self._ids = {k: int(v) for k, v in (data.get("ids") or {}).items()}
        self.config = {**CONFIG_DEFAULT, **(data.get("config") or {})}
        self.movimientos = [_mov_from(d) for d in data.get("movimientos", [])]
        self.canjes = [_canje_from(d) for d in data.get("canjes", [])]
        self.solicitudes = [_sol_from(d) for d in data.get("solicitudes", [])]
        self.verificaciones_fisicas = [_vf_from(d) for d in data.get("vfs", [])]
        self.verificadores = [Verificador(**d) for d in data.get("verificadores", [])]
        self.canchas = {
            k: CanchaEstado(**v) for k, v in (data.get("canchas") or {}).items()
        }
        self.visitas_liquidacion = list(data.get("visitas_liquidacion") or [])
        self.confirmaciones_propiedad = [
            _conf_from(d) for d in data.get("confirmaciones_propiedad", [])
        ]
        self.reclamos = [_reclamo_from(d) for d in data.get("reclamos", [])]
        self.modo_aprobacion_overrides = dict(
            data.get("modo_aprobacion_overrides") or {})
        self.convocatorias = [_conv_from(d) for d in data.get("convocatorias", [])]
        self.retos = [_reto_from(d) for d in data.get("retos", [])]
        self.ventas = [_venta_from(d) for d in data.get("ventas", [])]
        self.dni_verificados = {
            k: str(v) for k, v in (data.get("dni_verificados") or {}).items()}
        self.inscripciones = [_insc_from(d) for d in data.get("inscripciones", [])]
        self.saldos = {k: int(v) for k, v in (data.get("saldos") or {}).items()}
        self.pagos = [_pago_from(d) for d in data.get("pagos", [])]
        self.suscripciones = {
            k: dict(v) for k, v in (data.get("suscripciones") or {}).items()
        }
        self.landings = {
            k: dict(v) for k, v in (data.get("landings") or {}).items()
        }
        self.marketing_uso = {
            k: dict(v) for k, v in (data.get("marketing_uso") or {}).items()
        }
        self.cm = {k: dict(v) for k, v in (data.get("cm") or {}).items()}
        self.conexiones_redes = {
            k: dict(v) for k, v in (data.get("conexiones_redes") or {}).items()
        }
        self.vistas = {
            k: {d: int(n) for d, n in (v or {}).items()}
            for k, v in (data.get("vistas") or {}).items()
        }
        self.customers = dict(data.get("customers") or {})
        self.metodos = {
            k: list(v) for k, v in (data.get("metodos") or {}).items()
        }
        self.metodo_suscripcion = {
            k: dict(v) for k, v in (data.get("metodo_suscripcion") or {}).items()
        }
        self.suscripciones_alumno = {
            k: dict(v) for k, v in (data.get("suscripciones_alumno") or {}).items()
        }
        self.membresias_pro = {
            k: dict(v) for k, v in (data.get("membresias_pro") or {}).items()
        }
        self.libelula_deudas = {
            k: dict(v) for k, v in (data.get("libelula_deudas") or {}).items()
        }
        self.jugadores_circuito = {
            k: dict(v) for k, v in (data.get("jugadores_circuito") or {}).items()
        }
        self.ranking_snapshot = dict(data.get("ranking_snapshot") or {})
        self.recargas_qr = [dict(r) for r in data.get("recargas_qr", [])]
        self.cupones = {
            k: dict(v) for k, v in (data.get("cupones") or {}).items()
        }

    # --- normalización a TABLAS SQL (fase 1: saldos/pagos/vistas/reclamos) ----
    # Estas colecciones (plata + impacto + reclamos) migran a tablas propias en
    # Supabase (ver db/pg.py). Los mapeos van/vienen como filas simples y son
    # PUROS (testables sin BD). Las fechas se manejan como ISO (str), igual que
    # en el snapshot, para reusar los mismos parsers (`_pago_from`, etc.).
    def saldos_rows(self) -> list[tuple]:
        return [(k, int(v)) for k, v in self.saldos.items()]

    def cargar_saldos_rows(self, rows) -> None:
        self.saldos = {r[0]: int(r[1]) for r in rows}

    def pagos_rows(self) -> list[dict]:
        return [como_dict(p) for p in self.pagos]

    def cargar_pagos_rows(self, rows) -> None:
        self.pagos = [_pago_from(r) for r in rows]
        if self.pagos:  # mantiene el contador de ids coherente
            self._ids["pago"] = max(
                self._ids.get("pago", 0), max(p.id for p in self.pagos))

    def vistas_rows(self) -> list[tuple]:
        out: list[tuple] = []
        for id_, dias in self.vistas.items():
            for dia, n in dias.items():
                out.append((id_, dia, int(n)))
        return out

    def cargar_vistas_rows(self, rows) -> None:
        v: dict[str, dict[str, int]] = {}
        for id_, dia, n in rows:
            v.setdefault(id_, {})[str(dia)] = int(n)
        self.vistas = v

    def reclamos_rows(self) -> list[dict]:
        return [como_dict(r) for r in self.reclamos]

    def cargar_reclamos_rows(self, rows) -> None:
        self.reclamos = [_reclamo_from(r) for r in rows]
        if self.reclamos:
            self._ids["reclamo"] = max(
                self._ids.get("reclamo", 0), max(r.id for r in self.reclamos))


# Singleton (en producción: repos contra Supabase).
stores = Stores()


def seed_verificadores() -> None:
    """Carga verificadores de ejemplo si no hay (para demo/tests)."""
    if stores.verificadores:
        return
    ejemplos = [
        ("Ana Quispe", "lima_norte", "dedicado"),
        ("Luis Rojas", "lima_sur", "por_encargo"),
        ("Marta Díaz", "lima_este", "por_encargo"),
        ("Jorge León", "lima_moderna", "dedicado"),
        ("Rosa Mamani", "callao", "por_encargo"),
    ]
    for nombre, zona, tipo in ejemplos:
        stores.verificadores.append(Verificador(
            id=stores.next_id("verificador"), nombre=nombre, zona=zona, tipo=tipo))


def como_dict(obj) -> dict:
    """Serializa dataclasses con fechas a ISO."""
    d = asdict(obj)
    for k, v in d.items():
        if isinstance(v, datetime):
            d[k] = v.isoformat()
    return d


def _dt(s):
    return datetime.fromisoformat(s) if s else None


def _mov_from(d: dict) -> PuntosMovimiento:
    return PuntosMovimiento(
        id=d["id"], usuario_id=d["usuario_id"], accion=d["accion"],
        puntos=d["puntos"], estado=d["estado"], ref_tipo=d.get("ref_tipo"),
        ref_id=d.get("ref_id"), creado_en=_dt(d["creado_en"]),
        liberado_en=_dt(d.get("liberado_en")))


def _canje_from(d: dict) -> PremioCanje:
    return PremioCanje(
        id=d["id"], usuario_id=d["usuario_id"], puntos_usados=d["puntos_usados"],
        tipo_premio=d["tipo_premio"], vale_id=d["vale_id"],
        fuente_financiamiento=d["fuente_financiamiento"], estado=d["estado"],
        valor_soles=d["valor_soles"], creado_en=_dt(d["creado_en"]))


def _sol_from(d: dict) -> SolicitudCancha:
    return SolicitudCancha(
        id=d["id"], usuario_id=d["usuario_id"],
        nombre_cancha_libre=d["nombre_cancha_libre"],
        direccion_texto=d["direccion_texto"], lat=d.get("lat"), lng=d.get("lng"),
        distrito=d["distrito"], zona=d["zona"], estado=d["estado"],
        cancha_id=d.get("cancha_id"), creado_en=_dt(d["creado_en"]))


def _conf_from(d: dict) -> ConfirmacionPropiedad:
    return ConfirmacionPropiedad(
        id=d["id"], cancha_id=d["cancha_id"], solicitante_id=d["solicitante_id"],
        metodo=d["metodo"], estado=d["estado"],
        telefono_enmascarado=d.get("telefono_enmascarado"),
        creado_en=_dt(d["creado_en"]), decidido_en=_dt(d.get("decidido_en")),
        nota=d.get("nota"))


def _reclamo_from(d: dict) -> ReclamoPropiedad:
    return ReclamoPropiedad(
        id=d["id"], cancha_id=d["cancha_id"], solicitante_id=d["solicitante_id"],
        nombre_local=d["nombre_local"], codigo=d["codigo"], estado=d["estado"],
        creado_en=_dt(d["creado_en"]), telefono_contacto=d.get("telefono_contacto"),
        dni=d.get("dni"), nombre_titular=d.get("nombre_titular"),
        ruc=d.get("ruc"), razon_social=d.get("razon_social"),
        relacion=d.get("relacion"),
        lat=d.get("lat"), lng=d.get("lng"),
        solicitante_lat=d.get("solicitante_lat"),
        solicitante_lng=d.get("solicitante_lng"),
        decidido_en=_dt(d.get("decidido_en")),
        validado_en=_dt(d.get("validado_en")), validador=d.get("validador"),
        nota=d.get("nota"), solicitante_nombre=d.get("solicitante_nombre", ""),
        foto_evidencia_url=d.get("foto_evidencia_url", ""),
        nota_reclamante=d.get("nota_reclamante", ""))


def _conv_from(d: dict) -> Convocatoria:
    return Convocatoria(
        id=d["id"], club_id=d["club_id"], titulo=d["titulo"],
        deporte=d["deporte"], cupos=d["cupos"], estado=d["estado"],
        creado_en=_dt(d["creado_en"]), categoria=d.get("categoria"),
        fecha_partido=d.get("fecha_partido"), apertura=_dt(d.get("apertura")),
        cierre=_dt(d.get("cierre")), modo_asignacion=d.get("modo_asignacion"),
        semilla=d.get("semilla"), creado_por=d.get("creado_por", ""),
        cerrado_en=_dt(d.get("cerrado_en")))


def _reto_from(d: dict) -> Reto:
    return Reto(
        id=d["id"], retador_email=d["retador_email"],
        retador_nombre=d.get("retador_nombre", ""),
        retado_email=d["retado_email"], retado_nombre=d.get("retado_nombre", ""),
        deporte=d.get("deporte", ""), creado_en=_dt(d["creado_en"]),
        zona=d.get("zona", ""), estado=d.get("estado", "pendiente"),
        ganador_email=d.get("ganador_email", ""), marcador=d.get("marcador", ""),
        mensaje=d.get("mensaje", ""), jugado_en=_dt(d.get("jugado_en")),
        reportado_por=d.get("reportado_por", ""),
        reportado_en=_dt(d.get("reportado_en")),
        auto_confirmado=bool(d.get("auto_confirmado", False)),
        modalidad=d.get("modalidad", "singles"),
        retador2_email=d.get("retador2_email", ""),
        retador2_nombre=d.get("retador2_nombre", ""),
        retado2_email=d.get("retado2_email", ""),
        retado2_nombre=d.get("retado2_nombre", ""))


def _venta_from(d: dict) -> Venta:
    return Venta(
        id=d["id"], producto_id=d.get("producto_id", ""),
        producto_nombre=d.get("producto_nombre", ""),
        comprador_email=d.get("comprador_email", ""),
        comprador_nombre=d.get("comprador_nombre", ""),
        vendedor_email=d.get("vendedor_email", ""),
        vendedor_nombre=d.get("vendedor_nombre", ""),
        monto_soles=float(d.get("monto_soles", 0) or 0),
        creado_en=_dt(d["creado_en"]), estado=d.get("estado", "pagado"),
        entregado_en=_dt(d.get("entregado_en")),
        recibido_en=_dt(d.get("recibido_en")),
        auto_liberado=bool(d.get("auto_liberado", False)))


def _pago_from(d: dict) -> PagoRegistro:
    return PagoRegistro(
        id=d["id"], tipo=d["tipo"], monto_centimos=int(d["monto_centimos"]),
        moneda=d.get("moneda", "PEN"), estado=d["estado"],
        creado_en=_dt(d["creado_en"]), dueno_id=d.get("dueno_id"),
        culqi_charge_id=d.get("culqi_charge_id"), email=d.get("email"),
        concepto=d.get("concepto"),
        comision_centimos=int(d.get("comision_centimos", 0)),
        liquidado=bool(d.get("liquidado", False)),
        liquidado_en=_dt(d.get("liquidado_en")),
        metodo_liquidacion=d.get("metodo_liquidacion"),
        referencia_liquidacion=d.get("referencia_liquidacion"),
        medio=d.get("medio"))


def _insc_from(d: dict) -> Inscripcion:
    return Inscripcion(
        id=d["id"], convocatoria_id=d["convocatoria_id"],
        socio_id=d["socio_id"], socio_nombre=d["socio_nombre"],
        estado=d["estado"], creado_en=_dt(d["creado_en"]),
        posicion=d.get("posicion"), asistio=d.get("asistio"))


def _vf_from(d: dict) -> VerificacionFisica:
    return VerificacionFisica(
        id=d["id"], cancha_id=d["cancha_id"], solicitud_id=d.get("solicitud_id"),
        motivo=d["motivo"], verificador_id=d.get("verificador_id"),
        estado=d["estado"], fotos_geo_urls=list(d.get("fotos_geo_urls") or []),
        lat_sitio=d.get("lat_sitio"), lng_sitio=d.get("lng_sitio"),
        firma_verificador=d.get("firma_verificador"),
        observaciones=d.get("observaciones"), metodo=d.get("metodo"),
        creado_en=_dt(d["creado_en"]), cerrada_en=_dt(d.get("cerrada_en")))
