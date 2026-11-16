@Tags(['golden'])
library;

// Goldens de las pantallas NUEVAS del rediseño (cobros del club, bandeja de
// vouchers, reglas de reserva). Regenerar: flutter test --update-goldens test/goldens
import 'package:canchas_lima/models/models.dart';
import 'package:canchas_lima/screens/checkout_directo_screen.dart';
import 'package:canchas_lima/screens/club_pagos_screen.dart';
import 'package:canchas_lima/screens/pagos_por_confirmar_screen.dart';
import 'package:canchas_lima/screens/reglas_reserva_screen.dart';
import 'package:canchas_lima/services/club_pagos_service.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart';

import 'ayuda_golden.dart';

final _vence = DateTime.now().add(const Duration(minutes: 42)).toUtc().toIso8601String();

Future<RespuestaClub> _sim(String metodo, String ruta, Object? cuerpo) async {
  if (ruta == '/club/pagos') {
    return const RespuestaClub(true, {
      'ok': true, 'pais': 'PE', 'moneda': 'PEN', 'medios_permitidos': ['yape', 'plin', 'transferencia'],
      'culqi': {
        'configurada': true, 'activa': true, 'modo': 'test', 'public_key': 'pk_test_abcdefgh12345678',
        'secret_key': 'sk_test_••••9876', 'verificada': true,
        'webhook_url': 'https://www.canchalibre.pe/pagos/culqi/webhook/club/wh_Xy12',
      },
      'medios': [
        {'tipo': 'yape', 'etiqueta': 'Yape', 'titular': 'Club Raqueta SAC', 'numero': '987654321'},
        {'tipo': 'transferencia', 'etiqueta': 'Transferencia bancaria', 'titular': 'Club Raqueta SAC',
         'banco': 'BCP', 'cuenta': '191-1234567-0-12', 'cci': '00219100123456701254'},
      ],
      'comision': {'deuda_centimos': 600, 'suspendido': false, 'tope_centimos': 5000},
      'pendientes': 2,
    });
  }
  if (ruta.startsWith('/club/pagos/vouchers')) {
    return RespuestaClub(true, {'ok': true, 'pagos': [
      {'id': 'pgm_1', 'monto_centimos': 6000, 'moneda': 'PEN', 'estado': 'en_revision', 'jugador_nombre': 'Ana Pérez',
       'medio': 'yape', 'operacion': '04567812', 'vence_en': _vence},
    ]});
  }
  if (ruta.startsWith('/reservas/reglas/')) {
    return const RespuestaClub(true, {'ok': true, 'disponible': true,
      'base': {'hora_apertura': '07:00', 'hora_cierre': '23:00', 'precio_hora': 60, 'moneda': 'S/'},
      'reglas': {
        'horario_semana': {'sab': {'apertura': '08:00', 'cierre': '20:00'}, 'dom': null},
        'franjas': [{'nombre': 'Hora punta', 'dias': ['lun', 'mar', 'mie', 'jue', 'vie'], 'desde': '18:00',
                     'hasta': '23:59', 'precio_hora': 90, 'precio_turno': 0}],
        'recargo_luz': {'desde': '18:30', 'monto': 10},
        'anticipacion_min_horas': 2, 'cancelacion_horas': 24,
      }});
  }
  if (ruta == '/web/asegurar') {
    return const RespuestaClub(true, {'ok': true, 'ids': ['web_1'], 'firma': 'f', 'total_centimos': 9000,
      'moneda': 'S/', 'hold_segundos': 600});
  }
  return const RespuestaClub(false, {}, 'error');
}

const _checkout = {
  'directo': true, 'culqi_public_key': 'pk_test_abc',
  'medios': [
    {'tipo': 'yape', 'etiqueta': 'Yape', 'titular': 'Club Raqueta SAC', 'numero': '987654321', 'nota': ''},
    {'tipo': 'transferencia', 'etiqueta': 'Transferencia bancaria', 'titular': 'Club Raqueta SAC',
     'banco': 'BCP', 'cuenta': '191-1234567-0-12', 'cci': '00219100123456701254', 'nota': ''},
  ],
};

const _cancha = Cancha(
  id: 'c1', nombre: 'Cancha 1', club: 'Club Raqueta', distrito: Distrito.sanBorja,
  deporte: Deporte.futbol, precioHora: 60, ubicacion: LatLng(-12.1, -77.0), clubFundador: false, digitalizada: true,
);

void main() {
  setUpAll(() async {
    GoogleFonts.config.allowRuntimeFetching = false;
    await cargarFuentes();
    ClubPagosService.simulador = _sim;
  });

  Future<void> foto(WidgetTester t, Widget w, String nombre, {double alto = 1400, bool oscuro = false}) async {
    tamanoTelefono(t, alto: alto);
    await t.pumpWidget(envolver(w, oscuro: oscuro));
    await t.pump(const Duration(milliseconds: 50));
    await t.pump(const Duration(milliseconds: 50));
    await expectLater(find.byType(MaterialApp), matchesGoldenFile('png/$nombre.png'));
    await t.pumpWidget(const SizedBox());
  }

  testWidgets('cobros del club', (t) async => foto(t, const ClubPagosScreen(), 'cobros_club'));
  testWidgets('cobros del club (oscuro)', (t) async => foto(t, const ClubPagosScreen(), 'cobros_club_oscuro', oscuro: true));
  testWidgets('pagos por confirmar', (t) async => foto(t, const PagosPorConfirmarScreen(), 'pagos_por_confirmar', alto: 900));
  testWidgets('reglas de reserva', (t) async => foto(t, const ReglasReservaScreen(cancha: _cancha), 'reglas_reserva', alto: 2200));
  testWidgets('checkout directo: datos y pago', (t) async {
    tamanoTelefono(t, alto: 1500);
    await t.pumpWidget(envolver(const CheckoutDirectoScreen(
      cancha: _cancha, horas: [(fecha: '2026-11-07', hora: '18:00')], fechaTexto: 'Sáb 7 nov', checkout: _checkout)));
    await t.pump();
    await t.enterText(find.byType(TextField).at(0), 'Ana Pérez');
    await t.enterText(find.byType(TextField).at(1), '987654321');
    await t.pump();
    await expectLater(find.byType(MaterialApp), matchesGoldenFile('png/checkout_datos.png'));
    await t.tap(find.text('Apartar horario'));
    await t.pump();
    await t.pump(const Duration(milliseconds: 50));
    await expectLater(find.byType(MaterialApp), matchesGoldenFile('png/checkout_pago_yape.png'));
    await t.tap(find.text('Transferencia bancaria'));
    await t.pump();
    await expectLater(find.byType(MaterialApp), matchesGoldenFile('png/checkout_pago_voucher.png'));
    await t.pumpWidget(const SizedBox());
  });
}
