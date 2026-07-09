import 'package:google_maps_flutter/google_maps_flutter.dart';

import '../models/models.dart';

/// Datos de demostración en memoria (sin backend todavía).
/// Pensados para la DEMO en la cancha: el dueño toca el panel y "ve entrar una reserva".
///
/// El club que inicia sesión es "Club Raqueta San Borja" y administra sus propias
/// canchas. El resto pueblan el mapa del explorador.
class SampleData {
  static const String clubActivo = 'Club Raqueta San Borja';

  /// Clubes SEMBRADOS del piloto: lugares reales que Google no siempre devuelve
  /// en la búsqueda de texto (indexación pobre en la zona). Se inyectan como
  /// "descubiertos" (reclamables) para que aparezcan siempre en el corredor de
  /// Chosica, sin depender de Places. Al reclamarlos, la versión registrada los
  /// reemplaza (dedup por ubicación).
  static const List<Cancha> sembradas = [
    Cancha(
      id: 'seed_regatas_chosica',
      nombre: 'Club de Regatas Lima – Chosica',
      club: 'Club de Regatas Lima – Chosica',
      distrito: Distrito.laMolina, // referencial (Chosica no está en el enum)
      deporte: Deporte.futbol, // genérico; el dueño precisa al reclamar
      precioHora: 0,
      ubicacion: LatLng(-11.950372837472894, -76.7055048427175),
      clubFundador: false,
      digitalizada: false,
      direccion: 'Carretera Central, Lurigancho-Chosica',
      registrada: false, // reclamable, como un lugar descubierto
      verificada: false, // aún no reclamada → no verificada
    ),
    Cancha(
      id: 'seed_esmon',
      nombre: 'ESMON',
      club: 'ESMON',
      distrito: Distrito.laMolina,
      deporte: Deporte.tenis, // clubes que alquilan a academias (tenis/fútbol)
      precioHora: 0,
      ubicacion: LatLng(-11.943985233021179, -76.71577897498123),
      clubFundador: false,
      digitalizada: false,
      direccion: 'Lurigancho-Chosica',
      registrada: false,
      verificada: false,
    ),
    Cancha(
      id: 'seed_ceande',
      nombre: 'CEANDE',
      club: 'CEANDE',
      distrito: Distrito.laMolina,
      deporte: Deporte.tenis,
      precioHora: 0,
      ubicacion: LatLng(-11.959962965453006, -76.72790551915534),
      clubFundador: false,
      digitalizada: false,
      direccion: 'Lurigancho-Chosica',
      registrada: false,
      verificada: false,
    ),
  ];

  static const List<Cancha> canchas = [
    // --- Canchas del club que inicia sesión (panel del dueño) ---
    Cancha(
      id: 'c1', nombre: 'Cancha Central', club: clubActivo,
      distrito: Distrito.sanBorja, deporte: Deporte.tenis, precioHora: 70,
      ubicacion: LatLng(-12.1086, -76.9990), clubFundador: true, digitalizada: true,
    ),
    Cancha(
      id: 'c2', nombre: 'Cancha 2 (Arcilla)', club: clubActivo,
      distrito: Distrito.sanBorja, deporte: Deporte.tenis, precioHora: 65,
      ubicacion: LatLng(-12.1090, -76.9985), clubFundador: true, digitalizada: true,
    ),

    // --- Otras canchas de la zona piloto (pipeline / mapa del explorador) ---
    Cancha(
      id: 'c4', nombre: 'Cancha Tenis Aurora', club: 'Club Aurora',
      distrito: Distrito.sanBorja, deporte: Deporte.tenis, precioHora: 60,
      ubicacion: LatLng(-12.1110, -77.0020), clubFundador: false, digitalizada: false,
    ),
    Cancha(
      id: 'c6', nombre: 'Cancha 1 - Los Cedros', club: 'Club Los Cedros',
      distrito: Distrito.surco, deporte: Deporte.tenis, precioHora: 68,
      ubicacion: LatLng(-12.1402, -76.9880), clubFundador: false, digitalizada: false,
    ),
    Cancha(
      id: 'c8', nombre: 'Tenis La Planicie', club: 'La Planicie Tenis',
      distrito: Distrito.laMolina, deporte: Deporte.tenis, precioHora: 75,
      ubicacion: LatLng(-12.0760, -76.9410), clubFundador: false, digitalizada: false,
    ),

    // --- Fútbol sintético (nuevo deporte) ---
    Cancha(
      id: 'f1', nombre: 'Grass Sintético San Borja', club: 'Complejo La Bombonera',
      distrito: Distrito.sanBorja, deporte: Deporte.futbol, precioHora: 120,
      ubicacion: LatLng(-12.1075, -77.0008), clubFundador: false, digitalizada: false,
    ),
    Cancha(
      id: 'f2', nombre: 'Fútbol 7 Surco', club: 'Surco Sport Center',
      distrito: Distrito.surco, deporte: Deporte.futbol, precioHora: 140,
      ubicacion: LatLng(-12.1380, -76.9905), clubFundador: false, digitalizada: false,
    ),
    Cancha(
      id: 'f3', nombre: 'Cancha Sintética La Molina', club: 'Molina Fútbol Club',
      distrito: Distrito.laMolina, deporte: Deporte.futbol, precioHora: 150,
      ubicacion: LatLng(-12.0785, -76.9425), clubFundador: false, digitalizada: false,
    ),
    Cancha(
      id: 'f4', nombre: 'Mini Fútbol El Polo', club: 'El Polo Grass',
      distrito: Distrito.surco, deporte: Deporte.futbol, precioHora: 130,
      ubicacion: LatLng(-12.1085, -76.9760), clubFundador: false, digitalizada: false,
    ),
  ];

  /// Centro aproximado del eje piloto San Borja–Surco–La Molina.
  static const LatLng centroPiloto = LatLng(-12.108, -76.978);

  static const List<Reserva> reservas = [
    Reserva(
      id: 'r1', canchaId: 'c1', jugador: 'Carlos Mendoza', nivel: 'Intermedio 3.5',
      dia: 'Hoy', horaInicio: '07:00', horaFin: '08:00',
      estado: EstadoReserva.confirmada, traidaPorApp: true, precio: 70, sena: 20,
    ),
    Reserva(
      id: 'r2', canchaId: 'c3', jugador: 'Lucía Ferrer', nivel: 'Avanzado',
      dia: 'Hoy', horaInicio: '09:00', horaFin: '10:00',
      estado: EstadoReserva.nueva, traidaPorApp: true, precio: 90, sena: 25,
    ),
    Reserva(
      id: 'r3', canchaId: 'c2', jugador: 'Equipo Galván (de siempre)', nivel: '—',
      dia: 'Hoy', horaInicio: '18:00', horaFin: '19:00',
      estado: EstadoReserva.confirmada, traidaPorApp: false, precio: 65, sena: 0,
    ),
    Reserva(
      id: 'r4', canchaId: 'c1', jugador: 'Andrea Salas', nivel: 'Intermedio 4.0',
      dia: 'Mañana', horaInicio: '08:00', horaFin: '09:00',
      estado: EstadoReserva.nueva, traidaPorApp: true, precio: 70, sena: 20,
    ),
    Reserva(
      id: 'r5', canchaId: 'c3', jugador: 'Diego Rojas', nivel: 'Principiante',
      dia: 'Mañana', horaInicio: '10:00', horaFin: '11:00',
      estado: EstadoReserva.confirmada, traidaPorApp: true, precio: 90, sena: 25,
    ),
    Reserva(
      id: 'r6', canchaId: 'c2', jugador: 'Marta Pinto', nivel: 'Intermedio 3.0',
      dia: 'Ayer', horaInicio: '07:00', horaFin: '08:00',
      estado: EstadoReserva.completada, traidaPorApp: true, precio: 65, sena: 20,
    ),
    Reserva(
      id: 'r7', canchaId: 'c1', jugador: 'Jorge Li', nivel: 'Avanzado',
      dia: 'Ayer', horaInicio: '20:00', horaFin: '21:00',
      estado: EstadoReserva.noShow, traidaPorApp: true, precio: 70, sena: 20,
    ),
  ];

  static List<Cancha> canchasDelClubActivo() =>
      canchas.where((c) => c.club == clubActivo).toList();

  static Cancha? canchaPorId(String id) {
    for (final c in canchas) {
      if (c.id == id) return c;
    }
    return null;
  }

  static Reserva? reservaPorId(String id) {
    for (final r in reservas) {
      if (r.id == id) return r;
    }
    return null;
  }

  /// Agenda de HOY para las canchas del club activo. Mañanas = horas valle.
  static List<BloqueHorario> agendaHoy() {
    const horas = [
      '07:00', '08:00', '09:00', '10:00', '11:00',
      '16:00', '17:00', '18:00', '19:00', '20:00',
    ];
    final ocupadasHoy = reservas.where((r) => r.dia == 'Hoy').toList();
    final bloques = <BloqueHorario>[];
    for (final cancha in canchasDelClubActivo()) {
      for (final hora in horas) {
        final esValle = hora.compareTo('12:00') < 0;
        Reserva? reserva;
        for (final r in ocupadasHoy) {
          if (r.canchaId == cancha.id && r.horaInicio == hora) {
            reserva = r;
            break;
          }
        }
        bloques.add(BloqueHorario(
          canchaId: cancha.id,
          hora: hora,
          esHoraValle: esValle,
          disponible: true,
          reservaId: reserva?.id,
        ));
      }
    }
    return bloques;
  }
}
