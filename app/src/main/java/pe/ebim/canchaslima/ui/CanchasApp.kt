package pe.ebim.canchaslima.ui

import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ListAlt
import androidx.compose.material.icons.filled.BarChart
import androidx.compose.material.icons.filled.CalendarMonth
import androidx.compose.material.icons.filled.Map
import androidx.compose.material.icons.filled.Schedule
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.navigation.NavDestination.Companion.hierarchy
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import pe.ebim.canchaslima.AppViewModel
import pe.ebim.canchaslima.ui.screens.AgendaScreen
import pe.ebim.canchaslima.ui.screens.DisponibilidadScreen
import pe.ebim.canchaslima.ui.screens.ExplorarScreen
import pe.ebim.canchaslima.ui.screens.LoginScreen
import pe.ebim.canchaslima.ui.screens.ReportesScreen
import pe.ebim.canchaslima.ui.screens.ReservasScreen

private enum class Destino(val ruta: String, val etiqueta: String, val icono: ImageVector) {
    AGENDA("agenda", "Agenda", Icons.Filled.CalendarMonth),
    DISPONIBILIDAD("disponibilidad", "Horarios", Icons.Filled.Schedule),
    RESERVAS("reservas", "Reservas", Icons.AutoMirrored.Filled.ListAlt),
    REPORTES("reportes", "Reportes", Icons.Filled.BarChart),
    EXPLORAR("explorar", "Explorar", Icons.Filled.Map)
}

@Composable
fun CanchasApp(vm: AppViewModel) {
    if (!vm.sesionIniciada) {
        LoginScreen(onIngresar = { vm.iniciarSesion(it) })
        return
    }

    val navController = rememberNavController()
    val backStack by navController.currentBackStackEntryAsState()
    val rutaActual = backStack?.destination

    Scaffold(
        bottomBar = {
            NavigationBar {
                Destino.entries.forEach { destino ->
                    val seleccionado = rutaActual?.hierarchy?.any { it.route == destino.ruta } == true
                    NavigationBarItem(
                        selected = seleccionado,
                        onClick = {
                            navController.navigate(destino.ruta) {
                                popUpTo(navController.graph.findStartDestination().id) { saveState = true }
                                launchSingleTop = true
                                restoreState = true
                            }
                        },
                        icon = { Icon(destino.icono, contentDescription = destino.etiqueta) },
                        label = { Text(destino.etiqueta) }
                    )
                }
            }
        }
    ) { padding ->
        NavHost(
            navController = navController,
            startDestination = Destino.AGENDA.ruta,
            modifier = Modifier.padding(padding)
        ) {
            composable(Destino.AGENDA.ruta) { AgendaScreen(vm) }
            composable(Destino.DISPONIBILIDAD.ruta) { DisponibilidadScreen(vm) }
            composable(Destino.RESERVAS.ruta) { ReservasScreen(vm) }
            composable(Destino.REPORTES.ruta) { ReportesScreen(vm) }
            composable(Destino.EXPLORAR.ruta) { ExplorarScreen() }
        }
    }
}
