import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { forgotPassword, login, register, resetPassword } from "@/lib/api-client";
import { parseApiError } from "@/lib/api-error";
import { AuthForm } from "./auth-form";

const { MockApiError } = vi.hoisted(() => ({
  MockApiError: class MockApiError extends Error {
    constructor(public readonly status: number, public readonly code: string, message: string) {
      super(message);
    }
  }
}));

vi.mock("@/lib/api-client", () => ({
  ApiError: MockApiError,
  forgotPassword: vi.fn(),
  login: vi.fn(),
  register: vi.fn(),
  resetPassword: vi.fn()
}));

const pushMock = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: pushMock }) }));

const loginMock = vi.mocked(login);
const registerMock = vi.mocked(register);
const forgotPasswordMock = vi.mocked(forgotPassword);
const resetPasswordMock = vi.mocked(resetPassword);
const identity = { id: 1, email: "trader@example.com", email_verified_at: null };

describe("AuthForm", () => {
  beforeEach(() => {
    cleanup();
    vi.resetAllMocks();
    loginMock.mockResolvedValue(identity);
    registerMock.mockResolvedValue(identity);
    forgotPasswordMock.mockResolvedValue(undefined);
    resetPasswordMock.mockResolvedValue(undefined);
  });

  it("renders associated email and password fields", () => {
    render(<AuthForm mode="login" />);
    expect(screen.getByLabelText("Email address")).toHaveAttribute("type", "email");
    expect(screen.getByLabelText("Password")).toHaveAttribute("type", "password");
  });

  it("separates account creation and password recovery links in the login footer", () => {
    render(<AuthForm mode="login" />);
    const createAccountLink = screen.getByRole("link", { name: "Create an account" });
    const footer = createAccountLink.closest("p");
    expect(footer).toHaveTextContent("Create an account or Forgot password?");
    if (!footer) throw new Error("Login footer was not rendered.");
    expect(within(footer).getByRole("link", { name: "Create an account" })).toHaveAttribute("href", "/register");
    expect(within(footer).getByRole("link", { name: "Forgot password?" })).toHaveAttribute("href", "/forgot-password");
  });

  it("rejects passwords shorter than 12 characters or without a letter and number", async () => {
    const user = userEvent.setup();
    render(<AuthForm mode="login" />);
    await user.type(screen.getByLabelText("Email address"), "trader@example.com");
    await user.type(screen.getByLabelText("Password"), "shortpassword");
    await user.click(screen.getByRole("button", { name: "Log in" }));
    expect(screen.getByRole("alert")).toHaveTextContent("12 characters");
    expect(loginMock).not.toHaveBeenCalled();
  });

  it("toggles password visibility", async () => {
    const user = userEvent.setup();
    render(<AuthForm mode="login" />);
    const password = screen.getByLabelText("Password");
    await user.click(screen.getByRole("button", { name: "Show password" }));
    expect(password).toHaveAttribute("type", "text");
    expect(screen.getByRole("button", { name: "Hide password" })).toBeInTheDocument();
  });

  it("disables submit and shows loading state while request is pending", async () => {
    const user = userEvent.setup();
    loginMock.mockReturnValue(new Promise(() => undefined));
    render(<AuthForm mode="login" />);
    await user.type(screen.getByLabelText("Email address"), "trader@example.com");
    await user.type(screen.getByLabelText("Password"), "Validpassword1");
    await user.click(screen.getByRole("button", { name: "Log in" }));
    expect(screen.getByRole("button", { name: "Logging in..." })).toBeDisabled();
  });

  it("shows a generic server error without exposing credentials", async () => {
    const user = userEvent.setup();
    loginMock.mockRejectedValue(new Error("secret-password-from-server"));
    render(<AuthForm mode="login" />);
    await user.type(screen.getByLabelText("Email address"), "trader@example.com");
    await user.type(screen.getByLabelText("Password"), "Validpassword1");
    await user.click(screen.getByRole("button", { name: "Log in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("We couldn't sign you in. Check your details and try again.");
    expect(screen.queryByText("secret-password-from-server")).not.toBeInTheDocument();
  });

  it("shows unavailable evidence, retains email, and clears password", async () => {
    const user = userEvent.setup();
    const backendResponse = new Response(JSON.stringify({ detail: { code: "AUTH_UNAVAILABLE", message: "登录服务暂时不可用，请稍后重试。", request_id: "evidence-id" } }), { status: 503 });
    const parsedError = await parseApiError(backendResponse);
    Object.setPrototypeOf(parsedError, MockApiError.prototype);
    loginMock.mockRejectedValue(parsedError);
    render(<AuthForm mode="login" />);
    await user.type(screen.getByLabelText("Email address"), "trader@example.com");
    await user.type(screen.getByLabelText("Password"), "Validpassword1");
    await user.click(screen.getByRole("button", { name: "Log in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("登录服务暂时不可用，请稍后重试。");
    expect(screen.getByRole("alert")).toHaveTextContent("evidence-id");
    expect(screen.getByLabelText("Email address")).toHaveValue("trader@example.com");
    expect(screen.getByLabelText("Password")).toHaveValue("");
  });

  it("submits normalized-compatible email and password to login", async () => {
    const user = userEvent.setup();
    render(<AuthForm mode="login" />);
    await user.type(screen.getByLabelText("Email address"), "  TRADER@example.com ");
    await user.type(screen.getByLabelText("Password"), "Validpassword1");
    await user.click(screen.getByRole("button", { name: "Log in" }));
    await waitFor(() => expect(loginMock).toHaveBeenCalledWith({ email: "trader@example.com", password: "Validpassword1" }));
  });

  it("uses register mode for registration", async () => {
    const user = userEvent.setup();
    render(<AuthForm mode="register" />);
    await user.type(screen.getByLabelText("Email address"), "new@example.com");
    await user.type(screen.getByLabelText("Password"), "Validpassword1");
    await user.click(screen.getByRole("button", { name: "Create account" }));
    await waitFor(() => expect(registerMock).toHaveBeenCalledWith({ email: "new@example.com", password: "Validpassword1" }));
    expect(pushMock).not.toHaveBeenCalled();
    expect(screen.getByRole("status")).toHaveTextContent("Check your email for a verification link before signing in.");
  });

  it("calls onSuccess before navigating after login", async () => {
    const user = userEvent.setup();
    const onSuccess = vi.fn();
    render(<AuthForm mode="login" onSuccess={onSuccess} />);
    await user.type(screen.getByLabelText("Email address"), "user@example.com");
    await user.type(screen.getByLabelText("Password"), "Validpassword1");
    await user.click(screen.getByRole("button", { name: "Log in" }));
    await waitFor(() => expect(onSuccess).toHaveBeenCalledWith(identity));
    expect(pushMock).toHaveBeenCalledWith("/accounts");
  });

  it("uses a validated local return path after login", async () => {
    const user = userEvent.setup();
    render(<AuthForm mode="login" returnTo="/orders?status=open" />);
    await user.type(screen.getByLabelText("Email address"), "user@example.com");
    await user.type(screen.getByLabelText("Password"), "Validpassword1");
    await user.click(screen.getByRole("button", { name: "Log in" }));
    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/orders?status=open"));
  });

  it("falls back to accounts for unsafe return paths", async () => {
    const user = userEvent.setup();
    render(<AuthForm mode="login" returnTo="https://example.com/orders" />);
    await user.type(screen.getByLabelText("Email address"), "user@example.com");
    await user.type(screen.getByLabelText("Password"), "Validpassword1");
    await user.click(screen.getByRole("button", { name: "Log in" }));
    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/accounts"));
  });

  it("clears errors on edit and only marks the invalid field", async () => {
    const user = userEvent.setup();
    render(<AuthForm mode="login" />);
    await user.type(screen.getByLabelText("Email address"), "user@example.com");
    await user.click(screen.getByRole("button", { name: "Log in" }));
    expect(screen.getByLabelText("Password")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByLabelText("Email address")).toHaveAttribute("aria-invalid", "false");
    await user.type(screen.getByLabelText("Password"), "Validpassword1");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Password")).toHaveAttribute("aria-invalid", "false");
  });

  it.each(["1234567890a", "abcdefghijkl", "123456789012"])("rejects password boundary %s", async (invalidPassword) => {
    const user = userEvent.setup();
    render(<AuthForm mode="login" />);
    await user.type(screen.getByLabelText("Email address"), "user@example.com");
    await user.type(screen.getByLabelText("Password"), invalidPassword);
    await user.click(screen.getByRole("button", { name: "Log in" }));
    expect(loginMock).not.toHaveBeenCalled();
  });

  it("rejects an email with more than one at-sign", async () => {
    const user = userEvent.setup();
    render(<AuthForm mode="login" />);
    await user.type(screen.getByLabelText("Email address"), "a@b@c.com");
    await user.type(screen.getByLabelText("Password"), "Validpassword1");
    await user.click(screen.getByRole("button", { name: "Log in" }));
    expect(screen.getByRole("alert")).toHaveTextContent("valid email address");
    expect(loginMock).not.toHaveBeenCalled();
  });

  it("validates, submits, and confirms a password reset link request", async () => {
    const user = userEvent.setup();
    render(<AuthForm mode="forgot-password" />);
    await user.click(screen.getByRole("button", { name: "Send reset link" }));
    expect(screen.getByRole("alert")).toHaveTextContent("valid email address");
    await user.type(screen.getByLabelText("Email address"), " TRADER@example.com ");
    await user.click(screen.getByRole("button", { name: "Send reset link" }));
    await waitFor(() => expect(forgotPasswordMock).toHaveBeenCalledWith({ email: "trader@example.com" }));
    expect(screen.getByRole("status")).toHaveTextContent("If an account exists for that email address, we sent a password reset link.");
  });

  it("shows loading and generic error states when requesting a password reset link", async () => {
    const user = userEvent.setup();
    forgotPasswordMock.mockReturnValue(new Promise(() => undefined));
    render(<AuthForm mode="forgot-password" />);
    await user.type(screen.getByLabelText("Email address"), "trader@example.com");
    await user.click(screen.getByRole("button", { name: "Send reset link" }));
    expect(screen.getByRole("button", { name: "Sending reset link..." })).toBeDisabled();

    cleanup();
    forgotPasswordMock.mockRejectedValue(new Error("sensitive server error"));
    render(<AuthForm mode="forgot-password" />);
    await user.type(screen.getByLabelText("Email address"), "trader@example.com");
    await user.click(screen.getByRole("button", { name: "Send reset link" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("We couldn't send a password reset link. Try again.");
  });

  it("validates and resets a password with the supplied reset token", async () => {
    const user = userEvent.setup();
    render(<AuthForm mode="reset-password" token="reset-token" />);
    await user.click(screen.getByRole("button", { name: "Reset password" }));
    expect(screen.getByRole("alert")).toHaveTextContent("12 characters");
    await user.type(screen.getByLabelText("New password"), "Validpassword1");
    await user.click(screen.getByRole("button", { name: "Reset password" }));
    await waitFor(() => expect(resetPasswordMock).toHaveBeenCalledWith({ token: "reset-token", password: "Validpassword1" }));
    expect(screen.getByRole("status")).toHaveTextContent("Your password has been reset. You can now log in.");
  });

  it("shows expired-link states for missing and rejected reset tokens", async () => {
    const user = userEvent.setup();
    render(<AuthForm mode="reset-password" />);
    expect(screen.getByText("This password reset link is invalid or has expired.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Request a new reset link" })).toHaveAttribute("href", "/forgot-password");

    cleanup();
    resetPasswordMock.mockRejectedValue(new MockApiError(410, "RESET_TOKEN_EXPIRED", "expired"));
    render(<AuthForm mode="reset-password" token="expired-token" />);
    await user.type(screen.getByLabelText("New password"), "Validpassword1");
    await user.click(screen.getByRole("button", { name: "Reset password" }));
    expect(await screen.findByText("This password reset link is invalid or has expired.")).toBeInTheDocument();
  });
});
