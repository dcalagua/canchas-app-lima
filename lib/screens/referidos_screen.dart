import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../services/whatsapp_link.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../utils/compartir_pichangol.dart';
import '../widgets/dialogo_pichangol.dart';
import '../widgets/responsive.dart';
import 'login_google_sheet.dart';
import '../widgets/icono_vivo.dart';

const _kReleaseUrl =
    'https://github.com/dcalagua/canchas-app-lima/releases/tag/v0.1.0';

/// "Invita y gana" (referidos): comparte tu código; cuando un amigo lo canjea,
/// ambos ganan un bono de saldo. Motor de crecimiento del piloto.
class ReferidosScreen extends StatefulWidget {
  const ReferidosScreen({super.key});

  @override
  State<ReferidosScreen> createState() => _ReferidosScreenState();
}

class _ReferidosScreenState extends State<ReferidosScreen> {
  final _codigoAmigo = TextEditingController();
  int _invitados = 0;
  bool _canjeando = false;
  // Estado del backend (`/referidos/estado`): bono por moneda, lo ganado y el
  // código que ya canjeé. null mientras carga o sin red.
  Map<String, dynamic>? _estado;

  @override
  void initState() {
    super.initState();
    _refrescar();
  }

  @override
  void dispose() {
    _codigoAmigo.dispose();
    super.dispose();
  }

  Future<void> _refrescar() async {
    if (!appState.logueado) return;
    // El backend acredita los bonos (también los de canjes viejos del app) y
    // devuelve el conteo; aquí solo se muestra.
    final est = await appState.estadoReferidos();
    if (!mounted || est == null) return;
    setState(() {
      _estado = est;
      _invitados = (est['invitados'] as num?)?.toInt() ?? 0;
    });
    final imp = (est['importados'] as num?)?.toInt() ?? 0;
    if (imp > 0) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text('Te acreditamos $imp bono(s) de Invita y gana 🎁'),
        backgroundColor: lima,
      ));
    }
  }

  /// "S/ 10" / "\$ 2.50" / "Bs 15" en la moneda de MI billetera.
  String _monto(int centimos) {
    final sim = (_estado?['simbolo'] as String?) ?? '';
    final v = centimos / 100;
    final txt = v == v.roundToDouble() ? v.toStringAsFixed(0) : v.toStringAsFixed(2);
    return sim.isEmpty ? txt : '$sim $txt';
  }

  int get _bono => (_estado?['bono_centimos'] as num?)?.toInt() ?? 0;
  int get _ganado => (_estado?['ganado_centimos'] as num?)?.toInt() ?? 0;
  String get _canjeado => (_estado?['canjeado'] as String?) ?? '';

  String _mensajeReferido() {
    final cod = appState.codigoReferido;
    return '¡Juega conmigo en Pichangol! 🎾⚽\n\n'
        'Reserva canchas de fútbol, tenis y más cerca de ti.\n'
        'Usa mi código *$cod* al registrarte y ambos ganamos un bono. 🎁\n\n'
        'Descárgala: $_kReleaseUrl';
  }

  void _compartir() => WhatsAppLink.compartir(_mensajeReferido());

  Future<void> _canjear() async {
    final c = _codigoAmigo.text.trim();
    if (c.isEmpty) return;
    setState(() => _canjeando = true);
    final r = await appState.canjearReferido(c);
    if (!mounted) return;
    setState(() => _canjeando = false);
    if (r != null && r['ok'] == true) {
      _codigoAmigo.clear();
      final cent = (r['bono_centimos'] as num?)?.toInt() ?? 0;
      final sim = (r['simbolo'] as String?) ?? '';
      final v = cent / 100;
      final txt = v == v.roundToDouble() ? v.toStringAsFixed(0) : v.toStringAsFixed(2);
      await avisarPichangol(
        context,
        titulo: '¡Bono acreditado! 🎁',
        mensaje: cent > 0
            ? 'Te sumamos $sim $txt a tu saldo Pichangol. Tu amigo también recibe su bono.'
            : 'Código canjeado. Tu amigo ya sabe que te uniste.',
        textoBoton: 'Genial',
        icono: Icons.card_giftcard,
      );
      _refrescar();
    } else {
      avisarPichangol(
        context,
        titulo: 'No se pudo canjear',
        mensaje: (r?['mensaje'] as String?) ??
            'No hay conexión. Inténtalo de nuevo en un momento.',
        textoBoton: 'Entendido',
        icono: Icons.error_outline,
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    if (!appState.logueado) {
      return Scaffold(
        appBar: AppBar(title: const Text('Invita y gana')),
        body: Center(
          child: Padding(
            padding: const EdgeInsets.all(28),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const IconoVivo(Icons.card_giftcard, size: 56, color: lima),
                const SizedBox(height: 12),
                Text('Inicia sesión para tener tu código',
                    style: t.titleMedium?.copyWith(fontWeight: FontWeight.w800),
                    textAlign: TextAlign.center),
                const SizedBox(height: 16),
                FilledButton(
                  style: FilledButton.styleFrom(backgroundColor: lima),
                  onPressed: () async {
                    final ok = await LoginGoogleSheet.mostrar(context,
                        motivo: 'tener tu código de referido');
                    if (ok && mounted) {
                      setState(() {});
                      _refrescar();
                    }
                  },
                  child: const Text('Iniciar sesión'),
                ),
              ],
            ),
          ),
        ),
      );
    }
    final cod = appState.codigoReferido;
    return Scaffold(
      appBar: AppBar(title: const Text('Invita y gana')),
      body: ListenableBuilder(
        listenable: appState,
        builder: (context, _) {
          return ListView(
            // Regla app: contenido centrado (ancho máx) en pantallas anchas.
            padding: EdgeInsets.symmetric(
                horizontal: ladoTablet(context, 18, 600), vertical: 18),
            children: [
              // Tarjeta con el código.
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(22),
                decoration: BoxDecoration(
                  gradient: const LinearGradient(colors: [lima, teal]),
                  borderRadius: BorderRadius.circular(20),
                ),
                child: Column(
                  children: [
                    const IconoVivo(Icons.card_giftcard,
                        color: Colors.white, size: 40),
                    const SizedBox(height: 10),
                    Text('Tu código',
                        style: t.bodyMedium
                            ?.copyWith(color: Colors.white70)),
                    const SizedBox(height: 4),
                    Row(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Text(cod,
                            style: t.headlineSmall?.copyWith(
                                color: Colors.white,
                                fontWeight: FontWeight.w900,
                                letterSpacing: 2)),
                        const SizedBox(width: 8),
                        InkWell(
                          onTap: () {
                            Clipboard.setData(ClipboardData(text: cod));
                            ScaffoldMessenger.of(context).showSnackBar(
                                const SnackBar(
                                    content: Text('Código copiado')));
                          },
                          child: const Icon(Icons.copy,
                              color: Colors.white70, size: 20),
                        ),
                      ],
                    ),
                    const SizedBox(height: 16),
                    SizedBox(
                      width: double.infinity,
                      child: FilledButton.icon(
                        style: FilledButton.styleFrom(
                            backgroundColor: Colors.white,
                            foregroundColor: lima,
                            padding:
                                const EdgeInsets.symmetric(vertical: 13)),
                        onPressed: _compartir,
                        icon: const Icon(Icons.chat),
                        label: const Text('Invitar por WhatsApp',
                            style: TextStyle(fontWeight: FontWeight.w800)),
                      ),
                    ),
                    const SizedBox(height: 8),
                    TextButton.icon(
                      onPressed: () => CompartirPichangol.compartir(context,
                          texto: _mensajeReferido()),
                      icon: const Icon(Icons.send, color: Colors.white),
                      label: const Text('Compartir en Pichangol',
                          style: TextStyle(
                              color: Colors.white,
                              fontWeight: FontWeight.w800)),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 16),
              // Cómo funciona.
              Text(
                  _bono > 0
                      ? 'Comparte tu código. Cuando un amigo lo canjea, '
                          '${_monto(_bono)} para cada uno, directo a tu saldo. 🎁'
                      : 'Comparte tu código con tus amigos para que jueguen contigo en Pichangol.',
                  style: t.bodyMedium?.copyWith(color: textoTenueDe(context))),
              if (_ganado > 0) ...[
                const SizedBox(height: 12),
                Container(
                  padding: const EdgeInsets.all(14),
                  decoration: BoxDecoration(
                    color: const Color(0xFFFFF6E0),
                    borderRadius: BorderRadius.circular(14),
                  ),
                  child: Text(
                      '🎁 Llevas ${_monto(_ganado)} ganados con Invita y gana. Ya están en tu saldo.',
                      style: const TextStyle(
                          color: Color(0xFF8A5A00), fontWeight: FontWeight.w700)),
                ),
              ],
              const SizedBox(height: 16),
              Container(
                padding: const EdgeInsets.all(14),
                decoration: BoxDecoration(
                  color: limaSuave,
                  borderRadius: BorderRadius.circular(14),
                ),
                child: Row(
                  children: [
                    const CircleAvatar(radius: 16, backgroundColor: morado, child: IconoVivo(Icons.groups, size: 17, color: Colors.white)),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Text(
                        _invitados == 0
                            ? 'Aún nadie usó tu código. ¡Comparte y gana!'
                            : '$_invitados ${_invitados == 1 ? 'persona ya usó' : 'personas ya usaron'} tu código.',
                        style: const TextStyle(
                            color: bosque, fontWeight: FontWeight.w700),
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 24),
              // Canjear un código (o el que ya canjeé).
              if (_canjeado.isNotEmpty)
                Container(
                  padding: const EdgeInsets.all(14),
                  decoration: BoxDecoration(
                    color: limaSuave,
                    borderRadius: BorderRadius.circular(14),
                  ),
                  child: Text(
                      '✅ Ya canjeaste el código $_canjeado. Solo se puede uno por cuenta.',
                      style: const TextStyle(
                          color: bosque, fontWeight: FontWeight.w700)),
                )
              else ...[
                Text('¿Tienes el código de un amigo?',
                    style: t.titleMedium?.copyWith(fontWeight: FontWeight.w800)),
                const SizedBox(height: 8),
                TextField(
                  controller: _codigoAmigo,
                  textCapitalization: TextCapitalization.characters,
                  decoration: InputDecoration(
                    hintText: 'Ej. PCG3F9A2',
                    isDense: true,
                    border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(12),
                        borderSide: const BorderSide(color: trazo)),
                    enabledBorder: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(12),
                        borderSide: const BorderSide(color: trazo)),
                  ),
                ),
                const SizedBox(height: 10),
                SizedBox(
                  width: double.infinity,
                  child: FilledButton(
                    style: FilledButton.styleFrom(
                        backgroundColor: lima,
                        padding: const EdgeInsets.symmetric(vertical: 13)),
                    onPressed: _canjeando ? null : _canjear,
                    child: Text(_canjeando ? 'Canjeando…' : 'Canjear código',
                        style: const TextStyle(fontWeight: FontWeight.w800)),
                  ),
                ),
                const SizedBox(height: 8),
                Text(
                    'Solo puedes canjear un código una vez, y no el tuyo propio.',
                    style: t.bodySmall?.copyWith(color: textoTenueDe(context))),
              ],
            ],
          );
        },
      ),
    );
  }
}
