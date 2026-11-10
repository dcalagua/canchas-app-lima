-- ============================================================
-- MI BODEGA · Fase 3: PAGO DEL PEDIDO CON SALDO PICHANGOL
-- El cliente prepaga su pedido con su saldo (billetera única): el
-- pedido nace PAGADO, el dueño lo entrega sin cobrar (verifica contra
-- el backend) y recibe el monto COMPLETO "por recibir" (la bodega es
-- cero comisión). Si se cancela/rechaza, reembolso automático.
-- Correr una vez en el SQL Editor de Supabase.
-- ============================================================

alter table public.pichangol_bodega_pedidos
  add column if not exists pagado boolean not null default false;
