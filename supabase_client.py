from supabase import create_client, Client
from dotenv import load_dotenv
import os

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
SUPABASE_ENABLED = bool(SUPABASE_URL and SUPABASE_KEY)
SUPABASE_SERVICE_ROLE_ENABLED = bool(SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY)

supabase: Client | None = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_ENABLED else None
supabase_service: Client | None = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY) if SUPABASE_SERVICE_ROLE_ENABLED else None


def is_supabase_enabled() -> bool:
    return SUPABASE_ENABLED


def is_supabase_service_role_enabled() -> bool:
    return SUPABASE_SERVICE_ROLE_ENABLED


def get_authed_client(access_token: str) -> Client:
    """Return an RLS-authenticated client using the user's JWT."""
    if not SUPABASE_ENABLED:
        raise RuntimeError("Supabase is not configured.")

    authed: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    if access_token and access_token.strip():
        authed.postgrest.auth(access_token)
    return authed


def get_service_client() -> Client:
    """Return a service-role client for privileged server-side writes."""
    if not SUPABASE_SERVICE_ROLE_ENABLED or not supabase_service:
        raise RuntimeError("Supabase service role is not configured.")
    return supabase_service
