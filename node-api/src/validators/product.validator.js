const { body, param } = require("express-validator");

const productIdValidation = [
  param("id").isUUID().withMessage("Product id must be a UUID.")
];

const createProductValidation = [
  body("name").trim().notEmpty().withMessage("Product name is required."),
  body("price").isFloat({ min: 0 }).withMessage("Price cannot be negative."),
  body("stock").isInt({ min: 0 }).withMessage("Stock cannot be negative."),
  body("description").optional({ nullable: true }).trim(),
  body("imageUrl").optional({ nullable: true, checkFalsy: true }).isURL().withMessage("imageUrl must be a valid URL.")
];

const updateProductValidation = [
  ...productIdValidation,
  body("name").optional().trim().notEmpty().withMessage("Product name cannot be empty."),
  body("price").optional().isFloat({ min: 0 }).withMessage("Price cannot be negative."),
  body("stock").optional().isInt({ min: 0 }).withMessage("Stock cannot be negative."),
  body("description").optional({ nullable: true }).trim(),
  body("imageUrl").optional({ nullable: true, checkFalsy: true }).isURL().withMessage("imageUrl must be a valid URL.")
];

module.exports = {
  createProductValidation,
  updateProductValidation
};
