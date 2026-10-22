/// Un ESTADO / HISTORIA (tipo WhatsApp): publicación efímera que dura 24 h.
/// Puede ser texto (sobre un fondo de color) o una foto con pie opcional.
/// Se guarda en Supabase (`pichangol_estados`); la foto va al bucket público
/// `estados`. Solo lo ven los contactos/conocidos del autor.
class Estado {
  final String id;
  final String autorEmail;
  final String autorNombre; // snapshot del nombre al publicar
  final String tipo; // 'texto' | 'foto' | 'video'
  final String texto; // contenido (texto) o pie de foto/video
  final String fotoUrl; // URL de la foto O del video; vacío si es de texto
  final int bg; // color de fondo (para el de texto), ARGB
  final DateTime creadoEn;
  // Música opcional (preview 30s de iTunes/Apple + carátula). Se reproduce en el
  // visor y ofrece "abrir en Spotify".
  final String musicaTitulo;
  final String musicaArtista;
  final String musicaPreview; // URL del clip de 30s (m4a)
  final String musicaArt; // URL de la carátula
  final int musicaInicioMs; // desde qué ms del preview arranca (recorte)
  final String musicaTrackUrl; // enlace exacto a la canción (Apple Music)

  const Estado({
    required this.id,
    required this.autorEmail,
    required this.autorNombre,
    required this.tipo,
    required this.creadoEn,
    this.texto = '',
    this.fotoUrl = '',
    this.bg = 0xFF128C7E,
    this.musicaTitulo = '',
    this.musicaArtista = '',
    this.musicaPreview = '',
    this.musicaArt = '',
    this.musicaInicioMs = 0,
    this.musicaTrackUrl = '',
  });

  bool get esFoto => tipo == 'foto';
  bool get esVideo => tipo == 'video';
  bool get tieneMedia => fotoUrl.isNotEmpty; // foto o video
  bool get tieneMusica => musicaPreview.isNotEmpty;

  /// Sigue vigente si no han pasado 24 h desde que se publicó.
  bool get vigente =>
      DateTime.now().difference(creadoEn) < const Duration(hours: 24);

  Map<String, dynamic> toRow() => {
        'id': id,
        'autor_email': autorEmail,
        'autor_nombre': autorNombre,
        'tipo': tipo,
        'texto': texto,
        'foto_url': fotoUrl,
        'bg': bg,
        'creado_en': creadoEn.toUtc().toIso8601String(),
        if (musicaTitulo.isNotEmpty) 'musica_titulo': musicaTitulo,
        if (musicaArtista.isNotEmpty) 'musica_artista': musicaArtista,
        if (musicaPreview.isNotEmpty) 'musica_preview': musicaPreview,
        if (musicaArt.isNotEmpty) 'musica_art': musicaArt,
        if (musicaInicioMs > 0) 'musica_inicio_ms': musicaInicioMs,
        if (musicaTrackUrl.isNotEmpty) 'musica_track_url': musicaTrackUrl,
      };

  factory Estado.fromRow(Map<String, dynamic> r) => Estado(
        id: r['id'].toString(),
        autorEmail: (r['autor_email'] ?? '').toString().toLowerCase(),
        autorNombre: (r['autor_nombre'] ?? '').toString(),
        tipo: (r['tipo'] ?? 'texto').toString(),
        texto: (r['texto'] ?? '').toString(),
        fotoUrl: (r['foto_url'] ?? '').toString(),
        bg: r['bg'] == null ? 0xFF128C7E : (r['bg'] as num).toInt(),
        creadoEn: DateTime.tryParse((r['creado_en'] ?? '').toString())
                ?.toLocal() ??
            DateTime.fromMillisecondsSinceEpoch(0),
        musicaTitulo: (r['musica_titulo'] ?? '').toString(),
        musicaArtista: (r['musica_artista'] ?? '').toString(),
        musicaPreview: (r['musica_preview'] ?? '').toString(),
        musicaArt: (r['musica_art'] ?? '').toString(),
        musicaInicioMs: (r['musica_inicio_ms'] as num?)?.toInt() ?? 0,
        musicaTrackUrl: (r['musica_track_url'] ?? '').toString(),
      );
}
