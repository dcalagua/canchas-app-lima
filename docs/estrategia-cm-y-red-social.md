# Estrategia: Community Manager autónomo + capa social (¿red social propia?)

Documento vivo. Consolida (1) un barrido de mercado y (2) el plan del servicio de
**Community Manager autónomo**, más la decisión de producto sobre construir o no
una "red social" deportiva. Ver también la sección *Pendientes / backlog* y
*Mensajería device-first* de `CLAUDE.md`.

## TL;DR (recomendación)

1. **NO construir un Facebook desde cero.** Sí construir la **capa social VERTICAL
   delgada** que Playtomic ya validó (nivel de jugador verificado por resultados +
   matchmaking por nivel + chat por partido) sobre nuestro core transaccional
   (reservas/pagos). La **landing pública `/l/{id}`** (SEO en pichangol.app) es la
   "página" del negocio (galería, horarios, reseñas, botón Seguir).
2. **El wedge es FÚTBOL/FULBITO.** Playtomic domina pádel y **ya está en Lima**;
   casi no toca fútbol, que en Perú es masivo y de reserva recurrente por grupos.
   Los locales (CanchasYa, Mi Cancha, Cancha PE, Fairplay) ya hacen
   reserva+pago+reseñas = **commodity**. Nadie local ha clavado la **capa social
   del jugador** ni el **CM autónomo**. Ahí está la diferenciación.
3. **CM autónomo = servicio estrella B2B (ingreso recurrente).** Arrancar por el
   fallback **"post listo, 1 toque"** (sin depender de Meta), luego auto-publish en
   **Página de Facebook**, y al final **Instagram**. El bloqueador real es el
   **App Review + Business Verification de Meta**.

## BLOQUE 1 — Mercado

### Playtomic (el gemelo más cercano) — modelo VALIDADO
- Marketplace de reserva de pádel/tenis/pickleball + **red social del jugador**.
  B2B2C: *Playtomic Manager* (SaaS al club) + *Playtomic App* (marketplace social).
- **Monetiza diversificado:** comisión por reserva + suscripción SaaS al club +
  marketplace. 2025: ~€346M transaccionados (+51% a/a), ~€29M ingreso neto. Levantó
  €65M. Pitch a clubes: facturan **3-5x más**.
- **Foso = comunidad:** nivel de jugador 0-7 con "reliability" que se ajusta por
  resultados reales; **matchmaking** por nivel; **chat por partido**;
  amigos/invitaciones; feed comunitario. >2M jugadores.
- **Ya en Lima** (clubes de pádel, ej. Mad Padel Surco/Barranco/La Molina). Fuerte
  en México y Argentina.
- **Copiar:** nivel + reliability + matchmaking + chat por partido (convierte
  "reservas" en comunidad pegajosa). Pichangol ya tiene rankings/retos → conectarlos
  a un **nivel verificado por resultados**. **Evitar/ojo:** es pádel-céntrico y ya
  está en Lima; competir de frente en pádel es cuesta arriba → **entrar por fútbol**.

### Mindbody + ClassPass (fitness booking)
- SaaS de gestión + agregador de suscripción (yield management de cupos vacíos).
- Monetiza ~45% suscripción SaaS + ~35% pagos + marketplace. Capa social **débil**.
- **Copiar:** doble motor **SaaS + pagos**; pitch "te llenamos los horarios muertos"
  (aplica a canchas con huecos entre semana). **Evitar:** sin comunidad, el
  descubrimiento+pago es commodity/reemplazable.

### Spond / Heja (gestión de equipos)
- Spond: gratis total, monetiza **solo el procesamiento de pagos** + fundraising.
  Heja: freemium con plan de pago. Comunidad **de puertas adentro** (el equipo), no
  red abierta ni rankings.
- **Copiar:** el **grupo que ya existe** (tu equipo de fulbito) como unidad social =
  efecto de red *local*, barato. Absorber la **coordinación de la pichanga** como
  gancho de retención. **Evitar:** no monetizan comunidad ni marketing del negocio;
  Pichangol puede ir más allá (comisión + marketplace + CM).

### Perú/Lima (competencia local directa)
- **CanchasYa, Mi Cancha, Cancha PE, ReservaSimple, Fairplay:** reserva + pago +
  reseñas + mapa (paridad con nuestro core). En pádel: **LimaPadel.pe** (directorio)
  y **Pádel Lima app** (intento local de capa social en pádel).
- **Lectura:** el core transaccional es commodity local; **ninguno** ofrece capa
  social vertical fuerte (nivel/matchmaking/feed/retos/canales) **ni CM autónomo**.

### Veredicto
Modelo "**core transaccional + capa social vertical de deporte**" **VALIDADO** por
Playtomic. Hueco en Perú: **fútbol/fulbito con capa social del jugador + CM
autónomo para el dueño**. No construir Facebook; construir la capa delgada que
Playtomic probó, sobre fútbol, con la landing como "página" del negocio.

## BLOQUE 2 — Meta Graph API (auto-publicar)

### Página de Facebook (camino más corto)
- **Permisos:** `pages_manage_posts` (+ dependencias `pages_read_engagement`,
  `pages_show_list`). Se opera con **Page Access Token**.
- **Endpoints:** texto/enlace `POST /{page-id}/feed`; foto `/{page-id}/photos`;
  video `/{page-id}/videos`. Soporta programación nativa (`published=false` +
  `scheduled_publish_time`).
- **App Review: SÍ** (producción) + **Business Verification** de EBIM (documentos
  legales, ~2-5 días). Justificaciones específicas + screencast pasan mejor.

### Instagram (Business/Creator)
- **Content Publishing API.** Permisos `instagram_basic` + `instagram_content_publish`.
  Requiere **IG Business/Creator vinculado a una Página de FB**.
- **Flujo 2 pasos:** `POST /{ig-user-id}/media` (contenedor) → `POST /{ig-user-id}/media_publish`.
- **Media en URL PÚBLICA** (no se sube binario directo) → alojar en el **bucket
  público de Supabase** (ya existe `productos`) o en el backend.
- **Rate limit: 25 publicaciones / 24 h** por cuenta (carrusel = 1). Consultar
  `content_publishing_limit`; para 1-3 posts/día por academia sobra.
- **App Review: SÍ.** Sin aprobación, modo dev solo con usuarios de prueba.

### Gotchas / riesgos
- **Tokens de larga duración expiran a 60 días** → **refrescar automáticamente**
  (~cada 55 días) o el servicio se cae en silencio.
- **Business Verification** obligatoria antes del review.
- **Bloqueo de apps Meta = riesgo real** (la cuenta ya tuvo problemas). Mitigar:
  Business Manager/app **limpios y verificados**, permisos mínimos, casos de uso
  quirúrgicos.
- IG **solo** con cuenta Business/Creator + Página vinculada (fricción de onboarding).
- **Alternativas si no aprueban:** (1) fallback **"post listo, 1 toque"** (sin
  permisos de publicación); (2) empezar solo por FB Page; (3) **intermediarios**
  (Ayrshare, Postproxy, etc.) que ya tienen el review resuelto y exponen una API
  única — cuestan fee pero de-riskean el bloqueador Meta (evaluar costo vs. in-house).

## Plan del CM autónomo — por fases

- **Fase 0 — "Post listo, 1 toque" (sin Meta):** scheduler genera media (flyer de
  marca con fotos+logo del negocio / reel auto-armado con música de Historias) +
  copy + hashtags (Claude), y lo deja listo → push "publica en 1 toque" (share a
  Historia IG/FB ya existe). Valida disposición a pagar (~S/100/mes). Candado
  "usuario pro" (#28).
- **Fase 1 — Auto-publish FB Page:** Business Verification EBIM + app review
  `pages_manage_posts`. Scheduler en Railway por academia, con **renovación de token
  a 55 días**.
- **Fase 2 — Auto-publish IG:** tras FB estable; `instagram_content_publish`,
  vínculo IG Business↔Página en onboarding, media en URL pública (Supabase),
  self-throttling a 25/día.
- **Transversal:** app/Business Manager limpio, permisos mínimos, mantener el
  fallback "1 toque" siempre disponible. Config: frecuencia · tono · auto vs
  aprobar · tipos de contenido · pausar (torre de control `/admin`).

## Roadmap sugerido (orden)
1. Piloto actual estable (dev = QAS) + landings en `pg.ebim.pe`.
2. **CM Fase 0** ("1 toque") como primer servicio de pago recurrente.
3. Capa social ligera estilo Playtomic sobre fútbol: **nivel verificado por
   resultados** (conectar rankings/retos) + **matchmaking por nivel** + **chat por
   partido/reserva**.
4. CM Fase 1 (FB auto) cuando haya academias que justifiquen el review de Meta.
5. Evolucionar la landing a "página" del negocio (galería, reseñas, Seguir).
6. CM Fase 2 (IG auto).

## Fuentes
Playtomic (vizologi, getlatka, capital-riesgo, thepadelsociety, help Playtomic),
Mindbody/ClassPass (mindbodyonline, classpass partners), Spond/Heja (spond.com,
teamstats), Perú (Depor "6 apps", CanchasYa, Mi Cancha, Cancha PE, ReservaSimple,
LimaPadel), Meta (developers.facebook.com Pages API + IG content publishing +
content_publishing_limit; postproxy; feedframer tokens). Detalle de URLs en el
informe de investigación de la sesión.
