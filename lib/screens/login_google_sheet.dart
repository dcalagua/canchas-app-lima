import 'package:flutter/material.dart';

import '../brand.dart';
import '../state/app_state.dart';
import '../theme.dart';

/// Hoja de login con Google. Se muestra cuando un invitado intenta reservar.
/// Devuelve true por Navigator.pop si el usuario quedó logueado.
class LoginGoogleSheet extends StatefulWidget {
  const LoginGoogleSheet({super.key});

  /// Muestra la hoja y resuelve a true si el usuario inició sesión.
  static Future<bool> mostrar(BuildContext context) async {
    final ok = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
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
    return Container(
      decoration: const BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      padding: EdgeInsets.fromLTRB(
          24, 16, 24, 24 + MediaQuery.of(context).viewInsets.bottom),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: 44,
            height: 5,
            decoration: BoxDecoration(
              color: Colors.black12,
              borderRadius: BorderRadius.circular(10),
            ),
          ),
          const SizedBox(height: 20),
          Container(
            padding: const EdgeInsets.all(14),
            decoration: const BoxDecoration(
                color: Color(0xFFEAF6EF), shape: BoxShape.circle),
            child: const Icon(Icons.lock_open, color: verdeCancha, size: 30),
          ),
          const SizedBox(height: 16),
          const Text(
            'Inicia sesión para reservar',
            style: TextStyle(fontSize: 19, fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 6),
          Text(
            'Buscar y explorar es libre. Para reservar tu cancha en $kBrandName, '
            'entra con tu cuenta de Google.',
            textAlign: TextAlign.center,
            style: TextStyle(color: Colors.grey[700], height: 1.4),
          ),
          const SizedBox(height: 24),
          SizedBox(
            width: double.infinity,
            child: _cargando
                ? const Padding(
                    padding: EdgeInsets.symmetric(vertical: 14),
                    child: Center(child: CircularProgressIndicator()),
                  )
                : _BotonGoogle(onTap: _entrar),
          ),
          const SizedBox(height: 12),
          Text(
            'Usamos tu Gmail solo para identificar tus reservas.',
            textAlign: TextAlign.center,
            style: TextStyle(color: Colors.grey[500], fontSize: 12),
          ),
        ],
      ),
    );
  }
}

class _BotonGoogle extends StatelessWidget {
  final VoidCallback onTap;
  const _BotonGoogle({required this.onTap});

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.white,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(14),
        side: const BorderSide(color: Color(0xFFDADCE0)),
      ),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(14),
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 14),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              // Logotipo "G" multicolor simplificado.
              const _GoogleG(),
              const SizedBox(width: 12),
              Text(
                'Continuar con Google',
                style: TextStyle(
                  color: Colors.grey[800],
                  fontWeight: FontWeight.w600,
                  fontSize: 15,
                ),
              ),
            ],
          ),
        ),
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
      decoration: const BoxDecoration(shape: BoxShape.circle),
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
