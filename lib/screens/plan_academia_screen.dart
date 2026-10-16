import 'package:flutter/material.dart';

import '../models/academia.dart';
import '../services/academia_plan_service.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/dialogo_pichangol.dart';
import '../widgets/icono_vivo.dart';
import '../widgets/logo_academia.dart';
import '../widgets/responsive.dart';
import '../widgets/yape_auto_card.dart';
import 'crear_academia_screen.dart';
import 'recargar_saldo_screen.dart';

/// PLAN ACADEMIA (decisión del director, 10-oct-2026): suscripción mensual que
/// la academia paga a Pichangol (con prueba gratis). Sus alumnos le pagan
/// DIRECTO por Yape; Pichangol no cobra comisión. Estilo Spotify/Airbnb:
/// tarjeta de plan, beneficios, "Pagar con mi saldo" y renovación automática.
class PlanAcademiaScreen extends StatefulWidget {
  const PlanAcademiaScreen({super.key, required this.academia});
  final Academia academia;

  @override
  State<PlanAcademiaScreen> createState() => _PlanAcademiaScreenState();
}

class _PlanAcademiaScreenState extends State<PlanAcademiaScreen> {
  bool _pagando = false;
  bool _cambiandoRenovacion = false;
  bool _cargando = false;

  Academia get _ac => widget.academia;

  @override
  void initState() {
    super.initState();
    _refrescar();
  }

  Future<void> _refrescar() async {
    _cargando = AcademiaPlanService.planEnCache(_ac.id) == null;
    await AcademiaPlanService.plan(_ac.id, forzar: true);
    if (mounted) setState(() => _cargando = false);
  }

  Future<void> _pagar(PlanAcademiaEstado? est) async {
    if (_pagando) return;
    final email = appState.usuario?.email ?? '';
    if (email.isEmpty) return;
    final sim = est?.simbolo ?? _ac.monedaSimbolo;
    final precio = est?.precio ?? AcademiaPlanService.precioPlan(_ac.monedaSimbolo);
    final ok = await confirmarPichangol(
      context,
      titulo: 'Pagar Plan Academia',
      mensaje: 'Se descontarán $sim ${precio.toStringAsFixed(2)} de tu saldo '
          'Pichangol por 30 días más del Plan Academia de ${_ac.nombre}.',
      textoConfirmar: 'Pagar $sim ${precio.toStringAsFixed(2)}',
      textoCancelar: 'Ahora no',
      icono: Icons.workspace_premium,
    );
    if (!ok || !mounted) return;
    setState(() => _pagando = true);
    final r = await AcademiaPlanService.pagar(_ac.id, email);
    if (!mounted) return;
    setState(() => _pagando = false);
    if (r['ok'] == true) {
      appState.sincronizarSaldo();
      final e = AcademiaPlanService.planEnCache(_ac.id);
      await avisarPichangol(
        context,
        titulo: '¡Plan Academia activo!',
        mensaje: (e != null && e.venceTxt.isNotEmpty)
            ? 'Tu plan queda activo hasta el ${e.venceTxt}. Tus alumnos reciben '
                'sus recordatorios y pueden matricularse en línea.'
            : 'Tu plan quedó activo. Tus alumnos reciben sus recordatorios y '
                'pueden matricularse en línea.',
        textoBoton: 'Genial',
        icono: Icons.check_circle,
      );
      return;
    }
    final error = (r['error'] ?? '').toString();
    final mensaje = (r['mensaje'] ?? 'No se pudo pagar. Reintenta.').toString();
    if (error == 'falta_saldo') {
      final recargar = await confirmarPichangol(
        context,
        titulo: 'Te falta saldo',
        mensaje: mensaje,
        textoConfirmar: 'Recargar saldo',
        textoCancelar: 'Ahora no',
        icono: Icons.account_balance_wallet_outlined,
      );
      if (recargar && mounted) {
        await Navigator.of(context).push(MaterialPageRoute(
            builder: (_) => RecargarSaldoScreen(
                duenoId: appState.usuario?.email, titulo: 'Recargar saldo')));
        await appState.sincronizarSaldo();
        if (mounted) setState(() {});
      }
      return;
    }
    await avisarPichangol(
      context,
      titulo: error == 'moneda_distinta'
          ? 'Tu saldo está en otra moneda'
          : 'No se pudo pagar',
      mensaje: mensaje,
      icono: error == 'moneda_distinta'
          ? Icons.currency_exchange
          : Icons.error_outline,
    );
  }

  Future<void> _cambiarRenovacion(bool renovar) async {
    if (_cambiandoRenovacion) return;
    if (!renovar) {
      final ok = await confirmarPichangol(
        context,
        titulo: '¿Apagar la renovación automática?',
        mensaje: 'Al vencer, tu plan no se pagará solo desde tu saldo. Tus '
            'alumnos dejarán de recibir recordatorios y no podrán matricularse '
            'en línea hasta que lo pagues.',
        textoConfirmar: 'Apagar',
        textoCancelar: 'Mantener',
        destructivo: true,
      );
      if (!ok || !mounted) return;
    }
    setState(() => _cambiandoRenovacion = true);
    final r = await AcademiaPlanService.renovacion(
        _ac.id, appState.usuario?.email ?? '', renovar);
    if (!mounted) return;
    setState(() => _cambiandoRenovacion = false);
    if (r['ok'] != true) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text(
              (r['mensaje'] ?? 'No se pudo cambiar. Reintenta.').toString())));
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Plan Academia')),
      body: ValueListenableBuilder<int>(
        valueListenable: AcademiaPlanService.cambios,
        builder: (context, _, __) {
          final est = AcademiaPlanService.planEnCache(_ac.id);
          if (est == null && _cargando) {
            return const Center(child: CircularProgressIndicator(color: lima));
          }
          return RefreshIndicator(
            color: lima,
            onRefresh: _refrescar,
            child: ListView(
              padding: EdgeInsets.fromLTRB(ladoTablet(context, 16, 640), 14,
                  ladoTablet(context, 16, 640), 30),
              children: [
                _tarjetaPlan(est),
                const SizedBox(height: 18),
                const Text('Lo que incluye',
                    style:
                        TextStyle(fontWeight: FontWeight.w800, fontSize: 17)),
                const SizedBox(height: 10),
                const _Beneficio(
                    icono: Icons.notifications_active_outlined,
                    titulo: 'Recordatorios automáticos',
                    texto:
                        'Tus alumnos reciben aviso (notificación y correo) antes de que venza su cuota, el día y si se atrasan.'),
                const _Beneficio(
                    icono: Icons.how_to_reg_outlined,
                    titulo: 'Matrícula en línea',
                    texto:
                        'Se inscriben desde tu ficha en Pichangol, con tus programas, sedes y descuentos.'),
                const _Beneficio(
                    icono: Icons.dashboard_outlined,
                    titulo: 'Panel de tu academia',
                    texto:
                        'Alumnos, asistencia, evaluaciones, ranking, reportes y cobros en un solo lugar.'),
                _Beneficio(
                    icono: Icons.payments_outlined,
                    titulo: 'Cobras directo, sin comisión',
                    texto:
                        _usaQr
                            ? 'Tus alumnos te pagan a ti con tu QR y un monto único. Tu celular Android reconoce el pago y la cuota queda pagada sola.'
                            : 'Tus alumnos te yapean a ti. Confirmas cada pago con el código de seguridad de su Yape, o deja que tu celular Android lo confirme solo.'),
                const SizedBox(height: 14),
                _tarjetaYape(est),
                // Fase 2: confirmación automática leyendo la notificación de
                // Yape (solo Android, con Yape registrado y plan vigente).
                if ((_ac.cobroDirecto ?? est?.cobroDirecto) != null &&
                    est != null &&
                    est.beneficios &&
                    !est.libre) ...[
                  const SizedBox(height: 14),
                  TarjetaYapeAuto(qr: _usaQr),
                ],
                if (est != null && !est.libre) ...[
                  const SizedBox(height: 14),
                  Container(
                    decoration: BoxDecoration(
                      color: Theme.of(context).colorScheme.surface,
                      borderRadius: BorderRadius.circular(16),
                      border: Border.all(color: trazo),
                    ),
                    child: SwitchListTile(
                      value: est.autoRenovar,
                      activeColor: lima,
                      onChanged:
                          _cambiandoRenovacion ? null : _cambiarRenovacion,
                      title: const Text('Renovación automática',
                          style: TextStyle(fontWeight: FontWeight.w700)),
                      subtitle: Text(
                          est.autoRenovar
                              ? 'Se paga solo desde tu saldo al vencer.'
                              : 'Apagada: al vencer tendrás que pagarlo tú.',
                          style: const TextStyle(fontSize: 12.5)),
                    ),
                  ),
                ],
                const SizedBox(height: 14),
                const Text(
                    'Sin plan vigente tu academia sigue visible con su ficha '
                    'pública, pero no recibe matrículas en línea ni envía '
                    'recordatorios. Tus datos no se pierden.',
                    style: TextStyle(color: textoTenue, fontSize: 12.5)),
              ],
            ),
          );
        },
      ),
    );
  }

  Widget _tarjetaPlan(PlanAcademiaEstado? est) {
    final sim = est?.simbolo ?? _ac.monedaSimbolo;
    final precio =
        est?.precio ?? AcademiaPlanService.precioPlan(_ac.monedaSimbolo);
    final String estadoTxt;
    final Color pillBg;
    final Color pillFg;
    final String pill;
    if (est == null) {
      pill = 'Sin datos';
      pillBg = estadoNeutroBg;
      pillFg = estadoNeutroFg;
      estadoTxt = 'No pudimos consultar tu plan. Desliza para reintentar.';
    } else if (est.enPrueba) {
      pill = 'Prueba gratis';
      pillBg = estadoInfoBg;
      pillFg = estadoInfoFg;
      final d = est.diasRestantes ?? 0;
      estadoTxt = 'Te quedan $d ${d == 1 ? 'día' : 'días'} de prueba'
          '${est.venceTxt.isNotEmpty ? ' (hasta el ${est.venceTxt})' : ''}.';
    } else if (est.activa) {
      pill = 'Activo';
      pillBg = estadoOkBg;
      pillFg = estadoOkFg;
      estadoTxt = est.venceTxt.isNotEmpty
          ? 'Activo hasta el ${est.venceTxt}.'
          : 'Tu plan está activo.';
    } else if (est.vencida) {
      pill = 'Vencido';
      pillBg = estadoBadBg;
      pillFg = estadoBadFg;
      estadoTxt = est.venceTxt.isNotEmpty
          ? 'Tu plan venció el ${est.venceTxt}.'
          : 'Tu plan venció.';
    } else {
      pill = 'Incluido';
      pillBg = estadoOkBg;
      pillFg = estadoOkFg;
      estadoTxt = 'Tu academia tiene todas las herramientas activas.';
    }
    final puedePagar = est != null && !est.libre;
    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [bosque, verdeProfundo, teal],
        ),
        borderRadius: BorderRadius.circular(22),
        boxShadow: const [
          BoxShadow(
              color: Color(0x22000000), blurRadius: 18, offset: Offset(0, 6)),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              LogoAcademia(logoUrl: _ac.logoUrl, size: 40),
              const SizedBox(width: 10),
              Expanded(
                child: Text(_ac.nombre,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                        color: Colors.white,
                        fontWeight: FontWeight.w800,
                        fontSize: 15)),
              ),
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                decoration: BoxDecoration(
                    color: pillBg, borderRadius: BorderRadius.circular(999)),
                child: Text(pill,
                    style: TextStyle(
                        color: pillFg,
                        fontWeight: FontWeight.w800,
                        fontSize: 12)),
              ),
            ],
          ),
          const SizedBox(height: 18),
          const Text('Plan Academia',
              style: TextStyle(
                  color: Colors.white70,
                  fontWeight: FontWeight.w700,
                  fontSize: 13)),
          const SizedBox(height: 2),
          Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Text('$sim ${precio.toStringAsFixed(2)}',
                  style: const TextStyle(
                      color: Colors.white,
                      fontWeight: FontWeight.w900,
                      fontSize: 32)),
              const Padding(
                padding: EdgeInsets.only(bottom: 6, left: 4),
                child: Text('/ mes',
                    style: TextStyle(color: Colors.white70, fontSize: 14)),
              ),
            ],
          ),
          const SizedBox(height: 6),
          Text(estadoTxt,
              style: const TextStyle(color: Colors.white, fontSize: 13.5)),
          if (puedePagar) ...[
            const SizedBox(height: 16),
            SizedBox(
              width: double.infinity,
              child: FilledButton.icon(
                style: FilledButton.styleFrom(
                    backgroundColor: Colors.white,
                    foregroundColor: bosque,
                    padding: const EdgeInsets.symmetric(vertical: 14),
                    shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(14))),
                onPressed: _pagando ? null : () => _pagar(est),
                icon: _pagando
                    ? const SizedBox(
                        width: 18,
                        height: 18,
                        child: CircularProgressIndicator(
                            strokeWidth: 2.2, color: bosque))
                    : const Icon(Icons.account_balance_wallet_outlined),
                label: Text(
                    (est?.activa ?? false)
                        ? 'Adelantar 1 mes con mi saldo'
                        : 'Pagar con mi saldo · $sim ${precio.toStringAsFixed(2)}',
                    style: const TextStyle(fontWeight: FontWeight.w800)),
              ),
            ),
          ],
        ],
      ),
    );
  }

  /// Ecuador / Bolivia cobran por QR (Perú por Yape), según la sede.
  bool get _usaQr => QrApps.usaQr(_ac.pais.iso);

  Widget _tarjetaYape(PlanAcademiaEstado? est) {
    final cd = _ac.cobroDirecto ?? est?.cobroDirecto;
    return InkWell(
      borderRadius: BorderRadius.circular(16),
      onTap: () => Navigator.of(context).push(MaterialPageRoute(
          builder: (_) => CrearAcademiaScreen(academia: _ac))),
      child: Container(
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: cd == null ? estadoWarnBg : Theme.of(context).colorScheme.surface,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: trazo),
        ),
        child: Row(
          children: [
            const IconoVivo(Icons.qr_code_2, size: 26),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                      cd == null
                          ? (_usaQr ? 'Sube tu QR de cobro' : 'Registra tu Yape')
                          : (cd.esQr ? 'Cobras con tu QR' : 'Cobras en tu Yape'),
                      style: const TextStyle(
                          fontWeight: FontWeight.w800, fontSize: 14.5)),
                  Text(
                      cd == null
                          ? 'Así tus alumnos te pagan directo. Agrégalo en Editar academia.'
                          : cd.resumen,
                      style:
                          const TextStyle(color: textoTenue, fontSize: 12.5)),
                ],
              ),
            ),
            const Icon(Icons.chevron_right, color: textoTenue),
          ],
        ),
      ),
    );
  }
}

class _Beneficio extends StatelessWidget {
  const _Beneficio(
      {required this.icono, required this.titulo, required this.texto});
  final IconData icono;
  final String titulo;
  final String texto;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 40,
            height: 40,
            alignment: Alignment.center,
            decoration: BoxDecoration(
                color: limaSuave, borderRadius: BorderRadius.circular(12)),
            child: IconoVivo(icono, size: 22, color: lima),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(titulo,
                    style: const TextStyle(
                        fontWeight: FontWeight.w800, fontSize: 14.5)),
                const SizedBox(height: 2),
                Text(texto,
                    style:
                        const TextStyle(color: textoTenue, fontSize: 12.5)),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// Banner del Plan Academia para el panel del profe: "Te quedan N días de
/// prueba · Ver plan" o, rojo, "Tu plan venció…". Solo con academias por
/// suscripción. Toca → [PlanAcademiaScreen].
class BannerPlanAcademia extends StatefulWidget {
  const BannerPlanAcademia(
      {super.key, required this.academia, this.margen = EdgeInsets.zero});
  final Academia academia;
  final EdgeInsets margen;

  @override
  State<BannerPlanAcademia> createState() => _BannerPlanAcademiaState();
}

class _BannerPlanAcademiaState extends State<BannerPlanAcademia> {
  @override
  void initState() {
    super.initState();
    if (appState.academiasPorSuscripcion) {
      AcademiaPlanService.plan(widget.academia.id);
    }
  }

  @override
  Widget build(BuildContext context) {
    return ValueListenableBuilder<int>(
      valueListenable: AcademiaPlanService.cambios,
      builder: (context, _, __) {
        if (!appState.academiasPorSuscripcion) return const SizedBox.shrink();
        final est = AcademiaPlanService.planEnCache(widget.academia.id);
        if (est == null || est.libre) return const SizedBox.shrink();
        final String texto;
        final Color bg;
        final Color fg;
        final IconData icono;
        if (est.vencida) {
          texto = 'Tu Plan Academia venció. Tus alumnos no reciben '
              'recordatorios ni pueden matricularse. Actívalo';
          bg = estadoBadBg;
          fg = estadoBadFg;
          icono = Icons.error_outline;
        } else if (est.enPrueba) {
          final d = est.diasRestantes ?? 0;
          texto = 'Te quedan $d ${d == 1 ? 'día' : 'días'} de prueba · Ver plan';
          bg = estadoInfoBg;
          fg = estadoInfoFg;
          icono = Icons.card_giftcard;
        } else {
          final d = est.diasRestantes;
          // Activo: avisa en ámbar si vence pronto y no se renueva solo; si
          // no, un acceso discreto al plan.
          if (d != null && d <= 5 && !est.autoRenovar) {
            texto = 'Tu plan vence en $d ${d == 1 ? 'día' : 'días'} · Ver plan';
            bg = estadoWarnBg;
            fg = estadoWarnFg;
            icono = Icons.schedule;
          } else {
            texto = est.venceTxt.isNotEmpty
                ? 'Plan Academia activo hasta el ${est.venceTxt} · Ver plan'
                : 'Plan Academia activo · Ver plan';
            bg = estadoOkBg;
            fg = estadoOkFg;
            icono = Icons.workspace_premium;
          }
        }
        return Padding(
          padding: widget.margen,
          child: Material(
            color: bg,
            borderRadius: BorderRadius.circular(14),
            child: InkWell(
              borderRadius: BorderRadius.circular(14),
              onTap: () => Navigator.of(context).push(MaterialPageRoute(
                  builder: (_) =>
                      PlanAcademiaScreen(academia: widget.academia))),
              child: Padding(
                padding:
                    const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                child: Row(
                  children: [
                    Icon(icono, color: fg, size: 22),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Text(texto,
                          style: TextStyle(
                              color: fg,
                              fontWeight: FontWeight.w700,
                              fontSize: 13.5)),
                    ),
                    Icon(Icons.chevron_right, color: fg),
                  ],
                ),
              ),
            ),
          ),
        );
      },
    );
  }
}

/// PAYWALL del Plan Academia: sin plan vigente, las secciones de gestión
/// (alumnos, asistencia, evaluaciones, reportes…) muestran esta tarjeta en vez
/// de su contenido. Con modelo "comision" o plan vigente, muestra [child].
class CandadoPlanAcademia extends StatefulWidget {
  const CandadoPlanAcademia(
      {super.key, required this.academia, required this.child});
  final Academia academia;
  final Widget child;

  @override
  State<CandadoPlanAcademia> createState() => _CandadoPlanAcademiaState();
}

class _CandadoPlanAcademiaState extends State<CandadoPlanAcademia> {
  @override
  void initState() {
    super.initState();
    if (appState.academiasPorSuscripcion) {
      AcademiaPlanService.plan(widget.academia.id);
    }
  }

  @override
  Widget build(BuildContext context) {
    return ValueListenableBuilder<int>(
      valueListenable: AcademiaPlanService.cambios,
      builder: (context, _, __) {
        if (AcademiaPlanService.tieneBeneficios(widget.academia.id)) {
          return widget.child;
        }
        return Scaffold(
          body: Center(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(24),
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 460),
                child: TarjetaActivaPlan(academia: widget.academia),
              ),
            ),
          ),
        );
      },
    );
  }
}

/// Tarjeta "Activa tu Plan Academia" (la usa el paywall y secciones sueltas).
class TarjetaActivaPlan extends StatelessWidget {
  const TarjetaActivaPlan({super.key, required this.academia});
  final Academia academia;

  @override
  Widget build(BuildContext context) {
    final est = AcademiaPlanService.planEnCache(academia.id);
    final sim = est?.simbolo ?? academia.monedaSimbolo;
    final precio =
        est?.precio ?? AcademiaPlanService.precioPlan(academia.monedaSimbolo);
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: trazo),
        boxShadow: const [
          BoxShadow(
              color: Color(0x0F000000), blurRadius: 14, offset: Offset(0, 4)),
        ],
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const IconoVivo(Icons.workspace_premium, size: 40),
          const SizedBox(height: 10),
          const Text('Activa tu Plan Academia',
              textAlign: TextAlign.center,
              style: TextStyle(fontWeight: FontWeight.w800, fontSize: 18)),
          const SizedBox(height: 6),
          Text(
              'Esta sección es parte del Plan Academia ($sim ${precio.toStringAsFixed(2)} al mes). '
              'Con él tus alumnos se matriculan en línea, reciben recordatorios '
              'y tú gestionas todo desde aquí.',
              textAlign: TextAlign.center,
              style: const TextStyle(color: textoTenue, fontSize: 13.5)),
          const SizedBox(height: 16),
          SizedBox(
            width: double.infinity,
            child: FilledButton(
              style: FilledButton.styleFrom(
                  backgroundColor: lima,
                  foregroundColor: Colors.white,
                  padding: const EdgeInsets.symmetric(vertical: 13)),
              onPressed: () => Navigator.of(context).push(MaterialPageRoute(
                  builder: (_) => PlanAcademiaScreen(academia: academia))),
              child: const Text('Ver mi plan',
                  style: TextStyle(fontWeight: FontWeight.w800)),
            ),
          ),
        ],
      ),
    );
  }
}
