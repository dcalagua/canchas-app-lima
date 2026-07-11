import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';

import 'brand.dart';
import 'screens/splash_screen.dart';
import 'services/supabase_service.dart';
import 'state/app_state.dart';
import 'theme.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await SupabaseService.init();
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
      ),
    );
  }
}
