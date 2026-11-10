import 'dart:convert';

import 'package:http/http.dart' as http;

/// Un resultado de Giphy: [preview] (versión chica para la grilla) y [full]
/// (la que se envía al chat, ya animada).
class GifItem {
  const GifItem({required this.preview, required this.full});
  final String preview; // GIF chico para pintar la grilla rápido
  final String full; // GIF/sticker completo que se manda como mensaje
}

/// GIFs y stickers estilo WhatsApp vía **Giphy**. Requiere una API key gratuita
/// (dart-define `GIPHY_API_KEY`, se saca al instante en developers.giphy.com).
/// Sin key, [configurado] es false y el panel muestra el aviso para activarlo.
///
/// (Tenor —el motor original de WhatsApp— dejó de aceptar clientes nuevos desde
/// enero 2026, por eso usamos Giphy, que da key inmediata.)
class GiphyService {
  static const _key = String.fromEnvironment('GIPHY_API_KEY');
  static const _base = 'https://api.giphy.com/v1';

  static bool get configurado => _key.isNotEmpty;

  /// Busca GIFs (o stickers si [sticker]=true) por [q]. Si [q] está vacío, trae
  /// los de tendencia. Devuelve lista vacía si falla o no hay key.
  static Future<List<GifItem>> buscar(String q,
      {bool sticker = false, int limite = 24}) async {
    if (!configurado) return const [];
    final query = q.trim();
    // gifs vs stickers (transparentes); search (con texto) vs trending (sin).
    final recurso = sticker ? 'stickers' : 'gifs';
    final accion = query.isNotEmpty ? 'search' : 'trending';
    final params = <String, String>{
      'api_key': _key,
      'limit': '$limite',
      'rating': 'g', // contenido seguro (apto para todos)
      if (query.isNotEmpty) 'q': query,
    };
    final uri = Uri.parse('$_base/$recurso/$accion')
        .replace(queryParameters: params);
    try {
      final r = await http.get(uri).timeout(const Duration(seconds: 12));
      if (r.statusCode != 200) return const [];
      final data = jsonDecode(r.body) as Map<String, dynamic>;
      final results = (data['data'] as List?) ?? const [];
      final items = <GifItem>[];
      for (final res in results) {
        final images = (res as Map)['images'] as Map?;
        if (images == null) continue;
        String urlDe(String k) => (images[k]?['url'] ?? '').toString();
        // preview chico (200px) → grilla; full (original) → mensaje.
        final preview = urlDe('fixed_width').isNotEmpty
            ? urlDe('fixed_width')
            : urlDe('fixed_width_small');
        final full =
            urlDe('original').isNotEmpty ? urlDe('original') : preview;
        if (full.isEmpty) continue;
        items.add(GifItem(preview: preview.isNotEmpty ? preview : full, full: full));
      }
      return items;
    } catch (_) {
      return const [];
    }
  }
}
