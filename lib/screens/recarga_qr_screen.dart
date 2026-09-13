import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:supabase_flutter/supabase_flutter.dart' show FileOptions;

import '../services/pagos_service.dart';
import '../services/supabase_service.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/ancho_lectura.dart';
import '../widgets/cargando_pichangol.dart';
import '../widgets/dialogo_pichangol.dart';

/// RECARGA POR QR (Yape directo, sin comisión de pasarela): el usuario yapea
/// al QR de Pichangol, sube su constancia y el OPERADOR la aprueba en la
/// torre — al aprobar, el saldo se acredita y llega el push "Recarga
/// acreditada ✅". Modelo concierge (como los reclamos). Solo Perú (Yape).
class RecargaQrScreen extends StatefulWidget {
  const RecargaQrScreen({super.key});

  @override
  State<RecargaQrScreen> createState() => _RecargaQrScreenState();
}

class _RecargaQrScreenState extends State<RecargaQrScreen> {
  static const _montos = [20, 50, 100, 200];
  int _monto = 50;
  bool _cargando = true;
  Map<String, dynamic>? _cfg;

  String get _email => (appState.usuario?.email ?? '').toLowerCase();

  @override
  void initState() {
    super.initState();
    PagosService.recargaQrConfig().then((c) {
      if (!mounted) return;
      setState(() {
        _cfg = c;
        _cargando = false;
      });
    });
  }

  Future<void> _enviarConstancia() async {
    // 1. Foto de la constancia del Yape (cámara o galería, por selección).
    final origen = await showModalBottomSheet<ImageSource>(
      context: context,
      backgroundColor: Theme.of(context).colorScheme.surface,
      shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(22))),
      builder: (bctx) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Padding(
              padding: EdgeInsets.fromLTRB(20, 16, 20, 4),
              child: Align(
                alignment: Alignment.centerLeft,
                child: Text('Constancia de tu Yape',
                    style: TextStyle(
                        fontWeight: FontWeight.w800, fontSize: 17)),
              ),
            ),
            ListTile(
                leading: const Icon(Icons.photo_library_outlined,
                    color: bosque),
                title: const Text('Elegir la captura de la galería'),
                onTap: () => Navigator.pop(bctx, ImageSource.gallery)),
            ListTile(
                leading: const Icon(Icons.photo_camera_outlined,
                    color: bosque),
                title: const Text('Tomar foto'),
                onTap: () => Navigator.pop(bctx, ImageSource.camera)),
            const SizedBox(height: 8),
          ],
        ),
      ),
    );
    if (origen == null || !mounted) return;
    final foto = await ImagePicker()
        .pickImage(source: origen, maxWidth: 1280, imageQuality: 82);
    if (foto == null || !mounted) return;

    // 2. Sube la constancia + crea la solicitud (queda en revisión).
    final ok = await conPreload(context, () async {
      String url = '';
      try {
        final bytes = await foto.readAsBytes();
        final ruta =
            'recargas/rq_${DateTime.now().millisecondsSinceEpoch}.jpg';
        final storage = SupabaseService.client.storage.from('canchas');
        await storage.uploadBinary(ruta, bytes,
            fileOptions:
                const FileOptions(upsert: true, contentType: 'image/jpeg'));
        url = storage.getPublicUrl(ruta);
      } catch (_) {
        return null; // sin constancia no se envía (el operador la necesita)
      }
      return PagosService.crearRecargaQr(
          email: _email, monto: _monto, fotoUrl: url);
    }, texto: 'Enviando…');
    if (!mounted) return;
    if (ok == null) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          backgroundColor: clayOscuro,
          content: Text('No se pudo enviar. Revisa tu conexión e intenta.')));
      return;
    }
    if (ok['ok'] != true) {
      await avisarPichangol(
        context,
        titulo: 'Ya tienes una en revisión',
        mensaje: 'Tu recarga anterior aún está en revisión. Te avisamos con '
            'una notificación apenas se acredite.',
        icono: Icons.hourglass_top,
      );
      if (mounted) Navigator.of(context).pop(true);
      return;
    }
    await avisarPichangol(
      context,
      titulo: 'Constancia enviada ✅',
      mensaje: 'Tu recarga de S/ $_monto quedó EN REVISIÓN. La validamos y '
          'te avisamos con una notificación apenas se acredite (suele ser '
          'en minutos).',
      icono: Icons.mark_email_read_outlined,
    );
    if (mounted) Navigator.of(context).pop(true);
  }

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final cs = Theme.of(context).colorScheme;
    final activo = (_cfg?['activo'] ?? false) == true;
    final qrUrl = (_cfg?['qr_url'] ?? '').toString();
    final numero = (_cfg?['numero'] ?? '').toString();
    final nombre = (_cfg?['nombre'] ?? 'Pichangol').toString();
    return Scaffold(
      appBar: AppBar(title: const Text('Recargar con Yape (QR)')),
      body: AnchoLectura(
        child: _cargando
            ? const Center(child: CargandoPichangol())
            : !activo
                ? const Center(
                    child: Padding(
                      padding: EdgeInsets.all(28),
                      child: Text(
                          'La recarga por QR no está disponible por ahora. '
                          'Usa Yape o tarjeta desde "Recargar saldo".',
                          textAlign: TextAlign.center,
                          style: TextStyle(color: textoTenue)),
                    ),
                  )
                : ListView(
                    padding: const EdgeInsets.fromLTRB(18, 14, 18, 30),
                    children: [
                      Text('1 · Elige el monto',
                          style: t.titleMedium
                              ?.copyWith(fontWeight: FontWeight.w800)),
                      const SizedBox(height: 10),
                      Wrap(
                        spacing: 10,
                        runSpacing: 10,
                        children: [
                          for (final m in _montos)
                            ChoiceChip(
                              label: Text('S/ $m'),
                              selected: _monto == m,
                              selectedColor: lima,
                              labelStyle: TextStyle(
                                  fontWeight: FontWeight.w800,
                                  color: _monto == m
                                      ? Colors.white
                                      : cs.onSurface),
                              onSelected: (_) =>
                                  setState(() => _monto = m),
                            ),
                        ],
                      ),
                      const SizedBox(height: 20),
                      Text('2 · Yapea S/ $_monto a este QR',
                          style: t.titleMedium
                              ?.copyWith(fontWeight: FontWeight.w800)),
                      const SizedBox(height: 10),
                      Center(
                        child: Container(
                          padding: const EdgeInsets.all(14),
                          decoration: BoxDecoration(
                            color: Colors.white,
                            borderRadius: BorderRadius.circular(18),
                            border: Border.all(color: trazo),
                            boxShadow: const [
                              BoxShadow(
                                  color: Color(0x14000000),
                                  blurRadius: 12,
                                  offset: Offset(0, 4)),
                            ],
                          ),
                          child: Column(
                            children: [
                              ClipRRect(
                                borderRadius: BorderRadius.circular(10),
                                child: CachedNetworkImage(
                                  imageUrl: qrUrl,
                                  width: 220,
                                  height: 220,
                                  fit: BoxFit.contain,
                                  placeholder: (_, __) => const SizedBox(
                                      width: 220,
                                      height: 220,
                                      child: Center(
                                          child:
                                              CircularProgressIndicator())),
                                  errorWidget: (_, __, ___) =>
                                      const SizedBox(
                                          width: 220,
                                          height: 220,
                                          child: Center(
                                              child: Text('QR no cargó'))),
                                ),
                              ),
                              const SizedBox(height: 8),
                              Text(nombre,
                                  style: const TextStyle(
                                      fontWeight: FontWeight.w800)),
                              if (numero.isNotEmpty)
                                Text(numero,
                                    style: const TextStyle(
                                        color: textoTenue, fontSize: 13)),
                            ],
                          ),
                        ),
                      ),
                      const SizedBox(height: 20),
                      Text('3 · Envía tu constancia',
                          style: t.titleMedium
                              ?.copyWith(fontWeight: FontWeight.w800)),
                      const SizedBox(height: 6),
                      const Text(
                          'La captura del Yape que te sale al pagar. La '
                          'validamos y tu saldo se acredita con una '
                          'notificación (suele ser en minutos).',
                          style:
                              TextStyle(color: textoTenue, fontSize: 13)),
                      const SizedBox(height: 14),
                      SizedBox(
                        width: double.infinity,
                        child: FilledButton.icon(
                          style: FilledButton.styleFrom(
                              backgroundColor: lima,
                              foregroundColor: Colors.white,
                              padding:
                                  const EdgeInsets.symmetric(vertical: 15)),
                          onPressed: _enviarConstancia,
                          icon: const Icon(Icons.receipt_long),
                          label: Text('Ya yapeé S/ $_monto · enviar constancia'),
                        ),
                      ),
                      const SizedBox(height: 10),
                      const Center(
                        child: Text(
                            'Sin comisiones · lo valida el equipo Pichangol',
                            style: TextStyle(
                                color: textoTenue, fontSize: 12)),
                      ),
                    ],
                  ),
      ),
    );
  }
}
