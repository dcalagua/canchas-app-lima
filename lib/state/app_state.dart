import 'dart:convert';
import 'dart:math' as math;
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../data/academias_repo.dart';
import '../data/campeonatos_repo.dart';
import '../data/canchas_repo.dart';
import '../data/invitaciones_repo.dart';
import '../data/matriculas_repo.dart';
import '../data/mensajes_repo.dart';
import '../data/perfiles_repo.dart';
import '../data/bloqueos_repo.dart';
import '../data/referidos_repo.dart';
import '../data/resenas_repo.dart';
import '../data/reservas_repo.dart';
import '../data/sample_data.dart';
import '../data/verificacion_repo.dart';
import '../models/academia.dart';
import '../models/campeonato.dart';
import '../models/club.dart';
import '../models/invitacion.dart';
import '../models/models.dart';
import '../models/negocio.dart';
import '../models/resena.dart';
import '../models/temporada.dart';
import '../models/usuario.dart';
import '../services/auth_service.dart';
import '../services/circuito_service.dart';
import '../services/pagos_service.dart';
import '../services/retos_service.dart';
import '../services/push_service.dart';
import '../services/places_service.dart';
import '../services/verificacion_service.dart';
import '../services/growth_service.dart';
import '../services/propiedad_service.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart';
import '../config/pais.dart';
import '../utils/moneda.dart';

/// Instancia única del estado para toda la app (sin paquetes extra de DI).
final AppState appState = AppState();

/// Estado de la app. Sin backend todavía: arranca de [SampleData] y muta en memoria.
/// Pensado para Fase 1 (panel del dueño) + demo en la cancha.
class AppState extends ChangeNotifier {
  bool sesionIniciada = false; // sesión del DUEÑO (panel del club)
  String nombreClub = SampleData.clubActivo;

  // Sesión del JUGADOR (Google). Navegar/buscar es libre; reservar exige login.
  Usuario? usuario;
  bool get logueado => usuario != null;

  // ── Perfiles públicos (nombre/foto que la persona muestra) ────────────────
  // Cache email→{nombre, foto_url}. Lo llena `cargarPerfiles`; lo usan el chat y
  // donde se muestre a otra persona (nombre y foto en vez del correo).
  final Map<String, Map<String, dynamic>> _perfiles = {};

  /// Nombre a mostrar de un correo: el de su perfil si existe (no vacío), o null.
  String? nombreMostrableDe(String? email) {
    final e = (email ?? '').trim().toLowerCase();
    final n = (_perfiles[e]?['nombre'] ?? '').toString().trim();
    return n.isEmpty ? null : n;
  }

  /// Foto a mostrar de un correo (de su perfil), o null.
  String? fotoDe(String? email) {
    final e = (email ?? '').trim().toLowerCase();
    final f = (_perfiles[e]?['foto_url'] ?? '').toString().trim();
    return f.isEmpty ? null : f;
  }

  /// Celular (WhatsApp) de un correo, o null si no lo puso.
  String? celularDe(String? email) {
    final e = (email ?? '').trim().toLowerCase();
    final c = (_perfiles[e]?['celular'] ?? '').toString().trim();
    return c.isEmpty ? null : c;
  }

  /// Mi propio celular guardado (del perfil), o '' si no tengo.
  String get miCelular =>
      (_perfiles[(usuario?.email ?? '').toLowerCase()]?['celular'] ?? '')
          .toString();

  // ── Contactos guardados (tipo WhatsApp): correos que el usuario guardó ─────
  final Set<String> _contactos = {};
  static const _kContactos = 'contactos_json';

  /// Correos guardados como contacto (para chatear rápido).
  List<String> get contactos => _contactos.toList();
  bool esContacto(String? email) =>
      _contactos.contains((email ?? '').trim().toLowerCase());

  Future<void> _persistirContactos() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(_kContactos, jsonEncode(_contactos.toList()));
    } catch (_) {}
  }

  /// Guarda un contacto (y cachea su perfil para mostrar nombre/foto).
  Future<void> guardarContacto(String email, {Map<String, dynamic>? perfil}) async {
    final e = email.trim().toLowerCase();
    if (e.isEmpty || e == (usuario?.email ?? '').toLowerCase()) return;
    _contactos.add(e);
    if (perfil != null) _perfiles[e] = perfil;
    notifyListeners();
    await _persistirContactos();
  }

  Future<void> quitarContacto(String email) async {
    _contactos.remove(email.trim().toLowerCase());
    notifyListeners();
    await _persistirContactos();
  }

  /// Trae de Supabase los perfiles de estos correos y los cachea (best-effort).
  Future<void> cargarPerfiles(List<String> emails) async {
    final faltan = emails
        .map((e) => e.trim().toLowerCase())
        .where((e) => e.isNotEmpty && !_perfiles.containsKey(e))
        .toList();
    if (faltan.isEmpty) return;
    final res = await PerfilesRepo.obtenerVarios(faltan);
    if (res.isEmpty) return;
    _perfiles.addAll(res);
    notifyListeners();
  }

  /// Sincroniza MI perfil público al iniciar sesión: si ya tengo un perfil
  /// guardado (nombre/foto que elegí antes, incluso en otro dispositivo), lo
  /// aplico; si no, subo mi nombre/foto de Google como base. Best-effort.
  Future<void> _sincronizarMiPerfil() async {
    final u = usuario;
    if (u == null) return;
    final mio = await PerfilesRepo.obtener(u.email);
    if (mio != null && (mio['nombre'] ?? '').toString().trim().isNotEmpty) {
      final nombre = mio['nombre'].toString().trim();
      final foto = (mio['foto_url'] ?? '').toString().trim();
      _perfiles[u.email.toLowerCase()] = mio;
      usuario = Usuario(
          nombre: nombre,
          email: u.email,
          fotoUrl: foto.isNotEmpty ? foto : u.fotoUrl);
      await _persistirUsuario();
      notifyListeners();
    } else {
      // Aún no tengo perfil: subo el de Google como base.
      await PerfilesRepo.guardar(
          email: u.email, nombre: u.nombre, fotoUrl: u.fotoUrl);
      _perfiles[u.email.toLowerCase()] = {
        'email': u.email.toLowerCase(),
        'nombre': u.nombre,
        'foto_url': u.fotoUrl,
      };
    }
  }

  /// El usuario cambia su nombre (y opcionalmente su celular de WhatsApp) con el
  /// que se muestra en el chat, ranking, etc. Actualiza la sesión local + su
  /// perfil público. Devuelve true.
  Future<bool> actualizarMiNombre(String nuevo, {String? celular}) async {
    final u = usuario;
    final n = nuevo.trim();
    if (u == null || n.isEmpty) return false;
    final cel = celular ?? miCelular;
    usuario = Usuario(nombre: n, email: u.email, fotoUrl: u.fotoUrl);
    _perfiles[u.email.toLowerCase()] = {
      'email': u.email.toLowerCase(),
      'nombre': n,
      'foto_url': u.fotoUrl,
      'celular': cel,
    };
    await _persistirUsuario();
    notifyListeners();
    await PerfilesRepo.guardar(
        email: u.email, nombre: n, fotoUrl: u.fotoUrl, celular: cel);
    return true;
  }

  /// El usuario sube una foto PROPIA (galería/cámara). La sube a Storage,
  /// actualiza la sesión + su perfil público. Devuelve true si se pudo.
  Future<bool> actualizarMiFoto(Uint8List bytes) async {
    final u = usuario;
    if (u == null) return false;
    final url = await PerfilesRepo.subirFoto(u.email, bytes);
    if (url == null) return false;
    final cel = miCelular;
    usuario = Usuario(nombre: u.nombre, email: u.email, fotoUrl: url);
    _perfiles[u.email.toLowerCase()] = {
      'email': u.email.toLowerCase(),
      'nombre': u.nombre,
      'foto_url': url,
      'celular': cel,
    };
    await _persistirUsuario();
    notifyListeners();
    await PerfilesRepo.guardar(
        email: u.email, nombre: u.nombre, fotoUrl: url, celular: cel);
    return true;
  }

  // Reservas y agenda REALES: arrancan vacías. Se llenan con lo que llega de
  // Supabase (cargarReservasRemotas) y con las reservas que hacen los jugadores.
  // (Antes se sembraban datos de demostración; el producto ya no los usa.)
  final List<Reserva> reservas = [];
  final List<BloqueHorario> agenda = [];
  final List<Reserva> misReservas = []; // reservas del jugador logueado
  final List<Cancha> canchasExtra = []; // canchas registradas en este dispositivo
  final List<Cancha> canchasRemotas = []; // canchas traídas de Supabase
  final List<Cancha> canchasDescubiertas = []; // reales de Google Places (sin registrar)
  // IDs de canchas que el dueño eliminó: se respetan SIEMPRE, aunque Supabase
  // vuelva a devolverlas (borrado durable en el dispositivo).
  final Set<String> canchasEliminadas = {};

  // ── FAVORITOS del jugador (ids de club) ───────────────────────────────────
  final Set<String> favoritos = {};
  bool esFavorito(String clubId) => favoritos.contains(clubId);
  void alternarFavorito(String clubId) {
    if (clubId.isEmpty) return;
    if (!favoritos.remove(clubId)) favoritos.add(clubId);
    notifyListeners();
    _persistirDatos();
  }

  // ── Academias (Fase 1) ────────────────────────────────────────────────────
  final List<Academia> academias = [];

  /// Ids de academias con una edición LOCAL que aún NO se confirmó en la nube
  /// (Supabase falló, p. ej. RLS). Mientras un id esté aquí, la recarga NO pisa
  /// la versión local con la remota (vieja) y se reintenta subirla. Se persiste
  /// para que la edición no se pierda ni tras reiniciar la app.
  final Set<String> _academiasPendientesNube = {};
  final List<Alumno> alumnos = [];
  final List<Cuota> cuotas = [];
  final List<Asistencia> asistencias = [];
  final List<Invitacion> invitaciones = []; // invitaciones profe → alumno

  // Última vez que el usuario abrió cada hilo de chat (hilo → ISO). Sirve para
  // el contador de "no leídos" (Etapa A del chat).
  final Map<String, String> chatLecturas = {};

  // ── Campeonatos de academias ──────────────────────────────────────────────
  final List<Campeonato> campeonatos = [];
  bool descubriendo = false; // true mientras se traen canchas cercanas (feedback UI)

  /// Copia runtime de los clubes sembrados (SampleData.sembradas). Se enriquece
  /// con fotos reales de Google en `enriquecerSembradas()` sin tocar el const.
  final List<Cancha> _sembradas = List.of(SampleData.sembradas);

  /// Trae las FOTOS reales de Google para los clubes sembrados (que no pasan por
  /// el descubrimiento normal) y las inyecta. Best-effort: si Places no
  /// responde, los sembrados quedan con su placeholder.
  Future<void> enriquecerSembradas() async {
    if (!PlacesService.disponible) return;
    var cambio = false;
    for (var i = 0; i < _sembradas.length; i++) {
      final s = _sembradas[i];
      if (s.fotos.isNotEmpty) continue; // ya tiene
      // Consulta = nombre sin el sufijo de sede (tras "–"/"-").
      final query = s.nombre.split(RegExp(r'[–-]')).first.trim();
      try {
        final fotos = await PlacesService.fotosDeLugar(query, s.ubicacion);
        if (fotos.isNotEmpty) {
          _sembradas[i] = s.copyWith(fotos: fotos, fotoUrl: fotos.first);
          cambio = true;
        }
      } catch (_) {
        // sin fotos: se queda con el placeholder
      }
    }
    if (cambio) notifyListeners();
  }

  // ── Academias (Fase 1) ────────────────────────────────────────────────────

  /// La academia del profe logueado (por correo), si existe.
  Academia? get miAcademia {
    final email = usuario?.email ?? '';
    if (email.isEmpty) return null;
    for (final a in academias) {
      if (a.dueno == email) return a;
    }
    return null;
  }

  /// Crea o actualiza una academia (upsert por id). Persiste local + nube
  /// (Supabase) para que sobreviva a reinstalar el APK.
  /// Crea o actualiza la academia (local + nube). Devuelve true si además quedó
  /// confirmada en la NUBE; false si solo se guardó local (Supabase falló). En
  /// ese caso el id queda "pendiente" y se reintenta al recargar, sin perder la
  /// edición ni dejar que la versión vieja de la nube la revierta.
  Future<bool> guardarAcademia(Academia a) async {
    // Modelo piloto: UNA academia por dueño. Si ya existe una del mismo dueño con
    // OTRO id (típico: se creó una nueva porque la nube aún no había cargado tras
    // reinstalar), NO duplicamos: reusamos el id existente y la actualizamos. Es
    // la 2.ª barrera contra "academias duplicadas".
    var academia = a;
    final dueno = a.dueno.trim().toLowerCase();
    if (dueno.isNotEmpty) {
      final j = academias.indexWhere(
          (x) => x.id != a.id && x.dueno.trim().toLowerCase() == dueno);
      if (j >= 0) academia = a.copyWith(id: academias[j].id);
    }
    final i = academias.indexWhere((x) => x.id == academia.id);
    if (i >= 0) {
      academias[i] = academia;
    } else {
      academias.add(academia);
    }
    notifyListeners();
    _persistirDatos();
    // Nube: si falla, marca el id como pendiente para no perder la edición ni
    // que la recarga la pise con la versión vieja (comparte + sobrevive reinstalar).
    final ok = await AcademiasRepo.guardar(academia);
    if (ok) {
      _academiasPendientesNube.remove(academia.id);
    } else {
      _academiasPendientesNube.add(academia.id);
    }
    _persistirDatos();
    return ok;
  }

  // ── Circuito / Ranking interno (Fase 0) ────────────────────────────────────
  /// Registra un partido del ranking interno de una academia y lo persiste
  /// (local + nube, embebido en la academia).
  Future<void> registrarPartido(
      String academiaId, PartidoRanking partido) async {
    final i = academias.indexWhere((a) => a.id == academiaId);
    if (i < 0) return;
    final actualizada =
        academias[i].copyWith(partidos: [...academias[i].partidos, partido]);
    await guardarAcademia(actualizada);
    await _refrescarLandingAcademia(actualizada);
  }

  /// Borra un partido del ranking (corregir un error de carga).
  Future<void> eliminarPartido(String academiaId, String partidoId) async {
    final i = academias.indexWhere((a) => a.id == academiaId);
    if (i < 0) return;
    final nuevos =
        academias[i].partidos.where((p) => p.id != partidoId).toList();
    final actualizada = academias[i].copyWith(partidos: nuevos);
    await guardarAcademia(actualizada);
    await _refrescarLandingAcademia(actualizada);
  }

  /// Fija (o limpia si viene vacía) la categoría de ranking de un alumno.
  Future<void> setCategoriaAlumno(
      String academiaId, String alumnoId, String categoria) async {
    final i = academias.indexWhere((a) => a.id == academiaId);
    if (i < 0) return;
    final cats = Map<String, String>.from(academias[i].categorias);
    if (categoria.trim().isEmpty) {
      cats.remove(alumnoId);
    } else {
      cats[alumnoId] = categoria.trim();
    }
    final actualizada = academias[i].copyWith(categorias: cats);
    await guardarAcademia(actualizada);
    await _refrescarLandingAcademia(actualizada);
  }

  /// Re-publica la landing PROPIA de la academia (id = ac.id) para que el
  /// ranking embebido en la web se mantenga fresco. Las landings unificadas
  /// (mixto/club) se regeneran desde Servicios para no perder las canchas
  /// combinadas. Best-effort: no bloquea si falla la red.
  Future<void> _refrescarLandingAcademia(Academia ac) async {
    final url = ac.landingUrl.trim();
    if (url.isEmpty || !url.endsWith('/l/${ac.id}')) return;
    await PagosService.generarLanding(ac.id, _landingDatos(ac));
  }

  // ── Retos P2P (se pliegan al ranking global por identidad = correo) ────────
  List<Map<String, dynamic>> _retosResultados = const [];

  /// Trae del backend los retos JUGADOS para plegarlos al ranking (best-effort).
  Future<void> cargarRetosResultados() async {
    final res = await RetosService.resultados();
    _retosResultados = res;
    notifyListeners();
  }

  // Retos que REQUIEREN mi atención (badge del perfil, sin push): retos
  // recibidos pendientes de responder + retos aceptados (de ambos lados)
  // pendientes de reportar el resultado. Es el aviso in-app del loop P2P.
  int _retosPendientes = 0;
  int get retosPendientes => _retosPendientes;

  /// Cuenta los retos que requieren acción del usuario y actualiza el badge.
  /// Best-effort: si no hay backend o sesión, deja el contador en 0.
  Future<void> cargarRetosPendientes() async {
    final email = (usuario?.email ?? '').toLowerCase().trim();
    if (email.isEmpty) {
      if (_retosPendientes != 0) {
        _retosPendientes = 0;
        notifyListeners();
      }
      return;
    }
    final r = await RetosService.mios(email);
    if (r == null) return; // sin red: conserva el último valor conocido
    final recibidos = (r['recibidos'] as List?) ?? const [];
    final enviados = (r['enviados'] as List?) ?? const [];
    var n = 0;
    for (final e in recibidos) {
      final estado = ((e as Map)['estado'] ?? '').toString();
      if (estado == 'pendiente' || estado == 'aceptado') n++;
    }
    for (final e in enviados) {
      final estado = ((e as Map)['estado'] ?? '').toString();
      if (estado == 'aceptado') n++; // aceptado por el rival: falta reportar
    }
    if (_retosPendientes != n) {
      _retosPendientes = n;
      notifyListeners();
    }
  }

  Deporte? _deporteDe(dynamic name) {
    final n = (name ?? '').toString();
    for (final d in Deporte.values) {
      if (d.name == n) return d;
    }
    return null;
  }

  // ── Circuito: mi perfil "disponible para retar" (onboarding al ranking) ────
  Map<String, dynamic>? _miPerfilCircuito;

  /// ¿Ya me declaré disponible en el circuito?
  bool get estoyEnCircuito => _miPerfilCircuito != null;

  /// ¿Hay circuito de TENIS vivo/relevante para mostrar sus accesos? (hay
  /// ranking de raqueta con datos o el usuario ya se unió). El circuito es una
  /// capa de tenis; en fútbol NO se muestra.
  bool get hayCircuitoTenis =>
      estoyEnCircuito || deportesConRanking.any((d) => d.esRaqueta);

  /// ¿El usuario YA usa el circuito? (para mostrar sus accesos en Perfil sin
  /// ensuciar el menú de quien solo reserva/juega fútbol).
  bool get usaCircuito =>
      estoyEnCircuito || proActivo || _retosPendientes > 0;

  /// Mi perfil de circuito (deporte/zona/categoría) o null si no me uní.
  Map<String, dynamic>? get miPerfilCircuito => _miPerfilCircuito;

  /// Trae del backend mi perfil de circuito (para saber si ya me uní).
  Future<void> cargarMiPerfilCircuito() async {
    final email = (usuario?.email ?? '').toLowerCase().trim();
    if (email.isEmpty) {
      if (_miPerfilCircuito != null) {
        _miPerfilCircuito = null;
        notifyListeners();
      }
      return;
    }
    _miPerfilCircuito = await CircuitoService.perfil(email);
    notifyListeners();
  }

  /// Me declaro disponible para retar (crea/actualiza mi perfil de circuito).
  Future<bool> unirseCircuito({
    required Deporte deporte,
    String zona = '',
    String categoria = '',
  }) async {
    final u = usuario;
    if (u == null) return false;
    final j = await CircuitoService.unirse(
      email: u.email,
      nombre: u.nombre,
      deporte: deporte.name,
      zona: zona,
      categoria: categoria,
    );
    if (j == null) return false;
    _miPerfilCircuito = j;
    notifyListeners();
    return true;
  }

  /// Empuja a la torre de control el ranking global cruzado (top por deporte +
  /// campeón de la temporada anterior + temporada actual). Como el ranking se
  /// computa en el APK (academias de Supabase), la torre no lo puede calcular:
  /// se lo enviamos cuando alguien abre el Ranking Global. Best-effort.
  Future<void> publicarRankingSnapshot() async {
    final deportes = deportesConRanking;
    if (deportes.isEmpty) return;
    final ahora = DateTime.now();
    final tempActual = Temporada.de(ahora);
    final tempAnterior = tempActual.anterior;
    final out = <Map<String, dynamic>>[];
    for (final d in deportes) {
      final tabla = rankingGlobal(deporte: d).take(8).toList();
      if (tabla.isEmpty) continue;
      final campeon = campeonGlobal(deporte: d, temporada: tempAnterior);
      out.add({
        'deporte': d.name,
        'temporada': tempActual.id,
        'top': [
          for (final f in tabla)
            {
              'nombre': f.nombre,
              'puntos': f.puntos,
              'pg': f.pg,
              'pp': f.pp,
              'academia': f.academiaNombre,
              'pro': esProEmail(f.emailIdentidad),
            }
        ],
        'campeon': campeon == null
            ? null
            : {'nombre': campeon.nombre, 'puntos': campeon.puntos},
      });
    }
    await CircuitoService.publicarRanking(
        deportes: out, por: (usuario?.email ?? '').toLowerCase());
  }

  /// Me retiro del directorio de disponibles.
  Future<bool> salirCircuito() async {
    final email = usuario?.email ?? '';
    if (email.isEmpty) return false;
    final ok = await CircuitoService.salir(email);
    if (ok) {
      _miPerfilCircuito = null;
      notifyListeners();
    }
    return ok;
  }

  /// Fecha de un reto jugado para ubicarlo en su temporada: `jugado_en` (cuándo
  /// se reportó el resultado) y, si el backend no la trae, `creado_en`.
  DateTime _fechaReto(Map<String, dynamic> r) {
    final j = (r['jugado_en'] ?? r['creado_en'] ?? '').toString();
    return DateTime.tryParse(j)?.toLocal() ?? DateTime.now();
  }

  /// El campeón (fila #1) del ranking global de una temporada, o null si esa
  /// temporada no tuvo partidos. Sirve para coronar cuando la temporada cerró.
  RankingGlobalFila? campeonGlobal(
      {required Deporte deporte, required Temporada temporada, String? zona}) {
    final t = rankingGlobal(deporte: deporte, temporada: temporada, zona: zona);
    return t.isEmpty ? null : t.first;
  }

  /// Temporadas que tienen al menos un partido/reto del [deporte] (para el
  /// selector). Incluye siempre la temporada ACTUAL aunque esté vacía (para
  /// invitar a empezar a jugarla). Más reciente primero.
  List<Temporada> temporadasConDatos(Deporte deporte) {
    final ahora = DateTime.now();
    final actual = Temporada.de(ahora);
    final set = <String, Temporada>{actual.id: actual};
    for (final a in academias) {
      if (a.deporte != deporte) continue;
      for (final p in a.partidos) {
        final t = Temporada.de(p.fecha);
        set[t.id] = t;
      }
    }
    for (final r in _retosResultados) {
      if (_deporteDe(r['deporte']) != deporte) continue;
      final t = Temporada.de(_fechaReto(r));
      set[t.id] = t;
    }
    final l = set.values.toList()
      ..sort((x, y) => y.inicio.compareTo(x.inicio));
    return l;
  }

  /// Deportes con partidos de ranking (academias) o retos jugados.
  List<Deporte> get deportesConRanking {
    final s = <Deporte>{};
    for (final a in academias) {
      if (a.partidos.isNotEmpty) s.add(a.deporte);
    }
    for (final r in _retosResultados) {
      final d = _deporteDe(r['deporte']);
      if (d != null) s.add(d);
    }
    final l = s.toList()..sort((x, y) => x.index.compareTo(y.index));
    return l;
  }

  /// Categorías presentes en el ranking global de un deporte (para el filtro).
  List<String> categoriasGlobalDe(Deporte deporte) {
    final s = <String>{};
    for (final a in academias) {
      if (a.deporte != deporte) continue;
      s.addAll(a.categorias.values.where((c) => c.isNotEmpty));
    }
    final l = s.toList()..sort();
    return l;
  }

  /// Zonas/distritos con academias que tienen partidos, para el filtro del
  /// ranking global por ciudad. Solo cuentan las academias del [deporte].
  List<String> zonasGlobalDe(Deporte deporte) {
    final s = <String>{};
    for (final a in academias) {
      if (a.deporte != deporte || a.partidos.isEmpty) continue;
      if (a.zona.trim().isNotEmpty) s.add(a.zona.trim());
    }
    for (final r in _retosResultados) {
      if (_deporteDe(r['deporte']) != deporte) continue;
      final z = (r['zona'] ?? '').toString().trim();
      if (z.isNotEmpty) s.add(z);
    }
    final l = s.toList()..sort();
    return l;
  }

  /// RANKING GLOBAL Pichangol: agrega los partidos de TODAS las academias del
  /// [deporte] en una sola tabla, ordenada por puntos. Client-side (las
  /// academias ya vienen con sus partidos embebidos). DEDUPE POR IDENTIDAD: la
  /// misma persona (mismo correo) en varias academias es UNA sola fila con sus
  /// stats sumados. Los alumnos manuales (sin correo) no se dedupean.
  List<RankingGlobalFila> rankingGlobal(
      {Deporte? deporte, String? categoria, String? zona, Temporada? temporada}) {
    final agg = <String, _AggGlobal>{};
    for (final a in academias) {
      if (deporte != null && a.deporte != deporte) continue;
      if (zona != null && zona.isNotEmpty && a.zona.trim() != zona) continue;
      for (final p in a.partidos) {
        if (temporada != null && !temporada.contiene(p.fecha)) continue;
        for (final id in [p.jugadorAId, p.jugadorBId]) {
          if (id.isEmpty) continue;
          final cat = a.categoriaDe(id);
          if (categoria != null && categoria.isNotEmpty && cat != categoria) {
            continue;
          }
          final nombre = p.nombreDe(id);
          final email = p.emailDe(id).trim().toLowerCase();
          // Identidad: por correo (une academias) o por (academia, alumno).
          final key = email.isNotEmpty ? 'e:$email' : 'a:${a.id}|$id';
          final g = agg.putIfAbsent(
              key, () => _AggGlobal(deporte: a.deporte));
          g.pj++;
          if (p.ganadorId == id) {
            g.pg++;
          } else {
            g.pp++;
          }
          if (nombre.isNotEmpty) g.nombre = nombre;
          if (cat.isNotEmpty) g.categoria = cat;
          g.academiasIds.add(a.id);
          g.porAcademia[a.nombre] = (g.porAcademia[a.nombre] ?? 0) + 1;
        }
      }
    }
    // Pliega los RETOS jugados por identidad (correo). No tienen categoría, así
    // que solo cuentan cuando no se filtra por categoría.
    if (categoria == null || categoria.isEmpty) {
      for (final r in _retosResultados) {
        if (deporte != null && _deporteDe(r['deporte']) != deporte) continue;
        if (zona != null &&
            zona.isNotEmpty &&
            (r['zona'] ?? '').toString().trim() != zona) continue;
        if (temporada != null && !temporada.contiene(_fechaReto(r))) continue;
        final ganador =
            (r['ganador_email'] ?? '').toString().trim().toLowerCase();
        if (ganador.isEmpty) continue;
        for (final side in const ['retador', 'retado']) {
          final email = (r['${side}_email'] ?? '').toString().trim().toLowerCase();
          if (email.isEmpty) continue;
          final nombre = (r['${side}_nombre'] ?? '').toString();
          final g = agg.putIfAbsent(
              'e:$email',
              () => _AggGlobal(
                  deporte: deporte ?? (_deporteDe(r['deporte']) ?? Deporte.tenis)));
          g.pj++;
          if (ganador == email) {
            g.pg++;
          } else {
            g.pp++;
          }
          if (nombre.isNotEmpty) g.nombre = nombre;
          g.porAcademia['Retos'] = (g.porAcademia['Retos'] ?? 0) + 1;
        }
      }
    }

    final filas = <RankingGlobalFila>[];
    agg.forEach((key, g) {
      if (g.pj == 0) return;
      // Academia primaria = donde tiene más partidos.
      var primaria = '';
      var maxN = -1;
      g.porAcademia.forEach((n, c) {
        if (c > maxN) {
          maxN = c;
          primaria = n;
        }
      });
      filas.add(RankingGlobalFila(
        academiaId: '',
        academiaNombre: primaria,
        deporte: g.deporte,
        alumnoId: key,
        nombre: g.nombre,
        categoria: g.categoria,
        pj: g.pj,
        pg: g.pg,
        pp: g.pp,
        puntos: g.pg * Academia.puntosVictoria + g.pp * Academia.puntosDerrota,
        pct: g.pj == 0 ? 0 : g.pg / g.pj * 100,
        academias: g.academiasIds.length,
      ));
    });
    filas.sort((x, y) {
      if (y.puntos != x.puntos) return y.puntos.compareTo(x.puntos);
      if (y.pct != x.pct) return y.pct.compareTo(x.pct);
      return y.pg.compareTo(x.pg);
    });
    return filas;
  }

  /// Importa los resultados de un CAMPEONATO al ranking del circuito (y por ende
  /// al global). Cada partido jugado con ganador se vuelve un PartidoRanking con
  /// id determinista ('cmp_<campeonato>_<partido>'), así re-importar es idempotente
  /// y refleja ediciones/borrados. Denormaliza el correo del participante para la
  /// identidad global. Devuelve cuántos partidos se sumaron.
  Future<int> importarCampeonatoAlRanking(Campeonato c) async {
    final i = academias.indexWhere((a) => a.id == c.academiaId);
    if (i < 0) return 0;
    final academia = academias[i];
    final prefijo = 'cmp_${c.id}_';
    // Conserva la fecha de los ya importados (no reescribe la historia).
    final fechaPrevia = <String, DateTime>{
      for (final p in academia.partidos)
        if (p.id.startsWith(prefijo)) p.id: p.fecha
    };
    final part = {for (final p in c.participantes) p.id: p};
    final ahora = DateTime.now();
    final nuevos = <PartidoRanking>[];
    final cats = Map<String, String>.from(academia.categorias);
    for (final pt in c.partidos) {
      if (!pt.jugado) continue;
      final aId = pt.aId, bId = pt.bId, gid = pt.ganadorId;
      if (aId == null || bId == null || gid == null) continue; // bye/empate
      final pa = part[aId], pb = part[bId];
      if (pa == null || pb == null) continue;
      final id = '$prefijo${pt.id}';
      nuevos.add(PartidoRanking(
        id: id,
        fecha: fechaPrevia[id] ?? ahora,
        jugadorAId: aId,
        jugadorANombre: pa.nombre,
        jugadorAEmail: pa.email.trim().toLowerCase(),
        jugadorBId: bId,
        jugadorBNombre: pb.nombre,
        jugadorBEmail: pb.email.trim().toLowerCase(),
        ganadorId: gid,
        marcador: '${pt.marcadorA}-${pt.marcadorB}',
      ));
      if (c.categoria.isNotEmpty) {
        cats.putIfAbsent(aId, () => c.categoria);
        cats.putIfAbsent(bId, () => c.categoria);
      }
    }
    final resto =
        academia.partidos.where((p) => !p.id.startsWith(prefijo)).toList();
    final actualizada =
        academia.copyWith(partidos: [...resto, ...nuevos], categorias: cats);
    await guardarAcademia(actualizada);
    await _refrescarLandingAcademia(actualizada);
    return nuevos.length;
  }

  /// PERFIL GLOBAL de un jugador por su clave de identidad ([idKey] tal como la
  /// devuelve `rankingGlobal`: 'e:correo' o 'a:academiaId|alumnoId'). Consolida
  /// sus stats entre TODAS las academias, el desglose por academia y sus
  /// partidos recientes. Null si no tiene partidos.
  PerfilGlobalJugador? perfilGlobalDe(String idKey) {
    final email = idKey.startsWith('e:') ? idKey.substring(2) : '';
    var nombre = '', categoria = '';
    var pj = 0, pg = 0, pp = 0;
    final porAcad = <String, List<int>>{}; // academia -> [pj, pg, pp]
    final partidos = <PartidoConAcademia>[];

    bool esEl(Academia a, String playerId, String playerEmail) {
      if (email.isNotEmpty) return playerEmail.trim().toLowerCase() == email;
      return 'a:${a.id}|$playerId' == idKey;
    }

    for (final a in academias) {
      for (final p in a.partidos) {
        for (final id in [p.jugadorAId, p.jugadorBId]) {
          if (id.isEmpty) continue;
          if (!esEl(a, id, p.emailDe(id))) continue;
          final gano = p.ganadorId == id;
          pj++;
          if (gano) {
            pg++;
          } else {
            pp++;
          }
          final r = porAcad.putIfAbsent(a.nombre, () => [0, 0, 0]);
          r[0]++;
          if (gano) {
            r[1]++;
          } else {
            r[2]++;
          }
          final nom = p.nombreDe(id);
          if (nom.isNotEmpty) nombre = nom;
          final cat = a.categoriaDe(id);
          if (cat.isNotEmpty) categoria = cat;
          final rivalId = id == p.jugadorAId ? p.jugadorBId : p.jugadorAId;
          partidos.add(PartidoConAcademia(
              partido: p,
              academia: a.nombre,
              gano: gano,
              rival: p.nombreDe(rivalId)));
        }
      }
    }
    // Pliega los RETOS jugados de esta persona (solo identidad por correo).
    if (email.isNotEmpty) {
      for (final r in _retosResultados) {
        for (final side in const ['retador', 'retado']) {
          final e = (r['${side}_email'] ?? '').toString().trim().toLowerCase();
          if (e != email) continue;
          final otro = side == 'retador' ? 'retado' : 'retador';
          final rival = (r['${otro}_nombre'] ?? '').toString();
          final gano =
              (r['ganador_email'] ?? '').toString().trim().toLowerCase() == email;
          pj++;
          if (gano) {
            pg++;
          } else {
            pp++;
          }
          final rec = porAcad.putIfAbsent('Retos', () => [0, 0, 0]);
          rec[0]++;
          if (gano) {
            rec[1]++;
          } else {
            rec[2]++;
          }
          final nom = (r['${side}_nombre'] ?? '').toString();
          if (nom.isNotEmpty) nombre = nom;
          final rivalId = '${otro}_${r['id']}';
          partidos.add(PartidoConAcademia(
            partido: PartidoRanking(
              id: 'reto_${r['id']}',
              fecha: DateTime.tryParse((r['creado_en'] ?? '').toString()) ??
                  DateTime.now(),
              jugadorAId: email,
              jugadorANombre: nom,
              jugadorBId: rivalId,
              jugadorBNombre: rival,
              ganadorId: gano ? email : rivalId,
              marcador: (r['marcador'] ?? '').toString(),
            ),
            academia: 'Reto',
            gano: gano,
            rival: rival,
          ));
        }
      }
    }
    if (pj == 0) return null;
    partidos.sort((x, y) => y.partido.fecha.compareTo(x.partido.fecha));
    final porAcademia = porAcad.entries
        .map((e) => RegistroPorAcademia(
              academia: e.key,
              pj: e.value[0],
              pg: e.value[1],
              pp: e.value[2],
              puntos: e.value[1] * Academia.puntosVictoria +
                  e.value[2] * Academia.puntosDerrota,
            ))
        .toList()
      ..sort((a, b) => b.puntos.compareTo(a.puntos));
    return PerfilGlobalJugador(
      nombre: nombre,
      categoria: categoria,
      email: email,
      pj: pj,
      pg: pg,
      pp: pp,
      puntos:
          pg * Academia.puntosVictoria + pp * Academia.puntosDerrota,
      pct: pj == 0 ? 0 : pg / pj * 100,
      porAcademia: porAcademia,
      partidos: partidos,
    );
  }

  /// Al CONECTAR las redes (OAuth Meta en Servicios), auto-declara en la academia
  /// el @usuario de Instagram y la Página de Facebook reales, para no escribirlos
  /// dos veces. Solo rellena lo que esté VACÍO (no pisa lo que el dueño ya puso).
  /// Devuelve true si cambió algo.
  bool actualizarRedesAcademia(String academiaId,
      {String? instagram, String? facebook}) {
    final i = academias.indexWhere((a) => a.id == academiaId);
    if (i < 0) return false;
    final redes = Map<String, String>.from(academias[i].redes);
    var cambio = false;
    if (instagram != null &&
        instagram.trim().isNotEmpty &&
        (redes['instagram'] ?? '').trim().isEmpty) {
      redes['instagram'] = instagram.trim();
      cambio = true;
    }
    if (facebook != null &&
        facebook.trim().isNotEmpty &&
        (redes['facebook'] ?? '').trim().isEmpty) {
      redes['facebook'] = facebook.trim();
      cambio = true;
    }
    if (!cambio) return false;
    academias[i] = academias[i].copyWith(redes: redes);
    notifyListeners();
    _persistirDatos();
    AcademiasRepo.guardar(academias[i]);
    return true;
  }

  /// Arma los datos que el backend necesita para RENDERIZAR la landing de una
  /// academia (nombre, tarifario por programa, fotos, redes, ubicación).
  Map<String, dynamic> _landingDatos(Academia ac) {
    final programas = <Map<String, dynamic>>[];
    ac.planesPorPrograma.forEach((prog, planes) {
      if (prog.isEmpty) return;
      final first = planes.first;
      programas.add({
        'nombre': prog,
        'etapa': first.etapaEdad,
        'duracion': first.duracionClase,
        'precios': [
          for (final p in planes)
            {'frec': p.frecuenciaSemana, 'socio': p.precioMes}
        ],
      });
    });
    final simples = [
      for (final p in ac.planes)
        if (p.programa.isEmpty)
          {
            'nombre': p.nombre,
            'precio': p.precioMes,
            'sufijo': p.tipo == TipoPlan.porClase ? ' /clase' : ' /mes',
          }
    ];
    return {
      'nombre': ac.nombre,
      'deporte': ac.deporte.name,
      'sede': ac.sedeClub,
      'moneda': ac.monedaSimbolo,
      'recargo_invitado': ac.recargoInvitado,
      'descripcion': ac.descripcion,
      'whatsapp': ac.whatsapp,
      'instagram': ac.redes['instagram'] ?? '',
      if (ac.sedeUbicacion != null) 'lat': ac.sedeUbicacion!.latitude,
      if (ac.sedeUbicacion != null) 'lng': ac.sedeUbicacion!.longitude,
      'fotos': ac.fotos,
      'programas': programas,
      'planes': simples,
      // CIRCUITO: tabla de posiciones para embeber el ranking en la web (Fase 0-b).
      // Solo si hay al menos un partido jugado (si no, no se muestra la sección).
      'ranking': ac.partidos.isEmpty
          ? const []
          : [
              for (final p in ac.ranking(alumnosDe(ac.id)).take(10))
                {
                  'nombre': p.nombre,
                  'categoria': p.categoria,
                  'pj': p.pj,
                  'pg': p.pg,
                  'puntos': p.puntos,
                  'pct': p.pct.round(),
                }
            ],
    };
  }

  /// Genera/actualiza la landing en el backend y guarda su URL en la academia
  /// (para que el editor y la ficha muestren "Ver mi landing"). Devuelve la URL
  /// o null si no se pudo.
  Future<String?> generarLanding(Academia ac) async {
    final ok = await PagosService.generarLanding(ac.id, _landingDatos(ac));
    if (!ok) return null;
    final url = PagosService.landingUrl(ac.id);
    if (url == null) return null;
    final i = academias.indexWhere((a) => a.id == ac.id);
    if (i >= 0) {
      academias[i] = academias[i].copyWith(landingUrl: url);
      notifyListeners();
      _persistirDatos();
      AcademiasRepo.guardar(academias[i]);
    }
    return url;
  }

  /// Community manager con IA: genera posts para las redes de la academia
  /// (texto + hashtags + hora sugerida). Devuelve el JSON del backend (incluye
  /// 'posts' y el control de tope mensual 'limite'/'usados').
  Future<Map<String, dynamic>?> generarPosts(Academia ac, String tema) async {
    return PagosService.generarPosts(
        academiaId: ac.id, datos: _landingDatos(ac), contexto: tema);
  }

  // === Servicios Pichangol sobre "Negocio" (academia o club) ==============
  /// Ids de negocios (clubes) que ya generaron su landing (persistido). Las
  /// academias guardan su landingUrl en la propia academia; los clubes aquí.
  final Set<String> _landingNegocios = {};

  Negocio negocioDeAcademia(Academia a) => Negocio(
        id: a.id,
        nombre: a.nombre,
        monedaSimbolo: a.monedaSimbolo,
        pais: a.pais,
        dueno: a.dueno,
        tipo: 'academia',
        tieneRedesRegistradas:
            (a.redes['instagram']?.trim().isNotEmpty ?? false) ||
                (a.redes['facebook']?.trim().isNotEmpty ?? false) ||
                (a.redes['tiktok']?.trim().isNotEmpty ?? false),
        landingUrl: a.landingUrl,
        datosLanding: _landingDatos(a),
      );

  Negocio negocioDeClub(Club c) {
    final id = 'club_${c.id}';
    final lat = c.ubicacion.latitude, lng = c.ubicacion.longitude;
    final tieneLanding = _landingNegocios.contains(id);
    return Negocio(
      id: id,
      nombre: c.nombre,
      monedaSimbolo: monedaDeCoordenadas(lat, lng),
      pais: paisDeCoordenadas(lat, lng),
      dueno: usuario?.email ?? '',
      tipo: 'club',
      tieneRedesRegistradas: false,
      landingUrl: tieneLanding ? (PagosService.landingUrl(id) ?? '') : '',
      datosLanding: _datosClub(c),
    );
  }

  Map<String, dynamic> _datosClub(Club c) {
    final canchas = [
      for (final ca in c.canchas)
        {
          'nombre': ca.nombre,
          'precio': ca.precioHora,
          'sufijo': ' /hora',
        }
    ];
    return {
      'nombre': c.nombre,
      'deporte': c.deportes.isNotEmpty ? c.deportes.first.name : '',
      'sede': c.barrio,
      'moneda': monedaDeCoordenadas(c.ubicacion.latitude, c.ubicacion.longitude),
      'descripcion': '',
      'whatsapp': '',
      'instagram': '',
      'lat': c.ubicacion.latitude,
      'lng': c.ubicacion.longitude,
      'fotos': [for (final ca in c.canchas) ...ca.fotos],
      'programas': const [],
      'planes': canchas,
    };
  }

  /// Genera/actualiza la landing de un NEGOCIO (academia o club) en el backend.
  Future<String?> generarLandingNegocio(Negocio n) async {
    final ok = await PagosService.generarLanding(n.id, n.datosLanding);
    if (!ok) return null;
    final url = PagosService.landingUrl(n.id);
    if (url == null) return null;
    if (n.esAcademia) {
      final i = academias.indexWhere((a) => a.id == n.id);
      if (i >= 0) {
        academias[i] = academias[i].copyWith(landingUrl: url);
        AcademiasRepo.guardar(academias[i]);
      }
    } else {
      _landingNegocios.add(n.id);
      // Negocio unificado (mixto: academia + canchas): el id es `dueno_<slug>`,
      // no el de la academia, así que arriba NO se refleja el enlace en la ficha.
      // Lo copiamos a la(s) academia(s) del dueño para que aparezca SOLO en
      // "Editar academia › Landing" (la promesa "el enlace aparece aquí solo").
      final email = usuario?.email.toLowerCase();
      if (email != null && email.isNotEmpty) {
        for (var i = 0; i < academias.length; i++) {
          if (academias[i].dueno.toLowerCase() == email &&
              academias[i].landingUrl.trim() != url) {
            academias[i] = academias[i].copyWith(landingUrl: url);
            AcademiasRepo.guardar(academias[i]);
          }
        }
      }
    }
    notifyListeners();
    _persistirDatos();
    return url;
  }

  Future<Map<String, dynamic>?> generarPostsNegocio(
      Negocio n, String tema) async {
    return PagosService.generarPosts(
        academiaId: n.id, datos: n.datosLanding, contexto: tema);
  }

  // === Fase 2: presencia UNIFICADA (mismo dueño con academia + canchas) =====
  /// Clubes (locales) REGISTRADOS del dueño logueado. Se derivan agrupando sus
  /// canchas propias. Sólo cuentan las registradas (las descubiertas de Google
  /// no son "suyas").
  List<Club> get misClubesRegistrados =>
      Club.agrupar(misCanchas.where((c) => c.registrada).toList())
          .where((cl) => cl.registrada)
          .toList();

  /// ¿El dueño logueado tiene A LA VEZ una academia y al menos un local con
  /// canchas registradas? Entonces conviene un solo plan de Servicios Pichangol
  /// para ambos (no pagar doble por lo mismo).
  bool get duenoTieneCanchasYAcademia =>
      miAcademia != null && misClubesRegistrados.isNotEmpty;

  String _slugDueno(String email) =>
      email.toLowerCase().replaceAll(RegExp(r'[^a-z0-9]'), '_');

  /// Negocio UNIFICADO del dueño: fusiona su academia + todos sus locales en un
  /// solo sujeto de Servicios Pichangol (una landing que deja reservar cancha y
  /// matricularse, una sola suscripción keyed por `dueno_<correo>`). Null si el
  /// dueño no tiene ambos. La marca la lidera la academia (el nombre público).
  Negocio? negocioUnificado() {
    final ac = miAcademia;
    final clubes = misClubesRegistrados;
    if (ac == null || clubes.isEmpty) return null;
    final email = usuario?.email ?? '';
    final id = 'dueno_${_slugDueno(email)}';
    final tieneLanding = _landingNegocios.contains(id);

    // Datos combinados: programas de la academia + canchas de todos los locales
    // como ítems reservables. La sede/ubicación la aporta la academia.
    final base = _landingDatos(ac);
    final planes = List<Map<String, dynamic>>.from(
        (base['planes'] as List).map((e) => Map<String, dynamic>.from(e as Map)));
    for (final cl in clubes) {
      for (final ca in cl.canchas) {
        planes.add({
          'nombre': '${ca.nombre} · ${cl.nombre}',
          'precio': ca.precioHora,
          'sufijo': ' /hora',
        });
      }
    }
    final fotos = List<String>.from(base['fotos'] as List);
    for (final cl in clubes) {
      for (final ca in cl.canchas) {
        fotos.addAll(ca.fotos);
      }
    }
    final datos = Map<String, dynamic>.from(base)
      ..['planes'] = planes
      ..['fotos'] = fotos;

    return Negocio(
      id: id,
      nombre: ac.nombre,
      monedaSimbolo: ac.monedaSimbolo,
      pais: ac.pais,
      dueno: ac.dueno.isNotEmpty ? ac.dueno : email,
      tipo: 'mixto',
      tieneRedesRegistradas:
          (ac.redes['instagram']?.trim().isNotEmpty ?? false) ||
              (ac.redes['facebook']?.trim().isNotEmpty ?? false) ||
              (ac.redes['tiktok']?.trim().isNotEmpty ?? false),
      landingUrl: tieneLanding ? (PagosService.landingUrl(id) ?? '') : '',
      datosLanding: datos,
    );
  }

  /// El Negocio con el que abrir Servicios Pichangol desde la ACADEMIA: el
  /// unificado si el dueño también tiene canchas, si no la academia sola.
  Negocio negocioServiciosDeAcademia(Academia a) =>
      negocioUnificado() ?? negocioDeAcademia(a);

  /// El Negocio con el que abrir Servicios Pichangol desde un LOCAL: el unificado
  /// si el dueño también tiene academia, si no ese club solo.
  Negocio negocioServiciosDeClub(Club c) =>
      negocioUnificado() ?? negocioDeClub(c);

  void eliminarAcademia(String id) {
    academias.removeWhere((a) => a.id == id);
    alumnos.removeWhere((al) => al.academiaId == id);
    cuotas.removeWhere((c) => c.academiaId == id);
    asistencias.removeWhere((a) => a.academiaId == id);
    notifyListeners();
    _persistirDatos();
    AcademiasRepo.eliminar(id); // borrado lógico durable en la nube
  }

  // ── Campeonatos ────────────────────────────────────────────────────────────
  List<Campeonato> campeonatosDe(String academiaId) =>
      campeonatos.where((c) => c.academiaId == academiaId).toList();

  Campeonato? campeonatoPorId(String id) {
    for (final c in campeonatos) {
      if (c.id == id) return c;
    }
    return null;
  }

  /// Crea un campeonato para una academia y lo comparte (nube). Devuelve el id.
  Campeonato crearCampeonato({
    required String academiaId,
    required String nombre,
    required Deporte deporte,
    required FormatoTorneo formato,
    String categoria = '',
    String sede = '',
    LatLng? sedeUbicacion,
    String fechas = '',
    double costoInscripcion = 0,
  }) {
    final c = Campeonato(
      id: 'camp_${DateTime.now().microsecondsSinceEpoch}',
      academiaId: academiaId,
      dueno: usuario?.email ?? '',
      nombre: nombre,
      deporte: deporte,
      formato: formato,
      categoria: categoria,
      sede: sede,
      sedeUbicacion: sedeUbicacion,
      fechas: fechas,
      costoInscripcion: costoInscripcion,
      // Congela la moneda por el país de la SEDE (no el del dispositivo): un
      // torneo en Lima queda en S/ aunque el profe lo cree desde Bolivia.
      moneda: sedeUbicacion != null
          ? monedaDeCoordenadas(
              sedeUbicacion.latitude, sedeUbicacion.longitude)
          : paisActual.moneda,
    );
    campeonatos.add(c);
    notifyListeners();
    _persistirDatos();
    CampeonatosRepo.guardar(c);
    return c;
  }

  /// Reemplaza un campeonato (por id), persiste y sube a la nube.
  void guardarCampeonato(Campeonato c) {
    final i = campeonatos.indexWhere((x) => x.id == c.id);
    if (i >= 0) {
      campeonatos[i] = c;
    } else {
      campeonatos.add(c);
    }
    notifyListeners();
    _persistirDatos();
    CampeonatosRepo.guardar(c);
  }

  void eliminarCampeonato(String id) {
    campeonatos.removeWhere((c) => c.id == id);
    notifyListeners();
    _persistirDatos();
    CampeonatosRepo.eliminar(id);
  }

  /// Agrega un participante (jugador/pareja/equipo). Si ya hay fixture, no lo
  /// regenera (hay que rehacerlo manualmente para no romper resultados).
  void agregarParticipante(String campId, String nombre, {String contacto = ''}) {
    final c = campeonatoPorId(campId);
    if (c == null || nombre.trim().isEmpty) return;
    final p = Participante(
        id: 'part_${DateTime.now().microsecondsSinceEpoch}',
        nombre: nombre.trim(),
        contacto: contacto.trim());
    guardarCampeonato(c.copyWith(participantes: [...c.participantes, p]));
  }

  void eliminarParticipante(String campId, String partId) {
    final c = campeonatoPorId(campId);
    if (c == null) return;
    guardarCampeonato(c.copyWith(
        participantes:
            c.participantes.where((p) => p.id != partId).toList()));
  }

  /// El JUGADOR se inscribe a un campeonato desde la app (queda como
  /// participante-app vinculado a su cuenta). Si [nombreParticipante] viene, es
  /// un MENOR representado por el usuario (apoderado). Requiere sesión.
  ({bool ok, String mensaje}) inscribirseCampeonato(
    String campId, {
    String? nombreParticipante, // nombre del niño/equipo si aplica
    int? edad,
    String? apoderadoWhatsapp,
  }) {
    final u = usuario;
    if (u == null) {
      return (ok: false, mensaje: 'Inicia sesión para inscribirte.');
    }
    final c = campeonatoPorId(campId);
    if (c == null) return (ok: false, mensaje: 'Campeonato no encontrado.');
    if (c.cerrado || !c.inscripcionAbierta) {
      return (ok: false, mensaje: 'Las inscripciones están cerradas.');
    }
    if (c.fixtureGenerado) {
      return (
        ok: false,
        mensaje: 'El fixture ya fue generado; escribe al organizador.'
      );
    }
    final esMenor =
        nombreParticipante != null && nombreParticipante.trim().isNotEmpty;
    final nombre = esMenor ? nombreParticipante!.trim() : u.nombre;
    final ya = c.participantes.any((p) =>
        p.email.toLowerCase() == u.email.toLowerCase() &&
        p.nombre.toLowerCase() == nombre.toLowerCase());
    if (ya) {
      return (ok: true, mensaje: '"$nombre" ya está inscrito en ${c.nombre}.');
    }
    final p = Participante(
      id: 'part_${DateTime.now().microsecondsSinceEpoch}',
      nombre: nombre,
      contacto: esMenor ? (apoderadoWhatsapp?.trim() ?? '') : '',
      email: u.email,
      fotoUrl: esMenor ? null : u.fotoUrl,
      apoderadoNombre: esMenor ? u.nombre : '',
      edad: edad,
    );
    guardarCampeonato(c.copyWith(participantes: [...c.participantes, p]));
    return (
      ok: true,
      mensaje: esMenor
          ? 'Inscribiste a "$nombre" en ${c.nombre}. 🏆'
          : 'Te inscribiste en ${c.nombre}. 🏆'
    );
  }

  /// (Re)genera el fixture del campeonato según su formato. Borra resultados.
  void generarFixture(String campId) {
    final c = campeonatoPorId(campId);
    if (c == null) return;
    final partidos = TorneoFixture.generar(c.formato, c.participantes);
    guardarCampeonato(c.copyWith(partidos: partidos));
  }

  /// Carga el marcador de un partido. En eliminación, propaga el ganador a la
  /// siguiente ronda.
  void setResultado(String campId, String partidoId, int a, int b) {
    final c = campeonatoPorId(campId);
    if (c == null) return;
    var partidos = [
      for (final p in c.partidos)
        p.id == partidoId ? p.conMarcador(a, b) : p
    ];
    if (c.formato == FormatoTorneo.eliminacion) {
      partidos = TorneoFixture.recomputarLlave(partidos);
    }
    guardarCampeonato(c.copyWith(partidos: partidos));
  }

  /// Trae los campeonatos de la nube y los fusiona por id. Best-effort.
  Future<void> cargarCampeonatosRemotos() async {
    final remotos = await CampeonatosRepo.fetchRemotos();
    if (remotos.isEmpty) return;
    var cambio = false;
    for (final c in remotos) {
      final i = campeonatos.indexWhere((x) => x.id == c.id);
      if (i >= 0) {
        campeonatos[i] = c;
      } else {
        campeonatos.add(c);
      }
      cambio = true;
    }
    if (cambio) {
      notifyListeners();
      _persistirDatos();
    }
  }

  /// Trae las academias de la nube y las fusiona con las locales (por id). Así,
  /// al reinstalar el APK, las academias del profe reaparecen. Best-effort.
  /// Siembra la academia PILOTO (Jartur · El Bosque) si aún no está, con su
  /// tarifario cargado. Devuelve true si la agregó. Retro-compatible: si el
  /// profe la editó (mismo id), la versión guardada/remota gana luego.
  bool sembrarAcademias() {
    // La academia DEMO (Jartur) es solo para demos: se siembra únicamente en
    // dev. En QAS/prod NO aparece (evita el "duplicado" con academias reales).
    const entorno = String.fromEnvironment('ENTORNO', defaultValue: 'dev');
    if (entorno != 'dev') return false;
    const seedId = 'seed_jartur_elbosque';
    if (!academias.any((a) => a.id == seedId)) {
      academias.add(SampleData.academiaJartur());
      return true;
    }
    return _curarSeedJartur();
  }

  /// Cura una Jartur guardada de un build viejo: si NO tiene tarifa invitado ni
  /// descuentos ni retribución (todos en 0 = registro anterior a estos campos),
  /// les aplica los valores del seed SIN tocar el resto (nombre/planes que el
  /// profe pudo editar). Una vez que el profe fija cualquiera de estos valores,
  /// deja de curar. Devuelve true si cambió algo.
  bool _curarSeedJartur() {
    const seedId = 'seed_jartur_elbosque';
    final i = academias.indexWhere((a) => a.id == seedId);
    if (i < 0) return false;
    final actual = academias[i];
    final faltan = actual.recargoInvitado == 0 &&
        actual.descuentoHermano2 == 0 &&
        actual.descuentoHermano3 == 0 &&
        actual.descuentoPrepago == 0 &&
        actual.retribucionClubPct == 0;
    if (!faltan) return false;
    final seed = SampleData.academiaJartur();
    academias[i] = actual.copyWith(
      recargoInvitado: seed.recargoInvitado,
      descuentoHermano2: seed.descuentoHermano2,
      descuentoHermano3: seed.descuentoHermano3,
      descuentoPrepago: seed.descuentoPrepago,
      retribucionClubPct: seed.retribucionClubPct,
      planes: actual.planes.isEmpty ? seed.planes : actual.planes,
    );
    return true;
  }

  /// True una vez que el PRIMER intento de traer academias de la nube terminó
  /// (con éxito o fallo). Mientras es false, la UI del profe muestra un spinner
  /// en vez de "no tienes academia": así evitamos que el profe cree una academia
  /// DUPLICADA porque la suya aún no había bajado de Supabase (1.ª barrera).
  bool academiasRemotasCargadas = false;
  bool _cargandoAcademias = false;

  Future<void> cargarAcademiasRemotas() async {
    if (_cargandoAcademias) return; // ya hay una carga en curso: no re-entrar
    _cargandoAcademias = true;
    var cambio = sembrarAcademias(); // asegura la academia piloto + su tarifario
    try {
      final remotas = await AcademiasRepo.fetchRemotas();
      for (final a in remotas) {
        // Si hay una edición local sin confirmar en la nube, NO la pises con la
        // versión remota (más vieja): perderíamos lo que el profe acaba de
        // guardar. Se reintenta subir más abajo.
        if (_academiasPendientesNube.contains(a.id)) continue;
        final i = academias.indexWhere((x) => x.id == a.id);
        if (i >= 0) {
          academias[i] = a;
        } else {
          academias.add(a);
        }
        cambio = true;
      }
      // La remota pudo pisar a Jartur con una versión vieja: cúrala de nuevo.
      if (_curarSeedJartur()) cambio = true;
      // Reintenta subir las ediciones locales que aún no confirmaron en la nube.
      for (final id in _academiasPendientesNube.toList()) {
        final i = academias.indexWhere((x) => x.id == id);
        if (i < 0) {
          _academiasPendientesNube.remove(id); // ya no existe: nada que subir
          continue;
        }
        if (await AcademiasRepo.guardar(academias[i])) {
          _academiasPendientesNube.remove(id);
          cambio = true;
        }
      }
    } finally {
      _cargandoAcademias = false;
      if (!academiasRemotasCargadas) {
        academiasRemotasCargadas = true;
        cambio = true; // reemplaza el spinner por el contenido real
      }
    }
    if (cambio) {
      notifyListeners();
      _persistirDatos();
    }
  }

  List<Alumno> alumnosDe(String academiaId) =>
      alumnos.where((a) => a.academiaId == academiaId).toList();

  /// Matrículas del USUARIO actual (como ALUMNO): las academias donde está
  /// inscrito. Sirve para su vista "Mis clases y pagos".
  List<Alumno> get misMatriculas {
    final email = usuario?.email.trim().toLowerCase();
    if (email == null || email.isEmpty) return const [];
    return alumnos
        .where((a) => a.email.trim().toLowerCase() == email)
        .toList();
  }

  void agregarAlumno(Alumno a) {
    alumnos.add(a);
    notifyListeners();
    _persistirDatos();
    MatriculasRepo.guardar(a); // best-effort: cross-device + sobrevive reinstalar
  }

  void eliminarAlumno(String alumnoId) {
    alumnos.removeWhere((a) => a.id == alumnoId);
    cuotas.removeWhere((c) => c.alumnoId == alumnoId);
    asistencias.removeWhere((a) => a.alumnoId == alumnoId);
    notifyListeners();
    _persistirDatos();
    MatriculasRepo.eliminar(alumnoId); // borrado lógico durable en la nube
  }

  /// El alumno se une a una academia con su CÓDIGO (desde la app). La cuenta
  /// siempre es de un ADULTO: si [nombreAlumno] viene, es un MENOR representado
  /// por el usuario (apoderado); si no, el alumno es el propio adulto. Crea el
  /// alumno vinculado a la cuenta y lo sube a la nube para que el profe lo vea.
  /// Requiere sesión iniciada.
  ({bool ok, String mensaje}) matricularConCodigo(
    String codigoIngresado, {
    String? nombreAlumno, // nombre del niño si es un menor
    int? edad,
    String? apoderadoWhatsapp,
  }) {
    final u = usuario;
    if (u == null) {
      return (ok: false, mensaje: 'Inicia sesión para unirte a una academia.');
    }
    final code = Academia.normalizarCodigo(codigoIngresado);
    if (code.length < 6) {
      return (ok: false, mensaje: 'El código tiene 6 caracteres. Revísalo.');
    }
    Academia? encontrada;
    for (final a in academias) {
      if (a.codigo == code) {
        encontrada = a;
        break;
      }
    }
    if (encontrada == null) {
      return (ok: false, mensaje: 'No encontramos una academia con ese código.');
    }
    final academia = encontrada; // promovido a non-null
    final esMenor = nombreAlumno != null && nombreAlumno.trim().isNotEmpty;
    final nombre = esMenor ? nombreAlumno!.trim() : u.nombre;
    // Dedup por (academia + cuenta + nombre): así un apoderado puede inscribir a
    // VARIOS hijos, pero no duplica al mismo alumno.
    final ya = alumnos.any((al) =>
        al.academiaId == academia.id &&
        al.email.toLowerCase() == u.email.toLowerCase() &&
        al.nombre.toLowerCase() == nombre.toLowerCase());
    if (ya) {
      return (
        ok: true,
        mensaje: esMenor
            ? '"$nombre" ya está matriculado en ${academia.nombre}.'
            : 'Ya estás matriculado en ${academia.nombre}.'
      );
    }
    final alumno = Alumno(
      id: 'al_${DateTime.now().microsecondsSinceEpoch}',
      academiaId: academia.id,
      nombre: nombre,
      email: u.email,
      fotoUrl: esMenor ? null : u.fotoUrl,
      apoderadoNombre: esMenor ? u.nombre : '',
      apoderadoWhatsapp: esMenor ? (apoderadoWhatsapp?.trim() ?? '') : '',
      edad: edad,
    );
    alumnos.add(alumno);
    // Si tenía una invitación por correo pendiente a esta academia, márcala
    // aceptada para que el profe la vea resuelta (y no como pendiente).
    for (var k = 0; k < invitaciones.length; k++) {
      final inv = invitaciones[k];
      if (inv.academiaId == academia.id &&
          inv.estado == EstadoInvitacion.pendiente &&
          inv.coincideEmail(u.email)) {
        invitaciones[k] = inv.copyWith(estado: EstadoInvitacion.aceptada);
        InvitacionesRepo.guardar(invitaciones[k]);
      }
    }
    notifyListeners();
    _persistirDatos();
    MatriculasRepo.guardar(alumno);
    return (
      ok: true,
      mensaje: esMenor
          ? 'Inscribiste a "$nombre" en ${academia.nombre}. 🎾'
          : 'Te uniste a ${academia.nombre}. ¡Listo! 🎾'
    );
  }

  DateTime? _ultimoSyncMatriculas;

  /// Sincroniza matrículas desde la nube con THROTTLE (evita spam al reconstruir
  /// la pantalla). Úsalo al abrir "Mi academia" para que el profe vea al toque a
  /// los alumnos que se matricularon desde otro dispositivo.
  void syncMatriculas({bool forzar = false}) {
    final ahora = DateTime.now();
    if (!forzar &&
        _ultimoSyncMatriculas != null &&
        ahora.difference(_ultimoSyncMatriculas!).inSeconds < 15) {
      return;
    }
    _ultimoSyncMatriculas = ahora;
    refrescarAcademiaProfe();
  }

  /// Refresca academias + matrículas de la nube (para pull-to-refresh del panel
  /// del profe). Devuelve un Future para el RefreshIndicator.
  Future<void> refrescarAcademiaProfe() async {
    // Primero las academias (para tener bien `misAcademiaIds` aunque la academia
    // se haya creado en otro dispositivo) y luego las matrículas.
    await cargarAcademiasRemotas();
    await cargarMatriculasRemotas();
  }

  /// Trae de la nube las matrículas relevantes: las de las academias que el
  /// usuario administra (rol profe) y las suyas como alumno-app. Las fusiona por
  /// id. Best-effort (sin romper si Supabase no está).
  Future<void> cargarMatriculasRemotas() async {
    final u = usuario;
    final misAcademiaIds = <String>[
      for (final a in academias)
        if (u != null && a.dueno.toLowerCase() == u.email.toLowerCase()) a.id,
    ];
    final remotas = <Alumno>[];
    final remotasCuotas = <Cuota>[];
    if (misAcademiaIds.isNotEmpty) {
      final r = await MatriculasRepo.deAcademias(misAcademiaIds);
      remotas.addAll(r.alumnos);
      remotasCuotas.addAll(r.cuotas);
    }
    if (u != null) {
      final r = await MatriculasRepo.deAlumno(u.email);
      remotas.addAll(r.alumnos);
      remotasCuotas.addAll(r.cuotas);
    }
    if (remotas.isEmpty && remotasCuotas.isEmpty) return;
    var cambio = false;
    for (final al in remotas) {
      final i = alumnos.indexWhere((x) => x.id == al.id);
      if (i >= 0) {
        alumnos[i] = al;
      } else {
        alumnos.add(al);
      }
      cambio = true;
    }
    // Fusiona las cuotas embebidas. Si la cuota es nueva, se agrega; si ya existe
    // y en la nube figura PAGADA (pago manual del alumno / marcada por el profe
    // en otro dispositivo), se marca pagada acá también. El pago es "pegajoso":
    // nunca revierte una pagada a pendiente (evita carreras entre dispositivos).
    for (final c in remotasCuotas) {
      final i = cuotas.indexWhere((x) => x.id == c.id);
      if (i < 0) {
        cuotas.add(c);
        cambio = true;
      } else if (c.pagada && !cuotas[i].pagada) {
        cuotas[i] = cuotas[i]
            .copyWith(pagada: true, fechaPago: c.fechaPago ?? DateTime.now());
        cambio = true;
      }
    }
    if (cambio) {
      notifyListeners();
      _persistirDatos();
    }
  }

  /// RECONCILIA las cuotas de mes a mes: consulta al backend cuántos cobros
  /// automáticos hizo el cron y marca pagadas las cuotas correspondientes del
  /// alumno (1.er mes del signup + cobros hechos), en orden cronológico. Lo llama
  /// tanto el alumno (Mis clases) como el profe (ficha), y cada uno converge al
  /// mismo estado sin depender del otro. Devuelve el estado para mostrarlo.
  Future<Map<String, dynamic>?> reconciliarSuscripcionAlumno(
      String alumnoId) async {
    final estado = await PagosService.estadoSuscripcionAlumno(alumnoId);
    if (estado == null) return null;
    final hechos = (estado['cobros_hechos'] as num?)?.toInt() ?? 0;
    final pagadasEsperadas = 1 + hechos; // 1.er mes (signup) + cobros del cron
    final auto = cuotas
        .where((c) => c.alumnoId == alumnoId && c.autoDebito)
        .toList()
      ..sort((a, b) => a.vencimiento.compareTo(b.vencimiento));
    var cambio = false;
    final ahora = DateTime.now();
    for (var i = 0; i < auto.length && i < pagadasEsperadas; i++) {
      if (auto[i].pagada) continue;
      final idx = cuotas.indexWhere((x) => x.id == auto[i].id);
      if (idx >= 0) {
        cuotas[idx] = cuotas[idx].copyWith(pagada: true, fechaPago: ahora);
        cambio = true;
      }
    }
    if (cambio) {
      notifyListeners();
      _persistirDatos();
    }
    return estado;
  }

  // ── Invitaciones (invitar por correo / teléfono) ──────────────────────────

  /// Invitaciones que el profe creó para una academia (excluye canceladas), de
  /// la más reciente a la más antigua.
  List<Invitacion> invitacionesDe(String academiaId) => invitaciones
      .where((i) =>
          i.academiaId == academiaId &&
          i.estado != EstadoInvitacion.cancelada)
      .toList()
    ..sort((a, b) => b.creada.compareTo(a.creada));

  /// Invitaciones PENDIENTES dirigidas al usuario logueado (por correo) a
  /// academias en las que aún NO está matriculado. Es lo que ve el alumno como
  /// "te invitaron".
  List<Invitacion> misInvitacionesPendientes() {
    final email = usuario?.email;
    if (email == null || email.isEmpty) return [];
    final mail = Invitacion.normalizarEmail(email);
    return invitaciones.where((i) {
      if (i.estado != EstadoInvitacion.pendiente) return false;
      if (!i.coincideEmail(mail)) return false;
      // Ya matriculado en esa academia con esta cuenta → no molestar.
      final ya = alumnos.any((al) =>
          al.academiaId == i.academiaId &&
          al.email.toLowerCase() == mail);
      return !ya;
    }).toList()
      ..sort((a, b) => b.creada.compareTo(a.creada));
  }

  /// El profe crea una invitación por correo y/o teléfono. Devuelve la
  /// invitación creada (o null si no dio ni correo ni teléfono válidos).
  Invitacion? crearInvitacion({
    required Academia academia,
    String nombre = '',
    String email = '',
    String telefono = '',
  }) {
    final mail = Invitacion.normalizarEmail(email);
    final tel = Invitacion.normalizarTelefono(telefono);
    if (mail.isEmpty && tel.isEmpty) return null;
    // Dedup: si ya hay una invitación pendiente al mismo destino, reúsala.
    final existente = invitaciones.where((i) =>
        i.academiaId == academia.id &&
        i.estado == EstadoInvitacion.pendiente &&
        ((mail.isNotEmpty && i.email == mail) ||
            (tel.isNotEmpty && i.telefono == tel)));
    if (existente.isNotEmpty) return existente.first;
    final inv = Invitacion(
      id: 'inv_${DateTime.now().microsecondsSinceEpoch}',
      academiaId: academia.id,
      academiaNombre: academia.nombre,
      deporte: academia.deporte.name,
      email: mail,
      telefono: tel,
      nombreSugerido: nombre.trim(),
      estado: EstadoInvitacion.pendiente,
      creada: DateTime.now(),
    );
    invitaciones.add(inv);
    notifyListeners();
    _persistirDatos();
    InvitacionesRepo.guardar(inv); // cross-device
    return inv;
  }

  /// El profe cancela una invitación (borrado lógico durable en la nube).
  void cancelarInvitacion(String id) {
    final i = invitaciones.indexWhere((x) => x.id == id);
    if (i < 0) return;
    invitaciones[i] = invitaciones[i].copyWith(
        estado: EstadoInvitacion.cancelada);
    notifyListeners();
    _persistirDatos();
    InvitacionesRepo.guardar(invitaciones[i]);
  }

  /// El alumno ACEPTA una invitación: se matricula (queda como alumno-app) y la
  /// invitación pasa a aceptada. Requiere sesión iniciada.
  ({bool ok, String mensaje}) aceptarInvitacion(Invitacion inv) {
    final u = usuario;
    if (u == null) {
      return (ok: false, mensaje: 'Inicia sesión para aceptar la invitación.');
    }
    Academia? academia;
    for (final a in academias) {
      if (a.id == inv.academiaId) {
        academia = a;
        break;
      }
    }
    final nombre = inv.nombreSugerido.isNotEmpty ? inv.nombreSugerido : u.nombre;
    // Dedup por (academia + cuenta): no duplicar si ya se unió.
    final ya = alumnos.any((al) =>
        al.academiaId == inv.academiaId &&
        al.email.toLowerCase() == u.email.toLowerCase());
    if (!ya) {
      alumnos.add(Alumno(
        id: 'al_${DateTime.now().microsecondsSinceEpoch}',
        academiaId: inv.academiaId,
        nombre: nombre,
        email: u.email,
        fotoUrl: u.fotoUrl,
      ));
      MatriculasRepo.guardar(alumnos.last);
    }
    _marcarInvitacionAceptada(inv);
    notifyListeners();
    _persistirDatos();
    final nom = academia?.nombre ?? inv.academiaNombre;
    return (ok: true, mensaje: 'Te uniste a $nom. ¡Listo! 🎾');
  }

  /// El alumno rechaza una invitación (no vuelve a aparecer).
  void rechazarInvitacion(Invitacion inv) {
    final i = invitaciones.indexWhere((x) => x.id == inv.id);
    if (i < 0) return;
    invitaciones[i] = invitaciones[i].copyWith(
        estado: EstadoInvitacion.rechazada);
    notifyListeners();
    _persistirDatos();
    InvitacionesRepo.guardar(invitaciones[i]);
  }

  void _marcarInvitacionAceptada(Invitacion inv) {
    final i = invitaciones.indexWhere((x) => x.id == inv.id);
    if (i < 0) return;
    invitaciones[i] = invitaciones[i].copyWith(
        estado: EstadoInvitacion.aceptada);
    InvitacionesRepo.guardar(invitaciones[i]);
  }

  /// Trae de la nube las invitaciones relevantes: las que creó el profe (por sus
  /// academias) y las dirigidas al correo del usuario. Las fusiona por id.
  /// Best-effort.
  Future<void> cargarInvitacionesRemotas() async {
    final u = usuario;
    final misAcademiaIds = <String>[
      for (final a in academias)
        if (u != null && a.dueno.toLowerCase() == u.email.toLowerCase()) a.id,
    ];
    final remotas = <Invitacion>[];
    if (misAcademiaIds.isNotEmpty) {
      remotas.addAll(await InvitacionesRepo.deAcademias(misAcademiaIds));
    }
    if (u != null) {
      remotas.addAll(await InvitacionesRepo.paraEmail(u.email));
    }
    if (remotas.isEmpty) return;
    var cambio = false;
    for (final inv in remotas) {
      final i = invitaciones.indexWhere((x) => x.id == inv.id);
      if (i >= 0) {
        invitaciones[i] = inv;
      } else {
        invitaciones.add(inv);
      }
      cambio = true;
    }
    if (cambio) {
      notifyListeners();
      _persistirDatos();
    }
  }

  // ── Chat (Etapa A) ────────────────────────────────────────────────────────

  /// Marca un hilo como leído hasta ahora (limpia el contador de no leídos).
  void marcarChatLeido(String hilo) {
    chatLecturas[hilo] = DateTime.now().toIso8601String();
    notifyListeners();
    _persistirDatos();
  }

  /// Cuándo se leyó por última vez un hilo (null si nunca).
  DateTime? chatUltimaLectura(String hilo) {
    final iso = chatLecturas[hilo];
    return iso == null ? null : DateTime.tryParse(iso);
  }

  List<Cuota> cuotasDe(String academiaId) => cuotas
      .where((c) => c.academiaId == academiaId)
      .toList()
    ..sort((a, b) => a.vencimiento.compareTo(b.vencimiento));

  List<Cuota> cuotasDeAlumno(String alumnoId) => cuotas
      .where((c) => c.alumnoId == alumnoId)
      .toList()
    ..sort((a, b) => a.vencimiento.compareTo(b.vencimiento));

  /// Inscribe a un alumno en un plan: genera las cuotas mensuales (mensual /
  /// prepago). Para [TipoPlan.porClase] no genera nada (se cobra por clase).
  void inscribir(Alumno alumno, Plan plan, {DateTime? inicio, int? duracionMeses}) {
    if (plan.tipo == TipoPlan.porClase) return;
    final base = inicio ?? DateTime.now();
    // Duración elegida al inscribir (nº de cuotas mensuales). Si no se indica,
    // cae a la del plan (mensual = 1, prepago = meses del paquete).
    final meses = (duracionMeses != null && duracionMeses > 0)
        ? duracionMeses
        : (plan.meses < 1 ? 1 : plan.meses);
    // Precio efectivo: socio = tarifa del plan; invitado = + recargoInvitado de
    // la academia (sede/club). Si no ubica la academia, usa la tarifa del plan.
    Academia? ac;
    for (final a in academias) {
      if (a.id == alumno.academiaId) { ac = a; break; }
    }
    // Descuentos configurables de la academia: por orden de hermano (del alumno)
    // y por prepago (paquete de meses). El monto ya viene neto; se deja traza del
    // % aplicado en el concepto para el reporte del dueño.
    final prepago = plan.tipo == TipoPlan.prepago;
    final dtoPct = ac?.descuentoTotalPct(
            ordenHermano: alumno.ordenHermano, prepago: prepago) ??
        0;
    final sufijoDto = dtoPct > 0 ? ' (−${dtoPct.toStringAsFixed(0)}%)' : '';
    final monto = ac != null
        ? ac.precioFinal(plan,
            socio: alumno.esSocioSede,
            ordenHermano: alumno.ordenHermano,
            prepago: prepago)
        : plan.precioMes;
    for (var i = 0; i < meses; i++) {
      final venc = DateTime(base.year, base.month + i, base.day);
      cuotas.add(Cuota(
        id: 'cu_${DateTime.now().microsecondsSinceEpoch}_$i',
        academiaId: alumno.academiaId,
        alumnoId: alumno.id,
        concepto: '${plan.nombre} · ${_mesNombre(venc)}$sufijoDto',
        monto: monto,
        vencimiento: venc,
      ));
    }
    notifyListeners();
    _persistirDatos();
  }

  /// Matrícula del JUGADOR desde el directorio. [cantidad] es lo que el alumno
  /// PAGA por adelantado según el plan:
  /// - porClase: número de clases → 1 cuota de precio×cantidad.
  /// - mensual: número de meses → esa cantidad de cuotas mensuales.
  /// - prepago: número de paquetes → meses del paquete × cantidad cuotas.
  /// Todas las cuotas generadas quedan **pagadas** (acaba de pagarlas). Devuelve
  /// el alumno creado.
  Alumno matricular({
    required String academiaId,
    required String nombre,
    required String whatsapp,
    required Plan plan,
    int cantidad = 1,
    int? mesesPagados, // mes a mes: solo N pagadas, el resto quedan pendientes
    bool autoDebito = false, // mes a mes: marca las cuotas para reconciliación
    String apoderadoNombre = '', // si es menor: nombre del apoderado (el titular)
    String apoderadoWhatsapp = '',
    int? edad,
    String operacionId = '', // N.º de operación del pago (para el comprobante)
    String sedeId = '', // sede (local) elegida en academias multi-sede
    double? precioMesOverride, // precio de la sede (multi-sede con tarifa propia)
  }) {
    final n = cantidad < 1 ? 1 : cantidad;
    // Precio mensual/por-clase efectivo: el de la sede si vino, si no el del plan.
    final precioMes = precioMesOverride ?? plan.precioMes;
    final esMenor = apoderadoNombre.trim().isNotEmpty;
    final alumno = Alumno(
      id: 'al_${DateTime.now().microsecondsSinceEpoch}',
      academiaId: academiaId,
      nombre: nombre,
      whatsapp: esMenor ? '' : whatsapp,
      email: usuario?.email ?? '', // la CUENTA que administra (titular)
      fotoUrl: esMenor ? null : usuario?.fotoUrl,
      apoderadoNombre: apoderadoNombre.trim(),
      apoderadoWhatsapp: apoderadoWhatsapp.trim(),
      edad: edad,
      sedeId: sedeId,
    );
    alumnos.add(alumno);
    final hoy = DateTime.now();
    // Cuotas de la matrícula (pagadas). Se guardan localmente Y se embeben en la
    // subida para que el PROFE vea, desde su dispositivo, el programa y el pago.
    final nuevasCuotas = <Cuota>[];
    if (plan.tipo == TipoPlan.porClase) {
      nuevasCuotas.add(Cuota(
        id: 'cu_${hoy.microsecondsSinceEpoch}',
        academiaId: academiaId,
        alumnoId: alumno.id,
        concepto:
            '$n clase${n == 1 ? '' : 's'} particular${n == 1 ? '' : 'es'} · ${plan.nombre}',
        monto: precioMes * n,
        vencimiento: hoy,
        pagada: true,
        fechaPago: hoy,
        operacionId: operacionId,
      ));
    } else {
      final meses = (plan.tipo == TipoPlan.mensual ? 1 : plan.meses) * n;
      // Cuántas cuotas quedan PAGADAS ya: todas por defecto; en "mes a mes" solo
      // las primeras [mesesPagados] (típicamente 1), el resto quedan pendientes
      // con su fecha de vencimiento (el débito automático las cobrará su mes).
      final pagadasN = mesesPagados ?? meses;
      for (var i = 0; i < meses; i++) {
        final venc = DateTime(hoy.year, hoy.month + i, hoy.day);
        final pagada = i < pagadasN;
        nuevasCuotas.add(Cuota(
          id: 'cu_${hoy.microsecondsSinceEpoch}_$i',
          academiaId: academiaId,
          alumnoId: alumno.id,
          concepto: '${plan.nombre} · ${_mesNombre(venc)}',
          monto: precioMes,
          vencimiento: venc,
          pagada: pagada,
          fechaPago: pagada ? hoy : null,
          autoDebito: autoDebito,
          operacionId: pagada ? operacionId : '',
        ));
      }
    }
    cuotas.addAll(nuevasCuotas);
    // Sube el alumno con sus cuotas embebidas (cross-device + sobrevive reinstalar).
    MatriculasRepo.guardar(alumno, cuotas: nuevasCuotas);
    notifyListeners();
    _persistirDatos();
    return alumno;
  }

  /// Registra una CLASE SUELTA (drop-in) como cuota por cobrar.
  void agregarClaseSuelta(Alumno alumno, double monto, {String? concepto}) {
    final hoy = DateTime.now();
    cuotas.add(Cuota(
      id: 'cu_${hoy.microsecondsSinceEpoch}',
      academiaId: alumno.academiaId,
      alumnoId: alumno.id,
      concepto: concepto ?? 'Clase suelta ${hoy.day}/${hoy.month}',
      monto: monto,
      vencimiento: hoy,
    ));
    notifyListeners();
    _persistirDatos();
  }

  void marcarCuotaPagada(String cuotaId,
      {bool pagada = true, String operacionId = ''}) {
    final i = cuotas.indexWhere((c) => c.id == cuotaId);
    if (i < 0) return;
    final alumnoId = cuotas[i].alumnoId;
    cuotas[i] = pagada
        ? cuotas[i].copyWith(
            pagada: true,
            fechaPago: DateTime.now(),
            operacionId: operacionId.isEmpty ? null : operacionId)
        : cuotas[i].copyWith(pagada: false, limpiarFechaPago: true);
    notifyListeners();
    _persistirDatos();
    // Propaga el pago al otro lado (alumno ↔ profe) re-subiendo las cuotas del
    // alumno a la nube. El pago es "pegajoso" (una vez pagada, no se revierte).
    if (pagada) _subirCuotasAlumno(alumnoId);
  }

  /// Re-sube a la nube (embebidas en la matrícula) las cuotas actuales de un
  /// alumno, para que el estado de pago se sincronice entre dispositivos.
  void _subirCuotasAlumno(String alumnoId) {
    final ai = alumnos.indexWhere((a) => a.id == alumnoId);
    if (ai < 0) return;
    final sus = cuotas.where((c) => c.alumnoId == alumnoId).toList();
    MatriculasRepo.guardar(alumnos[ai], cuotas: sus);
  }

  /// ¿El alumno está marcado presente ese día?
  bool asistio(String alumnoId, String dia) => asistencias
      .any((a) => a.alumnoId == alumnoId && a.dia == dia && a.presente);

  /// Cuántas clases (días distintos) asistió el alumno.
  int clasesAsistidas(String alumnoId) => asistencias
      .where((a) => a.alumnoId == alumnoId && a.presente)
      .length;

  /// Marca/actualiza la asistencia de un alumno un día (upsert por alumno+día).
  void marcarAsistencia(String academiaId, String alumnoId, String dia,
      bool presente) {
    final i = asistencias
        .indexWhere((a) => a.alumnoId == alumnoId && a.dia == dia);
    final reg = Asistencia(
        academiaId: academiaId,
        alumnoId: alumnoId,
        dia: dia,
        presente: presente);
    if (i >= 0) {
      asistencias[i] = reg;
    } else {
      asistencias.add(reg);
    }
    notifyListeners();
    _persistirDatos();
  }

  static String _mesNombre(DateTime d) {
    const meses = [
      'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio',
      'Agosto', 'Setiembre', 'Octubre', 'Noviembre', 'Diciembre'
    ];
    final i = (d.month - 1).clamp(0, 11);
    return '${meses[i]} ${d.year}';
  }

  /// Radio de búsqueda (km) que el usuario elige: define hasta dónde se
  /// descubren y muestran canchas. Persistente. En el piloto de Chosica el
  /// corredor es largo (Ñaña–Ricardo Palma), por eso el default es amplio.
  double radioBusquedaKm = 20;
  static const double radioMinKm = 2;
  static const double radioMaxKm = 30;

  /// Modo de tema (claro/oscuro/automático). Persistente. Lo consume
  /// `MaterialApp.themeMode` en main.dart vía ListenableBuilder(appState).
  /// Por defecto **claro** (la marca Pichangol es premium-clara: splash verde
  /// lima, fondos blancos). Quien elija "Automático"/"Oscuro" en Ajustes lo
  /// sobreescribe y se respeta (se persiste su elección).
  ThemeMode temaModo = ThemeMode.light;

  /// Cambia el modo de tema, persiste y avisa a la app para redibujar.
  void setTemaModo(ThemeMode modo) {
    if (modo == temaModo) return;
    temaModo = modo;
    notifyListeners();
    _persistirDatos();
  }

  /// Cambia el radio de búsqueda (lo redondea a los límites), persiste y avisa.
  /// Devuelve true si cambió (para que la pantalla vuelva a descubrir).
  bool setRadioBusqueda(double km) {
    final v = km.clamp(radioMinKm, radioMaxKm).toDouble();
    if (v == radioBusquedaKm) return false;
    radioBusquedaKm = v;
    notifyListeners();
    _persistirDatos();
    return true;
  }

  /// Todas las canchas (descubiertas + remotas + locales), sin duplicar por id.
  /// Las registradas se ponen después para que ganen ante una colisión.
  /// NOTA: las canchas demo (SampleData.canchas) ya NO se muestran en el mapa —
  /// el explorador enseña solo canchas reales (Google Places + Supabase + las que
  /// registra el dueño). SampleData queda solo para el panel-demo legado.
  List<Cancha> todasLasCanchas() {
    final map = <String, Cancha>{};
    // Clubes sembrados del piloto (van primero: cualquier versión reclamada
    // que llegue después gana por id/lugar). Se enriquecen con fotos reales.
    for (final c in _sembradas) {
      map[c.id] = c;
    }
    for (final c in canchasDescubiertas) {
      map[c.id] = c;
    }
    for (final c in canchasRemotas) {
      map[c.id] = c;
    }
    for (final c in canchasExtra) {
      map[c.id] = c;
    }
    canchasEliminadas.forEach(map.remove); // borrados durables
    return _quitarDescubiertasReclamadas(_dedupPorLugar(map.values.toList()));
  }

  /// Quita las canchas DESCUBIERTAS (Google) que coinciden en UBICACIÓN con una
  /// cancha ya REGISTRADA (mismo lugar, ya reclamado, aunque el nombre haya
  /// cambiado). Evita que el mismo sitio aparezca dos veces (el pin de Google +
  /// la cancha reclamada) cuando el dueño renombró su cancha.
  List<Cancha> _quitarDescubiertasReclamadas(List<Cancha> canchas) {
    final registradas = canchas.where((c) => c.registrada).toList();
    if (registradas.isEmpty) return canchas;
    return canchas.where((c) {
      if (c.registrada) return true;
      return !registradas.any((r) => _cercaDe(r.ubicacion, c.ubicacion, 0.07));
    }).toList();
  }

  /// Colapsa canchas que son el MISMO lugar pero llegaron por fuentes distintas
  /// con ids diferentes (p. ej. la descubierta en Google + la misma reclamada en
  /// Supabase). Criterio: mismo deporte, nombre normalizado igual y a <120 m.
  /// Se queda con la "mejor": la registrada/reclamada (con dueño y precio real)
  /// gana a la descubierta; a igualdad, la que tiene fotos.
  List<Cancha> _dedupPorLugar(List<Cancha> canchas) {
    final salida = <Cancha>[];
    for (final c in canchas) {
      final clave = _claveLugar(c);
      final i = salida.indexWhere((x) =>
          _claveLugar(x) == clave && _cercaDe(x.ubicacion, c.ubicacion, 0.12));
      if (i < 0) {
        salida.add(c);
      } else if (_puntajeCancha(c) > _puntajeCancha(salida[i])) {
        salida[i] = c; // la nueva es mejor representante del lugar
      }
    }
    return salida;
  }

  String _claveLugar(Cancha c) {
    final n = c.nombre
        .toLowerCase()
        .replaceAll(RegExp(r'[áàä]'), 'a')
        .replaceAll(RegExp(r'[éèë]'), 'e')
        .replaceAll(RegExp(r'[íìï]'), 'i')
        .replaceAll(RegExp(r'[óòö]'), 'o')
        .replaceAll(RegExp(r'[úùü]'), 'u')
        .replaceAll(RegExp(r'[^a-z0-9]'), '');
    return '${c.deporte.name}|$n';
  }

  int _puntajeCancha(Cancha c) {
    var p = 0;
    if (c.verificada) p += 5; // la verificada/activada representa mejor el lugar
    if (c.registrada) p += 4;
    if (c.dueno.isNotEmpty) p += 2;
    if (c.fotos.isNotEmpty) p += 1;
    return p;
  }

  bool _cercaDe(LatLng a, LatLng b, double maxKm) {
    // Aproximación rápida (equirectangular) suficiente para deduplicar a <1 km.
    const kmPorGrado = 111.0;
    final dLat = (a.latitude - b.latitude) * kmPorGrado;
    final dLng = (a.longitude - b.longitude) *
        kmPorGrado *
        math.cos(a.latitude * math.pi / 180);
    return (dLat * dLat + dLng * dLng) <= maxKm * maxKm;
  }

  /// Descubre canchas REALES cerca de [centro] con Google Places y las suma al
  /// mapa como "sin registrar". Fail-safe: si Places no responde, no cambia nada.
  Future<void> descubrirCanchasCerca(LatLng centro) async {
    descubriendo = true;
    notifyListeners(); // muestra el indicador "Buscando canchas cerca de ti…"
    // Fase 1: canchas SIN fotos → respuesta rápida, las tarjetas salen al toque.
    try {
      final rapidas = await PlacesService.canchasCerca(centro,
          conFotos: false, radioMetros: radioBusquedaKm * 1000);
      _agregarDescubiertas(rapidas);
    } catch (_) {
      // fail-safe: si Places no responde, no cambia nada
    } finally {
      descubriendo = false;
      notifyListeners();
    }
    // Fase 2: vuelve a pedir CON fotos y las pinta encima (segundo plano).
    try {
      final conFotos = await PlacesService.canchasCerca(centro,
          conFotos: true, radioMetros: radioBusquedaKm * 1000);
      _fusionarFotos(conFotos);
    } catch (_) {
      // sin fotos, las canchas igual quedan visibles (placeholder de deporte)
    }
  }

  void _agregarDescubiertas(List<Cancha> reales) {
    final existentes = canchasDescubiertas.map((c) => c.id).toSet();
    final nuevas = reales.where((c) => !existentes.contains(c.id)).toList();
    if (nuevas.isNotEmpty) canchasDescubiertas.addAll(nuevas);
  }

  /// Mezcla las fotos resueltas (fase 2) sobre las canchas ya mostradas (fase 1).
  void _fusionarFotos(List<Cancha> conFotos) {
    var cambio = false;
    for (final c in conFotos) {
      final i = canchasDescubiertas.indexWhere((x) => x.id == c.id);
      if (i < 0) {
        canchasDescubiertas.add(c); // cancha nueva que apareció en fase 2
        cambio = true;
      } else if (c.fotos.isNotEmpty) {
        canchasDescubiertas[i] = canchasDescubiertas[i]
            .copyWith(fotos: c.fotos, fotoUrl: c.fotos.first);
        cambio = true;
      }
    }
    if (cambio) notifyListeners();
  }

  /// Trae las reservas compartidas desde Supabase (disponibilidad entre
  /// dispositivos) y recalcula "Mis reservas" según el correo del jugador.
  Future<void> cargarReservasRemotas() async {
    final remotas = await ReservasRepo.fetchRemotas();
    if (remotas.isEmpty) return;
    for (final r in remotas) {
      if (!reservas.any((x) => x.id == r.id)) reservas.insert(0, r);
    }
    _recomputarMisReservas();
    notifyListeners();
  }

  // ── Horarios BLOQUEADOS por el dueño ──────────────────────────────────────
  // Claves "canchaId|fecha|hora" de slots que el dueño cerró (no reservables).
  final Set<String> _bloqueos = {};

  bool estaBloqueado(String canchaId, String fecha, String hora) =>
      _bloqueos.contains(BloqueosRepo.clave(canchaId, fecha, hora));

  /// Carga los bloqueos desde la nube (al abrir una ficha de cancha).
  Future<void> cargarBloqueos() async {
    final s = await BloqueosRepo.fetch();
    _bloqueos
      ..clear()
      ..addAll(s);
    notifyListeners();
  }

  /// El dueño bloquea/desbloquea un horario. Actualiza al instante y sincroniza.
  Future<void> alternarBloqueo(
      String canchaId, String fecha, String hora) async {
    final k = BloqueosRepo.clave(canchaId, fecha, hora);
    if (_bloqueos.contains(k)) {
      _bloqueos.remove(k);
      notifyListeners();
      await BloqueosRepo.desbloquear(canchaId, fecha, hora);
    } else {
      _bloqueos.add(k);
      notifyListeners();
      await BloqueosRepo.bloquear(canchaId, fecha, hora);
    }
  }

  // ── RESEÑAS de canchas (⭐ real) ──────────────────────────────────────────
  // Cache por cancha_id (se llena al abrir una ficha).
  final Map<String, List<Resena>> _resenas = {};

  /// Carga las reseñas de todas las canchas de un local (una consulta).
  Future<void> cargarResenas(List<String> canchaIds) async {
    if (canchaIds.isEmpty) return;
    final rows = await ResenasRepo.deCanchas(canchaIds);
    for (final id in canchaIds) {
      _resenas[id] = rows.where((r) => r.canchaId == id).toList();
    }
    notifyListeners();
  }

  /// Reseñas cacheadas de un conjunto de canchas, más nuevas primero.
  List<Resena> resenasDe(List<String> canchaIds) {
    final out = <Resena>[];
    for (final id in canchaIds) {
      final l = _resenas[id];
      if (l != null) out.addAll(l);
    }
    out.sort((a, b) => b.creado.compareTo(a.creado));
    return out;
  }

  /// Promedio + cantidad de reseñas de un local.
  ResumenResenas resumenResenas(List<String> canchaIds) {
    final l = resenasDe(canchaIds);
    if (l.isEmpty) return const ResumenResenas(0, 0);
    final suma = l.fold<int>(0, (a, r) => a + r.estrellas);
    return ResumenResenas(suma / l.length, l.length);
  }

  /// La reseña del usuario logueado en este local (para editarla), si existe.
  Resena? miResena(List<String> canchaIds) {
    final email = usuario?.email.trim().toLowerCase();
    if (email == null || email.isEmpty) return null;
    for (final r in resenasDe(canchaIds)) {
      if (r.autorEmail.trim().toLowerCase() == email) return r;
    }
    return null;
  }

  /// El jugador dejó (o editó) su reseña de una cancha. Optimista: actualiza la
  /// cache al instante y sincroniza a Supabase.
  Future<bool> enviarResena(
      String canchaId, int estrellas, String comentario) async {
    final u = usuario;
    if (u == null || u.email.isEmpty) return false;
    final r = Resena(
      id: 'res_${u.email.hashCode.toUnsigned(20).toRadixString(16)}_$canchaId',
      canchaId: canchaId,
      autorEmail: u.email.trim().toLowerCase(),
      autorNombre: u.nombre,
      estrellas: estrellas.clamp(1, 5),
      comentario: comentario.trim(),
      creado: DateTime.now(),
    );
    // Optimista: reemplaza la reseña previa del autor en esa cancha.
    final lista = [..._resenas[canchaId] ?? const <Resena>[]]
      ..removeWhere((x) => x.autorEmail.toLowerCase() == r.autorEmail)
      ..insert(0, r);
    _resenas[canchaId] = lista;
    notifyListeners();
    return ResenasRepo.enviar(r);
  }

  /// Mis reservas = reservas cuyo correo coincide con el jugador logueado.
  void _recomputarMisReservas() {
    final email = usuario?.email;
    if (email == null || email.isEmpty) return;
    for (final r in reservas) {
      if (r.usuario == email && !misReservas.any((x) => x.id == r.id)) {
        misReservas.insert(0, r);
      }
    }
  }

  /// Trae las canchas compartidas desde Supabase (si está disponible).
  Future<void> cargarCanchasRemotas() async {
    final remotas = await CanchasRepo.fetchRemotas();
    if (remotas.isNotEmpty) {
      canchasRemotas
        ..clear()
        ..addAll(remotas.where((c) => !canchasEliminadas.contains(c.id)));
      _repararClubLegado();
      notifyListeners();
    }
  }

  /// Repara datos viejos: canchas registradas por el dueño que quedaron con el
  /// nombre del club DEMO ("Club Raqueta San Borja") por un bug anterior. Les
  /// pone como club su propio nombre (base, sin el sufijo de deporte) para que
  /// dejen de agruparse/mostrarse con el club de muestra. Persiste el arreglo.
  bool _repararClubLegado() {
    String base(String nombre) =>
        nombre.split(RegExp(r'\s[·\-–]\s')).first.trim();
    var cambio = false;
    for (var i = 0; i < canchasExtra.length; i++) {
      final c = canchasExtra[i];
      if (c.club == SampleData.clubActivo) {
        canchasExtra[i] = c.copyWith(club: base(c.nombre));
        cambio = true;
      }
    }
    for (var i = 0; i < canchasRemotas.length; i++) {
      final c = canchasRemotas[i];
      if (c.club == SampleData.clubActivo && c.dueno.isNotEmpty) {
        final fixed = c.copyWith(club: base(c.nombre));
        canchasRemotas[i] = fixed;
        CanchasRepo.actualizar(fixed); // persiste el arreglo en la nube
        cambio = true;
      }
    }
    if (cambio) _persistirDatos();
    return cambio;
  }

  /// Sincroniza la PROPIEDAD con el backend: para cada cancha mía que sigue
  /// "pendiente de verificación", pregunta al growth si el admin ya la aprobó
  /// (estado activada / verificada). Si sí, la marca verificada en el dispositivo
  /// y en Supabase, con lo que se quita el cartel "pendiente" y se habilitan las
  /// reservas. Es el puente que faltaba entre el panel del admin y la app.
  /// Fail-safe: si el backend no responde, no cambia nada.
  Future<void> sincronizarPropiedades() async {
    if (!PropiedadService.disponible) return;
    var cambio = false;
    // Candidatas: TODAS mis canchas reclamadas + legado reclamable (registradas,
    // no eliminadas). Se toman de las listas CRUDAS (no de misCanchas, que
    // deduplica) para procesar también los DUPLICADOS del mismo lugar en una sola
    // pasada. Se consultan en ambos sentidos: promover (aprobada → verificada) y
    // degradar (rechazada → deja de ser mía / se quitan las reservas).
    final email = usuario?.email ?? '';
    final vistos = <String>{};
    final candidatas = <Cancha>[];
    for (final c in [...canchasExtra, ...canchasRemotas]) {
      if (!c.registrada || canchasEliminadas.contains(c.id)) continue;
      final mia = email.isNotEmpty && c.dueno == email;
      final legado = c.dueno.isEmpty && !c.verificada;
      if (!(mia || legado)) continue;
      if (vistos.add(c.id)) candidatas.add(c);
    }
    for (final c in candidatas) {
      final est =
          await PropiedadService.estado(c.id, solicitante: usuario?.email);
      if (est == null || est['existe'] != true) continue;
      final verificada =
          est['verificada'] == true || est['estado'] == 'activada';
      final rechazada = est['estado'] == 'rechazada';

      Cancha? actualizada;
      if (rechazada && est['es_mio'] == true) {
        // MI reclamo fue RECHAZADO y no hay uno vigente del mismo lugar (el
        // backend prioriza un reclamo activo por encima de un rechazo viejo): la
        // cancha deja de ser mía y VUELVE A SER DESCUBIERTA (como si nadie la
        // hubiera reclamado). Sale de "Mis canchas" pero sigue en el mapa,
        // reclamable de nuevo. Se cancelan sus reservas.
        actualizada =
            c.copyWith(registrada: false, verificada: false, dueno: '');
        _cancelarReservasDeCancha(c.id);
      } else if (verificada && !c.verificada) {
        // Al activarse queda atada a su dueño. Solo me asigno como dueño si el
        // backend confirma que YO soy el reclamante (est['es_mio']); así una
        // cancha de "legado" no la apropia quien sincroniza primero.
        final nuevoDueno = c.dueno.isNotEmpty
            ? c.dueno
            : (est['es_mio'] == true ? (usuario?.email ?? '') : '');
        actualizada = c.copyWith(verificada: true, dueno: nuevoDueno);
      } else if ((rechazada || !verificada) && c.verificada) {
        // El admin rechazó/revocó el reclamo: la cancha vuelve a NO verificada
        // (se cae "Verificada", se deshabilitan las reservas) y se CANCELAN las
        // reservas ya tomadas (la cancha dejó de ser válida).
        actualizada = c.copyWith(verificada: false);
        _cancelarReservasDeCancha(c.id);
      }
      if (actualizada == null) continue;

      final i = canchasExtra.indexWhere((x) => x.id == c.id);
      if (i >= 0) canchasExtra[i] = actualizada;
      final j = canchasRemotas.indexWhere((x) => x.id == c.id);
      if (j >= 0) canchasRemotas[j] = actualizada;
      CanchasRepo.actualizar(actualizada); // refleja en la nube (best-effort)
      cambio = true;
    }
    if (cambio) {
      _persistirDatos();
      notifyListeners();
    }
  }

  /// Sincroniza el estado de UNA cancha concreta (la que se está mostrando),
  /// aunque no sea "mía". Sirve para que la ficha de una cancha ya verificada se
  /// DEGRADE si el admin la rechazó/revocó (la corrección a5d4e00 solo cubría
  /// `misCanchas`, dejando la ficha de terceros mostrando horarios de una cancha
  /// rechazada). Devuelve la cancha actualizada si cambió, o null. No auto-asigna
  /// dueño (evita apropiación por quien sincroniza).
  Future<Cancha?> sincronizarCanchaMostrada(Cancha c) async {
    if (!PropiedadService.disponible || !c.registrada) return null;
    if (canchasEliminadas.contains(c.id)) return null;
    final est = await PropiedadService.estado(c.id);
    if (est == null || est['existe'] != true) return null;
    final verificada = est['verificada'] == true || est['estado'] == 'activada';
    final rechazada = est['estado'] == 'rechazada';
    Cancha? actualizada;
    if (verificada && !c.verificada) {
      actualizada = c.copyWith(verificada: true);
    } else if ((rechazada || !verificada) && c.verificada) {
      actualizada = c.copyWith(verificada: false);
      _cancelarReservasDeCancha(c.id); // cancha rechazada: cancela sus reservas
    }
    if (actualizada == null) return null;
    final i = canchasExtra.indexWhere((x) => x.id == c.id);
    if (i >= 0) canchasExtra[i] = actualizada;
    final j = canchasRemotas.indexWhere((x) => x.id == c.id);
    if (j >= 0) canchasRemotas[j] = actualizada;
    CanchasRepo.actualizar(actualizada); // propaga a Supabase (best-effort)
    _persistirDatos();
    notifyListeners();
    return actualizada;
  }

  /// Cancela (elimina) las reservas de una cancha degradada/rechazada: se libera
  /// el slot y desaparecen de "Mis reservas" y del panel del dueño. Best-effort
  /// en la nube (borra en Supabase).
  void _cancelarReservasDeCancha(String canchaId) {
    final habia = reservas.any((r) => r.canchaId == canchaId) ||
        misReservas.any((r) => r.canchaId == canchaId);
    if (!habia) return;
    reservas.removeWhere((r) => r.canchaId == canchaId);
    misReservas.removeWhere((r) => r.canchaId == canchaId);
    ReservasRepo.eliminarDeCancha(canchaId); // borra en Supabase (best-effort)
  }

  /// Registra una cancha nueva (desde el flujo con detección por IA).
  /// Queda local (se ve al toque) y se sube a Supabase para compartirla.
  void agregarCancha(Cancha c) {
    canchasEliminadas.remove(c.id); // si se re-registra, deja de estar eliminada
    canchasExtra.insert(0, c);
    notifyListeners();
    _persistirDatos();
    CanchasRepo.insertar(c); // best-effort, compartir entre dispositivos
  }

  /// Canchas del dueño para "Mis canchas" (su panel de control). Reglas de
  /// PROPIEDAD:
  ///  - Es mía si `dueno == mi correo`.
  ///  - "Legado reclamable": registrada, SIN dueño y **aún no verificada** →
  ///    visible para que cualquiera la pueda reclamar/editar.
  ///  - Una vez **verificada/activada**, queda atada a su dueño: ningún otro
  ///    usuario ve su panel de control.
  List<Cancha> get misCanchas {
    final email = usuario?.email ?? '';
    bool visible(Cancha c) {
      if (email.isNotEmpty && c.dueno == email) return true; // es mía
      if (email.isEmpty && c.dueno.isEmpty) return true; // sin sesión, alta local
      // Legado: sin dueño, registrada y todavía NO verificada (reclamable).
      if (c.dueno.isEmpty && c.registrada && !c.verificada) return true;
      return false;
    }

    final map = <String, Cancha>{};
    for (final c in [...canchasRemotas, ...canchasExtra]) {
      if (visible(c)) map[c.id] = c;
    }
    canchasEliminadas.forEach(map.remove); // no mostrar lo eliminado
    // Colapsa duplicados del MISMO lugar (varios ids por re-registrar/re-reclamar
    // la misma cancha en pruebas): que no aparezca "Sabor Golazo" 3 veces.
    return _dedupPorLugar(map.values.toList());
  }

  /// Edita una cancha del dueño (local + nube). Funciona aunque la cancha venga
  /// solo de Supabase (tras reinstalar): la refleja también en `canchasRemotas`.
  void actualizarCancha(Cancha c) {
    canchasEliminadas.remove(c.id); // editar/reclamar una cancha la "revive"
    final i = canchasExtra.indexWhere((x) => x.id == c.id);
    if (i >= 0) {
      canchasExtra[i] = c;
    } else {
      canchasExtra.insert(0, c);
    }
    final j = canchasRemotas.indexWhere((x) => x.id == c.id);
    if (j >= 0) canchasRemotas[j] = c;
    notifyListeners();
    _persistirDatos();
    CanchasRepo.actualizar(c); // best-effort
  }

  /// Renombra el LOCAL: cambia `club` en TODAS las canchas del dueño que tenían
  /// el nombre anterior, para que sigan agrupadas bajo el nuevo nombre. Así,
  /// renombrar el local no separa sus canchas. Best-effort en la nube.
  void renombrarLocal(String clubAnterior, String clubNuevo) {
    final nuevo = clubNuevo.trim();
    if (nuevo.isEmpty || nuevo == clubAnterior) return;
    void aplicar(List<Cancha> lista) {
      for (var i = 0; i < lista.length; i++) {
        if (lista[i].club == clubAnterior) {
          final f = lista[i].copyWith(club: nuevo);
          lista[i] = f;
          CanchasRepo.actualizar(f); // persiste en la nube
        }
      }
    }

    aplicar(canchasExtra);
    aplicar(canchasRemotas);
    notifyListeners();
    _persistirDatos();
  }

  /// Los SERVICIOS (amenities: vestuario, parking, luces…) son del LOCAL, no de
  /// una cancha puntual: se aplican a TODAS las canchas del local. Best-effort
  /// en la nube.
  void actualizarServiciosLocal(String club, List<String> amenidades) {
    final lista = List<String>.of(amenidades);
    void aplicar(List<Cancha> canchas) {
      for (var i = 0; i < canchas.length; i++) {
        if (canchas[i].club == club) {
          final f = canchas[i].copyWith(amenidades: lista);
          canchas[i] = f;
          CanchasRepo.actualizar(f);
        }
      }
    }

    aplicar(canchasExtra);
    aplicar(canchasRemotas);
    notifyListeners();
    _persistirDatos();
  }

  /// Verifica la EXISTENCIA de una cancha contra el backend. **Importante:**
  /// existencia ≠ propiedad. Que un RUC sea válido en SUNAT (o que la IA confirme
  /// que el local existe) sólo prueba que el establecimiento es real, **no** que
  /// quien reclama sea el dueño. Por eso este método NUNCA marca la cancha como
  /// `verificada` (eso habilitaría reservas y daría el control al reclamante).
  /// La propiedad se confirma aparte —código al teléfono del local (OTP),
  /// aprobación manual o visita física del verificador— vía [confirmarPropiedad].
  /// Devuelve el resultado de existencia (informativo). Pensado para correr en
  /// segundo plano tras registrar/reclamar.
  Future<ResultadoExistencia?> verificarCancha(Cancha c,
      {String? ruc, String? razonSocial}) async {
    // Carril informal (backend/growth): IA primero; si no concluye, agenda visita.
    if (GrowthService.disponible) {
      final rf = await GrowthService.evaluarFisica(
        canchaId: c.id,
        direccion: c.direccion ?? c.nombre,
        ruc: ruc,
        ubicacion: c.ubicacion,
      );
      if (rf != null) {
        // NO se marca verificada: existencia confirmada, propiedad pendiente.
        return ResultadoExistencia(
          score: rf.score,
          aprobado: rf.verificada,
          nivel: 'pendiente_propiedad',
          justificacion: rf.verificada
              ? 'Existencia confirmada. Falta validar que eres el dueño.'
              : 'Pendiente: se agendó una visita para validar el local.',
        );
      }
    }
    // Fallback: verificación de existencia directa (tampoco confirma propiedad).
    final res = await VerificacionService.verificarExistencia(
      canchaId: c.id,
      direccion: c.direccion ?? c.nombre,
      ruc: ruc,
      razonSocial: razonSocial ?? c.nombre,
      ubicacion: c.ubicacion,
    );
    return res;
  }

  /// Verifica la EXISTENCIA de un LOCAL completo (varias canchas en el mismo
  /// punto/dirección) en una sola consulta. Igual que [verificarCancha]: confirma
  /// existencia, **no** propiedad, por lo que no marca ninguna cancha como
  /// verificada. La propiedad se valida aparte con [confirmarPropiedad].
  Future<ResultadoExistencia?> verificarVenue(List<Cancha> canchas,
      {String? ruc, String? razonSocial}) async {
    if (canchas.isEmpty) return null;
    final base = canchas.first;

    // Carril informal (backend/growth) para todo el local.
    if (GrowthService.disponible) {
      final rf = await GrowthService.evaluarFisica(
        canchaId: base.id,
        direccion: base.direccion ?? base.nombre,
        ruc: ruc,
        ubicacion: base.ubicacion,
      );
      if (rf != null) {
        // NO se marcan verificadas: existencia confirmada, propiedad pendiente.
        return ResultadoExistencia(
          score: rf.score,
          aprobado: rf.verificada,
          nivel: 'pendiente_propiedad',
          justificacion: rf.verificada
              ? 'Existencia confirmada. Falta validar que eres el dueño.'
              : 'Pendiente: se agendó una visita para validar el local.',
        );
      }
    }

    // Fallback: verificación de existencia directa (tampoco confirma propiedad).
    final res = await VerificacionService.verificarExistencia(
      canchaId: base.id,
      direccion: base.direccion ?? base.nombre,
      ruc: ruc,
      razonSocial: razonSocial ?? base.nombre,
      ubicacion: base.ubicacion,
    );
    return res;
  }

  /// Confirma la **PROPIEDAD** de una cancha (no su existencia). Sólo este camino
  /// habilita reservas (`verificada: true`) y debe llamarse cuando el dueño probó
  /// que controla el local: código OTP al teléfono registrado del establecimiento,
  /// aprobación manual del equipo, o visita física confirmada por el verificador.
  /// Un RUC válido por sí solo NUNCA llega aquí.
  void confirmarPropiedad(String canchaId,
      {String via = 'manual', String? dueno}) {
    Cancha? actual;
    for (final c in [...canchasExtra, ...canchasRemotas]) {
      if (c.id == canchaId) {
        actual = c;
        break;
      }
    }
    if (actual == null) return;
    actualizarCancha(actual.copyWith(
      verificada: true,
      dueno: dueno ?? actual.dueno,
    ));
  }

  /// Elimina una cancha del dueño (local + nube). Quita también de la lista
  /// remota para que desaparezca al instante aunque viniera solo de Supabase.
  void eliminarCancha(String id) {
    canchasEliminadas.add(id); // tombstone durable (sobrevive reinicios y re-fetch)
    canchasExtra.removeWhere((x) => x.id == id);
    canchasRemotas.removeWhere((x) => x.id == id);
    notifyListeners();
    _persistirDatos();
    CanchasRepo.eliminar(id); // borrado lógico durable en la nube (sobrevive reinstalar)
  }

  // Saldo prepago del club (modelo inDrive): con saldo aparece destacado y
  // cada reserva nueva descuenta una comisión. Sin saldo, deja de destacarse.
  int saldoClub = 30;
  // ¿Ya se le mostró al dueño el mensaje de bienvenida (onboarding "stack de
  // valor")? Se muestra una sola vez al entrar a "Mis canchas".
  bool bienvenidaDuenoVista = false;
  void marcarBienvenidaDueno() {
    if (bienvenidaDuenoVista) return;
    bienvenidaDuenoVista = true;
    _persistirDatos();
  }

  // Verificación de identidad del jugador: 'no' | 'en_revision' | 'verificado'.
  String estadoVerificacion = 'no';
  bool get jugadorVerificado => estadoVerificacion == 'verificado';

  /// Sincroniza el estado de verificación desde el backend (best-effort).
  Future<void> sincronizarVerificacion() async {
    final email = usuario?.email;
    if (email == null || email.isEmpty) return;
    final st = await VerificacionRepo.estadoDe(email);
    if (st != estadoVerificacion) {
      estadoVerificacion = st;
      notifyListeners();
      _persistirDatos();
    }
  }

  // Cache de qué correos de OTROS jugadores están verificados (para que el
  // dueño vea la insignia junto a cada jugador en reservas/chat).
  final Set<String> _verificados = {};
  bool estaVerificado(String email) =>
      _verificados.contains(email.trim().toLowerCase());

  /// Consulta y cachea qué correos del conjunto están verificados.
  Future<void> sincronizarVerificados(Iterable<String> emails) async {
    final pedir = emails
        .map((e) => e.trim().toLowerCase())
        .where((e) => e.isNotEmpty)
        .toSet();
    if (pedir.isEmpty) return;
    final set = await VerificacionRepo.verificados(pedir.toList());
    if (set.isNotEmpty) {
      _verificados.addAll(set);
      notifyListeners();
    }
  }

  /// Envía doc + selfie para verificar la identidad. Devuelve true si quedó
  /// registrada (piloto: auto-aprobada).
  Future<bool> enviarVerificacion(Uint8List doc, Uint8List selfie) async {
    final u = usuario;
    if (u == null) return false;
    final st = await VerificacionRepo.enviar(
        email: u.email, nombre: u.nombre, doc: doc, selfie: selfie);
    if (st == null) return false;
    estadoVerificacion = st;
    notifyListeners();
    _persistirDatos();
    return true;
  }

  // Moneda del saldo prepago del dueño: se congela con la primera recarga (el
  // país donde puso plata) y no cambia aunque el dueño abra la app en otro país.
  String monedaSaldo = '';
  String get monedaSaldoSimbolo {
    if (monedaSaldo.isNotEmpty) return monedaSaldo;
    // Sin moneda congelada aún: usa la de las canchas del dueño (no la del GPS),
    // así un dueño de Perú ve S/ aunque abra la app desde Bolivia.
    final mis = misCanchas;
    if (mis.isNotEmpty) return mis.first.monedaSimbolo;
    return paisActual.moneda;
  }
  final List<MovimientoSaldo> movimientos = [
    const MovimientoSaldo(
        tipo: TipoMovimiento.recarga, monto: 30, concepto: 'Recarga inicial', cuando: 'Ayer'),
  ];
  bool get destacadoActivo => saldoClub > 0;

  // ── Saldo por PAÍS (destacar multi-país) ──────────────────────────────────
  // Un dueño puede tener canchas en Perú y Bolivia a la vez. El saldo no se
  // puede mezclar (S/ ≠ Bs): cada país lleva su propia bolsa y se destaca con la
  // de ese país. Perú vive en `saldoClub` (respaldado por el backend Culqi);
  // los demás países viven aquí hasta enchufar su pasarela (#35 Libélula).
  final Map<String, int> _saldoOtrosPaises = {};

  /// Países (ISO) donde el dueño tiene canchas, según la ubicación REAL de cada
  /// una (no el GPS del dispositivo). Ordenados por cantidad de canchas (el país
  /// con más, primero). Alimenta el selector de "Recargar y destacar".
  List<String> get paisesDeMisCanchas {
    final conteo = <String, int>{};
    for (final c in misCanchas) {
      final iso =
          paisDeCoordenadas(c.ubicacion.latitude, c.ubicacion.longitude).iso;
      conteo[iso] = (conteo[iso] ?? 0) + 1;
    }
    final isos = conteo.keys.toList()
      ..sort((a, b) => conteo[b]!.compareTo(conteo[a]!));
    return isos;
  }

  /// Saldo prepago del dueño en un país (ISO). Perú = `saldoClub` (backend);
  /// otros países = su bolsa local (0 hasta integrar su pasarela).
  int saldoDePais(String iso) =>
      iso == 'PE' ? saldoClub : (_saldoOtrosPaises[iso] ?? 0);

  /// Recarga el saldo del país indicado con la pasarela que le corresponde.
  /// Perú pasa por Culqi (`recargar`); los demás acreditan en su bolsa local.
  void recargarPais(String iso, int monto) {
    if (monto <= 0) return;
    if (iso == 'PE') {
      recargar(monto);
      return;
    }
    _saldoOtrosPaises[iso] = (_saldoOtrosPaises[iso] ?? 0) + monto;
    notifyListeners();
    _persistirDatos();
  }

  /// Nivel de destacado del PROPIO dueño por su saldo (mismos umbrales que el
  /// backend): 0 = no, 1 bronce (>0), 2 plata (>=50), 3 oro (>=200).
  int get nivelDestacadoPropio {
    if (saldoClub >= 200) return 3;
    if (saldoClub >= 50) return 2;
    if (saldoClub > 0) return 1;
    return 0;
  }

  // ── Dueños DESTACADOS (saldo prepago > 0) → nivel (1-3) ───────────────────
  // Se resalta a sus canchas en Explorar: más saldo = más visibilidad (el
  // beneficio que la plataforma le da al dueño). Se carga del backend; los
  // demás usuarios lo leen para saber qué canchas van destacadas.
  Map<String, int> _destacadosPorDueno = {};

  /// Nivel de destacado de una cancha (por el saldo de su dueño). 0 = no.
  int nivelDestacado(Cancha c) {
    final d = c.dueno.toLowerCase().trim();
    if (d.isEmpty) return 0;
    return _destacadosPorDueno[d] ?? 0;
  }

  bool esDestacada(Cancha c) => nivelDestacado(c) > 0;

  /// Nivel de destacado de una ACADEMIA. BILLETERA ÚNICA: sale del saldo del
  /// DUEÑO (su correo), igual que sus canchas. Durante la transición, si el
  /// saldo aún no se consolidó, cae al que quedó bajo el id de la academia (se
  /// toma el mayor de ambos). 0 = no destacada.
  int nivelDestacadoAcademia(Academia a) {
    final email = a.dueno.toLowerCase().trim();
    final id = a.id.toLowerCase().trim();
    final porCorreo = email.isEmpty ? 0 : (_destacadosPorDueno[email] ?? 0);
    final porId = id.isEmpty ? 0 : (_destacadosPorDueno[id] ?? 0);
    return porCorreo > porId ? porCorreo : porId;
  }

  bool esDestacadaAcademia(Academia a) => nivelDestacadoAcademia(a) > 0;

  Academia? _academiaPorId(String id) {
    for (final a in academias) {
      if (a.id == id) return a;
    }
    return null;
  }

  /// Saldo prepago que ve una academia. BILLETERA ÚNICA: es el mismo saldo del
  /// DUEÑO (su correo), por país, que se ve en "Mi cuenta" —no una bolsa aparte.
  int saldoAcademiaDe(String academiaId) {
    final a = _academiaPorId(academiaId);
    return saldoDePais(a?.pais.iso ?? 'PE');
  }

  /// Sincroniza el saldo de la academia con la BILLETERA ÚNICA del dueño. Primero
  /// CONSOLIDA (junta el saldo que hubiera quedado bajo el id de la academia en la
  /// billetera del correo del dueño; idempotente) y luego refresca el saldo del
  /// correo. Solo corre en el panel del dueño (best-effort).
  Future<void> sincronizarSaldoAcademia(String academiaId) async {
    if (!PagosService.disponible || academiaId.isEmpty) return;
    final a = _academiaPorId(academiaId);
    final email =
        ((a?.dueno.isNotEmpty ?? false) ? a!.dueno : (usuario?.email ?? ''))
            .trim();
    if (email.isEmpty) return;
    await PagosService.consolidarSaldo(academiaId, email);
    // Refresca la billetera del correo (Perú vive en saldoClub, respaldado por
    // el backend). Los demás países usan su bolsa local, ya per-usuario.
    await sincronizarSaldo();
    notifyListeners();
  }

  /// Trae del backend el conjunto de dueños destacados (best-effort). Si el
  /// dueño logueado tiene saldo, se asegura de incluirse aunque el backend
  /// tarde en propagar (para que vea su propia cancha destacada al instante).
  Future<void> cargarDestacados() async {
    if (!PagosService.disponible) return;
    final m = await PagosService.destacados();
    if (m == null) return;
    // Normaliza las llaves a minúsculas (los correos pueden venir con distinta
    // caja): así el lookup por dueño/academia es consistente.
    final norm = <String, int>{};
    m.forEach((k, v) {
      final key = k.toLowerCase().trim();
      final nivel = norm[key] ?? 0;
      if (v > nivel) norm[key] = v; else norm.putIfAbsent(key, () => v);
    });
    final email = usuario?.email?.toLowerCase().trim();
    if (email != null && email.isNotEmpty && saldoClub > 0) {
      norm.putIfAbsent(email, () => 1);
    }
    _destacadosPorDueno = norm;
    notifyListeners();
  }

  /// Comisión que descuenta del saldo cada reserva nueva (5%, mínimo $monedaSimbolo 2).
  int comisionDe(num precio) {
    final c = (precio * 0.05).round();
    return c < 2 ? 2 : c;
  }

  // ── PICHANGOL PRO (membresía del jugador) ──────────────────────────────────
  bool proActivo = false; // ¿el usuario tiene la membresía Pro vigente?
  String? proHasta; // ISO de vigencia (si activa)
  double proPrecio = 12; // precio mensual (se refresca del backend)

  // Correos con Pichangol Pro vigente (para la insignia PRO en el ranking).
  Set<String> _proEmails = {};

  /// ¿Este correo tiene Pichangol Pro vigente? (para pintar la insignia PRO).
  bool esProEmail(String? email) {
    final e = (email ?? '').trim().toLowerCase();
    return e.isNotEmpty && _proEmails.contains(e);
  }

  /// Trae del backend los correos Pro para pintar la insignia en el ranking.
  Future<void> cargarMiembrosPro() async {
    final l = await PagosService.proMiembros();
    _proEmails = l.map((e) => e.toLowerCase()).toSet();
    notifyListeners();
  }

  /// Sincroniza el estado Pro del usuario con el backend (best-effort).
  Future<void> sincronizarPro() async {
    final email = usuario?.email;
    if (email == null || email.isEmpty || !PagosService.disponible) return;
    final est = await PagosService.proEstado(email, pais: paisActual.iso);
    if (est == null) return;
    proActivo = est['activa'] == true;
    proHasta = est['hasta'] as String?;
    proPrecio = (est['precio_soles'] as num?)?.toDouble() ?? proPrecio;
    // Mantén el set de Pro coherente con mi propio estado al instante.
    final mail = email.trim().toLowerCase();
    if (proActivo) {
      _proEmails = {..._proEmails, mail};
    } else {
      _proEmails = _proEmails.where((e) => e != mail).toSet();
    }
    notifyListeners();
  }

  /// Activa/renueva Pro debitando 1 mes del saldo (billetera única). Devuelve el
  /// resultado del backend: {ok:true,...} o {ok:false, falta_saldo:true,...}.
  Future<Map<String, dynamic>> suscribirPro() async {
    final email = usuario?.email ?? '';
    if (email.isEmpty) return {'ok': false, 'error': 'Inicia sesión primero.'};
    final r = await PagosService.proSuscribir(email, pais: paisActual.iso);
    if (r['ok'] == true) {
      proActivo = true;
      proHasta = r['hasta'] as String?;
      notifyListeners();
      await sincronizarSaldo(); // el saldo bajó (se debitó el mes)
    }
    return r;
  }

  /// Sincroniza el saldo con el BACKEND (fuente de verdad de los pagos reales).
  /// El saldo local solo vive en el teléfono, así que en una instalación limpia
  /// se pierde; el backend guarda las recargas por dueño (email). Best-effort:
  /// si el backend no responde o no hay sesión, conserva el saldo local.
  Future<void> sincronizarSaldo() async {
    final email = usuario?.email;
    if (email == null || email.isEmpty) return;
    if (!PagosService.disponible) return;
    final s = await PagosService.saldo(email);
    if (s != null) {
      final nuevo = s.round();
      if (nuevo != saldoClub) {
        saldoClub = nuevo;
        notifyListeners();
        _persistirDatos();
      }
    }
    // Historial de movimientos del backend (recargas): sobrevive a reinstalar,
    // a diferencia del historial local del teléfono. Si el backend responde con
    // recargas, reemplaza la lista local (que solo tenía la "Recarga inicial"
    // de demo). Si no hay ninguna o el backend no responde, conserva lo local.
    final movs = await PagosService.movimientos(email);
    if (movs != null && movs.isNotEmpty) {
      movimientos
        ..clear()
        ..addAll(movs.map((m) {
          final tipoStr = (m['tipo'] as String?) ?? 'recarga';
          // Egresos de la billetera (Pro, servicios, torneo, comisión) → consumo.
          final tipo = switch (tipoStr) {
            'comision_reserva' ||
            'suscripcion' ||
            'suscripcion_pro' ||
            'inscripcion_torneo' =>
              TipoMovimiento.consumo,
            'liquidacion_online' => TipoMovimiento.liquidacion,
            _ => TipoMovimiento.recarga, // recarga, inscripcion_torneo_ingreso
          };
          var concepto = (m['concepto'] as String?) ?? '';
          if (tipoStr == 'liquidacion_online') {
            final com = (m['comision_soles'] as num?)?.round();
            final txt = 'comisión $monedaSaldoSimbolo$com';
            concepto = concepto.isEmpty ? 'Reserva online · $txt' : '$concepto · $txt';
          } else if (concepto.isEmpty) {
            concepto = tipo == TipoMovimiento.consumo
                ? 'Consumo de saldo'
                : 'Recarga de saldo';
          }
          final montoExacto = (m['monto_soles'] as num?)?.toDouble() ?? 0;
          return MovimientoSaldo(
            // El signo lo pone el tipo en la UI; el monto (lista) va en positivo.
            tipo: tipo,
            monto: montoExacto.abs().round(),
            concepto: concepto,
            cuando: _fechaRelativa(m['creado_en'] as String?),
            liquidado: (m['liquidado'] ?? false) as bool,
            montoSoles: montoExacto,
            comprobante: ((m['comprobante'] ?? 0) as num).toInt(),
            fechaIso: (m['creado_en'] as String?) ?? '',
          );
        }));
      notifyListeners();
      _persistirDatos();
    }
  }

  /// Convierte una fecha ISO en una etiqueta corta para el historial de saldo:
  /// "Hoy" / "Ayer" / "dd/mm". Vacío si no se puede parsear.
  String _fechaRelativa(String? iso) {
    if (iso == null || iso.isEmpty) return '';
    final d = DateTime.tryParse(iso);
    if (d == null) return '';
    final hoy = DateTime.now();
    final dia = DateTime(d.year, d.month, d.day);
    final base = DateTime(hoy.year, hoy.month, hoy.day);
    final diff = base.difference(dia).inDays;
    if (diff <= 0) return 'Hoy';
    if (diff == 1) return 'Ayer';
    return '${d.day.toString().padLeft(2, '0')}/${d.month.toString().padLeft(2, '0')}';
  }

  // ── REFERIDOS (invita y gana) ─────────────────────────────────────────────
  /// Bono (en la moneda local) que gana cada lado de un referido.
  static const bonoReferido = 10;

  /// Código de referido del usuario: estable y derivado de su correo.
  String get codigoReferido {
    final e = usuario?.email.trim().toLowerCase() ?? '';
    if (e.isEmpty) return '';
    final h = e.codeUnits.fold<int>(7, (a, b) => (a * 31 + b) & 0x7fffffff);
    final s = h.toRadixString(36).toUpperCase().padLeft(6, '0');
    return 'PCG${s.substring(s.length - 6)}';
  }

  /// Acredita un bono de saldo en el país actual (+ movimiento).
  void _acreditarBono(int monto, String concepto) {
    if (monto <= 0) return;
    if (monedaSaldo.isEmpty) monedaSaldo = paisActual.moneda;
    final iso = paisActual.iso;
    if (iso == 'PE') {
      saldoClub += monto;
    } else {
      _saldoOtrosPaises[iso] = (_saldoOtrosPaises[iso] ?? 0) + monto;
    }
    movimientos.insert(
      0,
      MovimientoSaldo(
          tipo: TipoMovimiento.recarga,
          monto: monto,
          concepto: concepto,
          cuando: 'Ahora'),
    );
    notifyListeners();
    _persistirDatos();
  }

  /// El usuario canjea el código de referido de un amigo. Acredita el bono al
  /// invitado (a él). Devuelve false si el código es el suyo, vacío, o ya canjeó.
  Future<bool> canjearReferido(String codigo) async {
    final e = usuario?.email.trim().toLowerCase() ?? '';
    final c = codigo.trim().toUpperCase();
    if (e.isEmpty || c.isEmpty || c == codigoReferido) return false;
    final ok = await ReferidosRepo.canjear(invitadoEmail: e, codigo: c);
    if (!ok) return false;
    _acreditarBono(bonoReferido, 'Bono de bienvenida (referido)');
    return true;
  }

  /// Reclama los bonos de las personas que usaron MI código (self-credit).
  Future<int> reclamarBonosReferidor() async {
    final n = await ReferidosRepo.reclamarReferidor(codigoReferido);
    if (n > 0) _acreditarBono(bonoReferido * n, 'Bono por invitar amigos');
    return n;
  }

  /// Recarga el saldo prepago del club.
  void recargar(int monto) {
    if (monto <= 0) return;
    if (monedaSaldo.isEmpty) monedaSaldo = paisActual.moneda;
    saldoClub += monto;
    movimientos.insert(
      0,
      MovimientoSaldo(
          tipo: TipoMovimiento.recarga,
          monto: monto,
          concepto: 'Recarga de saldo',
          cuando: 'Ahora'),
    );
    notifyListeners();
    _persistirDatos();
  }

  /// Descuenta la comisión del saldo cuando entra una reserva a una cancha del
  /// club activo. No llama notifyListeners (lo hace el método que la invoca).
  void _consumirComision(Cancha cancha) {
    if (cancha.club != SampleData.clubActivo) return;
    if (saldoClub <= 0) return;
    final c = comisionDe(cancha.precioHora);
    saldoClub = (saldoClub - c).clamp(0, 1 << 31);
    movimientos.insert(
      0,
      MovimientoSaldo(
          tipo: TipoMovimiento.consumo,
          monto: c,
          concepto: 'Comisión · ${cancha.nombre}',
          cuando: 'Ahora'),
    );
  }

  int _contadorDemo = 1;
  int _contadorJugador = 1;

  static const _kUsuario = 'usuario_json';
  static const _kSaldo = 'saldo_club';
  static const _kSaldoOtros = 'saldo_otros_paises_json';
  static const _kMonedaSaldo = 'moneda_saldo';
  static const _kBienvenidaDueno = 'bienvenida_dueno_vista';
  static const _kVerif = 'verificacion_estado';
  static const _kMovs = 'movimientos_json';
  static const _kMisReservas = 'mis_reservas_json';
  static const _kCanchas = 'canchas_extra_json';
  static const _kEliminadas = 'canchas_eliminadas_json';
  static const _kLandingNegocios = 'landing_negocios_json';
  static const _kFavoritos = 'favoritos_json';
  static const _kRadio = 'radio_busqueda_km';
  static const _kTema = 'tema_modo'; // 0=system, 1=light, 2=dark
  static const _kAcademias = 'academias_json';
  static const _kAcademiasPendientes = 'academias_pendientes_nube_json';
  static const _kAlumnos = 'alumnos_json';
  static const _kCuotas = 'cuotas_json';
  static const _kAsistencias = 'asistencias_json';
  static const _kCampeonatos = 'campeonatos_json';
  static const _kInvitaciones = 'invitaciones_json';
  static const _kChatLecturas = 'chat_lecturas_json';

  /// Carga la sesión y los datos persistidos (al arrancar la app).
  Future<void> cargarSesion() async {
    try {
      final prefs = await SharedPreferences.getInstance();

      final raw = prefs.getString(_kUsuario);
      if (raw != null) {
        usuario = Usuario.fromJson(jsonDecode(raw) as Map<String, dynamic>);
        // Sesión restaurada: re-registra el token push de este dispositivo.
        PushService.registrarParaUsuario(usuario?.email);
        _sincronizarMiPerfil(); // trae mi nombre-foto elegido (otro dispositivo)
      }

      final contactosRaw = prefs.getString(_kContactos);
      if (contactosRaw != null) {
        try {
          _contactos
            ..clear()
            ..addAll((jsonDecode(contactosRaw) as List)
                .map((e) => e.toString().toLowerCase()));
        } catch (_) {}
      }

      if (prefs.containsKey(_kSaldo)) {
        saldoClub = prefs.getInt(_kSaldo) ?? saldoClub;
      }

      final saldoOtrosRaw = prefs.getString(_kSaldoOtros);
      if (saldoOtrosRaw != null) {
        try {
          final m = jsonDecode(saldoOtrosRaw) as Map<String, dynamic>;
          _saldoOtrosPaises
            ..clear()
            ..addAll(m.map((k, v) => MapEntry(k, (v as num).round())));
        } catch (_) {}
      }

      if (prefs.containsKey(_kMonedaSaldo)) {
        monedaSaldo = prefs.getString(_kMonedaSaldo) ?? monedaSaldo;
      }

      if (prefs.containsKey(_kVerif)) {
        estadoVerificacion = prefs.getString(_kVerif) ?? estadoVerificacion;
      }

      bienvenidaDuenoVista =
          prefs.getBool(_kBienvenidaDueno) ?? bienvenidaDuenoVista;
      sincronizarVerificacion(); // best-effort desde el backend

      if (prefs.containsKey(_kRadio)) {
        radioBusquedaKm = (prefs.getDouble(_kRadio) ?? radioBusquedaKm)
            .clamp(radioMinKm, radioMaxKm)
            .toDouble();
      }

      if (prefs.containsKey(_kTema)) {
        // Claro por defecto para TODOS: cualquier "automático" (0) guardado de
        // versiones viejas migra a claro. Solo "oscuro" (2) se respeta.
        temaModo = switch (prefs.getInt(_kTema)) {
          2 => ThemeMode.dark,
          _ => ThemeMode.light,
        };
      }

      final movsRaw = prefs.getString(_kMovs);
      if (movsRaw != null) {
        final list = (jsonDecode(movsRaw) as List)
            .map((e) => MovimientoSaldo.fromJson(e as Map<String, dynamic>))
            .toList();
        movimientos
          ..clear()
          ..addAll(list);
      }

      final canchasRaw = prefs.getString(_kCanchas);
      if (canchasRaw != null) {
        final list = (jsonDecode(canchasRaw) as List)
            .map((e) => Cancha.fromJson(e as Map<String, dynamic>))
            .toList();
        canchasExtra
          ..clear()
          ..addAll(list);
        _repararClubLegado(); // sana nombres de club de datos viejos
      }

      final elimRaw = prefs.getString(_kEliminadas);
      if (elimRaw != null) {
        canchasEliminadas
          ..clear()
          ..addAll((jsonDecode(elimRaw) as List).map((e) => e.toString()));
      }

      final landNegRaw = prefs.getString(_kLandingNegocios);
      if (landNegRaw != null) {
        _landingNegocios
          ..clear()
          ..addAll((jsonDecode(landNegRaw) as List).map((e) => e.toString()));
      }

      final favRaw = prefs.getString(_kFavoritos);
      if (favRaw != null) {
        favoritos
          ..clear()
          ..addAll((jsonDecode(favRaw) as List).map((e) => e.toString()));
      }

      final misRaw = prefs.getString(_kMisReservas);
      if (misRaw != null) {
        final list = (jsonDecode(misRaw) as List)
            .map((e) => Reserva.fromJson(e as Map<String, dynamic>))
            .toList();
        misReservas
          ..clear()
          ..addAll(list);
        // Refleja también en el panel del dueño (reservas) las que faltan.
        for (final r in list) {
          if (!reservas.any((x) => x.id == r.id)) reservas.insert(0, r);
        }
      }

      _cargarLista(prefs, _kAcademias, academias, Academia.fromJson);
      final pendRaw = prefs.getString(_kAcademiasPendientes);
      if (pendRaw != null) {
        try {
          _academiasPendientesNube
            ..clear()
            ..addAll((jsonDecode(pendRaw) as List).map((e) => e.toString()));
        } catch (_) {}
      }
      _cargarLista(prefs, _kAlumnos, alumnos, Alumno.fromJson);
      _cargarLista(prefs, _kCuotas, cuotas, Cuota.fromJson);
      _cargarLista(prefs, _kAsistencias, asistencias, Asistencia.fromJson);
      _cargarLista(prefs, _kCampeonatos, campeonatos, Campeonato.fromJson);
      _cargarLista(prefs, _kInvitaciones, invitaciones, Invitacion.fromJson);

      final lecturasRaw = prefs.getString(_kChatLecturas);
      if (lecturasRaw != null) {
        try {
          final m = jsonDecode(lecturasRaw) as Map<String, dynamic>;
          chatLecturas
            ..clear()
            ..addAll(m.map((k, v) => MapEntry(k, v.toString())));
        } catch (_) {}
      }

      notifyListeners();
      // Trae la disponibilidad compartida (reservas de otros dispositivos) para
      // que el anti-doble-reserva y el panel del dueño arranquen al día. Best-effort.
      cargarReservasRemotas();
      cargarCanalComunicacion(); // política de canal (WhatsApp vs chat PCG)
    } catch (_) {}
  }

  /// Canal de comunicación configurado en la torre de control: decide si el APK
  /// muestra el botón de WhatsApp. 'pcg_primero' (chat + WhatsApp respaldo) |
  /// 'solo_pcg' (oculta WhatsApp) | 'whatsapp_libre'. Se refresca al arrancar;
  /// mientras tanto usa 'pcg_primero' (fail-safe: no bloquea contactar).
  String canalComunicacion = 'pcg_primero';

  /// ¿El APK debe MOSTRAR el botón de WhatsApp? Solo se oculta en 'solo_pcg'.
  bool get mostrarWhatsapp => canalComunicacion != 'solo_pcg';

  /// ¿WhatsApp va tan visible como el chat interno? (modo 'whatsapp_libre').
  bool get whatsappLibre => canalComunicacion == 'whatsapp_libre';

  Future<void> cargarCanalComunicacion() async {
    final c = await GrowthService.canalComunicacion();
    if (c != null && c != canalComunicacion) {
      canalComunicacion = c;
      notifyListeners();
    }
  }

  /// Carga una lista JSON persistida en [destino] (fail-safe).
  void _cargarLista<T>(SharedPreferences prefs, String clave, List<T> destino,
      T Function(Map<String, dynamic>) desde) {
    final raw = prefs.getString(clave);
    if (raw == null) return;
    try {
      final list = (jsonDecode(raw) as List)
          .map((e) => desde(e as Map<String, dynamic>))
          .toList();
      destino
        ..clear()
        ..addAll(list);
    } catch (_) {}
  }

  Future<void> _persistirDatos() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setInt(_kSaldo, saldoClub);
      await prefs.setString(_kSaldoOtros, jsonEncode(_saldoOtrosPaises));
      await prefs.setString(_kMonedaSaldo, monedaSaldo);
      await prefs.setString(_kVerif, estadoVerificacion);
      await prefs.setBool(_kBienvenidaDueno, bienvenidaDuenoVista);
      await prefs.setString(
          _kMovs, jsonEncode(movimientos.map((m) => m.toJson()).toList()));
      await prefs.setString(_kMisReservas,
          jsonEncode(misReservas.map((r) => r.toJson()).toList()));
      await prefs.setString(
          _kCanchas, jsonEncode(canchasExtra.map((c) => c.toJson()).toList()));
      await prefs.setString(
          _kEliminadas, jsonEncode(canchasEliminadas.toList()));
      await prefs.setString(
          _kLandingNegocios, jsonEncode(_landingNegocios.toList()));
      await prefs.setString(_kFavoritos, jsonEncode(favoritos.toList()));
      await prefs.setDouble(_kRadio, radioBusquedaKm);
      await prefs.setInt(_kTema, switch (temaModo) {
        ThemeMode.light => 1,
        ThemeMode.dark => 2,
        ThemeMode.system => 0,
      });
      await prefs.setString(
          _kAcademias, jsonEncode(academias.map((a) => a.toJson()).toList()));
      await prefs.setString(
          _kAcademiasPendientes, jsonEncode(_academiasPendientesNube.toList()));
      await prefs.setString(
          _kAlumnos, jsonEncode(alumnos.map((a) => a.toJson()).toList()));
      await prefs.setString(
          _kCuotas, jsonEncode(cuotas.map((c) => c.toJson()).toList()));
      await prefs.setString(_kAsistencias,
          jsonEncode(asistencias.map((a) => a.toJson()).toList()));
      await prefs.setString(_kCampeonatos,
          jsonEncode(campeonatos.map((c) => c.toJson()).toList()));
      await prefs.setString(_kInvitaciones,
          jsonEncode(invitaciones.map((i) => i.toJson()).toList()));
      await prefs.setString(_kChatLecturas, jsonEncode(chatLecturas));
    } catch (_) {}
  }

  /// Login del jugador con Google. Devuelve true si quedó logueado.
  Future<bool> entrarConGoogle() async {
    final u = await AuthService.entrarConGoogle();
    if (u == null) return false; // canceló
    _finalizarLogin(u);
    return true;
  }

  /// Login MANUAL con una cuenta explícita (modo pruebas dev/qas): permite entrar
  /// como jugador o como profe con correos DISTINTOS sin depender de que el OAuth
  /// de Google esté configurado en el build. En prod no se usa (login = Google).
  Future<bool> entrarComo({required String email, String? nombre}) async {
    final correo = email.trim().toLowerCase();
    if (correo.isEmpty || !correo.contains('@')) return false;
    final nom = (nombre?.trim().isNotEmpty ?? false)
        ? nombre!.trim()
        : correo.split('@').first;
    _finalizarLogin(Usuario(nombre: nom, email: correo, fotoUrl: null));
    return true;
  }

  /// Deja la sesión lista tras autenticar (Google o manual) y dispara los
  /// refrescos remotos (reservas, saldo, academias→matrículas, invitaciones).
  void _finalizarLogin(Usuario u) {
    usuario = u;
    _persistirUsuario();
    _sincronizarMiPerfil(); // aplica/crea mi nombre-foto público (best-effort)
    PushService.registrarParaUsuario(u.email); // push del chat a este dispositivo
    _recomputarMisReservas(); // recupera sus reservas de otros dispositivos
    notifyListeners();
    cargarReservasRemotas(); // best-effort refresco
    sincronizarSaldo(); // saldo real del backend (sobrevive reinstalar)
    // Trae sus academias (por si las creó en otro dispositivo) y LUEGO las
    // matrículas, para que el profe vea a sus alumnos apenas entra.
    () async {
      await cargarAcademiasRemotas();
      await cargarMatriculasRemotas();
    }();
    cargarInvitacionesRemotas(); // ¿lo invitaron a alguna academia por correo?
  }

  Future<void> cerrarSesionUsuario() async {
    await PushService.olvidar(); // deja de recibir push de esta cuenta
    await AuthService.salir();
    usuario = null;
    misReservas.clear(); // no mezclar reservas entre cuentas
    await _persistirUsuario();
    _persistirDatos();
    notifyListeners();
  }

  /// "Empezar de cero" (solo pruebas dev/qas): deja el dispositivo VIRGEN.
  /// Borra academias/matrículas del usuario en la NUBE (best-effort, para que no
  /// reaparezcan al re-sincronizar) y limpia toda la memoria + disco local.
  Future<void> borrarTodoParaPruebas({bool incluirNube = true}) async {
    // 1) Nube (best-effort): academias del usuario + sus matrículas + las suyas
    //    como alumno. Solo lo del correo logueado; no toca datos de otros.
    if (incluirNube) {
      final email = usuario?.email.toLowerCase();
      if (email != null && email.isNotEmpty) {
        final mias =
            academias.where((a) => a.dueno.toLowerCase() == email).toList();
        for (final a in mias) {
          for (final al in alumnos.where((x) => x.academiaId == a.id)) {
            await MatriculasRepo.eliminar(al.id);
          }
          await AcademiasRepo.eliminar(a.id);
        }
        for (final al
            in alumnos.where((x) => x.email.toLowerCase() == email)) {
          await MatriculasRepo.eliminar(al.id);
        }
      }
    }
    // 2) Memoria en blanco.
    reservas.clear();
    agenda.clear();
    misReservas.clear();
    canchasExtra.clear();
    canchasRemotas.clear();
    canchasDescubiertas.clear();
    canchasEliminadas.clear();
    academias.clear();
    _academiasPendientesNube.clear();
    alumnos.clear();
    cuotas.clear();
    asistencias.clear();
    invitaciones.clear();
    campeonatos.clear();
    movimientos.clear();
    _landingNegocios.clear();
    _saldoOtrosPaises.clear();
    saldoClub = 0;
    _ultimoSyncMatriculas = null;
    usuario = null;
    // 3) Disco en blanco.
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.clear();
    } catch (_) {}
    await PushService.olvidar();
    await AuthService.salir();
    notifyListeners();
  }

  /// "DEJAR EN VIRGEN" (quirúrgico): deja el sistema como si NUNCA hubiera habido
  /// una transacción —sin alumnos, sin reservas, sin cobros ni saldo— pero
  /// CONSERVA las canchas reclamadas, las academias creadas y la sesión. Es lo
  /// contrario de "Empezar de cero" (que borra todo y cierra sesión).
  ///
  /// Nube (best-effort, solo lo del usuario logueado): borra las matrículas de
  /// SUS academias y las suyas como alumno, y las reservas de SUS canchas. NO
  /// borra academias ni canchas. El saldo/pagos/suscripciones del servidor se
  /// limpian aparte desde la torre de control (botón "Dejar el servidor en
  /// virgen").
  Future<void> resetVirgen() async {
    final email = usuario?.email.toLowerCase();
    if (email != null && email.isNotEmpty) {
      final misAcademiaIds = academias
          .where((a) => a.dueno.toLowerCase() == email)
          .map((a) => a.id)
          .toSet();
      // Matrículas (alumnos + cuotas embebidas) de mis academias + las mías.
      for (final al in List<Alumno>.from(alumnos)) {
        if (misAcademiaIds.contains(al.academiaId) ||
            al.email.toLowerCase() == email) {
          await MatriculasRepo.eliminar(al.id);
        }
      }
      final misCanchaIds =
          misCanchas.where((c) => c.registrada).map((c) => c.id).toList();
      // Reservas de mis canchas (registradas/reclamadas).
      for (final id in misCanchaIds) {
        await ReservasRepo.eliminarDeCancha(id);
      }
      // Reseñas de mis canchas.
      await ResenasRepo.eliminarDeCanchas(misCanchaIds);
      // Chats: de mis academias + conversaciones de cancha donde participo.
      await MensajesRepo.eliminarDeAcademias(misAcademiaIds.toList());
      await MensajesRepo.eliminarCanchaDe(email);
      // Campeonatos de mis academias.
      for (final c in campeonatos.where((c) => misAcademiaIds.contains(c.academiaId))) {
        await CampeonatosRepo.eliminar(c.id);
      }
    }
    // Memoria local: borra lo transaccional, CONSERVA academias, canchas y sesión.
    reservas.clear();
    agenda.clear();
    misReservas.clear();
    alumnos.clear();
    cuotas.clear();
    asistencias.clear();
    movimientos.clear();
    campeonatos.clear();
    saldoClub = 0;
    _saldoOtrosPaises.clear();
    _ultimoSyncMatriculas = null;
    notifyListeners();
    await _persistirDatos();
  }

  Future<void> _persistirUsuario() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      if (usuario == null) {
        await prefs.remove(_kUsuario);
      } else {
        await prefs.setString(_kUsuario, jsonEncode(usuario!.toJson()));
      }
    } catch (_) {}
  }

  /// Registra una reserva hecha por un jugador desde el detalle de cancha.
  /// [fecha] es la fecha real ISO ("2026-06-27"); [diaLabel] es solo la etiqueta
  /// visible ("Hoy"/"Mañana"). Devuelve el resultado: si otro jugador ganó el
  /// mismo slot, Supabase rechaza el INSERT (UNIQUE) y se devuelve `ocupado`.
  ///
  /// Piloto: pago EN CANCHA, sin seña con tarjeta (sena = 0). El dueño confirma
  /// el cobro luego con [marcarPago]. El precio se calcula por la duración del
  /// slot de la cancha (1h, 1.5h, 2h).
  Future<ResultadoReserva> agregarReservaJugador(
      Cancha cancha, String fecha, String diaLabel, String hora,
      {Deporte? deporte,
      List<ServicioExtra> extras = const [],
      String cobro = 'ninguno'}) async {
    // Chequeo local rápido (doble toque / feedback inmediato sin conexión).
    // La agenda es COMPARTIDA entre deportes: se ocupa por (cancha, fecha, hora),
    // sin importar el deporte (es la misma superficie física).
    final yaLocal = reservas.any((r) =>
        r.canchaId == cancha.id && r.fecha == fecha && r.horaInicio == hora);
    if (yaLocal) return ResultadoReserva.ocupado;

    // Precio efectivo del slot (aplica "hora feliz" si la hora es valle).
    final precio = (cancha.precioEn(hora) * cancha.duracionSlotMin / 60).round();
    final reserva = Reserva(
      id: 'jug_${DateTime.now().millisecondsSinceEpoch}_${_contadorJugador++}',
      canchaId: cancha.id,
      jugador: usuario?.nombre ?? 'Jugador',
      nivel: 'Intermedio 3.5',
      fecha: fecha,
      dia: diaLabel,
      horaInicio: hora,
      horaFin: cancha.horaFinDe(hora),
      estado: EstadoReserva.confirmada,
      traidaPorApp: true,
      precio: precio,
      sena: 0, // piloto: pago en cancha, sin seña con tarjeta
      usuario: usuario?.email ?? '',
      // Deporte elegido para este slot (loza multiuso). Default: el principal.
      deporte: (deporte ?? cancha.deporte).name,
      moneda: cancha.monedaSimbolo, // moneda de la cancha (Perú S/, Bolivia Bs…)
      extras: extras, // servicios extra elegidos (árbitro/pelotero…)
    );

    // Fuente de verdad anti-doble-reserva: Supabase con
    // UNIQUE(cancha_id, fecha, hora_inicio). Si otro ganó el slot → ocupado.
    final res = await ReservasRepo.insertarSegura(reserva);
    if (res == ResultadoReserva.ocupado) return res;

    // ok / sinConexion / error → se guarda local igual (fail-safe offline).
    reservas.insert(0, reserva); // visible para el dueño en su panel
    misReservas.insert(0, reserva); // visible para el jugador en "Mis reservas"
    if (diaLabel == 'Hoy') {
      final i = agenda.indexWhere(
          (b) => b.canchaId == cancha.id && b.hora == hora);
      if (i >= 0) agenda[i] = agenda[i].copyWith(reservaId: reserva.id);
    }
    // Trazabilidad de la comisión de PCG (best-effort, idempotente por id):
    //  - 'efectivo': el jugador paga la cancha; PCG cobra la comisión del SALDO
    //    prepago del dueño.
    //  - 'online': el jugador pagó por la app; se registra la LIQUIDACIÓN (neto
    //    que PCG le debe al dueño). No toca el saldo.
    if (res == ResultadoReserva.ok && cancha.dueno.isNotEmpty) {
      final etiqueta = '${cancha.nombre} · $diaLabel $hora';
      if (cobro == 'efectivo') {
        PagosService.comisionReserva(
          duenoId: cancha.dueno,
          montoSoles: cancha.precioEn(hora),
          reservaId: reserva.id,
          concepto: 'Comisión · $etiqueta',
        );
      } else if (cobro == 'online') {
        PagosService.liquidacionOnline(
          duenoId: cancha.dueno,
          montoSoles: cancha.precioEn(hora),
          reservaId: reserva.id,
          concepto: 'Reserva online · $etiqueta',
        );
      }
    }
    notifyListeners();
    _persistirDatos();
    return res == ResultadoReserva.ok ? ResultadoReserva.ok : res;
  }

  /// RESERVA MANUAL del dueño: registra la reserva de un cliente que llamó por
  /// teléfono/WhatsApp (digitaliza el cuaderno). Es `traidaPorApp: false` —
  /// cliente PROPIO del dueño, FUERA de la base de comisión: Pichangol solo
  /// monetiza lo que trae la app. Ocupa el slot igual (anti doble-reserva), así
  /// un jugador de la app no puede reservar una hora ya tomada.
  Future<ResultadoReserva> agregarReservaManual(
    Cancha cancha,
    String fecha,
    String diaLabel,
    String hora, {
    required String nombreCliente,
    String telefono = '',
    bool pagado = false,
    int? precioOverride,
    Deporte? deporte,
  }) async {
    final yaLocal = reservas.any((r) =>
        r.canchaId == cancha.id && r.fecha == fecha && r.horaInicio == hora);
    if (yaLocal) return ResultadoReserva.ocupado;

    final precio = precioOverride ??
        (cancha.precioHora * cancha.duracionSlotMin / 60).round();
    final nombre = nombreCliente.trim();
    final reserva = Reserva(
      id: 'man_${DateTime.now().millisecondsSinceEpoch}_${_contadorJugador++}',
      canchaId: cancha.id,
      jugador: nombre.isEmpty ? 'Cliente' : nombre,
      nivel: '',
      fecha: fecha,
      dia: diaLabel,
      horaInicio: hora,
      horaFin: cancha.horaFinDe(hora),
      estado: EstadoReserva.confirmada,
      traidaPorApp: false, // CLIENTE PROPIO del dueño → fuera de comisión
      precio: precio,
      sena: 0,
      pagado: pagado,
      usuario: '', // cliente offline: sin cuenta de la app
      deporte: (deporte ?? cancha.deporte).name,
      moneda: cancha.monedaSimbolo,
      telefono: telefono.trim(),
    );

    // Misma fuente de verdad anti-doble-reserva que la reserva del jugador.
    final res = await ReservasRepo.insertarSegura(reserva);
    if (res == ResultadoReserva.ocupado) return res;

    reservas.insert(0, reserva); // visible en el panel del dueño
    if (diaLabel == 'Hoy') {
      final i =
          agenda.indexWhere((b) => b.canchaId == cancha.id && b.hora == hora);
      if (i >= 0) agenda[i] = agenda[i].copyWith(reservaId: reserva.id);
    }
    notifyListeners();
    _persistirDatos();
    return res == ResultadoReserva.ok ? ResultadoReserva.ok : res;
  }

  /// El dueño confirma (o revierte) que el jugador pagó en efectivo en la cancha.
  Future<void> marcarPago(Reserva r, {bool pagado = true}) async {
    final upd = r.copyWith(pagado: pagado);
    _reemplazarReserva(upd);
    notifyListeners();
    _persistirDatos();
    ReservasRepo.actualizar(upd); // best-effort
  }

  /// El JUGADOR cancela / elimina una de sus reservas (próxima o del historial).
  /// La quita de sus listas y de la del dueño, libera el slot en la agenda y la
  /// borra de Supabase (best-effort) para que el horario vuelva a estar libre y
  /// no reaparezca al sincronizar.
  Future<void> cancelarReserva(Reserva r) async {
    misReservas.removeWhere((x) => x.id == r.id);
    reservas.removeWhere((x) => x.id == r.id);
    final i = agenda.indexWhere((b) => b.reservaId == r.id);
    if (i >= 0) {
      agenda[i] = agenda[i].copyWith(limpiarReserva: true, disponible: true);
    }
    notifyListeners();
    _persistirDatos();
    await ReservasRepo.eliminar(r.id); // libera el slot en la nube
  }

  /// El dueño marca que el jugador no se presentó.
  Future<void> marcarNoShow(Reserva r) async {
    final upd = r.copyWith(estado: EstadoReserva.noShow);
    _reemplazarReserva(upd);
    notifyListeners();
    _persistirDatos();
    ReservasRepo.actualizar(upd); // best-effort
  }

  void _reemplazarReserva(Reserva r) {
    final i = reservas.indexWhere((x) => x.id == r.id);
    if (i >= 0) reservas[i] = r;
    final j = misReservas.indexWhere((x) => x.id == r.id);
    if (j >= 0) misReservas[j] = r;
  }

  String siguienteHora(String hora) => _siguienteHora(hora);

  void iniciarSesion(String club) {
    nombreClub = club.trim().isEmpty ? SampleData.clubActivo : club.trim();
    sesionIniciada = true;
    notifyListeners();
  }

  void cerrarSesion() {
    sesionIniciada = false;
    notifyListeners();
  }

  Reserva? reservaPorId(String id) {
    for (final r in reservas) {
      if (r.id == id) return r;
    }
    return null;
  }

  List<BloqueHorario> bloquesDe(String canchaId) =>
      agenda.where((b) => b.canchaId == canchaId).toList();

  /// Abre/cierra la disponibilidad de un bloque (lo que el dueño publica en la app).
  void alternarDisponibilidad(BloqueHorario bloque) {
    if (bloque.reservaId != null) return; // ocupado: no se toca
    final i = agenda.indexWhere(
        (b) => b.canchaId == bloque.canchaId && b.hora == bloque.hora);
    if (i >= 0) {
      agenda[i] = agenda[i].copyWith(disponible: !agenda[i].disponible);
      notifyListeners();
    }
  }

  /// Simula que ENTRA una reserva nueva por la app en un bloque valle libre.
  /// Es el momento "mágico" del pitch de demo: que el dueño la vea entrar en vivo.
  String? simularReservaEntrante() {
    int idx = agenda.indexWhere(
        (b) => b.reservaId == null && b.disponible && b.esHoraValle);
    if (idx < 0) {
      idx = agenda.indexWhere((b) => b.reservaId == null && b.disponible);
    }
    if (idx < 0) return null;

    final bloque = agenda[idx];
    final cancha = SampleData.canchaPorId(bloque.canchaId);
    if (cancha == null) return null;

    final nueva = Reserva(
      id: 'demo${_contadorDemo++}',
      canchaId: cancha.id,
      jugador: 'Reserva por la app',
      nivel: 'Intermedio 3.5',
      dia: 'Hoy',
      horaInicio: bloque.hora,
      horaFin: _siguienteHora(bloque.hora),
      estado: EstadoReserva.nueva,
      traidaPorApp: true,
      precio: cancha.precioHora.round(),
      sena: (cancha.precioHora * 0.3).round(),
    );
    reservas.insert(0, nueva);
    agenda[idx] = bloque.copyWith(reservaId: nueva.id);
    _consumirComision(cancha);
    notifyListeners();
    _persistirDatos();
    return '${cancha.nombre} · ${nueva.horaInicio} · +$monedaSimbolo ${nueva.precio}';
  }

  String _siguienteHora(String hora) {
    final h = int.tryParse(hora.split(':').first);
    if (h == null) return hora;
    return '${(h + 1).toString().padLeft(2, '0')}:00';
  }
}

/// Acumulador interno del RANKING GLOBAL: junta las stats de una MISMA identidad
/// (correo) entre academias. `porAcademia` cuenta partidos por academia para
/// elegir la academia "primaria" a mostrar.
class _AggGlobal {
  _AggGlobal({required this.deporte});
  final Deporte deporte;
  String nombre = '';
  String categoria = '';
  int pj = 0;
  int pg = 0;
  int pp = 0;
  final Set<String> academiasIds = {};
  final Map<String, int> porAcademia = {};
}
