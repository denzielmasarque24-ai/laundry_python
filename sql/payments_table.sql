create table if not exists public.payments (
  id uuid primary key default gen_random_uuid(),
  booking_id uuid not null,
  user_id uuid not null,
  customer_name text not null default '',
  payment_method text not null default '',
  status text not null default 'pending',
  payment_status text not null default 'Pending',
  amount numeric not null default 0,
  payment_proof text,
  created_at timestamptz not null default now()
);

alter table public.payments add column if not exists status text not null default 'pending';
alter table public.payments add column if not exists payment_reference text;
alter table public.payments add column if not exists reference_number text;
alter table public.payments add column if not exists proof_image text;

update public.payments
set status = lower(replace(coalesce(nullif(status, ''), payment_status, 'pending'), ' ', '_'));

update public.payments
set status = 'paid'
where status in ('completed', 'verified');

alter table public.payments drop constraint if exists payments_status_check;
alter table public.payments
  add constraint payments_status_check
  check (status in ('pending', 'paid', 'cancelled'));

create index if not exists idx_payments_created_at
  on public.payments (created_at desc);

create index if not exists idx_payments_booking_id
  on public.payments (booking_id);
