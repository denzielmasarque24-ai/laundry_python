with open('app.py', 'r') as f:
    content = f.read()

old = '''            # Send OTP via Supabase
            try:
                supabase.auth.sign_in_with_otp({"email": email})
                log_auth_debug("supabase otp sent", email=email, flow="register")
            except Exception as otp_err:
                log_exception("supabase otp send failed", otp_err, email=email)
            flash("Account created! Enter the verification code we sent to your email.", "success")
            return redirect_to_auth_modal("verify", otp_modal_form_data())'''

new = '''            issue_otp_challenge(email, "signup")
            log_auth_debug("otp sent for user", email=email, flow="register")
            flash("Account created! Enter the verification code we sent to your email.", "success")
            return redirect_to_auth_modal("verify", otp_modal_form_data())'''

content = content.replace(old, new)

with open('app.py', 'w') as f:
    f.write(content)

print("Fixed!")
