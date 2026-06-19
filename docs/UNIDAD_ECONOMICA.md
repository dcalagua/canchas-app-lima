# Plan Comercial — Adenda: Unidad Económica por Cancha

> Complemento al **Plan Estratégico Comercial** (v1.0) y a `docs/PLAN_FUTBOL.md`.
> Modela la economía por cancha (CAC, contribución, reservas de equilibrio, payback y
> LTV) diferenciando **fútbol** vs. **tenis/pádel**.
>
> ⚠️ **Todos los números son hipótesis directionales para arrancar**, no verdades.
> Se calibran con datos reales del piloto (ver §7). El objetivo es tener un modelo
> para decidir, no una proyección "exacta".

---

## 1. Supuestos base (a validar)

| Variable | Valor asumido | Nota |
|---|---|---|
| Comisión Fase 2 | **5 %** sobre la reserva NUEVA | Solo reservas que trae la app; nunca la clientela previa del club. |
| Seña anti no-show | 30 % del precio, cobrada por tarjeta | Habilitador, no ingreso propio. |
| Costo de pasarela | ~4 % del monto procesado (la seña) | Culqi/Izipay/Niubiz Perú (aprox.). Lo absorbe la plataforma (conservador). |
| Costo del equipo de captación | ~**S/ 4,000/mes** cargado | 1 ejecutiva de alianzas (fijo bajo + variable por cancha activada). |
| Canchas activadas / mes (en régimen) | ~6 | Tras la rampa; al inicio 3–4/mes. |
| Vida útil de la cancha (retención) | **24 meses** | Para LTV. El churn real es la variable #1 a medir. |

### Reservas NUEVAS por cancha al mes (en madurez)
El fútbol tiene **más rotación** (juega de noche todos los días, grupos recurrentes);
el tenis es de menor volumen.

| Deporte | Reservas nuevas/mes (madurez) |
|---|---|
| Fútbol (sintética 5/7) | **25** |
| Pádel (no premium) | **18** |
| Tenis | **12** |

## 2. Ticket y comisión por reserva

| Deporte | Precio/hora | Comisión 5 % | Seña 30 % | Pasarela 4 % s/seña | **Contribución por reserva** |
|---|---:|---:|---:|---:|---:|
| Fútbol | S/ 120 | S/ 6.00 | S/ 36 | S/ 1.44 | **S/ 4.56** |
| Pádel | S/ 90 | S/ 4.50 | S/ 27 | S/ 1.08 | **S/ 3.42** |
| Tenis | S/ 70 | S/ 3.50 | S/ 21 | S/ 0.84 | **S/ 2.66** |

> *Contribución por reserva = comisión − costo de pasarela.* Es lo que queda por cada
> reserva nueva, antes de costos fijos (equipo, infra).

## 3. CAC por cancha (costo de adquisición de la oferta)

CAC = costo mensual del equipo ÷ canchas activadas por mes.

| Escenario | Canchas/mes | **CAC por cancha** |
|---|---:|---:|
| Rampa (mes 1–2) | 4 | S/ 1,000 |
| Régimen | 6 | **~S/ 667** |
| Optimista | 8 | S/ 500 |

**Usamos S/ 700 como CAC de referencia.** (El CAC es de la *cancha/dueño*, no del
jugador; el CAC del jugador se modela en Fase 2.)

## 4. Contribución por cancha/mes y reservas de equilibrio

| Deporte | Reservas/mes | **Contribución/mes** | Reservas/mes para **payback ≤ 12 meses** |
|---|---:|---:|---:|
| Fútbol | 25 | **S/ 114** | **~13** |
| Pádel | 18 | **S/ 62** | **~17** |
| Tenis | 12 | **S/ 32** | **~22** |

> "Reservas de equilibrio" = cuántas reservas nuevas/mes necesita la cancha para
> recuperar su CAC (S/ 700) en 12 meses. Si una cancha de tenis genera menos de ~22
> reservas nuevas/mes, **a 5 % de comisión no se paga sola** en un año.

## 5. Payback y LTV/CAC — el hallazgo clave

Con CAC S/ 700 y vida útil 24 meses:

| Deporte | Payback (meses) | LTV (24 m) | **LTV / CAC** | Lectura |
|---|---:|---:|---:|---|
| **Fútbol** | **~6.1** | S/ 2,736 | **~3.9x** | ✅ Saludable (>3x). Es el motor económico. |
| Pádel | ~11.4 | S/ 1,478 | ~2.1x | 🟡 Aceptable, no holgado. |
| Tenis | ~21.9 | S/ 766 | ~1.1x | 🔴 Apenas empata: NO se sostiene solo con 5 %. |

**Conclusión dura:** a 5 % de comisión, **el fútbol financia la operación** y el tenis
(y el pádel de bajo volumen) **no se paga solo**. Esto **no significa "no captar
tenis"** —es el hueco estratégico y aporta densidad/red— sino que el tenis necesita
una **palanca extra** para ser rentable (ver §6). Refuerza la mezcla recomendada
**~50 % fútbol** de la adenda de fútbol.

## 6. Palancas para arreglar la economía del bajo volumen

| Palanca | Efecto en tenis (ejemplo) |
|---|---|
| **Suscripción SaaS** S/ 99/mes al club | Contribución tenis: S/ 32 → **S/ 131/mes** · payback **~5.3 meses** · LTV/CAC ~4.5x. Lo arregla por completo. |
| **Comisión diferenciada** (ej. 8 % en bajo volumen) | Sube contribución sin costo fijo para el dueño; ojo con la objeción de precio. |
| **Bajar CAC** (referidos de dueño a dueño, autoalta) | A CAC S/ 400, el tenis baja a payback ~12.5 m / LTV-CAC ~1.9x. |
| **Subir rotación** (matchmaking social) | Cada +5 reservas/mes de tenis = +S/ 13/mes; el gancho social es justamente esto. |

**Recomendación:** Fase 2 con **comisión 5 % en fútbol/pádel** + **plan SaaS opcional
para canchas de baja rotación** (tenis, clubes chicos). Así el motor (fútbol) corre por
comisión y el bajo volumen se vuelve rentable por suscripción.

## 7. Vista de cartera — 100 canchas en madurez (mezcla 50/30/20)

| Deporte | # canchas | Contribución/mes |
|---|---:|---:|
| Fútbol | 50 | S/ 5,700 |
| Tenis | 30 | S/ 957 |
| Pádel | 20 | S/ 1,232 |
| **Total** | **100** | **~S/ 7,889/mes** |

Contra un costo de equipo de ~S/ 4,000/mes, **100 canchas maduras ya dejan
contribución positiva** para sostener captación + infra. El cuello de botella no es el
margen: es **llegar a la densidad y la madurez** (de ahí la "regla de oro" de no lanzar
al jugador antes de 15–20 canchas/zona).

## 8. Las 3 variables a medir primero en el piloto

El modelo entero pivota sobre tres números que **hoy son supuestos**. Medirlos en las
primeras canchas reales vale más que afinar el resto:

1. **Reservas NUEVAS por cancha/mes** (por deporte) — define toda la contribución.
2. **Churn de canchas** (cuántas dejan de usar la app a 30/90 días) — define el LTV.
3. **CAC real** (cuánto cuesta de verdad activar una cancha que SÍ se usa, no solo
   que firma) — define el payback.

> Con esos tres medidos en 10–15 canchas, este documento se recalibra y deja de ser
> hipótesis para convertirse en el modelo financiero de la Serie/inversión.
