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
  final String trackUrl; // enlace EXACTO a la canción en Apple Music
  final int inicioMs; // desde qué ms del preview arranca en la historia

  const PistaMusica({
    required this.titulo,
    required this.artista,
    required this.previewUrl,
    required this.artUrl,
    this.trackUrl = '',
    this.inicioMs = 0,
  });

  PistaMusica copyWith({int? inicioMs}) => PistaMusica(
        titulo: titulo,
        artista: artista,
        previewUrl: previewUrl,
        artUrl: artUrl,
        trackUrl: trackUrl,
        inicioMs: inicioMs ?? this.inicioMs,
      );

  /// Consulta de búsqueda para "abrir en Spotify".
  String get consultaSpotify => Uri.encodeComponent('$titulo $artista');
}

class MusicaService {
  /// Canciones DESTACADAS (top del país) para mostrar apenas se abre el selector,
  /// sin que el usuario tenga que buscar. Usa el feed RSS de iTunes (trae el
  /// preview de 30 s como "enclosure"). Fail-safe: lista vacía ante error.
  static Future<List<PistaMusica>> destacadas({String pais = 'pe'}) async {
    try {
      final uri = Uri.parse(
          'https://itunes.apple.com/$pais/rss/topsongs/limit=30/json');
      final r = await http.get(uri).timeout(const Duration(seconds: 8));
      if (r.statusCode != 200) return const [];
      final data = jsonDecode(r.body) as Map<String, dynamic>;
      final feed = (data['feed'] as Map?) ?? const {};
      final entries = (feed['entry'] as List?) ?? const [];
      final pistas = <PistaMusica>[];
      for (final e in entries) {
        try {
          final m = e as Map<String, dynamic>;
          // Preview: el <link> con rel="enclosure".
          String preview = '';
          for (final l in (m['link'] as List? ?? const [])) {
            final attrs = (l as Map)['attributes'] as Map? ?? const {};
            if (attrs['rel'] == 'enclosure') {
              preview = (attrs['href'] ?? '').toString();
              break;
            }
          }
          if (preview.isEmpty) continue;
          final imgs = (m['im:image'] as List?) ?? const [];
          final art =
              imgs.isNotEmpty ? ((imgs.last as Map)['label'] ?? '').toString() : '';
          // El <id label="..."> del feed es el enlace a la canción en Apple Music.
          final track = (((m['id'] as Map?) ?? const {})['label'] ?? '').toString();
          pistas.add(PistaMusica(
            titulo: (((m['im:name'] as Map?) ?? const {})['label'] ?? '')
                .toString(),
            artista: (((m['im:artist'] as Map?) ?? const {})['label'] ?? '')
                .toString(),
            previewUrl: preview,
            artUrl: art,
            trackUrl: track,
          ));
        } catch (_) {}
      }
      return pistas;
    } catch (_) {
      return const [];
    }
  }

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
          trackUrl: (m['trackViewUrl'] ?? '').toString(),
        ));
      }
      return pistas;
    } catch (_) {
      return const [];
    }
  }
}
