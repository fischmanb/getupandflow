import { createContext, useContext, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { apiClient } from "../api/client";
import { clearTokens, getAccessToken, getStoredUser, setStoredUser, setTokens } from "./storage";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const navigate = useNavigate();
  const [user, setUser] = useState(getStoredUser());
  const [isBootstrapping, setIsBootstrapping] = useState(Boolean(getAccessToken()));

  useEffect(() => {
    async function bootstrapSession() {
      if (!getAccessToken()) {
        setIsBootstrapping(false);
        return;
      }

      try {
        const response = await apiClient.get("/auth/me/");
        setUser(response.data);
        setStoredUser(response.data);
      } catch (error) {
        clearTokens();
        setUser(null);
        navigate("/login", { replace: true });
      } finally {
        setIsBootstrapping(false);
      }
    }

    bootstrapSession();
  }, [navigate]);

  useEffect(() => {
    function handleSessionExpiry() {
      setUser(null);
      navigate("/login", { replace: true });
    }

    window.addEventListener("auth:expired", handleSessionExpiry);
    return () => window.removeEventListener("auth:expired", handleSessionExpiry);
  }, [navigate]);

  const value = {
    user,
    isAuthenticated: Boolean(user && getAccessToken()),
    isBootstrapping,
    async login(credentials) {
      const response = await apiClient.post("/auth/login/", credentials);
      setTokens({
        access: response.data.access,
        refresh: response.data.refresh,
      });
      setStoredUser(response.data.user);
      setUser(response.data.user);
      return response.data.user;
    },
    updateUser(nextUser) {
      setStoredUser(nextUser);
      setUser(nextUser);
    },
    logout() {
      clearTokens();
      setUser(null);
      navigate("/login", { replace: true });
    },
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
