-- Add missing payment columns to bookings table
-- Safe to run multiple times (IF NOT EXISTS)

ALTER TABLE public.bookings
ADD COLUMN IF NOT EXISTS payment_method text;

ALTER TABLE public.bookings
ADD COLUMN IF NOT EXISTS payment_status text DEFAULT 'Pending';

ALTER TABLE public.bookings
ADD COLUMN IF NOT EXISTS payment_reference text;
