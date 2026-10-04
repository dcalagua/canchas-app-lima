# Flujo de Academias (diseño)

Academias de tenis/fútbol que **alquilan** canchas y dan clases. Segmento clave:
concentran oferta (clases) y demanda (alumnos). Decisiones de diseño tomadas con
el usuario (Dennis) a partir del caso real de su amigo (academia de tenis que
pasó de **ESMON** → **CEANDE** por precio).

## Decisiones (las 3 que definen todo)

1. **Rotan entre locales.** Las academias siguen el mejor precio y se mudan de
   club. → La **academia es una entidad propia** (marca), NO atada a un local.
   El local donde entrena hoy es un dato **cambiable** ("sede actual"); al
   mudarse, su historia (alumnos, pagos) se conserva. **Modelo B.**
2. **Pagos en la app.** El dolor central del profe es **perseguir el cobro**.
   La app gestiona paquetes, cuotas, efectivo con recordatorio y asistencia.
3. **Publicación libre.** La academia se publica sola y elige su sede; el club
   NO tiene que aprobar. Si un club no la reconoce, la reporta (backlog).

## Entidades

- **Academia** (marca): nombre, deporte(s), logo, WhatsApp, descripción,
  **sedeActual** (referencia a un local/club, cambiable), dueño (profe/email).
- **Alumno**: nombre, contacto (WhatsApp), inscripciones.
- **Plan/Paquete**: tipo, precio, nº de clases, descuento, vigencia.
- **Inscripción**: alumno + academia + plan + fecha de inicio.
- **Cuota**: de una inscripción → vencimiento, monto, **mora**, estado
  (pendiente / pagada / vencida). (Como la pantalla de "cuotas" que compartió.)
- **Sesión/Clase**: fecha, hora, sede, lista de asistencia.
- **Asistencia**: alumno + sesión + presente/faltó + (drop-in) pagada sí/no.
- **Pago**: de una cuota o clase; método (efectivo | tarjeta en Fase 2); quién
  lo marcó (profe para efectivo, pasarela para tarjeta).

## Paquetes (recomendado)

- **Mensualidad** (ej. 8 o 12 clases/mes) → plan base.
- **Prepago multi-mes con descuento**: 1 mes (base) · 3 meses (−10%) · 6 meses
  (−15%). Empuja a pagar por adelantado (lo que el profe quiere: cobrar de una).
- **Por clase / drop-in**: para el alumno suelto.
- (Opcional) **Bono de N clases** (ej. 8 clases, vencen en 45 días).

## Cómo cobra (3 vías)

1. **Tarjeta guardada → cobro automático** mensual, o el paquete completo de una.
   *(Fase 2: requiere pasarela peruana — Culqi / Izipay / Niubiz.)*
2. **Efectivo**: el profe marca la cuota/clase como pagada. Si NO la marca → la
   app manda **recordatorio por WhatsApp** al alumno (reusa Twilio/WhatsApp del
   OTP en `backend/growth/propiedad`).
3. **Vista de cuotas** (como la imagen): el alumno ve meses pendientes
   (vencimiento, monto, mora), selecciona y paga.

## Asistencia

- El profe marca **asistencia por sesión** (presente / faltó).
- La app cuenta clases usadas del paquete, avisa faltas, y en **drop-in**:
  marcar asistencia = matricular esa clase → dispara el cargo/recordatorio.

## Estados

- **Academia**: activa. `sedeActual = {local}` (cambiable al mudarse).
- **Cuota**: pendiente → pagada | vencida (con mora al vencer).
- **Clase drop-in**: matriculada → asistió → pagada | impaga → (impaga y no
  marcada) → recordatorio WhatsApp.

## Fases

**Fase 1 — matar el dolor, sin pasarela.**
Objetivo: que el profe deje de perseguir cobros.
1. **Perfil de Academia** (crear/editar): nombre, deporte, **sede actual**
   (elige un club del mapa), WhatsApp, planes.
2. **Alumnos**: el profe los da de alta (o el alumno se auto-inscribe con un plan).
3. **Cuotas**: al inscribir con plan mensual/prepago se generan las cuotas; el
   alumno ve sus cuotas.
4. **Efectivo + marcado**: el profe marca cuota/clase como pagada.
5. **Recordatorio WhatsApp**: cuota vencida o clase drop-in no marcada.
6. **Asistencia**: lista por sesión.

**Fase 2 — tarjeta.** Pasarela + tarjeta guardada + cobro automático
mensual/paquete. Aquí ya nadie persigue a nadie.

## Dónde vive (arquitectura propuesta)

- **Rol "Academia" en el APK** (como el rol "Verificador"): el profe gestiona
  alumnos, cuotas y asistencia desde su celular.
- **Jugador**: ve las academias en el marketplace (directorio: deporte, sede
  actual, planes) y se inscribe.
- **Backend**: nuevo módulo (posible `backend/growth/academias/` o servicio
  aparte) con academias, alumnos, planes, cuotas, asistencia; WhatsApp reutiliza
  el adapter existente.

## Pendiente de datos

- **ESMON** y **CEANDE** (clubes donde entrena/entrenaba la academia) NO salen en
  el mapa → sembrarlos como Regatas cuando el usuario pase coordenadas.
