from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, has_request_context
from supabase_client import (
    supabase,
    get_service_client,
    is_supabase_enabled,
    is_supabase_service_role_enabled,
    get_supabase_config_error,
)
from dotenv import load_dotenv
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.exceptions import HTTPException
import sqlite3
import uuid
import re
import os
import json
import base64
import html
import tempfile
import random
import smtplib
from collections import Counter
from datetime import datetime, timezone, timedelta
from itertools import product
from email.message import EmailMessage
from email.utils import formataddr

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))
load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "freshwash-secret-key-2024")
ADMIN_AVATAR_BUCKET = (os.environ.get("FRESHWASH_AVATAR_BUCKET") or "avatars").strip()
GCASH_ACCOUNT_NAME = os.environ.get("GCASH_ACCOUNT_NAME", "FreshWash Laundry")
GCASH_NUMBER = os.environ.get("GCASH_NUMBER", "09XX XXX XXXX")
GCASH_QR_IMAGE = os.environ.get("GCASH_QR_IMAGE", "images/gcash.jpg")
PAYMAYA_ACCOUNT_NAME = os.environ.get("PAYMAYA_ACCOUNT_NAME", GCASH_ACCOUNT_NAME)
PAYMAYA_NUMBER = os.environ.get("PAYMAYA_NUMBER", "09XX XXX XXXX")
PAYMAYA_QR_IMAGE = os.environ.get("PAYMAYA_QR_IMAGE", "images/paymaya.jpg")
PAYMENT_METHOD_CONFIG = {
    "GCash": {
        "label": "GCash",
        "account_name": GCASH_ACCOUNT_NAME,
        "mobile_number": GCASH_NUMBER,
        "qr_image": GCASH_QR_IMAGE,
        "copy_label": "Copy GCash number",
    },
    "Maya": {
        "label": "Maya",
        "account_name": PAYMAYA_ACCOUNT_NAME,
        "mobile_number": PAYMAYA_NUMBER,
        "qr_image": PAYMAYA_QR_IMAGE,
        "copy_label": "Copy Maya number",
    },
}
DIGITAL_PAYMENT_METHODS = set(PAYMENT_METHOD_CONFIG)
VALID_PAYMENT_METHODS = {"Cash on Pickup", "Cash on Delivery", *DIGITAL_PAYMENT_METHODS}
MAX_PAYMENT_PROOF_BYTES = 2 * 1024 * 1024
DEFAULT_DELIVERY_FEE = float(os.environ.get("FRESHWASH_DELIVERY_FEE", "50") or 50)


def resolve_instance_path():
    configured_path = os.environ.get("FRESHWASH_INSTANCE_DIR", "").strip()
    candidates = [configured_path] if configured_path else []
    candidates.append(app.instance_path)
    if os.environ.get("VERCEL"):
        candidates.insert(0, os.path.join(tempfile.gettempdir(), "freshwash-instance"))

    last_error = None
    for path in candidates:
        if not path:
            continue
        try:
            os.makedirs(path, exist_ok=True)
            return path
        except OSError as exc:
            last_error = exc
            print("ERROR: could not initialize instance path:", path, str(exc))

    fallback_path = os.path.join(tempfile.gettempdir(), "freshwash-instance")
    os.makedirs(fallback_path, exist_ok=True)
    if last_error:
        print("ERROR: falling back to temp instance path because default paths failed:", str(last_error))
    return fallback_path


app.instance_path = resolve_instance_path()
LOCAL_AUTH_DB = os.path.join(app.instance_path, "freshwash_auth.db")
LOCAL_USERS_JSON = os.path.join(app.instance_path, "freshwash_users.json")

SERVICES = {
    "Wash & Fold":  {"price": 150, "desc": "Clean and neatly folded laundry delivered to your door."},
    "Wash & Iron":  {"price": 200, "desc": "Washed and professionally ironed for a crisp finish."},
    "Dry Cleaning": {"price": 250, "desc": "Gentle dry cleaning for delicate and special garments."},
    "Premium Wash": {"price": 350, "desc": "Premium treatment with fabric softener and extra care."},
}

HOMEPAGE_SERVICES = [
    {
        "name": "Wash",
        "description": "Professional washing with premium detergents",
        "price_prefix": "From",
        "price_value": "₱150 / kg",
        "icon": "fa-soap",
        "accent": "bubble",
    },
    {
        "name": "Dry Clean",
        "description": "Gentle dry cleaning for delicate fabrics",
        "price_prefix": "From",
        "price_value": "₱250 / piece",
        "icon": "fa-shirt",
        "accent": "lavender",
    },
    {
        "name": "Fold & Pack",
        "description": "Expertly folded and neatly packed",
        "price_prefix": "From",
        "price_value": "₱99 / kg",
        "icon": "fa-box-open",
        "accent": "sky",
    },
    {
        "name": "Iron & Press",
        "description": "Crisp ironing for a sharp look",
        "price_prefix": "From",
        "price_value": "₱129 / piece",
        "icon": "fa-fire-flame-curved",
        "accent": "sunrise",
    },
    ]

MACHINE_TYPE_CONTENT = {
    "Light": {
        "title": "Light Load Machine",
        "description": "Ideal for daily wear, smaller loads, and quick refresh cycles.",
        "icon": "fa-shirt",
        "accent": "bubble",
    },
    "Medium": {
        "title": "Medium Load Machine",
        "description": "Balanced capacity for mixed garments, towels, and regular weekly laundry.",
        "icon": "fa-box-open",
        "accent": "lavender",
    },
    "Heavy": {
        "title": "Heavy Load Machine",
        "description": "Built for bulky fabrics, bedding, and larger household loads.",
        "icon": "fa-drum-steelpan",
        "accent": "sunrise",
    },
}

ADMIN_SERVICE_DEFAULTS = {
    "Wash & Dry Clean": {"price": 249, "desc": "Combined wash and dry clean workflow for mixed laundry loads."},
    "Fold & Pack": {"price": 99, "desc": "Freshly folded and packed items ready for pickup or delivery."},
    "Iron & Press": {"price": 129, "desc": "Pressed shirts, uniforms, and garments with a crisp finish."},
    "Pickup & Delivery": {"price": 79, "desc": "Door-to-door laundry collection and return scheduling."},
}

ADMIN_SETTINGS_DEFAULTS = {
    "shop_name": "FreshWash",
    "contact_number": "",
    "shop_address": "",
    "default_load_types": json.dumps(["Light", "Medium", "Heavy"]),
    "machines_globally_enabled": "true",
    "theme_mode": "light",
    "theme_accent": "pink-rose",
}

DEFAULT_MACHINE_ROWS = [
    {
        "machine_number": number,
        "name": f"Machine {number}",
        "status": "Available" if number % 3 else "In Use",
        "load_type": "Light" if number in {1, 4, 8} else ("Medium" if number in {2, 5, 7} else "Heavy"),
        "enabled": 1,
    }
    for number in range(1, 9)
]

VALID_MACHINE_STATUSES = {"Available", "In Use", "Disabled"}

EMAIL_RE = re.compile(r"^[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}$", re.IGNORECASE)
PHONE_E164_RE = re.compile(r"^\+[1-9]\d{7,14}$")


def env_flag(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return bool(default)
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


OTP_LENGTH = 6
OTP_EXPIRY_MINUTES = 1
OTP_MAX_ATTEMPTS = int(os.environ.get("FRESHWASH_OTP_MAX_ATTEMPTS", "3") or 3)
OTP_RESEND_COOLDOWN_SECONDS = int(os.environ.get("FRESHWASH_OTP_RESEND_COOLDOWN_SECONDS", "60") or 60)
ENABLE_LOGIN_OTP = env_flag("ENABLE_LOGIN_OTP", default=env_flag("FRESHWASH_ENABLE_LOGIN_OTP", default=False))
VERIFICATION_SEND_COOLDOWN_SECONDS = OTP_RESEND_COOLDOWN_SECONDS


def otp_email_configured():
    cfg = otp_smtp_settings()
    return bool(cfg["username"] and cfg["password"] and cfg["sender_email"])


def otp_setup_message():
    cfg = otp_smtp_settings()
    missing = []
    if not cfg["username"]:
        missing.append("EMAIL_USER or FRESHWASH_OTP_SMTP_USER")
    if not cfg["password"]:
        missing.append("EMAIL_PASS or FRESHWASH_OTP_SMTP_PASSWORD")
    if not cfg["sender_email"]:
        missing.append("FRESHWASH_OTP_SENDER_EMAIL")
    if missing:
        return f"OTP email is not configured on this server. Set {', '.join(missing)} in .env."
    return "OTP email is not configured on this server."


def safe_email_for_log(email):
    normalized = normalize_email(email or "")
    if "@" not in normalized:
        return "<missing>"
    local, domain = normalized.split("@", 1)
    if len(local) <= 2:
        masked_local = "*" * len(local)
    else:
        masked_local = local[:2] + ("*" * (len(local) - 2))
    return f"{masked_local}@{domain}"


def validate_otp_email_configuration():
    if otp_email_configured():
        cfg = otp_smtp_settings()
        print(
            "AUTH: OTP SMTP is configured.",
            f"host={cfg['host']}",
            f"port={cfg['port']}",
            f"sender={cfg['sender_email']}",
        )
    else:
        print(f"AUTH: warning | {otp_setup_message()}")


def otp_smtp_settings():
    username = (
        os.environ.get("EMAIL_USER")
        or os.environ.get("FRESHWASH_OTP_SMTP_USER")
        or os.environ.get("BREVO_SMTP_LOGIN")
        or ""
    ).strip()
    password = (
        os.environ.get("EMAIL_PASS")
        or os.environ.get("FRESHWASH_OTP_SMTP_PASSWORD")
        or os.environ.get("BREVO_SMTP_KEY")
        or ""
    ).replace(" ", "").strip()
    sender_email = (
        os.environ.get("FRESHWASH_OTP_SENDER_EMAIL")
        or os.environ.get("BREVO_SENDER_EMAIL")
        or os.environ.get("FRESHWASH_OTP_FROM_EMAIL")
        or (username if "@" in username else "")
    ).strip()
    sender_name = (
        os.environ.get("FRESHWASH_OTP_SENDER_NAME")
        or os.environ.get("BREVO_SENDER_NAME")
        or "FreshWash"
    ).strip()
    host = (os.environ.get("FRESHWASH_OTP_SMTP_HOST") or "smtp.gmail.com").strip()
    try:
        port = int(os.environ.get("FRESHWASH_OTP_SMTP_PORT", "587") or 587)
    except ValueError:
        port = 587
    use_tls = env_flag("FRESHWASH_OTP_SMTP_TLS", default=True)
    return {
        "host": host,
        "port": port,
        "use_tls": use_tls,
        "username": username,
        "password": password,
        "sender_email": sender_email,
        "sender_name": sender_name,
    }


def backup_corrupt_local_auth_db():
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    for suffix in ("", "-journal", "-wal", "-shm"):
        source = f"{LOCAL_AUTH_DB}{suffix}"
        if not os.path.exists(source):
            continue
        destination = f"{LOCAL_AUTH_DB}.corrupt-{timestamp}{suffix}"
        try:
            os.replace(source, destination)
        except OSError:
            pass


def _init_local_auth_db():
    with sqlite3.connect(LOCAL_AUTH_DB) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                full_name TEXT NOT NULL,
                phone TEXT NOT NULL,
                address TEXT NOT NULL,
                avatar TEXT DEFAULT '',
                role TEXT NOT NULL DEFAULT 'user',
                otp_code TEXT,
                otp_expiry TEXT,
                is_verified INTEGER NOT NULL DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS email_otps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL,
                purpose TEXT NOT NULL,
                otp_code TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                is_used INTEGER NOT NULL DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_email_otps_email_purpose
            ON email_otps(email, purpose, created_at DESC)
            """
        )
        columns = {row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
        if "role" not in columns:
            conn.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user'")
        if "otp_code" not in columns:
            conn.execute("ALTER TABLE users ADD COLUMN otp_code TEXT")
        if "otp_expiry" not in columns:
            conn.execute("ALTER TABLE users ADD COLUMN otp_expiry TEXT")
        if "is_verified" not in columns:
            conn.execute("ALTER TABLE users ADD COLUMN is_verified INTEGER NOT NULL DEFAULT 1")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS admin_machines (
                machine_number INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Available',
                load_type TEXT NOT NULL DEFAULT 'Medium',
                enabled INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        machine_columns = {row[1] for row in conn.execute("PRAGMA table_info(admin_machines)").fetchall()}
        if "name" not in machine_columns:
            conn.execute("ALTER TABLE admin_machines ADD COLUMN name TEXT")
            if "label" in machine_columns:
                conn.execute("UPDATE admin_machines SET name = COALESCE(name, label, '')")
            conn.execute("UPDATE admin_machines SET name = COALESCE(NULLIF(name, ''), 'Machine ' || machine_number)")
        if "load_type" not in machine_columns:
            conn.execute("ALTER TABLE admin_machines ADD COLUMN load_type TEXT NOT NULL DEFAULT 'Medium'")
        if "updated_at" not in machine_columns:
            conn.execute("ALTER TABLE admin_machines ADD COLUMN updated_at TEXT")
            conn.execute("UPDATE admin_machines SET updated_at = CURRENT_TIMESTAMP WHERE updated_at IS NULL")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS admin_services (
                name TEXT PRIMARY KEY,
                price REAL NOT NULL,
                description TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS admin_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        for machine in DEFAULT_MACHINE_ROWS:
            conn.execute(
                """
                INSERT OR IGNORE INTO admin_machines (machine_number, name, status, load_type, enabled)
                VALUES (?, ?, ?, ?, ?)
                """,
                (machine["machine_number"], machine["name"], machine["status"], machine["load_type"], machine["enabled"])
            )
        for name, data in ADMIN_SERVICE_DEFAULTS.items():
            conn.execute(
                """
                INSERT OR IGNORE INTO admin_services (name, price, description)
                VALUES (?, ?, ?)
                """,
                (name, data["price"], data["desc"])
            )
        for key, value in ADMIN_SETTINGS_DEFAULTS.items():
            conn.execute(
                """
                INSERT OR IGNORE INTO admin_settings (key, value)
                VALUES (?, ?)
                """,
                (key, value)
            )


def init_local_auth_db():
    try:
        _init_local_auth_db()
    except sqlite3.OperationalError as error:
        if "disk i/o" not in str(error).lower():
            raise
        backup_corrupt_local_auth_db()
        try:
            _init_local_auth_db()
        except sqlite3.OperationalError as retry_error:
            if "disk i/o" not in str(retry_error).lower():
                raise
            print(
                "ERROR: local auth database remains unavailable; continuing with JSON auth fallback:",
                str(retry_error),
            )


def local_auth_conn():
    conn = None
    try:
        conn = sqlite3.connect(LOCAL_AUTH_DB)
        check = conn.execute("PRAGMA integrity_check").fetchone()
        if not check or check[0] != "ok":
            raise sqlite3.OperationalError("Local auth database integrity check failed.")
    except sqlite3.OperationalError as error:
        message = str(error).lower()
        if conn is not None:
            conn.close()
        if "disk i/o" not in message and "integrity check failed" not in message:
            raise
        backup_corrupt_local_auth_db()
        _init_local_auth_db()
        conn = sqlite3.connect(LOCAL_AUTH_DB)
    conn.row_factory = sqlite3.Row
    return conn


def normalize_email(email):
    return email.strip().lower()


def normalize_phone(phone):
    raw = re.sub(r"[^\d+]", "", str(phone or "").strip())
    if not raw:
        return ""
    if raw.startswith("00"):
        raw = "+" + raw[2:]
    if raw.startswith("0"):
        raw = "+63" + raw[1:]
    elif raw.startswith("63"):
        raw = "+" + raw
    elif not raw.startswith("+"):
        raw = "+" + raw
    return raw


def configured_admin_emails():
    raw = os.environ.get("ADMIN_EMAILS", "")
    return {normalize_email(email) for email in raw.split(",") if email.strip()}


def is_valid_email(email):
    return bool(EMAIL_RE.match(normalize_email(email)))


def is_valid_phone(phone):
    return bool(PHONE_E164_RE.match(normalize_phone(phone)))


def masked_phone(phone):
    normalized = normalize_phone(phone)
    if not normalized:
        return ""
    if len(normalized) <= 7:
        return normalized
    return f"{normalized[:4]}{'*' * max(1, len(normalized) - 7)}{normalized[-3:]}"


def auth_template_context(form_data=None):
    return {"form_data": form_data or {}}


def render_auth_template(template_name, form_data=None):
    return render_template(template_name, **auth_template_context(form_data))


def log_exception(label, exc, **context):
    details = ", ".join(f"{key}={value!r}" for key, value in context.items())
    if details:
        print(f"ERROR: {label}: {type(exc).__name__}: {exc!r} | {details}")
    else:
        print(f"ERROR: {label}: {type(exc).__name__}: {exc!r}")


def log_auth_debug(label, **context):
    details = ", ".join(f"{key}={value!r}" for key, value in context.items())
    print(f"AUTH: {label}" + (f" | {details}" if details else ""))


def set_auth_modal_state(modal, form_data=None):
    session["auth_modal"] = modal
    session["auth_form_data"] = form_data or {}


def pop_auth_modal_state():
    return session.pop("auth_modal", None), session.pop("auth_form_data", {})


def redirect_to_auth_modal(modal, form_data=None):
    set_auth_modal_state(modal, form_data)
    return redirect(url_for("home"))


def parse_iso_datetime(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def generate_otp_code():
    upper = (10 ** OTP_LENGTH) - 1
    lower = 10 ** (OTP_LENGTH - 1)
    return str(random.randint(lower, upper))


def otp_modal_form_data(challenge=None):
    challenge = challenge or (session.get("pending_otp") or {})
    resend_at = parse_iso_datetime(challenge.get("resend_available_at"))
    remaining = max(0, int((resend_at - datetime.now(timezone.utc)).total_seconds())) if resend_at else 0
    return {
        "email": challenge.get("email", ""),
        "purpose": challenge.get("purpose", ""),
        "resend_cooldown": remaining,
        "attempts_remaining": int(challenge.get("attempts_remaining", OTP_MAX_ATTEMPTS) or OTP_MAX_ATTEMPTS),
    }


def set_pending_otp_challenge(email, purpose, pending_user=None, pending_signup=None):
    challenge = {
        "email": normalize_email(email),
        "purpose": purpose,
        "attempts_remaining": OTP_MAX_ATTEMPTS,
        "resend_available_at": (datetime.now(timezone.utc) + timedelta(seconds=OTP_RESEND_COOLDOWN_SECONDS)).isoformat(),
    }
    if pending_user:
        challenge["pending_user"] = compact_session_user(pending_user)
    if isinstance(pending_signup, dict) and pending_signup:
        challenge["pending_signup"] = {
            "full_name": str(pending_signup.get("full_name", "") or "").strip(),
            "email": normalize_email(pending_signup.get("email", email)),
            "phone": str(pending_signup.get("phone", "") or "").strip(),
            "address": str(pending_signup.get("address", "") or "").strip(),
            "role": normalize_profile_role(pending_signup.get("role", "user")),
            "password": str(pending_signup.get("password", "") or ""),
        }
    session["pending_otp"] = challenge
    session.modified = True
    return challenge


def get_pending_otp_challenge():
    challenge = session.get("pending_otp")
    if not challenge:
        return None
    return challenge


def clear_pending_otp_challenge():
    session.pop("pending_otp", None)
    session.modified = True


def _verification_send_cache():
    cache = session.get("verification_send_cache")
    if not isinstance(cache, dict):
        cache = {}
    return cache


def verification_send_key(email, purpose):
    return f"{normalize_email(email)}::{(purpose or 'signup').strip().lower()}"


def verification_send_wait_seconds(email, purpose):
    cache = _verification_send_cache()
    key = verification_send_key(email, purpose)
    last_sent_iso = cache.get(key)
    last_sent = parse_iso_datetime(last_sent_iso)
    if not last_sent:
        return 0
    if isinstance(last_sent, datetime) and last_sent.tzinfo is None:
        last_sent = last_sent.replace(tzinfo=timezone.utc)
    next_allowed = last_sent + timedelta(seconds=VERIFICATION_SEND_COOLDOWN_SECONDS)
    remaining = int((next_allowed - datetime.now(timezone.utc)).total_seconds())
    return max(0, remaining)


def resend_wait_message(wait_seconds):
    return f"Resend code in {max(1, int(wait_seconds))}s"


def mark_verification_send(email, purpose):
    cache = _verification_send_cache()
    key = verification_send_key(email, purpose)
    cache[key] = datetime.now(timezone.utc).isoformat()
    session["verification_send_cache"] = cache
    session.modified = True


def resolve_supabase_email_redirect_to():
    configured = (os.environ.get("FRESHWASH_SUPABASE_EMAIL_REDIRECT_TO") or "").strip()
    if configured:
        return configured
    if has_request_context():
        try:
            return url_for("home", _external=True)
        except Exception:
            return ""
    return ""


def extract_supabase_error_message(error):
    if error is None:
        return "Unknown error."

    message = getattr(error, "message", None)
    if isinstance(message, str) and message.strip():
        return message.strip()
    details = getattr(error, "details", None)
    if isinstance(details, str) and details.strip():
        return details.strip()
    error_description = getattr(error, "error_description", None)
    if isinstance(error_description, str) and error_description.strip():
        return error_description.strip()

    if isinstance(error, dict):
        for key in ("message", "error_description", "details", "error"):
            value = error.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        try:
            serialized = json.dumps(error, default=str)
            if serialized and serialized != "{}":
                return serialized
        except Exception:
            pass

    args = getattr(error, "args", None)
    if isinstance(args, tuple):
        for arg in args:
            if isinstance(arg, str) and arg.strip():
                return arg.strip()

    try:
        payload = getattr(error, "__dict__", None)
        if isinstance(payload, dict) and payload:
            serialized = json.dumps(payload, default=str)
            if serialized and serialized != "{}":
                return serialized
    except Exception:
        pass

    fallback = str(error or "").strip()
    if fallback:
        return fallback
    return "Unknown error."


def classify_otp_send_error(raw_message):
    lowered = (raw_message or "").lower()
    if not lowered:
        return ""
    if "email rate limit exceeded" in lowered or "rate limit" in lowered:
        return "Please wait before requesting another code."
    if "authentication" in lowered or "badcredentials" in lowered or "535" in lowered:
        return "Invalid SMTP credentials. Check EMAIL_USER and EMAIL_PASS in .env, then restart FreshWash."
    if "not authorized" in lowered or "email address not authorized" in lowered:
        return "Email address is not authorized for OTP delivery."
    if "smtp" in lowered and ("not configured" in lowered or "disabled" in lowered or "provider" in lowered):
        return "Email could not be sent. Check SMTP configuration."
    return ""


def otp_send_failure_message():
    return "Verification code was not sent. Check SMTP settings and try again."


def otp_send_delivery_note():
    return "If no code arrives, check spam folder or verify your Brevo sender configuration."


def send_otp_email(email, otp_code):
    cfg = otp_smtp_settings()
    username = cfg["username"]
    password = cfg["password"]

    if not username or not password:
        raise RuntimeError("OTP email is not configured on this server.")

    email = normalize_email(email)
    if not email:
        raise ValueError("Email is required for verification.")
    if not is_valid_email(email):
        raise ValueError("Enter a valid email address.")

    print(f"AUTH: SMTP config loaded | host={cfg['host']} port={cfg['port']} user={username} sender={cfg['sender_email']}")
    print(f"AUTH: Sending OTP to {safe_email_for_log(email)}")

    subject = "FreshWash Verification Code"
    text_body = (
        f"Your FreshWash verification code is: {otp_code}\n"
        f"This code will expire in {OTP_EXPIRY_MINUTES} minutes."
    )
    try:
        html_body = render_template("email_verification.html", otp_code=otp_code, expiry_minutes=OTP_EXPIRY_MINUTES)
    except Exception:
        html_body = (
            f"<h2>FreshWash Verification Code</h2>"
            f"<p>Your code: <strong>{otp_code}</strong></p>"
            f"<p>Expires in {OTP_EXPIRY_MINUTES} minutes.</p>"
        )

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = formataddr((cfg["sender_name"], cfg["sender_email"]))
    message["To"] = email
    message.set_content(text_body)
    message.add_alternative(html_body, subtype="html")

    try:
        with smtplib.SMTP(cfg["host"], cfg["port"], timeout=30) as smtp:
            smtp.ehlo()
            if cfg["use_tls"]:
                smtp.starttls()
                smtp.ehlo()
            try:
                smtp.login(username, password)
            except smtplib.SMTPAuthenticationError as auth_exc:
                print(f"AUTH: SMTP ERROR: {auth_exc}")
                raise ValueError("Invalid Gmail App Password or Gmail credentials.") from auth_exc
            smtp.send_message(message)
        print(f"AUTH: Email sent successfully to {safe_email_for_log(email)}")
    except ValueError:
        raise
    except Exception as exc:
        print(f"AUTH: SMTP ERROR: {exc}")
        log_exception("otp email send failed", exc, email=safe_email_for_log(email), smtp_host=cfg["host"])
        normalized_message = extract_supabase_error_message(exc)
        classified = classify_otp_send_error(normalized_message)
        if classified:
            raise ValueError(classified) from exc
        raise ValueError(f"Failed to send verification. SMTP error: {normalized_message}") from exc

    log_auth_debug("email sending result", email=safe_email_for_log(email), status="sent")


def send_booking_email(email, booking_data):
    cfg = otp_smtp_settings()
    username = cfg["username"]
    password = cfg["password"]
    if not username or not password:
        raise RuntimeError("Booking email is not configured on this server.")

    recipient = normalize_email(email or "")
    if not recipient:
        raise ValueError("Booking email recipient is required.")
    if not is_valid_email(recipient):
        raise ValueError("Enter a valid recipient email address.")

    service_type = booking_data.get("service_type", "")
    machine = booking_data.get("machine", "")
    load_type = booking_data.get("load_type", "")
    pickup_date = booking_data.get("pickup_date", "")
    pickup_time = booking_data.get("pickup_time", "")
    delivery_option = booking_data.get("delivery_option", "")
    total_price = booking_data.get("total_price", 0)
    total_display = f"PHP {total_price}"

    service_type_safe = html.escape(str(service_type or "-"))
    machine_safe = html.escape(str(machine or "-"))
    load_type_safe = html.escape(str(load_type or "-"))
    pickup_date_safe = html.escape(str(pickup_date or "-"))
    pickup_time_safe = html.escape(str(pickup_time or "-"))
    delivery_option_safe = html.escape(str(delivery_option or "-"))
    total_display_safe = html.escape(total_display)

    subject = "FreshWash Booking Confirmation"
    text_body = (
        "Your FreshWash booking is confirmed.\n\n"
        f"Service: {service_type}\n"
        f"Machine: {machine}\n"
        f"Load Type: {load_type}\n"
        f"Pickup Date: {pickup_date}\n"
        f"Pickup Time: {pickup_time}\n"
        f"Delivery Option: {delivery_option}\n"
        f"Estimated Total: {total_display}\n\n"
        "Thank you for choosing FreshWash."
    )
    html_body = (
        "<!doctype html>"
        "<html>"
        "<body style=\"margin:0;padding:0;background:#fff4fa;font-family:Arial,Helvetica,sans-serif;color:#3f2235;\">"
        "<table role=\"presentation\" cellpadding=\"0\" cellspacing=\"0\" border=\"0\" width=\"100%\" style=\"background:#fff4fa;padding:20px 0;\">"
        "<tr><td align=\"center\">"
        "<table role=\"presentation\" cellpadding=\"0\" cellspacing=\"0\" border=\"0\" width=\"100%\" style=\"max-width:640px;\">"
        "<tr><td style=\"padding:0 16px;\">"
        "<table role=\"presentation\" cellpadding=\"0\" cellspacing=\"0\" border=\"0\" width=\"100%\" style=\"border-radius:22px;overflow:hidden;background:#ffffff;box-shadow:0 12px 30px rgba(255,105,180,0.16);\">"
        "<tr>"
        "<td style=\"padding:22px 24px;background:linear-gradient(135deg,#ff4da6,#ff7ac3);color:#ffffff;text-align:center;\">"
        "<div style=\"font-size:22px;line-height:1.25;font-weight:700;\">FreshWash Booking Confirmation</div>"
        "</td>"
        "</tr>"
        "<tr>"
        "<td style=\"padding:22px 24px;\">"
        "<div style=\"display:inline-block;padding:6px 12px;border-radius:999px;background:#ffe3f1;color:#c03581;font-size:12px;font-weight:700;\">Confirmed</div>"
        "<p style=\"margin:14px 0 18px;font-size:15px;line-height:1.6;color:#5a3950;\">Your booking is confirmed. Here are your booking details:</p>"
        "<table role=\"presentation\" cellpadding=\"0\" cellspacing=\"0\" border=\"0\" width=\"100%\" style=\"border-collapse:separate;border-spacing:0;border:1px solid #ffd8ea;border-radius:14px;overflow:hidden;background:#fff9fc;\">"
        f"<tr><td style=\"padding:11px 14px;border-bottom:1px solid #ffe4f0;font-size:14px;color:#7b5a70;\">Service</td><td style=\"padding:11px 14px;border-bottom:1px solid #ffe4f0;font-size:14px;font-weight:600;color:#341c2e;text-align:right;\">{service_type_safe}</td></tr>"
        f"<tr><td style=\"padding:11px 14px;border-bottom:1px solid #ffe4f0;font-size:14px;color:#7b5a70;\">Machine</td><td style=\"padding:11px 14px;border-bottom:1px solid #ffe4f0;font-size:14px;font-weight:600;color:#341c2e;text-align:right;\">{machine_safe}</td></tr>"
        f"<tr><td style=\"padding:11px 14px;border-bottom:1px solid #ffe4f0;font-size:14px;color:#7b5a70;\">Load Type</td><td style=\"padding:11px 14px;border-bottom:1px solid #ffe4f0;font-size:14px;font-weight:600;color:#341c2e;text-align:right;\">{load_type_safe}</td></tr>"
        f"<tr><td style=\"padding:11px 14px;border-bottom:1px solid #ffe4f0;font-size:14px;color:#7b5a70;\">Pickup Date</td><td style=\"padding:11px 14px;border-bottom:1px solid #ffe4f0;font-size:14px;font-weight:600;color:#341c2e;text-align:right;\">{pickup_date_safe}</td></tr>"
        f"<tr><td style=\"padding:11px 14px;border-bottom:1px solid #ffe4f0;font-size:14px;color:#7b5a70;\">Pickup Time</td><td style=\"padding:11px 14px;border-bottom:1px solid #ffe4f0;font-size:14px;font-weight:600;color:#341c2e;text-align:right;\">{pickup_time_safe}</td></tr>"
        f"<tr><td style=\"padding:11px 14px;border-bottom:1px solid #ffe4f0;font-size:14px;color:#7b5a70;\">Delivery Option</td><td style=\"padding:11px 14px;border-bottom:1px solid #ffe4f0;font-size:14px;font-weight:600;color:#341c2e;text-align:right;\">{delivery_option_safe}</td></tr>"
        f"<tr><td style=\"padding:12px 14px;font-size:14px;color:#7b5a70;\">Estimated Total</td><td style=\"padding:12px 14px;font-size:15px;font-weight:700;color:#bf2d79;text-align:right;\">{total_display_safe}</td></tr>"
        "</table>"
        "<p style=\"margin:18px 0 0;font-size:14px;line-height:1.6;color:#5a3950;\">Thank you for choosing FreshWash. We appreciate your trust in us.</p>"
        "</td>"
        "</tr>"
        "<tr>"
        "<td style=\"padding:14px 20px;text-align:center;background:#fff0f7;font-size:12px;color:#8e6882;\">&copy; 2026 FreshWash. Fresh. Clean. You.</td>"
        "</tr>"
        "</table>"
        "</td></tr>"
        "</table>"
        "</td></tr>"
        "</table>"
        "</body>"
        "</html>"
    )

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = formataddr((cfg["sender_name"], cfg["sender_email"]))
    message["To"] = recipient
    message.set_content(text_body)
    message.add_alternative(html_body, subtype="html")

    with smtplib.SMTP(cfg["host"], cfg["port"], timeout=30) as smtp:
        smtp.ehlo()
        if cfg["use_tls"]:
            smtp.starttls()
            smtp.ehlo()
        smtp.login(username, password)
        smtp.send_message(message)


def set_verification_state(email, is_verified):
    email = normalize_email(email)
    if local_auth_enabled():
        user, users = find_local_user(email)
        if not user:
            raise ValueError("Account not found.")
        user["is_verified"] = bool(is_verified)
        save_local_users(users)
        return

    client = admin_db_client()
    if not client:
        raise RuntimeError("Verification needs an available database connection.")
    client.table("profiles").update({"is_verified": bool(is_verified)}).eq("email", email).execute()


def set_otp_for_account(email, otp_code, otp_expiry):
    email = normalize_email(email)
    expiry_value = otp_expiry.isoformat() if isinstance(otp_expiry, datetime) else str(otp_expiry or "")
    if local_auth_enabled():
        user, users = find_local_user(email)
        if not user:
            raise ValueError("Account not found.")
        user["otp_code"] = otp_code or ""
        user["otp_expiry"] = expiry_value if otp_code else ""
        save_local_users(users)
        return

    client = admin_db_client()
    if not client:
        raise RuntimeError("OTP setup needs an available database connection.")
    payload = {"otp_code": otp_code or "", "otp_expiry": expiry_value if otp_code else None}
    client.table("profiles").update(payload).eq("email", email).execute()


def clear_otp_for_account(email):
    set_otp_for_account(email, "", "")


def store_email_otp(email, purpose, otp_code, expires_at):
    normalized_email = normalize_email(email)
    normalized_purpose = (purpose or "signup").strip().lower()
    expiry_value = expires_at.isoformat() if isinstance(expires_at, datetime) else str(expires_at or "")
    now_iso = datetime.now(timezone.utc).isoformat()
    with local_auth_conn() as conn:
        conn.execute(
            "UPDATE email_otps SET is_used = 1 WHERE email = ? AND purpose = ? AND is_used = 0",
            (normalized_email, normalized_purpose),
        )
        conn.execute(
            """
            INSERT INTO email_otps (email, purpose, otp_code, expires_at, is_used, created_at)
            VALUES (?, ?, ?, ?, 0, ?)
            """,
            (normalized_email, normalized_purpose, str(otp_code), expiry_value, now_iso),
        )


def get_email_otp(email, purpose):
    normalized_email = normalize_email(email)
    normalized_purpose = (purpose or "signup").strip().lower()
    with local_auth_conn() as conn:
        row = conn.execute(
            """
            SELECT id, email, purpose, otp_code, expires_at, is_used, created_at
            FROM email_otps
            WHERE email = ? AND purpose = ? AND is_used = 0
            ORDER BY datetime(created_at) DESC, id DESC
            LIMIT 1
            """,
            (normalized_email, normalized_purpose),
        ).fetchone()
    if not row:
        return None
    return {
        "id": row["id"],
        "email": row["email"],
        "purpose": row["purpose"],
        "otp_code": str(row["otp_code"] or ""),
        "expires_at": parse_iso_datetime(row["expires_at"]),
        "is_used": bool(row["is_used"]),
        "created_at": parse_iso_datetime(row["created_at"]),
    }


def mark_email_otp_used(record_id):
    if not record_id:
        return
    with local_auth_conn() as conn:
        conn.execute("UPDATE email_otps SET is_used = 1 WHERE id = ?", (record_id,))


def clear_email_otps(email, purpose=None):
    normalized_email = normalize_email(email)
    with local_auth_conn() as conn:
        if purpose:
            normalized_purpose = (purpose or "signup").strip().lower()
            conn.execute(
                "UPDATE email_otps SET is_used = 1 WHERE email = ? AND purpose = ? AND is_used = 0",
                (normalized_email, normalized_purpose),
            )
        else:
            conn.execute(
                "UPDATE email_otps SET is_used = 1 WHERE email = ? AND is_used = 0",
                (normalized_email,),
            )


def get_account_security_state(email):
    email = normalize_email(email)
    if local_auth_enabled():
        user, _ = find_local_user(email)
        if not user:
            return None
        return {
            "email": user["email"],
            "is_verified": bool(user.get("is_verified", True)),
            "otp_code": str(user.get("otp_code", "") or ""),
            "otp_expiry": parse_iso_datetime(user.get("otp_expiry")),
        }

    client = admin_db_client()
    if not client:
        raise RuntimeError("Account lookup needs an available database connection.")
    result = client.table("profiles").select("email,is_verified,otp_code,otp_expiry").eq("email", email).limit(1).execute()
    rows = result.data or []
    if not rows:
        return None
    row = rows[0]
    has_verified_flag = "is_verified" in row and row.get("is_verified") is not None
    return {
        "email": row.get("email", email),
        "is_verified": bool(row.get("is_verified")) if has_verified_flag else True,
        "otp_code": str(row.get("otp_code", "") or ""),
        "otp_expiry": parse_iso_datetime(row.get("otp_expiry")),
    }


def issue_otp_challenge(email, purpose, pending_user=None, trigger_send=True, pending_signup=None):
    email = normalize_email(email)
    normalized_purpose = (purpose or "signup").strip().lower()

    if trigger_send:
        wait_seconds = verification_send_wait_seconds(email, normalized_purpose)
        if wait_seconds > 0:
            raise ValueError(resend_wait_message(wait_seconds))
        otp_code = generate_otp_code()
        otp_expiry = datetime.now(timezone.utc) + timedelta(minutes=OTP_EXPIRY_MINUTES)
        log_auth_debug(
            "otp generation result",
            email=safe_email_for_log(email),
            purpose=normalized_purpose,
            expires_at=otp_expiry.isoformat(),
        )
        store_email_otp(email, normalized_purpose, otp_code, otp_expiry)
        try:
            set_otp_for_account(email, otp_code, otp_expiry)
        except Exception as storage_error:
            log_exception("otp profile storage skipped", storage_error, email=safe_email_for_log(email))
        try:
            send_otp_email(email, otp_code)
        except Exception:
            clear_email_otps(email, normalized_purpose)
            try:
                clear_otp_for_account(email)
            except Exception:
                pass
            raise
        mark_verification_send(email, normalized_purpose)
    challenge = set_pending_otp_challenge(
        email,
        normalized_purpose,
        pending_user=pending_user,
        pending_signup=pending_signup,
    )
    return challenge


def user_role_for_email(email, stored_role="user", metadata=None):
    metadata = metadata or {}
    stored_role = (stored_role or "").strip().lower()
    metadata_role = str(metadata.get("role", "") or "").strip().lower()
    if stored_role == "admin" or metadata_role == "admin" or metadata.get("is_admin"):
        return "admin"
    if normalize_email(email) in configured_admin_emails():
        return "admin"
    return "user"


def normalize_profile_role(role):
    normalized_role = (role or "").strip().lower()
    if normalized_role not in {"admin", "user"}:
        raise ValueError("Your account role is missing or invalid. Please contact FreshWash support.")
    return normalized_role


def admin_db_client():
    if is_supabase_service_role_enabled():
        return get_service_client()
    if supabase:
        return supabase
    return None


def has_any_profile_rows():
    client = admin_db_client()
    if not client:
        return False
    try:
        result = client.table("profiles").select("id", count="exact").limit(1).execute()
        return bool(getattr(result, "count", 0))
    except Exception:
        return False


def resolve_registration_role(email):
    normalized_email = normalize_email(email)
    if normalized_email in configured_admin_emails():
        return "admin"
    if is_supabase_enabled() and not has_any_profile_rows():
        return "admin"
    return "user"


def safe_auth_user_email(auth_user):
    return normalize_email(getattr(auth_user, "email", "") or "")


def safe_auth_user_metadata(auth_user):
    metadata = getattr(auth_user, "user_metadata", None)
    return metadata if isinstance(metadata, dict) else {}


def resolve_signup_auth_user(signup_result, fallback_email=""):
    direct_user = getattr(signup_result, "user", None)
    if direct_user and getattr(direct_user, "id", None):
        return direct_user

    try:
        current_user_response = supabase.auth.get_user()
        user_from_get_user = (
            getattr(current_user_response, "user", None)
            or getattr(getattr(current_user_response, "data", None), "user", None)
        )
        if user_from_get_user and getattr(user_from_get_user, "id", None):
            return user_from_get_user
    except Exception as exc:
        log_exception("signup get_user fallback failed", exc, email=fallback_email)

    return None


def create_supabase_signup_user(name, email, phone, address, password, role, email_confirm=False):
    normalized_role = normalize_profile_role(role)
    metadata = {
        "full_name": name,
        "phone": phone,
        "address": address,
        "role": normalized_role,
    }

    if not is_supabase_service_role_enabled():
        raise RuntimeError(
            "SUPABASE_SERVICE_ROLE_KEY is required for OTP-only signup. "
            "Add it to .env so FreshWash can create users with OTP-code verification."
        )

    client = get_service_client()
    # Regular users rely on Supabase OTP verification; avoid auto link email.
    created = client.auth.admin.create_user({
        "email": email,
        "password": password,
        "email_confirm": bool(email_confirm or normalized_role == "admin"),
        "user_metadata": metadata,
    })
    created_user = getattr(created, "user", None) or getattr(getattr(created, "data", None), "user", None)
    if not created_user or not getattr(created_user, "id", None):
        # Surface the raw Supabase response so the exact error is visible
        raw_error = extract_supabase_error_message(created)
        raise RuntimeError(f"Supabase signup failed: {raw_error}")
    log_auth_debug(
        "auth signup result",
        email=email,
        has_user=True,
        has_session=False,
        provider="service_role_admin_create_user",
        role=normalized_role,
    )
    return created_user


def list_supabase_auth_users():
    if not is_supabase_service_role_enabled():
        return []
    client = get_service_client()
    try:
        response = client.auth.admin.list_users()
    except Exception as exc:
        log_exception("register auth users list failed", exc)
        return []

    if isinstance(response, dict):
        users = response.get("users") or (response.get("data") or {}).get("users") or []
        return users if isinstance(users, list) else []

    direct_users = getattr(response, "users", None)
    if isinstance(direct_users, list):
        return direct_users

    data = getattr(response, "data", None)
    nested_users = getattr(data, "users", None) if data is not None else None
    if isinstance(nested_users, list):
        return nested_users
    if isinstance(data, dict):
        users = data.get("users") or []
        return users if isinstance(users, list) else []
    return []


def find_supabase_auth_user_by_email(email):
    target = normalize_email(email)
    for auth_user in list_supabase_auth_users():
        if isinstance(auth_user, dict):
            auth_email = normalize_email(auth_user.get("email", ""))
        else:
            auth_email = safe_auth_user_email(auth_user)
        if auth_email == target:
            return auth_user
    return None


def find_profile_by_email(email):
    client = admin_db_client()
    if not client:
        return None
    try:
        result = client.table("profiles").select("*").eq("email", normalize_email(email)).limit(1).execute()
        rows = result.data or []
        return rows[0] if rows else None
    except Exception as exc:
        log_exception("register profile check failed", exc, email=email)
        return None


def recover_missing_profile_for_auth_user(auth_user, defaults):
    if not auth_user:
        return None
    try:
        profile = ensure_supabase_profile_record(auth_user, defaults)
        log_auth_debug(
            "registration recovered missing profile row",
            email=defaults.get("email", ""),
            user_id=getattr(auth_user, "id", ""),
            role=profile.get("role", ""),
        )
        return profile
    except Exception as exc:
        log_exception(
            "registration missing profile recovery failed",
            exc,
            email=defaults.get("email", ""),
            user_id=getattr(auth_user, "id", ""),
        )
        return None


def load_local_users():
    try:
        with local_auth_conn() as conn:
            rows = conn.execute(
                """
                SELECT id, email, password_hash, full_name, phone, address, avatar, role, otp_code, otp_expiry, is_verified, created_at
                FROM users
                ORDER BY datetime(created_at) DESC, email ASC
                """
            ).fetchall()
    except sqlite3.OperationalError:
        rows = []

    if rows:
        return [
            {
                "id": row["id"],
                "email": row["email"],
                "password_hash": row["password_hash"],
                "full_name": row["full_name"],
                "phone": row["phone"],
                "address": row["address"],
                "avatar": row["avatar"] or "",
                "role": row["role"] or "user",
                "otp_code": row["otp_code"] or "",
                "otp_expiry": row["otp_expiry"] or "",
                "is_verified": bool(row["is_verified"] if row["is_verified"] is not None else 1),
                "created_at": row["created_at"] or "",
            }
            for row in rows
        ]

    if not os.path.exists(LOCAL_USERS_JSON):
        return []

    try:
        with open(LOCAL_USERS_JSON, "r", encoding="utf-8") as handle:
            users = json.load(handle)
            if not isinstance(users, list):
                return []
    except (OSError, json.JSONDecodeError):
        return []

    # Migrate any legacy JSON-backed auth users into SQLite so login/register
    # use the database consistently.
    save_local_users(users)
    return users


def save_local_users(users):
    normalized_users = []
    seen_emails = set()

    for user in users or []:
        email = normalize_email(user.get("email", ""))
        if not email or email in seen_emails:
            continue
        seen_emails.add(email)
        normalized_users.append(
            {
                "id": user.get("id") or str(uuid.uuid4()),
                "email": email,
                "password_hash": user.get("password_hash", ""),
                "full_name": user.get("full_name", "").strip(),
                "phone": user.get("phone", "").strip(),
                "address": user.get("address", "").strip(),
                "avatar": user.get("avatar", "") or "",
                "role": user.get("role", "user") or "user",
                "otp_code": user.get("otp_code", "") or "",
                "otp_expiry": user.get("otp_expiry", "") or "",
                "is_verified": bool(user.get("is_verified", True)),
                "created_at": user.get("created_at") or datetime.now().isoformat(),
            }
        )

    with open(LOCAL_USERS_JSON, "w", encoding="utf-8") as handle:
        json.dump(normalized_users, handle, indent=2)

    try:
        with local_auth_conn() as conn:
            conn.execute("DELETE FROM users")
            for user in normalized_users:
                conn.execute(
                    """
                    INSERT INTO users (id, email, password_hash, full_name, phone, address, avatar, role, otp_code, otp_expiry, is_verified, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user["id"],
                        user["email"],
                        user["password_hash"],
                        user["full_name"],
                        user["phone"],
                        user["address"],
                        user["avatar"],
                        user["role"],
                        user["otp_code"],
                        user["otp_expiry"],
                        1 if user["is_verified"] else 0,
                        user["created_at"],
                    ),
                )
    except sqlite3.OperationalError as error:
        print("ERROR: could not sync local auth users to SQLite, JSON fallback remains active:", str(error))


def find_local_user(email):
    email = normalize_email(email)
    users = load_local_users()
    for user in users:
        if normalize_email(user.get("email", "")) == email:
            return user, users
    return None, users


def create_local_user(name, email, phone, address, password, role_override=None, is_verified=True):
    email = normalize_email(email)
    role = normalize_profile_role(role_override) if role_override else user_role_for_email(email)
    existing, users = find_local_user(email)
    if existing:
        raise ValueError("An account with that email already exists.")

    user_id = str(uuid.uuid4())
    users.append({
        "id": user_id,
        "email": email,
        "password_hash": generate_password_hash(password),
        "full_name": name,
        "phone": phone,
        "address": address,
        "avatar": "",
        "role": role,
        "otp_code": "",
        "otp_expiry": "",
        "is_verified": bool(is_verified),
        "created_at": datetime.now().isoformat(),
    })
    save_local_users(users)

    return {
        "id": user_id,
        "email": email,
        "name": name,
        "phone": phone,
        "address": address,
        "avatar": "",
        "role": role,
        "is_verified": bool(is_verified),
        "is_admin": role == "admin"
    }


def local_user_exists(email):
    existing, _ = find_local_user(email)
    return bool(existing)


def upsert_local_user(name, email, phone, address, password, role_override=None, is_verified=True):
    email = normalize_email(email)
    role = normalize_profile_role(role_override) if role_override else user_role_for_email(email)
    password_hash = generate_password_hash(password)
    existing, users = find_local_user(email)
    if existing:
        existing["password_hash"] = password_hash
        existing["full_name"] = name
        existing["phone"] = phone
        existing["address"] = address
        existing["role"] = role
        existing["is_verified"] = bool(existing.get("is_verified", is_verified))
        user_id = existing["id"]
        avatar = existing.get("avatar", "")
    else:
        user_id = str(uuid.uuid4())
        avatar = ""
        users.append({
            "id": user_id,
            "email": email,
            "password_hash": password_hash,
            "full_name": name,
            "phone": phone,
            "address": address,
            "avatar": avatar,
            "role": role,
            "otp_code": "",
            "otp_expiry": "",
            "is_verified": bool(is_verified),
            "created_at": datetime.now().isoformat(),
        })
    save_local_users(users)

    return {
        "id": user_id,
        "email": email,
        "name": name,
        "phone": phone,
        "address": address,
        "avatar": avatar,
        "role": role,
        "is_verified": bool(is_verified),
        "is_admin": role == "admin"
    }


def authenticate_local_user(email, password):
    email = normalize_email(email)
    user, _ = find_local_user(email)

    if not user or not check_password_hash(user.get("password_hash", ""), password):
        raise ValueError("Invalid email or password.")

    return {
        "id": user["id"],
        "email": user["email"],
        "name": user["full_name"],
        "phone": user.get("phone", ""),
        "address": user.get("address", ""),
        "avatar": user.get("avatar", "") or "",
        "role": user_role_for_email(user["email"], user.get("role", "user") or "user"),
        "is_verified": bool(user.get("is_verified", True)),
        "is_admin": user_role_for_email(user["email"], user.get("role", "user") or "user") == "admin"
    }


def update_local_user(user_id, name, phone, address, avatar):
    users = load_local_users()
    for user in users:
        if user.get("id") == user_id:
            user["full_name"] = name
            user["phone"] = phone
            user["address"] = address
            user["avatar"] = avatar
            break
    save_local_users(users)


def admin_update_local_user(user_id, name, email, phone, address, avatar="", role_override=None):
    normalized_email = normalize_email(email)
    role = normalize_profile_role(role_override) if role_override else user_role_for_email(normalized_email)
    users = load_local_users()
    for user in users:
        if user.get("id") != user_id and normalize_email(user.get("email", "")) == normalized_email:
            raise ValueError("Another user already uses that email.")
    for user in users:
        if user.get("id") == user_id:
            user["full_name"] = name
            user["email"] = normalized_email
            user["phone"] = phone
            user["address"] = address
            user["avatar"] = avatar or ""
            user["role"] = role
            break
    save_local_users(users)


def admin_delete_local_user(user_id):
    users = [user for user in load_local_users() if user.get("id") != user_id]
    save_local_users(users)


def admin_create_supabase_user(name, email, phone, address, password, role, is_verified=True):
    client = get_service_client()
    auth_user = client.auth.admin.create_user({
        "email": email,
        "password": password,
        "email_confirm": True,
        "user_metadata": {
            "full_name": name,
            "phone": phone,
            "address": address,
            "role": role,
        }
    }).user
    if not auth_user:
        raise RuntimeError("Could not create the Supabase admin user.")
    execute_upsert_with_fallback(
        "profiles",
        profile_payload_variants({
            "id": auth_user.id,
            "full_name": name,
            "email": email,
            "phone": phone,
            "address": address,
            "role": role,
            "is_verified": bool(is_verified),
            "otp_code": "",
            "otp_expiry": None,
        }),
        conflict_target="id",
        clients=[("service role", client)],
    )
    return auth_user


def admin_update_supabase_user(user_id, name, email, phone, address, avatar, role):
    role = normalize_profile_role(role)
    normalized_email = normalize_email(email)
    client = get_service_client()
    profile = client.table("profiles").select("*").eq("id", user_id).single().execute().data
    if not profile:
        raise ValueError("User profile not found.")
    execute_update_with_fallback(
        "profiles",
        profile_payload_variants({
            "id": user_id,
            "full_name": name,
            "email": normalized_email,
            "phone": phone,
            "address": address,
            "avatar": avatar or "",
            "role": role,
        }),
        "id",
        user_id,
        clients=[("service role", client)],
    )
    try:
        client.auth.admin.update_user_by_id(user_id, {
            "email": normalized_email,
            "user_metadata": {
                "full_name": name,
                "email": normalized_email,
                "phone": phone,
                "address": address,
                "avatar": avatar or "",
                "role": role,
            }
        })
    except Exception:
        pass


def admin_delete_supabase_user(user_id):
    client = get_service_client()
    client.table("profiles").delete().eq("id", user_id).execute()
    try:
        client.auth.admin.delete_user(user_id)
    except Exception:
        pass


init_local_auth_db()
validate_otp_email_configuration()


def validate_registration_form(name, email, phone, address, password, confirm_password):
    errors = []
    if not name:
        errors.append("Full name is required.")
    if not email:
        errors.append("Email is required.")
    elif not is_valid_email(email):
        errors.append("Enter a valid email address.")
    if not phone:
        errors.append("Phone number is required.")
    elif not is_valid_phone(phone):
        errors.append("Enter a valid mobile number (e.g. +639171234567).")
    if not address:
        errors.append("Address is required.")
    if not password:
        errors.append("Password is required.")
    elif len(password) < 6:
        errors.append("Password must be at least 6 characters.")
    elif not any(char.isalpha() for char in password) or not any(char.isdigit() for char in password):
        errors.append("Password must include at least one letter and one number.")
    if not confirm_password:
        errors.append("Please confirm your password.")
    elif password != confirm_password:
        errors.append("Passwords do not match.")
    return errors


def validate_login_form(email, password):
    errors = []
    if not email:
        errors.append("Email is required.")
    elif not is_valid_email(email):
        errors.append("Enter a valid email address.")
    if not password:
        errors.append("Password is required.")
    return errors


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user = session.get("user")
        if not user:
            if is_api_request():
                return jsonify({"ok": False, "error": "Please log in to continue."}), 401
            flash("Please log in to continue.", "error")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user = session.get("user")
        if not user:
            log_auth_debug("admin access blocked", reason="no active session", path=request.path)
            if is_api_request():
                return jsonify({"ok": False, "error": "Please log in to continue."}), 401
            flash("Please log in to continue.", "error")
            return redirect(url_for("login"))
        detected_role = (user or {}).get("role", "")
        normalized_role = (detected_role or "").strip().lower()
        is_admin = normalized_role == "admin"
        log_auth_debug(
            "admin page protection",
            email=(user or {}).get("email", ""),
            role=normalized_role,
            is_admin=is_admin,
            path=request.path,
        )
        if not is_admin:
            log_auth_debug(
                "admin access blocked",
                email=(user or {}).get("email", ""),
                role=normalized_role,
                is_admin=is_admin,
            )
            if is_api_request():
                return jsonify({"ok": False, "error": "This account is not authorized as admin."}), 403
            flash("This account is not authorized as admin.", "error")
            return redirect(url_for("home"))
        return f(*args, **kwargs)
    return decorated


def is_api_request(req=None):
    req = req or request
    path = (req.path or "").lower()
    accept = (req.headers.get("Accept") or "").lower()
    requested_with = (req.headers.get("X-Requested-With") or "").lower()
    return (
        path.startswith("/api/")
        or path.startswith("/admin/api/")
        or path.startswith("/profile/update")
        or "application/json" in accept
        or requested_with == "xmlhttprequest"
    )


@app.errorhandler(HTTPException)
def handle_http_error(exc):
    if is_api_request():
        message = exc.description if getattr(exc, "description", None) else exc.name
        return jsonify({"ok": False, "error": message}), exc.code
    return exc


@app.errorhandler(Exception)
def handle_unexpected_error(exc):
    log_exception(
        "unhandled route error",
        exc,
        path=request.path,
        method=request.method,
        user=session.get("user", {}).get("email", "anonymous"),
    )
    if is_api_request() or request.path.startswith("/profile/update"):
        return jsonify({"ok": False, "error": str(exc)}), 500
    return f"Internal Server Error: {exc}", 500


def db():
    """Return the configured Supabase database client for server-side work."""
    return admin_db_client()


def extract_schema_cache_missing_column(error, table_name):
    message = str(error)
    pattern = rf"Could not find the '([^']+)' column of '{re.escape(table_name)}' in the schema cache"
    match = re.search(pattern, message, re.IGNORECASE)
    return match.group(1) if match else None


def execute_upsert_with_fallback(table_name, payload_variants, conflict_target=None, clients=None):
    clients = clients or []
    errors = []
    for label, client in clients:
        for payload in payload_variants:
            try:
                query = client.table(table_name).upsert(payload, on_conflict=conflict_target) if conflict_target else client.table(table_name).upsert(payload)
                query.execute()
                return payload
            except Exception as exc:
                missing_column = extract_schema_cache_missing_column(exc, table_name)
                if missing_column:
                    errors.append(f"{label}: missing {missing_column}")
                    continue
                errors.append(f"{label}: {exc}")
        if label == "service role":
            break
    raise RuntimeError(" / ".join(errors) if errors else f"Could not upsert {table_name}.")


def execute_update_with_fallback(table_name, payload_variants, match_column, match_value, clients=None):
    clients = clients or []
    errors = []
    for label, client in clients:
        for payload in payload_variants:
            try:
                client.table(table_name).update(payload).eq(match_column, match_value).execute()
                return payload
            except Exception as exc:
                missing_column = extract_schema_cache_missing_column(exc, table_name)
                if missing_column:
                    errors.append(f"{label}: missing {missing_column}")
                    continue
                errors.append(f"{label}: {exc}")
        if label == "service role":
            break
    raise RuntimeError(" / ".join(errors) if errors else f"Could not update {table_name}.")


def profile_payload_variants(payload):
    preferred_order = ["id", "email", "full_name", "phone", "address", "avatar", "role", "is_verified", "otp_code", "otp_expiry", "created_at"]
    present_keys = [key for key in preferred_order if key in payload]
    variants = []
    seen = set()
    for index in range(len(present_keys), 0, -1):
        keys = tuple(key for key in present_keys[:index] if key in payload)
        if "id" not in keys or ("full_name" not in keys and "avatar" not in keys):
            continue
        if keys in seen:
            continue
        seen.add(keys)
        variants.append({key: payload[key] for key in keys})
    if not variants:
        fallback = {"id": payload["id"]}
        if "full_name" in payload:
            fallback["full_name"] = payload["full_name"]
        if "avatar" in payload:
            fallback["avatar"] = payload["avatar"]
        variants.append(fallback)
    return variants


def booking_insert_payload_variants(payload):
    base_payload = {
        "user_id": payload["user_id"],
        "full_name": payload["full_name"],
        "phone": payload["phone"],
        "service_type": payload["service_type"],
        "weight": payload["weight"],
        "pickup_date": payload["pickup_date"],
        "pickup_time": payload["pickup_time"],
        "notes": payload["notes"],
        "status": payload["status"],
    }
    if "total_price" in payload:
        base_payload["total_price"] = payload["total_price"]
    if "delivery_option" in payload and payload["delivery_option"] not in (None, ""):
        base_payload["delivery_option"] = payload["delivery_option"]
    address_variants = [
        {"pickup_address": payload["pickup_address"]},
        {"address": payload["pickup_address"]},
    ]
    optional_variants = [
        {"machine": payload["machine"], "load_type": payload["load_type"]},
        {"machine": payload["machine"]},
        {"load_type": payload["load_type"]},
        {},
    ]
    payment_payload = {
        key: payload[key]
        for key in ("payment_method", "reference_number", "payment_proof", "proof_image", "payment_status")
        if key in payload and payload[key] not in (None, "")
    }
    payment_variants = [{}]
    if payment_payload:
        payment_core = {
            key: payment_payload[key]
            for key in ("payment_method", "payment_status")
            if key in payment_payload
        }
        payment_without_proof = {
            key: value
            for key, value in payment_payload.items()
            if key not in {"payment_proof", "proof_image"}
        }
        payment_variants = [payment_payload, payment_without_proof, payment_core, {}]

    delivery_payload = {
        key: payload[key]
        for key in ("delivery_type", "delivery_fee", "total_amount")
        if key in payload and payload[key] not in (None, "")
    }
    delivery_variants = [delivery_payload, {}] if delivery_payload else [{}]

    variants = []
    seen = set()
    for address_variant, optional_variant, payment_variant, delivery_variant in product(
        address_variants, optional_variants, payment_variants, delivery_variants
    ):
        variant = {**base_payload, **address_variant, **optional_variant, **payment_variant, **delivery_variant}
        key = tuple(sorted(variant.keys()))
        if key in seen:
            continue
        seen.add(key)
        variants.append(variant)
    return variants


def encode_payment_proof_upload(uploaded_file):
    if not uploaded_file or not uploaded_file.filename:
        return ""
    mimetype = uploaded_file.mimetype or ""
    if not mimetype.startswith("image/"):
        raise ValueError("Payment proof must be an image file.")
    image_bytes = uploaded_file.read()
    if not image_bytes:
        raise ValueError("The uploaded payment proof is empty.")
    if len(image_bytes) > MAX_PAYMENT_PROOF_BYTES:
        raise ValueError("Payment proof must be 2MB or smaller.")
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{mimetype};base64,{encoded}"


def normalize_payment_method(payment_method):
    normalized = (payment_method or "Cash on Delivery").strip() or "Cash on Delivery"
    if normalized == "PayMaya":
        return "Maya"
    if normalized == "Cash on Pickup":
        return "Cash on Delivery"
    return normalized


def booking_template_context(user, form, machines):
    payment_method_config = {
        method: {
            **config,
            "qr_image_url": url_for("static", filename=config["qr_image"]),
        }
        for method, config in PAYMENT_METHOD_CONFIG.items()
    }
    return {
        "services": SERVICES,
        "user": user,
        "form": form,
        "machines": machines or [],
        "payment_method_config": payment_method_config,
        "delivery_fee_amount": DEFAULT_DELIVERY_FEE,
    }


def insert_booking_record(client, payload):
    missing_columns = []
    last_error = None

    for variant in booking_insert_payload_variants(payload):
        try:
            client.table("bookings").insert(variant).execute()
            return
        except Exception as exc:
            missing_column = extract_schema_cache_missing_column(exc, "bookings")
            if missing_column:
                missing_columns.append(missing_column)
                continue
            last_error = exc
            raise

    if last_error:
        raise last_error

    if missing_columns:
        unique_columns = ", ".join(sorted(set(missing_columns)))
        raise RuntimeError(
            "FreshWash could not save the booking because the bookings table is missing required columns: "
            f"{unique_columns}. Update the Supabase bookings schema and try again."
        )

    raise RuntimeError("FreshWash could not save the booking with the current bookings table schema.")


def normalize_booking_load_type(value):
    normalized = str(value or "").strip()
    if not normalized:
        return ""
    compact = re.sub(r"\s+", " ", normalized).strip().lower()
    if compact in {"light", "light load"}:
        return "Light"
    if compact in {"medium", "medium load"}:
        return "Medium"
    if compact in {"heavy", "heavy load"}:
        return "Heavy"
    return normalized.title()


def ensure_profile_record(authed_client, auth_user, defaults=None):
    """Load the user's profile and create a row if it doesn't exist yet."""
    defaults = defaults or {}
    metadata = auth_user.user_metadata or {}
    role = defaults.get("role") or metadata.get("role") or "user"
    profile_payload = {
        "id": auth_user.id,
        "email": auth_user.email,
        "full_name": defaults.get("full_name") or metadata.get("full_name") or auth_user.email.split("@")[0],
        "phone": defaults.get("phone", ""),
        "address": defaults.get("address", ""),
        "avatar": defaults.get("avatar", metadata.get("avatar", "")),
        "role": role,
        "is_verified": bool(defaults.get("is_verified", True)),
        "otp_code": defaults.get("otp_code", ""),
        "otp_expiry": defaults.get("otp_expiry"),
    }

    try:
        existing = authed_client.table("profiles").select("*").eq("id", auth_user.id).single().execute()
        if existing.data:
            merged_profile = {**profile_payload, **existing.data}
            if merged_profile.get("email") != auth_user.email:
                execute_update_with_fallback(
                    "profiles",
                    profile_payload_variants({"email": auth_user.email, "id": auth_user.id, "full_name": merged_profile.get("full_name") or profile_payload["full_name"]}),
                    "id",
                    auth_user.id,
                    clients=[("authenticated session", authed_client)],
                )
                merged_profile["email"] = auth_user.email
            if not merged_profile.get("role"):
                merged_profile["role"] = role
            return merged_profile
    except Exception:
        pass

    execute_upsert_with_fallback(
        "profiles",
        profile_payload_variants(profile_payload),
        conflict_target="id",
        clients=[("authenticated session", authed_client)],
    )
    return profile_payload


def ensure_supabase_profile_record(auth_user, defaults=None):
    defaults = defaults or {}
    clients = []
    if is_supabase_service_role_enabled():
        clients.append(("service role", get_service_client()))
    elif supabase:
        clients.append(("supabase", supabase))

    if not clients:
        raise RuntimeError(
            "Supabase signup succeeded, but FreshWash could not save the profile row. "
            "Add SUPABASE_SERVICE_ROLE_KEY to the environment to support OTP-code signup verification."
        )

    errors = []
    for label, client in clients:
        try:
            return ensure_profile_record(client, auth_user, defaults)
        except Exception as exc:
            errors.append(f"{label}: {exc}")

    combined_errors = " / ".join(errors)
    lowered_errors = combined_errors.lower()
    if "profiles_id_fkey" in lowered_errors or ("public.users" in lowered_errors and "foreign key" in lowered_errors):
        raise RuntimeError(
            "Supabase signup succeeded, but FreshWash could not save the profile row because profiles.id is linked to the wrong table. "
            "Update the profiles foreign key to reference auth.users(id), then retry signup."
        )
    raise RuntimeError(
        "Supabase signup succeeded, but FreshWash could not save the profile row. "
        + combined_errors
    )


def fetch_supabase_profile_or_error(auth_user, client=None):
    client = client or admin_db_client()
    if not client:
        raise RuntimeError("Login succeeded, but FreshWash could not connect to the profiles table.")

    try:
        result = client.table("profiles").select("*").eq("id", auth_user.id).single().execute()
    except Exception as exc:
        log_exception("profile fetch by id failed", exc, user_id=auth_user.id, email=auth_user.email)
        result = None

    profile = getattr(result, "data", None) or {}
    if not profile:
        try:
            result = client.table("profiles").select("*").eq("email", auth_user.email).single().execute()
            profile = result.data or {}
            log_auth_debug(
                "profile row fetched by email",
                user_id=auth_user.id,
                email=auth_user.email,
                profile_id=profile.get("id", ""),
                profile_role=profile.get("role", ""),
            )
        except Exception as exc:
            log_exception("profile fetch by email failed", exc, user_id=auth_user.id, email=auth_user.email)

    if not profile:
        log_auth_debug("profile row missing after auth login", user_id=auth_user.id, email=auth_user.email)
        metadata = auth_user.user_metadata or {}
        defaults = {
            "full_name": metadata.get("full_name") or auth_user.email.split("@")[0],
            "email": auth_user.email,
            "phone": metadata.get("phone", ""),
            "address": metadata.get("address", ""),
            "avatar": metadata.get("avatar", ""),
            "role": user_role_for_email(auth_user.email, metadata.get("role", "user"), metadata),
        }
        try:
            profile = ensure_supabase_profile_record(auth_user, defaults)
        except Exception as exc:
            raise RuntimeError(f"Admin profile not found: {exc}")

    stored_role = (profile.get("role") or "").strip().lower()
    profile_role = normalize_profile_role(profile.get("role", "user"))
    profile["role"] = profile_role

    should_repair_profile = (
        profile.get("id") != auth_user.id
        or
        normalize_email(profile.get("email", "")) != normalize_email(auth_user.email)
        or stored_role != profile_role
        or not (profile.get("full_name") or "").strip()
    )
    if should_repair_profile:
        repaired_profile = {
            "id": auth_user.id,
            "email": auth_user.email,
            "full_name": profile.get("full_name") or (auth_user.user_metadata or {}).get("full_name") or auth_user.email.split("@")[0],
            "phone": profile.get("phone", ""),
            "address": profile.get("address", ""),
            "avatar": profile.get("avatar", ""),
            "role": profile_role,
            "is_verified": bool(profile.get("is_verified")) if profile.get("is_verified") is not None else True,
            "otp_code": profile.get("otp_code", ""),
            "otp_expiry": profile.get("otp_expiry"),
        }
        repair_clients = []
        if is_supabase_service_role_enabled():
            repair_clients.append(("service role", get_service_client()))
        elif client:
            repair_clients.append(("supabase", client))
        try:
            execute_upsert_with_fallback(
                "profiles",
                profile_payload_variants(repaired_profile),
                conflict_target="id",
                clients=repair_clients,
            )
            profile = repaired_profile
        except Exception as exc:
            log_exception("profile role/email repair failed during login", exc, email=auth_user.email, user_id=auth_user.id)

    log_auth_debug(
        "profile row fetched",
        user_id=auth_user.id,
        email=auth_user.email,
        profile_email=profile.get("email", ""),
        profile_role=profile.get("role", ""),
    )
    return profile


def build_session_user(auth_user, profile):
    metadata = auth_user.user_metadata or {}
    role = user_role_for_email(
        auth_user.email,
        profile.get("role", "user"),
        metadata,
    )
    return {
        "id": auth_user.id,
        "email": profile.get("email") or auth_user.email,
        "name": profile.get("full_name") or metadata.get("full_name") or auth_user.email.split("@")[0],
        "phone": profile.get("phone", ""),
        "address": profile.get("address", ""),
        "avatar": profile.get("avatar", ""),
        "role": role,
        "is_admin": role == "admin"
    }


def compact_session_user(user):
    """Keep Flask's signed cookie small enough to survive redirects."""
    avatar = user.get("avatar", "") or ""
    if avatar.startswith("data:") or len(avatar) > 500:
        avatar = ""
    return {
        "id": user.get("id", ""),
        "email": normalize_email(user.get("email", "")),
        "name": user.get("name", "") or user.get("email", "").split("@")[0],
        "phone": user.get("phone", "") or "",
        "address": user.get("address", "") or "",
        "avatar": avatar,
        "role": normalize_profile_role(user.get("role", "user")),
    }


def persist_session_user(user):
    user = compact_session_user(user)
    role = user["role"]
    user["role"] = role
    user["is_admin"] = role == "admin"
    session.permanent = True
    session["user"] = user
    session.modified = True
    log_auth_debug(
        "session result",
        email=user.get("email", ""),
        role=user.get("role", ""),
        is_admin=user.get("is_admin", False),
        has_flask_session=True,
        session_user_bytes=len(json.dumps(user)),
    )


def is_supabase_connection_error(error):
    message = str(error).lower()
    indicators = (
        "connection refused",
        "target machine actively refused it",
        "failed to establish a new connection",
        "name or service not known",
        "temporary failure in name resolution",
        "timed out",
        "timeout",
        "network is unreachable",
        "connection aborted",
        "connection reset",
        "getaddrinfo failed",
        "nodename nor servname provided",
        "server disconnected",
    )
    return any(indicator in message for indicator in indicators)


def local_auth_enabled():
    return not is_supabase_enabled()


def admin_dashboard_bookings():
    client = admin_db_client()
    if client:
        try:
            result = client.table("bookings").select("*").order("created_at", desc=True).execute()
            bookings = result.data or []
            for booking in bookings:
                if booking.get("total_price") in (None, ""):
                    price = SERVICES.get(booking.get("service_type", ""), {}).get("price", 0)
                    booking["total_price"] = round(price * float(booking.get("weight", 0) or 0), 2)
            return bookings
        except Exception as exc:
            log_exception("admin bookings query failed", exc)
    return []


def admin_dashboard_users():
    if local_auth_enabled():
        rows = sorted(load_local_users(), key=lambda row: row.get("created_at", ""), reverse=True)
        return [
            {
                "id": row["id"],
                "name": row["full_name"],
                "email": row["email"],
                "phone": row.get("phone", ""),
                "address": row.get("address", ""),
                "avatar": row.get("avatar", "") or "",
                "role": user_role_for_email(row["email"], row.get("role", "user") or "user"),
                "created_at": row.get("created_at", ""),
            }
            for row in rows
        ]

    client = admin_db_client()
    if client:
        try:
            result = client.table("profiles").select("*").order("created_at", desc=True).execute()
            rows = result.data or []
            return [
                {
                    "id": row["id"],
                    "name": row.get("full_name") or row.get("email", "User").split("@")[0],
                    "email": row.get("email", ""),
                    "phone": row.get("phone", ""),
                    "address": row.get("address", ""),
                    "avatar": row.get("avatar", "") or "",
                    "role": normalize_profile_role(row.get("role", "user")),
                    "created_at": row.get("created_at", ""),
                }
                for row in rows
            ]
        except Exception:
            pass

    return []


def admin_dashboard_machines():
    settings = get_admin_settings()
    allowed_load_types = settings["machines"]["default_load_types"] or ["Light", "Medium", "Heavy"]
    machines_globally_enabled = settings["machines"]["machines_globally_enabled"]

    def seed_rows_from_local_source():
        try:
            with local_auth_conn() as conn:
                rows = conn.execute(
                    """
                    SELECT machine_number, name, status, load_type, enabled
                    FROM admin_machines
                    ORDER BY machine_number
                    """
                ).fetchall()
            if rows:
                return [
                    {
                        "machine_number": row["machine_number"],
                        "name": row["name"],
                        "status": row["status"],
                        "load_type": row["load_type"],
                        "enabled": row["enabled"],
                    }
                    for row in rows
                ]
        except sqlite3.OperationalError:
            pass
        return list(DEFAULT_MACHINE_ROWS)

    def normalize_machine(row):
        machine_number = row.get("machine_number") or row.get("id")
        machine_id = row.get("id") or machine_number
        name = row.get("name") or f"Machine {machine_number}"
        status = row.get("status", "Available")
        if status not in VALID_MACHINE_STATUSES:
            status = "Available"
        enabled = bool(row.get("enabled", status != "Disabled")) and status != "Disabled"
        effective_enabled = enabled and machines_globally_enabled
        load_type = row.get("load_type", "Medium")
        if load_type not in allowed_load_types and allowed_load_types:
            load_type = allowed_load_types[min(1, len(allowed_load_types) - 1)]
        status_display = status if effective_enabled and status != "Disabled" else "Disabled"
        return {
            "id": machine_id,
            "machine_number": machine_number,
            "name": name,
            "status": status,
            "status_display": status_display,
            "load_type": load_type,
            "enabled": enabled,
            "effective_enabled": effective_enabled,
            "button_label": "Book Now" if effective_enabled and status == "Available" else "Unavailable",
            "button_disabled": (not effective_enabled) or status != "Available",
        }

    client = admin_db_client()
    if client:
        try:
            try:
                rows = client.table("machines").select("*").order("machine_number").execute().data or []
            except Exception:
                rows = client.table("machines").select("*").order("id").execute().data or []
            print(f"[FreshWash] admin_dashboard_machines: Supabase returned {len(rows)} row(s)")
            if not rows:
                seed_rows = seed_rows_from_local_source()
                print(f"[FreshWash] admin_dashboard_machines: seeding {len(seed_rows)} machine(s) into Supabase")
                if seed_rows:
                    try:
                        client.table("machines").upsert(
                            [
                                {
                                    "id": row.get("id") or row.get("machine_number"),
                                    "machine_number": row.get("machine_number"),
                                    "name": row.get("name") or f"Machine {row.get('machine_number')}",
                                    "status": row.get("status", "Available"),
                                    "load_type": row.get("load_type", "Medium"),
                                    "enabled": bool(row.get("enabled", True)) and row.get("status", "Available") != "Disabled",
                                }
                                for row in seed_rows
                            ],
                            on_conflict="machine_number"
                        ).execute()
                        try:
                            rows = client.table("machines").select("*").order("machine_number").execute().data or []
                        except Exception:
                            rows = client.table("machines").select("*").order("id").execute().data or []
                        print(f"[FreshWash] admin_dashboard_machines: after seed, Supabase returned {len(rows)} row(s)")
                    except Exception as seed_exc:
                        log_exception("admin machines seed failed", seed_exc)
            if rows:
                return [normalize_machine(row) for row in rows]
        except Exception as exc:
            log_exception("admin machines fetch failed", exc)

    try:
        with local_auth_conn() as conn:
            rows = conn.execute(
                """
                SELECT machine_number, name, status, load_type, enabled
                FROM admin_machines
                ORDER BY machine_number
                """
            ).fetchall()
        return [
            normalize_machine(
                {
                    "machine_number": row["machine_number"],
                    "name": row["name"],
                    "status": row["status"],
                    "load_type": row["load_type"],
                    "enabled": row["enabled"],
                }
            )
            for row in rows
        ]
    except sqlite3.OperationalError:
        return [normalize_machine(row) for row in DEFAULT_MACHINE_ROWS]


def build_home_machine_types(machines):
    cards = []
    for load_type in ("Light", "Medium", "Heavy"):
        matching = [machine for machine in (machines or []) if machine.get("load_type") == load_type]
        available = [
            machine for machine in matching
            if machine.get("effective_enabled", machine.get("enabled", True))
            and machine.get("status") == "Available"
        ]
        content = MACHINE_TYPE_CONTENT[load_type]
        cards.append(
            {
                "load_type": load_type,
                "title": content["title"],
                "description": content["description"],
                "icon": content["icon"],
                "accent": content["accent"],
                "machine_count": len(matching),
                "available_count": len(available),
                "machine_name": available[0]["name"] if available else "",
                "is_available": bool(available),
                "button_label": "Book Now" if available else "Unavailable",
            }
        )
    return cards


@app.route("/api/machines")
@login_required
def machines_api():
    try:
        return jsonify({"ok": True, "data": {"machines": admin_dashboard_machines()}})
    except Exception as exc:
        log_exception("machines api failed", exc, user=session.get("user", {}).get("email", ""))
        return jsonify({"ok": False, "error": f"Could not load machines: {exc}"}), 500


def admin_dashboard_services():
    client = admin_db_client()
    if client:
        try:
            rows = client.table("services").select("*").order("name").execute().data or []
            if rows:
                return [
                    {
                        "name": row.get("name", ""),
                        "price": float(row.get("price", 0) or 0),
                        "description": row.get("description", ""),
                    }
                    for row in rows
                ]
        except Exception:
            pass

    try:
        with local_auth_conn() as conn:
            rows = conn.execute(
                """
                SELECT name, price, description
                FROM admin_services
                ORDER BY name
                """
            ).fetchall()
        return [
            {"name": row["name"], "price": float(row["price"]), "description": row["description"]}
            for row in rows
        ]
    except sqlite3.OperationalError:
        return [
            {"name": name, "price": float(data["price"]), "description": data["desc"]}
            for name, data in ADMIN_SERVICE_DEFAULTS.items()
        ]


def update_machine(machine_number, name=None, status=None, enabled=None, load_type=None):
    current_machine = next(
        (machine for machine in admin_dashboard_machines() if machine["machine_number"] == machine_number),
        None,
    )
    base_machine = next(
        (row for row in DEFAULT_MACHINE_ROWS if row["machine_number"] == machine_number),
        {
            "machine_number": machine_number,
            "name": f"Machine {machine_number}",
            "status": "Available",
            "load_type": "Medium",
            "enabled": 1,
        },
    )
    machine_name = (name if name is not None else (current_machine or {}).get("name", base_machine["name"])).strip()
    machine_status = status if status is not None else (current_machine or {}).get("status", base_machine["status"])
    if machine_status not in VALID_MACHINE_STATUSES:
        raise ValueError("Invalid machine status.")
    machine_load_type = load_type if load_type is not None else (current_machine or {}).get("load_type", base_machine["load_type"])
    machine_enabled = bool(enabled) if enabled is not None else bool((current_machine or {}).get("enabled", base_machine["enabled"]))
    if machine_status == "Disabled":
        machine_enabled = False
    client = admin_db_client()
    if client:
        payload = {
            "id": (current_machine or {}).get("id") or machine_number,
            "machine_number": machine_number,
            "name": machine_name,
            "status": machine_status,
            "load_type": machine_load_type,
            "enabled": machine_enabled,
        }
        try:
            client.table("machines").upsert(payload, on_conflict="machine_number").execute()
        except Exception as exc:
            log_exception("admin machine upsert failed", exc, machine_number=machine_number)

    fields = []
    values = []
    if name is not None:
        fields.append("name = ?")
        values.append(machine_name)
    if status is not None:
        fields.append("status = ?")
        values.append(machine_status)
    if enabled is not None:
        fields.append("enabled = ?")
        values.append(1 if machine_enabled else 0)
    if load_type is not None:
        fields.append("load_type = ?")
        values.append(machine_load_type)
    fields.append("updated_at = CURRENT_TIMESTAMP")
    with local_auth_conn() as conn:
        existing = conn.execute(
            "SELECT machine_number FROM admin_machines WHERE machine_number = ?",
            (machine_number,),
        ).fetchone()
        if existing:
            values.append(machine_number)
            conn.execute(f"UPDATE admin_machines SET {', '.join(fields)} WHERE machine_number = ?", values)
        else:
            conn.execute(
                """
                INSERT INTO admin_machines (machine_number, name, status, load_type, enabled)
                VALUES (?, ?, ?, ?, ?)
                """,
                (machine_number, machine_name, machine_status, machine_load_type, 1 if machine_enabled else 0),
            )


def update_machine_status_by_id(machine_id, status, load_type=None):
    machine_id = str(machine_id or "").strip()
    if not machine_id:
        raise ValueError("Machine id is required.")
    if status not in VALID_MACHINE_STATUSES:
        raise ValueError("Invalid machine status.")

    machine = next(
        (
            current_machine
            for current_machine in admin_dashboard_machines()
            if str(current_machine.get("id")) == machine_id
            or str(current_machine.get("machine_number")) == machine_id
        ),
        None,
    )
    if not machine:
        raise ValueError("Machine not found.")
    allowed_load_types = set(get_admin_settings()["machines"]["default_load_types"])
    if load_type is not None and load_type not in allowed_load_types:
        raise ValueError("Invalid load type.")

    update_machine(
        int(machine.get("machine_number") or machine.get("id")),
        name=machine.get("name"),
        status=status,
        enabled=status != "Disabled",
        load_type=load_type if load_type is not None else machine.get("load_type"),
    )
    return machine


def update_service(name, price, description):
    client = admin_db_client()
    if client:
        try:
            client.table("services").upsert(
                {"name": name, "price": price, "description": description},
                on_conflict="name"
            ).execute()
        except Exception as exc:
            log_exception("admin service upsert failed", exc, service_name=name)

    with local_auth_conn() as conn:
        conn.execute(
            """
            UPDATE admin_services
            SET price = ?, description = ?
            WHERE name = ?
            """,
            (price, description, name)
        )


def parse_bool_setting(value, default=False):
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def normalize_load_type_list(values):
    normalized = []
    seen = set()
    for value in values or []:
        item = str(value or "").strip()
        if not item:
            continue
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(item.title())
    return normalized or ["Light", "Medium", "Heavy"]


def load_admin_settings_rows():
    settings = dict(ADMIN_SETTINGS_DEFAULTS)
    try:
        with local_auth_conn() as conn:
            rows = conn.execute("SELECT key, value FROM admin_settings").fetchall()
        for row in rows:
            settings[row["key"]] = row["value"]
    except sqlite3.OperationalError:
        pass
    return settings


def get_admin_settings():
    rows = load_admin_settings_rows()
    load_types_raw = rows.get("default_load_types", ADMIN_SETTINGS_DEFAULTS["default_load_types"])
    try:
        parsed_load_types = json.loads(load_types_raw) if isinstance(load_types_raw, str) else load_types_raw
    except json.JSONDecodeError:
        parsed_load_types = [item.strip() for item in str(load_types_raw).split(",")]
    load_types = normalize_load_type_list(parsed_load_types)
    return {
        "profile": {
            "name": session.get("user", {}).get("name", ""),
            "email": session.get("user", {}).get("email", ""),
            "phone": session.get("user", {}).get("phone", ""),
            "address": session.get("user", {}).get("address", ""),
            "avatar": session.get("user", {}).get("avatar", ""),
        },
        "system": {
            "shop_name": rows.get("shop_name", ADMIN_SETTINGS_DEFAULTS["shop_name"]),
            "contact_number": rows.get("contact_number", ADMIN_SETTINGS_DEFAULTS["contact_number"]),
            "shop_address": rows.get("shop_address", ADMIN_SETTINGS_DEFAULTS["shop_address"]),
        },
        "machines": {
            "default_load_types": load_types,
            "machines_globally_enabled": parse_bool_setting(
                rows.get("machines_globally_enabled", ADMIN_SETTINGS_DEFAULTS["machines_globally_enabled"]),
                True,
            ),
        },
        "theme": {
            "mode": rows.get("theme_mode", ADMIN_SETTINGS_DEFAULTS["theme_mode"]),
            "accent": rows.get("theme_accent", ADMIN_SETTINGS_DEFAULTS["theme_accent"]),
        },
    }


def save_admin_settings(updates):
    serialized_updates = {}
    for key, value in (updates or {}).items():
        if key == "default_load_types":
            serialized_updates[key] = json.dumps(normalize_load_type_list(value))
        elif isinstance(value, bool):
            serialized_updates[key] = "true" if value else "false"
        else:
            serialized_updates[key] = str(value)

    if not serialized_updates:
        return

    with local_auth_conn() as conn:
        for key, value in serialized_updates.items():
            conn.execute(
                """
                INSERT INTO admin_settings (key, value, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET
                  value = excluded.value,
                  updated_at = CURRENT_TIMESTAMP
                """,
                (key, value),
            )


def update_admin_profile_settings(user_id, name, email, phone="", password="", address="", avatar=""):
    normalized_email = normalize_email(email)
    phone = (phone or "").strip()
    address = (address or "").strip()
    avatar = (avatar or "").strip()
    if local_auth_enabled():
        users = load_local_users()
        for user in users:
            if user.get("id") != user_id and normalize_email(user.get("email", "")) == normalized_email:
                raise ValueError("Another user already uses that email.")
        for user in users:
            if user.get("id") == user_id:
                user["full_name"] = name
                user["email"] = normalized_email
                user["phone"] = phone
                user["address"] = address
                if avatar:
                    user["avatar"] = avatar
                if password:
                    user["password_hash"] = generate_password_hash(password)
                break
        save_local_users(users)
        return

    profile_update = {"full_name": name, "email": normalized_email, "phone": phone, "address": address}
    if avatar:
        profile_update["avatar"] = avatar
    try:
        if is_supabase_service_role_enabled():
            client = get_service_client()
            execute_update_with_fallback(
                "profiles",
                profile_payload_variants({"id": user_id, **profile_update}),
                "id",
                user_id,
                clients=[("service role", client)],
            )
            auth_payload = {
                "email": normalized_email,
                "user_metadata": {
                    "full_name": name,
                    "phone": phone,
                    "address": address,
                    "avatar": avatar or session["user"].get("avatar", ""),
                    "role": session["user"].get("role", "admin"),
                }
            }
            if password:
                auth_payload["password"] = password
            client.auth.admin.update_user_by_id(user_id, auth_payload)
            return
        raise ValueError("Updating Supabase admin profiles requires SUPABASE_SERVICE_ROLE_KEY.")
    except Exception as exc:
        raise ValueError(f"Could not update admin profile: {exc}")


# ── FIXED: build_admin_reports now uses camelCase keys to match the JS frontend ──
def upload_admin_avatar_to_storage(user_id, image_bytes, content_type):
    if not is_supabase_enabled():
        raise ValueError("Supabase is not configured.")
    if not is_supabase_service_role_enabled():
        raise ValueError("Supabase service role is required to upload admin avatars.")
    if not user_id:
        raise ValueError("Missing logged-in user id.")

    extension = "jpg"
    if "/" in (content_type or ""):
        extension = (content_type.split("/", 1)[1] or "jpg").split(";", 1)[0].lower() or "jpg"
    if extension == "jpeg":
        extension = "jpg"
    if extension not in {"jpg", "png", "gif", "webp"}:
        extension = "jpg"

    storage_path = f"{user_id}/admin-profile-{uuid.uuid4().hex}.{extension}"
    try:
        client = get_service_client()
        client.storage.from_(ADMIN_AVATAR_BUCKET).upload(
            storage_path,
            image_bytes,
            {"content-type": content_type or "image/jpeg"},
        )
    except Exception as exc:
        message = str(exc)
        if "bucket not found" in message.lower() or "not found" in message.lower():
            raise ValueError(
                f"Storage bucket '{ADMIN_AVATAR_BUCKET}' was not found. "
                "Create it in Supabase Storage or set FRESHWASH_AVATAR_BUCKET to the correct name."
            )
        if "row-level security" in message.lower() or "policy" in message.lower():
            raise ValueError(
                f"Upload failed for storage bucket '{ADMIN_AVATAR_BUCKET}' because storage policies blocked access: {exc}. "
                f"Add Storage policies for authenticated users on storage.objects: SELECT, INSERT, and UPDATE for bucket_id = '{ADMIN_AVATAR_BUCKET}'."
            )
        raise ValueError(f"Upload failed for storage bucket '{ADMIN_AVATAR_BUCKET}': {exc}")

    try:
        public_url = client.storage.from_(ADMIN_AVATAR_BUCKET).get_public_url(storage_path)
    except Exception as exc:
        raise ValueError(f"Could not get public URL for uploaded avatar: {exc}")
    if not public_url:
        raise ValueError("Supabase did not return a public URL for the uploaded avatar.")
    return public_url


def update_admin_avatar(user_id, avatar):
    avatar = avatar or ""
    if not user_id:
        raise ValueError("Missing logged-in user id.")
    if not avatar:
        raise ValueError("Missing uploaded avatar URL.")
    if local_auth_enabled():
        users = load_local_users()
        for user in users:
            if user.get("id") == user_id:
                user["avatar"] = avatar
                break
        save_local_users(users)
        return

    profile_update = {"avatar": avatar}
    try:
        if is_supabase_service_role_enabled():
            client = get_service_client()
            execute_update_with_fallback(
                "profiles",
                profile_payload_variants({"id": user_id, **profile_update}),
                "id",
                user_id,
                clients=[("service role", client)],
            )
            try:
                client.auth.admin.update_user_by_id(
                    user_id,
                    {"user_metadata": {**(session.get("user") or {}), "avatar": avatar}},
                )
            except Exception as exc:
                log_exception("admin auth metadata avatar sync failed", exc, user=user_id)
            return
        raise ValueError("Supabase service role is required to save admin avatar URLs.")
    except Exception as exc:
        raise ValueError(f"Profile update failed: {exc}")


def build_admin_reports(bookings, machines):
    per_day_counter = Counter(
        (booking.get("pickup_date") or booking.get("date") or "Unscheduled")
        for booking in bookings
    )
    service_counter = Counter(booking.get("service_type", "Unknown") for booking in bookings)
    machine_counter = Counter(booking.get("machine", "Unassigned") for booking in bookings)
    status_counter = Counter((booking.get("status") or "Pending") for booking in bookings)

    completed_revenue = sum(
        float(booking.get("total_price", 0) or 0)
        for booking in bookings
        if (booking.get("status") or "").lower() == "completed"
    )

    return {
        "bookingsPerDay": [
            {"label": day, "count": count}
            for day, count in sorted(per_day_counter.items())[-7:]
        ],
        "mostUsedService": (
            service_counter.most_common(1)[0][0] if service_counter else "No data yet"
        ),
        "machineUsage": [
            {
                "label": machine["name"],
                "count": machine_counter.get(machine["name"], 0),
                "status": machine.get("status_display") or machine.get("status", "Available"),
            }
            for machine in machines
        ],
        "statusBreakdown": {
            "pending": status_counter.get("Pending", 0),
            "inProgress": status_counter.get("In Progress", 0),
            "completed": status_counter.get("Completed", 0),
            "cancelled": status_counter.get("Cancelled", 0),
        },
        "completedRevenue": round(completed_revenue, 2),
    }


def build_admin_payment_records(bookings):
    payment_records = []
    for index, booking in enumerate(bookings or []):
        payment_method = booking.get("payment_method") or ""
        if not payment_method:
            continue
        payment_records.append({
            "id": booking.get("id") or f"payment-{index}",
            "booking_id": booking.get("id") or "No booking linked",
            "amount": float(booking.get("total_price", 0) or 0),
            "status": booking.get("payment_status") or "Pending Payment",
            "method": payment_method,
            "reference_number": booking.get("reference_number") or "",
            "payment_proof": booking.get("payment_proof") or booking.get("proof_image") or "",
            "proof_image": booking.get("payment_proof") or booking.get("proof_image") or "",
            "paid_at": booking.get("created_at") or booking.get("pickup_date") or "",
            "customer_name": booking.get("full_name") or "FreshWash Customer",
        })
    return payment_records


def build_admin_dashboard_payload():
    users = admin_dashboard_users()
    bookings = admin_dashboard_bookings()
    machines = admin_dashboard_machines()
    services = admin_dashboard_services()
    settings = get_admin_settings()
    payments = build_admin_payment_records(bookings)
    completed_orders = sum(1 for booking in bookings if booking.get("status") == "Completed")
    pending_orders = sum(1 for booking in bookings if booking.get("status") == "Pending")
    cancelled_orders = sum(1 for booking in bookings if booking.get("status") == "Cancelled")
    active_machines = sum(1 for machine in machines if machine["enabled"] and machine["status"] == "In Use")
    available_machines = sum(1 for machine in machines if machine["enabled"] and machine["status"] == "Available")
    revenue = sum(float(booking.get("total_price", 0) or 0) for booking in bookings if booking.get("status") == "Completed")
    reports = build_admin_reports(bookings, machines)

    return {
        "summary": {
            "total_users": len(users),
            "total_bookings": len(bookings),
            "pending_bookings": pending_orders,
            "cancelled_bookings": cancelled_orders,
            "active_machines": active_machines,
            "available_machines": available_machines,
            "completed_orders": completed_orders,
            "revenue": round(revenue, 2),
        },
        "users": users,
        "bookings": bookings,
        "payments": payments,
        "machines": machines,
        "services": services,
        "reports": reports,
        "settings": settings,
    }


# ── FIXED: empty_admin_dashboard_payload now uses camelCase keys to match JS ──
def empty_admin_dashboard_payload():
    return {
        "summary": {
            "total_users": 0,
            "total_bookings": 0,
            "pending_bookings": 0,
            "cancelled_bookings": 0,
            "active_machines": 0,
            "available_machines": 0,
            "completed_orders": 0,
            "revenue": 0.0,
        },
        "users": [],
        "bookings": [],
        "payments": [],
        "machines": [],
        "services": [],
        "reports": {
            "bookingsPerDay": [],
            "mostUsedService": "No data yet",
            "machineUsage": [],
            "statusBreakdown": {
                "pending": 0,
                "inProgress": 0,
                "completed": 0,
                "cancelled": 0,
            },
            "completedRevenue": 0.0,
        },
        "settings": {
            "profile": {
                "name": session.get("user", {}).get("name", ""),
                "email": session.get("user", {}).get("email", ""),
                "phone": session.get("user", {}).get("phone", ""),
                "avatar": session.get("user", {}).get("avatar", ""),
            },
            "system": {
                "shop_name": ADMIN_SETTINGS_DEFAULTS["shop_name"],
                "contact_number": "",
                "shop_address": "",
            },
            "machines": {
                "default_load_types": ["Light", "Medium", "Heavy"],
                "machines_globally_enabled": True,
            },
            "theme": {
                "mode": "light",
                "accent": "pink-rose",
            },
        },
    }


def render_admin_dashboard_view(section="dashboard"):
    safe_user = session.get("user") or {}
    safe_section = section or "dashboard"

    try:
        admin_data = build_admin_dashboard_payload() or {}
    except Exception as exc:
        log_exception("render_admin_dashboard_view.payload", exc)
        admin_data = empty_admin_dashboard_payload()

    template_name = f"admin_{safe_section}.html"
    return render_template(
        template_name,
        user=safe_user,
        admin_data=admin_data,
        active_page=safe_section,
    )


# ── Auth ──────────────────────────────────────────────────────────────────────
@app.route("/register", methods=["GET", "POST"])
def register():
    print('DEBUG: register route called, method=', request.method)
    if "user" in session:
        return redirect(url_for("admin_dashboard" if session["user"].get("is_admin") else "home"))

    if request.method == "GET":
        return redirect_to_auth_modal("register")

    if request.method == "POST":
        print("AUTH: Register route triggered")
        name     = request.form.get("name", "").strip()
        email    = normalize_email(request.form.get("email", ""))
        print(f"AUTH: Submitted email: {email}")
        phone    = request.form.get("phone", "").strip()
        address  = request.form.get("address", "").strip()
        password = request.form.get("password", "").strip()
        confirm_password = request.form.get("confirm_password", "").strip()
        form_data = {
            "name": name,
            "email": email,
            "phone": phone,
            "address": address
        }

        errors = validate_registration_form(name, email, phone, address, password, confirm_password)
        if errors:
            for error in errors:
                flash(error, "error")
            return redirect_to_auth_modal("register", form_data)

        # Prevent rapid duplicate signup submits for the same email in one browser session.
        signup_submit_cache = session.get("signup_submit_cache") or {}
        recent_submit_iso = signup_submit_cache.get(email)
        recent_submit_at = parse_iso_datetime(recent_submit_iso)
        if recent_submit_at:
            if recent_submit_at.tzinfo is None:
                recent_submit_at = recent_submit_at.replace(tzinfo=timezone.utc)
            if (datetime.now(timezone.utc) - recent_submit_at).total_seconds() < 8:
                flash(resend_wait_message(8), "error")
                return redirect_to_auth_modal("register", form_data)
        signup_submit_cache[email] = datetime.now(timezone.utc).isoformat()
        session["signup_submit_cache"] = signup_submit_cache
        session.modified = True

        role = resolve_registration_role(email)

        try:
            if local_auth_enabled():
                create_local_user(
                    name,
                    email,
                    phone,
                    address,
                    password,
                    role_override=role,
                    is_verified=(role == "admin"),
                )
            else:
                existing_profile = find_profile_by_email(email)
                existing_auth_user = find_supabase_auth_user_by_email(email) if is_supabase_service_role_enabled() else None

                print(f"REGISTER: SUPABASE_URL={os.environ.get('SUPABASE_URL', '<not set>')}")
                print(f"REGISTER: submitted email={email}")
                print(f"REGISTER: auth_user_found={bool(existing_auth_user)} profile_found={bool(existing_profile)}")

                auth_metadata = safe_auth_user_metadata(existing_auth_user) if existing_auth_user else {}
                existing_role = user_role_for_email(
                    email,
                    (existing_profile or {}).get("role", "user"),
                    auth_metadata,
                ) if existing_auth_user else ""
                log_auth_debug(
                    "registration profile check result",
                    email=email,
                    has_profile=bool(existing_profile),
                    has_auth_user=bool(existing_auth_user),
                    profile_role=(existing_profile or {}).get("role", ""),
                    detected_role=existing_role,
                )

                # Orphaned profile: profile row exists but auth user was deleted.
                # Remove the stale profile so the user can register fresh.
                if existing_profile and not existing_auth_user:
                    print(f"REGISTER: orphaned profile found for {email}, deleting before re-registration")
                    try:
                        client = get_service_client()
                        client.table("profiles").delete().eq("email", normalize_email(email)).execute()
                        existing_profile = None
                        print(f"REGISTER: orphaned profile deleted for {email}")
                    except Exception as del_exc:
                        log_exception("register orphaned profile delete failed", del_exc, email=email)

                if existing_auth_user:
                    if existing_role == "admin":
                        flash("This email is reserved for admin.", "error")
                        return redirect_to_auth_modal("register", form_data)

                    if not existing_profile:
                        recover_missing_profile_for_auth_user(
                            existing_auth_user,
                            {
                                "email": email,
                                "full_name": name or (email.split("@")[0] if email else "FreshWash User"),
                                "phone": phone,
                                "address": address,
                                "role": "user",
                                "is_verified": False,
                            },
                        )
                    flash("Account already exists, please login.", "error")
                    return redirect_to_auth_modal("login", {"email": email})

                # User signup in OTP flow is completed after OTP verification.
                if role == "admin":
                    signup_auth_user = create_supabase_signup_user(
                        name=name,
                        email=email,
                        phone=phone,
                        address=address,
                        password=password,
                        role=role,
                    )
                    ensure_supabase_profile_record(
                        signup_auth_user,
                        {
                            "full_name": name,
                            "email": email,
                            "phone": phone,
                            "address": address,
                            "role": role,
                            "is_verified": True,
                            "otp_code": "",
                            "otp_expiry": None,
                        },
                    )
                    upsert_local_user(
                        name,
                        email,
                        phone,
                        address,
                        password,
                        role_override=role,
                        is_verified=True,
                    )

            if role == "admin":
                log_auth_debug("otp skipped for admin", email=email, role=role, flow="register")
                flash("Admin account created successfully. Please log in.", "success")
                return redirect_to_auth_modal("login", {"email": email})

            # Issue OTP verification for all non-admin users
            if local_auth_enabled():
                local_user, _ = find_local_user(email)
                pending_user_data = {
                    "id": local_user["id"] if local_user else str(uuid.uuid4()),
                    "email": email,
                    "name": name,
                    "phone": phone,
                    "address": address,
                    "avatar": "",
                    "role": role,
                    "is_admin": False,
                }
            else:
                profile = find_profile_by_email(email) or {}
                pending_user_data = {
                    "id": profile.get("id", ""),
                    "email": email,
                    "name": name,
                    "phone": phone,
                    "address": address,
                    "avatar": "",
                    "role": role,
                    "is_admin": False,
                }

            try:
                issue_otp_challenge(
                    email,
                    "signup",
                    pending_user=pending_user_data,
                    trigger_send=True,
                )
                flash("Verification code sent to your email. Please check your inbox.", "success")
                return redirect_to_auth_modal("verify", otp_modal_form_data())
            except Exception as otp_error:
                log_exception("register otp issue failed", otp_error, email=email)
                lowered = str(otp_error).lower()
                if "resend code in" in lowered or "rate limit" in lowered:
                    flash(str(otp_error), "error")
                    return redirect_to_auth_modal("verify", otp_modal_form_data())
                # OTP send failed — still log them in but warn
                persist_session_user(pending_user_data)
                flash("Account created! Verification email could not be sent — check SMTP settings.", "success")
                return redirect(url_for("home"))

        except ValueError as e:
            flash(str(e), "error")
        except Exception as e:
            message = str(e)
            log_exception("register route failed", e, email=email)
            log_auth_debug("register exact supabase error", email=email, error=message)
            if is_supabase_enabled() and is_supabase_connection_error(e):
                try:
                    create_local_user(
                        name,
                        email,
                        phone,
                        address,
                        password,
                        role_override=role,
                        is_verified=(role == "admin"),
                    )
                    if role == "admin":
                        log_auth_debug("otp skipped for admin", email=email, role=role, flow="register-fallback")
                        flash("Admin account created locally because Supabase is unavailable. Please log in.", "success")
                        return redirect_to_auth_modal("login", {"email": email})
                    flash("Supabase is currently unavailable. Please try registration again in a moment.", "error")
                    return redirect_to_auth_modal("register", form_data)
                except ValueError as local_error:
                    flash(str(local_error), "error")
            elif any(phrase in message.lower() for phrase in (
                "already registered",
                "already exists",
                "user already registered",
                "duplicate",
            )):
                existing_auth_user = find_supabase_auth_user_by_email(email) if is_supabase_service_role_enabled() else None
                existing_profile = find_profile_by_email(email)
                auth_metadata = safe_auth_user_metadata(existing_auth_user) if existing_auth_user else {}
                detected_role = user_role_for_email(
                    email,
                    (existing_profile or {}).get("role", "user"),
                    auth_metadata,
                ) if existing_auth_user else "user"
                if existing_auth_user and detected_role == "admin":
                    flash("This email is reserved for admin.", "error")
                elif existing_auth_user:
                    if not existing_profile:
                        recover_missing_profile_for_auth_user(
                            existing_auth_user,
                            {
                                "email": email,
                                "full_name": name or (email.split("@")[0] if email else "FreshWash User"),
                                "phone": phone,
                                "address": address,
                                "role": "user",
                                "is_verified": False,
                            },
                        )
                    flash("Account already exists, please login.", "error")
                else:
                    if normalize_email(email) in configured_admin_emails():
                        flash("This email is reserved for admin.", "error")
                    else:
                        flash("Account already exists, please login.", "error")
            elif "could not save the profile row" in message.lower():
                flash(message, "error")
            elif "email rate limit exceeded" in message.lower():
                flash("Please wait before requesting another code.", "error")
            elif "password should contain at least one character" in message.lower():
                flash("Password must include at least one letter and one number.", "error")
            else:
                flash(f"Registration error: {message}", "error")

        return redirect_to_auth_modal("register", form_data)


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user"):
        target = "admin_dashboard" if session["user"].get("is_admin") else "home"
        log_auth_debug("redirect destination", email=session["user"].get("email", ""), target=url_for(target))
        return redirect(url_for("admin_dashboard" if session["user"].get("is_admin") else "home"))

    if request.method == "GET":
        return redirect_to_auth_modal("login")

    if request.method == "POST":
        email    = normalize_email(request.form.get("email", ""))
        password = request.form.get("password", "").strip()
        form_data = {"email": email}
        log_auth_debug(
            "login started",
            email=email,
            login_otp_enabled=ENABLE_LOGIN_OTP,
            flow="password_only" if not ENABLE_LOGIN_OTP else "password_plus_otp",
        )

        errors = validate_login_form(email, password)
        if errors:
            for error in errors:
                flash(error, "error")
            return redirect_to_auth_modal("login", form_data)

        try:
            if local_auth_enabled():
                user = authenticate_local_user(email, password)
                log_auth_debug("local login success", email=email, role=user.get("role", ""), is_admin=user.get("is_admin", False))
            else:
                try:
                    log_auth_debug("supabase login attempt", email=email)
                    res = supabase.auth.sign_in_with_password({"email": email, "password": password})
                    login_user = getattr(res, "user", None)
                    login_session = getattr(res, "session", None)
                    auth_session = supabase.auth.get_session() or login_session
                    current_user_response = supabase.auth.get_user()
                    auth_user = (
                        getattr(current_user_response, "user", None)
                        or getattr(getattr(current_user_response, "data", None), "user", None)
                        or login_user
                    )
                    log_auth_debug(
                        "supabase login result",
                        email=email,
                        has_user=bool(login_user),
                        has_session=bool(login_session),
                    )
                    log_auth_debug("supabase login success", email=email)

                    if not auth_user or not auth_session:
                        flash("Invalid email or password.", "error")
                        return redirect_to_auth_modal("login", form_data)

                    log_auth_debug(
                        "session result",
                        email=email,
                        has_session=bool(auth_session),
                    )
                    log_auth_debug(
                        "current authenticated user",
                        user_id=getattr(auth_user, "id", ""),
                        email=getattr(auth_user, "email", ""),
                    )
                    profile = fetch_supabase_profile_or_error(auth_user)
                    if normalize_email(getattr(auth_user, "email", "")) in configured_admin_emails() and profile.get("role") != "admin":
                        try:
                            execute_update_with_fallback(
                                "profiles",
                                profile_payload_variants({
                                    "id": auth_user.id,
                                    "email": auth_user.email,
                                    "full_name": profile.get("full_name") or auth_user.email.split("@")[0],
                                    "role": "admin",
                                }),
                                "id",
                                auth_user.id,
                                clients=[("service role", get_service_client())] if is_supabase_service_role_enabled() else [("authenticated session", db())],
                            )
                            profile["role"] = "admin"
                            log_auth_debug("profile admin role repaired on login", email=auth_user.email, user_id=auth_user.id)
                        except Exception as role_fix_error:
                            log_exception("profile admin role repair failed on login", role_fix_error, email=auth_user.email, user_id=auth_user.id)
                    user = build_session_user(auth_user, profile)
                    email_confirmed = bool(getattr(auth_user, "email_confirmed_at", None))
                    if email_confirmed and not bool(profile.get("is_verified", True)):
                        set_verification_state(user.get("email", email), True)
                        user["is_verified"] = True
                        log_auth_debug("profile verification synced from supabase auth", email=user.get("email", email))
                    log_auth_debug(
                        "login role detected",
                        email=user.get("email", ""),
                        auth_user_id=auth_user.id,
                        profile_email=profile.get("email", ""),
                        detected_role=user.get("role", ""),
                        is_admin=user.get("is_admin", False),
                        has_session=bool(auth_session),
                    )

                    upsert_local_user(
                        user["name"],
                        user["email"],
                        user.get("phone", ""),
                        user.get("address", ""),
                        password,
                        role_override=user.get("role", "user"),
                    )
                except Exception as auth_error:
                    log_exception("supabase login failed", auth_error, email=email)
                    log_auth_debug("supabase login failure", email=email, error=extract_supabase_error_message(auth_error))
                    message = str(auth_error)
                    lowered = message.lower()
                    if any(phrase in lowered for phrase in (
                        "invalid login credentials",
                        "invalid email or password",
                        "email not confirmed",
                        "invalid credentials",
                    )):
                        flash("Invalid email or password.", "error")
                        return redirect_to_auth_modal("login", form_data)
                    if "admin profile not found" in lowered:
                        flash("Admin profile not found.", "error")
                        return redirect_to_auth_modal("login", form_data)
                    if "not authorized as admin" in lowered:
                        flash("This account is not authorized as admin.", "error")
                        return redirect_to_auth_modal("login", form_data)
                    if not is_supabase_connection_error(auth_error):
                        raise
                    user = authenticate_local_user(email, password)
                    flash("Signed in using locally saved account data because Supabase is currently unavailable.", "success")

            resolved_role = user_role_for_email(
                user.get("email", email),
                user.get("role", "user"),
            )
            user["role"] = resolved_role
            user["is_admin"] = resolved_role == "admin"
            log_auth_debug(
                "role detected",
                email=user.get("email", email),
                role=user.get("role", ""),
                is_admin=user.get("is_admin", False),
            )

            if user.get("is_admin"):
                log_auth_debug("otp skipped for admin", email=user.get("email", ""), role=user.get("role", ""))
                persist_session_user(user)
                log_auth_debug("redirect destination", email=user.get("email", ""), target=url_for("admin_dashboard"))
                flash(f"Welcome back, {user['name']}!", "success")
                return redirect(url_for("admin_dashboard"))

            account_security = get_account_security_state(user.get("email", email))
            if account_security and not account_security.get("is_verified", True):
                if ENABLE_LOGIN_OTP:
                    try:
                        issue_otp_challenge(user.get("email", email), "signup", trigger_send=True)
                    except Exception as resend_error:
                        log_exception("login verification resend failed", resend_error, email=user.get("email", email))
                        lowered = str(resend_error).lower()
                        if "email rate limit exceeded" in lowered:
                            flash("Please wait before requesting another code.", "error")
                        elif "resend code in" in lowered:
                            flash(str(resend_error), "error")
                else:
                    # LOGIN OTP disabled: do not send SMTP/OTP from login flow.
                    log_auth_debug("Skipping login OTP", email=user.get("email", email), login_otp_enabled=ENABLE_LOGIN_OTP)
                    set_pending_otp_challenge(user.get("email", email), "signup")
                flash("Please verify your email before logging in.", "error")
                return redirect_to_auth_modal("verify", otp_modal_form_data())

            persist_session_user(user)
            session["just_registered"] = False
            session.modified = True
            log_auth_debug("redirect destination", email=user.get("email", ""), target=url_for("home"))
            flash(f"Welcome back, {user['name']}!", "success")
            return redirect(url_for("home"))

        except ValueError as e:
            flash(str(e), "error")
        except Exception as e:
            log_exception("login route failed", e, email=email)
            flash(f"Login failed: {str(e)}", "error")

        return redirect_to_auth_modal("login", form_data)


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect_to_auth_modal("login")


# ── Pages ─────────────────────────────────────────────────────────────────────


@app.route("/api/register", methods=["POST"])
def api_register():
    """AJAX-friendly register endpoint used by the OTP modal flow."""
    name     = request.form.get("name", "").strip()
    email    = normalize_email(request.form.get("email", ""))
    phone    = request.form.get("phone", "").strip()
    address  = request.form.get("address", "").strip()
    password = request.form.get("password", "").strip()
    confirm_password = request.form.get("confirm_password", "").strip()

    errors = validate_registration_form(name, email, phone, address, password, confirm_password)
    if errors:
        return jsonify({"ok": False, "errors": errors})

    # Duplicate-submit guard (8-second window)
    signup_submit_cache = session.get("signup_submit_cache") or {}
    recent_submit_iso = signup_submit_cache.get(email)
    recent_submit_at = parse_iso_datetime(recent_submit_iso)
    if recent_submit_at:
        if recent_submit_at.tzinfo is None:
            recent_submit_at = recent_submit_at.replace(tzinfo=timezone.utc)
        if (datetime.now(timezone.utc) - recent_submit_at).total_seconds() < 8:
            return jsonify({"ok": False, "errors": [resend_wait_message(8)]})
    signup_submit_cache[email] = datetime.now(timezone.utc).isoformat()
    session["signup_submit_cache"] = signup_submit_cache
    session.modified = True

    role = resolve_registration_role(email)

    try:
        if local_auth_enabled():
            create_local_user(name, email, phone, address, password,
                              role_override=role, is_verified=(role == "admin"))
        else:
            print(f"REGISTER: SUPABASE_URL={os.environ.get('SUPABASE_URL', '<not set>')}")
            print(f"REGISTER: submitted email={email}")

            existing_profile  = find_profile_by_email(email)
            existing_auth_user = find_supabase_auth_user_by_email(email) if is_supabase_service_role_enabled() else None

            print(f"REGISTER: auth_user_found={bool(existing_auth_user)} profile_found={bool(existing_profile)}")

            auth_metadata = safe_auth_user_metadata(existing_auth_user) if existing_auth_user else {}
            existing_role = user_role_for_email(
                email, (existing_profile or {}).get("role", "user"), auth_metadata
            ) if existing_auth_user else ""

            # Profile exists but no auth user — stale profile from a deleted account.
            if existing_profile and not existing_auth_user:
                print(f"REGISTER: orphaned profile found for {email}, deleting before re-registration")
                try:
                    client = get_service_client()
                    client.table("profiles").delete().eq("email", normalize_email(email)).execute()
                    existing_profile = None
                    print(f"REGISTER: orphaned profile deleted for {email}")
                except Exception as del_exc:
                    log_exception("register orphaned profile delete failed", del_exc, email=email)
                try:
                    with local_auth_conn() as conn:
                        conn.execute("DELETE FROM users WHERE email = ?", (normalize_email(email),))
                except Exception:
                    pass

            if existing_auth_user:
                if existing_role == "admin":
                    return jsonify({"ok": False, "errors": ["This email is reserved for admin."]})
                # Auth user exists — already registered, direct to login
                return jsonify({"ok": False, "errors": ["This email is already registered. Please log in."], "action": "login"})

            # Admin path: create Supabase user immediately (no OTP needed)
            if role == "admin":
                signup_auth_user = create_supabase_signup_user(
                    name=name, email=email, phone=phone, address=address,
                    password=password, role=role,
                )
                ensure_supabase_profile_record(signup_auth_user, {
                    "full_name": name, "email": email, "phone": phone, "address": address,
                    "role": role, "is_verified": True, "otp_code": "", "otp_expiry": None,
                })
                upsert_local_user(name, email, phone, address, password, role_override=role, is_verified=True)
            # Non-admin: defer Supabase user creation to after OTP verification
            # (pending_signup stored in session challenge, created in api_otp_verify)

        if role == "admin":
            return jsonify({"ok": True, "otp": False, "redirect": url_for("admin_dashboard")})

        otp_sent = False
        try:
            issue_otp_challenge(
                email, "signup", trigger_send=True,
                pending_signup={"full_name": name, "email": email, "phone": phone, "address": address, "role": "user", "password": password},
            )
            otp_sent = True
        except Exception as otp_err:
            log_exception("api_register otp send failed", otp_err, email=email)
            try:
                issue_otp_challenge(
                    email, "signup", trigger_send=False,
                    pending_signup={"full_name": name, "email": email, "phone": phone, "address": address, "role": "user", "password": password},
                )
            except Exception:
                pass
            return jsonify({"ok": True, "otp": True, "email": email, "cooldown": OTP_RESEND_COOLDOWN_SECONDS, "warning": str(otp_err)})

        return jsonify({"ok": True, "otp": True, "email": email, "cooldown": OTP_RESEND_COOLDOWN_SECONDS})

    except ValueError as e:
        return jsonify({"ok": False, "errors": [str(e)]})
    except Exception as e:
        log_exception("api_register failed", e, email=email)
        # Clear the submit cache so the user can retry without waiting 8 seconds
        try:
            cache = session.get("signup_submit_cache") or {}
            cache.pop(email, None)
            session["signup_submit_cache"] = cache
            session.modified = True
        except Exception:
            pass
        raw_msg = extract_supabase_error_message(e)
        print(f"REGISTER: Supabase error for {email}: {raw_msg}")
        return jsonify({"ok": False, "errors": [raw_msg]})


@app.route("/verify", methods=["GET"])
def verify_page():
    print("DEBUG: Redirecting to verify page")
    form_data = session.get("auth_form_data") or {}
    return render_template("verify.html", form_data=form_data)


@app.route("/auth/verify-otp", methods=["POST"])
def auth_verify_otp():
    challenge = get_pending_otp_challenge()
    if not challenge:
        flash("Verification session expired. Please login or register again.", "error")
        return redirect_to_auth_modal("login")

    submitted_code = (request.form.get("otp_code", "") or "").strip()
    email = challenge.get("email", "")

    if not submitted_code.isdigit() or len(submitted_code) != OTP_LENGTH:
        flash(f"Enter a valid {OTP_LENGTH}-digit verification code.", "error")
        return redirect_to_auth_modal("verify", otp_modal_form_data(challenge))

    purpose = (challenge.get("purpose") or "signup").strip().lower()
    try:
        otp_record = get_email_otp(email, purpose)
        if not otp_record:
            flash("Verification code expired. Request a new one.", "error")
            return redirect_to_auth_modal("verify", otp_modal_form_data(challenge))

        now_utc = datetime.now(timezone.utc)
        expires_at = otp_record.get("expires_at")
        if isinstance(expires_at, datetime):
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at <= now_utc:
                mark_email_otp_used(otp_record.get("id"))
                try:
                    clear_otp_for_account(email)
                except Exception:
                    pass
                flash("Verification code expired. Request a new one.", "error")
                return redirect_to_auth_modal("verify", otp_modal_form_data(challenge))

        if otp_record.get("otp_code") != submitted_code:
            remaining = max(0, int(challenge.get("attempts_remaining", OTP_MAX_ATTEMPTS) or OTP_MAX_ATTEMPTS) - 1)
            challenge["attempts_remaining"] = remaining
            session["pending_otp"] = challenge
            session.modified = True
            if remaining <= 0:
                mark_email_otp_used(otp_record.get("id"))
                try:
                    clear_otp_for_account(email)
                except Exception:
                    pass
                flash("Maximum attempts reached. Please request a new verification code.", "error")
            else:
                flash("Invalid verification code.", "error")
            return redirect_to_auth_modal("verify", otp_modal_form_data(challenge))

        mark_email_otp_used(otp_record.get("id"))
        try:
            clear_otp_for_account(email)
        except Exception:
            pass

        if purpose == "signup":
            pending_signup = challenge.get("pending_signup") or {}
            signup_role = normalize_profile_role(pending_signup.get("role", "user"))
            full_name = pending_signup.get("full_name") or (email.split("@")[0] if email else "FreshWash User")
            phone = pending_signup.get("phone", "")
            address = pending_signup.get("address", "")
            password = pending_signup.get("password", "")
            if not password:
                try:
                    set_verification_state(email, True)
                except Exception as verify_state_error:
                    log_exception("set verification state skipped", verify_state_error, email=safe_email_for_log(email))
                profile = find_profile_by_email(email) or {}
                if not profile and local_auth_enabled():
                    local_user, _ = find_local_user(email)
                    if local_user:
                        profile = {
                            "id": local_user.get("id", ""),
                            "full_name": local_user.get("full_name", ""),
                            "phone": local_user.get("phone", ""),
                            "address": local_user.get("address", ""),
                            "avatar": local_user.get("avatar", ""),
                            "role": local_user.get("role", "user"),
                        }
                resolved_role = user_role_for_email(email, profile.get("role", "user"))
                verified_session_user = {
                    "id": profile.get("id", ""),
                    "email": email,
                    "name": profile.get("full_name") or (email.split("@")[0] if email else "FreshWash User"),
                    "phone": profile.get("phone", ""),
                    "address": profile.get("address", ""),
                    "avatar": profile.get("avatar", ""),
                    "role": resolved_role,
                    "is_admin": resolved_role == "admin",
                }
                clear_pending_otp_challenge()
                persist_session_user(verified_session_user)
                flash("Account verified! Welcome to FreshWash.", "success")
                return redirect(url_for("admin_dashboard" if verified_session_user.get("is_admin") else "home"))

            if not local_auth_enabled() and not is_supabase_service_role_enabled():
                raise ValueError(
                    "SUPABASE_SERVICE_ROLE_KEY is required to complete signup after OTP verification."
                )

            verified_user = None
            if is_supabase_service_role_enabled():
                existing_auth_user = find_supabase_auth_user_by_email(email)
                if existing_auth_user:
                    verified_user = existing_auth_user
                else:
                    verified_user = create_supabase_signup_user(
                        name=full_name,
                        email=email,
                        phone=phone,
                        address=address,
                        password=password,
                        role=signup_role,
                        email_confirm=True,
                    )

            profile_defaults = {
                "full_name": full_name,
                "email": email,
                "phone": phone,
                "address": address,
                "role": signup_role,
                "is_verified": True,
                "otp_code": "",
                "otp_expiry": None,
            }
            if verified_user:
                ensure_supabase_profile_record(verified_user, profile_defaults)
            try:
                set_verification_state(email, True)
            except Exception as verify_state_error:
                log_exception("set verification state skipped", verify_state_error, email=safe_email_for_log(email))
            upsert_local_user(
                profile_defaults["full_name"],
                email,
                profile_defaults["phone"],
                profile_defaults["address"],
                password,
                role_override=signup_role,
                is_verified=True,
            )
            clear_pending_otp_challenge()
            profile = find_profile_by_email(email) or profile_defaults
            resolved_role = user_role_for_email(email, profile.get("role", "user"))
            verified_session_user = {
                "id": profile.get("id", "") or (getattr(verified_user, "id", "") if verified_user else ""),
                "email": email,
                "name": profile.get("full_name") or (email.split("@")[0] if email else "FreshWash User"),
                "phone": profile.get("phone", ""),
                "address": profile.get("address", ""),
                "avatar": profile.get("avatar", ""),
                "role": resolved_role,
                "is_admin": resolved_role == "admin",
            }
            persist_session_user(verified_session_user)
            flash("Account verified! Welcome to FreshWash.", "success")
            return redirect(url_for("home"))

        pending_user = challenge.get("pending_user") or {}
        if not pending_user:
            profile = find_profile_by_email(email) or {}
            if not profile and local_auth_enabled():
                local_user, _ = find_local_user(email)
                if local_user:
                    profile = {
                        "id": local_user.get("id", ""),
                        "full_name": local_user.get("full_name", ""),
                        "phone": local_user.get("phone", ""),
                        "address": local_user.get("address", ""),
                        "avatar": local_user.get("avatar", ""),
                        "role": local_user.get("role", "user"),
                    }
            resolved_role = user_role_for_email(email, profile.get("role", "user"))
            pending_user = {
                "id": profile.get("id", ""),
                "email": email,
                "name": profile.get("full_name") or (email.split("@")[0] if email else "FreshWash User"),
                "phone": profile.get("phone", ""),
                "address": profile.get("address", ""),
                "avatar": profile.get("avatar", ""),
                "role": resolved_role,
                "is_admin": resolved_role == "admin",
            }

        clear_pending_otp_challenge()
        persist_session_user(pending_user)
        flash(f"Welcome back, {pending_user.get('name', 'FreshWash User')}!", "success")
        return redirect(url_for("home"))
    except Exception as verify_error:
        log_exception("verify otp failed", verify_error, email=email, purpose=purpose, token=submitted_code)
        raw_message = extract_supabase_error_message(verify_error)
        lowered = raw_message.lower()
        if "expired" in lowered:
            flash("Verification code expired. Request a new one.", "error")
        elif "rate limit" in lowered:
            flash("Please wait before requesting another code.", "error")
        elif raw_message:
            flash(raw_message, "error")
        else:
            flash("Invalid verification code.", "error")
        return redirect_to_auth_modal("verify", otp_modal_form_data(challenge))


@app.route("/auth/resend-otp", methods=["POST"])
def auth_resend_otp():
    challenge = get_pending_otp_challenge()
    if not challenge:
        flash("Verification session expired. Please login or register again.", "error")
        return redirect_to_auth_modal("login")

    resend_at = parse_iso_datetime(challenge.get("resend_available_at"))
    if resend_at and datetime.now(timezone.utc) < resend_at:
        wait_seconds = int((resend_at - datetime.now(timezone.utc)).total_seconds())
        flash(resend_wait_message(wait_seconds), "error")
        return redirect_to_auth_modal("verify", otp_modal_form_data(challenge))

    try:
        issue_otp_challenge(
            challenge.get("email", ""),
            challenge.get("purpose", "signup"),
            pending_user=challenge.get("pending_user"),
            trigger_send=True,
            pending_signup=challenge.get("pending_signup"),
        )
        flash("Verification code sent. Check your email or spam folder.", "success")
    except Exception as otp_error:
        log_exception("resend verification failed", otp_error, email=challenge.get("email", ""))
        lowered = str(otp_error).lower()
        if "email rate limit exceeded" in lowered:
            flash("Please wait before requesting another code.", "error")
        elif "resend code in" in lowered:
            flash(str(otp_error), "error")
        elif "smtp" in lowered or "credential" in lowered:
            flash(str(otp_error), "error")
        else:
            smtp_message = extract_supabase_error_message(otp_error)
            flash(f"Failed to send verification. SMTP error: {smtp_message}", "error")
            flash(otp_send_failure_message(), "error")
            flash(otp_send_delivery_note(), "error")
    return redirect_to_auth_modal("verify", otp_modal_form_data())



@app.route("/api/otp/verify", methods=["POST"])
def api_otp_verify():
    data = request.get_json(silent=True) or {}
    submitted_code = (data.get("otp_code") or "").strip()
    challenge = get_pending_otp_challenge()
    if not challenge:
        return jsonify({"ok": False, "error": "Verification session expired. Please register or login again."})
    if not submitted_code.isdigit() or len(submitted_code) != OTP_LENGTH:
        return jsonify({"ok": False, "error": f"Enter a valid {OTP_LENGTH}-digit code."})
    email = challenge.get("email", "")
    purpose = (challenge.get("purpose") or "signup").strip().lower()
    try:
        otp_record = get_email_otp(email, purpose)
        if not otp_record:
            return jsonify({"ok": False, "error": "Code expired. Request a new one."})
        now_utc = datetime.now(timezone.utc)
        expires_at = otp_record.get("expires_at")
        if isinstance(expires_at, datetime):
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at <= now_utc:
                mark_email_otp_used(otp_record.get("id"))
                try: clear_otp_for_account(email)
                except Exception: pass
                return jsonify({"ok": False, "error": "Code expired. Request a new one."})
        if otp_record.get("otp_code") != submitted_code:
            remaining = max(0, int(challenge.get("attempts_remaining", OTP_MAX_ATTEMPTS) or OTP_MAX_ATTEMPTS) - 1)
            challenge["attempts_remaining"] = remaining
            session["pending_otp"] = challenge
            session.modified = True
            if remaining <= 0:
                mark_email_otp_used(otp_record.get("id"))
                try: clear_otp_for_account(email)
                except Exception: pass
                return jsonify({"ok": False, "error": "Maximum attempts reached. Request a new code."})
            return jsonify({"ok": False, "error": f"Invalid code. {remaining} attempt(s) left."})
        mark_email_otp_used(otp_record.get("id"))
        try: clear_otp_for_account(email)
        except Exception: pass
        if purpose == "signup":
            pending_signup = challenge.get("pending_signup") or {}
            signup_role = normalize_profile_role(pending_signup.get("role", "user"))
            full_name = pending_signup.get("full_name") or (email.split("@")[0] if email else "FreshWash User")
            phone = pending_signup.get("phone", "")
            address = pending_signup.get("address", "")
            password = pending_signup.get("password", "")
            if password:
                if is_supabase_service_role_enabled():
                    # Create the Supabase auth user NOW (deferred from registration)
                    existing_auth_user = find_supabase_auth_user_by_email(email)
                    if existing_auth_user:
                        verified_user = existing_auth_user
                        print(f"OTP_VERIFY: auth user already exists for {email}, reusing")
                    else:
                        print(f"OTP_VERIFY: creating Supabase auth user for {email}")
                        verified_user = create_supabase_signup_user(
                            name=full_name, email=email, phone=phone, address=address,
                            password=password, role=signup_role, email_confirm=True,
                        )
                        print(f"OTP_VERIFY: Supabase auth user created id={getattr(verified_user, 'id', '?')}")
                    ensure_supabase_profile_record(verified_user, {
                        "full_name": full_name, "email": email, "phone": phone,
                        "address": address, "role": signup_role, "is_verified": True,
                        "otp_code": "", "otp_expiry": None,
                    })
                try: set_verification_state(email, True)
                except Exception: pass
                upsert_local_user(full_name, email, phone, address, password,
                                  role_override=signup_role, is_verified=True)
            else:
                try: set_verification_state(email, True)
                except Exception: pass
            clear_pending_otp_challenge()
            # Do NOT auto-login after signup OTP — send user to login modal
            session["just_registered"] = True
            session.modified = True
            return jsonify({
                "ok": True,
                "action": "login",
                "email": email,
                "message": "Email verified successfully. Please log in.",
            })
        pending_user = challenge.get("pending_user") or {}
        if not pending_user:
            profile = find_profile_by_email(email) or {}
            if not profile and local_auth_enabled():
                local_user, _ = find_local_user(email)
                if local_user:
                    profile = {"id": local_user.get("id",""), "full_name": local_user.get("full_name",""),
                               "phone": local_user.get("phone",""), "address": local_user.get("address",""),
                               "avatar": local_user.get("avatar",""), "role": local_user.get("role","user")}
            resolved_role = user_role_for_email(email, profile.get("role", "user"))
            pending_user = {"id": profile.get("id",""), "email": email,
                            "name": profile.get("full_name") or email.split("@")[0],
                            "phone": profile.get("phone",""), "address": profile.get("address",""),
                            "avatar": profile.get("avatar",""), "role": resolved_role,
                            "is_admin": resolved_role == "admin"}
        clear_pending_otp_challenge()
        persist_session_user(pending_user)
        redirect_url = url_for("admin_dashboard") if pending_user.get("is_admin") else url_for("home")
        return jsonify({"ok": True, "redirect": redirect_url})
    except Exception as exc:
        log_exception("api_otp_verify failed", exc, email=email)
        return jsonify({"ok": False, "error": extract_supabase_error_message(exc)})


@app.route("/api/otp/resend", methods=["POST"])
def api_otp_resend():
    challenge = get_pending_otp_challenge()
    if not challenge:
        return jsonify({"ok": False, "error": "Verification session expired. Please register or login again."})
    resend_at = parse_iso_datetime(challenge.get("resend_available_at"))
    if resend_at:
        if resend_at.tzinfo is None:
            resend_at = resend_at.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) < resend_at:
            wait = int((resend_at - datetime.now(timezone.utc)).total_seconds())
            return jsonify({"ok": False, "error": resend_wait_message(wait)})
    try:
        issue_otp_challenge(
            challenge.get("email", ""), challenge.get("purpose", "signup"),
            pending_user=challenge.get("pending_user"), trigger_send=True,
            pending_signup=challenge.get("pending_signup"),
        )
        return jsonify({"ok": True, "message": "Verification code sent."})
    except Exception as exc:
        log_exception("api_otp_resend failed", exc)
        return jsonify({"ok": False, "error": str(exc)})


@app.route("/dashboard")
@login_required
def dashboard():
    try:
        if session["user"].get("is_admin"):
            return redirect(url_for("admin_dashboard"))
        user = session["user"]
        try:
            res = db().table("bookings").select("*") \
                .eq("user_id", user["id"]) \
                .order("created_at", desc=True) \
                .limit(3).execute()
            recent = res.data or []
        except Exception as exc:
            log_exception("dashboard bookings fetch failed", exc, user=user.get("email", ""))
            recent = []
        return render_template("dashboard.html", user=user, recent=recent or [])
    except Exception as exc:
        log_exception("dashboard route failed", exc, user=session.get("user", {}))
        flash("FreshWash could not load the dashboard right now.", "error")
        return render_template("dashboard.html", user=session.get("user", {}), recent=[])


@app.route("/admin")
@app.route("/admin/dashboard")
@app.route("/admin-dashboard")
@app.route("/admin_dashboard")
@admin_required
def admin_dashboard():
    return render_admin_dashboard_view("dashboard")


@app.route("/admin/users")
@app.route("/admin-users")
@app.route("/admin_users")
@admin_required
def admin_users():
    return render_admin_dashboard_view("users")


@app.route("/admin/bookings")
@app.route("/admin-bookings")
@app.route("/admin_bookings")
@admin_required
def admin_bookings():
    return render_admin_dashboard_view("bookings")


@app.route("/admin/machines")
@app.route("/admin-machines")
@app.route("/admin_machines")
@admin_required
def admin_machines():
    return render_admin_dashboard_view("machines")


@app.route("/admin/services")
@app.route("/admin-services")
@app.route("/admin_services")
@admin_required
def admin_services():
    return render_admin_dashboard_view("services")


@app.route("/admin/reports")
@app.route("/admin-reports")
@app.route("/admin_reports")
@admin_required
def admin_reports():
    return render_admin_dashboard_view("reports")


@app.route("/admin/settings")
@app.route("/admin-settings")
@app.route("/admin_settings")
@admin_required
def admin_settings():
    return render_admin_dashboard_view("settings")


@app.route("/admin/api/dashboard-data", methods=["GET"])
@admin_required
def admin_dashboard_data_api():
    try:
        return jsonify({"ok": True, "data": build_admin_dashboard_payload()})
    except Exception as exc:
        log_exception("admin dashboard data api failed", exc, user=session.get("user", {}).get("email", ""))
        return jsonify({"ok": False, "error": f"Could not load admin dashboard data: {exc}"}), 500


@app.route("/admin/api/users/<user_id>", methods=["POST"])
@app.route("/admin/api/users", methods=["POST"])
@admin_required
def admin_user_action(user_id=None):
    data = request.get_json() or {}
    action = data.get("action")
    try:
        if action == "create":
            name = data.get("name", "").strip()
            email = normalize_email(data.get("email", ""))
            phone = data.get("phone", "").strip()
            address = data.get("address", "").strip()
            password = data.get("password", "").strip()
            role = normalize_profile_role(data.get("role", "user"))
            if not all([name, email, phone, address, password]):
                return jsonify({"ok": False, "error": "Name, email, phone, address, and password are required."}), 400
            if len(password) < 6:
                return jsonify({"ok": False, "error": "Password must be at least 6 characters."}), 400
            if local_auth_enabled():
                create_local_user(name, email, phone, address, password, role_override=role)
            else:
                if not is_supabase_service_role_enabled():
                    return jsonify({"ok": False, "error": "Creating users in Supabase admin mode requires SUPABASE_SERVICE_ROLE_KEY."}), 400
                admin_create_supabase_user(name, email, phone, address, password, role)
        elif action == "edit":
            name = data.get("name", "").strip()
            email = normalize_email(data.get("email", ""))
            phone = data.get("phone", "").strip()
            address = data.get("address", "").strip()
            avatar = data.get("avatar", "") or ""
            role = normalize_profile_role(data.get("role", "user"))
            if not name:
                return jsonify({"ok": False, "error": "Name is required."}), 400
            if not email:
                return jsonify({"ok": False, "error": "Email is required."}), 400
            if not is_valid_email(email):
                return jsonify({"ok": False, "error": "Enter a valid email address."}), 400
            if not phone:
                return jsonify({"ok": False, "error": "Phone number is required."}), 400
            if not address:
                return jsonify({"ok": False, "error": "Address is required."}), 400
            if local_auth_enabled():
                admin_update_local_user(user_id, name, email, phone, address, avatar, role_override=role)
            else:
                if not is_supabase_service_role_enabled():
                    return jsonify({"ok": False, "error": "Editing Supabase users requires SUPABASE_SERVICE_ROLE_KEY."}), 400
                admin_update_supabase_user(user_id, name, email, phone, address, avatar, role)
            if session["user"]["id"] == user_id:
                session["user"]["name"] = name
                session["user"]["email"] = email
                session["user"]["phone"] = phone
                session["user"]["address"] = address
                session["user"]["avatar"] = avatar
                session["user"]["role"] = role
                persist_session_user(session["user"])
        elif action == "delete":
            if session["user"]["id"] == user_id:
                return jsonify({"ok": False, "error": "You cannot delete the active admin account."}), 400
            if local_auth_enabled():
                admin_delete_local_user(user_id)
            else:
                if not is_supabase_service_role_enabled():
                    return jsonify({"ok": False, "error": "Deleting Supabase users requires SUPABASE_SERVICE_ROLE_KEY."}), 400
                admin_delete_supabase_user(user_id)
        else:
            return jsonify({"ok": False, "error": "Unsupported user action."}), 400
        return jsonify({"ok": True, "data": build_admin_dashboard_payload()})
    except ValueError as exc:
        log_exception("admin user action validation failed", exc, action=action, user_id=user_id)
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        log_exception("admin user action failed", exc, action=action, user_id=user_id, data=data)
        return jsonify({"ok": False, "error": f"User action failed: {exc}"}), 500


@app.route("/admin/api/bookings/<booking_id>", methods=["POST"])
@admin_required
def admin_booking_action(booking_id):
    client = admin_db_client()
    if not client:
        return jsonify({"ok": False, "error": "Booking management needs a configured database connection."}), 400

    data = request.get_json() or {}
    action = data.get("action")
    try:
        if action == "status":
            status = data.get("status", "").strip()
            if status not in {"Pending", "In Progress", "Completed", "Cancelled"}:
                return jsonify({"ok": False, "error": "Invalid status value."}), 400
            client.table("bookings").update({"status": status}).eq("id", booking_id).execute()
        elif action == "edit":
            payload = {}
            maybe_status = (data.get("status", "") or "").strip()
            if maybe_status:
                if maybe_status not in {"Pending", "In Progress", "Completed", "Cancelled"}:
                    return jsonify({"ok": False, "error": "Invalid status value."}), 400
                payload["status"] = maybe_status

            maybe_delivery = (data.get("delivery_option", "") or "").strip().title()
            if maybe_delivery:
                if maybe_delivery not in {"Pickup", "Delivery"}:
                    return jsonify({"ok": False, "error": "Invalid delivery option value."}), 400
                payload["delivery_option"] = maybe_delivery
                payload["delivery_type"] = maybe_delivery.lower()
                payload["delivery_fee"] = DEFAULT_DELIVERY_FEE if maybe_delivery == "Delivery" else 0

            if "notes" in data:
                payload["notes"] = (data.get("notes", "") or "").strip()

            for field in ("full_name", "service_type", "machine", "pickup_date", "pickup_time", "load_type"):
                if field in data and str(data.get(field, "")).strip():
                    payload[field] = str(data.get(field, "")).strip()

            if not payload:
                return jsonify({"ok": False, "error": "No booking fields provided for update."}), 400

            if "delivery_option" in payload:
                try:
                    existing_res = client.table("bookings").select("total_price,delivery_fee").eq("id", booking_id).limit(1).execute()
                    existing = (existing_res.data or [{}])[0] if existing_res else {}
                except Exception as exc:
                    missing_column = extract_schema_cache_missing_column(exc, "bookings")
                    if missing_column in {"delivery_fee"}:
                        existing_res = client.table("bookings").select("total_price").eq("id", booking_id).limit(1).execute()
                        existing = (existing_res.data or [{}])[0] if existing_res else {}
                        existing["delivery_fee"] = 0
                    else:
                        raise
                previous_delivery_fee = float(existing.get("delivery_fee", 0) or 0)
                current_total = float(existing.get("total_price", 0) or 0)
                base_amount = max(current_total - previous_delivery_fee, 0)
                new_delivery_fee = float(payload.get("delivery_fee", 0) or 0)
                new_total = round(base_amount + new_delivery_fee, 2)
                payload["total_price"] = new_total
                payload["total_amount"] = new_total

            if payload.get("status") and payload["status"] not in {"Pending", "In Progress", "Completed", "Cancelled"}:
                return jsonify({"ok": False, "error": "Invalid status value."}), 400
            update_variants = [
                payload,
                {k: v for k, v in payload.items() if k not in {"delivery_fee", "delivery_type", "total_amount"}},
                {k: v for k, v in payload.items() if k not in {"delivery_fee", "delivery_type", "total_amount", "delivery_option"}},
            ]
            tried = set()
            last_error = None
            updated = False
            for variant in update_variants:
                if not variant:
                    continue
                key = tuple(sorted(variant.keys()))
                if key in tried:
                    continue
                tried.add(key)
                try:
                    client.table("bookings").update(variant).eq("id", booking_id).execute()
                    updated = True
                    break
                except Exception as exc:
                    missing_column = extract_schema_cache_missing_column(exc, "bookings")
                    if missing_column:
                        last_error = exc
                        continue
                    raise
            if not updated:
                if last_error:
                    raise last_error
                raise RuntimeError("Booking update failed because no compatible bookings schema variant was found.")
        elif action == "cancel":
            client.table("bookings").update({"status": "Cancelled"}).eq("id", booking_id).execute()
        elif action == "delete":
            client.table("bookings").delete().eq("id", booking_id).execute()
        else:
            return jsonify({"ok": False, "error": "Unsupported booking action."}), 400
        return jsonify({"ok": True, "data": build_admin_dashboard_payload()})
    except Exception as exc:
        log_exception("admin booking action failed", exc, action=action, booking_id=booking_id, data=data)
        return jsonify({"ok": False, "error": f"Booking update failed: {exc}"}), 500


@app.route("/admin/api/machines/<int:machine_number>", methods=["POST"])
@admin_required
def admin_machine_action(machine_number):
    data = request.get_json() or {}
    name = data.get("name")
    status = data.get("status")
    enabled = data.get("enabled")
    load_type = data.get("load_type")
    allowed_load_types = set(get_admin_settings()["machines"]["default_load_types"])
    if name is not None and not str(name).strip():
        return jsonify({"ok": False, "error": "Machine name is required."}), 400
    if status is not None and status not in VALID_MACHINE_STATUSES:
        return jsonify({"ok": False, "error": "Invalid machine status."}), 400
    if load_type is not None and load_type not in allowed_load_types:
        return jsonify({"ok": False, "error": "Invalid load type."}), 400
    try:
        update_machine(machine_number, name=name, status=status, enabled=enabled, load_type=load_type)
        return jsonify({"ok": True, "data": build_admin_dashboard_payload()})
    except Exception as exc:
        log_exception("admin machine action failed", exc, machine_number=machine_number, data=data)
        return jsonify({"ok": False, "error": f"Machine update failed: {exc}"}), 500


@app.route("/api/update-machine-status", methods=["PATCH", "POST"])
@admin_required
def update_machine_status_api():
    data = request.get_json() or {}
    machine_id = data.get("id") or data.get("machine_id") or data.get("machine_number")
    status = data.get("status")
    load_type = data.get("load_type")
    if status not in VALID_MACHINE_STATUSES:
        return jsonify({"ok": False, "error": "Invalid machine status."}), 400
    try:
        update_machine_status_by_id(machine_id, status, load_type=load_type)
        return jsonify({"ok": True, "data": build_admin_dashboard_payload()})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        log_exception("machine status api failed", exc, data=data)
        return jsonify({"ok": False, "error": f"Machine status update failed: {exc}"}), 500


@app.route("/admin/api/services/<path:service_name>", methods=["POST"])
@app.route("/admin/api/services", methods=["POST"])
@admin_required
def admin_service_action(service_name=None):
    data = request.get_json() or {}
    action = data.get("action", "save")
    if action == "create":
        service_name = data.get("name", "").strip()
    description = data.get("description", "").strip()
    if not service_name:
        return jsonify({"ok": False, "error": "Service name is required."}), 400
    try:
        price = float(data.get("price", 0))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "Enter a valid numeric price."}), 400

    if action != "delete" and not description:
        return jsonify({"ok": False, "error": "Service description is required."}), 400

    if action == "delete":
        client = admin_db_client()
        if client:
            try:
                client.table("services").delete().eq("name", service_name).execute()
            except Exception as exc:
                log_exception("admin service delete failed", exc, service_name=service_name)
        with local_auth_conn() as conn:
            conn.execute("DELETE FROM admin_services WHERE name = ?", (service_name,))
    elif action == "create":
        client = admin_db_client()
        if client:
            try:
                client.table("services").upsert(
                    {"name": service_name, "price": price, "description": description},
                    on_conflict="name"
                ).execute()
            except Exception as exc:
                log_exception("admin service create failed", exc, service_name=service_name)
        with local_auth_conn() as conn:
            conn.execute(
                """
                INSERT INTO admin_services (name, price, description)
                VALUES (?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                  price = excluded.price,
                  description = excluded.description
                """,
                (service_name, price, description)
            )
    else:
        update_service(service_name, price, description)
    try:
        return jsonify({"ok": True, "data": build_admin_dashboard_payload()})
    except Exception as exc:
        log_exception("admin service payload refresh failed", exc, action=action, service_name=service_name)
        return jsonify({"ok": False, "error": f"Service update failed: {exc}"}), 500


@app.route("/admin/api/settings", methods=["POST"])
@admin_required
def admin_settings_action():
    data = request.get_json() or {}
    action = data.get("action", "").strip()

    try:
        if action == "profile":
            name = data.get("name", "").strip()
            email = normalize_email(data.get("email", ""))
            phone = data.get("phone", "").strip()
            address = data.get("address", session.get("user", {}).get("address", "")).strip()
            password = data.get("password", "").strip()
            if not name:
                return jsonify({"ok": False, "error": "Admin name is required."}), 400
            if not email or not is_valid_email(email):
                return jsonify({"ok": False, "error": "Enter a valid admin email."}), 400
            if password and len(password) < 6:
                return jsonify({"ok": False, "error": "Password must be at least 6 characters."}), 400
            update_admin_profile_settings(
                session["user"]["id"],
                name,
                email,
                phone,
                password,
                address=address,
                avatar=session["user"].get("avatar", ""),
            )
            session["user"]["name"] = name
            session["user"]["email"] = email
            session["user"]["phone"] = phone
            session["user"]["address"] = address
            persist_session_user(session["user"])
        elif action == "system":
            shop_name = data.get("shop_name", "").strip()
            contact_number = data.get("contact_number", "").strip()
            shop_address = data.get("shop_address", "").strip()
            if not shop_name:
                return jsonify({"ok": False, "error": "Shop name is required."}), 400
            save_admin_settings({
                "shop_name": shop_name,
                "contact_number": contact_number,
                "shop_address": shop_address,
            })
        elif action == "machines":
            raw_load_types = data.get("default_load_types", "")
            default_load_types = normalize_load_type_list(str(raw_load_types).split(","))
            machines_globally_enabled = bool(data.get("machines_globally_enabled", True))
            save_admin_settings({
                "default_load_types": default_load_types,
                "machines_globally_enabled": machines_globally_enabled,
            })
        elif action == "theme":
            mode = (data.get("mode", "light") or "light").strip().lower()
            accent = (data.get("accent", "pink-rose") or "pink-rose").strip().lower()
            if mode not in {"light", "dark"}:
                return jsonify({"ok": False, "error": "Invalid theme mode."}), 400
            if accent not in {"pink-rose", "pink-blush", "pink-berry"}:
                return jsonify({"ok": False, "error": "Invalid color theme."}), 400
            save_admin_settings({"theme_mode": mode, "theme_accent": accent})
        else:
            return jsonify({"ok": False, "error": "Unsupported settings action."}), 400
        return jsonify({"ok": True, "data": build_admin_dashboard_payload()})
    except ValueError as exc:
        log_exception("admin settings validation failed", exc, action=action, data=data)
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        log_exception("admin settings action failed", exc, action=action, data=data)
        return jsonify({"ok": False, "error": f"Settings update failed: {exc}"}), 500


@app.route("/admin/api/test-otp-email", methods=["POST"])
@admin_required
def admin_test_otp_email():
    data = request.get_json(silent=True) or {}
    recipient = normalize_email((data.get("email") or session.get("user", {}).get("email", "")).strip())
    if not recipient:
        return jsonify({"ok": False, "error": "Recipient email is required."}), 400
    if not is_valid_email(recipient):
        return jsonify({"ok": False, "error": "Enter a valid recipient email address."}), 400
    try:
        otp_code = generate_otp_code()
        send_otp_email(recipient, otp_code)
        return jsonify({"ok": True, "message": f"OTP email sent to {recipient}."})
    except Exception as exc:
        log_exception("admin test otp email failed", exc, recipient=recipient)
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/update-profile", methods=["POST"])
@admin_required
def api_update_profile():
    active_user = session.get("user") or {}
    user_id = active_user.get("id", "")
    if not user_id:
        return jsonify({"success": False, "error": "Missing session. Please log in again."}), 401

    name = (request.form.get("name", "") or "").strip()
    email = normalize_email(request.form.get("email", "") or "")
    phone = (request.form.get("phone", "") or "").strip()
    address = (request.form.get("address", "") or "").strip()
    uploaded = request.files.get("avatar")
    print(
        "DEBUG /api/update-profile request:",
        {
            "user_id": user_id,
            "name": name,
            "email": email,
            "phone": phone,
            "address": address,
            "has_avatar_file": bool(uploaded and uploaded.filename),
        },
    )

    if not all([name, email, phone, address]):
        return jsonify({"success": False, "error": "Name, email, phone, and address are required."}), 400
    if not is_valid_email(email):
        return jsonify({"success": False, "error": "Enter a valid email address."}), 400

    avatar_url = active_user.get("avatar", "") or ""
    if uploaded and uploaded.filename:
        if not (uploaded.mimetype or "").startswith("image/"):
            return jsonify({"success": False, "error": "Only image uploads are allowed."}), 400
        image_bytes = uploaded.read()
        if not image_bytes:
            return jsonify({"success": False, "error": "The selected image is empty."}), 400
        if len(image_bytes) > 2 * 1024 * 1024:
            return jsonify({"success": False, "error": "Profile photo must be 2MB or smaller."}), 400
        try:
            avatar_url = upload_admin_avatar_to_storage(user_id, image_bytes, uploaded.mimetype)
        except ValueError as exc:
            log_exception("api update-profile avatar upload failed", exc, user=active_user.get("email", ""))
            return jsonify({"success": False, "error": str(exc)}), 500

    try:
        update_admin_profile_settings(
            user_id,
            name,
            email,
            phone,
            password="",
            address=address,
            avatar=avatar_url,
        )
        session["user"]["name"] = name
        session["user"]["email"] = email
        session["user"]["phone"] = phone
        session["user"]["address"] = address
        session["user"]["avatar"] = avatar_url
        persist_session_user(session["user"])
        payload = build_admin_dashboard_payload()
        print("DEBUG /api/update-profile Supabase/profile update success for:", email)
        return jsonify({"success": True, "message": "Profile updated successfully", "avatar": avatar_url, "data": payload})
    except Exception as exc:
        log_exception("api update-profile failed", exc, user=active_user.get("email", ""))
        return jsonify({"success": False, "error": f"Profile update failed: {exc}"}), 500


@app.route("/test-email", methods=["GET", "POST"])
@admin_required
def test_email():
    payload = request.get_json(silent=True) or {}
    source_email = payload.get("email") if request.method == "POST" else request.args.get("email")
    recipient = normalize_email((source_email or session.get("user", {}).get("email", "")).strip())
    if not recipient:
        return jsonify({"ok": False, "error": "Recipient email is required."}), 400
    if not is_valid_email(recipient):
        return jsonify({"ok": False, "error": "Enter a valid recipient email address."}), 400
    try:
        otp_code = generate_otp_code()
        send_otp_email(recipient, otp_code)
        return jsonify({"ok": True, "message": f"OTP email sent to {recipient}."})
    except Exception as exc:
        log_exception("test-email failed", exc, recipient=recipient)
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/admin/api/profile-photo", methods=["POST"])
@admin_required
def admin_profile_photo_upload():
    active_user = session.get("user") or {}
    user_id = active_user.get("id", "")
    if not user_id:
        return jsonify({"ok": False, "error": "Missing session. Please log in again."}), 401
    if not is_supabase_enabled():
        return jsonify(
            {
                "ok": False,
                "error": (
                    "Supabase is not configured for profile photo uploads. "
                    f"Check SUPABASE_URL and keys. Details: {get_supabase_config_error()}"
                ),
            }
        ), 500
    if not is_supabase_service_role_enabled():
        return jsonify({"ok": False, "error": "SUPABASE_SERVICE_ROLE_KEY is required to upload admin profile photos."}), 500

    uploaded = request.files.get("avatar") or request.files.get("profile_image")
    if not uploaded or not uploaded.filename:
        return jsonify({"ok": False, "error": "Choose an image to upload."}), 400
    if not (uploaded.mimetype or "").startswith("image/"):
        return jsonify({"ok": False, "error": "Only image uploads are allowed."}), 400

    image_bytes = uploaded.read()
    if not image_bytes:
        return jsonify({"ok": False, "error": "The selected image is empty."}), 400
    if len(image_bytes) > 2 * 1024 * 1024:
        return jsonify({"ok": False, "error": "Profile photo must be 2MB or smaller."}), 400

    try:
        avatar = upload_admin_avatar_to_storage(
            user_id,
            image_bytes,
            uploaded.mimetype,
        )
    except ValueError as exc:
        log_exception("admin profile photo storage upload failed", exc, user=active_user.get("email", ""))
        return jsonify({"ok": False, "error": str(exc)}), 500

    try:
        update_admin_avatar(
            user_id,
            avatar,
        )
    except ValueError as exc:
        log_exception("admin profile avatar update failed", exc, user=active_user.get("email", ""), avatar=avatar)
        return jsonify({"ok": False, "error": str(exc)}), 500

    try:
        session["user"]["avatar"] = avatar
        persist_session_user(session["user"])
        return jsonify({"ok": True, "avatar": avatar, "data": build_admin_dashboard_payload()})
    except Exception as exc:
        log_exception("admin profile photo upload failed", exc, user=session.get("user", {}).get("email", ""))
        return jsonify({"ok": False, "error": f"Photo upload failed: {exc}"}), 500


@app.route("/services")
@login_required
def services():
    return render_template("services_page.html", services=SERVICES, user=session["user"])


@app.route("/booking", methods=["GET", "POST"])
@login_required
def booking():
    user = session["user"]
    try:
        machines = [machine for machine in admin_dashboard_machines() if machine.get("effective_enabled", machine.get("enabled"))]
    except Exception as exc:
        log_exception("booking machines fetch failed", exc, user=user.get("email", ""))
        machines = []
    machines_by_name = {
        str(machine.get("name", "")).strip(): machine
        for machine in machines
        if str(machine.get("name", "")).strip()
    }

    if request.method == "POST":
        service_type = request.form.get("service_type", "")
        machine      = request.form.get("machine", "").strip()
        load_type    = normalize_booking_load_type(request.form.get("load_type", ""))
        delivery_option = (request.form.get("delivery_option", "Pickup") or "Pickup").strip().title()
        full_name    = request.form.get("full_name", "").strip()
        phone        = request.form.get("phone", "").strip()
        address      = request.form.get("address", "").strip()
        pickup_date  = request.form.get("pickup_date", "")
        pickup_time  = request.form.get("pickup_time", "")
        notes        = request.form.get("notes", "").strip()
        selected_machine_status = request.form.get("selected_machine_status", "").strip()
        payment_method = normalize_payment_method(request.form.get("payment_method", "Cash on Delivery"))
        reference_number = request.form.get("reference_number", "").strip()
        payment_proof = ""

        try:
            weight = float(request.form.get("weight", 0))
        except ValueError:
            weight = 0

        errors = []
        if not full_name:                errors.append("Full name is required.")
        if not phone:                    errors.append("Phone number is required.")
        if not address:                  errors.append("Address is required.")
        if service_type not in SERVICES: errors.append("Invalid service selected.")
        if not machine:                  errors.append("Please select a machine.")
        if not load_type:                errors.append("Load type is required.")
        if not pickup_date:              errors.append("Pickup date is required.")
        if not pickup_time:              errors.append("Pickup time is required.")
        if weight <= 0:                  errors.append("Weight must be greater than 0.")
        if delivery_option not in {"Pickup", "Delivery"}:
            errors.append("Invalid delivery option selected.")
        if payment_method not in VALID_PAYMENT_METHODS:
            errors.append("Invalid payment method selected.")
        if payment_method in DIGITAL_PAYMENT_METHODS and not reference_number:
            errors.append(f"{payment_method} reference number is required.")

        try:
            payment_proof = encode_payment_proof_upload(
                request.files.get("payment_proof") or request.files.get("proof_image")
            )
        except ValueError as exc:
            errors.append(str(exc))

        selected_machine = machines_by_name.get(machine)
        if machine and not selected_machine:
            errors.append("Selected machine is no longer available. Please choose another machine.")
        elif selected_machine and selected_machine.get("status_display") == "Disabled":
            errors.append("This machine is currently disabled and cannot accept bookings.")
        elif selected_machine and selected_machine.get("status") != "Available":
            errors.append("This machine is currently in use. Please select an available machine.")
        elif selected_machine and load_type and normalize_booking_load_type(selected_machine.get("load_type", "")) != load_type:
            errors.append("Selected machine does not match the chosen load type. Please choose another machine.")
        elif selected_machine_status and selected_machine_status not in {"Available", "Disabled", "In Use"}:
            errors.append("Invalid machine status supplied.")

        if selected_machine and not load_type:
            load_type = normalize_booking_load_type(selected_machine.get("load_type", ""))

        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("booking.html", **booking_template_context(user, request.form, machines))

        payment_status = "Pending Verification" if payment_method in DIGITAL_PAYMENT_METHODS else "Pending Payment"
        delivery_type = delivery_option.strip().lower()
        delivery_fee = DEFAULT_DELIVERY_FEE if delivery_type == "delivery" else 0.0
        laundry_total = round(float(SERVICES.get(service_type, {}).get("price", 0) or 0) * weight, 2)
        total_amount = round(laundry_total + delivery_fee, 2)

        payload = {
            "user_id": user.get("id", ""),
            "full_name": full_name,
            "phone": phone,
            "pickup_address": address,
            "service_type": service_type,
            "machine": machine,
            "load_type": load_type,
            "pickup_date": pickup_date,
            "pickup_time": pickup_time,
            "weight": weight,
            "total_price": total_amount,
            "total_amount": total_amount,
            "delivery_fee": round(delivery_fee, 2),
            "delivery_type": delivery_type,
            "delivery_option": delivery_option,
            "notes": notes,
            "status": "Pending",
            "payment_method": payment_method,
            "reference_number": reference_number,
            "payment_proof": payment_proof,
            "payment_status": payment_status,
        }
        debug_payload = {**payload, "payment_proof": "[uploaded image]" if payment_proof else ""}
        print("DATA:", debug_payload)
        print("USER:", user)

        try:
            insert_booking_record(db(), payload)
            if selected_machine and selected_machine.get("machine_number") is not None:
                update_machine(
                    int(selected_machine["machine_number"]),
                    status="In Use",
                    enabled=selected_machine.get("enabled", True),
                    load_type=normalize_booking_load_type(selected_machine.get("load_type", load_type)),
                )
            try:
                send_booking_email(user.get("email", ""), payload)
            except Exception as email_exc:
                log_exception(
                    "booking confirmation email failed",
                    email_exc,
                    recipient=user.get("email", ""),
                    booking_payload={k: v for k, v in payload.items() if k != "payment_proof"},
                )
            flash("Booking confirmed! We'll pick up your laundry soon.", "success")
            return redirect(url_for("home", _anchor="my-booking"))
        except Exception as exc:
            log_exception("booking insert failed", exc, payload=payload, user=user.get("email", ""))
            flash(f"Booking failed: {str(exc)}", "error")

    return render_template("booking.html", **booking_template_context(user, {}, machines))


@app.route("/my-bookings")
@login_required
def my_bookings():
    user = session["user"]
    try:
        res = db().table("bookings").select("*") \
            .eq("user_id", user["id"]) \
            .order("created_at", desc=True).execute()
        bookings = res.data or []
        for b in bookings:
            price = SERVICES.get(b.get("service_type", ""), {}).get("price", 0)
            b["total_price"] = round(price * float(b.get("weight", 0) or 0), 2)
    except Exception as exc:
        log_exception("my bookings fetch failed", exc, user=user.get("email", ""))
        flash(f"Could not load bookings: {str(exc)}", "error")
        bookings = []
    return render_template("my_bookings.html", bookings=bookings or [], user=user)


@app.route("/bookings/<booking_id>")
@login_required
def booking_detail(booking_id):
    user = session["user"]
    client = db()
    if not client:
        return jsonify({"ok": False, "error": "Database unavailable."}), 503
    try:
        res = client.table("bookings").select("*").eq("id", booking_id).eq("user_id", user["id"]).limit(1).execute()
        rows = res.data or []
        if not rows:
            return jsonify({"ok": False, "error": "Booking not found."}), 404
        b = rows[0]
        price = SERVICES.get(b.get("service_type", ""), {}).get("price", 0)
        b["total_price"] = round(price * float(b.get("weight", 0) or 0), 2)
        return jsonify({"ok": True, "booking": b})
    except Exception as exc:
        log_exception("booking detail fetch failed", exc, booking_id=booking_id)
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/bookings/<booking_id>/cancel", methods=["POST"])
@login_required
def booking_cancel(booking_id):
    user = session["user"]
    client = db()
    if not client:
        return jsonify({"ok": False, "error": "Database unavailable."}), 503
    try:
        res = client.table("bookings").select("id,status,user_id").eq("id", booking_id).eq("user_id", user["id"]).limit(1).execute()
        rows = res.data or []
        if not rows:
            return jsonify({"ok": False, "error": "Booking not found."}), 404
        current_status = rows[0].get("status", "")
        if current_status == "Cancelled":
            return jsonify({"ok": False, "error": "Booking is already cancelled."}), 400
        if current_status == "Completed":
            return jsonify({"ok": False, "error": "Completed bookings cannot be cancelled."}), 400
        client.table("bookings").update({"status": "Cancelled"}).eq("id", booking_id).eq("user_id", user["id"]).execute()
        return jsonify({"ok": True, "message": "Booking cancelled successfully."})
    except Exception as exc:
        log_exception("booking cancel failed", exc, booking_id=booking_id)
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/bookings/<booking_id>/messages", methods=["GET"])
@login_required
def booking_messages_list(booking_id):
    user = session["user"]
    client = db()
    if not client:
        return jsonify({"ok": False, "error": "Database unavailable."}), 503
    try:
        booking_res = (
            client.table("bookings")
            .select("id,user_id")
            .eq("id", booking_id)
            .eq("user_id", user["id"])
            .limit(1)
            .execute()
        )
        if not (booking_res.data or []):
            return jsonify({"ok": False, "error": "Booking not found."}), 404

        msg_res = (
            client.table("messages")
            .select("id,booking_id,sender,message,created_at")
            .eq("booking_id", booking_id)
            .order("created_at", desc=False)
            .execute()
        )
        return jsonify({"ok": True, "messages": msg_res.data or []})
    except Exception as exc:
        log_exception("booking messages list failed", exc, booking_id=booking_id, user=user.get("email", ""))
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/bookings/<booking_id>/messages", methods=["POST"])
@login_required
def booking_messages_send(booking_id):
    user = session["user"]
    client = db()
    if not client:
        return jsonify({"ok": False, "error": "Database unavailable."}), 503
    try:
        booking_res = (
            client.table("bookings")
            .select("id,user_id")
            .eq("id", booking_id)
            .eq("user_id", user["id"])
            .limit(1)
            .execute()
        )
        if not (booking_res.data or []):
            return jsonify({"ok": False, "error": "Booking not found."}), 404

        payload = request.get_json(silent=True) or {}
        message_text = str(payload.get("message", "") or "").strip()
        if not message_text:
            return jsonify({"ok": False, "error": "Message is required."}), 400
        if len(message_text) > 1000:
            return jsonify({"ok": False, "error": "Message is too long."}), 400

        insert_payload = {
            "booking_id": booking_id,
            "sender": "user",
            "message": message_text,
        }
        insert_res = client.table("messages").insert(insert_payload).execute()
        inserted = (insert_res.data or [{}])[0]
        return jsonify({"ok": True, "message": inserted})
    except Exception as exc:
        log_exception("booking messages send failed", exc, booking_id=booking_id, user=user.get("email", ""))
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/")
def home():
    user = session.get("user")
    if user and user.get("is_admin"):
        return redirect(url_for("admin_dashboard"))
    active_auth_modal, auth_form_data = pop_auth_modal_state()
    recent = []
    bookings = []
    try:
        machines = admin_dashboard_machines()
    except Exception as exc:
        log_exception("homepage machines fetch failed", exc)
        machines = []
    if user:
        try:
            res = db().table("bookings").select("*") \
                .eq("user_id", user["id"]) \
                .order("created_at", desc=True) \
                .limit(3).execute()
            recent = res.data or []
        except Exception as exc:
            log_exception("recent bookings fetch failed", exc, user=user.get("email", ""))
            recent = []
        try:
            bookings_res = db().table("bookings").select("*") \
                .eq("user_id", user["id"]) \
                .order("created_at", desc=True).execute()
            bookings = bookings_res.data or []
            for booking in bookings:
                price = SERVICES.get(booking.get("service_type", ""), {}).get("price", 0)
                booking["total_price"] = round(price * float(booking.get("weight", 0) or 0), 2)
        except Exception as exc:
            log_exception("homepage bookings fetch failed", exc, user=user.get("email", ""))
            bookings = []
    return render_template(
        "readers_view.html",
        user=user,
        recent=recent or [],
        bookings=bookings or [],
        machines=machines or [],
        machine_type_cards=build_home_machine_types(machines or []) if user else [],
        services=SERVICES,
        homepage_services=HOMEPAGE_SERVICES,
        active_auth_modal=active_auth_modal,
        auth_form_data=auth_form_data,
    )


@app.route("/readers-view")
def readers_view():
    return redirect(url_for("home"))


@app.route("/profile/update", methods=["POST"])
@login_required
def profile_update():
    user = session["user"]
    is_json_request = request.is_json
    data = request.get_json(silent=True) or {}
    name = (request.form.get("name") if not is_json_request else data.get("name", "") or "").strip()
    phone = (request.form.get("phone") if not is_json_request else data.get("phone", "") or "").strip()
    address = (request.form.get("address") if not is_json_request else data.get("address", "") or "").strip()
    avatar = (data.get("avatar", "") if is_json_request else "").strip()
    uploaded = request.files.get("avatar")

    if not name:
        return jsonify({"ok": False, "error": "Name is required"}), 400

    try:
        update_data = {"full_name": name, "phone": phone, "address": address}
        if uploaded and uploaded.filename:
            if not (uploaded.mimetype or "").startswith("image/"):
                return jsonify({"ok": False, "error": "Only image uploads are allowed."}), 400
            image_bytes = uploaded.read()
            if not image_bytes:
                return jsonify({"ok": False, "error": "The selected image is empty."}), 400
            if len(image_bytes) > 2 * 1024 * 1024:
                return jsonify({"ok": False, "error": "Profile photo must be 2MB or smaller."}), 400
            try:
                avatar = upload_admin_avatar_to_storage(user["id"], image_bytes, uploaded.mimetype)
            except Exception as storage_exc:
                return jsonify({"ok": False, "error": f"Avatar upload failed: {storage_exc}"}), 500

        if avatar and (avatar.startswith("http://") or avatar.startswith("https://") or avatar.startswith("data:image")):
            update_data["avatar"] = avatar

        if local_auth_enabled():
            update_local_user(user["id"], name, phone, address, update_data.get("avatar", user.get("avatar", "")))
        else:
            try:
                execute_update_with_fallback(
                    "profiles",
                    profile_payload_variants({"id": user["id"], **update_data}),
                    "id",
                    user["id"],
                    clients=[("authenticated session", db())],
                )
            except Exception as db_exc:
                if "missing avatar" in str(db_exc).lower() or "column" in str(db_exc).lower():
                    raise ValueError(
                        "Database update failed. Ensure 'profiles.avatar' column exists and is type text."
                    ) from db_exc
                raise
        session["user"] = {
            **user,
            "name": name,
            "phone": phone,
            "address": address,
            "avatar": update_data.get("avatar", user.get("avatar", ""))
        }
        persist_session_user(session["user"])
        return jsonify({"ok": True, "avatar": session["user"].get("avatar", "")})
    except Exception as e:
        if is_supabase_connection_error(e):
            try:
                local_user, _ = find_local_user(user.get("email", ""))
                if local_user:
                    update_local_user(
                        local_user["id"],
                        name,
                        phone,
                        address,
                        update_data.get("avatar", user.get("avatar", "")),
                    )
                session["user"] = {
                    **user,
                    "name": name,
                    "phone": phone,
                    "address": address,
                    "avatar": update_data.get("avatar", user.get("avatar", "")),
                }
                persist_session_user(session["user"])
                return jsonify({
                    "ok": True,
                    "avatar": session["user"].get("avatar", ""),
                    "warning": "FreshWash updated your current session, but the remote profile service is unavailable right now."
                })
            except Exception:
                pass
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    user = session["user"]

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        phone     = request.form.get("phone", "").strip()
        address   = request.form.get("address", "").strip()

        if not full_name:
            flash("Full name is required.", "error")
            return render_template("profile.html", user=user)

        try:
            if local_auth_enabled():
                update_local_user(user["id"], full_name, phone, address, user.get("avatar", ""))
            else:
                execute_update_with_fallback(
                    "profiles",
                    profile_payload_variants({
                        "id": user["id"],
                        "full_name": full_name,
                        "phone": phone,
                        "address": address,
                    }),
                    "id",
                    user["id"],
                    clients=[("authenticated session", db())],
                )

            session["user"] = {**user, "name": full_name, "phone": phone, "address": address}
            flash("Profile updated successfully!", "success")
            return redirect(url_for("profile"))
        except Exception as e:
            flash(f"Update failed: {str(e)}", "error")

    return render_template("profile.html", user=user)


if __name__ == "__main__":
    init_local_auth_db()
    app.run(debug=True)



