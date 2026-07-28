import 'package:flutter/material.dart';

import '../services/musica_service.dart';

/// Pastilla que muestra la música elegida para una historia (en el composer),
/// con botón para quitarla. Estilo oscuro semitransparente (se ve sobre foto o
/// color).
class ChipMusica extends StatelessWidget {
  const ChipMusica({super.key, required this.pista, required this.onQuitar});
  final PistaMusica pista;
  final VoidCallback onQuitar;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.fromLTRB(6, 6, 8, 6),
      decoration: BoxDecoration(
        color: Colors.black.withOpacity(0.45),
        borderRadius: BorderRadius.circular(24),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          ClipRRect(
            borderRadius: BorderRadius.circular(6),
            child: pista.artUrl.isNotEmpty
                ? Image.network(pista.artUrl,
                    width: 28,
                    height: 28,
                    fit: BoxFit.cover,
                    errorBuilder: (_, __, ___) => const _Nota())
                : const _Nota(),
          ),
          const SizedBox(width: 8),
          const Icon(Icons.music_note, color: Colors.white, size: 16),
          const SizedBox(width: 2),
          Flexible(
            child: Text(
              '${pista.titulo} · ${pista.artista}',
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(
                  color: Colors.white,
                  fontWeight: FontWeight.w600,
                  fontSize: 13),
            ),
          ),
          const SizedBox(width: 4),
          InkWell(
            onTap: onQuitar,
            child: const Icon(Icons.close, color: Colors.white70, size: 18),
          ),
        ],
      ),
    );
  }
}

class _Nota extends StatelessWidget {
  const _Nota();
  @override
  Widget build(BuildContext context) => Container(
        width: 28,
        height: 28,
        color: Colors.white24,
        child: const Icon(Icons.music_note, color: Colors.white, size: 16),
      );
}
