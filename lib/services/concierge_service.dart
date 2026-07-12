import 'dart:convert';

import 'package:google_maps_flutter/google_maps_flutter.dart';
import 'package:http/http.dart' as http;

import '../models/models.dart';
import '../utils/geo.dart';

/// Una sugerencia del concierge: la cancha + el motivo por el que la eligió.
class SugerenciaConcierge {
  final Cancha cancha;
  final String motivo;
  const SugerenciaConcierge({required this.cancha, required this.motivo});
}

/// Respuesta del concierge de reservas.
class RespuestaConcierge {
  final String respuesta; // texto amable
  final List<SugerenciaConcierge> sugerencias;
  final bool viaIa; // true = respondió Claude; false = heurística de respaldo
  const RespuestaConcierge({
    required this.respuesta,
    required this.sugerencias,
    this.viaIa = false,
  });
}

/// Cliente del **concierge de reservas** (primer agente de IA), servido por el
/// backend growth (`/concierge/reservas`). La app manda el mensaje en lenguaje
/// natural + las canchas que ya conoce (con distancia si hay ubicación); el
/// backend usa Claude para interpretar y rankear, sin exponer la API key.
///
/// La URL base llega por `--dart-define=GROWTH_API_URL`. Fail-safe: si no está
/// configurada o el backend no responde, devuelve null y la pantalla muestra un
/// aviso.
class ConciergeService {
  static const _baseUrl = String.fromEnvironment('GROWTH_API_URL');
  static const _appKey = String.fromEnvironment('APP_API_KEY');

  static bool get disponible => _baseUrl.isNotEmpty;

  /// Pide recomendaciones para [mensaje]. [canchas] es el universo visible;
  /// [centro] (si se conoce) sirve para calcular distancias y ordenar.
  static Future<RespuestaConcierge?> recomendar(
    String mensaje,
    List<Cancha> canchas, {
    LatLng? centro,
  }) async {
    if (!disponible) return null;
    // Compacta las canchas para el contexto del agente (sólo lo útil).
    final ctx = canchas.take(40).map((c) {
      final m = <String, dynamic>{
        'id': c.id,
        'nombre': c.nombre,
        'deporte': c.deporte.name,
        'distrito': c.distrito.etiqueta,
        'club': c.club,
        'direccion': c.direccion ?? '',
        'precioHora': c.precioHora,
      };
      if (centro != null) {
        m['distanciaKm'] =
            double.parse(distanciaKm(centro, c.ubicacion).toStringAsFixed(2));
      }
      return m;
    }).toList();

    try {
      final uri = Uri.parse('$_baseUrl/concierge/reservas');
      final resp = await http
          .post(
            uri,
            headers: {
              'Content-Type': 'application/json',
              if (_appKey.isNotEmpty) 'X-App-Key': _appKey,
            },
            body: jsonEncode({'mensaje': mensaje, 'canchas': ctx}),
          )
          .timeout(const Duration(seconds: 20));
      if (resp.statusCode != 200) return null;
      final j = jsonDecode(resp.body) as Map<String, dynamic>;
      final porId = {for (final c in canchas) c.id: c};
      final sugs = <SugerenciaConcierge>[];
      for (final s in (j['sugerencias'] as List? ?? const [])) {
        final cancha = porId[(s as Map)['canchaId']];
        if (cancha != null) {
          sugs.add(SugerenciaConcierge(
              cancha: cancha, motivo: (s['motivo'] ?? '').toString()));
        }
      }
      return RespuestaConcierge(
        respuesta: (j['respuesta'] ?? '').toString(),
        sugerencias: sugs,
        viaIa: (j['via'] ?? '') == 'ia',
      );
    } catch (_) {
      return null;
    }
  }
}
