import 'package:flutter/material.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart' show LatLng;

import '../models/models.dart';
import '../theme.dart';
import '../widgets/responsive.dart';
import 'buscar_direccion_screen.dart';

/// Lo que devuelve la búsqueda guiada: zona + deporte (obligatorio) +
/// fecha y hora (opcionales para afinar; se muestran en el buscador).
class ResultadoBusquedaGuiada {
  const ResultadoBusquedaGuiada({
    required this.centro,
    required this.etiqueta,
    required this.deporte,
    required this.fecha,
    this.hora,
  });
  final LatLng centro;
  final String etiqueta;
  final Deporte deporte;
  final DateTime fecha;
  final String? hora; // "19:00" o null = cualquier hora
}

/// BÚSQUEDA GUIADA estilo Airbnb ("¿A dónde? → fechas → huéspedes"), versión
/// canchas: ¿Dónde? → ¿Qué deporte? (OBLIGATORIO) → ¿Cuándo? (fecha + hora).
/// Tarjetas apiladas blancas, CTA al pie. Devuelve [ResultadoBusquedaGuiada].
class BusquedaGuiadaScreen extends StatefulWidget {
  const BusquedaGuiadaScreen({
    super.key,
    this.centroInicial,
    this.etiquetaInicial,
    this.deporteInicial,
  });
  final LatLng? centroInicial;
  final String? etiquetaInicial;
  final Deporte? deporteInicial;

  @override
  State<BusquedaGuiadaScreen> createState() => _BusquedaGuiadaScreenState();
}

class _BusquedaGuiadaScreenState extends State<BusquedaGuiadaScreen> {
  LatLng? _centro;
  String? _etiqueta;
  Deporte? _deporte;
  late DateTime _fecha;
  String? _hora; // null = cualquier hora

  static const _deportes = [
    Deporte.futbol,
    Deporte.tenis,
    Deporte.basquet,
    Deporte.voley,
    Deporte.natacion,
  ];

  @override
  void initState() {
    super.initState();
    _centro = widget.centroInicial;
    _etiqueta = widget.etiquetaInicial;
    _deporte = widget.deporteInicial;
    _fecha = DateTime.now();
  }

  bool get _listo => _centro != null && _deporte != null;

  bool _mismoDia(DateTime a, DateTime b) =>
      a.year == b.year && a.month == b.month && a.day == b.day;

  String _fechaTxt(DateTime f) {
    final hoy = DateTime.now();
    if (_mismoDia(f, hoy)) return 'Hoy';
    if (_mismoDia(f, hoy.add(const Duration(days: 1)))) return 'Mañana';
    const dias = ['lun', 'mar', 'mié', 'jue', 'vie', 'sáb', 'dom'];
    const meses = [
      'ene', 'feb', 'mar', 'abr', 'may', 'jun',
      'jul', 'ago', 'sep', 'oct', 'nov', 'dic'
    ];
    return '${dias[f.weekday - 1]} ${f.day} ${meses[f.month - 1]}';
  }

  Future<void> _elegirZona() async {
    final res = await Navigator.of(context).push<ResultadoBusqueda>(
      MaterialPageRoute(builder: (_) => const BuscarDireccionScreen()),
    );
    if (res != null && mounted) {
      setState(() {
        _centro = res.centro;
        _etiqueta = res.etiqueta;
      });
    }
  }

  Future<void> _elegirFecha() async {
    final f = await showDatePicker(
      context: context,
      initialDate: _fecha,
      firstDate: DateTime.now(),
      lastDate: DateTime.now().add(const Duration(days: 60)),
    );
    if (f != null && mounted) setState(() => _fecha = f);
  }

  void _buscar() {
    if (!_listo) return;
    Navigator.of(context).pop(ResultadoBusquedaGuiada(
      centro: _centro!,
      etiqueta: _etiqueta ?? 'Zona elegida',
      deporte: _deporte!,
      fecha: _fecha,
      hora: _hora,
    ));
  }

  /// Tarjeta blanca de sección (estilo Airbnb: radio grande, sombra suave).
  Widget _seccion({required String titulo, required Widget child}) {
    return Container(
      margin: const EdgeInsets.only(bottom: 14),
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: const Color(0xFFE4E4E4)),
        boxShadow: const [
          BoxShadow(color: Color(0x0F000000), blurRadius: 10,
              offset: Offset(0, 3)),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(titulo,
              style: const TextStyle(
                  fontWeight: FontWeight.w800, fontSize: 17, color: tinta)),
          const SizedBox(height: 12),
          child,
        ],
      ),
    );
  }

  Widget _pill(String texto,
      {String emoji = '', required bool activo, required VoidCallback onTap}) {
    return GestureDetector(
      onTap: onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 150),
        padding: const EdgeInsets.symmetric(horizontal: 15, vertical: 10),
        decoration: BoxDecoration(
          color: activo ? const Color(0xFFEBEBEB) : Colors.white,
          borderRadius: BorderRadius.circular(30),
          border: Border.all(
              color:
                  activo ? const Color(0xFFB9B9B9) : const Color(0xFFE4E4E4)),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            if (emoji.isNotEmpty) ...[
              Text(emoji, style: const TextStyle(fontSize: 15)),
              const SizedBox(width: 6),
            ],
            Text(texto,
                style: TextStyle(
                    fontSize: 13.5,
                    fontWeight: activo ? FontWeight.w800 : FontWeight.w600,
                    color: tinta)),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFF4F5F3),
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        leading: IconButton(
          icon: const Icon(Icons.close, color: tinta),
          onPressed: () => Navigator.of(context).pop(),
        ),
        title: const Text('Busca tu cancha',
            style: TextStyle(
                color: tinta, fontWeight: FontWeight.w800, fontSize: 17)),
        centerTitle: true,
      ),
      body: AnchoTablet(
        maxWidth: 560,
        child: ListView(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 120),
          children: [
            // ── ¿Dónde? ────────────────────────────────────────────────
            _seccion(
              titulo: '¿Dónde juegas?',
              child: InkWell(
                onTap: _elegirZona,
                borderRadius: BorderRadius.circular(12),
                child: Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 14, vertical: 13),
                  decoration: BoxDecoration(
                    color: const Color(0xFFF6F9F5),
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(color: const Color(0xFFE4E4E4)),
                  ),
                  child: Row(
                    children: [
                      Icon(Icons.search,
                          size: 20,
                          color: Theme.of(context).colorScheme.primary),
                      const SizedBox(width: 10),
                      Expanded(
                        child: Text(
                          _etiqueta ?? 'Distrito, zona o dirección',
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                              fontWeight: FontWeight.w700,
                              fontSize: 14.5,
                              color: _etiqueta == null
                                  ? textoTenueDe(context)
                                  : tinta),
                        ),
                      ),
                      const Icon(Icons.chevron_right, color: Color(0xFF9A9A9A)),
                    ],
                  ),
                ),
              ),
            ),
            // ── ¿Qué deporte? (OBLIGATORIO) ────────────────────────────
            _seccion(
              titulo: '¿Qué deporte?',
              child: Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  for (final d in _deportes)
                    _pill(d.etiqueta,
                        emoji: emojiDeporte(d),
                        activo: _deporte == d,
                        onTap: () => setState(() => _deporte = d)),
                ],
              ),
            ),
            // ── ¿Cuándo? ───────────────────────────────────────────────
            _seccion(
              titulo: '¿Cuándo?',
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: [
                      _pill('Hoy',
                          activo: _mismoDia(_fecha, DateTime.now()),
                          onTap: () =>
                              setState(() => _fecha = DateTime.now())),
                      _pill('Mañana',
                          activo: _mismoDia(_fecha,
                              DateTime.now().add(const Duration(days: 1))),
                          onTap: () => setState(() => _fecha = DateTime.now()
                              .add(const Duration(days: 1)))),
                      _pill(
                          _mismoDia(_fecha, DateTime.now()) ||
                                  _mismoDia(
                                      _fecha,
                                      DateTime.now()
                                          .add(const Duration(days: 1)))
                              ? 'Elegir fecha'
                              : _fechaTxt(_fecha),
                          emoji: '🗓️',
                          activo: !_mismoDia(_fecha, DateTime.now()) &&
                              !_mismoDia(_fecha,
                                  DateTime.now().add(const Duration(days: 1))),
                          onTap: _elegirFecha),
                    ],
                  ),
                  const SizedBox(height: 14),
                  Text('Hora',
                      style: TextStyle(
                          fontWeight: FontWeight.w700,
                          fontSize: 13,
                          color: textoTenueDe(context))),
                  const SizedBox(height: 8),
                  SingleChildScrollView(
                    scrollDirection: Axis.horizontal,
                    child: Row(
                      children: [
                        Padding(
                          padding: const EdgeInsets.only(right: 8),
                          child: _pill('Cualquier hora',
                              activo: _hora == null,
                              onTap: () => setState(() => _hora = null)),
                        ),
                        for (var h = 6; h <= 22; h++)
                          Padding(
                            padding: const EdgeInsets.only(right: 8),
                            child: _pill(
                                '${h.toString().padLeft(2, '0')}:00',
                                activo: _hora ==
                                    '${h.toString().padLeft(2, '0')}:00',
                                onTap: () => setState(() => _hora =
                                    '${h.toString().padLeft(2, '0')}:00')),
                          ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
      // ── CTA al pie (como Airbnb: Limpiar + Buscar) ────────────────────
      bottomNavigationBar: SafeArea(
        child: Container(
          padding: const EdgeInsets.fromLTRB(16, 10, 16, 12),
          decoration: const BoxDecoration(
            color: Colors.white,
            border: Border(top: BorderSide(color: Color(0xFFE4E4E4))),
          ),
          child: Row(
            children: [
              TextButton(
                onPressed: () => setState(() {
                  _deporte = null;
                  _hora = null;
                  _fecha = DateTime.now();
                }),
                child: const Text('Limpiar',
                    style: TextStyle(
                        color: tinta,
                        fontWeight: FontWeight.w700,
                        decoration: TextDecoration.underline)),
              ),
              const Spacer(),
              Material(
                color: _listo ? bosque : const Color(0xFFCFCFCF),
                borderRadius: BorderRadius.circular(14),
                child: InkWell(
                  borderRadius: BorderRadius.circular(14),
                  onTap: _listo ? _buscar : null,
                  child: const Padding(
                    padding:
                        EdgeInsets.symmetric(horizontal: 26, vertical: 14),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(Icons.search, color: Colors.white, size: 19),
                        SizedBox(width: 8),
                        Text('Buscar canchas',
                            style: TextStyle(
                                color: Colors.white,
                                fontWeight: FontWeight.w800,
                                fontSize: 15)),
                      ],
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
