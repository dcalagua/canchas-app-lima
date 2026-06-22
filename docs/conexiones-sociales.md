# Conexiones sociales — importar fotos/videos del dueño (con consentimiento)

Al **registrar o reclamar** una cancha, el dueño puede **conectar su propia red**
(Facebook / Instagram / TikTok) e **importar sus fotos y videos** para enriquecer
el local. Si un día deja la cancha, **desconecta** y los medios importados se
retiran. Solo medios **propios**, con **OAuth/consentimiento** — nunca scraping de
cuentas ajenas (ToS + derechos de autor).

## Principio
- El dueño conecta **su** cuenta (OAuth) → autoriza el uso de **sus** medios.
- **Desconectar = retirar**: se revoca el token y se eliminan/ocultan los medios
  importados desde esa conexión (control de datos, alineado a Ley 29733).
- Para canchas que **ya están en Google Maps**, seguimos auto-enriqueciendo con
  Google Places (no requiere conexión).

## Modelo de datos
```sql
conexiones_sociales(
  id, cancha_id, dueno_id,
  plataforma [facebook|instagram|tiktok],
  cuenta_handle, token_cifrado, scope,
  estado [conectada|desconectada],
  conectado_en, desconectado_en
)
medios_importados(
  id, cancha_id, conexion_id,
  tipo [foto|video], url, miniatura_url,
  origen_post_id, importado_en
)
```
- **Token cifrado** server-side (nunca en el APK), scope **mínimo** (solo lectura
  de medios). Al desconectar: revocar token + borrar filas/medios.

## Flujo
1. **Conectar**: el dueño elige plataforma → OAuth → guardamos token cifrado.
2. **Elegir**: listamos sus medios; el dueño **selecciona** cuáles importar.
3. **Importar**: copiamos a **Storage de Pichangol** (las URLs de IG/FB/TikTok
   expiran o dependen del token), generamos miniatura y las mostramos en la ficha.
4. **Curar (IA visión)**: verificar que sean de canchas y priorizar las de mejor
   calidad (opcional).
5. **Desconectar**: revoca token y **elimina** los medios importados de esa cuenta.

## Realidades por plataforma (para fijar expectativas)
- **Meta (Facebook + Instagram)** — una sola app de Meta cubre ambos:
  - **Facebook**: Graph API → fotos/videos de la **Página** que el dueño
    administra. Requiere permisos (`pages_show_list`, `pages_read_engagement`) y
    **App Review** para producción.
  - **Instagram**: vía **Instagram API con Instagram Login** (Graph) para cuentas
    **profesionales** (Business/Creator). *Basic Display API* quedó **deprecado
    (dic 2024)**, así que cuentas personales ya no aplican igual.
- **TikTok**: **Login Kit + Display API** (`video.list`) → videos del usuario con
  su consentimiento. Requiere registrar la app y **review**.
- **Común a todos**: registrar la app en cada plataforma, flujo OAuth y revisión
  para salir a producción (toma tiempo de aprobación).

## Plan por fases
1. **Foundation (sin OAuth real)**: modelo + endpoints `conectar/desconectar/
   importar` + UI "Conectar red social" con **stub** (datos de ejemplo). Deja todo
   listo para enchufar proveedores.
2. **Meta primero** (FB Página + IG profesional) — una sola App Review cubre los
   dos. Recomendado por cobertura.
3. **TikTok** después (para videos).

## Cumplimiento
- Solo medios del dueño, con su consentimiento explícito al conectar.
- Tokens cifrados, scope mínimo, borrado al desconectar.
- No se guardan datos personales de terceros ni se scrapea contenido ajeno.
