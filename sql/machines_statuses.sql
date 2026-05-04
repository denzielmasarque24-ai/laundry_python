-- Allow all admin machine availability statuses.
-- Safe to run multiple times.

UPDATE public.machines
SET status = 'Available'
WHERE status IS NULL
   OR status NOT IN ('Available', 'In Use', 'Maintenance', 'Disabled', 'Unavailable');

ALTER TABLE public.machines
DROP CONSTRAINT IF EXISTS machines_status_check;

ALTER TABLE public.machines
ADD CONSTRAINT machines_status_check
CHECK (status IN ('Available', 'In Use', 'Maintenance', 'Disabled', 'Unavailable'));

UPDATE public.machines
SET enabled = false
WHERE status IN ('Maintenance', 'Disabled', 'Unavailable');

UPDATE public.machines
SET enabled = true
WHERE status IN ('Available', 'In Use')
  AND enabled IS DISTINCT FROM true;
