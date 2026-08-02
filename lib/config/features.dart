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
