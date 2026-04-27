const express = require("express");
const dotenv = require("dotenv");

dotenv.config();

const app = express();

app.use(express.json());
app.use(express.urlencoded({ extended: true }));

app.use("/auth", require("./routes/auth"));

// Consistent fallback response contract.
app.use((req, res) => {
  return res.status(404).json({
    success: false,
    message: "Route not found.",
    data: {}
  });
});

module.exports = app;

