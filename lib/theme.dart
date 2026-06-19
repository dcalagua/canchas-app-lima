import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import 'models/models.dart';

// ─────────────────────────────────────────────────────────────────────────
// PICHANGOL · Rediseño "Premium minimalista — Airbnb de canchas"
//
// Reemplazo directo de lib/theme.dart. Mantiene la MISMA API pública
// (verdeCancha, coral, colorDeporte, iconoDeporte, buildTheme) para no
// romper imports existentes — los nombres viejos quedan como alias.
//
// Paleta:
//   Pino   #15473A  → marca / superficies oscuras / CTA principal
//   Lima   #CDEE4A  → energía / texto sobre pino / acentos
//   Clay   #E2674B  → horas valle / urgencia amable
//   Tinta  #16140F  → texto
//   Papel  #F7F5F0  → fondo app
//   Por deporte: tenis=arcilla, pádel=azul, fútbol=verde grass
//
// Requiere en pubspec.yaml:
//   dependencies:
//     google_fonts: ^6.2.1
// ─────────────────────────────────────────────────────────────────────────

const Color pino = Color(0xFF15473A); // primary
const Color pinoOscuro = Color(0xFF0E2F26);
const Color lima = Color(0xFFCDEE4A); // accent / energía
const Color clay = Color(0xFFE2674B); // horas valle
const Color clayOscuro = Color(0xFFC0492E);
const Color tinta = Color(0xFF16140F); // texto
const Color papel = Color(0xFFF7F5F0); // fondo app
const Color papelCalido = Color(0xFFF4F2EC); // fondo panel del club
const Color trazo = Color(0xFFEAE5DA); // bordes / divisores
const Color textoTenue = Color(0xFF8A847A);

// Colores de superficie por deporte (gradiente de cancha en cabeceras/cards).
const Color arcillaTenis = Color(0xFFC0573B);
const Color azulPadel = Color(0xFF2F6BD8);
const Color verdeFutbol = Color(0xFF2FA855);

// ── Alias de compatibilidad con el tema anterior ──────────────────────────
const Color verdeCancha = pino;
const Color verdeClaro = Color(0xFF2C6E5C);
const Color verdeOscuro = pinoOscuro;
const Color coral = clay;
const Color coralOscuro = clayOscuro;
const Color arena = clay;
const Color naranjaFutbol = verdeFutbol;
const Color fondoApp = papel;

/// Color de marca por deporte (chips, cards y cabeceras de cancha).
Color colorDeporte(Deporte d) => switch (d) {
      Deporte.tenis => arcillaTenis,
      Deporte.padel => azulPadel,
      Deporte.futbol => verdeFutbol,
    };

/// Ícono por deporte.
IconData iconoDeporte(Deporte d) => switch (d) {
      Deporte.tenis => Icons.sports_tennis,
      Deporte.padel => Icons.sports_handball,
      Deporte.futbol => Icons.sports_soccer,
    };

/// Gradiente de "superficie de cancha" por deporte (para heros y miniaturas).
LinearGradient gradienteDeporte(Deporte d) {
  final base = colorDeporte(d);
  return LinearGradient(
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
    colors: [base, Color.lerp(base, Colors.black, 0.22)!],
  );
}

ThemeData buildTheme() {
  final scheme = ColorScheme.fromSeed(
    seedColor: pino,
    primary: pino,
    onPrimary: lima, // texto/íconos lima sobre pino (CTA principal)
    secondary: lima,
    onSecondary: pinoOscuro,
    tertiary: clay,
    onTertiary: Colors.white,
    surface: Colors.white,
    onSurface: tinta,
    brightness: Brightness.light,
  );

  // Tipografía: Bricolage Grotesque (display) + Hanken Grotesk (UI).
  final base = ThemeData(useMaterial3: true, colorScheme: scheme);
  final display = GoogleFonts.bricolageGrotesqueTextTheme(base.textTheme);
  final body = GoogleFonts.hankenGroteskTextTheme(base.textTheme);

  final textTheme = body.copyWith(
    displayLarge: display.displayLarge?.copyWith(
        fontWeight: FontWeight.w700, letterSpacing: -0.5, color: tinta),
    displayMedium: display.displayMedium
        ?.copyWith(fontWeight: FontWeight.w700, letterSpacing: -0.5, color: tinta),
    displaySmall: display.displaySmall
        ?.copyWith(fontWeight: FontWeight.w700, color: tinta),
    headlineMedium: display.headlineMedium
        ?.copyWith(fontWeight: FontWeight.w700, color: tinta),
    headlineSmall: display.headlineSmall
        ?.copyWith(fontWeight: FontWeight.w700, color: tinta),
    titleLarge: display.titleLarge
        ?.copyWith(fontWeight: FontWeight.w700, color: tinta),
  ).apply(bodyColor: tinta, displayColor: tinta);

  return ThemeData(
    useMaterial3: true,
    colorScheme: scheme,
    scaffoldBackgroundColor: papel,
    textTheme: textTheme,
    appBarTheme: const AppBarTheme(
      backgroundColor: papel,
      foregroundColor: tinta,
      surfaceTintColor: papel,
      elevation: 0,
      centerTitle: false,
    ),
    cardTheme: CardTheme(
      elevation: 0,
      color: Colors.white,
      surfaceTintColor: Colors.white,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(20),
        side: const BorderSide(color: trazo),
      ),
    ),
    // CTA principal = pino con texto lima (botón "Reservar" / "Pagar seña").
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: pino,
        foregroundColor: lima,
        padding: const EdgeInsets.symmetric(horizontal: 22, vertical: 17),
        shape:
            RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        textStyle: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16),
      ),
    ),
    chipTheme: ChipThemeData(
      backgroundColor: const Color(0xFFF0ECE2),
      labelStyle: const TextStyle(
          fontWeight: FontWeight.w700, fontSize: 12, color: Color(0xFF5C574E)),
      side: BorderSide.none,
      shape:
          RoundedRectangleBorder(borderRadius: BorderRadius.circular(999)),
    ),
    navigationBarTheme: NavigationBarThemeData(
      backgroundColor: Colors.white,
      surfaceTintColor: Colors.white,
      indicatorColor: lima.withOpacity(0.35),
      labelTextStyle: WidgetStateProperty.all(
        const TextStyle(fontSize: 11, fontWeight: FontWeight.w700, color: pino),
      ),
      iconTheme: WidgetStateProperty.resolveWith((s) => IconThemeData(
            color: s.contains(WidgetState.selected) ? pino : const Color(0xFFB5AFA3),
          )),
    ),
  );
}
