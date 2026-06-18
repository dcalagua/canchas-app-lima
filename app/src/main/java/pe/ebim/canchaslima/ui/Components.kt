package pe.ebim.canchaslima.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import pe.ebim.canchaslima.data.Deporte
import pe.ebim.canchaslima.data.EstadoReserva
import pe.ebim.canchaslima.ui.theme.Arena
import pe.ebim.canchaslima.ui.theme.VerdeCancha
import pe.ebim.canchaslima.ui.theme.VerdeClaro

/** Chip de etiqueta compacto. */
@Composable
fun EtiquetaChip(texto: String, fondo: Color, contenido: Color = Color.White) {
    Box(
        modifier = Modifier
            .clip(RoundedCornerShape(50))
            .background(fondo)
            .padding(horizontal = 10.dp, vertical = 4.dp)
    ) {
        Text(
            text = texto,
            color = contenido,
            style = MaterialTheme.typography.labelSmall,
            fontWeight = FontWeight.SemiBold
        )
    }
}

@Composable
fun ChipEstado(estado: EstadoReserva) {
    val fondo = when (estado) {
        EstadoReserva.NUEVA -> Arena
        EstadoReserva.CONFIRMADA -> VerdeCancha
        EstadoReserva.COMPLETADA -> VerdeClaro
        EstadoReserva.NO_SHOW -> Color(0xFFB3261E)
    }
    EtiquetaChip(estado.etiqueta, fondo)
}

@Composable
fun ChipDeporte(deporte: Deporte) {
    val fondo = if (deporte == Deporte.PADEL) Color(0xFF2D6CDF) else VerdeCancha
    EtiquetaChip(deporte.etiqueta, fondo)
}
