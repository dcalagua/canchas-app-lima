import 'package:flutter/material.dart';

import '../state/app_state.dart';
import '../theme.dart';
import 'hazte_pro_screen.dart';
import 'jugadores_disponibles_screen.dart';
import 'mis_retos_screen.dart';
import 'ranking_global_screen.dart';

/// CIRCUITO (hub del deporte). Agrupa TODO lo competitivo del circuito —ranking,
/// retos, jugadores disponibles y la membresía Pro— en un solo lugar. Hoy el
/// circuito es una capa de **TENIS**; cuando entre fútbol tendrá su propio
/// circuito con sus propias reglas, así que estos accesos NO deben vivir sueltos
/// en el Perfil (confundirían al mezclar deportes): cada deporte, lo suyo.
class CircuitoScreen extends StatelessWidget {
  const CircuitoScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return Scaffold(
      appBar: AppBar(title: const Text('Circuito')),
      body: ListenableBuilder(
        listenable: appState,
        builder: (context, _) {
          return ListView(
            padding: const EdgeInsets.fromLTRB(18, 8, 18, 24),
            children: [
              // Encabezado: hoy el circuito es de tenis.
              Row(
                children: [
                  Container(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 10, vertical: 5),
                    decoration: BoxDecoration(
                        color: limaSuave,
                        borderRadius: BorderRadius.circular(999)),
                    child: const Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(Icons.sports_tennis, size: 15, color: bosque),
                        SizedBox(width: 6),
                        Text('Tenis',
                            style: TextStyle(
                                color: bosque,
                                fontWeight: FontWeight.w700,
                                fontSize: 12.5)),
                      ],
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 10),
              Text('La liga de tenis de Pichangol',
                  style: t.titleMedium?.copyWith(fontWeight: FontWeight.w800)),
              const SizedBox(height: 4),
              Text('Rankea por tu ciudad, reta a otros jugadores y sube en la '
                  'tabla. Cada deporte tendrá su propio circuito.',
                  style: TextStyle(color: textoTenueDe(context), fontSize: 13)),
              const SizedBox(height: 16),

              _CircuitoTile(
                icon: Icons.emoji_events_outlined,
                title: 'Ranking global',
                subtitle: 'La tabla del circuito por ciudad',
                onTap: () => Navigator.of(context).push(MaterialPageRoute(
                    builder: (_) => const RankingGlobalScreen())),
              ),
              _CircuitoTile(
                icon: Icons.person_add_alt_1,
                title: 'Retar a alguien',
                subtitle: 'Jugadores disponibles para un partido',
                onTap: () => Navigator.of(context).push(MaterialPageRoute(
                    builder: (_) => const JugadoresDisponiblesScreen())),
              ),
              _CircuitoTile(
                icon: Icons.sports_kabaddi,
                title: 'Mis retos',
                subtitle: 'Rétalos, juega y sube en el ranking',
                badge: appState.retosPendientes,
                onTap: () => Navigator.of(context)
                    .push(MaterialPageRoute(
                        builder: (_) => const MisRetosScreen()))
                    .then((_) => appState.cargarRetosPendientes()),
              ),
              _CircuitoTile(
                icon: appState.proActivo
                    ? Icons.workspace_premium
                    : Icons.star_border,
                title: appState.proActivo
                    ? 'Pichangol Pro ✓'
                    : 'Hazte Pichangol Pro',
                subtitle: appState.proActivo
                    ? 'Tu membresía del circuito está activa'
                    : 'Tu carnet oficial y el ranking del circuito',
                onTap: () => Navigator.of(context).push(MaterialPageRoute(
                    builder: (_) => const HazteProScreen())),
              ),
            ],
          );
        },
      ),
    );
  }
}

/// Tile del hub del circuito (mismo lenguaje visual que el menú de Perfil).
class _CircuitoTile extends StatelessWidget {
  const _CircuitoTile({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.onTap,
    this.badge = 0,
  });

  final IconData icon;
  final String title;
  final String subtitle;
  final VoidCallback onTap;
  final int badge;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    Widget avatar = CircleAvatar(
      radius: 20,
      backgroundColor: limaSuave,
      child: Icon(icon, color: bosque, size: 20),
    );
    if (badge > 0) {
      avatar = Badge.count(
        count: badge,
        backgroundColor: bosque,
        textColor: Colors.white,
        child: avatar,
      );
    }
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: trazo),
        boxShadow: const [
          BoxShadow(color: Color(0x0F000000), blurRadius: 8, offset: Offset(0, 3)),
        ],
      ),
      child: ListTile(
        leading: avatar,
        title: Text(title,
            style: t.titleSmall?.copyWith(fontWeight: FontWeight.w700)),
        subtitle: Text(subtitle,
            style: t.bodySmall?.copyWith(color: textoTenueDe(context))),
        trailing: const Icon(Icons.chevron_right, color: textoTenue),
        onTap: onTap,
      ),
    );
  }
}
