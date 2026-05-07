create extension if not exists pgcrypto;

create table if not exists public.contact_us (
  id uuid primary key default gen_random_uuid(),
  user_id uuid,
  name text not null,
  email text not null,
  subject text not null,
  message text not null,
  admin_reply text,
  created_at timestamptz not null default now()
);

alter table public.contact_us
  add column if not exists user_id uuid;

alter table public.contact_us
  add column if not exists admin_reply text;

create table if not exists public.contact_messages (
  id uuid primary key default gen_random_uuid(),
  user_id uuid,
  name text not null,
  email text not null,
  subject text,
  message text not null,
  admin_reply text,
  created_at timestamptz not null default now()
);

create index if not exists idx_contact_us_created_at
  on public.contact_us (created_at desc);

create index if not exists idx_contact_messages_created_at
  on public.contact_messages (created_at desc);

create index if not exists idx_contact_messages_user_id
  on public.contact_messages (user_id);
