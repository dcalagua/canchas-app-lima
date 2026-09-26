import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:geolocator/geolocator.dart';

import '../data/ubicacion_vivo_repo.dart';

/// Mantiene MI ubicación en tiempo real subiéndola cada pocos segundos mientras
/// dure la compartición, aunque salga del chat. Singleton: solo se comparte UN
/// hilo a la vez (como WhatsApp, que muestra una sola sesión activa por chat).
///
/// El widget de la burbuja escucha [activo] para pintar "Compartiendo… / Detener".
class UbicacionVivoService {
  UbicacionVivoService._();
  static final UbicacionVivoService instance = UbicacionVivoService._();

  static const _cada = Duration(seconds: 8);

  Timer? _timer;
  String _hilo = '';
  String _email = '';
  DateTime? _expira;

  /// Notifica a la UI cuando arranca/para una compartición (para pintar el
  /// estado y el botón "Detener").
  final ValueNotifier<bool> activo = ValueNotifier<bool>(false);

  /// ¿Estoy compartiendo AHORA en [hilo]?
  bool compartiendoEn(String hilo) =>
      _timer != null && _hilo == hilo && !_vencio;

  bool get _vencio =>
      _expira == null || !DateTime.now().isBefore(_expira!);

  DateTime? get expira => _expira;

  /// Arranca la compartición en vivo en [hilo] hasta [expira]. Sube un primer fix
  /// de una vez y luego cada [_cada]. Si ya había otra activa, la reemplaza.
  Future<void> iniciar({
    required String hilo,
    required String email,
    required DateTime expira,
  }) async {
    await detener(avisarBackend: false); // corta cualquier sesión previa
    _hilo = hilo;
    _email = email.trim().toLowerCase();
    _expira = expira;
    activo.value = true;
    await _tick(); // primer fix inmediato
    _timer = Timer.periodic(_cada, (_) => _tick());
  }

  Future<void> _tick() async {
    if (_vencio) {
      await detener();
      return;
    }
    try {
      final pos = await Geolocator.getCurrentPosition(
        desiredAccuracy: LocationAccuracy.high,
        timeLimit: const Duration(seconds: 8),
      );
      await UbicacionVivoRepo.actualizar(
        hilo: _hilo,
        email: _email,
        lat: pos.latitude,
        lng: pos.longitude,
        expira: _expira!,
      );
    } catch (_) {
      // Un fix perdido no corta la sesión; se reintenta en el próximo tick.
    }
  }

  /// Detiene la compartición. Por defecto avisa al backend (pone expira=now) para
  /// que el otro lado la vea "finalizada".
  Future<void> detener({bool avisarBackend = true}) async {
    _timer?.cancel();
    _timer = null;
    final h = _hilo, e = _email;
    _hilo = '';
    _email = '';
    _expira = null;
    activo.value = false;
    if (avisarBackend && h.isNotEmpty && e.isNotEmpty) {
      await UbicacionVivoRepo.detener(hilo: h, email: e);
    }
  }
}
