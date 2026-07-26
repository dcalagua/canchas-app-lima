import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../services/pagos_service.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/cargando_pichangol.dart';
import '../utils/input_formatos.dart';
import '../widgets/marcas_pago.dart';
import '../widgets/sesion_requerida.dart';

/// Métodos de pago del usuario: tarjetas guardadas (Culqi One Click). El usuario
/// agrega una tarjeta una vez y luego paga sin re-tipear. No se guarda el número
/// completo: solo la marca y los últimos 4 (Culqi custodia la tarjeta).
class MetodosPagoScreen extends StatefulWidget {
  const MetodosPagoScreen({super.key});

  @override
  State<MetodosPagoScreen> createState() => _MetodosPagoScreenState();
}

class _MetodosPagoScreenState extends State<MetodosPagoScreen> {
  bool _cargando = true;
  String? _pk;
  String _modo = ''; // 'test' | 'live' | '' (según la llave Culqi del backend)
  List<Map<String, dynamic>> _metodos = [];

  String get _userId => appState.usuario?.email ?? '';

  @override
  void initState() {
    super.initState();
    _cargar();
  }

  Future<void> _cargar() async {
    final cfg = await PagosService.config();
    final lista = _userId.isEmpty ? <Map<String, dynamic>>[] : await PagosService.metodos(_userId);
    if (!mounted) return;
    setState(() {
      _cargando = false;
      _pk = (cfg?['disponible'] == true) ? (cfg?['public_key'] as String?) : null;
      _modo = (cfg?['modo'] ?? '').toString();
      _metodos = lista;
    });
  }

  Future<void> _agregar() async {
    if (_pk == null || _pk!.isEmpty) {
      _avisar('Los pagos aún no están habilitados en el servidor.');
      return;
    }
    final ok = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Theme.of(context).colorScheme.surface,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      builder: (_) =>
          _AgregarTarjetaSheet(publicKey: _pk!, userId: _userId, modo: _modo),
    );
    if (ok == true) _cargar();
  }

  Future<void> _eliminar(Map<String, dynamic> m) async {
    final si = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('Quitar tarjeta'),
        content: Text('¿Eliminar la tarjeta terminada en ${m['ultimos4']}?'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: const Text('Cancelar')),
          FilledButton(
              style: FilledButton.styleFrom(backgroundColor: const Color(0xFFC0392B)),
              onPressed: () => Navigator.pop(context, true),
              child: const Text('Eliminar')),
        ],
      ),
    );
    if (si != true) return;
    final borrado = await PagosService.eliminarMetodo(_userId, m['id'].toString());
    if (borrado) _cargar();
  }

  void _avisar(String m) =>
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(m)));

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final cs = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(title: const Text('Métodos de pago')),
      body: _cargando
          ? const CargandoPichangol()
          : _userId.isEmpty
              ? SesionRequerida(
                  motivo: 'guardar tus tarjetas',
                  icono: Icons.credit_card,
                  titulo: 'Guarda tus tarjetas',
                  onLogueado: _cargar,
                )
              : ListView(
                  padding: const EdgeInsets.all(18),
                  children: [
                    if (_metodos.isEmpty)
                      Container(
                        padding: const EdgeInsets.all(20),
                        decoration: BoxDecoration(
                            color: Theme.of(context).colorScheme.surface,
                            borderRadius: BorderRadius.circular(16),
                            border: Border.all(color: trazo)),
                        child: Column(
                          children: [
                            const Icon(Icons.credit_card_off,
                                color: textoTenue, size: 36),
                            const SizedBox(height: 10),
                            Text('Aún no tienes tarjetas guardadas',
                                style: t.titleSmall
                                    ?.copyWith(fontWeight: FontWeight.w700)),
                            const SizedBox(height: 4),
                            const Text(
                                'Agrega una para pagar más rápido la próxima vez.',
                                textAlign: TextAlign.center,
                                style: TextStyle(
                                    color: textoTenue, fontSize: 13)),
                          ],
                        ),
                      )
                    else
                      for (final m in _metodos) _TarjetaGuardada(m: m, onEliminar: () => _eliminar(m)),
                    const SizedBox(height: 16),
                    OutlinedButton.icon(
                      style: OutlinedButton.styleFrom(
                        foregroundColor: cs.primary,
                        side: BorderSide(color: cs.primary, width: 1.4),
                        padding: const EdgeInsets.symmetric(vertical: 14),
                        shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(14)),
                      ),
                      onPressed: _agregar,
                      icon: const Icon(Icons.add),
                      label: const Text('Agregar tarjeta'),
                    ),
                    const SizedBox(height: 12),
                    const Center(
                      child: Text('Tus tarjetas se guardan de forma segura en Culqi.',
                          style: TextStyle(color: textoTenue, fontSize: 12)),
                    ),
                  ],
                ),
    );
  }
}

class _TarjetaGuardada extends StatelessWidget {
  const _TarjetaGuardada({required this.m, required this.onEliminar});
  final Map<String, dynamic> m;
  final VoidCallback onEliminar;

  @override
  Widget build(BuildContext context) {
    final marca = (m['marca'] ?? 'Tarjeta').toString();
    final esVisa = marca.toLowerCase().contains('visa');
    final esMaster = marca.toLowerCase().contains('master');
    final cs = Theme.of(context).colorScheme;
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      decoration: BoxDecoration(
        color: cs.surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: trazo),
        boxShadow: const [
          BoxShadow(color: Color(0x0F000000), blurRadius: 8, offset: Offset(0, 3)),
        ],
      ),
      child: Row(
        children: [
          SizedBox(
            width: 44,
            child: esVisa
                ? const VisaMark(alto: 16)
                : esMaster
                    ? const MastercardMark(alto: 24)
                    : Icon(Icons.credit_card, color: cs.primary),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('$marca ···· ${m['ultimos4'] ?? ''}',
                    style: TextStyle(
                        fontWeight: FontWeight.w700, color: cs.onSurface)),
                const Text('Guardada para 1 toque',
                    style: TextStyle(color: textoTenue, fontSize: 12)),
              ],
            ),
          ),
          IconButton(
            icon: const Icon(Icons.delete_outline, color: Color(0xFFC0392B)),
            onPressed: onEliminar,
          ),
        ],
      ),
    );
  }
}

/// Hoja para agregar una tarjeta: tokeniza con la llave pública y la guarda.
class _AgregarTarjetaSheet extends StatefulWidget {
  const _AgregarTarjetaSheet(
      {required this.publicKey, required this.userId, this.modo = ''});
  final String publicKey;
  final String userId;
  final String modo; // 'test' | 'live' | ''

  @override
  State<_AgregarTarjetaSheet> createState() => _AgregarTarjetaSheetState();
}

class _AgregarTarjetaSheetState extends State<_AgregarTarjetaSheet> {
  final _num = TextEditingController();
  final _exp = TextEditingController();
  final _cvv = TextEditingController();
  final _nombre = TextEditingController();
  bool _guardando = false;
  String? _error;

  @override
  void dispose() {
    _num.dispose();
    _exp.dispose();
    _cvv.dispose();
    _nombre.dispose();
    super.dispose();
  }

  Future<void> _guardar() async {
    setState(() => _error = null);
    final numero = _num.text.replaceAll(' ', '');
    final exp = _exp.text.split('/');
    if (numero.length < 15) return _fail('Número de tarjeta inválido.');
    if (exp.length != 2) return _fail('Vencimiento inválido (MM/AA).');
    if (_cvv.text.length < 3) return _fail('CVV inválido.');
    final mes = int.tryParse(exp[0].trim()) ?? 0;
    var anio = int.tryParse(exp[1].trim()) ?? 0;
    if (anio < 100) anio += 2000;

    if (_guardando) return;
    setState(() => _guardando = true);
    final email = widget.userId;
    // Regla: tokenizar + guardar la tarjeta demora → preload de marca.
    String? err;
    final ok = await conPreload(context, () async {
      final tok = await PagosService.tokenizarTarjeta(
          publicKey: widget.publicKey, numero: numero, cvv: _cvv.text.trim(),
          mesExp: mes, anioExp: anio, email: email);
      if (tok['ok'] != true) {
        err = tok['error']?.toString() ?? 'Tarjeta rechazada.';
        return false;
      }
      final partes = _nombre.text.trim().split(' ');
      final res = await PagosService.guardarMetodo(
        token: tok['token'].toString(),
        userId: widget.userId,
        email: email,
        nombre: partes.isNotEmpty ? partes.first : '',
        apellido: partes.length > 1 ? partes.sublist(1).join(' ') : '',
      );
      if (res['ok'] != true) {
        err = res['error']?.toString() ?? 'No se pudo guardar.';
        return false;
      }
      return true;
    }, texto: 'Guardando tarjeta…');
    if (!mounted) return;
    if (!ok) return _fail(err ?? 'No se pudo guardar.');
    Navigator.of(context).pop(true);
  }

  void _fail(String m) {
    if (!mounted) return;
    setState(() {
      _guardando = false;
      _error = m;
    });
  }

  // Solo en modo prueba: rellena la tarjeta de test de Culqi para probar rápido.
  void _autocompletarPrueba() {
    setState(() {
      _num.text = '4111 1111 1111 1111';
      _exp.text = '09/28';
      _cvv.text = '123';
      if (_nombre.text.trim().isEmpty) {
        _nombre.text = appState.usuario?.nombre ?? 'Test Pichangol';
      }
      _error = null;
    });
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.fromLTRB(
          20, 18, 20, 20 + MediaQuery.of(context).viewInsets.bottom),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Text('Agregar tarjeta',
                  style: TextStyle(fontWeight: FontWeight.w800, fontSize: 18)),
              const Spacer(),
              if (widget.modo == 'test' || widget.modo == 'live')
                _ModoBadge(live: widget.modo == 'live'),
            ],
          ),
          if (widget.modo == 'live') ...[
            const SizedBox(height: 10),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 9),
              decoration: BoxDecoration(
                color: const Color(0xFFFFF4E5),
                borderRadius: BorderRadius.circular(12),
              ),
              child: const Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Icon(Icons.info_outline, size: 18, color: Color(0xFFB26A00)),
                  SizedBox(width: 8),
                  Expanded(
                    child: Text(
                        'Modo real: usa una tarjeta real. Las tarjetas de prueba '
                        '(4111 1111 1111 1111) serán rechazadas por el antifraude.',
                        style: TextStyle(
                            color: Color(0xFF8A5300),
                            fontSize: 12.5,
                            height: 1.3)),
                  ),
                ],
              ),
            ),
          ],
          const SizedBox(height: 14),
          if (widget.modo == 'test') ...[
            Align(
              alignment: Alignment.centerLeft,
              child: TextButton.icon(
                onPressed: _autocompletarPrueba,
                style: TextButton.styleFrom(
                    foregroundColor: bosque, padding: EdgeInsets.zero),
                icon: const Icon(Icons.bolt, size: 18),
                label: const Text('Autocompletar datos de prueba'),
              ),
            ),
            const SizedBox(height: 6),
          ],
          TextField(
            controller: _num,
            keyboardType: TextInputType.number,
            inputFormatters: [TarjetaNumeroFormatter()],
            decoration: const InputDecoration(
                labelText: 'Número de tarjeta',
                hintText: '1234 5678 9012 3456',
                prefixIcon: Icon(Icons.credit_card)),
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              Expanded(
                child: TextField(
                  controller: _exp,
                  keyboardType: TextInputType.number,
                  inputFormatters: [VencimientoFormatter()],
                  decoration: const InputDecoration(
                      labelText: 'Vence (MM/AA)', hintText: '09/28'),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: TextField(
                  controller: _cvv,
                  keyboardType: TextInputType.number,
                  obscureText: true,
                  inputFormatters: [FilteringTextInputFormatter.digitsOnly, LengthLimitingTextInputFormatter(4)],
                  decoration: const InputDecoration(labelText: 'CVV'),
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _nombre,
            textCapitalization: TextCapitalization.words,
            decoration: const InputDecoration(
                labelText: 'Nombre del titular (opcional)',
                prefixIcon: Icon(Icons.person_outline)),
          ),
          if (_error != null) ...[
            const SizedBox(height: 12),
            Text(_error!,
                style: const TextStyle(
                    color: Color(0xFFC0392B), fontWeight: FontWeight.w600)),
          ],
          const SizedBox(height: 18),
          SizedBox(
            width: double.infinity,
            child: FilledButton(
              style: FilledButton.styleFrom(
                  backgroundColor: lima,
                  foregroundColor: Colors.white,
                  padding: const EdgeInsets.symmetric(vertical: 14)),
              onPressed: _guardando ? null : _guardar,
              child: const Text('Guardar tarjeta'),
            ),
          ),
        ],
      ),
    );
  }
}

/// Chip que indica si el backend de pagos está en modo PRUEBA o REAL (según la
/// llave Culqi). Ayuda a entender por qué una tarjeta de test es o no aceptada.
class _ModoBadge extends StatelessWidget {
  const _ModoBadge({required this.live});
  final bool live;
  @override
  Widget build(BuildContext context) {
    final bg = live ? const Color(0xFFE7F5EC) : const Color(0xFFFFF4E5);
    final fg = live ? const Color(0xFF176B3A) : const Color(0xFFB26A00);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 4),
      decoration: BoxDecoration(color: bg, borderRadius: BorderRadius.circular(999)),
      child: Text(live ? 'Modo real' : 'Modo prueba',
          style: TextStyle(color: fg, fontSize: 11, fontWeight: FontWeight.w800)),
    );
  }
}
