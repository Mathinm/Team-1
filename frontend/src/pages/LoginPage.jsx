import { useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext.jsx";
import { canOpen, homePathFor } from "../config/roles.js";
import { Banner, Field } from "../components/ui.jsx";
import { USE_MOCK } from "../api/client.js";
import { MOCK_USERS } from "../api/mock/db.js";

export default function LoginPage() {
  const { user, login, notice } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [form, setForm] = useState({ userId: "", password: "", otpCode: "" });
  const [showOtp, setShowOtp] = useState(false);
  const [errors, setErrors] = useState({});
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  if (user) return <Navigate to={homePathFor(user.role)} replace />;

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  async function submit(e) {
    e.preventDefault();
    const errs = {};
    if (!form.userId.trim()) errs.userId = "Enter your user ID";
    if (!form.password) errs.password = "Enter your password";
    setErrors(errs);
    setError("");
    if (Object.keys(errs).length) return;

    setBusy(true);
    try {
      const s = await login(form.userId, form.password, form.otpCode || undefined);
      const from = location.state?.from;
      navigate(from && canOpen(s.role, from) ? from : homePathFor(s.role), { replace: true });
    } catch (err) {
      setError(err.message || "Login failed");
      // 2FA for Manager/Admin (NFR-10): backend asks for the one-time code.
      if (err.code === "OTP_REQUIRED") setShowOtp(true);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login">
      <form className="card login__card" onSubmit={submit} noValidate>
        <div className="login__brand">
          <span className="topbar__brand">PMS</span>
          <h1>Perishables Management System</h1>
          <p className="muted">Sign in to continue</p>
        </div>

        <Banner kind="info">{notice}</Banner>
        <Banner kind="error">{error}</Banner>

        <Field label="User ID" error={errors.userId} id="userId">
          <input id="userId" autoComplete="username" value={form.userId} onChange={set("userId")} autoFocus />
        </Field>
        <Field label="Password" error={errors.password} id="password">
          <input id="password" type="password" autoComplete="current-password" value={form.password} onChange={set("password")} />
        </Field>

        {showOtp ? (
          <Field label="One-time code" hint="Manager and Admin accounts" id="otp">
            <input id="otp" inputMode="numeric" autoComplete="one-time-code" value={form.otpCode} onChange={set("otpCode")} />
          </Field>
        ) : (
          <button type="button" className="link" onClick={() => setShowOtp(true)}>
            I have a one-time code
          </button>
        )}

        <button className="btn btn--primary btn--block" type="submit" disabled={busy}>
          {busy ? "Signing in…" : "Log in"}
        </button>

        {USE_MOCK && (
          <details className="demo-users">
            <summary>Demo accounts</summary>
            <ul>
              {MOCK_USERS.map((u) => (
                <li key={u.userId}>
                  <button
                    type="button"
                    className="link"
                    onClick={() => setForm({ userId: u.userId, password: u.password, otpCode: "" })}
                  >
                    {u.role}: {u.userId} / {u.password}
                  </button>
                </li>
              ))}
            </ul>
          </details>
        )}
      </form>
    </div>
  );
}
