import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../models/campeonato.dart';
import '../services/supabase_service.dart';
import '../services/whatsapp_link.dart';
import '../services/pagos_service.dart';
import '../services/propiedad_service.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/dialogo_pichangol.dart';
import '../utils/compartir_pichangol.dart';
import '../utils/ubicacion_share.dart';
import '../widgets/cargando_pichangol.dart';
import '../widgets/responsive.dart';
import 'login_google_sheet.dart';
import 'ranking_global_screen.dart';
import 'recargar_saldo_screen.dart';
import '../utils/moneda.dart';
import '../config/pais.dart';

/// Detalle de un campeonato: participantes, fixture (llave o tabla), carga de
/// resultados y compartir por WhatsApp. Los controles de edición se muestran
/// solo al organizador (dueño).
class CampeonatoDetalleScreen extends StatelessWidget {
  const CampeonatoDetalleScreen({super.key, required this.campeonatoId});
  final String campeonatoId;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Campeonato')),
      body: ListenableBuilder(
        listenable: appState,
        builder: (context, _) {
          final c = appState.campeonatoPorId(campeonatoId);
          if (c == null) {
            return const Center(child: Text('Campeonato no encontrado'));
          }
          final u = appState.usuario;
          final esDueno =
              u != null && c.dueno.toLowerCase() == u.email.toLowerCase();
          final puedeInscribirse = !esDueno &&
              !c.cerrado &&
              c.inscripcionAbierta &&
              !c.fixtureGenerado &&
              !c.inscripcionVencida; // cerró el plazo de inscripción
          return ListView(
            // Regla app: contenido centrado (ancho máx) en pantallas anchas.
            padding: EdgeInsets.fromLTRB(
                ladoTablet(context, 16, 760), 16, ladoTablet(context, 16, 760), 30),
            children: [
              _Cabecera(campeonato: c),
              const SizedBox(height: 10),
              Align(
                alignment: Alignment.centerLeft,
                child: _EstadoCampeonato(c),
              ),
              if (c.sedeUbicacion != null) ...[
                const SizedBox(height: 10),
                SizedBox(
                  width: double.infinity,
                  child: OutlinedButton.icon(
                    onPressed: () => UbicacionShare.menu(context,
                        punto: c.sedeUbicacion!,
                        titulo: c.sede.isEmpty ? c.nombre : c.sede),
                    icon: const Icon(Icons.place),
                    label: const Text('Ubicación · cómo llegar / compartir'),
                  ),
                ),
              ],
              const SizedBox(height: 12),
              _InvitarCard(campeonato: c),
              // Cronograma / verificación (chips informativos).
              if (c.inscripcionHasta != null ||
                  c.relampago ||
                  c.exigeDni ||
                  c.edadMin != null ||
                  c.edadMax != null) ...[
                const SizedBox(height: 12),
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    if (c.inscripcionHasta != null)
                      _ChipInfo('🗓️ Cierre inscrip.: '
                          '${_fmtDia(c.inscripcionHasta!)}'),
                    if (c.relampago) const _ChipInfo('⚡ Relámpago'),
                    if (c.exigeDni) _ChipInfo('🪪 Exige $docIdActual'),
                    if (c.edadMin != null || c.edadMax != null)
                      _ChipInfo('🎂 '
                          '${c.edadMin != null ? 'desde ${c.edadMin}' : ''}'
                          '${c.edadMax != null ? ' hasta ${c.edadMax} años' : ''}'
                          .trim()),
                  ],
                ),
              ],
              if (c.inscripcionVencida && !c.fixtureGenerado && !esDueno) ...[
                const SizedBox(height: 10),
                const Text('Las inscripciones cerraron. Espera el fixture.',
                    style: TextStyle(color: textoTenue, fontSize: 12.5)),
              ],
              if (puedeInscribirse) ...[
                const SizedBox(height: 12),
                if (c.deporte.name == 'futbol') ...[
                  // Fútbol = equipos: el capitán crea equipo (con código) y los
                  // jugadores se unen con ese código.
                  SizedBox(
                    width: double.infinity,
                    child: FilledButton.icon(
                      onPressed: () => _crearEquipo(context, c),
                      icon: const Icon(Icons.groups),
                      label: const Text('Crear mi equipo'),
                    ),
                  ),
                  const SizedBox(height: 8),
                  SizedBox(
                    width: double.infinity,
                    child: OutlinedButton.icon(
                      onPressed: () => _unirmeAEquipo(context, c),
                      icon: const Icon(Icons.login),
                      label: const Text('Unirme a un equipo (código)'),
                    ),
                  ),
                ] else
                  SizedBox(
                    width: double.infinity,
                    child: FilledButton.icon(
                      onPressed: () => _inscribirme(context, c),
                      icon: const Icon(Icons.how_to_reg),
                      label: Text(c.costoInscripcion > 0
                          ? 'Inscribirme · ${c.monedaSimbolo} ${c.costoInscripcion.toStringAsFixed(2)}'
                          : 'Inscribirme'),
                    ),
                  ),
              ],
              const SizedBox(height: 14),
              _Participantes(campeonato: c, esDueno: esDueno),
              const SizedBox(height: 18),
              // Natación: por tiempos/series (sin fixture de partidos G/P).
              if (c.esTiempos) _Natacion(campeonato: c, esDueno: esDueno),
              if (!c.esTiempos && c.fixtureGenerado) ...[
                Text(
                    c.formato == FormatoTorneo.liga
                        ? 'Tabla y partidos'
                        : 'Llave',
                    style: const TextStyle(
                        fontWeight: FontWeight.w800, fontSize: 17)),
                const SizedBox(height: 8),
                if (c.formato == FormatoTorneo.liga)
                  _Liga(campeonato: c, esDueno: esDueno)
                else
                  _Llave(campeonato: c, esDueno: esDueno),
                // "Ver ranking" solo para deportes CON circuito (tenis/pádel/
                // pickleball). Fútbol/natación no tienen ranking → no se ofrece.
                if (c.academiaId.isEmpty && c.esDeporteCircuito) ...[
                  const SizedBox(height: 12),
                  SizedBox(
                    width: double.infinity,
                    child: OutlinedButton.icon(
                      onPressed: () => Navigator.of(context).push(
                        MaterialPageRoute(
                          builder: (_) => RankingGlobalScreen(
                              deporteInicial: c.deporte),
                        ),
                      ),
                      icon: Text(emojiDeporte(c.deporte),
                          style: const TextStyle(fontSize: 16)),
                      label: Text('Ver ranking de ${c.deporte.etiqueta}'),
                    ),
                  ),
                ],
              ],
              // "Sumar al ranking" también solo para deportes con circuito.
              if (!c.esTiempos &&
                  esDueno &&
                  c.fixtureGenerado &&
                  c.esDeporteCircuito) ...[
                const SizedBox(height: 20),
                SizedBox(
                  width: double.infinity,
                  child: FilledButton.icon(
                    style: FilledButton.styleFrom(
                        backgroundColor: lima,
                        foregroundColor: Colors.white,
                        padding: const EdgeInsets.symmetric(vertical: 13)),
                    onPressed: () => _sumarAlRanking(context, c),
                    icon: const Icon(Icons.leaderboard, size: 20),
                    label: const Text('Sumar resultados al ranking',
                        style: TextStyle(fontWeight: FontWeight.w800)),
                  ),
                ),
                const Padding(
                  padding: EdgeInsets.only(top: 6),
                  child: Text(
                      'Los partidos jugados suman puntos al ranking del circuito '
                      '(y al global). Puedes volver a tocarlo si cargas más '
                      'resultados.',
                      style: TextStyle(color: textoTenue, fontSize: 12)),
                ),
              ],
              if (esDueno) ...[
                const SizedBox(height: 20),
                OutlinedButton.icon(
                  onPressed: () => _confirmarEliminar(context, c),
                  icon: const Icon(Icons.delete_outline,
                      color: Colors.redAccent),
                  label: const Text('Eliminar campeonato',
                      style: TextStyle(color: Colors.redAccent)),
                ),
              ],
            ],
          );
        },
      ),
    );
  }

  Future<void> _sumarAlRanking(BuildContext context, Campeonato c) async {
    final n = await appState.importarCampeonatoAlRanking(c);
    if (!context.mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
      backgroundColor: bosque,
      content: Text(n == 0
          ? 'Aún no hay partidos jugados para sumar.'
          : '$n partido${n == 1 ? '' : 's'} sumado${n == 1 ? '' : 's'} al '
              'ranking del circuito.'),
    ));
  }

  Future<void> _confirmarEliminar(BuildContext context, Campeonato c) async {
    final ok = await confirmarPichangol(
      context,
      titulo: 'Eliminar campeonato',
      mensaje: '¿Eliminar "${c.nombre}"? No se puede deshacer.',
      textoConfirmar: 'Eliminar',
      destructivo: true,
      icono: Icons.delete_outline,
    );
    if (ok && context.mounted) {
      appState.eliminarCampeonato(c.id);
      Navigator.of(context).pop();
    }
  }

  Future<void> _compartir(BuildContext context, Campeonato c) async {
    final ok = await WhatsAppLink.compartir(_resumen(c));
    if (!ok && context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('No pude abrir WhatsApp.')));
    }
  }

  Future<void> _copiarEnlace(BuildContext context, Campeonato c) async {
    final link = SupabaseService.paginaCampeonato(c.id);
    if (link == null) return;
    await Clipboard.setData(ClipboardData(text: link));
    if (context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text('Enlace de la página copiado. ¡Pégalo donde quieras!')));
    }
  }

  static const _meses = [
    'ene', 'feb', 'mar', 'abr', 'may', 'jun',
    'jul', 'ago', 'set', 'oct', 'nov', 'dic'
  ];
  static String _fmtDia(DateTime d) => '${d.day} ${_meses[d.month - 1]}';

  /// Calcula la edad actual desde una fecha de nacimiento en texto (Factiliza
  /// suele dar dd/mm/yyyy; también acepta yyyy-mm-dd). null si no se puede.
  static int? _edadDesde(String? fechaNac) {
    final s = (fechaNac ?? '').trim();
    if (s.isEmpty) return null;
    DateTime? nac;
    final m1 = RegExp(r'^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$').firstMatch(s);
    final m2 = RegExp(r'^(\d{4})[/-](\d{1,2})[/-](\d{1,2})$').firstMatch(s);
    if (m1 != null) {
      nac = DateTime(int.parse(m1.group(3)!), int.parse(m1.group(2)!),
          int.parse(m1.group(1)!));
    } else if (m2 != null) {
      nac = DateTime(int.parse(m2.group(1)!), int.parse(m2.group(2)!),
          int.parse(m2.group(3)!));
    }
    if (nac == null) return null;
    final hoy = DateTime.now();
    var edad = hoy.year - nac.year;
    if (hoy.month < nac.month ||
        (hoy.month == nac.month && hoy.day < nac.day)) edad--;
    return edad < 0 || edad > 120 ? null : edad;
  }

  /// Gate de DNI (cuando el campeonato lo exige): valida identidad, calcula la
  /// edad real y la compara con el rango de la categoría (Sub-N). Devuelve true
  /// si puede inscribirse. Evita que alguien se haga pasar por otra edad.
  void _avisoEdad(BuildContext context, String msg) {
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        backgroundColor: bosque, content: Text(msg)));
  }

  Future<bool> _gateDni(BuildContext context, Campeonato c) async {
    // Si el jugador YA está verificado en el app no re-pedimos el documento: la
    // identidad ya está confirmada. Si además tenemos su edad (la trajimos del
    // registro oficial al verificar), la categorizamos aquí mismo.
    if (appState.jugadorVerificado) {
      final edad = appState.edadActual;
      final sinRangoEdad = c.edadMin == null && c.edadMax == null;
      if (sinRangoEdad || edad == null) return true; // identidad basta
      if (c.edadMin != null && edad < c.edadMin!) {
        _avisoEdad(context,
            'Tienes $edad años; la categoría es desde ${c.edadMin}.');
        return false;
      }
      if (c.edadMax != null && edad > c.edadMax!) {
        _avisoEdad(context,
            'Tienes $edad años; la categoría es hasta ${c.edadMax}.');
        return false;
      }
      return true; // verificado y dentro del rango
    }
    final dni = TextEditingController();
    var cargando = false;
    String? error;
    DateTime? nac; // solo países SIN API de documento (Bolivia): fecha manual
    // ¿El país tiene consulta automática del documento? Perú (DNI) y Ecuador
    // (cédula) sí; Bolivia (CI) no → ingreso MANUAL, sin validar contra registro.
    final manual = !paisActual.consultaDoc;
    final conEdad = c.edadMin != null || c.edadMax != null;
    final ok = await showDialog<bool>(
      context: context,
      builder: (dctx) => StatefulBuilder(
        builder: (dctx, setSB) => DialogoPichangol(
          titulo: 'Verifica tu $docIdActual',
          icono: Icons.badge_outlined,
          contenido: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                  '${manual ? 'Ingresa tu $docIdActual para inscribirte' : 'Este campeonato exige $docIdActual para validar identidad y edad'}'
                  '${conEdad ? ' (categoría ${c.edadMin != null ? 'desde ${c.edadMin}' : ''}${c.edadMax != null ? ' hasta ${c.edadMax} años' : ''})' : ''}.',
                  style: const TextStyle(color: textoTenue, fontSize: 12.5)),
              const SizedBox(height: 10),
              TextField(
                controller: dni,
                // Bolivia (CI): texto (admite complemento); Perú/Ecuador: número.
                keyboardType:
                    manual ? TextInputType.text : TextInputType.number,
                maxLength: paisActual.docLongitud,
                decoration: InputDecoration(
                    labelText: paisActual.docLongitud != null
                        ? '$docIdActual (${paisActual.docLongitud} dígitos)'
                        : docIdActual,
                    counterText: ''),
              ),
              // Bolivia con categoría por edad: no hay registro que dé la fecha,
              // así que la pedimos a mano para calcular la edad.
              if (manual && conEdad) ...[
                const SizedBox(height: 8),
                OutlinedButton.icon(
                  onPressed: () async {
                    final hoy = DateTime.now();
                    final f = await showDatePicker(
                      context: dctx,
                      initialDate: DateTime(hoy.year - 15),
                      firstDate: DateTime(hoy.year - 90),
                      lastDate: hoy,
                      helpText: 'Tu fecha de nacimiento',
                    );
                    if (f != null) setSB(() => nac = f);
                  },
                  icon: const Icon(Icons.cake_outlined, size: 18),
                  label: Text(nac == null
                      ? 'Fecha de nacimiento'
                      : 'Nací: ${nac!.day}/${nac!.month}/${nac!.year}'),
                ),
              ],
              if (error != null) ...[
                const SizedBox(height: 6),
                Text(error!,
                    style: const TextStyle(
                        color: Colors.redAccent,
                        fontSize: 12.5,
                        fontWeight: FontWeight.w600)),
              ],
            ],
          ),
          acciones: [
            TextButton(
                onPressed: cargando ? null : () => Navigator.pop(dctx, false),
                child: const Text('Cancelar')),
            FilledButton(
              onPressed: cargando
                  ? null
                  : () async {
                      final d = dni.text.trim();
                      // ── BOLIVIA (manual, sin API): CI self-declarado ──────
                      if (manual) {
                        if (d.length < 5) {
                          setSB(() => error = 'Escribe tu $docIdActual.');
                          return;
                        }
                        if (conEdad) {
                          if (nac == null) {
                            setSB(() =>
                                error = 'Selecciona tu fecha de nacimiento.');
                            return;
                          }
                          final edad = appState.edadDesdeFecha(nac!);
                          if (edad != null &&
                              c.edadMin != null &&
                              edad < c.edadMin!) {
                            setSB(() => error =
                                'Tienes $edad años; la categoría es desde ${c.edadMin}.');
                            return;
                          }
                          if (edad != null &&
                              c.edadMax != null &&
                              edad > c.edadMax!) {
                            setSB(() => error =
                                'Tienes $edad años; la categoría es hasta ${c.edadMax}.');
                            return;
                          }
                        }
                        Navigator.pop(dctx, true);
                        return;
                      }
                      // ── PERÚ / ECUADOR (con API): valida contra registro ──
                      final largo = paisActual.docLongitud;
                      if ((largo != null && d.length != largo) ||
                          int.tryParse(d) == null) {
                        setSB(() => error = largo != null
                            ? 'El $docIdActual son $largo dígitos.'
                            : 'Escribe tu $docIdActual.');
                        return;
                      }
                      setSB(() {
                        cargando = true;
                        error = null;
                      });
                      // País-aware: Ecuador consulta la cédula (CipherByte);
                      // el resto, el DNI (Factiliza). Demora → preload de marca.
                      final r = await conPreload(
                          dctx,
                          () => paisActual.iso == 'EC'
                              ? PropiedadService.consultarCedula(d)
                              : PropiedadService.consultarDni(d),
                          texto: 'Verificando…');
                      if (r == null || r['ok'] != true) {
                        setSB(() {
                          cargando = false;
                          error = 'No pudimos verificar ese $docIdActual. Reintenta.';
                        });
                        return;
                      }
                      final edad = _edadDesde(r['fecha_nacimiento'] as String?);
                      if (edad == null) {
                        // Sin fecha: valida identidad pero no edad (deja pasar).
                        Navigator.pop(dctx, true);
                        return;
                      }
                      if (c.edadMin != null && edad < c.edadMin!) {
                        setSB(() {
                          cargando = false;
                          error =
                              'Tienes $edad años; la categoría es desde ${c.edadMin}.';
                        });
                        return;
                      }
                      if (c.edadMax != null && edad > c.edadMax!) {
                        setSB(() {
                          cargando = false;
                          error =
                              'Tienes $edad años; la categoría es hasta ${c.edadMax}.';
                        });
                        return;
                      }
                      Navigator.pop(dctx, true);
                    },
              child: const Text('Verificar'),
            ),
          ],
        ),
      ),
    );
    return ok == true;
  }

  /// El jugador se inscribe (queda como participante-app). Pregunta si compite
  /// él o un hijo (apoderado) y cobra la inscripción si tiene costo.
  Future<void> _inscribirme(BuildContext context, Campeonato c) async {
    if (!await LoginGoogleSheet.mostrar(context,
        motivo: 'inscribirte al campeonato')) {
      return;
    }
    if (!context.mounted) return;
    // Gate de DNI/edad si el organizador lo exige (anti-suplantación de edad).
    if (c.exigeDni) {
      final pasa = await _gateDni(context, c);
      if (!pasa || !context.mounted) return;
    }
    final nombreNino = TextEditingController();
    final edad = TextEditingController();
    final wa = TextEditingController();
    var paraHijo = false;
    var consiente = false;
    String? error; // mensaje de validación DENTRO del popup
    final esFutbol = c.deporte.name == 'futbol';

    final datos = await showDialog<
        ({bool hijo, String nombre, int? edad, String wa, bool consiente})>(
      context: context,
      builder: (dctx) => StatefulBuilder(
        builder: (dctx, setSB) => DialogoPichangol(
          titulo: 'Inscribirme · ${c.nombre}',
          icono: Icons.how_to_reg_outlined,
          contenido: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text('¿Quién va a competir?',
                    style: TextStyle(fontWeight: FontWeight.w700)),
                const SizedBox(height: 6),
                Row(
                  children: [
                    Expanded(
                      child: ChoiceChip(
                        label: const Center(child: Text('Yo')),
                        selected: !paraHijo,
                        onSelected: (_) => setSB(() => paraHijo = false),
                      ),
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: ChoiceChip(
                        label: const Center(child: Text('Mi hijo(a)')),
                        selected: paraHijo,
                        onSelected: (_) => setSB(() => paraHijo = true),
                      ),
                    ),
                  ],
                ),
                if (paraHijo) ...[
                  const SizedBox(height: 10),
                  TextField(
                    controller: nombreNino,
                    textCapitalization: TextCapitalization.words,
                    decoration: InputDecoration(
                        labelText: esFutbol
                            ? 'Nombre del equipo'
                            : 'Nombre del alumno (niño/a)'),
                  ),
                  const SizedBox(height: 8),
                  Row(
                    children: [
                      Expanded(
                        child: TextField(
                          controller: edad,
                          keyboardType: TextInputType.number,
                          decoration: const InputDecoration(
                              labelText: 'Edad (opcional)'),
                        ),
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: TextField(
                          controller: wa,
                          keyboardType: TextInputType.phone,
                          decoration: InputDecoration(
                              labelText: 'Tu WhatsApp', prefixText: '$codigoTelActual '),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 4),
                  CheckboxListTile(
                    contentPadding: EdgeInsets.zero,
                    controlAffinity: ListTileControlAffinity.leading,
                    dense: true,
                    value: consiente,
                    onChanged: (v) => setSB(() => consiente = v ?? false),
                    title: const Text(
                        'Soy el apoderado y autorizo el registro del menor.',
                        style: TextStyle(fontSize: 12)),
                  ),
                ],
                if (c.costoInscripcion > 0) ...[
                  const SizedBox(height: 8),
                  Text(
                      'Inscripción: ${c.monedaSimbolo} ${c.costoInscripcion.toStringAsFixed(2)}',
                      style: const TextStyle(color: textoTenue)),
                ],
                if (error != null) ...[
                  const SizedBox(height: 10),
                  Text(error!,
                      style: const TextStyle(
                          color: Colors.redAccent,
                          fontSize: 12.5,
                          fontWeight: FontWeight.w600)),
                ],
              ],
            ),
          ),
          acciones: [
            TextButton(
                onPressed: () => Navigator.pop(dctx),
                child: const Text('Cancelar')),
            FilledButton(
              onPressed: () {
                final nombre = nombreNino.text.trim();
                // Validación DENTRO del popup: muestra el error y NO cierra.
                if (paraHijo && nombre.isEmpty) {
                  setSB(() => error = esFutbol
                      ? 'Escribe el nombre del equipo.'
                      : 'Escribe el nombre del alumno.');
                  return;
                }
                if (paraHijo && !consiente) {
                  setSB(() =>
                      error = 'Marca la casilla: confirma que eres el apoderado.');
                  return;
                }
                Navigator.pop(dctx, (
                  hijo: paraHijo,
                  nombre: nombre,
                  edad: int.tryParse(edad.text.trim()),
                  wa: wa.text.trim(),
                  consiente: consiente,
                ));
              },
              child: Text(
                  c.costoInscripcion > 0 ? 'Continuar al pago' : 'Inscribirme'),
            ),
          ],
        ),
      ),
    );
    // El diálogo sólo devuelve datos ya validados (nombre + consentimiento).
    if (datos == null || !context.mounted) return;
    // Cobro de inscripción (si tiene costo): se paga del SALDO (billetera única).
    if (c.costoInscripcion > 0) {
      final email = appState.usuario?.email ?? '';
      final r = await PagosService.inscribirTorneo(
        email: email,
        academiaDueno: c.dueno,
        cuotaSoles: c.costoInscripcion,
        concepto: 'Inscripción ${c.nombre}',
      );
      if (!context.mounted) return;
      if (r['ok'] != true) {
        if (r['falta_saldo'] == true) {
          final req =
              (r['requerido_soles'] as num?)?.toDouble() ?? c.costoInscripcion;
          final ok = await confirmarPichangol(
            context,
            titulo: 'Te falta saldo',
            mensaje:
                'La inscripción cuesta ${c.monedaSimbolo} ${req.toStringAsFixed(2)} '
                'y se paga de tu saldo Pichangol. Recarga y vuelve a inscribirte.',
            textoConfirmar: 'Recargar saldo',
            textoCancelar: 'Ahora no',
            icono: Icons.account_balance_wallet_outlined,
          );
          if (ok && context.mounted) {
            await Navigator.of(context).push(MaterialPageRoute(
                builder: (_) => RecargarSaldoScreen(
                    duenoId: email, titulo: 'Recargar saldo')));
            await appState.sincronizarSaldo();
          }
        } else {
          ScaffoldMessenger.of(context).showSnackBar(SnackBar(
              content: Text(
                  (r['error'] ?? 'No se pudo cobrar la inscripción.').toString())));
        }
        return;
      }
      await appState.sincronizarSaldo();
    }
    final res = appState.inscribirseCampeonato(
      c.id,
      nombreParticipante: datos.hijo ? datos.nombre : null,
      edad: datos.hijo ? datos.edad : null,
      apoderadoWhatsapp: datos.hijo ? datos.wa : null,
    );
    if (context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text(res.mensaje),
        backgroundColor: res.ok ? bosque : null,
      ));
    }
  }

  /// Fútbol: el CAPITÁN crea su equipo y recibe un código para compartir.
  Future<void> _crearEquipo(BuildContext context, Campeonato c) async {
    if (!await LoginGoogleSheet.mostrar(context, motivo: 'crear tu equipo')) {
      return;
    }
    if (!context.mounted) return;
    if (c.exigeDni && !await _gateDni(context, c)) return;
    if (!context.mounted) return;
    final nombre = TextEditingController();
    final ok = await showDialog<bool>(
      context: context,
      builder: (dctx) => DialogoPichangol(
        titulo: 'Crear mi equipo',
        icono: Icons.groups,
        contenido: TextField(
          controller: nombre,
          autofocus: true,
          textCapitalization: TextCapitalization.words,
          decoration: const InputDecoration(
              labelText: 'Nombre del equipo', hintText: 'Los Tigres FC'),
        ),
        acciones: [
          TextButton(
              onPressed: () => Navigator.pop(dctx, false),
              child: const Text('Cancelar')),
          FilledButton(
              onPressed: () => Navigator.pop(dctx, true),
              child: const Text('Crear')),
        ],
      ),
    );
    if (ok != true || !context.mounted) return;
    final res = appState.crearEquipoCampeonato(c.id, nombre.text);
    if (!context.mounted) return;
    if (!res.ok) {
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(res.mensaje)));
      return;
    }
    await _mostrarCodigo(context, c, res.codigo);
  }

  /// Muestra el código del equipo para compartir (los jugadores se auto-inscriben).
  Future<void> _mostrarCodigo(
      BuildContext context, Campeonato c, String codigo) async {
    await showDialog<void>(
      context: context,
      builder: (dctx) => DialogoPichangol(
        titulo: '¡Equipo creado! ⚽',
        icono: Icons.emoji_events,
        contenido: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Text('Comparte este código con tus jugadores para que se '
                'inscriban a tu equipo:'),
            const SizedBox(height: 14),
            SelectableText(codigo,
                style: const TextStyle(
                    fontSize: 30,
                    fontWeight: FontWeight.w900,
                    letterSpacing: 4,
                    color: bosque)),
          ],
        ),
        acciones: [
          TextButton(
              onPressed: () => Navigator.pop(dctx),
              child: const Text('Listo')),
          FilledButton.icon(
            style: FilledButton.styleFrom(backgroundColor: lima),
            onPressed: () {
              WhatsAppLink.compartir(
                  'Únete a mi equipo en "${c.nombre}" (Pichangol). '
                  'Código: $codigo');
              Navigator.pop(dctx);
            },
            icon: const Icon(Icons.share, size: 18),
            label: const Text('Compartir'),
          ),
        ],
      ),
    );
  }

  /// Fútbol: un jugador se une a un equipo con el código del capitán.
  Future<void> _unirmeAEquipo(BuildContext context, Campeonato c) async {
    if (!await LoginGoogleSheet.mostrar(context,
        motivo: 'unirte a un equipo')) {
      return;
    }
    if (!context.mounted) return;
    if (c.exigeDni && !await _gateDni(context, c)) return;
    if (!context.mounted) return;
    final codigo = TextEditingController();
    final ok = await showDialog<bool>(
      context: context,
      builder: (dctx) => DialogoPichangol(
        titulo: 'Unirme a un equipo',
        icono: Icons.group_add,
        contenido: TextField(
          controller: codigo,
          autofocus: true,
          textCapitalization: TextCapitalization.characters,
          decoration: const InputDecoration(
              labelText: 'Código del equipo', hintText: 'Ej.: 4KZ9AB'),
        ),
        acciones: [
          TextButton(
              onPressed: () => Navigator.pop(dctx, false),
              child: const Text('Cancelar')),
          FilledButton(
              onPressed: () => Navigator.pop(dctx, true),
              child: const Text('Unirme')),
        ],
      ),
    );
    if (ok != true || !context.mounted) return;
    final res = appState.unirseAEquipoPorCodigo(c.id, codigo.text);
    if (context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text(res.mensaje),
          backgroundColor: res.ok ? bosque : null));
    }
  }

  static String _resumen(Campeonato c) {
    final sb = StringBuffer();
    sb.writeln('🏆 ${c.nombre}');
    if (c.categoria.isNotEmpty) sb.writeln('Categoría: ${c.categoria}');
    sb.writeln('${c.deporte.etiqueta} · ${c.formato.etiqueta}');
    if (c.fechas.isNotEmpty) sb.writeln('📅 ${c.fechas}');
    if (c.sede.isNotEmpty) sb.writeln('📍 ${c.sede}');
    sb.writeln('');
    if (c.esTiempos) {
      if (c.pruebas.isEmpty) sb.writeln('(aún sin pruebas)');
      for (final p in c.pruebas) {
        sb.writeln('🏊 ${p.nombre}');
        final rk = Natacion.ranking(p);
        if (rk.isEmpty) sb.writeln('(sin tiempos)');
        var pos = 1;
        for (final m in rk) {
          final n = c.participante(m.participanteId)?.nombre ?? '—';
          final val = m.dsq ? 'DSQ' : Natacion.fmt(m.centesimas);
          sb.writeln('${_medallaPos(pos)} $n — $val');
          if (!m.dsq) pos++;
        }
        sb.writeln('');
      }
    } else if (c.formato == FormatoTorneo.liga) {
      sb.writeln('TABLA:');
      var pos = 1;
      for (final f in TorneoFixture.tabla(c)) {
        sb.writeln('$pos. ${f.nombre} — ${f.pts} pts '
            '(${f.g}G ${f.e}E ${f.p}P, dif ${f.dif >= 0 ? '+' : ''}${f.dif})');
        pos++;
      }
    } else {
      sb.writeln('RESULTADOS:');
      final jugados = c.partidos.where((p) => p.jugado).toList();
      if (jugados.isEmpty) sb.writeln('(aún sin resultados)');
      for (final m in jugados) {
        final a = c.participante(m.aId)?.nombre ?? '—';
        final b = c.participante(m.bId)?.nombre ?? '—';
        sb.writeln('$a ${m.marcadorA}-${m.marcadorB} $b');
      }
    }
    final link = SupabaseService.paginaCampeonato(c.id);
    if (link != null) sb.writeln('\n👉 Míralo aquí: $link');
    sb.writeln('\nvía Pichangol');
    return sb.toString();
  }
}

class _Cabecera extends StatelessWidget {
  const _Cabecera({required this.campeonato});
  final Campeonato campeonato;
  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final t = Theme.of(context).textTheme;
    final c = campeonato;
    final chips = <String>[
      c.deporte.etiqueta,
      c.formato.etiqueta,
      if (c.categoria.isNotEmpty) c.categoria,
      if (c.fechas.isNotEmpty) '📅 ${c.fechas}',
      if (c.sede.isNotEmpty) '📍 ${c.sede}',
      if (c.costoInscripcion > 0)
        'Inscripción ${c.monedaSimbolo} ${c.costoInscripcion.toStringAsFixed(2)}',
    ];
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: cs.surface,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: trazo),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              CircleAvatar(
                backgroundColor: colorDeporte(c.deporte),
                child:
                    Icon(iconoDeporte(c.deporte), color: Colors.white),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Text(c.nombre,
                    style: t.titleLarge?.copyWith(fontWeight: FontWeight.w800)),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              for (final s in chips)
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                  decoration: BoxDecoration(
                      color: limaSuave,
                      borderRadius: BorderRadius.circular(999)),
                  child: Text(s,
                      style: const TextStyle(
                          color: bosque,
                          fontSize: 12,
                          fontWeight: FontWeight.w700)),
                ),
            ],
          ),
        ],
      ),
    );
  }
}

/// Chip informativo (cronograma / verificación) del campeonato.
class _ChipInfo extends StatelessWidget {
  const _ChipInfo(this.texto);
  final String texto;
  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: limaSuave,
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: trazo),
      ),
      child: Text(texto,
          style: const TextStyle(
              fontSize: 12, fontWeight: FontWeight.w600, color: bosque)),
    );
  }
}

/// Pastilla de ESTADO del campeonato con emoji vivo (mismo lenguaje que retos/
/// reservas): inscripciones abiertas → cerradas → en juego → finalizado.
class _EstadoCampeonato extends StatelessWidget {
  const _EstadoCampeonato(this.c);
  final Campeonato c;
  @override
  Widget build(BuildContext context) {
    final enJuego = c.esTiempos ? c.pruebas.isNotEmpty : c.fixtureGenerado;
    final (String texto, Color color, String emoji) = c.cerrado
        ? ('Finalizado', teal, '🏁')
        : enJuego
            ? ('En juego', morado, '🏆')
            : c.inscripcionVencida
                ? (c.esTiempos
                    ? 'Inscripciones cerradas · esperando pruebas'
                    : 'Inscripciones cerradas · esperando fixture', naranja, '⏳')
                : ('Inscripciones abiertas', lima, '📝');
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 11, vertical: 6),
      decoration: BoxDecoration(
        color: color.withOpacity(0.14),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text('$emoji  $texto',
          style: TextStyle(
              fontSize: 12.5, fontWeight: FontWeight.w800, color: color)),
    );
  }
}

class _Participantes extends StatelessWidget {
  const _Participantes({required this.campeonato, required this.esDueno});
  final Campeonato campeonato;
  final bool esDueno;

  /// Muestra el plantel del equipo; si soy el capitán, el código para compartir
  /// y agregar integrantes a mano.
  Future<void> _verEquipo(
      BuildContext context, Campeonato c, Participante eq) async {
    final yo = (appState.usuario?.email ?? '').toLowerCase();
    final soyCapitan = eq.capitanEmail.toLowerCase() == yo;
    await showDialog<void>(
      context: context,
      builder: (dctx) => DialogoPichangol(
        titulo: eq.nombre,
        icono: Icons.groups,
        contenido: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (soyCapitan && eq.codigo.isNotEmpty) ...[
                const Text('Código del equipo (compártelo):',
                    style: TextStyle(color: textoTenue, fontSize: 12.5)),
                Row(
                  children: [
                    SelectableText(eq.codigo,
                        style: const TextStyle(
                            fontSize: 22,
                            fontWeight: FontWeight.w900,
                            letterSpacing: 3,
                            color: bosque)),
                    const Spacer(),
                    IconButton(
                      tooltip: 'Compartir',
                      icon: const Icon(Icons.share, color: lima),
                      onPressed: () => WhatsAppLink.compartir(
                          'Únete a mi equipo en "${c.nombre}" (Pichangol). '
                          'Código: ${eq.codigo}'),
                    ),
                  ],
                ),
                const Divider(),
              ],
              Text('Plantel (${eq.roster.length})',
                  style: const TextStyle(fontWeight: FontWeight.w800)),
              const SizedBox(height: 6),
              if (eq.roster.isEmpty)
                const Text('Aún sin jugadores.',
                    style: TextStyle(color: textoTenue, fontSize: 12.5)),
              for (final m in eq.roster)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 3),
                  child: Row(
                    children: [
                      Icon(m.verificado ? Icons.verified : Icons.person_outline,
                          size: 18,
                          color: m.verificado ? lima : textoTenue),
                      const SizedBox(width: 8),
                      Expanded(child: Text(m.nombre)),
                      if (m.email.toLowerCase() == eq.capitanEmail.toLowerCase())
                        const Text('Capitán',
                            style: TextStyle(
                                color: textoTenue,
                                fontSize: 11,
                                fontWeight: FontWeight.w700)),
                    ],
                  ),
                ),
            ],
          ),
        ),
        acciones: [
          if (soyCapitan)
            TextButton.icon(
              onPressed: () async {
                final nombre = TextEditingController();
                final add = await showDialog<bool>(
                  context: dctx,
                  builder: (d2) => DialogoPichangol(
                    titulo: 'Agregar jugador (a mano)',
                    icono: Icons.person_add_alt,
                    contenido: TextField(
                      controller: nombre,
                      autofocus: true,
                      textCapitalization: TextCapitalization.words,
                      decoration:
                          const InputDecoration(labelText: 'Nombre'),
                    ),
                    acciones: [
                      TextButton(
                          onPressed: () => Navigator.pop(d2, false),
                          child: const Text('Cancelar')),
                      FilledButton(
                          onPressed: () => Navigator.pop(d2, true),
                          child: const Text('Agregar')),
                    ],
                  ),
                );
                if (add == true) {
                  appState.agregarIntegranteManual(
                      c.id, eq.id, nombre.text);
                  if (dctx.mounted) Navigator.pop(dctx);
                }
              },
              icon: const Icon(Icons.person_add_alt, size: 18),
              label: const Text('Agregar'),
            ),
          TextButton(
              onPressed: () => Navigator.pop(dctx),
              child: const Text('Cerrar')),
        ],
      ),
    );
  }

  Future<void> _agregar(BuildContext context) async {
    final nombre = TextEditingController();
    final wa = TextEditingController();
    final esFutbol = campeonato.deporte.name == 'futbol';
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => DialogoPichangol(
        titulo: esFutbol ? 'Nuevo equipo' : 'Nuevo participante',
        icono: Icons.group_add,
        contenido: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: nombre,
              textCapitalization: TextCapitalization.words,
              decoration: InputDecoration(
                  labelText: esFutbol
                      ? 'Nombre del equipo'
                      : 'Nombre (jugador o pareja "A / B")'),
            ),
            TextField(
              controller: wa,
              keyboardType: TextInputType.phone,
              decoration: InputDecoration(
                  labelText: 'WhatsApp (opcional)', prefixText: '$codigoTelActual '),
            ),
          ],
        ),
        acciones: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('Cancelar')),
          FilledButton(
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('Agregar')),
        ],
      ),
    );
    if (ok == true) {
      appState.agregarParticipante(campeonato.id, nombre.text,
          contacto: wa.text);
    }
  }

  Future<void> _generar(BuildContext context) async {
    if (campeonato.participantes.length < 2) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text('Agrega al menos 2 participantes.')));
      return;
    }
    if (campeonato.fixtureGenerado) {
      final ok = await confirmarPichangol(
        context,
        titulo: 'Regenerar fixture',
        mensaje: 'Ya hay un fixture. Regenerarlo BORRA los resultados cargados. '
            '¿Continuar?',
        textoConfirmar: 'Regenerar',
        destructivo: true,
        icono: Icons.refresh,
      );
      if (!ok) return;
    }
    appState.generarFixture(campeonato.id);
  }

  @override
  Widget build(BuildContext context) {
    final c = campeonato;
    final cs = Theme.of(context).colorScheme;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text('Participantes (${c.participantes.length})',
                style:
                    const TextStyle(fontWeight: FontWeight.w800, fontSize: 17)),
            if (esDueno)
              TextButton.icon(
                onPressed: () => _agregar(context),
                icon: const Icon(Icons.person_add_alt_1),
                label: const Text('Agregar'),
              ),
          ],
        ),
        if (c.participantes.isEmpty)
          const Padding(
            padding: EdgeInsets.symmetric(vertical: 8),
            child: Text('Aún no hay inscritos.',
                style: TextStyle(color: textoTenue)),
          ),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            for (final p in c.participantes)
              InputChip(
                avatar: p.esEquipo
                    ? const Icon(Icons.groups, size: 18, color: bosque)
                    : p.esApp
                        ? (p.fotoUrl != null && p.fotoUrl!.isNotEmpty
                            ? CircleAvatar(
                                backgroundImage: NetworkImage(p.fotoUrl!))
                            : Icon(
                                p.esMenor
                                    ? Icons.child_care
                                    : Icons.verified_user,
                                size: 18,
                                color: cs.primary))
                        : null,
                label: Text(p.esEquipo
                    ? '${p.nombre} · ${p.roster.length} jug.'
                    : p.esMenor
                        ? '${p.nombre} · apod. ${p.apoderadoNombre}'
                        : p.nombre),
                onPressed:
                    p.esEquipo ? () => _verEquipo(context, c, p) : null,
                onDeleted: esDueno
                    ? () => appState.eliminarParticipante(c.id, p.id)
                    : null,
              ),
          ],
        ),
        // Natación no usa fixture (se administra por pruebas/tiempos abajo).
        if (esDueno && !c.esTiempos) ...[
          const SizedBox(height: 12),
          SizedBox(
            width: double.infinity,
            child: FilledButton.icon(
              onPressed: () => _generar(context),
              icon: const Icon(Icons.account_tree),
              label: Text(c.fixtureGenerado
                  ? 'Regenerar fixture'
                  : 'Generar fixture'),
            ),
          ),
        ],
      ],
    );
  }
}

/// Diálogo para cargar el marcador de un partido.
Future<void> _cargarResultado(
    BuildContext context, Campeonato c, PartidoTorneo m) async {
  if (m.aId == null || m.bId == null) return; // cruce aún no definido
  final na = c.participante(m.aId)?.nombre ?? 'A';
  final nb = c.participante(m.bId)?.nombre ?? 'B';
  final ca = TextEditingController(text: m.marcadorA?.toString() ?? '');
  final cb = TextEditingController(text: m.marcadorB?.toString() ?? '');
  final ok = await showDialog<bool>(
    context: context,
    builder: (ctx) => DialogoPichangol(
      titulo: 'Cargar resultado',
      icono: Icons.scoreboard_outlined,
      contenido: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          _FilaMarcador(nombre: na, controller: ca),
          const SizedBox(height: 8),
          _FilaMarcador(nombre: nb, controller: cb),
        ],
      ),
      acciones: [
        TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Cancelar')),
        FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Guardar')),
      ],
    ),
  );
  if (ok == true) {
    final a = int.tryParse(ca.text.trim());
    final b = int.tryParse(cb.text.trim());
    if (a != null && b != null) {
      appState.setResultado(c.id, m.id, a, b);
    }
  }
}

class _FilaMarcador extends StatelessWidget {
  const _FilaMarcador({required this.nombre, required this.controller});
  final String nombre;
  final TextEditingController controller;
  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
            child: Text(nombre,
                maxLines: 1, overflow: TextOverflow.ellipsis)),
        const SizedBox(width: 10),
        SizedBox(
          width: 60,
          child: TextField(
            controller: controller,
            textAlign: TextAlign.center,
            keyboardType: TextInputType.number,
            decoration: const InputDecoration(hintText: '0'),
          ),
        ),
      ],
    );
  }
}

class _Liga extends StatelessWidget {
  const _Liga({required this.campeonato, required this.esDueno});
  final Campeonato campeonato;
  final bool esDueno;
  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final tabla = TorneoFixture.tabla(campeonato);
    // Partidos agrupados por jornada.
    final porJornada = <int, List<PartidoTorneo>>{};
    for (final m in campeonato.partidos) {
      (porJornada[m.ronda] ??= []).add(m);
    }
    final jornadas = porJornada.keys.toList()..sort();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // Tabla.
        Container(
          decoration: BoxDecoration(
            color: cs.surface,
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: trazo),
          ),
          child: Column(
            children: [
              const _TablaHeader(),
              for (var i = 0; i < tabla.length; i++)
                _TablaFila(pos: i + 1, fila: tabla[i]),
            ],
          ),
        ),
        const SizedBox(height: 16),
        for (final j in jornadas) ...[
          Text('Jornada ${j + 1}',
              style:
                  const TextStyle(fontWeight: FontWeight.w800, fontSize: 15)),
          const SizedBox(height: 6),
          for (final m in porJornada[j]!)
            _PartidoTile(
                campeonato: campeonato, partido: m, esDueno: esDueno),
          const SizedBox(height: 10),
        ],
      ],
    );
  }
}

class _TablaHeader extends StatelessWidget {
  const _TablaHeader();
  @override
  Widget build(BuildContext context) {
    const st = TextStyle(
        fontWeight: FontWeight.w800, fontSize: 12, color: textoTenue);
    return Padding(
      padding: const EdgeInsets.fromLTRB(10, 8, 10, 8),
      child: Row(
        children: [
          const SizedBox(width: 22, child: Text('#', style: st)),
          const Expanded(child: Text('Equipo', style: st)),
          _celda('PJ', st),
          _celda('G', st),
          _celda('E', st),
          _celda('P', st),
          _celda('Dif', st),
          _celda('Pts', st),
        ],
      ),
    );
  }

  static Widget _celda(String t, TextStyle st) =>
      SizedBox(width: 30, child: Text(t, textAlign: TextAlign.center, style: st));
}

class _TablaFila extends StatelessWidget {
  const _TablaFila({required this.pos, required this.fila});
  final int pos;
  final FilaTabla fila;
  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final n = TextStyle(fontSize: 13, color: cs.onSurface);
    final b = TextStyle(
        fontSize: 13, fontWeight: FontWeight.w800, color: cs.onSurface);
    return Container(
      decoration: BoxDecoration(
          border: Border(top: BorderSide(color: trazo.withOpacity(0.6)))),
      padding: const EdgeInsets.fromLTRB(10, 8, 10, 8),
      child: Row(
        children: [
          SizedBox(width: 22, child: Text('$pos', style: b)),
          Expanded(
              child: Text(fila.nombre,
                  maxLines: 1, overflow: TextOverflow.ellipsis, style: n)),
          _celda('${fila.pj}', n),
          _celda('${fila.g}', n),
          _celda('${fila.e}', n),
          _celda('${fila.p}', n),
          _celda('${fila.dif >= 0 ? '+' : ''}${fila.dif}', n),
          _celda('${fila.pts}', b),
        ],
      ),
    );
  }

  static Widget _celda(String t, TextStyle st) =>
      SizedBox(width: 30, child: Text(t, textAlign: TextAlign.center, style: st));
}

class _Llave extends StatelessWidget {
  const _Llave({required this.campeonato, required this.esDueno});
  final Campeonato campeonato;
  final bool esDueno;

  static String _nombreRonda(int total, int r) {
    final desdeFinal = total - 1 - r;
    return switch (desdeFinal) {
      0 => 'Final',
      1 => 'Semifinal',
      2 => 'Cuartos de final',
      3 => 'Octavos de final',
      _ => 'Ronda ${r + 1}',
    };
  }

  @override
  Widget build(BuildContext context) {
    final porRonda = <int, List<PartidoTorneo>>{};
    for (final m in campeonato.partidos) {
      (porRonda[m.ronda] ??= []).add(m);
    }
    final rondas = porRonda.keys.toList()..sort();
    final total = rondas.isEmpty ? 0 : rondas.last + 1;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        for (final r in rondas) ...[
          Text(_nombreRonda(total, r),
              style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 15)),
          const SizedBox(height: 6),
          for (final m in porRonda[r]!)
            _PartidoTile(
                campeonato: campeonato, partido: m, esDueno: esDueno),
          const SizedBox(height: 10),
        ],
      ],
    );
  }
}

class _PartidoTile extends StatelessWidget {
  const _PartidoTile(
      {required this.campeonato, required this.partido, required this.esDueno});
  final Campeonato campeonato;
  final PartidoTorneo partido;
  final bool esDueno;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final m = partido;
    final na = campeonato.participante(m.aId)?.nombre;
    final nb = campeonato.participante(m.bId)?.nombre;
    final ganador = m.ganadorId;
    final defBye =
        m.ronda == 0 && ((m.aId == null) != (m.bId == null)) && !m.jugado;
    final habilitado = esDueno && m.aId != null && m.bId != null;
    return Container(
      margin: const EdgeInsets.only(bottom: 6),
      decoration: BoxDecoration(
        color: cs.surface,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: trazo),
      ),
      child: ListTile(
        dense: true,
        onTap: habilitado ? () => _cargarResultado(context, campeonato, m) : null,
        title: Row(
          children: [
            Expanded(
              child: _Lado(
                  nombre: na ?? (defBye ? '(bye)' : 'Por definir'),
                  gana: ganador != null && ganador == m.aId),
            ),
            _Marcador(m.marcadorA),
            const Padding(
              padding: EdgeInsets.symmetric(horizontal: 4),
              child: Text('-', style: TextStyle(color: textoTenue)),
            ),
            _Marcador(m.marcadorB),
            Expanded(
              child: _Lado(
                  nombre: nb ?? (defBye ? '(bye)' : 'Por definir'),
                  gana: ganador != null && ganador == m.bId,
                  alinearDerecha: true),
            ),
          ],
        ),
        trailing: habilitado
            ? Icon(Icons.edit, size: 16, color: cs.primary)
            : null,
      ),
    );
  }
}

class _Lado extends StatelessWidget {
  const _Lado(
      {required this.nombre, required this.gana, this.alinearDerecha = false});
  final String nombre;
  final bool gana;
  final bool alinearDerecha;
  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Text(
      nombre,
      maxLines: 1,
      overflow: TextOverflow.ellipsis,
      textAlign: alinearDerecha ? TextAlign.right : TextAlign.left,
      style: TextStyle(
        fontSize: 13,
        color: cs.onSurface,
        fontWeight: gana ? FontWeight.w800 : FontWeight.w500,
      ),
    );
  }
}

class _Marcador extends StatelessWidget {
  const _Marcador(this.valor);
  final int? valor;
  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return SizedBox(
      width: 20,
      child: Text(valor?.toString() ?? '–',
          textAlign: TextAlign.center,
          style: TextStyle(fontWeight: FontWeight.w800, color: cs.onSurface)),
    );
  }
}

// ── NATACIÓN (formato por tiempos/series) ────────────────────────────────────

void _guardarPruebas(Campeonato c, List<PruebaNatacion> nuevas) {
  appState.guardarCampeonato(c.copyWith(pruebas: nuevas));
}

/// Agrega una prueba (evento): distancia + estilo → "50m Libre".
Future<void> _agregarPrueba(BuildContext context, Campeonato c) async {
  int dist = 50;
  String estilo = 'Libre';
  final ok = await showDialog<bool>(
    context: context,
    builder: (ctx) => StatefulBuilder(
      builder: (ctx, setSt) => AlertDialog(
        backgroundColor: Theme.of(ctx).colorScheme.surface,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
        title: const Text('Nueva prueba'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Distancia',
                style: TextStyle(
                    color: textoTenueDe(ctx),
                    fontWeight: FontWeight.w700,
                    fontSize: 13)),
            const SizedBox(height: 6),
            Wrap(
              spacing: 6,
              children: [
                for (final d in Natacion.distancias)
                  ChoiceChip(
                    label: Text('${d}m'),
                    selected: dist == d,
                    onSelected: (_) => setSt(() => dist = d),
                  ),
              ],
            ),
            const SizedBox(height: 12),
            Text('Estilo',
                style: TextStyle(
                    color: textoTenueDe(ctx),
                    fontWeight: FontWeight.w700,
                    fontSize: 13)),
            const SizedBox(height: 6),
            Wrap(
              spacing: 6,
              children: [
                for (final e in Natacion.estilos)
                  ChoiceChip(
                    label: Text(e),
                    selected: estilo == e,
                    onSelected: (_) => setSt(() => estilo = e),
                  ),
              ],
            ),
          ],
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('Cancelar')),
          FilledButton(
              style: FilledButton.styleFrom(backgroundColor: lima),
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('Agregar')),
        ],
      ),
    ),
  );
  if (ok != true) return;
  final prueba = PruebaNatacion(
    id: 'pr_${DateTime.now().microsecondsSinceEpoch}',
    nombre: '${dist}m $estilo',
  );
  _guardarPruebas(c, [...c.pruebas, prueba]);
}

/// Registra/edita la marca (tiempo) de un participante en una prueba.
Future<void> _editarMarca(BuildContext context, Campeonato c,
    PruebaNatacion prueba, String participanteId) async {
  final nombre = c.participante(participanteId)?.nombre ?? '';
  final actual = prueba.marcas.firstWhere(
      (m) => m.participanteId == participanteId,
      orElse: () => MarcaNatacion(participanteId: participanteId));
  final tiempoCtrl = TextEditingController(
      text: actual.centesimas > 0 ? Natacion.fmt(actual.centesimas) : '');
  final serieCtrl =
      TextEditingController(text: actual.serie > 0 ? '${actual.serie}' : '');
  final carrilCtrl =
      TextEditingController(text: actual.carril > 0 ? '${actual.carril}' : '');
  var dsq = actual.dsq;
  String? error;

  final guardo = await showDialog<bool>(
    context: context,
    builder: (ctx) => StatefulBuilder(
      builder: (ctx, setSt) => AlertDialog(
        backgroundColor: Theme.of(ctx).colorScheme.surface,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
        title: Text(nombre, maxLines: 1, overflow: TextOverflow.ellipsis),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(prueba.nombre,
                style: TextStyle(
                    color: textoTenueDe(ctx), fontWeight: FontWeight.w700)),
            const SizedBox(height: 10),
            TextField(
              controller: tiempoCtrl,
              enabled: !dsq,
              keyboardType: const TextInputType.numberWithOptions(decimal: true),
              decoration: InputDecoration(
                labelText: 'Tiempo (mm:ss.cc)',
                hintText: 'ej. 0:37.85',
                errorText: error,
              ),
            ),
            const SizedBox(height: 8),
            Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: serieCtrl,
                    keyboardType: TextInputType.number,
                    decoration: const InputDecoration(labelText: 'Serie'),
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: TextField(
                    controller: carrilCtrl,
                    keyboardType: TextInputType.number,
                    decoration: const InputDecoration(labelText: 'Carril'),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 4),
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              value: dsq,
              title: const Text('Descalificado (DSQ)'),
              onChanged: (v) => setSt(() => dsq = v),
            ),
          ],
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('Cancelar')),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: lima),
            onPressed: () {
              if (dsq) {
                Navigator.pop(ctx, true);
                return;
              }
              final cc = Natacion.parse(tiempoCtrl.text);
              if (tiempoCtrl.text.trim().isEmpty) {
                Navigator.pop(ctx, true); // limpia la marca
                return;
              }
              if (cc == null) {
                setSt(() => error = 'Formato inválido (usa mm:ss.cc)');
                return;
              }
              Navigator.pop(ctx, true);
            },
            child: const Text('Guardar'),
          ),
        ],
      ),
    ),
  );
  if (guardo != true) return;
  final cc = dsq ? 0 : (Natacion.parse(tiempoCtrl.text) ?? 0);
  final nueva = MarcaNatacion(
    participanteId: participanteId,
    centesimas: cc,
    serie: int.tryParse(serieCtrl.text.trim()) ?? 0,
    carril: int.tryParse(carrilCtrl.text.trim()) ?? 0,
    dsq: dsq,
  );
  final marcas = [
    ...prueba.marcas.where((m) => m.participanteId != participanteId),
    if (nueva.registrada || nueva.serie > 0 || nueva.carril > 0) nueva,
  ];
  final pruebas = [
    for (final p in c.pruebas)
      p.id == prueba.id ? p.copyWith(marcas: marcas) : p,
  ];
  _guardarPruebas(c, pruebas);
}

Future<void> _borrarPrueba(
    BuildContext context, Campeonato c, PruebaNatacion prueba) async {
  final ok = await confirmarPichangol(context,
      titulo: 'Eliminar prueba',
      mensaje: '¿Eliminar "${prueba.nombre}" y sus tiempos?',
      textoConfirmar: 'Eliminar',
      destructivo: true,
      icono: Icons.delete_outline);
  if (!ok) return;
  _guardarPruebas(c, c.pruebas.where((p) => p.id != prueba.id).toList());
}

String _medallaPos(int pos) => switch (pos) {
      1 => '🥇',
      2 => '🥈',
      3 => '🥉',
      _ => '$pos°',
    };

/// Sección de natación: pruebas con ranking por tiempo (medallas top 3).
class _Natacion extends StatelessWidget {
  const _Natacion({required this.campeonato, required this.esDueno});
  final Campeonato campeonato;
  final bool esDueno;

  @override
  Widget build(BuildContext context) {
    final c = campeonato;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            const Text('Pruebas',
                style: TextStyle(fontWeight: FontWeight.w800, fontSize: 17)),
            if (esDueno)
              TextButton.icon(
                onPressed: () => _agregarPrueba(context, c),
                icon: const Icon(Icons.add),
                label: const Text('Agregar prueba'),
              ),
          ],
        ),
        if (c.pruebas.isEmpty)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 10),
            child: Text(
              esDueno
                  ? 'Agrega las pruebas (50m Libre, 100m Espalda…) y registra el '
                      'tiempo de cada nadador. El ranking se ordena solo, del más '
                      'rápido al más lento.'
                  : 'El organizador aún no publicó las pruebas.',
              style: TextStyle(color: textoTenueDe(context)),
            ),
          )
        else
          for (final p in c.pruebas)
            _CardPrueba(campeonato: c, prueba: p, esDueno: esDueno),
      ],
    );
  }
}

class _CardPrueba extends StatelessWidget {
  const _CardPrueba(
      {required this.campeonato, required this.prueba, required this.esDueno});
  final Campeonato campeonato;
  final PruebaNatacion prueba;
  final bool esDueno;

  @override
  Widget build(BuildContext context) {
    final c = campeonato;
    final cs = Theme.of(context).colorScheme;
    final ranking = Natacion.ranking(prueba);
    final rankIds = ranking.map((m) => m.participanteId).toSet();
    final pendientes =
        c.participantes.where((p) => !rankIds.contains(p.id)).toList();
    return Container(
      margin: const EdgeInsets.symmetric(vertical: 6),
      padding: const EdgeInsets.fromLTRB(14, 10, 8, 12),
      decoration: BoxDecoration(
        color: Theme.of(context).brightness == Brightness.dark
            ? const Color(0xFF1F2C34)
            : Colors.white,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: trazo.withOpacity(0.5)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Text('🏊', style: TextStyle(fontSize: 16)),
              const SizedBox(width: 8),
              Expanded(
                child: Text(prueba.nombre,
                    style: TextStyle(
                        fontWeight: FontWeight.w800,
                        fontSize: 16,
                        color: cs.onSurface)),
              ),
              if (esDueno)
                PopupMenuButton<String>(
                  icon: Icon(Icons.more_vert, color: textoTenueDe(context)),
                  onSelected: (v) {
                    if (v == 'borrar') _borrarPrueba(context, c, prueba);
                  },
                  itemBuilder: (_) => const [
                    PopupMenuItem(
                        value: 'borrar',
                        child: ListTile(
                            contentPadding: EdgeInsets.zero,
                            leading: Icon(Icons.delete_outline),
                            title: Text('Eliminar prueba'))),
                  ],
                ),
            ],
          ),
          const SizedBox(height: 4),
          if (ranking.isEmpty && pendientes.isEmpty)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 8),
              child: Text('Sin nadadores inscritos.',
                  style: TextStyle(color: textoTenueDe(context), fontSize: 13)),
            ),
          // Ranking (con tiempo / DSQ), del más rápido al más lento.
          for (var i = 0; i < ranking.length; i++)
            _filaMarca(context, c, ranking[i], i + 1),
          // Pendientes (sin tiempo).
          if (pendientes.isNotEmpty) ...[
            Padding(
              padding: const EdgeInsets.only(top: 8, bottom: 2),
              child: Text('Sin tiempo',
                  style: TextStyle(
                      color: textoTenueDe(context),
                      fontSize: 12,
                      fontWeight: FontWeight.w700)),
            ),
            for (final p in pendientes)
              _filaPendiente(context, c, p.id, p.nombre),
          ],
        ],
      ),
    );
  }

  Widget _filaMarca(
      BuildContext context, Campeonato c, MarcaNatacion m, int pos) {
    final cs = Theme.of(context).colorScheme;
    final nombre = c.participante(m.participanteId)?.nombre ?? '—';
    final ubic = [
      if (m.serie > 0) 'S${m.serie}',
      if (m.carril > 0) 'C${m.carril}',
    ].join(' · ');
    final derecha = m.dsq ? 'DSQ' : Natacion.fmt(m.centesimas);
    return InkWell(
      onTap: esDueno
          ? () => _editarMarca(context, c, prueba, m.participanteId)
          : null,
      borderRadius: BorderRadius.circular(10),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 7, horizontal: 2),
        child: Row(
          children: [
            SizedBox(
                width: 30,
                child: Text(m.dsq ? '·' : _medallaPos(pos),
                    style: TextStyle(
                        fontSize: pos <= 3 && !m.dsq ? 18 : 14,
                        fontWeight: FontWeight.w800,
                        color: cs.onSurface))),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(nombre,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                          fontWeight: FontWeight.w600, color: cs.onSurface)),
                  if (ubic.isNotEmpty)
                    Text(ubic,
                        style: TextStyle(
                            color: textoTenueDe(context), fontSize: 11.5)),
                ],
              ),
            ),
            Text(derecha,
                style: TextStyle(
                    fontWeight: FontWeight.w800,
                    fontSize: 15,
                    color: m.dsq ? clayOscuro : cs.onSurface)),
            if (esDueno)
              Padding(
                padding: const EdgeInsets.only(left: 4),
                child: Icon(Icons.edit, size: 15, color: textoTenueDe(context)),
              ),
          ],
        ),
      ),
    );
  }

  Widget _filaPendiente(
      BuildContext context, Campeonato c, String pid, String nombre) {
    return InkWell(
      onTap: esDueno ? () => _editarMarca(context, c, prueba, pid) : null,
      borderRadius: BorderRadius.circular(10),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 7, horizontal: 2),
        child: Row(
          children: [
            const SizedBox(width: 30),
            Expanded(
              child: Text(nombre,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(color: textoTenueDe(context))),
            ),
            if (esDueno)
              Text('Registrar',
                  style: TextStyle(
                      color: lima, fontWeight: FontWeight.w700, fontSize: 13))
            else
              Text('—', style: TextStyle(color: textoTenueDe(context))),
          ],
        ),
      ),
    );
  }
}

/// Bloque "Invitar a inscribirse": el código corto (para dictar/pegar en
/// "Unirme a un campeonato"), el enlace, y botones para compartir dentro de
/// Pichangol o por WhatsApp. Es la forma clara de invitar a que se unan.
class _InvitarCard extends StatelessWidget {
  const _InvitarCard({required this.campeonato});
  final Campeonato campeonato;

  String _mensaje() {
    final c = campeonato;
    final enlace = SupabaseService.paginaCampeonato(c.id);
    final sb = StringBuffer()
      ..writeln('🏆 ${c.nombre}')
      ..writeln('${c.deporte.etiqueta} · inscríbete en Pichangol.')
      ..writeln('')
      ..writeln('Código para unirte: ${c.codigoInvitacion}')
      ..writeln('En la app: Anfitrión → Mis campeonatos → 🔗 Unirme (o '
          'Campeonatos → 🔗) y pega el código.');
    if (enlace != null) sb.writeln('\n👉 $enlace');
    return sb.toString();
  }

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final c = campeonato;
    final codigo = c.codigoInvitacion;
    final enlace = SupabaseService.paginaCampeonato(c.id);
    void copiar(String txt, String aviso) {
      Clipboard.setData(ClipboardData(text: txt));
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(aviso)));
    }

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: trazo),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.person_add_alt_1, color: teal),
              const SizedBox(width: 8),
              Text('Invitar a inscribirse',
                  style: t.titleMedium?.copyWith(fontWeight: FontWeight.w800)),
            ],
          ),
          const SizedBox(height: 4),
          Text(
              c.codigo.isNotEmpty
                  ? 'Comparte el código o el enlace. Para unirse en la app: '
                      '“Unirme a un campeonato” 🔗 y pegar el código.'
                  : 'Comparte el enlace para que se inscriban (o mándalo por '
                      'Pichangol/WhatsApp).',
              style: t.bodySmall?.copyWith(color: textoTenueDe(context))),
          const SizedBox(height: 12),
          // Código grande (solo si hay código corto real; los campeonatos viejos
          // usan el enlace). FittedBox evita que se desborde de la caja.
          if (c.codigo.isNotEmpty) ...[
            InkWell(
              borderRadius: BorderRadius.circular(12),
              onTap: () => copiar(codigo, 'Código copiado'),
              child: Container(
                width: double.infinity,
                padding:
                    const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                decoration: BoxDecoration(
                  color: teal.withOpacity(0.10),
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: teal.withOpacity(0.35)),
                ),
                child: Row(
                  children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text('CÓDIGO',
                              style: t.bodySmall?.copyWith(
                                  color: textoTenueDe(context),
                                  fontWeight: FontWeight.w700,
                                  letterSpacing: 1)),
                          FittedBox(
                            fit: BoxFit.scaleDown,
                            alignment: Alignment.centerLeft,
                            child: Text(codigo,
                                style: t.titleLarge?.copyWith(
                                    color: teal,
                                    fontWeight: FontWeight.w900,
                                    letterSpacing: 2)),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(width: 8),
                    const Icon(Icons.copy, color: teal, size: 20),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 12),
          ],
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              FilledButton.icon(
                style: FilledButton.styleFrom(backgroundColor: lima),
                onPressed: () =>
                    CompartirPichangol.compartir(context, texto: _mensaje()),
                icon: const Icon(Icons.send, size: 18),
                label: const Text('Compartir en Pichangol'),
              ),
              OutlinedButton.icon(
                onPressed: () => WhatsAppLink.compartir(_mensaje()),
                icon: const Icon(Icons.chat, size: 18),
                label: const Text('WhatsApp'),
              ),
              if (enlace != null)
                OutlinedButton.icon(
                  onPressed: () => copiar(enlace, 'Enlace copiado'),
                  icon: const Icon(Icons.link, size: 18),
                  label: const Text('Copiar enlace'),
                ),
            ],
          ),
        ],
      ),
    );
  }
}
