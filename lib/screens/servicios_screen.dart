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
import '../widgets/dialogo_pichangol.dart';
import '../widgets/cargando_pichangol.dart';
import '../widgets/responsive.dart';
import 'conectar_redes_screen.dart';
import 'cuenta_screen.dart';
import 'recargar_saldo_screen.dart';

/// "Servicios Pichangol": el dueño de un NEGOCIO (academia o club) contrata
/// landing / manejo de redes / presencia digital como SUSCRIPCIÓN mensual,
/// pagada con el saldo de marketing (mismo saldo prepago de Culqi). Muestra
/// estado y próximo cobro.
class ServiciosScreen extends StatefulWidget {
  const ServiciosScreen(
      {super.key, required this.negocio, this.mostrarBilleteraEnAppBar = true});
  final Negocio negocio;

  /// Muestra el acceso a "Mi billetera" en el AppBar. En la academia (tablet) va
  /// en `false` porque la billetera es su propio ítem del menú lateral.
  final bool mostrarBilleteraEnAppBar;

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

  // URL de la landing (se actualiza al generarla). Init desde el negocio.
  String _landingUrl = '';

  @override
  void dispose() {
    _tema.dispose();
    super.dispose();
  }

  String get _mon => widget.negocio.monedaSimbolo;
  String get _idAcademia => widget.negocio.id;
  // BILLETERA ÚNICA: llave del saldo del que se cobran los servicios = correo del
  // dueño; si el negocio no lo trae (compat), cae al id.
  String get _billetera =>
      widget.negocio.dueno.isNotEmpty ? widget.negocio.dueno : widget.negocio.id;

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
    // Todas las consultas EN PARALELO (antes iban en serie → carga lenta).
    final saldoF = appState.sincronizarSaldoAcademia(_idAcademia);
    final resultados = await Future.wait([
      PagosService.planesServicios(tipo: widget.negocio.tipo),
      PagosService.estadoServicios(_idAcademia),
      PagosService.estadoRedes(_idAcademia),
    ]);
    await saldoF;
    final planes = resultados[0] as List<Map<String, dynamic>>?;
    final subs = resultados[1] as List<Map<String, dynamic>>?;
    final conn = resultados[2] as Map<String, dynamic>?;
    if (!mounted) return;
    setState(() {
      _planes = planes;
      _subs = subs ?? const [];
      _redesConn = conn;
      _cargando = false;
    });
    // Conectar = declarar: si ya está conectado, auto-completa el @usuario de IG y
    // la Página de FB en la academia (solo lo vacío). El negocio unificado usa la
    // academia del dueño.
    if (conn?['conectado'] == true) {
      final academiaId = widget.negocio.esClub
          ? null
          : (widget.negocio.esMixto
              ? appState.miAcademia?.id
              : widget.negocio.id);
      if (academiaId != null) {
        appState.actualizarRedesAcademia(
          academiaId,
          instagram: (conn?['ig_username'] ?? '').toString(),
          facebook: (conn?['page_nombre'] ?? '').toString(),
        );
      }
    }
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
    Map<String, dynamic>? r;
    try {
      // Regla: acción que demora → preload de marca (overlay), nunca círculo.
      r = await conPreload(
        context,
        () => PagosService.contratarServicio(
            duenoId: _billetera,
            academiaId: _idAcademia,
            servicio: clave,
            tipo: widget.negocio.tipo),
        texto: 'Contratando…',
      );
    } finally {
      if (mounted) setState(() => _procesando = null);
    }
    if (!mounted) return;
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
    final ir = await confirmarPichangol(
      context,
      titulo: 'Saldo insuficiente',
      mensaje: 'Necesitas $_mon ${requerido.toStringAsFixed(0)} de saldo para '
          'contratar este servicio. Recarga y vuelve a intentarlo.',
      textoConfirmar: 'Recargar saldo',
      textoCancelar: 'Ahora no',
      icono: Icons.account_balance_wallet_outlined,
    );
    if (ir && mounted) await _pushRecarga();
  }

  Future<void> _pushRecarga() async {
    await Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => RecargarSaldoScreen(
          duenoId: _billetera,
          titulo: 'Recargar saldo',
          pais: widget.negocio.pais),
    ));
    await _cargar();
  }

  Future<void> _cancelar(String clave, String nombre) async {
    final ok = await confirmarPichangol(
      context,
      titulo: 'Cancelar $nombre',
      mensaje: 'Se cancela la renovación del próximo mes. El mes en curso sigue '
          'activo hasta su fecha.',
      textoConfirmar: 'Sí, cancelar',
      textoCancelar: 'No',
      destructivo: true,
      icono: Icons.cancel_outlined,
    );
    if (ok) {
      await PagosService.cancelarServicio(academiaId: _idAcademia, servicio: clave);
      await _cargar();
    }
  }

  void _msg(String t) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(t)));
  }

  Future<void> _generarLanding() async {
    if (_generandoLanding) return;
    setState(() => _generandoLanding = true);
    String? url;
    try {
      // Regla: acción que demora → preload de marca (overlay), nunca círculo.
      url = await conPreload(
        context,
        () => appState.generarLandingNegocio(widget.negocio),
        texto: 'Publicando tu landing…',
      );
    } finally {
      if (mounted) setState(() => _generandoLanding = false);
    }
    if (!mounted) return;
    if (url != null) setState(() => _landingUrl = url!);
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
    if (_generandoPosts) return;
    setState(() => _generandoPosts = true);
    Map<String, dynamic>? r;
    try {
      // Regla: acción que demora → preload de marca (overlay), nunca círculo.
      r = await conPreload(
        context,
        () => appState.generarPostsNegocio(widget.negocio, _tema.text.trim()),
        texto: 'Generando tus posts…',
      );
    } finally {
      if (mounted) setState(() => _generandoPosts = false);
    }
    if (!mounted) return;
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

    // La foto se ELIGE antes del preload (es interacción del usuario). La subida
    // y la publicación (lo que demora) van bajo el preload de marca.
    List<int>? bytes;
    String? ct;
    if (opcion == 'foto') {
      final f = await ImagePicker()
          .pickImage(source: ImageSource.gallery, maxWidth: 1080);
      if (f == null) return;
      bytes = await f.readAsBytes();
      ct = (f.mimeType != null && f.mimeType!.startsWith('image/'))
          ? f.mimeType!
          : (f.path.toLowerCase().endsWith('.png')
              ? 'image/png'
              : 'image/jpeg');
    }
    if (!mounted) return;

    setState(() => _publicando = idx);
    Map<String, dynamic>? r;
    var imgFallo = false;
    try {
      // Regla: acción que demora → preload de marca (overlay), nunca círculo.
      r = await conPreload(context, () async {
        String? imagenUrl;
        if (bytes != null) {
          imagenUrl = await PagosService.subirImagen(
              academiaId: _idAcademia, bytes: bytes!, contentType: ct!);
          if (imagenUrl == null) {
            imgFallo = true;
            return null;
          }
        }
        return PagosService.publicarPost(
            academiaId: _idAcademia, texto: completo, imagenUrl: imagenUrl);
      }, texto: 'Publicando en tus redes…');
    } finally {
      if (mounted) setState(() => _publicando = null);
    }
    if (!mounted) return;
    if (imgFallo) {
      _msg('No se pudo subir la imagen. Reintenta.');
      return;
    }
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
    return Scaffold(
      appBar: AppBar(
        title: const Text('Servicios Pichangol'),
        actions: [
          // "Mi billetera": solo cuando NO hay menú lateral (club / móvil). En la
          // academia va como ítem del rail, así que aquí se oculta. Es el mismo
          // módulo de billetera (saldo + movimientos) que el resto del app.
          if (widget.mostrarBilleteraEnAppBar)
            IconButton(
              tooltip: 'Mi billetera',
              icon: const Icon(Icons.account_balance_wallet_outlined),
              onPressed: () => Navigator.of(context).push(
                  MaterialPageRoute(builder: (_) => const CuentaScreen())),
            ),
        ],
      ),
      body: _cargando
          ? const CargandoPichangol()
          : RefreshIndicator(
              onRefresh: _cargar,
              color: lima,
              // Centra el contenido en tablet (ancho máx.) para que las tarjetas
              // no se estiren a todo lo ancho; en móvil no cambia nada.
              child: AnchoTablet(
                maxWidth: 640,
                child: ListView(
                padding: const EdgeInsets.fromLTRB(16, 14, 16, 30),
                children: [
                  const Text('Impulsa tu negocio',
                      style: TextStyle(
                          fontWeight: FontWeight.w800, fontSize: 19)),
                  const SizedBox(height: 4),
                  const Text(
                      'Contrata solo lo que necesitas. Se cobra a tu billetera '
                      'cada mes; cancela cuando quieras.',
                      style: TextStyle(color: textoTenue, fontSize: 13)),
                  // El método de pago de los servicios ya no va aquí: se maneja
                  // desde la billetera (mismo módulo de saldo/movimientos).
                  const SizedBox(height: 14),
                  if (_planes == null)
                    const Padding(
                      padding: EdgeInsets.all(24),
                      child: Text('No se pudo cargar el catálogo.',
                          style: TextStyle(color: textoTenue)),
                    )
                  else
                    for (final p in _planes!) _addonCard(p),
                ],
                ),
              ),
            ),
    );
  }

  /// Sub-título de una herramienta dentro del addon (estilo congruente).
  Widget _tituloTool(IconData ico, String texto) => Padding(
        padding: const EdgeInsets.only(top: 2, bottom: 6),
        child: Row(
          children: [
            Icon(ico, size: 18, color: lima),
            const SizedBox(width: 6),
            Text(texto,
                style: const TextStyle(
                    fontWeight: FontWeight.w800, fontSize: 14.5)),
          ],
        ),
      );

  /// Herramienta "Publicación automática": conectar el IG/FB del dueño para que
  /// Pichangol publique por él (permiso revocable). Contenido plano (va dentro
  /// del addon), sin contenedor propio.
  Widget _publicacionTools() {
    final conectada = _redesConectada;
    final modo = (_redesConn?['modo'] ?? '').toString();
    final ig = (_redesConn?['ig_username'] ?? '').toString();
    final page = (_redesConn?['page_nombre'] ?? '').toString();
    final pubs = (_redesConn?['publicaciones'] as num?)?.toInt() ?? 0;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Expanded(
              child: Text(
                  conectada
                      ? 'Publicamos por ti. ${ig.isNotEmpty ? '@$ig' : ''}'
                          '${page.isNotEmpty ? (ig.isNotEmpty ? ' · ' : '') + page : ''}'
                      : 'Conecta tu Instagram/Facebook y publicamos por ti. Das '
                          'el permiso a Meta y lo revocas cuando quieras.',
                  style: const TextStyle(color: textoTenue, fontSize: 13)),
            ),
            const SizedBox(width: 8),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
              decoration: BoxDecoration(
                color: conectada ? limaSuave : trazo.withOpacity(0.5),
                borderRadius: BorderRadius.circular(999),
              ),
              child: Text(conectada ? '● Conectada' : 'Sin conectar',
                  style: TextStyle(
                      fontSize: 11.5,
                      fontWeight: FontWeight.w800,
                      color: conectada ? lima : textoTenue)),
            ),
          ],
        ),
        if (conectada && pubs > 0) ...[
          const SizedBox(height: 4),
          Text('$pubs publicación${pubs == 1 ? '' : 'es'} realizada'
              '${pubs == 1 ? '' : 's'}.',
              style: const TextStyle(color: textoTenue, fontSize: 12)),
        ],
        if (modo == 'sandbox') ...[
          const SizedBox(height: 8),
          Container(
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(
              color: const Color(0xFFFBEAD2),
              borderRadius: BorderRadius.circular(10),
            ),
            child: const Text(
                '🧪 Modo prueba: el flujo funciona pero aún no se publica en '
                'redes reales (falta la aprobación de Meta). Se activará solo '
                'cuando esté lista.',
                style: TextStyle(color: clayOscuro, fontSize: 11.5)),
          ),
        ],
        const SizedBox(height: 10),
        SizedBox(
          width: double.infinity,
          child: OutlinedButton.icon(
            style: OutlinedButton.styleFrom(
                foregroundColor: lima,
                side: const BorderSide(color: lima),
                padding: const EdgeInsets.symmetric(vertical: 12)),
            icon: Icon(conectada ? Icons.settings : Icons.link, size: 18),
            label: Text(
                conectada ? 'Gestionar conexión' : 'Conectar Instagram / Facebook',
                style: const TextStyle(fontWeight: FontWeight.w800)),
            onPressed: _gestionarRedes,
          ),
        ),
      ],
    );
  }

  /// Herramienta "Tu landing web": genera / ve / comparte la página. Contenido
  /// plano (va dentro del addon).
  Widget _landingTools() {
    final url = _landingUrl;
    final tiene = url.isNotEmpty;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
            tiene
                ? 'Publicada y lista para compartir. Se arma con los datos de tu '
                    'negocio (actualízala si cambias precios o fotos).'
                : 'Genera tu página web con los datos de tu negocio. Queda con un '
                    'enlace público para compartir.',
            style: const TextStyle(color: textoTenue, fontSize: 13)),
        const SizedBox(height: 10),
        if (tiene)
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
                    foregroundColor: lima, side: const BorderSide(color: lima)),
                icon: const Icon(Icons.share_outlined, size: 18),
                label: const Text('Compartir'),
                onPressed: () =>
                    WhatsAppLink.compartir('Mira nuestra página: $url'),
              ),
              TextButton.icon(
                icon: const Icon(Icons.refresh, size: 18),
                label: const Text('Actualizar'),
                onPressed: _generandoLanding ? null : _generarLanding,
              ),
            ],
          )
        else
          SizedBox(
            width: double.infinity,
            child: FilledButton(
              style: FilledButton.styleFrom(
                  backgroundColor: lima,
                  foregroundColor: Colors.white,
                  padding: const EdgeInsets.symmetric(vertical: 13)),
              onPressed: _generandoLanding ? null : _generarLanding,
              child: const Text('Generar mi landing'),
            ),
          ),
      ],
    );
  }

  /// Herramienta "Community manager IA": genera posts a partir de un tema.
  /// Contenido plano (va dentro del addon).
  Widget _postsTools() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text(
            'Genera posts listos (texto + hashtags + mejor hora). Los revisas y '
            'compartes a tus redes con un tap.',
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
            icon: const Icon(Icons.auto_awesome, size: 18),
            label: Text(_posts == null ? 'Generar posts' : 'Generar otros'),
            onPressed: _generandoPosts ? null : _generarPosts,
          ),
        ),
        if (_posts != null) ...[
          const SizedBox(height: 12),
          for (final e in _posts!.asMap().entries) _postItem(e.key, e.value),
        ],
      ],
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
                  icon: const Icon(Icons.send, size: 16, color: lima),
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

  /// Ícono representativo de cada addon (marketplace).
  IconData _iconoAddon(String clave) {
    switch (clave) {
      case 'landing':
        return Icons.public;
      case 'redes':
        return Icons.campaign_outlined;
      case 'presencia':
        return Icons.auto_awesome;
      default:
        return Icons.widgets_outlined;
    }
  }

  /// Herramientas (fulfillment) que incluye un addon activo, según su clave.
  List<Widget> _toolsDe(String clave) {
    final daLanding = clave == 'landing' || clave == 'presencia';
    final daRedes = clave == 'redes' || clave == 'presencia';
    return [
      if (daLanding) ...[
        _tituloTool(Icons.public, 'Tu landing web'),
        _landingTools(),
      ],
      if (daRedes) ...[
        if (daLanding) const SizedBox(height: 18),
        _tituloTool(Icons.hub, 'Publicación automática'),
        _publicacionTools(),
        const SizedBox(height: 18),
        _tituloTool(Icons.auto_awesome, 'Community manager con IA'),
        _postsTools(),
      ],
    ];
  }

  /// Tarjeta UNIFORME de un addon (estilo marketplace): mismo formato para todos.
  /// Si está activo, sus herramientas se abren en un panel colapsable
  /// ("Administrar") para no alargar la vista.
  Widget _addonCard(Map<String, dynamic> plan) {
    final clave = plan['clave'] as String;
    final nombre = (plan['nombre'] ?? '') as String;
    final desc = (plan['desc'] ?? '') as String;
    final soles = (plan['soles'] as num?)?.toDouble() ?? 0;
    final sub = _subDe(clave);
    final estado = sub?['estado'] as String?;
    final activa = estado == 'activa';
    final pendiente = estado == 'pendiente_pago';
    final procesando = _procesando == clave;
    final incluido = _incluidoEnPresencia(clave);
    final cs = Theme.of(context).colorScheme;

    final header = Padding(
      padding: const EdgeInsets.fromLTRB(16, 16, 16, 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                width: 40,
                height: 40,
                decoration: BoxDecoration(
                    color: limaSuave, borderRadius: BorderRadius.circular(12)),
                child: Icon(_iconoAddon(clave), color: lima, size: 22),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(nombre,
                        style: const TextStyle(
                            fontWeight: FontWeight.w800, fontSize: 16.5)),
                    const SizedBox(height: 2),
                    Text(desc,
                        style: const TextStyle(
                            color: textoTenue, fontSize: 12.8, height: 1.25)),
                  ],
                ),
              ),
              const SizedBox(width: 8),
              Column(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  Text('$_mon ${soles.toStringAsFixed(0)}',
                      style: const TextStyle(
                          fontWeight: FontWeight.w900,
                          fontSize: 17,
                          color: lima)),
                  const Text('/mes',
                      style: TextStyle(color: textoTenue, fontSize: 11)),
                ],
              ),
            ],
          ),
          const SizedBox(height: 12),
          if (activa || pendiente)
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
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
            )
          else if (incluido)
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              decoration: BoxDecoration(
                  color: limaSuave, borderRadius: BorderRadius.circular(999)),
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
                child: Text('Contratar · $_mon ${soles.toStringAsFixed(0)}/mes'),
              ),
            ),
        ],
      ),
    );

    final tools = <Widget>[];
    if (activa || pendiente) {
      tools.addAll(_toolsDe(clave));
      tools.add(Align(
        alignment: Alignment.centerRight,
        child: TextButton(
          onPressed: () => _cancelar(clave, nombre),
          child: const Text('Cancelar suscripción',
              style: TextStyle(color: clayOscuro)),
        ),
      ));
    }

    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      clipBehavior: Clip.antiAlias,
      decoration: BoxDecoration(
        color: cs.surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: trazo),
      ),
      child: Column(
        children: [
          header,
          if (tools.isNotEmpty)
            Theme(
              data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
              child: ExpansionTile(
                tilePadding: const EdgeInsets.symmetric(horizontal: 16),
                childrenPadding: const EdgeInsets.fromLTRB(16, 0, 16, 14),
                expandedCrossAxisAlignment: CrossAxisAlignment.start,
                leading: const Icon(Icons.build_outlined, size: 20, color: lima),
                title: const Text('Administrar',
                    style: TextStyle(fontWeight: FontWeight.w700, fontSize: 14)),
                children: tools,
              ),
            ),
        ],
      ),
    );
  }
}
