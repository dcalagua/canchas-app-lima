# Diseño: capa social estilo Playtomic + CM autónomo Fase 0

Diseño técnico de dos features. Complementa `docs/estrategia-cm-y-red-social.md`.
Principio transversal: toda pantalla de mensajería/social se hace **device-first
cacheada** (ver `CLAUDE.md` → "Mensajería device-first").

---

# A) Capa social estilo Playtomic (adaptada a FÚTBOL)

**Idea:** copiar el foso de Playtomic —**nivel de jugador verificado por
resultados + matchmaking por nivel + chat por partido**— pero sobre fútbol/fulbito
y **reusando lo que Pichangol YA tiene** (rankings, retos, convocatorias,
jugadores disponibles, `grupoReservaId`). Lo ÚNICO nuevo de fondo es el **nivel**.

## 1. Nivel de jugador (lo nuevo)
- **Por deporte**, valor numérico **1.0–7.0** (1 decimal), como Playtomic 0-7.
- **Seed inicial (onboarding):** mini-cuestionario (años jugando, frecuencia,
  ¿compite?) → nivel estimado. Editable pero se ancla con resultados reales.
- **Ajuste por resultados (ELO suave):** tras cada resultado registrado (reto,
  partido de campeonato), actualizar:
  ```
  esperado = 1 / (1 + 10^((nivelRival - nivelYo) / 2))
  nivelYo  = clamp(nivelYo + K * (resultado - esperado), 1.0, 7.0)   // K≈0.15, resultado=1 gané / 0 perdí
  ```
  Se mueve lento (evita saltos), sube más si le ganas a alguien de mayor nivel.
- **Confiabilidad (reliability):** % de asistencias confirmadas vs. no-show
  (reusa la asistencia de convocatorias/clases). Badge en el perfil.
- **Persistencia:** tabla Supabase `pichangol_niveles` (`email`, `deporte`,
  `nivel`, `partidos`, `victorias`, `confiabilidad`, `updated`). Fail-safe como el
  resto. Cache device-first en `SharedPreferences`.

## 2. Perfil de jugador (evolucionar `perfil_global_screen`)
Foto real + nombre + **nivel por deporte** (chip) + posición (fútbol) + zona +
disponibilidad + historial (partidos/retos/victorias) + confiabilidad. Enlazable
desde la landing pública (`/l/{id}`) y desde el chat.

## 3. Matchmaking por nivel (reusar pantallas existentes)
- **`jugadores_disponibles_screen`:** filtrar por **|nivel−miNivel| ≤ 1.0** + zona
  + horario. "Juega con parejos".
- **"Completar la pichanga":** al reservar una cancha grupal que necesita N
  jugadores, sugerir disponibles del **mismo rango de nivel** en la zona → invitar.
  (Se apoya en `convocatorias_screen` + el nuevo nivel.)
- **Retos (`mis_retos`/`reto_dobles`):** sugerir rivales de nivel parejo.

## 4. Chat por partido (reusar `grupoReservaId` — ya existe, task #15)
Cuando se arma una **reserva grupal** (`grupoReservaId`), **auto-crear un chat del
partido** con los convocados (reusa grupos/`chat_screen`), device-first cacheado.
Es el "chat por partido" de Playtomic, gratis: ya tenemos el id que agrupa la
reserva y el motor de chat.

## 5. Ranking (ya existe) + enganche
Conectar el resultado de **campeonatos/retos** al nivel (mismo evento que alimenta
rankings). El ranking global/‌academia ya está; sumar la columna **nivel**.

## Mapa de reuso (qué hay vs. qué es nuevo)
| Pieza | Estado |
|---|---|
| Perfil, rankings, retos, convocatorias, jugadores disponibles | **YA existe** |
| `grupoReservaId` en reservas (hook del chat por partido) | **YA existe** |
| Chat/grupos device-first | **YA existe** |
| **Nivel por deporte + ELO + confiabilidad** | **NUEVO** (tabla + lógica) |
| Filtros de matchmaking por nivel | pequeño (usar el nivel en filtros ya hechos) |
| Auto-crear chat del partido desde `grupoReservaId` | pequeño |

---

# B) CM autónomo — Fase 0: "Post listo, 1 toque" (SIN Meta API)

**Meta de la fase:** que el dueño **entre a sus redes y ya tenga el post armado**;
solo toca "Publicar". Cero dependencia del App Review de Meta → **cobrable desde
ya**. Cuando Meta apruebe (Fase 1/2), el mismo pipeline auto-publica.

## Flujo
```
Scheduler (Railway) --por academia suscrita, según frecuencia-->
  genera IMAGEN (flyer de marca) + COPY + HASHTAGS (Claude) -->
  guarda el post (bucket público + growth_state) -->
  PUSH al dueño "Tu publicación de hoy está lista" -->
  APK: pantalla "Post del día" (preview + copy + hashtags) -->
  [Publicar en 1 toque] (hoja de compartir a IG/FB) · [Editar] · [Descartar]
```

## Piezas
1. **Suscripción / candado:** `academia.cmActivo` (plan). Reusa el candado
   "usuario pro" (#28). Sin plan, no genera.
2. **Config (dueño):** frecuencia (2-3/sem) · tono (juvenil/pro) · tipos de
   contenido (promo, horario libre, resultado/ranking, tip, testimonio) · auto vs
   aprobar. Se guarda en el backend (growth_state).
3. **Scheduler (backend growth, Railway):** worker periódico (APScheduler o loop
   asyncio) que, por academia suscrita y su frecuencia, dispara la generación.
   Estado en `growth_state` (última fecha, cola).
4. **Generación de COPY + hashtags:** **Claude** (`ANTHROPIC_API_KEY` ya está).
   Prompt con datos de la academia (nombre, deporte, sede, promos, horarios
   libres, highlight de ranking) → caption + hashtags + CTA. Rotar tipo de
   contenido para no repetir.
5. **Generación de IMAGEN (flyer de marca):** componer con **Pillow** (Python, sin
   navegador): foto del negocio de fondo + degradado + **logo Pichangol/academia**
   + texto generado, en paleta de marca. Determinista y barato. Se aloja en el
   **bucket público de Supabase** o en el endpoint `/marketing/img` (ya existe) →
   queda con **URL pública** (lo que luego pide la IG API en Fase 2). *(v0.5: reel
   con ffmpeg = fotos + música de Historias + texto.)*
6. **Entrega:** **push FCM** (ya existe) → abre pantalla **"Post del día"** en el
   APK: preview de la imagen + caption editable + botón **"Publicar en 1 toque"**
   → hoja de compartir a IG/FB (reusa `HistoriaShare` / share_plus, ya en la app).
   Publicación **client-side** = sin permisos de Meta.
7. **Registro:** marca el post como publicado/descartado (para métricas y para no
   repetir).

## Reuso (qué hay vs. qué es nuevo)
| Pieza | Estado |
|---|---|
| Motor marketing `backend/growth/marketing/` (+ `/marketing/img`) | **YA existe** |
| Claude enchufado (`ANTHROPIC_API_KEY`) | **YA existe** |
| Push FCM · compartir a IG/FB (`HistoriaShare`) | **YA existe** |
| `community_manager_screen.dart` (asistido) | **YA existe** (evolucionar) |
| **Scheduler** por academia | **NUEVO** |
| **Compositor de imagen (Pillow)** | **NUEVO** |
| **Config CM + candado suscripción** | **NUEVO** (parte reusa #28) |
| Pantalla "Post del día" + tipo de push | **NUEVO** (chico) |

## Por qué Fase 0 primero
- Entrega ~80% del valor percibido ("ya se posteó solo, yo solo confirmo").
- **Cero dependencia de Meta** → se cobra la suscripción desde ya.
- El mismo pipeline (generar media+copy) se REUSA en Fase 1 (FB auto) y Fase 2 (IG
  auto): solo se cambia el "publicar" de client-side a Graph API.

---

## Orden sugerido de implementación
1. **Nivel de jugador** (tabla + ELO + seed onboarding) → base de la capa social.
2. **Chat por partido** desde `grupoReservaId` (rápido, alto impacto de retención).
3. **Matchmaking por nivel** en jugadores disponibles / completar pichanga.
4. **CM Fase 0** (scheduler + Pillow + "Post del día") → primer ingreso recurrente.
5. Enlazar perfil de jugador desde la landing.
