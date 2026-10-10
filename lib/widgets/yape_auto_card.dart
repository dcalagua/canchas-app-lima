import 'package:flutter/material.dart';

import '../services/yape_auto_service.dart';
import '../state/app_state.dart';
import '../theme.dart';
import 'dialogo_pichangol.dart';
import 'icono_vivo.dart';

/// "Confirmar mis pagos automáticamente" (fase 2 del Plan Academia): el
/// celular Android de la academia lee la notificación de su Yape y Pichangol
/// confirma solo el pago del alumno con el mismo código de seguridad y monto.
/// Opt-in con aviso destacado (exigencia de Play para leer notificaciones) y
/// permiso que el dueño da a mano en Ajustes.
class TarjetaYapeAuto extends StatefulWidget {
  const TarjetaYapeAuto({super.key});

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
    if (mounted) setState(() => _confirmadas = c is num ? c.toInt() : 0);
  }

  Future<void> _encender() async {
    final ok = await confirmarPichangol(
      context,
      titulo: 'Confirmar pagos solos',
      mensaje: 'Pichangol leerá en ESTE celular solo las notificaciones de tu '
          'app Yape (monto, nombre y código de seguridad) para confirmar '
          'automáticamente los pagos que tus alumnos reportan. No leemos tus '
          'chats ni otras apps, y puedes apagarlo cuando quieras.\n\n'
          'En el siguiente paso Android te pedirá el permiso "Acceso a '
          'notificaciones" para Pichangol.',
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
    if (!await YapeAutoService.permisoActivo()) {
      await YapeAutoService.abrirPermiso();
    }
    await _leer();
  }

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
      sub = 'Este celular lee la notificación de tu Yape y confirma solo el '
          'pago del alumno con el mismo código de seguridad y monto.';
    } else if (faltaPermiso) {
      sub = 'Falta darle a Pichangol el "Acceso a notificaciones".';
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
                      mensaje: 'En algunos Android, si instalaste Pichangol '
                          'fuera de Play, primero entra a Ajustes → Apps → '
                          'Pichangol → ⋮ → "Permitir ajustes restringidos" y '
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
