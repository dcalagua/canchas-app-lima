package pe.ebim.canchaslima.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Card
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import pe.ebim.canchaslima.AppViewModel
import pe.ebim.canchaslima.data.EstadoReserva
import pe.ebim.canchaslima.data.SampleData
import pe.ebim.canchaslima.ui.theme.Arena
import pe.ebim.canchaslima.ui.theme.VerdeCancha

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ReportesScreen(vm: AppViewModel) {
    val canchasActivas = SampleData.canchasDelClubActivo().size
    val reservasApp = vm.reservas.filter { it.traidaPorApp }
    val ingresoApp = reservasApp
        .filter { it.estado != EstadoReserva.NO_SHOW }
        .sumOf { it.precio }
    val noShows = vm.reservas.count { it.estado == EstadoReserva.NO_SHOW }
    val totalConResultado = vm.reservas.count {
        it.estado == EstadoReserva.COMPLETADA || it.estado == EstadoReserva.NO_SHOW
    }.coerceAtLeast(1)
    val pctSinNoShow = ((totalConResultado - noShows) * 100) / totalConResultado

    val bloquesValle = vm.agenda.filter { it.esHoraValle }
    val valleLlenas = bloquesValle.count { it.reservaId != null }
    val pctValle = if (bloquesValle.isEmpty()) 0 else (valleLlenas * 100) / bloquesValle.size

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Reportes") },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.primary,
                    titleContentColor = Color.White
                )
            )
        }
    ) { padding ->
        Column(
            modifier = Modifier
                .padding(padding)
                .verticalScroll(rememberScrollState())
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp)
        ) {
            Text(
                "Resumen del mes",
                style = MaterialTheme.typography.titleLarge,
                fontWeight = FontWeight.Bold
            )
            Text(
                "Tu cuaderno, pero en tiempo real. Lo importante es lo que la app te suma.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )

            Row(horizontalArrangement = Arrangement.spacedBy(14.dp)) {
                KpiCard("Canchas activas", "$canchasActivas", "publicadas en la app", VerdeCancha, Modifier.weight(1f))
                KpiCard("Reservas por la app", "${reservasApp.size}", "este mes", Arena, Modifier.weight(1f))
            }
            Row(horizontalArrangement = Arrangement.spacedBy(14.dp)) {
                KpiCard("Ingreso vía app", "S/ $ingresoApp", "reservas nuevas", VerdeCancha, Modifier.weight(1f))
                KpiCard("Horas valle llenas", "$pctValle%", "$valleLlenas de ${bloquesValle.size} hoy", Arena, Modifier.weight(1f))
            }

            Card(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(16.dp)) {
                    Text("Anti no-show", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                    Spacer(Modifier.height(4.dp))
                    Text(
                        "$pctSinNoShow% de las reservas con seña llegaron a jugar. La seña con tarjeta reduce los plantones.",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }

            Card(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(16.dp)) {
                    Text("Club Fundador", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                    Spacer(Modifier.height(4.dp))
                    Text(
                        "Eres Club Fundador de San Borja: posición preferente en la app y condiciones que no se repiten. Cupos limitados por distrito.",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }
        }
    }
}

@Composable
private fun KpiCard(titulo: String, valor: String, sub: String, acento: Color, modifier: Modifier = Modifier) {
    Card(modifier = modifier) {
        Column(Modifier.padding(16.dp)) {
            Text(titulo, style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
            Spacer(Modifier.height(6.dp))
            Text(valor, style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold, color = acento)
            Spacer(Modifier.height(2.dp))
            Text(sub, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}
