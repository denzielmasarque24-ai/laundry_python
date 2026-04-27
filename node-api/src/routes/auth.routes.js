const express = require("express");
const validateRequest = require("../middleware/validate.middleware");
const { requireAuth, requireAdmin } = require("../middleware/auth.middleware");
const {
  registerValidation,
  loginValidation,
  verifyOtpValidation,
  resendOtpValidation
} = require("../validators/auth.validator");
const {
  register,
  login,
  verifyOtp,
  resendOtp,
  me,
  testEmail
} = require("../controllers/auth.controller");

const router = express.Router();

router.post("/register", registerValidation, validateRequest, register);
router.post("/login", loginValidation, validateRequest, login);
router.post("/verify-otp", verifyOtpValidation, validateRequest, verifyOtp);
router.post("/resend-otp", resendOtpValidation, validateRequest, resendOtp);
router.get("/me", requireAuth, me);
router.post("/test-email", requireAuth, requireAdmin, testEmail);

module.exports = router;
