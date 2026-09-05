import 'package:flutter/material.dart';

import '../models/bono.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../utils/moneda.dart';
import '../widgets/ancho_lectura.dart';

/// "Mis bonos" (vista del JUGADOR): los packs de horas prepagadas que compró,
/// con su saldo y consumo. Da claridad de a dónde fue su plata: compró un bono,
/// lo paga UNA vez, y cada reserva con bono descuenta de aquí (no vuelve a
/// pagar). El símbolo de moneda es el del local de cada bono.
class MisBonosScreen extends StatefulWidget {
  const MisBonosScreen({super.key});

  @override
  State<MisBonosScreen> createState() => _MisBonosScreenState();
}

class _MisBonosScreenState extends State<MisBonosScreen> {
  @override
  void initState() {
    super.initState();
    appState.cargarMisBonos();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Mis bonos')),
      body: ListenableBuilder(
        listenable: appState,
        builder: (context, _) {
          final bonos = appState.misBonos;
          return RefreshIndicator(
            onRefresh: () => appState.cargarMisBonos(),
            child: AnchoLectura(
              child: bonos.isEmpty
                  ? ListView(
                      children: const [
                        SizedBox(height: 90),
                        _Vacio(),
                      ],
                    )
                  : ListView(
                      padding: const EdgeInsets.fromLTRB(18, 16, 18, 24),
                      children: [
                        Text(
                            'Paquetes de horas que compraste. Los pagaste una '
                            'sola vez; al reservar con tu bono descuentas de '
                            'aquí, sin volver a pagar.',
                            style: Theme.of(context)
                                .textTheme
                                .bodySmall
                                ?.copyWith(color: textoTenueDe(context))),
                        const SizedBox(height: 16),
                        for (final b in bonos)
                          Padding(
                            padding: const EdgeInsets.only(bottom: 12),
                            child: _MiBonoCard(bono: b),
                          ),
                      ],
                    ),
            ),
          );
        },
      ),
    );
  }
}

class _MiBonoCard extends StatelessWidget {
  const _MiBonoCard({required this.bono});
  final BonoComprado bono;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    // El símbolo lo toma de una cancha del local si existe; si no, del actual.
    final mon = appState.monedaDeClub(bono.club);
    final sinSaldo = bono.saldo <= 0;
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: trazo),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                    color: (sinSaldo ? textoTenue : teal).withOpacity(0.14),
                    borderRadius: BorderRadius.circular(12)),
                child: Icon(Icons.confirmation_number,
                    color: sinSaldo ? textoTenue : teal),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(bono.club,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style:
                            t.titleMedium?.copyWith(fontWeight: FontWeight.w800)),
                    Text('Compraste ${bono.horasTotal} h · $mon ${montoTxt(bono.precio)}',
                        style: t.bodySmall
                            ?.copyWith(color: textoTenueDe(context))),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          // Barra de consumo: usadas vs total.
          ClipRRect(
            borderRadius: BorderRadius.circular(8),
            child: LinearProgressIndicator(
              value: bono.horasTotal == 0
                  ? 0
                  : bono.horasUsadas / bono.horasTotal,
              minHeight: 8,
              backgroundColor: const Color(0x14000000),
              valueColor: AlwaysStoppedAnimation(
                  sinSaldo ? textoTenue : teal),
            ),
          ),
          const SizedBox(height: 8),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text('Usaste ${bono.horasUsadas} de ${bono.horasTotal} h',
                  style: t.bodySmall?.copyWith(color: textoTenueDe(context))),
              Text(
                  sinSaldo ? 'Sin saldo' : 'Te quedan ${bono.saldo} h',
                  style: t.bodyMedium?.copyWith(
                      color: sinSaldo ? textoTenue : teal,
                      fontWeight: FontWeight.w800)),
            ],
          ),
        ],
      ),
    );
  }
}

class _Vacio extends StatelessWidget {
  const _Vacio();

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return Column(
      children: [
        Icon(Icons.confirmation_number_outlined,
            size: 56, color: textoTenueDe(context)),
        const SizedBox(height: 12),
        Text('Aún no tienes bonos',
            style: t.titleMedium?.copyWith(fontWeight: FontWeight.w800)),
        const SizedBox(height: 6),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 40),
          child: Text(
              'Compra un pack de horas en la ficha de una cancha y ahorra: '
              'pagas por adelantado y reservas descontando de tu bono.',
              textAlign: TextAlign.center,
              style: t.bodySmall?.copyWith(color: textoTenueDe(context))),
        ),
      ],
    );
  }
}
