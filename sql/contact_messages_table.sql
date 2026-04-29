create extension if not exists pgcrypto;

create table if not exists public.contact_us (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  email text not null,
  subject text not null,
  message text not null,
  created_at timestamptz not null default now()
);

create index if not exists idx_contact_us_created_at
  on public.contact_us (created_at desc);
