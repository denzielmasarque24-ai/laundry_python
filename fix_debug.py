with open('app.py', 'r') as f:
    content = f.read()

old = '''def issue_otp_challenge(email, purpose, pending_user=None):
    code = generate_otp_code()
    expiry = datetime.now(timezone.utc) + timedelta(minutes=OTP_EXPIRY_MINUTES)
    set_otp_for_account(email, code, expiry)
    send_otp_email(email, code, purpose)
    challenge = set_pending_otp_challenge(email, purpose, pending_user=pending_user)
    return challenge'''

new = '''def issue_otp_challenge(email, purpose, pending_user=None):
    code = generate_otp_code()
    expiry = datetime.now(timezone.utc) + timedelta(minutes=OTP_EXPIRY_MINUTES)
    print(f"DEBUG: Generating OTP for {email}, code={code}")
    set_otp_for_account(email, code, expiry)
    try:
        send_otp_email(email, code, purpose)
        print(f"DEBUG: OTP email sent OK to {email}")
    except Exception as e:
        print(f"DEBUG: OTP email FAILED: {e}")
    challenge = set_pending_otp_challenge(email, purpose, pending_user=pending_user)
    return challenge'''

content = content.replace(old, new)

with open('app.py', 'w') as f:
    f.write(content)

print("Fixed!")
