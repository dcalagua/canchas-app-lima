import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';

import 'brand.dart';
import 'config/pais.dart';
import 'data/presencia_repo.dart';
import 'screens/llamada_screen.dart';
import 'screens/mensajes_screen.dart';
import 'screens/home_shell.dart';
import 'screens/reservas_dueno_screen.dart';
import 'services/recordatorio_service.dart';
import 'screens/splash_screen.dart';
import 'services/llamada_service.dart';
import 'services/llamada_webrtc.dart';
import 'services/push_service.dart';
import 'services/supabase_service.dart';
import 'state/app_state.dart';
import 'theme.dart';

/// Entorno del build (dev | qas | prod), inyectado por `--dart-define=ENTORNO`.
/// En QAS la app muestra un banner para no confundir con producción.
const String kEntorno = String.fromEnvironment('ENTORNO', defaultValue: 'dev');

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  // Moneda correcta desde el primer frame (y offline): recupera el país
  // detectado la última vez. El GPS luego lo confirma/actualiza al abrir Explorar.
  await cargarPaisPersistido();
  await SupabaseService.init();
  // Notificaciones push del chat (Etapa B). Fail-safe: sin config de Firebase
  // queda desactivado y la app sigue igual.
  await PushService.init();
  // Recordatorios LOCALES (cobra en efectivo). Fail-safe: si el plugin no
  // inicializa, no rompe la app.
  await RecordatorioService.init();
  // Al tocar una notificación (o el aviso in-app), abre la bandeja en el chat
  // correspondiente. Se usa el navegador global de PushService.
  PushService.alAbrirChat = (hilo) {
    final nav = PushService.navigatorKey.currentState;
    if (nav == null || hilo.isEmpty) return;
    nav.push(MaterialPageRoute(
        builder: (_) => MensajesScreen(abrirHilo: hilo)));
  };
  // Al tocar el push de "Nueva reserva", abre el panel de Reservas del dueño.
  PushService.alAbrirReservas = () {
    final nav = PushService.navigatorKey.currentState;
    if (nav == null) return;
    nav.push(MaterialPageRoute(builder: (_) => const ReservasDuenoScreen()));
  };
  // Al tocar el push "tu cancha fue aprobada", abre el panel del dueño en "Mis
  // canchas" (la cancha ya sale verificada tras sincronizar propiedades).
  PushService.alAbrirMisCanchas = () {
    final nav = PushService.navigatorKey.currentState;
    if (nav == null) return;
    nav.push(MaterialPageRoute(builder: (_) => const HomeShell()));
  };
  // Al CONTESTAR una llamada entrante (CallKit), abre la pantalla de llamada
  // WebRTC en modo "contestar".
  LlamadaService.alContestar = (room, video, nombre, hilo) {
    if (room.isEmpty) return;
    final foto = _fotoDeHilo(hilo); // foto del que llama (para la pantalla)
    final email = _emailDeHilo(hilo); // correo del que llama (para el historial)
    // El navegador puede no estar montado todavía (resume / arranque en frío):
    // reintenta unos instantes hasta que exista, y recién ahí abre la pantalla.
    void abrir([int intento = 0]) {
      final nav = PushService.navigatorKey.currentState;
      if (nav == null) {
        if (intento < 25) {
          Future.delayed(const Duration(milliseconds: 150),
              () => abrir(intento + 1));
        }
        return;
      }
      nav.push(MaterialPageRoute(
          builder: (_) => LlamadaScreen(
              callId: room,
              video: video,
              iniciar: false,
              nombreOtro: nombre,
              fotoUrl: foto,
              emailOtro: email)));
    }

    abrir();
  };
  // Fallback (Xiaomi/HyperOS): mostrar la llamada ENTRANTE DENTRO de la app
  // (Contestar/Rechazar) cuando el evento "Contestar" de CallKit no llega.
  LlamadaService.alEntranteEnApp = (room, video, nombre, hilo) {
    if (room.isEmpty) return;
    final foto = _fotoDeHilo(hilo);
    final email = _emailDeHilo(hilo);
    final nav = PushService.navigatorKey.currentState;
    if (nav == null) return;
    nav.push(MaterialPageRoute(
        builder: (_) => LlamadaScreen(
            callId: room,
            video: video,
            iniciar: false,
            modoEntrante: true,
            nombreOtro: nombre,
            fotoUrl: foto,
            emailOtro: email)));
  };
  runApp(const PichangolApp());
  // Si la app arrancó porque se CONTESTÓ una llamada con la app cerrada, abre la
  // pantalla de llamada una vez montado el navegador.
  WidgetsBinding.instance.addPostFrameCallback((_) {
    LlamadaService.revisarLlamadaAlArrancar();
  });
}

class PichangolApp extends StatefulWidget {
  const PichangolApp({super.key});

  @override
  State<PichangolApp> createState() => _PichangolAppState();
}

class _PichangolAppState extends State<PichangolApp>
    with WidgetsBindingObserver {
  Timer? _latidoPresencia;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    // Presencia "en línea / última vez": late cada 25 s mientras la app esté
    // en primer plano (y al minimizar/volver). Persiste en pichangol_presencia.
    _latir();
    _latidoPresencia =
        Timer.periodic(const Duration(seconds: 25), (_) => _latir());
  }

  void _latir() {
    // Respeta la privacidad: si el usuario apagó "última vez / en línea", no
    // reporto mi presencia (nadie me ve conectado).
    if (!appState.mostrarUltimaVez) return;
    final e = appState.usuario?.email ?? '';
    if (e.isNotEmpty) PresenciaRepo.latir(e);
  }

  @override
  void dispose() {
    _latidoPresencia?.cancel();
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    // Cuando el usuario toca "Contestar" (o la notificación de llamada en
    // curso), Android trae la app al frente → aquí abrimos la pantalla completa
    // de la llamada. Es la vía más confiable para el que RECIBE la llamada.
    if (state == AppLifecycleState.resumed) {
      LlamadaService.revisarLlamadaResumida();
      // Si hay una llamada EN CURSO y se perdió la pantalla grande (p. ej. al
      // tocar la notificación de "llamada en curso"), la reabrimos.
      abrirLlamadaEnCurso();
      _latir(); // volví: actualizo mi presencia
      // Reintenta subir reservas que se hicieron sin señal (outbox offline) y
      // registrar la contabilidad (comisión/liquidación) que quedó pendiente.
      appState.sincronizarReservasPendientes();
      appState.flushContabilidad();
      // Baja reservas nuevas (p. ej. si llegó un push de reserva con la app en
      // segundo plano): al volver, el panel del dueño ya está al día.
      appState.cargarReservasRemotas();
    } else if (state == AppLifecycleState.paused ||
        state == AppLifecycleState.inactive) {
      _latir(); // me voy: registro mi "última vez" ahora
    }
  }

  @override
  Widget build(BuildContext context) {
    // Reconstruye la app cuando cambia el modo de tema (Claro/Oscuro/Automático).
    return ListenableBuilder(
      listenable: appState,
      builder: (context, _) => MaterialApp(
        title: kBrandName,
        navigatorKey: PushService.navigatorKey,
        debugShowCheckedModeBanner: false,
        theme: buildTheme(),
        darkTheme: buildThemeOscuro(),
        themeMode: appState.temaModo,
        locale: const Locale('es'),
        supportedLocales: const [Locale('es'), Locale('en')],
        localizationsDelegates: const [
          GlobalMaterialLocalizations.delegate,
          GlobalWidgetsLocalizations.delegate,
          GlobalCupertinoLocalizations.delegate,
        ],
        // Arranca en el splash de marca y luego entra al mapa (estilo Airbnb).
        home: const SplashScreen(),
        // Banner "QAS" (esquina) + barra "volver a la llamada" (estilo WhatsApp).
        builder: (context, child) {
          Widget contenido = child ?? const SizedBox();
          if (kEntorno == 'qas') {
            contenido = Banner(
              message: 'QAS',
              location: BannerLocation.topEnd,
              color: const Color(0xFFC75B39),
              child: contenido,
            );
          }
          return Stack(
            textDirection: TextDirection.ltr,
            children: [
              contenido,
              const _BarraLlamada(),
            ],
          );
        },
      ),
    );
  }
}

/// Deduce el correo del OTRO participante a partir del hilo directo
/// (`directo_<a>|<b>`): el que no es el mío.
String _emailDeHilo(String hilo) {
  if (!hilo.startsWith('directo_')) return '';
  final partes = hilo.substring('directo_'.length).split('|');
  if (partes.length != 2) return '';
  final yo = (appState.usuario?.email ?? '').trim().toLowerCase();
  return partes[0] == yo ? partes[1] : partes[0];
}

/// Foto del OTRO participante (a partir de su correo deducido del hilo).
String _fotoDeHilo(String hilo) {
  final otro = _emailDeHilo(hilo);
  return otro.isEmpty ? '' : (appState.fotoDe(otro) ?? '');
}

/// Reabre la pantalla completa de una llamada EN CURSO (no arranca nada). La
/// usan la barra "volver a la llamada" y el resume del ciclo de vida.
void abrirLlamadaEnCurso() {
  final svc = LlamadaWebRTC.instance;
  if (!svc.activa || LlamadaWebRTC.pantallaVisible) return;
  final nav = PushService.navigatorKey.currentState;
  nav?.push(MaterialPageRoute(
    builder: (_) => LlamadaScreen(
      callId: '',
      video: svc.video,
      iniciar: false,
      reattach: true,
      nombreOtro: svc.nombreOtro,
      fotoUrl: svc.fotoOtro,
      emailOtro: svc.emailOtro,
    ),
  ));
}

/// Barra superior "Toca para volver a la llamada" (como la barra verde de
/// WhatsApp). Solo aparece si hay llamada en curso y NO estás viendo la
/// pantalla grande.
class _BarraLlamada extends StatefulWidget {
  const _BarraLlamada();

  @override
  State<_BarraLlamada> createState() => _BarraLlamadaState();
}

class _BarraLlamadaState extends State<_BarraLlamada> {
  Timer? _tick;

  @override
  void initState() {
    super.initState();
    LlamadaWebRTC.instance.addListener(_actualizar);
    _tick = Timer.periodic(const Duration(seconds: 1), (_) {
      if (mounted) setState(() {});
    });
  }

  void _actualizar() {
    if (mounted) setState(() {});
  }

  @override
  void dispose() {
    _tick?.cancel();
    LlamadaWebRTC.instance.removeListener(_actualizar);
    super.dispose();
  }

  String _texto(LlamadaWebRTC s) {
    switch (s.estado) {
      case EstadoLlamada.llamando:
        return 'Llamando…';
      case EstadoLlamada.conectando:
        return 'Conectando…';
      case EstadoLlamada.enLlamada:
        final ini = s.conectadoEn;
        if (ini == null) return 'En llamada';
        final d = DateTime.now().difference(ini);
        final m = d.inMinutes.toString().padLeft(2, '0');
        final sec = (d.inSeconds % 60).toString().padLeft(2, '0');
        return '$m:$sec';
      default:
        return '';
    }
  }

  @override
  Widget build(BuildContext context) {
    final s = LlamadaWebRTC.instance;
    if (!s.activa || LlamadaWebRTC.pantallaVisible) {
      return const SizedBox.shrink();
    }
    return Positioned(
      top: 0,
      left: 0,
      right: 0,
      child: Material(
        color: Colors.transparent,
        child: SafeArea(
          bottom: false,
          child: GestureDetector(
            onTap: abrirLlamadaEnCurso,
            child: Container(
              width: double.infinity,
              color: const Color(0xFF128C7E),
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 7),
              child: Row(
                children: [
                  const Icon(Icons.phone_in_talk, color: Colors.white, size: 18),
                  const SizedBox(width: 10),
                  const Expanded(
                    child: Text('Toca para volver a la llamada',
                        style: TextStyle(
                            color: Colors.white,
                            fontWeight: FontWeight.w700,
                            fontSize: 13.5)),
                  ),
                  Text(_texto(s),
                      style: const TextStyle(
                          color: Colors.white, fontSize: 12.5)),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
