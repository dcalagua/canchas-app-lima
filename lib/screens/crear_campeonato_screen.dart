import 'package:flutter/material.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart';

import '../models/campeonato.dart';
import '../models/models.dart';
import '../config/pais.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/responsive.dart';

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
  final _costo = TextEditingController();
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

  /// Moneda del país de la SEDE del torneo (no la del dispositivo): el costo de
  /// inscripción se muestra y congela en ella. Sin sede ubicada, cae al país
  /// activo.
  String get _monedaSede => _sedeUbicacion != null
      ? monedaDeCoordenadas(_sedeUbicacion!.latitude, _sedeUbicacion!.longitude)
      : paisActual.moneda;

  static const _meses = [
    'ene', 'feb', 'mar', 'abr', 'may', 'jun',
    'jul', 'ago', 'set', 'oct', 'nov', 'dic'
  ];

  @override
  void initState() {
    super.initState();
    _formato = _deporte == Deporte.futbol
        ? FormatoTorneo.liga
        : FormatoTorneo.eliminacion;
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
      sede: _sedeNombre,
      sedeUbicacion: _sedeUbicacion,
      fechas: _rango == null ? '' : _fmtRango(_rango!),
      costoInscripcion:
          double.tryParse(_costo.text.trim().replaceAll(',', '.')) ?? 0,
      inscripcionHasta: _cierreInscripcion,
      inicio: _rango?.start,
      relampago: _relampago,
      exigeDni: _exigeDni,
      edadMin: int.tryParse(_edadMin.text.trim()),
      edadMax: int.tryParse(_edadMax.text.trim()),
    );
    Navigator.of(context).pop(c);
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(title: const Text('Nuevo campeonato')),
      body: ListView(
        padding: EdgeInsets.fromLTRB(
            ladoTablet(context), 18, ladoTablet(context), 18),
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
              style:
                  TextStyle(fontWeight: FontWeight.w700, color: cs.onSurface)),
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
          const SizedBox(height: 14),
          // Fechas (calendario).
          _CampoTap(
            icon: Icons.event,
            label: _relampago ? 'Fecha (relámpago, un día)' : 'Fechas de juego',
            valor: _rango == null ? 'Elegir en el calendario' : _fmtRango(_rango!),
            vacio: _rango == null,
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
            activeColor: lima,
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
            activeColor: lima,
            onChanged: (v) => setState(() => _exigeDni = v),
            title: const Text('Exigir DNI para inscribirse'),
            subtitle: const Text(
                'Valida identidad y calcula la edad real (evita que se hagan '
                'pasar por otra edad en categorías Sub-N). Solo Perú.'),
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
