/// Flags de funciones (feature flags) para prender/apagar módulos completos sin
/// borrar código. Útil para el piloto: ocultar algo que aún no se comercializa.
///
/// Para REACTIVAR un módulo, poné su flag en `true` y listo (el código sigue
/// intacto en el repo).
library;

/// "Servicios Pichangol" (marketing: landing, community manager, suscripción).
/// Apagado durante el piloto → se ocultan TODOS sus accesos en la app (Mis
/// canchas, academia, crear/editar academia). El backend de marketing y la
/// pantalla `ServiciosScreen` quedan intactos; solo se quitan las entradas.
const bool kServiciosPichangolActivo = false;

/// Entorno del build, inyectado por el CI (`--dart-define=ENTORNO=dev|qas|prod`).
/// Vacío en un build local → se comporta como dev.
const String kEntorno = String.fromEnvironment('ENTORNO', defaultValue: 'dev');

/// ¿Es un APK de PRODUCCIÓN? Sirve para dejar fuera de la tienda lo que aún se
/// está probando, sin tener que acordarse de bajar un flag antes del corte.
const bool kEsProduccion = kEntorno == 'prod';

/// ENTRENADOR VIRTUAL (coach IA que analiza tu golpe en video).
/// Decisión del director (ago-2026): se sigue probando en QAS y NO sale a
/// producción todavía. Se ata al entorno del build en vez de a un booleano
/// suelto: así el APK de PROD lo oculta solo, sin depender de que alguien
/// recuerde apagarlo. Para llevarlo a producción, cambiar esta línea por
/// `true` (o quitar la condición) cuando el director lo autorice.
const bool kEntrenadorVirtualActivo = !kEsProduccion;
