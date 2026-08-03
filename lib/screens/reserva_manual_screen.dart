import 'dart:async';

import 'package:flutter/material.dart';

import '../data/perfiles_repo.dart';
import '../data/reservas_repo.dart';
import '../models/models.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/cargando_pichangol.dart';

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
  // Cliente = usuario REGISTRADO del app (no texto libre): se elige con el
  // buscador y se liga la reserva a su cuenta.
  String _clienteEmail = '';
  String _clienteNombre = '';
  String _clienteFoto = '';
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
    _telefono.dispose();
    _precio.dispose();
    super.dispose();
  }

  /// Abre el buscador de usuarios registrados y fija el cliente elegido.
  Future<void> _elegirCliente() async {
    final sel = await showModalBottomSheet<Map<String, dynamic>>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => const _BuscadorClienteSheet(),
    );
    if (sel == null || !mounted) return;
    setState(() {
      _clienteEmail = (sel['email'] ?? '').toString().toLowerCase().trim();
      _clienteNombre = (sel['nombre'] ?? '').toString().trim();
      _clienteFoto = (sel['foto_url'] ?? '').toString().trim();
      final cel = (sel['celular'] ?? '').toString().trim();
      if (cel.isNotEmpty) _telefono.text = cel;
    });
  }

  void _sugerirPrecio() {
    final c = _cancha;
    if (c == null) return;
    // Precio efectivo del slot: aplica la hora feliz y el descuento puntual del
    // dueño para la hora elegida (si ya eligió una).
    final p = _hora != null
        ? appState.precioSlotEfectivo(c, _isoFecha, _hora!)
        : (c.precioHora * c.duracionSlotMin / 60).round();
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
    // Fecha REAL del slot: los de madrugada (horario que cruza medianoche) están
    // tomados/guardados en el día siguiente. Así se marca ocupado correctamente.
    final f = c.fechaRealSlot(_isoFecha, hora);
    final reservado = appState.reservas.any((r) =>
        r.canchaId == c.id && r.fecha == f && r.horaInicio == hora);
    return reservado || appState.estaBloqueado(c.id, f, hora);
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
    if (_clienteEmail.isEmpty) {
      _aviso('Elige al cliente (debe estar registrado en el app).');
      return;
    }
    final precio = int.tryParse(_precio.text.trim());
    if (_guardando) return;
    setState(() => _guardando = true);
    ResultadoReserva res;
    try {
      res = await conPreload(
          context,
          () => appState.agregarReservaManual(
                c,
                _isoFecha,
                _diaLabel,
                _hora!,
                nombreCliente:
                    _clienteNombre.isNotEmpty ? _clienteNombre : _clienteEmail,
                telefono: _telefono.text,
                clienteEmail: _clienteEmail,
                pagado: _pagado,
                precioOverride: precio,
              ),
          texto: 'Registrando…');
    } finally {
      if (mounted) setState(() => _guardando = false);
    }
    if (!mounted) return;
    if (res == ResultadoReserva.ocupado) {
      _aviso('Esa hora ya está reservada. Elige otra.');
      setState(() => _hora = null);
      return;
    }
    // ok / sinConexion / error → se guardó local igual (fail-safe offline).
    final quien = _clienteNombre.isNotEmpty ? _clienteNombre : _clienteEmail;
    Navigator.of(context).pop(true);
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('Reserva de $quien registrada.'),
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
                  onElegir: (h) => setState(() {
                    _hora = h;
                    _sugerirPrecio(); // precio del slot (con descuento si tiene)
                  }),
                ),
                const SizedBox(height: 18),
                _Etiqueta('Cliente'),
                const SizedBox(height: 6),
                _SelectorCliente(
                  email: _clienteEmail,
                  nombre: _clienteNombre,
                  foto: _clienteFoto,
                  onElegir: _elegirCliente,
                  onQuitar: () => setState(() {
                    _clienteEmail = '';
                    _clienteNombre = '';
                    _clienteFoto = '';
                  }),
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
                    icon: const Icon(Icons.check),
                    label: const Text('Registrar reserva',
                        style: TextStyle(
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

/// Casilla del cliente elegido: si no hay nadie, invita a buscar; si ya se
/// eligió, muestra su avatar/nombre/correo y permite cambiarlo.
class _SelectorCliente extends StatelessWidget {
  const _SelectorCliente({
    required this.email,
    required this.nombre,
    required this.foto,
    required this.onElegir,
    required this.onQuitar,
  });
  final String email;
  final String nombre;
  final String foto;
  final VoidCallback onElegir;
  final VoidCallback onQuitar;

  @override
  Widget build(BuildContext context) {
    final vacio = email.isEmpty;
    final mostrar = nombre.isNotEmpty ? nombre : email;
    return InkWell(
      onTap: onElegir,
      borderRadius: BorderRadius.circular(14),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
        decoration: BoxDecoration(
          color: Theme.of(context).colorScheme.surface,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: const Color(0xFFE4E4E4)),
        ),
        child: vacio
            ? Row(
                children: [
                  const Icon(Icons.person_search, color: textoTenue),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Text('Buscar cliente registrado…',
                        style: TextStyle(color: textoTenueDe(context))),
                  ),
                  const Icon(Icons.chevron_right, color: textoTenue),
                ],
              )
            : Row(
                children: [
                  CircleAvatar(
                    radius: 20,
                    backgroundColor: teal,
                    backgroundImage:
                        foto.isNotEmpty ? NetworkImage(foto) : null,
                    child: foto.isEmpty
                        ? Text(
                            mostrar.isNotEmpty
                                ? mostrar[0].toUpperCase()
                                : '?',
                            style: const TextStyle(
                                color: Colors.white,
                                fontWeight: FontWeight.w800))
                        : null,
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(mostrar,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(
                                fontWeight: FontWeight.w700, fontSize: 15)),
                        if (nombre.isNotEmpty)
                          Text(email,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: const TextStyle(
                                  color: textoTenue, fontSize: 12)),
                      ],
                    ),
                  ),
                  IconButton(
                    tooltip: 'Cambiar',
                    icon: const Icon(Icons.close, color: textoTenue),
                    onPressed: onQuitar,
                  ),
                ],
              ),
      ),
    );
  }
}

/// Hoja para BUSCAR un usuario registrado (por nombre o correo). Devuelve el
/// perfil elegido {email, nombre, foto_url, celular} vía `Navigator.pop`.
class _BuscadorClienteSheet extends StatefulWidget {
  const _BuscadorClienteSheet();

  @override
  State<_BuscadorClienteSheet> createState() => _BuscadorClienteSheetState();
}

class _BuscadorClienteSheetState extends State<_BuscadorClienteSheet> {
  final _q = TextEditingController();
  Timer? _debounce;
  bool _buscando = false;
  List<Map<String, dynamic>> _resultados = const [];

  @override
  void dispose() {
    _debounce?.cancel();
    _q.dispose();
    super.dispose();
  }

  void _onCambio(String v) {
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 350), () => _buscar(v));
  }

  Future<void> _buscar(String v) async {
    final q = v.trim();
    if (q.length < 2) {
      setState(() {
        _resultados = const [];
        _buscando = false;
      });
      return;
    }
    setState(() => _buscando = true);
    final r = await PerfilesRepo.buscar(q);
    if (!mounted) return;
    setState(() {
      _resultados = r;
      _buscando = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    final inset = MediaQuery.of(context).viewInsets.bottom;
    final hayQuery = _q.text.trim().length >= 2;
    return Padding(
      padding: EdgeInsets.only(bottom: inset),
      child: DraggableScrollableSheet(
        expand: false,
        initialChildSize: 0.7,
        minChildSize: 0.5,
        maxChildSize: 0.92,
        builder: (context, scroll) => Container(
          decoration: BoxDecoration(
            color: Theme.of(context).scaffoldBackgroundColor,
            borderRadius:
                const BorderRadius.vertical(top: Radius.circular(20)),
          ),
          child: Column(
            children: [
              const SizedBox(height: 10),
              Container(
                width: 40,
                height: 4,
                decoration: BoxDecoration(
                    color: trazo,
                    borderRadius: BorderRadius.circular(999)),
              ),
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
                child: TextField(
                  controller: _q,
                  autofocus: true,
                  onChanged: _onCambio,
                  decoration: InputDecoration(
                    hintText: 'Nombre o correo del cliente…',
                    prefixIcon: const Icon(Icons.search),
                    filled: true,
                    border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(14),
                        borderSide: BorderSide.none),
                  ),
                ),
              ),
              Expanded(
                child: _buscando
                    ? const Center(
                        child: CircularProgressIndicator(color: lima))
                    : !hayQuery
                        ? _mensaje(context,
                            'Escribe el nombre o correo del cliente. Debe haber '
                            'entrado al app al menos una vez.')
                        : _resultados.isEmpty
                            ? _mensaje(context,
                                'No se encontró a nadie. El cliente debe estar '
                                'registrado en el app.')
                            : ListView.separated(
                                controller: scroll,
                                itemCount: _resultados.length,
                                separatorBuilder: (_, __) => Divider(
                                    height: 1, color: trazo.withOpacity(0.5)),
                                itemBuilder: (_, i) {
                                  final p = _resultados[i];
                                  final email =
                                      (p['email'] ?? '').toString();
                                  final nombre =
                                      (p['nombre'] ?? '').toString();
                                  final foto =
                                      (p['foto_url'] ?? '').toString();
                                  final mostrar =
                                      nombre.isNotEmpty ? nombre : email;
                                  return ListTile(
                                    onTap: () => Navigator.pop(context, p),
                                    leading: CircleAvatar(
                                      radius: 22,
                                      backgroundColor: teal,
                                      backgroundImage: foto.isNotEmpty
                                          ? NetworkImage(foto)
                                          : null,
                                      child: foto.isEmpty
                                          ? Text(
                                              mostrar.isNotEmpty
                                                  ? mostrar[0].toUpperCase()
                                                  : '?',
                                              style: const TextStyle(
                                                  color: Colors.white,
                                                  fontWeight:
                                                      FontWeight.w800))
                                          : null,
                                    ),
                                    title: Text(mostrar,
                                        maxLines: 1,
                                        overflow: TextOverflow.ellipsis,
                                        style: const TextStyle(
                                            fontWeight: FontWeight.w700)),
                                    subtitle: nombre.isNotEmpty
                                        ? Text(email,
                                            maxLines: 1,
                                            overflow: TextOverflow.ellipsis,
                                            style: const TextStyle(
                                                color: textoTenue,
                                                fontSize: 12))
                                        : null,
                                  );
                                },
                              ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _mensaje(BuildContext context, String texto) => Center(
        child: Padding(
          padding: const EdgeInsets.all(30),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.person_search, size: 54, color: textoTenue),
              const SizedBox(height: 12),
              Text(texto,
                  textAlign: TextAlign.center,
                  style: const TextStyle(color: textoTenue)),
            ],
          ),
        ),
      );
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
              'Anota aquí a tu cliente de siempre (llamó o vino). Debe tener '
              'cuenta en el app: la reserva le aparece también a él. Ocupa la '
              'hora para que nadie reserve encima. No genera comisión.',
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
                  // Theme-aware: seleccionado tiñe con el acento; libre queda
                  // transparente con borde; ocupado, atenuado. Sin blanco fijo.
                  color: taken
                      ? textoTenueDe(context).withOpacity(0.12)
                      : sel
                          ? cs.primary
                          : Colors.transparent,
                  borderRadius: BorderRadius.circular(999),
                  border: Border.all(
                    color: sel
                        ? cs.primary
                        : textoTenueDe(context).withOpacity(0.4),
                  ),
                ),
                child: Text(
                  h,
                  style: TextStyle(
                    fontSize: 13.5,
                    fontWeight: FontWeight.w700,
                    color: taken
                        ? textoTenueDe(context)
                        : sel
                            ? Colors.white
                            : cs.onSurface,
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
