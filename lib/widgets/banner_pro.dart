import 'package:flutter/material.dart';

import '../screens/hazte_pro_screen.dart';
import '../state/app_state.dart';
import '../theme.dart';

/// Banner "Hazte Pro" — visible en los puntos de mayor tráfico SOLO si el
/// usuario NO es Pro (pedido del director: que la membresía se vea en toda la
/// app). Tarjeta premium (gradiente bosque, mismo look que HazteProScreen),
/// mensaje por contexto y chevron → pantalla de suscripción. Si ya es Pro,
/// no ocupa ni un píxel (se reconstruye solo al cambiar el estado).
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
        if (appState.proActivo) return const SizedBox.shrink();
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
}
