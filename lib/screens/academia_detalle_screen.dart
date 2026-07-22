import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../models/academia.dart';
import '../services/pagos_service.dart';
import '../services/whatsapp_link.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../utils/redes.dart';
import '../utils/ubicacion_share.dart';
import '../widgets/pago_tarjeta_sheet.dart';
import 'campeonatos_screen.dart';
import 'chat_screen.dart';
import '../utils/moneda.dart';
import '../config/pais.dart';

/// Ficha pública de una academia: feed de fotos propio (no Instagram embebido),
/// planes con matrícula en el mismo app (pago simulado) y redes para seguir.
class AcademiaDetalleScreen extends StatelessWidget {
  const AcademiaDetalleScreen({super.key, required this.academiaId});
  final String academiaId;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: ListenableBuilder(
        listenable: appState,
        builder: (context, _) {
          Academia? academia;
          for (final a in appState.academias) {
            if (a.id == academiaId) {
              academia = a;
              break;
            }
          }
          if (academia == null) {
            return const _NoExiste();
          }
          return _Contenido(academia: academia);
        },
      ),
    );
  }
}

class _NoExiste extends StatelessWidget {
  const _NoExiste();
  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(),
        body: const Center(
            child: Text('Esta academia ya no está disponible.',
                style: TextStyle(color: textoTenue))),
      );
}

class _Contenido extends StatelessWidget {
  const _Contenido({required this.academia});
  final Academia academia;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return CustomScrollView(
      slivers: [
        SliverAppBar(
          expandedHeight: academia.fotos.isEmpty ? 0 : 260,
          pinned: true,
          backgroundColor: bosque,
          foregroundColor: Colors.white,
          flexibleSpace: academia.fotos.isEmpty
              ? null
              : FlexibleSpaceBar(
                  background: _FeedPortada(fotos: academia.fotos),
                ),
        ),
        SliverToBoxAdapter(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(18, 18, 18, 28),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Encabezado: logo + nombre + deporte/sede.
                Row(
                  children: [
                    CircleAvatar(
                      radius: 30,
                      backgroundColor: colorDeporte(academia.deporte),
                      backgroundImage: (academia.logoUrl != null &&
                              academia.logoUrl!.isNotEmpty)
                          ? NetworkImage(academia.logoUrl!)
                          : null,
                      child: (academia.logoUrl != null &&
                              academia.logoUrl!.isNotEmpty)
                          ? null
                          : Icon(iconoDeporte(academia.deporte),
                              color: Colors.white, size: 28),
                    ),
                    const SizedBox(width: 14),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(academia.nombre,
                              style: t.titleLarge
                                  ?.copyWith(fontWeight: FontWeight.w800)),
                          Text(
                              '${academia.deporte.etiqueta}'
                              '${academia.sedeClub.isNotEmpty ? ' · ${academia.sedeClub}' : ''}',
                              style:
                                  t.bodyMedium?.copyWith(color: textoTenueDe(context))),
                        ],
                      ),
                    ),
                  ],
                ),
                if (academia.descripcion.isNotEmpty) ...[
                  const SizedBox(height: 14),
                  Text(academia.descripcion,
                      style: t.bodyMedium?.copyWith(
                          color: Theme.of(context).colorScheme.onSurface,
                          height: 1.4)),
                ],
                // Landing/publicidad (si la academia contrató el servicio).
                if (academia.tieneLanding) ...[
                  const SizedBox(height: 16),
                  SizedBox(
                    width: double.infinity,
                    child: FilledButton.icon(
                      style: FilledButton.styleFrom(
                          backgroundColor: lima,
                          foregroundColor: Colors.white,
                          padding: const EdgeInsets.symmetric(vertical: 13)),
                      icon: const Icon(Icons.public, size: 18),
                      label: const Text('Ver sitio web oficial'),
                      onPressed: () {
                        final raw = academia.landingUrl.trim();
                        final u = Uri.tryParse(
                            raw.startsWith('http') ? raw : 'https://$raw');
                        if (u != null) {
                          launchUrl(u, mode: LaunchMode.externalApplication);
                        }
                      },
                    ),
                  ),
                ],
                // Redes: "Síguenos" (secundario, con color de marca).
                if (academia.redes.isNotEmpty) ...[
                  const SizedBox(height: 18),
                  Text('Síguenos',
                      style:
                          t.titleSmall?.copyWith(fontWeight: FontWeight.w800)),
                  const SizedBox(height: 10),
                  Wrap(
                    children: [
                      for (final e in academia.redes.entries)
                        if (urlRed(e.key, e.value) != null)
                          RedBadge(clave: e.key, valor: e.value, size: 44),
                    ],
                  ),
                ],
                // Acciones principales: ubicación + contactar.
                const SizedBox(height: 20),
                Row(
                  children: [
                    if (academia.sedeUbicacion != null) ...[
                      Expanded(
                        child: OutlinedButton.icon(
                          style: OutlinedButton.styleFrom(
                            foregroundColor:
                                Theme.of(context).colorScheme.primary,
                            side: BorderSide(
                                color: Theme.of(context).colorScheme.primary,
                                width: 1.4),
                            padding: const EdgeInsets.symmetric(vertical: 12),
                            shape: RoundedRectangleBorder(
                                borderRadius: BorderRadius.circular(14)),
                          ),
                          onPressed: () => UbicacionShare.menu(context,
                              punto: academia.sedeUbicacion!,
                              titulo: academia.nombre),
                          icon: const Icon(Icons.share_location, size: 20),
                          label: const Text('Ubicación'),
                        ),
                      ),
                      const SizedBox(width: 10),
                    ],
                    Expanded(
                      child: OutlinedButton.icon(
                        style: OutlinedButton.styleFrom(
                          foregroundColor: verde,
                          side: const BorderSide(color: verde, width: 1.4),
                          padding: const EdgeInsets.symmetric(vertical: 12),
                          shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(14)),
                        ),
                        onPressed: academia.whatsapp.isEmpty
                            ? null
                            : () => WhatsAppLink.abrir(
                                academia.whatsapp,
                                'Hola, vi ${academia.nombre} en Pichangol y quiero info de las clases.'),
                        icon: const Icon(Icons.chat, size: 18),
                        label: const Text('Contactar'),
                      ),
                    ),
                  ],
                ),
                // Planes con matrícula.
                const SizedBox(height: 26),
                Text('Planes y matrícula',
                    style: t.titleMedium?.copyWith(fontWeight: FontWeight.w800)),
                const SizedBox(height: 4),
                const Text('Elige un plan y matricúlate aquí mismo.',
                    style: TextStyle(color: textoTenue, fontSize: 13)),
                if (academia.tieneDescuentos) ...[
                  const SizedBox(height: 10),
                  Container(
                    padding:
                        const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                    decoration: BoxDecoration(
                      color: limaSuave,
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Row(
                      children: [
                        const Icon(Icons.local_offer_outlined,
                            size: 18, color: lima),
                        const SizedBox(width: 8),
                        Expanded(
                          child: Text(_descuentosTexto(academia),
                              style: TextStyle(
                                  fontSize: 12.5,
                                  fontWeight: FontWeight.w600,
                                  color: Theme.of(context)
                                      .colorScheme
                                      .onSurface)),
                        ),
                      ],
                    ),
                  ),
                ],
                const SizedBox(height: 12),
                if (academia.planes.isEmpty)
                  const Text('Esta academia aún no publicó sus planes.',
                      style: TextStyle(color: textoTenue))
                else
                  // Planes AGRUPADOS por programa (Bola Roja/Naranja, Verde/
                  // Amarilla…): un encabezado por programa y debajo sus
                  // frecuencias. Los planes sin programa van sin encabezado.
                  for (final entrada in academia.planesPorPrograma.entries) ...[
                    if (entrada.key.isNotEmpty) ...[
                      const SizedBox(height: 6),
                      Text(entrada.key,
                          style: const TextStyle(
                              fontWeight: FontWeight.w800, fontSize: 16)),
                      if (entrada.value.first.etapaEdad.isNotEmpty)
                        Padding(
                          padding: const EdgeInsets.only(top: 2, bottom: 4),
                          child: Text(entrada.value.first.etapaEdad,
                              style: const TextStyle(
                                  color: textoTenue, fontSize: 12.5)),
                        ),
                      const SizedBox(height: 8),
                    ],
                    for (final p in entrada.value)
                      _TarjetaPlan(
                          academia: academia,
                          plan: p,
                          tituloOverride:
                              entrada.key.isEmpty ? null : p.frecuenciaLabel),
                  ],
                // Chat con el profe (solo si el usuario está matriculado aquí).
                Builder(builder: (context) {
                  final email = appState.usuario?.email;
                  if (email == null || email.isEmpty) {
                    return const SizedBox.shrink();
                  }
                  final matriculado = appState.alumnos.any((al) =>
                      al.academiaId == academia.id &&
                      al.email.toLowerCase() == email.toLowerCase());
                  if (!matriculado) return const SizedBox.shrink();
                  final cs = Theme.of(context).colorScheme;
                  return Padding(
                    padding: const EdgeInsets.only(top: 22),
                    child: Material(
                      color: cs.surface,
                      borderRadius: BorderRadius.circular(16),
                      child: InkWell(
                        borderRadius: BorderRadius.circular(16),
                        onTap: () => Navigator.of(context).push(
                            MaterialPageRoute(
                                builder: (_) => ChatScreen(
                                      academiaId: academia.id,
                                      cuentaEmail: email,
                                      titulo: academia.nombre,
                                      soyProfe: false,
                                    ))),
                        child: Container(
                          padding: const EdgeInsets.all(14),
                          decoration: BoxDecoration(
                              borderRadius: BorderRadius.circular(16),
                              border: Border.all(color: trazo)),
                          child: Row(
                            children: [
                              Icon(Icons.forum_outlined, color: cs.primary),
                              const SizedBox(width: 12),
                              const Expanded(
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Text('Chatear con el profe',
                                        style: TextStyle(
                                            fontWeight: FontWeight.w800)),
                                    Text('Dudas de horarios, pagos y clases',
                                        style: TextStyle(
                                            color: textoTenue, fontSize: 12)),
                                  ],
                                ),
                              ),
                              Icon(Icons.chevron_right, color: cs.primary),
                            ],
                          ),
                        ),
                      ),
                    ),
                  );
                }),
                // Acceso a los campeonatos de la academia (llaves/tabla).
                const SizedBox(height: 22),
                Builder(builder: (context) {
                  final n = appState.campeonatosDe(academia.id).length;
                  final cs = Theme.of(context).colorScheme;
                  return Material(
                    color: cs.surface,
                    borderRadius: BorderRadius.circular(16),
                    child: InkWell(
                      borderRadius: BorderRadius.circular(16),
                      onTap: () => Navigator.of(context).push(
                          MaterialPageRoute(
                              builder: (_) => CampeonatosScreen(
                                  academiaId: academia.id))),
                      child: Container(
                        padding: const EdgeInsets.all(14),
                        decoration: BoxDecoration(
                            borderRadius: BorderRadius.circular(16),
                            border: Border.all(color: trazo)),
                        child: Row(
                          children: [
                            Icon(Icons.emoji_events, color: cs.primary),
                            const SizedBox(width: 12),
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  const Text('Campeonatos',
                                      style: TextStyle(
                                          fontWeight: FontWeight.w800)),
                                  Text(
                                      n == 0
                                          ? 'Aún sin campeonatos'
                                          : '$n campeonato${n == 1 ? '' : 's'} · llaves y tabla',
                                      style: const TextStyle(
                                          color: textoTenue, fontSize: 12)),
                                ],
                              ),
                            ),
                            Icon(Icons.chevron_right, color: cs.primary),
                          ],
                        ),
                      ),
                    ),
                  );
                }),
                // Galería completa del feed.
                if (academia.fotos.length > 1) ...[
                  const SizedBox(height: 26),
                  Text('Fotos',
                      style:
                          t.titleMedium?.copyWith(fontWeight: FontWeight.w800)),
                  const SizedBox(height: 12),
                  _Galeria(fotos: academia.fotos),
                ],
              ],
            ),
          ),
        ),
      ],
    );
  }
}

/// Carrusel de portada (fotos del feed) para el SliverAppBar.
class _FeedPortada extends StatefulWidget {
  const _FeedPortada({required this.fotos});
  final List<String> fotos;
  @override
  State<_FeedPortada> createState() => _FeedPortadaState();
}

class _FeedPortadaState extends State<_FeedPortada> {
  final _ctrl = PageController();
  int _i = 0;

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Stack(
      fit: StackFit.expand,
      children: [
        PageView.builder(
          controller: _ctrl,
          itemCount: widget.fotos.length,
          onPageChanged: (i) => setState(() => _i = i),
          itemBuilder: (_, i) => Image.network(widget.fotos[i],
              fit: BoxFit.cover,
              errorBuilder: (_, __, ___) => Container(color: limaSuave)),
        ),
        if (widget.fotos.length > 1)
          Positioned(
            bottom: 12,
            left: 0,
            right: 0,
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                for (var i = 0; i < widget.fotos.length; i++)
                  Container(
                    width: 7,
                    height: 7,
                    margin: const EdgeInsets.symmetric(horizontal: 3),
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      color: i == _i ? Colors.white : Colors.white54,
                    ),
                  ),
              ],
            ),
          ),
      ],
    );
  }
}

/// Cuadrícula de fotos del feed.
class _Galeria extends StatelessWidget {
  const _Galeria({required this.fotos});
  final List<String> fotos;
  @override
  Widget build(BuildContext context) {
    return GridView.builder(
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
        crossAxisCount: 3,
        crossAxisSpacing: 6,
        mainAxisSpacing: 6,
      ),
      itemCount: fotos.length,
      itemBuilder: (_, i) => ClipRRect(
        borderRadius: BorderRadius.circular(10),
        child: Image.network(fotos[i],
            fit: BoxFit.cover,
            errorBuilder: (_, __, ___) => Container(color: limaSuave)),
      ),
    );
  }
}

/// Tarjeta de un plan con su botón "Matricularme".
class _TarjetaPlan extends StatelessWidget {
  const _TarjetaPlan(
      {required this.academia, required this.plan, this.tituloOverride});
  final Academia academia;
  final Plan plan;
  // Título compacto cuando la tarjeta ya va bajo un encabezado de programa
  // (ej. "4x/sem"); si es null usa el nombre completo del plan.
  final String? tituloOverride;

  String get _detalle {
    if (plan.tipo == TipoPlan.porClase) {
      return 'Por clase · ${academia.monedaSimbolo} ${plan.precioMes.toStringAsFixed(2)} c/u';
    }
    return '${plan.tipo.etiqueta} · ${plan.meses} '
        '${plan.meses == 1 ? 'mes' : 'meses'} · '
        '${academia.monedaSimbolo} ${plan.precioMes.toStringAsFixed(2)}/mes';
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: trazo),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(tituloOverride ?? plan.nombre,
              style: TextStyle(
                  fontWeight: FontWeight.w800,
                  fontSize: 15,
                  color: Theme.of(context).colorScheme.onSurface)),
          const SizedBox(height: 4),
          Text(_detalle, style: const TextStyle(color: textoTenue, fontSize: 13)),
          if (academia.tieneTarifaInvitado &&
              plan.tipo != TipoPlan.porClase) ...[
            const SizedBox(height: 4),
            Text(
              'Socio ${academia.monedaSimbolo} ${plan.precioMes.toStringAsFixed(0)}'
              ' · Invitado ${academia.monedaSimbolo} '
              '${academia.precioDePlan(plan, socio: false).toStringAsFixed(0)}',
              style: TextStyle(
                  color: Theme.of(context).colorScheme.primary,
                  fontSize: 12.5,
                  fontWeight: FontWeight.w700),
            ),
          ],
          const SizedBox(height: 12),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text('${academia.monedaSimbolo} ${plan.total.toStringAsFixed(2)}',
                  style: TextStyle(
                      color: Theme.of(context).colorScheme.primary,
                      fontWeight: FontWeight.w800,
                      fontSize: 18)),
              FilledButton(
                style: FilledButton.styleFrom(
                    backgroundColor: lima, foregroundColor: Colors.white),
                onPressed: () => _matricular(context),
                child: const Text('Matricularme'),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Future<void> _matricular(BuildContext context) async {
    // 1) Datos del alumno + MODO (mes a mes / adelantado) + cantidad + total.
    final datos =
        await showModalBottomSheet<(String, String, int, bool, double)>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Theme.of(context).colorScheme.surface,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      builder: (_) => _HojaDatosAlumno(
        nombreInicial: appState.usuario?.nombre ?? '',
        academia: academia.nombre,
        planObj: plan,
        moneda: academia.monedaSimbolo,
        esMensual: plan.tipo == TipoPlan.mensual,
        descuentoPrepago: academia.descuentoPrepago,
        mesesMinPrepago: academia.mesesMinPrepago,
      ),
    );
    if (datos == null) return;
    final (nombre, whatsapp, cantidad, mesAMes, totalAhora) = datos;
    final monto = totalAhora.round();

    // 2) Pago del total a cobrar AHORA (mes a mes = 1 mes; adelantado = N meses
    // con descuento si aplica). Capturamos el token para el débito automático.
    if (!context.mounted) return;
    String? tokenUsado;
    final pagado = await PagoTarjeta.cobrar(
      context,
      monto: monto,
      concepto: 'Matrícula ${academia.nombre} · ${plan.nombre}',
      email: appState.usuario?.email ?? '',
      moneda: academia.monedaSimbolo,
      onToken: (t) => tokenUsado = t,
    );
    if (!pagado) return;

    // 2b) Registra el COBRO DIGITAL en el backend: congela la comisión "tipo POS"
    // del país y deja el neto como "por recibir" de la academia (best-effort; no
    // bloquea la matrícula si falla la red).
    PagosService.registrarMatricula(
      academiaId: academia.id,
      montoSoles: monto.toDouble(),
      matriculaId: 'mat_${academia.id}_${DateTime.now().microsecondsSinceEpoch}',
      pais: academia.pais.iso,
      concepto: 'Matrícula ${academia.nombre} · ${plan.nombre}',
    );

    // 3) Registra la matrícula. Mes a mes: crea las N cuotas del compromiso con
    // solo la 1.ª pagada (las demás quedan pendientes con su fecha). Adelantado:
    // todas pagadas.
    final alumno = appState.matricular(
      academiaId: academia.id,
      nombre: nombre,
      whatsapp: whatsapp,
      plan: plan,
      cantidad: cantidad,
      mesesPagados: mesAMes ? 1 : null,
      autoDebito: mesAMes,
    );

    // 3b) Mes a mes: activa el débito automático de los meses restantes con la
    // tarjeta usada. cobrosRestantes = meses comprometidos − el 1.º ya pagado.
    if (mesAMes && tokenUsado != null) {
      PagosService.crearSuscripcionAlumno(
        alumnoId: alumno.id,
        academiaId: academia.id,
        email: appState.usuario?.email ?? '',
        token: tokenUsado!,
        montoSoles: plan.total,
        nombre: nombre,
        pais: academia.pais.iso,
        concepto: 'Mensualidad ${academia.nombre} · ${plan.nombre}',
        cobrosRestantes: cantidad - 1,
      );
    }

    if (!context.mounted) return;
    await showDialog<void>(
      context: context,
      builder: (_) => AlertDialog(
        icon: const Icon(Icons.check_circle, color: verde, size: 40),
        title: const Text('¡Matrícula lista!'),
        content: Text(mesAMes
            ? 'Ya estás inscrito en ${academia.nombre} (${plan.nombre}). '
                'Se debitará ${academia.monedaSimbolo} ${plan.total.toStringAsFixed(2)} '
                'automático cada mes; puedes cancelar cuando quieras.'
            : 'Ya estás inscrito en ${academia.nombre} (${plan.nombre}). '
                'Te contactarán por WhatsApp para coordinar tus horarios.'),
        actions: [
          if (academia.whatsapp.isNotEmpty)
            TextButton.icon(
              onPressed: () {
                WhatsAppLink.abrir(academia.whatsapp,
                    'Hola, acabo de matricularme en ${academia.nombre} (${plan.nombre}) por Pichangol. Soy $nombre.');
                Navigator.of(context).pop();
              },
              icon: const Icon(Icons.chat, color: verde),
              label: const Text('Avisar al profe'),
            ),
          FilledButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('Listo'),
          ),
        ],
      ),
    );
  }
}

/// Hoja para capturar nombre + WhatsApp del alumno y la CANTIDAD (clases/meses/
/// paquetes) antes de pagar.
class _HojaDatosAlumno extends StatefulWidget {
  const _HojaDatosAlumno({
    required this.nombreInicial,
    required this.academia,
    required this.planObj,
    required this.moneda,
    this.esMensual = false,
    this.descuentoPrepago = 0,
    this.mesesMinPrepago = 3,
  });
  final String nombreInicial;
  final String academia;
  final Plan planObj;
  final String moneda;
  final bool esMensual; // ¿el plan es mensual? (habilita "mes a mes")
  final double descuentoPrepago; // % de descuento por pago adelantado
  final int mesesMinPrepago; // desde cuántos meses aplica el descuento

  @override
  State<_HojaDatosAlumno> createState() => _HojaDatosAlumnoState();
}

class _HojaDatosAlumnoState extends State<_HojaDatosAlumno> {
  late final TextEditingController _nombre =
      TextEditingController(text: widget.nombreInicial);
  final _whatsapp = TextEditingController();
  int _cantidad = 1;
  bool _mesAMes = false; // solo aplica a planes mensuales
  String? _error; // mensaje de validación inline (visible)

  Plan get _plan => widget.planObj;

  String get _labelCantidad => switch (_plan.tipo) {
        TipoPlan.porClase => '¿Cuántas clases pagarás?',
        TipoPlan.mensual => _mesAMes
            ? '¿Por cuántos meses te comprometes?'
            : '¿Cuántos meses adelantas?',
        TipoPlan.prepago => '¿Cuántos paquetes de ${_plan.meses} meses?',
      };

  String get _unidad => switch (_plan.tipo) {
        TipoPlan.porClase => _cantidad == 1 ? 'clase' : 'clases',
        TipoPlan.mensual => _cantidad == 1 ? 'mes' : 'meses',
        TipoPlan.prepago => _cantidad == 1 ? 'paquete' : 'paquetes',
      };

  // ¿Aplica el descuento de prepago? (solo modo adelantado, con % y umbral).
  bool get _aplicaDescuento =>
      !_mesAMes &&
      widget.descuentoPrepago > 0 &&
      _cantidad >= widget.mesesMinPrepago;

  double get _totalSinDto => _plan.total * _cantidad;
  double get _ahorro =>
      _aplicaDescuento ? _totalSinDto * widget.descuentoPrepago / 100 : 0;
  // Lo que se cobra AHORA: mes a mes = 1 mes; adelantado = total − descuento.
  double get _total => _mesAMes ? _plan.total : (_totalSinDto - _ahorro);

  @override
  void dispose() {
    _nombre.dispose();
    _whatsapp.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.fromLTRB(
          20, 18, 20, 20 + MediaQuery.of(context).viewInsets.bottom),
      child: SingleChildScrollView(
        child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Matricularme en ${widget.academia}',
              style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 17)),
          const SizedBox(height: 4),
          Text('Plan: ${_plan.nombre}',
              style: const TextStyle(color: textoTenue, fontSize: 13)),
          const SizedBox(height: 16),
          TextField(
            controller: _nombre,
            decoration: const InputDecoration(
                labelText: 'Nombre del alumno',
                prefixIcon: Icon(Icons.person_outline)),
          ),
          const SizedBox(height: 14),
          TextField(
            controller: _whatsapp,
            keyboardType: TextInputType.phone,
            decoration: InputDecoration(
                labelText: 'WhatsApp de contacto',
                prefixText: '$codigoTelActual ',
                prefixIcon: Icon(Icons.chat_outlined)),
          ),
          const SizedBox(height: 18),
          // Modo de pago (solo planes mensuales): mes a mes vs adelantado.
          if (widget.esMensual) ...[
            Row(
              children: [
                Expanded(
                  child: _ChipModo(
                    titulo: 'Mes a mes',
                    subtitulo: 'Débito automático',
                    activo: _mesAMes,
                    onTap: () => setState(() => _mesAMes = true),
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: _ChipModo(
                    titulo: 'Adelantado',
                    subtitulo: widget.descuentoPrepago > 0
                        ? 'Ahorra desde ${widget.mesesMinPrepago} meses'
                        : 'Paga varios meses',
                    activo: !_mesAMes,
                    onTap: () => setState(() => _mesAMes = false),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 16),
          ],
          Text(_labelCantidad,
              style: const TextStyle(fontWeight: FontWeight.w700)),
          const SizedBox(height: 8),
          Row(
            children: [
              _StepBtn(
                  icon: Icons.remove,
                  onTap:
                      _cantidad > 1 ? () => setState(() => _cantidad--) : null),
              Expanded(
                child: Text('$_cantidad $_unidad',
                    textAlign: TextAlign.center,
                    style: const TextStyle(
                        fontWeight: FontWeight.w800, fontSize: 16)),
              ),
              _StepBtn(
                  icon: Icons.add,
                  onTap: _cantidad < 36
                      ? () => setState(() => _cantidad++)
                      : null),
            ],
          ),
          const SizedBox(height: 14),
          Container(
            width: double.infinity,
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
            decoration: BoxDecoration(
                color: limaSuave, borderRadius: BorderRadius.circular(12)),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                    _mesAMes
                        ? 'Pagas hoy 1 mes: ${widget.moneda} ${_plan.total.toStringAsFixed(2)}'
                        : 'Pagarás ahora: ${widget.moneda} ${_total.toStringAsFixed(2)}',
                    style: const TextStyle(
                        color: bosque,
                        fontWeight: FontWeight.w800,
                        fontSize: 15)),
                if (_mesAMes) ...[
                  const SizedBox(height: 2),
                  Text(
                      'Luego ${widget.moneda} ${_plan.total.toStringAsFixed(2)} '
                      'automático por ${_cantidad - 1} '
                      '${_cantidad - 1 == 1 ? 'mes más' : 'meses más'}.',
                      style: const TextStyle(
                          color: bosque,
                          fontWeight: FontWeight.w700,
                          fontSize: 12.5)),
                ],
                if (_aplicaDescuento) ...[
                  const SizedBox(height: 4),
                  Text(
                      'Descuento ${widget.descuentoPrepago.toStringAsFixed(0)}% '
                      'por adelantar · ahorras ${widget.moneda} ${_ahorro.toStringAsFixed(2)}',
                      style: const TextStyle(
                          color: lima,
                          fontWeight: FontWeight.w700,
                          fontSize: 12.5)),
                ] else if (!_mesAMes &&
                    widget.descuentoPrepago > 0 &&
                    _cantidad < widget.mesesMinPrepago) ...[
                  const SizedBox(height: 4),
                  Text(
                      'Paga ${widget.mesesMinPrepago}+ meses y ahorra '
                      '${widget.descuentoPrepago.toStringAsFixed(0)}%.',
                      style: const TextStyle(
                          color: textoTenue, fontSize: 12.5)),
                ],
                if (_mesAMes) ...[
                  const SizedBox(height: 4),
                  const Text('Se cobra automático de tu tarjeta. Cancela cuando quieras.',
                      style: TextStyle(color: textoTenue, fontSize: 12.5)),
                ],
              ],
            ),
          ),
          if (_error != null) ...[
            const SizedBox(height: 10),
            Row(
              children: [
                const Icon(Icons.error_outline, size: 18, color: clayOscuro),
                const SizedBox(width: 6),
                Expanded(
                  child: Text(_error!,
                      style: const TextStyle(
                          color: clayOscuro,
                          fontSize: 13,
                          fontWeight: FontWeight.w600)),
                ),
              ],
            ),
          ],
          const SizedBox(height: 16),
          SizedBox(
            width: double.infinity,
            child: FilledButton(
              style: FilledButton.styleFrom(
                  backgroundColor: lima,
                  foregroundColor: Colors.white,
                  padding: const EdgeInsets.symmetric(vertical: 14)),
              onPressed: () {
                final n = _nombre.text.trim();
                final w = _whatsapp.text.replaceAll(RegExp(r'[^0-9]'), '');
                if (n.isEmpty) {
                  setState(() => _error = 'Escribe el nombre del alumno.');
                  return;
                }
                if (w.length < 9) {
                  setState(() =>
                      _error = 'Pon un WhatsApp de contacto válido (9 dígitos).');
                  return;
                }
                setState(() => _error = null);
                Navigator.of(context).pop((
                  n,
                  _whatsapp.text.trim(),
                  _cantidad, // meses comprometidos (mes a mes) o adelantados
                  _mesAMes,
                  _total,
                ));
              },
              child: Text(_mesAMes
                  ? 'Pagar 1.er mes ${widget.moneda} ${_total.toStringAsFixed(2)}'
                  : 'Pagar ${widget.moneda} ${_total.toStringAsFixed(2)}'),
            ),
          ),
        ],
        ),
      ),
    );
  }
}

/// Chip de selección de MODO de pago (mes a mes / adelantado). Estilo Airbnb:
/// blanco con borde suave; seleccionado = tinte lima, sin borde negro.
class _ChipModo extends StatelessWidget {
  const _ChipModo({
    required this.titulo,
    required this.subtitulo,
    required this.activo,
    required this.onTap,
  });
  final String titulo;
  final String subtitulo;
  final bool activo;
  final VoidCallback onTap;
  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Material(
      color: activo ? limaSuave : cs.surface,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(14),
        side: BorderSide(color: activo ? lima : trazo, width: activo ? 1.5 : 1),
      ),
      child: InkWell(
        borderRadius: BorderRadius.circular(14),
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 12),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Icon(activo ? Icons.check_circle : Icons.circle_outlined,
                      size: 18, color: activo ? lima : textoTenue),
                  const SizedBox(width: 6),
                  Text(titulo,
                      style: TextStyle(
                          fontWeight: FontWeight.w800,
                          fontSize: 14,
                          color: activo ? bosque : textoTenue)),
                ],
              ),
              const SizedBox(height: 3),
              Text(subtitulo,
                  style: const TextStyle(color: textoTenue, fontSize: 11.5)),
            ],
          ),
        ),
      ),
    );
  }
}

/// Botón +/- para el selector de cantidad.
class _StepBtn extends StatelessWidget {
  const _StepBtn({required this.icon, required this.onTap});
  final IconData icon;
  final VoidCallback? onTap;
  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final activo = onTap != null;
    return Material(
      color: activo ? limaSuave : cs.surface,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: BorderSide(color: trazo),
      ),
      child: InkWell(
        borderRadius: BorderRadius.circular(12),
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(10),
          child: Icon(icon,
              color: activo ? lima : textoTenue, size: 22),
        ),
      ),
    );
  }
}

/// Resumen legible de los descuentos configurados de una academia (para la
/// ficha pública). Solo lista los que están activos (> 0).
String _descuentosTexto(Academia ac) {
  final partes = <String>[];
  if (ac.descuentoHermano2 > 0) {
    partes.add('2º hermano −${ac.descuentoHermano2.toStringAsFixed(0)}%');
  }
  if (ac.descuentoHermano3 > 0) {
    partes.add('3º+ −${ac.descuentoHermano3.toStringAsFixed(0)}%');
  }
  if (ac.descuentoPrepago > 0) {
    partes.add('prepago −${ac.descuentoPrepago.toStringAsFixed(0)}%');
  }
  return 'Descuentos: ${partes.join(' · ')}';
}
