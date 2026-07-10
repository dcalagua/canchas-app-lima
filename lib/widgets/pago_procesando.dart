import 'package:flutter/material.dart';

import '../theme.dart';

enum _Fase { procesando, exito, error }

/// Caja de pago "cobrándose" (estilo Airbnb): ejecuta [accion] (tokenizar +
/// cobrar), muestra una animación de procesando y luego el resultado (check de
/// éxito o error). Devuelve `true` por Navigator.pop si el pago fue exitoso.
///
/// Uso:
/// ```dart
/// final ok = await PagoProcesando.mostrar(context,
///     titulo: 'Recargando S/ 50', accion: () async { ... return {'ok': true}; });
/// ```
class PagoProcesando extends StatefulWidget {
  const PagoProcesando({
    super.key,
    required this.titulo,
    required this.accion,
    this.exitoTitulo = '¡Pago aprobado!',
    this.exitoDetalle = '',
  });

  final String titulo;
  final String exitoTitulo;
  final String exitoDetalle;

  /// Debe devolver {'ok': bool, 'error': String?, 'detalle': String?}.
  final Future<Map<String, dynamic>> Function() accion;

  static Future<bool?> mostrar(
    BuildContext context, {
    required String titulo,
    required Future<Map<String, dynamic>> Function() accion,
    String exitoTitulo = '¡Pago aprobado!',
    String exitoDetalle = '',
  }) {
    return showDialog<bool>(
      context: context,
      barrierDismissible: false,
      builder: (_) => PagoProcesando(
        titulo: titulo,
        accion: accion,
        exitoTitulo: exitoTitulo,
        exitoDetalle: exitoDetalle,
      ),
    );
  }

  @override
  State<PagoProcesando> createState() => _PagoProcesandoState();
}

class _PagoProcesandoState extends State<PagoProcesando>
    with SingleTickerProviderStateMixin {
  late final AnimationController _pulse = AnimationController(
      vsync: this, duration: const Duration(milliseconds: 900))
    ..repeat(reverse: true);
  _Fase _fase = _Fase.procesando;
  String _detalle = '';

  @override
  void initState() {
    super.initState();
    _ejecutar();
  }

  Future<void> _ejecutar() async {
    final r = await widget.accion();
    if (!mounted) return;
    setState(() {
      if (r['ok'] == true) {
        _fase = _Fase.exito;
        _detalle = (r['detalle'] as String?)?.isNotEmpty == true
            ? r['detalle'] as String
            : widget.exitoDetalle;
      } else {
        _fase = _Fase.error;
        _detalle = (r['error'] as String?) ?? 'No se pudo procesar el pago.';
      }
    });
    _pulse.stop();
  }

  @override
  void dispose() {
    _pulse.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Dialog(
      backgroundColor: Colors.white,
      insetPadding: const EdgeInsets.symmetric(horizontal: 36),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(24)),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(24, 30, 24, 22),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            _icono(),
            const SizedBox(height: 20),
            Text(
              _fase == _Fase.procesando
                  ? widget.titulo
                  : _fase == _Fase.exito
                      ? widget.exitoTitulo
                      : 'No se completó el pago',
              textAlign: TextAlign.center,
              style: const TextStyle(
                  fontSize: 19, fontWeight: FontWeight.w800, color: tinta),
            ),
            const SizedBox(height: 8),
            Text(
              _fase == _Fase.procesando
                  ? 'Pago seguro procesado por Culqi…'
                  : _detalle,
              textAlign: TextAlign.center,
              style: const TextStyle(color: textoTenue, fontSize: 14, height: 1.35),
            ),
            if (_fase != _Fase.procesando) ...[
              const SizedBox(height: 22),
              SizedBox(
                width: double.infinity,
                child: FilledButton(
                  style: FilledButton.styleFrom(
                      backgroundColor: _fase == _Fase.exito ? pino : trazo,
                      foregroundColor:
                          _fase == _Fase.exito ? lima : tinta,
                      padding: const EdgeInsets.symmetric(vertical: 14)),
                  onPressed: () =>
                      Navigator.of(context).pop(_fase == _Fase.exito),
                  child: Text(_fase == _Fase.exito ? 'Listo' : 'Reintentar'),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _icono() {
    switch (_fase) {
      case _Fase.procesando:
        // Tarjeta "latiendo" + spinner alrededor.
        return SizedBox(
          width: 92,
          height: 92,
          child: Stack(
            alignment: Alignment.center,
            children: [
              SizedBox(
                width: 92,
                height: 92,
                child: CircularProgressIndicator(
                    strokeWidth: 3, color: bosque.withOpacity(0.85)),
              ),
              ScaleTransition(
                scale: Tween(begin: 0.86, end: 1.0).animate(
                    CurvedAnimation(parent: _pulse, curve: Curves.easeInOut)),
                child: Container(
                  width: 56,
                  height: 56,
                  decoration: BoxDecoration(
                      color: limaSuave, shape: BoxShape.circle),
                  child: const Icon(Icons.payments_rounded,
                      color: bosque, size: 28),
                ),
              ),
            ],
          ),
        );
      case _Fase.exito:
        return _CirculoResultado(
            color: const Color(0xFF1E9E5A), icono: Icons.check_rounded);
      case _Fase.error:
        return _CirculoResultado(
            color: const Color(0xFFC0392B), icono: Icons.close_rounded);
    }
  }
}

/// Círculo de resultado con el ícono que crece (scale-in) al aparecer.
class _CirculoResultado extends StatelessWidget {
  const _CirculoResultado({required this.color, required this.icono});
  final Color color;
  final IconData icono;

  @override
  Widget build(BuildContext context) {
    return TweenAnimationBuilder<double>(
      tween: Tween(begin: 0, end: 1),
      duration: const Duration(milliseconds: 380),
      curve: Curves.elasticOut,
      builder: (_, v, __) => Transform.scale(
        scale: v.clamp(0.0, 1.0),
        child: Container(
          width: 84,
          height: 84,
          decoration: BoxDecoration(
              color: color.withOpacity(0.12), shape: BoxShape.circle),
          child: Center(
            child: Container(
              width: 58,
              height: 58,
              decoration: BoxDecoration(color: color, shape: BoxShape.circle),
              child: Icon(icono, color: Colors.white, size: 34),
            ),
          ),
        ),
      ),
    );
  }
}
