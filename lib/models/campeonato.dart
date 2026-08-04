import 'package:google_maps_flutter/google_maps_flutter.dart';

import '../config/pais.dart';
import 'models.dart';

/// Formato de un campeonato de academia.
/// - [eliminacion]: llave/bracket (ideal tenis). El ganador avanza.
/// - [liga]: todos contra todos + tabla de posiciones (ideal fútbol).
/// - [tiempos]: por tiempos y series (natación). No hay partidos G/P: cada nadador
///   registra su TIEMPO por prueba y se rankea del más rápido al más lento.
enum FormatoTorneo { eliminacion, liga, tiempos }

extension FormatoTorneoX on FormatoTorneo {
  String get etiqueta => switch (this) {
        FormatoTorneo.eliminacion => 'Eliminación (llave)',
        FormatoTorneo.liga => 'Liga (tabla)',
        FormatoTorneo.tiempos => 'Por tiempos (natación)',
      };
  String get clave => name;
  static FormatoTorneo desde(String? s) => switch (s) {
        'liga' => FormatoTorneo.liga,
        'tiempos' => FormatoTorneo.tiempos,
        _ => FormatoTorneo.eliminacion,
      };
}

/// La MARCA (tiempo) de un participante en una prueba de natación. [centesimas]
/// es el tiempo total en centésimas de segundo (mm:ss.cc); 0 = sin registrar.
/// [serie]/[carril] ubican al nadador en la serie (heat) y carril; [dsq] = DSQ.
class MarcaNatacion {
  final String participanteId;
  final int centesimas;
  final int serie;
  final int carril;
  final bool dsq;

  const MarcaNatacion({
    required this.participanteId,
    this.centesimas = 0,
    this.serie = 0,
    this.carril = 0,
    this.dsq = false,
  });

  bool get registrada => centesimas > 0 || dsq;

  MarcaNatacion copyWith(
          {int? centesimas, int? serie, int? carril, bool? dsq}) =>
      MarcaNatacion(
        participanteId: participanteId,
        centesimas: centesimas ?? this.centesimas,
        serie: serie ?? this.serie,
        carril: carril ?? this.carril,
        dsq: dsq ?? this.dsq,
      );

  Map<String, dynamic> toJson() => {
        'participanteId': participanteId,
        'centesimas': centesimas,
        if (serie != 0) 'serie': serie,
        if (carril != 0) 'carril': carril,
        if (dsq) 'dsq': true,
      };

  factory MarcaNatacion.fromJson(Map<String, dynamic> j) => MarcaNatacion(
        participanteId: (j['participanteId'] ?? '') as String,
        centesimas: (j['centesimas'] as num?)?.toInt() ?? 0,
        serie: (j['serie'] as num?)?.toInt() ?? 0,
        carril: (j['carril'] as num?)?.toInt() ?? 0,
        dsq: (j['dsq'] ?? false) as bool,
      );
}

/// Una PRUEBA (evento) de natación: distancia + estilo, p. ej. "50m Libre".
/// Reúne las marcas de los participantes; se rankea por tiempo ascendente.
class PruebaNatacion {
  final String id;
  final String nombre;
  final List<MarcaNatacion> marcas;

  const PruebaNatacion(
      {required this.id, required this.nombre, this.marcas = const []});

  PruebaNatacion copyWith({String? nombre, List<MarcaNatacion>? marcas}) =>
      PruebaNatacion(
          id: id, nombre: nombre ?? this.nombre, marcas: marcas ?? this.marcas);

  Map<String, dynamic> toJson() => {
        'id': id,
        'nombre': nombre,
        'marcas': marcas.map((m) => m.toJson()).toList(),
      };

  factory PruebaNatacion.fromJson(Map<String, dynamic> j) => PruebaNatacion(
        id: j['id'] as String,
        nombre: (j['nombre'] ?? '') as String,
        marcas: (j['marcas'] as List?)
                ?.map((e) =>
                    MarcaNatacion.fromJson(Map<String, dynamic>.from(e as Map)))
                .toList() ??
            const [],
      );
}

/// Utilidades de natación: formatear/parsear tiempos y rankear una prueba.
class Natacion {
  /// "mm:ss.cc" desde centésimas. Ej.: 3785 → "0:37.85".
  static String fmt(int cc) {
    if (cc <= 0) return '—';
    final min = cc ~/ 6000;
    final seg = (cc % 6000) ~/ 100;
    final cen = cc % 100;
    return '$min:${seg.toString().padLeft(2, '0')}.${cen.toString().padLeft(2, '0')}';
  }

  /// Parsea "mm:ss.cc", "ss.cc" o "ss" (coma o punto) a centésimas; null si no vale.
  static int? parse(String s) {
    var t = s.trim().replaceAll(',', '.');
    if (t.isEmpty) return null;
    int min = 0;
    if (t.contains(':')) {
      final partes = t.split(':');
      if (partes.length != 2) return null;
      min = int.tryParse(partes[0].trim()) ?? -1;
      if (min < 0) return null;
      t = partes[1].trim();
    }
    final segCen = t.split('.');
    final seg = int.tryParse(segCen[0].trim()) ?? -1;
    if (seg < 0 || seg > 59) return null;
    var cen = 0;
    if (segCen.length > 1) {
      var c = segCen[1].trim();
      if (c.length == 1) c = '${c}0';
      if (c.length > 2) c = c.substring(0, 2);
      cen = int.tryParse(c) ?? 0;
    }
    return (min * 60 + seg) * 100 + cen;
  }

  /// Ranking de una prueba: las marcas REGISTRADAS con tiempo, por tiempo
  /// ascendente (más rápido primero); los DSQ al final; las sin registrar fuera.
  static List<MarcaNatacion> ranking(PruebaNatacion p) {
    final conTiempo =
        p.marcas.where((m) => !m.dsq && m.centesimas > 0).toList()
          ..sort((a, b) => a.centesimas.compareTo(b.centesimas));
    final dsq = p.marcas.where((m) => m.dsq).toList();
    return [...conTiempo, ...dsq];
  }

  /// Distancias y estilos comunes (para el selector de prueba).
  static const distancias = [25, 50, 100, 200, 400];
  static const estilos = ['Libre', 'Espalda', 'Pecho', 'Mariposa', 'Combinado'];
}

/// Un INTEGRANTE del plantel de un equipo (fútbol). [email] no vacío = jugador
/// con cuenta (verificado, se auto-inscribió con el código); vacío = lo agregó
/// el capitán a mano (invitado/menor).
class Integrante {
  final String id;
  final String nombre;
  final String email;
  final String? fotoUrl;
  final int? edad;
  const Integrante({
    required this.id,
    required this.nombre,
    this.email = '',
    this.fotoUrl,
    this.edad,
  });

  bool get verificado => email.isNotEmpty;

  Map<String, dynamic> toJson() => {
        'id': id,
        'nombre': nombre,
        'email': email,
        if (fotoUrl != null) 'fotoUrl': fotoUrl,
        if (edad != null) 'edad': edad,
      };

  factory Integrante.fromJson(Map<String, dynamic> j) => Integrante(
        id: j['id'] as String,
        nombre: (j['nombre'] ?? '') as String,
        email: (j['email'] ?? '') as String,
        fotoUrl: j['fotoUrl'] as String?,
        edad: (j['edad'] as num?)?.toInt(),
      );
}

/// Un participante del campeonato: jugador (tenis individual), pareja ("A / B")
/// o equipo (fútbol). Modelo genérico para cubrir ambos deportes.
///
/// [email] no vacío = **participante-app**: se inscribió desde la app con su
/// cuenta. Vacío = lo agregó el profe a mano. Menores: [apoderadoNombre] no
/// vacío ⇒ el participante es un niño bajo un apoderado (la cuenta es del padre).
class Participante {
  final String id;
  final String nombre;
  final String contacto; // WhatsApp opcional (para avisos)
  final String email; // cuenta-app que lo inscribió ('' si manual)
  final String? fotoUrl;
  final String apoderadoNombre; // '' si es adulto
  final int? edad;
  // ── Equipo (fútbol): capitán + código + plantel ──────────────────────────
  /// Correo del CAPITÁN del equipo ('' si no es equipo). El capitán administra
  /// el plantel y comparte el código.
  final String capitanEmail;
  /// Código para que los jugadores se AUTO-INSCRIBAN al equipo ('' si no aplica).
  final String codigo;
  /// Plantel del equipo (integrantes). Vacío para individuales/parejas.
  final List<Integrante> roster;

  const Participante({
    required this.id,
    required this.nombre,
    this.contacto = '',
    this.email = '',
    this.fotoUrl,
    this.apoderadoNombre = '',
    this.edad,
    this.capitanEmail = '',
    this.codigo = '',
    this.roster = const [],
  });

  bool get esApp => email.isNotEmpty;
  bool get esMenor => apoderadoNombre.isNotEmpty;
  bool get esEquipo => capitanEmail.isNotEmpty || codigo.isNotEmpty;

  Participante copyWith({
    String? nombre,
    List<Integrante>? roster,
    String? codigo,
  }) =>
      Participante(
        id: id,
        nombre: nombre ?? this.nombre,
        contacto: contacto,
        email: email,
        fotoUrl: fotoUrl,
        apoderadoNombre: apoderadoNombre,
        edad: edad,
        capitanEmail: capitanEmail,
        codigo: codigo ?? this.codigo,
        roster: roster ?? this.roster,
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'nombre': nombre,
        'contacto': contacto,
        'email': email,
        if (fotoUrl != null) 'fotoUrl': fotoUrl,
        'apoderadoNombre': apoderadoNombre,
        if (edad != null) 'edad': edad,
        if (capitanEmail.isNotEmpty) 'capitanEmail': capitanEmail,
        if (codigo.isNotEmpty) 'codigo': codigo,
        if (roster.isNotEmpty)
          'roster': roster.map((r) => r.toJson()).toList(),
      };

  factory Participante.fromJson(Map<String, dynamic> j) => Participante(
        id: j['id'] as String,
        nombre: (j['nombre'] ?? '') as String,
        contacto: (j['contacto'] ?? '') as String,
        email: (j['email'] ?? '') as String,
        fotoUrl: j['fotoUrl'] as String?,
        apoderadoNombre: (j['apoderadoNombre'] ?? '') as String,
        edad: (j['edad'] as num?)?.toInt(),
        capitanEmail: (j['capitanEmail'] ?? '') as String,
        codigo: (j['codigo'] ?? '') as String,
        roster: (j['roster'] as List?)
                ?.map((e) =>
                    Integrante.fromJson(Map<String, dynamic>.from(e as Map)))
                .toList() ??
            const [],
      );
}

/// Un partido del fixture. En [FormatoTorneo.eliminacion] [ronda] es la ronda de
/// la llave (0 = primera); en [FormatoTorneo.liga] es la jornada. [idx] ordena
/// los partidos dentro de la ronda/jornada. [aId]/[bId] son ids de participante
/// (null = por definir / bye).
class PartidoTorneo {
  final String id;
  final int ronda;
  final int idx;
  final String? aId;
  final String? bId;
  final int? marcadorA;
  final int? marcadorB;

  const PartidoTorneo({
    required this.id,
    required this.ronda,
    required this.idx,
    this.aId,
    this.bId,
    this.marcadorA,
    this.marcadorB,
  });

  bool get jugado => marcadorA != null && marcadorB != null;

  /// Ganador del partido (id) o null si no está definido. En ronda 0 un lado
  /// nulo = bye (avanza el presente).
  String? get ganadorId {
    if (jugado) {
      if (marcadorA! > marcadorB!) return aId;
      if (marcadorB! > marcadorA!) return bId;
      return null; // empate (en eliminación se resuelve aparte)
    }
    if (ronda == 0 && ((aId == null) != (bId == null))) return aId ?? bId;
    return null;
  }

  PartidoTorneo conMarcador(int a, int b) => PartidoTorneo(
        id: id, ronda: ronda, idx: idx, aId: aId, bId: bId,
        marcadorA: a, marcadorB: b,
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'ronda': ronda,
        'idx': idx,
        if (aId != null) 'aId': aId,
        if (bId != null) 'bId': bId,
        if (marcadorA != null) 'marcadorA': marcadorA,
        if (marcadorB != null) 'marcadorB': marcadorB,
      };

  factory PartidoTorneo.fromJson(Map<String, dynamic> j) => PartidoTorneo(
        id: j['id'] as String,
        ronda: (j['ronda'] as num?)?.toInt() ?? 0,
        idx: (j['idx'] as num?)?.toInt() ?? 0,
        aId: j['aId'] as String?,
        bId: j['bId'] as String?,
        marcadorA: (j['marcadorA'] as num?)?.toInt(),
        marcadorB: (j['marcadorB'] as num?)?.toInt(),
      );
}

/// Fila de la tabla de posiciones (formato liga).
class FilaTabla {
  final String participanteId;
  final String nombre;
  int pj, g, e, p, gf, gc;
  FilaTabla(this.participanteId, this.nombre,
      {this.pj = 0, this.g = 0, this.e = 0, this.p = 0, this.gf = 0, this.gc = 0});
  int get dif => gf - gc;
  int get pts => g * 3 + e;
}

/// Un campeonato organizado por una academia.
class Campeonato {
  final String id;
  final String academiaId;
  final String dueno; // correo del profe organizador
  /// Código CORTO para invitar (6 chars). Se dicta/comparte para unirse desde
  /// "Unirme a un campeonato". Vacío en campeonatos viejos → se cae al id.
  final String codigo;
  final String nombre;
  final Deporte deporte;
  final FormatoTorneo formato;
  final String categoria; // texto libre: "Sub-10", "Libre", "Damas B"…
  final String sede;
  final LatLng? sedeUbicacion; // coordenadas de la sede (para mapa/compartir)
  final String fechas; // texto legible: "12–13 jul 2026"
  final double costoInscripcion; // S/ (0 = gratis)
  final bool inscripcionAbierta; // ¿los jugadores pueden inscribirse solos?
  final List<Participante> participantes;
  final List<PartidoTorneo> partidos; // fixture generado (vacío = aún no)
  final List<PruebaNatacion> pruebas; // solo formato 'tiempos' (natación)
  final bool cerrado;
  /// Moneda del costo de inscripción, congelada al crear ('' = 'S/', Perú).
  final String moneda;
  // ── Cronograma (Fase 1) ──────────────────────────────────────────────────
  /// Cierre de inscripciones: al llegar, se sortea el fixture. null = sin plazo.
  final DateTime? inscripcionHasta;
  /// Inicio del campeonato (primera fecha de juego). null = sin definir.
  final DateTime? inicio;
  /// Relámpago = todo en un día; false = por varias fechas.
  final bool relampago;
  // ── Verificación por DNI (opcional del organizador) ──────────────────────
  /// Exige DNI para inscribirse: valida identidad y calcula la EDAD real (evita
  /// que alguien se haga pasar por otra edad en categorías Sub-N).
  final bool exigeDni;
  /// Rango de edad de la categoría (para validar con la edad del DNI). null =
  /// sin tope. Ej.: Sub-30 → edadMax=30; Máster 35+ → edadMin=35.
  final int? edadMin;
  final int? edadMax;

  const Campeonato({
    required this.id,
    required this.academiaId,
    required this.dueno,
    this.codigo = '',
    required this.nombre,
    required this.deporte,
    this.formato = FormatoTorneo.eliminacion,
    this.categoria = '',
    this.sede = '',
    this.sedeUbicacion,
    this.fechas = '',
    this.costoInscripcion = 0,
    this.inscripcionAbierta = true,
    this.participantes = const [],
    this.partidos = const [],
    this.pruebas = const [],
    this.cerrado = false,
    this.moneda = '',
    this.inscripcionHasta,
    this.inicio,
    this.relampago = false,
    this.exigeDni = false,
    this.edadMin,
    this.edadMax,
  });

  /// ¿Las inscripciones ya cerraron por fecha? (para auto-sorteo / bloqueo).
  bool get inscripcionVencida =>
      inscripcionHasta != null && DateTime.now().isAfter(inscripcionHasta!);

  /// Símbolo de moneda del campeonato. La UBICACIÓN de la sede es la fuente de
  /// verdad (un torneo en Lima cobra en S/, aunque el profe abra la app desde
  /// Bolivia): se deriva del país donde cae la sede. Auto-corrige campeonatos
  /// que quedaron con la moneda del dispositivo. Sin sede ubicada, cae a la
  /// moneda congelada al crear y, por último, a 'S/'.
  String get monedaSimbolo {
    final u = sedeUbicacion;
    if (u != null) return monedaDeCoordenadas(u.latitude, u.longitude);
    return moneda.isNotEmpty ? moneda : 'S/';
  }

  bool get fixtureGenerado => partidos.isNotEmpty;
  bool get esTiempos => formato == FormatoTorneo.tiempos;

  /// Código para invitar a inscribirse: el corto si existe, si no el id (para
  /// campeonatos creados antes de que existiera el código).
  String get codigoInvitacion => codigo.isNotEmpty ? codigo : id;

  /// ¿Este deporte tiene circuito/ranking? Solo los de raqueta (tenis, pádel,
  /// pickleball) hoy. Fútbol/natación NO → no se ofrece "ver/sumar al ranking".
  bool get esDeporteCircuito => deportesCircuito.contains(deporte);

  Campeonato copyWith({
    String? nombre,
    FormatoTorneo? formato,
    String? categoria,
    String? sede,
    LatLng? sedeUbicacion,
    String? fechas,
    double? costoInscripcion,
    bool? inscripcionAbierta,
    List<Participante>? participantes,
    List<PartidoTorneo>? partidos,
    List<PruebaNatacion>? pruebas,
    bool? cerrado,
    String? moneda,
    DateTime? inscripcionHasta,
    DateTime? inicio,
    bool? relampago,
    bool? exigeDni,
    int? edadMin,
    int? edadMax,
  }) =>
      Campeonato(
        id: id,
        academiaId: academiaId,
        dueno: dueno,
        codigo: codigo,
        nombre: nombre ?? this.nombre,
        deporte: deporte,
        formato: formato ?? this.formato,
        categoria: categoria ?? this.categoria,
        sede: sede ?? this.sede,
        sedeUbicacion: sedeUbicacion ?? this.sedeUbicacion,
        fechas: fechas ?? this.fechas,
        costoInscripcion: costoInscripcion ?? this.costoInscripcion,
        inscripcionAbierta: inscripcionAbierta ?? this.inscripcionAbierta,
        participantes: participantes ?? this.participantes,
        partidos: partidos ?? this.partidos,
        pruebas: pruebas ?? this.pruebas,
        cerrado: cerrado ?? this.cerrado,
        moneda: moneda ?? this.moneda,
        inscripcionHasta: inscripcionHasta ?? this.inscripcionHasta,
        inicio: inicio ?? this.inicio,
        relampago: relampago ?? this.relampago,
        exigeDni: exigeDni ?? this.exigeDni,
        edadMin: edadMin ?? this.edadMin,
        edadMax: edadMax ?? this.edadMax,
      );

  Participante? participante(String? pid) {
    if (pid == null) return null;
    for (final p in participantes) {
      if (p.id == pid) return p;
    }
    return null;
  }

  Map<String, dynamic> toJson() => {
        'id': id,
        'academiaId': academiaId,
        'dueno': dueno,
        if (codigo.isNotEmpty) 'codigo': codigo,
        'nombre': nombre,
        'deporte': deporte.name,
        'formato': formato.clave,
        'categoria': categoria,
        'sede': sede,
        if (sedeUbicacion != null) 'sedeLat': sedeUbicacion!.latitude,
        if (sedeUbicacion != null) 'sedeLng': sedeUbicacion!.longitude,
        'fechas': fechas,
        'costoInscripcion': costoInscripcion,
        'inscripcionAbierta': inscripcionAbierta,
        'participantes': participantes.map((p) => p.toJson()).toList(),
        'partidos': partidos.map((p) => p.toJson()).toList(),
        if (pruebas.isNotEmpty)
          'pruebas': pruebas.map((p) => p.toJson()).toList(),
        'cerrado': cerrado,
        'moneda': moneda,
        if (inscripcionHasta != null)
          'inscripcionHasta': inscripcionHasta!.toIso8601String(),
        if (inicio != null) 'inicio': inicio!.toIso8601String(),
        'relampago': relampago,
        'exigeDni': exigeDni,
        if (edadMin != null) 'edadMin': edadMin,
        if (edadMax != null) 'edadMax': edadMax,
      };

  factory Campeonato.fromJson(Map<String, dynamic> j) => Campeonato(
        id: j['id'] as String,
        academiaId: (j['academiaId'] ?? '') as String,
        dueno: (j['dueno'] ?? '') as String,
        codigo: (j['codigo'] ?? '') as String,
        nombre: (j['nombre'] ?? '') as String,
        deporte: Deporte.values.firstWhere(
            (d) => d.name == j['deporte'], orElse: () => Deporte.tenis),
        formato: FormatoTorneoX.desde(j['formato'] as String?),
        categoria: (j['categoria'] ?? '') as String,
        sede: (j['sede'] ?? '') as String,
        sedeUbicacion: (j['sedeLat'] != null && j['sedeLng'] != null)
            ? LatLng((j['sedeLat'] as num).toDouble(),
                (j['sedeLng'] as num).toDouble())
            : null,
        fechas: (j['fechas'] ?? '') as String,
        costoInscripcion: ((j['costoInscripcion'] ?? 0) as num).toDouble(),
        inscripcionAbierta: (j['inscripcionAbierta'] ?? true) as bool,
        participantes: (j['participantes'] as List?)
                ?.map((e) => Participante.fromJson(Map<String, dynamic>.from(e as Map)))
                .toList() ??
            const [],
        partidos: (j['partidos'] as List?)
                ?.map((e) => PartidoTorneo.fromJson(Map<String, dynamic>.from(e as Map)))
                .toList() ??
            const [],
        pruebas: (j['pruebas'] as List?)
                ?.map((e) =>
                    PruebaNatacion.fromJson(Map<String, dynamic>.from(e as Map)))
                .toList() ??
            const [],
        cerrado: (j['cerrado'] ?? false) as bool,
        moneda: (j['moneda'] ?? '') as String,
        inscripcionHasta: j['inscripcionHasta'] != null
            ? DateTime.tryParse(j['inscripcionHasta'] as String)
            : null,
        inicio: j['inicio'] != null
            ? DateTime.tryParse(j['inicio'] as String)
            : null,
        relampago: (j['relampago'] ?? false) as bool,
        exigeDni: (j['exigeDni'] ?? false) as bool,
        edadMin: (j['edadMin'] as num?)?.toInt(),
        edadMax: (j['edadMax'] as num?)?.toInt(),
      );
}

/// Lógica de fixture: generar llave/liga, propagar ganadores y calcular tabla.
/// Sin estado; opera sobre listas. (Se mantiene fuera del modelo para tenerlo
/// testeable y aislado.)
class TorneoFixture {
  /// Genera el fixture según el formato. Requiere ≥ 2 participantes.
  static List<PartidoTorneo> generar(
      FormatoTorneo formato, List<Participante> ps) {
    if (ps.length < 2) return const [];
    return formato == FormatoTorneo.liga
        ? _generarLiga(ps)
        : recomputarLlave(_esqueletoEliminacion(ps));
  }

  // ── Eliminación ──────────────────────────────────────────────────────────
  static List<PartidoTorneo> _esqueletoEliminacion(List<Participante> ps) {
    final n = ps.length;
    var size = 1;
    while (size < n) {
      size *= 2; // próxima potencia de 2
    }
    // Slots de la ronda 0 (los que exceden son byes = null).
    final slots = <String?>[for (var i = 0; i < size; i++) i < n ? ps[i].id : null];
    final todos = <PartidoTorneo>[];
    // Ronda 0.
    for (var i = 0; i < size ~/ 2; i++) {
      todos.add(PartidoTorneo(
          id: 'r0_$i', ronda: 0, idx: i, aId: slots[2 * i], bId: slots[2 * i + 1]));
    }
    // Rondas siguientes (vacías; se llenan con recomputarLlave).
    var matches = size ~/ 2;
    var r = 1;
    while (matches > 1) {
      matches ~/= 2;
      for (var i = 0; i < matches; i++) {
        todos.add(PartidoTorneo(id: 'r${r}_$i', ronda: r, idx: i));
      }
      r++;
    }
    return todos;
  }

  /// Recalcula los cruces de las rondas ≥ 1 según los ganadores de la ronda
  /// previa (propaga byes y resultados). Si el cruce cambió, resetea su marcador.
  static List<PartidoTorneo> recomputarLlave(List<PartidoTorneo> partidos) {
    final porRonda = <int, List<PartidoTorneo>>{};
    for (final p in partidos) {
      (porRonda[p.ronda] ??= []).add(p);
    }
    for (final l in porRonda.values) {
      l.sort((a, b) => a.idx.compareTo(b.idx));
    }
    final maxR =
        porRonda.keys.isEmpty ? 0 : porRonda.keys.reduce((a, b) => a > b ? a : b);
    for (var r = 1; r <= maxR; r++) {
      final prev = porRonda[r - 1];
      final cur = porRonda[r];
      if (prev == null || cur == null) continue;
      for (var i = 0; i < cur.length; i++) {
        final a = (2 * i < prev.length) ? prev[2 * i].ganadorId : null;
        final b = (2 * i + 1 < prev.length) ? prev[2 * i + 1].ganadorId : null;
        final m = cur[i];
        final mismos = m.aId == a && m.bId == b;
        cur[i] = PartidoTorneo(
          id: m.id, ronda: r, idx: i, aId: a, bId: b,
          marcadorA: mismos ? m.marcadorA : null,
          marcadorB: mismos ? m.marcadorB : null,
        );
      }
    }
    return [for (var r = 0; r <= maxR; r++) ...?porRonda[r]];
  }

  // ── Liga (round-robin, método del círculo) ────────────────────────────────
  static List<PartidoTorneo> _generarLiga(List<Participante> ps) {
    final list = <String?>[for (final p in ps) p.id];
    if (list.length.isOdd) list.add(null); // descansa
    final n = list.length;
    final jornadas = n - 1;
    final mitad = n ~/ 2;
    final partidos = <PartidoTorneo>[];
    var arr = List<String?>.from(list);
    for (var j = 0; j < jornadas; j++) {
      var idx = 0;
      for (var i = 0; i < mitad; i++) {
        final a = arr[i];
        final b = arr[n - 1 - i];
        if (a != null && b != null) {
          partidos.add(
              PartidoTorneo(id: 'j${j}_$idx', ronda: j, idx: idx, aId: a, bId: b));
          idx++;
        }
      }
      // Rota: fija el primero, rota el resto en sentido horario.
      final fijo = arr[0];
      final resto = arr.sublist(1);
      resto.insert(0, resto.removeLast());
      arr = [fijo, ...resto];
    }
    return partidos;
  }

  /// Tabla de posiciones (formato liga) ordenada por Pts, dif, GF.
  static List<FilaTabla> tabla(Campeonato c) {
    final filas = <String, FilaTabla>{
      for (final p in c.participantes)
        p.id: FilaTabla(p.id, p.nombre),
    };
    for (final m in c.partidos) {
      if (!m.jugado || m.aId == null || m.bId == null) continue;
      final fa = filas[m.aId];
      final fb = filas[m.bId];
      if (fa == null || fb == null) continue;
      fa.pj++;
      fb.pj++;
      fa.gf += m.marcadorA!;
      fa.gc += m.marcadorB!;
      fb.gf += m.marcadorB!;
      fb.gc += m.marcadorA!;
      if (m.marcadorA! > m.marcadorB!) {
        fa.g++;
        fb.p++;
      } else if (m.marcadorB! > m.marcadorA!) {
        fb.g++;
        fa.p++;
      } else {
        fa.e++;
        fb.e++;
      }
    }
    final lista = filas.values.toList();
    lista.sort((a, b) {
      if (b.pts != a.pts) return b.pts - a.pts;
      if (b.dif != a.dif) return b.dif - a.dif;
      return b.gf - a.gf;
    });
    return lista;
  }
}
