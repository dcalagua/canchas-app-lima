package pe.ebim.canchaslima.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Card
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Lock
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import pe.ebim.canchaslima.AppViewModel
import pe.ebim.canchaslima.data.BloqueHorario
import pe.ebim.canchaslima.data.SampleData
import pe.ebim.canchaslima.ui.theme.Arena

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DisponibilidadScreen(vm: AppViewModel) {
    val canchas = SampleData.canchasDelClubActivo()
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Disponibilidad") },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.primary,
                    titleContentColor = Color.White
                )
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
                    "Abre las horas que quieres publicar en la app. Las mañanas (horas valle) son las que más conviene llenar.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
            items(canchas) { cancha ->
                val bloques = vm.agenda.filter { it.canchaId == cancha.id }
                Card(Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(16.dp)) {
                        Text(
                            cancha.nombre,
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.SemiBold
                        )
                        Spacer(Modifier.height(4.dp))
                        bloques.forEachIndexed { i, bloque ->
                            if (i > 0) HorizontalDivider()
                            FilaDisponibilidad(bloque) { vm.alternarDisponibilidad(bloque) }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun FilaDisponibilidad(bloque: BloqueHorario, onToggle: () -> Unit) {
    val ocupada = bloque.reservaId != null
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Text(
            bloque.hora,
            style = MaterialTheme.typography.bodyLarge,
            fontWeight = FontWeight.SemiBold,
            modifier = Modifier.width(64.dp)
        )
        Column(Modifier.weight(1f)) {
            Text(
                when {
                    ocupada -> "Reservada"
                    bloque.esHoraValle -> "Hora valle"
                    else -> "Horario regular"
                },
                style = MaterialTheme.typography.bodyMedium
            )
            if (bloque.esHoraValle && !ocupada) {
                Text(
                    "Prioriza abrirla",
                    style = MaterialTheme.typography.labelSmall,
                    color = Arena,
                    fontWeight = FontWeight.SemiBold
                )
            }
        }
        if (ocupada) {
            Icon(Icons.Filled.Lock, contentDescription = "Reservada", tint = MaterialTheme.colorScheme.primary)
        } else {
            Switch(checked = bloque.disponible, onCheckedChange = { onToggle() })
        }
    }
}
