import 'package:flutter/material.dart';

import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/dialogo_pichangol.dart';
import '../widgets/cargando_pichangol.dart';
import '../widgets/responsive.dart';
import 'recargar_saldo_screen.dart';
import '../widgets/icono_vivo.dart';

/// PICHANGOL PRO: membresía mensual del jugador. Se cobra de la BILLETERA ÚNICA
/// (saldo del usuario) — no pide tarjeta de nuevo. Es la monetización recurrente
/// (MRR) de la capa de comunidad/ranking.
class HazteProScreen extends StatefulWidget {
  const HazteProScreen({super.key});
  @override
  State<HazteProScreen> createState() => _HazteProScreenState();
}

class _HazteProScreenState extends State<HazteProScreen> {
  bool _procesando = false;
  bool _cambiandoRenovacion = false;

  static const _mesesCorto = [
    'ene', 'feb', 'mar', 'abr', 'may', 'jun',
    'jul', 'ago', 'set', 'oct', 'nov', 'dic'
  ];

  @override
  void initState() {
    super.initState();
    appState.sincronizarPro();
    appState.sincronizarSaldo();
  }

  String _fecha(String? iso) {
    if (iso == null) return '';
    final d = DateTime.tryParse(iso)?.toLocal();
    if (d == null) return '';
    return '${d.day} ${_mesesCorto[d.month - 1]} ${d.year}';
  }

  Future<void> _activar() async {
    if (_procesando) return;
    setState(() => _procesando = true);
    Map<String, dynamic> r;
    try {
      r = await conPreload(context, () => appState.suscribirPro(),
          texto: 'Activando…');
    } finally {
      if (mounted) setState(() => _procesando = false);
    }
    if (!mounted) return;
    if (r['ok'] == true) {
      avisarPichangol(
        context,
        titulo: '¡Ya eres Pro! 🎾',
        mensaje: 'Tu membresía Pichangol Pro está activa hasta el '
            '${_fecha(r['hasta'] as String?)}.'
            '${appState.proRenueva ? ' Se renueva sola desde tu saldo.' : ''}',
        textoBoton: 'Genial',
        icono: Icons.workspace_premium,
      );
    } else if (r['falta_saldo'] == true) {
      final req = (r['requerido_soles'] as num?)?.toDouble() ?? appState.proPrecio;
      final ok = await confirmarPichangol(
        context,
        titulo: 'Te falta saldo',
        mensaje: 'Pichangol Pro se cobra de tu saldo (${appState.monedaSaldoSimbolo} '
            '${req.toStringAsFixed(2)}/mes). Recarga y actívalo al toque.',
        textoConfirmar: 'Recargar saldo',
        textoCancelar: 'Ahora no',
        icono: Icons.account_balance_wallet_outlined,
      );
      if (ok && mounted) {
        await Navigator.of(context).push(MaterialPageRoute(
            builder: (_) => RecargarSaldoScreen(
                duenoId: appState.usuario?.email, titulo: 'Recargar saldo')));
        await appState.sincronizarSaldo();
        if (mounted) setState(() {});
      }
    } else {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text((r['error'] ?? 'No se pudo activar. Reintenta.').toString())));
    }
  }

  /// Interruptor "Renovación automática" (mismo núcleo que la web /pro):
  /// apagarlo pide confirmación; al vencer no se debita nada del saldo.
  Future<void> _cambiarRenovacion(bool renovar) async {
    if (_cambiandoRenovacion) return;
    if (!renovar) {
      final ok = await confirmarPichangol(
        context,
        titulo: '¿Cancelar la renovación?',
        mensaje: 'Sigues siendo Pro hasta el ${_fecha(appState.proHasta)}. '
            'Después ya no se cobrará de tu saldo y tu membresía vencerá. '
            'Puedes reactivarla cuando quieras.',
        textoConfirmar: 'Cancelar renovación',
        textoCancelar: 'Mantener',
        destructivo: true,
        icono: Icons.autorenew,
      );
      if (!ok || !mounted) return;
    }
    setState(() => _cambiandoRenovacion = true);
    Map<String, dynamic> r;
    try {
      r = await conPreload(context, () => appState.cambiarRenovacionPro(renovar),
          texto: renovar ? 'Reactivando…' : 'Cancelando…');
    } finally {
      if (mounted) setState(() => _cambiandoRenovacion = false);
    }
    if (!mounted) return;
    if (r['ok'] == true) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text(renovar
              ? 'Listo: tu Pro se renovará solo desde tu saldo.'
              : 'Listo: tu Pro no se renovará. Vence el ${_fecha(appState.proHasta)}.')));
    } else {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text((r['mensaje'] ?? 'No se pudo cambiar. Reintenta.')
              .toString())));
    }
  }

  Widget _tarjetaRenovacion() {
    final cortesia = appState.proCortesia;
    final renueva = appState.proRenueva;
    final detalle = cortesia
        ? 'Tu Pro es de cortesía: no se renueva solo ni se cobra de tu saldo. '
            'Al vencer, actívalo pagando si quieres seguir.'
        : renueva
            ? 'Al vencer (${_fecha(appState.proHasta)}) se cobra 1 mes de tu '
                'saldo Pichangol.'
            : 'Cancelada: vence el ${_fecha(appState.proHasta)} y no se cobrará '
                'nada más.';
    return Container(
      padding: const EdgeInsets.fromLTRB(14, 12, 8, 12),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(16),
        boxShadow: const [
          BoxShadow(color: Color(0x0F000000), blurRadius: 10, offset: Offset(0, 2)),
        ],
      ),
      child: Row(
        children: [
          const IconoVivo(Icons.autorenew, size: 22, color: bosque),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text('Renovación automática',
                    style: TextStyle(fontWeight: FontWeight.w700, fontSize: 14.5)),
                const SizedBox(height: 2),
                Text(detalle,
                    style: const TextStyle(
                        color: textoTenue, fontSize: 12.5, height: 1.3)),
              ],
            ),
          ),
          if (!cortesia)
            Switch(
              value: renueva,
              activeColor: lima,
              onChanged: _cambiandoRenovacion ? null : _cambiarRenovacion,
            ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Pichangol Pro')),
      body: ListenableBuilder(
        listenable: appState,
        builder: (context, _) {
          final activo = appState.proActivo;
          final precio = appState.proPrecio;
          final mon = appState.monedaSaldoSimbolo;
          final saldo = appState.saldoClub;
          return ListView(
            // Regla app: contenido centrado (ancho máx) en pantallas anchas.
            padding: EdgeInsets.fromLTRB(
                ladoTablet(context, 18, 640), 16, ladoTablet(context, 18, 640), 30),
            children: [
              // Tarjeta hero.
              Container(
                padding: const EdgeInsets.all(20),
                decoration: BoxDecoration(
                  gradient: const LinearGradient(
                    begin: Alignment.topLeft,
                    end: Alignment.bottomRight,
                    colors: [bosque, Color(0xFF1E5C4C)],
                  ),
                  borderRadius: BorderRadius.circular(20),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        const IconoVivo(Icons.workspace_premium,
                            color: lima, size: 30),
                        const SizedBox(width: 10),
                        const Text('Pichangol Pro',
                            style: TextStyle(
                                color: Colors.white,
                                fontWeight: FontWeight.w900,
                                fontSize: 22)),
                        const Spacer(),
                        if (activo)
                          Container(
                            padding: const EdgeInsets.symmetric(
                                horizontal: 10, vertical: 5),
                            decoration: BoxDecoration(
                              color: lima,
                              borderRadius: BorderRadius.circular(999),
                            ),
                            child: const Text('ACTIVO',
                                style: TextStyle(
                                    color: Colors.white,
                                    fontWeight: FontWeight.w900,
                                    fontSize: 11)),
                          ),
                      ],
                    ),
                    const SizedBox(height: 10),
                    Text(
                        activo
                            ? 'Eres Pro. Vigente hasta el ${_fecha(appState.proHasta)}.'
                            : 'Sé parte del circuito: tu carnet oficial, tu ranking y tus estadísticas.',
                        style: TextStyle(
                            color: Colors.white.withOpacity(0.9), height: 1.35)),
                    const SizedBox(height: 14),
                    Row(
                      crossAxisAlignment: CrossAxisAlignment.end,
                      children: [
                        Text('$mon ${precio.toStringAsFixed(precio % 1 == 0 ? 0 : 2)}',
                            style: const TextStyle(
                                color: Colors.white,
                                fontWeight: FontWeight.w900,
                                fontSize: 30)),
                        const Padding(
                          padding: EdgeInsets.only(bottom: 5, left: 4),
                          child: Text('/mes',
                              style: TextStyle(color: Colors.white70, fontSize: 15)),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
              if (activo) ...[
                const SizedBox(height: 14),
                _tarjetaRenovacion(),
              ],
              const SizedBox(height: 18),
              const Text('Qué incluye',
                  style: TextStyle(fontWeight: FontWeight.w800, fontSize: 16)),
              const SizedBox(height: 10),
              _Beneficio(Icons.badge, 'Carnet oficial verificado',
                  'Tu ficha de jugador con la insignia Pro.'),
              _Beneficio(Icons.leaderboard, 'Ranking y estadísticas',
                  'Apareces en el ranking del circuito con tus números.'),
              _Beneficio(Icons.emoji_events, 'Prioridad en torneos',
                  'Acceso preferente cuando abramos inscripciones.'),
              _Beneficio(Icons.favorite, 'Apoyas tu comunidad',
                  'Ayudas a que tu academia crezca su circuito.'),
              const SizedBox(height: 16),
              // Nota de cobro desde la billetera única.
              Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: limaSuave,
                  borderRadius: BorderRadius.circular(14),
                ),
                child: Row(
                  children: [
                    const CircleAvatar(radius: 16, backgroundColor: lima, child: IconoVivo(Icons.account_balance_wallet, size: 17, color: Colors.white)),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Text(
                          'Se cobra de tu saldo Pichangol (la misma billetera). '
                          'Tu saldo hoy: $mon $saldo.'
                          '${activo && !appState.proRenueva ? '' : ' Se renueva solo cada mes.'}',
                          style: const TextStyle(
                              color: bosque, fontSize: 12.5, height: 1.3)),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 20),
              SizedBox(
                width: double.infinity,
                child: FilledButton(
                  style: FilledButton.styleFrom(
                      backgroundColor: lima,
                      foregroundColor: Colors.white,
                      padding: const EdgeInsets.symmetric(vertical: 15),
                      shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(14))),
                  onPressed: _procesando ? null : _activar,
                  child: Text(
                          activo
                              ? 'Renovar 1 mes ($mon ${precio.toStringAsFixed(precio % 1 == 0 ? 0 : 2)})'
                              : 'Activar por $mon ${precio.toStringAsFixed(precio % 1 == 0 ? 0 : 2)}/mes',
                          style: const TextStyle(
                              fontWeight: FontWeight.w800, fontSize: 15)),
                ),
              ),
            ],
          );
        },
      ),
    );
  }
}

class _Beneficio extends StatelessWidget {
  const _Beneficio(this.icon, this.titulo, this.detalle);
  final IconData icon;
  final String titulo;
  final String detalle;
  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 38,
            height: 38,
            decoration: BoxDecoration(
              color: morado,
              borderRadius: BorderRadius.circular(11),
            ),
            child: IconoVivo(icon, color: Colors.white, size: 20),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(titulo,
                    style: const TextStyle(
                        fontWeight: FontWeight.w700, fontSize: 14.5)),
                Text(detalle,
                    style: const TextStyle(color: textoTenue, fontSize: 12.5)),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
