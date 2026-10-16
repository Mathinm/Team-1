import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider, useAuth } from "./auth/AuthContext.jsx";
import { homePathFor } from "./config/roles.js";
import Layout from "./components/Layout.jsx";
import RequireRole from "./components/RequireRole.jsx";
import LoginPage from "./pages/LoginPage.jsx";
import ProductsPage from "./pages/ProductsPage.jsx";
import StockPage from "./pages/StockPage.jsx";
import SalesPage from "./pages/SalesPage.jsx";

function AppRoutes() {
  const { user } = useAuth();
  const guard = (page) => <RequireRole>{page}</RequireRole>;

  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={user ? <Layout /> : <Navigate to="/login" replace />}>
        <Route path="/products" element={guard(<ProductsPage />)} />
        <Route path="/stock" element={guard(<StockPage />)} />
        <Route path="/sales" element={guard(<SalesPage />)} />
      </Route>
      <Route path="*" element={<Navigate to={user ? homePathFor(user.role) : "/login"} replace />} />
    </Routes>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  );
}
