import 'package:flutter/material.dart';

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

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  Future<void> _buscar() async {
    setState(() => _error = null);
    if (_ctrl.text.trim().isEmpty) {
      setState(() => _error = 'Pega el enlace o el código del campeonato.');
      return;
    }
    setState(() => _buscando = true);
    final c = await appState.buscarCampeonato(_ctrl.text);
    if (!mounted) return;
    setState(() => _buscando = false);
    if (c == null) {
      setState(() => _error =
          'No encontramos ese campeonato. Revisa el enlace/código o tu conexión.');
      return;
    }
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
              'Pega el enlace o el código que te compartieron. Abrimos la ficha '
              'para que te inscribas.',
              style: t.bodySmall?.copyWith(color: textoTenueDe(context))),
          const SizedBox(height: 14),
          TextField(
            controller: _ctrl,
            autofocus: true,
            minLines: 1,
            maxLines: 2,
            onSubmitted: (_) => _buscar(),
            decoration: InputDecoration(
              hintText: 'Enlace o código del campeonato',
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
        ],
      ),
    );
  }
}
