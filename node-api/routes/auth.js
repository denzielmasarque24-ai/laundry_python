const express = require("express");
const jwt = require("jsonwebtoken");
const { sendOTP, isConfigured } = require("../utils/mailer");
const { generateOTP, storeOTP, verifyOTP } = require("../utils/otp");

const router = express.Router();

const normalizeEmail = (email) => String(email || "").trim().toLowerCase();

router.post("/send-otp", async (req, res) => {
  try {
    const email = normalizeEmail(req.body.email);
    if (!email) {
      return res.status(400).json({ success: false, message: "Email is required.", data: {} });
    }
    if (!isConfigured) {
      return res.status(503).json({ success: false, message: "OTP email is not configured on this server.", data: {} });
    }
    const otp = generateOTP();
    storeOTP(email, otp);
    await sendOTP(email, otp);
    return res.status(200).json({ success: true, message: "OTP sent successfully.", data: {} });
  } catch (error) {
    console.error("SEND_OTP_ERROR:", error);
    return res.status(500).json({ success: false, message: "Failed to send OTP.", data: {} });
  }
});

router.post("/verify-otp", async (req, res) => {
  try {
    const email = normalizeEmail(req.body.email);
    const otp = String(req.body.otp || "").trim();
    if (!email || !otp) {
      return res.status(400).json({ success: false, message: "Email and OTP are required.", data: {} });
    }
    const verification = verifyOTP(email, otp);
    if (!verification.valid) {
      return res.status(400).json({ success: false, message: verification.message, data: {} });
    }
    const jwtSecret = process.env.JWT_SECRET || "";
    if (!jwtSecret) {
      return res.status(500).json({ success: false, message: "JWT_SECRET is not configured.", data: {} });
    }
    const token = jwt.sign({ email }, jwtSecret, { expiresIn: "7d" });
    return res.status(200).json({ success: true, message: verification.message, data: { token } });
  } catch (error) {
    console.error("VERIFY_OTP_ERROR:", error);
    return res.status(500).json({ success: false, message: "Failed to verify OTP.", data: {} });
  }
});

module.exports = router;