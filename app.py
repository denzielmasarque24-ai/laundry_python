from flask import Flask, render_template, request, redirect, url_for, session, flash
from supabase_client import supabase
from dotenv import load_dotenv
from functools import wraps
import os

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "freshwash-secret-key-2024")

SERVICES = {
    "Wash & Fold":    {"price": 150, "desc": "Clean and neatly folded laundry delivered to your door."},
    "Wash & Iron":    {"price": 200, "desc": "Washed and professionally ironed for a crisp finish."},
    "Dry Cleaning":   {"price": 250, "desc": "Gentle dry cleaning for delicate and special garments."},
    "Premium Wash":   {"price": 350, "desc": "Premium treatment with fabric softener and extra care."},
}

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            flash("Please log in to continue.", "error")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

@app.route("/")
def index():
    if "user" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email    = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()
        name     = request.form.get("name", "").strip()

        if not email or not password or not name:
            flash("All fields are required.", "error")
            return render_template("register.html")

        if len(password) < 6:
            flash("Password must be at least 6 characters.", "error")
            return render_template("register.html")

        try:
            res = supabase.auth.sign_up({
                "email": email,
                "password": password,
                "options": {"data": {"full_name": name}}
            })
            if res.user:
                flash("Account created! Please log in.", "success")
                return redirect(url_for("login"))
            flash("Registration failed. Try again.", "error")
        except Exception as e:
            flash(str(e), "error")

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
            if res.user:
                session["user"] = {
                    "id":    res.user.id,
                    "email": res.user.email,
                    "name":  res.user.user_metadata.get("full_name", email.split("@")[0])
                }
                session["access_token"] = res.session.access_token
                flash(f"Welcome back, {session['user']['name']}!", "success")
                return redirect(url_for("dashboard"))
            flash("Invalid credentials.", "error")
        except Exception as e:
            flash("Invalid email or password.", "error")

    return render_template("login.html")

@app.route("/logout")
def logout():
    try:
        supabase.auth.sign_out()
    except Exception:
        pass
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))

@app.route("/dashboard")
@login_required
def dashboard():
    user = session["user"]
    try:
        res = supabase.table("bookings").select("*").eq("user_id", user["id"]).order("created_at", desc=True).limit(3).execute()
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
        if not full_name:  errors.append("Full name is required.")
        if not phone:      errors.append("Phone number is required.")
        if not address:    errors.append("Address is required.")
        if service_type not in SERVICES: errors.append("Invalid service selected.")
        if not pickup_date: errors.append("Pickup date is required.")
        if not pickup_time: errors.append("Pickup time is required.")
        if weight <= 0:    errors.append("Weight must be greater than 0.")

        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("booking.html", services=SERVICES, user=user, form=request.form)

        try:
            supabase.table("bookings").insert({
                "user_id":     user["id"],
                "full_name":   full_name,
                "phone":       phone,
                "address":     address,
                "service_type": service_type,
                "pickup_date": pickup_date,
                "pickup_time": pickup_time,
                "weight":      weight,
                "notes":       notes,
                "status":      "Pending"
            }).execute()
            flash("Booking confirmed! We'll pick up your laundry soon. 🎉", "success")
            return redirect(url_for("my_bookings"))
        except Exception as e:
            flash(f"Booking failed: {str(e)}", "error")

    return render_template("booking.html", services=SERVICES, user=user, form={})

@app.route("/my-bookings")
@login_required
def my_bookings():
    user = session["user"]
    try:
        res = supabase.table("bookings").select("*").eq("user_id", user["id"]).order("created_at", desc=True).execute()
        bookings = res.data or []
        for b in bookings:
            price = SERVICES.get(b["service_type"], {}).get("price", 0)
            b["total_price"] = round(price * float(b.get("weight", 0)), 2)
    except Exception as e:
        flash(f"Could not load bookings: {str(e)}", "error")
        bookings = []
    return render_template("my_bookings.html", bookings=bookings, user=user)

if __name__ == "__main__":
    app.run(debug=True)
