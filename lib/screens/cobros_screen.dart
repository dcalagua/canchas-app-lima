import 'package:flutter/material.dart';

import '../data/mensajes_repo.dart';
import '../models/academia.dart';
import '../models/mensaje.dart';
import '../services/whatsapp_link.dart';
import '../state/app_state.dart';
import '../theme.dart';
import 'mi_academia_screen.dart' show AlumnoDetalleScreen;

/// TABLERO DE COBROS de la academia: lo que el profe abre a diario para cobrar.
/// Muestra cuánto tiene por cobrar / vencido / cobrado este mes, la lista de
/// morosos ordenada, y RECORDATORIOS: el app detecta solo a quién toca recordar,
/// recuerda cuándo se le avisó por última vez (para no repetir), y permite mandar
/// el recordatorio por WhatsApp de a uno o a todos.
class CobrosScreen extends StatefulWidget {
  const CobrosScreen({super.key, required this.academiaId});
  final String academiaId;

  @override
  State<CobrosScreen> createState() => _CobrosScreenState();
}

class _CobrosScreenState extends State<CobrosScreen> {
  String get _id => widget.academiaId;

  String get _moneda {
    final ac = appState.miAcademia;
    return (ac != null && ac.id == _id) ? ac.monedaSimbolo : 'S/';
  }

  String _mon(double v) => '$_moneda ${v.toStringAsFixed(0)}';

  String _saludo(Alumno a) => a.esMenor ? a.apoderadoNombre : a.nombre;

  /// Mensaje para WhatsApp (padres SIN la app).
  String _mensaje(Alumno a, double deuda) {
    final deQuien = a.esMenor ? ' de ${a.nombre}' : '';
    return 'Hola ${_saludo(a)}, te recuerdo el pago pendiente$deQuien por '
        '$_moneda ${deuda.toStringAsFixed(2)}. ¡Gracias! 🙌';
  }

  /// Mensaje IN-APP (padres CON la app): lo invita a pagar dentro de Pichangol.
  String _mensajeApp(Alumno a, double deuda) {
    final deQuien = a.esMenor ? ' de ${a.nombre}' : '';
    return 'Hola ${_saludo(a)}, tienes una cuota pendiente$deQuien por '
        '$_moneda ${deuda.toStringAsFixed(2)}. Puedes pagarla ahora mismo desde '
        'la app en “Mis clases y pagos”. ¡Gracias! 🙌';
  }

  /// Envía el recordatorio por el chat de la academia (in-app + push) al alumno
  /// con cuenta. Devuelve true si se envió. Marca recordado.
  Future<bool> _enviarChatCobro(Alumno a, double deuda) async {
    final u = appState.usuario;
    if (u == null) return false;
    final msg = Mensaje(
      id: 'msg_${DateTime.now().microsecondsSinceEpoch}_${a.id}',
      hilo: Mensaje.hiloDe(_id, a.email),
      tipo: 'academia',
      refId: _id,
      academiaId: _id,
      cuentaEmail: a.email,
      autorEmail: u.email,
      autorNombre: u.nombre,
      esProfe: true,
      texto: _mensajeApp(a, deuda),
      creado: DateTime.now(),
    );
    final ok = await MensajesRepo.enviar(msg);
    if (ok) appState.marcarRecordado(a.id);
    return ok;
  }

  /// Recuerda el pago: por la APP (chat + push) si el padre la tiene, o por
  /// WhatsApp si no. Así se empuja el pago dentro de Pichangol.
  Future<void> _recordar(Alumno a) async {
    final deuda = appState.deudaDeAlumno(a.id).deuda;
    if (a.esApp) {
      final ok = await _enviarChatCobro(a, deuda);
      if (mounted) {
        _msg(ok
            ? 'Le recordé a ${a.nombre} por la app 📲'
            : 'No se pudo enviar por la app.');
      }
      return;
    }
    final tel = a.whatsappContacto;
    if (tel.isEmpty) {
      _msg('${a.nombre} no tiene WhatsApp ni cuenta en la app.');
      return;
    }
    final ok = await WhatsAppLink.abrir(tel, _mensaje(a, deuda));
    appState.marcarRecordado(a.id);
    if (!ok && mounted) _msg('No pude abrir WhatsApp.');
  }

  void _msg(String t) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(t)));
  }

  /// Recuerda a TODOS los morosos: automático por la APP a los que la tienen
  /// (chat + push, sin taps), y luego WhatsApp para los que no.
  Future<void> _recordarATodos() async {
    final morosos = appState.morososDe(_id);
    final conApp = morosos.where((a) => a.esApp).toList();
    final sinApp = morosos.where((a) => !a.esApp).toList();
    var enviados = 0;
    for (final a in conApp) {
      final ok = await _enviarChatCobro(a, appState.deudaDeAlumno(a.id).deuda);
      if (ok) enviados++;
    }
    if (mounted && enviados > 0) {
      _msg('Recordé a $enviados padre(s) por la app 📲');
    }
    if (sinApp.isNotEmpty) {
      if (mounted) await _whatsappSheet(sinApp);
    } else if (enviados == 0 && mounted) {
      _msg('¡Nadie debe! 🎉');
    }
    if (mounted) setState(() {});
  }

  /// Hoja para recordar por WhatsApp a los morosos SIN app, uno por uno.
  Future<void> _whatsappSheet(List<Alumno> morosos) async {
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Theme.of(context).colorScheme.surface,
      shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(24))),
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setSt) {
          return DraggableScrollableSheet(
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
                        color: trazo,
                        borderRadius: BorderRadius.circular(999))),
                const Padding(
                  padding: EdgeInsets.fromLTRB(20, 14, 20, 4),
                  child: Align(
                    alignment: Alignment.centerLeft,
                    child: Text('Avisar por WhatsApp',
                        style: TextStyle(
                            fontWeight: FontWeight.w800, fontSize: 18)),
                  ),
                ),
                const Padding(
                  padding: EdgeInsets.fromLTRB(20, 0, 20, 8),
                  child: Align(
                    alignment: Alignment.centerLeft,
                    child: Text(
                        'Estos padres aún no tienen la app. WhatsApp abre un chat '
                        'a la vez; toca “Enviar” en cada uno.',
                        style: TextStyle(color: textoTenue, fontSize: 12.5)),
                  ),
                ),
                Expanded(
                  child: morosos.isEmpty
                      ? const Center(
                          child: Text('¡Nadie debe! 🎉',
                              style: TextStyle(color: textoTenue)))
                      : ListView.separated(
                          controller: scroll,
                          itemCount: morosos.length,
                          separatorBuilder: (_, __) =>
                              Divider(height: 1, color: trazo.withOpacity(0.6)),
                          itemBuilder: (_, i) {
                            final a = morosos[i];
                            final deuda = appState.deudaDeAlumno(a.id).deuda;
                            final dias = appState.diasDesdeRecordatorio(a.id);
                            final recienRecordado = dias != null && dias == 0;
                            return ListTile(
                              leading: _Avatar(alumno: a),
                              title: Text(a.nombre,
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
                                  style: const TextStyle(
                                      fontWeight: FontWeight.w700)),
                              subtitle: Text('Debe ${_mon(deuda)}',
                                  style: const TextStyle(
                                      color: textoTenue, fontSize: 12.5)),
                              trailing: recienRecordado
                                  ? const Icon(Icons.check_circle,
                                      color: lima)
                                  : FilledButton(
                                      style: FilledButton.styleFrom(
                                          backgroundColor: lima,
                                          foregroundColor: Colors.white,
                                          padding: const EdgeInsets.symmetric(
                                              horizontal: 14, vertical: 8),
                                          textStyle: const TextStyle(
                                              fontWeight: FontWeight.w700)),
                                      onPressed: () async {
                                        await _recordar(a);
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
          );
        },
      ),
    );
    if (mounted) setState(() {});
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Cobros'),
        actions: [
          ListenableBuilder(
            listenable: appState,
            builder: (context, _) => IconButton(
              tooltip: appState.recordatoriosAutoActivos
                  ? 'Avisos de cobranza: activados'
                  : 'Avisos de cobranza: desactivados',
              icon: Icon(appState.recordatoriosAutoActivos
                  ? Icons.notifications_active
                  : Icons.notifications_off_outlined),
              onPressed: () => appState
                  .setRecordatoriosAuto(!appState.recordatoriosAutoActivos),
            ),
          ),
        ],
      ),
      body: ListenableBuilder(
        listenable: appState,
        builder: (context, _) {
          final porCobrar = appState.porCobrarDe(_id);
          final vencido = appState.vencidoDe(_id);
          final cobradoMes = appState.cobradoMesDe(_id);
          final morosos = appState.morososDe(_id);
          final porRecordar = appState.porRecordarDe(_id);
          return ListView(
            padding: const EdgeInsets.fromLTRB(16, 14, 16, 28),
            children: [
              // KPIs
              Row(
                children: [
                  Expanded(
                    child: _Kpi(
                        titulo: 'Por cobrar',
                        valor: _mon(porCobrar),
                        color: bosque),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: _Kpi(
                        titulo: 'Vencido',
                        valor: _mon(vencido),
                        color: vencido > 0 ? clayOscuro : textoTenue),
                  ),
                ],
              ),
              const SizedBox(height: 10),
              _Kpi(
                  titulo: 'Cobrado este mes',
                  valor: _mon(cobradoMes),
                  color: lima,
                  ancho: true),
              const SizedBox(height: 14),
              // Recordatorios (automático): el app te dice a quién recordar.
              if (appState.recordatoriosAutoActivos && porRecordar.isNotEmpty)
                _CardRecordatorios(
                    cantidad: porRecordar.length, onTodos: _recordarATodos),
              const SizedBox(height: 6),
              Row(
                children: [
                  const Text('Quién debe',
                      style: TextStyle(
                          fontWeight: FontWeight.w800, fontSize: 16)),
                  const Spacer(),
                  if (morosos.isNotEmpty)
                    TextButton.icon(
                      onPressed: _recordarATodos,
                      icon: const Icon(Icons.campaign_outlined, size: 18),
                      label: const Text('Recordar a todos'),
                      style: TextButton.styleFrom(foregroundColor: lima),
                    ),
                ],
              ),
              const SizedBox(height: 4),
              if (morosos.isEmpty)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 30),
                  child: Column(
                    children: [
                      const Icon(Icons.check_circle_outline,
                          size: 52, color: lima),
                      const SizedBox(height: 10),
                      Text('Todos al día 🎉',
                          style: TextStyle(
                              color: textoTenueDe(context),
                              fontWeight: FontWeight.w700)),
                    ],
                  ),
                )
              else
                for (final a in morosos) _FilaMoroso(alumno: a, cobros: this),
            ],
          );
        },
      ),
    );
  }
}

/// Tarjeta KPI (por cobrar / vencido / cobrado).
class _Kpi extends StatelessWidget {
  const _Kpi(
      {required this.titulo,
      required this.valor,
      required this.color,
      this.ancho = false});
  final String titulo;
  final String valor;
  final Color color;
  final bool ancho;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: ancho ? double.infinity : null,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: trazo),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(titulo,
              style: const TextStyle(color: textoTenue, fontSize: 13)),
          const SizedBox(height: 4),
          Text(valor,
              style: TextStyle(
                  fontWeight: FontWeight.w900, fontSize: 22, color: color)),
        ],
      ),
    );
  }
}

/// Aviso proactivo: el app detectó a quién recordar.
class _CardRecordatorios extends StatelessWidget {
  const _CardRecordatorios({required this.cantidad, required this.onTodos});
  final int cantidad;
  final VoidCallback onTodos;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: limaSuave,
        borderRadius: BorderRadius.circular(16),
      ),
      child: Row(
        children: [
          const Icon(Icons.notifications_active, color: bosque),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
                'Tienes $cantidad ${cantidad == 1 ? 'alumno' : 'alumnos'} por '
                'recordar hoy.',
                style: const TextStyle(
                    color: bosque, fontWeight: FontWeight.w700, fontSize: 13.5)),
          ),
          const SizedBox(width: 8),
          FilledButton(
            style: FilledButton.styleFrom(
                backgroundColor: bosque, foregroundColor: Colors.white),
            onPressed: onTodos,
            child: const Text('Recordar'),
          ),
        ],
      ),
    );
  }
}

/// Fila de un alumno deudor: deuda, estado, recordatorio y acceso a su detalle
/// (donde se marca cobrado por cuota).
class _FilaMoroso extends StatelessWidget {
  const _FilaMoroso({required this.alumno, required this.cobros});
  final Alumno alumno;
  final _CobrosScreenState cobros;

  @override
  Widget build(BuildContext context) {
    final d = appState.deudaDeAlumno(alumno.id);
    final dias = appState.diasDesdeRecordatorio(alumno.id);
    final sub = dias == null
        ? 'Sin recordar aún'
        : (dias == 0 ? 'Recordado hoy' : 'Recordado hace $dias d');
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: trazo),
      ),
      child: ListTile(
        contentPadding: const EdgeInsets.fromLTRB(12, 6, 8, 6),
        onTap: () => Navigator.of(context).push(MaterialPageRoute(
            builder: (_) => AlumnoDetalleScreen(alumnoId: alumno.id))),
        leading: _Avatar(alumno: alumno),
        title: Row(
          children: [
            Expanded(
              child: Text(alumno.nombre,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(fontWeight: FontWeight.w700)),
            ),
            if (d.vencido)
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                decoration: BoxDecoration(
                    color: const Color(0xFFFBEAD2),
                    borderRadius: BorderRadius.circular(999)),
                child: const Text('Vencido',
                    style: TextStyle(
                        color: clayOscuro,
                        fontSize: 11,
                        fontWeight: FontWeight.w800)),
              ),
          ],
        ),
        subtitle: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Debe ${cobros._mon(d.deuda)}',
                style: TextStyle(
                    color: d.vencido ? clayOscuro : textoTenueDe(context),
                    fontWeight: FontWeight.w700,
                    fontSize: 13)),
            Text(sub,
                style: const TextStyle(color: textoTenue, fontSize: 11.5)),
          ],
        ),
        trailing: OutlinedButton.icon(
          style: OutlinedButton.styleFrom(
              foregroundColor: lima,
              side: const BorderSide(color: lima),
              padding: const EdgeInsets.symmetric(horizontal: 10)),
          icon: const Icon(Icons.chat_outlined, size: 16),
          label: const Text('Recordar'),
          onPressed: () => cobros._recordar(alumno),
        ),
      ),
    );
  }
}

/// Avatar del alumno (foto de perfil si tiene; si no, inicial).
class _Avatar extends StatelessWidget {
  const _Avatar({required this.alumno});
  final Alumno alumno;

  @override
  Widget build(BuildContext context) {
    final foto = alumno.fotoUrl ??
        (alumno.email.isNotEmpty ? appState.fotoDe(alumno.email) : null);
    final ini = alumno.nombre.trim().isNotEmpty
        ? alumno.nombre.trim().characters.first.toUpperCase()
        : '?';
    return CircleAvatar(
      radius: 20,
      backgroundColor: teal,
      backgroundImage:
          (foto != null && foto.isNotEmpty) ? NetworkImage(foto) : null,
      child: (foto == null || foto.isEmpty)
          ? Text(ini,
              style: const TextStyle(
                  color: Colors.white, fontWeight: FontWeight.w800))
          : null,
    );
  }
}
