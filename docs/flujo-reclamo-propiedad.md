# Flujo de reclamo de propiedad — niveles de seguridad y confianza

> Cómo un **dueño, concesionario o arrendatario** reclama su cancha y la activa,
> con verificación escalonada que **transmite confianza** y evita que cualquiera
> se apropie de un local ajeno.

## Principio rector

**Existir ≠ ser dueño. Un RUC válido NO basta.** La propiedad/operación se
prueba demostrando **control real del local**, no con datos públicos (que
cualquiera puede copiar de Google o SUNAT).

## Tres dimensiones independientes (no confundirlas)

| Dimensión | Pregunta | Señales | ¿Habilita reservas? |
|---|---|---|---|
| **Existencia** | ¿La cancha es real? | Google Places, IA de la foto, RUC en SUNAT | ❌ No |
| **Identidad** | ¿Quién reclama? | DNI (Factiliza) + OTP a su WhatsApp | ❌ No |
| **Control / Propiedad** | ¿Controla el local? | OTP al teléfono **público** del local, evidencia, visita en sitio | ✅ Sí |

Solo la tercera habilita reservas. Las tres juntas dan el sello de confianza
para el jugador.

## Niveles de verificación (tiers)

```
N0  Descubierta (Google)         → NO reservable. Solo invita a reclamar.
N1  Identidad confirmada         → DNI válido + OTP al WhatsApp del reclamante
                                    + relación declarada (dueño/concesionario/
                                    arrendatario). Sigue NO reservable.
N2  Control documental           → al menos UNA prueba fuerte de control:
                                    • OTP al teléfono PÚBLICO del local (el que
                                      figura en Google)  ← la más fuerte y barata
                                    • Evidencia: contrato de concesión/alquiler,
                                      recibo de servicios o licencia del local
                                    • Coincidencia RUC ↔ dirección
N3  Validada en sitio            → visita del motorizado: código + GPS coincide
                                    + foto. Máxima confianza.
─────────────────────────────────────────────────────────────────────────────
ACTIVACIÓN → siempre pasa por aprobación HUMANA (concierge) que revisa el
expediente y aprueba/rechaza (panel web, "Reclamos (admin)" in-app o WhatsApp).
```

## Trust score (las señales suman; el umbral decide la vía)

| Señal | Puntos |
|---|---|
| DNI validado (Factiliza) coincide con nombre declarado | +20 |
| OTP al WhatsApp del reclamante | +10 |
| **OTP al teléfono público del local** | **+35** |
| RUC válido y razón social coherente con el local | +10 |
| RUC con dirección que coincide con la ubicación | +10 |
| Evidencia documental (contrato/recibo/licencia) | +25 |
| Foto en sitio con GPS coincidente (selfie en la cancha) | +20 |
| Validación en sitio del motorizado (N3) | +40 |

**Vías según score (a escala):**
- `< 40`  → **rechazo o pedir más pruebas.**
- `40–69` → **revisión humana obligatoria** (concierge).
- `≥ 70`  → **elegible para auto-aprobación** (con revisión por muestreo).

> En el **piloto**, TODO pasa por revisión humana (aprobación directa tras
> verificar). El score se usa para priorizar y, más adelante, automatizar.

## Salvaguardas anti-fraude

1. **El teléfono público del local es el ancla.** El OTP a ese número (el que
   está en Google/Maps) es la prueba más barata y fuerte de control: quien
   contesta esa línea, opera el local.
2. **Contra-reclamo / disputa.** Si dos cuentas reclaman el mismo local, se
   **congela** y va a revisión; gana quien tenga mayor evidencia; se notifica al
   teléfono público para confirmar.
3. **Reversibilidad / impugnación.** Una cancha recién activada puede ser
   impugnada en una ventana de gracia (otro dueño llama); se re-revisa.
4. **Rate-limit.** Un mismo DNI/cuenta no puede activar N locales sin revisión
   manual reforzada (evita "coleccionistas" de canchas ajenas).
5. **Trazabilidad.** Cada reclamo guarda quién, cuándo y con qué evidencia
   (expediente auditable). Borrado durable con tombstones.
6. **Ley 29733.** El DNI es dato personal: se usa solo para validar al dueño,
   **no se publica**, y se conserva lo mínimo.

## Cuando NO hay teléfono público (la realidad del informal)

El OTP al teléfono público es la señal más fuerte, **pero gran parte del informal
no tiene ficha de Google, o el número está deshabilitado/errado, y el dueño no
sabe dónde editarlo.** Por eso el teléfono público **nunca puede ser
obligatorio**: es una señal más, no LA prueba.

**Regla de oro: verificación MULTI-RUTA.** Ninguna señal es única; el dueño
completa las que puede y el score (o el concierge) decide. Rutas de control
alternativas, por costo/fuerza:

1. **Selfie georreferenciada en la cancha (auto-validación en sitio).** El dueño,
   parado en su cancha, toma una foto desde la app; el GPS debe coincidir con la
   ubicación (≤ N m). Prueba presencia física. Barata, escalable, NO depende de
   Google. Reusa la lógica de `validar_en_sitio` (código + GPS), con peso medio
   y revisión humana (presencia ≠ propiedad por sí sola).
2. **Recibo de servicios / contrato / licencia del local.** El informal suele
   tener recibo de luz/agua aunque no tenga Google. Foto del documento.
3. **Reto físico (código en cartel / QR en sitio).** Le damos un código; lo
   muestra escrito en la cancha y manda foto, o escanea un QR que dejamos pegado.
4. **Visita del motorizado (N3).** Para alto valor o casos dudosos.
5. **Verificación comunitaria / referido.** Un dueño ya verificado o un embajador
   de la zona da fe; o reputación por reservas reales cumplidas.

### Presencia ≠ control: por qué una selfie sola NO aprueba

Una selfie+GPS solo prueba que *alguien* está en la cancha — un jugador
cualquiera también coincidiría. Por eso la presencia **nunca aprueba sola**; se
combina con señales de **acceso/control exclusivo** que un jugador no tiene:

- **Reto en zona de control:** mostrar un código (enviado a su WhatsApp) escrito
  a mano en un punto que solo el operador maneja: la oficina/caja, el tablero de
  luces, la puerta con candado. Liga identidad + presencia + control en una foto.
- **Foto de "trastienda":** llaves del local, tablero eléctrico, caja, almacén,
  vestuarios — no solo el campo. El jugador solo accede al campo.
- **Prueba con el local cerrado:** pedir la validación a hora de cierre
  (temprano/noche); quien está adentro con todo cerrado controla el acceso.
- **Documento del local:** recibo de servicios/contrato a su nombre o del
  negocio (el jugador no lo tiene).
- **Liveness + identidad:** foto en vivo (no de galería) ligada al DNI ya
  validado (a futuro, match biométrico cara↔DNI).

### El filtro definitivo: el control se demuestra OPERANDO (y el fraude no paga)

- **El que controla la cancha es el que COBRA.** Con pago en cancha, el dinero lo
  recibe quien opera; un impostor no puede monetizar una cancha ajena.
- **Operar en el tiempo** (gestionar reservas reales, que los jugadores asistan y
  paguen) es la prueba más difícil de falsificar. La activación inicial es
  reversible.
- **Sin incentivo:** reclamar una cancha ajena no rinde (no cobras) y arriesga tu
  DNI real (responsabilidad). Diseñamos para que el fraude **cueste más de lo que
  da**.
- **Contra-reclamo + impugnación + concierge:** el dueño real recupera su cancha;
  el humano decide en la duda.

**El giro estratégico — convertir el reto en valor:** el informal no sabe
gestionar su presencia digital → **Pichangol se la arma**. En el onboarding le
ayudamos a crear/corregir su ficha de Google Business (número, fotos, horario).
Resuelve la verificación a futuro Y es un diferenciador de retención ("te pongo
en Google y te lleno la cancha").

**Red de seguridad:** en el piloto, el **concierge humano** revisa el expediente
y decide; la tecnología asiste, no reemplaza. El **contra-reclamo + ventana de
impugnación** cubren el riesgo residual (si aparece el dueño real, recupera su
cancha). A escala, el score automatiza los casos claros y deja a revisión los
límite.

## Diferencias por tipo de reclamante

- **Dueño:** título / recibo de servicios a su nombre, o RUC del negocio.
- **Concesionario:** **contrato de concesión vigente**; aquí el OTP al teléfono
  del local pesa más que la titularidad del inmueble (opera la cancha aunque no
  sea dueño del terreno).
- **Arrendatario:** contrato de alquiler vigente + autorización para operar.

> Insight comercial: **quien OPERA la cancha** (muchas veces concesionario/
> arrendatario, no el propietario del terreno) es nuestro cliente real. El flujo
> debe servirle a él, no solo al titular registral.

## UX que transmite confianza

- **Sellos públicos por nivel:** "✓ Verificada por Pichangol", "Dueño
  verificado", "Validada en sitio" → el jugador ve seriedad.
- **Checklist del expediente:** barra de progreso ("Te falta: OTP al teléfono
  del local") que guía al dueño y muestra rigor.
- **Explicar el porqué** de cada paso (reduce abandono y comunica seguridad).
- **Diagnóstico in-app** ("Verificar estado ahora") y reenvío de solicitud.

## Estado actual vs recomendado (gap)

**Ya existe en el código:**
- Reclamo con DNI (Factiliza), WhatsApp de contacto, relación, RUC opcional.
- Verificación de **existencia** (IA/growth) separada de propiedad.
- OTP por WhatsApp (Twilio/Meta) — `propiedad/service.py`, adaptadores.
- Aprobación concierge: panel web, in-app y **por WhatsApp** (webhook Twilio).
- **Validación en sitio** (motorizado: código + GPS) — `validar_en_sitio`.
- Trazabilidad del reclamo + tombstones de borrado durable.

**Falta para cerrar el modelo de niveles:**
- [ ] **OTP al teléfono PÚBLICO del local** como señal de control (hoy el OTP es
      al número que pone el reclamante, no necesariamente el público).
- [ ] **Trust score** explícito que sume señales y decida la vía.
- [ ] **Evidencia documental** (subir contrato/recibo/licencia) en el reclamo.
- [ ] **Contra-reclamo / disputa** y ventana de impugnación.
- [ ] **Rate-limit** por DNI/cuenta.
- [ ] **Sellos por nivel** + checklist de expediente en la UI.

## Roadmap de implementación

- **Fase 1 (piloto, ya):** N1 (DNI + WhatsApp) + aprobación concierge. ✅
- **Fase 2 (alto impacto/bajo costo):** OTP al **teléfono público** del local +
  trust score básico + sellos por nivel. ← siguiente paso recomendado.
- **Fase 3:** evidencia documental + contra-reclamo/disputa + rate-limit.
- **Fase 4 (escala):** validación en sitio masiva + auto-aprobación por score
  con muestreo de auditoría.
