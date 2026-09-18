/// Una entrada del historial de llamadas (registro estilo WhatsApp).
class LlamadaHistorial {
  const LlamadaHistorial({
    required this.nombre,
    required this.foto,
    required this.email,
    required this.saliente,
    required this.conectada,
    required this.duracionSeg,
    required this.video,
    required this.cuando,
    this.rechazada = false,
  });

  final String nombre;
  final String foto;
  final String email;
  final bool saliente; // true = yo llamé; false = me llamaron
  final bool conectada; // ¿se llegó a hablar?
  final int duracionSeg;
  final bool video;
  final DateTime cuando;
  final bool rechazada; // entrante que YO rechacé (colgué el timbre)

  /// Perdida = entrante que no se contestó (ni se rechazó).
  bool get perdida => !saliente && !conectada && !rechazada;

  Map<String, dynamic> toJson() => {
        'nombre': nombre,
        'foto': foto,
        'email': email,
        'saliente': saliente,
        'conectada': conectada,
        'duracionSeg': duracionSeg,
        'video': video,
        'rechazada': rechazada,
        'ts': cuando.millisecondsSinceEpoch,
      };

  factory LlamadaHistorial.fromJson(Map<String, dynamic> m) => LlamadaHistorial(
        nombre: (m['nombre'] ?? '').toString(),
        foto: (m['foto'] ?? '').toString(),
        email: (m['email'] ?? '').toString(),
        saliente: m['saliente'] == true,
        conectada: m['conectada'] == true,
        duracionSeg: (m['duracionSeg'] as num?)?.toInt() ?? 0,
        video: m['video'] == true,
        rechazada: m['rechazada'] == true,
        cuando: DateTime.fromMillisecondsSinceEpoch(
            (m['ts'] as num?)?.toInt() ?? 0),
      );
}
