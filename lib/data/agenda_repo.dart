import 'package:supabase_flutter/supabase_flutter.dart';

import '../services/supabase_service.dart';

/// AGENDA PRIVADA del usuario en Supabase (`pichangol_agenda`): sus apodos de
/// contacto, la lista de contactos guardados y los bloqueados. Clave = correo
/// del DUEÑO de la agenda. Sirve para que estos datos SIGAN al usuario entre sus
/// dispositivos (teléfono, tablet, etc.). Fail-safe: si no hay backend o falla,
/// se queda solo en local. Requiere docs/piloto/supabase_agenda.sql.
class AgendaRepo {
  static const _tabla = 'pichangol_agenda';

  static bool get disponible => SupabaseService.disponible;

  /// Trae la agenda del correo, o null si no existe / falla.
  static Future<Map<String, dynamic>?> cargar(String email) async {
    final e = email.trim().toLowerCase();
    if (!disponible || e.isEmpty) return null;
    try {
      final rows = await SupabaseService.client
          .from(_tabla)
          .select()
          .eq('email', e)
          .limit(1);
      final l = rows as List;
      return l.isEmpty ? null : Map<String, dynamic>.from(l.first as Map);
    } catch (_) {
      return null;
    }
  }

  /// Guarda (upsert) la agenda del correo. Devuelve true si guardó.
  static Future<bool> guardar(
    String email, {
    required Map<String, String> apodos,
    required List<String> contactos,
    required List<String> bloqueados,
  }) async {
    final e = email.trim().toLowerCase();
    if (!disponible || e.isEmpty) return false;
    try {
      await SupabaseService.client.from(_tabla).upsert({
        'email': e,
        'apodos': apodos,
        'contactos': contactos,
        'bloqueados': bloqueados,
        'actualizado': DateTime.now().toUtc().toIso8601String(),
      }, onConflict: 'email');
      return true;
    } catch (_) {
      return false;
    }
  }
}
