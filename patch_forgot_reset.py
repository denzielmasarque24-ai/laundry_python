c = open('app.py', 'rb').read().decode('utf-8')

# 1. Expose APP_URL in app.config
old1 = 'app.config["SUPABASE_URL"] = os.environ.get("SUPABASE_URL", "")\r\napp.config["SUPABASE_ANON_KEY"] = os.environ.get("SUPABASE_ANON_KEY", "")\r\n'
new1 = 'app.config["SUPABASE_URL"] = os.environ.get("SUPABASE_URL", "")\r\napp.config["SUPABASE_ANON_KEY"] = os.environ.get("SUPABASE_ANON_KEY", "")\r\napp.config["APP_URL"] = (os.environ.get("APP_URL") or "http://localhost:5000").rstrip("/")\r\n'
assert old1 in c, "Patch 1 target not found!"
c = c.replace(old1, new1, 1)
print("Patch 1 applied.")

# 2. Replace reset_redirect to use APP_URL
old2 = (
    '        reset_redirect = (\n'
    '            (os.environ.get("FRESHWASH_PASSWORD_RESET_REDIRECT_TO") or "").strip()\n'
    '            or url_for("reset_password_page", _external=True)\n'
    '        )\n'
    '        supabase.auth.reset_password_for_email(email, {"redirect_to": reset_redirect})\n'
)
new2 = (
    '        app_url = (os.environ.get("APP_URL") or "http://localhost:5000").rstrip("/")\n'
    '        reset_redirect = (\n'
    '            (os.environ.get("FRESHWASH_PASSWORD_RESET_REDIRECT_TO") or "").strip()\n'
    '            or f"{app_url}/reset-password"\n'
    '        )\n'
    '        supabase.auth.reset_password_for_email(email, {"redirect_to": reset_redirect})\n'
)

# try LF first, then CRLF
if old2 in c:
    c = c.replace(old2, new2, 1)
    print("Patch 2 applied (LF).")
else:
    old2_crlf = old2.replace('\n', '\r\n')
    new2_crlf = new2.replace('\n', '\r\n')
    assert old2_crlf in c, "Patch 2 target not found!"
    c = c.replace(old2_crlf, new2_crlf, 1)
    print("Patch 2 applied (CRLF).")

open('app.py', 'wb').write(c.encode('utf-8'))
print("Done.")
