const sendSuccess = (res, message, data = {}, status = 200) => {
  return res.status(status).json({
    success: true,
    message,
    data
  });
};

const sendError = (res, message, data = {}, status = 400) => {
  return res.status(status).json({
    success: false,
    message,
    data
  });
};

module.exports = {
  sendSuccess,
  sendError
};

