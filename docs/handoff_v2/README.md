# Handoff: Pichangol — Rediseño UI/UX (app de reserva de canchas)

## Resumen
Rediseño visual completo de **Pichangol**, marketplace de reserva de canchas
de tenis, pádel y fútbol en Lima (estilo "Airbnb de canchas"). Cubre las dos
caras de la app: **jugador** (explorar → reservar → jugar) y **panel del club**
(agenda, reportes, saldo prepago). Dirección: **premium minimalista**.

## Sobre los archivos de este paquete
Los archivos `*.dc.html` son **referencias de diseño hechas en HTML** —
prototipos que muestran el look & feel y el comportamiento esperado, **no código
para copiar tal cual**. La tarea es **recrear estos diseños en el código real de
la app**, que es **Flutter (Dart)**, usando sus patrones existentes (Material 3,
`ThemeData`, los `models` y `sample_data` ya presentes).

`theme.dart` (incluido) **sí es Dart listo para usar**: es un reemplazo directo
de `lib/theme.dart` con los tokens del rediseño y la misma API pública.

## Fidelidad
**Alta fidelidad (hifi).** Colores, tipografía, espaciados y jerarquía son
finales. Recrear las pantallas con fidelidad de píxel usando los widgets de
Flutter del proyecto.

---

## Cómo llevarlo a git y generar el APK

No se hace *push* desde aquí; se aplica en tu repo. Camino recomendado:

1. **Rama nueva** desde la actual:
   `git checkout -b rediseno/ui-premium`
2. **Tema**: reemplaza `lib/theme.dart` por el `theme.dart` de este paquete.
   Añade a `pubspec.yaml` → `dependencies:` la línea `google_fonts: ^6.2.1`
   y corre `flutter pub get`.
3. **Navegación de arranque**: la app abre **directo en Explorar (mapa)** sin
   login. Elimina la pantalla de onboarding como ruta inicial.
4. **Login solo con Google, al reservar**: el login NO es pantalla inicial; se
   dispara como hoja modal al pulsar *Reservar*. Usar `google_sign_in`
   (+ Firebase Auth si aplica). Tras autenticar → continúa al checkout de seña.
5. **Pantallas**: aplica los cambios de layout descritos abajo, pantalla por
   pantalla, reutilizando tus widgets actuales. Marca: wordmark con la "o"-pelota
   y eslogan "Reserva, juega, repite." (ver sección Marca).
6. **Build**: `flutter build apk --release` (o el flujo CI que ya uses).
7. **PR** y merge a tu rama de releases.

> Atajo: puedes abrir este repo con **Claude Code** y pedirle "implementa el
> diseño de `design_handoff_pichangol/` siguiendo el README". El README es
> autosuficiente.

---

## Marca
- **Casa de marca**: Pichangol es un producto de **EBIM** (endorsed brand). EBIM
  aparece discreto como respaldo en login ("Una solución de EBIM") y panel del
  club ("Tu club en la red EBIM") — nunca compite con Pichangol en la UI.
- **Logo**: wordmark **"pichang[o]l"** con la **"o" convertida en pelota**
  (anillo + punto lima). Es el nombre como logo, sin ícono aparte. Versión
  cuadrada (login / app icon): cuadrado bosque con la "o"-pelota en lima.
- **Eslogan**: **"Reserva, juega, repite."**
- **Sellos de confianza**: badge **"✓ Verificada"** (lima) en clubes (lista +
  ficha) y strip de garantías (Verificada · Pago seguro · Soporte). "Club
  Fundador" se mantiene como señal de exclusividad.

## Design Tokens

### Color — paleta oficial EBIM (grupoebim.com), sin negro
| Token | Hex | Uso |
|---|---|---|
| Lima | `#AEEA94` | **CTA / acentos / energía** (botón estilo grupoebim) |
| Sage | `#5AA97F` | Superficies hero (degradado), base de la web EBIM |
| Verde | `#2E8B66` | Estados medios |
| Bosque | `#14463A` | **Primary**, CTA oscuro, superficies oscuras |
| Tinta | `#123D2D` | Texto principal (verde profundo — reemplaza el negro) |
| Texto tenue | `#7C8A80` | Texto secundario |
| Papel | `#F4F6F1` | Fondo de la app (jugador) |
| Papel cálido | `#ECF0E8` | Fondo del panel del club |
| Trazo | `#E0E5DB` | Bordes y divisores |
| Lima suave | `#EFF8E4` | Fondos de chips / avisos / sellos |

- **CTA principal** = fondo **bosque** + texto **lima** (botón "Reservar",
  "Pagar seña"). Botón de acento alterno = fondo **lima** + texto **bosque**.
- **Superficie de cancha** (heros y miniaturas) = degradado **sage** `#80C68A→#5AA97F→#4E9B72`
  con líneas de cancha; el deporte se distingue por el punto del selector, no por color de fondo.
- **Hora valle** = fondo `#EFF8E4`, borde/realce **lima**, texto **bosque** (sin coral).
- **Sello "✓ Verificada"** = fondo lima, texto bosque.

### Tipografía — DM Sans (oficial EBIM)
- **Todo el sistema** usa **DM Sans** (400/500/600/700). Títulos en 700 con
  letter-spacing ≈ -0.02em; el wordmark del logo va en 800.
- Escala móvil: títulos de pantalla 26–28px; H de tarjeta 18px; cuerpo 14–15px;
  metadatos 12–13px; precios 17–22px.

### Radios, sombras, espaciado
- Radios: tarjetas 20px, chips/botones 16px, píldoras 999px, sheets 26–28px arriba.
- Sombra de card: `0 6px 20px -12px rgba(0,0,0,.20)`.
- Padding de pantalla: 18–22px horizontal. Gap entre cards: 14px.
- Barra de tabs: fondo blanco, borde superior `#EEF1EB`, ítem activo en bosque.

---

## Pantallas / Vistas

> Flujo jugador: **Explorar (mapa) → Lista → Ficha de club → Login Google →
> Seña → Mis reservas.** Flujo club: **Agenda → Reportes → Cuenta/Saldo.**

### 1. Explorar · Mapa  (pantalla inicial, sin login)
- **Propósito**: descubrir clubes cercanos en mapa; explorar libre, sin cuenta.
- **Layout**: mapa a pantalla completa; barra de búsqueda flotante arriba
  (ubicación + "Hoy · 1 hora · cualquier deporte" + botón filtros); fila de
  chips de deporte (Todos/Tenis/Pádel/Fútbol); pines de **precio** sobre el mapa
  (el seleccionado en bosque/lima); bottom-sheet inferior con "N canchas cerca" y
  una card de resultado.
- **Componentes**: search pill blanca radio 18px sombra; chips píldora; pines
  píldora con precio "S/70"; card de club en el sheet (miniatura con gradiente de
  deporte + líneas de cancha, badge, nombre, "4 canchas · Tenis · Pádel · Fútbol",
  "desde S/65 /hora").

### 2. Explorar · Lista  (clubes, no canchas sueltas)
- **Propósito**: ver clubes ordenados por cercanía.
- **Layout**: título "Clubes en San Borja" + subtítulo "8 clubes · 23 canchas";
  lista de cards de club; tab bar.
- **Card de club**: cabecera 128px con gradiente de deporte + líneas de cancha +
  badge ("CLUB FUNDADOR" o "HORA VALLE -20%") + corazón; cuerpo con nombre,
  rating ★, "barrio · distancia · N canchas", **chips de deportes**, precio
  "desde S/XX /hora", y badge verde lima "N horas hoy".

### 3. Ficha de club  (un local = varias canchas / deportes)
- **Propósito**: ver el club, **elegir entre sus canchas** y un horario.
- **Layout**: hero 300px (gradiente del deporte, carrusel de fotos, botones
  back/share/like, dots); sheet de contenido con radio superior; badges
  (CLUB FUNDADOR / DIGITALIZADA); **nombre del club** + "barrio · N canchas ·
  Tenis · Pádel · Fútbol" + rating; fila de amenities (vestuario, parking, luces,
  raquetas); **selector "Elige cancha"** = píldoras horizontales con punto de
  color por deporte (Central·Tenis seleccionada, Pádel 1, Pádel 2, Fútbol 7);
  **Horarios · <cancha>** = chips de hora (valle en lima, elegido en bosque,
  ocupado tachado). Barra fija inferior: precio + hora + botón **Reservar** (bosque/lima).
- **Estado**: cancha seleccionada → cambia precio, deporte (gradiente) y grilla
  de horarios. Hora seleccionada → habilita Reservar.

### 4. Login con Google  (modal al pulsar Reservar)
- **Propósito**: autenticar **solo** cuando el usuario decide reservar. Único
  método: **Google**.
- **Layout**: ficha del club atenuada detrás (overlay `rgba(22,20,15,.55)`);
  bottom-sheet con handle; **logo cuadrado** (bosque, "o"-pelota lima); título
  "Inicia sesión para reservar tu cancha"; subtítulo "Explora y busca libre.
  Solo te pedimos cuenta al confirmar — y siempre es con Google."; card de
  contexto de la reserva (cancha · deporte · fecha-hora · "Seña S/20"); **botón
  blanco "Continuar con Google"** (borde `#E0E5DB`, ícono Google, texto tinta);
  línea de Términos/Privacidad + "Una solución de EBIM".
- **Comportamiento**: éxito → navega al checkout de seña (paso 5) conservando la
  reserva pendiente. Cancelar → vuelve a la ficha (sin perder selección).

### 5. Reserva · Seña anti no-show
- **Propósito**: confirmar y pagar la **seña** (se descuenta del total).
- **Layout**: app bar "Confirmar reserva"; card resumen (miniatura + cancha +
  deporte + "Hoy · 09:00–10:00"); desglose (Cancha 1h S/70 · Comisión Pichangol
  **Gratis** · **Pagas ahora (seña) S/20** · Resto en cancha S/50); aviso lima
  "Tu seña asegura la hora y se descuenta del total. Cancela gratis hasta 6 h
  antes."; método de pago. Barra fija: **Pagar seña · S/20** (bosque/lima).

### 6. Mis reservas
- **Layout**: título "Mis reservas"; tabs Próximas/Historial; **card destacada
  bosque** de la próxima reserva (badge "EN 2 HORAS", club, deporte, hora, "Seña
  pagada S/20", botones "Cómo llegar" lima + "Ver pase"); cards secundarias
  blancas; tab bar (Reservas activo).

### 7. Panel del club · Agenda de hoy
- **Propósito**: el dueño ve la agenda del día por cancha.
- **Layout**: header sage en degradado (saludo + nombre del club + chip **Saldo S/240**;
  mini-KPIs: Reservas hoy / Ocupación % / +N por la app); selector de cancha
  ("Hoy · Cancha Central · Cambiar"); lista de franjas horarias: reservas
  (nombre + nivel + seña), **nueva por app** resaltada (borde lima + badge
  "NUEVA · APP"), franjas libres con toggle "Abierta en la app", fijas con badge
  "FIJO". Tab bar club (Agenda/Reservas/Reportes/Club).
- **Nota multi-cancha**: el selector debe permitir cambiar entre las canchas del
  club (Central·Tenis, Pádel 1, Pádel 2, Fútbol 7) y recargar su agenda.

### 8. Panel del club · Reportes / KPIs
- **Layout**: título "Reportes · <mes>"; card bosque de **Ingresos del mes**
  (S/8,420, badge "↑ 23% vs. mayo", mini bar-chart con últimas barras en lima);
  grid 2 métricas ("42% reservas traídas por la app", "S/180 no-show evitados");
  card insight de **Horas valle** (barra de ocupación verde + sugerencia "Activa
  -20% de 7 a 11 a.m.").

### 9. Panel del club · Cuenta / Saldo prepago
- **Layout**: título "Mi cuenta"; **card de saldo bosque/tinta** estilo tarjeta
  (Saldo Pichangol S/240.00, "Comisiones se descuentan de aquí", botón lima
  **Recargar saldo**); aviso de saldo bajo (verde lima); lista de **Movimientos**
  (recargas en verde +S/200; comisiones −S/7, −S/9 por reserva app).

---

## Interacciones & comportamiento
- Sin login para explorar, buscar, ver fichas y horarios.
- `Reservar` → si no hay sesión, abre hoja de **Login Google**; si hay sesión,
  va directo al checkout.
- Selector de cancha en la ficha y en la agenda recarga datos dependientes.
- Toggle de franja en agenda = abrir/cerrar disponibilidad en la app.
- Transiciones de sheets: slide-up estándar de Material; overlay con fade.

## Gestión de estado
- `sesión` (Google user) — null mientras explora; requerida solo para reservar.
- `reservaPendiente` (club, cancha, deporte, fecha, hora, seña) — persiste a
  través del login.
- `canchaSeleccionada` en ficha y en agenda del club.
- Filtros de explorar (ubicación, deporte, fecha, duración).
- Datos: reutilizar `models/models.dart` y `data/sample_data.dart`.

## Assets
- No se usan fotos reales (las canchas se muestran con **gradiente por deporte +
  líneas de cancha** dibujadas). Cuando haya fotos del club, reemplazan el hero
  y las miniaturas. Íconos: Material Icons (ya en uso) — ver `iconoDeporte()`.
- Logo: wordmark **"pichang[o]l"** con la "o" = pelota (anillo + punto lima);
  versión cuadrada bosque con la "o"-pelota lima para login / app icon.
  Logos EBIM de respaldo en `assets/` (blanco, teal, isotipo).

## Archivos de este paquete
- `Pichangol Rediseño.dc.html` — prototipo de las 9 pantallas + sistema de marca.
- `support.js` — runtime para abrir el prototipo en el navegador.
- `theme.dart` — **tema Flutter listo** (reemplazo de `lib/theme.dart`).
- `snippets_dart/screens_clave.dart` — **código Dart de arranque** para 2 pantallas
  clave: ficha de club con selector de canchas y hoja de login con Google.
- `snippets_dart/agenda_y_tarjeta_club.dart` — agenda del club con **selector de
  cancha** (multi-deporte) y la **tarjeta de club** del listado/mapa.
- `screenshots/` — captura de cada pantalla (referencia visual):
  `01-explorar-mapa`, `02-explorar-lista`, `03-ficha-club`, `04-login-google`,
  `05-reserva-sena`, `06-mis-reservas`, `07-agenda-club`, `08-reportes-kpis`,
  `09-cuenta-saldo`.

> Nota: para el botón de Google usa el logo "G" oficial (`assets/google_g.png`)
> según las *Google Sign-In Branding Guidelines*. Para el login real:
> `google_sign_in` (+ Firebase Auth si centralizas sesión).
