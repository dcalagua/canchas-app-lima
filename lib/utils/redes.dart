import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:url_launcher/url_launcher.dart';

import '../theme.dart';

/// Catálogo de redes que una academia/cancha puede publicar. Fuente única de
/// verdad para el editor (chips seleccionables) y la ficha (badges de marca).
const redesCatalogo = <(String, String, IconData)>[
  ('instagram', 'Instagram', FontAwesomeIcons.instagram),
  ('facebook', 'Facebook', FontAwesomeIcons.facebook),
  ('tiktok', 'TikTok', FontAwesomeIcons.tiktok),
  ('youtube', 'YouTube', FontAwesomeIcons.youtube),
  ('web', 'Web', FontAwesomeIcons.globe),
];

/// Ícono de cada red (por su clave).
const iconoRed = <String, IconData>{
  'instagram': FontAwesomeIcons.instagram,
  'facebook': FontAwesomeIcons.facebook,
  'tiktok': FontAwesomeIcons.tiktok,
  'youtube': FontAwesomeIcons.youtube,
  'web': FontAwesomeIcons.globe,
};

/// Color sólido de marca de cada red (Instagram usa degradado aparte).
const _colorRed = <String, Color>{
  'facebook': Color(0xFF1877F2),
  'tiktok': Color(0xFF010101),
  'youtube': Color(0xFFFF0000),
  'web': bosque,
};

/// Degradado oficial de Instagram (solo para su badge).
const _gradInstagram = LinearGradient(
  begin: Alignment.bottomLeft,
  end: Alignment.topRight,
  colors: [
    Color(0xFFFEDA75),
    Color(0xFFFA7E1E),
    Color(0xFFD62976),
    Color(0xFF962FBF),
    Color(0xFF4F5BD5),
  ],
);

/// Convierte el usuario/enlace guardado en una URL abrible.
Uri? urlRed(String clave, String valor) {
  final v = valor.trim();
  if (v.isEmpty) return null;
  if (v.startsWith('http://') || v.startsWith('https://')) return Uri.tryParse(v);
  final u = v.startsWith('@') ? v.substring(1) : v;
  switch (clave) {
    case 'instagram':
      return Uri.parse('https://instagram.com/$u');
    case 'facebook':
      return Uri.parse('https://facebook.com/$u');
    case 'tiktok':
      return Uri.parse('https://tiktok.com/@$u');
    case 'youtube':
      return Uri.parse('https://youtube.com/@$u');
    default:
      return Uri.tryParse(v.contains('.') ? 'https://$v' : v);
  }
}

/// Badge circular con el color/ícono real de la red, clicable (abre el perfil).
class RedBadge extends StatelessWidget {
  const RedBadge({super.key, required this.clave, required this.valor, this.size = 40});
  final String clave;
  final String valor;
  final double size;

  @override
  Widget build(BuildContext context) {
    final url = urlRed(clave, valor);
    return Padding(
      padding: const EdgeInsets.only(right: 10),
      child: InkWell(
        borderRadius: BorderRadius.circular(999),
        onTap: url == null
            ? null
            : () => launchUrl(url, mode: LaunchMode.externalApplication),
        child: Container(
          width: size,
          height: size,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            gradient: clave == 'instagram' ? _gradInstagram : null,
            color: clave == 'instagram' ? null : (_colorRed[clave] ?? bosque),
          ),
          child: Center(
            child: FaIcon(iconoRed[clave] ?? FontAwesomeIcons.globe,
                size: size * 0.48, color: Colors.white),
          ),
        ),
      ),
    );
  }
}
