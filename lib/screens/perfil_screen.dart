import 'package:flutter/material.dart';

import '../brand.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/google_logo.dart';
import '../widgets/nivel_chip.dart';
import '../widgets/responsive.dart';
import 'nivel_onboarding_screen.dart';
import 'mis_clases_screen.dart';
import 'mis_bonos_screen.dart';
import 'mis_pagos_screen.dart';
import 'entrenador_screen.dart';
import 'mis_puntos_screen.dart';
import 'mis_reservas_screen.dart';
import 'marketplace_screen.dart';
import '../widgets/banner_pro.dart';
import 'ajustes_screen.dart';
import 'anfitrion_screen.dart';
import 'login_google_sheet.dart';
import 'cuenta_screen.dart';
import 'circuito_screen.dart';
import 'editar_perfil_screen.dart';

/// Pestaña PERFIL del jugador, rediseñada al UI/UX de Airbnb:
///  - Título "Perfil" grande + acción arriba a la derecha.
///  - Tarjeta de identidad: avatar + nombre GRANDE y columna de estadísticas
///    reales (reservas, deportes con nivel, retos) con separadores.
///  - Fila de 2 tarjetas cuadradas (Mis reservas / Marketplace "NOVEDAD").
///  - Banner "¿Tienes una cancha?" (equivalente a "Conviértete en anfitrión").
///  - Lista plana con íconos de LÍNEA (no tarjetas), dividers por grupo.
///  - Botón flotante charcoal "Cambiar a modo anfitrión" abajo al centro.
class PerfilScreen extends StatelessWidget {
  const PerfilScreen({super.key});

  void _irAnfitrion(BuildContext context) {
    Navigator.of(context).push(
        MaterialPageRoute(builder: (_) => const AnfitrionScreen()));
  }

  /// Título "Perfil" grande + botón editar (estilo Airbnb).
  Widget _tituloFila(BuildContext context, dynamic u) {
    final cs = Theme.of(context).colorScheme;
    return Row(
      children: [
        Text('Perfil',
            style: TextStyle(
                fontSize: 32,
                fontWeight: FontWeight.w800,
                letterSpacing: -0.5,
                color: cs.onSurface)),
        const Spacer(),
        if (u != null)
          Material(
            color: const Color(0xFFF0F1EF),
            shape: const CircleBorder(),
            child: InkWell(
              customBorder: const CircleBorder(),
              onTap: () => Navigator.of(context).push(MaterialPageRoute(
                  builder: (_) => const EditarPerfilScreen())),
              child: const Padding(
                padding: EdgeInsets.all(11),
                child: Icon(Icons.edit_outlined, size: 20, color: tinta),
              ),
            ),
          ),
      ],
    );
  }

  /// Columna IZQUIERDA (tablet) / bloque superior (móvil): identidad, login,
  /// tarjetas cuadradas, banner anfitrión y nivel de jugador.
  List<Widget> _colIzquierda(BuildContext context, dynamic u) => [
        _TarjetaIdentidad(u: u),
        const SizedBox(height: 14),
        if (u == null) ...[
          SizedBox(
            width: double.infinity,
            child: FilledButton.icon(
              onPressed: () => LoginGoogleSheet.mostrar(context,
                  motivo: 'acceder a tu cuenta'),
              icon: Container(
                padding: const EdgeInsets.all(3),
                decoration: const BoxDecoration(
                    color: Colors.white, shape: BoxShape.circle),
                child: const GoogleLogo(size: 18),
              ),
              label: const Text('Iniciar sesión con Google'),
            ),
          ),
          const SizedBox(height: 14),
        ],
        if (u != null) ...[
          Row(
            children: [
              Expanded(
                child: _TarjetaCuadrada(
                  emoji: '📅',
                  titulo: 'Mis reservas',
                  onTap: () => Navigator.of(context).push(MaterialPageRoute(
                      builder: (_) => const MisReservasScreen())),
                ),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: _TarjetaCuadrada(
                  emoji: '🛍️',
                  titulo: 'Marketplace',
                  badge: 'NOVEDAD',
                  onTap: () => Navigator.of(context).push(MaterialPageRoute(
                      builder: (_) => const MarketplaceScreen())),
                ),
              ),
            ],
          ),
          const SizedBox(height: 14),
        ],
        _BannerAnfitrion(onTap: () => _irAnfitrion(context)),
        const SizedBox(height: 14),
        if (u != null) ...[
          const _NivelCard(),
          const SizedBox(height: 8),
        ],
      ];

  /// Columna DERECHA (tablet) / bloque inferior (móvil): lista de opciones
  /// estilo Airbnb (íconos de línea + chevron).
  List<Widget> _colDerecha(BuildContext context, dynamic u) => [
        const SizedBox(height: 6),
        // Regla UX (decisión del director ago-2026): DESCUBRIR vive en
        // Explorar (chip 🎓 Academias); el Perfil es "lo mío". Por eso aquí
        // ya no va el catálogo de academias — va "Mis clases" SOLO si estás
        // matriculado (tú o tu hijo): tus clases, cuotas y pagos en un tap.
        if (appState.misMatriculas.isNotEmpty)
          _ItemAirbnb(
            icono: Icons.school_outlined,
            titulo: 'Mis clases y pagos',
            onTap: () => Navigator.of(context).push(
                MaterialPageRoute(builder: (_) => const MisClasesScreen())),
          ),
        if (u == null)
          _ItemAirbnb(
            icono: Icons.storefront_outlined,
            titulo: 'Marketplace Pichangol',
            onTap: () => Navigator.of(context).push(
                MaterialPageRoute(builder: (_) => const MarketplaceScreen())),
          ),
        if (u != null) ...[
          _ItemAirbnb(
            icono: Icons.confirmation_number_outlined,
            titulo: 'Mis bonos',
            onTap: () => Navigator.of(context).push(
                MaterialPageRoute(builder: (_) => const MisBonosScreen())),
          ),
          _ItemAirbnb(
            icono: Icons.receipt_long_outlined,
            titulo: 'Mis pagos',
            onTap: () => Navigator.of(context).push(
                MaterialPageRoute(builder: (_) => const MisPagosScreen())),
          ),
          _ItemAirbnb(
            icono: Icons.stars_outlined,
            titulo: appState.misPuntosDisponibles > 0
                ? 'Mis puntos · ${appState.misPuntosDisponibles} ⭐'
                : 'Mis puntos',
            onTap: () => Navigator.of(context).push(
                MaterialPageRoute(builder: (_) => const MisPuntosScreen())),
          ),
          _ItemAirbnb(
            icono: Icons.sports_tennis_outlined,
            titulo: 'Entrenador virtual',
            onTap: () => Navigator.of(context).push(
                MaterialPageRoute(builder: (_) => const EntrenadorScreen())),
          ),
          if (appState.usaCircuito)
            _ItemAirbnb(
              icono: Icons.emoji_events_outlined,
              titulo: 'Liga de tenis Pichangol',
              badge: appState.retosPendientes,
              onTap: () => Navigator.of(context)
                  .push(MaterialPageRoute(
                      builder: (_) => const CircuitoScreen()))
                  .then((_) => appState.cargarRetosPendientes()),
            ),
          _ItemAirbnb(
            icono: Icons.account_balance_wallet_outlined,
            titulo: 'Mi billetera',
            onTap: () => Navigator.of(context).push(
                MaterialPageRoute(builder: (_) => const CuentaScreen())),
          ),
        ],
        const Divider(height: 26, color: Color(0xFFEBEBEB)),
        _ItemAirbnb(
          icono: Icons.settings_outlined,
          titulo: 'Configuración de la cuenta',
          onTap: () => Navigator.of(context).push(
              MaterialPageRoute(builder: (_) => const AjustesScreen())),
        ),
        if (u != null)
          _ItemAirbnb(
            icono: Icons.logout,
            titulo: 'Cierra la sesión',
            onTap: () => appState.cerrarSesionUsuario(),
          ),
      ];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: ListenableBuilder(
        listenable: appState,
        builder: (context, _) {
          final u = appState.usuario;
          // TABLET/horizontal (>=900 px): DOS columnas — identidad y tarjetas
          // a la izquierda, lista de opciones a la derecha (como Airbnb en
          // pantallas anchas: se aprovecha el espacio sin estirar una columna).
          final esAncha = MediaQuery.sizeOf(context).width >= 900;
          final pie = Center(
            child: Text(kBrandEslogan,
                style:
                    TextStyle(fontSize: 12, color: textoTenueDe(context))),
          );
          if (esAncha) {
            return AnchoTablet(
              maxWidth: 1100,
              child: ListView(
                padding: EdgeInsets.fromLTRB(
                    28, 12 + MediaQuery.of(context).padding.top, 28, 110),
                children: [
                  _tituloFila(context, u),
                  // Hazte Pro bien visible (solo si NO es Pro).
                  const BannerPro(
                      margen: EdgeInsets.only(top: 14),
                      mensaje:
                          'Insignia PRO en el ranking, retos y beneficios '
                          'exclusivos en todo Pichangol.'),
                  const SizedBox(height: 16),
                  Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Expanded(
                          child: Column(children: _colIzquierda(context, u))),
                      const SizedBox(width: 28),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: _colDerecha(context, u),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 22),
                  pie,
                ],
              ),
            );
          }
          return AnchoTablet(
            maxWidth: 520,
            child: ListView(
              padding: EdgeInsets.fromLTRB(
                  20, 12 + MediaQuery.of(context).padding.top, 20, 110),
              children: [
                _tituloFila(context, u),
                // Hazte Pro bien visible (solo si NO es Pro).
                const BannerPro(
                    margen: EdgeInsets.only(top: 14),
                    // Si YA es Pro, la insignia va SOBRE la foto (no aquí).
                    insigniaSiPro: false,
                    mensaje: 'Insignia PRO en el ranking, retos y beneficios '
                        'exclusivos en todo Pichangol.'),
                const SizedBox(height: 16),
                ..._colIzquierda(context, u),
                ..._colDerecha(context, u),
                const SizedBox(height: 22),
                pie,
              ],
            ),
          );
        },
      ),
      // ── Botón flotante charcoal (como "Cambiar a modo anfitrión") ──
      floatingActionButtonLocation: FloatingActionButtonLocation.centerFloat,
      floatingActionButton: Material(
        elevation: 6,
        color: tinta,
        borderRadius: BorderRadius.circular(999),
        child: InkWell(
          borderRadius: BorderRadius.circular(999),
          onTap: () => _irAnfitrion(context),
          child: const Padding(
            padding: EdgeInsets.symmetric(horizontal: 20, vertical: 14),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(Icons.sync_alt, color: Colors.white, size: 18),
                SizedBox(width: 9),
                Text('Cambiar a modo anfitrión',
                    style: TextStyle(
                        color: Colors.white,
                        fontWeight: FontWeight.w800,
                        fontSize: 15)),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// Tarjeta de identidad estilo Airbnb: avatar grande + nombre enorme a la
/// izquierda; columna de ESTADÍSTICAS REALES a la derecha con separadores.
class _TarjetaIdentidad extends StatelessWidget {
  const _TarjetaIdentidad({required this.u});
  final dynamic u;

  Widget _stat(BuildContext context, String valor, String etiqueta,
      {bool divisor = true, VoidCallback? onTap}) {
    // LINK DIRECTO (pedido del director): tocar la estadística lleva a su
    // pantalla (reservas / nivel / retos), con chevron para que se note.
    final col = Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(valor,
            style: const TextStyle(
                fontSize: 22, fontWeight: FontWeight.w800, color: tinta)),
        Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Flexible(
              child: Text(etiqueta,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                      fontSize: 12.5,
                      fontWeight: FontWeight.w600,
                      color: textoTenueDe(context))),
            ),
            if (onTap != null)
              Icon(Icons.chevron_right,
                  size: 15, color: textoTenueDe(context)),
          ],
        ),
        if (divisor)
          Container(
            margin: const EdgeInsets.symmetric(vertical: 10),
            height: 1,
            width: 110,
            color: const Color(0xFFEBEBEB),
          ),
      ],
    );
    if (onTap == null) return col;
    return InkWell(
        onTap: onTap, borderRadius: BorderRadius.circular(8), child: col);
  }

  @override
  Widget build(BuildContext context) {
    final reservas = appState.misReservas.length;
    final deportes = appState.misNiveles.length;
    final retos = appState.retosPendientes;
    return Container(
      padding: const EdgeInsets.fromLTRB(20, 24, 20, 24),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface,
        borderRadius: BorderRadius.circular(22),
        boxShadow: const [
          BoxShadow(
              color: Color(0x14000000), blurRadius: 14, offset: Offset(0, 4)),
        ],
      ),
      child: Row(
        children: [
          // Avatar + nombre (centrados, como Airbnb).
          Expanded(
            child: Column(
              children: [
                Stack(
                  clipBehavior: Clip.none,
                  children: [
                    CircleAvatar(
                      radius: 46,
                      backgroundColor: limaSuave,
                      backgroundImage: u?.fotoUrl != null
                          ? NetworkImage(u!.fotoUrl!)
                          : null,
                      child: u?.fotoUrl == null
                          ? const Icon(Icons.person, size: 42, color: bosque)
                          : null,
                    ),
                    // Sello verificado (como el escudo rosado de Airbnb).
                    if (u != null && appState.estaVerificado(u!.email))
                      const Positioned(
                        right: -2,
                        bottom: -2,
                        child: CircleAvatar(
                          radius: 14,
                          backgroundColor: bosque,
                          child: Icon(Icons.verified_user,
                              size: 15, color: Colors.white),
                        ),
                      ),
                    // Insignia PRO SOBRE la foto (pedido del director): chip
                    // charcoal con corona dorada, esquina superior de la foto.
                    if (u != null && appState.proActivo)
                      Positioned(
                        top: -6,
                        right: -12,
                        child: Container(
                          padding: const EdgeInsets.symmetric(
                              horizontal: 8, vertical: 3),
                          decoration: BoxDecoration(
                            color: tinta,
                            borderRadius: BorderRadius.circular(999),
                            border: Border.all(color: Colors.white, width: 2),
                            boxShadow: const [
                              BoxShadow(
                                  color: Color(0x33000000),
                                  blurRadius: 6,
                                  offset: Offset(0, 2)),
                            ],
                          ),
                          child: const Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Icon(Icons.workspace_premium,
                                  size: 13, color: Color(0xFFD9B45A)),
                              SizedBox(width: 3),
                              Text('PRO',
                                  style: TextStyle(
                                      color: Colors.white,
                                      fontWeight: FontWeight.w800,
                                      fontSize: 10.5,
                                      letterSpacing: 0.4)),
                            ],
                          ),
                        ),
                      ),
                  ],
                ),
                const SizedBox(height: 10),
                Text(
                  (u?.nombre ?? 'Invitado').toString().split(' ').first,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                      fontSize: 28,
                      fontWeight: FontWeight.w800,
                      letterSpacing: -0.5,
                      color: tinta),
                ),
                Text(
                  u?.email ?? 'Inicia sesión para reservar',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                      fontSize: 12.5, color: textoTenueDe(context)),
                ),
              ],
            ),
          ),
          const SizedBox(width: 18),
          // Estadísticas reales con separadores (como 30 Viajes / 24 Reseñas).
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _stat(context, '$reservas',
                  reservas == 1 ? 'Reserva' : 'Reservas',
                  onTap: () => Navigator.of(context).push(MaterialPageRoute(
                      builder: (_) => const MisReservasScreen()))),
              _stat(context, '$deportes',
                  deportes == 1 ? 'Deporte con nivel' : 'Deportes con nivel',
                  onTap: () => Navigator.of(context).push(MaterialPageRoute(
                      builder: (_) => const NivelOnboardingScreen()))),
              _stat(context, '$retos',
                  retos == 1 ? 'Reto pendiente' : 'Retos pendientes',
                  divisor: false,
                  onTap: () => Navigator.of(context).push(MaterialPageRoute(
                      builder: (_) => const CircuitoScreen()))),
            ],
          ),
        ],
      ),
    );
  }
}

/// Tarjeta cuadrada (como "Viajes anteriores"/"Conexiones" de Airbnb): emoji
/// grande arriba, título abajo, badge opcional "NOVEDAD".
class _TarjetaCuadrada extends StatelessWidget {
  const _TarjetaCuadrada(
      {required this.emoji,
      required this.titulo,
      required this.onTap,
      this.badge});
  final String emoji;
  final String titulo;
  final String? badge;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Theme.of(context).colorScheme.surface,
      borderRadius: BorderRadius.circular(20),
      elevation: 0,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(20),
        child: Container(
          padding: const EdgeInsets.fromLTRB(16, 18, 16, 16),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(20),
            boxShadow: const [
              BoxShadow(
                  color: Color(0x12000000),
                  blurRadius: 12,
                  offset: Offset(0, 4)),
            ],
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Text(emoji, style: const TextStyle(fontSize: 34)),
                  const Spacer(),
                  if (badge != null)
                    Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 9, vertical: 4),
                      decoration: BoxDecoration(
                        color: bosque,
                        borderRadius: BorderRadius.circular(999),
                      ),
                      child: Text(badge!,
                          style: const TextStyle(
                              color: Colors.white,
                              fontSize: 10,
                              fontWeight: FontWeight.w800,
                              letterSpacing: 0.4)),
                    ),
                ],
              ),
              const SizedBox(height: 22),
              Text(titulo,
                  style: const TextStyle(
                      fontSize: 16.5,
                      fontWeight: FontWeight.w800,
                      color: tinta)),
            ],
          ),
        ),
      ),
    );
  }
}

/// Banner "¿Tienes una cancha?" (equivalente al "Conviértete en anfitrión").
class _BannerAnfitrion extends StatelessWidget {
  const _BannerAnfitrion({required this.onTap});
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Theme.of(context).colorScheme.surface,
      borderRadius: BorderRadius.circular(20),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(20),
        child: Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(20),
            boxShadow: const [
              BoxShadow(
                  color: Color(0x12000000),
                  blurRadius: 12,
                  offset: Offset(0, 4)),
            ],
          ),
          child: Row(
            children: [
              Container(
                width: 54,
                height: 54,
                decoration: BoxDecoration(
                  color: limaSuave,
                  borderRadius: BorderRadius.circular(14),
                ),
                child: const Center(
                    child: Text('🏟️', style: TextStyle(fontSize: 28))),
              ),
              const SizedBox(width: 14),
              const Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('¿Tienes una cancha o academia?',
                        style: TextStyle(
                            fontSize: 15.5,
                            fontWeight: FontWeight.w800,
                            color: tinta)),
                    SizedBox(height: 2),
                    Text(
                        'Publícala y genera ingresos adicionales, '
                        '¡es muy sencillo!',
                        style:
                            TextStyle(fontSize: 12.5, color: textoTenue)),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Tarjeta "Nivel de jugador" (capa social estilo Playtomic). Si aún no me
/// autoevalué, muestra un CTA para hacerlo; si ya, muestra mis niveles por
/// deporte como pastillas y deja reevaluar/agregar otro.
class _NivelCard extends StatelessWidget {
  const _NivelCard();

  void _abrir(BuildContext context) {
    Navigator.of(context).push(MaterialPageRoute(
        builder: (_) => const NivelOnboardingScreen()));
  }

  @override
  Widget build(BuildContext context) {
    final tengo = appState.tengoNivel;
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: const Color(0xFFE4E4E4)),
        boxShadow: const [
          BoxShadow(
              color: Color(0x0F000000), blurRadius: 8, offset: Offset(0, 2)),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.military_tech, color: lima),
              const SizedBox(width: 8),
              const Text('Tu nivel de jugador',
                  style: TextStyle(fontWeight: FontWeight.w800, fontSize: 16)),
            ],
          ),
          const SizedBox(height: 4),
          Text(
            tengo
                ? 'Sube o baja solo con tus resultados en retos y campeonatos.'
                : 'Autoevalúate en 30 segundos y encuentra rivales de tu nivel.',
            style: const TextStyle(color: textoTenue, fontSize: 13),
          ),
          const SizedBox(height: 12),
          if (tengo) ...[
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                for (final n in appState.misNiveles) NivelChip(nivel: n),
              ],
            ),
            const SizedBox(height: 6),
            Align(
              alignment: Alignment.centerLeft,
              child: TextButton.icon(
                style: TextButton.styleFrom(padding: EdgeInsets.zero),
                onPressed: () => _abrir(context),
                icon: const Icon(Icons.add, size: 18, color: teal),
                label: const Text('Reevaluar / agregar deporte',
                    style: TextStyle(color: teal, fontWeight: FontWeight.w700)),
              ),
            ),
          ] else
            SizedBox(
              width: double.infinity,
              child: FilledButton.icon(
                style: FilledButton.styleFrom(
                    backgroundColor: lima,
                    padding: const EdgeInsets.symmetric(vertical: 12)),
                onPressed: () => _abrir(context),
                icon: const Icon(Icons.sports_soccer),
                label: const Text('Descubre tu nivel',
                    style: TextStyle(fontWeight: FontWeight.w800)),
              ),
            ),
        ],
      ),
    );
  }
}

/// Ítem de lista estilo Airbnb: SIN tarjeta — ícono de línea charcoal, título
/// grande, chevron a la derecha, respiro generoso.
class _ItemAirbnb extends StatelessWidget {
  const _ItemAirbnb(
      {required this.icono,
      required this.titulo,
      required this.onTap,
      this.badge = 0});
  final IconData icono;
  final String titulo;
  final VoidCallback onTap;
  final int badge;

  @override
  Widget build(BuildContext context) {
    Widget lead = Icon(icono, size: 26, color: tinta);
    if (badge > 0) {
      lead = Badge.count(
        count: badge,
        backgroundColor: bosque,
        textColor: Colors.white,
        child: lead,
      );
    }
    return InkWell(
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 15),
        child: Row(
          children: [
            lead,
            const SizedBox(width: 16),
            Expanded(
              child: Text(titulo,
                  style: TextStyle(
                      fontSize: 16.5,
                      fontWeight: FontWeight.w600,
                      color: Theme.of(context).colorScheme.onSurface)),
            ),
            const Icon(Icons.chevron_right, color: Color(0xFF9A9A9A)),
          ],
        ),
      ),
    );
  }
}
