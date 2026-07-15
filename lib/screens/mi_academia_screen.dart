import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../models/academia.dart';
import '../models/invitacion.dart';
import '../services/pagos_service.dart';
import '../services/whatsapp_link.dart';
import '../state/app_state.dart';
import '../theme.dart';
import 'asistencia_screen.dart';
import 'campeonatos_screen.dart';
import 'chats_academia_screen.dart';
import 'crear_academia_screen.dart';
import 'recargar_saldo_screen.dart';
import 'reporte_academia_screen.dart';
import '../utils/moneda.dart';
import '../config/pais.dart';

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
              _DestacarCard(academia: ac),
              Padding(
                padding: const EdgeInsets.fromLTRB(18, 16, 18, 8),
                child: Row(
                  children: [
                    Expanded(
                        child: _Metrica(
                            'Por cobrar',
                            '${ac.monedaSimbolo} ${porCobrar.toStringAsFixed(2)}',
                            Theme.of(context).colorScheme.primary)),
                    const SizedBox(width: 10),
                    Expanded(
                        child: _Metrica('Vencido',
                            '${ac.monedaSimbolo} ${vencido.toStringAsFixed(2)}', clayOscuro)),
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
                    Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        TextButton.icon(
                          onPressed: () => _invitarAlumno(context, ac),
                          icon: const Icon(Icons.mail_outline, size: 20),
                          label: const Text('Invitar'),
                        ),
                        TextButton.icon(
                          onPressed: () => _agregarAlumno(context, ac),
                          icon: const Icon(Icons.person_add_alt_1, size: 20),
                          label: const Text('Agregar'),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
              _RosterAlumnos(academia: ac),
              _SeccionInvitaciones(academia: ac),
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
                decoration: InputDecoration(
                    labelText: 'WhatsApp', prefixText: '$codigoTelActual ')),
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

  /// Invita a un alumno por CORREO (le aparece solo al entrar a la app) y/o por
  /// WhatsApp (le llega el código de la academia). Con uno basta.
  static Future<void> _invitarAlumno(BuildContext context, Academia ac) async {
    final nombre = TextEditingController();
    final email = TextEditingController();
    final tel = TextEditingController();
    final res = await showDialog<({bool ok, String mensaje, String telWa})>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Invitar alumno'),
        content: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                  'Por correo le aparece sola al entrar a la app; por WhatsApp le '
                  'llega el código. Con uno basta.',
                  style: TextStyle(fontSize: 13, color: textoTenue)),
              const SizedBox(height: 12),
              TextField(
                  controller: nombre,
                  textCapitalization: TextCapitalization.words,
                  decoration:
                      const InputDecoration(labelText: 'Nombre (opcional)')),
              TextField(
                  controller: email,
                  keyboardType: TextInputType.emailAddress,
                  autocorrect: false,
                  decoration: const InputDecoration(
                      labelText: 'Correo (Gmail)',
                      hintText: 'alumno@gmail.com')),
              TextField(
                  controller: tel,
                  keyboardType: TextInputType.phone,
                  decoration: InputDecoration(
                      labelText: 'WhatsApp', prefixText: '$codigoTelActual ')),
            ],
          ),
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx),
              child: const Text('Cancelar')),
          FilledButton(
            onPressed: () {
              final inv = appState.crearInvitacion(
                academia: ac,
                nombre: nombre.text,
                email: email.text,
                telefono: tel.text,
              );
              if (inv == null) {
                Navigator.pop(ctx, (
                  ok: false,
                  mensaje: 'Escribe un correo o un WhatsApp.',
                  telWa: ''
                ));
                return;
              }
              Navigator.pop(ctx, (
                ok: true,
                mensaje: inv.email.isNotEmpty
                    ? 'Invitación creada. Le aparecerá al entrar con ${inv.email}.'
                    : 'Invitación creada. Se la mandamos por WhatsApp.',
                telWa: inv.telefono,
              ));
            },
            child: const Text('Invitar'),
          ),
        ],
      ),
    );
    if (res == null || !context.mounted) return;
    if (res.telWa.isNotEmpty) {
      await WhatsAppLink.abrir(
          res.telWa, _mensajeInvitacion(ac, nombre.text.trim()));
    }
    if (context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text(res.mensaje), backgroundColor: res.ok ? bosque : null));
    }
  }
}

const _kReleaseUrl =
    'https://github.com/dcalagua/canchas-app-lima/releases/tag/v0.1.0';

/// Mensaje de invitación por WhatsApp (con el código de la academia).
String _mensajeInvitacion(Academia ac, String nombre) {
  final saludo = nombre.isNotEmpty ? '¡Hola $nombre!' : '¡Hola!';
  return '$saludo Te invito a mi academia "${ac.nombre}" en Pichangol 🎾\n\n'
      '1) Descarga la app: $_kReleaseUrl\n'
      '2) Entra a Academias → "Unirme con código"\n'
      '3) Ingresa el código: ${ac.codigo}\n\n'
      'Ahí verás tus clases y pagos. ¡Nos vemos en la cancha!';
}

/// Lista de invitaciones que el profe creó (pendientes/aceptadas), con acciones
/// para reenviar por WhatsApp o cancelar.
class _SeccionInvitaciones extends StatelessWidget {
  const _SeccionInvitaciones({required this.academia});
  final Academia academia;

  @override
  Widget build(BuildContext context) {
    final invs = appState.invitacionesDe(academia.id);
    if (invs.isEmpty) return const SizedBox.shrink();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Padding(
          padding: EdgeInsets.fromLTRB(18, 20, 18, 4),
          child: Text('Invitaciones',
              style: TextStyle(fontWeight: FontWeight.w800, fontSize: 17)),
        ),
        for (final inv in invs)
          _TarjetaInvitacion(inv: inv, academia: academia),
      ],
    );
  }
}

class _TarjetaInvitacion extends StatelessWidget {
  const _TarjetaInvitacion({required this.inv, required this.academia});
  final Invitacion inv;
  final Academia academia;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final aceptada = inv.estado == EstadoInvitacion.aceptada;
    final color = aceptada ? cs.primary : textoTenue;
    return Container(
      margin: const EdgeInsets.fromLTRB(18, 8, 18, 0),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: cs.surface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: trazo),
      ),
      child: Row(
        children: [
          CircleAvatar(
            radius: 18,
            backgroundColor: color.withOpacity(0.14),
            child: Icon(
                inv.email.isNotEmpty
                    ? Icons.mail_outline
                    : Icons.chat_bubble_outline,
                size: 18,
                color: color),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                    inv.nombreSugerido.isNotEmpty
                        ? inv.nombreSugerido
                        : inv.destino,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                        fontWeight: FontWeight.w700, color: cs.onSurface)),
                Text('${inv.destino} · ${inv.estado.etiqueta}',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(color: textoTenue, fontSize: 12)),
              ],
            ),
          ),
          if (aceptada)
            Padding(
              padding: const EdgeInsets.only(left: 8),
              child: Icon(Icons.check_circle, color: cs.primary, size: 22),
            )
          else ...[
            if (inv.telefono.isNotEmpty)
              IconButton(
                tooltip: 'Reenviar por WhatsApp',
                icon: const Icon(Icons.share, color: Color(0xFF25D366)),
                onPressed: () => WhatsAppLink.abrir(
                    inv.telefono, _mensajeInvitacion(academia, inv.nombreSugerido)),
              ),
            IconButton(
              tooltip: 'Cancelar',
              icon: const Icon(Icons.close, color: textoTenue),
              onPressed: () => appState.cancelarInvitacion(inv.id),
            ),
          ],
        ],
      ),
    );
  }
}

/// "Destaca tu academia": prepago que pone la academia arriba en la lista (con
/// estrella), reusando la recarga de Culqi. Más saldo = más visibilidad, igual
/// que las canchas. El saldo de la academia va aparte del de las canchas.
class _DestacarCard extends StatefulWidget {
  const _DestacarCard({required this.academia});
  final Academia academia;
  @override
  State<_DestacarCard> createState() => _DestacarCardState();
}

class _DestacarCardState extends State<_DestacarCard> {
  Map<String, int>? _vistas; // {semana, total} de impresiones de la academia

  @override
  void initState() {
    super.initState();
    appState.sincronizarSaldoAcademia(widget.academia.id);
    appState.cargarDestacados();
    _cargarVistas();
  }

  Future<void> _cargarVistas() async {
    final v = await PagosService.resumenVistas([widget.academia.id]);
    if (mounted && v != null) setState(() => _vistas = v);
  }

  Future<void> _recargar() async {
    final monto = await Navigator.of(context).push<int>(MaterialPageRoute(
      builder: (_) => RecargarSaldoScreen(
          duenoId: widget.academia.id, titulo: 'Destacar academia'),
    ));
    if (monto != null && mounted) {
      await appState.sincronizarSaldoAcademia(widget.academia.id);
      await appState.cargarDestacados();
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final saldo = appState.saldoAcademiaDe(widget.academia.id);
    final nivel = appState.nivelDestacadoAcademia(widget.academia);
    final destacada = nivel > 0;
    return Container(
      margin: const EdgeInsets.fromLTRB(18, 12, 18, 4),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [Color(0xFF128C7E), Color(0xFF075E54)],
        ),
        borderRadius: BorderRadius.circular(18),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(destacada ? Icons.star : Icons.trending_up,
                  color: Colors.white, size: 20),
              const SizedBox(width: 8),
              Text(
                  destacada
                      ? '${medallaDestacado(nivel)} Nivel ${etiquetaNivelDestacado(nivel)}'
                      : 'Destaca tu academia',
                  style: t.titleMedium
                      ?.copyWith(color: Colors.white, fontWeight: FontWeight.w800)),
            ],
          ),
          const SizedBox(height: 6),
          Text(
            destacada
                ? 'Apareces primero en la lista de academias. Saldo: ${widget.academia.monedaSimbolo} $saldo. '
                    'Más saldo = mejor posición: Plata desde ${widget.academia.monedaSimbolo} 50, Oro desde ${widget.academia.monedaSimbolo} 200.'
                : 'Pon saldo y tu academia aparece destacada (arriba y con '
                    'medalla) para que más alumnos la encuentren. '
                    'Bronce desde ${widget.academia.monedaSimbolo} 1, Plata ${widget.academia.monedaSimbolo} 50, Oro ${widget.academia.monedaSimbolo} 200.',
            style: t.bodySmall
                ?.copyWith(color: Colors.white.withOpacity(0.92), height: 1.3),
          ),
          if (_vistas != null && (_vistas!['semana'] ?? 0) > 0) ...[
            const SizedBox(height: 10),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
              decoration: BoxDecoration(
                color: Colors.white.withOpacity(0.16),
                borderRadius: BorderRadius.circular(10),
              ),
              child: Text(
                '👀 ${_vistas!['semana']} personas vieron tu academia esta semana'
                '${(_vistas!['total'] ?? 0) > (_vistas!['semana'] ?? 0) ? ' · ${_vistas!['total']} en total' : ''}',
                style: t.bodySmall
                    ?.copyWith(color: Colors.white, fontWeight: FontWeight.w700),
              ),
            ),
          ],
          const SizedBox(height: 12),
          SizedBox(
            width: double.infinity,
            child: FilledButton.icon(
              style: FilledButton.styleFrom(
                  backgroundColor: Colors.white, foregroundColor: lima),
              onPressed: _recargar,
              icon: const Icon(Icons.add),
              label: Text(saldo > 0
                  ? 'Recargar saldo (${widget.academia.monedaSimbolo} $saldo)'
                  : 'Poner saldo y destacar'),
            ),
          ),
        ],
      ),
    );
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
              style: FilledButton.styleFrom(backgroundColor: lima, foregroundColor: Colors.white),
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
              style: t.bodySmall?.copyWith(color: textoTenueDe(context))),
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
          colors: [lima, teal], // verde WhatsApp
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
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: t.headlineSmall?.copyWith(
                        color: Colors.white, fontWeight: FontWeight.w800)),
              ),
              IconButton(
                tooltip: 'Mensajes',
                icon: const Icon(Icons.forum_outlined, color: Colors.white),
                onPressed: () => Navigator.of(context).push(MaterialPageRoute(
                    builder: (_) =>
                        ChatsAcademiaScreen(academiaId: academia.id))),
              ),
              IconButton(
                tooltip: 'Reporte de pagos',
                icon: const Icon(Icons.insights_outlined, color: Colors.white),
                onPressed: () => Navigator.of(context).push(MaterialPageRoute(
                    builder: (_) =>
                        ReporteAcademiaScreen(academiaId: academia.id))),
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

/// Deuda pendiente de un alumno (suma de cuotas impagas) + si alguna está
/// vencida. Base del roster de cobranza.
({double deuda, bool vencido}) _deudaAlumno(String alumnoId) {
  var deuda = 0.0;
  var vencido = false;
  final hoy = DateTime.now();
  for (final c in appState.cuotasDeAlumno(alumnoId)) {
    if (!c.pagada) {
      deuda += (c.monto as num).toDouble();
      if (c.vencidaAl(hoy)) vencido = true;
    }
  }
  return (deuda: deuda, vencido: vencido);
}

/// Recordatorio de cobranza por WhatsApp del TOTAL adeudado por el alumno.
Future<void> _recordarDeuda(
    BuildContext context, Alumno alumno, String moneda, double deuda) async {
  final tel = alumno.whatsappContacto;
  if (tel.isEmpty) {
    ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
        content: Text('No hay WhatsApp registrado para recordar el pago.')));
    return;
  }
  final saludo = alumno.esMenor ? alumno.apoderadoNombre : alumno.nombre;
  final deQuien = alumno.esMenor ? ' de ${alumno.nombre}' : '';
  final msg = 'Hola $saludo, te recuerdo el pago pendiente$deQuien por '
      '$moneda ${deuda.toStringAsFixed(2)}. ¡Gracias!';
  final ok = await WhatsAppLink.abrir(tel, msg);
  if (!ok && context.mounted) {
    ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('No pude abrir WhatsApp.')));
  }
}

enum _FiltroAlumno { todos, alDia, morosos }

/// Roster de alumnos como TABLERO DE COBRANZA (refuerzo del panel): buscador,
/// filtros Todos/Al día/Morosos, orden con los que más deben arriba, y en cada
/// tarjeta el estado (debe/vencido) + recordatorio por WhatsApp.
class _RosterAlumnos extends StatefulWidget {
  const _RosterAlumnos({required this.academia});
  final Academia academia;

  @override
  State<_RosterAlumnos> createState() => _RosterAlumnosState();
}

class _RosterAlumnosState extends State<_RosterAlumnos> {
  String _q = '';
  _FiltroAlumno _filtro = _FiltroAlumno.todos;

  @override
  Widget build(BuildContext context) {
    final ac = widget.academia;
    final todos = appState.alumnosDe(ac.id);
    if (todos.isEmpty) {
      return const Padding(
        padding: EdgeInsets.all(24),
        child: Text(
            'Aún no tienes alumnos. Invítalos por correo o WhatsApp, o '
            'agrégalos a mano y ellos verán sus cuotas.',
            style: TextStyle(color: textoTenue)),
      );
    }
    // Deuda por alumno, cacheada en este build.
    final deuda = <String, ({double deuda, bool vencido})>{};
    for (final a in todos) {
      deuda[a.id] = _deudaAlumno(a.id);
    }
    final morososN = todos.where((a) => deuda[a.id]!.deuda > 0).length;
    final alDiaN = todos.length - morososN;

    final q = _q.trim().toLowerCase();
    final lista = todos.where((a) {
      final d = deuda[a.id]!.deuda;
      if (_filtro == _FiltroAlumno.morosos && d <= 0) return false;
      if (_filtro == _FiltroAlumno.alDia && d > 0) return false;
      if (q.isNotEmpty && !a.nombre.toLowerCase().contains(q)) return false;
      return true;
    }).toList();
    lista.sort((a, b) {
      final da = deuda[a.id]!, db = deuda[b.id]!;
      // Deudores arriba (salvo en el filtro "Al día"); a más deuda, más arriba.
      if (_filtro != _FiltroAlumno.alDia) {
        if ((db.deuda > 0) != (da.deuda > 0)) return db.deuda > 0 ? 1 : -1;
        if (da.deuda != db.deuda) return db.deuda.compareTo(da.deuda);
      }
      return a.nombre.toLowerCase().compareTo(b.nombre.toLowerCase());
    });

    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(18, 4, 18, 8),
          child: TextField(
            onChanged: (v) => setState(() => _q = v),
            decoration: InputDecoration(
              hintText: 'Buscar alumno…',
              prefixIcon: const Icon(Icons.search),
              isDense: true,
              border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(14),
                  borderSide: const BorderSide(color: trazo)),
              enabledBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(14),
                  borderSide: const BorderSide(color: trazo)),
            ),
          ),
        ),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 14),
          child: Row(
            children: [
              _ChipFiltro(
                  texto: 'Todos',
                  n: todos.length,
                  activo: _filtro == _FiltroAlumno.todos,
                  onTap: () => setState(() => _filtro = _FiltroAlumno.todos)),
              _ChipFiltro(
                  texto: 'Al día',
                  n: alDiaN,
                  activo: _filtro == _FiltroAlumno.alDia,
                  onTap: () => setState(() => _filtro = _FiltroAlumno.alDia)),
              _ChipFiltro(
                  texto: 'Morosos',
                  n: morososN,
                  activo: _filtro == _FiltroAlumno.morosos,
                  color: clayOscuro,
                  onTap: () =>
                      setState(() => _filtro = _FiltroAlumno.morosos)),
            ],
          ),
        ),
        if (lista.isEmpty)
          const Padding(
            padding: EdgeInsets.all(24),
            child: Text('Nadie en este filtro.',
                style: TextStyle(color: textoTenue)),
          ),
        for (final al in lista)
          _TarjetaAlumno(
            alumno: al,
            moneda: ac.monedaSimbolo,
            deuda: deuda[al.id]!.deuda,
            vencido: deuda[al.id]!.vencido,
          ),
      ],
    );
  }
}

class _ChipFiltro extends StatelessWidget {
  const _ChipFiltro({
    required this.texto,
    required this.n,
    required this.activo,
    required this.onTap,
    this.color,
  });
  final String texto;
  final int n;
  final bool activo;
  final VoidCallback onTap;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    final c = color ?? Theme.of(context).colorScheme.primary;
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 4),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(999),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
          decoration: BoxDecoration(
            color: activo ? c.withOpacity(0.12) : Colors.white,
            borderRadius: BorderRadius.circular(999),
            border: Border.all(color: activo ? c : trazo),
          ),
          child: Text('$texto · $n',
              style: TextStyle(
                  fontSize: 12.5,
                  fontWeight: FontWeight.w700,
                  color: activo ? c : textoTenue)),
        ),
      ),
    );
  }
}

class _TarjetaAlumno extends StatelessWidget {
  const _TarjetaAlumno(
      {required this.alumno,
      required this.moneda,
      required this.deuda,
      required this.vencido});
  final Alumno alumno;
  final String moneda;
  final double deuda;
  final bool vencido;

  @override
  Widget build(BuildContext context) {
    final pend = deuda;
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
            if (vencido) ...[
              const SizedBox(width: 6),
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
                decoration: BoxDecoration(
                    color: clayOscuro.withOpacity(0.14),
                    borderRadius: BorderRadius.circular(999)),
                child: const Text('vencido',
                    style: TextStyle(
                        color: clayOscuro,
                        fontSize: 10.5,
                        fontWeight: FontWeight.w800)),
              ),
            ] else if (alumno.esMenor)
              const _EtiquetaAlumno('menor')
            else if (alumno.esApp)
              const _EtiquetaAlumno('app'),
          ],
        ),
        subtitle: Text(
          () {
            final estado = pend > 0
                ? 'Debe $moneda ${pend.toStringAsFixed(2)}'
                : 'Al día';
            if (alumno.esMenor) {
              return 'Apoderado: ${alumno.apoderadoNombre} · $estado';
            }
            return alumno.esApp ? 'Vinculado · $estado' : estado;
          }(),
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
        ),
        trailing: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            // Cobranza de un toque: recuerda el total adeudado por WhatsApp.
            if (pend > 0 && alumno.whatsappContacto.isNotEmpty)
              IconButton(
                tooltip: 'Recordar pago',
                icon: const Icon(Icons.chat, color: verde),
                onPressed: () =>
                    _recordarDeuda(context, alumno, moneda, pend),
              ),
            const Icon(Icons.chevron_right),
          ],
        ),
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
                _FilaCuota(
                    cuota: c,
                    alumno: al,
                    hoy: hoy,
                    moneda: ac?.monedaSimbolo ?? monedaSimbolo),
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
    final mon = appState.miAcademia?.monedaSimbolo ?? monedaSimbolo;
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
                    ? 'Por clase · $mon ${p.precioMes.toStringAsFixed(2)}'
                    : '${p.meses} ${p.meses == 1 ? 'mes' : 'meses'} · Total $mon ${p.total.toStringAsFixed(2)}'),
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
    final mon = appState.miAcademia?.monedaSimbolo ?? monedaSimbolo;
    final monto = TextEditingController();
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Clase suelta'),
        content: TextField(
          controller: monto,
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          decoration: InputDecoration(labelText: 'Monto', prefixText: '$mon '),
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
      {required this.cuota,
      required this.alumno,
      required this.hoy,
      required this.moneda});
  final dynamic cuota; // Cuota
  final Alumno alumno;
  final DateTime hoy;
  final String moneda;

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
              Text('$moneda ${c.monto.toStringAsFixed(2)}',
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
        'por $moneda ${c.monto.toStringAsFixed(2)}. ¡Gracias!';
    final ok = await WhatsAppLink.abrir(tel, msg);
    if (!ok && context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('No pude abrir WhatsApp.')));
    }
  }
}
