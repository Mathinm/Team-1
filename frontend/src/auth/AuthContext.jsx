import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api } from "../api/endpoints.js";
import { getToken, setToken, setUnauthorizedHandler } from "../api/client.js";

const SESSION_KEY = "pms.session";
const AuthContext = createContext(null);

function loadSession() {
  if (!getToken()) return null;
  try {
    return JSON.parse(localStorage.getItem(SESSION_KEY) || "null");
  } catch {
    return null;
  }
}

function saveSession(session) {
  try {
    if (session) localStorage.setItem(SESSION_KEY, JSON.stringify(session));
    else localStorage.removeItem(SESSION_KEY);
  } catch {
    /* ignore */
  }
}

export function AuthProvider({ children }) {
  const [session, setSession] = useState(loadSession);
  const [notice, setNotice] = useState("");

  const clear = useCallback((message = "") => {
    setToken(null);
    saveSession(null);
    setSession(null);
    setNotice(message);
  }, []);

  // Any 401 from the API ends the session (expired token, idle logout - SEC-3).
  useEffect(() => {
    setUnauthorizedHandler(() => clear("Your session has ended. Please log in again."));
  }, [clear]);

  const login = useCallback(async (userId, password, otpCode) => {
    const res = await api.login(userId.trim(), password, otpCode);
    setToken(res.token);
    const s = { userId: res.userId ?? userId.trim(), name: res.name ?? userId.trim(), role: res.role };
    saveSession(s);
    setSession(s);
    setNotice("");
    return s;
  }, []);

  const logout = useCallback(async () => {
    try {
      await api.logout();
    } catch {
      /* logging out locally is enough */
    }
    clear();
  }, [clear]);

  const value = useMemo(
    () => ({ user: session, login, logout, notice }),
    [session, login, logout, notice],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  return useContext(AuthContext);
}
