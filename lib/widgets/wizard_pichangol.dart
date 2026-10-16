import 'package:flutter/material.dart';

import '../theme.dart';
import 'dialogo_pichangol.dart';
import 'responsive.dart';

/// Un paso del wizard: título grande + subtítulo + su contenido.
class PasoWizard {
  final String titulo;
  final String sub;
  final List<Widget> hijos;
  const PasoWizard(
      {required this.titulo, required this.sub, required this.hijos});
}

/// Andamiaje del WIZARD estilo Airbnb — REGLA de UI para los flujos de
/// creación del anfitrión (reclamar/registrar cancha, academias, campeonatos,
/// tienda): pantalla completa por paso con "Paso N de M" + título grande +
/// subtítulo, barra de progreso segmentada, Atrás/Siguiente y pill "Salir"
/// con confirmación. La pantalla dueña controla el paso, valida y envía.
class WizardPichangol extends StatelessWidget {
  const WizardPichangol({
    super.key,
    required this.paso,
    required this.pasos,
    required this.onPaso,
    required this.onEnviar,
    required this.textoEnviar,
    this.enviando = false,
    this.tituloSalir = '¿Salir sin guardar?',
    this.mensajeSalir = 'Se perderá lo que llenaste hasta ahora.',
    this.validarPaso,
  });

  final int paso;
  final List<PasoWizard> pasos;
  final ValueChanged<int> onPaso;
  final VoidCallback onEnviar;
  final String textoEnviar;
  final bool enviando;
  final String tituloSalir;
  final String mensajeSalir;

  /// true = puede avanzar desde [paso]. La pantalla muestra su propio aviso
  /// (snackbar) cuando devuelve false. null = siempre se puede.
  final bool Function(int paso)? validarPaso;

  @override
  Widget build(BuildContext context) {
    final i = paso.clamp(0, pasos.length - 1);
    final p = pasos[i];
    final ultimo = i >= pasos.length - 1;
    final t = Theme.of(context).textTheme;
    return Scaffold(
      body: SafeArea(
        child: Column(
          children: [
            // Barra superior estilo Airbnb: pill "Salir" a la izquierda.
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 10, 16, 0),
              child: Row(
                children: [
                  OutlinedButton(
                    style: OutlinedButton.styleFrom(
                      foregroundColor: Theme.of(context).colorScheme.onSurface,
                      side: const BorderSide(color: trazo),
                      shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(999)),
                      padding: const EdgeInsets.symmetric(
                          horizontal: 16, vertical: 8),
                    ),
                    onPressed: () async {
                      final ok = await confirmarPichangol(
                        context,
                        titulo: tituloSalir,
                        mensaje: mensajeSalir,
                        textoConfirmar: 'Salir',
                        icono: Icons.logout,
                      );
                      if (ok && context.mounted) {
                        Navigator.of(context).maybePop();
                      }
                    },
                    child: const Text('Salir',
                        style: TextStyle(fontWeight: FontWeight.w700)),
                  ),
                ],
              ),
            ),
            Expanded(
              child: ListView(
                padding: EdgeInsets.fromLTRB(ladoTablet(context, 20), 16,
                    ladoTablet(context, 20), 24),
                children: [
                  Text('Paso ${i + 1} de ${pasos.length}',
                      style: t.bodySmall?.copyWith(
                          color: textoTenueDe(context),
                          fontWeight: FontWeight.w700)),
                  const SizedBox(height: 6),
                  Text(p.titulo,
                      style: t.headlineMedium?.copyWith(
                          fontWeight: FontWeight.w800, height: 1.05)),
                  const SizedBox(height: 8),
                  Text(p.sub,
                      style: t.bodyMedium?.copyWith(
                          color: textoTenueDe(context), height: 1.35)),
                  const SizedBox(height: 22),
                  ...p.hijos,
                ],
              ),
            ),
            // Progreso segmentado + Atrás / Siguiente (estilo Airbnb).
            Container(
              decoration: BoxDecoration(
                color: Theme.of(context).colorScheme.surface,
                border: const Border(top: BorderSide(color: trazo)),
              ),
              padding: EdgeInsets.fromLTRB(
                  ladoTablet(context, 20), 0, ladoTablet(context, 20), 12),
              child: Column(
                children: [
                  Row(
                    children: [
                      for (var s = 0; s < pasos.length; s++)
                        Expanded(
                          child: Container(
                            height: 4,
                            margin: EdgeInsets.only(
                                right: s == pasos.length - 1 ? 0 : 6),
                            decoration: BoxDecoration(
                              color:
                                  s <= i ? lima : const Color(0xFFE4E4E4),
                              borderRadius: BorderRadius.circular(999),
                            ),
                          ),
                        ),
                    ],
                  ),
                  const SizedBox(height: 10),
                  Row(
                    children: [
                      if (i > 0)
                        TextButton(
                          onPressed: enviando ? null : () => onPaso(i - 1),
                          child: Text('Atrás',
                              style: TextStyle(
                                  color:
                                      Theme.of(context).colorScheme.onSurface,
                                  fontWeight: FontWeight.w800,
                                  decoration: TextDecoration.underline)),
                        ),
                      const Spacer(),
                      FilledButton(
                        style: FilledButton.styleFrom(
                          backgroundColor: ultimo ? lima : tinta,
                          foregroundColor: Colors.white,
                          padding: const EdgeInsets.symmetric(
                              horizontal: 26, vertical: 13),
                          shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(12)),
                        ),
                        onPressed: enviando
                            ? null
                            : () {
                                if (ultimo) {
                                  onEnviar();
                                  return;
                                }
                                if (validarPaso != null &&
                                    !validarPaso!(i)) {
                                  return;
                                }
                                onPaso(i + 1);
                              },
                        child: Text(ultimo ? textoEnviar : 'Siguiente',
                            style:
                                const TextStyle(fontWeight: FontWeight.w800)),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
