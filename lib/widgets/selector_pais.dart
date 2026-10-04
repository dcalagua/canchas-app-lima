import 'package:flutter/material.dart';

import '../config/pais.dart';
import '../theme.dart';

/// Fila de chips de PAÍS (bandera + nombre), estilo Airbnb: blancas con borde
/// suave, la elegida en gris plomo. Es el ÚNICO selector de país de la app
/// (bienvenida, banner de Explorar, "Mi país" en Perfil): un solo formato.
class SelectorPais extends StatelessWidget {
  const SelectorPais({
    super.key,
    required this.seleccion,
    required this.onElegir,
    this.compacto = false,
  });

  /// ISO del país seleccionado ('PE' | 'BO' | 'EC').
  final String seleccion;
  final ValueChanged<PaisConfig> onElegir;
  final bool compacto;

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: 10,
      runSpacing: 10,
      alignment: WrapAlignment.center,
      children: [
        for (final p in paisesSoportados.values)
          _ChipPais(
            pais: p,
            sel: p.iso == seleccion,
            compacto: compacto,
            onTap: () => onElegir(p),
          ),
      ],
    );
  }
}

class _ChipPais extends StatelessWidget {
  const _ChipPais({
    required this.pais,
    required this.sel,
    required this.onTap,
    required this.compacto,
  });
  final PaisConfig pais;
  final bool sel;
  final VoidCallback onTap;
  final bool compacto;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: sel ? const Color(0xFFEBEBEB) : Colors.white,
      borderRadius: BorderRadius.circular(22),
      elevation: sel ? 0 : 1,
      shadowColor: const Color(0x0F000000),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(22),
        child: Container(
          padding: EdgeInsets.symmetric(
              horizontal: compacto ? 12 : 18, vertical: compacto ? 8 : 12),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(22),
            border: Border.all(
                color: sel ? const Color(0xFFD6D6D6) : const Color(0xFFE4E4E4)),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(pais.bandera,
                  style: TextStyle(fontSize: compacto ? 16 : 20)),
              const SizedBox(width: 8),
              Text(pais.nombre,
                  style: TextStyle(
                      fontSize: compacto ? 13.5 : 15,
                      fontWeight: FontWeight.w700,
                      color: const Color(0xFF222222))),
              if (sel) ...[
                const SizedBox(width: 6),
                const Icon(Icons.check_rounded, size: 18, color: bosque),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

/// Hoja inferior para elegir país. Devuelve el país elegido o null si cerró.
Future<PaisConfig?> elegirPaisSheet(
  BuildContext context, {
  required String actualIso,
  required String titulo,
  String? mensaje,
}) {
  return showModalBottomSheet<PaisConfig>(
    context: context,
    backgroundColor: Colors.white,
    shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(24))),
    builder: (ctx) => SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(22, 18, 22, 26),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Center(
              child: Container(
                width: 38,
                height: 5,
                margin: const EdgeInsets.only(bottom: 18),
                decoration: BoxDecoration(
                    color: const Color(0xFFD8D3C6),
                    borderRadius: BorderRadius.circular(3)),
              ),
            ),
            Text(titulo,
                style: const TextStyle(
                    fontSize: 19,
                    fontWeight: FontWeight.w800,
                    color: Color(0xFF222222))),
            if (mensaje != null) ...[
              const SizedBox(height: 6),
              Text(mensaje,
                  style: const TextStyle(
                      fontSize: 13.5, color: textoTenue, height: 1.4)),
            ],
            const SizedBox(height: 18),
            SelectorPais(
              seleccion: actualIso,
              onElegir: (p) => Navigator.of(ctx).pop(p),
            ),
          ],
        ),
      ),
    ),
  );
}
