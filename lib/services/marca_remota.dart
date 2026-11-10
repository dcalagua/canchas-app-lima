import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// LOGO DE LA MARCA configurable en la torre (20-oct-2026). El backend lo
/// publica en `GET /config/canal` (`marca_logo_url`; vacío = el que trae el
/// APK). Cache-first: la última URL vive en SharedPreferences y la imagen en
/// la caché de disco de `CachedNetworkImage`, así el logo nuevo sale al
/// instante en cada arranque. El ícono del celular y el splash nativo van
/// compilados en el APK y no cambian con esto.
class MarcaRemota {
  MarcaRemota._();

  static const _clave = 'marca_logo_url';

  /// URL del logo propio ('' = usar el asset del APK).
  static final ValueNotifier<String> logoUrl = ValueNotifier<String>('');

  static Future<void> cargarCache() async {
    try {
      final p = await SharedPreferences.getInstance();
      logoUrl.value = p.getString(_clave) ?? '';
    } catch (_) {}
  }

  /// Con la respuesta de `/config/canal`.
  static Future<void> actualizar(Map j) async {
    if (!j.containsKey('marca_logo_url')) return; // backend viejo: no tocar
    final u = (j['marca_logo_url'] ?? '').toString().trim();
    if (u == logoUrl.value) return;
    logoUrl.value = u;
    try {
      final p = await SharedPreferences.getInstance();
      await p.setString(_clave, u);
    } catch (_) {}
  }
}

/// Imagen del logo: el propio de la torre si hay, si no [asset].
class LogoMarcaImagen extends StatelessWidget {
  const LogoMarcaImagen({
    super.key,
    this.asset = 'assets/brand/logo_pin.png',
    this.width,
    this.height,
    this.fit = BoxFit.contain,
    this.error,
  });

  final String asset;
  final double? width;
  final double? height;
  final BoxFit fit;
  final Widget? error;

  Widget _asset() => Image.asset(
        asset,
        width: width,
        height: height,
        fit: fit,
        filterQuality: FilterQuality.medium,
        errorBuilder: (_, __, ___) =>
            error ?? SizedBox(width: width, height: height),
      );

  @override
  Widget build(BuildContext context) {
    return ValueListenableBuilder<String>(
      valueListenable: MarcaRemota.logoUrl,
      builder: (_, url, __) {
        if (url.isEmpty) return _asset();
        return CachedNetworkImage(
          imageUrl: url,
          width: width,
          height: height,
          fit: fit,
          filterQuality: FilterQuality.medium,
          // Sin el logo viejo de relleno: no queremos que "parpadee" la marca anterior.
          placeholder: (_, __) => SizedBox(width: width, height: height),
          errorWidget: (_, __, ___) => _asset(),
        );
      },
    );
  }
}
