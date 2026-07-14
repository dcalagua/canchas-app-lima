import 'package:flutter/material.dart';
import 'package:geocoding/geocoding.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart';

import '../config/pais.dart';
import '../models/models.dart';
import '../services/busqueda_local.dart';
import '../services/concierge_service.dart'; // tipos de sugerencia (UI)
import '../services/location_service.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../utils/geo.dart';
import 'cancha_detalle_screen.dart';
import '../utils/moneda.dart';

/// Asistente Pichangol: chat estilo WhatsApp donde el jugador escribe en
/// lenguaje natural ("fútbol mañana 8pm por Surco") y se le sugieren canchas.
/// La interpretación es LOCAL por reglas (`BusquedaLocal`) — sin IA/tokens, así
/// no cuesta por consulta en un producto B2C. Aquí se cuida el look & feel
/// (header con identidad, burbujas, "escribiendo…", tarjetas ricas).
class AsistenteScreen extends StatefulWidget {
  const AsistenteScreen({super.key, this.centro});

  /// Centro de búsqueda (zona del usuario) para calcular distancias.
  final LatLng? centro;

  @override
  State<AsistenteScreen> createState() => _AsistenteScreenState();
}

class _Turno {
  final bool mio;
  final String texto;
  final List<SugerenciaConcierge> sugerencias;
  final LatLng? centro; // centro usado para este resultado (zona o ubicación)
  _Turno.usuario(this.texto)
      : mio = true,
        sugerencias = const [],
        centro = null;
  _Turno.bot(this.texto, [this.sugerencias = const [], this.centro])
      : mio = false;
}

class _AsistenteScreenState extends State<AsistenteScreen> {
  final _texto = TextEditingController();
  final _scroll = ScrollController();
  final _turnos = <_Turno>[];
  bool _pensando = false;

  // Ubicación real del usuario (GPS), para recomendar según dónde está (Lima,
  // Juliaca, la ciudad que sea). Se resuelve al abrir el asistente.
  LatLng? _ubicacion;

  // Ejemplos SIN distrito fijo: antes decía "Tenis por Surco" (Lima), que
  // confundía a quien está en otra ciudad (p. ej. Juliaca). Ahora se apoyan en
  // "cerca de mí" para buscar según tu ubicación real.
  static const _ejemplos = [
    '⚽ Fútbol hoy 8pm',
    '🎾 Tenis cerca de mí',
    '💸 Algo barato cerca',
  ];

  @override
  void initState() {
    super.initState();
    _ubicacion = widget.centro;
    _turnos.add(_Turno.bot(
        '¡Hola! 👋 Soy tu asistente de reservas.\n\n'
        'Dime qué quieres jugar, cuándo y por dónde, y te busco cancha al toque. 🎾⚽🏓'));
    _resolverUbicacion();
  }

  /// Detecta la ubicación real del usuario (GPS) para recomendar según dónde
  /// está —sea Lima, Juliaca o donde sea— y saluda nombrando su ciudad. Trae
  /// además las canchas cercanas para tener qué recomendar. Fail-safe.
  Future<void> _resolverUbicacion() async {
    var pos = widget.centro;
    pos ??= await LocationService.ultimaConocida();
    pos ??= await LocationService.ubicacionActual();
    if (pos == null || !mounted) return;
    _ubicacion = pos;
    appState.descubrirCanchasCerca(pos); // canchas cerca de donde estás
    try {
      final marks = await placemarkFromCoordinates(pos.latitude, pos.longitude);
      if (!mounted || marks.isEmpty) return;
      final m = marks.first;
      setMonedaPorPais(m.isoCountryCode); // S/ · Bs · $ según el país donde estás
      final ciudad = (m.locality?.trim().isNotEmpty == true
              ? m.locality!
              : (m.subAdministrativeArea?.trim().isNotEmpty == true
                  ? m.subAdministrativeArea!
                  : (m.administrativeArea ?? '')))
          .trim();
      final distrito = (m.subLocality ?? '').trim();
      if (ciudad.isEmpty) return;
      final lugar = distrito.isNotEmpty && distrito != ciudad
          ? '$distrito, $ciudad'
          : ciudad;
      setState(() {
        _turnos[0] = _Turno.bot(
            '¡Hola! 👋 Te ubico en $lugar.\n\n'
            'Dime qué quieres jugar y cuándo, y te busco cancha cerca de ti. 🎾⚽🏓');
      });
    } catch (_) {
      // sin nombre de ciudad: se queda el saludo genérico
    }
  }

  @override
  void dispose() {
    _texto.dispose();
    _scroll.dispose();
    super.dispose();
  }

  Future<void> _enviar([String? sugerido]) async {
    final msg = (sugerido ?? _texto.text).trim();
    if (msg.isEmpty || _pensando) return;
    _texto.clear();
    setState(() {
      _turnos.add(_Turno.usuario(msg));
      _pensando = true;
    });
    _alFinal();

    // Recomendación LOCAL por reglas (sin IA, costo cero). Por defecto según
    // DÓNDE ESTÁS (GPS real). Si además mencionas una zona ("por Surco"), la
    // geolocalizamos y buscamos canchas ahí, ordenando por cercanía a esa zona.
    var centro = _ubicacion ?? widget.centro;
    final zona = _zonaEn(msg);
    if (zona != null) {
      try {
        final locs =
            await locationFromAddress('$zona, ${paisActual.geocodeHint}');
        if (locs.isNotEmpty) {
          centro = LatLng(locs.first.latitude, locs.first.longitude);
          await appState.descubrirCanchasCerca(centro);
        }
      } catch (_) {
        // sin geocodificación: seguimos con el centro que teníamos
      }
    }
    // Breve pausa para el efecto "escribiendo…" (la búsqueda es instantánea).
    await Future.delayed(const Duration(milliseconds: 350));
    if (!mounted) return;

    final canchas = appState.todasLasCanchas();
    final res = BusquedaLocal.recomendar(msg, canchas, centro: centro);
    if (!mounted) return;
    setState(() {
      _pensando = false;
      _turnos.add(_Turno.bot(res.respuesta, res.sugerencias, centro));
    });
    _alFinal();
  }

  void _alFinal() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scroll.hasClients) {
        _scroll.animateTo(_scroll.position.maxScrollExtent,
            duration: const Duration(milliseconds: 260), curve: Curves.easeOut);
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final oscuro = Theme.of(context).brightness == Brightness.dark;
    return Scaffold(
      appBar: AppBar(
        toolbarHeight: 66,
        foregroundColor: Colors.white,
        backgroundColor: bosque,
        surfaceTintColor: Colors.transparent,
        titleSpacing: 4,
        elevation: 4,
        flexibleSpace: const DecoratedBox(
          decoration: BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
              colors: [sage, bosque],
            ),
          ),
        ),
        title: Row(
          children: [
            Container(
              width: 40,
              height: 40,
              decoration: BoxDecoration(
                color: lima,
                shape: BoxShape.circle,
                boxShadow: const [
                  BoxShadow(
                      color: Color(0x40000000),
                      blurRadius: 6,
                      offset: Offset(0, 2)),
                ],
              ),
              child: const Icon(Icons.auto_awesome, color: bosque, size: 21),
            ),
            const SizedBox(width: 11),
            Column(
              mainAxisAlignment: MainAxisAlignment.center,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text('Asistente Pichangol',
                    style: TextStyle(
                        color: Colors.white,
                        fontSize: 16.5,
                        fontWeight: FontWeight.w800)),
                Row(
                  children: [
                    Container(
                      width: 8,
                      height: 8,
                      decoration: const BoxDecoration(
                          color: Color(0xFF3DDC84), shape: BoxShape.circle),
                    ),
                    const SizedBox(width: 6),
                    Text('en línea · te busco cancha',
                        style: TextStyle(
                            color: Colors.white.withOpacity(0.85),
                            fontSize: 11.5)),
                  ],
                ),
              ],
            ),
          ],
        ),
      ),
      body: Container(
        decoration: BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: oscuro
                ? [cs.surface.withOpacity(0.35), Theme.of(context).scaffoldBackgroundColor]
                : const [Color(0xFFF1F4F8), Color(0xFFF7F5EF)],
          ),
        ),
        child: Column(
          children: [
            Expanded(
              child: ListView.builder(
                controller: _scroll,
                padding: const EdgeInsets.fromLTRB(12, 16, 12, 10),
                itemCount: _turnos.length + (_pensando ? 1 : 0),
                itemBuilder: (context, i) {
                  if (i >= _turnos.length) return const _Escribiendo();
                  return _BurbujaTurno(
                      turno: _turnos[i],
                      centro: _turnos[i].centro ?? _ubicacion ?? widget.centro);
                },
              ),
            ),
            if (_turnos.length <= 1)
              SizedBox(
                height: 46,
                child: ListView(
                  scrollDirection: Axis.horizontal,
                  padding: const EdgeInsets.symmetric(horizontal: 12),
                  children: [
                    for (final e in _ejemplos)
                      Padding(
                        padding: const EdgeInsets.only(right: 8),
                        child: _ChipEjemplo(texto: e, onTap: () => _enviar(e)),
                      ),
                  ],
                ),
              ),
            _BarraEntrada(
                controller: _texto,
                pensando: _pensando,
                onEnviar: () => _enviar()),
          ],
        ),
      ),
    );
  }
}

class _BurbujaTurno extends StatelessWidget {
  const _BurbujaTurno({required this.turno, required this.centro});
  final _Turno turno;
  final LatLng? centro;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final oscuro = Theme.of(context).brightness == Brightness.dark;
    final mio = turno.mio;
    final bg = mio
        ? (oscuro ? cs.primary : limaSuave)
        : (oscuro ? cs.surface : Colors.white);
    final fg = mio
        ? (oscuro ? cs.onPrimary : tinta)
        : (oscuro ? cs.onSurface : tinta);

    // Animación suave de entrada (fade + leve subida) al aparecer.
    return TweenAnimationBuilder<double>(
      tween: Tween(begin: 0, end: 1),
      duration: const Duration(milliseconds: 260),
      curve: Curves.easeOut,
      builder: (context, t, child) => Opacity(
        opacity: t,
        child: Transform.translate(offset: Offset(0, (1 - t) * 8), child: child),
      ),
      child: Column(
        crossAxisAlignment:
            mio ? CrossAxisAlignment.end : CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment:
                mio ? MainAxisAlignment.end : MainAxisAlignment.start,
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              if (!mio) ...[
                const _AvatarBot(),
                const SizedBox(width: 8),
              ],
              Flexible(
                child: Container(
                  constraints: BoxConstraints(
                      maxWidth: MediaQuery.of(context).size.width * 0.76),
                  margin: const EdgeInsets.only(bottom: 4),
                  padding: const EdgeInsets.fromLTRB(13, 10, 13, 10),
                  decoration: BoxDecoration(
                    color: bg,
                    borderRadius: BorderRadius.only(
                      topLeft: const Radius.circular(18),
                      topRight: const Radius.circular(18),
                      bottomLeft: Radius.circular(mio ? 18 : 5),
                      bottomRight: Radius.circular(mio ? 5 : 18),
                    ),
                    boxShadow: const [
                      BoxShadow(
                          color: Color(0x14000000),
                          blurRadius: 6,
                          offset: Offset(0, 2)),
                    ],
                    border: (!mio && !oscuro)
                        ? Border.all(color: trazo.withOpacity(0.6))
                        : null,
                  ),
                  child: Text(turno.texto,
                      style: TextStyle(
                          color: fg, fontSize: 15, height: 1.32)),
                ),
              ),
            ],
          ),
          if (turno.sugerencias.isNotEmpty) ...[
            const SizedBox(height: 6),
            for (final s in turno.sugerencias)
              Padding(
                padding: const EdgeInsets.only(left: 40, bottom: 8),
                child: _TarjetaSugerencia(sugerencia: s, centro: centro),
              ),
          ],
          const SizedBox(height: 6),
        ],
      ),
    );
  }
}

class _AvatarBot extends StatelessWidget {
  const _AvatarBot();
  @override
  Widget build(BuildContext context) {
    return Container(
      width: 32,
      height: 32,
      decoration: const BoxDecoration(color: bosque, shape: BoxShape.circle),
      child: const Icon(Icons.auto_awesome, color: lima, size: 17),
    );
  }
}

class _TarjetaSugerencia extends StatelessWidget {
  const _TarjetaSugerencia({required this.sugerencia, required this.centro});
  final SugerenciaConcierge sugerencia;
  final LatLng? centro;

  void _abrir(BuildContext context) => Navigator.of(context).push(
      MaterialPageRoute(builder: (_) => CanchaDetalleScreen(cancha: sugerencia.cancha)));

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final oscuro = Theme.of(context).brightness == Brightness.dark;
    final c = sugerencia.cancha;
    final dist = centro == null ? null : distanciaKm(centro!, c.ubicacion);
    final tieneFoto = c.fotoUrl != null && c.fotoUrl!.isNotEmpty;
    return Material(
      color: oscuro ? cs.surface : Colors.white,
      borderRadius: BorderRadius.circular(18),
      elevation: 0,
      child: InkWell(
        borderRadius: BorderRadius.circular(18),
        onTap: () => _abrir(context),
        child: Container(
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(18),
            border: Border.all(color: trazo.withOpacity(oscuro ? 0.5 : 1)),
            boxShadow: const [
              BoxShadow(
                  color: Color(0x12000000), blurRadius: 10, offset: Offset(0, 4)),
            ],
          ),
          padding: const EdgeInsets.all(10),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  // Thumbnail: foto real o círculo del deporte.
                  ClipRRect(
                    borderRadius: BorderRadius.circular(12),
                    child: SizedBox(
                      width: 54,
                      height: 54,
                      child: tieneFoto
                          ? Image.network(c.fotoUrl!, fit: BoxFit.cover,
                              errorBuilder: (_, __, ___) => _IconoDeporte(c: c))
                          : _IconoDeporte(c: c),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(c.nombre,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(
                                fontWeight: FontWeight.w800, fontSize: 15)),
                        const SizedBox(height: 5),
                        Wrap(
                          spacing: 6,
                          runSpacing: 4,
                          children: [
                            _Pill(iconoDeporte(c.deporte), c.deporte.etiqueta),
                            _Pill(Icons.place_outlined, c.distrito.etiqueta),
                            if (dist != null)
                              _Pill(Icons.directions_walk,
                                  '${dist.toStringAsFixed(1)} km'),
                          ],
                        ),
                      ],
                    ),
                  ),
                ],
              ),
              if (sugerencia.motivo.isNotEmpty) ...[
                const SizedBox(height: 8),
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text('✨ ', style: TextStyle(fontSize: 12)),
                    Expanded(
                      child: Text(sugerencia.motivo,
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                              color: cs.primary,
                              fontSize: 12.5,
                              fontWeight: FontWeight.w600)),
                    ),
                  ],
                ),
              ],
              const SizedBox(height: 10),
              Row(
                children: [
                  Text('${c.monedaSimbolo} ${c.precioHora.toStringAsFixed(2)}',
                      style: const TextStyle(
                          fontWeight: FontWeight.w900, fontSize: 16)),
                  Text('  /hora',
                      style: const TextStyle(
                          color: textoTenue, fontSize: 12)),
                  const Spacer(),
                  FilledButton(
                    style: FilledButton.styleFrom(
                      backgroundColor: lima,
                      foregroundColor: bosque,
                      padding: const EdgeInsets.symmetric(
                          horizontal: 18, vertical: 8),
                      shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(12)),
                      textStyle: const TextStyle(
                          fontWeight: FontWeight.w800, fontSize: 13.5),
                    ),
                    onPressed: () => _abrir(context),
                    child: const Text('Reservar'),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _IconoDeporte extends StatelessWidget {
  const _IconoDeporte({required this.c});
  final Cancha c;
  @override
  Widget build(BuildContext context) => Container(
        color: colorDeporte(c.deporte),
        alignment: Alignment.center,
        child: Icon(iconoDeporte(c.deporte), color: Colors.white, size: 26),
      );
}

class _Pill extends StatelessWidget {
  const _Pill(this.icono, this.texto);
  final IconData icono;
  final String texto;
  @override
  Widget build(BuildContext context) {
    final oscuro = Theme.of(context).brightness == Brightness.dark;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: oscuro
            ? Colors.white.withOpacity(0.06)
            : const Color(0xFFF1F4F0),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icono, size: 13, color: textoTenue),
          const SizedBox(width: 4),
          Text(texto,
              style: const TextStyle(
                  fontSize: 11.5,
                  color: textoTenue,
                  fontWeight: FontWeight.w600)),
        ],
      ),
    );
  }
}

class _ChipEjemplo extends StatelessWidget {
  const _ChipEjemplo({required this.texto, required this.onTap});
  final String texto;
  final VoidCallback onTap;
  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final oscuro = Theme.of(context).brightness == Brightness.dark;
    return Material(
      color: oscuro ? cs.surface : Colors.white,
      borderRadius: BorderRadius.circular(22),
      child: InkWell(
        borderRadius: BorderRadius.circular(22),
        onTap: onTap,
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 9),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(22),
            border: Border.all(color: lima.withOpacity(0.8)),
          ),
          alignment: Alignment.center,
          child: Text(texto,
              style: TextStyle(
                  fontWeight: FontWeight.w700,
                  fontSize: 13.5,
                  color: oscuro ? cs.onSurface : tinta)),
        ),
      ),
    );
  }
}

/// Indicador "escribiendo…" con tres puntitos que rebotan (estilo mensajería).
class _Escribiendo extends StatefulWidget {
  const _Escribiendo();
  @override
  State<_Escribiendo> createState() => _EscribiendoState();
}

class _EscribiendoState extends State<_Escribiendo>
    with SingleTickerProviderStateMixin {
  late final AnimationController _c = AnimationController(
      vsync: this, duration: const Duration(milliseconds: 1000))
    ..repeat();

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final oscuro = Theme.of(context).brightness == Brightness.dark;
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          const _AvatarBot(),
          const SizedBox(width: 8),
          Container(
            padding: const EdgeInsets.fromLTRB(14, 12, 14, 12),
            decoration: BoxDecoration(
              color: oscuro ? cs.surface : Colors.white,
              borderRadius: const BorderRadius.only(
                topLeft: Radius.circular(18),
                topRight: Radius.circular(18),
                bottomLeft: Radius.circular(5),
                bottomRight: Radius.circular(18),
              ),
              border: oscuro ? null : Border.all(color: trazo.withOpacity(0.6)),
              boxShadow: const [
                BoxShadow(
                    color: Color(0x14000000),
                    blurRadius: 6,
                    offset: Offset(0, 2)),
              ],
            ),
            child: AnimatedBuilder(
              animation: _c,
              builder: (context, _) => Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  for (var i = 0; i < 3; i++) _punto(i),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _punto(int i) {
    // Cada punto rebota con un desfase.
    final t = (_c.value + i * 0.2) % 1.0;
    final dy = -4 * (t < 0.5 ? (t * 2) : (2 - t * 2)); // sube y baja
    return Padding(
      padding: EdgeInsets.only(right: i == 2 ? 0 : 5),
      child: Transform.translate(
        offset: Offset(0, dy),
        child: Container(
          width: 8,
          height: 8,
          decoration:
              const BoxDecoration(color: textoTenue, shape: BoxShape.circle),
        ),
      ),
    );
  }
}

class _BarraEntrada extends StatelessWidget {
  const _BarraEntrada(
      {required this.controller,
      required this.pensando,
      required this.onEnviar});
  final TextEditingController controller;
  final bool pensando;
  final VoidCallback onEnviar;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final oscuro = Theme.of(context).brightness == Brightness.dark;
    return SafeArea(
      top: false,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(10, 8, 10, 10),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            Expanded(
              child: Container(
                decoration: BoxDecoration(
                  color: oscuro ? cs.surface : Colors.white,
                  borderRadius: BorderRadius.circular(26),
                  border: Border.all(color: trazo.withOpacity(oscuro ? 0.5 : 1)),
                  boxShadow: const [
                    BoxShadow(
                        color: Color(0x0F000000),
                        blurRadius: 8,
                        offset: Offset(0, 2)),
                  ],
                ),
                child: TextField(
                  controller: controller,
                  minLines: 1,
                  maxLines: 4,
                  textCapitalization: TextCapitalization.sentences,
                  decoration: const InputDecoration(
                    hintText: 'Escribe qué quieres jugar…',
                    border: InputBorder.none,
                    contentPadding:
                        EdgeInsets.symmetric(horizontal: 18, vertical: 12),
                  ),
                  onSubmitted: (_) => onEnviar(),
                ),
              ),
            ),
            const SizedBox(width: 8),
            GestureDetector(
              onTap: pensando ? null : onEnviar,
              child: Container(
                width: 48,
                height: 48,
                decoration: BoxDecoration(
                  color: pensando ? textoTenue.withOpacity(0.4) : lima,
                  shape: BoxShape.circle,
                  boxShadow: const [
                    BoxShadow(
                        color: Color(0x33000000),
                        blurRadius: 6,
                        offset: Offset(0, 2)),
                  ],
                ),
                child: const Icon(Icons.send_rounded, color: bosque, size: 22),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ── Detección de zona en el mensaje ─────────────────────────────────────────

/// Zonas/distritos de Lima detectables en el mensaje (display → palabras clave).
/// El display se usa para geolocalizar ("<display>, Lima, Perú").
const Map<String, List<String>> _kZonas = {
  'Surco': ['surco'],
  'La Molina': ['la molina', 'molina'],
  'San Borja': ['san borja'],
  'Miraflores': ['miraflores'],
  'San Isidro': ['san isidro'],
  'Barranco': ['barranco'],
  'Chorrillos': ['chorrillos'],
  'San Miguel': ['san miguel'],
  'Jesús María': ['jesus maria'],
  'Magdalena': ['magdalena'],
  'Pueblo Libre': ['pueblo libre'],
  'Lince': ['lince'],
  'Surquillo': ['surquillo'],
  'La Victoria': ['la victoria'],
  'Ate': ['ate ', 'santa clara'],
  'Chaclacayo': ['chaclacayo'],
  'Chosica': ['chosica', 'lurigancho'],
  'San Juan de Lurigancho': ['san juan de lurigancho', 'sjl'],
  'San Juan de Miraflores': ['san juan de miraflores', 'sjm'],
  'Los Olivos': ['los olivos'],
  'Comas': ['comas'],
  'Callao': ['callao'],
};

String _normaZona(String s) {
  const acento = 'áàäéèíìóòúùñ';
  const plano = 'aaaeeiioouun';
  final b = StringBuffer();
  for (final ch in s.toLowerCase().split('')) {
    final i = acento.indexOf(ch);
    b.write(i >= 0 ? plano[i] : ch);
  }
  return b.toString();
}

/// Nombre de la zona mencionada en [msg] (para geolocalizar), o null.
String? _zonaEn(String msg) {
  final t = '${_normaZona(msg)} '; // espacio final: ayuda a 'ate '
  for (final e in _kZonas.entries) {
    if (e.value.any((k) => t.contains(k))) return e.key;
  }
  return null;
}
