import 'package:flutter/material.dart';

import '../models/academia.dart';
import '../state/app_state.dart';
import '../theme.dart';

/// Toma de ASISTENCIA por día: el profe marca quién vino. Upsert por alumno+día.
class AsistenciaScreen extends StatefulWidget {
  const AsistenciaScreen({super.key, required this.academiaId});
  final String academiaId;

  @override
  State<AsistenciaScreen> createState() => _AsistenciaScreenState();
}

class _AsistenciaScreenState extends State<AsistenciaScreen> {
  DateTime _fecha = DateTime.now();

  static const _dias = [
    'Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom'
  ];
  static const _meses = [
    'Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Set', 'Oct',
    'Nov', 'Dic'
  ];

  String get _dia => Asistencia.claveDia(_fecha);

  void _cambiarDia(int delta) {
    setState(() => _fecha = _fecha.add(Duration(days: delta)));
  }

  Future<void> _elegirFecha() async {
    final f = await showDatePicker(
      context: context,
      initialDate: _fecha,
      firstDate: DateTime(2024),
      lastDate: DateTime(2100),
    );
    if (f != null) setState(() => _fecha = f);
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
              else
                Expanded(
                  child: ListView(
                    padding: const EdgeInsets.fromLTRB(16, 12, 16, 24),
                    children: [
                      for (final al in alumnos)
                        _FilaAsistencia(
                          alumno: al,
                          presente: appState.asistio(al.id, _dia),
                          totalClases: appState.clasesAsistidas(al.id),
                          onToggle: (v) => appState.marcarAsistencia(
                              widget.academiaId, al.id, _dia, v),
                        ),
                    ],
                  ),
                ),
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
    required this.totalClases,
    required this.onToggle,
  });
  final Alumno alumno;
  final bool presente;
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
        subtitle: Text('$totalClases clases asistidas'),
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
