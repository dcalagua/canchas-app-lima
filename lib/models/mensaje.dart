/// Un mensaje de chat entre el PROFE de una academia y la CUENTA de un alumno
/// (el adulto que administra: el propio alumno o el apoderado). La conversación
/// es 1:1 por (academia, cuenta) e identificada por [hilo].
///
/// Etapa A: texto en tiempo real (Supabase Realtime), sin notificaciones push
/// (eso es Etapa B con FCM). Se guarda en columnas reales (no jsonb) porque es
/// alta frecuencia y se filtra/ordena por [hilo] + [creado].
class Mensaje {
  final String id;
  final String hilo; // "academiaId|cuentaEmail"
  final String academiaId;
  final String cuentaEmail; // lado alumno (cuenta que administra)
  final String autorEmail;
  final String autorNombre;
  final bool esProfe; // true = lo escribió el profe; false = el alumno
  final String texto;
  final DateTime creado;

  const Mensaje({
    required this.id,
    required this.hilo,
    required this.academiaId,
    required this.cuentaEmail,
    required this.autorEmail,
    required this.autorNombre,
    required this.esProfe,
    required this.texto,
    required this.creado,
  });

  /// Clave estable de la conversación (academia + cuenta del alumno).
  static String hiloDe(String academiaId, String cuentaEmail) =>
      '$academiaId|${cuentaEmail.trim().toLowerCase()}';

  /// Fila para INSERT en Supabase (columnas snake_case). Omite `creado` para que
  /// use el default now() del servidor (hora consistente entre dispositivos).
  Map<String, dynamic> toInsert() => {
        'id': id,
        'hilo': hilo,
        'academia_id': academiaId,
        'cuenta_email': cuentaEmail,
        'autor_email': autorEmail,
        'autor_nombre': autorNombre,
        'es_profe': esProfe,
        'texto': texto,
      };

  /// Mapea una fila de Supabase (columnas snake_case).
  factory Mensaje.fromRow(Map<String, dynamic> r) => Mensaje(
        id: (r['id'] ?? '').toString(),
        hilo: (r['hilo'] ?? '').toString(),
        academiaId: (r['academia_id'] ?? '').toString(),
        cuentaEmail: (r['cuenta_email'] ?? '').toString(),
        autorEmail: (r['autor_email'] ?? '').toString(),
        autorNombre: (r['autor_nombre'] ?? '').toString(),
        esProfe: (r['es_profe'] ?? false) as bool,
        texto: (r['texto'] ?? '').toString(),
        creado: DateTime.tryParse((r['creado'] ?? '').toString())?.toLocal() ??
            DateTime.now(),
      );
}
