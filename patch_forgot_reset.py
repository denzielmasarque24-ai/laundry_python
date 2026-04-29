c = open('app.py', 'rb').read().decode('utf-8')

old = 'app.secret_key = os.environ.get("SECRET_KEY", "freshwash-secret-key-2024")\r\n'
new = (
    'app.secret_key = os.environ.get("SECRET_KEY", "freshwash-secret-key-2024")\r\n'
    'app.config["SUPABASE_URL"] = os.environ.get("SUPABASE_URL", "")\r\n'
    'app.config["SUPABASE_ANON_KEY"] = os.environ.get("SUPABASE_ANON_KEY", "")\r\n'
)

assert old in c, "Target not found!"
c = c.replace(old, new, 1)
open('app.py', 'wb').write(c.encode('utf-8'))
print("Done.")
