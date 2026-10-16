import 'package:flutter/material.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart';

import '../services/location_service.dart';
import '../state/app_state.dart';
import '../utils/geo.dart';
import 'dialogo_pichangol.dart';

/// Resultado de [exigirUbicacionReclamo]: si se puede seguir con el reclamo y
/// el GPS que viaja al backend (puede ser null si la torre no lo exige).
class UbicacionReclamo {
  final bool ok;
  final LatLng? gps;
  const UbicacionReclamo(this.ok, [this.gps]);
}

/// UBICACIÓN OBLIGATORIA AL RECLAMAR (decisión del director, oct-2026): antes
/// de crear nada ni subir fotos, el celular debe estar en el local — GPS a
/// ≤ `appState.reclamoUbicacionMaxM` m de [punto] (lo publica la torre en
/// `GET /config/canal`). Si falta el GPS o está lejos se avisa con un diálogo
/// Pichangol y se ofrece reintentar; si el dueño cancela, `ok == false` y el
/// reclamo NO se envía. Con `reclamoExigirUbicacion == false` nunca bloquea,
/// pero igual se intenta mandar el GPS.
Future<UbicacionReclamo> exigirUbicacionReclamo(
  BuildContext context, {
  required LatLng? punto,
}) async {
  while (true) {
    final lectura = await LocationService.leerParaReclamo();
    if (!context.mounted) return const UbicacionReclamo(false);
    final exige = appState.reclamoExigirUbicacion;
    final maxM = appState.reclamoUbicacionMaxM.round();
    final gps = lectura.punto;

    if (gps != null) {
      if (!exige || punto == null) return UbicacionReclamo(true, gps);
      final d = (distanciaKm(gps, punto) * 1000).round();
      if (d <= maxM) return UbicacionReclamo(true, gps);
      final otra = await confirmarPichangol(
        context,
        titulo: 'Estás lejos del local',
        mensaje: 'Para reclamar tu cancha necesitamos tu ubicación estando en '
            'el local. Estás a ${_fmtDistancia(d)}; acércate a menos de '
            '$maxM m y toca Reintentar.',
        textoConfirmar: 'Reintentar',
        icono: Icons.location_on_outlined,
      );
      if (!otra || !context.mounted) return const UbicacionReclamo(false);
      continue;
    }

    if (!exige) return const UbicacionReclamo(true);

    final String titulo;
    final String mensaje;
    var ajustes = false;
    switch (lectura.estado) {
      case EstadoGpsReclamo.servicioApagado:
        titulo = 'Activa la ubicación';
        mensaje = 'Activa la ubicación de tu celular. Para reclamar tu cancha '
            'necesitamos tu ubicación estando en el local (a menos de '
            '$maxM m).';
        ajustes = true;
      case EstadoGpsReclamo.permisoBloqueado:
        titulo = 'Permite la ubicación';
        mensaje = 'Pichangol no tiene permiso de ubicación. Actívalo en los '
            'ajustes de la app: para reclamar tu cancha necesitamos tu '
            'ubicación estando en el local (a menos de $maxM m).';
        ajustes = true;
      case EstadoGpsReclamo.sinPermiso:
        titulo = 'Permite la ubicación';
        mensaje = 'Para reclamar tu cancha necesitamos tu ubicación estando en '
            'el local (a menos de $maxM m). Acepta el permiso de ubicación '
            'y toca Reintentar.';
      case EstadoGpsReclamo.sinSenal:
      case EstadoGpsReclamo.ok:
        titulo = 'No pudimos ubicarte';
        mensaje = 'Activa la ubicación y espera unos segundos con buena señal. '
            'Para reclamar tu cancha necesitamos tu ubicación estando en el '
            'local (a menos de $maxM m).';
    }
    final si = await confirmarPichangol(
      context,
      titulo: titulo,
      mensaje: mensaje,
      textoConfirmar: ajustes ? 'Abrir ajustes' : 'Reintentar',
      icono: Icons.location_off_outlined,
    );
    if (!si || !context.mounted) return const UbicacionReclamo(false);
    if (ajustes) {
      if (lectura.estado == EstadoGpsReclamo.servicioApagado) {
        await LocationService.abrirAjustesUbicacion();
      } else {
        await LocationService.abrirAjustesApp();
      }
      if (!context.mounted) return const UbicacionReclamo(false);
      final otra = await confirmarPichangol(
        context,
        titulo: '¿Ya activaste la ubicación?',
        mensaje: 'Cuando la actives, toca Reintentar.',
        textoConfirmar: 'Reintentar',
        icono: Icons.location_on_outlined,
      );
      if (!otra || !context.mounted) return const UbicacionReclamo(false);
    }
  }
}

String _fmtDistancia(int m) {
  if (m < 1000) return '$m m';
  final km = m / 1000;
  return '${km.toStringAsFixed(km < 10 ? 1 : 0)} km';
}
