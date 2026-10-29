# Bitácora — noche WEB de CanchaLibre (28→29-oct-2026)

Rama `feat/noche-canchalibre`. Plan: [`PLAN_NOCHE_WEB.md`](PLAN_NOCHE_WEB.md).
Solo dev/QAS; nada tocó PRD.

**Calidad al cierre**
- Backend: **952 tests pasan** (6 omitidos sin Postgres); 23 nuevos.
- Recorrido real con Playwright (backend local + Postgres de Docker, 390 y
  1440 px): portada, ficha, `/tenis`, flujo de pago con comprobante y 6
  pantallas del anfitrión → sin desbordes, sin errores JS, sin diálogos del
  navegador.
- Portada local: 90 KB de HTML (26 KB con gzip); antes ~366 KB en QAS.

## Hecho

| Fase | Qué | Commit |
|---|---|---|
| W0+W1 jugador | La ficha cobra con la **llave pública del Culqi del club** (antes: la de la plataforma → todo pago rechazado). "Pagar con comprobante": datos del medio con copiar/QR, foto, N.º de operación, cuenta regresiva. Sin cargo por servicio ni puntos en clubes directos; la pasarela de la plataforma ya no cobra sus reservas (BO/EC). "Pago en revisión del club" en Mis reservas y comprobante; rechazados/vencidos con motivo. Política del club en la ficha, día cerrado, franja y luz por turno, límites del club, errores con mensaje. Turnos como botones accesibles. XSS del JSON-LD y configs (`ui.json_js`). Sesión sin constante + `WEB_SESION_SECRETO`. Tope diario sin canceladas. Comprobante sin datos personales para terceros. | `149f5b5` |
| W0.7+W1.5–W1.8+W2.6 anfitrión | Calendario, manual, bloqueo, disponibilidad y fijas con las **reglas del club**. **Cobros de tu club**, **Pagos por confirmar**, **Reglas de reserva** y deuda de comisión en Ingresos, en la web. Menú agrupado; calendario por día en el celular. | `55df773` |
| W2 diseño | Tokens web = APK (CTA `#0B7A57` AA, grises, `--verde`), 142 verdes reemplazados; fotos rotas → respaldo; direcciones sin Plus Code; pestañas con degradado; `/tenis` legible; foco visible, diálogo accesible, 44 px. | `316945e` |
| W3 robustez | gzip; CSS/JS como `/web/a/*.<huella>` con caché inmutable; `private, no-cache`; anti-iframe; CSP solo-reporte (`[csp]` en logs); CSRF por origen; límites por IP; Leaflet diferido con SRI; marca en WhatsApp/.ics/.csv. | `ac3a531` |

## Para probar en QAS (después del push y el redeploy)
1. Reiniciar `pg-backend` si las migraciones 0001–0004 se corrieron después
   del despliegue (la web cachea si existe `reglas_reserva`).
2. `PAGOS_ENC_KEY` en Railway QAS (sin ella el club no puede conectar su Culqi).
3. Opcional: `WEB_SESION_SECRETO` (secreto largo propio de las sesiones web).
   Si no se pone, todo sigue con la clave de siempre.
4. Como dueño (web): Modo anfitrión → **Cobros del club** → conectar Culqi de
   pruebas y/o agregar Yape → **Reglas de reserva** → como jugador reservar
   → pagar con tarjeta de prueba o subir comprobante → **Pagos por confirmar**.
5. Revisar en los logs de Railway líneas `[csp]` (qué bloquearía la CSP) y
   `[csrf]` antes de endurecerlas.

## Pendiente (con su costo)
- Migrar los ~1.250 `style=` restantes a clases (varios días, sin cambio visible).
- CSP en modo bloqueo (tras ver los reportes de QAS).
- Zona horaria por país en la fecha por defecto de `/buscar`, Mis clases y
  "Nueva pichanga" (hoy usan la de Perú; impacto: el día por defecto en Bolivia
  entre 23:00 y 24:00).
- "100 puntos = S/ 3" se muestra también fuera de Perú en Mis puntos.
- Índice `cl_pagos_manuales (jugador_email, creado_en)` cuando haya volumen.
- Rediseño completo del explorador y la ficha.
