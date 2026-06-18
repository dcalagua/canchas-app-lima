import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';

import 'screens/explorar_home_screen.dart';
import 'theme.dart';

void main() => runApp(const CanchasApp());

class CanchasApp extends StatelessWidget {
  const CanchasApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Canchas Lima',
      debugShowCheckedModeBanner: false,
      theme: buildTheme(),
      locale: const Locale('es'),
      supportedLocales: const [Locale('es'), Locale('en')],
      localizationsDelegates: const [
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      // Pantalla de inicio estilo Airbnb (mapa de Google a pantalla completa).
      home: const ExplorarHomeScreen(),
    );
  }
}
