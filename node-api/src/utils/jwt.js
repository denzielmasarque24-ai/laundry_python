const jwt = require("jsonwebtoken");
const env = require("../config/env");
const ApiError = require("./apiError");

const signAccessToken = (payload) => {
  if (!env.jwt.secret) {
    throw new ApiError(500, "Server JWT configuration is missing.");
  }
  return jwt.sign(payload, env.jwt.secret, { expiresIn: env.jwt.expiresIn });
};

const verifyAccessToken = (token) => {
  if (!env.jwt.secret) {
    throw new ApiError(500, "Server JWT configuration is missing.");
  }
  return jwt.verify(token, env.jwt.secret);
};

module.exports = {
  signAccessToken,
  verifyAccessToken
};

