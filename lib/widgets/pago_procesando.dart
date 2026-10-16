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
  // Loop de 1 sentido (no reverse): la tarjeta entra al POS una y otra vez.
  late final AnimationController _pulse = AnimationController(
      vsync: this, duration: const Duration(milliseconds: 1500))
    ..repeat();
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
            if (_fase == _Fase.procesando) ...[
              const SizedBox(height: 18),
              // Línea de progreso fina (indeterminada) — nada de círculos.
              const SizedBox(
                width: 150,
                child: ClipRRect(
                  borderRadius: BorderRadius.all(Radius.circular(99)),
                  child: LinearProgressIndicator(
                    minHeight: 4,
                    backgroundColor: Color(0xFFE9EFEC),
                    color: lima,
                  ),
                ),
              ),
            ],
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
        // POS "cobrando": la tarjeta entra al datáfono en bucle + ondas
        // contactless. Sin círculo ni spinner (estilo Airbnb Pay).
        return RepaintBoundary(
          child: AnimatedBuilder(
            animation: _pulse,
            builder: (_, __) => CustomPaint(
              size: const Size(150, 104),
              painter: _PosCobrandoPainter(_pulse.value),
            ),
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

/// Anima un DATÁFONO (POS) cobrando: la tarjeta baja y entra por la ranura en
/// bucle, con ondas "contactless" a un lado. Estilo Airbnb Pay: limpio, sin
/// círculos ni spinner. [t] ∈ [0,1] es el avance del bucle.
class _PosCobrandoPainter extends CustomPainter {
  _PosCobrandoPainter(this.t);
  final double t;

  double _lerp(double a, double b, double x) => a + (b - a) * x;
  double _ease(double x) {
    x = x.clamp(0.0, 1.0);
    return x < 0.5 ? 2 * x * x : 1 - (-2 * x + 2) * (-2 * x + 2) / 2;
  }

  @override
  void paint(Canvas canvas, Size size) {
    const cx = 60.0; // el POS va a la izquierda; las ondas a la derecha

    // ── Ondas contactless (detrás), emanando hacia el POS ──────────────────
    final ondaCentro = const Offset(112, 34);
    for (var i = 0; i < 3; i++) {
      final fase = ((t + i / 3) % 1.0);
      final r = _lerp(4, 20, fase);
      final alpha = (1 - fase) * 0.8;
      final p = Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = 2.4
        ..strokeCap = StrokeCap.round
        ..color = lima.withOpacity(alpha.clamp(0.0, 1.0));
      // Arco abierto hacia la izquierda (mirando al datáfono).
      canvas.drawArc(Rect.fromCircle(center: ondaCentro, radius: r),
          2.5, 1.3, false, p);
    }

    // ── Tarjeta (se dibuja ANTES que el POS: su base queda "dentro") ────────
    final slideT = _ease(t / 0.55);
    final cardTop = _lerp(-6, 22, slideT);
    double cardAlpha;
    if (t < 0.12) {
      cardAlpha = t / 0.12;
    } else if (t > 0.78) {
      cardAlpha = (1 - (t - 0.78) / 0.22).clamp(0.0, 1.0);
    } else {
      cardAlpha = 1;
    }
    final cardRect = Rect.fromLTWH(cx - 22, cardTop, 44, 28);
    final cardRR = RRect.fromRectAndRadius(cardRect, const Radius.circular(6));
    canvas.saveLayer(
        cardRect.inflate(2), Paint()..color = Colors.white.withOpacity(cardAlpha));
    final cardPaint = Paint()
      ..shader = const LinearGradient(
        begin: Alignment.topLeft,
        end: Alignment.bottomRight,
        colors: [bosque, lima],
      ).createShader(cardRect);
    canvas.drawRRect(cardRR, cardPaint);
    // Chip dorado + banda.
    canvas.drawRRect(
      RRect.fromRectAndRadius(
          Rect.fromLTWH(cardRect.left + 6, cardRect.top + 7, 8, 6),
          const Radius.circular(2)),
      Paint()..color = const Color(0xFFD9B45A),
    );
    canvas.drawRRect(
      RRect.fromRectAndRadius(
          Rect.fromLTWH(cardRect.left + 6, cardRect.top + 17, 32, 3),
          const Radius.circular(2)),
      Paint()..color = Colors.white.withOpacity(0.55),
    );
    canvas.restore();

    // ── Datáfono / POS (encima, tapa la base de la tarjeta) ─────────────────
    final body = RRect.fromRectAndRadius(
        Rect.fromLTWH(cx - 26, 42, 52, 58), const Radius.circular(13));
    // Sombra suave.
    canvas.drawRRect(body.shift(const Offset(0, 3)),
        Paint()..color = Colors.black.withOpacity(0.08));
    canvas.drawRRect(body, Paint()..color = bosque);
    // Ranura (slot) superior.
    canvas.drawRRect(
      RRect.fromRectAndRadius(
          Rect.fromLTWH(cx - 22, 39, 44, 6), const Radius.circular(3)),
      Paint()..color = Colors.black.withOpacity(0.35),
    );
    // Pantalla con 3 puntos "procesando" que se encienden en secuencia.
    final screen = Rect.fromLTWH(cx - 18, 52, 36, 18);
    canvas.drawRRect(
      RRect.fromRectAndRadius(screen, const Radius.circular(5)),
      Paint()..color = limaSuave,
    );
    final activo = (t * 3).floor() % 3;
    for (var i = 0; i < 3; i++) {
      canvas.drawCircle(
        Offset(screen.left + 10 + i * 8, screen.center.dy),
        2.4,
        Paint()..color = bosque.withOpacity(i == activo ? 1 : 0.25),
      );
    }
    // Teclado (puntitos).
    final tecla = Paint()..color = Colors.white.withOpacity(0.4);
    for (var r = 0; r < 2; r++) {
      for (var c = 0; c < 3; c++) {
        canvas.drawCircle(Offset(cx - 12 + c * 12, 80 + r * 10.0), 2.2, tecla);
      }
    }
  }

  @override
  bool shouldRepaint(_PosCobrandoPainter old) => old.t != t;
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
