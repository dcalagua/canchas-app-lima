import 'dart:convert';

import 'package:sqflite/sqflite.dart';

import '../models/mensaje.dart';

/// Caché LOCAL device-first (SQLite vía sqflite). Guarda en el teléfono los
/// mensajes recientes de cada hilo y la lista de conversaciones del inbox, para
/// PINTAR AL INSTANTE al abrir (aunque Android haya matado la app) y luego
/// sincronizar lo nuevo desde Supabase. Todo fail-safe: si algo falla, la app
/// sigue leyendo del backend como siempre.
class DbLocal {
  static Database? _db;

  static Future<Database?> _abrir() async {
    if (_db != null) return _db;
    try {
      final base = await getDatabasesPath();
      _db = await openDatabase(
        '$base/pichangol_cache.db',
        version: 1,
        onCreate: (db, _) async {
          await db.execute(
              'CREATE TABLE cache_mensajes (id TEXT PRIMARY KEY, hilo TEXT, creado TEXT, json TEXT)');
          await db.execute(
              'CREATE INDEX ix_cm_hilo ON cache_mensajes (hilo, creado)');
          await db.execute(
              'CREATE TABLE cache_convs (email TEXT, hilo TEXT, cuando TEXT, json TEXT, PRIMARY KEY (email, hilo))');
        },
      );
      return _db;
    } catch (_) {
      return null; // sin caché local: la app sigue con el backend
    }
  }

  // ── Mensajes de un hilo ────────────────────────────────────────────────────

  /// Reemplaza la caché del hilo con [msgs] (la ventana reciente que se muestra).
  static Future<void> guardarMensajes(String hilo, List<Mensaje> msgs) async {
    final db = await _abrir();
    if (db == null || hilo.isEmpty) return;
    try {
      await db.transaction((txn) async {
        await txn.delete('cache_mensajes', where: 'hilo = ?', whereArgs: [hilo]);
        final batch = txn.batch();
        for (final m in msgs) {
          batch.insert(
              'cache_mensajes',
              {
                'id': m.id,
                'hilo': m.hilo,
                'creado': m.creado.toIso8601String(),
                'json': jsonEncode(m.toCache()),
              },
              conflictAlgorithm: ConflictAlgorithm.replace);
        }
        await batch.commit(noResult: true);
      });
    } catch (_) {}
  }

  /// Últimos [limite] mensajes cacheados de un hilo, en orden cronológico.
  static Future<List<Mensaje>> leerMensajes(String hilo,
      {int limite = 50}) async {
    final db = await _abrir();
    if (db == null || hilo.isEmpty) return const [];
    try {
      final rows = await db.query('cache_mensajes',
          columns: ['json'],
          where: 'hilo = ?',
          whereArgs: [hilo],
          orderBy: 'creado DESC',
          limit: limite);
      final l = rows
          .map((r) =>
              Mensaje.fromRow(jsonDecode(r['json'] as String) as Map<String, dynamic>))
          .toList();
      return l.reversed.toList(); // cronológico (más nuevo abajo)
    } catch (_) {
      return const [];
    }
  }

  // ── Conversaciones del inbox ───────────────────────────────────────────────

  /// Reemplaza la caché del inbox del usuario [email] con [convs] (cada uno es el
  /// JSON de una conversación + su hilo y fecha para ordenar).
  static Future<void> guardarConvs(
      String email, List<Map<String, dynamic>> convs) async {
    final db = await _abrir();
    if (db == null || email.isEmpty) return;
    try {
      await db.transaction((txn) async {
        await txn.delete('cache_convs', where: 'email = ?', whereArgs: [email]);
        final batch = txn.batch();
        for (final c in convs) {
          batch.insert(
              'cache_convs',
              {
                'email': email,
                'hilo': (c['hilo'] ?? '').toString(),
                'cuando': (c['cuando'] ?? '').toString(),
                'json': jsonEncode(c),
              },
              conflictAlgorithm: ConflictAlgorithm.replace);
        }
        await batch.commit(noResult: true);
      });
    } catch (_) {}
  }

  /// Conversaciones cacheadas del inbox del usuario, más nuevas primero.
  static Future<List<Map<String, dynamic>>> leerConvs(String email) async {
    final db = await _abrir();
    if (db == null || email.isEmpty) return const [];
    try {
      final rows = await db.query('cache_convs',
          columns: ['json'],
          where: 'email = ?',
          whereArgs: [email],
          orderBy: 'cuando DESC');
      return rows
          .map((r) => jsonDecode(r['json'] as String) as Map<String, dynamic>)
          .toList();
    } catch (_) {
      return const [];
    }
  }
}
