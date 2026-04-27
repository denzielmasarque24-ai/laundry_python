const sequelize = require("../config/database");
const User = require("./user.model");
const Otp = require("./otp.model");
const Order = require("./order.model");

User.hasMany(Otp, { foreignKey: "userId", as: "otps" });
Otp.belongsTo(User, { foreignKey: "userId", as: "user" });

User.hasMany(Order, { foreignKey: "userId", as: "orders" });
Order.belongsTo(User, { foreignKey: "userId", as: "user" });

module.exports = {
  sequelize,
  User,
  Otp,
  Order
};

