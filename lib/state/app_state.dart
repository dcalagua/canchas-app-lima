import 'package:flutter/foundation.dart';

import '../data/sample_data.dart';
import '../models/models.dart';

/// Instancia única del estado para toda la app (sin paquetes extra de DI).
final AppState appState = AppState();

/// Estado de la app. Sin backend todavía: arranca de [SampleData] y muta en memoria.
/// Pensado para Fase 1 (panel del dueño) + demo en la cancha.
class AppState extends ChangeNotifier {
  bool sesionIniciada = false;
  String nombreClub = SampleData.clubActivo;

  final List<Reserva> reservas = List.of(SampleData.reservas);
  final List<BloqueHorario> agenda = List.of(SampleData.agendaHoy());

  int _contadorDemo = 1;
  int _contadorJugador = 1;

  /// Registra una reserva hecha por un jugador desde el detalle de cancha.
  /// Aparece como reserva nueva (traída por la app) y, si la cancha es del club
  /// activo, también ocupa el bloque en su agenda.
  Reserva agregarReservaJugador(Cancha cancha, String dia, String hora) {
    final reserva = Reserva(
      id: 'jug${_contadorJugador++}',
      canchaId: cancha.id,
      jugador: 'Tú (jugador)',
      nivel: 'Intermedio 3.5',
      dia: dia,
      horaInicio: hora,
      horaFin: _siguienteHora(hora),
      estado: EstadoReserva.confirmada,
      traidaPorApp: true,
      precio: cancha.precioHora,
      sena: (cancha.precioHora * 0.3).round(),
    );
    reservas.insert(0, reserva);
    if (dia == 'Hoy') {
      final i = agenda.indexWhere(
          (b) => b.canchaId == cancha.id && b.hora == hora);
      if (i >= 0) agenda[i] = agenda[i].copyWith(reservaId: reserva.id);
    }
    notifyListeners();
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
    notifyListeners();
    return '${cancha.nombre} · ${nueva.horaInicio} · +S/ ${nueva.precio}';
  }

  String _siguienteHora(String hora) {
    final h = int.tryParse(hora.split(':').first);
    if (h == null) return hora;
    return '${(h + 1).toString().padLeft(2, '0')}:00';
  }
}
