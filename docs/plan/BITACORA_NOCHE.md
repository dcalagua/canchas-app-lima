# Bitácora — noche CanchaLibre (27-oct-2026)

Rama: `feat/noche-canchalibre` (desde `ccff09b` = `prd` + CLAUDE.md).
Plan: [`PLAN_NOCHE_CANCHALIBRE.md`](PLAN_NOCHE_CANCHALIBRE.md).

## Preparación
- Flutter **3.24.5** local en `~/sdk/flutter-3.24.5` (igual a CI); la 3.47.1 queda intacta.
- Postgres 16 local: `docker compose -f docker-compose.dev.yml up -d` (puerto 55432).
- Migraciones versionadas: `backend/growth/migraciones/NNNN_*.sql` +
  `python -m db.migrar [--estado|--local]` (tabla `cl_schema_migraciones`;
  `--local` se niega a correr fuera de localhost).
- Tests de integración con Postgres real: `TEST_DATABASE_URL=postgresql://canchalibre:canchalibre@localhost:55432/canchalibre python -m pytest`
  (sin la variable se saltan).

## Hecho

### C0 · Fuga del 2FA de la torre (commit `bb92c8d`)
- `GET /config/incentivos` devolvía `stores.config` COMPLETO sin auth: secretos
  TOTP de la torre (en base64 sin `META_TOKEN_KEY`), hashes de recuperación de
  32 bits, cuenta BCP de liquidaciones. Ahora: anónimo = lista blanca
  (`CONFIG_DEFAULT` no sensible); admin = todo menos secretos; el PUT genérico
  rechaza claves sensibles (`config_publica.py`).
- Secreto TOTP sin `META_TOKEN_KEY`: Fernet derivado de `ADMIN_PANEL_TOKEN`
  (prefijo `a:`), los `b:` legados se re-cifran al leerse.
- Códigos de recuperación: 64 bits + scrypt con sal (los viejos siguen valiendo una vez).
- **Acción del director tras desplegar:** asumir que los secretos 2FA y códigos de
  recuperación actuales pudieron filtrarse → cada operador re-enrola su 2FA
  (torre → Seguridad) y genera códigos nuevos. Recomendado fijar `META_TOKEN_KEY`.

### A2 · Reglas de reserva por cancha (commit `63a437c`)
- `reservas/reglas.py`: horario por día, cierres especiales, franjas de precio,
  recargo de luz, anticipación mín./máx., turnos mín./máx., tope por jugador/día,
  cancelación del club. Cancha sin reglas = comportamiento de siempre.
- Web (`/web/disponibilidad`, `/web/libres`, `/web/asegurar`, cancelación y
  comprobante) aplica las reglas; `/web/disponibilidad` devuelve `cerrado` y `politica`.
- `GET /reservas/politica/{id}` (público), `GET/PUT /reservas/reglas` (dueño
  verificado con `auth_usuario`).
- Migración **0002** (`reglas_reserva jsonb` + trigger: `anon` no puede pisarla).
- Diferido (con su costo): varios tramos por día, buffer entre turnos y
  "confirmación manual por el dueño" (requiere el flujo de aprobación de A3).

## Acciones pendientes del usuario/director
1. Correr en Supabase QAS (y luego PRD con autorización), en orden:
   `backend/growth/migraciones/0001_control_migraciones.sql`,
   `0002_reglas_reserva.sql`.
2. Re-enrolar el 2FA de la torre (ver C0).
