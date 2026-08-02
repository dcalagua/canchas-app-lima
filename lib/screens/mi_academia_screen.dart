import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../config/features.dart';
import '../models/academia.dart';
import '../models/invitacion.dart';
import '../services/pagos_service.dart';
import '../services/whatsapp_link.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/dialogo_pichangol.dart';
import '../widgets/ancho_lectura.dart';
import '../widgets/logo_academia.dart';
import 'cobros_screen.dart';
import 'crear_academia_screen.dart';
import 'post_del_dia_screen.dart';
import 'ranking_academia_screen.dart';
import 'recargar_saldo_screen.dart';
import 'servicios_screen.dart';
import '../utils/moneda.dart';
import '../config/pais.dart';

/// Panel del PROFE: su academia, alumnos y cobros (Fase 1). Sin pasarela: marca
/// pagos en efectivo y manda recordatorios por WhatsApp.
class MiAcademiaScreen extends StatelessWidget {
  const MiAcademiaScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: AnchoLectura(
        child: ListenableBuilder(
        listenable: appState,
        builder: (context, _) {
          final ac = appState.miAcademia;
          if (ac == null) {
            // Aún no sabemos si el profe tiene academia: la nube puede no haber
            // bajado (típico tras reinstalar). Mostramos spinner y disparamos la
            // carga; así NO se crea una academia duplicada por adelantarse.
            if (!appState.academiasRemotasCargadas) {
              appState.cargarAcademiasRemotas(); // idempotente (guard interno)
              return const _CargandoAcademia();
            }
            return const _SinAcademia();
          }
          // Al abrir, trae de la nube las matrículas nuevas (alumnos que se
          // inscribieron desde otro dispositivo). Con throttle; no bloquea.
          appState.syncMatriculas();
          final alumnos = appState.alumnosDe(ac.id);
          final hoy = DateTime.now();
          double porCobrar = 0, vencido = 0;
          for (final c in appState.cuotasDe(ac.id)) {
            if (!c.pagada) {
              porCobrar += c.monto;
              if (c.vencidaAl(hoy)) vencido += c.monto;
            }
          }
          return RefreshIndicator(
            color: lima,
            onRefresh: () => appState.refrescarAcademiaProfe(),
            child: ListView(
              padding: EdgeInsets.zero,
              children: [
              _Header(academia: ac),
              // ARRIBA lo del día a día del profe: la PLATA (por cobrar/vencido)
              // y sus ALUMNOS. El código/nivel/ranking bajan a una sección
              // plegable para no robar visibilidad (antes tapaban lo importante).
              Padding(
                padding: const EdgeInsets.fromLTRB(18, 14, 18, 8),
                child: Row(
                  children: [
                    // Por cobrar / Vencido → llevan a Cobros (recordar morosos).
                    Expanded(
                        child: _Metrica(
                            'Por cobrar',
                            '${ac.monedaSimbolo} ${porCobrar.toStringAsFixed(2)}',
                            Theme.of(context).colorScheme.primary,
                            onTap: () => _abrirCobros(context, ac.id))),
                    const SizedBox(width: 10),
                    Expanded(
                        child: _Metrica('Vencido',
                            '${ac.monedaSimbolo} ${vencido.toStringAsFixed(2)}', clayOscuro,
                            onTap: () => _abrirCobros(context, ac.id))),
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
              if (kServiciosPichangolActivo) _CmPostDelDiaTile(academia: ac),
              // Secundario y PLEGABLE: compartir código, nivel/destacar y
              // ranking. Colapsado por defecto → no roba espacio a lo importante.
              Theme(
                data: Theme.of(context)
                    .copyWith(dividerColor: Colors.transparent),
                child: ExpansionTile(
                  tilePadding: const EdgeInsets.symmetric(horizontal: 18),
                  leading: Icon(Icons.ios_share,
                      color: Theme.of(context).colorScheme.primary),
                  title: const Text('Compartir código · Nivel · Ranking',
                      style:
                          TextStyle(fontWeight: FontWeight.w800, fontSize: 14.5)),
                  subtitle: const Text(
                      'Invita alumnos con tu código y sube tu visibilidad',
                      style: TextStyle(fontSize: 12)),
                  children: [
                    // En tablet las dos tarjetas van lado a lado (mismo alto).
                    LayoutBuilder(builder: (context, cons) {
                      final codigo = _CodigoCard(academia: ac);
                      final destacar = _DestacarCard(academia: ac);
                      if (cons.maxWidth >= 680) {
                        return IntrinsicHeight(
                          child: Row(
                            crossAxisAlignment: CrossAxisAlignment.stretch,
                            children: [
                              Expanded(child: codigo),
                              Expanded(child: destacar),
                            ],
                          ),
                        );
                      }
                      return Column(children: [codigo, destacar]);
                    }),
                    _AccesoRanking(academiaId: ac.id),
                  ],
                ),
              ),
              const SizedBox(height: 30),
            ],
            ),
          );
        },
      )),
    );
  }

  /// Abre Cobros (morosidad + recordar a morosos) desde las métricas del home.
  static void _abrirCobros(BuildContext context, String academiaId) {
    Navigator.of(context).push(MaterialPageRoute(
        builder: (_) => CobrosScreen(academiaId: academiaId)));
  }

  static Future<void> _agregarAlumno(
      BuildContext context, Academia ac) async {
    final nombre = TextEditingController();
    final whats = TextEditingController();
    var esSocio = true;
    var orden = 1; // orden de hermano (descuento familiar)
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setSt) => DialogoPichangol(
          titulo: 'Nuevo alumno',
          icono: Icons.person_add_alt_1,
          contenido: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                TextField(
                    controller: nombre,
                    decoration: const InputDecoration(labelText: 'Nombre')),
                TextField(
                    controller: whats,
                    keyboardType: TextInputType.phone,
                    decoration: InputDecoration(
                        labelText: 'WhatsApp',
                        prefixText: '$codigoTelActual ')),
                if (ac.tieneTarifaInvitado) ...[
                  const SizedBox(height: 6),
                  SwitchListTile(
                    contentPadding: EdgeInsets.zero,
                    value: esSocio,
                    onChanged: (v) => setSt(() => esSocio = v),
                    title: const Text('Socio del club'),
                    subtitle: Text(esSocio
                        ? 'Paga tarifa de socio'
                        : 'Invitado: +${ac.monedaSimbolo} ${ac.recargoInvitado.toStringAsFixed(0)} por plan'),
                  ),
                ],
                if (ac.tieneDescuentoHermanos) ...[
                  const SizedBox(height: 12),
                  const Align(
                    alignment: Alignment.centerLeft,
                    child: Text('Orden de hermano (descuento familiar)',
                        style: TextStyle(
                            fontSize: 13, fontWeight: FontWeight.w600)),
                  ),
                  const SizedBox(height: 6),
                  Wrap(
                    spacing: 8,
                    children: [
                      for (final o in const [1, 2, 3])
                        ChoiceChip(
                          label: Text(_labelHermano(ac, o)),
                          selected: orden == o,
                          onSelected: (_) => setSt(() => orden = o),
                        ),
                    ],
                  ),
                ],
              ],
            ),
          ),
          acciones: [
            TextButton(
                onPressed: () => Navigator.pop(ctx, false),
                style: TextButton.styleFrom(foregroundColor: textoTenue),
                child: const Text('Cancelar')),
            FilledButton(
                style: FilledButton.styleFrom(
                    backgroundColor: lima,
                    foregroundColor: Colors.white,
                    shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(12)),
                    padding: const EdgeInsets.symmetric(
                        horizontal: 20, vertical: 12)),
                onPressed: () => Navigator.pop(ctx, true),
                child: const Text('Agregar',
                    style: TextStyle(fontWeight: FontWeight.w800))),
          ],
        ),
      ),
    );
    if (ok == true && nombre.text.trim().isNotEmpty) {
      appState.agregarAlumno(Alumno(
        id: 'al_${DateTime.now().microsecondsSinceEpoch}',
        academiaId: ac.id,
        nombre: nombre.text.trim(),
        whatsapp: whats.text.trim(),
        esSocioSede: esSocio,
        ordenHermano: orden,
      ));
    }
  }

  /// Etiqueta del chip de orden de hermano con su % de descuento.
  static String _labelHermano(Academia ac, int orden) {
    if (orden == 1) return 'Único / 1º';
    final pct = ac.descuentoHermanoPct(orden);
    final sufijo = pct > 0 ? ' (−${pct.toStringAsFixed(0)}%)' : '';
    return orden == 2 ? '2º hermano$sufijo' : '3º o más$sufijo';
  }

  /// Invita a un alumno por CORREO (le aparece solo al entrar a la app) y/o por
  /// WhatsApp (le llega el código de la academia). Con uno basta.
  static Future<void> _invitarAlumno(BuildContext context, Academia ac) async {
    final nombre = TextEditingController();
    final email = TextEditingController();
    final tel = TextEditingController();
    final res = await showDialog<({bool ok, String mensaje, String telWa})>(
      context: context,
      builder: (ctx) => DialogoPichangol(
        titulo: 'Invitar alumno',
        icono: Icons.mail_outline,
        contenido: SingleChildScrollView(
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
        acciones: [
          TextButton(
              onPressed: () => Navigator.pop(ctx),
              style: TextButton.styleFrom(foregroundColor: textoTenue),
              child: const Text('Cancelar')),
          FilledButton(
            style: FilledButton.styleFrom(
                backgroundColor: lima,
                foregroundColor: Colors.white,
                shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(12)),
                padding:
                    const EdgeInsets.symmetric(horizontal: 20, vertical: 12)),
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
            child: const Text('Invitar',
                style: TextStyle(fontWeight: FontWeight.w800)),
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
      // BILLETERA ÚNICA: la recarga entra a la billetera del DUEÑO (su correo),
      // no a una bolsa por academia. Así "Mi cuenta" y la academia ven lo mismo.
      builder: (_) => RecargarSaldoScreen(
          duenoId: widget.academia.dueno, titulo: 'Destacar academia'),
    ));
    if (monto != null && mounted) {
      await appState.sincronizarSaldoAcademia(widget.academia.id);
      await appState.cargarDestacados();
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final nivel = appState.nivelDestacadoAcademia(widget.academia);
    final destacada = nivel > 0;
    return Container(
      // Mismo margen que _CodigoCard: en tablet quedan alineadas y del mismo alto.
      margin: const EdgeInsets.fromLTRB(18, 16, 18, 0),
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
                ? 'Tu academia aparece primero en la lista. Sube de nivel con más '
                    'saldo: Plata desde ${widget.academia.monedaSimbolo} 50, '
                    'Oro desde ${widget.academia.monedaSimbolo} 200.'
                : 'Con saldo, tu academia aparece destacada (arriba y con medalla) '
                    'para que más alumnos la encuentren. '
                    'Bronce desde ${widget.academia.monedaSimbolo} 1, '
                    'Plata ${widget.academia.monedaSimbolo} 50, '
                    'Oro ${widget.academia.monedaSimbolo} 200.',
            style: t.bodySmall
                ?.copyWith(color: Colors.white.withOpacity(0.92), height: 1.3),
          ),
          const SizedBox(height: 6),
          Row(
            children: [
              const Icon(Icons.account_balance_wallet,
                  size: 14, color: Colors.white70),
              const SizedBox(width: 6),
              Expanded(
                child: Text(
                    'Es tu saldo único: el mismo de “Mi cuenta” y de tus canchas.',
                    style: t.bodySmall?.copyWith(
                        color: Colors.white.withOpacity(0.85),
                        fontStyle: FontStyle.italic,
                        height: 1.25)),
              ),
            ],
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
              icon: Icon(destacada ? Icons.trending_up : Icons.star),
              label: Text(destacada ? 'Subir de nivel' : 'Destacar mi academia'),
            ),
          ),
        ],
      ),
    );
  }
}

class _CargandoAcademia extends StatelessWidget {
  const _CargandoAcademia();
  @override
  Widget build(BuildContext context) {
    return const Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          CircularProgressIndicator(color: lima),
          SizedBox(height: 16),
          Text('Cargando tu academia…',
              style: TextStyle(color: textoTenue, fontWeight: FontWeight.w600)),
        ],
      ),
    );
  }
}

/// Acceso al RANKING interno del circuito (Fase 0). El profe entra a ver la
/// tabla y registrar resultados; los alumnos ven su carnet y compiten.
class _AccesoRanking extends StatelessWidget {
  const _AccesoRanking({required this.academiaId});
  final String academiaId;
  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.fromLTRB(18, 14, 18, 0),
      child: Material(
        color: cs.surface,
        borderRadius: BorderRadius.circular(16),
        child: InkWell(
          borderRadius: BorderRadius.circular(16),
          onTap: () => Navigator.of(context).push(MaterialPageRoute(
              builder: (_) => RankingAcademiaScreen(
                  academiaId: academiaId, esDueno: true))),
          child: Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(16),
              border: Border.all(color: trazo),
            ),
            child: Row(
              children: [
                Container(
                  width: 44,
                  height: 44,
                  decoration: BoxDecoration(
                    color: limaSuave,
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: const Icon(Icons.leaderboard, color: bosque),
                ),
                const SizedBox(width: 12),
                const Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('Ranking del circuito',
                          style: TextStyle(
                              fontWeight: FontWeight.w800, fontSize: 15)),
                      SizedBox(height: 2),
                      Text('Registra resultados y arma la tabla de tus alumnos.',
                          style: TextStyle(color: textoTenue, fontSize: 12.5)),
                    ],
                  ),
                ),
                const Icon(Icons.chevron_right, color: textoTenue),
              ],
            ),
          ),
        ),
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
    final padTop = MediaQuery.of(context).padding.top;
    // Celular apaisado (poca altura) → cabecera compacta: menos padding, título
    // más chico y saldo pegado, para que el banner no ocupe media pantalla.
    final compacto = MediaQuery.of(context).size.height < 520;
    return Container(
      width: double.infinity,
      padding: compacto
          ? EdgeInsets.fromLTRB(20, 10 + padTop, 20, 12)
          : EdgeInsets.fromLTRB(22, 20 + padTop, 22, 22),
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
              Container(
                margin: const EdgeInsets.only(right: 10),
                padding: const EdgeInsets.all(3),
                decoration: BoxDecoration(
                    color: Colors.white,
                    borderRadius: BorderRadius.circular(10)),
                child: LogoAcademia(
                    logoUrl: academia.logoUrl, size: compacto ? 28 : 34),
              ),
              Expanded(
                child: Text(academia.nombre,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: (compacto ? t.titleLarge : t.headlineSmall)?.copyWith(
                        color: Colors.white, fontWeight: FontWeight.w800)),
              ),
              // En móvil el menú principal (Cobros, Asistencia, Mensajes,
              // Torneos, Reporte, Billetera) vive en la BARRA INFERIOR
              // (AcademiaShell), igual que "Mis canchas". Aquí en la cabecera
              // solo quedan las acciones de configuración: Publicidad y Editar.
              // En tablet van en el rail lateral, así que la cabecera queda limpia.
              if (MediaQuery.of(context).size.width < 720) ...[
              if (kServiciosPichangolActivo)
                IconButton(
                  tooltip: 'Servicios (publicidad)',
                  icon: const Icon(Icons.campaign_outlined, color: Colors.white),
                  onPressed: () => Navigator.of(context).push(MaterialPageRoute(
                      builder: (_) => ServiciosScreen(
                          negocio:
                              appState.negocioServiciosDeAcademia(academia)))),
                ),
              IconButton(
                tooltip: 'Editar',
                icon: const Icon(Icons.edit, color: Colors.white),
                onPressed: () => Navigator.of(context).push(MaterialPageRoute(
                    builder: (_) => CrearAcademiaScreen(academia: academia))),
              ),
              ],
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
          SizedBox(height: compacto ? 10 : 14),
          _SaldoPill(academia: academia),
        ],
      ),
    );
  }
}

/// Píldora de SALDO siempre visible en la cabecera del dueño: ve su saldo de un
/// vistazo y toca para recargar (misma billetera prepago de la academia).
class _SaldoPill extends StatelessWidget {
  const _SaldoPill({required this.academia});
  final Academia academia;

  Future<void> _recargar(BuildContext context) async {
    await Navigator.of(context).push(MaterialPageRoute(
      // BILLETERA ÚNICA: recarga a la billetera del dueño (su correo).
      builder: (_) => RecargarSaldoScreen(
          duenoId: academia.dueno,
          titulo: 'Recargar saldo',
          pais: academia.pais),
    ));
    await appState.sincronizarSaldoAcademia(academia.id);
  }

  @override
  Widget build(BuildContext context) {
    final saldo = appState.saldoAcademiaDe(academia.id);
    return Material(
      color: Colors.white.withOpacity(0.18),
      borderRadius: BorderRadius.circular(999),
      child: InkWell(
        borderRadius: BorderRadius.circular(999),
        onTap: () => _recargar(context),
        child: Padding(
          padding: const EdgeInsets.fromLTRB(14, 9, 10, 9),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.account_balance_wallet,
                  size: 18, color: Colors.white),
              const SizedBox(width: 8),
              Flexible(
                child: Text('Saldo Pichangol  ',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                        color: Colors.white.withOpacity(0.85), fontSize: 13)),
              ),
              Text('${academia.monedaSimbolo} $saldo',
                  style: const TextStyle(
                      color: Colors.white,
                      fontSize: 16,
                      fontWeight: FontWeight.w900)),
              const SizedBox(width: 8),
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                decoration: BoxDecoration(
                  color: Colors.white,
                  borderRadius: BorderRadius.circular(999),
                ),
                child: const Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(Icons.add, size: 15, color: lima),
                    SizedBox(width: 2),
                    Text('Recargar',
                        style: TextStyle(
                            color: lima,
                            fontSize: 12.5,
                            fontWeight: FontWeight.w800)),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _Metrica extends StatelessWidget {
  const _Metrica(this.titulo, this.valor, this.color, {this.onTap});
  final String titulo;
  final String valor;
  final Color color;
  final VoidCallback? onTap; // si != null, la métrica es tocable

  @override
  Widget build(BuildContext context) {
    final card = Container(
      padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 10),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: onTap != null ? color.withOpacity(0.5) : trazo),
      ),
      child: Column(
        children: [
          Text(valor,
              style: TextStyle(
                  fontWeight: FontWeight.w800, fontSize: 16, color: color)),
          const SizedBox(height: 2),
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Text(titulo,
                  style: const TextStyle(color: textoTenue, fontSize: 12)),
              if (onTap != null)
                const Icon(Icons.chevron_right, size: 14, color: textoTenue),
            ],
          ),
        ],
      ),
    );
    if (onTap == null) return card;
    return InkWell(
        onTap: onTap, borderRadius: BorderRadius.circular(14), child: card);
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
            academia: ac,
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
    // Theme-aware: pastilla transparente con borde; teñida al activarse. Sin
    // blanco fijo ni gris no adaptativo (se leía mal en modo oscuro).
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 4),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(999),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
          decoration: BoxDecoration(
            color: activo ? c.withOpacity(0.15) : Colors.transparent,
            borderRadius: BorderRadius.circular(999),
            border: Border.all(
                color: activo ? c : textoTenueDe(context).withOpacity(0.4)),
          ),
          child: Text('$texto · $n',
              style: TextStyle(
                  fontSize: 12.5,
                  fontWeight: FontWeight.w700,
                  color: activo ? c : textoTenueDe(context))),
        ),
      ),
    );
  }
}

class _TarjetaAlumno extends StatelessWidget {
  const _TarjetaAlumno(
      {required this.alumno,
      required this.academia,
      required this.moneda,
      required this.deuda,
      required this.vencido});
  final Alumno alumno;
  final Academia academia;
  final String moneda;
  final double deuda;
  final bool vencido;

  /// Invita al padre/alumno a instalar la app y unirse con el código (así se
  /// auto-vincula a ESTE registro y todo pasa a ser in-app: avisos y pagos).
  Future<void> _invitar(BuildContext context) async {
    final tel = alumno.whatsappContacto;
    if (tel.isEmpty) return;
    final saludo = alumno.esMenor ? alumno.apoderadoNombre : alumno.nombre;
    final ok = await WhatsAppLink.abrir(tel, _mensajeInvitacion(academia, saludo));
    if (!ok && context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('No pude abrir WhatsApp.')));
    }
  }

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
            // Alumno SIN app: invitarlo (instala + se une con el código → todo
            // pasa a ser in-app: avisos y pagos, y se auto-vincula a este registro).
            if (!alumno.esApp && alumno.whatsappContacto.isNotEmpty)
              IconButton(
                tooltip: 'Invitar a la app',
                icon: const Icon(Icons.person_add_alt_1, color: teal),
                onPressed: () => _invitar(context),
              ),
            // Cobranza de un toque: recuerda el total adeudado por WhatsApp.
            if (pend > 0 && alumno.whatsappContacto.isNotEmpty)
              IconButton(
                tooltip: 'Recordar pago',
                icon: const Icon(Icons.chat, color: lima),
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
          var sedeNombre = '';
          if (al.sedeId.isNotEmpty && ac != null) {
            for (final s in ac.sedes) {
              if (s.id == al.sedeId) {
                sedeNombre = s.nombre;
                break;
              }
            }
          }
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
              if (sedeNombre.isNotEmpty)
                Padding(
                  padding: const EdgeInsets.only(top: 2),
                  child: Row(
                    children: [
                      const Icon(Icons.place, size: 14, color: textoTenue),
                      const SizedBox(width: 4),
                      Text('Sede: $sedeNombre',
                          style: const TextStyle(
                              color: textoTenue, fontWeight: FontWeight.w600)),
                    ],
                  ),
                ),
              _SuscripcionAlumnoInfoProfe(
                  alumnoId: al.id, moneda: ac?.monedaSimbolo ?? monedaSimbolo),
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
      isScrollControlled: true, // permite crecer y hacer scroll con muchos planes
      backgroundColor: Theme.of(context).colorScheme.surface,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (_) => SafeArea(
        child: ConstrainedBox(
          constraints: BoxConstraints(
              maxHeight: MediaQuery.of(context).size.height * 0.75),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Padding(
                padding: EdgeInsets.all(16),
                child: Text('Elige el plan',
                    style:
                        TextStyle(fontWeight: FontWeight.w800, fontSize: 17)),
              ),
              Flexible(
                child: ListView(
                  shrinkWrap: true,
                  children: [
                    // Planes AGRUPADOS por programa (mismo criterio que la ficha
                    // del alumno): un encabezado por programa y sus frecuencias.
                    for (final entrada in _agruparPorPrograma(planes).entries) ...[
                      if (entrada.key.isNotEmpty)
                        Padding(
                          padding: const EdgeInsets.fromLTRB(16, 12, 16, 2),
                          child: Text(entrada.key,
                              style: const TextStyle(
                                  fontWeight: FontWeight.w800, fontSize: 15)),
                        ),
                      for (final p in entrada.value)
                        ListTile(
                          title: Text(entrada.key.isEmpty
                              ? p.nombre
                              : (p.frecuenciaLabel.isEmpty
                                  ? p.nombre
                                  : p.frecuenciaLabel)),
                          subtitle: Text(p.tipo == TipoPlan.porClase
                              ? 'Por clase · $mon ${p.precioMes.toStringAsFixed(2)}'
                              : '${p.meses} ${p.meses == 1 ? 'mes' : 'meses'} · Total $mon ${p.total.toStringAsFixed(2)}'),
                          onTap: () => Navigator.pop(context, p),
                        ),
                    ],
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
    if (plan == null) return;
    if (plan.tipo == TipoPlan.porClase) {
      appState.agregarClaseSuelta(al, plan.precioMes, concepto: plan.nombre);
      return;
    }
    if (!context.mounted) return;
    final meses = await _pedirMeses(context, plan);
    if (meses == null) return;
    appState.inscribir(al, plan, duracionMeses: meses);
  }

  /// Pregunta por CUÁNTOS MESES inscribir (default 1). Genera esa cantidad de
  /// cuotas mensuales. Devuelve null si se cancela.
  Future<int?> _pedirMeses(BuildContext context, Plan plan) async {
    var meses = 1;
    return showDialog<int>(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setSt) {
          return DialogoPichangol(
            titulo: '¿Por cuántos meses?',
            icono: Icons.event_repeat,
            contenido: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(plan.nombre,
                    textAlign: TextAlign.center,
                    style: const TextStyle(color: textoTenue)),
                const SizedBox(height: 14),
                Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    IconButton.filledTonal(
                      onPressed:
                          meses > 1 ? () => setSt(() => meses--) : null,
                      icon: const Icon(Icons.remove),
                    ),
                    Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 22),
                      child: Text('$meses',
                          style: const TextStyle(
                              fontSize: 24, fontWeight: FontWeight.w800)),
                    ),
                    IconButton.filledTonal(
                      onPressed: () => setSt(() => meses++),
                      icon: const Icon(Icons.add),
                    ),
                  ],
                ),
                const SizedBox(height: 10),
                Text(
                    meses == 1
                        ? 'Genera 1 cuota mensual'
                        : 'Genera $meses cuotas mensuales',
                    style: const TextStyle(color: textoTenue, fontSize: 12.5)),
              ],
            ),
            acciones: [
              TextButton(
                  onPressed: () => Navigator.pop(ctx),
                  style: TextButton.styleFrom(foregroundColor: textoTenue),
                  child: const Text('Cancelar')),
              FilledButton(
                style: FilledButton.styleFrom(
                    backgroundColor: lima,
                    foregroundColor: Colors.white,
                    shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(12)),
                    padding: const EdgeInsets.symmetric(
                        horizontal: 20, vertical: 12)),
                onPressed: () => Navigator.pop(ctx, meses),
                child: const Text('Inscribir',
                    style: TextStyle(fontWeight: FontWeight.w800)),
              ),
            ],
          );
        },
      ),
    );
  }

  Future<void> _claseSuelta(BuildContext context, Alumno al) async {
    final mon = appState.miAcademia?.monedaSimbolo ?? monedaSimbolo;
    final monto = TextEditingController();
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => DialogoPichangol(
        titulo: 'Clase suelta',
        icono: Icons.sports_tennis,
        contenido: TextField(
          controller: monto,
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          decoration: InputDecoration(labelText: 'Monto', prefixText: '$mon '),
        ),
        acciones: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              style: TextButton.styleFrom(foregroundColor: textoTenue),
              child: const Text('Cancelar')),
          FilledButton(
              style: FilledButton.styleFrom(
                  backgroundColor: lima,
                  foregroundColor: Colors.white,
                  shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(12)),
                  padding:
                      const EdgeInsets.symmetric(horizontal: 20, vertical: 12)),
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('Registrar',
                  style: TextStyle(fontWeight: FontWeight.w800))),
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
                  icon: const Icon(Icons.chat, size: 18, color: lima),
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

/// Indicador (para el PROFE) de que el alumno paga MES A MES: modalidad, monto
/// mensual y próximo cobro automático. Vacío si el alumno no tiene débito
/// mensual activo (pago al contado / adelantado).
class _SuscripcionAlumnoInfoProfe extends StatefulWidget {
  const _SuscripcionAlumnoInfoProfe(
      {required this.alumnoId, required this.moneda});
  final String alumnoId;
  final String moneda;
  @override
  State<_SuscripcionAlumnoInfoProfe> createState() =>
      _SuscripcionAlumnoInfoProfeState();
}

class _SuscripcionAlumnoInfoProfeState
    extends State<_SuscripcionAlumnoInfoProfe> {
  static const _meses = [
    'ene', 'feb', 'mar', 'abr', 'may', 'jun',
    'jul', 'ago', 'set', 'oct', 'nov', 'dic'
  ];
  Map<String, dynamic>? _sus;
  bool _cargando = true;

  @override
  void initState() {
    super.initState();
    _cargar();
  }

  Future<void> _cargar() async {
    // Reconcilia (marca pagadas las cuotas ya cobradas por el cron) + trae estado.
    final s = await appState.reconciliarSuscripcionAlumno(widget.alumnoId);
    if (!mounted) return;
    setState(() {
      _sus = s;
      _cargando = false;
    });
  }

  String? _fecha(String? iso) {
    if (iso == null || iso.isEmpty) return null;
    final d = DateTime.tryParse(iso);
    if (d == null) return null;
    return '${d.day} ${_meses[d.month - 1]} ${d.year}';
  }

  @override
  Widget build(BuildContext context) {
    if (_cargando) return const SizedBox.shrink();
    final s = _sus;
    if (s == null || s['activa'] != true) return const SizedBox.shrink();
    final monto = (s['monto_soles'] as num?)?.toDouble() ?? 0;
    final prox = _fecha(s['proximo_cobro']?.toString());
    return Container(
      margin: const EdgeInsets.only(top: 12),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: limaSuave,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Row(
        children: [
          const Icon(Icons.autorenew, color: lima, size: 20),
          const SizedBox(width: 8),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text('Paga mes a mes (débito automático)',
                    style: TextStyle(
                        color: bosque,
                        fontWeight: FontWeight.w800,
                        fontSize: 13)),
                Text(
                    '${widget.moneda} ${monto.toStringAsFixed(2)}/mes'
                    '${prox != null ? ' · próximo cobro: $prox' : ''}',
                    style: const TextStyle(color: textoTenue, fontSize: 12.5)),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// Agrupa planes por PROGRAMA preservando el orden de aparición y ordenando cada
/// grupo por frecuencia (mismo criterio que `Academia.planesPorPrograma`). Se usa
/// en el selector "Elige el plan" del profe.
Map<String, List<Plan>> _agruparPorPrograma(List<Plan> planes) {
  final m = <String, List<Plan>>{};
  for (final p in planes) {
    (m[p.programa] ??= []).add(p);
  }
  for (final lista in m.values) {
    lista.sort((a, b) => a.frecuenciaSemana.compareTo(b.frecuenciaSemana));
  }
  return m;
}

/// Acceso al Community Manager AUTÓNOMO (Fase 0): el "post del día" listo (copy +
/// flyer de marca) para publicar en las redes del negocio en 1 toque.
class _CmPostDelDiaTile extends StatelessWidget {
  const _CmPostDelDiaTile({required this.academia});
  final Academia academia;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(14, 6, 14, 6),
      child: Container(
        decoration: BoxDecoration(
          color: Theme.of(context).colorScheme.surface,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: trazo),
        ),
        child: ListTile(
          leading: const CircleAvatar(
            backgroundColor: morado,
            child: Icon(Icons.auto_awesome, color: Colors.white),
          ),
          title: const Text('Community Manager · Post del día',
              style: TextStyle(fontWeight: FontWeight.w800)),
          subtitle: const Text(
              'Genera un post con flyer para tu Instagram/Facebook y publícalo '
              'en 1 toque',
              style: TextStyle(fontSize: 12.5)),
          trailing: const Icon(Icons.chevron_right),
          onTap: () => Navigator.of(context).push(MaterialPageRoute(
            builder: (_) => PostDelDiaScreen(
              academiaId: academia.id,
              titulo: academia.nombre,
              datos: {
                'nombre': academia.nombre,
                'deporte': academia.deporte.name,
                'descripcion': academia.descripcion,
                'whatsapp': academia.whatsapp,
                'fotos': academia.fotos,
                if (academia.logoUrl != null) 'logo_url': academia.logoUrl,
              },
            ),
          )),
        ),
      ),
    );
  }
}
