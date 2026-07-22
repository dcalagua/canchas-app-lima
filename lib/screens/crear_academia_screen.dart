import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart';
import 'package:image_picker/image_picker.dart';
import 'package:url_launcher/url_launcher.dart';

import '../data/canchas_repo.dart';
import '../models/academia.dart';
import '../models/club.dart';
import '../models/models.dart';
import '../services/whatsapp_link.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/responsive.dart';
import '../config/pais.dart';
import 'servicios_screen.dart';

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
  // Recargo fijo del INVITADO (no socio del club) sobre la tarifa socio. Vacío
  // o 0 = la academia no distingue socio/invitado (un solo precio).
  late final TextEditingController _recargoInvitado = TextEditingController(
      text: (widget.academia?.recargoInvitado ?? 0) > 0
          ? widget.academia!.recargoInvitado.toStringAsFixed(0)
          : '');
  // Descuentos configurables (%). Vacío = 0 = sin descuento.
  late final TextEditingController _dtoHermano2 =
      _ctrlPct(widget.academia?.descuentoHermano2);
  late final TextEditingController _dtoHermano3 =
      _ctrlPct(widget.academia?.descuentoHermano3);
  late final TextEditingController _dtoPrepago =
      _ctrlPct(widget.academia?.descuentoPrepago);
  // Desde cuántos meses adelantados aplica el descuento de prepago (default 3).
  late final TextEditingController _mesesMinPrepago = TextEditingController(
      text: '${widget.academia?.mesesMinPrepago ?? 3}');
  // Retribución al club/sede (%) sobre lo cobrado. Vacío = 0 = no aplica.
  late final TextEditingController _retribClub =
      _ctrlPct(widget.academia?.retribucionClubPct);
  // Landing/publicidad (servicio de marketing). Vacío = no contratada.
  late final TextEditingController _landing =
      TextEditingController(text: widget.academia?.landingUrl ?? '');
  static TextEditingController _ctrlPct(double? v) => TextEditingController(
      text: (v ?? 0) > 0 ? v!.toStringAsFixed(0) : '');
  late Deporte _deporte = widget.academia?.deporte ?? Deporte.tenis;
  late final List<Plan> _planes = [...(widget.academia?.planes ?? const [])];

  // "Plan simple" oculto por ahora (el tarifario se arma con "Programa").
  static const bool _mostrarPlanSimple = false;

  // Id fijo (para crear/editar y para la ruta del logo).
  late final String _id =
      widget.academia?.id ?? 'ac_${DateTime.now().microsecondsSinceEpoch}';
  late String? _logoUrl = widget.academia?.logoUrl;
  Uint8List? _logoNueva; // logo recién elegido (aún sin subir)
  bool _guardando = false;

  // Feed propio: fotos ya guardadas (URLs) + fotos nuevas por subir.
  late final List<String> _fotos = [...(widget.academia?.fotos ?? const [])];
  final List<Uint8List> _fotosNuevas = [];

  // Redes sociales que puede poner el profe.
  static const _redesCatalogo = <(String, String, IconData)>[
    ('instagram', 'Instagram', FontAwesomeIcons.instagram),
    ('facebook', 'Facebook', FontAwesomeIcons.facebook),
    ('tiktok', 'TikTok', FontAwesomeIcons.tiktok),
    ('youtube', 'YouTube', FontAwesomeIcons.youtube),
    ('web', 'Web', FontAwesomeIcons.globe),
  ];
  // Si ya tiene landing y no puso una web propia, la web = su landing (auto).
  late final String _webAuto = (widget.academia?.redes['web']?.trim().isNotEmpty
          ?? false)
      ? widget.academia!.redes['web']!.trim()
      : (widget.academia?.landingUrl ?? '');
  late final Map<String, TextEditingController> _redesCtrl = {
    for (final r in _redesCatalogo)
      r.$1: TextEditingController(
          text: r.$1 == 'web' ? _webAuto : (widget.academia?.redes[r.$1] ?? ''))
  };
  late final Set<String> _redesSel = {
    ...(widget.academia?.redes.keys ?? const <String>[]),
    if (_webAuto.isNotEmpty) 'web',
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

  /// Ubicación de la sede elegida (de la lista) o la que ya traía la academia.
  LatLng? get _ubicSede => _sedes[_sede.text.trim()] ?? _sedeUbic;

  /// País (config) de la academia = el de su SEDE, no el del dispositivo. Define
  /// la moneda de los planes y el prefijo del WhatsApp. Si aún no hay sede
  /// ubicada, cae al país activo. Así una academia en Lima queda en S/ y +51
  /// aunque el profe la edite desde Bolivia.
  PaisConfig get _paisAcademia {
    final u = _ubicSede;
    return u != null ? paisDeCoordenadas(u.latitude, u.longitude) : paisActual;
  }

  @override
  void dispose() {
    _nombre.dispose();
    _whatsapp.dispose();
    _sede.dispose();
    _desc.dispose();
    _recargoInvitado.dispose();
    _dtoHermano2.dispose();
    _dtoHermano3.dispose();
    _dtoPrepago.dispose();
    _mesesMinPrepago.dispose();
    _retribClub.dispose();
    _landing.dispose();
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

  Future<void> _agregarFoto() async {
    // Selección MÚLTIPLE: el usuario puede elegir varias fotos a la vez.
    final fs = await ImagePicker().pickMultiImage(maxWidth: 1280);
    if (fs.isEmpty) return;
    final nuevas = <Uint8List>[];
    for (final f in fs) {
      nuevas.add(await f.readAsBytes());
    }
    if (!mounted) return;
    setState(() => _fotosNuevas.addAll(nuevas));
  }

  void _avisar(String m) =>
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(m)));

  Future<void> _agregarPlan() async {
    final plan = await showModalBottomSheet<Plan>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Theme.of(context).colorScheme.surface,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      builder: (_) => _EditorPlan(moneda: _paisAcademia.moneda),
    );
    if (plan != null) setState(() => _planes.add(plan));
  }

  /// Editor de TARIFARIO por frecuencia: un programa (ej. "Bola Roja y Naranja")
  /// con sus precios socio 2x/3x/4x/5x → crea 4 planes mensuales de una vez.
  Future<void> _agregarPrograma() async {
    final nuevos = await showModalBottomSheet<List<Plan>>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Theme.of(context).colorScheme.surface,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      builder: (_) => _EditorPrograma(moneda: _paisAcademia.moneda),
    );
    if (nuevos != null && nuevos.isNotEmpty) {
      setState(() => _planes.addAll(nuevos));
    }
  }

  /// Edita un PROGRAMA existente: precarga sus planes, y al guardar reemplaza
  /// todos los planes de ese programa (soporta renombrarlo).
  Future<void> _editarPrograma(String programa) async {
    final base = _planes.where((p) => p.programa == programa).toList();
    final nuevos = await showModalBottomSheet<List<Plan>>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Theme.of(context).colorScheme.surface,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      builder: (_) => _EditorPrograma(moneda: _paisAcademia.moneda, base: base),
    );
    if (nuevos != null) {
      setState(() {
        _planes.removeWhere((p) => p.programa == programa);
        _planes.addAll(nuevos);
      });
    }
  }

  /// Abre la landing publicada en el navegador.
  Future<void> _abrirLanding(String url) async {
    final u = Uri.tryParse(url);
    if (u != null) await launchUrl(u, mode: LaunchMode.externalApplication);
  }


  /// Lee un % de un controller: number 0–100 (vacío/invalido = 0).
  double _pct(TextEditingController c) {
    final v = double.tryParse(c.text.trim().replaceAll(',', '.')) ?? 0;
    if (v < 0) return 0;
    return v > 100 ? 100 : v;
  }

  /// Campo de porcentaje reutilizable. La etiqueta va como texto FIJO arriba
  /// (no flotante) para que se lea completa incluso en columnas angostas.
  Widget _campoPct(TextEditingController c, String label) => Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(
                  fontSize: 12.5,
                  fontWeight: FontWeight.w600,
                  color: textoTenue)),
          const SizedBox(height: 4),
          TextField(
            controller: c,
            keyboardType: TextInputType.number,
            decoration: const InputDecoration(
              hintText: '0',
              suffixText: '%',
              isDense: true,
            ),
          ),
        ],
      );

  /// Sección plegable (ExpansionTile) para opciones avanzadas. Colapsada por
  /// defecto; [abierta] la muestra expandida (si la academia ya tiene valores).
  Widget _seccionPlegable({
    required String titulo,
    required String subtitulo,
    required bool abierta,
    required List<Widget> hijos,
  }) {
    return Container(
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: trazo),
      ),
      clipBehavior: Clip.antiAlias,
      child: Theme(
        data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
        child: ExpansionTile(
          initiallyExpanded: abierta,
          tilePadding: const EdgeInsets.symmetric(horizontal: 14),
          childrenPadding: const EdgeInsets.fromLTRB(14, 0, 14, 14),
          expandedCrossAxisAlignment: CrossAxisAlignment.start,
          title: Text(titulo,
              style:
                  const TextStyle(fontWeight: FontWeight.w700, fontSize: 15)),
          subtitle: Text(subtitulo,
              style: const TextStyle(color: textoTenue, fontSize: 12)),
          children: hijos,
        ),
      ),
    );
  }

  /// Lista de planes agrupada: los PROGRAMAS (matriz) como tarjeta editable con
  /// su etapa/edad, duración y precios por frecuencia; los planes simples aparte.
  List<Widget> _listaProgramas() {
    final porPrograma = <String, List<Plan>>{};
    final simples = <Plan>[];
    for (final p in _planes) {
      if (p.programa.isNotEmpty) {
        (porPrograma[p.programa] ??= []).add(p);
      } else {
        simples.add(p);
      }
    }
    final mon = _paisAcademia.moneda;
    final w = <Widget>[];
    porPrograma.forEach((prog, planes) {
      planes.sort((a, b) => a.frecuenciaSemana.compareTo(b.frecuenciaSemana));
      final first = planes.first;
      final sub = [
        if (first.etapaEdad.isNotEmpty) first.etapaEdad,
        if (first.duracionClase.isNotEmpty) 'Duración: ${first.duracionClase}',
      ].join(' · ');
      w.add(Card(
        margin: const EdgeInsets.only(bottom: 8),
        child: Padding(
          padding: const EdgeInsets.fromLTRB(14, 10, 6, 12),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(prog,
                        style: const TextStyle(
                            fontWeight: FontWeight.w800, fontSize: 15)),
                  ),
                  IconButton(
                    tooltip: 'Editar programa',
                    icon: const Icon(Icons.edit_outlined, color: lima),
                    onPressed: () => _editarPrograma(prog),
                  ),
                  IconButton(
                    tooltip: 'Eliminar programa',
                    icon: const Icon(Icons.delete_outline,
                        color: Colors.redAccent),
                    onPressed: () => setState(
                        () => _planes.removeWhere((p) => p.programa == prog)),
                  ),
                ],
              ),
              if (sub.isNotEmpty)
                Padding(
                  padding: const EdgeInsets.only(right: 8, bottom: 8),
                  child: Text(sub,
                      style:
                          const TextStyle(color: textoTenue, fontSize: 12.5)),
                ),
              Wrap(
                spacing: 6,
                runSpacing: 6,
                children: [
                  for (final p in planes)
                    Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 10, vertical: 6),
                      decoration: BoxDecoration(
                        color: limaSuave,
                        borderRadius: BorderRadius.circular(10),
                      ),
                      child: Text(
                          '${p.frecuenciaSemana}x · $mon ${p.precioMes.toStringAsFixed(0)}',
                          style: const TextStyle(
                              fontSize: 12.5, fontWeight: FontWeight.w700)),
                    ),
                ],
              ),
            ],
          ),
        ),
      ));
    });
    for (final p in simples) {
      w.add(Card(
        margin: const EdgeInsets.only(bottom: 8),
        child: ListTile(
          title: Text(p.nombre,
              style: const TextStyle(fontWeight: FontWeight.w700)),
          subtitle: Text(_descPlan(p)),
          trailing: IconButton(
            icon: const Icon(Icons.delete_outline, color: Colors.redAccent),
            onPressed: () => setState(() => _planes.remove(p)),
          ),
        ),
      ));
    }
    return w;
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

    // Sube las fotos nuevas del feed y las agrega a las ya guardadas.
    final fotos = [..._fotos];
    for (var i = 0; i < _fotosNuevas.length; i++) {
      final url = await CanchasRepo.subirFoto('academia_$_id', _fotosNuevas[i],
          sufijo: 'foto_${DateTime.now().microsecondsSinceEpoch}_$i');
      if (url != null) fotos.add(url);
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
              // Congela la moneda por el país de la SEDE (no el del dispositivo).
              moneda: _paisAcademia.moneda,
            ))
        .copyWith(
      nombre: nombre,
      deporte: _deporte,
      whatsapp: _whatsapp.text.trim(),
      sedeClub: _sede.text.trim(),
      sedeUbicacion: _sedes[_sede.text.trim()] ?? _sedeUbic,
      descripcion: _desc.text.trim(),
      planes: _planes,
      recargoInvitado:
          double.tryParse(_recargoInvitado.text.trim().replaceAll(',', '.')) ?? 0,
      descuentoHermano2: _pct(_dtoHermano2),
      descuentoHermano3: _pct(_dtoHermano3),
      descuentoPrepago: _pct(_dtoPrepago),
      mesesMinPrepago: (int.tryParse(_mesesMinPrepago.text.trim()) ?? 3)
          .clamp(1, 36),
      retribucionClubPct: _pct(_retribClub),
      landingUrl: _landing.text.trim(),
      logoUrl: _logoUrl,
      redes: redes,
      fotos: fotos,
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
      appBar: AppBar(
          title: Text(widget.academia == null
              ? 'Crear academia'
              : 'Editar academia')),
      body: ListView(
        padding: EdgeInsets.fromLTRB(
            ladoTablet(context), 18, ladoTablet(context), 18),
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
                      color: _deporte == d
                          ? Colors.white
                          : Theme.of(context).colorScheme.onSurface,
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
                          leading: Icon(Icons.place,
                              size: 18,
                              color: Theme.of(context).colorScheme.primary),
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
            decoration: InputDecoration(
                labelText: 'WhatsApp de contacto',
                // Prefijo del país de la SEDE (+51 Perú, +591 Bolivia…), no el
                // del dispositivo del profe.
                prefixText: '+${_paisAcademia.codigoTel} '),
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
          const Text('Fotos (feed de tu academia)',
              style: TextStyle(fontWeight: FontWeight.w700, fontSize: 16)),
          const SizedBox(height: 4),
          const Text('Se muestran dentro de Pichangol, sin salir a Instagram.',
              style: TextStyle(color: textoTenue, fontSize: 13)),
          const SizedBox(height: 10),
          SizedBox(
            height: 96,
            child: ListView(
              scrollDirection: Axis.horizontal,
              children: [
                // Botón agregar.
                GestureDetector(
                  onTap: _agregarFoto,
                  child: Container(
                    width: 96,
                    margin: const EdgeInsets.only(right: 10),
                    decoration: BoxDecoration(
                      color: limaSuave,
                      borderRadius: BorderRadius.circular(12),
                      border: Border.all(color: trazo),
                    ),
                    child: const Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Icon(Icons.add_a_photo_outlined, color: bosque),
                        SizedBox(height: 4),
                        Text('Agregar',
                            style: TextStyle(color: bosque, fontSize: 12)),
                      ],
                    ),
                  ),
                ),
                // Fotos ya guardadas (URL).
                for (var i = 0; i < _fotos.length; i++)
                  _MiniFoto(
                    imagen: NetworkImage(_fotos[i]),
                    onQuitar: () => setState(() => _fotos.removeAt(i)),
                  ),
                // Fotos nuevas (aún sin subir).
                for (var i = 0; i < _fotosNuevas.length; i++)
                  _MiniFoto(
                    imagen: MemoryImage(_fotosNuevas[i]),
                    onQuitar: () => setState(() => _fotosNuevas.removeAt(i)),
                  ),
              ],
            ),
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
                      color: _redesSel.contains(r.$1)
                          ? Colors.white
                          : Theme.of(context).colorScheme.primary),
                  label: Text(r.$2),
                  selected: _redesSel.contains(r.$1),
                  selectedColor: bosque,
                  labelStyle: TextStyle(
                      color: _redesSel.contains(r.$1)
                          ? Colors.white
                          : Theme.of(context).colorScheme.onSurface,
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
                    child: FaIcon(r.$3,
                        size: 18, color: Theme.of(context).colorScheme.primary),
                  ),
                  hintText: r.$1 == 'web'
                      ? 'https://tuacademia.com'
                      : '@tuusuario o enlace',
                  helperText: r.$1 == 'web' &&
                          (widget.academia?.landingUrl ?? '').isNotEmpty &&
                          _redesCtrl['web']?.text.trim() ==
                              widget.academia?.landingUrl.trim()
                      ? 'Es tu landing de Pichangol (puedes reemplazarla).'
                      : null,
                ),
              ),
            ],
          const SizedBox(height: 14),
          // Atajo al servicio de MANEJO de redes (OAuth para publicar). El enlace
          // OAuth vive en Servicios Pichangol (donde se contrata); aquí solo se
          // descubre. Publicar por el usuario ≠ declarar el @usuario de arriba.
          Container(
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
                color: limaSuave, borderRadius: BorderRadius.circular(14)),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Row(
                  children: [
                    Icon(Icons.campaign_outlined, color: bosque, size: 20),
                    SizedBox(width: 8),
                    Expanded(
                      child: Text('¿Quieres que publiquemos por ti?',
                          style: TextStyle(
                              fontWeight: FontWeight.w800, color: bosque)),
                    ),
                  ],
                ),
                const SizedBox(height: 4),
                const Text(
                    'Conecta tu Instagram/Facebook y deja que Pichangol maneje '
                    'tus redes (contenido con IA + publicación). Se activa en '
                    'Servicios Pichangol.',
                    style: TextStyle(fontSize: 12.5, color: textoTenue)),
                const SizedBox(height: 10),
                if (widget.academia != null)
                  SizedBox(
                    width: double.infinity,
                    child: FilledButton.icon(
                      style: FilledButton.styleFrom(
                          backgroundColor: lima, foregroundColor: Colors.white),
                      icon: const Icon(Icons.arrow_forward, size: 18),
                      label: const Text('Ir a Servicios Pichangol'),
                      onPressed: () => Navigator.of(context).push(
                        MaterialPageRoute(
                          builder: (_) => ServiciosScreen(
                              negocio: appState.negocioServiciosDeAcademia(
                                  widget.academia!)),
                        ),
                      ),
                    ),
                  )
                else
                  const Text(
                      'Guarda la academia y actívalo desde Servicios Pichangol.',
                      style: TextStyle(fontSize: 12, color: textoTenue)),
              ],
            ),
          ),
          const SizedBox(height: 22),
          const Text('Planes y tarifario',
              style: TextStyle(fontWeight: FontWeight.w700, fontSize: 16)),
          const SizedBox(height: 6),
          Wrap(
            spacing: 8,
            children: [
              OutlinedButton.icon(
                onPressed: _agregarPrograma,
                style: OutlinedButton.styleFrom(
                    foregroundColor: lima,
                    side: const BorderSide(color: lima)),
                icon: const Icon(Icons.grid_view, size: 18),
                label: const Text('Programa (tarifa x frecuencia)'),
              ),
              // "Plan simple" oculto por ahora (poner true para reactivarlo).
              if (_mostrarPlanSimple)
                TextButton.icon(
                  onPressed: _agregarPlan,
                  icon: const Icon(Icons.add),
                  label: const Text('Plan simple'),
                ),
            ],
          ),
          const SizedBox(height: 12),
          if (_planes.isEmpty)
            const Text('Aún no agregas planes (mensualidad, paquetes, por clase).',
                style: TextStyle(color: textoTenue, fontSize: 13)),
          ..._listaProgramas(),
          const SizedBox(height: 18),
          // Opciones avanzadas plegadas: una academia "normal" (sin convenio de
          // club) no las necesita. Se abren solas si ya traen valores (Jartur).
          _seccionPlegable(
            titulo: 'Convenio con club (opcional)',
            subtitulo:
                'Solo si operas dentro de un club: tarifa distinta para invitados '
                'y % que le pagas al club.',
            abierta: (widget.academia?.recargoInvitado ?? 0) > 0 ||
                (widget.academia?.retribucionClubPct ?? 0) > 0,
            hijos: [
              TextField(
                controller: _recargoInvitado,
                keyboardType: TextInputType.number,
                decoration: InputDecoration(
                  labelText: 'Recargo invitado (no socio del club)',
                  hintText: 'Ej.: 50',
                  prefixText: '${_paisAcademia.moneda} ',
                  helperText:
                      'Se suma a la tarifa socio para invitados. Vacío = un solo precio.',
                ),
              ),
              const SizedBox(height: 14),
              _campoPct(_retribClub, 'Retribución al club (%)'),
              const SizedBox(height: 4),
              const Text(
                  '% de lo cobrado que le pagas al club. Aparece en el Reporte '
                  'como liquidación al club.',
                  style: TextStyle(color: textoTenue, fontSize: 11.5)),
            ],
          ),
          const SizedBox(height: 10),
          _seccionPlegable(
            titulo: 'Descuentos (opcional)',
            subtitulo:
                'Se aplican al inscribir. Hermano y prepago se suman. Vacío = sin '
                'descuento.',
            abierta: (widget.academia?.descuentoHermano2 ?? 0) > 0 ||
                (widget.academia?.descuentoHermano3 ?? 0) > 0 ||
                (widget.academia?.descuentoPrepago ?? 0) > 0,
            hijos: [
              Row(
                children: [
                  Expanded(child: _campoPct(_dtoHermano2, '2º hermano')),
                  const SizedBox(width: 10),
                  Expanded(child: _campoPct(_dtoHermano3, '3º hermano +')),
                ],
              ),
              const SizedBox(height: 10),
              Row(
                children: [
                  Expanded(
                      child: _campoPct(_dtoPrepago, 'Prepago (% adelantado)')),
                  const SizedBox(width: 10),
                  Expanded(
                    child: TextField(
                      controller: _mesesMinPrepago,
                      keyboardType: TextInputType.number,
                      decoration: const InputDecoration(
                        labelText: 'Desde N meses',
                        isDense: true,
                      ),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 6),
              const Text(
                  'El descuento de prepago aplica cuando el alumno paga N o más '
                  'meses de golpe (tú decides el N).',
                  style: TextStyle(color: textoTenue, fontSize: 11.5)),
            ],
          ),
          const SizedBox(height: 10),
          _seccionPlegable(
            titulo: 'Publicidad / Landing (opcional)',
            subtitulo:
                'Si ya tienes tu página web, pégala aquí. Si no, contrata tu '
                'landing en "Servicios Pichangol": la generamos con los datos de '
                'tu academia.',
            abierta: (widget.academia?.landingUrl ?? '').isNotEmpty,
            hijos: [
              TextField(
                controller: _landing,
                keyboardType: TextInputType.url,
                decoration: const InputDecoration(
                  labelText: 'Enlace de la landing',
                  hintText: 'https://…',
                  prefixIcon: Icon(Icons.public, size: 20),
                  isDense: true,
                ),
              ),
              const SizedBox(height: 12),
              if ((widget.academia?.landingUrl ?? '').isNotEmpty) ...[
                Row(
                  children: [
                    Expanded(
                      child: FilledButton.icon(
                        style: FilledButton.styleFrom(
                            backgroundColor: lima, foregroundColor: Colors.white),
                        icon: const Icon(Icons.open_in_new, size: 18),
                        label: const Text('Ver mi landing'),
                        onPressed: () =>
                            _abrirLanding(widget.academia!.landingUrl),
                      ),
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: OutlinedButton.icon(
                        style: OutlinedButton.styleFrom(
                            foregroundColor: lima,
                            side: const BorderSide(color: lima)),
                        icon: const Icon(Icons.share_outlined, size: 18),
                        label: const Text('Compartir'),
                        onPressed: () => WhatsAppLink.compartir(
                            'Mira nuestra página: ${widget.academia!.landingUrl}'),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 6),
                const Text(
                    'Genérala o actualízala desde "Servicios" (📣) cuando cambies '
                    'tu tarifario o fotos.',
                    style: TextStyle(color: textoTenue, fontSize: 11.5)),
              ] else ...[
                Text(
                    widget.academia == null
                        ? '¿No tienes web? Guarda la academia y contrata tu '
                            'landing en "Servicios Pichangol" (📣): la generamos '
                            'con tus datos.'
                        : '¿No tienes web? Contrata tu landing en "Servicios '
                            'Pichangol": la generamos con los datos de tu academia '
                            'y el enlace aparece aquí solo.',
                    style: const TextStyle(color: textoTenue, fontSize: 12)),
                const SizedBox(height: 8),
                if (widget.academia != null)
                  SizedBox(
                    width: double.infinity,
                    child: FilledButton.icon(
                      style: FilledButton.styleFrom(
                          backgroundColor: lima,
                          foregroundColor: Colors.white,
                          padding: const EdgeInsets.symmetric(vertical: 12)),
                      icon: const Icon(Icons.campaign_outlined, size: 18),
                      label: const Text('Contratar mi landing (Servicios)'),
                      onPressed: () => Navigator.of(context).push(
                        MaterialPageRoute(
                          builder: (_) => ServiciosScreen(
                              negocio: appState.negocioServiciosDeAcademia(
                                  widget.academia!)),
                        ),
                      ),
                    ),
                  ),
              ],
            ],
          ),
          const SizedBox(height: 24),
          SizedBox(
            width: double.infinity,
            child: FilledButton(
              style: FilledButton.styleFrom(
                  backgroundColor: lima,
                  foregroundColor: Colors.white,
                  padding: const EdgeInsets.symmetric(vertical: 15)),
              onPressed: _guardando ? null : _guardar,
              child: _guardando
                  ? const SizedBox(
                      height: 20,
                      width: 20,
                      child: CircularProgressIndicator(
                          strokeWidth: 2.4, color: Colors.white),
                    )
                  : const Text('Guardar academia'),
            ),
          ),
        ],
      ),
    );
  }

  String _descPlan(Plan p) {
    final mon = _paisAcademia.moneda; // moneda del país de la sede
    if (p.tipo == TipoPlan.porClase) {
      return 'Por clase · $mon ${p.precioMes.toStringAsFixed(2)} c/u';
    }
    return '${p.tipo.etiqueta} · ${p.meses} ${p.meses == 1 ? 'mes' : 'meses'} · '
        '$mon ${p.precioMes.toStringAsFixed(2)}/mes · Total $mon ${p.total.toStringAsFixed(2)}';
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
                    color: lima, shape: BoxShape.circle),
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

/// Miniatura de una foto del feed con botón para quitarla.
class _MiniFoto extends StatelessWidget {
  const _MiniFoto({required this.imagen, required this.onQuitar});
  final ImageProvider imagen;
  final VoidCallback onQuitar;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 96,
      margin: const EdgeInsets.only(right: 10),
      child: Stack(
        fit: StackFit.expand,
        children: [
          ClipRRect(
            borderRadius: BorderRadius.circular(12),
            child: Image(image: imagen, fit: BoxFit.cover),
          ),
          Positioned(
            top: 4,
            right: 4,
            child: GestureDetector(
              onTap: onQuitar,
              child: Container(
                padding: const EdgeInsets.all(3),
                decoration: const BoxDecoration(
                    color: Colors.black54, shape: BoxShape.circle),
                child: const Icon(Icons.close, size: 15, color: Colors.white),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// Hoja para crear un plan (nombre, tipo, precio/mes, meses).
class _EditorPlan extends StatefulWidget {
  const _EditorPlan({required this.moneda});

  /// Símbolo de moneda del país de la sede de la academia ('S/', 'Bs', '$').
  final String moneda;

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
                  selectedColor: lima,
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
                // Moneda del país de la sede de la academia (no la del device).
                prefixText: '${widget.moneda} '),
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
                      selectedColor: lima,
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
                  backgroundColor: lima,
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

/// Editor de un PROGRAMA del tarifario (matriz): nombre + precio SOCIO por
/// frecuencia (2x–5x). Devuelve un plan mensual por cada frecuencia con precio.
class _EditorPrograma extends StatefulWidget {
  final String moneda;
  /// Planes existentes del programa (para EDITAR). null/vacío = crear nuevo.
  final List<Plan>? base;
  const _EditorPrograma({required this.moneda, this.base});
  @override
  State<_EditorPrograma> createState() => _EditorProgramaState();
}

class _EditorProgramaState extends State<_EditorPrograma> {
  final _prog = TextEditingController();
  final _etapa = TextEditingController();
  final _duracion = TextEditingController();
  static const _frecs = [2, 3, 4, 5];
  final Map<int, TextEditingController> _precio = {
    for (final f in [2, 3, 4, 5]) f: TextEditingController(),
  };

  bool get _editando => (widget.base?.isNotEmpty ?? false);

  @override
  void initState() {
    super.initState();
    final base = widget.base;
    if (base != null && base.isNotEmpty) {
      final first = base.first;
      _prog.text = first.programa;
      _etapa.text = first.etapaEdad;
      _duracion.text = first.duracionClase;
      for (final p in base) {
        final c = _precio[p.frecuenciaSemana];
        if (c != null && p.precioMes > 0) {
          c.text = p.precioMes.toStringAsFixed(0);
        }
      }
    }
  }

  @override
  void dispose() {
    _prog.dispose();
    _etapa.dispose();
    _duracion.dispose();
    for (final c in _precio.values) {
      c.dispose();
    }
    super.dispose();
  }

  void _guardar() {
    final prog = _prog.text.trim();
    if (prog.isEmpty) return;
    final etapa = _etapa.text.trim();
    final duracion = _duracion.text.trim();
    final planes = <Plan>[];
    for (final f in _frecs) {
      final v = double.tryParse(_precio[f]!.text.trim().replaceAll(',', '.'));
      if (v != null && v > 0) {
        planes.add(Plan(
          id: '$prog | ${f}x',
          nombre: '$prog · ${f}x/sem',
          tipo: TipoPlan.mensual,
          precioMes: v,
          meses: 1,
          programa: prog,
          frecuenciaSemana: f,
          etapaEdad: etapa,
          duracionClase: duracion,
        ));
      }
    }
    Navigator.pop(context, planes);
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.fromLTRB(
          20, 14, 20, 20 + MediaQuery.of(context).viewInsets.bottom),
      child: ConstrainedBox(
        constraints: BoxConstraints(
            maxHeight: MediaQuery.of(context).size.height * 0.85),
        child: SingleChildScrollView(
          child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Center(
            child: Container(
                width: 44,
                height: 5,
                decoration: BoxDecoration(
                    color: Colors.black12,
                    borderRadius: BorderRadius.circular(10))),
          ),
          const SizedBox(height: 16),
          Text(_editando ? 'Editar programa' : 'Programa del tarifario',
              style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w800)),
          const SizedBox(height: 4),
          const Text(
              'Precio SOCIO por frecuencia. Deja en blanco las que no ofreces. '
              'El invitado se calcula con el recargo de la academia.',
              style: TextStyle(color: textoTenue, fontSize: 13)),
          const SizedBox(height: 14),
          TextField(
            controller: _prog,
            decoration: const InputDecoration(
                labelText: 'Programa', hintText: 'Ej.: Bola Roja y Naranja'),
          ),
          const SizedBox(height: 10),
          TextField(
            controller: _etapa,
            decoration: const InputDecoration(
                labelText: 'Etapa / Edad',
                hintText: 'Ej.: Iniciación e intermedio · 5 a 10 años',
                isDense: true),
          ),
          const SizedBox(height: 10),
          TextField(
            controller: _duracion,
            decoration: const InputDecoration(
                labelText: 'Duración de clase',
                hintText: 'Ej.: 1 h 30 min',
                isDense: true),
          ),
          const SizedBox(height: 6),
          const Text('Precio socio por frecuencia (veces x semana):',
              style: TextStyle(
                  color: textoTenue, fontSize: 12, fontWeight: FontWeight.w600)),
          for (final f in _frecs)
            Padding(
              padding: const EdgeInsets.only(top: 10),
              child: Row(
                children: [
                  SizedBox(
                      width: 84,
                      child: Text('${f}x/sem',
                          style: const TextStyle(fontWeight: FontWeight.w700))),
                  Expanded(
                    child: TextField(
                      controller: _precio[f],
                      keyboardType: TextInputType.number,
                      decoration: InputDecoration(
                          prefixText: '${widget.moneda} ',
                          hintText: 'socio / mes',
                          isDense: true),
                    ),
                  ),
                ],
              ),
            ),
          const SizedBox(height: 18),
          SizedBox(
            width: double.infinity,
            child: FilledButton(
              style: FilledButton.styleFrom(
                  backgroundColor: lima,
                  foregroundColor: Colors.white,
                  padding: const EdgeInsets.symmetric(vertical: 14)),
              onPressed: _guardar,
              child: Text(_editando ? 'Guardar cambios' : 'Agregar programa'),
            ),
          ),
        ],
          ),
        ),
      ),
    );
  }
}
