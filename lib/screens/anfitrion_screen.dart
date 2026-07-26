import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../services/growth_service.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/ancho_lectura.dart';
import 'campeonato_detalle_screen.dart';
import 'crear_campeonato_screen.dart';
import 'home_shell.dart';
import 'login_google_sheet.dart';
import 'academia_shell.dart';
import 'mis_productos_screen.dart';
import 'verificador_screen.dart';

/// Modo anfitrión (estilo Airbnb): un solo lugar con todo lo del anfitrión —
/// publicar/administrar canchas y academias, y el rol de verificador. Separa el
/// mundo "jugador" (perfil) del mundo "anfitrión".
class AnfitrionScreen extends StatelessWidget {
  const AnfitrionScreen({super.key});

  /// Los paneles de administración (Mis canchas / Mi academia) son master-detail
  /// pensados para pantalla ANCHA: al entrar forzamos horizontal y al volver
  /// restauramos la orientación libre.
  static const _horizontal = [
    DeviceOrientation.landscapeLeft,
    DeviceOrientation.landscapeRight,
  ];
  Future<void> _restaurarOrientacion() =>
      SystemChrome.setPreferredOrientations(DeviceOrientation.values);

  Future<void> _abrirPanel(BuildContext context) async {
    if (!await LoginGoogleSheet.mostrar(context,
        motivo: 'administrar tus canchas')) {
      return;
    }
    if (!context.mounted) return;
    await SystemChrome.setPreferredOrientations(_horizontal);
    if (!context.mounted) {
      await _restaurarOrientacion();
      return;
    }
    await Navigator.of(context)
        .push(MaterialPageRoute(builder: (_) => const HomeShell()));
    await _restaurarOrientacion();
  }

  Future<void> _abrirMiAcademia(BuildContext context) async {
    if (!await LoginGoogleSheet.mostrar(context,
        motivo: 'administrar tu academia')) {
      return;
    }
    if (!context.mounted) return;
    await SystemChrome.setPreferredOrientations(_horizontal);
    if (!context.mounted) {
      await _restaurarOrientacion();
      return;
    }
    // Siempre a MiAcademiaScreen: él resuelve si mostrar la academia, un spinner
    // mientras baja de la nube, o "Crear mi academia" cuando ya es seguro que no
    // hay ninguna. Así evitamos crear una academia DUPLICADA por adelantarnos a
    // que Supabase responda (típico tras reinstalar el APK).
    await Navigator.of(context).push(
        MaterialPageRoute(builder: (_) => const AcademiaShell()));
    await _restaurarOrientacion();
  }

  /// Organizar un campeonato SIN academia (cualquier usuario): crea el torneo
  /// como organizador independiente y salta a su ficha para invitar/inscribir.
  Future<void> _organizarCampeonato(BuildContext context) async {
    if (!await LoginGoogleSheet.mostrar(context,
        motivo: 'organizar un campeonato')) {
      return;
    }
    if (!context.mounted) return;
    final c = await Navigator.of(context).push(MaterialPageRoute(
        builder: (_) => const CrearCampeonatoScreen(academiaId: '')));
    if (c == null || !context.mounted) return;
    Navigator.of(context).push(MaterialPageRoute(
        builder: (_) => CampeonatoDetalleScreen(campeonatoId: c.id)));
  }

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return Scaffold(
      body: AnchoLectura(
        child: ListView(
        padding: EdgeInsets.zero,
        children: [
          // Header degradado.
          Container(
            width: double.infinity,
            padding: EdgeInsets.fromLTRB(
                22, 18 + MediaQuery.of(context).padding.top, 22, 24),
            decoration: const BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
                colors: [lima, teal], // verde WhatsApp
              ),
              borderRadius: BorderRadius.vertical(bottom: Radius.circular(24)),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    GestureDetector(
                      onTap: () => Navigator.of(context).maybePop(),
                      child: const Padding(
                        padding: EdgeInsets.only(right: 10),
                        child: Icon(Icons.arrow_back_ios_new,
                            color: Colors.white, size: 20),
                      ),
                    ),
                    Text('Modo anfitrión',
                        style: t.headlineSmall?.copyWith(
                            color: Colors.white, fontWeight: FontWeight.w700)),
                  ],
                ),
                const SizedBox(height: 10),
                Text(
                    'Publica tu cancha o academia y recibe reservas y alumnos.',
                    style: t.bodyMedium?.copyWith(color: Colors.white70)),
              ],
            ),
          ),
          const SizedBox(height: 16),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 18),
            child: Column(
              children: [
                _Tile(
                  icon: Icons.storefront,
                  color: teal,
                  title: 'Mis canchas',
                  subtitle:
                      'Registra y administra: canchas, agenda, reservas, cuenta',
                  onTap: () => _abrirPanel(context),
                ),
                _Tile(
                  icon: Icons.sports,
                  color: naranja,
                  title: 'Mi academia',
                  subtitle: 'Soy profe: alumnos, cuotas y cobros',
                  onTap: () => _abrirMiAcademia(context),
                ),
                _Tile(
                  icon: Icons.emoji_events,
                  color: amarillo,
                  title: 'Organizar campeonato',
                  subtitle: 'Torneo de fútbol, tenis y más: invita, sortea y juega',
                  onTap: () => _organizarCampeonato(context),
                ),
                _Tile(
                  icon: Icons.storefront,
                  color: morado,
                  title: 'Mi tienda',
                  subtitle:
                      'Vende en el Marketplace Pichangol: raquetas, pelotas y más',
                  onTap: () => Navigator.of(context).push(MaterialPageRoute(
                      builder: (_) => const MisProductosScreen())),
                ),
                if (GrowthService.disponible)
                  _Tile(
                    icon: Icons.verified_user,
                    color: lima,
                    title: 'Verificador',
                    subtitle: 'Rol de campo: visitas con foto, GPS y firma',
                    onTap: () => Navigator.of(context).push(MaterialPageRoute(
                        builder: (_) => const VerificadorScreen())),
                  ),
              ],
            ),
          ),
          const SizedBox(height: 30),
        ],
      )),
    );
  }
}

class _Tile extends StatelessWidget {
  const _Tile(
      {required this.icon,
      required this.title,
      required this.subtitle,
      required this.onTap,
      this.color = lima});
  final IconData icon;
  final String title;
  final String subtitle;
  final VoidCallback onTap;
  final Color color;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
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
        leading: CircleAvatar(
          radius: 20,
          backgroundColor: color,
          child: Icon(icon, color: Colors.white, size: 20),
        ),
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
