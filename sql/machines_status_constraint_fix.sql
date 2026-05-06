-- Fix machines table status constraint to allow all admin statuses
-- Run in: Supabase Dashboard → SQL Editor → New Query

-- 1. Drop the old constraint before writing the new Not Available value
ALTER TABLE public.machines DROP CONSTRAINT IF EXISTS machines_status_check;

-- 2. Normalise existing values
UPDATE public.machines
SET status = 'Not Available'
WHERE status = 'Unavailable';

UPDATE public.machines
SET status = 'Disabled'
WHERE status IS NULL
   OR status NOT IN ('Available', 'In Use', 'Maintenance', 'Not Available', 'Disabled');

-- 3. Add the new constraint with all admin statuses
ALTER TABLE public.machines
  ADD CONSTRAINT machines_status_check
  CHECK (status IN ('Available', 'In Use', 'Maintenance', 'Not Available', 'Disabled'));

-- 4. Verify
SELECT conname, pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conrelid = 'public.machines'::regclass
  AND contype = 'c';
