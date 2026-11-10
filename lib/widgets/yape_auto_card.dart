import 'package:flutter/material.dart';

import '../services/yape_auto_service.dart';
import '../state/app_state.dart';
import '../theme.dart';
import 'dialogo_pichangol.dart';
import 'icono_vivo.dart';

import '../brand.dart';
/// "Confirmar mis pagos automáticamente" (fase 2 del Plan Academia): el
/// celular Android de la academia lee la notificación de su Yape y Pichangol
/// confirma solo el pago del alumno con el mismo código de seguridad y monto.
/// Opt-in con aviso destacado (exigencia de Play para leer notificaciones) y
/// permiso que el dueño da a mano en Ajustes.
class TarjetaYapeAuto extends StatefulWidget {
  /// [qr] = academia en Ecuador / Bolivia: escucha la app de cobros que elija
  /// el dueño (DeUna!, su banco…) y confirma el pago por el MONTO ÚNICO.
  const TarjetaYapeAuto({super.key, this.qr = false});
  final bool qr;

  @override
  State<TarjetaYapeAuto> createState() => _TarjetaYapeAutoState();
}

class _TarjetaYapeAutoState extends State<TarjetaYapeAuto>
    with WidgetsBindingObserver {
  bool _activo = false;
  bool _permiso = false;
  bool _ocupado = false;
  int _confirmadas = 0;
  bool _cargado = false;
  List<String> _apps = const [];
  Map<String, String> _nombres = const {};

  String get _email => (appState.usuario?.email ?? '').trim().toLowerCase();

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _leer();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState s) {
    // Vuelve de Ajustes → ¿ya dio el acceso?
    if (s == AppLifecycleState.resumed) _leer();
  }

  Future<void> _leer() async {
    final loc = await YapeAutoService.estadoLocal();
    final permiso = await YapeAutoService.permisoActivo();
    if (!mounted) return;
    setState(() {
      _activo = loc['activo'] == true;
      _permiso = permiso;
      _cargado = true;
    });
    final srv = await YapeAutoService.estado(_email);
    if (!mounted || srv == null) return;
    if (_activo && srv['vinculado'] != true) {
      // Se vinculó otro celular (o la torre lo desvinculó): este queda apagado.
      await YapeAutoService.desactivar(_email);
      if (mounted) setState(() => _activo = false);
      return;
    }
    await YapeAutoService.sincronizar(
        _email, srv['paquetes'] is List ? srv['paquetes'] as List : null);
    final c = srv['confirmadas'];
    final apps = srv['apps'];
    if (mounted) {
      setState(() {
        _confirmadas = c is num ? c.toInt() : 0;
        _apps = [if (apps is List) for (final a in apps) a.toString()];
      });
    }
    if (widget.qr && _apps.isNotEmpty && _nombres.isEmpty) {
      final inst = await YapeAutoService.appsInstaladas();
      if (mounted) setState(() => _nombres = {for (final a in inst) a.$1: a.$2});
    }
  }

  Future<void> _encender() async {
    final ok = await confirmarPichangol(
      context,
      titulo: 'Confirmar pagos solos',
      mensaje: widget.qr
          ? '$kBrandName leerá en ESTE celular solo las notificaciones de la app '
              'donde recibes tus cobros por QR (la eliges en el siguiente paso) '
              'para reconocer el monto único que paga cada alumno y marcar su '
              'cuota como pagada. No leemos tus chats ni otras apps, y puedes '
              'apagarlo cuando quieras.\n\n'
              'Android te pedirá el permiso "Acceso a notificaciones" para '
              '$kBrandName.'
          : '$kBrandName leerá en ESTE celular solo las notificaciones de tu '
              'app Yape (monto, nombre y código de seguridad) para confirmar '
              'automáticamente los pagos que tus alumnos reportan. No leemos tus '
              'chats ni otras apps, y puedes apagarlo cuando quieras.\n\n'
              'En el siguiente paso Android te pedirá el permiso "Acceso a '
              'notificaciones" para $kBrandName.',
      textoConfirmar: 'Activar',
      textoCancelar: 'Ahora no',
      icono: Icons.notifications_active_outlined,
    );
    if (!ok || !mounted) return;
    setState(() => _ocupado = true);
    final r = await YapeAutoService.activar(_email);
    if (!mounted) return;
    setState(() => _ocupado = false);
    if (r['ok'] != true) {
      await avisarPichangol(context,
          titulo: 'No se pudo activar',
          mensaje: (r['mensaje'] ?? 'Reintenta en un momento.').toString(),
          icono: Icons.error_outline);
      return;
    }
    setState(() => _activo = true);
    if (widget.qr) {
      // Primero elige su app de cobros (sin ella no hay nada que escuchar).
      final r = await YapeAutoService.estado(_email);
      final ya = r?['apps'];
      if (ya is! List || ya.isEmpty) await _elegirApps();
      if (!mounted) return;
    }
    if (!await YapeAutoService.permisoActivo()) {
      await YapeAutoService.abrirPermiso();
    }
    await _leer();
  }

  /// Lista de apps instaladas para marcar dónde recibe los cobros por QR.
  Future<void> _elegirApps() async {
    final instaladas = await YapeAutoService.appsInstaladas();
    if (!mounted) return;
    if (instaladas.isEmpty) {
      await avisarPichangol(context,
          titulo: 'Actualiza $kBrandName',
          mensaje: 'Esta versión del app no puede listar tus apps de cobro. '
              'Actualiza $kBrandName e inténtalo otra vez.',
          icono: Icons.system_update_alt);
      return;
    }
    final elegidas = await showModalBottomSheet<List<String>>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Theme.of(context).colorScheme.surface,
      shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(24))),
      builder: (_) => _HojaAppsCobro(instaladas: instaladas, marcadas: _apps),
    );
    if (elegidas == null || !mounted) return;
    setState(() => _ocupado = true);
    final r = await YapeAutoService.elegirApps(_email, elegidas);
    if (!mounted) return;
    setState(() => _ocupado = false);
    if (r['ok'] != true) {
      await avisarPichangol(context,
          titulo: 'No se pudo guardar',
          mensaje: (r['mensaje'] ?? 'Reintenta en un momento.').toString(),
          icono: Icons.error_outline);
      return;
    }
    setState(() {
      _apps = elegidas;
      _nombres = {for (final a in instaladas) a.$1: a.$2};
    });
  }

  String _nombreApps() =>
      _apps.isEmpty ? 'ninguna' : _apps.map((p) => _nombres[p] ?? p).join(', ');

  Future<void> _apagar() async {
    final ok = await confirmarPichangol(
      context,
      titulo: '¿Apagar la confirmación automática?',
      mensaje: 'Seguirás recibiendo los pagos reportados por tus alumnos, '
          'pero tendrás que confirmarlos tú comparando el código de seguridad.',
      textoConfirmar: 'Apagar',
      textoCancelar: 'Mantener',
      destructivo: true,
    );
    if (!ok || !mounted) return;
    setState(() => _ocupado = true);
    await YapeAutoService.desactivar(_email);
    if (mounted) {
      setState(() {
        _ocupado = false;
        _activo = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    if (!YapeAutoService.soportado || !_cargado) return const SizedBox.shrink();
    final faltaPermiso = _activo && !_permiso;
    final String sub;
    if (!_activo) {
      sub = widget.qr
          ? 'Este celular lee la notificación de tu app de cobros y marca '
              'pagada la cuota del alumno que pagó el monto único.'
          : 'Este celular lee la notificación de tu Yape y confirma solo el '
              'pago del alumno con el mismo código de seguridad y monto.';
    } else if (widget.qr && _apps.isEmpty) {
      sub = 'Elige la app donde recibes tus cobros por QR.';
    } else if (faltaPermiso) {
      sub = 'Falta darle a $kBrandName el "Acceso a notificaciones".';
    } else {
      sub = _confirmadas > 0
          ? 'Activo en este celular · $_confirmadas '
              '${_confirmadas == 1 ? 'pago confirmado' : 'pagos confirmados'} solos (7 días).'
          : 'Activo en este celular. Los pagos que coincidan se confirman solos.';
    }
    return Container(
      decoration: BoxDecoration(
        color: faltaPermiso
            ? estadoWarnBg
            : Theme.of(context).colorScheme.surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: trazo),
      ),
      padding: const EdgeInsets.fromLTRB(14, 10, 8, 10),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const IconoVivo(Icons.notifications_active_outlined, size: 26),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text('Confirmar mis pagos automáticamente',
                        style: TextStyle(
                            fontWeight: FontWeight.w800, fontSize: 14.5)),
                    const SizedBox(height: 2),
                    Text(sub,
                        style: const TextStyle(
                            color: textoTenue, fontSize: 12.5)),
                  ],
                ),
              ),
              Switch(
                value: _activo,
                activeColor: lima,
                onChanged: _ocupado
                    ? null
                    : (v) => v ? _encender() : _apagar(),
              ),
            ],
          ),
          if (widget.qr && _activo) ...[
            const SizedBox(height: 6),
            Row(
              children: [
                Expanded(
                  child: Text('Apps de cobro: ${_nombreApps()}',
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(fontSize: 12.5)),
                ),
                TextButton(
                  onPressed: _ocupado ? null : _elegirApps,
                  child: Text(_apps.isEmpty ? 'Elegir' : 'Cambiar'),
                ),
              ],
            ),
          ],
          if (faltaPermiso) ...[
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              runSpacing: 4,
              children: [
                FilledButton(
                  style: FilledButton.styleFrom(backgroundColor: lima),
                  onPressed: () async {
                    await YapeAutoService.abrirPermiso();
                  },
                  child: const Text('Dar acceso'),
                ),
                TextButton(
                  onPressed: () async {
                    await avisarPichangol(
                      context,
                      titulo: '¿El interruptor sale bloqueado?',
                      mensaje: 'En algunos Android, si instalaste $kBrandName '
                          'fuera de Play, primero entra a Ajustes → Apps → '
                          '$kBrandName → ⋮ → "Permitir ajustes restringidos" y '
                          'vuelve a "Dar acceso".',
                      textoBoton: 'Abrir info de la app',
                      icono: Icons.lock_open_outlined,
                    );
                    await YapeAutoService.abrirInfoApp();
                  },
                  child: const Text('¿Sale bloqueado?'),
                ),
              ],
            ),
          ],
        ],
      ),
    );
  }
}


/// Hoja "¿Dónde recibes tus cobros?": apps instaladas con casillas (máx. 6) y
/// buscador. Devuelve los paquetes elegidos.
class _HojaAppsCobro extends StatefulWidget {
  const _HojaAppsCobro({required this.instaladas, required this.marcadas});
  final List<(String, String)> instaladas;
  final List<String> marcadas;

  @override
  State<_HojaAppsCobro> createState() => _HojaAppsCobroState();
}

class _HojaAppsCobroState extends State<_HojaAppsCobro> {
  late final Set<String> _sel = {...widget.marcadas};
  String _q = '';

  @override
  Widget build(BuildContext context) {
    final q = _q.trim().toLowerCase();
    final lista = widget.instaladas
        .where((a) => q.isEmpty || a.$2.toLowerCase().contains(q))
        .toList()
      ..sort((a, b) {
        final sa = _sel.contains(a.$1) ? 0 : 1, sb = _sel.contains(b.$1) ? 0 : 1;
        return sa != sb ? sa - sb : a.$2.toLowerCase().compareTo(b.$2.toLowerCase());
      });
    return SafeArea(
      child: Padding(
        padding: EdgeInsets.fromLTRB(
            20, 18, 20, 12 + MediaQuery.of(context).viewInsets.bottom),
        child: SizedBox(
          height: MediaQuery.of(context).size.height * 0.75,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text('¿Dónde recibes tus cobros por QR?',
                  style: TextStyle(fontWeight: FontWeight.w800, fontSize: 17)),
              const SizedBox(height: 4),
              const Text(
                  'Marca la app de tu banco o billetera (DeUna!, Banco '
                  'Pichincha, Banco Unión…). Solo leeremos SUS notificaciones.',
                  style: TextStyle(color: textoTenue, fontSize: 12.5)),
              const SizedBox(height: 10),
              TextField(
                onChanged: (v) => setState(() => _q = v),
                decoration: const InputDecoration(
                    hintText: 'Buscar app',
                    prefixIcon: Icon(Icons.search),
                    isDense: true),
              ),
              const SizedBox(height: 6),
              Expanded(
                child: ListView(
                  children: [
                    for (final a in lista)
                      CheckboxListTile(
                        value: _sel.contains(a.$1),
                        activeColor: lima,
                        dense: true,
                        contentPadding: EdgeInsets.zero,
                        title: Text(a.$2,
                            style: const TextStyle(fontWeight: FontWeight.w600)),
                        onChanged: (v) => setState(() {
                          if (v == true) {
                            if (_sel.length < 6) _sel.add(a.$1);
                          } else {
                            _sel.remove(a.$1);
                          }
                        }),
                      ),
                  ],
                ),
              ),
              const SizedBox(height: 8),
              SizedBox(
                width: double.infinity,
                child: FilledButton(
                  style: FilledButton.styleFrom(
                      backgroundColor: lima,
                      foregroundColor: Colors.white,
                      padding: const EdgeInsets.symmetric(vertical: 14)),
                  onPressed: _sel.isEmpty
                      ? null
                      : () => Navigator.of(context).pop(_sel.toList()),
                  child: Text(
                      _sel.isEmpty
                          ? 'Marca al menos una app'
                          : 'Guardar · ${_sel.length} ${_sel.length == 1 ? 'app' : 'apps'}',
                      style: const TextStyle(fontWeight: FontWeight.w800)),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
