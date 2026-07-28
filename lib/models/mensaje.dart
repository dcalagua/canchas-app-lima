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
  final String mediaUrl; // URL de la foto adjunta ('' = solo texto)
  final DateTime creado;
  // Responder citando (tipo WhatsApp): snippet + autor del mensaje citado.
  final String respTexto;
  final String respAutor;
  final String respMedia; // URL de la foto citada ('' si el citado no es foto)
  final bool reenviado; // muestra la etiqueta "Reenviado"

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
    this.mediaUrl = '',
    this.respTexto = '',
    this.respAutor = '',
    this.respMedia = '',
    this.reenviado = false,
  });

  bool get esRespuesta => respTexto.isNotEmpty || respAutor.isNotEmpty;

  /// ¿El adjunto es una nota de voz? (se distingue por la extensión del archivo).
  bool get esAudio {
    if (mediaUrl.isEmpty) return false;
    final u = mediaUrl.toLowerCase();
    return u.contains('.m4a') ||
        u.contains('.aac') ||
        u.contains('.mp3') ||
        u.contains('.wav') ||
        u.contains('.ogg');
  }

  /// ¿El adjunto es una foto? (media que no es audio).
  bool get tieneFoto => mediaUrl.isNotEmpty && !esAudio;

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

  /// Clave de un MENSAJE DIRECTO 1:1 entre dos usuarios (por correo). Simétrica:
  /// los dos participantes calculan el mismo hilo sin importar quién lo abra.
  static String hiloDirecto(String a, String b) {
    final par = [a.trim().toLowerCase(), b.trim().toLowerCase()]..sort();
    return 'directo_${par[0]}|${par[1]}';
  }

  bool get esDirecto => tipo == 'directo';

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
        if (mediaUrl.isNotEmpty) 'media_url': mediaUrl,
        if (respTexto.isNotEmpty) 'resp_texto': respTexto,
        if (respAutor.isNotEmpty) 'resp_autor': respAutor,
        if (respMedia.isNotEmpty) 'resp_media': respMedia,
        if (reenviado) 'reenviado': true,
      };

  /// Serialización COMPLETA para caché local (SharedPreferences): incluye todos
  /// los campos (incluido `creado`) para reconstruir el mensaje sin backend.
  /// Se relee con [Mensaje.fromRow].
  Map<String, dynamic> toCache() => {
        'id': id,
        'hilo': hilo,
        'tipo': tipo,
        'ref_id': refId,
        'academia_id': academiaId,
        'cuenta_email': cuentaEmail,
        'autor_email': autorEmail,
        'autor_nombre': autorNombre,
        'es_profe': esProfe,
        'texto': texto,
        'media_url': mediaUrl,
        'resp_texto': respTexto,
        'resp_autor': respAutor,
        'resp_media': respMedia,
        'reenviado': reenviado,
        'creado': creado.toIso8601String(),
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
        mediaUrl: (r['media_url'] ?? '').toString(),
        respTexto: (r['resp_texto'] ?? '').toString(),
        respAutor: (r['resp_autor'] ?? '').toString(),
        respMedia: (r['resp_media'] ?? '').toString(),
        reenviado: (r['reenviado'] ?? false) as bool,
        creado: DateTime.tryParse((r['creado'] ?? '').toString())?.toLocal() ??
            DateTime.now(),
      );
}
