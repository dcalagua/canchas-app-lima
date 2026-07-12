import 'package:flutter/material.dart';

import '../models/campeonato.dart';
import '../models/models.dart';
import '../state/app_state.dart';
import '../theme.dart';

/// Formulario para que el profe cree un campeonato de su academia.
class CrearCampeonatoScreen extends StatefulWidget {
  const CrearCampeonatoScreen(
      {super.key, required this.academiaId, this.deporteSugerido});
  final String academiaId;
  final Deporte? deporteSugerido;

  @override
  State<CrearCampeonatoScreen> createState() => _CrearCampeonatoScreenState();
}

class _CrearCampeonatoScreenState extends State<CrearCampeonatoScreen> {
  final _nombre = TextEditingController();
  final _categoria = TextEditingController();
  final _sede = TextEditingController();
  final _fechas = TextEditingController();
  final _costo = TextEditingController();
  late Deporte _deporte = widget.deporteSugerido ?? Deporte.futbol;
  FormatoTorneo _formato = FormatoTorneo.eliminacion;

  @override
  void initState() {
    super.initState();
    // Tenis/pádel/pickleball suelen ir por llave; fútbol por liga.
    _formato = _deporte == Deporte.futbol
        ? FormatoTorneo.liga
        : FormatoTorneo.eliminacion;
  }

  void _guardar() {
    if (_nombre.text.trim().isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text('Ponle un nombre al campeonato.')));
      return;
    }
    final c = appState.crearCampeonato(
      academiaId: widget.academiaId,
      nombre: _nombre.text.trim(),
      deporte: _deporte,
      formato: _formato,
      categoria: _categoria.text.trim(),
      sede: _sede.text.trim(),
      fechas: _fechas.text.trim(),
      costoInscripcion:
          double.tryParse(_costo.text.trim().replaceAll(',', '.')) ?? 0,
    );
    Navigator.of(context).pop(c);
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(title: const Text('Nuevo campeonato')),
      body: ListView(
        padding: const EdgeInsets.all(18),
        children: [
          TextField(
            controller: _nombre,
            textCapitalization: TextCapitalization.words,
            decoration: const InputDecoration(
                labelText: 'Nombre del campeonato',
                hintText: 'Copa Verano CEANDE'),
          ),
          const SizedBox(height: 16),
          Text('Deporte',
              style: TextStyle(
                  fontWeight: FontWeight.w700, color: cs.onSurface)),
          const SizedBox(height: 8),
          Wrap(
            spacing: 8,
            children: [
              for (final d in Deporte.values)
                ChoiceChip(
                  label: Text(d.etiqueta),
                  avatar: Icon(iconoDeporte(d),
                      size: 18,
                      color: _deporte == d ? cs.onPrimary : colorDeporte(d)),
                  selected: _deporte == d,
                  onSelected: (_) => setState(() {
                    _deporte = d;
                    _formato = d == Deporte.futbol
                        ? FormatoTorneo.liga
                        : FormatoTorneo.eliminacion;
                  }),
                ),
            ],
          ),
          const SizedBox(height: 16),
          Text('Formato',
              style: TextStyle(
                  fontWeight: FontWeight.w700, color: cs.onSurface)),
          const SizedBox(height: 8),
          for (final f in FormatoTorneo.values)
            RadioListTile<FormatoTorneo>(
              contentPadding: EdgeInsets.zero,
              value: f,
              groupValue: _formato,
              onChanged: (v) => setState(() => _formato = v!),
              title: Text(f.etiqueta),
              subtitle: Text(f == FormatoTorneo.eliminacion
                  ? 'Llave: el ganador avanza (ideal tenis/pádel).'
                  : 'Todos contra todos + tabla (ideal fútbol).'),
            ),
          const SizedBox(height: 8),
          TextField(
            controller: _categoria,
            textCapitalization: TextCapitalization.words,
            decoration: const InputDecoration(
                labelText: 'Categoría (opcional)',
                hintText: 'Sub-10, Libre, Damas B…'),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _sede,
            textCapitalization: TextCapitalization.words,
            decoration: const InputDecoration(
                labelText: 'Sede (opcional)', hintText: 'Club CEANDE'),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _fechas,
            decoration: const InputDecoration(
                labelText: 'Fechas (opcional)',
                hintText: 'Sáb 12 y Dom 13 de julio'),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _costo,
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            decoration: const InputDecoration(
                labelText: 'Costo de inscripción (opcional)',
                prefixText: 'S/ '),
          ),
          const SizedBox(height: 24),
          SizedBox(
            width: double.infinity,
            child: FilledButton.icon(
              onPressed: _guardar,
              icon: const Icon(Icons.emoji_events),
              label: const Text('Crear campeonato'),
            ),
          ),
        ],
      ),
    );
  }
}
