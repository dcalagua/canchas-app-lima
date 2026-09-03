import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../brand.dart';
import '../config/pais.dart';
import '../theme.dart';
import '../widgets/selector_pais.dart';
import 'app_shell.dart';

const String kPrefOnboardingVisto = 'onboarding_visto';

class _Slide {
  final IconData icono;
  final Color color;
  final String titulo;
  final String texto;
  const _Slide(this.icono, this.color, this.titulo, this.texto);
}

class OnboardingScreen extends StatefulWidget {
  const OnboardingScreen({super.key});

  @override
  State<OnboardingScreen> createState() => _OnboardingScreenState();
}

class _OnboardingScreenState extends State<OnboardingScreen> {
  final _controller = PageController();
  int _page = 0;

  /// País elegido en la última pantalla ("¿Dónde juegas?"). Arranca con el
  /// que la app ya tenga (persistido o GPS) y el usuario lo confirma o cambia.
  /// Fija a la vez el país que explora y el de su billetera.
  String _paisIso = paisActual.iso;

  /// Total de pantallas: los slides + la de país al final.
  int get _total => _slides.length + 1;
  bool get _enPais => _page == _slides.length;

  static const _slides = [
    _Slide(Icons.map, verdeCancha, 'Encuentra tu cancha',
        'Mira en el mapa las canchas de fútbol, tenis y pádel cerca de ti, con su precio por hora. Buscar es libre, sin registrarte.'),
    _Slide(Icons.bolt, coral, 'Reserva en segundos',
        'Elige día y hora y asegura tu cancha con una seña. Menos plantones, tu hora garantizada.'),
    _Slide(Icons.groups, arena, 'Arma tu partido',
        'Junta a tu gente y juega a tu nivel. Pichangol conecta jugadores y canchas cerca de ti.'),
  ];

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Future<void> _terminar() async {
    final p = paisesSoportados[_paisIso];
    if (p != null) {
      await elegirPais(p); // país de exploración (elección explícita)
      await setPaisCasa(p); // país de la billetera
    }
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setBool(kPrefOnboardingVisto, true);
    } catch (_) {}
    if (!mounted) return;
    Navigator.of(context).pushReplacement(
      MaterialPageRoute(builder: (_) => const AppShell()),
    );
  }

  void _siguiente() {
    if (_page < _total - 1) {
      _controller.nextPage(
          duration: const Duration(milliseconds: 350), curve: Curves.easeOut);
    } else {
      _terminar();
    }
  }

  /// Última pantalla: elegir país. Define qué canchas ves y en qué moneda
  /// funciona tu billetera; se puede cambiar después desde Explorar y Perfil.
  Widget _slidePais() {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 32),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Container(
            width: 150,
            height: 150,
            decoration: BoxDecoration(
              color: verdeCancha.withOpacity(0.12),
              shape: BoxShape.circle,
            ),
            child: const Icon(Icons.public, size: 72, color: verdeCancha),
          ),
          const SizedBox(height: 40),
          const Text(
            '¿Dónde juegas?',
            textAlign: TextAlign.center,
            style: TextStyle(fontSize: 24, fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 14),
          Text(
            'Pichangol está en Perú, Bolivia y Ecuador. Elige tu país para ver '
            'las canchas y pagar en tu moneda. Si viajas, podrás cambiarlo '
            'cuando quieras.',
            textAlign: TextAlign.center,
            style: TextStyle(fontSize: 15, height: 1.5, color: Colors.grey[700]),
          ),
          const SizedBox(height: 26),
          SelectorPais(
            seleccion: _paisIso,
            onElegir: (p) => setState(() => _paisIso = p.iso),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final ultimo = _page == _total - 1;
    return Scaffold(
      body: SafeArea(
        child: Column(
          children: [
            Align(
              alignment: Alignment.centerRight,
              child: TextButton(
                onPressed: _terminar,
                child: const Text('Saltar',
                    style: TextStyle(color: Colors.grey)),
              ),
            ),
            Expanded(
              child: PageView.builder(
                controller: _controller,
                itemCount: _total,
                onPageChanged: (i) => setState(() => _page = i),
                itemBuilder: (context, i) {
                  if (i == _slides.length) return _slidePais();
                  final s = _slides[i];
                  return Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 32),
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Container(
                          width: 150,
                          height: 150,
                          decoration: BoxDecoration(
                            color: s.color.withOpacity(0.12),
                            shape: BoxShape.circle,
                          ),
                          child: Icon(s.icono, size: 72, color: s.color),
                        ),
                        const SizedBox(height: 40),
                        Text(
                          s.titulo,
                          textAlign: TextAlign.center,
                          style: const TextStyle(
                              fontSize: 24, fontWeight: FontWeight.bold),
                        ),
                        const SizedBox(height: 14),
                        Text(
                          s.texto,
                          textAlign: TextAlign.center,
                          style: TextStyle(
                              fontSize: 15,
                              height: 1.5,
                              color: Colors.grey[700]),
                        ),
                      ],
                    ),
                  );
                },
              ),
            ),
            Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                for (int i = 0; i < _total; i++)
                  AnimatedContainer(
                    duration: const Duration(milliseconds: 250),
                    margin: const EdgeInsets.symmetric(horizontal: 4),
                    width: i == _page ? 22 : 8,
                    height: 8,
                    decoration: BoxDecoration(
                      color: i == _page ? verdeCancha : Colors.black12,
                      borderRadius: BorderRadius.circular(10),
                    ),
                  ),
              ],
            ),
            Padding(
              padding: const EdgeInsets.all(24),
              child: SizedBox(
                width: double.infinity,
                child: FilledButton(
                  style: FilledButton.styleFrom(
                    backgroundColor: ultimo ? coral : verdeCancha,
                    padding: const EdgeInsets.symmetric(vertical: 16),
                  ),
                  onPressed: _siguiente,
                  child: Text(ultimo
                      ? 'Buscar canchas en ${paisesSoportados[_paisIso]?.nombre ?? 'mi país'}'
                      : 'Siguiente'),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
