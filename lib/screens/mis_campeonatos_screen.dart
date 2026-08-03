import 'package:flutter/material.dart';

import '../models/campeonato.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/ancho_lectura.dart';
import '../widgets/dialogo_pichangol.dart';
import 'campeonato_detalle_screen.dart';
import 'crear_campeonato_screen.dart';
import 'hazte_pro_screen.dart';
import 'login_google_sheet.dart';

/// "Mis campeonatos": TODOS los campeonatos que el usuario organiza, con o sin
/// academia. Antes, un campeonato creado desde Anfitrión (sin academia) no
/// aparecía en ninguna lista y "se perdía". Aquí siempre está, y re-sincroniza
/// desde la nube al abrir (no depende de reiniciar la app).
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
    if (!appState.proActivo) {
      final ir = await confirmarPichangol(
        context,
        titulo: 'Organizar es Pichangol Pro',
        mensaje: 'Crear y administrar tus propios campeonatos (fixture, '
            'inscripciones, resultados) es parte de Pichangol Pro. Hazte Pro '
            'para organizar los tuyos.',
        textoConfirmar: 'Hazte Pro',
        icono: Icons.workspace_premium,
      );
      if (ir != true || !mounted) return;
      await Navigator.of(context).push(
          MaterialPageRoute(builder: (_) => const HazteProScreen()));
      if (!mounted || !appState.proActivo) return; // sigue sin Pro → no crea
    }
    final c = await Navigator.of(context).push<Campeonato>(MaterialPageRoute(
        builder: (_) => const CrearCampeonatoScreen(academiaId: '')));
    if (c == null || !mounted) return;
    Navigator.of(context).push(MaterialPageRoute(
        builder: (_) => CampeonatoDetalleScreen(campeonatoId: c.id)));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Mis campeonatos')),
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
          return RefreshIndicator(
            onRefresh: () => appState.cargarCampeonatosRemotos(),
            child: AnchoLectura(
              child: lista.isEmpty
                  ? ListView(children: const [SizedBox(height: 90), _Vacio()])
                  : ListView(
                      padding: const EdgeInsets.fromLTRB(16, 12, 16, 90),
                      children: [
                        for (final c in lista) _CampCard(campeonato: c),
                      ],
                    ),
            ),
          );
        },
      ),
    );
  }
}

class _CampCard extends StatelessWidget {
  const _CampCard({required this.campeonato});
  final Campeonato campeonato;

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
            '${c.deporte.etiqueta} · ${c.formato.etiqueta} · '
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
        Text('Aún no organizas campeonatos',
            style: t.titleMedium?.copyWith(fontWeight: FontWeight.w800)),
        const SizedBox(height: 6),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 40),
          child: Text(
              'Toca “Organizar” para crear tu torneo (fútbol, tenis, natación…), '
              'invitar y que se inscriban.',
              textAlign: TextAlign.center,
              style: t.bodySmall?.copyWith(color: textoTenueDe(context))),
        ),
      ],
    );
  }
}
