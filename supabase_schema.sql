-- ============================================================
-- FreshWash — Full Schema (bookings + profiles)
-- Run this in: Supabase Dashboard → SQL Editor → New Query
-- ============================================================

-- ── Profiles table ──────────────────────────────────────────
create table if not exists public.profiles (
  id         uuid primary key references auth.users(id) on delete cascade,
  email      text unique not null,
  full_name  text not null,
  phone      text,
  address    text,
  avatar     text,
  created_at timestamptz default now()
);

alter table public.profiles add column if not exists email text;
alter table public.profiles add column if not exists avatar text;
alter table public.profiles alter column email set not null;

alter table public.profiles enable row level security;

drop policy if exists "Users can view own profile"   on public.profiles;
drop policy if exists "Users can insert own profile" on public.profiles;
drop policy if exists "Users can update own profile" on public.profiles;

create policy "Users can view own profile"
  on public.profiles for select
  using (auth.uid() = id);

create policy "Users can insert own profile"
  on public.profiles for insert
  with check (auth.uid() = id);

create policy "Users can update own profile"
  on public.profiles for update
  using (auth.uid() = id)
  with check (auth.uid() = id);


-- ── Bookings table ──────────────────────────────────────────
create table if not exists public.bookings (
  id           uuid primary key default gen_random_uuid(),
  user_id      uuid references auth.users(id) on delete cascade not null,
  full_name    text not null,
  phone        text not null,
  address      text not null,
  service_type text not null,
  pickup_date  date not null,
  pickup_time  time not null,
  weight       numeric(6,2) not null,
  notes        text,
  status       text not null default 'Pending',
  created_at   timestamptz default now()
);

alter table public.bookings enable row level security;

drop policy if exists "Users manage own bookings"    on public.bookings;
drop policy if exists "Users can view own bookings"  on public.bookings;
drop policy if exists "Users can insert own bookings" on public.bookings;
drop policy if exists "Users can update own bookings" on public.bookings;
drop policy if exists "Users can delete own bookings" on public.bookings;

create policy "Users can view own bookings"
  on public.bookings for select
  using (auth.uid() = user_id);

create policy "Users can insert own bookings"
  on public.bookings for insert
  with check (auth.uid() = user_id);

create policy "Users can update own bookings"
  on public.bookings for update
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

create policy "Users can delete own bookings"
  on public.bookings for delete
  using (auth.uid() = user_id);


-- ── Verify ──────────────────────────────────────────────────
select tablename, policyname, cmd
from pg_policies
where schemaname = 'public'
order by tablename, cmd;
