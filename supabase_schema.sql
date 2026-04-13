-- Run this in your Supabase SQL Editor (Dashboard → SQL Editor → New Query)

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

-- Enable Row Level Security
alter table public.bookings enable row level security;

-- Users can only read/write their own bookings
create policy "Users manage own bookings"
  on public.bookings
  for all
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);
