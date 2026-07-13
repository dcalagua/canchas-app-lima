# Heurística de detección de canchas (Google Places)

> Cómo Pichangol descubre canchas/clubes reales en el mapa y les asigna deporte.
> Código: `lib/services/places_service.dart`. Este doc es la **referencia viva**
> del criterio; al afinar la heurística, actualizarlo.

## Principio

- Las canchas descubiertas en Google entran como **`registrada = false`** →
  **reclamables, NO reservables**. Sirven para invitar al dueño a reclamar.
- Por eso la heurística puede ser **inclusiva**: un falso positivo es solo un pin
  para reclamar (el dueño precisa el deporte real al reclamarlo); un falso
  negativo (no detectar una cancha real) sí nos cuesta.
- Equilibrio: incluir lo deportivo, **excluir lo claramente no-cancha**
  (gimnasios, tiendas, piscinas, etc.).

## 1) Consultas de búsqueda (`_consultas`)

Texto que se envía a Places (New) `searchText`, en paralelo. Cubre:
- **Fútbol informal (jerga PE):** canchas de fútbol, cancha sintética, pichanga,
  grass sintético, fútbol 7, loza deportiva.
- **Raqueta:** club de tenis, cancha de tenis, cancha de pádel, club de pádel,
  cancha de pickleball.
- **Clubes / complejos:** complejo deportivo, club deportivo, polideportivo,
  country club, racquet club.

## 2) Deporte por NOMBRE (`_deporteDe`)

Orden de prioridad (primer match gana):
- **Pickleball:** `pickleball`, `pickle`.
- **Pádel:** `pádel`, `padel`.
- **Tenis:** `tenis`, `tennis`, `raqueta`, `racquet`.
- **Fútbol (también genérico de cancha):** `fútbol/futbol`, `pichang`, `golazo`,
  `fulbito`, `futsal`, `cancha/canchita`, `sintétic`, `grass`, `loza/losa
  deportiva`, `complejo/club/centro deportivo`, `polideportivo`, `country club`,
  `club de campo`, `club campestre`, `estadio`.

## 3) Deporte por TIPO de Google (cuando el nombre no dice nada)

Si Google marca el lugar como recinto deportivo/club → reclamable (deporte
genérico fútbol; el dueño lo precisa):
`stadium`, `arena`, `sports_complex`, `sports_club`, `sports_activity_location`,
`recreation_center`, `athletic_field`, `country_club`.

## 4) Descartes (no son canchas)

- **Tipos excluidos:** gym, store, shopping_mall, clothing_store, school,
  university, lodging, gas_station, supermarket, restaurant, bar, doctor,
  hospital, pharmacy, bank.
- **Palabras excluidas:** gimnasio, gym, tienda, store, colegio, universidad,
  federación, crossfit, spinning, natación, piscina, billar, bowling.
- Nota: "academia" NO se excluye (academias de tenis/pádel sí son canchas).

## Mejora continua (cómo afinarla con casos reales)

Cuando se pruebe en una zona y una cancha/club real **no aparezca** (o aparezca
mal), registrar el caso y ajustar:
1. ¿El **nombre** tiene una palabra que deberíamos reconocer? → agregar a la
   lista del deporte correspondiente en `_deporteDe`.
2. ¿Google lo marca con un **tipo** deportivo que no contemplamos? → agregarlo a
   la sección de tipos.
3. ¿Una **búsqueda** nueva lo encontraría? → agregar a `_consultas`.
4. ¿Es un **falso positivo** molesto (no-cancha)? → agregar a los descartes.

> A futuro, el **radar de mercado con agentes IA** (ver `docs/estrategia.md`)
> puede proponer estos ajustes automáticamente a partir de lo que se ve en campo.

## Casos de prueba conocidos

| Lugar | Esperado | Notas |
|---|---|---|
| Country Club El Bosque | Detectado (club) | por nombre "country club" / tipo `country_club` |
| Loza deportiva de barrio | Detectado (fútbol) | jerga informal |
| Gimnasio / tienda deportiva | NO detectado | descarte por tipo/palabra |
| **"Tenis Americanos" (zapatería)** | **NO detectado** | "tenis" en jerga = zapatillas; se descarta por tipo `shoe_store`/palabra de calzado, y porque `tenis` sin señal de recinto (club/cancha/academia) no basta |

## Ambigüedad de "tenis" (importante)

En Perú/Bolivia **"tenis" también significa zapatillas**. Por eso el nombre
`tenis`/`tennis` **solo** clasifica como cancha de tenis si además hay una
**señal de recinto** (`club`, `cancha`, `academia`, `court`, `lawn`, `sede`,
`country`, o nombre fuertemente deportivo) **o** un tipo deportivo de Google.
`raqueta`/`racquet` sí son inequívocos → tenis directo.

## Vóley y básquet

Muchos locales alquilan la misma **loza multiuso** para vóley y básquet. Se
detectan por nombre (`vóley`/`voley`/`voleibol`/`volley`; `básquet`/`basquet`/
`basket`) y por las consultas `cancha de vóley` / `cancha de básquet`. Ojo: las
**lozas municipales** ("loza deportiva") siguen fuera del marketplace (no son
alquilables); solo entran locales privados con señal de recinto.
