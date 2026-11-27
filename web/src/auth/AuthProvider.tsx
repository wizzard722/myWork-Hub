import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, refreshSession, type Session } from "../api";

type AuthState =
  | { status: "loading" }
  | { status: "anonymous" }
  | { status: "authenticated"; session: Session };

interface AuthContextValue {
  state: AuthState;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({ status: "loading" });

  useEffect(() => {
    // Bestaande sessie hervatten via de refresh-cookie.
    refreshSession().then((session) =>
      setState(session ? { status: "authenticated", session } : { status: "anonymous" }),
    );
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const session = await api.login(email, password);
    setState({ status: "authenticated", session });
  }, []);

  const logout = useCallback(async () => {
    await api.logout();
    setState({ status: "anonymous" });
  }, []);

  return <AuthContext.Provider value={{ state, login, logout }}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth buiten AuthProvider");
  return value;
}
