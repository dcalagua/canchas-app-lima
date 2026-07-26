import 'package:flutter/material.dart';

import '../data/mensajes_repo.dart';
import '../models/academia.dart';
import '../models/mensaje.dart';
import '../services/whatsapp_link.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/cargando_pichangol.dart';
import '../widgets/responsive.dart';

/// Toma de ASISTENCIA por día: el profe marca quién vino (upsert por alumno+día)
/// y con un tap AVISA a los padres — por la app (chat + push) a quienes tienen
/// cuenta, y por WhatsApp a quienes no.
class AsistenciaScreen extends StatefulWidget {
  const AsistenciaScreen({super.key, required this.academiaId});
  final String academiaId;

  @override
  State<AsistenciaScreen> createState() => _AsistenciaScreenState();
}

class _AsistenciaScreenState extends State<AsistenciaScreen> {
  DateTime _fecha = DateTime.now();
  bool _avisando = false;

  static const _dias = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom'];
  static const _meses = [
    'Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Set', 'Oct',
    'Nov', 'Dic'
  ];

  String get _dia => Asistencia.claveDia(_fecha);

  String get _nombreAcademia => appState.miAcademia?.nombre ?? 'la academia';

  void _cambiarDia(int delta) =>
      setState(() => _fecha = _fecha.add(Duration(days: delta)));

  Future<void> _elegirFecha() async {
    final f = await showDatePicker(
      context: context,
      initialDate: _fecha,
      firstDate: DateTime(2024),
      lastDate: DateTime(2100),
    );
    if (f != null) setState(() => _fecha = f);
  }

  void _msg(String t) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(t)));
  }

  /// Texto del aviso según asistió o faltó.
  String _texto(Alumno a, bool presente) => presente
      ? '✅ ${a.nombre} asistió hoy a $_nombreAcademia.'
      : '⚠️ ${a.nombre} faltó hoy a $_nombreAcademia.';

  /// Marca a toda la clase como presente.
  void _todosPresentes() {
    final ids = appState.alumnosDe(widget.academiaId).map((a) => a.id).toList();
    appState.marcarAsistenciaTodos(widget.academiaId, ids, _dia, true);
  }

  /// AVISA a los padres: chat (app) automático + WhatsApp para los que no tienen
  /// cuenta. Se salta a quien ya se le avisó hoy (no reenvía).
  Future<void> _avisar() async {
    final u = appState.usuario;
    if (u == null) {
      _msg('Inicia sesión para avisar.');
      return;
    }
    final alumnos = appState.alumnosDe(widget.academiaId);
    final pendientes =
        alumnos.where((a) => !appState.asistenciaAvisada(a.id, _dia)).toList();
    if (pendientes.isEmpty) {
      _msg('Ya avisaste a todos hoy. 🎉');
      return;
    }
    final presentes = pendientes.where((a) => appState.asistio(a.id, _dia)).length;
    final ausentes = pendientes.length - presentes;
    final go = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Avisar a los padres'),
        content: Text(
            'Se enviará: ✅ asistió a $presentes y ⚠️ faltó a $ausentes.\n\n'
            'A los que tienen la app les llega al instante; a los demás se abre '
            'WhatsApp para enviarlo.'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('Cancelar')),
          FilledButton(
              style: FilledButton.styleFrom(backgroundColor: lima),
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('Avisar')),
        ],
      ),
    );
    if (go != true) return;

    if (_avisando) return;
    setState(() => _avisando = true);
    final sinApp = <Alumno>[];
    int enviadosApp;
    try {
      // Regla: avisar (envía por la app a cada padre) demora → preload de marca.
      enviadosApp = await conPreload(context, () async {
        var n = 0;
        for (final a in pendientes) {
          final presente = appState.asistio(a.id, _dia);
          if (a.esApp) {
            final msg = Mensaje(
              id: 'msg_${DateTime.now().microsecondsSinceEpoch}_${a.id}',
              hilo: Mensaje.hiloDe(widget.academiaId, a.email),
              tipo: 'academia',
              refId: widget.academiaId,
              academiaId: widget.academiaId,
              cuentaEmail: a.email,
              autorEmail: u.email,
              autorNombre: u.nombre,
              esProfe: true,
              texto: _texto(a, presente),
              creado: DateTime.now(),
            );
            final ok = await MensajesRepo.enviar(msg);
            if (ok) {
              n++;
              appState.marcarAsistenciaAvisada(a.id, _dia);
            }
          } else {
            sinApp.add(a);
          }
        }
        return n;
      }, texto: 'Avisando a los padres…');
    } finally {
      if (mounted) setState(() => _avisando = false);
    }
    if (!mounted) return;
    _msg(enviadosApp > 0
        ? '✅ Avisé a $enviadosApp padre(s) por la app.'
        : (sinApp.isEmpty ? 'Listo.' : 'Ningún padre tiene la app aún.'));
    if (sinApp.isNotEmpty) await _whatsappSheet(sinApp);
  }

  /// Hoja para avisar por WhatsApp a los alumnos SIN app (uno por uno).
  Future<void> _whatsappSheet(List<Alumno> alumnos) async {
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
                  child: Text('Avisar por WhatsApp',
                      style:
                          TextStyle(fontWeight: FontWeight.w800, fontSize: 18)),
                ),
              ),
              const Padding(
                padding: EdgeInsets.fromLTRB(20, 0, 20, 8),
                child: Align(
                  alignment: Alignment.centerLeft,
                  child: Text('Estos padres aún no tienen la app. Toca “Enviar”.',
                      style: TextStyle(color: textoTenue, fontSize: 12.5)),
                ),
              ),
              Expanded(
                child: ListView.separated(
                  controller: scroll,
                  itemCount: alumnos.length,
                  separatorBuilder: (_, __) =>
                      Divider(height: 1, color: trazo.withOpacity(0.6)),
                  itemBuilder: (_, i) {
                    final a = alumnos[i];
                    final presente = appState.asistio(a.id, _dia);
                    final avisado = appState.asistenciaAvisada(a.id, _dia);
                    final tel = a.whatsappContacto;
                    return ListTile(
                      leading: CircleAvatar(
                        backgroundColor: presente ? verde : verdeClaro,
                        child: Icon(presente ? Icons.check : Icons.close,
                            color: Colors.white, size: 20),
                      ),
                      title: Text(a.nombre,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(fontWeight: FontWeight.w700)),
                      subtitle: Text(presente ? 'Asistió' : 'Faltó',
                          style: const TextStyle(
                              color: textoTenue, fontSize: 12.5)),
                      trailing: avisado
                          ? const Icon(Icons.check_circle, color: lima)
                          : tel.isEmpty
                              ? const Text('Sin WhatsApp',
                                  style: TextStyle(
                                      color: textoTenue, fontSize: 12))
                              : FilledButton(
                                  style: FilledButton.styleFrom(
                                      backgroundColor: verde,
                                      foregroundColor: Colors.white,
                                      textStyle: const TextStyle(
                                          fontWeight: FontWeight.w700)),
                                  onPressed: () async {
                                    await WhatsAppLink.abrir(
                                        tel, _texto(a, presente));
                                    appState.marcarAsistenciaAvisada(a.id, _dia);
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
      body: ListenableBuilder(
        listenable: appState,
        builder: (context, _) {
          final alumnos = appState.alumnosDe(widget.academiaId);
          final presentes =
              alumnos.where((a) => appState.asistio(a.id, _dia)).length;
          final porAvisar = alumnos
              .where((a) => !appState.asistenciaAvisada(a.id, _dia))
              .length;
          return Column(
            children: [
              _Cabecera(
                fecha: _fecha,
                dias: _dias,
                meses: _meses,
                presentes: presentes,
                total: alumnos.length,
                onPrev: () => _cambiarDia(-1),
                onNext: () => _cambiarDia(1),
                onFecha: _elegirFecha,
              ),
              if (alumnos.isEmpty)
                const Expanded(
                  child: Center(
                    child: Padding(
                      padding: EdgeInsets.all(28),
                      child: Text(
                          'No tienes alumnos aún. Agrégalos en tu academia.',
                          textAlign: TextAlign.center,
                          style: TextStyle(color: textoTenue)),
                    ),
                  ),
                )
              else ...[
                // Acción rápida: marcar toda la clase presente.
                Padding(
                  padding: const EdgeInsets.fromLTRB(16, 10, 16, 0),
                  child: Row(
                    children: [
                      Expanded(
                        child: OutlinedButton.icon(
                          style: OutlinedButton.styleFrom(
                              foregroundColor: verde,
                              side: const BorderSide(color: verde)),
                          icon: const Icon(Icons.done_all, size: 18),
                          label: const Text('Todos presentes'),
                          onPressed: _todosPresentes,
                        ),
                      ),
                    ],
                  ),
                ),
                Expanded(
                  child: ListView(
                    // Regla app: contenido centrado en pantallas anchas.
                    padding: EdgeInsets.fromLTRB(
                        ladoTablet(context, 16, 760), 10,
                        ladoTablet(context, 16, 760), 24),
                    children: [
                      for (final al in alumnos)
                        _FilaAsistencia(
                          alumno: al,
                          presente: appState.asistio(al.id, _dia),
                          avisado: appState.asistenciaAvisada(al.id, _dia),
                          totalClases: appState.clasesAsistidas(al.id),
                          onToggle: (v) => appState.marcarAsistencia(
                              widget.academiaId, al.id, _dia, v),
                        ),
                    ],
                  ),
                ),
                // Barra inferior: avisar a los padres.
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
                        onPressed:
                            (_avisando || porAvisar == 0) ? null : _avisar,
                        icon: const Icon(Icons.campaign),
                        label: Text(
                            porAvisar == 0
                                ? 'Padres avisados ✓'
                                : 'Avisar a los padres ($porAvisar)',
                            style: const TextStyle(
                                fontWeight: FontWeight.w800, fontSize: 15)),
                      ),
                    ),
                  ),
                ),
              ],
            ],
          );
        },
      ),
    );
  }
}

class _Cabecera extends StatelessWidget {
  const _Cabecera({
    required this.fecha,
    required this.dias,
    required this.meses,
    required this.presentes,
    required this.total,
    required this.onPrev,
    required this.onNext,
    required this.onFecha,
  });
  final DateTime fecha;
  final List<String> dias;
  final List<String> meses;
  final int presentes;
  final int total;
  final VoidCallback onPrev;
  final VoidCallback onNext;
  final VoidCallback onFecha;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final etiqueta =
        '${dias[(fecha.weekday - 1) % 7]} ${fecha.day} ${meses[fecha.month - 1]}';
    return Container(
      width: double.infinity,
      padding: EdgeInsets.fromLTRB(
          10, 12 + MediaQuery.of(context).padding.top, 10, 18),
      decoration: const BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [lima, teal], // verde WhatsApp
        ),
        borderRadius: BorderRadius.vertical(bottom: Radius.circular(24)),
      ),
      child: Column(
        children: [
          Row(
            children: [
              IconButton(
                icon: const Icon(Icons.arrow_back, color: Colors.white),
                onPressed: () => Navigator.of(context).maybePop(),
              ),
              Expanded(
                child: Text('Asistencia',
                    style: t.titleLarge?.copyWith(
                        color: Colors.white, fontWeight: FontWeight.w800)),
              ),
            ],
          ),
          const SizedBox(height: 6),
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              IconButton(
                icon: const Icon(Icons.chevron_left, color: Colors.white),
                onPressed: onPrev,
              ),
              GestureDetector(
                onTap: onFecha,
                child: Row(
                  children: [
                    const Icon(Icons.event, color: Colors.white70, size: 18),
                    const SizedBox(width: 6),
                    Text(etiqueta,
                        style: t.titleMedium?.copyWith(
                            color: Colors.white, fontWeight: FontWeight.w700)),
                  ],
                ),
              ),
              IconButton(
                icon: const Icon(Icons.chevron_right, color: Colors.white),
                onPressed: onNext,
              ),
            ],
          ),
          Text('$presentes de $total presentes',
              style: t.bodyMedium?.copyWith(color: Colors.white70)),
        ],
      ),
    );
  }
}

class _FilaAsistencia extends StatelessWidget {
  const _FilaAsistencia({
    required this.alumno,
    required this.presente,
    required this.avisado,
    required this.totalClases,
    required this.onToggle,
  });
  final Alumno alumno;
  final bool presente;
  final bool avisado;
  final int totalClases;
  final ValueChanged<bool> onToggle;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: presente ? verde : trazo),
      ),
      child: ListTile(
        leading: CircleAvatar(
          backgroundColor: presente ? verde : verdeClaro,
          child: Icon(presente ? Icons.check : Icons.person,
              color: Colors.white),
        ),
        title: Text(alumno.nombre,
            style: const TextStyle(fontWeight: FontWeight.w700)),
        subtitle: Row(
          children: [
            Text('$totalClases clases',
                style: const TextStyle(color: textoTenue, fontSize: 12.5)),
            if (avisado) ...[
              const SizedBox(width: 8),
              const Icon(Icons.notifications_active, size: 13, color: lima),
              const SizedBox(width: 2),
              const Text('avisado',
                  style: TextStyle(
                      color: lima, fontSize: 11.5, fontWeight: FontWeight.w700)),
            ],
          ],
        ),
        trailing: Switch(
          value: presente,
          activeColor: verde,
          onChanged: onToggle,
        ),
        onTap: () => onToggle(!presente),
      ),
    );
  }
}
