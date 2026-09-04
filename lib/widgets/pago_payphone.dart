import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:webview_flutter/webview_flutter.dart';

import '../config/features.dart';
import '../screens/pago_sheet.dart';
import '../services/pagos_service.dart';
import '../state/app_state.dart';
import '../theme.dart';
import 'cargando_pichangol.dart';
import 'dialogo_pichangol.dart';

/// Cobro con PAYPHONE (Ecuador). Modelo "botón de pagos por redirección": el
/// backend PREPARA la transacción y devuelve una URL hospedada; aquí la abrimos
/// en un WebView para que el cliente pague (tarjeta Visa/Mastercard/Diners/
/// Discover o saldo PayPhone). Al terminar, PayPhone vuelve a la URL de retorno
/// del backend con `?id=<tx>&clientTransactionId=<ident>`.
///
/// REGLA DE ORO de PayPhone: el cobro hay que CONFIRMARLO antes de 5 minutos o
/// se revierte solo. Por eso (1) dejamos que la URL de retorno LLEGUE al
/// backend (que confirma al instante) y (2) además le pasamos al backend el
/// `id` que vimos en esa URL al consultar el estado — si el retorno no llegó
/// por cualquier motivo, se confirma igual. Doble vía, idempotente.
///
/// Devuelve true si el pago se confirmó. Sin PayPhone configurada: en dev/QAS
/// cae a la pasarela SIMULADA; en producción avisa y devuelve false (nunca se
/// inventa un pago).
class PagoPayPhone {
  // Anti doble-click: mientras hay un cobro en curso, los taps extra se ignoran
  // (evita preparar varias transacciones y abrir varias pasarelas).
  static bool _enCurso = false;

  static Future<bool> cobrar(
    BuildContext context, {
    required num monto, // unidad mayor (USD), admite 2 decimales
    required String concepto,
    required String email,
    String moneda = '\$',
    String tipo = '',
    String ref = '',
    String duenoId = '',
  }) async {
    if (_enCurso) return false;
    _enCurso = true; // síncrono: bloquea incluso el doble-tap de 1 frame
    try {
      return await _flujo(context,
          monto: monto, concepto: concepto, email: email, moneda: moneda,
          tipo: tipo, ref: ref, duenoId: duenoId);
    } finally {
      _enCurso = false;
    }
  }

  static Future<bool> _flujo(
    BuildContext context, {
    required num monto,
    required String concepto,
    required String email,
    required String moneda,
    required String tipo,
    required String ref,
    required String duenoId,
  }) async {
    final correo = (appState.usuario?.email ?? email).trim();
    final nombre = appState.usuario?.nombre ?? '';
    // 1) Preparar el pago en el backend (que llama a PayPhone). Preload de
    //    marca mientras tanto (preparar puede demorar un par de segundos).
    final nav = Navigator.of(context, rootNavigator: true);
    showDialog<void>(
      context: context,
      barrierDismissible: false,
      useRootNavigator: true,
      builder: (_) => const PopScope(
        canPop: false,
        child: Dialog(
          backgroundColor: Colors.transparent,
          elevation: 0,
          child: Padding(
            padding: EdgeInsets.symmetric(vertical: 28),
            child: CargandoPichangol(texto: 'Preparando tu pago…'),
          ),
        ),
      ),
    );
    Map<String, dynamic>? r;
    try {
      r = await PagosService.crearPagoEc(
        email: correo,
        montoUsd: monto.toDouble(),
        concepto: concepto,
        nombre: nombre,
        tipo: tipo,
        ref: ref,
        duenoId: duenoId,
      );
    } finally {
      if (nav.canPop()) nav.pop(); // cierra el preload
    }
    if (!context.mounted) return false;

    // Sin pasarela configurada: en producción NO se simula nunca (sería
    // acreditar plata inexistente); en dev/QAS sí, para recorrer el flujo.
    if (r == null || r['error'] == 'no_configurado') {
      if (kEsProduccion) {
        await avisarPichangol(
          context,
          titulo: 'Pago en la app no disponible',
          mensaje: 'Todavía no tenemos habilitado el cobro dentro de '
              'Pichangol en Ecuador, así que no se te cobró nada. Coordina '
              'el pago directamente con el local o el vendedor.',
          icono: Icons.credit_card_off_outlined,
        );
        return false;
      }
      final sim = await PagoSheet.mostrar(context,
          monto: monto, concepto: concepto, moneda: moneda);
      return sim != null && sim.exito;
    }
    if (r['ok'] != true) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          backgroundColor: const Color(0xFFC0392B),
          content:
              Text('No se pudo iniciar el pago. ${r['error'] ?? ''}'.trim())));
      return false;
    }

    // Se abre la página PUENTE del backend (nuestro dominio), que navega a la
    // pasarela: PayPhone rechaza su página si el navegador llega sin un
    // origen autorizado ("No autorizado… intenta desde la página de origen").
    final url = (r['url_lanzador'] ?? r['url_pasarela'] ?? '').toString();
    final ident = (r['identificador'] ?? '').toString();
    if (url.isEmpty || ident.isEmpty) return false;

    // 2) Abrir la pasarela de PayPhone en un WebView. Devuelve el `id` de la
    //    transacción que PayPhone puso en la URL de retorno ('' si el usuario
    //    cerró sin terminar).
    final txId = await Navigator.of(context).push<String>(MaterialPageRoute(
      fullscreenDialog: true,
      builder: (_) => _PayPhoneWebView(url: url, concepto: concepto),
    ));
    if (!context.mounted) return false;

    // 3) Confirmar contra el backend, mandando el transaction_id si lo vimos:
    //    el backend CONFIRMA con PayPhone (antes de los 5 minutos) y responde
    //    pagado. Si no hubo retorno, igual se sondea unas veces por si acaso.
    final tx = txId ?? '';
    return _confirmar(context, ident, tx, intentos: tx.isNotEmpty ? 8 : 3);
  }

  /// Sondea el estado del pago mostrando "Confirmando pago…".
  static Future<bool> _confirmar(
      BuildContext context, String ident, String transactionId,
      {int intentos = 6}) async {
    final res = await showDialog<bool>(
      context: context,
      barrierDismissible: false,
      builder: (_) => _ConfirmandoPago(
          identificador: ident, transactionId: transactionId, intentos: intentos),
    );
    return res == true;
  }
}

/// Pantalla WebView con la pasarela hospedada de PayPhone.
class _PayPhoneWebView extends StatefulWidget {
  const _PayPhoneWebView({required this.url, required this.concepto});
  final String url;
  final String concepto;

  @override
  State<_PayPhoneWebView> createState() => _PayPhoneWebViewState();
}

class _PayPhoneWebViewState extends State<_PayPhoneWebView> {
  late final WebViewController _controller;
  bool _cargando = true;
  bool _cerrado = false;

  /// Saca el `id` (transactionId de PayPhone) de la URL de retorno.
  static String _txDe(String url) {
    try {
      return Uri.parse(url).queryParameters['id'] ?? '';
    } catch (_) {
      return '';
    }
  }

  void _cerrar(String tx) {
    if (_cerrado || !mounted) return;
    _cerrado = true;
    Navigator.of(context).pop(tx);
  }

  @override
  void initState() {
    super.initState();
    _controller = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..setNavigationDelegate(NavigationDelegate(
        onPageStarted: (_) {
          if (mounted) setState(() => _cargando = true);
        },
        onPageFinished: (url) {
          if (mounted) setState(() => _cargando = false);
          // La página de retorno del backend ya cargó: el backend acaba de
          // CONFIRMAR con PayPhone. Cerramos llevándonos el id por si acaso.
          if (url.contains('/pagos/ec/retorno')) _cerrar(_txDe(url));
          if (url.contains('/pagos/ec/cancelado')) _cerrar('');
        },
        onNavigationRequest: (req) {
          // OJO: al retorno se le deja LLEGAR al backend (NavigationDecision.
          // navigate), porque es ahí donde se confirma el cobro dentro de los
          // 5 minutos. No se intercepta como en Libélula.
          return NavigationDecision.navigate;
        },
      ))
      ..loadRequest(Uri.parse(widget.url));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        backgroundColor: bosque,
        foregroundColor: Colors.white,
        title: const Text('Pago seguro · PayPhone',
            style: TextStyle(fontWeight: FontWeight.w700, fontSize: 16)),
        leading: IconButton(
          icon: const Icon(Icons.close),
          tooltip: 'Cancelar',
          onPressed: () => _cerrar(''),
        ),
        actions: [
          // Salida de emergencia: si la pasarela no carga dentro del WebView
          // (cookies, políticas del sitio), la misma página puente se abre en
          // el navegador del teléfono. El retorno igual llega al backend y la
          // app confirma al volver.
          IconButton(
            icon: const Icon(Icons.open_in_browser),
            tooltip: 'Abrir en el navegador',
            onPressed: () => launchUrl(Uri.parse(widget.url),
                mode: LaunchMode.externalApplication),
          ),
        ],
      ),
      body: Stack(
        children: [
          WebViewWidget(controller: _controller),
          if (_cargando)
            const Center(child: CircularProgressIndicator(color: lima)),
        ],
      ),
    );
  }
}

/// Diálogo que sondea el backend hasta confirmar el pago (o agotar intentos).
class _ConfirmandoPago extends StatefulWidget {
  const _ConfirmandoPago({
    required this.identificador,
    required this.transactionId,
    required this.intentos,
  });
  final String identificador;
  final String transactionId;
  final int intentos;

  @override
  State<_ConfirmandoPago> createState() => _ConfirmandoPagoState();
}

class _ConfirmandoPagoState extends State<_ConfirmandoPago> {
  @override
  void initState() {
    super.initState();
    _sondear();
  }

  Future<void> _sondear() async {
    for (var i = 0; i < widget.intentos; i++) {
      final e = await PagosService.estadoPagoEc(widget.identificador,
          transactionId: widget.transactionId);
      if (!mounted) return;
      if (e != null && e['pagado'] == true) {
        Navigator.of(context).pop(true);
        return;
      }
      // Rechazado/cancelado en firme: no tiene sentido seguir sondeando.
      final est = (e?['estado'] ?? '').toString().toLowerCase();
      if (est == 'cancelado' || est == 'canceled' || est == 'rejected') break;
      await Future.delayed(const Duration(seconds: 2));
    }
    if (mounted) Navigator.of(context).pop(false);
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      content: Column(
        mainAxisSize: MainAxisSize.min,
        children: const [
          SizedBox(height: 6),
          CircularProgressIndicator(color: lima),
          SizedBox(height: 18),
          Text('Confirmando tu pago…',
              style: TextStyle(fontWeight: FontWeight.w700)),
          SizedBox(height: 6),
          Text('No cierres esta ventana.',
              style: TextStyle(color: textoTenue, fontSize: 12.5)),
        ],
      ),
    );
  }
}
