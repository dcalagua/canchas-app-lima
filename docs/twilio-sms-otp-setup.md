# Twilio — OTP por SMS (alternativa/respaldo a WhatsApp)

Sirve para enviar el código de verificación de **propiedad** por **SMS**, sin
depender de Meta/WhatsApp. Útil mientras la cuenta de Meta está en revisión, o como
respaldo permanente si WhatsApp falla.

El backend ya es **multicanal**. Orden de canales (cae al siguiente disponible):
1. `whatsapp` — WhatsApp Cloud API de Meta.
2. `twilio_whatsapp` — **WhatsApp vía Twilio** (sandbox o número aprobado), NO depende
   de la aprobación de Meta → ideal para probar hoy.
3. `sms` — SMS vía Twilio.
4. `stub` — sin envío real.

La preferencia se controla con `OTP_CANAL_PREFERIDO`
(`whatsapp` | `twilio_whatsapp` | `sms`).

---

## Opción A (recomendada para probar HOY): WhatsApp Sandbox de Twilio

No requiere aprobación de Meta. Limitación: en el sandbox, **cada destinatario debe
unirse una vez** enviando una palabra clave por WhatsApp al número del sandbox (sirve
para pruebas con tu equipo; para producción real se usa WhatsApp Cloud de Meta o un
número de WhatsApp aprobado en Twilio).

1. En la Console: **Messaging → Try it out → Send a WhatsApp message**.
2. Verás el **número del sandbox** (normalmente `+1 415 523 8886`) y una **palabra de
   unión** tipo `join <dos-palabras>`.
3. Desde **tu WhatsApp**, envía ese `join <dos-palabras>` al número del sandbox. Te
   responde "conectado". (Cada tester hace lo mismo con su celular.)
4. Carga en Railway (`pg-backend`):

   | Variable | Valor |
   |---|---|
   | `TWILIO_ACCOUNT_SID` | tu Account SID (`AC...`) |
   | `TWILIO_AUTH_TOKEN` | tu Auth Token |
   | `TWILIO_WHATSAPP_FROM` | número del sandbox, ej. `+14155238886` |
   | `OTP_CANAL_PREFERIDO` | `twilio_whatsapp` |

5. Verifica:

   ```bash
   curl https://pg-backend-production-c176.up.railway.app/propiedad/canal
   # -> {"whatsapp": false, "twilio_whatsapp": true, "sms": false, "activo": "twilio_whatsapp"}
   ```

> El OTP llegará por WhatsApp al celular que se unió al sandbox. Cuando Meta apruebe tu
> cuenta, pasas a `OTP_CANAL_PREFERIDO=whatsapp` y ya no hace falta el "join".

---

## Opción B: SMS por Twilio

## Paso a paso

1. Crea una cuenta en **https://www.twilio.com/try-twilio** (el trial regala saldo).
2. En la **Console** (https://console.twilio.com) verás en el panel principal:
   - **Account SID** → `TWILIO_ACCOUNT_SID`
   - **Auth Token** (clic en "Show") → `TWILIO_AUTH_TOKEN`
3. Consigue un **remitente**. Dos opciones:
   - **Número Twilio**: *Phone Numbers → Buy a number* (elige uno con capacidad SMS).
     Ese número (formato `+1...`) va en `TWILIO_FROM`.
   - **Messaging Service** (recomendado para producción): *Messaging → Services →
     Create*. El SID (`MG....`) va en `TWILIO_MESSAGING_SERVICE_SID` (tiene prioridad
     sobre `TWILIO_FROM`).
4. **Trial:** Twilio solo deja enviar a números **verificados**. Agrega tu celular en
   *Phone Numbers → Verified Caller IDs*. Para enviar a cualquier dueño, sal del trial
   (upgrade) — en Perú conviene un Messaging Service.

## Secrets en Railway (servicio `pg-backend`)

| Variable | Valor |
|---|---|
| `TWILIO_ACCOUNT_SID` | tu Account SID (`AC...`) |
| `TWILIO_AUTH_TOKEN` | tu Auth Token |
| `TWILIO_FROM` | número Twilio `+1...` (si no usas Messaging Service) |
| `TWILIO_MESSAGING_SERVICE_SID` | `MG...` (opcional, recomendado) |
| `OTP_CANAL_PREFERIDO` | `sms` (mientras WhatsApp no esté listo) |

Verifica el canal activo:

```bash
curl https://pg-backend-production-c176.up.railway.app/propiedad/canal
# -> {"whatsapp": false, "twilio_whatsapp": false, "sms": true, "activo": "sms"}
```

## Consideraciones (Perú)

- **Costo:** el SMS internacional/peruano se cobra por mensaje (más caro que WhatsApp).
  Por eso WhatsApp sigue siendo el canal principal cuando Meta lo habilite.
- **Entregabilidad:** algunos operadores filtran SMS de remitentes nuevos. Un
  **Messaging Service** mejora la tasa de entrega.
- **Alfanumérico:** Perú no siempre soporta Sender ID alfanumérico; usa número o
  Messaging Service.

## Cuando Meta apruebe WhatsApp

Carga los secrets de WhatsApp (ver `docs/whatsapp-cloud-api-setup.md`) y pon
`OTP_CANAL_PREFERIDO=whatsapp`. El backend usará WhatsApp como principal y Twilio
queda como respaldo automático si WhatsApp no estuviera disponible.
