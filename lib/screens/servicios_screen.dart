import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:url_launcher/url_launcher.dart';

import '../brand.dart';
import '../models/academia.dart';
import '../services/growth_service.dart';
import '../services/pagos_service.dart';
import '../services/whatsapp_link.dart';
import '../state/app_state.dart';
import '../theme.dart';
import 'recargar_saldo_screen.dart';

/// "Servicios Pichangol": el dueño contrata landing / manejo de redes /
/// presencia digital como SUSCRIPCIÓN mensual, pagada con el saldo de su
/// academia (mismo saldo prepago de Culqi). Muestra estado y próximo cobro.
class ServiciosScreen extends StatefulWidget {
  const ServiciosScreen({super.key, required this.academia});
  final Academia academia;

  @override
  State<ServiciosScreen> createState() => _ServiciosScreenState();
}

class _ServiciosScreenState extends State<ServiciosScreen> {
  List<Map<String, dynamic>>? _planes;
  List<Map<String, dynamic>> _subs = const [];
  bool _cargando = true;
  String? _procesando; // clave del servicio en curso

  bool _generandoLanding = false;
  final _tema = TextEditingController();
  List<Map<String, dynamic>>? _posts;
  bool _generandoPosts = false;

  @override
  void dispose() {
    _tema.dispose();
    super.dispose();
  }

  String get _mon => widget.academia.monedaSimbolo;
  String get _idAcademia => widget.academia.id;
  // Academia SIEMPRE actualizada (tras generar landing, guardarAcademia, etc.).
  Academia get _ac => appState.academias.firstWhere((a) => a.id == _idAcademia,
      orElse: () => widget.academia);

  // ¿Tiene un servicio con landing activo (landing o presencia)?
  bool get _landingContratada => _subs.any((s) =>
      (s['servicio'] == 'landing' || s['servicio'] == 'presencia') &&
      (s['estado'] == 'activa' || s['estado'] == 'pendiente_pago'));

  // ¿Tiene manejo de redes activo (redes o presencia)?
  bool get _redesContratada => _subs.any((s) =>
      (s['servicio'] == 'redes' || s['servicio'] == 'presencia') &&
      (s['estado'] == 'activa' || s['estado'] == 'pendiente_pago'));

  // ¿La academia ya tiene alguna red social publicada?
  bool get _tieneRedes =>
      (_ac.redes['instagram']?.trim().isNotEmpty ?? false) ||
      (_ac.redes['facebook']?.trim().isNotEmpty ?? false) ||
      (_ac.redes['tiktok']?.trim().isNotEmpty ?? false);

  /// Abre WhatsApp con Pichangol (número del país) para pedir que le CREEN las
  /// redes al dueño que no tiene cuentas.
  Future<void> _pedirCrearRedes() async {
    final numero =
        await GrowthService.contactoWhatsApp(_ac.pais.iso) ?? kContactoWhatsApp;
    await WhatsAppLink.abrir(numero,
        'Hola Pichangol, no tengo redes y quiero que me ayuden a crear y manejar '
        'las de mi academia "${_ac.nombre}".');
  }

  @override
  void initState() {
    super.initState();
    _cargar();
  }

  Future<void> _cargar() async {
    setState(() => _cargando = true);
    await appState.sincronizarSaldoAcademia(_idAcademia);
    final planes = await PagosService.planesServicios();
    final subs = await PagosService.estadoServicios(_idAcademia);
    if (!mounted) return;
    setState(() {
      _planes = planes;
      _subs = subs ?? const [];
      _cargando = false;
    });
  }

  Map<String, dynamic>? _subDe(String clave) {
    for (final s in _subs) {
      if (s['servicio'] == clave) return s;
    }
    return null;
  }

  Future<void> _contratar(Map<String, dynamic> plan) async {
    final clave = plan['clave'] as String;
    setState(() => _procesando = clave);
    final r = await PagosService.contratarServicio(
        duenoId: _idAcademia, academiaId: _idAcademia, servicio: clave);
    if (!mounted) return;
    setState(() => _procesando = null);
    if (r == null) {
      _msg('No se pudo contratar. Revisa tu conexión.');
      return;
    }
    if (r['falta_saldo'] == true) {
      await _faltaSaldo((r['requerido_soles'] as num?)?.toDouble() ?? 0);
      return;
    }
    if (r['ok'] == true) {
      await _cargar();
      _msg('✅ ${plan['nombre']} activado. Te contactaremos para arrancar.');
    } else {
      _msg('No se pudo contratar.');
    }
  }

  Future<void> _faltaSaldo(double requerido) async {
    final ir = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Saldo insuficiente'),
        content: Text(
            'Necesitas $_mon ${requerido.toStringAsFixed(0)} de saldo para '
            'contratar este servicio. Recarga y vuelve a intentarlo.'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('Ahora no')),
          FilledButton(
              style: FilledButton.styleFrom(backgroundColor: lima),
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('Recargar saldo')),
        ],
      ),
    );
    if (ir == true && mounted) await _pushRecarga();
  }

  Future<void> _pushRecarga() async {
    await Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => RecargarSaldoScreen(
          duenoId: _idAcademia,
          titulo: 'Recargar saldo',
          pais: widget.academia.pais),
    ));
    await _cargar();
  }

  Future<void> _cancelar(String clave, String nombre) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text('Cancelar $nombre'),
        content: const Text(
            'Se cancela la renovación del próximo mes. El mes en curso sigue '
            'activo hasta su fecha.'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('No')),
          FilledButton(
              style: FilledButton.styleFrom(backgroundColor: clayOscuro),
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('Sí, cancelar')),
        ],
      ),
    );
    if (ok == true) {
      await PagosService.cancelarServicio(academiaId: _idAcademia, servicio: clave);
      await _cargar();
    }
  }

  void _msg(String t) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(t)));
  }

  Future<void> _generarLanding() async {
    setState(() => _generandoLanding = true);
    final url = await appState.generarLanding(_ac);
    if (!mounted) return;
    setState(() => _generandoLanding = false);
    if (url == null) {
      _msg('No se pudo generar la landing. Revisa tu conexión.');
    } else {
      _msg('✅ Tu landing está publicada.');
    }
  }

  Future<void> _abrir(String url) async {
    final u = Uri.tryParse(url);
    if (u != null) await launchUrl(u, mode: LaunchMode.externalApplication);
  }

  Future<void> _generarPosts() async {
    setState(() => _generandoPosts = true);
    final r = await appState.generarPosts(_ac, _tema.text.trim());
    if (!mounted) return;
    setState(() => _generandoPosts = false);
    if (r == null) {
      _msg('No se pudo generar. Revisa tu conexión.');
      return;
    }
    if (r['limite'] == true) {
      final lim = r['limite_mes'] ?? '';
      _msg('Alcanzaste el límite de generaciones de este mes ($lim). '
          'Vuelve el próximo mes o escríbenos.');
      return;
    }
    final posts = ((r['posts'] as List?) ?? const [])
        .map((e) => Map<String, dynamic>.from(e as Map))
        .toList();
    setState(() => _posts = posts);
  }

  String _fecha(String? iso) {
    if (iso == null) return '';
    final d = DateTime.tryParse(iso);
    if (d == null) return '';
    return '${d.day}/${d.month}/${d.year}';
  }

  @override
  Widget build(BuildContext context) {
    final saldo = appState.saldoAcademiaDe(_idAcademia);
    return Scaffold(
      appBar: AppBar(title: const Text('Servicios Pichangol')),
      body: _cargando
          ? const Center(child: CircularProgressIndicator(color: lima))
          : RefreshIndicator(
              onRefresh: _cargar,
              color: lima,
              child: ListView(
                padding: const EdgeInsets.fromLTRB(16, 14, 16, 30),
                children: [
                  // Saldo de la academia.
                  Container(
                    padding: const EdgeInsets.all(16),
                    decoration: BoxDecoration(
                      color: limaSuave,
                      borderRadius: BorderRadius.circular(16),
                    ),
                    child: Row(
                      children: [
                        const Icon(Icons.account_balance_wallet_outlined,
                            color: lima),
                        const SizedBox(width: 10),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              const Text('Saldo de la academia',
                                  style: TextStyle(
                                      fontSize: 12, color: textoTenue)),
                              Text('$_mon $saldo',
                                  style: const TextStyle(
                                      fontSize: 20,
                                      fontWeight: FontWeight.w800)),
                            ],
                          ),
                        ),
                        TextButton(
                          onPressed: _pushRecarga,
                          child: const Text('Recargar',
                              style: TextStyle(
                                  color: lima, fontWeight: FontWeight.w800)),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 8),
                  if (_landingContratada) _cardLanding(),
                  if (_redesContratada) _cardRedes(),
                  const Padding(
                    padding: EdgeInsets.symmetric(vertical: 8, horizontal: 2),
                    child: Text(
                        'Contrata tu presencia digital. Se cobra del saldo cada '
                        'mes; puedes cancelar cuando quieras.',
                        style: TextStyle(color: textoTenue, fontSize: 13)),
                  ),
                  if (_planes == null)
                    const Padding(
                      padding: EdgeInsets.all(24),
                      child: Text('No se pudo cargar el catálogo.',
                          style: TextStyle(color: textoTenue)),
                    )
                  else
                    for (final p in _planes!) _tarjetaPlan(p),
                ],
              ),
            ),
    );
  }

  /// Tarjeta "Tu landing" (fulfillment): genera / ve / comparte la página web.
  Widget _cardLanding() {
    final ac = _ac;
    final tiene = ac.tieneLanding;
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: limaSuave,
        borderRadius: BorderRadius.circular(16),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.public, color: lima),
              const SizedBox(width: 8),
              const Expanded(
                child: Text('Tu landing web',
                    style:
                        TextStyle(fontWeight: FontWeight.w800, fontSize: 16)),
              ),
            ],
          ),
          const SizedBox(height: 4),
          Text(
              tiene
                  ? 'Publicada y lista para compartir. Se arma con los datos de '
                      'tu academia (actualízala si cambias tarifario o fotos).'
                  : 'Genera tu página web con los datos de tu academia. Queda con '
                      'un enlace público para compartir.',
              style: const TextStyle(color: textoTenue, fontSize: 13)),
          const SizedBox(height: 12),
          if (tiene) ...[
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                FilledButton.icon(
                  style: FilledButton.styleFrom(
                      backgroundColor: lima, foregroundColor: Colors.white),
                  icon: const Icon(Icons.open_in_new, size: 18),
                  label: const Text('Ver'),
                  onPressed: () => _abrir(ac.landingUrl),
                ),
                OutlinedButton.icon(
                  style: OutlinedButton.styleFrom(
                      foregroundColor: lima,
                      side: const BorderSide(color: lima)),
                  icon: const Icon(Icons.share_outlined, size: 18),
                  label: const Text('Compartir'),
                  onPressed: () => WhatsAppLink.compartir(
                      'Mira nuestra página: ${ac.landingUrl}'),
                ),
                TextButton.icon(
                  icon: _generandoLanding
                      ? const SizedBox(
                          height: 16,
                          width: 16,
                          child: CircularProgressIndicator(strokeWidth: 2))
                      : const Icon(Icons.refresh, size: 18),
                  label: const Text('Actualizar'),
                  onPressed: _generandoLanding ? null : _generarLanding,
                ),
              ],
            ),
          ] else
            SizedBox(
              width: double.infinity,
              child: FilledButton(
                style: FilledButton.styleFrom(
                    backgroundColor: lima,
                    foregroundColor: Colors.white,
                    padding: const EdgeInsets.symmetric(vertical: 13)),
                onPressed: _generandoLanding ? null : _generarLanding,
                child: _generandoLanding
                    ? const SizedBox(
                        height: 20,
                        width: 20,
                        child: CircularProgressIndicator(
                            strokeWidth: 2.4, color: Colors.white))
                    : const Text('Generar mi landing'),
              ),
            ),
        ],
      ),
    );
  }

  /// Tarjeta "Community manager IA": genera posts para redes a partir de un tema.
  Widget _cardRedes() {
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: trazo),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: const [
              Icon(Icons.auto_awesome, color: lima),
              SizedBox(width: 8),
              Expanded(
                child: Text('Community manager con IA',
                    style:
                        TextStyle(fontWeight: FontWeight.w800, fontSize: 16)),
              ),
            ],
          ),
          const SizedBox(height: 4),
          const Text(
              'Genera posts listos (texto + hashtags + mejor hora). Los revisas '
              'y compartes a tus redes con un tap.',
              style: TextStyle(color: textoTenue, fontSize: 13)),
          if (!_tieneRedes) ...[
            const SizedBox(height: 10),
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: const Color(0xFFFBEAD2),
                borderRadius: BorderRadius.circular(12),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                      '💡 Aún no registraste tu Instagram/Facebook. Puedes generar '
                      'el contenido igual, y si no tienes cuentas, nosotros te las '
                      'creamos y las manejamos.',
                      style: TextStyle(fontSize: 12.5, color: clayOscuro)),
                  const SizedBox(height: 8),
                  OutlinedButton.icon(
                    style: OutlinedButton.styleFrom(
                        foregroundColor: clayOscuro,
                        side: const BorderSide(color: clayOscuro)),
                    icon: const Icon(Icons.support_agent, size: 18),
                    label: const Text('Ayúdenme a crear mis redes'),
                    onPressed: _pedirCrearRedes,
                  ),
                ],
              ),
            ),
          ],
          const SizedBox(height: 10),
          TextField(
            controller: _tema,
            decoration: const InputDecoration(
              labelText: '¿Sobre qué quieres postear? (opcional)',
              hintText: 'Ej.: apertura, torneo, promo de vacaciones',
              isDense: true,
            ),
          ),
          const SizedBox(height: 10),
          SizedBox(
            width: double.infinity,
            child: FilledButton.icon(
              style: FilledButton.styleFrom(
                  backgroundColor: lima,
                  foregroundColor: Colors.white,
                  padding: const EdgeInsets.symmetric(vertical: 12)),
              icon: _generandoPosts
                  ? const SizedBox(
                      height: 18,
                      width: 18,
                      child: CircularProgressIndicator(
                          strokeWidth: 2.2, color: Colors.white))
                  : const Icon(Icons.auto_awesome, size: 18),
              label: Text(_posts == null ? 'Generar posts' : 'Generar otros'),
              onPressed: _generandoPosts ? null : _generarPosts,
            ),
          ),
          if (_posts != null) ...[
            const SizedBox(height: 12),
            for (final p in _posts!) _postItem(p),
          ],
        ],
      ),
    );
  }

  Widget _postItem(Map<String, dynamic> p) {
    final texto = (p['texto'] ?? '').toString();
    final hashtags =
        ((p['hashtags'] as List?) ?? const []).map((e) => e.toString()).toList();
    final hora = (p['hora_sugerida'] ?? '').toString();
    final completo = hashtags.isEmpty ? texto : '$texto\n\n${hashtags.join(' ')}';
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: limaSuave,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (hora.isNotEmpty)
            Text('⏰ Mejor hora: $hora',
                style: const TextStyle(
                    fontSize: 12, fontWeight: FontWeight.w700, color: lima)),
          const SizedBox(height: 4),
          Text(texto, style: const TextStyle(fontSize: 14)),
          if (hashtags.isNotEmpty) ...[
            const SizedBox(height: 6),
            Text(hashtags.join(' '),
                style: const TextStyle(fontSize: 12.5, color: lima)),
          ],
          const SizedBox(height: 6),
          Row(
            children: [
              TextButton.icon(
                icon: const Icon(Icons.copy, size: 16),
                label: const Text('Copiar'),
                onPressed: () {
                  Clipboard.setData(ClipboardData(text: completo));
                  _msg('Post copiado');
                },
              ),
              TextButton.icon(
                icon: const Icon(Icons.share_outlined, size: 16),
                label: const Text('Compartir'),
                onPressed: () => WhatsAppLink.compartir(completo),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _tarjetaPlan(Map<String, dynamic> plan) {
    final clave = plan['clave'] as String;
    final nombre = (plan['nombre'] ?? '') as String;
    final desc = (plan['desc'] ?? '') as String;
    final soles = (plan['soles'] as num?)?.toDouble() ?? 0;
    final sub = _subDe(clave);
    final estado = sub?['estado'] as String?;
    final activa = estado == 'activa';
    final pendiente = estado == 'pendiente_pago';
    final procesando = _procesando == clave;
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: trazo),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: Text(nombre,
                    style: const TextStyle(
                        fontWeight: FontWeight.w800, fontSize: 17)),
              ),
              Text('$_mon ${soles.toStringAsFixed(0)}',
                  style: const TextStyle(
                      fontWeight: FontWeight.w900, fontSize: 18, color: lima)),
              const Text(' /mes',
                  style: TextStyle(color: textoTenue, fontSize: 12)),
            ],
          ),
          const SizedBox(height: 4),
          Text(desc, style: const TextStyle(color: textoTenue, fontSize: 13)),
          const SizedBox(height: 12),
          if (activa || pendiente) ...[
            Container(
              padding:
                  const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
              decoration: BoxDecoration(
                color: pendiente ? const Color(0xFFFBEAD2) : limaSuave,
                borderRadius: BorderRadius.circular(999),
              ),
              child: Text(
                pendiente
                    ? '⚠ Pago pendiente — recarga tu saldo'
                    : '● Activo · próximo cobro ${_fecha(sub?['proximo_cobro'])}',
                style: TextStyle(
                    fontSize: 12.5,
                    fontWeight: FontWeight.w700,
                    color: pendiente ? clayOscuro : lima),
              ),
            ),
            const SizedBox(height: 8),
            Align(
              alignment: Alignment.centerRight,
              child: TextButton(
                onPressed: () => _cancelar(clave, nombre),
                child: const Text('Cancelar suscripción',
                    style: TextStyle(color: clayOscuro)),
              ),
            ),
          ] else
            SizedBox(
              width: double.infinity,
              child: FilledButton(
                style: FilledButton.styleFrom(
                    backgroundColor: lima,
                    foregroundColor: Colors.white,
                    padding: const EdgeInsets.symmetric(vertical: 13)),
                onPressed: procesando ? null : () => _contratar(plan),
                child: procesando
                    ? const SizedBox(
                        height: 20,
                        width: 20,
                        child: CircularProgressIndicator(
                            strokeWidth: 2.4, color: Colors.white))
                    : Text('Contratar · $_mon ${soles.toStringAsFixed(0)}/mes'),
              ),
            ),
        ],
      ),
    );
  }
}
