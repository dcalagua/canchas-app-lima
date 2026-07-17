import 'dart:typed_data';

import 'package:google_maps_flutter/google_maps_flutter.dart';
import 'package:supabase_flutter/supabase_flutter.dart' show FileOptions;

import '../models/models.dart';
import '../services/supabase_service.dart';

/// Acceso a canchas en Supabase (tabla `pichangol_canchas`). Todo es fail-safe:
/// si Supabase no está disponible o falla, devuelve vacío / no hace nada y la
/// app sigue con datos locales.
class CanchasRepo {
  static const _tabla = 'pichangol_canchas';

  static Future<List<Cancha>> fetchRemotas() async {
    if (!SupabaseService.disponible) return [];
    try {
      final rows = await SupabaseService.client.from(_tabla).select();
      return (rows as List)
          .map((r) => _fromRow(r as Map<String, dynamic>))
          .where((c) => !c.eliminada) // borrado lógico durable en la nube
          .toList();
    } catch (_) {
      return [];
    }
  }

  static Future<void> insertar(Cancha c) async {
    if (!SupabaseService.disponible) return;
    try {
      // upsert: si la cancha ya existía (p. ej. se re-registra una que estaba
      // borrada) la revive en vez de fallar por id duplicado.
      await SupabaseService.client.from(_tabla).upsert(_toRow(c));
    } catch (_) {
      // Reintento sin columnas nuevas (p. ej. `amenidades`/`superficie` aún no
      // migradas en la BD): así el guardado del resto no se pierde por una
      // columna faltante.
      try {
        await SupabaseService.client
            .from(_tabla)
            .upsert(_toRow(c, conAmenidades: false));
      } catch (_) {}
    }
  }

  /// Actualiza una cancha existente (edición del dueño). Fail-safe.
  static Future<void> actualizar(Cancha c) async {
    if (!SupabaseService.disponible) return;
    try {
      await SupabaseService.client
          .from(_tabla)
          .update(_toRow(c))
          .eq('id', c.id);
    } catch (_) {
      try {
        await SupabaseService.client
            .from(_tabla)
            .update(_toRow(c, conAmenidades: false))
            .eq('id', c.id);
      } catch (_) {}
    }
  }

  /// Borra una cancha de forma DURABLE en la nube. Usa borrado lógico
  /// (`eliminada = true`) en vez de DELETE físico: el DELETE suele estar
  /// bloqueado por RLS y, sobre todo, así el borrado sobrevive a reinstalar la
  /// app (no depende de la "lápida" local). Fail-safe.
  static Future<void> eliminar(String id) async {
    if (!SupabaseService.disponible) return;
    try {
      await SupabaseService.client
          .from(_tabla)
          .update({'eliminada': true}).eq('id', id);
    } catch (_) {}
  }

  /// Motivo del último fallo de [subirFoto], en texto legible para el dueño.
  /// Lo usa la UI para distinguir "sin red" de "bucket no configurado" en vez
  /// de mostrar siempre "revise su conexión".
  static String? ultimoErrorFoto;

  /// Sube una foto al bucket `canchas` y devuelve su URL pública. Si [sufijo]
  /// es null usa una ruta fija (portada, se sobreescribe); con [sufijo] crea
  /// rutas únicas para una galería. Requiere un bucket público `canchas`.
  /// En caso de fallo devuelve null y deja el motivo en [ultimoErrorFoto].
  static Future<String?> subirFoto(String canchaId, Uint8List bytes,
      {String? sufijo}) async {
    if (!SupabaseService.disponible) {
      ultimoErrorFoto = 'Supabase no está configurado en esta app.';
      return null;
    }
    try {
      final ruta = sufijo == null ? '$canchaId.jpg' : '$canchaId/$sufijo.jpg';
      final storage = SupabaseService.client.storage.from('canchas');
      await storage.uploadBinary(
        ruta,
        bytes,
        fileOptions: const FileOptions(upsert: true),
      );
      final base = storage.getPublicUrl(ruta);
      ultimoErrorFoto = null;
      return '$base?v=${DateTime.now().millisecondsSinceEpoch}';
    } catch (e) {
      ultimoErrorFoto = _motivoFoto(e);
      return null;
    }
  }

  /// Traduce el error de Storage a una pista accionable para el dueño.
  static String _motivoFoto(Object e) {
    final s = e.toString().toLowerCase();
    if (s.contains('not found') || s.contains('bucket')) {
      return 'Falta el bucket "canchas" en Supabase Storage (créalo público).';
    }
    if (s.contains('row-level') ||
        s.contains('policy') ||
        s.contains('unauthorized') ||
        s.contains('403') ||
        s.contains('permission')) {
      return 'El bucket "canchas" no permite subir fotos (falta la política de subida).';
    }
    if (s.contains('socket') ||
        s.contains('timeout') ||
        s.contains('connection') ||
        s.contains('failed host')) {
      return 'Sin conexión: revisa tu internet e inténtalo de nuevo.';
    }
    return 'No se pudo subir la foto. Detalle: $e';
  }

  static Map<String, dynamic> _toRow(Cancha c, {bool conAmenidades = true}) => {
        'id': c.id,
        'nombre': c.nombre,
        'club': c.club,
        'distrito': c.distrito.name,
        'deporte': c.deporte.name,
        'precio_hora': c.precioHora,
        'lat': c.ubicacion.latitude,
        'lng': c.ubicacion.longitude,
        'club_fundador': c.clubFundador,
        'digitalizada': c.digitalizada,
        'direccion': c.direccion,
        'registrada': c.registrada,
        'foto_url': c.fotoUrl,
        'fotos': c.fotos,
        'dueno': c.dueno,
        'verificada': c.verificada,
        'hora_apertura': c.horaApertura,
        'hora_cierre': c.horaCierre,
        'duracion_slot_min': c.duracionSlotMin,
        'eliminada': c.eliminada,
        if (conAmenidades) 'amenidades': c.amenidades,
        if (conAmenidades) 'superficie': c.superficie,
        // Columnas nuevas. Van bajo el mismo flag de retry: si la BD aún no las
        // tiene, el reintento las omite (la app conserva el valor local).
        if (conAmenidades)
          'deportes': c.deportesJugables.map((e) => e.name).toList(),
        if (conAmenidades) 'moneda': c.moneda,
        if (conAmenidades)
          'servicios_extra':
              c.serviciosExtra.map((s) => s.toJson()).toList(),
        if (conAmenidades) 'descuento_valle': c.descuentoValle,
        if (conAmenidades) 'barrio': c.barrio,
      };

  static Cancha _fromRow(Map<String, dynamic> r) => Cancha(
        id: r['id'].toString(),
        nombre: (r['nombre'] ?? 'Cancha') as String,
        club: (r['club'] ?? '') as String,
        distrito: _enumDistrito(r['distrito'] as String?),
        barrio: (r['barrio'] ?? '') as String,
        deporte: _enumDeporte(r['deporte'] as String?),
        deportes: (r['deportes'] as List?)
                ?.map((e) => deportePorNombre(e.toString()))
                .whereType<Deporte>()
                .toList() ??
            const [],
        precioHora: ((r['precio_hora'] ?? 100) as num).toDouble(),
        ubicacion: LatLng(
          ((r['lat'] ?? -12.108) as num).toDouble(),
          ((r['lng'] ?? -76.978) as num).toDouble(),
        ),
        clubFundador: (r['club_fundador'] ?? false) as bool,
        digitalizada: (r['digitalizada'] ?? true) as bool,
        direccion: r['direccion'] as String?,
        registrada: (r['registrada'] ?? true) as bool,
        fotoUrl: r['foto_url'] as String?,
        fotos: (r['fotos'] as List?)?.map((e) => e.toString()).toList() ??
            const [],
        dueno: (r['dueno'] ?? '') as String,
        verificada: (r['verificada'] ?? true) as bool,
        horaApertura: (r['hora_apertura'] ?? '07:00') as String,
        horaCierre: (r['hora_cierre'] ?? '23:00') as String,
        duracionSlotMin: ((r['duracion_slot_min'] ?? 60) as num).toInt(),
        eliminada: (r['eliminada'] ?? false) as bool,
        amenidades:
            (r['amenidades'] as List?)?.map((e) => e.toString()).toList() ??
                const [],
        superficie: (r['superficie'] ?? '') as String,
        moneda: (r['moneda'] ?? '') as String,
        serviciosExtra: ServicioExtra.listaDe(r['servicios_extra']),
        descuentoValle: ((r['descuento_valle'] ?? 0) as num).toInt(),
      );

  static Distrito _enumDistrito(String? s) {
    for (final d in Distrito.values) {
      if (d.name == s) return d;
    }
    return Distrito.sanBorja;
  }

  static Deporte _enumDeporte(String? s) {
    for (final d in Deporte.values) {
      if (d.name == s) return d;
    }
    return Deporte.futbol;
  }
}
