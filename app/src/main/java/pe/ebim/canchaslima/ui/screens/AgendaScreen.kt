package pe.ebim.canchaslima.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Bolt
import androidx.compose.material3.Card
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExtendedFloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.launch
import pe.ebim.canchaslima.AppViewModel
import pe.ebim.canchaslima.data.BloqueHorario
import pe.ebim.canchaslima.data.SampleData
import pe.ebim.canchaslima.ui.theme.Arena
import pe.ebim.canchaslima.ui.theme.VerdeCancha

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AgendaScreen(vm: AppViewModel) {
    val snackbar = remember { SnackbarHostState() }
    val scope = rememberCoroutineScope()
    val canchas = SampleData.canchasDelClubActivo()

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Agenda de hoy") },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.primary,
                    titleContentColor = Color.White
                )
            )
        },
        snackbarHost = { SnackbarHost(snackbar) },
        floatingActionButton = {
            ExtendedFloatingActionButton(
                onClick = {
                    val resultado = vm.simularReservaEntrante()
                    scope.launch {
                        snackbar.showSnackbar(
                            if (resultado != null) "🎾 ¡Entró una reserva! $resultado"
                            else "No quedan horas libres abiertas"
                        )
                    }
                },
                icon = { Icon(Icons.Filled.Bolt, contentDescription = null) },
                text = { Text("Simular reserva") }
            )
        }
    ) { padding ->
        LazyColumn(
            modifier = Modifier.padding(padding),
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            item {
                Text(
                    vm.nombreClub,
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold
                )
                Text(
                    "Toca “Simular reserva” en la demo para que el dueño la vea entrar.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
                Spacer(Modifier.height(4.dp))
                LeyendaAgenda()
            }
            items(canchas) { cancha ->
                val bloques = vm.agenda.filter { it.canchaId == cancha.id }
                CanchaAgendaCard(cancha.nombre, bloques)
            }
        }
    }
}

@Composable
private fun LeyendaAgenda() {
    Row(
        horizontalArrangement = Arrangement.spacedBy(16.dp),
        verticalAlignment = Alignment.CenterVertically,
        modifier = Modifier.padding(top = 6.dp)
    ) {
        Punto(VerdeCancha, "Reservada")
        Punto(Arena, "Hora valle libre")
        Punto(Color(0xFFD7E3DB), "Libre")
    }
}

@Composable
private fun Punto(color: Color, texto: String) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Box(Modifier.size(12.dp).clip(RoundedCornerShape(50)).background(color))
        Spacer(Modifier.width(6.dp))
        Text(texto, style = MaterialTheme.typography.labelSmall)
    }
}

@Composable
private fun CanchaAgendaCard(nombre: String, bloques: List<BloqueHorario>) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp)) {
            Text(nombre, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
            Spacer(Modifier.height(10.dp))
            bloques.forEach { bloque ->
                BloqueFila(bloque)
                Spacer(Modifier.height(8.dp))
            }
        }
    }
}

@Composable
private fun BloqueFila(bloque: BloqueHorario) {
    val ocupada = bloque.reservaId != null
    val reserva = bloque.reservaId?.let { id -> SampleData.reservas.firstOrNull { it.id == id } }
    val fondo = when {
        ocupada -> VerdeCancha
        bloque.esHoraValle -> Arena
        else -> Color(0xFFD7E3DB)
    }
    val contenido = if (ocupada || bloque.esHoraValle) Color.White else Color(0xFF20302A)

    Row(verticalAlignment = Alignment.CenterVertically) {
        Box(
            modifier = Modifier
                .width(64.dp)
                .height(36.dp)
                .clip(RoundedCornerShape(8.dp))
                .background(fondo),
            contentAlignment = Alignment.Center
        ) {
            Text(bloque.hora, color = contenido, fontWeight = FontWeight.SemiBold)
        }
        Spacer(Modifier.width(12.dp))
        Column {
            Text(
                when {
                    ocupada -> reserva?.jugador ?: "Reservada"
                    bloque.esHoraValle -> "Hora valle libre — ¡llénala!"
                    else -> "Libre"
                },
                style = MaterialTheme.typography.bodyMedium,
                fontWeight = if (ocupada) FontWeight.SemiBold else FontWeight.Normal
            )
            if (ocupada && reserva != null) {
                Text(
                    (if (reserva.traidaPorApp) "Por la app · " else "Cliente de siempre · ") +
                        "${reserva.horaInicio}–${reserva.horaFin}",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        }
    }
}
