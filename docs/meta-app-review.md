# Meta App Review — Pichangol (Manejo de redes)

Guía completa para aprobar los permisos de publicación en nombre de las
academias (para abrir el servicio a **cualquier** academia, sin agregarlas como
testers). App ID `2082565302654489`.

> Mientras no esté aprobado + la app en **Live**, solo conectan cuentas con rol
> (admin/tester). Con App Review aprobado, conecta **cualquiera**.

---

## 0. Requisitos previos (haz esto primero — lo más lento)

- [ ] **Verificación de empresa de EBIM** (Meta Business Suite → Configuración →
      Centro de seguridad → *Verificar empresa*). Sube RUC/ficha RUC. **Es
      obligatoria** para el acceso avanzado y tarda días → arráncala YA.
- [x] **Política de privacidad:** `https://pg.ebim.pe/legal/privacidad`
- [x] **Eliminación de datos:** `https://pg.ebim.pe/legal/eliminacion-datos`
- [x] **Categoría de la app:** Negocios y páginas
- [ ] **Ícono de la app** (1024×1024 PNG, cuadrado) en Configuración → Básica.
      (Podemos generarlo con el logo de Pichangol.)
- [ ] **Correo y datos de contacto** completos en Básica.

---

## 1. Permisos a solicitar (Advanced Access)

En **Revisión de la app → Permisos y funciones**, pide **Acceso avanzado** de:

| Permiso | Para qué lo usamos (versión corta) |
|---|---|
| `pages_show_list` | Listar las Páginas que administra el dueño para que elija cuál conectar. |
| `pages_read_engagement` | Leer el nombre/estado de la Página conectada y su Instagram vinculado. |
| `pages_manage_posts` | Publicar en la Página los posts que el dueño aprueba. |
| `instagram_basic` | Leer el usuario/estado de la cuenta de Instagram conectada. |
| `instagram_content_publish` | Publicar en Instagram los posts (con foto) que el dueño aprueba. |
| `business_management` | Acceder a los activos (Páginas/IG) que el dueño autoriza para publicar por él. |

---

## 2. Justificaciones (texto listo para PEGAR en cada permiso)

> Meta pide una descripción por permiso. Pega estos textos (en inglés, que es lo
> que Meta espera; abajo va la versión en español por si el formulario lo acepta).

### pages_show_list
> Pichangol is a social-media management service for sports academies. During the
> Facebook Login for Business flow, the academy owner grants access to their
> assets. We use `pages_show_list` to display the list of Facebook Pages the
> person administers, so they can choose which Page Pichangol will publish to on
> their behalf. Shown in the connect step of the video.

### pages_read_engagement
> We use `pages_read_engagement` to read basic information of the connected Page
> (its name and its linked Instagram Business account) in order to (a) show the
> owner which account is connected and (b) resolve the Instagram account used for
> publishing. We do not read followers' personal data. Shown after connecting.

### pages_manage_posts
> Core use case. After the academy owner reviews and approves AI-generated
> content inside Pichangol, we use `pages_manage_posts` to publish that content
> (text and photos) to their Facebook Page on their behalf. The owner approves
> each post with an explicit "Publish" tap. Demonstrated in the video (approve →
> publish → post appears on the Page).

### instagram_basic
> We use `instagram_basic` to read the connected Instagram Business account's
> basic info (username, linked-to-Page status) to display which Instagram account
> is connected and to enable publishing to it.

### instagram_content_publish
> Core use case. We use `instagram_content_publish` to publish the photo posts the
> academy owner approves inside Pichangol to their Instagram Business account, on
> their behalf. Each publication is triggered by the owner's explicit approval.
> Demonstrated in the video (approve with photo → publish → post appears on IG).

### business_management
> We use `business_management` to access the business assets (Facebook Pages and
> linked Instagram Business accounts) that the academy owner explicitly grants
> during the Login for Business flow, so Pichangol can identify and publish to the
> correct accounts on their behalf. The owner can revoke access anytime.

**Común a todos (agregar al final de cada uno):**
> Access is granted by the business owner via Facebook Login for Business and is
> fully revocable (in-app "Disconnect" and Facebook settings). We never store the
> user's password. Privacy policy: https://pg.ebim.pe/legal/privacidad — Data
> deletion: https://pg.ebim.pe/legal/eliminacion-datos

---

## 3. Guion del VIDEO (lo más importante de la revisión)

Graba **una pantalla** (celular o emulador) mostrando el flujo COMPLETO y real,
sin cortes. Debe verse cómo se **otorga** el permiso y cómo se **usa**. Duración
ideal 1–3 min. Narra o subtitula cada paso.

**Escena por escena:**
1. **App Pichangol** → entra como dueño de una academia. Muestra la academia.
2. Ve a **Servicios → Manejo de redes** (o "Publicación automática") → toca
   **"Conectar Instagram / Facebook"**.
3. Se abre **Facebook Login for Business** → muestra que **eliges la Página** y la
   **cuenta de Instagram**, y la pantalla donde Facebook **pide los permisos**
   (aquí se ve `instagram_content_publish`, `pages_manage_posts`, etc.). **Acepta.**
4. Vuelve a Pichangol → muestra **"Redes conectadas"** con el @Instagram y la
   Página (prueba que `pages_show_list` / `instagram_basic` se usaron).
5. En **Community manager con IA**, genera un post → toca **Publicar → Con foto**
   → elige una imagen. (Aquí se usan `pages_manage_posts` + `instagram_content_publish`.)
6. **Abre Instagram y la Página de Facebook** en el mismo video y muestra el post
   **ya publicado**. (Prueba visual de que el permiso funciona.)
7. Muestra el botón **"Desconectar"** (revocación).

> Consejo: usa una cuenta con rol tester para grabar (funciona antes de aprobar).
> Ese mismo video es la evidencia para que aprueben.

---

## 4. Instrucciones para el revisor (pegar en "Test instructions")

> Pichangol is a mobile app (Android). Test build (APK):
> https://github.com/dcalagua/canchas-app-lima/releases/tag/v0.1.0
>
> Steps to reproduce:
> 1. Open the app, sign in, and open an academy you own.
> 2. Go to "Servicios" → "Manejo de redes" → tap "Conectar Instagram / Facebook".
> 3. Complete Facebook Login for Business: select a Page and its linked Instagram
>    Business account, and accept the permissions.
> 4. Back in the app, "Servicios" → "Community manager con IA" → generate a post →
>    tap "Publicar" → "Con foto" → choose an image.
> 5. The post is published to the connected Facebook Page and Instagram account.
>
> A full screencast of this flow is attached. Access is revocable via the
> in-app "Desconectar" button and Facebook settings.
> Privacy policy: https://pg.ebim.pe/legal/privacidad
> Data deletion: https://pg.ebim.pe/legal/eliminacion-datos

> Si Meta pide credenciales de prueba, crea un **usuario de prueba de Facebook**
> (Roles → Usuarios de prueba) con una Página + IG de prueba, y compártelo.

---

## 5. Enviar a revisión (paso a paso en el panel)

1. Completa **Verificación de empresa** (bloqueante) y el **ícono** de la app.
2. **Revisión de la app → Permisos y funciones** → por cada permiso de la lista,
   **"Solicitar acceso avanzado"** → pega la **justificación** (sección 2) y sube
   el **video** (sección 3).
3. Completa **Instrucciones de prueba** (sección 4).
4. En **Configurar → Inicio de sesión con Facebook** verifica que estén las
   **Instrucciones de prueba obligatorias** actualizadas (botón "Agregar o
   actualizar instrucciones").
5. Cambia la app a **"Activo/Live"** (toggle arriba; requiere privacidad ✅).
6. **Enviar** la solicitud. Espera de Meta: **días a semanas**.

---

## 6. Después de aprobar

- La app queda en **Live** con acceso avanzado → **cualquier academia** conecta
  con los 3 taps, **sin** agregarla como tester.
- No hay que tocar código ni Railway. El flujo ya es el mismo.

---

## 7. Qué necesito de ti para avanzar

1. **Empieza la Verificación de empresa** (lo más lento).
2. Dime si quieres que **genere el ícono 1024×1024** con el logo de Pichangol.
3. Cuando grabes el **video** con tu cuenta tester (ya conectaste La Vidriería,
   así que puedes grabarlo hoy), lo revisamos juntos antes de enviar.
