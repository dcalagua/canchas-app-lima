import 'package:google_maps_flutter/google_maps_flutter.dart';

import '../config/pais.dart';
import 'models.dart';

/// Tipo de plan que ofrece una academia.
enum TipoPlan {
  mensual('Mensualidad'),
  prepago('Paquete de meses'),
  porClase('Por clase');

  final String etiqueta;
  const TipoPlan(this.etiqueta);
}

/// Un plan/paquete que la academia vende a sus alumnos.
/// - [mensual]/[prepago]: genera [meses] cuotas mensuales de [precioMes] c/u.
/// - [porClase]: no genera cuotas por adelantado; cada clase suelta cobra
///   [precioMes] (se reusa el campo como "precio por clase").
class Plan {
  final String id;
  final String nombre;
  final TipoPlan tipo;
  final double precioMes; // S/ por mes (o por clase si tipo == porClase)
  final int meses; // duración: 1 (mensual) o N (prepago); 0 si porClase
  /// Tarifario por PROGRAMA y FRECUENCIA (academias tipo Jartur El Bosque):
  /// [programa] agrupa (ej. "Bola Roja y Naranja"); [frecuenciaSemana] es las
  /// veces por semana (2–5). Vacío/0 = plan simple (sin matriz). [precioMes] es
  /// la tarifa SOCIO; la de invitado se deriva con `Academia.recargoInvitado`.
  final String programa;
  final int frecuenciaSemana;
  /// Descripción de la ETAPA/EDAD del programa (ej. "Iniciación e intermedio ·
  /// 5 a 10 años"). Compartida por todas las frecuencias del mismo programa.
  final String etapaEdad;
  /// Duración de la clase (ej. "1 h 30 min", "2 h"). Igual dentro del programa.
  final String duracionClase;
  /// Días y horario del programa (opcional, texto libre; ej. "Lun, Mié y Vie ·
  /// 5:00–6:30 pm"). Compartido por todas las frecuencias del programa. Es el
  /// horario "por defecto"; en academias multi-sede, el horario por sede
  /// (`Academia.horarios[sede|programa]`) manda si está puesto.
  final String horario;

  const Plan({
    required this.id,
    required this.nombre,
    required this.tipo,
    required this.precioMes,
    this.meses = 1,
    this.programa = '',
    this.frecuenciaSemana = 0,
    this.etapaEdad = '',
    this.duracionClase = '',
    this.horario = '',
  });

  /// Total del plan (para mostrar "paga todo").
  double get total => tipo == TipoPlan.porClase ? precioMes : precioMes * meses;

  /// Etiqueta corta de frecuencia: 3 → "3x/sem" (vacío si no aplica).
  String get frecuenciaLabel =>
      frecuenciaSemana > 0 ? '${frecuenciaSemana}x/sem' : '';

  Map<String, dynamic> toJson() => {
        'id': id,
        'nombre': nombre,
        'tipo': tipo.name,
        'precioMes': precioMes,
        'meses': meses,
        'programa': programa,
        'frecuenciaSemana': frecuenciaSemana,
        'etapaEdad': etapaEdad,
        'duracionClase': duracionClase,
        'horario': horario,
      };

  factory Plan.fromJson(Map<String, dynamic> j) => Plan(
        id: j['id'] as String,
        nombre: (j['nombre'] ?? '') as String,
        tipo: TipoPlan.values.firstWhere(
            (t) => t.name == j['tipo'], orElse: () => TipoPlan.mensual),
        precioMes: ((j['precioMes'] ?? 0) as num).toDouble(),
        meses: ((j['meses'] ?? 1) as num).toInt(),
        programa: (j['programa'] ?? '') as String,
        frecuenciaSemana: ((j['frecuenciaSemana'] ?? 0) as num).toInt(),
        etapaEdad: (j['etapaEdad'] ?? '') as String,
        duracionClase: (j['duracionClase'] ?? '') as String,
        horario: (j['horario'] ?? '') as String,
      );
}

/// Una academia (marca independiente). Rota de sede: `sedeClub` es cambiable y
/// su historia (alumnos, cuotas) no depende del local. Ver docs/flujo-academias.
class Academia {
  final String id;
  final String nombre;
  final Deporte deporte;
  final String dueno; // correo del profe
  final String whatsapp; // contacto (para que el alumno la ubique)
  final String descripcion;
  final String sedeClub; // dónde entrena AHORA (nombre del club/local)
  final LatLng? sedeUbicacion;
  /// ZONA / distrito de la academia (ej. "San Borja", "Miraflores"). Texto libre
  /// que el dueño fija. Se usa para segmentar el RANKING GLOBAL por ciudad/zona.
  /// Vacío = sin zona (solo aparece en "Todas").
  final String zona;
  final List<Plan> planes;
  final String? logoUrl; // logo de la academia (si tiene)
  final Map<String, String> redes; // red → handle/url (instagram, tiktok…)
  final List<String> fotos; // feed propio (URLs de fotos subidas por el profe)
  /// Moneda de la academia, congelada al crearla según el país ('' = 'S/', Perú).
  /// Los precios de los planes se muestran en esta moneda sin importar el país
  /// desde donde se abra la app.
  final String moneda;
  /// Recargo FIJO (S/) que paga un INVITADO (no socio de la sede/club) sobre la
  /// tarifa socio del plan. 0 = la academia no distingue socio/invitado (un solo
  /// precio). Caso Jartur (Country Club El Bosque): 50.
  final double recargoInvitado;
  /// Descuentos CONFIGURABLES (%), 0 = sin descuento. Se aplican al inscribir:
  /// [descuentoHermano2] al 2º hermano, [descuentoHermano3] al 3º en adelante,
  /// [descuentoPrepago] al pagar un paquete de meses por adelantado (prepago).
  /// Caso Jartur: 10 / 20 / 5. Son ADITIVOS entre sí (2º hermano + prepago =
  /// 10 + 5 = 15%).
  final double descuentoHermano2;
  final double descuentoHermano3;
  final double descuentoPrepago;
  /// Desde cuántos MESES adelantados aplica [descuentoPrepago]. CONFIGURABLE por
  /// el profe (default 3): al pagar N ≥ este umbral de golpe, se aplica el
  /// descuento de prepago. Si es 1, cualquier pago adelantado ya descuenta.
  final int mesesMinPrepago;
  /// URL de la LANDING/publicidad de la academia (servicio de marketing de
  /// Pichangol). Vacío = no contratada. Se muestra como "Sitio web" en la ficha
  /// y el dueño puede compartirla. Configurable por academia (extra opcional).
  final String landingUrl;
  /// Retribución (%) que la academia le paga al CLUB/sede sobre lo EFECTIVAMENTE
  /// cobrado (liquidación). CONFIGURABLE; 0 = la academia no le paga nada al club
  /// (clubes que no usan esta opción). Caso Jartur (El Bosque): 11.
  final double retribucionClubPct;
  /// SEDES de la academia (multi-local). Una academia de fútbol puede operar en
  /// varios lugares con horarios distintos. Vacío = academia de una sola sede
  /// (se usa la sede principal `sedeClub`/`sedeUbicacion`).
  final List<Sede> sedes;
  /// HORARIOS por SEDE y PROGRAMA. Clave = "sedeId|programa" → texto del horario
  /// (ej. "Lun-Mié-Vie 4-6pm"). Así cada programa (Sub-8, Sub-10…) tiene su
  /// horario en cada sede.
  final Map<String, String> horarios;
  /// PRECIOS por SEDE y PLAN (multi-sede con tarifas distintas por local).
  /// Clave = "sedeId|planId" → precio mensual (o por clase) en esa sede. Si un
  /// (sede, plan) no está aquí, se usa el `Plan.precioMes` base. Vacío = todas
  /// las sedes cobran el precio base del plan.
  final Map<String, double> preciosSede;
  /// CIRCUITO / RANKING interno (Fase 0): partidos jugados entre alumnos de la
  /// academia. Alimentan la tabla de posiciones (`ranking`). Se embeben en la
  /// academia (sin tabla nueva). El profe los registra.
  final List<PartidoRanking> partidos;
  /// CATEGORÍA de cada alumno en el ranking (ej. "7ma", "Intermedio").
  /// Clave = alumnoId → categoría. Vacío = sin categoría.
  final Map<String, String> categorias;

  const Academia({
    required this.id,
    required this.nombre,
    required this.deporte,
    required this.dueno,
    this.whatsapp = '',
    this.descripcion = '',
    this.sedeClub = '',
    this.sedeUbicacion,
    this.zona = '',
    this.planes = const [],
    this.logoUrl,
    this.redes = const {},
    this.fotos = const [],
    this.moneda = '',
    this.recargoInvitado = 0,
    this.descuentoHermano2 = 0,
    this.descuentoHermano3 = 0,
    this.descuentoPrepago = 0,
    this.mesesMinPrepago = 3,
    this.landingUrl = '',
    this.retribucionClubPct = 0,
    this.sedes = const [],
    this.horarios = const {},
    this.preciosSede = const {},
    this.partidos = const [],
    this.categorias = const {},
  });

  /// Sedes EFECTIVAS: las declaradas; si no hay ninguna, una sede única derivada
  /// de la sede principal (compatibilidad con academias de un solo local).
  List<Sede> get sedesEfectivas => sedes.isNotEmpty
      ? sedes
      : [
          Sede(
              id: 'principal',
              nombre: sedeClub.isNotEmpty ? sedeClub : 'Sede principal',
              ubicacion: sedeUbicacion)
        ];

  /// ¿Opera en más de una sede?
  bool get multiSede => sedes.length > 1;

  /// Horario configurado para (sede, programa). Vacío si no se fijó.
  String horarioDe(String sedeId, String programa) =>
      horarios['$sedeId|$programa'] ?? '';

  /// Precio mensual (o por clase) EFECTIVO de un plan en una sede: el override
  /// de `preciosSede` si existe; si no, el precio base del plan. `sedeId` vacío
  /// (sede única) siempre cae al precio base.
  double precioMesEnSede(Plan p, String sedeId) {
    if (sedeId.isEmpty) return p.precioMes;
    return preciosSede['$sedeId|${p.id}'] ?? p.precioMes;
  }

  /// Total del plan en una sede (respeta el override de precio de esa sede).
  double totalPlanEnSede(Plan p, String sedeId) {
    final precio = precioMesEnSede(p, sedeId);
    return p.tipo == TipoPlan.porClase ? precio : precio * p.meses;
  }

  /// ¿Alguna sede tiene un precio distinto al base para este plan?
  bool tienePreciosPorSede(Plan p) =>
      sedes.any((s) => preciosSede.containsKey('${s.id}|${p.id}'));

  /// ¿Aplica el descuento de prepago al pagar [meses] adelantados de golpe?
  bool aplicaPrepago(int meses) =>
      descuentoPrepago > 0 && meses >= mesesMinPrepago;

  /// ¿Tiene landing/publicidad contratada (servicio de marketing)?
  bool get tieneLanding => landingUrl.trim().isNotEmpty;

  /// ¿La academia distingue tarifa socio vs invitado (según la sede/club)?
  bool get tieneTarifaInvitado => recargoInvitado > 0;

  /// Tarifa mensual efectiva de un plan según sea socio (de la sede) o invitado.
  double precioDePlan(Plan p, {required bool socio}) =>
      socio ? p.precioMes : p.precioMes + recargoInvitado;

  /// ¿La academia tiene algún descuento configurado?
  bool get tieneDescuentos =>
      descuentoHermano2 > 0 || descuentoHermano3 > 0 || descuentoPrepago > 0;

  /// ¿Distingue descuento por orden de hermano (2º / 3º)?
  bool get tieneDescuentoHermanos =>
      descuentoHermano2 > 0 || descuentoHermano3 > 0;

  /// % de descuento por orden de hermano (1 = único/1º sin dto, 2 = 2º, 3+ = 3º
  /// o más).
  double descuentoHermanoPct(int orden) {
    if (orden >= 3) return descuentoHermano3;
    if (orden == 2) return descuentoHermano2;
    return 0;
  }

  /// % total de descuento aplicable (hermano + prepago), aditivo, tope 100.
  double descuentoTotalPct({int ordenHermano = 1, bool prepago = false}) {
    var d = descuentoHermanoPct(ordenHermano);
    if (prepago) d += descuentoPrepago;
    return d > 100 ? 100 : d;
  }

  /// Precio final de un plan tras aplicar tarifa socio/invitado y descuentos.
  double precioFinal(Plan p,
      {required bool socio, int ordenHermano = 1, bool prepago = false}) {
    final base = precioDePlan(p, socio: socio);
    final f = base *
        (1 - descuentoTotalPct(ordenHermano: ordenHermano, prepago: prepago) / 100);
    return f < 0 ? 0 : f;
  }

  /// ¿La academia le retribuye un % al club/sede (liquidación)?
  bool get tieneRetribucionClub => retribucionClubPct > 0;

  /// Monto a pagar al club sobre lo EFECTIVAMENTE cobrado.
  double retribucionClub(double cobrado) => cobrado * retribucionClubPct / 100;

  /// Planes agrupados por programa (para el tarifario matriz), preservando el
  /// orden de aparición. Los planes sin programa quedan bajo la clave ''.
  Map<String, List<Plan>> get planesPorPrograma {
    final m = <String, List<Plan>>{};
    for (final p in planes) {
      (m[p.programa] ??= []).add(p);
    }
    for (final lista in m.values) {
      lista.sort((a, b) => a.frecuenciaSemana.compareTo(b.frecuenciaSemana));
    }
    return m;
  }

  /// Símbolo de moneda de la academia. La UBICACIÓN de la sede es la fuente de
  /// verdad (una academia en Lima cobra en S/, aunque el profe abra la app desde
  /// Bolivia): se deriva del país donde cae la sede. Esto auto-corrige academias
  /// que quedaron con la moneda del dispositivo del profe. Si no hay sede
  /// ubicada, cae a la moneda congelada al crear y, por último, a 'S/'.
  String get monedaSimbolo {
    final u = sedeUbicacion;
    if (u != null) return monedaDeCoordenadas(u.latitude, u.longitude);
    return moneda.isNotEmpty ? moneda : 'S/';
  }

  /// País (config) de la academia según su sede; si no hay sede ubicada, cae al
  /// país activo. Fuente del prefijo telefónico y la moneda en el editor.
  PaisConfig get pais {
    final u = sedeUbicacion;
    return u != null ? paisDeCoordenadas(u.latitude, u.longitude) : paisActual;
  }

  /// Código corto y ESTABLE para que un alumno se una desde la app
  /// ("Unirme con código"). Se deriva del [id] (hash FNV-1a → base32), así que
  /// no necesita almacenarse ni migrarse y es el mismo en todos los
  /// dispositivos. 6 caracteres sin ambiguos (sin 0/O/1/I).
  String get codigo => _codigoDeId(id);

  static const _alfabeto = '23456789ABCDEFGHJKLMNPQRSTUVWXYZ'; // 32 símbolos

  static String _codigoDeId(String id) {
    var h = 0x811c9dc5; // FNV-1a 32-bit offset basis
    for (final c in id.codeUnits) {
      h = (h ^ c) & 0xFFFFFFFF;
      h = (h * 0x01000193) & 0xFFFFFFFF; // FNV prime
    }
    final sb = StringBuffer();
    for (var i = 0; i < 6; i++) {
      sb.write(_alfabeto[(h >> (i * 5)) & 31]);
    }
    return sb.toString();
  }

  /// Normaliza un código tecleado por el alumno para compararlo con [codigo]:
  /// mayúsculas y conserva solo los símbolos válidos del alfabeto (descarta
  /// espacios, guiones y ambiguos 0/O/1/I que el usuario pudiera teclear).
  static String normalizarCodigo(String entrada) {
    final sb = StringBuffer();
    for (final ch in entrada.toUpperCase().split('')) {
      if (_alfabeto.contains(ch)) sb.write(ch);
    }
    return sb.toString();
  }

  Academia copyWith({
    String? id,
    String? nombre,
    Deporte? deporte,
    String? whatsapp,
    String? descripcion,
    String? sedeClub,
    LatLng? sedeUbicacion,
    String? zona,
    List<Plan>? planes,
    String? logoUrl,
    Map<String, String>? redes,
    List<String>? fotos,
    String? moneda,
    double? recargoInvitado,
    double? descuentoHermano2,
    double? descuentoHermano3,
    double? descuentoPrepago,
    int? mesesMinPrepago,
    String? landingUrl,
    double? retribucionClubPct,
    List<Sede>? sedes,
    Map<String, String>? horarios,
    Map<String, double>? preciosSede,
    List<PartidoRanking>? partidos,
    Map<String, String>? categorias,
  }) =>
      Academia(
        id: id ?? this.id,
        nombre: nombre ?? this.nombre,
        deporte: deporte ?? this.deporte,
        dueno: dueno,
        whatsapp: whatsapp ?? this.whatsapp,
        descripcion: descripcion ?? this.descripcion,
        sedeClub: sedeClub ?? this.sedeClub,
        sedeUbicacion: sedeUbicacion ?? this.sedeUbicacion,
        zona: zona ?? this.zona,
        planes: planes ?? this.planes,
        logoUrl: logoUrl ?? this.logoUrl,
        redes: redes ?? this.redes,
        fotos: fotos ?? this.fotos,
        moneda: moneda ?? this.moneda,
        recargoInvitado: recargoInvitado ?? this.recargoInvitado,
        descuentoHermano2: descuentoHermano2 ?? this.descuentoHermano2,
        descuentoHermano3: descuentoHermano3 ?? this.descuentoHermano3,
        descuentoPrepago: descuentoPrepago ?? this.descuentoPrepago,
        mesesMinPrepago: mesesMinPrepago ?? this.mesesMinPrepago,
        landingUrl: landingUrl ?? this.landingUrl,
        retribucionClubPct: retribucionClubPct ?? this.retribucionClubPct,
        sedes: sedes ?? this.sedes,
        horarios: horarios ?? this.horarios,
        preciosSede: preciosSede ?? this.preciosSede,
        partidos: partidos ?? this.partidos,
        categorias: categorias ?? this.categorias,
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'nombre': nombre,
        'deporte': deporte.name,
        'dueno': dueno,
        'whatsapp': whatsapp,
        'descripcion': descripcion,
        'sedeClub': sedeClub,
        if (zona.isNotEmpty) 'zona': zona,
        if (sedeUbicacion != null) 'lat': sedeUbicacion!.latitude,
        if (sedeUbicacion != null) 'lng': sedeUbicacion!.longitude,
        'planes': planes.map((p) => p.toJson()).toList(),
        if (logoUrl != null) 'logoUrl': logoUrl,
        'redes': redes,
        'fotos': fotos,
        'moneda': moneda,
        'recargoInvitado': recargoInvitado,
        'descuentoHermano2': descuentoHermano2,
        'descuentoHermano3': descuentoHermano3,
        'descuentoPrepago': descuentoPrepago,
        'mesesMinPrepago': mesesMinPrepago,
        'landingUrl': landingUrl,
        'retribucionClubPct': retribucionClubPct,
        'sedes': sedes.map((s) => s.toJson()).toList(),
        'horarios': horarios,
        'preciosSede': preciosSede,
        'partidos': partidos.map((p) => p.toJson()).toList(),
        'categorias': categorias,
      };

  factory Academia.fromJson(Map<String, dynamic> j) => Academia(
        id: j['id'] as String,
        nombre: (j['nombre'] ?? '') as String,
        deporte: Deporte.values.firstWhere(
            (d) => d.name == j['deporte'], orElse: () => Deporte.tenis),
        dueno: (j['dueno'] ?? '') as String,
        whatsapp: (j['whatsapp'] ?? '') as String,
        descripcion: (j['descripcion'] ?? '') as String,
        sedeClub: (j['sedeClub'] ?? '') as String,
        zona: (j['zona'] ?? '') as String,
        sedeUbicacion: (j['lat'] != null && j['lng'] != null)
            ? LatLng((j['lat'] as num).toDouble(), (j['lng'] as num).toDouble())
            : null,
        planes: (j['planes'] as List?)
                ?.map((e) => Plan.fromJson(e as Map<String, dynamic>))
                .toList() ??
            const [],
        logoUrl: j['logoUrl'] as String?,
        redes: (j['redes'] as Map?)
                ?.map((k, v) => MapEntry(k.toString(), v.toString())) ??
            const {},
        fotos: (j['fotos'] as List?)?.map((e) => e.toString()).toList() ??
            const [],
        moneda: (j['moneda'] ?? '') as String,
        recargoInvitado: ((j['recargoInvitado'] ?? 0) as num).toDouble(),
        descuentoHermano2: ((j['descuentoHermano2'] ?? 0) as num).toDouble(),
        descuentoHermano3: ((j['descuentoHermano3'] ?? 0) as num).toDouble(),
        descuentoPrepago: ((j['descuentoPrepago'] ?? 0) as num).toDouble(),
        mesesMinPrepago: ((j['mesesMinPrepago'] ?? 3) as num).toInt(),
        landingUrl: (j['landingUrl'] ?? '') as String,
        retribucionClubPct:
            ((j['retribucionClubPct'] ?? 0) as num).toDouble(),
        sedes: (j['sedes'] as List?)
                ?.map((e) => Sede.fromJson(e as Map<String, dynamic>))
                .toList() ??
            const [],
        horarios: (j['horarios'] as Map?)
                ?.map((k, v) => MapEntry(k.toString(), v.toString())) ??
            const {},
        preciosSede: (j['preciosSede'] as Map?)?.map(
                (k, v) => MapEntry(k.toString(), (v as num).toDouble())) ??
            const {},
        partidos: (j['partidos'] as List?)
                ?.map((e) =>
                    PartidoRanking.fromJson(e as Map<String, dynamic>))
                .toList() ??
            const [],
        categorias: (j['categorias'] as Map?)
                ?.map((k, v) => MapEntry(k.toString(), v.toString())) ??
            const {},
      );

  // ── Circuito / Ranking interno (Fase 0) ─────────────────────────────────────
  /// Puntos por VICTORIA y por DERROTA (jugar suma; ganar suma más). Ajustables.
  static const int puntosVictoria = 3;
  static const int puntosDerrota = 1;

  /// Categoría de ranking de un alumno ('' si no se fijó).
  String categoriaDe(String alumnoId) => categorias[alumnoId] ?? '';

  /// Tabla de posiciones del ranking interno. Incluye a TODOS los alumnos dados
  /// en [alumnosAcademia] (los que no jugaron quedan al fondo con 0). Filtra por
  /// [sedeId] y/o [categoria] si se indican. Orden: puntos → % victorias → PG.
  List<PosicionRanking> ranking(List<Alumno> alumnosAcademia,
      {String? sedeId, String? categoria}) {
    final stats = <String, PosicionRanking>{};
    for (final a in alumnosAcademia) {
      if (categoria != null &&
          categoria.isNotEmpty &&
          categoriaDe(a.id) != categoria) {
        continue;
      }
      stats[a.id] = PosicionRanking(
        alumnoId: a.id,
        nombre: a.nombre,
        fotoUrl: a.fotoUrl,
        categoria: categoriaDe(a.id),
      );
    }
    for (final p in partidos) {
      if (sedeId != null && sedeId.isNotEmpty && p.sedeId != sedeId) continue;
      for (final jid in [p.jugadorAId, p.jugadorBId]) {
        final s = stats[jid];
        if (s == null) continue;
        final gano = p.ganadorId == jid;
        stats[jid] = s.conResultado(gano);
      }
    }
    final lista = stats.values.toList()
      ..sort((a, b) {
        if (b.puntos != a.puntos) return b.puntos.compareTo(a.puntos);
        if (b.pct != a.pct) return b.pct.compareTo(a.pct);
        return b.pg.compareTo(a.pg);
      });
    return lista;
  }

  /// Ranking derivado SOLO de los partidos (los jugadores son los que aparecen
  /// en ellos, con su nombre denormalizado). Sirve para el RANKING GLOBAL, que
  /// agrega academias sin cargar sus rosters de alumnos. Filtra por [categoria].
  List<PosicionRanking> rankingDePartidos({String? categoria}) {
    final stats = <String, PosicionRanking>{};
    void asegurar(String id, String nombre) {
      if (id.isEmpty || stats.containsKey(id)) return;
      final cat = categoriaDe(id);
      if (categoria != null && categoria.isNotEmpty && cat != categoria) return;
      stats[id] = PosicionRanking(alumnoId: id, nombre: nombre, categoria: cat);
    }

    for (final p in partidos) {
      asegurar(p.jugadorAId, p.jugadorANombre);
      asegurar(p.jugadorBId, p.jugadorBNombre);
    }
    for (final p in partidos) {
      final sa = stats[p.jugadorAId];
      if (sa != null) {
        stats[p.jugadorAId] = sa.conResultado(p.ganadorId == p.jugadorAId);
      }
      final sb = stats[p.jugadorBId];
      if (sb != null) {
        stats[p.jugadorBId] = sb.conResultado(p.ganadorId == p.jugadorBId);
      }
    }
    return stats.values.toList();
  }

  /// Partidos de un alumno (para su carnet), más recientes primero.
  List<PartidoRanking> partidosDe(String alumnoId) =>
      (partidos.where((p) => p.jugadorAId == alumnoId || p.jugadorBId == alumnoId)
              .toList()
        ..sort((a, b) => b.fecha.compareTo(a.fecha)));
}

/// Un PARTIDO del ranking interno de la academia (Fase 0 del Circuito): dos
/// alumnos se enfrentan; el ganador suma más puntos. Alimenta la tabla de
/// posiciones. Se embebe en la academia (no requiere tabla nueva en Supabase).
class PartidoRanking {
  final String id;
  final DateTime fecha;
  final String jugadorAId;
  final String jugadorANombre; // denormalizado para mostrar sin cruzar tablas
  final String jugadorBId;
  final String jugadorBNombre;
  /// Correo de cada jugador (denormalizado del alumno al registrar). Es la
  /// IDENTIDAD GLOBAL: el ranking global une a la misma persona entre academias
  /// por este correo. Vacío = alumno manual (no se dedupe entre academias).
  final String jugadorAEmail;
  final String jugadorBEmail;
  final String marcador; // texto libre, ej. "6-3 6-4"
  final String ganadorId; // == jugadorAId o jugadorBId
  final String sedeId; // opcional (academias multi-sede)

  const PartidoRanking({
    required this.id,
    required this.fecha,
    required this.jugadorAId,
    required this.jugadorANombre,
    required this.jugadorBId,
    required this.jugadorBNombre,
    required this.ganadorId,
    this.jugadorAEmail = '',
    this.jugadorBEmail = '',
    this.marcador = '',
    this.sedeId = '',
  });

  /// Correo del jugador con [id] (para la identidad global).
  String emailDe(String id) => id == jugadorAId ? jugadorAEmail : jugadorBEmail;

  String get perdedorId => ganadorId == jugadorAId ? jugadorBId : jugadorAId;
  String nombreDe(String id) =>
      id == jugadorAId ? jugadorANombre : jugadorBNombre;

  Map<String, dynamic> toJson() => {
        'id': id,
        'fecha': fecha.toIso8601String(),
        'jugadorAId': jugadorAId,
        'jugadorANombre': jugadorANombre,
        'jugadorBId': jugadorBId,
        'jugadorBNombre': jugadorBNombre,
        if (jugadorAEmail.isNotEmpty) 'jugadorAEmail': jugadorAEmail,
        if (jugadorBEmail.isNotEmpty) 'jugadorBEmail': jugadorBEmail,
        'marcador': marcador,
        'ganadorId': ganadorId,
        'sedeId': sedeId,
      };

  factory PartidoRanking.fromJson(Map<String, dynamic> j) => PartidoRanking(
        id: (j['id'] ?? '') as String,
        fecha: DateTime.tryParse((j['fecha'] ?? '') as String) ?? DateTime.now(),
        jugadorAId: (j['jugadorAId'] ?? '') as String,
        jugadorANombre: (j['jugadorANombre'] ?? '') as String,
        jugadorBId: (j['jugadorBId'] ?? '') as String,
        jugadorBNombre: (j['jugadorBNombre'] ?? '') as String,
        jugadorAEmail: (j['jugadorAEmail'] ?? '') as String,
        jugadorBEmail: (j['jugadorBEmail'] ?? '') as String,
        marcador: (j['marcador'] ?? '') as String,
        ganadorId: (j['ganadorId'] ?? '') as String,
        sedeId: (j['sedeId'] ?? '') as String,
      );
}

/// Una fila de la tabla de posiciones (computada, no se persiste).
class PosicionRanking {
  final String alumnoId;
  final String nombre;
  final String? fotoUrl;
  final String categoria;
  final int pj; // partidos jugados
  final int pg; // partidos ganados
  final int pp; // partidos perdidos

  const PosicionRanking({
    required this.alumnoId,
    required this.nombre,
    this.fotoUrl,
    this.categoria = '',
    this.pj = 0,
    this.pg = 0,
    this.pp = 0,
  });

  int get puntos =>
      pg * Academia.puntosVictoria + pp * Academia.puntosDerrota;
  double get pct => pj == 0 ? 0 : pg / pj * 100;

  PosicionRanking conResultado(bool gano) => PosicionRanking(
        alumnoId: alumnoId,
        nombre: nombre,
        fotoUrl: fotoUrl,
        categoria: categoria,
        pj: pj + 1,
        pg: pg + (gano ? 1 : 0),
        pp: pp + (gano ? 0 : 1),
      );
}

/// Una fila del RANKING GLOBAL Pichangol: un jugador de alguna academia, con su
/// academia y deporte, para el ranking cruzado por deporte (estilo circuito
/// abierto). Se computa agregando los partidos de todas las academias.
class RankingGlobalFila {
  final String academiaId;
  final String academiaNombre;
  final Deporte deporte;
  final String alumnoId;
  final String nombre;
  final String categoria;
  final int pj;
  final int pg;
  final int pp;
  final int puntos;
  final double pct;
  /// En cuántas academias juega esta persona (≥1). >1 = ranking dedupeado por su
  /// correo (misma persona en varias academias).
  final int academias;
  const RankingGlobalFila({
    required this.academiaId,
    required this.academiaNombre,
    required this.deporte,
    required this.alumnoId,
    required this.nombre,
    required this.categoria,
    required this.pj,
    required this.pg,
    required this.pp,
    required this.puntos,
    required this.pct,
    this.academias = 1,
  });

  /// Correo de identidad de la fila (clave 'e:correo'), o '' si es un alumno
  /// manual sin correo. Sirve para saber si es Pro / retarlo / abrir su perfil.
  String get emailIdentidad =>
      alumnoId.startsWith('e:') ? alumnoId.substring(2) : '';
}

/// El registro de un jugador en UNA academia (para su perfil global).
class RegistroPorAcademia {
  final String academia;
  final int pj;
  final int pg;
  final int pp;
  final int puntos;
  const RegistroPorAcademia({
    required this.academia,
    required this.pj,
    required this.pg,
    required this.pp,
    required this.puntos,
  });
}

/// Un partido con la academia donde se jugó y la perspectiva del jugador del
/// perfil (si ganó y contra quién). Para los "últimos partidos" del carnet global.
class PartidoConAcademia {
  final PartidoRanking partido;
  final String academia;
  final bool gano;
  final String rival;
  const PartidoConAcademia({
    required this.partido,
    required this.academia,
    required this.gano,
    required this.rival,
  });
}

/// PERFIL GLOBAL de un jugador: sus stats CONSOLIDADAS entre todas las academias
/// (identidad = correo), el desglose por academia y sus partidos recientes.
class PerfilGlobalJugador {
  final String nombre;
  final String categoria;
  final String email; // '' si identidad por academia (alumno manual)
  final int pj;
  final int pg;
  final int pp;
  final int puntos;
  final double pct;
  final List<RegistroPorAcademia> porAcademia;
  final List<PartidoConAcademia> partidos;
  const PerfilGlobalJugador({
    required this.nombre,
    required this.categoria,
    required this.email,
    required this.pj,
    required this.pg,
    required this.pp,
    required this.puntos,
    required this.pct,
    required this.porAcademia,
    required this.partidos,
  });
}

/// Una SEDE (local) de una academia multi-sede: nombre + dirección + ubicación.
/// El horario NO va aquí: se guarda por (sede, programa) en `Academia.horarios`,
/// porque cada programa (Sub-8, Sub-10…) entrena en días/horas distintos.
class Sede {
  final String id;
  final String nombre;
  final String direccion;
  final LatLng? ubicacion;
  const Sede({
    required this.id,
    required this.nombre,
    this.direccion = '',
    this.ubicacion,
  });

  Sede copyWith({String? nombre, String? direccion, LatLng? ubicacion}) => Sede(
        id: id,
        nombre: nombre ?? this.nombre,
        direccion: direccion ?? this.direccion,
        ubicacion: ubicacion ?? this.ubicacion,
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'nombre': nombre,
        'direccion': direccion,
        if (ubicacion != null) 'lat': ubicacion!.latitude,
        if (ubicacion != null) 'lng': ubicacion!.longitude,
      };

  factory Sede.fromJson(Map<String, dynamic> j) => Sede(
        id: (j['id'] ?? '') as String,
        nombre: (j['nombre'] ?? '') as String,
        direccion: (j['direccion'] ?? '') as String,
        ubicacion: (j['lat'] != null && j['lng'] != null)
            ? LatLng((j['lat'] as num).toDouble(), (j['lng'] as num).toDouble())
            : null,
      );
}

/// Un alumno inscrito en una academia.
///
/// [email] no vacío = **alumno-app**: se unió con el código desde la app (la
/// cuenta que lo administra: el propio adulto o un apoderado).
///
/// Menores: un niño NO tiene cuenta propia (Ley 29733). Se registra bajo un
/// **apoderado** (adulto con cuenta): [apoderadoNombre] no vacío ⇒ el alumno es
/// un menor; [nombre] es el nombre del niño y el contacto/pagos van al
/// apoderado ([apoderadoWhatsapp] / [email]).
class Alumno {
  final String id;
  final String academiaId;
  final String nombre; // nombre del alumno (adulto o niño)
  final String whatsapp; // WhatsApp del alumno adulto (si aplica)
  final String email; // cuenta-app que lo administra ('' si manual)
  final String? fotoUrl; // foto del perfil (si el alumno es el adulto)
  final String apoderadoNombre; // '' si el alumno es un adulto; nombre del padre si es menor
  final String apoderadoWhatsapp; // WhatsApp del apoderado (recordatorios de pago)
  final int? edad; // edad del alumno (opcional; útil para menores)
  /// ¿Es SOCIO de la sede/club (ej. Country Club El Bosque)? Define la tarifa:
  /// socio = precio del plan; invitado (false) = precio + recargoInvitado.
  /// Por defecto true (los alumnos fundadores son socios). Lo marca el profe.
  final bool esSocioSede;
  /// Orden de hermano para el descuento familiar configurable de la academia:
  /// 1 = único/1º (sin descuento), 2 = 2º hermano, 3 = 3º o más. Lo marca el
  /// profe al inscribir. Ver `Academia.descuentoHermano2/3`.
  final int ordenHermano;
  /// SEDE (local) donde entrena el alumno, en academias multi-sede. Vacío = la
  /// sede única/principal. Ver `Academia.sedes`.
  final String sedeId;

  const Alumno({
    required this.id,
    required this.academiaId,
    required this.nombre,
    this.whatsapp = '',
    this.email = '',
    this.fotoUrl,
    this.apoderadoNombre = '',
    this.apoderadoWhatsapp = '',
    this.edad,
    this.esSocioSede = true,
    this.ordenHermano = 1,
    this.sedeId = '',
  });

  /// ¿Es un alumno que usa la app (se unió con código)?
  bool get esApp => email.isNotEmpty;

  /// ¿Es un menor representado por un apoderado?
  bool get esMenor => apoderadoNombre.isNotEmpty;

  /// WhatsApp para contactarlo/recordar pagos: el del apoderado si es menor.
  String get whatsappContacto =>
      esMenor && apoderadoWhatsapp.isNotEmpty ? apoderadoWhatsapp : whatsapp;

  Map<String, dynamic> toJson() => {
        'id': id,
        'academiaId': academiaId,
        'nombre': nombre,
        'whatsapp': whatsapp,
        'email': email,
        if (fotoUrl != null) 'fotoUrl': fotoUrl,
        'apoderadoNombre': apoderadoNombre,
        'apoderadoWhatsapp': apoderadoWhatsapp,
        if (edad != null) 'edad': edad,
        'esSocioSede': esSocioSede,
        'ordenHermano': ordenHermano,
        'sedeId': sedeId,
      };

  factory Alumno.fromJson(Map<String, dynamic> j) => Alumno(
        id: j['id'] as String,
        academiaId: (j['academiaId'] ?? '') as String,
        nombre: (j['nombre'] ?? '') as String,
        whatsapp: (j['whatsapp'] ?? '') as String,
        email: (j['email'] ?? '') as String,
        fotoUrl: j['fotoUrl'] as String?,
        apoderadoNombre: (j['apoderadoNombre'] ?? '') as String,
        apoderadoWhatsapp: (j['apoderadoWhatsapp'] ?? '') as String,
        edad: (j['edad'] as num?)?.toInt(),
        esSocioSede: (j['esSocioSede'] ?? true) as bool,
        ordenHermano: ((j['ordenHermano'] ?? 1) as num).toInt(),
        sedeId: (j['sedeId'] ?? '') as String,
      );
}

/// Una cuota de cobro (mensualidad o clase suelta). Modelo estilo "provisión":
/// vencimiento + monto + estado. La mora se calcula al vencer (Fase 1: simple).
class Cuota {
  final String id;
  final String academiaId;
  final String alumnoId;
  final String concepto; // "Mensualidad · Marzo", "Clase suelta 12/03"
  final double monto;
  final DateTime vencimiento;
  final bool pagada;
  final DateTime? fechaPago; // cuándo se cobró (para reportes por fecha)
  /// N.º de operación del pago (charge_id de Culqi). Se muestra en el comprobante.
  final String operacionId;
  /// Cuota de una MENSUALIDAD con débito automático (pago "mes a mes"): el cron
  /// la cobra en su fecha. Sirve para la RECONCILIACIÓN (marcar pagada sola según
  /// los cobros que hizo el backend). Las cuotas normales (contado, clase suelta)
  /// van en false y no se auto-marcan.
  final bool autoDebito;

  const Cuota({
    required this.id,
    required this.academiaId,
    required this.alumnoId,
    required this.concepto,
    required this.monto,
    required this.vencimiento,
    this.pagada = false,
    this.fechaPago,
    this.autoDebito = false,
    this.operacionId = '',
  });

  /// Vencida = no pagada y ya pasó su fecha de vencimiento.
  bool vencidaAl(DateTime hoy) =>
      !pagada && vencimiento.isBefore(DateTime(hoy.year, hoy.month, hoy.day));

  Cuota copyWith(
          {bool? pagada,
          DateTime? fechaPago,
          bool limpiarFechaPago = false,
          String? operacionId}) =>
      Cuota(
        id: id,
        academiaId: academiaId,
        alumnoId: alumnoId,
        concepto: concepto,
        monto: monto,
        vencimiento: vencimiento,
        pagada: pagada ?? this.pagada,
        fechaPago: limpiarFechaPago ? null : (fechaPago ?? this.fechaPago),
        autoDebito: autoDebito,
        operacionId: operacionId ?? this.operacionId,
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'academiaId': academiaId,
        'alumnoId': alumnoId,
        'concepto': concepto,
        'monto': monto,
        'vencimiento': vencimiento.toIso8601String(),
        'pagada': pagada,
        if (fechaPago != null) 'fechaPago': fechaPago!.toIso8601String(),
        if (autoDebito) 'autoDebito': true,
        if (operacionId.isNotEmpty) 'operacionId': operacionId,
      };

  factory Cuota.fromJson(Map<String, dynamic> j) => Cuota(
        id: j['id'] as String,
        academiaId: (j['academiaId'] ?? '') as String,
        alumnoId: (j['alumnoId'] ?? '') as String,
        concepto: (j['concepto'] ?? '') as String,
        monto: ((j['monto'] ?? 0) as num).toDouble(),
        vencimiento:
            DateTime.tryParse((j['vencimiento'] ?? '') as String) ??
                DateTime.now(),
        pagada: (j['pagada'] ?? false) as bool,
        fechaPago: j['fechaPago'] != null
            ? DateTime.tryParse(j['fechaPago'] as String)
            : null,
        autoDebito: (j['autoDebito'] ?? false) as bool,
        operacionId: (j['operacionId'] ?? '') as String,
      );
}

/// Registro de ASISTENCIA de un alumno a una clase de un día. La clave lógica
/// es (alumnoId + día): marcar/desmarcar presente. [dia] es "YYYY-MM-DD".
class Asistencia {
  final String academiaId;
  final String alumnoId;
  final String dia; // 'YYYY-MM-DD'
  final bool presente;

  const Asistencia({
    required this.academiaId,
    required this.alumnoId,
    required this.dia,
    this.presente = true,
  });

  /// "YYYY-MM-DD" de una fecha (clave de día).
  static String claveDia(DateTime d) =>
      '${d.year.toString().padLeft(4, '0')}-'
      '${d.month.toString().padLeft(2, '0')}-'
      '${d.day.toString().padLeft(2, '0')}';

  Map<String, dynamic> toJson() => {
        'academiaId': academiaId,
        'alumnoId': alumnoId,
        'dia': dia,
        'presente': presente,
      };

  factory Asistencia.fromJson(Map<String, dynamic> j) => Asistencia(
        academiaId: (j['academiaId'] ?? '') as String,
        alumnoId: (j['alumnoId'] ?? '') as String,
        dia: (j['dia'] ?? '') as String,
        presente: (j['presente'] ?? true) as bool,
      );
}
