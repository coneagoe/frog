"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { type FormEvent, useState } from "react";
import { login, register } from "@/lib/api-client";
import type { AuthIdentity } from "@/lib/types";

type AuthMode = "login" | "register";

export function AuthForm({ mode, onSuccess }: { mode: AuthMode; onSuccess?: (identity: AuthIdentity) => void | Promise<void> }) {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [emailError, setEmailError] = useState(false);
  const [passwordError, setPasswordError] = useState(false);
  const [pending, setPending] = useState(false);
  const isRegister = mode === "register";
  const actionLabel = isRegister ? "Create account" : "Log in";
  const pendingLabel = isRegister ? "Creating account..." : "Logging in...";

  function validate(): string | null {
    const normalizedEmail = email.trim().toLowerCase();
    if (!normalizedEmail || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(normalizedEmail)) return "Enter a valid email address.";
    if (password.length < 12 || !/[A-Za-z]/.test(password) || !/[0-9]/.test(password)) return "Password must be at least 12 characters and include a letter and a number.";
    return null;
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const validationError = validate();
    if (validationError) {
      setFieldError(validationError);
      setEmailError(!email.trim() || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim()));
      setPasswordError(password.length < 12 || !/[A-Za-z]/.test(password) || !/[0-9]/.test(password));
      return;
    }
    setFieldError(null);
    setEmailError(false);
    setPasswordError(false);
    setError(null);
    setPending(true);
    try {
      const input = { email: email.trim().toLowerCase(), password };
      const identity = isRegister ? await register(input) : await login(input);
      await onSuccess?.(identity);
      router.push(isRegister ? "/login" : "/accounts");
    } catch {
      setError(isRegister ? "We couldn't create your account. Check your details and try again." : "We couldn't sign you in. Check your details and try again.");
    } finally {
      setPending(false);
    }
  }

  const describedBy = [fieldError && "auth-field-error", error && "auth-server-error"].filter(Boolean).join(" ") || undefined;

  return (
    <section className="auth-card" aria-labelledby="auth-title">
      <div className="auth-card__intro">
        <p className="auth-card__eyebrow">Paper Trading</p>
        <h1 id="auth-title">{isRegister ? "Create your operator account" : "Welcome back"}</h1>
        <p>{isRegister ? "Set up secure access to your trading desk." : "Sign in to continue to your trading desk."}</p>
      </div>
      <form className="form auth-form" onSubmit={handleSubmit} noValidate>
        <label htmlFor="auth-email">
          Email address
          <input id="auth-email" name="email" type="email" autoComplete="email" value={email} onChange={(event) => { setEmail(event.target.value); setError(null); setFieldError(null); setEmailError(false); }} aria-invalid={emailError} aria-describedby={describedBy} required />
        </label>
        <label htmlFor="auth-password">
          Password
          <span className="auth-form__password">
            <input id="auth-password" name="password" type={showPassword ? "text" : "password"} autoComplete={isRegister ? "new-password" : "current-password"} value={password} onChange={(event) => { setPassword(event.target.value); setError(null); setFieldError(null); setPasswordError(false); }} aria-invalid={passwordError} aria-describedby={describedBy} required />
            <button className="auth-form__visibility" type="button" onClick={() => setShowPassword((visible) => !visible)} aria-label={showPassword ? "Hide password" : "Show password"} aria-pressed={showPassword}>
              {showPassword ? "Hide" : "Show"}
            </button>
          </span>
        </label>
        {fieldError && <p className="filter-error" id="auth-field-error" role="alert">{fieldError}</p>}
        {error && <p className="error-banner" id="auth-server-error" role="alert">{error}</p>}
        <button className="button auth-form__submit" type="submit" disabled={pending} aria-busy={pending}>
          {pending ? pendingLabel : actionLabel}
        </button>
      </form>
      <p className="auth-card__switch">
        {isRegister ? "Already have an account?" : "New to Paper Trading?"} {isRegister ? <Link href="/login">Back to login</Link> : <Link href="/register">Create an account</Link>}
      </p>
    </section>
  );
}
