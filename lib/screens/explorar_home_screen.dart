import 'package:flutter/material.dart';
import 'package:geocoding/geocoding.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart' show LatLng;

import '../models/models.dart';
import '../models/club.dart';
import '../widgets/club_card.dart';
import '../widgets/pin_cargando.dart';
import '../widgets/responsive.dart';
import '../brand.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../config/pais.dart';
import '../services/location_service.dart';
import '../services/pagos_service.dart';
import '../utils/geo.dart';
import '../utils/moneda.dart';
import 'academias_screen.dart';
import 'busqueda_guiada_screen.dart';
import 'club_detalle_screen.dart';
import 'login_google_sheet.dart';
import 'mapa_canchas_screen.dart';
import 'permisos_onboarding_screen.dart';
import 'home_shell.dart';
import 'ranking_global_screen.dart';

/// Pantalla de inicio estilo Airbnb: LISTA de canchas/locales (sin mapa) con
/// barra de búsqueda flotante y filtros por deporte. La ubicación se usa para
/// ordenar y descubrir canchas cercanas, pero no se muestra ningún mapa.
class ExplorarHomeScreen extends StatefulWidget {
  const ExplorarHomeScreen({super.key});

  @override
  State<ExplorarHomeScreen> createState() => _ExplorarHomeScreenState();
}

class _ExplorarHomeScreenState extends State<ExplorarHomeScreen> {
  Deporte? _filtro = Deporte.futbol; // por defecto: Fútbol
  bool _soloClubes = false; // pestaña "Clubes": solo clubes formales (country…)
  bool _porPrecio = false; // orden de la lista: false = cercanía, true = precio

  /// Ordena una sección por precio "desde" (más barato primero) si el usuario
  /// eligió ordenar por precio; si no, respeta el orden por cercanía.
  List<Club> _ordenarPorPrecio(List<Club> l) {
    if (!_porPrecio) return l;
    final copia = [...l];
    copia.sort((a, b) => (a.precioDesde ?? double.infinity)
        .compareTo(b.precioDesde ?? double.infinity));
    return copia;
  }

  LatLng? _centroBusqueda; // zona buscada por el usuario (estilo Airbnb)
  String? _labelBusqueda;
  bool _ubicando = true; // true mientras se resuelve la ubicación inicial
  // El centro actual es un DEFAULT por país (no la ubicación real todavía): la
  // lista ya se muestra, pero al llegar el GPS se re-centra y re-etiqueta.
  bool _ubicacionProvisional = false;

  /// Clubes derivados de las canchas filtradas (un local = varias canchas).
  /// En la pestaña "Clubes" solo quedan los clubes formales (country clubs…).
  List<Club> _clubs({bool todosLosDeportes = false}) {
    final clubs =
        Club.agrupar(_filtradas(todosLosDeportes: todosLosDeportes));
    if (_soloClubes) return clubs.where((c) => c.esClubFormal).toList();
    return clubs;
  }

  /// Nivel de "destacado" de un local (máximo entre sus canchas: si su dueño
  /// tiene saldo, va destacado). 0 = no destacado.
  int _nivelClub(Club cl) {
    var mx = 0;
    for (final c in cl.canchas) {
      final n = appState.nivelDestacado(c);
      if (n > mx) mx = n;
    }
    return mx;
  }

  /// Score para ordenar "Destacados cerca de ti": el nivel (tier) manda, luego
  /// la calidad (verificada, rating, fotos), la cercanía, y una rotación
  /// anti-fatiga por hora para que no salga siempre el mismo entre parecidos.
  double _scoreDestacado(Club cl) {
    var s = _nivelClub(cl) * 1000.0;
    if (cl.verificada) s += 60;
    // Reputación REAL (⭐ promedio): si no tiene reseñas usa una base neutra
    // (4.5) para no castigar a los nuevos ni premiar un rating inventado.
    final rep = appState.resumenResenas(cl.canchas.map((c) => c.id).toList());
    s += (rep.hay ? rep.promedio : 4.5) * 12;
    final tieneFotos =
        cl.canchas.any((c) => c.fotos.isNotEmpty || c.fotoUrl != null);
    if (tieneFotos) s += 25;
    if (_centroBusqueda != null) {
      s -= distanciaKm(_centroBusqueda!, cl.ubicacion) * 8;
    }
    s += _jitterRotacion(cl.id);
    return s;
  }

  /// Rotación determinística por hora del día (0..39): rota el orden entre
  /// destacados parecidos sin romper la estabilidad dentro de la sesión.
  double _jitterRotacion(String id) {
    var h = DateTime.now().hour;
    for (final code in id.codeUnits) {
      h = (h * 31 + code) & 0x7fffffff;
    }
    return (h % 40).toDouble();
  }

  List<Cancha> _filtradas({bool todosLosDeportes = false}) {
    // Pádel retirado del piloto: nunca aparece en la lista. Con multideporte,
    // basta que la cancha ofrezca ALGO distinto de pádel para mostrarla.
    final base = appState
        .todasLasCanchas()
        .where((c) => c.deportesJugables.any((d) => d != Deporte.padel))
        .toList();
    // En "Clubes" no se filtra por deporte (un club puede tener varios). Una
    // loza multiuso aparece en el filtro de CADA deporte que ofrece (`ofrece`).
    // `todosLosDeportes` (mapa): ignora el chip activo — el mapa filtra solo.
    var lista = (todosLosDeportes || _filtro == null || _soloClubes)
        ? base
        : base.where((c) => c.ofrece(_filtro!)).toList();

    // Producto real: SIEMPRE mostramos canchas CERCA del usuario. Mientras no
    // haya ubicación (GPS sin resolver o sin permiso), NO se vuelca un listado
    // global: así nunca aparecen canchas de otra ciudad/país. La UI muestra
    // "buscando tu ubicación…" con la opción de reintentar.
    final centro = _centroBusqueda;
    if (centro == null) return const [];
    lista.sort((a, b) => distanciaKm(centro, a.ubicacion)
        .compareTo(distanciaKm(centro, b.ubicacion)));
    // Solo las que están de verdad cerca (dentro del radio de búsqueda).
    lista = lista
        .where((c) =>
            distanciaKm(centro, c.ubicacion) <= appState.radioBusquedaKm)
        .toList();
    return lista;
  }

  int _numCanchas = 0;

  @override
  void initState() {
    super.initState();
    _numCanchas = appState.todasLasCanchas().length;
    appState.addListener(_onStateChange);
    appState.cargarDestacados(); // refresca qué dueños van destacados (saldo>0)
    _cargarResenasVisibles(); // rating real en las tarjetas (⭐ reputación)
    _autoUbicar(); // autodetecta la ubicación al abrir
    // Onboarding de permisos (una sola vez, tras instalar): notificaciones,
    // micrófono, cámara y pantalla completa. Estilo WhatsApp.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) PermisosOnboardingScreen.mostrarSiHaceFalta(context);
    });
  }

  void _onStateChange() {
    final n = appState.todasLasCanchas().length;
    if (n != _numCanchas) {
      _numCanchas = n;
      _cargarResenasVisibles(); // trae reseñas de las canchas nuevas
      if (mounted) setState(() {}); // refresca la lista al registrar una cancha
    }
  }

  /// Trae en lote la reputación real de las canchas REGISTRADAS (las que pueden
  /// tener reseñas) para pintar el ⭐ en las tarjetas. Guardado contra rebuilds
  /// (solo consulta las no cacheadas) y repinta al terminar.
  void _cargarResenasVisibles() {
    final ids = appState
        .todasLasCanchas()
        .where((c) => c.registrada)
        .map((c) => c.id)
        .toList();
    appState.cargarResenasFaltantes(ids).then((_) {
      if (mounted) setState(() {});
    });
  }

  /// Re-identifica la ubicación a pedido (botón): limpia el nombre de zona para
  /// que se resuelva de nuevo y re-centra en el usuario.
  Future<void> _reubicar() async {
    setState(() => _labelBusqueda = null);
    await _autoUbicar();
  }

  Future<void> _autoUbicar() async {
    if (mounted) setState(() => _ubicando = true);
    // 0) DEFAULT por país AL INSTANTE: si aún no hay centro, muestra canchas de
    //    la ciudad principal del país de una vez. Así Explorar NUNCA se queda en
    //    "Detectando tu ubicación…" ni en blanco por un GPS colgado. Es
    //    provisional: al llegar el fix real se re-centra y re-etiqueta.
    if (_centroBusqueda == null) {
      final d = ubicacionPorDefecto();
      _aplicarUbicacion(LatLng(d.lat, d.lng),
          descubrir: false, provisional: true);
    }
    try {
      // 1) Ubicación INSTANTÁNEA con la última conocida (con tope duro por si el
      //    SO se cuelga leyéndola). Reordena la lista a la zona del usuario.
      final rapida = await LocationService.ultimaConocida()
          .timeout(const Duration(seconds: 2), onTimeout: () => null);
      if (rapida != null && mounted) _aplicarUbicacion(rapida);

      // 2) Fix PRECISO. Tope duro extra sobre el interno del service: pase lo que
      //    pase, esto resuelve y el spinner se apaga (nunca queda pegado).
      final precisa = await LocationService.ubicacionActual()
          .timeout(const Duration(seconds: 9), onTimeout: () => null);
      if (precisa != null && mounted) {
        // Re-busca canchas reales solo si nos movimos lejos de la posición
        // rápida (o si esa no existía): evita una llamada a Places innecesaria.
        final reUbicar = rapida == null || distanciaKm(rapida, precisa) > 2;
        _aplicarUbicacion(precisa, descubrir: reUbicar);
      }
    } finally {
      if (mounted) setState(() => _ubicando = false);
    }
  }

  /// Aplica una ubicación: reordena la lista a lo cercano y (opcionalmente)
  /// descubre canchas reales alrededor. [provisional] = default por país (aún no
  /// es la ubicación real): no geocodifica ni descubre, y marca el estado para
  /// re-resolver la zona cuando llegue el GPS.
  void _aplicarUbicacion(LatLng pos,
      {bool descubrir = true, bool provisional = false}) {
    setState(() {
      _centroBusqueda = pos;
      if (provisional) {
        _ubicacionProvisional = true;
        _labelBusqueda = '${paisActual.nombre} · aprox.'; // hasta el fix real
      } else {
        // Ubicación real: si veníamos de un default provisional, limpia la
        // etiqueta para que se resuelva la zona (distrito) verdadera.
        if (_ubicacionProvisional) _labelBusqueda = null;
        _ubicacionProvisional = false;
        _labelBusqueda ??= 'Tu ubicación'; // provisional hasta resolver la zona
      }
    });
    if (provisional) return; // el default no geocodifica ni gasta Places
    _resolverNombreZona(pos); // identifica el nombre real de la zona (distrito)
    if (descubrir) appState.descubrirCanchasCerca(pos); // canchas reales (Places)
  }

  /// Reverse-geocode: pone el nombre real de la zona (distrito/localidad) en la
  /// barra, para que se vea que la app identificó tu ubicación. Fail-safe.
  Future<void> _resolverNombreZona(LatLng pos) async {
    try {
      final marks = await placemarkFromCoordinates(pos.latitude, pos.longitude);
      if (!mounted || marks.isEmpty) return;
      final m = marks.first;
      setMonedaPorPais(m.isoCountryCode); // S/ · Bs · $ según el país
      final n = (m.subLocality?.trim().isNotEmpty == true
              ? m.subLocality
              : (m.locality?.trim().isNotEmpty == true
                  ? m.locality
                  : m.subAdministrativeArea)) ??
          '';
      // Solo si la barra sigue mostrando la ubicación automática (no una
      // búsqueda manual que el usuario hizo entre tanto).
      if (n.trim().isNotEmpty &&
          (_labelBusqueda == 'Tu ubicación' || _labelBusqueda == null)) {
        setState(() => _labelBusqueda = n.trim());
      }
    } catch (_) {
      // sin nombre: se queda "Tu ubicación"
    }
  }

  @override
  void dispose() {
    appState.removeListener(_onStateChange);
    super.dispose();
  }

  void _cambiarFiltro(Deporte? f) {
    setState(() {
      _filtro = f;
      _soloClubes = false; // elegir un deporte sale de la pestaña "Clubes"
    });
  }

  /// Activa la pestaña "Clubes": solo clubes formales (country clubs, etc.).
  void _activarClubes() {
    setState(() => _soloClubes = true);
  }

  // BÚSQUEDA GUIADA (estilo Airbnb): zona + deporte obligatorio + fecha/hora.
  DateTime? _fechaBusqueda;
  String? _horaBusqueda;
  bool _busquedaHecha = false; // tras buscar, el mapa abre con ATRIBUTOS

  Future<void> _abrirBuscar() async {
    final res = await Navigator.of(context).push<ResultadoBusquedaGuiada>(
      MaterialPageRoute(
          builder: (_) => BusquedaGuiadaScreen(
                centroInicial: _centroBusqueda,
                etiquetaInicial: _labelBusqueda,
                deporteInicial: _filtro,
              )),
    );
    if (!mounted) return;
    if (res == null) {
      // Pudo cambiar solo el radio (sin elegir zona): refresca la lista.
      setState(() {});
      return;
    }
    setState(() {
      _centroBusqueda = res.centro;
      _labelBusqueda = res.etiqueta;
      _filtro = res.deporte; // el deporte elegido filtra la lista
      _soloClubes = false;
      _fechaBusqueda = res.fecha;
      _horaBusqueda = res.hora;
      _busquedaHecha = true;
    });
    // Búsqueda explícita del usuario → fuerza Google y re-cosecha (frescura).
    appState.descubrirCanchasCerca(res.centro, forzarGoogle: true);
  }

  /// Subtítulo del buscador tras una búsqueda guiada: "⚽ Fútbol · Hoy · 19:00".
  String? get _subtituloBusqueda {
    final f = _fechaBusqueda;
    if (!_busquedaHecha || f == null || _filtro == null) return null;
    final hoy = DateTime.now();
    bool mismo(DateTime a, DateTime b) =>
        a.year == b.year && a.month == b.month && a.day == b.day;
    const dias = ['lun', 'mar', 'mié', 'jue', 'vie', 'sáb', 'dom'];
    final fecha = mismo(f, hoy)
        ? 'Hoy'
        : mismo(f, hoy.add(const Duration(days: 1)))
            ? 'Mañana'
            : '${dias[f.weekday - 1]} ${f.day}';
    final hora = _horaBusqueda == null ? '' : ' · $_horaBusqueda';
    return '${emojiDeporte(_filtro!)} ${_filtro!.etiqueta} · $fecha$hora';
  }

  void _limpiarBusqueda() {
    setState(() {
      _centroBusqueda = null;
      _labelBusqueda = null;
      _fechaBusqueda = null;
      _horaBusqueda = null;
      _busquedaHecha = false;
    });
  }

  /// Abre un LOCAL desde su card. Si el usuario es su DUEÑO, va directo a su
  /// panel (Mis canchas); si no, a la ficha pública para reservar.
  ///
  /// IMPORTANTE: la ficha recibe el club TAL CUAL viene del card, con sus
  /// canchas YA FILTRADAS por el deporte elegido (el card se arma desde
  /// `_clubs()` = `Club.agrupar(_filtradas())`). Así, si buscas FÚTBOL y abres
  /// Machuca, "Elige la cancha" muestra solo sus canchas de fútbol; si buscas
  /// TENIS, solo la de tenis. Con filtro "Todos" se ven todas.
  void _abrirClub(Club club) {
    final email = appState.usuario?.email ?? '';
    final esMio = email.isNotEmpty && club.canchas.any((c) => c.dueno == email);
    if (esMio) {
      _abrirPanel(); // panel del dueño (Mis canchas)
      return;
    }
    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) =>
            ClubDetalleScreen(club: club, canchaInicial: club.principal),
      ),
    );
  }

  /// Abre el Panel del Dueño unificado (Mis canchas · Agenda · Reservas ·
  /// Reportes · Cuenta). Requiere sesión de Google porque "Mis canchas" trabaja
  /// sobre las canchas del dueño (dueno == tu correo).
  Future<void> _abrirPanel() async {
    if (!await LoginGoogleSheet.mostrar(context,
        motivo: 'administrar tus canchas')) {
      return;
    }
    if (!mounted) return;
    Navigator.of(context).push(
      MaterialPageRoute(builder: (_) => const HomeShell()),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Stack(
        children: [
          // LISTA de clubes/canchas (deja hueco arriba para la barra flotante).
          Positioned.fill(
            child: Padding(
              padding: const EdgeInsets.only(top: 160),
              child: ListenableBuilder(
                listenable: appState,
                builder: (context, _) {
                  final clubs = _clubs();
                  if (clubs.isEmpty) {
                    // Sin ubicación (permiso/GPS) → invita a activarla.
                    if (_centroBusqueda == null && !_ubicando) {
                      return _SinUbicacion(onUsar: _reubicar);
                    }
                    if (_ubicando) {
                      return const Center(
                        child: Padding(
                          padding: EdgeInsets.all(32),
                          child: PinCargando(texto: 'Detectando tu ubicación…'),
                        ),
                      );
                    }
                    return Center(
                      child: Padding(
                        padding: const EdgeInsets.all(32),
                        child: Text(
                          'No hay canchas cerca. Amplía el radio o busca otra '
                          'zona.',
                          textAlign: TextAlign.center,
                          style: Theme.of(context)
                              .textTheme
                              .bodyMedium
                              ?.copyWith(color: textoTenueDe(context)),
                        ),
                      ),
                    );
                  }
                  // Clasificar: CLUBES = locales formales (country clubs,
                  // varios deportes, fundador). El resto, por su deporte.
                  final clubesFormales = <Club>[];
                  final porDeporte = <Deporte, List<Club>>{};
                  for (final cl in clubs) {
                    if (cl.esClubFormal) {
                      clubesFormales.add(cl);
                    } else {
                      // Con un deporte filtrado, agrupa bajo ese deporte (una
                      // loza multiuso cae en la sección del deporte pedido); sin
                      // filtro, bajo su deporte principal.
                      porDeporte
                          .putIfAbsent(_filtro ?? cl.principal.deporte, () => [])
                          .add(cl);
                    }
                  }
                  // COMPARADOR DE PRECIOS: por cada grupo del MISMO deporte,
                  // calcula el promedio y el mínimo "desde" para marcar el más
                  // barato ("MEJOR PRECIO") y el % de ahorro vs. la zona. Solo
                  // aplica con ≥2 opciones con precio (comparar tiene sentido).
                  final comp = <String, ({int? ahorro, bool mejor})>{};
                  void calcularComparador(List<Club> grupo) {
                    final conPrecio = grupo
                        .where((c) => c.registrada && (c.precioDesde ?? 0) > 0)
                        .toList();
                    if (conPrecio.length < 2) return;
                    final precios =
                        conPrecio.map((c) => c.precioDesde!).toList();
                    final avg =
                        precios.reduce((a, b) => a + b) / precios.length;
                    final minP = precios.reduce((a, b) => a < b ? a : b);
                    // Solo hay "mejor precio" si existe diferencia real (si todas
                    // valen igual, el sello no aporta).
                    final haySpread = precios.any((x) => x > minP);
                    for (final c in conPrecio) {
                      final p = c.precioDesde!;
                      final ah =
                          avg > 0 ? (((avg - p) / avg) * 100).round() : 0;
                      comp[c.id] = (
                        ahorro: ah > 0 ? ah : null,
                        mejor: haySpread && p <= minP,
                      );
                    }
                  }

                  for (final g in porDeporte.values) {
                    calcularComparador(g);
                  }
                  calcularComparador(clubesFormales);

                  final nCanchas =
                      clubs.fold<int>(0, (a, c) => a + c.canchas.length);
                  final hijos = <Widget>[
                    // El acceso a ACADEMIAS ahora es un CHIP en la fila de
                    // filtros (pedido del director) — ya no tarjeta aquí.
                    // La liga es una capa de TENIS: el banner de descubrimiento
                    // sale al filtrar raqueta y SOLO si aún no eres del circuito
                    // (si ya lo eres, lo tienes en tu Perfil).
                    if (_filtro != null &&
                        _filtro!.esRaqueta &&
                        !appState.usaCircuito)
                      _CircuitoBannerExplorar(
                        onTap: () => Navigator.of(context).push(
                            MaterialPageRoute(
                                builder: (_) => const RankingGlobalScreen())),
                      ),
                    Row(
                      children: [
                        Expanded(
                          child: Text(
                            '${clubs.length} ${clubs.length == 1 ? 'lugar' : 'lugares'} · $nCanchas canchas',
                            style: Theme.of(context)
                                .textTheme
                                .bodyMedium
                                ?.copyWith(color: textoTenueDe(context)),
                          ),
                        ),
                        _OrdenChip(
                            texto: 'Cerca',
                            icono: Icons.near_me,
                            activo: !_porPrecio,
                            onTap: () => setState(() => _porPrecio = false)),
                        const SizedBox(width: 6),
                        _OrdenChip(
                            texto: 'Precio',
                            icono: Icons.sell_outlined,
                            activo: _porPrecio,
                            onTap: () => setState(() => _porPrecio = true)),
                      ],
                    ),
                  ];
                  Widget card(Club cl) => Padding(
                        padding: const EdgeInsets.only(top: 12),
                        child: ClubCard(
                          club: cl,
                          nivelDestacado: _nivelClub(cl),
                          esMejorPrecio: comp[cl.id]?.mejor ?? false,
                          ahorroPct: comp[cl.id]?.ahorro,
                          resumenResenas: appState.resumenResenas(
                              cl.canchas.map((c) => c.id).toList()),
                          onTap: () => _abrirClub(cl),
                          distanciaKm: _centroBusqueda == null
                              ? null
                              : distanciaKm(_centroBusqueda!, cl.ubicacion),
                        ),
                      );

                  // En tablet/landscape las tarjetas van en grilla de 2-3
                  // columnas; en móvil, una debajo de otra.
                  final tablet = esTablet(context);
                  void agregarCards(List<Club> lista) {
                    if (!tablet) {
                      hijos.addAll(lista.map(card));
                      return;
                    }
                    hijos.add(LayoutBuilder(builder: (context, cons) {
                      final cols = columnasTablet(cons.maxWidth);
                      final w = (cons.maxWidth - 14 * (cols - 1)) / cols;
                      return Padding(
                        padding: const EdgeInsets.only(top: 12),
                        child: Wrap(
                          spacing: 14,
                          runSpacing: 14,
                          children: [
                            for (final cl in lista)
                              SizedBox(
                                width: w,
                                child: ClubCard(
                                  club: cl,
                                  nivelDestacado: _nivelClub(cl),
                                  esMejorPrecio: comp[cl.id]?.mejor ?? false,
                                  ahorroPct: comp[cl.id]?.ahorro,
                                  onTap: () => _abrirClub(cl),
                                  distanciaKm: _centroBusqueda == null
                                      ? null
                                      : distanciaKm(
                                          _centroBusqueda!, cl.ubicacion),
                                ),
                              ),
                          ],
                        ),
                      );
                    }));
                  }

                  // DESTACADOS cerca de ti: locales cuyo dueño tiene saldo (más
                  // saldo = más visibilidad). Van arriba, ordenados por nivel y
                  // luego cercanía; también aparecen en su sección de deporte.
                  final destacados = clubs
                      .where((cl) => _nivelClub(cl) > 0)
                      .toList()
                    ..sort((a, b) =>
                        _scoreDestacado(b).compareTo(_scoreDestacado(a)));
                  final topDest = destacados.take(6).toList();
                  // Métrica de impacto: registra una impresión por cada dueño
                  // destacado mostrado (dedup por sesión en PagosService).
                  if (destacados.isNotEmpty) {
                    final duenosVistos = <String>{};
                    for (final cl in destacados) {
                      for (final c in cl.canchas) {
                        if (appState.nivelDestacado(c) > 0 &&
                            c.dueno.isNotEmpty) {
                          duenosVistos.add(c.dueno);
                        }
                      }
                    }
                    PagosService.registrarVistasUnaVez(duenosVistos.toList());
                  }
                  // FAVORITOS del jugador que están cerca (arriba de todo).
                  final favs = clubs
                      .where((cl) => appState.esFavorito(cl.id))
                      .toList();
                  if (favs.isNotEmpty) {
                    hijos.add(_SeccionHeader(
                        'Tus favoritos', favs.length, const Color(0xFFE0245E),
                        Icons.favorite));
                    agregarCards(favs);
                  }
                  if (topDest.isNotEmpty) {
                    hijos.add(_SeccionHeader('Destacados cerca de ti',
                        topDest.length, lima, Icons.star));
                    agregarCards(topDest);
                  }

                  // Los que ya se mostraron arriba en "Destacados" NO se repiten
                  // en su sección de deporte/clubes (estilo Airbnb: destacado
                  // arriba, el resto abajo, sin duplicar).
                  final idsDest = topDest.map((c) => c.id).toSet();
                  for (final d in deportesActivos) {
                    final lista = (porDeporte[d] ?? const <Club>[])
                        .where((cl) => !idsDest.contains(cl.id))
                        .toList();
                    if (lista.isEmpty) continue;
                    hijos.add(_SeccionHeader(
                        d.etiqueta, lista.length, colorDeporte(d),
                        iconoDeporte(d)));
                    agregarCards(_ordenarPorPrecio(lista));
                  }
                  final formalesRestantes = clubesFormales
                      .where((cl) => !idsDest.contains(cl.id))
                      .toList();
                  if (formalesRestantes.isNotEmpty) {
                    hijos.add(_SeccionHeader(
                        'Clubes',
                        formalesRestantes.length,
                        Theme.of(context).colorScheme.primary,
                        Icons.apartment));
                    agregarCards(_ordenarPorPrecio(formalesRestantes));
                  }
                  return ListView(
                    padding: const EdgeInsets.fromLTRB(18, 16, 18, 28),
                    children: hijos,
                  );
                },
              ),
            ),
          ),

          // Barra de búsqueda + filtros (overlay superior)
          SafeArea(
            bottom: false,
            child: Padding(
              padding: const EdgeInsets.fromLTRB(16, 10, 16, 0),
              child: Column(
                children: [
                  _BarraBusqueda(
                    onBuscar: _abrirBuscar,
                    label: _labelBusqueda,
                    subtitulo: _subtituloBusqueda,
                    onClear: _limpiarBusqueda,
                  ),
                  const SizedBox(height: 10),
                  _FiltrosDeporte(
                    seleccion: _filtro,
                    soloClubes: _soloClubes,
                    onSeleccion: _cambiarFiltro,
                    onClubes: _activarClubes,
                    onAcademias: () => Navigator.of(context).push(
                        MaterialPageRoute(
                            builder: (_) => const AcademiasScreen())),
                  ),
                  // Feedback mientras la app trae canchas reales cerca (Places).
                  ListenableBuilder(
                    listenable: appState,
                    builder: (_, __) => appState.descubriendo
                        ? const Padding(
                            padding: EdgeInsets.only(top: 10),
                            child: _BuscandoCerca(),
                          )
                        : const SizedBox.shrink(),
                  ),
                ],
              ),
            ),
          ),

          // Botón "Mapa" (estilo Airbnb): píldora oscura centrada abajo que
          // abre el mapa con los pines de la lista. El Maps SDK nativo es
          // GRATIS (no consume cuota de Google).
          Positioned(
            left: 0,
            right: 0,
            bottom: 32,
            child: ListenableBuilder(
              listenable: appState,
              builder: (context, _) {
                final clubs = _clubs();
                final centro = _centroBusqueda;
                if (clubs.isEmpty || centro == null) {
                  return const SizedBox.shrink();
                }
                return Center(
                  child: Material(
                    elevation: 6,
                    color: tinta,
                    borderRadius: BorderRadius.circular(999),
                    child: InkWell(
                      borderRadius: BorderRadius.circular(999),
                      onTap: () => Navigator.of(context).push(
                        MaterialPageRoute(
                          builder: (_) => MapaCanchasScreen(
                            clubs: _clubs(todosLosDeportes: true),
                            centro: centro,
                            titulo: _labelBusqueda,
                            filtroInicial: _soloClubes ? null : _filtro,
                            // Tras una búsqueda guiada, el mapa abre con los
                            // chips de ATRIBUTOS (el deporte ya se eligió).
                            atributosInicial: _busquedaHecha,
                          ),
                        ),
                      ),
                      child: const Padding(
                        padding: EdgeInsets.symmetric(
                            horizontal: 18, vertical: 12),
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Text('Mapa',
                                style: TextStyle(
                                    color: Colors.white,
                                    fontWeight: FontWeight.w800,
                                    fontSize: 14.5)),
                            SizedBox(width: 7),
                            Icon(Icons.map_outlined,
                                color: Colors.white, size: 18),
                          ],
                        ),
                      ),
                    ),
                  ),
                );
              },
            ),
          ),

          // Botón "mi ubicación": re-identifica la zona y reordena la lista.
          Positioned(
            right: 16,
            bottom: 32,
            child: Material(
              elevation: 4,
              shape: const CircleBorder(),
              color: Theme.of(context).colorScheme.surface,
              child: InkWell(
                customBorder: const CircleBorder(),
                onTap: _reubicar,
                child: Padding(
                  padding: const EdgeInsets.all(12),
                  child: _ubicando
                      ? SizedBox(
                          width: 22,
                          height: 22,
                          child: CircularProgressIndicator(
                              strokeWidth: 2,
                              color: Theme.of(context).colorScheme.primary))
                      : Icon(Icons.my_location,
                          color: Theme.of(context).colorScheme.primary),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _BarraBusqueda extends StatelessWidget {
  final VoidCallback onBuscar;
  final VoidCallback onClear;
  final String? label;
  final String? subtitulo; // "⚽ Fútbol · Hoy · 19:00" (búsqueda guiada)
  const _BarraBusqueda({
    required this.onBuscar,
    required this.onClear,
    this.label,
    this.subtitulo,
  });

  @override
  Widget build(BuildContext context) {
    final buscando = label != null;
    final cs = Theme.of(context).colorScheme;
    // El acceso al perfil vive en la pestaña "Perfil" de la barra inferior;
    // por eso el buscador ya no lleva avatar (se evita el doble acceso).
    return Row(
      children: [
        Expanded(
          child: Material(
            elevation: 4,
            borderRadius: BorderRadius.circular(30),
            color: cs.surface,
            child: InkWell(
              onTap: onBuscar,
              borderRadius: BorderRadius.circular(30),
              child: Padding(
                padding:
                    const EdgeInsets.symmetric(horizontal: 18, vertical: 12),
                child: Row(
                  children: [
                    const Icon(Icons.search, color: coral),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Text(
                            buscando ? label! : kBrandTaglineShort,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(
                                fontWeight: FontWeight.w700, fontSize: 15),
                          ),
                          Text(
                            subtitulo ??
                                (buscando
                                    ? 'Canchas cerca de tu zona'
                                    : 'Fútbol · Tenis · Clubes cerca de ti'),
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(
                                color: textoTenue, fontSize: 12),
                          ),
                        ],
                      ),
                    ),
                    if (buscando)
                      GestureDetector(
                        onTap: onClear,
                        child: const Icon(Icons.close, color: Colors.grey),
                      ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ],
    );
  }
}

/// Píldora de "cargando" mientras se traen canchas reales cerca del usuario.
/// Da feedback claro (estilo Airbnb) para que la espera no confunda.
class _BuscandoCerca extends StatelessWidget {
  const _BuscandoCerca();

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.centerLeft,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        decoration: BoxDecoration(
          color: Theme.of(context).colorScheme.surface,
          borderRadius: BorderRadius.circular(999),
          boxShadow: const [
            BoxShadow(color: Colors.black12, blurRadius: 8, offset: Offset(0, 2)),
          ],
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            SizedBox(
              width: 16,
              height: 16,
              child: CircularProgressIndicator(
                  strokeWidth: 2,
                  color: Theme.of(context).colorScheme.primary),
            ),
            const SizedBox(width: 10),
            const Text('Buscando canchas cerca de ti…',
                style: TextStyle(fontWeight: FontWeight.w600, fontSize: 13)),
          ],
        ),
      ),
    );
  }
}

/// Estado de la lista cuando no hay ubicación (permiso denegado / GPS off):
/// invita a activarla con un toque.
class _SinUbicacion extends StatelessWidget {
  const _SinUbicacion({required this.onUsar});
  final VoidCallback onUsar;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(28),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.location_off, size: 56, color: textoTenue),
            const SizedBox(height: 14),
            const Text('Activa tu ubicación',
                style: TextStyle(fontWeight: FontWeight.w800, fontSize: 18)),
            const SizedBox(height: 6),
            const Text(
                'La usamos para mostrarte las canchas más cercanas. También '
                'puedes buscar una zona a mano.',
                textAlign: TextAlign.center,
                style: TextStyle(color: textoTenue)),
            const SizedBox(height: 18),
            FilledButton.icon(
              style: FilledButton.styleFrom(
                  backgroundColor: lima,
                  padding:
                      const EdgeInsets.symmetric(horizontal: 20, vertical: 12)),
              onPressed: onUsar,
              icon: const Icon(Icons.my_location),
              label: const Text('Usar mi ubicación'),
            ),
          ],
        ),
      ),
    );
  }
}

/// Acceso a ACADEMIAS desde la home (buscar clases por deporte cerca de ti).
/// Tarjeta blanca estilo Airbnb con ícono de escuela.
/// Banner SLIM del Circuito Pichangol en Explorar: puente discreto al ranking y
/// los retos desde la home (descubrimiento). Estilo Airbnb (tinte lima suave).
class _CircuitoBannerExplorar extends StatelessWidget {
  const _CircuitoBannerExplorar({required this.onTap});
  final VoidCallback onTap;
  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 4),
      child: Material(
        color: limaSuave,
        borderRadius: BorderRadius.circular(14),
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(14),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 11),
            child: Row(
              children: [
                const Icon(Icons.emoji_events, color: bosque, size: 20),
                const SizedBox(width: 10),
                const Expanded(
                  child: Text(
                      'Liga de tenis Pichangol · ranking de tu ciudad y retos',
                      style: TextStyle(
                          color: bosque,
                          fontWeight: FontWeight.w700,
                          fontSize: 13)),
                ),
                const Icon(Icons.chevron_right, color: bosque),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// Chip compacto del selector de orden (Cerca / Precio), estilo Airbnb.
class _OrdenChip extends StatelessWidget {
  const _OrdenChip({
    required this.texto,
    required this.icono,
    required this.activo,
    required this.onTap,
  });
  final String texto;
  final IconData icono;
  final bool activo;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final color = activo ? cs.primary : textoTenueDe(context);
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(999),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 11, vertical: 6),
        decoration: BoxDecoration(
          color: activo ? cs.primary.withOpacity(0.12) : Colors.transparent,
          borderRadius: BorderRadius.circular(999),
          border: Border.all(
              color: activo ? cs.primary : const Color(0xFFE4E4E4)),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icono, size: 14, color: color),
            const SizedBox(width: 4),
            Text(texto,
                style: TextStyle(
                    fontSize: 12.5, fontWeight: FontWeight.w700, color: color)),
          ],
        ),
      ),
    );
  }
}

class _FiltrosDeporte extends StatelessWidget {
  final Deporte? seleccion;
  final bool soloClubes;
  final ValueChanged<Deporte?> onSeleccion;
  final VoidCallback onClubes;
  final VoidCallback onAcademias; // acceso a Academias como un chip más
  const _FiltrosDeporte({
    required this.seleccion,
    required this.soloClubes,
    required this.onSeleccion,
    required this.onClubes,
    required this.onAcademias,
  });

  @override
  Widget build(BuildContext context) {
    // Píldora estilo Airbnb: pastilla blanca con borde gris muy suave y un
    // relieve leve (sombra). Al seleccionar NO se pone marco negro: se rellena
    // de gris plomo (como el "Todo" de Airbnb) y el texto va en negrita.
    Widget chip(String emoji, String texto,
        {required bool activo, required VoidCallback onTap}) {
      return Padding(
        padding: const EdgeInsets.only(right: 10),
        child: GestureDetector(
          onTap: onTap,
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 160),
            padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 12),
            decoration: BoxDecoration(
              color: activo ? const Color(0xFFEBEBEB) : Colors.white,
              borderRadius: BorderRadius.circular(30),
              border: Border.all(
                color: activo ? const Color(0xFFD6D6D6) : const Color(0xFFE4E4E4),
                width: 1,
              ),
              boxShadow: [
                BoxShadow(
                  color: Colors.black.withOpacity(0.06),
                  blurRadius: 6,
                  offset: const Offset(0, 2),
                ),
              ],
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(emoji, style: const TextStyle(fontSize: 17)),
                const SizedBox(width: 8),
                Text(
                  texto,
                  style: TextStyle(
                    color: const Color(0xFF222222),
                    fontWeight: activo ? FontWeight.w700 : FontWeight.w500,
                    fontSize: 15,
                    letterSpacing: -0.1,
                  ),
                ),
              ],
            ),
          ),
        ),
      );
    }

    // En pantallas anchas (tablet/horizontal) los chips van CENTRADOS; si no
    // caben (móvil angosto), scrollean desde la izquierda como siempre.
    return LayoutBuilder(builder: (context, cons) {
      return SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        child: ConstrainedBox(
          constraints: BoxConstraints(minWidth: cons.maxWidth),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              chip('🏟️', 'Todos',
                  activo: !soloClubes && seleccion == null,
                  onTap: () => onSeleccion(null)),
              chip(emojiDeporte(Deporte.futbol), 'Fútbol',
                  activo: !soloClubes && seleccion == Deporte.futbol,
                  onTap: () => onSeleccion(Deporte.futbol)),
              chip(emojiDeporte(Deporte.tenis), 'Tenis',
                  activo: !soloClubes && seleccion == Deporte.tenis,
                  onTap: () => onSeleccion(Deporte.tenis)),
              chip(emojiDeporte(Deporte.basquet), 'Básquet',
                  activo: !soloClubes && seleccion == Deporte.basquet,
                  onTap: () => onSeleccion(Deporte.basquet)),
              chip(emojiDeporte(Deporte.voley), 'Vóley',
                  activo: !soloClubes && seleccion == Deporte.voley,
                  onTap: () => onSeleccion(Deporte.voley)),
              chip(emojiDeporte(Deporte.natacion), 'Natación',
                  activo: !soloClubes && seleccion == Deporte.natacion,
                  onTap: () => onSeleccion(Deporte.natacion)),
              chip('🏛️', 'Clubes', activo: soloClubes, onTap: onClubes),
              // Acceso (no filtro): abre la pantalla de Academias.
              chip('🎓', 'Academias', activo: false, onTap: onAcademias),
            ],
          ),
        ),
      );
    });
  }
}

/// Encabezado de sección de la lista (por deporte o "Clubes"): ícono + título +
/// contador.
class _SeccionHeader extends StatelessWidget {
  const _SeccionHeader(this.titulo, this.n, this.color, this.icono);
  final String titulo;
  final int n;
  final Color color;
  final IconData icono;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return Padding(
      padding: const EdgeInsets.only(top: 20, bottom: 2),
      child: Row(
        children: [
          Icon(icono, size: 20, color: color),
          const SizedBox(width: 8),
          Text(titulo,
              style: t.titleMedium?.copyWith(fontWeight: FontWeight.w700)),
          const SizedBox(width: 8),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
            decoration: BoxDecoration(
                color: color.withOpacity(0.12),
                borderRadius: BorderRadius.circular(999)),
            child: Text('$n',
                style: TextStyle(
                    color: color, fontWeight: FontWeight.w700, fontSize: 12)),
          ),
        ],
      ),
    );
  }
}
