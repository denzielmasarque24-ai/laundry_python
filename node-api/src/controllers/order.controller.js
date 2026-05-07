const { Order, Product, sequelize } = require("../models");
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

const formatProductStatus = (stock) => (Number(stock || 0) > 0 ? "In Stock" : "Out of Stock");

const serializeProduct = (product) => {
  if (!product) return null;
  const plain = typeof product.toJSON === "function" ? product.toJSON() : product;
  const stock = Number(plain.stock || 0);
  return {
    ...plain,
    stock,
    status: stock > 0 ? "in_stock" : "out_of_stock",
    stockStatus: formatProductStatus(stock),
    isAvailable: stock > 0
  };
};

const createProductOrder = async (req) => {
  const productId = req.body.productId;
  const quantity = Number.parseInt(req.body.quantity || 1, 10);
  if (!Number.isInteger(quantity) || quantity < 1) {
    throw new ApiError(400, "Quantity must be at least 1.");
  }

  return sequelize.transaction(async (transaction) => {
    const product = await Product.findByPk(productId, {
      transaction,
      lock: transaction.LOCK.UPDATE
    });

    if (!product) throw new ApiError(404, "Product not found.");

    const currentStock = Number(product.stock || 0);
    if (currentStock <= 0) {
      throw new ApiError(400, "This product is out of stock.", {
        productId,
        stock: currentStock,
        stockStatus: "Out of Stock"
      });
    }

    if (quantity > currentStock) {
      throw new ApiError(400, `Only ${currentStock} item${currentStock === 1 ? "" : "s"} available.`, {
        productId,
        requestedQuantity: quantity,
        stock: currentStock
      });
    }

    const unitPrice = Number(product.price || 0);
    const totalPrice = Number((unitPrice * quantity).toFixed(2));
    const newStock = currentStock - quantity;

    const order = await Order.create(
      {
        userId: req.user.id,
        productId: product.id,
        quantity,
        unitPrice,
        serviceType: product.name,
        pickupAddress: req.body.pickupAddress || null,
        pickupDate: req.body.pickupDate || null,
        deliveryDate: req.body.deliveryDate || null,
        deliveryOption: req.body.deliveryOption || "pickup",
        totalPrice
      },
      { transaction }
    );

    await product.update(
      {
        stock: newStock,
        status: newStock > 0 ? "in_stock" : "out_of_stock"
      },
      { transaction }
    );

    return { order, product: serializeProduct(product), previousStock: currentStock, newStock };
  });
};

const createOrder = async (req, res, next) => {
  try {
    if (req.body.productId) {
      const result = await createProductOrder(req);
      return sendSuccess(res, "Order created successfully.", result, 201);
    }

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
      include: [{ model: Product, as: "product" }],
      order: [["createdAt", "DESC"]]
    });
    return sendSuccess(res, "Orders fetched successfully.", { orders });
  } catch (error) {
    return next(error);
  }
};

const listAllOrders = async (req, res, next) => {
  try {
    const orders = await Order.findAll({
      include: [{ model: Product, as: "product" }],
      order: [["createdAt", "DESC"]]
    });
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
