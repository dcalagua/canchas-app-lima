# Push "¡Tu cancha fue aprobada!" — despliegue (una vez)

Cuando el operador aprueba un reclamo en la torre de control, el backend growth
(Railway) le pega a una Edge Function de Supabase que envía el FCM al reclamante.
El backend growth **no hace FCM** (por eso se delega en Supabase, igual que
`push-reserva`).

## 1) Desplegar la Edge Function (desde la laptop)

```bash
# En la raíz del repo, con la Supabase CLI ya logueada al proyecto de Pichangol:
supabase functions deploy push-aprobacion --project-ref <TU_PROJECT_REF>
```

Reutiliza los secrets que ya tienen `push-reserva`/`push-mensaje`
(`FCM_SERVICE_ACCOUNT`; `SUPABASE_URL` y `SUPABASE_SERVICE_ROLE_KEY` los inyecta
Supabase). **Opcional pero recomendado** — un secreto compartido para que solo el
backend growth pueda disparar la función:

```bash
supabase secrets set PUSH_APROBACION_SECRET=<un-secreto-largo-al-azar> \
  --project-ref <TU_PROJECT_REF>
```

La URL de la función queda así (anótala):
`https://<TU_PROJECT_REF>.functions.supabase.co/push-aprobacion`

## 2) Variables en Railway (servicio `pg-backend`)

En Railway → `pg-backend` → Variables, agrega:

| Variable | Valor |
|---|---|
| `PUSH_APROBACION_URL` | `https://<TU_PROJECT_REF>.functions.supabase.co/push-aprobacion` |
| `PUSH_APROBACION_SECRET` | el **mismo** secreto del paso 1 (si lo pusiste) |

Al guardar, Railway redespliega el backend. Si `PUSH_APROBACION_URL` queda vacío,
no se envía nada (fail-safe) — todo lo demás sigue igual.

## 3) Probar

1. Con un usuario logueado, reclama una cancha (queda "Por verificar").
2. Aprueba ese reclamo en el panel `/admin` (o "Reclamos (admin)" en la app, o
   respondiendo `APROBAR <código>` por WhatsApp).
3. Al reclamante le debe llegar el push **"¡Cancha aprobada! ✅"**; al tocarlo,
   abre **Mis canchas** (ya sin el cartel "pendiente", con reservas habilitadas).

> Requiere que el reclamante tenga token de push registrado
> (`pichangol_push_tokens`) — se registra solo al abrir la app con sesión.
