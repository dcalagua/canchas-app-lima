import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../data/sample_data.dart';
import '../models/models.dart';
import '../models/usuario.dart';
import '../services/auth_service.dart';

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

  // Saldo prepago del club (modelo inDrive): con saldo aparece destacado y
  // cada reserva nueva descuenta una comisión. Sin saldo, deja de destacarse.
  int saldoClub = 30;
  final List<MovimientoSaldo> movimientos = [
    const MovimientoSaldo(
        tipo: TipoMovimiento.recarga, monto: 30, concepto: 'Recarga inicial', cuando: 'Ayer'),
  ];
  bool get destacadoActivo => saldoClub > 0;

  /// Comisión que descuenta del saldo cada reserva nueva (5%, mínimo S/ 2).
  int comisionDe(int precio) {
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
    } catch (_) {}
  }

  /// Login del jugador con Google. Devuelve true si quedó logueado.
  Future<bool> entrarConGoogle() async {
    final u = await AuthService.entrarConGoogle();
    if (u == null) return false; // canceló
    usuario = u;
    await _persistirUsuario();
    notifyListeners();
    return true;
  }

  Future<void> cerrarSesionUsuario() async {
    await AuthService.salir();
    usuario = null;
    await _persistirUsuario();
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
  /// Aparece como reserva nueva (traída por la app) y, si la cancha es del club
  /// activo, también ocupa el bloque en su agenda.
  Reserva agregarReservaJugador(Cancha cancha, String dia, String hora) {
    final reserva = Reserva(
      id: 'jug${_contadorJugador++}',
      canchaId: cancha.id,
      jugador: usuario?.nombre ?? 'Jugador',
      nivel: 'Intermedio 3.5',
      dia: dia,
      horaInicio: hora,
      horaFin: _siguienteHora(hora),
      estado: EstadoReserva.confirmada,
      traidaPorApp: true,
      precio: cancha.precioHora,
      sena: (cancha.precioHora * 0.3).round(),
    );
    reservas.insert(0, reserva); // visible para el dueño en su panel
    misReservas.insert(0, reserva); // visible para el jugador en "Mis reservas"
    if (dia == 'Hoy') {
      final i = agenda.indexWhere(
          (b) => b.canchaId == cancha.id && b.hora == hora);
      if (i >= 0) agenda[i] = agenda[i].copyWith(reservaId: reserva.id);
    }
    _consumirComision(cancha);
    notifyListeners();
    _persistirDatos();
    return reserva;
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
      precio: cancha.precioHora,
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
