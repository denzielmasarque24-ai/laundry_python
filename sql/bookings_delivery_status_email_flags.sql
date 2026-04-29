alter table public.bookings
add column if not exists out_for_delivery_email_sent boolean not null default false;

alter table public.bookings
add column if not exists delivered_email_sent boolean not null default false;
