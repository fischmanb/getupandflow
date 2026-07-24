import axios from "axios";

import { clearTokens, getAccessToken, getRefreshToken, setTokens } from "../auth/storage";

const DEFAULT_PRODUCTION_API_BASE_URL = "https://remaining-dalila-cheesecakemaster-ed9f83f4.koyeb.app/api";
const DEFAULT_DEVELOPMENT_API_BASE_URL = "http://127.0.0.1:8000/api";

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ||
  (import.meta.env.PROD ? DEFAULT_PRODUCTION_API_BASE_URL : DEFAULT_DEVELOPMENT_API_BASE_URL);

let refreshPromise = null;

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 20000,
});

apiClient.interceptors.request.use((config) => {
  const accessToken = getAccessToken();
  if (accessToken) {
    config.headers.Authorization = `Bearer ${accessToken}`;
  }
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;
    const status = error.response?.status;

    // Auth endpoints answer 401 as a verdict, not an expiry -- never refresh-loop them.
    const isAuthEndpoint = originalRequest?.url?.includes("/auth/login/") || originalRequest?.url?.includes("/auth/refresh/");

    if (status !== 401 || originalRequest?._retry || isAuthEndpoint) {
      return Promise.reject(error);
    }

    const refreshToken = getRefreshToken();
    if (!refreshToken) {
      clearTokens();
      window.dispatchEvent(new Event("auth:expired"));
      return Promise.reject(error);
    }

    originalRequest._retry = true;

    if (!refreshPromise) {
      refreshPromise = axios
        .post(`${API_BASE_URL}/auth/refresh/`, { refresh: refreshToken }, { timeout: 20000 })
        .then((response) => {
          const nextAccess = response.data.access;
          const nextRefresh = response.data.refresh || refreshToken;
          setTokens({ access: nextAccess, refresh: nextRefresh });
          return nextAccess;
        })
        .catch((refreshError) => {
          clearTokens();
          window.dispatchEvent(new Event("auth:expired"));
          throw refreshError;
        })
        .finally(() => {
          refreshPromise = null;
        });
    }

    const nextAccessToken = await refreshPromise;
    originalRequest.headers.Authorization = `Bearer ${nextAccessToken}`;
    return apiClient(originalRequest);
  },
);
