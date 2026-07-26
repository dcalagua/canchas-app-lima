import 'package:flutter/material.dart';
import 'package:webview_flutter/webview_flutter.dart';

import '../screens/pago_sheet.dart';
import '../services/pagos_service.dart';
import '../state/app_state.dart';
import '../theme.dart';

/// Cobro con LIBÉLULA (Bolivia). Modelo "deuda + pasarela hospedada": el backend
/// registra la deuda y devuelve una URL; aquí abrimos esa URL en un WebView para
/// que el cliente pague (QR interoperable · tarjeta · Tigo Money). Al volver a la
/// URL de retorno (o al cerrar), confirmamos con el backend si la deuda se pagó.
///
/// Devuelve true si el pago se confirmó. Si Libélula no está configurada en el
/// backend, cae a la pasarela SIMULADA (para no romper la demo/pruebas).
class PagoLibelula {
  static Future<bool> cobrar(
    BuildContext context, {
    required int monto,
    required String concepto,
    required String email,
    String moneda = 'Bs',
    String tipo = '',
    String ref = '',
    String duenoId = '',
  }) async {
    final correo = (appState.usuario?.email ?? email).trim();
    final nombre = appState.usuario?.nombre ?? '';
    // 1) Registrar la deuda en el backend (que llama a Libélula). El [tipo]
    //    'recarga' + [duenoId] hace que el backend acredite el saldo al pagarse.
    final r = await PagosService.crearDeudaBo(
      email: correo,
      montoBs: monto.toDouble(),
      concepto: concepto,
      nombre: nombre,
      tipo: tipo,
      ref: ref,
      duenoId: duenoId,
    );
    if (!context.mounted) return false;

    // Sin pasarela configurada → demo simulada (igual que Culqi).
    if (r == null || r['error'] == 'no_configurado') {
      final sim = await PagoSheet.mostrar(context,
          monto: monto, concepto: concepto, moneda: moneda);
      return sim != null && sim.exito;
    }
    if (r['ok'] != true) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          backgroundColor: const Color(0xFFC0392B),
          content: Text('No se pudo iniciar el pago. ${r['error'] ?? ''}'.trim())));
      return false;
    }

    final url = (r['url_pasarela'] ?? '').toString();
    final ident = (r['identificador'] ?? '').toString();
    if (url.isEmpty || ident.isEmpty) return false;

    // 2) Abrir la pasarela de Libélula en un WebView; se cierra al llegar a la
    //    URL de retorno del backend (/pagos/bo/retorno) o si el usuario sale.
    final volvio = await Navigator.of(context).push<bool>(MaterialPageRoute(
      fullscreenDialog: true,
      builder: (_) => _LibelulaWebView(url: url, concepto: concepto),
    ));
    if (!context.mounted) return false;

    // 3) Confirmar contra el backend (el callback marca pagado; si no llegó, el
    //    backend reconcilia consultando a Libélula). Da unos segundos.
    return _confirmar(context, ident, intentos: volvio == true ? 8 : 3);
  }

  /// Sondea el estado de la deuda mostrando "Confirmando pago…".
  static Future<bool> _confirmar(BuildContext context, String ident,
      {int intentos = 6}) async {
    final res = await showDialog<bool>(
      context: context,
      barrierDismissible: false,
      builder: (_) => _ConfirmandoPago(identificador: ident, intentos: intentos),
    );
    return res == true;
  }
}

/// Pantalla WebView con la pasarela de Libélula.
class _LibelulaWebView extends StatefulWidget {
  const _LibelulaWebView({required this.url, required this.concepto});
  final String url;
  final String concepto;

  @override
  State<_LibelulaWebView> createState() => _LibelulaWebViewState();
}

class _LibelulaWebViewState extends State<_LibelulaWebView> {
  late final WebViewController _controller;
  bool _cargando = true;

  @override
  void initState() {
    super.initState();
    _controller = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..setNavigationDelegate(NavigationDelegate(
        onPageStarted: (_) {
          if (mounted) setState(() => _cargando = true);
        },
        onPageFinished: (_) {
          if (mounted) setState(() => _cargando = false);
        },
        onNavigationRequest: (req) {
          // Al volver a nuestra URL de retorno, el pago se hizo: cerramos OK.
          if (req.url.contains('/pagos/bo/retorno')) {
            Navigator.of(context).pop(true);
            return NavigationDecision.prevent;
          }
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
        title: const Text('Pago seguro · Libélula',
            style: TextStyle(fontWeight: FontWeight.w700, fontSize: 16)),
        leading: IconButton(
          icon: const Icon(Icons.close),
          tooltip: 'Cancelar',
          onPressed: () => Navigator.of(context).pop(false),
        ),
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
  const _ConfirmandoPago({required this.identificador, required this.intentos});
  final String identificador;
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
      final e = await PagosService.estadoDeudaBo(widget.identificador);
      if (!mounted) return;
      if (e != null && e['pagado'] == true) {
        Navigator.of(context).pop(true);
        return;
      }
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
