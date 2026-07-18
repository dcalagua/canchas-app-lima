import 'package:flutter/material.dart';

import '../brand.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/google_logo.dart';
import '../widgets/marca.dart';

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
          // Marca: logo cuadrado (pelota) + wordmark "Pichang·o·l" + eslogan.
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
                ? Center(child: CircularProgressIndicator(color: cs.primary))
                : OutlinedButton.icon(
                    style: OutlinedButton.styleFrom(
                      backgroundColor: Colors.white,
                      side: const BorderSide(
                          color: Color(0xFFE3DECF), width: 1.5),
                      shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(16)),
                      foregroundColor: tinta,
                    ),
                    icon: const GoogleLogo(size: 22),
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

