import 'package:flutter/material.dart';
import 'package:geocoding/geocoding.dart';

import '../data/geo_admin.dart';
import '../services/location_service.dart';
import '../theme.dart';

/// Selector en CASCADA de la ubicación administrativa del país (3 niveles), con
/// las etiquetas correctas por país (Departamento/Provincia/Distrito en Perú,
/// Provincia/Cantón/Parroquia en Ecuador, etc.). Todo por combo — sin texto
/// libre. Reutilizable en el circuito y en academias.
///
/// Reporta la HOJA elegida (distrito/municipio/parroquia) por [onSeleccion]
/// (cadena vacía si se limpia). Opcionalmente autodetecta por GPS: si se pasa
/// [lat]/[lng] usa ESA coordenada (p. ej. la sede); si no, la del dispositivo.
class SelectorUbicacion extends StatefulWidget {
  const SelectorUbicacion({
    super.key,
    required this.iso,
    required this.onSeleccion,
    this.valorInicial,
    this.lat,
    this.lng,
    this.detectarAlIniciar = false,
  });

  final String iso;
  final String? valorInicial;
  final ValueChanged<String> onSeleccion;
  final double? lat;
  final double? lng;

  /// Si no hay valor inicial, intenta autodetectar por GPS al abrir.
  final bool detectarAlIniciar;

  @override
  State<SelectorUbicacion> createState() => _SelectorUbicacionState();
}

class _SelectorUbicacionState extends State<SelectorUbicacion> {
  String? _n1, _n2, _n3;
  bool _listo = false;
  bool _detectando = false;

  @override
  void initState() {
    super.initState();
    _preparar();
  }

  @override
  void didUpdateWidget(SelectorUbicacion old) {
    super.didUpdateWidget(old);
    // El país cambió (p. ej. la sede se movió a otro país): recarga y reinicia.
    if (old.iso.toUpperCase() != widget.iso.toUpperCase()) {
      _n1 = _n2 = _n3 = null;
      _listo = false;
      _preparar();
    }
  }

  Future<void> _preparar() async {
    await GeoAdmin.cargar(widget.iso);
    if (!mounted) return;
    final v = (widget.valorInicial ?? '').trim();
    if (v.isNotEmpty) {
      final path = GeoAdmin.ubicar(widget.iso, v);
      _n1 = path[0];
      _n2 = path[1];
      _n3 = path[2];
    }
    setState(() => _listo = true);
    if (_n3 == null && v.isEmpty && widget.detectarAlIniciar) _detectar();
  }

  Future<void> _detectar() async {
    setState(() => _detectando = true);
    try {
      double? lat = widget.lat, lng = widget.lng;
      if (lat == null || lng == null) {
        final pos = await LocationService.ubicacionActual();
        lat = pos?.latitude;
        lng = pos?.longitude;
      }
      if (lat == null || lng == null) return;
      final marks = await placemarkFromCoordinates(lat, lng);
      if (marks.isEmpty) return;
      final m = marks.first;
      String pick(String? s) => (s ?? '').trim();
      final path = GeoAdmin.emparejarGps(
        widget.iso,
        pick(m.administrativeArea),
        pick(m.subAdministrativeArea),
        [pick(m.locality), pick(m.subLocality), pick(m.name)],
      );
      if (!mounted || path[0] == null) return;
      setState(() {
        _n1 = path[0];
        _n2 = path[1];
        _n3 = path[2];
      });
      widget.onSeleccion(_n3 ?? '');
    } catch (_) {
    } finally {
      if (mounted) setState(() => _detectando = false);
    }
  }

  Widget _drop(String label, String? value, List<String> items,
      ValueChanged<String?>? onChanged, String hintDeshab) {
    return DropdownButtonFormField<String>(
      value: value,
      isExpanded: true,
      decoration: InputDecoration(
          labelText: label, prefixIcon: const Icon(Icons.place_outlined)),
      items: [
        for (final it in items)
          DropdownMenuItem(
              value: it, child: Text(it, overflow: TextOverflow.ellipsis)),
      ],
      onChanged: onChanged,
      disabledHint: onChanged == null ? Text(hintDeshab) : null,
    );
  }

  @override
  Widget build(BuildContext context) {
    // País sin jerarquía (no debería pasar con PE/BO/EC): evita dead-end.
    if (_listo && !GeoAdmin.disponible(widget.iso)) {
      return const Text('No hay catálogo de zonas para este país todavía.',
          style: TextStyle(color: textoTenue, fontSize: 13));
    }
    if (!_listo) {
      return const Padding(
        padding: EdgeInsets.symmetric(vertical: 8),
        child: SizedBox(
            height: 18,
            width: 18,
            child: CircularProgressIndicator(strokeWidth: 2.2, color: lima)),
      );
    }

    final etq = GeoAdmin.labels(widget.iso);
    final l2Items = _n1 == null ? <String>[] : GeoAdmin.nivel2(widget.iso, _n1!);
    final l3Items = (_n1 == null || _n2 == null)
        ? <String>[]
        : GeoAdmin.nivel3(widget.iso, _n1!, _n2!);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Align(
          alignment: Alignment.centerRight,
          child: TextButton.icon(
            onPressed: _detectando ? null : _detectar,
            icon: _detectando
                ? const SizedBox(
                    width: 15,
                    height: 15,
                    child: CircularProgressIndicator(
                        strokeWidth: 2.2, color: lima))
                : const Icon(Icons.my_location, size: 18, color: bosque),
            label: Text(
                _detectando
                    ? 'Detectando…'
                    : (widget.lat != null
                        ? 'Usar ubicación de la sede'
                        : 'Usar mi ubicación'),
                style: const TextStyle(color: bosque)),
          ),
        ),
        _drop(etq[0], _n1, GeoAdmin.nivel1(widget.iso), (v) {
          setState(() {
            _n1 = v;
            _n2 = null;
            _n3 = null;
          });
          widget.onSeleccion('');
        }, ''),
        const SizedBox(height: 10),
        _drop(
            etq[1],
            _n2,
            l2Items,
            _n1 == null
                ? null
                : (v) {
                    setState(() {
                      _n2 = v;
                      _n3 = null;
                    });
                    widget.onSeleccion('');
                  },
            'Elige ${etq[0].toLowerCase()}'),
        const SizedBox(height: 10),
        _drop(
            etq[2],
            _n3,
            l3Items,
            _n2 == null
                ? null
                : (v) {
                    setState(() => _n3 = v);
                    widget.onSeleccion(v ?? '');
                  },
            'Elige ${etq[1].toLowerCase()}'),
      ],
    );
  }
}
