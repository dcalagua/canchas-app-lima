import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart';
import 'package:image_picker/image_picker.dart';

import '../data/canchas_repo.dart';
import '../models/academia.dart';
import '../models/club.dart';
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

  // Id fijo (para crear/editar y para la ruta del logo).
  late final String _id =
      widget.academia?.id ?? 'ac_${DateTime.now().microsecondsSinceEpoch}';
  String? _logoUrl = widget.academia?.logoUrl;
  Uint8List? _logoNueva; // logo recién elegido (aún sin subir)
  bool _guardando = false;

  // Redes sociales que puede poner el profe.
  static const _redesCatalogo = <(String, String, IconData)>[
    ('instagram', 'Instagram', FontAwesomeIcons.instagram),
    ('facebook', 'Facebook', FontAwesomeIcons.facebook),
    ('tiktok', 'TikTok', FontAwesomeIcons.tiktok),
    ('youtube', 'YouTube', FontAwesomeIcons.youtube),
    ('web', 'Web', FontAwesomeIcons.globe),
  ];
  late final Map<String, TextEditingController> _redesCtrl = {
    for (final r in _redesCatalogo)
      r.$1: TextEditingController(text: widget.academia?.redes[r.$1] ?? '')
  };
  late final Set<String> _redesSel = {
    ...(widget.academia?.redes.keys ?? const <String>[])
  };

  // Sedes conocidas (locales de la lista) para el autocompletable. Al elegir
  // una, se guarda también su ubicación; si escribe una nueva, queda sin ubic.
  late final Map<String, LatLng> _sedes = _cargarSedes();
  late LatLng? _sedeUbic = widget.academia?.sedeUbicacion;

  Map<String, LatLng> _cargarSedes() {
    final m = <String, LatLng>{};
    for (final c in Club.agrupar(appState.todasLasCanchas())) {
      if (c.nombre.trim().isNotEmpty) m.putIfAbsent(c.nombre, () => c.ubicacion);
    }
    return m;
  }

  @override
  void dispose() {
    _nombre.dispose();
    _whatsapp.dispose();
    _sede.dispose();
    _desc.dispose();
    for (final c in _redesCtrl.values) {
      c.dispose();
    }
    super.dispose();
  }

  Future<void> _elegirLogo() async {
    final f = await ImagePicker()
        .pickImage(source: ImageSource.gallery, maxWidth: 512);
    if (f == null) return;
    final bytes = await f.readAsBytes();
    if (!mounted) return;
    setState(() => _logoNueva = bytes);
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

  Future<void> _guardar() async {
    final nombre = _nombre.text.trim();
    if (nombre.isEmpty) {
      _avisar('Ponle un nombre a tu academia.');
      return;
    }
    if (_whatsapp.text.replaceAll(RegExp(r'[^0-9]'), '').length < 9) {
      _avisar('Pon un WhatsApp de contacto válido.');
      return;
    }
    setState(() => _guardando = true);

    // Sube el logo nuevo (si eligió uno) y toma su URL pública.
    if (_logoNueva != null) {
      final url = await CanchasRepo.subirFoto('academia_$_id', _logoNueva!,
          sufijo: 'logo');
      if (url != null) {
        _logoUrl = url;
      } else {
        _avisar(
            'No se pudo subir el logo (${CanchasRepo.ultimoErrorFoto ?? 'sin red'}). Guardo el resto.');
      }
    }

    // Recolecta las redes seleccionadas con dato escrito.
    final redes = <String, String>{};
    for (final clave in _redesSel) {
      final v = _redesCtrl[clave]?.text.trim() ?? '';
      if (v.isNotEmpty) redes[clave] = v;
    }

    final dueno = appState.usuario?.email ?? '';
    final base = widget.academia;
    final academia = (base ??
            Academia(
              id: _id,
              nombre: nombre,
              deporte: _deporte,
              dueno: dueno,
            ))
        .copyWith(
      nombre: nombre,
      deporte: _deporte,
      whatsapp: _whatsapp.text.trim(),
      sedeClub: _sede.text.trim(),
      sedeUbicacion: _sedes[_sede.text.trim()] ?? _sedeUbic,
      descripcion: _desc.text.trim(),
      planes: _planes,
      logoUrl: _logoUrl,
      redes: redes,
    );
    appState.guardarAcademia(academia);
    if (!mounted) return;
    setState(() => _guardando = false);
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
          // Logo (opcional): avatar circular con lo que ya tenga o lo recién elegido.
          Center(child: _LogoPicker(
            bytes: _logoNueva,
            url: _logoUrl,
            deporte: _deporte,
            onTap: _elegirLogo,
          )),
          const SizedBox(height: 20),
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
            controller: _nombre,
            decoration: const InputDecoration(
                labelText: 'Nombre de la academia',
                hintText: 'Ej.: Academia de Tenis Baseline'),
          ),
          const SizedBox(height: 16),
          Autocomplete<String>(
            initialValue: TextEditingValue(text: _sede.text),
            optionsBuilder: (v) {
              final q = v.text.trim().toLowerCase();
              if (q.isEmpty) return const Iterable<String>.empty();
              return _sedes.keys
                  .where((n) => n.toLowerCase().contains(q))
                  .take(6);
            },
            onSelected: (sel) {
              _sede.text = sel;
              _sedeUbic = _sedes[sel]; // captura la ubicación del local elegido
            },
            fieldViewBuilder: (context, controller, focus, onSubmit) {
              return TextField(
                controller: controller,
                focusNode: focus,
                onChanged: (v) {
                  _sede.text = v;
                  _sedeUbic = _sedes[v]; // null si es un nombre nuevo (no de lista)
                },
                decoration: const InputDecoration(
                  labelText: '¿Dónde entrenas ahora? (sede actual)',
                  hintText: 'Escribe y elige de la lista, o pon una nueva',
                  prefixIcon: Icon(Icons.place_outlined),
                ),
              );
            },
            optionsViewBuilder: (context, onSelected, options) => Align(
              alignment: Alignment.topLeft,
              child: Material(
                elevation: 4,
                borderRadius: BorderRadius.circular(12),
                child: ConstrainedBox(
                  constraints: const BoxConstraints(maxHeight: 240, maxWidth: 360),
                  child: ListView(
                    padding: EdgeInsets.zero,
                    shrinkWrap: true,
                    children: [
                      for (final o in options)
                        ListTile(
                          dense: true,
                          leading: const Icon(Icons.place,
                              size: 18, color: verdeCancha),
                          title: Text(o),
                          onTap: () => onSelected(o),
                        ),
                    ],
                  ),
                ),
              ),
            ),
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
          const Text('Redes sociales (opcional)',
              style: TextStyle(fontWeight: FontWeight.w700, fontSize: 16)),
          const SizedBox(height: 4),
          const Text('Elige las que usas y pon tu usuario o enlace.',
              style: TextStyle(color: textoTenue, fontSize: 13)),
          const SizedBox(height: 10),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              for (final r in _redesCatalogo)
                FilterChip(
                  avatar: Icon(r.$3,
                      size: 16,
                      color: _redesSel.contains(r.$1) ? Colors.white : bosque),
                  label: Text(r.$2),
                  selected: _redesSel.contains(r.$1),
                  selectedColor: bosque,
                  labelStyle: TextStyle(
                      color: _redesSel.contains(r.$1) ? Colors.white : tinta,
                      fontWeight: FontWeight.w600),
                  onSelected: (s) => setState(() {
                    if (s) {
                      _redesSel.add(r.$1);
                    } else {
                      _redesSel.remove(r.$1);
                    }
                  }),
                ),
            ],
          ),
          for (final r in _redesCatalogo)
            if (_redesSel.contains(r.$1)) ...[
              const SizedBox(height: 10),
              TextField(
                controller: _redesCtrl[r.$1],
                decoration: InputDecoration(
                  labelText: r.$2,
                  prefixIcon: Padding(
                    padding: const EdgeInsets.all(12),
                    child: FaIcon(r.$3, size: 18, color: bosque),
                  ),
                  hintText: r.$1 == 'web'
                      ? 'https://tuacademia.com'
                      : '@tuusuario o enlace',
                ),
              ),
            ],
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
              onPressed: _guardando ? null : _guardar,
              child: _guardando
                  ? const SizedBox(
                      height: 20,
                      width: 20,
                      child: CircularProgressIndicator(
                          strokeWidth: 2.4, color: lima),
                    )
                  : const Text('Guardar academia'),
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

/// Avatar circular para elegir/mostrar el logo de la academia. Prioriza el logo
/// recién elegido ([bytes]); si no, el ya guardado ([url]); si no, un ícono del
/// deporte como marcador de posición.
class _LogoPicker extends StatelessWidget {
  const _LogoPicker({
    required this.bytes,
    required this.url,
    required this.deporte,
    required this.onTap,
  });

  final Uint8List? bytes;
  final String? url;
  final Deporte deporte;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    ImageProvider? img;
    if (bytes != null) {
      img = MemoryImage(bytes!);
    } else if (url != null && url!.isNotEmpty) {
      img = NetworkImage(url!);
    }
    return Column(
      children: [
        GestureDetector(
          onTap: onTap,
          child: Stack(
            alignment: Alignment.bottomRight,
            children: [
              CircleAvatar(
                radius: 46,
                backgroundColor: limaSuave,
                backgroundImage: img,
                child: img == null
                    ? Icon(iconoDeporte(deporte),
                        size: 34, color: colorDeporte(deporte))
                    : null,
              ),
              Container(
                padding: const EdgeInsets.all(6),
                decoration: const BoxDecoration(
                    color: pino, shape: BoxShape.circle),
                child: const Icon(Icons.photo_camera,
                    size: 16, color: Colors.white),
              ),
            ],
          ),
        ),
        const SizedBox(height: 8),
        Text(img == null ? 'Agregar logo' : 'Cambiar logo',
            style: const TextStyle(
                color: textoTenue, fontSize: 13, fontWeight: FontWeight.w600)),
      ],
    );
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
