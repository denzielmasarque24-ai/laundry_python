const otpStore = new Map();

function generateOTP() {
  return Math.floor(100000 + Math.random() * 900000).toString();
}

function storeOTP(email, otp) {
  const expiry = Date.now() + 10 * 60 * 1000;
  otpStore.set(email, { otp, expiry });
}

function verifyOTP(email, otp) {
  const record = otpStore.get(email);
  if (!record) return { valid: false, message: "OTP not found. Please request a new one." };
  if (Date.now() > record.expiry) {
    otpStore.delete(email);
    return { valid: false, message: "OTP has expired. Please request a new one." };
  }
  if (record.otp !== otp) {
    return { valid: false, message: "Invalid OTP." };
  }
  otpStore.delete(email);
  return { valid: true, message: "OTP verified successfully." };
}

module.exports = { generateOTP, storeOTP, verifyOTP };