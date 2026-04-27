const { DataTypes } = require("sequelize");
const sequelize = require("../config/database");

const Otp = sequelize.define(
  "Otp",
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
    purpose: {
      type: DataTypes.ENUM("register", "login"),
      allowNull: false
    },
    codeHash: {
      type: DataTypes.STRING(255),
      allowNull: false
    },
    expiresAt: {
      type: DataTypes.DATE,
      allowNull: false
    },
    attemptsLeft: {
      type: DataTypes.INTEGER,
      allowNull: false,
      defaultValue: 3
    },
    consumedAt: {
      type: DataTypes.DATE,
      allowNull: true
    }
  },
  {
    tableName: "otps",
    underscored: true
  }
);

module.exports = Otp;

