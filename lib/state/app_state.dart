import 'dart:convert';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../data/academias_repo.dart';
import '../data/campeonatos_repo.dart';
import '../data/canchas_repo.dart';
import '../data/matriculas_repo.dart';
import '../data/reservas_repo.dart';
import '../data/sample_data.dart';
import '../models/academia.dart';
import '../models/campeonato.dart';
import '../models/models.dart';
import '../models/usuario.dart';
import '../services/auth_service.dart';
import '../services/places_service.dart';
import '../services/verificacion_service.dart';
import '../services/growth_service.dart';
import '../services/propiedad_service.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart';

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

  final List<Reserva> reservas = List.of(SampleData.reservas);
  final List<BloqueHorario> agenda = List.of(SampleData.agendaHoy());
  final List<Reserva> misReservas = []; // reservas del jugador logueado
  final List<Cancha> canchasExtra = []; // canchas registradas en este dispositivo
  final List<Cancha> canchasRemotas = []; // canchas traídas de Supabase
  final List<Cancha> canchasDescubiertas = []; // reales de Google Places (sin registrar)
  // IDs de canchas que el dueño eliminó: se respetan SIEMPRE, aunque Supabase
  // vuelva a devolverlas (borrado durable en el dispositivo).
  final Set<String> canchasEliminadas = {};

  // ── Academias (Fase 1) ────────────────────────────────────────────────────
  final List<Academia> academias = [];
  final List<Alumno> alumnos = [];
  final List<Cuota> cuotas = [];
  final List<Asistencia> asistencias = [];

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
  void guardarAcademia(Academia a) {
    final i = academias.indexWhere((x) => x.id == a.id);
    if (i >= 0) {
      academias[i] = a;
    } else {
      academias.add(a);
    }
    notifyListeners();
    _persistirDatos();
    AcademiasRepo.guardar(a); // best-effort: comparte y sobrevive reinstalación
  }

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
  Future<void> cargarAcademiasRemotas() async {
    final remotas = await AcademiasRepo.fetchRemotas();
    if (remotas.isEmpty) return;
    var cambio = false;
    for (final a in remotas) {
      final i = academias.indexWhere((x) => x.id == a.id);
      if (i >= 0) {
        academias[i] = a;
      } else {
        academias.add(a);
      }
      cambio = true;
    }
    if (cambio) {
      notifyListeners();
      _persistirDatos();
    }
  }

  List<Alumno> alumnosDe(String academiaId) =>
      alumnos.where((a) => a.academiaId == academiaId).toList();

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
    if (misAcademiaIds.isNotEmpty) {
      remotas.addAll(await MatriculasRepo.deAcademias(misAcademiaIds));
    }
    if (u != null) {
      remotas.addAll(await MatriculasRepo.deAlumno(u.email));
    }
    if (remotas.isEmpty) return;
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
    if (cambio) {
      notifyListeners();
      _persistirDatos();
    }
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
  void inscribir(Alumno alumno, Plan plan, {DateTime? inicio}) {
    if (plan.tipo == TipoPlan.porClase) return;
    final base = inicio ?? DateTime.now();
    final meses = plan.meses < 1 ? 1 : plan.meses;
    for (var i = 0; i < meses; i++) {
      final venc = DateTime(base.year, base.month + i, base.day);
      cuotas.add(Cuota(
        id: 'cu_${DateTime.now().microsecondsSinceEpoch}_$i',
        academiaId: alumno.academiaId,
        alumnoId: alumno.id,
        concepto: '${plan.nombre} · ${_mesNombre(venc)}',
        monto: plan.precioMes,
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
  }) {
    final n = cantidad < 1 ? 1 : cantidad;
    final alumno = Alumno(
      id: 'al_${DateTime.now().microsecondsSinceEpoch}',
      academiaId: academiaId,
      nombre: nombre,
      whatsapp: whatsapp,
      email: usuario?.email ?? '', // si hay sesión, queda como alumno-app
      fotoUrl: usuario?.fotoUrl,
    );
    alumnos.add(alumno);
    MatriculasRepo.guardar(alumno); // cross-device + sobrevive reinstalar
    final hoy = DateTime.now();
    if (plan.tipo == TipoPlan.porClase) {
      cuotas.add(Cuota(
        id: 'cu_${hoy.microsecondsSinceEpoch}',
        academiaId: academiaId,
        alumnoId: alumno.id,
        concepto:
            '$n clase${n == 1 ? '' : 's'} particular${n == 1 ? '' : 'es'} · ${plan.nombre}',
        monto: plan.precioMes * n,
        vencimiento: hoy,
        pagada: true,
      ));
    } else {
      final meses = (plan.tipo == TipoPlan.mensual ? 1 : plan.meses) * n;
      for (var i = 0; i < meses; i++) {
        final venc = DateTime(hoy.year, hoy.month + i, hoy.day);
        cuotas.add(Cuota(
          id: 'cu_${hoy.microsecondsSinceEpoch}_$i',
          academiaId: academiaId,
          alumnoId: alumno.id,
          concepto: '${plan.nombre} · ${_mesNombre(venc)}',
          monto: plan.precioMes,
          vencimiento: venc,
          pagada: true,
        ));
      }
    }
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

  void marcarCuotaPagada(String cuotaId, {bool pagada = true}) {
    final i = cuotas.indexWhere((c) => c.id == cuotaId);
    if (i < 0) return;
    cuotas[i] = cuotas[i].copyWith(pagada: pagada);
    notifyListeners();
    _persistirDatos();
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
  ThemeMode temaModo = ThemeMode.system;

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
  final List<MovimientoSaldo> movimientos = [
    const MovimientoSaldo(
        tipo: TipoMovimiento.recarga, monto: 30, concepto: 'Recarga inicial', cuando: 'Ayer'),
  ];
  bool get destacadoActivo => saldoClub > 0;

  /// Comisión que descuenta del saldo cada reserva nueva (5%, mínimo S/ 2).
  int comisionDe(num precio) {
    final c = (precio * 0.05).round();
    return c < 2 ? 2 : c;
  }

  /// Recarga el saldo prepago del club.
  void recargar(int monto) {
    if (monto <= 0) return;
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
  static const _kMovs = 'movimientos_json';
  static const _kMisReservas = 'mis_reservas_json';
  static const _kCanchas = 'canchas_extra_json';
  static const _kEliminadas = 'canchas_eliminadas_json';
  static const _kRadio = 'radio_busqueda_km';
  static const _kTema = 'tema_modo'; // 0=system, 1=light, 2=dark
  static const _kAcademias = 'academias_json';
  static const _kAlumnos = 'alumnos_json';
  static const _kCuotas = 'cuotas_json';
  static const _kAsistencias = 'asistencias_json';
  static const _kCampeonatos = 'campeonatos_json';

  /// Carga la sesión y los datos persistidos (al arrancar la app).
  Future<void> cargarSesion() async {
    try {
      final prefs = await SharedPreferences.getInstance();

      final raw = prefs.getString(_kUsuario);
      if (raw != null) {
        usuario = Usuario.fromJson(jsonDecode(raw) as Map<String, dynamic>);
      }

      if (prefs.containsKey(_kSaldo)) {
        saldoClub = prefs.getInt(_kSaldo) ?? saldoClub;
      }

      if (prefs.containsKey(_kRadio)) {
        radioBusquedaKm = (prefs.getDouble(_kRadio) ?? radioBusquedaKm)
            .clamp(radioMinKm, radioMaxKm)
            .toDouble();
      }

      if (prefs.containsKey(_kTema)) {
        temaModo = switch (prefs.getInt(_kTema)) {
          1 => ThemeMode.light,
          2 => ThemeMode.dark,
          _ => ThemeMode.system,
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
      _cargarLista(prefs, _kAlumnos, alumnos, Alumno.fromJson);
      _cargarLista(prefs, _kCuotas, cuotas, Cuota.fromJson);
      _cargarLista(prefs, _kAsistencias, asistencias, Asistencia.fromJson);
      _cargarLista(prefs, _kCampeonatos, campeonatos, Campeonato.fromJson);

      notifyListeners();
      // Trae la disponibilidad compartida (reservas de otros dispositivos) para
      // que el anti-doble-reserva y el panel del dueño arranquen al día. Best-effort.
      cargarReservasRemotas();
    } catch (_) {}
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
      await prefs.setString(
          _kMovs, jsonEncode(movimientos.map((m) => m.toJson()).toList()));
      await prefs.setString(_kMisReservas,
          jsonEncode(misReservas.map((r) => r.toJson()).toList()));
      await prefs.setString(
          _kCanchas, jsonEncode(canchasExtra.map((c) => c.toJson()).toList()));
      await prefs.setString(
          _kEliminadas, jsonEncode(canchasEliminadas.toList()));
      await prefs.setDouble(_kRadio, radioBusquedaKm);
      await prefs.setInt(_kTema, switch (temaModo) {
        ThemeMode.light => 1,
        ThemeMode.dark => 2,
        ThemeMode.system => 0,
      });
      await prefs.setString(
          _kAcademias, jsonEncode(academias.map((a) => a.toJson()).toList()));
      await prefs.setString(
          _kAlumnos, jsonEncode(alumnos.map((a) => a.toJson()).toList()));
      await prefs.setString(
          _kCuotas, jsonEncode(cuotas.map((c) => c.toJson()).toList()));
      await prefs.setString(_kAsistencias,
          jsonEncode(asistencias.map((a) => a.toJson()).toList()));
      await prefs.setString(_kCampeonatos,
          jsonEncode(campeonatos.map((c) => c.toJson()).toList()));
    } catch (_) {}
  }

  /// Login del jugador con Google. Devuelve true si quedó logueado.
  Future<bool> entrarConGoogle() async {
    final u = await AuthService.entrarConGoogle();
    if (u == null) return false; // canceló
    usuario = u;
    await _persistirUsuario();
    _recomputarMisReservas(); // recupera sus reservas de otros dispositivos
    notifyListeners();
    cargarReservasRemotas(); // best-effort refresco
    return true;
  }

  Future<void> cerrarSesionUsuario() async {
    await AuthService.salir();
    usuario = null;
    misReservas.clear(); // no mezclar reservas entre cuentas
    await _persistirUsuario();
    _persistirDatos();
    notifyListeners();
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
      Cancha cancha, String fecha, String diaLabel, String hora) async {
    // Chequeo local rápido (doble toque / feedback inmediato sin conexión).
    final yaLocal = reservas.any((r) =>
        r.canchaId == cancha.id && r.fecha == fecha && r.horaInicio == hora);
    if (yaLocal) return ResultadoReserva.ocupado;

    final precio = (cancha.precioHora * cancha.duracionSlotMin / 60).round();
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
    return '${cancha.nombre} · ${nueva.horaInicio} · +S/ ${nueva.precio}';
  }

  String _siguienteHora(String hora) {
    final h = int.tryParse(hora.split(':').first);
    if (h == null) return hora;
    return '${(h + 1).toString().padLeft(2, '0')}:00';
  }
}
