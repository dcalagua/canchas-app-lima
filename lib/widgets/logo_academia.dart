import 'package:flutter/material.dart';

import '../theme.dart';

/// Logo de una academia (avatar cuadrado redondeado). Si la academia no subió
/// logo (o falla la descarga), cae al ícono de raqueta. Reutilizable en todos
/// los lugares donde aparece el nombre de la academia (ficha, matrícula, panel
/// del profe, "Mis clases", listados…).
class LogoAcademia extends StatelessWidget {
  const LogoAcademia({
    super.key,
    required this.logoUrl,
    this.size = 36,
    this.fallbackIcon = Icons.sports_tennis,
    this.color = lima,
  });
  final String? logoUrl;
  final double size;
  final IconData fallbackIcon;
  final Color color;

  @override
  Widget build(BuildContext context) {
    final url = logoUrl;
    if (url != null && url.isNotEmpty) {
      return ClipRRect(
        borderRadius: BorderRadius.circular(size * 0.24),
        child: Image.network(
          url,
          width: size,
          height: size,
          fit: BoxFit.cover,
          errorBuilder: (_, __, ___) =>
              Icon(fallbackIcon, color: color, size: size * 0.62),
        ),
      );
    }
    return Icon(fallbackIcon, color: color, size: size * 0.62);
  }
}
