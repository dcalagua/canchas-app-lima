import 'package:flutter/material.dart';
import 'package:pdf/pdf.dart';
import 'package:pdf/widgets.dart' as pw;
import 'package:printing/printing.dart';

import '../data/perfiles_repo.dart';
import '../models/academia.dart';
import '../models/models.dart';
import '../services/pagos_service.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/reto_flow.dart';

/// PERFIL GLOBAL del jugador: su carnet CONSOLIDADO entre todas las academias
/// (identidad = correo). Se abre al tocar una fila del ranking global. Cierra el
/// círculo de identidad: "una persona, un ranking".
class PerfilGlobalScreen extends StatefulWidget {
  const PerfilGlobalScreen(
      {super.key,
      required this.idKey,
      required this.deporte,
      required this.posicion});
  final String idKey;
  final Deporte deporte;
  final int posicion;

  @override
  State<PerfilGlobalScreen> createState() => _PerfilGlobalScreenState();
}

/// Prompts de la bio (misma lista/orden que "Editar perfil"): clave estable →
/// ícono + etiqueta. Solo se pintan los que el jugador llenó.
const List<(String, IconData, String)> _kPromptsPerfil = [
  ('cancha_favorita', Icons.stadium_outlined, 'Mi cancha favorita'),
  ('dedico', Icons.work_outline, 'Me dedico a'),
  ('juego_desde', Icons.history_outlined, 'Juego desde'),
  ('logro', Icons.emoji_events_outlined, 'Mi mayor logro deportivo'),
  ('tiempo', Icons.schedule_outlined, 'Dedico demasiado tiempo a'),
  ('dato', Icons.lightbulb_outline, 'Dato curioso sobre mí'),
  ('cancion', Icons.music_note_outlined, 'Mi canción para entrar en calor'),
  ('amo', Icons.favorite_border, 'Amo'),
  ('idiomas', Icons.translate_outlined, 'Idiomas que hablo'),
];

class _PerfilGlobalScreenState extends State<PerfilGlobalScreen> {
  bool _esPro = false;

  /// BIO pública del jugador (la que llenó en "Editar perfil").
  Map<String, String> _bio = {};

  @override
  void initState() {
    super.initState();
    _verificarPro();
    _cargarBio();
  }

  Future<void> _cargarBio() async {
    final email =
        widget.idKey.startsWith('e:') ? widget.idKey.substring(2) : '';
    if (email.isEmpty) return;
    final b = await PerfilesRepo.leerBio(email);
    if (mounted && b.isNotEmpty) setState(() => _bio = b);
  }

  Future<void> _verificarPro() async {
    final email =
        widget.idKey.startsWith('e:') ? widget.idKey.substring(2) : '';
    if (email.isEmpty) return;
    final est = await PagosService.proEstado(email);
    if (!mounted) return;
    if (est != null && est['activa'] == true) setState(() => _esPro = true);
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final perfil = appState.perfilGlobalDe(widget.idKey);
    return Scaffold(
      appBar: AppBar(title: const Text('Carnet del jugador')),
      body: perfil == null
          ? const Center(child: Text('Jugador no encontrado.'))
          : ListView(
              padding: const EdgeInsets.fromLTRB(18, 16, 18, 30),
              children: [
                // Carnet.
                Container(
                  padding: const EdgeInsets.all(18),
                  decoration: BoxDecoration(
                    gradient: const LinearGradient(
                      begin: Alignment.topLeft,
                      end: Alignment.bottomRight,
                      colors: [bosque, Color(0xFF1E5C4C)],
                    ),
                    borderRadius: BorderRadius.circular(20),
                  ),
                  child: Row(
                    children: [
                      CircleAvatar(
                        radius: 30,
                        backgroundColor: lima,
                        child: Text(
                            perfil.nombre.isNotEmpty
                                ? perfil.nombre[0].toUpperCase()
                                : '?',
                            style: const TextStyle(
                                color: Colors.white,
                                fontWeight: FontWeight.w900,
                                fontSize: 24)),
                      ),
                      const SizedBox(width: 14),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(perfil.nombre,
                                maxLines: 2,
                                overflow: TextOverflow.ellipsis,
                                style: const TextStyle(
                                    color: Colors.white,
                                    fontWeight: FontWeight.w900,
                                    fontSize: 19)),
                            const SizedBox(height: 2),
                            Row(
                              children: [
                                Text(
                                    'Puesto #${widget.posicion} · ${widget.deporte.etiqueta}',
                                    style: TextStyle(
                                        color: Colors.white.withOpacity(0.85),
                                        fontWeight: FontWeight.w700)),
                                if (_esPro) ...[
                                  const SizedBox(width: 8),
                                  Container(
                                    padding: const EdgeInsets.symmetric(
                                        horizontal: 7, vertical: 2),
                                    decoration: BoxDecoration(
                                        color: lima,
                                        borderRadius:
                                            BorderRadius.circular(6)),
                                    child: const Text('PRO',
                                        style: TextStyle(
                                            color: Colors.white,
                                            fontWeight: FontWeight.w900,
                                            fontSize: 10)),
                                  ),
                                ],
                              ],
                            ),
                            if (perfil.categoria.isNotEmpty)
                              Text(perfil.categoria,
                                  style: TextStyle(
                                      color: Colors.white.withOpacity(0.7),
                                      fontSize: 12.5)),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 14),
                Row(
                  children: [
                    _Stat('Puntos', '${perfil.puntos}', cs.primary),
                    const SizedBox(width: 10),
                    _Stat('Jugados', '${perfil.pj}', cs.onSurface),
                    const SizedBox(width: 10),
                    _Stat('Ganados', '${perfil.pg}', lima),
                    const SizedBox(width: 10),
                    _Stat('Efectividad', '${perfil.pct.toStringAsFixed(0)}%',
                        bosque),
                  ],
                ),
                const SizedBox(height: 12),
                if (_puedeRetar())
                  SizedBox(
                    width: double.infinity,
                    child: FilledButton.icon(
                      style: FilledButton.styleFrom(
                          backgroundColor: lima,
                          foregroundColor: Colors.white,
                          padding: const EdgeInsets.symmetric(vertical: 12)),
                      icon: const Icon(Icons.sports_kabaddi, size: 20),
                      label: Text('Retar a ${perfil.nombre.split(' ').first}'),
                      onPressed: () => _retar(perfil),
                    ),
                  ),
                if (_puedeRetar()) const SizedBox(height: 8),
                SizedBox(
                  width: double.infinity,
                  child: OutlinedButton.icon(
                    style: OutlinedButton.styleFrom(
                        foregroundColor: bosque,
                        side: const BorderSide(color: bosque)),
                    icon: const Icon(Icons.ios_share, size: 18),
                    label: const Text('Compartir carnet'),
                    onPressed: () => _compartir(perfil),
                  ),
                ),
                const SizedBox(height: 20),
                Text(
                    perfil.porAcademia.length > 1
                        ? 'Juega en ${perfil.porAcademia.length} academias'
                        : 'Academia',
                    style: const TextStyle(
                        fontWeight: FontWeight.w800, fontSize: 15)),
                const SizedBox(height: 8),
                for (final r in perfil.porAcademia)
                  Container(
                    margin: const EdgeInsets.only(bottom: 8),
                    padding: const EdgeInsets.symmetric(
                        vertical: 11, horizontal: 14),
                    decoration: BoxDecoration(
                      color: cs.surface,
                      borderRadius: BorderRadius.circular(14),
                      border: Border.all(color: trazo),
                    ),
                    child: Row(
                      children: [
                        const Icon(Icons.school_outlined,
                            size: 18, color: lima),
                        const SizedBox(width: 10),
                        Expanded(
                          child: Text(r.academia,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: const TextStyle(
                                  fontWeight: FontWeight.w700)),
                        ),
                        Text('${r.pg}G-${r.pp}P',
                            style: const TextStyle(
                                color: textoTenue, fontSize: 12.5)),
                        const SizedBox(width: 12),
                        Text('${r.puntos} pts',
                            style: TextStyle(
                                fontWeight: FontWeight.w800,
                                color: cs.primary)),
                      ],
                    ),
                  ),
                const SizedBox(height: 14),
                // ── Acerca del jugador (BIO estilo Airbnb, si la llenó) ──
                if (_bio.isNotEmpty) ...[
                  Text('Acerca de ${perfil.nombre.split(' ').first}',
                      style: const TextStyle(
                          fontWeight: FontWeight.w800, fontSize: 15)),
                  const SizedBox(height: 4),
                  for (final (clave, icono, etiqueta) in _kPromptsPerfil)
                    if ((_bio[clave] ?? '').isNotEmpty)
                      Padding(
                        padding: const EdgeInsets.symmetric(vertical: 7),
                        child: Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Icon(icono, size: 19, color: textoTenueDe(context)),
                            const SizedBox(width: 10),
                            Expanded(
                              child: Text('$etiqueta: ${_bio[clave]}',
                                  style: const TextStyle(
                                      fontSize: 13.5, height: 1.35)),
                            ),
                          ],
                        ),
                      ),
                  const SizedBox(height: 14),
                ],
                const Text('Últimos partidos',
                    style:
                        TextStyle(fontWeight: FontWeight.w800, fontSize: 15)),
                const SizedBox(height: 8),
                for (final pc in perfil.partidos.take(12))
                  Container(
                    margin: const EdgeInsets.only(bottom: 8),
                    padding: const EdgeInsets.symmetric(
                        vertical: 10, horizontal: 12),
                    decoration: BoxDecoration(
                      color: cs.surface,
                      borderRadius: BorderRadius.circular(12),
                      border: Border.all(color: trazo),
                    ),
                    child: Row(
                      children: [
                        Container(
                          padding: const EdgeInsets.symmetric(
                              horizontal: 8, vertical: 3),
                          decoration: BoxDecoration(
                            color: pc.gano
                                ? limaSuave
                                : const Color(0xFFF3E4E4),
                            borderRadius: BorderRadius.circular(8),
                          ),
                          child: Text(pc.gano ? 'Ganó' : 'Perdió',
                              style: TextStyle(
                                  color: pc.gano ? bosque : clayOscuro,
                                  fontWeight: FontWeight.w800,
                                  fontSize: 12)),
                        ),
                        const SizedBox(width: 10),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text('vs ${pc.rival}',
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
                                  style: const TextStyle(
                                      fontWeight: FontWeight.w600)),
                              Text(pc.academia,
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
                                  style: const TextStyle(
                                      color: textoTenue, fontSize: 11.5)),
                            ],
                          ),
                        ),
                        if (pc.partido.marcador.isNotEmpty)
                          Text(pc.partido.marcador,
                              style: const TextStyle(
                                  color: textoTenue, fontSize: 12.5)),
                      ],
                    ),
                  ),
              ],
            ),
    );
  }

  String get _retadoEmail =>
      widget.idKey.startsWith('e:') ? widget.idKey.substring(2) : '';

  /// ¿Se puede retar a este jugador? Solo si tiene cuenta (identidad por correo)
  /// y no soy yo mismo.
  bool _puedeRetar() {
    if (_retadoEmail.isEmpty) return false;
    final yo = (appState.usuario?.email ?? '').toLowerCase().trim();
    return yo != _retadoEmail;
  }

  Future<void> _retar(PerfilGlobalJugador perfil) async {
    // Un solo reto por click: guardia anti doble-clic + preload centralizados.
    await enviarRetoConGuardia(
      context,
      deporte: widget.deporte.name,
      retadoEmail: _retadoEmail,
      retadoNombre: perfil.nombre,
    );
  }

  Future<void> _compartir(PerfilGlobalJugador p) async {
    final verde = PdfColor.fromInt(0xFF14463A);
    final limaP = PdfColor.fromInt(0xFFAEEA94);
    pw.Widget stat(String t, String v) => pw.Expanded(
          child: pw.Column(children: [
            pw.Text(v,
                style: pw.TextStyle(
                    fontSize: 18, fontWeight: pw.FontWeight.bold, color: verde)),
            pw.SizedBox(height: 2),
            pw.Text(t,
                style: const pw.TextStyle(fontSize: 8, color: PdfColors.grey600)),
          ]),
        );
    final doc = pw.Document();
    doc.addPage(pw.Page(
      pageFormat: PdfPageFormat(360, 520, marginAll: 20),
      build: (context) => pw.Center(
        child: pw.Container(
          decoration: pw.BoxDecoration(
            color: PdfColors.white,
            borderRadius: pw.BorderRadius.circular(20),
            border: pw.Border.all(color: PdfColors.grey300),
          ),
          child: pw.Column(
            mainAxisSize: pw.MainAxisSize.min,
            crossAxisAlignment: pw.CrossAxisAlignment.stretch,
            children: [
              pw.Container(
                padding: const pw.EdgeInsets.all(18),
                decoration: pw.BoxDecoration(
                  color: verde,
                  borderRadius: const pw.BorderRadius.only(
                    topLeft: pw.Radius.circular(20),
                    topRight: pw.Radius.circular(20),
                  ),
                ),
                child: pw.Column(
                  crossAxisAlignment: pw.CrossAxisAlignment.start,
                  children: [
                    pw.Text(p.nombre,
                        style: pw.TextStyle(
                            fontSize: 18,
                            fontWeight: pw.FontWeight.bold,
                            color: PdfColors.white)),
                    pw.SizedBox(height: 3),
                    pw.Text(
                        'Puesto #${widget.posicion} · ${widget.deporte.etiqueta}'
                        '${_esPro ? '  ·  PRO' : ''}',
                        style: pw.TextStyle(
                            fontSize: 11,
                            fontWeight: pw.FontWeight.bold,
                            color: limaP)),
                  ],
                ),
              ),
              pw.Padding(
                padding: const pw.EdgeInsets.fromLTRB(18, 20, 18, 18),
                child: pw.Column(children: [
                  pw.Row(children: [
                    stat('Puntos', '${p.puntos}'),
                    stat('Jugados', '${p.pj}'),
                    stat('Ganados', '${p.pg}'),
                    stat('Efectividad', '${p.pct.toStringAsFixed(0)}%'),
                  ]),
                  pw.SizedBox(height: 18),
                  pw.Text(
                      p.porAcademia.length > 1
                          ? 'Juega en ${p.porAcademia.length} academias'
                          : (p.porAcademia.isNotEmpty
                              ? p.porAcademia.first.academia
                              : ''),
                      style: pw.TextStyle(
                          fontSize: 11,
                          fontWeight: pw.FontWeight.bold,
                          color: verde)),
                  pw.SizedBox(height: 6),
                  pw.Text('Ranking Global Pichangol',
                      style: const pw.TextStyle(
                          fontSize: 9, color: PdfColors.grey600)),
                ]),
              ),
            ],
          ),
        ),
      ),
    ));
    final bytes = await doc.save();
    await Printing.sharePdf(
        bytes: bytes,
        filename: 'carnet_global_${p.nombre.replaceAll(' ', '_')}.pdf');
  }
}

class _Stat extends StatelessWidget {
  const _Stat(this.titulo, this.valor, this.color);
  final String titulo;
  final String valor;
  final Color color;
  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 6),
        decoration: BoxDecoration(
          color: Theme.of(context).colorScheme.surface,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: trazo),
        ),
        child: Column(
          children: [
            Text(valor,
                style: TextStyle(
                    fontWeight: FontWeight.w900, fontSize: 17, color: color)),
            const SizedBox(height: 2),
            Text(titulo,
                textAlign: TextAlign.center,
                style: const TextStyle(color: textoTenue, fontSize: 10.5)),
          ],
        ),
      ),
    );
  }
}
