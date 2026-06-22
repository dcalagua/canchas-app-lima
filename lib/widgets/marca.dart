import 'package:flutter/material.dart';

import '../theme.dart';

/// La "o"-pelota del logo: anillo + punto lima (parece una 'o' y una pelota).
class OPelota extends StatelessWidget {
  final double size;
  final Color anillo;
  final Color punto;
  const OPelota({super.key, required this.size, this.anillo = bosque, this.punto = lima});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        border: Border.all(color: anillo, width: size * 0.16),
      ),
      child: Center(
        child: Container(
          width: size * 0.30,
          height: size * 0.30,
          decoration: BoxDecoration(shape: BoxShape.circle, color: punto),
        ),
      ),
    );
  }
}

/// Wordmark de marca: **pichang[o]l** con la 'o' convertida en pelota.
class PichangolWordmark extends StatelessWidget {
  final double fontSize;
  final Color color;   // color de las letras
  final Color pelota;  // punto de la 'o'-pelota
  const PichangolWordmark(
      {super.key, this.fontSize = 26, this.color = bosque, this.pelota = lima});

  @override
  Widget build(BuildContext context) {
    final style = TextStyle(
      fontSize: fontSize, fontWeight: FontWeight.w800, color: color,
      letterSpacing: -0.5, height: 1,
    );
    return Row(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.center,
      children: [
        Text('pichang', style: style),
        Padding(
          padding: EdgeInsets.symmetric(horizontal: fontSize * 0.04),
          child: OPelota(size: fontSize * 0.80, anillo: color, punto: pelota),
        ),
        Text('l', style: style),
      ],
    );
  }
}

/// Logo cuadrado (login / app icon): cuadrado bosque con la 'o'-pelota lima.
class LogoCuadrado extends StatelessWidget {
  final double size;
  const LogoCuadrado({super.key, this.size = 60});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: size,
      height: size,
      alignment: Alignment.center,
      decoration: BoxDecoration(
        color: bosque,
        borderRadius: BorderRadius.circular(size * 0.30),
      ),
      child: OPelota(size: size * 0.52, anillo: lima, punto: lima),
    );
  }
}

/// Sello de confianza "✓ Verificada" (fondo lima, texto bosque). Si fue
/// verificada en persona se expone como PLUS, nunca como categoría menor.
class SelloVerificada extends StatelessWidget {
  final bool enPersona;
  final double fontSize;
  const SelloVerificada({super.key, this.enPersona = false, this.fontSize = 11});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 4),
      decoration: BoxDecoration(color: lima, borderRadius: BorderRadius.circular(999)),
      child: Text(
        enPersona ? '✓ Verificada en persona' : '✓ Verificada',
        style: TextStyle(
            color: bosque, fontSize: fontSize, fontWeight: FontWeight.w800,
            height: 1),
      ),
    );
  }
}
