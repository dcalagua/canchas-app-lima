# Pagos con Culqi — configuración (Fase 2, piloto)

Módulo `backend/growth/pagos/` (FastAPI). Modelo **inDrive**: lo único que mueve
plata real es la **recarga del dueño** (va a la cuenta Pichangol) y, en saldo
cero, el **fee de reserva** al jugador. Sin split a terceros → sin fricción de
agregador. La llave **secreta** vive sólo aquí (Railway), nunca en el APK.

## 1) Variables de entorno en Railway (servicio `pg-backend`)

| Variable | Valor | Notas |
|---|---|---|
| `CULQI_SECRET_KEY` | `sk_test_...` (luego `sk_live_...`) | **Secreta**. Sólo en el backend. |
| `CULQI_PUBLIC_KEY` | `pk_test_...` (luego `pk_live_...`) | Pública; la expone `/pagos/config` para el APK. |
| `CULQI_WEBHOOK_TOKEN` | (opcional) una cadena al azar | Si la pones, el webhook exige `?t=<token>`. |
| `COMISION_PORC` | `5` | Comisión Pichangol por reserva. |
| `COMISION_MIN_SOLES` | `2` | Mínimo de comisión. |

Empezar con las llaves **test** (sandbox, sin plata real). Cuando Culqi valide el
comercio (≤24 h), cambiar a las **live**.

## 2) Webhook en el panel de Culqi

En Culqi → **Desarrollo → Webhooks**, registrar la URL:

```
https://pg-backend-production-c176.up.railway.app/pagos/webhook
```

(si usaste `CULQI_WEBHOOK_TOKEN`, agregar `?t=<token>` al final).

El webhook **re-consulta el cargo con la sk** (fuente de verdad, no confía en el
payload) y es **idempotente** (no acredita dos veces).

## 3) Endpoints

| Método | Ruta | Para qué |
|---|---|---|
| `GET` | `/pagos/config` | Llave pública + modo (test/live) para el APK. |
| `POST` | `/pagos/recarga` | Cobra la recarga y **acredita el saldo** del dueño. |
| `POST` | `/pagos/fee-reserva` | Cobra al jugador **sólo la comisión** (saldo cero). |
| `GET` | `/pagos/saldo/{dueno_id}` | Saldo del dueño (céntimos y soles). |
| `POST` | `/pagos/webhook` | Confirmación de Culqi (idempotente). |

Los `POST` que inicia el APK exigen `X-App-Key` (igual que propiedad) si
`APP_API_KEY` está configurada. El webhook no (lo llama Culqi).

## 4) Flujo de cobro (APK ↔ backend ↔ Culqi)

1. El APK tokeniza la **tarjeta o Yape** en el celular con la **llave pública**
   → obtiene un `token` (`tkn_...`).
2. El APK llama a `/pagos/recarga` (o `/pagos/fee-reserva`) con ese `token` +
   monto. **Nunca** manda datos de tarjeta al backend, sólo el token.
3. El backend crea el cargo en Culqi con la **llave secreta**.
4. Si se aprueba → acredita el saldo (recarga) y responde el nuevo saldo.
5. Culqi además dispara el **webhook** como respaldo (idempotente).

## Estado

- [x] Backend: cliente Culqi (`culqi.py`), router (`router.py`), ledger de saldo
      server-side (`stores.saldos` / `stores.pagos`, persistido en snapshot),
      tests (`tests/test_pagos.py`).
- [ ] APK: reemplazar `PasarelaSimulada` por `PasarelaCulqi` (tokeniza con la pk
      y llama a `/pagos/recarga`). Migrar el saldo local a server-side.
- [ ] Registrar el webhook en Culqi y cargar las llaves en Railway.
