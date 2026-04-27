const express = require("express");
const validateRequest = require("../middleware/validate.middleware");
const { requireAuth, requireAdmin } = require("../middleware/auth.middleware");
const {
  createOrderValidation,
  updateOrderStatusValidation
} = require("../validators/order.validator");
const {
  createOrder,
  listMyOrders,
  listAllOrders,
  updateOrderStatus
} = require("../controllers/order.controller");

const router = express.Router();

router.post("/", requireAuth, createOrderValidation, validateRequest, createOrder);
router.get("/me", requireAuth, listMyOrders);
router.get("/", requireAuth, requireAdmin, listAllOrders);
router.patch(
  "/:id/status",
  requireAuth,
  requireAdmin,
  updateOrderStatusValidation,
  validateRequest,
  updateOrderStatus
);

module.exports = router;
