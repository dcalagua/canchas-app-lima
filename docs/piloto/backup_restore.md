# Backup / restore de datos Pichangol (Supabase)

Para migrar de un proyecto Supabase a otro (o guardar un respaldo). Las tablas
del APK son `public.pichangol_canchas` y `public.pichangol_reservas`. El estado
del backend growth vive en `public.growth_state` (una fila JSON).

> La connection string sale de: Supabase → **Project Settings → Database →
> Connection string → URI**. Para `pg_dump` usa la **Direct connection** (o la
> Session pooler). No la publiques en el repo ni en el chat.

## 1) Backup (desde el proyecto VIEJO)

Solo datos de las tablas del piloto (para reimportar sobre tablas ya creadas):

```bash
pg_dump "postgresql://postgres:PASSWORD@HOST:5432/postgres?sslmode=require" \
  --no-owner --no-privileges --data-only --column-inserts \
  -t public.pichangol_canchas \
  -t public.pichangol_reservas \
  -t public.growth_state \
  > pichangol_backup_$(date +%Y%m%d).sql
```

Backup COMPLETO (esquema + datos + todo el schema public):

```bash
pg_dump "postgresql://postgres:PASSWORD@HOST:5432/postgres?sslmode=require" \
  --no-owner --no-privileges \
  > pichangol_full_$(date +%Y%m%d).sql
```

Alternativas sin consola:
- **Dashboard → Database → Backups**: descarga (solo en plan Pro).
- **SQL Editor**: `select * from public.pichangol_canchas;` → botón **Download CSV**
  (repetir por tabla). Rápido pero manual.

## 2) Restore (en el proyecto NUEVO)

1. Primero crea las tablas: corre `docs/piloto/supabase_setup_nuevo_proyecto.sql`
   en el SQL Editor del proyecto nuevo.
2. Luego importa los datos:

```bash
psql "postgresql://postgres:PASSWORD@HOST:5432/postgres?sslmode=require" \
  -f pichangol_backup_YYYYMMDD.sql
```

(`growth_state` también la crea el backend solo al arrancar; si la importas,
respeta la fila `id = 1`.)

## Notas
- Verifica el conteo tras importar:
  `select count(*) from public.pichangol_canchas;` y `..._reservas;`.
- Si `pg_dump` da error de "prepared statement" con la pooler, usa la **Direct
  connection** (puerto 5432).
