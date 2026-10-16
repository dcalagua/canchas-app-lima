import 'dart:async';
import 'dart:io';

import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';
import 'package:share_plus/share_plus.dart';

import '../models/academia.dart';
import '../screens/chat_screen.dart';
import '../screens/login_google_sheet.dart';
import '../services/academia_plan_service.dart';
import '../services/whatsapp_link.dart';
import '../state/app_state.dart';
import '../theme.dart';
import 'dialogo_pichangol.dart';
import 'icono_vivo.dart';
import 'logo_academia.dart';
import 'marcas_pago.dart';

const _yapeMorado = Color(0xFF742284);

/// Abre el CHAT INTERNO con la academia (exige cuenta). Lo usan la ficha de la
/// academia y "Mis clases" cuando el pago se coordina directo con el profe.
Future<void> abrirChatAcademia(BuildContext context, Academia academia) async {
  if (!await LoginGoogleSheet.mostrar(context, motivo: 'escribirle al profe')) {
    return;
  }
  if (!context.mounted) return;
  final email = appState.usuario!.email;
  Navigator.of(context).push(MaterialPageRoute(
    builder: (_) => ChatScreen(
      academiaId: academia.id,
      cuentaEmail: email,
      titulo: academia.nombre,
      soyProfe: false,
    ),
  ));
}

/// Aviso "Coordina el pago con la academia" (la academia no registró su Yape
/// o está fuera de Perú): chat interno y, si hay, WhatsApp.
Future<void> avisarCoordinarPago(BuildContext context, Academia academia,
    {String? mensaje, String titulo = 'Coordina el pago con la academia'}) async {
  await showDialog<void>(
    context: context,
    builder: (ctx) => DialogoPichangol(
      titulo: titulo,
      icono: Icons.forum_outlined,
      mensaje: mensaje ??
          '${academia.nombre} recibe sus pagos directamente. Escríbele para '
              'saber cómo pagarle.',
      acciones: [
        if (academia.whatsapp.isNotEmpty)
          TextButton.icon(
            onPressed: () {
              Navigator.of(ctx).pop();
              WhatsAppLink.abrir(academia.whatsapp,
                  'Hola, quiero coordinar el pago de mis clases en ${academia.nombre} (vi tu academia en Pichangol).');
            },
            icon: const Icon(Icons.chat_outlined, color: lima),
            label: const Text('WhatsApp'),
          ),
        FilledButton.icon(
          style: FilledButton.styleFrom(
              backgroundColor: lima,
              foregroundColor: Colors.white,
              shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(12)),
              padding:
                  const EdgeInsets.symmetric(horizontal: 18, vertical: 12)),
          onPressed: () {
            Navigator.of(ctx).pop();
            abrirChatAcademia(context, academia);
          },
          icon: const Icon(Icons.forum_outlined, size: 18),
          label: const Text('Escribir a la academia',
              style: TextStyle(fontWeight: FontWeight.w800)),
        ),
      ],
    ),
  );
}

/// PAGO DIRECTO A LA ACADEMIA (Plan Academia, decisión del director
/// 10-oct-2026): el alumno yapea al Yape de la academia y reporta en Pichangol
/// el CÓDIGO DE SEGURIDAD de 3 dígitos que muestra su comprobante (y, si
/// quiere, el N.º de operación). La academia lo compara con su Yape y
/// confirma. Pichangol no toca la plata.
class PagoDirectoSheet {
  /// Abre la hoja para [cuotas] (todas de la MISMA academia y alumno).
  /// Devuelve true si el pago quedó reportado.
  static Future<bool> mostrar(
    BuildContext context, {
    required Academia academia,
    required Alumno alumno,
    required List<Cuota> cuotas,
  }) async {
    final lista = cuotas.where((c) => !c.pagada).toList();
    if (lista.isEmpty) return false;
    var cd = academia.cobroDirecto;
    if (cd == null) {
      // Puede que la academia lo haya registrado desde la web y este teléfono
      // aún no lo baje: se pregunta al backend.
      final est = await AcademiaPlanService.plan(academia.id);
      cd = est?.cobroDirecto;
    }
    if (!context.mounted) return false;
    if (cd == null) {
      await avisarCoordinarPago(context, academia);
      return false;
    }
    final CobroDirecto cobro = cd;
    if (cobro.esQr) {
      // Ecuador / Bolivia: QR de la academia con MONTO ÚNICO; se confirma solo.
      final okQr = await showModalBottomSheet<bool>(
        context: context,
        isScrollControlled: true,
        backgroundColor: Theme.of(context).colorScheme.surface,
        shape: const RoundedRectangleBorder(
            borderRadius: BorderRadius.vertical(top: Radius.circular(24))),
        builder: (_) => _HojaPagoQr(
            academia: academia, alumno: alumno, cuotas: lista, cobro: cobro),
      );
      if (okQr == true && context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
            content: Text('¡Pago recibido! Tu cuota quedó pagada.')));
      }
      appState.cargarMatriculasRemotas();
      return okQr == true;
    }
    final ok = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Theme.of(context).colorScheme.surface,
      shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(24))),
      builder: (_) => _HojaPagoDirecto(
          academia: academia, alumno: alumno, cuotas: lista, cobro: cobro),
    );
    if (ok == true && context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text(
              '¡Listo! La academia confirmará tu pago en cuanto lo vea en su Yape.')));
    }
    return ok == true;
  }
}

class _HojaPagoDirecto extends StatefulWidget {
  const _HojaPagoDirecto({
    required this.academia,
    required this.alumno,
    required this.cuotas,
    required this.cobro,
  });
  final Academia academia;
  final Alumno alumno;
  final List<Cuota> cuotas;
  final CobroDirecto cobro;

  @override
  State<_HojaPagoDirecto> createState() => _HojaPagoDirectoState();
}

class _HojaPagoDirectoState extends State<_HojaPagoDirecto> {
  final _codigo = TextEditingController();
  final _operacion = TextEditingController();
  String? _error;
  bool _enviando = false;

  double get _total =>
      widget.cuotas.fold<double>(0, (s, c) => s + c.monto);
  String get _mon => widget.academia.monedaSimbolo;

  @override
  void dispose() {
    _codigo.dispose();
    _operacion.dispose();
    super.dispose();
  }

  Future<void> _copiar() async {
    await Clipboard.setData(ClipboardData(text: widget.cobro.yape));
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
        content: Text('Número de Yape copiado.')));
  }

  Future<void> _enviar() async {
    final cod = _codigo.text.replaceAll(RegExp(r'[^0-9]'), '');
    if (cod.length != 3) {
      setState(() => _error =
          'Escribe los 3 dígitos del código de seguridad que sale en tu Yape.');
      return;
    }
    final op = _operacion.text.replaceAll(RegExp(r'[^0-9]'), '');
    final email = appState.usuario?.email ?? '';
    if (email.isEmpty) {
      setState(() => _error = 'Inicia sesión para avisar tu pago.');
      return;
    }
    setState(() {
      _error = null;
      _enviando = true;
    });
    final ids = widget.cuotas.map((c) => c.id).toList();
    final r = await AcademiaPlanService.reportar(
      alumnoId: widget.alumno.id,
      email: email,
      cuotaIds: ids,
      codigo: cod,
      operacion: op,
    );
    if (!mounted) return;
    if (r['ok'] == true) {
      final hechas = (r['cuotas'] is List)
          ? (r['cuotas'] as List).map((e) => e.toString()).toList()
          : ids;
      appState.marcarCuotasReportadas(hechas, codigo: cod, operacion: op);
      // Trae el estado real de la nube en segundo plano.
      appState.cargarMatriculasRemotas();
      Navigator.of(context).pop(true);
      return;
    }
    setState(() {
      _enviando = false;
      _error = (r['mensaje'] ?? 'No se pudo avisar tu pago. Reintenta.')
          .toString();
    });
  }

  Widget _paso(String n, String texto) => Padding(
        padding: const EdgeInsets.only(bottom: 8),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Container(
              width: 22,
              height: 22,
              alignment: Alignment.center,
              decoration: const BoxDecoration(
                  color: limaSuave, shape: BoxShape.circle),
              child: Text(n,
                  style: const TextStyle(
                      color: bosque,
                      fontWeight: FontWeight.w800,
                      fontSize: 12)),
            ),
            const SizedBox(width: 10),
            Expanded(
                child: Text(texto,
                    style: const TextStyle(fontSize: 13.5, height: 1.3))),
          ],
        ),
      );

  @override
  Widget build(BuildContext context) {
    final cd = widget.cobro;
    return Padding(
      padding: EdgeInsets.fromLTRB(
          20, 18, 20, 20 + MediaQuery.of(context).viewInsets.bottom),
      child: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Center(
              child: Container(
                width: 40,
                height: 4,
                decoration: BoxDecoration(
                    color: trazo, borderRadius: BorderRadius.circular(999)),
              ),
            ),
            const SizedBox(height: 14),
            Row(
              children: [
                LogoAcademia(logoUrl: widget.academia.logoUrl, size: 40),
                const SizedBox(width: 10),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text('Paga a la academia',
                          style: TextStyle(
                              fontWeight: FontWeight.w800, fontSize: 18)),
                      Text(widget.academia.nombre,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                              color: textoTenue, fontSize: 13)),
                    ],
                  ),
                ),
              ],
            ),
            const SizedBox(height: 14),
            // Monto y detalle.
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                  color: limaSuave, borderRadius: BorderRadius.circular(14)),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  for (final c in widget.cuotas)
                    Padding(
                      padding: const EdgeInsets.only(bottom: 4),
                      child: Row(
                        children: [
                          Expanded(
                            child: Text(c.concepto,
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: const TextStyle(
                                    fontSize: 13, color: bosque)),
                          ),
                          Text('$_mon ${c.monto.toStringAsFixed(2)}',
                              style: const TextStyle(
                                  fontSize: 13, color: bosque)),
                        ],
                      ),
                    ),
                  const Divider(height: 14),
                  Row(
                    children: [
                      const Expanded(
                        child: Text('Yapea exactamente',
                            style: TextStyle(
                                fontWeight: FontWeight.w700, color: bosque)),
                      ),
                      Text('$_mon ${_total.toStringAsFixed(2)}',
                          style: const TextStyle(
                              fontWeight: FontWeight.w900,
                              fontSize: 20,
                              color: bosque)),
                    ],
                  ),
                ],
              ),
            ),
            const SizedBox(height: 12),
            // Yape de la academia.
            Container(
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                color: Theme.of(context).colorScheme.surface,
                borderRadius: BorderRadius.circular(14),
                border: Border.all(color: trazo),
                boxShadow: const [
                  BoxShadow(
                      color: Color(0x0F000000),
                      blurRadius: 10,
                      offset: Offset(0, 3)),
                ],
              ),
              child: Row(
                children: [
                  const YapeBadge(alto: 34),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(cd.yapeBonito,
                            style: const TextStyle(
                                fontWeight: FontWeight.w900,
                                fontSize: 19,
                                letterSpacing: 0.5)),
                        if (cd.titular.isNotEmpty)
                          Text('A nombre de ${cd.titular}',
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: const TextStyle(
                                  color: textoTenue, fontSize: 12.5)),
                      ],
                    ),
                  ),
                  TextButton.icon(
                    onPressed: _copiar,
                    icon: const Icon(Icons.copy_rounded, size: 18),
                    label: const Text('Copiar'),
                    style: TextButton.styleFrom(foregroundColor: _yapeMorado),
                  ),
                ],
              ),
            ),
            if (cd.tieneQr) ...[
              const SizedBox(height: 12),
              Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(14),
                  border: Border.all(color: trazo),
                ),
                child: Row(
                  children: [
                    ClipRRect(
                      borderRadius: BorderRadius.circular(10),
                      child: CachedNetworkImage(
                        imageUrl: cd.qrUrl,
                        width: 120,
                        height: 120,
                        fit: BoxFit.contain,
                        errorWidget: (_, __, ___) => const SizedBox(
                            width: 120,
                            height: 120,
                            child: Icon(Icons.qr_code_2, size: 48)),
                      ),
                    ),
                    const SizedBox(width: 12),
                    const Expanded(
                      child: Text(
                          'O escanea su QR de Yape desde otro celular, o '
                          'haz captura y en Yape elige «Escanear» → galería.',
                          style: TextStyle(fontSize: 12.5, height: 1.3)),
                    ),
                  ],
                ),
              ),
            ],
            const SizedBox(height: 16),
            const Text('Cómo pagar',
                style: TextStyle(fontWeight: FontWeight.w800, fontSize: 15)),
            const SizedBox(height: 8),
            _paso('1',
                'Abre tu Yape y yapea $_mon ${_total.toStringAsFixed(2)} al ${cd.yapeBonito}.'),
            _paso('2',
                'En el comprobante de Yape busca el «Código de seguridad»: son 3 dígitos.'),
            _paso('3',
                'Escríbelos aquí. La academia los compara con su Yape y confirma tu pago.'),
            const SizedBox(height: 6),
            const Center(child: ComprobanteYapeMini()),
            const SizedBox(height: 16),
            TextField(
              controller: _codigo,
              keyboardType: TextInputType.number,
              maxLength: 3,
              autofocus: false,
              textAlign: TextAlign.center,
              inputFormatters: [FilteringTextInputFormatter.digitsOnly],
              style: const TextStyle(
                  fontSize: 26,
                  fontWeight: FontWeight.w900,
                  letterSpacing: 14),
              decoration: const InputDecoration(
                labelText: 'Código de seguridad (3 dígitos)',
                counterText: '',
                hintText: '•••',
              ),
              onChanged: (_) {
                if (_error != null) setState(() => _error = null);
              },
            ),
            const SizedBox(height: 10),
            TextField(
              controller: _operacion,
              keyboardType: TextInputType.number,
              maxLength: 12,
              inputFormatters: [FilteringTextInputFormatter.digitsOnly],
              decoration: const InputDecoration(
                labelText: 'N.º de operación (opcional)',
                helperText: 'También sale en tu comprobante de Yape.',
                counterText: '',
                prefixIcon: IconoVivo(Icons.receipt_long),
              ),
            ),
            if (_error != null) ...[
              const SizedBox(height: 10),
              Row(
                children: [
                  const IconoVivo(Icons.error_outline,
                      size: 18, color: clayOscuro),
                  const SizedBox(width: 6),
                  Expanded(
                    child: Text(_error!,
                        style: const TextStyle(
                            color: clayOscuro,
                            fontSize: 13,
                            fontWeight: FontWeight.w600)),
                  ),
                ],
              ),
            ],
            const SizedBox(height: 16),
            SizedBox(
              width: double.infinity,
              child: FilledButton(
                style: FilledButton.styleFrom(
                    backgroundColor: lima,
                    foregroundColor: Colors.white,
                    padding: const EdgeInsets.symmetric(vertical: 14)),
                onPressed: _enviando ? null : _enviar,
                child: _enviando
                    ? const SizedBox(
                        width: 20,
                        height: 20,
                        child: CircularProgressIndicator(
                            strokeWidth: 2.4, color: Colors.white))
                    : const Text('Ya yapeé · avisar a la academia',
                        style: TextStyle(fontWeight: FontWeight.w800)),
              ),
            ),
            const SizedBox(height: 8),
            const Text(
                'Le pagas directo a la academia. Pichangol solo registra tu pago '
                'y te lo recuerda; no cobra comisión.',
                style: TextStyle(color: textoTenue, fontSize: 12)),
          ],
        ),
      ),
    );
  }
}

/// Mini ilustración del comprobante de Yape con el CÓDIGO DE SEGURIDAD
/// resaltado (para que el alumno sepa qué 3 dígitos buscar).
class ComprobanteYapeMini extends StatelessWidget {
  const ComprobanteYapeMini({super.key});

  @override
  Widget build(BuildContext context) {
    Widget raya(double w) => Container(
        width: w,
        height: 7,
        margin: const EdgeInsets.only(top: 6),
        decoration: BoxDecoration(
            color: const Color(0xFFE9E0EE),
            borderRadius: BorderRadius.circular(4)));
    return Container(
      width: 230,
      padding: const EdgeInsets.fromLTRB(16, 14, 16, 14),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: const Color(0xFFE9E0EE)),
        boxShadow: const [
          BoxShadow(
              color: Color(0x14000000), blurRadius: 14, offset: Offset(0, 4)),
        ],
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: 34,
            height: 34,
            decoration: const BoxDecoration(
                color: _yapeMorado, shape: BoxShape.circle),
            child: const Icon(Icons.check, color: Colors.white, size: 20),
          ),
          const SizedBox(height: 6),
          const Text('¡Yapeaste!',
              style: TextStyle(
                  color: _yapeMorado,
                  fontWeight: FontWeight.w900,
                  fontSize: 15)),
          raya(110),
          raya(80),
          const SizedBox(height: 10),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
            decoration: BoxDecoration(
              color: limaSuave,
              borderRadius: BorderRadius.circular(10),
              border: Border.all(color: lima, width: 2),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Text('Código de seguridad',
                    style: TextStyle(
                        fontSize: 11.5,
                        fontWeight: FontWeight.w700,
                        color: bosque)),
                const SizedBox(width: 8),
                for (final d in const ['4', '7', '2'])
                  Container(
                    width: 20,
                    height: 24,
                    margin: const EdgeInsets.only(left: 3),
                    alignment: Alignment.center,
                    decoration: BoxDecoration(
                        color: Colors.white,
                        borderRadius: BorderRadius.circular(5),
                        border: Border.all(color: lima)),
                    child: Text(d,
                        style: const TextStyle(
                            fontWeight: FontWeight.w900,
                            fontSize: 13,
                            color: bosque)),
                  ),
              ],
            ),
          ),
          const SizedBox(height: 4),
          const Text('↑ Estos 3 dígitos',
              style: TextStyle(
                  color: lima, fontWeight: FontWeight.w800, fontSize: 12)),
          raya(120),
        ],
      ),
    );
  }
}


/// PAGO POR QR (Ecuador / Bolivia): el alumno recibe un MONTO ÚNICO (su cuota
/// + unos centavos de identificación), escanea el QR de la academia y paga.
/// El celular de la academia lee la notificación de su app de cobros y la
/// cuota queda pagada sola; mientras tanto la hoja sondea el estado.
class _HojaPagoQr extends StatefulWidget {
  const _HojaPagoQr({
    required this.academia,
    required this.alumno,
    required this.cuotas,
    required this.cobro,
  });
  final Academia academia;
  final Alumno alumno;
  final List<Cuota> cuotas;
  final CobroDirecto cobro;

  @override
  State<_HojaPagoQr> createState() => _HojaPagoQrState();
}

class _HojaPagoQrState extends State<_HojaPagoQr> {
  PagoQr? _pago;
  String? _error;
  bool _cargando = true;
  bool _avisando = false;
  bool _compartiendo = false;
  Timer? _sondeo;

  String get _email => appState.usuario?.email ?? '';

  @override
  void initState() {
    super.initState();
    _iniciar();
  }

  @override
  void dispose() {
    _sondeo?.cancel();
    super.dispose();
  }

  Future<void> _iniciar() async {
    if (_email.isEmpty) {
      setState(() {
        _cargando = false;
        _error = 'Inicia sesión para pagar.';
      });
      return;
    }
    setState(() {
      _cargando = true;
      _error = null;
    });
    final (p, err) = await AcademiaPlanService.iniciarQr(
        alumnoId: widget.alumno.id,
        email: _email,
        cuotaIds: widget.cuotas.map((c) => c.id).toList());
    if (!mounted) return;
    setState(() {
      _cargando = false;
      _pago = p;
      _error = err;
    });
    if (p != null) _vigilar();
  }

  void _vigilar() {
    _sondeo?.cancel();
    _sondeo = Timer.periodic(const Duration(seconds: 5), (_) async {
      final p = _pago;
      if (p == null || !mounted) return;
      final n = await AcademiaPlanService.estadoQr(p.id, _email);
      if (!mounted || n == null) return;
      if (n.confirmado) {
        _sondeo?.cancel();
        Navigator.of(context).pop(true);
        return;
      }
      if (!n.vivo) {
        _sondeo?.cancel();
        setState(() {
          _pago = null;
          _error = n.estado == 'rechazado'
              ? 'La academia no encontró tu pago. Revisa el monto o escríbele.'
              : 'Este QR ya no está vigente. Genera un monto nuevo.';
        });
        return;
      }
      if (n.estado != p.estado) setState(() => _pago = n);
    });
  }

  Future<void> _yaPague() async {
    final p = _pago;
    if (p == null || _avisando) return;
    final ok = await confirmarPichangol(context,
        titulo: '¿Ya pagaste?',
        mensaje: 'Le avisamos a ${widget.academia.nombre}. Si su celular está '
            'vinculado, tu pago se confirma solo apenas llegue; si no, la '
            'academia lo revisa.',
        textoConfirmar: 'Sí, ya pagué',
        icono: Icons.check_circle_outline);
    if (!ok || !mounted) return;
    setState(() => _avisando = true);
    final (n, err) = await AcademiaPlanService.marcarPagadoQr(p.id, _email);
    if (!mounted) return;
    setState(() => _avisando = false);
    if (n == null) {
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(err ?? 'No se pudo avisar.')));
      return;
    }
    if (n.confirmado) {
      Navigator.of(context).pop(true);
      return;
    }
    setState(() => _pago = n);
  }

  Future<void> _copiarMonto() async {
    final p = _pago;
    if (p == null) return;
    await Clipboard.setData(ClipboardData(text: p.monto.toStringAsFixed(2)));
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Monto copiado: ${p.montoTxt}')));
  }

  /// Guarda/comparte la imagen del QR para abrirla desde la app del banco
  /// (no se puede escanear la pantalla del mismo celular).
  Future<void> _compartirQr() async {
    final p = _pago;
    if (p == null || _compartiendo) return;
    setState(() => _compartiendo = true);
    try {
      final resp = await http.get(Uri.parse(p.qrUrl)).timeout(const Duration(seconds: 15));
      if (resp.statusCode == 200) {
        final dir = await getTemporaryDirectory();
        final ruta = '${dir.path}/qr_${widget.academia.id}.jpg';
        await File(ruta).writeAsBytes(resp.bodyBytes);
        await Share.shareXFiles([XFile(ruta, mimeType: 'image/jpeg')],
            text: 'QR de ${widget.academia.nombre} · paga exactamente ${p.montoTxt}');
      } else if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('No se pudo descargar el QR.')));
      }
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('No se pudo compartir el QR.')));
      }
    }
    if (mounted) setState(() => _compartiendo = false);
  }

  Widget _paso(String n, String texto) => Padding(
        padding: const EdgeInsets.only(bottom: 8),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Container(
              width: 22,
              height: 22,
              alignment: Alignment.center,
              decoration:
                  const BoxDecoration(color: limaSuave, shape: BoxShape.circle),
              child: Text(n,
                  style: const TextStyle(
                      color: bosque, fontWeight: FontWeight.w800, fontSize: 12)),
            ),
            const SizedBox(width: 10),
            Expanded(
                child: Text(texto,
                    style: const TextStyle(fontSize: 13.5, height: 1.3))),
          ],
        ),
      );

  @override
  Widget build(BuildContext context) {
    final p = _pago;
    final mon = widget.academia.monedaSimbolo;
    final base = widget.cuotas.fold<double>(0, (s, c) => s + c.monto);
    return Padding(
      padding: EdgeInsets.fromLTRB(
          20, 18, 20, 20 + MediaQuery.of(context).viewInsets.bottom),
      child: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Center(
              child: Container(
                width: 40,
                height: 4,
                decoration: BoxDecoration(
                    color: trazo, borderRadius: BorderRadius.circular(999)),
              ),
            ),
            const SizedBox(height: 14),
            Row(
              children: [
                LogoAcademia(logoUrl: widget.academia.logoUrl, size: 40),
                const SizedBox(width: 10),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text('Paga con QR',
                          style: TextStyle(
                              fontWeight: FontWeight.w800, fontSize: 18)),
                      Text(
                          '${widget.academia.nombre} · ${widget.cobro.appVisible}',
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style:
                              const TextStyle(color: textoTenue, fontSize: 13)),
                    ],
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            for (final c in widget.cuotas)
              Padding(
                padding: const EdgeInsets.only(bottom: 4),
                child: Row(
                  children: [
                    Expanded(
                      child: Text(c.concepto,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(fontSize: 13)),
                    ),
                    Text('$mon ${c.monto.toStringAsFixed(2)}',
                        style: const TextStyle(fontSize: 13)),
                  ],
                ),
              ),
            const SizedBox(height: 10),
            if (_cargando)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 40),
                child: Center(child: CircularProgressIndicator(color: lima)),
              )
            else if (p == null) ...[
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(14),
                decoration: BoxDecoration(
                    color: estadoWarnBg,
                    borderRadius: BorderRadius.circular(14)),
                child: Text(_error ?? 'No se pudo preparar el pago.',
                    style: const TextStyle(
                        color: estadoWarnFg, fontWeight: FontWeight.w600)),
              ),
              const SizedBox(height: 12),
              SizedBox(
                width: double.infinity,
                child: FilledButton(
                  style: FilledButton.styleFrom(
                      backgroundColor: lima,
                      foregroundColor: Colors.white,
                      padding: const EdgeInsets.symmetric(vertical: 14)),
                  onPressed: _iniciar,
                  child: Text('Generar QR · $mon ${base.toStringAsFixed(2)}',
                      style: const TextStyle(fontWeight: FontWeight.w800)),
                ),
              ),
            ] else ...[
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(14),
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(18),
                  border: Border.all(color: lima, width: 2),
                ),
                child: Column(
                  children: [
                    Text('Escanea y paga a ${p.titular}',
                        textAlign: TextAlign.center,
                        style: const TextStyle(
                            fontWeight: FontWeight.w800, fontSize: 14.5)),
                    const SizedBox(height: 10),
                    ClipRRect(
                      borderRadius: BorderRadius.circular(14),
                      child: CachedNetworkImage(
                        imageUrl: p.qrUrl,
                        width: 240,
                        height: 240,
                        fit: BoxFit.contain,
                        placeholder: (_, __) => const SizedBox(
                            width: 240,
                            height: 240,
                            child: Center(
                                child: CircularProgressIndicator(color: lima))),
                        errorWidget: (_, __, ___) => const SizedBox(
                            width: 240,
                            height: 240,
                            child: Center(
                                child: Text('No se pudo cargar el QR'))),
                      ),
                    ),
                    const SizedBox(height: 10),
                    Text(p.montoTxt,
                        style: const TextStyle(
                            fontWeight: FontWeight.w900,
                            fontSize: 32,
                            color: bosque)),
                    const SizedBox(height: 2),
                    Text(
                        'Paga EXACTAMENTE este monto: incluye ${p.extraTxt} '
                        'de identificación para que tu pago se confirme solo.',
                        textAlign: TextAlign.center,
                        style: const TextStyle(
                            color: textoTenue, fontSize: 12.5, height: 1.3)),
                  ],
                ),
              ),
              const SizedBox(height: 14),
              _paso('1',
                  'Toca «Compartir QR» y ábrelo desde ${p.appNombre.isNotEmpty ? p.appNombre : 'tu app del banco'} (o escanéalo desde otro celular).'),
              _paso('2', 'Escribe el monto ${p.montoTxt} tal cual, con los centavos.'),
              _paso('3',
                  'Paga. Apenas le llegue a la academia, tu cuota queda pagada sola.'),
              const SizedBox(height: 8),
              Row(
                children: [
                  Expanded(
                    child: OutlinedButton.icon(
                      onPressed: _compartiendo ? null : _compartirQr,
                      icon: const Icon(Icons.ios_share, size: 18),
                      label: const Text('Compartir QR'),
                    ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: OutlinedButton.icon(
                      onPressed: _copiarMonto,
                      icon: const Icon(Icons.copy_rounded, size: 18),
                      label: const Text('Copiar monto'),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              if (p.estado == 'esperando')
                SizedBox(
                  width: double.infinity,
                  child: FilledButton(
                    style: FilledButton.styleFrom(
                        backgroundColor: lima,
                        foregroundColor: Colors.white,
                        padding: const EdgeInsets.symmetric(vertical: 14)),
                    onPressed: _avisando ? null : _yaPague,
                    child: _avisando
                        ? const SizedBox(
                            width: 20,
                            height: 20,
                            child: CircularProgressIndicator(
                                strokeWidth: 2.4, color: Colors.white))
                        : const Text('Ya pagué',
                            style: TextStyle(fontWeight: FontWeight.w800)),
                  ),
                ),
              const SizedBox(height: 12),
              Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  const SizedBox(
                      width: 14,
                      height: 14,
                      child: CircularProgressIndicator(
                          strokeWidth: 2, color: lima)),
                  const SizedBox(width: 8),
                  Flexible(
                    child: Text(
                        p.estado == 'reportado'
                            ? 'Esperando que el pago llegue a la academia…'
                            : 'Esperando tu pago… se confirma solo cuando llegue.',
                        style: const TextStyle(
                            fontSize: 12.5, color: textoTenue)),
                  ),
                ],
              ),
            ],
            const SizedBox(height: 10),
            const Text(
                'Le pagas directo a la academia. Pichangol no toca tu plata ni '
                'cobra comisión: solo reconoce tu pago y te lo recuerda.',
                style: TextStyle(color: textoTenue, fontSize: 12)),
          ],
        ),
      ),
    );
  }
}
