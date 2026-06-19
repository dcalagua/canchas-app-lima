import 'package:flutter/material.dart';

import 'models/models.dart';

// ─────────────────────────────────────────────────────────────────────────
// Sistema de color — mood "energético y social" (psicología del color):
//  • Verde   = deporte, confianza, "go", crecimiento / valor.  (marca)
//  • Coral   = acción, entusiasmo, urgencia amable.            (CTAs / convertir)
//  • Lima    = energía, juventud, movimiento.                  (acentos)
//  • Ámbar   = atención sin alarma.                            (seña / horas valle)
// ─────────────────────────────────────────────────────────────────────────
const Color verdeCancha = Color(0xFF12A05C); // primary
const Color verdeClaro = Color(0xFF3DBE82);
const Color verdeOscuro = Color(0xFF0B6B45);
const Color coral = Color(0xFFFF6B57); // acción / CTA
const Color coralOscuro = Color(0xFFE8553F);
const Color lima = Color(0xFFCFF24D); // energía / acentos
const Color arena = Color(0xFFF4A93B); // seña / horas valle
const Color azulPadel = Color(0xFF2E7BE4); // tag pádel
const Color naranjaFutbol = Color(0xFFEF6C2B); // tag fútbol
const Color tinta = Color(0xFF14201B); // texto
const Color fondoApp = Color(0xFFF4F8F5);

/// Color de marca por deporte (para chips, tarjetas y cabeceras).
Color colorDeporte(Deporte d) => switch (d) {
      Deporte.tenis => verdeCancha,
      Deporte.padel => azulPadel,
      Deporte.futbol => naranjaFutbol,
    };

/// Ícono por deporte.
IconData iconoDeporte(Deporte d) => switch (d) {
      Deporte.tenis => Icons.sports_tennis,
      Deporte.padel => Icons.sports_handball,
      Deporte.futbol => Icons.sports_soccer,
    };

ThemeData buildTheme() {
  final scheme = ColorScheme.fromSeed(
    seedColor: verdeCancha,
    primary: verdeCancha,
    onPrimary: Colors.white,
    secondary: coral,
    onSecondary: Colors.white,
    tertiary: arena,
    brightness: Brightness.light,
  ).copyWith(surface: Colors.white);

  return ThemeData(
    useMaterial3: true,
    colorScheme: scheme,
    scaffoldBackgroundColor: fondoApp,
    textTheme: Typography.material2021().black.apply(
          bodyColor: tinta,
          displayColor: tinta,
        ),
    appBarTheme: const AppBarTheme(
      backgroundColor: verdeCancha,
      foregroundColor: Colors.white,
      elevation: 0,
      centerTitle: false,
    ),
    cardTheme: CardTheme(
      elevation: 1,
      color: Colors.white,
      surfaceTintColor: Colors.white,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
    ),
    // Botón de acción por defecto = coral (el color de "convertir").
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: coral,
        foregroundColor: Colors.white,
        padding: const EdgeInsets.symmetric(horizontal: 22, vertical: 14),
        shape:
            RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
        textStyle: const TextStyle(fontWeight: FontWeight.w700, fontSize: 15),
      ),
    ),
    navigationBarTheme: NavigationBarThemeData(
      backgroundColor: Colors.white,
      indicatorColor: verdeCancha.withOpacity(0.14),
      labelTextStyle: WidgetStateProperty.all(
        const TextStyle(fontSize: 12, fontWeight: FontWeight.w600),
      ),
    ),
  );
}
