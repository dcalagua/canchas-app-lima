import 'package:flutter/material.dart';

const Color verdeCancha = Color(0xFF0E7C4A);
const Color verdeClaro = Color(0xFF3DA86E);
const Color arena = Color(0xFFE9A23B); // pelota / horas valle
const Color azulPadel = Color(0xFF2D6CDF);

ThemeData buildTheme() {
  final scheme = ColorScheme.fromSeed(
    seedColor: verdeCancha,
    primary: verdeCancha,
    secondary: arena,
    brightness: Brightness.light,
  );
  return ThemeData(
    useMaterial3: true,
    colorScheme: scheme,
    scaffoldBackgroundColor: const Color(0xFFF6F8F6),
    appBarTheme: const AppBarTheme(
      backgroundColor: verdeCancha,
      foregroundColor: Colors.white,
      elevation: 0,
    ),
    cardTheme: CardTheme(
      elevation: 1,
      color: Colors.white,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
    ),
  );
}
