import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';

import '../models/bodega.dart';
import '../services/supabase_service.dart';
import '../theme.dart';

/// Miniatura del producto de la bodega con CASCADA de imagen:
/// 1. FOTO REAL del dueño (siempre manda si existe).
/// 2. PACKSHOT IA genérico por tipo (sin marcas — legal y multi-país; lo
///    sirve el backend y se cachea en disco con CachedNetworkImage).
/// 3. EMOJI de siempre (sin red o si el packshot no está disponible).
class ImagenProductoBodega extends StatelessWidget {
  final ProductoBodega producto;
  final double lado;

  const ImagenProductoBodega(
      {super.key, required this.producto, this.lado = 44});

  @override
  Widget build(BuildContext context) {
    final radio = BorderRadius.circular(lado * 0.23);
    final emoji = Container(
      width: lado,
      height: lado,
      alignment: Alignment.center,
      decoration: BoxDecoration(color: limaSuave, borderRadius: radio),
      child: Text(producto.emoji, style: TextStyle(fontSize: lado * 0.5)),
    );
    final foto = (producto.fotoUrl ?? '').trim();
    final url = foto.isNotEmpty
        ? foto
        : SupabaseService.packshotBodega(producto.packshotTipo);
    if (url == null) return emoji;
    return ClipRRect(
      borderRadius: radio,
      child: CachedNetworkImage(
        imageUrl: url,
        width: lado,
        height: lado,
        fit: BoxFit.cover,
        fadeInDuration: const Duration(milliseconds: 120),
        placeholder: (_, __) => emoji,
        errorWidget: (_, __, ___) => emoji,
      ),
    );
  }
}
