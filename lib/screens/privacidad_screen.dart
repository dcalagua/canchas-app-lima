import 'package:flutter/material.dart';

import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/responsive.dart';

/// Privacidad del chat, estilo WhatsApp: el usuario decide si muestra su
/// "última vez / en línea" y si envía confirmaciones de lectura (2 azules).
/// Ambas con RECIPROCIDAD: si apagas la tuya, tampoco ves la del otro.
class PrivacidadScreen extends StatelessWidget {
  const PrivacidadScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return Scaffold(
      appBar: AppBar(title: const Text('Privacidad')),
      body: ListenableBuilder(
        listenable: appState,
        builder: (context, _) {
          return ListView(
            padding: EdgeInsets.fromLTRB(
                ladoTablet(context, 18, 600), 14,
                ladoTablet(context, 18, 600), 30),
            children: [
              Text('Tú decides qué comparten tus chats. Como en WhatsApp, si '
                  'apagas una opción tampoco la ves en los demás.',
                  style: t.bodyMedium?.copyWith(color: textoTenueDe(context))),
              const SizedBox(height: 18),
              _SwitchCard(
                icon: Icons.visibility_outlined,
                color: teal,
                titulo: 'Última vez y en línea',
                subtitulo: appState.mostrarUltimaVez
                    ? 'Tus contactos ven cuándo estuviste en línea.'
                    : 'Nadie ve tu "última vez" ni si estás en línea (y tú '
                        'tampoco ves la de ellos).',
                valor: appState.mostrarUltimaVez,
                onChanged: appState.setMostrarUltimaVez,
              ),
              _SwitchCard(
                icon: Icons.done_all,
                color: const Color(0xFF34B7F1), // azul de los checks
                titulo: 'Confirmaciones de lectura',
                subtitulo: appState.confirmacionLectura
                    ? 'Se muestran los 2 checks azules cuando lees un mensaje.'
                    : 'No envías los 2 azules (y tú tampoco los ves). La entrega '
                        '(2 grises) se mantiene.',
                valor: appState.confirmacionLectura,
                onChanged: appState.setConfirmacionLectura,
              ),
              const SizedBox(height: 8),
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 4),
                child: Text(
                  'Nota: las confirmaciones de lectura siempre están activas en '
                  'los grupos y no afectan a las llamadas.',
                  style:
                      t.bodySmall?.copyWith(color: textoTenueDe(context)),
                ),
              ),
            ],
          );
        },
      ),
    );
  }
}

class _SwitchCard extends StatelessWidget {
  const _SwitchCard({
    required this.icon,
    required this.color,
    required this.titulo,
    required this.subtitulo,
    required this.valor,
    required this.onChanged,
  });
  final IconData icon;
  final Color color;
  final String titulo;
  final String subtitulo;
  final bool valor;
  final ValueChanged<bool> onChanged;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.fromLTRB(14, 6, 8, 6),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: trazo),
      ),
      child: Row(
        children: [
          CircleAvatar(
            radius: 20,
            backgroundColor: color,
            child: Icon(icon, color: Colors.white, size: 20),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Padding(
              padding: const EdgeInsets.symmetric(vertical: 10),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(titulo,
                      style:
                          t.titleSmall?.copyWith(fontWeight: FontWeight.w700)),
                  const SizedBox(height: 2),
                  Text(subtitulo,
                      style: t.bodySmall
                          ?.copyWith(color: textoTenueDe(context))),
                ],
              ),
            ),
          ),
          Switch(
            value: valor,
            activeColor: lima,
            onChanged: onChanged,
          ),
        ],
      ),
    );
  }
}
