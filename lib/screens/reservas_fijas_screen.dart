import 'package:flutter/material.dart';

import '../models/reserva_fija.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/dialogo_pichangol.dart';

/// RESERVAS FIJAS ("pensionados"): el dueño registra a los clientes que juegan
/// SIEMPRE el mismo día y hora, y el app genera solas las reservas de las
/// próximas semanas. Ingreso estable sin anotarlo a mano cada vez.
class ReservasFijasScreen extends StatelessWidget {
  const ReservasFijasScreen({super.key});

  static const _dias = [
    'Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo'
  ];

  String _nombreCancha(String canchaId) {
    for (final c in appState.misCanchas) {
      if (c.id == canchaId) {
        return c.club.isNotEmpty ? '${c.club} · ${c.nombre}' : c.nombre;
      }
    }
    return 'Cancha';
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Reservas fijas')),
      floatingActionButton: appState.misCanchas.isEmpty
          ? null
          : FloatingActionButton.extended(
              backgroundColor: lima,
              foregroundColor: Colors.white,
              icon: const Icon(Icons.add),
              label: const Text('Cliente fijo'),
              onPressed: () => _agregar(context),
            ),
      body: ListenableBuilder(
        listenable: appState,
        builder: (context, _) {
          if (appState.misCanchas.isEmpty) {
            return const Center(
              child: Padding(
                padding: EdgeInsets.all(28),
                child: Text('Registra una cancha para tener clientes fijos.',
                    textAlign: TextAlign.center,
                    style: TextStyle(color: textoTenue)),
              ),
            );
          }
          final fijas = appState.misReservasFijas;
          return ListView(
            padding: const EdgeInsets.fromLTRB(16, 14, 16, 90),
            children: [
              const Text('Tus pensionados',
                  style: TextStyle(fontWeight: FontWeight.w800, fontSize: 19)),
              const SizedBox(height: 4),
              const Text(
                  'El equipo que juega siempre el mismo día y hora. El app crea '
                  'solo sus reservas de las próximas 4 semanas.',
                  style: TextStyle(color: textoTenue, fontSize: 13)),
              const SizedBox(height: 16),
              if (fijas.isEmpty)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 30),
                  child: Column(
                    children: [
                      const Icon(Icons.event_repeat,
                          size: 52, color: textoTenue),
                      const SizedBox(height: 10),
                      Text('Aún no tienes clientes fijos.',
                          style: TextStyle(color: textoTenueDe(context))),
                    ],
                  ),
                )
              else
                for (final f in fijas)
                  _FilaFija(
                    fija: f,
                    dia: _dias[(f.diaSemana - 1).clamp(0, 6)],
                    cancha: _nombreCancha(f.canchaId),
                  ),
            ],
          );
        },
      ),
    );
  }

  Future<void> _agregar(BuildContext context) async {
    final mias = appState.misCanchas;
    var canchaId = mias.first.id;
    var dia = DateTime.now().weekday; // 1..7
    String? hora;
    final nombre = TextEditingController();
    final tel = TextEditingController();
    String? error;

    List<String> slotsDe(String id) {
      for (final c in mias) {
        if (c.id == id) return c.horariosSlots();
      }
      return const [];
    }

    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Theme.of(context).colorScheme.surface,
      shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(24))),
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setSt) {
          final slots = slotsDe(canchaId);
          if (hora != null && !slots.contains(hora)) hora = null;
          return Padding(
            padding: EdgeInsets.fromLTRB(
                18, 18, 18, MediaQuery.of(ctx).viewInsets.bottom + 18),
            child: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('Nuevo cliente fijo',
                      style:
                          TextStyle(fontWeight: FontWeight.w800, fontSize: 18)),
                  const SizedBox(height: 14),
                  _Label('Cancha'),
                  DropdownButtonFormField<String>(
                    value: canchaId,
                    isExpanded: true,
                    decoration: _dec(ctx),
                    items: [
                      for (final c in mias)
                        DropdownMenuItem(
                          value: c.id,
                          child: Text(
                              c.club.isNotEmpty
                                  ? '${c.club} · ${c.nombre}'
                                  : c.nombre,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis),
                        ),
                    ],
                    onChanged: (v) => setSt(() => canchaId = v ?? canchaId),
                  ),
                  const SizedBox(height: 12),
                  _Label('Día de la semana'),
                  DropdownButtonFormField<int>(
                    value: dia,
                    isExpanded: true,
                    decoration: _dec(ctx),
                    items: [
                      for (var i = 1; i <= 7; i++)
                        DropdownMenuItem(value: i, child: Text(_dias[i - 1])),
                    ],
                    onChanged: (v) => setSt(() => dia = v ?? dia),
                  ),
                  const SizedBox(height: 12),
                  _Label('Hora'),
                  DropdownButtonFormField<String>(
                    value: hora,
                    isExpanded: true,
                    decoration: _dec(ctx, hint: 'Elige la hora'),
                    items: [
                      for (final h in slots)
                        DropdownMenuItem(value: h, child: Text(h)),
                    ],
                    onChanged: (v) => setSt(() => hora = v),
                  ),
                  const SizedBox(height: 12),
                  _Label('Cliente'),
                  TextField(
                    controller: nombre,
                    textCapitalization: TextCapitalization.words,
                    decoration: _dec(ctx, hint: 'Nombre del cliente/equipo'),
                  ),
                  const SizedBox(height: 10),
                  TextField(
                    controller: tel,
                    keyboardType: TextInputType.phone,
                    decoration: _dec(ctx, hint: 'WhatsApp (opcional)'),
                  ),
                  if (error != null) ...[
                    const SizedBox(height: 8),
                    Text(error!,
                        style:
                            const TextStyle(color: clayOscuro, fontSize: 13)),
                  ],
                  const SizedBox(height: 18),
                  SizedBox(
                    width: double.infinity,
                    height: 50,
                    child: FilledButton(
                      style: FilledButton.styleFrom(
                          backgroundColor: lima, foregroundColor: Colors.white),
                      onPressed: () async {
                        if (hora == null) {
                          setSt(() => error = 'Elige la hora.');
                          return;
                        }
                        if (nombre.text.trim().isEmpty) {
                          setSt(() => error = 'Escribe el nombre del cliente.');
                          return;
                        }
                        await appState.agregarReservaFija(
                          canchaId: canchaId,
                          diaSemana: dia,
                          hora: hora!,
                          clienteNombre: nombre.text,
                          clienteTelefono: tel.text,
                        );
                        if (ctx.mounted) Navigator.pop(ctx);
                      },
                      child: const Text('Guardar y generar reservas',
                          style: TextStyle(fontWeight: FontWeight.w800)),
                    ),
                  ),
                ],
              ),
            ),
          );
        },
      ),
    );
  }

  InputDecoration _dec(BuildContext ctx, {String? hint}) => InputDecoration(
        hintText: hint,
        isDense: true,
        filled: true,
        fillColor: Theme.of(ctx).colorScheme.surface,
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

class _Label extends StatelessWidget {
  const _Label(this.t);
  final String t;
  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(bottom: 6),
        child: Text(t,
            style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 13)),
      );
}

class _FilaFija extends StatelessWidget {
  const _FilaFija(
      {required this.fija, required this.dia, required this.cancha});
  final ReservaFija fija;
  final String dia;
  final String cancha;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: trazo),
      ),
      child: ListTile(
        leading: CircleAvatar(
          backgroundColor: fija.activo ? lima.withOpacity(0.15) : trazo,
          child: Icon(Icons.event_repeat,
              color: fija.activo ? lima : textoTenue),
        ),
        title: Text(
            fija.clienteNombre.isEmpty ? 'Cliente' : fija.clienteNombre,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(fontWeight: FontWeight.w700)),
        subtitle: Text('$dia · ${fija.hora} · $cancha',
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(color: textoTenue, fontSize: 12.5)),
        trailing: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Switch(
              value: fija.activo,
              onChanged: (v) => appState.pausarReservaFija(fija.id, v),
            ),
            IconButton(
              tooltip: 'Eliminar',
              icon: const Icon(Icons.delete_outline, color: textoTenue),
              onPressed: () => _confirmarBorrar(context),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _confirmarBorrar(BuildContext context) async {
    final ok = await confirmarPichangol(
      context,
      titulo: 'Quitar cliente fijo',
      mensaje: 'Se deja de generar sus reservas. Las que ya están creadas siguen '
          'en tu agenda (puedes cancelarlas aparte).',
      textoConfirmar: 'Quitar',
      destructivo: true,
      icono: Icons.person_remove_outlined,
    );
    if (ok) appState.quitarReservaFija(fija.id);
  }
}
