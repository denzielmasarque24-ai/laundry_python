const express = require("express");
const authRoutes = require("./auth.routes");
const orderRoutes = require("./order.routes");
const { sendSuccess } = require("../utils/response");

const router = express.Router();

router.get("/health", (req, res) => {
  return sendSuccess(res, "FreshWash API is healthy.", {
    uptime: process.uptime()
  });
});

router.use("/auth", authRoutes);
router.use("/orders", orderRoutes);

module.exports = router;

