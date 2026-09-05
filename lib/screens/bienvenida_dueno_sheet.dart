import 'package:flutter/material.dart';

import '../state/app_state.dart';
import '../theme.dart';

/// Mensaje de BIENVENIDA al dueño (onboarding con el "stack de valor" de la
/// estrategia comercial: docs/estrategia-comercial-dueno.md). Se muestra UNA
/// sola vez, al entrar por primera vez a "Mis canchas". Reencuadra la comisión
/// como "por éxito" (pagas solo cuando ganas) y lista todo lo que recibe gratis.
class BienvenidaDuenoSheet {
  /// Muestra el sheet si el dueño no lo ha visto aún. Lo marca como visto.
  static Future<void> mostrarSiCorresponde(BuildContext context) async {
    if (appState.bienvenidaDuenoVista) return;
    appState.marcarBienvenidaDueno();
    if (!context.mounted) return;
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => const _BienvenidaDuenoSheet(),
    );
  }
}

class _BienvenidaDuenoSheet extends StatelessWidget {
  const _BienvenidaDuenoSheet();

  static const _valor = <(IconData, String, String)>[
    (Icons.person_add_alt_1, 'Clientes nuevos',
        'Te encuentran en el mapa, no solo tus habituales.'),
    (Icons.event_available, 'Reservas 24/7',
        'Dejas de contestar el teléfono a cada rato.'),
    (Icons.verified_user, 'Jugadores verificados',
        'Menos plantones: se paga al reservar.'),
    (Icons.insights, 'Panel y reportes',
        'Sabes cuánto facturas, sin cuadernos.'),
    (Icons.school, 'Academia incluida',
        'Alumnos, cuotas, morosos y cobros en un solo lugar.'),
    (Icons.star, 'Destaca tu cancha',
        'Más visibilidad para que te reserven más.'),
  ];

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final t = Theme.of(context).textTheme;
    return Container(
      decoration: BoxDecoration(
        color: cs.surface,
        borderRadius: const BorderRadius.vertical(top: Radius.circular(24)),
      ),
      padding: EdgeInsets.fromLTRB(
          20, 10, 20, 20 + MediaQuery.of(context).padding.bottom),
      child: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Center(
              child: Container(
                width: 44,
                height: 5,
                decoration: BoxDecoration(
                    color: Colors.black12,
                    borderRadius: BorderRadius.circular(10)),
              ),
            ),
            const SizedBox(height: 18),
            // Encabezado verde WhatsApp.
            Container(
              padding: const EdgeInsets.all(18),
              decoration: BoxDecoration(
                gradient: const LinearGradient(
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                  colors: [lima, teal],
                ),
                borderRadius: BorderRadius.circular(18),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      const Icon(Icons.handshake, color: Colors.white, size: 26),
                      const SizedBox(width: 10),
                      Expanded(
                        child: Text('¡Bienvenido, socio!',
                            style: t.titleLarge?.copyWith(
                                color: Colors.white,
                                fontWeight: FontWeight.w800)),
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  Text(
                      'Pichangol es tu socio digital: te traemos clientes y te '
                      'damos el sistema para manejar todo tu negocio.',
                      style: t.bodyMedium?.copyWith(
                          color: Colors.white.withOpacity(0.95), height: 1.35)),
                ],
              ),
            ),
            const SizedBox(height: 16),
            Text('Lo que recibes',
                style: t.titleMedium?.copyWith(fontWeight: FontWeight.w800)),
            const SizedBox(height: 10),
            for (final v in _valor) _FilaValor(icono: v.$1, titulo: v.$2, sub: v.$3),
            const SizedBox(height: 14),
            // Reencuadre de la comisión (por éxito).
            Container(
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                  color: limaSuave, borderRadius: BorderRadius.circular(14)),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Icon(Icons.paid_outlined, color: bosque, size: 22),
                  const SizedBox(width: 10),
                  Expanded(
                    child: RichText(
                      text: TextSpan(
                        style: t.bodyMedium?.copyWith(color: bosque, height: 1.35),
                        children: const [
                          TextSpan(
                              text: 'Cobramos comisión solo cuando tú cobras. ',
                              style: TextStyle(fontWeight: FontWeight.w800)),
                          TextSpan(
                              text:
                                  'Si nadie te reserva, no pagas nada. El sistema '
                                  'para manejar tu negocio es gratis.'),
                        ],
                      ),
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 18),
            SizedBox(
              width: double.infinity,
              child: FilledButton(
                style: FilledButton.styleFrom(
                    backgroundColor: lima,
                    foregroundColor: Colors.white,
                    padding: const EdgeInsets.symmetric(vertical: 15)),
                onPressed: () => Navigator.of(context).pop(),
                child: const Text('Empezar',
                    style: TextStyle(fontWeight: FontWeight.w800, fontSize: 15)),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _FilaValor extends StatelessWidget {
  const _FilaValor(
      {required this.icono, required this.titulo, required this.sub});
  final IconData icono;
  final String titulo;
  final String sub;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 40,
            height: 40,
            decoration: BoxDecoration(
                color: teal, borderRadius: BorderRadius.circular(11)),
            child: Icon(icono, color: Colors.white, size: 21),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(titulo,
                    style: t.titleSmall?.copyWith(fontWeight: FontWeight.w800)),
                const SizedBox(height: 1),
                Text(sub,
                    style: t.bodySmall?.copyWith(
                        color: textoTenueDe(context), height: 1.3)),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
