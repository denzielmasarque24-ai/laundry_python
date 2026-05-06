-- Allow all admin machine availability statuses.
-- Safe to run multiple times.

ALTER TABLE public.machines
DROP CONSTRAINT IF EXISTS machines_status_check;

UPDATE public.machines
SET status = 'Not Available'
WHERE status = 'Unavailable';

UPDATE public.machines
SET status = 'Available'
WHERE status IS NULL
   OR status NOT IN ('Available', 'In Use', 'Maintenance', 'Not Available', 'Disabled');

ALTER TABLE public.machines
ADD CONSTRAINT machines_status_check
CHECK (status IN ('Available', 'In Use', 'Maintenance', 'Not Available', 'Disabled'));

UPDATE public.machines
SET enabled = false
WHERE status IN ('In Use', 'Maintenance', 'Not Available', 'Disabled');

UPDATE public.machines
SET enabled = true
WHERE status = 'Available'
  AND enabled IS DISTINCT FROM true;
