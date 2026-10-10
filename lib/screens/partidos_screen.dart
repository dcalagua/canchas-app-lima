import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart';

import '../config/pais.dart';
import '../data/partidos_repo.dart';
import '../models/academia.dart';
import '../models/club.dart';
import '../models/juego.dart';
import '../models/models.dart';
import '../models/partido.dart';
import '../services/enlaces_service.dart';
import '../services/juego_service.dart';
import '../services/location_service.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/banner_pro.dart';
import '../widgets/cargando_pichangol.dart';
import '../widgets/dialogo_pichangol.dart';
import '../widgets/responsive.dart';
import 'chat_screen.dart';
import 'convocatorias_screen.dart';
import 'login_google_sheet.dart';
import 'ranking_global_screen.dart';
import '../widgets/icono_vivo.dart';

/// JUEGA YA (antes "Partidos", el **Match** del benchmark): para quien está
/// solo y quiere jugar. Tres caminos, igual que la web `/partidos`:
///  · **Busco partido**: partidos abiertos cerca (radio 5/10/20/30 km desde mi
///    ubicación, deporte, cuándo, "De mi nivel") → Me apunto + chat del grupo.
///  · **Organizo un partido**: publico con selección (deporte, total de
///    jugadores, nivel, detalles), sin texto libre; el backend avisa por push a
///    los jugadores de la zona a los que les calza (`juego.py`).
///  · **Busco partner** (tenis/pickleball): publicaciones "Busco partner"
///    (singles/dobles/pelotear) + jugadores DISPONIBLES cerca a los que puedo
///    escribir.
/// "Avísame partidos cerca" = preferencias en el backend (`/juego/prefs`).
class PartidosScreen extends StatefulWidget {
  const PartidosScreen({super.key, this.tabInicial = 0});

  /// 0 = Busco partido · 1 = Busco partner.
  final int tabInicial;

  @override
  State<PartidosScreen> createState() => _PartidosScreenState();
}

class _PartidosScreenState extends State<PartidosScreen> {
  List<PartidoAbierto> _partidos = const [];
  bool _cargando = true;
  late int _tab = widget.tabInicial;

  // Filtros (como la web).
  Deporte? _dep;
  String _cuando = 'hoy'; // todos | hoy | manana | finde
  // Inteligente (pedido del director): arranca en mi deporte y en "Hoy"; si
  // hoy no hay nada, abre a los próximos días. Lo que el usuario toca manda.
  bool _depAuto = true;
  bool _cuandoAuto = true;
  bool _deMiNivel = false;
  int _radio = Juego.radioDefault;
  LatLng? _yo;

  PrefsJuego? _prefs;
  List<JugadorDisponible>? _disponibles;
  bool _cargandoDisp = false;

  String get _email => (appState.usuario?.email ?? '').trim().toLowerCase();

  @override
  void initState() {
    super.initState();
    _radio = appState.radioBusquedaKm.round();
    if (!Juego.radios.contains(_radio)) _radio = Juego.radioDefault;
    _dep = _depSugerido();
    _cargar();
    _ubicar();
    _cargarPrefs();
    // Datos del circuito para la tarjeta de descubrimiento (best-effort).
    appState.cargarAcademiasRemotas();
    appState.cargarRetosResultados();
    appState.cargarMiembrosPro();
  }

  Future<void> _ubicar() async {
    final u = await LocationService.ultimaConocida();
    if (u != null && mounted) {
      setState(() => _yo = u);
      _cargarDisponibles();
    }
    final a = await LocationService.ubicacionActual();
    if (a != null && mounted) {
      setState(() => _yo = a);
      _cargarDisponibles();
      if (_email.isNotEmpty && _prefs != null && (_prefs!.avisos || _prefs!.disponible)) {
        JuegoService.prefs(_email, lat: a.latitude, lng: a.longitude); // renueva vigencia
      }
    }
  }

  Future<void> _cargarPrefs() async {
    if (_email.isEmpty) return;
    final c = await JuegoService.prefsCache(_email);
    if (c != null && mounted) setState(() => _prefs = c);
    final p = await JuegoService.prefs(_email);
    if (p != null && mounted) setState(() => _prefs = p);
    if (mounted && _depAuto) {
      setState(() => _dep = _depSugerido());
      _cargarDisponibles();
    }
  }

  /// = `juego.deporte_sugerido`: partner → raqueta de mis preferencias, si no
  /// la que más jugué, si no tenis; partido → la 1.ª de mis preferencias.
  Deporte? _depSugerido() {
    Deporte? de(String n) {
      for (final d in Deporte.values) {
        if (d.name == n) return d;
      }
      return null;
    }

    final mios = [
      for (final n in _prefs?.deportes ?? const <String>[])
        if (de(n) != null && deportesActivos.contains(de(n))) de(n)!
    ];
    if (_tab == 1) {
      for (final d in mios) {
        if (Juego.deportesPartner.contains(d)) return d;
      }
      final jugados = [
        for (final n in appState.misNiveles)
          if (de(n.deporte) != null && Juego.deportesPartner.contains(de(n.deporte))) n
      ]..sort((a, b) => b.partidos.compareTo(a.partidos));
      return jugados.isNotEmpty ? de(jugados.first.deporte) : Juego.deportesPartner.first;
    }
    return mios.isNotEmpty ? mios.first : null;
  }

  /// País que se mira: el de mi ubicación real (GPS); sin GPS, el del app.
  String get _paisVista => _yo != null
      ? paisDeCoordenadas(_yo!.latitude, _yo!.longitude).iso
      : paisActual.iso;

  Future<void> _cargarDisponibles() async {
    if (_tab != 1 || _yo == null || _email.isEmpty) return;
    final dep = (_dep != null && Juego.deportesPartner.contains(_dep))
        ? _dep!
        : Juego.deportesPartner.first;
    setState(() => _cargandoDisp = true);
    final l = await JuegoService.disponibles(
        _email, dep.name, _yo!.latitude, _yo!.longitude, _radio);
    if (!mounted) return;
    setState(() {
      _disponibles = l ?? const [];
      _cargandoDisp = false;
    });
  }

  Future<void> _cargar() async {
    final lista = await PartidosRepo.abiertos();
    if (!mounted) return;
    // El país se filtra al mostrar (`_paisVista`: el de mi GPS).
    setState(() {
      _partidos = lista;
      _cargando = false;
    });
  }

  double? _kmA(PartidoAbierto p) {
    final u = p.ubicacion;
    if (_yo == null || u == null) return null;
    return Juego.km(_yo!.latitude, _yo!.longitude, u.latitude, u.longitude);
  }

  bool _cuandoOk(String fecha, String cuando) {
    if (cuando == 'todos') return true;
    final d = DateTime.tryParse(fecha);
    if (d == null) return true;
    final n = DateTime.now();
    final hoy = DateTime(n.year, n.month, n.day);
    final dif = DateTime(d.year, d.month, d.day).difference(hoy).inDays;
    if (dif < 0) return false;
    if (cuando == 'hoy') return dif == 0;
    if (cuando == 'manana') return dif == 1;
    // Este finde: el sábado y domingo más próximos.
    final hastaDom = 7 - hoy.weekday; // domingo = 7
    return dif >= 0 &&
        dif <= hastaDom &&
        (d.weekday == DateTime.saturday || d.weekday == DateTime.sunday);
  }

  /// (lista, true si "Hoy" no tenía nada y se abrió a los próximos días).
  (List<PartidoAbierto>, bool) get _visibles {
    final v = _filtrar(_cuando);
    if (v.isEmpty && _cuandoAuto && _cuando == 'hoy') {
      final w = _filtrar('todos');
      if (w.isNotEmpty) return (w, true);
    }
    return (v, false);
  }

  bool _noPasado(String fecha) {
    final d = DateTime.tryParse(fecha);
    if (d == null) return true;
    final n = DateTime.now();
    return !DateTime(d.year, d.month, d.day).isBefore(DateTime(n.year, n.month, n.day));
  }

  bool _enPaisVista(PartidoAbierto p) {
    final u = p.ubicacion;
    return u == null || paisDeCoordenadas(u.latitude, u.longitude).iso == _paisVista;
  }

  List<PartidoAbierto> _filtrar(String cuando) => [
        for (final p in _partidos)
          if (p.esPartner == (_tab == 1) &&
              _noPasado(p.fecha) &&
              _enPaisVista(p) &&
              (_dep == null || p.deporte == _dep) &&
              _cuandoOk(p.fecha, cuando) &&
              (!_deMiNivel ||
                  p.nivel.isEmpty ||
                  p.nivel ==
                      Juego.nivelBanda(appState.miNivelDe(p.deporte.name)?.nivel)) &&
              (() {
                final k = _kmA(p);
                return k == null || k <= _radio;
              })())
            p
      ];

  Future<void> _crear({required bool partner}) async {
    if (!await LoginGoogleSheet.mostrar(context,
        motivo: partner ? 'buscar partner' : 'publicar tu partido')) {
      return;
    }
    if (!mounted) return;
    final creado = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Theme.of(context).colorScheme.surface,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      builder: (_) => _CrearPartidoSheet(
          partner: partner,
          yo: _yo,
          deporteInicial: _dep),
    );
    if (creado == true) {
      _snack(partner
          ? '¡Publicado! Te avisamos cuando alguien quiera jugar contigo.'
          : '¡Partido publicado! Avisamos a los jugadores de la zona.');
      _cargar();
    }
  }

  Future<void> _abrirPrefs() async {
    if (!await LoginGoogleSheet.mostrar(context,
        motivo: 'recibir avisos de partidos cerca')) {
      return;
    }
    if (!mounted) return;
    final p = await showModalBottomSheet<PrefsJuego>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Theme.of(context).colorScheme.surface,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      builder: (_) => _PrefsSheet(
          inicial: _prefs ?? const PrefsJuego(),
          yo: _yo,
          partner: _tab == 1),
    );
    if (p != null && mounted) {
      setState(() => _prefs = p);
      _snack('Listo, guardado.');
      _cargarDisponibles();
    }
  }

  Future<void> _apuntarse(PartidoAbierto p) async {
    if (!await LoginGoogleSheet.mostrar(context,
        motivo: 'apuntarte al partido')) {
      return;
    }
    if (!mounted) return;
    final u = appState.usuario!;
    final res = await PartidosRepo.apuntarse(p.id, u.email, u.nombre, p.cupos);
    if (!mounted) return;
    _snack(switch (res) {
      'ok' => '¡Te apuntaste! Coordinen por el chat del partido.',
      'lleno' => '⛔ El partido ya se llenó (otro jugador tomó el último '
          'cupo). Pídele al creador que amplíe los cupos o busca otro.',
      _ => 'No se pudo apuntar. Revisa tu conexión.',
    });
    _cargar(); // refresca el conteo real aunque no haya entrado
  }

  Future<void> _bajarse(PartidoAbierto p) async {
    final u = appState.usuario;
    if (u == null) return;
    final ok = await confirmarPichangol(context,
        titulo: '¿Salir del partido?',
        mensaje: 'Dejas tu cupo libre para otro jugador.',
        textoConfirmar: 'Salir',
        destructivo: true);
    if (!ok || !mounted) return;
    final hecho = await PartidosRepo.bajarse(p.id, u.email);
    if (!mounted) return;
    _snack(hecho ? 'Te bajaste del partido.' : 'No se pudo.');
    if (hecho) _cargar();
  }

  Future<void> _ampliarCupo(PartidoAbierto p) async {
    final nuevo = (p.cupos + 1).clamp(2, 40);
    final ok = await PartidosRepo.cambiarCupos(p.id, nuevo);
    if (!mounted) return;
    _snack(ok
        ? 'Cupo ampliado a $nuevo jugadores.'
        : 'No se pudo ampliar el cupo.');
    if (ok) _cargar();
  }

  Future<void> _eliminar(PartidoAbierto p) async {
    final si = await confirmarPichangol(context,
        titulo: '¿Eliminar el partido?',
        mensaje: 'Se borra el partido y su chat de coordinación para todos.',
        textoConfirmar: 'Eliminar',
        destructivo: true);
    if (!si || !mounted) return;
    final ok = await PartidosRepo.eliminar(p.id);
    if (!mounted) return;
    _snack(ok ? 'Partido eliminado.' : 'No se pudo eliminar.');
    if (ok) _cargar();
  }

  void _coordinar(PartidoAbierto p) {
    Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => ChatScreen(
        academiaId: '',
        cuentaEmail: '',
        titulo: p.titulo,
        soyProfe: false,
        tipo: 'grupo',
        refId: p.id,
      ),
    ));
  }

  void _escribir(JugadorDisponible j) {
    Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => ChatScreen(
        academiaId: '',
        cuentaEmail: j.email,
        titulo: j.nombre.isNotEmpty ? j.nombre : 'Jugador',
        soyProfe: false,
        tipo: 'directo',
      ),
    ));
  }

  /// Pichangas de MI club: el club sale de mis canchas REALES (dueño), como la
  /// web `/pichangas`. Un local → directo; varios → elijo con chips; ninguno
  /// (jugador) → las pichangas de todos los clubes para anotarme.
  Future<void> _pichangasDeClub() async {
    final clubs = appState.misClubesPropios;
    String clubId = '';
    String clubNombre = 'Todos los clubes';
    if (clubs.length == 1) {
      clubId = clubs.keys.first;
      clubNombre = clubs.values.first;
    } else if (clubs.length > 1) {
      final elegido = await showModalBottomSheet<String>(
        context: context,
        showDragHandle: true,
        builder: (ctx) => SafeArea(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(20, 0, 20, 20),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text('¿De qué local?',
                    style: TextStyle(fontWeight: FontWeight.w800, fontSize: 17)),
                const SizedBox(height: 4),
                const Text('Elige el local cuyas pichangas quieres ver u organizar.',
                    style: TextStyle(color: textoTenue, fontSize: 13)),
                const SizedBox(height: 14),
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    for (final e in clubs.entries)
                      ActionChip(
                        avatar: const IconoVivo(Icons.storefront, size: 18),
                        label: Text(e.value),
                        backgroundColor: Colors.white,
                        side: const BorderSide(color: Color(0xFFE4E4E4)),
                        shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(999)),
                        onPressed: () => Navigator.of(ctx).pop(e.key),
                      ),
                    ActionChip(
                      avatar: const IconoVivo(Icons.public, size: 18),
                      label: const Text('Todos los clubes'),
                      backgroundColor: Colors.white,
                      side: const BorderSide(color: Color(0xFFE4E4E4)),
                      shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(999)),
                      onPressed: () => Navigator.of(ctx).pop(''),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
      );
      if (elegido == null || !mounted) return;
      clubId = elegido;
      if (elegido.isNotEmpty) clubNombre = clubs[elegido] ?? clubNombre;
    }
    if (!mounted) return;
    Navigator.of(context).push(MaterialPageRoute(
      builder: (_) =>
          ConvocatoriasScreen(clubId: clubId, clubNombre: clubNombre),
    ));
  }

  void _snack(String m) => ScaffoldMessenger.of(context)
      .showSnackBar(SnackBar(content: Text(m)));

  void _cambiarTab(int t) {
    if (t == _tab) return;
    setState(() {
      _tab = t;
      if (_depAuto ||
          (t == 1 && _dep != null && !Juego.deportesPartner.contains(_dep))) {
        _depAuto = true;
        _dep = _depSugerido();
      }
      _cuando = 'hoy';
      _cuandoAuto = true;
    });
    _cargarDisponibles();
  }

  String _textoPrefs() {
    final p = _prefs;
    if (p == null || (!p.avisos && !p.disponible)) {
      return 'Te avisamos cuando alguien publique un partido cerca de ti, '
          'de tu deporte y a tu hora.';
    }
    final partes = <String>[
      if (p.avisos) '🔔 Avisos encendidos',
      if (p.disponible) '🙋 Apareces como disponible',
    ];
    final deps = [
      for (final d in p.deportes)
        Deporte.values
            .firstWhere((x) => x.name == d, orElse: () => Deporte.futbol)
            .etiqueta
    ].join(', ');
    return '${partes.join(' · ')}${deps.isNotEmpty ? ' · $deps' : ''} · a ${p.radioKm} km';
  }

  Widget _chip(String texto, bool sel, VoidCallback onTap, {String? emoji}) {
    return Padding(
      padding: const EdgeInsets.only(right: 8),
      child: ChoiceChip(
        label: Text(emoji != null ? '$emoji $texto' : texto),
        selected: sel,
        showCheckmark: false,
        backgroundColor: Colors.white,
        selectedColor: limaSuave,
        side: BorderSide(color: sel ? lima : const Color(0xFFE4E4E4)),
        shape:
            RoundedRectangleBorder(borderRadius: BorderRadius.circular(999)),
        labelStyle: TextStyle(
            color: sel ? bosque : const Color(0xFF222222),
            fontWeight: FontWeight.w600),
        onSelected: (_) => onTap(),
      ),
    );
  }

  Widget _tile(String emoji, String titulo, String sub, bool sel,
      VoidCallback onTap) {
    return Expanded(
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(16),
        child: Container(
          padding: const EdgeInsets.all(10),
          decoration: BoxDecoration(
            color: sel ? Colors.white : Colors.white.withOpacity(0.16),
            borderRadius: BorderRadius.circular(16),
            border: Border.all(color: Colors.white.withOpacity(0.3)),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(emoji, style: const TextStyle(fontSize: 22)),
              const SizedBox(height: 4),
              Text(titulo,
                  style: TextStyle(
                      color: sel ? const Color(0xFF0A1B3D) : Colors.white,
                      fontWeight: FontWeight.w800,
                      fontSize: 13)),
              Text(sub,
                  maxLines: 2,
                  style: TextStyle(
                      color: sel ? textoTenue : Colors.white.withOpacity(0.9),
                      fontSize: 11)),
            ],
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final partner = _tab == 1;
    final (visibles, abrioDias) = _visibles;
    final cuandoVisto = abrioDias ? 'todos' : _cuando;
    final deps = partner ? Juego.deportesPartner : deportesActivos;
    final lado = ladoTablet(context, 16, 760);
    return Scaffold(
      floatingActionButton: FloatingActionButton.extended(
        backgroundColor: lima,
        foregroundColor: Colors.white,
        onPressed: () => _crear(partner: partner),
        icon: const Icon(Icons.add),
        label: Text(partner ? 'Busco partner' : 'Organizar partido'),
      ),
      body: SafeArea(
        child: RefreshIndicator(
          onRefresh: () async {
            await Future.wait([_cargar(), _cargarPrefs()]);
            await _cargarDisponibles();
          },
          child: ListView(
            padding: const EdgeInsets.only(bottom: 100),
            children: [
              // Cabecera verde con los tres caminos.
              Container(
                width: double.infinity,
                padding: EdgeInsets.fromLTRB(lado + 4, 18, lado, 18),
                decoration: const BoxDecoration(
                  gradient: LinearGradient(
                    begin: Alignment.topLeft,
                    end: Alignment.bottomRight,
                    colors: [lima, teal],
                  ),
                  borderRadius:
                      BorderRadius.vertical(bottom: Radius.circular(22)),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('Juega ya',
                        style: t.headlineSmall?.copyWith(
                            color: Colors.white, fontWeight: FontWeight.w800)),
                    const SizedBox(height: 2),
                    Text(
                        'Encuentra un partido, organiza el tuyo o busca con '
                        'quién jugar.',
                        style: t.bodyMedium
                            ?.copyWith(color: Colors.white.withOpacity(0.92))),
                    const SizedBox(height: 12),
                    Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        _tile('⚽', 'Busco partido', 'Únete a uno cerca',
                            !partner, () => _cambiarTab(0)),
                        const SizedBox(width: 8),
                        _tile('📣', 'Organizo', 'Publica y completa tu equipo',
                            false, () => _crear(partner: false)),
                        const SizedBox(width: 8),
                        _tile('🎾', 'Busco partner', 'Tenis y pickleball',
                            partner, () => _cambiarTab(1)),
                      ],
                    ),
                    const SizedBox(height: 12),
                    InkWell(
                      onTap: _pichangasDeClub,
                      borderRadius: BorderRadius.circular(10),
                      child: Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 12, vertical: 8),
                        decoration: BoxDecoration(
                          color: Colors.white.withOpacity(0.18),
                          borderRadius: BorderRadius.circular(10),
                        ),
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            const IconoVivo(Icons.event_available,
                                color: Colors.white, size: 18),
                            const SizedBox(width: 8),
                            Text('Pichangas de mi club',
                                style: t.bodySmall?.copyWith(
                                    color: Colors.white,
                                    fontWeight: FontWeight.w700)),
                            const SizedBox(width: 4),
                            const Icon(Icons.chevron_right,
                                color: Colors.white, size: 18),
                          ],
                        ),
                      ),
                    ),
                  ],
                ),
              ),
              Padding(
                padding: EdgeInsets.fromLTRB(lado, 14, lado, 0),
                child: _AvisosCard(texto: _textoPrefs(), onTap: _abrirPrefs),
              ),
              Padding(
                padding: EdgeInsets.fromLTRB(lado, 12, lado, 0),
                child: Row(
                  children: [
                    const IconoVivo(Icons.place_outlined, size: 16),
                    const SizedBox(width: 6),
                    Expanded(
                      child: Text(
                          _yo == null
                              ? 'Sin tu ubicación: ves todo el país'
                              : 'Cerca de ti · hasta',
                          style: TextStyle(
                              color: textoTenueDe(context), fontSize: 13)),
                    ),
                    if (_yo == null)
                      TextButton(
                          onPressed: _ubicar,
                          child: const Text('Usar mi ubicación'))
                    else
                      DropdownButton<int>(
                        value: _radio,
                        underline: const SizedBox.shrink(),
                        borderRadius: BorderRadius.circular(14),
                        items: [
                          for (final r in Juego.radios)
                            DropdownMenuItem(value: r, child: Text('$r km')),
                        ],
                        onChanged: (v) {
                          if (v == null) return;
                          setState(() => _radio = v);
                          _cargarDisponibles();
                        },
                      ),
                  ],
                ),
              ),
              SingleChildScrollView(
                scrollDirection: Axis.horizontal,
                padding: EdgeInsets.fromLTRB(lado, 6, lado, 0),
                child: Row(children: [
                  _chip('Todos', _dep == null, () {
                    setState(() {
                      _dep = null;
                      _depAuto = false;
                    });
                    _cargarDisponibles();
                  }),
                  for (final d in deps)
                    _chip(d.etiqueta, _dep == d, () {
                      setState(() {
                        _dep = d;
                        _depAuto = false;
                      });
                      _cargarDisponibles();
                    }),
                ]),
              ),
              SingleChildScrollView(
                scrollDirection: Axis.horizontal,
                padding: EdgeInsets.fromLTRB(lado, 4, lado, 0),
                child: Row(children: [
                  for (final c in const [
                    ('todos', 'Cuando sea'),
                    ('hoy', 'Hoy'),
                    ('manana', 'Mañana'),
                    ('finde', 'Este finde'),
                  ])
                    _chip(c.$2, cuandoVisto == c.$1, () => setState(() {
                          _cuando = c.$1;
                          _cuandoAuto = false;
                        })),
                  _chip('De mi nivel', _deMiNivel,
                      () => setState(() => _deMiNivel = !_deMiNivel),
                      emoji: '📊'),
                ]),
              ),
              if (!partner) ...[
                const _CircuitoPreview(),
                // Hazte Pro visible (solo si NO es Pro): el circuito y los
                // retos son donde la insignia PRO más luce.
                const BannerPro(
                    margen: EdgeInsets.fromLTRB(16, 6, 16, 0),
                    mensaje: 'Luce la insignia PRO en el ranking y los retos.'),
              ],
              Padding(
                padding: EdgeInsets.fromLTRB(lado, 16, lado, 8),
                child: Text(partner ? '🎾 Buscan partner' : '⚽ Partidos abiertos',
                    style: t.titleMedium?.copyWith(fontWeight: FontWeight.w800)),
              ),
              if (abrioDias && !_cargando)
                Padding(
                  padding: EdgeInsets.fromLTRB(lado, 0, lado, 10),
                  child: Container(
                    padding: const EdgeInsets.all(10),
                    decoration: BoxDecoration(
                        color: const Color(0xFFFFF6E0),
                        borderRadius: BorderRadius.circular(12)),
                    child: const Text(
                        'Hoy no hay nada cerca: te mostramos los próximos días.',
                        style: TextStyle(color: Color(0xFF7A5B00), fontSize: 13)),
                  ),
                ),
              if (_cargando)
                const Padding(
                    padding: EdgeInsets.symmetric(vertical: 40),
                    child: CargandoPichangol())
              else if (visibles.isEmpty)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 24),
                  child: _Vacio(partner: partner),
                )
              else
                for (final p in visibles)
                  Padding(
                    padding: EdgeInsets.symmetric(horizontal: lado),
                    child: _PartidoCard(
                      partido: p,
                      km: _kmA(p),
                      onApuntarse: () => _apuntarse(p),
                      onBajarse: () => _bajarse(p),
                      onCoordinar: () => _coordinar(p),
                      onEliminar: () => _eliminar(p),
                      onAmpliarCupo: () => _ampliarCupo(p),
                    ),
                  ),
              if (partner)
                Padding(
                  padding: EdgeInsets.fromLTRB(lado, 10, lado, 0),
                  child: _Disponibles(
                    yo: _yo,
                    cargando: _cargandoDisp,
                    jugadores: _disponibles,
                    radio: _radio,
                    onEscribir: _escribir,
                    onUbicar: _ubicar,
                    onDisponible: _abrirPrefs,
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Tarjeta "Avísame partidos cerca" (abre las preferencias).
class _AvisosCard extends StatelessWidget {
  const _AvisosCard({required this.texto, required this.onTap});
  final String texto;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.fromLTRB(14, 12, 10, 12),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: trazo),
        boxShadow: const [
          BoxShadow(color: Color(0x0F000000), blurRadius: 12, offset: Offset(0, 4)),
        ],
      ),
      child: Row(
        children: [
          const IconoVivo(Icons.notifications_active_outlined, size: 26),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text('Avísame partidos cerca',
                    style: TextStyle(fontWeight: FontWeight.w800, fontSize: 14.5)),
                const SizedBox(height: 2),
                Text(texto,
                    style: TextStyle(color: textoTenueDe(context), fontSize: 12.5)),
              ],
            ),
          ),
          const SizedBox(width: 8),
          OutlinedButton(onPressed: onTap, child: const Text('Configurar')),
        ],
      ),
    );
  }
}

/// "Jugadores disponibles cerca" (pestaña Busco partner).
class _Disponibles extends StatelessWidget {
  const _Disponibles({
    required this.yo,
    required this.cargando,
    required this.jugadores,
    required this.radio,
    required this.onEscribir,
    required this.onUbicar,
    required this.onDisponible,
  });
  final LatLng? yo;
  final bool cargando;
  final List<JugadorDisponible>? jugadores;
  final int radio;
  final void Function(JugadorDisponible) onEscribir;
  final VoidCallback onUbicar;
  final VoidCallback onDisponible;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    Widget cuerpo;
    if (yo == null) {
      cuerpo = Column(children: [
        const Text('Activa tu ubicación para ver quién quiere jugar cerca de ti.',
            textAlign: TextAlign.center, style: TextStyle(color: textoTenue)),
        TextButton(onPressed: onUbicar, child: const Text('Usar mi ubicación')),
      ]);
    } else if (cargando && jugadores == null) {
      cuerpo = const Padding(
          padding: EdgeInsets.symmetric(vertical: 20), child: CargandoPichangol());
    } else if ((jugadores ?? const []).isEmpty) {
      cuerpo = Column(children: [
        Text('Nadie disponible a $radio km por ahora',
            style: const TextStyle(fontWeight: FontWeight.w800)),
        const SizedBox(height: 4),
        const Text(
            'Márcate como disponible para que otros te encuentren, o publica '
            '"Busco partner".',
            textAlign: TextAlign.center,
            style: TextStyle(color: textoTenue)),
        const SizedBox(height: 10),
        OutlinedButton(
            onPressed: onDisponible,
            child: const Text('🙋 Aparecer como disponible')),
      ]);
    } else {
      cuerpo = Column(children: [
        for (final j in jugadores!)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 8),
            child: Row(
              children: [
                CircleAvatar(
                  radius: 23,
                  backgroundColor: const Color(0xFF0E8F67),
                  backgroundImage: j.foto.isNotEmpty
                      ? CachedNetworkImageProvider(j.foto)
                      : null,
                  child: j.foto.isEmpty
                      ? Text(
                          (j.nombre.isNotEmpty ? j.nombre[0] : '?').toUpperCase(),
                          style: const TextStyle(
                              color: Colors.white, fontWeight: FontWeight.w800))
                      : null,
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(j.nombre,
                          style: const TextStyle(fontWeight: FontWeight.w800)),
                      Text(
                          [
                            Juego.etiquetaNivel(j.banda) +
                                (j.nivel != null
                                    ? ' · ${j.nivel!.toStringAsFixed(1)}'
                                    : ''),
                            'a ${Juego.fmtKm(j.km)} km',
                            if (j.franjas.isNotEmpty)
                              j.franjas.map(Juego.etiquetaFranja).join(' · '),
                          ].join(' · '),
                          style: TextStyle(
                              color: textoTenueDe(context), fontSize: 12.5)),
                    ],
                  ),
                ),
                FilledButton(
                  style: FilledButton.styleFrom(
                      backgroundColor: lima, foregroundColor: Colors.white),
                  onPressed: () => onEscribir(j),
                  child: const Text('Escribir'),
                ),
              ],
            ),
          ),
      ]);
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('🙋 Jugadores disponibles cerca',
            style: t.titleMedium?.copyWith(fontWeight: FontWeight.w800)),
        const SizedBox(height: 8),
        Container(
          width: double.infinity,
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            color: Theme.of(context).colorScheme.surface,
            borderRadius: BorderRadius.circular(18),
            border: Border.all(color: trazo),
          ),
          child: cuerpo,
        ),
      ],
    );
  }
}

class _CircuitoPreview extends StatelessWidget {
  const _CircuitoPreview();

  void _abrir(BuildContext context) => Navigator.of(context).push(
      MaterialPageRoute(builder: (_) => const RankingGlobalScreen()));

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: appState,
      builder: (context, _) {
        // El circuito es capa de TENIS: no ensuciar Partidos (matchmaking de
        // todos los deportes) si no hay circuito de raqueta vivo ni el usuario
        // se unió.
        if (!appState.hayCircuitoTenis) return const SizedBox.shrink();
        final deportes =
            appState.deportesConRanking.where((d) => d.esRaqueta).toList();
        final dep = deportes.isNotEmpty ? deportes.first : null;
        final top = dep == null
            ? const <RankingGlobalFila>[]
            : appState.rankingGlobal(deporte: dep).take(3).toList();
        return Padding(
          padding: const EdgeInsets.fromLTRB(16, 14, 16, 2),
          child: Material(
            color: Theme.of(context).colorScheme.surface,
            borderRadius: BorderRadius.circular(18),
            child: InkWell(
              borderRadius: BorderRadius.circular(18),
              onTap: () => _abrir(context),
              child: Container(
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(18),
                  border: Border.all(color: trazo),
                ),
                padding: const EdgeInsets.fromLTRB(16, 14, 12, 14),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Container(
                          width: 38,
                          height: 38,
                          decoration: BoxDecoration(
                              color: limaSuave,
                              borderRadius: BorderRadius.circular(11)),
                          child: const IconoVivo(Icons.emoji_events,
                              color: bosque, size: 21),
                        ),
                        const SizedBox(width: 12),
                        const Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text('Circuito Pichangol',
                                  style: TextStyle(
                                      fontWeight: FontWeight.w800,
                                      fontSize: 15.5)),
                              Text('Ranking de tu ciudad · rétalos y sube',
                                  style: TextStyle(
                                      color: textoTenue, fontSize: 12.5)),
                            ],
                          ),
                        ),
                        const Icon(Icons.chevron_right, color: textoTenue),
                      ],
                    ),
                    if (top.isEmpty) ...[
                      const SizedBox(height: 10),
                      Text(
                          '¡Arranca el circuito! Reta a un jugador y aparece en '
                          'el ranking de tu ciudad.',
                          style: TextStyle(
                              color: textoTenueDe(context),
                              fontSize: 12.5,
                              height: 1.3)),
                    ] else ...[
                      const SizedBox(height: 8),
                      const _MiniHeaderRanking(),
                      const SizedBox(height: 2),
                      for (var i = 0; i < top.length; i++)
                        _MiniFila(
                            posicion: i + 1,
                            f: top[i],
                            esPro: appState.esProEmail(top[i].emailIdentidad)),
                    ],
                  ],
                ),
              ),
            ),
          ),
        );
      },
    );
  }
}

// Anchos de las columnas numéricas del mini-ranking (comunes al encabezado y a
// las filas → alineación perfecta entre sí y entre filas).
const double _wPj = 30, _wG = 24, _wP = 24, _wPts = 40;

/// Encabezado del mini-ranking: rótulos PJ · G · P · Pts alineados con las
/// columnas de cada fila.
class _MiniHeaderRanking extends StatelessWidget {
  const _MiniHeaderRanking();
  Widget _h(String t, double w, {bool fuerte = false}) => SizedBox(
        width: w,
        child: Text(t,
            textAlign: TextAlign.right,
            style: TextStyle(
                color: textoTenue,
                fontSize: 10.5,
                fontWeight: fuerte ? FontWeight.w900 : FontWeight.w700)),
      );
  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 2),
      child: Row(
        children: [
          const SizedBox(width: 30), // medalla + gap
          const Expanded(child: SizedBox()),
          _h('PJ', _wPj),
          _h('G', _wG),
          _h('P', _wP),
          _h('Pts', _wPts, fuerte: true),
        ],
      ),
    );
  }
}

/// Fila compacta del top-3 en la tarjeta del circuito: medalla + nombre + tabla
/// PJ · G · P · Pts (columnas de ancho fijo, alineadas).
class _MiniFila extends StatelessWidget {
  const _MiniFila(
      {required this.posicion, required this.f, required this.esPro});
  final int posicion;
  final RankingGlobalFila f;
  final bool esPro;

  Widget _num(String v, double w, Color c,
          {bool fuerte = false, double size = 12.5}) =>
      SizedBox(
        width: w,
        child: Text(v,
            textAlign: TextAlign.right,
            style: TextStyle(
                color: c,
                fontSize: size,
                fontWeight: fuerte ? FontWeight.w900 : FontWeight.w700)),
      );

  @override
  Widget build(BuildContext context) {
    final medalla = switch (posicion) {
      1 => '🥇',
      2 => '🥈',
      3 => '🥉',
      _ => '$posicion',
    };
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Row(
        children: [
          SizedBox(
              width: 22,
              child: Text(medalla,
                  style: const TextStyle(fontSize: 15),
                  textAlign: TextAlign.center)),
          const SizedBox(width: 8),
          Expanded(
            child: Row(
              children: [
                Flexible(
                  child: Text(f.nombre,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                          fontWeight: FontWeight.w600, fontSize: 13.5)),
                ),
                if (esPro) ...[
                  const SizedBox(width: 6),
                  Container(
                    padding:
                        const EdgeInsets.symmetric(horizontal: 5, vertical: 1),
                    decoration: BoxDecoration(
                        color: bosque, borderRadius: BorderRadius.circular(5)),
                    child: const Text('PRO',
                        style: TextStyle(
                            color: Colors.white,
                            fontWeight: FontWeight.w900,
                            fontSize: 8.5)),
                  ),
                ],
              ],
            ),
          ),
          // Tabla: partidos jugados, ganados (verde), perdidos (rojo) y puntos.
          _num('${f.pj}', _wPj, textoTenue),
          _num('${f.pg}', _wG, lima),
          _num('${f.pp}', _wP, clayOscuro),
          _num('${f.puntos}', _wPts, bosque, fuerte: true, size: 14),
        ],
      ),
    );
  }
}

class _Vacio extends StatelessWidget {
  const _Vacio({this.partner = false});
  final bool partner;
  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 32),
      child: Column(
        children: [
          IconoVivo(partner ? Icons.sports_tennis : Icons.sports_soccer,
              size: 56, color: lima.withOpacity(0.6)),
          const SizedBox(height: 14),
          Text(
              partner
                  ? 'Nadie busca partner por ahora'
                  : 'No hay partidos abiertos cerca',
              textAlign: TextAlign.center,
              style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 17)),
          const SizedBox(height: 6),
          Text(
              partner
                  ? 'Publica "Busco partner" o escríbele a un jugador '
                      'disponible de abajo.'
                  : '¿Te falta gente para jugar? Organiza tu partido y deja '
                      'que otros se apunten; avisamos a los de la zona.',
              textAlign: TextAlign.center,
              style: TextStyle(color: textoTenueDe(context), height: 1.35)),
        ],
      ),
    );
  }
}

/// Formatea 'YYYY-MM-DD' + 'HH:mm' a algo legible: "vie 18 jul · 20:00".
String _fechaLegible(String fecha, String hora) {
  const dias = ['lun', 'mar', 'mié', 'jue', 'vie', 'sáb', 'dom'];
  const meses = [
    'ene', 'feb', 'mar', 'abr', 'may', 'jun',
    'jul', 'ago', 'set', 'oct', 'nov', 'dic'
  ];
  final d = DateTime.tryParse(fecha);
  final base = d != null
      ? '${dias[d.weekday - 1]} ${d.day} ${meses[d.month - 1]}'
      : fecha;
  return hora.isNotEmpty ? '$base · $hora' : base;
}

/// "Fut 7", "Singles"… (espejo de `_nombre_modalidad` de la web).
String _nombreModalidad(PartidoAbierto p) {
  if (p.esPartner) return Juego.modalidad(p.modalidad)?.$2 ?? 'Partner';
  for (final x in _presetsDe(p.deporte)) {
    if (x.$2 == p.cupos) return x.$1;
  }
  return p.deporte.etiqueta;
}

/// Atajos de "jugadores en total" según el deporte (etiqueta, total). El
/// total incluye al creador. ESPEJO de `PRESETS` en `jugador_partidos.py`.
List<(String, int)> _presetsDe(Deporte d) => switch (d) {
      Deporte.tenis || Deporte.padel || Deporte.pickleball =>
        const [('Singles', 2), ('Dobles', 4)],
      Deporte.futbol => const [
          ('Fut 5', 10),
          ('Fut 6', 12),
          ('Fut 7', 14),
          ('Fut 8', 16),
          ('Fut 11', 22),
        ],
      Deporte.voley => const [('4 vs 4', 8), ('6 vs 6', 12)],
      Deporte.basquet => const [('3 vs 3', 6), ('5 vs 5', 10)],
      Deporte.natacion => const [], // sin modalidades de partido
    };

class _PartidoCard extends StatelessWidget {
  const _PartidoCard({
    required this.partido,
    required this.km,
    required this.onApuntarse,
    required this.onBajarse,
    required this.onCoordinar,
    required this.onEliminar,
    required this.onAmpliarCupo,
  });
  final PartidoAbierto partido;
  final double? km;
  final VoidCallback onApuntarse;
  final VoidCallback onBajarse;
  final VoidCallback onCoordinar;
  final VoidCallback onEliminar;
  final VoidCallback onAmpliarCupo;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final cs = Theme.of(context).colorScheme;
    final email = appState.usuario?.email;
    final apuntado = partido.apuntado(email);
    final esCreador = partido.esCreador(email);
    final p = partido;
    final chipTexto = p.lleno
        ? 'Completo'
        : p.esPartner && p.faltan == 1
            ? 'Busca partner'
            : 'Faltan ${p.faltan}';
    return Container(
      margin: const EdgeInsets.only(bottom: 14),
      decoration: BoxDecoration(
        color: cs.surface,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: trazo),
        boxShadow: const [
          BoxShadow(color: Color(0x14000000), blurRadius: 14, offset: Offset(0, 5)),
        ],
      ),
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              CircleAvatar(
                radius: 22,
                backgroundColor: colorDeporte(p.deporte),
                child: Icon(iconoDeporte(p.deporte), color: Colors.white),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(p.titulo,
                        style: t.titleMedium
                            ?.copyWith(fontWeight: FontWeight.w800)),
                    const SizedBox(height: 2),
                    Text(_fechaLegible(p.fecha, p.hora),
                        style: t.bodySmall
                            ?.copyWith(color: textoTenueDe(context))),
                  ],
                ),
              ),
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                decoration: BoxDecoration(
                  color: p.lleno
                      ? const Color(0xFFEBEBEB)
                      : p.esPartner
                          ? const Color(0xFFEAF2FB)
                          : limaSuave,
                  borderRadius: BorderRadius.circular(999),
                ),
                child: Text(chipTexto,
                    style: TextStyle(
                        color: p.lleno
                            ? textoTenue
                            : p.esPartner
                                ? const Color(0xFF1F5FA8)
                                : bosque,
                        fontWeight: FontWeight.w800,
                        fontSize: 12)),
              ),
            ],
          ),
          const SizedBox(height: 10),
          if (p.sedeNombre.isNotEmpty)
            _Linea(
                Icons.place_outlined,
                km != null
                    ? '${p.sedeNombre} · a ${Juego.fmtKm(km!)} km'
                    : p.sedeNombre),
          _Linea(
              Icons.groups_outlined,
              '${p.inscritos} de ${p.cupos} jugadores · ${_nombreModalidad(p)}'
              '${p.esPartner ? '' : ' · ${p.deporte.etiqueta}'}'),
          if (p.nivel.isNotEmpty)
            _Linea(Icons.equalizer, 'Nivel ${Juego.etiquetaNivel(p.nivel)}'),
          if (p.etiquetas.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(top: 4, bottom: 4),
              child: Wrap(
                spacing: 6,
                runSpacing: 6,
                children: [
                  for (final k in p.etiquetas)
                    if (Juego.etiquetas[k] != null)
                      Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 10, vertical: 4),
                        decoration: BoxDecoration(
                          color: const Color(0xFFF4F7FA),
                          borderRadius: BorderRadius.circular(999),
                          border: Border.all(color: const Color(0xFFEBEBEB)),
                        ),
                        child: Text(
                            '${Juego.etiquetas[k]!.$1} ${Juego.etiquetas[k]!.$2}',
                            style: const TextStyle(fontSize: 12)),
                      ),
                ],
              ),
            )
          else if (p.nota.isNotEmpty)
            _Linea(Icons.sticky_note_2_outlined, p.nota),
          const SizedBox(height: 12),
          Row(
            children: [
              if (apuntado) ...[
                Expanded(
                  child: FilledButton.icon(
                    style: FilledButton.styleFrom(
                        backgroundColor: lima, foregroundColor: Colors.white),
                    onPressed: onCoordinar,
                    icon: const Icon(Icons.chat_bubble_outline, size: 18),
                    label: const Text('Coordinar'),
                  ),
                ),
                const SizedBox(width: 8),
                if (esCreador) ...[
                  // El creador puede AMPLIAR el cupo (deja entrar a uno más;
                  // también sincera un partido que quedó sobre-cupo).
                  OutlinedButton(
                    onPressed: onAmpliarCupo,
                    style: OutlinedButton.styleFrom(foregroundColor: bosque),
                    child: const Text('+1 cupo'),
                  ),
                  const SizedBox(width: 8),
                  OutlinedButton(
                    onPressed: onEliminar,
                    style: OutlinedButton.styleFrom(
                        foregroundColor: const Color(0xFFC0392B)),
                    child: const Text('Eliminar'),
                  ),
                ] else
                  OutlinedButton(
                    onPressed: onBajarse,
                    child: const Text('Salir'),
                  ),
              ] else
                Expanded(
                  child: FilledButton.icon(
                    style: FilledButton.styleFrom(
                        backgroundColor: p.lleno ? const Color(0xFFBDBDBD) : lima,
                        foregroundColor: Colors.white),
                    onPressed: p.lleno ? null : onApuntarse,
                    icon: const Icon(Icons.add, size: 18),
                    label: Text(p.lleno
                        ? 'Completo'
                        : p.esPartner
                            ? 'Juego contigo'
                            : 'Me apunto'),
                  ),
                ),
            ],
          ),
          if (p.canchaId.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: SizedBox(
                width: double.infinity,
                child: OutlinedButton.icon(
                  onPressed: () => EnlacesService.abrirCancha(p.canchaId),
                  icon: const IconoVivo(Icons.stadium_outlined, size: 18),
                  label: const Text('Ver cancha'),
                ),
              ),
            ),
        ],
      ),
    );
  }
}

class _Linea extends StatelessWidget {
  const _Linea(this.icono, this.texto);
  final IconData icono;
  final String texto;
  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 5),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          IconoVivo(icono, size: 16, color: textoTenueDe(context)),
          const SizedBox(width: 8),
          Expanded(
            child: Text(texto,
                style: TextStyle(
                    color: textoTenueDe(context), fontSize: 13, height: 1.3)),
          ),
        ],
      ),
    );
  }
}

Widget _chipSel(BuildContext context, String texto, bool sel, VoidCallback onTap) {
  final cs = Theme.of(context).colorScheme;
  return ChoiceChip(
    label: Text(texto),
    selected: sel,
    showCheckmark: false,
    selectedColor: lima,
    labelStyle: TextStyle(
        color: sel ? Colors.white : cs.onSurface, fontWeight: FontWeight.w600),
    onSelected: (_) => onTap(),
  );
}

/// Hoja para publicar: partido (completar equipo) o "Busco partner". Todo por
/// selección (sin título ni nota libres); el título se arma solo, igual que la
/// web (`titulo_auto`).
class _CrearPartidoSheet extends StatefulWidget {
  const _CrearPartidoSheet(
      {required this.partner, required this.yo, this.deporteInicial});
  final bool partner;
  final LatLng? yo;
  final Deporte? deporteInicial;
  @override
  State<_CrearPartidoSheet> createState() => _CrearPartidoSheetState();
}

class _CrearPartidoSheetState extends State<_CrearPartidoSheet> {
  late Deporte _deporte;
  final _sede = TextEditingController();
  DateTime? _fecha;
  TimeOfDay? _hora;
  int _cupos = 10;
  String _modalidad = 'singles';
  String _nivel = '';
  final List<String> _etiquetas = [];
  bool _guardando = false;
  LatLng? _sedeUbic;

  late final Map<String, (LatLng, String)> _sedes = _cargarSedes();

  /// Locales conocidos → (ubicación, cancha reservable para "Ver cancha").
  Map<String, (LatLng, String)> _cargarSedes() {
    final m = <String, (LatLng, String)>{};
    for (final c in Club.agrupar(appState.todasLasCanchas())) {
      if (c.nombre.trim().isEmpty) continue;
      String id = '';
      for (final x in c.canchas) {
        if (x.reservable) {
          id = x.id;
          break;
        }
      }
      m.putIfAbsent(c.nombre, () => (c.ubicacion, id));
    }
    return m;
  }

  @override
  void initState() {
    super.initState();
    final lista = widget.partner ? Juego.deportesPartner : deportesActivos;
    _deporte = (widget.deporteInicial != null &&
            lista.contains(widget.deporteInicial))
        ? widget.deporteInicial!
        : lista.first;
    _cupos = widget.partner ? 2 : (_presetsDe(_deporte).firstOrNull?.$2 ?? 10);
  }

  @override
  void dispose() {
    _sede.dispose();
    super.dispose();
  }

  Future<void> _elegirFecha() async {
    final hoy = DateTime.now();
    final d = await showDatePicker(
      context: context,
      initialDate: _fecha ?? hoy,
      firstDate: hoy,
      lastDate: hoy.add(const Duration(days: 90)),
    );
    if (d != null) setState(() => _fecha = d);
  }

  Future<void> _elegirHora() async {
    final h = await showTimePicker(
      context: context,
      initialTime: _hora ?? const TimeOfDay(hour: 20, minute: 0),
    );
    if (h != null) setState(() => _hora = h);
  }

  String _dosDig(int n) => n.toString().padLeft(2, '0');

  void _toggleEtiqueta(String k) {
    setState(() {
      if (_etiquetas.contains(k)) {
        _etiquetas.remove(k);
        return;
      }
      if (_etiquetas.length >= Juego.maxEtiquetas) {
        _err('Elige hasta ${Juego.maxEtiquetas} detalles.');
        return;
      }
      if (k == 'mixto') _etiquetas.remove('solo_mujeres');
      if (k == 'solo_mujeres') _etiquetas.remove('mixto');
      _etiquetas.add(k);
    });
  }

  Future<void> _publicar() async {
    final u = appState.usuario;
    if (u == null) return;
    if (_fecha == null || _hora == null) {
      _err('Elige la fecha y la hora del partido.');
      return;
    }
    final sede = _sede.text.trim().replaceAll(RegExp(r'\s+'), ' ');
    if (sede.isEmpty) {
      _err('¿Dónde se juega? Elige la cancha o el lugar.');
      return;
    }
    setState(() => _guardando = true);
    final conocida = _sedes[sede];
    // Otro lugar: mi ubicación ubica el partido para "cerca de mí" y avisos.
    final ubic = conocida?.$1 ?? _sedeUbic ?? widget.yo;
    final fechaIso =
        '${_fecha!.year}-${_dosDig(_fecha!.month)}-${_dosDig(_fecha!.day)}';
    final borrador = PartidoAbierto(
      id: 'p_${DateTime.now().microsecondsSinceEpoch}',
      creadorEmail: u.email,
      creadorNombre: u.nombre,
      deporte: _deporte,
      titulo: '',
      fecha: fechaIso,
      hora: '${_dosDig(_hora!.hour)}:${_dosDig(_hora!.minute)}',
      sedeNombre: sede.length > 80 ? sede.substring(0, 80) : sede,
      lat: ubic?.latitude,
      lng: ubic?.longitude,
      cupos: widget.partner ? (Juego.modalidad(_modalidad)?.$3 ?? 2) : _cupos,
      tipo: widget.partner ? 'partner' : 'partido',
      modalidad: widget.partner ? _modalidad : '',
      nivel: _nivel,
      etiquetas: [
        for (final k in _etiquetas)
          if (Juego.etiquetasPara(_deporte).contains(k)) k
      ],
      canchaId: conocida?.$2 ?? '',
      creado: DateTime.now(),
    );
    // Título automático (= `titulo_auto` de la web).
    var mod = _nombreModalidad(borrador);
    if (widget.partner) mod = '$mod de ${_deporte.etiqueta.toLowerCase()}';
    final titulo = '$mod · ${borrador.sedeNombre}';
    final partido = PartidoAbierto(
      id: borrador.id,
      creadorEmail: borrador.creadorEmail,
      creadorNombre: borrador.creadorNombre,
      deporte: borrador.deporte,
      titulo: titulo.length > 80 ? titulo.substring(0, 80) : titulo,
      fecha: borrador.fecha,
      hora: borrador.hora,
      sedeNombre: borrador.sedeNombre,
      lat: borrador.lat,
      lng: borrador.lng,
      cupos: borrador.cupos,
      tipo: borrador.tipo,
      modalidad: borrador.modalidad,
      nivel: borrador.nivel,
      etiquetas: borrador.etiquetas,
      canchaId: borrador.canchaId,
      creado: borrador.creado,
    );
    bool ok;
    try {
      ok = await conPreload(context, () => PartidosRepo.crear(partido),
          texto: 'Publicando…');
    } finally {
      if (mounted) setState(() => _guardando = false);
    }
    if (!mounted) return;
    if (ok) {
      Navigator.of(context).pop(true);
    } else {
      _err('No se pudo publicar. Revisa tu conexión.');
    }
  }

  void _err(String m) =>
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(m)));

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final deps = widget.partner ? Juego.deportesPartner : deportesActivos;
    return Padding(
      padding: EdgeInsets.fromLTRB(
          20, 18, 20, 20 + MediaQuery.of(context).viewInsets.bottom),
      child: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(widget.partner ? 'Busco partner' : 'Organizar partido',
                style: t.titleLarge?.copyWith(fontWeight: FontWeight.w800)),
            const SizedBox(height: 14),
            Text('Deporte', style: t.labelLarge),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                for (final d in deps)
                  _chipSel(context, d.etiqueta, _deporte == d, () {
                    setState(() {
                      _deporte = d;
                      // Propone un total típico del deporte nuevo y quita los
                      // detalles que no le aplican.
                      if (!widget.partner) {
                        final ps = _presetsDe(d);
                        if (ps.isNotEmpty) _cupos = ps.first.$2;
                      }
                      _etiquetas.removeWhere(
                          (k) => !Juego.etiquetasPara(d).contains(k));
                    });
                  }),
              ],
            ),
            const SizedBox(height: 16),
            Autocomplete<String>(
              optionsBuilder: (v) {
                final q = v.text.trim().toLowerCase();
                if (q.isEmpty) return const Iterable<String>.empty();
                return _sedes.keys
                    .where((n) => n.toLowerCase().contains(q))
                    .take(6);
              },
              onSelected: (sel) {
                _sede.text = sel;
                _sedeUbic = _sedes[sel]?.$1;
              },
              fieldViewBuilder: (ctx, ctrl, focus, _) {
                return TextField(
                  controller: ctrl,
                  focusNode: focus,
                  // Espeja lo tecleado en nuestro controller (lo leemos al
                  // publicar); onSelected además captura la ubicación.
                  onChanged: (v) {
                    _sede.text = v;
                    _sedeUbic = null;
                  },
                  decoration: const InputDecoration(
                      labelText: '¿Dónde se juega?',
                      hintText: 'Busca la cancha o el lugar',
                      helperText:
                          'Si no es un local de Pichangol, usamos tu ubicación '
                          'para avisar a los de la zona.',
                      helperMaxLines: 2,
                      prefixIcon: IconoVivo(Icons.place_outlined)),
                );
              },
            ),
            const SizedBox(height: 14),
            Row(
              children: [
                Expanded(
                  child: _SelectorCampo(
                    icono: Icons.calendar_today,
                    etiqueta: _fecha == null
                        ? 'Fecha'
                        : '${_fecha!.day}/${_dosDig(_fecha!.month)}',
                    onTap: _elegirFecha,
                    lleno: _fecha != null,
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: _SelectorCampo(
                    icono: Icons.access_time,
                    etiqueta: _hora == null
                        ? 'Hora'
                        : '${_dosDig(_hora!.hour)}:${_dosDig(_hora!.minute)}',
                    onTap: _elegirHora,
                    lleno: _hora != null,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 16),
            if (widget.partner) ...[
              Text('¿Qué buscas?', style: t.labelLarge),
              const SizedBox(height: 2),
              Text(
                  (Juego.modalidad(_modalidad)?.$3 ?? 2) == 4
                      ? 'Buscas 3 jugadores más'
                      : 'Buscas 1 jugador',
                  style: const TextStyle(color: textoTenue, fontSize: 12)),
              const SizedBox(height: 8),
              Wrap(spacing: 8, runSpacing: 8, children: [
                for (final m in Juego.modalidades)
                  _chipSel(context, m.$2, _modalidad == m.$1,
                      () => setState(() => _modalidad = m.$1)),
              ]),
            ] else ...[
              Text('Jugadores en total', style: t.labelLarge),
              const SizedBox(height: 2),
              Text('Tú ya cuentas como 1 · te faltan ${_cupos - 1}',
                  style: const TextStyle(color: textoTenue, fontSize: 12)),
              const SizedBox(height: 8),
              // Atajos por deporte (Fut 5/6/7…): fijan el total sin que el
              // usuario tenga que hacer la cuenta.
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  for (final p in _presetsDe(_deporte))
                    _chipSel(context, '${p.$1} (${p.$2})', _cupos == p.$2,
                        () => setState(() => _cupos = p.$2)),
                ],
              ),
              const SizedBox(height: 10),
              Row(
                children: [
                  _StepBtn(
                      icon: Icons.remove,
                      onTap: () =>
                          setState(() => _cupos = (_cupos - 1).clamp(2, 40))),
                  Expanded(
                    child: Center(
                      child: Text('$_cupos',
                          style: t.headlineSmall
                              ?.copyWith(fontWeight: FontWeight.w800)),
                    ),
                  ),
                  _StepBtn(
                      icon: Icons.add,
                      onTap: () =>
                          setState(() => _cupos = (_cupos + 1).clamp(2, 40))),
                ],
              ),
            ],
            const SizedBox(height: 16),
            Text('Nivel', style: t.labelLarge),
            const SizedBox(height: 8),
            Wrap(spacing: 8, runSpacing: 8, children: [
              _chipSel(context, 'Todos los niveles', _nivel.isEmpty,
                  () => setState(() => _nivel = '')),
              for (final n in Juego.niveles)
                _chipSel(context, n.$2, _nivel == n.$1,
                    () => setState(() => _nivel = n.$1)),
            ]),
            const SizedBox(height: 16),
            Text('Detalles (hasta ${Juego.maxEtiquetas})', style: t.labelLarge),
            const SizedBox(height: 8),
            Wrap(spacing: 8, runSpacing: 8, children: [
              for (final k in Juego.etiquetasPara(_deporte))
                _chipSel(
                    context,
                    '${Juego.etiquetas[k]!.$1} ${Juego.etiquetas[k]!.$2}',
                    _etiquetas.contains(k),
                    () => _toggleEtiqueta(k)),
            ]),
            const SizedBox(height: 20),
            SizedBox(
              width: double.infinity,
              child: FilledButton(
                style: FilledButton.styleFrom(
                    backgroundColor: lima,
                    foregroundColor: Colors.white,
                    padding: const EdgeInsets.symmetric(vertical: 15)),
                onPressed: _guardando ? null : _publicar,
                child: const Text('Publicar'),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// "Avísame partidos cerca" + "Aparecer como disponible" (backend `/juego/prefs`).
class _PrefsSheet extends StatefulWidget {
  const _PrefsSheet(
      {required this.inicial, required this.yo, required this.partner});
  final PrefsJuego inicial;
  final LatLng? yo;
  final bool partner;
  @override
  State<_PrefsSheet> createState() => _PrefsSheetState();
}

class _PrefsSheetState extends State<_PrefsSheet> {
  late bool _avisos = widget.inicial.avisos;
  late bool _disponible = widget.inicial.disponible;
  late final List<String> _deportes = widget.inicial.deportes.isNotEmpty
      ? [...widget.inicial.deportes]
      : [widget.partner ? Juego.deportesPartner.first.name : Deporte.futbol.name];
  late int _radio = widget.inicial.radioKm;
  late final List<String> _franjas = [...widget.inicial.franjas];
  late String _dias = widget.inicial.dias;
  bool _guardando = false;

  Future<void> _guardar() async {
    final u = appState.usuario;
    if (u == null) return;
    setState(() => _guardando = true);
    LatLng? ubic = widget.yo;
    if (_avisos || _disponible) {
      ubic = await LocationService.ubicacionActual() ?? ubic;
    }
    if (!mounted) return;
    final (p, error) = await JuegoService.guardar(
      u.email,
      PrefsJuego(
        deportes: _deportes,
        radioKm: _radio,
        franjas: _franjas,
        dias: _dias,
        avisos: _avisos,
        disponible: _disponible,
      ),
      lat: ubic?.latitude,
      lng: ubic?.longitude,
      nombre: u.nombre,
    );
    if (!mounted) return;
    setState(() => _guardando = false);
    if (p != null) {
      Navigator.of(context).pop(p);
    } else {
      await avisarPichangol(context,
          titulo: 'No se pudo guardar',
          mensaje: error ?? 'Reintenta en un momento.',
          icono: Icons.error_outline);
    }
  }

  Widget _switch(String titulo, String sub, bool v, ValueChanged<bool> on) {
    return SwitchListTile(
      contentPadding: EdgeInsets.zero,
      value: v,
      activeColor: lima,
      onChanged: on,
      title: Text(titulo, style: const TextStyle(fontWeight: FontWeight.w800)),
      subtitle: Text(sub, style: const TextStyle(fontSize: 12.5)),
    );
  }

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return Padding(
      padding: EdgeInsets.fromLTRB(
          20, 18, 20, 20 + MediaQuery.of(context).viewInsets.bottom),
      child: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Avisos y disponibilidad',
                style: t.titleLarge?.copyWith(fontWeight: FontWeight.w800)),
            const SizedBox(height: 6),
            _switch(
                '🔔 Avísame partidos cerca',
                'Te llega una notificación cuando alguien publica un partido '
                    'que te calza (máx. 3 al día).',
                _avisos,
                (v) => setState(() => _avisos = v)),
            _switch(
                '🙋 Aparecer como disponible',
                'Otros jugadores cerca te ven y te pueden escribir para jugar. '
                    'Solo ven tu nombre, tu nivel y la distancia aproximada.',
                _disponible,
                (v) => setState(() => _disponible = v)),
            const SizedBox(height: 10),
            Text('Deportes', style: t.labelLarge),
            const SizedBox(height: 8),
            Wrap(spacing: 8, runSpacing: 8, children: [
              for (final d in deportesActivos)
                _chipSel(context, d.etiqueta, _deportes.contains(d.name), () {
                  setState(() {
                    if (_deportes.contains(d.name)) {
                      if (_deportes.length > 1) _deportes.remove(d.name);
                    } else {
                      _deportes.add(d.name);
                    }
                  });
                }),
            ]),
            const SizedBox(height: 14),
            Text('¿Hasta qué distancia?', style: t.labelLarge),
            const SizedBox(height: 8),
            Wrap(spacing: 8, runSpacing: 8, children: [
              for (final r in Juego.radios)
                _chipSel(context, '$r km', _radio == r,
                    () => setState(() => _radio = r)),
            ]),
            const SizedBox(height: 14),
            Text('¿A qué hora juegas?', style: t.labelLarge),
            const Text('Sin elegir = a cualquier hora.',
                style: TextStyle(color: textoTenue, fontSize: 12)),
            const SizedBox(height: 8),
            Wrap(spacing: 8, runSpacing: 8, children: [
              for (final f in Juego.franjas)
                _chipSel(context, f.$2, _franjas.contains(f.$1), () {
                  setState(() {
                    if (_franjas.contains(f.$1)) {
                      _franjas.remove(f.$1);
                    } else {
                      _franjas.add(f.$1);
                    }
                  });
                }),
            ]),
            const SizedBox(height: 14),
            Text('¿Qué días?', style: t.labelLarge),
            const SizedBox(height: 8),
            Wrap(spacing: 8, runSpacing: 8, children: [
              for (final d in Juego.dias)
                _chipSel(context, d.$2, _dias == d.$1,
                    () => setState(() => _dias = d.$1)),
            ]),
            const SizedBox(height: 20),
            SizedBox(
              width: double.infinity,
              child: FilledButton(
                style: FilledButton.styleFrom(
                    backgroundColor: lima,
                    foregroundColor: Colors.white,
                    padding: const EdgeInsets.symmetric(vertical: 15)),
                onPressed: _guardando ? null : _guardar,
                child: Text(_guardando ? 'Guardando…' : 'Guardar'),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _SelectorCampo extends StatelessWidget {
  const _SelectorCampo({
    required this.icono,
    required this.etiqueta,
    required this.onTap,
    required this.lleno,
  });
  final IconData icono;
  final String etiqueta;
  final VoidCallback onTap;
  final bool lleno;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(12),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 15),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: lleno ? bosque : trazo),
        ),
        child: Row(
          children: [
            Icon(icono, size: 18, color: lleno ? bosque : textoTenue),
            const SizedBox(width: 10),
            Text(etiqueta,
                style: TextStyle(
                    color: lleno ? cs.onSurface : textoTenue,
                    fontWeight: FontWeight.w600)),
          ],
        ),
      ),
    );
  }
}

class _StepBtn extends StatelessWidget {
  const _StepBtn({required this.icon, required this.onTap});
  final IconData icon;
  final VoidCallback onTap;
  @override
  Widget build(BuildContext context) {
    return Material(
      color: limaSuave,
      shape: const CircleBorder(),
      child: InkWell(
        customBorder: const CircleBorder(),
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(10),
          child: Icon(icon, color: bosque),
        ),
      ),
    );
  }
}
