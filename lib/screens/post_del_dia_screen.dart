import 'dart:io';

import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';
import 'package:share_plus/share_plus.dart';

import '../services/community_service.dart';
import '../theme.dart';
import '../widgets/cargando_pichangol.dart';
import '../widgets/responsive.dart';

/// COMMUNITY MANAGER autónomo (Fase 0): el "post del día" LISTO para las redes
/// del negocio (IG/FB). Muestra el flyer de marca + el copy (editable) y lo
/// publica en **1 toque** (hoja de compartir del sistema). Sin depender aún de
/// la API de Meta: el mismo pipeline auto-publicará en la Fase 1/2.
class PostDelDiaScreen extends StatefulWidget {
  const PostDelDiaScreen({
    super.key,
    required this.academiaId,
    required this.datos,
    required this.titulo,
  });

  final String academiaId;
  final Map<String, dynamic> datos;
  final String titulo;

  @override
  State<PostDelDiaScreen> createState() => _PostDelDiaScreenState();
}

class _PostDelDiaScreenState extends State<PostDelDiaScreen> {
  final _texto = TextEditingController();
  PostDelDia? _post;
  bool _cargando = true;
  bool _compartiendo = false;
  bool _activo = false; // CM automático activado para esta academia
  int _cadaDias = 3;
  bool _guardandoAuto = false;

  @override
  void initState() {
    super.initState();
    _cargar();
  }

  /// Carga device-friendly: primero el post PRE-GENERADO por el scheduler
  /// (instantáneo); si no hay, genera uno on-demand.
  Future<void> _cargar() async {
    setState(() => _cargando = true);
    final e = await CommunityService.cmEstado(widget.academiaId);
    if (!mounted) return;
    if (e != null) {
      _activo = e.activo;
      _cadaDias = e.cadaDias;
      if (e.post != null) {
        setState(() {
          _cargando = false;
          _post = e.post;
          _texto.text = e.post!.textoCompleto;
        });
        return;
      }
    }
    await _generar();
  }

  /// Activa/desactiva el CM automático (el backend lo renueva en su cadencia).
  Future<void> _alternarAuto(bool v) async {
    setState(() => _guardandoAuto = true);
    final e = await CommunityService.cmConfig(
      academiaId: widget.academiaId,
      activo: v,
      datos: widget.datos,
      cadaDias: _cadaDias,
    );
    if (!mounted) return;
    setState(() {
      _guardandoAuto = false;
      if (e != null) {
        _activo = e.activo;
        _cadaDias = e.cadaDias;
        if (e.post != null) {
          _post = e.post;
          _texto.text = e.post!.textoCompleto;
        }
      }
    });
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
      content: Text(e == null
          ? 'No se pudo actualizar. Reintenta.'
          : (_activo
              ? 'Community manager automático activado.'
              : 'Automático desactivado.')),
      duration: const Duration(milliseconds: 1500),
    ));
  }

  @override
  void dispose() {
    _texto.dispose();
    super.dispose();
  }

  Future<void> _generar() async {
    setState(() => _cargando = true);
    final p = await CommunityService.postDelDia(
      academiaId: widget.academiaId,
      datos: widget.datos,
    );
    if (!mounted) return;
    setState(() {
      _cargando = false;
      _post = p;
      if (p != null) _texto.text = p.textoCompleto;
    });
  }

  Future<void> _publicar() async {
    if (_compartiendo || _post == null) return;
    setState(() => _compartiendo = true);
    final texto = _texto.text.trim();
    final url = _post!.imagenUrl;
    try {
      if (url.isNotEmpty) {
        final resp = await http.get(Uri.parse(url));
        if (resp.statusCode == 200) {
          final dir = await getTemporaryDirectory();
          final ruta = '${dir.path}/pichangol_post_'
              '${DateTime.now().millisecondsSinceEpoch}.png';
          await File(ruta).writeAsBytes(resp.bodyBytes);
          await Share.shareXFiles([XFile(ruta, mimeType: 'image/png')],
              text: texto.isNotEmpty ? texto : null);
        } else {
          await Share.share(texto);
        }
      } else if (texto.isNotEmpty) {
        await Share.share(texto);
      }
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
            content: Text('No se pudo compartir. Inténtalo de nuevo.')));
      }
    } finally {
      if (mounted) setState(() => _compartiendo = false);
    }
  }

  void _copiar() {
    Clipboard.setData(ClipboardData(text: _texto.text.trim()));
    ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
        content: Text('Copiado. Pégalo donde quieras.'),
        duration: Duration(milliseconds: 1200)));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Post del día'),
        actions: [
          IconButton(
            tooltip: 'Generar otro',
            icon: const Icon(Icons.refresh),
            onPressed: _cargando ? null : _generar,
          ),
        ],
      ),
      body: AnchoTablet(
        maxWidth: 640,
        child: _cargando
            ? const Padding(
                padding: EdgeInsets.symmetric(vertical: 60),
                child: CargandoPichangol(texto: 'Preparando tu post…'))
            : _post == null
                ? _error()
                : _contenido(),
      ),
      bottomNavigationBar: (_cargando || _post == null)
          ? null
          : SafeArea(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(16, 8, 16, 12),
                child: SizedBox(
                  width: double.infinity,
                  child: FilledButton.icon(
                    style: FilledButton.styleFrom(
                        backgroundColor: const Color(0xFF25D366),
                        padding: const EdgeInsets.symmetric(vertical: 14)),
                    onPressed: _compartiendo ? null : _publicar,
                    icon: _compartiendo
                        ? const SizedBox(
                            width: 20,
                            height: 20,
                            child: CircularProgressIndicator(
                                strokeWidth: 2, color: Colors.white))
                        : const Icon(Icons.ios_share),
                    label: const Text('Publicar en 1 toque',
                        style: TextStyle(fontWeight: FontWeight.w800)),
                  ),
                ),
              ),
            ),
    );
  }

  Widget _error() => Center(
        child: Padding(
          padding: const EdgeInsets.all(28),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.cloud_off, color: textoTenue, size: 48),
              const SizedBox(height: 12),
              const Text('No se pudo generar el post. Revisa tu conexión.',
                  textAlign: TextAlign.center,
                  style: TextStyle(color: textoTenue)),
              const SizedBox(height: 16),
              FilledButton(
                style: FilledButton.styleFrom(backgroundColor: lima),
                onPressed: _generar,
                child: const Text('Reintentar'),
              ),
            ],
          ),
        ),
      );

  Widget _contenido() {
    final p = _post!;
    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 16, 16, 24),
      children: [
        Text(widget.titulo,
            style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 16)),
        if (p.horaSugerida.isNotEmpty)
          Padding(
            padding: const EdgeInsets.only(top: 2),
            child: Text('Mejor hora para publicar: ${p.horaSugerida}',
                style: const TextStyle(color: textoTenue, fontSize: 12.5)),
          ),
        const SizedBox(height: 12),
        // Interruptor del CM AUTÓNOMO: el agente arma los posts solo, en un
        // calendario; el dueño solo revisa y publica.
        Container(
          decoration: BoxDecoration(
            color: _activo
                ? limaSuave
                : Theme.of(context).colorScheme.surface,
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: trazo),
          ),
          child: SwitchListTile(
            activeColor: lima,
            secondary: Icon(Icons.auto_awesome,
                color: _activo ? lima : textoTenue),
            title: const Text('Publicar automático',
                style: TextStyle(fontWeight: FontWeight.w800)),
            subtitle: Text(
                _activo
                    ? 'El agente arma tu post cada $_cadaDias días. Solo revisas '
                        'y publicas.'
                    : 'Deja que el agente arme tus posts solo, en un calendario.',
                style: const TextStyle(fontSize: 12.5)),
            value: _activo,
            onChanged: _guardandoAuto ? null : _alternarAuto,
          ),
        ),
        const SizedBox(height: 14),
        if (p.imagenUrl.isNotEmpty)
          ClipRRect(
            borderRadius: BorderRadius.circular(16),
            child: CachedNetworkImage(
              imageUrl: p.imagenUrl,
              fit: BoxFit.cover,
              placeholder: (c, u) => const AspectRatio(
                  aspectRatio: 1,
                  child: Center(child: CircularProgressIndicator(color: lima))),
              errorWidget: (c, u, e) => const AspectRatio(
                  aspectRatio: 1,
                  child: Icon(Icons.image_not_supported_outlined,
                      color: textoTenue, size: 40)),
            ),
          ),
        const SizedBox(height: 16),
        const Text('Texto (edítalo si quieres)',
            style: TextStyle(fontWeight: FontWeight.w700)),
        const SizedBox(height: 6),
        Container(
          decoration: BoxDecoration(
            border: Border.all(color: trazo),
            borderRadius: BorderRadius.circular(14),
          ),
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 4),
          child: TextField(
            controller: _texto,
            maxLines: null,
            minLines: 4,
            decoration: const InputDecoration(border: InputBorder.none),
          ),
        ),
        const SizedBox(height: 8),
        Align(
          alignment: Alignment.centerLeft,
          child: TextButton.icon(
            style: TextButton.styleFrom(padding: EdgeInsets.zero),
            onPressed: _copiar,
            icon: const Icon(Icons.copy, size: 18, color: teal),
            label: const Text('Copiar texto',
                style: TextStyle(color: teal, fontWeight: FontWeight.w700)),
          ),
        ),
        const SizedBox(height: 8),
        const Text(
          'Toca "Publicar en 1 toque" y elige Instagram o Facebook: se abrirá con '
          'la imagen lista. (Pronto se publicará solo.)',
          style: TextStyle(color: textoTenue, fontSize: 12.5),
        ),
      ],
    );
  }
}
