import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';

import 'brand.dart';
import 'config/pais.dart';
import 'screens/splash_screen.dart';
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
  runApp(const PichangolApp());
}

class PichangolApp extends StatelessWidget {
  const PichangolApp({super.key});

  @override
  Widget build(BuildContext context) {
    // Reconstruye la app cuando cambia el modo de tema (Claro/Oscuro/Automático).
    return ListenableBuilder(
      listenable: appState,
      builder: (context, _) => MaterialApp(
        title: kBrandName,
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
