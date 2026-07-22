import '../config/pais.dart';

/// Sujeto genérico de "Servicios Pichangol" (marketing): puede ser una
/// **Academia** o un **Club** (local con canchas). Desacopla la pantalla de
/// Servicios del tipo concreto para no duplicar el módulo.
///
/// Todo (suscripción, landing, redes, tarjeta de débito automático, saldo de
/// marketing) se llavea por [id].
class Negocio {
  final String id; // clave de landing/redes/suscripción/saldo de marketing
  final String nombre;
  final String monedaSimbolo;
  final PaisConfig pais;
  final String tipo; // 'academia' | 'club' | 'mixto'
  final bool tieneRedesRegistradas; // ¿ya declaró IG/FB/TikTok?
  final String landingUrl; // '' si aún no se generó
  final Map<String, dynamic> datosLanding; // datos para landing + posts

  const Negocio({
    required this.id,
    required this.nombre,
    required this.monedaSimbolo,
    required this.pais,
    required this.tipo,
    required this.tieneRedesRegistradas,
    required this.landingUrl,
    required this.datosLanding,
  });

  bool get esAcademia => tipo == 'academia';
  bool get esClub => tipo == 'club';

  /// Negocio UNIFICADO: el mismo dueño tiene academia + canchas. Un solo plan de
  /// Servicios Pichangol (una landing, una suscripción) cubre ambos; así no paga
  /// doble por lo mismo. La landing deja reservar cancha y matricularse.
  bool get esMixto => tipo == 'mixto';
  bool get tieneLanding => landingUrl.isNotEmpty;
}
