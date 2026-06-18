import 'package:flutter_test/flutter_test.dart';

import 'package:canchas_lima/data/sample_data.dart';
import 'package:canchas_lima/state/app_state.dart';
import 'package:canchas_lima/models/models.dart';

void main() {
  test('el club activo tiene canchas', () {
    expect(SampleData.canchasDelClubActivo().isNotEmpty, true);
  });

  test('simular reserva entrante agrega una reserva nueva por la app', () {
    final state = AppState();
    final antes = state.reservas.length;
    final res = state.simularReservaEntrante();
    expect(res, isNotNull);
    expect(state.reservas.length, antes + 1);
    expect(state.reservas.first.traidaPorApp, true);
    expect(state.reservas.first.estado, EstadoReserva.nueva);
  });
}
