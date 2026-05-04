-- Fix machines table status constraint to allow all 5 statuses
-- Run in: Supabase Dashboard → SQL Editor → New Query

-- 1. Normalise any existing bad values before touching the constraint
UPDATE public.machines
SET status = 'Disabled'
WHERE status NOT IN ('Available', 'In Use', 'Maintenance', 'Disabled', 'Unavailable');

-- 2. Drop the old constraint (only allowed Available / In Use / Disabled)
ALTER TABLE public.machines DROP CONSTRAINT IF EXISTS machines_status_check;

-- 3. Add the new constraint with all 5 statuses
ALTER TABLE public.machines
  ADD CONSTRAINT machines_status_check
  CHECK (status IN ('Available', 'In Use', 'Maintenance', 'Disabled', 'Unavailable'));

-- 4. Verify
SELECT conname, pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conrelid = 'public.machines'::regclass
  AND contype = 'c';
