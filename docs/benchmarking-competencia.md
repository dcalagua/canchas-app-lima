# Benchmarking competencia — Reva vs EasyCancha vs Pichangol

> Notas de estrategia (no es código). Punto de partida para diferenciarnos y ser
> mejores. Datos de info pública (jul 2026); confirmar cifras directo con cada
> proveedor antes de decisiones finales.

## Qué es cada uno

| | Reva | EasyCancha | Pichangol |
|---|---|---|---|
| Origen | Paraguay → Bolivia (Santa Cruz, Cochabamba), ~200 complejos / 500+ canchas | Chile → Colombia, Ecuador, etc. | PE / BO / EC (nativo multi-país) |
| Modelo con el dueño | Comisión + pagos online | **Mensualidad fija** (SaaS, sin comisión por reserva) | **Comisión por éxito** (saldo estilo inDrive) |
| Fuerte en | Torneos, verificación de jugador (doc + selfie), stats/comunidad, red instalada | Comparador de precios, "Match" (buscar rival), servicios extra (árbitro/pelotero), panel de gestión completo | Descubrimiento automático, academias, concierge de propiedad |

## Lo mejor de cada uno (adoptar como piso)
- **De Reva:** verificación de jugador (documento + selfie) → menos plantones y
  torneos confiables; historial/stats del jugador; comunidad.
- **De EasyCancha:** comparador de precios; "Match"/encontrar con quién jugar;
  servicios extra (árbitro/pelotero); y un **panel de gestión SaaS completo**
  para el club (reservas, pagos, reportes, base de clientes, comunicación) — ese
  panel es el estándar mínimo a igualar.

## Punto de partida (paridad — imprescindibles)
Reservas + pago + **comparador de precios** · panel de gestión completo del club
· torneos · comunidad / "encontrar con quién jugar" · **verificación de jugador**.
Ya tenemos: torneos, reservas, pago, chat, convocatorias. Falta pulir:
**comparador de precios** y **verificación de jugador**.

## Valor agregado (diferenciadores — donde Reva/Easy NO juegan)
1. **Comisión por éxito, no mensualidad.** Easy cobra al dueño todos los meses
   aunque no le reserven; Pichangol solo cobra cuando el dueño gana. Argumento
   de adopción más fuerte de la región.
2. **Descubrimiento automático + concierge de propiedad.** Reva/Easy solo tienen
   las canchas inscritas a mano; Pichangol pone TODAS en el mapa desde el día 1
   (Google Places) y el dueño real la reclama con verificación (OTP/doc). = más
   oferta al instante + anti-fraude de propiedad.
3. **No es solo reservas: es el sistema del negocio deportivo.** Ni Reva ni Easy
   manejan **academias** (alumnos, cuotas, morosos, cobros). Muchos dueños de
   cancha también dan clases → Pichangol administra TODO su negocio.

### Diferenciador #1 recomendado
**Las academias como cuña de entrada.** Ganar al dueño administrándole el negocio
completo (cobros a alumnos + morosos + reportes), algo que la competencia no
toca, y de ahí la demanda del marketplace viene sola. Combinado con "comisión
solo por éxito" + "descubrimiento automático" = propuesta difícil de copiar.

## Backlog derivado (para implementar)
- [ ] Comparador de precios en Explorar (opciones cercanas ordenadas por precio).
- [ ] Verificación de jugador (documento + selfie) → reputación / menos no-shows.
- [ ] "Match" / encontrar con quién jugar (potenciar convocatorias existentes).
- [ ] Servicios extra (árbitro/pelotero) como add-on.
- [ ] Reforzar el panel de gestión del club al nivel SaaS de EasyCancha.

---

## Pasarela de pago Bolivia — Libélula vs Circle.bo

| | Libélula | Circle.bo |
|---|---|---|
| Comisión | **2.5% plano**, sin costo mensual/alta | **3% + Bs 1** por transacción |
| En reserva de Bs 120 | **Bs 3.00** | Bs 4.60 |
| Canales/QR | 7 canales, QR multibanco amplio, tarjetas, wallets | QR + link de pago + negocio físico (más liviano) |
| Facturación SIN | **Sí** | No claro |
| Madurez | Todotix, desde 2009, API probada | Más nuevo/simple |

**Elegimos Libélula** por: más barata (el +Bs 1 fijo castiga tickets chicos y de
alto volumen = reservas), más canales/bancos, **facturación SIN** (clave para la
Arquitectura A donde la plata pasa por Pichangol) y madurez de API.

⚠️ Antes de cerrar: confirmar con Libélula (a) **split / recaudación a terceros**
(liquidar al dueño automáticamente) y (b) precio para nuestro volumen.

## Fuentes
- Reva: https://reva.la/ · https://infonegocios.com.py/conosur/esta-app-nacional-llego-a-bolivia-y-ahora-va-por-el-mercado-argentino-y-colombiano
- EasyCancha: https://marketing4ecommerce.co/asi-es-easycancha-la-app-para-reserva-de-canchas-deportivas-en-colombia/
- Libélula: https://libelula.bo/pasarela-multi-canal/
- Circle.bo: https://circle.bo/
