import 'package:supabase_flutter/supabase_flutter.dart';

/// Inicializa Supabase. URL y anon key se inyectan en build con --dart-define
/// (en CI vienen de los secrets SUPABASE_URL / SUPABASE_ANON_KEY). Si no están,
/// la app funciona igual en modo local (sin backend).
class SupabaseService {
  static const _url = String.fromEnvironment('SUPABASE_URL');
  static const _anon = String.fromEnvironment('SUPABASE_ANON_KEY');

  static bool disponible = false;

  static Future<void> init() async {
    if (_url.isEmpty || _anon.isEmpty) return;
    try {
      await Supabase.initialize(url: _url, anonKey: _anon);
      disponible = true;
    } catch (_) {
      disponible = false;
    }
  }

  static SupabaseClient get client => Supabase.instance.client;

  /// Host del proyecto al que apunta el APK (p. ej. `abcd1234.supabase.co`),
  /// SIN la anon key. Sirve para diagnosticar: confirma que estás configurando
  /// el MISMO proyecto que usa la app. Vacío = Supabase sin configurar.
  static String get proyecto {
    if (_url.isEmpty) return 'sin configurar';
    return Uri.tryParse(_url)?.host ?? _url;
  }
}
