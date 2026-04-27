const { body } = require("express-validator");

const registerValidation = [
  body("fullName").trim().notEmpty().withMessage("Full name is required."),
  body("email").trim().isEmail().withMessage("Valid email is required."),
  body("password")
    .isLength({ min: 6 })
    .withMessage("Password must be at least 6 characters."),
  body("phone").optional({ nullable: true }).trim(),
  body("address").optional({ nullable: true }).trim()
];

const loginValidation = [
  body("email").trim().isEmail().withMessage("Valid email is required."),
  body("password").notEmpty().withMessage("Password is required.")
];

const verifyOtpValidation = [
  body("email").trim().isEmail().withMessage("Valid email is required."),
  body("purpose")
    .optional()
    .isIn(["register", "login"])
    .withMessage("Purpose must be register or login."),
  body("code")
    .trim()
    .isLength({ min: 6, max: 6 })
    .isNumeric()
    .withMessage("OTP code must be 6 digits.")
];

const resendOtpValidation = [
  body("email").trim().isEmail().withMessage("Valid email is required."),
  body("purpose")
    .optional()
    .isIn(["register", "login"])
    .withMessage("Purpose must be register or login.")
];

module.exports = {
  registerValidation,
  loginValidation,
  verifyOtpValidation,
  resendOtpValidation
};

