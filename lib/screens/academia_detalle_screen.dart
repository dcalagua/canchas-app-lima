import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:url_launcher/url_launcher.dart';

import '../models/academia.dart';
import '../services/pagos_service.dart';
import '../services/whatsapp_link.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/dialogo_pichangol.dart';
import '../utils/redes.dart';
import '../widgets/ancho_lectura.dart';
import '../widgets/chat_burbuja.dart';
import '../utils/ubicacion_share.dart';
import '../widgets/logo_academia.dart';
import '../widgets/pago_tarjeta_sheet.dart';
import 'campeonatos_screen.dart';
import 'ranking_academia_screen.dart';
import 'chat_screen.dart';
import 'login_google_sheet.dart';
import 'mis_clases_screen.dart';
import '../utils/moneda.dart';
import '../config/pais.dart';

/// Ficha pública de una academia: feed de fotos propio (no Instagram embebido),
/// planes con matrícula en el mismo app (pago simulado) y redes para seguir.
class AcademiaDetalleScreen extends StatelessWidget {
  const AcademiaDetalleScreen({super.key, required this.academiaId});
  final String academiaId;

  @override
  Widget build(BuildContext context) {
    // _Contenido y _NoExiste traen su propio Scaffold (así el globo de chat
    // flotante vive con la academia ya resuelta).
    return ListenableBuilder(
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

  /// Etiqueta del chip de campeonatos (con conteo si hay).
  String _campeonatosLabel() {
    final n = appState.campeonatosDe(academia.id).length;
    return n == 0 ? 'Campeonatos' : 'Campeonatos ($n)';
  }

  /// Abre el CHAT INTERNO con el profe (lo preferido: deja historial, notifica
  /// al profe, retención). Exige cuenta; si no hay sesión, pide login con el
  /// portón único. Disponible para cualquiera (interesado o ya matriculado).
  Future<void> _abrirChatProfe(BuildContext context) async {
    if (!await LoginGoogleSheet.mostrar(context,
        motivo: 'escribirle al profe')) {
      return;
    }
    if (!context.mounted) return;
    final email = appState.usuario!.email;
    Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => ChatScreen(
        academiaId: academia.id,
        cuentaEmail: email,
        titulo: academia.nombre,
        soyProfe: false,
      ),
    ));
  }

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return Scaffold(
      // Globo de chat SIEMPRE a la mano (no se pierde al hacer scroll): escribirle
      // al profe por el chat interno. Es nuestra "burbuja" (identidad Pichangol).
      floatingActionButton: ChatBurbuja(
        logoUrl: academia.logoUrl,
        onTap: () => _abrirChatProfe(context),
      ),
      body: CustomScrollView(
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
          child: AnchoLectura(
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
                // Acciones. El chat con el profe ya vive en el GLOBO flotante
                // (siempre a la mano), así que aquí no repetimos el botón.
                const SizedBox(height: 20),
                // Modo 'whatsapp_libre' (torre de control): WhatsApp también como
                // botón visible (co-primario), no solo chip.
                if (academia.whatsapp.isNotEmpty &&
                    appState.mostrarWhatsapp &&
                    appState.whatsappLibre) ...[
                  SizedBox(
                    width: double.infinity,
                    child: OutlinedButton.icon(
                      style: OutlinedButton.styleFrom(
                          foregroundColor: const Color(0xFF25D366),
                          side: const BorderSide(
                              color: Color(0xFF25D366), width: 1.4),
                          padding: const EdgeInsets.symmetric(vertical: 13),
                          shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(14))),
                      icon: const Icon(FontAwesomeIcons.whatsapp, size: 18),
                      label: const Text('Contactar por WhatsApp',
                          style: TextStyle(fontWeight: FontWeight.w800)),
                      onPressed: () => WhatsAppLink.abrir(academia.whatsapp,
                          'Hola, vi ${academia.nombre} en Pichangol y quiero info de las clases.'),
                    ),
                  ),
                ],
                const SizedBox(height: 10),
                // Accesos rápidos a la MISMA altura (nada escondido abajo):
                // ubicación · WhatsApp (respaldo) · campeonatos. El chip de
                // WhatsApp se OCULTA en 'solo_pcg' y no se duplica en
                // 'whatsapp_libre' (allí ya está como botón arriba).
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    if (academia.sedeUbicacion != null)
                      _ChipAccion(
                        icon: Icons.share_location,
                        label: 'Ubicación',
                        onTap: () => UbicacionShare.menu(context,
                            punto: academia.sedeUbicacion!,
                            titulo: academia.nombre),
                      ),
                    if (academia.whatsapp.isNotEmpty &&
                        appState.mostrarWhatsapp &&
                        !appState.whatsappLibre)
                      _ChipAccion(
                        icon: FontAwesomeIcons.whatsapp,
                        label: 'WhatsApp',
                        color: const Color(0xFF25D366), // verde WhatsApp oficial
                        onTap: () => WhatsAppLink.abrir(academia.whatsapp,
                            'Hola, vi ${academia.nombre} en Pichangol y quiero info de las clases.'),
                      ),
                    _ChipAccion(
                      icon: Icons.emoji_events,
                      label: _campeonatosLabel(),
                      onTap: () => Navigator.of(context).push(MaterialPageRoute(
                          builder: (_) =>
                              CampeonatosScreen(academiaId: academia.id))),
                    ),
                    _ChipAccion(
                      icon: Icons.leaderboard,
                      label: 'Ranking',
                      onTap: () => Navigator.of(context).push(MaterialPageRoute(
                          builder: (_) => RankingAcademiaScreen(
                                academiaId: academia.id,
                                esDueno:
                                    (appState.usuario?.email ?? '')
                                            .toLowerCase()
                                            .trim() ==
                                        academia.dueno.toLowerCase().trim(),
                              ))),
                    ),
                  ],
                ),
                // Sedes y horarios (solo academias multi-sede).
                if (academia.sedes.isNotEmpty) ...[
                  const SizedBox(height: 24),
                  Text('Sedes y horarios',
                      style:
                          t.titleMedium?.copyWith(fontWeight: FontWeight.w800)),
                  const SizedBox(height: 10),
                  for (final s in academia.sedes)
                    _TarjetaSedeInfo(sede: s, academia: academia),
                ],
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
                        const CircleAvatar(
                            radius: 18,
                            backgroundColor: amarillo,
                            child: Icon(Icons.local_offer_outlined,
                                color: Colors.white, size: 20)),
                        const SizedBox(width: 10),
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
                  // Planes agrupados por programa. Si hay MÁS de un programa, se
                  // elige primero cuál (evita el scroll enorme); si hay uno solo
                  // se muestra directo.
                  _PlanesSection(academia: academia),
                // (El chat con el profe y campeonatos ahora van ARRIBA, en la
                // fila de acciones — ya no escondidos aquí.)
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
          )),
        ),
      ],
      ),
    );
  }
}

/// Chip de acción (estilo Airbnb): blanco, borde suave, esquinas redondeadas.
/// Se usa en la fila de accesos rápidos (ubicación, WhatsApp, campeonatos).
class _ChipAccion extends StatelessWidget {
  const _ChipAccion({
    required this.icon,
    required this.label,
    required this.onTap,
    this.color,
  });
  final IconData icon;
  final String label;
  final VoidCallback onTap;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    final c = color ?? Theme.of(context).colorScheme.primary;
    return Material(
      color: Theme.of(context).colorScheme.surface,
      borderRadius: BorderRadius.circular(999),
      child: InkWell(
        borderRadius: BorderRadius.circular(999),
        onTap: onTap,
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(999),
            border: Border.all(color: const Color(0xFFE4E4E4)),
            boxShadow: const [
              BoxShadow(
                  color: Color(0x0F000000), blurRadius: 6, offset: Offset(0, 2)),
            ],
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(icon, size: 18, color: c),
              const SizedBox(width: 7),
              Text(label,
                  style: TextStyle(
                      fontWeight: FontWeight.w700,
                      fontSize: 13.5,
                      color: Theme.of(context).colorScheme.onSurface)),
            ],
          ),
        ),
      ),
    );
  }
}

/// Tarjeta pública de una SEDE: nombre + dirección + horarios por programa +
/// "cómo llegar". Solo se muestra en academias multi-sede.
class _TarjetaSedeInfo extends StatelessWidget {
  const _TarjetaSedeInfo({required this.sede, required this.academia});
  final Sede sede;
  final Academia academia;

  @override
  Widget build(BuildContext context) {
    final programas = academia.planesPorPrograma.keys
        .map((p) => p.isEmpty ? 'General' : p)
        .toList();
    final horarios = <MapEntry<String, String>>[];
    for (final prog in programas) {
      final h = academia.horarioDe(sede.id, prog);
      if (h.isNotEmpty) horarios.add(MapEntry(prog, h));
    }
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: trazo),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.place, size: 18, color: lima),
              const SizedBox(width: 8),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(sede.nombre,
                        style: const TextStyle(fontWeight: FontWeight.w800)),
                    if (sede.direccion.isNotEmpty)
                      Text(sede.direccion,
                          style:
                              const TextStyle(color: textoTenue, fontSize: 12)),
                  ],
                ),
              ),
              if (sede.ubicacion != null)
                IconButton(
                  icon: const Icon(Icons.directions, color: lima),
                  tooltip: 'Cómo llegar',
                  onPressed: () => UbicacionShare.abrirMapa(sede.ubicacion!),
                ),
            ],
          ),
          if (horarios.isNotEmpty) ...[
            const SizedBox(height: 6),
            for (final e in horarios)
              Padding(
                padding: const EdgeInsets.only(top: 3),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Icon(Icons.schedule, size: 14, color: textoTenue),
                    const SizedBox(width: 6),
                    Expanded(
                        child: Text('${e.key}: ${e.value}',
                            style: const TextStyle(fontSize: 12.5))),
                  ],
                ),
              ),
          ],
        ],
      ),
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

/// Sección de PLANES con selección de programa. Si la academia tiene más de un
/// programa (Bola Roja/Naranja, Verde, Amarilla…), primero se elige cuál (chips)
/// y solo se muestran los precios y horarios de ESE programa — así la ficha no
/// escrolea de más. Con un solo programa se muestra todo directo.
class _PlanesSection extends StatefulWidget {
  const _PlanesSection({required this.academia});
  final Academia academia;
  @override
  State<_PlanesSection> createState() => _PlanesSectionState();
}

class _PlanesSectionState extends State<_PlanesSection> {
  String? _prog; // clave del programa elegido

  /// Horarios (por sede) publicados para un programa. Empareja por el sufijo
  /// `|programa` de la clave `sedeId|programa`, sin depender del id de sede.
  List<String> _horariosDe(String prog) {
    final out = <String>[];
    for (final e in widget.academia.horarios.entries) {
      if (e.key.endsWith('|$prog') && e.value.trim().isNotEmpty) {
        out.add(e.value.trim());
      }
    }
    return out;
  }

  /// Encabezado (nombre + etapa/edad) + horarios + tarjetas de plan del grupo.
  List<Widget> _grupo(MapEntry<String, List<Plan>> entrada,
      {bool conEncabezado = true}) {
    final academia = widget.academia;
    // Horario por SEDE (multi-sede) manda; si no hay, cae al horario del
    // programa (campo opcional que puso el profe en el editor).
    final perSede = entrada.key.isEmpty ? const <String>[] : _horariosDe(entrada.key);
    final progHorario = entrada.value.first.horario.trim();
    final horarios = perSede.isNotEmpty
        ? perSede
        : (progHorario.isNotEmpty ? [progHorario] : const <String>[]);
    return [
      if (conEncabezado && entrada.key.isNotEmpty) ...[
        const SizedBox(height: 6),
        Text(entrada.key,
            style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 16)),
        if (entrada.value.first.etapaEdad.isNotEmpty)
          Padding(
            padding: const EdgeInsets.only(top: 2, bottom: 4),
            child: Text(entrada.value.first.etapaEdad,
                style: const TextStyle(color: textoTenue, fontSize: 12.5)),
          ),
        const SizedBox(height: 8),
      ],
      if (horarios.isNotEmpty) ...[
        Padding(
          padding: const EdgeInsets.only(bottom: 8),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Icon(Icons.schedule, size: 16, color: bosque),
              const SizedBox(width: 6),
              Expanded(
                child: Text(horarios.join(' · '),
                    style: const TextStyle(fontSize: 12.5, color: textoTenue)),
              ),
            ],
          ),
        ),
      ],
      for (final p in entrada.value)
        _TarjetaPlan(
            academia: academia,
            plan: p,
            tituloOverride: entrada.key.isEmpty ? null : p.frecuenciaLabel),
    ];
  }

  @override
  Widget build(BuildContext context) {
    final grupos = widget.academia.planesPorPrograma.entries.toList();

    // Un solo programa (o planes sin programa): mostrar todo directo.
    if (grupos.length <= 1) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [for (final g in grupos) ..._grupo(g)],
      );
    }

    // Varios programas: elegir primero cuál.
    final selKey = grupos.any((g) => g.key == _prog) ? _prog! : grupos.first.key;
    final sel = grupos.firstWhere((g) => g.key == selKey);
    String etiqueta(String k) => k.isEmpty ? 'General' : k;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text('¿Qué programa te interesa?',
            style: TextStyle(fontWeight: FontWeight.w700, fontSize: 13.5)),
        const SizedBox(height: 8),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            for (final g in grupos)
              ChoiceChip(
                label: Text(etiqueta(g.key)),
                selected: g.key == selKey,
                selectedColor: lima,
                labelStyle: TextStyle(
                    color: g.key == selKey
                        ? Colors.white
                        : Theme.of(context).colorScheme.onSurface,
                    fontWeight: FontWeight.w600),
                onSelected: (_) => setState(() => _prog = g.key),
              ),
          ],
        ),
        const SizedBox(height: 14),
        ..._grupo(sel),
      ],
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
          if (academia.tienePreciosPorSede(plan)) ...[
            const SizedBox(height: 4),
            Row(
              children: [
                const Icon(Icons.store_mall_directory_outlined,
                    size: 14, color: textoTenue),
                const SizedBox(width: 4),
                Text('El precio varía según la sede',
                    style: TextStyle(
                        color: Theme.of(context).colorScheme.primary,
                        fontSize: 12,
                        fontWeight: FontWeight.w600)),
              ],
            ),
          ],
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
    // 0) Sesión OBLIGATORIA antes de matricular/pagar: el cobro (Culqi) necesita
    //    un email válido y la matrícula se ata a la cuenta. Sin esto, el pago
    //    fallaba con "email inválido". Pedimos login primero (Airbnb): así el
    //    nombre y el correo ya vienen cargados.
    if (!await LoginGoogleSheet.mostrar(context, motivo: 'matricularte y pagar')) {
      return;
    }
    if (!context.mounted) return;
    // 1) Datos del alumno + MODO (mes a mes / adelantado) + cantidad + total.
    final datos = await showModalBottomSheet<
        (String, String, int, bool, double, bool, int?, String)>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Theme.of(context).colorScheme.surface,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      builder: (_) => _HojaDatosAlumno(
        nombreInicial: appState.usuario?.nombre ?? '',
        academia: academia.nombre,
        logoUrl: academia.logoUrl,
        planObj: plan,
        moneda: academia.monedaSimbolo,
        esMensual: plan.tipo == TipoPlan.mensual,
        descuentoPrepago: academia.descuentoPrepago,
        mesesMinPrepago: academia.mesesMinPrepago,
        sedes: academia.sedes,
        preciosSede: academia.preciosSede,
      ),
    );
    if (datos == null) return;
    final (nombre, whatsapp, cantidad, mesAMes, totalAhora, esHijo, edad,
            sedeId) =
        datos;
    final monto = totalAhora.round();
    // Precio mensual y total del plan EN LA SEDE elegida (multi-sede con tarifas
    // por local): así las cuotas y el débito automático usan el precio correcto.
    final precioMesSede = academia.precioMesEnSede(plan, sedeId);
    final totalPlanSede = academia.totalPlanEnSede(plan, sedeId);

    // 2) Pago del total a cobrar AHORA (mes a mes = 1 mes; adelantado = N meses
    // con descuento si aplica). Capturamos el token para el débito automático.
    if (!context.mounted) return;
    String? tokenUsado;
    String? operacionId;
    final pagado = await PagoTarjeta.cobrar(
      context,
      monto: monto,
      concepto: 'Matrícula ${academia.nombre} · ${plan.nombre}',
      email: appState.usuario?.email ?? '',
      moneda: academia.monedaSimbolo,
      onToken: (t) => tokenUsado = t,
      onOperacion: (o) => operacionId = o,
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
      // Si es para un hijo(a): el titular de la cuenta es el apoderado.
      apoderadoNombre: esHijo ? (appState.usuario?.nombre ?? 'Apoderado') : '',
      apoderadoWhatsapp: esHijo ? whatsapp : '',
      edad: esHijo ? edad : null,
      operacionId: operacionId ?? '',
      sedeId: sedeId,
      precioMesOverride: precioMesSede,
    );

    // 3b) Mes a mes: activa el débito automático de los meses restantes con la
    // tarjeta usada. cobrosRestantes = meses comprometidos − el 1.º ya pagado.
    if (mesAMes && tokenUsado != null) {
      PagosService.crearSuscripcionAlumno(
        alumnoId: alumno.id,
        academiaId: academia.id,
        email: appState.usuario?.email ?? '',
        token: tokenUsado!,
        montoSoles: totalPlanSede,
        nombre: nombre,
        pais: academia.pais.iso,
        concepto: 'Mensualidad ${academia.nombre} · ${plan.nombre}',
        cobrosRestantes: cantidad - 1,
      );
    }

    if (!context.mounted) return;
    await showDialog<void>(
      context: context,
      builder: (_) => DialogoPichangol(
        titulo: '¡Matrícula lista!',
        icono: Icons.check_circle,
        mensaje: mesAMes
            ? 'Ya estás inscrito en ${academia.nombre} (${plan.nombre}). '
                'Se debitará ${academia.monedaSimbolo} ${totalPlanSede.toStringAsFixed(2)} '
                'automático cada mes; puedes cancelar cuando quieras.'
            : 'Ya estás inscrito en ${academia.nombre} (${plan.nombre}). '
                'Te contactarán por WhatsApp para coordinar tus horarios.',
        acciones: [
          if (academia.whatsapp.isNotEmpty)
            TextButton.icon(
              onPressed: () {
                WhatsAppLink.abrir(academia.whatsapp,
                    'Hola, acabo de matricularme en ${academia.nombre} (${plan.nombre}) por Pichangol. Soy $nombre.');
                Navigator.of(context).pop();
              },
              icon: const Icon(Icons.chat, color: lima),
              label: const Text('Avisar al profe'),
            ),
          FilledButton(
            style: FilledButton.styleFrom(
                backgroundColor: lima,
                foregroundColor: Colors.white,
                shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(12)),
                padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12)),
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('Listo',
                style: TextStyle(fontWeight: FontWeight.w800)),
          ),
        ],
      ),
    );
    // Tras confirmar, lleva al alumno a "Mis clases y pagos": ahí ve su
    // matrícula, el comprobante y el cronograma de cuotas.
    if (!context.mounted) return;
    Navigator.of(context).push(
        MaterialPageRoute(builder: (_) => const MisClasesScreen()));
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
    this.logoUrl,
    this.esMensual = false,
    this.descuentoPrepago = 0,
    this.mesesMinPrepago = 3,
    this.sedes = const [],
    this.preciosSede = const {},
  });
  final String nombreInicial;
  final String academia;
  final String? logoUrl;
  final Plan planObj;
  final String moneda;
  final bool esMensual; // ¿el plan es mensual? (habilita "mes a mes")
  final double descuentoPrepago; // % de descuento por pago adelantado
  final int mesesMinPrepago; // desde cuántos meses aplica el descuento
  final List<Sede> sedes; // sedes de la academia (elige una si hay varias)
  // Precios por sede (clave "sedeId|planId"): la tarifa cambia según el local.
  final Map<String, double> preciosSede;

  @override
  State<_HojaDatosAlumno> createState() => _HojaDatosAlumnoState();
}

class _HojaDatosAlumnoState extends State<_HojaDatosAlumno> {
  late final TextEditingController _nombre = TextEditingController();
  final _whatsapp = TextEditingController();
  final _edad = TextEditingController();
  int _cantidad = 1;
  bool _mesAMes = false; // solo aplica a planes mensuales
  bool _esHijo = false; // ¿matriculo a mi hijo(a)? (yo soy el apoderado)
  String? _error; // mensaje de validación inline (visible)
  // Sede elegida (academias multi-sede): por defecto la primera.
  late String? _sedeId =
      widget.sedes.isNotEmpty ? widget.sedes.first.id : null;

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

  // Precio mensual/por-clase EFECTIVO según la sede elegida (multi-sede con
  // tarifas por local); si la sede no tiene precio propio, usa el del plan.
  double get _precioMesEf {
    final id = _sedeId;
    if (id != null && id.isNotEmpty) {
      final v = widget.preciosSede['$id|${_plan.id}'];
      if (v != null) return v;
    }
    return _plan.precioMes;
  }

  // Total del plan a este precio (por clase = precio; mensual/prepago = ×meses).
  double get _planTotalEf =>
      _plan.tipo == TipoPlan.porClase ? _precioMesEf : _precioMesEf * _plan.meses;

  double get _totalSinDto => _planTotalEf * _cantidad;
  double get _ahorro =>
      _aplicaDescuento ? _totalSinDto * widget.descuentoPrepago / 100 : 0;
  // Lo que se cobra AHORA: mes a mes = 1 mes; adelantado = total − descuento.
  double get _total => _mesAMes ? _planTotalEf : (_totalSinDto - _ahorro);

  @override
  void initState() {
    super.initState();
    _nombre.text = widget.nombreInicial; // "Para mí": prellena el nombre del titular
  }

  @override
  void dispose() {
    _nombre.dispose();
    _whatsapp.dispose();
    _edad.dispose();
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
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              LogoAcademia(logoUrl: widget.logoUrl, size: 40),
              const SizedBox(width: 10),
              Expanded(
                child: Text('Matricularme en ${widget.academia}',
                    style: const TextStyle(
                        fontWeight: FontWeight.w800, fontSize: 17)),
              ),
            ],
          ),
          const SizedBox(height: 4),
          Text('Plan: ${_plan.nombre}',
              style: const TextStyle(color: textoTenue, fontSize: 13)),
          const SizedBox(height: 16),
          // ¿Para quién es la matrícula? Con la misma cuenta puedes inscribir a
          // varias personas (tú + tus hijos); cada una es un alumno aparte.
          Row(
            children: [
              Expanded(
                child: _ChipModo(
                  titulo: 'Para mí',
                  subtitulo: 'Soy yo quien entrena',
                  activo: !_esHijo,
                  onTap: () => setState(() {
                    _esHijo = false;
                    _nombre.text = widget.nombreInicial;
                  }),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: _ChipModo(
                  titulo: 'Para mi hijo(a)',
                  subtitulo: 'Yo soy el apoderado',
                  activo: _esHijo,
                  onTap: () => setState(() {
                    _esHijo = true;
                    if (_nombre.text == widget.nombreInicial) _nombre.clear();
                  }),
                ),
              ),
            ],
          ),
          const SizedBox(height: 14),
          TextField(
            controller: _nombre,
            textCapitalization: TextCapitalization.words,
            decoration: InputDecoration(
                labelText: _esHijo ? 'Nombre del hijo(a)' : 'Nombre del alumno',
                prefixIcon: const Icon(Icons.person_outline)),
          ),
          if (_esHijo) ...[
            const SizedBox(height: 14),
            TextField(
              controller: _edad,
              keyboardType: TextInputType.number,
              decoration: const InputDecoration(
                  labelText: 'Edad del hijo(a) (opcional)',
                  prefixIcon: Icon(Icons.cake_outlined)),
            ),
          ],
          const SizedBox(height: 14),
          TextField(
            controller: _whatsapp,
            keyboardType: TextInputType.phone,
            decoration: InputDecoration(
                labelText: _esHijo
                    ? 'WhatsApp del apoderado (tú)'
                    : 'WhatsApp de contacto',
                prefixText: '$codigoTelActual ',
                prefixIcon: const Icon(Icons.chat_outlined)),
          ),
          // Sede (academias multi-sede): elige dónde entrenará el alumno.
          if (widget.sedes.length > 1) ...[
            const SizedBox(height: 18),
            const Text('¿En qué sede entrenará?',
                style: TextStyle(fontWeight: FontWeight.w700)),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                for (final s in widget.sedes)
                  ChoiceChip(
                    avatar: Icon(Icons.place,
                        size: 16,
                        color: _sedeId == s.id ? Colors.white : lima),
                    label: Text(s.nombre),
                    selected: _sedeId == s.id,
                    selectedColor: lima,
                    labelStyle: TextStyle(
                        color: _sedeId == s.id ? Colors.white : null,
                        fontWeight: FontWeight.w600),
                    onSelected: (_) => setState(() => _sedeId = s.id),
                  ),
              ],
            ),
          ],
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
                  _esHijo,
                  int.tryParse(_edad.text.trim()),
                  _sedeId ?? '',
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
