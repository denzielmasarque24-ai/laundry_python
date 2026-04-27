path = 'c:/Bayot/FreshWash/app.py'
content = open(path, encoding='utf-8').read()

# Insert the /api/register endpoint right before the /verify GET route
marker = '@app.route("/verify", methods=["GET"])\ndef verify_page():'

new_endpoint = '''
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
            existing_profile  = find_profile_by_email(email)
            existing_auth_user = find_supabase_auth_user_by_email(email) if is_supabase_service_role_enabled() else None
            auth_metadata = safe_auth_user_metadata(existing_auth_user) if existing_auth_user else {}
            existing_role = user_role_for_email(
                email, (existing_profile or {}).get("role", "user"), auth_metadata
            ) if existing_auth_user else ""

            if existing_auth_user:
                if existing_role == "admin":
                    return jsonify({"ok": False, "errors": ["This email is reserved for admin."]})
                if not existing_profile:
                    recover_missing_profile_for_auth_user(existing_auth_user, {
                        "email": email, "full_name": name or email.split("@")[0],
                        "phone": phone, "address": address, "role": "user", "is_verified": False,
                    })
                return jsonify({"ok": False, "errors": ["Account already exists, please login."]})

            signup_auth_user = create_supabase_signup_user(
                name=name, email=email, phone=phone, address=address,
                password=password, role=role,
            )
            ensure_supabase_profile_record(signup_auth_user, {
                "full_name": name, "email": email, "phone": phone, "address": address,
                "role": role, "is_verified": True, "otp_code": "", "otp_expiry": None,
            })
            upsert_local_user(name, email, phone, address, password,
                              role_override=role, is_verified=True)

        if role == "admin":
            return jsonify({"ok": True, "otp": False, "redirect": "/"})

        # Issue OTP challenge
        otp_sent = False
        try:
            issue_otp_challenge(
                email, "signup", trigger_send=True,
                pending_signup={
                    "full_name": name, "email": email, "phone": phone,
                    "address": address, "role": "user", "password": password,
                },
            )
            otp_sent = True
        except Exception as otp_err:
            log_exception("api_register otp send failed", otp_err, email=email)
            try:
                issue_otp_challenge(
                    email, "signup", trigger_send=False,
                    pending_signup={
                        "full_name": name, "email": email, "phone": phone,
                        "address": address, "role": "user", "password": password,
                    },
                )
            except Exception:
                pass
            return jsonify({
                "ok": True, "otp": True, "email": email,
                "cooldown": OTP_RESEND_COOLDOWN_SECONDS,
                "warning": str(otp_err),
            })

        return jsonify({
            "ok": True, "otp": True, "email": email,
            "cooldown": OTP_RESEND_COOLDOWN_SECONDS,
        })

    except ValueError as e:
        return jsonify({"ok": False, "errors": [str(e)]})
    except Exception as e:
        log_exception("api_register failed", e, email=email)
        return jsonify({"ok": False, "errors": [f"Registration error: {str(e)}"]})


'''

assert marker in content, f'Marker not found: {marker}'
content = content.replace(marker, new_endpoint + marker, 1)
open(path, 'w', encoding='utf-8').write(content)
print('OK: /api/register endpoint added')
