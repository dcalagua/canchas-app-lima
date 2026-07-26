import 'package:flutter/material.dart';

import '../data/mensajes_repo.dart';
import '../models/mensaje.dart';
import '../models/models.dart';
import '../services/whatsapp_link.dart';
import '../state/app_state.dart';
import '../theme.dart';

/// ANTI NO-SHOW: recuerda a los jugadores su reserva próxima (hoy/mañana) para
/// que no se olviden ni dejen plantada la cancha. In-app (chat + push) a los que
/// tienen cuenta, WhatsApp a los que no. Recuerda a quién ya avisó.
class RecordarReservasScreen extends StatefulWidget {
  const RecordarReservasScreen({super.key});

  @override
  State<RecordarReservasScreen> createState() => _RecordarReservasScreenState();
}

class _RecordarReservasScreenState extends State<RecordarReservasScreen> {
  int _dia = 1; // 0 = hoy, 1 = mañana (lo típico: recordar la víspera)
  bool _enviando = false;

  DateTime get _fecha => DateTime.now().add(Duration(days: _dia));
  String get _iso => appState.isoDe(_fecha);
  String get _diaLabel => _dia == 0 ? 'hoy' : 'mañana';

  Cancha? _cancha(String id) {
    for (final c in appState.misCanchas) {
      if (c.id == id) return c;
    }
    return null;
  }

  String _nombreCancha(String id) {
    final c = _cancha(id);
    if (c == null) return 'la cancha';
    return c.club.isNotEmpty ? '${c.club} · ${c.nombre}' : c.nombre;
  }

  String _texto(Reserva r) =>
      'Hola ${r.jugador.isEmpty ? '' : '${r.jugador} '}🎾 Te recuerdo tu reserva '
      '$_diaLabel ${r.horaInicio} en ${_nombreCancha(r.canchaId)}. ¡Te esperamos! '
      'Si no puedes venir, avísame por aquí.';

  void _msg(String t) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(t)));
  }

  /// Envía el recordatorio de una reserva por el canal que corresponda y lo marca.
  Future<void> _recordar(Reserva r) async {
    final u = appState.usuario;
    if (u == null) return;
    if (r.usuario.trim().isNotEmpty) {
      final msg = Mensaje(
        id: 'msg_${DateTime.now().microsecondsSinceEpoch}_${r.id}',
        hilo: Mensaje.hiloCancha(u.email, r.usuario.trim().toLowerCase()),
        tipo: 'cancha',
        refId: u.email,
        cuentaEmail: r.usuario.trim().toLowerCase(),
        autorEmail: u.email,
        autorNombre: u.nombre,
        esProfe: true,
        texto: _texto(r),
        creado: DateTime.now(),
      );
      final ok = await MensajesRepo.enviar(msg);
      if (ok) appState.marcarReservaRecordada(r.id);
      if (mounted) {
        _msg(ok
            ? 'Le recordé a ${r.jugador} por la app 📲'
            : 'No se pudo enviar por la app.');
      }
    } else if (r.telefono.trim().isNotEmpty) {
      await WhatsAppLink.abrir(r.telefono.trim(), _texto(r));
      appState.marcarReservaRecordada(r.id);
    } else {
      _msg('${r.jugador} no tiene forma de contacto.');
    }
  }

  Future<void> _recordarATodos(List<Reserva> pendientes) async {
    final conApp =
        pendientes.where((r) => r.usuario.trim().isNotEmpty).toList();
    final sinApp = pendientes
        .where((r) => r.usuario.trim().isEmpty && r.telefono.trim().isNotEmpty)
        .toList();
    setState(() => _enviando = true);
    var enviados = 0;
    final u = appState.usuario;
    if (u != null) {
      for (final r in conApp) {
        final msg = Mensaje(
          id: 'msg_${DateTime.now().microsecondsSinceEpoch}_${r.id}',
          hilo: Mensaje.hiloCancha(u.email, r.usuario.trim().toLowerCase()),
          tipo: 'cancha',
          refId: u.email,
          cuentaEmail: r.usuario.trim().toLowerCase(),
          autorEmail: u.email,
          autorNombre: u.nombre,
          esProfe: true,
          texto: _texto(r),
          creado: DateTime.now(),
        );
        if (await MensajesRepo.enviar(msg)) {
          appState.marcarReservaRecordada(r.id);
          enviados++;
        }
      }
    }
    if (!mounted) return;
    setState(() => _enviando = false);
    if (enviados > 0) _msg('✅ Recordé a $enviados jugador(es) por la app 📲');
    if (sinApp.isNotEmpty) await _whatsappSheet(sinApp);
  }

  Future<void> _whatsappSheet(List<Reserva> reservas) async {
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Theme.of(context).colorScheme.surface,
      shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(24))),
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setSt) => DraggableScrollableSheet(
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
                  child: Text('Recordar por WhatsApp',
                      style:
                          TextStyle(fontWeight: FontWeight.w800, fontSize: 18)),
                ),
              ),
              const Padding(
                padding: EdgeInsets.fromLTRB(20, 0, 20, 8),
                child: Align(
                  alignment: Alignment.centerLeft,
                  child: Text('Estos jugadores no tienen la app. Toca “Enviar”.',
                      style: TextStyle(color: textoTenue, fontSize: 12.5)),
                ),
              ),
              Expanded(
                child: ListView.separated(
                  controller: scroll,
                  itemCount: reservas.length,
                  separatorBuilder: (_, __) =>
                      Divider(height: 1, color: trazo.withOpacity(0.6)),
                  itemBuilder: (_, i) {
                    final r = reservas[i];
                    final ya = appState.reservaRecordada(r.id);
                    return ListTile(
                      leading: CircleAvatar(
                          backgroundColor: teal,
                          child: Text(
                              r.jugador.isNotEmpty
                                  ? r.jugador[0].toUpperCase()
                                  : '?',
                              style: const TextStyle(
                                  color: Colors.white,
                                  fontWeight: FontWeight.w800))),
                      title: Text(r.jugador.isEmpty ? 'Cliente' : r.jugador,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(fontWeight: FontWeight.w700)),
                      subtitle: Text('${r.horaInicio} · ${_nombreCancha(r.canchaId)}',
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                              color: textoTenue, fontSize: 12.5)),
                      trailing: ya
                          ? const Icon(Icons.check_circle, color: lima)
                          : FilledButton(
                              style: FilledButton.styleFrom(
                                  backgroundColor: verde,
                                  foregroundColor: Colors.white),
                              onPressed: () async {
                                await WhatsAppLink.abrir(
                                    r.telefono.trim(), _texto(r));
                                appState.marcarReservaRecordada(r.id);
                                setSt(() {});
                              },
                              child: const Text('Enviar'),
                            ),
                    );
                  },
                ),
              ),
            ],
          ),
        ),
      ),
    );
    if (mounted) setState(() {});
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Recordar reservas')),
      body: ListenableBuilder(
        listenable: appState,
        builder: (context, _) {
          final reservas = appState.reservasDelDiaDueno(_iso);
          final pendientes = reservas
              .where((r) =>
                  !appState.reservaRecordada(r.id) &&
                  (r.usuario.trim().isNotEmpty || r.telefono.trim().isNotEmpty))
              .toList();
          return Column(
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
                child: Row(
                  children: [
                    _Chip('Hoy', _dia == 0, () => setState(() => _dia = 0)),
                    const SizedBox(width: 10),
                    _Chip('Mañana', _dia == 1, () => setState(() => _dia = 1)),
                  ],
                ),
              ),
              Expanded(
                child: reservas.isEmpty
                    ? Center(
                        child: Padding(
                          padding: const EdgeInsets.all(28),
                          child: Text('No hay reservas $_diaLabel.',
                              style: TextStyle(color: textoTenueDe(context))),
                        ),
                      )
                    : ListView(
                        padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
                        children: [
                          for (final r in reservas)
                            _FilaReserva(
                              reserva: r,
                              cancha: _nombreCancha(r.canchaId),
                              recordada: appState.reservaRecordada(r.id),
                              onRecordar: () => _recordar(r),
                            ),
                        ],
                      ),
              ),
              SafeArea(
                top: false,
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(16, 6, 16, 12),
                  child: SizedBox(
                    height: 50,
                    child: FilledButton.icon(
                      style: FilledButton.styleFrom(
                          backgroundColor: lima,
                          foregroundColor: Colors.white,
                          shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(14))),
                      onPressed: (_enviando || pendientes.isEmpty)
                          ? null
                          : () => _recordarATodos(pendientes),
                      icon: _enviando
                          ? const SizedBox(
                              width: 20,
                              height: 20,
                              child: CircularProgressIndicator(
                                  strokeWidth: 2, color: Colors.white))
                          : const Icon(Icons.notifications_active),
                      label: Text(
                          pendientes.isEmpty
                              ? 'Todos recordados ✓'
                              : 'Recordar a todos (${pendientes.length})',
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
}

class _Chip extends StatelessWidget {
  const _Chip(this.texto, this.sel, this.onTap);
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

class _FilaReserva extends StatelessWidget {
  const _FilaReserva({
    required this.reserva,
    required this.cancha,
    required this.recordada,
    required this.onRecordar,
  });
  final Reserva reserva;
  final String cancha;
  final bool recordada;
  final VoidCallback onRecordar;

  @override
  Widget build(BuildContext context) {
    final r = reserva;
    final sinContacto = r.usuario.trim().isEmpty && r.telefono.trim().isEmpty;
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.fromLTRB(12, 8, 8, 8),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: trazo),
      ),
      child: Row(
        children: [
          Text(r.horaInicio,
              style: const TextStyle(
                  fontWeight: FontWeight.w800, fontSize: 13)),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(r.jugador.isEmpty ? 'Cliente' : r.jugador,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(fontWeight: FontWeight.w700)),
                Text(cancha,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(color: textoTenue, fontSize: 12)),
              ],
            ),
          ),
          if (recordada)
            const Padding(
              padding: EdgeInsets.only(right: 6),
              child: Row(mainAxisSize: MainAxisSize.min, children: [
                Icon(Icons.check_circle, size: 16, color: lima),
                SizedBox(width: 3),
                Text('recordado',
                    style: TextStyle(
                        color: lima,
                        fontSize: 11.5,
                        fontWeight: FontWeight.w700)),
              ]),
            )
          else if (sinContacto)
            const Text('sin contacto',
                style: TextStyle(color: textoTenue, fontSize: 11.5))
          else
            OutlinedButton(
              style: OutlinedButton.styleFrom(
                  foregroundColor: lima,
                  side: const BorderSide(color: lima),
                  padding: const EdgeInsets.symmetric(horizontal: 12)),
              onPressed: onRecordar,
              child: const Text('Recordar'),
            ),
        ],
      ),
    );
  }
}
