const { DataTypes } = require("sequelize");
const sequelize = require("../config/database");

const Product = sequelize.define(
  "Product",
  {
    id: {
      type: DataTypes.UUID,
      defaultValue: DataTypes.UUIDV4,
      primaryKey: true
    },
    name: {
      type: DataTypes.STRING(160),
      allowNull: false
    },
    description: {
      type: DataTypes.TEXT,
      allowNull: true
    },
    price: {
      type: DataTypes.DECIMAL(10, 2),
      allowNull: false,
      defaultValue: 0
    },
    stock: {
      type: DataTypes.INTEGER.UNSIGNED,
      allowNull: false,
      defaultValue: 0,
      validate: {
        min: 0
      }
    },
    status: {
      type: DataTypes.ENUM("in_stock", "out_of_stock"),
      allowNull: false,
      defaultValue: "in_stock"
    },
    imageUrl: {
      type: DataTypes.STRING(500),
      allowNull: true
    }
  },
  {
    tableName: "products",
    underscored: true,
    hooks: {
      beforeValidate(product) {
        product.status = Number(product.stock || 0) > 0 ? "in_stock" : "out_of_stock";
      }
    }
  }
);

module.exports = Product;
