package pe.ebim.canchas_lima

import android.app.Notification
import android.content.Context
import android.content.SharedPreferences
import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

/**
 * YAPE AUTOMÁTICO (fase 2 del Plan Academia, 10-oct-2026).
 *
 * Lee SOLO las notificaciones de los paquetes de Yape que el backend indica
 * (`yape_paquetes` en la torre) y las manda tal cual (título + texto) a
 * `POST /academias/yape/notificacion` con el token del dispositivo. El backend
 * lee monto + código de seguridad y confirma el pago que el alumno reportó.
 * Todo lo demás (chats, otras apps) se ignora aquí mismo: nunca sale del
 * teléfono. Sin red, la notificación queda en cola (máx. 50) y se reintenta
 * con la siguiente o cuando el app lo pide.
 *
 * Lo configura Dart por el MethodChannel `pichangol/yape_auto`
 * (MainActivity → [YapeAuto.configurar]). Este archivo lo copia
 * `tool/configure_platforms.py` al proyecto Android que arma el CI.
 */
class YapeListener : NotificationListenerService() {

    override fun onListenerConnected() {
        super.onListenerConnected()
        YapeAuto.enviarPendientes(applicationContext)
    }

    override fun onNotificationPosted(sbn: StatusBarNotification?) {
        val n = sbn ?: return
        val ctx = applicationContext
        val prefs = YapeAuto.prefs(ctx)
        if (!prefs.getBoolean("activo", false)) return
        val paquetes = (prefs.getString("paquetes", "") ?: "").split(",").map { it.trim() }.filter { it.isNotEmpty() }
        if (n.packageName !in paquetes) return
        val extras = n.notification?.extras ?: return
        val titulo = extras.getCharSequence(Notification.EXTRA_TITLE)?.toString() ?: ""
        val big = extras.getCharSequence(Notification.EXTRA_BIG_TEXT)?.toString() ?: ""
        val corto = extras.getCharSequence(Notification.EXTRA_TEXT)?.toString() ?: ""
        val texto = if (big.length >= corto.length) big else corto
        if (titulo.isBlank() && texto.isBlank()) return
        val item = JSONObject()
            .put("paquete", n.packageName)
            .put("titulo", titulo.take(200))
            .put("texto", texto.take(500))
            .put("recibida_ms", n.postTime)
        YapeAuto.encolar(ctx, item)
        YapeAuto.enviarPendientes(ctx)
    }
}

object YapeAuto {
    private const val MAX_COLA = 50
    private val candado = Any()
    @Volatile private var enviando = false

    fun prefs(ctx: Context): SharedPreferences =
        ctx.getSharedPreferences("pichangol_yape", Context.MODE_PRIVATE)

    fun configurar(ctx: Context, url: String, appKey: String, email: String, token: String,
                   paquetes: List<String>, activo: Boolean) {
        val e = prefs(ctx).edit()
            .putString("url", url.trimEnd('/'))
            .putString("app_key", appKey)
            .putString("email", email.trim().lowercase())
            .putString("paquetes", paquetes.joinToString(","))
            .putBoolean("activo", activo)
        if (token.isNotEmpty()) e.putString("token", token)
        if (!activo) e.remove("token").remove("cola")
        e.apply()
    }

    fun pendientes(ctx: Context): Int = try {
        JSONArray(prefs(ctx).getString("cola", "[]")).length()
    } catch (_: Exception) { 0 }

    fun encolar(ctx: Context, item: JSONObject) {
        synchronized(candado) {
            val p = prefs(ctx)
            val cola = try { JSONArray(p.getString("cola", "[]")) } catch (_: Exception) { JSONArray() }
            cola.put(item)
            val recortada = JSONArray()
            val desde = maxOf(0, cola.length() - MAX_COLA)
            for (i in desde until cola.length()) recortada.put(cola.get(i))
            p.edit().putString("cola", recortada.toString()).apply()
        }
    }

    fun enviarPendientes(ctx: Context) {
        if (enviando) return
        enviando = true
        Thread {
            try { enviar(ctx) } catch (_: Exception) { } finally { enviando = false }
        }.start()
    }

    private fun enviar(ctx: Context) {
        val p = prefs(ctx)
        val url = p.getString("url", "") ?: ""
        val token = p.getString("token", "") ?: ""
        val email = p.getString("email", "") ?: ""
        if (url.isEmpty() || token.isEmpty() || email.isEmpty() || !p.getBoolean("activo", false)) return
        while (true) {
            val item: JSONObject = synchronized(candado) {
                val cola = try { JSONArray(p.getString("cola", "[]")) } catch (_: Exception) { JSONArray() }
                if (cola.length() == 0) return
                cola.getJSONObject(0)
            }
            val codigo = postear(url, p.getString("app_key", "") ?: "", token, JSONObject(item.toString()).put("email", email))
            when {
                codigo in 200..299 || codigo == 400 || codigo == 422 -> quitarPrimero(ctx)
                codigo == 401 -> {
                    // El dueño desvinculó este celular (o vinculó otro): se apaga.
                    p.edit().putBoolean("activo", false).remove("token").remove("cola").apply()
                    return
                }
                else -> return // sin red / servidor caído: se reintenta después
            }
        }
    }

    private fun quitarPrimero(ctx: Context) {
        synchronized(candado) {
            val p = prefs(ctx)
            val cola = try { JSONArray(p.getString("cola", "[]")) } catch (_: Exception) { JSONArray() }
            val resto = JSONArray()
            for (i in 1 until cola.length()) resto.put(cola.get(i))
            p.edit().putString("cola", resto.toString()).apply()
        }
    }

    private fun postear(base: String, appKey: String, token: String, cuerpo: JSONObject): Int {
        var con: HttpURLConnection? = null
        return try {
            con = (URL("$base/academias/yape/notificacion").openConnection() as HttpURLConnection).apply {
                requestMethod = "POST"
                connectTimeout = 15000
                readTimeout = 20000
                doOutput = true
                setRequestProperty("Content-Type", "application/json")
                if (appKey.isNotEmpty()) setRequestProperty("X-App-Key", appKey)
                setRequestProperty("X-Yape-Token", token)
            }
            con.outputStream.use { it.write(cuerpo.toString().toByteArray(Charsets.UTF_8)) }
            con.responseCode
        } catch (_: Exception) {
            -1
        } finally {
            con?.disconnect()
        }
    }
}
