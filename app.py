from flask import Flask, render_template, request, redirect, url_for, session, flash
from supabase_client import supabase, get_authed_client
from dotenv import load_dotenv
from functools import wraps
import os

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "freshwash-secret-key-2024")

SERVICES = {
    "Wash & Fold":  {"price": 150, "desc": "Clean and neatly folded laundry delivered to your door."},
    "Wash & Iron":  {"price": 200, "desc": "Washed and professionally ironed for a crisp finish."},
    "Dry Cleaning": {"price": 250, "desc": "Gentle dry cleaning for delicate and special garments."},
    "Premium Wash": {"price": 350, "desc": "Premium treatment with fabric softener and extra care."},
}


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            flash("Please log in to continue.", "error")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def db():
    """Return an RLS-authenticated Supabase client for the current user."""
    return get_authed_client(session.get("access_token", ""))


# ── Auth ──────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return redirect(url_for("readers_view"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name     = request.form.get("name", "").strip()
        email    = request.form.get("email", "").strip()
        phone    = request.form.get("phone", "").strip()
        address  = request.form.get("address", "").strip()
        password = request.form.get("password", "").strip()

        if not name or not email or not phone or not address or not password:
            flash("All fields are required.", "error")
            return render_template("register.html")

        if len(password) < 6:
            flash("Password must be at least 6 characters.", "error")
            return render_template("register.html")

        try:
            # Step 1: Create auth user
            res = supabase.auth.sign_up({
                "email": email,
                "password": password,
                "options": {"data": {"full_name": name}}
            })

            if not res.user:
                flash("Registration failed. Try again.", "error")
                return render_template("register.html")

            # Step 2: Save profile with phone and address
            authed = get_authed_client(res.session.access_token) if res.session else supabase
            authed.table("profiles").insert({
                "id":        res.user.id,
                "full_name": name,
                "phone":     phone,
                "address":   address
            }).execute()

            flash("Account created! Please log in.", "success")
            return redirect(url_for("login"))

        except Exception as e:
            flash(f"Registration error: {str(e)}", "error")

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email    = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()

        if not email or not password:
            flash("Email and password are required.", "error")
            return render_template("login.html")

        try:
            res = supabase.auth.sign_in_with_password({"email": email, "password": password})

            if not res.user or not res.session:
                flash("Invalid credentials.", "error")
                return render_template("login.html")

            access_token = res.session.access_token
            authed = get_authed_client(access_token)

            # Load profile from profiles table
            profile_res = authed.table("profiles").select("*").eq("id", res.user.id).single().execute()
            profile = profile_res.data or {}

            session["user"] = {
                "id":      res.user.id,
                "email":   res.user.email,
                "name":    profile.get("full_name") or res.user.user_metadata.get("full_name", email.split("@")[0]),
                "phone":   profile.get("phone", ""),
                "address": profile.get("address", ""),
                "avatar":  profile.get("avatar", "")
            }
            session["access_token"] = access_token

            flash(f"Welcome back, {session['user']['name']}!", "success")
            return redirect(url_for("readers_view"))

        except Exception as e:
            flash(f"Login failed: {str(e)}", "error")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("readers_view"))


# ── Pages ─────────────────────────────────────────────────────────────────────

@app.route("/dashboard")
@login_required
def dashboard():
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


@app.route("/services")
@login_required
def services():
    return render_template("services.html", services=SERVICES, user=session["user"])


@app.route("/booking", methods=["GET", "POST"])
@login_required
def booking():
    user = session["user"]

    if request.method == "POST":
        service_type = request.form.get("service_type", "")
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
            return render_template("booking.html", services=SERVICES, user=user, form=request.form)

        try:
            db().table("bookings").insert({
                "user_id":      user["id"],
                "full_name":    full_name,
                "phone":        phone,
                "address":      address,
                "service_type": service_type,
                "pickup_date":  pickup_date,
                "pickup_time":  pickup_time,
                "weight":       weight,
                "notes":        notes,
                "status":       "Pending"
            }).execute()
            flash("Booking confirmed! We'll pick up your laundry soon. 🎉", "success")
            return redirect(url_for("readers_view", _anchor="my-booking"))
        except Exception as e:
            flash(f"Booking failed: {str(e)}", "error")

    return render_template("booking.html", services=SERVICES, user=user, form={})


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
    return render_template("readers_spa.html", user=user, recent=recent, bookings=bookings, services=SERVICES)


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
        db().table("profiles").update(update_data).eq("id", user["id"]).execute()
        session["user"] = {**user, "name": name, "phone": phone, "address": address, "avatar": avatar}
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
    app.run(debug=True)
