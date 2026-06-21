# Verificación de Existencia (submódulo de onboarding)

Submódulo backend que estima qué tan **real** es un negocio (cancha) antes de
aprobarlo en Pichangol, combinando señales de **SUNAT**, **Google Places** y
**redes/reseñas** en un **score explicable**. Es la base técnica de la
verificación de propiedad anti-fraude (Capa 2 del onboarding).

> Código: `backend/onboarding_verificacion/existencia/`

## Principio rector: verificar y NO retener
Cumple **Ley 29733** (Protección de Datos Personales) y **DS 016-2024-JUS**:

- Los **documentos personales** (DNI, recibo, selfie) se procesan en
  memoria/temporal y se **eliminan** (`compliance/retention.py`,
  `documento_temporal`). **No** existen columnas para guardarlos ni para DNI en
  claro (ver `db/schema.sql`).
- Solo persiste el **resultado**: `bool + score + fecha` (+ evidencias NO
  personales = factores y sus puntajes).
- **Consentimientos** (`verificacion | marketing | llamada`) registrados; el
  recontacto se **bloquea** si el titular denegó o si venció
  (`compliance/consent.py`).
- Si por excepción se conserva algo → **cifrado + TTL** de eliminación.
- Stubs de **protocolo de brecha** (notificación ≤ 48 h, `compliance/breach.py`)
  y **logging de acceso por rol** (`compliance/access_log.py`).

## Contrato del endpoint
`POST /verificacion/existencia`

```jsonc
// body
{ "cancha_id": "u123_futbol", "ruc": "20123456789",
  "razon_social": "Club Demo SAC", "direccion": "Av. Aviación 2345, San Borja",
  "lat": -12.108, "lng": -76.978 }
```
```jsonc
// return (sin datos personales)
{ "cancha_id": "...", "score_existencia": 86, "nivel": "alto", "aprobado": true,
  "justificacion": "Puntaje 86/100 ...",
  "sunat": { "consultado": true, "existe": true, "estado": "ACTIVO",
             "condicion": "HABIDO", "domicilio_coincide": 0.93,
             "establecimientos_anexos": 1, "fuente": "stub" },
  "maps":  { "consultado": true, "encontrado": true, "operativo": true,
             "distancia_m": 72.0, "fuente": "stub" },
  "social": { "...": "..." },
  "evidencias": [ { "factor": "sunat_activo", "peso": 0.30, "valor": 1.0,
                    "aporte": 30.0, "disponible": true, "detalle": "..." } ],
  "fecha": "2026-...Z", "sin_datos_personales": true }
```

Otros endpoints: `POST /consentimientos`,
`GET /consentimientos/{sujeto}/{tipo}`, `GET /health`.

## Scoring (explicable)
`scoring.py` combina factores con **pesos que suman 1.0** (configurables por
`VERIF_PESOS`). Cada factor aporta una porción justificable del puntaje (0–100):

| Factor | Peso | Qué mide |
|---|---:|---|
| `sunat_activo` | 0.30 | RUC existe, **ACTIVO** y **HABIDO** |
| `sunat_domicilio` | 0.20 | Domicilio fiscal ≈ dirección declarada |
| `maps_operativo` | 0.15 | Negocio **OPERATIVO** en Maps |
| `maps_distancia` | 0.20 | Cercanía declarado ↔ Maps |
| `social` | 0.15 | Antigüedad/actividad en redes |

- Un factor **sin dato** (`None`) se excluye y su **peso se redistribuye** entre
  los disponibles (no penaliza lo que no se pudo evaluar; ej.: cancha sin RUC).
- Umbrales: `>= 70` aprobado (alto), `40–69` revisión manual (medio), `< 40`
  rechazo (bajo).
- El resultado trae `justificacion` + `desglose` por factor → siempre explicable.

## Adaptadores (aislados e intercambiables, todos STUB)
- `adapters/sunat_adapter.py` — RUC: existencia, estado, domicilio, anexos.
  Proveedor por `SUNAT_PROVIDER` (`stub | factiliza | oficial`).
- `adapters/places_adapter.py` — Google Places: coordenadas, operatividad,
  distancia.
- `adapters/social_adapter.py` — antigüedad/actividad de redes y reseñas.
- `adapters/address_normalizer.py` — normaliza y compara direcciones con
  tolerancia de formato (abreviaturas, acentos, puntuación).

> Ningún adaptador llama a servicios reales todavía. Las claves van por `.env`
> (ver `.env.example`).

## Persistencia
`db/schema.sql` define **solo**:
- `verificaciones` (resultado: cancha_id, score, aprobado, nivel, evidencias no
  personales, fecha, TTL).
- `consentimientos` (sujeto, tipo, otorgado, vigencia).

Prohibido por diseño: columnas para imágenes de DNI/recibo/selfie o DNI en claro.

## Cómo correr
```bash
cd backend/onboarding_verificacion/existencia
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # opcional (stubs funcionan sin tocar nada)

uvicorn main:app --reload       # API en http://127.0.0.1:8000/docs
python -m pytest                # tests del scoring
```

## Tests del scoring
`tests/test_scoring.py` cubre: cancha real coincidente (score alto), dirección
que no cuadra (score bajo), negocio en baja en SUNAT (penaliza), redistribución
de peso por factor sin dato y validación de pesos = 1.0.

## Roadmap
1. Activar `factiliza`/oficial en `sunat_adapter` (reemplazar TODOs).
2. Activar Google Places real en `places_adapter`.
3. Conectar `db/repository.py` a Postgres (Supabase) con `schema.sql`.
4. Capa OTP por WhatsApp como verificación de propiedad además de existencia.
