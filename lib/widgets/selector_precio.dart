import 'package:flutter/material.dart';

import '../models/models.dart';
import '../theme.dart';

/// PRECIO POR HORA o POR TURNO (pedido del director, 29-sep-2026: "debo tener
/// la opción de cobrar 15 soles la hora o 15 por 1.5 h"). Mismo bloque que la
/// web (`web/anfitrion.py::_bloque_precio`): chips "¿Cómo cobras?", el campo
/// de precio y la vista previa "Cada turno de 1 h 30 cuesta S/ 15.00".
/// Lo usan Editar cancha, Registrar cancha y Agregar cancha.
class SelectorPrecioCancha extends StatelessWidget {
  const SelectorPrecioCancha({
    super.key,
    required this.controller,
    required this.porTurno,
    required this.onPorTurno,
    required this.duracionMin,
    required this.moneda,
    this.onCambio,
  });

  final TextEditingController controller;
  final bool porTurno;
  final ValueChanged<bool> onPorTurno;
  final int duracionMin;
  final String moneda;
  final VoidCallback? onCambio;

  /// Precio escrito (o null si no es válido).
  static double? leer(TextEditingController c) {
    final v = double.tryParse(c.text.trim().replaceAll(',', '.'));
    return (v == null || v <= 0) ? null : double.parse(v.toStringAsFixed(2));
  }

  /// (precioHora, precioTurno) que se guardan en la cancha. Por turno →
  /// `precioHora` = equivalente por hora (APKs viejos cobran igual).
  static (double, double) valores(double precio, bool porTurno, int duracionMin) =>
      porTurno
          ? (Cancha.precioHoraEquivalente(precio, duracionMin), precio)
          : (precio, 0.0);

  /// Lo que cuesta UN turno con lo escrito (vista previa de hora feliz/seña).
  static double turnoDe(double precio, bool porTurno, int duracionMin) =>
      porTurno ? precio : precio * duracionMin / 60;

  @override
  Widget build(BuildContext context) {
    final p = leer(controller);
    final durTxt = Cancha.duracionTexto(duracionMin);
    String? prev;
    if (p != null) {
      final turno = turnoDe(p, porTurno, duracionMin).round();
      prev = porTurno
          ? 'Cada turno de $durTxt cuesta $moneda ${turno.toStringAsFixed(2)} '
              '(equivale a $moneda ${(p * 60 / duracionMin).toStringAsFixed(2)} la hora).'
          : 'Un turno de $durTxt cuesta $moneda ${turno.toStringAsFixed(2)}.';
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text('¿Cómo cobras?',
            style: TextStyle(fontWeight: FontWeight.w700)),
        const SizedBox(height: 8),
        Wrap(spacing: 8, children: [
          ChoiceChip(
            label: const Text('Por hora'),
            selected: !porTurno,
            onSelected: (_) => onPorTurno(false),
          ),
          ChoiceChip(
            label: const Text('Por turno'),
            selected: porTurno,
            onSelected: (_) => onPorTurno(true),
          ),
        ]),
        const SizedBox(height: 10),
        TextField(
          controller: controller,
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          onChanged: (_) => onCambio?.call(),
          decoration: InputDecoration(
            labelText: porTurno ? 'Precio por turno' : 'Precio por hora',
            prefixText: '$moneda ',
          ),
        ),
        if (prev != null) ...[
          const SizedBox(height: 6),
          Text(prev,
              style: TextStyle(color: textoTenueDe(context), fontSize: 12.5)),
        ],
      ],
    );
  }
}
