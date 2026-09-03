import { cleanup, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import LoginPage from "./login/page";
import RegisterPage from "./register/page";

const { authFormMock } = vi.hoisted(() => ({
  authFormMock: vi.fn(({ mode }: { mode: string }) => <div data-testid={`auth-form-${mode}`} />)
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
});
