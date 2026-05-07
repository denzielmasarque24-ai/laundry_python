const express = require("express");
const authRoutes = require("./auth.routes");
const orderRoutes = require("./order.routes");
const productRoutes = require("./product.routes");
const { sendSuccess } = require("../utils/response");

const router = express.Router();

router.get("/health", (req, res) => {
  return sendSuccess(res, "FreshWash API is healthy.", {
    uptime: process.uptime()
  });
});

router.use("/auth", authRoutes);
router.use("/products", productRoutes);
router.use("/orders", orderRoutes);

module.exports = router;
