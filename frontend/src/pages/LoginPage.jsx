import { useState } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext.jsx";
import { canOpen, homePathFor } from "../config/roles.js";
import { Banner, Field } from "../components/ui.jsx";
import { USE_MOCK } from "../api/client.js";
import { MOCK_USERS } from "../api/mock/db.js";
import "./products-login.css";

export default function LoginPage() {
  const { user, login, notice } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [form, setForm] = useState({ userId: "", password: "", otpCode: "" });
  const [showOtp, setShowOtp] = useState(false);
  const [errors, setErrors] = useState({});
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");
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
    setInfo("");
    if (Object.keys(errs).length) return;

    setBusy(true);
    try {
      const s = await login(form.userId, form.password, form.otpCode || undefined);
      const from = location.state?.from;
      navigate(from && canOpen(s.role, from) ? from : homePathFor(s.role), { replace: true });
    } catch (err) {
      // T4: 2FA one-time code notice is informational, not an error.
      if (err.code === "OTP_REQUIRED") {
        setShowOtp(true);
        setError("");
        setInfo(err.message || "We emailed a login code to your address. Enter it below.");
      } else {
        setError(err.message || "Login failed");
        setInfo("");
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login login-v2">
      <aside className="login-v2__photo" aria-hidden="true">
        <div className="login-v2__caption">
          <span className="login-v2__logo">PMS</span>
          <h2>Freshness deserves better management.</h2>
          <p>Track inventory. Reduce waste. Keep every product moving.</p>
        </div>
      </aside>
      <div className="login-v2__side">
      <form className="login__card login-v2__card" onSubmit={submit} noValidate>
        <div className="login-v2__brand">
          <span className="login-v2__mark" aria-hidden="true">🌿</span>
          <span>Perishables Management System</span>
        </div>
        <h1 className="login-v2__title">Hello,<br />welcome back</h1>
        <p className="muted login-v2__lead">Sign in to manage your store&apos;s fresh stock.</p>

        <Banner kind="info">{notice || info}</Banner>
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
        <p className="login-v2__forgot">
          <Link to="/forgot-password">Forgot your password?</Link>
        </p>

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
    </div>
  );
}
