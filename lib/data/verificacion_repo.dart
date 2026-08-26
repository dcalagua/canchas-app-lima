import 'dart:typed_data';

import 'package:supabase_flutter/supabase_flutter.dart';

import '../services/supabase_service.dart';
import 'storage_limpieza.dart';

/// Verificación de identidad del jugador (doc + selfie). Cumplimiento Ley 29733:
/// las imágenes van a un bucket PRIVADO ('verificacion'), NUNCA públicas y no se
/// muestran en la app. El estado vive en `pichangol_verificaciones`.
/// Piloto (marcha blanca): al enviar queda 'verificado' (auto-aprobado); la
/// revisión humana y el face-match son endurecimiento posterior.
class VerificacionRepo {
  static const _tabla = 'pichangol_verificaciones';
  static const _bucket = 'verificacion';

  static bool get disponible => SupabaseService.disponible;

  /// Borra del bucket las fotos (documento + selfie) del usuario. Minimización
  /// de datos personales (Ley 29733): el DNI/CI solo sirve para validar — no
  /// debe quedarse para siempre. Lo llama "Dejar en virgen". Fail-safe.
  static Future<void> borrarDocsDe(String email) async {
    final e = email.trim().toLowerCase();
    if (!disponible || e.isEmpty) return;
    final carpeta = e.replaceAll(RegExp(r'[^a-zA-Z0-9_-]'), '_');
    await StorageLimpieza.borrarCarpeta(_bucket, carpeta);
  }

  /// Sube documento + selfie al bucket privado y registra la verificación.
  /// Devuelve el estado ('verificado') o null si falló.
  static Future<String?> enviar({
    required String email,
    required String nombre,
    required Uint8List doc,
    required Uint8List selfie,
  }) async {
    if (!disponible || email.trim().isEmpty) return null;
    try {
      final e = email.trim().toLowerCase();
      final carpeta = e.replaceAll(RegExp(r'[^a-zA-Z0-9_-]'), '_');
      final ts = DateTime.now().microsecondsSinceEpoch;
      final docPath = '$carpeta/doc_$ts.jpg';
      final selfiePath = '$carpeta/selfie_$ts.jpg';
      final st = SupabaseService.client.storage.from(_bucket);
      await st.uploadBinary(docPath, doc,
          fileOptions:
              const FileOptions(contentType: 'image/jpeg', upsert: true));
      await st.uploadBinary(selfiePath, selfie,
          fileOptions:
              const FileOptions(contentType: 'image/jpeg', upsert: true));
      await SupabaseService.client.from(_tabla).upsert({
        'email': e,
        'nombre': nombre,
        'doc_path': docPath,
        'selfie_path': selfiePath,
        'estado': 'verificado',
      });
      return 'verificado';
    } catch (_) {
      return null;
    }
  }

  /// Registra al jugador como VERIFICADO sin subir imágenes. Se usa cuando la
  /// identidad se validó contra el registro oficial (DNI/RENIEC vía Factiliza):
  /// el número existe y trae la persona, así que no hace falta guardar foto del
  /// documento (menos dato personal = mejor para la Ley 29733). Devuelve el
  /// estado ('verificado') o null si falló.
  static Future<String?> registrarVerificado({
    required String email,
    required String nombre,
  }) async {
    if (!disponible || email.trim().isEmpty) return null;
    try {
      await SupabaseService.client.from(_tabla).upsert({
        'email': email.trim().toLowerCase(),
        'nombre': nombre,
        'estado': 'verificado',
      });
      return 'verificado';
    } catch (_) {
      return null;
    }
  }

  /// De un conjunto de correos, cuáles están VERIFICADOS. Para que el dueño vea
  /// la insignia junto a cada jugador (reservas/chat).
  static Future<Set<String>> verificados(List<String> emails) async {
    if (!disponible || emails.isEmpty) return <String>{};
    try {
      final low = emails
          .map((e) => e.trim().toLowerCase())
          .where((e) => e.isNotEmpty)
          .toSet()
          .toList();
      if (low.isEmpty) return <String>{};
      final rows = await SupabaseService.client
          .from(_tabla)
          .select('email')
          .eq('estado', 'verificado')
          .inFilter('email', low);
      return (rows as List)
          .map((r) => ((r as Map)['email'] ?? '').toString().toLowerCase())
          .where((e) => e.isNotEmpty)
          .toSet();
    } catch (_) {
      return <String>{};
    }
  }

  /// Estado de verificación del usuario ('no' | 'en_revision' | 'verificado').
  static Future<String> estadoDe(String email) async {
    if (!disponible || email.trim().isEmpty) return 'no';
    try {
      final rows = await SupabaseService.client
          .from(_tabla)
          .select('estado')
          .eq('email', email.trim().toLowerCase())
          .limit(1);
      final list = rows as List;
      if (list.isEmpty) return 'no';
      return ((list.first as Map)['estado'] ?? 'no').toString();
    } catch (_) {
      return 'no';
    }
  }
}
