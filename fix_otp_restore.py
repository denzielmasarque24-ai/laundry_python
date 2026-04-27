with open('app.py', 'r') as f:
    content = f.read()

old = '''def issue_otp_challenge(email, purpose, pending_user=None):
    try:
        supabase.auth.sign_in_with_otp({"email": email, "options": {"should_create_user": False}})
        print(f"AUTH: Supabase OTP sent | email={email!r}, purpose={purpose!r}")
    except Exception as e:
        print(f"AUTH: Supabase OTP failed | email={email!r}, error={e!r}")
    challenge = set_pending_otp_challenge(email, purpose, pending_user=pending_user)
    return challenge'''

new = '''def issue_otp_challenge(email, purpose, pending_user=None):
    code = generate_otp_code()
    expiry = datetime.now(timezone.utc) + timedelta(minutes=OTP_EXPIRY_MINUTES)
    set_otp_for_account(email, code, expiry)
    send_otp_email(email, code, purpose)
    challenge = set_pending_otp_challenge(email, purpose, pending_user=pending_user)
    return challenge'''

content = content.replace(old, new)

with open('app.py', 'w') as f:
    f.write(content)

print("Fixed!")
