import 'package:flutter/material.dart';

import '../models/models.dart';
import '../models/nivel.dart';
import '../theme.dart';

/// Pastilla estilo Airbnb con el NIVEL del jugador en un deporte (0-7, aquí
/// 1.0–7.0), tipo Playtomic: ícono del deporte + "Fútbol · 4.3". Blanca, borde
/// gris muy suave, relieve leve, esquinas muy redondeadas.
class NivelChip extends StatelessWidget {
  const NivelChip({super.key, required this.nivel, this.compacto = false});
  final Nivel nivel;
  final bool compacto;

  @override
  Widget build(BuildContext context) {
    final dep = deportePorNombre(nivel.deporte);
    final nombreDep = dep?.etiqueta ?? nivel.deporte;
    return Container(
      padding: EdgeInsets.symmetric(
          horizontal: compacto ? 10 : 12, vertical: compacto ? 5 : 7),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(24),
        border: Border.all(color: const Color(0xFFE4E4E4)),
        boxShadow: const [
          BoxShadow(color: Color(0x0F000000), blurRadius: 6, offset: Offset(0, 2)),
        ],
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(dep != null ? iconoDeporte(dep) : Icons.sports,
              size: compacto ? 15 : 17, color: teal),
          const SizedBox(width: 6),
          if (!compacto) ...[
            Text('$nombreDep · ',
                style: const TextStyle(
                    color: Color(0xFF222222), fontWeight: FontWeight.w600)),
          ],
          Text(nivel.etiqueta,
              style: TextStyle(
                  color: bosque,
                  fontWeight: FontWeight.w900,
                  fontSize: compacto ? 13 : 15)),
        ],
      ),
    );
  }
}
