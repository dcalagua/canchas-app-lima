# Agentes IA sobre Pichangol (3 actores) — pendiente de definir

Visión (Dennis): una **plataforma de agentes** sobre Pichangol. Los mismos
"ladrillos" (buscar, disponibilidad, reservar, cobrar, reportar, publicar en
redes, WhatsApp) sirven para los 3 actores; cada agente = mismo motor (LLM +
tool-use) con distinto **rol + herramientas + permisos**.

Detalle del agente de **academia/profe** en `docs/academia-agente-ia.md`.

## 🏟️ Agente del DUEÑO de cancha (copiloto de negocio) — add-on pagado
Dolor: horas muertas + no conoce sus números + admin. El agente:
- **Marketing en redes (lo que más ingreso trae):** posts con foto + copy,
  promos para llenar **horas valle**, publica y responde DMs.
- **Precio dinámico (yield):** ajusta precio por demanda (sube pico, baja valle).
- **Reportes:** ocupación por hora/día, ingresos, valle vs pico, qué cancha
  rinde, con **recomendaciones accionables**.
- **Cobros/saldo:** avisa cuándo recargar (modelo inDrive), concilia, morosidad.
- **Atención:** responde a jugadores por WhatsApp y reagenda.
- **Monetización:** reportes gratis (gancho) + marketing/pricing/cobros = add-on
  por suscripción. Le llena horas → más ingreso → paga por él.

## 🎙️ Agente del JUGADOR (conserje por voz) — GRATIS (crecimiento)
Flujo: voz *"fútbol 8pm en San Luis cerca a la Rambla"* → STT → el LLM extrae
(deporte, hora, zona, referencia) → geocodifica el landmark → busca en el
marketplace → **da opciones rankeadas y conversa** ("hay 3 cerca; la más barata
S/60, ¿reservo?") → **reserva** con el flujo de pago.
- Referencias difusas (landmarks), presupuesto, "lo de siempre".
- Proactivo: "tu jueves 8pm está por llenarse, ¿reservo?", "arma tu equipo".
- **No es add-on de pago:** genera más reservas → más comisión. Es
  crecimiento/retención.

## 🧱 Arquitectura común
- **Capa de herramientas** (funciones) sobre Pichangol: `buscarCanchas`,
  `disponibilidad`, `reservar`, `cobrar`, `generarReporte`, `publicarRedes`,
  `enviarWhatsApp`. Cada agente = mismo motor + su system prompt + permisos.
- **Canales:** in-app chat/voz para el jugador; **WhatsApp Business** para
  dueño/profe.
- **Voz:** speech-to-text (device o Whisper) + TTS.
- **LLM:** Claude (el org ya tiene un edge function `claude-proxy` como base).
- **Guardrails:** acciones con plata/públicas → modo con aprobación o autonomía
  configurable + límites de gasto.

## MVP por agente (para no quedar en humo)
- **Jugador:** búsqueda en **lenguaje natural** (texto/voz) que el LLM convierte
  a los filtros existentes (deporte, hora, zona) → resultados. Reserva
  conversacional después.
- **Dueño:** **reporte semanal por WhatsApp** auto-generado (barato, engancha) →
  luego posts de marketing → luego pricing dinámico.
- **Profe:** ver `academia-agente-ia.md`.

## Estado / orden
Pendiente. Va después del piloto Perú + Fase 2 (pagos). La **búsqueda en lenguaje
natural del jugador** es el mejor primer paso (alto valor, bajo esfuerzo, usa lo
que ya existe). WhatsApp Business API es dependencia para los agentes de
dueño/profe (envío automático + costo por mensaje).
