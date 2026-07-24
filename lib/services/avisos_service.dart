import 'supabase_service.dart';

/// AVISOS PUSH (canal genérico). Inserta una fila en `pichangol_avisos` de
/// Supabase; un Database Webhook dispara la Edge Function `push-aviso`, que
/// busca los tokens del destinatario en `pichangol_push_tokens` y le envía la
/// notificación FCM. Reusa la MISMA cuenta de servicio (`FCM_SERVICE_ACCOUNT`)
/// que el chat.
///
/// Se usa para los RETOS P2P (que viven en el backend growth, no en Supabase, y
/// por eso el push del chat no los cubre): al retar, al aceptar y al reportar el
/// resultado, el cliente que hace la acción inserta el aviso para el otro
/// jugador. Todo **fail-safe**: sin Supabase o ante cualquier error, no rompe el
/// flujo (el badge in-app del perfil sigue avisando igual).
class AvisosService {
  /// Encola un aviso push para [email]. Devuelve true si se insertó (no
  /// garantiza la entrega del push: eso depende de que el destinatario tenga
  /// token registrado y del webhook).
  static Future<bool> enviar({
    required String email,
    required String titulo,
    required String cuerpo,
    String tipo = 'aviso',
    Map<String, dynamic> data = const {},
  }) async {
    final e = email.trim().toLowerCase();
    if (e.isEmpty || !SupabaseService.disponible) return false;
    try {
      await SupabaseService.client.from('pichangol_avisos').insert({
        'email': e,
        'titulo': titulo,
        'cuerpo': cuerpo,
        'tipo': tipo,
        if (data.isNotEmpty) 'data': data,
        'creado': DateTime.now().toUtc().toIso8601String(),
      });
      return true;
    } catch (_) {
      return false;
    }
  }

  /// Avisa a un jugador que lo retaron.
  static Future<void> retoRecibido({
    required String retadoEmail,
    required String retadorNombre,
    String deporte = '',
  }) =>
      enviar(
        email: retadoEmail,
        titulo: '¡Te retaron! 🎾',
        cuerpo: '$retadorNombre te retó a un partido. Ábrelo en "Mis retos".',
        tipo: 'reto',
        data: {'accion': 'reto', 'deporte': deporte},
      ).then((_) {});

  /// Avisa al retador que su reto fue aceptado (o rechazado).
  static Future<void> retoRespondido({
    required String retadorEmail,
    required String retadoNombre,
    required bool aceptado,
  }) =>
      enviar(
        email: retadorEmail,
        titulo: aceptado ? '¡Reto aceptado! 🔥' : 'Reto rechazado',
        cuerpo: aceptado
            ? '$retadoNombre aceptó tu reto. Coordinen la cancha y jueguen.'
            : '$retadoNombre no pudo aceptar tu reto esta vez.',
        tipo: 'reto',
        data: {'accion': 'respondido', 'aceptado': aceptado},
      ).then((_) {});

  /// Avisa al otro jugador que se reportó el resultado del reto.
  static Future<void> resultadoReportado({
    required String email,
    required String porNombre,
    String marcador = '',
  }) =>
      enviar(
        email: email,
        titulo: 'Resultado del reto 🏆',
        cuerpo: marcador.isNotEmpty
            ? '$porNombre reportó el resultado: $marcador. Revisa tu ranking.'
            : '$porNombre reportó el resultado. Revisa tu ranking.',
        tipo: 'reto',
        data: {'accion': 'resultado'},
      ).then((_) {});
}
