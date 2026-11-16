// ─────────────────────────────────────────────────────────────────────────
// CANCHALIBRE · Sistema de diseño (rediseño B1, oct-2026)
//
// Una sola fuente para espaciado, radios, tipografía y componentes. Las
// pantallas NUEVAS se arman solo con esto; las existentes migran de a poco.
// Reglas:
//   · Colores: SIEMPRE del ColorScheme o de los tokens de `theme.dart`
//     (nunca `Color(0x…)` suelto). Texto sobre blanco ≥ 4.5:1 (WCAG AA).
//   · Tipografía: los 7 estilos de [Tipo] (no `fontSize` sueltos).
//   · Espaciado: múltiplos de 4 ([Esp]). Radios: [Rad].
//   · Toque: todo lo interactivo mide ≥ 48 dp y lleva `Semantics`/tooltip.
//   · Estados: carga = [CLSkeleton], vacío = [CLVacio], error = [CLError].
// Compatible con Flutter 3.24.5 (sin `Color.withValues`).
// ─────────────────────────────────────────────────────────────────────────

import 'dart:async';

import 'package:flutter/material.dart';

import '../theme.dart';

/// Espaciado (grilla de 4).
abstract final class Esp {
  static const double x1 = 4, x2 = 8, x3 = 12, x4 = 16, x5 = 20, x6 = 24, x8 = 32, x10 = 40;

  /// Margen lateral de pantalla.
  static const EdgeInsets pantalla = EdgeInsets.symmetric(horizontal: x4);
}

/// Radios.
abstract final class Rad {
  static const double sm = 8, md = 12, lg = 16, xl = 24;
  static BorderRadius get rSm => BorderRadius.circular(sm);
  static BorderRadius get rMd => BorderRadius.circular(md);
  static BorderRadius get rLg => BorderRadius.circular(lg);
  static BorderRadius get rXl => BorderRadius.circular(xl);
}

/// Duraciones de animación.
abstract final class Dur {
  static const rapida = Duration(milliseconds: 150);
  static const normal = Duration(milliseconds: 240);
}

/// Escala tipográfica (7 pasos). Hereda la fuente del tema (DM Sans).
abstract final class Tipo {
  static TextStyle _b(BuildContext c) => Theme.of(c).textTheme.bodyMedium ?? const TextStyle();
  static Color _tx(BuildContext c) => Theme.of(c).colorScheme.onSurface;

  /// Cifras grandes y títulos de pantalla.
  static TextStyle display(BuildContext c) =>
      _b(c).copyWith(fontSize: 28, height: 1.15, fontWeight: FontWeight.w700, letterSpacing: -0.4, color: _tx(c));
  static TextStyle titulo(BuildContext c) =>
      _b(c).copyWith(fontSize: 20, height: 1.25, fontWeight: FontWeight.w700, letterSpacing: -0.2, color: _tx(c));
  static TextStyle subtitulo(BuildContext c) =>
      _b(c).copyWith(fontSize: 16, height: 1.3, fontWeight: FontWeight.w600, color: _tx(c));
  static TextStyle cuerpo(BuildContext c) => _b(c).copyWith(fontSize: 15, height: 1.45, color: _tx(c));
  static TextStyle detalle(BuildContext c) =>
      _b(c).copyWith(fontSize: 13.5, height: 1.4, color: textoTenueDe(c));
  static TextStyle etiqueta(BuildContext c) =>
      _b(c).copyWith(fontSize: 13, height: 1.2, fontWeight: FontWeight.w600, color: _tx(c));
  static TextStyle micro(BuildContext c) =>
      _b(c).copyWith(fontSize: 12, height: 1.2, fontWeight: FontWeight.w600, letterSpacing: 0.2, color: textoTenueDe(c));
}

bool _oscuro(BuildContext c) => Theme.of(c).brightness == Brightness.dark;

Color _borde(BuildContext c) => _oscuro(c) ? const Color(0xFF2A3A4E) : trazo;

// ── Botones ──────────────────────────────────────────────────────────────

enum CLBotonTipo { primario, secundario, texto, peligro }

/// Botón de la marca: alto mínimo 52 (grande) / 48, estado de carga y ancho
/// completo opcional. El texto es la etiqueta accesible.
class CLBoton extends StatelessWidget {
  const CLBoton({
    super.key,
    required this.texto,
    required this.onPressed,
    this.tipo = CLBotonTipo.primario,
    this.icono,
    this.cargando = false,
    this.expandido = true,
    this.grande = true,
  });

  final String texto;
  final VoidCallback? onPressed;
  final CLBotonTipo tipo;
  final IconData? icono;
  final bool cargando;
  final bool expandido;
  final bool grande;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final alto = grande ? 52.0 : 48.0;
    final accion = cargando ? null : onPressed;
    final hijo = cargando
        ? SizedBox(
            width: 22,
            height: 22,
            child: CircularProgressIndicator(
              strokeWidth: 2.4,
              color: tipo == CLBotonTipo.primario || tipo == CLBotonTipo.peligro ? Colors.white : cs.primary,
            ),
          )
        : Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (icono != null) ...[Icon(icono, size: 20), const SizedBox(width: Esp.x2)],
              Flexible(child: Text(texto, overflow: TextOverflow.ellipsis)),
            ],
          );
    final forma = RoundedRectangleBorder(borderRadius: Rad.rMd);
    final estilo = Tipo.subtitulo(context).copyWith(fontSize: 15.5);
    final Widget b = switch (tipo) {
      CLBotonTipo.primario => FilledButton(
          onPressed: accion,
          style: FilledButton.styleFrom(minimumSize: Size(0, alto), shape: forma, textStyle: estilo),
          child: hijo),
      CLBotonTipo.peligro => FilledButton(
          onPressed: accion,
          style: FilledButton.styleFrom(
              backgroundColor: estadoBadFg, minimumSize: Size(0, alto), shape: forma, textStyle: estilo),
          child: hijo),
      CLBotonTipo.secundario => OutlinedButton(
          onPressed: accion,
          style: OutlinedButton.styleFrom(
              minimumSize: Size(0, alto),
              shape: forma,
              textStyle: estilo,
              side: BorderSide(color: _borde(context), width: 1.4)),
          child: hijo),
      CLBotonTipo.texto => TextButton(
          onPressed: accion,
          style: TextButton.styleFrom(minimumSize: Size(0, alto), shape: forma, textStyle: estilo),
          child: hijo),
    };
    return Semantics(
      button: true,
      enabled: accion != null,
      label: cargando ? '$texto, procesando' : texto,
      excludeSemantics: true,
      child: expandido ? SizedBox(width: double.infinity, child: b) : b,
    );
  }
}

// ── Superficies ──────────────────────────────────────────────────────────

/// Tarjeta: borde fino, radio grande, sin sombra pesada. Con [onTap] es un
/// botón accesible ([semantica] = qué hace).
class CLTarjeta extends StatelessWidget {
  const CLTarjeta({
    super.key,
    required this.child,
    this.onTap,
    this.semantica,
    this.padding = const EdgeInsets.all(Esp.x4),
    this.destacada = false,
  });

  final Widget child;
  final VoidCallback? onTap;
  final String? semantica;
  final EdgeInsets padding;
  final bool destacada;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final cuerpo = Padding(padding: padding, child: child);
    final caja = Material(
      color: destacada ? cs.primary.withOpacity(_oscuro(context) ? 0.16 : 0.07) : cs.surface,
      shape: RoundedRectangleBorder(
        borderRadius: Rad.rLg,
        side: BorderSide(color: destacada ? cs.primary.withOpacity(0.35) : _borde(context)),
      ),
      clipBehavior: Clip.antiAlias,
      child: onTap == null ? cuerpo : InkWell(onTap: onTap, child: cuerpo),
    );
    if (onTap == null) return caja;
    return Semantics(button: true, label: semantica, child: caja);
  }
}

/// Encabezado de sección: título, bajada opcional y acción a la derecha.
class CLSeccion extends StatelessWidget {
  const CLSeccion({super.key, required this.titulo, this.bajada, this.accion});

  final String titulo;
  final String? bajada;
  final Widget? accion;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: Esp.x6, bottom: Esp.x3),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Semantics(header: true, child: Text(titulo, style: Tipo.subtitulo(context).copyWith(fontSize: 17))),
                if (bajada != null) ...[
                  const SizedBox(height: Esp.x1),
                  Text(bajada!, style: Tipo.detalle(context)),
                ],
              ],
            ),
          ),
          if (accion != null) ...[const SizedBox(width: Esp.x2), accion!],
        ],
      ),
    );
  }
}

/// Fila "etiqueta ······ valor" (resúmenes, comprobantes).
class CLFila extends StatelessWidget {
  const CLFila({super.key, required this.etiqueta, required this.valor, this.fuerte = false});

  final String etiqueta;
  final String valor;
  final bool fuerte;

  @override
  Widget build(BuildContext context) {
    final st = fuerte ? Tipo.subtitulo(context) : Tipo.cuerpo(context);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: Esp.x1 + 2),
      child: Row(
        children: [
          Expanded(child: Text(etiqueta, style: fuerte ? st : Tipo.detalle(context).copyWith(fontSize: 14.5))),
          const SizedBox(width: Esp.x3),
          Text(valor, style: st),
        ],
      ),
    );
  }
}

// ── Estados ──────────────────────────────────────────────────────────────

enum CLTono { ok, aviso, error, info, neutro }

({Color bg, Color fg, IconData icono}) _tono(CLTono t) => switch (t) {
      CLTono.ok => (bg: estadoOkBg, fg: estadoOkFg, icono: Icons.check_circle_rounded),
      CLTono.aviso => (bg: estadoWarnBg, fg: estadoWarnFg, icono: Icons.schedule_rounded),
      CLTono.error => (bg: estadoBadBg, fg: estadoBadFg, icono: Icons.error_rounded),
      CLTono.info => (bg: estadoInfoBg, fg: estadoInfoFg, icono: Icons.info_rounded),
      CLTono.neutro => (bg: estadoNeutroBg, fg: estadoNeutroFg, icono: Icons.circle_outlined),
    };

/// Insignia de estado (reserva, pago, voucher). Lleva ícono además del color
/// (no depender solo del color: daltonismo).
class CLInsignia extends StatelessWidget {
  const CLInsignia({super.key, required this.texto, required this.tono, this.icono});

  final String texto;
  final CLTono tono;
  final IconData? icono;

  @override
  Widget build(BuildContext context) {
    final t = _tono(tono);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: Esp.x2 + 2, vertical: Esp.x1 + 1),
      decoration: BoxDecoration(color: t.bg, borderRadius: BorderRadius.circular(100)),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icono ?? t.icono, size: 14, color: t.fg),
          const SizedBox(width: Esp.x1),
          Text(texto, style: Tipo.micro(context).copyWith(color: t.fg)),
        ],
      ),
    );
  }
}

/// Aviso en línea (banner) con tono.
class CLAviso extends StatelessWidget {
  const CLAviso({super.key, required this.texto, this.titulo, this.tono = CLTono.info, this.accion});

  final String? titulo;
  final String texto;
  final CLTono tono;
  final Widget? accion;

  @override
  Widget build(BuildContext context) {
    final t = _tono(tono);
    return Semantics(
      container: true,
      liveRegion: tono == CLTono.error,
      child: Container(
        padding: const EdgeInsets.all(Esp.x3 + 2),
        decoration: BoxDecoration(color: t.bg, borderRadius: Rad.rMd),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(t.icono, color: t.fg, size: 20),
            const SizedBox(width: Esp.x3),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  if (titulo != null)
                    Text(titulo!, style: Tipo.etiqueta(context).copyWith(color: t.fg, fontSize: 14)),
                  Text(texto, style: Tipo.detalle(context).copyWith(color: t.fg)),
                  if (accion != null) Padding(padding: const EdgeInsets.only(top: Esp.x2), child: accion),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Estado vacío: ícono, título, mensaje y CTA opcional.
class CLVacio extends StatelessWidget {
  const CLVacio({super.key, required this.icono, required this.titulo, required this.mensaje, this.cta, this.onCta});

  final IconData icono;
  final String titulo;
  final String mensaje;
  final String? cta;
  final VoidCallback? onCta;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Center(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: Esp.x8, vertical: Esp.x10),
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 420),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                width: 72,
                height: 72,
                decoration: BoxDecoration(color: cs.primary.withOpacity(0.08), shape: BoxShape.circle),
                child: Icon(icono, size: 34, color: cs.primary),
              ),
              const SizedBox(height: Esp.x5),
              Text(titulo, textAlign: TextAlign.center, style: Tipo.titulo(context).copyWith(fontSize: 18)),
              const SizedBox(height: Esp.x2),
              Text(mensaje, textAlign: TextAlign.center, style: Tipo.detalle(context).copyWith(fontSize: 14.5)),
              if (cta != null && onCta != null) ...[
                const SizedBox(height: Esp.x6),
                CLBoton(texto: cta!, onPressed: onCta, expandido: false, tipo: CLBotonTipo.secundario),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

/// Estado de error con reintento.
class CLError extends StatelessWidget {
  const CLError({super.key, required this.mensaje, this.onReintentar});

  final String mensaje;
  final VoidCallback? onReintentar;

  @override
  Widget build(BuildContext context) => CLVacio(
        icono: Icons.wifi_off_rounded,
        titulo: 'No pudimos cargar esto',
        mensaje: mensaje,
        cta: onReintentar == null ? null : 'Reintentar',
        onCta: onReintentar,
      );
}

/// Bloque de carga (skeleton) que late suave. Para listas: [CLSkeleton.lista].
class CLSkeleton extends StatefulWidget {
  const CLSkeleton({super.key, this.alto = 16, this.ancho, this.radio = Rad.sm});

  final double alto;
  final double? ancho;
  final double radio;

  /// N tarjetas de carga (lista típica).
  static Widget lista({int n = 4, double alto = 84}) => Semantics(
        label: 'Cargando',
        child: Column(
          children: [
            for (var i = 0; i < n; i++)
              Padding(
                padding: const EdgeInsets.only(bottom: Esp.x3),
                child: CLSkeleton(alto: alto, radio: Rad.lg),
              ),
          ],
        ),
      );

  @override
  State<CLSkeleton> createState() => _CLSkeletonState();
}

class _CLSkeletonState extends State<CLSkeleton> with SingleTickerProviderStateMixin {
  late final AnimationController _c =
      AnimationController(vsync: this, duration: const Duration(milliseconds: 900))..repeat(reverse: true);

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final base = _oscuro(context) ? const Color(0xFF1B2A3C) : const Color(0xFFE9EEF4);
    return FadeTransition(
      opacity: Tween(begin: 0.55, end: 1.0).animate(_c),
      child: Container(
        height: widget.alto,
        width: widget.ancho ?? double.infinity,
        decoration: BoxDecoration(color: base, borderRadius: BorderRadius.circular(widget.radio)),
      ),
    );
  }
}

// ── Dinero y tiempo ──────────────────────────────────────────────────────

/// Monto con su moneda (S/, $, Bs — nunca "S/" fijo: multi-país).
class CLPrecio extends StatelessWidget {
  const CLPrecio({super.key, required this.monto, required this.moneda, this.unidad, this.grande = false});

  final num monto;
  final String moneda;
  final String? unidad;
  final bool grande;

  @override
  Widget build(BuildContext context) {
    final st = grande ? Tipo.display(context) : Tipo.subtitulo(context);
    final txt = monto == monto.roundToDouble() ? monto.toStringAsFixed(0) : monto.toStringAsFixed(2);
    return Semantics(
      label: '$moneda $txt${unidad == null ? '' : ' $unidad'}',
      excludeSemantics: true,
      child: Text.rich(TextSpan(children: [
        TextSpan(text: '$moneda $txt', style: st),
        if (unidad != null) TextSpan(text: ' $unidad', style: Tipo.detalle(context)),
      ])),
    );
  }
}

/// Cuenta regresiva hasta [vence] (apartados, vouchers). Llama [alVencer] una vez.
class CLTemporizador extends StatefulWidget {
  const CLTemporizador({super.key, required this.vence, this.prefijo = 'Tu horario está apartado por', this.alVencer});

  final DateTime vence;
  final String prefijo;
  final VoidCallback? alVencer;

  @override
  State<CLTemporizador> createState() => _CLTemporizadorState();
}

class _CLTemporizadorState extends State<CLTemporizador> {
  Timer? _t;
  bool _avisado = false;

  @override
  void initState() {
    super.initState();
    _t = Timer.periodic(const Duration(seconds: 1), (_) {
      if (!mounted) return;
      setState(() {});
      if (!_avisado && DateTime.now().isAfter(widget.vence)) {
        _avisado = true;
        widget.alVencer?.call();
      }
    });
  }

  @override
  void dispose() {
    _t?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final resta = widget.vence.difference(DateTime.now());
    final s = resta.isNegative ? 0 : resta.inSeconds;
    final mm = (s ~/ 60).toString().padLeft(2, '0');
    final ss = (s % 60).toString().padLeft(2, '0');
    final urgente = s < 120;
    return CLAviso(
      tono: urgente ? CLTono.aviso : CLTono.info,
      texto: s == 0 ? 'El apartado venció. Vuelve a elegir tu horario.' : '${widget.prefijo} $mm:$ss',
    );
  }
}

// ── Formularios ──────────────────────────────────────────────────────────

/// Campo de texto de la marca (etiqueta arriba, ayuda y error debajo).
class CLCampo extends StatelessWidget {
  const CLCampo({
    super.key,
    required this.etiqueta,
    this.controller,
    this.ayuda,
    this.error,
    this.teclado,
    this.oculto = false,
    this.maxLength,
    this.onChanged,
    this.prefijo,
  });

  final String etiqueta;
  final TextEditingController? controller;
  final String? ayuda;
  final String? error;
  final TextInputType? teclado;
  final bool oculto;
  final int? maxLength;
  final ValueChanged<String>? onChanged;
  final String? prefijo;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: Esp.x4),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(etiqueta, style: Tipo.etiqueta(context)),
          const SizedBox(height: Esp.x2),
          TextField(
            controller: controller,
            keyboardType: teclado,
            obscureText: oculto,
            maxLength: maxLength,
            onChanged: onChanged,
            style: Tipo.cuerpo(context),
            decoration: InputDecoration(
              helperText: ayuda,
              helperMaxLines: 3,
              errorMaxLines: 3,
              errorText: error,
              counterText: '',
              prefixText: prefijo,
              isDense: true,
              contentPadding: const EdgeInsets.symmetric(horizontal: Esp.x4, vertical: Esp.x3 + 2),
              border: OutlineInputBorder(borderRadius: Rad.rMd),
              enabledBorder: OutlineInputBorder(borderRadius: Rad.rMd, borderSide: BorderSide(color: _borde(context))),
            ),
          ),
        ],
      ),
    );
  }
}

/// Hoja inferior estándar (manija, título, contenido con scroll y teclado).
Future<T?> mostrarHojaCL<T>(BuildContext context, {required String titulo, required Widget Function(BuildContext) contenido}) {
  return showModalBottomSheet<T>(
    context: context,
    isScrollControlled: true,
    useSafeArea: true,
    showDragHandle: true,
    shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(Rad.xl))),
    builder: (ctx) => Padding(
      padding: EdgeInsets.only(bottom: MediaQuery.of(ctx).viewInsets.bottom),
      child: SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(Esp.x5, 0, Esp.x5, Esp.x6),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Semantics(header: true, child: Text(titulo, style: Tipo.titulo(ctx))),
            const SizedBox(height: Esp.x4),
            contenido(ctx),
          ],
        ),
      ),
    ),
  );
}
