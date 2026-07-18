import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import 'models/models.dart';

// ─────────────────────────────────────────────────────────────────────────
// PICHANGOL · Tema final — paleta oficial EBIM (grupoebim.com) + DM Sans
//
// Reemplazo directo de lib/theme.dart. Mantiene la MISMA API pública
// (verdeCancha, coral, colorDeporte, iconoDeporte, buildTheme) para no
// romper imports; los nombres viejos quedan como alias.
//
// Paleta (sin negro, todo verde):
//   Lima    #AEEA94  → CTA / energía / acentos (botón grupoebim)
//   Sage    #5AA97F  → superficies hero / color base de la web EBIM
//   Verde   #2E8B66  → estados medios
//   Bosque  #14463A  → primary / CTA oscuro / superficies oscuras
//   Tinta   #123D2D  → texto (verde profundo, reemplaza el negro)
//   Papel   #F4F6F1  → fondo de la app
//
// Marca: wordmark "pichang[o]l" con la 'o' = pelota (anillo + punto lima).
// Eslogan: "Reserva, juega, repite."
//
// Requiere en pubspec.yaml → dependencies: google_fonts: ^6.2.1
// ─────────────────────────────────────────────────────────────────────────

// ── Identidad: estructura AIRBNB (negro Hof + blancos/grises) pero el color de
// ACENTO es el VERDE de WhatsApp (#128C7E), no el coral. Se mantienen los
// NOMBRES de los tokens; solo cambia el valor de `lima`, así todo el acento de
// la app pasa a verde sin tocar cada pantalla.
const Color lima = Color(0xFF128C7E);   // Verde WhatsApp — CTA / acento principal
const Color sage = Color(0xFF484848);   // charcoal (degradado de headers)
const Color teal = Color(0xFF008489);   // Babu — acento secundario (teal)
const Color amarillo = Color(0xFFFFB400); // dorado (calificaciones/energía)
const Color verde = Color(0xFF484848);  // charcoal medio
const Color verdeProfundo = Color(0xFF333333); // charcoal profundo
const Color bosque = Color(0xFF222222); // Hof — texto / superficies oscuras
const Color tinta = Color(0xFF222222);  // texto (Hof near-black)
const Color papel = Color(0xFFF7F7F7);  // fondo app (gris muy claro Airbnb)
const Color papelCalido = Color(0xFFF7F7F7); // fondo panel
const Color trazo = Color(0xFFDDDDDD);  // bordes / divisores (Airbnb)
const Color textoTenue = Color(0xFF717171); // muted (Foggy)
const Color limaSuave = Color(0xFFE3F2EF); // tinte verde WhatsApp suave

/// Gris de texto secundario ADAPTADO al tema: en claro es el Foggy #717171
/// (bien sobre blanco); en oscuro un gris más claro/frío estilo WhatsApp para
/// que las letras chicas (direcciones, precios, horarios) se lean sobre fondo
/// oscuro. Úsalo en vez de `textoTenue` cuando el texto va sobre una superficie
/// que cambia con el tema.
Color textoTenueDe(BuildContext context) =>
    Theme.of(context).brightness == Brightness.dark
        ? const Color(0xFFAEBAC1) // gris claro WhatsApp (dark)
        : textoTenue;

// ── Niveles de destacado (por saldo del dueño): Bronce / Plata / Oro ───────
/// Medalla del nivel de destacado (más saldo = mejor medalla). 0 = ninguno.
String medallaDestacado(int nivel) => switch (nivel) {
      >= 3 => '🥇',
      2 => '🥈',
      _ => '🥉',
    };

/// Etiqueta del nivel de destacado (Bronce / Plata / Oro).
String etiquetaNivelDestacado(int nivel) => switch (nivel) {
      >= 3 => 'Oro',
      2 => 'Plata',
      _ => 'Bronce',
    };

// ── Colores de estado (chips) — sistema de diseño ─────────────────────────
const Color estadoOkBg = Color(0xFFE9F4EE);
const Color estadoOkFg = Color(0xFF1F6E49);
const Color estadoWarnBg = Color(0xFFFDF2D6);
const Color estadoWarnFg = Color(0xFF946200);
const Color estadoBadBg = Color(0xFFFBE7E7);
const Color estadoBadFg = Color(0xFFC0392B);
const Color estadoInfoBg = Color(0xFFE7F0FB);
const Color estadoInfoFg = Color(0xFF1E5FB0);
const Color estadoNeutroBg = Color(0xFFEEF1F1);
const Color estadoNeutroFg = Color(0xFF5C6B6C);

// ── Alias de compatibilidad con el tema anterior ──────────────────────────
const Color pino = bosque;
const Color pinoOscuro = tinta;
// `verdeCancha` se usa en toda la app como acento/relleno de SELECCIÓN (chips de
// día/hora, dots activos, badges "confirmada", íconos). Debe ser el verde
// WhatsApp de la marca, NO el charcoal: mapearlo a `lima` mantiene la app
// congruente sin tocar cada uso. (Antes era `bosque`, por eso salían negros.)
const Color verdeCancha = lima;
const Color verdeClaro = sage;
const Color verdeOscuro = tinta;
const Color clay = textoTenue;  // neutro (gris Foggy)
const Color clayOscuro = Color(0xFFC13515); // rojo Airbnb (estados/vencido)
const Color coral = lima;       // coral Rausch real
const Color coralOscuro = Color(0xFFC13515);
const Color arena = textoTenue;
const Color naranjaFutbol = lima;
const Color fondoApp = papel;

// Superficies de cancha por deporte (armonizan con la identidad nocturna).
const Color arcillaTenis = Color(0xFF3A4066);
const Color azulPadel = Color(0xFF2A2F52);
const Color verdeFutbol = Color(0xFFC4F542);

/// Tinte por deporte (punto del selector de cancha, chips). Paleta Airbnb.
Color colorDeporte(Deporte d) => switch (d) {
      Deporte.tenis => teal,        // Babu
      Deporte.padel => textoTenue,  // Foggy (gris)
      Deporte.futbol => bosque,     // Hof (negro)
      Deporte.pickleball => lima,   // Rausch (coral)
      Deporte.voley => const Color(0xFF3D8BC9),  // azul cielo
      Deporte.basquet => const Color(0xFFE07A3E), // naranja balón
    };

IconData iconoDeporte(Deporte d) => switch (d) {
      Deporte.tenis => Icons.sports_tennis,
      Deporte.padel => Icons.sports_handball,
      Deporte.futbol => Icons.sports_soccer,
      Deporte.pickleball => Icons.sports_tennis, // raqueta (lo más cercano)
      Deporte.voley => Icons.sports_volleyball,
      Deporte.basquet => Icons.sports_basketball,
    };

// ── Amenities / servicios de la cancha (editable por el dueño) ────────────
/// Catálogo de servicios que el dueño puede marcar en su cancha. Se guarda por
/// `clave` en `Cancha.amenidades`; aquí viven la etiqueta y el ícono.
class AmenidadInfo {
  final String clave;
  final String etiqueta;
  final IconData icono;
  const AmenidadInfo(this.clave, this.etiqueta, this.icono);
}

const List<AmenidadInfo> amenidadesCatalogo = [
  AmenidadInfo('vestuario', 'Vestuario', Icons.checkroom),
  AmenidadInfo('duchas', 'Duchas', Icons.shower),
  AmenidadInfo('parking', 'Parking', Icons.local_parking),
  AmenidadInfo('luces', 'Luces', Icons.lightbulb_outline),
  AmenidadInfo('techado', 'Techado', Icons.roofing),
  AmenidadInfo('cafeteria', 'Cafetería', Icons.local_cafe),
  AmenidadInfo('wifi', 'Wi-Fi', Icons.wifi),
  AmenidadInfo('alquiler', 'Alquiler de equipo', Icons.sports_tennis),
];

/// Datos (etiqueta/ícono) de una amenity por su clave; null si no existe.
AmenidadInfo? amenidadPorClave(String clave) {
  for (final a in amenidadesCatalogo) {
    if (a.clave == clave) return a;
  }
  return null;
}

// ── Superficie / tipo de piso de la cancha (editable por el dueño) ────────
/// Tipos de piso disponibles según el deporte. Se guarda como texto libre
/// (la etiqueta) en `Cancha.superficie`. Sirve para categorizar en la lista
/// (loza vs arcilla, etc.) y mostrar un chip en la ficha.
List<String> superficiesDe(Deporte d) => switch (d) {
      Deporte.futbol => const [
          'Grass sintético',
          'Loza',
          'Grass natural',
        ],
      Deporte.tenis => const [
          'Arcilla',
          'Dura',
          'Césped',
          'Loza',
        ],
      Deporte.padel => const [
          'Cristal',
          'Muro',
        ],
      Deporte.pickleball => const [
          'Dura',
          'Loza',
        ],
      Deporte.voley => const [
          'Loza',
          'Arena',
          'Parquet',
        ],
      Deporte.basquet => const [
          'Loza',
          'Parquet',
          'Cemento',
        ],
    };

/// Ícono representativo de una superficie (por palabra clave). Fallback: grid.
IconData iconoSuperficie(String superficie) {
  final s = superficie.toLowerCase();
  if (s.contains('arcilla')) return Icons.terrain;
  if (s.contains('grass') || s.contains('césped') || s.contains('cesped')) {
    return Icons.grass;
  }
  if (s.contains('loza') || s.contains('dura') || s.contains('cemento')) {
    return Icons.grid_4x4;
  }
  if (s.contains('cristal')) return Icons.window;
  if (s.contains('muro')) return Icons.fence;
  return Icons.grid_view;
}

/// Gradiente de "superficie de cancha" — degradado sage→bosque (hero EBIM).
LinearGradient gradienteDeporte(Deporte d) => const LinearGradient(
      begin: Alignment.topLeft,
      end: Alignment.bottomRight,
      colors: [Color(0xFF5A5A5A), sage, Color(0xFF2B2B2B)],
    );

ThemeData buildTheme() {
  final scheme = ColorScheme.fromSeed(
    seedColor: lima,
    primary: lima,           // coral Rausch = acento/CTA principal
    onPrimary: Colors.white, // texto blanco sobre coral
    secondary: bosque,       // negro Hof
    onSecondary: Colors.white,
    tertiary: teal,          // Babu
    onTertiary: Colors.white,
    surface: Colors.white,
    onSurface: tinta,
    brightness: Brightness.light,
  );

  // Tipografía oficial EBIM: DM Sans (display + UI).
  final base = ThemeData(useMaterial3: true, colorScheme: scheme);
  final dm = GoogleFonts.dmSansTextTheme(base.textTheme);
  final textTheme = dm.copyWith(
    displayLarge: dm.displayLarge?.copyWith(fontWeight: FontWeight.w700, letterSpacing: -0.5),
    displayMedium: dm.displayMedium?.copyWith(fontWeight: FontWeight.w700, letterSpacing: -0.5),
    headlineSmall: dm.headlineSmall?.copyWith(fontWeight: FontWeight.w700),
    titleLarge: dm.titleLarge?.copyWith(fontWeight: FontWeight.w700),
  ).apply(bodyColor: tinta, displayColor: tinta);

  return ThemeData(
    useMaterial3: true,
    colorScheme: scheme,
    scaffoldBackgroundColor: papel,
    textTheme: textTheme,
    appBarTheme: const AppBarTheme(
      backgroundColor: papel, foregroundColor: tinta,
      surfaceTintColor: papel, elevation: 0, centerTitle: false,
    ),
    // Tarjetas premium del handoff: radio 20, borde sutil + sombra suave
    // (0 6px 20px -12px rgba(0,0,0,.20) → aprox. con elevation baja).
    cardTheme: CardTheme(
      elevation: 3, color: Colors.white, surfaceTintColor: Colors.white,
      shadowColor: Colors.black.withOpacity(0.18),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(20),
        side: const BorderSide(color: trazo),
      ),
    ),
    // CTA principal Airbnb = coral Rausch con texto blanco. Radio 12.
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: lima, foregroundColor: Colors.white,
        padding: const EdgeInsets.symmetric(horizontal: 22, vertical: 16),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
        textStyle: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16),
      ),
    ),
    // Inputs Airbnb: blanco, borde #DDDDDD, foco negro Hof, radio 12.
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: Colors.white,
      contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: const BorderSide(color: trazo),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: const BorderSide(color: trazo),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: const BorderSide(color: bosque, width: 1.6),
      ),
      labelStyle: const TextStyle(color: textoTenue),
      hintStyle: const TextStyle(color: textoTenue),
    ),
    chipTheme: ChipThemeData(
      backgroundColor: const Color(0xFFF7F7F7),
      labelStyle: const TextStyle(
          fontWeight: FontWeight.w700, fontSize: 12, color: bosque),
      // Chip SELECCIONADO: verde sólido con texto/check blancos (legible en
      // claro y oscuro; antes el verde claro dejaba el texto invisible).
      selectedColor: lima,
      secondaryLabelStyle: const TextStyle(
          fontWeight: FontWeight.w700, fontSize: 12, color: Colors.white),
      checkmarkColor: Colors.white,
      side: const BorderSide(color: trazo),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(999)),
    ),
    // Barra inferior EXACTA a Airbnb: SIN pastilla de fondo al seleccionar.
    // El tab activo se distingue solo por color coral (ícono + texto); el resto
    // en gris Foggy. Nada de sombreado rosa detrás del ítem.
    navigationBarTheme: NavigationBarThemeData(
      backgroundColor: Colors.white, surfaceTintColor: Colors.white,
      elevation: 0,
      height: 64,
      indicatorColor: Colors.transparent, // ← sin pastilla (look Airbnb)
      indicatorShape: const RoundedRectangleBorder(),
      labelBehavior: NavigationDestinationLabelBehavior.alwaysShow,
      labelTextStyle: WidgetStateProperty.resolveWith((s) => TextStyle(
          fontSize: 12,
          fontWeight: FontWeight.w600,
          color: s.contains(WidgetState.selected) ? lima : textoTenue)),
      iconTheme: WidgetStateProperty.resolveWith((s) => IconThemeData(
          size: 26,
          color: s.contains(WidgetState.selected) ? lima : textoTenue)),
    ),
    // Botón secundario (outline) Airbnb: borde/texto negro Hof, radio 12.
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: bosque,
        side: const BorderSide(color: bosque, width: 1.3),
        padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 14),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
        textStyle: const TextStyle(fontWeight: FontWeight.w700, fontSize: 15),
      ),
    ),
    // Botón terciario (texto): negro Hof.
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(
        foregroundColor: bosque,
        textStyle: const TextStyle(fontWeight: FontWeight.w700),
      ),
    ),
    // Elevated = mismo CTA coral+blanco por si alguna pantalla lo usa.
    elevatedButtonTheme: ElevatedButtonThemeData(
      style: ElevatedButton.styleFrom(
        backgroundColor: lima, foregroundColor: Colors.white, elevation: 0,
        padding: const EdgeInsets.symmetric(horizontal: 22, vertical: 16),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
        textStyle: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16),
      ),
    ),
    floatingActionButtonTheme: const FloatingActionButtonThemeData(
      backgroundColor: lima, foregroundColor: Colors.white,
    ),
    // Diálogos: superficie blanca, esquinas suaves, tipografía del sistema.
    dialogTheme: DialogTheme(
      backgroundColor: Colors.white, surfaceTintColor: Colors.white,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      titleTextStyle: textTheme.titleLarge,
      contentTextStyle: textTheme.bodyMedium,
    ),
    // SnackBars flotantes y de marca (las pantallas pueden sobreescribir color).
    snackBarTheme: SnackBarThemeData(
      behavior: SnackBarBehavior.floating,
      backgroundColor: bosque,
      contentTextStyle: const TextStyle(
          color: Colors.white, fontWeight: FontWeight.w600),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
    ),
    dividerTheme: const DividerThemeData(color: trazo, thickness: 1, space: 24),
    listTileTheme: const ListTileThemeData(iconColor: bosque, textColor: tinta),
    switchTheme: SwitchThemeData(
      thumbColor: WidgetStateProperty.all(Colors.white),
      trackColor: WidgetStateProperty.resolveWith((s) =>
          s.contains(WidgetState.selected) ? lima : const Color(0xFFDDDDDD)),
      trackOutlineColor: WidgetStateProperty.resolveWith((s) =>
          s.contains(WidgetState.selected) ? lima : const Color(0xFFB0B0B0)),
    ),
  );
}

// ── Tema OSCURO "Cancha nocturna" ─────────────────────────────────────────
// Fondo índigo casi negro, superficies un escalón más claras, lima eléctrica
// como acento y texto claro. Comparte lenguaje con el tema claro (radios,
// tipografía DM Sans, CTA lima). Se activa con `appState.temaModo`.

// Tokens del tema oscuro (privados; el resto de la app sigue usando los tokens
// claros salvo donde ya se lee del ColorScheme).
const Color _oscFondo = Color(0xFF1A1A1A);      // page (negro Airbnb)
const Color _oscSuperficie = Color(0xFF242424); // tarjetas / appbar
const Color _oscSuperficie2 = Color(0xFF2E2E2E); // inputs / chips
const Color _oscTrazo = Color(0xFF3A3A3A);      // bordes / divisores
const Color _oscTexto = Color(0xFFF2F2F2);       // texto principal
const Color _oscTenue = Color(0xFFA0A0A0);       // texto muted

ThemeData buildThemeOscuro() {
  final scheme = ColorScheme.fromSeed(
    seedColor: lima,
    primary: lima,           // coral Rausch como acento/CTA
    onPrimary: Colors.white, // texto blanco sobre coral
    secondary: lima,
    onSecondary: Colors.white,
    tertiary: teal,
    onTertiary: Colors.white,
    surface: _oscSuperficie,
    onSurface: _oscTexto,
    brightness: Brightness.dark,
  );

  final base = ThemeData(useMaterial3: true, colorScheme: scheme);
  final dm = GoogleFonts.dmSansTextTheme(base.textTheme);
  final textTheme = dm.copyWith(
    displayLarge: dm.displayLarge?.copyWith(fontWeight: FontWeight.w700, letterSpacing: -0.5),
    displayMedium: dm.displayMedium?.copyWith(fontWeight: FontWeight.w700, letterSpacing: -0.5),
    headlineSmall: dm.headlineSmall?.copyWith(fontWeight: FontWeight.w700),
    titleLarge: dm.titleLarge?.copyWith(fontWeight: FontWeight.w700),
  ).apply(bodyColor: _oscTexto, displayColor: _oscTexto);

  return ThemeData(
    useMaterial3: true,
    colorScheme: scheme,
    scaffoldBackgroundColor: _oscFondo,
    textTheme: textTheme,
    appBarTheme: const AppBarTheme(
      backgroundColor: _oscFondo, foregroundColor: _oscTexto,
      surfaceTintColor: _oscFondo, elevation: 0, centerTitle: false,
    ),
    cardTheme: CardTheme(
      elevation: 0, color: _oscSuperficie, surfaceTintColor: _oscSuperficie,
      shadowColor: Colors.black.withOpacity(0.4),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(20),
        side: const BorderSide(color: _oscTrazo),
      ),
    ),
    // CTA principal = coral con texto blanco.
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: lima, foregroundColor: Colors.white,
        padding: const EdgeInsets.symmetric(horizontal: 22, vertical: 16),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
        textStyle: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16),
      ),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: _oscSuperficie2,
      contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(14),
        borderSide: const BorderSide(color: _oscTrazo),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(14),
        borderSide: const BorderSide(color: _oscTrazo),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(14),
        borderSide: const BorderSide(color: lima, width: 1.6),
      ),
      labelStyle: const TextStyle(color: _oscTenue),
      hintStyle: const TextStyle(color: _oscTenue),
    ),
    chipTheme: ChipThemeData(
      backgroundColor: _oscSuperficie2,
      labelStyle: const TextStyle(
          fontWeight: FontWeight.w700, fontSize: 12, color: _oscTexto),
      // Chip SELECCIONADO: verde sólido con texto/check blancos (legible sobre
      // fondo oscuro; el verde claro dejaba el texto casi invisible).
      selectedColor: lima,
      secondaryLabelStyle: const TextStyle(
          fontWeight: FontWeight.w700, fontSize: 12, color: Colors.white),
      checkmarkColor: Colors.white,
      side: BorderSide.none,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(999)),
    ),
    // Barra inferior oscura, mismo criterio Airbnb: sin pastilla; activo coral.
    navigationBarTheme: NavigationBarThemeData(
      backgroundColor: _oscSuperficie, surfaceTintColor: _oscSuperficie,
      elevation: 0,
      height: 64,
      indicatorColor: Colors.transparent,
      indicatorShape: const RoundedRectangleBorder(),
      labelBehavior: NavigationDestinationLabelBehavior.alwaysShow,
      labelTextStyle: WidgetStateProperty.resolveWith((s) => TextStyle(
          fontSize: 12,
          fontWeight: FontWeight.w600,
          color: s.contains(WidgetState.selected) ? lima : _oscTenue)),
      iconTheme: WidgetStateProperty.resolveWith((s) => IconThemeData(
          size: 26,
          color: s.contains(WidgetState.selected) ? lima : _oscTenue)),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: _oscTexto,
        side: const BorderSide(color: _oscTrazo, width: 1.4),
        padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 15),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        textStyle: const TextStyle(fontWeight: FontWeight.w700, fontSize: 15),
      ),
    ),
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(
        foregroundColor: lima,
        textStyle: const TextStyle(fontWeight: FontWeight.w700),
      ),
    ),
    elevatedButtonTheme: ElevatedButtonThemeData(
      style: ElevatedButton.styleFrom(
        backgroundColor: lima, foregroundColor: Colors.white, elevation: 0,
        padding: const EdgeInsets.symmetric(horizontal: 22, vertical: 16),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
        textStyle: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16),
      ),
    ),
    floatingActionButtonTheme: const FloatingActionButtonThemeData(
      backgroundColor: lima, foregroundColor: Colors.white,
    ),
    dialogTheme: DialogTheme(
      backgroundColor: _oscSuperficie, surfaceTintColor: _oscSuperficie,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      titleTextStyle: textTheme.titleLarge,
      contentTextStyle: textTheme.bodyMedium,
    ),
    snackBarTheme: SnackBarThemeData(
      behavior: SnackBarBehavior.floating,
      backgroundColor: _oscSuperficie2,
      contentTextStyle: const TextStyle(
          color: _oscTexto, fontWeight: FontWeight.w600),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
    ),
    dividerTheme: const DividerThemeData(color: _oscTrazo, thickness: 1, space: 24),
    listTileTheme: const ListTileThemeData(iconColor: lima, textColor: _oscTexto),
    switchTheme: SwitchThemeData(
      thumbColor: WidgetStateProperty.all(Colors.white),
      trackColor: WidgetStateProperty.resolveWith((s) =>
          s.contains(WidgetState.selected) ? lima : _oscSuperficie2),
      trackOutlineColor: WidgetStateProperty.resolveWith((s) =>
          s.contains(WidgetState.selected) ? lima : _oscTrazo),
    ),
  );
}
