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
    productId: {
      type: DataTypes.UUID,
      allowNull: true
    },
    quantity: {
      type: DataTypes.INTEGER.UNSIGNED,
      allowNull: false,
      defaultValue: 1,
      validate: {
        min: 1
      }
    },
    unitPrice: {
      type: DataTypes.DECIMAL(10, 2),
      allowNull: true
    },
    serviceType: {
      type: DataTypes.STRING(120),
      allowNull: true
    },
    weightKg: {
      type: DataTypes.DECIMAL(10, 2),
      allowNull: true
    },
    pickupAddress: {
      type: DataTypes.STRING(255),
      allowNull: true
    },
    pickupDate: {
      type: DataTypes.DATEONLY,
      allowNull: true
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
