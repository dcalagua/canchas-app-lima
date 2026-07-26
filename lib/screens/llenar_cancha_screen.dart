import 'package:flutter/material.dart';

import '../data/mensajes_repo.dart';
import '../models/mensaje.dart';
import '../models/models.dart';
import '../services/whatsapp_link.dart';
import '../state/app_state.dart';
import '../theme.dart';

/// LLENAR LA CANCHA VACÍA: el dueño ve las horas LIBRES de hoy/mañana y con un
/// toque las AVISA a sus clientes — por la app (chat + push) a los que tienen
/// cuenta, y por WhatsApp a los que no. Convierte horas muertas en reservas.
class LlenarCanchaScreen extends StatefulWidget {
  const LlenarCanchaScreen({super.key, this.canchaInicial});
  final Cancha? canchaInicial;

  @override
  State<LlenarCanchaScreen> createState() => _LlenarCanchaScreenState();
}

class _LlenarCanchaScreenState extends State<LlenarCanchaScreen> {
  String? _canchaId;
  int _dia = 0; // 0 = hoy, 1 = mañana
  final _sel = <String>{};
  int _descuento = 0; // % de descuento REAL para las horas seleccionadas
  final _promo = TextEditingController();
  bool _avisando = false;

  @override
  void initState() {
    super.initState();
    final mias = appState.misCanchas;
    _canchaId =
        widget.canchaInicial?.id ?? (mias.isNotEmpty ? mias.first.id : null);
  }

  @override
  void dispose() {
    _promo.dispose();
    super.dispose();
  }

  Cancha? get _cancha {
    for (final c in appState.misCanchas) {
      if (c.id == _canchaId) return c;
    }
    return null;
  }

  DateTime get _fecha => DateTime.now().add(Duration(days: _dia));
  String get _iso {
    final d = _fecha;
    return '${d.year.toString().padLeft(4, '0')}-'
        '${d.month.toString().padLeft(2, '0')}-'
        '${d.day.toString().padLeft(2, '0')}';
  }

  String get _diaLabel => _dia == 0 ? 'hoy' : 'mañana';

  void _msg(String t) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(t)));
  }

  /// Precio del slot (lo que pagaría el cliente). Si el slot está SELECCIONADO y
  /// hay descuento elegido, aplica ese %; si no, la hora feliz normal.
  int _precioSlot(Cancha c, String hora, {bool conDescuento = false}) {
    if (conDescuento && _descuento > 0) {
      return (c.precioHora * (100 - _descuento) / 100 * c.duracionSlotMin / 60)
          .round();
    }
    return (c.precioEn(hora) * c.duracionSlotMin / 60).round();
  }

  /// Texto del aviso, personalizado con el nombre del cliente.
  String _texto(String nombre) {
    final c = _cancha!;
    final horas = (_sel.toList()..sort()).join(', ');
    final precios = _sel.map((h) => _precioSlot(c, h, conDescuento: true)).toList()
      ..sort();
    final desde = precios.isEmpty ? 0 : precios.first;
    final donde = c.club.isNotEmpty ? '${c.club} · ${c.nombre}' : c.nombre;
    final off = _descuento > 0 ? ' 🔥 $_descuento% OFF' : '';
    final promo = _promo.text.trim().isEmpty ? '' : '\n${_promo.text.trim()}';
    return '¡Hola $nombre! 🎾 Tengo libre $donde $_diaLabel: $horas '
        '(desde ${c.monedaSimbolo} $desde$off). ¿La quieres? Resérvala en '
        'Pichangol o respóndeme por aquí.$promo';
  }

  Future<void> _avisar() async {
    final u = appState.usuario;
    if (u == null) {
      _msg('Inicia sesión para avisar.');
      return;
    }
    if (_sel.isEmpty) {
      _msg('Elige al menos una hora libre.');
      return;
    }
    final clientes = appState.clientesParaAvisar();
    if (clientes.isEmpty) {
      _msg('Aún no tienes clientes registrados para avisar.');
      return;
    }
    final conApp = clientes.where((c) => c.email.isNotEmpty).toList();
    final sinApp = clientes.where((c) => c.email.isEmpty).toList();
    final go = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Avisar a tus clientes'),
        content: Text(
            'Se avisará a ${clientes.length} cliente(s): '
            '${conApp.length} por la app y ${sinApp.length} por WhatsApp.'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('Cancelar')),
          FilledButton(
              style: FilledButton.styleFrom(backgroundColor: lima),
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('Avisar')),
        ],
      ),
    );
    if (go != true) return;

    setState(() => _avisando = true);
    // Aplica el descuento REAL a cada slot elegido: ese precio será el que se
    // cobre al reservar (0 = deja el precio normal / quita descuentos previos).
    final c = _cancha;
    if (c != null) {
      for (final h in _sel) {
        await appState.aplicarDescuentoSlot(c.id, _iso, h, _descuento);
      }
    }
    var enviados = 0;
    for (final cli in conApp) {
      final msg = Mensaje(
        id: 'msg_${DateTime.now().microsecondsSinceEpoch}_${enviados}',
        hilo: Mensaje.hiloCancha(u.email, cli.email),
        tipo: 'cancha',
        refId: u.email, // hilo dueño↔jugador (mismo patrón del chat de cancha)
        cuentaEmail: cli.email,
        autorEmail: u.email,
        autorNombre: u.nombre,
        esProfe: true,
        texto: _texto(cli.nombre),
        creado: DateTime.now(),
      );
      if (await MensajesRepo.enviar(msg)) enviados++;
    }
    if (!mounted) return;
    setState(() => _avisando = false);
    _msg(enviados > 0
        ? '✅ Avisé a $enviados cliente(s) por la app 📲'
        : (sinApp.isEmpty ? 'Listo.' : 'Ningún cliente tiene la app aún.'));
    if (sinApp.isNotEmpty) await _whatsappSheet(sinApp);
  }

  Future<void> _whatsappSheet(
      List<({String nombre, String email, String telefono})> clientes) async {
    final conTel = clientes.where((c) => c.telefono.isNotEmpty).toList();
    if (conTel.isEmpty) return;
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Theme.of(context).colorScheme.surface,
      shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(24))),
      builder: (ctx) => DraggableScrollableSheet(
        expand: false,
        initialChildSize: 0.7,
        maxChildSize: 0.92,
        builder: (context, scroll) => Column(
          children: [
            const SizedBox(height: 10),
            Container(
                width: 40,
                height: 4,
                decoration: BoxDecoration(
                    color: trazo, borderRadius: BorderRadius.circular(999))),
            const Padding(
              padding: EdgeInsets.fromLTRB(20, 14, 20, 4),
              child: Align(
                alignment: Alignment.centerLeft,
                child: Text('Avisar por WhatsApp',
                    style: TextStyle(fontWeight: FontWeight.w800, fontSize: 18)),
              ),
            ),
            const Padding(
              padding: EdgeInsets.fromLTRB(20, 0, 20, 8),
              child: Align(
                alignment: Alignment.centerLeft,
                child: Text('Estos clientes aún no tienen la app. Toca “Enviar”.',
                    style: TextStyle(color: textoTenue, fontSize: 12.5)),
              ),
            ),
            Expanded(
              child: ListView.separated(
                controller: scroll,
                itemCount: conTel.length,
                separatorBuilder: (_, __) =>
                    Divider(height: 1, color: trazo.withOpacity(0.6)),
                itemBuilder: (_, i) {
                  final cli = conTel[i];
                  return ListTile(
                    leading: CircleAvatar(
                        backgroundColor: teal,
                        child: Text(
                            cli.nombre.isNotEmpty
                                ? cli.nombre[0].toUpperCase()
                                : '?',
                            style: const TextStyle(
                                color: Colors.white,
                                fontWeight: FontWeight.w800))),
                    title: Text(cli.nombre,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(fontWeight: FontWeight.w700)),
                    trailing: FilledButton(
                      style: FilledButton.styleFrom(
                          backgroundColor: verde,
                          foregroundColor: Colors.white),
                      onPressed: () =>
                          WhatsAppLink.abrir(cli.telefono, _texto(cli.nombre)),
                      child: const Text('Enviar'),
                    ),
                  );
                },
              ),
            ),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Llenar cancha')),
      body: ListenableBuilder(
        listenable: appState,
        builder: (context, _) {
          final mias = appState.misCanchas;
          if (mias.isEmpty) {
            return const Center(
              child: Padding(
                padding: EdgeInsets.all(28),
                child: Text('Registra una cancha para poder llenar sus horas.',
                    textAlign: TextAlign.center,
                    style: TextStyle(color: textoTenue)),
              ),
            );
          }
          final c = _cancha;
          final libres = c == null ? <String>[] : appState.horasLibresDe(c, _iso);
          final nClientes = appState.clientesParaAvisar().length;
          return Column(
            children: [
              Expanded(
                child: ListView(
                  padding: const EdgeInsets.fromLTRB(16, 14, 16, 24),
                  children: [
                    const Text('Avisa tus horas libres',
                        style: TextStyle(
                            fontWeight: FontWeight.w800, fontSize: 19)),
                    const SizedBox(height: 4),
                    const Text(
                        'Elige las horas vacías y avísalas a tus clientes: no '
                        'dejes la cancha sin jugar.',
                        style: TextStyle(color: textoTenue, fontSize: 13)),
                    const SizedBox(height: 16),
                    // Cancha
                    DropdownButtonFormField<String>(
                      value: _canchaId,
                      isExpanded: true,
                      decoration: _dec(),
                      items: [
                        for (final k in mias)
                          DropdownMenuItem(
                            value: k.id,
                            child: Text(
                                k.club.isNotEmpty
                                    ? '${k.club} · ${k.nombre}'
                                    : k.nombre,
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis),
                          ),
                      ],
                      onChanged: (v) => setState(() {
                        _canchaId = v;
                        _sel.clear();
                      }),
                    ),
                    const SizedBox(height: 12),
                    // Hoy / Mañana
                    Row(
                      children: [
                        _ChipDia('Hoy', _dia == 0,
                            () => setState(() {
                                  _dia = 0;
                                  _sel.clear();
                                })),
                        const SizedBox(width: 10),
                        _ChipDia('Mañana', _dia == 1,
                            () => setState(() {
                                  _dia = 1;
                                  _sel.clear();
                                })),
                      ],
                    ),
                    const SizedBox(height: 16),
                    Text('Horas libres',
                        style: const TextStyle(
                            fontWeight: FontWeight.w800, fontSize: 14)),
                    const SizedBox(height: 8),
                    if (libres.isEmpty)
                      Padding(
                        padding: const EdgeInsets.symmetric(vertical: 20),
                        child: Text(
                            _dia == 0
                                ? 'No quedan horas libres hoy. 🎉'
                                : 'No hay horas libres mañana. 🎉',
                            style: TextStyle(color: textoTenueDe(context))),
                      )
                    else
                      Wrap(
                        spacing: 8,
                        runSpacing: 8,
                        children: [
                          for (final h in libres)
                            _ChipHora(
                              hora: h,
                              precio: '${c!.monedaSimbolo} '
                                  '${_precioSlot(c, h, conDescuento: _sel.contains(h))}',
                              sel: _sel.contains(h),
                              onTap: () => setState(() {
                                if (!_sel.remove(h)) _sel.add(h);
                              }),
                            ),
                        ],
                      ),
                    if (libres.isNotEmpty) ...[
                      const SizedBox(height: 8),
                      Align(
                        alignment: Alignment.centerLeft,
                        child: TextButton(
                          onPressed: () => setState(() {
                            if (_sel.length == libres.length) {
                              _sel.clear();
                            } else {
                              _sel
                                ..clear()
                                ..addAll(libres);
                            }
                          }),
                          child: Text(_sel.length == libres.length
                              ? 'Quitar todas'
                              : 'Seleccionar todas'),
                        ),
                      ),
                    ],
                    if (_sel.isNotEmpty) ...[
                      const SizedBox(height: 10),
                      const Text('Descuento para llenar (opcional)',
                          style: TextStyle(
                              fontWeight: FontWeight.w800, fontSize: 14)),
                      const SizedBox(height: 8),
                      Wrap(
                        spacing: 8,
                        runSpacing: 8,
                        children: [
                          for (final p in const [0, 10, 15, 20, 30])
                            _ChipDia(p == 0 ? 'Sin desc.' : '$p%',
                                _descuento == p,
                                () => setState(() => _descuento = p)),
                        ],
                      ),
                      const SizedBox(height: 6),
                      Text(
                          _descuento > 0
                              ? 'Se cobra $_descuento% menos en esas horas: es el '
                                  'precio REAL al reservar (no solo el aviso).'
                              : 'Sin descuento: precio normal.',
                          style: TextStyle(
                              color: textoTenueDe(context), fontSize: 12)),
                    ],
                    const SizedBox(height: 12),
                    TextField(
                      controller: _promo,
                      decoration: _dec(
                          hint: 'Mensaje o promo (opcional). Ej.: 20% off hoy'),
                      maxLines: 2,
                    ),
                  ],
                ),
              ),
              SafeArea(
                top: false,
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(16, 6, 16, 12),
                  child: SizedBox(
                    height: 52,
                    child: FilledButton.icon(
                      style: FilledButton.styleFrom(
                          backgroundColor: lima,
                          foregroundColor: Colors.white,
                          shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(14))),
                      onPressed:
                          (_avisando || _sel.isEmpty) ? null : _avisar,
                      icon: _avisando
                          ? const SizedBox(
                              width: 20,
                              height: 20,
                              child: CircularProgressIndicator(
                                  strokeWidth: 2, color: Colors.white))
                          : const Icon(Icons.campaign),
                      label: Text(
                          _sel.isEmpty
                              ? 'Elige horas para avisar'
                              : 'Avisar a mis clientes ($nClientes)',
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

  InputDecoration _dec({String? hint}) => InputDecoration(
        hintText: hint,
        isDense: true,
        filled: true,
        fillColor: Theme.of(context).colorScheme.surface,
        contentPadding:
            const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
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

class _ChipDia extends StatelessWidget {
  const _ChipDia(this.texto, this.sel, this.onTap);
  final String texto;
  final bool sel;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 9),
        decoration: BoxDecoration(
          color: sel ? cs.primary : Colors.transparent,
          borderRadius: BorderRadius.circular(999),
          border: Border.all(
              color: sel ? cs.primary : textoTenueDe(context).withOpacity(0.4)),
        ),
        child: Text(texto,
            style: TextStyle(
                fontWeight: FontWeight.w700,
                color: sel ? Colors.white : cs.onSurface)),
      ),
    );
  }
}

class _ChipHora extends StatelessWidget {
  const _ChipHora(
      {required this.hora,
      required this.precio,
      required this.sel,
      required this.onTap});
  final String hora;
  final String precio;
  final bool sel;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
        decoration: BoxDecoration(
          color: sel ? cs.primary : Colors.transparent,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(
              color: sel ? cs.primary : textoTenueDe(context).withOpacity(0.4)),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(hora,
                style: TextStyle(
                    fontWeight: FontWeight.w800,
                    fontSize: 14,
                    color: sel ? Colors.white : cs.onSurface)),
            Text(precio,
                style: TextStyle(
                    fontSize: 11,
                    color: sel ? Colors.white70 : textoTenueDe(context))),
          ],
        ),
      ),
    );
  }
}
