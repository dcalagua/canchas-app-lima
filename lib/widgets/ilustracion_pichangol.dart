import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';

import '../services/supabase_service.dart';
import '../theme.dart';

/// ILUSTRACIÓN de marca para ESTADOS VACÍOS y momentos del app (darle vida,
/// pedido del director): imagen flat de la familia visual Pichangol servida
/// por el backend (se genera una vez, Storage + caché en disco). Fallback:
/// emoji grande — sin red o sin proveedor, nada se rompe ni parpadea.
class IlustracionPichangol extends StatelessWidget {
  const IlustracionPichangol({
    super.key,
    required this.clave,
    required this.emoji,
    this.size = 120,
  });

  /// Clave del catálogo del backend (billetera_vacia, puntos_vacio,
  /// bodega_vacia, pedidos_vacio, cuentas_vacio, mensajes_vacio,
  /// reservas_vacias, clases_vacias, explorar_vacio, celebracion…).
  final String clave;

  /// Emoji de respaldo (y placeholder mientras carga).
  final String emoji;
  final double size;

  @override
  Widget build(BuildContext context) {
    final fallback = SizedBox(
      width: size,
      height: size,
      child: Center(
        child: Text(emoji, style: TextStyle(fontSize: size * 0.5)),
      ),
    );
    final url = SupabaseService.ilustracionPichangol(clave);
    if (url == null) return fallback;
    return ClipRRect(
      borderRadius: BorderRadius.circular(size * 0.15),
      child: CachedNetworkImage(
        imageUrl: url,
        width: size,
        height: size,
        fit: BoxFit.cover,
        fadeInDuration: const Duration(milliseconds: 150),
        placeholder: (_, __) => fallback,
        errorWidget: (_, __, ___) => fallback,
      ),
    );
  }
}

/// Estado vacío COMPLETO con la ilustración arriba y el mensaje debajo —
/// reemplaza los `Text` grises sueltos de "aún no hay nada" en un solo
/// widget consistente (título opcional + cuerpo tenue).
class VacioPichangol extends StatelessWidget {
  const VacioPichangol({
    super.key,
    required this.clave,
    required this.emoji,
    this.titulo,
    required this.mensaje,
    this.size = 120,
  });

  final String clave;
  final String emoji;
  final String? titulo;
  final String mensaje;
  final double size;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(32, 24, 32, 24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            IlustracionPichangol(clave: clave, emoji: emoji, size: size),
            const SizedBox(height: 14),
            if (titulo != null) ...[
              Text(titulo!,
                  textAlign: TextAlign.center,
                  style: const TextStyle(
                      fontWeight: FontWeight.w800, fontSize: 17)),
              const SizedBox(height: 6),
            ],
            Text(mensaje,
                textAlign: TextAlign.center,
                style: const TextStyle(color: textoTenue, height: 1.4)),
          ],
        ),
      ),
    );
  }
}
