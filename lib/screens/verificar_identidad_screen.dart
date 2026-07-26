import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:image_picker/image_picker.dart';

import '../config/pais.dart';
import '../services/ocr_documento.dart';
import '../state/app_state.dart';
import '../theme.dart';

/// Verificación de identidad del jugador.
///
/// Dos caminos según el país:
///  • **Con registro oficial** (`paisActual.consultaDoc`, hoy Perú/DNI): el
///    jugador escribe su número y lo validamos contra RENIEC (Factiliza). Es la
///    validación ANTI-FRAUDE real — una foto cualquiera no pasa, el número tiene
///    que existir y traer a la persona. De paso obtenemos la fecha de nacimiento
///    para CATEGORIZAR por edad en campeonatos (Sub-30, etc.) sin volver a pedir
///    nada. No guardamos foto del documento (menos dato personal, Ley 29733).
///  • **Sin registro oficial** (Bolivia/Ecuador por ahora): flujo "lite" con
///    foto del documento + selfie (bucket privado, marcha blanca). La validación
///    automática de esos documentos está en el backlog (Ecuador: API propia
///    pendiente de enchufar; Bolivia: OCR on-device).
class VerificarIdentidadScreen extends StatefulWidget {
  const VerificarIdentidadScreen({super.key});

  @override
  State<VerificarIdentidadScreen> createState() =>
      _VerificarIdentidadScreenState();
}

class _VerificarIdentidadScreenState extends State<VerificarIdentidadScreen> {
  // Camino con foto (países sin consulta oficial).
  Uint8List? _doc;
  Uint8List? _selfie;
  bool _enviando = false;

  // Camino con número de documento (Perú/DNI).
  final _dniCtrl = TextEditingController();
  bool _verificando = false;
  String? _errorDni;

  // Camino con OCR (Bolivia/CI): valida que la foto ES un documento.
  ResultadoOcr? _ocr;
  bool _ocrCargando = false;

  @override
  void dispose() {
    _dniCtrl.dispose();
    super.dispose();
  }

  Future<void> _elegir({required bool selfie}) async {
    final XFile? f = await ImagePicker().pickImage(
      source: selfie ? ImageSource.camera : ImageSource.gallery,
      preferredCameraDevice: CameraDevice.front,
      maxWidth: 1600,
      imageQuality: 80,
    );
    if (f == null) return;
    final bytes = await f.readAsBytes();
    if (!mounted) return;
    setState(() {
      if (selfie) {
        _selfie = bytes;
      } else {
        _doc = bytes;
      }
    });
  }

  Future<void> _enviar() async {
    if (_doc == null || _selfie == null) return;
    setState(() => _enviando = true);
    final ok = await appState.enviarVerificacion(_doc!, _selfie!);
    if (!mounted) return;
    setState(() => _enviando = false);
    if (ok) {
      _dialogoOk();
    } else {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text('No se pudo enviar. Revisa tu conexión.')));
    }
  }

  /// Elige la foto del documento y la pasa por OCR (Bolivia). El resultado
  /// decide si es un documento válido (bloquea imágenes cualquiera).
  Future<void> _elegirDocOcr() async {
    final XFile? f = await ImagePicker().pickImage(
      source: ImageSource.gallery,
      maxWidth: 1600,
      imageQuality: 85,
    );
    if (f == null) return;
    final bytes = await f.readAsBytes();
    if (!mounted) return;
    setState(() {
      _doc = bytes;
      _ocr = null;
      _ocrCargando = true;
    });
    final r = await OcrDocumento.analizar(f.path);
    if (!mounted) return;
    setState(() {
      _ocr = r;
      _ocrCargando = false;
    });
  }

  Future<void> _enviarOcr() async {
    if (_doc == null || _selfie == null || _ocr?.esDocumento != true) return;
    setState(() => _enviando = true);
    final ok = await appState.verificarConOcr(
        doc: _doc!, selfie: _selfie!, nacimiento: _ocr!.nacimiento);
    if (!mounted) return;
    setState(() => _enviando = false);
    if (ok) {
      _dialogoOk();
    } else {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text('No se pudo enviar. Revisa tu conexión.')));
    }
  }

  Future<void> _verificarConDni() async {
    final dni = _dniCtrl.text.trim();
    final largo = paisActual.docLongitud;
    if (largo != null && dni.length != largo) {
      setState(() => _errorDni =
          'El ${paisActual.docId} tiene $largo dígitos.');
      return;
    }
    if (dni.isEmpty) {
      setState(() => _errorDni = 'Escribe tu número de ${paisActual.docId}.');
      return;
    }
    setState(() {
      _errorDni = null;
      _verificando = true;
    });
    final (ok, err) = await appState.verificarConDni(dni);
    if (!mounted) return;
    setState(() => _verificando = false);
    if (ok) {
      _dialogoOk();
    } else {
      setState(() => _errorDni = err);
    }
  }

  void _dialogoOk() {
    final edad = appState.edadActual;
    showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('¡Identidad verificada! ✓'),
        content: Text(
          'Tu perfil ahora muestra la insignia de jugador verificado. '
          'Los dueños de cancha confían más en jugadores verificados.'
          '${edad != null ? '\n\nEdad registrada: $edad años '
              '(se usa para categorizarte en campeonatos).' : ''}',
        ),
        actions: [
          FilledButton(
            onPressed: () {
              Navigator.of(ctx).pop();
              Navigator.of(context).pop();
            },
            child: const Text('Listo'),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final verificado = appState.jugadorVerificado;
    return Scaffold(
      appBar: AppBar(title: const Text('Verificar identidad')),
      body: ListView(
        padding: const EdgeInsets.all(18),
        children: [
          if (verificado)
            _CajaVerificado(edad: appState.edadActual)
          else if (paisActual.consultaDoc)
            _porNumero()
          else if (paisActual.iso == 'BO')
            _porOcr()
          else
            _porFoto(),
        ],
      ),
    );
  }

  // ── Camino OFICIAL: número de documento validado contra el registro ────────
  Widget _porNumero() {
    final doc = paisActual.docId; // "DNI" (PE) · "Cédula" (EC)
    // Registro oficial de cada país (para el texto de confianza).
    final registro = paisActual.iso == 'EC'
        ? 'el Registro Civil'
        : (paisActual.iso == 'PE' ? 'RENIEC' : 'el registro oficial');
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text('Jugador verificado',
            style: TextStyle(fontWeight: FontWeight.w800, fontSize: 18)),
        const SizedBox(height: 6),
        Text(
          'Validamos tu $doc contra $registro. Es rápido y da confianza a los '
          'dueños de cancha para reservar sin fricción.',
          style: TextStyle(color: textoTenue, height: 1.35),
        ),
        const SizedBox(height: 18),
        Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: Theme.of(context).colorScheme.surface,
            borderRadius: BorderRadius.circular(16),
            border: Border.all(color: trazo),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  CircleAvatar(
                    backgroundColor: lima.withOpacity(0.16),
                    child: const Icon(Icons.badge_outlined, color: bosque),
                  ),
                  const SizedBox(width: 12),
                  Text('Número de $doc',
                      style: const TextStyle(
                          fontWeight: FontWeight.w700, fontSize: 15)),
                ],
              ),
              const SizedBox(height: 14),
              TextField(
                controller: _dniCtrl,
                keyboardType: TextInputType.number,
                inputFormatters: [
                  FilteringTextInputFormatter.digitsOnly,
                  if (paisActual.docLongitud != null)
                    LengthLimitingTextInputFormatter(paisActual.docLongitud),
                ],
                onChanged: (_) {
                  if (_errorDni != null) setState(() => _errorDni = null);
                },
                decoration: InputDecoration(
                  hintText: paisActual.docLongitud != null
                      ? '${paisActual.docLongitud} dígitos'
                      : 'Número de $doc',
                  errorText: _errorDni,
                  border: const OutlineInputBorder(),
                  prefixIcon: const Icon(Icons.pin_outlined),
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 18),
        SizedBox(
          width: double.infinity,
          child: FilledButton.icon(
            style: FilledButton.styleFrom(
                backgroundColor: lima,
                foregroundColor: Colors.white,
                padding: const EdgeInsets.symmetric(vertical: 15)),
            onPressed: _verificando ? null : _verificarConDni,
            icon: _verificando
                ? const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(
                        strokeWidth: 2, color: Colors.white))
                : const Icon(Icons.verified_user_outlined),
            label: Text(_verificando ? 'Validando…' : 'Verificar $doc',
                style: const TextStyle(
                    fontWeight: FontWeight.w800, fontSize: 15)),
          ),
        ),
        const SizedBox(height: 12),
        _NotaPrivacidad(
          'Solo usamos tu $doc para confirmar tu identidad y tu edad. No '
          'guardamos foto de tu documento ni lo mostramos a nadie.',
        ),
      ],
    );
  }

  // ── Camino OCR: valida on-device que la foto ES un documento (Bolivia) ─────
  Widget _porOcr() {
    final doc = paisActual.docId; // "CI"
    final ocr = _ocr;
    final esDoc = ocr?.esDocumento == true;
    final edad = ocr?.nacimiento == null
        ? null
        : appState.edadDesdeFecha(ocr!.nacimiento!);
    // Estado del análisis para el subtítulo del tile del documento.
    String subtituloDoc;
    Color colorDoc;
    if (_ocrCargando) {
      subtituloDoc = 'Analizando el documento…';
      colorDoc = textoTenue;
    } else if (ocr == null) {
      subtituloDoc = 'Foto legible de tu $doc (dato privado, no se publica)';
      colorDoc = textoTenue;
    } else if (esDoc) {
      subtituloDoc = edad != null
          ? '✓ Documento detectado · edad $edad'
          : '✓ Documento detectado';
      colorDoc = lima;
    } else {
      subtituloDoc = 'Eso no parece un $doc. Sube una foto legible del documento.';
      colorDoc = Colors.redAccent;
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text('Jugador verificado',
            style: TextStyle(fontWeight: FontWeight.w800, fontSize: 18)),
        const SizedBox(height: 6),
        Text(
          'Validamos tu $doc en tu propio teléfono (no se envía a ningún lado '
          'para leerlo). Sube una foto legible y una selfie.',
          style: TextStyle(color: textoTenue, height: 1.35),
        ),
        const SizedBox(height: 18),
        _Tile(
          titulo: 'Foto del documento',
          subtitulo: subtituloDoc,
          subtituloColor: colorDoc,
          icono: Icons.badge_outlined,
          preview: _doc,
          cargando: _ocrCargando,
          onTap: _elegirDocOcr,
        ),
        const SizedBox(height: 12),
        _Tile(
          titulo: 'Selfie',
          subtitulo: 'Una foto tuya de frente',
          icono: Icons.face_outlined,
          preview: _selfie,
          onTap: () => _elegir(selfie: true),
        ),
        const SizedBox(height: 20),
        SizedBox(
          width: double.infinity,
          child: FilledButton.icon(
            style: FilledButton.styleFrom(
                backgroundColor: lima,
                foregroundColor: Colors.white,
                padding: const EdgeInsets.symmetric(vertical: 15)),
            onPressed: (!esDoc || _selfie == null || _enviando)
                ? null
                : _enviarOcr,
            icon: _enviando
                ? const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(
                        strokeWidth: 2, color: Colors.white))
                : const Icon(Icons.verified_user_outlined),
            label: const Text('Enviar y verificar',
                style: TextStyle(fontWeight: FontWeight.w800, fontSize: 15)),
          ),
        ),
        const SizedBox(height: 12),
        _NotaPrivacidad(
          'El OCR corre en tu teléfono. Guardamos tu $doc de forma privada '
          'solo como respaldo; no se muestra a nadie.',
        ),
      ],
    );
  }

  // ── Camino LITE: foto de documento + selfie (países sin consulta) ──────────
  Widget _porFoto() {
    // Ecuador ya tiene API propia (pendiente de enchufar); el resto (Bolivia)
    // irá con OCR on-device. Mientras, foto + selfie con revisión.
    final esEcuador = paisActual.iso == 'EC';
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text('Jugador verificado',
            style: TextStyle(fontWeight: FontWeight.w800, fontSize: 18)),
        const SizedBox(height: 6),
        Text(
          'Verifica tu identidad para dar confianza a los dueños de cancha. '
          'Es rápido: una foto de tu ${paisActual.docId} y una selfie.',
          style: TextStyle(color: textoTenue, height: 1.35),
        ),
        const SizedBox(height: 10),
        Container(
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            color: amarillo.withOpacity(0.14),
            borderRadius: BorderRadius.circular(12),
          ),
          child: Row(
            children: [
              const Icon(Icons.info_outline, size: 18, color: bosque),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  esEcuador
                      ? 'Pronto validaremos tu cédula automáticamente contra '
                          'el registro. Por ahora, sube tu documento y selfie.'
                      : 'Sube una foto legible de tu documento. Pronto '
                          'sumaremos validación automática.',
                  style: const TextStyle(fontSize: 12.5, color: bosque),
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 16),
        _Tile(
          titulo: 'Foto del documento',
          subtitulo:
              '${paisActual.docId}, carné o pasaporte (dato privado, no se publica)',
          icono: Icons.badge_outlined,
          preview: _doc,
          onTap: () => _elegir(selfie: false),
        ),
        const SizedBox(height: 12),
        _Tile(
          titulo: 'Selfie',
          subtitulo: 'Una foto tuya de frente',
          icono: Icons.face_outlined,
          preview: _selfie,
          onTap: () => _elegir(selfie: true),
        ),
        const SizedBox(height: 20),
        SizedBox(
          width: double.infinity,
          child: FilledButton.icon(
            style: FilledButton.styleFrom(
                backgroundColor: lima,
                foregroundColor: Colors.white,
                padding: const EdgeInsets.symmetric(vertical: 15)),
            onPressed:
                (_doc == null || _selfie == null || _enviando) ? null : _enviar,
            icon: _enviando
                ? const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(
                        strokeWidth: 2, color: Colors.white))
                : const Icon(Icons.verified_user_outlined),
            label: const Text('Enviar y verificar',
                style: TextStyle(fontWeight: FontWeight.w800, fontSize: 15)),
          ),
        ),
        const SizedBox(height: 12),
        _NotaPrivacidad(
          'Tu documento se guarda de forma privada y no se muestra a nadie. '
          'Solo se usa para validar tu identidad.',
        ),
      ],
    );
  }
}

class _NotaPrivacidad extends StatelessWidget {
  const _NotaPrivacidad(this.texto);
  final String texto;
  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Icon(Icons.lock_outline, size: 15, color: textoTenue),
        const SizedBox(width: 6),
        Expanded(
          child: Text(texto,
              style: TextStyle(color: textoTenue, fontSize: 12)),
        ),
      ],
    );
  }
}

class _CajaVerificado extends StatelessWidget {
  const _CajaVerificado({this.edad});
  final int? edad;
  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: limaSuave,
        borderRadius: BorderRadius.circular(18),
      ),
      child: Column(
        children: [
          const CircleAvatar(
              radius: 30,
              backgroundColor: lima,
              child: Icon(Icons.verified, size: 30, color: Colors.white)),
          const SizedBox(height: 10),
          const Text('¡Ya estás verificado!',
              style: TextStyle(fontWeight: FontWeight.w800, fontSize: 18)),
          const SizedBox(height: 6),
          Text(
            edad != null
                ? 'Tu perfil muestra la insignia de jugador verificado. '
                    'Edad registrada: $edad años.'
                : 'Tu perfil muestra la insignia de jugador verificado.',
            textAlign: TextAlign.center,
            style: TextStyle(color: textoTenue),
          ),
        ],
      ),
    );
  }
}

class _Tile extends StatelessWidget {
  const _Tile({
    required this.titulo,
    required this.subtitulo,
    required this.icono,
    required this.onTap,
    this.preview,
    this.subtituloColor,
    this.cargando = false,
  });
  final String titulo;
  final String subtitulo;
  final IconData icono;
  final VoidCallback onTap;

  /// Bytes de la foto capturada (documento o selfie). Si viene, se muestra una
  /// miniatura para que el jugador confirme que salió bien (y pueda re-tomarla).
  final Uint8List? preview;

  /// Color del subtítulo cuando el llamador maneja el estado (p. ej. OCR: verde
  /// = documento detectado, rojo = no parece documento). Si es null, se usa el
  /// comportamiento por defecto ("Listo · toca para cambiar").
  final Color? subtituloColor;

  /// Muestra un spinner (análisis OCR en curso).
  final bool cargando;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final listo = preview != null;
    // Si el llamador maneja el estado (subtituloColor), respetamos su texto y
    // color; si no, mostramos el default "Listo · toca para cambiar".
    final manejado = subtituloColor != null;
    final acento = subtituloColor ?? (listo ? lima : trazo);
    final subTexto = manejado
        ? subtitulo
        : (listo ? 'Listo · toca para cambiar' : subtitulo);
    final subColor = manejado ? subtituloColor! : (listo ? lima : textoTenue);
    return Material(
      color: cs.surface,
      borderRadius: BorderRadius.circular(16),
      child: InkWell(
        onTap: cargando ? null : onTap,
        borderRadius: BorderRadius.circular(16),
        child: Container(
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(16),
            border: Border.all(
                color: acento, width: (listo || manejado) ? 1.5 : 1),
          ),
          child: Row(
            children: [
              // Miniatura de lo capturado, o el ícono si aún no hay foto.
              if (listo)
                ClipRRect(
                  borderRadius: BorderRadius.circular(10),
                  child: Image.memory(preview!,
                      width: 46, height: 46, fit: BoxFit.cover),
                )
              else
                CircleAvatar(
                  backgroundColor: cs.primary.withOpacity(0.14),
                  child: Icon(icono, color: cs.primary),
                ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(titulo,
                        style: const TextStyle(fontWeight: FontWeight.w700)),
                    const SizedBox(height: 2),
                    Text(subTexto,
                        style: TextStyle(
                            color: subColor,
                            fontSize: 12.5,
                            fontWeight: (listo || manejado)
                                ? FontWeight.w600
                                : FontWeight.w400)),
                  ],
                ),
              ),
              if (cargando)
                const SizedBox(
                    width: 20,
                    height: 20,
                    child: CircularProgressIndicator(strokeWidth: 2))
              else
                Icon(
                  subtituloColor == Colors.redAccent
                      ? Icons.error_outline
                      : (listo ? Icons.check_circle : Icons.chevron_right),
                  color: acento == trazo ? textoTenue : acento,
                ),
            ],
          ),
        ),
      ),
    );
  }
}
