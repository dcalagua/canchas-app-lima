# Pichangol AI Marketing Agent

Sistema de marketing autónomo que reemplaza al calendario fijo de `agente_redes.py`:

```
DATOS → ANÁLISIS → ESTRATEGIA → CONTENIDO → VALIDACIÓN → APROBACIÓN → PUBLICACIÓN → MÉTRICAS → APRENDIZAJE
```

Código: `backend/growth/marketing/agente_ia/`. Torre: `/admin` → **Marketing IA**.
Tests: `backend/growth/tests/test_agente_ia.py`.

## Agentes

| Agente | Módulo | Qué hace |
|---|---|---|
| Data Collector | `datos.py` | Lee canchas, reservas, bloqueos, promos, canchas descubiertas, partidos y "pide tu cancha". Arma **agregados sin PII** por zona/día/franja (ocupación de 28 días y turnos libres de los próximos 7). Zona real con `zonas.py` (catálogo de distritos; si no se sabe, no hay zona). |
| Marketing Strategist | `estratega.py` | Reglas **deterministas** generan oportunidades candidatas con objetivo, KPI, razón y `hechos`. La IA (si hay `ANTHROPIC_API_KEY`) solo **elige** entre ellas; ids inventados se descartan. Peso dueños/jugadores según oferta (regla de oro de `PLAN_FUTBOL.md`). Aprendizajes suben o bajan el puntaje; lo repetido se penaliza. |
| Content Creator | `creador.py` | Copy con IA usando **solo** `hechos`. Si no pasa los guardrails, reintenta con los errores; si vuelve a fallar, usa plantillas probadas. Hashtags y enlace los pone el código. |
| Creative Agent | `creativo.py` | Prioridad: fotos reales de la biblioteca de marca → fotos del dueño (únicas válidas para un local destacado) → diseño de marca → arte IA conceptual (opcional, nunca para una cancha concreta). Imagen persistida en Storage `canchas/marketing/<id>.jpg`. |
| Guardrails | `guardrails.py` | Rechaza montos, porcentajes, horarios, cifras, zonas o locales que no estén en `hechos`; promos sin promo vigente; "gratis" fuera del registro de dueños; disponibilidad sin turnos reales; arte IA con un local; jerga/moneda de Perú en otro país; teléfonos/correos; repeticiones. |
| Publisher | `publicador.py` | Cada minuto publica lo `APPROVED` cuya hora llegó. Antes **revalida** contra los datos del momento: fecha anunciada pasada, promo vencida o cambiada, hora feliz de la zona distinta, turnos ya llenos, conteos que bajaron o local que dejó de ser Pro dan `FAILED` con motivo. Sin datos frescos no publica y reintenta. Reintentos 15/30 min, máximo 3. Facebook (foto/video) e Instagram (si `IG_USER_ID`). |
| Analytics | `analitica.py` | Ventanas 1h/24h/72h/7d/28d: insights de Facebook (cada métrica por separado; lo que Meta no da queda NULL), clics únicos del short-link y reservas atribuidas. |
| Learner | `aprendizaje.py` | Cada lunes: compara la media de cada dimensión contra la global (≥ 8 piezas, ≥ 3 por grupo, confianza ≥ 60 %, efecto ≥ 15 %). Sin LLM: estadística explicable con evidencia. |
| Venue Acquisition | `estratega.py` (`captar_duenos_zona`, `demanda_zona`, `duenos_beneficios`) | Zonas con canchas descubiertas sin dueño y zonas donde los jugadores piden canchas. |

`orquestador.py` une todo (cron de `main.py` cada 60 s) y expone los controles humanos.

## Estados

`DRAFT → PENDING_APPROVAL → APPROVED → PUBLISHING → PUBLISHED`, más `REJECTED`, `FAILED` y `CANCELLED`.

`PUBLISHING` es el reclamo atómico del publicador: solo quien pasa una pieza de APPROVED a PUBLISHING la publica, y mientras tanto nadie puede cancelarla, editarla ni publicarla otra vez. Si la base falla justo después de publicar, la pieza queda en PUBLISHING y a los 30 minutos pasa a FAILED con el aviso de revisar la página. Nunca se republica sola.
El operador puede **aprobar, rechazar (con motivo), editar** (se recompone la imagen y se revalida), **reprogramar, cancelar, pedir otra versión y publicar ya**.

## Modos

* `aprobar` (por defecto): nada sale sin aprobación humana.
* `auto_validado` (fase 6): lo que pasa todos los guardrails se aprueba solo, con tope diario (`ai_mkt_auto_max_dia`). Aun así, el publisher revalida antes de publicar.
* `ai_mkt_pausa = 1`: freno de emergencia, no se publica nada.

Al activar el agente se apaga `agente_fb_activo`: un solo agente publica en la página. El modo por defecto del agente viejo pasó de `auto` a `aprobar`.

## Atribución

Cada pieza lleva `https://www.pichangol.app/go/<codigo>`. El short-link cuenta el clic (huella anónima, sin IP ni PII), deja la cookie `pg_utm` por 7 días y redirige con `utm_*`. La reserva web guarda `origen='web'` y `utm` (`web/router.py` → `datos.insertar_reservas`). Mientras no se corra el SQL, la reserva entra igual que antes, sin atribución.

## Configuración (`stores.config`, desde la torre)

| Clave | Defecto | |
|---|---|---|
| `ai_mkt_activo` | `0` | Enciende el agente |
| `ai_mkt_modo` | `aprobar` | `aprobar` / `auto_validado` |
| `ai_mkt_hora_plan` | `06:30` | Hora local de planificación por país |
| `ai_mkt_paises` | `PE` | `PE,BO,EC` |
| `ai_mkt_posts_dia` | `1` | 1–3 |
| `ai_mkt_umbral` | `15` | Canchas reservables por zona para vender disponibilidad |
| `ai_mkt_mix_baja` / `ai_mkt_mix_alta` | `0.7` / `0.3` | Proporción de piezas para dueños con poca / suficiente oferta |
| `ai_mkt_destacar_pro` | `0` | Nombrar locales Pro (regla del director) |
| `ai_mkt_arte_ia` | `0` | Permitir arte IA conceptual |
| `ai_mkt_plataformas` | `facebook` | `facebook,instagram` |
| `ai_mkt_auto_max_dia` | `2` | Tope del modo automático |
| `ai_mkt_pausa` | `0` | Freno de emergencia |

| `ai_mkt_pro_cupo_mes` | `4` | Publicaciones por local Pro al mes (0 = ninguna) |
| `ai_mkt_pro_max_dia` | `1` | Piezas Pro extra por día |
| `ai_mkt_ia_ambientar` | `0` | Ambientar con IA las fotos reales del local Pro |
| `ai_mkt_video_ia` | `0` | Además, video con movimiento y música (en casa, gratis) |
| `ai_mkt_video_seg` | `12` | 8 / 12 / 16 s de fotos (más intro y cierre) |
| `ai_mkt_media_tope_usd` | `20` | Tope de gasto IA del mes (solo la imagen cuesta) |
| `ai_mkt_costo_imagen` | `0.07` | Costo estimado por imagen (confirmar con OpenAI) |

## Locales Pro con IA (20-oct-2026)

Decisiones del director: **ambientar las fotos reales** del dueño (no inventar el lugar), **video** y **cupo fijo al mes** por local Pro. El video se pidió con OpenAI Sora, pero **OpenAI cerró la API de Sora el 24-sep-2026** sin reemplazo (el primer pedido real en QAS respondió 404): el video se arma en casa.

- **Cupo** (`estratega.pro_del_dia`): piezas EXTRA, fuera de las N del día, para cada local destacable (dueño Pro + `ai_mkt_destacar_pro=1`) con al menos una foto propia. El cupo se reparte parejo en el mes (hoy toca el que va atrasado frente a `cupo × día / días del mes`; entre atrasados, el más atrasado y luego el que hace más tiempo no sale). `orquestador.uso_pro` cuenta las piezas del mes local (sin canceladas/rechazadas/fallidas, una por oportunidad aunque salga en dos redes); un local que llegó a su cupo deja de aparecer también en `cancha_destacada` / `promo_real`.
- **Foto ambientada** (`ia_media.ambientar`, origen `ia_ambientada`): OpenAI Images *edits* (`IMAGE_EDIT_MODEL`, gpt-image-1, `input_fidelity=high`) sobre la PRIMERA foto propia; el prompt exige conservar cancha, líneas, cercos, paredes, techos y edificios, y solo agrega jugadores y luz. La imagen queda en Storage `canchas/marketing/amb_*.jpg`; el collage lleva la ambientada + hasta 2 fotos reales. "Otra versión" y la gemela de la otra red REUSAN la misma (no se paga dos veces).
- **Video** (`ia_media.encargar_video` / `procesar_videos`, origen `video_ia`): la foto ambientada + las reales con movimiento tipo Ken Burns (`marketing/foto_video.py`) y el pulido Pichangol (`video_pulido.pulir`: logo, intro, rótulo con el título, cierre con www.pichangol.app, música original), cuadrado, gratis. Se pide al crear la pieza (o con "🎬 Hacer video" en una pieza ya ambientada, `orquestador.pedir_video`) y el cron (cada minuto) lo arma y lo sube a `canchas/marketing/<id>.mp4`. Mientras tanto la pieza no se aprueba ni se publica (el publicador espera 10 min sin gastar intentos); si falla, sale con la foto ambientada. En Facebook se sube el MP4; Instagram usa la foto. **Motor elegible en la torre** (`ai_mkt_video_motor`): `movimiento` (lo anterior, gratis) o **`veo` = Veo de Google** por la API de Gemini (`GEMINI_API_KEY` + `VEO_MODEL`, default `veo-3.1-fast-generate-preview`): `POST models/{VEO_MODEL}:predictLongRunning` con la foto ambientada como primer cuadro (image-to-video, 16:9, 8 s, `negativePrompt` sin textos ni logos) → el cron consulta la operación cada minuto → descarga el clip (`x-goog-api-key`) → `video_pulido.pulir` cuadrado con logo, intro, rótulo, cierre y música de fondo. Costo = `ai_mkt_costo_video_seg` × 8 s, RESERVADO al pedir dentro del tope mensual y devuelto si Veo rechaza o no entrega el clip (filtro de contenido). Sin llave, sin tope, error, o más de 20 min → el video se arma EN CASA en la misma vuelta (`nota_veo` lo explica en la torre). Tests `test_agente_ia_media.py` (Gemini simulado + pulido real con FFmpeg). Confirmar el id del modelo y el precio vigente en Google AI Studio.
- **Transparencia**: toda pieza con `ia_ambientada`/`video_ia` termina con `✨ Contenido creado con IA a partir de fotos reales del local.` (`guardrails.AVISO_IA`); el guardrail rechaza la pieza sin el aviso o si el texto presenta la imagen como foto sin retoque.
- **Tope de gasto mensual** (`ia_media.gasto`, `stores.config[ai_mkt_media_gasto]`): cada imagen se reserva antes de pedirla; un error de OpenAI devuelve la reserva. El video no cuesta (solo se cuenta). Sin tope disponible o sin `OPENAI_API_KEY`, la pieza Pro sale con las fotos reales (`foto_dueno`).
- **Torre** → Marketing IA → Configuración → "Locales Pro con IA": cupo, máximo por día, interruptores (marcar el video marca el ambientado), duración, tope, costo por imagen, gasto del mes y uso por local; la tarjeta muestra el video (o "Armando el video…", con refresco solo cada 20 s) y oculta "Aprobar" mientras se arma.
- Base: `ai_content.media_origen` acepta `ia_ambientada` y `video_ia` (el backend actualiza la regla al arrancar; el SQL lo trae también). Tests `tests/test_agente_ia_media.py`.

Variables de entorno nuevas: `IMAGE_EDIT_MODEL` (gpt-image-1), `MARKETING_STRATEGY_MODEL`, `MARKETING_COPY_MODEL` (por defecto el de `MARKETING_MODEL`) e `IG_USER_ID`. Para las métricas, el token de la página necesita `pages_read_engagement` y `read_insights`.

## Base de datos

`docs/piloto/supabase_ai_marketing.sql` (idempotente). Crea las 8 tablas `ai_*` con RLS activo y sin políticas (solo backend) y agrega `created_at`, `origen` y `utm` a `pichangol_reservas`. El backend también crea las tablas `ai_*` al arrancar; las columnas de reservas **solo** las agrega el SQL manual.

Orden de despliegue: **QAS** (Supabase "Pichangol") → probar → con la orden "pasa a PRD", **PCG-PRD**.
