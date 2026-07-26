import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../brand.dart';
import '../models/negocio.dart';
import '../services/growth_service.dart';
import '../services/pagos_service.dart';
import '../services/whatsapp_link.dart';
import '../theme.dart';
import '../widgets/cargando_pichangol.dart';

/// Flujo GUIADO para que el dueño conecte su Instagram/Facebook y Pichangol
/// publique por él (Gestión de redes / Nivel 2). Verifica requisitos, abre el
/// permiso de Meta, muestra las cuentas conectadas y permite desconectar.
class ConectarRedesScreen extends StatefulWidget {
  const ConectarRedesScreen({super.key, required this.negocio});
  final Negocio negocio;

  @override
  State<ConectarRedesScreen> createState() => _ConectarRedesScreenState();
}

class _ConectarRedesScreenState extends State<ConectarRedesScreen> {
  static const _baseUrl = String.fromEnvironment('GROWTH_API_URL');

  Map<String, dynamic>? _conn;
  bool _cargando = true;
  bool _conectando = false;

  String get _idAcademia => widget.negocio.id;
  bool get _conectada => _conn?['conectado'] == true;

  @override
  void initState() {
    super.initState();
    _cargar();
  }

  Future<void> _cargar() async {
    setState(() => _cargando = true);
    final c = await PagosService.estadoRedes(_idAcademia);
    if (!mounted) return;
    setState(() {
      _conn = c;
      _cargando = false;
    });
  }

  void _msg(String t) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(t)));
  }

  Future<void> _abrir(String url) async {
    final u = Uri.tryParse(url);
    if (u != null) await launchUrl(u, mode: LaunchMode.externalApplication);
  }

  Future<void> _conectar() async {
    if (_conectando) return;
    setState(() => _conectando = true);
    Map<String, dynamic>? res;
    try {
      res = await conPreload(
          context,
          () => PagosService.conectarRedes(
              academiaId: _idAcademia,
              // BILLETERA ÚNICA: el dueño (correo) es la llave del saldo.
              duenoId: widget.negocio.dueno.isNotEmpty
                  ? widget.negocio.dueno
                  : _idAcademia),
          texto: 'Conectando…');
    } finally {
      if (mounted) setState(() => _conectando = false);
    }
    if (!mounted) return;
    // Copia a un final: Dart no promueve una variable asignada dentro de `try`.
    final r = res;
    if (r == null || r['ok'] != true) {
      _msg('No se pudo iniciar la conexión. Reintenta.');
      return;
    }
    final loginUrl = r['login_url'] as String?;
    if (loginUrl != null && loginUrl.isNotEmpty) {
      await _abrir(loginUrl);
      if (!mounted) return;
      await showDialog<void>(
        context: context,
        builder: (ctx) => AlertDialog(
          title: const Text('Autoriza en Facebook'),
          content: const Text(
              'Se abrió una página de Facebook para que autorices a Pichangol a '
              'publicar en tu Instagram/Facebook. Cuando termines y veas el '
              'mensaje de confirmación, vuelve aquí y toca "Ya autoricé".'),
          actions: [
            FilledButton(
                style: FilledButton.styleFrom(backgroundColor: lima),
                onPressed: () => Navigator.pop(ctx),
                child: const Text('Ya autoricé')),
          ],
        ),
      );
      await _cargar();
      if (_conectada) _msg('✅ Redes conectadas.');
    } else {
      // Sandbox: conectó al instante.
      setState(() => _conn = Map<String, dynamic>.from(
          (r['conexion'] as Map?) ?? const {}));
      _msg('✅ Redes conectadas.');
    }
  }

  Future<void> _desconectar() async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Desconectar redes'),
        content: const Text(
            'Dejaremos de publicar por ti. Puedes volver a conectar cuando '
            'quieras. También puedes revocar el permiso desde tu Facebook.'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('No')),
          FilledButton(
              style: FilledButton.styleFrom(backgroundColor: clayOscuro),
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('Desconectar')),
        ],
      ),
    );
    if (ok == true) {
      await PagosService.desconectarRedes(_idAcademia);
      await _cargar();
    }
  }

  Future<void> _ayuda() async {
    final numero =
        await GrowthService.contactoWhatsApp(widget.negocio.pais.iso) ??
            kContactoWhatsApp;
    await WhatsAppLink.abrir(
        numero,
        'Hola Pichangol, quiero conectar las redes de "${widget.negocio.nombre}" '
        'pero necesito ayuda con mi Instagram/Página.');
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Conectar tus redes')),
      body: _cargando
          ? const CargandoPichangol()
          : RefreshIndicator(
              color: lima,
              onRefresh: _cargar,
              child: ListView(
                padding: const EdgeInsets.fromLTRB(16, 16, 16, 32),
                children: _conectada ? _conectadaUI() : _porConectarUI(),
              ),
            ),
    );
  }

  // ---- Estado: aún sin conectar --------------------------------------------
  List<Widget> _porConectarUI() {
    final modo = (_conn?['modo'] ?? '').toString();
    return [
      _hero(),
      const SizedBox(height: 16),
      const Text('Antes de conectar, revisa 2 cosas',
          style: TextStyle(fontWeight: FontWeight.w800, fontSize: 16)),
      const SizedBox(height: 8),
      _requisito(
        '1',
        'Tu Instagram debe ser cuenta Business o Creator',
        'En Instagram: Configuración → Cuenta → Cambiar a cuenta profesional. '
            'Es gratis y toma 1 minuto.',
      ),
      _requisito(
        '2',
        'Ese Instagram debe estar vinculado a una Página de Facebook',
        'En Instagram profesional: Configuración → Compartir en otras apps → '
            'Facebook, y vincula tu Página. Si no tienes Página, créala gratis.',
      ),
      const SizedBox(height: 4),
      Align(
        alignment: Alignment.centerLeft,
        child: TextButton.icon(
          onPressed: _ayuda,
          icon: const Icon(Icons.support_agent, size: 18),
          label: const Text('No tengo eso / necesito ayuda'),
        ),
      ),
      const SizedBox(height: 8),
      if (modo == 'sandbox') _avisoSandbox(),
      const SizedBox(height: 8),
      SizedBox(
        width: double.infinity,
        child: FilledButton.icon(
          style: FilledButton.styleFrom(
              backgroundColor: lima,
              foregroundColor: Colors.white,
              padding: const EdgeInsets.symmetric(vertical: 15)),
          icon: const Icon(Icons.link),
          label: const Text('Conectar Instagram / Facebook',
              style: TextStyle(fontWeight: FontWeight.w800, fontSize: 15)),
          onPressed: _conectando ? null : _conectar,
        ),
      ),
      const SizedBox(height: 14),
      _piePrivacidad(),
    ];
  }

  // ---- Estado: conectada ----------------------------------------------------
  List<Widget> _conectadaUI() {
    final ig = (_conn?['ig_username'] ?? '').toString();
    final page = (_conn?['page_nombre'] ?? '').toString();
    final pubs = (_conn?['publicaciones'] as num?)?.toInt() ?? 0;
    final modo = (_conn?['modo'] ?? '').toString();
    return [
      Container(
        padding: const EdgeInsets.all(18),
        decoration: BoxDecoration(
          color: bosque,
          borderRadius: BorderRadius.circular(18),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: const [
                Icon(Icons.check_circle, color: lima, size: 24),
                SizedBox(width: 8),
                Text('Redes conectadas',
                    style: TextStyle(
                        color: Colors.white,
                        fontWeight: FontWeight.w800,
                        fontSize: 18)),
              ],
            ),
            const SizedBox(height: 12),
            if (ig.isNotEmpty)
              _cuentaFila(Icons.camera_alt_outlined, 'Instagram', '@$ig'),
            if (page.isNotEmpty)
              _cuentaFila(Icons.facebook, 'Facebook', page),
            if (pubs > 0) ...[
              const SizedBox(height: 8),
              Text('$pubs publicación${pubs == 1 ? '' : 'es'} realizada'
                  '${pubs == 1 ? '' : 's'}.',
                  style: const TextStyle(color: Colors.white60, fontSize: 12.5)),
            ],
          ],
        ),
      ),
      const SizedBox(height: 14),
      Container(
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: limaSuave,
          borderRadius: BorderRadius.circular(14),
        ),
        child: const Text(
            'Ya podemos publicar por ti. Genera contenido en "Community manager '
            'con IA" y aprueba cada post con "Publicar".',
            style: TextStyle(fontSize: 13.5, height: 1.3)),
      ),
      const SizedBox(height: 8),
      if (modo == 'sandbox') _avisoSandbox(),
      const SizedBox(height: 6),
      Align(
        alignment: Alignment.centerRight,
        child: TextButton.icon(
          onPressed: _desconectar,
          icon: const Icon(Icons.link_off, size: 18, color: clayOscuro),
          label: const Text('Desconectar',
              style: TextStyle(color: clayOscuro)),
        ),
      ),
      const SizedBox(height: 8),
      _piePrivacidad(),
    ];
  }

  // ---- Piezas ---------------------------------------------------------------
  Widget _hero() {
    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          colors: [lima, teal],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
        borderRadius: BorderRadius.circular(18),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: const [
          Icon(Icons.hub, color: Colors.white, size: 28),
          SizedBox(height: 10),
          Text('Publicamos por ti',
              style: TextStyle(
                  color: Colors.white,
                  fontWeight: FontWeight.w900,
                  fontSize: 20)),
          SizedBox(height: 6),
          Text(
              'Conecta tu Instagram y Facebook y nosotros publicamos por ti. '
              'Tú apruebas cada contenido y puedes revocar el permiso cuando '
              'quieras.',
              style: TextStyle(color: Colors.white, fontSize: 14, height: 1.35)),
        ],
      ),
    );
  }

  Widget _requisito(String n, String titulo, String detalle) {
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: trazo),
      ),
      child: Theme(
        data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
        child: ExpansionTile(
          tilePadding: const EdgeInsets.symmetric(horizontal: 14),
          childrenPadding: const EdgeInsets.fromLTRB(14, 0, 14, 14),
          leading: CircleAvatar(
            radius: 14,
            backgroundColor: limaSuave,
            child: Text(n,
                style: const TextStyle(
                    color: lima, fontWeight: FontWeight.w800, fontSize: 13)),
          ),
          title: Text(titulo,
              style: const TextStyle(
                  fontWeight: FontWeight.w700, fontSize: 14)),
          children: [
            Align(
              alignment: Alignment.centerLeft,
              child: Text(detalle,
                  style: const TextStyle(color: textoTenue, fontSize: 13, height: 1.35)),
            ),
          ],
        ),
      ),
    );
  }

  Widget _cuentaFila(IconData icono, String red, String valor) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        children: [
          Icon(icono, color: Colors.white70, size: 18),
          const SizedBox(width: 8),
          Text('$red: ',
              style: const TextStyle(color: Colors.white70, fontSize: 13)),
          Expanded(
            child: Text(valor,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(
                    color: Colors.white,
                    fontSize: 14,
                    fontWeight: FontWeight.w700)),
          ),
        ],
      ),
    );
  }

  Widget _avisoSandbox() {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: const Color(0xFFFBEAD2),
        borderRadius: BorderRadius.circular(12),
      ),
      child: const Text(
          '🧪 Modo prueba: el flujo funciona pero aún no se publica en redes '
          'reales (falta la aprobación de Meta). Se activará solo cuando esté '
          'lista, sin que hagas nada.',
          style: TextStyle(fontSize: 12.5, color: clayOscuro)),
    );
  }

  Widget _piePrivacidad() {
    return Row(
      children: [
        const Icon(Icons.lock_outline, size: 15, color: textoTenue),
        const SizedBox(width: 6),
        const Expanded(
          child: Text(
              'Solo publicamos lo que apruebas. No guardamos tu contraseña.',
              style: TextStyle(color: textoTenue, fontSize: 12)),
        ),
        if (_baseUrl.isNotEmpty)
          TextButton(
            onPressed: () => _abrir('$_baseUrl/legal/privacidad'),
            style: TextButton.styleFrom(
                padding: const EdgeInsets.symmetric(horizontal: 8),
                minimumSize: const Size(0, 0),
                tapTargetSize: MaterialTapTargetSize.shrinkWrap),
            child: const Text('Privacidad', style: TextStyle(color: lima)),
          ),
      ],
    );
  }
}
