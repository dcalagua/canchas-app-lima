# Convocatorias ("pichangas" programadas)

Módulo que resuelve el caos del **chat de WhatsApp de los jueves** de un club
(caso real: El Bosque Country Club). Hoy el problema es:

- La inscripción es por WhatsApp a las 12:00 en punto → gana **el que madruga**,
  no el socio fiel. El que se distrae 5 minutos ya no encuentra cupo.
- Tras 14 inscritos (2 equipos de 7) el resto **queda fuera** sin más.
- **Cero trazabilidad**: nadie sabe quién se anota siempre ni quién falta.

La solución vive **dentro de Pichangol** (no es otra app): reusa login Google,
Supabase, WhatsApp (Twilio) y el patrón de config en caliente del backend growth.

## Objetos

- **Convocatoria** — la pichanga programada de un club: título, deporte,
  categoría (master/menor/libre), fecha del partido, ventana de inscripción
  (`apertura`/`cierre`), `cupos` y **modo de asignación**.
- **Inscripción** — un socio anotado. `creado_en` es la marca de inscripción
  (clave para orden de llegada); `asistio` lo marca el admin tras el partido.

## Los 3 modos de asignación (configurables por el admin)

El admin del club (rol **dueño** del APK) elige el modo **por convocatoria** al
crearla; si no elige, usa el **default global** (config `convocatoria_modo_asignacion`,
editable por la torre de control con `X-Admin-Token`). Los 3 modos:

| Modo | Cuándo confirma | Cómo reparte |
|---|---|---|
| `orden_llegada` | **En vivo** | El que se anota primero entra. Feedback inmediato ("entraste" / "espera #3"). Es lo de hoy, pero ordenado y con lista de espera automática. |
| `sorteo` | **Al cerrar** | Ventana de inscripción; todos quedan "en la bolsa" y al cerrar se sortea de forma **reproducible** (semilla fija). Mata el estrés del reloj. |
| `equidad` | **Al cerrar** | Prioriza a **quien más veces quedó fuera** y **mejor asiste**; baja a quien ya jugó las últimas fechas y penaliza al **no-show**. El socio fiel que siempre quedaba afuera empieza a entrar. |

### Puntaje de equidad (todo configurable, nada hardcodeado)

Sobre las convocatorias **cerradas** del mismo club:

```
puntaje = veces_en_espera * peso_espera
        - jugó_en_las_últimas_N_fechas * peso_jugo
        - no_shows * peso_noshow
```

Pesos por defecto (`db/store.py` → `CONFIG_DEFAULT`, ajustables en caliente):

- `convocatoria_equidad_peso_espera = 3`
- `convocatoria_equidad_peso_jugo = 2`
- `convocatoria_equidad_peso_noshow = 5`
- `convocatoria_equidad_ventana = 4` (cuántas fechas cuentan como "jugó reciente")

Mayor puntaje = más prioridad; empate → el que se anotó antes.

## Flujo

1. **Crear** (admin/dueño): `POST /convocatorias` con cupos y modo.
2. **Inscribirse** (socio): `POST /convocatorias/{id}/inscribir`. Devuelve el
   estado efectivo del socio: `confirmado` | `lista_espera` | `en_bolsa`.
3. **Cancelar** (socio): `POST /convocatorias/{id}/cancelar`. Si la convocatoria
   ya estaba cerrada, **auto-promueve** al primero de la lista de espera.
4. **Cerrar** (admin): `POST /convocatorias/{id}/cerrar`. Resuelve la asignación
   final según el modo y congela posiciones (para `sorteo` fija la semilla).
5. **Asistencia** (admin, tras el partido): `POST /convocatorias/{id}/asistencia`
   con `[{socio_id, asistio}]`. Alimenta el puntaje de equidad y el ranking.

## Endpoints

Público (identificado por email/Google; el día a día del club NO usa el token de
la torre de control):

- `POST /convocatorias` — crear
- `GET /convocatorias?club_id=&estado=` — listar
- `GET /convocatorias/{id}?socio=` — detalle (+ `mi_estado` si se pasa `socio`)
- `POST /convocatorias/{id}/inscribir`
- `POST /convocatorias/{id}/cancelar`
- `POST /convocatorias/{id}/cerrar`
- `POST /convocatorias/{id}/reabrir`
- `POST /convocatorias/{id}/asistencia`
- `GET /convocatorias/ranking?club_id=` — **trazabilidad**: recurrencia por socio
  (inscripciones, confirmado, lista_espera, jugó, no_show), ordenado por partidos
  jugados.

Sólo el **default global** del modo va con `X-Admin-Token` (config SaaS):

- `GET /convocatorias/config/modo`
- `PUT /convocatorias/config/modo` — `{ "modo": "orden_llegada|sorteo|equidad" }`

## Persistencia

Igual que el resto del backend growth: stores en memoria + snapshot JSON a
Postgres (`db/pg.py`, tabla `growth_state`). Tablas lógicas de referencia en
`db/schema.sql` (`convocatorias`, `inscripciones_convocatoria`).

## Tests

`cd backend/growth && python3 -m pytest tests/test_convocatorias.py -q`
(cubre los 3 modos, lista de espera, cancelación con auto-promoción, ranking y
persistencia por snapshot).

## Pendiente (siguiente fase)

- UI Flutter: sección "Pichangas" en la ficha del club (`club_detalle_screen`) y
  panel del dueño (`mis_pichangas_screen`), + `ConvocatoriasState` con SharedPreferences.
- Recordatorio por WhatsApp (Twilio) 10 min antes de abrir la inscripción.
- Armado automático de equipos y sub-categorías.
