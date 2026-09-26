import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../config/pais.dart';
import '../services/pagos_service.dart';
import '../state/app_state.dart';
import '../theme.dart';

/// Hoja "Cuenta de cobro": dónde quiere recibir el dueño/organizador/academia
/// sus liquidaciones (pedido del director, 26-sep-2026, tras el primer cobro
/// live: Culqi cobra pero no dispersa; Pichangol transfiere desde su cuenta
/// empresa). Por país: PE → Yape / Plin / cuenta bancaria con CCI; BO y EC →
/// cuenta bancaria. TODO por selección (tipo, banco, documento); solo números y
/// el nombre del titular se escriben (regla del app). El catálogo lo manda el
/// backend (`/pagos/cuenta-cobro/catalogo`) y la validación final es suya.
class CuentaCobroSheet extends StatefulWidget {
  const CuentaCobroSheet({super.key, required this.pais, this.actual});
  final PaisConfig pais;
  final Map<String, dynamic>? actual;

  /// Abre la hoja y devuelve el `resumen` de la cuenta guardada (o null).
  static Future<Map<String, dynamic>?> mostrar(BuildContext context,
      {required PaisConfig pais, Map<String, dynamic>? actual}) {
    return showModalBottomSheet<Map<String, dynamic>>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Theme.of(context).colorScheme.surface,
      shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(24))),
      builder: (_) => CuentaCobroSheet(pais: pais, actual: actual),
    );
  }

  @override
  State<CuentaCobroSheet> createState() => _CuentaCobroSheetState();
}

class _CuentaCobroSheetState extends State<CuentaCobroSheet> {
  Map<String, dynamic>? _cat; // catálogo del país
  bool _cargando = true;
  bool _guardando = false;
  String? _error;
  String _tipo = '';
  String _banco = '';
  String _tipoCuenta = 'ahorros';
  String _doc = '';
  late final TextEditingController _numero =
      TextEditingController(text: (widget.actual?['numero'] ?? '') as String);
  late final TextEditingController _cci =
      TextEditingController(text: (widget.actual?['cci'] ?? '') as String);
  late final TextEditingController _titular = TextEditingController(
      text: (widget.actual?['titular'] as String?)?.isNotEmpty == true
          ? widget.actual!['titular'] as String
          : (appState.usuario?.nombre ?? ''));
  late final TextEditingController _docNum = TextEditingController(
      text: (widget.actual?['doc_numero'] as String?)?.isNotEmpty == true
          ? widget.actual!['doc_numero'] as String
          : appState.dniVerificado);

  @override
  void initState() {
    super.initState();
    _tipo = (widget.actual?['tipo'] ?? '') as String;
    _banco = (widget.actual?['banco'] ?? '') as String;
    _tipoCuenta = (widget.actual?['tipo_cuenta'] ?? 'ahorros') as String;
    _doc = (widget.actual?['doc_tipo'] ?? '') as String;
    PagosService.cuentaCobroCatalogo().then((c) {
      if (!mounted) return;
      final cat = c?[widget.pais.iso] as Map<String, dynamic>?;
      setState(() {
        _cat = cat;
        _cargando = false;
        if (cat != null) {
          final tipos = _lista(cat['tipos']);
          if (_tipo.isEmpty ||
              !tipos.any((t) => t['codigo'] == _tipo)) {
            _tipo = tipos.isNotEmpty ? tipos.first['codigo'] as String : '';
          }
          final docs = _lista(cat['documentos']);
          if (_doc.isEmpty || !docs.any((d) => d['codigo'] == _doc)) {
            _doc = docs.isNotEmpty ? docs.first['codigo'] as String : '';
          }
        }
      });
    });
  }

  List<Map<String, dynamic>> _lista(dynamic v) =>
      ((v as List?) ?? const []).map((e) => Map<String, dynamic>.from(e as Map)).toList();

  @override
  void dispose() {
    _numero.dispose();
    _cci.dispose();
    _titular.dispose();
    _docNum.dispose();
    super.dispose();
  }

  bool get _esBanco => _tipo == 'banco';
  bool get _pideCci =>
      _esBanco && (_cat?['cci'] == true) && _banco != 'BCP';

  Future<void> _guardar() async {
    final email = (appState.usuario?.email ?? '').trim().toLowerCase();
    if (email.isEmpty || _guardando) return;
    setState(() {
      _guardando = true;
      _error = null;
    });
    final r = await PagosService.guardarCuentaCobro(
      email: email,
      pais: widget.pais.iso,
      tipo: _tipo,
      banco: _banco,
      tipoCuenta: _tipoCuenta,
      numero: _numero.text,
      cci: _cci.text,
      titular: _titular.text,
      docTipo: _doc,
      docNumero: _docNum.text,
    );
    if (!mounted) return;
    if (r == null) {
      setState(() {
        _guardando = false;
        _error = 'Sin conexión. Intenta de nuevo.';
      });
      return;
    }
    if (r['ok'] == true) {
      Navigator.of(context).pop(Map<String, dynamic>.from(r['resumen'] as Map));
      return;
    }
    setState(() {
      _guardando = false;
      _error = (r['error'] as String?) ?? 'No se pudo guardar.';
    });
  }

  Widget _chips(List<Map<String, dynamic>> ops, String sel,
      ValueChanged<String> onSel) {
    return Wrap(
      spacing: 8,
      runSpacing: 8,
      children: [
        for (final o in ops)
          ChoiceChip(
            label: Text(o['nombre'] as String),
            selected: sel == o['codigo'],
            selectedColor: lima,
            labelStyle: TextStyle(
                color: sel == o['codigo'] ? Colors.white : null,
                fontWeight: FontWeight.w700),
            onSelected: (_) => setState(() => onSel(o['codigo'] as String)),
          ),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final cat = _cat;
    final pais = widget.pais;
    return Padding(
      padding: EdgeInsets.only(
          left: 20,
          right: 20,
          top: 18,
          bottom: 20 + MediaQuery.of(context).viewInsets.bottom),
      child: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Container(
                  width: 44,
                  height: 44,
                  decoration: BoxDecoration(
                      color: limaSuave,
                      borderRadius: BorderRadius.circular(14)),
                  child: const Icon(Icons.account_balance_outlined, color: lima),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('Cuenta de cobro',
                          style: t.titleLarge
                              ?.copyWith(fontWeight: FontWeight.w800)),
                      Text(
                          'Dónde te transferimos lo que recibes por reservas, '
                          'ventas y torneos · ${pais.bandera} ${pais.nombre}',
                          style: t.bodySmall?.copyWith(color: textoTenue)),
                    ],
                  ),
                ),
              ],
            ),
            const SizedBox(height: 16),
            if (_cargando)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 30),
                child: Center(child: CircularProgressIndicator()),
              )
            else if (cat == null)
              Container(
                padding: const EdgeInsets.all(14),
                decoration: BoxDecoration(
                    color: estadoWarnBg,
                    borderRadius: BorderRadius.circular(14)),
                child: const Text(
                    'No pudimos cargar las opciones. Revisa tu conexión e '
                    'inténtalo de nuevo.',
                    style: TextStyle(color: estadoWarnFg)),
              )
            else ...[
              const Text('¿Cómo quieres recibir tu plata?',
                  style: TextStyle(fontWeight: FontWeight.w700)),
              const SizedBox(height: 8),
              _chips(_lista(cat['tipos']), _tipo, (v) => _tipo = v),
              if (_esBanco) ...[
                const SizedBox(height: 14),
                const Text('Banco',
                    style: TextStyle(fontWeight: FontWeight.w700)),
                const SizedBox(height: 8),
                _chips(_lista(cat['bancos']), _banco, (v) => _banco = v),
                const SizedBox(height: 14),
                const Text('Tipo de cuenta',
                    style: TextStyle(fontWeight: FontWeight.w700)),
                const SizedBox(height: 8),
                _chips(_lista(cat['tipos_cuenta']), _tipoCuenta,
                    (v) => _tipoCuenta = v),
              ],
              const SizedBox(height: 14),
              TextField(
                controller: _numero,
                keyboardType: TextInputType.number,
                inputFormatters: [FilteringTextInputFormatter.digitsOnly],
                decoration: InputDecoration(
                  labelText: _esBanco
                      ? 'Número de cuenta'
                      : 'Celular de ${_tipo == 'plin' ? 'Plin' : 'Yape'} '
                          '(${cat['tel_longitud']} dígitos)',
                  prefixIcon: Icon(_esBanco
                      ? Icons.numbers
                      : Icons.phone_android_outlined),
                ),
              ),
              if (_pideCci) ...[
                const SizedBox(height: 12),
                TextField(
                  controller: _cci,
                  keyboardType: TextInputType.number,
                  inputFormatters: [FilteringTextInputFormatter.digitsOnly],
                  decoration: const InputDecoration(
                    labelText: 'CCI (20 dígitos)',
                    helperText:
                        'Código interbancario: lo ves en la app de tu banco. '
                        'Con él te pagamos desde el BCP sin que cambies de banco.',
                    helperMaxLines: 2,
                    prefixIcon: Icon(Icons.swap_horiz),
                  ),
                ),
              ],
              const SizedBox(height: 12),
              TextField(
                controller: _titular,
                textCapitalization: TextCapitalization.words,
                decoration: const InputDecoration(
                  labelText: 'Titular (tal como figura en la cuenta)',
                  prefixIcon: Icon(Icons.person_outline),
                ),
              ),
              const SizedBox(height: 14),
              const Text('Documento del titular',
                  style: TextStyle(fontWeight: FontWeight.w700)),
              const SizedBox(height: 8),
              _chips(_lista(cat['documentos']), _doc, (v) => _doc = v),
              const SizedBox(height: 10),
              TextField(
                controller: _docNum,
                keyboardType: TextInputType.text,
                textCapitalization: TextCapitalization.characters,
                decoration: const InputDecoration(
                  labelText: 'Número de documento',
                  prefixIcon: Icon(Icons.badge_outlined),
                ),
              ),
              if (_error != null) ...[
                const SizedBox(height: 12),
                Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                      color: estadoBadBg,
                      borderRadius: BorderRadius.circular(12)),
                  child: Text(_error!,
                      style: const TextStyle(
                          color: estadoBadFg, fontWeight: FontWeight.w600)),
                ),
              ],
              const SizedBox(height: 16),
              SizedBox(
                width: double.infinity,
                child: FilledButton(
                  style: FilledButton.styleFrom(
                      backgroundColor: lima,
                      foregroundColor: Colors.white,
                      padding: const EdgeInsets.symmetric(vertical: 14),
                      shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(14))),
                  onPressed: _guardando ? null : _guardar,
                  child: Text(_guardando ? 'Guardando…' : 'Guardar cuenta de cobro',
                      style: const TextStyle(fontWeight: FontWeight.w800)),
                ),
              ),
              const SizedBox(height: 8),
              const Text(
                  'Solo la usamos para transferirte. Nunca se muestra a los '
                  'jugadores.',
                  style: TextStyle(color: textoTenue, fontSize: 12)),
            ],
          ],
        ),
      ),
    );
  }
}
