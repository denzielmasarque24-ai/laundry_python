const { verifyAccessToken } = require("../utils/jwt");
const { User } = require("../models");
const { sendError } = require("../utils/response");

const requireAuth = async (req, res, next) => {
  try {
    const authHeader = req.headers.authorization || "";
    if (!authHeader.startsWith("Bearer ")) {
      return sendError(res, "Authentication required.", {}, 401);
    }

    const token = authHeader.slice(7);
    const payload = verifyAccessToken(token);
    const user = await User.findByPk(payload.sub);

    if (!user) return sendError(res, "Invalid session.", {}, 401);

    req.user = user;
    return next();
  } catch (error) {
    return sendError(res, "Invalid or expired token.", {}, 401);
  }
};

const requireAdmin = async (req, res, next) => {
  if (!req.user || req.user.role !== "admin") {
    return sendError(res, "Admin access required.", {}, 403);
  }
  return next();
};

module.exports = {
  requireAuth,
  requireAdmin
};

