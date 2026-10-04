import 'package:flutter/material.dart';

import '../theme.dart';
import 'logo_vivo.dart';

/// REGLA de la app: cuando una acción puede DEMORAR, se muestra SIEMPRE el
/// preload de marca (la pelota de Pichangol), nunca un spinner/círculo pelado.
/// [conPreload] ejecuta [accion] mostrando ese preload como overlay y lo cierra
/// al terminar (pase lo que pase). Devuelve el resultado de [accion].
///
/// Uso: `final r = await conPreload(context, () => servicio.algo(), texto: '…');`
Future<T> conPreload<T>(
  BuildContext context,
  Future<T> Function() accion, {
  String texto = 'Cargando…',
}) async {
  final nav = Navigator.of(context, rootNavigator: true);
  showDialog<void>(
    context: context,
    barrierDismissible: false,
    useRootNavigator: true,
    builder: (_) => PopScope(
      canPop: false,
      child: Dialog(
        backgroundColor: Colors.transparent,
        elevation: 0,
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 28),
          child: CargandoPichangol(texto: texto),
        ),
      ),
    ),
  );
  try {
    return await accion();
  } finally {
    if (nav.canPop()) nav.pop();
  }
}

/// Loader de marca (mini-splash) para los estados de PRELOAD: el LOGO NUEVO
/// "en vivo" — el pin quieto y la pelota de adentro cambiando de deporte como
/// un gif (mismo componente que el splash inicial) — en una tarjeta blanca
/// redondeada + el texto de carga. Reutilizable en cualquier pantalla.
class CargandoPichangol extends StatelessWidget {
  const CargandoPichangol({
    super.key,
    this.texto = 'Cargando…',
    this.conMarca = true,
  });

  /// Texto bajo el logo (p. ej. "Cargando tus canchas…").
  final String texto;

  /// Compat: el logo nuevo ya trae el wordmark impreso; en espacios chicos se
  /// reduce el tamaño en vez de ocultar la marca.
  final bool conMarca;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          // Tarjeta blanca redondeada (el asset del logo tiene fondo blanco):
          // se ve bien tanto sobre el fondo claro de una pantalla como
          // flotando sobre el velo oscuro del diálogo de conPreload.
          Container(
            clipBehavior: Clip.antiAlias,
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(28),
              boxShadow: const [
                BoxShadow(
                    color: Color(0x22000000),
                    blurRadius: 18,
                    offset: Offset(0, 8)),
              ],
            ),
            child: LogoPichangolVivo(ancho: conMarca ? 180 : 130),
          ),
          const SizedBox(height: 12),
          Text(texto,
              textAlign: TextAlign.center,
              style: TextStyle(
                  color: textoTenueDe(context),
                  fontWeight: FontWeight.w700,
                  fontSize: 13)),
        ],
      ),
    );
  }
}
