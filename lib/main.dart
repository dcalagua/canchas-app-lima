import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';

import 'brand.dart';
import 'config/pais.dart';
import 'screens/llamada_screen.dart';
import 'screens/mensajes_screen.dart';
import 'screens/splash_screen.dart';
import 'services/llamada_service.dart';
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
  // Al tocar una notificación (o el aviso in-app), abre la bandeja en el chat
  // correspondiente. Se usa el navegador global de PushService.
  PushService.alAbrirChat = (hilo) {
    final nav = PushService.navigatorKey.currentState;
    if (nav == null || hilo.isEmpty) return;
    nav.push(MaterialPageRoute(
        builder: (_) => MensajesScreen(abrirHilo: hilo)));
  };
  // Al CONTESTAR una llamada entrante (CallKit), abre la pantalla de llamada
  // WebRTC en modo "contestar".
  LlamadaService.alContestar = (room, video, nombre) {
    final nav = PushService.navigatorKey.currentState;
    if (nav == null || room.isEmpty) return;
    nav.push(MaterialPageRoute(
        builder: (_) => LlamadaScreen(
            callId: room, video: video, iniciar: false, nombreOtro: nombre)));
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
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
  }

  @override
  void dispose() {
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
        // Banner "QAS" (esquina) solo en builds de pruebas, para no confundirlo
        // con producción.
        builder: (context, child) {
          if (kEntorno != 'qas' || child == null) return child ?? const SizedBox();
          return Banner(
            message: 'QAS',
            location: BannerLocation.topEnd,
            color: const Color(0xFFC75B39),
            child: child,
          );
        },
      ),
    );
  }
}
