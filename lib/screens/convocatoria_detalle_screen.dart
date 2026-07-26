import 'package:flutter/material.dart';

import '../models/convocatoria.dart';
import '../services/convocatorias_service.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/cargando_pichangol.dart';
import 'convocatorias_screen.dart' show EstadoChip, ModoChip;
import 'login_google_sheet.dart';

/// Ficha de una convocatoria: el jugador ve su estado y se anota / cancela; el
/// dueño (admin) cierra la convocatoria, la reabre y marca asistencia.
class ConvocatoriaDetalleScreen extends StatefulWidget {
  final int convId;
  const ConvocatoriaDetalleScreen({super.key, required this.convId});

  @override
  State<ConvocatoriaDetalleScreen> createState() =>
      _ConvocatoriaDetalleScreenState();
}

class _ConvocatoriaDetalleScreenState extends State<ConvocatoriaDetalleScreen> {
  ConvocatoriaDetalle? _detalle;
  bool _cargando = true;
  bool _ocupado = false; // acción en curso (anotarse/cancelar/cerrar)

  bool get _esAdmin => appState.sesionIniciada;
  String? get _miEmail => appState.usuario?.email;

  @override
  void initState() {
    super.initState();
    _cargar();
  }

  Future<void> _cargar() async {
    setState(() => _cargando = true);
    final d = await ConvocatoriasService.detalle(widget.convId,
        socio: _miEmail ?? '');
    if (!mounted) return;
    setState(() {
      _detalle = d;
      _cargando = false;
    });
  }

  void _aviso(String msg, {bool error = false}) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
      content: Text(msg),
      backgroundColor: error ? estadoBadFg : bosque,
    ));
  }

  Future<void> _anotarme() async {
    if (!await LoginGoogleSheet.mostrar(context,
        motivo: 'anotarte a esta convocatoria')) {
      return;
    }
    if (!mounted) return;
    final email = appState.usuario?.email;
    if (email == null || email.isEmpty) return;
    setState(() => _ocupado = true);
    Map<String, dynamic>? res;
    try {
      res = await conPreload(
          context,
          () => ConvocatoriasService.inscribir(
              widget.convId, email, appState.usuario?.nombre ?? email),
          texto: 'Anotándote…');
    } finally {
      if (mounted) setState(() => _ocupado = false);
    }
    if (!mounted) return;
    // Copia a un final: Dart no promueve una variable asignada dentro de `try`.
    final r = res;
    if (r == null || r['ok'] != true) {
      _aviso(_mensajeError(r), error: true);
      return;
    }
    final estado = r['estado_efectivo'] as String?;
    _aviso(switch (estado) {
      'confirmado' => '¡Estás dentro! Cupo confirmado.',
      'lista_espera' => 'Entraste a la lista de espera (puesto ${r['posicion']}).',
      'en_bolsa' => 'Anotado. Los cupos se definen al cerrar la inscripción.',
      _ => 'Anotado.',
    });
    _cargar();
  }

  Future<void> _cancelar() async {
    final email = _miEmail;
    if (email == null) return;
    final ok = await _confirmar('¿Cancelar tu inscripción?',
        'Si te cancelas, tu cupo pasa al primero de la lista de espera.');
    if (ok != true) return;
    setState(() => _ocupado = true);
    final r = await ConvocatoriasService.cancelar(widget.convId, email);
    setState(() => _ocupado = false);
    if (r == null || r['ok'] != true) {
      _aviso('No se pudo cancelar. Intenta de nuevo.', error: true);
      return;
    }
    _aviso('Inscripción cancelada.');
    _cargar();
  }

  Future<void> _cerrar() async {
    final ok = await _confirmar('¿Cerrar la inscripción?',
        'Se resolverá la asignación final según el modo y no se podrán anotar más socios.');
    if (ok != true) return;
    setState(() => _ocupado = true);
    final r = await ConvocatoriasService.cerrar(widget.convId);
    setState(() => _ocupado = false);
    if (r == null || r['ok'] != true) {
      _aviso('No se pudo cerrar.', error: true);
      return;
    }
    _aviso('Convocatoria cerrada. Cupos asignados.');
    _cargar();
  }

  Future<void> _reabrir() async {
    final ok = await _confirmar('¿Reabrir la convocatoria?',
        'Vuelve a estado abierto para recibir inscripciones.');
    if (ok != true) return;
    setState(() => _ocupado = true);
    final r = await ConvocatoriasService.reabrir(widget.convId);
    setState(() => _ocupado = false);
    if (r == null || r['ok'] != true) {
      _aviso('No se pudo reabrir.', error: true);
      return;
    }
    _cargar();
  }

  Future<void> _marcarAsistencia() async {
    final d = _detalle;
    if (d == null) return;
    final seleccion = {for (final i in d.confirmados) i.socioId: i.asistio ?? true};
    final resultado = await showModalBottomSheet<Map<String, bool>>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Theme.of(context).colorScheme.surface,
      shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(20))),
      builder: (ctx) => _AsistenciaSheet(
          confirmados: d.confirmados, seleccionInicial: seleccion),
    );
    if (resultado == null) return;
    setState(() => _ocupado = true);
    final r = await ConvocatoriasService.asistencia(widget.convId, resultado);
    setState(() => _ocupado = false);
    if (r == null || r['ok'] != true) {
      _aviso('No se pudo guardar la asistencia.', error: true);
      return;
    }
    _aviso('Asistencia guardada (${r['marcadas']} socios).');
    _cargar();
  }

  String _mensajeError(Map<String, dynamic>? r) {
    return switch (r?['error']) {
      'convocatoria_cerrada' => 'La inscripción ya está cerrada.',
      'inscripcion_cerrada' => 'La inscripción ya cerró.',
      'aun_no_abre' => 'La inscripción aún no abre.',
      _ => 'No se pudo anotar. Intenta de nuevo.',
    };
  }

  Future<bool?> _confirmar(String titulo, String cuerpo) {
    return showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(titulo),
        content: Text(cuerpo),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('No')),
          FilledButton(
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('Sí')),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final d = _detalle;
    return Scaffold(
      appBar: AppBar(title: Text(d?.convocatoria.titulo ?? 'Pichanga')),
      body: _cargando
          ? const CargandoPichangol()
          : d == null
              ? _ErrorCarga(onReintentar: _cargar)
              : RefreshIndicator(
                  onRefresh: _cargar,
                  child: ListView(
                    padding: const EdgeInsets.fromLTRB(16, 16, 16, 40),
                    children: [
                      _Cabecera(conv: d.convocatoria),
                      const SizedBox(height: 16),
                      _MiEstadoBanner(detalle: d),
                      const SizedBox(height: 16),
                      _AccionesJugador(
                        detalle: d,
                        ocupado: _ocupado,
                        onAnotarme: _anotarme,
                        onCancelar: _cancelar,
                      ),
                      if (_esAdmin) ...[
                        const SizedBox(height: 8),
                        _PanelAdmin(
                          detalle: d,
                          ocupado: _ocupado,
                          onCerrar: _cerrar,
                          onReabrir: _reabrir,
                          onAsistencia: _marcarAsistencia,
                        ),
                      ],
                      const SizedBox(height: 20),
                      _ListaInscritos(
                        titulo: 'Confirmados',
                        icono: Icons.check_circle,
                        color: estadoOkFg,
                        inscritos: d.confirmados,
                        cerrada: d.convocatoria.cerrada,
                        miEmail: _miEmail,
                        mostrarPosicion: false,
                      ),
                      if (d.listaEspera.isNotEmpty) ...[
                        const SizedBox(height: 16),
                        _ListaInscritos(
                          titulo: 'Lista de espera',
                          icono: Icons.hourglass_bottom,
                          color: estadoWarnFg,
                          inscritos: d.listaEspera,
                          cerrada: d.convocatoria.cerrada,
                          miEmail: _miEmail,
                          mostrarPosicion: true,
                        ),
                      ],
                    ],
                  ),
                ),
    );
  }
}

class _Cabecera extends StatelessWidget {
  final Convocatoria conv;
  const _Cabecera({required this.conv});

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(conv.titulo,
            style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 22)),
        const SizedBox(height: 10),
        Wrap(
          spacing: 8,
          runSpacing: 6,
          children: [
            EstadoChip(
              texto: conv.cerrada ? 'Cerrada' : 'Abierta',
              bg: conv.cerrada ? estadoNeutroBg : estadoOkBg,
              fg: conv.cerrada ? estadoNeutroFg : estadoOkFg,
            ),
            if (conv.categoria != null && conv.categoria!.isNotEmpty)
              EstadoChip(
                  texto: conv.categoria!, bg: estadoInfoBg, fg: estadoInfoFg),
            ModoChip(modo: conv.modo),
            if (conv.fechaPartido != null && conv.fechaPartido!.isNotEmpty)
              EstadoChip(
                  texto: conv.fechaPartido!,
                  bg: estadoNeutroBg,
                  fg: estadoNeutroFg,
                  icono: Icons.event),
          ],
        ),
        const SizedBox(height: 8),
        Text(conv.modo.descripcion, style: TextStyle(color: textoTenue)),
      ],
    );
  }
}

class _MiEstadoBanner extends StatelessWidget {
  final ConvocatoriaDetalle detalle;
  const _MiEstadoBanner({required this.detalle});

  @override
  Widget build(BuildContext context) {
    final (icono, texto, sub, bg, fg) = switch (detalle.miEstado) {
      EstadoSocio.confirmado => (
          Icons.check_circle,
          '¡Estás dentro!',
          'Tu cupo está confirmado.',
          estadoOkBg,
          estadoOkFg
        ),
      EstadoSocio.listaEspera => (
          Icons.hourglass_bottom,
          'En lista de espera',
          'Puesto ${detalle.miPosicion ?? '-'}. Si alguien cancela, subes.',
          estadoWarnBg,
          estadoWarnFg
        ),
      EstadoSocio.enBolsa => (
          Icons.casino_outlined,
          'Anotado — en la bolsa',
          'Los cupos se definen al cerrar la inscripción.',
          estadoInfoBg,
          estadoInfoFg
        ),
      EstadoSocio.sinInscripcion => (
          Icons.info_outline,
          'No estás anotado',
          detalle.convocatoria.cerrada
              ? 'La inscripción está cerrada.'
              : 'Anótate mientras haya cupo.',
          estadoNeutroBg,
          estadoNeutroFg
        ),
    };
    return Container(
      padding: const EdgeInsets.all(14),
      decoration:
          BoxDecoration(color: bg, borderRadius: BorderRadius.circular(12)),
      child: Row(
        children: [
          Icon(icono, color: fg),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(texto,
                    style: TextStyle(color: fg, fontWeight: FontWeight.w800)),
                const SizedBox(height: 2),
                Text(sub, style: TextStyle(color: fg.withOpacity(0.9), fontSize: 13)),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _AccionesJugador extends StatelessWidget {
  final ConvocatoriaDetalle detalle;
  final bool ocupado;
  final VoidCallback onAnotarme;
  final VoidCallback onCancelar;
  const _AccionesJugador({
    required this.detalle,
    required this.ocupado,
    required this.onAnotarme,
    required this.onCancelar,
  });

  @override
  Widget build(BuildContext context) {
    final anotado = detalle.miEstado != EstadoSocio.sinInscripcion;
    final cerrada = detalle.convocatoria.cerrada;
    if (cerrada && !anotado) return const SizedBox.shrink();
    if (anotado) {
      return OutlinedButton.icon(
        onPressed: ocupado || cerrada ? null : onCancelar,
        style: OutlinedButton.styleFrom(
            foregroundColor: estadoBadFg,
            side: const BorderSide(color: estadoBadFg, width: 1.3)),
        icon: const Icon(Icons.close),
        label: Text(cerrada ? 'Inscripción cerrada' : 'Cancelar mi inscripción'),
      );
    }
    return FilledButton.icon(
      onPressed: ocupado ? null : onAnotarme,
      icon: const Icon(Icons.how_to_reg),
      label: const Text('Anotarme'),
    );
  }
}

class _PanelAdmin extends StatelessWidget {
  final ConvocatoriaDetalle detalle;
  final bool ocupado;
  final VoidCallback onCerrar;
  final VoidCallback onReabrir;
  final VoidCallback onAsistencia;
  const _PanelAdmin({
    required this.detalle,
    required this.ocupado,
    required this.onCerrar,
    required this.onReabrir,
    required this.onAsistencia,
  });

  @override
  Widget build(BuildContext context) {
    final cerrada = detalle.convocatoria.cerrada;
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: papelCalido,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: trazo),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(Icons.admin_panel_settings, size: 18, color: bosque),
              const SizedBox(width: 8),
              const Text('Panel del dueño',
                  style: TextStyle(fontWeight: FontWeight.w800)),
            ],
          ),
          const SizedBox(height: 12),
          if (!cerrada)
            SizedBox(
              width: double.infinity,
              child: FilledButton.icon(
                onPressed: ocupado ? null : onCerrar,
                icon: const Icon(Icons.lock_clock),
                label: const Text('Cerrar inscripción y asignar cupos'),
              ),
            )
          else ...[
            SizedBox(
              width: double.infinity,
              child: FilledButton.icon(
                onPressed: ocupado ? null : onAsistencia,
                icon: const Icon(Icons.fact_check_outlined),
                label: const Text('Marcar asistencia'),
              ),
            ),
            const SizedBox(height: 8),
            SizedBox(
              width: double.infinity,
              child: OutlinedButton.icon(
                onPressed: ocupado ? null : onReabrir,
                icon: const Icon(Icons.lock_open),
                label: const Text('Reabrir inscripción'),
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _ListaInscritos extends StatelessWidget {
  final String titulo;
  final IconData icono;
  final Color color;
  final List<Inscripcion> inscritos;
  final bool cerrada;
  final String? miEmail;
  final bool mostrarPosicion;
  const _ListaInscritos({
    required this.titulo,
    required this.icono,
    required this.color,
    required this.inscritos,
    required this.cerrada,
    required this.miEmail,
    required this.mostrarPosicion,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Icon(icono, size: 18, color: color),
            const SizedBox(width: 8),
            Text('$titulo (${inscritos.length})',
                style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 16)),
          ],
        ),
        const SizedBox(height: 8),
        if (inscritos.isEmpty)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 8),
            child: Text('Nadie todavía.', style: TextStyle(color: textoTenue)),
          )
        else
          Card(
            child: Column(
              children: [
                for (var i = 0; i < inscritos.length; i++)
                  _FilaInscrito(
                    orden: i + 1,
                    insc: inscritos[i],
                    cerrada: cerrada,
                    soyYo: inscritos[i].socioId == miEmail,
                    mostrarPosicion: mostrarPosicion,
                    divisor: i < inscritos.length - 1,
                  ),
              ],
            ),
          ),
      ],
    );
  }
}

class _FilaInscrito extends StatelessWidget {
  final int orden;
  final Inscripcion insc;
  final bool cerrada;
  final bool soyYo;
  final bool mostrarPosicion;
  final bool divisor;
  const _FilaInscrito({
    required this.orden,
    required this.insc,
    required this.cerrada,
    required this.soyYo,
    required this.mostrarPosicion,
    required this.divisor,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        border: divisor
            ? const Border(bottom: BorderSide(color: trazo))
            : null,
      ),
      child: ListTile(
        leading: CircleAvatar(
          radius: 16,
          backgroundColor: soyYo ? lima : limaSuave,
          child: Text('$orden',
              style: TextStyle(
                  color: soyYo ? Colors.white : bosque,
                  fontWeight: FontWeight.w700,
                  fontSize: 13)),
        ),
        title: Text(
          insc.socioNombre + (soyYo ? '  (tú)' : ''),
          style: TextStyle(
              fontWeight: soyYo ? FontWeight.w800 : FontWeight.w600),
          overflow: TextOverflow.ellipsis,
        ),
        trailing: cerrada && insc.asistio != null
            ? EstadoChip(
                texto: insc.asistio! ? 'Asistió' : 'No-show',
                bg: insc.asistio! ? estadoOkBg : estadoBadBg,
                fg: insc.asistio! ? estadoOkFg : estadoBadFg,
              )
            : null,
      ),
    );
  }
}

class _AsistenciaSheet extends StatefulWidget {
  final List<Inscripcion> confirmados;
  final Map<String, bool> seleccionInicial;
  const _AsistenciaSheet(
      {required this.confirmados, required this.seleccionInicial});

  @override
  State<_AsistenciaSheet> createState() => _AsistenciaSheetState();
}

class _AsistenciaSheetState extends State<_AsistenciaSheet> {
  late final Map<String, bool> _sel = Map.of(widget.seleccionInicial);

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(
          bottom: MediaQuery.of(context).viewInsets.bottom + 16,
          top: 12,
          left: 16,
          right: 16),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Center(
            child: Container(
              width: 44,
              height: 5,
              decoration: BoxDecoration(
                  color: Colors.black12,
                  borderRadius: BorderRadius.circular(10)),
            ),
          ),
          const SizedBox(height: 14),
          const Text('¿Quién asistió?',
              style: TextStyle(fontWeight: FontWeight.w800, fontSize: 18)),
          const SizedBox(height: 2),
          Text('Marca a los que jugaron. Alimenta el ranking y la equidad.',
              style: TextStyle(color: textoTenue, fontSize: 13)),
          const SizedBox(height: 8),
          Flexible(
            child: ListView(
              shrinkWrap: true,
              children: [
                for (final i in widget.confirmados)
                  SwitchListTile(
                    contentPadding: EdgeInsets.zero,
                    title: Text(i.socioNombre,
                        overflow: TextOverflow.ellipsis),
                    value: _sel[i.socioId] ?? true,
                    onChanged: (v) => setState(() => _sel[i.socioId] = v),
                  ),
              ],
            ),
          ),
          const SizedBox(height: 8),
          FilledButton(
            onPressed: () => Navigator.pop(context, _sel),
            child: const Text('Guardar asistencia'),
          ),
        ],
      ),
    );
  }
}

class _ErrorCarga extends StatelessWidget {
  final VoidCallback onReintentar;
  const _ErrorCarga({required this.onReintentar});

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.cloud_off, size: 44, color: textoTenue),
          const SizedBox(height: 12),
          const Text('No se pudo cargar la pichanga'),
          const SizedBox(height: 12),
          OutlinedButton(
              onPressed: onReintentar, child: const Text('Reintentar')),
        ],
      ),
    );
  }
}
