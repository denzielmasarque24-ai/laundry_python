const express = require("express");
const env = require("./config/env");
const routes = require("./routes");
const otpAuthRoutes = require("./routes/auth");
const errorHandler = require("./middleware/error.middleware");
const { sendError } = require("./utils/response");

const app = express();

app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// OTP auth endpoints requested as absolute routes:
// POST /auth/send-otp
// POST /auth/verify-otp
app.use(otpAuthRoutes);

app.use(env.apiPrefix, routes);

app.use((req, res) => {
  return sendError(res, "Route not found.", { path: req.originalUrl }, 404);
});

app.use(errorHandler);

module.exports = app;
