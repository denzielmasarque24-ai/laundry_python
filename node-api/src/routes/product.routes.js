const express = require("express");
const validateRequest = require("../middleware/validate.middleware");
const { requireAuth, requireAdmin } = require("../middleware/auth.middleware");
const {
  createProductValidation,
  updateProductValidation
} = require("../validators/product.validator");
const {
  listProducts,
  createProduct,
  updateProduct
} = require("../controllers/product.controller");

const router = express.Router();

router.get("/", listProducts);
router.post("/", requireAuth, requireAdmin, createProductValidation, validateRequest, createProduct);
router.patch("/:id", requireAuth, requireAdmin, updateProductValidation, validateRequest, updateProduct);

module.exports = router;
