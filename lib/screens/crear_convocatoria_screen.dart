import 'package:flutter/material.dart';

import '../models/convocatoria.dart';
import '../services/convocatorias_service.dart';
import '../state/app_state.dart';
import '../theme.dart';

/// Formulario del dueño para crear una convocatoria ("pichanga"). Aquí elige el
/// **modo de asignación** entre las 3 opciones configurables.
class CrearConvocatoriaScreen extends StatefulWidget {
  final String clubId;
  final String clubNombre;
  const CrearConvocatoriaScreen({
    super.key,
    required this.clubId,
    required this.clubNombre,
  });

  @override
  State<CrearConvocatoriaScreen> createState() =>
      _CrearConvocatoriaScreenState();
}

class _CrearConvocatoriaScreenState extends State<CrearConvocatoriaScreen> {
  final _formKey = GlobalKey<FormState>();
  final _titulo = TextEditingController(text: 'Fulbito');
  final _cupos = TextEditingController(text: '14');
  String _categoria = 'master';
  ModoAsignacion _modo = ModoAsignacion.ordenLlegada;
  DateTime? _fecha;
  bool _guardando = false;

  static const _categorias = ['master', 'menor', 'libre'];

  @override
  void dispose() {
    _titulo.dispose();
    _cupos.dispose();
    super.dispose();
  }

  Future<void> _elegirFecha() async {
    final ahora = DateTime.now();
    final f = await showDatePicker(
      context: context,
      initialDate: _fecha ?? ahora,
      firstDate: ahora.subtract(const Duration(days: 1)),
      lastDate: ahora.add(const Duration(days: 120)),
      locale: const Locale('es'),
    );
    if (f != null) setState(() => _fecha = f);
  }

  String? _fechaTexto() {
    final f = _fecha;
    if (f == null) return null;
    const dias = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom'];
    const meses = [
      'ene', 'feb', 'mar', 'abr', 'may', 'jun',
      'jul', 'ago', 'sep', 'oct', 'nov', 'dic'
    ];
    return '${dias[f.weekday - 1]} ${f.day} ${meses[f.month - 1]}';
  }

  Future<void> _guardar() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() => _guardando = true);
    final d = await ConvocatoriasService.crear(
      clubId: widget.clubId,
      titulo: _titulo.text.trim(),
      cupos: int.tryParse(_cupos.text.trim()) ?? 14,
      categoria: _categoria,
      fechaPartido: _fechaTexto(),
      modo: _modo,
      creadoPor: appState.usuario?.email ?? widget.clubNombre,
    );
    if (!mounted) return;
    setState(() => _guardando = false);
    if (d == null) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
        content: Text('No se pudo crear la convocatoria. Revisa tu conexión.'),
        backgroundColor: estadoBadFg,
      ));
      return;
    }
    Navigator.of(context).pop(true);
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(title: const Text('Nueva pichanga')),
      body: Form(
        key: _formKey,
        child: ListView(
          padding: const EdgeInsets.fromLTRB(16, 16, 16, 40),
          children: [
            Text(widget.clubNombre,
                style: TextStyle(color: textoTenue, fontWeight: FontWeight.w600)),
            const SizedBox(height: 16),
            TextFormField(
              controller: _titulo,
              textCapitalization: TextCapitalization.sentences,
              decoration: const InputDecoration(
                labelText: 'Título',
                hintText: 'Ej. Fulbito Máster',
                prefixIcon: Icon(Icons.sports_soccer),
              ),
              validator: (v) =>
                  (v == null || v.trim().isEmpty) ? 'Ponle un título' : null,
            ),
            const SizedBox(height: 14),
            Row(
              children: [
                Expanded(
                  child: DropdownButtonFormField<String>(
                    value: _categoria,
                    decoration: const InputDecoration(labelText: 'Categoría'),
                    items: [
                      for (final c in _categorias)
                        DropdownMenuItem(
                            value: c,
                            child: Text(c[0].toUpperCase() + c.substring(1))),
                    ],
                    onChanged: (v) => setState(() => _categoria = v ?? 'master'),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: TextFormField(
                    controller: _cupos,
                    keyboardType: TextInputType.number,
                    decoration: const InputDecoration(
                      labelText: 'Cupos',
                      prefixIcon: Icon(Icons.groups),
                    ),
                    validator: (v) {
                      final n = int.tryParse(v?.trim() ?? '');
                      if (n == null || n < 1) return 'N.º de cupos';
                      return null;
                    },
                  ),
                ),
              ],
            ),
            const SizedBox(height: 14),
            InkWell(
              onTap: _elegirFecha,
              borderRadius: BorderRadius.circular(10),
              child: InputDecorator(
                decoration: const InputDecoration(
                  labelText: 'Fecha del partido (opcional)',
                  prefixIcon: Icon(Icons.event),
                ),
                child: Text(_fechaTexto() ?? 'Elegir fecha',
                    style: TextStyle(
                        color: _fecha == null ? textoTenue : cs.onSurface)),
              ),
            ),
            const SizedBox(height: 24),
            const Text('¿Cómo se reparten los cupos?',
                style: TextStyle(fontWeight: FontWeight.w800, fontSize: 16)),
            const SizedBox(height: 4),
            Text(
              'Elige el modo para esta pichanga. Puedes usar uno distinto en cada una.',
              style: TextStyle(color: textoTenue, fontSize: 13),
            ),
            const SizedBox(height: 12),
            for (final m in ModoAsignacion.values)
              _ModoOption(
                modo: m,
                seleccionado: _modo == m,
                onTap: () => setState(() => _modo = m),
              ),
            const SizedBox(height: 28),
            FilledButton.icon(
              onPressed: _guardando ? null : _guardar,
              icon: _guardando
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child:
                          CircularProgressIndicator(strokeWidth: 2, color: lima))
                  : const Icon(Icons.check),
              label: const Text('Crear convocatoria'),
            ),
          ],
        ),
      ),
    );
  }
}

class _ModoOption extends StatelessWidget {
  final ModoAsignacion modo;
  final bool seleccionado;
  final VoidCallback onTap;
  const _ModoOption({
    required this.modo,
    required this.seleccionado,
    required this.onTap,
  });

  IconData get _icono => switch (modo) {
        ModoAsignacion.ordenLlegada => Icons.timer_outlined,
        ModoAsignacion.sorteo => Icons.casino_outlined,
        ModoAsignacion.equidad => Icons.balance_outlined,
      };

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: InkWell(
        borderRadius: BorderRadius.circular(12),
        onTap: onTap,
        child: Container(
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            color: seleccionado ? limaSuave : Theme.of(context).colorScheme.surface,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(
              color: seleccionado ? sage : trazo,
              width: seleccionado ? 1.6 : 1,
            ),
          ),
          child: Row(
            children: [
              Icon(_icono, color: seleccionado ? bosque : textoTenue),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(modo.etiqueta,
                        style: const TextStyle(
                            fontWeight: FontWeight.w800, fontSize: 15)),
                    const SizedBox(height: 2),
                    Text(modo.descripcion,
                        style: TextStyle(color: textoTenue, fontSize: 13)),
                  ],
                ),
              ),
              Icon(
                seleccionado
                    ? Icons.radio_button_checked
                    : Icons.radio_button_off,
                color: seleccionado ? bosque : trazo,
              ),
            ],
          ),
        ),
      ),
    );
  }
}
