# Rediseño del MODO ANFITRIÓN web (16-nov-2026)

Fuente: 40 capturas del diseñador en `~/Downloads/Soluciones EBIM_2` (1280 px,
solo escritorio). Es la 2.ª entrega: la 1.ª (portada, legales, ficha, login,
Libro) ya está en `feat/web-rediseno-azul` (`docs/plan/REDISENO_AZUL.md`).
Rama de trabajo: `feat/web-rediseno-anfitrion` (sale de `feat/web-rediseno-azul`).
Solo web. Nada toca QAS ni PRD.

## 1. Qué propone el diseño

**Una barra superior blanca** (logo azul · 5 menús desplegables · pastilla
"Modo anfitrión" · avatar) reemplaza al menú de tarjetas de `/anfitrion` y a las
pestañas Hoy/Calendario/Reservas/Ingresos/Canchas. Los 5 menús son EXACTAMENTE
los grupos que ya existen en `web/anfitrion.py::GRUPOS_MENU`:

| Menú | Ítems (todos ya existen en la web) |
|---|---|
| Mi club (7) | Mis canchas · Cobros del club · Pagos por confirmar · Encargados · Reglas de reserva · Disponibilidad · Reservas fijas |
| Negocio (7) | Reportes · Caja del día · Clientes · Llenar cancha · Recordar reservas · Bonos · Mis campeonatos |
| Academia (3) | Mi academia · Cobros de academia · Plan Academia |
| Comercio (2) | Mi tienda · Mi bodega |
| Roles (2) | Soy boleador · Verificador |

Cada desplegable ("Ventanas color.png") = encabezado del grupo + "N opciones" +
filas con ícono blanco sobre cuadrado de color propio, título, descripción y ›.
Cada módulo se ve como **una vista**: fondo celeste, "‹ Título", subtítulo, una
acción principal a la derecha y tarjetas blancas.

Conclusión: **no hay módulos nuevos; es navegación + presentación**, con un
puñado de funciones nuevas (sección 3). Hallazgo colateral: hoy academia,
tienda, bodega, campeonatos, boleador y verificador muestran la cabecera del
JUGADOR; la barra nueva se aplica a TODO `/anfitrion/*` y lo corrige.

## 2. Inventario: captura → ruta actual → tipo de cambio

V = visual/maquetación sobre datos que ya existen · F = función nueva.

| Captura | Pantalla | Ruta actual | Cambio |
|---|---|---|---|
| CanchaLibre Anfitrión (+ Variante Logo) | Inicio del anfitrión | `/anfitrion` (menú de tarjetas) | V+F: tablero (4 KPI, calendario semanal de una cancha, Pendientes de hoy, Ingresos 7 días, Accesos rápidos) |
| Modo Anfitrión - Mi Club / Negocios / Academia / Comercio / Roles, Ventanas color | Desplegables | — | V: barra + mega-menú |
| Frame 8, 9, 10 | Mis canchas | `/anfitrion/mis-canchas`, `/calendario`, `/canchas` | V+F: columna de locales→canchas con filtro + calendario semanal de la cancha elegida; vista **Día**; menú contextual sobre el turno (reserva manual / bloquear turno / **bloquear todo el día**) y sobre la reserva (pagada / WhatsApp / detalle / cancelar); aviso de fotos; "Sincronizar con Google Calendar" = la agenda iCal que ya existe |
| Frame 11, 12, 13 | Agregar local (asistente 4 pasos) | `/anfitrion/nueva` (un solo formulario) | V+F: pasos con vista previa "Así lo verán los jugadores" y lista "Para publicar necesitas"; **Guardar borrador**; correo de contacto; "días que atiende" y "precio en horario punta" (se guardan como reglas) |
| Frame 14 (Frame 23 = versión vieja) | Cobros de tu club | `/anfitrion/cobros-club` | V |
| Frame 15 | Pagos por confirmar | `/anfitrion/pagos-por-confirmar` | V |
| Frame 16 | Encargados | `/anfitrion/encargados` | V |
| Frame 17 | Reglas de reserva | `/anfitrion/reglas/{id}` | V+F: **Copiar a otra cancha**; política de **no-show**; interruptor **"Aceptar cobrar en cancha"** (el diseñador avisa: "valores de ejemplo") |
| Frame 18 | Disponibilidad | `/anfitrion/disponibilidad` | V+F: "Cerrar todo el día", "Abrir horas valle" |
| Frame 19, 20 | Reservas fijas + modal | `/anfitrion/fijas` | V (vista previa "Se crearán 4 reservas") |
| Frame 21 | Reportes · Resumen | `/anfitrion/reportes` | V: pestañas, gráfico de barras 7/30 días |
| Frame 22 | Ocupación | `/anfitrion/ocupacion` | V+F: 4 KPI y dos **sugerencias automáticas** (hora que se llena / mañana vacía) |
| Frame 24 | Ingresos | `/anfitrion/ingresos` | V (sale de Reportes → Billetera) |
| Frame 25 | Caja del día | `/anfitrion/caja` | V: "Por dónde entró la plata" |
| Frame 26 | Base de clientes | `/anfitrion/clientes` | V |
| Frame 27 | Llenar cancha | `/anfitrion/llenar` | V: "Así les llega" |
| Frame 28 | Recordar reservas | `/anfitrion/recordatorios` | V |
| Frame 29 | Bonos | `/anfitrion/bonos` | V |
| Frame 30 | Mis campeonatos (vacío) | `/anfitrion/campeonatos` | V |
| Frame 31 | Cobros · academia | `/anfitrion/cobros` | V |
| Frame 32 | Mi academia | `/anfitrion/academia` | V: 10 accesos de gestión |
| Frame 33 | Plan Academia | `/anfitrion/academia/plan` | V |
| Frame 34 | Mi tienda | `/anfitrion/tienda` | V |
| Frame 35 | Mi bodega (sin Pro) | `/anfitrion/bodega` | V |
| Frame 36 | CanchaLibre Pro | `/pro` | V |
| Frame 37 | Soy boleador (verificar DNI) | `/anfitrion/boleador` → `/cuenta/identidad` | V: la verificación dentro de la página |
| Frame 38 | Verificador | `/anfitrion/verificador` | V |
| CanchaLibre Perfil | Mi perfil del anfitrión | piezas en `/perfil`, `/cuenta/*` | V+F: **preferencias de notificación**, **cerrar sesión en todos los dispositivos** |

## 3. Funciones nuevas que pide el diseño (con su costo)

1. **Tablero de inicio**: compone datos que ya hay (caja, comprobantes, ocupación, reservas). Medio.
2. **Mis canchas unificado** + vista Día + bloquear todo el día. Medio-alto (el calendario ya existe con modal; pasa a menú contextual).
3. **Asistente "Agregar local"** con borrador. Alto: el registro hoy es un formulario con reglas duras (GPS ≤ 150 m, 3-5 fotos propias, reclamo). El diseño OMITE la verificación (WhatsApp, relación con el local, documento, evidencia, GPS): **se conserva** en el paso 4.
4. **Reglas**: copiar a otra cancha (bajo), no-show (medio: hoy no hay política de no-show en reglas), aceptar cobrar en cancha (medio: hoy lo decide la seña).
5. **Preferencias de notificación** por tipo (medio: filtrar push y correos por preferencia).
6. **Cerrar sesión en todos los dispositivos** (bajo: época por usuario en la cookie firmada). "Sesiones abiertas" con lista NO es posible sin registrar sesiones; se ofrece el cierre global.
7. **Idioma**: la plataforma es solo español → no se muestra el selector.
8. **Sugerencias de ocupación** (bajo: reglas sobre el mapa de calor).

## 4. Errores del diseño que NO se copian

- "Modo anfitrion" sin tilde.
- **"S/" fijo** en todas partes (regla MULTI-PAÍS): moneda por país/cancha/billetera.
- Precios fijos: Pro "S/ 12", Plan Academia "S/ 11.50", comisión "5 %" → salen de la torre.
- **Botones verdes** (Editar, Guardar cambios, Invitar, Guardar cancha, Recargar saldo): azul `#3056ED` como en la 1.ª entrega; el verde queda solo para estados.
- "Un verificador lo visita" (Agregar local): el flujo real es aprobación del reclamo con fotos propias y GPS.
- "Mensaje o promo (opcional)" de texto libre en Llenar cancha: se mantienen los chips de descuento (regla "sin texto libre").
- Marcadores del diseño ("Información detallada", "—", "— %"): van datos reales.
- Textos de 9-10 px (gráfico del tablero, accesos rápidos): mínimo 12 px.
- Pro "Prioridad en torneos" y "Apoyas tu comunidad": no son beneficios implementados → no se prometen.
- Boleador con Bolivia en el selector: en BO la verificación es solo en el app (documento + selfie) → se avisa.

## 5. Decisiones por defecto (cambiar si el director dice otra cosa)

| Tema | Decisión |
|---|---|
| Logo de la barra | **Apilado** ("CanchaLibre Anfitrión Variante Logo": el usuario envió esa captura como la página principal); `static/brand/cl_apilado_azul.png` sale del blanco del pie recoloreado |
| Botón principal | Azul (igual que la 1.ª entrega) |
| Pie | En todas las páginas (el diseño solo lo dibuja en el inicio) |
| Móvil | Adaptado por nosotros: ☰ con acordeón de los 5 grupos (no hay frames a 390 px) |
| Encargado (Recepción) | La barra solo muestra lo que su rol puede abrir (`permisos`) |
| Alcance | Solo web; el APK después |

## 6. Fases de ejecución

Cada fase: tests (`python -m pytest`), barrido e2e (`tests/e2e/barrido.mjs`,
390 y 1440 px), commit en la rama. Nada a QAS/PRD sin orden del director.

| Fase | Contenido | Estado |
|---|---|---|
| **F0 · Fundación** | Barra blanca con los 5 desplegables y móvil (☰ acordeón) en TODO `/anfitrion/*`; íconos de color por módulo; fondo celeste; encabezado de vista "‹ Título + acción"; kit de componentes (tarjeta KPI, panel, tabla, segmentado, píldoras de estado). Las pestañas Hoy/Calendario/… pasan a sub-navegación de Mis canchas hasta F2 | **hecha** (barra, íconos, fondo, móvil; el kit de vistas se arma con F1) |
| F1 · Inicio | Tablero de `/anfitrion` (KPI reales, mini-calendario, pendientes, ingresos 7 días, accesos rápidos); invitaciones de encargado arriba. **Es la página principal** del modo anfitrión (aclarado por el usuario, 16-nov) | **hecha** |
| F2 · Mis canchas | Columna de locales + calendario semanal/día + menús contextuales + bloquear día + aviso de fotos + iCal | pendiente |
| F3 · Mi club | Cobros del club, Pagos por confirmar, Encargados, Reglas (+copiar, no-show, cobrar en cancha), Disponibilidad (+cerrar día, abrir valle), Reservas fijas | pendiente |
| F4 · Negocio | Reportes (pestañas + gráfico), Ocupación (+sugerencias), Ingresos, Caja, Clientes, Llenar, Recordar, Bonos, Campeonatos | pendiente |
| F5 · Academia, Comercio, Roles, Pro | Mi academia, Cobros, Plan, Tienda, Bodega, Boleador, Verificador, `/pro` | pendiente |
| F6 · Agregar local | Asistente de 4 pasos con vista previa y borrador, conservando reclamo/GPS/fotos | pendiente |
| F7 · Mi perfil | Página del anfitrión + preferencias de notificación + cerrar sesiones | pendiente |
| F8 · Cierre | Barrido completo, `CLAUDE.md`, memoria | pendiente |

## 7. Preguntas abiertas al director (no bloquean)

2. ¿Reglas: quiere de verdad no-show "Marcar y cobrar" y el interruptor "cobrar en cancha", o eran de ejemplo?
3. ¿Preferencias de notificación también en el APK?
4. ¿Versión móvil del diseñador?
