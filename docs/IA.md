# IA en Pichangol

## Lo implementado: detección de deporte por foto
Al **registrar una cancha**, el dueño sube una foto y la app detecta el deporte
(fútbol/pádel/tenis). Hoy corre una **heurística de visión por color dominante**
100% en el dispositivo (`lib/services/sport_detector.dart`), sin red ni API.

Para producción se reemplaza por un modelo real **sin cambiar la interfaz**:
- **ML Kit (on-device, gratis, offline)**: `google_mlkit_image_labeling` para
  etiquetar la escena (grass, tennis, ball…) y mapear a deporte.
- **Modelo de visión en la nube** (Gemini Vision / Claude Vision / Vision API):
  más preciso, clasifica "cancha de pádel/tenis/fútbol" e incluso estado del
  grass, número de canchas, techada/abierta.

## Lo implementado: descubrimiento de canchas reales (Google Places)
Al abrir la app (o al buscar una zona) Pichangol consulta la **Places API (New)**
de Google y trae las **canchas reales que existen alrededor** —las mismas que
ves en Google Maps— aunque todavía no estén dadas de alta en Pichangol
(`lib/services/places_service.dart`). Se muestran en el mapa con un pin "Ver" y
la etiqueta **"En Google / Reclama tu cancha"**. Es, además, una palanca de
crecimiento: el dueño ve su cancha ya en el mapa y la reclama para recibir
reservas.

**Requisito de configuración (una sola vez):**
1. En Google Cloud Console → APIs y servicios → habilitar **Places API (New)**
   en el mismo proyecto de la `MAPS_API_KEY`.
2. La key debe poder usarse como *web service*: si la restringes a apps Android,
   estas llamadas se rechazan. Para producción, lo ideal es una **key aparte**
   solo para Places (restringida por API, sin restricción de app) o, mejor aún,
   **proxyar la llamada por una Edge Function de Supabase** para no exponer la
   key en el cliente.

> Si la Places API no está habilitada, la app no falla: simplemente no aparecen
> las canchas descubiertas y sigue funcionando con las registradas.

### Fotos automáticas desde Google (sin que el dueño suba nada)
Las canchas descubiertas traen sus **fotos reales de Google** automáticamente:
la Edge Function resuelve cada foto a su `photoUri` público (Places Photos API,
con la key del lado servidor) y la app las muestra en tarjetas y en el carrusel
de la ficha. El dueño solo sube fotos si **reclama** su cancha y quiere
reemplazarlas, o si registra un **local nuevo** que aún no está en Google.

### Registrar una cancha por dirección (geocoding)
Registrar una cancha ya **no depende de una lista de distritos**: el dueño
escribe la dirección, la app la **geocodifica** y coloca el pin en el mapa
(arrastrable para ajustar), igual que en eSupplier. Un mismo local puede tener
**varias canchas de distintos deportes** (selección múltiple): se crea una
cancha por deporte en el mismo punto.

## Otros usos de IA recomendados (alto impacto)
1. **Matchmaking por nivel** (el diferencial del plan): IA que arma partidos
   juntando jugadores de nivel parecido y sugiere "te falta 1 para tu pichanga".
2. **Precios dinámicos**: recomendar al dueño el precio/hora óptimo según
   demanda, día, clima y horas valle (más ingreso en horas muertas).
3. **Predicción de no-show**: estimar probabilidad de plantón por reserva y
   ajustar la seña automáticamente (anti no-show inteligente).
4. **Asistente por WhatsApp/chat**: bot que reserva, responde dudas y reagenda
   en lenguaje natural (con un humano detrás, como manda la estrategia).
5. **Búsqueda en lenguaje natural**: "una cancha de fútbol 7 techada en Surco
   para hoy 8pm barata" → filtra y ordena resultados.
6. **Onboarding de canchas con IA**: a partir de la foto, autocompletar tipo de
   superficie, fotos destacadas y hasta el nombre sugerido.
7. **Moderación y calidad**: detectar fotos falsas/duplicadas o de baja calidad
   al registrar canchas.
8. **Resumen y reputación**: generar reseñas/resúmenes y un "score" de cancha a
   partir de comentarios de jugadores.

## Recomendación de prioridad
Para esta etapa, lo que más mueve la aguja: **(1) Matchmaking por nivel** (es el
gancho social que nadie cubre en Perú) y **(3) Predicción de no-show + seña
dinámica** (protege la confianza del dueño). La detección por foto que ya
implementamos baja la fricción de registrar oferta (Fase 1).
