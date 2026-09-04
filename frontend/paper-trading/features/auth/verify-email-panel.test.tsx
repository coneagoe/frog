import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { verifyEmailMock } = vi.hoisted(() => ({
  verifyEmailMock: vi.fn()
}));

const { resendVerificationEmailMock } = vi.hoisted(() => ({
  resendVerificationEmailMock: vi.fn()
}));

vi.mock("@/lib/api-client", () => ({
  resendVerificationEmail: resendVerificationEmailMock,
  verifyEmail: verifyEmailMock
}));

import { VerifyEmailPanel } from "./verify-email-panel";

describe("VerifyEmailPanel", () => {
  beforeEach(() => {
    cleanup();
    vi.resetAllMocks();
  });

  function deferred<T>() {
    let resolve!: (value: T | PromiseLike<T>) => void;
    let reject!: (reason?: unknown) => void;
    const promise = new Promise<T>((promiseResolve, promiseReject) => {
      resolve = promiseResolve;
      reject = promiseReject;
    });
    return { promise, resolve, reject };
  }

  it("invokes verifyEmail for a present token and renders success", async () => {
    verifyEmailMock.mockResolvedValue({ message: "ok" });

    render(<VerifyEmailPanel token="verify-token" />);

    await waitFor(() => expect(verifyEmailMock).toHaveBeenCalledWith("verify-token"));
    expect(screen.getByRole("status")).toHaveTextContent("verified");
    expect(screen.getByRole("link", { name: "Back to login" })).toHaveAttribute("href", "/login");
  });

  it("renders generic failure when verification fails", async () => {
    verifyEmailMock.mockRejectedValue(new Error("backend failed"));

    render(<VerifyEmailPanel token="expired-token" />);

    await waitFor(() => expect(verifyEmailMock).toHaveBeenCalledWith("expired-token"));
    expect(screen.getByRole("alert")).toHaveTextContent("invalid or has expired");
  });

  it("does not invoke verifyEmail without a token", async () => {
    render(<VerifyEmailPanel />);

    expect(verifyEmailMock).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent("invalid or has expired");
  });

  it("resends verification email with generic success and pending states", async () => {
    const user = userEvent.setup();
    const request = deferred<{ message: string }>();
    resendVerificationEmailMock.mockReturnValue(request.promise);

    render(<VerifyEmailPanel />);

    await user.type(screen.getByLabelText("Email address"), "Trader@Example.com ");
    await user.click(screen.getByRole("button", { name: "Resend verification email" }));
    expect(screen.getByRole("button", { name: "Sending verification link..." })).toBeDisabled();
    request.resolve({ message: "ok" });
    await waitFor(() => expect(resendVerificationEmailMock).toHaveBeenCalledWith({ email: "trader@example.com" }));
    expect(screen.getByRole("status")).toHaveTextContent("If an account exists for that email address, we sent a verification link.");
  });

  it("shows a generic resend failure without provider details", async () => {
    const user = userEvent.setup();
    resendVerificationEmailMock.mockRejectedValue(new Error("smtp provider failed"));

    render(<VerifyEmailPanel />);

    await user.type(screen.getByLabelText("Email address"), "trader@example.com");
    await user.click(screen.getByRole("button", { name: "Resend verification email" }));
    expect(await screen.findByText("We couldn't send a verification link. Try again.")).toBeInTheDocument();
    expect(screen.queryByText("smtp provider failed")).not.toBeInTheDocument();
  });
});
