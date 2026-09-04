import { cleanup, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import ForgotPasswordPage from "./forgot-password/page";
import LoginPage from "./login/page";
import ResetPasswordPage from "./reset-password/page";
import RegisterPage from "./register/page";
import VerifyEmailPage from "./verify-email/page";

const { authFormMock } = vi.hoisted(() => ({
  authFormMock: vi.fn(({ mode, token }: { mode: string; token?: string }) => <div data-testid={`auth-form-${mode}`} data-token={token} />)
}));

const { verifyEmailPanelMock } = vi.hoisted(() => ({
  verifyEmailPanelMock: vi.fn(({ token }: { token?: string }) => <div data-testid="verify-email-panel" data-token={token} />)
}));

vi.mock("@/features/auth/auth-form", () => ({ AuthForm: authFormMock }));
vi.mock("@/features/auth/verify-email-panel", () => ({ VerifyEmailPanel: verifyEmailPanelMock }));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() })
}));

describe("auth pages", () => {
  afterEach(cleanup);

  it("renders login and register pages with the correct mode", () => {
    render(<LoginPage />);
    expect(screen.getByTestId("auth-form-login")).toBeInTheDocument();
    expect(authFormMock.mock.lastCall?.[0]).toEqual({ mode: "login" });

    cleanup();
    render(<RegisterPage />);
    expect(screen.getByTestId("auth-form-register")).toBeInTheDocument();
    expect(authFormMock.mock.lastCall?.[0]).toEqual({ mode: "register" });
  });

  it("renders forgot-password and reset-password pages with the correct mode", async () => {
    render(<ForgotPasswordPage />);
    expect(screen.getByTestId("auth-form-forgot-password")).toBeInTheDocument();
    expect(authFormMock.mock.lastCall?.[0]).toEqual({ mode: "forgot-password" });

    cleanup();
    render(await ResetPasswordPage({ searchParams: Promise.resolve({ token: "reset-token" }) }));
    expect(screen.getByTestId("auth-form-reset-password")).toHaveAttribute("data-token", "reset-token");
    expect(authFormMock.mock.lastCall?.[0]).toEqual({ mode: "reset-password", token: "reset-token" });
  });

  it("renders the verification page", async () => {
    render(await VerifyEmailPage({ searchParams: Promise.resolve({ token: "verify-token" }) }));
    expect(screen.getByTestId("verify-email-panel")).toHaveAttribute("data-token", "verify-token");
    expect(verifyEmailPanelMock).toHaveBeenCalledWith({ token: "verify-token" }, undefined);
  });
});
