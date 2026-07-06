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

const Color lima = Color(0xFFAEEA94);   // accent / CTA / realce
const Color sage = Color(0xFF5AA97F);   // acento primario (web EBIM)
const Color teal = Color(0xFF056769);   // acento de apoyo (teal)
const Color amarillo = Color(0xFFF2C94C); // acento de energía (pelota, destacado)
const Color verde = Color(0xFF2E8B66);  // medio
const Color verdeProfundo = Color(0xFF3F8A66); // window bar / verde profundo
const Color bosque = Color(0xFF14463A); // primary / superficies oscuras
const Color tinta = Color(0xFF123D2D);  // texto (verde profundo, NO negro — handoff)
const Color papel = Color(0xFFF4F6F1);  // fondo app (page)
const Color papelCalido = Color(0xFFECF0E8); // fondo panel del club
const Color trazo = Color(0xFFE0E5DB);  // bordes / divisores
const Color textoTenue = Color(0xFF7C8A80); // muted
const Color limaSuave = Color(0xFFEFF8E4); // verde soft (tint)

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
const Color verdeCancha = bosque;
const Color verdeClaro = sage;
const Color verdeOscuro = tinta;
const Color clay = sage;        // ya no hay coral; "valle" usa verdes
const Color clayOscuro = verde;
const Color coral = sage;
const Color coralOscuro = verde;
const Color arena = verde;      // antes tono "arena"; ahora verde EBIM
const Color naranjaFutbol = lima;
const Color fondoApp = papel;

// Superficies de cancha por deporte: degradados verdes EBIM (sin azul/coral).
const Color arcillaTenis = Color(0xFF5AA97F);
const Color azulPadel = Color(0xFF2E8B66);
const Color verdeFutbol = Color(0xFFAEEA94);

/// Tinte por deporte (punto del selector de cancha, chips).
Color colorDeporte(Deporte d) => switch (d) {
      Deporte.tenis => bosque,
      Deporte.padel => sage,
      Deporte.futbol => verde,
      Deporte.pickleball => const Color(0xFF2F8F8F), // teal verdoso
    };

IconData iconoDeporte(Deporte d) => switch (d) {
      Deporte.tenis => Icons.sports_tennis,
      Deporte.padel => Icons.sports_handball,
      Deporte.futbol => Icons.sports_soccer,
      Deporte.pickleball => Icons.sports_tennis, // raqueta (lo más cercano)
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

/// Gradiente de "superficie de cancha" — degradado sage→bosque (hero EBIM).
LinearGradient gradienteDeporte(Deporte d) => const LinearGradient(
      begin: Alignment.topLeft,
      end: Alignment.bottomRight,
      colors: [Color(0xFF80C68A), sage, Color(0xFF4E9B72)],
    );

ThemeData buildTheme() {
  final scheme = ColorScheme.fromSeed(
    seedColor: bosque,
    primary: bosque,
    onPrimary: lima,        // texto/íconos lima sobre bosque (no usar negro)
    secondary: lima,
    onSecondary: bosque,
    tertiary: sage,
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
    // CTA principal = bosque con texto lima (botón "Reservar" / "Pagar seña").
    // Radio 16 (handoff premium).
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: bosque, foregroundColor: lima,
        padding: const EdgeInsets.symmetric(horizontal: 22, vertical: 17),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        textStyle: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16),
      ),
    ),
    // Inputs consistentes: blanco, borde del sistema, foco sage, radio 10.
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: Colors.white,
      contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(14),
        borderSide: const BorderSide(color: trazo),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(14),
        borderSide: const BorderSide(color: trazo),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(14),
        borderSide: const BorderSide(color: sage, width: 1.6),
      ),
      labelStyle: const TextStyle(color: textoTenue),
      hintStyle: const TextStyle(color: textoTenue),
    ),
    chipTheme: ChipThemeData(
      backgroundColor: estadoNeutroBg,
      labelStyle: const TextStyle(
          fontWeight: FontWeight.w700, fontSize: 12, color: estadoNeutroFg),
      side: BorderSide.none,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(999)),
    ),
    navigationBarTheme: NavigationBarThemeData(
      backgroundColor: Colors.white, surfaceTintColor: Colors.white,
      indicatorColor: lima.withOpacity(0.45),
      labelTextStyle: WidgetStateProperty.all(
        const TextStyle(fontSize: 11, fontWeight: FontWeight.w700, color: bosque)),
      iconTheme: WidgetStateProperty.resolveWith((s) => IconThemeData(
        color: s.contains(WidgetState.selected) ? bosque : const Color(0xFF9AA89E))),
    ),
    // Botón secundario (outline): borde bosque, texto bosque, radio 12.
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: bosque,
        side: const BorderSide(color: bosque, width: 1.4),
        padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 15),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        textStyle: const TextStyle(fontWeight: FontWeight.w700, fontSize: 15),
      ),
    ),
    // Botón terciario (texto): acción discreta, color de marca.
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(
        foregroundColor: bosque,
        textStyle: const TextStyle(fontWeight: FontWeight.w700),
      ),
    ),
    // Elevated = mismo lenguaje del CTA (bosque + lima) por si alguna pantalla
    // lo usa en vez de FilledButton.
    elevatedButtonTheme: ElevatedButtonThemeData(
      style: ElevatedButton.styleFrom(
        backgroundColor: bosque, foregroundColor: lima, elevation: 0,
        padding: const EdgeInsets.symmetric(horizontal: 22, vertical: 17),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        textStyle: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16),
      ),
    ),
    floatingActionButtonTheme: const FloatingActionButtonThemeData(
      backgroundColor: bosque, foregroundColor: lima,
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
      thumbColor: WidgetStateProperty.resolveWith((s) =>
          s.contains(WidgetState.selected) ? bosque : Colors.white),
      trackColor: WidgetStateProperty.resolveWith((s) =>
          s.contains(WidgetState.selected) ? lima : const Color(0xFFCFD8D2)),
    ),
  );
}
