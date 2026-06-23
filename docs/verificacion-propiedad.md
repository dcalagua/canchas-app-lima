# Verificación de PROPIEDAD (no de existencia)

## El problema que resuelve

Antes, reclamar una cancha con un **RUC válido** la marcaba como verificada y
convertía al reclamante en dueño. Eso es inseguro: un RUC sólo prueba que el
**local existe** (está en SUNAT), no que **tú** lo controles. Cualquiera podía
copiar un RUC público y "adueñarse" de una cancha.

> **Existencia ≠ propiedad.** Son dos chequeos distintos y se confirman por caminos
> distintos.

| | Pregunta | Cómo se prueba | Habilita reservas |
|---|---|---|---|
| Existencia | ¿El local es real? | RUC en SUNAT, Google Places, IA | No |
| **Propiedad** | ¿Tú controlas el local? | **OTP al teléfono del local**, visita física, aprobación manual | **Sí** |

## Cómo quedó el flujo

1. **Registrar / reclamar** una cancha → queda `verificada: false`
   ("en revisión de propiedad"). Se dispara la verificación de **existencia** en
   segundo plano (informativa), pero **nunca** marca la cancha como verificada.
2. En **Mis canchas**, la cancha pendiente muestra el botón **"Verificar propiedad"**.
3. Ese botón abre el flujo de **OTP por WhatsApp**:
   - El dueño ingresa el **teléfono del local**.
   - El backend (`POST /propiedad/otp/solicitar`) genera un código de 6 dígitos y lo
     envía por WhatsApp Cloud API a ese número.
   - El dueño ingresa el código (`POST /propiedad/otp/confirmar`).
   - Si coincide → la cancha pasa a `verificada: true` y **recién ahí acepta reservas**.
4. **Aprobación manual** (`POST /propiedad/aprobar-manual`): para casos sin teléfono o
   en disputa, el equipo de Pichangol confirma/rechaza a mano.
5. **Visita física** (carril del Verificador, ya existente): también confirma
   propiedad presencialmente (es la categoría PLUS).

### Anti-fraude del OTP

Leer un código prueba que controlas **ese teléfono**, no que seas el dueño. Por eso:

- Si el número del OTP **coincide** con el teléfono público del local (el que trajo
  Google Places / redes), el OTP basta → `confirmada`.
- Si **no hay** teléfono público con el cual contrastar, el OTP exitoso deja la
  solicitud en `pendiente_revision` (aprobación manual ligera), evitando que alguien
  ponga su propio número y se autoadjudique el local.

### Privacidad (Ley 29733 / DS 016-2024-JUS)

- El código se guarda **sólo como hash** (HMAC-SHA256) con **TTL de 5 min** y se
  **borra al usarse o vencer**. Nunca se persiste en la base.
- El teléfono completo no se almacena: en el registro auditable queda **enmascarado**
  (`•••••4321`).
- Las fotos de verificación física son **del establecimiento**, nunca documentos
  personales (ni DNI ni recibos).

### Canales de OTP (multicanal)

El backend elige el canal automáticamente:

1. **WhatsApp Cloud API** (principal) — ver `docs/whatsapp-cloud-api-setup.md`.
2. **SMS por Twilio** (alternativa/respaldo, no depende de Meta) — ver
   `docs/twilio-sms-otp-setup.md`.
3. **Stub** (sin envío real) si no hay ninguno configurado.

Preferencia configurable con `OTP_CANAL_PREFERIDO` (`whatsapp` | `sms`). Si el canal
preferido no está disponible, cae al otro. `GET /propiedad/canal` informa cuál está
activo.

## Endpoints (backend/growth, módulo `propiedad`)

```
GET  /propiedad/canal                 -> {whatsapp: bool}  (¿está configurado?)
GET  /propiedad/estado/{cancha_id}    -> estado de propiedad
POST /propiedad/otp/solicitar         {cancha_id, telefono}
POST /propiedad/otp/confirmar         {cancha_id, codigo, solicitante_id, telefono_publico?}
POST /propiedad/aprobar-manual        {cancha_id, solicitante_id, aprobado, revisor?, nota?}
```

Config por entorno: ver `docs/whatsapp-cloud-api-setup.md` y `backend/growth/config.py`
(`WHATSAPP_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_OTP_TEMPLATE`,
`OTP_TTL_SEG`, `OTP_MAX_INTENTOS`, `OTP_REENVIO_MIN_SEG`).

---

## Roadmap: biometría (a madurar, NO para este sprint)

La idea de "el que registra se toma una selfie biométrica y el sistema valida" es
potente pero hay que diseñarla con cuidado. Recomendaciones:

### Qué SÍ resuelve la biometría
- **Liveness + identidad de la persona**: que detrás de la cuenta hay un humano real y
  no un bot/perfil falso (anti–multicuenta y anti–suplantación de la *persona*).

### Qué NO resuelve por sí sola
- **No prueba propiedad del local.** Una selfie válida no dice que esa persona sea la
  dueña de la cancha. La biometría es un factor de *identidad de persona*, no de
  *titularidad del negocio*. Debe combinarse con OTP al teléfono del local, contrato/
  recibo, o visita física.

### Diseño propuesto (cuando se aborde)
1. **Capa 1 – Identidad (biometría):** selfie con **prueba de vida** (parpadeo/giro) +
   match contra el documento. Proveedores en LATAM/Perú: **Reconoce-ID, Truora,
   Jumio, Onfido, AWS Rekognition Liveness**. Idealmente con cotejo **RENIEC** vía un
   agregador autorizado.
2. **Capa 2 – Titularidad (la que da el control):** OTP al teléfono del local +
   coincidencia con el teléfono público, o documento del negocio, o visita.
3. **Capa 3 – Riesgo:** un score combina ambas; alto valor / disputa → visita física
   obligatoria.

### Cuidados legales y de UX
- **Dato sensible:** la biometría es **dato sensible** bajo la Ley 29733 → exige
  **consentimiento explícito**, finalidad acotada, y de preferencia **no retener** la
  plantilla biométrica (usar verificación *on-device* o un proveedor que devuelva sólo
  "match/no-match" y borre la imagen).
- **Inclusión:** muchos dueños informales pueden tener equipos de gama baja o
  desconfiar de la selfie → la biometría debe ser **opcional/alternativa**, nunca el
  único camino. El OTP + visita cubren a todos.
- **Costo:** las verificaciones biométricas se cobran por transacción; reservarlas
  para casos de **alto valor o disputa**, no para cada registro.

### Recomendación de secuencia
1. **Ahora:** OTP WhatsApp + aprobación manual + visita física (ya implementado).
2. **Después:** biometría de **identidad de persona** como factor *adicional* para
   subir el nivel de confianza y reducir multicuentas, integrada con un proveedor con
   liveness y, si es posible, cotejo RENIEC, siempre con consentimiento y no-retención.
