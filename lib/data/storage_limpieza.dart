import '../services/supabase_service.dart';

/// LIMPIEZA DE STORAGE — el ciclo de vida completo de los archivos subidos.
///
/// Regla de producción: todo lo que el app SUBE al storage debe BORRARSE
/// cuando su dueño lógico muere (se elimina la cancha/producto/estado, vence
/// la historia, se reemplaza el avatar). Sin esto los buckets se llenan de
/// huérfanos para siempre. Cada repo llama a estos helpers en su `eliminar`.
///
/// Todo es fail-safe y best-effort: si el borrado falla (sin red, sin policy
/// RLS de DELETE) la operación principal NO se cae — solo queda el archivo.
/// Requiere las policies de docs/piloto/supabase_storage_limpieza.sql.
class StorageLimpieza {
  /// Borra rutas puntuales de un bucket. Ignora las que no existan.
  static Future<void> borrar(String bucket, List<String> rutas) async {
    if (!SupabaseService.disponible || rutas.isEmpty) return;
    try {
      await SupabaseService.client.storage.from(bucket).remove(rutas);
    } catch (_) {}
  }

  /// Borra TODOS los archivos de una carpeta (no recursivo), opcionalmente
  /// conservando uno (p. ej. el avatar recién subido).
  static Future<void> borrarCarpeta(String bucket, String carpeta,
      {String? excepto}) async {
    if (!SupabaseService.disponible || carpeta.isEmpty) return;
    try {
      final st = SupabaseService.client.storage.from(bucket);
      final archivos = await st.list(path: carpeta);
      final rutas = <String>[
        for (final a in archivos)
          if (a.name.isNotEmpty && '$carpeta/${a.name}' != excepto)
            '$carpeta/${a.name}',
      ];
      if (rutas.isNotEmpty) await st.remove(rutas);
    } catch (_) {}
  }
}
