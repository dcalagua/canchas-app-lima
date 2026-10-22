/// Un CANAL de difusión (tipo WhatsApp Channels): el dueño publica novedades y
/// los seguidores las ven (uno-a-muchos, sin chat de vuelta). Se guarda en
/// Supabase (`pichangol_canales`); los seguidores en `pichangol_canal_seguidores`
/// y las publicaciones en `pichangol_canal_posts`.
class Canal {
  final String id;
  final String nombre;
  final String descripcion;
  final String fotoUrl;
  final String ownerEmail;
  final DateTime creado;
  final int seguidores; // conteo (runtime, no se persiste en la fila del canal)

  const Canal({
    required this.id,
    required this.nombre,
    required this.ownerEmail,
    required this.creado,
    this.descripcion = '',
    this.fotoUrl = '',
    this.seguidores = 0,
  });

  Canal copyWith({int? seguidores, String? nombre, String? descripcion, String? fotoUrl}) =>
      Canal(
        id: id,
        nombre: nombre ?? this.nombre,
        ownerEmail: ownerEmail,
        creado: creado,
        descripcion: descripcion ?? this.descripcion,
        fotoUrl: fotoUrl ?? this.fotoUrl,
        seguidores: seguidores ?? this.seguidores,
      );

  Map<String, dynamic> toInsert() => {
        'id': id,
        'nombre': nombre,
        'descripcion': descripcion,
        if (fotoUrl.isNotEmpty) 'foto_url': fotoUrl,
        'owner_email': ownerEmail.trim().toLowerCase(),
      };

  factory Canal.fromRow(Map<String, dynamic> r) => Canal(
        id: (r['id'] ?? '').toString(),
        nombre: (r['nombre'] ?? '').toString(),
        descripcion: (r['descripcion'] ?? '').toString(),
        fotoUrl: (r['foto_url'] ?? '').toString(),
        ownerEmail: (r['owner_email'] ?? '').toString().toLowerCase(),
        creado: DateTime.tryParse((r['creado'] ?? '').toString())?.toLocal() ??
            DateTime.now(),
      );
}

/// Caché local (device-first) de la lista de canales visibles + sus posts, para
/// pintar Novedades al instante sin esperar a Supabase.
class CanalesCache {
  final List<Canal> canales;
  final Map<String, List<CanalPost>> posts;
  const CanalesCache(this.canales, this.posts);
}

/// Una publicación dentro de un canal (texto + foto/video opcional).
class CanalPost {
  final String id;
  final String canalId;
  final String autorEmail;
  final String autorNombre;
  final String tipo; // 'texto' | 'foto' | 'video'
  final String texto;
  final String mediaUrl;
  final DateTime creado;

  const CanalPost({
    required this.id,
    required this.canalId,
    required this.autorEmail,
    required this.autorNombre,
    required this.creado,
    this.tipo = 'texto',
    this.texto = '',
    this.mediaUrl = '',
  });

  bool get esFoto => tipo == 'foto';
  bool get esVideo => tipo == 'video';
  bool get tieneMedia => mediaUrl.isNotEmpty;

  Map<String, dynamic> toInsert() => {
        'id': id,
        'canal_id': canalId,
        'autor_email': autorEmail.trim().toLowerCase(),
        'autor_nombre': autorNombre,
        'tipo': tipo,
        'texto': texto,
        if (mediaUrl.isNotEmpty) 'media_url': mediaUrl,
      };

  factory CanalPost.fromRow(Map<String, dynamic> r) => CanalPost(
        id: (r['id'] ?? '').toString(),
        canalId: (r['canal_id'] ?? '').toString(),
        autorEmail: (r['autor_email'] ?? '').toString().toLowerCase(),
        autorNombre: (r['autor_nombre'] ?? '').toString(),
        tipo: (r['tipo'] ?? 'texto').toString(),
        texto: (r['texto'] ?? '').toString(),
        mediaUrl: (r['media_url'] ?? '').toString(),
        creado: DateTime.tryParse((r['creado'] ?? '').toString())?.toLocal() ??
            DateTime.now(),
      );
}
