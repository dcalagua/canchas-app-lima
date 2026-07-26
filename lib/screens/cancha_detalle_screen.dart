import 'package:flutter/material.dart';

import '../data/reservas_repo.dart';
import '../models/models.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/chat_burbuja.dart';
import '../widgets/court_lines.dart';
import '../widgets/pago_tarjeta_sheet.dart';
import 'chat_screen.dart';
import 'login_google_sheet.dart';
import 'registrar_cancha_screen.dart';
import '../utils/moneda.dart';
import '../utils/ubicacion_share.dart';

/// Detalle de una cancha (estilo ficha de Airbnb) con selección de día/hora y
/// flujo de reserva. Demo sin backend: la reserva se guarda en memoria.
class CanchaDetalleScreen extends StatefulWidget {
  final Cancha cancha;
  const CanchaDetalleScreen({super.key, required this.cancha});

  @override
  State<CanchaDetalleScreen> createState() => _CanchaDetalleScreenState();
}

class _CanchaDetalleScreenState extends State<CanchaDetalleScreen> {
  String _dia = 'Hoy';
  String? _hora;

  Cancha get cancha => widget.cancha;
  Color get _color => colorDeporte(cancha.deporte);

  /// Horas reservables reales de ESTA cancha (apertura→cierre, paso = duración).
  /// Para "Hoy" se omiten las horas que ya pasaron.
  List<String> get _horas {
    int? desde;
    if (_dia == 'Hoy') {
      final n = DateTime.now();
      desde = n.hour * 60 + n.minute;
    }
    return cancha.horariosSlots(desdeMinutos: desde);
  }

  /// Fecha real (ISO) según el día elegido. Es la fuente de verdad de la reserva
  /// y del anti-doble-reserva; "Hoy/Mañana" es solo la etiqueta visible.
  String get _fechaIso {
    final base = DateTime.now();
    final d = _dia == 'Mañana' ? base.add(const Duration(days: 1)) : base;
    return '${d.year.toString().padLeft(4, '0')}-'
        '${d.month.toString().padLeft(2, '0')}-'
        '${d.day.toString().padLeft(2, '0')}';
  }

  bool _ocupada(String hora) {
    return appState.reservas.any((r) =>
        r.canchaId == cancha.id && r.fecha == _fechaIso && r.horaInicio == hora);
  }

  Future<void> _reservar() async {
    final hora = _hora;
    if (hora == null) return;

    // Navegar/buscar es libre; reservar exige login con Google.
    if (!await LoginGoogleSheet.mostrar(context, motivo: 'reservar tu cancha')) {
      return;
    }
    if (!mounted) return;

    final total = cancha.precioHora * cancha.duracionSlotMin / 60;
    // El efectivo (pago en la cancha) SOLO se ofrece si el dueño tiene saldo:
    // así PCG cobra su comisión de ese saldo. Sin saldo, el jugador paga online.
    final efectivo = appState.esDestacada(cancha);
    final confirmar = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Confirmar reserva'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('${cancha.nombre} · ${cancha.club}'),
            const SizedBox(height: 8),
            Text('$_dia · $hora a ${cancha.horaFinDe(hora)}'),
            const SizedBox(height: 8),
            Text('Total: ${cancha.monedaSimbolo} ${total.toStringAsFixed(2)}',
                style: TextStyle(
                    color: Theme.of(ctx).colorScheme.primary,
                    fontWeight: FontWeight.w700)),
            const SizedBox(height: 8),
            Text(
              efectivo
                  ? 'Reservas ahora y pagas en la cancha (efectivo). El club '
                      'confirma tu pago al llegar.'
                  : 'Pagas ahora por la app (Yape/tarjeta) para asegurar tu hora.',
              style: const TextStyle(fontSize: 12, color: Colors.grey),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(false),
            child: const Text('Cancelar'),
          ),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: coral),
            onPressed: () => Navigator.of(ctx).pop(true),
            child: const Text('Reservar'),
          ),
        ],
      ),
    );
    if (confirmar != true || !mounted) return;

    final messenger = ScaffoldMessenger.of(context);
    final nav = Navigator.of(context);
    // Sin saldo del dueño → el jugador paga online ANTES de reservar (ahí queda
    // la comisión de PCG). Si cancela o falla el pago, no se reserva.
    if (!efectivo) {
      final pagado = await PagoTarjeta.cobrar(
        context,
        monto: total.round(),
        concepto: 'Reserva · ${cancha.nombre} · $_dia $hora',
        email: appState.usuario?.email ?? '',
        moneda: cancha.monedaSimbolo,
      );
      if (!pagado || !mounted) return;
    }
    final res = await appState.agregarReservaJugador(
        cancha, _fechaIso, _dia, hora,
        // Con saldo → efectivo (comisión del saldo); sin saldo → online (ya se
        // cobró al jugador; se registra la liquidación / neto al dueño).
        cobro: efectivo ? 'efectivo' : 'online');
    if (!mounted) return;

    if (res == ResultadoReserva.ocupado) {
      setState(() => _hora = null); // libera la selección; la grilla se refresca
      messenger.showSnackBar(const SnackBar(
        backgroundColor: Colors.redAccent,
        content: Text('Ese horario acaba de tomarse. Elige otro, por favor.'),
      ));
      return;
    }

    nav.pop(); // vuelve al mapa
    messenger.showSnackBar(SnackBar(
      backgroundColor: verdeCancha,
      content:
          Text('✅ Reserva confirmada en ${cancha.nombre} · $_dia $hora'),
    ));
  }

  /// Chat interno con el DUEÑO de la cancha. Exige cuenta (portón único).
  Future<void> _chatearConDueno() async {
    if (!await LoginGoogleSheet.mostrar(context,
        motivo: 'escribirle al dueño')) {
      return;
    }
    if (!mounted) return;
    Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => ChatScreen(
        academiaId: '',
        cuentaEmail: appState.usuario!.email,
        titulo: cancha.club.isNotEmpty ? cancha.club : cancha.nombre,
        soyProfe: false,
        tipo: 'cancha',
        refId: cancha.dueno,
      ),
    ));
  }

  @override
  Widget build(BuildContext context) {
    final email = appState.usuario?.email ?? '';
    final soyDueno = email.isNotEmpty && cancha.dueno == email;
    return Scaffold(
      // Globo de chat con el dueño (si hay dueño y no soy yo): siempre a la mano.
      floatingActionButton: (cancha.dueno.isNotEmpty && !soyDueno)
          ? ChatBurbuja(logoUrl: cancha.fotoUrl, onTap: _chatearConDueno)
          : null,
      body: CustomScrollView(
        slivers: [
          SliverAppBar(
            expandedHeight: 220,
            pinned: true,
            backgroundColor: _color,
            foregroundColor: Colors.white,
            flexibleSpace: FlexibleSpaceBar(
              title: Text(
                cancha.nombre,
                style: const TextStyle(
                    fontWeight: FontWeight.bold, color: Colors.white),
              ),
              background: Container(
                decoration: BoxDecoration(
                  gradient: gradienteDeporte(cancha.deporte),
                ),
                child: Stack(
                  children: [
                    const Positioned.fill(child: CourtLines(opacity: 0.5)),
                    Center(
                      child: Icon(
                        iconoDeporte(cancha.deporte),
                        size: 90,
                        color: Colors.white.withOpacity(0.9),
                      ),
                    ),
                    if (cancha.clubFundador)
                      const Positioned(
                        top: 70,
                        right: 16,
                        child: _Badge('★ Club Fundador'),
                      ),
                  ],
                ),
              ),
            ),
          ),
          SliverToBoxAdapter(
            child: Padding(
              padding: const EdgeInsets.all(20),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      _Pill(cancha.deporte.etiqueta, _color),
                      if (cancha.zonaMostrable.isNotEmpty) ...[
                        const SizedBox(width: 8),
                        _Pill(cancha.zonaMostrable, Colors.black54),
                      ],
                      const Spacer(),
                      if (cancha.registrada) ...[
                        Text(
                          '${cancha.monedaSimbolo} ${cancha.precioHora.toStringAsFixed(2)}',
                          style: TextStyle(
                              fontWeight: FontWeight.bold,
                              fontSize: 22,
                              color: Theme.of(context).colorScheme.primary),
                        ),
                        const Text(' /hora',
                            style: TextStyle(color: Colors.grey)),
                      ],
                    ],
                  ),
                  const SizedBox(height: 8),
                  _FilaUbicacion(cancha: cancha),
                  const SizedBox(height: 16),
                  if (!cancha.registrada)
                    _PanelDescubierta(cancha: cancha)
                  else ...[
                    Text(
                      'Cancha de ${cancha.deporte.etiqueta.toLowerCase()}'
                      '${cancha.zonaMostrable.isNotEmpty ? ' en ${cancha.zonaMostrable}' : ''}. '
                      'Reserva tu hora y juega con quien quieras, a tu nivel. '
                      'Reservas online y pagas en la cancha (efectivo).',
                      style: const TextStyle(height: 1.4),
                    ),
                    const SizedBox(height: 24),
                    const Text('Elige el día',
                        style: TextStyle(
                            fontWeight: FontWeight.bold, fontSize: 16)),
                    const SizedBox(height: 10),
                    Row(
                      children: [
                        _DiaChip('Hoy', _dia == 'Hoy',
                            () => setState(() {
                                  _dia = 'Hoy';
                                  _hora = null;
                                })),
                        const SizedBox(width: 10),
                        _DiaChip('Mañana', _dia == 'Mañana',
                            () => setState(() {
                                  _dia = 'Mañana';
                                  _hora = null;
                                })),
                      ],
                    ),
                    const SizedBox(height: 22),
                    const Text('Elige la hora',
                        style: TextStyle(
                            fontWeight: FontWeight.bold, fontSize: 16)),
                    const SizedBox(height: 4),
                    const Text(
                      'Las mañanas suelen estar más libres.',
                      style: TextStyle(color: Colors.grey, fontSize: 12),
                    ),
                    const SizedBox(height: 12),
                    if (_horas.isEmpty)
                      Text(
                        _dia == 'Hoy'
                            ? 'No quedan horarios para hoy. Elige "Mañana".'
                            : 'Sin horarios disponibles.',
                        style: const TextStyle(color: Colors.grey),
                      )
                    else
                      Wrap(
                        spacing: 10,
                        runSpacing: 10,
                        children: [
                          for (final h in _horas)
                            _HoraChip(
                              hora: h,
                              ocupada: _ocupada(h),
                              seleccionada: _hora == h,
                              onTap: () => setState(() => _hora = h),
                            ),
                        ],
                      ),
                  ],
                  const SizedBox(height: 100),
                ],
              ),
            ),
          ),
        ],
      ),
      bottomSheet: cancha.registrada
          ? _BarraReserva(
              habilitado: _hora != null,
              textoHora: _hora,
              dia: _dia,
              onReservar: _reservar,
            )
          : null,
    );
  }
}

class _BarraReserva extends StatelessWidget {
  final bool habilitado;
  final String? textoHora;
  final String dia;
  final VoidCallback onReservar;
  const _BarraReserva({
    required this.habilitado,
    required this.textoHora,
    required this.dia,
    required this.onReservar,
  });

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.fromLTRB(20, 12, 20, 20),
      decoration: BoxDecoration(
        color: cs.surface,
        boxShadow: const [BoxShadow(color: Colors.black12, blurRadius: 8)],
      ),
      child: Row(
        children: [
          Expanded(
            child: Text(
              habilitado
                  ? 'Reservar $dia · $textoHora'
                  : 'Elige una hora disponible',
              style: TextStyle(
                color: habilitado ? cs.onSurface : Colors.grey,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
          FilledButton(
            style: FilledButton.styleFrom(
              backgroundColor: lima,
              foregroundColor: Colors.white,
              padding: const EdgeInsets.symmetric(horizontal: 28, vertical: 14),
            ),
            onPressed: habilitado ? onReservar : null,
            child: const Text('Reservar'),
          ),
        ],
      ),
    );
  }
}

class _DiaChip extends StatelessWidget {
  final String texto;
  final bool activo;
  final VoidCallback onTap;
  const _DiaChip(this.texto, this.activo, this.onTap);

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 22, vertical: 12),
        decoration: BoxDecoration(
          color: activo ? verdeCancha : cs.surface,
          borderRadius: BorderRadius.circular(30),
          border: Border.all(color: verdeCancha),
        ),
        child: Text(
          texto,
          style: TextStyle(
            color: activo ? Colors.white : cs.primary,
            fontWeight: FontWeight.w600,
          ),
        ),
      ),
    );
  }
}

class _HoraChip extends StatelessWidget {
  final String hora;
  final bool ocupada;
  final bool seleccionada;
  final VoidCallback onTap;
  const _HoraChip({
    required this.hora,
    required this.ocupada,
    required this.seleccionada,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    if (ocupada) {
      return Container(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 11),
        decoration: BoxDecoration(
          color: const Color(0xFFEDEDED),
          borderRadius: BorderRadius.circular(12),
        ),
        child: Text(
          hora,
          style: const TextStyle(
            color: Colors.grey,
            decoration: TextDecoration.lineThrough,
          ),
        ),
      );
    }
    final cs = Theme.of(context).colorScheme;
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 11),
        decoration: BoxDecoration(
          color: seleccionada ? verdeCancha : cs.surface,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(
              color: seleccionada ? verdeCancha : const Color(0xFFCDD8D1)),
        ),
        child: Text(
          hora,
          style: TextStyle(
            color: seleccionada ? Colors.white : cs.onSurface,
            fontWeight: FontWeight.w600,
          ),
        ),
      ),
    );
  }
}

/// Panel para una cancha REAL descubierta en Google que aún no está en
/// Pichangol. Invita al dueño a reclamarla/registrarla (palanca de crecimiento).
class _PanelDescubierta extends StatelessWidget {
  final Cancha cancha;
  const _PanelDescubierta({required this.cancha});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFFEAF6EF),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: verdeClaro),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Row(
            children: [
              Icon(Icons.travel_explore, color: verdeOscuro),
              SizedBox(width: 8),
              Expanded(
                child: Text(
                  'Encontramos esta cancha en Google Maps',
                  style: TextStyle(
                      fontWeight: FontWeight.bold, color: verdeOscuro),
                ),
              ),
            ],
          ),
          const SizedBox(height: 10),
          const Text(
            'Todavía no está activa en Pichangol, así que aún no se puede '
            'reservar online. ¿Es tuya? Regístrala y empieza a recibir '
            'reservas.',
            style: TextStyle(height: 1.4),
          ),
          const SizedBox(height: 14),
          SizedBox(
            width: double.infinity,
            child: FilledButton.icon(
              style: FilledButton.styleFrom(backgroundColor: coral),
              onPressed: () => Navigator.of(context).push(
                MaterialPageRoute(
                    builder: (_) => const RegistrarCanchaScreen()),
              ),
              icon: const Icon(Icons.add_location_alt),
              label: const Text('Reclamar / registrar esta cancha'),
            ),
          ),
        ],
      ),
    );
  }
}

/// Ubicación de la cancha: dirección REAL (tocar = abrir en Google Maps) + botón
/// para compartir/“cómo llegar”. Nunca inventa distrito: si no hay dirección ni
/// barrio real, cae al nombre del club (y el mapa siempre funciona por GPS).
class _FilaUbicacion extends StatelessWidget {
  const _FilaUbicacion({required this.cancha});
  final Cancha cancha;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final dir = (cancha.direccion ?? '').trim();
    final zona = cancha.zonaMostrable;
    final texto = dir.isNotEmpty ? dir : (zona.isNotEmpty ? zona : cancha.club);
    final tituloShare = dir.isNotEmpty ? '${cancha.nombre} · $dir' : cancha.nombre;
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(Icons.place_outlined, size: 20, color: cs.primary),
        const SizedBox(width: 6),
        Expanded(
          child: InkWell(
            onTap: () => UbicacionShare.abrirMapa(cancha.ubicacion),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(texto,
                    style: const TextStyle(
                        color: Color(0xFF444444), fontSize: 14, height: 1.3)),
                if (dir.isNotEmpty && zona.isNotEmpty && zona != dir)
                  Padding(
                    padding: const EdgeInsets.only(top: 2),
                    child: Text(zona,
                        style: const TextStyle(
                            color: Colors.grey, fontSize: 12.5)),
                  ),
                const SizedBox(height: 2),
                Text('Ver en el mapa',
                    style: TextStyle(
                        color: cs.primary,
                        fontSize: 12.5,
                        fontWeight: FontWeight.w700)),
              ],
            ),
          ),
        ),
        TextButton.icon(
          onPressed: () => UbicacionShare.menu(context,
              punto: cancha.ubicacion, titulo: tituloShare),
          icon: const Icon(Icons.ios_share, size: 18),
          label: const Text('Compartir'),
          style: TextButton.styleFrom(foregroundColor: cs.primary),
        ),
      ],
    );
  }
}

class _Pill extends StatelessWidget {
  final String texto;
  final Color color;
  const _Pill(this.texto, this.color);

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: color,
        borderRadius: BorderRadius.circular(20),
      ),
      child: Text(
        texto,
        style: const TextStyle(
            color: Colors.white, fontSize: 12, fontWeight: FontWeight.w600),
      ),
    );
  }
}

class _Badge extends StatelessWidget {
  final String texto;
  const _Badge(this.texto);

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(
        color: arena,
        borderRadius: BorderRadius.circular(20),
      ),
      child: Text(
        texto,
        style: const TextStyle(
            color: Colors.white, fontSize: 12, fontWeight: FontWeight.w700),
      ),
    );
  }
}
