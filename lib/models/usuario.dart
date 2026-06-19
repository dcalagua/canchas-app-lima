/// Usuario jugador (logueado con Google al momento de reservar).
class Usuario {
  final String nombre;
  final String email;
  final String? fotoUrl;

  const Usuario({required this.nombre, required this.email, this.fotoUrl});

  Map<String, dynamic> toJson() =>
      {'nombre': nombre, 'email': email, 'fotoUrl': fotoUrl};

  factory Usuario.fromJson(Map<String, dynamic> j) => Usuario(
        nombre: j['nombre'] as String,
        email: j['email'] as String,
        fotoUrl: j['fotoUrl'] as String?,
      );
}
