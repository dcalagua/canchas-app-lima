import 'dart:convert';
import 'dart:math' as math;

import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../data/canchas_repo.dart';
import '../data/reservas_repo.dart';
import '../data/sample_data.dart';
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
  bool descubriendo = false; // true mientras se traen canchas cercanas (feedback UI)

  /// Todas las canchas (descubiertas + semilla + remotas + locales), sin duplicar
  /// por id. Las registradas se ponen después para que ganen ante una colisión.
  List<Cancha> todasLasCanchas() {
    final map = <String, Cancha>{};
    for (final c in canchasDescubiertas) {
      map[c.id] = c;
    }
    for (final c in SampleData.canchas) {
      map[c.id] = c;
    }
    for (final c in canchasRemotas) {
      map[c.id] = c;
    }
    for (final c in canchasExtra) {
      map[c.id] = c;
    }
    canchasEliminadas.forEach(map.remove); // borrados durables
    return _dedupPorLugar(map.values.toList());
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
      final rapidas = await PlacesService.canchasCerca(centro, conFotos: false);
      _agregarDescubiertas(rapidas);
    } catch (_) {
      // fail-safe: si Places no responde, no cambia nada
    } finally {
      descubriendo = false;
      notifyListeners();
    }
    // Fase 2: vuelve a pedir CON fotos y las pinta encima (segundo plano).
    try {
      final conFotos =
          await PlacesService.canchasCerca(centro, conFotos: true);
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
    // Candidatas: TODAS mis canchas reclamadas (registradas, no eliminadas). Se
    // consultan en ambos sentidos: promover (aprobada → verificada) y degradar
    // (rechazada → deja de estar verificada, se quitan las reservas).
    final candidatas = [
      for (final c in misCanchas)
        if (c.registrada && !canchasEliminadas.contains(c.id)) c,
    ];
    for (final c in candidatas) {
      final est =
          await PropiedadService.estado(c.id, solicitante: usuario?.email);
      if (est == null || est['existe'] != true) continue;
      final verificada =
          est['verificada'] == true || est['estado'] == 'activada';
      final rechazada = est['estado'] == 'rechazada';

      Cancha? actualizada;
      if (verificada && !c.verificada) {
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
    return map.values.toList();
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

      notifyListeners();
      // Trae la disponibilidad compartida (reservas de otros dispositivos) para
      // que el anti-doble-reserva y el panel del dueño arranquen al día. Best-effort.
      cargarReservasRemotas();
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
