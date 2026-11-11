import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider, useAuth } from "./auth/AuthContext.jsx";
import { homePathFor } from "./config/roles.js";
import Layout from "./components/Layout.jsx";
import RequireRole from "./components/RequireRole.jsx";
import LoginPage from "./pages/LoginPage.jsx";
import { ForgotPasswordPage, ResetPasswordPage } from "./pages/PasswordResetPages.jsx";
import ProductsPage from "./pages/ProductsPage.jsx";
import StockPage from "./pages/StockPage.jsx";
import StockCountPage from "./pages/StockCountPage.jsx";
import RemovalsPage from "./pages/RemovalsPage.jsx";
import MarkdownsPage from "./pages/MarkdownsPage.jsx";
import SalesPage from "./pages/SalesPage.jsx";
import DashboardPage from "./pages/DashboardPage.jsx";
import ReportsPage from "./pages/ReportsPage.jsx";
import AlertsPage from "./pages/AlertsPage.jsx";
import RefrigerationPage from "./pages/RefrigerationPage.jsx";
import UsersPage from "./pages/UsersPage.jsx";

function AppRoutes() {
  const { user } = useAuth();
  const guard = (page) => <RequireRole>{page}</RequireRole>;

  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/reset-password" element={<ResetPasswordPage />} />
      <Route element={user ? <Layout /> : <Navigate to="/login" replace />}>
        <Route path="/dashboard" element={guard(<DashboardPage />)} />
        <Route path="/products" element={guard(<ProductsPage />)} />
        <Route path="/stock" element={guard(<StockPage />)} />
        <Route path="/stock-count" element={guard(<StockCountPage />)} />
        <Route path="/removals" element={guard(<RemovalsPage />)} />
        <Route path="/markdowns" element={guard(<MarkdownsPage />)} />
        <Route path="/sales" element={guard(<SalesPage />)} />
        <Route path="/alerts" element={guard(<AlertsPage />)} />
        <Route path="/refrigeration" element={guard(<RefrigerationPage />)} />
        <Route path="/reports" element={guard(<ReportsPage />)} />
        <Route path="/users" element={guard(<UsersPage />)} />
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
