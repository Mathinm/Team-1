// One function per backend endpoint. Paths and bodies follow SAD 4.3; the
// extra list endpoints the UI needs are documented in docs/frontend-api-contract.md.

import { request } from "./client.js";

export const api = {
  // Auth (SEC-1)
  login: (userId, password, otpCode) =>
    request("POST", "/auth/login", { userId, password, ...(otpCode ? { otpCode } : {}) }),
  logout: () => request("POST", "/auth/logout"),
  me: () => request("GET", "/auth/me"),

  // Master data (FR-1)
  listProducts: () => request("GET", "/products"),
  createProduct: (body) => request("POST", "/products", body),
  updateProduct: (id, body) => request("PUT", `/products/${id}`, body),
  deactivateProduct: (id) => request("PATCH", `/products/${id}/deactivate`),
  activateProduct: (id) => request("PATCH", `/products/${id}/activate`),
  listSuppliers: () => request("GET", "/suppliers"),

  // Stock (FR-2, FR-4, FR-5, FR-6)
  receiveBatch: (body) => request("POST", "/batches", body),
  restock: (body) => request("POST", "/restocks", body),
  fefo: (productId) => request("GET", `/batches/fefo?productId=${productId}`),

  // Sales (FR-3, FR-7, FR-8)
  recordSale: (body) => request("POST", "/sales", body),
  uploadSalesCsv: (file) => {
    const form = new FormData();
    form.append("file", file);
    return request("POST", "/sales/csv", form);
  },
};
