import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../config/pais.dart';
import '../services/pagos_service.dart';
import 'models.dart';

/// BOLEADORES (peloteo por turno, sep-2026; `docs/diseno-boleadores.md`).
///
/// Jugadores de la Liga Pichangol se registran como boleadores (categoría 5P…
/// 1ra, tarifa por turno, locales donde atienden, disponibilidad). El cliente
/// que reserva una cancha de tenis/pádel elige uno como servicio extra y paga
/// TODO junto en línea; el boleador recibe un push, ACEPTA o rechaza; al
/// aceptar, su neto (tarifa − comisión fija S/ 2 · \$ 0.50 · Bs 3 por turno)
/// queda "por recibir" en su billetera. Si no puede, se le devuelve al cliente
/// su parte. La fuente de verdad es el backend (`boleadores.py`); este archivo
/// es el espejo del APK: modelos + caché + outbox.

/// Catálogos del registro para el país (config pública del backend).
class BoleadorConfig {
  final bool activo;
  final String nombre; // "Boleador" (PE) / "Sparring" (BO, EC)
  final List<String> categorias;
  final List<String> deportes;
  final List<String> etiquetas;
  final List<double> tarifas;
  final double tarifaMax;
  final String moneda; // ISO
  final String simbolo;
  final double comision;
  final int horasAceptar;

  const BoleadorConfig({
    required this.activo,
    required this.nombre,
    required this.categorias,
    required this.deportes,
    required this.etiquetas,
    required this.tarifas,
    required this.tarifaMax,
    required this.moneda,
    required this.simbolo,
    required this.comision,
    required this.horasAceptar,
  });

  /// Respaldo empaquetado (sin red): categorías de la Liga Pichangol y la
  /// comisión fija del país. Espejo de las constantes del backend.
  factory BoleadorConfig.local(PaisConfig pais) => BoleadorConfig(
        activo: true,
        nombre: pais.nombreBoleador,
        categorias: const ['5P', '5A', '5B', '4ta', '3ra', '2da', '1ra'],
        deportes: const ['tenis', 'padel'],
        etiquetas: const [
          'Peloteo',
          'Partido de práctica',
          'Clases a niños',
          'Principiantes bienvenidos',
          'Dobles',
          'Alta intensidad',
          'Zurdo',
          'Saque fuerte',
        ],
        tarifas: switch (pais.monedaIso) {
          'USD' => const <double>[5, 8, 10, 12, 15, 20],
          'BOB' => const <double>[30, 40, 50, 70, 100],
          _ => const <double>[15, 20, 25, 30, 40, 50],
        },
        tarifaMax: switch (pais.monedaIso) {
          'USD' => 100.0,
          'BOB' => 700.0,
          _ => 300.0,
        },
        moneda: pais.monedaIso,
        simbolo: pais.moneda,
        comision: pais.comisionBoleador,
        horasAceptar: 2,
      );

  factory BoleadorConfig.fromJson(Map<String, dynamic> j, PaisConfig pais) {
    final local = BoleadorConfig.local(pais);
    List<String> lista(dynamic v, List<String> def) =>
        v is List && v.isNotEmpty ? v.map((e) => e.toString()).toList() : def;
    return BoleadorConfig(
      activo: j['activo'] != false,
      nombre: (j['nombre'] ?? local.nombre).toString(),
      categorias: lista(j['categorias'], local.categorias),
      deportes: lista(j['deportes'], local.deportes),
      etiquetas: lista(j['etiquetas'], local.etiquetas),
      tarifas: j['tarifas'] is List && (j['tarifas'] as List).isNotEmpty
          ? (j['tarifas'] as List)
              .whereType<num>()
              .map((e) => e.toDouble())
              .toList()
          : local.tarifas,
      tarifaMax: ((j['tarifa_max'] ?? local.tarifaMax) as num).toDouble(),
      moneda: (j['moneda'] ?? local.moneda).toString(),
      simbolo: (j['simbolo'] ?? local.simbolo).toString(),
      comision: ((j['comision'] ?? local.comision) as num).toDouble(),
      horasAceptar: ((j['horas_aceptar'] ?? 2) as num).toInt(),
    );
  }
}

/// Lo que ve el CLIENTE de un boleador disponible (sin correo).
class BoleadorPublico {
  final String slug;
  final String nombre;
  final String foto;
  final String categoria;
  final String deporte;
  final double tarifa;
  final String moneda; // ISO
  final String simbolo;
  final List<String> etiquetas;
  final int aceptadas;

  const BoleadorPublico({
    required this.slug,
    required this.nombre,
    required this.foto,
    required this.categoria,
    required this.deporte,
    required this.tarifa,
    required this.moneda,
    required this.simbolo,
    required this.etiquetas,
    required this.aceptadas,
  });

  factory BoleadorPublico.fromJson(Map<String, dynamic> j) => BoleadorPublico(
        slug: (j['slug'] ?? '').toString(),
        nombre: (j['nombre'] ?? '').toString(),
        foto: (j['foto'] ?? '').toString(),
        categoria: (j['categoria'] ?? '').toString(),
        deporte: (j['deporte'] ?? 'tenis').toString(),
        tarifa: ((j['tarifa'] ?? 0) as num).toDouble(),
        moneda: (j['moneda'] ?? 'PEN').toString(),
        simbolo: (j['simbolo'] ?? 'S/').toString(),
        etiquetas: (j['etiquetas'] as List? ?? const [])
            .map((e) => e.toString())
            .toList(),
        aceptadas: ((j['aceptadas'] ?? 0) as num).toInt(),
      );

  String get inicial => nombre.trim().isEmpty ? '?' : nombre.trim()[0].toUpperCase();

  /// "Peloteo · Zurdo · 12 boleos" (o "Nuevo en Pichangol").
  String get detalle {
    final partes = [
      ...etiquetas.take(3),
      aceptadas > 0 ? '$aceptadas boleo${aceptadas == 1 ? '' : 's'}' : 'Nuevo en Pichangol',
    ];
    return partes.join(' · ');
  }

  /// Línea de servicio extra para la RESERVA: tarifa × turnos, tipo `turno`,
  /// misma forma que `boleadores.linea_reserva` del backend (así el dueño, la
  /// web y el comprobante la entienden igual).
  ServicioExtra linea(int turnos) {
    final n = turnos < 1 ? 1 : turnos;
    return ServicioExtra(
      clave: 'boleador',
      precio: tarifa * n,
      nombre: 'Boleador · $nombre',
      emoji: '🎾',
      tipo: 'turno',
      ambito: 'cancha',
      cantidad: n,
      unitario: tarifa,
      boleador: slug,
      estado: 'pendiente',
    );
  }
}

/// Una solicitud de boleo (la ve el boleador para aceptar/rechazar y el
/// cliente para saber en qué quedó).
class SolicitudBoleo {
  final String id;
  final String boleadorEmail;
  final String clienteEmail;
  final String clienteNombre;
  final String reservaRef;
  final List<String> reservaIds;
  final String canchaId;
  final String club;
  final String cancha;
  final String fecha; // ISO
  final String horaInicio;
  final String horaFin;
  final int turnos;
  final int montoCentimos;
  final int comisionCentimos;
  final String moneda; // ISO
  final String estado;
  final String estadoVisible;
  final String canal;
  final DateTime? venceEn;
  final String creado;
  final Map<String, dynamic> data;

  const SolicitudBoleo({
    required this.id,
    required this.boleadorEmail,
    required this.clienteEmail,
    required this.clienteNombre,
    required this.reservaRef,
    required this.reservaIds,
    required this.canchaId,
    required this.club,
    required this.cancha,
    required this.fecha,
    required this.horaInicio,
    required this.horaFin,
    required this.turnos,
    required this.montoCentimos,
    required this.comisionCentimos,
    required this.moneda,
    required this.estado,
    required this.estadoVisible,
    required this.canal,
    required this.venceEn,
    required this.creado,
    required this.data,
  });

  factory SolicitudBoleo.fromJson(Map<String, dynamic> j) {
    final data = j['data'] is Map
        ? Map<String, dynamic>.from(j['data'] as Map)
        : <String, dynamic>{};
    DateTime? vence;
    final v = (j['vence_en'] ?? '').toString();
    if (v.isNotEmpty) vence = DateTime.tryParse(v)?.toLocal();
    return SolicitudBoleo(
      id: (j['id'] ?? '').toString(),
      boleadorEmail: (j['boleador_email'] ?? '').toString(),
      clienteEmail: (j['cliente_email'] ?? '').toString(),
      clienteNombre: (j['cliente_nombre'] ?? '').toString(),
      reservaRef: (j['reserva_ref'] ?? '').toString(),
      reservaIds: (data['reserva_ids'] as List? ?? const [])
          .map((e) => e.toString())
          .toList(),
      canchaId: (j['cancha_id'] ?? '').toString(),
      club: (j['club'] ?? '').toString(),
      cancha: (data['cancha'] ?? '').toString(),
      fecha: (j['fecha'] ?? '').toString(),
      horaInicio: (j['hora_inicio'] ?? '').toString(),
      horaFin: (j['hora_fin'] ?? '').toString(),
      turnos: ((j['turnos'] ?? 1) as num).toInt(),
      montoCentimos: ((j['monto_centimos'] ?? 0) as num).toInt(),
      comisionCentimos: ((j['comision_centimos'] ?? 0) as num).toInt(),
      moneda: (j['moneda'] ?? 'PEN').toString(),
      estado: (j['estado'] ?? '').toString(),
      estadoVisible: (j['estado_visible'] ?? '').toString(),
      canal: (j['canal'] ?? '').toString(),
      venceEn: vence,
      creado: (j['creado'] ?? '').toString(),
      data: data,
    );
  }

  bool get pendiente => estado == 'pendiente';
  bool get aceptada => estado == 'aceptada';
  bool get viva => pendiente || aceptada;
  double get monto => montoCentimos / 100.0;
  double get comision => comisionCentimos / 100.0;
  double get neto => (montoCentimos - comisionCentimos) / 100.0;
  String get simbolo => switch (moneda) {
        'USD' => '\$',
        'BOB' => 'Bs',
        _ => 'S/',
      };
  String get lugar => club.isNotEmpty ? club : (cancha.isNotEmpty ? cancha : 'Cancha');

  /// Etiqueta corta del estado para el cliente/boleador (texto del backend o
  /// un respaldo local por si un APK viejo habla con un backend nuevo).
  String get etiquetaEstado => estadoVisible.isNotEmpty
      ? estadoVisible
      : switch (estado) {
          'pendiente' => 'Esperando confirmación',
          'aceptada' => 'Confirmado ✅',
          'rechazada' => 'No disponible · devuelto',
          'vencida' => 'No respondió · devuelto',
          'cancelada' => 'Cancelado',
          'cancelada_boleador' => 'Canceló · devuelto',
          _ => estado,
        };

  /// ¿Coincide con esta reserva del cliente (por grupo o por id de la hora)?
  bool cubre(Reserva r) =>
      (r.grupoReservaId.isNotEmpty && r.grupoReservaId == reservaRef) ||
      r.id == reservaRef ||
      reservaIds.contains(r.id);
}

/// Mi perfil de boleador (lo que guardé) — espejo de `PerfilReq` del backend.
class PerfilBoleador {
  final String email;
  final String nombre;
  final String foto;
  final String celular;
  final String deporte;
  final String categoria;
  final double tarifa;
  final String moneda;
  final List<String> canchas;
  final List<int> dias;
  final String desde;
  final String hasta;
  final List<String> etiquetas;
  final bool activo;
  final int aceptadas;
  final int faltas;
  final String pausadoHasta;

  const PerfilBoleador({
    required this.email,
    required this.nombre,
    required this.foto,
    required this.celular,
    required this.deporte,
    required this.categoria,
    required this.tarifa,
    required this.moneda,
    required this.canchas,
    required this.dias,
    required this.desde,
    required this.hasta,
    required this.etiquetas,
    required this.activo,
    required this.aceptadas,
    required this.faltas,
    required this.pausadoHasta,
  });

  factory PerfilBoleador.fromJson(Map<String, dynamic> j) {
    final disp = j['disponibilidad'] is Map
        ? Map<String, dynamic>.from(j['disponibilidad'] as Map)
        : const <String, dynamic>{};
    final stats = j['stats'] is Map
        ? Map<String, dynamic>.from(j['stats'] as Map)
        : const <String, dynamic>{};
    return PerfilBoleador(
      email: (j['email'] ?? '').toString(),
      nombre: (j['nombre'] ?? '').toString(),
      foto: (j['foto'] ?? '').toString(),
      celular: (j['celular'] ?? '').toString(),
      deporte: (j['deporte'] ?? 'tenis').toString(),
      categoria: (j['categoria'] ?? '').toString(),
      tarifa: ((j['tarifa'] ?? 0) as num).toDouble(),
      moneda: (j['moneda'] ?? 'PEN').toString(),
      canchas: (j['canchas'] as List? ?? const []).map((e) => e.toString()).toList(),
      dias: (disp['dias'] as List? ?? const [1, 2, 3, 4, 5, 6, 7])
          .whereType<num>()
          .map((e) => e.toInt())
          .toList(),
      desde: (disp['desde'] ?? '07:00').toString(),
      hasta: (disp['hasta'] ?? '22:00').toString(),
      etiquetas: (j['etiquetas'] as List? ?? const []).map((e) => e.toString()).toList(),
      activo: j['activo'] == true,
      aceptadas: ((stats['aceptadas'] ?? 0) as num).toInt(),
      faltas: ((stats['faltas'] ?? 0) as num).toInt(),
      pausadoHasta: (j['pausado_hasta'] ?? '').toString(),
    );
  }

  Map<String, dynamic> toJson() => {
        'email': email,
        'nombre': nombre,
        'foto': foto,
        'celular': celular,
        'deporte': deporte,
        'categoria': categoria,
        'tarifa': tarifa,
        'moneda': moneda,
        'canchas': canchas,
        'disponibilidad': {'dias': dias, 'desde': desde, 'hasta': hasta},
        'etiquetas': etiquetas,
        'activo': activo,
        'stats': {'aceptadas': aceptadas, 'faltas': faltas},
        'pausado_hasta': pausadoHasta,
      };
}

/// Caché + outbox del módulo en el APK (device-first: pinta lo último que se
/// vio y refresca en silencio).
class Boleadores {
  static const _kPerfil = 'boleador_perfil';
  static const _kSolic = 'boleador_solicitudes';
  static const _kOutbox = 'boleador_solicitar_pend';
  static const _kCfg = 'boleador_config';

  /// Mi perfil (null = no registrado o aún no cargó). Notifica cambios para
  /// que Perfil pinte "Soy boleador" / badge sin reconstruir todo.
  static final ValueNotifier<PerfilBoleador?> perfil = ValueNotifier(null);

  /// Solicitudes PENDIENTES que me esperan como boleador (badge en Perfil).
  static final ValueNotifier<int> pendientes = ValueNotifier(0);

  static List<SolicitudBoleo> comoBoleador = const [];
  static List<SolicitudBoleo> comoCliente = const [];
  static final Map<String, BoleadorConfig> _cfg = {};
  static String _emailCache = '';

  static bool get soyBoleador => perfil.value != null;

  /// Carga desde disco (al instante) lo último conocido de ESTA cuenta.
  static Future<void> cargarCache(String email) async {
    final e = email.trim().toLowerCase();
    if (e.isEmpty) {
      limpiar();
      return;
    }
    try {
      final prefs = await SharedPreferences.getInstance();
      final pj = prefs.getString('$_kPerfil:$e');
      perfil.value = pj == null
          ? null
          : PerfilBoleador.fromJson(Map<String, dynamic>.from(jsonDecode(pj) as Map));
      final sj = prefs.getString('$_kSolic:$e');
      if (sj != null) _aplicarSolicitudes(Map<String, dynamic>.from(jsonDecode(sj) as Map));
      _emailCache = e;
    } catch (_) {}
  }

  static void limpiar() {
    perfil.value = null;
    pendientes.value = 0;
    comoBoleador = const [];
    comoCliente = const [];
    _emailCache = '';
  }

  /// Config del país: caché en memoria + disco, respaldo empaquetado.
  static Future<BoleadorConfig> config(PaisConfig pais) async {
    final c = _cfg[pais.iso];
    if (c != null) return c;
    try {
      final prefs = await SharedPreferences.getInstance();
      final j = prefs.getString('$_kCfg:${pais.iso}');
      if (j != null) {
        _cfg[pais.iso] = BoleadorConfig.fromJson(
            Map<String, dynamic>.from(jsonDecode(j) as Map), pais);
      }
    } catch (_) {}
    final r = await PagosService.boleadorConfig(pais.iso);
    if (r != null && r['categorias'] is List) {
      _cfg[pais.iso] = BoleadorConfig.fromJson(r, pais);
      try {
        final prefs = await SharedPreferences.getInstance();
        await prefs.setString('$_kCfg:${pais.iso}', jsonEncode(r));
      } catch (_) {}
    }
    return _cfg[pais.iso] ?? BoleadorConfig.local(pais);
  }

  /// Refresca mi perfil desde el backend (y lo deja en disco).
  static Future<PerfilBoleador?> refrescarPerfil(String email) async {
    final e = email.trim().toLowerCase();
    if (e.isEmpty) return null;
    final r = await PagosService.boleadorPerfil(e);
    if (r == null || r['ok'] != true) return perfil.value;
    final b = r['boleador'];
    perfil.value = b is Map
        ? PerfilBoleador.fromJson(Map<String, dynamic>.from(b))
        : null;
    try {
      final prefs = await SharedPreferences.getInstance();
      if (perfil.value == null) {
        await prefs.remove('$_kPerfil:$e');
      } else {
        await prefs.setString('$_kPerfil:$e', jsonEncode(perfil.value!.toJson()));
      }
    } catch (_) {}
    return perfil.value;
  }

  /// Refresca mis solicitudes (como boleador y como cliente).
  static Future<bool> refrescarSolicitudes(String email) async {
    final e = email.trim().toLowerCase();
    if (e.isEmpty) return false;
    await flushPendientes();
    final r = await PagosService.solicitudesBoleo(e);
    if (r == null || r['ok'] != true) return false;
    _aplicarSolicitudes(r);
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString('$_kSolic:$e', jsonEncode(r));
    } catch (_) {}
    return true;
  }

  static void _aplicarSolicitudes(Map<String, dynamic> r) {
    List<SolicitudBoleo> lista(dynamic raw) => (raw as List? ?? const [])
        .whereType<Map>()
        .map((m) => SolicitudBoleo.fromJson(Map<String, dynamic>.from(m)))
        .toList();
    comoBoleador = lista(r['como_boleador']);
    comoCliente = lista(r['como_cliente']);
    pendientes.value = comoBoleador.where((s) => s.pendiente).length;
  }

  /// Estado del boleador de UNA reserva mía (como cliente), si la tiene.
  static SolicitudBoleo? deReserva(Reserva r) {
    for (final s in comoCliente) {
      if (s.cubre(r)) return s;
    }
    return null;
  }

  /// Registra la solicitud tras pagar. Si el backend no responde, queda en el
  /// OUTBOX y se reintenta (al abrir Mis reservas, Perfil o al sincronizar):
  /// el cliente YA pagó al boleador, la solicitud no se puede perder.
  static Future<Map<String, dynamic>?> solicitar(Map<String, dynamic> body) async {
    final r = await PagosService.solicitarBoleador(body);
    if (r != null) return r;
    try {
      final prefs = await SharedPreferences.getInstance();
      final lista = _leerOutbox(prefs);
      if (!lista.any((x) => x['reserva_ref'] == body['reserva_ref'])) {
        lista.add(body);
        await prefs.setString(_kOutbox, jsonEncode(lista));
      }
    } catch (_) {}
    return null;
  }

  static List<Map<String, dynamic>> _leerOutbox(SharedPreferences prefs) {
    try {
      final raw = prefs.getString(_kOutbox);
      if (raw == null) return [];
      return (jsonDecode(raw) as List)
          .whereType<Map>()
          .map((m) => Map<String, dynamic>.from(m))
          .toList();
    } catch (_) {
      return [];
    }
  }

  /// Reintenta las solicitudes que no llegaron al backend (idempotente por
  /// reserva en el servidor).
  static Future<void> flushPendientes() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final lista = _leerOutbox(prefs);
      if (lista.isEmpty) return;
      final quedan = <Map<String, dynamic>>[];
      for (final b in lista) {
        final r = await PagosService.solicitarBoleador(b);
        if (r == null) quedan.add(b);
      }
      await prefs.setString(_kOutbox, jsonEncode(quedan));
    } catch (_) {}
  }

  /// Sincronización al iniciar sesión / arrancar: caché al instante, red en
  /// silencio.
  static Future<void> sincronizar(String email) async {
    final e = email.trim().toLowerCase();
    if (e.isEmpty) {
      limpiar();
      return;
    }
    if (_emailCache != e) await cargarCache(e);
    await refrescarPerfil(e);
    await refrescarSolicitudes(e);
  }
}
