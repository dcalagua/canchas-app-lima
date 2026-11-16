# Push al profe cuando le escriben por el chat interno

El código ya está listo (`supabase/functions/push-mensaje/index.ts`). Para que
llegue la notificación al profe cuando un alumno/interesado le escribe por el
**chat del app**, falta activarlo en Supabase (una sola vez).

## Qué hace
Cuando entra un mensaje nuevo en la tabla `pichangol_mensajes`, Supabase llama a
la Edge Function `push-mensaje`, que:
- decide el destinatario (si escribió el alumno → el **dueño/profe** de la
  academia; si escribió el profe → el **alumno**),
- busca sus tokens FCM en `pichangol_push_tokens`,
- envía la notificación a cada dispositivo.

## Pasos (una vez)

### 1) Secret de Firebase (si no está ya)
Supabase → **Edge Functions → Secrets** → agrega:
- `FCM_SERVICE_ACCOUNT` = el JSON de la cuenta de servicio de Firebase (el mismo
  que usa `push-matricula`). Si `push-matricula` ya notifica, este secret ya está.

### 2) Desplegar la función
Con la CLI de Supabase (o el dashboard):
```bash
supabase functions deploy push-mensaje --project-ref <TU_PROJECT_REF>
```
(Si `push-matricula` ya está desplegada, es el mismo comando cambiando el nombre.)

### 3) Crear el Database Webhook (lo que falta y no está en código)
Supabase → **Database → Webhooks → Create a new hook**:
- **Name:** `push-mensaje`
- **Table:** `public.pichangol_mensajes`
- **Events:** solo **Insert**
- **Type:** Supabase Edge Functions → **push-mensaje**
- **Method:** POST (por defecto)
- Guardar.

> Nota: ya debería existir un webhook equivalente para `pichangol_matriculas` →
> `push-matricula`. Este es el gemelo para el chat.

## Probar
1. Instala el APK y **inicia sesión** con la cuenta del profe en un teléfono
   (así se registra su token en `pichangol_push_tokens`).
2. Desde OTRA cuenta (alumno/interesado), abre la academia → **"Escríbele al
   profe"** y envía un mensaje.
3. El teléfono del profe debe recibir la notificación push.

Si no llega:
- Revisa **Edge Functions → Logs → push-mensaje** (ahí se ve el destinatario y si
  encontró tokens).
- Verifica que el profe tenga fila en `pichangol_push_tokens` (se crea al iniciar
  sesión; en iOS pide permiso de notificaciones).
