import '../services/supabase_service.dart';

/// FOTOS PROPIAS OBLIGATORIAS AL RECLAMAR (decisión del director, 2-oct-2026).
///
/// ESPEJO de `backend/growth/propiedad/fotos_reclamo.py`: una foto es PROPIA
/// solo si es una URL pública de NUESTRO Supabase Storage, bucket `canchas`, en
/// la carpeta de ESA cancha (`canchas/<id>/…` o la portada `canchas/<id>.jpg`;
/// las hermanas `u<ts>_<deporte>` comparten la carpeta `u<ts>`). Las de Google
/// no cuentan (sus términos no permiten guardarlas) ni la foto de evidencia
/// (`canchas/ev<id>/`). El mínimo lo decide la torre (`GET /config/canal` →
/// `reclamo_fotos_min`, `AppState.reclamoFotosMin`, cache-first, respaldo 2).
class FotosPropias {
  FotosPropias._();

  /// Respaldo si nunca se pudo consultar al backend.
  static const minimoPorDefecto = 2;

  /// Tope de la galería (= `catalogos.MAX_FOTOS` de la web).
  static const maximo = 8;

  static const _prefijoRuta = '/storage/v1/object/public/canchas/';
  static final _reBase = RegExp(r'^(u\d+)_');

  /// Carpetas del bucket donde viven las fotos de [canchaId].
  static Set<String> carpetasDe(String canchaId) {
    final id = canchaId.trim();
    if (id.isEmpty) return {};
    final out = {id};
    final m = _reBase.firstMatch(id);
    if (m != null) out.add(m.group(1)!);
    return out;
  }

  static String? _carpeta(String url) {
    final u = Uri.tryParse(url.trim());
    if (u == null || (u.scheme != 'https' && u.scheme != 'http')) return null;
    final host = u.host.toLowerCase();
    if (host.isEmpty ||
        host.contains('google') ||
        host.contains('gstatic') ||
        host.contains('ggpht')) {
      return null;
    }
    final proyecto = SupabaseService.proyecto.toLowerCase();
    if (proyecto.contains('.')) {
      if (proyecto != host) return null;
    } else if (!host.endsWith('.supabase.co')) {
      return null;
    }
    if (!u.path.startsWith(_prefijoRuta)) return null;
    final resto = Uri.decodeComponent(u.path.substring(_prefijoRuta.length));
    if (resto.isEmpty || resto.contains('..')) return null;
    final partes = resto.split('/');
    if (partes.length == 1) {
      final n = partes.first;
      final i = n.lastIndexOf('.');
      return i > 0 ? n.substring(0, i) : null; // portada: canchas/<id>.jpg
    }
    return (partes.first.isNotEmpty && partes.last.isNotEmpty)
        ? partes.first
        : null;
  }

  /// ¿[url] es una foto subida por el dueño a la carpeta de [canchaId]?
  static bool esPropia(String url, String canchaId) {
    final c = _carpeta(url);
    return c != null && carpetasDe(canchaId).contains(c);
  }

  /// Fotos propias (sin repetir, en orden).
  static List<String> propias(Iterable<String?> urls, String canchaId) {
    final out = <String>[];
    for (final u in urls) {
      final s = (u ?? '').trim();
      if (s.isNotEmpty && !out.contains(s) && esPropia(s, canchaId)) out.add(s);
    }
    return out;
  }

  /// Texto para el dueño: "Sube 2 fotos de tu local para que podamos aprobarlo".
  static String textoFaltan(int n) =>
      'Sube $n foto${n == 1 ? '' : 's'} de tu local para que podamos aprobarlo';

  /// Por qué las pedimos (mismo texto en web y app).
  static const porQue =
      'Las fotos de Google no se pueden guardar (sus términos no lo permiten): '
      'las tuyas quedan para siempre en tu ficha y nos prueban que el local existe.';
}
