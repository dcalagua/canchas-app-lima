import 'package:flutter/material.dart';

import '../models/bono.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/ancho_lectura.dart';
import '../widgets/dialogo_pichangol.dart';

/// Bonos de horas prepagadas de UN local (vista del dueño): crea/edita/retira
/// los packs que vende ("10 horas por S/360"). El jugador los compra en la ficha
/// pública. Caja adelantada + fidelización; la contabilidad de la compra reusa
/// la venta (por recibir + comisión).
class BonosDuenoScreen extends StatefulWidget {
  const BonosDuenoScreen(
      {super.key, required this.club, required this.moneda});
  final String club;
  final String moneda;

  @override
  State<BonosDuenoScreen> createState() => _BonosDuenoScreenState();
}

class _BonosDuenoScreenState extends State<BonosDuenoScreen> {
  List<BonoOferta> _bonos = [];
  bool _cargando = true;

  @override
  void initState() {
    super.initState();
    _cargar();
  }

  Future<void> _cargar() async {
    final todos = await appState.cargarBonosDueno();
    if (!mounted) return;
    setState(() {
      _bonos = todos.where((b) => b.club == widget.club).toList();
      _cargando = false;
    });
  }

  Future<void> _editar([BonoOferta? existente]) async {
    final creado = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Theme.of(context).colorScheme.surface,
      shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(22))),
      builder: (_) => _FormBono(
          club: widget.club, moneda: widget.moneda, existente: existente),
    );
    if (creado == true) _cargar();
  }

  Future<void> _eliminar(BonoOferta b) async {
    final ok = await confirmarPichangol(context,
        titulo: 'Retirar bono',
        mensaje: '¿Quitar "${b.nombre}" de tu local? Los jugadores que ya lo '
            'compraron conservan sus horas.',
        textoConfirmar: 'Retirar',
        destructivo: true,
        icono: Icons.delete_outline);
    if (ok != true) return;
    await appState.eliminarBonoOferta(b);
    _cargar();
  }

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return Scaffold(
      appBar: AppBar(title: Text('Bonos · ${widget.club}')),
      floatingActionButton: FloatingActionButton.extended(
        backgroundColor: lima,
        foregroundColor: Colors.white,
        icon: const Icon(Icons.add),
        label: const Text('Nuevo bono'),
        onPressed: () => _editar(),
      ),
      body: AnchoLectura(
        child: _cargando
            ? const Center(child: CircularProgressIndicator())
            : ListView(
                padding: const EdgeInsets.fromLTRB(18, 16, 18, 90),
                children: [
                  Text(
                      'Vende packs de horas con descuento. El jugador paga por '
                      'adelantado y descuenta 1 hora al reservar en tu local.',
                      style:
                          t.bodySmall?.copyWith(color: textoTenueDe(context))),
                  const SizedBox(height: 16),
                  if (_bonos.isEmpty)
                    _Vacio(onCrear: () => _editar())
                  else
                    for (final b in _bonos)
                      Padding(
                        padding: const EdgeInsets.only(bottom: 12),
                        child: _BonoCard(
                          bono: b,
                          moneda: widget.moneda,
                          onEditar: () => _editar(b),
                          onEliminar: () => _eliminar(b),
                        ),
                      ),
                ],
              ),
      ),
    );
  }
}

class _BonoCard extends StatelessWidget {
  const _BonoCard(
      {required this.bono,
      required this.moneda,
      required this.onEditar,
      required this.onEliminar});
  final BonoOferta bono;
  final String moneda;
  final VoidCallback onEditar;
  final VoidCallback onEliminar;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: trazo),
      ),
      child: Row(
        children: [
          Container(
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(
                color: lima.withOpacity(0.14),
                borderRadius: BorderRadius.circular(12)),
            child: Text('${bono.horas}h',
                style: const TextStyle(
                    color: lima, fontWeight: FontWeight.w800, fontSize: 16)),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(bono.nombre.isEmpty ? '${bono.horas} horas' : bono.nombre,
                    style: t.titleMedium?.copyWith(fontWeight: FontWeight.w700)),
                Text(
                    '$moneda ${bono.precio.toStringAsFixed(2)} · '
                    '$moneda ${bono.precioHora.toStringAsFixed(2)}/hora',
                    style: t.bodySmall?.copyWith(color: textoTenueDe(context))),
              ],
            ),
          ),
          IconButton(
              onPressed: onEditar,
              icon: const Icon(Icons.edit_outlined),
              color: Theme.of(context).colorScheme.primary),
          IconButton(
              onPressed: onEliminar,
              icon: const Icon(Icons.delete_outline),
              color: clayOscuro),
        ],
      ),
    );
  }
}

/// Formulario para crear/editar un bono.
class _FormBono extends StatefulWidget {
  const _FormBono(
      {required this.club, required this.moneda, this.existente});
  final String club;
  final String moneda;
  final BonoOferta? existente;

  @override
  State<_FormBono> createState() => _FormBonoState();
}

class _FormBonoState extends State<_FormBono> {
  late final TextEditingController _nombre =
      TextEditingController(text: widget.existente?.nombre ?? '');
  late final TextEditingController _horas = TextEditingController(
      text: widget.existente?.horas.toString() ?? '');
  late final TextEditingController _precio = TextEditingController(
      text: widget.existente?.precio.toStringAsFixed(2) ?? '');
  bool _guardando = false;

  @override
  void dispose() {
    _nombre.dispose();
    _horas.dispose();
    _precio.dispose();
    super.dispose();
  }

  Future<void> _guardar() async {
    final horas = int.tryParse(_horas.text.trim()) ?? 0;
    final precio = double.tryParse(_precio.text.trim().replaceAll(',', '.')) ?? 0;
    if (horas <= 0 || precio <= 0) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text('Pon una cantidad de horas y un precio válidos.')));
      return;
    }
    setState(() => _guardando = true);
    final email = appState.usuario?.email ?? '';
    final base = widget.existente;
    final oferta = base != null
        ? base.copyWith(
            nombre: _nombre.text.trim(), horas: horas, precio: precio)
        : BonoOferta(
            id: 'bof_${DateTime.now().millisecondsSinceEpoch}',
            dueno: email,
            club: widget.club,
            nombre: _nombre.text.trim(),
            horas: horas,
            precio: precio,
            creado: DateTime.now(),
          );
    final ok = await appState.guardarBonoOferta(oferta);
    if (!mounted) return;
    setState(() => _guardando = false);
    if (ok) {
      Navigator.of(context).pop(true);
    } else {
      ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('No se pudo guardar. Reintenta.')));
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final bottom = MediaQuery.of(context).viewInsets.bottom;
    return Padding(
      padding: EdgeInsets.fromLTRB(20, 16, 20, 20 + bottom),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(widget.existente == null ? 'Nuevo bono' : 'Editar bono',
              style: t.titleLarge?.copyWith(fontWeight: FontWeight.w800)),
          const SizedBox(height: 12),
          TextField(
            controller: _nombre,
            textCapitalization: TextCapitalization.sentences,
            decoration: _dec(context, 'Nombre (ej. "Pack mensual")'),
          ),
          const SizedBox(height: 10),
          Row(
            children: [
              Expanded(
                child: TextField(
                  controller: _horas,
                  keyboardType: TextInputType.number,
                  decoration: _dec(context, 'Horas'),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: TextField(
                  controller: _precio,
                  keyboardType:
                      const TextInputType.numberWithOptions(decimal: true),
                  decoration: _dec(context, 'Precio (${widget.moneda})'),
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          SizedBox(
            width: double.infinity,
            child: FilledButton(
              style: FilledButton.styleFrom(backgroundColor: lima),
              onPressed: _guardando ? null : _guardar,
              child: Text(_guardando ? 'Guardando…' : 'Guardar bono'),
            ),
          ),
        ],
      ),
    );
  }

  InputDecoration _dec(BuildContext context, String hint) => InputDecoration(
        hintText: hint,
        filled: true,
        fillColor: Theme.of(context).colorScheme.surface,
        border: OutlineInputBorder(
            borderRadius: BorderRadius.circular(14),
            borderSide: const BorderSide(color: Color(0xFFE4E4E4))),
        enabledBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(14),
            borderSide: const BorderSide(color: Color(0xFFE4E4E4))),
      );
}

class _Vacio extends StatelessWidget {
  const _Vacio({required this.onCrear});
  final VoidCallback onCrear;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 40),
      child: Column(
        children: [
          Icon(Icons.confirmation_number_outlined,
              size: 56, color: textoTenueDe(context)),
          const SizedBox(height: 12),
          Text('Aún no tienes bonos',
              style: t.titleMedium?.copyWith(fontWeight: FontWeight.w800)),
          const SizedBox(height: 6),
          Text(
              'Crea packs de horas con descuento para fidelizar y cobrar por '
              'adelantado.',
              textAlign: TextAlign.center,
              style: t.bodySmall?.copyWith(color: textoTenueDe(context))),
        ],
      ),
    );
  }
}
