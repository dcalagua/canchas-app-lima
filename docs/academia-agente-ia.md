# Academia — Asistente IA (add-on de pago) — pendiente de definir

Visión (Dennis): un **agente IA** que es el **asistente administrativo virtual**
del profe. **Add-on de pago**, cobrado aparte por Pichangol (además de la
comisión de reservas). El alcance fino se define más adelante.

## Dos niveles

- **🟢 Sin IA (incluido en Academias):** automatización por **reglas**. El profe
  configura *cuánto tiempo después de la clase* se lanza el recordatorio/cobro
  (inmediato / 2 h / al día siguiente). Un job programado manda el WhatsApp o
  marca la cuota. Determinístico y barato.
- **🤖 Con IA (add-on pagado):** asistente administrativo virtual (abajo).

## Cobro automático (configurable por el profe)

- El profe define el disparo: cuánto tiempo tras la clase se cobra/recuerda.
- **Sin IA:** regla fija (job programado).
- **Con IA:** el agente decide el momento y el tono, personaliza el mensaje,
  insiste con morosos, concilia. Si hay **tarjeta guardada (Fase 2)** cobra de
  verdad automático; si no, manda el link de pago.

## Qué hará el agente (a detallar)

- **Cobros:** recordatorios personalizados, seguimiento de morosos, conciliación.
- **Asistencia:** registrar quién vino (el profe le dice por chat/voz, o QR de
  check-in del alumno) + reportes de asistencia/retención.
- **Reportes:** ingresos, morosidad, asistencia, alumnos en riesgo de fuga.
- **Marketing:** posts para redes, promos, captación de alumnos.
- **Redes sociales:** manejo/publicación.
- **Atención a alumnos:** responde horarios, precios, cupos por WhatsApp.

## Monetización (Pichangol)

- **Suscripción mensual** del profe por el asistente IA (ej. S/ 29–49/mes),
  escalable por # de alumnos. **Aparte** de la comisión de reservas → ingreso
  recurrente nuevo.

## Dependencias técnicas

- **WhatsApp Business API real** para enviar/recibir automático (los `wa.me`
  actuales son manuales, no sirven para automatizar) → costo por mensaje.
- **Fase 2 pagos (tarjeta guardada)** para el cobro automático real; sin ella,
  el agente manda link de pago.
- **Backend/agente:** servicio con acceso a los datos de la academia (alumnos,
  cuotas, asistencia) + **LLM (Claude)** + **jobs programados (cron)** para
  cobros/reportes + **guardrails** (aprobación del profe para acciones sensibles,
  o modo automático total configurable). Nota: el org ya tiene un edge function
  `claude-proxy` — posible base para el LLM.

## Estado / orden

Pendiente. Alcance del agente a definir. Va **después** de Academias Fase 2
(pasarela) y del piloto Perú. La automatización por reglas (🟢 sin IA) se puede
adelantar como parte de Academias.
