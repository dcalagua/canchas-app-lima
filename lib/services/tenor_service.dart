import 'dart:convert';

import 'package:http/http.dart' as http;

/// Un resultado de Tenor: [preview] (versión chica para la grilla) y [full]
/// (la que se envía al chat, ya animada).
class TenorItem {
  const TenorItem({required this.preview, required this.full});
  final String preview; // GIF chico para pintar la grilla rápido
  final String full; // GIF/sticker completo que se manda como mensaje
}

/// GIFs y stickers estilo WhatsApp vía **Tenor** (el mismo motor de WhatsApp).
/// Requiere una API key gratuita de Google (dart-define `TENOR_API_KEY`). Sin
/// key, [configurado] es false y el panel muestra el aviso para activarlo.
///
/// Docs: https://developers.google.com/tenor/guides/quickstart
class TenorService {
  static const _key = String.fromEnvironment('TENOR_API_KEY');
  static const _base = 'https://tenor.googleapis.com/v2';
  static const _clientKey = 'pichangol';

  static bool get configurado => _key.isNotEmpty;

  /// Busca GIFs (o stickers si [sticker]=true) por [q]. Si [q] está vacío, trae
  /// los destacados/tendencia. Devuelve lista vacía si falla o no hay key.
  static Future<List<TenorItem>> buscar(String q,
      {bool sticker = false, int limite = 24}) async {
    if (!configurado) return const [];
    final query = q.trim();
    // Formatos: GIF normal vs sticker transparente.
    final mediaFilter = sticker
        ? 'tinygif_transparent,gif_transparent'
        : 'tinygif,gif';
    final params = <String, String>{
      'key': _key,
      'client_key': _clientKey,
      'limit': '$limite',
      'media_filter': mediaFilter,
      'contentfilter': 'high', // seguro (sin contenido adulto)
      if (sticker) 'searchfilter': 'sticker',
      if (query.isNotEmpty) 'q': query,
    };
    // Con búsqueda → /search; sin texto → /featured (tendencia).
    final path = query.isNotEmpty ? 'search' : 'featured';
    final uri = Uri.parse('$_base/$path').replace(queryParameters: params);
    try {
      final r = await http.get(uri).timeout(const Duration(seconds: 12));
      if (r.statusCode != 200) return const [];
      final data = jsonDecode(r.body) as Map<String, dynamic>;
      final results = (data['results'] as List?) ?? const [];
      final items = <TenorItem>[];
      for (final res in results) {
        final formats = (res as Map)['media_formats'] as Map?;
        if (formats == null) continue;
        String urlDe(String k) =>
            (formats[k]?['url'] ?? '').toString();
        final preview = sticker
            ? (urlDe('tinygif_transparent').isNotEmpty
                ? urlDe('tinygif_transparent')
                : urlDe('gif_transparent'))
            : (urlDe('tinygif').isNotEmpty ? urlDe('tinygif') : urlDe('gif'));
        final full = sticker
            ? (urlDe('gif_transparent').isNotEmpty
                ? urlDe('gif_transparent')
                : urlDe('tinygif_transparent'))
            : (urlDe('gif').isNotEmpty ? urlDe('gif') : urlDe('tinygif'));
        if (full.isEmpty) continue;
        items.add(TenorItem(
            preview: preview.isNotEmpty ? preview : full, full: full));
      }
      return items;
    } catch (_) {
      return const [];
    }
  }
}
