import 'dart:convert';

import 'package:http/http.dart' as http;

/// Tarjeta de previsualización de un enlace (Open Graph), como en WhatsApp.
class PreviewEnlace {
  final String url;
  final String titulo;
  final String descripcion;
  final String imagen;
  final String dominio;

  const PreviewEnlace({
    required this.url,
    this.titulo = '',
    this.descripcion = '',
    this.imagen = '',
    this.dominio = '',
  });

  bool get vacio => titulo.isEmpty && imagen.isEmpty;
}

/// Baja los metadatos de un enlace (título, descripción, imagen, dominio) desde el
/// backend growth, que hace el fetch server-side (maneja redirecciones y cachea).
///
/// Fail-safe: si el servicio no está configurado o el enlace no da metadatos,
/// devuelve null y la UI no muestra tarjeta. Cachea en memoria por URL para no
/// pedir lo mismo en cada render.
class LinkPreviewService {
  static const _baseUrl = String.fromEnvironment('GROWTH_API_URL');
  static const _appKey = String.fromEnvironment('APP_API_KEY');

  static bool get disponible => _baseUrl.isNotEmpty;

  // Caché por URL. El valor null = ya se intentó y no hubo preview (no reintentar).
  static final Map<String, PreviewEnlace?> _cache = {};

  static Future<PreviewEnlace?> obtener(String url) async {
    final u = url.trim();
    if (u.isEmpty || !disponible) return null;
    if (_cache.containsKey(u)) return _cache[u];
    try {
      final uri = Uri.parse('$_baseUrl/marketing/link-preview')
          .replace(queryParameters: {'url': u});
      final resp = await http.get(uri, headers: {
        if (_appKey.isNotEmpty) 'X-App-Key': _appKey,
      }).timeout(const Duration(seconds: 12));
      if (resp.statusCode != 200) {
        _cache[u] = null;
        return null;
      }
      final j = jsonDecode(resp.body) as Map<String, dynamic>;
      if (j['ok'] != true) {
        _cache[u] = null;
        return null;
      }
      final p = PreviewEnlace(
        url: (j['url'] ?? u).toString(),
        titulo: (j['title'] ?? '').toString(),
        descripcion: (j['description'] ?? '').toString(),
        imagen: (j['image'] ?? '').toString(),
        dominio: (j['domain'] ?? '').toString(),
      );
      final val = p.vacio ? null : p;
      _cache[u] = val;
      return val;
    } catch (_) {
      _cache[u] = null;
      return null;
    }
  }
}
