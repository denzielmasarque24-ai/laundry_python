with open('.env', 'r') as f:
    lines = f.readlines()

filtered = [l for l in lines if not any(k in l.upper() for k in ['EMAIL_USER','EMAIL_PASS','MAIL_SERVER','MAIL_PORT','MAIL_USE','MAIL_FROM'])]
filtered.append('EMAIL_USER=a94eb4001@smtp-brevo.com\n')
filtered.append('EMAIL_PASS=g3DWNt7rZfkqKTGR\n')
filtered.append('MAIL_SERVER=smtp-relay.brevo.com\n')
filtered.append('MAIL_PORT=587\n')
filtered.append('MAIL_USE_TLS=true\n')
filtered.append('MAIL_USE_SSL=false\n')
filtered.append('MAIL_FROM=a94eb4001@smtp-brevo.com\n')

with open('.env', 'w') as f:
    f.writelines(filtered)

print("Fixed!")
