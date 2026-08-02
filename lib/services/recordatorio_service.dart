import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:timezone/data/latest_all.dart' as tzdata;
import 'package:timezone/timezone.dart' as tz;

import '../config/pais.dart';

/// Recordatorios LOCALES (gratis, sin servidor) para el DUEÑO: "cobra en
/// efectivo" cuando se acerca la hora de una reserva pagada en efectivo. La
/// notificación la programa y la muestra el propio teléfono; no cuesta nada ni
/// necesita red. Modo INEXACTO (±unos minutos) para no exigir permiso de alarma
/// exacta en Android 12+. Fail-safe: si algo falla, no rompe la app.
class RecordatorioService {
  RecordatorioService._();

  static final FlutterLocalNotificationsPlugin _plugin =
      FlutterLocalNotificationsPlugin();
  static bool _listo = false;

  /// Minutos ANTES de la hora de la reserva en que suena el recordatorio.
  static const int minutosAntes = 30;

  static const String _canalId = 'recordatorios_cobro';

  /// Zona horaria local según el país (piloto): PE/EC = Lima/Guayaquil (UTC-5),
  /// BO = La Paz (UTC-4). Suficiente para que la hora del aviso cuadre.
  static String _zonaDePais() {
    switch (paisActual.iso) {
      case 'BO':
        return 'America/La_Paz';
      case 'EC':
        return 'America/Guayaquil';
      default:
        return 'America/Lima';
    }
  }

  static Future<void> init() async {
    if (_listo) return;
    try {
      tzdata.initializeTimeZones();
      tz.setLocalLocation(tz.getLocation(_zonaDePais()));
      const androidInit =
          AndroidInitializationSettings('@mipmap/ic_launcher');
      await _plugin.initialize(
          const InitializationSettings(android: androidInit));
      // Canal dedicado (Android 8+). Importancia alta para que se vea/oiga.
      await _plugin
          .resolvePlatformSpecificImplementation<
              AndroidFlutterLocalNotificationsPlugin>()
          ?.createNotificationChannel(const AndroidNotificationChannel(
            _canalId,
            'Cobros en efectivo',
            description:
                'Te recuerda cobrar en efectivo cuando se acerca la hora.',
            importance: Importance.high,
          ));
      // Android 13+: permiso de notificaciones (FCM ya lo pide, es idempotente).
      await _plugin
          .resolvePlatformSpecificImplementation<
              AndroidFlutterLocalNotificationsPlugin>()
          ?.requestNotificationsPermission();
      _listo = true;
    } catch (_) {
      _listo = false;
    }
  }

  /// Id estable de notificación derivado del id de la reserva (para que
  /// re-programar la misma reserva NO duplique el aviso).
  static int _notifId(String reservaId) => reservaId.hashCode & 0x7fffffff;

  /// Programa (o re-programa) el recordatorio de cobro en efectivo para el
  /// instante [cuando] − [minutosAntes]. Si ya pasó ese instante, no agenda.
  static Future<void> programarCobroEfectivo({
    required String reservaId,
    required String titulo,
    required String cuerpo,
    required DateTime cuando,
  }) async {
    await init();
    if (!_listo) return;
    try {
      final disparo = cuando.subtract(const Duration(minutes: minutosAntes));
      if (!disparo.isAfter(DateTime.now())) return; // ya pasó → no agendar
      final cuandoTz = tz.TZDateTime.from(disparo, tz.local);
      await _plugin.zonedSchedule(
        _notifId(reservaId),
        titulo,
        cuerpo,
        cuandoTz,
        const NotificationDetails(
          android: AndroidNotificationDetails(
            _canalId,
            'Cobros en efectivo',
            channelDescription:
                'Te recuerda cobrar en efectivo cuando se acerca la hora.',
            importance: Importance.high,
            priority: Priority.high,
            icon: '@mipmap/ic_launcher',
          ),
        ),
        androidScheduleMode: AndroidScheduleMode.inexactAllowWhileIdle,
      );
    } catch (_) {
      // best-effort
    }
  }

  /// Cancela el recordatorio de una reserva (p. ej. al marcarla pagada o
  /// cancelarla).
  static Future<void> cancelar(String reservaId) async {
    if (!_listo) return;
    try {
      await _plugin.cancel(_notifId(reservaId));
    } catch (_) {}
  }
}
