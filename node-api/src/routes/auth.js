const express = require("express");
const jwt = require("jsonwebtoken");
const { sendOTP, isEmailConfigured } = require("../utils/mailer");
const { generateOTP, storeOTP, verifyOTP } = require("../utils/otp");

const router = express.Router();

const normalizeEmail = (email) => String(email || "").trim().toLowerCase();

router.post("/auth/send-otp", async (req, res) => {
  try {
    const email = normalizeEmail(req.body.email);
    if (!email) {
      return res.status(400).json({
        success: false,
        message: "Email is required.",
        data: {}
      });
    }

    if (!isEmailConfigured()) {
      return res.status(500).json({
        success: false,
        message: "OTP email is not configured on this server.",
        data: {}
      });
    }

    const otp = generateOTP();
    storeOTP(email, otp);
    await sendOTP(email, otp);

    return res.status(200).json({
      success: true,
      message: "OTP sent successfully.",
      data: {}
    });
  } catch (error) {
    console.error("SEND_OTP_ERROR:", error);
    const isAuthError = error?.responseCode === 535 || error?.code === "EAUTH";
    return res.status(500).json({
      success: false,
      message: isAuthError
        ? "Invalid Gmail credentials or App Password required"
        : "Failed to send OTP email.",
      data: {}
    });
  }
});

router.post("/auth/verify-otp", async (req, res) => {
  try {
    const email = normalizeEmail(req.body.email);
    const otp = String(req.body.otp || "").trim();
    if (!email || !otp) {
      return res.status(400).json({
        success: false,
        message: "Email and OTP are required.",
        data: {}
      });
    }

    const result = verifyOTP(email, otp);
    if (!result.valid && result.reason === "expired") {
      return res.status(400).json({
        success: false,
        message: "OTP has expired. Please request a new one.",
        data: {}
      });
    }
    if (!result.valid) {
      return res.status(400).json({
        success: false,
        message: "Invalid OTP.",
        data: {}
      });
    }

    const jwtSecret = process.env.JWT_SECRET || "";
    if (!jwtSecret) {
      return res.status(500).json({
        success: false,
        message: "JWT configuration is missing on this server.",
        data: {}
      });
    }

    const token = jwt.sign(
      { email },
      jwtSecret,
      { expiresIn: "7d" }
    );

    return res.status(200).json({
      success: true,
      message: "OTP verified successfully.",
      data: { token }
    });
  } catch (error) {
    console.error("VERIFY_OTP_ERROR:", error);
    return res.status(500).json({
      success: false,
      message: "OTP verification failed.",
      data: {}
    });
  }
});

module.exports = router;

