const nodemailer = require("nodemailer");

const EMAIL_USER = (process.env.EMAIL_USER || process.env.FRESHWASH_OTP_SMTP_USER || "").trim();
const EMAIL_PASS = (process.env.EMAIL_PASS || process.env.FRESHWASH_OTP_SMTP_PASSWORD || "").replace(/\s+/g, "");

const isEmailConfigured = () => Boolean(EMAIL_USER && EMAIL_PASS);

if (!isEmailConfigured()) {
  console.warn(
    "WARN: OTP email is not configured on this server. Missing EMAIL_USER/EMAIL_PASS or FRESHWASH_OTP_SMTP_USER/FRESHWASH_OTP_SMTP_PASSWORD."
  );
}

const transporter = nodemailer.createTransport({
  host: "smtp.resend.com",
  port: 465,
  secure: true,
  auth: {
    user: "resend",
    pass: EMAIL_PASS
  }
});

const sendOTP = async (email, otp) => {
  if (!isEmailConfigured()) {
    throw new Error("OTP email is not configured on this server.");
  }

  return transporter.sendMail({
    from: EMAIL_USER,
    to: email,
    subject: "Your FreshWash Verification Code",
    html: `
      <div style="font-family: Arial, sans-serif; color: #111827; line-height: 1.6;">
        <h2 style="margin: 0 0 12px;">FreshWash Verification Code</h2>
        <p style="margin: 0 0 10px;">Use this OTP to continue:</p>
        <p style="font-size: 24px; font-weight: 700; letter-spacing: 4px; margin: 8px 0 16px;">${otp}</p>
        <p style="margin: 0;">This code expires soon. If you did not request it, you can ignore this email.</p>
      </div>
    `
  });
};

module.exports = {
  sendOTP,
  isEmailConfigured
};
