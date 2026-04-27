const env = require("../config/env");
const transporter = require("../config/mailer");
const ApiError = require("../utils/apiError");

const smtpConfigError = () => {
  if (!env.mail.user) return "EMAIL_USER (or MAIL_USERNAME) is missing.";
  if (!env.mail.pass) return "EMAIL_PASS (or MAIL_PASSWORD) is missing.";
  return "";
};

const sendOtpEmail = async ({ to, code, purpose }) => {
  const configError = smtpConfigError();
  if (configError) {
    throw new ApiError(
      500,
      `OTP email is not configured on this server. Set EMAIL_USER and EMAIL_PASS in .env, then restart FreshWash.`
    );
  }

  try {
    await transporter.sendMail({
      from: env.mail.from,
      to,
      subject: "Your FreshWash Verification Code",
      html: `
        <div style="font-family:sans-serif;max-width:420px;margin:auto;padding:24px;border-radius:12px;border:1px solid #f9a8d4;">
          <h2 style="color:#e91e8c;">🧺 FreshWash</h2>
          <p style="font-size:16px;">Your <strong>${purpose}</strong> verification code is:</p>
          <h1 style="font-size:48px;letter-spacing:12px;color:#e91e8c;margin:16px 0;">${code}</h1>
          <p style="color:#888;">This code expires in <strong>${env.otp.expiryMinutes} minutes</strong>.</p>
          <p style="color:#888;">If you did not request this, ignore this email.</p>
        </div>
      `
    });
    console.log("OTP_EMAIL_SENT", { to, purpose });
  } catch (error) {
    console.error("OTP_EMAIL_ERROR", { to, purpose, message: error.message });
    throw new ApiError(500, "Failed to send OTP email. Please check your email configuration.");
  }
};

module.exports = { smtpConfigError, sendOtpEmail };