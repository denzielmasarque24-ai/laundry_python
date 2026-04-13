# 🧺 FreshWash – Laundry Shop Management System

A full-stack web app built with **Python Flask** + **Supabase**.

---

## 🚀 Quick Start

### 1. Set Up Supabase

1. Go to [supabase.com](https://supabase.com) and create a free project
2. Open **SQL Editor** → paste and run the contents of `supabase_schema.sql`
3. Go to **Project Settings → API** and copy:
   - `Project URL` → `SUPABASE_URL`
   - `anon public` key → `SUPABASE_KEY`

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

## 📁 Project Structure

```
FreshWash/
├── app.py                  # Flask routes & logic
├── supabase_client.py      # Supabase connection
├── supabase_schema.sql     # Database setup script
├── requirements.txt
├── .env                    # Your credentials (never commit this)
├── templates/
│   ├── base.html           # Shared layout + navbar
│   ├── login.html
│   ├── register.html
│   ├── dashboard.html
│   ├── services.html
│   ├── booking.html
│   └── my_bookings.html
└── static/
    └── css/
        └── style.css       # Pink theme styles
```

---

## 💰 Services & Pricing

| Service       | Price   |
|---------------|---------|
| Wash & Fold   | ₱150/kg |
| Wash & Iron   | ₱200/kg |
| Dry Cleaning  | ₱250/kg |
| Premium Wash  | ₱350/kg |

---

## 🔐 Supabase Auth Notes

- Email confirmation is **disabled by default** in new Supabase projects (good for dev)
- To disable it in production: Supabase Dashboard → Authentication → Settings → uncheck "Enable email confirmations"

---

## 🛠️ Expanding the System

- **Admin Panel**: Add a role check (`is_admin`) in user metadata and create `/admin` routes
- **Status Updates**: Add a PATCH route to update booking status
- **Email Notifications**: Use Supabase Edge Functions or Flask-Mail
