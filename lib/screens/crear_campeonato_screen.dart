import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart';
import 'package:image_picker/image_picker.dart';

import '../models/campeonato.dart';
import '../models/models.dart';
import '../config/pais.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/wizard_pichangol.dart';
import '../widgets/responsive.dart';

/// Una categoría estándar de campeonato. Las de edad auto-setean edadMin/edadMax
/// (Sub-N = hasta N años; +N = desde N). Al inscribirse, el sistema valida la
/// edad real (DNI/Cédula/CI + nacimiento) contra ese rango y rechaza si no
/// clasifica. `null` en ambos = sin tope de edad (Abierta/Libre).
class CatCampeonato {
  final String label;
  final int? edadMin;
  final int? edadMax;
  const CatCampeonato(this.label, {this.edadMin, this.edadMax});
}

/// Catálogo de categorías propuestas en el combo (+ opción "Otra" libre).
const List<CatCampeonato> catalogoCategorias = [
  CatCampeonato('Sub-8', edadMax: 8),
  CatCampeonato('Sub-10', edadMax: 10),
  CatCampeonato('Sub-12', edadMax: 12),
  CatCampeonato('Sub-14', edadMax: 14),
  CatCampeonato('Sub-16', edadMax: 16),
  CatCampeonato('Sub-18', edadMax: 18),
  CatCampeonato('Sub-21', edadMax: 21),
  CatCampeonato('Sub-23', edadMax: 23),
  CatCampeonato('+35 (Máster)', edadMin: 35),
  CatCampeonato('+40 (Máster)', edadMin: 40),
  CatCampeonato('+45 (Máster)', edadMin: 45),
  CatCampeonato('+50 (Máster)', edadMin: 50),
  CatCampeonato('Abierta / Libre'),
];

/// Formulario para CREAR o EDITAR un campeonato. Si [editar] no es null, precarga
/// sus datos y al guardar reemplaza el existente (conserva id, código, dueño,
/// participantes y fixture); si es null, crea uno nuevo.
class CrearCampeonatoScreen extends StatefulWidget {
  const CrearCampeonatoScreen(
      {super.key, required this.academiaId, this.deporteSugerido, this.editar});
  final String academiaId;
  final Deporte? deporteSugerido;
  final Campeonato? editar;

  @override
  State<CrearCampeonatoScreen> createState() => _CrearCampeonatoScreenState();
}

class _CrearCampeonatoScreenState extends State<CrearCampeonatoScreen> {
  final _nombre = TextEditingController();
  final _categoria = TextEditingController();
  final _costo = TextEditingController();
  // Publicidad del torneo: premios (uno por línea) y auspiciador oficial.
  late final _premios =
      TextEditingController(text: widget.editar?.premios ?? '');
  late final _auspiciador =
      TextEditingController(text: widget.editar?.auspiciador ?? '');
  late Deporte _deporte = widget.deporteSugerido ?? Deporte.futbol;
  FormatoTorneo _formato = FormatoTorneo.eliminacion;
  DateTimeRange? _rango;
  String _sedeNombre = '';
  LatLng? _sedeUbicacion;
  // Cronograma + verificación (Fase 1).
  DateTime? _cierreInscripcion;
  bool _relampago = false;
  bool _exigeDni = false;
  final _edadMin = TextEditingController();
  final _edadMax = TextEditingController();
  // Fútbol: mínimo de jugadores por equipo para marcarlo "completo".
  final _minJug = TextEditingController();
  // Categoría elegida del combo (label del catálogo) o el sentinel 'otra'
  // (texto libre). null = aún no elige (sin categoría).
  String? _catSel;
  // Logo del campeonato (opcional). Se sube a Storage recién al guardar (cuando
  // ya existe el id), para no crear filas huérfanas.
  Uint8List? _logoBytes;
  bool _guardando = false;
  // Modo edición: logo ya guardado en la nube y fechas actuales (texto), para
  // conservarlos si el usuario no elige nuevos.
  String? _logoUrlActual;
  String _fechasIniciales = '';

  bool get _editando => widget.editar != null;

  /// Moneda del país de la SEDE del torneo (no la del dispositivo): el costo de
  /// inscripción se muestra y congela en ella. Sin sede ubicada, cae al país
  /// activo.
  String get _monedaSede => _sedeUbicacion != null
      ? monedaDeCoordenadas(_sedeUbicacion!.latitude, _sedeUbicacion!.longitude)
      : paisActual.moneda;

  /// Texto del combo: label + pista del rango de edad.
  String _labelCat(CatCampeonato c) {
    if (c.edadMax != null) return '${c.label} · hasta ${c.edadMax} años';
    if (c.edadMin != null) return '${c.label} · desde ${c.edadMin} años';
    return '${c.label} · sin límite de edad';
  }

  /// Al elegir categoría del combo: si es del catálogo, fija el nombre y la edad
  /// automáticamente (y exige documento si es por edad); "otra" abre texto libre.
  void _elegirCategoria(String? sel) {
    setState(() {
      _catSel = sel;
      if (sel == null) return;
      if (sel == 'otra') {
        _categoria.clear();
        _edadMin.clear();
        _edadMax.clear();
        return;
      }
      final cat = catalogoCategorias.firstWhere((c) => c.label == sel);
      _categoria.text = cat.label;
      _edadMin.text = cat.edadMin?.toString() ?? '';
      _edadMax.text = cat.edadMax?.toString() ?? '';
      // Una categoría por edad EXIGE documento para validar la edad real.
      if (cat.edadMin != null || cat.edadMax != null) _exigeDni = true;
    });
  }

  static const _meses = [
    'ene', 'feb', 'mar', 'abr', 'may', 'jun',
    'jul', 'ago', 'set', 'oct', 'nov', 'dic'
  ];

  /// Formato por defecto según el deporte (natación = por tiempos).
  static FormatoTorneo _formatoDe(Deporte d) => d == Deporte.natacion
      ? FormatoTorneo.tiempos
      : d == Deporte.futbol
          ? FormatoTorneo.liga
          : FormatoTorneo.eliminacion;

  /// Formatos ofrecibles según el deporte: natación solo "por tiempos"; el resto,
  /// eliminación o liga (nunca por tiempos).
  List<FormatoTorneo> get _formatosDisponibles => _deporte == Deporte.natacion
      ? const [FormatoTorneo.tiempos]
      : const [FormatoTorneo.eliminacion, FormatoTorneo.liga];

  @override
  void initState() {
    super.initState();
    final e = widget.editar;
    if (e != null) {
      // Precarga todos los campos del campeonato a editar.
      _nombre.text = e.nombre;
      _deporte = e.deporte;
      _formato = e.formato;
      _categoria.text = e.categoria;
      _costo.text = e.costoInscripcion > 0
          ? e.costoInscripcion.toStringAsFixed(2)
          : '';
      _sedeNombre = e.sede;
      _sedeUbicacion = e.sedeUbicacion;
      _cierreInscripcion = e.inscripcionHasta;
      _relampago = e.relampago;
      _exigeDni = e.exigeDni;
      _edadMin.text = e.edadMin?.toString() ?? '';
      _edadMax.text = e.edadMax?.toString() ?? '';
      _minJug.text =
          e.minJugadoresEquipo > 0 ? e.minJugadoresEquipo.toString() : '';
      _logoUrlActual = e.logoUrl;
      _fechasIniciales = e.fechas;
      // Categoría: si coincide con una del catálogo, selecciona ese ítem; si no,
      // "otra" (texto libre); vacía = sin selección.
      if (e.categoria.isEmpty) {
        _catSel = null;
      } else if (catalogoCategorias.any((c) => c.label == e.categoria)) {
        _catSel = e.categoria;
      } else {
        _catSel = 'otra';
      }
      return;
    }
    _formato = _formatoDe(_deporte);
    // Sede por defecto: la de la academia (si tiene ubicación).
    for (final a in appState.academias) {
      if (a.id == widget.academiaId) {
        if (a.sedeClub.isNotEmpty) _sedeNombre = a.sedeClub;
        _sedeUbicacion = a.sedeUbicacion;
        break;
      }
    }
  }

  String _fmtRango(DateTimeRange r) {
    final a = r.start, b = r.end;
    if (a.year == b.year && a.month == b.month && a.day == b.day) {
      return '${a.day} ${_meses[a.month - 1]} ${a.year}';
    }
    if (a.year == b.year && a.month == b.month) {
      return '${a.day}–${b.day} ${_meses[a.month - 1]} ${a.year}';
    }
    return '${a.day} ${_meses[a.month - 1]} – ${b.day} ${_meses[b.month - 1]} ${b.year}';
  }

  Future<void> _elegirFechas() async {
    final hoy = DateTime.now();
    final r = await showDateRangePicker(
      context: context,
      firstDate: DateTime(hoy.year, hoy.month, hoy.day),
      lastDate: DateTime(hoy.year + 1, 12, 31),
      initialDateRange: _rango,
      helpText: 'Fechas del campeonato',
      saveText: 'Listo',
    );
    if (r != null) setState(() => _rango = r);
  }

  String _fmtFecha(DateTime d) =>
      '${d.day} ${_meses[d.month - 1]} ${d.year}';

  Future<void> _elegirCierre() async {
    final hoy = DateTime.now();
    final r = await showDatePicker(
      context: context,
      firstDate: DateTime(hoy.year, hoy.month, hoy.day),
      lastDate: DateTime(hoy.year + 1, 12, 31),
      initialDate: _cierreInscripcion ?? hoy,
      helpText: 'Cierre de inscripciones',
    );
    if (r != null) setState(() => _cierreInscripcion = r);
  }

  Future<void> _elegirSede() async {
    final sel = await showModalBottomSheet<Cancha>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Theme.of(context).colorScheme.surface,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      builder: (_) => const _SelectorSede(),
    );
    if (sel != null) {
      setState(() {
        _sedeNombre = sel.nombre;
        _sedeUbicacion = sel.ubicacion;
      });
    }
  }

  Future<void> _elegirLogo() async {
    final XFile? f = await ImagePicker().pickImage(
        source: ImageSource.gallery, maxWidth: 600, imageQuality: 85);
    if (f == null) return;
    final bytes = await f.readAsBytes();
    if (!mounted) return;
    setState(() => _logoBytes = bytes);
  }

  Future<void> _guardar() async {
    if (_nombre.text.trim().isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text('Ponle un nombre al campeonato.')));
      return;
    }
    setState(() => _guardando = true);
    // Fechas: si el usuario eligió un nuevo rango, se usa; si no, conserva las
    // que ya tenía (modo edición) o vacío (creación).
    final fechas = _rango != null ? _fmtRango(_rango!) : _fechasIniciales;
    final costo = double.tryParse(_costo.text.trim().replaceAll(',', '.')) ?? 0;
    // El rango de edad solo tiene sentido si se exige documento (así se valida
    // la edad real). Sin DNI, se limpia para no dejar un tope "fantasma".
    final edadMin = _exigeDni ? int.tryParse(_edadMin.text.trim()) : null;
    final edadMax = _exigeDni ? int.tryParse(_edadMax.text.trim()) : null;
    // Cupo mínimo por equipo: solo aplica a fútbol (por equipos).
    final minJug = _deporte == Deporte.futbol
        ? (int.tryParse(_minJug.text.trim()) ?? 0)
        : 0;

    final Campeonato c;
    if (_editando) {
      final e = widget.editar!;
      // EDITAR: se reconstruye conservando id, código, dueño, participantes,
      // fixture y pruebas; solo cambian los campos editables. Se construye
      // directo (no copyWith) para poder BORRAR el rango de edad (null). La
      // moneda se recongela por la sede (por si cambió de país).
      c = Campeonato(
        id: e.id,
        academiaId: e.academiaId,
        dueno: e.dueno,
        codigo: e.codigo,
        nombre: _nombre.text.trim(),
        deporte: e.deporte,
        formato: _formato,
        categoria: _categoria.text.trim(),
        sede: _sedeNombre,
        sedeUbicacion: _sedeUbicacion,
        fechas: fechas,
        costoInscripcion: costo,
        inscripcionAbierta: e.inscripcionAbierta,
        participantes: e.participantes,
        partidos: e.partidos,
        pruebas: e.pruebas,
        cerrado: e.cerrado,
        moneda: _monedaSede,
        inscripcionHasta: _cierreInscripcion,
        inicio: _rango?.start ?? e.inicio,
        relampago: _relampago,
        exigeDni: _exigeDni,
        edadMin: edadMin,
        edadMax: edadMax,
        logoUrl: e.logoUrl,
        minJugadoresEquipo: minJug,
        premios: _premios.text.trim(),
        auspiciador: _auspiciador.text.trim(),
        // Conservar los LOGOS de auspiciadores ya subidos: al reconstruir sin
        // este campo, la edición los borraba (default = lista vacía).
        auspiciadoresLogos: e.auspiciadoresLogos,
      );
      appState.guardarCampeonato(c);
    } else {
      c = appState.crearCampeonato(
        academiaId: widget.academiaId,
        nombre: _nombre.text.trim(),
        deporte: _deporte,
        formato: _formato,
        categoria: _categoria.text.trim(),
        sede: _sedeNombre,
        sedeUbicacion: _sedeUbicacion,
        fechas: fechas,
        costoInscripcion: costo,
        inscripcionHasta: _cierreInscripcion,
        inicio: _rango?.start,
        relampago: _relampago,
        exigeDni: _exigeDni,
        edadMin: edadMin,
        edadMax: edadMax,
        minJugadoresEquipo: minJug,
        premios: _premios.text.trim(),
        auspiciador: _auspiciador.text.trim(),
      );
    }
    // Sube el logo (si eligió uno nuevo) ahora que el campeonato ya tiene id.
    if (_logoBytes != null) {
      await appState.ponerLogoCampeonato(c.id, _logoBytes!);
    }
    if (!mounted) return;
    setState(() => _guardando = false);
    Navigator.of(context).pop(c);
  }

  @override
  // WIZARD estilo Airbnb (regla de UI de los flujos de creación).
  int _paso = 0;

  bool _validarPaso(int i) {
    if (i == 0 && _nombre.text.trim().isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text('Ponle nombre al campeonato para continuar.')));
      return false;
    }
    return true;
  }

  @override
  Widget build(BuildContext context) {
    return WizardPichangol(
      paso: _paso,
      onPaso: (v) => setState(() => _paso = v),
      onEnviar: _guardar,
      enviando: _guardando,
      textoEnviar: _editando ? 'Guardar cambios' : 'Crear campeonato',
      tituloSalir:
          _editando ? '¿Salir sin guardar?' : '¿Salir sin crear el campeonato?',
      validarPaso: _validarPaso,
      pasos: [
        PasoWizard(
          titulo: _editando ? 'Edita tu campeonato' : 'Presenta tu campeonato',
          sub: 'El logo y el nombre son la cara del torneo: así lo verán los '
              'jugadores al inscribirse.',
          hijos: _hijosPresentacion(context),
        ),
        PasoWizard(
          titulo: 'Formato y categoría',
          sub: 'Cómo se compite (llave, liga o tiempos) y para quién es.',
          hijos: _hijosFormato(context),
        ),
        PasoWizard(
          titulo: 'Fechas, sede y reglas',
          sub: 'Cuándo y dónde se juega, cuánto cuesta inscribirse y si '
              'exiges identidad verificada.',
          hijos: _hijosLogistica(context),
        ),
      ],
    );
  }

  List<Widget> _hijosPresentacion(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return [
          // Logo del campeonato (opcional): avatar grande tocable con badge de
          // cámara. Se sube al guardar.
          Center(child: _SelectorLogo(
            bytes: _logoBytes,
            logoUrl: _logoUrlActual,
            deporte: _deporte,
            onTap: _elegirLogo,
          )),
          const SizedBox(height: 18),
          TextField(
            controller: _nombre,
            textCapitalization: TextCapitalization.words,
            decoration: const InputDecoration(
                labelText: 'Nombre del campeonato',
                hintText: 'Copa Verano CEANDE'),
          ),
          const SizedBox(height: 16),
          Text('Deporte',
              style:
                  TextStyle(fontWeight: FontWeight.w700, color: cs.onSurface)),
          const SizedBox(height: 8),
          Wrap(
            spacing: 8,
            children: [
              for (final d in Deporte.values)
                ChoiceChip(
                  label: Text('${emojiDeporte(d)}  ${d.etiqueta}'),
                  selected: _deporte == d,
                  // Al editar, el deporte NO se cambia (participantes y fixture
                  // dependen de él): se muestra fijo.
                  onSelected: _editando
                      ? null
                      : (_) => setState(() {
                            _deporte = d;
                            _formato = _formatoDe(d);
                          }),
                ),
            ],
          ),
          if (_editando)
            const Padding(
              padding: EdgeInsets.only(top: 6),
              child: Text('El deporte no se puede cambiar en un campeonato ya '
                  'creado.',
                  style: TextStyle(color: textoTenue, fontSize: 12)),
            ),
    ];
  }

  List<Widget> _hijosFormato(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return [
          Text('Formato',
              style:
                  TextStyle(fontWeight: FontWeight.w700, color: cs.onSurface)),
          const SizedBox(height: 8),
          for (final f in _formatosDisponibles)
            RadioListTile<FormatoTorneo>(
              contentPadding: EdgeInsets.zero,
              value: f,
              groupValue: _formato,
              // Si ya se generó el fixture, cambiar el formato lo rompería: se
              // bloquea hasta rehacer/reiniciar el torneo.
              onChanged: (_editando && widget.editar!.fixtureGenerado)
                  ? null
                  : (v) => setState(() => _formato = v!),
              title: Text(f.etiqueta),
              subtitle: Text(switch (f) {
                FormatoTorneo.eliminacion =>
                  'Llave: el ganador avanza (ideal tenis/pádel).',
                FormatoTorneo.liga =>
                  'Todos contra todos + tabla (ideal fútbol).',
                FormatoTorneo.tiempos =>
                  'Cada nadador registra su TIEMPO por prueba; se rankea del más '
                      'rápido al más lento (sin partidos G/P).',
              }),
            ),
          if (_editando && widget.editar!.fixtureGenerado)
            const Padding(
              padding: EdgeInsets.only(bottom: 4),
              child: Text('El formato no se cambia porque el fixture ya está '
                  'generado.',
                  style: TextStyle(color: textoTenue, fontSize: 12)),
            ),
          const SizedBox(height: 8),
          // Fútbol (por equipos): mínimo de jugadores para marcar el equipo como
          // "completo". Cada capitán arma su plantel; al llegar a este mínimo, al
          // organizador le aparece "✅ Completo".
          if (_deporte == Deporte.futbol) ...[
            TextField(
              controller: _minJug,
              keyboardType: TextInputType.number,
              decoration: const InputDecoration(
                labelText: 'Mínimo de jugadores por equipo (opcional)',
                hintText: 'ej. 7',
                helperText: 'Cada equipo aparece "Completo" al llegar a este '
                    'número. Vacío = solo se muestra el conteo.',
                helperMaxLines: 3,
              ),
            ),
            const SizedBox(height: 12),
          ],
          // Categoría: combo de categorías estándar (las de edad auto-setean el
          // rango y exigen documento al inscribirse) + "Otra" texto libre.
          DropdownButtonFormField<String>(
            value: _catSel,
            isExpanded: true,
            decoration: const InputDecoration(labelText: 'Categoría (opcional)'),
            items: [
              for (final c in catalogoCategorias)
                DropdownMenuItem(value: c.label, child: Text(_labelCat(c))),
              const DropdownMenuItem(
                  value: 'otra', child: Text('Otra… (escribir)')),
            ],
            onChanged: _elegirCategoria,
          ),
          if (_catSel == 'otra') ...[
            const SizedBox(height: 10),
            TextField(
              controller: _categoria,
              textCapitalization: TextCapitalization.words,
              decoration: const InputDecoration(
                  labelText: 'Nombre de la categoría',
                  hintText: 'Ej. Damas B, Nivel intermedio, Mixto…'),
            ),
          ],
    ];
  }

  List<Widget> _hijosLogistica(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return [
          // Fechas (calendario).
          _CampoTap(
            icon: Icons.event,
            label: _relampago ? 'Fecha (relámpago, un día)' : 'Fechas de juego',
            // Al editar sin tocar el calendario, muestra las fechas actuales.
            valor: _rango != null
                ? _fmtRango(_rango!)
                : (_fechasIniciales.isNotEmpty
                    ? _fechasIniciales
                    : 'Elegir en el calendario'),
            vacio: _rango == null && _fechasIniciales.isEmpty,
            onTap: _elegirFechas,
          ),
          const SizedBox(height: 12),
          // Cronograma: cierre de inscripciones (al llegar se sortea el fixture).
          _CampoTap(
            icon: Icons.how_to_reg,
            label: 'Cierre de inscripciones',
            valor: _cierreInscripcion == null
                ? 'Hasta cuándo pueden inscribirse'
                : _fmtFecha(_cierreInscripcion!),
            vacio: _cierreInscripcion == null,
            onTap: _elegirCierre,
          ),
          const SizedBox(height: 4),
          SwitchListTile(
            contentPadding: EdgeInsets.zero,
            value: _relampago,
            onChanged: (v) => setState(() => _relampago = v),
            title: const Text('Relámpago (todo en un día)'),
            subtitle: const Text(
                'Apágalo si el campeonato se juega en varias fechas.'),
          ),
          const SizedBox(height: 8),
          // Sede (del listado de ubicaciones del app + mapa).
          _CampoTap(
            icon: Icons.place,
            label: 'Sede',
            valor: _sedeNombre.isEmpty
                ? 'Elegir del listado de canchas'
                : _sedeNombre +
                    (_sedeUbicacion != null ? '  ·  📍 ubicada' : ''),
            vacio: _sedeNombre.isEmpty,
            onTap: _elegirSede,
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _costo,
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            decoration: InputDecoration(
                labelText: 'Costo de inscripción (opcional)',
                prefixText: '$_monedaSede '),
          ),
          const SizedBox(height: 18),
          // Verificación por DNI (opcional del organizador).
          Text('Verificación',
              style:
                  TextStyle(fontWeight: FontWeight.w700, color: cs.onSurface)),
          SwitchListTile(
            contentPadding: EdgeInsets.zero,
            value: _exigeDni,
            onChanged: (v) => setState(() => _exigeDni = v),
            title: Text('Exigir $docIdActual para inscribirse'),
            subtitle: const Text(
                'Valida identidad y calcula la edad real (evita que se hagan '
                'pasar por otra edad en categorías Sub-N). Donde hay registro '
                'oficial (Perú, Ecuador).'),
          ),
          if (_exigeDni) ...[
            const SizedBox(height: 4),
            Text('Rango de edad de la categoría (opcional)',
                style: const TextStyle(color: textoTenue, fontSize: 12.5)),
            const SizedBox(height: 8),
            Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _edadMin,
                    keyboardType: TextInputType.number,
                    decoration: const InputDecoration(
                        labelText: 'Edad mín', hintText: 'ej. 18'),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: TextField(
                    controller: _edadMax,
                    keyboardType: TextInputType.number,
                    decoration: const InputDecoration(
                        labelText: 'Edad máx', hintText: 'ej. 30 (Sub-30)'),
                  ),
                ),
              ],
            ),
          ],
          const SizedBox(height: 20),
          // ── Publicidad del torneo (pedido del director): premios y
          // auspiciador se lucen en el mensaje de compartir (estilo RALLY
          // CHALLENGE) y en la página pública del campeonato. ──
          const Text('Publicidad del torneo 📣',
              style: TextStyle(fontWeight: FontWeight.w700)),
          const SizedBox(height: 4),
          const Text(
              'Los premios y el auspiciador salen en el mensaje de WhatsApp y '
              'en la página del torneo.',
              style: TextStyle(color: textoTenue, fontSize: 12)),
          const SizedBox(height: 10),
          TextField(
            controller: _auspiciador,
            textCapitalization: TextCapitalization.characters,
            decoration: const InputDecoration(
                labelText: 'Auspiciador oficial (opcional)',
                hintText: 'Ej. JORDI MEAT BOUTIQUE'),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _premios,
            maxLines: 4,
            textCapitalization: TextCapitalization.sentences,
            decoration: const InputDecoration(
                labelText: 'Premios (uno por línea, opcional)',
                hintText: 'Trofeos para campeones y subcampeones\n'
                    'Raqueteros WILSON\nTarros de pelotas',
                alignLabelWithHint: true),
          ),
    ];
  }
}

/// Avatar grande y tocable para elegir el LOGO del campeonato en el formulario
/// de creación. Muestra la imagen elegida (aún local, sin subir) o el ícono del
/// deporte, con un badge de cámara y una etiqueta "Agregar logo".
class _SelectorLogo extends StatelessWidget {
  const _SelectorLogo(
      {required this.bytes,
      required this.deporte,
      required this.onTap,
      this.logoUrl});
  final Uint8List? bytes;
  final String? logoUrl;
  final Deporte deporte;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final tieneUrl = logoUrl != null && logoUrl!.isNotEmpty;
    // Prioridad: la imagen recién elegida (bytes) > el logo ya guardado (url) >
    // el ícono del deporte.
    final ImageProvider? img = bytes != null
        ? MemoryImage(bytes!)
        : (tieneUrl ? NetworkImage(logoUrl!) as ImageProvider : null);
    return Column(
      children: [
        GestureDetector(
          onTap: onTap,
          child: Stack(
            clipBehavior: Clip.none,
            children: [
              CircleAvatar(
                radius: 44,
                backgroundColor: colorDeporte(deporte),
                backgroundImage: img,
                child: img == null
                    ? Icon(iconoDeporte(deporte),
                        color: Colors.white, size: 40)
                    : null,
              ),
              Positioned(
                right: -2,
                bottom: -2,
                child: Container(
                  padding: const EdgeInsets.all(6),
                  decoration: BoxDecoration(
                    color: lima,
                    shape: BoxShape.circle,
                    border: Border.all(color: cs.surface, width: 2),
                  ),
                  child: const Icon(Icons.photo_camera,
                      size: 16, color: Colors.white),
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 8),
        Text((bytes == null && !tieneUrl)
            ? 'Agregar logo (opcional)'
            : 'Cambiar logo',
            style: const TextStyle(color: textoTenue, fontSize: 13)),
      ],
    );
  }
}

/// Campo tipo "pastilla" tocable (fecha/sede) con ícono, etiqueta y valor.
class _CampoTap extends StatelessWidget {
  const _CampoTap({
    required this.icon,
    required this.label,
    required this.valor,
    required this.vacio,
    required this.onTap,
  });
  final IconData icon;
  final String label;
  final String valor;
  final bool vacio;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Material(
      color: cs.surface,
      borderRadius: BorderRadius.circular(14),
      child: InkWell(
        borderRadius: BorderRadius.circular(14),
        onTap: onTap,
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
          decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(14),
              border: Border.all(color: trazo)),
          child: Row(
            children: [
              Icon(icon, color: cs.primary, size: 22),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(label,
                        style:
                            const TextStyle(color: textoTenue, fontSize: 12)),
                    const SizedBox(height: 2),
                    Text(valor,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                            fontWeight: FontWeight.w700,
                            color: vacio ? textoTenue : cs.onSurface)),
                  ],
                ),
              ),
              Icon(Icons.chevron_right, color: cs.primary),
            ],
          ),
        ),
      ),
    );
  }
}

/// Selector de sede: lista las canchas/clubes conocidos del app (con búsqueda)
/// para que el profe elija la ubicación exacta del campeonato.
class _SelectorSede extends StatefulWidget {
  const _SelectorSede();
  @override
  State<_SelectorSede> createState() => _SelectorSedeState();
}

class _SelectorSedeState extends State<_SelectorSede> {
  String _q = '';

  @override
  Widget build(BuildContext context) {
    // Canchas únicas por nombre (con ubicación).
    final vistas = <String>{};
    final lista = <Cancha>[];
    for (final c in appState.todasLasCanchas()) {
      if (vistas.add(c.nombre.toLowerCase())) lista.add(c);
    }
    final filtro = _q.trim().toLowerCase();
    final res = filtro.isEmpty
        ? lista
        : lista
            .where((c) =>
                c.nombre.toLowerCase().contains(filtro) ||
                (c.direccion ?? '').toLowerCase().contains(filtro))
            .toList();
    return Padding(
      padding: EdgeInsets.fromLTRB(
          16, 14, 16, 16 + MediaQuery.of(context).viewInsets.bottom),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text('Elige la sede',
              style: TextStyle(fontWeight: FontWeight.w800, fontSize: 17)),
          const SizedBox(height: 10),
          TextField(
            autofocus: true,
            onChanged: (v) => setState(() => _q = v),
            decoration: const InputDecoration(
                hintText: 'Buscar cancha o club',
                prefixIcon: Icon(Icons.search)),
          ),
          const SizedBox(height: 8),
          ConstrainedBox(
            constraints: BoxConstraints(
                maxHeight: MediaQuery.of(context).size.height * 0.5),
            child: res.isEmpty
                ? const Padding(
                    padding: EdgeInsets.all(20),
                    child: Text('Sin resultados.',
                        style: TextStyle(color: textoTenue)),
                  )
                : ListView.builder(
                    shrinkWrap: true,
                    itemCount: res.length,
                    itemBuilder: (_, i) {
                      final c = res[i];
                      return ListTile(
                        leading: Icon(Icons.place,
                            color: Theme.of(context).colorScheme.primary),
                        title: Text(c.nombre,
                            maxLines: 1, overflow: TextOverflow.ellipsis),
                        subtitle: c.direccion == null
                            ? null
                            : Text(c.direccion!,
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis),
                        onTap: () => Navigator.of(context).pop(c),
                      );
                    },
                  ),
          ),
        ],
      ),
    );
  }
}
