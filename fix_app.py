with open('app.py', 'r') as f:
    content = f.read()

# Fix error message
old1 = '''        raise RuntimeError(
            "Invalid Resend credentials. "
            "Use EMAIL_USER=onboarding@resend.dev and EMAIL_PASS=your_resend_api_key in .env, "
            "then restart FreshWash."
        ) from exc'''

new1 = '''        raise RuntimeError(
            "Invalid email credentials. Check EMAIL_USER and EMAIL_PASS in .env, then restart FreshWash."
        ) from exc'''

content = content.replace(old1, new1)

# Fix SMTP login - use EMAIL_USER not "resend"
content = content.replace('server.login("resend", OTP_SMTP_PASSWORD)', 'server.login(OTP_SMTP_USER, OTP_SMTP_PASSWORD)')

with open('app.py', 'w') as f:
    f.write(content)

print("Fixed!")
