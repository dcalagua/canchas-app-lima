# Bitácora — noche CanchaLibre (26→27-oct-2026)

Rama: `feat/noche-canchalibre` (desde `ccff09b` = `prd` + CLAUDE.md). **15 commits,
83 archivos, +7.039 / −2.068.** Plan: [`PLAN_NOCHE_CANCHALIBRE.md`](PLAN_NOCHE_CANCHALIBRE.md).

**Estado de calidad al cierre**
- Backend: **929 tests pasan** (6 omitidos sin Postgres); con Postgres local, 932.
  Verificado también con **Python 3.11** (= producción) en Docker.
- Flutter 3.24.5 (= CI): `flutter analyze` **0 errores**, 94 avisos (línea base
  96); `flutter test` verde; goldens en `test/goldens/png/`.
- **La rama NO se subió a GitHub**: el `git push` fue bloqueado por permisos de
  la sesión. Para compilar el APK en CI: `git push -u origin feat/noche-canchalibre`
  (esta rama no redespliega Railway ni publica Release).

## Preparación
- Flutter **3.24.5** local en `~/sdk/flutter-3.24.5` (igual a CI).
- Postgres 16 local: `docker compose -f docker-compose.dev.yml up -d` (puerto 55432).
- Migraciones versionadas: `backend/growth/migraciones/NNNN_*.sql` +
  `python -m db.migrar [--estado|--local]` (`--local` se niega fuera de localhost).
- Integración real: `TEST_DATABASE_URL=postgresql://canchalibre:canchalibre@localhost:55432/canchalibre python -m pytest`.

## Hecho

| Fase | Qué | Commit |
|---|---|---|
| C0 | `GET /config/incentivos` ya no filtra el 2FA de la torre (lista blanca), secreto TOTP sin base64, recuperación 64 bits + scrypt | `bb92c8d` |
| A2 | Reglas de reserva por cancha: horario por día, cierres, franjas, luz, anticipación, turnos mín./máx., tope por jugador, cancelación del club. Web y APK las aplican | `63a437c`, `6cde90f` |
| A4–A6 | Cobro DIRECTO al club: Culqi propio (sk cifrada), medios manuales con voucher anti-fraude, bandeja del dueño, vencimiento, webhook por club, comisión desde saldo o como deuda (suspensión sobre tope) | `f4ca964` |
| A1 | Deportes activos configurables en la torre (`deportes_activos`) | `4004e77` |
| B1 | Sistema de diseño `lib/ui/ds.dart`, CTA AA (#0B7A57), DM Sans única, bug de fuente del sistema en botones/chips/inputs | `4004e77` |
| B (pantallas) | Cobros de tu club, Pagos por confirmar, Reglas de reserva, Checkout directo del jugador | `4004e77`, `6f08d5c` |
| C2 | Liquidaciones solo con cobro real (sin cargo → en revisión), comisión-reserva solo del dueño real, carrera de `/web/pagar`, reembolsos del APK al backend | `e7fc118`, `d8ddabe` |
| C1 | Identidad verificada (token de Google) en boleadores y `es_mio` de propiedad; APK envía el token | `5a9d38d` |
| C3 | Migración 0004: la anon key no sube `verificada` ni cambia un dueño asignado | `6a371d8` |
| C4/C5 | CI con pytest+Postgres y flutter test; reset-total bloqueado en PRD; IP real en rate limit; `/health` con DB; 6 pantallas muertas fuera | `fba5198` |
| Rebrand | Loader/splash sin el PNG "Pichangol"; "Mis reservas" ya no muestra como Confirmada una reserva sin pagar | `3739535`, último |

## Acciones del usuario / director (en orden)
1. **Push** de la rama y revisar el build de CI.
2. **Variables nuevas en Railway (QAS primero):**
   - `PAGOS_ENC_KEY` (Fernet; generar: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`). Sin ella los clubes no pueden cargar su Culqi.
   - Opcional: `VOUCHER_PLAZO_MIN` (60), `AUTH_USUARIO_ESTRICTO` (dejar 0 hasta que el APK nuevo esté distribuido), `PERMITIR_RESET_TOTAL` (no poner en PRD), `META_TOKEN_KEY` (recomendado).
3. **SQL en Supabase QAS** (y PRD con autorización), en orden:
   [0001](https://github.com/dcalagua/canchas-app-lima/blob/feat/noche-canchalibre/backend/growth/migraciones/0001_control_migraciones.sql) ·
   [0002](https://github.com/dcalagua/canchas-app-lima/blob/feat/noche-canchalibre/backend/growth/migraciones/0002_reglas_reserva.sql) ·
   [0003](https://github.com/dcalagua/canchas-app-lima/blob/feat/noche-canchalibre/backend/growth/migraciones/0003_cobro_directo_club.sql) ·
   [0004](https://github.com/dcalagua/canchas-app-lima/blob/feat/noche-canchalibre/backend/growth/migraciones/0004_proteger_propiedad_anon.sql)
   (0004: probar en QAS registrar/editar/reclamar desde el APK antes de PRD).
4. **Re-enrolar el 2FA** de cada operador de la torre y generar códigos nuevos (pudieron filtrarse por C0).
5. **Probar con las llaves Culqi de prueba**: Torre/APK → Modo anfitrión → *Cobros y reglas* → conectar Culqi → reservar como jugador → pagar con tarjeta de prueba Culqi / subir voucher → confirmar en *Pagos por confirmar*.
6. Revisar liquidaciones "en revisión" (APKs viejos sin cargo) y aprobarlas con `POST /pagos/liquidacion/{id}/aprobar-revision` tras verificar en Culqi.

## Pendiente (con su costo)
- **Push-aviso falsificable** (`pichangol_avisos` con anon): requiere Supabase Auth o mover los avisos al backend (1–2 días).
- **RLS por usuario** en todas las tablas y fin de la escritura anon de reservas: requiere Supabase Auth (varios días) + APK nuevo.
- **Snapshot JSON → tablas** (saldos/pagos ya tienen tabla; el resto no): varios días.
- **Apartados del APK (`jug_…`) sin vencimiento**: el APK no distingue un apartado online abandonado de una reserva en efectivo; se resuelve migrando el APK al flujo del servidor (ya disponible para clubes con cobro directo).
- **Checkout directo en el APK**: v1 sin bono, puntos, fidelidad ni boleador (el servidor los soporta; falta UI).
- **Reglas**: varios tramos por día, tiempo de limpieza entre turnos y confirmación manual por el dueño.
- **B3 restante**: rediseño de Explorar, ficha completa, panel del dueño 7→5 pestañas, router con rutas nombradas, partir `app_state.dart`.
- **Ícono del launcher y splash nativo**: siguen compilados con el logo viejo; requieren un logo nuevo aprobado por el director.
- **3DS de Culqi**: no implementado; un cargo que Culqi mande a autenticación se ve como rechazo (verificar con la cuenta del club).
