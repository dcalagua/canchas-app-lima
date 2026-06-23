# WhatsApp Cloud API — guía paso a paso (OTP de propiedad)

Esta guía te lleva desde cero hasta tener las **3 credenciales** que el backend
necesita para enviar el código OTP que confirma al dueño de una cancha:

- `WHATSAPP_TOKEN` (token permanente de un *System User*)
- `WHATSAPP_PHONE_NUMBER_ID` (ID del número emisor)
- `WHATSAPP_OTP_TEMPLATE` (nombre de la plantilla de autenticación aprobada)

> Tiempo aproximado: 30–45 min. Necesitas una cuenta de Facebook y, para producción,
> un número de teléfono propio para WhatsApp Business (no tu WhatsApp personal).

---

## Paso 0 — Cuenta de empresa (Meta Business)

1. Entra a **https://business.facebook.com** con tu cuenta de Facebook.
2. Crea un **Portafolio comercial** (Business portfolio): nombre "EBIM" o "Pichangol",
   correo `dcalagua@ebim.pe`.
3. (Opcional ahora, obligatorio para escalar) **Verificación del negocio**:
   *Configuración del negocio → Centro de seguridad → Verificar*. Te pedirán datos
   de la empresa (RUC/partida) y un documento. Sin verificar puedes usar el número
   de prueba; para enviar a muchos números reales hay que verificar.

## Paso 1 — Crear la app en Meta for Developers

1. Entra a **https://developers.facebook.com** → arriba a la derecha **My Apps**.
2. **Create App**.
3. Caso de uso: elige **Other** → tipo **Business**.
4. Nombre de la app: `Pichangol`. Correo de contacto: `dcalagua@ebim.pe`.
   Asóciala al **Portafolio comercial** del Paso 0.
5. Create App (te pedirá tu contraseña de Facebook).

## Paso 2 — Agregar el producto WhatsApp

1. En el panel de la app: **Add products** → busca **WhatsApp** → **Set up**.
2. Selecciona la cuenta de WhatsApp Business (se crea una por defecto: *WhatsApp
   Business Account*, o **WABA**).
3. Meta te muestra la pantalla **API Setup** (o "Comenzar"). Aquí ya tienes, gratis:
   - Un **número de prueba** (de Meta) para emitir.
   - El **Phone number ID** → guárdalo, es tu `WHATSAPP_PHONE_NUMBER_ID`.
   - El **WhatsApp Business Account ID** (WABA ID).
   - Un **token temporal** (dura 24 h) — sirve sólo para probar.

## Paso 3 — Probar el envío (número de prueba)

1. En **API Setup**, sección "To", agrega tu propio celular como **destinatario de
   prueba** (hasta 5 números). Te llega un código para validarlo.
2. Copia el `curl` de ejemplo que muestra Meta (envía la plantilla `hello_world`) y
   córrelo. Si te llega el WhatsApp, el canal funciona.

```bash
curl -X POST \
  "https://graph.facebook.com/v21.0/<PHONE_NUMBER_ID>/messages" \
  -H "Authorization: Bearer <TOKEN_TEMPORAL>" \
  -H "Content-Type: application/json" \
  -d '{
    "messaging_product": "whatsapp",
    "to": "519XXXXXXXX",
    "type": "template",
    "template": { "name": "hello_world", "language": { "code": "en_US" } }
  }'
```

## Paso 4 — Crear la plantilla de **autenticación** (OTP)

Los OTP **deben** ir en una plantilla de categoría *Authentication* (Meta no deja
mandar códigos en texto libre).

1. Entra a **WhatsApp Manager** → **https://business.facebook.com/wa/manage/message-templates**
   (o desde el panel de la app: WhatsApp → *Message Templates*).
2. **Create template**:
   - **Category:** `Authentication`.
   - **Name:** `pichangol_otp`  → este es tu `WHATSAPP_OTP_TEMPLATE`.
   - **Languages:** Español (`es`). (Si eliges otro código, ajústalo en
     `WHATSAPP_OTP_LANG`.)
3. En el contenido, activa el formato estándar de OTP:
   - Cuerpo con el código (variable `{{1}}`).
   - Botón **Copy code** (one-time passcode). Nuestro backend ya manda el código
     tanto en el body como en el botón, así que con el formato por defecto basta.
4. **Submit**. Meta la revisa (suele tardar minutos a unas horas). Cuando quede en
   estado **Approved**, ya se puede usar.

> Importante: el `language.code` del backend (`WHATSAPP_OTP_LANG`, por defecto `es`)
> debe coincidir con el idioma de la plantilla aprobada, o el envío falla.

## Paso 5 — Token permanente (System User)

El token de 24 h no sirve para producción. Genera uno que no expira:

1. **business.facebook.com** → **Configuración del negocio** (Business Settings).
2. **Usuarios → Usuarios del sistema** (System Users) → **Agregar**.
   - Nombre: `pichangol-bot`. Rol: **Admin** (o Empleado con acceso a la app).
3. Con el usuario del sistema creado: **Agregar activos** → **Apps** → selecciona
   `Pichangol` → permiso **Control total**.
4. También **Agregar activos** → **Cuentas de WhatsApp** → tu WABA → **Control total**.
5. Botón **Generar token (token nuevo)**:
   - App: `Pichangol`.
   - Caducidad: **Nunca** (o 60 días si prefieres rotarlo).
   - Permisos: marca **`whatsapp_business_messaging`** y
     **`whatsapp_business_management`**.
6. **Generar** y **copia el token** (no se vuelve a mostrar) → este es tu
   `WHATSAPP_TOKEN`.

## Paso 6 — (Producción) Agregar tu número propio

El número de prueba sólo manda a los 5 destinatarios verificados. Para enviar a
cualquier dueño:

1. WhatsApp → **API Setup** → **Add phone number**.
2. Registra un número que **no** esté en uso en la app de WhatsApp normal (puede ser
   un chip nuevo o un fijo con verificación por llamada).
3. Verifícalo por SMS/llamada y ponle nombre visible ("Pichangol").
4. Ese número te da un nuevo **Phone number ID** → usa ese en
   `WHATSAPP_PHONE_NUMBER_ID` para producción.

---

## Paso 7 — Cargar los secrets en Railway (servicio `pg-backend`)

En Railway → proyecto → servicio **pg-backend** → **Variables** → agrega:

| Variable | Valor |
|---|---|
| `WHATSAPP_TOKEN` | el token permanente del Paso 5 |
| `WHATSAPP_PHONE_NUMBER_ID` | el Phone number ID (Paso 2 o 6) |
| `WHATSAPP_OTP_TEMPLATE` | `pichangol_otp` |
| `WHATSAPP_OTP_LANG` | `es` |
| `WHATSAPP_API_VERSION` | `v21.0` (opcional) |

Guarda y Railway redeploya. Verifica el canal:

```bash
curl https://pg-backend-production-c176.up.railway.app/propiedad/canal
# -> {"whatsapp": true}  cuando el token está cargado
```

Mientras `WHATSAPP_TOKEN` esté vacío, el backend corre en **modo stub**: no envía
nada real y, sólo si `OTP_DEBUG_DEVOLVER_CODIGO=1`, devuelve el código en la
respuesta para poder probar el flujo en la app sin gastar mensajes.

---

## Costos (referencia)

- Las **conversaciones de autenticación** se cobran por conversación iniciada por la
  empresa; en Perú el precio es bajo y hay un tramo gratuito mensual. Revisa la
  tarifa vigente en *WhatsApp Manager → Insights / Facturación*.
- Para facturar necesitas un **método de pago** en la cuenta de WhatsApp Business.

## Errores comunes

- **(#132001) Template name does not exist**: el `name`/`language` no coincide con la
  plantilla aprobada, o aún está *Pending*.
- **(#131030) Recipient not in allowed list**: estás con el número de prueba y el
  destinatario no está en los 5 verificados → agrega el número o pasa a producción.
- **(#190) Token expired**: usaste el token temporal de 24 h → usa el del System User.
- **403 / permisos**: al System User le faltan `whatsapp_business_messaging` o el
  activo (app/WABA) no está asignado.
