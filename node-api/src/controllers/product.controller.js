const { Product } = require("../models");
const { sendSuccess } = require("../utils/response");
const ApiError = require("../utils/apiError");

const formatProduct = (product) => {
  const plain = typeof product.toJSON === "function" ? product.toJSON() : product;
  const stock = Number(plain.stock || 0);
  return {
    ...plain,
    stock,
    status: stock > 0 ? "in_stock" : "out_of_stock",
    stockStatus: stock > 0 ? "In Stock" : "Out of Stock",
    isAvailable: stock > 0
  };
};

const listProducts = async (req, res, next) => {
  try {
    const products = await Product.findAll({ order: [["name", "ASC"]] });
    return sendSuccess(res, "Products fetched successfully.", {
      products: products.map(formatProduct)
    });
  } catch (error) {
    return next(error);
  }
};

const createProduct = async (req, res, next) => {
  try {
    const stock = Number.parseInt(req.body.stock || 0, 10);
    if (!Number.isInteger(stock) || stock < 0) throw new ApiError(400, "Stock cannot be negative.");

    const product = await Product.create({
      name: req.body.name,
      description: req.body.description || null,
      price: req.body.price,
      stock,
      status: stock > 0 ? "in_stock" : "out_of_stock",
      imageUrl: req.body.imageUrl || null
    });

    return sendSuccess(res, "Product created successfully.", { product: formatProduct(product) }, 201);
  } catch (error) {
    return next(error);
  }
};

const updateProduct = async (req, res, next) => {
  try {
    const product = await Product.findByPk(req.params.id);
    if (!product) throw new ApiError(404, "Product not found.");

    const payload = {};
    for (const field of ["name", "description", "price", "imageUrl"]) {
      if (Object.prototype.hasOwnProperty.call(req.body, field)) payload[field] = req.body[field];
    }
    if (Object.prototype.hasOwnProperty.call(req.body, "stock")) {
      const stock = Number.parseInt(req.body.stock, 10);
      if (!Number.isInteger(stock) || stock < 0) throw new ApiError(400, "Stock cannot be negative.");
      payload.stock = stock;
      payload.status = stock > 0 ? "in_stock" : "out_of_stock";
    }

    await product.update(payload);
    return sendSuccess(res, "Product updated successfully.", { product: formatProduct(product) });
  } catch (error) {
    return next(error);
  }
};

module.exports = {
  listProducts,
  createProduct,
  updateProduct
};
