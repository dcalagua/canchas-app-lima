@Tags(['golden'])
library;

import 'package:canchas_lima/widgets/logo_vivo.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:google_fonts/google_fonts.dart';

import 'ayuda_golden.dart';

void main() {
  setUpAll(() async {
    GoogleFonts.config.allowRuntimeFetching = false;
    await cargarFuentes();
  });

  testWidgets('logo en vivo sin logo de la torre (CanchaLibre)', (t) async {
    tamanoTelefono(t, alto: 420);
    await t.pumpWidget(envolver(const Scaffold(body: Center(child: LogoPichangolVivo(ancho: 260)))));
    await t.pump(const Duration(milliseconds: 100));
    await expectLater(find.byType(MaterialApp), matchesGoldenFile('png/logo_vivo.png'));
    await t.pumpWidget(const SizedBox());
  });
}
