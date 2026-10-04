import 'dart:async';

import 'package:app_links/app_links.dart';
import 'package:flutter/material.dart';

import '../models/club.dart';
import '../models/models.dart';
import '../screens/academia_detalle_screen.dart';
import '../screens/anfitrion_screen.dart';
import '../screens/campeonato_detalle_screen.dart';
import '../screens/club_detalle_screen.dart';
import '../screens/mis_reservas_screen.dart';
import '../state/app_state.dart';
import 'push_service.dart';

/// DEEP LINKS de la app. Dos orígenes:
///  - **App Links** `https://www.pichangol.app/...` (también `pichangol.app` y
///    `pg.ebim.pe`, verificados contra `/.well-known/assetlinks.json`): al tocar
///    el enlace en WhatsApp/Chrome, Android abre la app instalada en vez del
///    navegador.
///  - **Esquema propio** `pichangol://…`: lo dispara la web desde el navegador
///    del celular (`ui.JS_ABRIR_APP`: `intent://<host><ruta>#Intent;scheme=
///    pichangol;…`) y el botón "Unirme en la app" del campeonato
///    (`pichangol://c/ID`).
///
/// La app abre la MISMA pantalla que el usuario veía en la web (pedido del
/// director, 28-sep-2026: "si estoy en la web de un celular y tengo el PCG
/// instalado, que me lleve inmediatamente al app"):
///  - `/c/{id}[?equipo=COD]` → ficha del campeonato (+ "Unirme a «equipo»");
///  - `/reservar/{canchaId}` → ficha del LOCAL con esa cancha seleccionada;
///  - `/reserva/{ref}` y `/mis-reservas` → Mis reservas;
///  - `/academia/{id}` y `/l/{id}` → ficha de la academia;
///  - `/anfitrion…` → Modo anfitrión;
///  - `/` y `/canchas` → Explorar (la pantalla inicial: nada que empujar).
/// Espejo de `RUTAS` en `web/ui.py` y de los `pathPrefix` del manifest
/// (`tool/configure_platforms.py`). Fail-safe: cualquier error se ignora y la
/// app arranca normal.
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

  /// Ruta "de la web" que representa el URI, siempre con `/` inicial y sin
  /// barra final: `https://www.pichangol.app/reservar/x` → `/reservar/x`;
  /// `pichangol://www.pichangol.app/mis-reservas` → `/mis-reservas`;
  /// `pichangol://c/ID` (host sin punto = primer segmento) → `/c/ID`.
  /// '' si no se reconoce el esquema.
  static String rutaWebDe(Uri uri) {
    String ruta;
    if (uri.scheme == 'https' || uri.scheme == 'http') {
      ruta = uri.path;
    } else if (uri.scheme == 'pichangol') {
      final host = uri.host.trim();
      ruta = host.isEmpty || host.contains('.')
          ? uri.path
          : '/$host${uri.path}';
    } else {
      return '';
    }
    if (ruta.isEmpty) return '/';
    if (!ruta.startsWith('/')) ruta = '/$ruta';
    while (ruta.length > 1 && ruta.endsWith('/')) {
      ruta = ruta.substring(0, ruta.length - 1);
    }
    return ruta;
  }

  /// Id de campeonato dentro de un URI soportado ('' si no aplica):
  /// `/c/ID` (https o `pichangol://c/ID`) y el formato viejo
  /// `…/campeonato…?id=ID` / `pichangol://campeonato?id=ID`.
  static String _idCampeonato(Uri uri) {
    final segs = _segmentos(rutaWebDe(uri));
    if (segs.length >= 2 && segs.first == 'c') return segs[1];
    final q = (uri.queryParameters['id'] ?? '').trim();
    if (q.isNotEmpty && segs.isNotEmpty && segs.first.startsWith('campeonato')) {
      return q;
    }
    return '';
  }

  static List<String> _segmentos(String ruta) {
    final out = <String>[];
    for (final s in ruta.split('/')) {
      String t;
      try {
        t = Uri.decodeComponent(s).trim();
      } catch (_) {
        t = s.trim();
      }
      if (t.isNotEmpty) out.add(t);
    }
    return out;
  }

  /// Código de equipo del enlace (`?equipo=`), en mayúsculas; '' si no trae.
  static String codigoEquipoDe(Uri uri) {
    final e = (uri.queryParameters['equipo'] ?? '').trim().toUpperCase();
    if (e.isEmpty || e.length > 16) return '';
    return e;
  }

  static void _manejar(Uri uri) {
    final ruta = rutaWebDe(uri);
    if (ruta.isEmpty) return;
    _pendiente = uri;
    final idCamp = _idCampeonato(uri);
    if (idCamp.isNotEmpty) {
      _abrirCampeonato(idCamp, equipo: codigoEquipoDe(uri));
      return;
    }
    final segs = _segmentos(ruta);
    if (segs.isEmpty) {
      _pendiente = null; // portada: Explorar ya es la pantalla inicial
      return;
    }
    final seccion = segs.first.toLowerCase();
    final id = segs.length >= 2 ? segs[1] : '';
    switch (seccion) {
      case 'reservar':
        if (id.isNotEmpty) _abrirCancha(id);
      case 'reserva':
      case 'mis-reservas':
        _abrirPantalla((_) => const MisReservasScreen());
      case 'academia':
      case 'l':
        if (id.isNotEmpty) _abrirAcademia(id);
      case 'anfitrion':
        _abrirPantalla((_) => const AnfitrionScreen());
      default:
        _pendiente = null; // /canchas, rutas sin equivalente: queda Explorar
    }
  }

  /// Espera a que el navegador global exista (arranque en frío: el enlace
  /// llega durante el splash). Reintenta unos segundos y desiste.
  static Future<NavigatorState?> _esperarNavegador() async {
    for (var i = 0; i < 40; i++) {
      final nav = PushService.navigatorKey.currentState;
      if (nav != null) return nav;
      await Future.delayed(const Duration(milliseconds: 250));
    }
    return null;
  }

  static Future<void> _abrirPantalla(WidgetBuilder builder) async {
    final nav = await _esperarNavegador();
    if (nav == null) return;
    _pendiente = null;
    nav.push(MaterialPageRoute(builder: builder));
  }

  /// `/reservar/{canchaId}` → ficha del LOCAL (como la web: la ficha es el
  /// local, con la cancha del enlace seleccionada). Si las canchas de la nube
  /// aún no bajaron, las trae primero.
  static Future<void> _abrirCancha(String canchaId) async {
    final nav = await _esperarNavegador();
    if (nav == null) return;
    Cancha? c = _canchaPorId(canchaId);
    if (c == null) {
      try {
        await appState.cargarCanchasRemotas();
      } catch (_) {}
      c = _canchaPorId(canchaId);
    }
    if (c == null) return; // no existe / sin red: no interrumpir el arranque
    final vigente = appState.canchaVigente(c);
    final todas = <Cancha>[...appState.canchasExtra, ...appState.canchasRemotas];
    Club? club;
    for (final cl in Club.agrupar(todas)) {
      if (cl.canchas.any((x) => x.id == vigente.id)) {
        club = cl;
        break;
      }
    }
    final destino =
        club ?? Club(id: vigente.id, nombre: vigente.club, canchas: [vigente]);
    _pendiente = null;
    nav.push(MaterialPageRoute(
        builder: (_) =>
            ClubDetalleScreen(club: destino, canchaInicial: vigente)));
  }

  static Cancha? _canchaPorId(String id) {
    for (final c in [...appState.canchasExtra, ...appState.canchasRemotas]) {
      if (c.id == id) return c;
    }
    return null;
  }

  /// `/academia/{id}` y `/l/{id}` → ficha de la academia (baja las academias
  /// de la nube si aún no están).
  static Future<void> _abrirAcademia(String id) async {
    final nav = await _esperarNavegador();
    if (nav == null) return;
    if (appState.academiaPorId(id) == null) {
      try {
        await appState.cargarAcademiasRemotas();
      } catch (_) {}
    }
    if (appState.academiaPorId(id) == null) return;
    _pendiente = null;
    nav.push(MaterialPageRoute(
        builder: (_) => AcademiaDetalleScreen(academiaId: id)));
  }

  static Future<void> _abrirCampeonato(String id, {String equipo = ''}) async {
    final nav = await _esperarNavegador();
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
