const bcrypt = require("bcryptjs");
const { Op } = require("sequelize");
const env = require("../config/env");
const { Otp } = require("../models");
const { generateOtpCode, otpExpiryDate } = require("../utils/otp");
const ApiError = require("../utils/apiError");
const { sendOtpEmail } = require("./email.service");

const createAndSendOtp = async ({ user, purpose }) => {
  const code = generateOtpCode();
  const codeHash = await bcrypt.hash(code, 10);
  const expiresAt = otpExpiryDate();

  const recentOtp = await Otp.findOne({
    where: {
      userId: user.id,
      purpose,
      consumedAt: null,
      createdAt: { [Op.gte]: new Date(Date.now() - env.otp.resendCooldownSeconds * 1000) }
    },
    order: [["createdAt", "DESC"]]
  });
  if (recentOtp) {
    throw new ApiError(429, `Please wait ${env.otp.resendCooldownSeconds} seconds before requesting another OTP.`);
  }

  await Otp.create({
    userId: user.id,
    purpose,
    codeHash,
    expiresAt,
    attemptsLeft: env.otp.maxAttempts
  });

  console.log("OTP_GENERATED", { email: user.email, purpose, expiresAt: expiresAt.toISOString() });
  await sendOtpEmail({ to: user.email, code, purpose });
};

const verifyOtpCode = async ({ user, code, purpose }) => {
  const otpRecord = await Otp.findOne({
    where: {
      userId: user.id,
      purpose,
      consumedAt: null
    },
    order: [["createdAt", "DESC"]]
  });

  if (!otpRecord) {
    throw new ApiError(400, "No active OTP found. Please request a new code.");
  }
  if (otpRecord.expiresAt < new Date()) {
    throw new ApiError(400, "OTP expired. Please request a new code.");
  }
  if (otpRecord.attemptsLeft <= 0) {
    throw new ApiError(400, "OTP attempts exceeded. Please request a new code.");
  }

  const valid = await bcrypt.compare(code, otpRecord.codeHash);
  if (!valid) {
    otpRecord.attemptsLeft -= 1;
    await otpRecord.save();
    throw new ApiError(400, "Invalid OTP code.");
  }

  otpRecord.consumedAt = new Date();
  await otpRecord.save();
  return otpRecord;
};

module.exports = {
  createAndSendOtp,
  verifyOtpCode
};

