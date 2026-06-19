import 'package:flutter/material.dart';

import '../brand.dart';
import '../data/sample_data.dart';
import '../state/app_state.dart';
import '../theme.dart';
import 'home_shell.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  late final TextEditingController _ctrl =
      TextEditingController(text: SampleData.clubActivo);

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        foregroundColor: verdeCancha,
        title: const Text('Soy dueño de cancha',
            style: TextStyle(color: verdeCancha, fontSize: 16)),
      ),
      extendBodyBehindAppBar: true,
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(28),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                const Text('🎾', style: TextStyle(fontSize: 56)),
                const SizedBox(height: 8),
                Text(
                  kBrandName,
                  style: Theme.of(context)
                      .textTheme
                      .headlineMedium
                      ?.copyWith(fontWeight: FontWeight.bold, color: verdeCancha),
                ),
                Text(
                  'Panel del Club · Llena tus horas vacías',
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.bodyMedium,
                ),
                const SizedBox(height: 40),
                TextField(
                  controller: _ctrl,
                  decoration: const InputDecoration(
                    labelText: 'Nombre del club',
                    border: OutlineInputBorder(),
                  ),
                ),
                const SizedBox(height: 16),
                SizedBox(
                  width: double.infinity,
                  child: FilledButton(
                    onPressed: () {
                      appState.iniciarSesion(_ctrl.text);
                      Navigator.of(context).pushReplacement(
                        MaterialPageRoute(builder: (_) => const HomeShell()),
                      );
                    },
                    style: FilledButton.styleFrom(
                      backgroundColor: verdeCancha,
                      padding: const EdgeInsets.symmetric(vertical: 14),
                    ),
                    child: const Text('Ingresar al panel'),
                  ),
                ),
                const SizedBox(height: 24),
                Text(
                  'Acceso de demostración · Fase 1 (captación de oferta)',
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.labelSmall,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
