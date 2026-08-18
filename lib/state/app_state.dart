import 'dart:async';
import 'dart:convert';
import 'dart:math' as math;
import 'dart:typed_data';

import 'package:flutter_cache_manager/flutter_cache_manager.dart';

import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../data/academias_repo.dart';
import '../data/agenda_repo.dart';
import '../data/estados_repo.dart';
import '../data/lecturas_repo.dart';
import '../data/presencia_repo.dart';
import '../models/estado.dart';
import '../models/canal.dart';
import '../data/campeonatos_repo.dart';
import '../data/canchas_cache_repo.dart';
import '../data/canchas_repo.dart';
import '../data/invitaciones_repo.dart';
import '../data/matriculas_repo.dart';
import '../data/mensajes_repo.dart';
import '../models/mensaje.dart';
import '../models/nivel.dart';
import '../data/niveles_repo.dart';
import '../data/perfiles_repo.dart';
import '../data/bloqueos_repo.dart';
import '../data/descuentos_repo.dart';
import '../data/referidos_repo.dart';
import '../data/bonos_repo.dart';
import '../data/espera_repo.dart';
import '../data/resenas_repo.dart';
import '../data/reservas_repo.dart';
import '../data/sample_data.dart';
import '../data/verificacion_repo.dart';
import '../models/academia.dart';
import '../models/campeonato.dart';
import '../models/cierre_caja.dart';
import '../models/club.dart';
import '../models/invitacion.dart';
import '../models/models.dart';
import '../models/negocio.dart';
import '../models/plan_trabajo.dart';
import '../data/planes_semilla.dart';
import '../models/bono.dart';
import '../models/espera.dart';
import '../models/resena.dart';
import '../models/reserva_fija.dart';
import '../models/temporada.dart';
import '../models/usuario.dart';
import '../services/auth_service.dart';
import '../services/avisos_service.dart';
import '../services/circuito_service.dart';
import '../services/pagos_service.dart';
import '../services/retos_service.dart';
import '../services/push_service.dart';
import '../services/places_service.dart';
import '../services/supabase_service.dart';
import '../services/verificacion_service.dart';
import '../services/growth_service.dart';
import '../services/propiedad_service.dart';
import '../services/recordatorio_service.dart';
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

  // Apodos que YO le puse a un contacto (email→alias, local, tipo WhatsApp).
  // Mandan sobre el nombre de su perfil al mostrarlo. Se persisten.
  final Map<String, String> _apodos = {};

  // Notas privadas del DUEÑO por cliente (clave = correo, o 'n:nombre' para el
  // walk-in sin cuenta), tipo "cuaderno del club": prefiere efectivo, juega los
  // martes, cancha 2, etc. Device-first (SharedPreferences); solo las ve el dueño.
  final Map<String, String> _notasCliente = {};

  /// Nota privada que el dueño le puso a un cliente (vacío si no hay).
  String notaCliente(String clave) => _notasCliente[clave.trim()] ?? '';

  /// Guarda (o borra, si queda vacía) la nota privada de un cliente y persiste.
  Future<void> guardarNotaCliente(String clave, String nota) async {
    final k = clave.trim();
    if (k.isEmpty) return;
    final t = nota.trim();
    if (t.isEmpty) {
      _notasCliente.remove(k);
    } else {
      _notasCliente[k] = t;
    }
    notifyListeners();
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(_kNotasCliente, jsonEncode(_notasCliente));
    } catch (_) {}
  }

  /// Apodo local que le puse a un correo, o null si no le puse.
  String? apodoDe(String? email) {
    final a = _apodos[(email ?? '').trim().toLowerCase()];
    return (a != null && a.trim().isNotEmpty) ? a.trim() : null;
  }

  /// Guarda (o borra, con texto vacío) el apodo local de un contacto. Solo lo
  /// veo yo; no cambia el perfil de la otra persona.
  Future<void> guardarApodo(String email, String apodo) async {
    final e = email.trim().toLowerCase();
    if (e.isEmpty) return;
    final a = apodo.trim();
    if (a.isEmpty) {
      _apodos.remove(e);
    } else {
      _apodos[e] = a;
    }
    notifyListeners();
    await _persistirDatos();
    await _guardarAgendaRemota();
  }

  /// Nombre a mostrar de un correo: MI apodo si le puse uno; si no, el de su
  /// perfil (no vacío); si no, null.
  String? nombreMostrableDe(String? email) {
    final e = (email ?? '').trim().toLowerCase();
    final apodo = apodoDe(e);
    if (apodo != null) return apodo;
    final n = (_perfiles[e]?['nombre'] ?? '').toString().trim();
    return n.isEmpty ? null : n;
  }

  /// Nombre REAL del perfil (ignora mi apodo), o null. Para la "info del
  /// contacto": ver su identidad real aunque le haya puesto un apodo.
  String? nombreRealDe(String? email) {
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

  /// Recado/estado (tipo WhatsApp) de un correo, o null si no lo puso. Es un
  /// texto corto que el usuario muestra a sus contactos (ej. "Disponible").
  String? recadoDe(String? email) {
    final e = (email ?? '').trim().toLowerCase();
    final r = (_perfiles[e]?['recado'] ?? '').toString().trim();
    return r.isEmpty ? null : r;
  }

  /// Mi propio recado guardado, o '' si no tengo.
  String get miRecado =>
      (_perfiles[(usuario?.email ?? '').toLowerCase()]?['recado'] ?? '')
          .toString();

  /// Guarda mi recado (estado) en el perfil: cache local + Supabase (best-effort,
  /// requiere la columna `recado`). Mis contactos lo ven en el chat.
  Future<void> guardarRecado(String texto) async {
    final u = usuario;
    if (u == null) return;
    final e = u.email.toLowerCase();
    final t = texto.trim();
    _perfiles[e] = {...?_perfiles[e], 'email': e, 'recado': t};
    notifyListeners();
    await PerfilesRepo.guardar(email: u.email, nombre: u.nombre, recado: t);
  }

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
    await _guardarAgendaRemota();
  }

  Future<void> quitarContacto(String email) async {
    _contactos.remove(email.trim().toLowerCase());
    notifyListeners();
    await _persistirContactos();
    await _guardarAgendaRemota();
  }

  // ── Nivel de jugador (estilo Playtomic 0-7, aquí 1.0–7.0) ──────────────────
  // MIS niveles por deporte (cache device-first). Se siembran en el onboarding y
  // se ajustan con resultados reales (retos/campeonatos) vía ELO suave. Fuente
  // durable: Supabase `pichangol_niveles` (docs/piloto/supabase_niveles.sql).
  final Map<String, Nivel> _misNiveles = {}; // deporte → Nivel
  static const _kMisNiveles = 'mis_niveles_json';

  /// Mi nivel en un deporte, o null si aún no me he autoevaluado.
  Nivel? miNivelDe(String deporte) => _misNiveles[deporte];

  /// Todos MIS niveles (uno por deporte) para pintarlos en el perfil.
  List<Nivel> get misNiveles => _misNiveles.values.toList();

  /// ¿Ya tengo un nivel sembrado en algún deporte? (para saber si mostrar el
  /// mini-cuestionario del onboarding).
  bool get tengoNivel => _misNiveles.isNotEmpty;

  Future<void> _guardarMisNivelesCache() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(_kMisNiveles,
          jsonEncode([for (final n in _misNiveles.values) n.toRow()]));
    } catch (_) {}
  }

  /// Carga MIS niveles device-first: pinta al instante desde la caché local y
  /// luego refresca desde Supabase en segundo plano. Se llama al iniciar sesión.
  Future<void> cargarMisNiveles() async {
    final email = (usuario?.email ?? '').toLowerCase();
    if (email.isEmpty) return;
    // 1) Caché local (device-first).
    try {
      final prefs = await SharedPreferences.getInstance();
      final raw = prefs.getString(_kMisNiveles);
      if (raw != null && raw.isNotEmpty) {
        for (final r in (jsonDecode(raw) as List)) {
          final n = Nivel.fromRow(Map<String, dynamic>.from(r as Map));
          if (n.email.isEmpty || n.email.toLowerCase() == email) {
            _misNiveles[n.deporte] = n;
          }
        }
        notifyListeners();
      }
    } catch (_) {}
    // 2) Remoto (Supabase) → actualiza y persiste.
    final remotos = await NivelesRepo.deJugador(email);
    if (remotos.isNotEmpty) {
      for (final n in remotos) {
        _misNiveles[n.deporte] = n;
      }
      notifyListeners();
      await _guardarMisNivelesCache();
    }
  }

  /// Siembra MI nivel inicial en un deporte desde el auto-cuestionario del
  /// onboarding. Persiste local + Supabase.
  Future<void> sembrarMiNivel(
    String deporte, {
    required int anios,
    required int frecuenciaSemana,
    required bool compite,
  }) async {
    final email = (usuario?.email ?? '').toLowerCase();
    if (email.isEmpty || deporte.isEmpty) return;
    final n = Nivel(
      email: email,
      deporte: deporte,
      nivel: Nivel.seedDesde(
          anios: anios, frecuenciaSemana: frecuenciaSemana, compite: compite),
      actualizado: DateTime.now(),
    );
    _misNiveles[deporte] = n;
    notifyListeners();
    await _guardarMisNivelesCache();
    await NivelesRepo.guardar(n);
  }

  /// Ajusta MI nivel tras un resultado real (reto/campeonato) con ELO suave, y
  /// suma partido/victoria. Persiste local + Supabase.
  Future<void> registrarResultadoNivel(
    String deporte, {
    required double rivalNivel,
    required bool gane,
  }) async {
    final email = (usuario?.email ?? '').toLowerCase();
    if (email.isEmpty || deporte.isEmpty) return;
    final actual =
        _misNiveles[deporte] ?? Nivel(email: email, deporte: deporte);
    final nuevo = actual.copyWith(
      nivel: Nivel.calcularElo(
          miNivel: actual.nivel, rivalNivel: rivalNivel, gane: gane),
      partidos: actual.partidos + 1,
      victorias: actual.victorias + (gane ? 1 : 0),
      actualizado: DateTime.now(),
    );
    _misNiveles[deporte] = nuevo;
    notifyListeners();
    await _guardarMisNivelesCache();
    await NivelesRepo.guardar(nuevo);
  }

  static const _kRetosElo = 'retos_elo_aplicados';

  /// Aplica el ELO a MI nivel por CADA reto ya JUGADO que aún no procesé
  /// (idempotente por id de reto → nunca se aplica dos veces). Cada jugador
  /// actualiza SU propio nivel en su dispositivo, con el nivel actual del rival.
  /// Sólo singles (el dobles necesita lógica de equipo). Se llama al abrir "Mis
  /// retos": así el nivel sube/baja SOLO con resultados reales (Playtomic).
  Future<void> aplicarEloDeRetos(List<Map<String, dynamic>> retos) async {
    final yo = (usuario?.email ?? '').toLowerCase();
    if (yo.isEmpty || retos.isEmpty) return;
    final prefs = await SharedPreferences.getInstance();
    final hechos = (prefs.getStringList(_kRetosElo) ?? <String>[]).toSet();
    var cambio = false;
    for (final r in retos) {
      if ((r['estado'] ?? '').toString() != 'jugado') continue;
      if ((r['modalidad'] ?? 'singles').toString() == 'dobles') continue;
      final ganador = (r['ganador_email'] ?? '').toString().toLowerCase();
      if (ganador.isEmpty) continue;
      final id = r['id']?.toString() ?? '';
      if (id.isEmpty || hechos.contains(id)) continue;
      final deporte = (r['deporte'] ?? '').toString();
      if (deporte.isEmpty) continue;
      final retador = (r['retador_email'] ?? '').toString().toLowerCase();
      final retado = (r['retado_email'] ?? '').toString().toLowerCase();
      final rival = yo == retador ? retado : (yo == retado ? retador : '');
      if (rival.isEmpty) continue;
      final nivRival = await NivelesRepo.de(rival, deporte);
      await registrarResultadoNivel(deporte,
          rivalNivel: nivRival?.nivel ?? 3.0, gane: ganador == yo);
      hechos.add(id);
      cambio = true;
    }
    if (cambio) await prefs.setStringList(_kRetosElo, hechos.toList());
  }

  // ── Bloqueados (tipo WhatsApp): correos que el usuario bloqueó ─────────────
  final Set<String> _bloqueados = {};

  bool bloqueado(String? email) =>
      _bloqueados.contains((email ?? '').trim().toLowerCase());

  /// Bloquea/desbloquea a un contacto (local). Bloqueado = no le puedo escribir
  /// ni llamar desde el app hasta desbloquearlo.
  Future<void> toggleBloqueado(String email) async {
    final e = email.trim().toLowerCase();
    if (e.isEmpty) return;
    if (!_bloqueados.remove(e)) _bloqueados.add(e);
    notifyListeners();
    await _persistirDatos();
    await _guardarAgendaRemota();
  }

  /// Sube MI agenda (apodos + contactos + bloqueados) a Supabase para que siga a
  /// todos mis dispositivos. Best-effort (requiere docs/piloto/supabase_agenda.sql).
  Future<void> _guardarAgendaRemota() async {
    final e = (usuario?.email ?? '').toLowerCase();
    if (e.isEmpty) return;
    await AgendaRepo.guardar(e,
        apodos: _apodos,
        contactos: _contactos.toList(),
        bloqueados: _bloqueados.toList());
  }

  /// Trae MI agenda de Supabase al iniciar sesión y la fusiona con la local: los
  /// contactos y bloqueados se UNEN; en los apodos el remoto manda por clave. Así
  /// el apodo "BEBIM" (y mis contactos/bloqueos) me siguen en teléfono, tablet,
  /// etc. Best-effort.
  Future<void> sincronizarAgenda() async {
    final e = (usuario?.email ?? '').toLowerCase();
    if (e.isEmpty || !AgendaRepo.disponible) return;
    final data = await AgendaRepo.cargar(e);
    if (data == null) {
      await _guardarAgendaRemota(); // primera vez: sube lo local
      return;
    }
    final apodos = (data['apodos'] as Map?) ?? const {};
    final cont = (data['contactos'] as List?) ?? const [];
    final bloq = (data['bloqueados'] as List?) ?? const [];
    for (final entry in apodos.entries) {
      final v = entry.value.toString().trim();
      if (v.isEmpty) {
        _apodos.remove(entry.key.toString());
      } else {
        _apodos[entry.key.toString()] = v;
      }
    }
    _contactos.addAll(cont.map((x) => x.toString().toLowerCase()));
    _bloqueados.addAll(bloq.map((x) => x.toString().toLowerCase()));
    notifyListeners();
    await _persistirDatos();
    await _persistirContactos();
  }

  // ── ESTADOS / HISTORIAS (tipo WhatsApp, duran 24 h) ───────────────────────
  // Cache en memoria de los estados vigentes (todos los conocidos), el set de
  // ids que YO ya vi (local + remoto, para el aro visto/no visto) y, para MIS
  // estados, quién los vio.
  final List<Estado> _estados = [];
  final Set<String> _estadosVistos = {};
  final Map<String, List<String>> _vistasPorEstado = {};
  // Autores cuyas historias OCULTO (no quiero verlas), tipo WhatsApp.
  final Set<String> _estadosOcultos = {};
  static const _kEstadosVistos = 'estados_vistos_json';
  static const _kEstadosOcultos = 'estados_ocultos_json';

  // ── Canales: última vez que abrí cada canal (para el badge de no leídos) ─────
  final Map<String, DateTime> _canalVisto = {};
  static const _kCanalVisto = 'canal_visto_json';

  DateTime? canalUltimaVista(String canalId) => _canalVisto[canalId];

  /// Marca un canal como visto hasta [hasta] (normalmente la fecha del último
  /// post). Guarda el máximo para no "des-leer" al reabrir.
  Future<void> marcarCanalVisto(String canalId, DateTime hasta) async {
    if (canalId.isEmpty) return;
    final actual = _canalVisto[canalId];
    if (actual != null && !hasta.isAfter(actual)) return;
    _canalVisto[canalId] = hasta;
    notifyListeners();
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(
          _kCanalVisto,
          jsonEncode(_canalVisto
              .map((k, v) => MapEntry(k, v.toIso8601String()))));
    } catch (_) {}
  }

  // ── Canales: caché local de la lista (device-first, pinta al instante) ──────
  static const _kCanalesCache = 'canales_cache_json';

  /// Guarda la última lista de canales visibles + sus posts, para pintar
  /// Novedades al instante en la próxima entrada (luego se refresca de Supabase).
  Future<void> guardarCanalesCache(CanalesCache cache) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final data = {
        'canales': [
          for (final c in cache.canales)
            {
              'id': c.id,
              'nombre': c.nombre,
              'descripcion': c.descripcion,
              'foto_url': c.fotoUrl,
              'owner_email': c.ownerEmail,
              'creado': c.creado.toIso8601String(),
            }
        ],
        'posts': cache.posts.map((k, v) => MapEntry(k, [
              for (final p in v)
                {
                  'id': p.id,
                  'canal_id': p.canalId,
                  'autor_email': p.autorEmail,
                  'autor_nombre': p.autorNombre,
                  'tipo': p.tipo,
                  'texto': p.texto,
                  'media_url': p.mediaUrl,
                  'creado': p.creado.toIso8601String(),
                }
            ])),
      };
      await prefs.setString(_kCanalesCache, jsonEncode(data));
    } catch (_) {}
  }

  /// Lee la lista cacheada de canales, o null si no hay / falla.
  Future<CanalesCache?> leerCanalesCache() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final raw = prefs.getString(_kCanalesCache);
      if (raw == null || raw.isEmpty) return null;
      final data = jsonDecode(raw) as Map<String, dynamic>;
      final canales = [
        for (final c in (data['canales'] as List? ?? const []))
          Canal.fromRow(Map<String, dynamic>.from(c as Map))
      ];
      final posts = <String, List<CanalPost>>{};
      ((data['posts'] as Map?) ?? const {}).forEach((k, v) {
        posts[k.toString()] = [
          for (final p in (v as List? ?? const []))
            CanalPost.fromRow(Map<String, dynamic>.from(p as Map))
        ];
      });
      return CanalesCache(canales, posts);
    } catch (_) {
      return null;
    }
  }

  bool estadoVisto(String id) => _estadosVistos.contains(id);
  bool estadosOcultosDe(String? email) =>
      _estadosOcultos.contains((email ?? '').trim().toLowerCase());

  /// Oculta/muestra las historias de un autor (no borra nada; solo dejo de verlas).
  Future<void> alternarOcultarEstados(String email) async {
    final e = email.trim().toLowerCase();
    if (e.isEmpty) return;
    if (!_estadosOcultos.remove(e)) _estadosOcultos.add(e);
    notifyListeners();
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(
          _kEstadosOcultos, jsonEncode(_estadosOcultos.toList()));
    } catch (_) {}
  }

  String get _yo => (usuario?.email ?? '').trim().toLowerCase();

  /// Correos "conocidos" cuyos estados me interesa ver: mis contactos, la gente
  /// con la que he chateado (perfiles cacheados) y a quien le puse apodo. Nunca
  /// los bloqueados.
  Set<String> _conocidos() {
    // REGLA de privacidad: solo veo historias de contactos que YO agregué
    // (`_contactos`). Antes se incluía `_perfiles.keys`, pero ese cache se llena
    // con TODOS los autores de historias al cargarlas → cualquiera se volvía
    // "conocido" y se filtraban historias ajenas. NO usar perfiles/apodos aquí.
    final s = <String>{...contactos};
    s.remove('');
    s.remove(_yo);
    s.removeWhere((e) => _bloqueados.contains(e) || _estadosOcultos.contains(e));
    return s;
  }

  /// Estados de un autor (vigentes), en orden de publicación (más antiguo
  /// primero, como WhatsApp).
  List<Estado> estadosDe(String? email) {
    final e = (email ?? '').trim().toLowerCase();
    final l = _estados.where((x) => x.autorEmail == e && x.vigente).toList();
    l.sort((a, b) => a.creadoEn.compareTo(b.creadoEn));
    return l;
  }

  /// Mis propios estados vigentes.
  List<Estado> get misEstados => estadosDe(_yo);

  /// ¿El autor tiene al menos un estado que YO no he visto? (aro lima vs gris).
  bool autorTieneNoVisto(String? email) =>
      estadosDe(email).any((x) => !_estadosVistos.contains(x.id));

  /// Autores conocidos con estado vigente, ordenados: los que tienen algo no
  /// visto primero; dentro de cada grupo, el más reciente arriba.
  List<String> autoresConEstado() {
    final conocidos = _conocidos();
    final autores = <String>{};
    for (final e in _estados) {
      if (e.vigente && conocidos.contains(e.autorEmail)) autores.add(e.autorEmail);
    }
    final l = autores.toList();
    l.sort((a, b) {
      final na = autorTieneNoVisto(a);
      final nb = autorTieneNoVisto(b);
      if (na != nb) return na ? -1 : 1;
      final ea = estadosDe(a);
      final eb = estadosDe(b);
      final ta = ea.isEmpty ? DateTime(0) : ea.last.creadoEn;
      final tb = eb.isEmpty ? DateTime(0) : eb.last.creadoEn;
      return tb.compareTo(ta);
    });
    return l;
  }

  /// Correos que vieron un estado mío (para "visto por N").
  List<String> vistasDe(String id) => _vistasPorEstado[id] ?? const [];
  int vistasCount(String id) => vistasDe(id).length;

  /// Trae los estados vigentes de Supabase y, para los míos, quién los vio.
  /// Best-effort (fail-safe). Se llama al iniciar sesión, al abrir Mensajes y
  /// con pull-to-refresh.
  Future<void> cargarEstados() async {
    if (!EstadosRepo.disponible) return;
    final vigentes = await EstadosRepo.fetchVigentes();
    _estados
      ..clear()
      ..addAll(vigentes);
    // Pre-cachea la media de los estados AJENOS (fotos/videos) para abrirlos al
    // instante, sin "cargando", como WhatsApp. Fire-and-forget.
    _precacharEstados(vigentes);
    // Poda el set de vistos a lo que sigue vigente (no crece indefinidamente).
    final ids = vigentes.map((e) => e.id).toSet();
    _estadosVistos.retainWhere(ids.contains);
    // Trae los perfiles de los autores para mostrar nombre/foto en el aro.
    final autores = vigentes.map((e) => e.autorEmail).toSet().toList();
    if (autores.isNotEmpty) await cargarPerfiles(autores);
    // "Quién vio" MIS estados.
    final mios = misEstados.map((e) => e.id).toList();
    if (mios.isNotEmpty) {
      final v = await EstadosRepo.vistas(mios);
      _vistasPorEstado
        ..clear()
        ..addAll(v);
    }
    notifyListeners();
    await _persistirEstadosVistos();
  }

  /// Descarga a la caché de disco la media de los estados ajenos (la propia ya
  /// se reproduce local). Así el visor abre sin spinner (como WhatsApp).
  void _precacharEstados(List<Estado> estados) {
    final yo = (usuario?.email ?? '').toLowerCase();
    for (final e in estados) {
      if (!e.tieneMedia) continue;
      if (e.autorEmail.toLowerCase() == yo) continue; // el mío ya es local
      unawaited(DefaultCacheManager()
          .downloadFile(e.fotoUrl)
          .then((_) {})
          .catchError((_) {}));
    }
  }

  Future<void> _persistirEstadosVistos() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(
          _kEstadosVistos, jsonEncode(_estadosVistos.toList()));
    } catch (_) {}
  }

  /// Publica un estado de TEXTO (sobre un color de fondo). Devuelve el estado o
  /// null si falla. Acepta música opcional (preview 30 s).
  Future<Estado?> publicarEstadoTexto(
    String texto,
    int bg, {
    String musicaTitulo = '',
    String musicaArtista = '',
    String musicaPreview = '',
    String musicaArt = '',
    int musicaInicioMs = 0,
    String musicaTrackUrl = '',
  }) async {
    final u = usuario;
    final t = texto.trim();
    if (u == null || t.isEmpty) return null;
    final e = Estado(
      id: 'st_${DateTime.now().microsecondsSinceEpoch}',
      autorEmail: u.email.toLowerCase(),
      autorNombre: u.nombre,
      tipo: 'texto',
      texto: t,
      bg: bg,
      creadoEn: DateTime.now(),
      musicaTitulo: musicaTitulo,
      musicaArtista: musicaArtista,
      musicaPreview: musicaPreview,
      musicaArt: musicaArt,
      musicaInicioMs: musicaInicioMs,
      musicaTrackUrl: musicaTrackUrl,
    );
    final ok = await EstadosRepo.publicar(e);
    if (!ok) return null;
    _estados.add(e);
    _estadosVistos.add(e.id); // los míos ya "vistos" por mí
    notifyListeners();
    return e;
  }

  /// Publica un estado de FOTO (con pie opcional). Sube la imagen al bucket.
  /// Devuelve el estado o null si falla (motivo en EstadosRepo.ultimoErrorFoto).
  Future<Estado?> publicarEstadoFoto(
    Uint8List bytes, {
    String pie = '',
    String musicaTitulo = '',
    String musicaArtista = '',
    String musicaPreview = '',
    String musicaArt = '',
    int musicaInicioMs = 0,
    String musicaTrackUrl = '',
  }) async {
    final u = usuario;
    if (u == null) return null;
    final id = 'st_${DateTime.now().microsecondsSinceEpoch}';
    final url = await EstadosRepo.subirFoto(id, bytes);
    if (url == null) return null;
    final e = Estado(
      id: id,
      autorEmail: u.email.toLowerCase(),
      autorNombre: u.nombre,
      tipo: 'foto',
      texto: pie.trim(),
      fotoUrl: url,
      creadoEn: DateTime.now(),
      musicaTitulo: musicaTitulo,
      musicaArtista: musicaArtista,
      musicaPreview: musicaPreview,
      musicaArt: musicaArt,
      musicaInicioMs: musicaInicioMs,
      musicaTrackUrl: musicaTrackUrl,
    );
    final ok = await EstadosRepo.publicar(e);
    if (!ok) return null;
    _estados.add(e);
    _estadosVistos.add(e.id);
    notifyListeners();
    return e;
  }

  /// Publica un estado de VIDEO (con pie opcional). Sube el clip al bucket.
  /// Devuelve el estado o null si falla (motivo en EstadosRepo.ultimoErrorFoto).
  Future<Estado?> publicarEstadoVideo(
    Uint8List bytes, {
    String pie = '',
    String rutaLocal = '', // ruta del archivo local (para reproducirlo sin bajar)
    String musicaTitulo = '',
    String musicaArtista = '',
    String musicaPreview = '',
    String musicaArt = '',
    int musicaInicioMs = 0,
    String musicaTrackUrl = '',
  }) async {
    final u = usuario;
    if (u == null) return null;
    final id = 'st_${DateTime.now().microsecondsSinceEpoch}';
    final url = await EstadosRepo.subirVideo(id, bytes);
    if (url == null) return null;
    final e = Estado(
      id: id,
      autorEmail: u.email.toLowerCase(),
      autorNombre: u.nombre,
      tipo: 'video',
      texto: pie.trim(),
      fotoUrl: url,
      creadoEn: DateTime.now(),
      musicaTitulo: musicaTitulo,
      musicaArtista: musicaArtista,
      musicaPreview: musicaPreview,
      musicaArt: musicaArt,
      musicaInicioMs: musicaInicioMs,
      musicaTrackUrl: musicaTrackUrl,
    );
    final ok = await EstadosRepo.publicar(e);
    if (!ok) return null;
    // Device-first: recuerda el archivo LOCAL para reproducir MI historia al
    // instante (sin re-bajar de la nube).
    if (rutaLocal.isNotEmpty) recordarVideoLocal(url, rutaLocal);
    _estados.add(e);
    _estadosVistos.add(e.id);
    notifyListeners();
    return e;
  }

  // ── Videos de historia: mapa URL remota → archivo LOCAL (device-first) ─────
  final Map<String, String> _videosLocales = {};

  /// Archivo local del video de esta URL (para reproducirlo sin bajarlo), o null.
  String? videoLocalDe(String url) => _videosLocales[url];

  /// Recuerda (y persiste) el archivo local de un video de historia.
  void recordarVideoLocal(String url, String ruta) {
    if (url.isEmpty || ruta.isEmpty) return;
    _videosLocales[url] = ruta;
    _guardarVideosLocales();
  }

  Future<void> _guardarVideosLocales() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(_kVideosLocales, jsonEncode(_videosLocales));
    } catch (_) {}
  }

  /// Envía un mensaje DIRECTO 1:1 a [paraEmail] (usado para "responder historia").
  /// Acepta una CITA opcional (autor/texto/miniatura) para que la respuesta a una
  /// historia muestre la historia citada, tipo WhatsApp. Devuelve true si se envió.
  Future<bool> enviarMensajeDirecto(
    String paraEmail,
    String texto, {
    String respTexto = '',
    String respAutor = '',
    String respMedia = '',
  }) async {
    final u = usuario;
    final t = texto.trim();
    final para = paraEmail.trim().toLowerCase();
    if (u == null || t.isEmpty || para.isEmpty || bloqueado(para)) return false;
    final msg = Mensaje(
      id: 'msg_${DateTime.now().microsecondsSinceEpoch}',
      hilo: Mensaje.hiloDirecto(u.email, para),
      tipo: 'directo',
      refId: '',
      academiaId: '',
      cuentaEmail: para,
      autorEmail: u.email,
      autorNombre: u.nombre,
      esProfe: false,
      texto: t,
      respTexto: respTexto,
      respAutor: respAutor,
      respMedia: respMedia,
      creado: DateTime.now(),
    );
    return MensajesRepo.enviar(msg);
  }

  /// Marca que YO vi un estado (aro gris + registra la vista para el autor).
  Future<void> marcarEstadoVisto(String id) async {
    if (id.isEmpty || _estadosVistos.contains(id)) return;
    _estadosVistos.add(id);
    notifyListeners();
    await _persistirEstadosVistos();
    await EstadosRepo.marcarVisto(id, _yo);
  }

  /// Borra un estado propio (local + Supabase).
  Future<void> eliminarEstado(String id) async {
    _estados.removeWhere((e) => e.id == id);
    _vistasPorEstado.remove(id);
    notifyListeners();
    await EstadosRepo.eliminar(id);
  }

  /// Carga (best-effort) los perfiles —para tener NOMBRE y FOTO— de todos los
  /// jugadores que aparecen en el ranking: participantes de retos (incluidos los
  /// compañeros de dobles) y de partidos de academia. Así las filas del ranking
  /// muestran la foto real en vez de la inicial.
  Future<void> cargarFotosDeParticipantes() async {
    final emails = <String>{};
    for (final r in _retosResultados) {
      for (final k in const [
        'retador_email',
        'retado_email',
        'retador2_email',
        'retado2_email'
      ]) {
        final e = (r[k] ?? '').toString().trim().toLowerCase();
        if (e.isNotEmpty) emails.add(e);
      }
    }
    for (final a in academias) {
      for (final p in a.partidos) {
        for (final id in [p.jugadorAId, p.jugadorBId]) {
          if (id.isEmpty) continue;
          final e = p.emailDe(id).trim().toLowerCase();
          if (e.isNotEmpty) emails.add(e);
        }
      }
    }
    if (emails.isNotEmpty) await cargarPerfiles(emails.toList());
  }

  /// Trae de Supabase los perfiles de estos correos y los cachea (best-effort).
  /// Con [forzar] re-baja aunque ya estén en caché (para refrescar foto/nombre).
  Future<void> cargarPerfiles(List<String> emails, {bool forzar = false}) async {
    final faltan = emails
        .map((e) => e.trim().toLowerCase())
        .where((e) => e.isNotEmpty && (forzar || !_perfiles.containsKey(e)))
        .toList();
    if (faltan.isEmpty) return;
    final res = await PerfilesRepo.obtenerVarios(faltan);
    if (res.isEmpty) return;
    _perfiles.addAll(res);
    notifyListeners();
    _guardarPerfiles(); // persiste para el próximo arranque (device-first)
  }

  /// Guarda el caché de perfiles en disco (nombre+foto), para pintar al instante
  /// al reabrir sin re-descargar.
  Future<void> _guardarPerfiles() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(_kPerfiles, jsonEncode(_perfiles));
    } catch (_) {}
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

  // ── PUNTOS Pichangol del jugador (beneficios cruzados) ────────────────────
  // DERIVADOS siempre de las reservas (sin contador aparte → sin bugs de doble
  // acreditación y consistentes entre equipos): 1 punto por cada S/1 pagado
  // POR LA APP en los últimos 12 meses. Online acredita al instante; el
  // EFECTIVO recién cuando el DUEÑO lo marca pagado → el jugador tiene motivo
  // para exigir esa confirmación (sube el registro de cobros). La reserva
  // MANUAL (cliente propio del dueño, fuera de comisión) no acumula.

  /// Puntos ACREDITADOS del jugador (reservas por la app ya pagadas, últimos
  /// 12 meses).
  int get misPuntos => _puntosDe(pagadas: true);

  /// Puntos "por confirmar": reservas por la app aún NO marcadas como pagadas
  /// (típicamente efectivo que el dueño no registró). La palanca del jugador.
  int get misPuntosPendientes => _puntosDe(pagadas: false);

  int _puntosDe({required bool pagadas}) {
    final desde = DateTime.now().subtract(const Duration(days: 365));
    var total = 0;
    for (final r in misReservas) {
      if (!r.traidaPorApp) continue; // manual: fuera del programa
      if (r.estado == EstadoReserva.noShow) continue;
      if (r.pagado != pagadas) continue;
      final f = DateTime.tryParse(r.fecha);
      if (f == null || f.isBefore(desde)) continue;
      total += r.totalConExtras.round();
    }
    return total;
  }

  // ── Reservas OFFLINE: bandeja de salida (outbox) ──────────────────────────
  // Ids de reservas guardadas LOCAL que aún NO llegaron a Supabase (se hicieron
  // sin señal). Se reintenta subirlas al recuperar conexión. Persisten para
  // sobrevivir cierres de la app. Mientras estén aquí, son "Pendiente de
  // confirmar" (no cuentan como confirmadas para el jugador).
  final Set<String> _reservasPendientesSync = {};
  // Ids de reservas que NO se pudieron confirmar: el slot ya lo tomó otro, o la
  // app sincronizó DESPUÉS de la hora de juego. Se muestran "No se confirmó".
  final Set<String> _reservasNoConfirmadas = {};
  static const _kResvPend = 'reservas_pendientes_sync';
  static const _kResvNoConf = 'reservas_no_confirmadas';

  // ── Contabilidad de reservas (comisión/liquidación) con REINTENTO ──────────
  // Antes la comisión/liquidación era "best-effort": UNA llamada al confirmar la
  // reserva; si fallaba la red, se PERDÍA (el dueño no veía el descuento). Ahora
  // se encola y se reintenta (el backend es idempotente por reserva_id).
  final List<Map<String, dynamic>> _contaPend = [];
  // Acción contable EN ESPERA de una reserva que quedó offline: se registra
  // recién cuando la reserva se CONFIRMA en el servidor (o se marca reembolso si
  // expira / se ocupa). reservaId → acción.
  final Map<String, Map<String, dynamic>> _contaEnEspera = {};
  // Reembolsos pendientes: pagos ONLINE cobrados cuya reserva NO se pudo asegurar
  // (slot ocupado / expiró). Registro auditable para no quedarnos con la plata;
  // el reembolso real (Culqi) es una tarea aparte del backend.
  final List<Map<String, dynamic>> _reembolsosPend = [];
  static const _kContaPend = 'conta_pendiente_json';
  static const _kContaEspera = 'conta_espera_json';
  static const _kReembolsos = 'reembolsos_pendientes_json';

  int get reembolsosPendientes => _reembolsosPend.length;

  List<Map<String, dynamic>> _listaMapa(String? raw) {
    if (raw == null || raw.isEmpty) return [];
    try {
      return (jsonDecode(raw) as List)
          .map((e) => Map<String, dynamic>.from(e as Map))
          .toList();
    } catch (_) {
      return [];
    }
  }

  Future<void> cargarContabilidad() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      _contaPend
        ..clear()
        ..addAll(_listaMapa(prefs.getString(_kContaPend)));
      _reembolsosPend
        ..clear()
        ..addAll(_listaMapa(prefs.getString(_kReembolsos)));
      _contaEnEspera.clear();
      final esp = prefs.getString(_kContaEspera);
      if (esp != null && esp.isNotEmpty) {
        (jsonDecode(esp) as Map<String, dynamic>).forEach(
            (k, v) => _contaEnEspera[k] = Map<String, dynamic>.from(v as Map));
      }
    } catch (_) {}
  }

  Future<void> _persistirContabilidad() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(_kContaPend, jsonEncode(_contaPend));
      await prefs.setString(_kReembolsos, jsonEncode(_reembolsosPend));
      await prefs.setString(_kContaEspera, jsonEncode(_contaEnEspera));
    } catch (_) {}
  }

  /// Construye la acción contable de una reserva según cómo se cobró. Null si la
  /// cancha no tiene dueño (nadie a quien acreditar/cobrar).
  Map<String, dynamic>? _accionContable(Cancha cancha, String cobro,
      {required double montoBase,
      required int sena,
      required String reservaId,
      required String etiqueta}) {
    if (cancha.dueno.isEmpty) return null;
    switch (cobro) {
      case 'efectivo':
        return {
          'kind': 'comision', 'dueno': cancha.dueno, 'monto': montoBase,
          'reserva_id': reservaId, 'concepto': 'Comisión · $etiqueta',
          'online': false,
        };
      case 'online':
        return {
          'kind': 'liquidacion', 'dueno': cancha.dueno, 'monto': montoBase,
          'reserva_id': reservaId, 'concepto': 'Reserva online · $etiqueta',
          'online': true,
        };
      case 'sena':
        return {
          'kind': 'liquidacion', 'dueno': cancha.dueno,
          'monto': sena.toDouble(), 'reserva_id': reservaId,
          'concepto': 'Seña · $etiqueta', 'online': true,
        };
      default:
        return null;
    }
  }

  void _encolarConta(Map<String, dynamic> accion) {
    final dup = _contaPend.any((x) =>
        x['reserva_id'] == accion['reserva_id'] && x['kind'] == accion['kind']);
    if (!dup) _contaPend.add(accion);
    unawaited(_persistirContabilidad());
    unawaited(flushContabilidad());
  }

  /// Reintenta registrar en el backend la contabilidad pendiente (comisión de
  /// saldo / liquidación online). Idempotente por reserva_id → seguro repetir.
  Future<void> flushContabilidad() async {
    if (_contaPend.isEmpty || !PagosService.disponible) return;
    var cambios = false;
    for (final e in [..._contaPend]) {
      final monto = (e['monto'] as num?)?.toDouble() ?? 0;
      final rid = (e['reserva_id'] ?? '').toString();
      bool quitar = monto <= 0; // nada que registrar
      if (!quitar) {
        Map<String, dynamic>? r;
        if (e['kind'] == 'comision') {
          r = await PagosService.comisionReserva(
              duenoId: (e['dueno'] ?? '').toString(),
              montoSoles: monto,
              reservaId: rid,
              concepto: (e['concepto'] ?? '').toString());
        } else {
          r = await PagosService.liquidacionOnline(
              duenoId: (e['dueno'] ?? '').toString(),
              montoSoles: monto,
              reservaId: rid,
              concepto: (e['concepto'] ?? '').toString());
        }
        quitar = r != null; // 200 (ok o duplicada) → listo
      }
      if (quitar) {
        _contaPend.removeWhere(
            (x) => x['reserva_id'] == rid && x['kind'] == e['kind']);
        cambios = true;
      }
    }
    if (cambios) await _persistirContabilidad();
  }

  void _registrarReembolso(String reservaId, double monto, String motivo) {
    if (monto <= 0) return;
    _reembolsosPend.add({
      'reserva_id': reservaId,
      'email': (usuario?.email ?? '').toLowerCase(),
      'monto': monto,
      'motivo': motivo,
    });
    unawaited(_persistirContabilidad());
  }

  /// Una reserva pendiente (offline) que NO llegó a confirmarse: si su pago fue
  /// online, registra el reembolso; descarta su acción contable en espera.
  void _reembolsoSiEnEspera(String reservaId, String motivo) {
    final accion = _contaEnEspera.remove(reservaId);
    if (accion == null) return;
    if (accion['online'] == true) {
      _registrarReembolso(
          reservaId, (accion['monto'] as num?)?.toDouble() ?? 0, motivo);
    }
    unawaited(_persistirContabilidad());
  }

  /// ¿La reserva está guardada pero aún no confirmada en el servidor (offline)?
  bool reservaPendienteSync(String id) => _reservasPendientesSync.contains(id);

  /// ¿La reserva no se pudo confirmar (slot tomado o sincronizó tarde)?
  bool reservaNoConfirmada(String id) => _reservasNoConfirmadas.contains(id);

  Future<void> cargarReservasSync() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      _reservasPendientesSync
        ..clear()
        ..addAll(prefs.getStringList(_kResvPend) ?? const []);
      _reservasNoConfirmadas
        ..clear()
        ..addAll(prefs.getStringList(_kResvNoConf) ?? const []);
    } catch (_) {}
  }

  Future<void> _persistirReservasSync() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setStringList(_kResvPend, _reservasPendientesSync.toList());
      await prefs.setStringList(_kResvNoConf, _reservasNoConfirmadas.toList());
    } catch (_) {}
  }

  /// ¿La hora de inicio del slot ya pasó (respecto a ahora)? Si no se puede
  /// parsear, se asume que NO pasó (para no expirar por error).
  bool _slotYaPaso(Reserva r) {
    try {
      final f = r.fecha.split('-'); // yyyy-MM-dd
      final h = r.horaInicio.split(':'); // HH:mm
      if (f.length < 3 || h.length < 2) return false;
      final dt = DateTime(int.parse(f[0]), int.parse(f[1]), int.parse(f[2]),
          int.parse(h[0]), int.parse(h[1]));
      return dt.isBefore(DateTime.now());
    } catch (_) {
      return false;
    }
  }

  Cancha? _canchaPorIdAny(String id) {
    for (final c in [...canchasExtra, ...canchasRemotas]) {
      if (c.id == id) return c;
    }
    return SampleData.canchaPorId(id);
  }

  /// Versión MÁS FRESCA de una cancha por id (para que la ficha del jugador
  /// refleje al instante lo que el dueño acaba de editar: duración de slot,
  /// precio, horario, nombre, etc.). Prioridad: canchasExtra (registradas en
  /// este equipo) → canchasRemotas (Supabase) → descubiertas (Google) → el
  /// snapshot recibido. Nunca devuelve null: cae a `c` si no la encuentra.
  Cancha canchaVigente(Cancha c) {
    for (final x in canchasExtra) {
      if (x.id == c.id) return x;
    }
    for (final x in canchasRemotas) {
      if (x.id == c.id) return x;
    }
    for (final x in canchasDescubiertas) {
      if (x.id == c.id) return x;
    }
    // Fallback por SITIO: si lo que se muestra es la versión DESCUBIERTA de
    // Google (sin registrar, id = place_id) y existe la MISMA cancha REGISTRADA
    // con otro id (Supabase), usa la registrada: trae la duración/precio/horario
    // REALES que editó el dueño (la de Google trae los valores por defecto).
    if (!c.registrada) {
      Cancha? reg;
      for (final x in [...canchasExtra, ...canchasRemotas]) {
        if (!x.registrada) continue;
        if (x.deporte == c.deporte && _cercaDe(x.ubicacion, c.ubicacion, 0.10)) {
          if (reg == null || _puntajeCancha(x) > _puntajeCancha(reg)) reg = x;
        }
      }
      if (reg != null) return reg;
    }
    return c;
  }

  /// De qué FUENTE sale una cancha por id (diagnóstico). Ayuda a entender por qué
  /// una ficha muestra datos viejos: 'extra' (registrada en este equipo),
  /// 'remota' (Supabase), 'google' (descubierta) o 'snapshot' (no está en listas).
  String fuenteCancha(String id) {
    if (canchasExtra.any((x) => x.id == id)) return 'extra';
    if (canchasRemotas.any((x) => x.id == id)) return 'remota';
    if (canchasDescubiertas.any((x) => x.id == id)) return 'google';
    return 'snapshot';
  }

  /// Avisa al DUEÑO de la cancha que entró una reserva, con un PUSH DEDICADO
  /// (fuera del chat) vía la Edge Function `push-reserva`. Se manda solo el id
  /// (o el del grupo si son varias horas); el servidor deriva destinatario y
  /// texto. Se llama cuando la reserva quedó CONFIRMADA en el servidor (no
  /// offline). No avisa si el dueño es el propio jugador (el backend lo revalida).
  void _notificarDuenoReserva(Cancha cancha, List<Reserva> rs) {
    final dueno = cancha.dueno.trim().toLowerCase();
    final yo = (usuario?.email ?? '').trim().toLowerCase();
    if (dueno.isEmpty || dueno == yo || rs.isEmpty) return;
    final r0 = rs.first;
    unawaited(PushService.avisarReserva(
        reservaId: r0.id, grupoId: r0.grupoReservaId));
  }

  /// Reintenta subir a Supabase las reservas que quedaron pendientes (offline).
  /// Reglas al sincronizar: si el slot YA PASÓ o el horario lo tomó otro jugador,
  /// NO se crea la reserva (queda "no confirmada" y se libera el slot local); si
  /// entra bien, se confirma y se AVISA al dueño. Fail-safe.
  Future<void> sincronizarReservasPendientes() async {
    if (_reservasPendientesSync.isEmpty || !SupabaseService.disponible) return;
    final ids = [..._reservasPendientesSync];
    final gruposNotificados = <String>{};
    var cambios = false;
    for (final id in ids) {
      final idx = reservas.indexWhere((x) => x.id == id);
      if (idx < 0) {
        _reservasPendientesSync.remove(id);
        cambios = true;
        continue;
      }
      final r = reservas[idx];
      // Sincronizó DESPUÉS de la hora de juego → ya no vale.
      if (_slotYaPaso(r)) {
        _reservasPendientesSync.remove(id);
        _reservasNoConfirmadas.add(id);
        reservas.removeWhere((x) => x.id == id); // libera slot; el dueño no la ve
        _reembolsoSiEnEspera(id, 'Sincronizó después de la hora de juego');
        cambios = true;
        continue;
      }
      final res = await ReservasRepo.insertarSegura(r);
      if (res == ResultadoReserva.ok) {
        _reservasPendientesSync.remove(id);
        cambios = true;
        // Recién ahora registra la contabilidad (comisión/liquidación).
        final accion = _contaEnEspera.remove(id);
        if (accion != null) _encolarConta(accion);
        final cancha = _canchaPorIdAny(r.canchaId);
        if (cancha != null) {
          final clave = r.grupoReservaId.isNotEmpty ? r.grupoReservaId : r.id;
          if (gruposNotificados.add(clave)) {
            final grupo = r.grupoReservaId.isNotEmpty
                ? reservas
                    .where((x) => x.grupoReservaId == r.grupoReservaId)
                    .toList()
                : [r];
            _notificarDuenoReserva(cancha, grupo);
          }
        }
      } else if (res == ResultadoReserva.ocupado) {
        // Otro jugador ganó el slot mientras estabas offline.
        _reservasPendientesSync.remove(id);
        _reservasNoConfirmadas.add(id);
        reservas.removeWhere((x) => x.id == id);
        _reembolsoSiEnEspera(id, 'El horario lo tomó otro jugador');
        cambios = true;
      }
      // sinConexion / error → sigue pendiente para el próximo intento.
    }
    if (cambios) {
      _recomputarMisReservas();
      notifyListeners();
      await _persistirReservasSync();
      await _persistirContabilidad();
      _persistirDatos();
    }
  }
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

  /// Ids de academias BORRADAS (tombstones durables). Aunque la nube devuelva la
  /// academia (p. ej. el borrado lógico en Supabase falló por RLS), NO reaparece
  /// en este dispositivo. También bloquea el re-sembrado de la academia demo si
  /// el usuario la borró. Espeja `canchasEliminadas`. Se persiste.
  final Set<String> _academiasEliminadas = {};
  final List<Alumno> alumnos = [];
  final List<Cuota> cuotas = [];
  final List<Asistencia> asistencias = [];
  final List<Invitacion> invitaciones = []; // invitaciones profe → alumno
  final List<PlanTrabajo> planes = []; // planes de trabajo (por academia)
  final List<EvaluacionAlumno> evaluaciones = []; // rúbrica por alumno/plan
  final List<NotaClase> notasClase = []; // bitácora diaria (evaluación por clase)

  // Última vez que el usuario abrió cada hilo de chat (hilo → ISO). Sirve para
  // el contador de "no leídos" (Etapa A del chat).
  final Map<String, String> chatLecturas = {};

  // Chats que el usuario "eliminó" de su bandeja (hilo → ISO de cuándo lo ocultó).
  // Es por-usuario y local, igual que WhatsApp: se quita de TU lista; si luego
  // llega un mensaje MÁS NUEVO que la fecha de ocultado, la conversación reaparece.
  final Map<String, String> chatsOcultos = {};

  // Acciones de bandeja estilo WhatsApp (por-usuario, locales):
  final Set<String> chatsFijados = {};      // pin: van primero en la lista
  final Set<String> chatsArchivados = {};   // salen de la bandeja → "Archivados"
  final Set<String> chatsSilenciados = {};  // sin aviso in-app de mensajes nuevos

  // ── Campeonatos de academias ──────────────────────────────────────────────
  final List<Campeonato> campeonatos = [];
  bool descubriendo = false; // true mientras se traen canchas cercanas (feedback UI)

  /// Clubes sembrados en el mapa. VACÍO (virgen, como PRD): el explorador enseña
  /// solo canchas REALES (Google Places + Supabase + las que registra el dueño),
  /// sin data demo. Antes traía `SampleData.sembradas` (Regatas, ESMON, CEANDE…),
  /// que aparecían como reclamables aunque la app estuviera "en virgen".
  final List<Cancha> _sembradas = [];

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

  /// Academia por id (o null). La usa el chat de academia para saber su DUEÑO.
  Academia? academiaPorId(String id) {
    if (id.isEmpty) return null;
    for (final a in academias) {
      if (a.id == id) return a;
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
    // Campeonatos independientes con al menos un partido jugado.
    for (final c in campeonatos) {
      if (c.academiaId.isEmpty && c.partidos.any((p) => p.jugado)) {
        s.add(c.deporte);
      }
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
        // Los retos de DOBLES van a su propia tabla (rankingDobles), no aquí.
        if ((r['modalidad'] ?? 'singles').toString() == 'dobles') continue;
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
    // Pliega los CAMPEONATOS INDEPENDIENTES (sin academia) — los de academia ya
    // entran por academia.partidos. Cada partido jugado suma al equipo/jugador.
    // (Fútbol: la fila es el EQUIPO; individuales, por correo.)
    for (final camp in campeonatos) {
      if (camp.academiaId.isNotEmpty) continue; // ya contado vía academia
      if (deporte != null && camp.deporte != deporte) continue;
      if (zona != null && zona.isNotEmpty) continue; // los torneos no tienen zona
      if (categoria != null &&
          categoria.isNotEmpty &&
          camp.categoria != categoria) continue;
      final fecha = camp.inicio ?? camp.inscripcionHasta ?? DateTime.now();
      if (temporada != null && !temporada.contiene(fecha)) continue;
      final byId = {for (final p in camp.participantes) p.id: p};
      for (final pt in camp.partidos) {
        if (!pt.jugado) continue;
        final aId = pt.aId, bId = pt.bId, gid = pt.ganadorId;
        if (aId == null || bId == null || gid == null) continue;
        for (final id in [aId, bId]) {
          final p = byId[id];
          if (p == null) continue;
          final email = p.email.trim().toLowerCase();
          final key = p.esEquipo
              ? 't:${camp.id}|$id'
              : (email.isNotEmpty ? 'e:$email' : 'c:${camp.id}|$id');
          final g = agg.putIfAbsent(key, () => _AggGlobal(deporte: camp.deporte));
          g.pj++;
          if (gid == id) {
            g.pg++;
          } else {
            g.pp++;
          }
          if (p.nombre.isNotEmpty) g.nombre = p.nombre;
          if (camp.categoria.isNotEmpty) g.categoria = camp.categoria;
          g.porAcademia[camp.nombre] = (g.porAcademia[camp.nombre] ?? 0) + 1;
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

  /// Ranking de DOBLES (parejas), SEPARADO del de singles. Se arma solo con los
  /// retos de modalidad 'dobles': cada partido suma a las DOS parejas y da la
  /// victoria a la pareja del ganador reportado. La identidad de la fila es la
  /// pareja (clave canónica `d:correoA|correoB` con los correos ordenados, así
  /// "A/B" y "B/A" son la misma pareja). `alumnoId` guarda esa clave.
  List<RankingGlobalFila> rankingDobles(
      {Deporte? deporte, String? zona, Temporada? temporada}) {
    final agg = <String, _AggGlobal>{};
    final nombres = <String, String>{}; // clave pareja → "NombreA / NombreB"
    for (final r in _retosResultados) {
      if ((r['modalidad'] ?? 'singles').toString() != 'dobles') continue;
      final dep = _deporteDe(r['deporte']) ?? Deporte.tenis;
      if (deporte != null && dep != deporte) continue;
      if (zona != null &&
          zona.isNotEmpty &&
          (r['zona'] ?? '').toString().trim() != zona) continue;
      if (temporada != null && !temporada.contiene(_fechaReto(r))) continue;
      final ganador =
          (r['ganador_email'] ?? '').toString().trim().toLowerCase();
      if (ganador.isEmpty) continue;

      // Cada lado es una pareja: (correo, nombre) x2.
      final ladoRetador = [
        (r['retador_email'], r['retador_nombre']),
        (r['retador2_email'], r['retador2_nombre']),
      ];
      final ladoRetado = [
        (r['retado_email'], r['retado_nombre']),
        (r['retado2_email'], r['retado2_nombre']),
      ];
      final claveRetador = _clavePareja(ladoRetador);
      final claveRetado = _clavePareja(ladoRetado);
      if (claveRetador == null || claveRetado == null) continue;
      nombres[claveRetador] ??= _nombrePareja(ladoRetador);
      nombres[claveRetado] ??= _nombrePareja(ladoRetado);

      // ¿Qué lado ganó? El que contiene al correo ganador.
      final correosRetador = ladoRetador
          .map((e) => (e.$1 ?? '').toString().trim().toLowerCase())
          .toSet();
      final ganoRetador = correosRetador.contains(ganador);

      for (final entry in [
        (claveRetador, ganoRetador),
        (claveRetado, !ganoRetador),
      ]) {
        final g = agg.putIfAbsent(entry.$1, () => _AggGlobal(deporte: dep));
        g.pj++;
        if (entry.$2) {
          g.pg++;
        } else {
          g.pp++;
        }
        g.nombre = nombres[entry.$1] ?? g.nombre;
        g.porAcademia['Dobles'] = (g.porAcademia['Dobles'] ?? 0) + 1;
      }
    }

    final filas = <RankingGlobalFila>[];
    agg.forEach((key, g) {
      if (g.pj == 0) return;
      filas.add(RankingGlobalFila(
        academiaId: '',
        academiaNombre: 'Dobles',
        deporte: g.deporte,
        alumnoId: key,
        nombre: g.nombre,
        categoria: '',
        pj: g.pj,
        pg: g.pg,
        pp: g.pp,
        puntos: g.pg * Academia.puntosVictoria + g.pp * Academia.puntosDerrota,
        pct: g.pj == 0 ? 0 : g.pg / g.pj * 100,
        academias: 0,
      ));
    });
    filas.sort((x, y) {
      if (y.puntos != x.puntos) return y.puntos.compareTo(x.puntos);
      if (y.pct != x.pct) return y.pct.compareTo(x.pct);
      return y.pg.compareTo(x.pg);
    });
    return filas;
  }

  /// Clave canónica de una pareja a partir de sus dos (correo, nombre). Ordena
  /// los correos para que "A/B" == "B/A". Null si falta algún correo.
  String? _clavePareja(List<(dynamic, dynamic)> lado) {
    final correos = lado
        .map((e) => (e.$1 ?? '').toString().trim().toLowerCase())
        .where((e) => e.isNotEmpty)
        .toList()
      ..sort();
    if (correos.length != 2) return null;
    return 'd:${correos[0]}|${correos[1]}';
  }

  /// Nombre visible de una pareja: "NombreA / NombreB" (cae al correo si falta).
  String _nombrePareja(List<(dynamic, dynamic)> lado) {
    final ns = lado.map((e) {
      final n = (e.$2 ?? '').toString().trim();
      if (n.isNotEmpty) return n;
      final c = (e.$1 ?? '').toString().trim();
      return c.contains('@') ? c.split('@').first : c;
    }).where((n) => n.isNotEmpty).toList();
    return ns.join(' / ');
  }

  /// ¿Hay al menos un reto de dobles jugado para este deporte? (para mostrar la
  /// pestaña de dobles solo cuando tiene sentido).
  bool hayRankingDobles(Deporte deporte) {
    for (final r in _retosResultados) {
      if ((r['modalidad'] ?? 'singles').toString() != 'dobles') continue;
      if ((_deporteDe(r['deporte']) ?? Deporte.tenis) == deporte) return true;
    }
    return false;
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
        academiaId: n.id, datos: n.datosLanding, contexto: tema,
        email: usuario?.email ?? '');
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
    final planesBorrados =
        planes.where((p) => p.academiaId == id).map((p) => p.id).toSet();
    planes.removeWhere((p) => p.academiaId == id);
    evaluaciones.removeWhere((e) => planesBorrados.contains(e.planId));
    _academiasEliminadas.add(id); // tombstone durable: no reaparece aunque la
    _academiasPendientesNube.remove(id); // nube la devuelva (RLS) ni se re-siembre
    notifyListeners();
    _persistirDatos();
    AcademiasRepo.eliminar(id); // borrado lógico durable en la nube (best-effort)
  }

  // ── Campeonatos ────────────────────────────────────────────────────────────
  List<Campeonato> campeonatosDe(String academiaId) =>
      campeonatos.where((c) => c.academiaId == academiaId).toList();

  /// Campeonatos que ORGANIZA el usuario logueado (los creó él), tengan o no
  /// academia. Es la fuente de "Mis campeonatos": sin esto, un campeonato creado
  /// desde Anfitrión (academiaId vacío) no aparecía en ninguna lista.
  List<Campeonato> get misCampeonatosOrganizados {
    final email = (usuario?.email ?? '').trim().toLowerCase();
    if (email.isEmpty) return const <Campeonato>[];
    return campeonatos
        .where((c) => c.dueno.trim().toLowerCase() == email)
        .toList()
      ..sort((a, b) => b.id.compareTo(a.id)); // recientes primero (id con ts)
  }

  Campeonato? campeonatoPorId(String id) {
    for (final c in campeonatos) {
      if (c.id == id) return c;
    }
    return null;
  }

  /// Extrae el ID de campeonato de lo que pegó el usuario: un enlace
  /// (`…/campeonato-web?id=ABC`) o el id/código pelado. Devuelve '' si no se
  /// reconoce nada usable.
  static String idCampeonatoDe(String entrada) {
    final t = entrada.trim();
    if (t.isEmpty) return '';
    // ¿Es un enlace con ?id=… ?
    final uri = Uri.tryParse(t);
    final qid = uri?.queryParameters['id'];
    if (qid != null && qid.trim().isNotEmpty) return qid.trim();
    // Si no es URL (o no trae id), tomamos el texto tal cual como id/código.
    if (!t.contains('://') && !t.contains(' ')) return t;
    return '';
  }

  /// Trae un campeonato por id desde Supabase y lo agrega a la caché local para
  /// poder abrir su ficha (aunque no sea de una academia del usuario). Devuelve
  /// el campeonato, o null si no existe / sin backend.
  Future<Campeonato?> traerCampeonato(String id) async {
    final existente = campeonatoPorId(id);
    if (existente != null) return existente;
    final c = await CampeonatosRepo.porId(id);
    if (c == null) return null;
    if (campeonatoPorId(c.id) == null) {
      campeonatos.add(c);
      notifyListeners();
    }
    return c;
  }

  /// Busca un campeonato desde lo que pegó el usuario en "Unirme a un
  /// campeonato": un ENLACE (?id=…), el ID largo (`camp_…`) o el CÓDIGO corto.
  /// Lo agrega a la caché local para abrir su ficha. null si no se encuentra.
  Future<Campeonato?> buscarCampeonato(String entrada) async {
    final t = entrada.trim();
    if (t.isEmpty) return null;
    // 1) ¿Enlace con ?id=… ? → por id.
    final qid = Uri.tryParse(t)?.queryParameters['id'];
    if (qid != null && qid.trim().isNotEmpty) return traerCampeonato(qid.trim());
    // 2) ¿Es el id largo? → por id.
    if (t.startsWith('camp_')) return traerCampeonato(t);
    // 3) Si no, es un CÓDIGO corto. Primero en caché local, luego en la nube.
    final cod = t.toUpperCase();
    for (final c in campeonatos) {
      if (c.codigoInvitacion.toUpperCase() == cod) return c;
    }
    final c = await CampeonatosRepo.porCodigo(cod);
    if (c == null) return null;
    if (campeonatoPorId(c.id) == null) {
      campeonatos.add(c);
      notifyListeners();
    }
    return c;
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
    DateTime? inscripcionHasta,
    DateTime? inicio,
    bool relampago = false,
    bool exigeDni = false,
    int? edadMin,
    int? edadMax,
    int minJugadoresEquipo = 0,
  }) {
    final c = Campeonato(
      id: 'camp_${DateTime.now().microsecondsSinceEpoch}',
      academiaId: academiaId,
      dueno: usuario?.email ?? '',
      codigo: _nuevoCodigoEquipo(), // código corto para invitar/unirse
      nombre: nombre,
      deporte: deporte,
      formato: formato,
      categoria: categoria,
      sede: sede,
      sedeUbicacion: sedeUbicacion,
      fechas: fechas,
      costoInscripcion: costoInscripcion,
      inscripcionHasta: inscripcionHasta,
      inicio: inicio,
      relampago: relampago,
      exigeDni: exigeDni,
      edadMin: edadMin,
      edadMax: edadMax,
      minJugadoresEquipo: minJugadoresEquipo,
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

  /// Sube un LOGO al campeonato [campId] (bytes de una imagen) y lo guarda.
  /// Devuelve true si subió y quedó guardado. Solo el organizador debería
  /// llamarlo (la UI ya lo restringe al dueño).
  Future<bool> ponerLogoCampeonato(String campId, List<int> bytes) async {
    final c = campeonatoPorId(campId);
    if (c == null) return false;
    final url = await CampeonatosRepo.subirLogo(campId, bytes);
    if (url == null) return false;
    guardarCampeonato(c.copyWith(logoUrl: url));
    return true;
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

  String _nuevoCodigoEquipo() {
    final base =
        DateTime.now().microsecondsSinceEpoch.toRadixString(36).toUpperCase();
    return base.substring(base.length - 6);
  }

  /// Crea un EQUIPO (fútbol) con el usuario como CAPITÁN y un CÓDIGO para que sus
  /// jugadores se auto-inscriban al plantel. Devuelve el código a compartir.
  ({bool ok, String mensaje, String codigo, String equipoId})
      crearEquipoCampeonato(String campId, String nombreEquipo) {
    final u = usuario;
    if (u == null) {
      return (ok: false, mensaje: 'Inicia sesión.', codigo: '', equipoId: '');
    }
    final c = campeonatoPorId(campId);
    if (c == null) {
      return (
        ok: false,
        mensaje: 'Campeonato no encontrado.',
        codigo: '',
        equipoId: ''
      );
    }
    if (c.cerrado ||
        !c.inscripcionAbierta ||
        c.fixtureGenerado ||
        c.inscripcionVencida) {
      return (
        ok: false,
        mensaje: 'Las inscripciones están cerradas.',
        codigo: '',
        equipoId: ''
      );
    }
    final nombre = nombreEquipo.trim();
    if (nombre.isEmpty) {
      return (
        ok: false,
        mensaje: 'Ponle nombre al equipo.',
        codigo: '',
        equipoId: ''
      );
    }
    final mio = c.participantes.where(
        (p) => p.capitanEmail.toLowerCase() == u.email.toLowerCase());
    if (mio.isNotEmpty) {
      return (
        ok: true,
        mensaje: 'Ya tienes un equipo aquí.',
        codigo: mio.first.codigo,
        equipoId: mio.first.id
      );
    }
    final codigo = _nuevoCodigoEquipo();
    final micro = DateTime.now().microsecondsSinceEpoch;
    final p = Participante(
      id: 'eq_$micro',
      nombre: nombre,
      email: u.email,
      fotoUrl: u.fotoUrl,
      capitanEmail: u.email,
      codigo: codigo,
      roster: [
        Integrante(id: 'in_$micro', nombre: u.nombre, email: u.email,
            fotoUrl: u.fotoUrl),
      ],
    );
    guardarCampeonato(c.copyWith(participantes: [...c.participantes, p]));
    return (
      ok: true,
      mensaje: 'Equipo "$nombre" creado.',
      codigo: codigo,
      equipoId: p.id
    );
  }

  /// Un jugador se UNE a un equipo por su CÓDIGO (queda en el roster, verificado
  /// por tener cuenta). Avisa al capitán.
  ({bool ok, String mensaje}) unirseAEquipoPorCodigo(String campId, String codigo,
      {String? nombre}) {
    final u = usuario;
    if (u == null) return (ok: false, mensaje: 'Inicia sesión.');
    final c = campeonatoPorId(campId);
    if (c == null) return (ok: false, mensaje: 'Campeonato no encontrado.');
    if (c.fixtureGenerado || c.inscripcionVencida) {
      return (ok: false, mensaje: 'Las inscripciones cerraron.');
    }
    final cod = codigo.trim().toUpperCase();
    final idx = c.participantes.indexWhere((p) => p.codigo.toUpperCase() == cod);
    if (idx < 0) {
      return (ok: false, mensaje: 'Código no válido. Pídeselo a tu capitán.');
    }
    final eq = c.participantes[idx];
    if (eq.roster
        .any((r) => r.email.toLowerCase() == u.email.toLowerCase())) {
      return (ok: true, mensaje: 'Ya estás en "${eq.nombre}".');
    }
    final integrante = Integrante(
      id: 'in_${DateTime.now().microsecondsSinceEpoch}',
      nombre: (nombre != null && nombre.trim().isNotEmpty)
          ? nombre.trim()
          : u.nombre,
      email: u.email,
      fotoUrl: u.fotoUrl,
    );
    final parts = [...c.participantes];
    parts[idx] = eq.copyWith(roster: [...eq.roster, integrante]);
    guardarCampeonato(c.copyWith(participantes: parts));
    if (eq.capitanEmail.isNotEmpty &&
        eq.capitanEmail.toLowerCase() != u.email.toLowerCase()) {
      AvisosService.enviar(
        email: eq.capitanEmail,
        titulo: 'Nuevo jugador en tu equipo ⚽',
        cuerpo: '${integrante.nombre} se unió a "${eq.nombre}".',
        tipo: 'campeonato',
        data: {'accion': 'roster', 'campeonato': c.id},
      );
    }
    return (ok: true, mensaje: 'Te uniste a "${eq.nombre}". 🎽');
  }

  /// El capitán agrega un integrante A MANO (sin cuenta / invitado).
  ({bool ok, String mensaje}) agregarIntegranteManual(
      String campId, String equipoId, String nombre) {
    final c = campeonatoPorId(campId);
    if (c == null) return (ok: false, mensaje: 'No encontrado.');
    final idx = c.participantes.indexWhere((p) => p.id == equipoId);
    if (idx < 0) return (ok: false, mensaje: 'Equipo no encontrado.');
    final n = nombre.trim();
    if (n.isEmpty) return (ok: false, mensaje: 'Escribe el nombre.');
    final eq = c.participantes[idx];
    final parts = [...c.participantes];
    parts[idx] = eq.copyWith(roster: [
      ...eq.roster,
      Integrante(id: 'in_${DateTime.now().microsecondsSinceEpoch}', nombre: n),
    ]);
    guardarCampeonato(c.copyWith(participantes: parts));
    return (ok: true, mensaje: 'Agregaste a "$n".');
  }

  /// (Re)genera el fixture del campeonato según su formato. Borra resultados.
  void generarFixture(String campId) {
    final c = campeonatoPorId(campId);
    if (c == null) return;
    final partidos = TorneoFixture.generar(c.formato, c.participantes);
    guardarCampeonato(c.copyWith(partidos: partidos));
  }

  /// AUTO-SORTEO: para cada campeonato cuyo plazo de inscripción venció y aún no
  /// tiene fixture (≥2 participantes), genera el fixture y NOTIFICA a los
  /// participantes con cuenta. Idempotente (una vez generado, ya no re-corre).
  /// Lazy: se llama al cargar campeonatos, sin cron.
  void autoSortearVencidos() {
    var cambio = false;
    for (final c in List<Campeonato>.from(campeonatos)) {
      if (c.cerrado || c.fixtureGenerado || !c.inscripcionVencida) continue;
      if (c.participantes.length < 2) continue;
      final partidos = TorneoFixture.generar(c.formato, c.participantes);
      if (partidos.isEmpty) continue;
      final nuevo = c.copyWith(partidos: partidos);
      final i = campeonatos.indexWhere((x) => x.id == c.id);
      if (i >= 0) campeonatos[i] = nuevo;
      CampeonatosRepo.guardar(nuevo);
      cambio = true;
      // Notifica a cada participante con cuenta (push, best-effort).
      for (final p in c.participantes) {
        if (p.email.trim().isEmpty) continue;
        AvisosService.enviar(
          email: p.email,
          titulo: '¡Fixture publicado! 🏆',
          cuerpo: 'Ya salió el fixture de "${c.nombre}". Revisa tus partidos.',
          tipo: 'campeonato',
          data: {'accion': 'fixture', 'campeonato': c.id},
        );
      }
    }
    if (cambio) {
      notifyListeners();
      _persistirDatos();
    }
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
    // Al refrescar campeonatos, cierra los que vencieron y sortea su fixture.
    autoSortearVencidos();
  }

  /// Trae las academias de la nube y las fusiona con las locales (por id). Así,
  /// al reinstalar el APK, las academias del profe reaparecen. Best-effort.
  /// Siembra la academia PILOTO (Jartur · El Bosque) si aún no está, con su
  /// tarifario cargado. Devuelve true si la agregó. Retro-compatible: si el
  /// profe la editó (mismo id), la versión guardada/remota gana luego.
  bool sembrarAcademias() {
    // DESACTIVADO: ya NO se auto-siembra la academia demo (Jartur · El Bosque).
    // Antes se inyectaba sola en dev y REAPARECÍA en cada instalación limpia
    // (al reinstalar el APK se borra SharedPreferences y con él el tombstone),
    // impidiendo un estado realmente "virgen" para pruebas. Si se editó de un
    // build viejo, `_curarSeedJartur` la sigue curando pero no la crea de cero.
    // (La data demo sigue disponible en SampleData.academiaJartur() por si se
    //  quiere reactivar con un botón explícito más adelante.)
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
        // Borrada (tombstone durable): no reaparece aunque la nube la devuelva
        // (p. ej. el borrado lógico falló por RLS sin política de UPDATE).
        if (_academiasEliminadas.contains(a.id)) continue;
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
    evaluaciones.removeWhere((e) => e.alumnoId == alumnoId);
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
    // AUTO-VINCULACIÓN: si el profe ya había registrado a este alumno a mano
    // (sin cuenta, email vacío), lo RECLAMAMOS —mismo id, así conserva su
    // asistencia y sus cuotas— en vez de crear un duplicado. Match por nombre o
    // por WhatsApp (el del apoderado si es menor).
    final telEntrante = esMenor ? (apoderadoWhatsapp?.trim() ?? '') : '';
    Alumno? reclamable;
    for (final al in alumnos) {
      if (al.academiaId != academia.id || al.email.isNotEmpty) continue;
      final nombreMatch =
          al.nombre.trim().toLowerCase() == nombre.toLowerCase();
      final telMatch = telEntrante.isNotEmpty &&
          (_telCoincide(telEntrante, al.whatsapp) ||
              _telCoincide(telEntrante, al.apoderadoWhatsapp));
      if (nombreMatch || telMatch) {
        reclamable = al;
        break;
      }
    }
    if (reclamable != null) {
      final r = reclamable;
      final vinculado = Alumno(
        id: r.id, // MISMO id → conserva asistencia y cuotas
        academiaId: r.academiaId,
        nombre: r.nombre.isNotEmpty ? r.nombre : nombre,
        whatsapp: r.whatsapp,
        email: u.email,
        fotoUrl: esMenor ? r.fotoUrl : (u.fotoUrl ?? r.fotoUrl),
        apoderadoNombre: esMenor ? u.nombre : r.apoderadoNombre,
        apoderadoWhatsapp: esMenor
            ? (telEntrante.isNotEmpty ? telEntrante : r.apoderadoWhatsapp)
            : r.apoderadoWhatsapp,
        edad: edad ?? r.edad,
        esSocioSede: r.esSocioSede,
        ordenHermano: r.ordenHermano,
        sedeId: r.sedeId,
      );
      final idx = alumnos.indexWhere((x) => x.id == r.id);
      if (idx >= 0) alumnos[idx] = vinculado;
      _marcarInvitacionesAceptadas(academia.id, u.email);
      notifyListeners();
      _persistirDatos();
      MatriculasRepo.guardar(vinculado);
      return (
        ok: true,
        mensaje: 'Te vinculamos a tu registro en ${academia.nombre}. 🎾'
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
    _marcarInvitacionesAceptadas(academia.id, u.email);
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

  /// Marca aceptadas las invitaciones por correo pendientes de [email] en una
  /// academia (al unirse por código/aceptar), para que el profe las vea resueltas.
  void _marcarInvitacionesAceptadas(String academiaId, String email) {
    for (var k = 0; k < invitaciones.length; k++) {
      final inv = invitaciones[k];
      if (inv.academiaId == academiaId &&
          inv.estado == EstadoInvitacion.pendiente &&
          inv.coincideEmail(email)) {
        invitaciones[k] = inv.copyWith(estado: EstadoInvitacion.aceptada);
        InvitacionesRepo.guardar(invitaciones[k]);
      }
    }
  }

  /// ¿Dos teléfonos son el mismo número? Compara los últimos 8 dígitos (ignora
  /// prefijo de país/espacios). Para vincular al alumno por su WhatsApp.
  static bool _telCoincide(String a, String b) {
    final x = a.replaceAll(RegExp(r'\D'), '');
    final y = b.replaceAll(RegExp(r'\D'), '');
    if (x.length < 8 || y.length < 8) return false;
    return x.substring(x.length - 8) == y.substring(y.length - 8);
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

  /// Hilo del chat abierto AHORA en pantalla (no se persiste). Sirve para NO
  /// mostrar el aviso de push cuando el mensaje llega al chat que ya estás viendo
  /// (como WhatsApp: si estás dentro, el mensaje aparece solo, sin banner).
  String hiloChatAbierto = '';

  /// Marca un hilo como leído hasta ahora (limpia el contador de no leídos).
  void marcarChatLeido(String hilo) {
    chatLecturas[hilo] = DateTime.now().toIso8601String();
    notifyListeners();
    _persistirDatos();
    // Checks tipo WhatsApp. Si tengo activada la confirmación de lectura, aviso
    // al remitente que YO leí (2 azules). Si la apagué (privacidad), solo marco
    // ENTREGADO (2 grises) — nunca "leído".
    if (confirmacionLectura) {
      LecturasRepo.marcarLeido(hilo, _yo);
    } else {
      LecturasRepo.marcarEntregados([hilo], _yo);
    }
  }

  /// Marca ENTREGADOS (no leídos) varios hilos para MÍ: se llama cuando bajo los
  /// mensajes (abro Mensajes) para que el remitente vea 2 checks grises aunque
  /// no haya abierto el chat.
  Future<void> marcarEntregados(Iterable<String> hilos) async {
    await LecturasRepo.marcarEntregados(hilos.toList(), _yo);
  }

  /// Cuándo se leyó por última vez un hilo (null si nunca).
  DateTime? chatUltimaLectura(String hilo) {
    final iso = chatLecturas[hilo];
    return iso == null ? null : DateTime.tryParse(iso);
  }

  /// "Eliminar conversación" (estilo WhatsApp): la saca de MI bandeja. No borra
  /// nada en el servidor ni para la otra persona; solo marca el hilo como oculto
  /// desde ahora.
  void ocultarChat(String hilo) {
    chatsOcultos[hilo] = DateTime.now().toIso8601String();
    notifyListeners();
    _persistirDatos();
  }

  /// ¿El hilo debe ocultarse de la bandeja? Se oculta si el usuario lo eliminó y
  /// no ha llegado ningún mensaje más nuevo que ese momento (si llega uno nuevo,
  /// reaparece —como WhatsApp). [ultimoMensaje] = fecha del último mensaje del hilo.
  bool chatOculto(String hilo, DateTime ultimoMensaje) {
    final iso = chatsOcultos[hilo];
    if (iso == null) return false;
    final ocultadoEn = DateTime.tryParse(iso);
    if (ocultadoEn == null) return false;
    // Si hay un mensaje posterior al ocultado → reaparece (deja de estar oculto).
    if (ultimoMensaje.isAfter(ocultadoEn)) {
      chatsOcultos.remove(hilo);
      return false;
    }
    return true;
  }

  // ── Acciones de bandeja (fijar / archivar / silenciar), estilo WhatsApp ──────
  bool chatFijado(String hilo) => chatsFijados.contains(hilo);
  bool chatArchivado(String hilo) => chatsArchivados.contains(hilo);
  bool chatSilenciado(String hilo) => chatsSilenciados.contains(hilo);

  /// Fija/desfija un hilo (pin). Los fijados van primero en la bandeja.
  void toggleChatFijado(String hilo) {
    if (!chatsFijados.remove(hilo)) chatsFijados.add(hilo);
    notifyListeners();
    _persistirDatos();
  }

  /// Archiva/desarchiva un hilo. Al archivar, también se desfija (como WhatsApp).
  void toggleChatArchivado(String hilo) {
    if (!chatsArchivados.remove(hilo)) {
      chatsArchivados.add(hilo);
      chatsFijados.remove(hilo);
    }
    notifyListeners();
    _persistirDatos();
  }

  /// Silencia/activa los avisos de un hilo (la campanita).
  void toggleChatSilenciado(String hilo) {
    if (!chatsSilenciados.remove(hilo)) chatsSilenciados.add(hilo);
    notifyListeners();
    _persistirDatos();
  }

  List<Cuota> cuotasDe(String academiaId) => cuotas
      .where((c) => c.academiaId == academiaId)
      .toList()
    ..sort((a, b) => a.vencimiento.compareTo(b.vencimiento));

  List<Cuota> cuotasDeAlumno(String alumnoId) => cuotas
      .where((c) => c.alumnoId == alumnoId)
      .toList()
    ..sort((a, b) => a.vencimiento.compareTo(b.vencimiento));

  // ── TABLERO DE COBROS (academia) ──────────────────────────────────────────
  // Memoria de "a quién ya le recordé" (alumnoId → ISO de la última vez). Evita
  // repetir el aviso y permite mostrar "recordado hace X". Se persiste.
  final Map<String, String> _recordatoriosCobro = {};
  // ¿Mostrar los avisos proactivos de "por recordar"? (config del profe).
  bool recordatoriosAutoActivos = true;

  /// Deuda de un alumno (suma de cuotas impagas) y si alguna está vencida.
  ({double deuda, bool vencido}) deudaDeAlumno(String alumnoId) {
    final hoy = DateTime.now();
    double deuda = 0;
    var vencido = false;
    for (final c in cuotas) {
      if (c.alumnoId != alumnoId || c.pagada) continue;
      deuda += c.monto;
      if (c.vencidaAl(hoy)) vencido = true;
    }
    return (deuda: deuda, vencido: vencido);
  }

  /// Total por cobrar de la academia (todas las cuotas impagas).
  double porCobrarDe(String academiaId) {
    double t = 0;
    for (final c in cuotasDe(academiaId)) {
      if (!c.pagada) t += c.monto;
    }
    return t;
  }

  /// Total VENCIDO de la academia (impagas ya pasadas de fecha).
  double vencidoDe(String academiaId) {
    final hoy = DateTime.now();
    double t = 0;
    for (final c in cuotasDe(academiaId)) {
      if (!c.pagada && c.vencidaAl(hoy)) t += c.monto;
    }
    return t;
  }

  /// Cobrado en el MES actual (cuotas pagadas con fecha de pago en el mes).
  double cobradoMesDe(String academiaId) {
    final hoy = DateTime.now();
    double t = 0;
    for (final c in cuotasDe(academiaId)) {
      final f = c.fechaPago;
      if (c.pagada && f != null && f.year == hoy.year && f.month == hoy.month) {
        t += c.monto;
      }
    }
    return t;
  }

  /// Alumnos de la academia que DEBEN, ordenados por deuda (mayor primero);
  /// dentro de igual deuda, primero los vencidos.
  List<Alumno> morososDe(String academiaId) {
    final lista = alumnosDe(academiaId)
        .where((a) => deudaDeAlumno(a.id).deuda > 0)
        .toList();
    lista.sort((a, b) {
      final da = deudaDeAlumno(a.id), db = deudaDeAlumno(b.id);
      if (da.vencido != db.vencido) return da.vencido ? -1 : 1;
      return db.deuda.compareTo(da.deuda);
    });
    return lista;
  }

  /// Marca que se le RECORDÓ el pago a un alumno (ahora).
  void marcarRecordado(String alumnoId) {
    _recordatoriosCobro[alumnoId] = DateTime.now().toIso8601String();
    notifyListeners();
    _persistirDatos();
  }

  /// Última vez que se le recordó a un alumno (null si nunca).
  DateTime? ultimoRecordatorioDe(String alumnoId) {
    final iso = _recordatoriosCobro[alumnoId];
    return iso == null ? null : DateTime.tryParse(iso);
  }

  /// Días desde el último recordatorio (null si nunca se le recordó).
  int? diasDesdeRecordatorio(String alumnoId) {
    final u = ultimoRecordatorioDe(alumnoId);
    if (u == null) return null;
    return DateTime.now().difference(u).inDays;
  }

  /// Morosos que TOCA recordar: deudores a los que no se les recordó en los
  /// últimos [cadaDias] días (o nunca). Es la lista "automática" del tablero.
  List<Alumno> porRecordarDe(String academiaId, {int cadaDias = 7}) {
    return morososDe(academiaId).where((a) {
      final d = diasDesdeRecordatorio(a.id);
      return d == null || d >= cadaDias;
    }).toList();
  }

  /// Activa/desactiva los avisos proactivos de cobranza.
  void setRecordatoriosAuto(bool v) {
    recordatoriosAutoActivos = v;
    notifyListeners();
    _persistirDatos();
  }

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

  /// Marca a VARIOS alumnos de una vez el mismo día (upsert), notificando una
  /// sola vez. Para el botón "Todos presentes" de la asistencia rápida.
  void marcarAsistenciaTodos(
      String academiaId, List<String> alumnoIds, String dia, bool presente) {
    for (final alumnoId in alumnoIds) {
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
    }
    notifyListeners();
    _persistirDatos();
  }

  // Memoria de "a qué alumno ya le avisé la asistencia" (clave "alumnoId|dia"),
  // para no reenviar y mostrar el estado. Se persiste.
  final Set<String> _asistenciaAvisada = {};

  bool asistenciaAvisada(String alumnoId, String dia) =>
      _asistenciaAvisada.contains('$alumnoId|$dia');

  void marcarAsistenciaAvisada(String alumnoId, String dia) {
    _asistenciaAvisada.add('$alumnoId|$dia');
    notifyListeners();
    _persistirDatos();
  }

  // ── Planes de trabajo del profe + evaluación de alumnos ────────────────────

  /// Planes de trabajo GUARDADOS de una academia (los que el profe creó/editó).
  List<PlanTrabajo> planesDe(String academiaId) =>
      planes.where((p) => p.academiaId == academiaId).toList();

  /// Plantilla Pichangol para el deporte de la academia (tenis, pádel, fútbol,
  /// natación, vóley, básquet). Es una PLANTILLA (no persistida): se ofrece como
  /// base para "usar/duplicar".
  PlanTrabajo? plantillaDe(Academia ac) =>
      plantillaPara(ac.deporte.name, ac.id);

  /// Clona un plan (plantilla o propio) como un plan NUEVO editable de la
  /// academia y lo guarda. Devuelve el id del nuevo plan.
  String clonarPlan(PlanTrabajo base, {String? nombre}) {
    final nuevo = base.copyWith(
      id: 'plan_${DateTime.now().microsecondsSinceEpoch}',
      nombre: nombre ?? base.nombre,
      esPlantilla: false,
    );
    planes.add(nuevo);
    notifyListeners();
    _persistirDatos();
    return nuevo.id;
  }

  /// Crea un plan VACÍO (desde cero) para una academia. Devuelve su id.
  String crearPlanVacio(String academiaId, String deporte,
      {String nombre = 'Nuevo plan', String nivel = ''}) {
    final nuevo = PlanTrabajo(
      id: 'plan_${DateTime.now().microsecondsSinceEpoch}',
      academiaId: academiaId,
      deporte: deporte,
      nombre: nombre,
      nivel: nivel,
    );
    planes.add(nuevo);
    notifyListeners();
    _persistirDatos();
    return nuevo.id;
  }

  PlanTrabajo? planPorId(String id) {
    for (final p in planes) {
      if (p.id == id) return p;
    }
    return null;
  }

  /// Guarda (upsert) un plan editado.
  void guardarPlan(PlanTrabajo plan) {
    final i = planes.indexWhere((p) => p.id == plan.id);
    if (i >= 0) {
      planes[i] = plan;
    } else {
      planes.add(plan);
    }
    notifyListeners();
    _persistirDatos();
  }

  void eliminarPlan(String planId) {
    planes.removeWhere((p) => p.id == planId);
    evaluaciones.removeWhere((e) => e.planId == planId);
    notifyListeners();
    _persistirDatos();
  }

  /// Nivel evaluado de una habilidad de un alumno en un plan (null = sin evaluar).
  NivelLogro? nivelDe(String alumnoId, String planId, String habilidad) {
    for (final e in evaluaciones) {
      if (e.alumnoId == alumnoId &&
          e.planId == planId &&
          e.habilidad == habilidad) {
        return e.nivel;
      }
    }
    return null;
  }

  /// Evalúa (upsert) una habilidad de un alumno en un plan.
  void evaluar(
      String alumnoId, String planId, String habilidad, NivelLogro nivel) {
    final reg = EvaluacionAlumno(
      alumnoId: alumnoId,
      planId: planId,
      habilidad: habilidad,
      nivel: nivel,
      cuando: DateTime.now(),
    );
    final i = evaluaciones.indexWhere((e) =>
        e.alumnoId == alumnoId &&
        e.planId == planId &&
        e.habilidad == habilidad);
    if (i >= 0) {
      evaluaciones[i] = reg;
    } else {
      evaluaciones.add(reg);
    }
    notifyListeners();
    _persistirDatos();
  }

  /// Resumen de progreso de un alumno en un plan: cuántas habilidades hay en cada
  /// nivel y el % de avance (promedio de niveles / máximo). Sirve para el carnet.
  ({int total, int logrado, int enProceso, int inicial, int sinEvaluar, double pct})
      progresoAlumno(String alumnoId, PlanTrabajo plan) {
    var logrado = 0, enProceso = 0, inicial = 0, sinEvaluar = 0, suma = 0;
    for (final h in plan.habilidades) {
      final n = nivelDe(alumnoId, plan.id, h);
      if (n == null) {
        sinEvaluar++;
        continue;
      }
      suma += n.valor;
      switch (n) {
        case NivelLogro.logrado:
          logrado++;
        case NivelLogro.enProceso:
          enProceso++;
        case NivelLogro.inicial:
          inicial++;
      }
    }
    final total = plan.habilidades.length;
    // % sobre el máximo posible (todas en "Logrado" = valor 2).
    final pct = total == 0 ? 0.0 : (suma / (total * 2)) * 100;
    return (
      total: total,
      logrado: logrado,
      enProceso: enProceso,
      inicial: inicial,
      sinEvaluar: sinEvaluar,
      pct: pct,
    );
  }

  // ── Bitácora de clase (evaluación DIARIA por alumno) ───────────────────────

  /// Notas de clase de un alumno, más recientes primero.
  List<NotaClase> notasDe(String alumnoId) {
    final l = notasClase.where((n) => n.alumnoId == alumnoId).toList();
    l.sort((a, b) => b.creado.compareTo(a.creado));
    return l;
  }

  /// Cuántas clases del [planId] ya tienen bitácora para el alumno (progreso del
  /// programa: "clases dictadas" al alumno).
  int clasesConNota(String alumnoId, String planId) => notasClase
      .where((n) =>
          n.alumnoId == alumnoId && n.planId == planId && n.sesionNumero > 0)
      .map((n) => n.sesionNumero)
      .toSet()
      .length;

  /// Agrega una nota de clase (evaluación del día). Devuelve su id.
  String agregarNotaClase({
    required String academiaId,
    required String alumnoId,
    required String planId,
    required int sesionNumero,
    required DesempenoClase desempeno,
    required String nota,
    DateTime? fecha,
  }) {
    final f = fecha ?? DateTime.now();
    final ymd = '${f.year.toString().padLeft(4, '0')}-'
        '${f.month.toString().padLeft(2, '0')}-'
        '${f.day.toString().padLeft(2, '0')}';
    final reg = NotaClase(
      id: 'nota_${DateTime.now().microsecondsSinceEpoch}',
      academiaId: academiaId,
      alumnoId: alumnoId,
      planId: planId,
      sesionNumero: sesionNumero,
      fecha: ymd,
      desempeno: desempeno,
      nota: nota.trim(),
      creado: DateTime.now(),
    );
    notasClase.add(reg);
    notifyListeners();
    _persistirDatos();
    return reg.id;
  }

  void eliminarNotaClase(String id) {
    notasClase.removeWhere((n) => n.id == id);
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

  // ── Privacidad (estilo WhatsApp, con reciprocidad) ─────────────────────────

  /// Si es false: NO reporto mi "en línea / última vez" y —por reciprocidad—
  /// tampoco veo la de los demás.
  bool mostrarUltimaVez = true;

  /// Si es false: NO envío confirmaciones de lectura (2 checks azules) y —por
  /// reciprocidad— tampoco las veo. La ENTREGA (2 grises) se mantiene siempre.
  bool confirmacionLectura = true;

  void setMostrarUltimaVez(bool v) {
    if (v == mostrarUltimaVez) return;
    mostrarUltimaVez = v;
    notifyListeners();
    _persistirDatos();
    if (!v) {
      // Al apagarlo, borra mi última vez del servidor (nadie la ve ya).
      final e = usuario?.email ?? '';
      if (e.isNotEmpty) PresenciaRepo.ocultar(e);
    } else {
      // Al prenderlo, vuelvo a latir de una.
      final e = usuario?.email ?? '';
      if (e.isNotEmpty) PresenciaRepo.latir(e);
    }
  }

  void setConfirmacionLectura(bool v) {
    if (v == confirmacionLectura) return;
    confirmacionLectura = v;
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

  /// Descubre canchas REALES cerca de [centro]. Estrategia de COSTO CERO:
  ///  1. Lee primero la COSECHA en Supabase (`pichangol_canchas_cache`):
  ///     instantáneo, gratis y offline-friendly.
  ///  2. Solo si la zona NO está cosechada (pocos resultados) consulta Google
  ///     Places, y lo que trae lo COSECHA para que el siguiente usuario ya no
  ///     gaste cuota. La primera visita a una zona paga; el resto, S/0.
  ///  Sin fase de fotos de Google (caducan + licencia + cuota): la lista usa
  ///  placeholder por deporte; la foto real llega cuando el dueño reclama.
  ///
  ///  [forzarGoogle]: re-consulta Google AUNQUE la zona ya esté cosechada y
  ///  re-cosecha lo nuevo. Se usa en las búsquedas EXPLÍCITAS del usuario
  ///  (búsqueda guiada, "Buscar canchas en esta zona"): así los locales que
  ///  Google agregó después de la primera cosecha sí aparecen (frescura),
  ///  pagando solo cuando alguien lo pide de verdad.
  Future<void> descubrirCanchasCerca(LatLng centro,
      {bool forzarGoogle = false}) async {
    descubriendo = true;
    notifyListeners(); // muestra el indicador "Buscando canchas cerca de ti…"
    // 1) Cosecha primero (Supabase): pinta al toque sin gastar cuota.
    var cosechadas = 0;
    try {
      final cache = await CanchasCacheRepo.cerca(centro, radioBusquedaKm);
      cosechadas = cache.length;
      _agregarDescubiertas(cache);
      if (cosechadas > 0) notifyListeners();
    } catch (_) {}
    // 2) Zona ya cosechada (≥8 lugares) → NO gastar Google (salvo búsqueda
    //    explícita). Zona nueva/rala → descubrir en Google y cosechar.
    if (!forzarGoogle && cosechadas >= 8) {
      descubriendo = false;
      notifyListeners();
      return;
    }
    try {
      final rapidas = await PlacesService.canchasCerca(centro,
          conFotos: false, radioMetros: radioBusquedaKm * 1000);
      _agregarDescubiertas(rapidas);
      CanchasCacheRepo.guardar(rapidas); // cosecha (best-effort, sin await UI)
    } catch (_) {
      // fail-safe: si Places no responde, quedan las cosechadas/registradas
    } finally {
      descubriendo = false;
      notifyListeners();
    }
  }

  void _agregarDescubiertas(List<Cancha> reales) {
    final existentes = canchasDescubiertas.map((c) => c.id).toSet();
    final nuevas = reales.where((c) => !existentes.contains(c.id)).toList();
    if (nuevas.isNotEmpty) canchasDescubiertas.addAll(nuevas);
  }

  /// Trae las reservas compartidas desde Supabase (disponibilidad entre
  /// dispositivos) y recalcula "Mis reservas" según el correo del jugador.
  Future<void> cargarReservasRemotas() async {
    // Hay conexión (vamos a leer de Supabase): primero intenta SUBIR las
    // reservas que quedaron pendientes por haberse hecho sin señal, y registrar
    // la contabilidad (comisión/liquidación) que no se pudo enviar antes.
    await sincronizarReservasPendientes();
    await flushContabilidad();
    final remotas = await ReservasRepo.fetchRemotas();
    for (final r in remotas) {
      if (!reservas.any((x) => x.id == r.id)) reservas.insert(0, r);
    }
    if (remotas.isNotEmpty) {
      _recomputarMisReservas();
      notifyListeners();
    }
    // Programa (en ESTE dispositivo, el del dueño) los recordatorios de cobro en
    // efectivo de sus canchas. Aquí es donde el dueño "se entera" de la reserva.
    _programarRecordatoriosEfectivo();
  }

  /// Fecha+hora real de una reserva (para agendar avisos). Null si no se puede.
  DateTime? _fechaHoraReserva(Reserva r) {
    if (r.fecha.isEmpty) return null;
    final d = DateTime.tryParse(r.fecha);
    if (d == null) return null;
    final partes = r.horaInicio.split(':');
    final h = int.tryParse(partes.isNotEmpty ? partes[0] : '') ?? 0;
    final m = int.tryParse(partes.length > 1 ? partes[1] : '') ?? 0;
    return DateTime(d.year, d.month, d.day, h, m);
  }

  /// Agenda recordatorios LOCALES de "cobra en efectivo" para las reservas EN
  /// EFECTIVO de MIS canchas, aún no pagadas y en el futuro. Idempotente (mismo
  /// id de notificación por reserva → no duplica). Best-effort.
  void _programarRecordatoriosEfectivo() {
    for (final r in reservas) {
      if (r.medioPago != 'efectivo' || r.pagado) continue;
      if (r.estado == EstadoReserva.noShow) continue;
      final cancha = miCanchaDeReserva(r.canchaId);
      if (cancha == null) continue; // no es mi cancha → no me toca cobrar
      final cuando = _fechaHoraReserva(r);
      if (cuando == null || !cuando.isAfter(DateTime.now())) continue;
      final sim = r.monedaSimbolo;
      RecordatorioService.programarCobroEfectivo(
        reservaId: r.id,
        titulo: 'Cobra en efectivo 💵',
        cuerpo: '${cancha.nombre} · ${r.jugador} · $sim${r.precio} · '
            '${r.horaInicio}',
        cuando: cuando,
      );
    }
  }

  // ── Horarios BLOQUEADOS por el dueño ──────────────────────────────────────
  // Claves "canchaId|fecha|hora" de slots que el dueño cerró (no reservables).
  final Set<String> _bloqueos = {};

  bool estaBloqueado(String canchaId, String fecha, String hora) =>
      _bloqueos.contains(BloqueosRepo.clave(canchaId, fecha, hora));

  // ── LLENAR LA CANCHA VACÍA (dueño) ────────────────────────────────────────
  /// Horas LIBRES de una cancha en una fecha (ISO): están en su grilla, no
  /// reservadas y no bloqueadas. Si la fecha es HOY, omite las horas ya pasadas.
  List<String> horasLibresDe(Cancha c, String fechaIso) {
    final hoy = DateTime.now();
    final esHoy = fechaIso ==
        '${hoy.year.toString().padLeft(4, '0')}-'
            '${hoy.month.toString().padLeft(2, '0')}-'
            '${hoy.day.toString().padLeft(2, '0')}';
    final desde = esHoy ? hoy.hour * 60 + hoy.minute : null;
    final slots = c.horariosSlots(desdeMinutos: desde);
    return slots.where((h) {
      final reservado = reservas.any((r) =>
          r.canchaId == c.id && r.fecha == fechaIso && r.horaInicio == h);
      return !reservado && !estaBloqueado(c.id, fechaIso, h);
    }).toList();
  }

  /// Clientes del dueño (agregados de las reservas de SUS canchas) a los que se
  /// les puede avisar: con correo (tienen la app → chat/push) o con teléfono
  /// (WhatsApp). Deduplicados. Para difundir horas libres/promos.
  List<({String nombre, String email, String telefono})> clientesParaAvisar() {
    final out = <String, ({String nombre, String email, String telefono})>{};
    for (final r in reservas) {
      if (miCanchaDeReserva(r.canchaId) == null) continue;
      final email = r.usuario.trim().toLowerCase();
      final tel = r.telefono.trim();
      if (email.isEmpty && tel.isEmpty) continue; // sin forma de contactar
      final key = email.isNotEmpty ? email : 't:$tel';
      out.putIfAbsent(
          key,
          () => (
                nombre: r.jugador.trim().isEmpty ? 'Cliente' : r.jugador.trim(),
                email: email,
                telefono: tel
              ));
    }
    return out.values.toList();
  }

  /// Carga los bloqueos desde la nube (al abrir una ficha de cancha).
  Future<void> cargarBloqueos() async {
    final s = await BloqueosRepo.fetch();
    _bloqueos
      ..clear()
      ..addAll(s);
    notifyListeners();
  }

  // ── DESCUENTO POR SLOT (hora feliz de una hora puntual) ───────────────────
  // Mapa "canchaId|fecha|hora" → % (1..90). El dueño lo aplica para llenar la
  // cancha; el precio rebajado es el que se COBRA al reservar ese slot.
  final Map<String, int> _descuentosSlot = {};

  /// % de descuento del slot (0 si no tiene).
  int descuentoSlotPct(String canchaId, String fecha, String hora) =>
      _descuentosSlot[DescuentosRepo.clave(canchaId, fecha, hora)] ?? 0;

  /// Precio POR HORA efectivo de un slot en una fecha: si tiene descuento
  /// puntual, ese manda; si no, el de la cancha (que ya aplica la hora feliz de
  /// las mañanas). Fuente única para cobrar/mostrar el precio real de un slot.
  double precioHoraEfectivo(Cancha c, String fecha, String hora) {
    final pct = descuentoSlotPct(c.id, fecha, hora);
    if (pct > 0) return c.precioHora * (100 - pct.clamp(0, 90)) / 100;
    return c.precioEn(hora);
  }

  /// Precio del SLOT (lo que paga el cliente por el bloque) en una fecha, con el
  /// descuento efectivo aplicado.
  int precioSlotEfectivo(Cancha c, String fecha, String hora) =>
      (precioHoraEfectivo(c, fecha, hora) * c.duracionSlotMin / 60).round();

  /// El dueño aplica (pct>0) o quita (pct<=0) el descuento de un slot. Persiste
  /// local + nube para que valga en todos los dispositivos.
  Future<void> aplicarDescuentoSlot(
      String canchaId, String fecha, String hora, int pct) async {
    final k = DescuentosRepo.clave(canchaId, fecha, hora);
    if (pct <= 0) {
      _descuentosSlot.remove(k);
      notifyListeners();
      _persistirDatos();
      await DescuentosRepo.quitar(canchaId, fecha, hora);
    } else {
      final p = pct.clamp(1, 90);
      _descuentosSlot[k] = p;
      notifyListeners();
      _persistirDatos();
      await DescuentosRepo.aplicar(canchaId, fecha, hora, p);
    }
  }

  /// Carga los descuentos de slot desde la nube (best-effort).
  Future<void> cargarDescuentosSlot() async {
    final m = await DescuentosRepo.fetch();
    _descuentosSlot
      ..clear()
      ..addAll(m);
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

  /// Carga en LOTE solo las reseñas de canchas aún NO cacheadas (para pintar el
  /// rating real en las tarjetas de Explorar sin re-consultar en cada rebuild).
  /// Pre-marca las pedidas como cargadas (vacío) para evitar consultas duplicadas.
  Future<void> cargarResenasFaltantes(List<String> canchaIds) async {
    final faltan = canchaIds
        .where((id) => id.isNotEmpty && !_resenas.containsKey(id))
        .toList();
    if (faltan.isEmpty) return;
    for (final id in faltan) {
      _resenas.putIfAbsent(id, () => const <Resena>[]);
    }
    final rows = await ResenasRepo.deCanchas(faltan);
    for (final id in faltan) {
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

  // ── LISTA DE ESPERA de horarios (waitlist) ────────────────────────────────
  // Cache por cancha_id (se llena al abrir una ficha o el panel del dueño).
  final Map<String, List<EnEspera>> _espera = {};

  /// Carga la lista de espera de un conjunto de canchas (una consulta).
  Future<void> cargarEspera(List<String> canchaIds) async {
    if (canchaIds.isEmpty) return;
    final rows = await EsperaRepo.deCanchas(canchaIds);
    for (final id in canchaIds) {
      _espera[id] = rows.where((e) => e.canchaId == id).toList();
    }
    notifyListeners();
  }

  /// Quiénes esperan un slot concreto (orden de llegada = orden de cola).
  List<EnEspera> esperaSlot(String canchaId, String fecha, String hora) {
    final l = _espera[canchaId];
    if (l == null) return const <EnEspera>[];
    return l.where((e) => e.fecha == fecha && e.hora == hora).toList();
  }

  /// Total en espera de un slot.
  int nEnEspera(String canchaId, String fecha, String hora) =>
      esperaSlot(canchaId, fecha, hora).length;

  /// ¿El jugador logueado ya está en la lista de espera de este slot?
  bool estoyEnEspera(String canchaId, String fecha, String hora) {
    final email = usuario?.email.trim().toLowerCase();
    if (email == null || email.isEmpty) return false;
    return esperaSlot(canchaId, fecha, hora)
        .any((e) => e.usuario.trim().toLowerCase() == email);
  }

  /// El jugador se anota a la lista de espera de un slot tomado. Optimista.
  Future<bool> unirmeAEspera(String canchaId, String fecha, String hora) async {
    final u = usuario;
    if (u == null || u.email.isEmpty) return false;
    final email = u.email.trim().toLowerCase();
    final e = EnEspera(
      id: EnEspera.claveId(email, canchaId, fecha, hora),
      canchaId: canchaId,
      fecha: fecha,
      hora: hora,
      usuario: email,
      nombre: u.nombre,
      telefono: miCelular,
      creado: DateTime.now(),
    );
    final lista = [..._espera[canchaId] ?? const <EnEspera>[]]
      ..removeWhere((x) =>
          x.fecha == fecha && x.hora == hora && x.usuario == email)
      ..add(e);
    _espera[canchaId] = lista;
    notifyListeners();
    return EsperaRepo.unirse(e);
  }

  /// El jugador se baja de la lista de espera de un slot. Optimista.
  Future<bool> salirDeEspera(String canchaId, String fecha, String hora) async {
    final email = usuario?.email.trim().toLowerCase();
    if (email == null || email.isEmpty) return false;
    final id = EnEspera.claveId(email, canchaId, fecha, hora);
    _espera[canchaId] = [..._espera[canchaId] ?? const <EnEspera>[]]
      ..removeWhere((x) => x.id == id);
    notifyListeners();
    return EsperaRepo.salir(id);
  }

  // ── BONOS de horas prepagadas (packs por local) ───────────────────────────
  final Map<String, List<BonoOferta>> _bonosClub = {}; // club → ofertas activas
  List<BonoComprado> _misBonos = []; // créditos del jugador logueado

  /// Ofertas de bonos activas de un local (caché).
  List<BonoOferta> bonosDeClub(String club) =>
      _bonosClub[club] ?? const <BonoOferta>[];

  /// Carga las ofertas de bonos de un local.
  Future<void> cargarBonosClub(String club) async {
    if (club.isEmpty) return;
    _bonosClub[club] = await BonosRepo.ofertasDeClub(club);
    notifyListeners();
  }

  /// Ofertas del dueño (todas), para administrarlas.
  Future<List<BonoOferta>> cargarBonosDueno() async {
    final email = usuario?.email ?? '';
    if (email.isEmpty) return const <BonoOferta>[];
    return BonosRepo.ofertasDeDueno(email);
  }

  /// Bonos VENDIDOS en los locales del dueño (quién compró, horas, saldo), para
  /// que vea la plata que entró y el consumo.
  Future<List<BonoComprado>> cargarBonosVendidos() async {
    final email = usuario?.email ?? '';
    if (email.isEmpty) return const <BonoComprado>[];
    return BonosRepo.comprasDeDueno(email);
  }

  Future<bool> guardarBonoOferta(BonoOferta b) async {
    final ok = await BonosRepo.guardarOferta(b);
    if (ok) {
      _bonosClub[b.club] = await BonosRepo.ofertasDeClub(b.club);
      notifyListeners();
    }
    return ok;
  }

  Future<void> eliminarBonoOferta(BonoOferta b) async {
    await BonosRepo.eliminarOferta(b.id);
    _bonosClub[b.club] = await BonosRepo.ofertasDeClub(b.club);
    notifyListeners();
  }

  /// Carga los créditos de bono del jugador logueado.
  Future<void> cargarMisBonos() async {
    final email = usuario?.email ?? '';
    if (email.isEmpty) {
      _misBonos = [];
      return;
    }
    _misBonos = await BonosRepo.comprasDe(email);
    notifyListeners();
  }

  /// Créditos de bono del jugador logueado (todos los locales), para "Mis bonos".
  List<BonoComprado> get misBonos => List.unmodifiable(_misBonos);

  /// Símbolo de moneda de un local (por su nombre): toma el de cualquier cancha
  /// de ese club; si no hay, cae al símbolo del país actual. Para mostrar bonos
  /// del jugador con la moneda correcta del local.
  String monedaDeClub(String club) {
    for (final c in [...canchasExtra, ...canchasRemotas, ...canchasDescubiertas]) {
      if (c.club == club) return c.monedaSimbolo;
    }
    return monedaSimbolo;
  }

  /// Saldo de horas de bono del jugador en un local (suma de créditos con saldo).
  int miSaldoBono(String club) {
    var s = 0;
    for (final c in _misBonos) {
      if (c.club == club) s += c.saldo;
    }
    return s;
  }

  /// El jugador compra un bono (ya pagó con Culqi; [ventaId] = idempotencia).
  /// Crea el crédito local + Supabase. Optimista. El registro contable (por
  /// recibir del dueño + comisión) lo hace la pantalla vía PagosService.venta.
  Future<bool> comprarBono(BonoOferta o, String ventaId) async {
    final u = usuario;
    if (u == null || u.email.isEmpty) return false;
    final c = BonoComprado(
      id: ventaId.isNotEmpty
          ? 'bono_$ventaId'
          : 'bono_${o.id}_${u.email.hashCode.toUnsigned(20).toRadixString(16)}'
              '_${DateTime.now().millisecondsSinceEpoch}',
      bonoId: o.id,
      dueno: o.dueno,
      club: o.club,
      comprador: u.email.trim().toLowerCase(),
      compradorNombre: u.nombre,
      horasTotal: o.horas,
      horasUsadas: 0,
      precio: o.precio,
      ventaId: ventaId,
      creado: DateTime.now(),
    );
    _misBonos = [c, ..._misBonos];
    notifyListeners();
    return BonosRepo.registrarCompra(c);
  }

  /// Canjea [horas] del saldo de bono del jugador en un local (FIFO: gasta
  /// primero los créditos más antiguos). Devuelve true si alcanzó y se
  /// descontó; optimista + sincroniza cada crédito tocado.
  Future<bool> usarBonoHoras(String club, int horas) async {
    if (horas <= 0) return true;
    if (miSaldoBono(club) < horas) return false;
    var restan = horas;
    // Ordena por antigüedad (FIFO): gasta primero lo comprado antes.
    final orden = [..._misBonos]
      ..sort((a, b) => a.creado.compareTo(b.creado));
    final actualizados = <String, int>{}; // id → nuevas horas_usadas
    for (final c in orden) {
      if (restan <= 0) break;
      if (c.club != club || c.saldo <= 0) continue;
      final gastar = restan < c.saldo ? restan : c.saldo;
      actualizados[c.id] = c.horasUsadas + gastar;
      restan -= gastar;
    }
    if (restan > 0) return false; // no debería pasar (ya validamos el saldo)
    // Aplica local (inmutable → reconstruye) y sincroniza.
    _misBonos = [
      for (final c in _misBonos)
        if (actualizados.containsKey(c.id))
          BonoComprado(
            id: c.id,
            bonoId: c.bonoId,
            dueno: c.dueno,
            club: c.club,
            comprador: c.comprador,
            compradorNombre: c.compradorNombre,
            horasTotal: c.horasTotal,
            horasUsadas: actualizados[c.id]!,
            precio: c.precio,
            ventaId: c.ventaId,
            creado: c.creado,
          )
        else
          c
    ];
    notifyListeners();
    for (final e in actualizados.entries) {
      await BonosRepo.actualizarUsadas(e.key, e.value);
    }
    return true;
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
      _sincronizarConfigLocalDesdeNube();
      _repararClubLegado();
      _persistirDatos();
      notifyListeners();
    }
  }

  /// La NUBE es la fuente de verdad de la CONFIG de una cancha ya registrada.
  /// Si la misma cancha vive también en `canchasExtra` (editada en ESTE equipo),
  /// trae de la versión remota los campos de config (duración/precio/horario/
  /// seña/valle/nombre/servicios). Sin esto, dos equipos del MISMO dueño
  /// mostraban valores distintos: `canchaVigente` prioriza `canchasExtra`, así
  /// que el equipo que editó ANTES seguía viendo su valor viejo aunque otro
  /// equipo ya guardó el nuevo en la nube. Preserva id/dueño/verificada locales.
  /// (El flujo de edición espera la escritura a la nube antes de cerrar, así que
  /// esto no revierte una edición recién hecha en este mismo equipo.)
  void _sincronizarConfigLocalDesdeNube() {
    for (final r in canchasRemotas) {
      final i = canchasExtra.indexWhere((x) => x.id == r.id);
      if (i < 0) continue;
      final loc = canchasExtra[i];
      canchasExtra[i] = loc.copyWith(
        nombre: r.nombre,
        club: r.club,
        precioHora: r.precioHora,
        horaApertura: r.horaApertura,
        horaCierre: r.horaCierre,
        duracionSlotMin: r.duracionSlotMin,
        senaPct: r.senaPct,
        descuentoValle: r.descuentoValle,
        amenidades: r.amenidades,
        superficie: r.superficie,
      );
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
      final ajena = est['estado'] == 'reclamada_por_otro';
      if (rechazada && est['es_mio'] == true) {
        // MI reclamo fue RECHAZADO y no hay uno vigente del mismo lugar (el
        // backend prioriza un reclamo activo por encima de un rechazo viejo): la
        // cancha deja de ser mía y VUELVE A SER DESCUBIERTA (como si nadie la
        // hubiera reclamado). Sale de "Mis canchas" pero sigue en el mapa,
        // reclamable de nuevo. Se cancelan sus reservas.
        actualizada =
            c.copyWith(registrada: false, verificada: false, dueno: '');
        _cancelarReservasDeCancha(c.id);
      } else if (ajena && email.isNotEmpty && c.dueno == email) {
        // SEGURIDAD: el lugar tiene un dueño APROBADO con otra cuenta — mi
        // copia reclamada se deshace y vuelve a descubierta (auto-limpia las
        // filas "envenenadas" de cuando existió el hueco de apropiación).
        actualizada =
            c.copyWith(registrada: false, verificada: false, dueno: '');
        _cancelarReservasDeCancha(c.id);
      } else if (verificada && !c.verificada) {
        // SEGURIDAD (anti-apropiación): si esta cancha dice ser MÍA
        // (dueno = mi correo), solo se activa cuando el backend confirma que el
        // reclamo APROBADO es el mío (es_mio). Sin este candado, reclamar un
        // lugar que ya tenía un reclamo aprobado de OTRA persona activaba la
        // copia del nuevo reclamante al instante, sin pasar por la torre (el
        // estado se resuelve por LUGAR y devolvía la aprobación ajena).
        final esMia = email.isNotEmpty && c.dueno == email;
        if (esMia && est['es_mio'] != true) continue;
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
    // SEGURIDAD (anti-apropiación): si la cancha mostrada dice ser MÍA, la
    // consulta va IDENTIFICADA — el backend responde "reclamada_por_otro" (y
    // nunca "activada") cuando la aprobación vigente del lugar es de OTRA
    // persona. Sin esto, abrir la ficha de una copia reclamada promovía
    // verificada=true al instante con la aprobación ajena (y la escribía a
    // Supabase), saltándose la torre.
    final email = usuario?.email ?? '';
    final esMia = email.isNotEmpty && c.dueno == email;
    final est =
        await PropiedadService.estado(c.id, solicitante: esMia ? email : null);
    if (est == null || est['existe'] != true) return null;
    final verificada = est['verificada'] == true || est['estado'] == 'activada';
    final rechazada = est['estado'] == 'rechazada';
    final ajena = est['estado'] == 'reclamada_por_otro';
    Cancha? actualizada;
    if (esMia && ajena) {
      // El lugar pertenece a OTRO dueño aprobado: mi copia reclamada se
      // deshace y vuelve a DESCUBIERTA (auto-limpia también las filas
      // "envenenadas" creadas mientras existió el hueco de apropiación).
      actualizada = c.copyWith(registrada: false, verificada: false, dueno: '');
      _cancelarReservasDeCancha(c.id);
    } else if (verificada && !c.verificada) {
      if (esMia && est['es_mio'] != true) return null; // aprobación ajena: no
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

  /// Resuelve a qué cancha del DUEÑO pertenece una reserva, AUNQUE la reserva
  /// apunte a un id duplicado del mismo local (pasa cuando la cancha se
  /// re-registró/re-reclamó y quedó con varios ids: `misCanchas` deduplica por
  /// lugar y se queda con UNO, pero la reserva puede traer otro de los ids). Sin
  /// esto, una reserva real "no aparecía" en el panel del dueño. Null si la
  /// reserva no es de ninguna cancha suya.
  Cancha? miCanchaDeReserva(String canchaId) {
    if (canchaId.isEmpty) return null;
    final mias = misCanchas;
    // 1) Match directo por id (caso normal).
    for (final c in mias) {
      if (c.id == canchaId) return c;
    }
    // 2) Match por LUGAR: ubica la cancha original de la reserva (en todo lo que
    // conocemos) y busca la cancha del dueño del mismo local.
    Cancha? orig;
    for (final c in [...canchasExtra, ...canchasRemotas]) {
      if (c.id == canchaId) {
        orig = c;
        break;
      }
    }
    if (orig == null) return null;
    final clave = _claveLugar(orig);
    for (final c in mias) {
      if (_claveLugar(c) == clave &&
          _cercaDe(c.ubicacion, orig.ubicacion, 0.12)) {
        return c;
      }
    }
    return null;
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
    _propagarEdicionADuplicados(c);
  }

  /// El MISMO lugar puede tener VARIAS filas con ids distintos (por
  /// re-registrar/re-reclamar la cancha en pruebas). La dedup (`_dedupPorLugar`)
  /// se queda con UNO, y en otro equipo puede ser un id DISTINTO al que se editó
  /// → el cliente veía la duración/precio VIEJOS aunque el dueño ya guardó.
  /// Solución: propagar los campos que afectan la RESERVA a esos duplicados
  /// (local + nube), para que el cliente vea lo mismo sin importar cuál resuelva.
  /// Si no hay duplicados, no hace nada.
  void _propagarEdicionADuplicados(Cancha c) {
    final clave = _claveLugar(c);
    void aplicar(List<Cancha> lista) {
      for (var k = 0; k < lista.length; k++) {
        final x = lista[k];
        if (x.id == c.id) continue;
        if (_claveLugar(x) == clave &&
            _cercaDe(x.ubicacion, c.ubicacion, 0.12)) {
          final f = x.copyWith(
            duracionSlotMin: c.duracionSlotMin,
            precioHora: c.precioHora,
            horaApertura: c.horaApertura,
            horaCierre: c.horaCierre,
            senaPct: c.senaPct,
            descuentoValle: c.descuentoValle,
          );
          lista[k] = f;
          CanchasRepo.actualizar(f); // propaga a la nube (best-effort)
        }
      }
    }

    aplicar(canchasExtra);
    aplicar(canchasRemotas);
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
  // Virgen (como PRD): arranca en 0; el saldo real baja del backend al iniciar
  // sesión (antes arrancaba en 30 de demo, que confundía en pruebas limpias).
  int saldoClub = 0;
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

  // Correo TITULAR de la verificación local. La identidad es POR CUENTA, pero se
  // guarda en el dispositivo; este campo evita que, al cambiar de cuenta en el
  // mismo equipo, la nueva cuenta herede el "verificado" de la anterior.
  String _verifEmail = '';

  /// Limpia el estado de verificación LOCAL (al cambiar de cuenta / cerrar
  /// sesión). El estado real de cada cuenta vive en el backend y se re-sincroniza
  /// con [sincronizarVerificacion].
  void _limpiarVerificacionLocal() {
    estadoVerificacion = 'no';
    fechaNacimiento = null;
    dniVerificado = '';
    _verifEmail = '';
  }

  /// ¿Soy dueño de al menos una cancha PROPIA? (no cuenta el "legado
  /// reclamable"). Los dueños/academias son vendedores de confianza.
  bool get soyDueno {
    final email = usuario?.email ?? '';
    if (email.isEmpty) return false;
    return [...canchasRemotas, ...canchasExtra].any((c) => c.dueno == email);
  }

  /// ¿Puedo PUBLICAR en el Marketplace? Cualquier usuario verificado, o un dueño
  /// de cancha (aunque no haya verificado su identidad como jugador). Es el
  /// candado anti-fraude: para vender hay que estar identificado.
  bool get puedeVender => jugadorVerificado || soyDueno;

  // Datos que devuelve la consulta oficial del documento (Factiliza/DNI en Perú).
  // La fecha de nacimiento permite CATEGORIZAR por edad en campeonatos (Sub-30,
  // etc.) sin volver a pedir el documento. Dato personal (Ley 29733): solo se
  // guarda localmente en el dispositivo del dueño de la cuenta, no se publica.
  DateTime? fechaNacimiento;
  String dniVerificado = '';

  /// Edad ACTUAL calculada a partir de [fechaNacimiento] (null si no hay dato).
  int? get edadActual {
    final f = fechaNacimiento;
    return f == null ? null : edadDesdeFecha(f);
  }

  /// Edad actual (años cumplidos) a partir de una fecha de nacimiento dada.
  /// Devuelve null si el resultado no es plausible (fecha corrupta).
  int? edadDesdeFecha(DateTime f) {
    final hoy = DateTime.now();
    var edad = hoy.year - f.year;
    if (hoy.month < f.month || (hoy.month == f.month && hoy.day < f.day)) {
      edad--;
    }
    return edad >= 0 && edad < 130 ? edad : null;
  }

  /// Parsea una fecha de nacimiento en los formatos que puede devolver la API
  /// (dd/mm/yyyy o yyyy-mm-dd). Devuelve null si no reconoce el formato.
  static DateTime? _parseNacimiento(String? raw) {
    final s = (raw ?? '').trim();
    if (s.isEmpty) return null;
    // dd/mm/yyyy
    final m1 = RegExp(r'^(\d{1,2})/(\d{1,2})/(\d{4})$').firstMatch(s);
    if (m1 != null) {
      final d = int.tryParse(m1.group(1)!), mo = int.tryParse(m1.group(2)!);
      final y = int.tryParse(m1.group(3)!);
      if (d != null && mo != null && y != null) return DateTime(y, mo, d);
    }
    // yyyy-mm-dd (ISO, con o sin hora)
    final m2 = RegExp(r'^(\d{4})-(\d{1,2})-(\d{1,2})').firstMatch(s);
    if (m2 != null) {
      final y = int.tryParse(m2.group(1)!), mo = int.tryParse(m2.group(2)!);
      final d = int.tryParse(m2.group(3)!);
      if (y != null && mo != null && d != null) return DateTime(y, mo, d);
    }
    return null;
  }

  /// Verifica la identidad del jugador consultando su documento contra el
  /// registro oficial (Perú: DNI vía Factiliza). Es la validación ANTI-FRAUDE
  /// real: si el número no existe en RENIEC, no se verifica (a diferencia de
  /// subir una foto cualquiera). Al validar, guarda la fecha de nacimiento para
  /// categorizar por edad. Devuelve `(ok, mensajeError)`.
  Future<(bool, String?)> verificarConDni(String dni) async {
    final u = usuario;
    if (u == null) return (false, 'Inicia sesión primero.');
    if (!PropiedadService.disponible) {
      return (false, 'Servicio de verificación no disponible.');
    }
    final numero = dni.trim();
    final doc = paisActual.docId; // 'DNI' (PE) · 'Cédula' (EC)
    // Verifica contra el registro oficial del país + regla "1 documento = 1
    // cuenta" (anti-fraude). El país decide la fuente (RENIEC/Factiliza o
    // CipherByte).
    final data = await PropiedadService.verificarDni(numero, u.email,
        pais: paisActual.iso);
    if (data == null) {
      return (false, 'No pudimos conectar. Revisa tu conexión.');
    }
    if (data['ok'] != true) {
      if (data['error'] == 'dni_en_uso') {
        return (false,
            'Ese $doc ya está verificado en otra cuenta. Cada persona verifica '
            'una sola cuenta.');
      }
      return (false, 'Ese número no figura en el registro. Revísalo.');
    }
    // Válido: guarda nacimiento + marca verificado (marcha blanca del piloto).
    fechaNacimiento = _parseNacimiento(data['fecha_nacimiento'] as String?);
    dniVerificado = numero;
    estadoVerificacion = 'verificado';
    _verifEmail = u.email.toLowerCase();
    // Best-effort: registra en el backend para que otros vean la insignia.
    try {
      await VerificacionRepo.registrarVerificado(
          email: u.email, nombre: u.nombre);
    } catch (_) {}
    notifyListeners();
    _persistirDatos();
    return (true, null);
  }

  /// Sincroniza el estado de verificación desde el backend (best-effort). El
  /// backend es la FUENTE DE VERDAD por cuenta: así, aunque el estado local haya
  /// quedado de otra cuenta, aquí se corrige al valor real de la cuenta actual.
  Future<void> sincronizarVerificacion() async {
    final email = usuario?.email;
    if (email == null || email.isEmpty) return;
    final st = await VerificacionRepo.estadoDe(email);
    final low = email.toLowerCase();
    var cambio = false;
    if (st != estadoVerificacion) {
      estadoVerificacion = st;
      cambio = true;
    }
    if (st == 'verificado') {
      if (_verifEmail != low) {
        _verifEmail = low;
        cambio = true;
      }
    } else {
      // El backend dice que esta cuenta NO está verificada: borra cualquier dato
      // personal heredado (DNI/nacimiento) de otra cuenta en este equipo.
      if (dniVerificado.isNotEmpty || fechaNacimiento != null ||
          _verifEmail.isNotEmpty) {
        dniVerificado = '';
        fechaNacimiento = null;
        _verifEmail = '';
        cambio = true;
      }
    }
    if (cambio) {
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

  /// Verificación por OCR on-device (países sin registro oficial, hoy Bolivia).
  /// El documento ya pasó el filtro OCR (es un documento, no una imagen
  /// cualquiera). Sube doc + selfie al bucket privado como evidencia y guarda la
  /// fecha de nacimiento si el OCR la detectó (para categorizar por edad).
  Future<bool> verificarConOcr(
      {required Uint8List doc,
      required Uint8List selfie,
      DateTime? nacimiento}) async {
    final u = usuario;
    if (u == null) return false;
    final st = await VerificacionRepo.enviar(
        email: u.email, nombre: u.nombre, doc: doc, selfie: selfie);
    if (st == null) return false;
    estadoVerificacion = st;
    _verifEmail = u.email.toLowerCase();
    if (nacimiento != null) fechaNacimiento = nacimiento;
    notifyListeners();
    _persistirDatos();
    return true;
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
    _verifEmail = u.email.toLowerCase();
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
  // Virgen (como PRD): sin movimientos demo. El historial real baja del backend.
  final List<MovimientoSaldo> movimientos = [];
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
    // recargas. IMPORTANTE (privacidad): refleja SIEMPRE lo que devuelve el
    // backend para ESTE correo. Si responde LISTA VACÍA (el usuario no tiene
    // movimientos), se LIMPIA — antes se conservaba lo local y un jugador podía
    // ver los movimientos que quedaron de otra cuenta (p. ej. el dueño) en el
    // mismo dispositivo. Solo si el backend NO responde (null) se conserva lo
    // local (fallo transitorio).
    final movs = await PagosService.movimientos(email);
    if (movs != null) {
      movimientos
        ..clear()
        ..addAll(movs.map((m) {
          final tipoStr = (m['tipo'] as String?) ?? 'recarga';
          // Egresos de la billetera (Pro, servicios, torneo, comisión) → consumo.
          // Ingresos "por recibir" (reserva online) → liquidación (los paga
          // Pichangol aparte). 'liquidacion_full' = billetera-first: recibes el
          // 100% porque la comisión ya salió de tu saldo (otro movimiento).
          final tipo = switch (tipoStr) {
            'comision_reserva' ||
            'suscripcion' ||
            'suscripcion_pro' ||
            'inscripcion_torneo' =>
              TipoMovimiento.consumo,
            'liquidacion_online' || 'liquidacion_full' || 'venta_producto' =>
              TipoMovimiento.liquidacion,
            _ => TipoMovimiento.recarga, // recarga, inscripcion_torneo_ingreso
          };
          final sim = monedaSaldoSimbolo;
          final com = (m['comision_soles'] as num?)?.toDouble() ?? 0;
          final bruto = (m['bruto_soles'] as num?)?.toDouble() ?? 0;
          var concepto = (m['concepto'] as String?) ?? '';
          var fuente = '';
          if (tipoStr == 'liquidacion_online') {
            // La comisión salió del PAGO del jugador: recibes el neto. El desglose
            // (cobrado/comisión/recibes) lo muestra la tarjeta, no el concepto.
            fuente = 'transaccion';
            if (concepto.isEmpty) concepto = 'Reserva online';
          } else if (tipoStr == 'liquidacion_full') {
            // Billetera-first: recibes el 100%; la comisión ya se descontó de tu
            // saldo (aparece como otro movimiento "Comisión").
            fuente = 'saldo';
            concepto = concepto.isEmpty
                ? 'Reserva online · recibes 100%'
                : '$concepto · recibes 100%';
          } else if (tipoStr == 'venta_producto') {
            // Venta del marketplace o bono de horas: Pichangol cobró al comprador
            // y te debe el neto (por recibir). El concepto ya dice qué fue
            // ("Bono 2h · Club" / "Venta: producto"); el desglose va en la tarjeta.
            fuente = 'transaccion';
            if (concepto.isEmpty) concepto = 'Venta';
          } else if (tipoStr == 'comision_reserva') {
            // Egreso de la billetera: dejar claro de dónde salió.
            fuente = 'saldo';
            if (concepto.isEmpty) concepto = 'Comisión de reserva';
          } else if (concepto.isEmpty) {
            concepto = tipo == TipoMovimiento.consumo
                ? 'Consumo de saldo'
                : 'Recarga de saldo';
          }
          final montoExacto = (m['monto_soles'] as num?)?.toDouble() ?? 0;
          // Para el recibo: comisión de este movimiento (en comision_reserva el
          // monto ES la comisión).
          final comisionRecibo =
              tipoStr == 'comision_reserva' ? montoExacto.abs() : com;
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
            brutoSoles: bruto,
            comisionSoles: comisionRecibo,
            fuente: fuente,
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
  static const _kVerifEmail = 'verificacion_email'; // titular de la verificación
  static const _kRecordCobro = 'recordatorios_cobro_json'; // alumnoId→ISO
  static const _kRecordAuto = 'recordatorios_auto'; // avisos proactivos on/off
  static const _kAsistAvisada = 'asistencia_avisada_json'; // "alumnoId|dia"
  static const _kDescuentosSlot = 'descuentos_slot_json'; // "cancha|fecha|hora"→pct
  static const _kCierresCaja = 'cierres_caja_json';
  static const _kReservasFijas = 'reservas_fijas_json';
  static const _kResRecordadas = 'reservas_recordadas_json';
  static const _kNacimiento = 'fecha_nacimiento_iso';
  static const _kDniVerif = 'dni_verificado';
  static const _kMovs = 'movimientos_json';
  static const _kMisReservas = 'mis_reservas_json';
  static const _kCanchas = 'canchas_extra_json';
  static const _kEliminadas = 'canchas_eliminadas_json';
  static const _kAcademiasEliminadas = 'academias_eliminadas_json';
  static const _kLandingNegocios = 'landing_negocios_json';
  static const _kFavoritos = 'favoritos_json';
  static const _kRadio = 'radio_busqueda_km';
  static const _kTema = 'tema_modo'; // 0=system, 1=light, 2=dark
  static const _kMostrarUltimaVez = 'priv_mostrar_ultima_vez';
  static const _kConfirmacionLectura = 'priv_confirmacion_lectura';
  static const _kAcademias = 'academias_json';
  static const _kAcademiasPendientes = 'academias_pendientes_nube_json';
  static const _kAlumnos = 'alumnos_json';
  static const _kCuotas = 'cuotas_json';
  static const _kAsistencias = 'asistencias_json';
  static const _kPlanes = 'planes_trabajo_json';
  static const _kEvaluaciones = 'evaluaciones_json';
  static const _kNotasClase = 'notas_clase_json';
  static const _kCampeonatos = 'campeonatos_json';
  static const _kInvitaciones = 'invitaciones_json';
  static const _kChatLecturas = 'chat_lecturas_json';
  static const _kChatsOcultos = 'chats_ocultos_json';
  static const _kApodos = 'apodos_json';
  static const _kPerfiles = 'perfiles_cache_json';
  static const _kNotasCliente = 'notas_cliente_json'; // clave cliente→nota dueño
  static const _kVideosLocales = 'videos_locales_json';
  static const _kBloqueados = 'bloqueados_json';
  static const _kChatsFijados = 'chats_fijados_json';
  static const _kChatsArchivados = 'chats_archivados_json';
  static const _kChatsSilenciados = 'chats_silenciados_json';

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
        cargarMisNiveles(); // mi nivel de jugador (device-first) al reabrir la app
        cargarReservasSync(); // reservas offline pendientes de subir (outbox)
        cargarContabilidad(); // comisión/liquidación pendiente de registrar
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
      if (prefs.containsKey(_kNacimiento)) {
        fechaNacimiento = DateTime.tryParse(prefs.getString(_kNacimiento) ?? '');
      }
      dniVerificado = prefs.getString(_kDniVerif) ?? dniVerificado;
      _verifEmail = (prefs.getString(_kVerifEmail) ?? '').toLowerCase();
      recordatoriosAutoActivos =
          prefs.getBool(_kRecordAuto) ?? recordatoriosAutoActivos;
      final rc = prefs.getString(_kRecordCobro);
      if (rc != null && rc.isNotEmpty) {
        try {
          _recordatoriosCobro
            ..clear()
            ..addAll((jsonDecode(rc) as Map)
                .map((k, v) => MapEntry(k.toString(), v.toString())));
        } catch (_) {}
      }
      final aa = prefs.getString(_kAsistAvisada);
      if (aa != null && aa.isNotEmpty) {
        try {
          _asistenciaAvisada
            ..clear()
            ..addAll((jsonDecode(aa) as List).map((e) => e.toString()));
        } catch (_) {}
      }
      final ds = prefs.getString(_kDescuentosSlot);
      if (ds != null && ds.isNotEmpty) {
        try {
          _descuentosSlot
            ..clear()
            ..addAll((jsonDecode(ds) as Map)
                .map((k, v) => MapEntry(k.toString(), (v as num).toInt())));
        } catch (_) {}
      }
      final cc = prefs.getString(_kCierresCaja);
      if (cc != null && cc.isNotEmpty) {
        try {
          cierresCaja
            ..clear()
            ..addAll((jsonDecode(cc) as List)
                .map((e) => CierreCaja.fromJson(Map<String, dynamic>.from(e))));
        } catch (_) {}
      }
      final rf = prefs.getString(_kReservasFijas);
      if (rf != null && rf.isNotEmpty) {
        try {
          reservasFijas
            ..clear()
            ..addAll((jsonDecode(rf) as List)
                .map((e) => ReservaFija.fromJson(Map<String, dynamic>.from(e))));
        } catch (_) {}
      }
      final rr = prefs.getString(_kResRecordadas);
      if (rr != null && rr.isNotEmpty) {
        try {
          _reservasRecordadas
            ..clear()
            ..addAll((jsonDecode(rr) as List).map((e) => e.toString()));
        } catch (_) {}
      }
      // Migración de instalaciones previas (sin titular guardado): atribuye la
      // verificación existente al usuario logueado.
      if (_verifEmail.isEmpty &&
          estadoVerificacion != 'no' &&
          (usuario?.email.isNotEmpty ?? false)) {
        _verifEmail = usuario!.email.toLowerCase();
      }
      // Salvaguarda: si el estado local pertenece a OTRA cuenta que la logueada,
      // límpialo (evita mostrar "verificado" heredado). El backend lo corrige.
      if (estadoVerificacion != 'no' &&
          (usuario?.email.isNotEmpty ?? false) &&
          _verifEmail != usuario!.email.toLowerCase()) {
        _limpiarVerificacionLocal();
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

      mostrarUltimaVez = prefs.getBool(_kMostrarUltimaVez) ?? mostrarUltimaVez;
      confirmacionLectura =
          prefs.getBool(_kConfirmacionLectura) ?? confirmacionLectura;

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

      final acElimRaw = prefs.getString(_kAcademiasEliminadas);
      if (acElimRaw != null) {
        _academiasEliminadas
          ..clear()
          ..addAll((jsonDecode(acElimRaw) as List).map((e) => e.toString()));
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
      _cargarLista(prefs, _kPlanes, planes, PlanTrabajo.fromJson);
      _cargarLista(prefs, _kEvaluaciones, evaluaciones, EvaluacionAlumno.fromJson);
      _cargarLista(prefs, _kNotasClase, notasClase, NotaClase.fromJson);
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

      final ocultosRaw = prefs.getString(_kChatsOcultos);
      if (ocultosRaw != null) {
        try {
          final m = jsonDecode(ocultosRaw) as Map<String, dynamic>;
          chatsOcultos
            ..clear()
            ..addAll(m.map((k, v) => MapEntry(k, v.toString())));
        } catch (_) {}
      }

      final apodosRaw = prefs.getString(_kApodos);
      if (apodosRaw != null) {
        try {
          final m = jsonDecode(apodosRaw) as Map<String, dynamic>;
          _apodos
            ..clear()
            ..addAll(m.map((k, v) => MapEntry(k, v.toString())));
        } catch (_) {}
      }

      // Caché PERSISTENTE de perfiles (nombre+foto): así el inbox y el chat
      // muestran nombre/avatar al INSTANTE al reabrir, sin re-bajar de Supabase
      // ni parpadear (device-first, como WhatsApp). Se refresca en segundo plano.
      final perfilesRaw = prefs.getString(_kPerfiles);
      if (perfilesRaw != null) {
        try {
          final m = jsonDecode(perfilesRaw) as Map<String, dynamic>;
          m.forEach((k, v) {
            if (v is Map) _perfiles[k] = Map<String, dynamic>.from(v);
          });
        } catch (_) {}
      }

      // Notas privadas del dueño por cliente (cuaderno del club, device-first).
      final notasRaw = prefs.getString(_kNotasCliente);
      if (notasRaw != null) {
        try {
          final m = jsonDecode(notasRaw) as Map<String, dynamic>;
          m.forEach((k, v) => _notasCliente[k] = v.toString());
        } catch (_) {}
      }

      final vidsRaw = prefs.getString(_kVideosLocales);
      if (vidsRaw != null) {
        try {
          final m = jsonDecode(vidsRaw) as Map<String, dynamic>;
          m.forEach((k, v) => _videosLocales[k] = v.toString());
        } catch (_) {}
      }

      final bloqRaw = prefs.getString(_kBloqueados);
      if (bloqRaw != null) {
        try {
          final l = jsonDecode(bloqRaw) as List;
          _bloqueados
            ..clear()
            ..addAll(l.map((e) => e.toString()));
        } catch (_) {}
      }

      void cargarSetChat(String key, Set<String> target) {
        final raw = prefs.getString(key);
        if (raw == null) return;
        try {
          final l = jsonDecode(raw) as List;
          target
            ..clear()
            ..addAll(l.map((e) => e.toString()));
        } catch (_) {}
      }

      cargarSetChat(_kChatsFijados, chatsFijados);
      cargarSetChat(_kChatsArchivados, chatsArchivados);
      cargarSetChat(_kChatsSilenciados, chatsSilenciados);

      final vistosRaw = prefs.getString(_kEstadosVistos);
      if (vistosRaw != null) {
        try {
          final l = jsonDecode(vistosRaw) as List;
          _estadosVistos
            ..clear()
            ..addAll(l.map((e) => e.toString()));
        } catch (_) {}
      }

      final ocEstRaw = prefs.getString(_kEstadosOcultos);
      if (ocEstRaw != null) {
        try {
          final l = jsonDecode(ocEstRaw) as List;
          _estadosOcultos
            ..clear()
            ..addAll(l.map((e) => e.toString()));
        } catch (_) {}
      }

      final canalVistoRaw = prefs.getString(_kCanalVisto);
      if (canalVistoRaw != null) {
        try {
          final m = jsonDecode(canalVistoRaw) as Map<String, dynamic>;
          _canalVisto.clear();
          m.forEach((k, v) {
            final t = DateTime.tryParse(v.toString());
            if (t != null) _canalVisto[k] = t;
          });
        } catch (_) {}
      }

      notifyListeners();
      // Trae la disponibilidad compartida (reservas de otros dispositivos) para
      // que el anti-doble-reserva y el panel del dueño arranquen al día. Best-effort.
      cargarReservasRemotas();
      cargarCanalComunicacion(); // política de canal (WhatsApp vs chat PCG)
      // SESIÓN RESTAURADA (no pasa por _finalizarLogin): sincroniza la agenda
      // (apodos/contactos/bloqueados) y las historias desde la nube para que los
      // cambios hechos en OTRO dispositivo lleguen a este. Se hace al FINAL, tras
      // cargar lo local, para no pisar el merge. Best-effort.
      if (usuario != null) {
        sincronizarAgenda();
        cargarEstados();
      }
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
      await prefs.setString(_kVerifEmail, _verifEmail);
      await prefs.setString(_kRecordCobro, jsonEncode(_recordatoriosCobro));
      await prefs.setBool(_kRecordAuto, recordatoriosAutoActivos);
      await prefs.setBool(_kMostrarUltimaVez, mostrarUltimaVez);
      await prefs.setBool(_kConfirmacionLectura, confirmacionLectura);
      await prefs.setString(
          _kAsistAvisada, jsonEncode(_asistenciaAvisada.toList()));
      await prefs.setString(_kDescuentosSlot, jsonEncode(_descuentosSlot));
      await prefs.setString(_kCierresCaja,
          jsonEncode(cierresCaja.map((c) => c.toJson()).toList()));
      await prefs.setString(_kReservasFijas,
          jsonEncode(reservasFijas.map((f) => f.toJson()).toList()));
      await prefs.setString(
          _kResRecordadas, jsonEncode(_reservasRecordadas.toList()));
      if (fechaNacimiento != null) {
        await prefs.setString(
            _kNacimiento, fechaNacimiento!.toIso8601String());
      } else {
        await prefs.remove(_kNacimiento);
      }
      if (dniVerificado.isNotEmpty) {
        await prefs.setString(_kDniVerif, dniVerificado);
      } else {
        await prefs.remove(_kDniVerif);
      }
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
          _kAcademiasEliminadas, jsonEncode(_academiasEliminadas.toList()));
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
      await prefs.setString(
          _kPlanes, jsonEncode(planes.map((p) => p.toJson()).toList()));
      await prefs.setString(_kEvaluaciones,
          jsonEncode(evaluaciones.map((e) => e.toJson()).toList()));
      await prefs.setString(_kNotasClase,
          jsonEncode(notasClase.map((n) => n.toJson()).toList()));
      await prefs.setString(_kCampeonatos,
          jsonEncode(campeonatos.map((c) => c.toJson()).toList()));
      await prefs.setString(_kInvitaciones,
          jsonEncode(invitaciones.map((i) => i.toJson()).toList()));
      await prefs.setString(_kChatLecturas, jsonEncode(chatLecturas));
      await prefs.setString(_kChatsOcultos, jsonEncode(chatsOcultos));
      await prefs.setString(_kApodos, jsonEncode(_apodos));
      await prefs.setString(_kBloqueados, jsonEncode(_bloqueados.toList()));
      await prefs.setString(_kChatsFijados, jsonEncode(chatsFijados.toList()));
      await prefs.setString(
          _kChatsArchivados, jsonEncode(chatsArchivados.toList()));
      await prefs.setString(
          _kChatsSilenciados, jsonEncode(chatsSilenciados.toList()));
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
    // Cambio directo de cuenta (sin cerrar sesión antes): no arrastrar la agenda
    // ni los chats/estados de la cuenta anterior a la nueva.
    final previo = (usuario?.email ?? '').toLowerCase();
    if (previo.isNotEmpty && previo != u.email.toLowerCase()) {
      _limpiarDatosDeSesion();
    }
    usuario = u;
    // La verificación de identidad es POR CUENTA: si cambió el titular, limpia el
    // estado local para que la nueva cuenta NO herede el "verificado" de la
    // anterior en el mismo equipo. El estado real llega de sincronizarVerificacion.
    if (_verifEmail != u.email.toLowerCase()) _limpiarVerificacionLocal();
    _persistirUsuario();
    sincronizarVerificacion(); // estado REAL de verificación de esta cuenta
    _sincronizarMiPerfil(); // aplica/crea mi nombre-foto público (best-effort)
    PushService.registrarParaUsuario(u.email); // push del chat a este dispositivo
    _recomputarMisReservas(); // recupera sus reservas de otros dispositivos
    notifyListeners();
    cargarReservasRemotas(); // best-effort refresco
    sincronizarSaldo(); // saldo real del backend (sobrevive reinstalar)
    sincronizarAgenda(); // apodos + contactos + bloqueados en todos mis dispositivos
    cargarEstados(); // historias vigentes (24 h) de mis conocidos
    cargarMisNiveles(); // mi nivel de jugador por deporte (device-first)
    cargarReservasSync(); // reservas offline pendientes de subir (outbox)
    cargarContabilidad(); // comisión/liquidación pendiente de registrar
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
    _limpiarVerificacionLocal(); // no arrastrar la verificación a otra cuenta
    _limpiarDatosDeSesion(); // agenda, chats y estados NO deben cruzarse de cuenta
    await _persistirUsuario();
    _persistirDatos();
    _persistirContactos();
    notifyListeners();
  }

  /// Limpia TODO lo que es privado de una cuenta (agenda, estado de chats e
  /// historias) para que al cambiar de usuario en el mismo equipo NO se vea nada
  /// del anterior. La fuente de verdad de cada cuenta vuelve a bajarse de la nube
  /// al iniciar sesión (sincronizarAgenda, cargarEstados, etc.).
  void _limpiarDatosDeSesion() {
    _apodos.clear();
    _contactos.clear();
    _bloqueados.clear();
    _misNiveles.clear();
    _reservasPendientesSync.clear();
    _reservasNoConfirmadas.clear();
    _contaPend.clear();
    _contaEnEspera.clear();
    _reembolsosPend.clear();
    chatsOcultos.clear();
    chatsFijados.clear();
    chatsArchivados.clear();
    chatsSilenciados.clear();
    _estados.clear();
    _estadosVistos.clear();
    _estadosOcultos.clear();
    _vistasPorEstado.clear();
    _perfiles.clear();
    _guardarPerfiles(); // limpia también el caché en disco (no mostrar ajenos)
    _retosPendientes = 0;
    // BILLETERA: el saldo y los movimientos son PRIVADOS de cada cuenta. Al
    // cambiar de usuario en el mismo equipo hay que vaciarlos, o el nuevo usuario
    // (p. ej. un jugador) vería los movimientos del anterior (p. ej. el dueño).
    // El valor real de esta cuenta lo baja `sincronizarSaldo` del backend.
    movimientos.clear();
    saldoClub = 0;
    _saldoOtrosPaises.clear();
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
        // Torre de control: borra MIS reclamos de propiedad del servidor.
        await PropiedadService.borrarMisReclamos(email);
        // Billetera del backend en virgen (saldo 0 + sin movimientos).
        await PagosService.resetMiBilletera(email);
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
    _academiasEliminadas.clear();
    _contaPend.clear();
    _contaEnEspera.clear();
    _reembolsosPend.clear();
    _reservasPendientesSync.clear();
    _reservasNoConfirmadas.clear();
    alumnos.clear();
    cuotas.clear();
    asistencias.clear();
    planes.clear();
    evaluaciones.clear();
    notasClase.clear();
    invitaciones.clear();
    campeonatos.clear();
    movimientos.clear();
    _landingNegocios.clear();
    _saldoOtrosPaises.clear();
    saldoClub = 0;
    _ultimoSyncMatriculas = null;
    _limpiarVerificacionLocal();
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

  /// "DEJAR EN VIRGEN": borra TODO lo del usuario —academias, alumnos, matrículas,
  /// reservas, cobros, saldo, campeonatos, chats, reseñas y sus canchas reclamadas
  /// (incluido el reclamo en la torre de control)— pero MANTIENE la sesión abierta.
  /// Es como "Empezar de cero" pero SIN cerrar sesión (ni borrar todas las prefs).
  ///
  /// Nube (best-effort, solo lo del usuario logueado): borra sus academias y las
  /// matrículas (suyas y de sus academias), las reservas y reseñas de sus canchas,
  /// y sus reclamos de propiedad. El saldo/pagos/suscripciones del servidor se
  /// limpian aparte desde la torre de control (botón "Dejar el servidor en
  /// virgen").
  Future<void> resetVirgen() async {
    final email = usuario?.email.toLowerCase();
    if (email != null && email.isNotEmpty) {
      // ACADEMIAS MÍAS: junta las que están en memoria + las que estén SOLO en la
      // nube (aún no cargadas). Si no consultara la nube, una academia no cargada
      // se escaparía del tombstone y reaparecería al re-sincronizar.
      final misAcademiaIds = <String>{
        for (final a in academias)
          if (a.dueno.toLowerCase() == email) a.id,
      };
      try {
        for (final a in await AcademiasRepo.fetchRemotas()) {
          if (a.dueno.toLowerCase() == email) misAcademiaIds.add(a.id);
        }
      } catch (_) {}
      // CANCHAS MÍAS: locales + solo-nube (mismo motivo).
      final misCanchaIds = <String>{
        for (final c in [...canchasExtra, ...canchasRemotas])
          if (c.dueno.toLowerCase() == email) c.id,
      };
      try {
        for (final c in await CanchasRepo.fetchRemotas()) {
          if (c.dueno.toLowerCase() == email) misCanchaIds.add(c.id);
        }
      } catch (_) {}
      // Matrículas (alumnos + cuotas embebidas) de mis academias + las mías.
      for (final al in List<Alumno>.from(alumnos)) {
        if (misAcademiaIds.contains(al.academiaId) ||
            al.email.toLowerCase() == email) {
          await MatriculasRepo.eliminar(al.id);
        }
      }
      // Reservas y reseñas de mis canchas.
      for (final id in misCanchaIds) {
        await ReservasRepo.eliminarDeCancha(id);
      }
      await ResenasRepo.eliminarDeCanchas(misCanchaIds.toList());
      await EsperaRepo.eliminarDeCanchas(misCanchaIds.toList());
      await BonosRepo.eliminarDeDueno(email);
      // Chats: de mis academias + conversaciones de cancha donde participo.
      await MensajesRepo.eliminarDeAcademias(misAcademiaIds.toList());
      await MensajesRepo.eliminarCanchaDe(email);
      // Campeonatos de mis academias.
      for (final c in campeonatos.where((c) => misAcademiaIds.contains(c.academiaId))) {
        await CampeonatosRepo.eliminar(c.id);
      }
      // ACADEMIAS: borra en la nube + TOMBSTONE durable (aunque el borrado en la
      // nube falle por RLS, no reaparece en este dispositivo).
      for (final id in misAcademiaIds) {
        await AcademiasRepo.eliminar(id);
        _academiasEliminadas.add(id);
      }
      // CANCHAS: tombstone durable + quita local + borra en la nube.
      for (final id in misCanchaIds) {
        eliminarCancha(id);
      }
      // Torre de control (backend): borra MIS reclamos de propiedad para que mis
      // canchas reclamadas también desaparezcan del servidor.
      await PropiedadService.borrarMisReclamos(email);
      // BILLETERA en el backend: saldo 0 y sin movimientos. Sin esto, el saldo y
      // los pagos "por recibir" volverían al re-sincronizar (viven en el server).
      await PagosService.resetMiBilletera(email);
    }
    // Tombstone CUALQUIER academia local restante (p. ej. la demo de dev) para que
    // no reaparezca al re-cargar de la nube ni se re-siembre.
    _academiasEliminadas.addAll(academias.map((a) => a.id));
    // Memoria local: borra TODO lo transaccional Y las academias/alumnos; CONSERVA
    // solo la sesión (no cierra sesión, esa es la diferencia con "Empezar de cero").
    reservas.clear();
    agenda.clear();
    misReservas.clear();
    academias.clear();
    _academiasPendientesNube.clear();
    alumnos.clear();
    cuotas.clear();
    asistencias.clear();
    planes.clear();
    evaluaciones.clear();
    notasClase.clear();
    invitaciones.clear();
    movimientos.clear();
    campeonatos.clear();
    _landingNegocios.clear();
    saldoClub = 0;
    _saldoOtrosPaises.clear();
    _ultimoSyncMatriculas = null;
    // Colas pendientes (outbox): si no se vacían, `flushContabilidad` /
    // `sincronizarReservasPendientes` re-registrarían movimientos y reservas en
    // el backend después del reset → la billetera volvería a "llenarse".
    _contaPend.clear();
    _contaEnEspera.clear();
    _reembolsosPend.clear();
    _reservasPendientesSync.clear();
    _reservasNoConfirmadas.clear();
    _limpiarVerificacionLocal(); // la verificación de identidad también se reinicia
    notifyListeners();
    await _persistirDatos();
    await _persistirContabilidad();
    await _persistirReservasSync();
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
      String cobro = 'ninguno',
      String medioPago = '',
      int sena = 0,
      String grupoReservaId = '',
      bool notificarDueno = true}) async {
    // Chequeo local rápido (doble toque / feedback inmediato sin conexión).
    // La agenda es COMPARTIDA entre deportes: se ocupa por (cancha, fecha, hora),
    // sin importar el deporte (es la misma superficie física).
    final yaLocal = reservas.any((r) =>
        r.canchaId == cancha.id && r.fecha == fecha && r.horaInicio == hora);
    if (yaLocal) {
      _reembolsoSiPagado(cobro, cancha, fecha, hora, sena);
      return ResultadoReserva.ocupado;
    }

    // Precio efectivo del slot (hora feliz de mañanas + descuento puntual).
    final precio = precioSlotEfectivo(cancha, fecha, hora);
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
      // Pago ONLINE (tarjeta/Yape por Culqi): el jugador YA pagó el total → la
      // reserva nace PAGADA y el dueño NO tiene que marcarla. Efectivo (paga en
      // la cancha) y seña (adelanta una parte, debe el resto) nacen sin pagar:
      // ahí el dueño sí confirma cuando cobra el resto/efectivo.
      // Online = pagado por Culqi. BONO = el jugador YA lo pagó al comprar el
      // pack (por eso NO genera contabilidad extra: `_accionContable` devuelve
      // null para 'bono'); nace pagada y el dueño no la marca.
      pagado: cobro == 'online' || cobro == 'bono',
      // Seña anti no-show cobrada por adelantado (Culqi). 0 = sin seña / pago
      // total online / efectivo puro. No reembolsable: se queda con el dueño.
      sena: sena.clamp(0, precio),
      // trazabilidad: yape/tarjeta/efectivo/sena/bono
      medioPago: cobro == 'bono' ? 'bono' : medioPago,

      usuario: usuario?.email ?? '',
      // Deporte elegido para este slot (loza multiuso). Default: el principal.
      deporte: (deporte ?? cancha.deporte).name,
      moneda: cancha.monedaSimbolo, // moneda de la cancha (Perú S/, Bolivia Bs…)
      extras: extras, // servicios extra elegidos (árbitro/pelotero…)
      grupoReservaId: grupoReservaId, // agrupa las horas de una reserva multi-hora
    );

    // Fuente de verdad anti-doble-reserva: Supabase con
    // UNIQUE(cancha_id, fecha, hora_inicio). Si otro ganó el slot → ocupado.
    final res = await ReservasRepo.insertarSegura(reserva);
    if (res == ResultadoReserva.ocupado) {
      // Se cobró por adelantado (online/seña) pero el slot ya lo tomó otro →
      // registra el reembolso (no nos quedamos la plata).
      _reembolsoSiPagado(cobro, cancha, fecha, hora, sena);
      return res;
    }

    // ok / sinConexion / error → se guarda local igual (fail-safe offline).
    reservas.insert(0, reserva); // visible para el dueño en su panel
    misReservas.insert(0, reserva); // visible para el jugador en "Mis reservas"
    if (diaLabel == 'Hoy') {
      final i = agenda.indexWhere(
          (b) => b.canchaId == cancha.id && b.hora == hora);
      if (i >= 0) agenda[i] = agenda[i].copyWith(reservaId: reserva.id);
    }
    // CONTABILIDAD (comisión de saldo / liquidación online), con REINTENTO:
    //  - 'efectivo': PCG cobra su comisión del SALDO prepago del dueño.
    //  - 'online'/'sena': el jugador pagó por la app; se registra la LIQUIDACIÓN
    //    (neto que PCG le debe al dueño). No toca el saldo.
    // Antes era una sola llamada best-effort (si fallaba la red, se PERDÍA). Ahora
    // se encola: si la reserva confirmó → se registra ya (con reintento); si quedó
    // offline → espera a confirmarse en el reintento del outbox.
    // El jugador que reserva (para que el dueño vea QUIÉN reservó en su billetera).
    final quien = reserva.jugador.trim();
    // Local (sede/club) + cancha, para que el movimiento diga DÓNDE fue. Se omite
    // el local si está vacío o si es igual al nombre de la cancha (no repetir).
    final local = cancha.club.trim();
    final lugar = (local.isEmpty || local == cancha.nombre.trim())
        ? cancha.nombre
        : '$local · ${cancha.nombre}';
    final accion = _accionContable(cancha, cobro,
        montoBase: precioHoraEfectivo(cancha, fecha, hora),
        sena: sena,
        reservaId: reserva.id,
        etiqueta: quien.isEmpty
            ? '$lugar · $diaLabel $hora'
            : '$lugar · $quien · $diaLabel $hora');
    if (res == ResultadoReserva.ok) {
      if (accion != null) _encolarConta(accion);
      // Reserva CONFIRMADA en el servidor → avisa al dueño (push dedicado).
      if (notificarDueno) _notificarDuenoReserva(cancha, [reserva]);
    } else {
      // Sin señal / error: quedó SOLO local. Va a la bandeja de salida para
      // reintentar subirla al recuperar conexión (y recién ahí avisar al dueño y
      // registrar la contabilidad).
      _reservasPendientesSync.add(reserva.id);
      if (accion != null) _contaEnEspera[reserva.id] = accion;
      unawaited(_persistirReservasSync());
      unawaited(_persistirContabilidad());
    }
    notifyListeners();
    _persistirDatos();
    return res == ResultadoReserva.ok ? ResultadoReserva.ok : res;
  }

  /// Si la reserva se pagó por adelantado (online/seña) pero el slot NO se pudo
  /// asegurar (ocupado), registra el reembolso pendiente para no quedarnos con la
  /// plata del jugador.
  void _reembolsoSiPagado(
      String cobro, Cancha cancha, String fecha, String hora, int sena) {
    if (cobro != 'online' && cobro != 'sena') return;
    final monto = cobro == 'sena'
        ? sena.toDouble()
        : precioHoraEfectivo(cancha, fecha, hora);
    _registrarReembolso('ocupado_${cancha.id}_${fecha}_$hora', monto,
        'Horario ya tomado (pagado por adelantado)');
  }

  /// RESERVA DE VARIAS HORAS SEGUIDAS (ej. 18:00–20:00 = 2 Reservas del mismo
  /// grupo). Primero verifica que TODAS las horas estén libres (si una está
  /// tomada, no reserva ninguna); luego crea una Reserva por hora con su precio
  /// propio (respeta valle/descuento por hora) y un `grupoReservaId` compartido
  /// para mostrarlas como un solo bloque en "Mis reservas". [conSena] cobra la
  /// seña por hora (% de cada hora). Los [extras] se cargan una sola vez.
  Future<ResultadoReserva> agregarReservasJugadorMulti(
      Cancha cancha, String fecha, String diaLabel, List<String> horas,
      {Deporte? deporte,
      List<ServicioExtra> extras = const [],
      String cobro = 'ninguno',
      bool conSena = false}) async {
    if (horas.isEmpty) return ResultadoReserva.error;
    final ordenadas = [...horas]..sort();
    // Pre-chequeo: TODAS deben estar libres (atómico local). Si una está tomada,
    // no reservo nada (evita medias reservas). Cada slot se compara con su FECHA
    // REAL (los de madrugada caen en el día siguiente).
    for (final h in ordenadas) {
      final fh = cancha.fechaRealSlot(fecha, h);
      final ocupada = reservas.any((r) =>
          r.canchaId == cancha.id && r.fecha == fh && r.horaInicio == h);
      if (ocupada) return ResultadoReserva.ocupado;
    }
    // Grupo solo si son 2+ horas (una sola hora se guarda como reserva suelta).
    final grupo = ordenadas.length > 1
        ? 'grp_${DateTime.now().millisecondsSinceEpoch}'
        : '';
    var peor = ResultadoReserva.ok;
    for (var i = 0; i < ordenadas.length; i++) {
      final h = ordenadas[i];
      final fh = cancha.fechaRealSlot(fecha, h); // fecha real del slot
      final senaSlot = conSena && cancha.senaPct > 0
          ? (precioSlotEfectivo(cancha, fh, h) * cancha.senaPct / 100).round()
          : 0;
      final res = await agregarReservaJugador(
        cancha, fh, diaLabel, h,
        deporte: deporte,
        // Los servicios extra (árbitro/pelotero…) se cobran una sola vez.
        extras: i == 0 ? extras : const [],
        cobro: cobro,
        sena: senaSlot,
        grupoReservaId: grupo,
        // El aviso al dueño se manda UNA sola vez para todo el bloque (abajo),
        // no una vez por hora.
        notificarDueno: false,
      );
      if (res == ResultadoReserva.ocupado) return ResultadoReserva.ocupado;
      if (res != ResultadoReserva.ok) peor = res; // sinConexion / error
    }
    // Todo el bloque quedó confirmado en el servidor → un solo aviso al dueño con
    // el rango completo. Si algo quedó offline, el aviso lo manda el reintento.
    if (peor == ResultadoReserva.ok) {
      final delGrupo = grupo.isNotEmpty
          ? reservas.where((r) => r.grupoReservaId == grupo).toList()
          : reservas
              .where((r) =>
                  r.canchaId == cancha.id &&
                  ordenadas.contains(r.horaInicio) &&
                  r.fecha == cancha.fechaRealSlot(fecha, r.horaInicio))
              .toList();
      if (delGrupo.isNotEmpty) _notificarDuenoReserva(cancha, delGrupo);
    }
    return peor;
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
    String clienteEmail = '',
    bool pagado = false,
    int? precioOverride,
    Deporte? deporte,
  }) async {
    // Fecha REAL del slot (los de madrugada caen en el día siguiente).
    final fechaReal = cancha.fechaRealSlot(fecha, hora);
    final yaLocal = reservas.any((r) =>
        r.canchaId == cancha.id && r.fecha == fechaReal && r.horaInicio == hora);
    if (yaLocal) return ResultadoReserva.ocupado;

    final precio = precioOverride ?? precioSlotEfectivo(cancha, fechaReal, hora);
    final nombre = nombreCliente.trim();
    final reserva = Reserva(
      id: 'man_${DateTime.now().millisecondsSinceEpoch}_${_contadorJugador++}',
      canchaId: cancha.id,
      jugador: nombre.isEmpty ? 'Cliente' : nombre,
      nivel: '',
      fecha: fechaReal,
      dia: diaLabel,
      horaInicio: hora,
      horaFin: cancha.horaFinDe(hora),
      estado: EstadoReserva.confirmada,
      traidaPorApp: false, // CLIENTE PROPIO del dueño → fuera de comisión
      precio: precio,
      sena: 0,
      pagado: pagado,
      // El cliente debe ser un usuario registrado del app: ligamos la reserva a
      // su cuenta para que también la vea en su app (y cuente en su historial).
      usuario: clienteEmail.trim().toLowerCase(),
      deporte: (deporte ?? cancha.deporte).name,
      moneda: cancha.monedaSimbolo,
      telefono: telefono.trim(),
      medioPago: 'manual', // reserva del dueño (cliente propio, fuera de la app)
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
    // Push al JUGADOR: "te reservaron" (pedido del director — antes la reserva
    // manual no le avisaba nada a su cuenta). Fire-and-forget, fail-safe.
    _avisarReservaManual(reserva, cancha);
    notifyListeners();
    _persistirDatos();
    return res == ResultadoReserva.ok ? ResultadoReserva.ok : res;
  }

  /// Notifica al CLIENTE (usuario registrado del app) que el dueño le creó una
  /// reserva manual, vía la Edge Function `push-aviso` (invocación directa,
  /// misma que usa el diagnóstico — no depende de webhooks). Fail-safe: si no
  /// hay email, no hay red o la función no está, la reserva queda igual.
  void _avisarReservaManual(Reserva r, Cancha cancha) {
    final email = r.usuario;
    if (email.isEmpty || !SupabaseService.disponible) return;
    // El dueño anotándose a sí mismo no necesita push.
    if (email == (usuario?.email ?? '').trim().toLowerCase()) return;
    () async {
      try {
        final lugar = cancha.club.isNotEmpty ? cancha.club : cancha.nombre;
        await SupabaseService.client.functions.invoke('push-aviso', body: {
          'email': email,
          'titulo': 'Reserva confirmada 🎾',
          'cuerpo': '$lugar te reservó ${cancha.nombre} · ${r.dia} '
              '${r.horaInicio}–${r.horaFin}. ¡Te esperamos!',
          'tipo': 'reserva_manual',
          'data': {'reserva_id': r.id, 'cancha_id': r.canchaId},
        });
      } catch (_) {}
    }();
  }

  /// El dueño confirma (o revierte) que el jugador pagó en efectivo en la cancha.
  Future<void> marcarPago(Reserva r, {bool pagado = true}) async {
    final upd = r.copyWith(pagado: pagado);
    _reemplazarReserva(upd);
    notifyListeners();
    _persistirDatos();
    ReservasRepo.actualizar(upd); // best-effort
    // Ya cobró → no hace falta el recordatorio de "cobra en efectivo".
    if (pagado) RecordatorioService.cancelar(r.id);
  }

  // ── CAJA DEL DÍA (dueño) ──────────────────────────────────────────────────
  /// ISO 'YYYY-MM-DD' de una fecha.
  String isoDe(DateTime d) =>
      '${d.year.toString().padLeft(4, '0')}-'
      '${d.month.toString().padLeft(2, '0')}-'
      '${d.day.toString().padLeft(2, '0')}';

  /// Reservas del día [iso] de las canchas del dueño (excluye no-shows).
  List<Reserva> reservasDelDiaDueno(String iso) {
    return reservas
        .where((r) =>
            r.fecha == iso &&
            r.estado != EstadoReserva.noShow &&
            miCanchaDeReserva(r.canchaId) != null)
        .toList()
      ..sort((a, b) => a.horaInicio.compareTo(b.horaInicio));
  }

  /// Caja del día: cobrado, por cobrar (con extras), reservas y % ocupación.
  ({int cobrado, int porCobrar, int reservas, int ocupacion}) cajaDia(
      String iso) {
    final list = reservasDelDiaDueno(iso);
    var cobrado = 0, porCobrar = 0;
    for (final r in list) {
      // Reserva canjeada con BONO: cuenta para ocupación (sigue en `list`) pero
      // NO suma dinero hoy (ya se cobró al comprar el bono → evita doble conteo).
      if (r.esBono) continue;
      final t = r.totalConExtras.round();
      if (r.pagado) {
        cobrado += t;
      } else {
        // La seña ya se pagó por adelantado (online): cuenta como cobrada y solo
        // queda por cobrar el resto en efectivo en la cancha.
        final sena = r.sena.clamp(0, t);
        cobrado += sena;
        porCobrar += t - sena;
      }
    }
    final slots = misCanchas.fold<int>(0, (s, c) => s + c.horariosSlots().length);
    final ocupacion = slots == 0 ? 0 : (list.length * 100) ~/ slots;
    return (
      cobrado: cobrado,
      porCobrar: porCobrar,
      reservas: list.length,
      ocupacion: ocupacion
    );
  }

  // Cierres de caja (arqueo por día). Se persisten local.
  final List<CierreCaja> cierresCaja = [];

  /// Cierre de un día (null si aún no se cerró).
  CierreCaja? cierreDe(String iso) {
    for (final c in cierresCaja) {
      if (c.fecha == iso) return c;
    }
    return null;
  }

  /// Cierra (o recierra) la caja del día: guarda la foto de cobrado/por cobrar.
  /// [automatico] = lo cerró el sistema (respaldo, sin confirmar); el default
  /// (false) es el arqueo CONFIRMADO por el dueño (o al confirmar un auto-cierre).
  void cerrarCaja(String iso, {bool automatico = false}) {
    final c = cajaDia(iso);
    cierresCaja.removeWhere((x) => x.fecha == iso);
    cierresCaja.insert(
        0,
        CierreCaja(
          fecha: iso,
          cobrado: c.cobrado,
          porCobrar: c.porCobrar,
          reservas: c.reservas,
          cerradaEn: DateTime.now(),
          automatico: automatico,
        ));
    notifyListeners();
    _persistirDatos();
  }

  /// Reabre la caja de un día (borra su cierre) para que el dueño la revise y la
  /// vuelva a cerrar/confirmar.
  void reabrirCaja(String iso) {
    cierresCaja.removeWhere((x) => x.fecha == iso);
    notifyListeners();
    _persistirDatos();
  }

  /// CIERRE AUTOMÁTICO DE RESPALDO: si el dueño no cerró un día con actividad, el
  /// sistema le genera una foto marcada como "automática (sin confirmar)" para no
  /// dejar el historial vacío. Ventana prudente: solo cierra días ANTERIORES a la
  /// fecha de corte (hoy, o AYER si aún no son las 3 a.m.), para dar margen a
  /// canchas nocturnas y a marcar el efectivo tardío. Nunca toca el día en curso
  /// ni un día ya cerrado por el dueño. Se llama al abrir "Mis canchas"/caja y al
  /// sincronizar. Idempotente.
  void autocerrarCajasPendientes() {
    if (misCanchas.isEmpty) return;
    final ahora = DateTime.now();
    // Corte: hasta ayer normalmente; si aún no son las 3 a.m., ayer sigue "vivo"
    // y el corte baja a anteayer.
    var corte = DateTime(ahora.year, ahora.month, ahora.day);
    if (ahora.hour < 3) corte = corte.subtract(const Duration(days: 1));
    // Días CON actividad del dueño (fechas distintas de sus reservas activas).
    final misIds = misCanchas.map((c) => c.id).toSet();
    final dias = <String>{};
    for (final r in reservas) {
      if (r.estado == EstadoReserva.noShow) continue;
      if (!misIds.contains(r.canchaId)) continue;
      dias.add(r.fecha);
    }
    var cambio = false;
    for (final iso in dias) {
      final d = DateTime.tryParse(iso);
      if (d == null) continue;
      final dd = DateTime(d.year, d.month, d.day);
      if (!dd.isBefore(corte)) continue; // día en curso / dentro del margen
      if (cierreDe(iso) != null) continue; // ya cerrado (manual o auto)
      final c = cajaDia(iso);
      cierresCaja.insert(
          0,
          CierreCaja(
            fecha: iso,
            cobrado: c.cobrado,
            porCobrar: c.porCobrar,
            reservas: c.reservas,
            cerradaEn: ahora,
            automatico: true,
          ));
      cambio = true;
    }
    if (cambio) {
      notifyListeners();
      _persistirDatos();
    }
  }

  // ── ANTI NO-SHOW: recordatorio de reserva al jugador ──────────────────────
  // Reservas ya recordadas (por id) para no repetir el aviso. Se persiste.
  final Set<String> _reservasRecordadas = {};

  bool reservaRecordada(String id) => _reservasRecordadas.contains(id);

  void marcarReservaRecordada(String id) {
    _reservasRecordadas.add(id);
    notifyListeners();
    _persistirDatos();
  }

  // ── RESERVAS FIJAS / "pensionados" (dueño) ────────────────────────────────
  final List<ReservaFija> reservasFijas = [];

  /// Reservas fijas de las canchas del dueño (todas las que administra).
  List<ReservaFija> get misReservasFijas {
    final ids = misCanchas.map((c) => c.id).toSet();
    return reservasFijas.where((f) => ids.contains(f.canchaId)).toList();
  }

  /// Crea una reserva fija y genera de una vez sus próximas ocurrencias.
  Future<void> agregarReservaFija({
    required String canchaId,
    required int diaSemana,
    required String hora,
    required String clienteNombre,
    String clienteEmail = '',
    String clienteTelefono = '',
  }) async {
    reservasFijas.add(ReservaFija(
      id: 'fija_${DateTime.now().microsecondsSinceEpoch}',
      canchaId: canchaId,
      diaSemana: diaSemana,
      hora: hora,
      clienteNombre: clienteNombre.trim(),
      clienteEmail: clienteEmail.trim().toLowerCase(),
      clienteTelefono: clienteTelefono.trim(),
    ));
    notifyListeners();
    _persistirDatos();
    await generarReservasFijas();
  }

  /// Pausa/activa una reserva fija (deja de generar sin borrar el registro).
  void pausarReservaFija(String id, bool activo) {
    final i = reservasFijas.indexWhere((f) => f.id == id);
    if (i < 0) return;
    reservasFijas[i] = reservasFijas[i].copyWith(activo: activo);
    notifyListeners();
    _persistirDatos();
  }

  /// Elimina la reserva fija (no borra las reservas ya generadas).
  void quitarReservaFija(String id) {
    reservasFijas.removeWhere((f) => f.id == id);
    notifyListeners();
    _persistirDatos();
  }

  /// GENERA las reservas de las próximas [semanas] ocurrencias de cada fija
  /// activa (idempotente: no duplica si el slot ya está reservado). Llamar al
  /// abrir el panel del dueño.
  Future<void> generarReservasFijas({int semanas = 4}) async {
    final hoy = DateTime.now();
    final base = DateTime(hoy.year, hoy.month, hoy.day);
    for (final f in reservasFijas.where((x) => x.activo)) {
      Cancha? cancha;
      for (final c in misCanchas) {
        if (c.id == f.canchaId) {
          cancha = c;
          break;
        }
      }
      if (cancha == null) continue;
      // Día de esta semana (o el mismo día si es hoy) + próximas semanas.
      final delta = (f.diaSemana - base.weekday) % 7;
      for (var w = 0; w < semanas; w++) {
        final fecha = base.add(Duration(days: delta + w * 7));
        final iso = isoDe(fecha);
        final ocupado = reservas.any((r) =>
            r.canchaId == f.canchaId &&
            r.fecha == iso &&
            r.horaInicio == f.hora);
        if (ocupado) continue;
        await agregarReservaManual(
          cancha,
          iso,
          _diaLabelDe(fecha),
          f.hora,
          nombreCliente: f.clienteNombre,
          telefono: f.clienteTelefono,
          clienteEmail: f.clienteEmail,
        );
      }
    }
  }

  /// Etiqueta de día para una fecha (Hoy/Mañana/ISO), coherente con la agenda.
  String _diaLabelDe(DateTime fecha) {
    final hoy = DateTime.now();
    final base = DateTime(hoy.year, hoy.month, hoy.day);
    final d = DateTime(fecha.year, fecha.month, fecha.day);
    final diff = d.difference(base).inDays;
    if (diff == 0) return 'Hoy';
    if (diff == 1) return 'Mañana';
    return isoDe(fecha);
  }

  /// El JUGADOR cancela / elimina una de sus reservas (próxima o del historial).
  /// La quita de sus listas y de la del dueño, libera el slot en la agenda y la
  /// borra de Supabase (best-effort) para que el horario vuelva a estar libre y
  /// no reaparezca al sincronizar.
  Future<void> cancelarReserva(Reserva r) async {
    // Reserva de varias horas seguidas: cancelar el bloque cancela TODAS sus
    // horas (mismo grupo). Una hora suelta solo se cancela a sí misma.
    final grupo = r.grupoReservaId.isNotEmpty
        ? reservas.where((x) => x.grupoReservaId == r.grupoReservaId).toList()
        : [r];
    final ids = grupo.map((x) => x.id).toSet();
    // Captura los slots que se liberan (para avisar a la lista de espera).
    final liberados = [
      for (final x in grupo)
        (canchaId: x.canchaId, fecha: x.fecha, hora: x.horaInicio)
    ];
    misReservas.removeWhere((x) => ids.contains(x.id));
    reservas.removeWhere((x) => ids.contains(x.id));
    for (final id in ids) {
      final i = agenda.indexWhere((b) => b.reservaId == id);
      if (i >= 0) {
        agenda[i] = agenda[i].copyWith(limpiarReserva: true, disponible: true);
      }
    }
    notifyListeners();
    _persistirDatos();
    for (final id in ids) {
      await ReservasRepo.eliminar(id); // libera cada slot en la nube
    }
    // Push AUTOMÁTICO a quienes esperaban esa hora (waitlist): reusa el canal
    // genérico de avisos (pichangol_avisos → push-aviso), sin deploy nuevo.
    _avisarEsperaLiberada(liberados);
  }

  /// Notifica a la lista de espera de cada slot recién liberado. Consulta la
  /// cola FRESCA de Supabase (la caché puede no estar cargada si se cancela
  /// desde "Mis reservas") y encola un push por jugador. Best-effort.
  Future<void> _avisarEsperaLiberada(
      List<({String canchaId, String fecha, String hora})> slots) async {
    if (slots.isEmpty) return;
    final yo = usuario?.email.trim().toLowerCase() ?? '';
    final canchaIds = slots.map((s) => s.canchaId).toSet().toList();
    final cola = await EsperaRepo.deCanchas(canchaIds);
    if (cola.isEmpty) return;
    for (final s in slots) {
      final esperan = cola.where((e) =>
          e.canchaId == s.canchaId &&
          e.fecha == s.fecha &&
          e.hora == s.hora &&
          e.usuario.trim().toLowerCase() != yo);
      for (final e in esperan) {
        AvisosService.enviar(
          email: e.usuario,
          titulo: '¡Se liberó tu hora! ⏰',
          cuerpo:
              'Las ${s.hora} que esperabas quedaron libres. Entra y resérvalas '
              'antes de que las tomen.',
          tipo: 'espera',
          data: {
            'accion': 'espera_libre',
            'cancha_id': s.canchaId,
            'fecha': s.fecha,
            'hora': s.hora,
          },
        );
      }
    }
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
