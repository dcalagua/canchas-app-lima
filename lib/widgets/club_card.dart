import 'package:flutter/material.dart';

import '../models/club.dart';
import '../models/models.dart';
import '../models/resena.dart';
import '../services/places_service.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../utils/moneda.dart';
import 'court_lines.dart';
import 'marca.dart';

/// Tarjeta de club (rediseño): portada con gradiente de deporte + líneas de
/// cancha, badges, rating, chips de deportes y precio "desde".
class ClubCard extends StatelessWidget {
  const ClubCard(
      {super.key,
      required this.club,
      this.onTap,
      this.distanciaKm,
      this.nivelDestacado = 0,
      this.esMejorPrecio = false,
      this.ahorroPct,
      this.resumenResenas});

  final Club club;
  final VoidCallback? onTap;

  /// Reputación REAL del local (⭐ promedio + cantidad). Si es null o no tiene
  /// reseñas, no se muestra nada (nunca un rating inventado — regla de prod).
  final ResumenResenas? resumenResenas;

  /// Distancia (km) del usuario al local. Si viene, se muestra junto a la
  /// dirección ("a 2.3 km"). Null = no se muestra (sin ubicación).
  final double? distanciaKm;

  /// Nivel de DESTACADO del local (0 = no; 1 bronce, 2 plata, 3 oro). Su dueño
  /// puso saldo → más visibilidad. Se muestra con medalla en el badge.
  final int nivelDestacado;

  /// Comparador de precios: true si este local tiene el precio "desde" más bajo
  /// entre las opciones del MISMO deporte cerca del usuario. Muestra el sello
  /// "MEJOR PRECIO" en la portada.
  final bool esMejorPrecio;

  /// % de ahorro respecto al promedio de la zona (para el mismo deporte). Si es
  /// > 0 se muestra un chip verde "−N% vs. zona" junto al precio. Null = no
  /// comparable (menos de 2 opciones con precio).
  final int? ahorroPct;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final cs = Theme.of(context).colorScheme;
    final portada = club.principal.deporte;
    final desc = !club.registrada;
    final fotos = _fotosClub(club);
    return GestureDetector(
      onTap: onTap,
      child: Container(
        decoration: BoxDecoration(
          color: cs.surface,
          borderRadius: BorderRadius.circular(20),
          border: Border.all(color: const Color(0xFFEEEAE0)),
          boxShadow: const [
            BoxShadow(color: Color(0x1A000000), blurRadius: 20, offset: Offset(0, 6)),
          ],
        ),
        clipBehavior: Clip.antiAlias,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Portada: carrusel de fotos deslizable (estilo Airbnb) + badges.
            SizedBox(
              height: 150,
              width: double.infinity,
              child: Stack(
                children: [
                  Positioned.fill(
                    child: _CoverCarrusel(
                      fotos: fotos,
                      portada: portada,
                      // Descubierta sin fotos propias → baja 1 foto de Google
                      // en vivo (perezoso + caché de sesión compartida con la
                      // ficha, así abrirla después no vuelve a pedir nada).
                      canchaIdGoogle: desc ? club.principal.id : null,
                    ),
                  ),
                  Positioned(
                    top: 14,
                    left: 14,
                    child: nivelDestacado > 0
                        ? _Badge(
                            '${medallaDestacado(nivelDestacado)} DESTACADO',
                            bg: lima, fg: Colors.white)
                        : desc
                            ? const _Badge('◎ EN GOOGLE',
                                bg: Colors.black54, fg: Colors.white)
                            : club.clubFundador
                                ? const _Badge('CLUB FUNDADOR',
                                    bg: pino, fg: lima)
                                : _Badge('${club.canchas.length} CANCHAS',
                                    bg: Colors.white, fg: tinta),
                  ),
                  Positioned(
                    top: 12,
                    right: 12,
                    child: GestureDetector(
                      onTap: () => appState.alternarFavorito(club.id),
                      child: CircleAvatar(
                        radius: 16,
                        backgroundColor: Colors.white,
                        child: Icon(
                          appState.esFavorito(club.id)
                              ? Icons.favorite
                              : Icons.favorite_border,
                          size: 18,
                          color: appState.esFavorito(club.id)
                              ? const Color(0xFFE0245E)
                              : tinta,
                        ),
                      ),
                    ),
                  ),
                  // Comparador de precios: sello del más barato de su deporte.
                  if (esMejorPrecio && !desc)
                    const Positioned(
                      bottom: 14,
                      left: 14,
                      child: _Badge('💰 MEJOR PRECIO',
                          bg: _verdeAhorro, fg: Colors.white),
                    ),
                ],
              ),
            ),
            Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: Text(club.nombre,
                            style: t.titleMedium
                                ?.copyWith(fontWeight: FontWeight.w700),
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis),
                      ),
                      // Reputación REAL (⭐ promedio + cantidad). Nunca fake:
                      // si no hay reseñas, no se muestra nada.
                      if (resumenResenas?.hay == true) ...[
                        const SizedBox(width: 8),
                        const Icon(Icons.star, size: 15, color: amarillo),
                        const SizedBox(width: 2),
                        Text(resumenResenas!.promedio.toStringAsFixed(1),
                            style: t.bodyMedium
                                ?.copyWith(fontWeight: FontWeight.w800)),
                        const SizedBox(width: 2),
                        Text('(${resumenResenas!.cantidad})',
                            style: t.bodySmall
                                ?.copyWith(color: textoTenueDe(context))),
                      ],
                    ],
                  ),
                  const SizedBox(height: 2),
                  Row(
                    children: [
                      Expanded(
                        child: Text(
                          club.direccion ??
                              [
                                if (club.barrio.isNotEmpty) club.barrio,
                                '${club.canchas.length} ${club.canchas.length == 1 ? 'cancha' : 'canchas'}',
                              ].join(' · '),
                          style: t.bodySmall?.copyWith(color: textoTenueDe(context)),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                      if (distanciaKm != null) ...[
                        const SizedBox(width: 8),
                        Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Icon(Icons.near_me,
                                size: 13, color: cs.primary),
                            const SizedBox(width: 3),
                            Text(_distanciaTxt(distanciaKm!),
                                style: t.bodySmall?.copyWith(
                                    color: cs.primary,
                                    fontWeight: FontWeight.w700)),
                          ],
                        ),
                      ],
                    ],
                  ),
                  if (club.verificada) ...[
                    const SizedBox(height: 8),
                    const Align(
                        alignment: Alignment.centerLeft,
                        child: SelloVerificada()),
                  ],
                  const SizedBox(height: 10),
                  Wrap(
                    spacing: 6,
                    runSpacing: 6,
                    children: [
                      for (final d in club.deportes)
                        _Badge(d.etiqueta,
                            bg: const Color(0xFFF0ECE2),
                            fg: const Color(0xFF5C574E)),
                      for (final s in _superficies(club))
                        _BadgeIcono(s, iconoSuperficie(s)),
                    ],
                  ),
                  const SizedBox(height: 12),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    crossAxisAlignment: CrossAxisAlignment.end,
                    children: [
                      if (desc)
                        Text('Reclama tu cancha',
                            style: t.titleSmall?.copyWith(
                                color: clayOscuro, fontWeight: FontWeight.w700))
                      else
                        Flexible(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              RichText(
                                text: TextSpan(
                                  style: t.bodySmall
                                      ?.copyWith(color: textoTenueDe(context)),
                                  children: [
                                    const TextSpan(text: 'desde '),
                                    TextSpan(
                                      text:
                                          '${club.monedaSimbolo}${club.precioDesde?.toStringAsFixed(2) ?? '--'}',
                                      style: t.titleMedium?.copyWith(
                                          color: cs.onSurface,
                                          fontWeight: FontWeight.w700),
                                    ),
                                    const TextSpan(text: ' /hora'),
                                  ],
                                ),
                              ),
                              if (ahorroPct != null && ahorroPct! > 0) ...[
                                const SizedBox(height: 5),
                                _AhorroChip(ahorroPct!),
                              ],
                            ],
                          ),
                        ),
                      Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 12, vertical: 6),
                        decoration: BoxDecoration(
                          color: lima,
                          borderRadius: BorderRadius.circular(9),
                        ),
                        child: Text(
                          desc ? 'En Google' : 'Disponible hoy',
                          style: t.bodySmall?.copyWith(
                              color: Colors.white, fontWeight: FontWeight.w700),
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Verde del comparador de precios (ahorro / mejor precio). Tono sobrio,
/// congruente con la paleta (no el verde saturado de WhatsApp).
const Color _verdeAhorro = Color(0xFF119861);

/// Chip verde "−N% vs. zona": señala cuánto más barato es este local respecto
/// al promedio de su deporte cerca del usuario (núcleo del comparador).
class _AhorroChip extends StatelessWidget {
  const _AhorroChip(this.pct);
  final int pct;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: _verdeAhorro.withOpacity(0.12),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Icon(Icons.trending_down, size: 13, color: _verdeAhorro),
          const SizedBox(width: 4),
          Text('$pct% vs. zona',
              style: const TextStyle(
                  color: _verdeAhorro,
                  fontSize: 11.5,
                  fontWeight: FontWeight.w800,
                  height: 1)),
        ],
      ),
    );
  }
}

/// Fotos del local para la portada: junta fotoUrl + galerías de todas sus
/// canchas, sin repetir, en orden. Vacío = sin fotos (se usa el gradiente).
List<String> _fotosClub(Club club) {
  final vistas = <String>{};
  final out = <String>[];
  for (final c in club.canchas) {
    for (final f in [if (c.fotoUrl != null) c.fotoUrl!, ...c.fotos]) {
      if (f.isNotEmpty && vistas.add(f)) out.add(f);
    }
  }
  return out;
}

/// "a 450 m" / "a 2.3 km".
String _distanciaTxt(double km) {
  if (km < 1) return 'a ${(km * 1000).round()} m';
  return 'a ${km.toStringAsFixed(1)} km';
}

/// Carrusel de portada deslizable con puntos (estilo Airbnb). Si no hay fotos,
/// muestra el gradiente del deporte con líneas de cancha.
class _CoverCarrusel extends StatefulWidget {
  const _CoverCarrusel(
      {required this.fotos, required this.portada, this.canchaIdGoogle});
  final List<String> fotos;
  final Deporte portada;

  /// Id `gp_…` de la cancha DESCUBIERTA en Google. Si viene y no hay fotos
  /// propias, la tarjeta baja UNA foto de Google en forma perezosa (misma
  /// caché de sesión que la ficha: un solo request por lugar por sesión).
  final String? canchaIdGoogle;

  @override
  State<_CoverCarrusel> createState() => _CoverCarruselState();
}

class _CoverCarruselState extends State<_CoverCarrusel> {
  final _ctrl = PageController();
  int _pagina = 0;

  /// Foto de Google bajada en vivo (solo la primera: portada de la tarjeta).
  List<String> _fotosVivo = const [];

  List<String> get _fotos =>
      widget.fotos.isNotEmpty ? widget.fotos : _fotosVivo;

  @override
  void initState() {
    super.initState();
    _cargarFotoVivo();
  }

  Future<void> _cargarFotoVivo() async {
    final id = widget.canchaIdGoogle;
    if (id == null || widget.fotos.isNotEmpty) return;
    final urls = await PlacesService.fotosFicha(id);
    if (mounted && urls.isNotEmpty) {
      setState(() => _fotosVivo = [urls.first]);
    }
  }

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final fondo = DecoratedBox(
      decoration: BoxDecoration(gradient: gradienteDeporte(widget.portada)),
      child: const CourtLines(),
    );
    final fotos = _fotos;
    if (fotos.isEmpty) return fondo;
    return Stack(
      fit: StackFit.expand,
      children: [
        PageView.builder(
          controller: _ctrl,
          itemCount: fotos.length,
          onPageChanged: (i) => setState(() => _pagina = i),
          itemBuilder: (_, i) => Image.network(
            fotos[i],
            fit: BoxFit.cover,
            errorBuilder: (_, __, ___) => fondo,
            loadingBuilder: (ctx, child, prog) =>
                prog == null ? child : fondo,
          ),
        ),
        if (fotos.length > 1)
          Positioned(
            bottom: 10,
            left: 0,
            right: 0,
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                for (var i = 0; i < fotos.length; i++)
                  AnimatedContainer(
                    duration: const Duration(milliseconds: 200),
                    margin: const EdgeInsets.symmetric(horizontal: 3),
                    width: i == _pagina ? 16 : 6,
                    height: 6,
                    decoration: BoxDecoration(
                      color: i == _pagina ? Colors.white : Colors.white60,
                      borderRadius: BorderRadius.circular(999),
                    ),
                  ),
              ],
            ),
          ),
      ],
    );
  }
}

/// Superficies (tipos de piso) presentes en el local, sin repetir y en orden.
List<String> _superficies(Club club) {
  final vistas = <String>{};
  final orden = <String>[];
  for (final c in club.canchas) {
    final s = c.superficie;
    if (s.isNotEmpty && vistas.add(s)) orden.add(s);
  }
  return orden;
}

/// Badge con ícono (para superficie: piso de la cancha).
class _BadgeIcono extends StatelessWidget {
  const _BadgeIcono(this.texto, this.icono);
  final String texto;
  final IconData icono;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 4),
      decoration: BoxDecoration(
        color: limaSuave,
        borderRadius: BorderRadius.circular(999),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icono, size: 13, color: bosque),
          const SizedBox(width: 4),
          Text(texto,
              style: const TextStyle(
                  color: bosque,
                  fontSize: 11,
                  fontWeight: FontWeight.w700,
                  height: 1)),
        ],
      ),
    );
  }
}

class _Badge extends StatelessWidget {
  const _Badge(this.texto, {required this.bg, required this.fg});
  final String texto;
  final Color bg;
  final Color fg;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 4),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(
        texto,
        style: TextStyle(
            color: fg, fontSize: 11, fontWeight: FontWeight.w700, height: 1),
      ),
    );
  }
}
