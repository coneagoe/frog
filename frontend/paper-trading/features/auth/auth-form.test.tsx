import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { login, register } from "@/lib/api-client";
import { AuthForm } from "./auth-form";

vi.mock("@/lib/api-client", () => ({
  login: vi.fn(),
  register: vi.fn()
}));

const pushMock = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: pushMock }) }));

const loginMock = vi.mocked(login);
const registerMock = vi.mocked(register);
const identity = { id: 1, email: "trader@example.com", email_verified_at: null };

describe("AuthForm", () => {
  beforeEach(() => {
    cleanup();
    vi.resetAllMocks();
    loginMock.mockResolvedValue(identity);
    registerMock.mockResolvedValue(identity);
  });

  it("renders associated email and password fields", () => {
    render(<AuthForm mode="login" />);
    expect(screen.getByLabelText("Email address")).toHaveAttribute("type", "email");
    expect(screen.getByLabelText("Password")).toHaveAttribute("type", "password");
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
    expect(pushMock).toHaveBeenCalledWith("/login");
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
});
