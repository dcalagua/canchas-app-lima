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

Variables de entorno nuevas: `MARKETING_STRATEGY_MODEL`, `MARKETING_COPY_MODEL` (por defecto el de `MARKETING_MODEL`) e `IG_USER_ID`. Para las métricas, el token de la página necesita `pages_read_engagement` y `read_insights`.

## Base de datos

`docs/piloto/supabase_ai_marketing.sql` (idempotente). Crea las 8 tablas `ai_*` con RLS activo y sin políticas (solo backend) y agrega `created_at`, `origen` y `utm` a `pichangol_reservas`. El backend también crea las tablas `ai_*` al arrancar; las columnas de reservas **solo** las agrega el SQL manual.

Orden de despliegue: **QAS** (Supabase "Pichangol") → probar → con la orden "pasa a PRD", **PCG-PRD**.
