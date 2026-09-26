import 'package:flutter/material.dart';

import '../models/campeonato.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../utils/pro_gate.dart';
import '../widgets/ancho_lectura.dart';
import 'campeonato_detalle_screen.dart';
import 'crear_campeonato_screen.dart';
import 'login_google_sheet.dart';
import 'unirse_campeonato_sheet.dart';

/// "Mis campeonatos": TODOS los campeonatos que el usuario organiza, con o sin
/// academia. Antes, un campeonato creado desde Anfitrión (sin academia) no
/// aparecía en ninguna lista y "se perdía". Aquí siempre está, y re-sincroniza
/// desde la nube al abrir (no depende de reiniciar la app).
///
/// También es la pantalla del JUGADOR (queja del director, 26-sep-2026: "tengo
/// el código pero solo me sale Organizar"): botón "Unirme con código o enlace"
/// en la barra y en el vacío, y sección "Donde participo" con los torneos en
/// los que está inscrito / en un plantel, para volver a ellos.
class MisCampeonatosScreen extends StatefulWidget {
  const MisCampeonatosScreen({super.key});

  @override
  State<MisCampeonatosScreen> createState() => _MisCampeonatosScreenState();
}

class _MisCampeonatosScreenState extends State<MisCampeonatosScreen> {
  @override
  void initState() {
    super.initState();
    // Re-baja los campeonatos de la nube (no solo en el splash).
    appState.cargarCampeonatosRemotos();
  }

  Future<void> _organizar() async {
    if (!await LoginGoogleSheet.mostrar(context,
        motivo: 'organizar un campeonato')) {
      return;
    }
    if (!mounted) return;
    // Candado Pichangol Pro: organizar campeonatos es feature de la suscripción.
    final ok = await exigirPro(context,
        motivo: 'Crear y administrar tus propios campeonatos (fixture, '
            'inscripciones, resultados) es parte de Pichangol Pro. Hazte Pro '
            'para organizar los tuyos.');
    if (!ok || !mounted) return;
    final c = await Navigator.of(context).push<Campeonato>(MaterialPageRoute(
        builder: (_) => const CrearCampeonatoScreen(academiaId: '')));
    if (c == null || !mounted) return;
    Navigator.of(context).push(MaterialPageRoute(
        builder: (_) => CampeonatoDetalleScreen(campeonatoId: c.id)));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Mis campeonatos'),
        actions: [
          IconButton(
            tooltip: 'Unirme con código o enlace',
            icon: const Icon(Icons.qr_code_2),
            onPressed: () => UnirseCampeonato.mostrar(context),
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton.extended(
        backgroundColor: lima,
        foregroundColor: Colors.white,
        icon: const Icon(Icons.add),
        label: const Text('Organizar'),
        onPressed: _organizar,
      ),
      body: ListenableBuilder(
        listenable: appState,
        builder: (context, _) {
          final lista = appState.misCampeonatosOrganizados;
          final participo = appState.campeonatosDondeParticipo;
          return RefreshIndicator(
            onRefresh: () => appState.cargarCampeonatosRemotos(),
            child: AnchoLectura(
              child: lista.isEmpty && participo.isEmpty
                  ? ListView(children: const [SizedBox(height: 60), _Vacio()])
                  : ListView(
                      padding: const EdgeInsets.fromLTRB(16, 12, 16, 90),
                      children: [
                        // Jugador: unirse con el código/enlace del organizador
                        // o del capitán (siempre a la vista, no solo vacío).
                        _UnirmeTile(
                            onTap: () => UnirseCampeonato.mostrar(context)),
                        if (participo.isNotEmpty) ...[
                          const SizedBox(height: 14),
                          const _Titulo('Donde participo'),
                          for (final c in participo)
                            _CampCard(campeonato: c, rol: _rolEn(c)),
                        ],
                        if (lista.isNotEmpty) ...[
                          const SizedBox(height: 14),
                          const _Titulo('Organizo'),
                          for (final c in lista) _CampCard(campeonato: c),
                        ],
                      ],
                    ),
            ),
          );
        },
      ),
    );
  }
}

/// Cómo participo en [c]: nombre del equipo (fútbol) o "Inscrito".
String _rolEn(Campeonato c) {
  final yo = (appState.usuario?.email ?? '').toLowerCase();
  for (final p in c.participantes) {
    if (p.esEquipo &&
        (p.capitanEmail.toLowerCase() == yo ||
            p.roster.any((i) => i.email.toLowerCase() == yo))) {
      return p.capitanEmail.toLowerCase() == yo
          ? 'Capitán de ${p.nombre}'
          : 'En ${p.nombre}';
    }
  }
  return 'Inscrito';
}

class _Titulo extends StatelessWidget {
  const _Titulo(this.texto);
  final String texto;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(bottom: 8),
        child: Text(texto,
            style: Theme.of(context)
                .textTheme
                .titleMedium
                ?.copyWith(fontWeight: FontWeight.w800)),
      );
}

/// Tarjeta "Unirme a un campeonato" (estilo Airbnb, sin texto libre aquí: el
/// código se pega en la hoja). Es la entrada del JUGADOR con código.
class _UnirmeTile extends StatelessWidget {
  const _UnirmeTile({required this.onTap});
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final cs = Theme.of(context).colorScheme;
    return Container(
      decoration: BoxDecoration(
        color: cs.surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: trazo),
      ),
      child: ListTile(
        contentPadding:
            const EdgeInsets.symmetric(horizontal: 14, vertical: 4),
        leading: const CircleAvatar(
          backgroundColor: bosque,
          child: Icon(Icons.qr_code_2, color: Colors.white),
        ),
        title: Text('Unirme a un campeonato',
            style: t.titleMedium?.copyWith(fontWeight: FontWeight.w800)),
        subtitle: Text(
            'Pega el código o enlace del torneo o de tu equipo',
            style: t.bodySmall?.copyWith(color: textoTenueDe(context))),
        trailing: const Icon(Icons.chevron_right, color: textoTenue),
        onTap: onTap,
      ),
    );
  }
}

class _CampCard extends StatelessWidget {
  const _CampCard({required this.campeonato, this.rol});
  final Campeonato campeonato;

  /// Etiqueta de mi rol cuando NO soy el organizador ("En Kinder 01").
  final String? rol;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final cs = Theme.of(context).colorScheme;
    final c = campeonato;
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      decoration: BoxDecoration(
        color: cs.surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: trazo),
      ),
      child: ListTile(
        contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 6),
        leading: CircleAvatar(
          backgroundColor: colorDeporte(c.deporte),
          child: Icon(iconoDeporte(c.deporte), color: Colors.white),
        ),
        title: Text(c.nombre,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: t.titleMedium?.copyWith(fontWeight: FontWeight.w800)),
        subtitle: Text(
            rol != null
                ? '$rol · ${c.deporte.etiqueta} · ${c.formato.etiqueta}'
                : '${c.deporte.etiqueta} · ${c.formato.etiqueta} · '
                    '${c.participantes.length} inscritos'
                    '${c.academiaId.isEmpty ? ' · sin academia' : ''}',
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: t.bodySmall?.copyWith(color: textoTenueDe(context))),
        trailing: const Icon(Icons.chevron_right, color: textoTenue),
        onTap: () => Navigator.of(context).push(MaterialPageRoute(
            builder: (_) =>
                CampeonatoDetalleScreen(campeonatoId: c.id))),
      ),
    );
  }
}

class _Vacio extends StatelessWidget {
  const _Vacio();

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return Column(
      children: [
        Icon(Icons.emoji_events_outlined,
            size: 56, color: textoTenueDe(context)),
        const SizedBox(height: 12),
        Text('Aún no tienes campeonatos',
            style: t.titleMedium?.copyWith(fontWeight: FontWeight.w800)),
        const SizedBox(height: 6),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 40),
          child: Text(
              '¿Te compartieron un código o enlace? Únete y quedas inscrito '
              '(o en tu equipo). ¿Quieres el tuyo? Toca “Organizar” para crear '
              'tu torneo (fútbol, tenis, natación…), invitar y que se inscriban.',
              textAlign: TextAlign.center,
              style: t.bodySmall?.copyWith(color: textoTenueDe(context))),
        ),
        const SizedBox(height: 18),
        FilledButton.icon(
          style: FilledButton.styleFrom(
              backgroundColor: bosque,
              padding:
                  const EdgeInsets.symmetric(horizontal: 22, vertical: 14)),
          onPressed: () => UnirseCampeonato.mostrar(context),
          icon: const Icon(Icons.qr_code_2),
          label: const Text('Tengo un código · Unirme'),
        ),
      ],
    );
  }
}
