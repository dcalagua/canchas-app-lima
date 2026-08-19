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

  /// URL pública de una Edge Function (`.../functions/v1/<nombre>`), o null si
  /// Supabase no está configurado.
  static String? funcionUrl(String nombre) =>
      _url.isEmpty ? null : '$_url/functions/v1/$nombre';

  /// Enlace público (web) de un campeonato, para compartir a quien no tiene la
  /// app. Lo sirve el BACKEND growth (`GET /c/{id}`, dominio de marca si
  /// LANDING_BASE_URL está seteado) — la Edge Function `campeonato-web` quedó
  /// deprecada (su deploy manual servía el HTML como texto plano). Fallback:
  /// la función vieja solo si no hay backend configurado.
  static String? paginaCampeonato(String id) {
    const landing = String.fromEnvironment('LANDING_BASE_URL');
    const growth = String.fromEnvironment('GROWTH_API_URL');
    final base = landing.isNotEmpty
        ? landing
        : growth.isNotEmpty
            ? growth
            : null;
    if (base != null) {
      return '${base.endsWith('/') ? base.substring(0, base.length - 1) : base}/c/$id';
    }
    final fn = funcionUrl('campeonato-web');
    return fn == null ? null : '$fn?id=$id';
  }
}
