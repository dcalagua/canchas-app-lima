import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';

import 'brand.dart';
import 'screens/splash_screen.dart';
import 'theme.dart';

void main() => runApp(const PichangolApp());

class PichangolApp extends StatelessWidget {
  const PichangolApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: kBrandName,
      debugShowCheckedModeBanner: false,
      theme: buildTheme(),
      locale: const Locale('es'),
      supportedLocales: const [Locale('es'), Locale('en')],
      localizationsDelegates: const [
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      // Arranca en el splash de marca y luego entra al mapa (estilo Airbnb).
      home: const SplashScreen(),
    );
  }
}
