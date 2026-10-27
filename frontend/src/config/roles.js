// Role-based access (SEC-2). One place that decides which screens and actions
// each role gets. The backend must enforce the same rules (403 on violation).

export const ROLES = {
  ADMIN: "Admin",
  MANAGER: "Manager",
  STAFF: "Inventory Staff",
  CASHIER: "Cashier",
};

const { ADMIN, MANAGER, STAFF, CASHIER } = ROLES;

// Menu entries in display order. `roles` = who sees the entry.
export const MENU = [
  { path: "/products", label: "Products", roles: [ADMIN, MANAGER, STAFF] },
  { path: "/stock", label: "Stock & FEFO", roles: [ADMIN, MANAGER, STAFF] },
  { path: "/sales", label: "Sales", roles: [ADMIN, CASHIER] },
];

// Actions inside screens.
export const PERMISSIONS = {
  editProducts: [ADMIN, MANAGER],
  manageSuppliers: [ADMIN, MANAGER],
  receiveBatch: [ADMIN, MANAGER, STAFF],
  recordSale: [ADMIN, CASHIER],
};

export function can(role, permission) {
  return Boolean(role && PERMISSIONS[permission]?.includes(role));
}

export function menuFor(role) {
  return MENU.filter((m) => m.roles.includes(role));
}

export function canOpen(role, path) {
  return menuFor(role).some((m) => path.startsWith(m.path));
}

export function homePathFor(role) {
  return menuFor(role)[0]?.path ?? "/login";
}
