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

const Color lima = Color(0xFFAEEA94);   // accent / CTA
const Color sage = Color(0xFF5AA97F);   // hero / base EBIM
const Color verde = Color(0xFF2E8B66);  // medio
const Color bosque = Color(0xFF14463A); // primary
const Color tinta = Color(0xFF123D2D);  // texto (verde profundo, NO negro)
const Color papel = Color(0xFFF4F6F1);  // fondo app
const Color papelCalido = Color(0xFFECF0E8); // fondo panel del club
const Color trazo = Color(0xFFE0E5DB);  // bordes / divisores
const Color textoTenue = Color(0xFF7C8A80);
const Color limaSuave = Color(0xFFEFF8E4); // fondos de chips/avisos

// ── Alias de compatibilidad con el tema anterior ──────────────────────────
const Color pino = bosque;
const Color pinoOscuro = tinta;
const Color verdeCancha = bosque;
const Color verdeClaro = sage;
const Color verdeOscuro = tinta;
const Color clay = sage;        // ya no hay coral; "valle" usa verdes
const Color clayOscuro = verde;
const Color coral = sage;
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
    };

IconData iconoDeporte(Deporte d) => switch (d) {
      Deporte.tenis => Icons.sports_tennis,
      Deporte.padel => Icons.sports_handball,
      Deporte.futbol => Icons.sports_soccer,
    };

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
    cardTheme: CardTheme(
      elevation: 0, color: Colors.white, surfaceTintColor: Colors.white,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(20),
        side: const BorderSide(color: trazo),
      ),
    ),
    // CTA principal = bosque con texto lima (botón "Reservar" / "Pagar seña").
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: bosque, foregroundColor: lima,
        padding: const EdgeInsets.symmetric(horizontal: 22, vertical: 17),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        textStyle: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16),
      ),
    ),
    chipTheme: ChipThemeData(
      backgroundColor: const Color(0xFFEDF1EA),
      labelStyle: const TextStyle(fontWeight: FontWeight.w700, fontSize: 12, color: Color(0xFF5C6B62)),
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
  );
}
