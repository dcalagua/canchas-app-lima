package pe.ebim.canchaslima.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

val VerdeCancha = Color(0xFF0E7C4A)
val VerdeClaro = Color(0xFF3DA86E)
val VerdeOscuro = Color(0xFF0A5C37)
val Arena = Color(0xFFE9A23B)   // pelota / horas valle
val FondoClaro = Color(0xFFF6F8F6)

private val LightColors = lightColorScheme(
    primary = VerdeCancha,
    onPrimary = Color.White,
    primaryContainer = VerdeClaro,
    onPrimaryContainer = Color.White,
    secondary = Arena,
    onSecondary = Color(0xFF3A2700),
    background = FondoClaro,
    surface = Color.White,
)

private val DarkColors = darkColorScheme(
    primary = VerdeClaro,
    onPrimary = Color.Black,
    secondary = Arena,
    background = Color(0xFF101411),
    surface = Color(0xFF1A201C),
)

@Composable
fun CanchasLimaTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    content: @Composable () -> Unit
) {
    MaterialTheme(
        colorScheme = if (darkTheme) DarkColors else LightColors,
        typography = Typography(),
        content = content
    )
}
