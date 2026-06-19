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
