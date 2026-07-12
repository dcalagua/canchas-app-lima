import 'package:flutter/material.dart';

import '../models/club.dart';
import '../models/models.dart';
import '../theme.dart';
import '../utils/moneda.dart';
import 'court_lines.dart';
import 'marca.dart';

/// Tarjeta de club (rediseño): portada con gradiente de deporte + líneas de
/// cancha, badges, rating, chips de deportes y precio "desde".
class ClubCard extends StatelessWidget {
  const ClubCard(
      {super.key, required this.club, this.onTap, this.distanciaKm});

  final Club club;
  final VoidCallback? onTap;

  /// Distancia (km) del usuario al local. Si viene, se muestra junto a la
  /// dirección ("a 2.3 km"). Null = no se muestra (sin ubicación).
  final double? distanciaKm;

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
                    child: _CoverCarrusel(fotos: fotos, portada: portada),
                  ),
                  Positioned(
                    top: 14,
                    left: 14,
                    child: desc
                        ? const _Badge('◎ EN GOOGLE',
                            bg: Colors.black54, fg: Colors.white)
                        : club.clubFundador
                            ? const _Badge('CLUB FUNDADOR', bg: pino, fg: lima)
                            : _Badge('${club.canchas.length} CANCHAS',
                                bg: Colors.white, fg: tinta),
                  ),
                  const Positioned(
                    top: 12,
                    right: 12,
                    child: CircleAvatar(
                      radius: 16,
                      backgroundColor: Colors.white,
                      child: Icon(Icons.favorite_border, size: 18, color: tinta),
                    ),
                  ),
                ],
              ),
            ),
            Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(club.nombre,
                      style:
                          t.titleMedium?.copyWith(fontWeight: FontWeight.w700),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis),
                  const SizedBox(height: 2),
                  Row(
                    children: [
                      Expanded(
                        child: Text(
                          club.direccion ??
                              '${club.barrio} · ${club.canchas.length} ${club.canchas.length == 1 ? 'cancha' : 'canchas'}',
                          style: t.bodySmall?.copyWith(color: textoTenue),
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
                        RichText(
                          text: TextSpan(
                            style: t.bodySmall?.copyWith(color: textoTenue),
                            children: [
                              const TextSpan(text: 'desde '),
                              TextSpan(
                                text: '$monedaSimbolo${club.precioDesde?.toStringAsFixed(2) ?? '--'}',
                                style: t.titleMedium?.copyWith(
                                    color: cs.onSurface, fontWeight: FontWeight.w700),
                              ),
                              const TextSpan(text: ' /hora'),
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
                          desc ? 'En el mapa' : 'Disponible hoy',
                          style: t.bodySmall?.copyWith(
                              color: pinoOscuro, fontWeight: FontWeight.w700),
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
  const _CoverCarrusel({required this.fotos, required this.portada});
  final List<String> fotos;
  final Deporte portada;

  @override
  State<_CoverCarrusel> createState() => _CoverCarruselState();
}

class _CoverCarruselState extends State<_CoverCarrusel> {
  final _ctrl = PageController();
  int _pagina = 0;

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
    if (widget.fotos.isEmpty) return fondo;
    return Stack(
      fit: StackFit.expand,
      children: [
        PageView.builder(
          controller: _ctrl,
          itemCount: widget.fotos.length,
          onPageChanged: (i) => setState(() => _pagina = i),
          itemBuilder: (_, i) => Image.network(
            widget.fotos[i],
            fit: BoxFit.cover,
            errorBuilder: (_, __, ___) => fondo,
            loadingBuilder: (ctx, child, prog) =>
                prog == null ? child : fondo,
          ),
        ),
        if (widget.fotos.length > 1)
          Positioned(
            bottom: 10,
            left: 0,
            right: 0,
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                for (var i = 0; i < widget.fotos.length; i++)
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
