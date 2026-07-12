import 'package:flutter/material.dart';

import '../models/academia.dart';
import '../services/whatsapp_link.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../utils/redes.dart';
import '../utils/ubicacion_share.dart';
import '../widgets/pago_tarjeta_sheet.dart';

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
                                  t.bodyMedium?.copyWith(color: textoTenue)),
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
                const SizedBox(height: 12),
                if (academia.planes.isEmpty)
                  const Text('Esta academia aún no publicó sus planes.',
                      style: TextStyle(color: textoTenue))
                else
                  for (final p in academia.planes)
                    _TarjetaPlan(academia: academia, plan: p),
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
  const _TarjetaPlan({required this.academia, required this.plan});
  final Academia academia;
  final Plan plan;

  String get _detalle {
    if (plan.tipo == TipoPlan.porClase) {
      return 'Por clase · S/ ${plan.precioMes.toStringAsFixed(2)} c/u';
    }
    return '${plan.tipo.etiqueta} · ${plan.meses} '
        '${plan.meses == 1 ? 'mes' : 'meses'} · '
        'S/ ${plan.precioMes.toStringAsFixed(2)}/mes';
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
          Text(plan.nombre,
              style: TextStyle(
                  fontWeight: FontWeight.w800,
                  fontSize: 15,
                  color: Theme.of(context).colorScheme.onSurface)),
          const SizedBox(height: 4),
          Text(_detalle, style: const TextStyle(color: textoTenue, fontSize: 13)),
          const SizedBox(height: 12),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text('S/ ${plan.total.toStringAsFixed(2)}',
                  style: TextStyle(
                      color: Theme.of(context).colorScheme.primary,
                      fontWeight: FontWeight.w800,
                      fontSize: 18)),
              FilledButton(
                style: FilledButton.styleFrom(
                    backgroundColor: pino, foregroundColor: lima),
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
    // 1) Datos del alumno (prellena nombre del usuario logueado).
    final datos = await showModalBottomSheet<(String, String)>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Theme.of(context).colorScheme.surface,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      builder: (_) => _HojaDatosAlumno(
        nombreInicial: appState.usuario?.nombre ?? '',
        academia: academia.nombre,
        plan: plan.nombre,
      ),
    );
    if (datos == null) return;
    final (nombre, whatsapp) = datos;

    // 2) Pago del primer mes / de la clase con tarjeta (Culqi). Si Culqi no
    // está configurado, el sheet cae a la pasarela simulada (demo).
    if (!context.mounted) return;
    final pagado = await PagoTarjeta.cobrar(
      context,
      monto: plan.precioMes.round(),
      concepto: 'Matrícula ${academia.nombre} · ${plan.nombre}',
      email: appState.usuario?.email ?? '',
    );
    if (!pagado) return;

    // 3) Registra la matrícula (crea alumno + cuotas, primera pagada).
    appState.matricular(
      academiaId: academia.id,
      nombre: nombre,
      whatsapp: whatsapp,
      plan: plan,
    );

    if (!context.mounted) return;
    await showDialog<void>(
      context: context,
      builder: (_) => AlertDialog(
        icon: const Icon(Icons.check_circle, color: verde, size: 40),
        title: const Text('¡Matrícula lista!'),
        content: Text(
            'Ya estás inscrito en ${academia.nombre} (${plan.nombre}). '
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

/// Hoja para capturar nombre + WhatsApp del alumno antes de pagar.
class _HojaDatosAlumno extends StatefulWidget {
  const _HojaDatosAlumno({
    required this.nombreInicial,
    required this.academia,
    required this.plan,
  });
  final String nombreInicial;
  final String academia;
  final String plan;

  @override
  State<_HojaDatosAlumno> createState() => _HojaDatosAlumnoState();
}

class _HojaDatosAlumnoState extends State<_HojaDatosAlumno> {
  late final TextEditingController _nombre =
      TextEditingController(text: widget.nombreInicial);
  final _whatsapp = TextEditingController();

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
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Matricularme en ${widget.academia}',
              style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 17)),
          const SizedBox(height: 4),
          Text('Plan: ${widget.plan}',
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
            decoration: const InputDecoration(
                labelText: 'WhatsApp de contacto',
                prefixText: '+51 ',
                prefixIcon: Icon(Icons.chat_outlined)),
          ),
          const SizedBox(height: 20),
          SizedBox(
            width: double.infinity,
            child: FilledButton(
              style: FilledButton.styleFrom(
                  backgroundColor: pino,
                  foregroundColor: lima,
                  padding: const EdgeInsets.symmetric(vertical: 14)),
              onPressed: () {
                final n = _nombre.text.trim();
                final w = _whatsapp.text.replaceAll(RegExp(r'[^0-9]'), '');
                if (n.isEmpty || w.length < 9) {
                  ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
                      content: Text('Pon el nombre y un WhatsApp válido.')));
                  return;
                }
                Navigator.of(context).pop((n, _whatsapp.text.trim()));
              },
              child: const Text('Continuar al pago'),
            ),
          ),
        ],
      ),
    );
  }
}
