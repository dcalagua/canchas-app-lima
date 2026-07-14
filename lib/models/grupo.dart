/// Un grupo de chat entre usuarios registrados. Los mensajes del grupo viven en
/// `pichangol_mensajes` con `tipo='grupo'` y `ref_id=grupo.id`. Los miembros
/// (emails) viven en `pichangol_grupo_miembros`.
class Grupo {
  final String id;
  final String nombre;
  final String creadorEmail;
  final List<String> miembros; // emails (incluye al creador)

  const Grupo({
    required this.id,
    required this.nombre,
    required this.creadorEmail,
    this.miembros = const [],
  });

  Grupo copyWith({List<String>? miembros}) => Grupo(
        id: id,
        nombre: nombre,
        creadorEmail: creadorEmail,
        miembros: miembros ?? this.miembros,
      );

  Map<String, dynamic> toInsert() => {
        'id': id,
        'nombre': nombre,
        'creador_email': creadorEmail.trim().toLowerCase(),
      };

  factory Grupo.fromRow(Map<String, dynamic> r) => Grupo(
        id: (r['id'] ?? '').toString(),
        nombre: (r['nombre'] ?? '').toString(),
        creadorEmail: (r['creador_email'] ?? '').toString(),
      );
}
