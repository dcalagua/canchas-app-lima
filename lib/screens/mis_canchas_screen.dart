import 'package:flutter/material.dart';

import '../models/club.dart';
import '../models/models.dart';
import '../services/pagos_service.dart';
import '../state/app_state.dart';
import '../theme.dart';
import 'agregar_cancha_screen.dart';
import 'editar_cancha_screen.dart';
import 'recargar_saldo_screen.dart';
import 'registrar_cancha_screen.dart';
import '../utils/moneda.dart';

/// Canchas del dueño agrupadas por LOCAL (un local = varias canchas, posibles
/// de distintos deportes). Cada local permite agregar más canchas y editar las
/// existentes (precio, deporte, horario, fotos).
class MisCanchasScreen extends StatefulWidget {
  const MisCanchasScreen({super.key});

  @override
  State<MisCanchasScreen> createState() => _MisCanchasScreenState();
}

class _MisCanchasScreenState extends State<MisCanchasScreen> {
  @override
  void initState() {
    super.initState();
    // Al abrir, pregunta al backend si el admin ya aprobó alguna cancha pendiente
    // (quita el cartel "pendiente" y habilita reservas si así fue).
    appState.sincronizarPropiedades();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      floatingActionButton: FloatingActionButton.extended(
        backgroundColor: pino,
        foregroundColor: lima,
        onPressed: () => Navigator.of(context).push(
          MaterialPageRoute(builder: (_) => const RegistrarCanchaScreen()),
        ),
        icon: const Icon(Icons.add_location_alt),
        label: const Text('Nuevo local'),
      ),
      body: ListenableBuilder(
        listenable: appState,
        builder: (context, _) {
          final canchas = appState.misCanchas;
          final hayPendientes = canchas.any((c) => c.pendienteVerificacion);
          final locales = Club.agrupar(canchas);
          return Column(
            children: [
              _HeaderMisCanchas(
                  nLocales: locales.length, nCanchas: canchas.length),
              Expanded(
                child: RefreshIndicator(
                  onRefresh: () => appState.sincronizarPropiedades(),
                  child: canchas.isEmpty
                      ? ListView(
                          children: const [SizedBox(height: 60), _Vacio()])
                      : ListView(
                          padding: const EdgeInsets.fromLTRB(18, 16, 18, 90),
                          children: [
                            const _DestacarCanchasCard(),
                            const SizedBox(height: 14),
                            if (hayPendientes) ...[
                              const _AvisoPendiente(),
                              const SizedBox(height: 14),
                            ],
                            // Tablet/landscape: grilla de 2-3 columnas.
                            if (MediaQuery.of(context).size.width >= 720)
                              _GridLocales(locales: locales)
                            else
                              for (final local in locales) ...[
                                _LocalCard(local: local),
                                const SizedBox(height: 14),
                              ],
                          ],
                        ),
                ),
              ),
            ],
          );
        },
      ),
    );
  }
}

/// "Destaca tus canchas": prepago que pone tus canchas primero en Explorar (con
/// medalla), igual que las academias. Más saldo = mejor nivel (Bronce/Plata/Oro).
class _DestacarCanchasCard extends StatefulWidget {
  const _DestacarCanchasCard();
  @override
  State<_DestacarCanchasCard> createState() => _DestacarCanchasCardState();
}

class _DestacarCanchasCardState extends State<_DestacarCanchasCard> {
  Map<String, int>? _vistas; // {semana, total} de impresiones de tus canchas

  @override
  void initState() {
    super.initState();
    appState.sincronizarSaldo();
    appState.cargarDestacados();
    _cargarVistas();
  }

  Future<void> _cargarVistas() async {
    final email = appState.usuario?.email;
    if (email == null || email.isEmpty) return;
    final v = await PagosService.resumenVistas([email]);
    if (mounted && v != null) setState(() => _vistas = v);
  }

  Future<void> _recargar() async {
    final monto = await Navigator.of(context).push<int>(MaterialPageRoute(
      builder: (_) => const RecargarSaldoScreen(titulo: 'Destacar mis canchas'),
    ));
    if (monto != null && mounted) {
      appState.recargar(monto); // refleja el saldo al instante
      await appState.sincronizarSaldo();
      await appState.cargarDestacados();
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final saldo = appState.saldoClub;
    final nivel = appState.nivelDestacadoPropio;
    final destacada = nivel > 0;
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [Color(0xFF128C7E), Color(0xFF075E54)],
        ),
        borderRadius: BorderRadius.circular(18),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(destacada ? Icons.star : Icons.trending_up,
                  color: Colors.white, size: 20),
              const SizedBox(width: 8),
              Text(
                  destacada
                      ? '${medallaDestacado(nivel)} Nivel ${etiquetaNivelDestacado(nivel)}'
                      : 'Destaca tus canchas',
                  style: t.titleMedium?.copyWith(
                      color: Colors.white, fontWeight: FontWeight.w800)),
            ],
          ),
          const SizedBox(height: 6),
          Text(
            destacada
                ? 'Tus canchas salen primero en Explorar. Saldo: $monedaSimbolo $saldo. '
                    'Más saldo = mejor posición: Plata desde $monedaSimbolo 50, Oro desde $monedaSimbolo 200.'
                : 'Pon saldo y tus canchas aparecen destacadas (arriba y con '
                    'medalla) para que más jugadores las reserven. '
                    'Bronce desde $monedaSimbolo 1, Plata $monedaSimbolo 50, Oro $monedaSimbolo 200.',
            style: t.bodySmall
                ?.copyWith(color: Colors.white.withOpacity(0.92), height: 1.3),
          ),
          if (_vistas != null && (_vistas!['semana'] ?? 0) > 0) ...[
            const SizedBox(height: 10),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
              decoration: BoxDecoration(
                color: Colors.white.withOpacity(0.16),
                borderRadius: BorderRadius.circular(10),
              ),
              child: Text(
                '👀 ${_vistas!['semana']} jugadores vieron tus canchas esta semana'
                '${(_vistas!['total'] ?? 0) > (_vistas!['semana'] ?? 0) ? ' · ${_vistas!['total']} en total' : ''}',
                style: t.bodySmall
                    ?.copyWith(color: Colors.white, fontWeight: FontWeight.w700),
              ),
            ),
          ],
          const SizedBox(height: 12),
          SizedBox(
            width: double.infinity,
            child: FilledButton.icon(
              style: FilledButton.styleFrom(
                  backgroundColor: Colors.white, foregroundColor: lima),
              onPressed: _recargar,
              icon: const Icon(Icons.add),
              label: Text(saldo > 0
                  ? 'Recargar y destacar ($monedaSimbolo $saldo)'
                  : 'Poner saldo y destacar'),
            ),
          ),
        ],
      ),
    );
  }
}

/// Grilla de locales (2-3 columnas) para tablet/landscape.
class _GridLocales extends StatelessWidget {
  const _GridLocales({required this.locales});
  final List<Club> locales;
  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(builder: (context, cons) {
      final cols = cons.maxWidth >= 1100 ? 3 : 2;
      final w = (cons.maxWidth - 14 * (cols - 1)) / cols;
      return Wrap(
        spacing: 14,
        runSpacing: 14,
        children: [
          for (final local in locales)
            SizedBox(width: w, child: _LocalCard(local: local)),
        ],
      );
    });
  }
}

/// Header premium (degradado sage) del panel "Mis canchas", igual que la Agenda.
class _HeaderMisCanchas extends StatelessWidget {
  const _HeaderMisCanchas({required this.nLocales, required this.nCanchas});
  final int nLocales;
  final int nCanchas;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return Container(
      width: double.infinity,
      padding: EdgeInsets.fromLTRB(
          22, 18 + MediaQuery.of(context).padding.top, 22, 20),
      decoration: const BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [sage, verde, bosque],
        ),
        borderRadius: BorderRadius.vertical(bottom: Radius.circular(24)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Mis canchas',
              style: t.headlineSmall
                  ?.copyWith(color: Colors.white, fontWeight: FontWeight.w700)),
          const SizedBox(height: 2),
          Text(
            nCanchas == 0
                ? 'Registra o reclama tu primer local'
                : '$nLocales ${nLocales == 1 ? 'local' : 'locales'} · '
                    '$nCanchas ${nCanchas == 1 ? 'cancha' : 'canchas'}',
            style: t.bodyMedium?.copyWith(color: Colors.white70),
          ),
        ],
      ),
    );
  }
}

/// Aviso para el dueño cuando tiene canchas en revisión.
class _AvisoPendiente extends StatelessWidget {
  const _AvisoPendiente();

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: const Color(0xFFFBF3E2),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: const Color(0xFFF0DDB8)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text('⏳', style: TextStyle(fontSize: 18)),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Tienes canchas en revisión',
                    style: t.bodyMedium?.copyWith(
                        fontWeight: FontWeight.w800, color: clayOscuro)),
                const SizedBox(height: 3),
                Text(
                  'Ya puedes editar precio, deporte, horario y fotos tocando la '
                  'cancha. Cuando el equipo apruebe la propiedad se habilitan las '
                  'reservas. Desliza hacia abajo para actualizar el estado.',
                  style:
                      t.bodySmall?.copyWith(color: textoTenue, height: 1.35),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// Tarjeta de un LOCAL: cabecera + sus canchas (editar al tocar) + botón para
/// agregar otra cancha al mismo local.
class _LocalCard extends StatelessWidget {
  const _LocalCard({required this.local});
  final Club local;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final cs = Theme.of(context).colorScheme;
    final n = local.canchas.length;
    return Container(
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: trazo),
      ),
      padding: const EdgeInsets.fromLTRB(14, 14, 14, 6),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(Icons.storefront, color: cs.primary, size: 20),
              const SizedBox(width: 8),
              Expanded(
                child: Text(local.nombre,
                    style: t.titleMedium?.copyWith(fontWeight: FontWeight.w800),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis),
              ),
              Text('$n ${n == 1 ? 'cancha' : 'canchas'}',
                  style: t.bodySmall?.copyWith(color: textoTenueDe(context))),
            ],
          ),
          if (local.direccion != null) ...[
            const SizedBox(height: 3),
            Text(local.direccion!,
                style: t.bodySmall?.copyWith(color: textoTenueDe(context)),
                maxLines: 1,
                overflow: TextOverflow.ellipsis),
          ],
          const SizedBox(height: 8),
          for (final c in local.canchas) _FilaCancha(cancha: c),
          Align(
            alignment: Alignment.centerLeft,
            child: TextButton.icon(
              onPressed: () => Navigator.of(context).push(
                MaterialPageRoute(
                    builder: (_) => AgregarCanchaScreen(local: local.principal)),
              ),
              icon: Icon(Icons.add, color: cs.primary, size: 20),
              label: Text('Agregar cancha',
                  style:
                      TextStyle(color: cs.primary, fontWeight: FontWeight.w700)),
            ),
          ),
        ],
      ),
    );
  }
}

/// Una cancha dentro del local: punto del deporte, nombre, deporte/precio/horario
/// y acceso a editar. Marca "⏳" si está pendiente de verificación.
class _FilaCancha extends StatelessWidget {
  const _FilaCancha({required this.cancha});
  final Cancha cancha;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return InkWell(
      borderRadius: BorderRadius.circular(12),
      onTap: () => Navigator.of(context).push(
        MaterialPageRoute(builder: (_) => EditarCanchaScreen(cancha: cancha)),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 9),
        child: Row(
          children: [
            Container(
              width: 10,
              height: 10,
              decoration: BoxDecoration(
                  color: colorDeporte(cancha.deporte),
                  borderRadius: BorderRadius.circular(3)),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(cancha.nombre,
                      style:
                          t.bodyMedium?.copyWith(fontWeight: FontWeight.w700),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis),
                  Text(
                    '${cancha.deporte.etiqueta} · ${cancha.monedaSimbolo} ${cancha.precioHora.toStringAsFixed(2)}/h · '
                    '${cancha.horaApertura}–${cancha.horaCierre}',
                    style: t.bodySmall?.copyWith(color: textoTenueDe(context)),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                ],
              ),
            ),
            if (cancha.pendienteVerificacion)
              Container(
                margin: const EdgeInsets.only(right: 6),
                padding:
                    const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                decoration: BoxDecoration(
                    color: const Color(0xFFFBEAD2),
                    borderRadius: BorderRadius.circular(999)),
                child: const Text('⏳ Por verificar',
                    style: TextStyle(
                        color: clayOscuro,
                        fontSize: 10,
                        fontWeight: FontWeight.w700)),
              ),
            Icon(Icons.chevron_right, color: textoTenueDe(context)),
          ],
        ),
      ),
    );
  }
}

class _Vacio extends StatelessWidget {
  const _Vacio();

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.add_location_alt, size: 64, color: verdeClaro),
            const SizedBox(height: 16),
            Text('Aún no registras canchas',
                style: t.titleMedium?.copyWith(fontWeight: FontWeight.w700)),
            const SizedBox(height: 6),
            Text(
              'Registra tu local para que aparezca en Pichangol; luego puedes '
              'agregarle todas las canchas que tengas.',
              textAlign: TextAlign.center,
              style: t.bodyMedium?.copyWith(color: textoTenueDe(context)),
            ),
            const SizedBox(height: 18),
            FilledButton.icon(
              style: FilledButton.styleFrom(
                  backgroundColor: pino, foregroundColor: lima),
              onPressed: () => Navigator.of(context).push(
                MaterialPageRoute(
                    builder: (_) => const RegistrarCanchaScreen()),
              ),
              icon: const Icon(Icons.add_location_alt),
              label: const Text('Registrar mi local'),
            ),
          ],
        ),
      ),
    );
  }
}
