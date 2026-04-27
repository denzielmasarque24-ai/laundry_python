const bcrypt = require("bcryptjs");
const { User } = require("../models");
const env = require("../config/env");
const { sendSuccess } = require("../utils/response");
const ApiError = require("../utils/apiError");
const { signAccessToken } = require("../utils/jwt");
const { createAndSendOtp, verifyOtpCode } = require("../services/otp.service");
const { smtpConfigError, sendOtpEmail } = require("../services/email.service");

const normalizedEmail = (value) => String(value || "").trim().toLowerCase();
const isAdminEmail = (email) => env.adminEmails.includes(normalizedEmail(email));

const register = async (req, res, next) => {
  try {
    const { fullName, email, password, phone, address } = req.body;
    const safeEmail = normalizedEmail(email);
    const role = isAdminEmail(safeEmail) ? "admin" : "user";

    const existingUser = await User.findOne({ where: { email: safeEmail } });
    if (existingUser) {
      if (existingUser.role === "admin") {
        throw new ApiError(409, "This email is reserved for admin.");
      }
      throw new ApiError(409, "Account already exists, please login.");
    }

    if (role === "user") {
      const configError = smtpConfigError();
      if (configError) throw new ApiError(500, `OTP email configuration error: ${configError}`);
    }

    const passwordHash = await bcrypt.hash(password, 10);
    const user = await User.create({
      fullName,
      email: safeEmail,
      passwordHash,
      phone: phone || null,
      address: address || null,
      role,
      isVerified: role === "admin"
    });

    console.log("ROLE_DETECTED", { email: safeEmail, role });

    if (role === "admin") {
      return sendSuccess(res, "Admin account created. OTP skipped.", {
        requiresOtp: false
      }, 201);
    }

    await createAndSendOtp({ user, purpose: "register" });
    return sendSuccess(res, "Registration successful. OTP sent to email.", {
      requiresOtp: true,
      email: user.email
    }, 201);
  } catch (error) {
    return next(error);
  }
};

const login = async (req, res, next) => {
  try {
    const { email, password } = req.body;
    const safeEmail = normalizedEmail(email);
    const user = await User.findOne({ where: { email: safeEmail } });
    if (!user) throw new ApiError(401, "Invalid email or password.");

    const passwordOk = await bcrypt.compare(password, user.passwordHash);
    if (!passwordOk) throw new ApiError(401, "Invalid email or password.");

    const role = isAdminEmail(safeEmail) ? "admin" : user.role;
    if (role !== user.role) {
      user.role = role;
      await user.save();
    }
    console.log("ROLE_DETECTED", { email: safeEmail, role });

    if (role === "admin") {
      console.log("OTP_SKIPPED_ADMIN", { email: safeEmail });
      const token = signAccessToken({ sub: user.id, role });
      return sendSuccess(res, "Login successful.", {
        token,
        user: { id: user.id, email: user.email, fullName: user.fullName, role },
        requiresOtp: false
      });
    }

    if (!user.isVerified) {
      const configError = smtpConfigError();
      if (configError) throw new ApiError(500, `OTP email configuration error: ${configError}`);
      await createAndSendOtp({ user, purpose: "register" });
      return sendSuccess(res, "Account not verified. OTP sent.", {
        requiresOtp: true,
        purpose: "register",
        email: user.email
      });
    }

    if (env.otp.enableLoginOtp) {
      const configError = smtpConfigError();
      if (configError) throw new ApiError(500, `OTP email configuration error: ${configError}`);
      await createAndSendOtp({ user, purpose: "login" });
      return sendSuccess(res, "Login OTP sent.", {
        requiresOtp: true,
        purpose: "login",
        email: user.email
      });
    }

    const token = signAccessToken({ sub: user.id, role: user.role });
    return sendSuccess(res, "Login successful.", {
      token,
      user: { id: user.id, email: user.email, fullName: user.fullName, role: user.role },
      requiresOtp: false
    });
  } catch (error) {
    return next(error);
  }
};

const verifyOtp = async (req, res, next) => {
  try {
    const { email, code, purpose = "register" } = req.body;
    const user = await User.findOne({ where: { email: normalizedEmail(email) } });
    if (!user) throw new ApiError(404, "User not found.");

    await verifyOtpCode({ user, code, purpose });

    if (purpose === "register") {
      user.isVerified = true;
      await user.save();
      return sendSuccess(res, "Registration OTP verified successfully.", {
        verified: true
      });
    }

    const token = signAccessToken({ sub: user.id, role: user.role });
    return sendSuccess(res, "Login OTP verified successfully.", {
      token,
      user: {
        id: user.id,
        email: user.email,
        fullName: user.fullName,
        role: user.role
      }
    });
  } catch (error) {
    return next(error);
  }
};

const resendOtp = async (req, res, next) => {
  try {
    const { email, purpose = "register" } = req.body;
    const user = await User.findOne({ where: { email: normalizedEmail(email) } });
    if (!user) throw new ApiError(404, "User not found.");
    if (user.role === "admin") throw new ApiError(400, "Admin accounts do not require OTP.");

    const configError = smtpConfigError();
    if (configError) throw new ApiError(500, `OTP email configuration error: ${configError}`);

    await createAndSendOtp({ user, purpose });
    return sendSuccess(res, "OTP resent successfully.", {
      email: user.email,
      purpose
    });
  } catch (error) {
    return next(error);
  }
};

const me = async (req, res, next) => {
  try {
    return sendSuccess(res, "Authenticated user fetched.", {
      user: {
        id: req.user.id,
        email: req.user.email,
        fullName: req.user.fullName,
        role: req.user.role,
        isVerified: req.user.isVerified
      }
    });
  } catch (error) {
    return next(error);
  }
};

const testEmail = async (req, res, next) => {
  try {
    const to = normalizedEmail(req.body.email || req.user.email);
    const configError = smtpConfigError();
    if (configError) throw new ApiError(500, `OTP email configuration error: ${configError}`);
    await sendOtpEmail({ to, code: "123456", purpose: "login" });
    return sendSuccess(res, "Test email sent successfully.", { to });
  } catch (error) {
    return next(error);
  }
};

module.exports = {
  register,
  login,
  verifyOtp,
  resendOtp,
  me,
  testEmail
};
