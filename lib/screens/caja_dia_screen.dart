import 'package:flutter/material.dart';

import '../models/models.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/dialogo_pichangol.dart';
import '../widgets/responsive.dart';

/// CAJA DEL DÍA del dueño: la plata de hoy de un vistazo (cobrado, por cobrar,
/// reservas, ocupación), la lista de reservas del día con "marcar pagado", y el
/// CIERRE DE CAJA (arqueo). Es lo que el dueño abre a diario para cuadrar.
class CajaDiaScreen extends StatefulWidget {
  const CajaDiaScreen({super.key});

  @override
  State<CajaDiaScreen> createState() => _CajaDiaScreenState();
}

class _CajaDiaScreenState extends State<CajaDiaScreen> {
  DateTime _fecha = DateTime.now();

  @override
  void initState() {
    super.initState();
    // Cierre automático de respaldo de días pasados sin cerrar (idempotente).
    appState.autocerrarCajasPendientes();
  }

  String get _iso => appState.isoDe(_fecha);
  bool get _esHoy => appState.isoDe(DateTime.now()) == _iso;

  String get _mon {
    final c = appState.misCanchas;
    return c.isEmpty ? 'S/' : c.first.monedaSimbolo;
  }

  static const _dias = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom'];
  static const _meses = [
    'ene', 'feb', 'mar', 'abr', 'may', 'jun',
    'jul', 'ago', 'set', 'oct', 'nov', 'dic'
  ];

  String get _label {
    final hoy = DateTime.now();
    final d = _fecha;
    final base = DateTime(hoy.year, hoy.month, hoy.day);
    final dd = DateTime(d.year, d.month, d.day);
    final diff = dd.difference(base).inDays;
    if (diff == 0) return 'Hoy';
    if (diff == 1) return 'Mañana';
    if (diff == -1) return 'Ayer';
    return '${_dias[(d.weekday - 1) % 7]} ${d.day} ${_meses[d.month - 1]}';
  }

  void _cambiar(int delta) =>
      setState(() => _fecha = _fecha.add(Duration(days: delta)));

  Future<void> _cerrarCaja() async {
    final c = appState.cajaDia(_iso);
    final ok = await confirmarPichangol(
      context,
      titulo: 'Cerrar caja del día',
      mensaje: 'Cobrado: $_mon ${c.cobrado}\nPor cobrar: $_mon ${c.porCobrar}\n'
          'Reservas: ${c.reservas}\n\nSe guarda el arqueo de $_label.',
      textoConfirmar: 'Cerrar caja',
      icono: Icons.point_of_sale,
    );
    if (ok) {
      appState.cerrarCaja(_iso);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
            backgroundColor: lima,
            content: Text('Caja cerrada: cobraste $_mon ${c.cobrado}.')));
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Caja del día')),
      body: ListenableBuilder(
        listenable: appState,
        builder: (context, _) {
          if (appState.misCanchas.isEmpty) {
            return const Center(
              child: Padding(
                padding: EdgeInsets.all(28),
                child: Text('Registra una cancha para llevar tu caja.',
                    textAlign: TextAlign.center,
                    style: TextStyle(color: textoTenue)),
              ),
            );
          }
          final caja = appState.cajaDia(_iso);
          final reservas = appState.reservasDelDiaDueno(_iso);
          final cierre = appState.cierreDe(_iso);
          return Column(
            children: [
              // Navegación de día.
              Padding(
                padding: const EdgeInsets.fromLTRB(8, 8, 8, 0),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    IconButton(
                        icon: const Icon(Icons.chevron_left),
                        onPressed: () => _cambiar(-1)),
                    Text(_label,
                        style: const TextStyle(
                            fontWeight: FontWeight.w800, fontSize: 16)),
                    IconButton(
                        icon: const Icon(Icons.chevron_right),
                        onPressed: () => _cambiar(1)),
                  ],
                ),
              ),
              Expanded(
                child: ListView(
                  // Regla app: contenido centrado en pantallas anchas.
                  padding: EdgeInsets.fromLTRB(
                      ladoTablet(context, 16, 760), 6,
                      ladoTablet(context, 16, 760), 24),
                  children: [
                    // Caja (cobrado / por cobrar).
                    Container(
                      padding: const EdgeInsets.all(18),
                      decoration: BoxDecoration(
                        color: Theme.of(context).colorScheme.surface,
                        borderRadius: BorderRadius.circular(18),
                        border: Border.all(color: trazo),
                      ),
                      child: Column(
                        children: [
                          Row(
                            children: [
                              Expanded(
                                  child: _Monto('Cobrado',
                                      '$_mon ${caja.cobrado}', lima)),
                              Container(
                                  width: 1, height: 46, color: trazo),
                              Expanded(
                                  child: _Monto('Por cobrar',
                                      '$_mon ${caja.porCobrar}', bosque)),
                            ],
                          ),
                          const Divider(height: 22),
                          Row(
                            mainAxisAlignment: MainAxisAlignment.spaceAround,
                            children: [
                              _Mini('Reservas', '${caja.reservas}'),
                              _Mini('Ocupación', '${caja.ocupacion}%'),
                            ],
                          ),
                        ],
                      ),
                    ),
                    if (cierre != null) ...[
                      const SizedBox(height: 10),
                      Container(
                        padding: const EdgeInsets.all(12),
                        decoration: BoxDecoration(
                          color: cierre.automatico
                              ? const Color(0xFFFBEAD2)
                              : limaSuave,
                          borderRadius: BorderRadius.circular(14),
                        ),
                        child: Row(
                          children: [
                            Icon(
                                cierre.automatico
                                    ? Icons.auto_mode
                                    : Icons.lock_clock,
                                color: cierre.automatico ? clayOscuro : bosque,
                                size: 20),
                            const SizedBox(width: 8),
                            Expanded(
                              child: Text(
                                  cierre.automatico
                                      ? 'Cierre automático (sin confirmar) · '
                                          'cobrado $_mon ${cierre.cobrado}. '
                                          'Revísalo y confírmalo.'
                                      : 'Caja cerrada a las '
                                          '${cierre.cerradaEn.hour.toString().padLeft(2, '0')}:'
                                          '${cierre.cerradaEn.minute.toString().padLeft(2, '0')} · '
                                          'cobraste $_mon ${cierre.cobrado}.',
                                  style: TextStyle(
                                      color: cierre.automatico
                                          ? clayOscuro
                                          : bosque,
                                      fontWeight: FontWeight.w700,
                                      fontSize: 12.5)),
                            ),
                            if (cierre.automatico)
                              TextButton(
                                onPressed: () => appState.reabrirCaja(_iso),
                                style: TextButton.styleFrom(
                                    foregroundColor: clayOscuro,
                                    padding: const EdgeInsets.symmetric(
                                        horizontal: 8)),
                                child: const Text('Reabrir',
                                    style:
                                        TextStyle(fontWeight: FontWeight.w800)),
                              ),
                          ],
                        ),
                      ),
                    ],
                    const SizedBox(height: 18),
                    const Text('Reservas del día',
                        style: TextStyle(
                            fontWeight: FontWeight.w800, fontSize: 15)),
                    const SizedBox(height: 8),
                    if (reservas.isEmpty)
                      Padding(
                        padding: const EdgeInsets.symmetric(vertical: 24),
                        child: Text('No hay reservas este día.',
                            textAlign: TextAlign.center,
                            style: TextStyle(color: textoTenueDe(context))),
                      )
                    else
                      for (final r in reservas) _FilaReserva(reserva: r, mon: _mon),
                  ],
                ),
              ),
              // Cerrar caja.
              SafeArea(
                top: false,
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(16, 6, 16, 12),
                  child: SizedBox(
                    height: 50,
                    child: FilledButton.icon(
                      style: FilledButton.styleFrom(
                          backgroundColor:
                              (cierre == null || cierre.automatico)
                                  ? lima
                                  : bosque,
                          foregroundColor: Colors.white,
                          shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(14))),
                      onPressed: _cerrarCaja,
                      icon: Icon(cierre == null
                          ? Icons.point_of_sale
                          : (cierre.automatico
                              ? Icons.verified_outlined
                              : Icons.refresh)),
                      // Sin cierre → cerrar. Auto-cierre → confirmarlo (pasa a
                      // arqueo del dueño). Cierre manual → recerrar.
                      label: Text(
                          cierre == null
                              ? 'Cerrar caja'
                              : (cierre.automatico
                                  ? 'Confirmar cierre'
                                  : 'Recerrar caja'),
                          style: const TextStyle(
                              fontWeight: FontWeight.w800, fontSize: 15)),
                    ),
                  ),
                ),
              ),
            ],
          );
        },
      ),
    );
  }
}

class _Monto extends StatelessWidget {
  const _Monto(this.titulo, this.valor, this.color);
  final String titulo;
  final String valor;
  final Color color;
  @override
  Widget build(BuildContext context) => Column(
        children: [
          Text(titulo,
              style: const TextStyle(color: textoTenue, fontSize: 13)),
          const SizedBox(height: 4),
          Text(valor,
              style: TextStyle(
                  fontWeight: FontWeight.w900, fontSize: 24, color: color)),
        ],
      );
}

class _Mini extends StatelessWidget {
  const _Mini(this.titulo, this.valor);
  final String titulo;
  final String valor;
  @override
  Widget build(BuildContext context) => Column(
        children: [
          Text(valor,
              style: const TextStyle(
                  fontWeight: FontWeight.w800, fontSize: 17)),
          Text(titulo,
              style: const TextStyle(color: textoTenue, fontSize: 12)),
        ],
      );
}

class _FilaReserva extends StatelessWidget {
  const _FilaReserva({required this.reserva, required this.mon});
  final Reserva reserva;
  final String mon;

  @override
  Widget build(BuildContext context) {
    final r = reserva;
    final total = r.totalConExtras.round();
    final sena = r.sena.clamp(0, total);
    final resto = total - sena; // lo que falta cobrar en efectivo
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.fromLTRB(12, 10, 12, 10),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: r.pagado ? lima.withOpacity(0.5) : trazo),
      ),
      child: Row(
        children: [
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('${r.horaInicio}–${r.horaFin}',
                  style: const TextStyle(
                      fontWeight: FontWeight.w800, fontSize: 13)),
              if (!r.traidaPorApp)
                const Text('propio',
                    style: TextStyle(color: textoTenue, fontSize: 10.5)),
            ],
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(r.jugador.isEmpty ? 'Cliente' : r.jugador,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(fontWeight: FontWeight.w700)),
                // Bono: no es plata fresca de hoy (ya se cobró al vender el
                // bono). Se muestra como cubierto, no como cobrado.
                Text(r.esBono ? 'Cubierto con bono · $mon 0' : '$mon $total',
                    style: TextStyle(
                        color: r.esBono
                            ? teal
                            : (r.pagado ? lima : textoTenueDe(context)),
                        fontWeight: FontWeight.w700,
                        fontSize: 12.5)),
                // Seña pagada por adelantado: el dueño solo cobra el resto.
                if (!r.esBono && !r.pagado && sena > 0)
                  Text('Seña $mon $sena pagada · cobra $mon $resto',
                      style: const TextStyle(
                          color: pino,
                          fontWeight: FontWeight.w700,
                          fontSize: 11)),
              ],
            ),
          ),
          // Marcar pagado / cobrado (el resto en efectivo). El bono no se
          // "des-paga": muestra una etiqueta fija en vez del botón.
          r.esBono
              ? const _EtiquetaBono()
              : r.pagado
              ? TextButton.icon(
                  onPressed: () => appState.marcarPago(r, pagado: false),
                  icon: const Icon(Icons.check_circle, size: 18, color: lima),
                  label: const Text('Pagado',
                      style: TextStyle(
                          color: lima, fontWeight: FontWeight.w800)),
                )
              : FilledButton(
                  style: FilledButton.styleFrom(
                      backgroundColor: lima,
                      foregroundColor: Colors.white,
                      padding: const EdgeInsets.symmetric(
                          horizontal: 14, vertical: 8)),
                  onPressed: () => appState.marcarPago(r, pagado: true),
                  child: Text(sena > 0 ? 'Cobrar $mon $resto' : 'Cobrar'),
                ),
        ],
      ),
    );
  }
}

/// Etiqueta fija para una reserva cubierta con bono (no se marca pagado/impago).
class _EtiquetaBono extends StatelessWidget {
  const _EtiquetaBono();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: teal.withOpacity(0.12),
        borderRadius: BorderRadius.circular(20),
      ),
      child: const Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.confirmation_number, size: 15, color: teal),
          SizedBox(width: 5),
          Text('Bono',
              style: TextStyle(color: teal, fontWeight: FontWeight.w800)),
        ],
      ),
    );
  }
}
