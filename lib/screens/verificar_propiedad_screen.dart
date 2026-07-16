import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';

import '../models/models.dart';
import '../services/propiedad_service.dart';
import '../state/app_state.dart';
import '../theme.dart';

/// Verifica la **PROPIEDAD** de una cancha por OTP de WhatsApp: el código llega
/// al teléfono del local. Probar que controlas ese teléfono es lo que te habilita
/// como dueño (recién ahí se activan las reservas). Existir ≠ ser el dueño.
class VerificarPropiedadScreen extends StatefulWidget {
  const VerificarPropiedadScreen({super.key, required this.cancha});
  final Cancha cancha;

  @override
  State<VerificarPropiedadScreen> createState() =>
      _VerificarPropiedadScreenState();
}

class _VerificarPropiedadScreenState extends State<VerificarPropiedadScreen> {
  final _telefono = TextEditingController();
  final _codigo = TextEditingController();

  bool _enviando = false;
  bool _otpEnviado = false;
  String? _telefonoEnmascarado;
  String? _via;
  String? _msg;

  @override
  void dispose() {
    _telefono.dispose();
    _codigo.dispose();
    super.dispose();
  }

  Future<void> _solicitar() async {
    final tel = _telefono.text.trim();
    if (tel.length < 9) {
      setState(() => _msg = 'Ingresa el teléfono del local (9 dígitos).');
      return;
    }
    setState(() {
      _enviando = true;
      _msg = null;
    });
    final r = await PropiedadService.solicitarOtp(
        canchaId: widget.cancha.id, telefono: tel);
    if (!mounted) return;
    setState(() => _enviando = false);

    if (r == null) {
      setState(() => _msg =
          'No se pudo enviar el código. Revisa tu conexión e intenta otra vez.');
      return;
    }
    if (r['ok'] == true) {
      setState(() {
        _otpEnviado = true;
        _telefonoEnmascarado = r['telefono_enmascarado'] as String?;
        _via = r['via'] as String?;
        // En entorno de prueba (stub) el backend puede devolver el código.
        final dbg = r['codigo_debug'];
        _msg = dbg != null ? 'Código de prueba: $dbg' : null;
      });
    } else {
      final err = r['error'];
      setState(() => _msg = err == 'reenvio_muy_pronto'
          ? 'Espera ${r['espera_seg']} s antes de reenviar.'
          : 'No se pudo enviar el código ($err).');
    }
  }

  Future<void> _confirmar() async {
    final cod = _codigo.text.trim();
    if (cod.length < 4) {
      setState(() => _msg = 'Ingresa el código que te llegó.');
      return;
    }
    final email = appState.usuario?.email ?? '';
    setState(() {
      _enviando = true;
      _msg = null;
    });
    final r = await PropiedadService.confirmarOtp(
      canchaId: widget.cancha.id,
      codigo: cod,
      solicitanteId: email,
    );
    if (!mounted) return;
    setState(() => _enviando = false);

    if (r == null) {
      setState(() => _msg = 'No se pudo confirmar. Revisa tu conexión.');
      return;
    }
    if (r['ok'] == true && r['estado'] == 'confirmada') {
      // La propiedad quedó probada: habilita la cancha localmente también.
      appState.confirmarPropiedad(widget.cancha.id,
          via: 'otp_whatsapp', dueno: email);
      Navigator.of(context).pop(true);
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
        backgroundColor: lima,
        content: Text('✅ Propiedad verificada. Tu cancha ya acepta reservas.',
            style: TextStyle(color: Colors.white)),
      ));
    } else if (r['ok'] == true && r['estado'] == 'pendiente_revision') {
      Navigator.of(context).pop(false);
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
        content: Text(
            'Código correcto. Como el número no coincide con el del local, lo revisará nuestro equipo.'),
      ));
    } else {
      final err = r['error'];
      setState(() => _msg = err == 'codigo_incorrecto'
          ? 'Código incorrecto. Te quedan ${r['intentos_restantes'] ?? 0} intentos.'
          : err == 'otp_vencido'
              ? 'El código venció. Pide uno nuevo.'
              : 'No se pudo confirmar ($err).');
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final cs = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: const _AppBar(),
      body: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          Text('Confirma que eres el dueño de "${widget.cancha.nombre}"',
              style: t.titleLarge?.copyWith(fontWeight: FontWeight.w800)),
          const SizedBox(height: 8),
          Text(
              'Te enviaremos un código por WhatsApp o SMS al teléfono del local. '
              'Solo quien lo recibe puede activar la cancha para recibir reservas.',
              style: t.bodyMedium?.copyWith(color: textoTenueDe(context))),
          if (!PropiedadService.disponible) ...[
            const SizedBox(height: 16),
            Container(
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                  color: const Color(0xFFFBEAD2),
                  borderRadius: BorderRadius.circular(12)),
              child: Text(
                'La verificación por código aún no está activa en esta versión de '
                'la app. Tu cancha quedó "en revisión de propiedad" y la validará '
                'nuestro equipo. (Falta configurar GROWTH_API_URL en la build.)',
                style: t.bodySmall?.copyWith(color: clayOscuro),
              ),
            ),
          ],
          const SizedBox(height: 22),
          TextField(
            controller: _telefono,
            enabled: !_otpEnviado,
            keyboardType: TextInputType.phone,
            decoration: const InputDecoration(
              labelText: 'Teléfono del local (WhatsApp)',
              hintText: 'Ej.: 987 654 321',
              prefixIcon: Padding(
                padding: EdgeInsets.all(12),
                child: FaIcon(FontAwesomeIcons.whatsapp,
                    color: Color(0xFF25D366), size: 20),
              ),
              prefixIconConstraints: BoxConstraints(minWidth: 44),
            ),
          ),
          const SizedBox(height: 14),
          if (!_otpEnviado)
            SizedBox(
              width: double.infinity,
              child: FilledButton.icon(
                style: FilledButton.styleFrom(
                    padding: const EdgeInsets.symmetric(vertical: 15)),
                onPressed: _enviando ? null : _solicitar,
                icon: _enviando
                    ? const _Spin()
                    : const Icon(Icons.send_to_mobile),
                label: Text(_enviando ? 'Enviando…' : 'Enviar código'),
              ),
            ),
          if (_otpEnviado) ...[
            if (_telefonoEnmascarado != null)
              Padding(
                padding: const EdgeInsets.only(bottom: 12),
                child: Text(
                    _via == 'stub'
                        ? 'Modo prueba (envío real aún no configurado).'
                        : 'Código enviado a $_telefonoEnmascarado'
                            ' por ${_via == 'sms' ? 'SMS' : 'WhatsApp'}.',
                    style: t.bodySmall?.copyWith(color: textoTenueDe(context))),
              ),
            TextField(
              controller: _codigo,
              keyboardType: TextInputType.number,
              maxLength: 6,
              decoration: const InputDecoration(
                labelText: 'Código de 6 dígitos',
                prefixIcon: Icon(Icons.lock_outline),
              ),
            ),
            const SizedBox(height: 6),
            SizedBox(
              width: double.infinity,
              child: FilledButton.icon(
                style: FilledButton.styleFrom(
                    padding: const EdgeInsets.symmetric(vertical: 15)),
                onPressed: _enviando ? null : _confirmar,
                icon: _enviando ? const _Spin() : const Icon(Icons.verified),
                label: Text(_enviando ? 'Verificando…' : 'Verificar propiedad'),
              ),
            ),
            const SizedBox(height: 6),
            TextButton(
              onPressed: _enviando ? null : _solicitar,
              child: const Text('Reenviar código'),
            ),
          ],
          if (_msg != null) ...[
            const SizedBox(height: 12),
            Text(_msg!,
                style: TextStyle(
                    color: _msg!.startsWith('✅') ? cs.primary : clayOscuro,
                    fontWeight: FontWeight.w600)),
          ],
          const SizedBox(height: 24),
          Container(
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
                color: limaSuave,
                borderRadius: BorderRadius.circular(12)),
            child: Text(
              '¿No tienes acceso al teléfono del local? También puedes verificar '
              'con una visita de nuestro equipo o pedir aprobación manual.',
              style: t.bodySmall?.copyWith(color: tinta),
            ),
          ),
        ],
      ),
    );
  }
}

class _AppBar extends StatelessWidget implements PreferredSizeWidget {
  const _AppBar();
  @override
  Size get preferredSize => const Size.fromHeight(kToolbarHeight);
  @override
  Widget build(BuildContext context) =>
      AppBar(title: const Text('Verificar propiedad'));
}

class _Spin extends StatelessWidget {
  const _Spin();
  @override
  Widget build(BuildContext context) => const SizedBox(
      width: 18,
      height: 18,
      child: CircularProgressIndicator(strokeWidth: 2, color: lima));
}
