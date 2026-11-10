# Concierge de reservas (primer agente de IA)

El **Asistente Pichangol**: el jugador escribe en lenguaje natural ("fútbol
mañana 8pm por Surco", "una cancha de tenis barata cerca") y el agente le
sugiere canchas ordenadas. Es el primer paso del roadmap "ir metiendo agentes
en todos los procesos".

## Cómo funciona

- **App:** botón flotante ✨ (ícono `auto_awesome`) en la pantalla de
  exploración → pantalla de chat `AsistenteScreen`. La app manda el mensaje + la
  lista de canchas que ya conoce (con distancia si hay ubicación) al backend.
- **Backend (growth):** `POST /concierge/reservas` (`concierge/`). Con la
  API key de Anthropic, **Claude** interpreta la intención (deporte, día, hora,
  zona) y rankea las canchas; devuelve una respuesta amable + sugerencias con
  ids reales de la lista. La API key **nunca** sale del backend.
- **Fail-safe:** sin `ANTHROPIC_API_KEY` (o si Claude falla), cae a una
  heurística (filtra por deporte detectado + ordena por distancia). El asistente
  siempre responde algo útil.

## Paso manual tuyo (para encender la IA)

1. Consigue una API key en <https://console.anthropic.com/> (Anthropic).
2. En **Railway → servicio `pg-backend` → Variables**, agrega:
   - `ANTHROPIC_API_KEY` = tu key (secret).
   - *(opcional)* `CONCIERGE_MODEL` = `claude-haiku-4-5` para bajar costo en
     alto volumen (por defecto usa `claude-opus-4-8`).
3. Redeploy (o espera el auto-deploy del próximo push).

Mientras no pongas la key, el asistente funciona igual pero en modo heurístico
(sin lenguaje natural fino). El costo por uso corre por tu cuenta de Anthropic
(tokens); Haiku es el más barato para este caso.

## Nota de costo

El concierge es alto volumen (cada consulta de un jugador). Empieza con
`claude-haiku-4-5` si quieres el menor costo; sube a `claude-opus-4-8` si
necesitas respuestas más finas. El endpoint sólo manda al modelo el mensaje +
una lista compacta de hasta 40 canchas, así el gasto por llamada es bajo.
