import 'package:flutter/material.dart';

import '../models/models.dart';
import '../services/propiedad_service.dart';
import '../state/app_state.dart';
import '../theme.dart';

/// Configuración del MODO de aprobación de canchas (admin).
///
/// - **Marcha blanca**: el modelo actual de pruebas — el admin aprueba y la
///   cancha queda activa al instante.
/// - **Nuevo flujo**: tras aprobar, la cancha exige validación en sitio
///   (código + GPS) antes de habilitar reservas.
///
/// El modo GLOBAL aplica a todas las canchas; se puede sobreescribir por cancha.
class ConfiguracionAprobacionScreen extends StatefulWidget {
  const ConfiguracionAprobacionScreen({super.key});

  @override
  State<ConfiguracionAprobacionScreen> createState() =>
      _ConfiguracionAprobacionScreenState();
}

class _ConfiguracionAprobacionScreenState
    extends State<ConfiguracionAprobacionScreen> {
  String _global = 'marcha_blanca';
  Map<String, String> _overrides = {};
  bool _cargando = true;
  bool _guardando = false;

  static const _titulos = {
    'marcha_blanca': 'Marcha blanca',
    'nuevo_flujo': 'Nuevo flujo',
  };
  static const _desc = {
    'marcha_blanca':
        'Aprobación directa. El admin aprueba y la cancha queda activa al '
            'instante (sin validación en sitio). Ideal para tus pruebas.',
    'nuevo_flujo':
        'Verificación reforzada. Tras aprobar, la cancha exige validación en '
            'sitio (código + GPS) antes de habilitar reservas.',
  };

  @override
  void initState() {
    super.initState();
    _cargar();
  }

  Future<void> _cargar() async {
    final cfg = await PropiedadService.configModo();
    if (!mounted) return;
    setState(() {
      _cargando = false;
      if (cfg != null) {
        _global = (cfg['global'] ?? 'marcha_blanca') as String;
        final ov = cfg['overrides'];
        _overrides = ov is Map
            ? ov.map((k, v) => MapEntry(k.toString(), v.toString()))
            : {};
      }
    });
  }

  Future<void> _setGlobal(String modo) async {
    if (modo == _global) return;
    setState(() => _guardando = true);
    final ok = await PropiedadService.setModoGlobal(modo);
    if (!mounted) return;
    setState(() {
      _guardando = false;
      if (ok) _global = modo;
    });
    _aviso(ok ? 'Modo global: ${_titulos[modo]}' : 'No se pudo guardar.');
  }

  Future<void> _setOverride(String canchaId, String? modo) async {
    setState(() => _guardando = true);
    final ok = await PropiedadService.setModoCancha(canchaId, modo);
    if (!mounted) return;
    setState(() {
      _guardando = false;
      if (ok) {
        if (modo == null) {
          _overrides.remove(canchaId);
        } else {
          _overrides[canchaId] = modo;
        }
      }
    });
    _aviso(ok ? 'Excepción actualizada.' : 'No se pudo guardar.');
  }

  void _aviso(String m) =>
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(m)));

  String _modoEfectivo(String canchaId) => _overrides[canchaId] ?? _global;

  @override
  Widget build(BuildContext context) {
    if (!PropiedadService.disponible) {
      return Scaffold(
        backgroundColor: papel,
        appBar: AppBar(title: const Text('Aprobación de canchas')),
        body: const Center(
          child: Padding(
            padding: EdgeInsets.all(28),
            child: Text(
              'El backend no está configurado (GROWTH_API_URL vacío), así que no '
              'se puede cambiar el modo de aprobación en esta build.',
              textAlign: TextAlign.center,
            ),
          ),
        ),
      );
    }

    final canchas = appState
        .todasLasCanchas()
        .where((c) => c.registrada)
        .toList()
      ..sort((a, b) => a.nombre.compareTo(b.nombre));

    return Scaffold(
      backgroundColor: papel,
      appBar: AppBar(
        title: const Text('Aprobación de canchas'),
        bottom: _guardando
            ? const PreferredSize(
                preferredSize: Size.fromHeight(3),
                child: LinearProgressIndicator(minHeight: 3),
              )
            : null,
      ),
      body: _cargando
          ? const Center(child: CircularProgressIndicator())
          : ListView(
              padding: const EdgeInsets.fromLTRB(18, 16, 18, 40),
              children: [
                Text('Modo global',
                    style: Theme.of(context)
                        .textTheme
                        .titleMedium
                        ?.copyWith(fontWeight: FontWeight.w800)),
                const SizedBox(height: 4),
                Text('Aplica a todas las canchas que no tengan una excepción.',
                    style: TextStyle(color: textoTenue, fontSize: 13)),
                const SizedBox(height: 12),
                for (final modo in const ['marcha_blanca', 'nuevo_flujo'])
                  _ModoCard(
                    titulo: _titulos[modo]!,
                    descripcion: _desc[modo]!,
                    seleccionado: _global == modo,
                    onTap: _guardando ? null : () => _setGlobal(modo),
                  ),
                const SizedBox(height: 22),
                Text('Excepciones por cancha',
                    style: Theme.of(context)
                        .textTheme
                        .titleMedium
                        ?.copyWith(fontWeight: FontWeight.w800)),
                const SizedBox(height: 4),
                Text(
                  'Por defecto cada cancha usa el modo global. Aquí puedes forzar '
                  'un modo distinto solo para algunas.',
                  style: TextStyle(color: textoTenue, fontSize: 13),
                ),
                const SizedBox(height: 10),
                if (canchas.isEmpty)
                  Padding(
                    padding: const EdgeInsets.symmetric(vertical: 16),
                    child: Text('No hay canchas registradas todavía.',
                        style: TextStyle(color: textoTenue)),
                  )
                else
                  for (final c in canchas)
                    _FilaCanchaModo(
                      cancha: c,
                      tieneOverride: _overrides.containsKey(c.id),
                      modoEfectivo: _modoEfectivo(c.id),
                      tituloDe: (m) => _titulos[m] ?? m,
                      onElegir: _guardando
                          ? null
                          : (modo) => _setOverride(c.id, modo),
                    ),
              ],
            ),
    );
  }
}

class _ModoCard extends StatelessWidget {
  const _ModoCard({
    required this.titulo,
    required this.descripcion,
    required this.seleccionado,
    required this.onTap,
  });
  final String titulo;
  final String descripcion;
  final bool seleccionado;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: InkWell(
        borderRadius: BorderRadius.circular(16),
        onTap: onTap,
        child: Container(
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            color: seleccionado ? limaSuave : Colors.white,
            borderRadius: BorderRadius.circular(16),
            border: Border.all(
                color: seleccionado ? pino : trazo,
                width: seleccionado ? 2 : 1),
          ),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icon(
                seleccionado
                    ? Icons.radio_button_checked
                    : Icons.radio_button_unchecked,
                color: seleccionado ? pino : textoTenue,
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(titulo,
                        style: const TextStyle(
                            fontWeight: FontWeight.w800, fontSize: 15)),
                    const SizedBox(height: 3),
                    Text(descripcion,
                        style: TextStyle(
                            color: textoTenue, fontSize: 12.5, height: 1.35)),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _FilaCanchaModo extends StatelessWidget {
  const _FilaCanchaModo({
    required this.cancha,
    required this.tieneOverride,
    required this.modoEfectivo,
    required this.tituloDe,
    required this.onElegir,
  });
  final Cancha cancha;
  final bool tieneOverride;
  final String modoEfectivo;
  final String Function(String) tituloDe;
  final ValueChanged<String?>? onElegir;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final etiqueta = tieneOverride
        ? '${tituloDe(modoEfectivo)} (excepción)'
        : '${tituloDe(modoEfectivo)} (global)';
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.fromLTRB(12, 6, 6, 6),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: trazo),
      ),
      child: Row(
        children: [
          Container(
            width: 10,
            height: 10,
            decoration: BoxDecoration(
                color: colorDeporte(cancha.deporte),
                borderRadius: BorderRadius.circular(3)),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(cancha.nombre,
                    style: t.bodyMedium?.copyWith(fontWeight: FontWeight.w700),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis),
                Text(etiqueta,
                    style: t.bodySmall?.copyWith(
                        color: tieneOverride ? pino : textoTenue,
                        fontWeight:
                            tieneOverride ? FontWeight.w700 : FontWeight.w400)),
              ],
            ),
          ),
          PopupMenuButton<String>(
            enabled: onElegir != null,
            icon: const Icon(Icons.more_vert, color: pino),
            onSelected: (v) => onElegir?.call(v == 'global' ? null : v),
            itemBuilder: (_) => [
              const PopupMenuItem(
                  value: 'global', child: Text('Usar modo global')),
              const PopupMenuItem(
                  value: 'marcha_blanca', child: Text('Marcha blanca')),
              const PopupMenuItem(
                  value: 'nuevo_flujo', child: Text('Nuevo flujo')),
            ],
          ),
        ],
      ),
    );
  }
}
