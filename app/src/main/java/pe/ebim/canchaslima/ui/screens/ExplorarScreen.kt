package pe.ebim.canchaslima.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.google.android.gms.maps.model.BitmapDescriptorFactory
import com.google.android.gms.maps.model.CameraPosition
import com.google.maps.android.compose.GoogleMap
import com.google.maps.android.compose.MapProperties
import com.google.maps.android.compose.Marker
import com.google.maps.android.compose.MarkerState
import com.google.maps.android.compose.rememberCameraPositionState
import pe.ebim.canchaslima.data.Deporte
import pe.ebim.canchaslima.data.SampleData

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ExplorarScreen() {
    val camara = rememberCameraPositionState {
        position = CameraPosition.fromLatLngZoom(SampleData.centroPiloto, 12.5f)
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Explorar canchas") },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.primary,
                    titleContentColor = Color.White
                )
            )
        }
    ) { padding ->
        Box(Modifier.padding(padding).fillMaxSize()) {
            GoogleMap(
                modifier = Modifier.fillMaxSize(),
                cameraPositionState = camara,
                properties = MapProperties(isMyLocationEnabled = false)
            ) {
                SampleData.canchas.forEach { cancha ->
                    val hue = if (cancha.deporte == Deporte.PADEL)
                        BitmapDescriptorFactory.HUE_AZURE
                    else
                        BitmapDescriptorFactory.HUE_GREEN
                    Marker(
                        state = MarkerState(position = cancha.ubicacion),
                        title = "${cancha.nombre} · S/ ${cancha.precioHora}/h",
                        snippet = "${cancha.club} · ${cancha.deporte.etiqueta} · ${cancha.distrito.etiqueta}" +
                            if (cancha.clubFundador) " · Club Fundador" else "",
                        icon = BitmapDescriptorFactory.defaultMarker(hue)
                    )
                }
            }

            Leyenda(
                modifier = Modifier
                    .align(Alignment.BottomCenter)
                    .padding(16.dp)
            )
        }
    }
}

@Composable
private fun Leyenda(modifier: Modifier = Modifier) {
    Surface(
        modifier = modifier,
        shape = RoundedCornerShape(12.dp),
        tonalElevation = 3.dp,
        shadowElevation = 6.dp,
        color = MaterialTheme.colorScheme.surface
    ) {
        Column(Modifier.padding(horizontal = 14.dp, vertical = 10.dp)) {
            Text(
                "Zona piloto: San Borja · Surco · La Molina",
                style = MaterialTheme.typography.labelMedium,
                fontWeight = FontWeight.SemiBold
            )
            Spacer(Modifier.size(6.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                PuntoLeyenda(Color(0xFF2D6CDF), "Pádel")
                PuntoLeyenda(Color(0xFF0E7C4A), "Tenis")
            }
        }
    }
}

@Composable
private fun PuntoLeyenda(color: Color, texto: String) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Box(Modifier.size(12.dp).clip(RoundedCornerShape(50)).background(color))
        Spacer(Modifier.width(6.dp))
        Text(texto, style = MaterialTheme.typography.labelSmall)
    }
}
