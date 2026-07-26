import 'package:flutter/material.dart';

import '../models/negocio.dart';
import '../services/pagos_service.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/cargando_pichangol.dart';

/// MÉTODO DE PAGO DE SERVICIOS: la tarjeta (débito automático One-Click) con la
/// que se RENUEVAN cada mes las suscripciones de "Servicios Pichangol". El saldo
/// y los movimientos viven en la billetera única (CuentaScreen); esto es solo la
/// tarjeta de renovación. Se abre desde Servicios Pichangol.
class BilleteraNegocioScreen extends StatefulWidget {
  const BilleteraNegocioScreen({super.key, required this.negocio});
  final Negocio negocio;

  @override
  State<BilleteraNegocioScreen> createState() => _BilleteraNegocioScreenState();
}

class _BilleteraNegocioScreenState extends State<BilleteraNegocioScreen> {
  Map<String, dynamic>? _metodo;
  bool _cargando = true;

  String get _id => widget.negocio.id;

  @override
  void initState() {
    super.initState();
    _cargar();
  }

  Future<void> _cargar() async {
    setState(() => _cargando = true);
    final m = await PagosService.metodoSuscripcion(_id);
    if (!mounted) return;
    setState(() {
      _metodo = m;
      _cargando = false;
    });
  }

  void _msg(String t) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(t)));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Método de pago de servicios')),
      body: _cargando
          ? const CargandoPichangol()
          : RefreshIndicator(
              onRefresh: _cargar,
              color: lima,
              child: ListView(
                padding: const EdgeInsets.fromLTRB(16, 14, 16, 28),
                children: [
                  const Text(
                      'La tarjeta con la que se renuevan automáticamente tus '
                      'servicios cada mes. El saldo y los movimientos están en tu '
                      'billetera.',
                      style: TextStyle(color: textoTenue, fontSize: 13)),
                  const SizedBox(height: 14),
                  _cardDebitoAuto(),
                ],
              ),
            ),
    );
  }

  /// MÉTODO DE PAGO (recurrente): guarda una tarjeta (One-Click) para que las
  /// suscripciones se cobren solas cada mes. Yape no es recurrente (pago único).
  Widget _cardDebitoAuto() {
    final tiene = _metodo?['tiene_tarjeta'] == true;
    final marca = (_metodo?['marca'] ?? '').toString();
    final u4 = (_metodo?['ultimos4'] ?? '').toString();
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
              const Icon(Icons.credit_card, color: lima),
              const SizedBox(width: 8),
              const Expanded(
                child: Text('Método de pago',
                    style:
                        TextStyle(fontWeight: FontWeight.w800, fontSize: 16)),
              ),
              if (tiene)
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                  decoration: BoxDecoration(
                      color: limaSuave,
                      borderRadius: BorderRadius.circular(999)),
                  child: const Text('● Activo',
                      style: TextStyle(
                          fontSize: 11.5,
                          fontWeight: FontWeight.w800,
                          color: lima)),
                ),
            ],
          ),
          const SizedBox(height: 6),
          Text(
              tiene
                  ? 'Tus suscripciones se cobran solas cada mes. Tarjeta '
                      '${marca.isEmpty ? '' : '$marca '}····$u4.'
                  : 'Agrega tu tarjeta y tus suscripciones se cobran solas cada '
                      'mes. Sin recargar ni perseguir el pago.\n'
                      'Yape sirve para pagos únicos (recargar saldo); el cobro '
                      'automático es solo con tarjeta.',
              style: const TextStyle(color: textoTenue, fontSize: 13)),
          const SizedBox(height: 12),
          if (tiene)
            Align(
              alignment: Alignment.centerRight,
              child: TextButton.icon(
                icon: const Icon(Icons.delete_outline,
                    size: 18, color: clayOscuro),
                label: const Text('Quitar tarjeta',
                    style: TextStyle(color: clayOscuro)),
                onPressed: _quitarTarjeta,
              ),
            )
          else
            SizedBox(
              width: double.infinity,
              child: FilledButton.icon(
                style: FilledButton.styleFrom(
                    backgroundColor: lima,
                    foregroundColor: Colors.white,
                    padding: const EdgeInsets.symmetric(vertical: 13)),
                icon: const Icon(Icons.add_card, size: 18),
                label: const Text('Agregar tarjeta',
                    style: TextStyle(fontWeight: FontWeight.w800)),
                onPressed: _agregarTarjeta,
              ),
            ),
        ],
      ),
    );
  }

  Future<void> _quitarTarjeta() async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Quitar tarjeta'),
        content: const Text(
            'Se elimina la tarjeta de débito automático. Tus suscripciones se '
            'cobrarán del saldo; recárgalo para que no se pausen.'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('No')),
          FilledButton(
              style: FilledButton.styleFrom(backgroundColor: clayOscuro),
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('Quitar')),
        ],
      ),
    );
    if (ok == true) {
      await PagosService.eliminarMetodoSuscripcion(_id);
      await _cargar();
    }
  }

  /// Hoja para tokenizar y guardar la tarjeta de débito automático (Culqi).
  Future<void> _agregarTarjeta() async {
    final cfg = await PagosService.config();
    final pk = (cfg?['public_key'] ?? '').toString();
    if (!mounted) return;
    if (cfg?['disponible'] != true || pk.isEmpty) {
      _msg('Pagos no configurados en el servidor.');
      return;
    }
    final email = appState.usuario?.email ?? '';
    final numero = TextEditingController();
    final exp = TextEditingController();
    final cvv = TextEditingController();
    var guardando = false;
    String? error;

    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Theme.of(context).colorScheme.surface,
      shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(24))),
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setSt) => Padding(
          padding: EdgeInsets.fromLTRB(
              18, 18, 18, MediaQuery.of(ctx).viewInsets.bottom + 18),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text('Tarjeta para débito automático',
                  style: TextStyle(fontWeight: FontWeight.w800, fontSize: 17)),
              const SizedBox(height: 4),
              const Text(
                  'Se guarda de forma segura (no guardamos el número). Se usará '
                  'para cobrar tus suscripciones cada mes.',
                  style: TextStyle(color: textoTenue, fontSize: 12.5)),
              const SizedBox(height: 14),
              TextField(
                controller: numero,
                keyboardType: TextInputType.number,
                decoration: const InputDecoration(
                    labelText: 'Número de tarjeta',
                    hintText: '4111 1111 1111 1111'),
              ),
              Row(
                children: [
                  Expanded(
                    child: TextField(
                      controller: exp,
                      keyboardType: TextInputType.number,
                      decoration: const InputDecoration(
                          labelText: 'Vence (MM/AA)', hintText: '09/28'),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: TextField(
                      controller: cvv,
                      keyboardType: TextInputType.number,
                      obscureText: true,
                      decoration: const InputDecoration(
                          labelText: 'CVV', hintText: '123'),
                    ),
                  ),
                ],
              ),
              if (error != null) ...[
                const SizedBox(height: 8),
                Text(error!,
                    style: const TextStyle(color: clayOscuro, fontSize: 13)),
              ],
              const SizedBox(height: 16),
              SizedBox(
                width: double.infinity,
                child: FilledButton(
                  style: FilledButton.styleFrom(
                      backgroundColor: lima,
                      foregroundColor: Colors.white,
                      padding: const EdgeInsets.symmetric(vertical: 14)),
                  onPressed: guardando
                      ? null
                      : () async {
                          final num = numero.text.replaceAll(' ', '');
                          final partes = exp.text.split('/');
                          final mes = partes.isNotEmpty
                              ? (int.tryParse(partes[0].trim()) ?? 0)
                              : 0;
                          var anio = partes.length > 1
                              ? (int.tryParse(partes[1].trim()) ?? 0)
                              : 0;
                          if (anio < 100) anio += 2000;
                          if (num.length < 15) {
                            setSt(() => error = 'Número de tarjeta inválido.');
                            return;
                          }
                          if (mes < 1 || mes > 12) {
                            setSt(() => error =
                                'Fecha inválida. Escribe MES/AÑO, ej. 09/28.');
                            return;
                          }
                          if (cvv.text.trim().length < 3) {
                            setSt(() => error = 'CVV inválido.');
                            return;
                          }
                          setSt(() {
                            guardando = true;
                            error = null;
                          });
                          // Regla: tokenizar + guardar demora → preload de marca.
                          String? err;
                          final ok = await conPreload(ctx, () async {
                            final tok = await PagosService.tokenizarTarjeta(
                                publicKey: pk,
                                numero: num,
                                cvv: cvv.text.trim(),
                                mesExp: mes,
                                anioExp: anio,
                                email: email);
                            if (tok['ok'] != true) {
                              err = tok['error']?.toString() ??
                                  'No se pudo validar la tarjeta.';
                              return false;
                            }
                            final r =
                                await PagosService.guardarMetodoSuscripcion(
                                    academiaId: _id,
                                    token: tok['token'].toString(),
                                    email: email);
                            if (r['ok'] != true) {
                              err = r['error']?.toString() ??
                                  'No se pudo guardar la tarjeta.';
                              return false;
                            }
                            return true;
                          }, texto: 'Guardando tarjeta…');
                          if (ok) {
                            if (ctx.mounted) Navigator.pop(ctx);
                          } else {
                            setSt(() {
                              guardando = false;
                              error = err ?? 'No se pudo guardar la tarjeta.';
                            });
                          }
                        },
                  child: const Text('Guardar tarjeta'),
                ),
              ),
            ],
          ),
        ),
      ),
    );
    if (mounted) await _cargar();
  }
}
