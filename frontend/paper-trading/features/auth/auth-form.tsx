"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { type FormEvent, useState } from "react";
import { ApiError, forgotPassword, login, register, resetPassword } from "@/lib/api-client";
import type { AuthIdentity } from "@/lib/types";

type AuthMode = "login" | "register" | "forgot-password" | "reset-password";

function getSafeReturnPath(returnTo?: string) {
  return typeof returnTo === "string" && /^\/(?!\/)/.test(returnTo) && !returnTo.includes("\\") ? returnTo : "/accounts";
}

export function AuthForm({ mode, token, returnTo, onSuccess }: { mode: AuthMode; token?: string; returnTo?: string; onSuccess?: (identity: AuthIdentity) => void | Promise<void> }) {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [emailError, setEmailError] = useState(false);
  const [passwordError, setPasswordError] = useState(false);
  const [pending, setPending] = useState(false);
  const [success, setSuccess] = useState<string | null>(null);
  const [expired, setExpired] = useState(mode === "reset-password" && !token);
  const isRegister = mode === "register";
  const isLogin = mode === "login";
  const isForgot = mode === "forgot-password";
  const isReset = mode === "reset-password";
  const actionLabel = isRegister ? "Create account" : isForgot ? "Send reset link" : isReset ? "Reset password" : "Log in";
  const pendingLabel = isRegister ? "Creating account..." : isForgot ? "Sending reset link..." : isReset ? "Resetting password..." : "Logging in...";
  const loginTarget = getSafeReturnPath(returnTo);

  if (expired) return <section className="auth-card" aria-labelledby="auth-title"><div className="auth-card__intro"><p className="auth-card__eyebrow">Paper Trading</p><h1 id="auth-title">Reset your password</h1><p role="alert">This password reset link is invalid or has expired.</p></div><p className="auth-card__switch"><Link href="/forgot-password">Request a new reset link</Link></p></section>;

  function validate(): string | null {
    const normalizedEmail = email.trim().toLowerCase();
    if ((isLogin || isRegister || isForgot) && (!normalizedEmail || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(normalizedEmail))) return "Enter a valid email address.";
    if ((isLogin || isRegister || isReset) && (password.length < 12 || !/[A-Za-z]/.test(password) || !/[0-9]/.test(password))) return "Password must be at least 12 characters and include a letter and a number.";
    return null;
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const validationError = validate();
    if (validationError) {
      setFieldError(validationError);
      setEmailError((isLogin || isRegister || isForgot) && (!email.trim() || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())));
      setPasswordError((isLogin || isRegister || isReset) && (password.length < 12 || !/[A-Za-z]/.test(password) || !/[0-9]/.test(password)));
      return;
    }
    setFieldError(null);
    setEmailError(false);
    setPasswordError(false);
    setError(null);
    setSuccess(null);
    setPending(true);
    try {
      const normalizedEmail = email.trim().toLowerCase();
      if (isRegister || isLogin) {
        const identity = isRegister ? await register({ email: normalizedEmail, password }) : await login({ email: normalizedEmail, password });
        if (isRegister) {
          setSuccess("Check your email for a verification link before signing in.");
        } else {
          await onSuccess?.(identity);
          router.push(loginTarget);
        }
      } else if (isForgot) {
        await forgotPassword({ email: normalizedEmail });
        setSuccess("If an account exists for that email address, we sent a password reset link.");
      } else {
        await resetPassword({ token: token ?? "", password });
        setSuccess("Your password has been reset. You can now log in.");
      }
    } catch (requestError) {
      if (isReset && requestError instanceof ApiError && (requestError.status === 400 || requestError.status === 410)) {
        setExpired(true);
      } else {
        setError(isRegister ? "We couldn't create your account. Check your details and try again." : isForgot ? "We couldn't send a password reset link. Try again." : isReset ? "We couldn't reset your password. Try again." : "We couldn't sign you in. Check your details and try again.");
      }
    } finally {
      setPending(false);
    }
  }

  const describedBy = [fieldError && "auth-field-error", error && "auth-server-error"].filter(Boolean).join(" ") || undefined;

  return (
    <section className="auth-card" aria-labelledby="auth-title">
      <div className="auth-card__intro">
        <p className="auth-card__eyebrow">Paper Trading</p>
        <h1 id="auth-title">{isRegister ? "Create your operator account" : isForgot ? "Reset your password" : isReset ? "Choose a new password" : "Welcome back"}</h1>
        <p>{isRegister ? "Set up secure access to your trading desk." : isForgot ? "We will send a reset link to the email address on file." : isReset ? "Choose a new password for your account." : "Sign in to continue to your trading desk."}</p>
      </div>
      <form className="form auth-form" onSubmit={handleSubmit} noValidate>
        {(isLogin || isRegister || isForgot) && <label htmlFor="auth-email">
          Email address
          <input id="auth-email" name="email" type="email" autoComplete="email" value={email} onChange={(event) => { setEmail(event.target.value); setError(null); setFieldError(null); setEmailError(false); }} aria-invalid={emailError} aria-describedby={describedBy} required />
        </label>}
        {(isLogin || isRegister || isReset) && <label htmlFor="auth-password">
          {isReset ? "New password" : "Password"}
          <span className="auth-form__password">
            <input id="auth-password" name="password" type={showPassword ? "text" : "password"} autoComplete={isRegister || isReset ? "new-password" : "current-password"} value={password} onChange={(event) => { setPassword(event.target.value); setError(null); setFieldError(null); setPasswordError(false); }} aria-invalid={passwordError} aria-describedby={describedBy} required />
            <button className="auth-form__visibility" type="button" onClick={() => setShowPassword((visible) => !visible)} aria-label={showPassword ? "Hide password" : "Show password"} aria-pressed={showPassword}>
              {showPassword ? "Hide" : "Show"}
            </button>
          </span>
        </label>}
        {fieldError && <p className="filter-error" id="auth-field-error" role="alert">{fieldError}</p>}
        {error && <p className="error-banner" id="auth-server-error" role="alert">{error}</p>}
        {success && <p role="status">{success}</p>}
        <button className="button auth-form__submit" type="submit" disabled={pending} aria-busy={pending}>
          {pending ? pendingLabel : actionLabel}
        </button>
      </form>
      <p className="auth-card__switch">
        {isRegister ? "Already have an account?" : isForgot || isReset ? "Need to sign in?" : "New to Paper Trading?"} {isRegister || isForgot || isReset ? <Link href="/login">Back to login</Link> : <><Link href="/register">Create an account</Link> <Link href="/forgot-password">Forgot password?</Link></>}
      </p>
    </section>
  );
}
