# Crecimiento: Puntos/Premios · Solicitudes por Zona · Verificación Física

Tres subsistemas **conectados** que impulsan la captación de oferta de Pichangol,
con anti-fraude y cumplimiento de la **Ley 29733** (no-retención de datos
personales). Backend **FastAPI** (in-memory + `db/schema.sql` para Supabase) y
app **React Native/Expo**. Integraciones externas en **STUB** (no mueve dinero ni
envía nada real).

> Código: `backend/growth/` · App: `mobile/` · Deploy: `Dockerfile`/`railway.json`.

## Cómo se conectan
```
"pide tu cancha" (B) ──acredita──▶ puntos pendientes (A)
        │                                   ▲
        ▼                                   │ libera al verificar/registrar
   ranking por zona ──prioriza──▶ verificación física (C)
                                            │
   IA primero (reusa módulo de existencia)  │ al verificar + 1ª reserva
                                            ▼
                                   premio LIBERADO (A)
```

## A. Puntos y Premios
- **Reglas en `config_incentivos`** (tabla key/value), nunca hardcodeadas.
  Editables en caliente vía `PUT /config/incentivos/{clave}`.
- **Anti-fraude (pendiente → liberado):**
  - `traer_cancha` se libera **solo** cuando la cancha está **verificada Y** tiene
    su **primera reserva real**.
  - `invitar_jugador` y `pedir_cancha`: mismo patrón pendiente→liberado.
  - Los puntos **pendientes no son canjeables**; solo cuentan los liberados.
- **Canje** → genera un **vale** aplicable a una reserva, con su
  `fuente_financiamiento`. Si Pichangol llegó al **tope mensual**, se **bloquean**
  los canjes financiados por Pichangol; los **cofinanciados por el dueño** siguen.
- **Idempotencia**: `POST /puntos/acreditar` y `POST /puntos/canjear` aceptan el
  header `Idempotency-Key`.
- Endpoints: `GET /puntos/saldo/{u}`, `GET /puntos/movimientos/{u}`,
  `POST /puntos/acreditar`, `POST /puntos/canjear`,
  `POST /puntos/eventos/primera-reserva`.

## B. Solicitudes por Zona ("pide tu cancha")
- `POST /solicitudes`: crea la solicitud, acredita puntos **con tope por
  usuario/mes**, deriva la **zona** del distrito y **agrupa** solicitudes cercanas
  (mismo nombre + coordenada ~100 m) para medir **demanda**.
- `GET /solicitudes/ranking?zona=`: ranking de canchas **más pedidas** (esto
  **prioriza a los verificadores**).
- `POST /solicitudes/{id}/registrar`: enlaza la solicitud a una `cancha_id`.
  Cuando esa cancha queda **verificada**, se **libera el premio** del usuario que
  la pidió/trajo.

## C. Verificación Física (carril informal)
Regla rectora: **IA primero, visita solo si hace falta.**
1. `POST /verificacion-fisica/evaluar` corre la **verificación remota por IA**
   (reusa el módulo de existencia: `EXISTENCIA_API_URL`, o stub). Si el score
   supera `umbral_ia_verificacion` → cancha **verificada sin visita**
   (estado `no_requerida`).
2. Si la IA **no concluye** → crea verificación `agendada` y la **asigna por
   zona**, priorizando las canchas más pedidas (cruce con solicitudes).
3. **Mini-app del verificador**: `GET /verificacion-fisica/visitas` (cola
   priorizada por demanda) → captura **fotos GEO del sitio**, confirma
   coincidencia con la ubicación declarada y **firma**:
   `POST /verificacion-fisica/{id}/captura`.
4. Al confirmar → cancha **verificada por carril físico**. La **insignia pública
   es única** ("cancha verificada"); *verificada en persona* se expone como
   **PLUS**, nunca como categoría menor. Internamente se guarda `metodo`
   (`documental` | `en_sitio`).
5. Visita `por_encargo` → se **registra para liquidación** (STUB, sin pago real).

## Transversal (cumplimiento)
- **No-retención**: las fotos de verificación son del **establecimiento**, no
  documentos personales; **no se guardan DNI/recibos**.
- **Consentimientos SEPARADOS**: `puntos` y `contacto` (`POST /consentimientos`).

## Cómo correr
```bash
cd backend/growth
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload     # http://127.0.0.1:8000/docs
python -m pytest              # tests
```

### App Expo (mobile)
```bash
cd mobile
npm install
# apunta la API: EXPO_PUBLIC_GROWTH_API_URL=https://tu-backend npx expo start
npx expo start
```
Pantallas: **Pide tu cancha**, **Mis puntos / canjear**, **Verificador** (lista de
visitas, captura de fotos geo, confirmar/firmar).

## Tests (en `backend/growth/tests/`)
- `test_puntos_antifraude.py`: el premio NO se libera sin verificación + 1ª reserva.
- `test_tope_mensual.py`: al límite, bloquea canje Pichangol y permite dueño.
- `test_priorizacion_zona.py`: la cancha más pedida sale primero.

## Despliegue (Railway)
Igual que los otros servicios: Root Directory `backend/growth`, builder Dockerfile,
healthcheck `/health`. Variable opcional `EXISTENCIA_API_URL` apuntando al módulo
de existencia ya desplegado para que la IA de verificación sea real.

## Roadmap
1. Conectar `db/store.py` a Postgres/Supabase con `schema.sql`.
2. Integrar pagos reales (vales aplicados a reservas; liquidación a verificadores).
3. Notificaciones (push/WhatsApp) para verificadores y para "tu cancha ya está".
