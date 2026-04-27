import os
from typing import Any
from urllib.parse import urlparse
from dotenv import load_dotenv

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(_BASE_DIR, ".env"))

try:
    from supabase import create_client, Client
    SUPABASE_IMPORT_ERROR = ""
except Exception as exc:
    create_client = None
    Client = Any
    SUPABASE_IMPORT_ERROR = str(exc)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip()
SUPABASE_KEY = (
    os.environ.get("SUPABASE_ANON_KEY", "")
    or os.environ.get("SUPABASE_KEY", "")
    or os.environ.get("SUPABASE_ANON_PUBLIC_KEY", "")
).strip()
SUPABASE_SERVICE_ROLE_KEY = (
    os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    or os.environ.get("SUPABASE_SERVICE_KEY", "")
).strip()
SUPABASE_CONFIG_ERROR = ""


def _is_valid_supabase_url(url: str) -> bool:
    normalized = (url or "").strip()
    if not normalized:
        return False
    parsed = urlparse(normalized)
    if parsed.scheme != "https":
        return False
    return (parsed.netloc or "").lower().endswith(".supabase.co")


def _resolve_config_error() -> str:
    if SUPABASE_IMPORT_ERROR:
        return f"Supabase SDK unavailable: {SUPABASE_IMPORT_ERROR}"
    if not SUPABASE_URL:
        return "Missing SUPABASE_URL in .env"
    if not _is_valid_supabase_url(SUPABASE_URL):
        return f"Invalid SUPABASE_URL '{SUPABASE_URL}'"
    if not SUPABASE_KEY:
        return "Missing SUPABASE_ANON_KEY in .env"
    return ""


SUPABASE_CONFIG_ERROR = _resolve_config_error()
SUPABASE_ENABLED = not bool(SUPABASE_CONFIG_ERROR)
SUPABASE_SERVICE_ROLE_ENABLED = bool(SUPABASE_ENABLED and SUPABASE_SERVICE_ROLE_KEY)

supabase: "Client | None" = None
try:
    if SUPABASE_ENABLED and create_client:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        print(f"[FreshWash] Supabase connected | url={SUPABASE_URL}", flush=True)
    else:
        print(f"[FreshWash] Supabase DISABLED | reason={SUPABASE_CONFIG_ERROR}", flush=True)
except Exception as exc:
    SUPABASE_CONFIG_ERROR = f"Failed to initialize Supabase client: {exc}"
    SUPABASE_ENABLED = False
    SUPABASE_SERVICE_ROLE_ENABLED = False
    supabase = None
    print(f"[FreshWash] Supabase init FAILED | {exc!r}", flush=True)

supabase_service: "Client | None" = None
try:
    if SUPABASE_SERVICE_ROLE_ENABLED and create_client:
        supabase_service = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
        print("[FreshWash] Supabase service-role client ready", flush=True)
    elif SUPABASE_ENABLED and not SUPABASE_SERVICE_ROLE_KEY:
        print(
            "[FreshWash] WARNING: SUPABASE_SERVICE_ROLE_KEY missing — "
            "new user signup will fail. Add it to .env and restart.",
            flush=True,
        )
except Exception as exc:
    SUPABASE_SERVICE_ROLE_ENABLED = False
    supabase_service = None
    print(f"[FreshWash] Supabase service-role init FAILED | {exc!r}", flush=True)

_gmail_user = os.environ.get("GMAIL_USER", "").strip()
_gmail_pass = os.environ.get("GMAIL_APP_PASSWORD", "").replace(" ", "").strip()
if _gmail_user and _gmail_pass and len(_gmail_pass) >= 16:
    print(f"[FreshWash] Gmail SMTP ready | user={_gmail_user}", flush=True)
else:
    _missing = []
    if not _gmail_user:
        _missing.append("GMAIL_USER")
    if not _gmail_pass:
        _missing.append("GMAIL_APP_PASSWORD")
    elif len(_gmail_pass) < 16:
        _missing.append(
            "GMAIL_APP_PASSWORD (must be 16 chars — use App Password from "
            "myaccount.google.com/apppasswords, not your Gmail login password)"
        )
    print(f"[FreshWash] WARNING: Gmail SMTP not ready — missing {', '.join(_missing)}", flush=True)


def is_supabase_enabled() -> bool:
    return SUPABASE_ENABLED


def is_supabase_service_role_enabled() -> bool:
    return SUPABASE_SERVICE_ROLE_ENABLED


def get_supabase_config_error() -> str:
    return SUPABASE_CONFIG_ERROR


def get_authed_client(access_token: str, refresh_token: str = "") -> "Client":
    if not SUPABASE_ENABLED:
        raise RuntimeError(SUPABASE_CONFIG_ERROR or "Supabase is not configured.")
    if not create_client:
        raise RuntimeError("Supabase SDK import is unavailable.")
    authed: "Client" = create_client(SUPABASE_URL, SUPABASE_KEY)
    if access_token and access_token.strip():
        authed.postgrest.auth(access_token)
        if refresh_token and refresh_token.strip():
            authed.auth.set_session(access_token, refresh_token)
    return authed


def get_service_client() -> "Client":
    if not SUPABASE_SERVICE_ROLE_ENABLED or not supabase_service:
        raise RuntimeError(
            "Supabase service role is not configured. "
            "Set SUPABASE_SERVICE_ROLE_KEY in .env and restart."
        )
    return supabase_service
