from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from supabase_client import (
    supabase,
    get_authed_client,
    get_service_client,
    is_supabase_enabled,
    is_supabase_service_role_enabled,
)
from dotenv import load_dotenv
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import uuid
import re
import os
import json
from collections import Counter
from datetime import datetime
from itertools import product

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "freshwash-secret-key-2024")
os.makedirs(app.instance_path, exist_ok=True)
LOCAL_AUTH_DB = os.path.join(app.instance_path, "freshwash_auth.db")
LOCAL_USERS_JSON = os.path.join(app.instance_path, "freshwash_users.json")

SERVICES = {
    "Wash & Fold":  {"price": 150, "desc": "Clean and neatly folded laundry delivered to your door."},
    "Wash & Iron":  {"price": 200, "desc": "Washed and professionally ironed for a crisp finish."},
    "Dry Cleaning": {"price": 250, "desc": "Gentle dry cleaning for delicate and special garments."},
    "Premium Wash": {"price": 350, "desc": "Premium treatment with fabric softener and extra care."},
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
        "label": f"Machine {number}",
        "status": "Available" if number % 3 else "In Use",
        "load_type": "Light" if number in {1, 4, 8} else ("Medium" if number in {2, 5, 7} else "Heavy"),
        "enabled": 1,
    }
    for number in range(1, 9)
]

EMAIL_RE = re.compile(r"^[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}$", re.IGNORECASE)


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
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        columns = {row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
        if "role" not in columns:
            conn.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user'")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS admin_machines (
                machine_number INTEGER PRIMARY KEY,
                label TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Available',
                load_type TEXT NOT NULL DEFAULT 'Medium',
                enabled INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        machine_columns = {row[1] for row in conn.execute("PRAGMA table_info(admin_machines)").fetchall()}
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
                INSERT OR IGNORE INTO admin_machines (machine_number, label, status, load_type, enabled)
                VALUES (?, ?, ?, ?, ?)
                """,
                (machine["machine_number"], machine["label"], machine["status"], machine["load_type"], machine["enabled"])
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
        _init_local_auth_db()


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


def configured_admin_emails():
    raw = os.environ.get("ADMIN_EMAILS", "admin@freshwash.com")
    return {normalize_email(email) for email in raw.split(",") if email.strip()}


def is_valid_email(email):
    return bool(EMAIL_RE.match(normalize_email(email)))


def auth_template_context(form_data=None):
    return {"form_data": form_data or {}}


def render_auth_template(template_name, form_data=None):
    return render_template(template_name, **auth_template_context(form_data))


def set_auth_modal_state(modal, form_data=None):
    session["auth_modal"] = modal
    session["auth_form_data"] = form_data or {}


def pop_auth_modal_state():
    return session.pop("auth_modal", None), session.pop("auth_form_data", {})


def redirect_to_auth_modal(modal, form_data=None):
    set_auth_modal_state(modal, form_data)
    return redirect(url_for("readers_view"))


def user_role_for_email(email, stored_role="user", metadata=None):
    metadata = metadata or {}
    if stored_role == "admin" or metadata.get("role") == "admin" or metadata.get("is_admin"):
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


def load_local_users():
    if not os.path.exists(LOCAL_USERS_JSON):
        return []
    try:
        with open(LOCAL_USERS_JSON, "r", encoding="utf-8") as handle:
            users = json.load(handle)
            return users if isinstance(users, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def save_local_users(users):
    with open(LOCAL_USERS_JSON, "w", encoding="utf-8") as handle:
        json.dump(users, handle, indent=2)


def find_local_user(email):
    email = normalize_email(email)
    users = load_local_users()
    for user in users:
        if normalize_email(user.get("email", "")) == email:
            return user, users
    return None, users


def create_local_user(name, email, phone, address, password, role_override=None):
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
        "is_admin": role == "admin"
    }


def local_user_exists(email):
    existing, _ = find_local_user(email)
    return bool(existing)


def upsert_local_user(name, email, phone, address, password, role_override=None):
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


def admin_update_local_user(user_id, name, email, role_override=None):
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
            user["role"] = role
            break
    save_local_users(users)


def admin_delete_local_user(user_id):
    users = [user for user in load_local_users() if user.get("id") != user_id]
    save_local_users(users)


def admin_create_supabase_user(name, email, phone, address, password, role):
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
    client.table("profiles").upsert({
        "id": auth_user.id,
        "full_name": name,
        "email": email,
        "phone": phone,
        "address": address,
        "role": role,
    }).execute()
    return auth_user


def admin_update_supabase_user(user_id, name, phone, address, role):
    role = normalize_profile_role(role)
    client = get_service_client()
    profile = client.table("profiles").select("*").eq("id", user_id).single().execute().data
    if not profile:
        raise ValueError("User profile not found.")
    client.table("profiles").update({
        "full_name": name,
        "phone": phone,
        "address": address,
        "role": role,
    }).eq("id", user_id).execute()
    try:
        client.auth.admin.update_user_by_id(user_id, {
            "user_metadata": {
                "full_name": name,
                "phone": phone,
                "address": address,
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
    if not address:
        errors.append("Address is required.")
    if not password:
        errors.append("Password is required.")
    elif len(password) < 6:
        errors.append("Password must be at least 6 characters.")
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
        if "user" not in session:
            flash("Please log in to continue.", "error")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            flash("Please log in to continue.", "error")
            return redirect(url_for("login"))
        if not session["user"].get("is_admin"):
            flash("Admin access only.", "error")
            return redirect(url_for("readers_view"))
        return f(*args, **kwargs)
    return decorated


def db():
    """Return an RLS-authenticated Supabase client for the current user."""
    return get_authed_client(session.get("access_token", ""))


def extract_schema_cache_missing_column(error, table_name):
    message = str(error)
    pattern = rf"Could not find the '([^']+)' column of '{re.escape(table_name)}' in the schema cache"
    match = re.search(pattern, message, re.IGNORECASE)
    return match.group(1) if match else None


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

    variants = []
    seen = set()
    for address_variant, optional_variant in product(address_variants, optional_variants):
        variant = {**base_payload, **address_variant, **optional_variant}
        key = tuple(sorted(variant.keys()))
        if key in seen:
            continue
        seen.add(key)
        variants.append(variant)
    return variants


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
        "role": role,
    }

    try:
        existing = authed_client.table("profiles").select("*").eq("id", auth_user.id).single().execute()
        if existing.data:
            merged_profile = {**profile_payload, **existing.data}
            if merged_profile.get("email") != auth_user.email:
                authed_client.table("profiles").update({"email": auth_user.email}).eq("id", auth_user.id).execute()
                merged_profile["email"] = auth_user.email
            if not merged_profile.get("role"):
                merged_profile["role"] = role
            return merged_profile
    except Exception:
        pass

    authed_client.table("profiles").upsert(profile_payload).execute()
    return profile_payload


def ensure_supabase_profile_record(auth_user, defaults=None, access_token=""):
    defaults = defaults or {}
    clients = []
    if is_supabase_service_role_enabled():
        clients.append(("service role", get_service_client()))
    if access_token and access_token.strip():
        clients.append(("authenticated session", get_authed_client(access_token)))

    if not clients:
        raise RuntimeError(
            "Supabase signup succeeded, but FreshWash could not save the profile row. "
            "Add SUPABASE_SERVICE_ROLE_KEY to the environment or disable email confirmation so signup returns a session."
        )

    errors = []
    for label, client in clients:
        try:
            return ensure_profile_record(client, auth_user, defaults)
        except Exception as exc:
            errors.append(f"{label}: {exc}")

    raise RuntimeError(
        "Supabase signup succeeded, but FreshWash could not save the profile row. "
        + " / ".join(errors)
    )


def fetch_supabase_profile_or_error(auth_user, access_token):
    if not access_token or not access_token.strip():
        raise RuntimeError("Login succeeded, but FreshWash could not open your authenticated session.")

    authed = get_authed_client(access_token)
    try:
        result = authed.table("profiles").select("*").eq("id", auth_user.id).single().execute()
    except Exception as exc:
        raise RuntimeError(f"Login succeeded, but FreshWash could not load your profile: {exc}")

    profile = result.data or {}
    if not profile:
        raise RuntimeError("Login succeeded, but your profile is missing. Please contact FreshWash support.")

    profile["role"] = normalize_profile_role(profile.get("role"))
    return profile


def build_session_user(auth_user, profile):
    metadata = auth_user.user_metadata or {}
    role = normalize_profile_role(profile.get("role"))
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


def persist_session_user(user, access_token=""):
    role = user_role_for_email(user.get("email", ""), user.get("role", "user"), user)
    user["role"] = role
    user["is_admin"] = role == "admin"
    session["user"] = user
    session["access_token"] = access_token


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
            for index, booking in enumerate(bookings):
                booking["machine"] = booking.get("machine") or f"Machine {(index % 8) + 1}"
                booking["load_type"] = booking.get("load_type") or "Medium Load"
                price = SERVICES.get(booking.get("service_type", ""), {}).get("price", 0)
                booking["total_price"] = round(price * float(booking.get("weight", 0) or 0), 2)
            return bookings
        except Exception:
            pass

    sample_services = list(ADMIN_SERVICE_DEFAULTS.keys())
    users = admin_dashboard_users()
    names = [user["name"] for user in users] or ["FreshWash Customer"]
    return [
        {
            "id": f"sample-{index}",
            "full_name": names[index % len(names)],
            "service_type": sample_services[index % len(sample_services)],
            "pickup_date": f"2026-04-{10 + index:02d}",
            "pickup_time": "10:00",
            "machine": f"Machine {((index + 1) % 8) + 1}",
            "load_type": ["Light Load", "Medium Load", "Heavy Load"][index % 3],
            "status": ["Pending", "In Progress", "Completed", "Cancelled"][index % 4],
            "total_price": round(249 * (index + 1), 2),
        }
        for index in range(1, 7)
    ]


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

    def normalize_machine(row):
        machine_number = row.get("machine_number")
        name = row.get("label") or row.get("name") or f"Machine {machine_number}"
        enabled = bool(row.get("enabled", True))
        effective_enabled = enabled and machines_globally_enabled
        status = row.get("status", "Available")
        load_type = row.get("load_type", "Medium")
        if load_type not in allowed_load_types and allowed_load_types:
            load_type = allowed_load_types[min(1, len(allowed_load_types) - 1)]
        status_display = status if effective_enabled else "Disabled"
        return {
            "machine_number": machine_number,
            "name": name,
            "status": status,
            "status_display": status_display,
            "load_type": load_type,
            "enabled": enabled,
            "effective_enabled": effective_enabled,
            "button_label": "Book Now" if effective_enabled and status == "Available" else ("Select Anyway" if effective_enabled and status == "In Use" else "Unavailable"),
            "button_disabled": (not effective_enabled) or status not in {"Available", "In Use"},
        }

    client = admin_db_client()
    if client:
        try:
            rows = client.table("machines").select("*").order("machine_number").execute().data or []
            if rows:
                return [normalize_machine(row) for row in rows]
        except Exception:
            pass

    try:
        with local_auth_conn() as conn:
            rows = conn.execute(
                """
                SELECT machine_number, label, status, load_type, enabled
                FROM admin_machines
                ORDER BY machine_number
                """
            ).fetchall()
        return [
            normalize_machine(
                {
                    "machine_number": row["machine_number"],
                    "label": row["label"],
                    "status": row["status"],
                    "load_type": row["load_type"],
                    "enabled": row["enabled"],
                }
            )
            for row in rows
        ]
    except sqlite3.OperationalError:
        return [normalize_machine(row) for row in DEFAULT_MACHINE_ROWS]


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
            "label": f"Machine {machine_number}",
            "status": "Available",
            "load_type": "Medium",
            "enabled": 1,
        },
    )
    machine_name = (name if name is not None else (current_machine or {}).get("name", base_machine["label"])).strip()
    machine_status = status if status is not None else (current_machine or {}).get("status", base_machine["status"])
    machine_load_type = load_type if load_type is not None else (current_machine or {}).get("load_type", base_machine["load_type"])
    machine_enabled = bool(enabled) if enabled is not None else bool((current_machine or {}).get("enabled", base_machine["enabled"]))
    client = admin_db_client()
    if client:
        payload = {
            "machine_number": machine_number,
            "label": machine_name,
            "name": machine_name,
            "status": machine_status,
            "load_type": machine_load_type,
            "enabled": machine_enabled,
            "updated_at": datetime.utcnow().isoformat(),
        }
        try:
            client.table("machines").upsert(payload, on_conflict="machine_number").execute()
        except Exception:
            pass

    fields = []
    values = []
    if name is not None:
        fields.append("label = ?")
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
                INSERT INTO admin_machines (machine_number, label, status, load_type, enabled)
                VALUES (?, ?, ?, ?, ?)
                """,
                (machine_number, machine_name, machine_status, machine_load_type, 1 if machine_enabled else 0),
            )


def update_service(name, price, description):
    client = admin_db_client()
    if client:
        try:
            client.table("services").upsert(
                {"name": name, "price": price, "description": description},
                on_conflict="name"
            ).execute()
        except Exception:
            pass

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


def update_admin_profile_settings(user_id, name, email, password=""):
    normalized_email = normalize_email(email)
    if local_auth_enabled():
        users = load_local_users()
        for user in users:
            if user.get("id") != user_id and normalize_email(user.get("email", "")) == normalized_email:
                raise ValueError("Another user already uses that email.")
        for user in users:
            if user.get("id") == user_id:
                user["full_name"] = name
                user["email"] = normalized_email
                if password:
                    user["password_hash"] = generate_password_hash(password)
                break
        save_local_users(users)
        return

    profile_update = {"full_name": name, "email": normalized_email}
    access_token = session.get("access_token", "")
    try:
        if is_supabase_service_role_enabled():
            client = get_service_client()
            client.table("profiles").update(profile_update).eq("id", user_id).execute()
            auth_payload = {
                "email": normalized_email,
                "user_metadata": {
                    "full_name": name,
                    "phone": session["user"].get("phone", ""),
                    "address": session["user"].get("address", ""),
                    "role": session["user"].get("role", "admin"),
                }
            }
            if password:
                auth_payload["password"] = password
            client.auth.admin.update_user_by_id(user_id, auth_payload)
            return
        authed = get_authed_client(access_token)
        authed.table("profiles").update(profile_update).eq("id", user_id).execute()
        auth_payload = {"email": normalized_email, "data": {"full_name": name}}
        if password:
            auth_payload["password"] = password
        authed.auth.update_user(auth_payload)
    except Exception as exc:
        raise ValueError(f"Could not update admin profile: {exc}")


def build_admin_reports(bookings, machines):
    per_day_counter = Counter((booking.get("pickup_date") or booking.get("date") or "Unscheduled") for booking in bookings)
    service_counter = Counter(booking.get("service_type", "Unknown") for booking in bookings)
    machine_counter = Counter(booking.get("machine", "Unassigned") for booking in bookings)
    status_counter = Counter((booking.get("status") or "Pending") for booking in bookings)

    return {
        "bookings_per_day": [{"label": day, "count": count} for day, count in sorted(per_day_counter.items())[:7]],
        "most_used_service": service_counter.most_common(1)[0][0] if service_counter else "No data yet",
        "machine_usage": [
            {
                "label": machine["name"],
                "count": machine_counter.get(machine["name"], 0),
                "status": machine["status"],
            }
            for machine in machines
        ],
        "status_breakdown": {
            "pending": status_counter.get("Pending", 0),
            "completed": status_counter.get("Completed", 0),
            "cancelled": status_counter.get("Cancelled", 0),
        },
    }


def build_admin_dashboard_payload():
    users = admin_dashboard_users()
    bookings = admin_dashboard_bookings()
    machines = admin_dashboard_machines()
    services = admin_dashboard_services()
    settings = get_admin_settings()
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
        "machines": machines,
        "services": services,
        "reports": reports,
        "settings": settings,
    }


def render_admin_dashboard_view(section="dashboard"):
    return render_template(
        "admin_dashboard.html",
        user=session["user"],
        admin_data=build_admin_dashboard_payload(),
        initial_section=section,
    )


# ── Auth ──────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return redirect(url_for("readers_view"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if "user" in session:
        return redirect(url_for("admin_dashboard" if session["user"].get("is_admin") else "readers_view"))

    if request.method == "GET":
        return redirect_to_auth_modal("register")

    if request.method == "POST":
        name     = request.form.get("name", "").strip()
        email    = normalize_email(request.form.get("email", ""))
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

        try:
            if local_auth_enabled():
                create_local_user(name, email, phone, address, password, role_override=resolve_registration_role(email))
                flash("Account created successfully. Please log in.", "success")
            else:
                role = resolve_registration_role(email)

                res = supabase.auth.sign_up({
                    "email": email,
                    "password": password,
                    "options": {
                        "data": {
                            "full_name": name,
                            "phone": phone,
                            "address": address,
                            "role": role,
                        }
                    }
                })

                if not res.user:
                    raise RuntimeError("Supabase signup failed. Please try again.")

                ensure_supabase_profile_record(
                    res.user,
                    {
                        "full_name": name,
                        "email": email,
                        "phone": phone,
                        "address": address,
                        "role": role,
                    },
                    access_token=res.session.access_token if res.session else "",
                )

                upsert_local_user(name, email, phone, address, password)
                flash("Account created successfully. Please log in.", "success")
            return redirect_to_auth_modal("login", {"email": email})

        except ValueError as e:
            flash(str(e), "error")
        except Exception as e:
            message = str(e)
            if is_supabase_enabled() and is_supabase_connection_error(e):
                try:
                    create_local_user(name, email, phone, address, password)
                    flash("Account created successfully. Please log in.", "success")
                    flash("Supabase is currently unavailable, so FreshWash saved your account locally for now.", "success")
                    return redirect_to_auth_modal("login", {"email": email})
                except ValueError as local_error:
                    flash(str(local_error), "error")
            elif any(phrase in message.lower() for phrase in (
                "already registered",
                "already exists",
                "user already registered",
                "duplicate",
            )):
                flash("Account already exists, please login.", "error")
            elif "could not save the profile row" in message.lower():
                flash(message, "error")
            else:
                flash(f"Registration error: {message}", "error")

        return redirect_to_auth_modal("register", form_data)


@app.route("/login", methods=["GET", "POST"])
def login():
    if "user" in session:
        return redirect(url_for("admin_dashboard" if session["user"].get("is_admin") else "readers_view"))

    if request.method == "GET":
        return redirect_to_auth_modal("login")

    if request.method == "POST":
        email    = normalize_email(request.form.get("email", ""))
        password = request.form.get("password", "").strip()
        form_data = {"email": email}

        errors = validate_login_form(email, password)
        if errors:
            for error in errors:
                flash(error, "error")
            return redirect_to_auth_modal("login", form_data)

        try:
            if local_auth_enabled():
                user = authenticate_local_user(email, password)
                persist_session_user(user)
            else:
                try:
                    res = supabase.auth.sign_in_with_password({"email": email, "password": password})

                    if not res.user or not res.session:
                        flash("Invalid email or password.", "error")
                        return redirect_to_auth_modal("login", form_data)

                    access_token = res.session.access_token
                    profile = fetch_supabase_profile_or_error(res.user, access_token)
                    user = build_session_user(res.user, profile)
                    persist_session_user(user, access_token)

                    upsert_local_user(
                        user["name"],
                        user["email"],
                        user.get("phone", ""),
                        user.get("address", ""),
                        password,
                    )
                except Exception as auth_error:
                    if not is_supabase_connection_error(auth_error):
                        raise
                    user = authenticate_local_user(email, password)
                    persist_session_user(user)
                    flash("Signed in using locally saved account data because Supabase is currently unavailable.", "success")

            flash(f"Welcome back, {session['user']['name']}!", "success")
            return redirect(url_for("admin_dashboard" if session["user"].get("is_admin") else "readers_view"))

        except ValueError as e:
            flash(str(e), "error")
        except Exception as e:
            flash(f"Login failed: {str(e)}", "error")

        return redirect_to_auth_modal("login", form_data)


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect_to_auth_modal("login")


# ── Pages ─────────────────────────────────────────────────────────────────────

@app.route("/dashboard")
@login_required
def dashboard():
    if session["user"].get("is_admin"):
        return redirect(url_for("admin_dashboard"))
    user = session["user"]
    try:
        res = db().table("bookings").select("*") \
            .eq("user_id", user["id"]) \
            .order("created_at", desc=True) \
            .limit(3).execute()
        recent = res.data or []
    except Exception:
        recent = []
    return render_template("dashboard.html", user=user, recent=recent)


@app.route("/admin")
@app.route("/admin-dashboard")
@admin_required
def admin_dashboard():
    return render_admin_dashboard_view("dashboard")


@app.route("/admin-users")
@admin_required
def admin_users():
    return render_admin_dashboard_view("users")


@app.route("/admin-bookings")
@admin_required
def admin_bookings():
    return render_admin_dashboard_view("bookings")


@app.route("/admin-machines")
@admin_required
def admin_machines():
    return render_admin_dashboard_view("machines")


@app.route("/admin-services")
@admin_required
def admin_services():
    return render_admin_dashboard_view("services")


@app.route("/admin-reports")
@admin_required
def admin_reports():
    return render_admin_dashboard_view("reports")


@app.route("/admin-settings")
@admin_required
def admin_settings():
    return render_admin_dashboard_view("settings")


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
            phone = data.get("phone", "").strip()
            address = data.get("address", "").strip()
            role = normalize_profile_role(data.get("role", "user"))
            if not name:
                return jsonify({"ok": False, "error": "Name is required."}), 400
            if local_auth_enabled():
                email = normalize_email(data.get("email", ""))
                if not email:
                    return jsonify({"ok": False, "error": "Email is required."}), 400
                admin_update_local_user(user_id, name, email, role_override=role)
                existing_local_user = next((user for user in load_local_users() if user.get("id") == user_id), None)
                update_local_user(user_id, name, phone, address, (existing_local_user or {}).get("avatar", ""))
            else:
                if not is_supabase_service_role_enabled():
                    return jsonify({"ok": False, "error": "Editing Supabase users requires SUPABASE_SERVICE_ROLE_KEY."}), 400
                admin_update_supabase_user(user_id, name, phone, address, role)
            if session["user"]["id"] == user_id:
                session["user"]["name"] = name
                if local_auth_enabled():
                    session["user"]["email"] = normalize_email(data.get("email", ""))
                session["user"]["phone"] = phone
                session["user"]["address"] = address
                session["user"]["role"] = role
                persist_session_user(session["user"], session.get("access_token", ""))
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
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
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
            payload = {
                "full_name": data.get("full_name", "").strip(),
                "service_type": data.get("service_type", "").strip(),
                "machine": data.get("machine", "").strip(),
                "pickup_date": data.get("pickup_date", "").strip(),
                "pickup_time": data.get("pickup_time", "").strip(),
                "load_type": data.get("load_type", "").strip(),
                "notes": data.get("notes", "").strip(),
                "status": data.get("status", "").strip() or "Pending",
            }
            if payload["status"] not in {"Pending", "In Progress", "Completed", "Cancelled"}:
                return jsonify({"ok": False, "error": "Invalid status value."}), 400
            client.table("bookings").update(payload).eq("id", booking_id).execute()
        elif action == "cancel":
            client.table("bookings").update({"status": "Cancelled"}).eq("id", booking_id).execute()
        elif action == "delete":
            client.table("bookings").delete().eq("id", booking_id).execute()
        else:
            return jsonify({"ok": False, "error": "Unsupported booking action."}), 400
        return jsonify({"ok": True, "data": build_admin_dashboard_payload()})
    except Exception as exc:
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
    if status is not None and status not in {"Available", "In Use"}:
        return jsonify({"ok": False, "error": "Invalid machine status."}), 400
    if load_type is not None and load_type not in allowed_load_types:
        return jsonify({"ok": False, "error": "Invalid load type."}), 400
    update_machine(machine_number, name=name, status=status, enabled=enabled, load_type=load_type)
    return jsonify({"ok": True, "data": build_admin_dashboard_payload()})


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
            except Exception:
                pass
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
            except Exception:
                pass
        with local_auth_conn() as conn:
            conn.execute(
                "INSERT INTO admin_services (name, price, description) VALUES (?, ?, ?)",
                (service_name, price, description)
            )
    else:
        update_service(service_name, price, description)
    return jsonify({"ok": True, "data": build_admin_dashboard_payload()})


@app.route("/admin/api/settings", methods=["POST"])
@admin_required
def admin_settings_action():
    data = request.get_json() or {}
    action = data.get("action", "").strip()

    try:
        if action == "profile":
            name = data.get("name", "").strip()
            email = normalize_email(data.get("email", ""))
            password = data.get("password", "").strip()
            if not name:
                return jsonify({"ok": False, "error": "Admin name is required."}), 400
            if not email or not is_valid_email(email):
                return jsonify({"ok": False, "error": "Enter a valid admin email."}), 400
            if password and len(password) < 6:
                return jsonify({"ok": False, "error": "Password must be at least 6 characters."}), 400
            update_admin_profile_settings(session["user"]["id"], name, email, password)
            session["user"]["name"] = name
            session["user"]["email"] = email
            persist_session_user(session["user"], session.get("access_token", ""))
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
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Settings update failed: {exc}"}), 500


@app.route("/services")
@login_required
def services():
    return render_template("services_page.html", services=SERVICES, user=session["user"])


@app.route("/booking", methods=["GET", "POST"])
@login_required
def booking():
    user = session["user"]
    machines = [machine for machine in admin_dashboard_machines() if machine.get("effective_enabled", machine.get("enabled"))]

    if request.method == "POST":
        service_type = request.form.get("service_type", "")
        machine      = request.form.get("machine", "").strip()
        load_type    = request.form.get("load_type", "").strip()
        full_name    = request.form.get("full_name", "").strip()
        phone        = request.form.get("phone", "").strip()
        address      = request.form.get("address", "").strip()
        pickup_date  = request.form.get("pickup_date", "")
        pickup_time  = request.form.get("pickup_time", "")
        notes        = request.form.get("notes", "").strip()

        try:
            weight = float(request.form.get("weight", 0))
        except ValueError:
            weight = 0

        errors = []
        if not full_name:                errors.append("Full name is required.")
        if not phone:                    errors.append("Phone number is required.")
        if not address:                  errors.append("Address is required.")
        if service_type not in SERVICES: errors.append("Invalid service selected.")
        if not pickup_date:              errors.append("Pickup date is required.")
        if not pickup_time:              errors.append("Pickup time is required.")
        if weight <= 0:                  errors.append("Weight must be greater than 0.")

        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("booking.html", services=SERVICES, user=user, form=request.form, machines=machines)

        try:
            insert_booking_record(
                db(),
                {
                    "user_id": user["id"],
                    "full_name": full_name,
                    "phone": phone,
                    "pickup_address": address,
                    "service_type": service_type,
                    "machine": machine,
                    "load_type": load_type,
                    "pickup_date": pickup_date,
                    "pickup_time": pickup_time,
                    "weight": weight,
                    "notes": notes,
                    "status": "Pending",
                }
            )
            flash("Booking confirmed! We'll pick up your laundry soon. 🎉", "success")
            return redirect(url_for("readers_view", _anchor="my-booking"))
        except Exception as e:
            flash(f"Booking failed: {str(e)}", "error")

    return render_template("booking.html", services=SERVICES, user=user, form={}, machines=machines)


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
            price = SERVICES.get(b["service_type"], {}).get("price", 0)
            b["total_price"] = round(price * float(b.get("weight", 0)), 2)
    except Exception as e:
        flash(f"Could not load bookings: {str(e)}", "error")
        bookings = []
    return render_template("my_bookings.html", bookings=bookings, user=user)


@app.route("/readers-view")
def readers_view():
    user = session.get("user")
    if user and user.get("is_admin"):
        return redirect(url_for("admin_dashboard"))
    active_auth_modal, auth_form_data = pop_auth_modal_state()
    recent = []
    bookings = []
    if user:
        try:
            res = db().table("bookings").select("*") \
                .eq("user_id", user["id"]) \
                .order("created_at", desc=True) \
                .limit(3).execute()
            recent = res.data or []
        except Exception:
            recent = []
        try:
            bookings_res = db().table("bookings").select("*") \
                .eq("user_id", user["id"]) \
                .order("created_at", desc=True).execute()
            bookings = bookings_res.data or []
            for booking in bookings:
                price = SERVICES.get(booking["service_type"], {}).get("price", 0)
                booking["total_price"] = round(price * float(booking.get("weight", 0)), 2)
        except Exception:
            bookings = []
    return render_template(
        "readers_spa.html",
        user=user,
        recent=recent,
        bookings=bookings,
        machines=admin_dashboard_machines(),
        services=SERVICES,
        active_auth_modal=active_auth_modal,
        auth_form_data=auth_form_data,
    )


@app.route("/profile/update", methods=["POST"])
@login_required
def profile_update():
    import json
    user = session["user"]
    data = request.get_json()
    name    = data.get("name", "").strip()
    phone   = data.get("phone", "").strip()
    address = data.get("address", "").strip()
    avatar  = data.get("avatar", "")

    if not name:
        return json.dumps({"ok": False, "error": "Name is required"}), 400

    try:
        update_data = {"full_name": name, "phone": phone, "address": address}
        if avatar and avatar.startswith("data:image"):
            update_data["avatar"] = avatar
        if local_auth_enabled():
            update_local_user(user["id"], name, phone, address, update_data.get("avatar", user.get("avatar", "")))
        else:
            db().table("profiles").update(update_data).eq("id", user["id"]).execute()
        session["user"] = {
            **user,
            "name": name,
            "phone": phone,
            "address": address,
            "avatar": update_data.get("avatar", user.get("avatar", ""))
        }
        return json.dumps({"ok": True})
    except Exception as e:
        return json.dumps({"ok": False, "error": str(e)}), 500


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
                db().table("profiles").update({
                    "full_name": full_name,
                    "phone":     phone,
                    "address":   address
                }).eq("id", user["id"]).execute()

            session["user"] = {**user, "name": full_name, "phone": phone, "address": address}
            flash("Profile updated successfully!", "success")
            return redirect(url_for("profile"))
        except Exception as e:
            flash(f"Update failed: {str(e)}", "error")

    return render_template("profile.html", user=user)


if __name__ == "__main__":
    init_local_auth_db()
    app.run(debug=True)
