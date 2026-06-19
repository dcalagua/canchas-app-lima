import 'package:flutter/material.dart';

import '../state/app_state.dart';
import '../theme.dart';

/// Hoja de login con Google (rediseño premium). Se muestra cuando un invitado
/// intenta reservar. Devuelve true por Navigator.pop si quedó logueado.
class LoginGoogleSheet extends StatefulWidget {
  const LoginGoogleSheet({super.key});

  /// Muestra la hoja y resuelve a true si el usuario inició sesión.
  static Future<bool> mostrar(BuildContext context) async {
    final ok = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      barrierColor: const Color(0x8C16140F), // rgba(22,20,15,.55)
      builder: (_) => const LoginGoogleSheet(),
    );
    return ok ?? false;
  }

  @override
  State<LoginGoogleSheet> createState() => _LoginGoogleSheetState();
}

class _LoginGoogleSheetState extends State<LoginGoogleSheet> {
  bool _cargando = false;

  Future<void> _entrar() async {
    setState(() => _cargando = true);
    final ok = await appState.entrarConGoogle();
    if (!mounted) return;
    setState(() => _cargando = false);
    if (ok) Navigator.of(context).pop(true);
  }

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return Container(
      decoration: const BoxDecoration(
        color: papel,
        borderRadius: BorderRadius.vertical(top: Radius.circular(28)),
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
          // Marca: cuadrado pino con "P" lima.
          Container(
            width: 60,
            height: 60,
            alignment: Alignment.center,
            decoration: BoxDecoration(
              color: pino,
              borderRadius: BorderRadius.circular(18),
            ),
            child: Text('P',
                style: t.headlineSmall
                    ?.copyWith(color: lima, fontWeight: FontWeight.w700)),
          ),
          const SizedBox(height: 18),
          Text('Inicia sesión para\nreservar tu cancha',
              style: t.headlineSmall),
          const SizedBox(height: 10),
          Text(
            'Explora y busca libre. Solo te pedimos cuenta al confirmar — y '
            'siempre es con Google.',
            style: t.bodyMedium?.copyWith(color: const Color(0xFF7C766B)),
          ),
          const SizedBox(height: 22),
          SizedBox(
            width: double.infinity,
            height: 58,
            child: _cargando
                ? const Center(child: CircularProgressIndicator(color: pino))
                : OutlinedButton.icon(
                    style: OutlinedButton.styleFrom(
                      backgroundColor: Colors.white,
                      side: const BorderSide(
                          color: Color(0xFFE3DECF), width: 1.5),
                      shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(16)),
                      foregroundColor: tinta,
                    ),
                    icon: const _GoogleG(),
                    label: Text('Continuar con Google',
                        style: t.titleMedium?.copyWith(
                            fontWeight: FontWeight.w700, color: tinta)),
                    onPressed: _entrar,
                  ),
          ),
          const SizedBox(height: 16),
          Center(
            child: Text(
              'Al continuar aceptas los Términos y la Privacidad de Pichangol.',
              textAlign: TextAlign.center,
              style: t.bodySmall?.copyWith(color: const Color(0xFFA39D91)),
            ),
          ),
        ],
      ),
    );
  }
}

class _GoogleG extends StatelessWidget {
  const _GoogleG();

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 22,
      height: 22,
      alignment: Alignment.center,
      child: const Text(
        'G',
        style: TextStyle(
          fontWeight: FontWeight.w800,
          fontSize: 18,
          color: Color(0xFF4285F4),
        ),
      ),
    );
  }
}
