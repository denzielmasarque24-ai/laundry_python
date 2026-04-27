const { validationResult } = require("express-validator");
const { sendError } = require("../utils/response");

const validateRequest = (req, res, next) => {
  const errors = validationResult(req);
  if (errors.isEmpty()) return next();

  return sendError(res, "Validation failed.", { errors: errors.array() }, 422);
};

module.exports = validateRequest;

