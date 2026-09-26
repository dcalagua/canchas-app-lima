import 'package:google_maps_flutter/google_maps_flutter.dart';

import '../config/pais.dart';
import 'models.dart';

/// Formato de un campeonato de academia.
/// - [eliminacion]: llave/bracket (ideal tenis). El ganador avanza.
/// - [liga]: todos contra todos + tabla de posiciones (ideal fútbol).
/// - [grupos]: fase de GRUPOS (todos contra todos dentro del grupo, así cada
///   equipo juega al menos [Campeonato.minPartidos] partidos) y luego LLAVE con
///   los 2 primeros de cada grupo. Pedido del director (sep-2026): "quiero
///   asegurar que al menos cada equipo juegue 2 partidos a más".
/// - [tiempos]: por tiempos y series (natación). No hay partidos G/P: cada nadador
///   registra su TIEMPO por prueba y se rankea del más rápido al más lento.
enum FormatoTorneo { eliminacion, liga, grupos, tiempos }

extension FormatoTorneoX on FormatoTorneo {
  String get etiqueta => switch (this) {
        FormatoTorneo.eliminacion => 'Eliminación (llave)',
        FormatoTorneo.liga => 'Liga (tabla)',
        FormatoTorneo.grupos => 'Grupos + eliminatoria',
        FormatoTorneo.tiempos => 'Por tiempos (natación)',
      };
  String get clave => name;
  static FormatoTorneo desde(String? s) => switch (s) {
        'liga' => FormatoTorneo.liga,
        'grupos' => FormatoTorneo.grupos,
        'tiempos' => FormatoTorneo.tiempos,
        _ => FormatoTorneo.eliminacion,
      };
}

/// Opciones de "cada equipo juega al menos N partidos" (formato grupos).
const kMinPartidosOpciones = [2, 3];

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
  /// Lo que este jugador PUSO en el pozo del equipo (céntimos). Espejo de
  /// `pagos/pozos.py` (la fuente de verdad del dinero es el backend); 0 = aún
  /// no aportó o el torneo es gratis.
  final int aporteCentimos;
  const Integrante({
    required this.id,
    required this.nombre,
    this.email = '',
    this.fotoUrl,
    this.edad,
    this.aporteCentimos = 0,
  });

  bool get verificado => email.isNotEmpty;

  Integrante copyWith({int? aporteCentimos}) => Integrante(
        id: id,
        nombre: nombre,
        email: email,
        fotoUrl: fotoUrl,
        edad: edad,
        aporteCentimos: aporteCentimos ?? this.aporteCentimos,
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'nombre': nombre,
        'email': email,
        if (fotoUrl != null) 'fotoUrl': fotoUrl,
        if (edad != null) 'edad': edad,
        if (aporteCentimos > 0) 'aporteCentimos': aporteCentimos,
      };

  factory Integrante.fromJson(Map<String, dynamic> j) => Integrante(
        id: j['id'] as String,
        nombre: (j['nombre'] ?? '') as String,
        email: (j['email'] ?? '') as String,
        fotoUrl: j['fotoUrl'] as String?,
        edad: (j['edad'] as num?)?.toInt(),
        aporteCentimos: (j['aporteCentimos'] as num?)?.toInt() ?? 0,
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
    String? fotoUrl,
    List<Integrante>? roster,
    String? codigo,
  }) =>
      Participante(
        id: id,
        nombre: nombre ?? this.nombre,
        contacto: contacto,
        email: email,
        fotoUrl: fotoUrl ?? this.fotoUrl,
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
  /// Formato grupos: 'grupo' (fase de grupos) o 'llave' (fase final). null en
  /// los demás formatos. Se conserva TAL CUAL al guardar (la web lo lee igual).
  final String? fase;
  /// Formato grupos: letra del grupo ('A', 'B'…) de los partidos de fase de grupos.
  final String? grupo;

  const PartidoTorneo({
    required this.id,
    required this.ronda,
    required this.idx,
    this.aId,
    this.bId,
    this.marcadorA,
    this.marcadorB,
    this.fase,
    this.grupo,
  });

  bool get esGrupo => fase == 'grupo';
  bool get esLlave => fase == 'llave';

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
        marcadorA: a, marcadorB: b, fase: fase, grupo: grupo,
      );

  /// Copia con otros lados (y marcador opcional), conservando fase/grupo.
  PartidoTorneo conLados(String? a, String? b, {int? marcadorA, int? marcadorB}) =>
      PartidoTorneo(
        id: id, ronda: ronda, idx: idx, aId: a, bId: b,
        marcadorA: marcadorA, marcadorB: marcadorB, fase: fase, grupo: grupo,
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'ronda': ronda,
        'idx': idx,
        if (aId != null) 'aId': aId,
        if (bId != null) 'bId': bId,
        if (marcadorA != null) 'marcadorA': marcadorA,
        if (marcadorB != null) 'marcadorB': marcadorB,
        if (fase != null) 'fase': fase,
        if (grupo != null) 'grupo': grupo,
      };

  factory PartidoTorneo.fromJson(Map<String, dynamic> j) => PartidoTorneo(
        id: j['id'] as String,
        ronda: (j['ronda'] as num?)?.toInt() ?? 0,
        idx: (j['idx'] as num?)?.toInt() ?? 0,
        aId: j['aId'] as String?,
        bId: j['bId'] as String?,
        marcadorA: (j['marcadorA'] as num?)?.toInt(),
        marcadorB: (j['marcadorB'] as num?)?.toInt(),
        fase: j['fase'] as String?,
        grupo: j['grupo'] as String?,
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
  /// Logo del campeonato (URL pública en Supabase Storage). null = sin logo →
  /// se muestra el ícono del deporte.
  final String? logoUrl;
  /// Fútbol (por equipos): MÍNIMO de jugadores para que un equipo cuente como
  /// "completo". 0 = sin cupo definido (solo se muestra el conteo, sin marcar
  /// completo/incompleto). No hay tope máximo (pueden sumar suplentes).
  final int minJugadoresEquipo;
  /// Fútbol: TOPE de plantel (titulares + suplentes). 0 = sin tope. Con costo
  /// de inscripción, la cuota del equipo se reparte entre este número (ver
  /// [cuotaJugadorCentimos]). Decisión del director (26-sep-2026): "la
  /// vaquita del equipo".
  final int maxJugadoresEquipo;
  /// Formato grupos: cada equipo juega AL MENOS este número de partidos en la
  /// fase de grupos (2 o 3). Decide el tamaño mínimo de grupo (minPartidos+1).
  final int minPartidos;
  /// GRUPOS ARMADOS A MANO por el organizador (pedido del director,
  /// 26-sep-2026, desde el campo): lista de grupos (A, B, C…) con los ids de
  /// sus participantes. Vacío = el sorteo automático (`armarGrupos`). Si
  /// dejan de calzar con los inscritos (entró o salió alguien) se ignoran.
  /// JSON `gruposManuales: [[id,…],[…]]`. ESPEJO en `campeonatos_logica`.
  final List<List<String>> gruposManuales;
  /// PREMIOS del torneo, uno por línea ("Trofeos para campeones", "Tarros de
  /// pelotas"…). Se lucen en la publicidad de compartir y en la página web.
  final String premios;
  /// AUSPICIADOR oficial (ej. "JORDI MEAT BOUTIQUE"). Espacio de marca en la
  /// publicidad y la página del torneo.
  final String auspiciador;
  /// LOGOS de los auspiciadores (URLs en Storage). Un campeonato puede tener
  /// varias empresas auspiciando: sus logos salen en el AFICHE y en la página.
  final List<String> auspiciadoresLogos;
  /// FOTOS del torneo (galería "así se vivió", URLs en Storage): las sube el
  /// organizador y las ve todo el mundo en la ficha y en la página pública —
  /// clave para campeonatos PASADOS (memoria del evento).
  final List<String> fotos;
  /// FONDO PROPIO del afiche (URL en Storage): si el organizador sube su
  /// foto, el afiche la usa en lugar del arte IA. Vacío = arte automático.
  final String aficheFondoUrl;
  /// Variante del ARTE IA del afiche: "generar otro arte" la incrementa para
  /// que el fondo IA cambie (sin repetir el mismo).
  final int aficheVariante;
  /// TEMÁTICA del arte IA del afiche: '' = nocturna de marca; claves curadas
  /// (claro/cancha/amanecer/celebracion) o la DESCRIPCIÓN LIBRE del
  /// organizador ("Mi idea": p. ej. "fondo claro, cancha de arcilla").
  final String aficheTema;

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
    this.logoUrl,
    this.minJugadoresEquipo = 0,
    this.maxJugadoresEquipo = 0,
    this.minPartidos = 2,
    this.gruposManuales = const [],
    this.premios = '',
    this.auspiciador = '',
    this.auspiciadoresLogos = const [],
    this.fotos = const [],
    this.aficheFondoUrl = '',
    this.aficheVariante = 0,
    this.aficheTema = '',
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

  /// ¿Un jugador aún puede UNIRSE al plantel de un equipo (fútbol)? A
  /// diferencia de crear equipos o de la inscripción individual, NI el
  /// fixture generado NI la fecha de "cierre de inscripciones" cierran el
  /// plantel: ese cierre sirve para sortear (cuántos equipos hay); los
  /// suplentes entran (y ponen su parte del pozo) hasta que el torneo termine
  /// o el organizador lo cierre (pedido del director, 26-sep-2026: "me quiero
  /// inscribir al Kinder-01" con el torneo ya "En juego" y el cierre vencido).
  /// ESPEJO de `campeonatos_logica.plantel_abierto`.
  bool get plantelAbierto =>
      deporte == Deporte.futbol &&
      !cerrado &&
      inscripcionAbierta &&
      !terminado;

  /// Por qué NO se puede unir al plantel ('' = sí se puede). Para que el
  /// modal del equipo lo diga en vez de esconder el botón en silencio.
  String motivoPlantelCerrado() {
    if (deporte != Deporte.futbol) return 'Este torneo no es por equipos.';
    if (cerrado || terminado) return 'Este campeonato ya terminó.';
    if (!inscripcionAbierta) {
      return 'El organizador cerró las inscripciones.';
    }
    return '';
  }

  /// Participante por id (o null).
  Participante? participanteDe(String? id) {
    if (id == null) return null;
    for (final p in participantes) {
      if (p.id == id) return p;
    }
    return null;
  }

  /// ¿El torneo ya TERMINÓ? Cerrado por el organizador, o fixture completo:
  /// en eliminación cuando la FINAL tiene ganador; en liga cuando todos los
  /// partidos tienen marcador.
  bool get terminado {
    if (cerrado) return true;
    if (!fixtureGenerado) return false;
    if (formato == FormatoTorneo.eliminacion || formato == FormatoTorneo.grupos) {
      final llave = partidosLlave;
      if (llave.isEmpty) return false;
      var maxR = 0;
      for (final p in llave) {
        if (p.ronda > maxR) maxR = p.ronda;
      }
      final fin = llave.where((p) => p.ronda == maxR).toList();
      return fin.length == 1 && fin.first.ganadorId != null;
    }
    return partidos
        .every((m) => m.jugado || m.aId == null || m.bId == null);
  }

  bool get esGrupos => formato == FormatoTorneo.grupos;

  /// Partidos de la FASE DE GRUPOS (formato grupos); vacío en otros formatos.
  List<PartidoTorneo> get partidosGrupo =>
      [for (final m in partidos) if (m.esGrupo) m];

  /// La LLAVE: en grupos solo los partidos de fase final; en eliminación, todos.
  List<PartidoTorneo> get partidosLlave => esGrupos
      ? [for (final m in partidos) if (m.esLlave) m]
      : partidos;

  /// Letras de los grupos existentes, en orden ('A', 'B'…).
  List<String> get grupos {
    final set = <String>{for (final m in partidosGrupo) if (m.grupo != null) m.grupo!};
    return set.toList()..sort();
  }

  /// ¿Terminó la fase de grupos (todos sus partidos con marcador)?
  bool get gruposCompletos =>
      partidosGrupo.isNotEmpty && partidosGrupo.every((m) => m.jugado);

  /// CAMPEÓN del torneo (id de participante), o null si aún no terminó.
  /// Liga → 1º de la tabla; eliminación → ganador de la final.
  String? get campeonId {
    if (!fixtureGenerado || !terminado) return null;
    if (formato == FormatoTorneo.liga) {
      final tabla = TorneoFixture.tabla(this);
      return tabla.isEmpty ? null : tabla.first.participanteId;
    }
    final llave = partidosLlave;
    var maxR = 0;
    for (final p in llave) {
      if (p.ronda > maxR) maxR = p.ronda;
    }
    final fin = llave.where((p) => p.ronda == maxR).toList();
    return fin.length == 1 ? fin.first.ganadorId : null;
  }

  /// SUBCAMPEÓN (id), o null. Liga → 2º de la tabla; eliminación → el que
  /// perdió la final.
  String? get subcampeonId {
    if (!fixtureGenerado || !terminado) return null;
    if (formato == FormatoTorneo.liga) {
      final tabla = TorneoFixture.tabla(this);
      return tabla.length > 1 ? tabla[1].participanteId : null;
    }
    final llave = partidosLlave;
    var maxR = 0;
    for (final p in llave) {
      if (p.ronda > maxR) maxR = p.ronda;
    }
    final fin = llave.where((p) => p.ronda == maxR).toList();
    if (fin.length != 1) return null;
    final f = fin.first;
    final g = f.ganadorId;
    if (g == null) return null;
    return g == f.aId ? f.bId : f.aId;
  }
  bool get esTiempos => formato == FormatoTorneo.tiempos;

  /// Código para invitar a inscribirse: el corto si existe, si no el id (para
  /// campeonatos creados antes de que existiera el código).
  String get codigoInvitacion => codigo.isNotEmpty ? codigo : id;

  /// ¿Este deporte tiene circuito/ranking? Solo los de raqueta (tenis, pádel,
  /// pickleball) hoy. Fútbol/natación NO → no se ofrece "ver/sumar al ranking".
  bool get esDeporteCircuito => deportesCircuito.contains(deporte);

  /// ¿Se muestra el estado "completo/incompleto" por equipo? Solo fútbol y si el
  /// organizador definió un mínimo de jugadores por equipo.
  bool get usaCupoEquipos => deporte == Deporte.futbol && minJugadoresEquipo > 0;

  /// ¿El equipo [p] llegó al mínimo de jugadores (está "completo")? Si no hay
  /// cupo definido, siempre false (no aplica).
  bool equipoCompleto(Participante p) =>
      usaCupoEquipos && p.roster.length >= minJugadoresEquipo;

  // ── Pozo del equipo (cuota repartida entre el plantel) ────────────────────
  // Espejo de `web/campeonatos_logica.py` y `pagos/pozos.py`.
  /// ¿La cuota se cobra POR EQUIPO y se reparte? Solo fútbol con costo.
  bool get tieneCuotaPorEquipo =>
      deporte == Deporte.futbol && costoInscripcion > 0;

  /// Entre cuántos se reparte: el máximo; si no hay, el mínimo; si no, 0
  /// (= quien crea el equipo pone la cuota entera).
  int get cupoReparto => maxJugadoresEquipo > 0
      ? maxJugadoresEquipo
      : (minJugadoresEquipo > 0 ? minJugadoresEquipo : 0);

  int get cuotaEquipoCentimos => (costoInscripcion * 100).round();

  /// Parte de cada jugador: cuota ÷ cupo, redondeada HACIA ARRIBA a 0.50.
  int get cuotaJugadorCentimos {
    final cuota = cuotaEquipoCentimos;
    if (cuota <= 0) return 0;
    final cupo = cupoReparto > 0 ? cupoReparto : 1;
    return ((cuota / cupo) / 50).ceil() * 50;
  }

  /// Lo que lleva juntado el equipo (suma de aportes espejados).
  int pozoCentimos(Participante p) =>
      p.roster.fold<int>(0, (a, m) => a + m.aporteCentimos);

  int faltantePozo(Participante p) {
    final f = cuotaEquipoCentimos - pozoCentimos(p);
    return f > 0 ? f : 0;
  }

  /// ¿El equipo ya cubrió su cuota (está INSCRITO)? Sin cuota, siempre true.
  bool pozoCompleto(Participante p) =>
      !tieneCuotaPorEquipo || pozoCentimos(p) >= cuotaEquipoCentimos;

  /// ¿El plantel llegó al tope? (0 = sin tope).
  bool equipoLleno(Participante p) =>
      maxJugadoresEquipo > 0 && p.roster.length >= maxJugadoresEquipo;

  /// Cuánto le toca poner al PRÓXIMO en unirse: su cuota o lo que falte.
  int aporteSiguiente(Participante? p) {
    if (!tieneCuotaPorEquipo) return 0;
    if (p == null) return cuotaJugadorCentimos.clamp(0, cuotaEquipoCentimos);
    final falta = faltantePozo(p);
    return falta < cuotaJugadorCentimos ? falta : cuotaJugadorCentimos;
  }

  /// "S/ 10" / "S/ 14.50" (sin decimales cuando son .00).
  String fmtMonto(int centimos) {
    final v = centimos / 100.0;
    final txt = (v - v.roundToDouble()).abs() < 0.005
        ? v.round().toString()
        : v.toStringAsFixed(2);
    return '$monedaSimbolo $txt';
  }

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
    String? logoUrl,
    int? minJugadoresEquipo,
    int? maxJugadoresEquipo,
    int? minPartidos,
    List<List<String>>? gruposManuales,
    String? premios,
    String? auspiciador,
    List<String>? auspiciadoresLogos,
    List<String>? fotos,
    String? aficheFondoUrl,
    int? aficheVariante,
    String? aficheTema,
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
        logoUrl: logoUrl ?? this.logoUrl,
        minJugadoresEquipo: minJugadoresEquipo ?? this.minJugadoresEquipo,
        maxJugadoresEquipo: maxJugadoresEquipo ?? this.maxJugadoresEquipo,
        minPartidos: minPartidos ?? this.minPartidos,
        gruposManuales: gruposManuales ?? this.gruposManuales,
        premios: premios ?? this.premios,
        auspiciador: auspiciador ?? this.auspiciador,
        auspiciadoresLogos: auspiciadoresLogos ?? this.auspiciadoresLogos,
        fotos: fotos ?? this.fotos,
        aficheFondoUrl: aficheFondoUrl ?? this.aficheFondoUrl,
        aficheVariante: aficheVariante ?? this.aficheVariante,
        aficheTema: aficheTema ?? this.aficheTema,
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
        if (logoUrl != null && logoUrl!.isNotEmpty) 'logoUrl': logoUrl,
        if (minJugadoresEquipo > 0) 'minJugadoresEquipo': minJugadoresEquipo,
        if (maxJugadoresEquipo > 0) 'maxJugadoresEquipo': maxJugadoresEquipo,
        if (formato == FormatoTorneo.grupos) 'minPartidos': minPartidos,
        if (formato == FormatoTorneo.grupos && gruposManuales.isNotEmpty)
          'gruposManuales': gruposManuales,
        if (premios.isNotEmpty) 'premios': premios,
        if (auspiciador.isNotEmpty) 'auspiciador': auspiciador,
        if (auspiciadoresLogos.isNotEmpty)
          'auspiciadoresLogos': auspiciadoresLogos,
        if (fotos.isNotEmpty) 'fotos': fotos,
        if (aficheFondoUrl.isNotEmpty) 'aficheFondoUrl': aficheFondoUrl,
        if (aficheVariante != 0) 'aficheVariante': aficheVariante,
        if (aficheTema.isNotEmpty) 'aficheTema': aficheTema,
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
        logoUrl: j['logoUrl'] as String?,
        minJugadoresEquipo: (j['minJugadoresEquipo'] as num?)?.toInt() ?? 0,
        maxJugadoresEquipo: (j['maxJugadoresEquipo'] as num?)?.toInt() ?? 0,
        minPartidos: kMinPartidosOpciones.contains((j['minPartidos'] as num?)?.toInt())
            ? (j['minPartidos'] as num).toInt()
            : 2,
        gruposManuales: [
          for (final g in (j['gruposManuales'] as List?) ?? const [])
            if (g is List) [for (final x in g) x.toString()],
        ],
        premios: (j['premios'] ?? '') as String,
        auspiciador: (j['auspiciador'] ?? '') as String,
        auspiciadoresLogos: (j['auspiciadoresLogos'] as List?)
                ?.map((e) => e.toString())
                .toList() ??
            const [],
        fotos: (j['fotos'] as List?)?.map((e) => e.toString()).toList() ??
            const [],
        aficheFondoUrl: (j['aficheFondoUrl'] ?? '') as String,
        aficheVariante: (j['aficheVariante'] as num?)?.toInt() ?? 0,
        aficheTema: (j['aficheTema'] ?? '') as String,
      );
}

/// Lógica de fixture: generar llave/liga, propagar ganadores y calcular tabla.
/// Sin estado; opera sobre listas. (Se mantiene fuera del modelo para tenerlo
/// testeable y aislado.)
class TorneoFixture {
  /// Genera el fixture según el formato. Requiere ≥ 2 participantes.
  static List<PartidoTorneo> generar(
      FormatoTorneo formato, List<Participante> ps,
      {int minPartidos = 2, List<List<String>>? gruposManuales}) {
    if (ps.length < 2) return const [];
    if (formato == FormatoTorneo.liga) return _generarLiga(ps);
    if (formato == FormatoTorneo.grupos) {
      return _generarGrupos(ps, minPartidos, gruposManuales);
    }
    return recomputarLlave(_esqueletoEliminacion(ps));
  }

  /// Genera el fixture de [c] con su formato, su mínimo de partidos y, si el
  /// organizador los armó a mano y siguen válidos, sus grupos.
  static List<PartidoTorneo> generarDe(Campeonato c) => generar(
      c.formato, c.participantes,
      minPartidos: c.minPartidos, gruposManuales: gruposManualesDe(c));

  /// Los grupos a mano de [c] si existen y siguen siendo válidos; si no, null
  /// (sorteo automático). ESPEJO de `campeonatos_logica.grupos_manuales`.
  static List<List<String>>? gruposManualesDe(Campeonato c) {
    if (c.gruposManuales.isEmpty) return null;
    if (validarGruposManuales(c, c.gruposManuales) != null) return null;
    return c.gruposManuales;
  }

  /// Valida grupos a mano: 1..16 grupos, cada uno con ≥ 2 equipos y TODOS los
  /// participantes asignados exactamente una vez. Devuelve el mensaje de error
  /// o null si es válido. ESPEJO de `validar_grupos_manuales` (web).
  static String? validarGruposManuales(
      Campeonato c, List<List<String>> grupos) {
    final ids = [for (final p in c.participantes) p.id];
    if (grupos.isEmpty) return 'Arma al menos un grupo.';
    if (grupos.length > _letras.length) return 'Máximo ${_letras.length} grupos.';
    final vistos = <String>{};
    for (var i = 0; i < grupos.length; i++) {
      final g = grupos[i];
      if (g.length < 2) {
        return 'El grupo ${_letras[i]} necesita al menos 2 equipos.';
      }
      for (final x in g) {
        if (!ids.contains(x)) {
          return 'Hay un equipo que ya no está inscrito: vuelve a armar los grupos.';
        }
        if (!vistos.add(x)) return 'Un equipo está en dos grupos.';
      }
    }
    final faltan = [
      for (final p in c.participantes)
        if (!vistos.contains(p.id)) p.nombre
    ];
    if (faltan.isNotEmpty) {
      return 'Falta asignar a: ${faltan.take(4).join(', ')}'
          '${faltan.length > 4 ? '…' : ''}';
    }
    return null;
  }

  // ── Grupos + eliminatoria ─────────────────────────────────────────────────
  static const _letras = 'ABCDEFGHIJKLMNOP';

  /// Tamaños de grupo para [n] equipos garantizando [minPartidos] partidos a
  /// cada uno (grupo de k → k-1 partidos). Prefiere grupos de 4 cuando el
  /// mínimo es 2; reparte parejo (tamaños que difieren a lo sumo en 1). Con
  /// menos de 3 equipos no hay cómo garantizarlo: [] (se juega solo la final).
  /// ESPEJO de `campeonatos_logica.armar_grupos` (web): no cambiar uno solo.
  static List<int> armarGrupos(int n, int minPartidos) {
    final tam = (minPartidos < 2 ? 2 : minPartidos) + 1;
    if (n < 3 || n < tam) return const [];
    var g = n ~/ tam;
    if (g < 1) g = 1;
    if (minPartidos <= 2) {
      final pref = (n / 4 + 0.5).floor();
      g = g < (pref < 1 ? 1 : pref) ? g : (pref < 1 ? 1 : pref);
    }
    final base = n ~/ g, extra = n % g;
    return [for (var i = 0; i < g; i++) base + (i < extra ? 1 : 0)];
  }

  /// Posiciones de siembra estándar (1 vs size, 2 vs size-1…): [1,8,4,5,2,7,3,6].
  static List<int> _ordenSiembra(int size) {
    var seq = [1];
    while (seq.length < size) {
      final k = seq.length * 2;
      seq = [for (final s in seq) ...[s, k + 1 - s]];
    }
    return seq;
  }

  static List<PartidoTorneo> _generarGrupos(
      List<Participante> ps, int minPartidos,
      [List<List<String>>? gruposManuales]) {
    final List<List<Participante>> listas;
    if (gruposManuales != null && gruposManuales.isNotEmpty) {
      // A mano: el organizador decidió cuántos grupos y quién va en cada uno.
      final porId = {for (final p in ps) p.id: p};
      listas = [
        for (final g in gruposManuales)
          [for (final id in g) if (porId[id] != null) porId[id]!],
      ];
    } else {
      final tams = armarGrupos(ps.length, minPartidos);
      if (tams.isEmpty) return recomputarLlave(_esqueletoEliminacion(ps));
      listas = [];
      var pos = 0;
      for (final t in tams) {
        listas.add(ps.sublist(pos, pos + t));
        pos += t;
      }
    }
    final tams = [for (final l in listas) l.length];
    final partidos = <PartidoTorneo>[];
    for (var gi = 0; gi < listas.length; gi++) {
      final letra = _letras[gi];
      final miembros = listas[gi];
      for (final m in _generarLiga(miembros)) {
        partidos.add(PartidoTorneo(
            id: 'g${letra}_${m.id}', ronda: m.ronda, idx: m.idx,
            aId: m.aId, bId: m.bId, fase: 'grupo', grupo: letra));
      }
    }
    // Esqueleto de la llave: clasifican 2 por grupo; potencia de 2 con byes.
    final q = 2 * tams.length;
    var size = 1;
    while (size < q) {
      size *= 2;
    }
    for (var i = 0; i < size ~/ 2; i++) {
      partidos.add(PartidoTorneo(id: 'k0_$i', ronda: 0, idx: i, fase: 'llave'));
    }
    var matches = size ~/ 2;
    var r = 1;
    while (matches > 1) {
      matches ~/= 2;
      for (var i = 0; i < matches; i++) {
        partidos.add(PartidoTorneo(id: 'k${r}_$i', ronda: r, idx: i, fase: 'llave'));
      }
      r++;
    }
    return partidos;
  }

  /// Tabla de UN grupo (solo sus equipos y sus partidos).
  static List<FilaTabla> tablaGrupo(Campeonato c, String letra) {
    final ms = [for (final m in c.partidosGrupo) if (m.grupo == letra) m];
    final ids = <String>{for (final m in ms) ...[if (m.aId != null) m.aId!, if (m.bId != null) m.bId!]};
    return tabla(c,
        partidos: ms,
        participantes: [for (final p in c.participantes) if (ids.contains(p.id)) p]);
  }

  /// Clasificados con su siembra: primeros de cada grupo (ordenados por
  /// campaña) y luego segundos (ídem). Cada uno: (id, grupo, pos).
  static List<({String id, String grupo, int pos})> clasificados(Campeonato c) {
    final primeros = <(FilaTabla, String)>[];
    final segundos = <(FilaTabla, String)>[];
    for (final letra in c.grupos) {
      final t = tablaGrupo(c, letra);
      if (t.isNotEmpty) primeros.add((t[0], letra));
      if (t.length > 1) segundos.add((t[1], letra));
    }
    int cmp((FilaTabla, String) x, (FilaTabla, String) y) {
      if (y.$1.pts != x.$1.pts) return y.$1.pts - x.$1.pts;
      if (y.$1.dif != x.$1.dif) return y.$1.dif - x.$1.dif;
      return y.$1.gf - x.$1.gf;
    }
    primeros.sort(cmp);
    segundos.sort(cmp);
    return [
      for (final e in primeros) (id: e.$1.participanteId, grupo: e.$2, pos: 1),
      for (final e in segundos) (id: e.$1.participanteId, grupo: e.$2, pos: 2),
    ];
  }

  /// Rellena la ronda 0 de la llave con la siembra estándar (los mejores
  /// primeros reciben los byes) evitando, si se puede, que dos del mismo
  /// grupo se crucen en la primera ronda.
  static List<PartidoTorneo> _sembrar(
      List<PartidoTorneo> r0, List<({String id, String grupo, int pos})> sembrados) {
    final ordenados = List<PartidoTorneo>.from(r0)..sort((a, b) => a.idx.compareTo(b.idx));
    final size = ordenados.length * 2;
    final orden = _ordenSiembra(size);
    final slots = [for (final o in orden) o - 1 < sembrados.length ? sembrados[o - 1] : null];
    final pares = [for (var i = 0; i < ordenados.length; i++) [slots[2 * i], slots[2 * i + 1]]];
    for (var i = 0; i < pares.length; i++) {
      final a = pares[i][0], b = pares[i][1];
      if (a == null || b == null || a.grupo != b.grupo) continue;
      for (var j = 0; j < pares.length; j++) {
        final c2 = pares[j][0], d2 = pares[j][1];
        if (j == i || c2 == null || d2 == null) continue;
        if (b.pos == 2 && d2.pos == 2 && d2.grupo != a.grupo && b.grupo != c2.grupo) {
          pares[i][1] = d2;
          pares[j][1] = b;
          break;
        }
      }
    }
    return [
      for (var i = 0; i < ordenados.length; i++)
        PartidoTorneo(
            id: ordenados[i].id, ronda: 0, idx: i,
            aId: pares[i][0]?.id, bId: pares[i][1]?.id, fase: 'llave'),
    ];
  }

  /// Formato grupos: con la fase de grupos completa siembra la llave (solo
  /// mientras ningún partido de llave tenga resultado) y propaga ganadores.
  static List<PartidoTorneo> recomputarGrupos(
      Campeonato c, List<PartidoTorneo> partidos) {
    final grupo = [for (final m in partidos) if (m.esGrupo) m];
    final llave = [for (final m in partidos) if (m.esLlave) m];
    if (llave.isEmpty) return partidos;
    final tmp = c.copyWith(partidos: grupo);
    var r0 = [for (final m in llave) if (m.ronda == 0) m];
    final resto = [for (final m in llave) if (m.ronda != 0) m];
    if (!llave.any((m) => m.jugado)) {
      r0 = tmp.gruposCompletos
          ? _sembrar(r0, clasificados(tmp))
          : [for (final m in r0) m.conLados(null, null)];
    }
    return [...grupo, ...recomputarLlave([...r0, ...resto])];
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
          fase: m.fase, grupo: m.grupo,
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

  /// Tabla de posiciones (formato liga) ordenada por Pts, dif, GF. Con
  /// [partidos]/[participantes] se calcula sobre un subconjunto (un grupo).
  static List<FilaTabla> tabla(Campeonato c,
      {List<PartidoTorneo>? partidos, List<Participante>? participantes}) {
    final filas = <String, FilaTabla>{
      for (final p in participantes ?? c.participantes)
        p.id: FilaTabla(p.id, p.nombre),
    };
    for (final m in partidos ?? c.partidos) {
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
