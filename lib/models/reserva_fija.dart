/// RESERVA FIJA ("pensionado"): un cliente que juega SIEMPRE el mismo día de la
/// semana a la misma hora en una cancha. El app genera solo las reservas de las
/// próximas semanas (ingreso estable, sin anotarlo a mano cada vez).
class ReservaFija {
  final String id;
  final String canchaId;
  final int diaSemana; // 1 = Lunes … 7 = Domingo (DateTime.weekday)
  final String hora; // 'HH:mm' de inicio
  final String clienteNombre;
  final String clienteEmail; // si tiene cuenta en el app (opcional)
  final String clienteTelefono; // WhatsApp (opcional)
  final bool activo;

  const ReservaFija({
    required this.id,
    required this.canchaId,
    required this.diaSemana,
    required this.hora,
    required this.clienteNombre,
    this.clienteEmail = '',
    this.clienteTelefono = '',
    this.activo = true,
  });

  ReservaFija copyWith({bool? activo}) => ReservaFija(
        id: id,
        canchaId: canchaId,
        diaSemana: diaSemana,
        hora: hora,
        clienteNombre: clienteNombre,
        clienteEmail: clienteEmail,
        clienteTelefono: clienteTelefono,
        activo: activo ?? this.activo,
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'canchaId': canchaId,
        'diaSemana': diaSemana,
        'hora': hora,
        'clienteNombre': clienteNombre,
        'clienteEmail': clienteEmail,
        'clienteTelefono': clienteTelefono,
        'activo': activo,
      };

  factory ReservaFija.fromJson(Map<String, dynamic> j) => ReservaFija(
        id: (j['id'] ?? '') as String,
        canchaId: (j['canchaId'] ?? '') as String,
        diaSemana: ((j['diaSemana'] ?? 1) as num).toInt(),
        hora: (j['hora'] ?? '') as String,
        clienteNombre: (j['clienteNombre'] ?? '') as String,
        clienteEmail: (j['clienteEmail'] ?? '') as String,
        clienteTelefono: (j['clienteTelefono'] ?? '') as String,
        activo: (j['activo'] ?? true) as bool,
      );
}
