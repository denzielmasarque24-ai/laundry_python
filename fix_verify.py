with open('app.py', 'r') as f:
    content = f.read()

old = '''@app.route("/auth/verify-otp", methods=["POST"])
def auth_verify_otp():
    challenge = get_pending_otp_challenge()
    if not challenge:
        flash("Verification session expired. Please login or register again.", "error")
        return redirect_to_auth_modal("login")

    submitted_code = (request.form.get("otp_code", "") or "").strip()
    if not submitted_code.isdigit() or len(submitted_code) != OTP_LENGTH:
        flash(f"Enter a valid {OTP_LENGTH}-digit verification code.", "error")
        return redirect_to_auth_modal("verify", otp_modal_form_data(challenge))

    attempts_remaining = int(challenge.get("attempts_remaining", OTP_MAX_ATTEMPTS))
    if attempts_remaining <= 0:
        clear_pending_otp_challenge()
        flash("Too many failed attempts. Please request a new code.", "error")
        return redirect_to_auth_modal("login")

    account_security = get_account_security_state(challenge.get("email", ""))
    if not account_security:
        clear_pending_otp_challenge()
        flash("Account not found. Please register again.", "error")
        return redirect_to_auth_modal("register")

    expected_code = account_security.get("otp_code", "")
    otp_expiry = account_security.get("otp_expiry")
    if not expected_code or not otp_expiry or datetime.now(timezone.utc) > otp_expiry:
        clear_pending_otp_challenge()
        clear_otp_for_account(account_security["email"])
        flash("Verification code expired. Please request a new code.", "error")
        return redirect_to_auth_modal("verify", otp_modal_form_data(challenge))

    if submitted_code != expected_code:
        challenge["attempts_remaining"] = attempts_remaining - 1
        session["pending_otp"] = challenge
        session.modified = True
        if challenge["attempts_remaining"] <= 0:
            clear_pending_otp_challenge()
            clear_otp_for_account(account_security["email"])
            flash("Too many failed attempts. Start again and request a new code.", "error")
            return redirect_to_auth_modal("login")
        flash(f"Invalid code. {challenge['attempts_remaining']} attempt(s) remaining.", "error")
        return redirect_to_auth_modal("verify", otp_modal_form_data(challenge))

    clear_otp_for_account(account_security["email"])
    purpose = challenge.get("purpose", "signup")
    if purpose == "signup":
        set_verification_state(account_security["email"], True)
        clear_pending_otp_challenge()
        flash("Account verified. You can now log in.", "success")
        return redirect_to_auth_modal("login", {"email": account_security["email"]})

    pending_user = challenge.get("pending_user") or {}
    clear_pending_otp_challenge()
    if not pending_user:
        flash("Login session expired. Please login again.", "error")
        return redirect_to_auth_modal("login", {"email": account_security["email"]})
    persist_session_user(pending_user)
    flash(f"Welcome back, {pending_user.get('name', 'User')}!", "success")
    return redirect(url_for("admin_dashboard" if pending_user.get("is_admin") else "home"))'''

new = '''@app.route("/auth/verify-otp", methods=["POST"])
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

    try:
        res = supabase.auth.verify_otp({
            "email": email,
            "token": submitted_code,
            "type": "signup"
        })
        if res and res.user:
            set_verification_state(email, True)
            clear_pending_otp_challenge()
            flash("Account verified! You can now log in.", "success")
            return redirect_to_auth_modal("login", {"email": email})
        else:
            flash("Invalid or expired code. Please try again.", "error")
            return redirect_to_auth_modal("verify", otp_modal_form_data(challenge))
    except Exception as e:
        flash("Invalid or expired code. Please try again.", "error")
        return redirect_to_auth_modal("verify", otp_modal_form_data(challenge))'''

content = content.replace(old, new)

with open('app.py', 'w') as f:
    f.write(content)

print("Fixed!")
