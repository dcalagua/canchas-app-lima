package pe.ebim.canchaslima

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import pe.ebim.canchaslima.data.BloqueHorario
import pe.ebim.canchaslima.data.EstadoReserva
import pe.ebim.canchaslima.data.Reserva
import pe.ebim.canchaslima.data.SampleData

/**
 * Estado de la app. Sin backend todavía: arranca de [SampleData] y muta en memoria.
 * Pensado para Fase 1 (panel del dueño) + demo en la cancha.
 */
class AppViewModel : ViewModel() {

    var sesionIniciada by mutableStateOf(false)
        private set

    var nombreClub by mutableStateOf(SampleData.CLUB_ACTIVO)
        private set

    val reservas = mutableStateListOf<Reserva>().apply { addAll(SampleData.reservas) }
    val agenda = mutableStateListOf<BloqueHorario>().apply { addAll(SampleData.agendaHoy) }

    private var contadorDemo = 1

    fun iniciarSesion(club: String) {
        nombreClub = club.ifBlank { SampleData.CLUB_ACTIVO }
        sesionIniciada = true
    }

    fun cerrarSesion() {
        sesionIniciada = false
    }

    /** Abre/cierra la disponibilidad de un bloque (lo que el dueño publica en la app). */
    fun alternarDisponibilidad(bloque: BloqueHorario) {
        if (bloque.reservaId != null) return // ocupado: no se toca
        val i = agenda.indexOfFirst { it.canchaId == bloque.canchaId && it.hora == bloque.hora }
        if (i >= 0) agenda[i] = agenda[i].copy(disponible = !agenda[i].disponible)
    }

    /**
     * Simula que ENTRA una reserva nueva por la app en un bloque valle libre.
     * Es el momento "mágico" del pitch de demo: que el dueño la vea entrar en vivo.
     */
    fun simularReservaEntrante(): String? {
        val libreValle = agenda.firstOrNull {
            it.reservaId == null && it.disponible && it.esHoraValle
        } ?: agenda.firstOrNull { it.reservaId == null && it.disponible } ?: return null

        val cancha = SampleData.canchaPorId(libreValle.canchaId) ?: return null
        val nueva = Reserva(
            id = "demo${contadorDemo++}",
            canchaId = cancha.id,
            jugador = "Reserva por la app",
            nivel = "Intermedio 3.5",
            dia = "Hoy",
            horaInicio = libreValle.hora,
            horaFin = siguienteHora(libreValle.hora),
            estado = EstadoReserva.NUEVA,
            traidaPorApp = true,
            precio = cancha.precioHora,
            sena = (cancha.precioHora * 0.3).toInt()
        )
        reservas.add(0, nueva)
        val i = agenda.indexOf(libreValle)
        if (i >= 0) agenda[i] = libreValle.copy(reservaId = nueva.id)
        return "${cancha.nombre} · ${nueva.horaInicio} · +S/ ${nueva.precio}"
    }

    private fun siguienteHora(hora: String): String {
        val h = hora.substringBefore(":").toIntOrNull() ?: return hora
        return "%02d:00".format(h + 1)
    }
}
