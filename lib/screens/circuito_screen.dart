import 'unirse_campeonato_sheet.dart';
import 'package:flutter/material.dart';

import '../models/models.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/responsive.dart';
import 'hazte_pro_screen.dart';
import 'jugadores_disponibles_screen.dart';
import 'mis_retos_screen.dart';
import 'perfil_global_screen.dart';
import 'ranking_global_screen.dart';
import 'reto_dobles_screen.dart';

/// CIRCUITO (hub del deporte). Agrupa TODO lo competitivo del circuito —ranking,
/// retos, jugadores disponibles y la membresía Pro— en un solo lugar. Hoy el
/// circuito es una capa de **TENIS**; cuando entre fútbol tendrá su propio
/// circuito con sus propias reglas, así que estos accesos NO deben vivir sueltos
/// en el Perfil (confundirían al mezclar deportes): cada deporte, lo suyo.
class CircuitoScreen extends StatelessWidget {
  const CircuitoScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Liga de tenis Pichangol'),
        actions: [
          IconButton(
            tooltip: 'Unirme a un campeonato (enlace o código)',
            icon: const Icon(Icons.link),
            onPressed: () => UnirseCampeonato.mostrar(context),
          ),
        ],
      ),
      body: ListenableBuilder(
        listenable: appState,
        builder: (context, _) {
          return ListView(
            // Regla app: contenido centrado (ancho máx) en pantallas anchas.
            padding: EdgeInsets.fromLTRB(
                ladoTablet(context, 18, 640), 8, ladoTablet(context, 18, 640), 24),
            children: [
              // Hero de la liga: gradiente de marca, 🎾 y estado del circuito.
              _HeroLiga(perfil: appState.miPerfilCircuito),
              const SizedBox(height: 16),

              // Unirse a un campeonato con el enlace/código que te compartieron
              // (destacado: es la vía para inscribirte a un torneo ajeno).
              _CircuitoTile(
                icon: Icons.qr_code_2,
                color: bosque,
                title: 'Unirme a un campeonato',
                subtitle: 'Pega el enlace o código que te compartieron',
                onTap: () => UnirseCampeonato.mostrar(context),
              ),
              _CircuitoTile(
                icon: Icons.emoji_events,
                color: amarillo,
                title: 'Ranking global',
                subtitle: 'La tabla del circuito por ciudad',
                onTap: () => Navigator.of(context).push(MaterialPageRoute(
                    builder: (_) => const RankingGlobalScreen())),
              ),
              _CircuitoTile(
                icon: Icons.person_add_alt_1,
                color: morado,
                title: 'Retar a alguien',
                subtitle: 'Jugadores disponibles para un partido',
                onTap: () => Navigator.of(context).push(MaterialPageRoute(
                    builder: (_) => const JugadoresDisponiblesScreen())),
              ),
              _CircuitoTile(
                icon: Icons.groups,
                color: lima,
                title: 'Reto de dobles',
                subtitle: 'Tú y tu pareja contra otra pareja (2 vs 2)',
                onTap: () => Navigator.of(context).push(MaterialPageRoute(
                    builder: (_) =>
                        const RetoDoblesScreen(deporte: Deporte.tenis))),
              ),
              _CircuitoTile(
                icon: Icons.sports_kabaddi,
                color: naranja,
                title: 'Mis retos',
                subtitle: 'Rétalos, juega y sube en el ranking',
                badge: appState.retosPendientes,
                onTap: () => Navigator.of(context)
                    .push(MaterialPageRoute(
                        builder: (_) => const MisRetosScreen()))
                    .then((_) => appState.cargarRetosPendientes()),
              ),
              _CircuitoTile(
                icon: Icons.bar_chart,
                color: teal,
                title: 'Mis estadísticas',
                subtitle: 'Tu carnet: jugados, ganados y puntos',
                onTap: () async {
                  final email = (appState.usuario?.email ?? '').toLowerCase();
                  if (email.isEmpty) return;
                  // Asegura los datos para consolidar el carnet.
                  await appState.cargarAcademiasRemotas();
                  await appState.cargarRetosResultados();
                  if (!context.mounted) return;
                  Navigator.of(context).push(MaterialPageRoute(
                      builder: (_) => PerfilGlobalScreen(
                          idKey: 'e:$email',
                          deporte: Deporte.tenis,
                          posicion: 0)));
                },
              ),
              _CircuitoTile(
                icon: appState.proActivo
                    ? Icons.workspace_premium
                    : Icons.star,
                color: amarillo,
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

/// Hero de la Liga: tarjeta con gradiente de marca, la pelota 🎾 grande y el
/// estado del jugador en el circuito. Le da vida a la pantalla.
class _HeroLiga extends StatelessWidget {
  const _HeroLiga({required this.perfil});
  final Map<String, dynamic>? perfil;

  @override
  Widget build(BuildContext context) {
    final enCircuito = perfil != null;
    final zona = (perfil?['zona'] ?? '').toString();
    final categoria = (perfil?['categoria'] ?? '').toString();
    final detalle = [
      if (zona.isNotEmpty) zona,
      if (categoria.isNotEmpty) 'Cat. $categoria',
    ].join(' · ');
    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        gradient: const LinearGradient(
            colors: [bosque, teal],
            begin: Alignment.topLeft,
            end: Alignment.bottomRight),
        borderRadius: BorderRadius.circular(20),
        boxShadow: const [
          BoxShadow(color: Color(0x22000000), blurRadius: 14, offset: Offset(0, 6)),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                width: 56,
                height: 56,
                alignment: Alignment.center,
                decoration: const BoxDecoration(
                    color: Colors.white24, shape: BoxShape.circle),
                child: Text(emojiDeporte(Deporte.tenis),
                    style: const TextStyle(fontSize: 30)),
              ),
              const SizedBox(width: 14),
              const Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('Liga de tenis Pichangol',
                        style: TextStyle(
                            color: Colors.white,
                            fontWeight: FontWeight.w900,
                            fontSize: 18)),
                    SizedBox(height: 2),
                    Text('Rankea, reta y sube en tu ciudad',
                        style: TextStyle(color: Colors.white70, fontSize: 13)),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 14),
          // Pastilla de estado: dentro del circuito o invitación a unirse.
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
            decoration: BoxDecoration(
                color: Colors.white.withOpacity(0.15),
                borderRadius: BorderRadius.circular(999)),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(enCircuito ? Icons.check_circle : Icons.emoji_events,
                    color: enCircuito ? lima : amarillo, size: 18),
                const SizedBox(width: 8),
                Flexible(
                  child: Text(
                      enCircuito
                          ? (detalle.isNotEmpty
                              ? 'Estás en el circuito · $detalle'
                              : 'Estás en el circuito')
                          : 'Únete al circuito y deja que te reten',
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                          color: Colors.white,
                          fontWeight: FontWeight.w700,
                          fontSize: 12.5)),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// Tile del hub del circuito (mismo lenguaje visual que el menú de Perfil).
class _CircuitoTile extends StatelessWidget {
  const _CircuitoTile({
    required this.icon,
    required this.color,
    required this.title,
    required this.subtitle,
    required this.onTap,
    this.badge = 0,
  });

  final IconData icon;
  final Color color;
  final String title;
  final String subtitle;
  final VoidCallback onTap;
  final int badge;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    Widget avatar = CircleAvatar(
      radius: 20,
      backgroundColor: color,
      child: Icon(icon, color: Colors.white, size: 20),
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
