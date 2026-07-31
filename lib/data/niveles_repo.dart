import '../models/nivel.dart';
import '../services/supabase_service.dart';

/// Nivel de jugador por deporte (estilo Playtomic) en Supabase. Tabla
/// `pichangol_niveles`. Todo fail-safe (si no hay Supabase o la tabla, devuelve
/// vacío/false y la app sigue). Requiere `docs/piloto/supabase_niveles.sql`.
class NivelesRepo {
  static const _tabla = 'pichangol_niveles';

  static bool get disponible => SupabaseService.disponible;

  /// Nivel de un jugador en un deporte, o null si no lo tiene aún.
  static Future<Nivel?> de(String email, String deporte) async {
    if (!disponible || email.isEmpty || deporte.isEmpty) return null;
    try {
      final rows = await SupabaseService.client
          .from(_tabla)
          .select()
          .eq('email', email.toLowerCase())
          .eq('deporte', deporte)
          .limit(1);
      final list = rows as List;
      if (list.isEmpty) return null;
      return Nivel.fromRow(list.first as Map<String, dynamic>);
    } catch (_) {
      return null;
    }
  }

  /// Todos los niveles de un jugador (uno por deporte).
  static Future<List<Nivel>> deJugador(String email) async {
    if (!disponible || email.isEmpty) return const [];
    try {
      final rows = await SupabaseService.client
          .from(_tabla)
          .select()
          .eq('email', email.toLowerCase());
      return [
        for (final r in (rows as List)) Nivel.fromRow(r as Map<String, dynamic>)
      ];
    } catch (_) {
      return const [];
    }
  }

  /// Jugadores de un deporte dentro de una banda de nivel [min]–[max] (para el
  /// matchmaking "juega con parejos"). Ordenados por nivel.
  static Future<List<Nivel>> parejos(
    String deporte, {
    required double min,
    required double max,
    int limite = 60,
  }) async {
    if (!disponible || deporte.isEmpty) return const [];
    try {
      final rows = await SupabaseService.client
          .from(_tabla)
          .select()
          .eq('deporte', deporte)
          .gte('nivel', min)
          .lte('nivel', max)
          .order('nivel', ascending: false)
          .limit(limite);
      return [
        for (final r in (rows as List)) Nivel.fromRow(r as Map<String, dynamic>)
      ];
    } catch (_) {
      return const [];
    }
  }

  /// Crea o actualiza el nivel (upsert por email+deporte). Devuelve true si quedó.
  static Future<bool> guardar(Nivel n) async {
    if (!disponible || n.email.isEmpty || n.deporte.isEmpty) return false;
    try {
      await SupabaseService.client.from(_tabla).upsert(
            n.copyWith(actualizado: DateTime.now()).toRow(),
            onConflict: 'email,deporte',
          );
      return true;
    } catch (_) {
      return false;
    }
  }
}
