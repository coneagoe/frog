"use client";

import Link from "next/link";
import { type FormEvent, useEffect, useRef, useState } from "react";

import { resendVerificationEmail, verifyEmail } from "@/lib/api-client";

export function VerifyEmailPanel({ token }: { token?: string }) {
  const [message, setMessage] = useState(token ? "Verifying your email address..." : "This verification link is invalid or has expired.");
  const [isAlert, setIsAlert] = useState(!token);
  const [resendEmail, setResendEmail] = useState("");
  const [resendPending, setResendPending] = useState(false);
  const [resendNotice, setResendNotice] = useState<string | null>(null);
  const [resendError, setResendError] = useState(false);
  const attemptedRef = useRef(false);

  useEffect(() => {
    if (!token || attemptedRef.current) return;
    attemptedRef.current = true;
    let active = true;

    void verifyEmail(token)
      .then(() => {
        if (!active) return;
        setMessage("Your email address has been verified. You can now sign in.");
        setIsAlert(false);
      })
      .catch(() => {
        if (!active) return;
        setMessage("This verification link is invalid or has expired.");
        setIsAlert(true);
      });

    return () => {
      active = false;
    };
  }, [token]);

  async function handleResend(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setResendPending(true);
    setResendError(false);
    setResendNotice(null);
    try {
      await resendVerificationEmail({ email: resendEmail.trim().toLowerCase() });
      setResendNotice("If an account exists for that email address, we sent a verification link.");
    } catch {
      setResendError(true);
      setResendNotice(null);
    } finally {
      setResendPending(false);
    }
  }

  return (
    <section className="auth-card" aria-labelledby="verify-email-title">
      <div className="auth-card__intro">
        <p className="auth-card__eyebrow">Paper Trading</p>
        <h1 id="verify-email-title">Verify your email</h1>
        <p role={isAlert ? "alert" : "status"}>{message}</p>
      </div>
      <form className="form auth-form" onSubmit={handleResend} noValidate>
        <label htmlFor="resend-email">
          Email address
          <input
            id="resend-email"
            name="email"
            type="email"
            autoComplete="email"
            value={resendEmail}
            onChange={(event) => {
              setResendEmail(event.target.value);
              setResendError(false);
              setResendNotice(null);
            }}
            required
          />
        </label>
        {resendError && <p role="alert">We couldn&apos;t send a verification link. Try again.</p>}
        {resendNotice && <p role="status">{resendNotice}</p>}
        <button className="button auth-form__submit" type="submit" disabled={resendPending} aria-busy={resendPending}>
          {resendPending ? "Sending verification link..." : "Resend verification email"}
        </button>
      </form>
      <p className="auth-card__switch">
        <Link href="/login">Back to login</Link>
      </p>
    </section>
  );
}
