# Estrategia Pichangol — brújula viva

> Producto de EBIM. Marketplace de reserva de canchas (fútbol/fulbito, tenis,
> pádel, pickleball) en Lima, con foco en el **sector informal**. Este documento
> es la brújula estratégica; se actualiza conforme aprendemos.

## Tesis (cómo ganamos)

**Pichangol es el sistema operativo del deporte amateur informal del Perú.**
Empezamos por la cancha de barrio (loza, grass, fulbito) que las apps formales
ignoran, y sobre esa red construimos comunidad y, recién después, monetización
B2B (academias, marcas, torneos).

Secuencia obligatoria (no saltarse pasos):
**inventario → densidad → retención → comunidad → monetización.**
El error clásico del rubro es vender publicidad antes de tener audiencia.

## La cuña (wedge) — ventajas defendibles

1. **El inventario ya existe.** Con Google Places las canchas informales ya
   están en el mapa desde el día 1; el dueño solo "reclama". Colapsa el
   huevo-gallina: el jugador encuentra canchas aunque ningún dueño se haya
   registrado. Las apps formales arrancan con inventario vacío.
2. **Pago en cancha / efectivo.** Inclusión real: el sector informal no
   bancariza. La competencia exige tarjeta; nosotros nos adaptamos.
3. **Confianza con bajo costo (concierge + WhatsApp).** Verificación de
   propiedad y aprobación por WhatsApp → onboarding del dueño en minutos, con
   anti-fraude. Ver `docs/flujo-reclamo-propiedad.md`.
4. **Multideporte bajo un local.** Fútbol/fulbito + tenis + pádel + pickleball
   en una sola ficha.

## Los 4 lados y su monetización (no depender solo de comisión)

| Actor | Valor que le damos | Monetización |
|---|---|---|
| **Jugador** | Encuentra y reserva sin llamar; juega por nivel; arma pichangas | Gratis (imán de audiencia) |
| **Dueño / concesionario / arrendatario** | **Llenar horas valle**, libro de caja, menos plantones, demanda nueva | Saldo prepago/comisión (modelo inDrive) + plan Pro |
| **Academias** | Captación de alumnos, agenda, visibilidad | Suscripción / lead-gen |
| **Marcas y torneos** | Audiencia segmentada por deporte/zona/nivel; patrocinio | Publicidad + sponsorship (mayor margen) |

La publicidad y los torneos se venden **cuando ya hay tráfico**. Antes, distraen.

## Valor agregado (lo que nos hace pegajosos)

- **Dueño:** la promesa que paga no es "reservas", es **"te lleno las horas
  muertas"** (horas valle, precios dinámicos sugeridos por IA, reserva entrante
  en vivo).
- **Jugador:** comunidad — **partidas abiertas** ("faltan 2 para fulbito hoy
  8pm"), nivel, ranking, historial. Playtomic para el barrio.
- **Marcas/torneos:** la red de canchas + audiencia jugadora = **medio
  publicitario deportivo hiperlocal** que hoy no existe en el informal.

## Benchmarking continuo (radar competitivo con agentes IA)

Proceso recurrente (semanal):
- **Agente features/precios:** vigila Playtomic, Atletic, Canchea, grupos de
  WhatsApp y tiendas de apps.
- **Agente voz-de-mercado:** analiza reseñas/quejas → dolores no resueltos =
  backlog.
- **Agente pricing/ocupación:** sugiere precios y horas valle por zona.
- **Salida:** brief de 1 página (oportunidades / amenazas / acciones).

## Roadmap por fases

- **Fase 0 — Piloto (1 club):** validar embudo reservar → pagar → ocupación.
- **Fase 1 — Densidad por zona:** conquistar **un distrito** (10-20 locales)
  antes de abrir otro. La densidad geográfica vence el huevo-gallina.
- **Fase 2 — Comunidad/retención:** partidas abiertas, niveles, reseñas.
- **Fase 3 — Monetización B2B:** academias → marcas → torneos → publicidad.
- **Fase 4 — Multitenant técnico + escala:** formalizar tenant/RLS/panel B2B,
  multi-ciudad. (Solo con tracción; antes es optimizar sin usuarios.)

## Métrica norte

**Horas valle ocupadas gracias a la app** + **retención semanal de dueños.**
Si esas dos suben, el resto (marcas, torneos) llega solo.

## Riesgos

- Huevo-gallina (mitigado por inventario Google + densidad por zona).
- Retención del dueño (que no vuelva al cuaderno) — el valor "horas valle".
- Confianza/fraude en el reclamo de propiedad (ver flujo dedicado).
- Dependencia de WhatsApp/Twilio (tener respaldo multicanal).
- Monetizar prematuramente.
