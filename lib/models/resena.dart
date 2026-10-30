/// Una reseña de un jugador sobre una cancha/local (⭐ + comentario). Reemplaza
/// el rating "presentacional" por reputación real. Se guarda en Supabase
/// (`pichangol_resenas`), una por (cancha, autor) — el jugador puede editarla.
class Resena {
  final String id;
  final String canchaId;
  final String autorEmail;
  final String autorNombre;
  final int estrellas; // 1..5
  final String comentario;
  final DateTime creado;

  const Resena({
    required this.id,
    required this.canchaId,
    required this.autorEmail,
    required this.autorNombre,
    required this.estrellas,
    this.comentario = '',
    required this.creado,
  });

  Map<String, dynamic> toInsert() => {
        'id': id,
        'cancha_id': canchaId,
        'autor_email': autorEmail,
        'autor_nombre': autorNombre,
        'estrellas': estrellas,
        'comentario': comentario,
        // `creado` lo pone el servidor (default now()).
      };

  factory Resena.fromRow(Map<String, dynamic> r) => Resena(
        id: (r['id'] ?? '').toString(),
        canchaId: (r['cancha_id'] ?? '').toString(),
        autorEmail: (r['autor_email'] ?? '').toString(),
        autorNombre: (r['autor_nombre'] ?? '').toString(),
        estrellas: ((r['estrellas'] ?? 0) as num).toInt(),
        comentario: (r['comentario'] ?? '').toString(),
        creado: DateTime.tryParse((r['creado'] ?? '').toString())?.toLocal() ??
            DateTime.now(),
      );
}

/// Resumen agregado de reseñas de un local (promedio + cantidad).
class ResumenResenas {
  final double promedio;
  final int cantidad;
  const ResumenResenas(this.promedio, this.cantidad);
  bool get hay => cantidad > 0;
}
