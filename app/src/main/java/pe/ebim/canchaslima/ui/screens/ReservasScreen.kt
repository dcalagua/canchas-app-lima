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
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CreditCard
import androidx.compose.material3.Card
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import pe.ebim.canchaslima.AppViewModel
import pe.ebim.canchaslima.data.Reserva
import pe.ebim.canchaslima.data.SampleData
import pe.ebim.canchaslima.ui.ChipEstado
import pe.ebim.canchaslima.ui.EtiquetaChip
import pe.ebim.canchaslima.ui.theme.Arena
import pe.ebim.canchaslima.ui.theme.VerdeCancha

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ReservasScreen(vm: AppViewModel) {
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Reservas") },
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
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            item {
                val nuevas = vm.reservas.count { it.traidaPorApp }
                Text(
                    "$nuevas reservas traídas por la app. Solo estas generan comisión en Fase 2 — tus clientes de siempre nunca.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
            items(vm.reservas) { reserva -> ReservaCard(reserva) }
        }
    }
}

@Composable
private fun ReservaCard(reserva: Reserva) {
    val cancha = SampleData.canchaPorId(reserva.canchaId)
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    reserva.jugador,
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.SemiBold
                )
                ChipEstado(reserva.estado)
            }
            Spacer(Modifier.height(2.dp))
            Text(
                "${cancha?.nombre ?: "Cancha"} · ${reserva.dia} ${reserva.horaInicio}–${reserva.horaFin}",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
            if (reserva.nivel != "—") {
                Text(
                    "Nivel: ${reserva.nivel}",
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
            Spacer(Modifier.height(10.dp))
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                if (reserva.traidaPorApp) {
                    EtiquetaChip("Reserva nueva", VerdeCancha)
                } else {
                    EtiquetaChip("Cliente de siempre", Color(0xFF6B7B72))
                }
                if (reserva.sena > 0) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(
                            Icons.Filled.CreditCard,
                            contentDescription = null,
                            tint = Arena,
                            modifier = Modifier.height(18.dp)
                        )
                        Spacer(Modifier.width(4.dp))
                        Text(
                            "Seña S/ ${reserva.sena}",
                            style = MaterialTheme.typography.labelMedium,
                            color = Arena,
                            fontWeight = FontWeight.SemiBold
                        )
                    }
                }
                Spacer(Modifier.weight(1f))
                Text(
                    "S/ ${reserva.precio}",
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.primary
                )
            }
        }
    }
}
