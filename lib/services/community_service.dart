import 'dart:convert';

import 'package:http/http.dart' as http;

/// Un borrador de post generado por el community manager con IA (backend
/// growth `POST /marketing/posts`). El dueño lo revisa, edita y publica en su
/// canal con un tap.
class BorradorPost {
  final String texto;
  final List<String> hashtags;
  final String horaSugerida;

  const BorradorPost({
    required this.texto,
    this.hashtags = const [],
    this.horaSugerida = '',
  });

  factory BorradorPost.fromJson(Map<String, dynamic> j) => BorradorPost(
        texto: (j['texto'] ?? '').toString().trim(),
        hashtags: [
          for (final h in (j['hashtags'] as List? ?? const []))
            h.toString().trim()
        ].where((h) => h.isNotEmpty).toList(),
        horaSugerida: (j['hora_sugerida'] ?? '').toString().trim(),
      );

  /// Texto listo para publicar: cuerpo + hashtags en una línea aparte.
  String get textoCompleto {
    final tags = hashtags.isEmpty ? '' : '\n\n${hashtags.join(' ')}';
    return '$texto$tags'.trim();
  }
}

/// Resultado de una generación: los borradores + si se topó el límite mensual.
class ResultadoCommunity {
  final List<BorradorPost> posts;
  final bool topoLimite; // el backend rechazó por tope mensual de la academia
  final bool viaIa; // true = generado con Claude; false = plantillas
  final int usados;
  final int limiteMes;

  const ResultadoCommunity({
    required this.posts,
    this.topoLimite = false,
    this.viaIa = false,
    this.usados = 0,
    this.limiteMes = 0,
  });
}

/// Cliente del **community manager con IA** (marketing automático de Pichangol).
///
/// Llama al backend growth, que a su vez usa Claude (Anthropic) para redactar
/// posts. Fail-safe: si `GROWTH_API_URL` no está definida, queda inactivo y la
/// pantalla lo avisa. El backend cae a plantillas si no tiene `ANTHROPIC_API_KEY`.
class CommunityService {
  static const _baseUrl = String.fromEnvironment('GROWTH_API_URL');
  static const _appKey = String.fromEnvironment('APP_API_KEY');

  static bool get disponible => _baseUrl.isNotEmpty;

  /// Genera [cantidad] borradores de post para un canal/academia.
  ///
  /// [academiaId] identifica al dueño para aplicar el tope mensual de
  /// generaciones (protege el costo de Anthropic). [datos] describe la academia
  /// (nombre, deporte, sede, instagram) para que el copy sea concreto y real.
  /// [contexto] es el tema/tono que pide el dueño ("promo de verano", etc.).
  ///
  /// Devuelve null si el servicio no está configurado o no respondió.
  static Future<ResultadoCommunity?> generarPosts({
    required String academiaId,
    required Map<String, dynamic> datos,
    String contexto = '',
    int cantidad = 3,
  }) async {
    if (!disponible) return null;
    try {
      final uri = Uri.parse('$_baseUrl/marketing/posts');
      final resp = await http
          .post(
            uri,
            headers: {
              'Content-Type': 'application/json',
              if (_appKey.isNotEmpty) 'X-App-Key': _appKey,
            },
            body: jsonEncode({
              'academia_id': academiaId,
              'datos': datos,
              'contexto': contexto,
              'cantidad': cantidad,
            }),
          )
          .timeout(const Duration(seconds: 30));
      if (resp.statusCode != 200) return null;
      final j = jsonDecode(resp.body) as Map<String, dynamic>;
      if (j['ok'] == false && j['limite'] == true) {
        return ResultadoCommunity(
          posts: const [],
          topoLimite: true,
          usados: (j['usados'] as num?)?.toInt() ?? 0,
          limiteMes: (j['limite_mes'] as num?)?.toInt() ?? 0,
        );
      }
      final posts = [
        for (final p in (j['posts'] as List? ?? const []))
          if (p is Map<String, dynamic>) BorradorPost.fromJson(p)
      ].where((p) => p.texto.isNotEmpty).toList();
      return ResultadoCommunity(
        posts: posts,
        viaIa: (j['via'] ?? '') == 'ia',
        usados: (j['usados'] as num?)?.toInt() ?? 0,
        limiteMes: (j['limite_mes'] as num?)?.toInt() ?? 0,
      );
    } catch (_) {
      return null;
    }
  }
}
