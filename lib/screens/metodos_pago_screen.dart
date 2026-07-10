import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../services/pagos_service.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/marcas_pago.dart';

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
      backgroundColor: Colors.white,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      builder: (_) => _AgregarTarjetaSheet(publicKey: _pk!, userId: _userId),
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
    return Scaffold(
      backgroundColor: papel,
      appBar: AppBar(title: const Text('Métodos de pago')),
      body: _cargando
          ? const Center(child: CircularProgressIndicator())
          : _userId.isEmpty
              ? const Center(
                  child: Padding(
                    padding: EdgeInsets.all(28),
                    child: Text('Inicia sesión para guardar tus tarjetas.',
                        textAlign: TextAlign.center,
                        style: TextStyle(color: textoTenue)),
                  ),
                )
              : ListView(
                  padding: const EdgeInsets.all(18),
                  children: [
                    if (_metodos.isEmpty)
                      Container(
                        padding: const EdgeInsets.all(20),
                        decoration: BoxDecoration(
                            color: Colors.white,
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
                        foregroundColor: bosque,
                        side: const BorderSide(color: bosque, width: 1.4),
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
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      decoration: BoxDecoration(
        color: Colors.white,
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
                    : const Icon(Icons.credit_card, color: bosque),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('$marca ···· ${m['ultimos4'] ?? ''}',
                    style: const TextStyle(
                        fontWeight: FontWeight.w700, color: tinta)),
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
  const _AgregarTarjetaSheet({required this.publicKey, required this.userId});
  final String publicKey;
  final String userId;

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

    setState(() => _guardando = true);
    final email = widget.userId;
    final tok = await PagosService.tokenizarTarjeta(
        publicKey: widget.publicKey, numero: numero, cvv: _cvv.text.trim(),
        mesExp: mes, anioExp: anio, email: email);
    if (!mounted) return;
    if (tok['ok'] != true) return _fail(tok['error']?.toString() ?? 'Tarjeta rechazada.');

    final partes = _nombre.text.trim().split(' ');
    final res = await PagosService.guardarMetodo(
      token: tok['token'].toString(),
      userId: widget.userId,
      email: email,
      nombre: partes.isNotEmpty ? partes.first : '',
      apellido: partes.length > 1 ? partes.sublist(1).join(' ') : '',
    );
    if (!mounted) return;
    if (res['ok'] != true) return _fail(res['error']?.toString() ?? 'No se pudo guardar.');
    Navigator.of(context).pop(true);
  }

  void _fail(String m) {
    if (!mounted) return;
    setState(() {
      _guardando = false;
      _error = m;
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
          const Text('Agregar tarjeta',
              style: TextStyle(fontWeight: FontWeight.w800, fontSize: 18)),
          const SizedBox(height: 14),
          TextField(
            controller: _num,
            keyboardType: TextInputType.number,
            inputFormatters: [FilteringTextInputFormatter.digitsOnly, LengthLimitingTextInputFormatter(19)],
            decoration: const InputDecoration(
                labelText: 'Número de tarjeta', prefixIcon: Icon(Icons.credit_card)),
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              Expanded(
                child: TextField(
                  controller: _exp,
                  keyboardType: TextInputType.number,
                  inputFormatters: [LengthLimitingTextInputFormatter(5)],
                  decoration: const InputDecoration(
                      labelText: 'Vence (MM/AA)', hintText: '08/28'),
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
                  backgroundColor: pino,
                  foregroundColor: lima,
                  padding: const EdgeInsets.symmetric(vertical: 14)),
              onPressed: _guardando ? null : _guardar,
              child: _guardando
                  ? const SizedBox(
                      height: 20,
                      width: 20,
                      child: CircularProgressIndicator(strokeWidth: 2.4, color: lima))
                  : const Text('Guardar tarjeta'),
            ),
          ),
        ],
      ),
    );
  }
}
