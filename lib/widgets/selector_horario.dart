import 'package:flutter/material.dart';

import '../theme.dart';

/// Selector de horario de atención (apertura / cierre) y duración del turno,
/// reutilizable al agregar o editar una cancha. Las horas son en punto.
class SelectorHorario extends StatelessWidget {
  const SelectorHorario({
    super.key,
    required this.apertura,
    required this.cierre,
    required this.duracionMin,
    required this.onApertura,
    required this.onCierre,
    required this.onDuracion,
  });

  final String apertura; // "07:00"
  final String cierre; // "23:00"
  final int duracionMin; // 60 / 90 / 120
  final ValueChanged<String> onApertura;
  final ValueChanged<String> onCierre;
  final ValueChanged<int> onDuracion;

  static List<String> get _horas =>
      [for (var h = 0; h < 24; h++) '${h.toString().padLeft(2, '0')}:00'];

  static String _labelDur(int min) => switch (min) {
        60 => '1 hora',
        90 => '1h 30min',
        120 => '2 horas',
        _ => '$min min',
      };

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text('Horario de atención',
            style: TextStyle(fontWeight: FontWeight.w700)),
        const SizedBox(height: 8),
        Row(
          children: [
            Expanded(child: _dropHora('Abre', apertura, onApertura)),
            const SizedBox(width: 12),
            Expanded(child: _dropHora('Cierra', cierre, onCierre)),
          ],
        ),
        const SizedBox(height: 6),
        Text(
            'Cierre 00:00 = medianoche (12 de la noche). Para 24 h, pon abre y '
            'cierra en 00:00. Cancha de madrugada (ej. 18:00 a 02:00): elige el '
            'cierre del día siguiente.',
            style: TextStyle(fontSize: 11.5, color: tinta.withOpacity(0.6))),
        const SizedBox(height: 16),
        const Text('Duración del turno',
            style: TextStyle(fontWeight: FontWeight.w700)),
        const SizedBox(height: 8),
        Wrap(
          spacing: 10,
          children: [
            for (final d in const [60, 90, 120])
              ChoiceChip(
                label: Text(_labelDur(d)),
                selected: duracionMin == d,
                selectedColor: verdeCancha,
                labelStyle: TextStyle(
                  color: duracionMin == d ? Colors.white : tinta,
                  fontWeight: FontWeight.w600,
                ),
                onSelected: (_) => onDuracion(d),
              ),
          ],
        ),
      ],
    );
  }

  Widget _dropHora(String label, String value, ValueChanged<String> onChanged) {
    return DropdownButtonFormField<String>(
      value: _horas.contains(value) ? value : null,
      isExpanded: true,
      decoration: InputDecoration(
        labelText: label,
      ),
      items: [
        for (final h in _horas) DropdownMenuItem(value: h, child: Text(h)),
      ],
      onChanged: (v) {
        if (v != null) onChanged(v);
      },
    );
  }
}
