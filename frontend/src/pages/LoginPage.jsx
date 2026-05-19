import { useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";

import { getErrorMessage } from "../api/utils";
import { useAuth } from "../auth/AuthContext";

export function LoginPage() {
  const navigate = useNavigate();
  const { isAuthenticated, login } = useAuth();
  const [formData, setFormData] = useState({ username: "", password: "" });
  const [errorMessage, setErrorMessage] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  if (isAuthenticated) {
    return <Navigate to="/app" replace />;
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setErrorMessage("");
    setIsSubmitting(true);

    try {
      await login(formData);
      navigate("/app", { replace: true });
    } catch (error) {
      setErrorMessage(getErrorMessage(error, "Invalid username or password."));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main className="auth-layout">
      <section className="auth-card">
        <h1>Sign in to Get Up and Flow</h1>
        <p className="subtle-copy">Welcome back.</p>
        <form className="auth-form" onSubmit={handleSubmit}>
          <label>
            Username
            <input
              autoComplete="username"
              name="username"
              value={formData.username}
              onChange={(event) => setFormData((current) => ({ ...current, username: event.target.value }))}
              required
            />
          </label>
          <label>
            Password
            <input
              autoComplete="current-password"
              name="password"
              type="password"
              value={formData.password}
              onChange={(event) => setFormData((current) => ({ ...current, password: event.target.value }))}
              required
            />
          </label>
          {errorMessage ? <p className="form-error">{errorMessage}</p> : null}
          <button type="submit" disabled={isSubmitting}>
            {isSubmitting ? "Signing in..." : "Sign in"}
          </button>
        </form>
      </section>
    </main>
  );
}
