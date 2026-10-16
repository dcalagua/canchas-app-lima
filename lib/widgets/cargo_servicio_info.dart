import 'package:flutter/material.dart';

import '../models/cargo_servicio.dart';
import '../theme.dart';
import 'dialogo_pichangol.dart';

/// Línea "Cargo por servicio Pichangol ⓘ · S/ x" del checkout (reserva,
/// matrícula, Mi familia). El ⓘ abre el desglose con el MISMO formato de
/// popup de toda la app (`DialogoPichangol`). Con [cot] nulo o sin cargo no
/// pinta nada: así, con la línea apagada en la torre, el checkout no cambia.
class FilaCargoServicio extends StatelessWidget {
  const FilaCargoServicio({
    super.key,
    required this.cot,
    this.simbolo,
    this.nota,
    this.compacta = false,
  });

  final CotizacionCargo? cot;

  /// Símbolo de la moneda a mostrar (por defecto el de la cotización).
  final String? simbolo;

  /// Texto chico bajo la línea (p. ej. "Ahorras S/ 2.10 pagando en familia").
  final String? nota;

  final bool compacta;

  @override
  Widget build(BuildContext context) {
    final c = cot;
    if (c == null || !c.hayCargo) return const SizedBox.shrink();
    final t = Theme.of(context).textTheme;
    final mon = simbolo ?? c.simbolo;
    return Padding(
      padding: EdgeInsets.symmetric(vertical: compacta ? 2 : 6),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Row(
                  children: [
                    Flexible(
                      child: Text(c.titulo,
                          style: t.bodyMedium?.copyWith(
                              fontWeight: FontWeight.w600, height: 1.2)),
                    ),
                    const SizedBox(width: 4),
                    InkWell(
                      borderRadius: BorderRadius.circular(12),
                      onTap: () => mostrarDesgloseCargo(context, c, simbolo: mon),
                      child: const Padding(
                        padding: EdgeInsets.all(4),
                        child: Icon(Icons.info_outline,
                            size: 18, color: textoTenue),
                      ),
                    ),
                  ],
                ),
              ),
              Text('$mon ${c.cargo.toStringAsFixed(2)}',
                  style: t.bodyMedium?.copyWith(fontWeight: FontWeight.w700)),
            ],
          ),
          if ((nota ?? '').isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(top: 2),
              child: Text(nota!,
                  style: t.bodySmall?.copyWith(
                      color: bosque, fontWeight: FontWeight.w700, height: 1.2)),
            ),
        ],
      ),
    );
  }
}

/// Cotiza desde `build()` sin parpadeos: devuelve al instante la cotización
/// conocida (caché del servidor o regla local) y, si la base cambió, pide la
/// del servidor en segundo plano; cuando llega y difiere, llama [onCambio]
/// (un `setState`/`notifyListeners`) para repintar con el valor definitivo.
class CotizadorCargo {
  CotizadorCargo(this.onCambio);
  final VoidCallback onCambio;
  String _clave = '';
  CotizacionCargo? _cot;

  CotizacionCargo? para({
    required String linea,
    required String moneda,
    required int baseCentimos,
    String deporte = '',
    List<int> partes = const [],
  }) {
    if (!CargoServicio.activo(linea) || baseCentimos <= 0) {
      _clave = '';
      _cot = null;
      return null;
    }
    final clave = '$linea|$moneda|$baseCentimos|$deporte|${partes.join(',')}';
    if (clave == _clave) return _cot;
    _clave = clave;
    _cot = CargoServicio.inmediata(
        linea: linea,
        moneda: moneda,
        baseCentimos: baseCentimos,
        deporte: deporte,
        partes: partes);
    if (!(_cot?.delServidor ?? false)) {
      CargoServicio.cotizar(
              linea: linea,
              moneda: moneda,
              baseCentimos: baseCentimos,
              deporte: deporte,
              partes: partes)
          .then((c) {
        if (_clave != clave) return;
        final antes = _cot;
        if (antes == null ||
            antes.cargoCentimos != c.cargoCentimos ||
            antes.delServidor != c.delServidor) {
          _cot = c;
          onCambio();
        }
      });
    }
    return _cot;
  }
}

/// Popup con el desglose del cargo (qué incluye, cuánto de cada parte y la
/// regla), en el formato único de la app.
Future<void> mostrarDesgloseCargo(BuildContext context, CotizacionCargo cot,
    {String? simbolo}) {
  final mon = simbolo ?? cot.simbolo;
  return showDialog<void>(
    context: context,
    builder: (ctx) {
      final t = Theme.of(ctx).textTheme;
      return DialogoPichangol(
        titulo: cot.titulo,
        icono: Icons.verified_user_outlined,
        contenido: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            for (final x in cot.desglose) ...[
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(x.nombre,
                            style: t.bodyMedium
                                ?.copyWith(fontWeight: FontWeight.w800)),
                        if (x.detalle.isNotEmpty)
                          Text(x.detalle,
                              style: t.bodySmall
                                  ?.copyWith(color: textoTenue, height: 1.3)),
                      ],
                    ),
                  ),
                  const SizedBox(width: 10),
                  Text('$mon ${x.monto.toStringAsFixed(2)}',
                      style:
                          t.bodyMedium?.copyWith(fontWeight: FontWeight.w800)),
                ],
              ),
              const SizedBox(height: 8),
              const Divider(height: 1, color: trazo),
              const SizedBox(height: 8),
            ],
            Text(
              '${cot.regla.isNotEmpty ? '${cot.regla}. ' : ''}'
              'El precio va completo al ${cot.linea == 'academias' ? 'a la academia' : 'local'}, '
              'menos su comisión; este cargo es lo que cobra Pichangol por el servicio.',
              style: t.bodySmall?.copyWith(color: textoTenue, height: 1.3),
            ),
            if (cot.ahorroCentimos > 0) ...[
              const SizedBox(height: 8),
              Text(
                  '🎉 Un solo cargo por todo el pago: ahorras $mon '
                  '${cot.ahorro.toStringAsFixed(2)} frente a pagar por separado.',
                  style: t.bodySmall
                      ?.copyWith(color: bosque, fontWeight: FontWeight.w700)),
            ],
          ],
        ),
        acciones: [
          FilledButton(
            style: FilledButton.styleFrom(
                backgroundColor: lima,
                foregroundColor: Colors.white,
                shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(12)),
                padding:
                    const EdgeInsets.symmetric(horizontal: 22, vertical: 12)),
            onPressed: () => Navigator.of(ctx).pop(),
            child: const Text('Entendido',
                style: TextStyle(fontWeight: FontWeight.w800)),
          ),
        ],
      );
    },
  );
}
