const nodemailer = require("nodemailer");

const EMAIL_USER = (process.env.EMAIL_USER || process.env.FRESHWASH_OTP_SMTP_USER || "").trim();
const EMAIL_PASS = (process.env.EMAIL_PASS || process.env.FRESHWASH_OTP_SMTP_PASSWORD || "").replace(/\s+/g, "");

let transporter = null;
let isConfigured = false;

if (!EMAIL_USER || !EMAIL_PASS) {
  console.warn("WARN: OTP email is not configured. Set EMAIL_USER and EMAIL_PASS in .env");
} else {
  isConfigured = true;
  transporter = nodemailer.createTransport({
    host: "smtp.resend.com",
    port: 465,
    secure: true,
    auth: {
      user: "resend",
      pass: EMAIL_PASS
    }
  });
}

const sendOTP = async (email, otp) => {
  if (!transporter) {
    throw new Error("OTP email is not configured on this server.");
  }
  await transporter.sendMail({
    from: `"FreshWash" <${EMAIL_USER}>`,
    to: email,
    subject: "Your FreshWash Verification Code",
    html: `
      <div style="font-family:sans-serif;max-width:420px;margin:auto;padding:24px;border-radius:12px;border:1px solid #f9a8d4;">
        <h2 style="color:#e91e8c;">🧺 FreshWash</h2>
        <p style="font-size:16px;">Your verification code is:</p>
        <h1 style="font-size:48px;letter-spacing:12px;color:#e91e8c;margin:16px 0;">${otp}</h1>
        <p style="color:#888;">This code expires in <strong>10 minutes</strong>.</p>
        <p style="color:#888;">If you did not request this, ignore this email.</p>
      </div>
    `
  });
};

module.exports = { sendOTP, isConfigured };