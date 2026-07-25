import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../models/models.dart';
import '../services/avisos_service.dart';
import '../services/retos_service.dart';
import '../state/app_state.dart';
import '../theme.dart';

/// MIS RETOS P2P: retos recibidos (aceptar/rechazar) y enviados; reportar el
/// resultado de los aceptados (suma al ranking global).
class MisRetosScreen extends StatefulWidget {
  const MisRetosScreen({super.key});
  @override
  State<MisRetosScreen> createState() => _MisRetosScreenState();
}

class _MisRetosScreenState extends State<MisRetosScreen> {
  bool _cargando = true;
  List<Map<String, dynamic>> _recibidos = const [];
  List<Map<String, dynamic>> _enviados = const [];

  String get _email => (appState.usuario?.email ?? '').toLowerCase().trim();

  @override
  void initState() {
    super.initState();
    _cargar();
  }

  Future<void> _cargar() async {
    if (_email.isEmpty) {
      setState(() => _cargando = false);
      return;
    }
    setState(() => _cargando = true);
    final r = await RetosService.mios(_email);
    if (!mounted) return;
    final recibidos = ((r?['recibidos'] as List?) ?? const [])
        .map((e) => Map<String, dynamic>.from(e as Map))
        .toList();
    final enviados = ((r?['enviados'] as List?) ?? const [])
        .map((e) => Map<String, dynamic>.from(e as Map))
        .toList();
    setState(() {
      _recibidos = recibidos;
      _enviados = enviados;
      _cargando = false;
    });
    // Retos auto-confirmados por vencer el plazo → notificar siempre (al que
    // ganó y al que perdió), una sola vez.
    await _notificarAutoConfirmados([...recibidos, ...enviados]);
  }

  /// Detecta retos que se auto-confirmaron (nadie confirmó a tiempo) desde la
  /// última vez, avisa al OTRO por push y muestra feedback en pantalla.
  Future<void> _notificarAutoConfirmados(
      List<Map<String, dynamic>> todos) async {
    final prefs = await SharedPreferences.getInstance();
    final vistos = (prefs.getStringList('retos_auto_vistos') ?? <String>[]).toSet();
    bool mostrarGane = false, mostrarPerdi = false;
    String ganadorNombre = '', ganadorFoto = '', rivalNombre = '';
    var cambio = false;
    for (final r in todos) {
      if ((r['estado'] ?? '').toString() != 'jugado') continue;
      if (r['auto_confirmado'] != true) continue;
      final id = (r['id'] as num).toInt().toString();
      if (vistos.contains(id)) continue;
      vistos.add(id);
      cambio = true;
      final ganadorEmail = (r['ganador_email'] ?? '').toString().toLowerCase();
      final retadorEmail = (r['retador_email'] ?? '').toString().toLowerCase();
      final retadorNombre = (r['retador_nombre'] ?? 'Retador').toString();
      final retadoNombre = (r['retado_nombre'] ?? 'Retado').toString();
      final otroEmail =
          _email == retadorEmail ? (r['retado_email'] ?? '').toString() : retadorEmail;
      final otroGano = ganadorEmail == otroEmail.toLowerCase();
      // Push al otro (best-effort): así ambos se enteran del desenlace.
      AvisosService.desenlaceReto(
          email: otroEmail,
          ganaste: otroGano,
          rivalNombre: _email == retadorEmail ? retadorNombre : retadoNombre,
          automatico: true);
      if (ganadorEmail == _email) {
        mostrarGane = true;
        ganadorNombre = ganadorEmail == retadorEmail ? retadorNombre : retadoNombre;
        ganadorFoto = appState.fotoDe(ganadorEmail) ?? '';
      } else {
        mostrarPerdi = true;
        rivalNombre = ganadorEmail == retadorEmail ? retadorNombre : retadoNombre;
      }
    }
    if (cambio) await prefs.setStringList('retos_auto_vistos', vistos.toList());
    if (!mounted) return;
    if (mostrarGane) {
      await showDialog(
        context: context,
        builder: (_) =>
            _CelebracionGanador(nombre: ganadorNombre, foto: ganadorFoto),
      );
    } else if (mostrarPerdi && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text(rivalNombre.isNotEmpty
              ? 'Se dio por válido el resultado vs $rivalNombre. Esta vez perdiste.'
              : 'Se dio por válido el resultado del reto. Esta vez perdiste.')));
    }
  }

  String _deporte(String name) {
    for (final d in Deporte.values) {
      if (d.name == name) return d.etiqueta;
    }
    return name;
  }

  Future<void> _responder(Map<String, dynamic> r, bool aceptar) async {
    final ok = await RetosService.responder((r['id'] as num).toInt(), aceptar);
    if (!mounted) return;
    if (ok) {
      // Avisa al retador que respondí su reto (push, best-effort).
      AvisosService.retoRespondido(
          retadorEmail: (r['retador_email'] ?? '').toString(),
          retadoNombre: (r['retado_nombre'] ?? 'Tu rival').toString(),
          aceptado: aceptar);
      await _cargar();
      await appState.cargarRetosPendientes(); // refresca el badge del perfil
    } else {
      ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('No se pudo. Reintenta.')));
    }
  }

  Future<void> _reportar(Map<String, dynamic> r) async {
    final retadorEmail = (r['retador_email'] ?? '').toString();
    final retadoEmail = (r['retado_email'] ?? '').toString();
    final retadorNombre = (r['retador_nombre'] ?? 'Retador').toString();
    final retadoNombre = (r['retado_nombre'] ?? 'Retado').toString();
    final esDobles = (r['modalidad'] ?? 'singles').toString() == 'dobles';
    // En dobles, cada opción es una PAREJA; el "email representante" es el del
    // capitán de ese lado (el backend acepta cualquier integrante del lado).
    final retadorLabel = esDobles
        ? '$retadorNombre / ${r['retador2_nombre'] ?? ''}'
        : retadorNombre;
    final retadoLabel = esDobles
        ? '$retadoNombre / ${r['retado2_nombre'] ?? ''}'
        : retadoNombre;
    final marcador = TextEditingController();
    String? ganador;
    final ok = await showDialog<bool>(
      context: context,
      builder: (dctx) => StatefulBuilder(
        builder: (dctx, setSB) => AlertDialog(
          title: Row(
            children: const [
              CircleAvatar(
                radius: 16,
                backgroundColor: amarillo,
                child: Icon(Icons.emoji_events, color: Colors.white, size: 18),
              ),
              SizedBox(width: 10),
              Text('Reportar resultado'),
            ],
          ),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(esDobles ? '¿Qué pareja ganó?' : '¿Quién ganó?',
                  style: const TextStyle(fontWeight: FontWeight.w700)),
              const SizedBox(height: 10),
              for (final o in [
                (retadorEmail, retadorLabel),
                (retadoEmail, retadoLabel),
              ])
                _OpcionGanador(
                  email: o.$1,
                  nombre: o.$2,
                  seleccionado: ganador == o.$1,
                  onTap: () => setSB(() => ganador = o.$1),
                ),
              const SizedBox(height: 8),
              TextField(
                controller: marcador,
                decoration: const InputDecoration(
                    labelText: 'Marcador (opcional)', hintText: 'ej. 6-3 6-4'),
              ),
            ],
          ),
          actions: [
            TextButton(
                onPressed: () => Navigator.pop(dctx, false),
                child: const Text('Cancelar')),
            FilledButton(
              style: FilledButton.styleFrom(backgroundColor: lima),
              onPressed: ganador == null
                  ? null
                  : () => Navigator.pop(dctx, true),
              child: const Text('Guardar'),
            ),
          ],
        ),
      ),
    );
    if (ok != true || ganador == null) return;
    final done = await RetosService.resultado(
        (r['id'] as num).toInt(), ganador!,
        marcador: marcador.text.trim(), reportadoPor: _email);
    if (!mounted) return;
    if (done) {
      // Doble confirmación: el resultado NO cuenta hasta que el OTRO confirme.
      // Le mando el aviso al LADO CONTRARIO para que confirme/dispute (en dobles
      // son dos personas; cualquiera puede confirmar).
      final yo = _email;
      final soyRetador = [
        retadorEmail.toLowerCase(),
        (r['retador2_email'] ?? '').toString().toLowerCase(),
      ].contains(yo);
      final miNombre = soyRetador ? retadorNombre : retadoNombre;
      final otrosEmails = (soyRetador
              ? [retadoEmail, (r['retado2_email'] ?? '').toString()]
              : [retadorEmail, (r['retador2_email'] ?? '').toString()])
          .where((e) => e.trim().isNotEmpty);
      for (final otro in otrosEmails) {
        AvisosService.confirmarResultado(
            email: otro, porNombre: miNombre, marcador: marcador.text.trim());
      }
      await _cargar();
      if (mounted) {
        final otroNombre = soyRetador ? retadoLabel : retadorLabel;
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
            backgroundColor: bosque,
            content: Text(
                'Resultado enviado. Falta que $otroNombre lo confirme.')));
      }
    } else {
      ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('No se pudo guardar.')));
    }
  }

  /// El OTRO jugador confirma o disputa el resultado reportado.
  Future<void> _confirmar(Map<String, dynamic> r, bool acepta) async {
    final id = (r['id'] as num).toInt();
    final ok = await RetosService.confirmar(id, _email, acepta: acepta);
    if (!mounted) return;
    if (!ok) {
      ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('No se pudo. Reintenta.')));
      return;
    }
    final retadorEmail = (r['retador_email'] ?? '').toString().toLowerCase();
    final retadorNombre = (r['retador_nombre'] ?? 'Retador').toString();
    final retadoNombre = (r['retado_nombre'] ?? 'Retado').toString();
    final ganadorEmail = (r['ganador_email'] ?? '').toString().toLowerCase();
    final reportadoPor = (r['reportado_por'] ?? '').toString().toLowerCase();
    final esDobles = (r['modalidad'] ?? 'singles').toString() == 'dobles';
    final soyRetador = [
      retadorEmail.toLowerCase(),
      (r['retador2_email'] ?? '').toString().toLowerCase(),
    ].contains(_email);
    final miNombre = soyRetador ? retadorNombre : retadoNombre;
    // El lado ganador se deriva de a qué pareja pertenece el correo ganador.
    final ganoRetador = [
      retadorEmail.toLowerCase(),
      (r['retador2_email'] ?? '').toString().toLowerCase(),
    ].contains(ganadorEmail);
    final labelRetador = esDobles
        ? '$retadorNombre / ${r['retador2_nombre'] ?? ''}'
        : retadorNombre;
    final labelRetado = esDobles
        ? '$retadoNombre / ${r['retado2_nombre'] ?? ''}'
        : retadoNombre;

    if (acepta) {
      // Avisa al reportador el desenlace (ganó/perdió) — siempre notifica.
      // ¿El lado del reportador fue el que ganó?
      final reporterEsRetador = [
        retadorEmail.toLowerCase(),
        (r['retador2_email'] ?? '').toString().toLowerCase(),
      ].contains(reportadoPor);
      final reportadorGano = reporterEsRetador == ganoRetador;
      AvisosService.desenlaceReto(
          email: reportadoPor, ganaste: reportadorGano, rivalNombre: miNombre);
      await appState.cargarRetosResultados(); // suma al ranking
      await appState.cargarRetosPendientes();
      await _cargar();
      // Celebración del ganador (pareja o jugador).
      final ganadorNombre = ganoRetador ? labelRetador : labelRetado;
      if (mounted) {
        await showDialog(
          context: context,
          builder: (_) => _CelebracionGanador(
              nombre: ganadorNombre, foto: appState.fotoDe(ganadorEmail)),
        );
      }
    } else {
      AvisosService.resultadoDisputado(email: reportadoPor, porNombre: miNombre);
      await _cargar();
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
            content: Text('Marcaste el resultado en disputa. Vuelvan a '
                'reportarlo cuando coincidan.')));
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Mis retos')),
      body: _email.isEmpty
          ? const Center(
              child: Padding(
                padding: EdgeInsets.all(28),
                child: Text('Inicia sesión para ver tus retos.',
                    textAlign: TextAlign.center,
                    style: TextStyle(color: textoTenue)),
              ),
            )
          : _cargando
              ? const Center(child: CircularProgressIndicator(color: lima))
              : RefreshIndicator(
                  color: lima,
                  onRefresh: _cargar,
                  child: (_recibidos.isEmpty && _enviados.isEmpty)
                      ? ListView(children: const [
                          SizedBox(height: 80),
                          Icon(Icons.sports_kabaddi,
                              size: 60, color: textoTenue),
                          SizedBox(height: 12),
                          Padding(
                            padding: EdgeInsets.symmetric(horizontal: 30),
                            child: Text(
                                'Aún no tienes retos. Abre el Ranking Global, '
                                'toca un jugador y rétalo.',
                                textAlign: TextAlign.center,
                                style: TextStyle(color: textoTenue)),
                          ),
                        ])
                      : ListView(
                          padding: const EdgeInsets.fromLTRB(16, 14, 16, 30),
                          children: [
                            if (_recibidos.isNotEmpty) ...[
                              const Text('Recibidos',
                                  style: TextStyle(
                                      fontWeight: FontWeight.w800,
                                      fontSize: 16)),
                              const SizedBox(height: 8),
                              for (final r in _recibidos)
                                _RetoCard(
                                    r: r,
                                    soyRetado: true,
                                    miEmail: _email,
                                    deporte: _deporte(
                                        (r['deporte'] ?? '').toString()),
                                    onAceptar: () => _responder(r, true),
                                    onRechazar: () => _responder(r, false),
                                    onReportar: () => _reportar(r),
                                    onConfirmar: () => _confirmar(r, true),
                                    onDisputar: () => _confirmar(r, false)),
                              const SizedBox(height: 12),
                            ],
                            if (_enviados.isNotEmpty) ...[
                              const Text('Enviados',
                                  style: TextStyle(
                                      fontWeight: FontWeight.w800,
                                      fontSize: 16)),
                              const SizedBox(height: 8),
                              for (final r in _enviados)
                                _RetoCard(
                                    r: r,
                                    soyRetado: false,
                                    miEmail: _email,
                                    deporte: _deporte(
                                        (r['deporte'] ?? '').toString()),
                                    onReportar: () => _reportar(r),
                                    onConfirmar: () => _confirmar(r, true),
                                    onDisputar: () => _confirmar(r, false)),
                            ],
                          ],
                        ),
                ),
    );
  }
}

/// Celebración VIVA del ganador al reportar el resultado: copa que rebota,
/// estallido de confeti de colores y el nombre/foto del ganador. Se cierra sola
/// (~2.5s) o al tocar. Da la sensación de "gif" sin usar assets ni paquetes.
class _CelebracionGanador extends StatefulWidget {
  const _CelebracionGanador({required this.nombre, this.foto});
  final String nombre;
  final String? foto;
  @override
  State<_CelebracionGanador> createState() => _CelebracionGanadorState();
}

class _CelebracionGanadorState extends State<_CelebracionGanador>
    with SingleTickerProviderStateMixin {
  late final AnimationController _c;
  Timer? _cierre;

  @override
  void initState() {
    super.initState();
    _c = AnimationController(
        vsync: this, duration: const Duration(milliseconds: 2400))
      ..forward();
    _cierre = Timer(const Duration(milliseconds: 2500),
        () => mounted ? Navigator.of(context).maybePop() : null);
  }

  @override
  void dispose() {
    _cierre?.cancel();
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    const colores = [lima, teal, amarillo, naranja, morado, clayOscuro];
    final foto = widget.foto;
    final inicial =
        widget.nombre.trim().isNotEmpty ? widget.nombre.trim()[0].toUpperCase() : '?';
    return GestureDetector(
      onTap: () => Navigator.of(context).maybePop(),
      child: Dialog(
        backgroundColor: Colors.transparent,
        elevation: 0,
        child: AnimatedBuilder(
          animation: _c,
          builder: (context, _) {
            final t = _c.value;
            final trofeo = Curves.elasticOut.transform((t / 0.45).clamp(0.0, 1.0));
            final burst = Curves.easeOut.transform(((t - 0.1) / 0.6).clamp(0.0, 1.0));
            final textoOp = ((t - 0.35) / 0.3).clamp(0.0, 1.0);
            return SizedBox(
              width: 260,
              height: 320,
              child: Stack(
                alignment: Alignment.center,
                children: [
                  // Estallido de confeti de colores.
                  for (int i = 0; i < 12; i++)
                    Transform.translate(
                      offset: Offset(
                          math.cos(i / 12 * 2 * math.pi) * (20 + burst * 115),
                          math.sin(i / 12 * 2 * math.pi) * (20 + burst * 115) -
                              30),
                      child: Opacity(
                        opacity: (1 - burst).clamp(0.0, 1.0),
                        child: Container(
                          width: 12,
                          height: 12,
                          decoration: BoxDecoration(
                              color: colores[i % colores.length],
                              shape: BoxShape.circle),
                        ),
                      ),
                    ),
                  Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Transform.scale(
                        scale: trofeo,
                        child: Container(
                          width: 96,
                          height: 96,
                          decoration: const BoxDecoration(
                              color: amarillo, shape: BoxShape.circle),
                          child: const Icon(Icons.emoji_events,
                              color: Colors.white, size: 52),
                        ),
                      ),
                      const SizedBox(height: 16),
                      Opacity(
                        opacity: textoOp,
                        child: Column(
                          children: [
                            CircleAvatar(
                              radius: 22,
                              backgroundColor: teal,
                              backgroundImage: (foto != null && foto.isNotEmpty)
                                  ? NetworkImage(foto)
                                  : null,
                              child: (foto != null && foto.isNotEmpty)
                                  ? null
                                  : Text(inicial,
                                      style: const TextStyle(
                                          color: Colors.white,
                                          fontWeight: FontWeight.w800)),
                            ),
                            const SizedBox(height: 10),
                            Text('¡${widget.nombre} ganó!',
                                textAlign: TextAlign.center,
                                style: const TextStyle(
                                    color: Colors.white,
                                    fontWeight: FontWeight.w900,
                                    fontSize: 20)),
                            const SizedBox(height: 4),
                            const Text('Sumó al ranking de tenis 🎾',
                                style: TextStyle(
                                    color: Colors.white70, fontSize: 13)),
                          ],
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            );
          },
        ),
      ),
    );
  }
}

/// Opción de ganador en "Reportar resultado": tarjeta con avatar de color +
/// nombre, resaltada al elegirla. Más viva y clara que un radio pelado.
class _OpcionGanador extends StatelessWidget {
  const _OpcionGanador(
      {required this.email,
      required this.nombre,
      required this.seleccionado,
      required this.onTap});
  final String email;
  final String nombre;
  final bool seleccionado;
  final VoidCallback onTap;
  @override
  Widget build(BuildContext context) {
    final inicial =
        nombre.trim().isNotEmpty ? nombre.trim()[0].toUpperCase() : '?';
    final foto = appState.fotoDe(email);
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(12),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
          decoration: BoxDecoration(
            color: seleccionado
                ? limaSuave
                : Theme.of(context).colorScheme.surface,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(
                color: seleccionado ? lima : trazo,
                width: seleccionado ? 1.5 : 1),
          ),
          child: Row(
            children: [
              CircleAvatar(
                radius: 18,
                backgroundColor: teal,
                backgroundImage:
                    (foto != null && foto.isNotEmpty) ? NetworkImage(foto) : null,
                child: (foto != null && foto.isNotEmpty)
                    ? null
                    : Text(inicial,
                        style: const TextStyle(
                            color: Colors.white, fontWeight: FontWeight.w800)),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Text(nombre,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(fontWeight: FontWeight.w700)),
              ),
              Icon(
                  seleccionado
                      ? Icons.check_circle
                      : Icons.radio_button_unchecked,
                  color: seleccionado ? lima : textoTenue),
            ],
          ),
        ),
      ),
    );
  }
}

class _RetoCard extends StatelessWidget {
  const _RetoCard({
    required this.r,
    required this.soyRetado,
    required this.deporte,
    required this.miEmail,
    this.onAceptar,
    this.onRechazar,
    this.onReportar,
    this.onConfirmar,
    this.onDisputar,
  });
  final Map<String, dynamic> r;
  final bool soyRetado;
  final String deporte;
  final String miEmail;
  final VoidCallback? onAceptar;
  final VoidCallback? onRechazar;
  final VoidCallback? onReportar;
  final VoidCallback? onConfirmar;
  final VoidCallback? onDisputar;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final estado = (r['estado'] ?? '').toString();
    final esDobles = (r['modalidad'] ?? 'singles').toString() == 'dobles';
    String _lado(String n1, String n2) =>
        esDobles && n2.trim().isNotEmpty ? '$n1 / $n2' : n1;
    final ladoRetador = _lado((r['retador_nombre'] ?? 'Retador').toString(),
        (r['retador2_nombre'] ?? '').toString());
    final ladoRetado = _lado((r['retado_nombre'] ?? 'Retado').toString(),
        (r['retado2_nombre'] ?? '').toString());
    // El "otro" lado según mi rol (en dobles, la pareja rival).
    final otro = soyRetado ? ladoRetador : ladoRetado;
    // Colores VIVOS y distintos por estado (como los deportes de la home), no
    // tonos oscuros/apagados.
    final (String etiqueta, Color color, IconData icono) = switch (estado) {
      'pendiente' => ('Pendiente', amarillo, Icons.hourglass_top),
      'aceptado' => ('Aceptado', lima, Icons.handshake),
      'por_confirmar' => ('Por confirmar', naranja, Icons.hourglass_bottom),
      'jugado' => ('Jugado', morado, Icons.emoji_events),
      'disputado' => ('En disputa', clayOscuro, Icons.report_gmailerrorred),
      'rechazado' => ('Rechazado', clayOscuro, Icons.close),
      _ => (estado, teal, Icons.sports_kabaddi),
    };
    // Datos para la confirmación del resultado.
    final ganadorEmail = (r['ganador_email'] ?? '').toString().toLowerCase();
    final reportadoPor = (r['reportado_por'] ?? '').toString().toLowerCase();
    final yoReporte = reportadoPor == miEmail.toLowerCase();
    // Lado ganador (en dobles, la pareja): el correo ganador pertenece a él.
    final ganoRetador = [
      (r['retador_email'] ?? '').toString().toLowerCase(),
      (r['retador2_email'] ?? '').toString().toLowerCase(),
    ].contains(ganadorEmail);
    final ganadorNombre = ganoRetador ? ladoRetador : ladoRetado;
    final marcadorTxt = (r['marcador'] ?? '').toString();
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: cs.surface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: trazo),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Ícono estilo Airbnb: círculo de color según el estado del reto.
              CircleAvatar(
                radius: 22,
                backgroundColor: color,
                child: Icon(icono, color: Colors.white, size: 22),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Expanded(
                          child: Text(
                              soyRetado ? 'Te retó $otro' : 'Retaste a $otro',
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style:
                                  const TextStyle(fontWeight: FontWeight.w800)),
                        ),
                        Container(
                          padding: const EdgeInsets.symmetric(
                              horizontal: 8, vertical: 3),
                          decoration: BoxDecoration(
                              color: color.withOpacity(0.14),
                              borderRadius: BorderRadius.circular(8)),
                          child: Text(etiqueta,
                              style: TextStyle(
                                  color: color,
                                  fontWeight: FontWeight.w800,
                                  fontSize: 11.5)),
                        ),
                      ],
                    ),
                    const SizedBox(height: 2),
                    Text(
                        '$deporte'
                        '${(r['zona'] ?? '').toString().isNotEmpty ? ' · ${r['zona']}' : ''}',
                        style:
                            const TextStyle(color: textoTenue, fontSize: 12.5)),
                    if ((estado == 'jugado' || estado == 'por_confirmar') &&
                        marcadorTxt.isNotEmpty) ...[
                      const SizedBox(height: 4),
                      Text('Resultado: $marcadorTxt',
                          style: const TextStyle(
                              color: textoTenue, fontSize: 12.5)),
                    ],
                    // Quién reportó como ganador (mientras se confirma).
                    if (estado == 'por_confirmar' && ganadorNombre.isNotEmpty) ...[
                      const SizedBox(height: 4),
                      Text('Reportaron que ganó $ganadorNombre',
                          style: const TextStyle(
                              color: naranja,
                              fontSize: 12.5,
                              fontWeight: FontWeight.w700)),
                    ],
                  ],
                ),
              ),
            ],
          ),
          // Por confirmar: si yo reporté, espero; si no, confirmo o disputo.
          if (estado == 'por_confirmar') ...[
            const SizedBox(height: 10),
            if (yoReporte)
              Text('Esperando que $otro confirme el resultado…',
                  style: const TextStyle(color: textoTenue, fontSize: 12.5))
            else
              Row(
                children: [
                  Expanded(
                    child: OutlinedButton(
                      onPressed: onDisputar,
                      style: OutlinedButton.styleFrom(
                          foregroundColor: clayOscuro,
                          side: const BorderSide(color: clayOscuro)),
                      child: const Text('Disputar'),
                    ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: FilledButton.icon(
                      style: FilledButton.styleFrom(backgroundColor: lima),
                      onPressed: onConfirmar,
                      icon: const Icon(Icons.check, size: 18),
                      label: const Text('Confirmar'),
                    ),
                  ),
                ],
              ),
          ],
          // En disputa: cualquiera de los dos puede volver a reportar.
          if (estado == 'disputado') ...[
            const SizedBox(height: 10),
            const Text('El resultado quedó en disputa. Coordinen y vuelvan a '
                'reportarlo.',
                style: TextStyle(color: textoTenue, fontSize: 12.5)),
            const SizedBox(height: 8),
            SizedBox(
              width: double.infinity,
              child: OutlinedButton.icon(
                onPressed: onReportar,
                icon: const Icon(Icons.emoji_events, size: 18),
                label: const Text('Reportar de nuevo'),
              ),
            ),
          ],
          if (estado == 'pendiente' && soyRetado) ...[
            const SizedBox(height: 10),
            Row(
              children: [
                Expanded(
                  child: OutlinedButton(
                    onPressed: onRechazar,
                    style: OutlinedButton.styleFrom(
                        foregroundColor: clayOscuro,
                        side: const BorderSide(color: clayOscuro)),
                    child: const Text('Rechazar'),
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: FilledButton(
                    style: FilledButton.styleFrom(backgroundColor: lima),
                    onPressed: onAceptar,
                    child: const Text('Aceptar'),
                  ),
                ),
              ],
            ),
          ],
          if (estado == 'aceptado') ...[
            const SizedBox(height: 10),
            SizedBox(
              width: double.infinity,
              child: FilledButton.icon(
                style: FilledButton.styleFrom(
                    backgroundColor: lima, foregroundColor: Colors.white),
                onPressed: onReportar,
                icon: const Icon(Icons.emoji_events, size: 18),
                label: const Text('Reportar resultado'),
              ),
            ),
          ],
        ],
      ),
    );
  }
}
