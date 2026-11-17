import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { api, permisos, session, type UsuarioOut } from "../api/client";

/**
 * Proveedor de identidad del prototipo: usuario/contraseña locales con JWT.
 * Para producción (Microsoft Entra ID) se reemplaza `login`/`logout` por MSAL
 * manteniendo esta misma interfaz (`AuthValue`); el resto de la app no cambia.
 */
export interface AuthValue {
  user: UsuarioOut | null;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  puede: {
    maestros: boolean;
    presupuesto: boolean;
    aprobacion: boolean;
    control: boolean;
  };
}

const AuthCtx = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UsuarioOut | null>(() => (session.getToken() ? session.getUser() : null));
  const navigate = useNavigate();
  const qc = useQueryClient();

  const logout = useCallback(() => {
    session.clear();
    setUser(null);
    qc.clear();
    navigate("/login", { replace: true });
  }, [navigate, qc]);

  useEffect(() => {
    session.onUnauthorized(() => {
      setUser(null);
      qc.clear();
      navigate("/login", { replace: true });
    });
    return () => session.onUnauthorized(null);
  }, [navigate, qc]);

  const login = useCallback(async (username: string, password: string) => {
    const res = await api.auth.login(username, password);
    session.set(res.access_token, res.user);
    setUser(res.user);
  }, []);

  const value = useMemo<AuthValue>(
    () => ({
      user,
      login,
      logout,
      puede: {
        maestros: permisos.maestros(user?.rol),
        presupuesto: permisos.presupuesto(user?.rol),
        aprobacion: permisos.aprobacion(user?.rol),
        control: permisos.control(user?.rol),
      },
    }),
    [user, login, logout],
  );
  return <AuthCtx.Provider value={value}>{children}</AuthCtx.Provider>;
}

export function useAuth(): AuthValue {
  const v = useContext(AuthCtx);
  if (!v) throw new Error("useAuth fuera de AuthProvider");
  return v;
}
