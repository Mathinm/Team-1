import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api/endpoints.js";
import { Banner, Field } from "../components/ui.jsx";
import "./products-login.css";

/** Same split layout as the login screen. */
function AuthShell({ title, lead, children, back = true }) {
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
        <div className="login__card login-v2__card">
          <div className="login-v2__brand">
            <span className="login-v2__mark" aria-hidden="true">🌿</span>
            <span>Perishables Management System</span>
          </div>
          <h1 className="login-v2__title">{title}</h1>
          <p className="muted login-v2__lead">{lead}</p>
          {children}
          {back && <p className="login-v2__forgot"><Link to="/login">Back to log in</Link></p>}
        </div>
      </div>
    </div>
  );
}

/** SEC-5 step 1: ask for a reset link by user ID. The answer never says whether the ID exists. */
export function ForgotPasswordPage() {
  const [userId, setUserId] = useState("");
  const [fieldError, setFieldError] = useState("");
  const [error, setError] = useState("");
  const [sent, setSent] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setError("");
    if (!userId.trim()) return setFieldError("Enter your user ID");
    setFieldError("");
    setBusy(true);
    try {
      const res = await api.requestPasswordReset(userId.trim());
      setSent(res?.message || "If that user ID exists, a reset link has been sent to its registered email.");
    } catch (ex) {
      setError(ex.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthShell title="Forgot your password?" lead="Enter your user ID and we'll email you a link to set a new one.">
      <Banner kind="error">{error}</Banner>
      {sent ? (
        <Banner kind="success">{sent} The link works for 30 minutes.</Banner>
      ) : (
        <form onSubmit={submit} noValidate>
          <Field label="User ID" error={fieldError} id="fp-user">
            <input id="fp-user" autoComplete="username" value={userId} onChange={(e) => setUserId(e.target.value)} autoFocus />
          </Field>
          <button className="btn btn--primary btn--block" type="submit" disabled={busy}>
            {busy ? "Sending…" : "Email me a reset link"}
          </button>
        </form>
      )}
    </AuthShell>
  );
}

/** SEC-5 step 2: the emailed link opens /reset-password?token=... to choose a new password. */
export function ResetPasswordPage() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const [form, setForm] = useState({ password: "", confirm: "" });
  const [errors, setErrors] = useState({});
  const [error, setError] = useState("");
  const [done, setDone] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  async function submit(e) {
    e.preventDefault();
    const errs = {};
    if (form.password.length < 8) errs.password = "At least 8 characters";
    if (form.confirm !== form.password) errs.confirm = "The passwords don't match";
    setErrors(errs);
    setError("");
    if (Object.keys(errs).length) return;
    setBusy(true);
    try {
      const res = await api.confirmPasswordReset(token, form.password);
      setDone(res?.message || "Your password has been changed. Log in with the new password.");
    } catch (ex) {
      setError(ex.message);
    } finally {
      setBusy(false);
    }
  }

  if (!token) {
    return (
      <AuthShell title="Reset link missing" lead="Open the link from the email again, or ask for a new one.">
        <Link className="btn btn--primary btn--block" to="/forgot-password">Ask for a new link</Link>
      </AuthShell>
    );
  }

  return (
    <AuthShell title="Choose a new password" lead="Use at least 8 characters. Other devices are logged out." back={!done}>
      <Banner kind="error">{error}</Banner>
      {done ? (
        <>
          <Banner kind="success">{done}</Banner>
          <Link className="btn btn--primary btn--block" to="/login">Go to log in</Link>
        </>
      ) : (
        <form onSubmit={submit} noValidate>
          <Field label="New password" error={errors.password} id="rp-pw">
            <input id="rp-pw" type="password" autoComplete="new-password" value={form.password} onChange={set("password")} autoFocus />
          </Field>
          <Field label="Repeat new password" error={errors.confirm} id="rp-pw2">
            <input id="rp-pw2" type="password" autoComplete="new-password" value={form.confirm} onChange={set("confirm")} />
          </Field>
          <button className="btn btn--primary btn--block" type="submit" disabled={busy}>
            {busy ? "Saving…" : "Set new password"}
          </button>
        </form>
      )}
    </AuthShell>
  );
}
