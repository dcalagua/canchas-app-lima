import 'package:flutter/material.dart';

import '../models/models.dart';
import '../models/nivel.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/nivel_chip.dart';
import '../widgets/responsive.dart';

/// Mini-cuestionario que SIEMBRA el nivel inicial del jugador en un deporte
/// (estilo Playtomic: te autoevalúas y luego los resultados lo ajustan). Tres
/// preguntas simples: años jugando, frecuencia semanal, ¿compites?
class NivelOnboardingScreen extends StatefulWidget {
  const NivelOnboardingScreen({super.key, this.deporteInicial});

  /// Deporte preseleccionado (p. ej. el de la sección desde donde se abrió).
  final Deporte? deporteInicial;

  @override
  State<NivelOnboardingScreen> createState() => _NivelOnboardingScreenState();
}

class _NivelOnboardingScreenState extends State<NivelOnboardingScreen> {
  late Deporte _deporte = widget.deporteInicial ?? Deporte.futbol;
  double _anios = 2;
  double _frecuencia = 2;
  bool _compite = false;
  bool _guardando = false;
  Nivel? _resultado;

  Future<void> _calcular() async {
    if (_guardando) return;
    setState(() => _guardando = true);
    await appState.sembrarMiNivel(
      _deporte.name,
      anios: _anios.round(),
      frecuenciaSemana: _frecuencia.round(),
      compite: _compite,
    );
    if (!mounted) return;
    setState(() {
      _guardando = false;
      _resultado = appState.miNivelDe(_deporte.name);
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Tu nivel de jugador')),
      body: AnchoTablet(
        maxWidth: 560,
        child: _resultado != null ? _vistaResultado() : _vistaCuestionario(),
      ),
    );
  }

  Widget _vistaCuestionario() {
    return ListView(
      padding: const EdgeInsets.fromLTRB(20, 18, 20, 30),
      children: [
        const Text('Autoevalúate',
            style: TextStyle(fontSize: 20, fontWeight: FontWeight.w800)),
        const SizedBox(height: 4),
        const Text(
            'Estimamos tu nivel (1 a 7, como Playtomic). Luego se ajusta solo con '
            'tus resultados en retos y campeonatos.',
            style: TextStyle(color: textoTenue)),
        const SizedBox(height: 18),
        const Text('Deporte', style: TextStyle(fontWeight: FontWeight.w700)),
        const SizedBox(height: 8),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            for (final d in deportesActivos)
              _PastillaDeporte(
                deporte: d,
                sel: _deporte == d,
                onTap: () => setState(() => _deporte = d),
              ),
          ],
        ),
        const SizedBox(height: 20),
        _Pregunta(
          titulo: '¿Cuántos años llevas jugando?',
          valor: '${_anios.round()} ${_anios.round() == 1 ? 'año' : 'años'}'
              '${_anios.round() >= 10 ? '+' : ''}',
          slider: Slider(
            value: _anios,
            min: 0,
            max: 10,
            divisions: 10,
            activeColor: lima,
            label: '${_anios.round()}',
            onChanged: (v) => setState(() => _anios = v),
          ),
        ),
        _Pregunta(
          titulo: '¿Cuántas veces juegas por semana?',
          valor: '${_frecuencia.round()}'
              '${_frecuencia.round() >= 5 ? '+' : ''} por semana',
          slider: Slider(
            value: _frecuencia,
            min: 0,
            max: 5,
            divisions: 5,
            activeColor: lima,
            label: '${_frecuencia.round()}',
            onChanged: (v) => setState(() => _frecuencia = v),
          ),
        ),
        SwitchListTile(
          contentPadding: EdgeInsets.zero,
          title: const Text('¿Compites en torneos o ligas?',
              style: TextStyle(fontWeight: FontWeight.w700)),
          value: _compite,
          onChanged: (v) => setState(() => _compite = v),
        ),
        const SizedBox(height: 18),
        SizedBox(
          width: double.infinity,
          child: FilledButton(
            style: FilledButton.styleFrom(
                backgroundColor: lima,
                padding: const EdgeInsets.symmetric(vertical: 14)),
            onPressed: _guardando ? null : _calcular,
            child: _guardando
                ? const SizedBox(
                    width: 22,
                    height: 22,
                    child: CircularProgressIndicator(
                        strokeWidth: 2, color: Colors.white))
                : const Text('Calcular mi nivel',
                    style: TextStyle(fontWeight: FontWeight.w800)),
          ),
        ),
      ],
    );
  }

  Widget _vistaResultado() {
    final n = _resultado!;
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.emoji_events, color: lima, size: 56),
            const SizedBox(height: 12),
            const Text('¡Listo! Este es tu nivel',
                style: TextStyle(fontSize: 19, fontWeight: FontWeight.w800)),
            const SizedBox(height: 16),
            Transform.scale(scale: 1.3, child: NivelChip(nivel: n)),
            const SizedBox(height: 16),
            const Text(
                'Subirá o bajará solo según tus resultados. Ahora puedes buscar '
                'rivales de tu nivel.',
                textAlign: TextAlign.center,
                style: TextStyle(color: textoTenue)),
            const SizedBox(height: 24),
            SizedBox(
              width: double.infinity,
              child: FilledButton(
                style: FilledButton.styleFrom(
                    backgroundColor: bosque,
                    padding: const EdgeInsets.symmetric(vertical: 14)),
                onPressed: () => Navigator.of(context).pop(true),
                child: const Text('Continuar',
                    style: TextStyle(fontWeight: FontWeight.w800)),
              ),
            ),
            TextButton(
              onPressed: () => setState(() => _resultado = null),
              child: const Text('Evaluar otro deporte'),
            ),
          ],
        ),
      ),
    );
  }
}

class _Pregunta extends StatelessWidget {
  const _Pregunta(
      {required this.titulo, required this.valor, required this.slider});
  final String titulo;
  final String valor;
  final Widget slider;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Expanded(
                child: Text(titulo,
                    style: const TextStyle(fontWeight: FontWeight.w700))),
            Text(valor,
                style: const TextStyle(
                    color: teal, fontWeight: FontWeight.w800)),
          ],
        ),
        slider,
      ],
    );
  }
}

class _PastillaDeporte extends StatelessWidget {
  const _PastillaDeporte(
      {required this.deporte, required this.sel, required this.onTap});
  final Deporte deporte;
  final bool sel;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      borderRadius: BorderRadius.circular(24),
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 9),
        decoration: BoxDecoration(
          color: sel ? const Color(0xFFEBEBEB) : Colors.white,
          borderRadius: BorderRadius.circular(24),
          border: Border.all(color: const Color(0xFFE4E4E4)),
          boxShadow: const [
            BoxShadow(
                color: Color(0x0F000000), blurRadius: 6, offset: Offset(0, 2)),
          ],
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(iconoDeporte(deporte), size: 17, color: teal),
            const SizedBox(width: 6),
            Text(deporte.etiqueta,
                style: TextStyle(
                    fontWeight: sel ? FontWeight.w800 : FontWeight.w600,
                    color: const Color(0xFF222222))),
          ],
        ),
      ),
    );
  }
}
