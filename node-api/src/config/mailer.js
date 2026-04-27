const nodemailer = require("nodemailer");
const env = require("./env");

const transporter = nodemailer.createTransport({
  host: env.mail.server,
  port: env.mail.port,
  secure: env.mail.useSsl,
  auth: {
    user: env.mail.user,
    pass: env.mail.pass
  },
  tls: env.mail.useTls ? { rejectUnauthorized: false } : undefined
});

module.exports = transporter;

