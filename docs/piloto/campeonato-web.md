# Página pública del campeonato (`campeonato-web`)

Página web (HTML) para **compartir un campeonato a quien NO tiene la app**:
muestra la llave o la tabla de posiciones, la sede con botón "Cómo llegar",
las fechas y, si están abiertas, un aviso de inscripciones. La arma una **Edge
Function** de Supabase que lee `pichangol_campeonatos`.

- **URL:** `https://<proyecto>.supabase.co/functions/v1/campeonato-web?id=<campeonatoId>`
- En la app, el botón **"Enlace"** (detalle del campeonato) copia ese link y
  **"Compartir"** lo incluye en el mensaje de WhatsApp.
- No usa secretos: Supabase inyecta `SUPABASE_URL` y `SUPABASE_ANON_KEY` a la
  función; la tabla ya tiene lectura anónima (RLS del piloto).

## Desplegarla (una vez)

**Opción A — CLI (si la tienes):**

```bash
supabase functions deploy campeonato-web --no-verify-jwt
```

`--no-verify-jwt` es **clave**: la hace pública (cualquiera abre el link sin
token). El código vive en `supabase/functions/campeonato-web/index.ts`.

**Opción B — Dashboard (sin CLI):**

1. Supabase → **Edge Functions** → **Create function** → nombre
   `campeonato-web`.
2. Pega el contenido de `supabase/functions/campeonato-web/index.ts`.
3. En los **settings** de la función, desactiva **"Verify JWT"** (para que sea
   pública).
4. Deploy.

## Probar

Abre en el navegador:
`https://<proyecto>.supabase.co/functions/v1/campeonato-web?id=<id-de-un-campeonato>`

Debe verse la página con la marca Pichangol, la llave/tabla y el botón de mapa.
Si sale "No encontrado", revisa que ese campeonato exista y no esté eliminado en
`pichangol_campeonatos`.
