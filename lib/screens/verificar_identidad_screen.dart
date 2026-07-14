import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';

import '../state/app_state.dart';
import '../theme.dart';

/// Verificación de identidad del jugador (piloto "lite"): sube documento +
/// selfie → queda "verificado" (marcha blanca: auto-aprobado). El documento es
/// dato personal (Ley 29733): se guarda en un bucket PRIVADO y no se muestra.
class VerificarIdentidadScreen extends StatefulWidget {
  const VerificarIdentidadScreen({super.key});

  @override
  State<VerificarIdentidadScreen> createState() =>
      _VerificarIdentidadScreenState();
}

class _VerificarIdentidadScreenState extends State<VerificarIdentidadScreen> {
  Uint8List? _doc;
  Uint8List? _selfie;
  bool _enviando = false;

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
      showDialog<void>(
        context: context,
        builder: (ctx) => AlertDialog(
          title: const Text('¡Identidad verificada! ✓'),
          content: const Text(
              'Tu perfil ahora muestra la insignia de jugador verificado. '
              'Los dueños de cancha confían más en jugadores verificados.'),
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
    } else {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text('No se pudo enviar. Revisa tu conexión.')));
    }
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
            _CajaVerificado()
          else ...[
            const Text('Jugador verificado',
                style: TextStyle(fontWeight: FontWeight.w800, fontSize: 18)),
            const SizedBox(height: 6),
            Text(
              'Verifica tu identidad para dar confianza a los dueños de cancha '
              'y reservar sin fricción. Es rápido: una foto de tu documento y '
              'una selfie.',
              style: TextStyle(color: textoTenue, height: 1.35),
            ),
            const SizedBox(height: 18),
            _Tile(
              titulo: 'Foto del documento',
              subtitulo: 'DNI / carné (dato privado, no se publica)',
              icono: Icons.badge_outlined,
              listo: _doc != null,
              onTap: () => _elegir(selfie: false),
            ),
            const SizedBox(height: 12),
            _Tile(
              titulo: 'Selfie',
              subtitulo: 'Una foto tuya de frente',
              icono: Icons.face_outlined,
              listo: _selfie != null,
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
            Row(
              children: [
                Icon(Icons.lock_outline, size: 15, color: textoTenue),
                const SizedBox(width: 6),
                Expanded(
                  child: Text(
                    'Tu documento se guarda de forma privada y no se muestra a '
                    'nadie. Solo se usa para validar tu identidad.',
                    style: TextStyle(color: textoTenue, fontSize: 12),
                  ),
                ),
              ],
            ),
          ],
        ],
      ),
    );
  }
}

class _CajaVerificado extends StatelessWidget {
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
          const Icon(Icons.verified, color: pino, size: 56),
          const SizedBox(height: 10),
          const Text('¡Ya estás verificado!',
              style: TextStyle(fontWeight: FontWeight.w800, fontSize: 18)),
          const SizedBox(height: 6),
          Text(
            'Tu perfil muestra la insignia de jugador verificado.',
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
    required this.listo,
    required this.onTap,
  });
  final String titulo;
  final String subtitulo;
  final IconData icono;
  final bool listo;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Material(
      color: cs.surface,
      borderRadius: BorderRadius.circular(16),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(16),
        child: Container(
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(16),
            border: Border.all(color: listo ? pino : trazo, width: listo ? 1.5 : 1),
          ),
          child: Row(
            children: [
              CircleAvatar(
                backgroundColor:
                    (listo ? pino : cs.primary).withOpacity(0.14),
                child: Icon(listo ? Icons.check : icono,
                    color: listo ? pino : cs.primary),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(titulo,
                        style: const TextStyle(fontWeight: FontWeight.w700)),
                    const SizedBox(height: 2),
                    Text(subtitulo,
                        style: TextStyle(color: textoTenue, fontSize: 12.5)),
                  ],
                ),
              ),
              Icon(listo ? Icons.check_circle : Icons.chevron_right,
                  color: listo ? pino : textoTenue),
            ],
          ),
        ),
      ),
    );
  }
}
