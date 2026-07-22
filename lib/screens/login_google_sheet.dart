import 'package:flutter/material.dart';

import '../brand.dart';
import '../services/auth_service.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/google_logo.dart';
import '../widgets/marca.dart';

/// Hoja de login con Google (rediseño premium). Se muestra cuando un invitado
/// intenta una acción que requiere cuenta (reservar, matricularse, publicar,
/// etc.). Devuelve true por Navigator.pop si quedó logueado.
class LoginGoogleSheet extends StatefulWidget {
  const LoginGoogleSheet({super.key, this.motivo});

  /// Frase que completa "Inicia sesión para {motivo}" (ej. "reservar tu
  /// cancha", "matricularte", "publicar tu partido"). Si es null usa un texto
  /// genérico. Adapta el copy al ACTO que disparó el login.
  final String? motivo;

  /// PORTÓN de sesión: úsalo en TODA acción que requiera cuenta.
  /// - Si el usuario YA tiene sesión → devuelve true al instante (no muestra
  ///   nada), así el flujo continúa sin fricción.
  /// - Si no → abre la hoja de login con copy contextual y devuelve true solo
  ///   si el usuario terminó logueado.
  ///
  /// Patrón único recomendado en cada acción:
  ///   if (!await LoginGoogleSheet.mostrar(context, motivo: 'para reservar')) return;
  static Future<bool> mostrar(BuildContext context, {String? motivo}) async {
    if (appState.logueado) return true; // ya tiene cuenta: sin fricción
    final ok = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      barrierColor: const Color(0x8C16140F), // rgba(22,20,15,.55)
      builder: (_) => LoginGoogleSheet(motivo: motivo),
    );
    return ok ?? false;
  }

  @override
  State<LoginGoogleSheet> createState() => _LoginGoogleSheetState();
}

class _LoginGoogleSheetState extends State<LoginGoogleSheet> {
  bool _cargando = false;

  // Modo pruebas: en dev/qas el OAuth de Google no está configurado, así que se
  // permite entrar con un correo escrito (cuentas distintas → probar roles).
  static const _entorno =
      String.fromEnvironment('ENTORNO', defaultValue: 'dev');
  bool get _modoPruebas => _entorno != 'prod';

  final _email = TextEditingController();
  final _nombre = TextEditingController();

  @override
  void dispose() {
    _email.dispose();
    _nombre.dispose();
    super.dispose();
  }

  Future<void> _entrar() async {
    setState(() => _cargando = true);
    final ok = await appState.entrarConGoogle();
    if (!mounted) return;
    setState(() => _cargando = false);
    if (ok) {
      Navigator.of(context).pop(true);
      return;
    }
    // Falló o se canceló. Si hubo error real de Google, muéstralo para
    // diagnosticar (ej. ApiException: 10 = SHA-1/paquete que no calzan).
    final err = AuthService.ultimoError;
    if (err != null && mounted) {
      await showDialog<void>(
        context: context,
        builder: (_) => AlertDialog(
          title: const Text('No se pudo entrar con Google'),
          content: SingleChildScrollView(
            child: Text(
                'Detalle técnico (para diagnóstico):\n\n$err\n\n'
                'Si dice "ApiException: 10", es el SHA-1/paquete del cliente '
                'OAuth. Mientras tanto puedes entrar con tu correo abajo.'),
          ),
          actions: [
            TextButton(
                onPressed: () => Navigator.pop(context),
                child: const Text('Entendido')),
          ],
        ),
      );
    }
  }

  Future<void> _entrarManual() async {
    final correo = _email.text.trim();
    if (!correo.contains('@')) {
      ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Escribe un correo válido.')));
      return;
    }
    setState(() => _cargando = true);
    final ok = await appState.entrarComo(email: correo, nombre: _nombre.text);
    if (!mounted) return;
    setState(() => _cargando = false);
    if (ok) Navigator.of(context).pop(true);
  }

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final cs = Theme.of(context).colorScheme;
    return Container(
      decoration: BoxDecoration(
        color: cs.surface,
        borderRadius: const BorderRadius.vertical(top: Radius.circular(28)),
      ),
      padding: EdgeInsets.fromLTRB(
          26, 18, 26, 36 + MediaQuery.of(context).viewInsets.bottom),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Center(
            child: Container(
              width: 38,
              height: 5,
              margin: const EdgeInsets.only(bottom: 22),
              decoration: BoxDecoration(
                color: const Color(0xFFD8D3C6),
                borderRadius: BorderRadius.circular(3),
              ),
            ),
          ),
          // Marca: logo cuadrado (pin) + wordmark "Pichang·o·l" (pelota) + eslogan.
          Row(
            children: [
              const LogoCuadrado(size: 52),
              const SizedBox(width: 12),
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  const PichangolWordmark(fontSize: 24),
                  Text(kBrandEslogan,
                      style: t.bodySmall?.copyWith(
                          color: textoTenue, fontWeight: FontWeight.w600)),
                ],
              ),
            ],
          ),
          const SizedBox(height: 18),
          Text('Inicia sesión para\n${widget.motivo ?? 'reservar tu cancha'}',
              style: t.headlineSmall),
          const SizedBox(height: 10),
          Text(
            'Explora y busca libre. Solo te pedimos cuenta al confirmar — y '
            'siempre es con Google.',
            style: t.bodyMedium?.copyWith(color: const Color(0xFF7C766B)),
          ),
          const SizedBox(height: 22),
          if (_cargando)
            const Center(child: CircularProgressIndicator(color: lima))
          else ...[
            // Login REAL con Google (siempre disponible). Si falla, muestra el
            // error para diagnóstico (ver _entrar).
            SizedBox(
              width: double.infinity,
              height: 58,
              child: OutlinedButton.icon(
                style: OutlinedButton.styleFrom(
                  backgroundColor: Colors.white,
                  side: const BorderSide(color: Color(0xFFE3DECF), width: 1.5),
                  shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(16)),
                  foregroundColor: tinta,
                ),
                icon: const GoogleLogo(size: 22),
                label: Text('Continuar con Google',
                    style: t.titleMedium
                        ?.copyWith(fontWeight: FontWeight.w700, color: tinta)),
                onPressed: _entrar,
              ),
            ),
            // Respaldo por CORREO: si Google falla o para simular cuentas en
            // pruebas. En prod queda discreto (abajo), pero disponible.
            const SizedBox(height: 18),
            Row(children: [
              const Expanded(child: Divider()),
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 10),
                child: Text(
                    _modoPruebas
                        ? 'o entra con tu correo (pruebas)'
                        : 'o si Google falla, entra con tu correo',
                    style: t.bodySmall?.copyWith(color: textoTenue)),
              ),
              const Expanded(child: Divider()),
            ]),
            const SizedBox(height: 14),
            TextField(
              controller: _nombre,
              textCapitalization: TextCapitalization.words,
              decoration: const InputDecoration(
                labelText: 'Nombre (opcional)',
                border: OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: 10),
            TextField(
              controller: _email,
              keyboardType: TextInputType.emailAddress,
              autocorrect: false,
              decoration: const InputDecoration(
                labelText: 'Correo',
                hintText: 'ej. dcalagua@ebim.pe',
                border: OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: 12),
            SizedBox(
              width: double.infinity,
              height: 50,
              child: FilledButton(
                style: FilledButton.styleFrom(
                  backgroundColor: cs.primary,
                  shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(16)),
                ),
                onPressed: _entrarManual,
                child: const Text('Entrar con correo',
                    style:
                        TextStyle(fontWeight: FontWeight.w800, fontSize: 16)),
              ),
            ),
          ],
          const SizedBox(height: 16),
          Center(
            child: Text(
              'Al continuar aceptas los Términos y la Privacidad de Pichangol.',
              textAlign: TextAlign.center,
              style: t.bodySmall?.copyWith(color: const Color(0xFFA39D91)),
            ),
          ),
          const SizedBox(height: 8),
          Center(
            child: Text(kRespaldoEbim,
                style: t.bodySmall?.copyWith(
                    color: textoTenue, fontWeight: FontWeight.w700)),
          ),
        ],
      ),
    );
  }
}

