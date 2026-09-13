import 'package:flutter/material.dart';

import '../screens/login_google_sheet.dart';
import '../state/app_state.dart';
import '../theme.dart';
import 'google_logo.dart';

/// Estado "necesitas iniciar sesión" reutilizable para pantallas de SOLO
/// LECTURA que sin cuenta quedan vacías (Mis reservas, Métodos de pago,
/// Recargar saldo, etc.). En vez de un vacío engañoso ("aún no tienes…"),
/// explica por qué y ofrece el botón para entrar — con el copy contextual del
/// portón único ([LoginGoogleSheet.mostrar]).
///
/// [motivo] completa "Inicia sesión para {motivo}" (ej. "ver tus reservas").
/// [onLogueado] se llama si el usuario terminó logueado (para recargar la
/// pantalla). Pensado para usarse dentro de un `ListenableBuilder(appState)`.
class SesionRequerida extends StatelessWidget {
  const SesionRequerida({
    super.key,
    required this.motivo,
    this.icono = Icons.lock_outline,
    this.titulo,
    this.onLogueado,
  });

  final String motivo;
  final IconData icono;
  final String? titulo;
  final VoidCallback? onLogueado;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icono, size: 60, color: verdeClaro),
            const SizedBox(height: 16),
            Text(titulo ?? 'Inicia sesión para continuar',
                textAlign: TextAlign.center,
                style: const TextStyle(
                    fontSize: 18, fontWeight: FontWeight.bold)),
            const SizedBox(height: 6),
            Text('Necesitas tu cuenta para $motivo.',
                textAlign: TextAlign.center,
                style: const TextStyle(color: textoTenue)),
            const SizedBox(height: 20),
            FilledButton.icon(
              style: FilledButton.styleFrom(
                  backgroundColor: lima,
                  foregroundColor: Colors.white,
                  padding:
                      const EdgeInsets.symmetric(horizontal: 20, vertical: 12)),
              onPressed: () async {
                final ok =
                    await LoginGoogleSheet.mostrar(context, motivo: motivo);
                if (ok) onLogueado?.call();
              },
              icon: Container(
                padding: const EdgeInsets.all(3),
                decoration: const BoxDecoration(
                    color: Colors.white, shape: BoxShape.circle),
                child: const GoogleLogo(size: 16),
              ),
              label: const Text('Iniciar sesión',
                  style: TextStyle(fontWeight: FontWeight.w800)),
            ),
          ],
        ),
      ),
    );
  }
}
