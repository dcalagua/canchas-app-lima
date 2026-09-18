import 'package:google_mlkit_text_recognition/google_mlkit_text_recognition.dart';

/// Resultado de leer un documento con OCR on-device (ML Kit).
class ResultadoOcr {
  const ResultadoOcr({
    required this.esDocumento,
    this.numero,
    this.nacimiento,
    this.textoCrudo = '',
  });

  /// ¿El texto reconocido parece un documento de identidad? (bloquea imágenes
  /// cualquiera: una foto de una pared no tiene estas palabras).
  final bool esDocumento;

  /// Número de documento detectado (best-effort), o null.
  final String? numero;

  /// Fecha de nacimiento detectada (best-effort), para calcular la edad.
  final DateTime? nacimiento;

  /// Texto crudo reconocido (para diagnóstico, no se muestra).
  final String textoCrudo;
}

/// Validación de documento por OCR on-device, para países SIN consulta oficial
/// (hoy Bolivia/CI). No sustituye una verificación contra registro, pero (a)
/// impide subir una imagen cualquiera y (b) extrae número + nacimiento para
/// categorizar por edad. Gratis y offline (ML Kit reconoce en el dispositivo).
class OcrDocumento {
  /// Palabras que aparecen en las cédulas/carnés de la región (mayúsculas, sin
  /// tildes). Se comparan contra el texto reconocido en mayúsculas.
  static const _clavesFuertes = [
    'PLURINACIONAL', // Bolivia: "ESTADO PLURINACIONAL DE BOLIVIA"
    'CEDULA DE IDENTIDAD',
    'CÉDULA DE IDENTIDAD',
    'IDENTIFICACION PERSONAL',
    'SERECI',
  ];
  static const _clavesDebiles = [
    'CEDULA',
    'CÉDULA',
    'IDENTIDAD',
    'BOLIVIA',
    'NACIONALIDAD',
    'FECHA DE NACIMIENTO',
    'NACIMIENTO',
    'APELLIDOS',
    'NOMBRES',
    'DOCUMENTO',
  ];

  /// Analiza la imagen del documento en [path]. Nunca lanza: ante error
  /// devuelve `esDocumento=false` (el flujo pide reintentar la foto).
  static Future<ResultadoOcr> analizar(String path) async {
    final recognizer = TextRecognizer(script: TextRecognitionScript.latin);
    try {
      final input = InputImage.fromFilePath(path);
      final rec = await recognizer.processImage(input);
      final crudo = rec.text;
      final t = _sinTildes(crudo.toUpperCase());

      final fuertes = _clavesFuertes.where((k) => t.contains(k)).length;
      final debiles = _clavesDebiles.where((k) => t.contains(k)).length;
      // Documento si hay una palabra fuerte, o al menos dos débiles.
      final esDoc = fuertes >= 1 || debiles >= 2;

      return ResultadoOcr(
        esDocumento: esDoc,
        numero: esDoc ? _extraerNumero(t) : null,
        nacimiento: esDoc ? _extraerNacimiento(crudo) : null,
        textoCrudo: crudo,
      );
    } catch (_) {
      return const ResultadoOcr(esDocumento: false);
    } finally {
      await recognizer.close();
    }
  }

  static String _sinTildes(String s) => s
      .replaceAll('Á', 'A')
      .replaceAll('É', 'E')
      .replaceAll('Í', 'I')
      .replaceAll('Ó', 'O')
      .replaceAll('Ú', 'U')
      .replaceAll('Ñ', 'N');

  /// Extrae un número de documento plausible: la secuencia más larga de 5–9
  /// dígitos (los CI bolivianos rondan 6–8, a veces con complemento alfanumérico
  /// que aquí se ignora).
  static String? _extraerNumero(String texto) {
    final matches = RegExp(r'\d{5,9}').allMatches(texto).toList();
    if (matches.isEmpty) return null;
    matches.sort((a, b) => b.group(0)!.length.compareTo(a.group(0)!.length));
    return matches.first.group(0);
  }

  /// Busca una fecha (dd/mm/yyyy, dd-mm-yyyy, dd.mm.yyyy) que sea una fecha de
  /// nacimiento plausible: año entre 1900 y (hoy - 5). Si hay varias, toma la
  /// más antigua (el nacimiento suele ser anterior a emisión/expiración).
  static DateTime? _extraerNacimiento(String crudo) {
    final re = RegExp(r'(\d{1,2})[\/\-.](\d{1,2})[\/\-.](\d{4})');
    DateTime? mejor;
    final anioTope = DateTime.now().year - 5;
    for (final m in re.allMatches(crudo)) {
      final d = int.tryParse(m.group(1)!);
      final mo = int.tryParse(m.group(2)!);
      final y = int.tryParse(m.group(3)!);
      if (d == null || mo == null || y == null) continue;
      if (mo < 1 || mo > 12 || d < 1 || d > 31) continue;
      if (y < 1900 || y > anioTope) continue;
      final fecha = DateTime(y, mo, d);
      if (mejor == null || fecha.isBefore(mejor)) mejor = fecha;
    }
    return mejor;
  }
}
