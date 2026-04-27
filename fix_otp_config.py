with open('app.py', 'r') as f:
    content = f.read()

old = '''def otp_email_configured():
    return otp_email_config_error() == ""'''

new = '''def otp_email_configured():
    if is_supabase_enabled():
        return True
    return otp_email_config_error() == ""'''

content = content.replace(old, new)

with open('app.py', 'w') as f:
    f.write(content)

print("Fixed!")
