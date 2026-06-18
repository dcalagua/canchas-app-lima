package pe.ebim.canchaslima.data

import com.google.android.gms.maps.model.LatLng

/**
 * Datos de demostración en memoria (sin backend todavía).
 * Pensados para la DEMO en la cancha: el dueño toca el panel y "ve entrar una reserva".
 *
 * El club que inicia sesión es "Club Raqueta San Borja" y administra sus propias canchas
 * (canchas con club == "Club Raqueta San Borja"). El resto pueblan el mapa del explorador.
 */
object SampleData {

    const val CLUB_ACTIVO = "Club Raqueta San Borja"

    val canchas: List<Cancha> = listOf(
        // --- Canchas del club que inicia sesión (panel del dueño) ---
        Cancha(
            id = "c1", nombre = "Cancha Central", club = CLUB_ACTIVO,
            distrito = Distrito.SAN_BORJA, deporte = Deporte.TENIS, precioHora = 70,
            ubicacion = LatLng(-12.1086, -76.9990), clubFundador = true, digitalizada = true
        ),
        Cancha(
            id = "c2", nombre = "Cancha 2 (Arcilla)", club = CLUB_ACTIVO,
            distrito = Distrito.SAN_BORJA, deporte = Deporte.TENIS, precioHora = 65,
            ubicacion = LatLng(-12.1090, -76.9985), clubFundador = true, digitalizada = true
        ),
        Cancha(
            id = "c3", nombre = "Pádel 1", club = CLUB_ACTIVO,
            distrito = Distrito.SAN_BORJA, deporte = Deporte.PADEL, precioHora = 90,
            ubicacion = LatLng(-12.1082, -76.9994), clubFundador = true, digitalizada = true
        ),

        // --- Otras canchas de la zona piloto (pipeline / mapa del explorador) ---
        Cancha(
            id = "c4", nombre = "Cancha Tenis Aurora", club = "Club Aurora",
            distrito = Distrito.SAN_BORJA, deporte = Deporte.TENIS, precioHora = 60,
            ubicacion = LatLng(-12.1110, -77.0020), clubFundador = false, digitalizada = false
        ),
        Cancha(
            id = "c5", nombre = "Pádel Surco Park", club = "Surco Pádel Park",
            distrito = Distrito.SURCO, deporte = Deporte.PADEL, precioHora = 95,
            ubicacion = LatLng(-12.1355, -76.9925), clubFundador = false, digitalizada = false
        ),
        Cancha(
            id = "c6", nombre = "Cancha 1 - Los Cedros", club = "Club Los Cedros",
            distrito = Distrito.SURCO, deporte = Deporte.TENIS, precioHora = 68,
            ubicacion = LatLng(-12.1402, -76.9880), clubFundador = false, digitalizada = false
        ),
        Cancha(
            id = "c7", nombre = "Pádel Molina Indoor", club = "Molina Indoor",
            distrito = Distrito.LA_MOLINA, deporte = Deporte.PADEL, precioHora = 100,
            ubicacion = LatLng(-12.0795, -76.9480), clubFundador = false, digitalizada = false
        ),
        Cancha(
            id = "c8", nombre = "Tenis La Planicie", club = "La Planicie Tenis",
            distrito = Distrito.LA_MOLINA, deporte = Deporte.TENIS, precioHora = 75,
            ubicacion = LatLng(-12.0760, -76.9410), clubFundador = false, digitalizada = false
        ),
        Cancha(
            id = "c9", nombre = "Pádel Camino Real", club = "Camino Real Club",
            distrito = Distrito.LA_MOLINA, deporte = Deporte.PADEL, precioHora = 92,
            ubicacion = LatLng(-12.0820, -76.9445), clubFundador = false, digitalizada = false
        )
    )

    /** Centro aproximado del eje piloto San Borja–Surco–La Molina. */
    val centroPiloto = LatLng(-12.108, -76.978)

    val reservas: List<Reserva> = listOf(
        Reserva("r1", "c1", "Carlos Mendoza", "Intermedio 3.5", "Hoy", "07:00", "08:00",
            EstadoReserva.CONFIRMADA, traidaPorApp = true, precio = 70, sena = 20),
        Reserva("r2", "c3", "Lucía Ferrer", "Avanzado", "Hoy", "09:00", "10:00",
            EstadoReserva.NUEVA, traidaPorApp = true, precio = 90, sena = 25),
        Reserva("r3", "c2", "Equipo Galván (de siempre)", "—", "Hoy", "18:00", "19:00",
            EstadoReserva.CONFIRMADA, traidaPorApp = false, precio = 65, sena = 0),
        Reserva("r4", "c1", "Andrea Salas", "Intermedio 4.0", "Mañana", "08:00", "09:00",
            EstadoReserva.NUEVA, traidaPorApp = true, precio = 70, sena = 20),
        Reserva("r5", "c3", "Diego Rojas", "Principiante", "Mañana", "10:00", "11:00",
            EstadoReserva.CONFIRMADA, traidaPorApp = true, precio = 90, sena = 25),
        Reserva("r6", "c2", "Marta Pinto", "Intermedio 3.0", "Ayer", "07:00", "08:00",
            EstadoReserva.COMPLETADA, traidaPorApp = true, precio = 65, sena = 20),
        Reserva("r7", "c1", "Jorge Li", "Avanzado", "Ayer", "20:00", "21:00",
            EstadoReserva.NO_SHOW, traidaPorApp = true, precio = 70, sena = 20)
    )

    /** Agenda de HOY para las canchas del club activo. Mañanas = horas valle. */
    val agendaHoy: List<BloqueHorario> = run {
        val horas = listOf("07:00", "08:00", "09:00", "10:00", "11:00",
            "16:00", "17:00", "18:00", "19:00", "20:00")
        val ocupadasHoy = reservas.filter { it.dia == "Hoy" }
        canchasDelClubActivo().flatMap { cancha ->
            horas.map { hora ->
                val esValle = hora < "12:00"
                val reserva = ocupadasHoy.firstOrNull { it.canchaId == cancha.id && it.horaInicio == hora }
                BloqueHorario(
                    canchaId = cancha.id,
                    hora = hora,
                    esHoraValle = esValle,
                    disponible = true,
                    reservaId = reserva?.id
                )
            }
        }
    }

    fun canchasDelClubActivo(): List<Cancha> = canchas.filter { it.club == CLUB_ACTIVO }

    fun canchaPorId(id: String): Cancha? = canchas.firstOrNull { it.id == id }
}
