# Plan de mejoras de la web — ronda 2 (29-oct-2026)

> **Estado (29-oct-2026):**
> - **Hecho:**
>   - P0 completo.
>   - P1: billetera, puntos, ficha y galería, comprobante, Pro, accesibilidad y campeonato sin Pro.
>   - P2: 1 calificar, 2 lista de espera, 3 favoritos, 4 reprogramar, 5 notificaciones, 6 centro de ayuda,
>     7 SEO (sitemap, páginas por zona, h1, JSON-LD de academia), 8 instalable (manifest), 9 mover el pin
>     (≤ 300 m) y 10 agenda iCal del anfitrión.
>   - P3: errores de JavaScript a los logs (`[js]`).
> - **Pendiente, con su motivo:**
>   - P1 peso de fotos: el Storage de Supabase no redimensiona en el plan actual; hay que generar
>     miniaturas al subir.
>   - P2-11 encargados con permisos y P2-12 dividir el pago: necesitan decisiones de producto
>     (roles; cómo cobrar a varios con Culqi).
>   - P3 CSP en modo bloqueo: esperar los reportes `[csp]` de QAS.
>   - P3 estilos en línea y partir `router.py`: refactor grande sin cambio visible.
>   - P3 Playwright en CI: necesita un Postgres con datos semilla en el job.

Base: barrido con Playwright de **QAS** (`pg.ebim.pe`) con la cuenta de
gep.soporteit@gmail.com (acceso de revisión). Se revisaron **95 pantallas**
(públicas, jugador y anfitrión), en celular (390 px) y en computadora
(1440 px), más el flujo de reserva hasta el pago.

- Ninguna pantalla tuvo errores de JavaScript ni pop-ups del navegador.
- Ninguna pantalla hace scroll horizontal ni tiene imágenes rotas.
- Todas responden 200, salvo la ruta inexistente, que da un 404 en JSON (ver P0-1).
- Los arreglos del commit `e34c765` (ronda 1) aún no están en QAS; aquí no se repiten.

Leyenda de esfuerzo: **S** < ½ día · **M** 1–2 días · **L** 3+ días.

---

## P0 — Bugs y cosas que dañan la confianza

| # | Qué se ve | Mejora | Esf. |
|---|---|---|---|
| 1 | Una URL que no existe muestra `{"detail":"Not Found"}` en texto plano. | Página 404 con la marca: cabecera, buscador y "Ver canchas". Igual para los errores 500. | S |
| 2 | **Barra de reserva en el celular:** el botón "Reservar y pagar S/ 128.00" ocupa 4 líneas y el total se parte en 2. Es el botón más importante de la web. | Dejarlo en "Reservar · S/ 128", con el total en una línea y el medio de pago en un chip. | S |
| 3 | **Textos que mandan al app** cuando la web ya lo tiene. | Enlazar a la pantalla web en vez de "En la app". | S |
|   | — Configuración → "Invita y gana · En la app" | La web ya tiene `/referidos`. | |
|   | — "Bonos de horas": "se administran desde la app" | La web ya tiene `/anfitrion/bonos`. | |
|   | — Soy boleador: "Verifícate desde la app" | La web ya tiene `/cuenta/identidad` (PE/EC). | |
| 4 | **Verificación de una cancha ya verificada:** la línea de tiempo dice "Aún no hay una solicitud a tu nombre". | Si la cancha está verificada y no hay reclamo, mostrar solo "Verificada". | S |
| 5 | **Lentitud del servidor:** 0,6–0,9 s antes del primer byte (`/tenis` pesa 3,9 KB y tarda 640 ms). `canchas_publicas()` consulta todas las canchas en cada visita, y la ficha la repite (`_hermanas`). | Caché en memoria de 30–60 s, que se borre al editar una cancha. Revisar también la región de `pg-backend` de QAS frente a Supabase us-east-1. | S |
| 6 | **Portada en el celular** mientras busca la ubicación: la primera tarjeta es un local a 30 km y sin foto (dibujo de cancha). | Mientras no hay GPS: ordenar por el centro de la ciudad y poner primero las tarjetas con foto. | S |

## P1 — Experiencia de uso (UI/UX)

**Billetera y pagos**
- El sello "⏸ Pausado" sobre el saldo no se entiende. Hay que explicarlo ("Tu club no aparece destacado") o quitarlo para quien solo juega.
- El aviso rojo "Saldo bajo" se le muestra a cualquiera. Debería salir solo a los dueños con cobro directo y con tono informativo.
- "Estado de cuenta" muestra "Aún no hay movimientos" mientras "Mis pagos" lista 5. Unificar en una sola historia o decir claramente qué es cada una.
- "Mis puntos" dice "Valen S/ 18.90" fijo en soles (pendiente multi-país). "Cómo funcionan" es un bloque largo de texto: pasarlo a un acordeón.

**Ficha y reserva**
- En el celular, la galería muestra una sola foto. Hace falta un carrusel con puntos, como en la portada.
- El comprobante muestra el id crudo ("Comprobante demo_r_0013"). Mostrar un código corto legible y la fecha.
- La tarjeta de bono parte "ahorras 13 %" en dos líneas; el CCI largo también se parte en el sheet de pago.

**Juega ya**
- El texto "Viendo todo Perú (sin tu ubicación)" queda tapado por el botón flotante "Organizar partido".

**Pro**
- La página habla solo del circuito de tenis. Para un dueño, el valor (bodega, campeonatos, reserva manual) no aparece arriba. Hacen falta dos mensajes: jugador y dueño.

**Anfitrión**
- Al abrir "Nuevo campeonato" sin Pro te devuelve a la lista sin decir por qué. Debe abrir el aviso "Es Pro" con el CTA.
- El calendario en el celular necesita una vista por día más compacta: hoy hay que desplazarse mucho para ver la tarde.

**Accesibilidad** (datos del barrido)
- **Sin `<h1>`:** `/liga`, `/pro`, `/anfitrion/boleador`.
- **Campos sin etiqueta:**
  - Editar academia: 17.
  - Pon tu cancha: 3.
  - Marketplace, referidos y canales: 1 cada uno.
- **Elementos tocables de menos de 40 px de alto:** 19–27 por pantalla. La mayoría están en la cabecera: avatar, ☰ y chips.
- **Textos de menos de 12 px:**
  - `/liga`: 19.
  - Ficha: 28.
  - Reporte de academia: 9.

**Peso**
- La portada en el celular transfiere 509 KB y el marketplace 447 KB, sobre todo por fotos de 1200 px en tarjetas de 300 px. Hay que usar `srcset` o pedir la foto al tamaño de la tarjeta (`w=600`).

## P2 — Lo que la web aún no tiene ("por haber")

| # | Función | Por qué | Esf. |
|---|---|---|---|
| 1 | **Calificar después de jugar** (reseñas en la web) + respuesta del dueño | La web muestra ★ pero solo se puede calificar en el app. | M |
| 2 | **Lista de espera** en turnos ocupados | La tabla `pichangol_espera` existe, pero la web no la usa. Llena huecos por cancelación. | M |
| 3 | **Favoritos en la cuenta** + página "Mis favoritos" | Hoy el ♥ vive solo en ese navegador y se pierde al cambiar de equipo. | S |
| 4 | **Reprogramar una reserva** dentro de la política del club | Hoy solo se puede cancelar y volver a reservar. | M |
| 5 | **Centro de notificaciones** (🔔 en la cabecera) | La web no tiene dónde ver los avisos: confirmación de pago, voucher aprobado, partido cerca. | M |
| 6 | **Centro de ayuda / FAQ** real | "Centro de ayuda" lleva a un ancla de la portada. | S |
| 7 | **SEO** | Hoy solo hay `robots.txt` y un único JSON-LD. Es tráfico gratis de Google. | M |
|   | — `sitemap.xml` | | |
|   | — Páginas por deporte y zona (`/canchas/futbol/miraflores`) | | |
|   | — JSON-LD en fichas y academias | | |
|   | — Imagen OG por local | | |
| 8 | **Instalable (PWA):** manifest + íconos | "Agregar a inicio" en iPhone, donde no hay app. | S |
| 9 | **Dueño: mover el pin del local** en la web | Hoy dice "la ubicación se ajusta desde la app". | S |
| 10 | **Dueño: agenda en Google Calendar** (feed iCal privado) | Los dueños viven en su calendario. | S |
| 11 | **Dueño: encargados con permisos** (multiusuario) | Hoy el local se maneja con una sola cuenta de Google. | L |
| 12 | **Jugador: dividir el pago** entre amigos / invitar a la reserva | Es la etiqueta más usada en partidos ("se divide"). | L |

## P3 — Técnica (sin cambio visible)

- Hay 1.284 `style=` en línea en `web/*.py`: pasarlos a clases por módulo, de a poco.
- `web/router.py` tiene 4.388 líneas: separar explorador, ficha, comprobante y sesión.
- Pasar la CSP a modo bloqueo después de revisar los `[csp]` de QAS.
- Llevar el barrido de Playwright de esta ronda a CI: capturas + métricas por pantalla (sin h1, sin label, desbordes), para que una regresión se vea en el PR.
- Monitoreo de errores del navegador (por ejemplo, un endpoint `/web/js-error` que anote en los logs).

---

### Orden sugerido

1. **P0 completo** (1 día): son arreglos chicos con mucho impacto en confianza y conversión.
2. **P1 de reserva, billetera y accesibilidad** (1–2 días).
3. **P2 en este orden: 3, 1, 2, 9, 7, 8**. Primero lo que retiene al jugador y al dueño, después el tráfico.
4. P2 grandes (11, 12) y P3, como proyectos aparte.
