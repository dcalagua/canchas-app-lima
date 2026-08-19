import 'package:flutter/material.dart';

import '../screens/hazte_pro_screen.dart';
import '../state/app_state.dart';
import '../theme.dart';

/// Banner "Hazte Pro" — visible en los puntos de mayor tráfico (pedido del
/// director: que la membresía se vea en toda la app):
///  - NO Pro → tarjeta premium (gradiente bosque, mismo look que
///    HazteProScreen), mensaje por contexto y chevron → suscripción.
///  - YA Pro → INSIGNIA compacta "Eres Pichangol PRO ⭐" (membresía activa),
///    tap → la misma pantalla (ver estado/beneficios).
/// Se reconstruye solo al cambiar el estado (activar Pro convierte el banner
/// en insignia al instante).
class BannerPro extends StatelessWidget {
  const BannerPro({super.key, this.mensaje = '', this.margen});

  /// Beneficio a resaltar según la pantalla (vacío = mensaje general).
  final String mensaje;

  /// Margen externo (default: horizontal 16, vertical 8).
  final EdgeInsetsGeometry? margen;

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: appState,
      builder: (context, _) {
        if (appState.proActivo) return _insignia(context);
        return Padding(
          padding: margen ??
              const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
          child: Material(
            color: Colors.transparent,
            child: InkWell(
              borderRadius: BorderRadius.circular(18),
              onTap: () => Navigator.of(context).push(
                  MaterialPageRoute(builder: (_) => const HazteProScreen())),
              child: Container(
                padding: const EdgeInsets.all(14),
                decoration: BoxDecoration(
                  gradient: const LinearGradient(
                    begin: Alignment.topLeft,
                    end: Alignment.bottomRight,
                    colors: [bosque, Color(0xFF1E5C4C)],
                  ),
                  borderRadius: BorderRadius.circular(18),
                  boxShadow: const [
                    BoxShadow(
                        color: Color(0x22000000),
                        blurRadius: 12,
                        offset: Offset(0, 5)),
                  ],
                ),
                child: Row(
                  children: [
                    Container(
                      width: 40,
                      height: 40,
                      decoration: BoxDecoration(
                        color: lima,
                        borderRadius: BorderRadius.circular(12),
                      ),
                      child: const Icon(Icons.workspace_premium,
                          color: Colors.white, size: 24),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Text('Hazte Pro',
                              style: TextStyle(
                                  color: Colors.white,
                                  fontWeight: FontWeight.w800,
                                  fontSize: 15.5)),
                          const SizedBox(height: 2),
                          Text(
                            mensaje.isNotEmpty
                                ? mensaje
                                : 'Desbloquea todo Pichangol: reserva manual, '
                                    'bloqueo de horas, campeonatos y más.',
                            style: TextStyle(
                                color: Colors.white.withOpacity(0.88),
                                fontSize: 12,
                                height: 1.3),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(width: 6),
                    const Icon(Icons.chevron_right,
                        color: Colors.white, size: 22),
                  ],
                ),
              ),
            ),
          ),
        );
      },
    );
  }

  /// Insignia compacta para el usuario que YA es Pro: pill charcoal con la
  /// corona dorada y "Eres Pichangol PRO". Menos alta que el banner de venta
  /// (ya no hay nada que vender, solo lucir el estado).
  Widget _insignia(BuildContext context) {
    return Padding(
      padding:
          margen ?? const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          borderRadius: BorderRadius.circular(999),
          onTap: () => Navigator.of(context).push(
              MaterialPageRoute(builder: (_) => const HazteProScreen())),
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
            decoration: BoxDecoration(
              color: tinta,
              borderRadius: BorderRadius.circular(999),
              boxShadow: const [
                BoxShadow(
                    color: Color(0x1A000000),
                    blurRadius: 10,
                    offset: Offset(0, 4)),
              ],
            ),
            child: Row(
              children: [
                const Icon(Icons.workspace_premium,
                    color: Color(0xFFF2C94C), size: 20),
                const SizedBox(width: 8),
                const Expanded(
                  child: Text('Eres Pichangol PRO',
                      style: TextStyle(
                          color: Colors.white,
                          fontWeight: FontWeight.w800,
                          fontSize: 13.5)),
                ),
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                  decoration: BoxDecoration(
                    color: lima,
                    borderRadius: BorderRadius.circular(999),
                  ),
                  child: const Text('ACTIVO',
                      style: TextStyle(
                          color: Colors.white,
                          fontWeight: FontWeight.w800,
                          fontSize: 10.5,
                          letterSpacing: 0.4)),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
