# Backend — recomendación y plan (Supabase)

## Recomendación: **Supabase**
Para que el desarrollo crezca y sea **escalable en el tiempo**, recomiendo
**Supabase** sobre Firebase u otros:

- **Postgres (SQL relacional)**: un marketplace tiene datos muy relacionados
  (clubes → canchas → reservas → pagos → saldos). SQL escala mejor para
  reportes, comisiones y consultas complejas que el NoSQL de Firestore.
- **Auth incluido** y compatible con el **Google Sign-In** que ya usamos.
- **Realtime, Storage** (fotos de canchas), **Edge Functions** (lógica de
  servidor: webhooks de pago, matchmaking, anti no-show).
- **Row Level Security** para multi-tenant (cada club ve lo suyo).
- **No depende de Google Cloud** → esquiva el bloqueo de ebim.pe.
- **Open source**: si algún día creces mucho, puedes **autohospedarlo** (sin
  lock-in). Plan free generoso para arrancar.

> Firebase es válido, pero Firestore (NoSQL) complica reportes/transacciones de
> un marketplace, y ata a Google Cloud. Para crecer, Postgres es más sólido.

## Esquema inicial (SQL para correr en Supabase)
```sql
-- Perfiles (1:1 con auth.users)
create table profiles (
  id uuid primary key references auth.users on delete cascade,
  nombre text, email text, foto_url text,
  creado timestamptz default now()
);

create table clubs (
  id uuid primary key default gen_random_uuid(),
  owner uuid references auth.users,
  nombre text not null,
  distrito text not null,
  saldo int not null default 0,
  destacado boolean generated always as (saldo > 0) stored,
  creado timestamptz default now()
);

create table canchas (
  id uuid primary key default gen_random_uuid(),
  club_id uuid references clubs on delete cascade,
  nombre text not null,
  deporte text not null check (deporte in ('tenis','padel','futbol')),
  distrito text not null,
  precio_hora int not null,
  lat double precision, lng double precision,
  foto_url text,
  club_fundador boolean default false,
  creado timestamptz default now()
);

create table reservas (
  id uuid primary key default gen_random_uuid(),
  cancha_id uuid references canchas on delete cascade,
  usuario uuid references auth.users,
  dia text, hora_inicio text, hora_fin text,
  estado text not null default 'confirmada',
  precio int, sena int,
  traida_por_app boolean default true,
  creado timestamptz default now()
);

create table movimientos_saldo (
  id uuid primary key default gen_random_uuid(),
  club_id uuid references clubs on delete cascade,
  tipo text check (tipo in ('recarga','consumo')),
  monto int, concepto text,
  creado timestamptz default now()
);

create table pagos (
  id uuid primary key default gen_random_uuid(),
  usuario uuid references auth.users,
  club_id uuid references clubs,
  monto int, metodo text, referencia text,
  estado text default 'pagado', concepto text,
  creado timestamptz default now()
);
```
(Luego activamos **RLS** con políticas: canchas/reservas legibles por todos;
escritura del club solo por su `owner`; reservas escritas por el jugador dueño.)

## Pasos para arrancar (tú)
1. Crea cuenta en **https://supabase.com** y un **proyecto** (región: South
   America / São Paulo). Plan free.
2. En **SQL Editor**, pega y corre el esquema de arriba.
3. En **Authentication → Providers**, activa **Google** (con el OAuth que
   crearemos — ver RELEASE_SIGNING.md).
4. Pásame de **Project Settings → API**:
   - **Project URL** (ej. `https://xxxx.supabase.co`)
   - **anon public key** (es publicable; la cargamos como secret de igual modo).

## Pasos para integrarlo (yo, cuando me des URL + anon key)
1. Agrego `supabase_flutter`, inicializo con URL+anon (inyectados como la Maps key).
2. Refactor del acceso a datos a un **Repository** (`CanchasRepo`, `ReservasRepo`,
   `ClubRepo`) con implementación Supabase; el estado local queda como caché/offline.
3. Auth con Supabase + Google; los datos pasan a ser **compartidos entre celulares**.
4. Migración por capas: primero canchas y reservas; luego saldo/pagos.

## Migración — columnas `direccion` y `registrada` (correr en SQL Editor)
La tabla en uso por la app es **`pichangol_canchas`**. Para que se compartan la
dirección escrita y el estado "registrada/descubierta", agrega dos columnas:

```sql
alter table pichangol_canchas
  add column if not exists direccion text,
  add column if not exists registrada boolean not null default true,
  add column if not exists foto_url text,
  add column if not exists fotos jsonb default '[]'::jsonb,
  add column if not exists dueno text default '',          -- correo del dueño
  add column if not exists verificada boolean default true; -- propiedad verificada
```

La columna **`verificada`** habilita el flujo anti-fraude (Capa 1): al **registrar o
reclamar** una cancha, la app la marca `verificada = false` ("Pendiente de
verificación") y **bloquea las reservas online** hasta confirmar que quien la reclama
es el dueño real. Para **aprobar** una cancha (revisión manual del piloto), en el
**Table Editor** de Supabase pon `verificada = true` en esa fila, o por SQL:

```sql
update pichangol_canchas set verificada = true where id = 'ID_DE_LA_CANCHA';
```

> La Capa 2 (OTP por WhatsApp/SMS al teléfono del local) automatizará esta aprobación
> cuando elijas proveedor; hará el mismo `update` tras validar el código.

La columna **`dueno`** (correo del dueño) hace que **"Mis canchas"** recupere las
canchas del dueño desde la nube tras reinstalar la app: la app filtra por ese
correo. Las canchas registradas antes de esta columna quedan con `dueno` vacío
("legado"); aparecen igual en "Mis canchas" y, al **guardarlas/editarlas una vez**,
se **reclaman** automáticamente con el correo del usuario logueado.

### Fotos de cancha (Supabase Storage)
Para que el dueño suba una **foto de portada** al registrar/editar su cancha:
1. En Supabase → **Storage** → **New bucket** → nombre **`canchas`** → marcar
   **Public bucket** → crear.
2. (Opcional, recomendado) políticas: lectura pública e inserción/actualización
   para el rol `anon` mientras no haya auth de dueño:
   ```sql
   -- Subir/actualizar fotos (piloto sin auth de dueño)
   create policy "canchas_upload" on storage.objects
     for insert to anon with check (bucket_id = 'canchas');
   create policy "canchas_update" on storage.objects
     for update to anon using (bucket_id = 'canchas');
   ```
   La lectura ya es pública por ser *public bucket*. Si no creas el bucket, la
   app no falla: la cancha simplemente queda sin foto.

> Si no corres esto, la app sigue funcionando: las canchas nuevas se ven en tu
> celular, pero el alta a Supabase podría fallar en silencio hasta que existan
> las columnas. Por eso conviene aplicarlo.

## Reservas compartidas (tabla `pichangol_reservas`)
Para que la **disponibilidad de horarios** se comparta entre dispositivos y
"Mis reservas" siga al jugador por su correo, corre en el SQL Editor:

```sql
create table if not exists pichangol_reservas (
  id text primary key,
  cancha_id text,
  jugador text,
  nivel text,
  dia text,
  hora_inicio text,
  hora_fin text,
  estado text default 'confirmada',
  traida_por_app boolean default true,
  precio int,
  sena int,
  usuario text,            -- correo del jugador (para "mis reservas")
  creado timestamptz default now()
);
alter table pichangol_reservas enable row level security;
-- Piloto sin auth de dueño: lectura/escritura para anon (ajustar con RLS real luego)
create policy "reservas_read"  on pichangol_reservas for select to anon using (true);
create policy "reservas_write" on pichangol_reservas for insert to anon with check (true);
```

> Fail-safe: si no creas la tabla, las reservas siguen funcionando en local;
> simplemente no se comparten entre dispositivos.

## Places vía Edge Function (sacar la API key del APK)
La app llama primero a la función `places-cerca` (código en
`supabase/functions/places-cerca/`) y solo si no está desplegada cae al llamado
directo a Google. Para desplegarla y guardar la key del lado servidor:

```bash
# Requiere la CLI de Supabase y haber hecho `supabase link` a tu proyecto
supabase functions deploy places-cerca --no-verify-jwt
supabase secrets set PLACES_API_KEY=tu_key_de_places
```

Con esto la key deja de viajar en el APK (más seguro y escalable). Mientras no
la despliegues, todo sigue funcionando con la key del cliente.

## Escalabilidad a futuro
- Edge Functions para webhooks de la pasarela (Culqi/Yape) y para el
  matchmaking por nivel.
- Storage para fotos reales de canchas (hoy se detecta el deporte localmente).
- Índices geográficos (PostGIS) para "canchas cercanas" del lado servidor.
