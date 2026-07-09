import 'package:flutter/material.dart';

import '../models/academia.dart';
import '../models/models.dart';
import '../state/app_state.dart';
import '../theme.dart';

/// Crea o edita la academia del profe (marca independiente). Fase 1: nombre,
/// deporte, sede actual (texto), WhatsApp, descripción y planes.
class CrearAcademiaScreen extends StatefulWidget {
  const CrearAcademiaScreen({super.key, this.academia});

  /// Si viene, se edita; si no, se crea nueva.
  final Academia? academia;

  @override
  State<CrearAcademiaScreen> createState() => _CrearAcademiaScreenState();
}

class _CrearAcademiaScreenState extends State<CrearAcademiaScreen> {
  late final TextEditingController _nombre =
      TextEditingController(text: widget.academia?.nombre ?? '');
  late final TextEditingController _whatsapp =
      TextEditingController(text: widget.academia?.whatsapp ?? '');
  late final TextEditingController _sede =
      TextEditingController(text: widget.academia?.sedeClub ?? '');
  late final TextEditingController _desc =
      TextEditingController(text: widget.academia?.descripcion ?? '');
  late Deporte _deporte = widget.academia?.deporte ?? Deporte.tenis;
  late final List<Plan> _planes = [...(widget.academia?.planes ?? const [])];

  @override
  void dispose() {
    _nombre.dispose();
    _whatsapp.dispose();
    _sede.dispose();
    _desc.dispose();
    super.dispose();
  }

  void _avisar(String m) =>
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(m)));

  Future<void> _agregarPlan() async {
    final plan = await showModalBottomSheet<Plan>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.white,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      builder: (_) => const _EditorPlan(),
    );
    if (plan != null) setState(() => _planes.add(plan));
  }

  void _guardar() {
    final nombre = _nombre.text.trim();
    if (nombre.isEmpty) {
      _avisar('Ponle un nombre a tu academia.');
      return;
    }
    if (_whatsapp.text.replaceAll(RegExp(r'[^0-9]'), '').length < 9) {
      _avisar('Pon un WhatsApp de contacto válido.');
      return;
    }
    final dueno = appState.usuario?.email ?? '';
    final base = widget.academia;
    final academia = (base ?? Academia(
      id: 'ac_${DateTime.now().microsecondsSinceEpoch}',
      nombre: nombre,
      deporte: _deporte,
      dueno: dueno,
    ))
        .copyWith(
      nombre: nombre,
      deporte: _deporte,
      whatsapp: _whatsapp.text.trim(),
      sedeClub: _sede.text.trim(),
      descripcion: _desc.text.trim(),
      planes: _planes,
    );
    appState.guardarAcademia(academia);
    Navigator.of(context).pop();
    _avisar('✅ Academia guardada.');
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: papel,
      appBar: AppBar(
          title: Text(widget.academia == null
              ? 'Crear academia'
              : 'Editar academia')),
      body: ListView(
        padding: const EdgeInsets.all(18),
        children: [
          TextField(
            controller: _nombre,
            decoration: const InputDecoration(
                labelText: 'Nombre de la academia',
                hintText: 'Ej.: Academia de Tenis Baseline'),
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
                  onSelected: (_) => setState(() => _deporte = d),
                ),
            ],
          ),
          const SizedBox(height: 16),
          TextField(
            controller: _sede,
            decoration: const InputDecoration(
                labelText: '¿Dónde entrenas ahora? (sede actual)',
                hintText: 'Ej.: Club CEANDE'),
          ),
          const SizedBox(height: 16),
          TextField(
            controller: _whatsapp,
            keyboardType: TextInputType.phone,
            decoration: const InputDecoration(
                labelText: 'WhatsApp de contacto', prefixText: '+51 '),
          ),
          const SizedBox(height: 16),
          TextField(
            controller: _desc,
            maxLines: 3,
            decoration: const InputDecoration(
                labelText: 'Descripción (opcional)',
                hintText: 'Niveles, horarios, para quién es…'),
          ),
          const SizedBox(height: 22),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              const Text('Planes',
                  style: TextStyle(fontWeight: FontWeight.w700, fontSize: 16)),
              TextButton.icon(
                onPressed: _agregarPlan,
                icon: const Icon(Icons.add),
                label: const Text('Agregar plan'),
              ),
            ],
          ),
          if (_planes.isEmpty)
            const Text('Aún no agregas planes (mensualidad, paquetes, por clase).',
                style: TextStyle(color: textoTenue, fontSize: 13)),
          for (var i = 0; i < _planes.length; i++)
            Card(
              margin: const EdgeInsets.only(bottom: 8),
              child: ListTile(
                title: Text(_planes[i].nombre,
                    style: const TextStyle(fontWeight: FontWeight.w700)),
                subtitle: Text(_descPlan(_planes[i])),
                trailing: IconButton(
                  icon: const Icon(Icons.delete_outline, color: Colors.redAccent),
                  onPressed: () => setState(() => _planes.removeAt(i)),
                ),
              ),
            ),
          const SizedBox(height: 24),
          SizedBox(
            width: double.infinity,
            child: FilledButton(
              style: FilledButton.styleFrom(
                  backgroundColor: pino,
                  foregroundColor: lima,
                  padding: const EdgeInsets.symmetric(vertical: 15)),
              onPressed: _guardar,
              child: const Text('Guardar academia'),
            ),
          ),
        ],
      ),
    );
  }

  String _descPlan(Plan p) {
    if (p.tipo == TipoPlan.porClase) {
      return 'Por clase · S/ ${p.precioMes.toStringAsFixed(2)} c/u';
    }
    return '${p.tipo.etiqueta} · ${p.meses} ${p.meses == 1 ? 'mes' : 'meses'} · '
        'S/ ${p.precioMes.toStringAsFixed(2)}/mes · Total S/ ${p.total.toStringAsFixed(2)}';
  }
}

/// Hoja para crear un plan (nombre, tipo, precio/mes, meses).
class _EditorPlan extends StatefulWidget {
  const _EditorPlan();

  @override
  State<_EditorPlan> createState() => _EditorPlanState();
}

class _EditorPlanState extends State<_EditorPlan> {
  final _nombre = TextEditingController();
  final _precio = TextEditingController();
  TipoPlan _tipo = TipoPlan.mensual;
  int _meses = 1;

  @override
  void dispose() {
    _nombre.dispose();
    _precio.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final porClase = _tipo == TipoPlan.porClase;
    return Padding(
      padding: EdgeInsets.fromLTRB(
          20, 18, 20, 20 + MediaQuery.of(context).viewInsets.bottom),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text('Nuevo plan',
              style: TextStyle(fontWeight: FontWeight.w800, fontSize: 18)),
          const SizedBox(height: 14),
          TextField(
            controller: _nombre,
            decoration: const InputDecoration(
                labelText: 'Nombre', hintText: 'Ej.: Mensualidad 12 clases'),
          ),
          const SizedBox(height: 14),
          Wrap(
            spacing: 8,
            children: [
              for (final t in TipoPlan.values)
                ChoiceChip(
                  label: Text(t.etiqueta),
                  selected: _tipo == t,
                  selectedColor: limaSuave,
                  onSelected: (_) => setState(() {
                    _tipo = t;
                    if (t == TipoPlan.mensual) _meses = 1;
                    if (t == TipoPlan.prepago && _meses < 2) _meses = 3;
                  }),
                ),
            ],
          ),
          const SizedBox(height: 14),
          TextField(
            controller: _precio,
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            decoration: InputDecoration(
                labelText: porClase ? 'Precio por clase' : 'Precio por mes',
                prefixText: 'S/ '),
          ),
          if (!porClase) ...[
            const SizedBox(height: 14),
            Row(
              children: [
                const Text('Meses:', style: TextStyle(fontWeight: FontWeight.w600)),
                const SizedBox(width: 12),
                for (final m in const [1, 3, 6, 12])
                  Padding(
                    padding: const EdgeInsets.only(right: 6),
                    child: ChoiceChip(
                      label: Text('$m'),
                      selected: _meses == m,
                      selectedColor: limaSuave,
                      onSelected: (_) => setState(() => _meses = m),
                    ),
                  ),
              ],
            ),
          ],
          const SizedBox(height: 20),
          SizedBox(
            width: double.infinity,
            child: FilledButton(
              style: FilledButton.styleFrom(
                  backgroundColor: verdeCancha,
                  padding: const EdgeInsets.symmetric(vertical: 14)),
              onPressed: () {
                final nombre = _nombre.text.trim();
                final precio =
                    double.tryParse(_precio.text.trim().replaceAll(',', '.'));
                if (nombre.isEmpty || precio == null || precio <= 0) {
                  ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
                      content: Text('Pon nombre y precio válido.')));
                  return;
                }
                Navigator.of(context).pop(Plan(
                  id: 'pl_${DateTime.now().microsecondsSinceEpoch}',
                  nombre: nombre,
                  tipo: _tipo,
                  precioMes: precio,
                  meses: porClase ? 0 : _meses,
                ));
              },
              child: const Text('Agregar'),
            ),
          ),
        ],
      ),
    );
  }
}
