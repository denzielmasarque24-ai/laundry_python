create extension if not exists pgcrypto;

create table if not exists public.messages (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  booking_id uuid null,
  sender text not null check (sender in ('user', 'admin')),
  message text not null,
  is_read boolean not null default false,
  created_at timestamptz not null default now()
);

create index if not exists idx_messages_user_created_at
  on public.messages (user_id, created_at);

create index if not exists idx_messages_booking_created_at
  on public.messages (booking_id, created_at);

