const { body, param } = require("express-validator");

const createOrderValidation = [
  body("serviceType").trim().notEmpty().withMessage("serviceType is required."),
  body("weightKg").isFloat({ gt: 0 }).withMessage("weightKg must be greater than 0."),
  body("pickupAddress").trim().notEmpty().withMessage("pickupAddress is required."),
  body("pickupDate").isISO8601().withMessage("pickupDate must be a valid date."),
  body("deliveryDate").optional({ nullable: true }).isISO8601().withMessage("deliveryDate must be a valid date."),
  body("deliveryOption")
    .optional()
    .isIn(["pickup", "delivery"])
    .withMessage("deliveryOption must be pickup or delivery.")
];

const updateOrderStatusValidation = [
  param("id").isUUID().withMessage("Order id must be a UUID."),
  body("status")
    .isIn(["pending", "confirmed", "in_progress", "completed", "cancelled"])
    .withMessage("Invalid status.")
];

module.exports = {
  createOrderValidation,
  updateOrderStatusValidation
};

