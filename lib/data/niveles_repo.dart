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

  /// Niveles (todos sus deportes) de VARIOS jugadores a la vez, para pintar el
  /// chip de nivel en una lista (jugadores disponibles). Un query en vez de N.
  static Future<List<Nivel>> deVarios(List<String> emails) async {
    final es = [
      for (final e in emails)
        if (e.trim().isNotEmpty) e.trim().toLowerCase()
    ];
    if (!disponible || es.isEmpty) return const [];
    try {
      final rows = await SupabaseService.client
          .from(_tabla)
          .select()
          .inFilter('email', es);
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

  /// REEVALUACIÓN del auto-cuestionario (= `/mi-nivel` de la web): si la fila
  /// ya existe cambia SOLO `nivel` y `actualizado` — conserva partidos,
  /// victorias y confiabilidad (antes el upsert de la fila completa los ponía
  /// en 0). Si no existe, la crea. Devuelve la fila resultante (null si falló).
  static Future<Nivel?> reevaluar(
      String email, String deporte, double nivel) async {
    final e = email.trim().toLowerCase();
    if (!disponible || e.isEmpty || deporte.isEmpty) return null;
    final ahora = DateTime.now();
    Future<Nivel?> actualizar() async {
      final rows = await SupabaseService.client
          .from(_tabla)
          .update({'nivel': nivel, 'actualizado': ahora.toIso8601String()})
          .eq('email', e)
          .eq('deporte', deporte)
          .select();
      final list = rows as List;
      if (list.isEmpty) return null;
      return Nivel.fromRow(list.first as Map<String, dynamic>);
    }

    try {
      final ya = await actualizar();
      if (ya != null) return ya;
      final nuevo =
          Nivel(email: e, deporte: deporte, nivel: nivel, actualizado: ahora);
      try {
        await SupabaseService.client.from(_tabla).insert(nuevo.toRow());
        return nuevo;
      } catch (_) {
        // Otra sesión la creó entre medio (UNIQUE email+deporte): actualiza.
        return await actualizar();
      }
    } catch (_) {
      return null;
    }
  }
}
