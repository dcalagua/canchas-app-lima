import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/material.dart';
import 'package:supabase_flutter/supabase_flutter.dart';

import '../services/push_service.dart';
import '../services/supabase_service.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/responsive.dart';

/// Diagnóstico de NOTIFICACIONES PUSH: recorre la cadena completa
/// (Firebase en el APK → permiso → token → nube → Edge Function) y dice en
/// cristiano cuál eslabón está roto y qué paso de la guía lo arregla
/// (docs/piloto/push_fcm_setup.md). Existe porque todo `PushService` es
/// fail-safe: cuando algo falta, la app sigue andando y nadie se entera.
class DiagnosticoPushScreen extends StatefulWidget {
  const DiagnosticoPushScreen({super.key});

  @override
  State<DiagnosticoPushScreen> createState() => _DiagnosticoPushScreenState();
}

enum _Estado { pendiente, corriendo, ok, advertencia, fallo }

class _Paso {
  _Paso(this.titulo);
  final String titulo;
  _Estado estado = _Estado.pendiente;
  String detalle = '';

  /// Qué hacer para arreglarlo (solo si falló).
  String arreglo = '';
}

class _DiagnosticoPushScreenState extends State<DiagnosticoPushScreen> {
  final List<_Paso> _pasos = [
    _Paso('Firebase dentro del APK'),
    _Paso('Conexión a Supabase'),
    _Paso('Sesión iniciada'),
    _Paso('Permiso de notificaciones'),
    _Paso('Token del dispositivo (FCM)'),
    _Paso('Token guardado en la nube'),
    _Paso('Envío real por la Edge Function'),
  ];

  bool _corriendo = false;
  String _conclusion = '';
  bool _conclusionBuena = false;

  /// Resultado de la prueba visual diferida (se muestra al volver a la app).
  String _resultadoPruebaVisual = '';

  @override
  void initState() {
    super.initState();
    _correr();
  }

  Future<void> _correr() async {
    if (_corriendo) return;
    setState(() {
      _corriendo = true;
      _conclusion = '';
      _conclusionBuena = false;
      for (final p in _pasos) {
        p.estado = _Estado.pendiente;
        p.detalle = '';
        p.arreglo = '';
      }
    });

    // 1) Firebase en el APK -------------------------------------------------
    final pFirebase = _pasos[0];
    _marcar(pFirebase, _Estado.corriendo);
    await PushService.init();
    if (PushService.disponible) {
      _marcar(pFirebase, _Estado.ok, detalle: 'google-services.json presente.');
    } else {
      _marcar(pFirebase, _Estado.fallo,
          detalle: 'Este APK se compiló SIN la configuración de Firebase '
              '(o falló al iniciar).',
          arreglo: 'Instala el último build desde el Release v0.1.0 (los '
              'builds recientes ya salen con Firebase activo). Si persiste, '
              'revisa el secret GOOGLE_SERVICES_JSON_B64 en GitHub (paso 2 '
              'de la guía).');
      return _terminar();
    }

    // 2) Supabase -----------------------------------------------------------
    final pSupa = _pasos[1];
    _marcar(pSupa, _Estado.corriendo);
    if (SupabaseService.disponible) {
      _marcar(pSupa, _Estado.ok, detalle: SupabaseService.proyecto);
    } else {
      _marcar(pSupa, _Estado.fallo,
          detalle: 'El APK no tiene conexión a Supabase.',
          arreglo: 'Faltan los dart-defines SUPABASE_URL / SUPABASE_ANON_KEY '
              'en el build (secrets de GitHub Actions).');
      return _terminar();
    }

    // 3) Sesión -------------------------------------------------------------
    final pSesion = _pasos[2];
    _marcar(pSesion, _Estado.corriendo);
    final email = (appState.usuario?.email ?? '').trim().toLowerCase();
    if (email.isNotEmpty) {
      _marcar(pSesion, _Estado.ok, detalle: email);
    } else {
      _marcar(pSesion, _Estado.fallo,
          detalle: 'Nadie ha iniciado sesión en este equipo.',
          arreglo: 'Inicia sesión: el token se registra recién ahí (el push '
              'siempre va dirigido a una cuenta).');
      return _terminar();
    }

    // 4) Permiso ------------------------------------------------------------
    final pPermiso = _pasos[3];
    _marcar(pPermiso, _Estado.corriendo);
    try {
      final fm = FirebaseMessaging.instance;
      var ajustes = await fm.getNotificationSettings();
      if (ajustes.authorizationStatus == AuthorizationStatus.notDetermined ||
          ajustes.authorizationStatus == AuthorizationStatus.denied) {
        // Reintenta pedirlo aquí mismo (Android 13+ muestra el diálogo).
        await fm.requestPermission();
        ajustes = await fm.getNotificationSettings();
      }
      final st = ajustes.authorizationStatus;
      if (st == AuthorizationStatus.authorized ||
          st == AuthorizationStatus.provisional) {
        _marcar(pPermiso, _Estado.ok, detalle: 'Permiso concedido.');
      } else {
        _marcar(pPermiso, _Estado.fallo,
            detalle: 'El sistema tiene bloqueadas las notificaciones de '
                'Pichangol.',
            arreglo: 'Ajustes de Android → Apps → Pichangol → Notificaciones '
                '→ permitir.');
        return _terminar();
      }
    } catch (e) {
      _marcar(pPermiso, _Estado.advertencia,
          detalle: 'No se pudo leer el permiso ($e); sigo igual.');
    }

    // 5) Token del equipo ---------------------------------------------------
    final pToken = _pasos[4];
    _marcar(pToken, _Estado.corriendo);
    await PushService.registrarParaUsuario(email);
    final token = PushService.token ?? '';
    if (token.isNotEmpty) {
      final resumen =
          token.length > 14 ? '${token.substring(0, 14)}…' : token;
      _marcar(pToken, _Estado.ok, detalle: 'Token: $resumen');
    } else {
      _marcar(pToken, _Estado.fallo,
          detalle: 'Firebase no entregó token para este equipo.',
          arreglo: 'Suele ser falta de Google Play Services o de internet. '
              'Verifica la conexión y vuelve a probar.');
      return _terminar();
    }

    // 6) Token en la nube ---------------------------------------------------
    final pNube = _pasos[5];
    _marcar(pNube, _Estado.corriendo);
    try {
      final filas = await SupabaseService.client
          .from('pichangol_push_tokens')
          .select('email, actualizado')
          .eq('token', token);
      if (filas.isNotEmpty) {
        final deQuien = (filas.first['email'] ?? '').toString();
        if (deQuien == email) {
          _marcar(pNube, _Estado.ok,
              detalle: 'Registrado para $deQuien.');
        } else {
          _marcar(pNube, _Estado.advertencia,
              detalle: 'El token está registrado para OTRA cuenta '
                  '($deQuien). Cierra sesión y vuelve a entrar.');
        }
      } else {
        _marcar(pNube, _Estado.fallo,
            detalle: 'El token no se pudo guardar en '
                'pichangol_push_tokens (el guardado es silencioso, por eso '
                'no viste error).',
            arreglo: 'Casi siempre la tabla no existe o su política RLS no '
                'deja escribir: corre el bloque de pichangol_push_tokens de '
                'docs/piloto/supabase_mensajes.sql (paso 5 de la guía).');
        return _terminar();
      }
    } on PostgrestException catch (e) {
      final noExiste = e.code == '42P01' ||
          e.message.toLowerCase().contains('does not exist');
      _marcar(pNube, _Estado.fallo,
          detalle: noExiste
              ? 'La tabla pichangol_push_tokens NO existe en Supabase.'
              : 'Supabase rechazó la consulta: ${e.message}',
          arreglo: noExiste
              ? 'Corre el bloque de pichangol_push_tokens de '
                  'docs/piloto/supabase_mensajes.sql (paso 5 de la guía).'
              : 'Revisa las políticas RLS de pichangol_push_tokens.');
      return _terminar();
    } catch (e) {
      _marcar(pNube, _Estado.fallo,
          detalle: 'Error consultando la nube: $e',
          arreglo: 'Verifica la conexión a internet y repite.');
      return _terminar();
    }

    // 7) Envío real ---------------------------------------------------------
    final pEnvio = _pasos[6];
    _marcar(pEnvio, _Estado.corriendo);
    await _probarEnvio(pEnvio, email);
    _terminar();
  }

  /// Invoca push-aviso a MI propio correo y lee su respuesta, que dice
  /// exactamente qué falta del lado del servidor.
  Future<void> _probarEnvio(_Paso p, String email) async {
    try {
      final res = await SupabaseService.client.functions.invoke(
        'push-aviso',
        body: {
          'email': email,
          'titulo': 'Prueba de notificación 🎾',
          'cuerpo': 'Si lees esto en la barra del sistema, el push funciona.',
          'tipo': 'diagnostico',
        },
      );
      final data = res.data is Map ? res.data as Map : const {};
      final skip = (data['skip'] ?? '').toString();
      final error = (data['error'] ?? '').toString();
      final enviados = (data['enviados'] as num?)?.toInt() ?? -1;
      final total = (data['total'] as num?)?.toInt() ?? 0;

      if (skip == 'sin FCM_SERVICE_ACCOUNT') {
        _marcar(p, _Estado.fallo,
            detalle: 'La Edge Function está desplegada pero SIN la clave '
                'para hablar con Firebase.',
            arreglo: 'Supabase → Edge Functions → Secrets → crear '
                'FCM_SERVICE_ACCOUNT con el JSON de la cuenta de servicio '
                '(paso 3 de la guía).');
      } else if (skip == 'sin tokens') {
        _marcar(p, _Estado.fallo,
            detalle: 'La función corre pero no encontró tokens para '
                '$email.',
            arreglo: 'Raro (el paso anterior lo verificó). Repite el '
                'diagnóstico; si persiste, la función apunta a otro '
                'proyecto Supabase.');
      } else if (error.isNotEmpty) {
        _marcar(p, _Estado.fallo,
            detalle: 'La función respondió error: $error',
            arreglo: 'Mira los Logs de push-aviso en Supabase → Edge '
                'Functions.');
      } else if (enviados >= 1) {
        _marcar(p, _Estado.ok,
            detalle: 'FCM aceptó $enviados de $total dispositivo(s). '
                'Con la app en segundo plano lo verías en la barra del '
                'sistema.');
      } else if (enviados == 0 && total > 0) {
        _marcar(p, _Estado.fallo,
            detalle: 'FCM RECHAZÓ los $total token(s).',
            arreglo: 'Casi siempre: el google-services.json del APK y la '
                'cuenta de servicio (FCM_SERVICE_ACCOUNT) son de proyectos '
                'Firebase DISTINTOS. Deben salir del mismo proyecto. '
                'También pasa si el token es de un APK viejo: reinstala y '
                'repite.');
      } else {
        _marcar(p, _Estado.advertencia,
            detalle: 'Respuesta inesperada de la función: $data');
      }
    } on FunctionException catch (e) {
      if (e.status == 404) {
        _marcar(p, _Estado.fallo,
            detalle: 'La Edge Function push-aviso NO está desplegada en '
                'este proyecto Supabase.',
            arreglo: 'Supabase → Edge Functions → Deploy new function → '
                'nómbrala push-aviso y pega '
                'supabase/functions/push-aviso/index.ts (paso 4 de la '
                'guía). Igual para push-mensaje y push-reserva.');
      } else {
        _marcar(p, _Estado.fallo,
            detalle: 'La función respondió ${e.status}: '
                '${e.details ?? e.reasonPhrase ?? ''}',
            arreglo: 'Mira los Logs de push-aviso en Supabase → Edge '
                'Functions.');
      }
    } catch (e) {
      _marcar(p, _Estado.fallo,
          detalle: 'No se pudo invocar la función: $e',
          arreglo: 'Verifica internet y que la función exista (paso 4 de '
              'la guía).');
    }
  }

  /// Prueba VISUAL: espera unos segundos (para que minimices la app) y recién
  /// ahí dispara el push — así el sistema lo pinta en la barra, como en la vida
  /// real. El resultado queda guardado y lo ves al volver.
  Future<void> _pruebaVisual() async {
    final email = (appState.usuario?.email ?? '').trim().toLowerCase();
    if (email.isEmpty || !SupabaseService.disponible) return;
    ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
        content: Text('Minimiza la app AHORA — la prueba sale en 5 s…')));
    await Future.delayed(const Duration(seconds: 5));
    final paso = _Paso('visual');
    await _probarEnvio(paso, email);
    if (!mounted) return;
    setState(() {
      _resultadoPruebaVisual = paso.estado == _Estado.ok
          ? '✅ Enviada. ¿Sonó y apareció en la barra? Entonces el push está '
              'VIVO de punta a punta.'
          : '❌ ${paso.detalle}\n${paso.arreglo}';
    });
  }

  void _marcar(_Paso p, _Estado e, {String detalle = '', String arreglo = ''}) {
    if (!mounted) return;
    setState(() {
      p.estado = e;
      if (detalle.isNotEmpty) p.detalle = detalle;
      if (arreglo.isNotEmpty) p.arreglo = arreglo;
    });
  }

  void _terminar() {
    if (!mounted) return;
    final primerFallo =
        _pasos.where((p) => p.estado == _Estado.fallo).toList();
    setState(() {
      _corriendo = false;
      if (primerFallo.isEmpty) {
        _conclusionBuena = true;
        _conclusion =
            'La cadena de ENVÍO funciona de punta a punta. Si aun así el '
            'CHAT no te notifica, lo único que falta es conectar el '
            'disparador: mensaje nuevo → push-mensaje (webhook o trigger de '
            'pichangol_mensajes, paso 6 de docs/piloto/push_fcm_setup.md). '
            'Lo mismo aplica a reservas (push-reserva) y matrículas '
            '(push-matricula).';
      } else {
        _conclusionBuena = false;
        _conclusion = 'Eslabón roto: "${primerFallo.first.titulo}". '
            '${primerFallo.first.arreglo}';
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final cs = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(title: const Text('Diagnóstico de notificaciones')),
      body: AnchoTablet(
        maxWidth: 640,
        child: ListView(
          padding: const EdgeInsets.fromLTRB(18, 12, 18, 30),
          children: [
            Text(
              'Prueba cada eslabón de la cadena del push y te dice cuál está '
              'roto. Corre esto en el equipo donde NO llegan las '
              'notificaciones.',
              style: t.bodySmall?.copyWith(color: textoTenueDe(context)),
            ),
            const SizedBox(height: 14),
            for (final p in _pasos) _TilePaso(paso: p),
            const SizedBox(height: 14),
            if (_conclusion.isNotEmpty)
              Container(
                padding: const EdgeInsets.all(14),
                decoration: BoxDecoration(
                  color: (_conclusionBuena ? lima : clayOscuro)
                      .withOpacity(0.10),
                  borderRadius: BorderRadius.circular(16),
                  border: Border.all(
                      color: (_conclusionBuena ? lima : clayOscuro)
                          .withOpacity(0.5)),
                ),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Icon(
                        _conclusionBuena
                            ? Icons.check_circle
                            : Icons.build_circle_outlined,
                        color: _conclusionBuena ? bosque : clayOscuro),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Text(_conclusion,
                          style: t.bodyMedium
                              ?.copyWith(fontWeight: FontWeight.w600)),
                    ),
                  ],
                ),
              ),
            const SizedBox(height: 16),
            FilledButton.icon(
              style: FilledButton.styleFrom(
                backgroundColor: lima,
                foregroundColor: Colors.white,
                minimumSize: const Size.fromHeight(50),
                shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(14)),
              ),
              icon: const Icon(Icons.refresh),
              label: const Text('Repetir diagnóstico',
                  style: TextStyle(fontWeight: FontWeight.w800)),
              onPressed: _corriendo ? null : _correr,
            ),
            const SizedBox(height: 10),
            OutlinedButton.icon(
              style: OutlinedButton.styleFrom(
                foregroundColor: teal,
                side: const BorderSide(color: teal),
                minimumSize: const Size.fromHeight(50),
                shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(14)),
              ),
              icon: const Icon(Icons.notifications_active_outlined),
              label: const Text('Enviarme una prueba (minimiza la app, 5 s)',
                  style: TextStyle(fontWeight: FontWeight.w800)),
              onPressed: _corriendo ? null : _pruebaVisual,
            ),
            if (_resultadoPruebaVisual.isNotEmpty) ...[
              const SizedBox(height: 10),
              Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: cs.surface,
                  borderRadius: BorderRadius.circular(14),
                  border: Border.all(color: trazo),
                ),
                child: Text(_resultadoPruebaVisual, style: t.bodySmall),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _TilePaso extends StatelessWidget {
  const _TilePaso({required this.paso});
  final _Paso paso;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final cs = Theme.of(context).colorScheme;

    final (icono, color) = switch (paso.estado) {
      _Estado.pendiente => (Icons.circle_outlined, textoTenue),
      _Estado.corriendo => (Icons.sync, teal),
      _Estado.ok => (Icons.check_circle, bosque),
      _Estado.advertencia => (Icons.error_outline, amarillo),
      _Estado.fallo => (Icons.cancel, clayOscuro),
    };

    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      decoration: BoxDecoration(
        color: cs.surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: trazo),
        boxShadow: const [
          BoxShadow(
              color: Color(0x0F000000), blurRadius: 8, offset: Offset(0, 3)),
        ],
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          paso.estado == _Estado.corriendo
              ? const SizedBox(
                  width: 22,
                  height: 22,
                  child: CircularProgressIndicator(strokeWidth: 2.4))
              : Icon(icono, color: color, size: 24),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(paso.titulo,
                    style:
                        t.titleSmall?.copyWith(fontWeight: FontWeight.w700)),
                if (paso.detalle.isNotEmpty) ...[
                  const SizedBox(height: 2),
                  Text(paso.detalle,
                      style: t.bodySmall
                          ?.copyWith(color: textoTenueDe(context))),
                ],
                if (paso.arreglo.isNotEmpty &&
                    paso.estado == _Estado.fallo) ...[
                  const SizedBox(height: 6),
                  Text('Cómo arreglarlo: ${paso.arreglo}',
                      style: t.bodySmall?.copyWith(
                          color: clayOscuro, fontWeight: FontWeight.w600)),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}
