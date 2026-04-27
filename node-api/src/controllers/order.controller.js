const { Order } = require("../models");
const { sendSuccess } = require("../utils/response");
const ApiError = require("../utils/apiError");

const SERVICE_PRICING = {
  "Wash & Fold": 150,
  "Wash & Iron": 200,
  "Dry Cleaning": 250,
  "Premium Wash": 350
};

const calculatePrice = (serviceType, weightKg) => {
  const pricePerKg = SERVICE_PRICING[serviceType];
  if (!pricePerKg) throw new ApiError(400, "Unsupported serviceType.");
  return Number((pricePerKg * Number(weightKg)).toFixed(2));
};

const createOrder = async (req, res, next) => {
  try {
    const {
      serviceType,
      weightKg,
      pickupAddress,
      pickupDate,
      deliveryDate,
      deliveryOption = "pickup"
    } = req.body;

    const totalPrice = calculatePrice(serviceType, weightKg);
    const order = await Order.create({
      userId: req.user.id,
      serviceType,
      weightKg,
      pickupAddress,
      pickupDate,
      deliveryDate: deliveryDate || null,
      deliveryOption,
      totalPrice
    });

    return sendSuccess(res, "Order created successfully.", { order }, 201);
  } catch (error) {
    return next(error);
  }
};

const listMyOrders = async (req, res, next) => {
  try {
    const orders = await Order.findAll({
      where: { userId: req.user.id },
      order: [["createdAt", "DESC"]]
    });
    return sendSuccess(res, "Orders fetched successfully.", { orders });
  } catch (error) {
    return next(error);
  }
};

const listAllOrders = async (req, res, next) => {
  try {
    const orders = await Order.findAll({ order: [["createdAt", "DESC"]] });
    return sendSuccess(res, "All orders fetched successfully.", { orders });
  } catch (error) {
    return next(error);
  }
};

const updateOrderStatus = async (req, res, next) => {
  try {
    const { id } = req.params;
    const { status } = req.body;
    const order = await Order.findByPk(id);
    if (!order) throw new ApiError(404, "Order not found.");

    order.status = status;
    await order.save();
    return sendSuccess(res, "Order status updated successfully.", { order });
  } catch (error) {
    return next(error);
  }
};

module.exports = {
  createOrder,
  listMyOrders,
  listAllOrders,
  updateOrderStatus
};

