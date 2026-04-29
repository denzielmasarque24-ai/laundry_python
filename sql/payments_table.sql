create table if not exists public.payments (
  id uuid primary key default gen_random_uuid(),
  booking_id uuid not null,
  user_id uuid not null,
  customer_name text not null default '',
  payment_method text not null default '',
  payment_status text not null default 'Pending',
  amount numeric not null default 0,
  payment_proof text,
  created_at timestamptz not null default now()
);

create index if not exists idx_payments_created_at
  on public.payments (created_at desc);

create index if not exists idx_payments_booking_id
  on public.payments (booking_id);
