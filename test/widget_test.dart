import 'package:canchas_lima/models/models.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart';

void main() {
  group('deportes activos desde la torre (A1)', () {
    tearDown(() => aplicarDeportesActivos([for (final d in deportesActivosBase) d.name]));

    test('aplica en el orden de la torre, sin repetidos ni desconocidos', () {
      expect(aplicarDeportesActivos(['padel', 'futbol', 'xxx', 'padel']), isTrue);
      expect(deportesActivos, [Deporte.padel, Deporte.futbol]);
    });

    test('nunca deja la lista vacía ni acepta natación (no es de cancha)', () {
      expect(aplicarDeportesActivos(['natacion', 'nada']), isFalse);
      expect(deportesActivos, isNotEmpty);
      expect(aplicarDeportesActivos(null), isFalse);
    });

    test('la misma lista no cuenta como cambio', () {
      expect(aplicarDeportesActivos([for (final d in deportesActivosBase) d.name]), isFalse);
    });
  });

  test('reglas de reserva viajan en la cancha (solo lectura)', () {
    const base = Cancha(
      id: 'c1', nombre: 'C', club: 'Club', distrito: Distrito.sanBorja, deporte: Deporte.futbol,
      precioHora: 60, ubicacion: LatLng(-12.1, -77.0), clubFundador: false, digitalizada: true,
    );
    expect(base.tieneReglas, isFalse);
    final j = base.toJson()..['reglasReserva'] = {'cancelacion_horas': 24};
    final c = Cancha.fromJson(j);
    expect(c.tieneReglas, isTrue);
    expect(c.reglasReserva['cancelacion_horas'], 24);
    expect(c.copyWith(nombre: 'Otra').reglasReserva, c.reglasReserva);
  });
}
