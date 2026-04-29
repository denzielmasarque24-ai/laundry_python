alter table public.bookings
add column if not exists delivery_fee numeric not null default 0;

-- Keep delivery_type as-is; this only aligns missing fee values with current backend logic.
update public.bookings
set delivery_fee = 0
where delivery_fee is null;
