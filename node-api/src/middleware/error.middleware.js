const { sendError } = require("../utils/response");

const errorHandler = (err, req, res, next) => {
  const statusCode = err.statusCode || 500;
  const message = err.message || "Internal server error.";
  const details = err.details || {};

  // Keep stack logs server-side only.
  console.error("API ERROR:", {
    path: req.path,
    method: req.method,
    message: err.message,
    stack: err.stack
  });

  return sendError(res, message, details, statusCode);
};

module.exports = errorHandler;

