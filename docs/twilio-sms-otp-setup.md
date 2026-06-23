# Twilio — OTP por SMS (alternativa/respaldo a WhatsApp)

Sirve para enviar el código de verificación de **propiedad** por **SMS**, sin
depender de Meta/WhatsApp. Útil mientras la cuenta de Meta está en revisión, o como
respaldo permanente si WhatsApp falla.

El backend ya es **multicanal**: si `WHATSAPP_TOKEN` está configurado usa WhatsApp;
si no, usa Twilio SMS; si ninguno, corre en modo stub. La preferencia se controla con
`OTP_CANAL_PREFERIDO` (`whatsapp` por defecto, o `sms`).

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
# -> {"whatsapp": false, "sms": true, "activo": "sms"}
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
