import 'package:flutter/material.dart';

import '../theme.dart';

/// Rojo del pin de ubicación (identidad: la 'o' de Pichangol es un pin de mapa).
const Color rojoPin = Color(0xFFE5372B);

/// La 'o' de la marca convertida en PIN DE UBICACIÓN (pin rojo con punto blanco
/// en la cabeza, como un marcador de Google Maps). Sustituye a la vieja pelota.
class PinUbicacion extends StatelessWidget {
  final double size;
  final Color color;   // color del pin
  final Color punto;   // punto interior (cabeza del pin)
  const PinUbicacion(
      {super.key, required this.size, this.color = rojoPin, this.punto = Colors.white});

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: size,
      height: size,
      child: Stack(
        alignment: Alignment.center,
        children: [
          Icon(Icons.location_on, size: size, color: color),
          // Punto en la cabeza del pin (queda en el tercio superior del ícono).
          Positioned(
            top: size * 0.20,
            child: Container(
              width: size * 0.26,
              height: size * 0.26,
              decoration: BoxDecoration(shape: BoxShape.circle, color: punto),
            ),
          ),
        ],
      ),
    );
  }
}

/// Wordmark de marca: **Pichang[o]l** (P mayúscula) con la 'o' convertida en un
/// pin de ubicación rojo.
class PichangolWordmark extends StatelessWidget {
  final double fontSize;
  final Color color;   // color de las letras
  final Color pin;     // color del pin de la 'o'
  final Color punto;   // punto interior del pin
  const PichangolWordmark(
      {super.key, this.fontSize = 26, this.color = bosque,
      this.pin = rojoPin, this.punto = Colors.white});

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
          padding: EdgeInsets.symmetric(horizontal: fontSize * 0.02),
          // El pin va un poco más grande que la letra para leerse como marcador,
          // y baja un pelín para asentar la 'o' en la línea del texto.
          child: Transform.translate(
            offset: Offset(0, fontSize * 0.08),
            child: PinUbicacion(size: fontSize * 0.98, color: pin, punto: punto),
          ),
        ),
        Text('l', style: style),
      ],
    );
  }
}

/// Logo cuadrado (login / app icon): cuadrado bosque con el pin de ubicación
/// rojo en el centro.
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
      child: PinUbicacion(size: size * 0.58, color: rojoPin, punto: Colors.white),
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
