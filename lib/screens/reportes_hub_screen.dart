import 'package:flutter/material.dart';

import '../theme.dart';
import 'reporte_canchas_screen.dart';
import 'reportes_screen.dart';

/// Hub de REPORTES del dueño con dos pestañas (unifica lo que antes eran dos
/// entradas separadas):
///  - **Resumen:** el dashboard rápido (ingresos del mes, 7 días, ocupación).
///  - **Cobros:** el reporte detallado (filtro por período, ganancia neta tras
///    comisión, desglose por local/cancha, compartir).
/// La billetera queda aparte (es tu dinero, no analítica); se enlaza desde ahí.
class ReportesHubScreen extends StatelessWidget {
  const ReportesHubScreen({super.key, this.inicial = 0});

  /// Pestaña inicial: 0 = Resumen, 1 = Cobros.
  final int inicial;

  @override
  Widget build(BuildContext context) {
    return DefaultTabController(
      length: 2,
      initialIndex: inicial.clamp(0, 1),
      child: Scaffold(
        backgroundColor: Theme.of(context).brightness == Brightness.dark
            ? Theme.of(context).scaffoldBackgroundColor
            : papelCalido,
        appBar: AppBar(
          title: const Text('Reportes'),
          bottom: const TabBar(
            labelColor: bosque,
            unselectedLabelColor: textoTenue,
            indicatorColor: lima,
            indicatorWeight: 3,
            labelStyle: TextStyle(fontWeight: FontWeight.w800),
            tabs: [
              Tab(text: 'Resumen'),
              Tab(text: 'Cobros'),
            ],
          ),
        ),
        body: const TabBarView(
          children: [
            // El resumen no tiene AppBar propia, así que se anida tal cual.
            ReportesScreen(),
            ReporteCanchasScreen(embedded: true),
          ],
        ),
      ),
    );
  }
}
