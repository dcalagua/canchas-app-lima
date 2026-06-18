import 'package:flutter/material.dart';

import '../models/models.dart';
import '../theme.dart';

class EtiquetaChip extends StatelessWidget {
  final String texto;
  final Color fondo;
  final Color contenido;

  const EtiquetaChip(
    this.texto, {
    super.key,
    required this.fondo,
    this.contenido = Colors.white,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: fondo,
        borderRadius: BorderRadius.circular(50),
      ),
      child: Text(
        texto,
        style: TextStyle(
          color: contenido,
          fontSize: 11,
          fontWeight: FontWeight.w600,
        ),
      ),
    );
  }
}

class ChipEstado extends StatelessWidget {
  final EstadoReserva estado;
  const ChipEstado(this.estado, {super.key});

  @override
  Widget build(BuildContext context) {
    final fondo = switch (estado) {
      EstadoReserva.nueva => arena,
      EstadoReserva.confirmada => verdeCancha,
      EstadoReserva.completada => verdeClaro,
      EstadoReserva.noShow => const Color(0xFFB3261E),
    };
    return EtiquetaChip(estado.etiqueta, fondo: fondo);
  }
}

class ChipDeporte extends StatelessWidget {
  final Deporte deporte;
  const ChipDeporte(this.deporte, {super.key});

  @override
  Widget build(BuildContext context) {
    final fondo = deporte == Deporte.padel ? azulPadel : verdeCancha;
    return EtiquetaChip(deporte.etiqueta, fondo: fondo);
  }
}
