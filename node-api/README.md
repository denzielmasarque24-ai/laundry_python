# FreshWash Node API

Modular Express backend scaffold with:
- JWT auth
- bcrypt password hashing
- OTP email (Nodemailer + Gmail SMTP)
- Sequelize ORM (default MySQL)
- RESTful routes with consistent JSON responses

## Quick Start

1. Copy `.env.example` to `.env` and fill values.
2. Install dependencies:
   - `npm install`
3. Run:
   - `npm run dev`

## Response Contract

All endpoints return:

```json
{
  "success": true,
  "message": "text",
  "data": {}
}
```

## Main Routes

- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/verify-otp`
- `POST /api/v1/auth/resend-otp`
- `GET /api/v1/auth/me`
- `POST /api/v1/auth/test-email` (admin only)

- `POST /api/v1/orders`
- `GET /api/v1/orders/me`
- `GET /api/v1/orders` (admin only)
- `PATCH /api/v1/orders/:id/status` (admin only)

