/// Un grupo de chat entre usuarios registrados. Los mensajes del grupo viven en
/// `pichangol_mensajes` con `tipo='grupo'` y `ref_id=grupo.id`. Los miembros
/// (emails) viven en `pichangol_grupo_miembros`.
class Grupo {
  final String id;
  final String nombre;
  final String creadorEmail;
  final String fotoUrl; // foto del grupo ('' = inicial de color)
  final List<String> miembros; // emails (incluye al creador)

  const Grupo({
    required this.id,
    required this.nombre,
    required this.creadorEmail,
    this.fotoUrl = '',
    this.miembros = const [],
  });

  Grupo copyWith({String? nombre, String? fotoUrl, List<String>? miembros}) =>
      Grupo(
        id: id,
        nombre: nombre ?? this.nombre,
        creadorEmail: creadorEmail,
        fotoUrl: fotoUrl ?? this.fotoUrl,
        miembros: miembros ?? this.miembros,
      );

  Map<String, dynamic> toInsert() => {
        'id': id,
        'nombre': nombre,
        'creador_email': creadorEmail.trim().toLowerCase(),
        if (fotoUrl.isNotEmpty) 'foto_url': fotoUrl,
      };

  factory Grupo.fromRow(Map<String, dynamic> r) => Grupo(
        id: (r['id'] ?? '').toString(),
        nombre: (r['nombre'] ?? '').toString(),
        creadorEmail: (r['creador_email'] ?? '').toString(),
        fotoUrl: (r['foto_url'] ?? '').toString(),
      );
}
