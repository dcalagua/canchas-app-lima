# Push de retos P2P (canal de avisos genérico)

Cuando un jugador **reta** a otro, **acepta** un reto o **reporta** el resultado,
el otro jugador recibe una **notificación push**. Además, dentro de la app hay un
**badge** (contador verde) en el perfil que avisa aunque el push no llegue.

## Por qué un canal aparte
Los retos viven en el **backend growth** (Railway), no en Supabase. El push del
chat (`push-mensaje`) se dispara por inserts en tablas de Supabase, así que no
cubre los retos. Este canal genérico (`pichangol_avisos` → `push-aviso`) cierra
ese hueco y **reusa la misma cuenta de servicio FCM** del chat.

## Cómo funciona
1. El APK que hace la acción inserta una fila en `pichangol_avisos`
   (`email` del destinatario + `titulo` + `cuerpo` + `data`). Lo hace
   `AvisosService` (`lib/services/avisos_service.dart`), **fail-safe**.
2. Un Database Webhook (INSERT) llama a la Edge Function `push-aviso`.
3. `push-aviso` busca los tokens del correo en `pichangol_push_tokens` y envía la
   notificación FCM a cada dispositivo.

El **badge in-app** no depende de nada de esto: `AppState.cargarRetosPendientes()`
consulta el backng growth al abrir la app / la pestaña Perfil y pinta el contador.

## Pasos (una vez, en Supabase)

### 1) Crear la tabla
SQL Editor → pega y corre `docs/piloto/supabase_avisos.sql`.

### 2) Secret de Firebase (si no está ya)
Edge Functions → **Secrets** → `FCM_SERVICE_ACCOUNT` = JSON de la cuenta de
servicio de Firebase. **Es el mismo** que usan `push-mensaje` / `push-matricula`:
si el chat ya notifica, este secret ya está puesto.

### 3) Desplegar la función
```bash
supabase functions deploy push-aviso --project-ref <TU_PROJECT_REF>
```

### 4) Crear el Database Webhook
Database → **Webhooks → Create a new hook**:
- **Name:** `push-aviso`
- **Table:** `public.pichangol_avisos`
- **Events:** solo **Insert**
- **Type:** Supabase Edge Functions → **push-aviso**
- **Method:** POST (por defecto)
- Guardar.

## Probar
1. Instala el APK e inicia sesión con **dos cuentas** en dos teléfonos (así ambas
   registran token en `pichangol_push_tokens`).
2. Con la cuenta A, abre **Ranking Global → toca a la cuenta B → Retar**.
3. El teléfono de B debe recibir el push **"¡Te retaron!"** y, al abrir la app,
   ver el **badge** en Perfil → "Mis retos".
4. B acepta → A recibe **"¡Reto aceptado!"**. Al reportar el resultado, el otro
   recibe **"Resultado del reto"**.

Si no llega el push (el badge sí debería):
- Edge Functions → **Logs → push-aviso** (muestra si encontró tokens).
- Verifica que el destinatario tenga fila en `pichangol_push_tokens` (se crea al
  iniciar sesión; en iOS pide permiso de notificaciones).
- El badge funciona igual sin push: es el respaldo in-app.
