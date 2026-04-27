const { DataTypes } = require("sequelize");
const sequelize = require("../config/database");

const Order = sequelize.define(
  "Order",
  {
    id: {
      type: DataTypes.UUID,
      defaultValue: DataTypes.UUIDV4,
      primaryKey: true
    },
    userId: {
      type: DataTypes.UUID,
      allowNull: false
    },
    serviceType: {
      type: DataTypes.STRING(120),
      allowNull: false
    },
    weightKg: {
      type: DataTypes.DECIMAL(10, 2),
      allowNull: false
    },
    pickupAddress: {
      type: DataTypes.STRING(255),
      allowNull: false
    },
    pickupDate: {
      type: DataTypes.DATEONLY,
      allowNull: false
    },
    deliveryDate: {
      type: DataTypes.DATEONLY,
      allowNull: true
    },
    deliveryOption: {
      type: DataTypes.ENUM("pickup", "delivery"),
      allowNull: false,
      defaultValue: "pickup"
    },
    status: {
      type: DataTypes.ENUM("pending", "confirmed", "in_progress", "completed", "cancelled"),
      allowNull: false,
      defaultValue: "pending"
    },
    totalPrice: {
      type: DataTypes.DECIMAL(10, 2),
      allowNull: false
    }
  },
  {
    tableName: "orders",
    underscored: true
  }
);

module.exports = Order;

