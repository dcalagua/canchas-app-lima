# Gestión de redes (Nivel 2) — publicar por el dueño en IG/FB

Servicio superior: Pichangol publica **directamente** en el Instagram/Facebook
del dueño de cancha/academia, con su **permiso** (OAuth de Meta, revocable). Es
como que el dueño contrate un equipo de marketing.

## Cómo funciona (ya implementado)

1. El dueño **contrata** el plan **"Gestión de redes"** en _Servicios Pichangol_
   (se debita del saldo, precio editable en la torre de control →
   `servicio_gestion_soles`).
2. Aparece la tarjeta **"Gestión de redes"** con **"Conectar Instagram/Facebook"**.
3. Al tocar, el APK abre el **diálogo de permiso de Meta** (OAuth). El dueño
   acepta → Meta redirige a `GROWTH_API_URL/marketing/redes/callback` → el backend
   guarda el **token cifrado** y la conexión queda **conectada**.
4. En _Community manager IA_ cada post generado muestra **"Publicar"**: publica en
   la Página de FB (texto) y en Instagram (si hay imagen). El token del dueño
   nunca sale del backend ni se muestra en el APK.
5. El dueño puede **Desconectar** desde el APK, o **revocar** el permiso desde su
   propio Facebook.

### Modo sandbox vs producción (`META_MODO`)

- **sandbox** (por defecto, sin credenciales): el flujo completo funciona pero
  **no** publica en redes reales — simula la conexión y la publicación. Sirve
  para probar en dev/QAS y para **grabar el video** que exige App Review.
- **produccion**: OAuth y publicación reales. Se activa **solo** cuando estén las
  credenciales y Meta haya aprobado los permisos. **No hay que tocar código**:
  basta cambiar las variables en Railway.

## Lo que TÚ tienes que hacer en Meta (trámite, corre en paralelo)

> El cuello de botella es Meta (semanas). Arráncalo ya; el código ya está listo.

1. **Crear la app** en <https://developers.facebook.com> → tipo **Business**.
2. **Verificación de empresa** (Business Verification) de EBIM: sube RUC/ficha
   RUC, datos de la empresa. Es lo que más demora — empieza por aquí.
3. **Productos a agregar** en la app: _Facebook Login for Business_ + _Instagram
   Graph API_.
4. **Permisos a solicitar** en App Review (justificar cada uno + video demo):
   `pages_show_list`, `pages_manage_posts`, `pages_read_engagement`,
   `instagram_basic`, `instagram_content_publish`, `business_management`.
5. **Política de privacidad** pública (URL) y **URL de eliminación de datos**.
6. **Redirect URI** válido (OAuth): registrar exactamente
   `https://pg-backend-production-c176.up.railway.app/marketing/redes/callback`.
7. **Requisito del dueño de cancha**: su Instagram debe ser **Business/Creator**
   y estar **vinculado a una Página de Facebook** (un perfil personal no sirve).
   El agente lo guía; si no puede, se queda en Nivel 1 (Presencia).

## Variables en Railway (cuando Meta apruebe)

Cargar en el servicio `pg-backend` (nunca en el APK ni en el repo):

| Variable | Valor |
|---|---|
| `META_APP_ID` | ID de la app de Meta |
| `META_APP_SECRET` | Secret de la app |
| `META_REDIRECT_URI` | `…/marketing/redes/callback` (idéntico al registrado) |
| `META_MODO` | `produccion` |
| `META_TOKEN_KEY` | clave Fernet para cifrar tokens (ver abajo) |
| `META_GRAPH_VERSION` | opcional, por defecto `v21.0` |

Generar `META_TOKEN_KEY`:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Con eso, el flujo ya construido pasa de sandbox a real **sin cambios de código**.

## Endpoints (backend growth)

- `GET  /marketing/redes/estado/{academia_id}` — estado (enmascarado, sin token).
- `POST /marketing/redes/conectar` — inicia conexión (login_url en prod / simulada en sandbox).
- `GET  /marketing/redes/callback` — público; Meta redirige aquí tras el permiso.
- `POST /marketing/redes/desconectar` — revoca la conexión.
- `POST /marketing/redes/publicar` — publica un post aprobado en IG/FB.

Precio del plan: `servicio_gestion_soles` (torre de control → _Servicios de
marketing_ → "Gestión de redes").
