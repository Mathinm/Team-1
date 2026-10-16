import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../auth/AuthContext.jsx";
import { canOpen } from "../config/roles.js";

/** Redirects to login when signed out; shows "no access" when the role can't open the page. */
export default function RequireRole({ children }) {
  const { user } = useAuth();
  const location = useLocation();

  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  if (!canOpen(user.role, location.pathname)) {
    return (
      <section className="card">
        <h1>No access</h1>
        <p>Your role ({user.role}) can't open this page.</p>
      </section>
    );
  }
  return children;
}
