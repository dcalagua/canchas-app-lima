import 'package:flutter/material.dart';

import '../data/reservas_repo.dart';
import '../models/models.dart';
import '../state/app_state.dart';
import '../theme.dart';

/// RESERVA MANUAL del dueño: registra la reserva de un cliente que llamó por
/// teléfono/WhatsApp (digitaliza el cuaderno). Queda como `traidaPorApp: false`
/// (cliente propio, fuera de comisión) y OCUPA el slot igual que una reserva de
/// la app, para que nadie pueda reservar encima (anti doble-reserva).
class ReservaManualScreen extends StatefulWidget {
  const ReservaManualScreen({super.key, this.canchaInicial});

  /// Cancha preseleccionada (si se abre desde una cancha concreta).
  final Cancha? canchaInicial;

  @override
  State<ReservaManualScreen> createState() => _ReservaManualScreenState();
}

class _ReservaManualScreenState extends State<ReservaManualScreen> {
  // Se guarda el ID (no el objeto): misCanchas reconstruye instancias y Cancha
  // no define ==, así el Dropdown por objeto podría no encontrar el value.
  String? _canchaId;
  DateTime _fecha = _hoy();
  String? _hora;
  final _nombre = TextEditingController();
  final _telefono = TextEditingController();
  final _precio = TextEditingController();
  bool _pagado = false;
  bool _guardando = false;

  static DateTime _hoy() {
    final n = DateTime.now();
    return DateTime(n.year, n.month, n.day);
  }

  /// Cancha actual resuelta desde el id (o null si ya no existe).
  Cancha? get _cancha {
    final id = _canchaId;
    if (id == null) return null;
    for (final c in appState.misCanchas) {
      if (c.id == id) return c;
    }
    return null;
  }

  @override
  void initState() {
    super.initState();
    final mias = appState.misCanchas;
    _canchaId =
        widget.canchaInicial?.id ?? (mias.isNotEmpty ? mias.first.id : null);
    _sugerirPrecio();
  }

  @override
  void dispose() {
    _nombre.dispose();
    _telefono.dispose();
    _precio.dispose();
    super.dispose();
  }

  void _sugerirPrecio() {
    final c = _cancha;
    if (c == null) return;
    final p = (c.precioHora * c.duracionSlotMin / 60).round();
    _precio.text = p.toString();
  }

  String get _isoFecha {
    final d = _fecha;
    return '${d.year.toString().padLeft(4, '0')}-'
        '${d.month.toString().padLeft(2, '0')}-'
        '${d.day.toString().padLeft(2, '0')}';
  }

  /// Etiqueta de día para la agenda ("Hoy"/"Mañana"/ISO). Debe mapear el día de
  /// hoy a "Hoy" para que la agenda del panel enlace la reserva.
  String get _diaLabel {
    final hoy = _hoy();
    final man = hoy.add(const Duration(days: 1));
    if (_fecha == hoy) return 'Hoy';
    if (_fecha == man) return 'Mañana';
    return _isoFecha;
  }

  bool _ocupada(String hora) {
    final c = _cancha;
    if (c == null) return true;
    final reservado = appState.reservas.any((r) =>
        r.canchaId == c.id && r.fecha == _isoFecha && r.horaInicio == hora);
    return reservado || appState.estaBloqueado(c.id, _isoFecha, hora);
  }

  Future<void> _elegirFecha() async {
    final hoy = _hoy();
    final d = await showDatePicker(
      context: context,
      initialDate: _fecha,
      firstDate: hoy,
      lastDate: hoy.add(const Duration(days: 60)),
    );
    if (d != null) {
      setState(() {
        _fecha = DateTime(d.year, d.month, d.day);
        _hora = null; // el slot elegido puede no aplicar a la nueva fecha
      });
    }
  }

  Future<void> _guardar() async {
    final c = _cancha;
    if (c == null) return;
    if (_hora == null) {
      _aviso('Elige una hora.');
      return;
    }
    if (_nombre.text.trim().isEmpty) {
      _aviso('Escribe el nombre del cliente.');
      return;
    }
    final precio = int.tryParse(_precio.text.trim());
    setState(() => _guardando = true);
    final res = await appState.agregarReservaManual(
      c,
      _isoFecha,
      _diaLabel,
      _hora!,
      nombreCliente: _nombre.text,
      telefono: _telefono.text,
      pagado: _pagado,
      precioOverride: precio,
    );
    if (!mounted) return;
    setState(() => _guardando = false);
    if (res == ResultadoReserva.ocupado) {
      _aviso('Esa hora ya está reservada. Elige otra.');
      setState(() => _hora = null);
      return;
    }
    // ok / sinConexion / error → se guardó local igual (fail-safe offline).
    Navigator.of(context).pop(true);
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('Reserva de ${_nombre.text.trim()} registrada.'),
        backgroundColor: lima,
      ),
    );
  }

  void _aviso(String m) {
    ScaffoldMessenger.of(context)
        .showSnackBar(SnackBar(content: Text(m)));
  }

  @override
  Widget build(BuildContext context) {
    final mias = appState.misCanchas;
    final t = Theme.of(context).textTheme;
    return Scaffold(
      appBar: AppBar(title: const Text('Reserva manual')),
      body: mias.isEmpty
          ? Center(
              child: Padding(
                padding: const EdgeInsets.all(32),
                child: Text(
                  'Primero registra una cancha para poder anotar reservas.',
                  textAlign: TextAlign.center,
                  style: t.bodyLarge?.copyWith(color: textoTenueDe(context)),
                ),
              ),
            )
          : ListView(
              padding: const EdgeInsets.fromLTRB(18, 14, 18, 28),
              children: [
                _Nota(),
                const SizedBox(height: 16),
                _Etiqueta('Cancha'),
                const SizedBox(height: 6),
                DropdownButtonFormField<String>(
                  value: _canchaId,
                  isExpanded: true,
                  decoration: _dec(),
                  items: [
                    for (final c in mias)
                      DropdownMenuItem(
                        value: c.id,
                        child: Text(
                          c.club.isNotEmpty ? '${c.club} · ${c.nombre}' : c.nombre,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                  ],
                  onChanged: (id) => setState(() {
                    _canchaId = id;
                    _hora = null;
                    _sugerirPrecio();
                  }),
                ),
                const SizedBox(height: 16),
                _Etiqueta('Fecha'),
                const SizedBox(height: 6),
                InkWell(
                  onTap: _elegirFecha,
                  borderRadius: BorderRadius.circular(14),
                  child: InputDecorator(
                    decoration: _dec(),
                    child: Row(
                      children: [
                        const Icon(Icons.calendar_month, size: 20),
                        const SizedBox(width: 10),
                        Text(_diaLabel == _isoFecha
                            ? _isoFecha
                            : '$_diaLabel · $_isoFecha'),
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 16),
                _Etiqueta('Hora'),
                const SizedBox(height: 8),
                _GrillaHoras(
                  slots: _cancha?.horariosSlots() ?? const [],
                  seleccion: _hora,
                  ocupada: _ocupada,
                  onElegir: (h) => setState(() => _hora = h),
                ),
                const SizedBox(height: 18),
                _Etiqueta('Cliente'),
                const SizedBox(height: 6),
                TextField(
                  controller: _nombre,
                  textCapitalization: TextCapitalization.words,
                  decoration: _dec(hint: 'Nombre del cliente'),
                ),
                const SizedBox(height: 10),
                TextField(
                  controller: _telefono,
                  keyboardType: TextInputType.phone,
                  decoration:
                      _dec(hint: 'Teléfono (opcional)', icono: Icons.phone),
                ),
                const SizedBox(height: 16),
                _Etiqueta('Precio'),
                const SizedBox(height: 6),
                TextField(
                  controller: _precio,
                  keyboardType: TextInputType.number,
                  decoration: _dec(
                      hint: 'Monto',
                      prefix: '${_cancha?.monedaSimbolo ?? 'S/'} '),
                ),
                const SizedBox(height: 12),
                SwitchListTile.adaptive(
                  value: _pagado,
                  onChanged: (v) => setState(() => _pagado = v),
                  contentPadding: EdgeInsets.zero,
                  activeColor: lima,
                  title: const Text('Ya pagó'),
                  subtitle: Text(
                    _pagado
                        ? 'Se registra como cobrado.'
                        : 'Queda como “por cobrar” en tu caja.',
                    style: t.bodySmall?.copyWith(color: textoTenueDe(context)),
                  ),
                ),
                const SizedBox(height: 18),
                SizedBox(
                  height: 52,
                  child: FilledButton.icon(
                    style: FilledButton.styleFrom(
                      backgroundColor: lima,
                      shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(14)),
                    ),
                    onPressed: _guardando ? null : _guardar,
                    icon: _guardando
                        ? const SizedBox(
                            width: 20,
                            height: 20,
                            child: CircularProgressIndicator(
                                strokeWidth: 2, color: Colors.white))
                        : const Icon(Icons.check),
                    label: Text(_guardando ? 'Guardando…' : 'Registrar reserva',
                        style: const TextStyle(
                            fontWeight: FontWeight.w700, fontSize: 16)),
                  ),
                ),
              ],
            ),
    );
  }

  InputDecoration _dec({String? hint, IconData? icono, String? prefix}) {
    return InputDecoration(
      hintText: hint,
      prefixIcon: icono != null ? Icon(icono) : null,
      prefixText: prefix,
      isDense: true,
      filled: true,
      fillColor: Theme.of(context).colorScheme.surface,
      contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(14),
        borderSide: const BorderSide(color: Color(0xFFE4E4E4)),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(14),
        borderSide: const BorderSide(color: Color(0xFFE4E4E4)),
      ),
    );
  }
}

class _Etiqueta extends StatelessWidget {
  const _Etiqueta(this.texto);
  final String texto;
  @override
  Widget build(BuildContext context) => Text(texto,
      style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 14));
}

/// Aviso de que la reserva manual NO genera comisión (cliente propio).
class _Nota extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: limaSuave,
        borderRadius: BorderRadius.circular(14),
      ),
      child: Row(
        children: [
          const Icon(Icons.info_outline, size: 18, color: bosque),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              'Anota aquí a tu cliente de siempre (llamó o vino). Ocupa la hora '
              'para que nadie reserve encima. No genera comisión.',
              style: TextStyle(
                  fontSize: 12.5,
                  color: bosque,
                  fontWeight: FontWeight.w600,
                  height: 1.25),
            ),
          ),
        ],
      ),
    );
  }
}

/// Grilla de horas seleccionable; deshabilita las ocupadas/bloqueadas.
class _GrillaHoras extends StatelessWidget {
  const _GrillaHoras({
    required this.slots,
    required this.seleccion,
    required this.ocupada,
    required this.onElegir,
  });
  final List<String> slots;
  final String? seleccion;
  final bool Function(String) ocupada;
  final ValueChanged<String> onElegir;

  @override
  Widget build(BuildContext context) {
    if (slots.isEmpty) {
      return Text('Esta cancha no tiene horarios configurados.',
          style: TextStyle(color: textoTenueDe(context)));
    }
    final cs = Theme.of(context).colorScheme;
    return Wrap(
      spacing: 8,
      runSpacing: 8,
      children: [
        for (final h in slots)
          Builder(builder: (context) {
            final taken = ocupada(h);
            final sel = h == seleccion;
            return GestureDetector(
              onTap: taken ? null : () => onElegir(h),
              child: Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 14, vertical: 9),
                decoration: BoxDecoration(
                  color: taken
                      ? const Color(0xFFF0F0F0)
                      : sel
                          ? cs.primary
                          : Colors.white,
                  borderRadius: BorderRadius.circular(999),
                  border: Border.all(
                    color: sel ? cs.primary : const Color(0xFFE4E4E4),
                  ),
                ),
                child: Text(
                  h,
                  style: TextStyle(
                    fontSize: 13.5,
                    fontWeight: FontWeight.w700,
                    color: taken
                        ? const Color(0xFFBDBDBD)
                        : sel
                            ? Colors.white
                            : const Color(0xFF222222),
                    decoration:
                        taken ? TextDecoration.lineThrough : TextDecoration.none,
                  ),
                ),
              ),
            );
          }),
      ],
    );
  }
}
