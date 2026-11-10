import 'dart:io';

import 'package:canchas_lima/theme.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

/// Carga DM Sans (la fuente de la marca) y los íconos Material para que los
/// goldens se vean como la app real (sin fuentes, Flutter pinta cajas).
Future<void> cargarFuentes() async {
  Future<ByteData> leer(String ruta) async => ByteData.view(Uint8List.fromList(await File(ruta).readAsBytes()).buffer);
  final dm = FontLoader('DM Sans')..addFont(leer('test/fuentes/DMSans.ttf'));
  await dm.load();
  final iconos = FontLoader('MaterialIcons')..addFont(leer('test/fuentes/MaterialIcons-Regular.otf'));
  await iconos.load();
}

/// Tema de la app para tests: el MISMO ColorScheme y componentes que
/// `buildTheme()`, con DM Sans cargada localmente (google_fonts no baja nada en tests).
ThemeData temaPrueba({bool oscuro = false}) {
  fuenteDePrueba = 'DM Sans';
  return oscuro ? buildThemeOscuro() : buildTheme();
}

Widget envolver(Widget pantalla, {bool oscuro = false}) => MaterialApp(
      debugShowCheckedModeBanner: false,
      theme: temaPrueba(oscuro: oscuro),
      home: pantalla,
    );

/// Tamaño de un teléfono típico (360×780 dp, densidad 3).
void tamanoTelefono(WidgetTester t, {double alto = 780}) {
  t.view.physicalSize = Size(360 * 3, alto * 3);
  t.view.devicePixelRatio = 3;
}
