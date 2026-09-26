import 'dart:async';

import 'package:app_links/app_links.dart';
import 'package:flutter/material.dart';

import '../screens/campeonato_detalle_screen.dart';
import '../state/app_state.dart';
import 'push_service.dart';

/// DEEP LINKS de la app (pedido del director: el enlace compartido debe
/// llevar DIRECTO a unirse). Maneja:
///  - `https://…/c/{campeonatoId}` (App Link del dominio de marca), y
///  - `pichangol://c/{campeonatoId}` (esquema propio: lo dispara el botón
///    "Unirme en la app" de la página web del campeonato).
/// Ambos aceptan `?equipo=CODIGO` (enlace que comparte el CAPITÁN en fútbol):
/// la app abre la ficha y, tras el login, ofrece "Unirme a «equipo»" sin que
/// el jugador escriba el código (pedido del director, sep-2026).
/// Si la app está instalada, el enlace la abre en la FICHA del campeonato
/// (con su botón "Inscribirme"); si no, la página web empuja a descargarla.
/// Fail-safe: cualquier error se ignora (la app arranca normal).
class EnlacesService {
  EnlacesService._();

  static StreamSubscription<Uri>? _sub;
  static Uri? _pendiente; // llegó antes de que el navegador esté listo

  static Future<void> init() async {
    try {
      final links = AppLinks();
      // Enlace que ABRIÓ la app (estaba cerrada).
      try {
        final inicial = await links.getInitialLink();
        if (inicial != null) _manejar(inicial);
      } catch (_) {}
      // Enlaces que llegan con la app ya abierta (foreground/background).
      _sub?.cancel();
      _sub = links.uriLinkStream.listen(_manejar, onError: (_) {});
    } catch (_) {
      // sin plugin / plataforma sin soporte: la app sigue normal
    }
  }

  /// Id de campeonato dentro de un URI soportado ('' si no aplica).
  static String _idCampeonato(Uri uri) {
    // pichangol://c/ID  (host = 'c', path = '/ID')  ·  pichangol://campeonato?id=ID
    if (uri.scheme == 'pichangol') {
      final q = (uri.queryParameters['id'] ?? '').trim();
      if (q.isNotEmpty) return q;
      if (uri.host == 'c' && uri.pathSegments.isNotEmpty) {
        return uri.pathSegments.first.trim();
      }
      return '';
    }
    // https://dominio/c/ID (y el formato viejo ?id=…): mismo parser que
    // "Unirme a un campeonato".
    return AppState.idCampeonatoDe(uri.toString());
  }

  /// Código de equipo del enlace (`?equipo=`), en mayúsculas; '' si no trae.
  static String codigoEquipoDe(Uri uri) {
    final e = (uri.queryParameters['equipo'] ?? '').trim().toUpperCase();
    if (e.isEmpty || e.length > 16) return '';
    return e;
  }

  static void _manejar(Uri uri) {
    final id = _idCampeonato(uri);
    if (id.isEmpty) return;
    _pendiente = uri;
    _abrirCampeonato(id, equipo: codigoEquipoDe(uri));
  }

  static Future<void> _abrirCampeonato(String id, {String equipo = ''}) async {
    // Espera a que el navegador global exista (arranque en frío: el enlace
    // llega durante el splash). Reintenta unos segundos y desiste.
    NavigatorState? nav;
    for (var i = 0; i < 40; i++) {
      nav = PushService.navigatorKey.currentState;
      if (nav != null) break;
      await Future.delayed(const Duration(milliseconds: 250));
    }
    if (nav == null) return;
    // Trae el campeonato a la caché local (si no estaba) y abre su ficha,
    // donde vive el botón "Inscribirme".
    final c = await appState.traerCampeonato(id);
    if (c == null) return; // no existe / sin red: no interrumpir el arranque
    _pendiente = null;
    nav.push(MaterialPageRoute(
        builder: (_) => CampeonatoDetalleScreen(campeonatoId: c.id)));
    if (equipo.isEmpty) return;
    // Enlace del capitán: con la ficha ya abierta, ofrecer unirse a SU equipo
    // (login → confirmación → roster). Sobre el overlay del navegador para
    // que los diálogos vivan bajo el MaterialApp.
    await Future.delayed(const Duration(milliseconds: 450));
    final ctx = nav.overlay?.context;
    if (ctx == null || !ctx.mounted) return;
    try {
      await CampeonatoDetalleScreen.unirseConEnlace(ctx, c, equipo);
    } catch (_) {
      // fail-safe: la ficha queda abierta con el botón manual
    }
  }
}
