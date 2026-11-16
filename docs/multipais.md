# Multi-país (PE · EC · BO) — pendiente

Plan para llevar Pichangol a **Perú, Ecuador y Bolivia**. Pendiente: se retoma
cuando cierre el piloto Perú (el usuario estará en Bolivia la próxima semana y
seguirá esto ahí). NO empezar los 3 a la vez.

## Estado actual (ya hecho)

- **Moneda por país (display-only):** `lib/utils/moneda.dart` — `monedaSimbolo`
  + `setMonedaPorPais(iso)` (S/ PE · Bs BO · $ EC), fijado por reverse-geocode
  (`isoCountryCode`). Aplica en tarjeta, ficha, carrusel y checkout. **No
  convierte montos**, solo cambia el símbolo.
- **Pasarela de pago SIMULADA:** `services/payments_service.dart` +
  `screens/pago_sheet.dart` (Yape/Tarjeta). Suficiente para demo en EC/BO.
- **Descubrimiento (Google Places) funciona global** (consultas en español) →
  en La Paz/Quito ya se ven canchas reales.

## Lo que falta (el módulo multi-país)

### 1. "País" como configuración
Un `PaisConfig` por país: **moneda · API de identidad · reglas de documento ·
pasarela(s) · wallet**. La app detecta país por GPS → carga la config → moneda,
reclamo y pago usan lo del país. Sumar un país = llenar una config + adaptadores.

### 2. Identidad / reclamo (interfaz `IdentidadService` por país)
Ya existe `backend/growth/propiedad/identidad.py` (Factiliza). Agregar:
- **PE:** Factiliza (DNI 8 + RUC 11). ✅ ya
- **EC:** API del usuario (cédula 10 + RUC 13) → validación automática.
- **BO:** API del usuario valida **RUC/NIT**; **CI personal = entrada manual**
  (nombre + apellido, sin validación automática — el concierge valida por otros
  medios).

### 3. Pagos (interfaz `PaymentsGateway` por país — ya existe la abstracción)
- **PE:** Yape + Culqi.
- **EC:** **DeUna** (wallet, equivalente a Yape) + tarjeta (Kushki o Stripe).
- **BO:** **Yape ya está disponible en Bolivia** → wallet principal; + tarjeta
  (Stripe/Kushki) + QR.
- **Columna de tarjetas:** Stripe (internacional) o **Kushki** (LATAM, unifica
  EC+PE). Los **wallets locales (Yape/DeUna) NO se reemplazan** con Stripe: es
  como paga la mayoría. Regla: tarjetas con Stripe/Kushki; wallet local por país.

### 4. Roadmap sugerido
1. **Ahora:** moneda por país (hecho) + pasarela simulada → demo EC/BO.
2. **Pagos reales:** empezar por **Ecuador** (país más listo: identidad + DeUna
   + tarjetas). Perú ya tiene Factiliza + Yape. Bolivia después (Yape ayuda;
   identidad parcial).
3. Cerrar piloto **Perú** primero; expandir país por país con la config.

## Assets del usuario (confirmados)
- **EC:** API RUC + cédula · DeUna (wallet) · tarjetas de bancos EC · Stripe/Kushki.
- **BO:** API que consulta RUC · CI personal manual (nombre+apellido) · **Yape** ·
  tarjeta vía Stripe/Kushki.
- **PE:** Factiliza · Yape · Culqi.
