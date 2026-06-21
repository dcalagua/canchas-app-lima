# Pichangol Growth — App (Expo / React Native)

App móvil de los subsistemas de crecimiento: **Pide tu cancha**, **Mis puntos /
canjear** y la **mini-app del Verificador** (visitas priorizadas, captura de fotos
geo del sitio, confirmar/firmar).

## Correr
```bash
cd mobile
npm install
# Apunta al backend (backend/growth desplegado o local):
EXPO_PUBLIC_GROWTH_API_URL=https://tu-backend npx expo start
```
Sin la variable, usa `http://localhost:8000` (corre `uvicorn main:app` en
`backend/growth`). Para probar en un dispositivo físico, usa la IP de tu PC o la
URL pública de Railway.

## Pantallas
- `src/screens/PideTuCanchaScreen.tsx` → `POST /solicitudes`.
- `src/screens/MisPuntosScreen.tsx` → `GET /puntos/saldo`, `/movimientos`,
  `POST /puntos/canjear` (bloqueo por tope + opción cofinanciado por el dueño).
- `src/screens/VerificadorScreen.tsx` → `GET /verificacion-fisica/visitas`
  (priorizadas por demanda), cámara (`expo-image-picker`) + ubicación
  (`expo-location`) + `POST /verificacion-fisica/{id}/captura`.

> Las fotos de verificación son del **establecimiento**, no documentos personales.
> No se piden ni guardan DNI/recibos (Ley 29733).
