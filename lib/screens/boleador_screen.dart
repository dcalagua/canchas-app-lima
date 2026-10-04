import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../config/pais.dart';
import '../models/boleador.dart';
import '../models/models.dart';
import '../services/pagos_service.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/cargando_pichangol.dart';
import '../widgets/dialogo_pichangol.dart';
import '../widgets/responsive.dart';
import 'verificar_identidad_screen.dart';
import '../widgets/icono_vivo.dart';

/// "Soy boleador" (Perfil → Ser boleador; módulo Boleadores, sep-2026). Mismo
/// flujo que `/anfitrion/boleador` de la web: solicitudes PENDIENTES arriba
/// (Aceptar · ganas X / No puedo), confirmadas, y el perfil por SELECCIÓN
/// (deporte, categoría de la Liga Pichangol, tarifa por turno, locales
/// verificados, días y franja, etiquetas). Exige identidad verificada.
class BoleadorScreen extends StatefulWidget {
  const BoleadorScreen({super.key});

  @override
  State<BoleadorScreen> createState() => _BoleadorScreenState();
}

class _BoleadorScreenState extends State<BoleadorScreen> {
  BoleadorConfig? _cfg;
  bool _cargando = true;
  bool _guardando = false;
  bool _ocupado = false; // aceptando/rechazando

  // Formulario (todo por selección).
  String _deporte = 'tenis';
  String _categoria = '';
  double _tarifa = 0;
  final Set<String> _canchas = {};
  final Set<int> _dias = {1, 2, 3, 4, 5, 6, 7};
  String _desde = '07:00';
  String _hasta = '22:00';
  final Set<String> _etiquetas = {};
  bool _activo = true;
  final TextEditingController _celular = TextEditingController();
  final TextEditingController _otraTarifa = TextEditingController();

  String get _email => (appState.usuario?.email ?? '').trim().toLowerCase();
  PaisConfig get _pais => appState.paisBilletera;
  String get _sim => _cfg?.simbolo ?? _pais.moneda;

  @override
  void initState() {
    super.initState();
    _cargar();
  }

  @override
  void dispose() {
    _celular.dispose();
    _otraTarifa.dispose();
    super.dispose();
  }

  Future<void> _cargar() async {
    // Device-first: pinta el perfil cacheado y refresca en silencio.
    await Boleadores.cargarCache(_email);
    _aplicarPerfil(Boleadores.perfil.value);
    _cfg = await Boleadores.config(_pais);
    if (mounted) setState(() => _cargando = false);
    await Boleadores.refrescarPerfil(_email);
    await Boleadores.refrescarSolicitudes(_email);
    if (!mounted) return;
    setState(() => _aplicarPerfil(Boleadores.perfil.value));
  }

  void _aplicarPerfil(PerfilBoleador? p) {
    if (p == null) {
      if (_celular.text.isEmpty) _celular.text = appState.miCelular;
      return;
    }
    _deporte = p.deporte;
    _categoria = p.categoria;
    _tarifa = p.tarifa;
    _canchas
      ..clear()
      ..addAll(p.canchas);
    _dias
      ..clear()
      ..addAll(p.dias);
    _desde = p.desde;
    _hasta = p.hasta;
    _etiquetas
      ..clear()
      ..addAll(p.etiquetas);
    _activo = p.activo;
    _celular.text = p.celular.isNotEmpty ? p.celular : appState.miCelular;
    final cfg = _cfg;
    if (cfg != null && !cfg.tarifas.contains(_tarifa) && _tarifa > 0) {
      _otraTarifa.text = _fmt(_tarifa);
    }
  }

  static String _fmt(double v) =>
      v == v.roundToDouble() ? v.toStringAsFixed(0) : v.toStringAsFixed(2);

  /// Locales VERIFICADOS de Pichangol donde se juega este deporte (una tarjeta
  /// por local; marcar el local marca todas sus canchas).
  List<({String club, String zona, List<String> ids})> get _locales {
    final dep = deportePorNombre(_deporte);
    final porClub = <String, ({String zona, List<String> ids})>{};
    for (final c in [...appState.canchasRemotas, ...appState.canchasExtra]) {
      if (!c.registrada || !c.verificada || c.eliminada || c.dueno.isEmpty) {
        continue;
      }
      if (dep != null && !c.deportesJugables.contains(dep)) continue;
      if (!c.permiteBoleadores) continue;
      final club = c.club.trim().isEmpty ? c.nombre.trim() : c.club.trim();
      final e = porClub.putIfAbsent(
          club, () => (zona: c.zonaMostrable, ids: <String>[]));
      if (!e.ids.contains(c.id)) e.ids.add(c.id);
    }
    return [
      for (final e in porClub.entries)
        (club: e.key, zona: e.value.zona, ids: e.value.ids),
    ]..sort((a, b) => a.club.compareTo(b.club));
  }

  Future<void> _guardar() async {
    final cfg = _cfg ?? BoleadorConfig.local(_pais);
    final otra = double.tryParse(_otraTarifa.text.trim().replaceAll(',', '.'));
    final tarifa = otra != null && otra > 0 ? otra : _tarifa;
    if (_categoria.isEmpty) {
      await avisarPichangol(context,
          titulo: 'Falta tu categoría',
          mensaje:
              'Elige tu categoría de la Liga Pichangol (5P, 5A, 5B, 4ta…).',
          icono: Icons.sports_tennis);
      return;
    }
    if (tarifa <= 0 || tarifa > cfg.tarifaMax) {
      await avisarPichangol(context,
          titulo: 'Revisa tu tarifa',
          mensaje:
              'Elige cuánto cobras por turno (hasta $_sim ${_fmt(cfg.tarifaMax)}).',
          icono: Icons.payments_outlined);
      return;
    }
    if (_canchas.isEmpty) {
      await avisarPichangol(context,
          titulo: 'Elige tus locales',
          mensaje: 'Marca al menos un local donde atiendes.',
          icono: Icons.place_outlined);
      return;
    }
    if (_dias.isEmpty) {
      await avisarPichangol(context,
          titulo: 'Elige tus días',
          mensaje: 'Marca al menos un día de la semana.',
          icono: Icons.event_outlined);
      return;
    }
    setState(() => _guardando = true);
    final r = await PagosService.guardarPerfilBoleador({
      'email': _email,
      'nombre': appState.usuario?.nombre ?? '',
      'foto': appState.usuario?.fotoUrl ?? '',
      'celular': _celular.text.trim(),
      'deporte': _deporte,
      'categoria': _categoria,
      'tarifa': tarifa,
      'canchas': _canchas.toList(),
      'disponibilidad': {
        'dias': (_dias.toList()..sort()),
        'desde': _desde,
        'hasta': _hasta,
      },
      'etiquetas': _etiquetas.toList(),
      'activo': _activo,
    });
    if (!mounted) return;
    setState(() => _guardando = false);
    if (r == null) {
      await avisarPichangol(context,
          titulo: 'Sin conexión',
          mensaje: 'No se pudo guardar. Inténtalo de nuevo.',
          icono: Icons.wifi_off);
      return;
    }
    if (r['ok'] != true) {
      final err = (r['error'] ?? '').toString();
      if (err == 'verificacion_requerida') {
        await _pedirVerificacion();
        return;
      }
      await avisarPichangol(context,
          titulo: 'Revisa tu perfil',
          mensaje: switch (err) {
            'categoria_requerida' => 'Elige tu categoría.',
            'canchas_requeridas' => 'Marca al menos un local.',
            'tarifa_invalida' => 'La tarifa no es válida.',
            'cancha_invalida' => 'Uno de los locales ya no está disponible.',
            _ => 'No se pudo guardar.',
          },
          icono: Icons.error_outline);
      return;
    }
    await Boleadores.refrescarPerfil(_email);
    if (!mounted) return;
    setState(() => _aplicarPerfil(Boleadores.perfil.value));
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        backgroundColor: pino,
        content: Text(_activo
            ? '✅ Perfil guardado · ya recibes solicitudes'
            : '✅ Perfil guardado (pausado: no recibes solicitudes)')));
  }

  Future<void> _pedirVerificacion() async {
    final ir = await confirmarPichangol(context,
        titulo: 'Verifica tu identidad',
        mensaje:
            'Vas a estar en una cancha con jugadores que no te conocen: por '
            'eso todo ${_cfg?.nombre.toLowerCase() ?? 'boleador'} de Pichangol '
            'tiene su ${_pais.docId} validado. Toma un minuto.',
        textoConfirmar: 'Verificar ahora',
        icono: Icons.verified_user_outlined);
    if (ir && mounted) {
      await Navigator.of(context).push(MaterialPageRoute(
          builder: (_) => const VerificarIdentidadScreen()));
      if (mounted) setState(() {});
    }
  }

  Future<void> _responder(SolicitudBoleo s, String accion) async {
    if (_ocupado) return;
    final esAceptar = accion == 'aceptar';
    if (!esAceptar) {
      final ok = await confirmarPichangol(context,
          titulo: accion == 'cancelar' ? '¿Cancelar este boleo?' : '¿No puedes?',
          mensaje: accion == 'cancelar'
              ? 'Se le devolverá al jugador tu parte. Dos cancelaciones en 90 '
                  'días pausan tu perfil.'
              : 'Le devolvemos al jugador tu parte y buscará a otro. No afecta '
                  'tu perfil.',
          textoConfirmar: accion == 'cancelar' ? 'Sí, cancelar' : 'No puedo',
          destructivo: true,
          icono: Icons.event_busy_outlined);
      if (!ok || !mounted) return;
    }
    setState(() => _ocupado = true);
    final r = await PagosService.responderBoleo(
        solicitudId: s.id, accion: accion, email: _email);
    if (!mounted) return;
    setState(() => _ocupado = false);
    if (r == null) {
      await avisarPichangol(context,
          titulo: 'Sin conexión',
          mensaje: 'No se pudo enviar tu respuesta. Inténtalo de nuevo.',
          icono: Icons.wifi_off);
      return;
    }
    if (r['ok'] != true) {
      final err = (r['error'] ?? '').toString();
      await avisarPichangol(context,
          titulo: 'No se pudo',
          mensaje: switch (err) {
            'vencida' => 'Esta solicitud ya venció y se le devolvió al jugador.',
            'cruce' => 'Ya aceptaste otro boleo a esa hora.',
            'pausado' => 'Tu perfil está pausado por faltas recientes.',
            _ => 'La solicitud ya no está $err.',
          },
          icono: Icons.info_outline);
      await Boleadores.refrescarSolicitudes(_email);
      if (mounted) setState(() {});
      return;
    }
    await Boleadores.refrescarSolicitudes(_email);
    if (!mounted) return;
    setState(() {});
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        backgroundColor: esAceptar ? pino : clayOscuro,
        content: Text(esAceptar
            ? '✅ Confirmado · $_sim ${s.neto.toStringAsFixed(2)} quedan por recibir al terminar'
            : 'Listo, se le devolvió al jugador su parte')));
  }

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final cfg = _cfg ?? BoleadorConfig.local(_pais);
    final nombre = cfg.nombre;
    final verificado = appState.jugadorVerificado;
    final perfil = Boleadores.perfil.value;
    final pend = Boleadores.comoBoleador.where((s) => s.pendiente).toList();
    final acept = Boleadores.comoBoleador.where((s) => s.aceptada).toList();
    final hist = Boleadores.comoBoleador.where((s) => !s.viva).take(10).toList();
    return Scaffold(
      backgroundColor: papel,
      appBar: AppBar(
        title: Text('Soy ${nombre.toLowerCase()}'),
        actions: [
          IconButton(
            tooltip: 'Actualizar',
            onPressed: _cargando ? null : () => _cargar(),
            icon: const Icon(Icons.refresh),
          ),
        ],
      ),
      body: _cargando
          ? const CargandoPichangol()
          : AnchoTablet(
              maxWidth: 640,
              child: RefreshIndicator(
                onRefresh: _cargar,
                child: ListView(
                  padding: const EdgeInsets.fromLTRB(16, 12, 16, 32),
                  children: [
                    _Intro(nombre: nombre, cfg: cfg, perfil: perfil),
                    if (!verificado) ...[
                      const SizedBox(height: 12),
                      _Candado(nombre: nombre, pais: _pais, onTap: _pedirVerificacion),
                    ],
                    if (pend.isNotEmpty) ...[
                      const SizedBox(height: 18),
                      _Titulo('Solicitudes por responder', badge: pend.length),
                      for (final s in pend)
                        _TarjetaSolicitud(
                            s: s,
                            ocupado: _ocupado,
                            onAceptar: () => _responder(s, 'aceptar'),
                            onRechazar: () => _responder(s, 'rechazar')),
                    ],
                    if (acept.isNotEmpty) ...[
                      const SizedBox(height: 18),
                      const _Titulo('Confirmados'),
                      for (final s in acept)
                        _TarjetaSolicitud(
                            s: s,
                            ocupado: _ocupado,
                            onCancelar: () => _responder(s, 'cancelar')),
                    ],
                    const SizedBox(height: 18),
                    const _Titulo('Mi perfil'),
                    _tarjetaPerfil(context, cfg, verificado),
                    if (hist.isNotEmpty) ...[
                      const SizedBox(height: 18),
                      const _Titulo('Historial'),
                      for (final s in hist) _TarjetaSolicitud(s: s, ocupado: true),
                    ],
                  ],
                ),
              ),
            ),
    );
  }

  Widget _tarjetaPerfil(BuildContext context, BoleadorConfig cfg, bool verificado) {
    final t = Theme.of(context).textTheme;
    final locales = _locales;
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: trazo),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _label('Deporte'),
          _chipsTexto(
            [for (final d in cfg.deportes) (d, d == 'padel' ? '🏓 Pádel' : '🎾 Tenis')],
            {_deporte},
            (v) => setState(() {
              _deporte = v;
              _canchas.clear();
            }),
          ),
          const SizedBox(height: 14),
          _label('Mi categoría (Liga Pichangol)'),
          _chipsTexto([for (final c in cfg.categorias) (c, c)], {_categoria},
              (v) => setState(() => _categoria = v)),
          const SizedBox(height: 14),
          _label('Tarifa por turno'),
          Text(
              'Lo que cobras por cada turno de la cancha. Pichangol descuenta '
              '$_sim ${_fmt(cfg.comision)} por turno y el resto queda por recibir '
              'en tu billetera al terminar el boleo.',
              style: t.bodySmall?.copyWith(color: textoTenue, height: 1.3)),
          const SizedBox(height: 8),
          _chipsTexto(
            [for (final v in cfg.tarifas) (_fmt(v), '$_sim ${_fmt(v)}')],
            {_otraTarifa.text.trim().isEmpty ? _fmt(_tarifa) : ''},
            (v) => setState(() {
              _tarifa = double.parse(v);
              _otraTarifa.clear();
            }),
          ),
          const SizedBox(height: 8),
          TextField(
            controller: _otraTarifa,
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            inputFormatters: [
              FilteringTextInputFormatter.allow(RegExp(r'[0-9.,]')),
              LengthLimitingTextInputFormatter(7),
            ],
            onChanged: (_) => setState(() {}),
            decoration: InputDecoration(
              labelText: 'Otro monto ($_sim)',
              hintText: 'p. ej. 35',
              isDense: true,
            ),
          ),
          if (_tarifaVisible > 0) ...[
            const SizedBox(height: 6),
            Text(
                'Por cada turno cobras $_sim ${_fmt(_tarifaVisible)} y recibes '
                '$_sim ${_fmt((_tarifaVisible - cfg.comision).clamp(0, double.infinity))}.',
                style: const TextStyle(
                    color: lima, fontWeight: FontWeight.w700, fontSize: 12.5)),
          ],
          const SizedBox(height: 14),
          _label('Locales donde atiendes'),
          Text(
              'Solo locales verificados en Pichangol. Marca todos los que te '
              'queden bien.',
              style: t.bodySmall?.copyWith(color: textoTenue)),
          const SizedBox(height: 8),
          if (locales.isEmpty)
            Text('Aún no hay locales verificados de $_deporte cerca. Prueba '
                'de nuevo más tarde.',
                style: t.bodySmall?.copyWith(color: textoTenue))
          else
            for (final l in locales)
              _TarjetaLocal(
                club: l.club,
                zona: l.zona,
                n: l.ids.length,
                marcado: l.ids.any(_canchas.contains),
                onTap: () => setState(() {
                  if (l.ids.any(_canchas.contains)) {
                    _canchas.removeAll(l.ids);
                  } else {
                    _canchas.addAll(l.ids);
                  }
                }),
              ),
          const SizedBox(height: 14),
          _label('Disponibilidad'),
          _chipsTexto(
            const [
              ('1', 'Lun'),
              ('2', 'Mar'),
              ('3', 'Mié'),
              ('4', 'Jue'),
              ('5', 'Vie'),
              ('6', 'Sáb'),
              ('7', 'Dom'),
            ],
            _dias.map((d) => '$d').toSet(),
            (v) => setState(() {
              final d = int.parse(v);
              _dias.contains(d) ? _dias.remove(d) : _dias.add(d);
            }),
            multi: true,
          ),
          const SizedBox(height: 10),
          Row(
            children: [
              Expanded(child: _selectorHora('Desde', _desde, (v) => setState(() => _desde = v))),
              const SizedBox(width: 10),
              Expanded(child: _selectorHora('Hasta', _hasta, (v) => setState(() => _hasta = v))),
            ],
          ),
          const SizedBox(height: 14),
          _label('Sobre ti (elige)'),
          _chipsTexto([for (final e in cfg.etiquetas) (e, e)], _etiquetas,
              (v) => setState(() {
                    _etiquetas.contains(v) ? _etiquetas.remove(v) : _etiquetas.add(v);
                  }),
              multi: true),
          const SizedBox(height: 14),
          TextField(
            controller: _celular,
            keyboardType: TextInputType.phone,
            inputFormatters: [
              FilteringTextInputFormatter.digitsOnly,
              LengthLimitingTextInputFormatter(15),
            ],
            decoration: InputDecoration(
              labelText: 'Celular (WhatsApp)',
              prefixText: '${_pais.bandera} +${_pais.codigoTel} ',
              isDense: true,
            ),
          ),
          const SizedBox(height: 10),
          SwitchListTile(
            contentPadding: EdgeInsets.zero,
            value: _activo,
            activeColor: pino,
            title: const Text('Recibir solicitudes',
                style: TextStyle(fontWeight: FontWeight.w700)),
            subtitle: Text(
                _activo ? 'Apareces al reservar en tus locales' : 'Pausado: nadie te ve',
                style: const TextStyle(fontSize: 12.5)),
            onChanged: (v) => setState(() => _activo = v),
          ),
          const SizedBox(height: 8),
          SizedBox(
            width: double.infinity,
            child: FilledButton(
              style: FilledButton.styleFrom(
                  backgroundColor: lima,
                  foregroundColor: Colors.white,
                  padding: const EdgeInsets.symmetric(vertical: 15)),
              onPressed: _guardando
                  ? null
                  : (verificado ? _guardar : _pedirVerificacion),
              child: Text(
                  _guardando
                      ? 'Guardando…'
                      : verificado
                          ? 'Guardar mi perfil'
                          : 'Verificar identidad para continuar',
                  style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 15)),
            ),
          ),
        ],
      ),
    );
  }

  double get _tarifaVisible {
    final otra = double.tryParse(_otraTarifa.text.trim().replaceAll(',', '.'));
    return otra != null && otra > 0 ? otra : _tarifa;
  }

  Widget _label(String s) => Padding(
        padding: const EdgeInsets.only(bottom: 6),
        child: Text(s, style: const TextStyle(fontWeight: FontWeight.w800)),
      );

  Widget _chipsTexto(List<(String, String)> ops, Set<String> sel,
      ValueChanged<String> onSel,
      {bool multi = false}) {
    return Wrap(
      spacing: 8,
      runSpacing: 8,
      children: [
        for (final (v, txt) in ops)
          ChoiceChip(
            label: Text(txt),
            selected: sel.contains(v),
            selectedColor: lima,
            labelStyle: TextStyle(
                color: sel.contains(v) ? Colors.white : null,
                fontWeight: FontWeight.w700),
            onSelected: (_) => onSel(v),
          ),
      ],
    );
  }

  Widget _selectorHora(String label, String valor, ValueChanged<String> onSel) {
    final horas = [for (var h = 5; h <= 23; h++) '${h.toString().padLeft(2, '0')}:00'];
    return DropdownButtonFormField<String>(
      value: horas.contains(valor) ? valor : horas.first,
      decoration: InputDecoration(labelText: label, isDense: true),
      items: [for (final h in horas) DropdownMenuItem(value: h, child: Text(h))],
      onChanged: (v) {
        if (v != null) onSel(v);
      },
    );
  }
}

class _Intro extends StatelessWidget {
  const _Intro({required this.nombre, required this.cfg, required this.perfil});
  final String nombre;
  final BoleadorConfig cfg;
  final PerfilBoleador? perfil;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final estado = perfil == null
        ? 'Aún no registrado'
        : perfil!.activo
            ? 'Activo · recibes solicitudes'
            : 'Pausado';
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: limaSuave,
        borderRadius: BorderRadius.circular(18),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text('🎾', style: TextStyle(fontSize: 30)),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(
                      child: Text('Soy ${nombre.toLowerCase()}',
                          style: t.titleMedium?.copyWith(fontWeight: FontWeight.w800)),
                    ),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 3),
                      decoration: BoxDecoration(
                        color: perfil?.activo == true ? pino : Colors.white,
                        borderRadius: BorderRadius.circular(999),
                      ),
                      child: Text(estado,
                          style: TextStyle(
                              fontSize: 11,
                              fontWeight: FontWeight.w800,
                              color: perfil?.activo == true ? Colors.white : textoTenue)),
                    ),
                  ],
                ),
                const SizedBox(height: 4),
                Text(
                    'Los jugadores te contratan por turno al reservar la cancha. '
                    'Tú aceptas o rechazas cada solicitud. Pichangol descuenta '
                    '${cfg.simbolo} ${_BoleadorScreenState._fmt(cfg.comision)} por turno y el resto '
                    'queda por recibir en tu billetera al terminar el boleo.',
                    style: t.bodySmall?.copyWith(color: bosque, height: 1.35)),
                if (perfil != null && perfil!.aceptadas > 0) ...[
                  const SizedBox(height: 6),
                  Text('⭐ ${perfil!.aceptadas} boleo${perfil!.aceptadas == 1 ? '' : 's'} aceptado${perfil!.aceptadas == 1 ? '' : 's'}',
                      style: t.bodySmall?.copyWith(fontWeight: FontWeight.w700, color: bosque)),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _Candado extends StatelessWidget {
  const _Candado({required this.nombre, required this.pais, required this.onTap});
  final String nombre;
  final PaisConfig pais;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: estadoWarnBg,
        borderRadius: BorderRadius.circular(16),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const IconoVivo(Icons.verified_user_outlined, size: 20, color: clayOscuro),
              const SizedBox(width: 8),
              Expanded(
                child: Text('Verifica tu identidad para ser ${nombre.toLowerCase()}',
                    style: const TextStyle(fontWeight: FontWeight.w800)),
              ),
            ],
          ),
          const SizedBox(height: 6),
          Text(
              'Vas a estar en una cancha con jugadores que no te conocen: por eso '
              'todo ${nombre.toLowerCase()} de Pichangol tiene su ${pais.docId} '
              'validado. Toma un minuto.',
              style: const TextStyle(fontSize: 13, height: 1.3)),
          const SizedBox(height: 8),
          Align(
            alignment: Alignment.centerRight,
            child: TextButton.icon(
              onPressed: onTap,
              icon: const Icon(Icons.arrow_forward, size: 16),
              label: const Text('Verificar ahora',
                  style: TextStyle(fontWeight: FontWeight.w800)),
            ),
          ),
        ],
      ),
    );
  }
}

class _Titulo extends StatelessWidget {
  const _Titulo(this.texto, {this.badge = 0});
  final String texto;
  final int badge;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        children: [
          Text(texto, style: t.titleMedium?.copyWith(fontWeight: FontWeight.w800)),
          if (badge > 0) ...[
            const SizedBox(width: 8),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
              decoration: BoxDecoration(
                  color: clayOscuro, borderRadius: BorderRadius.circular(999)),
              child: Text('$badge',
                  style: const TextStyle(
                      color: Colors.white, fontWeight: FontWeight.w800, fontSize: 12)),
            ),
          ],
        ],
      ),
    );
  }
}

class _TarjetaLocal extends StatelessWidget {
  const _TarjetaLocal(
      {required this.club,
      required this.zona,
      required this.n,
      required this.marcado,
      required this.onTap});
  final String club;
  final String zona;
  final int n;
  final bool marcado;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(14),
      child: Container(
        margin: const EdgeInsets.only(bottom: 8),
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
        decoration: BoxDecoration(
          color: marcado ? limaSuave : Colors.white,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: marcado ? pino : trazo, width: marcado ? 1.6 : 1),
        ),
        child: Row(
          children: [
            const Text('🏟️', style: TextStyle(fontSize: 20)),
            const SizedBox(width: 10),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(club, style: const TextStyle(fontWeight: FontWeight.w800)),
                  Text('${zona.isNotEmpty ? '$zona · ' : ''}$n cancha${n == 1 ? '' : 's'}',
                      style: const TextStyle(fontSize: 12.5, color: textoTenue)),
                ],
              ),
            ),
            Icon(marcado ? Icons.check_circle : Icons.radio_button_unchecked,
                color: marcado ? pino : trazo),
          ],
        ),
      ),
    );
  }
}

/// Tarjeta de una solicitud (pendiente: Aceptar / No puedo; aceptada: Cancelar;
/// historial: solo lectura).
class _TarjetaSolicitud extends StatelessWidget {
  const _TarjetaSolicitud(
      {required this.s,
      required this.ocupado,
      this.onAceptar,
      this.onRechazar,
      this.onCancelar});
  final SolicitudBoleo s;
  final bool ocupado;
  final VoidCallback? onAceptar;
  final VoidCallback? onRechazar;
  final VoidCallback? onCancelar;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final pend = s.pendiente;
    final foto = appState.fotoDe(s.clienteEmail);
    final nombre = s.clienteNombre.isNotEmpty ? s.clienteNombre : 'Jugador';
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: pend ? const Color(0xFFF2C94C) : trazo, width: pend ? 1.6 : 1),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              CircleAvatar(
                radius: 18,
                backgroundColor: limaSuave,
                backgroundImage: foto != null && foto.isNotEmpty
                    ? CachedNetworkImageProvider(foto)
                    : null,
                child: foto == null || foto.isEmpty
                    ? Text(nombre[0].toUpperCase(),
                        style: const TextStyle(fontWeight: FontWeight.w800, color: bosque))
                    : null,
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('${AppState.fechaBonita(s.fecha)} · ${s.horaInicio}–${s.horaFin}',
                        style: t.bodyMedium?.copyWith(fontWeight: FontWeight.w800)),
                    Text('${s.lugar} · $nombre · ${s.turnos} turno${s.turnos == 1 ? '' : 's'}',
                        style: t.bodySmall?.copyWith(color: textoTenue)),
                  ],
                ),
              ),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                decoration: BoxDecoration(
                  color: s.aceptada ? pino : (pend ? const Color(0xFFFFF4D6) : papel),
                  borderRadius: BorderRadius.circular(999),
                ),
                child: Text(pend ? 'Por responder' : s.etiquetaEstado,
                    style: TextStyle(
                        fontSize: 11,
                        fontWeight: FontWeight.w800,
                        color: s.aceptada ? Colors.white : textoTenue)),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Text(
              'Cobras ${s.simbolo} ${s.monto.toStringAsFixed(2)} − comisión Pichangol '
              '${s.simbolo} ${s.comision.toStringAsFixed(2)} = ${s.simbolo} ${s.neto.toStringAsFixed(2)} '
              'por recibir al terminar el turno.',
              style: t.bodySmall?.copyWith(height: 1.3)),
          if (pend && s.venceEn != null) ...[
            const SizedBox(height: 4),
            Text(
                'Responde antes de las ${_hhmm(s.venceEn!)}; si no, se le devuelve al jugador.',
                style: t.bodySmall?.copyWith(color: textoTenue, fontSize: 12)),
          ],
          if (pend && onAceptar != null) ...[
            const SizedBox(height: 10),
            Row(
              children: [
                Expanded(
                  child: FilledButton(
                    style: FilledButton.styleFrom(
                        backgroundColor: pino, foregroundColor: Colors.white),
                    onPressed: ocupado ? null : onAceptar,
                    child: Text('✅ Aceptar · ganas ${s.simbolo} ${s.neto.toStringAsFixed(2)}',
                        style: const TextStyle(fontWeight: FontWeight.w800)),
                  ),
                ),
                const SizedBox(width: 8),
                OutlinedButton(
                  onPressed: ocupado ? null : onRechazar,
                  child: const Text('No puedo', style: TextStyle(fontWeight: FontWeight.w700)),
                ),
              ],
            ),
          ],
          if (s.aceptada && onCancelar != null) ...[
            const SizedBox(height: 8),
            Align(
              alignment: Alignment.centerRight,
              child: TextButton(
                onPressed: ocupado ? null : onCancelar,
                style: TextButton.styleFrom(foregroundColor: clayOscuro),
                child: const Text('Cancelar este boleo',
                    style: TextStyle(fontWeight: FontWeight.w700)),
              ),
            ),
          ],
        ],
      ),
    );
  }

  static String _hhmm(DateTime d) {
    final hoy = DateTime.now();
    final mismoDia = d.year == hoy.year && d.month == hoy.month && d.day == hoy.day;
    final hm = '${d.hour.toString().padLeft(2, '0')}:${d.minute.toString().padLeft(2, '0')}';
    return mismoDia ? hm : '${d.day}/${d.month} $hm';
  }
}
