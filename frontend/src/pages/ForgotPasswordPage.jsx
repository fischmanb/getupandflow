import { useState } from "react";
import { Link } from "react-router-dom";

import { apiClient } from "../api/client";
import { getErrorMessage } from "../api/utils";

export function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [wasSent, setWasSent] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");

  async function handleSubmit(event) {
    event.preventDefault();
    setErrorMessage("");
    setIsSubmitting(true);
    try {
      await apiClient.post("/auth/password-reset/", { email });
      setWasSent(true);
    } catch (error) {
      setErrorMessage(getErrorMessage(error, "We couldn't send the email. Please try again."));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main className="auth-layout">
      <section className="auth-card">
        <h1>Reset your password</h1>
        {wasSent ? (
          <>
            <p className="subtle-copy">
              If an account exists for <strong>{email}</strong>, a reset link is on its way.
              Check your inbox — the link works for a limited time.
            </p>
            <p className="subtle-copy">
              <Link className="back-link" to="/login">
                Back to login
              </Link>
            </p>
          </>
        ) : (
          <>
            <p className="subtle-copy">
              Enter the email you signed up with and we&apos;ll send you a link to choose a new
              password.
            </p>
            <form className="auth-form" onSubmit={handleSubmit}>
              <label>
                Email
                <input
                  autoComplete="email"
                  name="email"
                  type="email"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  required
                />
              </label>
              {errorMessage ? <p className="form-error">{errorMessage}</p> : null}
              <button disabled={isSubmitting} type="submit">
                {isSubmitting ? "Sending..." : "Send reset link"}
              </button>
            </form>
            <p className="subtle-copy">
              <Link className="back-link" to="/login">
                Back to login
              </Link>
            </p>
          </>
        )}
      </section>
    </main>
  );
}
