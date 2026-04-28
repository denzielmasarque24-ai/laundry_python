alter table public.bookings
add column if not exists delivery_status text not null default 'Not Started';

-- Optional safeguard for allowed values
do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'bookings_delivery_status_check'
  ) then
    alter table public.bookings
    add constraint bookings_delivery_status_check
    check (delivery_status in ('Not Started', 'Preparing', 'Out for Delivery', 'Delivered'));
  end if;
end$$;

