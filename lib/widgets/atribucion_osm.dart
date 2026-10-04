import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../theme.dart';

/// Atribución pequeña "© OpenStreetMap" para los lugares que vienen de
/// OpenStreetMap (`Cancha.esOsm`). La licencia ODbL la exige; al tocarla abre
/// la página de derechos de autor de OSM en el navegador.
class AtribucionOsm extends StatelessWidget {
  const AtribucionOsm({super.key});

  static final Uri _url = Uri.parse('https://www.openstreetmap.org/copyright');

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: () async {
        try {
          await launchUrl(_url, mode: LaunchMode.externalApplication);
        } catch (_) {}
      },
      child: Padding(
        padding: const EdgeInsets.only(top: 2),
        child: Text(
          '© colaboradores de OpenStreetMap',
          style: TextStyle(
            fontSize: 10.5,
            color: textoTenueDe(context),
            decoration: TextDecoration.underline,
            decorationColor: textoTenueDe(context),
          ),
        ),
      ),
    );
  }
}
