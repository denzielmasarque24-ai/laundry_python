const OTP_EXPIRY_MINUTES = Number.parseInt(process.env.OTP_EXPIRY_MINUTES || "10", 10);

// In-memory OTP store for quick scaffolding. Replace with DB in production.
const otpStore = new Map();

const normalizeEmail = (email) => String(email || "").trim().toLowerCase();

const generateOTP = () => {
  const min = 100000;
  const max = 999999;
  return String(Math.floor(Math.random() * (max - min + 1)) + min);
};

const storeOTP = (email, otp) => {
  const normalizedEmail = normalizeEmail(email);
  const expiresAt = Date.now() + (OTP_EXPIRY_MINUTES * 60 * 1000);
  otpStore.set(normalizedEmail, {
    otp: String(otp),
    expiresAt
  });
  return { expiresAt };
};

const verifyOTP = (email, otp) => {
  const normalizedEmail = normalizeEmail(email);
  const stored = otpStore.get(normalizedEmail);

  if (!stored) {
    return { valid: false, reason: "invalid" };
  }

  if (Date.now() > stored.expiresAt) {
    otpStore.delete(normalizedEmail);
    return { valid: false, reason: "expired" };
  }

  if (stored.otp !== String(otp)) {
    return { valid: false, reason: "invalid" };
  }

  otpStore.delete(normalizedEmail);
  return { valid: true, reason: null };
};

module.exports = {
  generateOTP,
  storeOTP,
  verifyOTP
};

