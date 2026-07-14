import 'package:flutter/material.dart';

import '../config/pais.dart';
import '../models/club.dart';
import '../models/models.dart';
import '../services/pagos_service.dart';
import '../state/app_state.dart';
import '../theme.dart';
import 'agregar_cancha_screen.dart';
import 'editar_cancha_screen.dart';
import 'recargar_saldo_screen.dart';
import 'registrar_cancha_screen.dart';
import '../utils/moneda.dart';

/// Canchas del dueño agrupadas por LOCAL (un local = varias canchas, posibles
/// de distintos deportes). Cada local permite agregar más canchas y editar las
/// existentes (precio, deporte, horario, fotos).
class MisCanchasScreen extends StatefulWidget {
  const MisCanchasScreen({super.key});

  @override
  State<MisCanchasScreen> createState() => _MisCanchasScreenState();
}

class _MisCanchasScreenState extends State<MisCanchasScreen> {
  @override
  void initState() {
    super.initState();
    // Al abrir, pregunta al backend si el admin ya aprobó alguna cancha pendiente
    // (quita el cartel "pendiente" y habilita reservas si así fue).
    appState.sincronizarPropiedades();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      floatingActionButton: FloatingActionButton.extended(
        backgroundColor: pino,
        foregroundColor: lima,
        onPressed: () => Navigator.of(context).push(
          MaterialPageRoute(builder: (_) => const RegistrarCanchaScreen()),
        ),
        icon: const Icon(Icons.add_location_alt),
        label: const Text('Nuevo local'),
      ),
      body: ListenableBuilder(
        listenable: appState,
        builder: (context, _) {
          final canchas = appState.misCanchas;
          final hayPendientes = canchas.any((c) => c.pendienteVerificacion);
          final locales = Club.agrupar(canchas);
          return Column(
            children: [
              _HeaderMisCanchas(
                  nLocales: locales.length, nCanchas: canchas.length),
              Expanded(
                child: RefreshIndicator(
                  onRefresh: () => appState.sincronizarPropiedades(),
                  child: canchas.isEmpty
                      ? ListView(
                          children: const [SizedBox(height: 60), _Vacio()])
                      : ListView(
                          padding: const EdgeInsets.fromLTRB(18, 16, 18, 90),
                          children: [
                            _GeneradoCard(canchas: canchas),
                            const SizedBox(height: 14),
                            const _DestacarCanchasCard(),
                            const SizedBox(height: 14),
                            if (hayPendientes) ...[
                              const _AvisoPendiente(),
                              const SizedBox(height: 14),
                            ],
                            // Tablet/landscape: grilla de 2-3 columnas.
                            if (MediaQuery.of(context).size.width >= 720)
                              _GridLocales(locales: locales)
                            else
                              for (final local in locales) ...[
                                _LocalCard(local: local),
                                const SizedBox(height: 14),
                              ],
                          ],
                        ),
                ),
              ),
            ],
          );
        },
      ),
    );
  }
}

/// Panel "Lo que Pichangol te generó": muestra las reservas y las ventas del MES
/// que le llegaron al dueño por la app. Hace VISIBLE el valor de la plataforma
/// (retención: la comisión se siente ganada, no cobrada).
class _GeneradoCard extends StatelessWidget {
  const _GeneradoCard({required this.canchas});
  final List<Cancha> canchas;

  static const _meses = [
    'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
    'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'
  ];

  String _miles(int n) {
    final s = n.toString();
    final b = StringBuffer();
    for (var i = 0; i < s.length; i++) {
      if (i > 0 && (s.length - i) % 3 == 0) b.write(',');
      b.write(s[i]);
    }
    return b.toString();
  }

  @override
  Widget build(BuildContext context) {
    final ahora = DateTime.now();
    final mesIso =
        '${ahora.year}-${ahora.month.toString().padLeft(2, '0')}'; // "2026-07"
    final ids = canchas.map((c) => c.id).toSet();
    var nReservas = 0;
    var ventas = 0;
    for (final r in appState.reservas) {
      if (!ids.contains(r.canchaId)) continue;
      if (!r.fecha.startsWith(mesIso)) continue;
      if (r.estado == EstadoReserva.noShow) continue; // no-show no es venta
      nReservas++;
      ventas += r.precio;
    }
    final mon = canchas.isNotEmpty ? canchas.first.monedaSimbolo : monedaSimbolo;
    final t = Theme.of(context).textTheme;

    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        // Verde bosque→WhatsApp: es un "logro", se resalta con la marca.
        gradient: const LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [Color(0xFF128C7E), Color(0xFF075E54)],
        ),
        borderRadius: BorderRadius.circular(18),
        boxShadow: [
          BoxShadow(
              color: const Color(0xFF075E54).withOpacity(0.30),
              blurRadius: 16,
              offset: const Offset(0, 6)),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.trending_up, color: Colors.white, size: 20),
              const SizedBox(width: 8),
              Text('Lo que Pichangol te generó',
                  style: t.titleMedium?.copyWith(
                      color: Colors.white, fontWeight: FontWeight.w800)),
            ],
          ),
          const SizedBox(height: 2),
          Text('${_meses[ahora.month - 1]} ${ahora.year}',
              style: t.bodySmall?.copyWith(color: Colors.white70)),
          const SizedBox(height: 14),
          Row(
            children: [
              Expanded(
                child: _Metrica(
                    valor: '$nReservas',
                    etiqueta: nReservas == 1 ? 'reserva' : 'reservas'),
              ),
              Container(width: 1, height: 40, color: Colors.white24),
              Expanded(
                child: _Metrica(
                    valor: '$mon ${_miles(ventas)}', etiqueta: 'reservado'),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Text(
            nReservas == 0
                ? 'Aún no tienes reservas este mes por la app. Cuando te lleguen, '
                    'verás aquí cuánto te trae Pichangol.'
                : 'Reservas que te llegaron por la app. ¡Sigue así! 🎉',
            style: t.bodySmall?.copyWith(color: Colors.white70, height: 1.3),
          ),
        ],
      ),
    );
  }
}

class _Metrica extends StatelessWidget {
  const _Metrica({required this.valor, required this.etiqueta});
  final String valor;
  final String etiqueta;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.center,
      children: [
        Text(valor,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: t.headlineSmall
                ?.copyWith(color: Colors.white, fontWeight: FontWeight.w800)),
        const SizedBox(height: 2),
        Text(etiqueta, style: t.bodySmall?.copyWith(color: Colors.white70)),
      ],
    );
  }
}

/// "Destaca tus canchas": prepago que pone tus canchas primero en Explorar (con
/// medalla), igual que las academias. Más saldo = mejor nivel (Bronce/Plata/Oro).
class _DestacarCanchasCard extends StatefulWidget {
  const _DestacarCanchasCard();
  @override
  State<_DestacarCanchasCard> createState() => _DestacarCanchasCardState();
}

class _DestacarCanchasCardState extends State<_DestacarCanchasCard> {
  Map<String, int>? _vistas; // {semana, total} de impresiones de tus canchas
  String? _paisSel; // ISO del país seleccionado para destacar (multi-país)

  @override
  void initState() {
    super.initState();
    appState.sincronizarSaldo();
    appState.cargarDestacados();
    _cargarVistas();
  }

  Future<void> _cargarVistas() async {
    final email = appState.usuario?.email;
    if (email == null || email.isEmpty) return;
    final v = await PagosService.resumenVistas([email]);
    if (mounted && v != null) setState(() => _vistas = v);
  }

  /// Nivel de destacado (0-3) según un monto de saldo. Mismos umbrales que el
  /// backend: >0 bronce, >=50 plata, >=200 oro.
  int _nivelDe(int saldo) {
    if (saldo >= 200) return 3;
    if (saldo >= 50) return 2;
    if (saldo > 0) return 1;
    return 0;
  }

  Future<void> _recargar(String iso) async {
    final monto = await Navigator.of(context).push<int>(MaterialPageRoute(
      builder: (_) => RecargarSaldoScreen(
        titulo: 'Destacar mis canchas',
        pais: paisesSoportados[iso],
      ),
    ));
    if (monto != null && mounted) {
      appState.recargarPais(iso, monto); // refleja el saldo del país al instante
      await appState.sincronizarSaldo();
      await appState.cargarDestacados();
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    // Países donde el dueño tiene canchas (por la ubicación real de cada una).
    final paises = appState.paisesDeMisCanchas;
    // País seleccionado: el elegido, o el primero (donde tiene más canchas).
    final iso = (_paisSel != null && paises.contains(_paisSel))
        ? _paisSel!
        : (paises.isNotEmpty ? paises.first : 'PE');
    final saldo = appState.saldoDePais(iso);
    final nivel = _nivelDe(saldo);
    final destacada = nivel > 0;
    // Moneda del país seleccionado (S/ Perú, Bs Bolivia…), no la del GPS.
    final mon = paisesSoportados[iso]?.moneda ??
        (appState.misCanchas.isNotEmpty
            ? appState.misCanchas.first.monedaSimbolo
            : appState.monedaSaldoSimbolo);
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [Color(0xFF128C7E), Color(0xFF075E54)],
        ),
        borderRadius: BorderRadius.circular(18),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(destacada ? Icons.star : Icons.trending_up,
                  color: Colors.white, size: 20),
              const SizedBox(width: 8),
              Text(
                  destacada
                      ? '${medallaDestacado(nivel)} Nivel ${etiquetaNivelDestacado(nivel)}'
                      : 'Destaca tus canchas',
                  style: t.titleMedium?.copyWith(
                      color: Colors.white, fontWeight: FontWeight.w800)),
            ],
          ),
          const SizedBox(height: 6),
          Text(
            destacada
                ? 'Tus canchas salen primero en Explorar. Saldo: $mon $saldo. '
                    'Más saldo = mejor posición: Plata desde $mon 50, Oro desde $mon 200.'
                : 'Pon saldo y tus canchas aparecen destacadas (arriba y con '
                    'medalla) para que más jugadores las reserven. '
                    'Bronce desde $mon 1, Plata $mon 50, Oro $mon 200.',
            style: t.bodySmall
                ?.copyWith(color: Colors.white.withOpacity(0.92), height: 1.3),
          ),
          if (_vistas != null && (_vistas!['semana'] ?? 0) > 0) ...[
            const SizedBox(height: 10),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
              decoration: BoxDecoration(
                color: Colors.white.withOpacity(0.16),
                borderRadius: BorderRadius.circular(10),
              ),
              child: Text(
                '👀 ${_vistas!['semana']} jugadores vieron tus canchas esta semana'
                '${(_vistas!['total'] ?? 0) > (_vistas!['semana'] ?? 0) ? ' · ${_vistas!['total']} en total' : ''}',
                style: t.bodySmall
                    ?.copyWith(color: Colors.white, fontWeight: FontWeight.w700),
              ),
            ),
          ],
          // Selector de PAÍS: sólo si el dueño tiene canchas en más de un país.
          // Cada país lleva su propio saldo/moneda y su propia pasarela.
          if (paises.length > 1) ...[
            const SizedBox(height: 12),
            Text('¿Dónde quieres destacar?',
                style: t.bodySmall?.copyWith(
                    color: Colors.white.withOpacity(0.92),
                    fontWeight: FontWeight.w700)),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              children: [
                for (final p in paises)
                  _PaisChip(
                    iso: p,
                    sel: p == iso,
                    onTap: () => setState(() => _paisSel = p),
                  ),
              ],
            ),
          ],
          const SizedBox(height: 12),
          SizedBox(
            width: double.infinity,
            child: FilledButton.icon(
              style: FilledButton.styleFrom(
                  backgroundColor: Colors.white, foregroundColor: lima),
              onPressed: () => _recargar(iso),
              icon: const Icon(Icons.add),
              label: Text(saldo > 0
                  ? 'Recargar y destacar ($mon $saldo)'
                  : 'Poner saldo y destacar'),
            ),
          ),
        ],
      ),
    );
  }
}

/// Chip de país para el selector de "dónde destacar" (bandera + nombre). Sobre
/// el fondo verde de la tarjeta: seleccionado = blanco sólido, resto translúcido.
class _PaisChip extends StatelessWidget {
  const _PaisChip({required this.iso, required this.sel, required this.onTap});
  final String iso;
  final bool sel;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final p = paisesSoportados[iso];
    final etiqueta = p != null ? '${p.bandera} ${p.nombre}' : iso;
    return Material(
      color: sel ? Colors.white : Colors.white.withOpacity(0.18),
      borderRadius: BorderRadius.circular(20),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(20),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
          child: Text(etiqueta,
              style: TextStyle(
                  color: sel ? const Color(0xFF075E54) : Colors.white,
                  fontWeight: FontWeight.w700,
                  fontSize: 13)),
        ),
      ),
    );
  }
}

/// Grilla de locales (2-3 columnas) para tablet/landscape.
class _GridLocales extends StatelessWidget {
  const _GridLocales({required this.locales});
  final List<Club> locales;
  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(builder: (context, cons) {
      final cols = cons.maxWidth >= 1100 ? 3 : 2;
      final w = (cons.maxWidth - 14 * (cols - 1)) / cols;
      return Wrap(
        spacing: 14,
        runSpacing: 14,
        children: [
          for (final local in locales)
            SizedBox(width: w, child: _LocalCard(local: local)),
        ],
      );
    });
  }
}

/// Header premium (degradado sage) del panel "Mis canchas", igual que la Agenda.
class _HeaderMisCanchas extends StatelessWidget {
  const _HeaderMisCanchas({required this.nLocales, required this.nCanchas});
  final int nLocales;
  final int nCanchas;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return Container(
      width: double.infinity,
      padding: EdgeInsets.fromLTRB(
          22, 18 + MediaQuery.of(context).padding.top, 22, 20),
      decoration: const BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [lima, teal], // verde WhatsApp
        ),
        borderRadius: BorderRadius.vertical(bottom: Radius.circular(24)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Mis canchas',
              style: t.headlineSmall
                  ?.copyWith(color: Colors.white, fontWeight: FontWeight.w700)),
          const SizedBox(height: 2),
          Text(
            nCanchas == 0
                ? 'Registra o reclama tu primer local'
                : '$nLocales ${nLocales == 1 ? 'local' : 'locales'} · '
                    '$nCanchas ${nCanchas == 1 ? 'cancha' : 'canchas'}',
            style: t.bodyMedium?.copyWith(color: Colors.white70),
          ),
        ],
      ),
    );
  }
}

/// Aviso para el dueño cuando tiene canchas en revisión.
class _AvisoPendiente extends StatelessWidget {
  const _AvisoPendiente();

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: const Color(0xFFFBF3E2),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: const Color(0xFFF0DDB8)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text('⏳', style: TextStyle(fontSize: 18)),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Tienes canchas en revisión',
                    style: t.bodyMedium?.copyWith(
                        fontWeight: FontWeight.w800, color: clayOscuro)),
                const SizedBox(height: 3),
                Text(
                  'Ya puedes editar precio, deporte, horario y fotos tocando la '
                  'cancha. Cuando el equipo apruebe la propiedad se habilitan las '
                  'reservas. Desliza hacia abajo para actualizar el estado.',
                  style:
                      t.bodySmall?.copyWith(color: textoTenue, height: 1.35),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// Tarjeta de un LOCAL: cabecera + sus canchas (editar al tocar) + botón para
/// agregar otra cancha al mismo local.
class _LocalCard extends StatelessWidget {
  const _LocalCard({required this.local});
  final Club local;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final cs = Theme.of(context).colorScheme;
    final n = local.canchas.length;
    return Container(
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: trazo),
      ),
      padding: const EdgeInsets.fromLTRB(14, 14, 14, 6),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(Icons.storefront, color: cs.primary, size: 20),
              const SizedBox(width: 8),
              Expanded(
                child: Text(local.nombre,
                    style: t.titleMedium?.copyWith(fontWeight: FontWeight.w800),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis),
              ),
              Text('$n ${n == 1 ? 'cancha' : 'canchas'}',
                  style: t.bodySmall?.copyWith(color: textoTenueDe(context))),
            ],
          ),
          if (local.direccion != null) ...[
            const SizedBox(height: 3),
            Text(local.direccion!,
                style: t.bodySmall?.copyWith(color: textoTenueDe(context)),
                maxLines: 1,
                overflow: TextOverflow.ellipsis),
          ],
          const SizedBox(height: 8),
          for (final c in local.canchas) _FilaCancha(cancha: c),
          Align(
            alignment: Alignment.centerLeft,
            child: TextButton.icon(
              onPressed: () => Navigator.of(context).push(
                MaterialPageRoute(
                    builder: (_) => AgregarCanchaScreen(local: local.principal)),
              ),
              icon: Icon(Icons.add, color: cs.primary, size: 20),
              label: Text('Agregar cancha',
                  style:
                      TextStyle(color: cs.primary, fontWeight: FontWeight.w700)),
            ),
          ),
        ],
      ),
    );
  }
}

/// Una cancha dentro del local: punto del deporte, nombre, deporte/precio/horario
/// y acceso a editar. Marca "⏳" si está pendiente de verificación.
class _FilaCancha extends StatelessWidget {
  const _FilaCancha({required this.cancha});
  final Cancha cancha;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return InkWell(
      borderRadius: BorderRadius.circular(12),
      onTap: () => Navigator.of(context).push(
        MaterialPageRoute(builder: (_) => EditarCanchaScreen(cancha: cancha)),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 9),
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
                      style:
                          t.bodyMedium?.copyWith(fontWeight: FontWeight.w700),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis),
                  Text(
                    '${cancha.deporte.etiqueta} · ${cancha.monedaSimbolo} ${cancha.precioHora.toStringAsFixed(2)}/h · '
                    '${cancha.horaApertura}–${cancha.horaCierre}',
                    style: t.bodySmall?.copyWith(color: textoTenueDe(context)),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                ],
              ),
            ),
            if (cancha.pendienteVerificacion)
              Container(
                margin: const EdgeInsets.only(right: 6),
                padding:
                    const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                decoration: BoxDecoration(
                    color: const Color(0xFFFBEAD2),
                    borderRadius: BorderRadius.circular(999)),
                child: const Text('⏳ Por verificar',
                    style: TextStyle(
                        color: clayOscuro,
                        fontSize: 10,
                        fontWeight: FontWeight.w700)),
              ),
            Icon(Icons.chevron_right, color: textoTenueDe(context)),
          ],
        ),
      ),
    );
  }
}

class _Vacio extends StatelessWidget {
  const _Vacio();

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.add_location_alt, size: 64, color: verdeClaro),
            const SizedBox(height: 16),
            Text('Aún no registras canchas',
                style: t.titleMedium?.copyWith(fontWeight: FontWeight.w700)),
            const SizedBox(height: 6),
            Text(
              'Registra tu local para que aparezca en Pichangol; luego puedes '
              'agregarle todas las canchas que tengas.',
              textAlign: TextAlign.center,
              style: t.bodyMedium?.copyWith(color: textoTenueDe(context)),
            ),
            const SizedBox(height: 18),
            FilledButton.icon(
              style: FilledButton.styleFrom(
                  backgroundColor: pino, foregroundColor: lima),
              onPressed: () => Navigator.of(context).push(
                MaterialPageRoute(
                    builder: (_) => const RegistrarCanchaScreen()),
              ),
              icon: const Icon(Icons.add_location_alt),
              label: const Text('Registrar mi local'),
            ),
          ],
        ),
      ),
    );
  }
}
