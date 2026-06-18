package pe.ebim.canchaslima

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.lifecycle.viewmodel.compose.viewModel
import pe.ebim.canchaslima.ui.CanchasApp
import pe.ebim.canchaslima.ui.theme.CanchasLimaTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            CanchasLimaTheme {
                val vm: AppViewModel = viewModel()
                CanchasApp(vm)
            }
        }
    }
}
