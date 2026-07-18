import 'package:flutter/material.dart';

import '../theme.dart';

/// La 'o' de la marca convertida en PELOTA (identidad "pichang·o·l": la 'o' es
/// un balón). Verde WhatsApp por defecto, para hablar el idioma de la app.
class PelotaMarca extends StatelessWidget {
  final double size;
  final Color color;
  const PelotaMarca({super.key, required this.size, this.color = lima});

  @override
  Widget build(BuildContext context) =>
      Icon(Icons.sports_soccer, size: size, color: color);
}

/// Wordmark de marca: **Pichang[o]l** (P mayúscula) con la 'o' convertida en una
/// PELOTA. Opción A (monocromo verde): letras charcoal + pelota verde WhatsApp.
class PichangolWordmark extends StatelessWidget {
  final double fontSize;
  final Color color;    // color de las letras
  final Color pelota;   // color de la pelota (la 'o')
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
        Text('Pichang', style: style),
        Padding(
          // La pelota ocupa el lugar de la 'o', al mismo alto que las letras.
          padding: EdgeInsets.symmetric(horizontal: fontSize * 0.03),
          child: PelotaMarca(size: fontSize * 0.92, color: pelota),
        ),
        Text('l', style: style),
      ],
    );
  }
}

/// Logo cuadrado (login / app icon): cuadrado VERDE WhatsApp con una PELOTA
/// blanca al centro (Opción A). Reemplaza el cuadro gris + pin del esquema viejo.
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
        color: lima,
        borderRadius: BorderRadius.circular(size * 0.30),
      ),
      child: PelotaMarca(size: size * 0.58, color: Colors.white),
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
