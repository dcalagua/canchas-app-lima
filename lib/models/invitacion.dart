/// Invitación de un profe a un alumno para que se una a su academia por
/// **correo** y/o **teléfono** (además del código público).
///
/// Dos mecánicas complementarias:
/// - **Correo:** la invitación aparece SOLA en la app del alumno cuando entra
///   con esa cuenta de Google (match por email) → un toque "Aceptar".
/// - **Teléfono:** queda como registro rastreable y se entrega por WhatsApp con
///   el código de la academia (deep link wa.me).
///
/// El profe ve el estado de cada invitación (pendiente/aceptada) y puede
/// reenviarla o cancelarla.
library;

import '../config/pais.dart';

enum EstadoInvitacion {
  pendiente('Pendiente'),
  aceptada('Aceptada'),
  rechazada('Rechazada'),
  cancelada('Cancelada');

  final String etiqueta;
  const EstadoInvitacion(this.etiqueta);
}

class Invitacion {
  final String id;
  final String academiaId;
  final String academiaNombre; // denormalizado (para mostrar al invitado)
  final String deporte; // Deporte.name denormalizado (ícono/etiqueta)
  final String email; // normalizado a minúsculas; '' si sólo por teléfono
  final String telefono; // sólo dígitos (últimos 9); '' si sólo por correo
  final String nombreSugerido; // nombre que el profe puso al invitar
  final EstadoInvitacion estado;
  final DateTime creada;

  const Invitacion({
    required this.id,
    required this.academiaId,
    required this.academiaNombre,
    this.deporte = 'tenis',
    this.email = '',
    this.telefono = '',
    this.nombreSugerido = '',
    this.estado = EstadoInvitacion.pendiente,
    required this.creada,
  });

  /// Normaliza un correo para comparar (minúsculas, sin espacios).
  static String normalizarEmail(String e) => e.trim().toLowerCase();

  /// Normaliza un teléfono a los **últimos N dígitos** del celular local del
  /// país activo (9 en PE/EC, 8 en BO), así coincide venga con código de país,
  /// espacios, guiones o sin prefijo.
  static String normalizarTelefono(String t) {
    final d = t.replaceAll(RegExp(r'[^0-9]'), '');
    final n = paisActual.telLongitud;
    return d.length <= n ? d : d.substring(d.length - n);
  }

  bool coincideEmail(String e) =>
      email.isNotEmpty && email == normalizarEmail(e);

  bool coincideTelefono(String t) =>
      telefono.isNotEmpty && telefono == normalizarTelefono(t);

  /// Cómo se identificó al invitado (para mostrarlo en la lista del profe).
  String get destino => email.isNotEmpty
      ? email
      : (telefono.isNotEmpty ? '$codigoTelActual $telefono' : 'código');

  Invitacion copyWith({EstadoInvitacion? estado}) => Invitacion(
        id: id,
        academiaId: academiaId,
        academiaNombre: academiaNombre,
        deporte: deporte,
        email: email,
        telefono: telefono,
        nombreSugerido: nombreSugerido,
        estado: estado ?? this.estado,
        creada: creada,
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'academiaId': academiaId,
        'academiaNombre': academiaNombre,
        'deporte': deporte,
        'email': email,
        'telefono': telefono,
        'nombreSugerido': nombreSugerido,
        'estado': estado.name,
        'creada': creada.toIso8601String(),
      };

  factory Invitacion.fromJson(Map<String, dynamic> j) => Invitacion(
        id: j['id'] as String,
        academiaId: (j['academiaId'] ?? '') as String,
        academiaNombre: (j['academiaNombre'] ?? '') as String,
        deporte: (j['deporte'] ?? 'tenis') as String,
        email: (j['email'] ?? '') as String,
        telefono: (j['telefono'] ?? '') as String,
        nombreSugerido: (j['nombreSugerido'] ?? '') as String,
        estado: EstadoInvitacion.values.firstWhere(
            (e) => e.name == j['estado'],
            orElse: () => EstadoInvitacion.pendiente),
        creada:
            DateTime.tryParse((j['creada'] ?? '') as String) ?? DateTime.now(),
      );
}
