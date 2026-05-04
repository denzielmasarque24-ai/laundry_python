-- Add missing payment columns to bookings table
-- Safe to run multiple times (IF NOT EXISTS)

ALTER TABLE public.bookings
ADD COLUMN IF NOT EXISTS payment_method text;

ALTER TABLE public.bookings
ADD COLUMN IF NOT EXISTS payment_option text;

ALTER TABLE public.bookings
ADD COLUMN IF NOT EXISTS payment_status text DEFAULT 'Pending';

ALTER TABLE public.bookings
ADD COLUMN IF NOT EXISTS payment_reference text;

ALTER TABLE public.bookings
ADD COLUMN IF NOT EXISTS reference_number text;

ALTER TABLE public.bookings
ADD COLUMN IF NOT EXISTS payment_proof text;

ALTER TABLE public.bookings
ADD COLUMN IF NOT EXISTS proof_image text;

ALTER TABLE public.bookings
ADD COLUMN IF NOT EXISTS total_amount numeric(10,2);

ALTER TABLE public.bookings
ADD COLUMN IF NOT EXISTS total_price numeric(10,2);

ALTER TABLE public.bookings
ADD COLUMN IF NOT EXISTS amount numeric(10,2);

ALTER TABLE public.bookings
ADD COLUMN IF NOT EXISTS price numeric(10,2);

ALTER TABLE public.bookings
ADD COLUMN IF NOT EXISTS created_at timestamptz DEFAULT now();

ALTER TABLE public.bookings
ADD COLUMN IF NOT EXISTS delivery_option text;

ALTER TABLE public.bookings
ADD COLUMN IF NOT EXISTS delivery_type text;

UPDATE public.bookings
SET payment_reference = reference_number
WHERE payment_reference IS NULL AND reference_number IS NOT NULL;

UPDATE public.bookings
SET reference_number = payment_reference
WHERE reference_number IS NULL AND payment_reference IS NOT NULL;

UPDATE public.bookings
SET total_amount = COALESCE(total_amount, amount, price, total_price),
    amount = COALESCE(amount, total_amount, price, total_price),
    price = COALESCE(price, total_amount, amount, total_price)
WHERE total_amount IS NULL
   OR amount IS NULL
   OR price IS NULL;
