import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../models/academia.dart';
import '../services/whatsapp_link.dart';
import '../state/app_state.dart';
import '../theme.dart';
import 'asistencia_screen.dart';
import 'campeonatos_screen.dart';
import 'crear_academia_screen.dart';

/// Panel del PROFE: su academia, alumnos y cobros (Fase 1). Sin pasarela: marca
/// pagos en efectivo y manda recordatorios por WhatsApp.
class MiAcademiaScreen extends StatelessWidget {
  const MiAcademiaScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: ListenableBuilder(
        listenable: appState,
        builder: (context, _) {
          final ac = appState.miAcademia;
          if (ac == null) {
            return const _SinAcademia();
          }
          final alumnos = appState.alumnosDe(ac.id);
          final hoy = DateTime.now();
          double porCobrar = 0, vencido = 0;
          for (final c in appState.cuotasDe(ac.id)) {
            if (!c.pagada) {
              porCobrar += c.monto;
              if (c.vencidaAl(hoy)) vencido += c.monto;
            }
          }
          return ListView(
            padding: EdgeInsets.zero,
            children: [
              _Header(academia: ac),
              _CodigoCard(academia: ac),
              Padding(
                padding: const EdgeInsets.fromLTRB(18, 16, 18, 8),
                child: Row(
                  children: [
                    Expanded(
                        child: _Metrica(
                            'Por cobrar',
                            'S/ ${porCobrar.toStringAsFixed(2)}',
                            Theme.of(context).colorScheme.primary)),
                    const SizedBox(width: 10),
                    Expanded(
                        child: _Metrica('Vencido',
                            'S/ ${vencido.toStringAsFixed(2)}', clayOscuro)),
                    const SizedBox(width: 10),
                    Expanded(
                        child: _Metrica('Alumnos', '${alumnos.length}',
                            Theme.of(context).colorScheme.primary)),
                  ],
                ),
              ),
              Padding(
                padding: const EdgeInsets.fromLTRB(18, 8, 18, 4),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    const Text('Alumnos',
                        style:
                            TextStyle(fontWeight: FontWeight.w800, fontSize: 17)),
                    TextButton.icon(
                      onPressed: () => _agregarAlumno(context, ac),
                      icon: const Icon(Icons.person_add_alt_1),
                      label: const Text('Agregar'),
                    ),
                  ],
                ),
              ),
              if (alumnos.isEmpty)
                const Padding(
                  padding: EdgeInsets.all(24),
                  child: Text(
                      'Aún no tienes alumnos. Agrégalos y ellos verán sus cuotas.',
                      style: TextStyle(color: textoTenue)),
                ),
              for (final al in alumnos)
                _TarjetaAlumno(alumno: al),
              const SizedBox(height: 30),
            ],
          );
        },
      ),
    );
  }

  static Future<void> _agregarAlumno(
      BuildContext context, Academia ac) async {
    final nombre = TextEditingController();
    final whats = TextEditingController();
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Nuevo alumno'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
                controller: nombre,
                decoration: const InputDecoration(labelText: 'Nombre')),
            TextField(
                controller: whats,
                keyboardType: TextInputType.phone,
                decoration: const InputDecoration(
                    labelText: 'WhatsApp', prefixText: '+51 ')),
          ],
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('Cancelar')),
          FilledButton(
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('Agregar')),
        ],
      ),
    );
    if (ok == true && nombre.text.trim().isNotEmpty) {
      appState.agregarAlumno(Alumno(
        id: 'al_${DateTime.now().microsecondsSinceEpoch}',
        academiaId: ac.id,
        nombre: nombre.text.trim(),
        whatsapp: whats.text.trim(),
      ));
    }
  }
}

class _SinAcademia extends StatelessWidget {
  const _SinAcademia();
  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(28),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.school_outlined,
                size: 64, color: Theme.of(context).colorScheme.primary),
            const SizedBox(height: 14),
            const Text('Aún no tienes una academia',
                style: TextStyle(fontWeight: FontWeight.w800, fontSize: 18)),
            const SizedBox(height: 6),
            const Text(
                'Créala y empieza a gestionar tus alumnos y cobros sin perseguir a nadie.',
                textAlign: TextAlign.center,
                style: TextStyle(color: textoTenue)),
            const SizedBox(height: 18),
            FilledButton.icon(
              style: FilledButton.styleFrom(backgroundColor: pino, foregroundColor: lima),
              onPressed: () => Navigator.of(context).push(MaterialPageRoute(
                  builder: (_) => const CrearAcademiaScreen())),
              icon: const Icon(Icons.add),
              label: const Text('Crear mi academia'),
            ),
          ],
        ),
      ),
    );
  }
}

/// Tarjeta con el CÓDIGO de la academia: el profe lo comparte por WhatsApp para
/// que sus alumnos se unan desde la app y queden vinculados (alumno-app).
class _CodigoCard extends StatelessWidget {
  const _CodigoCard({required this.academia});
  final Academia academia;

  static const _releaseUrl =
      'https://github.com/dcalagua/canchas-app-lima/releases/tag/v0.1.0';

  Future<void> _compartir(BuildContext context) async {
    final msg = '¡Hola! Te invito a mi academia "${academia.nombre}" en '
        'Pichangol 🎾\n\n'
        '1) Descarga la app: $_releaseUrl\n'
        '2) Entra a Academias → "Unirme con código"\n'
        '3) Ingresa el código: ${academia.codigo}\n\n'
        'Ahí verás tus clases y pagos. ¡Nos vemos en la cancha!';
    final ok = await WhatsAppLink.compartir(msg);
    if (!ok && context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('No pude abrir WhatsApp.')));
    }
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final t = Theme.of(context).textTheme;
    return Container(
      margin: const EdgeInsets.fromLTRB(18, 16, 18, 0),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: cs.surface,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: lima.withOpacity(0.7)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            Icon(Icons.qr_code_2, color: cs.primary, size: 20),
            const SizedBox(width: 8),
            Text('Código de tu academia',
                style: t.titleSmall?.copyWith(fontWeight: FontWeight.w800)),
          ]),
          const SizedBox(height: 4),
          Text('Compártelo para que tus alumnos se unan desde la app.',
              style: t.bodySmall?.copyWith(color: textoTenue)),
          const SizedBox(height: 12),
          Row(
            children: [
              Expanded(
                child: Container(
                  padding: const EdgeInsets.symmetric(vertical: 12),
                  alignment: Alignment.center,
                  decoration: BoxDecoration(
                    color: limaSuave,
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Text(academia.codigo,
                      style: const TextStyle(
                          fontSize: 26,
                          fontWeight: FontWeight.w900,
                          letterSpacing: 6,
                          color: bosque)),
                ),
              ),
              const SizedBox(width: 8),
              IconButton(
                tooltip: 'Copiar código',
                icon: Icon(Icons.copy, color: cs.primary),
                onPressed: () {
                  Clipboard.setData(ClipboardData(text: academia.codigo));
                  ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
                      content: Text('Código copiado')));
                },
              ),
            ],
          ),
          const SizedBox(height: 10),
          SizedBox(
            width: double.infinity,
            child: FilledButton.icon(
              style: FilledButton.styleFrom(
                  backgroundColor: const Color(0xFF25D366),
                  foregroundColor: Colors.white),
              onPressed: () => _compartir(context),
              icon: const Icon(Icons.share),
              label: const Text('Compartir por WhatsApp'),
            ),
          ),
        ],
      ),
    );
  }
}

class _Header extends StatelessWidget {
  const _Header({required this.academia});
  final Academia academia;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return Container(
      width: double.infinity,
      padding: EdgeInsets.fromLTRB(
          22, 20 + MediaQuery.of(context).padding.top, 22, 22),
      decoration: const BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [sage, verde, bosque],
        ),
        borderRadius: BorderRadius.vertical(bottom: Radius.circular(24)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(academia.nombre,
                    style: t.headlineSmall?.copyWith(
                        color: Colors.white, fontWeight: FontWeight.w800)),
              ),
              IconButton(
                tooltip: 'Campeonatos',
                icon: const Icon(Icons.emoji_events_outlined,
                    color: Colors.white),
                onPressed: () => Navigator.of(context).push(MaterialPageRoute(
                    builder: (_) =>
                        CampeonatosScreen(academiaId: academia.id))),
              ),
              IconButton(
                tooltip: 'Asistencia',
                icon: const Icon(Icons.fact_check_outlined,
                    color: Colors.white),
                onPressed: () => Navigator.of(context).push(MaterialPageRoute(
                    builder: (_) =>
                        AsistenciaScreen(academiaId: academia.id))),
              ),
              IconButton(
                tooltip: 'Editar',
                icon: const Icon(Icons.edit, color: Colors.white),
                onPressed: () => Navigator.of(context).push(MaterialPageRoute(
                    builder: (_) => CrearAcademiaScreen(academia: academia))),
              ),
            ],
          ),
          const SizedBox(height: 2),
          Row(
            children: [
              const Icon(Icons.place, size: 16, color: Colors.white70),
              const SizedBox(width: 4),
              Text(
                  academia.sedeClub.isEmpty
                      ? 'Sin sede definida'
                      : academia.sedeClub,
                  style: t.bodyMedium?.copyWith(color: Colors.white70)),
            ],
          ),
        ],
      ),
    );
  }
}

class _Metrica extends StatelessWidget {
  const _Metrica(this.titulo, this.valor, this.color);
  final String titulo;
  final String valor;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 10),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: trazo),
      ),
      child: Column(
        children: [
          Text(valor,
              style: TextStyle(
                  fontWeight: FontWeight.w800, fontSize: 16, color: color)),
          const SizedBox(height: 2),
          Text(titulo,
              style: const TextStyle(color: textoTenue, fontSize: 12)),
        ],
      ),
    );
  }
}

/// Pastilla que marca el tipo de alumno en el roster ("app" / "menor").
class _EtiquetaAlumno extends StatelessWidget {
  const _EtiquetaAlumno(this.texto);
  final String texto;
  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(left: 6),
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
      decoration:
          BoxDecoration(color: limaSuave, borderRadius: BorderRadius.circular(999)),
      child: Text(texto,
          style: const TextStyle(
              color: bosque, fontSize: 10, fontWeight: FontWeight.w800)),
    );
  }
}

class _TarjetaAlumno extends StatelessWidget {
  const _TarjetaAlumno({required this.alumno});
  final Alumno alumno;

  @override
  Widget build(BuildContext context) {
    final cuotas = appState.cuotasDeAlumno(alumno.id);
    final pend =
        cuotas.where((c) => !c.pagada).fold<double>(0, (s, c) => s + c.monto);
    final tieneFoto = alumno.fotoUrl != null && alumno.fotoUrl!.isNotEmpty;
    return Card(
      margin: const EdgeInsets.symmetric(horizontal: 18, vertical: 5),
      child: ListTile(
        leading: CircleAvatar(
          backgroundColor: verdeClaro,
          backgroundImage: tieneFoto ? NetworkImage(alumno.fotoUrl!) : null,
          child: tieneFoto
              ? null
              : Text(
                  alumno.nombre.isNotEmpty
                      ? alumno.nombre[0].toUpperCase()
                      : '?',
                  style: const TextStyle(color: Colors.white)),
        ),
        title: Row(
          children: [
            Flexible(
              child: Text(alumno.nombre,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(fontWeight: FontWeight.w700)),
            ),
            if (alumno.esMenor)
              const _EtiquetaAlumno('menor')
            else if (alumno.esApp)
              const _EtiquetaAlumno('app'),
          ],
        ),
        subtitle: Text(
          () {
            final deuda = pend > 0
                ? 'Debe S/ ${pend.toStringAsFixed(2)}'
                : 'Al día';
            if (alumno.esMenor) {
              return 'Apoderado: ${alumno.apoderadoNombre} · $deuda';
            }
            return alumno.esApp ? 'Vinculado · $deuda' : deuda;
          }(),
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
        ),
        trailing: const Icon(Icons.chevron_right),
        onTap: () => Navigator.of(context).push(MaterialPageRoute(
            builder: (_) => AlumnoDetalleScreen(alumnoId: alumno.id))),
      ),
    );
  }
}

/// Detalle de un alumno: inscribir a un plan, clase suelta, y sus cuotas
/// (marcar pagada / recordar por WhatsApp).
class AlumnoDetalleScreen extends StatelessWidget {
  const AlumnoDetalleScreen({super.key, required this.alumnoId});
  final String alumnoId;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Alumno')),
      body: ListenableBuilder(
        listenable: appState,
        builder: (context, _) {
          Alumno? alumno;
          for (final a in appState.alumnos) {
            if (a.id == alumnoId) alumno = a;
          }
          if (alumno == null) {
            return const Center(child: Text('Alumno no encontrado'));
          }
          final al = alumno;
          final ac = appState.miAcademia;
          final cuotas = appState.cuotasDeAlumno(al.id);
          final hoy = DateTime.now();
          return ListView(
            padding: const EdgeInsets.all(18),
            children: [
              Text(al.nombre,
                  style: const TextStyle(
                      fontWeight: FontWeight.w800, fontSize: 22)),
              if (al.esMenor)
                Text(
                    'Apoderado: ${al.apoderadoNombre}'
                    '${al.edad != null ? ' · ${al.edad} años' : ''}',
                    style: const TextStyle(color: textoTenue)),
              if (al.whatsappContacto.isNotEmpty)
                Text(
                    '${al.esMenor ? 'WhatsApp apoderado' : 'WhatsApp'}: ${al.whatsappContacto}',
                    style: const TextStyle(color: textoTenue)),
              const SizedBox(height: 16),
              Row(
                children: [
                  Expanded(
                    child: OutlinedButton.icon(
                      onPressed: ac == null
                          ? null
                          : () => _inscribir(context, al, ac.planes),
                      icon: const Icon(Icons.assignment_add),
                      label: const Text('Inscribir a plan'),
                    ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: OutlinedButton.icon(
                      onPressed: () => _claseSuelta(context, al),
                      icon: const Icon(Icons.add),
                      label: const Text('Clase suelta'),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 18),
              const Text('Cuotas',
                  style: TextStyle(fontWeight: FontWeight.w800, fontSize: 17)),
              const SizedBox(height: 6),
              if (cuotas.isEmpty)
                const Text('Sin cuotas. Inscríbelo a un plan o agrega una clase.',
                    style: TextStyle(color: textoTenue)),
              for (final c in cuotas)
                _FilaCuota(cuota: c, alumno: al, hoy: hoy),
            ],
          );
        },
      ),
    );
  }

  Future<void> _inscribir(
      BuildContext context, Alumno al, List<Plan> planes) async {
    if (planes.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text('Primero crea planes en tu academia (editar).')));
      return;
    }
    final plan = await showModalBottomSheet<Plan>(
      context: context,
      backgroundColor: Theme.of(context).colorScheme.surface,
      builder: (_) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Padding(
              padding: EdgeInsets.all(16),
              child: Text('Elige el plan',
                  style: TextStyle(fontWeight: FontWeight.w800, fontSize: 17)),
            ),
            for (final p in planes)
              ListTile(
                title: Text(p.nombre),
                subtitle: Text(p.tipo == TipoPlan.porClase
                    ? 'Por clase · S/ ${p.precioMes.toStringAsFixed(2)}'
                    : '${p.meses} ${p.meses == 1 ? 'mes' : 'meses'} · Total S/ ${p.total.toStringAsFixed(2)}'),
                onTap: () => Navigator.pop(context, p),
              ),
          ],
        ),
      ),
    );
    if (plan == null) return;
    if (plan.tipo == TipoPlan.porClase) {
      appState.agregarClaseSuelta(al, plan.precioMes, concepto: plan.nombre);
    } else {
      appState.inscribir(al, plan);
    }
  }

  Future<void> _claseSuelta(BuildContext context, Alumno al) async {
    final monto = TextEditingController();
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Clase suelta'),
        content: TextField(
          controller: monto,
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          decoration: const InputDecoration(labelText: 'Monto', prefixText: 'S/ '),
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('Cancelar')),
          FilledButton(
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('Registrar')),
        ],
      ),
    );
    if (ok == true) {
      final m = double.tryParse(monto.text.trim().replaceAll(',', '.'));
      if (m != null && m > 0) appState.agregarClaseSuelta(al, m);
    }
  }
}

class _FilaCuota extends StatelessWidget {
  const _FilaCuota(
      {required this.cuota, required this.alumno, required this.hoy});
  final dynamic cuota; // Cuota
  final Alumno alumno;
  final DateTime hoy;

  @override
  Widget build(BuildContext context) {
    final c = cuota;
    final vencida = c.vencidaAl(hoy);
    final Color estadoColor = c.pagada
        ? verde
        : vencida
            ? clayOscuro
            : textoTenue;
    final String estado = c.pagada
        ? 'Pagada'
        : vencida
            ? 'Vencida'
            : 'Pendiente';
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: trazo),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(c.concepto,
                    style: const TextStyle(fontWeight: FontWeight.w700)),
              ),
              Text('S/ ${c.monto.toStringAsFixed(2)}',
                  style: const TextStyle(fontWeight: FontWeight.w800)),
            ],
          ),
          const SizedBox(height: 4),
          Row(
            children: [
              Text(
                  'Vence ${c.vencimiento.day}/${c.vencimiento.month}/${c.vencimiento.year}',
                  style: const TextStyle(color: textoTenue, fontSize: 12)),
              const SizedBox(width: 8),
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                decoration: BoxDecoration(
                    color: estadoColor.withOpacity(0.12),
                    borderRadius: BorderRadius.circular(999)),
                child: Text(estado,
                    style: TextStyle(
                        color: estadoColor,
                        fontSize: 11,
                        fontWeight: FontWeight.w700)),
              ),
            ],
          ),
          const SizedBox(height: 6),
          Row(
            mainAxisAlignment: MainAxisAlignment.end,
            children: [
              if (!c.pagada) ...[
                TextButton.icon(
                  onPressed: () => _recordar(context, c),
                  icon: const Icon(Icons.chat, size: 18, color: verde),
                  label: const Text('Recordar'),
                ),
                const SizedBox(width: 4),
              ],
              FilledButton(
                style: FilledButton.styleFrom(
                    backgroundColor: c.pagada ? Colors.grey : verdeCancha,
                    padding:
                        const EdgeInsets.symmetric(horizontal: 14, vertical: 8)),
                onPressed: () =>
                    appState.marcarCuotaPagada(c.id, pagada: !c.pagada),
                child: Text(c.pagada ? 'Marcar impaga' : 'Marcar pagada'),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Future<void> _recordar(BuildContext context, dynamic c) async {
    final tel = alumno.whatsappContacto;
    if (tel.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text('No hay WhatsApp registrado para recordar el pago.')));
      return;
    }
    // Si es menor, el mensaje va al apoderado y menciona al alumno.
    final saludo = alumno.esMenor ? alumno.apoderadoNombre : alumno.nombre;
    final deQuien = alumno.esMenor ? ' de ${alumno.nombre}' : '';
    final msg = 'Hola $saludo, te recuerdo el pago$deQuien de "${c.concepto}" '
        'por S/ ${c.monto.toStringAsFixed(2)}. ¡Gracias!';
    final ok = await WhatsAppLink.abrir(tel, msg);
    if (!ok && context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('No pude abrir WhatsApp.')));
    }
  }
}
