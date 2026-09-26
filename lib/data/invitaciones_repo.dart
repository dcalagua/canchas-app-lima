import '../models/invitacion.dart';
import '../services/supabase_service.dart';

/// Acceso a INVITACIONES en Supabase (tabla `pichangol_invitaciones`). Guarda la
/// invitación completa como JSON (columna `data` jsonb) + columnas sueltas
/// `academia_id` y `email` para filtrar rápido.
///
/// Hace que "invitar por correo" funcione ENTRE dispositivos: el profe invita en
/// su celular → la invitación sube a la nube → el alumno la ve en el suyo al
/// entrar con esa cuenta. Todo fail-safe: si Supabase no está o falla, la app
/// sigue con lo local.
class InvitacionesRepo {
  static const _tabla = 'pichangol_invitaciones';

  /// Invitaciones que creó el profe (las de sus academias). Fail-safe.
  static Future<List<Invitacion>> deAcademias(List<String> academiaIds) async {
    if (!SupabaseService.disponible || academiaIds.isEmpty) return [];
    try {
      final rows = await SupabaseService.client
          .from(_tabla)
          .select()
          .inFilter('academia_id', academiaIds);
      return _mapear(rows);
    } catch (_) {
      return [];
    }
  }

  /// Invitaciones dirigidas a un correo (para que el alumno las vea al entrar).
  /// Fail-safe.
  static Future<List<Invitacion>> paraEmail(String email) async {
    if (!SupabaseService.disponible || email.isEmpty) return [];
    try {
      final rows = await SupabaseService.client
          .from(_tabla)
          .select()
          .eq('email', Invitacion.normalizarEmail(email));
      return _mapear(rows);
    } catch (_) {
      return [];
    }
  }

  static List<Invitacion> _mapear(dynamic rows) => (rows as List)
      .map((r) => Invitacion.fromJson(
          Map<String, dynamic>.from((r as Map)['data'] as Map)))
      .toList();

  /// Inserta o actualiza (upsert por id). Fail-safe.
  static Future<void> guardar(Invitacion inv) async {
    if (!SupabaseService.disponible) return;
    try {
      await SupabaseService.client.from(_tabla).upsert({
        'id': inv.id,
        'academia_id': inv.academiaId,
        'email': inv.email,
        'estado': inv.estado.name,
        'data': inv.toJson(),
      });
    } catch (_) {}
  }
}
