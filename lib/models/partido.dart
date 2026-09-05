import 'package:google_maps_flutter/google_maps_flutter.dart';

import 'models.dart';

/// Un PARTIDO ABIERTO ("busca con quién jugar" — el "Match" del benchmark). Lo
/// crea CUALQUIER jugador: publica un partido con cupos y otros se apuntan. No es
/// una convocatoria de club (esas las organiza el dueño): es matchmaking entre
/// jugadores.
///
/// Reutiliza la infraestructura de GRUPOS: `id` del partido = `id` del grupo de
/// chat, y el roster vive en `pichangol_grupo_miembros`. Así la coordinación por
/// chat (y su push) sale gratis. La metadata del partido vive en
/// `pichangol_partidos`.
class PartidoAbierto {
  final String id;
  final String creadorEmail;
  final String creadorNombre;
  final Deporte deporte;
  final String titulo; // "Fulbito en La Molina", editable
  final String fecha; // 'YYYY-MM-DD'
  final String hora; // 'HH:mm'
  final String sedeNombre; // dónde se juega (cancha o lugar libre)
  final double? lat;
  final double? lng;
  final int cupos; // jugadores que se necesitan en total (incluye al creador)
  final String nota; // "traigan pechera", "nivel intermedio", etc.
  final DateTime creado;

  // ── Runtime (del roster en pichangol_grupo_miembros) ──────────────────────
  final List<String> jugadoresEmails; // correos apuntados (incluye al creador)
  final List<String> jugadoresNombres; // nombres, en el mismo orden

  const PartidoAbierto({
    required this.id,
    required this.creadorEmail,
    required this.creadorNombre,
    required this.deporte,
    required this.titulo,
    required this.fecha,
    required this.hora,
    required this.sedeNombre,
    required this.creado,
    this.lat,
    this.lng,
    this.cupos = 10,
    this.nota = '',
    this.jugadoresEmails = const [],
    this.jugadoresNombres = const [],
  });

  LatLng? get ubicacion => (lat != null && lng != null) ? LatLng(lat!, lng!) : null;

  int get inscritos => jugadoresEmails.length;
  int get faltan => (cupos - inscritos).clamp(0, cupos);
  bool get lleno => inscritos >= cupos;

  bool apuntado(String? email) =>
      email != null &&
      jugadoresEmails.contains(email.trim().toLowerCase());

  bool esCreador(String? email) =>
      email != null &&
      creadorEmail.trim().toLowerCase() == email.trim().toLowerCase();

  PartidoAbierto copyWith({
    List<String>? jugadoresEmails,
    List<String>? jugadoresNombres,
  }) =>
      PartidoAbierto(
        id: id,
        creadorEmail: creadorEmail,
        creadorNombre: creadorNombre,
        deporte: deporte,
        titulo: titulo,
        fecha: fecha,
        hora: hora,
        sedeNombre: sedeNombre,
        creado: creado,
        lat: lat,
        lng: lng,
        cupos: cupos,
        nota: nota,
        jugadoresEmails: jugadoresEmails ?? this.jugadoresEmails,
        jugadoresNombres: jugadoresNombres ?? this.jugadoresNombres,
      );

  /// Fila para INSERT en `pichangol_partidos` (snake_case). Omite `creado` para
  /// que use el default now() del servidor.
  Map<String, dynamic> toInsert() => {
        'id': id,
        'creador_email': creadorEmail.trim().toLowerCase(),
        'creador_nombre': creadorNombre,
        'deporte': deporte.name,
        'titulo': titulo,
        'fecha': fecha,
        'hora': hora,
        'sede_nombre': sedeNombre,
        if (lat != null) 'lat': lat,
        if (lng != null) 'lng': lng,
        'cupos': cupos,
        'nota': nota,
      };

  factory PartidoAbierto.fromRow(Map<String, dynamic> r) => PartidoAbierto(
        id: (r['id'] ?? '').toString(),
        creadorEmail: (r['creador_email'] ?? '').toString(),
        creadorNombre: (r['creador_nombre'] ?? '').toString(),
        deporte: Deporte.values.firstWhere(
            (d) => d.name == r['deporte'],
            orElse: () => Deporte.futbol),
        titulo: (r['titulo'] ?? '').toString(),
        fecha: (r['fecha'] ?? '').toString(),
        hora: (r['hora'] ?? '').toString(),
        sedeNombre: (r['sede_nombre'] ?? '').toString(),
        lat: (r['lat'] as num?)?.toDouble(),
        lng: (r['lng'] as num?)?.toDouble(),
        cupos: (r['cupos'] as num?)?.toInt() ?? 10,
        nota: (r['nota'] ?? '').toString(),
        creado: DateTime.tryParse((r['creado'] ?? '').toString())?.toLocal() ??
            DateTime.now(),
      );
}
