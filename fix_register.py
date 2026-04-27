with open('app.py', 'r') as f:
    content = f.read()

old = '''            log_auth_debug("registration complete", email=email, flow="register")
            flash("Account created! Please check your email to verify your account, then log in.", "success")
            return redirect_to_auth_modal("login", {"email": email})'''

new = '''            log_auth_debug("registration complete", email=email, flow="register")
            flash("Account created! Enter the verification code we sent to your email.", "success")
            return redirect_to_auth_modal("verify", otp_modal_form_data())'''

content = content.replace(old, new)

with open('app.py', 'w') as f:
    f.write(content)

print("Fixed!")
