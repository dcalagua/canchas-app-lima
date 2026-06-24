import 'package:flutter/material.dart';

import '../services/propiedad_service.dart';
import '../state/app_state.dart';
import '../theme.dart';

/// Panel ADMIN de reclamos (modelo concierge): el equipo de Pichangol ve los
/// reclamos pendientes, contacta al dueño (el código y el teléfono salen aquí y
/// también te llegan por WhatsApp) y aprueba/rechaza. Aprobar desbloquea que el
/// dueño configure su cancha; luego se valida en sitio.
class AdminReclamosScreen extends StatefulWidget {
  const AdminReclamosScreen({super.key});

  @override
  State<AdminReclamosScreen> createState() => _AdminReclamosScreenState();
}

class _AdminReclamosScreenState extends State<AdminReclamosScreen> {
  bool _cargando = false;
  List<Map<String, dynamic>> _reclamos = [];
  String _filtro = 'pendiente_triage';

  static const _filtros = {
    'pendiente_triage': 'Por aprobar',
    'aprobado_triage': 'Aprobados',
    'pendiente_validacion': 'Por validar',
    'activada': 'Activadas',
  };

  @override
  void initState() {
    super.initState();
    _cargar();
  }

  Future<void> _cargar() async {
    setState(() => _cargando = true);
    final r = await PropiedadService.listarReclamos(estado: _filtro);
    if (!mounted) return;
    setState(() {
      _reclamos = r.reversed.toList(); // más recientes primero
      _cargando = false;
    });
  }

  Future<void> _decidir(Map<String, dynamic> r, bool aprobado) async {
    final res = await PropiedadService.triageReclamo(
      reclamoId: (r['id'] as num).toInt(),
      aprobado: aprobado,
      revisor: appState.usuario?.email ?? 'admin',
    );
    if (!mounted) return;
    if (res != null && res['ok'] == true) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        backgroundColor: aprobado ? bosque : clayOscuro,
        content: Text(aprobado
            ? '✅ Reclamo aprobado. El dueño ya puede configurar su cancha.'
            : '❌ Reclamo rechazado.',
            style: const TextStyle(color: Colors.white)),
      ));
      _cargar();
    } else {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text('No se pudo registrar la decisión. Reintenta.')));
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: papel,
      appBar: AppBar(title: const Text('Reclamos')),
      body: Column(
        children: [
          SizedBox(
            height: 56,
            child: ListView(
              scrollDirection: Axis.horizontal,
              padding: const EdgeInsets.fromLTRB(16, 10, 16, 8),
              children: [
                for (final e in _filtros.entries)
                  Padding(
                    padding: const EdgeInsets.only(right: 8),
                    child: ChoiceChip(
                      label: Text(e.value),
                      selected: _filtro == e.key,
                      selectedColor: bosque,
                      labelStyle: TextStyle(
                          color: _filtro == e.key ? lima : tinta,
                          fontWeight: FontWeight.w700),
                      onSelected: (_) {
                        setState(() => _filtro = e.key);
                        _cargar();
                      },
                    ),
                  ),
              ],
            ),
          ),
          Expanded(
            child: RefreshIndicator(
              onRefresh: _cargar,
              child: _cargando
                  ? const Center(child: CircularProgressIndicator())
                  : _reclamos.isEmpty
                      ? ListView(children: const [
                          SizedBox(height: 90),
                          Center(child: Text('No hay reclamos en este estado.')),
                        ])
                      : ListView.separated(
                          padding: const EdgeInsets.fromLTRB(16, 6, 16, 24),
                          itemCount: _reclamos.length,
                          separatorBuilder: (_, __) =>
                              const SizedBox(height: 10),
                          itemBuilder: (_, i) => _ReclamoCard(
                            reclamo: _reclamos[i],
                            onAprobar: () => _decidir(_reclamos[i], true),
                            onRechazar: () => _decidir(_reclamos[i], false),
                          ),
                        ),
            ),
          ),
        ],
      ),
    );
  }
}

class _ReclamoCard extends StatelessWidget {
  const _ReclamoCard(
      {required this.reclamo, required this.onAprobar, required this.onRechazar});
  final Map<String, dynamic> reclamo;
  final VoidCallback onAprobar;
  final VoidCallback onRechazar;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final estado = reclamo['estado'] as String? ?? '';
    final pendiente = estado == 'pendiente_triage';
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: trazo),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(reclamo['nombre_local']?.toString() ?? 'Local',
                    style:
                        t.titleSmall?.copyWith(fontWeight: FontWeight.w800)),
              ),
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                decoration: BoxDecoration(
                    color: const Color(0xFFEAF6C2),
                    borderRadius: BorderRadius.circular(999)),
                child: Text('cód. ${reclamo['codigo'] ?? '------'}',
                    style: const TextStyle(
                        color: bosque,
                        fontWeight: FontWeight.w900,
                        fontSize: 12)),
              ),
            ],
          ),
          const SizedBox(height: 6),
          Text('Solicitante: ${reclamo['solicitante_id'] ?? '—'}',
              style: t.bodySmall?.copyWith(color: textoTenue)),
          if ((reclamo['telefono_contacto'] ?? '').toString().isNotEmpty)
            Text('Contacto: ${reclamo['telefono_contacto']}',
                style: t.bodySmall?.copyWith(color: textoTenue)),
          Text('Estado: $estado',
              style: t.bodySmall?.copyWith(color: textoTenue)),
          if (pendiente) ...[
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: OutlinedButton(
                    onPressed: onRechazar,
                    child: const Text('Rechazar'),
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: FilledButton(
                    onPressed: onAprobar,
                    child: const Text('Aprobar'),
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
