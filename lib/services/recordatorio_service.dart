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

  static const String _canalEstadoId = 'estado_reservas';

  /// Notificación INMEDIATA en el propio teléfono (canal "Estado de tus
  /// reservas"). Se usa para avisarle al JUGADOR el resultado de su reserva
  /// (confirmada / rechazada con motivo / pendiente): al ser LOCAL llega
  /// incluso sin señal — justo cuando más importa (reserva offline). [clave]
  /// da un id estable: re-avisar por la misma reserva reemplaza, no duplica.
  static Future<void> mostrarAhora({
    required String clave,
    required String titulo,
    required String cuerpo,
  }) async {
    await init();
    if (!_listo) return;
    try {
      await _plugin
          .resolvePlatformSpecificImplementation<
              AndroidFlutterLocalNotificationsPlugin>()
          ?.createNotificationChannel(const AndroidNotificationChannel(
            _canalEstadoId,
            'Estado de tus reservas',
            description:
                'Confirmación o rechazo de tus reservas (con el motivo).',
            importance: Importance.high,
          ));
      await _plugin.show(
        _notifId('estado_$clave'),
        titulo,
        cuerpo,
        NotificationDetails(
          android: AndroidNotificationDetails(
            _canalEstadoId,
            'Estado de tus reservas',
            channelDescription:
                'Confirmación o rechazo de tus reservas (con el motivo).',
            importance: Importance.high,
            priority: Priority.high,
            icon: '@mipmap/ic_launcher',
            // Texto expandible: el motivo completo se lee sin recortes.
            styleInformation: BigTextStyleInformation(cuerpo),
          ),
        ),
      );
    } catch (_) {
      // best-effort
    }
  }

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
        // Requerido por la API (interpretación de la hora en iOS antiguo). En
        // Android no aplica; usamos la hora absoluta.
        uiLocalNotificationDateInterpretation:
            UILocalNotificationDateInterpretation.absoluteTime,
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

  // Id fijo del recordatorio DIARIO de "cierra tu caja" (una sola serie).
  static const int _idCierreDiario = 918273;

  /// Programa el recordatorio DIARIO al DUEÑO para cerrar su caja (~23:00 hora
  /// local, cerca del cierre del local). Se repite todos los días a la misma
  /// hora (matchDateTimeComponents). Idempotente: re-llamar re-agenda la misma
  /// serie. El auto-cierre de respaldo actúa si aun así no la cierra.
  static Future<void> programarRecordatorioCierreDiario() async {
    await init();
    if (!_listo) return;
    try {
      final now = tz.TZDateTime.now(tz.local);
      var cuando =
          tz.TZDateTime(tz.local, now.year, now.month, now.day, 23, 0);
      if (!cuando.isAfter(now)) cuando = cuando.add(const Duration(days: 1));
      await _plugin.zonedSchedule(
        _idCierreDiario,
        'Cierra tu caja de hoy',
        'Revisa lo cobrado del día y cierra tu caja en Pichangol.',
        cuando,
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
        uiLocalNotificationDateInterpretation:
            UILocalNotificationDateInterpretation.absoluteTime,
        matchDateTimeComponents: DateTimeComponents.time, // diario a esa hora
      );
    } catch (_) {
      // best-effort
    }
  }

  /// Cancela el recordatorio diario de cierre (p. ej. si deja de ser dueño).
  static Future<void> cancelarRecordatorioCierre() async {
    if (!_listo) return;
    try {
      await _plugin.cancel(_idCierreDiario);
    } catch (_) {}
  }
}
