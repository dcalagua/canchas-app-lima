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

/// ZONA DE PRUEBAS de Ajustes: "Dejar en virgen", "Empezar de cero", "Depurar
/// academias" y los simuladores de llamada. Son herramientas del PILOTO: borran
/// datos sin vuelta atrás y "Depurar academias" alcanza a las academias de
/// OTROS dueños (además de mostrar sus correos), así que no pueden viajar en el
/// APK de la tienda, donde cualquiera lo instala. Se ata al entorno para que
/// producción las oculte sola; `--dart-define=OCULTAR_PRUEBAS=1` permite
/// apagarlas también en dev/QAS.
///
/// Lo que un usuario de producción SÍ necesita sigue disponible: borrar su
/// cuenta se hace en Perfil → "Eliminar mi cuenta", y el diagnóstico de push
/// (sólo lectura) queda fuera de esta zona para poder dar soporte.
const bool kHerramientasPruebaActivas = !kEsProduccion && !_kOcultarPruebas;

const bool _kOcultarPruebas =
    String.fromEnvironment('OCULTAR_PRUEBAS', defaultValue: '0') == '1';
