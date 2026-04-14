from supabase import create_client, Client
from dotenv import load_dotenv
import os

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be set in environment variables.")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


def get_authed_client(access_token: str) -> Client:
    """Return an RLS-authenticated client using the user's JWT."""
    authed: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    if access_token and access_token.strip():
        authed.postgrest.auth(access_token)
    return authed
