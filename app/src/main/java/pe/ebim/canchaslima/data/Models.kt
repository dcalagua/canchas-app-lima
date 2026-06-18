package pe.ebim.canchaslima.data

import com.google.android.gms.maps.model.LatLng

/** Distritos del piloto (densidad geográfica antes que cobertura amplia). */
enum class Distrito(val etiqueta: String) {
    SAN_BORJA("San Borja"),
    SURCO("Surco"),
    LA_MOLINA("La Molina")
}

enum class Deporte(val etiqueta: String) {
    TENIS("Tenis"),
    PADEL("Pádel")
}

/** Una cancha en el marketplace. */
data class Cancha(
    val id: String,
    val nombre: String,
    val club: String,
    val distrito: Distrito,
    val deporte: Deporte,
    val precioHora: Int,            // soles por hora
    val ubicacion: LatLng,
    val clubFundador: Boolean,      // sello "Club Fundador" de su distrito
    val digitalizada: Boolean       // false = aún en cuaderno/WhatsApp (objetivo prioritario)
)

enum class EstadoReserva(val etiqueta: String) {
    NUEVA("Nueva"),            // entró por la app, sin confirmar
    CONFIRMADA("Confirmada"),  // seña pagada
    COMPLETADA("Completada"),
    NO_SHOW("No-show")
}

/** Una reserva. `traidaPorApp` distingue una reserva NUEVA de un cliente de siempre. */
data class Reserva(
    val id: String,
    val canchaId: String,
    val jugador: String,
    val nivel: String,             // ej. "Intermedio 3.5" (ángulo social / por nivel)
    val dia: String,               // ej. "Hoy", "Mañana", "Lun 22"
    val horaInicio: String,        // "07:00"
    val horaFin: String,           // "08:00"
    val estado: EstadoReserva,
    val traidaPorApp: Boolean,     // true = reserva nueva (genera comisión en Fase 2)
    val precio: Int,
    val sena: Int                  // monto de seña/garantía con tarjeta (anti no-show)
)

/** Un bloque horario de una cancha en la agenda de hoy. */
data class BloqueHorario(
    val canchaId: String,
    val hora: String,              // "07:00"
    val esHoraValle: Boolean,      // mañanas / inicios de semana = el oro de la Fase 1
    val disponible: Boolean,       // el dueño la abrió en la app
    val reservaId: String?         // ocupada si != null
)
