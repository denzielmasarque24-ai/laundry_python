from supabase import create_client, Client
import os

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError(
        "SUPABASE_URL and SUPABASE_KEY must be set in Vercel Environment Variables"
    )

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)