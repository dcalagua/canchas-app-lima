import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:image_picker/image_picker.dart';
import 'package:url_launcher/url_launcher.dart';

import '../brand.dart';
import '../models/negocio.dart';
import '../services/growth_service.dart';
import '../services/pagos_service.dart';
import '../services/whatsapp_link.dart';
import '../state/app_state.dart';
import '../theme.dart';
import 'conectar_redes_screen.dart';
import 'recargar_saldo_screen.dart';

/// "Servicios Pichangol": el dueño de un NEGOCIO (academia o club) contrata
/// landing / manejo de redes / presencia digital como SUSCRIPCIÓN mensual,
/// pagada con el saldo de marketing (mismo saldo prepago de Culqi). Muestra
/// estado y próximo cobro.
class ServiciosScreen extends StatefulWidget {
  const ServiciosScreen({super.key, required this.negocio});
  final Negocio negocio;

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

  // Gestión de redes (Nivel 2): estado de la conexión OAuth del dueño.
  Map<String, dynamic>? _redesConn;
  int? _publicando; // índice del post que se está publicando

  // Tarjeta de débito automático de las suscripciones.
  Map<String, dynamic>? _metodoSus;

  // URL de la landing (se actualiza al generarla). Init desde el negocio.
  String _landingUrl = '';

  @override
  void dispose() {
    _tema.dispose();
    super.dispose();
  }

  String get _mon => widget.negocio.monedaSimbolo;
  String get _idAcademia => widget.negocio.id;

  // ¿Tiene un servicio con landing activo (landing o presencia)?
  bool get _landingContratada => _subs.any((s) =>
      (s['servicio'] == 'landing' || s['servicio'] == 'presencia') &&
      (s['estado'] == 'activa' || s['estado'] == 'pendiente_pago'));

  // ¿Tiene "Manejo de redes" (unificado: contenido IA + publicación)? Incluye
  // "presencia" (lo trae todo) y el legado "gestion".
  bool get _redesContratada => _subs.any((s) =>
      (s['servicio'] == 'redes' ||
          s['servicio'] == 'presencia' ||
          s['servicio'] == 'gestion') &&
      (s['estado'] == 'activa' || s['estado'] == 'pendiente_pago'));

  bool get _redesConectada => _redesConn?['conectado'] == true;

  // ¿El negocio ya declaró alguna red social?
  bool get _tieneRedes => widget.negocio.tieneRedesRegistradas;

  /// Abre WhatsApp con Pichangol (número del país) para pedir que le CREEN las
  /// redes al dueño que no tiene cuentas.
  Future<void> _pedirCrearRedes() async {
    final numero =
        await GrowthService.contactoWhatsApp(widget.negocio.pais.iso) ??
            kContactoWhatsApp;
    await WhatsAppLink.abrir(numero,
        'Hola Pichangol, no tengo redes y quiero que me ayuden a crear y manejar '
        'las de "${widget.negocio.nombre}".');
  }

  @override
  void initState() {
    super.initState();
    _landingUrl = widget.negocio.landingUrl;
    _cargar();
  }

  Future<void> _cargar() async {
    setState(() => _cargando = true);
    await appState.sincronizarSaldoAcademia(_idAcademia);
    final planes =
        await PagosService.planesServicios(tipo: widget.negocio.tipo);
    final subs = await PagosService.estadoServicios(_idAcademia);
    final conn = await PagosService.estadoRedes(_idAcademia);
    final metodo = await PagosService.metodoSuscripcion(_idAcademia);
    if (!mounted) return;
    setState(() {
      _planes = planes;
      _subs = subs ?? const [];
      _redesConn = conn;
      _metodoSus = metodo;
      _cargando = false;
    });
  }

  Map<String, dynamic>? _subDe(String clave) {
    for (final s in _subs) {
      if (s['servicio'] == clave) return s;
    }
    return null;
  }

  // ¿La academia tiene el paquete "Presencia digital" activo?
  bool get _presenciaActiva => _subs.any((s) =>
      s['servicio'] == 'presencia' &&
      (s['estado'] == 'activa' || s['estado'] == 'pendiente_pago'));

  // ¿Este plan ya está incluido en un paquete mayor (Presencia)?
  bool _incluidoEnPresencia(String clave) =>
      (clave == 'landing' || clave == 'redes') && _presenciaActiva;

  Future<void> _contratar(Map<String, dynamic> plan) async {
    final clave = plan['clave'] as String;
    setState(() => _procesando = clave);
    final r = await PagosService.contratarServicio(
        duenoId: _idAcademia,
        academiaId: _idAcademia,
        servicio: clave,
        tipo: widget.negocio.tipo);
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
    if (r['incluido'] == true) {
      _msg('Ya está incluido en tu ${r['nombre_por'] ?? 'plan'}.');
      return;
    }
    if (r['ok'] == true) {
      await _cargar();
      final reemplaza = (r['reemplaza'] as List?) ?? const [];
      _msg(reemplaza.isEmpty
          ? '✅ ${plan['nombre']} activado. Te contactaremos para arrancar.'
          : '✅ ${plan['nombre']} activado (reemplaza tus planes individuales).');
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
          pais: widget.negocio.pais),
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
    final url = await appState.generarLandingNegocio(widget.negocio);
    if (!mounted) return;
    setState(() {
      _generandoLanding = false;
      if (url != null) _landingUrl = url;
    });
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
    final r =
        await appState.generarPostsNegocio(widget.negocio, _tema.text.trim());
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

  // --- Gestión de redes (conexión OAuth + publicación) --------------------
  /// Abre la pantalla guiada de conexión (requisitos → conectar → estado).
  Future<void> _gestionarRedes() async {
    await Navigator.of(context).push(MaterialPageRoute(
        builder: (_) => ConectarRedesScreen(negocio: widget.negocio)));
    if (mounted) await _cargar();
  }

  /// Pregunta si publicar con foto (IG+FB) o solo texto (FB). Instagram EXIGE
  /// una imagen, así que la opción con foto es la que llega a IG.
  Future<void> _publicar(int idx, Map<String, dynamic> p) async {
    final opcion = await showModalBottomSheet<String>(
      context: context,
      builder: (ctx) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Padding(
              padding: EdgeInsets.fromLTRB(16, 16, 16, 6),
              child: Align(
                alignment: Alignment.centerLeft,
                child: Text('¿Cómo publicamos?',
                    style: TextStyle(fontWeight: FontWeight.w800, fontSize: 16)),
              ),
            ),
            ListTile(
              leading: const Icon(Icons.photo_library_outlined, color: lima),
              title: const Text('Con foto (Instagram + Facebook)'),
              subtitle: const Text('Instagram requiere una imagen.'),
              onTap: () => Navigator.pop(ctx, 'foto'),
            ),
            ListTile(
              leading: const Icon(Icons.notes, color: lima),
              title: const Text('Solo texto (Facebook)'),
              onTap: () => Navigator.pop(ctx, 'texto'),
            ),
            const SizedBox(height: 8),
          ],
        ),
      ),
    );
    if (opcion == null) return;

    final texto = (p['texto'] ?? '').toString();
    final hashtags =
        ((p['hashtags'] as List?) ?? const []).map((e) => e.toString()).toList();
    final completo =
        hashtags.isEmpty ? texto : '$texto\n\n${hashtags.join(' ')}';

    String? imagenUrl;
    if (opcion == 'foto') {
      final f = await ImagePicker()
          .pickImage(source: ImageSource.gallery, maxWidth: 1080);
      if (f == null) return;
      final bytes = await f.readAsBytes();
      if (!mounted) return;
      setState(() => _publicando = idx);
      final ct = (f.mimeType != null && f.mimeType!.startsWith('image/'))
          ? f.mimeType!
          : (f.path.toLowerCase().endsWith('.png')
              ? 'image/png'
              : 'image/jpeg');
      imagenUrl = await PagosService.subirImagen(
          academiaId: _idAcademia, bytes: bytes, contentType: ct);
      if (!mounted) return;
      if (imagenUrl == null) {
        setState(() => _publicando = null);
        _msg('No se pudo subir la imagen. Reintenta.');
        return;
      }
    } else {
      setState(() => _publicando = idx);
    }

    final r = await PagosService.publicarPost(
        academiaId: _idAcademia, texto: completo, imagenUrl: imagenUrl);
    if (!mounted) return;
    setState(() => _publicando = null);
    if (r == null) {
      _msg('No se pudo publicar. Revisa tu conexión.');
      return;
    }
    if (r['ok'] == true) {
      final sim = r['simulado'] == true;
      _msg(sim
          ? '✅ Publicado (modo prueba). En vivo se publicará en tus redes.'
          : '✅ Publicado en tus redes.');
      await _cargar(); // refresca el contador de publicaciones
    } else {
      _msg('No se pudo publicar: ${r['error'] ?? 'error'}');
    }
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
                  // Saldo de marketing del negocio.
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
                              const Text('Saldo de marketing',
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
                  if (widget.negocio.esMixto) ...[
                    const SizedBox(height: 8),
                    _bannerUnificado(),
                  ],
                  const SizedBox(height: 8),
                  _cardDebitoAuto(),
                  if (_landingContratada) _cardLanding(),
                  if (_redesContratada) _cardGestion(),
                  if (_redesContratada) _cardRedes(),
                  const Padding(
                    padding: EdgeInsets.symmetric(vertical: 8, horizontal: 2),
                    child: Text(
                        'Contrata tu presencia digital. Se cobra del saldo o de tu '
                        'tarjeta cada mes; puedes cancelar cuando quieras.',
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

  /// Aviso de PRESENCIA UNIFICADA: cuando el dueño tiene academia + canchas, un
  /// solo plan cubre ambos (no paga doble). La landing deja reservar y matricular.
  Widget _bannerUnificado() {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: limaSuave,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: lima.withOpacity(0.35)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Icon(Icons.hub_outlined, color: bosque, size: 22),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text('Presencia unificada',
                    style: TextStyle(
                        fontWeight: FontWeight.w800,
                        fontSize: 15,
                        color: bosque)),
                const SizedBox(height: 2),
                Text(
                    'Tienes academia y canchas. Un solo plan las cubre a ambas: '
                    'tu página deja reservar cancha y matricularse. No pagas doble.',
                    style: TextStyle(fontSize: 13, color: bosque.withOpacity(0.85))),
              ],
            ),
          ),
        ],
      ),
    );
  }

  /// Tarjeta de DÉBITO AUTOMÁTICO: la academia guarda una tarjeta para que las
  /// suscripciones se cobren solas cada mes (si no hay saldo).
  Widget _cardDebitoAuto() {
    final tiene = _metodoSus?['tiene_tarjeta'] == true;
    final marca = (_metodoSus?['marca'] ?? '').toString();
    final u4 = (_metodoSus?['ultimos4'] ?? '').toString();
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
            children: [
              const Icon(Icons.credit_card, color: lima),
              const SizedBox(width: 8),
              const Expanded(
                child: Text('Débito automático',
                    style:
                        TextStyle(fontWeight: FontWeight.w800, fontSize: 16)),
              ),
              if (tiene)
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                  decoration: BoxDecoration(
                      color: limaSuave,
                      borderRadius: BorderRadius.circular(999)),
                  child: const Text('● Activo',
                      style: TextStyle(
                          fontSize: 11.5,
                          fontWeight: FontWeight.w800,
                          color: lima)),
                ),
            ],
          ),
          const SizedBox(height: 6),
          Text(
              tiene
                  ? 'Tus suscripciones se cobran solas cada mes. Tarjeta '
                      '${marca.isEmpty ? '' : '$marca '}····$u4.'
                  : 'Guarda una tarjeta y tus suscripciones se cobran solas cada '
                      'mes (si no tienes saldo). Sin perseguir el pago.',
              style: const TextStyle(color: textoTenue, fontSize: 13)),
          const SizedBox(height: 12),
          if (tiene)
            Align(
              alignment: Alignment.centerRight,
              child: TextButton.icon(
                icon: const Icon(Icons.delete_outline, size: 18, color: clayOscuro),
                label: const Text('Quitar tarjeta',
                    style: TextStyle(color: clayOscuro)),
                onPressed: _quitarTarjeta,
              ),
            )
          else
            SizedBox(
              width: double.infinity,
              child: FilledButton.icon(
                style: FilledButton.styleFrom(
                    backgroundColor: lima,
                    foregroundColor: Colors.white,
                    padding: const EdgeInsets.symmetric(vertical: 13)),
                icon: const Icon(Icons.add_card, size: 18),
                label: const Text('Agregar tarjeta',
                    style: TextStyle(fontWeight: FontWeight.w800)),
                onPressed: _agregarTarjeta,
              ),
            ),
        ],
      ),
    );
  }

  Future<void> _quitarTarjeta() async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Quitar tarjeta'),
        content: const Text(
            'Se elimina la tarjeta de débito automático. Tus suscripciones se '
            'cobrarán del saldo; recárgalo para que no se pausen.'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('No')),
          FilledButton(
              style: FilledButton.styleFrom(backgroundColor: clayOscuro),
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('Quitar')),
        ],
      ),
    );
    if (ok == true) {
      await PagosService.eliminarMetodoSuscripcion(_idAcademia);
      await _cargar();
    }
  }

  /// Hoja para tokenizar y guardar la tarjeta de débito automático (Culqi).
  Future<void> _agregarTarjeta() async {
    final cfg = await PagosService.config();
    final pk = (cfg?['public_key'] ?? '').toString();
    if (!mounted) return;
    if (cfg?['disponible'] != true || pk.isEmpty) {
      _msg('Pagos no configurados en el servidor.');
      return;
    }
    final email = appState.usuario?.email ?? '';
    final numero = TextEditingController();
    final exp = TextEditingController();
    final cvv = TextEditingController();
    var guardando = false;
    String? error;

    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Theme.of(context).colorScheme.surface,
      shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(24))),
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setSt) => Padding(
          padding: EdgeInsets.fromLTRB(
              18, 18, 18, MediaQuery.of(ctx).viewInsets.bottom + 18),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text('Tarjeta para débito automático',
                  style: TextStyle(fontWeight: FontWeight.w800, fontSize: 17)),
              const SizedBox(height: 4),
              const Text(
                  'Se guarda de forma segura (no guardamos el número). Se usará '
                  'para cobrar tus suscripciones cada mes.',
                  style: TextStyle(color: textoTenue, fontSize: 12.5)),
              const SizedBox(height: 14),
              TextField(
                controller: numero,
                keyboardType: TextInputType.number,
                decoration: const InputDecoration(
                    labelText: 'Número de tarjeta',
                    hintText: '4111 1111 1111 1111'),
              ),
              Row(
                children: [
                  Expanded(
                    child: TextField(
                      controller: exp,
                      keyboardType: TextInputType.number,
                      decoration: const InputDecoration(
                          labelText: 'Vence (MM/AA)', hintText: '09/28'),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: TextField(
                      controller: cvv,
                      keyboardType: TextInputType.number,
                      obscureText: true,
                      decoration: const InputDecoration(
                          labelText: 'CVV', hintText: '123'),
                    ),
                  ),
                ],
              ),
              if (error != null) ...[
                const SizedBox(height: 8),
                Text(error!, style: const TextStyle(color: clayOscuro, fontSize: 13)),
              ],
              const SizedBox(height: 16),
              SizedBox(
                width: double.infinity,
                child: FilledButton(
                  style: FilledButton.styleFrom(
                      backgroundColor: lima,
                      foregroundColor: Colors.white,
                      padding: const EdgeInsets.symmetric(vertical: 14)),
                  onPressed: guardando
                      ? null
                      : () async {
                          final num = numero.text.replaceAll(' ', '');
                          final partes = exp.text.split('/');
                          final mes = partes.isNotEmpty
                              ? (int.tryParse(partes[0].trim()) ?? 0)
                              : 0;
                          var anio = partes.length > 1
                              ? (int.tryParse(partes[1].trim()) ?? 0)
                              : 0;
                          if (anio < 100) anio += 2000;
                          if (num.length < 15) {
                            setSt(() => error = 'Número de tarjeta inválido.');
                            return;
                          }
                          if (mes < 1 || mes > 12) {
                            setSt(() =>
                                error = 'Fecha inválida. Escribe MES/AÑO, ej. 09/28.');
                            return;
                          }
                          if (cvv.text.trim().length < 3) {
                            setSt(() => error = 'CVV inválido.');
                            return;
                          }
                          setSt(() {
                            guardando = true;
                            error = null;
                          });
                          final tok = await PagosService.tokenizarTarjeta(
                              publicKey: pk,
                              numero: num,
                              cvv: cvv.text.trim(),
                              mesExp: mes,
                              anioExp: anio,
                              email: email);
                          if (tok['ok'] != true) {
                            setSt(() {
                              guardando = false;
                              error = tok['error']?.toString() ??
                                  'No se pudo validar la tarjeta.';
                            });
                            return;
                          }
                          final r = await PagosService.guardarMetodoSuscripcion(
                              academiaId: _idAcademia,
                              token: tok['token'].toString(),
                              email: email);
                          if (r['ok'] == true) {
                            if (ctx.mounted) Navigator.pop(ctx);
                          } else {
                            setSt(() {
                              guardando = false;
                              error = r['error']?.toString() ??
                                  'No se pudo guardar la tarjeta.';
                            });
                          }
                        },
                  child: guardando
                      ? const SizedBox(
                          height: 20,
                          width: 20,
                          child: CircularProgressIndicator(
                              strokeWidth: 2.4, color: Colors.white))
                      : const Text('Guardar tarjeta'),
                ),
              ),
            ],
          ),
        ),
      ),
    );
    if (mounted) await _cargar();
  }

  /// Tarjeta "Publicación automática": conectar el IG/FB del dueño para que
  /// Pichangol publique por él (parte de Manejo de redes; permiso revocable).
  Widget _cardGestion() {
    final conectada = _redesConectada;
    final modo = (_redesConn?['modo'] ?? '').toString();
    final ig = (_redesConn?['ig_username'] ?? '').toString();
    final page = (_redesConn?['page_nombre'] ?? '').toString();
    final pubs = (_redesConn?['publicaciones'] as num?)?.toInt() ?? 0;
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: bosque,
        borderRadius: BorderRadius.circular(16),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.hub, color: lima),
              const SizedBox(width: 8),
              const Expanded(
                child: Text('Publicación automática',
                    style: TextStyle(
                        fontWeight: FontWeight.w800,
                        fontSize: 16,
                        color: Colors.white)),
              ),
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                decoration: BoxDecoration(
                  color: conectada ? lima : Colors.white24,
                  borderRadius: BorderRadius.circular(999),
                ),
                child: Text(conectada ? '● Conectada' : 'Sin conectar',
                    style: TextStyle(
                        fontSize: 11.5,
                        fontWeight: FontWeight.w800,
                        color: conectada ? bosque : Colors.white)),
              ),
            ],
          ),
          const SizedBox(height: 6),
          Text(
              conectada
                  ? 'Publicamos por ti en tus redes. ${ig.isNotEmpty ? '@$ig' : ''}'
                      '${page.isNotEmpty ? (ig.isNotEmpty ? ' · ' : '') + page : ''}'
                  : 'Conecta tu Instagram/Facebook y nosotros publicamos por ti. '
                      'Tú das el permiso a Meta y lo puedes revocar cuando quieras.',
              style: const TextStyle(color: Colors.white70, fontSize: 13)),
          if (conectada && pubs > 0) ...[
            const SizedBox(height: 6),
            Text('$pubs publicación${pubs == 1 ? '' : 'es'} realizada'
                '${pubs == 1 ? '' : 's'}.',
                style: const TextStyle(color: Colors.white54, fontSize: 12)),
          ],
          if (modo == 'sandbox') ...[
            const SizedBox(height: 8),
            Container(
              padding: const EdgeInsets.all(10),
              decoration: BoxDecoration(
                color: Colors.white.withOpacity(0.10),
                borderRadius: BorderRadius.circular(10),
              ),
              child: const Text(
                  '🧪 Modo prueba: el flujo funciona pero aún no se publica en '
                  'redes reales (falta la aprobación de Meta). Se activará solo '
                  'cuando esté lista, sin que hagas nada.',
                  style: TextStyle(color: Colors.white70, fontSize: 11.5)),
            ),
          ],
          const SizedBox(height: 12),
          SizedBox(
            width: double.infinity,
            child: FilledButton.icon(
              style: FilledButton.styleFrom(
                  backgroundColor: lima,
                  foregroundColor: bosque,
                  padding: const EdgeInsets.symmetric(vertical: 13)),
              icon: Icon(conectada ? Icons.settings : Icons.link, size: 18),
              label: Text(
                  conectada ? 'Gestionar conexión' : 'Conectar Instagram / Facebook',
                  style: const TextStyle(fontWeight: FontWeight.w800)),
              onPressed: _gestionarRedes,
            ),
          ),
        ],
      ),
    );
  }

  /// Tarjeta "Tu landing" (fulfillment): genera / ve / comparte la página web.
  Widget _cardLanding() {
    final url = _landingUrl;
    final tiene = url.isNotEmpty;
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
                      'tu negocio (actualízala si cambias precios o fotos).'
                  : 'Genera tu página web con los datos de tu negocio. Queda con '
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
                  onPressed: () => _abrir(url),
                ),
                OutlinedButton.icon(
                  style: OutlinedButton.styleFrom(
                      foregroundColor: lima,
                      side: const BorderSide(color: lima)),
                  icon: const Icon(Icons.share_outlined, size: 18),
                  label: const Text('Compartir'),
                  onPressed: () => WhatsAppLink.compartir(
                      'Mira nuestra página: $url'),
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
            for (final e in _posts!.asMap().entries) _postItem(e.key, e.value),
          ],
        ],
      ),
    );
  }

  Widget _postItem(int idx, Map<String, dynamic> p) {
    final texto = (p['texto'] ?? '').toString();
    final hashtags =
        ((p['hashtags'] as List?) ?? const []).map((e) => e.toString()).toList();
    final hora = (p['hora_sugerida'] ?? '').toString();
    final completo = hashtags.isEmpty ? texto : '$texto\n\n${hashtags.join(' ')}';
    // Publicar directo sólo si contrató Manejo de redes y está conectado.
    final puedePublicar = _redesContratada && _redesConectada;
    final publicandoEste = _publicando == idx;
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
              if (puedePublicar)
                TextButton.icon(
                  icon: publicandoEste
                      ? const SizedBox(
                          height: 14,
                          width: 14,
                          child: CircularProgressIndicator(strokeWidth: 2))
                      : const Icon(Icons.send, size: 16, color: lima),
                  label: const Text('Publicar',
                      style: TextStyle(
                          color: lima, fontWeight: FontWeight.w800)),
                  onPressed:
                      _publicando != null ? null : () => _publicar(idx, p),
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
          ] else if (_incluidoEnPresencia(clave))
            Container(
              padding:
                  const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              decoration: BoxDecoration(
                color: limaSuave,
                borderRadius: BorderRadius.circular(999),
              ),
              child: const Text('✓ Incluido en Presencia digital',
                  style: TextStyle(
                      fontSize: 12.5,
                      fontWeight: FontWeight.w700,
                      color: lima)),
            )
          else
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
