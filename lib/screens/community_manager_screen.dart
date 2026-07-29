import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../data/canales_repo.dart';
import '../models/canal.dart';
import '../services/community_service.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/cargando_pichangol.dart';
import '../widgets/dialogo_pichangol.dart';
import '../widgets/responsive.dart';

/// Community manager con IA (servicio Pichangol). El dueño de un canal elige un
/// tema y un tono, la IA (Claude, en el backend growth) redacta varios posts, y
/// el dueño los revisa, edita y publica en su canal con un tap.
///
/// Al salir devuelve la lista de [CanalPost] que se publicaron, para que la
/// ficha del canal los muestre al instante.
class CommunityManagerScreen extends StatefulWidget {
  const CommunityManagerScreen({super.key, required this.canal});
  final Canal canal;

  @override
  State<CommunityManagerScreen> createState() => _CommunityManagerScreenState();
}

class _CommunityManagerScreenState extends State<CommunityManagerScreen> {
  final _tema = TextEditingController();

  // Tonos disponibles (se pliegan al "contexto" que recibe la IA).
  static const _tonos = <String>[
    'Motivador',
    'Promocional',
    'Informativo',
    'Divertido',
  ];
  String _tono = 'Motivador';
  int _cantidad = 3;

  bool _generando = false;
  bool _viaIa = false;
  String? _aviso; // mensaje de estado (sin resultados, tope, etc.)

  // Borradores en edición: un controlador por tarjeta.
  final List<TextEditingController> _borradores = [];
  // Posts ya publicados en esta sesión (se devuelven al cerrar).
  final List<CanalPost> _publicados = [];

  @override
  void dispose() {
    _tema.dispose();
    for (final c in _borradores) {
      c.dispose();
    }
    super.dispose();
  }

  Future<void> _generar() async {
    if (_generando) return;
    FocusScope.of(context).unfocus();
    if (!CommunityService.disponible) {
      setState(() => _aviso =
          'El servicio de IA no está configurado en esta versión de la app.');
      return;
    }
    setState(() {
      _generando = true;
      _aviso = null;
    });

    final tema = _tema.text.trim();
    // El tono viaja dentro del contexto: la IA lo usa como estilo del copy.
    final contexto = [
      if (tema.isNotEmpty) tema,
      'Tono $_tono',
    ].join('. ');

    // REGLA de la app: acción que demora → preload de marca (nunca spinner pelado).
    final r = await conPreload(
      context,
      () => CommunityService.generarPosts(
        academiaId: 'canal_${widget.canal.id}',
        datos: {
          'nombre': widget.canal.nombre,
          'descripcion': widget.canal.descripcion,
        },
        contexto: contexto,
        cantidad: _cantidad,
      ),
      texto: 'Redactando con IA…',
    );

    if (!mounted) return;
    setState(() {
      _generando = false;
      if (r == null) {
        _aviso = 'No se pudo generar. Revisa tu conexión e inténtalo de nuevo.';
        return;
      }
      if (r.topoLimite) {
        _aviso =
            'Llegaste al límite de generaciones de este mes (${r.limiteMes}). '
            'Vuelve el próximo mes o publica los que ya tienes.';
        return;
      }
      if (r.posts.isEmpty) {
        _aviso = 'La IA no devolvió resultados. Prueba con otro tema.';
        return;
      }
      _viaIa = r.viaIa;
      // Añade los nuevos borradores (no borra los que ya editabas).
      for (final p in r.posts) {
        _borradores.add(TextEditingController(text: p.textoCompleto));
      }
    });
  }

  Future<void> _publicar(int i) async {
    final u = appState.usuario;
    final texto = _borradores[i].text.trim();
    if (u == null || texto.isEmpty) return;
    final post = CanalPost(
      id: 'cp_${DateTime.now().microsecondsSinceEpoch}',
      canalId: widget.canal.id,
      autorEmail: u.email,
      autorNombre: u.nombre,
      tipo: 'texto',
      texto: texto,
      creado: DateTime.now(),
    );
    final ok = await conPreload(context, () => CanalesRepo.publicar(post),
        texto: 'Publicando…');
    if (!mounted) return;
    if (!ok) {
      await avisarPichangol(context,
          titulo: 'No se pudo publicar',
          mensaje: 'Inténtalo de nuevo en unos segundos.',
          icono: Icons.error_outline);
      return;
    }
    setState(() {
      _publicados.insert(0, post);
      _borradores[i].dispose();
      _borradores.removeAt(i);
    });
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('Publicado en tu canal ✓')),
    );
  }

  Future<void> _descartar(int i) async {
    final ok = await confirmarPichangol(context,
        titulo: 'Descartar borrador',
        mensaje: '¿Quieres descartar este borrador?',
        textoConfirmar: 'Descartar',
        destructivo: true,
        icono: Icons.delete_outline);
    if (!ok || !mounted) return;
    setState(() {
      _borradores[i].dispose();
      _borradores.removeAt(i);
    });
  }

  void _copiar(int i) {
    Clipboard.setData(ClipboardData(text: _borradores[i].text));
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('Copiado al portapapeles')),
    );
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(
        title: const Text('Generar con IA',
            style: TextStyle(fontWeight: FontWeight.w800)),
      ),
      body: WillPopScope(
        onWillPop: () async {
          Navigator.of(context).pop(_publicados);
          return false;
        },
        child: AnchoTablet(
          maxWidth: 640,
          child: ListView(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 28),
            children: [
              _intro(cs),
              const SizedBox(height: 16),
              _campoTema(cs),
              const SizedBox(height: 16),
              _selectorTono(cs),
              const SizedBox(height: 16),
              _selectorCantidad(cs),
              const SizedBox(height: 18),
              SizedBox(
                width: double.infinity,
                child: FilledButton.icon(
                  style: FilledButton.styleFrom(
                      backgroundColor: lima,
                      minimumSize: const Size.fromHeight(52)),
                  onPressed: _generando ? null : _generar,
                  icon: const Icon(Icons.auto_awesome),
                  label: Text(
                      _borradores.isEmpty ? 'Generar posts' : 'Generar más',
                      style: const TextStyle(fontWeight: FontWeight.w800)),
                ),
              ),
              if (_aviso != null) ...[
                const SizedBox(height: 16),
                _tarjetaAviso(_aviso!),
              ],
              if (_borradores.isNotEmpty) ...[
                const SizedBox(height: 22),
                Row(
                  children: [
                    Text('Borradores',
                        style: TextStyle(
                            fontWeight: FontWeight.w800,
                            fontSize: 16,
                            color: cs.onSurface)),
                    const SizedBox(width: 8),
                    if (_viaIa)
                      Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 8, vertical: 3),
                        decoration: BoxDecoration(
                            color: limaSuave,
                            borderRadius: BorderRadius.circular(20)),
                        child: const Text('IA',
                            style: TextStyle(
                                color: lima,
                                fontWeight: FontWeight.w800,
                                fontSize: 11)),
                      ),
                  ],
                ),
                const SizedBox(height: 4),
                Text('Revisa y edita antes de publicar. Se publican como texto '
                    'en tu canal.',
                    style: TextStyle(
                        color: textoTenueDe(context), fontSize: 12.5)),
                const SizedBox(height: 12),
                for (int i = 0; i < _borradores.length; i++) _tarjeta(i, cs),
              ],
              if (_publicados.isNotEmpty) ...[
                const SizedBox(height: 14),
                Center(
                  child: Text('Publicaste ${_publicados.length} post(s) ✓',
                      style: const TextStyle(
                          color: lima, fontWeight: FontWeight.w700)),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }

  Widget _intro(ColorScheme cs) => Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
            color: limaSuave.withOpacity(0.5),
            borderRadius: BorderRadius.circular(16)),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Icon(Icons.campaign, color: teal),
            const SizedBox(width: 12),
            Expanded(
              child: Text(
                'Tu community manager con IA redacta novedades para el canal '
                '"${widget.canal.nombre}". Tú revisas, editas y publicas.',
                style: TextStyle(color: cs.onSurface, fontSize: 13.5),
              ),
            ),
          ],
        ),
      );

  Widget _campoTema(ColorScheme cs) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('¿Sobre qué? (opcional)',
              style: TextStyle(
                  fontWeight: FontWeight.w700, color: cs.onSurface)),
          const SizedBox(height: 8),
          TextField(
            controller: _tema,
            minLines: 1,
            maxLines: 3,
            textCapitalization: TextCapitalization.sentences,
            decoration: const InputDecoration(
              hintText: 'Ej: promo de verano, torneo del sábado, horarios nuevos…',
              isDense: true,
            ),
          ),
        ],
      );

  Widget _selectorTono(ColorScheme cs) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Tono',
              style: TextStyle(
                  fontWeight: FontWeight.w700, color: cs.onSurface)),
          const SizedBox(height: 8),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              for (final t in _tonos)
                _Pastilla(
                  texto: t,
                  activo: _tono == t,
                  onTap: () => setState(() => _tono = t),
                ),
            ],
          ),
        ],
      );

  Widget _selectorCantidad(ColorScheme cs) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('¿Cuántos posts?',
              style: TextStyle(
                  fontWeight: FontWeight.w700, color: cs.onSurface)),
          const SizedBox(height: 8),
          Wrap(
            spacing: 8,
            children: [
              for (final n in const [1, 2, 3, 4, 5])
                _Pastilla(
                  texto: '$n',
                  activo: _cantidad == n,
                  onTap: () => setState(() => _cantidad = n),
                ),
            ],
          ),
        ],
      );

  Widget _tarjetaAviso(String msg) => Container(
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
            color: const Color(0xFFFFF6E6),
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: const Color(0xFFF0D9A8))),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Icon(Icons.info_outline, color: Color(0xFFB8860B), size: 20),
            const SizedBox(width: 10),
            Expanded(
              child: Text(msg,
                  style: const TextStyle(
                      color: Color(0xFF7A5C00), fontSize: 13.5)),
            ),
          ],
        ),
      );

  Widget _tarjeta(int i, ColorScheme cs) => Container(
        margin: const EdgeInsets.only(bottom: 12),
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: cs.surface,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: trazo.withOpacity(0.7)),
          boxShadow: const [
            BoxShadow(color: Color(0x0F000000), blurRadius: 10, offset: Offset(0, 3)),
          ],
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            TextField(
              controller: _borradores[i],
              minLines: 3,
              maxLines: 12,
              textCapitalization: TextCapitalization.sentences,
              decoration: const InputDecoration(
                border: InputBorder.none,
                isDense: true,
                contentPadding: EdgeInsets.zero,
              ),
              style: TextStyle(color: cs.onSurface, fontSize: 14.5, height: 1.35),
            ),
            Divider(color: trazo.withOpacity(0.5), height: 22),
            Row(
              children: [
                _AccionTexto(
                    icono: Icons.copy_rounded,
                    texto: 'Copiar',
                    onTap: () => _copiar(i)),
                const SizedBox(width: 4),
                _AccionTexto(
                    icono: Icons.delete_outline,
                    texto: 'Descartar',
                    color: clayOscuro,
                    onTap: () => _descartar(i)),
                const Spacer(),
                FilledButton.icon(
                  style: FilledButton.styleFrom(
                      backgroundColor: lima,
                      visualDensity: VisualDensity.compact),
                  onPressed: () => _publicar(i),
                  icon: const Icon(Icons.send, size: 16),
                  label: const Text('Publicar',
                      style: TextStyle(fontWeight: FontWeight.w800)),
                ),
              ],
            ),
          ],
        ),
      );
}

/// Pastilla estilo Airbnb (blanca con relieve; seleccionada = tinte lima).
class _Pastilla extends StatelessWidget {
  const _Pastilla(
      {required this.texto, required this.activo, required this.onTap});
  final String texto;
  final bool activo;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Material(
      color: activo ? limaSuave : cs.surface,
      borderRadius: BorderRadius.circular(22),
      child: InkWell(
        borderRadius: BorderRadius.circular(22),
        onTap: onTap,
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 9),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(22),
            border: Border.all(
                color: activo ? lima : trazo.withOpacity(0.8),
                width: activo ? 1.4 : 1),
          ),
          child: Text(texto,
              style: TextStyle(
                  color: activo ? teal : cs.onSurface,
                  fontWeight: activo ? FontWeight.w800 : FontWeight.w600,
                  fontSize: 13.5)),
        ),
      ),
    );
  }
}

class _AccionTexto extends StatelessWidget {
  const _AccionTexto(
      {required this.icono,
      required this.texto,
      required this.onTap,
      this.color});
  final IconData icono;
  final String texto;
  final VoidCallback onTap;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    final c = color ?? textoTenueDe(context);
    return TextButton.icon(
      style: TextButton.styleFrom(
          foregroundColor: c,
          padding: const EdgeInsets.symmetric(horizontal: 8),
          visualDensity: VisualDensity.compact),
      onPressed: onTap,
      icon: Icon(icono, size: 17, color: c),
      label: Text(texto,
          style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 13)),
    );
  }
}
