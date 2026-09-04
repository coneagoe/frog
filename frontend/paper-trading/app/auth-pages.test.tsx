import { cleanup, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import ForgotPasswordPage from "./forgot-password/page";
import LoginPage from "./login/page";
import ResetPasswordPage from "./reset-password/page";
import RegisterPage from "./register/page";

const { authFormMock } = vi.hoisted(() => ({
  authFormMock: vi.fn(({ mode, token }: { mode: string; token?: string }) => <div data-testid={`auth-form-${mode}`} data-token={token} />)
}));

vi.mock("@/features/auth/auth-form", () => ({ AuthForm: authFormMock }));

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
});
