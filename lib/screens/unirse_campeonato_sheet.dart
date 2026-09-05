import 'package:flutter/material.dart';

import '../models/campeonato.dart';

import '../state/app_state.dart';
import '../theme.dart';
import 'campeonato_detalle_screen.dart';
import 'login_google_sheet.dart';

/// "Unirme a un campeonato": el invitado pega el **enlace** (o el **código/id**)
/// que le compartieron, la app trae ese campeonato de la nube y abre su ficha
/// para inscribirse — aunque no sea de una academia suya. Es el puente hasta que
/// haya deep-link nativo con el dominio de marca.
class UnirseCampeonato {
  UnirseCampeonato._();

  static Future<void> mostrar(BuildContext context) async {
    if (!await LoginGoogleSheet.mostrar(context, motivo: 'unirte a un campeonato')) {
      return;
    }
    if (!context.mounted) return;
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Theme.of(context).colorScheme.surface,
      shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(22))),
      builder: (_) => const _UnirseSheet(),
    );
  }
}

class _UnirseSheet extends StatefulWidget {
  const _UnirseSheet();

  @override
  State<_UnirseSheet> createState() => _UnirseSheetState();
}

class _UnirseSheetState extends State<_UnirseSheet> {
  final _ctrl = TextEditingController();
  bool _buscando = false;
  String? _error;
  List<Campeonato> _resultados = const []; // coincidencias por NOMBRE

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  Future<void> _buscar() async {
    setState(() {
      _error = null;
      _resultados = const [];
    });
    final texto = _ctrl.text.trim();
    if (texto.isEmpty) {
      setState(() =>
          _error = 'Pega el enlace/código, o escribe el nombre del torneo.');
      return;
    }
    setState(() => _buscando = true);
    // 1. Enlace / id / código exacto (como siempre).
    final c = await appState.buscarCampeonato(texto);
    if (!mounted) return;
    if (c != null) {
      setState(() => _buscando = false);
      _abrir(c);
      return;
    }
    // 2. Por NOMBRE (contiene): lista para elegir. Incluye torneos pasados —
    //    su ficha muestra ganadores, tabla y la galería de fotos.
    final lista = await appState.buscarCampeonatosPorNombre(texto);
    if (!mounted) return;
    setState(() {
      _buscando = false;
      _resultados = lista;
      if (lista.isEmpty) {
        _error = 'No encontramos ese campeonato. Revisa el enlace/código, '
            'prueba con otro nombre o revisa tu conexión.';
      }
    });
  }

  void _abrir(Campeonato c) {
    appState.agregarCampeonatoCache(c);
    Navigator.of(context).pop(); // cierra la hoja
    Navigator.of(context).push(MaterialPageRoute(
        builder: (_) => CampeonatoDetalleScreen(campeonatoId: c.id)));
  }

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final bottom = MediaQuery.of(context).viewInsets.bottom;
    return Padding(
      padding: EdgeInsets.fromLTRB(20, 16, 20, 20 + bottom),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.emoji_events, color: amarillo),
              const SizedBox(width: 8),
              Text('Unirme a un campeonato',
                  style: t.titleLarge?.copyWith(fontWeight: FontWeight.w800)),
            ],
          ),
          const SizedBox(height: 6),
          Text(
              'Pega el enlace o código que te compartieron, o busca el torneo '
              'por su nombre (también campeonatos pasados: verás ganadores, '
              'tabla y fotos).',
              style: t.bodySmall?.copyWith(color: textoTenueDe(context))),
          const SizedBox(height: 14),
          TextField(
            controller: _ctrl,
            autofocus: true,
            minLines: 1,
            maxLines: 2,
            onSubmitted: (_) => _buscar(),
            decoration: InputDecoration(
              hintText: 'Enlace, código o nombre del campeonato',
              errorText: _error,
              filled: true,
              fillColor: Theme.of(context).colorScheme.surface,
              border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(14),
                  borderSide: const BorderSide(color: Color(0xFFE4E4E4))),
              enabledBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(14),
                  borderSide: const BorderSide(color: Color(0xFFE4E4E4))),
            ),
          ),
          const SizedBox(height: 16),
          SizedBox(
            width: double.infinity,
            child: FilledButton.icon(
              style: FilledButton.styleFrom(backgroundColor: lima),
              onPressed: _buscando ? null : _buscar,
              icon: _buscando
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(
                          strokeWidth: 2, color: Colors.white))
                  : const Icon(Icons.search),
              label: Text(_buscando ? 'Buscando…' : 'Buscar campeonato'),
            ),
          ),
          if (_resultados.isNotEmpty) ...[
            const SizedBox(height: 14),
            Text('Coincidencias (${_resultados.length})',
                style: t.bodySmall?.copyWith(
                    color: textoTenueDe(context),
                    fontWeight: FontWeight.w700)),
            const SizedBox(height: 6),
            ConstrainedBox(
              constraints: const BoxConstraints(maxHeight: 300),
              child: ListView(
                shrinkWrap: true,
                children: [
                  for (final r in _resultados)
                    Card(
                      elevation: 0,
                      margin: const EdgeInsets.only(bottom: 8),
                      shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(14),
                          side: const BorderSide(color: Color(0xFFE4E4E4))),
                      child: ListTile(
                        onTap: () => _abrir(r),
                        leading: Text(emojiDeporte(r.deporte),
                            style: const TextStyle(fontSize: 22)),
                        title: Text(r.nombre,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style:
                                const TextStyle(fontWeight: FontWeight.w700)),
                        subtitle: Text(
                            [
                              if (r.fechas.isNotEmpty) r.fechas,
                              if (r.terminado)
                                'Finalizado 🏁'
                              else if (r.inscripcionAbierta &&
                                  !r.fixtureGenerado)
                                'Inscripciones abiertas'
                              else
                                'En juego',
                            ].join(' · '),
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(fontSize: 12.5)),
                        trailing: const Icon(Icons.chevron_right),
                      ),
                    ),
                ],
              ),
            ),
          ],
        ],
      ),
    );
  }
}
