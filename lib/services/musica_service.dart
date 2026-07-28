import 'dart:convert';

import 'package:http/http.dart' as http;

/// Una pista musical para una historia: título, artista, preview de 30 s y
/// carátula. La fuente del audio es la API pública de búsqueda de Apple/iTunes
/// (gratis, sin login, con `previewUrl` de 30 s en casi toda canción). Spotify
/// deshabilitó `preview_url` para apps nuevas, por eso no se usa como audio; sí
/// se ofrece un enlace "abrir en Spotify" (búsqueda) en el visor.
class PistaMusica {
  final String titulo;
  final String artista;
  final String previewUrl; // clip .m4a de ~30 s
  final String artUrl;

  const PistaMusica({
    required this.titulo,
    required this.artista,
    required this.previewUrl,
    required this.artUrl,
  });

  /// Consulta de búsqueda para "abrir en Spotify".
  String get consultaSpotify => Uri.encodeComponent('$titulo $artista');
}

class MusicaService {
  /// Busca canciones por texto. Devuelve pistas con preview de 30 s. Fail-safe:
  /// ante error o sin red, lista vacía.
  static Future<List<PistaMusica>> buscar(String q) async {
    final termino = q.trim();
    if (termino.isEmpty) return const [];
    try {
      final uri = Uri.parse(
          'https://itunes.apple.com/search?media=music&entity=song&limit=25'
          '&term=${Uri.encodeQueryComponent(termino)}');
      final r = await http
          .get(uri)
          .timeout(const Duration(seconds: 8));
      if (r.statusCode != 200) return const [];
      final data = jsonDecode(r.body) as Map<String, dynamic>;
      final results = (data['results'] as List?) ?? const [];
      final pistas = <PistaMusica>[];
      for (final e in results) {
        final m = e as Map<String, dynamic>;
        final preview = (m['previewUrl'] ?? '').toString();
        if (preview.isEmpty) continue; // sin preview no sirve
        // Carátula: iTunes da 100x100; pedimos una más grande.
        final art = (m['artworkUrl100'] ?? '')
            .toString()
            .replaceAll('100x100bb', '300x300bb');
        pistas.add(PistaMusica(
          titulo: (m['trackName'] ?? '').toString(),
          artista: (m['artistName'] ?? '').toString(),
          previewUrl: preview,
          artUrl: art,
        ));
      }
      return pistas;
    } catch (_) {
      return const [];
    }
  }
}
