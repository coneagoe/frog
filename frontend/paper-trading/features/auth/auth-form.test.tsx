import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { login, register } from "@/lib/api-client";
import { AuthForm } from "./auth-form";

vi.mock("@/lib/api-client", () => ({
  login: vi.fn(),
  register: vi.fn()
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() })
}));

const loginMock = vi.mocked(login);
const registerMock = vi.mocked(register);
const identity = { id: 1, email: "trader@example.com", email_verified_at: null };

describe("AuthForm", () => {
  beforeEach(() => {
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
    render(<AuthForm mode="register" />);
    expect(screen.getByRole("button", { name: "Create account" })).toBeInTheDocument();
    expect(registerMock).not.toHaveBeenCalled();
  });
});
