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

/// El POST DEL DÍA del community manager AUTÓNOMO (Fase 0): un post listo para
/// las redes EXTERNAS del negocio (IG/FB) = copy + hashtags + un FLYER de marca
/// (imagen). El dueño lo publica en 1 toque. Backend `POST /marketing/cm/post-del-dia`.
class PostDelDia {
  final String texto;
  final List<String> hashtags;
  final String horaSugerida;
  final String imagenUrl; // flyer de marca servido por el backend (público)

  const PostDelDia({
    required this.texto,
    this.hashtags = const [],
    this.horaSugerida = '',
    this.imagenUrl = '',
  });

  factory PostDelDia.fromJson(Map<String, dynamic> j) => PostDelDia(
        texto: (j['texto'] ?? '').toString().trim(),
        hashtags: [
          for (final h in (j['hashtags'] as List? ?? const []))
            h.toString().trim()
        ].where((h) => h.isNotEmpty).toList(),
        horaSugerida: (j['hora_sugerida'] ?? '').toString().trim(),
        imagenUrl: (j['imagen_url'] ?? '').toString().trim(),
      );

  /// Texto listo para publicar: cuerpo + hashtags en línea aparte.
  String get textoCompleto {
    final tags = hashtags.isEmpty ? '' : '\n\n${hashtags.join(' ')}';
    return '$texto$tags'.trim();
  }
}

/// Estado del CM AUTÓNOMO de una academia: si está activo, cada cuántos días
/// publica, y el post del día ya PRE-GENERADO por el scheduler (listo al abrir).
class CmEstado {
  final bool activo;
  final int cadaDias;
  final PostDelDia? post;

  const CmEstado({this.activo = false, this.cadaDias = 3, this.post});

  factory CmEstado.fromJson(Map<String, dynamic> j) {
    final p = j['post'];
    return CmEstado(
      activo: j['activo'] == true,
      cadaDias: (j['cada_dias'] as num?)?.toInt() ?? 3,
      post: (p is Map<String, dynamic>) ? PostDelDia.fromJson(p) : null,
    );
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

  /// Genera EL POST DEL DÍA (copy + hashtags + flyer de marca) para publicar en
  /// las redes externas del negocio. Devuelve null si el servicio no respondió.
  static Future<PostDelDia?> postDelDia({
    required String academiaId,
    required Map<String, dynamic> datos,
    String contexto = '',
  }) async {
    if (!disponible) return null;
    try {
      final uri = Uri.parse('$_baseUrl/marketing/cm/post-del-dia');
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
            }),
          )
          .timeout(const Duration(seconds: 40));
      if (resp.statusCode != 200) return null;
      final j = jsonDecode(resp.body) as Map<String, dynamic>;
      if (j['ok'] != true) return null;
      return PostDelDia.fromJson(j);
    } catch (_) {
      return null;
    }
  }

  /// Lee el estado del CM autónomo (activo/cadencia + el post PRE-GENERADO).
  static Future<CmEstado?> cmEstado(String academiaId) async {
    if (!disponible || academiaId.isEmpty) return null;
    try {
      final uri = Uri.parse('$_baseUrl/marketing/cm/estado/$academiaId');
      final resp = await http.get(
        uri,
        headers: {if (_appKey.isNotEmpty) 'X-App-Key': _appKey},
      ).timeout(const Duration(seconds: 25));
      if (resp.statusCode != 200) return null;
      return CmEstado.fromJson(jsonDecode(resp.body) as Map<String, dynamic>);
    } catch (_) {
      return null;
    }
  }

  /// Activa/configura el CM autónomo de una academia. Al activar, el backend
  /// genera un post de una vez (lo trae en la respuesta) y luego lo renueva solo.
  static Future<CmEstado?> cmConfig({
    required String academiaId,
    required bool activo,
    required Map<String, dynamic> datos,
    int cadaDias = 3,
    String contexto = '',
  }) async {
    if (!disponible || academiaId.isEmpty) return null;
    try {
      final uri = Uri.parse('$_baseUrl/marketing/cm/config');
      final resp = await http
          .post(
            uri,
            headers: {
              'Content-Type': 'application/json',
              if (_appKey.isNotEmpty) 'X-App-Key': _appKey,
            },
            body: jsonEncode({
              'academia_id': academiaId,
              'activo': activo,
              'cada_dias': cadaDias,
              'contexto': contexto,
              'datos': datos,
            }),
          )
          .timeout(const Duration(seconds: 45));
      if (resp.statusCode != 200) return null;
      return CmEstado.fromJson(jsonDecode(resp.body) as Map<String, dynamic>);
    } catch (_) {
      return null;
    }
  }
}
