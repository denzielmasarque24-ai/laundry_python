const path = require("path");
const dotenv = require("dotenv");

dotenv.config({ path: path.resolve(process.cwd(), ".env") });

const toBool = (value, fallback = false) => {
  if (value === undefined || value === null || value === "") return fallback;
  return ["1", "true", "yes", "on"].includes(String(value).toLowerCase());
};

const toInt = (value, fallback) => {
  const parsed = Number.parseInt(value, 10);
  return Number.isNaN(parsed) ? fallback : parsed;
};

module.exports = {
  nodeEnv: process.env.NODE_ENV || "development",
  port: toInt(process.env.PORT, 5000),
  apiPrefix: process.env.API_PREFIX || "/api/v1",

  db: {
    dialect: process.env.DB_DIALECT || "mysql",
    host: process.env.DB_HOST || "localhost",
    port: toInt(process.env.DB_PORT, 3306),
    name: process.env.DB_NAME || "freshwash",
    user: process.env.DB_USER || "root",
    password: process.env.DB_PASSWORD || "",
    logging: toBool(process.env.DB_LOGGING, false),
    sync: toBool(process.env.DB_SYNC, false)
  },

  jwt: {
    secret: process.env.JWT_SECRET || "",
    expiresIn: process.env.JWT_EXPIRES_IN || "7d"
  },

  mail: {
    user: (process.env.EMAIL_USER || "").trim(),
    pass: (process.env.EMAIL_PASS || "").replace(/\s+/g, ""),
    server: (process.env.MAIL_SERVER || "smtp.gmail.com").trim(),
    port: toInt(process.env.MAIL_PORT, 587),
    useTls: toBool(process.env.MAIL_USE_TLS, true),
    useSsl: toBool(process.env.MAIL_USE_SSL, false),
    from: (process.env.MAIL_FROM || process.env.EMAIL_USER || "no-reply@freshwash.local").trim()
  },

  otp: {
    length: toInt(process.env.OTP_LENGTH, 6),
    expiryMinutes: toInt(process.env.OTP_EXPIRY_MINUTES, 5),
    maxAttempts: toInt(process.env.OTP_MAX_ATTEMPTS, 3),
    resendCooldownSeconds: toInt(process.env.OTP_RESEND_COOLDOWN_SECONDS, 60),
    enableLoginOtp: toBool(process.env.ENABLE_LOGIN_OTP, true)
  },

  adminEmails: (process.env.ADMIN_EMAILS || "")
    .split(",")
    .map((email) => email.trim().toLowerCase())
    .filter(Boolean)
};

