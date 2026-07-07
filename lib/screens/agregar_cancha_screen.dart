import 'package:flutter/material.dart';

import '../models/models.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/selector_horario.dart';

/// Agrega una cancha individual a un LOCAL ya existente del dueño. Hereda del
/// local su nombre de club, distrito, ubicación, dirección, dueño y estado de
/// verificación (si el local ya está verificado, la cancha nueva entra activa
/// al instante — no se re-valida la propiedad). Solo se pide lo propio de la
/// cancha: nombre, deporte, precio, horario y duración. Permite varias canchas
/// del mismo deporte (id único por cancha).
class AgregarCanchaScreen extends StatefulWidget {
  const AgregarCanchaScreen({super.key, required this.local});

  /// Una cancha existente del local, usada como plantilla para heredar datos.
  final Cancha local;

  @override
  State<AgregarCanchaScreen> createState() => _AgregarCanchaScreenState();
}

class _AgregarCanchaScreenState extends State<AgregarCanchaScreen> {
  final _nombre = TextEditingController();
  late final TextEditingController _precio =
      TextEditingController(text: widget.local.precioHora.toStringAsFixed(2));
  Deporte _deporte = Deporte.futbol;
  String _superficie = ''; // tipo de piso (opcional, según deporte)
  late String _apertura = widget.local.horaApertura;
  late String _cierre = widget.local.horaCierre;
  late int _duracion = widget.local.duracionSlotMin;
  bool _guardando = false;

  @override
  void dispose() {
    _nombre.dispose();
    _precio.dispose();
    super.dispose();
  }

  Future<void> _guardar() async {
    // Nombre opcional: si se deja vacío, se nombra sola por deporte con el
    // siguiente número dentro del local ("Fútbol 2", "Tenis 1"…).
    var nombre = _nombre.text.trim();
    if (nombre.isEmpty) {
      // Cuenta las canchas del MISMO local y deporte para el siguiente número.
      final n = appState.misCanchas
              .where((c) =>
                  c.club == widget.local.club && c.deporte == _deporte)
              .length +
          1;
      nombre = '${_deporte.etiqueta} $n';
    }
    final precio = double.tryParse(_precio.text.trim().replaceAll(',', '.'));
    if (precio == null || precio <= 0) {
      _avisar('Pon un precio por hora válido.');
      return;
    }
    final a = horaEnMinutos(_apertura), c = horaEnMinutos(_cierre);
    if (a == null || c == null || c <= a) {
      _avisar('El cierre debe ser después de la apertura.');
      return;
    }

    setState(() => _guardando = true);
    final l = widget.local;
    final cancha = Cancha(
      id: 'u${DateTime.now().microsecondsSinceEpoch}',
      nombre: nombre,
      club: l.club, // mismo local
      distrito: l.distrito,
      deporte: _deporte,
      precioHora: precio,
      ubicacion: l.ubicacion,
      clubFundador: l.clubFundador,
      digitalizada: true,
      direccion: l.direccion,
      registrada: true,
      fotoUrl: l.fotoUrl,
      fotos: l.fotos,
      dueno: l.dueno,
      verificada: l.verificada, // hereda: si el local ya está activo, esta también
      horaApertura: _apertura,
      horaCierre: _cierre,
      duracionSlotMin: _duracion,
      amenidades: l.amenidades, // los servicios son del local: se heredan
      superficie: _superficie,
    );
    appState.agregarCancha(cancha);
    if (!mounted) return;
    setState(() => _guardando = false);
    Navigator.of(context).pop();
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        backgroundColor: pino,
        content: Text('✅ "$nombre" agregada a ${l.club}.',
            style: const TextStyle(color: Colors.white)),
      ),
    );
  }

  void _avisar(String m) =>
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(m)));

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: papel,
      appBar: AppBar(title: const Text('Agregar cancha')),
      body: ListView(
        padding: const EdgeInsets.all(18),
        children: [
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
                color: limaSuave, borderRadius: BorderRadius.circular(10)),
            child: Text(
              'Se agregará al local "${widget.local.club}" (misma dirección y '
              'ubicación). Puedes tener varias canchas del mismo deporte.',
              style: Theme.of(context)
                  .textTheme
                  .bodySmall
                  ?.copyWith(color: tinta),
            ),
          ),
          const SizedBox(height: 16),
          TextField(
            controller: _nombre,
            decoration: const InputDecoration(
              labelText: 'Nombre de la cancha (opcional)',
            ),
          ),
          const SizedBox(height: 16),
          const Text('Deporte', style: TextStyle(fontWeight: FontWeight.w700)),
          const SizedBox(height: 8),
          Wrap(
            spacing: 10,
            children: [
              for (final d in deportesActivos)
                ChoiceChip(
                  avatar: Icon(iconoDeporte(d),
                      size: 18,
                      color: _deporte == d ? Colors.white : colorDeporte(d)),
                  label: Text(d.etiqueta),
                  selected: _deporte == d,
                  selectedColor: colorDeporte(d),
                  labelStyle: TextStyle(
                      color: _deporte == d ? Colors.white : tinta,
                      fontWeight: FontWeight.w600),
                  onSelected: (_) => setState(() {
                    _deporte = d;
                    _superficie = ''; // cambia el catálogo de pisos
                  }),
                ),
            ],
          ),
          const SizedBox(height: 16),
          const Text('Tipo de piso',
              style: TextStyle(fontWeight: FontWeight.w700)),
          const SizedBox(height: 8),
          Wrap(
            spacing: 10,
            runSpacing: 10,
            children: [
              for (final s in superficiesDe(_deporte))
                ChoiceChip(
                  avatar: Icon(iconoSuperficie(s),
                      size: 18,
                      color: _superficie == s ? bosque : textoTenue),
                  label: Text(s),
                  selected: _superficie == s,
                  labelStyle: TextStyle(
                      color: _superficie == s ? bosque : tinta,
                      fontWeight: FontWeight.w600),
                  selectedColor: limaSuave,
                  onSelected: (sel) =>
                      setState(() => _superficie = sel ? s : ''),
                ),
            ],
          ),
          const SizedBox(height: 16),
          TextField(
            controller: _precio,
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            decoration: const InputDecoration(
              labelText: 'Precio por hora',
              prefixText: 'S/ ',
            ),
          ),
          const SizedBox(height: 18),
          SelectorHorario(
            apertura: _apertura,
            cierre: _cierre,
            duracionMin: _duracion,
            onApertura: (v) => setState(() => _apertura = v),
            onCierre: (v) => setState(() => _cierre = v),
            onDuracion: (v) => setState(() => _duracion = v),
          ),
          const SizedBox(height: 24),
          SizedBox(
            width: double.infinity,
            child: FilledButton.icon(
              style: FilledButton.styleFrom(
                  backgroundColor: pino,
                  foregroundColor: lima,
                  padding: const EdgeInsets.symmetric(vertical: 15)),
              onPressed: _guardando ? null : _guardar,
              icon: _guardando
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(
                          strokeWidth: 2, color: lima))
                  : const Icon(Icons.add),
              label: Text(_guardando ? 'Agregando…' : 'Agregar cancha'),
            ),
          ),
        ],
      ),
    );
  }
}
