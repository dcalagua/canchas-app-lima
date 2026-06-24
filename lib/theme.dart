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
const Color tinta = Color(0xFF0F1B1C);  // texto (tinta del sistema)
const Color papel = Color(0xFFF3F5F5);  // fondo app (page)
const Color papelCalido = Color(0xFFECF0E8); // fondo panel del club
const Color trazo = Color(0xFFE2E8E7);  // bordes / divisores
const Color textoTenue = Color(0xFF5C6B6C); // muted
const Color limaSuave = Color(0xFFE9F4EE); // verde soft (tint)

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
        borderRadius: BorderRadius.circular(12),
        side: const BorderSide(color: trazo),
      ),
    ),
    // CTA principal = bosque con texto lima (botón "Reservar" / "Pagar seña").
    // Radio 12 (sistema de diseño, look ERP-grade más sobrio).
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: bosque, foregroundColor: lima,
        padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
        textStyle: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16),
      ),
    ),
    // Inputs consistentes: blanco, borde del sistema, foco sage, radio 10.
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: Colors.white,
      contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(10),
        borderSide: const BorderSide(color: trazo),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(10),
        borderSide: const BorderSide(color: trazo),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(10),
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
  );
}
