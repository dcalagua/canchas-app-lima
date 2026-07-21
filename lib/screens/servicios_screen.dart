import 'package:flutter/material.dart';

import '../models/academia.dart';
import '../services/pagos_service.dart';
import '../state/app_state.dart';
import '../theme.dart';
import 'recargar_saldo_screen.dart';

/// "Servicios Pichangol": el dueño contrata landing / manejo de redes /
/// presencia digital como SUSCRIPCIÓN mensual, pagada con el saldo de su
/// academia (mismo saldo prepago de Culqi). Muestra estado y próximo cobro.
class ServiciosScreen extends StatefulWidget {
  const ServiciosScreen({super.key, required this.academia});
  final Academia academia;

  @override
  State<ServiciosScreen> createState() => _ServiciosScreenState();
}

class _ServiciosScreenState extends State<ServiciosScreen> {
  List<Map<String, dynamic>>? _planes;
  List<Map<String, dynamic>> _subs = const [];
  bool _cargando = true;
  String? _procesando; // clave del servicio en curso

  String get _mon => widget.academia.monedaSimbolo;
  String get _idAcademia => widget.academia.id;

  @override
  void initState() {
    super.initState();
    _cargar();
  }

  Future<void> _cargar() async {
    setState(() => _cargando = true);
    await appState.sincronizarSaldoAcademia(_idAcademia);
    final planes = await PagosService.planesServicios();
    final subs = await PagosService.estadoServicios(_idAcademia);
    if (!mounted) return;
    setState(() {
      _planes = planes;
      _subs = subs ?? const [];
      _cargando = false;
    });
  }

  Map<String, dynamic>? _subDe(String clave) {
    for (final s in _subs) {
      if (s['servicio'] == clave) return s;
    }
    return null;
  }

  Future<void> _contratar(Map<String, dynamic> plan) async {
    final clave = plan['clave'] as String;
    setState(() => _procesando = clave);
    final r = await PagosService.contratarServicio(
        duenoId: _idAcademia, academiaId: _idAcademia, servicio: clave);
    if (!mounted) return;
    setState(() => _procesando = null);
    if (r == null) {
      _msg('No se pudo contratar. Revisa tu conexión.');
      return;
    }
    if (r['falta_saldo'] == true) {
      await _faltaSaldo((r['requerido_soles'] as num?)?.toDouble() ?? 0);
      return;
    }
    if (r['ok'] == true) {
      await _cargar();
      _msg('✅ ${plan['nombre']} activado. Te contactaremos para arrancar.');
    } else {
      _msg('No se pudo contratar.');
    }
  }

  Future<void> _faltaSaldo(double requerido) async {
    final ir = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Saldo insuficiente'),
        content: Text(
            'Necesitas $_mon ${requerido.toStringAsFixed(0)} de saldo para '
            'contratar este servicio. Recarga y vuelve a intentarlo.'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('Ahora no')),
          FilledButton(
              style: FilledButton.styleFrom(backgroundColor: lima),
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('Recargar saldo')),
        ],
      ),
    );
    if (ir == true && mounted) await _pushRecarga();
  }

  Future<void> _pushRecarga() async {
    await Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => RecargarSaldoScreen(
          duenoId: _idAcademia,
          titulo: 'Recargar saldo',
          pais: widget.academia.pais),
    ));
    await _cargar();
  }

  Future<void> _cancelar(String clave, String nombre) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text('Cancelar $nombre'),
        content: const Text(
            'Se cancela la renovación del próximo mes. El mes en curso sigue '
            'activo hasta su fecha.'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('No')),
          FilledButton(
              style: FilledButton.styleFrom(backgroundColor: clayOscuro),
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('Sí, cancelar')),
        ],
      ),
    );
    if (ok == true) {
      await PagosService.cancelarServicio(academiaId: _idAcademia, servicio: clave);
      await _cargar();
    }
  }

  void _msg(String t) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(t)));
  }

  String _fecha(String? iso) {
    if (iso == null) return '';
    final d = DateTime.tryParse(iso);
    if (d == null) return '';
    return '${d.day}/${d.month}/${d.year}';
  }

  @override
  Widget build(BuildContext context) {
    final saldo = appState.saldoAcademiaDe(_idAcademia);
    return Scaffold(
      appBar: AppBar(title: const Text('Servicios Pichangol')),
      body: _cargando
          ? const Center(child: CircularProgressIndicator(color: lima))
          : RefreshIndicator(
              onRefresh: _cargar,
              color: lima,
              child: ListView(
                padding: const EdgeInsets.fromLTRB(16, 14, 16, 30),
                children: [
                  // Saldo de la academia.
                  Container(
                    padding: const EdgeInsets.all(16),
                    decoration: BoxDecoration(
                      color: limaSuave,
                      borderRadius: BorderRadius.circular(16),
                    ),
                    child: Row(
                      children: [
                        const Icon(Icons.account_balance_wallet_outlined,
                            color: lima),
                        const SizedBox(width: 10),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              const Text('Saldo de la academia',
                                  style: TextStyle(
                                      fontSize: 12, color: textoTenue)),
                              Text('$_mon $saldo',
                                  style: const TextStyle(
                                      fontSize: 20,
                                      fontWeight: FontWeight.w800)),
                            ],
                          ),
                        ),
                        TextButton(
                          onPressed: _pushRecarga,
                          child: const Text('Recargar',
                              style: TextStyle(
                                  color: lima, fontWeight: FontWeight.w800)),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 8),
                  const Padding(
                    padding: EdgeInsets.symmetric(vertical: 8, horizontal: 2),
                    child: Text(
                        'Contrata tu presencia digital. Se cobra del saldo cada '
                        'mes; puedes cancelar cuando quieras.',
                        style: TextStyle(color: textoTenue, fontSize: 13)),
                  ),
                  if (_planes == null)
                    const Padding(
                      padding: EdgeInsets.all(24),
                      child: Text('No se pudo cargar el catálogo.',
                          style: TextStyle(color: textoTenue)),
                    )
                  else
                    for (final p in _planes!) _tarjetaPlan(p),
                ],
              ),
            ),
    );
  }

  Widget _tarjetaPlan(Map<String, dynamic> plan) {
    final clave = plan['clave'] as String;
    final nombre = (plan['nombre'] ?? '') as String;
    final desc = (plan['desc'] ?? '') as String;
    final soles = (plan['soles'] as num?)?.toDouble() ?? 0;
    final sub = _subDe(clave);
    final estado = sub?['estado'] as String?;
    final activa = estado == 'activa';
    final pendiente = estado == 'pendiente_pago';
    final procesando = _procesando == clave;
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
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
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: Text(nombre,
                    style: const TextStyle(
                        fontWeight: FontWeight.w800, fontSize: 17)),
              ),
              Text('$_mon ${soles.toStringAsFixed(0)}',
                  style: const TextStyle(
                      fontWeight: FontWeight.w900, fontSize: 18, color: lima)),
              const Text(' /mes',
                  style: TextStyle(color: textoTenue, fontSize: 12)),
            ],
          ),
          const SizedBox(height: 4),
          Text(desc, style: const TextStyle(color: textoTenue, fontSize: 13)),
          const SizedBox(height: 12),
          if (activa || pendiente) ...[
            Container(
              padding:
                  const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
              decoration: BoxDecoration(
                color: pendiente ? const Color(0xFFFBEAD2) : limaSuave,
                borderRadius: BorderRadius.circular(999),
              ),
              child: Text(
                pendiente
                    ? '⚠ Pago pendiente — recarga tu saldo'
                    : '● Activo · próximo cobro ${_fecha(sub?['proximo_cobro'])}',
                style: TextStyle(
                    fontSize: 12.5,
                    fontWeight: FontWeight.w700,
                    color: pendiente ? clayOscuro : lima),
              ),
            ),
            const SizedBox(height: 8),
            Align(
              alignment: Alignment.centerRight,
              child: TextButton(
                onPressed: () => _cancelar(clave, nombre),
                child: const Text('Cancelar suscripción',
                    style: TextStyle(color: clayOscuro)),
              ),
            ),
          ] else
            SizedBox(
              width: double.infinity,
              child: FilledButton(
                style: FilledButton.styleFrom(
                    backgroundColor: lima,
                    foregroundColor: Colors.white,
                    padding: const EdgeInsets.symmetric(vertical: 13)),
                onPressed: procesando ? null : () => _contratar(plan),
                child: procesando
                    ? const SizedBox(
                        height: 20,
                        width: 20,
                        child: CircularProgressIndicator(
                            strokeWidth: 2.4, color: Colors.white))
                    : Text('Contratar · $_mon ${soles.toStringAsFixed(0)}/mes'),
              ),
            ),
        ],
      ),
    );
  }
}
