import 'package:google_maps_flutter/google_maps_flutter.dart';

import '../models/models.dart';
import '../utils/geo.dart';
import '../utils/moneda.dart';
import 'concierge_service.dart'; // reutiliza SugerenciaConcierge / RespuestaConcierge

/// Búsqueda inteligente por **REGLAS** (sin IA, costo CERO). Interpreta la
/// consulta del jugador en lenguaje natural —deporte (con jerga peruana),
/// intención de precio ("barato"), y día/hora para el texto— y devuelve canchas
/// reservables filtradas y ordenadas por cercanía. Reemplaza al concierge LLM
/// (que Pichangol pagaba por token): cubre el grueso de las intenciones gratis.
class BusquedaLocal {
  /// Radio máximo (km) para considerar una cancha "de tu zona". Más allá, se
  /// asume que no hay oferta cerca (mejor invitar a registrar que sugerir lejos).
  static const double _radioKm = 50;

  static RespuestaConcierge recomendar(
    String mensaje,
    List<Cancha> canchas, {
    LatLng? centro,
  }) {
    final t = _norma(mensaje);
    final deporte = _deporteEn(t);
    final barato = _quiereBarato(t);
    final cuando = _cuandoTexto(t);

    // Solo canchas RESERVABLES (en Pichangol y con propiedad verificada): así el
    // botón "Reservar" de la tarjeta siempre funciona.
    var lista = canchas.where((c) => c.reservable).toList();
    if (deporte != null) {
      lista = lista.where((c) => c.ofrece(deporte)).toList();
    }
    // Acota a la zona del usuario (si sabemos dónde está).
    if (centro != null) {
      lista = lista
          .where((c) => distanciaKm(centro, c.ubicacion) <= _radioKm)
          .toList();
    }

    // Orden: si pidió "barato" → precio ascendente; si no y hay ubicación → por
    // cercanía; si no, deja el orden natural.
    if (barato) {
      lista.sort((a, b) => a.precioHora.compareTo(b.precioHora));
    } else if (centro != null) {
      lista.sort((a, b) => distanciaKm(centro, a.ubicacion)
          .compareTo(distanciaKm(centro, b.ubicacion)));
    }

    final top = lista.take(6).toList();
    final sugs = [
      for (final c in top)
        SugerenciaConcierge(cancha: c, motivo: _motivo(c, centro, barato)),
    ];
    return RespuestaConcierge(
      respuesta: _texto(deporte, barato, cuando, top.length),
      sugerencias: sugs,
      viaIa: false,
    );
  }

  // ── Parsers ────────────────────────────────────────────────────────────────

  /// Deporte mencionado (con jerga PE). Null si no se reconoce ninguno.
  static Deporte? _deporteEn(String t) {
    if (t.contains('pickle')) return Deporte.pickleball;
    // Vóley: incluye 'ecuavoley' (variante nacional de Ecuador, 3 vs 3).
    if (t.contains('voley') || t.contains('voleibol') || t.contains('volei') ||
        t.contains('volley') || t.contains('ecuavoley')) {
      return Deporte.voley;
    }
    if (t.contains('basquet') || t.contains('basket') ||
        t.contains('basketbol') || t.contains('basquetbol')) {
      return Deporte.basquet;
    }
    if (t.contains('tenis') || t.contains('tennis') || t.contains('raqueta')) {
      return Deporte.tenis;
    }
    // Fútbol y su jerga por país (sin 'cancha', que es genérico):
    //  PE: pichanga/pichanguita/fulbito · BO: picho · EC: indor/picadito.
    if (t.contains('futbol') || t.contains('futsal') || t.contains('fulbito') ||
        t.contains('pichang') || t.contains('picho') || t.contains('indor') ||
        t.contains('picadito') || t.contains('grass') ||
        t.contains('sintetic') || t.contains('fut ')) {
      return Deporte.futbol;
    }
    return null;
  }

  static bool _quiereBarato(String t) =>
      t.contains('barat') ||
      t.contains('economic') ||
      t.contains('mas barat') ||
      t.contains('menor precio') ||
      t.contains('mas barato');

  /// Frase corta de "cuándo" para el texto de respuesta (no filtra canchas: la
  /// disponibilidad se ve al reservar). "" si no menciona día/hora.
  static String _cuandoTexto(String t) {
    final partes = <String>[];
    // "mañana" = día siguiente, salvo "en/por la mañana" (= turno mañana).
    final esTurnoManiana =
        t.contains('la maniana') || t.contains('en la maniana');
    if (t.contains('maniana') && !esTurnoManiana) {
      partes.add('mañana');
    } else if (t.contains('hoy')) {
      partes.add('hoy');
    }
    // Hora tipo "8pm", "20:00", "8 pm".
    final hora = RegExp(r'(\d{1,2})\s*(:\d{2})?\s*(am|pm)?').firstMatch(t);
    if (hora != null &&
        (t.contains('pm') || t.contains('am') || t.contains(':'))) {
      partes.add('a las ${hora.group(0)!.trim()}');
    }
    return partes.isEmpty ? '' : ' para ${partes.join(' ')}';
  }

  static String _motivo(Cancha c, LatLng? centro, bool barato) {
    if (barato) return 'De las más económicas · ${precio(c.precioHora)}/h';
    final zona = c.zonaMostrable;
    if (centro != null) {
      final d = distanciaKm(centro, c.ubicacion);
      final base = 'A ${d.toStringAsFixed(1)} km de ti';
      return zona.isNotEmpty ? '$base · $zona' : base;
    }
    return zona.isNotEmpty ? zona : c.club;
  }

  static String _texto(Deporte? dep, bool barato, String cuando, int n) {
    final q = dep != null ? '${dep.etiqueta.toLowerCase()} ' : '';
    if (n == 0) {
      return 'No encontré canchas ${q}reservables cerca de ti$cuando. 😕\n'
          'Prueba con otro deporte, o si conoces una, ¡regístrala en Pichangol! 🙌';
    }
    final b = barato ? 'más económicas ' : '';
    return '¡Listo! Estas canchas ${q}${b}son las más cercanas a ti$cuando 👇';
  }

  // ── Utilidad ────────────────────────────────────────────────────────────────

  /// minúsculas + sin acentos, para comparar sin sorpresas.
  static String _norma(String s) {
    const acento = 'áàäâéèëêíìïîóòöôúùüûñ';
    const plano = 'aaaaeeeeiiiioooouuuun';
    final b = StringBuffer();
    for (final ch in s.toLowerCase().split('')) {
      final i = acento.indexOf(ch);
      b.write(i >= 0 ? plano[i] : ch);
    }
    return b.toString();
  }
}
