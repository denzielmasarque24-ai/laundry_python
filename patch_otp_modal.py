import re

path = 'c:/Bayot/FreshWash/app.py'
content = open(path, encoding='utf-8').read()

# ── 1. Add JSON API endpoints before the /dashboard route ─────────────────
dashboard_marker = '@app.route("/dashboard")\n@login_required\ndef dashboard():'
assert dashboard_marker in content, 'dashboard marker not found'

json_endpoints = '''
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
                    existing_auth_user = find_supabase_auth_user_by_email(email)
                    verified_user = existing_auth_user or create_supabase_signup_user(
                        name=full_name, email=email, phone=phone, address=address,
                        password=password, role=signup_role, email_confirm=True,
                    )
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
            profile = find_profile_by_email(email) or {}
            if not profile and local_auth_enabled():
                local_user, _ = find_local_user(email)
                if local_user:
                    profile = {"id": local_user.get("id",""), "full_name": local_user.get("full_name",""),
                               "phone": local_user.get("phone",""), "address": local_user.get("address",""),
                               "avatar": local_user.get("avatar",""), "role": local_user.get("role","user")}
            resolved_role = user_role_for_email(email, profile.get("role", "user"))
            verified_session_user = {
                "id": profile.get("id", ""), "email": email,
                "name": profile.get("full_name") or email.split("@")[0],
                "phone": profile.get("phone", ""), "address": profile.get("address", ""),
                "avatar": profile.get("avatar", ""), "role": resolved_role,
                "is_admin": resolved_role == "admin",
            }
            persist_session_user(verified_session_user)
            redirect_url = url_for("admin_dashboard") if resolved_role == "admin" else url_for("home")
            return jsonify({"ok": True, "redirect": redirect_url})
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


'''

content = content.replace(dashboard_marker, json_endpoints + dashboard_marker, 1)
print('OK: JSON endpoints injected')

# ── 2. Change register POST to set active_auth_modal="otp" instead of /verify ─
old_reg = (
    'print("AUTH: Redirecting to verify page")\n'
    '            session["auth_form_data"] = {**otp_modal_form_data(), "show_signup_success": bool(otp_sent)}\n'
    '            session.modified = True\n'
    '            return redirect(url_for("verify_page"))'
)
new_reg = (
    'print("AUTH: Redirecting to verify page")\n'
    '            session["auth_form_data"] = {**otp_modal_form_data(), "show_signup_success": bool(otp_sent)}\n'
    '            session["auth_modal"] = "otp"\n'
    '            session.modified = True\n'
    '            return redirect(url_for("home"))'
)
if old_reg in content:
    content = content.replace(old_reg, new_reg, 1)
    print('OK: register redirect updated')
else:
    print('WARN: register redirect not found (may already be correct)')

# ── 3. Change login OTP redirect to use modal ──────────────────────────────
# Login currently ends with: return redirect_to_auth_modal("verify", otp_modal_form_data())
# Replace the two occurrences inside the login route with the new modal approach
old_login_verify = 'return redirect_to_auth_modal("verify", otp_modal_form_data())\n\n            persist_session_user(user)'
new_login_verify = (
    'session["auth_form_data"] = otp_modal_form_data()\n'
    '            session["auth_modal"] = "otp"\n'
    '            session.modified = True\n'
    '            return redirect(url_for("home"))\n\n'
    '            persist_session_user(user)'
)
if old_login_verify in content:
    content = content.replace(old_login_verify, new_login_verify, 1)
    print('OK: login OTP redirect updated')
else:
    print('WARN: login OTP redirect not found')

open(path, 'w', encoding='utf-8').write(content)
print('Done writing file')
