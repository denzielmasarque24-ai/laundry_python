const { body, param } = require("express-validator");

const createOrderValidation = [
  body().custom((value) => {
    if (value.productId) return true;
    if (value.serviceType && value.weightKg && value.pickupAddress && value.pickupDate) return true;
    throw new Error("Either productId or service order details are required.");
  }),
  body("productId")
    .optional({ nullable: true, checkFalsy: true })
    .isUUID()
    .withMessage("productId must be a UUID."),
  body("quantity")
    .optional({ nullable: true })
    .isInt({ min: 1 })
    .withMessage("quantity must be at least 1."),
  body("serviceType").optional({ nullable: true, checkFalsy: true }).trim(),
  body("weightKg").optional({ nullable: true, checkFalsy: true }).isFloat({ gt: 0 }).withMessage("weightKg must be greater than 0."),
  body("pickupAddress")
    .optional({ nullable: true, checkFalsy: true })
    .trim()
    .notEmpty()
    .withMessage("pickupAddress is required."),
  body("pickupDate")
    .optional({ nullable: true, checkFalsy: true })
    .isISO8601()
    .withMessage("pickupDate must be a valid date."),
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
