/// Un mensaje de chat. La conversación es 1:1 (o grupo) e identificada por
/// [hilo]. Generalizado para tres tipos:
///   - 'academia' → profe ↔ cuenta de alumno (existente).
///   - 'cancha'   → dueño de cancha ↔ jugador que reservó.
///   - 'grupo'    → varios usuarios registrados.
///
/// [refId] es la referencia genérica de la conversación: id de academia, de
/// cancha o de grupo según [tipo]. [cuentaEmail] es la otra parte en un 1:1
/// (alumno o jugador); vacío en grupos. [esProfe] = lo escribió el lado
/// "anfitrión" (profe o dueño).
///
/// Se guarda en columnas reales (no jsonb) porque es alta frecuencia y se
/// filtra/ordena por [hilo] + [creado].
class Mensaje {
  final String id;
  final String hilo;
  final String tipo; // 'academia' | 'cancha' | 'grupo'
  final String refId; // academiaId | canchaId | grupoId
  final String academiaId; // solo 'academia' (compat / routing de push)
  final String cuentaEmail; // otra parte en 1:1 (alumno/jugador); '' en grupo
  final String autorEmail;
  final String autorNombre;
  final bool esProfe; // true = lo escribió el anfitrión (profe/dueño)
  final String texto;
  final DateTime creado;

  const Mensaje({
    required this.id,
    required this.hilo,
    required this.autorEmail,
    required this.autorNombre,
    required this.esProfe,
    required this.texto,
    required this.creado,
    this.tipo = 'academia',
    this.refId = '',
    this.academiaId = '',
    this.cuentaEmail = '',
  });

  bool get esCancha => tipo == 'cancha';
  bool get esGrupo => tipo == 'grupo';

  /// refId efectivo: si no vino, cae a academiaId (mensajes de academia viejos).
  String get refEfectivo => refId.isNotEmpty ? refId : academiaId;

  /// Clave estable de una conversación de ACADEMIA (academia + cuenta alumno).
  static String hiloDe(String academiaId, String cuentaEmail) =>
      '$academiaId|${cuentaEmail.trim().toLowerCase()}';

  /// Clave de una conversación de CANCHA (dueño ↔ jugador).
  static String hiloCancha(String canchaId, String jugadorEmail) =>
      'cancha_$canchaId|${jugadorEmail.trim().toLowerCase()}';

  /// Clave de una conversación de GRUPO.
  static String hiloGrupo(String grupoId) => 'grupo_$grupoId';

  /// Fila para INSERT en Supabase (columnas snake_case). Omite `creado` para que
  /// use el default now() del servidor (hora consistente entre dispositivos).
  Map<String, dynamic> toInsert() => {
        'id': id,
        'hilo': hilo,
        'tipo': tipo,
        'ref_id': refEfectivo,
        // academia_id solo para conversaciones de academia (nullable en la BD).
        if (tipo == 'academia') 'academia_id': academiaId,
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
        tipo: (r['tipo'] ?? 'academia').toString(),
        refId: (r['ref_id'] ?? '').toString(),
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
