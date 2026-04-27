const app = require("../app");
const env = require("./config/env");
const { sequelize } = require("./models");

const start = async () => {
  try {
    await sequelize.authenticate();
    console.log("DB connected.");

    if (env.db.sync) {
      // Enable this only in controlled environments.
      await sequelize.sync({ alter: true });
      console.log("DB synced.");
    }

    app.listen(env.port, () => {
      console.log(`FreshWash Node API running on port ${env.port}`);
    });
  } catch (error) {
    console.error("Server startup failed:", error);
    process.exit(1);
  }
};

start();
