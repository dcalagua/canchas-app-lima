# Rediseño azul de la web CanchaLibre (9-nov-2026)

Fuente: 7 PDF del diseñador en `Downloads/Soluciones EBIM` (Frame 1–7, 1440 px):
portada, términos + devoluciones + privacidad, calendario "Cuándo", panel
"Hora", ficha de reserva, Libro de Reclamaciones e inicio de sesión.
Rama `feat/web-rediseno-azul` (sale de `feat/web-ronda3`). Solo web; el APK
queda para después. Nada tocó QAS ni PRD.

## Decisiones (por defecto, el usuario no respondió las 4 preguntas)

| Tema | Decisión | Por qué |
|---|---|---|
| Botón principal | Azul `#3056ED` (el verde del PDF no está en la paleta y con texto blanco no llega a AA) | una sola paleta; 5,7:1 |
| Alcance | Solo web | el APK comparte tokens: cambiarlo es otro trabajo (build + Play) |
| Fuente | DM Sans en todo | el PDF mezclaba Open Sans y DM Sans |
| Móvil | Adaptado por nosotros (no hay frames a 390 px) | se probó a 390 px con Playwright |

## Paleta (`web/ui.py::TOKENS`)

`--azul #3056ED` (marca, CTA, barra, pie) · `--azul-osc #2442C4` (hover, texto
sobre tinte) · `--azul-claro #7E98FF` (SOLO decoración: blanco encima = 2,7:1)
· `--azul-tinte #E3E8FF` (franjas, fondos suaves) · `--carbon #333333` (texto).
Los nombres históricos siguen (`--esmeralda` = CTA, `--noche` = texto,
`--tinte`, `--teal`) para no tocar ~200 usos. El verde queda solo para estados
(`--ok-*`: pagado, verificado). 150 líneas con verdes de marca a mano pasaron
a la escala azul (`web/*.py`, `legal/*`).

## Qué cambió

- **Cabecera** (`ui.cabecera`): tres franjas. Barra azul fija (logo blanco ·
  Cómo funciona · Centro de ayuda · Modo anfitrión · "Iniciar sesión o
  registrarse" / avatar · ☰), fila blanca de pastillas por deporte con ícono de
  línea, franja celeste con el buscador grande + amenidades rápidas + Filtros
  (o el buscador chico en páginas interiores). El `<header>` es
  `display:contents`: solo la barra queda fija, sin saltos al hacer scroll. En
  modo anfitrión las pestañas van blancas dentro de la barra y no hay franja.
- **Íconos**: `web/iconos.py` (SVG de línea, `currentColor`) para deportes,
  buscador, secciones de la portada, amenidades, chat, bodega y Libro.
- **Logo**: `static/brand/cl_*` (sacados de los PDF con transparencia). Con la
  marca CanchaLibre y sin logo subido en la torre, `ui.wordmark()` usa el
  isotipo + wordmark del diseñador (`color="azul"` sobre fondo claro); con otra
  marca o con logo de la torre, lo de antes. `marca_logo` ahora tiene de
  respaldo `logo_canchalibre.png` (512 px) y `logo_canchalibre_og.png` (1200×630).
- **Portada** (`legal/home.html`, estilos propios bajo `.marca`): Qué ofrecemos y
  Cómo funciona en franja azul; Servicios y precios con íconos azules, Pro en
  azul y Bono con reloj; Pagos (blanco · azul · tinte); Contacto en gris con el
  panel azul "¿Tienes una cancha?"; Términos en tarjetas 4×2; Devoluciones y
  Privacidad en franja oscura; Libro con pastillas.
- **Explorador**: tarjetas con fondo y sombra, sello verde "Verificada",
  corazón en círculo, títulos azules, 3 columnas a 1440 px.
- **Ficha**: "Escribir al local" azul y "Bodega del local" negro; sello verde.
- **Pie** azul con el logo apilado, isotipo de fondo y el Libro en rojo.
- **Login** (`/entrar`): logo vertical azul + ilustración (≥1200 px).
- **Libro** (`/libro-de-reclamaciones`): título azul con ícono, distintivo rojo
  "LIBRO DE RECLAMACIONES", proveedor en caja celeste, Tipo y Reclamo/Queja como
  pastillas, definiciones legales a la vista, "Enviar reclamo".
- **`/legal/*`**: barra azul con logo y DM Sans (antes verde bosque).

## Errores del PDF que NO se copiaron

Sin tildes ("Que ofrecemos", "Peru"…); "Academias y clases" con el texto de
otra tarjeta; "Pro · S/ 12 por hora" (es mensual y ahora sale de la torre:
`pro_precio_soles`); "precio con signo S/" y "precios en Soles" (multi-país);
"Verificada" en "Más canchas cerca de ti" (son locales sin registrar); proveedor
vacío en el Libro; botón "Filtros" dentro de la ficha; textos de ~10 px.

## Pendiente (con su costo)

- **"Ver más resultados"** (3.ª tarjeta del PDF): falta definir el
  comportamiento (¿limitar la grilla y paginar?). Hoy se muestran todas.
- **APK**: llevar la misma paleta a `lib/theme.dart` y `lib/ui/ds.dart` y los
  logos a los assets (build nuevo y Play).
- **Torre `/admin`** y **correos de pago** siguen con su estética (fuera del PDF).
- Confirmar con el diseñador: la versión móvil, la cabecera con sesión y las
  pantallas que no dibujó (Mis reservas, Perfil, modo anfitrión).

## Verificación

- `python -m pytest` → 1049 pasan (nuevo `tests/test_rediseno_azul.py`).
- `tests/e2e/barrido.mjs` contra Postgres local con la semilla: **204
  pantallas, 0 fallas** (390 y 1440 px; sin desbordes, errores JS, diálogos ni
  violaciones de CSP).
