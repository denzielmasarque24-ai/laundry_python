# ðŸ§º FreshWash â€“ Laundry Shop Management System

A full-stack web app built with **Python Flask** + **Supabase**.

---

## ðŸš€ Quick Start

### 1. Set Up Supabase

1. Go to [supabase.com](https://supabase.com) and create a free project
2. Open **SQL Editor** â†’ paste and run the contents of `supabase_schema.sql`
3. Go to **Project Settings â†’ API** and copy:
   - `Project URL` â†’ `SUPABASE_URL`
   - `anon public` key â†’ `SUPABASE_KEY`

### 2. Configure Environment

Edit `.env` with your credentials:
```
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_KEY=your_anon_key_here
SECRET_KEY=any_random_string
```

### 3. Install & Run

```bash
cd FreshWash
pip install -r requirements.txt
python app.py
```

Open your browser at **http://127.0.0.1:5000**

---

## ðŸ“ Project Structure

```
FreshWash/
â”œâ”€â”€ app.py                  # Flask routes & logic
â”œâ”€â”€ supabase_client.py      # Supabase connection
â”œâ”€â”€ supabase_schema.sql     # Database setup script
â”œâ”€â”€ requirements.txt
â”œâ”€â”€ .env                    # Your credentials (never commit this)
â”œâ”€â”€ templates/
â”‚   â”œâ”€â”€ base.html           # Shared layout + navbar
â”‚   â”œâ”€â”€ login.html
â”‚   â”œâ”€â”€ register.html
â”‚   â”œâ”€â”€ dashboard.html
â”‚   â”œâ”€â”€ services.html
â”‚   â”œâ”€â”€ booking.html
â”‚   â””â”€â”€ my_bookings.html
â””â”€â”€ static/
    â””â”€â”€ css/
        â””â”€â”€ style.css       # Pink theme styles
```

---

## ðŸ’° Services & Pricing

| Service       | Price   |
|---------------|---------|
| Wash & Fold   | â‚±150/kg |
| Wash & Iron   | â‚±200/kg |
| Dry Cleaning  | â‚±250/kg |
| Premium Wash  | â‚±350/kg |

---

## Supabase Auth Notes

- FreshWash uses email OTP codes (6 digits) via signInWithOtp + erifyOtp.
- Do not use confirmation/magic-link templates for login verification.
- In Supabase templates, use {{ .Token }} and remove {{ .ConfirmationURL }} for OTP-code emails.

---

## Expanding the System

- **Admin Panel**: Add a role check (`is_admin`) in user metadata and create `/admin` routes
- **Status Updates**: Add a PATCH route to update booking status
- **Email Notifications**: Use Supabase Edge Functions or Flask-Mail
"laundry_python" 

---

## Supabase OTP Template (No Links)

FreshWash uses Supabase Email OTP code verification (6 digits), not magic links.

In Supabase Dashboard:
1. Go to `Authentication -> Email Templates -> Magic Link`
2. Remove all `{{ .ConfirmationURL }}`
3. Use this content only:

```html
<h2>FreshWash OTP Verification</h2>
<p>Your 6-digit verification code is:</p>
<h1>{{ .Token }}</h1>
<p>This code will expire soon.</p>
```

If `{{ .ConfirmationURL }}` is present, users may receive a clickable link instead of a code-style email.

Delivery note:
- Supabase default email sender may not deliver to some non-team email addresses.
- Configure Custom SMTP in `Authentication -> Settings -> SMTP Settings` for reliable delivery.

Brevo Custom SMTP for Supabase:
- Host: `smtp-relay.brevo.com`
- Port: `587`
- Username: your Brevo SMTP login
- Password: your Brevo SMTP key
- Sender email: a verified Brevo sender email
- Sender name: `FreshWash`

