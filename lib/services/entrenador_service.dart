import 'dart:convert';
import 'dart:typed_data';

import 'package:http/http.dart' as http;
import 'package:supabase_flutter/supabase_flutter.dart' show FileOptions;

import 'supabase_service.dart';

/// ENTRENADOR VIRTUAL — "un coach que ve tu video".
///
/// El jugador graba un clip corto de su golpe; se sube al bucket público
/// `canchas` (carpeta `entrenador/`) y el backend growth lo analiza con
/// visión IA (`POST /entrenador/analizar`), devolviendo un informe de
/// entrenador (fortalezas, correcciones, drills). Si el jugador tiene un
/// smartwatch emparejado, los tips cortos le llegan como notificaciones
/// (Android las espeja sola a la muñeca — no hay app de reloj).
/// Todo fail-safe: sin backend/red, la pantalla lo explica y no rompe nada.
class EntrenadorService {
  static const _baseUrl = String.fromEnvironment('GROWTH_API_URL');
  static const _appKey = String.fromEnvironment('APP_API_KEY');

  static bool get disponible => _baseUrl.isNotEmpty;

  /// Motivo del último fallo (para mostrarlo tal cual al usuario).
  static String? ultimoError;

  /// Sube el clip al bucket `canchas` y devuelve su URL pública, o null.
  static Future<String?> subirVideo(String analisisLocalId, Uint8List bytes) async {
    if (!SupabaseService.disponible) {
      ultimoError = 'Supabase no está configurado en esta app.';
      return null;
    }
    try {
      final ruta = 'entrenador/$analisisLocalId.mp4';
      final storage = SupabaseService.client.storage.from('canchas');
      await storage.uploadBinary(ruta, bytes,
          fileOptions:
              const FileOptions(upsert: true, contentType: 'video/mp4'));
      ultimoError = null;
      return storage.getPublicUrl(ruta);
    } catch (e) {
      final s = e.toString().toLowerCase();
      ultimoError = s.contains('maximum') || s.contains('size') || s.contains('413')
          ? 'El video pesa demasiado. Graba un clip de 15–20 segundos.'
          : 'No se pudo subir el video. Revisa tu conexión.';
      return null;
    }
  }

  /// Pide el análisis al coach. Devuelve el JSON del backend, o un mapa con
  /// {'error': ...} legible ('requiere_pro' | 'limite_mensual' | texto).
  static Future<Map<String, dynamic>> analizar({
    required String email,
    required String deporte,
    required String golpe,
    required String videoUrl,
    required bool tipsReloj,
  }) async {
    if (!disponible) return {'error': 'Backend no configurado.'};
    try {
      final r = await http
          .post(Uri.parse('$_baseUrl/entrenador/analizar'),
              headers: {
                'Content-Type': 'application/json',
                if (_appKey.isNotEmpty) 'X-App-Key': _appKey,
              },
              body: jsonEncode({
                'email': email,
                'deporte': deporte,
                'golpe': golpe,
                'video_url': videoUrl,
                'tips_reloj': tipsReloj,
              }))
          .timeout(const Duration(seconds: 120));
      if (r.statusCode == 402) return {'error': 'requiere_pro'};
      if (r.statusCode == 429) return {'error': 'limite_mensual'};
      if (r.statusCode == 413) {
        return {'error': 'El video pesa demasiado. Graba 15–20 segundos.'};
      }
      if (r.statusCode != 200) {
        return {'error': 'El entrenador no está disponible ahora. '
            'Intenta en unos minutos.'};
      }
      return jsonDecode(r.body) as Map<String, dynamic>;
    } catch (_) {
      return {'error': 'Sin conexión: no se pudo analizar el video.'};
    }
  }

  /// Historial de análisis del jugador (device-first lo cachea la pantalla).
  static Future<List<Map<String, dynamic>>> historial(String email) async {
    if (!SupabaseService.disponible || email.isEmpty) return const [];
    try {
      final rows = await SupabaseService.client
          .from('pichangol_entrenador_analisis')
          .select()
          .eq('email', email.toLowerCase())
          .order('creado', ascending: false)
          .limit(30);
      return [
        for (final r in (rows as List)) Map<String, dynamic>.from(r as Map),
      ];
    } catch (_) {
      return const [];
    }
  }
}
