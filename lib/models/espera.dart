/// Una entrada de LISTA DE ESPERA: un jugador quiere una hora que está tomada.
/// Si esa reserva se cancela, el dueño ve quién espera (y lo contacta) y el
/// jugador ve device-first que su hora se liberó. Se guarda en Supabase
/// (`pichangol_espera`), una por (cancha, fecha, hora, jugador) → upsert.
class EnEspera {
  final String id;
  final String canchaId;
  final String fecha; // 'YYYY-MM-DD' (fecha real del slot)
  final String hora; // 'HH:mm'
  final String usuario; // correo del jugador
  final String nombre;
  final String telefono;
  final DateTime creado;

  const EnEspera({
    required this.id,
    required this.canchaId,
    required this.fecha,
    required this.hora,
    required this.usuario,
    this.nombre = '',
    this.telefono = '',
    required this.creado,
  });

  /// Clave determinística (para upsert idempotente): un jugador ↔ un slot.
  static String claveId(String usuario, String canchaId, String fecha,
          String hora) =>
      'esp_${usuario.trim().toLowerCase().hashCode.toUnsigned(20).toRadixString(16)}'
      '_${canchaId}_${fecha}_$hora';

  Map<String, dynamic> toInsert() => {
        'id': id,
        'cancha_id': canchaId,
        'fecha': fecha,
        'hora': hora,
        'usuario': usuario.trim().toLowerCase(),
        'nombre': nombre,
        'telefono': telefono,
        // `creado` lo pone el servidor (default now()).
      };

  factory EnEspera.fromRow(Map<String, dynamic> r) => EnEspera(
        id: (r['id'] ?? '').toString(),
        canchaId: (r['cancha_id'] ?? '').toString(),
        fecha: (r['fecha'] ?? '').toString(),
        hora: (r['hora'] ?? '').toString(),
        usuario: (r['usuario'] ?? '').toString(),
        nombre: (r['nombre'] ?? '').toString(),
        telefono: (r['telefono'] ?? '').toString(),
        creado: DateTime.tryParse((r['creado'] ?? '').toString())?.toLocal() ??
            DateTime.now(),
      );
}
